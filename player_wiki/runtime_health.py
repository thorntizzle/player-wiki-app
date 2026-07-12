from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3

from .migrations import MigrationError, inspect_migration_ledger


READINESS_DATABASE_TIMEOUT_SECONDS = 0.25


@dataclass(frozen=True)
class DependencyCheck:
    status: str
    reason: str = ""

    def to_payload(self) -> dict[str, str]:
        payload = {"status": self.status}
        if self.reason:
            payload["reason"] = self.reason
        return payload


def liveness_payload() -> dict[str, str]:
    """Return process liveness without consulting application dependencies."""

    return {"status": "ok"}


def readiness_payload(
    *,
    database_path: Path,
    campaigns_dir: Path,
    database_timeout_seconds: float = READINESS_DATABASE_TIMEOUT_SECONDS,
) -> tuple[dict[str, object], int]:
    """Inspect required dependencies without creating or mutating application data."""

    database_check, migration_check = _inspect_database(
        Path(database_path),
        timeout_seconds=database_timeout_seconds,
    )
    campaigns_check = _inspect_campaigns_dir(Path(campaigns_dir))
    checks = {
        "database": database_check.to_payload(),
        "migrations": migration_check.to_payload(),
        "campaigns": campaigns_check.to_payload(),
    }

    failed_reason = next(
        (
            check.reason
            for check in (database_check, migration_check, campaigns_check)
            if check.status == "fail"
        ),
        "",
    )
    if not failed_reason:
        return {"status": "ready", "checks": checks}, 200
    return {
        "status": "not_ready",
        "reason": failed_reason,
        "checks": checks,
    }, 503


def _inspect_database(
    database_path: Path,
    *,
    timeout_seconds: float,
) -> tuple[DependencyCheck, DependencyCheck]:
    try:
        if not database_path.exists():
            return (
                DependencyCheck("fail", "database_missing"),
                DependencyCheck("skipped", "database_unavailable"),
            )
        if not database_path.is_file():
            return (
                DependencyCheck("fail", "database_not_file"),
                DependencyCheck("skipped", "database_unavailable"),
            )
    except OSError:
        return (
            DependencyCheck("fail", "database_unavailable"),
            DependencyCheck("skipped", "database_unavailable"),
        )

    timeout_seconds = min(max(float(timeout_seconds), 0.0), 1.0)
    connection: sqlite3.Connection | None = None
    try:
        database_uri = f"{database_path.absolute().as_uri()}?mode=ro"
        connection = sqlite3.connect(
            database_uri,
            uri=True,
            timeout=timeout_seconds,
            isolation_level=None,
        )
        connection.execute("PRAGMA query_only = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        inspection = inspect_migration_ledger(connection)
    except MigrationError:
        return (
            DependencyCheck("ok"),
            DependencyCheck("fail", "migration_ledger_invalid"),
        )
    except (OSError, sqlite3.Error, ValueError):
        return (
            DependencyCheck("fail", "database_unavailable"),
            DependencyCheck("skipped", "database_unavailable"),
        )
    finally:
        if connection is not None:
            connection.close()

    if not inspection.ledger_exists:
        return (
            DependencyCheck("ok"),
            DependencyCheck("fail", "migration_ledger_missing"),
        )
    if not inspection.is_current:
        return (
            DependencyCheck("ok"),
            DependencyCheck("fail", "migration_ledger_outdated"),
        )
    return DependencyCheck("ok"), DependencyCheck("ok")


def _inspect_campaigns_dir(campaigns_dir: Path) -> DependencyCheck:
    try:
        if not campaigns_dir.exists():
            return DependencyCheck("fail", "campaigns_missing")
        if not campaigns_dir.is_dir():
            return DependencyCheck("fail", "campaigns_not_directory")
        if not os.access(campaigns_dir, os.R_OK | os.X_OK):
            return DependencyCheck("fail", "campaigns_unreadable")
        with os.scandir(campaigns_dir) as entries:
            next(entries, None)
    except OSError:
        return DependencyCheck("fail", "campaigns_unreadable")
    return DependencyCheck("ok")
