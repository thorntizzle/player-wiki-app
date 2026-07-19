from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from .backup_archive import BackupArchiveEvidence, inspect_backup_archive
from .operations import BackupResult, create_backup_archive
from .player_wiki_reconciliation import ReconciliationHooks
from .player_wiki_reconciliation_inspection import (
    InspectionFilters,
    inspect_player_wiki_reconciliation,
)
from .runtime_lease import (
    RuntimeStateBusyError,
    RuntimeStateLeaseError,
    acquire_exclusive_state_lease,
    has_active_restore_journal,
)


SUPPORTED_ACTIONS = frozenset(
    {"abandon-precommit", "resume-forward", "retry-refresh-cleanup"}
)
_RECOMMENDED_ACTIONS = {
    "abandon-precommit": frozenset({"abandon_precommit_after_backup"}),
    "resume-forward": frozenset(
        {
            "resume_forward_after_backup",
            "resume_forward_publish_markdown_after_backup",
        }
    ),
    "retry-refresh-cleanup": frozenset(
        {"retry_refresh_cleanup_after_backup"}
    ),
}
_TABLES = (
    ("publication", "player_wiki_reconciliation_operations"),
    ("deletion", "player_wiki_deletion_operations"),
)


class PlayerWikiReconciliationOperationError(RuntimeError):
    def __init__(self, reason_code: str, *, exit_code: int = 2) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class PlayerWikiReconciliationOperationHooks:
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True, slots=True)
class PlayerWikiReconciliationOperationResult:
    kind: str
    operation_id: str
    action: str
    outcome: str
    backup_path: Path
    backup_evidence: BackupArchiveEvidence


def apply_player_wiki_reconciliation_operation(
    *,
    database_path: Path,
    campaigns_dir: Path,
    backup_root: Path,
    kind: str,
    operation_id: str,
    action: str,
    confirmed: bool,
    app_factory: Callable[[], Any] | None = None,
    hooks: PlayerWikiReconciliationOperationHooks | None = None,
    backup_creator: Callable[..., BackupResult] = create_backup_archive,
) -> PlayerWikiReconciliationOperationResult:
    """Apply one deterministic reconciliation action behind a verified backup."""

    _validate_arguments(kind, operation_id, action, confirmed)
    database = Path(database_path).expanduser().resolve(strict=False)
    campaigns = Path(campaigns_dir).expanduser().resolve(strict=False)
    backups = Path(backup_root).expanduser().resolve(strict=False)
    selected_hooks = hooks or PlayerWikiReconciliationOperationHooks()

    if has_active_restore_journal(database):
        raise PlayerWikiReconciliationOperationError("restore_recovery_active")
    preliminary = _inspect_exact(database, campaigns, kind, operation_id, action)
    try:
        lease = acquire_exclusive_state_lease(database, timeout_seconds=0.0)
    except RuntimeStateBusyError:
        raise PlayerWikiReconciliationOperationError(
            "runtime_state_busy", exit_code=3
        ) from None
    except RuntimeStateLeaseError:
        raise PlayerWikiReconciliationOperationError(
            "runtime_state_unavailable"
        ) from None

    try:
        with lease:
            if has_active_restore_journal(database):
                raise PlayerWikiReconciliationOperationError(
                    "restore_recovery_active"
                )
            locked = _inspect_exact(database, campaigns, kind, operation_id, action)
            if locked != preliminary:
                raise PlayerWikiReconciliationOperationError(
                    "operation_evidence_changed", exit_code=3
                )

            _event(selected_hooks, "before_backup", operation_id)
            try:
                backup = backup_creator(
                    db_path=database,
                    campaigns_dir=campaigns,
                    backup_root=backups,
                    label=(
                        f"player-wiki-reconciliation-{kind}-{operation_id}-{action}"
                    ),
                )
            except PlayerWikiReconciliationOperationError:
                raise
            except Exception:
                raise PlayerWikiReconciliationOperationError("backup_failed") from None
            _verify_backup(backup)
            try:
                _event(selected_hooks, "after_backup", operation_id)
            except Exception:
                raise PlayerWikiReconciliationOperationError(
                    "post_backup_gate_failed"
                ) from None

            try:
                _event(selected_hooks, "before_reinspection", operation_id)
                reinspected = _inspect_exact(
                    database, campaigns, kind, operation_id, action
                )
                rows_before = _active_row_fingerprints(database)
                _event(selected_hooks, "after_reinspection", operation_id)
            except PlayerWikiReconciliationOperationError:
                raise
            except Exception:
                raise PlayerWikiReconciliationOperationError(
                    "operation_evidence_changed", exit_code=3
                ) from None
            if reinspected != locked:
                raise PlayerWikiReconciliationOperationError(
                    "operation_evidence_changed", exit_code=3
                )

            factory = app_factory or _default_app_factory
            try:
                app = factory()
            except Exception:
                raise PlayerWikiReconciliationOperationError(
                    "application_context_unavailable"
                ) from None
            if (
                Path(app.config.get("DB_PATH", "")).expanduser().resolve(strict=False)
                != database
                or Path(app.config.get("CAMPAIGNS_DIR", ""))
                .expanduser()
                .resolve(strict=False)
                != campaigns
            ):
                raise PlayerWikiReconciliationOperationError(
                    "application_configuration_mismatch"
                )

            try:
                with app.app_context():
                    reconciler = app.extensions["player_wiki_reconciler"]
                    previous_hooks = reconciler.hooks
                    reconciler.hooks = ReconciliationHooks(
                        on_event=selected_hooks.on_event
                    )
                    try:
                        _event(selected_hooks, "before_action", operation_id)
                        outcome = _invoke_action(
                            reconciler,
                            kind=kind,
                            operation_id=operation_id,
                            action=action,
                        )
                        _event(selected_hooks, "after_action", operation_id)
                    finally:
                        reconciler.hooks = previous_hooks
            except PlayerWikiReconciliationOperationError:
                raise
            except Exception:
                raise PlayerWikiReconciliationOperationError("action_failed") from None

            _prove_exact_completion(
                database,
                campaigns,
                kind=kind,
                operation_id=operation_id,
                rows_before=rows_before,
            )
            return PlayerWikiReconciliationOperationResult(
                kind=kind,
                operation_id=operation_id,
                action=action,
                outcome=outcome,
                backup_path=backup.archive_path,
                backup_evidence=backup.evidence,
            )
    except PlayerWikiReconciliationOperationError:
        raise
    except RuntimeStateLeaseError:
        raise PlayerWikiReconciliationOperationError(
            "runtime_state_unavailable"
        ) from None
    except Exception:
        raise PlayerWikiReconciliationOperationError("operation_failed_safely") from None


def _default_app_factory() -> Any:
    from .app import create_app

    return create_app()


def _validate_arguments(
    kind: str,
    operation_id: str,
    action: str,
    confirmed: bool,
) -> None:
    if kind not in {"publication", "deletion"}:
        raise PlayerWikiReconciliationOperationError("invalid_kind")
    if (
        not isinstance(operation_id, str)
        or len(operation_id) != 32
        or operation_id != operation_id.lower()
        or any(character not in "0123456789abcdef" for character in operation_id)
    ):
        raise PlayerWikiReconciliationOperationError("invalid_operation_id")
    if action not in SUPPORTED_ACTIONS:
        raise PlayerWikiReconciliationOperationError("unsupported_action")
    if confirmed is not True:
        raise PlayerWikiReconciliationOperationError("confirmation_required")


def _inspect_exact(
    database: Path,
    campaigns: Path,
    kind: str,
    operation_id: str,
    action: str,
) -> dict[str, object]:
    report, _exit_code = inspect_player_wiki_reconciliation(
        database_path=database,
        campaigns_dir=campaigns,
        filters=InspectionFilters(kind="all", operation_id=operation_id),
    )
    if report.get("consistency") != "stable":
        error = report.get("error")
        reason = str(error.get("reason_code")) if isinstance(error, dict) else ""
        exit_code = 3 if "changed" in reason or "busy" in reason else 2
        raise PlayerWikiReconciliationOperationError(
            "inspection_failed", exit_code=exit_code
        )
    migration = report.get("migration")
    if not isinstance(migration, dict) or (
        migration.get("applied_version") != 9
        or migration.get("current_version") != 9
        or migration.get("compatibility") != "current"
        or migration.get("evidence_status") != "verified"
        or migration.get("migration_required") is not False
    ):
        raise PlayerWikiReconciliationOperationError("current_schema_required")
    operations = report.get("operations")
    if not isinstance(operations, list) or len(operations) != 1:
        raise PlayerWikiReconciliationOperationError("no_active_operation")
    operation = operations[0]
    if not isinstance(operation, dict):
        raise PlayerWikiReconciliationOperationError("operation_evidence_invalid")
    if operation.get("operation_id") != operation_id:
        raise PlayerWikiReconciliationOperationError("operation_identity_mismatch")
    if operation.get("kind") != kind:
        raise PlayerWikiReconciliationOperationError("operation_kind_mismatch")
    if operation.get("recommended_action") not in _RECOMMENDED_ACTIONS[action]:
        raise PlayerWikiReconciliationOperationError("action_not_supported_by_evidence")
    return dict(operation)


def _verify_backup(backup: BackupResult) -> None:
    try:
        verified = inspect_backup_archive(backup.archive_path)
    except Exception:
        raise PlayerWikiReconciliationOperationError(
            "backup_verification_failed"
        ) from None
    if (
        verified != backup.evidence
        or verified.format_version != 2
        or verified.verification_level != "verified_v2"
        or not verified.manifest_hashes_verified
        or verified.migration.applied_version != 9
        or verified.migration.current_version != 9
        or not verified.migration.is_current
    ):
        raise PlayerWikiReconciliationOperationError("backup_verification_failed")


def _invoke_action(
    reconciler: Any,
    *,
    kind: str,
    operation_id: str,
    action: str,
) -> str:
    if action == "abandon-precommit":
        return str(
            reconciler.abandon_precommit_operation(
                kind=kind, operation_id=operation_id
            )
        )
    if action == "resume-forward":
        return str(
            reconciler.resume_forward_operation(
                kind=kind, operation_id=operation_id
            )
        )
    if action == "retry-refresh-cleanup":
        return str(
            reconciler.retry_refresh_cleanup_operation(
                kind=kind, operation_id=operation_id
            )
        )
    raise PlayerWikiReconciliationOperationError("unsupported_action")


def _active_row_fingerprints(database: Path) -> dict[tuple[str, str], str]:
    uri = f"{database.as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=0.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        fingerprints: dict[tuple[str, str], str] = {}
        for kind, table in _TABLES:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE state IN ('prepared','repository_pending','conflict') ORDER BY operation_id"
            ).fetchall()
            for row in rows:
                operation_id = str(row["operation_id"])
                normalized = {
                    key: _fingerprint_value(row[key]) for key in row.keys()
                }
                fingerprints[(kind, operation_id)] = hashlib.sha256(
                    json.dumps(
                        normalized,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
        return fingerprints
    except (OSError, sqlite3.Error, TypeError, ValueError):
        raise PlayerWikiReconciliationOperationError(
            "operation_evidence_invalid"
        ) from None
    finally:
        if "connection" in locals():
            connection.close()


def _fingerprint_value(value: object) -> object:
    if isinstance(value, bytes):
        return {
            "blob_byte_count": len(value),
            "blob_sha256": hashlib.sha256(value).hexdigest(),
        }
    if value is None or isinstance(value, (str, int, float)):
        return value
    raise TypeError("Unsupported reconciliation evidence value.")


def _prove_exact_completion(
    database: Path,
    campaigns: Path,
    *,
    kind: str,
    operation_id: str,
    rows_before: dict[tuple[str, str], str],
) -> None:
    report, _exit_code = inspect_player_wiki_reconciliation(
        database_path=database,
        campaigns_dir=campaigns,
        filters=InspectionFilters(kind="all", operation_id=operation_id),
    )
    if (
        report.get("consistency") != "stable"
        or not isinstance(report.get("operations"), list)
        or report["operations"]
    ):
        raise PlayerWikiReconciliationOperationError(
            "completion_evidence_failed", exit_code=3
        )
    rows_after = _active_row_fingerprints(database)
    expected = dict(rows_before)
    if expected.pop((kind, operation_id), None) is None or rows_after != expected:
        raise PlayerWikiReconciliationOperationError(
            "operation_isolation_failed", exit_code=3
        )


def _event(
    hooks: PlayerWikiReconciliationOperationHooks,
    event: str,
    operation_id: str,
) -> None:
    if hooks.on_event is not None:
        hooks.on_event(event, operation_id)
