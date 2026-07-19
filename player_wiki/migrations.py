from __future__ import annotations

import hashlib
import errno
import json
import os
import re
import sqlite3
import stat
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Sequence

from .sqlite_safety import (
    SQLiteMigrationStorageEvidence,
    SQLiteSnapshotEvidence,
    collect_migration_storage_evidence,
    ensure_migration_free_space,
    snapshot_sqlite_database,
)


BASELINE_SCHEMA_SQL = """
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
    frontend_mode TEXT NOT NULL DEFAULT 'flask' CHECK (frontend_mode IN ('flask', 'gen2')),
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
    recipient_scope TEXT NOT NULL DEFAULT 'global',
    recipient_user_id INTEGER,
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
    subsection TEXT NOT NULL DEFAULT '',
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
    player_detail_visible INTEGER NOT NULL DEFAULT 0,
    source_kind TEXT NOT NULL DEFAULT 'manual_npc' CHECK (source_kind IN ('character', 'manual_npc', 'dm_statblock', 'systems_monster')),
    source_ref TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL,
    turn_value INTEGER NOT NULL DEFAULT 0,
    initiative_bonus INTEGER NOT NULL DEFAULT 0,
    dexterity_modifier INTEGER NOT NULL DEFAULT 0,
    initiative_priority INTEGER NOT NULL DEFAULT 1,
    current_hp INTEGER NOT NULL DEFAULT 0,
    max_hp INTEGER NOT NULL DEFAULT 0,
    temp_hp INTEGER NOT NULL DEFAULT 0,
    movement_total INTEGER NOT NULL DEFAULT 0,
    movement_remaining INTEGER NOT NULL DEFAULT 0,
    has_action INTEGER NOT NULL DEFAULT 1,
    has_bonus_action INTEGER NOT NULL DEFAULT 1,
    has_reaction INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 1,
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

CREATE TABLE IF NOT EXISTS campaign_combatant_resource_counters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combatant_id INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    label TEXT NOT NULL,
    current_value INTEGER NOT NULL DEFAULT 0,
    max_value INTEGER NOT NULL DEFAULT 0,
    reset_label TEXT NOT NULL DEFAULT '',
    source_label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    updated_by_user_id INTEGER,
    UNIQUE (combatant_id, resource_key),
    CHECK (current_value >= 0),
    CHECK (max_value >= 0),
    CHECK (current_value <= max_value),
    FOREIGN KEY (combatant_id) REFERENCES campaign_combatants(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS campaign_combatant_resource_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combatant_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    note TEXT NOT NULL,
    source_label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    FOREIGN KEY (combatant_id) REFERENCES campaign_combatants(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_combatants_campaign_order
ON campaign_combatants(campaign_slug, turn_value DESC, display_name, id);

CREATE INDEX IF NOT EXISTS idx_campaign_combat_conditions_combatant
ON campaign_combat_conditions(combatant_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_campaign_combatant_resource_counters_combatant
ON campaign_combatant_resource_counters(combatant_id, resource_key, id);

CREATE INDEX IF NOT EXISTS idx_campaign_combatant_resource_notes_combatant
ON campaign_combatant_resource_notes(combatant_id, id);

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

CREATE TABLE IF NOT EXISTS systems_shared_entry_edit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    entry_slug TEXT NOT NULL,
    original_source_identity_json TEXT NOT NULL DEFAULT '{}',
    edited_fields_json TEXT NOT NULL DEFAULT '[]',
    actor_user_id INTEGER,
    audit_event_type TEXT NOT NULL,
    audit_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_systems_shared_entry_edit_events_entry
ON systems_shared_entry_edit_events(library_slug, entry_key, created_at DESC, id DESC);

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
    allow_dm_shared_core_entry_edits INTEGER NOT NULL DEFAULT 0,
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


_PLAYER_WIKI_RECONCILIATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS player_wiki_reconciliation_operations (
    operation_id TEXT PRIMARY KEY
        CHECK (
            length(operation_id) = 32
            AND operation_id = lower(operation_id)
            AND operation_id NOT GLOB '*[^0-9a-f]*'
        ),
    campaign_slug TEXT NOT NULL
        CHECK (
            campaign_slug <> ''
            AND campaign_slug = trim(campaign_slug)
            AND campaign_slug = lower(campaign_slug)
            AND campaign_slug NOT GLOB '*[^a-z0-9-]*'
        ),
    page_ref TEXT NOT NULL
        CHECK (
            page_ref <> ''
            AND page_ref = trim(page_ref)
            AND page_ref NOT LIKE '/%'
            AND page_ref NOT LIKE '%/'
            AND page_ref NOT LIKE '%\\%'
            AND page_ref NOT LIKE '%//%'
            AND ('/' || page_ref || '/') NOT LIKE '%/../%'
            AND ('/' || page_ref || '/') NOT LIKE '%/./%'
        ),
    operation_kind TEXT NOT NULL
        CHECK (operation_kind IN ('create', 'update', 'unpublish', 'api_upsert')),
    primary_authority TEXT NOT NULL
        CHECK (primary_authority IN ('markdown', 'image')),
    desired_primary_ref TEXT NOT NULL
        CHECK (
            desired_primary_ref <> ''
            AND desired_primary_ref = trim(desired_primary_ref)
            AND desired_primary_ref NOT LIKE '/%'
            AND desired_primary_ref NOT LIKE '%/'
            AND desired_primary_ref NOT LIKE '%\\%'
            AND desired_primary_ref NOT LIKE '%//%'
            AND ('/' || desired_primary_ref || '/') NOT LIKE '%/../%'
            AND ('/' || desired_primary_ref || '/') NOT LIKE '%/./%'
        ),
    previous_primary_digest TEXT NOT NULL
        CHECK (
            previous_primary_digest = ''
            OR (
                length(previous_primary_digest) = 64
                AND previous_primary_digest = lower(previous_primary_digest)
                AND previous_primary_digest NOT GLOB '*[^0-9a-f]*'
            )
        ),
    desired_primary_digest TEXT NOT NULL
        CHECK (
            length(desired_primary_digest) = 64
            AND desired_primary_digest = lower(desired_primary_digest)
            AND desired_primary_digest NOT GLOB '*[^0-9a-f]*'
        ),
    previous_markdown_digest TEXT NOT NULL
        CHECK (
            previous_markdown_digest = ''
            OR (
                length(previous_markdown_digest) = 64
                AND previous_markdown_digest = lower(previous_markdown_digest)
                AND previous_markdown_digest NOT GLOB '*[^0-9a-f]*'
            )
        ),
    desired_markdown_digest TEXT NOT NULL
        CHECK (
            length(desired_markdown_digest) = 64
            AND desired_markdown_digest = lower(desired_markdown_digest)
            AND desired_markdown_digest NOT GLOB '*[^0-9a-f]*'
        ),
    desired_markdown BLOB,
    audit_event_type TEXT,
    audit_actor_user_id INTEGER,
    audit_metadata_json TEXT,
    state TEXT NOT NULL
        CHECK (state IN ('prepared', 'repository_pending', 'completed', 'aborted', 'conflict')),
    error_code TEXT NOT NULL DEFAULT ''
        CHECK (
            length(error_code) <= 80
            AND error_code = lower(error_code)
            AND error_code NOT GLOB '*[^a-z0-9_-]*'
        ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (state IN ('prepared', 'conflict')
            AND typeof(desired_markdown) = 'blob'
            AND length(desired_markdown) > 0
            AND length(desired_markdown) <= 100663296)
        OR
        (state IN ('repository_pending', 'completed', 'aborted')
            AND desired_markdown IS NULL)
    ),
    CHECK (
        (audit_event_type IS NULL
            AND audit_actor_user_id IS NULL
            AND audit_metadata_json IS NULL)
        OR
        (audit_event_type IS NOT NULL
            AND audit_event_type <> ''
            AND length(CAST(audit_event_type AS BLOB)) <= 128
            AND audit_metadata_json IS NOT NULL
            AND length(CAST(audit_metadata_json AS BLOB)) <= 65536)
    ),
    FOREIGN KEY (audit_actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_player_wiki_reconciliation_active_page
ON player_wiki_reconciliation_operations(campaign_slug, page_ref)
WHERE state IN ('prepared', 'repository_pending', 'conflict');

CREATE INDEX IF NOT EXISTS idx_player_wiki_reconciliation_recovery
ON player_wiki_reconciliation_operations(state, updated_at, operation_id);
"""


SCHEMA_V2_SQL = BASELINE_SCHEMA_SQL + "\n" + _PLAYER_WIKI_RECONCILIATION_SCHEMA_SQL


_PLAYER_WIKI_DELETION_RECONCILIATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS player_wiki_deletion_operations (
    operation_id TEXT PRIMARY KEY
        CHECK (
            length(operation_id) = 32
            AND operation_id = lower(operation_id)
            AND operation_id NOT GLOB '*[^0-9a-f]*'
        ),
    campaign_slug TEXT NOT NULL
        CHECK (
            campaign_slug <> ''
            AND campaign_slug = trim(campaign_slug)
            AND length(CAST(campaign_slug AS BLOB)) <= 128
            AND campaign_slug = lower(campaign_slug)
            AND campaign_slug NOT GLOB '*[^a-z0-9-]*'
        ),
    page_ref TEXT NOT NULL
        CHECK (
            page_ref <> ''
            AND page_ref = trim(page_ref)
            AND length(CAST(page_ref AS BLOB)) <= 2048
            AND page_ref NOT LIKE '/%'
            AND page_ref NOT LIKE '%/'
            AND page_ref NOT LIKE '%\\%'
            AND page_ref NOT LIKE '%//%'
            AND ('/' || page_ref || '/') NOT LIKE '%/../%'
            AND ('/' || page_ref || '/') NOT LIKE '%/./%'
        ),
    source_ref TEXT NOT NULL
        CHECK (
            source_ref = page_ref || '.md'
            AND length(CAST(source_ref AS BLOB)) <= 2051
        ),
    tombstone_ref TEXT NOT NULL
        CHECK (
            tombstone_ref <> ''
            AND tombstone_ref = trim(tombstone_ref)
            AND length(CAST(tombstone_ref AS BLOB)) <= 2150
            AND tombstone_ref NOT LIKE '/%'
            AND tombstone_ref NOT LIKE '%/'
            AND tombstone_ref NOT LIKE '%\\%'
            AND tombstone_ref NOT LIKE '%//%'
            AND tombstone_ref NOT LIKE '%.md'
            AND ('/' || tombstone_ref || '/') NOT LIKE '%/../%'
            AND ('/' || tombstone_ref || '/') NOT LIKE '%/./%'
        ),
    source_sha256 TEXT NOT NULL
        CHECK (
            length(source_sha256) = 64
            AND source_sha256 = lower(source_sha256)
            AND source_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
    source_size INTEGER NOT NULL
        CHECK (source_size > 0 AND source_size <= 100663296),
    operation_kind TEXT NOT NULL
        CHECK (operation_kind IN ('browser_delete', 'api_delete')),
    audit_event_type TEXT,
    audit_actor_user_id INTEGER,
    audit_metadata_json TEXT,
    state TEXT NOT NULL
        CHECK (state IN ('prepared', 'repository_pending', 'conflict')),
    error_code TEXT NOT NULL DEFAULT ''
        CHECK (
            length(error_code) <= 80
            AND error_code = lower(error_code)
            AND error_code NOT GLOB '*[^a-z0-9_-]*'
        ),
    created_at TEXT NOT NULL CHECK (length(CAST(created_at AS BLOB)) BETWEEN 1 AND 64),
    updated_at TEXT NOT NULL CHECK (length(CAST(updated_at AS BLOB)) BETWEEN 1 AND 64),
    CHECK (
        (operation_kind = 'api_delete'
            AND audit_event_type IS NULL
            AND audit_actor_user_id IS NULL
            AND audit_metadata_json IS NULL)
        OR
        (operation_kind = 'browser_delete'
            AND audit_event_type IS NOT NULL
            AND audit_event_type <> ''
            AND length(CAST(audit_event_type AS BLOB)) <= 128
            AND audit_metadata_json IS NOT NULL
            AND length(CAST(audit_metadata_json AS BLOB)) <= 65536)
    ),
    FOREIGN KEY (audit_actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_player_wiki_deletion_active_page
ON player_wiki_deletion_operations(campaign_slug, page_ref)
WHERE state IN ('prepared', 'repository_pending', 'conflict');

CREATE INDEX IF NOT EXISTS idx_player_wiki_deletion_recovery
ON player_wiki_deletion_operations(state, updated_at, operation_id);
"""


SCHEMA_V3_SQL = SCHEMA_V2_SQL + "\n" + _PLAYER_WIKI_DELETION_RECONCILIATION_SCHEMA_SQL


_CHARACTER_RECONCILIATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS character_reconciliation_operations (
    operation_id TEXT PRIMARY KEY
        CHECK (
            length(operation_id) = 32
            AND operation_id = lower(operation_id)
            AND operation_id NOT GLOB '*[^0-9a-f]*'
        ),
    campaign_slug TEXT NOT NULL
        CHECK (
            campaign_slug <> ''
            AND campaign_slug = trim(campaign_slug)
            AND length(CAST(campaign_slug AS BLOB)) <= 128
            AND campaign_slug = lower(campaign_slug)
            AND campaign_slug NOT GLOB '*[^a-z0-9-]*'
        ),
    character_slug TEXT NOT NULL
        CHECK (
            character_slug <> ''
            AND character_slug = trim(character_slug)
            AND length(CAST(character_slug AS BLOB)) <= 255
            AND character_slug NOT LIKE '%/%'
            AND character_slug NOT LIKE '%\\%'
            AND character_slug NOT IN ('.', '..')
        ),
    operation_kind TEXT NOT NULL
        CHECK (operation_kind IN (
            'native_create',
            'manual_import',
            'markdown_import',
            'pdf_import',
            'content_api_create'
        )),
    previous_definition_digest TEXT NOT NULL CHECK (previous_definition_digest = ''),
    desired_definition_digest TEXT NOT NULL
        CHECK (
            length(desired_definition_digest) = 64
            AND desired_definition_digest = lower(desired_definition_digest)
            AND desired_definition_digest NOT GLOB '*[^0-9a-f]*'
        ),
    previous_import_digest TEXT NOT NULL CHECK (previous_import_digest = ''),
    desired_import_digest TEXT NOT NULL
        CHECK (
            length(desired_import_digest) = 64
            AND desired_import_digest = lower(desired_import_digest)
            AND desired_import_digest NOT GLOB '*[^0-9a-f]*'
        ),
    previous_state_digest TEXT NOT NULL CHECK (previous_state_digest = ''),
    desired_state_digest TEXT NOT NULL
        CHECK (
            length(desired_state_digest) = 64
            AND desired_state_digest = lower(desired_state_digest)
            AND desired_state_digest NOT GLOB '*[^0-9a-f]*'
        ),
    desired_definition_yaml BLOB NOT NULL,
    desired_import_yaml BLOB NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('prepared', 'repository_pending', 'conflict')),
    error_code TEXT NOT NULL DEFAULT ''
        CHECK (
            length(CAST(error_code AS BLOB)) <= 80
            AND error_code = lower(error_code)
            AND error_code NOT GLOB '*[^a-z0-9_-]*'
        ),
    created_at TEXT NOT NULL CHECK (length(CAST(created_at AS BLOB)) BETWEEN 1 AND 64),
    updated_at TEXT NOT NULL CHECK (length(CAST(updated_at AS BLOB)) BETWEEN 1 AND 64),
    CHECK (
        typeof(desired_definition_yaml) = 'blob'
        AND length(desired_definition_yaml) > 0
        AND typeof(desired_import_yaml) = 'blob'
        AND length(desired_import_yaml) > 0
        AND length(desired_definition_yaml) + length(desired_import_yaml) <= 100663296
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reconciliation_active_character
ON character_reconciliation_operations(campaign_slug, character_slug)
WHERE state IN ('prepared', 'repository_pending', 'conflict');

CREATE INDEX IF NOT EXISTS idx_character_reconciliation_recovery
ON character_reconciliation_operations(state, updated_at, operation_id);
"""


SCHEMA_V4_SQL = SCHEMA_V3_SQL + "\n" + _CHARACTER_RECONCILIATION_SCHEMA_SQL


_CHARACTER_RECONCILIATION_UPDATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS character_reconciliation_operations (
    operation_id TEXT PRIMARY KEY
        CHECK (
            length(operation_id) = 32
            AND operation_id = lower(operation_id)
            AND operation_id NOT GLOB '*[^0-9a-f]*'
        ),
    campaign_slug TEXT NOT NULL
        CHECK (
            campaign_slug <> ''
            AND campaign_slug = trim(campaign_slug)
            AND length(CAST(campaign_slug AS BLOB)) <= 128
            AND campaign_slug = lower(campaign_slug)
            AND campaign_slug NOT GLOB '*[^a-z0-9-]*'
        ),
    character_slug TEXT NOT NULL
        CHECK (
            character_slug <> ''
            AND character_slug = trim(character_slug)
            AND length(CAST(character_slug AS BLOB)) <= 255
            AND character_slug NOT LIKE '%/%'
            AND character_slug NOT LIKE '%\\%'
            AND character_slug NOT IN ('.', '..')
        ),
    operation_kind TEXT NOT NULL
        CHECK (operation_kind IN (
            'native_create',
            'manual_import',
            'markdown_import',
            'pdf_import',
            'content_api_create',
            'interactive_update'
        )),
    previous_definition_digest TEXT NOT NULL,
    desired_definition_digest TEXT NOT NULL
        CHECK (
            length(desired_definition_digest) = 64
            AND desired_definition_digest = lower(desired_definition_digest)
            AND desired_definition_digest NOT GLOB '*[^0-9a-f]*'
        ),
    previous_import_digest TEXT NOT NULL,
    desired_import_digest TEXT NOT NULL
        CHECK (
            length(desired_import_digest) = 64
            AND desired_import_digest = lower(desired_import_digest)
            AND desired_import_digest NOT GLOB '*[^0-9a-f]*'
        ),
    previous_state_digest TEXT NOT NULL,
    desired_state_digest TEXT NOT NULL
        CHECK (
            length(desired_state_digest) = 64
            AND desired_state_digest = lower(desired_state_digest)
            AND desired_state_digest NOT GLOB '*[^0-9a-f]*'
        ),
    previous_state_revision INTEGER NOT NULL,
    desired_state_revision INTEGER NOT NULL,
    desired_definition_yaml BLOB NOT NULL,
    desired_import_yaml BLOB NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('prepared', 'repository_pending', 'conflict')),
    error_code TEXT NOT NULL DEFAULT ''
        CHECK (
            length(CAST(error_code AS BLOB)) <= 80
            AND error_code = lower(error_code)
            AND error_code NOT GLOB '*[^a-z0-9_-]*'
        ),
    created_at TEXT NOT NULL CHECK (length(CAST(created_at AS BLOB)) BETWEEN 1 AND 64),
    updated_at TEXT NOT NULL CHECK (length(CAST(updated_at AS BLOB)) BETWEEN 1 AND 64),
    CHECK (
        typeof(desired_definition_yaml) = 'blob'
        AND length(desired_definition_yaml) > 0
        AND typeof(desired_import_yaml) = 'blob'
        AND length(desired_import_yaml) > 0
        AND length(desired_definition_yaml) + length(desired_import_yaml) <= 100663296
    ),
    CHECK (
        (
            operation_kind IN (
                'native_create',
                'manual_import',
                'markdown_import',
                'pdf_import',
                'content_api_create'
            )
            AND previous_definition_digest = ''
            AND previous_import_digest = ''
            AND previous_state_digest = ''
            AND previous_state_revision = 0
            AND desired_state_revision = 1
        )
        OR
        (
            operation_kind = 'interactive_update'
            AND length(previous_definition_digest) = 64
            AND previous_definition_digest = lower(previous_definition_digest)
            AND previous_definition_digest NOT GLOB '*[^0-9a-f]*'
            AND length(previous_import_digest) = 64
            AND previous_import_digest = lower(previous_import_digest)
            AND previous_import_digest NOT GLOB '*[^0-9a-f]*'
            AND length(previous_state_digest) = 64
            AND previous_state_digest = lower(previous_state_digest)
            AND previous_state_digest NOT GLOB '*[^0-9a-f]*'
            AND previous_state_revision >= 1
            AND desired_state_revision = previous_state_revision + 1
        )
    )
);
"""


_CHARACTER_RECONCILIATION_UPDATE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reconciliation_active_character
ON character_reconciliation_operations(campaign_slug, character_slug)
WHERE state IN ('prepared', 'repository_pending', 'conflict');

CREATE INDEX IF NOT EXISTS idx_character_reconciliation_recovery
ON character_reconciliation_operations(state, updated_at, operation_id);
"""


SCHEMA_V5_SQL = (
    SCHEMA_V3_SQL
    + "\n"
    + _CHARACTER_RECONCILIATION_UPDATE_TABLE_SQL
    + "\n"
    + _CHARACTER_RECONCILIATION_UPDATE_INDEX_SQL
)


_CHARACTER_RECONCILIATION_V5_INVARIANT_SQL = """        (
            operation_kind IN (
                'native_create',
                'manual_import',
                'markdown_import',
                'pdf_import',
                'content_api_create'
            )
            AND previous_definition_digest = ''
            AND previous_import_digest = ''
            AND previous_state_digest = ''
            AND previous_state_revision = 0
            AND desired_state_revision = 1
        )
        OR
        (
            operation_kind = 'interactive_update'
            AND length(previous_definition_digest) = 64
            AND previous_definition_digest = lower(previous_definition_digest)
            AND previous_definition_digest NOT GLOB '*[^0-9a-f]*'
            AND length(previous_import_digest) = 64
            AND previous_import_digest = lower(previous_import_digest)
            AND previous_import_digest NOT GLOB '*[^0-9a-f]*'
            AND length(previous_state_digest) = 64
            AND previous_state_digest = lower(previous_state_digest)
            AND previous_state_digest NOT GLOB '*[^0-9a-f]*'
            AND previous_state_revision >= 1
            AND desired_state_revision = previous_state_revision + 1
        )"""


_CHARACTER_RECONCILIATION_V6_INVARIANT_SQL = """        (
            operation_kind IN (
                'native_create',
                'manual_import',
                'content_api_create'
            )
            AND previous_definition_digest = ''
            AND previous_import_digest = ''
            AND previous_state_digest = ''
            AND previous_state_revision = 0
            AND desired_state_revision = 1
        )
        OR
        (
            operation_kind IN ('markdown_import', 'pdf_import')
            AND (
                (
                    previous_definition_digest = ''
                    AND previous_import_digest = ''
                    AND previous_state_digest = ''
                    AND previous_state_revision = 0
                    AND desired_state_revision = 1
                )
                OR
                (
                    length(previous_definition_digest) = 64
                    AND previous_definition_digest = lower(previous_definition_digest)
                    AND previous_definition_digest NOT GLOB '*[^0-9a-f]*'
                    AND length(previous_import_digest) = 64
                    AND previous_import_digest = lower(previous_import_digest)
                    AND previous_import_digest NOT GLOB '*[^0-9a-f]*'
                    AND length(previous_state_digest) = 64
                    AND previous_state_digest = lower(previous_state_digest)
                    AND previous_state_digest NOT GLOB '*[^0-9a-f]*'
                    AND previous_state_revision >= 1
                    AND (
                        (
                            desired_state_revision = previous_state_revision
                            AND desired_state_digest = previous_state_digest
                        )
                        OR (
                            desired_state_revision = previous_state_revision + 1
                            AND desired_state_digest <> previous_state_digest
                        )
                    )
                )
            )
        )
        OR
        (
            operation_kind = 'interactive_update'
            AND length(previous_definition_digest) = 64
            AND previous_definition_digest = lower(previous_definition_digest)
            AND previous_definition_digest NOT GLOB '*[^0-9a-f]*'
            AND length(previous_import_digest) = 64
            AND previous_import_digest = lower(previous_import_digest)
            AND previous_import_digest NOT GLOB '*[^0-9a-f]*'
            AND length(previous_state_digest) = 64
            AND previous_state_digest = lower(previous_state_digest)
            AND previous_state_digest NOT GLOB '*[^0-9a-f]*'
            AND previous_state_revision >= 1
            AND desired_state_revision = previous_state_revision + 1
        )"""


_CHARACTER_RECONCILIATION_REIMPORT_TABLE_SQL = (
    _CHARACTER_RECONCILIATION_UPDATE_TABLE_SQL.replace(
        _CHARACTER_RECONCILIATION_V5_INVARIANT_SQL,
        _CHARACTER_RECONCILIATION_V6_INVARIANT_SQL,
    )
)


CURRENT_SCHEMA_SQL = (
    SCHEMA_V3_SQL
    + "\n"
    + _CHARACTER_RECONCILIATION_REIMPORT_TABLE_SQL
    + "\n"
    + _CHARACTER_RECONCILIATION_UPDATE_INDEX_SQL
)


class MigrationError(RuntimeError):
    """Raised when migration metadata or execution cannot be trusted."""


@dataclass(frozen=True, slots=True)
class MigrationHooks:
    """Fault-injection seams used by migration transaction tests."""

    before_migration: Callable[[int, str], None] | None = None
    before_statement: Callable[[int, str], None] | None = None
    after_statement: Callable[[int, str], None] | None = None
    before_ledger_insert: Callable[[int, str], None] | None = None
    after_ledger_insert: Callable[[int, str], None] | None = None


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    checksum: str
    payload: "MigrationPayload"


@dataclass(frozen=True, slots=True)
class ColumnAddition:
    name: str
    sql: str
    after_add_statements: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TransformSpec:
    table: str | None
    additions: tuple[ColumnAddition, ...] = ()
    statements: tuple[str, ...] = ()
    current_schema_tokens: tuple[str, ...] = ()
    skip_when_table_missing: bool = False


@dataclass(frozen=True, slots=True)
class MigrationPayload:
    schema_sql: str
    transforms: tuple[TransformSpec, ...]


@dataclass(frozen=True, slots=True)
class MigrationResult:
    from_version: int
    to_version: int
    applied_versions: tuple[int, ...]
    applied_names: tuple[str, ...]
    backup_evidence: SQLiteSnapshotEvidence | None
    no_op: bool

    @property
    def backup_path(self) -> Path | None:
        if self.backup_evidence is None:
            return None
        return self.backup_evidence.final_path


class MigrationContext:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        hooks: MigrationHooks,
    ) -> None:
        self.connection = connection
        self.hooks = hooks
        self.statement_count = 0

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        self.statement_count += 1
        if self.hooks.before_statement is not None:
            self.hooks.before_statement(self.statement_count, sql)
        cursor = self.connection.execute(sql, parameters)
        if self.hooks.after_statement is not None:
            self.hooks.after_statement(self.statement_count, sql)
        return cursor


_BASELINE_NAME = "0001_legacy_current_baseline"
_BASELINE_PAYLOAD = MigrationPayload(
    schema_sql=BASELINE_SCHEMA_SQL,
    transforms=(
        TransformSpec(
            table="user_preferences",
            additions=(
                ColumnAddition(
                    "session_chat_order",
                    "ALTER TABLE user_preferences ADD COLUMN session_chat_order TEXT NOT NULL DEFAULT 'newest_first'",
                ),
                ColumnAddition(
                    "frontend_mode",
                    "ALTER TABLE user_preferences ADD COLUMN frontend_mode TEXT NOT NULL DEFAULT 'flask'",
                ),
            ),
        ),
        TransformSpec(
            table="campaign_system_policies",
            additions=(
                ColumnAddition(
                    "allow_dm_shared_core_entry_edits",
                    """ALTER TABLE campaign_system_policies
                    ADD COLUMN allow_dm_shared_core_entry_edits INTEGER NOT NULL DEFAULT 0""",
                ),
            ),
        ),
        TransformSpec(
            table="campaign_visibility_settings",
            current_schema_tokens=("'systems'", "'combat'", "'dm_content'"),
            statements=(
                "ALTER TABLE campaign_visibility_settings RENAME TO campaign_visibility_settings_legacy",
                """CREATE TABLE campaign_visibility_settings (
                    campaign_slug TEXT NOT NULL,
                    scope TEXT NOT NULL CHECK (scope IN (
                        'campaign', 'wiki', 'systems', 'session', 'combat', 'characters', 'dm_content'
                    )),
                    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'players', 'dm', 'private')),
                    updated_at TEXT NOT NULL,
                    updated_by_user_id INTEGER,
                    PRIMARY KEY (campaign_slug, scope),
                    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
                )""",
                """INSERT INTO campaign_visibility_settings
                (campaign_slug, scope, visibility, updated_at, updated_by_user_id)
                SELECT campaign_slug, scope, visibility, updated_at, updated_by_user_id
                FROM campaign_visibility_settings_legacy""",
                "DROP TABLE campaign_visibility_settings_legacy",
            ),
        ),
        TransformSpec(
            table="campaign_session_messages",
            additions=(
                ColumnAddition(
                    "recipient_scope",
                    """ALTER TABLE campaign_session_messages
                    ADD COLUMN recipient_scope TEXT NOT NULL DEFAULT 'global'""",
                ),
                ColumnAddition(
                    "recipient_user_id",
                    "ALTER TABLE campaign_session_messages ADD COLUMN recipient_user_id INTEGER",
                ),
            ),
            statements=(
                """CREATE INDEX IF NOT EXISTS idx_campaign_session_messages_session_recipient
                ON campaign_session_messages(
                    session_id, recipient_scope, recipient_user_id, created_at, id
                )""",
            ),
        ),
        TransformSpec(
            table="campaign_session_articles",
            additions=(
                ColumnAddition(
                    "source_page_ref",
                    """ALTER TABLE campaign_session_articles
                    ADD COLUMN source_page_ref TEXT NOT NULL DEFAULT ''""",
                ),
            ),
        ),
        TransformSpec(
            table=None,
            statements=(
                """CREATE TABLE IF NOT EXISTS campaign_session_states (
                    campaign_slug TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    updated_by_user_id INTEGER,
                    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
                )""",
            ),
        ),
        TransformSpec(
            table="campaign_combat_trackers",
            skip_when_table_missing=True,
            additions=(
                ColumnAddition(
                    "revision",
                    """ALTER TABLE campaign_combat_trackers
                    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1""",
                ),
            ),
            statements=(
                """UPDATE campaign_combat_trackers SET revision = CASE
                WHEN revision IS NULL OR revision < 1 THEN 1 ELSE revision END""",
            ),
        ),
        TransformSpec(
            table="campaign_combatants",
            skip_when_table_missing=True,
            additions=(
                ColumnAddition(
                    "revision",
                    "ALTER TABLE campaign_combatants ADD COLUMN revision INTEGER NOT NULL DEFAULT 1",
                ),
            ),
            statements=(
                """UPDATE campaign_combatants SET revision = CASE
                WHEN revision IS NULL OR revision < 1 THEN 1 ELSE revision END""",
            ),
        ),
        TransformSpec(
            table="campaign_combatants",
            skip_when_table_missing=True,
            additions=(
                ColumnAddition(
                    "source_kind",
                    """ALTER TABLE campaign_combatants
                    ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'manual_npc'""",
                ),
                ColumnAddition(
                    "source_ref",
                    "ALTER TABLE campaign_combatants ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''",
                ),
                ColumnAddition(
                    "player_detail_visible",
                    """ALTER TABLE campaign_combatants
                    ADD COLUMN player_detail_visible INTEGER NOT NULL DEFAULT 0""",
                ),
            ),
            statements=(
                """UPDATE campaign_combatants SET source_kind = CASE
                WHEN character_slug IS NOT NULL
                    AND TRIM(COALESCE(source_kind, '')) IN ('', 'manual_npc') THEN 'character'
                WHEN TRIM(COALESCE(source_kind, '')) = '' THEN 'manual_npc'
                ELSE source_kind END""",
                """UPDATE campaign_combatants SET source_ref = CASE
                WHEN source_kind = 'character' THEN COALESCE(character_slug, '')
                WHEN source_ref IS NULL THEN '' ELSE source_ref END""",
                """UPDATE campaign_combatants SET player_detail_visible = CASE
                WHEN combatant_type = 'player_character' THEN 1
                WHEN COALESCE(player_detail_visible, 0) NOT IN (0, 1) THEN 0
                ELSE COALESCE(player_detail_visible, 0) END""",
            ),
        ),
        TransformSpec(
            table="campaign_combatants",
            skip_when_table_missing=True,
            additions=(
                ColumnAddition(
                    "dexterity_modifier",
                    """ALTER TABLE campaign_combatants
                    ADD COLUMN dexterity_modifier INTEGER NOT NULL DEFAULT 0""",
                    (
                        """UPDATE campaign_combatants
                        SET dexterity_modifier = COALESCE(initiative_bonus, 0)""",
                    ),
                ),
                ColumnAddition(
                    "initiative_priority",
                    """ALTER TABLE campaign_combatants
                    ADD COLUMN initiative_priority INTEGER NOT NULL DEFAULT 1""",
                ),
            ),
            statements=(
                """UPDATE campaign_combatants SET initiative_priority = CASE
                WHEN initiative_priority IS NULL OR initiative_priority < 1
                THEN 1 ELSE initiative_priority END""",
                """CREATE INDEX IF NOT EXISTS idx_campaign_combatants_campaign_order_v2
                ON campaign_combatants(
                    campaign_slug, turn_value DESC, dexterity_modifier DESC,
                    initiative_priority, display_name, id
                )""",
            ),
        ),
        TransformSpec(
            table=None,
            statements=(
                """CREATE TABLE IF NOT EXISTS campaign_combatant_resource_counters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    combatant_id INTEGER NOT NULL,
                    resource_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    current_value INTEGER NOT NULL DEFAULT 0,
                    max_value INTEGER NOT NULL DEFAULT 0,
                    reset_label TEXT NOT NULL DEFAULT '',
                    source_label TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by_user_id INTEGER,
                    updated_by_user_id INTEGER,
                    UNIQUE (combatant_id, resource_key),
                    CHECK (current_value >= 0),
                    CHECK (max_value >= 0),
                    CHECK (current_value <= max_value),
                    FOREIGN KEY (combatant_id) REFERENCES campaign_combatants(id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
                    FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
                )""",
                """CREATE TABLE IF NOT EXISTS campaign_combatant_resource_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    combatant_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    note TEXT NOT NULL,
                    source_label TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    created_by_user_id INTEGER,
                    FOREIGN KEY (combatant_id) REFERENCES campaign_combatants(id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
                )""",
                """CREATE INDEX IF NOT EXISTS idx_campaign_combatant_resource_counters_combatant
                ON campaign_combatant_resource_counters(combatant_id, resource_key, id)""",
                """CREATE INDEX IF NOT EXISTS idx_campaign_combatant_resource_notes_combatant
                ON campaign_combatant_resource_notes(combatant_id, id)""",
            ),
        ),
        TransformSpec(
            table="campaign_dm_statblocks",
            skip_when_table_missing=True,
            additions=(
                ColumnAddition(
                    "subsection",
                    """ALTER TABLE campaign_dm_statblocks
                    ADD COLUMN subsection TEXT NOT NULL DEFAULT ''""",
                ),
            ),
            statements=(
                """UPDATE campaign_dm_statblocks SET subsection = 'Malverine Minions'
                WHERE campaign_slug = 'linden-pass'
                AND TRIM(COALESCE(subsection, '')) = ''
                AND LOWER(TRIM(COALESCE(title, ''))) IN
                ('eyestitched watcher', 'earless listener', 'mute scribe')""",
            ),
        ),
    )
)
_BASELINE_CHECKSUM = "bf860bf11bb6c9bc8410c57cba91951825248d69a4bd52bd545bff1b2f717a16"
_CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

_PLAYER_WIKI_RECONCILIATION_NAME = "0002_player_wiki_reconciliation_operations"
_PLAYER_WIKI_RECONCILIATION_PAYLOAD = MigrationPayload(
    schema_sql=SCHEMA_V2_SQL,
    transforms=(),
)
_PLAYER_WIKI_RECONCILIATION_CHECKSUM = "30f45aa2aad64bd50e19760051b6d634b51a1c8f947614b82873d9e96d081d9c"

_PLAYER_WIKI_DELETION_RECONCILIATION_NAME = "0003_player_wiki_deletion_reconciliation_operations"
_PLAYER_WIKI_DELETION_RECONCILIATION_PAYLOAD = MigrationPayload(
    schema_sql=SCHEMA_V3_SQL,
    transforms=(),
)
_PLAYER_WIKI_DELETION_RECONCILIATION_CHECKSUM = "78c9613b4b69c713c30f36809b1538092cdc32da88df67a8c69704489efb50d0"

_CHARACTER_RECONCILIATION_NAME = "0004_character_reconciliation_operations"
_CHARACTER_RECONCILIATION_PAYLOAD = MigrationPayload(
    schema_sql=SCHEMA_V4_SQL,
    transforms=(),
)
_CHARACTER_RECONCILIATION_CHECKSUM = "7555546c534606e8bb43f745df99d870bcab6ceb6029eaddd7716a8f1aa447e4"

_CHARACTER_RECONCILIATION_UPDATES_NAME = "0005_character_reconciliation_updates"
_CHARACTER_RECONCILIATION_UPDATES_PAYLOAD = MigrationPayload(
    schema_sql=SCHEMA_V5_SQL,
    transforms=(
        TransformSpec(
            table="character_reconciliation_operations",
            statements=(
                "ALTER TABLE character_reconciliation_operations RENAME TO character_reconciliation_operations_v4",
                _CHARACTER_RECONCILIATION_UPDATE_TABLE_SQL,
                """INSERT INTO character_reconciliation_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    state, error_code, created_at, updated_at
                )
                SELECT
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    0, 1,
                    desired_definition_yaml, desired_import_yaml,
                    state, error_code, created_at, updated_at
                FROM character_reconciliation_operations_v4""",
                "DROP TABLE character_reconciliation_operations_v4",
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reconciliation_active_character
                ON character_reconciliation_operations(campaign_slug, character_slug)
                WHERE state IN ('prepared', 'repository_pending', 'conflict')""",
                """CREATE INDEX IF NOT EXISTS idx_character_reconciliation_recovery
                ON character_reconciliation_operations(state, updated_at, operation_id)""",
            ),
        ),
    ),
)
_CHARACTER_RECONCILIATION_UPDATES_CHECKSUM = "c2175e95c1c02aab259e4d5d4fbff4e7c5bb9ddc991a510f837c08752162b8ee"

_CHARACTER_REIMPORT_RECONCILIATION_NAME = "0006_character_reimport_reconciliation"
_CHARACTER_REIMPORT_RECONCILIATION_PAYLOAD = MigrationPayload(
    schema_sql=CURRENT_SCHEMA_SQL,
    transforms=(
        TransformSpec(
            table="character_reconciliation_operations",
            statements=(
                "ALTER TABLE character_reconciliation_operations RENAME TO character_reconciliation_operations_v5",
                _CHARACTER_RECONCILIATION_REIMPORT_TABLE_SQL,
                """INSERT INTO character_reconciliation_operations (
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    state, error_code, created_at, updated_at
                )
                SELECT
                    operation_id, campaign_slug, character_slug, operation_kind,
                    previous_definition_digest, desired_definition_digest,
                    previous_import_digest, desired_import_digest,
                    previous_state_digest, desired_state_digest,
                    previous_state_revision, desired_state_revision,
                    desired_definition_yaml, desired_import_yaml,
                    state, error_code, created_at, updated_at
                FROM character_reconciliation_operations_v5""",
                "DROP TABLE character_reconciliation_operations_v5",
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reconciliation_active_character
                ON character_reconciliation_operations(campaign_slug, character_slug)
                WHERE state IN ('prepared', 'repository_pending', 'conflict')""",
                """CREATE INDEX IF NOT EXISTS idx_character_reconciliation_recovery
                ON character_reconciliation_operations(state, updated_at, operation_id)""",
            ),
        ),
    ),
)
_CHARACTER_REIMPORT_RECONCILIATION_CHECKSUM = "7391aad507569340900014e6f682846c0aa900bc78adcf93a55056a4b27921b9"


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, _BASELINE_NAME, _BASELINE_CHECKSUM, _BASELINE_PAYLOAD),
    Migration(
        2,
        _PLAYER_WIKI_RECONCILIATION_NAME,
        _PLAYER_WIKI_RECONCILIATION_CHECKSUM,
        _PLAYER_WIKI_RECONCILIATION_PAYLOAD,
    ),
    Migration(
        3,
        _PLAYER_WIKI_DELETION_RECONCILIATION_NAME,
        _PLAYER_WIKI_DELETION_RECONCILIATION_CHECKSUM,
        _PLAYER_WIKI_DELETION_RECONCILIATION_PAYLOAD,
    ),
    Migration(
        4,
        _CHARACTER_RECONCILIATION_NAME,
        _CHARACTER_RECONCILIATION_CHECKSUM,
        _CHARACTER_RECONCILIATION_PAYLOAD,
    ),
    Migration(
        5,
        _CHARACTER_RECONCILIATION_UPDATES_NAME,
        _CHARACTER_RECONCILIATION_UPDATES_CHECKSUM,
        _CHARACTER_RECONCILIATION_UPDATES_PAYLOAD,
    ),
    Migration(
        6,
        _CHARACTER_REIMPORT_RECONCILIATION_NAME,
        _CHARACTER_REIMPORT_RECONCILIATION_CHECKSUM,
        _CHARACTER_REIMPORT_RECONCILIATION_PAYLOAD,
    ),
)


@dataclass(frozen=True)
class MigrationLedgerInspection:
    ledger_exists: bool
    applied_version: int
    current_version: int
    is_current: bool


def inspect_migration_ledger(
    connection: sqlite3.Connection,
    *,
    schema_sql: str = CURRENT_SCHEMA_SQL,
    registry: Sequence[Migration] = MIGRATIONS,
) -> MigrationLedgerInspection:
    """Inspect registry and ledger state without creating locks, tables, or files."""

    migrations = tuple(registry)
    validate_migration_registry(migrations, schema_sql=schema_sql)
    ledger_exists = _migration_ledger_exists(connection)
    ledger_rows = _read_and_validate_ledger(connection, migrations)
    applied_version = int(ledger_rows[-1][0]) if ledger_rows else 0
    current_version = migrations[-1].version if migrations else 0
    return MigrationLedgerInspection(
        ledger_exists=ledger_exists,
        applied_version=applied_version,
        current_version=current_version,
        is_current=ledger_exists and applied_version == current_version,
    )


def run_migrations(
    connection: sqlite3.Connection,
    *,
    database_path: Path,
    schema_sql: str,
    registry: Sequence[Migration] = MIGRATIONS,
    hooks: MigrationHooks | None = None,
    snapshotter: Callable[..., SQLiteSnapshotEvidence] = snapshot_sqlite_database,
) -> MigrationResult:
    """Validate, snapshot when needed, and apply an ordered migration prefix."""

    migrations = tuple(registry)
    validate_migration_registry(migrations, schema_sql=schema_sql)
    database_path = Path(database_path)
    with _migration_lock(database_path):
        return _run_migrations_locked(
            connection,
            database_path=database_path,
            migrations=migrations,
            hooks=hooks,
            snapshotter=snapshotter,
        )


def _run_migrations_locked(
    connection: sqlite3.Connection,
    *,
    database_path: Path,
    migrations: tuple[Migration, ...],
    hooks: MigrationHooks | None,
    snapshotter: Callable[..., SQLiteSnapshotEvidence],
) -> MigrationResult:
    ledger_rows = _read_and_validate_ledger(connection, migrations)
    from_version = int(ledger_rows[-1][0]) if ledger_rows else 0
    pending = migrations[from_version:]
    latest_version = migrations[-1].version if migrations else 0

    if not pending:
        return MigrationResult(
            from_version=from_version,
            to_version=from_version,
            applied_versions=(),
            applied_names=(),
            backup_evidence=None,
            no_op=True,
        )

    if connection.in_transaction:
        raise MigrationError("Migrations require a connection with no active transaction.")

    backup_evidence = None
    if _has_application_schema(connection):
        storage_evidence = collect_migration_storage_evidence(
            connection,
            database_path,
        )
        backup_dir = _migration_backup_dir(database_path)
        _validate_migration_backup_root(
            database_path,
            backup_dir,
            storage_evidence=storage_evidence,
            require_complete=False,
        )
        ensure_migration_free_space(
            database_path.parent,
            required_free_bytes=storage_evidence.sizing.pre_required_free_bytes,
        )
        backup_path = _next_backup_path(database_path, from_version, latest_version)
        _validate_migration_backup_root(
            database_path,
            backup_dir,
            storage_evidence=storage_evidence,
            require_complete=True,
        )
        backup_evidence = snapshotter(
            source_path=database_path,
            destination_path=backup_path,
        )
        _validate_published_migration_snapshot(
            backup_path,
            backup_evidence,
            storage_evidence=storage_evidence,
        )
        _validate_migration_backup_root(
            database_path,
            backup_dir,
            storage_evidence=storage_evidence,
            require_complete=True,
        )
        ensure_migration_free_space(
            backup_dir,
            required_free_bytes=storage_evidence.sizing.post_required_free_bytes,
        )

    hooks = hooks or MigrationHooks()
    context = MigrationContext(connection, hooks=hooks)
    applied_versions: list[int] = []
    applied_names: list[str] = []
    try:
        connection.execute("BEGIN IMMEDIATE")
        context.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        for migration in pending:
            if hooks.before_migration is not None:
                hooks.before_migration(migration.version, migration.name)
            _apply_payload(context, migration.payload)
            if hooks.before_ledger_insert is not None:
                hooks.before_ledger_insert(migration.version, migration.name)
            context.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            if hooks.after_ledger_insert is not None:
                hooks.after_ledger_insert(migration.version, migration.name)
            applied_versions.append(migration.version)
            applied_names.append(migration.name)
        connection.commit()
    except BaseException as exc:
        connection.rollback()
        if _is_storage_exhaustion(exc):
            raise MigrationError(
                "Migration could not complete because storage became unavailable."
            ) from exc
        raise

    return MigrationResult(
        from_version=from_version,
        to_version=applied_versions[-1],
        applied_versions=tuple(applied_versions),
        applied_names=tuple(applied_names),
        backup_evidence=backup_evidence,
        no_op=False,
    )


def validate_migration_registry(
    registry: Sequence[Migration],
    *,
    schema_sql: str,
) -> None:
    registry = tuple(registry)
    versions = [migration.version for migration in registry]
    names = [migration.name for migration in registry]
    if len(versions) != len(set(versions)):
        raise MigrationError("Migration registry contains duplicate versions.")
    if len(names) != len(set(names)):
        raise MigrationError("Migration registry contains duplicate names.")
    if versions != list(range(1, len(registry) + 1)):
        raise MigrationError("Migration registry versions must be ordered and gap-free from version 1.")
    for migration in registry:
        if not migration.name or not migration.name.startswith(f"{migration.version:04d}_"):
            raise MigrationError(f"Migration {migration.version} has an invalid name.")
        if _CHECKSUM_PATTERN.fullmatch(migration.checksum) is None:
            raise MigrationError(f"Migration {migration.version} has an invalid checksum.")
        expected_checksum = calculate_migration_checksum(migration.payload)
        if migration.checksum != expected_checksum:
            raise MigrationError(
                f"Migration {migration.version} checksum does not match its executable payload."
            )
    if registry and schema_sql != registry[-1].payload.schema_sql:
        raise MigrationError("Current schema does not match the latest executable migration payload.")


def calculate_migration_checksum(payload: MigrationPayload) -> str:
    canonical_payload = {
        "schema_statements": _split_sql_statements(payload.schema_sql),
        "transforms": [asdict(spec) for spec in payload.transforms],
    }
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@contextmanager
def _migration_lock(database_path: Path, *, timeout_seconds: float = 30.0):
    lock_path = Path(f"{database_path}.migration.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+b")
    acquired = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while not acquired:
            try:
                _try_acquire_file_lock(lock_file)
                acquired = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise MigrationError(
                        "Timed out waiting for the database migration lock."
                    ) from exc
                time.sleep(0.025)
        _normalize_lock_file_under_lock(lock_file)
        yield
    finally:
        if acquired:
            _release_file_lock(lock_file)
        lock_file.close()


def _normalize_lock_file_under_lock(lock_file) -> None:
    lock_file.seek(0, os.SEEK_END)
    byte_count = lock_file.tell()
    if byte_count == 1:
        return
    if byte_count == 0:
        lock_file.write(b"\0")
    else:
        lock_file.truncate(1)
    lock_file.flush()
    os.fsync(lock_file.fileno())


def _try_acquire_file_lock(lock_file) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_file_lock(lock_file) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_and_validate_ledger(
    connection: sqlite3.Connection,
    registry: tuple[Migration, ...],
) -> list[tuple[int, str, str]]:
    if not _migration_ledger_exists(connection):
        return []
    _validate_ledger_schema(connection)
    try:
        raw_rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.Error as exc:
        raise MigrationError("The schema_migrations ledger is malformed.") from exc

    try:
        rows = [(int(row[0]), str(row[1]), str(row[2])) for row in raw_rows]
    except (TypeError, ValueError) as exc:
        raise MigrationError("The schema_migrations ledger contains invalid values.") from exc
    versions = [row[0] for row in rows]
    if versions != list(range(1, len(rows) + 1)):
        raise MigrationError("The schema_migrations ledger is unknown or contains a gap.")
    if rows and rows[-1][0] > len(registry):
        raise MigrationError("The database was migrated by a newer application version.")
    for version, name, checksum in rows:
        expected = registry[version - 1]
        if name != expected.name:
            raise MigrationError(f"Migration {version} name does not match the application registry.")
        if checksum != expected.checksum:
            raise MigrationError(f"Migration {version} checksum does not match the application registry.")
    return rows


def _migration_ledger_exists(connection: sqlite3.Connection) -> bool:
    table_row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    return table_row is not None


def _validate_ledger_schema(connection: sqlite3.Connection) -> None:
    columns = connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
    shape = [
        (
            str(row[1]),
            str(row[2]).upper(),
            int(row[3]),
            int(row[5]),
        )
        for row in columns
    ]
    expected = [
        ("version", "INTEGER", 0, 1),
        ("name", "TEXT", 1, 0),
        ("checksum", "TEXT", 1, 0),
        ("applied_at", "TEXT", 1, 0),
    ]
    if shape != expected:
        raise MigrationError("The schema_migrations ledger schema is not authoritative.")
    has_unique_name = False
    for index_row in connection.execute("PRAGMA index_list(schema_migrations)").fetchall():
        if not int(index_row[2]):
            continue
        index_name = str(index_row[1])
        index_columns = [
            str(row[2])
            for row in connection.execute(f"PRAGMA index_info('{index_name}')").fetchall()
        ]
        if index_columns == ["name"]:
            has_unique_name = True
            break
    if not has_unique_name:
        raise MigrationError("The schema_migrations ledger name constraint is missing.")


def _has_application_schema(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
          AND name <> 'schema_migrations'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _migration_backup_dir(database_path: Path) -> Path:
    return database_path.parent / "migration-backups" / database_path.stem


def _validate_migration_backup_root(
    database_path: Path,
    backup_dir: Path,
    *,
    storage_evidence: SQLiteMigrationStorageEvidence,
    require_complete: bool,
) -> None:
    error = "Migration backup storage is not a safe same-device directory."
    try:
        database_stat = database_path.lstat()
        if (
            not stat.S_ISREG(database_stat.st_mode)
            or _is_reparse_stat(database_stat)
            or int(database_stat.st_dev) != storage_evidence.source_device
            or int(database_stat.st_ino) != storage_evidence.source_inode
        ):
            raise MigrationError(error)

        database_parent = Path(os.path.abspath(database_path.parent))
        current = Path(database_parent.anchor)
        anchor_stat = current.lstat()
        if (
            not stat.S_ISDIR(anchor_stat.st_mode)
            or stat.S_ISLNK(anchor_stat.st_mode)
            or _is_reparse_stat(anchor_stat)
        ):
            raise MigrationError(error)
        for component in database_parent.parts[1:]:
            current = current / component
            current_stat = current.lstat()
            if (
                not stat.S_ISDIR(current_stat.st_mode)
                or stat.S_ISLNK(current_stat.st_mode)
                or _is_reparse_stat(current_stat)
            ):
                raise MigrationError(error)

        expected_backup_dir = _migration_backup_dir(database_path)
        if Path(os.path.abspath(backup_dir)) != Path(
            os.path.abspath(expected_backup_dir)
        ):
            raise MigrationError(error)
        for candidate in (
            database_path.parent,
            database_path.parent / "migration-backups",
            backup_dir,
        ):
            try:
                candidate_stat = candidate.lstat()
            except FileNotFoundError:
                if require_complete or candidate == database_path.parent:
                    raise MigrationError(error) from None
                break
            if (
                not stat.S_ISDIR(candidate_stat.st_mode)
                or stat.S_ISLNK(candidate_stat.st_mode)
                or _is_reparse_stat(candidate_stat)
                or int(candidate_stat.st_dev) != storage_evidence.source_device
            ):
                raise MigrationError(error)
    except MigrationError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise MigrationError(error) from exc


def _validate_published_migration_snapshot(
    backup_path: Path,
    backup_evidence: SQLiteSnapshotEvidence,
    *,
    storage_evidence: SQLiteMigrationStorageEvidence,
) -> None:
    error = "Migration backup publication could not be verified safely."
    try:
        backup_stat = backup_path.lstat()
        if (
            not stat.S_ISREG(backup_stat.st_mode)
            or _is_reparse_stat(backup_stat)
            or int(backup_stat.st_dev) != storage_evidence.source_device
            or int(backup_stat.st_ino) == storage_evidence.source_inode
            or int(getattr(backup_stat, "st_nlink", 1)) != 1
            or isinstance(backup_evidence.byte_count, bool)
            or not isinstance(backup_evidence.byte_count, int)
            or backup_evidence.byte_count < 1
            or int(backup_stat.st_size) != backup_evidence.byte_count
            or Path(os.path.abspath(backup_evidence.final_path))
            != Path(os.path.abspath(backup_path))
            or backup_evidence.integrity_check != ("ok",)
            or backup_evidence.foreign_key_violations
        ):
            raise MigrationError(error)
    except MigrationError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise MigrationError(error) from exc


def _is_reparse_stat(value: os.stat_result) -> bool:
    return bool(int(getattr(value, "st_file_attributes", 0)) & 0x400)


def _is_storage_exhaustion(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.Error):
        error_code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(error_code, int) and error_code & 0xFF == sqlite3.SQLITE_FULL:
            return True
        message = str(exc).lower()
        return "database or disk is full" in message or "disk full" in message
    if isinstance(exc, OSError):
        return exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}
    return False


def _next_backup_path(database_path: Path, from_version: int, to_version: int) -> Path:
    backup_dir = _migration_backup_dir(database_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"pre-migration-v{from_version:04d}-to-v{to_version:04d}.sqlite3"
    candidate = backup_dir / base_name
    suffix = 1
    while candidate.exists():
        candidate = backup_dir / f"{Path(base_name).stem}.{suffix}.sqlite3"
        suffix += 1
    return candidate


def _apply_payload(context: MigrationContext, payload: MigrationPayload) -> None:
    for statement in _split_sql_statements(payload.schema_sql):
        context.execute(statement)
    for transform in payload.transforms:
        _apply_transform(context, transform)


def _apply_transform(context: MigrationContext, transform: TransformSpec) -> None:
    columns: set[str] = set()
    if transform.table is not None:
        columns = _columns(context, transform.table)
        if transform.skip_when_table_missing and not columns:
            return
        if transform.current_schema_tokens:
            create_sql = _table_create_sql(context, transform.table)
            if all(token in create_sql for token in transform.current_schema_tokens):
                return

    for addition in transform.additions:
        if addition.name in columns:
            continue
        context.execute(addition.sql)
        columns.add(addition.name)
        for statement in addition.after_add_statements:
            context.execute(statement)

    for statement in transform.statements:
        context.execute(statement)


def _split_sql_statements(sql_script: str) -> tuple[str, ...]:
    statements: list[str] = []
    buffer = ""
    for line in sql_script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        raise MigrationError("Schema contains an incomplete SQL statement.")
    return tuple(statements)


def _columns(context: MigrationContext, table: str) -> set[str]:
    return {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in context.connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _table_create_sql(context: MigrationContext, table: str) -> str:
    row = context.connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        return ""
    return str(row["sql"] if isinstance(row, sqlite3.Row) else row[0] or "")
