from __future__ import annotations

import sqlite3
from pathlib import Path
import time
from typing import Callable, Sequence

from flask import Flask, current_app, g, has_app_context

from .migrations import (
    BASELINE_SCHEMA_SQL,
    CURRENT_SCHEMA_SQL,
    MIGRATIONS,
    Migration,
    MigrationHooks,
    MigrationResult,
    run_migrations,
    validate_migration_registry,
)
from .sqlite_safety import SQLiteSnapshotEvidence, snapshot_sqlite_database

SCHEMA = CURRENT_SCHEMA_SQL


class _InstrumentedCursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)

    def execute(self, sql: str, parameters=()):
        started_at = time.perf_counter()
        try:
            self._cursor.execute(sql, parameters)
            return self
        finally:
            _record_db_query(
                (time.perf_counter() - started_at) * 1000,
                is_write=_is_write_sql(sql),
            )

    def executemany(self, sql: str, seq_of_parameters):
        started_at = time.perf_counter()
        try:
            self._cursor.executemany(sql, seq_of_parameters)
            return self
        finally:
            _record_db_query(
                (time.perf_counter() - started_at) * 1000,
                is_write=_is_write_sql(sql),
            )

    def executescript(self, sql_script: str):
        started_at = time.perf_counter()
        try:
            self._cursor.executescript(sql_script)
            return self
        finally:
            _record_db_query(
                (time.perf_counter() - started_at) * 1000,
                is_write=_is_write_sql(sql_script),
            )


class _InstrumentedConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def cursor(self, *args, **kwargs) -> _InstrumentedCursor:
        return _InstrumentedCursor(self._connection.cursor(*args, **kwargs))

    def execute(self, sql: str, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters):
        return self.cursor().executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str):
        return self.cursor().executescript(sql_script)

    def close(self) -> None:
        self._connection.close()

    def commit(self) -> None:
        started_at = time.perf_counter()
        try:
            self._connection.commit()
        finally:
            _record_db_commit((time.perf_counter() - started_at) * 1000)

    def rollback(self) -> None:
        started_at = time.perf_counter()
        try:
            self._connection.rollback()
        finally:
            _record_db_rollback((time.perf_counter() - started_at) * 1000)


def reset_db_query_metrics() -> None:
    if not has_app_context():
        return
    g.db_query_metrics = {
        "query_count": 0,
        "query_time_ms": 0.0,
        "write_count": 0,
        "write_time_ms": 0.0,
        "commit_count": 0,
        "commit_time_ms": 0.0,
        "rollback_count": 0,
        "rollback_time_ms": 0.0,
    }


def get_db_query_metrics() -> dict[str, float | int]:
    if not has_app_context():
        return {
            "query_count": 0,
            "query_time_ms": 0.0,
            "write_count": 0,
            "write_time_ms": 0.0,
            "commit_count": 0,
            "commit_time_ms": 0.0,
            "rollback_count": 0,
            "rollback_time_ms": 0.0,
        }
    metrics = getattr(g, "db_query_metrics", None)
    if not isinstance(metrics, dict):
        reset_db_query_metrics()
        metrics = getattr(g, "db_query_metrics", {})
    return {
        "query_count": int(metrics.get("query_count", 0) or 0),
        "query_time_ms": float(metrics.get("query_time_ms", 0.0) or 0.0),
        "write_count": int(metrics.get("write_count", 0) or 0),
        "write_time_ms": float(metrics.get("write_time_ms", 0.0) or 0.0),
        "commit_count": int(metrics.get("commit_count", 0) or 0),
        "commit_time_ms": float(metrics.get("commit_time_ms", 0.0) or 0.0),
        "rollback_count": int(metrics.get("rollback_count", 0) or 0),
        "rollback_time_ms": float(metrics.get("rollback_time_ms", 0.0) or 0.0),
    }


def _record_db_query(duration_ms: float, *, is_write: bool = False) -> None:
    if not has_app_context():
        return
    metrics = get_db_query_metrics()
    metrics["query_count"] = int(metrics["query_count"]) + 1
    metrics["query_time_ms"] = float(metrics["query_time_ms"]) + max(0.0, duration_ms)
    if is_write:
        metrics["write_count"] = int(metrics["write_count"]) + 1
        metrics["write_time_ms"] = float(metrics["write_time_ms"]) + max(0.0, duration_ms)
    g.db_query_metrics = metrics


def _record_db_commit(duration_ms: float) -> None:
    if not has_app_context():
        return
    metrics = get_db_query_metrics()
    metrics["commit_count"] = int(metrics["commit_count"]) + 1
    metrics["commit_time_ms"] = float(metrics["commit_time_ms"]) + max(0.0, duration_ms)
    g.db_query_metrics = metrics


def _record_db_rollback(duration_ms: float) -> None:
    if not has_app_context():
        return
    metrics = get_db_query_metrics()
    metrics["rollback_count"] = int(metrics["rollback_count"]) + 1
    metrics["rollback_time_ms"] = float(metrics["rollback_time_ms"]) + max(0.0, duration_ms)
    g.db_query_metrics = metrics


def _is_write_sql(sql: str) -> bool:
    if not sql:
        return False
    first_token = str(sql).strip().split(None, 1)[0].lower()
    if not first_token:
        return False
    return first_token in {
        "alter",
        "attach",
        "create",
        "delete",
        "detach",
        "drop",
        "insert",
        "reindex",
        "replace",
        "truncate",
        "update",
        "vacuum",
    }


def register_db(app: Flask) -> None:
    app.teardown_appcontext(close_db)


def get_db() -> sqlite3.Connection | _InstrumentedConnection:
    if "db_connection" not in g:
        db_path = Path(current_app.config["DB_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA foreign_keys = ON")
        g.db_connection = _InstrumentedConnection(connection)

    return g.db_connection


def close_db(_: object | None = None) -> None:
    connection = g.pop("db_connection", None)
    if connection is not None:
        connection.close()


def init_database(
    path: Path | None = None,
    *,
    registry: Sequence[Migration] = MIGRATIONS,
    hooks: MigrationHooks | None = None,
    snapshotter: Callable[..., SQLiteSnapshotEvidence] = snapshot_sqlite_database,
) -> MigrationResult:
    """Initialize or migrate a database and return non-secret execution evidence."""

    validate_migration_registry(registry, schema_sql=SCHEMA)
    owns_connection = path is not None
    if path is None:
        database_path = Path(current_app.config["DB_PATH"])
        connection = get_db()
    else:
        database_path = Path(path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        raw_connection = sqlite3.connect(database_path, timeout=30.0)
        raw_connection.row_factory = sqlite3.Row
        raw_connection.execute("PRAGMA busy_timeout = 30000")
        raw_connection.execute("PRAGMA foreign_keys = ON")
        connection = raw_connection

    try:
        return run_migrations(
            connection,
            database_path=database_path,
            schema_sql=SCHEMA,
            registry=registry,
            hooks=hooks,
            snapshotter=snapshotter,
        )
    finally:
        if owns_connection:
            connection.close()

# Numbered schema evolution is owned by player_wiki.migrations.
