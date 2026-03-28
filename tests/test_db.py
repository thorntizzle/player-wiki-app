from __future__ import annotations

from player_wiki.db import get_db


def test_db_connections_enable_wal_and_busy_timeout(app):
    with app.app_context():
        connection = get_db()

        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
