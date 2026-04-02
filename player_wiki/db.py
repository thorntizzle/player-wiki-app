from __future__ import annotations

import sqlite3
from pathlib import Path
import time

from flask import Flask, current_app, g, has_app_context

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('invited', 'active', 'disabled')),
    password_hash TEXT,
    auth_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    theme_key TEXT NOT NULL DEFAULT 'parchment',
    session_chat_order TEXT NOT NULL DEFAULT 'newest_first' CHECK (session_chat_order IN ('newest_first', 'oldest_first')),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('dm', 'player', 'observer')),
    status TEXT NOT NULL CHECK (status IN ('active', 'invited', 'removed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, campaign_slug),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_visibility_settings (
    campaign_slug TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('campaign', 'wiki', 'systems', 'session', 'combat', 'characters', 'dm_content')),
    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'players', 'dm', 'private')),
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, scope),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS character_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    character_slug TEXT NOT NULL,
    assignment_type TEXT NOT NULL CHECK (assignment_type IN ('owner')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (campaign_slug, character_slug),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS invite_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    user_agent TEXT,
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    created_by_user_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS auth_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    target_user_id INTEGER,
    campaign_slug TEXT,
    character_slug TEXT,
    event_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (actor_user_id) REFERENCES users(id),
    FOREIGN KEY (target_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS character_state (
    campaign_slug TEXT NOT NULL,
    character_slug TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, character_slug),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
    started_at TEXT NOT NULL,
    started_by_user_id INTEGER,
    ended_at TEXT,
    ended_by_user_id INTEGER,
    FOREIGN KEY (started_by_user_id) REFERENCES users(id),
    FOREIGN KEY (ended_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_session_states (
    campaign_slug TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_session_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    source_page_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('staged', 'revealed')),
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    revealed_at TEXT,
    revealed_by_user_id INTEGER,
    revealed_in_session_id INTEGER,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (revealed_by_user_id) REFERENCES users(id),
    FOREIGN KEY (revealed_in_session_id) REFERENCES campaign_sessions(id)
);

CREATE TABLE IF NOT EXISTS campaign_session_article_images (
    article_id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    alt_text TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    data_blob BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES campaign_session_articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    message_type TEXT NOT NULL CHECK (message_type IN ('chat', 'article_reveal', 'system')),
    body_text TEXT NOT NULL,
    author_user_id INTEGER,
    author_display_name TEXT NOT NULL,
    article_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES campaign_sessions(id),
    FOREIGN KEY (author_user_id) REFERENCES users(id),
    FOREIGN KEY (article_id) REFERENCES campaign_session_articles(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_sessions_active
ON campaign_sessions(campaign_slug)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_campaign_session_articles_campaign_status
ON campaign_session_articles(campaign_slug, status, created_at, id);

CREATE INDEX IF NOT EXISTS idx_campaign_session_messages_session
ON campaign_session_messages(session_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_api_tokens_user
ON api_tokens(user_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS campaign_dm_statblocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    armor_class INTEGER,
    max_hp INTEGER NOT NULL DEFAULT 0,
    speed_text TEXT NOT NULL DEFAULT '',
    movement_total INTEGER NOT NULL DEFAULT 0,
    initiative_bonus INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    updated_by_user_id INTEGER,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_dm_condition_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description_markdown TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    updated_by_user_id INTEGER,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_dm_statblocks_campaign
ON campaign_dm_statblocks(campaign_slug, updated_at DESC, title, id);

CREATE INDEX IF NOT EXISTS idx_campaign_dm_condition_definitions_campaign
ON campaign_dm_condition_definitions(campaign_slug, name, id);

CREATE TABLE IF NOT EXISTS campaign_combatants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    combatant_type TEXT NOT NULL CHECK (combatant_type IN ('player_character', 'npc')),
    character_slug TEXT,
    source_kind TEXT NOT NULL DEFAULT 'manual_npc' CHECK (source_kind IN ('character', 'manual_npc', 'dm_statblock', 'systems_monster')),
    source_ref TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL,
    turn_value INTEGER NOT NULL DEFAULT 0,
    initiative_bonus INTEGER NOT NULL DEFAULT 0,
    current_hp INTEGER NOT NULL DEFAULT 0,
    max_hp INTEGER NOT NULL DEFAULT 0,
    temp_hp INTEGER NOT NULL DEFAULT 0,
    movement_total INTEGER NOT NULL DEFAULT 0,
    movement_remaining INTEGER NOT NULL DEFAULT 0,
    has_action INTEGER NOT NULL DEFAULT 1,
    has_bonus_action INTEGER NOT NULL DEFAULT 1,
    has_reaction INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    updated_by_user_id INTEGER,
    UNIQUE (campaign_slug, character_slug),
    CHECK (character_slug IS NOT NULL OR combatant_type = 'npc'),
    CHECK (character_slug IS NULL OR combatant_type = 'player_character'),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_combat_trackers (
    campaign_slug TEXT PRIMARY KEY,
    round_number INTEGER NOT NULL DEFAULT 1,
    current_combatant_id INTEGER,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    FOREIGN KEY (current_combatant_id) REFERENCES campaign_combatants(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_combat_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combatant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    duration_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    FOREIGN KEY (combatant_id) REFERENCES campaign_combatants(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_combatants_campaign_order
ON campaign_combatants(campaign_slug, turn_value DESC, display_name, id);

CREATE INDEX IF NOT EXISTS idx_campaign_combat_conditions_combatant
ON campaign_combat_conditions(combatant_id, created_at, id);

CREATE TABLE IF NOT EXISTS systems_libraries (
    library_slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    system_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS systems_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    license_class TEXT NOT NULL CHECK (license_class IN ('proprietary_private', 'srd_cc', 'open_license', 'custom_campaign')),
    license_url TEXT NOT NULL DEFAULT '',
    attribution_text TEXT NOT NULL DEFAULT '',
    public_visibility_allowed INTEGER NOT NULL DEFAULT 0,
    requires_unofficial_notice INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (library_slug, source_id)
);

CREATE INDEX IF NOT EXISTS idx_systems_sources_library
ON systems_sources(library_slug, title, source_id);

CREATE TABLE IF NOT EXISTS systems_import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('started', 'completed', 'failed')),
    import_version TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    summary_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    started_by_user_id INTEGER,
    FOREIGN KEY (started_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_systems_import_runs_library_source
ON systems_import_runs(library_slug, source_id, started_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS systems_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    source_page TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    search_text TEXT NOT NULL DEFAULT '',
    player_safe_default INTEGER NOT NULL DEFAULT 0,
    dm_heavy INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    body_json TEXT NOT NULL DEFAULT '{}',
    rendered_html TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (library_slug, entry_key),
    UNIQUE (library_slug, slug)
);

CREATE INDEX IF NOT EXISTS idx_systems_entries_source
ON systems_entries(library_slug, source_id, title, id);

CREATE INDEX IF NOT EXISTS idx_systems_entries_search
ON systems_entries(library_slug, source_id, entry_type, title, id);

CREATE TABLE IF NOT EXISTS systems_entry_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_slug TEXT NOT NULL,
    from_entry_key TEXT NOT NULL,
    to_entry_key TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    UNIQUE (library_slug, from_entry_key, to_entry_key, relation_type)
);

CREATE TABLE IF NOT EXISTS campaign_system_policies (
    campaign_slug TEXT PRIMARY KEY,
    library_slug TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
    proprietary_acknowledged_at TEXT,
    proprietary_acknowledged_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    FOREIGN KEY (proprietary_acknowledged_by_user_id) REFERENCES users(id),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_enabled_sources (
    campaign_slug TEXT NOT NULL,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 0,
    default_visibility TEXT NOT NULL CHECK (default_visibility IN ('public', 'players', 'dm', 'private')),
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, source_id),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_enabled_sources_campaign
ON campaign_enabled_sources(campaign_slug, library_slug, source_id);

CREATE TABLE IF NOT EXISTS campaign_entry_overrides (
    campaign_slug TEXT NOT NULL,
    library_slug TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    visibility_override TEXT,
    is_enabled_override INTEGER,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, entry_key),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_entry_overrides_campaign
ON campaign_entry_overrides(campaign_slug, library_slug, entry_key);

CREATE TABLE IF NOT EXISTS campaign_pages (
    campaign_slug TEXT NOT NULL,
    page_ref TEXT NOT NULL,
    route_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    subsection TEXT NOT NULL DEFAULT '',
    page_type TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 10000,
    published INTEGER NOT NULL DEFAULT 1,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    image_alt TEXT NOT NULL DEFAULT '',
    image_caption TEXT NOT NULL DEFAULT '',
    reveal_after_session INTEGER NOT NULL DEFAULT 0,
    source_ref TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    raw_link_targets_json TEXT NOT NULL DEFAULT '[]',
    searchable_text TEXT NOT NULL DEFAULT '',
    body_markdown TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (campaign_slug, page_ref),
    UNIQUE (campaign_slug, route_slug)
);

CREATE INDEX IF NOT EXISTS idx_campaign_pages_campaign_route
ON campaign_pages(campaign_slug, route_slug);

CREATE INDEX IF NOT EXISTS idx_campaign_pages_campaign_section
ON campaign_pages(campaign_slug, section, subsection, display_order, title, page_ref);

CREATE TABLE IF NOT EXISTS campaign_page_sync_state (
    campaign_slug TEXT PRIMARY KEY,
    seeded_at TEXT NOT NULL
);
"""


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
            _record_db_query((time.perf_counter() - started_at) * 1000)

    def executemany(self, sql: str, seq_of_parameters):
        started_at = time.perf_counter()
        try:
            self._cursor.executemany(sql, seq_of_parameters)
            return self
        finally:
            _record_db_query((time.perf_counter() - started_at) * 1000)

    def executescript(self, sql_script: str):
        started_at = time.perf_counter()
        try:
            self._cursor.executescript(sql_script)
            return self
        finally:
            _record_db_query((time.perf_counter() - started_at) * 1000)


class _InstrumentedConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

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


def reset_db_query_metrics() -> None:
    if not has_app_context():
        return
    g.db_query_metrics = {"query_count": 0, "query_time_ms": 0.0}


def get_db_query_metrics() -> dict[str, float | int]:
    if not has_app_context():
        return {"query_count": 0, "query_time_ms": 0.0}
    metrics = getattr(g, "db_query_metrics", None)
    if not isinstance(metrics, dict):
        reset_db_query_metrics()
        metrics = getattr(g, "db_query_metrics", {})
    return {
        "query_count": int(metrics.get("query_count", 0) or 0),
        "query_time_ms": float(metrics.get("query_time_ms", 0.0) or 0.0),
    }


def _record_db_query(duration_ms: float) -> None:
    if not has_app_context():
        return
    metrics = get_db_query_metrics()
    metrics["query_count"] = int(metrics["query_count"]) + 1
    metrics["query_time_ms"] = float(metrics["query_time_ms"]) + max(0.0, duration_ms)
    g.db_query_metrics = metrics


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


def init_database() -> None:
    connection = get_db()
    connection.executescript(SCHEMA)
    _migrate_user_preferences_for_session_chat_order(connection)
    _migrate_campaign_visibility_settings_for_additional_scopes(connection)
    _migrate_campaign_combat_trackers_for_revision(connection)
    _migrate_campaign_session_states(connection)
    _migrate_campaign_session_articles_for_source_page_ref(connection)
    _migrate_campaign_combatants_for_source_identity(connection)
    connection.commit()


def _migrate_user_preferences_for_session_chat_order(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"] or "")
        for row in connection.execute("PRAGMA table_info(user_preferences)").fetchall()
    }
    if "session_chat_order" in columns:
        return

    connection.execute(
        """
        ALTER TABLE user_preferences
        ADD COLUMN session_chat_order TEXT NOT NULL DEFAULT 'newest_first'
        """
    )


def _migrate_campaign_visibility_settings_for_additional_scopes(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'campaign_visibility_settings'
        """
    ).fetchone()
    if row is None:
        return

    create_sql = str(row["sql"] or "")
    if "'combat'" in create_sql and "'dm_content'" in create_sql and "'systems'" in create_sql:
        return

    connection.executescript(
        """
        ALTER TABLE campaign_visibility_settings RENAME TO campaign_visibility_settings_legacy;

        CREATE TABLE campaign_visibility_settings (
            campaign_slug TEXT NOT NULL,
            scope TEXT NOT NULL CHECK (scope IN ('campaign', 'wiki', 'systems', 'session', 'combat', 'characters', 'dm_content')),
            visibility TEXT NOT NULL CHECK (visibility IN ('public', 'players', 'dm', 'private')),
            updated_at TEXT NOT NULL,
            updated_by_user_id INTEGER,
            PRIMARY KEY (campaign_slug, scope),
            FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
        );

        INSERT INTO campaign_visibility_settings (
            campaign_slug,
            scope,
            visibility,
            updated_at,
            updated_by_user_id
        )
        SELECT
            campaign_slug,
            scope,
            visibility,
            updated_at,
            updated_by_user_id
        FROM campaign_visibility_settings_legacy;

        DROP TABLE campaign_visibility_settings_legacy;
        """
    )


def _migrate_campaign_session_articles_for_source_page_ref(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"] or "")
        for row in connection.execute("PRAGMA table_info(campaign_session_articles)").fetchall()
    }
    if "source_page_ref" in columns:
        return

    connection.execute(
        """
        ALTER TABLE campaign_session_articles
        ADD COLUMN source_page_ref TEXT NOT NULL DEFAULT ''
        """
    )


def _migrate_campaign_session_states(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_session_states (
            campaign_slug TEXT PRIMARY KEY,
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            updated_by_user_id INTEGER,
            FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
        )
        """
    )


def _migrate_campaign_combat_trackers_for_revision(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"] or "")
        for row in connection.execute("PRAGMA table_info(campaign_combat_trackers)").fetchall()
    }
    if not columns:
        return

    if "revision" not in columns:
        connection.execute(
            """
            ALTER TABLE campaign_combat_trackers
            ADD COLUMN revision INTEGER NOT NULL DEFAULT 1
            """
        )

    connection.execute(
        """
        UPDATE campaign_combat_trackers
        SET revision = CASE
            WHEN revision IS NULL OR revision < 1
                THEN 1
            ELSE revision
        END
        """
    )


def _migrate_campaign_combatants_for_source_identity(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"] or "")
        for row in connection.execute("PRAGMA table_info(campaign_combatants)").fetchall()
    }
    if not columns:
        return

    if "source_kind" not in columns:
        connection.execute(
            """
            ALTER TABLE campaign_combatants
            ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'manual_npc'
            """
        )
    if "source_ref" not in columns:
        connection.execute(
            """
            ALTER TABLE campaign_combatants
            ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''
            """
        )

    connection.execute(
        """
        UPDATE campaign_combatants
        SET source_kind = CASE
            WHEN character_slug IS NOT NULL
                 AND TRIM(COALESCE(source_kind, '')) IN ('', 'manual_npc')
                THEN 'character'
            WHEN TRIM(COALESCE(source_kind, '')) = ''
                THEN 'manual_npc'
            ELSE source_kind
        END
        """
    )
    connection.execute(
        """
        UPDATE campaign_combatants
        SET source_ref = CASE
            WHEN source_kind = 'character'
                THEN COALESCE(character_slug, '')
            WHEN source_ref IS NULL
                THEN ''
            ELSE source_ref
        END
        """
    )
