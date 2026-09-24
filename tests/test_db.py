from __future__ import annotations

import sqlite3

from flask import Flask
import pytest

from player_wiki.db import (
    _InstrumentedConnection,
    get_db,
    get_db_query_metrics,
    reset_db_query_metrics,
)


def test_db_connections_enable_wal_and_busy_timeout(app):
    with app.app_context():
        connection = get_db()

        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


@pytest.fixture(params=[False, True], ids=["sqlite", "instrumented"])
def context_connection(request, tmp_path):
    """Exercise the same transaction contract through native and wrapped SQLite."""
    raw = sqlite3.connect(tmp_path / "context.sqlite")
    raw.execute("PRAGMA foreign_keys = ON")
    raw.executescript(
        """
        CREATE TABLE parents (id INTEGER PRIMARY KEY);
        CREATE TABLE children (
            parent_id INTEGER REFERENCES parents(id)
                DEFERRABLE INITIALLY DEFERRED
        );
        """
    )
    connection = _InstrumentedConnection(raw) if request.param else raw
    with Flask(__name__).app_context():
        reset_db_query_metrics()
        try:
            yield connection
        finally:
            raw.set_authorizer(None)
            raw.close()


def _assert_transaction_metrics(connection, *, commits, rollbacks):
    if not isinstance(connection, _InstrumentedConnection):
        return
    metrics = get_db_query_metrics()
    assert metrics["commit_count"] == commits
    assert metrics["rollback_count"] == rollbacks
    assert metrics["commit_time_ms"] >= 0
    assert metrics["rollback_time_ms"] >= 0


def _deny_rollback(action, argument, _second, _database, _trigger):
    if action == sqlite3.SQLITE_TRANSACTION and argument == "ROLLBACK":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def test_context_commits_and_returns_the_same_open_connection(context_connection):
    connection = context_connection
    with connection as entered:
        assert entered is connection
        connection.execute("INSERT INTO parents VALUES (1)")
        connection.execute("INSERT INTO children VALUES (1)")
        assert connection.in_transaction

    assert not connection.in_transaction
    assert connection.execute("SELECT parent_id FROM children").fetchall() == [(1,)]
    _assert_transaction_metrics(connection, commits=1, rollbacks=0)
    if isinstance(connection, _InstrumentedConnection):
        metrics = get_db_query_metrics()
        assert metrics["query_count"] == 3
        assert metrics["write_count"] == 2


@pytest.mark.parametrize("error_type", [ValueError, BaseException])
def test_context_rolls_back_body_failure_and_preserves_error(context_connection, error_type):
    connection = context_connection
    body_error = error_type("body failure")
    with pytest.raises(error_type) as caught:
        with connection:
            connection.execute("INSERT INTO parents VALUES (1)")
            raise body_error

    assert caught.value is body_error
    assert not connection.in_transaction
    assert connection.execute("SELECT id FROM parents").fetchall() == []
    _assert_transaction_metrics(connection, commits=0, rollbacks=1)


def test_failed_commit_rolls_back_before_same_connection_is_reused(context_connection):
    connection = context_connection
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with connection:
            connection.execute("INSERT INTO parents VALUES (1)")
            connection.execute("INSERT INTO children VALUES (999)")
            assert connection.in_transaction

    assert not connection.in_transaction
    assert connection.execute("SELECT id FROM parents").fetchall() == []
    assert connection.execute("SELECT parent_id FROM children").fetchall() == []
    _assert_transaction_metrics(connection, commits=1, rollbacks=1)

    # Recovery work must not accidentally commit any writes from the failed unit.
    with connection:
        connection.execute("INSERT INTO parents VALUES (2)")
        connection.execute("INSERT INTO children VALUES (2)")
    assert not connection.in_transaction
    assert connection.execute("SELECT id FROM parents").fetchall() == [(2,)]
    assert connection.execute("SELECT parent_id FROM children").fetchall() == [(2,)]
    _assert_transaction_metrics(connection, commits=2, rollbacks=1)


def test_failed_rollback_retains_the_commit_error_and_requires_recovery(context_connection):
    connection = context_connection
    connection.set_authorizer(_deny_rollback)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized") as caught:
        with connection:
            connection.execute("INSERT INTO children VALUES (999)")

    assert isinstance(caught.value.__context__, sqlite3.IntegrityError)
    assert "FOREIGN KEY" in str(caught.value.__context__)
    assert connection.in_transaction
    _assert_transaction_metrics(connection, commits=1, rollbacks=1)

    connection.set_authorizer(None)
    connection.rollback()
    assert not connection.in_transaction
    assert connection.execute("SELECT parent_id FROM children").fetchall() == []
    _assert_transaction_metrics(connection, commits=1, rollbacks=2)


def test_failed_rollback_retains_the_body_error(context_connection):
    connection = context_connection
    body_error = ValueError("body failure")
    connection.set_authorizer(_deny_rollback)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized") as caught:
        with connection:
            connection.execute("INSERT INTO parents VALUES (1)")
            raise body_error

    assert caught.value.__context__ is body_error
    assert connection.in_transaction
    _assert_transaction_metrics(connection, commits=0, rollbacks=1)
    connection.set_authorizer(None)
    connection.rollback()
    assert not connection.in_transaction
    assert connection.execute("SELECT id FROM parents").fetchall() == []


def test_select_only_context_does_not_start_a_transaction(context_connection):
    connection = context_connection
    statements = []
    connection.set_trace_callback(statements.append)
    with connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
        assert not connection.in_transaction
    assert not connection.in_transaction
    assert statements == ["SELECT 1"]
    # Count the explicit wrapper attempt even when SQLite has nothing to commit.
    _assert_transaction_metrics(connection, commits=1, rollbacks=0)


def test_context_joins_an_existing_transaction_without_a_savepoint(context_connection):
    connection = context_connection
    statements = []
    connection.set_trace_callback(statements.append)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO parents VALUES (1)")
    with pytest.raises(ValueError, match="caller transaction"):
        with connection:
            connection.execute("INSERT INTO parents VALUES (2)")
            raise ValueError("caller transaction")
    assert not connection.in_transaction
    assert connection.execute("SELECT id FROM parents").fetchall() == []
    assert not any("SAVEPOINT" in statement for statement in statements)
    _assert_transaction_metrics(connection, commits=0, rollbacks=1)


def test_explicit_transaction_methods_leave_ownership_with_the_caller(context_connection):
    connection = context_connection
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO parents VALUES (1)")
    assert connection.in_transaction
    _assert_transaction_metrics(connection, commits=0, rollbacks=0)
    connection.commit()
    connection.execute("INSERT INTO parents VALUES (2)")
    connection.rollback()
    assert not connection.in_transaction
    assert connection.execute("SELECT id FROM parents").fetchall() == [(1,)]
    _assert_transaction_metrics(connection, commits=1, rollbacks=1)


def test_failed_commit_cleanup_works_without_flask_context():
    raw = sqlite3.connect(":memory:")
    raw.execute("PRAGMA foreign_keys = ON")
    raw.executescript(
        "CREATE TABLE parents (id INTEGER PRIMARY KEY);"
        "CREATE TABLE children (parent_id INTEGER REFERENCES parents(id) "
        "DEFERRABLE INITIALLY DEFERRED);"
    )
    connection = _InstrumentedConnection(raw)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            with connection:
                connection.execute("INSERT INTO children VALUES (999)")
        assert not connection.in_transaction
        assert connection.execute("SELECT parent_id FROM children").fetchall() == []
    finally:
        connection.close()
