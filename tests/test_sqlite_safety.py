from __future__ import annotations

import errno
import hashlib
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.sqlite_safety import (
    BackupProgress,
    SQLITE_SNAPSHOT_POLICY,
    SQLiteSnapshotError,
    SQLiteSnapshotHooks,
    SQLiteSnapshotTimeout,
    calculate_migration_sizing,
    collect_migration_storage_evidence,
    ensure_migration_free_space,
    migration_free_space_reserve,
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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


def test_snapshot_policy_is_immutable_and_matches_production_budgets():
    assert SQLITE_SNAPSHOT_POLICY.inactivity_timeout_seconds == 15.0
    assert SQLITE_SNAPSHOT_POLICY.absolute_base_seconds == 15.0
    assert SQLITE_SNAPSHOT_POLICY.estimated_bytes_per_second == 1024 * 1024
    assert SQLITE_SNAPSHOT_POLICY.minimum_absolute_timeout_seconds == 30.0
    assert SQLITE_SNAPSHOT_POLICY.maximum_absolute_timeout_seconds == 300.0
    assert SQLITE_SNAPSHOT_POLICY.minimum_free_space_reserve_bytes == 64 * 1024 * 1024
    assert SQLITE_SNAPSHOT_POLICY.free_space_reserve_fraction == 0.25
    with pytest.raises(FrozenInstanceError):
        SQLITE_SNAPSHOT_POLICY.inactivity_timeout_seconds = 5.0


def test_size_aware_absolute_budget_and_capacity_reserve_are_bounded():
    from player_wiki import sqlite_safety

    mib = 1024 * 1024
    assert sqlite_safety._absolute_timeout_seconds(1) == 30.0
    assert sqlite_safety._absolute_timeout_seconds(96 * mib) == 111.0
    assert sqlite_safety._absolute_timeout_seconds(1024 * mib) == 300.0
    assert sqlite_safety._required_free_bytes(96 * mib) == 160 * mib
    assert sqlite_safety._required_free_bytes(400 * mib) == 500 * mib


def test_migration_sizing_uses_main_page_and_wal_footprints_exactly():
    mib = 1024 * 1024
    sizing = calculate_migration_sizing(
        main_apparent_bytes=20 * mib,
        page_count=8_192,
        page_size=4_096,
        wal_apparent_bytes=24 * mib,
    )

    assert sizing.main_apparent_bytes == 20 * mib
    assert sizing.page_footprint_bytes == 32 * mib
    assert sizing.baseline_bytes == 32 * mib
    assert sizing.snapshot_bytes == 44 * mib
    assert sizing.working_bytes == 32 * mib
    assert migration_free_space_reserve(76 * mib) == 64 * mib
    assert sizing.pre_required_free_bytes == 140 * mib
    assert sizing.post_required_free_bytes == 96 * mib


def test_migration_sizing_uses_page_footprint_for_sparse_main_and_quarter_reserve():
    mib = 1024 * 1024
    sizing = calculate_migration_sizing(
        main_apparent_bytes=1,
        page_count=100_000,
        page_size=4_096,
        wal_apparent_bytes=0,
    )

    assert sizing.baseline_bytes == 409_600_000
    assert sizing.snapshot_bytes == sizing.baseline_bytes
    assert sizing.working_bytes == sizing.baseline_bytes
    pre_work = 2 * sizing.baseline_bytes
    assert sizing.pre_required_free_bytes == pre_work + (pre_work + 3) // 4
    assert sizing.post_required_free_bytes == (
        sizing.working_bytes + (sizing.working_bytes + 3) // 4
    )


def test_migration_storage_evidence_uses_sparse_file_apparent_size(tmp_path):
    database_path = tmp_path / "sparse.sqlite3"
    apparent_bytes = 256 * 1024 * 1024
    database_path.touch()
    os.truncate(database_path, apparent_bytes)

    class PragmaConnection:
        def execute(self, sql):
            value = 0 if "page_count" in sql else 4_096
            return SimpleNamespace(fetchone=lambda: (value,))

    evidence = collect_migration_storage_evidence(PragmaConnection(), database_path)

    assert evidence.sizing.main_apparent_bytes == apparent_bytes
    assert evidence.sizing.baseline_bytes == apparent_bytes
    assert evidence.sizing.working_bytes == apparent_bytes


@pytest.mark.parametrize(
    "values",
    [
        {
            "main_apparent_bytes": -1,
            "page_count": 1,
            "page_size": 4_096,
            "wal_apparent_bytes": 0,
        },
        {
            "main_apparent_bytes": 1,
            "page_count": -1,
            "page_size": 4_096,
            "wal_apparent_bytes": 0,
        },
        {
            "main_apparent_bytes": 1,
            "page_count": 1,
            "page_size": 0,
            "wal_apparent_bytes": 0,
        },
        {
            "main_apparent_bytes": 1,
            "page_count": 1,
            "page_size": 4_096,
            "wal_apparent_bytes": -1,
        },
    ],
)
def test_migration_sizing_rejects_invalid_evidence(values):
    with pytest.raises(ValueError, match="Migration"):
        calculate_migration_sizing(**values)


def test_migration_free_space_exact_boundary_passes_and_one_under_fails(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    required = 123_456_789
    monkeypatch.setattr(
        sqlite_safety.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=required, used=0, free=required),
    )
    ensure_migration_free_space(tmp_path, required_free_bytes=required)

    monkeypatch.setattr(
        sqlite_safety.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=required, used=1, free=required - 1),
    )
    with pytest.raises(SQLiteSnapshotError, match="enough free space"):
        ensure_migration_free_space(tmp_path, required_free_bytes=required)


def test_migration_storage_evidence_includes_regular_wal_apparent_bytes(tmp_path):
    database_path = tmp_path / "wal.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE items (value TEXT NOT NULL)")
        connection.execute("INSERT INTO items VALUES ('committed')")
        connection.commit()
        wal_path = Path(f"{database_path}-wal")
        assert wal_path.is_file()

        evidence = collect_migration_storage_evidence(connection, database_path)

        assert evidence.sizing.main_apparent_bytes == database_path.stat().st_size
        assert evidence.sizing.wal_apparent_bytes == wal_path.stat().st_size
        assert evidence.sizing.page_footprint_bytes == (
            connection.execute("PRAGMA page_count").fetchone()[0]
            * connection.execute("PRAGMA page_size").fetchone()[0]
        )
        assert evidence.sizing.snapshot_bytes == max(
            evidence.sizing.baseline_bytes,
            evidence.sizing.main_apparent_bytes + evidence.sizing.wal_apparent_bytes,
        )


def test_migration_storage_evidence_rejects_nonregular_wal(tmp_path):
    database_path = tmp_path / "unsafe-wal.sqlite3"
    create_database(database_path)
    wal_path = Path(f"{database_path}-wal")
    wal_path.mkdir()
    with sqlite3.connect(database_path) as connection:
        with pytest.raises(SQLiteSnapshotError, match="WAL storage evidence"):
            collect_migration_storage_evidence(connection, database_path)


def test_migration_storage_evidence_treats_disappearing_wal_as_zero(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "disappearing-wal.sqlite3"
    create_database(database_path)
    wal_path = Path(f"{database_path}-wal")
    original = Path.lstat

    def disappear(path):
        if Path(path) == wal_path:
            raise FileNotFoundError("private path")
        return original(path)

    monkeypatch.setattr(Path, "lstat", disappear)
    with sqlite3.connect(database_path) as connection:
        evidence = collect_migration_storage_evidence(connection, database_path)

    assert evidence.sizing.wal_apparent_bytes == 0


@pytest.mark.parametrize("invalid_row", [None, (), ("4096",), (-1,), (1, 2)])
def test_migration_storage_evidence_rejects_invalid_pragma_rows(
    tmp_path,
    invalid_row,
):
    database_path = tmp_path / "invalid-pragma.sqlite3"
    create_database(database_path)

    class InvalidPragmaConnection:
        def execute(self, _sql):
            return SimpleNamespace(fetchone=lambda: invalid_row)

    with pytest.raises(SQLiteSnapshotError, match="could not be measured safely"):
        collect_migration_storage_evidence(InvalidPragmaConnection(), database_path)


def test_migration_storage_evidence_rejects_invalid_main_stat(tmp_path, monkeypatch):
    database_path = tmp_path / "invalid-stat.sqlite3"
    create_database(database_path)
    original = Path.lstat

    def invalid_stat(path):
        value = original(path)
        if Path(path) == database_path:
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_size=-1,
                st_dev=value.st_dev,
                st_ino=value.st_ino,
                st_file_attributes=getattr(value, "st_file_attributes", 0),
            )
        return value

    monkeypatch.setattr(Path, "lstat", invalid_stat)
    with sqlite3.connect(database_path) as connection:
        with pytest.raises(SQLiteSnapshotError, match="unavailable or unsafe"):
            collect_migration_storage_evidence(connection, database_path)


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


def test_real_large_database_snapshot_completes_with_size_aware_budget(tmp_path):
    source_path = tmp_path / "source-large.sqlite3"
    destination_path = tmp_path / "snapshot-large.sqlite3"
    with sqlite3.connect(source_path) as connection:
        connection.execute("CREATE TABLE payloads (id INTEGER PRIMARY KEY, payload BLOB NOT NULL)")
        connection.execute(
            "INSERT INTO payloads (payload) VALUES (zeroblob(?))",
            (88 * 1024 * 1024,),
        )
        connection.commit()

    assert 86 * 1024 * 1024 <= source_path.stat().st_size <= 96 * 1024 * 1024
    evidence = snapshot_sqlite_database(
        source_path=source_path,
        destination_path=destination_path,
    )

    assert evidence.byte_count == destination_path.stat().st_size
    with destination_path.open("rb") as snapshot_file:
        assert evidence.sha256 == hashlib.file_digest(snapshot_file, "sha256").hexdigest()
    with sqlite3.connect(destination_path) as connection:
        assert connection.execute("SELECT length(payload) FROM payloads").fetchone()[0] == 88 * 1024 * 1024


def test_wal_bytes_are_included_in_conservative_output_estimate(tmp_path):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    with sqlite3.connect(source_path) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("CREATE TABLE payloads (payload BLOB NOT NULL)")
        writer.execute("INSERT INTO payloads VALUES (zeroblob(1048576))")
        writer.commit()
        wal_path = Path(f"{source_path}-wal")
        expected = source_path.stat().st_size + wal_path.stat().st_size

        assert sqlite_safety._estimate_snapshot_output_bytes(source_path.resolve()) == expected


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


def test_decreasing_page_progress_can_run_longer_than_legacy_five_second_budget(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path, rows=20)
    clock = FakeClock()
    original_run_backup = sqlite_safety._run_backup

    def slow_healthy_backup(source, destination, *, pages, progress, sleep):
        progress(sqlite3.SQLITE_OK, 4, 4)
        for remaining in (3, 2, 1):
            clock.now += 6.0
            progress(sqlite3.SQLITE_OK, remaining, 4)
        original_run_backup(
            source,
            destination,
            pages=pages,
            progress=progress,
            sleep=sleep,
        )

    monkeypatch.setattr(sqlite_safety, "time", clock)
    monkeypatch.setattr(sqlite_safety, "_run_backup", slow_healthy_backup)

    evidence = snapshot_sqlite_database(
        source_path=source_path,
        destination_path=destination_path,
        pages_per_step=1,
    )

    assert evidence.elapsed_seconds == 18.0
    assert read_values(destination_path) == [f"value-{index}" for index in range(20)]


def test_decreasing_trickle_progress_cannot_exceed_size_aware_absolute_cap(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")
    clock = FakeClock()

    def endless_trickle(_source, _destination, *, pages, progress, sleep):
        assert pages == 1
        assert sleep == 0.0
        progress(sqlite3.SQLITE_OK, 100, 100)
        remaining = 99
        while True:
            clock.now += 10.0
            progress(sqlite3.SQLITE_OK, remaining, 100)
            remaining -= 1

    monkeypatch.setattr(sqlite_safety, "time", clock)
    monkeypatch.setattr(sqlite_safety, "_run_backup", endless_trickle)

    with pytest.raises(SQLiteSnapshotTimeout, match="absolute deadline"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            pages_per_step=1,
        )

    assert clock.now == 30.0
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_unchanged_success_progress_does_not_reset_inactivity_budget(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")
    clock = FakeClock()

    def stalled_success(_source, _destination, *, pages, progress, sleep):
        progress(sqlite3.SQLITE_OK, 1, 1)
        clock.now += 16.0
        progress(sqlite3.SQLITE_OK, 1, 1)

    monkeypatch.setattr(sqlite_safety, "time", clock)
    monkeypatch.setattr(sqlite_safety, "_run_backup", stalled_success)

    with pytest.raises(SQLiteSnapshotTimeout, match="made no progress"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            pages_per_step=1,
        )

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_late_meaningful_progress_cannot_revive_expired_inactivity_budget(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")
    clock = FakeClock()

    def late_progress(_source, _destination, *, pages, progress, sleep):
        progress(sqlite3.SQLITE_OK, 2, 2)
        clock.now += 16.0
        progress(sqlite3.SQLITE_OK, 1, 2)

    monkeypatch.setattr(sqlite_safety, "time", clock)
    monkeypatch.setattr(sqlite_safety, "_run_backup", late_progress)

    with pytest.raises(SQLiteSnapshotTimeout, match="made no progress"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            pages_per_step=1,
        )

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


@pytest.mark.parametrize("timeout_seconds", [0.025, 0.05, 0.1])
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
        with pytest.raises(SQLiteSnapshotTimeout, match=r"busy|locked"):
            snapshot_sqlite_database(
                source_path=source_path,
                destination_path=destination_path,
                timeout_seconds=timeout_seconds,
                pages_per_step=1,
            )
        elapsed = time.monotonic() - started_at

    # The deterministic fake-clock busy/locked test below owns the 10 ms case.
    # The fixed 250 ms allowance covers Windows and loaded-runner scheduling
    # without scaling the allowed overrun with the requested deadline. The
    # lower bound still proves the application deadline was honored.
    assert timeout_seconds - 0.004 <= elapsed <= timeout_seconds + 0.25
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
    with pytest.raises(SQLiteSnapshotTimeout, match="busy or locked"):
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


@pytest.mark.parametrize("stage", ["validation", "hash"])
def test_postcopy_work_can_exceed_inactivity_budget_below_absolute_cap(
    tmp_path,
    monkeypatch,
    stage,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path, rows=20)
    clock = FakeClock()
    seam_name = "_validate_snapshot" if stage == "validation" else "_hash_file"
    original = getattr(sqlite_safety, seam_name)

    def delayed(*args, **kwargs):
        clock.now += 20.0
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite_safety, "time", clock)
    monkeypatch.setattr(
        sqlite_safety,
        seam_name,
        delayed,
    )

    evidence = snapshot_sqlite_database(
        source_path=source_path,
        destination_path=destination_path,
        pages_per_step=1,
    )

    assert evidence.elapsed_seconds == 20.0
    assert read_values(destination_path) == [f"value-{index}" for index in range(20)]


@pytest.mark.parametrize("stage", ["validation", "hash"])
def test_postcopy_work_beyond_absolute_cap_fails_closed(tmp_path, monkeypatch, stage):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path, rows=20)
    destination_path.write_bytes(b"existing-destination")
    clock = FakeClock()
    seam_name = "_validate_snapshot" if stage == "validation" else "_hash_file"
    original = getattr(sqlite_safety, seam_name)

    def delayed(*args, **kwargs):
        clock.now += 31.0
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite_safety, "time", clock)
    monkeypatch.setattr(sqlite_safety, seam_name, delayed)

    with pytest.raises(SQLiteSnapshotTimeout, match="absolute deadline"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            pages_per_step=1,
        )

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_capacity_preflight_fails_before_temp_creation_and_preserves_destination(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")
    estimated_bytes = sqlite_safety._estimate_snapshot_output_bytes(source_path.resolve())
    required_bytes = sqlite_safety._required_free_bytes(estimated_bytes)
    temp_creation_attempted = False

    def record_temp_attempt(_destination):
        nonlocal temp_creation_attempted
        temp_creation_attempted = True
        raise AssertionError("capacity preflight must run before temp creation")

    monkeypatch.setattr(
        sqlite_safety.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=required_bytes, used=1, free=required_bytes - 1),
    )
    monkeypatch.setattr(sqlite_safety, "_create_temp_path", record_temp_attempt)

    with pytest.raises(SQLiteSnapshotError, match="enough free space"):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
        )

    assert temp_creation_attempted is False
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


@pytest.mark.parametrize("failure_stage", ["backup", "fsync"])
def test_runtime_enospc_preserves_destination_and_cleans_temp(
    tmp_path,
    monkeypatch,
    failure_stage,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")

    def raise_enospc(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "injected no space left")

    if failure_stage == "backup":
        monkeypatch.setattr(sqlite_safety, "_run_backup", raise_enospc)
    else:
        monkeypatch.setattr(sqlite_safety, "_sync_file", raise_enospc)

    with pytest.raises(SQLiteSnapshotError, match="published safely") as exc_info:
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
        )

    assert isinstance(exc_info.value.__cause__, OSError)
    assert exc_info.value.__cause__.errno == errno.ENOSPC
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


def test_sqlite_full_during_backup_preserves_destination_and_cleans_temp(
    tmp_path,
    monkeypatch,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")
    disk_full = sqlite3.OperationalError("injected database or disk is full")
    disk_full.sqlite_errorcode = sqlite3.SQLITE_FULL

    monkeypatch.setattr(
        sqlite_safety,
        "_run_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(disk_full),
    )

    with pytest.raises(SQLiteSnapshotError, match="failed before publication") as exc_info:
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
        )

    assert exc_info.value.__cause__ is disk_full
    assert disk_full.sqlite_errorcode == sqlite3.SQLITE_FULL
    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


@pytest.mark.parametrize("interrupt_type", [KeyboardInterrupt, SystemExit])
def test_process_interrupts_preserve_destination_and_clean_temp(
    tmp_path,
    interrupt_type,
):
    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path)
    destination_path.write_bytes(b"existing-destination")

    def interrupt_after_temp(_temp_path):
        raise interrupt_type()

    with pytest.raises(interrupt_type):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            hooks=SQLiteSnapshotHooks(after_temp_create=interrupt_after_temp),
        )

    assert destination_path.read_bytes() == b"existing-destination"
    assert snapshot_temps(destination_path) == []


@pytest.mark.parametrize("stage", ["progress", "validation", "hash"])
@pytest.mark.parametrize("interrupt_type", [KeyboardInterrupt, SystemExit])
def test_base_exceptions_during_processing_clean_temp_and_preserve_destination(
    tmp_path,
    monkeypatch,
    stage,
    interrupt_type,
):
    from player_wiki import sqlite_safety

    source_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    create_database(source_path, rows=20)
    destination_path.write_bytes(b"existing-destination")
    hooks = SQLiteSnapshotHooks()

    def interrupt(*_args, **_kwargs):
        raise interrupt_type()

    if stage == "progress":
        hooks = SQLiteSnapshotHooks(on_progress=interrupt)
    else:
        monkeypatch.setattr(
            sqlite_safety,
            "_validate_snapshot" if stage == "validation" else "_hash_file",
            interrupt,
        )

    with pytest.raises(interrupt_type):
        snapshot_sqlite_database(
            source_path=source_path,
            destination_path=destination_path,
            pages_per_step=1,
            hooks=hooks,
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
