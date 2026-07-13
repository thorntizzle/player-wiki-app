from __future__ import annotations

import hashlib
import math
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class SQLiteSnapshotError(RuntimeError):
    """Raised when a safe SQLite snapshot cannot be published."""


class SQLiteSnapshotTimeout(SQLiteSnapshotError):
    """Raised when a safe snapshot cannot publish within its deadline."""


_MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SQLiteSnapshotPolicy:
    """Immutable production safety budgets for SQLite snapshot publication."""

    inactivity_timeout_seconds: float = 15.0
    absolute_base_seconds: float = 15.0
    estimated_bytes_per_second: int = _MIB
    minimum_absolute_timeout_seconds: float = 30.0
    maximum_absolute_timeout_seconds: float = 300.0
    minimum_free_space_reserve_bytes: int = 64 * _MIB
    free_space_reserve_fraction: float = 0.25


SQLITE_SNAPSHOT_POLICY = SQLiteSnapshotPolicy()


@dataclass(slots=True)
class _SnapshotDeadlineState:
    inactivity_timeout_seconds: float
    inactivity_deadline: float
    absolute_deadline: float
    previous_remaining_pages: int | None = None

    def record_progress(self, remaining_pages: int, total_pages: int) -> None:
        previous_remaining_pages = self.previous_remaining_pages
        if previous_remaining_pages is None:
            previous_remaining_pages = total_pages
        if (
            previous_remaining_pages is not None
            and remaining_pages < previous_remaining_pages
        ):
            self.inactivity_deadline = min(
                time.monotonic() + self.inactivity_timeout_seconds,
                self.absolute_deadline,
            )
        self.previous_remaining_pages = remaining_pages

    def ensure_backup_active(self, *, busy_or_locked: bool = False) -> None:
        now = time.monotonic()
        if now < self.absolute_deadline and now < self.inactivity_deadline:
            return
        if now >= self.absolute_deadline:
            raise SQLiteSnapshotTimeout(
                "SQLite snapshot exceeded its absolute deadline before publication."
            )
        if busy_or_locked:
            message = (
                "SQLite snapshot timed out while waiting for a busy or locked "
                "source database."
            )
        else:
            message = (
                "SQLite snapshot backup made no progress within its inactivity deadline."
            )
        raise SQLiteSnapshotTimeout(message)

    def ensure_before_absolute_deadline(self) -> None:
        if time.monotonic() < self.absolute_deadline:
            return
        raise SQLiteSnapshotTimeout(
            "SQLite snapshot exceeded its absolute deadline before publication."
        )


@dataclass(frozen=True, slots=True)
class BackupProgress:
    status: int
    remaining_pages: int
    total_pages: int
    call_count: int
    busy_retries: int


@dataclass(frozen=True, slots=True)
class SQLiteSnapshotEvidence:
    final_path: Path
    byte_count: int
    sha256: str
    integrity_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[object, ...], ...]
    elapsed_seconds: float
    total_pages: int
    remaining_pages: int
    progress_calls: int
    busy_retries: int


@dataclass(frozen=True, slots=True)
class SQLiteSnapshotHooks:
    """Deterministic fault/concurrency seams for tests and local operations."""

    after_source_open: Callable[[sqlite3.Connection], None] | None = None
    after_temp_create: Callable[[Path], None] | None = None
    on_progress: Callable[[BackupProgress], None] | None = None
    before_validation: Callable[[Path], None] | None = None


def snapshot_sqlite_database(
    *,
    source_path: Path,
    destination_path: Path,
    timeout_seconds: float = SQLITE_SNAPSHOT_POLICY.inactivity_timeout_seconds,
    pages_per_step: int = 64,
    hooks: SQLiteSnapshotHooks | None = None,
) -> SQLiteSnapshotEvidence:
    """Create, validate, and atomically publish a WAL-aware SQLite snapshot."""

    source_path = Path(source_path)
    destination_path = Path(destination_path)
    if timeout_seconds <= 0 or timeout_seconds != timeout_seconds:
        raise ValueError("timeout_seconds must be greater than zero")
    if pages_per_step <= 0:
        raise ValueError("pages_per_step must be greater than zero")
    if not source_path.exists():
        raise FileNotFoundError("SQLite snapshot source does not exist.")
    if not source_path.is_file():
        raise SQLiteSnapshotError("SQLite snapshot source is not a regular file.")

    resolved_source = source_path.resolve()
    resolved_destination = destination_path.resolve(strict=False)
    if resolved_source == resolved_destination:
        raise SQLiteSnapshotError("SQLite snapshot source and destination must differ.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    estimated_output_bytes = _estimate_snapshot_output_bytes(resolved_source)
    absolute_timeout_seconds = _absolute_timeout_seconds(estimated_output_bytes)
    absolute_deadline = started_at + absolute_timeout_seconds
    inactivity_timeout_seconds = min(timeout_seconds, absolute_timeout_seconds)
    deadlines = _SnapshotDeadlineState(
        inactivity_timeout_seconds=inactivity_timeout_seconds,
        inactivity_deadline=started_at + inactivity_timeout_seconds,
        absolute_deadline=absolute_deadline,
    )
    hooks = hooks or SQLiteSnapshotHooks()
    temp_path: Path | None = None
    progress_calls = 0
    busy_retries = 0
    remaining_pages = 0
    total_pages = 0
    retry_sleep = _backup_retry_sleep(inactivity_timeout_seconds)

    try:
        _ensure_snapshot_capacity(
            destination_path.parent,
            estimated_output_bytes=estimated_output_bytes,
        )
        temp_path = _create_temp_path(destination_path)
        if hooks.after_temp_create is not None:
            hooks.after_temp_create(temp_path)
        deadlines.ensure_before_absolute_deadline()

        with closing(_connect_read_only(resolved_source)) as source_connection:
            if hooks.after_source_open is not None:
                hooks.after_source_open(source_connection)
            deadlines.ensure_backup_active()
            with closing(
                sqlite3.connect(temp_path, timeout=0.0)
            ) as destination_connection:
                destination_connection.execute("PRAGMA busy_timeout=0")

                def report_progress(status: int, remaining: int, total: int) -> None:
                    nonlocal progress_calls, busy_retries, remaining_pages, total_pages
                    primary_status = _primary_result_code(status)
                    is_busy = primary_status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                    progress_calls += 1
                    remaining_pages = remaining
                    total_pages = total
                    if is_busy:
                        busy_retries += 1
                    deadlines.ensure_backup_active(busy_or_locked=is_busy)
                    deadlines.record_progress(remaining, total)
                    if hooks.on_progress is not None:
                        hooks.on_progress(
                            BackupProgress(
                                status=status,
                                remaining_pages=remaining,
                                total_pages=total,
                                call_count=progress_calls,
                                busy_retries=busy_retries,
                            )
                        )
                    deadlines.ensure_backup_active(busy_or_locked=is_busy)
                    if is_busy:
                        _sleep_for_retry(deadlines, retry_sleep)

                _run_backup_until_deadline(
                    source_connection,
                    destination_connection,
                    deadlines=deadlines,
                    pages=pages_per_step,
                    progress=report_progress,
                    retry_sleep=retry_sleep,
                )
                deadlines.ensure_before_absolute_deadline()
                destination_connection.commit()
                journal_mode_row = destination_connection.execute(
                    "PRAGMA journal_mode=DELETE"
                ).fetchone()
                if journal_mode_row is None or str(journal_mode_row[0]).lower() != "delete":
                    raise SQLiteSnapshotError("SQLite snapshot could not finalize its journal safely.")
                destination_connection.commit()
                deadlines.ensure_before_absolute_deadline()

        _remove_incomplete_sidecars(temp_path)

        if hooks.before_validation is not None:
            hooks.before_validation(temp_path)
        deadlines.ensure_before_absolute_deadline()
        integrity_check, foreign_key_violations = _validate_snapshot(temp_path, deadlines)
        byte_count, sha256 = _hash_file(temp_path, deadlines)
        _sync_file(temp_path)
        deadlines.ensure_before_absolute_deadline()

        _atomic_replace(temp_path, destination_path)
        temp_path = None

        return SQLiteSnapshotEvidence(
            final_path=destination_path.resolve(),
            byte_count=byte_count,
            sha256=sha256,
            integrity_check=integrity_check,
            foreign_key_violations=foreign_key_violations,
            elapsed_seconds=time.monotonic() - started_at,
            total_pages=total_pages,
            remaining_pages=remaining_pages,
            progress_calls=progress_calls,
            busy_retries=busy_retries,
        )
    except (FileNotFoundError, SQLiteSnapshotError):
        raise
    except sqlite3.Error as exc:
        raise SQLiteSnapshotError("SQLite snapshot failed before publication.") from exc
    except OSError as exc:
        raise SQLiteSnapshotError("SQLite snapshot could not be published safely.") from exc
    finally:
        if temp_path is not None:
            _remove_incomplete_temp(temp_path)


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=0.0)
    connection.execute("PRAGMA busy_timeout=0")
    return connection


def _run_backup(
    source_connection: sqlite3.Connection,
    destination_connection: sqlite3.Connection,
    *,
    pages: int,
    progress: Callable[[int, int, int], None],
    sleep: float,
) -> None:
    source_connection.backup(
        destination_connection,
        pages=pages,
        progress=progress,
        sleep=sleep,
    )


def _run_backup_until_deadline(
    source_connection: sqlite3.Connection,
    destination_connection: sqlite3.Connection,
    *,
    deadlines: _SnapshotDeadlineState,
    pages: int,
    progress: Callable[[int, int, int], None],
    retry_sleep: float,
) -> None:
    while True:
        deadlines.ensure_backup_active()
        try:
            _run_backup(
                source_connection,
                destination_connection,
                pages=pages,
                progress=progress,
                sleep=0.0,
            )
            return
        except sqlite3.Error as exc:
            if not _is_busy_error(exc):
                raise
            try:
                _sleep_for_retry(deadlines, retry_sleep)
            except SQLiteSnapshotTimeout as timeout_exc:
                raise timeout_exc from exc


def _backup_retry_sleep(timeout_seconds: float) -> float:
    return min(0.0025, max(0.0005, timeout_seconds / 10.0))


def _sleep_for_retry(deadlines: _SnapshotDeadlineState, retry_sleep: float) -> None:
    remaining = min(
        deadlines.inactivity_deadline,
        deadlines.absolute_deadline,
    ) - time.monotonic()
    if remaining <= 0:
        deadlines.ensure_backup_active(busy_or_locked=True)
    time.sleep(min(retry_sleep, remaining))
    deadlines.ensure_backup_active(busy_or_locked=True)


def _estimate_snapshot_output_bytes(source_path: Path) -> int:
    estimated_bytes = source_path.stat().st_size
    wal_path = Path(f"{source_path}-wal")
    try:
        if wal_path.is_file():
            estimated_bytes += wal_path.stat().st_size
    except FileNotFoundError:
        # A WAL may disappear between the existence and stat checks.
        pass
    return max(estimated_bytes, 1)


def _absolute_timeout_seconds(estimated_output_bytes: int) -> float:
    policy = SQLITE_SNAPSHOT_POLICY
    calculated = (
        policy.absolute_base_seconds
        + estimated_output_bytes / policy.estimated_bytes_per_second
    )
    return min(
        max(calculated, policy.minimum_absolute_timeout_seconds),
        policy.maximum_absolute_timeout_seconds,
    )


def _required_free_bytes(estimated_output_bytes: int) -> int:
    policy = SQLITE_SNAPSHOT_POLICY
    fractional_reserve = math.ceil(
        estimated_output_bytes * policy.free_space_reserve_fraction
    )
    reserve = max(policy.minimum_free_space_reserve_bytes, fractional_reserve)
    return estimated_output_bytes + reserve


def _ensure_snapshot_capacity(
    destination_parent: Path,
    *,
    estimated_output_bytes: int,
) -> None:
    available_bytes = shutil.disk_usage(destination_parent).free
    if available_bytes < _required_free_bytes(estimated_output_bytes):
        raise SQLiteSnapshotError(
            "SQLite snapshot destination does not have enough free space."
        )


def _is_busy_error(exc: sqlite3.Error) -> bool:
    error_code = getattr(exc, "sqlite_errorcode", None)
    if isinstance(error_code, int) and _primary_result_code(error_code) in (
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
    ):
        return True
    message = str(exc).lower()
    return "busy" in message or "locked" in message


def _primary_result_code(status: int) -> int:
    return int(status) & 0xFF


def _create_temp_path(destination_path: Path) -> Path:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".snapshot.tmp",
        dir=destination_path.parent,
    )
    os.close(descriptor)
    return Path(temp_name)


def _validate_snapshot(
    snapshot_path: Path,
    deadlines: _SnapshotDeadlineState,
) -> tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]:
    try:
        deadlines.ensure_before_absolute_deadline()
        with closing(_connect_read_only(snapshot_path.resolve())) as connection:
            integrity_check = tuple(
                str(row[0])
                for row in connection.execute("PRAGMA integrity_check").fetchall()
            )
            deadlines.ensure_before_absolute_deadline()
            foreign_key_violations = tuple(
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
            )
            deadlines.ensure_before_absolute_deadline()
    except sqlite3.Error as exc:
        raise SQLiteSnapshotError("SQLite snapshot validation could not be completed.") from exc

    if integrity_check != ("ok",):
        raise SQLiteSnapshotError("SQLite snapshot failed integrity validation.")
    if foreign_key_violations:
        raise SQLiteSnapshotError("SQLite snapshot failed foreign-key validation.")
    return integrity_check, foreign_key_violations


def _hash_file(path: Path, deadlines: _SnapshotDeadlineState) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as snapshot_file:
        for chunk in iter(lambda: snapshot_file.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
            deadlines.ensure_before_absolute_deadline()
    return byte_count, digest.hexdigest()


def _sync_file(path: Path) -> None:
    # Windows requires a writable descriptor for FlushFileBuffers/os.fsync.
    with path.open("r+b") as snapshot_file:
        os.fsync(snapshot_file.fileno())


def _atomic_replace(source_path: Path, destination_path: Path) -> None:
    os.replace(source_path, destination_path)
    try:
        _sync_parent_directory_best_effort(destination_path.parent)
    except Exception:
        # Publication already succeeded. A best-effort durability helper must
        # never turn that success into an ambiguous reported failure.
        pass


def _sync_parent_directory_best_effort(parent_path: Path) -> None:
    if not _supports_directory_fsync():
        return
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(parent_path, flags)
        os.fsync(descriptor)
    except OSError:
        # Publication already succeeded; directory durability cannot safely be
        # reported as a failed snapshot at this point.
        pass
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _supports_directory_fsync() -> bool:
    return os.name == "posix"


def _remove_incomplete_temp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    _remove_incomplete_sidecars(path)


def _remove_incomplete_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            Path(f"{path}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass
