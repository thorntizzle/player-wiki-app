from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import closing
from dataclasses import fields
from pathlib import Path

import pytest

from player_wiki.sqlite_safety import (
    BackupProgress,
    SQLiteSnapshotError,
    SQLiteSnapshotHooks,
    SQLiteSnapshotTimeout,
    snapshot_sqlite_database,
)


EXTENDED_BUSY_OR_LOCKED_CODES = [
    ("BUSY_RECOVERY", getattr(sqlite3, "SQLITE_BUSY_RECOVERY", 261)),
    ("BUSY_SNAPSHOT", getattr(sqlite3, "SQLITE_BUSY_SNAPSHOT", 517)),
    ("BUSY_TIMEOUT", getattr(sqlite3, "SQLITE_BUSY_TIMEOUT", 773)),
    ("LOCKED_SHAREDCACHE", getattr(sqlite3, "SQLITE_LOCKED_SHAREDCACHE", 262)),
    ("LOCKED_VTAB", getattr(sqlite3, "SQLITE_LOCKED_VTAB", 518)),
]


def create_database(path: Path, *, rows: int = 1) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO items (value) VALUES (?)",
            [(f"value-{index}",) for index in range(rows)],
        )
        connection.commit()


def read_values(path: Path) -> list[str]:
    with sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro", uri=True
    ) as connection:
        return [str(row[0]) for row in connection.execute("SELECT value FROM items ORDER BY id")]


def snapshot_temps(destination_path: Path) -> list[Path]:
    return list(destination_path.parent.glob(f".{destination_path.name}.*.snapshot.tmp*"))


def test_snapshot_publishes_valid_database_with_deterministic_evidence(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    first_destination = tmp_path / "first.sqlite3"
    second_destination = tmp_path / "second.sqlite3"
    create_database(source_path, rows=5)

    first = snapshot_sqlite_database(source_path=source_path, destination_path=first_destination)
    second = snapshot_sqlite_database(source_path=source_path, destination_path=second_destination)

    expected_hash = hashlib.sha256(first_destination.read_bytes()).hexdigest()
    assert read_values(first_destination) == [f"value-{index}" for index in range(5)]
    assert first.final_path == first_destination.resolve()
    assert first.byte_count == first_destination.stat().st_size
    assert first.sha256 == expected_hash
    assert first.integrity_check == ("ok",)
    assert first.foreign_key_violations == ()
    assert first.progress_calls >= 1
    assert first.remaining_pages == 0
    assert first.elapsed_seconds >= 0
    assert (second.byte_count, second.sha256) == (first.byte_count, first.sha256)


def test_snapshot_includes_committed_wal_rows_without_copying_sidecars_or_changing_source(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"

    with sqlite3.connect(source_path) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        writer.execute("INSERT INTO items (value) VALUES ('wal-committed')")
        writer.commit()

        wal_path = Path(f"{source_path}-wal")
        shm_path = Path(f"{source_path}-shm")
        before = {path: path.read_bytes() for path in (source_path, wal_path)}
        shm_size = shm_path.stat().st_size
        snapshot_sqlite_database(source_path=source_path, destination_path=destination_path)

        assert not Path(f"{destination_path}-wal").exists()
        assert not Path(f"{destination_path}-shm").exists()
        assert read_values(destination_path) == ["wal-committed"]
        assert read_values(source_path) == ["wal-committed"]
        assert {path: path.read_bytes() for path in (source_path, wal_path)} == before
        # A read-only WAL connection may update ephemeral read marks/locks in
        # SHM, but it must not replace, resize, copy, or publish that sidecar.
        assert shm_path.exists()
        assert shm_path.stat().st_size == shm_size

def test_concurrent_wal_commit_yields_one_consistent_committed_snapshot(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    with sqlite3.connect(source_path) as connection:
        connection.execute("PRAGMA page_size=512")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO items (value) VALUES (?)",
            [(f"seed-{index}-" + "x" * 300,) for index in range(40)],
        )
        connection.commit()

    wrote_concurrent_transaction = False

    def write_during_backup(_progress) -> None:
        nonlocal wrote_concurrent_transaction
        if wrote_concurrent_transaction:
            return
        wrote_concurrent_transaction = True
        with sqlite3.connect(source_path) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("INSERT INTO items (value) VALUES ('transaction-start')")
            writer.execute("INSERT INTO items (value) VALUES ('transaction-end')")
            writer.commit()

    snapshot_sqlite_database(
        source_path=source_path,
        destination_path=destination_path,
        pages_per_step=1,
        hooks=SQLiteSnapshotHooks(on_progress=write_during_backup),
    )

    snapshot_values = read_values(destination_path)
    markers = [value for value in snapshot_values if value.startswith("transaction-")]
    assert wrote_concurrent_transaction
    assert markers in ([], ["transaction-start", "transaction-end"])
    assert read_values(source_path)[-2:] == ["transaction-start", "transaction-end"]


@pytest.mark.parametrize("source_kind", ["missing", "directory", "corrupt"])
def test_invalid_sources_fail_without_publishing_or_leaving_temp_files(tmp_path, source_kind):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    destination_path.write_bytes(b"existing-destination")
    if source_kind == "directory":
        source_path.mkdir()
    elif source_kind == "corrupt":
        source_path.write_bytes(b"not a sqlite database")

    expected_exception = FileNotFoundError if source_kind == "missing" else SQLiteSnapshotError
    with pytest.raises(expected_exception):
        snapshot_sqlite_database(source_path=source_path, destination_path=destination_path)

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []
    if source_kind == "missing":
        assert not source_path.exists()
    else:
        assert source_path.exists()


@pytest.mark.parametrize("timeout_seconds", [0.01, 0.025, 0.05, 0.1])
def test_locked_source_stops_at_application_deadline_and_preserves_destination(
    tmp_path,
    timeout_seconds,
):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")

    with sqlite3.connect(source_path, timeout=0) as lock_connection:
        lock_connection.execute("BEGIN EXCLUSIVE")
        started_at = time.monotonic()
        with pytest.raises(SQLiteSnapshotTimeout, match=r"timed out|deadline"):
            snapshot_sqlite_database(
                source_path=source_path,
                destination_path=destination_path,
                timeout_seconds=timeout_seconds,
                pages_per_step=1,
            )
        elapsed = time.monotonic() - started_at

    # The fixed 250 ms allowance covers Windows and loaded-runner scheduling
    # without scaling the allowed overrun with the requested deadline. The
    # lower bound still proves the application deadline was honored.
    assert timeout_seconds - 0.004 <= elapsed <= timeout_seconds + 0.25
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_pre_validation_delay_consumes_application_deadline(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")

    started_at = time.monotonic()
    with pytest.raises(SQLiteSnapshotTimeout, match=r"timed out|deadline"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            timeout_seconds=0.01,
            hooks=SQLiteSnapshotHooks(
                before_validation=lambda _path: time.sleep(0.02)
            ),
        )
    elapsed = time.monotonic() - started_at

    assert 0.01 <= elapsed <= 0.05
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


@pytest.mark.parametrize(
    ("status_name", "extended_status"),
    EXTENDED_BUSY_OR_LOCKED_CODES,
    ids=[item[0] for item in EXTENDED_BUSY_OR_LOCKED_CODES],
)
def test_extended_busy_and_locked_progress_statuses_back_off_until_deadline(
    tmp_path,
    monkeypatch,
    status_name,
    extended_status,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")
    observed: list[BackupProgress] = []
    requested_sleeps: list[float] = []

    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, duration: float) -> None:
            requested_sleeps.append(duration)
            self.now += duration

    fake_clock = FakeClock()

    def report_only_extended_status(
        _source_connection,
        _destination_connection,
        *,
        pages,
        progress,
        sleep,
    ) -> None:
        assert pages == 1
        assert sleep == 0.0
        while True:
            progress(extended_status, 1, 1)

    monkeypatch.setattr(sqlite_safety, "time", fake_clock)
    monkeypatch.setattr(sqlite_safety, "_run_backup", report_only_extended_status)
    extended_error = sqlite3.OperationalError("injected extended result")
    extended_error.sqlite_errorcode = extended_status

    started_at = fake_clock.monotonic()
    with pytest.raises(SQLiteSnapshotTimeout, match="timed out"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            timeout_seconds=0.01,
            pages_per_step=1,
            hooks=SQLiteSnapshotHooks(on_progress=observed.append),
        )
    elapsed = fake_clock.monotonic() - started_at

    assert status_name
    assert sqlite_safety._is_busy_error(extended_error)
    assert observed
    assert all(progress.status == extended_status for progress in observed)
    assert [progress.busy_retries for progress in observed] == list(
        range(1, len(observed) + 1)
    )
    assert requested_sleeps
    assert len(requested_sleeps) == len(observed)
    assert all(0 < duration <= 0.001 for duration in requested_sleeps)
    assert len(observed) <= 25
    assert elapsed == pytest.approx(0.01)
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_foreign_key_validation_failure_preserves_existing_destination(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    with sqlite3.connect(source_path) as connection:
        connection.executescript(
            """
            CREATE TABLE parents (id INTEGER PRIMARY KEY);
            CREATE TABLE children (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES parents(id)
            );
            INSERT INTO children (parent_id) VALUES (999);
            """
        )
    destination_path.write_bytes(b"existing-destination")

    with pytest.raises(SQLiteSnapshotError, match="foreign-key validation"):
        snapshot_sqlite_database(source_path=source_path, destination_path=destination_path)

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_integrity_failure_injection_preserves_destination_and_cleans_temp(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")

    def corrupt_before_validation(temp_path: Path) -> None:
        temp_path.write_bytes(b"corrupt after backup")

    with pytest.raises(SQLiteSnapshotError, match="validation"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            hooks=SQLiteSnapshotHooks(before_validation=corrupt_before_validation),
        )

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


@pytest.mark.parametrize("failure_stage", ["temp", "backup", "progress", "publish"])
def test_injected_stage_failures_preserve_destination_and_clean_temp(tmp_path, monkeypatch, failure_stage):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path, rows=20)
    source_before = source_path.read_bytes()
    destination_path.write_bytes(b"existing-destination")

    hooks = SQLiteSnapshotHooks()
    if failure_stage == "temp":
        monkeypatch.setattr(
            "player_wiki.sqlite_safety._create_temp_path",
            lambda _destination: (_ for _ in ()).throw(OSError("injected temp failure")),
        )
    elif failure_stage == "backup":
        monkeypatch.setattr(
            "player_wiki.sqlite_safety._run_backup",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                sqlite3.OperationalError("injected backup failure")
            ),
        )
    elif failure_stage == "progress":
        hooks = SQLiteSnapshotHooks(
            on_progress=lambda _progress: (_ for _ in ()).throw(RuntimeError("injected progress failure"))
        )
    else:
        monkeypatch.setattr(
            "player_wiki.sqlite_safety._atomic_replace",
            lambda _source, _destination: (_ for _ in ()).throw(OSError("injected publish failure")),
        )

    expected_exception = RuntimeError if failure_stage == "progress" else SQLiteSnapshotError
    with pytest.raises(expected_exception):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            pages_per_step=1,
            hooks=hooks,
        )

    assert source_path.read_bytes() == source_before
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_source_and_destination_must_differ(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    create_database(source_path)
    before = source_path.read_bytes()

    with pytest.raises(SQLiteSnapshotError, match="must differ"):
        snapshot_sqlite_database(source_path=source_path, destination_path=source_path)

    assert source_path.read_bytes() == before


def test_no_public_post_validation_path_hook_and_published_evidence_matches_bytes(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    bytes_at_replace = b""

    def add_valid_row_before_validation(temp_path: Path) -> None:
        with closing(sqlite3.connect(temp_path)) as connection:
            connection.execute("INSERT INTO items (value) VALUES ('validated-adversarial-row')")
            connection.commit()

    from player_wiki import sqlite_safety

    original_atomic_replace = sqlite_safety._atomic_replace

    def inspect_atomic_replace(temp_path: Path, final_path: Path) -> None:
        nonlocal bytes_at_replace
        bytes_at_replace = temp_path.read_bytes()
        original_atomic_replace(temp_path, final_path)

    monkeypatch.setattr(sqlite_safety, "_atomic_replace", inspect_atomic_replace)

    evidence = snapshot_sqlite_database(
        source_path=source_path,
        destination_path=destination_path,
        hooks=SQLiteSnapshotHooks(before_validation=add_valid_row_before_validation),
    )
    published_bytes = destination_path.read_bytes()

    assert "before_publish" not in {field.name for field in fields(SQLiteSnapshotHooks)}
    assert read_values(destination_path)[-1] == "validated-adversarial-row"
    assert bytes_at_replace == published_bytes
    assert evidence.byte_count == len(published_bytes)
    assert evidence.sha256 == hashlib.sha256(published_bytes).hexdigest()


def test_best_effort_directory_fsync_runs_after_publish_without_reporting_failure(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    calls = []
    monkeypatch.setattr(sqlite_safety, "_supports_directory_fsync", lambda: True)
    monkeypatch.setattr(sqlite_safety.os, "open", lambda path, flags: calls.append((path, flags)) or 123)
    monkeypatch.setattr(
        sqlite_safety.os,
        "fsync",
        lambda descriptor: (_ for _ in ()).throw(OSError("injected directory fsync failure")),
    )
    monkeypatch.setattr(sqlite_safety.os, "close", lambda descriptor: calls.append(("close", descriptor)))

    sqlite_safety._sync_parent_directory_best_effort(tmp_path)

    assert calls[0][0] == tmp_path
    assert calls[-1] == ("close", 123)


def test_post_publish_directory_sync_bug_cannot_report_atomic_replace_failure(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    temp_path = tmp_path / "temp.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    temp_path.write_bytes(b"published")
    destination_path.write_bytes(b"old")
    monkeypatch.setattr(
        sqlite_safety,
        "_sync_parent_directory_best_effort",
        lambda _path: (_ for _ in ()).throw(RuntimeError("injected sync bug")),
    )

    sqlite_safety._atomic_replace(temp_path, destination_path)

    assert destination_path.read_bytes() == b"published"
    assert not temp_path.exists()
