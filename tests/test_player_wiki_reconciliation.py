from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from player_wiki.campaign_content_service import prepare_campaign_page_write
from player_wiki.auth_store import AuthStore
from player_wiki.backup_archive import create_backup_archive_v2
from player_wiki.campaign_page_store import CampaignPageStore
from player_wiki.db import close_db, get_db
from player_wiki.operations import restore_backup_archive
from player_wiki.player_wiki_reconciliation import (
    PreparedManagedImage,
    PlayerWikiCreateConflict,
    PlayerWikiReconciler,
    PlayerWikiReconciliationConflict,
    ReconciliationHooks,
)
from player_wiki.repository_store import RepositoryStore


def _campaign(app):
    campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
    assert campaign is not None
    return campaign


def _page_path(app, page_ref: str) -> Path:
    return (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "content"
        / f"{page_ref}.md"
    )


def _prepared_page(app, page_ref: str, *, title: str = "Reconciled Page", body: str = "Safe body"):
    campaign = _campaign(app)
    return campaign, prepare_campaign_page_write(
        campaign,
        page_ref,
        metadata={
            "slug": page_ref,
            "title": title,
            "section": "Notes",
            "type": "note",
            "published": True,
        },
        body_markdown=body,
        page_store=app.extensions["campaign_page_store"],
    )


def _journal_row():
    return get_db().execute(
        "SELECT * FROM player_wiki_reconciliation_operations"
    ).fetchone()


def test_create_rechecks_late_database_destination_inside_preparation(app, users):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/late-database-create")
        page_store = app.extensions["campaign_page_store"]
        existing = page_store.upsert_page(
            campaign.slug,
            prepared.page_ref,
            metadata={
                "slug": prepared.page_ref,
                "title": "Existing Database Authority",
                "section": "Notes",
                "type": "note",
                "source_ref": "existing:database",
                "published": True,
            },
            body_markdown="Existing database body.",
        )

        with pytest.raises(PlayerWikiCreateConflict, match="destination is already in use"):
            app.extensions["player_wiki_reconciler"].mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )

        stored = page_store.get_page_record(campaign.slug, prepared.page_ref, include_body=True)
        assert stored is not None
        assert stored.page.source_ref == "existing:database"
        assert stored.body_markdown == "Existing database body."
        assert stored.updated_at == existing.updated_at
        assert not prepared.file_path.exists()
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 0


def test_create_rechecks_late_markdown_destination_inside_preparation(app, users):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/late-markdown-create")
        prepared.file_path.parent.mkdir(parents=True, exist_ok=True)
        existing_bytes = b"third-party Markdown authority\n"
        prepared.file_path.write_bytes(existing_bytes)

        with pytest.raises(PlayerWikiCreateConflict, match="destination is already in use"):
            app.extensions["player_wiki_reconciler"].mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )

        assert prepared.file_path.read_bytes() == existing_bytes
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            prepared.page_ref,
        ) is None
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 0


def test_create_rechecks_active_publication_destination_inside_preparation(app):
    with app.app_context():
        campaign, first = _prepared_page(app, "notes/active-create-destination")
        reconciler = app.extensions["player_wiki_reconciler"]

        def interrupt(event, _operation_id):
            if event == "before_primary_publish":
                raise RuntimeError("leave active create")

        reconciler.hooks = ReconciliationHooks(on_event=interrupt)
        with pytest.raises(RuntimeError, match="leave active create"):
            reconciler.mutate(campaign, first, operation_kind="create")
        original_operation_id = _journal_row()["operation_id"]
        reconciler.hooks = ReconciliationHooks()
        second = prepare_campaign_page_write(
            campaign,
            first.page_ref,
            metadata={
                "slug": first.page_ref,
                "title": "Second Create",
                "section": "Notes",
                "type": "note",
                "published": True,
            },
            body_markdown="Second create must not publish.",
            page_store=app.extensions["campaign_page_store"],
        )

        with pytest.raises(PlayerWikiCreateConflict, match="destination is already in use"):
            reconciler.mutate(campaign, second, operation_kind="create")

        row = _journal_row()
        assert row["operation_id"] == original_operation_id
        assert row["state"] == "prepared"
        assert not first.file_path.exists()
        assert app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            first.page_ref,
        ) is None


@pytest.mark.parametrize("operation_kind", ("update", "api_upsert"))
def test_noncreate_operations_still_accept_existing_destination(app, operation_kind):
    with app.app_context():
        campaign, initial = _prepared_page(
            app,
            f"notes/{operation_kind}-existing",
            title="Existing Page",
            body="Existing body.",
        )
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.mutate(campaign, initial, operation_kind="create")
        updated = prepare_campaign_page_write(
            campaign,
            initial.page_ref,
            metadata={
                "slug": initial.page_ref,
                "title": "Updated Page",
                "section": "Notes",
                "type": "note",
                "published": True,
            },
            body_markdown="Updated body.",
            page_store=app.extensions["campaign_page_store"],
        )

        result = reconciler.mutate(campaign, updated, operation_kind=operation_kind)

        assert result.page.title == "Updated Page"
        assert result.body_markdown == "Updated body."
        assert updated.file_path.read_bytes() == updated.rendered_markdown
        assert _journal_row() is None


def test_precommit_crash_aborts_without_authority_or_audit(app, users):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/precommit-abort")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "before_primary_publish":
                raise RuntimeError("precommit crash")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="precommit crash"):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        assert not prepared.file_path.exists()
        assert _journal_row()["state"] == "prepared"

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["aborted"] == 1
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 0


def test_markdown_primary_crash_recovers_page_audit_refresh_and_deletes_journal(app, users):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/markdown-forward")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_primary_publish":
                raise RuntimeError("post-primary crash")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="post-primary crash"):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        row = _journal_row()
        assert row["primary_authority"] == "markdown"
        assert row["state"] == "prepared"
        assert bytes(row["desired_markdown"]) == prepared.rendered_markdown
        assert prepared.file_path.read_bytes() == prepared.rendered_markdown

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["recovered"] == 1
        assert _journal_row() is None
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            prepared.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Reconciled Page"
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


def test_third_digest_becomes_payload_retaining_conflict_and_blocks_same_page(app):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/digest-conflict")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_prepare":
                raise RuntimeError("prepared crash")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="prepared crash"):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
        prepared.file_path.parent.mkdir(parents=True, exist_ok=True)
        prepared.file_path.write_bytes(b"third-party bytes")

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["conflict"] == 1
        row = _journal_row()
        assert row["state"] == "conflict"
        assert row["error_code"] == "primary_digest_conflict"
        assert bytes(row["desired_markdown"]) == prepared.rendered_markdown

        _, second = _prepared_page(app, prepared.page_ref, title="Blocked replacement")
        with pytest.raises(PlayerWikiReconciliationConflict, match="pending reconciliation"):
            reconciler.mutate(campaign, second, operation_kind="api_upsert")


@pytest.mark.parametrize("failure_event", ["after_repository_pending", "before_journal_cleanup"])
def test_repository_pending_retries_refresh_and_cleanup_without_duplicate_audit(
    app,
    users,
    failure_event,
):
    with app.app_context():
        campaign, prepared = _prepared_page(app, f"notes/{failure_event}")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == failure_event:
                raise RuntimeError(failure_event)

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match=failure_event):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        row = _journal_row()
        assert row["state"] == "repository_pending"
        assert row["desired_markdown"] is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["recovered"] == 1
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize("changed_authority", ["markdown", "image"])
def test_repository_pending_third_authority_stays_retryable_without_refresh_or_duplicate_audit(
    app,
    users,
    changed_authority,
):
    with app.app_context():
        campaign, prepared = _prepared_page(
            app,
            f"notes/repository-pending-third-{changed_authority}",
            title="Desired title",
            body="Desired body",
        )
        prepared_image = None
        asset_path = None
        desired_image = b"desired managed image"
        if changed_authority == "image":
            asset_ref = f"wiki-pages/{prepared.page_ref}.webp"
            asset_path = Path(campaign.assets_dir) / Path(*asset_ref.split("/"))
            prepared = prepare_campaign_page_write(
                campaign,
                prepared.page_ref,
                metadata={
                    **prepared.metadata,
                    "image": asset_ref,
                },
                body_markdown=prepared.body_markdown,
                page_store=app.extensions["campaign_page_store"],
            )
            prepared_image = PreparedManagedImage(
                asset_ref=asset_ref,
                file_path=asset_path,
                data_blob=desired_image,
            )

        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_repository_pending":
                raise RuntimeError("freeze repository pending")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="freeze repository pending"):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="create",
                prepared_image=prepared_image,
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        operation_id = str(_journal_row()["operation_id"])

        if changed_authority == "markdown":
            _, third = _prepared_page(
                app,
                prepared.page_ref,
                title="Third title",
                body="Third body",
            )
            prepared.file_path.write_bytes(third.rendered_markdown)
        else:
            assert asset_path is not None
            asset_path.write_bytes(b"third managed image")

        reconciler.hooks = ReconciliationHooks()
        outcome = reconciler.recover_pending()
        assert outcome == {"recovered": 0, "aborted": 0, "conflict": 0, "pending": 1}
        row = _journal_row()
        assert row["operation_id"] == operation_id
        assert row["state"] == "repository_pending"
        assert row["desired_markdown"] is None
        assert row["error_code"] == f"{changed_authority}_authority_changed"
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            prepared.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Desired title"
        assert stored.body_markdown == "Desired body"
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1

        if changed_authority == "markdown":
            prepared.file_path.write_bytes(prepared.rendered_markdown)
        else:
            assert asset_path is not None
            asset_path.write_bytes(desired_image)

        assert reconciler.recover_pending() == {
            "recovered": 1,
            "aborted": 0,
            "conflict": 0,
            "pending": 0,
        }
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize(
    "fault_event",
    ["before_repository_refresh", "after_repository_refresh", "before_journal_cleanup"],
)
@pytest.mark.parametrize("changed_authority", ["markdown", "image"])
def test_repository_pending_hook_authority_change_never_replaces_desired_read_model(
    app,
    users,
    fault_event,
    changed_authority,
):
    with app.app_context():
        campaign, prepared = _prepared_page(
            app,
            f"notes/{fault_event}-{changed_authority}",
            title="Desired hook title",
            body="Desired hook body",
        )
        prepared_image = None
        asset_path = None
        desired_image = b"desired hook image"
        if changed_authority == "image":
            asset_ref = f"wiki-pages/{prepared.page_ref}.webp"
            asset_path = Path(campaign.assets_dir) / Path(*asset_ref.split("/"))
            prepared = prepare_campaign_page_write(
                campaign,
                prepared.page_ref,
                metadata={**prepared.metadata, "image": asset_ref},
                body_markdown=prepared.body_markdown,
                page_store=app.extensions["campaign_page_store"],
            )
            prepared_image = PreparedManagedImage(
                asset_ref=asset_ref,
                file_path=asset_path,
                data_blob=desired_image,
            )

        reconciler = app.extensions["player_wiki_reconciler"]
        _, unrelated = _prepared_page(
            app,
            f"notes/unrelated-{fault_event}-{changed_authority}",
            title="Unrelated original",
            body="Unrelated original body",
        )
        reconciler.mutate(campaign, unrelated, operation_kind="api_upsert")

        def freeze_repository_pending(event, _operation_id):
            if event == "after_repository_pending":
                raise RuntimeError("freeze repository pending")

        reconciler.hooks = ReconciliationHooks(on_event=freeze_repository_pending)
        with pytest.raises(RuntimeError, match="freeze repository pending"):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="create",
                prepared_image=prepared_image,
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )

        _, third = _prepared_page(
            app,
            prepared.page_ref,
            title="Third hook title",
            body="Third hook body",
        )

        def replace_authority(event, _operation_id):
            if event != fault_event:
                return
            if changed_authority == "markdown":
                prepared.file_path.write_bytes(third.rendered_markdown)
            else:
                assert asset_path is not None
                asset_path.write_bytes(b"third hook image")

        reconciler.hooks = ReconciliationHooks(on_event=replace_authority)
        assert reconciler.recover_pending() == {
            "recovered": 0,
            "aborted": 0,
            "conflict": 0,
            "pending": 1,
        }
        row = _journal_row()
        assert row["state"] == "repository_pending"
        assert row["desired_markdown"] is None
        assert row["error_code"] == f"{changed_authority}_authority_changed"
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            prepared.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Desired hook title"
        assert stored.body_markdown == "Desired hook body"
        _, unrelated_reload = _prepared_page(
            app,
            unrelated.page_ref,
            title="Unrelated reloaded",
            body="Unrelated reloaded body",
        )
        unrelated.file_path.write_bytes(unrelated_reload.rendered_markdown)
        configured_store = app.extensions["repository_store"]
        fresh_store = RepositoryStore(
            configured_store.campaigns_dir,
            page_store=app.extensions["campaign_page_store"],
            reload_enabled=True,
            scan_interval_seconds=0,
        )
        in_memory_campaign = fresh_store.get().get_campaign(campaign.slug)
        assert in_memory_campaign is not None
        in_memory_page = in_memory_campaign.pages[prepared.route_slug]
        assert in_memory_page.title == "Desired hook title"
        assert in_memory_campaign.pages[unrelated.route_slug].title == "Unrelated reloaded"
        unrelated_stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            unrelated.page_ref,
            include_body=True,
        )
        assert unrelated_stored is not None
        assert unrelated_stored.page.title == "Unrelated reloaded"
        assert unrelated_stored.body_markdown == "Unrelated reloaded body"
        row = _journal_row()
        assert row["state"] == "repository_pending"
        assert row["error_code"] == f"{changed_authority}_authority_changed"
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1

        reconciler.hooks = ReconciliationHooks()
        if changed_authority == "markdown":
            prepared.file_path.write_bytes(prepared.rendered_markdown)
        else:
            assert asset_path is not None
            asset_path.write_bytes(desired_image)
        assert reconciler.recover_pending() == {
            "recovered": 1,
            "aborted": 0,
            "conflict": 0,
            "pending": 0,
        }
        assert _journal_row() is None
        _, resumed = _prepared_page(
            app,
            prepared.page_ref,
            title="Normal sync resumed",
            body="Normal sync resumed body",
        )
        prepared.file_path.write_bytes(resumed.rendered_markdown)
        resumed_campaign = fresh_store.get().get_campaign(campaign.slug)
        assert resumed_campaign is not None
        assert resumed_campaign.pages[prepared.route_slug].title == "Normal sync resumed"
        resumed_stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            prepared.page_ref,
            include_body=True,
        )
        assert resumed_stored is not None
        assert resumed_stored.page.title == "Normal sync resumed"
        assert resumed_stored.body_markdown == "Normal sync resumed body"
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


def test_database_authoritative_refresh_skips_seeding_and_default_refresh_still_seeds(app):
    with app.app_context():
        campaign, desired = _prepared_page(
            app,
            "notes/database-authoritative-refresh",
            title="Database title",
            body="Database body",
        )
        app.extensions["player_wiki_reconciler"].mutate(
            campaign,
            desired,
            operation_kind="api_upsert",
        )
        _, third = _prepared_page(
            app,
            desired.page_ref,
            title="Filesystem title",
            body="Filesystem body",
        )
        desired.file_path.write_bytes(third.rendered_markdown)

        repository_store = app.extensions["repository_store"]
        database_repository = repository_store.refresh_from_database()
        database_campaign = database_repository.get_campaign(campaign.slug)
        assert database_campaign is not None
        database_page = database_campaign.pages[desired.route_slug]
        assert database_page.title == "Database title"
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            desired.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Database title"

        default_repository = repository_store.refresh()
        default_campaign = default_repository.get_campaign(campaign.slug)
        assert default_campaign is not None
        default_page = default_campaign.pages[desired.route_slug]
        assert default_page.title == "Filesystem title"
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            desired.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Filesystem title"


def test_prepared_and_conflict_journals_protect_page_upsert_and_absence_deletion(app):
    with app.app_context():
        campaign, original = _prepared_page(
            app,
            "notes/active-journal-protection",
            title="Stored authority",
            body="Stored authority body",
        )
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.mutate(campaign, original, operation_kind="api_upsert")
        _, updated = _prepared_page(
            app,
            original.page_ref,
            title="Pending authority",
            body="Pending authority body",
        )

        def freeze_prepared(event, _operation_id):
            if event == "after_prepare":
                raise RuntimeError("freeze prepared")

        reconciler.hooks = ReconciliationHooks(on_event=freeze_prepared)
        with pytest.raises(RuntimeError, match="freeze prepared"):
            reconciler.mutate(campaign, updated, operation_kind="api_upsert")
        assert _journal_row()["state"] == "prepared"
        original.file_path.unlink()

        configured_store = app.extensions["repository_store"]
        prepared_store = RepositoryStore(
            configured_store.campaigns_dir,
            page_store=app.extensions["campaign_page_store"],
            reload_enabled=True,
            scan_interval_seconds=0,
        )
        prepared_campaign = prepared_store.get().get_campaign(campaign.slug)
        assert prepared_campaign is not None
        assert prepared_campaign.pages[original.route_slug].title == "Stored authority"
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            original.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Stored authority"

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["conflict"] == 1
        row = _journal_row()
        assert row["state"] == "conflict"
        assert bytes(row["desired_markdown"]) == updated.rendered_markdown
        _, third = _prepared_page(
            app,
            original.page_ref,
            title="Conflict filesystem",
            body="Conflict filesystem body",
        )
        original.file_path.write_bytes(third.rendered_markdown)

        conflict_store = RepositoryStore(
            configured_store.campaigns_dir,
            page_store=app.extensions["campaign_page_store"],
            reload_enabled=True,
            scan_interval_seconds=0,
        )
        conflict_campaign = conflict_store.get().get_campaign(campaign.slug)
        assert conflict_campaign is not None
        assert conflict_campaign.pages[original.route_slug].title == "Stored authority"
        original.file_path.unlink()
        conflict_campaign = conflict_store.get().get_campaign(campaign.slug)
        assert conflict_campaign is not None
        assert conflict_campaign.pages[original.route_slug].title == "Stored authority"
        stored = app.extensions["campaign_page_store"].get_page_record(
            campaign.slug,
            original.page_ref,
            include_body=True,
        )
        assert stored is not None
        assert stored.page.title == "Stored authority"


def test_api_operation_has_no_browser_audit_metadata(app):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/api-no-audit")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_prepare":
                raise RuntimeError("inspect api journal")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="inspect api journal"):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
        row = _journal_row()
        assert row["operation_kind"] == "api_upsert"
        assert row["audit_event_type"] is None
        assert row["audit_actor_user_id"] is None
        assert row["audit_metadata_json"] is None


def test_two_stale_finalizers_produce_one_page_and_one_audit(app, users):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/stale-finalizer")
        initial = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_primary_publish":
                raise RuntimeError("freeze prepared operation")

        initial.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="freeze prepared operation"):
            initial.mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        operation_id = str(_journal_row()["operation_id"])

    barrier = Barrier(2)

    def finalize(_worker: int):
        with app.app_context():
            reconciler = PlayerWikiReconciler(
                page_store=app.extensions["campaign_page_store"],
                repository_store=app.extensions["repository_store"],
                auth_store=app.extensions["auth_store"],
                hooks=ReconciliationHooks(
                    on_event=lambda event, _operation_id: (
                        barrier.wait(timeout=10)
                        if event == "before_sqlite_finalize"
                        else None
                    )
                ),
            )
            return reconciler._continue_prepared(_campaign(app), operation_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(finalize, range(2)))

    assert any(result is not None for result in results)
    with app.app_context():
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM campaign_pages WHERE campaign_slug = ? AND page_ref = ?",
            ("linden-pass", "notes/stale-finalizer"),
        ).fetchone()[0] == 1
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


def test_stale_conflict_marker_returns_repository_pending_without_overwriting_it(
    app,
    users,
):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/stale-conflict-marker")
        initial = app.extensions["player_wiki_reconciler"]

        def freeze_prepared(event, _operation_id):
            if event == "after_primary_publish":
                raise RuntimeError("freeze prepared")

        initial.hooks = ReconciliationHooks(on_event=freeze_prepared)
        with pytest.raises(RuntimeError, match="freeze prepared"):
            initial.mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        operation_id = str(_journal_row()["operation_id"])

    barrier = Barrier(2)

    def finalize():
        with app.app_context():
            def pause_after_repository_pending(event, _operation_id):
                if event == "after_repository_pending":
                    barrier.wait(timeout=10)
                    raise RuntimeError("finalizer paused after repository pending")

            reconciler = PlayerWikiReconciler(
                page_store=app.extensions["campaign_page_store"],
                repository_store=app.extensions["repository_store"],
                auth_store=app.extensions["auth_store"],
                hooks=ReconciliationHooks(on_event=pause_after_repository_pending),
            )
            try:
                reconciler._continue_prepared(campaign, operation_id)
            except Exception as exc:
                return f"{exc}: {type(exc).__name__}"
            return "unexpected finalizer completion"

    def mark_conflict():
        with app.app_context():
            barrier.wait(timeout=10)
            reconciler = PlayerWikiReconciler(
                page_store=app.extensions["campaign_page_store"],
                repository_store=app.extensions["repository_store"],
                auth_store=app.extensions["auth_store"],
            )
            current = reconciler._mark_conflict(operation_id, "stale_digest_conflict")
            return current.state if current is not None else "disappeared"

    with ThreadPoolExecutor(max_workers=2) as executor:
        finalizer_result = executor.submit(finalize)
        marker_result = executor.submit(mark_conflict)
        assert marker_result.result(timeout=15) == "repository_pending"
        assert finalizer_result.result(timeout=15) == (
            "finalizer paused after repository pending: RuntimeError"
        )

    with app.app_context():
        row = _journal_row()
        assert row["state"] == "repository_pending"
        assert row["error_code"] == ""
        assert app.extensions["player_wiki_reconciler"].recover_pending()["recovered"] == 1
        assert _journal_row() is None
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize(
    ("crash_event", "expected_state", "expected_counter", "payload_retained"),
    [
        ("after_prepare", "conflict", "conflict", True),
        ("after_repository_pending", "repository_pending", "pending", False),
    ],
)
def test_missing_campaign_recovery_counts_match_retryable_state(
    app,
    users,
    monkeypatch,
    crash_event,
    expected_state,
    expected_counter,
    payload_retained,
):
    with app.app_context():
        campaign, prepared = _prepared_page(app, f"notes/missing-{expected_counter}")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == crash_event:
                raise RuntimeError(crash_event)

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match=crash_event):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="create",
                audit_event_type="campaign_wiki_page_created",
                audit_actor_user_id=users["dm"]["id"],
                audit_metadata={"page_ref": prepared.page_ref},
            )
        reconciler.hooks = ReconciliationHooks()
        monkeypatch.setattr(reconciler, "_load_campaign_for_recovery", lambda _slug: None)
        outcome = reconciler.recover_pending()
        assert outcome[expected_counter] == 1
        assert sum(outcome.values()) == 1
        row = _journal_row()
        assert row["state"] == expected_state
        assert (row["desired_markdown"] is not None) is payload_retained


def test_competing_prepare_transactions_leave_one_active_operation(app):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/competing-prepare")
    start = Barrier(2)

    def prepare(_worker: int) -> str:
        with app.app_context():
            reconciler = PlayerWikiReconciler(
                page_store=app.extensions["campaign_page_store"],
                repository_store=app.extensions["repository_store"],
                auth_store=app.extensions["auth_store"],
                hooks=ReconciliationHooks(
                    on_event=lambda event, _operation_id: (
                        (_ for _ in ()).throw(RuntimeError("prepared winner"))
                        if event == "after_prepare"
                        else None
                    )
                ),
            )
            start.wait(timeout=10)
            try:
                reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
            except RuntimeError:
                return "winner"
            except PlayerWikiReconciliationConflict:
                return "blocked"
            return "unexpected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(prepare, range(2)))
    assert outcomes == ["blocked", "winner"]
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations WHERE state = 'prepared'"
        ).fetchone()[0] == 1
        assert not _page_path(app, "notes/competing-prepare").exists()


def test_cold_recovery_does_not_sync_page_row_before_atomic_finalization(
    app,
    monkeypatch,
):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/cold-recovery")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_primary_publish":
                raise RuntimeError("simulate process loss")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="simulate process loss"):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
        assert get_db().execute(
            "SELECT COUNT(*) FROM campaign_pages WHERE campaign_slug = ? AND page_ref = ?",
            (campaign.slug, prepared.page_ref),
        ).fetchone()[0] == 0

        page_store = app.extensions["campaign_page_store"]
        original_sync = page_store.sync_campaign_pages
        observed_states: list[str] = []

        def guarded_sync(campaign_slug, content_dir):
            state_row = _journal_row()
            observed_states.append(str(state_row["state"]) if state_row is not None else "deleted")
            assert state_row is not None
            assert state_row["state"] == "repository_pending"
            return original_sync(campaign_slug, content_dir)

        monkeypatch.setattr(page_store, "sync_campaign_pages", guarded_sync)
        configured_store = app.extensions["repository_store"]
        cold_repository_store = RepositoryStore(
            configured_store.campaigns_dir,
            page_store=page_store,
            reload_enabled=configured_store.reload_enabled,
            scan_interval_seconds=configured_store.scan_interval_seconds,
        )
        cold_reconciler = PlayerWikiReconciler(
            page_store=page_store,
            repository_store=cold_repository_store,
            auth_store=app.extensions["auth_store"],
        )
        assert cold_reconciler.recover_pending()["recovered"] == 1
        assert observed_states == []
        assert _journal_row() is None


def test_identical_managed_image_makes_markdown_the_primary_authority(app):
    with app.app_context():
        campaign = _campaign(app)
        asset_ref = "wiki-pages/notes/identical.webp"
        asset_path = Path(campaign.assets_dir) / Path(*asset_ref.split("/"))
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"same managed image")
        prepared = prepare_campaign_page_write(
            campaign,
            "notes/identical",
            metadata={
                "slug": "notes/identical",
                "title": "Identical Image",
                "section": "Notes",
                "type": "note",
                "published": True,
                "image": asset_ref,
            },
            body_markdown="Markdown is the changed authority.",
            page_store=app.extensions["campaign_page_store"],
        )
        reconciler = app.extensions["player_wiki_reconciler"]

        def inspect(event, _operation_id):
            if event == "after_prepare":
                assert _journal_row()["primary_authority"] == "markdown"
                raise RuntimeError("primary inspected")

        reconciler.hooks = ReconciliationHooks(on_event=inspect)
        with pytest.raises(RuntimeError, match="primary inspected"):
            reconciler.mutate(
                campaign,
                prepared,
                operation_kind="update",
                prepared_image=PreparedManagedImage(
                    asset_ref=asset_ref,
                    file_path=asset_path,
                    data_blob=b"same managed image",
                ),
            )
        assert asset_path.read_bytes() == b"same managed image"


@pytest.mark.parametrize("crash_event", ["before_markdown_publish", "after_markdown_publish"])
def test_image_primary_markdown_forward_crash_recovers_exact_page(app, crash_event):
    with app.app_context():
        campaign, original = _prepared_page(
            app,
            f"notes/image-{crash_event}",
            title="Original",
            body="Original body",
        )
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.mutate(campaign, original, operation_kind="api_upsert")

        asset_ref = f"wiki-pages/notes/image-{crash_event}.webp"
        asset_path = Path(campaign.assets_dir) / Path(*asset_ref.split("/"))
        updated = prepare_campaign_page_write(
            campaign,
            original.page_ref,
            metadata={
                "slug": original.page_ref,
                "title": "Recovered Image Update",
                "section": "Notes",
                "type": "note",
                "published": True,
                "image": asset_ref,
            },
            body_markdown="Recovered exact body",
            page_store=app.extensions["campaign_page_store"],
        )

        def crash(event, _operation_id):
            if event == crash_event:
                raise RuntimeError(crash_event)

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match=crash_event):
            reconciler.mutate(
                campaign,
                updated,
                operation_kind="update",
                prepared_image=PreparedManagedImage(
                    asset_ref=asset_ref,
                    file_path=asset_path,
                    data_blob=b"changed managed image",
                ),
            )
        row = _journal_row()
        assert row["primary_authority"] == "image"
        assert row["state"] == "prepared"
        assert asset_path.read_bytes() == b"changed managed image"

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["recovered"] == 1
        assert _journal_row() is None
        assert updated.file_path.read_bytes() == updated.rendered_markdown


@pytest.mark.parametrize(
    ("changed_authority", "expected_error"),
    [
        ("image", "primary_digest_conflict"),
        ("markdown", "markdown_digest_conflict"),
    ],
)
def test_image_primary_third_digest_retains_payload_conflict(
    app,
    changed_authority,
    expected_error,
):
    with app.app_context():
        campaign, original = _prepared_page(
            app,
            f"notes/image-third-{changed_authority}",
            title="Original",
        )
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.mutate(campaign, original, operation_kind="api_upsert")
        asset_ref = f"wiki-pages/notes/image-third-{changed_authority}.webp"
        asset_path = Path(campaign.assets_dir) / Path(*asset_ref.split("/"))
        updated = prepare_campaign_page_write(
            campaign,
            original.page_ref,
            metadata={
                "slug": original.page_ref,
                "title": "Desired Update",
                "section": "Notes",
                "type": "note",
                "published": True,
                "image": asset_ref,
            },
            body_markdown="Desired body",
            page_store=app.extensions["campaign_page_store"],
        )

        def crash(event, _operation_id):
            if event == "after_primary_publish":
                raise RuntimeError("image committed")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="image committed"):
            reconciler.mutate(
                campaign,
                updated,
                operation_kind="update",
                prepared_image=PreparedManagedImage(
                    asset_ref=asset_ref,
                    file_path=asset_path,
                    data_blob=b"desired image",
                ),
            )
        if changed_authority == "image":
            asset_path.write_bytes(b"third image")
        else:
            updated.file_path.write_bytes(b"third markdown")

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["conflict"] == 1
        row = _journal_row()
        assert row["state"] == "conflict"
        assert row["error_code"] == expected_error
        assert bytes(row["desired_markdown"]) == updated.rendered_markdown


@pytest.mark.parametrize("markdown_state", ["desired", "third"])
def test_image_previous_with_changed_markdown_conflicts_instead_of_abandoning(
    app,
    markdown_state,
):
    with app.app_context():
        campaign = _campaign(app)
        page_ref = f"notes/image-previous-markdown-{markdown_state}"
        asset_ref = f"wiki-pages/{page_ref}.webp"
        asset_path = Path(campaign.assets_dir) / Path(*asset_ref.split("/"))
        original = prepare_campaign_page_write(
            campaign,
            page_ref,
            metadata={
                "slug": page_ref,
                "title": "Previous",
                "section": "Notes",
                "type": "note",
                "published": True,
                "image": asset_ref,
            },
            body_markdown="Previous body",
            page_store=app.extensions["campaign_page_store"],
        )
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.mutate(
            campaign,
            original,
            operation_kind="api_upsert",
            prepared_image=PreparedManagedImage(
                asset_ref=asset_ref,
                file_path=asset_path,
                data_blob=b"previous image",
            ),
        )
        updated = prepare_campaign_page_write(
            campaign,
            page_ref,
            metadata={
                "slug": page_ref,
                "title": "Desired",
                "section": "Notes",
                "type": "note",
                "published": True,
                "image": asset_ref,
            },
            body_markdown="Desired body",
            page_store=app.extensions["campaign_page_store"],
        )

        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError("prepared only"))
                if event == "after_prepare"
                else None
            )
        )
        with pytest.raises(RuntimeError, match="prepared only"):
            reconciler.mutate(
                campaign,
                updated,
                operation_kind="update",
                prepared_image=PreparedManagedImage(
                    asset_ref=asset_ref,
                    file_path=asset_path,
                    data_blob=b"desired image",
                ),
            )
        assert asset_path.read_bytes() == b"previous image"
        updated.file_path.write_bytes(
            updated.rendered_markdown
            if markdown_state == "desired"
            else b"third markdown"
        )

        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["conflict"] == 1
        row = _journal_row()
        assert row["state"] == "conflict"
        assert row["error_code"] == "image_previous_markdown_changed"
        assert bytes(row["desired_markdown"]) == updated.rendered_markdown
        assert asset_path.read_bytes() == b"previous image"


def test_active_prepared_operation_survives_backup_restore_and_recovers(
    app,
    tmp_path,
):
    with app.app_context():
        campaign, prepared = _prepared_page(app, "notes/restored-recovery")
        reconciler = app.extensions["player_wiki_reconciler"]

        def crash(event, _operation_id):
            if event == "after_primary_publish":
                raise RuntimeError("archive prepared operation")

        reconciler.hooks = ReconciliationHooks(on_event=crash)
        with pytest.raises(RuntimeError, match="archive prepared operation"):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
        assert _journal_row()["state"] == "prepared"

        source_database = Path(app.config["DB_PATH"])
        source_campaigns = Path(app.config["TEST_CAMPAIGNS_DIR"])
        archive = create_backup_archive_v2(
            db_path=source_database,
            campaigns_dir=source_campaigns,
            backup_root=tmp_path / "archives",
            archive_basename="active-reconciliation",
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
            restored_page_store = CampaignPageStore(
                reload_enabled=False,
                scan_interval_seconds=0,
            )
            restored_repository_store = RepositoryStore(
                restored_campaigns,
                page_store=restored_page_store,
                reload_enabled=False,
                scan_interval_seconds=0,
            )
            restored_reconciler = PlayerWikiReconciler(
                page_store=restored_page_store,
                repository_store=restored_repository_store,
                auth_store=AuthStore(),
            )
            row = _journal_row()
            assert row["state"] == "prepared"
            assert bytes(row["desired_markdown"])
            assert restored_reconciler.recover_pending()["recovered"] == 1
            assert _journal_row() is None
            page = restored_page_store.get_page_record(
                "linden-pass",
                "notes/restored-recovery",
                include_body=True,
            )
            assert page is not None
            assert page.page.title == "Reconciled Page"
        finally:
            close_db()
            app.config["DB_PATH"] = original_database
