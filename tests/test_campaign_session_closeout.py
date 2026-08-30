from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import inspect
import sqlite3

import pytest

from player_wiki.app import create_app
from player_wiki.auth_store import AuthStore
from player_wiki.backup_archive import create_backup_archive_v2
from player_wiki.campaign_package_exporter import export_campaign_package
from player_wiki.campaign_session_service import (
    CampaignSessionCloseoutAuthorizationContext,
    CampaignSessionCloseoutAuthorizationError,
    CampaignSessionCloseoutConflictError,
    CampaignSessionCloseoutService,
    CampaignSessionCloseoutValidationError,
    CampaignSessionService,
    CampaignSessionValidationError,
)
from player_wiki.db import get_db
from player_wiki.migrations import CURRENT_SCHEMA_SQL, MIGRATIONS, run_migrations
from player_wiki.operations import restore_backup_archive
from player_wiki.session_models import (
    SESSION_CLOSEOUT_ITEM_KEYS,
    SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE,
    SESSION_CLOSEOUT_STATUS_COMPLETED,
    SESSION_CLOSEOUT_STATUS_OPEN,
)
from tests.sample_data import TEST_CAMPAIGN_SLUG


def _authorization(
    actor_user_id: int | None,
    *,
    campaign_slug: str = TEST_CAMPAIGN_SLUG,
    content: bool = True,
    session: bool = True,
    view_as: bool = False,
    read_only: bool = False,
) -> CampaignSessionCloseoutAuthorizationContext:
    return CampaignSessionCloseoutAuthorizationContext(
        campaign_slug=campaign_slug,
        actor_user_id=actor_user_id,
        can_manage_campaign_content=content,
        can_manage_session=session,
        is_view_as=view_as,
        is_read_only=read_only,
    )


def _service(
    app,
    actor_user_id: int | None,
    *,
    context: CampaignSessionCloseoutAuthorizationContext | None = None,
    pre_commit_hook=None,
) -> CampaignSessionCloseoutService:
    resolved = context or _authorization(actor_user_id)
    return CampaignSessionCloseoutService(
        app.extensions["campaign_session_store"],
        app.extensions["auth_store"],
        authorization_adapter=lambda _slug: resolved,
        pre_commit_hook=pre_commit_hook,
    )


def _closed_session(app, actor_user_id: int) -> int:
    session_service = app.extensions["campaign_session_service"]
    started = session_service.begin_session(
        TEST_CAMPAIGN_SLUG,
        started_by_user_id=actor_user_id,
    )
    closed = session_service.close_session(
        TEST_CAMPAIGN_SLUG,
        ended_by_user_id=actor_user_id,
    )
    assert closed.id == started.id
    return closed.id


def _audit_rows(event_type: str) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM auth_audit_log WHERE event_type = ? ORDER BY id",
        (event_type,),
    ).fetchall()


def test_closeout_composition_preserves_legacy_session_constructor(app):
    assert tuple(inspect.signature(CampaignSessionService).parameters) == ("store",)
    assert isinstance(
        app.extensions["campaign_session_closeout_service"],
        CampaignSessionCloseoutService,
    )


def test_v13_schema_has_campaign_confined_fks_indexes_and_database_guards(tmp_path):
    database = tmp_path / "schema.sqlite3"
    with sqlite3.connect(database) as connection:
        result = run_migrations(
            connection,
            database_path=database,
            schema_sql=CURRENT_SCHEMA_SQL,
            registry=MIGRATIONS,
        )
        assert result.to_version == 13
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        assert {
            "campaign_session_closeouts",
            "campaign_session_closeout_items",
        } <= tables
        closeout_indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(campaign_session_closeouts)"
            )
        }
        item_indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(campaign_session_closeout_items)"
            )
        }
        session_indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(campaign_sessions)")
        }
        assert "idx_campaign_session_closeouts_campaign_status" in closeout_indexes
        assert "idx_campaign_session_closeout_items_campaign" in item_indexes
        assert "idx_campaign_sessions_campaign_id" in session_indexes
        closeout_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(campaign_session_closeouts)"
        ).fetchall()
        item_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(campaign_session_closeout_items)"
        ).fetchall()
        assert {(row[2], row[3], row[4], row[6]) for row in closeout_foreign_keys} >= {
            ("campaign_sessions", "campaign_slug", "campaign_slug", "RESTRICT"),
            ("campaign_sessions", "session_id", "id", "RESTRICT"),
            ("users", "created_by_user_id", "id", "SET NULL"),
            ("users", "updated_by_user_id", "id", "SET NULL"),
            ("users", "completed_by_user_id", "id", "SET NULL"),
        }
        assert {(row[2], row[3], row[4], row[6]) for row in item_foreign_keys} == {
            ("campaign_session_closeouts", "campaign_slug", "campaign_slug", "CASCADE"),
            ("campaign_session_closeouts", "closeout_id", "id", "CASCADE"),
        }
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_open_duplicate_and_summary_are_persistent_bounded_and_audited(app, users):
    with app.app_context():
        active = app.extensions["campaign_session_service"].begin_session(
            "active-only",
            started_by_user_id=users["dm"]["id"],
        )
        active_service = _service(
            app,
            users["dm"]["id"],
            context=_authorization(users["dm"]["id"], campaign_slug="active-only"),
        )
        with pytest.raises(CampaignSessionCloseoutValidationError):
            active_service.open_or_create("active-only", active.id)

        session_id = _closed_session(app, users["dm"]["id"])
        service = _service(app, users["dm"]["id"])
        isolated_service = _service(
            app,
            users["dm"]["id"],
            context=_authorization(users["dm"]["id"], campaign_slug="other-campaign"),
        )
        with pytest.raises(CampaignSessionCloseoutValidationError):
            isolated_service.open_or_create("other-campaign", session_id)

        opened = service.open_or_create(TEST_CAMPAIGN_SLUG, session_id)
        assert opened.created is True
        assert opened.closeout.status == SESSION_CLOSEOUT_STATUS_OPEN
        assert opened.closeout.revision == 1
        assert tuple(item.item_key for item in opened.closeout.items) == SESSION_CLOSEOUT_ITEM_KEYS
        assert {item.status for item in opened.closeout.items} == {"pending"}

        before = get_db().execute(
            "SELECT * FROM campaign_session_closeouts WHERE id = ?",
            (opened.closeout.id,),
        ).fetchone()
        duplicate = service.open_or_create(TEST_CAMPAIGN_SLUG, session_id)
        after = get_db().execute(
            "SELECT * FROM campaign_session_closeouts WHERE id = ?",
            (opened.closeout.id,),
        ).fetchone()
        assert duplicate.created is False
        assert duplicate.closeout == opened.closeout
        assert tuple(before) == tuple(after)
        assert len(_audit_rows("campaign_session_closeout_opened")) == 1

        assert service.list_summaries(TEST_CAMPAIGN_SLUG) == [
            service.list_summaries(TEST_CAMPAIGN_SLUG)[0]
        ]
        summary = service.list_summaries(TEST_CAMPAIGN_SLUG)[0]
        assert (summary.item_count, summary.resolved_count) == (6, 0)
        with pytest.raises(CampaignSessionCloseoutValidationError):
            service.list_summaries(TEST_CAMPAIGN_SLUG, limit=27)


def test_item_revision_noop_note_bounds_completion_and_reopen(app, users):
    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        service = _service(app, users["dm"]["id"])
        current = service.open_or_create(TEST_CAMPAIGN_SLUG, session_id).closeout

        changed = service.update_item(
            TEST_CAMPAIGN_SLUG,
            session_id,
            expected_revision=current.revision,
            item_key=SESSION_CLOSEOUT_ITEM_KEYS[0],
            status=SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE,
            note="  first\r\nsecond  ",
        )
        assert changed.revision == 2
        assert changed.items[0].note == "first\nsecond"
        audit = AuthStore().list_recent_audit_events(
            limit=10,
            event_type="campaign_session_closeout_item_updated",
        )[0]
        assert audit.metadata == {
            "closeout_id": changed.id,
            "item_count": 6,
            "item_key": SESSION_CLOSEOUT_ITEM_KEYS[0],
            "new_revision": 2,
            "new_status": "complete",
            "note_changed": True,
            "note_present": True,
            "previous_revision": 1,
            "previous_status": "pending",
            "resolved_count": 1,
            "session_id": session_id,
        }
        assert "first" not in str(audit.metadata)

        before_audits = len(_audit_rows("campaign_session_closeout_item_updated"))
        assert service.update_item(
            TEST_CAMPAIGN_SLUG,
            session_id,
            expected_revision=changed.revision,
            item_key=SESSION_CLOSEOUT_ITEM_KEYS[0],
            status=SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE,
            note="first\nsecond",
        ) == changed
        assert len(_audit_rows("campaign_session_closeout_item_updated")) == before_audits

        with pytest.raises(CampaignSessionCloseoutConflictError):
            service.update_item(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=1,
                item_key=SESSION_CLOSEOUT_ITEM_KEYS[1],
                status="complete",
            )
        for invalid_note in ("bad\x00note", "x" * 501, "é" * 501):
            with pytest.raises(CampaignSessionCloseoutValidationError):
                service.update_item(
                    TEST_CAMPAIGN_SLUG,
                    session_id,
                    expected_revision=changed.revision,
                    item_key=SESSION_CLOSEOUT_ITEM_KEYS[1],
                    status="complete",
                    note=invalid_note,
                )
        for invalid_status in ("complete", "not_applicable"):
            with pytest.raises(CampaignSessionCloseoutValidationError):
                service.update_item(
                    TEST_CAMPAIGN_SLUG,
                    session_id,
                    expected_revision=changed.revision,
                    item_key="external_archive",
                    status=invalid_status,
                )
        with pytest.raises(CampaignSessionCloseoutValidationError, match="URLs"):
            service.update_item(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=changed.revision,
                item_key="external_archive",
                status="table_managed",
                note="https://archive.example.invalid/private",
            )

        with pytest.raises(CampaignSessionCloseoutValidationError):
            service.complete(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=changed.revision,
            )
        current = changed
        for item_key in SESSION_CLOSEOUT_ITEM_KEYS[1:]:
            current = service.update_item(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=current.revision,
                item_key=item_key,
                status="not_applicable" if item_key != "external_archive" else "table_managed",
            )
        assert current.status == SESSION_CLOSEOUT_STATUS_OPEN
        assert current.resolved_count == 6

        completed = service.complete(
            TEST_CAMPAIGN_SLUG,
            session_id,
            expected_revision=current.revision,
        )
        assert completed.status == SESSION_CLOSEOUT_STATUS_COMPLETED
        assert completed.completed_at is not None
        assert completed.completed_by_user_id == users["dm"]["id"]
        assert len(_audit_rows("campaign_session_closeout_completed")) == 1
        with pytest.raises(CampaignSessionCloseoutConflictError):
            service.update_item(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=completed.revision,
                item_key=SESSION_CLOSEOUT_ITEM_KEYS[0],
                status="pending",
            )

        reopened = service.reopen(
            TEST_CAMPAIGN_SLUG,
            session_id,
            expected_revision=completed.revision,
        )
        assert reopened.status == SESSION_CLOSEOUT_STATUS_OPEN
        assert reopened.completed_at is None
        assert reopened.completed_by_user_id is None
        assert reopened.items == completed.items
        assert len(_audit_rows("campaign_session_closeout_reopened")) == 1


def test_authorization_precedes_parsing_and_reads_and_view_as_is_read_only(app, users):
    class UnreadableStore:
        def __getattr__(self, name):
            raise AssertionError(f"unauthorized caller reached {name}")

    denied = CampaignSessionCloseoutService(
        UnreadableStore(),
        app.extensions["auth_store"],
        authorization_adapter=lambda _slug: _authorization(
            users["party"]["id"],
            content=False,
            session=False,
        ),
    )
    with app.app_context(), pytest.raises(CampaignSessionCloseoutAuthorizationError):
        denied.get_closeout(TEST_CAMPAIGN_SLUG, "not-an-id")

    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        owner = _service(app, users["dm"]["id"])
        owner.open_or_create(TEST_CAMPAIGN_SLUG, session_id)
        view_as = _service(
            app,
            users["admin"]["id"],
            context=_authorization(
                users["admin"]["id"],
                view_as=True,
                read_only=True,
            ),
        )
        assert view_as.get_closeout(TEST_CAMPAIGN_SLUG, session_id) is not None
        with pytest.raises(CampaignSessionCloseoutAuthorizationError):
            view_as.update_item(
                TEST_CAMPAIGN_SLUG,
                "not-an-id",
                expected_revision="not-a-revision",
                item_key="unknown",
                status="unknown",
            )


@pytest.mark.parametrize("failure_boundary", ["store", "audit", "pre_commit"])
def test_mutation_faults_roll_back_closeout_and_audit(
    app,
    users,
    monkeypatch,
    failure_boundary,
):
    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        service = _service(app, users["dm"]["id"])
        opened = service.open_or_create(TEST_CAMPAIGN_SLUG, session_id).closeout
        store = app.extensions["campaign_session_store"]
        auth_store = app.extensions["auth_store"]

        if failure_boundary == "store":
            original = store.update_closeout_item

            def fail_store(*args, **kwargs):
                get_db().execute(
                    "UPDATE campaign_session_closeout_items SET note = 'must roll back' WHERE closeout_id = ?",
                    (opened.id,),
                )
                raise RuntimeError("store fault")

            monkeypatch.setattr(store, "update_closeout_item", fail_store)
        elif failure_boundary == "audit":
            monkeypatch.setattr(
                auth_store,
                "insert_audit_event",
                lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit fault")),
            )
        else:
            service = _service(
                app,
                users["dm"]["id"],
                pre_commit_hook=lambda _operation: (_ for _ in ()).throw(
                    RuntimeError("pre-commit fault")
                ),
            )

        with pytest.raises(RuntimeError, match="fault"):
            service.update_item(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=opened.revision,
                item_key=SESSION_CLOSEOUT_ITEM_KEYS[0],
                status="complete",
                note="private note",
            )
        restored = store.get_closeout(TEST_CAMPAIGN_SLUG, session_id)
        assert restored == opened
        assert _audit_rows("campaign_session_closeout_item_updated") == []
        if failure_boundary == "store":
            monkeypatch.setattr(store, "update_closeout_item", original)


def test_concurrent_item_updates_have_one_revision_winner(app, users):
    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        opened = _service(app, users["dm"]["id"]).open_or_create(
            TEST_CAMPAIGN_SLUG,
            session_id,
        ).closeout

    second_app = create_app()
    second_app.config.update(
        TESTING=True,
        DB_PATH=app.config["DB_PATH"],
        CAMPAIGNS_DIR=app.config["CAMPAIGNS_DIR"],
    )

    def run(target_app, item_key):
        with target_app.app_context():
            service = _service(target_app, users["dm"]["id"])
            try:
                return service.update_item(
                    TEST_CAMPAIGN_SLUG,
                    session_id,
                    expected_revision=opened.revision,
                    item_key=item_key,
                    status="complete",
                ).revision
            except CampaignSessionCloseoutConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda pair: run(*pair),
                (
                    (app, SESSION_CLOSEOUT_ITEM_KEYS[0]),
                    (second_app, SESSION_CLOSEOUT_ITEM_KEYS[1]),
                ),
            )
        )
    assert sorted(results, key=str) == [2, "conflict"]


def test_confirmed_history_delete_is_closeout_aware_atomic_and_bumps_live_once(app, users):
    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        legacy = app.extensions["campaign_session_service"]
        closeout_service = _service(app, users["dm"]["id"])
        closeout = closeout_service.open_or_create(
            TEST_CAMPAIGN_SLUG,
            session_id,
        ).closeout
        before_revision = legacy.get_live_revision(TEST_CAMPAIGN_SLUG)

        with pytest.raises(CampaignSessionCloseoutConflictError):
            closeout_service.delete_confirmed_session_history(
                TEST_CAMPAIGN_SLUG,
                session_id,
                expected_revision=closeout.revision + 1,
            )
        with pytest.raises(
            CampaignSessionValidationError,
            match="confirmed Session-history deletion",
        ):
            legacy.delete_session_log(
                TEST_CAMPAIGN_SLUG,
                session_id,
                updated_by_user_id=users["dm"]["id"],
            )
        assert legacy.get_live_revision(TEST_CAMPAIGN_SLUG) == before_revision

        closeout_service.delete_confirmed_session_history(
            TEST_CAMPAIGN_SLUG,
            session_id,
            expected_revision=closeout.revision,
        )
        assert legacy.get_session_log(TEST_CAMPAIGN_SLUG, session_id) is None
        assert legacy.get_live_revision(TEST_CAMPAIGN_SLUG) == before_revision + 1
        assert app.extensions["campaign_session_store"].get_closeout(
            TEST_CAMPAIGN_SLUG,
            session_id,
        ) is None
        assert len(_audit_rows("campaign_session_closeout_deleted_with_history")) == 1


def test_actor_deletion_nulls_closeout_evidence_without_deleting_state(app, users):
    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        service = _service(app, users["dm"]["id"])
        opened = service.open_or_create(TEST_CAMPAIGN_SLUG, session_id).closeout
        AuthStore().delete_user(users["dm"]["id"])
        retained = app.extensions["campaign_session_store"].get_closeout(
            TEST_CAMPAIGN_SLUG,
            session_id,
        )
        assert retained is not None and retained.id == opened.id
        assert retained.created_by_user_id is None
        assert retained.updated_by_user_id is None


def test_populated_v13_backup_restore_and_package_export_are_lossless(app, users, tmp_path):
    with app.app_context():
        session_id = _closed_session(app, users["dm"]["id"])
        service = _service(app, users["dm"]["id"])
        closeout = service.open_or_create(TEST_CAMPAIGN_SLUG, session_id).closeout
        closeout = service.update_item(
            TEST_CAMPAIGN_SLUG,
            session_id,
            expected_revision=closeout.revision,
            item_key="table_notes",
            status="complete",
            note="private closeout note",
        )
        archive = create_backup_archive_v2(
            db_path=Path(app.config["DB_PATH"]),
            campaigns_dir=Path(app.config["CAMPAIGNS_DIR"]),
            backup_root=tmp_path / "backups",
            archive_basename="closeout-v13",
            created_at="2026-08-29T12:00:00Z",
        )
        package_dir = tmp_path / "campaign-package"
        export_campaign_package(
            app=app,
            campaign_slug=TEST_CAMPAIGN_SLUG,
            output_dir=package_dir,
        )

    restored = restore_backup_archive(
        archive_path=archive.archive_path,
        db_path=tmp_path / "restored" / "wiki.sqlite3",
        campaigns_dir=tmp_path / "restored" / "campaigns",
    )
    assert restored.migration_required is False
    with sqlite3.connect(restored.database_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        restored_note = connection.execute(
            "SELECT note FROM campaign_session_closeout_items WHERE closeout_id = ? AND item_key = 'table_notes'",
            (closeout.id,),
        ).fetchone()[0]
        assert restored_note == "private closeout note"

    closeout_rows = (
        package_dir
        / "state"
        / "sqlite-tables"
        / "campaign_session_closeouts.jsonl"
    ).read_text(encoding="utf-8")
    item_rows = (
        package_dir
        / "state"
        / "sqlite-tables"
        / "campaign_session_closeout_items.jsonl"
    ).read_text(encoding="utf-8")
    assert f'"session_id": {session_id}' in closeout_rows
    assert "private closeout note" in item_rows


def test_v12_restore_requires_forward_migration_and_v13_creates_no_closeouts(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_db = source_root / "wiki.sqlite3"
    source_campaigns = source_root / "campaigns"
    source_campaigns.mkdir()
    with sqlite3.connect(source_db) as connection:
        connection.row_factory = sqlite3.Row
        result = run_migrations(
            connection,
            database_path=source_db,
            schema_sql=MIGRATIONS[11].payload.schema_sql,
            registry=MIGRATIONS[:12],
        )
        assert result.to_version == 12
        connection.execute(
            "INSERT INTO campaign_sessions (campaign_slug, status, started_at) VALUES ('legacy', 'closed', '2026-01-01T00:00:00+00:00')"
        )
        connection.commit()

    archive = create_backup_archive_v2(
        db_path=source_db,
        campaigns_dir=source_campaigns,
        backup_root=tmp_path / "backups",
        archive_basename="v12",
        created_at="2026-08-29T12:00:00Z",
    )
    restored = restore_backup_archive(
        archive_path=archive.archive_path,
        db_path=tmp_path / "restored" / "wiki.sqlite3",
        campaigns_dir=tmp_path / "restored" / "campaigns",
    )
    assert restored.migration_required is True
    with sqlite3.connect(restored.database_path) as connection:
        connection.row_factory = sqlite3.Row
        migrated = run_migrations(
            connection,
            database_path=restored.database_path,
            schema_sql=CURRENT_SCHEMA_SQL,
        )
        assert migrated.from_version == 12
        assert migrated.to_version == 13
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_session_closeouts"
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
