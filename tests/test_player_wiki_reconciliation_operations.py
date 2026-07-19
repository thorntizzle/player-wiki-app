from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from player_wiki.backup_archive import create_backup_archive_v2
from player_wiki.campaign_content_service import (
    CampaignContentError,
    prepare_campaign_page_write,
)
from player_wiki.db import get_db
from player_wiki.operations import BackupResult
from player_wiki.player_wiki_reconciliation import (
    PreparedManagedImage,
    ReconciliationHooks,
)
from player_wiki.player_wiki_reconciliation_operations import (
    PlayerWikiReconciliationOperationError,
    PlayerWikiReconciliationOperationHooks,
    apply_player_wiki_reconciliation_operation,
)
from player_wiki.runtime_lease import (
    acquire_runtime_state_lease,
    active_restore_journal_path,
)
from tests.test_player_wiki_deletion_reconciliation import _create_page
from tests.test_player_wiki_reconciliation import _campaign, _prepared_page
from tests.test_player_wiki_reconciliation_inspection import (
    _fixture,
    _insert_publication,
)


def _controlled_backup_creator(**kwargs) -> BackupResult:
    created_at = "2026-07-19T12:00:00Z"
    evidence = create_backup_archive_v2(
        db_path=kwargs["db_path"],
        campaigns_dir=kwargs["campaigns_dir"],
        backup_root=kwargs["backup_root"],
        archive_basename=f"controlled-{uuid4().hex}",
        created_at=created_at,
    )
    return BackupResult(
        archive_path=evidence.archive_path,
        created_at=created_at,
        database_filename=evidence.database_filename,
        campaign_file_count=evidence.campaign_file_count,
        evidence=evidence,
    )


def _close_disposable_wal(database: Path) -> None:
    wal = Path(f"{database}-wal")
    shm = Path(f"{database}-shm")
    if wal.exists():
        assert wal.stat().st_size == 0
        wal.unlink()
    if shm.exists():
        shm.unlink()


def _apply(app, tmp_path: Path, *, kind: str, operation_id: str, action: str, **kwargs):
    return apply_player_wiki_reconciliation_operation(
        database_path=Path(app.config["DB_PATH"]),
        campaigns_dir=Path(app.config["CAMPAIGNS_DIR"]),
        backup_root=tmp_path / "backups",
        kind=kind,
        operation_id=operation_id,
        action=action,
        confirmed=True,
        app_factory=lambda: app,
        backup_creator=_controlled_backup_creator,
        **kwargs,
    )


def _publication_operation(
    app,
    *,
    page_ref: str,
    crash_event: str,
    existing: bool = False,
):
    with app.app_context():
        campaign, prepared = _prepared_page(
            app,
            page_ref,
            title="Desired title",
            body="Desired body",
        )
        reconciler = app.extensions["player_wiki_reconciler"]
        if existing:
            _, original = _prepared_page(
                app,
                page_ref,
                title="Previous title",
                body="Previous body",
            )
            reconciler.mutate(campaign, original, operation_kind="api_upsert")
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError(crash_event))
                if event == crash_event
                else None
            )
        )
        with pytest.raises(RuntimeError, match=crash_event):
            reconciler.mutate(campaign, prepared, operation_kind="api_upsert")
        reconciler.hooks = ReconciliationHooks()
        row = get_db().execute(
            "SELECT * FROM player_wiki_reconciliation_operations WHERE page_ref = ?",
            (page_ref,),
        ).fetchone()
        assert row is not None
        result = campaign, prepared, str(row["operation_id"])
    _close_disposable_wal(Path(app.config["DB_PATH"]))
    return result


def _deletion_operation(app, *, page_ref: str, crash_event: str):
    with app.app_context():
        campaign, record = _create_page(app, page_ref)
        reconciler = app.extensions["player_wiki_reconciler"]
        reconciler.hooks = ReconciliationHooks(
            on_event=lambda event, _operation_id: (
                (_ for _ in ()).throw(RuntimeError(crash_event))
                if event == crash_event
                else None
            )
        )
        with pytest.raises(RuntimeError, match=crash_event):
            reconciler.delete(campaign, record, operation_kind="api_delete")
        reconciler.hooks = ReconciliationHooks()
        row = get_db().execute(
            "SELECT * FROM player_wiki_deletion_operations WHERE page_ref = ?",
            (page_ref,),
        ).fetchone()
        assert row is not None
        result = campaign, record, str(row["operation_id"]), dict(row)
    _close_disposable_wal(Path(app.config["DB_PATH"]))
    return result


@pytest.mark.parametrize(
    ("crash_event", "action", "outcome"),
    [
        ("after_prepare", "abandon-precommit", "abandoned"),
        ("after_primary_publish", "resume-forward", "completed"),
        ("after_repository_pending", "retry-refresh-cleanup", "completed"),
    ],
)
def test_publication_apply_supported_actions_are_backup_gated_and_exact(
    app, tmp_path, crash_event, action, outcome
):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref=f"notes/publication-{action}",
        crash_event=crash_event,
    )

    result = _apply(
        app,
        tmp_path,
        kind="publication",
        operation_id=operation_id,
        action=action,
    )

    assert result.outcome == outcome
    assert result.backup_path.exists()
    assert result.backup_evidence.verification_level == "verified_v2"
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0
        page = app.extensions["campaign_page_store"].get_page_record(
            "linden-pass", prepared.page_ref, include_body=True
        )
        if action == "abandon-precommit":
            assert page is None
            assert not prepared.file_path.exists()
        else:
            assert page is not None
            assert prepared.file_path.read_bytes() == prepared.rendered_markdown


@pytest.mark.parametrize(
    ("crash_event", "action", "outcome"),
    [
        ("after_delete_prepare", "abandon-precommit", "abandoned"),
        ("after_tombstone_move", "resume-forward", "completed"),
        ("after_delete_repository_pending", "retry-refresh-cleanup", "completed"),
    ],
)
def test_deletion_apply_supported_actions_are_backup_gated_and_exact(
    app, tmp_path, crash_event, action, outcome
):
    _campaign_value, record, operation_id, _row = _deletion_operation(
        app,
        page_ref=f"notes/deletion-{action}",
        crash_event=crash_event,
    )

    result = _apply(
        app,
        tmp_path,
        kind="deletion",
        operation_id=operation_id,
        action=action,
    )

    assert result.outcome == outcome
    assert result.backup_path.exists()
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_deletion_operations"
        ).fetchone()[0] == 0
        page = app.extensions["campaign_page_store"].get_page_record(
            "linden-pass", record.page_ref
        )
        if action == "abandon-precommit":
            assert page is not None
            assert record.file_path.exists()
        else:
            assert page is None
            assert not record.file_path.exists()


@pytest.mark.parametrize(
    ("kind", "operation_id", "action", "confirmed", "reason"),
    [
        ("other", "a" * 32, "resume-forward", True, "invalid_kind"),
        ("publication", "NOT-AN-ID", "resume-forward", True, "invalid_operation_id"),
        ("publication", "a" * 32, "invented", True, "unsupported_action"),
        ("publication", "a" * 32, "resume-forward", False, "confirmation_required"),
    ],
)
def test_apply_rejects_invalid_inputs_before_inspection_or_backup(
    app, tmp_path, kind, operation_id, action, confirmed, reason
):
    called = False

    def backup_creator(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("backup must not run")

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        apply_player_wiki_reconciliation_operation(
            database_path=Path(app.config["DB_PATH"]),
            campaigns_dir=Path(app.config["CAMPAIGNS_DIR"]),
            backup_root=tmp_path / "backups",
            kind=kind,
            operation_id=operation_id,
            action=action,
            confirmed=confirmed,
            app_factory=lambda: app,
            backup_creator=backup_creator,
        )
    assert captured.value.reason_code == reason
    assert called is False


def test_apply_rejects_mismatched_action_before_backup(app, tmp_path):
    _campaign_value, _prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/mismatch",
        crash_event="after_prepare",
    )
    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
        )
    assert captured.value.reason_code == "action_not_supported_by_evidence"
    assert not (tmp_path / "backups").exists()


def test_backup_failure_preserves_publication_state(app, tmp_path):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/backup-failure",
        crash_event="after_primary_publish",
    )
    desired = prepared.file_path.read_bytes()

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        apply_player_wiki_reconciliation_operation(
            database_path=Path(app.config["DB_PATH"]),
            campaigns_dir=Path(app.config["CAMPAIGNS_DIR"]),
            backup_root=tmp_path / "backups",
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
            confirmed=True,
            app_factory=lambda: app,
            backup_creator=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("private backup detail")
            ),
        )
    assert captured.value.reason_code == "backup_failed"
    assert prepared.file_path.read_bytes() == desired
    with app.app_context():
        assert get_db().execute(
            "SELECT state FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "prepared"


def test_post_backup_evidence_drift_retains_backup_and_operation(app, tmp_path):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/post-backup-drift",
        crash_event="after_primary_publish",
    )

    def drift(event: str, _operation_id: str) -> None:
        if event == "before_reinspection":
            prepared.file_path.write_bytes(b"third private bytes")

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
            hooks=PlayerWikiReconciliationOperationHooks(on_event=drift),
        )
    assert captured.value.reason_code == "action_not_supported_by_evidence"
    assert list((tmp_path / "backups").glob("*.zip"))
    with app.app_context():
        assert get_db().execute(
            "SELECT state FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "prepared"


def test_completed_operation_repeat_fails_without_duplicate_effects(app, tmp_path):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/repeat",
        crash_event="after_primary_publish",
    )
    _apply(
        app,
        tmp_path,
        kind="publication",
        operation_id=operation_id,
        action="resume-forward",
    )
    with app.app_context():
        audit_count = get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log"
        ).fetchone()[0]
    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
        )
    assert captured.value.reason_code == "no_active_operation"
    assert prepared.file_path.exists()
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log"
        ).fetchone()[0] == audit_count


def test_completed_deletion_repeat_fails_without_duplicate_effects(app, tmp_path):
    _campaign_value, record, operation_id, _row = _deletion_operation(
        app,
        page_ref="notes/deletion-repeat",
        crash_event="after_tombstone_move",
    )
    _apply(
        app,
        tmp_path,
        kind="deletion",
        operation_id=operation_id,
        action="resume-forward",
    )
    with app.app_context():
        audit_count = get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log"
        ).fetchone()[0]
    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="deletion",
            operation_id=operation_id,
            action="resume-forward",
        )
    assert captured.value.reason_code == "no_active_operation"
    assert not record.file_path.exists()
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log"
        ).fetchone()[0] == audit_count


def test_active_restore_refuses_before_inspection_backup_or_action(app, tmp_path):
    _campaign_value, _prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/restore-active",
        crash_event="after_primary_publish",
    )
    journal = active_restore_journal_path(Path(app.config["DB_PATH"]))
    journal.write_text("private restore evidence", encoding="utf-8")

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
        )

    assert captured.value.reason_code == "restore_recovery_active"
    assert not (tmp_path / "backups").exists()


def test_busy_runtime_lease_refuses_before_backup_or_action(app, tmp_path):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/runtime-busy",
        crash_event="after_primary_publish",
    )
    lease = acquire_runtime_state_lease(Path(app.config["DB_PATH"]))
    try:
        with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
            _apply(
                app,
                tmp_path,
                kind="publication",
                operation_id=operation_id,
                action="resume-forward",
            )
    finally:
        lease.close()

    assert captured.value.reason_code == "runtime_state_busy"
    assert not (tmp_path / "backups").exists()
    assert prepared.file_path.exists()


def test_apply_requires_current_v9_ledger_before_backup(tmp_path):
    database, campaigns, content, _assets = _fixture(tmp_path, version=8)
    desired = b"legacy active operation"
    (content / "legacy.md").write_bytes(desired)
    _insert_publication(
        database,
        operation_id="a" * 32,
        page_ref="legacy",
        state="prepared",
        desired=desired,
    )

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        apply_player_wiki_reconciliation_operation(
            database_path=database,
            campaigns_dir=campaigns,
            backup_root=tmp_path / "backups",
            kind="publication",
            operation_id="a" * 32,
            action="resume-forward",
            confirmed=True,
            app_factory=lambda: (_ for _ in ()).throw(AssertionError("no app")),
            backup_creator=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("no backup")
            ),
        )

    assert captured.value.reason_code == "current_schema_required"
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("markdown_payload", [b"desired markdown", b"third markdown"])
def test_image_previous_with_changed_markdown_refuses_abandon_before_backup(
    tmp_path, markdown_payload
):
    database, campaigns, content, assets = _fixture(tmp_path)
    previous_markdown = b"previous markdown"
    desired_markdown = b"desired markdown"
    previous_image = b"previous image"
    (content / "mixed.md").write_bytes(markdown_payload)
    (assets / "mixed.webp").write_bytes(previous_image)
    _insert_publication(
        database,
        operation_id="b" * 32,
        page_ref="mixed",
        state="prepared",
        desired=desired_markdown,
        previous_markdown=hashlib.sha256(previous_markdown).hexdigest(),
        primary_authority="image",
        desired_primary_ref="mixed.webp",
        previous_primary=hashlib.sha256(previous_image).hexdigest(),
        desired_primary=hashlib.sha256(b"desired image").hexdigest(),
    )

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        apply_player_wiki_reconciliation_operation(
            database_path=database,
            campaigns_dir=campaigns,
            backup_root=tmp_path / "backups",
            kind="publication",
            operation_id="b" * 32,
            action="abandon-precommit",
            confirmed=True,
            app_factory=lambda: (_ for _ in ()).throw(AssertionError("no app")),
            backup_creator=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("no backup")
            ),
        )

    assert captured.value.reason_code == "action_not_supported_by_evidence"
    assert not (tmp_path / "backups").exists()


def test_exact_apply_preserves_unrelated_active_operation(app, tmp_path):
    _campaign_value, _first, first_id = _publication_operation(
        app,
        page_ref="notes/exact-first",
        crash_event="after_primary_publish",
    )
    _campaign_value, second, second_id = _publication_operation(
        app,
        page_ref="notes/exact-second",
        crash_event="after_primary_publish",
    )
    database = Path(app.config["DB_PATH"])
    connection = sqlite3.connect(database)
    try:
        connection.row_factory = sqlite3.Row
        before = dict(
            connection.execute(
                "SELECT * FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
                (second_id,),
            ).fetchone()
        )
    finally:
        connection.close()

    _apply(
        app,
        tmp_path,
        kind="publication",
        operation_id=first_id,
        action="resume-forward",
    )

    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        after_row = connection.execute(
            "SELECT * FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (second_id,),
        ).fetchone()
        assert after_row is not None
        assert dict(after_row) == before
        assert connection.execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (first_id,),
        ).fetchone()[0] == 0
    assert second.file_path.exists()


def test_backup_verification_failure_retains_archive_and_operation(app, tmp_path):
    _campaign_value, _prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/backup-verification",
        crash_event="after_primary_publish",
    )

    def false_evidence_backup(**kwargs):
        result = _controlled_backup_creator(**kwargs)
        return replace(
            result,
            evidence=replace(result.evidence, manifest_hashes_verified=False),
        )

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        apply_player_wiki_reconciliation_operation(
            database_path=Path(app.config["DB_PATH"]),
            campaigns_dir=Path(app.config["CAMPAIGNS_DIR"]),
            backup_root=tmp_path / "backups",
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
            confirmed=True,
            app_factory=lambda: app,
            backup_creator=false_evidence_backup,
        )

    assert captured.value.reason_code == "backup_verification_failed"
    assert list((tmp_path / "backups").glob("*.zip"))
    with closing(sqlite3.connect(app.config["DB_PATH"])) as connection:
        assert connection.execute(
            "SELECT state FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "prepared"


def test_image_first_resume_publishes_stored_markdown_after_verified_backup(
    app, tmp_path
):
    with app.app_context():
        campaign = _campaign(app)
        page_ref = "notes/image-first-apply"
        asset_ref = "wiki-pages/notes/image-first-apply.webp"
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
                (_ for _ in ()).throw(RuntimeError("image committed"))
                if event == "after_primary_publish"
                else None
            )
        )
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
        row = get_db().execute(
            "SELECT operation_id FROM player_wiki_reconciliation_operations WHERE page_ref = ?",
            (page_ref,),
        ).fetchone()
        operation_id = str(row["operation_id"])
        assert asset_path.read_bytes() == b"desired image"
        assert updated.file_path.read_bytes() == original.rendered_markdown
        reconciler.hooks = ReconciliationHooks()
    _close_disposable_wal(Path(app.config["DB_PATH"]))

    result = _apply(
        app,
        tmp_path,
        kind="publication",
        operation_id=operation_id,
        action="resume-forward",
    )

    assert result.outcome == "completed"
    assert asset_path.read_bytes() == b"desired image"
    assert updated.file_path.read_bytes() == updated.rendered_markdown


@pytest.mark.parametrize(
    "failure_event",
    ["before_repository_refresh", "before_journal_cleanup"],
)
def test_publication_post_commit_fault_retains_backup_and_retries_cleanup_once(
    app, tmp_path, failure_event
):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref=f"notes/publication-fault-{failure_event}",
        crash_event="after_primary_publish",
    )

    def fail(event: str, _operation_id: str) -> None:
        if event == failure_event:
            raise RuntimeError("private publication failure")

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="publication",
            operation_id=operation_id,
            action="resume-forward",
            hooks=PlayerWikiReconciliationOperationHooks(on_event=fail),
        )

    assert captured.value.reason_code == "action_failed"
    assert len(list((tmp_path / "backups").glob("*.zip"))) == 1
    with app.app_context():
        assert get_db().execute(
            "SELECT state FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "repository_pending"

    result = _apply(
        app,
        tmp_path,
        kind="publication",
        operation_id=operation_id,
        action="retry-refresh-cleanup",
    )
    assert result.outcome == "completed"
    assert prepared.file_path.exists()
    assert len(list((tmp_path / "backups").glob("*.zip"))) == 2


@pytest.mark.parametrize(
    "failure_event",
    ["before_delete_repository_refresh", "before_delete_journal_cleanup"],
)
def test_deletion_post_commit_fault_retains_backup_and_retries_cleanup_once(
    app, tmp_path, failure_event
):
    _campaign_value, record, operation_id, _row = _deletion_operation(
        app,
        page_ref=f"notes/deletion-fault-{failure_event}",
        crash_event="after_tombstone_move",
    )

    def fail(event: str, _operation_id: str) -> None:
        if event == failure_event:
            raise RuntimeError("private deletion failure")

    with pytest.raises(PlayerWikiReconciliationOperationError) as captured:
        _apply(
            app,
            tmp_path,
            kind="deletion",
            operation_id=operation_id,
            action="resume-forward",
            hooks=PlayerWikiReconciliationOperationHooks(on_event=fail),
        )

    assert captured.value.reason_code == "action_failed"
    assert len(list((tmp_path / "backups").glob("*.zip"))) == 1
    with app.app_context():
        assert get_db().execute(
            "SELECT state FROM player_wiki_deletion_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "repository_pending"

    result = _apply(
        app,
        tmp_path,
        kind="deletion",
        operation_id=operation_id,
        action="retry-refresh-cleanup",
    )
    assert result.outcome == "completed"
    assert not record.file_path.exists()
    assert len(list((tmp_path / "backups").glob("*.zip"))) == 2


def test_ops_cli_applies_exact_operation_and_emits_bounded_success_json(app, tmp_path):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/cli-apply",
        crash_event="after_primary_publish",
    )
    project_root = Path(__file__).resolve().parents[1]
    backup_root = tmp_path / "cli-backups"
    env = os.environ.copy()
    env.update(
        {
            "PLAYER_WIKI_DB_PATH": str(app.config["DB_PATH"]),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(app.config["CAMPAIGNS_DIR"]),
            "PLAYER_WIKI_ENV": "development",
            "PLAYER_WIKI_SECRET_KEY": "disposable-cli-secret",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "ops.py"),
            "player-wiki-reconciliation-apply",
            "--kind",
            "publication",
            "--operation-id",
            operation_id,
            "--action",
            "resume-forward",
            "--output-dir",
            str(backup_root),
            "--yes",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_root,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert report["kind"] == "publication"
    assert report["operation_id"] == operation_id
    assert report["action"] == "resume-forward"
    assert report["outcome"] == "completed"
    assert report["backup"]["verification_level"] == "verified_v2"
    assert report["backup"]["manifest_hashes_verified"] is True
    assert prepared.file_path.exists()
    with closing(sqlite3.connect(app.config["DB_PATH"])) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == 0


def test_selected_publication_resume_refuses_stale_switch_to_previous(
    app, monkeypatch
):
    campaign, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/stale-publication-resume",
        crash_event="after_primary_publish",
    )
    with app.app_context():
        reconciler = app.extensions["player_wiki_reconciler"]
        original = reconciler._revalidate_exact_action

        def switch_after_validation(*args, **kwargs):
            result = original(*args, **kwargs)
            prepared.file_path.unlink()
            return result

        monkeypatch.setattr(reconciler, "_revalidate_exact_action", switch_after_validation)
        with pytest.raises(CampaignContentError, match="no longer matches"):
            reconciler.resume_forward_operation(
                kind="publication", operation_id=operation_id
            )
        assert get_db().execute(
            "SELECT state FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "prepared"
        assert campaign.slug == "linden-pass"


def test_selected_deletion_resume_refuses_stale_switch_to_precommit(
    app, monkeypatch
):
    campaign, record, operation_id, row = _deletion_operation(
        app,
        page_ref="notes/stale-deletion-resume",
        crash_event="after_tombstone_move",
    )
    tombstone = Path(campaign.player_content_dir) / Path(
        *str(row["tombstone_ref"]).split("/")
    )
    with app.app_context():
        reconciler = app.extensions["player_wiki_reconciler"]
        original = reconciler._revalidate_exact_action

        def switch_after_validation(*args, **kwargs):
            result = original(*args, **kwargs)
            tombstone.replace(record.file_path)
            return result

        monkeypatch.setattr(reconciler, "_revalidate_exact_action", switch_after_validation)
        with pytest.raises(CampaignContentError, match="no longer matches"):
            reconciler.resume_forward_operation(
                kind="deletion", operation_id=operation_id
            )
        assert get_db().execute(
            "SELECT state FROM player_wiki_deletion_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "prepared"
        assert record.file_path.exists()


def test_selected_publication_retry_refuses_stale_switch_to_prepared(
    app, monkeypatch
):
    _campaign_value, prepared, operation_id = _publication_operation(
        app,
        page_ref="notes/stale-publication-retry",
        crash_event="after_repository_pending",
    )
    with app.app_context():
        reconciler = app.extensions["player_wiki_reconciler"]
        original_continue_once = reconciler._continue_prepared_once

        def stale_continue(campaign, selected_operation_id, *, selected_action=None):
            current = reconciler._load_operation(selected_operation_id)
            assert current is not None
            stale = replace(
                current,
                state="prepared",
                desired_markdown=prepared.file_path.read_bytes(),
            )
            monkeypatch.setattr(reconciler, "_load_operation", lambda _operation_id: stale)
            return original_continue_once(
                campaign,
                selected_operation_id,
                selected_action=selected_action,
            )

        monkeypatch.setattr(reconciler, "_continue_prepared_once", stale_continue)
        with pytest.raises(CampaignContentError, match="no longer matches"):
            reconciler.retry_refresh_cleanup_operation(
                kind="publication", operation_id=operation_id
            )
        assert get_db().execute(
            "SELECT state FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "repository_pending"
