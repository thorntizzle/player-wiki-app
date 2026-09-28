from __future__ import annotations

from pathlib import Path

from .runtime_lease import RuntimeStateLease, acquire_state_lease


def _gate_identity(database_path: Path) -> Path:
    # Use a distinct lease: the running app retains the normal state lease.
    return Path(f"{Path(database_path).resolve(strict=False)}.fly-sync-capture")


def acquire_request_capture_lease(database_path: Path) -> RuntimeStateLease:
    """Keep a request within one side of a Fly capture boundary."""
    return acquire_state_lease(_gate_identity(database_path), mode="shared")


def acquire_exclusive_capture_lease(
    database_path: Path, *, timeout_seconds: float = 15.0
) -> RuntimeStateLease:
    """Drain requests and exclude new ones while DB and files are captured."""
    return acquire_state_lease(
        _gate_identity(database_path), mode="exclusive", timeout_seconds=timeout_seconds
    )


def acquire_exclusive_sync_operation_lease(database_path: Path) -> RuntimeStateLease:
    """Reject another pull targeting the same local database until this pull ends."""
    identity = Path(f"{Path(database_path).resolve(strict=False)}.fly-sync-operation")
    return acquire_state_lease(identity, mode="exclusive")
