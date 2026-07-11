from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import unicodedata
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from .backup_archive import (
    DEFAULT_LIMITS,
    BackupArchiveEvidence,
    BackupArchiveError,
    BackupArchiveLimits,
    CampaignFileEvidence,
    MigrationEvidence,
    canonical_json_bytes,
    create_backup_archive_v2,
    stage_backup_archive,
)
from .migrations import MigrationError, inspect_migration_ledger
from .runtime_lease import (
    RuntimeStateBusyError,
    acquire_exclusive_state_lease,
    active_restore_journal_path,
)
from .sqlite_safety import snapshot_sqlite_database


JOURNAL_VERSION = 1
PHASES = (
    "prepared",
    "db_swap_intent",
    "db_published",
    "campaign_swap_intent",
    "campaigns_published",
    "verifying",
    "verified",
    "cleanup_intent",
    "committed",
    "rollback_intent",
    "rolled_back",
    "recovery_required",
)
RECOVERY_ORIGIN_PHASES = frozenset(PHASES) - {"recovery_required"}


class RestoreTransactionError(RuntimeError):
    """Raised when local restore cannot complete safely."""


class RestoreTamperError(RestoreTransactionError):
    """Raised when durable recovery artifacts no longer match evidence."""


class RestoreRecoveryRequiredError(RestoreTransactionError):
    """Raised when explicit resume or rollback is required."""


@dataclass(frozen=True, slots=True)
class RestoreHooks:
    on_event: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class DatabaseRestoreEvidence:
    byte_count: int
    sha256: str
    integrity_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[object, ...], ...]
    migration: MigrationEvidence


@dataclass(frozen=True, slots=True)
class CampaignRestoreEvidence:
    file_count: int
    total_bytes: int
    files: tuple[CampaignFileEvidence, ...]
    hashes_verified: bool


@dataclass(frozen=True, slots=True)
class RestoreResult:
    archive_path: Path
    restored_campaign_files: int
    database_path: Path
    evidence: BackupArchiveEvidence
    transaction_id: str
    action: str
    outcome: str
    recovery_state: str
    prebackup_evidence: BackupArchiveEvidence | None
    database_verification: DatabaseRestoreEvidence
    campaign_verification: CampaignRestoreEvidence
    migration_required: bool


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    transaction_id: str | None
    action: str
    outcome: str
    recovery_state: str


def restore_backup_archive_atomic(
    *,
    archive_path: Path,
    db_path: Path,
    campaigns_dir: Path,
    backup_root: Path | None = None,
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
    hooks: RestoreHooks | None = None,
) -> RestoreResult:
    hooks = hooks or RestoreHooks()
    try:
        archive = _canonical_regular_file(archive_path, require_single_link=True)
        initial_archive = _file_record(archive)
        with stage_backup_archive(archive, limits=limits):
            pass
    except FileNotFoundError:
        raise FileNotFoundError("Backup archive not found.") from None
    except (BackupArchiveError, RestoreTransactionError):
        raise
    except (OSError, RuntimeError):
        raise RestoreTransactionError("The restore archive is unavailable.") from None

    database = _safe_target_path(db_path)
    campaigns = _safe_target_path(campaigns_dir)
    for parent in {database.parent, campaigns.parent}:
        if not parent.exists():
            _validate_path_chain(parent.parent, require_existing=True)
            try:
                parent.mkdir()
            except OSError:
                raise RestoreTransactionError(
                    "The restore target parent is unavailable."
                ) from None
    journal = active_restore_journal_path(database)
    state: dict[str, object] | None = None
    prepared_paths: list[Path] = []

    try:
        with acquire_exclusive_state_lease(database):
            if os.path.lexists(journal):
                raise RestoreRecoveryRequiredError(
                    "An unfinished restore requires explicit resume or rollback."
                )
            if _file_record(archive) != initial_archive:
                raise RestoreTamperError("The restore archive changed during validation.")
            _validate_restore_boundaries(
                archive=archive,
                database=database,
                campaigns=campaigns,
                backup_root=backup_root,
                journal=journal,
            )

            with stage_backup_archive(archive, limits=limits) as staged:
                transaction_id = uuid.uuid4().hex
                stage_db = database.parent / f".{database.name}.restore-{transaction_id}.new"
                stage_campaigns = campaigns.parent / f".{campaigns.name}.restore-{transaction_id}.new"
                old_db = database.parent / f".{database.name}.restore-{transaction_id}.old"
                old_campaigns = campaigns.parent / f".{campaigns.name}.restore-{transaction_id}.old"
                for candidate in (stage_db, stage_campaigns, old_db, old_campaigns):
                    if os.path.lexists(candidate):
                        raise RestoreTransactionError("A restore staging name is unavailable.")
                    prepared_paths.append(candidate)

                _event(hooks, "before_stage_database")
                shutil.copy2(staged.database_path, stage_db)
                _sync_file(stage_db)
                _event(hooks, "after_stage_database")
                _copy_campaign_tree(staged.campaigns_dir, stage_campaigns)
                _sync_tree(stage_campaigns)
                _sync_directory(stage_campaigns.parent)
                _event(hooks, "after_stage_campaigns")
                staged_database = _database_evidence(stage_db)
                if (
                    staged_database.byte_count != staged.evidence.database_byte_count
                    or staged_database.sha256 != staged.evidence.database_sha256
                    or staged_database.migration != staged.evidence.migration
                ):
                    raise RestoreTamperError("The staged database evidence does not match.")
                staged_campaigns_evidence = _verify_campaign_tree(
                    stage_campaigns,
                    staged.campaign_files,
                )

                target_campaign_files = _scan_regular_tree(campaigns) if campaigns.exists() else ()
                target_nonempty = database.exists() or bool(target_campaign_files)
                if not database.exists() and target_campaign_files:
                    raise RestoreTransactionError("The active restore targets are inconsistent.")

                prebackup: BackupArchiveEvidence | None = None
                if target_nonempty:
                    destination = (
                        Path(backup_root).expanduser().resolve(strict=False)
                        if backup_root is not None
                        else archive.parent
                    )
                    _event(hooks, "before_prebackup")
                    prebackup = _create_prebackup(
                        database=database,
                        campaigns=campaigns,
                        backup_root=destination,
                        transaction_id=transaction_id,
                        limits=limits,
                    )
                    precheck = (
                        database.parent
                        / f".{database.name}.restore-{transaction_id}.precheck"
                    )
                    prepared_paths.append(precheck)
                    with stage_backup_archive(
                        prebackup.archive_path, limits=limits
                    ) as staged_prebackup:
                        _event(hooks, "after_prebackup")
                        _quiesce_database(database)
                        _verify_prebackup_matches_targets(
                            database=database,
                            campaigns=campaigns,
                            staged_database=staged_prebackup.database_path,
                            staged_campaign_files=staged_prebackup.campaign_files,
                            snapshot_path=precheck,
                        )
                    _remove_path(precheck)
                    target_campaign_files = (
                        _scan_regular_tree(campaigns) if campaigns.exists() else ()
                    )
                else:
                    _quiesce_database(database)
                original_db_bundle = _db_bundle_records(database)
                original_campaigns = (
                    _campaign_records(target_campaign_files) if campaigns.exists() else []
                )
                state = {
                    "journal_version": JOURNAL_VERSION,
                    "transaction_id": transaction_id,
                    "phase": "prepared",
                    "archive": initial_archive,
                    "prebackup": _evidence_record(prebackup) if prebackup else None,
                    "targets": {
                        "database": str(database),
                        "campaigns": str(campaigns),
                        "database_existed": database.exists(),
                        "campaigns_existed": campaigns.exists(),
                    },
                    "staging": {
                        "database": str(stage_db),
                        "campaigns": str(stage_campaigns),
                    },
                    "rollback": {
                        "database": str(old_db),
                        "campaigns": str(old_campaigns),
                    },
                    "expected": {
                        "database": _database_record(staged_database),
                        "campaigns": _campaign_records(staged.campaign_files),
                    },
                    "original": {
                        "database_bundle": original_db_bundle,
                        "campaigns": original_campaigns,
                    },
                }
                _write_journal(journal, state, hooks)

                try:
                    result = _resume_locked(state, journal, hooks)
                except BaseException:
                    if state.get("phase") in ("cleanup_intent", "committed"):
                        _mark_recovery_required(state, journal)
                        raise RestoreRecoveryRequiredError(
                            "Restore cleanup failed and explicit recovery is required."
                        ) from None
                    try:
                        _rollback_locked(state, journal, hooks)
                    except BaseException:
                        _mark_recovery_required(state, journal)
                        raise RestoreRecoveryRequiredError(
                            "Restore failed and explicit recovery is required."
                        ) from None
                    raise
                return RestoreResult(
                    archive_path=archive,
                    restored_campaign_files=staged_campaigns_evidence.file_count,
                    database_path=database,
                    evidence=staged.evidence,
                    transaction_id=transaction_id,
                    action="restore",
                    outcome="committed",
                    recovery_state="clean",
                    prebackup_evidence=prebackup,
                    database_verification=result[0],
                    campaign_verification=result[1],
                    migration_required=not staged.evidence.migration.is_current,
                )
    except (BackupArchiveError, FileNotFoundError, RuntimeStateBusyError, RestoreTransactionError):
        raise
    except BaseException:
        raise RestoreTransactionError("The restore transaction failed safely.") from None
    finally:
        if state is None or not os.path.lexists(journal):
            _cleanup_prepared_paths(prepared_paths)


def resume_restore(
    *,
    db_path: Path,
    hooks: RestoreHooks | None = None,
) -> RecoveryResult:
    hooks = hooks or RestoreHooks()
    database = _safe_target_path(db_path)
    journal = active_restore_journal_path(database)
    with acquire_exclusive_state_lease(database):
        if not os.path.lexists(journal):
            return RecoveryResult(None, "resume", "no_active_transaction", "clean")
        state = _read_journal(journal)
        _validate_recovery_state(state, database)
        transaction_id = str(state["transaction_id"])
        try:
            _resume_locked(state, journal, hooks)
        except RestoreTransactionError:
            raise
        except BaseException:
            _mark_recovery_required(state, journal)
            raise RestoreRecoveryRequiredError(
                "Resume failed and explicit recovery is still required."
            ) from None
        return RecoveryResult(transaction_id, "resume", "committed", "clean")


def rollback_restore(
    *,
    db_path: Path,
    hooks: RestoreHooks | None = None,
) -> RecoveryResult:
    hooks = hooks or RestoreHooks()
    database = _safe_target_path(db_path)
    journal = active_restore_journal_path(database)
    with acquire_exclusive_state_lease(database):
        if not os.path.lexists(journal):
            return RecoveryResult(None, "rollback", "no_active_transaction", "clean")
        state = _read_journal(journal)
        _validate_recovery_state(state, database)
        if state["phase"] == "committed":
            raise RestoreTransactionError("A committed restore cannot be rolled back.")
        transaction_id = str(state["transaction_id"])
        if state["phase"] == "rolled_back":
            try:
                _finish_rolled_back(state, journal)
            except RestoreTransactionError:
                raise
            except BaseException:
                _mark_recovery_required(state, journal)
                raise RestoreRecoveryRequiredError(
                    "Rollback finalization failed and explicit recovery is still required."
                ) from None
            return RecoveryResult(transaction_id, "rollback", "rolled_back", "clean")
        _validate_recovery_removal_artifacts(state)
        if not _rollback_evidence_available(state):
            raise RestoreTransactionError(
                "Rollback evidence was already cleaned; resume the restore instead."
            )
        try:
            _rollback_locked(state, journal, hooks)
        except BaseException:
            _mark_recovery_required(state, journal)
            raise RestoreRecoveryRequiredError(
                "Rollback failed and explicit recovery is still required."
            ) from None
        return RecoveryResult(transaction_id, "rollback", "rolled_back", "clean")


def _resume_locked(
    state: dict[str, object],
    journal: Path,
    hooks: RestoreHooks,
) -> tuple[DatabaseRestoreEvidence, CampaignRestoreEvidence]:
    _validate_artifact_evidence(state)
    _set_phase(state, journal, "db_swap_intent", hooks)
    _publish_database(state, hooks)
    _set_phase(state, journal, "db_published", hooks)
    _set_phase(state, journal, "campaign_swap_intent", hooks)
    _publish_campaigns(state, hooks)
    _set_phase(state, journal, "campaigns_published", hooks)
    _set_phase(state, journal, "verifying", hooks)
    _event(hooks, "before_verify")
    database, campaigns = _verify_published(state)
    _event(hooks, "after_verify")
    _set_phase(state, journal, "verified", hooks)
    _set_phase(state, journal, "cleanup_intent", hooks)
    _event(hooks, "before_cleanup")
    _cleanup_transaction_artifacts(state)
    _event(hooks, "after_cleanup")
    _set_phase(state, journal, "committed", hooks)
    _remove_journal(journal)
    return database, campaigns


def _rollback_locked(
    state: dict[str, object],
    journal: Path,
    hooks: RestoreHooks,
) -> None:
    _set_phase(state, journal, "rollback_intent", hooks)
    targets = _mapping(state, "targets")
    staging = _mapping(state, "staging")
    rollback = _mapping(state, "rollback")
    database = Path(_string(targets, "database"))
    campaigns = Path(_string(targets, "campaigns"))
    old_db = Path(_string(rollback, "database"))
    old_campaigns = Path(_string(rollback, "campaigns"))
    affected_parents: set[Path] = set()

    if old_campaigns.exists():
        _remove_path_and_track_parent(campaigns, affected_parents)
        os.replace(old_campaigns, campaigns)
        affected_parents.add(campaigns.parent)
    elif not bool(targets["campaigns_existed"]):
        _remove_path_and_track_parent(campaigns, affected_parents)

    if old_db.exists():
        for active in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
            _remove_path_and_track_parent(active, affected_parents)
        os.replace(old_db, database)
        affected_parents.add(database.parent)
    elif not bool(targets["database_existed"]):
        for active in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
            _remove_path_and_track_parent(active, affected_parents)

    _remove_path_and_track_parent(
        Path(_string(staging, "database")), affected_parents
    )
    _remove_path_and_track_parent(
        Path(_string(staging, "campaigns")), affected_parents
    )
    _sync_affected_parents(affected_parents)
    _set_phase(state, journal, "rolled_back", hooks)
    _remove_journal(journal)


def _finish_rolled_back(
    state: dict[str, object],
    journal: Path,
) -> None:
    targets = _mapping(state, "targets")
    rollback = _mapping(state, "rollback")
    database = Path(_string(targets, "database"))
    campaigns = Path(_string(targets, "campaigns"))
    old_database = Path(_string(rollback, "database"))
    old_campaigns = Path(_string(rollback, "campaigns"))
    _validate_original_database_location(state, database, old_database)
    _validate_original_campaign_location(state, campaigns, old_campaigns)
    _cleanup_transaction_artifacts(state)
    _remove_journal(journal)


def _publish_database(state: dict[str, object], hooks: RestoreHooks) -> None:
    targets = _mapping(state, "targets")
    staging = _mapping(state, "staging")
    rollback = _mapping(state, "rollback")
    database = Path(_string(targets, "database"))
    stage = Path(_string(staging, "database"))
    old = Path(_string(rollback, "database"))
    expected = _mapping(_mapping(state, "expected"), "database")

    if stage.exists():
        _validate_original_database_location(state, database, old)
        if database.exists():
            if old.exists():
                raise RestoreTamperError("The database rollback bundle is ambiguous.")
            _event(hooks, f"before_rename_old_{database.name}")
            os.replace(database, old)
            _event(hooks, f"after_rename_old_{database.name}")
        _event(hooks, "before_publish_database")
        os.replace(stage, database)
        _event(hooks, "after_publish_database")
        _sync_directory(database.parent)
    else:
        try:
            record = _file_record(database)
        except (FileNotFoundError, OSError, RestoreTransactionError):
            raise RestoreTamperError(
                "The published database does not match evidence."
            ) from None
        if record != {
            "path": str(database),
            "byte_count": int(expected["byte_count"]),
            "sha256": str(expected["sha256"]),
        }:
            raise RestoreTamperError("The published database does not match evidence.")


def _publish_campaigns(state: dict[str, object], hooks: RestoreHooks) -> None:
    targets = _mapping(state, "targets")
    staging = _mapping(state, "staging")
    rollback = _mapping(state, "rollback")
    campaigns = Path(_string(targets, "campaigns"))
    stage = Path(_string(staging, "campaigns"))
    old = Path(_string(rollback, "campaigns"))
    if stage.exists():
        _validate_original_campaign_location(state, campaigns, old)
        if campaigns.exists():
            if old.exists():
                raise RestoreTamperError("The campaign rollback target is ambiguous.")
            _event(hooks, "before_rename_old_campaigns")
            os.replace(campaigns, old)
            _event(hooks, "after_rename_old_campaigns")
        _event(hooks, "before_publish_campaigns")
        os.replace(stage, campaigns)
        _event(hooks, "after_publish_campaigns")
        _sync_directory(campaigns.parent)
    else:
        expected = _campaign_evidence_from_records(
            _list(_mapping(state, "expected"), "campaigns")
        )
        _verify_campaign_tree(campaigns, expected.files)


def _verify_published(
    state: dict[str, object],
) -> tuple[DatabaseRestoreEvidence, CampaignRestoreEvidence]:
    targets = _mapping(state, "targets")
    expected = _mapping(state, "expected")
    database_path = Path(_string(targets, "database"))
    database = _database_evidence(database_path)
    expected_database = _mapping(expected, "database")
    if _database_record(database) != expected_database:
        raise RestoreTamperError("The restored database failed verification.")
    if Path(f"{database_path}-wal").exists() or Path(f"{database_path}-shm").exists():
        raise RestoreTamperError("The restored database has stale sidecars.")
    campaign_files = tuple(
        CampaignFileEvidence(
            _string(item, "relative_path"),
            int(item["byte_count"]),
            str(item["sha256"]),
        )
        for item in _list(expected, "campaigns")
        if isinstance(item, dict)
    )
    campaigns = _verify_campaign_tree(
        Path(_string(targets, "campaigns")),
        campaign_files,
    )
    return database, campaigns


def _validate_artifact_evidence(state: dict[str, object]) -> None:
    archive = _mapping(state, "archive")
    if _safe_file_record(Path(_string(archive, "path"))) != archive:
        raise RestoreTamperError("The restore archive no longer matches evidence.")
    prebackup = state.get("prebackup")
    if prebackup is not None:
        value = prebackup if isinstance(prebackup, dict) else {}
        record = _mapping(value, "file")
        if _safe_file_record(Path(_string(record, "path"))) != record:
            raise RestoreTamperError("The pre-restore backup no longer matches evidence.")
    staging = _mapping(state, "staging")
    expected = _mapping(state, "expected")
    stage_db = Path(_string(staging, "database"))
    target_db = Path(_string(_mapping(state, "targets"), "database"))
    if stage_db.exists():
        expected_db = _mapping(expected, "database")
        record = _safe_file_record(stage_db)
        if record["byte_count"] != expected_db["byte_count"] or record["sha256"] != expected_db["sha256"]:
            raise RestoreTamperError("The staged database no longer matches evidence.")
    elif not target_db.exists():
        raise RestoreTamperError("The staged or published database is missing.")
    stage_campaigns = Path(_string(staging, "campaigns"))
    if stage_campaigns.exists():
        expected_campaigns = _campaign_evidence_from_records(
            _list(expected, "campaigns")
        )
        _verify_campaign_tree(stage_campaigns, expected_campaigns.files)
    _validate_retained_rollback_evidence(state)


def _validate_retained_rollback_evidence(state: dict[str, object]) -> None:
    rollback = _mapping(state, "rollback")
    original = _mapping(state, "original")
    staging = _mapping(state, "staging")
    targets = _mapping(state, "targets")
    old_database = Path(_string(rollback, "database"))
    old_campaigns = Path(_string(rollback, "campaigns"))
    database_records = _list(original, "database_bundle")
    if old_database.exists():
        if len(database_records) != 1 or not isinstance(database_records[0], dict):
            raise RestoreTamperError("The database rollback evidence is invalid.")
        actual = _safe_file_record(old_database)
        expected = database_records[0]
        if (
            actual["byte_count"] != expected.get("byte_count")
            or actual["sha256"] != expected.get("sha256")
        ):
            raise RestoreTamperError("The database rollback evidence changed.")
    elif (
        bool(targets["database_existed"])
        and not Path(_string(staging, "database")).exists()
        and not _cleanup_was_started(state)
    ):
        if _rollback_retry_uses_active_originals(state):
            _validate_original_database_location(state, Path(_string(targets, "database")), old_database)
        else:
            raise RestoreTamperError("The database rollback evidence is missing.")
    if old_campaigns.exists():
        campaigns = _campaign_evidence_from_records(_list(original, "campaigns"))
        _verify_campaign_tree(old_campaigns, campaigns.files)
    elif (
        bool(targets["campaigns_existed"])
        and not Path(_string(staging, "campaigns")).exists()
        and not _cleanup_was_started(state)
    ):
        if _rollback_retry_uses_active_originals(state):
            _validate_original_campaign_location(
                state,
                Path(_string(targets, "campaigns")),
                old_campaigns,
            )
        else:
            raise RestoreTamperError("The campaign rollback evidence is missing.")


def _validate_recovery_removal_artifacts(state: dict[str, object]) -> None:
    _validate_retained_rollback_evidence(state)
    staging = _mapping(state, "staging")
    expected = _mapping(state, "expected")
    stage_database = Path(_string(staging, "database"))
    if stage_database.exists():
        record = _safe_file_record(stage_database)
        expected_database = _mapping(expected, "database")
        if (
            record["byte_count"] != expected_database.get("byte_count")
            or record["sha256"] != expected_database.get("sha256")
        ):
            raise RestoreTamperError("The staged database no longer matches evidence.")
    stage_campaigns = Path(_string(staging, "campaigns"))
    if stage_campaigns.exists():
        campaigns = _campaign_evidence_from_records(_list(expected, "campaigns"))
        _verify_campaign_tree(stage_campaigns, campaigns.files)


def _rollback_evidence_available(state: dict[str, object]) -> bool:
    targets = _mapping(state, "targets")
    rollback = _mapping(state, "rollback")
    if bool(targets["database_existed"]) and not Path(
        _string(rollback, "database")
    ).exists():
        database = Path(_string(targets, "database"))
        original_records = _list(_mapping(state, "original"), "database_bundle")
        if not original_records or not isinstance(original_records[0], dict):
            return False
        try:
            active = _safe_file_record(database)
        except RestoreTamperError:
            return False
        original = original_records[0]
        if (
            active["byte_count"] != original.get("byte_count")
            or active["sha256"] != original.get("sha256")
        ):
            return False
    if bool(targets["campaigns_existed"]) and not Path(
        _string(rollback, "campaigns")
    ).exists():
        campaigns_path = Path(_string(targets, "campaigns"))
        original_campaigns = _campaign_evidence_from_records(
            _list(_mapping(state, "original"), "campaigns")
        )
        try:
            _verify_campaign_tree(campaigns_path, original_campaigns.files)
        except RestoreTransactionError:
            return False
    return True


def _validate_recovery_state(state: dict[str, object], database: Path) -> None:
    if int(state.get("journal_version", 0)) != JOURNAL_VERSION:
        raise RestoreTamperError("The restore journal version is unsupported.")
    phase = state.get("phase")
    if phase not in PHASES:
        raise RestoreTamperError("The restore journal phase is invalid.")
    recovery_origin = state.get("recovery_from_phase")
    if phase == "recovery_required":
        if not isinstance(recovery_origin, str) or recovery_origin not in RECOVERY_ORIGIN_PHASES:
            raise RestoreTamperError("The restore recovery origin is invalid.")
    elif "recovery_from_phase" in state:
        raise RestoreTamperError("The restore recovery origin is inconsistent.")
    transaction_id = str(state.get("transaction_id", ""))
    if len(transaction_id) != 32 or any(character not in "0123456789abcdef" for character in transaction_id):
        raise RestoreTamperError("The restore transaction identity is invalid.")
    target = Path(_string(_mapping(state, "targets"), "database"))
    if target != database:
        raise RestoreTamperError("The restore journal target does not match.")
    transaction_id = str(state["transaction_id"])
    targets = _mapping(state, "targets")
    campaigns = Path(_string(targets, "campaigns"))
    staging = _mapping(state, "staging")
    rollback = _mapping(state, "rollback")
    expected_paths = {
        "stage_database": database.parent / f".{database.name}.restore-{transaction_id}.new",
        "stage_campaigns": campaigns.parent / f".{campaigns.name}.restore-{transaction_id}.new",
        "old_database": database.parent / f".{database.name}.restore-{transaction_id}.old",
        "old_campaigns": campaigns.parent / f".{campaigns.name}.restore-{transaction_id}.old",
    }
    actual_paths = {
        "stage_database": Path(_string(staging, "database")),
        "stage_campaigns": Path(_string(staging, "campaigns")),
        "old_database": Path(_string(rollback, "database")),
        "old_campaigns": Path(_string(rollback, "campaigns")),
    }
    if actual_paths != expected_paths:
        raise RestoreTamperError("The restore journal artifact paths are invalid.")


def _validate_original_database_location(
    state: dict[str, object],
    database: Path,
    old: Path,
) -> None:
    original = _list(_mapping(state, "original"), "database_bundle")
    expected = {
        Path(_string(item, "path")).name: item
        for item in original
        if isinstance(item, dict)
    }
    for name, record in expected.items():
        active = database.parent / name
        candidate = old if old.exists() else active
        actual = _safe_file_record(candidate)
        if actual["byte_count"] != record.get("byte_count") or actual["sha256"] != record.get("sha256"):
            raise RestoreTamperError("The original database rollback evidence changed.")
    expected_names = set(expected)
    for active in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        if active.exists() and active.name not in expected_names:
            raise RestoreTamperError("An unexpected database artifact appeared.")


def _validate_original_campaign_location(
    state: dict[str, object],
    campaigns: Path,
    old: Path,
) -> None:
    original = _campaign_evidence_from_records(
        _list(_mapping(state, "original"), "campaigns")
    )
    candidate = old if old.exists() else campaigns
    if candidate.exists():
        _verify_campaign_tree(candidate, original.files)
    elif original.file_count:
        raise RestoreTamperError("The original campaign rollback evidence is missing.")


def _validate_restore_boundaries(
    *,
    archive: Path,
    database: Path,
    campaigns: Path,
    backup_root: Path | None,
    journal: Path,
) -> None:
    _validate_path_chain(database.parent, require_existing=True)
    _validate_path_chain(campaigns.parent, require_existing=True)
    if database.exists():
        _validate_regular(database, single_link=True)
    if campaigns.exists():
        _validate_directory(campaigns)
        _scan_regular_tree(campaigns)
    paths = [archive, database, campaigns, journal]
    if backup_root is not None:
        resolved_backup = _safe_target_path(backup_root)
        if resolved_backup.exists():
            _validate_directory(resolved_backup)
        else:
            _validate_path_chain(resolved_backup.parent, require_existing=True)
        paths.append(resolved_backup)
    normalized = [_path_key(path) for path in paths]
    if len(normalized) != len(set(normalized)):
        raise RestoreTransactionError("Restore paths overlap or alias each other.")
    if _contains(database, campaigns) or _contains(campaigns, database):
        raise RestoreTransactionError("Restore targets overlap.")
    for value in (archive, journal, *(paths[4:])):
        if (
            _contains(value, campaigns)
            or _contains(campaigns, value)
            or _contains(value, database)
            or _contains(database, value)
        ):
            raise RestoreTransactionError("Restore storage paths overlap.")


def _create_prebackup(
    *,
    database: Path,
    campaigns: Path,
    backup_root: Path,
    transaction_id: str,
    limits: BackupArchiveLimits,
) -> BackupArchiveEvidence:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return create_backup_archive_v2(
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backup_root,
        archive_basename=f"pre-restore-{transaction_id}",
        created_at=created_at,
        limits=limits,
        snapshotter=snapshot_sqlite_database,
    )


def _verify_prebackup_matches_targets(
    *,
    database: Path,
    campaigns: Path,
    staged_database: Path,
    staged_campaign_files: tuple[CampaignFileEvidence, ...],
    snapshot_path: Path,
) -> None:
    try:
        snapshot = snapshot_sqlite_database(
            source_path=database,
            destination_path=snapshot_path,
        )
        if _database_logical_sha256(snapshot.final_path) != _database_logical_sha256(
            staged_database
        ):
            raise RestoreTamperError(
                "The active database changed after its mandatory prebackup."
            )
        _verify_campaign_tree(campaigns, staged_campaign_files)
    finally:
        _remove_path(snapshot_path)


def _database_logical_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            for pragma in ("application_id", "user_version", "encoding"):
                row = connection.execute(f"PRAGMA {pragma}").fetchone()
                _hash_logical_value(digest, f"pragma:{pragma}:{row!r}")
            for statement in connection.iterdump():
                _hash_logical_value(digest, statement)
    except sqlite3.Error:
        raise RestoreTamperError(
            "The mandatory prebackup database could not be compared safely."
        ) from None
    return digest.hexdigest()


def _hash_logical_value(digest, value: str) -> None:
    payload = value.encode("utf-8")
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _quiesce_database(database: Path) -> None:
    if not database.exists():
        return
    try:
        with closing(sqlite3.connect(database, timeout=0)) as connection:
            connection.execute("PRAGMA busy_timeout = 0")
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is not None and int(checkpoint[0]) != 0:
                raise RestoreTransactionError("The active database is busy.")
            journal_mode = str(connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]).lower()
            if journal_mode != "delete":
                raise RestoreTransactionError("The active database could not be quiesced.")
    except RestoreTransactionError:
        raise
    except sqlite3.Error:
        raise RestoreTransactionError("The active database is busy or invalid.") from None
    if Path(f"{database}-wal").exists() or Path(f"{database}-shm").exists():
        raise RestoreTransactionError(
            "The active database retained SQLite sidecars after quiescing."
        )


def _database_evidence(path: Path) -> DatabaseRestoreEvidence:
    byte_count, digest = _hash_file(path)
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            integrity = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
            foreign_keys = tuple(tuple(row) for row in connection.execute("PRAGMA foreign_key_check"))
            inspection = inspect_migration_ledger(connection)
            row = None
            if inspection.applied_version:
                row = connection.execute(
                    "SELECT name, checksum FROM schema_migrations WHERE version = ?",
                    (inspection.applied_version,),
                ).fetchone()
    except (sqlite3.Error, MigrationError):
        raise RestoreTamperError("The restored database is invalid.") from None
    if integrity != ("ok",) or foreign_keys:
        raise RestoreTamperError("The restored database failed integrity checks.")
    migration = MigrationEvidence(
        ledger_exists=inspection.ledger_exists,
        applied_version=inspection.applied_version,
        current_version=inspection.current_version,
        is_current=inspection.is_current,
        applied_name=str(row[0]) if row else None,
        applied_checksum=str(row[1]) if row else None,
    )
    return DatabaseRestoreEvidence(byte_count, digest, integrity, foreign_keys, migration)


def _copy_campaign_tree(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, copy_function=shutil.copy2)
    else:
        destination.mkdir()


def _verify_campaign_tree(
    root: Path,
    expected: tuple[CampaignFileEvidence, ...],
) -> CampaignRestoreEvidence:
    try:
        actual = _scan_regular_tree(root)
    except RestoreTamperError:
        raise
    except RestoreTransactionError:
        raise RestoreTamperError(
            "Restored campaign file identities are unsafe."
        ) from None
    actual_evidence = tuple(
        CampaignFileEvidence(relative, size, digest)
        for relative, _, size, digest in actual
    )
    if actual_evidence != expected:
        raise RestoreTamperError("Restored campaign files do not match evidence.")
    return CampaignRestoreEvidence(
        len(expected),
        sum(item.byte_count for item in expected),
        expected,
        True,
    )


def _scan_regular_tree(root: Path) -> tuple[tuple[str, Path, int, str], ...]:
    if not root.exists():
        return ()
    _validate_directory(root)
    files: list[tuple[str, Path, int, str]] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        for name in dirnames:
            _validate_directory(directory_path / name)
        for name in filenames:
            path = directory_path / name
            _validate_regular(path, single_link=True)
            size, digest = _hash_file(path)
            relative = path.relative_to(root).as_posix()
            files.append((relative, path, size, digest))
    files.sort(key=lambda item: item[0].encode("utf-8"))
    return tuple(files)


def _db_bundle_records(database: Path) -> list[dict[str, object]]:
    records = []
    for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        if path.exists():
            records.append(_file_record(path))
    return records


def _campaign_records(files) -> list[dict[str, object]]:
    records = []
    for item in files:
        if isinstance(item, CampaignFileEvidence):
            records.append(asdict(item))
        else:
            relative, _, size, digest = item
            records.append({"relative_path": relative, "byte_count": size, "sha256": digest})
    return records


def _database_record(evidence: DatabaseRestoreEvidence) -> dict[str, object]:
    return {
        "byte_count": evidence.byte_count,
        "sha256": evidence.sha256,
        "integrity_check": list(evidence.integrity_check),
        "foreign_key_violations": [list(row) for row in evidence.foreign_key_violations],
        "migration": asdict(evidence.migration),
    }


def _campaign_evidence_from_records(records: list[object]) -> CampaignRestoreEvidence:
    files = tuple(
        CampaignFileEvidence(
            _string(item, "relative_path"), int(item["byte_count"]), str(item["sha256"])
        )
        for item in records
        if isinstance(item, dict)
    )
    return CampaignRestoreEvidence(len(files), sum(item.byte_count for item in files), files, True)


def _evidence_record(evidence: BackupArchiveEvidence) -> dict[str, object]:
    return {
        "file": _file_record(evidence.archive_path),
        "format_version": evidence.format_version,
        "verification_level": evidence.verification_level,
    }


def _file_record(path: Path) -> dict[str, object]:
    resolved = _canonical_regular_file(path, require_single_link=True)
    size, digest = _hash_file(resolved)
    return {"path": str(resolved), "byte_count": size, "sha256": digest}


def _safe_file_record(path: Path) -> dict[str, object]:
    try:
        return _file_record(path)
    except (FileNotFoundError, OSError, RuntimeError):
        raise RestoreTamperError("A restore evidence file is unavailable.") from None


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            total += len(chunk)
            digest.update(chunk)
    return total, digest.hexdigest()


def _write_journal(
    journal: Path,
    state: dict[str, object],
    hooks: RestoreHooks,
) -> None:
    _event(hooks, f"before_journal_{state['phase']}")
    payload = dict(state)
    payload.pop("journal_sha256", None)
    checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    payload["journal_sha256"] = checksum
    temporary = journal.parent / f".{journal.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(canonical_json_bytes(payload))
        _sync_file(temporary)
        os.replace(temporary, journal)
        _sync_directory(journal.parent)
    finally:
        _remove_path(temporary)
    state["journal_sha256"] = checksum
    _event(hooks, f"after_journal_{state['phase']}")


def _read_journal(journal: Path) -> dict[str, object]:
    _validate_regular(journal, single_link=True)
    try:
        raw = journal.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RestoreTamperError("The restore journal is invalid.") from None
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise RestoreTamperError("The restore journal encoding is invalid.")
    checksum = value.pop("journal_sha256", None)
    if not isinstance(checksum, str) or hashlib.sha256(canonical_json_bytes(value)).hexdigest() != checksum:
        raise RestoreTamperError("The restore journal checksum is invalid.")
    value["journal_sha256"] = checksum
    return value


def _set_phase(
    state: dict[str, object],
    journal: Path,
    phase: str,
    hooks: RestoreHooks,
) -> None:
    if phase not in PHASES:
        raise RestoreTransactionError("The restore phase is invalid.")
    if phase != "recovery_required":
        state.pop("recovery_from_phase", None)
    state["phase"] = phase
    _write_journal(journal, state, hooks)


def _mark_recovery_required(state: dict[str, object], journal: Path) -> None:
    try:
        if state.get("phase") != "recovery_required":
            state["recovery_from_phase"] = state.get("phase")
        state["phase"] = "recovery_required"
        _write_journal(journal, state, RestoreHooks())
    except BaseException:
        pass


def _cleanup_was_started(state: dict[str, object]) -> bool:
    return state.get("phase") in ("cleanup_intent", "committed") or (
        state.get("phase") == "recovery_required"
        and state.get("recovery_from_phase") in ("cleanup_intent", "committed")
    )


def _rollback_retry_uses_active_originals(state: dict[str, object]) -> bool:
    return state.get("phase") == "rollback_intent" or (
        state.get("phase") == "recovery_required"
        and state.get("recovery_from_phase") in ("rollback_intent", "rolled_back")
    )


def _cleanup_prepared_paths(paths: list[Path]) -> None:
    affected_parents: set[Path] = set()
    for path in paths:
        if not os.path.lexists(path):
            continue
        _remove_path(path)
        affected_parents.add(path.parent)
    _sync_affected_parents(affected_parents)


def _cleanup_transaction_artifacts(state: dict[str, object]) -> None:
    affected_parents: set[Path] = set()
    for group in ("staging", "rollback"):
        values = _mapping(state, group)
        for value in values.values():
            if isinstance(value, str):
                _remove_path_and_track_parent(Path(value), affected_parents)
    _sync_affected_parents(affected_parents)


def _remove_path_and_track_parent(
    path: Path,
    affected_parents: set[Path],
) -> None:
    affected_parents.add(path.parent)
    if not os.path.lexists(path):
        return
    _remove_path(path)


def _sync_affected_parents(parents: set[Path]) -> None:
    for parent in sorted(parents, key=_path_key):
        _sync_directory(parent)


def _remove_journal(journal: Path) -> None:
    _remove_path(journal)
    _sync_directory(journal.parent)


def _sync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _sync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            _sync_file(path)
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
        _sync_directory(path)
    _sync_directory(root)


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_path(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except FileNotFoundError:
        pass


def _canonical_regular_file(path: Path, *, require_single_link: bool) -> Path:
    candidate = Path(os.path.abspath(Path(path).expanduser()))
    if not os.path.lexists(candidate):
        raise FileNotFoundError
    _validate_path_chain(candidate.parent, require_existing=True)
    if candidate.is_symlink() or _is_reparse(candidate):
        raise RestoreTransactionError("A restore file identity is unsafe.")
    resolved = candidate.resolve(strict=True)
    _validate_regular(resolved, single_link=require_single_link)
    return resolved


def _safe_target_path(path: Path) -> Path:
    candidate = Path(os.path.abspath(Path(path).expanduser()))
    _validate_path_chain(candidate, require_existing=False)
    if os.path.lexists(candidate) and (candidate.is_symlink() or _is_reparse(candidate)):
        raise RestoreTransactionError("A restore path identity is unsafe.")
    return candidate


def _validate_regular(path: Path, *, single_link: bool) -> None:
    if path.is_symlink() or _is_reparse(path):
        raise RestoreTransactionError("A restore file identity is unsafe.")
    details = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode) or (single_link and details.st_nlink != 1):
        raise RestoreTransactionError("A restore file identity is unsafe.")


def _validate_directory(path: Path) -> None:
    if path.is_symlink() or _is_reparse(path):
        raise RestoreTransactionError("A restore directory identity is unsafe.")
    details = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(details.st_mode):
        raise RestoreTransactionError("A restore directory identity is unsafe.")


def _validate_path_chain(path: Path, *, require_existing: bool) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            if require_existing:
                raise RestoreTransactionError("A restore path parent is unavailable.")
            return
        if current.is_symlink() or _is_reparse(current):
            raise RestoreTransactionError("A restore path contains an unsafe alias.")


def _is_reparse(path: Path) -> bool:
    try:
        return bool(path.lstat().st_file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except (AttributeError, FileNotFoundError):
        return False


def _path_key(path: Path) -> str:
    return unicodedata.normalize("NFC", str(path.resolve(strict=False))).casefold()


def _contains(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _event(hooks: RestoreHooks, name: str) -> None:
    if hooks.on_event is not None:
        hooks.on_event(name)


def _mapping(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise RestoreTamperError("The restore journal structure is invalid.")
    return item


def _list(value: dict[str, object], key: str) -> list[object]:
    item = value.get(key)
    if not isinstance(item, list):
        raise RestoreTamperError("The restore journal structure is invalid.")
    return item


def _string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise RestoreTamperError("The restore journal structure is invalid.")
    return item
