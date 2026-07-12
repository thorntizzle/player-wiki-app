from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from player_wiki.backup_archive import (
    DATABASE_MEMBER,
    MANIFEST_MEMBER,
    BackupArchiveError,
    canonical_json_bytes,
    create_backup_archive_v2,
    inspect_backup_archive,
)
from player_wiki.db import init_database
from player_wiki.restore_transaction import (
    RestoreHooks,
    RestoreRecoveryRequiredError,
    RestoreTamperError,
    RestoreTransactionError,
    inspect_restore_recovery,
    restore_backup_archive_atomic,
    resume_restore,
    rollback_restore,
)
from player_wiki.runtime_lease import (
    RuntimeRecoveryRequiredError,
    RuntimeStateBusyError,
    acquire_exclusive_state_lease,
    acquire_runtime_state_lease,
    active_restore_journal_path,
)


def test_restore_recovery_status_is_clean_without_journal(tmp_path):
    database = tmp_path / "active" / "wiki.sqlite3"
    database.parent.mkdir()

    status = inspect_restore_recovery(db_path=database)

    assert status.recovery_state == "clean"
    assert status.transaction_id is None
    assert status.phase is None
    assert status.recovery_origin is None
    assert status.recommended_action == "none"


def test_restore_recovery_status_uses_raw_shared_lease_and_reports_busy(tmp_path):
    database, _ = make_nonempty_target(tmp_path)

    with acquire_exclusive_state_lease(database):
        with pytest.raises(RuntimeStateBusyError):
            inspect_restore_recovery(db_path=database)


@pytest.mark.parametrize(
    ("event", "phase", "recommendation"),
    [
        ("after_journal_prepared", "prepared", "resume_or_rollback"),
        ("after_publish_database", "db_swap_intent", "resume_or_rollback"),
        ("after_cleanup", "cleanup_intent", "resume"),
    ],
)
def test_restore_recovery_status_validates_phase_evidence(
    tmp_path, event, phase, recommendation
):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, event)

    status = inspect_restore_recovery(db_path=database)

    assert status.recovery_state == "required"
    assert status.transaction_id == read_journal(database)["transaction_id"]
    assert status.phase == phase
    assert status.recovery_origin is None
    assert status.recommended_action == recommendation


def test_restore_recovery_status_recommends_rollback_for_durable_rolled_back(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore_while_rolling_back(source.archive_path, database, campaigns)

    status = inspect_restore_recovery(db_path=database)

    assert status.phase == "rolled_back"
    assert status.recommended_action == "rollback"


def test_restore_recovery_status_accepts_pre_cleanup_intent_artifacts(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(
        source.archive_path,
        database,
        campaigns,
        "after_journal_cleanup_intent",
    )

    payload = read_journal(database)
    assert Path(payload["rollback"]["database"]).exists()
    assert Path(payload["rollback"]["campaigns"]).exists()

    status = inspect_restore_recovery(db_path=database)
    assert status.phase == "cleanup_intent"
    assert status.recommended_action == "resume"

    assert resume_restore(db_path=database).outcome == "committed"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_restore_recovery_status_accepts_partial_cleanup_recovery_origin(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def fail_before_cleanup(event):
        if event == "before_cleanup":
            raise RuntimeError("interrupt cleanup")

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            hooks=RestoreHooks(fail_before_cleanup),
        )
    payload = read_journal(database)
    old_database = Path(payload["rollback"]["database"])
    old_campaigns = Path(payload["rollback"]["campaigns"])
    assert old_database.exists()
    assert old_campaigns.exists()
    shutil.rmtree(old_campaigns)

    status = inspect_restore_recovery(db_path=database)
    assert status.phase == "recovery_required"
    assert status.recovery_origin == "cleanup_intent"
    assert status.recommended_action == "resume"

    assert resume_restore(db_path=database).outcome == "committed"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


@pytest.mark.parametrize(
    ("origin", "recommendation"),
    [
        ("rollback_intent", "rollback"),
        ("prepared", "resume_or_rollback"),
    ],
)
def test_restore_recovery_status_uses_recovery_origin(tmp_path, origin, recommendation):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")
    rewrite_journal(
        database,
        lambda payload: payload.update(
            phase="recovery_required", recovery_from_phase=origin
        ),
    )

    status = inspect_restore_recovery(db_path=database)

    assert status.phase == "recovery_required"
    assert status.recovery_origin == origin
    assert status.recommended_action == recommendation


@pytest.mark.parametrize(
    ("failure_event", "origin"),
    [
        ("after_cleanup", "cleanup_intent"),
        ("after_journal_committed", "committed"),
    ],
)
def test_restore_recovery_status_validates_resume_only_recovery_origins(
    tmp_path, failure_event, origin
):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def fail(event):
        if event == failure_event:
            raise RuntimeError("injected recovery failure")

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            hooks=RestoreHooks(fail),
        )

    status = inspect_restore_recovery(db_path=database)
    assert status.phase == "recovery_required"
    assert status.recovery_origin == origin
    assert status.recommended_action == "resume"


@pytest.mark.parametrize("origin", ["rollback_intent", "rolled_back"])
def test_restore_recovery_status_validates_rollback_recovery_origins(
    tmp_path, origin
):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def fail(event):
        if event == "after_publish_database":
            raise RuntimeError("start rollback")
        if event == f"after_journal_{origin}":
            raise RuntimeError("interrupt rollback")

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            hooks=RestoreHooks(fail),
        )

    status = inspect_restore_recovery(db_path=database)
    assert status.phase == "recovery_required"
    assert status.recovery_origin == origin
    assert status.recommended_action == "rollback"


def test_restore_recovery_status_fails_closed_and_retains_tampered_journal(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")
    journal = active_restore_journal_path(database)
    journal.write_bytes(journal.read_bytes().replace(b'"prepared"', b'"verified"'))

    with pytest.raises(RestoreTamperError, match="checksum"):
        inspect_restore_recovery(db_path=database)

    assert journal.exists()


def test_restore_recovery_status_fails_closed_and_retains_artifact_tamper(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")
    journal = active_restore_journal_path(database)
    stage_database = Path(read_journal(database)["staging"]["database"])
    stage_database.write_bytes(stage_database.read_bytes() + b"tamper")

    with pytest.raises(RestoreTamperError, match="staged database"):
        inspect_restore_recovery(db_path=database)

    assert journal.exists()


def test_restore_recovery_status_validates_published_target_evidence(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_publish_database")
    journal = active_restore_journal_path(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE restore_marker SET value = 'tampered'")
        connection.commit()

    with pytest.raises(RestoreTamperError, match="published database"):
        inspect_restore_recovery(db_path=database)

    assert journal.exists()


def write_database(path: Path, value: str, *, current: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if current:
        init_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE restore_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO restore_marker VALUES (?)", (value,))
        connection.commit()


def read_database(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT value FROM restore_marker").fetchone()
    assert row is not None
    return str(row[0])


def make_archive(tmp_path: Path, *, current: bool = False):
    database = tmp_path / "source" / "wiki.sqlite3"
    campaigns = tmp_path / "source-campaigns"
    backups = tmp_path / "backups"
    write_database(database, "restored", current=current)
    (campaigns / "alpha").mkdir(parents=True)
    (campaigns / "alpha" / "page.md").write_text("restored page\n", encoding="utf-8")
    evidence = create_backup_archive_v2(
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
        archive_basename="restore-source",
        created_at="2026-07-11T12:00:00Z",
    )
    return evidence, backups


def make_nonempty_target(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "active" / "wiki.sqlite3"
    campaigns = tmp_path / "active" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    return database, campaigns


def assert_restored(database: Path, campaigns: Path) -> None:
    assert read_database(database) == "restored"
    assert (campaigns / "alpha" / "page.md").read_text(encoding="utf-8") == "restored page\n"
    assert not (campaigns / "old.md").exists()


def assert_original(database: Path, campaigns: Path) -> None:
    assert read_database(database) == "original"
    assert (campaigns / "old.md").read_text(encoding="utf-8") == "original page\n"
    assert not (campaigns / "alpha" / "page.md").exists()


def assert_transaction_clean(database: Path) -> None:
    assert not active_restore_journal_path(database).exists()
    assert not list(database.parent.glob(".*.restore-*.new"))
    assert not list(database.parent.glob(".*.restore-*.old"))


def crash_restore(archive: Path, database: Path, campaigns: Path, event: str) -> None:
    script = (
        "import os,sys; from pathlib import Path; "
        "from player_wiki.restore_transaction import RestoreHooks,restore_backup_archive_atomic; "
        "target=sys.argv[4]; "
        "hook=lambda name: os._exit(73) if name==target else None; "
        "restore_backup_archive_atomic(archive_path=Path(sys.argv[1]),db_path=Path(sys.argv[2]),"
        "campaigns_dir=Path(sys.argv[3]),hooks=RestoreHooks(hook))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(archive), str(database), str(campaigns), event],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 73, (completed.stdout, completed.stderr)


def crash_restore_while_rolling_back(
    archive: Path,
    database: Path,
    campaigns: Path,
) -> None:
    script = """
import os
import sys
from pathlib import Path
from player_wiki.restore_transaction import RestoreHooks, restore_backup_archive_atomic

def hook(name):
    if name == "after_publish_database":
        raise RuntimeError("injected failure")
    if name == "after_journal_rolled_back":
        os._exit(73)

restore_backup_archive_atomic(
    archive_path=Path(sys.argv[1]),
    db_path=Path(sys.argv[2]),
    campaigns_dir=Path(sys.argv[3]),
    hooks=RestoreHooks(hook),
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(archive), str(database), str(campaigns)],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 73, (completed.stdout, completed.stderr)


def crash_recovery(database: Path, action: str, event: str) -> None:
    script = """
import os
import sys
from pathlib import Path
from player_wiki.restore_transaction import RestoreHooks, resume_restore, rollback_restore

target = sys.argv[3]
hook = lambda name: os._exit(73) if name == target else None
operation = rollback_restore if sys.argv[2] == "rollback" else resume_restore
operation(db_path=Path(sys.argv[1]), hooks=RestoreHooks(hook))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(database), action, event],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 73, (completed.stdout, completed.stderr)


def read_journal(database: Path) -> dict[str, object]:
    return json.loads(active_restore_journal_path(database).read_bytes())


def rewrite_journal(database: Path, mutate) -> None:
    journal = active_restore_journal_path(database)
    payload = read_journal(database)
    payload.pop("journal_sha256", None)
    mutate(payload)
    payload["journal_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    journal.write_bytes(canonical_json_bytes(payload))


def run_ops_recovery(
    database: Path, campaigns: Path, command: str
) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(database)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(campaigns)
    arguments = [sys.executable, str(project_root / "ops.py"), command]
    if command != "restore-status":
        arguments.append("--yes")
    return subprocess.run(
        arguments,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize("command", ["restore-resume", "restore-rollback"])
def test_ops_recovery_cli_finishes_crash_journal(tmp_path, command):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_publish_database")

    status = run_ops_recovery(database, campaigns, "restore-status")
    assert status.returncode == 0
    assert "Recovery state: required" in status.stdout
    assert "Recommended action: resume_or_rollback" in status.stdout
    assert str(database) not in status.stdout

    recovered = run_ops_recovery(database, campaigns, command)
    assert recovered.returncode == 0, recovered.stderr
    assert f"Action: {command.removeprefix('restore-')}" in recovered.stdout
    assert "Recovery state: clean" in recovered.stdout
    if command == "restore-resume":
        assert_restored(database, campaigns)
    else:
        assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_ops_recovery_cli_cleanup_is_resume_only(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_cleanup")

    status = run_ops_recovery(database, campaigns, "restore-status")
    assert status.returncode == 0
    assert "Phase: cleanup_intent" in status.stdout
    assert "Recommended action: resume" in status.stdout

    rejected = run_ops_recovery(database, campaigns, "restore-rollback")
    assert rejected.returncode != 0
    assert active_restore_journal_path(database).exists()

    resumed = run_ops_recovery(database, campaigns, "restore-resume")
    assert resumed.returncode == 0, resumed.stderr
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_ops_recovery_cli_finalizes_durable_rolled_back(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore_while_rolling_back(source.archive_path, database, campaigns)

    status = run_ops_recovery(database, campaigns, "restore-status")
    assert status.returncode == 0
    assert "Phase: rolled_back" in status.stdout
    assert "Recommended action: rollback" in status.stdout

    finalized = run_ops_recovery(database, campaigns, "restore-rollback")
    assert finalized.returncode == 0, finalized.stderr
    assert "Outcome: rolled_back" in finalized.stdout
    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_nonempty_restore_creates_and_reinspects_mandatory_prebackup(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    result = restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
    )

    assert_restored(database, campaigns)
    assert result.outcome == "committed"
    assert result.recovery_state == "clean"
    assert result.prebackup_evidence is not None
    assert result.migration_required is True
    inspected = inspect_backup_archive(result.prebackup_evidence.archive_path)
    assert inspected == result.prebackup_evidence
    assert inspected.format_version == 2
    assert_transaction_clean(database)


def test_empty_target_restore_does_not_create_prebackup(tmp_path):
    source, backups = make_archive(tmp_path)
    database = tmp_path / "empty" / "wiki.sqlite3"
    campaigns = tmp_path / "empty" / "campaigns"
    before = set(backups.glob("*.zip"))

    result = restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
    )

    assert_restored(database, campaigns)
    assert result.prebackup_evidence is None
    assert set(backups.glob("*.zip")) == before
    assert_transaction_clean(database)


def test_current_migration_ledger_is_preserved_as_current_evidence(tmp_path):
    source, backups = make_archive(tmp_path, current=True)
    database = tmp_path / "active" / "wiki.sqlite3"
    campaigns = tmp_path / "active" / "campaigns"

    result = restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
    )

    assert result.database_verification.migration.is_current is True
    assert result.migration_required is False


def test_shared_runtime_lease_blocks_restore_without_target_mutation(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    with acquire_runtime_state_lease(database):
        with pytest.raises(RuntimeStateBusyError):
            restore_backup_archive_atomic(
                archive_path=source.archive_path,
                db_path=database,
                campaigns_dir=campaigns,
                backup_root=backups,
            )

    assert_original(database, campaigns)
    assert len(list(backups.glob("*.zip"))) == 1


def test_preexisting_journal_requires_explicit_recovery_without_mutation(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    journal = active_restore_journal_path(database)
    journal.write_text("{}\n", encoding="utf-8")

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
        )

    assert_original(database, campaigns)
    assert len(list(backups.glob("*.zip"))) == 1
    assert journal.read_text(encoding="utf-8") == "{}\n"


def test_normal_failure_after_database_publish_rolls_back_and_keeps_prebackup(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def fail_after_database(event: str) -> None:
        if event == "after_publish_database":
            raise RuntimeError("injected failure")

    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_after_database),
        )

    assert_original(database, campaigns)
    assert len(list(backups.glob("*.zip"))) == 2
    assert_transaction_clean(database)


def test_crash_after_database_publish_can_resume_idempotently(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    crash_restore(source.archive_path, database, campaigns, "after_publish_database")

    assert active_restore_journal_path(database).exists()
    with pytest.raises(RuntimeRecoveryRequiredError):
        acquire_runtime_state_lease(database)
    recovered = resume_restore(db_path=database)
    assert recovered.outcome == "committed"
    assert resume_restore(db_path=database).outcome == "no_active_transaction"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_crash_after_database_publish_can_roll_back_idempotently(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    crash_restore(source.archive_path, database, campaigns, "after_publish_database")

    recovered = rollback_restore(db_path=database)
    assert recovered.outcome == "rolled_back"
    assert rollback_restore(db_path=database).outcome == "no_active_transaction"
    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_crash_after_durable_rolled_back_phase_finishes_rollback_idempotently(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    crash_restore_while_rolling_back(source.archive_path, database, campaigns)

    journal = active_restore_journal_path(database)
    assert journal.exists()
    assert read_journal(database)["phase"] == "rolled_back"
    assert_original(database, campaigns)
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()

    recovered = rollback_restore(db_path=database)
    assert recovered.outcome == "rolled_back"
    assert recovered.recovery_state == "clean"
    assert rollback_restore(db_path=database).outcome == "no_active_transaction"
    assert_original(database, campaigns)
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()
    assert_transaction_clean(database)


@pytest.mark.parametrize(
    "event",
    [
        "after_journal_prepared",
        "after_rename_old_wiki.sqlite3",
        "after_rename_old_campaigns",
        "after_publish_campaigns",
        "after_journal_verified",
    ],
)
def test_durable_phase_crashes_resume_to_verified_new_state(tmp_path, event):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    crash_restore(source.archive_path, database, campaigns, event)

    assert active_restore_journal_path(database).exists()
    assert resume_restore(db_path=database).outcome == "committed"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


@pytest.mark.parametrize(
    "event",
    [
        "after_journal_prepared",
        "after_rename_old_wiki.sqlite3",
        "after_rename_old_campaigns",
        "after_publish_campaigns",
        "after_journal_verified",
    ],
)
def test_durable_phase_crashes_roll_back_to_verified_old_state(tmp_path, event):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    crash_restore(source.archive_path, database, campaigns, event)

    assert rollback_restore(db_path=database).outcome == "rolled_back"
    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_crash_after_cleanup_can_resume_but_cannot_claim_rollback(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_cleanup")

    with pytest.raises(RestoreTransactionError, match="resume"):
        rollback_restore(db_path=database)
    assert active_restore_journal_path(database).exists()
    assert resume_restore(db_path=database).outcome == "committed"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_tampered_journal_fails_closed_and_remains_for_operator(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_publish_database")
    journal = active_restore_journal_path(database)
    payload = json.loads(journal.read_bytes())
    payload["phase"] = "verified"
    journal.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(RestoreTamperError, match="checksum"):
        resume_restore(db_path=database)

    assert journal.exists()


@pytest.mark.parametrize(
    ("event", "artifact"),
    [
        ("after_journal_prepared", "archive"),
        ("after_journal_prepared", "prebackup"),
        ("after_journal_prepared", "stage_database"),
        ("after_journal_prepared", "stage_campaign"),
        ("after_publish_database", "old_database"),
        ("after_publish_campaigns", "old_campaign"),
    ],
)
def test_tampered_recovery_artifacts_fail_closed(tmp_path, event, artifact):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, event)
    payload = read_journal(database)

    if artifact == "archive":
        path = Path(payload["archive"]["path"])
    elif artifact == "prebackup":
        path = Path(payload["prebackup"]["file"]["path"])
    elif artifact == "stage_database":
        path = Path(payload["staging"]["database"])
    elif artifact == "stage_campaign":
        path = Path(payload["staging"]["campaigns"]) / "alpha" / "page.md"
    elif artifact == "old_database":
        path = Path(payload["rollback"]["database"])
    else:
        path = Path(payload["rollback"]["campaigns"]) / "old.md"
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(RestoreTamperError):
        resume_restore(db_path=database)
    assert active_restore_journal_path(database).exists()


@pytest.mark.parametrize("artifact", ["stage_database", "stage_campaign"])
def test_hardlinked_recovery_artifact_identity_fails_closed(tmp_path, artifact):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")
    payload = read_journal(database)
    if artifact == "stage_database":
        path = Path(payload["staging"]["database"])
    else:
        path = Path(payload["staging"]["campaigns"]) / "alpha" / "page.md"
    os.link(path, path.parent / f"{path.name}.alias")

    with pytest.raises(RestoreTamperError):
        resume_restore(db_path=database)
    assert active_restore_journal_path(database).exists()


@pytest.mark.parametrize(
    ("event", "artifact"),
    [
        ("after_journal_prepared", "stage_database"),
        ("after_journal_prepared", "stage_campaign"),
        ("after_publish_database", "old_database"),
        ("after_publish_campaigns", "old_campaign"),
    ],
)
def test_explicit_rollback_refuses_tampered_transaction_artifacts(
    tmp_path, event, artifact
):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, event)
    payload = read_journal(database)
    if artifact == "stage_database":
        path = Path(payload["staging"]["database"])
    elif artifact == "stage_campaign":
        path = Path(payload["staging"]["campaigns"]) / "alpha" / "page.md"
    elif artifact == "old_database":
        path = Path(payload["rollback"]["database"])
    else:
        path = Path(payload["rollback"]["campaigns"]) / "old.md"
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(RestoreTamperError):
        rollback_restore(db_path=database)
    assert active_restore_journal_path(database).exists()


def test_busy_sqlite_writer_fails_before_publication_and_keeps_old_state(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    with sqlite3.connect(database, timeout=0) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("UPDATE restore_marker SET value = 'uncommitted'")
        with pytest.raises((BackupArchiveError, RestoreTransactionError)):
            restore_backup_archive_atomic(
                archive_path=source.archive_path,
                db_path=database,
                campaigns_dir=campaigns,
                backup_root=backups,
            )
        writer.rollback()

    assert_original(database, campaigns)
    assert not active_restore_journal_path(database).exists()


def test_campaign_tamper_after_publish_fails_verification_and_rolls_back(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def tamper(event: str) -> None:
        if event == "after_publish_campaigns":
            (campaigns / "alpha" / "page.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(tamper),
        )

    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_enospc_during_staging_fails_before_journal_and_preserves_targets(tmp_path, monkeypatch):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def no_space(_path):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("player_wiki.restore_transaction._sync_file", no_space)
    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
        )
    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_enospc_during_first_journal_fsync_preserves_targets_and_prebackup(tmp_path, monkeypatch):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    real_sync = __import__("player_wiki.restore_transaction", fromlist=["_sync_file"])._sync_file

    def fail_journal(path: Path):
        if ".restore-journal.json." in path.name:
            raise OSError(28, "No space left on device")
        return real_sync(path)

    monkeypatch.setattr("player_wiki.restore_transaction._sync_file", fail_journal)
    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
        )
    assert_original(database, campaigns)
    assert len(list(backups.glob("*.zip"))) == 2
    assert_transaction_clean(database)


def test_single_publication_directory_fsync_failure_rolls_back(tmp_path, monkeypatch):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_directory"])
    real_sync = module._sync_directory
    armed = False

    def arm_failure(event: str) -> None:
        nonlocal armed
        if event == "after_publish_database":
            armed = True

    def fail_once(path: Path):
        nonlocal armed
        if armed and path == database.parent:
            armed = False
            raise OSError(28, "No space left on device")
        return real_sync(path)

    monkeypatch.setattr("player_wiki.restore_transaction._sync_directory", fail_once)
    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(arm_failure),
        )
    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_cleanup_failure_requires_explicit_resume(tmp_path):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def fail_cleanup(event: str) -> None:
        if event == "before_cleanup":
            raise OSError(28, "No space left on device")

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_cleanup),
        )
    assert active_restore_journal_path(database).exists()
    assert resume_restore(db_path=database).outcome == "committed"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


@pytest.mark.parametrize("target", ["database", "campaign"])
def test_target_change_after_mandatory_prebackup_aborts_before_journal(
    tmp_path, target
):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)

    def mutate_after_prebackup(event: str) -> None:
        if event != "after_prebackup":
            return
        if target == "database":
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("UPDATE restore_marker SET value = 'raced'")
                connection.commit()
        else:
            (campaigns / "old.md").write_text("raced campaign\n", encoding="utf-8")

    with pytest.raises(RestoreTamperError, match="prebackup|campaign"):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(mutate_after_prebackup),
        )

    assert not active_restore_journal_path(database).exists()
    assert not list(database.parent.glob(".*.restore-*.new"))
    assert len(list(backups.glob("*.zip"))) == 2
    assert read_database(database) != "restored"


def test_prebackup_captures_committed_wal_only_state(tmp_path):
    source, backups = make_archive(tmp_path / "source-archive")
    database = tmp_path / "active" / "wiki.sqlite3"
    campaigns = tmp_path / "active" / "campaigns"
    database.parent.mkdir(parents=True)
    campaigns.mkdir()
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    script = (
        "import os,sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
        "c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0'); "
        "c.execute('CREATE TABLE restore_marker(value TEXT NOT NULL)'); c.commit(); "
        "c.execute(\"INSERT INTO restore_marker VALUES ('wal-original')\"); c.commit(); os._exit(0)"
    )
    completed = subprocess.run([sys.executable, "-c", script, str(database)], check=False)
    assert completed.returncode == 0
    assert Path(f"{database}-wal").exists()

    result = restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
    )

    assert result.prebackup_evidence is not None
    from player_wiki.backup_archive import stage_backup_archive

    with stage_backup_archive(result.prebackup_evidence.archive_path) as staged:
        assert read_database(staged.database_path) == "wal-original"
    assert_restored(database, campaigns)


@pytest.mark.parametrize("current", [False, True])
def test_legacy_v1_restore_reports_derived_migration_requirement(tmp_path, current):
    source_db = tmp_path / "legacy-source.sqlite3"
    write_database(source_db, "restored", current=current)
    archive = tmp_path / "legacy.zip"
    manifest = {
        "format_version": 1,
        "created_at": "2026-07-10T12:00:00Z",
        "database_filename": "player_wiki.sqlite3",
        "campaigns_dir_name": "campaigns",
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(MANIFEST_MEMBER, json.dumps(manifest).encode())
        package.writestr(DATABASE_MEMBER, source_db.read_bytes())
        package.writestr("campaigns/alpha/page.md", b"restored page\n")
    database = tmp_path / "active" / "wiki.sqlite3"
    campaigns = tmp_path / "active" / "campaigns"

    result = restore_backup_archive_atomic(
        archive_path=archive,
        db_path=database,
        campaigns_dir=campaigns,
    )

    assert result.evidence.format_version == 1
    assert result.migration_required is (not current)
    assert_restored(database, campaigns)


def test_archive_hardlink_and_overlapping_storage_are_rejected(tmp_path):
    source, _ = make_archive(tmp_path)
    hardlink = tmp_path / "linked.zip"
    os.link(source.archive_path, hardlink)
    database, campaigns = make_nonempty_target(tmp_path)

    with pytest.raises(RestoreTransactionError, match="unsafe"):
        restore_backup_archive_atomic(
            archive_path=hardlink,
            db_path=database,
            campaigns_dir=campaigns,
        )
    hardlink.unlink()
    with pytest.raises(RestoreTransactionError, match="overlap"):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=campaigns,
        )
    assert_original(database, campaigns)


def test_archive_and_target_symlink_aliases_are_rejected_before_mutation(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    archive_alias = tmp_path / "archive-alias.zip"
    database_alias = tmp_path / "database-alias.sqlite3"
    try:
        archive_alias.symlink_to(source.archive_path)
        database_alias.symlink_to(database)
    except OSError:
        pytest.skip("This filesystem does not permit test symlinks.")

    with pytest.raises(RestoreTransactionError, match="unsafe"):
        restore_backup_archive_atomic(
            archive_path=archive_alias,
            db_path=database,
            campaigns_dir=campaigns,
        )
    with pytest.raises(RestoreTransactionError, match="unsafe"):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database_alias,
            campaigns_dir=campaigns,
        )
    assert_original(database, campaigns)


def test_all_atomic_replacements_stay_within_one_parent_directory(tmp_path, monkeypatch):
    source, backups = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def checked_replace(source_path, destination_path):
        source_value = Path(source_path).resolve(strict=False)
        destination_value = Path(destination_path).resolve(strict=False)
        replacements.append((source_value, destination_value))
        assert source_value.parent == destination_value.parent
        return real_replace(source_path, destination_path)

    monkeypatch.setattr("player_wiki.restore_transaction.os.replace", checked_replace)
    restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
    )

    assert replacements
    assert_restored(database, campaigns)


def test_staged_campaign_parent_is_synced_before_prepared_journal(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    assert database.parent != campaigns.parent

    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_tree"])
    real_sync_tree = module._sync_tree
    real_sync_directory = module._sync_directory
    ordering: list[str] = []

    def record_tree(root: Path) -> None:
        if root.parent == campaigns.parent and ".restore-" in root.name:
            ordering.append("stage_tree")
        real_sync_tree(root)

    def record_directory(path: Path) -> None:
        if path == campaigns.parent:
            ordering.append("campaign_parent")
        real_sync_directory(path)

    def record_journal(event: str) -> None:
        if event == "before_journal_prepared":
            ordering.append("prepared_journal")

    monkeypatch.setattr("player_wiki.restore_transaction._sync_tree", record_tree)
    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        record_directory,
    )

    restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
        hooks=RestoreHooks(record_journal),
    )

    assert ordering[:3] == ["stage_tree", "campaign_parent", "prepared_journal"]
    assert_restored(database, campaigns)


def test_empty_target_rollback_syncs_removed_artifact_parents_before_rolled_back(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    database.parent.mkdir(parents=True)
    campaigns.parent.mkdir(parents=True)
    assert database.parent != campaigns.parent

    module = __import__("player_wiki.restore_transaction", fromlist=["_remove_path"])
    real_remove = module._remove_path
    real_sync_directory = module._sync_directory
    ordering: list[tuple[str, Path | None]] = []
    rollback_started = False
    target_bundle = {database, Path(f"{database}-wal"), Path(f"{database}-shm"), campaigns}

    def record_remove(path: Path) -> None:
        if (
            rollback_started
            and os.path.lexists(path)
            and (path in target_bundle or path.name.endswith((".new", ".old")))
        ):
            ordering.append(("remove", path.parent))
        real_remove(path)

    def record_sync(path: Path) -> None:
        if rollback_started:
            ordering.append(("sync", path))
        real_sync_directory(path)

    def fail_and_record(event: str) -> None:
        nonlocal rollback_started
        if event == "after_publish_database":
            raise RuntimeError("injected failure")
        if event == "after_journal_rollback_intent":
            rollback_started = True
        if event == "before_journal_rolled_back":
            ordering.append(("rolled_back", None))

    monkeypatch.setattr("player_wiki.restore_transaction._remove_path", record_remove)
    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        record_sync,
    )

    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_and_record),
        )

    rolled_back_index = ordering.index(("rolled_back", None))
    for parent in (database.parent, campaigns.parent):
        removal_indices = [
            index
            for index, event in enumerate(ordering)
            if event == ("remove", parent)
        ]
        sync_index = ordering.index(("sync", parent))
        assert removal_indices
        assert max(removal_indices) < sync_index < rolled_back_index
    assert not database.exists()
    assert not campaigns.exists()
    assert_transaction_clean(database)


def test_successful_cleanup_syncs_removed_artifact_parents_before_committed(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    assert database.parent != campaigns.parent

    module = __import__("player_wiki.restore_transaction", fromlist=["_remove_path"])
    real_remove = module._remove_path
    real_sync_directory = module._sync_directory
    ordering: list[tuple[str, Path | None]] = []
    cleanup_started = False

    def record_remove(path: Path) -> None:
        if (
            cleanup_started
            and os.path.lexists(path)
            and path.name.endswith((".new", ".old"))
        ):
            ordering.append(("remove", path.parent))
        real_remove(path)

    def record_sync(path: Path) -> None:
        if cleanup_started:
            ordering.append(("sync", path))
        real_sync_directory(path)

    def record_cleanup(event: str) -> None:
        nonlocal cleanup_started
        if event == "after_journal_cleanup_intent":
            cleanup_started = True
        if event == "before_journal_committed":
            ordering.append(("committed", None))

    monkeypatch.setattr("player_wiki.restore_transaction._remove_path", record_remove)
    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        record_sync,
    )

    restore_backup_archive_atomic(
        archive_path=source.archive_path,
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
        hooks=RestoreHooks(record_cleanup),
    )

    committed_index = ordering.index(("committed", None))
    for parent in (database.parent, campaigns.parent):
        removal_indices = [
            index
            for index, event in enumerate(ordering)
            if event == ("remove", parent)
        ]
        sync_index = ordering.index(("sync", parent))
        assert removal_indices
        assert max(removal_indices) < sync_index < committed_index
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_rollback_parent_sync_failure_is_retried_after_artifact_removal(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    database.parent.mkdir(parents=True)
    campaigns.parent.mkdir(parents=True)
    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_directory"])
    real_sync_directory = module._sync_directory
    rollback_started = False
    fail_once = True

    def fail_campaign_parent_once(path: Path) -> None:
        nonlocal fail_once
        if rollback_started and fail_once and path == campaigns.parent:
            fail_once = False
            raise OSError(5, "injected directory sync failure")
        real_sync_directory(path)

    def fail_restore(event: str) -> None:
        nonlocal rollback_started
        if event == "after_publish_database":
            raise RuntimeError("injected publication failure")
        if event == "after_journal_rollback_intent":
            rollback_started = True

    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        fail_campaign_parent_once,
    )

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_restore),
        )

    assert rollback_restore(db_path=database).outcome == "rolled_back"
    assert not database.exists()
    assert not campaigns.exists()
    assert_transaction_clean(database)


def test_cleanup_parent_sync_failure_is_retried_after_artifact_removal(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_directory"])
    real_sync_directory = module._sync_directory
    cleanup_started = False
    fail_once = True

    def fail_campaign_parent_once(path: Path) -> None:
        nonlocal fail_once
        if cleanup_started and fail_once and path == campaigns.parent:
            fail_once = False
            raise OSError(5, "injected directory sync failure")
        real_sync_directory(path)

    def record_cleanup(event: str) -> None:
        nonlocal cleanup_started
        if event == "after_journal_cleanup_intent":
            cleanup_started = True

    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        fail_campaign_parent_once,
    )

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(record_cleanup),
        )

    assert resume_restore(db_path=database).outcome == "committed"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_existing_target_rollback_parent_sync_failure_retries_active_originals(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_directory"])
    real_sync_directory = module._sync_directory
    rollback_started = False
    fail_once = True

    def fail_campaign_parent_once(path: Path) -> None:
        nonlocal fail_once
        if rollback_started and fail_once and path == campaigns.parent:
            fail_once = False
            raise OSError(5, "injected directory sync failure")
        real_sync_directory(path)

    def fail_restore(event: str) -> None:
        nonlocal rollback_started
        if event == "after_publish_database":
            raise RuntimeError("injected publication failure")
        if event == "after_journal_rollback_intent":
            rollback_started = True

    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        fail_campaign_parent_once,
    )
    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_restore),
        )

    assert read_journal(database)["recovery_from_phase"] == "rollback_intent"
    assert_original(database, campaigns)
    assert rollback_restore(db_path=database).outcome == "rolled_back"
    assert rollback_restore(db_path=database).outcome == "no_active_transaction"
    assert_original(database, campaigns)
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()
    assert_transaction_clean(database)


@pytest.mark.parametrize("tamper", ["database", "campaigns"])
def test_existing_target_rollback_retry_rejects_tampered_active_originals(
    tmp_path,
    monkeypatch,
    tamper,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_directory"])
    real_sync_directory = module._sync_directory
    rollback_started = False
    fail_once = True

    def fail_campaign_parent_once(path: Path) -> None:
        nonlocal fail_once
        if rollback_started and fail_once and path == campaigns.parent:
            fail_once = False
            raise OSError(5, "injected directory sync failure")
        real_sync_directory(path)

    def fail_restore(event: str) -> None:
        nonlocal rollback_started
        if event == "after_publish_database":
            raise RuntimeError("injected publication failure")
        if event == "after_journal_rollback_intent":
            rollback_started = True

    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        fail_campaign_parent_once,
    )
    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_restore),
        )

    if tamper == "database":
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("UPDATE restore_marker SET value = 'tampered'")
            connection.commit()
    else:
        (campaigns / "old.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(RestoreTamperError):
        rollback_restore(db_path=database)
    assert active_restore_journal_path(database).exists()


def test_inconsistent_recovery_origin_is_rejected_before_mutation(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")

    def forge(payload: dict[str, object]) -> None:
        payload["phase"] = "db_swap_intent"
        payload["recovery_from_phase"] = "cleanup_intent"

    rewrite_journal(database, forge)
    with pytest.raises(RestoreTamperError, match="origin"):
        rollback_restore(db_path=database)
    assert_original(database, campaigns)
    assert active_restore_journal_path(database).exists()


@pytest.mark.parametrize(
    "origin",
    [None, 3, "invalid", "recovery_required"],
)
def test_recovery_required_rejects_invalid_origin(tmp_path, origin):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")

    def forge(payload: dict[str, object]) -> None:
        payload["phase"] = "recovery_required"
        payload["recovery_from_phase"] = origin

    rewrite_journal(database, forge)
    with pytest.raises(RestoreTamperError, match="origin"):
        resume_restore(db_path=database)
    assert_original(database, campaigns)
    assert active_restore_journal_path(database).exists()


def test_recovery_required_requires_origin(tmp_path):
    source, _ = make_archive(tmp_path)
    database, campaigns = make_nonempty_target(tmp_path)
    crash_restore(source.archive_path, database, campaigns, "after_journal_prepared")

    def forge(payload: dict[str, object]) -> None:
        payload["phase"] = "recovery_required"
        payload.pop("recovery_from_phase", None)

    rewrite_journal(database, forge)
    with pytest.raises(RestoreTamperError, match="origin"):
        resume_restore(db_path=database)
    assert_original(database, campaigns)
    assert active_restore_journal_path(database).exists()


def test_prepared_artifact_cleanup_syncs_distinct_parents_without_journal(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    module = __import__("player_wiki.restore_transaction", fromlist=["_remove_path"])
    real_remove = module._remove_path
    real_sync_directory = module._sync_directory
    ordering: list[tuple[str, Path]] = []
    cleanup_started = False

    def record_remove(path: Path) -> None:
        if cleanup_started and os.path.lexists(path) and path.name.endswith(".new"):
            ordering.append(("remove", path.parent))
        real_remove(path)

    def record_sync(path: Path) -> None:
        if cleanup_started:
            ordering.append(("sync", path))
        real_sync_directory(path)

    def fail_before_journal(event: str) -> None:
        nonlocal cleanup_started
        if event == "before_journal_prepared":
            cleanup_started = True
            raise RuntimeError("injected pre-journal failure")

    monkeypatch.setattr("player_wiki.restore_transaction._remove_path", record_remove)
    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        record_sync,
    )
    with pytest.raises(RestoreTransactionError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_before_journal),
        )

    for parent in (database.parent, campaigns.parent):
        remove_index = ordering.index(("remove", parent))
        sync_index = ordering.index(("sync", parent))
        assert remove_index < sync_index
    assert not active_restore_journal_path(database).exists()
    assert_original(database, campaigns)
    assert_transaction_clean(database)


def test_rollback_retry_crash_clears_recovery_origin_and_retries_idempotently(
    tmp_path,
    monkeypatch,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")
    module = __import__("player_wiki.restore_transaction", fromlist=["_sync_directory"])
    real_sync_directory = module._sync_directory
    rollback_started = False
    fail_once = True

    def fail_campaign_parent_once(path: Path) -> None:
        nonlocal fail_once
        if rollback_started and fail_once and path == campaigns.parent:
            fail_once = False
            raise OSError(5, "injected directory sync failure")
        real_sync_directory(path)

    def fail_restore(event: str) -> None:
        nonlocal rollback_started
        if event == "after_publish_database":
            raise RuntimeError("injected publication failure")
        if event == "after_journal_rollback_intent":
            rollback_started = True

    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        fail_campaign_parent_once,
    )
    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_restore),
        )
    monkeypatch.setattr(
        "player_wiki.restore_transaction._sync_directory",
        real_sync_directory,
    )
    assert read_journal(database)["phase"] == "recovery_required"

    crash_recovery(database, "rollback", "after_journal_rollback_intent")

    journal = read_journal(database)
    assert journal["phase"] == "rollback_intent"
    assert "recovery_from_phase" not in journal

    def fail_retry(event: str) -> None:
        if event == "after_journal_rollback_intent":
            raise RuntimeError("injected retry failure")

    with pytest.raises(RestoreRecoveryRequiredError):
        rollback_restore(db_path=database, hooks=RestoreHooks(fail_retry))
    remarked = read_journal(database)
    assert remarked["phase"] == "recovery_required"
    assert remarked["recovery_from_phase"] == "rollback_intent"

    assert rollback_restore(db_path=database).outcome == "rolled_back"
    assert rollback_restore(db_path=database).outcome == "no_active_transaction"
    assert_original(database, campaigns)
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()
    assert_transaction_clean(database)


def test_resume_retry_crash_clears_recovery_origin_and_retries_idempotently(
    tmp_path,
):
    source, backups = make_archive(tmp_path / "source")
    database = tmp_path / "database-parent" / "wiki.sqlite3"
    campaigns = tmp_path / "campaign-parent" / "campaigns"
    write_database(database, "original")
    campaigns.mkdir(parents=True)
    (campaigns / "old.md").write_text("original page\n", encoding="utf-8")

    def fail_cleanup(event: str) -> None:
        if event == "before_cleanup":
            raise OSError(5, "injected cleanup failure")

    with pytest.raises(RestoreRecoveryRequiredError):
        restore_backup_archive_atomic(
            archive_path=source.archive_path,
            db_path=database,
            campaigns_dir=campaigns,
            backup_root=backups,
            hooks=RestoreHooks(fail_cleanup),
        )
    recovery = read_journal(database)
    assert recovery["phase"] == "recovery_required"
    assert recovery["recovery_from_phase"] == "cleanup_intent"

    crash_recovery(database, "resume", "after_journal_db_swap_intent")

    journal = read_journal(database)
    assert journal["phase"] == "db_swap_intent"
    assert "recovery_from_phase" not in journal
    assert resume_restore(db_path=database).outcome == "committed"
    assert resume_restore(db_path=database).outcome == "no_active_transaction"
    assert_restored(database, campaigns)
    assert_transaction_clean(database)


def test_invalid_archive_leaves_database_and_campaigns_byte_identical(tmp_path):
    database, campaigns = make_nonempty_target(tmp_path)
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not a zip")
    before_db = hashlib.sha256(database.read_bytes()).hexdigest()
    before_campaign = (campaigns / "old.md").read_bytes()

    with pytest.raises(BackupArchiveError):
        restore_backup_archive_atomic(
            archive_path=invalid,
            db_path=database,
            campaigns_dir=campaigns,
        )

    assert hashlib.sha256(database.read_bytes()).hexdigest() == before_db
    assert (campaigns / "old.md").read_bytes() == before_campaign
    assert not active_restore_journal_path(database).exists()


def test_missing_archive_error_does_not_disclose_target_path(tmp_path):
    missing = tmp_path / "private" / "secret-name.zip"

    with pytest.raises(FileNotFoundError) as captured:
        restore_backup_archive_atomic(
            archive_path=missing,
            db_path=tmp_path / "active" / "wiki.sqlite3",
            campaigns_dir=tmp_path / "active" / "campaigns",
        )

    assert str(missing) not in str(captured.value)
    assert str(captured.value) == "Backup archive not found."
