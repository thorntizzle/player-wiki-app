from __future__ import annotations

import errno
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.db import SCHEMA, init_database
from player_wiki.migrations import (
    BASELINE_SCHEMA_SQL,
    CURRENT_SCHEMA_SQL,
    MIGRATIONS,
    MigrationPayload,
    MigrationError,
    MigrationHooks,
    TransformSpec,
    calculate_migration_checksum,
    inspect_migration_ledger,
    run_migrations,
)
from player_wiki.sqlite_safety import (
    SQLiteSnapshotError,
    SQLiteSnapshotEvidence,
    snapshot_sqlite_database,
)


class _StatOverride:
    def __init__(self, base, **overrides):
        self._base = base
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._base, name)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _schema_statements_for(schema_sql: str) -> tuple[str, ...]:
    statements: list[str] = []
    buffer = ""
    for line in schema_sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    assert not buffer.strip()
    return tuple(statements)


def _schema_statements() -> tuple[str, ...]:
    return _schema_statements_for(SCHEMA)


def _create_current_unversioned(path: Path) -> None:
    with _connect(path) as connection:
        for statement in _schema_statements():
            connection.execute(statement)


def _ledger_rows(path: Path) -> list[tuple[int, str, str]]:
    with _connect(path) as connection:
        return [
            (int(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]


def _schema_and_data_fingerprint(path: Path) -> tuple[object, ...]:
    with _connect(path) as connection:
        schema = tuple(
            tuple(row)
            for row in connection.execute(
                """SELECT type, name, tbl_name, sql FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"""
            ).fetchall()
        )
        preferences = ()
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_preferences'"
        ).fetchone():
            preferences = tuple(
                tuple(row)
                for row in connection.execute("SELECT * FROM user_preferences ORDER BY user_id").fetchall()
            )
        return schema, preferences


def _downgrade_user_preferences(path: Path) -> None:
    with _connect(path) as connection:
        connection.execute("ALTER TABLE user_preferences RENAME TO user_preferences_current")
        connection.execute(
            """CREATE TABLE user_preferences (
            user_id INTEGER PRIMARY KEY,
            theme_key TEXT NOT NULL DEFAULT 'parchment',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)"""
        )
        connection.execute(
            """INSERT INTO user_preferences (user_id, theme_key, updated_at)
            SELECT user_id, theme_key, updated_at FROM user_preferences_current"""
        )
        connection.execute("DROP TABLE user_preferences_current")


def test_missing_database_applies_current_registry_without_pointless_backup(tmp_path):
    database_path = tmp_path / "data" / "wiki.sqlite3"

    result = init_database(database_path)

    assert result.from_version == 0
    assert result.to_version == 2
    assert result.applied_versions == (1, 2)
    assert result.applied_names == (
        "0001_legacy_current_baseline",
        "0002_player_wiki_reconciliation_operations",
    )
    assert result.backup_evidence is None
    assert result.no_op is False
    rows = _ledger_rows(database_path)
    assert rows == [
        (1, "0001_legacy_current_baseline", MIGRATIONS[0].checksum),
        (2, "0002_player_wiki_reconciliation_operations", MIGRATIONS[1].checksum),
    ]


def test_empty_existing_database_applies_without_backup(tmp_path):
    database_path = tmp_path / "empty.sqlite3"
    with _connect(database_path):
        pass

    result = init_database(database_path)

    assert result.applied_versions == (1, 2)
    assert result.backup_evidence is None


def test_current_unversioned_database_is_snapshotted_once_and_rows_preserved(tmp_path):
    database_path = tmp_path / "wiki.sqlite3"
    _create_current_unversioned(database_path)
    with _connect(database_path) as connection:
        connection.execute(
            """INSERT INTO users
            (email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at)
            VALUES ('legacy@example.test', 'Legacy', 0, 'active', NULL, 1, 'before', 'before')"""
        )
        connection.execute(
            """INSERT INTO user_preferences
            (user_id, theme_key, session_chat_order, frontend_mode, updated_at)
            VALUES (1, 'moonlit', 'oldest_first', 'flask', 'before')"""
        )

    result = init_database(database_path)

    assert result.backup_evidence is not None
    assert result.backup_path is not None
    assert result.backup_path.parent == tmp_path / "migration-backups" / "wiki"
    assert result.backup_evidence.integrity_check == ("ok",)
    assert result.backup_evidence.foreign_key_violations == ()
    assert result.backup_evidence.sha256 == hashlib.sha256(result.backup_path.read_bytes()).hexdigest()
    with _connect(database_path) as connection:
        preference_row = connection.execute(
            "SELECT theme_key, session_chat_order, frontend_mode FROM user_preferences"
        ).fetchone()
        assert tuple(preference_row) == (
            "moonlit",
            "oldest_first",
            "flask",
        )
    assert len(list((tmp_path / "migration-backups" / "wiki").glob("*.sqlite3"))) == 1


def test_second_init_is_true_no_op_without_write_or_backup(tmp_path):
    database_path = tmp_path / "wiki.sqlite3"
    init_database(database_path)
    before_ledger = _ledger_rows(database_path)
    statements: list[str] = []
    with _connect(database_path) as connection:
        connection.set_trace_callback(statements.append)
        result = run_migrations(connection, database_path=database_path, schema_sql=SCHEMA)

    assert result.no_op is True
    assert result.from_version == result.to_version == 2
    assert result.applied_versions == ()
    assert result.backup_evidence is None
    assert _ledger_rows(database_path) == before_ledger
    assert not any(
        statement.lstrip().upper().startswith(("BEGIN", "CREATE", "ALTER", "UPDATE", "INSERT", "DELETE", "DROP"))
        for statement in statements
    )
    assert not (tmp_path / "migration-backups").exists()


def test_read_only_ledger_inspector_reports_current_without_transaction_or_write(tmp_path):
    database_path = tmp_path / "wiki.sqlite3"
    init_database(database_path)
    before = database_path.read_bytes()
    lock_path = Path(f"{database_path}.migration.lock")
    before_lock = lock_path.read_bytes()
    statements: list[str] = []
    with _connect(database_path) as connection:
        connection.set_trace_callback(statements.append)
        inspection = inspect_migration_ledger(connection, schema_sql=SCHEMA)
        assert connection.in_transaction is False

    assert inspection.ledger_exists is True
    assert inspection.applied_version == inspection.current_version == 2
    assert inspection.is_current is True
    assert database_path.read_bytes() == before
    assert lock_path.read_bytes() == before_lock
    assert not (tmp_path / "migration-backups").exists()
    assert not any(
        statement.lstrip().upper().startswith(
            ("BEGIN", "CREATE", "ALTER", "UPDATE", "INSERT", "DELETE", "DROP", "COMMIT")
        )
        for statement in statements
    )


def test_read_only_ledger_inspector_reports_missing_without_creating_it(tmp_path):
    database_path = tmp_path / "empty.sqlite3"
    with _connect(database_path) as connection:
        inspection = inspect_migration_ledger(connection, schema_sql=SCHEMA)
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    assert inspection.ledger_exists is False
    assert inspection.applied_version == 0
    assert inspection.current_version == 2
    assert inspection.is_current is False
    assert tables == []
    assert not Path(f"{database_path}.migration.lock").exists()


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([(2, "0002_future", "a" * 64)], "gap"),
        (
                [
                    (1, MIGRATIONS[0].name, MIGRATIONS[0].checksum),
                    (2, MIGRATIONS[1].name, MIGRATIONS[1].checksum),
                    (3, "0003_future", "a" * 64),
                ],
            "newer",
        ),
        ([(1, "0001_wrong", MIGRATIONS[0].checksum)], "name"),
        ([(1, MIGRATIONS[0].name, "b" * 64)], "checksum"),
    ],
)
def test_invalid_existing_ledger_fails_closed_before_backup_or_schema_write(tmp_path, rows, message):
    database_path = tmp_path / "wiki.sqlite3"
    _create_current_unversioned(database_path)
    with _connect(database_path) as connection:
        connection.execute(
            """CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"""
        )
        connection.executemany(
            "INSERT INTO schema_migrations VALUES (?, ?, ?, 'before')",
            rows,
        )
    before = _schema_and_data_fingerprint(database_path)

    with pytest.raises(MigrationError, match=message):
        init_database(database_path)

    assert _schema_and_data_fingerprint(database_path) == before
    assert not (tmp_path / "migration-backups").exists()


def test_non_authoritative_ledger_table_fails_closed(tmp_path):
    database_path = tmp_path / "wiki.sqlite3"
    _create_current_unversioned(database_path)
    with _connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER, name TEXT, checksum TEXT, applied_at TEXT)"
        )
    before = _schema_and_data_fingerprint(database_path)

    with pytest.raises(MigrationError, match="not authoritative"):
        init_database(database_path)

    assert _schema_and_data_fingerprint(database_path) == before
    assert not (tmp_path / "migration-backups").exists()


@pytest.mark.parametrize(
    ("registry", "message"),
    [
        ((MIGRATIONS[0], MIGRATIONS[0]), "duplicate versions"),
        ((MIGRATIONS[0], replace(MIGRATIONS[0], version=2)), "duplicate names"),
        ((replace(MIGRATIONS[0], version=2, name="0002_gap"),), "gap-free"),
        ((replace(MIGRATIONS[0], checksum="not-a-checksum"),), "checksum"),
    ],
)
def test_invalid_registry_is_rejected_before_database_write(tmp_path, registry, message):
    database_path = tmp_path / "wiki.sqlite3"

    with pytest.raises(MigrationError, match=message):
        init_database(database_path, registry=registry)

    assert not database_path.exists()


def test_snapshot_failure_blocks_all_schema_and_ledger_writes(tmp_path):
    database_path = tmp_path / "wiki.sqlite3"
    _create_current_unversioned(database_path)
    before = _schema_and_data_fingerprint(database_path)

    def fail_snapshot(**_kwargs):
        raise SQLiteSnapshotError("injected snapshot failure")

    with pytest.raises(SQLiteSnapshotError, match="injected"):
        init_database(database_path, snapshotter=fail_snapshot)

    assert _schema_and_data_fingerprint(database_path) == before
    with _connect(database_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone() is None


def test_migration_capacity_gates_run_in_order_around_snapshot_before_begin(
    tmp_path,
    monkeypatch,
):
    from player_wiki import migrations

    database_path = tmp_path / "ordered.sqlite3"
    _create_current_unversioned(database_path)
    events: list[str] = []
    original_snapshotter = snapshot_sqlite_database

    def gate(path, *, required_free_bytes):
        backup_root = tmp_path / "migration-backups"
        if not events:
            assert path == tmp_path
            assert not backup_root.exists()
            events.append("pre")
        else:
            assert path == backup_root / "ordered"
            assert len(list(path.glob("*.sqlite3"))) == 1
            events.append("post")
        assert required_free_bytes > 64 * 1024 * 1024

    def injected_snapshotter(**kwargs):
        events.append("snapshot")
        return original_snapshotter(**kwargs)

    monkeypatch.setattr(migrations, "ensure_migration_free_space", gate)
    result = init_database(database_path, snapshotter=injected_snapshotter)

    assert events == ["pre", "snapshot", "post"]
    assert result.applied_versions == (1, 2)


def test_pre_snapshot_capacity_failure_has_zero_database_or_backup_effects(
    tmp_path,
    monkeypatch,
):
    from player_wiki import migrations

    database_path = tmp_path / "pre-fail.sqlite3"
    _create_current_unversioned(database_path)
    before = _schema_and_data_fingerprint(database_path)
    snapshot_called = False

    def fail_gate(*_args, **_kwargs):
        raise SQLiteSnapshotError("SQLite migration does not have enough free space.")

    def forbidden_snapshot(**_kwargs):
        nonlocal snapshot_called
        snapshot_called = True
        raise AssertionError("snapshotter must not run")

    monkeypatch.setattr(migrations, "ensure_migration_free_space", fail_gate)
    with pytest.raises(SQLiteSnapshotError, match="enough free space") as exc_info:
        init_database(database_path, snapshotter=forbidden_snapshot)

    assert snapshot_called is False
    assert _schema_and_data_fingerprint(database_path) == before
    assert not (tmp_path / "migration-backups").exists()
    assert str(database_path) not in str(exc_info.value)


def test_post_snapshot_capacity_drop_retains_verified_backup_and_blocks_begin(
    tmp_path,
    monkeypatch,
):
    from player_wiki import migrations

    database_path = tmp_path / "post-fail.sqlite3"
    _create_current_unversioned(database_path)
    before = _schema_and_data_fingerprint(database_path)
    calls = 0

    def drop_after_snapshot(_path, *, required_free_bytes):
        nonlocal calls
        calls += 1
        assert required_free_bytes > 64 * 1024 * 1024
        if calls == 2:
            raise SQLiteSnapshotError(
                "SQLite migration does not have enough free space to proceed safely."
            )

    monkeypatch.setattr(migrations, "ensure_migration_free_space", drop_after_snapshot)
    with pytest.raises(SQLiteSnapshotError, match="enough free space"):
        init_database(database_path)

    assert calls == 2
    assert _schema_and_data_fingerprint(database_path) == before
    backups = list((tmp_path / "migration-backups" / "post-fail").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as snapshot:
        assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with _connect(database_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone() is None


def test_injected_snapshotter_cannot_bypass_publication_or_capacity_gates(
    tmp_path,
    monkeypatch,
):
    from player_wiki import migrations

    database_path = tmp_path / "injected.sqlite3"
    _create_current_unversioned(database_path)
    before = _schema_and_data_fingerprint(database_path)
    capacity_calls = 0

    def record_capacity(*_args, **_kwargs):
        nonlocal capacity_calls
        capacity_calls += 1

    def fake_snapshotter(*, destination_path, **_kwargs):
        return SimpleNamespace(
            final_path=destination_path,
            byte_count=1,
            integrity_check=("ok",),
            foreign_key_violations=(),
        )

    monkeypatch.setattr(migrations, "ensure_migration_free_space", record_capacity)
    with pytest.raises(MigrationError, match="publication could not be verified"):
        init_database(database_path, snapshotter=fake_snapshotter)

    assert capacity_calls == 1
    assert _schema_and_data_fingerprint(database_path) == before


def test_missing_empty_and_no_application_schema_paths_skip_migration_storage_probe(
    tmp_path,
    monkeypatch,
):
    from player_wiki import migrations

    def forbidden(*_args, **_kwargs):
        raise AssertionError("storage probe must not run")

    monkeypatch.setattr(migrations, "collect_migration_storage_evidence", forbidden)
    missing = tmp_path / "missing.sqlite3"
    empty = tmp_path / "empty.sqlite3"
    ledger_only = tmp_path / "ledger-only.sqlite3"
    with sqlite3.connect(empty):
        pass
    with sqlite3.connect(ledger_only) as connection:
        connection.execute(
            """CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL)"""
        )

    for database_path in (missing, empty, ledger_only):
        result = init_database(database_path)
        assert result.applied_versions == (1, 2)
        assert result.backup_evidence is None


def test_no_pending_migration_skips_storage_probe_and_capacity_gate(tmp_path, monkeypatch):
    from player_wiki import migrations

    database_path = tmp_path / "current.sqlite3"
    init_database(database_path)
    monkeypatch.setattr(
        migrations,
        "collect_migration_storage_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("probe")),
    )
    monkeypatch.setattr(
        migrations,
        "ensure_migration_free_space",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("gate")),
    )

    result = init_database(database_path)

    assert result.no_op is True
    assert result.backup_evidence is None


def test_active_transaction_is_rejected_before_storage_probe(tmp_path, monkeypatch):
    from player_wiki import migrations

    database_path = tmp_path / "active-transaction.sqlite3"
    _create_current_unversioned(database_path)
    monkeypatch.setattr(
        migrations,
        "collect_migration_storage_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("probe")),
    )

    with _connect(database_path) as connection:
        connection.execute("BEGIN")
        with pytest.raises(MigrationError, match="no active transaction"):
            run_migrations(
                connection,
                database_path=database_path,
                schema_sql=SCHEMA,
            )
        connection.rollback()

    assert not (tmp_path / "migration-backups").exists()


@pytest.mark.parametrize("failure_kind", ["sqlite_full", "enospc"])
def test_runtime_storage_exhaustion_rolls_back_and_retains_snapshot(
    tmp_path,
    failure_kind,
):
    database_path = tmp_path / f"runtime-{failure_kind}.sqlite3"
    _create_current_unversioned(database_path)
    before = _schema_and_data_fingerprint(database_path)

    def exhaust(*_args):
        if failure_kind == "sqlite_full":
            failure = sqlite3.OperationalError("private database or disk is full detail")
            failure.sqlite_errorcode = sqlite3.SQLITE_FULL
            raise failure
        raise OSError(errno.ENOSPC, "private filesystem detail")

    hooks = MigrationHooks(before_migration=exhaust)
    with pytest.raises(MigrationError, match="storage became unavailable") as exc_info:
        init_database(database_path, hooks=hooks)

    assert "private" not in str(exc_info.value)
    assert str(database_path) not in str(exc_info.value)
    assert _schema_and_data_fingerprint(database_path) == before
    backups = list(
        (tmp_path / "migration-backups" / f"runtime-{failure_kind}").glob("*.sqlite3")
    )
    assert len(backups) == 1


def test_precreated_symlinked_backup_root_is_rejected_without_following(tmp_path):
    database_path = tmp_path / "symlink-root.sqlite3"
    _create_current_unversioned(database_path)
    before = _schema_and_data_fingerprint(database_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    backup_root = tmp_path / "migration-backups"
    try:
        backup_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink capability unavailable: {exc.__class__.__name__}")

    with pytest.raises(MigrationError, match="safe same-device") as exc_info:
        init_database(database_path)

    assert str(database_path) not in str(exc_info.value)
    assert _schema_and_data_fingerprint(database_path) == before
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("unsafe_kind", ["cross_device", "reparse"])
def test_precreated_backup_directory_must_be_same_device_nonreparse(
    tmp_path,
    monkeypatch,
    unsafe_kind,
):
    from player_wiki import migrations

    database_path = tmp_path / f"unsafe-{unsafe_kind}.sqlite3"
    _create_current_unversioned(database_path)
    backup_dir = tmp_path / "migration-backups" / f"unsafe-{unsafe_kind}"
    backup_dir.mkdir(parents=True)
    backup_inode = backup_dir.lstat().st_ino
    original_lstat = Path.lstat
    original_reparse = migrations._is_reparse_stat

    if unsafe_kind == "cross_device":

        def unsafe_lstat(path):
            value = original_lstat(path)
            if Path(path) == backup_dir:
                return _StatOverride(value, st_dev=value.st_dev + 1)
            return value

        monkeypatch.setattr(Path, "lstat", unsafe_lstat)
    else:
        monkeypatch.setattr(
            migrations,
            "_is_reparse_stat",
            lambda value: value.st_ino == backup_inode or original_reparse(value),
        )

    with pytest.raises(MigrationError, match="safe same-device"):
        init_database(database_path)

    assert list(backup_dir.iterdir()) == []


@pytest.mark.parametrize("fault_point", ["before_ddl", "mid_transform", "before_ledger", "after_ledger"])
def test_faults_roll_back_schema_data_and_ledger_while_snapshot_remains_valid(tmp_path, fault_point):
    database_path = tmp_path / f"{fault_point}.sqlite3"
    _create_current_unversioned(database_path)
    _downgrade_user_preferences(database_path)
    before = _schema_and_data_fingerprint(database_path)

    def raise_fault(*_args):
        raise RuntimeError(f"injected {fault_point}")

    def after_statement(_count: int, sql: str):
        if "ADD COLUMN session_chat_order" in sql:
            raise_fault()

    hooks = {
        "before_ddl": MigrationHooks(before_statement=lambda count, _sql: raise_fault() if count == 1 else None),
        "mid_transform": MigrationHooks(after_statement=after_statement),
        "before_ledger": MigrationHooks(before_ledger_insert=raise_fault),
        "after_ledger": MigrationHooks(after_ledger_insert=raise_fault),
    }[fault_point]

    with pytest.raises(RuntimeError, match="injected"):
        init_database(database_path, hooks=hooks)

    assert _schema_and_data_fingerprint(database_path) == before
    backups = list((tmp_path / "migration-backups" / fault_point).glob("*.sqlite3"))
    assert len(backups) == 1
    with _connect(backups[0]) as snapshot:
        assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert snapshot.execute("PRAGMA foreign_key_check").fetchall() == []


def test_legacy_preferences_are_migrated_only_by_explicit_init(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    _create_current_unversioned(database_path)
    _downgrade_user_preferences(database_path)

    with _connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(user_preferences)")}
        assert columns == {"user_id", "theme_key", "updated_at"}

    result = init_database(database_path)

    assert result.applied_versions == (1, 2)
    with _connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(user_preferences)")}
        assert {"session_chat_order", "frontend_mode"} <= columns


def test_v1_converges_all_known_legacy_transitions_in_one_partial_database(tmp_path):
    database_path = tmp_path / "legacy-partial.sqlite3"
    with _connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL, password_hash TEXT, auth_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO users VALUES (1, 'legacy@example.test', 'Legacy', 0, 'active', NULL, 1, 'before', 'before');

            CREATE TABLE user_preferences (
                user_id INTEGER PRIMARY KEY, theme_key TEXT NOT NULL DEFAULT 'parchment',
                updated_at TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users(id)
            );
            INSERT INTO user_preferences VALUES (1, 'moonlit', 'before');

            CREATE TABLE campaign_visibility_settings (
                campaign_slug TEXT NOT NULL,
                scope TEXT NOT NULL CHECK (scope IN ('campaign', 'wiki', 'session', 'characters')),
                visibility TEXT NOT NULL CHECK (visibility IN ('public', 'players', 'dm', 'private')),
                updated_at TEXT NOT NULL, updated_by_user_id INTEGER,
                PRIMARY KEY (campaign_slug, scope)
            );
            INSERT INTO campaign_visibility_settings VALUES ('legacy-campaign', 'wiki', 'players', 'before', 1);

            CREATE TABLE campaign_system_policies (
                campaign_slug TEXT PRIMARY KEY, library_slug TEXT NOT NULL, status TEXT NOT NULL,
                proprietary_acknowledged_at TEXT, proprietary_acknowledged_by_user_id INTEGER,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by_user_id INTEGER
            );
            INSERT INTO campaign_system_policies VALUES
                ('legacy-campaign', 'dnd-5e', 'active', NULL, NULL, 'before', 'before', 1);

            CREATE TABLE campaign_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_slug TEXT NOT NULL,
                status TEXT NOT NULL, started_at TEXT NOT NULL, started_by_user_id INTEGER,
                ended_at TEXT, ended_by_user_id INTEGER
            );
            INSERT INTO campaign_sessions VALUES (1, 'legacy-campaign', 'active', 'before', 1, NULL, NULL);

            CREATE TABLE campaign_session_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_slug TEXT NOT NULL,
                title TEXT NOT NULL, body_markdown TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, created_by_user_id INTEGER, revealed_at TEXT,
                revealed_by_user_id INTEGER, revealed_in_session_id INTEGER
            );
            INSERT INTO campaign_session_articles VALUES
                (1, 'legacy-campaign', 'Legacy Reveal', 'body', 'staged', 'before', 1, NULL, NULL, NULL);

            CREATE TABLE campaign_session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
                campaign_slug TEXT NOT NULL, message_type TEXT NOT NULL, body_text TEXT NOT NULL,
                author_user_id INTEGER, author_display_name TEXT NOT NULL, article_id INTEGER,
                created_at TEXT NOT NULL
            );
            INSERT INTO campaign_session_messages VALUES
                (1, 1, 'legacy-campaign', 'chat', 'hello', 1, 'Legacy', NULL, 'before');

            CREATE TABLE campaign_combatants (
                id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_slug TEXT NOT NULL,
                combatant_type TEXT NOT NULL, character_slug TEXT, display_name TEXT NOT NULL,
                turn_value INTEGER NOT NULL DEFAULT 0, initiative_bonus INTEGER NOT NULL DEFAULT 0,
                current_hp INTEGER NOT NULL DEFAULT 0, max_hp INTEGER NOT NULL DEFAULT 0,
                temp_hp INTEGER NOT NULL DEFAULT 0, movement_total INTEGER NOT NULL DEFAULT 0,
                movement_remaining INTEGER NOT NULL DEFAULT 0, has_action INTEGER NOT NULL DEFAULT 1,
                has_bonus_action INTEGER NOT NULL DEFAULT 1, has_reaction INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                created_by_user_id INTEGER, updated_by_user_id INTEGER
            );
            INSERT INTO campaign_combatants VALUES
                (1, 'legacy-campaign', 'player_character', 'legacy-hero', 'Legacy Hero',
                 17, 4, 20, 20, 0, 30, 30, 1, 1, 1, 'before', 'before', 1, 1);

            CREATE TABLE campaign_combat_trackers (
                campaign_slug TEXT PRIMARY KEY, round_number INTEGER NOT NULL DEFAULT 1,
                current_combatant_id INTEGER, updated_at TEXT NOT NULL, updated_by_user_id INTEGER
            );
            INSERT INTO campaign_combat_trackers VALUES ('legacy-campaign', 2, 1, 'before', 1);

            CREATE TABLE campaign_dm_statblocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_slug TEXT NOT NULL,
                title TEXT NOT NULL, body_markdown TEXT NOT NULL, source_filename TEXT NOT NULL,
                armor_class INTEGER, max_hp INTEGER NOT NULL DEFAULT 0, speed_text TEXT NOT NULL DEFAULT '',
                movement_total INTEGER NOT NULL DEFAULT 0, initiative_bonus INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                created_by_user_id INTEGER, updated_by_user_id INTEGER
            );
            INSERT INTO campaign_dm_statblocks VALUES
                (1, 'linden-pass', 'Mute Scribe', 'body', 'mute.md', 12, 9, '30 ft.', 30, 2,
                 'before', 'before', 1, 1);
            """
        )

    result = init_database(database_path)

    assert result.applied_names == (
        "0001_legacy_current_baseline",
        "0002_player_wiki_reconciliation_operations",
    )
    assert result.backup_evidence is not None
    with _connect(database_path) as connection:
        preference = connection.execute(
            "SELECT theme_key, session_chat_order, frontend_mode FROM user_preferences"
        ).fetchone()
        assert tuple(preference) == ("moonlit", "newest_first", "flask")
        policy = connection.execute(
            "SELECT allow_dm_shared_core_entry_edits FROM campaign_system_policies"
        ).fetchone()
        assert policy[0] == 0
        visibility = connection.execute(
            "SELECT scope, visibility FROM campaign_visibility_settings"
        ).fetchone()
        assert tuple(visibility) == ("wiki", "players")
        connection.execute(
            """INSERT INTO campaign_visibility_settings
            (campaign_slug, scope, visibility, updated_at, updated_by_user_id)
            VALUES ('legacy-campaign', 'dm_content', 'dm', 'after', 1)"""
        )
        message = connection.execute(
            "SELECT body_text, recipient_scope, recipient_user_id FROM campaign_session_messages"
        ).fetchone()
        assert tuple(message) == ("hello", "global", None)
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_campaign_session_messages_session_recipient'"
        ).fetchone() is not None
        article = connection.execute(
            "SELECT title, source_page_ref FROM campaign_session_articles"
        ).fetchone()
        assert tuple(article) == ("Legacy Reveal", "")
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_session_states'"
        ).fetchone() is not None
        tracker = connection.execute(
            "SELECT round_number, revision FROM campaign_combat_trackers"
        ).fetchone()
        assert tuple(tracker) == (2, 1)
        combatant = connection.execute(
            """SELECT display_name, revision, source_kind, source_ref, player_detail_visible,
            dexterity_modifier, initiative_priority FROM campaign_combatants"""
        ).fetchone()
        assert tuple(combatant) == ("Legacy Hero", 1, "character", "legacy-hero", 1, 4, 1)
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_campaign_combatants_campaign_order_v2'"
        ).fetchone() is not None
        for table in ("campaign_combatant_resource_counters", "campaign_combatant_resource_notes"):
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone() is not None
        statblock = connection.execute(
            "SELECT title, subsection FROM campaign_dm_statblocks"
        ).fetchone()
        assert tuple(statblock) == ("Mute Scribe", "Malverine Minions")

    second = init_database(database_path)
    assert second.no_op is True
    assert second.backup_evidence is None
    assert len(list((tmp_path / "migration-backups" / "legacy-partial").glob("*.sqlite3"))) == 1


def test_preference_store_source_contains_no_request_time_schema_ddl():
    source = (Path(__file__).parents[1] / "player_wiki" / "auth_store.py").read_text(encoding="utf-8")
    assert "_ensure_user_preferences_schema" not in source
    assert "ALTER TABLE user_preferences" not in source


@pytest.mark.parametrize("repetition", range(3))
def test_concurrent_legacy_wal_initializers_serialize_snapshot_and_migration(tmp_path, repetition):
    database_path = tmp_path / f"concurrent-{repetition}.sqlite3"
    _create_current_unversioned(database_path)
    with _connect(database_path) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        connection.execute(
            """INSERT INTO users
            (email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at)
            VALUES ('concurrent@example.test', 'Concurrent', 0, 'active', NULL, 1, 'before', 'before')"""
        )

    script = (
        "import json,sys; from pathlib import Path; "
        "from player_wiki.db import init_database; "
        "r=init_database(Path(sys.argv[1])); "
        "print(json.dumps({'from':r.from_version,'to':r.to_version,"
        "'applied':r.applied_versions,'no_op':r.no_op,'backup':str(r.backup_path or '')}))"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(database_path)],
            cwd=Path(__file__).parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(10)
    ]
    results: list[dict[str, object]] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=45)
        assert process.returncode == 0, stderr
        results.append(json.loads(stdout.strip()))

    assert sum(not bool(result["no_op"]) for result in results) == 1
    assert sum(bool(result["no_op"]) for result in results) == 9
    assert [result["applied"] for result in results].count([1, 2]) == 1
    assert [result["applied"] for result in results].count([]) == 9
    backup_dir = tmp_path / "migration-backups" / f"concurrent-{repetition}"
    backups = list(backup_dir.glob("*.sqlite3"))
    assert len(backups) == 1
    assert list(backup_dir.glob("*.snapshot.tmp*")) == []
    assert list(backup_dir.glob(".*.snapshot.tmp*")) == []
    lock_path = Path(f"{database_path}.migration.lock")
    assert len(lock_path.read_bytes()) == 1
    assert _ledger_rows(database_path) == [
        (1, "0001_legacy_current_baseline", MIGRATIONS[0].checksum),
        (2, "0002_player_wiki_reconciliation_operations", MIGRATIONS[1].checksum),
    ]
    with _connect(database_path) as connection:
        assert connection.execute("SELECT email FROM users").fetchall()[0][0] == "concurrent@example.test"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with _connect(backups[0]) as snapshot:
        assert snapshot.execute("SELECT email FROM users").fetchall()[0][0] == "concurrent@example.test"
        assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert snapshot.execute("PRAGMA foreign_key_check").fetchall() == []


def test_checksum_is_deterministic_across_processes():
    local_checksum = calculate_migration_checksum(MIGRATIONS[0].payload)
    script = (
        "from player_wiki.db import SCHEMA; "
        "from player_wiki.migrations import MIGRATIONS,calculate_migration_checksum; "
        "print(calculate_migration_checksum(MIGRATIONS[0].payload))"
    )
    observed = [
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).parents[1],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for _ in range(3)
    ]
    assert local_checksum == MIGRATIONS[0].checksum
    assert observed == [local_checksum] * 3


def test_stale_checksum_rejects_schema_drift_before_database_creation(tmp_path, monkeypatch):
    from player_wiki import db

    database_path = tmp_path / "schema-drift.sqlite3"
    monkeypatch.setattr(db, "SCHEMA", f"{SCHEMA}\nSELECT 1;")

    with pytest.raises(MigrationError, match="latest executable migration payload"):
        db.init_database(database_path)

    assert not database_path.exists()
    assert not Path(f"{database_path}.migration.lock").exists()


def test_stale_checksum_rejects_transform_drift_before_database_creation(tmp_path):
    database_path = tmp_path / "transform-drift.sqlite3"
    changed_payload = MigrationPayload(
        schema_sql=MIGRATIONS[0].payload.schema_sql,
        transforms=MIGRATIONS[0].payload.transforms
        + (TransformSpec(table=None, statements=("SELECT 1",)),)
    )
    changed_registry = (replace(MIGRATIONS[0], payload=changed_payload),)

    with pytest.raises(MigrationError, match="executable payload"):
        init_database(database_path, registry=changed_registry)

    assert not database_path.exists()
    assert not Path(f"{database_path}.migration.lock").exists()


def test_migration_registry_has_no_swappable_apply_callable():
    assert not hasattr(MIGRATIONS[0], "apply")
    with pytest.raises(TypeError):
        replace(MIGRATIONS[0], apply=lambda _context: None)


def test_lock_owner_normalizes_legacy_oversized_sidecar_without_replacing_inode(tmp_path):
    database_path = tmp_path / "legacy-lock.sqlite3"
    lock_path = Path(f"{database_path}.migration.lock")
    lock_path.write_bytes(b"old")
    inode_before = lock_path.stat().st_ino

    result = init_database(database_path)

    assert result.applied_versions == (1, 2)
    assert len(lock_path.read_bytes()) == 1
    assert lock_path.stat().st_ino == inode_before


def test_v1_payload_and_checksum_remain_immutable_while_v2_owns_current_schema():
    assert MIGRATIONS[0].name == "0001_legacy_current_baseline"
    assert MIGRATIONS[0].checksum == "bf860bf11bb6c9bc8410c57cba91951825248d69a4bd52bd545bff1b2f717a16"
    assert MIGRATIONS[0].payload.schema_sql == BASELINE_SCHEMA_SQL
    assert "player_wiki_reconciliation_operations" not in BASELINE_SCHEMA_SQL
    assert MIGRATIONS[1].name == "0002_player_wiki_reconciliation_operations"
    assert MIGRATIONS[1].payload.schema_sql == CURRENT_SCHEMA_SQL == SCHEMA
    assert "player_wiki_reconciliation_operations" in CURRENT_SCHEMA_SQL
    assert calculate_migration_checksum(MIGRATIONS[1].payload) == MIGRATIONS[1].checksum


def test_v1_database_advances_to_v2_and_then_is_a_true_no_op(tmp_path):
    database_path = tmp_path / "v1-to-v2.sqlite3"
    with _connect(database_path) as connection:
        first = run_migrations(
            connection,
            database_path=database_path,
            schema_sql=BASELINE_SCHEMA_SQL,
            registry=MIGRATIONS[:1],
        )
    assert first.applied_versions == (1,)

    def controlled_snapshotter(*, source_path: Path, destination_path: Path):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        controlled_destination = (
            f"\\\\?\\{destination_path.resolve()}"
            if os.name == "nt"
            else str(destination_path)
        )
        with sqlite3.connect(source_path) as source, sqlite3.connect(controlled_destination) as target:
            source.backup(target)
        data = destination_path.read_bytes()
        return SQLiteSnapshotEvidence(
            final_path=destination_path.resolve(),
            byte_count=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            integrity_check=("ok",),
            foreign_key_violations=(),
            elapsed_seconds=0.0,
            total_pages=1,
            remaining_pages=0,
            progress_calls=1,
            busy_retries=0,
        )

    result = init_database(database_path, snapshotter=controlled_snapshotter)
    assert result.from_version == 1
    assert result.to_version == 2
    assert result.applied_versions == (2,)
    assert result.backup_evidence is not None
    with _connect(database_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_wiki_reconciliation_operations'"
        ).fetchone() is not None
    assert init_database(database_path).no_op is True


def _create_current_memory_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in _schema_statements_for(CURRENT_SCHEMA_SQL):
        connection.execute(statement)
    return connection


def _insert_reconciliation_row(
    connection: sqlite3.Connection,
    *,
    operation_id: str = "a" * 32,
    desired_markdown: bytes | None = b"---\ntitle: Safe\n---\n\nBody\n",
    audit_event_type: str | None = None,
    audit_actor_user_id: int | None = None,
    audit_metadata_json: str | None = None,
    state: str = "prepared",
) -> None:
    connection.execute(
        """
        INSERT INTO player_wiki_reconciliation_operations (
            operation_id, campaign_slug, page_ref, operation_kind,
            primary_authority, desired_primary_ref,
            previous_primary_digest, desired_primary_digest,
            previous_markdown_digest, desired_markdown_digest,
            desired_markdown, audit_event_type, audit_actor_user_id,
            audit_metadata_json, state, error_code, created_at, updated_at
        )
        VALUES (?, 'safe-campaign', 'notes/safe', 'update', 'markdown',
            'notes/safe.md', '', ?, '', ?, ?, ?, ?, ?, ?, '', 'before', 'before')
        """,
        (
            operation_id,
            "b" * 64,
            "b" * 64,
            sqlite3.Binary(desired_markdown) if desired_markdown is not None else None,
            audit_event_type,
            audit_actor_user_id,
            audit_metadata_json,
            state,
        ),
    )


def test_v2_reconciliation_payload_bounds_and_digest_constraints():
    with _create_current_memory_database() as connection:
        _insert_reconciliation_row(
            connection,
            desired_markdown=b"x" * 100663296,
        )
        connection.execute(
            "DELETE FROM player_wiki_reconciliation_operations WHERE operation_id = ?",
            ("a" * 32,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_reconciliation_row(connection, desired_markdown=b"")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO player_wiki_reconciliation_operations (
                    operation_id, campaign_slug, page_ref, operation_kind,
                    primary_authority, desired_primary_ref,
                    previous_primary_digest, desired_primary_digest,
                    previous_markdown_digest, desired_markdown_digest,
                    desired_markdown, state, created_at, updated_at
                ) VALUES (?, 'safe-campaign', 'notes/too-large', 'update', 'markdown',
                    'notes/too-large.md', '', ?, '', ?, zeroblob(100663297),
                    'prepared', 'before', 'before')
                """,
                ("c" * 32, "b" * 64, "b" * 64),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO player_wiki_reconciliation_operations (
                    operation_id, campaign_slug, page_ref, operation_kind,
                    primary_authority, desired_primary_ref,
                    previous_primary_digest, desired_primary_digest,
                    previous_markdown_digest, desired_markdown_digest,
                    desired_markdown, state, created_at, updated_at
                ) VALUES (?, 'safe-campaign', 'notes/bad-digest', 'update', 'markdown',
                    'notes/bad-digest.md', '', ?, '', ?, ?, 'prepared', 'before', 'before')
                """,
                ("d" * 32, "G" * 64, "b" * 64, sqlite3.Binary(b"safe")),
            )


def test_v2_audit_bounds_and_deleted_actor_remain_structurally_valid():
    with _create_current_memory_database() as connection:
        connection.execute(
            """INSERT INTO users
            (email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at)
            VALUES ('actor@example.test', 'Actor', 0, 'active', NULL, 1, 'before', 'before')"""
        )
        _insert_reconciliation_row(
            connection,
            audit_event_type="e" * 128,
            audit_actor_user_id=1,
            audit_metadata_json="m" * 65536,
        )
        connection.execute("DELETE FROM users WHERE id = 1")
        row = connection.execute(
            "SELECT audit_event_type, audit_actor_user_id, audit_metadata_json FROM player_wiki_reconciliation_operations"
        ).fetchone()
        assert row["audit_event_type"] == "e" * 128
        assert row["audit_actor_user_id"] is None
        assert row["audit_metadata_json"] == "m" * 65536
        connection.execute("DELETE FROM player_wiki_reconciliation_operations")

        with pytest.raises(sqlite3.IntegrityError):
            _insert_reconciliation_row(
                connection,
                audit_event_type="e" * 129,
                audit_metadata_json="{}",
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_reconciliation_row(
                connection,
                audit_event_type="event",
                audit_metadata_json="m" * 65537,
            )
