from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

from player_wiki import file_publication
from player_wiki.auth_store import AuthStore
from player_wiki.backup_archive import create_backup_archive_v2
from player_wiki.campaign_content_service import prepare_campaign_page_write
from player_wiki.campaign_page_store import CampaignPageStore
from player_wiki.db import close_db, get_db
from player_wiki.operations import restore_backup_archive
from player_wiki.player_wiki_reconciliation import (
    PlayerWikiReconciler,
    PlayerWikiReconciliationConflict,
    ReconciliationHooks,
)
from player_wiki.repository_store import RepositoryStore


def _campaign(app):
    campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
    assert campaign is not None
    return campaign


def _create_page(
    app,
    page_ref: str,
    *,
    title: str = "Delete Target",
    image: str = "",
    body: str | None = None,
):
    campaign = _campaign(app)
    metadata = {
        "slug": page_ref,
        "title": title,
        "section": "Notes",
        "type": "note",
        "published": True,
    }
    if image:
        metadata["image"] = image
    prepared = prepare_campaign_page_write(
        campaign,
        page_ref,
        metadata=metadata,
        body_markdown=body if body is not None else f"Body for {title}.",
        page_store=app.extensions["campaign_page_store"],
    )
    return campaign, app.extensions["player_wiki_reconciler"].mutate(
        campaign,
        prepared,
        operation_kind="api_upsert",
    )


def _deletion_row():
    return get_db().execute(
        "SELECT * FROM player_wiki_deletion_operations"
    ).fetchone()


def _audit_count() -> int:
    return int(
        get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_deleted'"
        ).fetchone()[0]
    )


def _delete_browser(reconciler, campaign, record, actor_id):
    return reconciler.delete(
        campaign,
        record,
        operation_kind="browser_delete",
        audit_event_type="campaign_wiki_page_deleted",
        audit_actor_user_id=actor_id,
        audit_metadata={
            "page_ref": record.page_ref,
            "route_slug": record.page.route_slug,
            "source": "dm_content_player_wiki",
        },
    )


def _new_reconciler(app):
    return PlayerWikiReconciler(
        page_store=app.extensions["campaign_page_store"],
        repository_store=app.extensions["repository_store"],
        auth_store=app.extensions["auth_store"],
    )


def _zero_recovery_counts():
    return {"recovered": 0, "aborted": 0, "conflict": 0, "pending": 0}


def test_delete_precommit_crash_aborts_without_file_row_or_audit_effect(app, users):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-precommit")
        reconciler = app.extensions["player_wiki_reconciler"]
        original = record.file_path.read_bytes()

        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("before move"))
                if event == "before_tombstone_move"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="before move"):
            _delete_browser(reconciler, campaign, record, users["dm"]["id"])
        assert record.file_path.read_bytes() == original
        assert _deletion_row() is None
        assert _audit_count() == 0
        assert record.file_path.read_bytes() == original
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is not None


def test_tombstone_basename_is_operation_only_and_within_windows_path_budget(app):
    with app.app_context():
        campaign, record = _create_page(app, "notes/tombstone-budget")
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("inspect tombstone"))
                if event == "after_tombstone_move"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="inspect tombstone"):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        row = _deletion_row()
        tombstone = PurePosixPath(str(row["tombstone_ref"]))
        assert tombstone.parent == PurePosixPath("notes")
        assert tombstone.name == f".{row['operation_id']}.del"
        assert len(tombstone.name.encode("utf-8")) == 37
        assert len(tombstone.name.encode("utf-8")) <= 40
        assert "tombstone-budget" not in tombstone.name

        from player_wiki.player_wiki_reconciliation import _deletion_tombstone_ref

        long_leaf = "x" * 180
        synthetic = PurePosixPath(
            _deletion_tombstone_ref(
                f"notes/{long_leaf}.md",
                str(row["operation_id"]),
            )
        )
        assert synthetic.name == tombstone.name
        assert len(synthetic.name.encode("utf-8")) <= 40
        assert long_leaf not in synthetic.name


def test_stale_precommit_reconciler_does_not_report_second_abort(app, monkeypatch):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-stale-precommit")
        creator = app.extensions["player_wiki_reconciler"]
        creator.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("prepared only"))
                if event == "after_delete_prepare"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="prepared only"):
            creator.delete(campaign, record, operation_kind="api_delete")

        winner = _new_reconciler(app)
        stale = _new_reconciler(app)
        original_delete = stale._delete_deletion_precommit
        winner_outcomes = []

        def finish_first(operation_id):
            winner_outcomes.append(winner._continue_deletion(campaign, operation_id))
            return original_delete(operation_id)

        monkeypatch.setattr(stale, "_delete_deletion_precommit", finish_first)
        assert stale.recover_pending() == _zero_recovery_counts()
        assert winner_outcomes == [False]
        assert _deletion_row() is None
        assert record.file_path.exists()
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is not None
        assert _audit_count() == 0


def test_stale_conflict_reconciler_follows_completed_finalizer_without_false_count(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-stale-conflict")
        creator = app.extensions["player_wiki_reconciler"]
        creator.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("committed tombstone"))
                if event == "after_tombstone_move"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="committed tombstone"):
            _delete_browser(creator, campaign, record, users["dm"]["id"])
        record.file_path.write_bytes(b"transient third source")

        winner = _new_reconciler(app)
        stale = _new_reconciler(app)
        original_mark = stale._mark_deletion_conflict
        winner_outcomes = []

        def finalize_first(operation_id, error_code, *, expected_state):
            record.file_path.unlink()
            winner_outcomes.append(winner._continue_deletion(campaign, operation_id))
            return original_mark(
                operation_id,
                error_code,
                expected_state=expected_state,
            )

        monkeypatch.setattr(stale, "_mark_deletion_conflict", finalize_first)
        assert stale.recover_pending() == _zero_recovery_counts()
        assert winner_outcomes == [True]
        assert _deletion_row() is None
        assert not record.file_path.exists()
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is None
        assert _audit_count() == 1


def test_stale_conflict_reconciler_follows_repository_pending_without_false_conflict(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-stale-advanced")
        creator = app.extensions["player_wiki_reconciler"]
        creator.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("committed tombstone"))
                if event == "after_tombstone_move"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="committed tombstone"):
            _delete_browser(creator, campaign, record, users["dm"]["id"])
        record.file_path.write_bytes(b"transient third source")

        winner = _new_reconciler(app)
        winner.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("winner pending"))
                if event == "before_delete_repository_refresh"
                else None
            )
        )
        stale = _new_reconciler(app)
        original_mark = stale._mark_deletion_conflict
        winner_outcomes = []

        def advance_first(operation_id, error_code, *, expected_state):
            record.file_path.unlink()
            try:
                winner._continue_deletion(campaign, operation_id)
            except RuntimeError as exc:
                winner_outcomes.append(str(exc))
            assert _deletion_row()["state"] == "repository_pending"
            return original_mark(
                operation_id,
                error_code,
                expected_state=expected_state,
            )

        monkeypatch.setattr(stale, "_mark_deletion_conflict", advance_first)
        assert stale.recover_pending() == {
            "recovered": 1,
            "aborted": 0,
            "conflict": 0,
            "pending": 0,
        }
        assert winner_outcomes == ["winner pending"]
        assert _deletion_row() is None
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is None
        assert _audit_count() == 1


def test_stale_repository_finalizer_does_not_report_duplicate_recovery(
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-stale-finalizer")
        creator = app.extensions["player_wiki_reconciler"]
        creator.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("repository pending"))
                if event == "before_delete_repository_refresh"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="repository pending"):
            _delete_browser(creator, campaign, record, users["dm"]["id"])
        assert _deletion_row()["state"] == "repository_pending"

        winner = _new_reconciler(app)
        stale = _new_reconciler(app)
        original_cleanup = stale._refresh_and_cleanup_deletion
        winner_outcomes = []

        def finalize_first(campaign_arg, operation, source_path, tombstone_path):
            winner_outcomes.append(
                winner._continue_deletion(campaign_arg, operation.operation_id)
            )
            return original_cleanup(
                campaign_arg,
                operation,
                source_path,
                tombstone_path,
            )

        monkeypatch.setattr(stale, "_refresh_and_cleanup_deletion", finalize_first)
        assert stale.recover_pending() == _zero_recovery_counts()
        assert winner_outcomes == [True]
        assert _deletion_row() is None
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is None
        assert _audit_count() == 1


@pytest.mark.parametrize(
    "failure_event",
    [
        "after_tombstone_move",
        "after_delete_page_row",
        "after_delete_audit_insert",
        "after_delete_repository_pending",
        "before_delete_repository_refresh",
        "after_delete_repository_refresh",
        "before_tombstone_cleanup",
        "after_tombstone_cleanup",
        "before_delete_journal_cleanup",
        "after_delete_journal_cleanup",
    ],
)
def test_delete_crash_boundaries_recover_forward_once(app, users, failure_event):
    with app.app_context():
        campaign, record = _create_page(app, f"notes/delete-{failure_event}")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == failure_event:
                raise RuntimeError(failure_event)

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match=failure_event):
            _delete_browser(reconciler, campaign, record, users["dm"]["id"])
        row = _deletion_row()
        assert row is not None
        assert row["state"] in {"prepared", "repository_pending"}

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["recovered"] == 1
        assert _deletion_row() is None
        assert not record.file_path.exists()
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is None
        assert record.page_ref not in app.extensions["repository_store"].get().get_campaign(
            campaign.slug
        ).pages
        assert _audit_count() == 1


@pytest.mark.parametrize("pair", ["source-third", "tomb-third", "both", "neither"])
def test_prepared_third_file_states_conflict_without_overwrite(app, pair):
    with app.app_context():
        campaign, record = _create_page(app, f"notes/delete-conflict-{pair}")
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("moved"))
                if event == "after_tombstone_move"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="moved"):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        row = _deletion_row()
        tombstone = Path(campaign.player_content_dir) / Path(*str(row["tombstone_ref"]).split("/"))
        original = tombstone.read_bytes()
        if pair == "source-third":
            record.file_path.write_bytes(b"third source")
        elif pair == "tomb-third":
            tombstone.write_bytes(b"third tombstone")
        elif pair == "both":
            record.file_path.write_bytes(original)
        else:
            tombstone.unlink()

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["conflict"] == 1
        row = _deletion_row()
        assert row["state"] == "conflict"
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is not None
        if pair in {"source-third", "both"}:
            assert record.file_path.exists()
        if pair != "neither":
            assert tombstone.exists()


@pytest.mark.parametrize("failure_event", ["before_delete_repository_refresh", "before_tombstone_cleanup"])
def test_repository_pending_source_reappearance_retains_conflict_and_evidence(
    app,
    failure_event,
):
    with app.app_context():
        campaign, record = _create_page(app, f"notes/delete-reappear-{failure_event}")
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("pending"))
                if event == failure_event
                else None
            )
        )
        with pytest.raises(RuntimeError, match="pending"):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        row = _deletion_row()
        assert row["state"] == "repository_pending"
        tombstone = Path(campaign.player_content_dir) / Path(*str(row["tombstone_ref"]).split("/"))
        record.file_path.write_bytes(b"reappeared third source")

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["conflict"] == 1
        assert _deletion_row()["state"] == "conflict"
        assert record.file_path.read_bytes() == b"reappeared third source"
        assert tombstone.exists()


@pytest.mark.parametrize("mutation_event", ["after_delete_page_row", "after_delete_audit_insert"])
def test_finalization_authority_change_rolls_back_page_and_audit_before_conflict(
    app,
    users,
    mutation_event,
):
    with app.app_context():
        campaign, record = _create_page(app, f"notes/delete-finalize-{mutation_event}")
        reconciler = app.extensions["player_wiki_reconciler"]

        def mutate_authority(event, _operation_id):
            if event == mutation_event:
                record.file_path.write_bytes(b"late third source")

        reconciler.hooks = ReconciliationHooks(on_event=mutate_authority)
        with pytest.raises(PlayerWikiReconciliationConflict):
            _delete_browser(reconciler, campaign, record, users["dm"]["id"])
        row = _deletion_row()
        assert row["state"] == "conflict"
        assert row["error_code"] == "delete_finalize_state_conflict"
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug, record.page_ref
        ) is not None
        assert _audit_count() == 0
        assert record.file_path.read_bytes() == b"late third source"


def test_tombstone_unlink_failure_retains_retryable_journal_and_evidence(
    app,
    monkeypatch,
):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-unlink-retry")
        reconciler = app.extensions["player_wiki_reconciler"]
        from player_wiki import player_wiki_reconciliation as reconciliation_module

        original_unlink = reconciliation_module.durable_unlink_file
        monkeypatch.setattr(
            reconciliation_module,
            "durable_unlink_file",
            lambda _path: (_ for _ in ()).throw(OSError("injected unlink failure")),
        )
        with pytest.raises(OSError, match="injected unlink failure"):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        row = _deletion_row()
        assert row["state"] == "repository_pending"
        tombstone = Path(campaign.player_content_dir) / Path(*str(row["tombstone_ref"]).split("/"))
        assert tombstone.exists()

        monkeypatch.setattr(
            reconciliation_module,
            "durable_unlink_file",
            original_unlink,
        )
        assert reconciler.recover_pending()["recovered"] == 1
        assert _deletion_row() is None
        assert not tombstone.exists()


@pytest.mark.parametrize("active_state", ["prepared", "repository_pending"])
def test_restart_interval_zero_sync_protects_target_and_updates_unrelated_page(app, active_state):
    with app.app_context():
        campaign, target = _create_page(app, f"notes/delete-protected-{active_state}")
        _, unrelated = _create_page(app, f"notes/delete-unrelated-{active_state}")
        reconciler = app.extensions["player_wiki_reconciler"]
        crash_event = (
            "after_tombstone_move"
            if active_state == "prepared"
            else "before_delete_repository_refresh"
        )
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError(active_state))
                if event == crash_event
                else None
            )
        )
        with pytest.raises(RuntimeError, match=active_state):
            reconciler.delete(campaign, target, operation_kind="api_delete")
        assert _deletion_row()["state"] == active_state

        if active_state == "repository_pending":
            target.file_path.write_text(
                "---\ntitle: Reappeared target\nsection: Notes\ntype: note\npublished: true\n---\n\nMust stay protected\n",
                encoding="utf-8",
            )

        unrelated.file_path.write_text(
            "---\ntitle: Reloaded unrelated\nsection: Notes\ntype: note\npublished: true\n---\n\nReloaded body\n",
            encoding="utf-8",
        )
        restarted = CampaignPageStore(reload_enabled=True, scan_interval_seconds=0)
        restarted.sync_campaign_pages(campaign.slug, Path(campaign.player_content_dir))
        protected = restarted.get_page_record(campaign.slug, target.page_ref, include_body=True)
        unrelated_row = restarted.get_page_record(campaign.slug, unrelated.page_ref, include_body=True)
        if active_state == "prepared":
            assert protected is not None
        else:
            assert protected is None
        assert unrelated_row is not None
        assert unrelated_row.page.title == "Reloaded unrelated"


def test_active_delete_and_upsert_journals_exclude_each_other(app):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-cross-journal")
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("delete prepared"))
                if event == "after_delete_prepare"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="delete prepared"):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        prepared = prepare_campaign_page_write(
            campaign,
            record.page_ref,
            metadata={**record.metadata, "title": "Blocked update"},
            body_markdown=record.body_markdown,
            page_store=app.extensions["campaign_page_store"],
        )
        reconciler.hooks = ReconciliationHooks()
        with pytest.raises(PlayerWikiReconciliationConflict, match="pending deletion"):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")

        get_db().execute("DELETE FROM player_wiki_deletion_operations")
        get_db().commit()
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("upsert prepared"))
                if event == "after_prepare"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="upsert prepared"):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
        reconciler.hooks = ReconciliationHooks()
        with pytest.raises(PlayerWikiReconciliationConflict, match="pending publication"):
            reconciler.delete(campaign, record, operation_kind="api_delete")


def test_delete_move_destination_race_preserves_both_authorities_and_redacts_paths(
    app,
    monkeypatch,
):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-move-race")
        original = record.file_path.read_bytes()
        original_move = file_publication._rename_no_replace
        observed_destination = None

        def race(source_path, destination_path):
            nonlocal observed_destination
            observed_destination = destination_path
            destination_path.write_bytes(b"unrelated raced bytes")
            return original_move(source_path, destination_path)

        monkeypatch.setattr(file_publication, "_rename_no_replace", race)
        with pytest.raises(FileExistsError) as caught:
            app.extensions["player_wiki_reconciler"].delete(
                campaign,
                record,
                operation_kind="api_delete",
            )
        assert observed_destination is not None
        assert record.file_path.read_bytes() == original
        assert observed_destination.read_bytes() == b"unrelated raced bytes"
        assert record.file_path.name not in str(caught.value)
        assert observed_destination.name not in str(caught.value)
        row = _deletion_row()
        assert row["state"] == "conflict"
        assert row["error_code"] == "delete_move_state_conflict"


def test_delete_rejects_symlink_source_and_never_removes_link_target(app, tmp_path):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-symlink")
        outside = tmp_path / "outside.md"
        outside.write_bytes(b"outside authority")
        record.file_path.unlink()
        try:
            os.symlink(outside, record.file_path)
        except OSError:
            pytest.skip("This platform does not permit an unprivileged file symlink.")
        with pytest.raises(Exception, match="regular Markdown"):
            app.extensions["player_wiki_reconciler"].delete(
                campaign,
                record,
                operation_kind="api_delete",
            )
        assert record.file_path.is_symlink()
        assert outside.read_bytes() == b"outside authority"
        assert _deletion_row() is None


def test_delete_rejects_windows_reparse_source_before_journal_effects(app, monkeypatch):
    with app.app_context():
        campaign, record = _create_page(app, "notes/delete-reparse")
        original_lstat = Path.lstat

        class ReparseStat:
            def __init__(self, wrapped):
                self._wrapped = wrapped
                self.st_file_attributes = int(
                    getattr(wrapped, "st_file_attributes", 0)
                ) | 0x400

            def __getattr__(self, name):
                return getattr(self._wrapped, name)

        def reparse_lstat(path):
            observed = original_lstat(path)
            if Path(path).absolute() == record.file_path.absolute():
                return ReparseStat(observed)
            return observed

        monkeypatch.setattr(Path, "lstat", reparse_lstat)
        with pytest.raises(Exception, match="regular Markdown"):
            app.extensions["player_wiki_reconciler"].delete(
                campaign,
                record,
                operation_kind="api_delete",
            )
        assert record.file_path.exists()
        assert _deletion_row() is None


def test_api_delete_retains_referenced_asset_and_writes_no_browser_audit(app):
    with app.app_context():
        campaign = _campaign(app)
        asset_refs = (
            "wiki-pages/delete-retained.webp",
            "wiki-pages/body-retained.webp",
            "session-articles/session-retained.webp",
            "direct-api/direct-retained.webp",
        )
        asset_paths = [Path(campaign.assets_dir) / ref for ref in asset_refs]
        for index, asset_path in enumerate(asset_paths):
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(f"retained image {index}".encode())
        _, record = _create_page(
            app,
            "notes/delete-retained-asset",
            image=asset_refs[0],
            body=(
                f"![Body](/campaigns/linden-pass/assets/{asset_refs[1]})\n\n"
                f"![Session](/campaigns/linden-pass/assets/{asset_refs[2]})\n\n"
                f"![Direct](/campaigns/linden-pass/assets/{asset_refs[3]})"
            ),
        )
        app.extensions["player_wiki_reconciler"].delete(
            campaign,
            record,
            operation_kind="api_delete",
        )
        for index, asset_path in enumerate(asset_paths):
            assert asset_path.read_bytes() == f"retained image {index}".encode()
        assert _audit_count() == 0


@pytest.mark.parametrize("active_state", ["prepared", "repository_pending"])
def test_active_deletion_survives_backup_restore_and_recovers(app, tmp_path, active_state):
    with app.app_context():
        campaign, record = _create_page(app, f"notes/delete-restored-{active_state}")
        reconciler = app.extensions["player_wiki_reconciler"]
        crash_event = (
            "after_tombstone_move"
            if active_state == "prepared"
            else "before_delete_repository_refresh"
        )
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("archive deletion"))
                if event == crash_event
                else None
            )
        )
        with pytest.raises(RuntimeError, match="archive deletion"):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        assert _deletion_row()["state"] == active_state
        archive = create_backup_archive_v2(
            db_path=Path(app.config["DB_PATH"]),
            campaigns_dir=Path(app.config["TEST_CAMPAIGNS_DIR"]),
            backup_root=tmp_path / "archives",
            archive_basename=f"active-delete-{active_state}",
            created_at="2026-07-18T12:00:00Z",
        )

    restored_database = tmp_path / "restored" / "wiki.sqlite3"
    restored_campaigns = tmp_path / "restored" / "campaigns"
    restored = restore_backup_archive(
        archive_path=archive.archive_path,
        db_path=restored_database,
        campaigns_dir=restored_campaigns,
    )
    assert restored.migration_required is False

    with app.app_context():
        original_database = app.config["DB_PATH"]
        try:
            close_db()
            app.config["DB_PATH"] = restored_database
            page_store = CampaignPageStore(reload_enabled=False, scan_interval_seconds=0)
            repository_store = RepositoryStore(
                restored_campaigns,
                page_store=page_store,
                reload_enabled=False,
                scan_interval_seconds=0,
            )
            restored_reconciler = PlayerWikiReconciler(
                page_store=page_store,
                repository_store=repository_store,
                auth_store=AuthStore(),
            )
            assert _deletion_row()["state"] == active_state
            assert restored_reconciler.recover_pending()["recovered"] == 1
            assert _deletion_row() is None
            assert page_store.get_page_record(
                "linden-pass", f"notes/delete-restored-{active_state}"
            ) is None
        finally:
            close_db()
            app.config["DB_PATH"] = original_database
