import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";

const DEFAULT_PORT = 39873;
const port = Number(process.env.CPW_SMOKE_PORT || DEFAULT_PORT);
const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const sourceCampaignsDir =
  process.env.CPW_CAMPAIGNS_DIR ||
  fileURLToPath(new URL("../../../tests/fixtures/sample_campaigns", import.meta.url));
const smokeTempDir = mkdtempSync(path.join(tmpdir(), "cpw-api-smoke-"));
const campaignsDir = path.join(smokeTempDir, "campaigns");
cpSync(sourceCampaignsDir, campaignsDir, { recursive: true });
const dbPath = path.join(smokeTempDir, "player_wiki.sqlite3");
const liveApiToken = "fixture-live-api-token";
const dmApiToken = "fixture-dm-api-token";
const playerApiToken = "fixture-player-api-token";
const outsiderApiToken = "fixture-outsider-api-token";
const hashToken = (rawToken) => createHash("sha256").update(rawToken, "utf8").digest("hex");

const smokeDb = new Database(dbPath);
smokeDb.exec(`
  CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    password_hash TEXT,
    auth_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE user_preferences (
    user_id INTEGER PRIMARY KEY,
    theme_key TEXT NOT NULL DEFAULT 'parchment',
    session_chat_order TEXT NOT NULL DEFAULT 'newest_first',
    frontend_mode TEXT NOT NULL DEFAULT 'gen2',
    updated_at TEXT NOT NULL
  );

  CREATE TABLE campaign_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    created_by_user_id INTEGER
  );

  CREATE TABLE campaign_visibility_settings (
    campaign_slug TEXT NOT NULL,
    scope TEXT NOT NULL,
    visibility TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, scope)
  );

  CREATE TABLE character_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    character_slug TEXT NOT NULL,
    assignment_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (campaign_slug, character_slug)
  );

  CREATE TABLE auth_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    target_user_id INTEGER,
    campaign_slug TEXT,
    character_slug TEXT,
    event_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE systems_import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL,
    import_version TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    summary_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    started_by_user_id INTEGER
  );

  CREATE TABLE character_state (
    campaign_slug TEXT NOT NULL,
    character_slug TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, character_slug)
  );
`);
smokeDb
  .prepare(
    "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    77,
    "fixture-token-user@example.com",
    "Fixture Token User",
    1,
    "active",
    null,
    3,
    "2026-06-25T08:00:00+00:00",
    "2026-06-25T08:30:00+00:00",
  );
smokeDb
  .prepare(
    "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    78,
    "fixture-view-target@example.com",
    "Fixture View Target",
    0,
    "active",
    null,
    1,
    "2026-06-25T08:05:00+00:00",
    "2026-06-25T08:05:00+00:00",
  );
smokeDb
  .prepare(
    "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    79,
    "fixture-token-player@example.com",
    "Fixture Token Player",
    0,
    "active",
    null,
    1,
    "2026-06-25T08:15:00+00:00",
    "2026-06-25T08:15:00+00:00",
  );
smokeDb
  .prepare(
    "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    80,
    "fixture-token-outsider@example.com",
    "Fixture Token Outsider",
    0,
    "active",
    null,
    1,
    "2026-06-25T08:20:00+00:00",
    "2026-06-25T08:20:00+00:00",
  );
smokeDb
  .prepare(
    "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    81,
    "fixture-token-dm@example.com",
    "Fixture Token DM",
    0,
    "active",
    null,
    1,
    "2026-06-25T08:25:00+00:00",
    "2026-06-25T08:25:00+00:00",
  );
smokeDb
  .prepare(
    "INSERT INTO user_preferences (user_id, theme_key, session_chat_order, frontend_mode, updated_at) VALUES (?, ?, ?, ?, ?)",
  )
  .run(77, "moonlit", "oldest_first", "flask", "2026-06-25T08:35:00+00:00");
smokeDb
  .prepare(
    "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(501, 77, "linden-pass", "dm", "active", "2026-06-25T08:10:00+00:00", "2026-06-25T08:10:00+00:00");
smokeDb
  .prepare(
    "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(502, 79, "linden-pass", "player", "active", "2026-06-25T08:16:00+00:00", "2026-06-25T08:16:00+00:00");
smokeDb
  .prepare(
    "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(503, 81, "linden-pass", "dm", "active", "2026-06-25T08:26:00+00:00", "2026-06-25T08:26:00+00:00");
smokeDb
  .prepare(
    "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    901,
    77,
    "Smoke Token",
    hashToken(liveApiToken),
    "2026-06-25T08:40:00+00:00",
    "2026-06-25T08:40:00+00:00",
    null,
    null,
    null,
  );
smokeDb
  .prepare(
    "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    902,
    79,
    "Player Smoke Token",
    hashToken(playerApiToken),
    "2026-06-25T08:45:00+00:00",
    "2026-06-25T08:45:00+00:00",
    null,
    null,
    null,
  );
smokeDb
  .prepare(
    "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    903,
    80,
    "Outsider Smoke Token",
    hashToken(outsiderApiToken),
    "2026-06-25T08:50:00+00:00",
    "2026-06-25T08:50:00+00:00",
    null,
    null,
    null,
  );
smokeDb
  .prepare(
    "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    904,
    81,
    "DM Smoke Token",
    hashToken(dmApiToken),
    "2026-06-25T08:55:00+00:00",
    "2026-06-25T08:55:00+00:00",
    null,
    null,
    null,
  );
const ardenInitialState = {
  vitals: {
    current_hp: 38,
    temp_hp: 0,
    death_saves: {
      successes: 0,
      failures: 0,
    },
  },
  resources: [],
  hit_dice: {
    pools: [{ die_size: 8, total: 3, current: 2 }],
  },
  inventory: [],
  currency: {},
  spell_slots: [],
  attunement: {},
  notes: {},
};
smokeDb
  .prepare(
    "INSERT INTO character_state (campaign_slug, character_slug, revision, state_json, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?)",
  )
  .run(
    "linden-pass",
    "arden-march",
    8,
    JSON.stringify(ardenInitialState),
    "2026-06-25T09:05:00+00:00",
    77,
  );
smokeDb
  .prepare(
    "INSERT INTO character_assignments (user_id, campaign_slug, character_slug, assignment_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
  )
  .run(
    79,
    "linden-pass",
    "arden-march",
    "owner",
    "2026-06-25T09:06:00+00:00",
    "2026-06-25T09:06:00+00:00",
  );
const insertImportRun = smokeDb.prepare(`
  INSERT INTO systems_import_runs (
    library_slug,
    source_id,
    status,
    import_version,
    source_path,
    summary_json,
    started_at,
    completed_at,
    started_by_user_id
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
insertImportRun.run(
  "DND-5E",
  "MM",
  "completed",
  "mm-import",
  "api-upload:mm-import.zip",
  JSON.stringify({ entry_types: ["monster"], imported_count: 1, source_files: ["data/bestiary/bestiary-mm.json"] }),
  "2026-06-25T10:00:00+00:00",
  "2026-06-25T10:01:00+00:00",
  42,
);
insertImportRun.run(
  "DND-5E",
  "PHB",
  "started",
  "phb-import",
  "api-upload:phb-import.zip",
  JSON.stringify({ entry_types: ["spell"], imported_count: 0 }),
  "2026-06-25T09:00:00+00:00",
  null,
  null,
);
smokeDb.exec(`
  CREATE TABLE systems_libraries (
    library_slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    system_code TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE systems_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    license_class TEXT NOT NULL,
    license_url TEXT NOT NULL DEFAULT '',
    attribution_text TEXT NOT NULL DEFAULT '',
    public_visibility_allowed INTEGER NOT NULL DEFAULT 0,
    requires_unofficial_notice INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (library_slug, source_id)
  );

  CREATE TABLE campaign_enabled_sources (
    campaign_slug TEXT NOT NULL,
    library_slug TEXT NOT NULL,
    source_id TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 0,
    default_visibility TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, source_id)
  );

  CREATE TABLE systems_entries (
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

  CREATE TABLE campaign_entry_overrides (
    campaign_slug TEXT NOT NULL,
    library_slug TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    visibility_override TEXT,
    is_enabled_override INTEGER,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, entry_key)
  );

  CREATE TABLE campaign_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    started_by_user_id INTEGER,
    ended_at TEXT,
    ended_by_user_id INTEGER
  );

  CREATE TABLE campaign_session_states (
    campaign_slug TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER
  );

  CREATE TABLE campaign_session_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    source_page_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    revealed_at TEXT,
    revealed_by_user_id INTEGER,
    revealed_in_session_id INTEGER
  );

  CREATE TABLE campaign_session_article_images (
    article_id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    alt_text TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    data_blob BLOB NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE campaign_session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    message_type TEXT NOT NULL,
    body_text TEXT NOT NULL,
    recipient_scope TEXT NOT NULL DEFAULT 'global',
    recipient_user_id INTEGER,
    author_user_id INTEGER,
    author_display_name TEXT NOT NULL,
    article_id INTEGER,
    created_at TEXT NOT NULL
  );

  CREATE TABLE campaign_dm_statblocks (
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
    updated_by_user_id INTEGER
  );

  CREATE TABLE campaign_dm_condition_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description_markdown TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    updated_by_user_id INTEGER
  );

  CREATE TABLE campaign_combatants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_slug TEXT NOT NULL,
    combatant_type TEXT NOT NULL,
    character_slug TEXT,
    player_detail_visible INTEGER NOT NULL DEFAULT 0,
    source_kind TEXT NOT NULL DEFAULT 'manual_npc',
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
    updated_by_user_id INTEGER
  );

  CREATE TABLE campaign_combat_trackers (
    campaign_slug TEXT PRIMARY KEY,
    round_number INTEGER NOT NULL DEFAULT 1,
    current_combatant_id INTEGER,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER
  );

  CREATE TABLE campaign_combat_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combatant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    duration_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER
  );

  CREATE TABLE campaign_combatant_resource_counters (
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
    updated_by_user_id INTEGER
  );

  CREATE TABLE campaign_combatant_resource_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combatant_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    note TEXT NOT NULL,
    source_label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER
  );
`);
smokeDb
  .prepare(
    "INSERT INTO systems_libraries (library_slug, title, system_code, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
  )
  .run("DND-5E", "DND 5E", "DND-5E", "active", "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
const insertSource = smokeDb.prepare(`
  INSERT INTO systems_sources (
    library_slug,
    source_id,
    title,
    license_class,
    public_visibility_allowed,
    requires_unofficial_notice,
    status,
    created_at,
    updated_at
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
insertSource.run("DND-5E", "PHB", "Player's Handbook", "proprietary_private", 0, 1, "active", "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
insertSource.run("DND-5E", "MM", "Monster Manual", "proprietary_private", 0, 1, "active", "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
insertSource.run("DND-5E", "XGE", "Xanathar's Guide to Everything", "proprietary_private", 0, 1, "active", "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
smokeDb
  .prepare(
    "INSERT INTO campaign_enabled_sources (campaign_slug, library_slug, source_id, is_enabled, default_visibility, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run("linden-pass", "DND-5E", "XGE", 0, "players", "2026-06-25T09:30:00+00:00", 42);
const insertEntry = smokeDb.prepare(`
  INSERT INTO systems_entries (
    library_slug,
    source_id,
    entry_key,
    entry_type,
    slug,
    title,
    player_safe_default,
    created_at,
    updated_at
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
insertEntry.run("DND-5E", "PHB", "PHB:spell:mage-hand", "spell", "phb-spell-mage-hand", "Mage Hand", 1, "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
insertEntry.run("DND-5E", "PHB", "PHB:item:chain-mail", "item", "phb-item-chain-mail", "Chain Mail", 1, "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
insertEntry.run("DND-5E", "MM", "MM:monster:goblin", "monster", "mm-monster-goblin", "Goblin", 0, "2026-06-25T09:00:00+00:00", "2026-06-25T09:00:00+00:00");
smokeDb
  .prepare(
    `
      UPDATE systems_entries
      SET
        source_page = ?,
        source_path = ?,
        metadata_json = ?,
        body_json = ?,
        rendered_html = ?
      WHERE library_slug = ?
        AND entry_key = ?
    `,
  )
  .run(
    "145",
    "items/chain-mail",
    JSON.stringify({ armor: { ac: 16 }, reference_terms: ["armor"] }),
    JSON.stringify({ entries: ["A sample armor entry."] }),
    "<p>A sample armor entry.</p>",
    "DND-5E",
    "PHB:item:chain-mail",
  );
smokeDb
  .prepare(
    `
      UPDATE systems_entries
      SET
        metadata_json = ?,
        body_json = ?
      WHERE library_slug = ?
        AND entry_key = ?
    `,
  )
  .run(
    JSON.stringify({ abilities: { dex: 14 }, hp: { average: 7 }, speed: { walk: 30 } }),
    JSON.stringify({
      traits: [{ name: "Battle Cry", entries: ["Battle Cry (1/day)."] }],
      actions: [
        { name: "At-Will Tricks", entries: ["At will: minor illusion, dancing lights."] },
        { name: "Snare Net", entries: ["Snare Net (Recharge 5-6)."] },
      ],
    }),
    "DND-5E",
    "MM:monster:goblin",
  );
smokeDb
  .prepare(
    "INSERT INTO campaign_entry_overrides (campaign_slug, library_slug, entry_key, visibility_override, is_enabled_override, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run("linden-pass", "DND-5E", "PHB:item:chain-mail", "players", null, "2026-06-25T09:35:00+00:00", 42);
smokeDb
  .prepare(
    "INSERT INTO campaign_session_states (campaign_slug, revision, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?)",
  )
  .run("linden-pass", 7, "2026-06-25T11:00:00+00:00", 42);
smokeDb
  .prepare(
    "INSERT INTO campaign_sessions (id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(1, "linden-pass", "active", "2026-06-25T10:00:00+00:00", 42, null, null);
smokeDb
  .prepare(
    "INSERT INTO campaign_sessions (id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(2, "linden-pass", "closed", "2026-06-24T10:00:00+00:00", 42, "2026-06-24T12:00:00+00:00", 42);
const insertSessionArticle = smokeDb.prepare(`
  INSERT INTO campaign_session_articles (
    id,
    campaign_slug,
    title,
    body_markdown,
    source_page_ref,
    status,
    created_at,
    created_by_user_id,
    revealed_at,
    revealed_by_user_id,
    revealed_in_session_id
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
insertSessionArticle.run(
  101,
  "linden-pass",
  "Harbor Clue",
  "A staged clue for the table.",
  "npcs/captain-lyra-vale",
  "staged",
  "2026-06-25T10:05:00+00:00",
  42,
  null,
  null,
  null,
);
insertSessionArticle.run(
  102,
  "linden-pass",
  "Revealed Systems Note",
  "<p>A revealed Systems note.</p>",
  "systems:phb-item-chain-mail",
  "revealed",
  "2026-06-25T10:10:00+00:00",
  42,
  "2026-06-25T10:20:00+00:00",
  42,
  1,
);
smokeDb
  .prepare(
    "INSERT INTO campaign_session_article_images (article_id, filename, media_type, alt_text, caption, data_blob, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    101,
    "staged-note.gif",
    "image/gif",
    "Staged note image",
    "A manager-only staged fixture image.",
    Buffer.from("staged-image"),
    "2026-06-25T10:06:00+00:00",
  );
smokeDb
  .prepare(
    "INSERT INTO campaign_session_article_images (article_id, filename, media_type, alt_text, caption, data_blob, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
  )
  .run(
    102,
    "revealed-note.png",
    "image/png",
    "Revealed note image",
    "A fixture session image.",
    Buffer.from("fixture-image"),
    "2026-06-25T10:21:00+00:00",
  );
const insertSessionMessage = smokeDb.prepare(`
  INSERT INTO campaign_session_messages (
    id,
    session_id,
    campaign_slug,
    message_type,
    body_text,
    recipient_scope,
    recipient_user_id,
    author_user_id,
    author_display_name,
    article_id,
    created_at
  )
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
insertSessionMessage.run(
  201,
  1,
  "linden-pass",
  "chat",
  "The session begins.",
  "global",
  null,
  42,
  "Dungeon Master",
  null,
  "2026-06-25T10:15:00+00:00",
);
insertSessionMessage.run(
  202,
  1,
  "linden-pass",
  "system",
  "DM-only note.",
  "dm_only",
  null,
  42,
  "Dungeon Master",
  null,
  "2026-06-25T10:16:00+00:00",
);
insertSessionMessage.run(
  203,
  1,
  "linden-pass",
  "article_reveal",
  "Revealed Systems Note",
  "global",
  null,
  42,
  "Dungeon Master",
  102,
  "2026-06-25T10:20:00+00:00",
);
insertSessionMessage.run(
  204,
  2,
  "linden-pass",
  "chat",
  "A closed-session DM-only message.",
  "dm_only",
  null,
  42,
  "Dungeon Master",
  null,
  "2026-06-24T10:30:00+00:00",
);
smokeDb
  .prepare(
    `
      INSERT INTO campaign_dm_statblocks (
        id,
        campaign_slug,
        title,
        body_markdown,
        source_filename,
        subsection,
        armor_class,
        max_hp,
        speed_text,
        movement_total,
        initiative_bonus,
        created_at,
        updated_at,
        created_by_user_id,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(
    301,
    "linden-pass",
    "Dock Tough",
    "## Dock Tough\nArmor Class: 12\nHit Points: 16\nSpeed: 30 ft.\nDEX 14 (+2)\nArcane Jolt (2/day)\nAt will: light, mage hand\nRust Breath (Recharge 5-6)",
    "dock-tough.md",
    "Dock Crew",
    12,
    16,
    "30 ft.",
    30,
    2,
    "2026-06-25T10:40:00+00:00",
    "2026-06-25T10:45:00+00:00",
    77,
    77,
  );
smokeDb
  .prepare(
    `
      INSERT INTO campaign_dm_condition_definitions (
        id,
        campaign_slug,
        name,
        description_markdown,
        created_at,
        updated_at,
        created_by_user_id,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(
    401,
    "linden-pass",
    "Salt-Burned",
    "A custom fixture condition.",
    "2026-06-25T10:42:00+00:00",
    "2026-06-25T10:46:00+00:00",
    77,
    77,
  );
smokeDb
  .prepare(
    `
      INSERT INTO campaign_combatants (
        id,
        campaign_slug,
        combatant_type,
        character_slug,
        player_detail_visible,
        source_kind,
        source_ref,
        display_name,
        turn_value,
        initiative_bonus,
        dexterity_modifier,
        initiative_priority,
        current_hp,
        max_hp,
        temp_hp,
        movement_total,
        movement_remaining,
        has_action,
        has_bonus_action,
        has_reaction,
        revision,
        created_at,
        updated_at,
        created_by_user_id,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(
    501,
    "linden-pass",
    "npc",
    null,
    1,
    "manual_npc",
    "",
    "Clockwork Hound",
    18,
    4,
    2,
    1,
    22,
    28,
    3,
    40,
    25,
    1,
    0,
    1,
    6,
    "2026-06-25T10:50:00+00:00",
    "2026-06-25T10:55:00+00:00",
    77,
    77,
  );
smokeDb
  .prepare(
    `
      INSERT INTO campaign_combatants (
        id,
        campaign_slug,
        combatant_type,
        character_slug,
        player_detail_visible,
        source_kind,
        source_ref,
        display_name,
        turn_value,
        initiative_bonus,
        dexterity_modifier,
        initiative_priority,
        current_hp,
        max_hp,
        temp_hp,
        movement_total,
        movement_remaining,
        has_action,
        has_bonus_action,
        has_reaction,
        revision,
        created_at,
        updated_at,
        created_by_user_id,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(
    502,
    "linden-pass",
    "player_character",
    "arden-march",
    0,
    "character",
    "arden-march",
    "Arden March",
    15,
    2,
    2,
    2,
    38,
    38,
    0,
    30,
    30,
    1,
    1,
    1,
    4,
    "2026-06-25T10:51:00+00:00",
    "2026-06-25T10:56:00+00:00",
    77,
    77,
  );
smokeDb
  .prepare(
    `
      INSERT INTO campaign_combat_trackers (
        campaign_slug,
        round_number,
        current_combatant_id,
        revision,
        updated_at,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?)
    `,
  )
  .run("linden-pass", 3, 501, 12, "2026-06-25T10:57:00+00:00", 77);
smokeDb
  .prepare(
    `
      INSERT INTO campaign_combat_conditions (
        id,
        combatant_id,
        name,
        duration_text,
        created_at,
        created_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?)
    `,
  )
  .run(601, 501, "Restrained", "One minute", "2026-06-25T10:58:00+00:00", 77);
smokeDb
  .prepare(
    `
      INSERT INTO campaign_combatant_resource_counters (
        id,
        combatant_id,
        resource_key,
        label,
        current_value,
        max_value,
        reset_label,
        source_label,
        created_at,
        updated_at,
        created_by_user_id,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(
    701,
    501,
    "overdrive",
    "Overdrive",
    1,
    2,
    "Short rest",
    "Manual NPC",
    "2026-06-25T10:59:00+00:00",
    "2026-06-25T10:59:00+00:00",
    77,
    77,
  );
smokeDb
  .prepare(
    `
      INSERT INTO campaign_combatant_resource_notes (
        id,
        combatant_id,
        label,
        note,
        source_label,
        created_at,
        created_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(801, 501, "Tactics", "Tries to pin the nearest runner.", "Manual NPC", "2026-06-25T11:00:00+00:00", 77);
smokeDb.close();

const nodePath = fileURLToPath(new URL("../dist/server.js", import.meta.url));
const child = spawn(process.execPath, [nodePath], {
  env: {
    ...process.env,
    PORT: String(port),
    NODE_ENV: "test",
    CPW_CAMPAIGNS_DIR: campaignsDir,
    CPW_DB_PATH: dbPath,
  },
  stdio: ["ignore", "pipe", "pipe"],
});

const ensureStopped = () => {
  if (!child.killed) {
    child.kill("SIGINT");
  }
  rmSync(smokeTempDir, { recursive: true, force: true });
};

process.on("exit", ensureStopped);
process.on("SIGINT", ensureStopped);
process.on("SIGTERM", ensureStopped);

let output = "";
const logLine = (chunk) => {
  output += chunk.toString();
};
child.stdout.on("data", logLine);
child.stderr.on("data", logLine);

const requestJson = async (path, headers = {}, options = {}) => {
  const requestHeaders = { ...headers };
  let body;
  if (Object.hasOwn(options, "body")) {
    body = typeof options.body === "string" ? options.body : JSON.stringify(options.body);
    if (!Object.keys(requestHeaders).some((key) => key.toLowerCase() === "content-type")) {
      requestHeaders["Content-Type"] = "application/json";
    }
  }
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: options.method || "GET",
    headers: requestHeaders,
    body,
  });
  const payload = await response.json();
  return { status: response.status, payload };
};

const requestBytes = async (path, headers = {}) => {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    headers,
  });
  const body = new Uint8Array(await response.arrayBuffer());
  return { status: response.status, headers: response.headers, body };
};

const readApiTokenLastUsedAt = (tokenId) => {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    return database.prepare("SELECT last_used_at FROM api_tokens WHERE id = ?").get(tokenId)?.last_used_at || "";
  } finally {
    database.close();
  }
};

const waitForReady = async () => {
  const timeout = Number(process.env.CPW_SMOKE_TIMEOUT_MS || 5000);
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const response = await requestJson("/healthz");
      if (response.status === 200 && response.payload?.status === "ok") {
        return;
      }
    } catch {
      // server not yet ready
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out waiting for API readiness. Output: ${output}`);
};

await waitForReady();

const health = await requestJson("/healthz");
if (health.status !== 200 || health.payload?.status !== "ok") {
  throw new Error(`Expected /healthz ok, got ${health.status}`);
}
if (health.payload?.runtime_mode !== "fixture") {
  throw new Error(`Expected fixture runtime, got ${health.payload?.runtime_mode}`);
}
if (health.payload?.campaign_count < 1) {
  throw new Error(`Expected at least one campaign fixture under ${repoRoot}.`);
}

const appState = await requestJson("/api/v1/app");
if (appState.status !== 200 || appState.payload?.ok !== true) {
  throw new Error(`Expected app state endpoint 200 ok, got ${appState.status}`);
}
for (const key of ["version", "build_id", "git_sha", "runtime", "instance_name", "environment", "base_url", "db_path", "campaigns_dir"]) {
  if (typeof appState.payload?.app?.[key] !== "string" || !appState.payload.app[key]) {
    throw new Error(`Expected app state string field ${key}, got ${appState.payload?.app?.[key]}`);
  }
}
if (typeof appState.payload?.app?.git_dirty !== "boolean") {
  throw new Error(`Expected app state git_dirty boolean, got ${appState.payload?.app?.git_dirty}`);
}
if (appState.payload.app.campaigns_dir !== campaignsDir) {
  throw new Error(`Expected app state campaigns_dir ${campaignsDir}, got ${appState.payload.app.campaigns_dir}`);
}
if (appState.payload.app.db_path !== dbPath) {
  throw new Error(`Expected app state db_path ${dbPath}, got ${appState.payload.app.db_path}`);
}

const blockedMe = await requestJson("/api/v1/me");
if (blockedMe.status !== 401 || blockedMe.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated me request to return auth_required 401, got ${blockedMe.status} ${blockedMe.payload?.error?.code}`,
  );
}

const invalidBearerMe = await requestJson("/api/v1/me", {
  Authorization: "Bearer definitely-invalid",
});
if (invalidBearerMe.status !== 401 || invalidBearerMe.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected invalid bearer me request to return auth_required 401, got ${invalidBearerMe.status} ${invalidBearerMe.payload?.error?.code}`,
  );
}

const liveTokenLastUsedBeforeMe = readApiTokenLastUsedAt(901);
const bearerMe = await requestJson("/api/v1/me", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerMe.status !== 200 ||
  bearerMe.payload?.ok !== true ||
  bearerMe.payload?.auth_source !== "api_token" ||
  bearerMe.payload?.user?.email !== "fixture-token-user@example.com" ||
  bearerMe.payload?.user?.is_admin !== true ||
  bearerMe.payload?.memberships?.[0]?.campaign_slug !== "linden-pass" ||
  bearerMe.payload?.memberships?.[0]?.role !== "dm" ||
  bearerMe.payload?.preferences?.theme_key !== "moonlit" ||
  bearerMe.payload?.preferences?.session_chat_order !== "oldest_first" ||
  bearerMe.payload?.preferences?.frontend_mode !== "gen2" ||
  bearerMe.payload?.view_as?.can_view_as !== true ||
  bearerMe.payload?.view_as?.active_user !== null ||
  !bearerMe.payload?.view_as?.user_choices
    ?.map((user) => user.email)
    .includes("fixture-view-target@example.com")
) {
  throw new Error(`Unexpected bearer me payload: ${JSON.stringify(bearerMe.payload)}`);
}
const liveTokenLastUsedAfterMe = readApiTokenLastUsedAt(901);
if (
  liveTokenLastUsedAfterMe === liveTokenLastUsedBeforeMe ||
  Date.parse(liveTokenLastUsedAfterMe) <= Date.parse(liveTokenLastUsedBeforeMe)
) {
  throw new Error(
    `Expected bearer /me to touch api_tokens.last_used_at, before=${liveTokenLastUsedBeforeMe}, after=${liveTokenLastUsedAfterMe}`,
  );
}

const playerMe = await requestJson("/api/v1/me", {
  "X-CPW-Fixture-Role": "player",
});
if (
  playerMe.status !== 200 ||
  playerMe.payload?.ok !== true ||
  playerMe.payload?.auth_source !== "fixture" ||
  playerMe.payload?.user?.email !== "fixture-player@example.com" ||
  playerMe.payload?.user?.is_admin !== false ||
  playerMe.payload?.memberships?.[0]?.campaign_slug !== "linden-pass" ||
  playerMe.payload?.memberships?.[0]?.role !== "player" ||
  playerMe.payload?.preferences?.theme_key !== "parchment" ||
  playerMe.payload?.preferences?.session_chat_order !== "newest_first" ||
  playerMe.payload?.preferences?.frontend_mode !== "gen2" ||
  playerMe.payload?.view_as?.can_view_as !== false
) {
  throw new Error(`Unexpected fixture player me payload: ${JSON.stringify(playerMe.payload)}`);
}

const adminMe = await requestJson("/api/v1/me", {
  "X-CPW-Fixture-Role": "admin",
});
if (
  adminMe.status !== 200 ||
  adminMe.payload?.user?.is_admin !== true ||
  adminMe.payload?.memberships?.[0]?.role !== "dm" ||
  adminMe.payload?.view_as?.can_view_as !== true ||
  adminMe.payload?.view_as?.active_user !== null ||
  adminMe.payload?.view_as?.user_choices?.length !== 2 ||
  adminMe.payload?.view_as?.user_choices?.some((user) => user.id === adminMe.payload?.user?.id)
) {
  throw new Error(`Unexpected fixture admin me payload: ${JSON.stringify(adminMe.payload)}`);
}

const blockedMeSettings = await requestJson("/api/v1/me/settings");
if (blockedMeSettings.status !== 401 || blockedMeSettings.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated me settings request to return auth_required 401, got ${blockedMeSettings.status} ${blockedMeSettings.payload?.error?.code}`,
  );
}

const playerMeSettings = await requestJson("/api/v1/me/settings", {
  "X-CPW-Fixture-Role": "player",
});
if (
  playerMeSettings.status !== 200 ||
  playerMeSettings.payload?.ok !== true ||
  playerMeSettings.payload?.user?.email !== "fixture-player@example.com" ||
  playerMeSettings.payload?.preferences?.theme_key !== "parchment" ||
  playerMeSettings.payload?.preferences?.session_chat_order !== "newest_first" ||
  playerMeSettings.payload?.preferences?.frontend_mode !== "gen2" ||
  playerMeSettings.payload?.theme_presets?.length !== 4 ||
  playerMeSettings.payload?.theme_presets?.[0]?.key !== "parchment" ||
  playerMeSettings.payload?.session_chat_order_choices?.length !== 2 ||
  playerMeSettings.payload?.session_chat_order_choices?.[1]?.value !== "oldest_first" ||
  "frontend_mode_choices" in (playerMeSettings.payload || {})
) {
  throw new Error(`Unexpected fixture player settings payload: ${JSON.stringify(playerMeSettings.payload)}`);
}

const bearerMeSettings = await requestJson("/api/v1/me/settings", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerMeSettings.status !== 200 ||
  bearerMeSettings.payload?.ok !== true ||
  bearerMeSettings.payload?.user?.email !== "fixture-token-user@example.com" ||
  bearerMeSettings.payload?.preferences?.theme_key !== "moonlit" ||
  bearerMeSettings.payload?.preferences?.session_chat_order !== "oldest_first" ||
  bearerMeSettings.payload?.preferences?.frontend_mode !== "gen2" ||
  bearerMeSettings.payload?.theme_presets?.length !== 4 ||
  bearerMeSettings.payload?.session_chat_order_choices?.length !== 2 ||
  "frontend_mode_choices" in (bearerMeSettings.payload || {})
) {
  throw new Error(`Unexpected bearer settings payload: ${JSON.stringify(bearerMeSettings.payload)}`);
}

const blockedMeSettingsPatch = await requestJson(
  "/api/v1/me/settings",
  {},
  { method: "PATCH", body: { theme_key: "moonlit" } },
);
if (blockedMeSettingsPatch.status !== 401 || blockedMeSettingsPatch.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated settings PATCH to return auth_required 401, got ${blockedMeSettingsPatch.status} ${blockedMeSettingsPatch.payload?.error?.code}`,
  );
}
const fixtureMeSettingsPatch = await requestJson(
  "/api/v1/me/settings",
  { "X-CPW-Fixture-Role": "player" },
  { method: "PATCH", body: { theme_key: "moonlit" } },
);
if (
  fixtureMeSettingsPatch.status !== 403 ||
  fixtureMeSettingsPatch.payload?.error?.message !== "Account settings updates require bearer API authentication."
) {
  throw new Error(
    `Expected fixture settings PATCH to require bearer auth, got ${fixtureMeSettingsPatch.status} ${fixtureMeSettingsPatch.payload?.error?.message}`,
  );
}
const invalidThemeSettingsPatch = await requestJson(
  "/api/v1/me/settings",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: { theme_key: "bad-theme", session_chat_order: "oldest_first" } },
);
if (
  invalidThemeSettingsPatch.status !== 400 ||
  invalidThemeSettingsPatch.payload?.error?.message !== "Choose a valid theme preset."
) {
  throw new Error(
    `Expected invalid theme settings PATCH validation, got ${invalidThemeSettingsPatch.status} ${invalidThemeSettingsPatch.payload?.error?.message}`,
  );
}
const invalidOrderSettingsPatch = await requestJson(
  "/api/v1/me/settings",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: { theme_key: "moonlit", session_chat_order: "sideways" } },
);
if (
  invalidOrderSettingsPatch.status !== 400 ||
  invalidOrderSettingsPatch.payload?.error?.message !== "Choose a valid live session chat order."
) {
  throw new Error(
    `Expected invalid chat-order settings PATCH validation, got ${invalidOrderSettingsPatch.status} ${invalidOrderSettingsPatch.payload?.error?.message}`,
  );
}
const retiredFrontendSettingsPatch = await requestJson(
  "/api/v1/me/settings",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: { frontend_mode: "gen2" } },
);
if (
  retiredFrontendSettingsPatch.status !== 400 ||
  retiredFrontendSettingsPatch.payload?.error?.message !== "Preferred frontend selection is no longer available."
) {
  throw new Error(
    `Expected retired frontend settings PATCH validation, got ${retiredFrontendSettingsPatch.status} ${retiredFrontendSettingsPatch.payload?.error?.message}`,
  );
}
const emptySettingsPatch = await requestJson(
  "/api/v1/me/settings",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: {} },
);
if (emptySettingsPatch.status !== 400 || emptySettingsPatch.payload?.error?.message !== "No account settings were provided.") {
  throw new Error(
    `Expected empty settings PATCH validation, got ${emptySettingsPatch.status} ${emptySettingsPatch.payload?.error?.message}`,
  );
}
const updatedSettingsPatch = await requestJson(
  "/api/v1/me/settings",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: { theme_key: "moonlit", session_chat_order: "oldest_first" } },
);
if (
  updatedSettingsPatch.status !== 200 ||
  updatedSettingsPatch.payload?.ok !== true ||
  updatedSettingsPatch.payload?.user?.email !== "fixture-token-player@example.com" ||
  updatedSettingsPatch.payload?.preferences?.theme_key !== "moonlit" ||
  updatedSettingsPatch.payload?.preferences?.session_chat_order !== "oldest_first" ||
  updatedSettingsPatch.payload?.preferences?.frontend_mode !== "gen2" ||
  "theme_presets" in (updatedSettingsPatch.payload || {})
) {
  throw new Error(`Unexpected account settings PATCH payload: ${JSON.stringify(updatedSettingsPatch.payload)}`);
}
const playerMeAfterSettingsPatch = await requestJson("/api/v1/me", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (
  playerMeAfterSettingsPatch.status !== 200 ||
  playerMeAfterSettingsPatch.payload?.preferences?.theme_key !== "moonlit" ||
  playerMeAfterSettingsPatch.payload?.preferences?.session_chat_order !== "oldest_first" ||
  playerMeAfterSettingsPatch.payload?.preferences?.frontend_mode !== "gen2"
) {
  throw new Error(`Expected /me to reflect settings PATCH, got ${JSON.stringify(playerMeAfterSettingsPatch.payload)}`);
}
const accountSettingsAssertionDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const playerPreferenceRow = accountSettingsAssertionDb
  .prepare("SELECT theme_key, session_chat_order, frontend_mode FROM user_preferences WHERE user_id = ?")
  .get(79);
accountSettingsAssertionDb.close();
if (
  playerPreferenceRow?.theme_key !== "moonlit" ||
  playerPreferenceRow?.session_chat_order !== "oldest_first" ||
  playerPreferenceRow?.frontend_mode !== "gen2"
) {
  throw new Error(`Expected persisted player preferences, got ${JSON.stringify(playerPreferenceRow)}`);
}

const blockedImportRuns = await requestJson("/api/v1/systems/import-runs");
if (blockedImportRuns.status !== 401 || blockedImportRuns.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems import runs request to return auth_required 401, got ${blockedImportRuns.status} ${blockedImportRuns.payload?.error?.code}`,
  );
}

const playerBearerImportRuns = await requestJson("/api/v1/systems/import-runs", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (playerBearerImportRuns.status !== 403 || playerBearerImportRuns.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player bearer systems import runs request to return forbidden 403, got ${playerBearerImportRuns.status} ${playerBearerImportRuns.payload?.error?.code}`,
  );
}

const bearerImportRuns = await requestJson("/api/v1/systems/import-runs?source_id=MM", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerImportRuns.status !== 200 ||
  bearerImportRuns.payload?.ok !== true ||
  bearerImportRuns.payload?.import_runs?.length !== 1 ||
  bearerImportRuns.payload?.import_runs?.[0]?.source_id !== "MM"
) {
  throw new Error(`Unexpected bearer systems import runs payload: ${JSON.stringify(bearerImportRuns.payload)}`);
}

const importRuns = await requestJson("/api/v1/systems/import-runs?source_id=MM", {
  "X-CPW-Fixture-Role": "admin",
});
if (importRuns.status !== 200 || importRuns.payload?.ok !== true) {
  throw new Error(`Expected systems import runs endpoint 200 ok, got ${importRuns.status}`);
}
if (!Array.isArray(importRuns.payload?.import_runs) || importRuns.payload.import_runs.length !== 1) {
  throw new Error(`Expected one MM import run, got ${JSON.stringify(importRuns.payload?.import_runs)}`);
}
const mmImportRun = importRuns.payload.import_runs[0];
if (mmImportRun.source_id !== "MM" || mmImportRun.import_version !== "mm-import" || mmImportRun.status !== "completed") {
  throw new Error(`Unexpected MM import run payload: ${JSON.stringify(mmImportRun)}`);
}
if (mmImportRun.summary?.imported_count !== 1 || mmImportRun.summary?.entry_types?.[0] !== "monster") {
  throw new Error(`Unexpected MM import run summary: ${JSON.stringify(mmImportRun.summary)}`);
}
if (mmImportRun.completed_at !== "2026-06-25T10:01:00+00:00" || mmImportRun.started_by_user_id !== 42) {
  throw new Error(`Unexpected MM import run completion metadata: ${JSON.stringify(mmImportRun)}`);
}

const blockedImportRunDetail = await requestJson(`/api/v1/systems/import-runs/${mmImportRun.id}`);
if (blockedImportRunDetail.status !== 401 || blockedImportRunDetail.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems import run detail to return auth_required 401, got ${blockedImportRunDetail.status} ${blockedImportRunDetail.payload?.error?.code}`,
  );
}

const importRunDetail = await requestJson(`/api/v1/systems/import-runs/${mmImportRun.id}`, {
  "X-CPW-Fixture-Role": "admin",
});
if (importRunDetail.status !== 200 || importRunDetail.payload?.ok !== true) {
  throw new Error(`Expected systems import run detail 200 ok, got ${importRunDetail.status}`);
}
if (importRunDetail.payload?.import_run?.id !== mmImportRun.id) {
  throw new Error(`Expected systems import run detail id ${mmImportRun.id}, got ${importRunDetail.payload?.import_run?.id}`);
}
if (importRunDetail.payload?.import_run?.summary?.source_files?.[0] !== "data/bestiary/bestiary-mm.json") {
  throw new Error(`Unexpected systems import run detail summary: ${JSON.stringify(importRunDetail.payload?.import_run)}`);
}

const bearerImportRunDetail = await requestJson(`/api/v1/systems/import-runs/${mmImportRun.id}`, {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerImportRunDetail.status !== 200 ||
  bearerImportRunDetail.payload?.ok !== true ||
  bearerImportRunDetail.payload?.import_run?.id !== mmImportRun.id
) {
  throw new Error(`Unexpected bearer systems import run detail payload: ${JSON.stringify(bearerImportRunDetail.payload)}`);
}

const missingImportRunDetail = await requestJson("/api/v1/systems/import-runs/999999", {
  "X-CPW-Fixture-Role": "admin",
});
if (missingImportRunDetail.status !== 404 || missingImportRunDetail.payload?.error?.code !== "systems_import_run_not_found") {
  throw new Error(
    `Expected missing systems import run detail JSON 404, got ${missingImportRunDetail.status} ${missingImportRunDetail.payload?.error?.code}`,
  );
}

const blockedSystemsIndex = await requestJson("/api/v1/campaigns/linden-pass/systems");
if (blockedSystemsIndex.status !== 401 || blockedSystemsIndex.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems index to return auth_required 401, got ${blockedSystemsIndex.status} ${blockedSystemsIndex.payload?.error?.code}`,
  );
}

const outsiderSystemsIndex = await requestJson("/api/v1/campaigns/linden-pass/systems", {
  Authorization: `Bearer ${outsiderApiToken}`,
});
if (outsiderSystemsIndex.status !== 403 || outsiderSystemsIndex.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected bearer systems index without membership to return forbidden 403, got ${outsiderSystemsIndex.status} ${outsiderSystemsIndex.payload?.error?.code}`,
  );
}

const playerSystemsIndex = await requestJson("/api/v1/campaigns/linden-pass/systems", {
  "X-CPW-Fixture-Role": "player",
});
if (playerSystemsIndex.status !== 200 || playerSystemsIndex.payload?.ok !== true) {
  throw new Error(`Expected player systems index 200 ok, got ${playerSystemsIndex.status}`);
}
if (playerSystemsIndex.payload?.library?.library_slug !== "DND-5E") {
  throw new Error(`Expected systems index DND-5E library, got ${JSON.stringify(playerSystemsIndex.payload?.library)}`);
}
const playerIndexSourceIds = (playerSystemsIndex.payload?.sources || []).map((source) => source.source_id);
if (playerIndexSourceIds.join("|") !== "PHB") {
  throw new Error(`Expected player systems index to include only PHB, got ${JSON.stringify(playerIndexSourceIds)}`);
}
if (
  playerSystemsIndex.payload?.query !== "" ||
  playerSystemsIndex.payload?.reference_query !== "" ||
  playerSystemsIndex.payload?.search_results?.length !== 0 ||
  playerSystemsIndex.payload?.has_rules_reference_search !== false ||
  playerSystemsIndex.payload?.source_scoped_rules_reference_sources?.length !== 0 ||
  playerSystemsIndex.payload?.permissions?.can_manage_systems !== false
) {
  throw new Error(`Unexpected player systems index payload: ${JSON.stringify(playerSystemsIndex.payload)}`);
}
const phbIndexSource = playerSystemsIndex.payload.sources[0];
if (
  phbIndexSource.entry_count !== 2 ||
  phbIndexSource.default_visibility !== "players" ||
  phbIndexSource.has_rules_reference_entries !== false ||
  phbIndexSource.rules_reference_search_scope !== "global"
) {
  throw new Error(`Unexpected PHB systems index source card: ${JSON.stringify(phbIndexSource)}`);
}

const playerSystemsSearch = await requestJson("/api/v1/campaigns/linden-pass/systems/search?q=chain", {
  "X-CPW-Fixture-Role": "player",
});
if (
  playerSystemsSearch.status !== 200 ||
  playerSystemsSearch.payload?.query !== "chain" ||
  playerSystemsSearch.payload?.search_results?.length !== 1 ||
  playerSystemsSearch.payload?.search_results?.[0]?.slug !== "phb-item-chain-mail"
) {
  throw new Error(`Unexpected player systems search payload: ${JSON.stringify(playerSystemsSearch.payload)}`);
}

const bearerPlayerSystemsIndex = await requestJson("/api/v1/campaigns/linden-pass/systems", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (
  bearerPlayerSystemsIndex.status !== 200 ||
  bearerPlayerSystemsIndex.payload?.permissions?.can_manage_systems !== false ||
  (bearerPlayerSystemsIndex.payload?.sources || []).map((source) => source.source_id).join("|") !== "PHB"
) {
  throw new Error(`Unexpected bearer player systems index payload: ${JSON.stringify(bearerPlayerSystemsIndex.payload)}`);
}

const dmSystemsIndex = await requestJson("/api/v1/campaigns/linden-pass/systems", {
  "X-CPW-Fixture-Role": "dm",
});
if (dmSystemsIndex.status !== 200 || dmSystemsIndex.payload?.permissions?.can_manage_systems !== true) {
  throw new Error(`Expected DM systems index manage permission, got ${JSON.stringify(dmSystemsIndex.payload?.permissions)}`);
}
const dmIndexSourceIds = (dmSystemsIndex.payload?.sources || []).map((source) => source.source_id);
if (dmIndexSourceIds.join("|") !== "MM|PHB") {
  throw new Error(`Expected DM systems index to include enabled source cards sorted by title, got ${JSON.stringify(dmIndexSourceIds)}`);
}

const bearerAdminSystemsIndex = await requestJson("/api/v1/campaigns/linden-pass/systems", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerAdminSystemsIndex.status !== 200 ||
  bearerAdminSystemsIndex.payload?.permissions?.can_manage_systems !== true ||
  (bearerAdminSystemsIndex.payload?.sources || []).map((source) => source.source_id).join("|") !== "MM|PHB"
) {
  throw new Error(`Unexpected bearer admin systems index payload: ${JSON.stringify(bearerAdminSystemsIndex.payload)}`);
}

const blockedSystemsSources = await requestJson("/api/v1/campaigns/linden-pass/systems/sources");
if (blockedSystemsSources.status !== 401 || blockedSystemsSources.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems source list to return auth_required 401, got ${blockedSystemsSources.status} ${blockedSystemsSources.payload?.error?.code}`,
  );
}

const playerSystemsSources = await requestJson("/api/v1/campaigns/linden-pass/systems/sources", {
  "X-CPW-Fixture-Role": "player",
});
if (playerSystemsSources.status !== 200 || playerSystemsSources.payload?.ok !== true) {
  throw new Error(`Expected player systems source list 200 ok, got ${playerSystemsSources.status}`);
}
if (playerSystemsSources.payload?.library?.library_slug !== "DND-5E") {
  throw new Error(`Expected DND-5E systems library, got ${JSON.stringify(playerSystemsSources.payload?.library)}`);
}
const playerSourceIds = (playerSystemsSources.payload?.sources || []).map((source) => source.source_id);
if (playerSourceIds.join("|") !== "PHB") {
  throw new Error(`Expected player-visible systems sources to include only PHB, got ${JSON.stringify(playerSourceIds)}`);
}
const phbSource = playerSystemsSources.payload.sources[0];
if (phbSource.entry_count !== 2 || phbSource.default_visibility !== "players" || phbSource.permissions?.can_manage !== false) {
  throw new Error(`Unexpected PHB source state for player: ${JSON.stringify(phbSource)}`);
}

const dmSystemsSources = await requestJson("/api/v1/campaigns/linden-pass/systems/sources", {
  "X-CPW-Fixture-Role": "dm",
});
if (dmSystemsSources.status !== 200 || dmSystemsSources.payload?.permissions?.can_manage_systems !== true) {
  throw new Error(`Expected DM systems source list manage permission, got ${JSON.stringify(dmSystemsSources.payload?.permissions)}`);
}
const dmSourceIds = (dmSystemsSources.payload?.sources || []).map((source) => source.source_id);
if (dmSourceIds.join("|") !== "MM|PHB|XGE") {
  throw new Error(`Expected DM systems source list to include all seeded sources sorted by title, got ${JSON.stringify(dmSourceIds)}`);
}
const bearerAdminSystemsSources = await requestJson("/api/v1/campaigns/linden-pass/systems/sources", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerAdminSystemsSources.status !== 200 ||
  bearerAdminSystemsSources.payload?.permissions?.can_manage_systems !== true ||
  (bearerAdminSystemsSources.payload?.sources || []).map((source) => source.source_id).join("|") !== "MM|PHB|XGE"
) {
  throw new Error(`Unexpected bearer admin systems source list payload: ${JSON.stringify(bearerAdminSystemsSources.payload)}`);
}
const mmSource = dmSystemsSources.payload.sources.find((source) => source.source_id === "MM");
if (mmSource?.entry_count !== 1 || mmSource?.default_visibility !== "dm" || mmSource?.permissions?.can_access !== true) {
  throw new Error(`Unexpected MM source state for DM: ${JSON.stringify(mmSource)}`);
}
const xgeSource = dmSystemsSources.payload.sources.find((source) => source.source_id === "XGE");
if (xgeSource?.is_enabled !== false || xgeSource?.is_configured !== true || xgeSource?.entry_count !== 0) {
  throw new Error(`Expected XGE configured disabled source state, got ${JSON.stringify(xgeSource)}`);
}

const blockedSystemsSourceDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/PHB");
if (blockedSystemsSourceDetail.status !== 401 || blockedSystemsSourceDetail.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems source detail to return auth_required 401, got ${blockedSystemsSourceDetail.status} ${blockedSystemsSourceDetail.payload?.error?.code}`,
  );
}

const playerPhbDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/PHB", {
  "X-CPW-Fixture-Role": "player",
});
if (playerPhbDetail.status !== 200 || playerPhbDetail.payload?.ok !== true) {
  throw new Error(`Expected player PHB source detail 200 ok, got ${playerPhbDetail.status}`);
}
if (playerPhbDetail.payload?.source?.source_id !== "PHB" || playerPhbDetail.payload?.source?.entry_count !== 2) {
  throw new Error(`Unexpected player PHB source detail source state: ${JSON.stringify(playerPhbDetail.payload?.source)}`);
}
const phbEntryGroups = (playerPhbDetail.payload?.entry_groups || []).map((group) => `${group.entry_type}:${group.count}`);
if (phbEntryGroups.join("|") !== "spell:1|item:1") {
  throw new Error(`Expected PHB source detail groups spell/item, got ${JSON.stringify(playerPhbDetail.payload?.entry_groups)}`);
}
if (
  playerPhbDetail.payload?.entry_count !== 2 ||
  playerPhbDetail.payload?.browsable_entry_count !== 2 ||
  playerPhbDetail.payload?.permissions?.can_manage_systems !== false
) {
  throw new Error(`Unexpected PHB source detail counts/permissions: ${JSON.stringify(playerPhbDetail.payload)}`);
}
if (playerPhbDetail.payload?.has_rules_reference_search !== false || playerPhbDetail.payload?.reference_query !== "") {
  throw new Error(`Unexpected PHB rules-reference state: ${JSON.stringify(playerPhbDetail.payload)}`);
}

const playerBlockedMmDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/MM", {
  "X-CPW-Fixture-Role": "player",
});
if (playerBlockedMmDetail.status !== 403 || playerBlockedMmDetail.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player MM source detail forbidden 403, got ${playerBlockedMmDetail.status} ${playerBlockedMmDetail.payload?.error?.code}`,
  );
}

const dmMmDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/MM", {
  "X-CPW-Fixture-Role": "dm",
});
if (dmMmDetail.status !== 200 || dmMmDetail.payload?.ok !== true) {
  throw new Error(`Expected DM MM source detail 200 ok, got ${dmMmDetail.status}`);
}
const mmEntryGroups = (dmMmDetail.payload?.entry_groups || []).map((group) => `${group.entry_type}:${group.count}`);
if (dmMmDetail.payload?.source?.source_id !== "MM" || mmEntryGroups.join("|") !== "monster:1") {
  throw new Error(`Unexpected DM MM source detail: ${JSON.stringify(dmMmDetail.payload)}`);
}
if (dmMmDetail.payload?.permissions?.can_manage_systems !== true || dmMmDetail.payload?.book_entries?.length !== 0) {
  throw new Error(`Unexpected DM MM source detail permissions/book entries: ${JSON.stringify(dmMmDetail.payload)}`);
}

const missingSystemsSourceDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/NOPE", {
  "X-CPW-Fixture-Role": "admin",
});
if (missingSystemsSourceDetail.status !== 404 || missingSystemsSourceDetail.payload?.error?.code !== "systems_source_not_found") {
  throw new Error(
    `Expected missing systems source detail JSON 404, got ${missingSystemsSourceDetail.status} ${missingSystemsSourceDetail.payload?.error?.code}`,
  );
}

const blockedSystemsSourceCategory = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/PHB/types/spell");
if (blockedSystemsSourceCategory.status !== 401 || blockedSystemsSourceCategory.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems source category to return auth_required 401, got ${blockedSystemsSourceCategory.status} ${blockedSystemsSourceCategory.payload?.error?.code}`,
  );
}

const playerPhbSpellCategory = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/PHB/types/spell", {
  "X-CPW-Fixture-Role": "player",
});
if (playerPhbSpellCategory.status !== 200 || playerPhbSpellCategory.payload?.ok !== true) {
  throw new Error(`Expected player PHB spell category 200 ok, got ${playerPhbSpellCategory.status}`);
}
if (
  playerPhbSpellCategory.payload?.source?.source_id !== "PHB" ||
  playerPhbSpellCategory.payload?.entry_type !== "spell" ||
  playerPhbSpellCategory.payload?.entry_type_label !== "Spells"
) {
  throw new Error(`Unexpected player PHB spell category identity: ${JSON.stringify(playerPhbSpellCategory.payload)}`);
}
if (
  playerPhbSpellCategory.payload?.entry_count !== 1 ||
  playerPhbSpellCategory.payload?.filtered_entry_count !== 1 ||
  playerPhbSpellCategory.payload?.entries?.[0]?.title !== "Mage Hand"
) {
  throw new Error(`Unexpected player PHB spell category entries: ${JSON.stringify(playerPhbSpellCategory.payload)}`);
}
if ((playerPhbSpellCategory.payload?.entry_groups || []).map((group) => `${group.entry_type}:${group.count}`).join("|") !== "spell:1|item:1") {
  throw new Error(`Unexpected player PHB category groups: ${JSON.stringify(playerPhbSpellCategory.payload?.entry_groups)}`);
}

const playerPhbSpellFiltered = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/PHB/types/spell?q=chain", {
  "X-CPW-Fixture-Role": "player",
});
if (
  playerPhbSpellFiltered.status !== 200 ||
  playerPhbSpellFiltered.payload?.query !== "chain" ||
  playerPhbSpellFiltered.payload?.entry_count !== 1 ||
  playerPhbSpellFiltered.payload?.filtered_entry_count !== 0
) {
  throw new Error(`Unexpected filtered PHB spell category payload: ${JSON.stringify(playerPhbSpellFiltered)}`);
}

const playerBlockedMmCategory = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster", {
  "X-CPW-Fixture-Role": "player",
});
if (playerBlockedMmCategory.status !== 403 || playerBlockedMmCategory.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player MM source category forbidden 403, got ${playerBlockedMmCategory.status} ${playerBlockedMmCategory.payload?.error?.code}`,
  );
}

const dmMmCategory = await requestJson("/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmMmCategory.status !== 200 ||
  dmMmCategory.payload?.entry_type !== "monster" ||
  dmMmCategory.payload?.entry_count !== 1 ||
  dmMmCategory.payload?.entries?.[0]?.slug !== "mm-monster-goblin" ||
  dmMmCategory.payload?.permissions?.can_manage_systems !== true
) {
  throw new Error(`Unexpected DM MM category payload: ${JSON.stringify(dmMmCategory.payload)}`);
}

const missingSystemsSourceCategory = await requestJson(
  "/api/v1/campaigns/linden-pass/systems/sources/PHB/types/definitely-not-a-type",
  {
    "X-CPW-Fixture-Role": "admin",
  },
);
if (
  missingSystemsSourceCategory.status !== 404 ||
  missingSystemsSourceCategory.payload?.error?.code !== "systems_source_category_not_found"
) {
  throw new Error(
    `Expected missing systems source category JSON 404, got ${missingSystemsSourceCategory.status} ${missingSystemsSourceCategory.payload?.error?.code}`,
  );
}

const blockedSystemsEntryDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/entries/phb-item-chain-mail");
if (blockedSystemsEntryDetail.status !== 401 || blockedSystemsEntryDetail.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems entry detail to return auth_required 401, got ${blockedSystemsEntryDetail.status} ${blockedSystemsEntryDetail.payload?.error?.code}`,
  );
}

const playerChainMailDetail = await requestJson("/api/v1/campaigns/linden-pass/systems/entries/phb-item-chain-mail", {
  "X-CPW-Fixture-Role": "player",
});
if (playerChainMailDetail.status !== 200 || playerChainMailDetail.payload?.ok !== true) {
  throw new Error(`Expected player systems entry detail 200 ok, got ${playerChainMailDetail.status}`);
}
const chainMailEntry = playerChainMailDetail.payload?.entry;
if (
  chainMailEntry?.slug !== "phb-item-chain-mail" ||
  chainMailEntry?.title !== "Chain Mail" ||
  chainMailEntry?.entry_type_label !== "Items" ||
  chainMailEntry?.source_page !== "145" ||
  chainMailEntry?.source_path !== "items/chain-mail"
) {
  throw new Error(`Unexpected player systems entry detail identity: ${JSON.stringify(chainMailEntry)}`);
}
if (
  chainMailEntry?.metadata?.armor?.ac !== 16 ||
  chainMailEntry?.body?.entries?.[0] !== "A sample armor entry." ||
  chainMailEntry?.rendered_html !== "<p>A sample armor entry.</p>"
) {
  throw new Error(`Unexpected player systems entry detail body fields: ${JSON.stringify(chainMailEntry)}`);
}
if (
  chainMailEntry?.source_state?.source_id !== "PHB" ||
  chainMailEntry?.source_state?.permissions?.can_access !== true ||
  chainMailEntry?.source_state?.permissions?.can_manage !== false
) {
  throw new Error(`Unexpected player systems entry source state: ${JSON.stringify(chainMailEntry?.source_state)}`);
}
if (
  chainMailEntry?.override?.entry_key !== "PHB:item:chain-mail" ||
  chainMailEntry?.override?.visibility_override !== "players" ||
  chainMailEntry?.override?.is_enabled_override !== null ||
  chainMailEntry?.override?.updated_by_user_id !== 42
) {
  throw new Error(`Unexpected player systems entry override: ${JSON.stringify(chainMailEntry?.override)}`);
}
const chainMailLinks = playerChainMailDetail.payload?.links || {};
if (
  chainMailLinks.flask_entry_url !== "/campaigns/linden-pass/systems/entries/phb-item-chain-mail" ||
  chainMailLinks.flask_source_url !== "/campaigns/linden-pass/systems/sources/PHB" ||
  chainMailLinks.flask_source_category_url !== "/campaigns/linden-pass/systems/sources/PHB/types/item" ||
  chainMailLinks.dm_content_systems_url !== ""
) {
  throw new Error(`Unexpected player systems entry links: ${JSON.stringify(chainMailLinks)}`);
}

const playerBlockedMmEntry = await requestJson("/api/v1/campaigns/linden-pass/systems/entries/mm-monster-goblin", {
  "X-CPW-Fixture-Role": "player",
});
if (playerBlockedMmEntry.status !== 403 || playerBlockedMmEntry.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player systems entry forbidden 403, got ${playerBlockedMmEntry.status} ${playerBlockedMmEntry.payload?.error?.code}`,
  );
}

const dmMmEntry = await requestJson("/api/v1/campaigns/linden-pass/systems/entries/mm-monster-goblin", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmMmEntry.status !== 200 ||
  dmMmEntry.payload?.entry?.slug !== "mm-monster-goblin" ||
  dmMmEntry.payload?.permissions?.can_manage_systems !== true ||
  !String(dmMmEntry.payload?.links?.dm_content_systems_url || "").includes("/campaigns/linden-pass/dm-content/systems") ||
  !String(dmMmEntry.payload?.links?.dm_content_systems_url || "").includes("systems-entry-overrides")
) {
  throw new Error(`Unexpected DM systems entry detail payload: ${JSON.stringify(dmMmEntry.payload)}`);
}

const missingSystemsEntryDetail = await requestJson(
  "/api/v1/campaigns/linden-pass/systems/entries/definitely-not-an-entry",
  {
    "X-CPW-Fixture-Role": "admin",
  },
);
if (missingSystemsEntryDetail.status !== 404 || missingSystemsEntryDetail.payload?.error?.code !== "systems_entry_not_found") {
  throw new Error(
    `Expected missing systems entry detail JSON 404, got ${missingSystemsEntryDetail.status} ${missingSystemsEntryDetail.payload?.error?.code}`,
  );
}

const blockedCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat");
if (blockedCombatState.status !== 401 || blockedCombatState.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated combat state to return auth_required 401, got ${blockedCombatState.status} ${blockedCombatState.payload?.error?.code}`,
  );
}

const invalidBearerCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat", {
  Authorization: "Bearer definitely-invalid-token",
});
if (invalidBearerCombatState.status !== 401 || invalidBearerCombatState.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected invalid bearer combat state to return auth_required 401, got ${invalidBearerCombatState.status} ${invalidBearerCombatState.payload?.error?.code}`,
  );
}

const outsiderCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat", {
  Authorization: `Bearer ${outsiderApiToken}`,
});
if (outsiderCombatState.status !== 403 || outsiderCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected outsider bearer combat state forbidden 403, got ${outsiderCombatState.status} ${outsiderCombatState.payload?.error?.code}`,
  );
}

const playerCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat", {
  "X-CPW-Fixture-Role": "player",
});
const playerCombatTracker = playerCombatState.payload?.tracker;
const playerCurrentCombatant = playerCombatTracker?.combatants?.[0];
if (
  playerCombatState.status !== 200 ||
  playerCombatState.payload?.ok !== true ||
  playerCombatState.payload?.changed !== true ||
  playerCombatState.payload?.campaign?.slug !== "linden-pass" ||
  playerCombatState.payload?.combat_system_supported !== true ||
  playerCombatState.payload?.live_revision !== 12 ||
  typeof playerCombatState.payload?.live_view_token !== "string" ||
  playerCombatState.payload.live_view_token.length !== 12 ||
  playerCombatTracker?.round_number !== 3 ||
  playerCombatTracker?.current_turn_label !== "Clockwork Hound" ||
  playerCombatTracker?.has_current_turn !== true ||
  playerCombatTracker?.combatant_count !== 2 ||
  playerCombatTracker?.combatants?.length !== 2 ||
  playerCurrentCombatant?.name !== "Clockwork Hound" ||
  playerCurrentCombatant?.source_kind !== "manual_npc" ||
  playerCurrentCombatant?.is_current_turn !== true ||
  playerCurrentCombatant?.current_hp !== 22 ||
  playerCurrentCombatant?.max_hp !== 28 ||
  playerCurrentCombatant?.temp_hp !== 3 ||
  playerCurrentCombatant?.movement_remaining !== 25 ||
  playerCurrentCombatant?.conditions?.[0]?.name !== "Restrained" ||
  playerCurrentCombatant?.npc_resource_counters?.[0]?.label !== "Overdrive" ||
  playerCurrentCombatant?.npc_resource_notes?.[0]?.label !== "Tactics" ||
  playerCombatState.payload?.selected_combatant_id !== 501 ||
  playerCombatState.payload?.selected_combatant?.name !== "Clockwork Hound" ||
  playerCombatState.payload?.selected_player_character !== null ||
  playerCombatState.payload?.player_character_targets?.length !== 0 ||
  playerCombatState.payload?.available_character_choices?.length !== 0 ||
  playerCombatState.payload?.available_statblock_choices?.length !== 0 ||
  playerCombatState.payload?.combat_condition_options?.includes("Salt-Burned") !== true ||
  playerCombatState.payload?.permissions?.can_manage_combat !== false ||
  playerCombatState.payload?.permissions?.can_access_systems !== true ||
  playerCombatState.payload?.links?.flask_dm_status_url !== ""
) {
  throw new Error(`Unexpected player combat state payload: ${JSON.stringify(playerCombatState.payload)}`);
}

const bearerPlayerCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (
  bearerPlayerCombatState.status !== 200 ||
  bearerPlayerCombatState.payload?.ok !== true ||
  bearerPlayerCombatState.payload?.campaign?.slug !== "linden-pass" ||
  bearerPlayerCombatState.payload?.live_revision !== 12 ||
  bearerPlayerCombatState.payload?.selected_combatant_id !== 501 ||
  bearerPlayerCombatState.payload?.permissions?.can_manage_combat !== false ||
  bearerPlayerCombatState.payload?.permissions?.can_access_systems !== true ||
  bearerPlayerCombatState.payload?.links?.flask_dm_status_url !== "" ||
  bearerPlayerCombatState.payload?.live_view_token !== playerCombatState.payload?.live_view_token
) {
  throw new Error(`Unexpected bearer player combat state payload: ${JSON.stringify(bearerPlayerCombatState.payload)}`);
}

const dmCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat", {
  "X-CPW-Fixture-Role": "dm",
});
const dmSelectedCombatant = dmCombatState.payload?.selected_combatant;
if (
  dmCombatState.status !== 200 ||
  dmCombatState.payload?.permissions?.can_manage_combat !== true ||
  dmCombatState.payload?.permissions?.can_access_dm_content !== true ||
  dmCombatState.payload?.live_revision !== 12 ||
  dmCombatState.payload?.tracker?.round_number !== 3 ||
  dmCombatState.payload?.tracker?.combatant_count !== 2 ||
  dmCombatState.payload?.selected_combatant_id !== 501 ||
  dmSelectedCombatant?.name !== "Clockwork Hound" ||
  dmSelectedCombatant?.dexterity_modifier !== 2 ||
  dmSelectedCombatant?.initiative_priority !== 1 ||
  dmSelectedCombatant?.can_edit_vitals !== true ||
  dmSelectedCombatant?.can_toggle_player_detail_visibility !== true ||
  dmSelectedCombatant?.npc_resource_counters?.[0]?.label !== "Overdrive" ||
  dmCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  dmCombatState.payload?.player_character_targets?.length !== 1 ||
  dmCombatState.payload?.player_character_targets?.[0]?.character_slug !== "arden-march" ||
  dmCombatState.payload?.player_character_targets?.[0]?.is_selected !== true ||
  dmCombatState.payload?.available_character_choices?.length !== 2 ||
  dmCombatState.payload?.available_character_choices?.map((item) => item.slug).join("|") !==
    "selene-brook|tobin-slate" ||
  dmCombatState.payload?.available_character_choices?.[0]?.name !== "Selene Brook" ||
  dmCombatState.payload?.available_statblock_choices?.length !== 1 ||
  dmCombatState.payload?.available_statblock_choices?.[0]?.id !== "301" ||
  dmCombatState.payload?.available_statblock_choices?.[0]?.title !== "Dock Tough" ||
  dmCombatState.payload?.available_statblock_choices?.[0]?.subtitle !== "HP 16 - Speed 30 ft." ||
  dmCombatState.payload?.available_statblock_choices?.[0]?.initiative_bonus !== "+2" ||
  dmCombatState.payload?.combat_condition_options?.includes("Prone") !== true ||
  dmCombatState.payload?.combat_condition_options?.includes("Salt-Burned") !== true ||
  dmCombatState.payload?.poll_settings?.active_interval_ms !== 500 ||
  dmCombatState.payload?.links?.flask_dm_status_url !== "/campaigns/linden-pass/combat/dm" ||
  dmCombatState.payload?.links?.flask_dm_controls_url !== "/campaigns/linden-pass/combat/dm?view=controls" ||
  dmCombatState.payload?.links?.flask_status_url !== "/campaigns/linden-pass/combat/status"
) {
  throw new Error(`Unexpected DM combat state payload: ${JSON.stringify(dmCombatState.payload)}`);
}

const bearerAdminCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerAdminCombatState.status !== 200 ||
  bearerAdminCombatState.payload?.permissions?.can_manage_combat !== true ||
  bearerAdminCombatState.payload?.permissions?.can_access_dm_content !== true ||
  bearerAdminCombatState.payload?.live_revision !== 12 ||
  bearerAdminCombatState.payload?.tracker?.combatant_count !== 2 ||
  bearerAdminCombatState.payload?.selected_combatant_id !== 501 ||
  bearerAdminCombatState.payload?.available_character_choices?.[0]?.name !== "Selene Brook" ||
  bearerAdminCombatState.payload?.available_statblock_choices?.[0]?.title !== "Dock Tough" ||
  bearerAdminCombatState.payload?.combat_condition_options?.includes("Salt-Burned") !== true ||
  bearerAdminCombatState.payload?.links?.flask_dm_status_url !== "/campaigns/linden-pass/combat/dm" ||
  bearerAdminCombatState.payload?.links?.flask_dm_controls_url !== "/campaigns/linden-pass/combat/dm?view=controls" ||
  bearerAdminCombatState.payload?.live_view_token !== dmCombatState.payload?.live_view_token
) {
  throw new Error(`Unexpected bearer admin combat state payload: ${JSON.stringify(bearerAdminCombatState.payload)}`);
}

const unchangedCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat/live-state", {
  "X-CPW-Fixture-Role": "dm",
  "X-Live-Revision": String(dmCombatState.payload.live_revision),
  "X-Live-View-Token": dmCombatState.payload.live_view_token,
});
if (
  unchangedCombatState.status !== 200 ||
  unchangedCombatState.payload?.changed !== false ||
  unchangedCombatState.payload?.live_revision !== dmCombatState.payload.live_revision ||
  unchangedCombatState.payload?.live_view_token !== dmCombatState.payload.live_view_token ||
  "tracker" in unchangedCombatState.payload
) {
  throw new Error(`Unexpected unchanged combat live-state payload: ${JSON.stringify(unchangedCombatState.payload)}`);
}

const unchangedBearerAdminCombatState = await requestJson("/api/v1/campaigns/linden-pass/combat/live-state", {
  Authorization: `Bearer ${liveApiToken}`,
  "X-Live-Revision": String(bearerAdminCombatState.payload.live_revision),
  "X-Live-View-Token": bearerAdminCombatState.payload.live_view_token,
});
if (
  unchangedBearerAdminCombatState.status !== 200 ||
  unchangedBearerAdminCombatState.payload?.changed !== false ||
  unchangedBearerAdminCombatState.payload?.live_revision !== bearerAdminCombatState.payload.live_revision ||
  unchangedBearerAdminCombatState.payload?.live_view_token !== bearerAdminCombatState.payload.live_view_token ||
  "tracker" in unchangedBearerAdminCombatState.payload
) {
  throw new Error(
    `Unexpected unchanged bearer admin combat live-state payload: ${JSON.stringify(unchangedBearerAdminCombatState.payload)}`,
  );
}

const fixtureSetCurrentCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/502/set-current",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST" },
);
if (
  fixtureSetCurrentCombatState.status !== 403 ||
  fixtureSetCurrentCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat set-current forbidden 403, got ${fixtureSetCurrentCombatState.status} ${fixtureSetCurrentCombatState.payload?.error?.code}`,
  );
}

const fixtureAdvanceCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/advance-turn",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST" },
);
if (fixtureAdvanceCombatState.status !== 403 || fixtureAdvanceCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture combat advance-turn forbidden 403, got ${fixtureAdvanceCombatState.status} ${fixtureAdvanceCombatState.payload?.error?.code}`,
  );
}

const playerAdvanceCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/advance-turn",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST" },
);
if (playerAdvanceCombatState.status !== 403 || playerAdvanceCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat advance-turn forbidden 403, got ${playerAdvanceCombatState.status} ${playerAdvanceCombatState.payload?.error?.code}`,
  );
}

const fixtureClearCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/clear",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST" },
);
if (fixtureClearCombatState.status !== 403 || fixtureClearCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture combat clear forbidden 403, got ${fixtureClearCombatState.status} ${fixtureClearCombatState.payload?.error?.code}`,
  );
}

const playerClearCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/clear",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST" },
);
if (playerClearCombatState.status !== 403 || playerClearCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat clear forbidden 403, got ${playerClearCombatState.status} ${playerClearCombatState.payload?.error?.code}`,
  );
}

const playerSetCurrentCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/502/set-current",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST" },
);
if (
  playerSetCurrentCombatState.status !== 403 ||
  playerSetCurrentCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected player combat set-current forbidden 403, got ${playerSetCurrentCombatState.status} ${playerSetCurrentCombatState.payload?.error?.code}`,
  );
}

const missingSetCurrentCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/set-current",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (
  missingSetCurrentCombatState.status !== 400 ||
  missingSetCurrentCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected missing combat set-current validation_error 400, got ${missingSetCurrentCombatState.status} ${missingSetCurrentCombatState.payload?.error?.code}`,
  );
}

const setCurrentCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/502/set-current",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (
  setCurrentCombatState.status !== 200 ||
  setCurrentCombatState.payload?.ok !== true ||
  setCurrentCombatState.payload?.changed !== true ||
  setCurrentCombatState.payload?.live_revision !== 13 ||
  setCurrentCombatState.payload?.tracker?.round_number !== 3 ||
  setCurrentCombatState.payload?.tracker?.current_turn_label !== "Arden March" ||
  setCurrentCombatState.payload?.selected_combatant_id !== 502 ||
  setCurrentCombatState.payload?.selected_combatant?.name !== "Arden March" ||
  setCurrentCombatState.payload?.selected_combatant?.combatant_revision !== 5 ||
  setCurrentCombatState.payload?.selected_combatant?.has_action !== true ||
  setCurrentCombatState.payload?.selected_combatant?.has_bonus_action !== true ||
  setCurrentCombatState.payload?.selected_combatant?.has_reaction !== true ||
  setCurrentCombatState.payload?.selected_combatant?.movement_remaining !== 30 ||
  setCurrentCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  setCurrentCombatState.payload?.player_character_targets?.[0]?.is_selected !== true ||
  setCurrentCombatState.payload?.available_character_choices?.map((item) => item.slug).join("|") !==
    "selene-brook|tobin-slate"
) {
  throw new Error(`Unexpected combat set-current payload: ${JSON.stringify(setCurrentCombatState.payload)}`);
}

const advanceWrapCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/advance-turn",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (
  advanceWrapCombatState.status !== 200 ||
  advanceWrapCombatState.payload?.ok !== true ||
  advanceWrapCombatState.payload?.changed !== true ||
  advanceWrapCombatState.payload?.live_revision !== 14 ||
  advanceWrapCombatState.payload?.tracker?.round_number !== 4 ||
  advanceWrapCombatState.payload?.tracker?.current_turn_label !== "Clockwork Hound" ||
  advanceWrapCombatState.payload?.selected_combatant_id !== 501 ||
  advanceWrapCombatState.payload?.selected_combatant?.name !== "Clockwork Hound" ||
  advanceWrapCombatState.payload?.selected_combatant?.combatant_revision !== 7 ||
  advanceWrapCombatState.payload?.selected_combatant?.has_action !== true ||
  advanceWrapCombatState.payload?.selected_combatant?.has_bonus_action !== true ||
  advanceWrapCombatState.payload?.selected_combatant?.has_reaction !== true ||
  advanceWrapCombatState.payload?.selected_combatant?.movement_remaining !== 40 ||
  advanceWrapCombatState.payload?.selected_player_character?.name !== "Arden March"
) {
  throw new Error(`Unexpected combat advance-turn wrap payload: ${JSON.stringify(advanceWrapCombatState.payload)}`);
}

const advanceNextCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/advance-turn",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (
  advanceNextCombatState.status !== 200 ||
  advanceNextCombatState.payload?.ok !== true ||
  advanceNextCombatState.payload?.changed !== true ||
  advanceNextCombatState.payload?.live_revision !== 15 ||
  advanceNextCombatState.payload?.tracker?.round_number !== 4 ||
  advanceNextCombatState.payload?.tracker?.current_turn_label !== "Arden March" ||
  advanceNextCombatState.payload?.selected_combatant_id !== 502 ||
  advanceNextCombatState.payload?.selected_combatant?.name !== "Arden March" ||
  advanceNextCombatState.payload?.selected_combatant?.combatant_revision !== 6 ||
  advanceNextCombatState.payload?.selected_combatant?.has_action !== true ||
  advanceNextCombatState.payload?.selected_combatant?.has_bonus_action !== true ||
  advanceNextCombatState.payload?.selected_combatant?.has_reaction !== true ||
  advanceNextCombatState.payload?.selected_combatant?.movement_remaining !== 30 ||
  advanceNextCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  advanceNextCombatState.payload?.player_character_targets?.[0]?.is_selected !== true
) {
  throw new Error(`Unexpected combat advance-turn next payload: ${JSON.stringify(advanceNextCombatState.payload)}`);
}

const missingAdvanceCombatState = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/combat/advance-turn",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (missingAdvanceCombatState.status !== 404 || missingAdvanceCombatState.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing combat advance-turn JSON 404, got ${missingAdvanceCombatState.status} ${missingAdvanceCombatState.payload?.error?.code}`,
  );
}

const missingClearCombatState = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/combat/clear",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (missingClearCombatState.status !== 404 || missingClearCombatState.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing combat clear JSON 404, got ${missingClearCombatState.status} ${missingClearCombatState.payload?.error?.code}`,
  );
}

const clearCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/clear",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (
  clearCombatState.status !== 200 ||
  clearCombatState.payload?.ok !== true ||
  clearCombatState.payload?.changed !== true ||
  clearCombatState.payload?.live_revision !== 16 ||
  clearCombatState.payload?.tracker?.round_number !== 1 ||
  clearCombatState.payload?.tracker?.current_turn_label !== "" ||
  clearCombatState.payload?.tracker?.has_current_turn !== false ||
  clearCombatState.payload?.tracker?.combatant_count !== 0 ||
  clearCombatState.payload?.tracker?.combatants?.length !== 0 ||
  clearCombatState.payload?.selected_combatant_id !== null ||
  clearCombatState.payload?.selected_combatant !== null ||
  clearCombatState.payload?.selected_player_character !== null ||
  clearCombatState.payload?.player_character_targets?.length !== 0 ||
  clearCombatState.payload?.available_character_choices?.map((item) => item.slug).join("|") !==
    "arden-march|selene-brook|tobin-slate"
) {
  throw new Error(`Unexpected combat clear payload: ${JSON.stringify(clearCombatState.payload)}`);
}

const combatClearAssertionDb = new Database(dbPath, { readonly: true });
const combatantRowsAfterClear = combatClearAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combatants WHERE campaign_slug = ?")
  .get("linden-pass");
const conditionRowsAfterClear = combatClearAssertionDb
  .prepare(
    `
      SELECT COUNT(*) AS count
      FROM campaign_combat_conditions
      WHERE combatant_id IN (501, 502)
    `,
  )
  .get();
const counterRowsAfterClear = combatClearAssertionDb
  .prepare(
    `
      SELECT COUNT(*) AS count
      FROM campaign_combatant_resource_counters
      WHERE combatant_id IN (501, 502)
    `,
  )
  .get();
const noteRowsAfterClear = combatClearAssertionDb
  .prepare(
    `
      SELECT COUNT(*) AS count
      FROM campaign_combatant_resource_notes
      WHERE combatant_id IN (501, 502)
    `,
  )
  .get();
combatClearAssertionDb.close();
if (
  combatantRowsAfterClear?.count !== 0 ||
  conditionRowsAfterClear?.count !== 0 ||
  counterRowsAfterClear?.count !== 0 ||
  noteRowsAfterClear?.count !== 0
) {
  throw new Error(
    `Expected combat clear to remove dependent rows, got ${JSON.stringify({
      combatantRowsAfterClear,
      conditionRowsAfterClear,
      counterRowsAfterClear,
      noteRowsAfterClear,
    })}`,
  );
}

const emptyAdvanceCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/advance-turn",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST" },
);
if (
  emptyAdvanceCombatState.status !== 400 ||
  emptyAdvanceCombatState.payload?.error?.code !== "validation_error" ||
  emptyAdvanceCombatState.payload?.error?.message !== "Add combatants before advancing turn order."
) {
  throw new Error(
    `Expected empty combat advance-turn validation_error 400, got ${emptyAdvanceCombatState.status} ${JSON.stringify(emptyAdvanceCombatState.payload)}`,
  );
}

const fixtureAddPlayerCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST", body: { character_slug: "arden-march" } },
);
if (fixtureAddPlayerCombatState.status !== 403 || fixtureAddPlayerCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture combat player add forbidden 403, got ${fixtureAddPlayerCombatState.status} ${fixtureAddPlayerCombatState.payload?.error?.code}`,
  );
}

const playerAddPlayerCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march" } },
);
if (playerAddPlayerCombatState.status !== 403 || playerAddPlayerCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat player add forbidden 403, got ${playerAddPlayerCombatState.status} ${playerAddPlayerCombatState.payload?.error?.code}`,
  );
}

const missingAddPlayerCombatState = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march" } },
);
if (missingAddPlayerCombatState.status !== 404 || missingAddPlayerCombatState.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing combat player add JSON 404, got ${missingAddPlayerCombatState.status} ${missingAddPlayerCombatState.payload?.error?.code}`,
  );
}

const malformedAddPlayerCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: "{" },
);
if (malformedAddPlayerCombatState.status !== 400 || malformedAddPlayerCombatState.payload?.error?.code !== "validation_error") {
  throw new Error(
    `Expected malformed combat player add validation_error 400, got ${malformedAddPlayerCombatState.status} ${malformedAddPlayerCombatState.payload?.error?.code}`,
  );
}

const invalidCharacterAddCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "missing-character" } },
);
if (
  invalidCharacterAddCombatState.status !== 400 ||
  invalidCharacterAddCombatState.payload?.error?.code !== "validation_error" ||
  invalidCharacterAddCombatState.payload?.error?.message !== "Choose a valid player character to add to the tracker."
) {
  throw new Error(
    `Expected invalid combat player add character validation_error 400, got ${invalidCharacterAddCombatState.status} ${JSON.stringify(invalidCharacterAddCombatState.payload)}`,
  );
}

const invalidTurnAddCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march", turn_value: "12.5" } },
);
if (
  invalidTurnAddCombatState.status !== 400 ||
  invalidTurnAddCombatState.payload?.error?.code !== "validation_error" ||
  invalidTurnAddCombatState.payload?.error?.message !== "Turn value must be a whole number."
) {
  throw new Error(
    `Expected invalid combat player add turn validation_error 400, got ${invalidTurnAddCombatState.status} ${JSON.stringify(invalidTurnAddCombatState.payload)}`,
  );
}

const invalidPriorityAddCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march", initiative_priority: "none" } },
);
if (
  invalidPriorityAddCombatState.status !== 400 ||
  invalidPriorityAddCombatState.payload?.error?.code !== "validation_error" ||
  invalidPriorityAddCombatState.payload?.error?.message !== "Priority must be a whole number."
) {
  throw new Error(
    `Expected invalid combat player add priority validation_error 400, got ${invalidPriorityAddCombatState.status} ${JSON.stringify(invalidPriorityAddCombatState.payload)}`,
  );
}

const lowPriorityAddCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march", initiative_priority: "0" } },
);
if (
  lowPriorityAddCombatState.status !== 400 ||
  lowPriorityAddCombatState.payload?.error?.code !== "validation_error" ||
  lowPriorityAddCombatState.payload?.error?.message !== "Priority must be 1 or higher."
) {
  throw new Error(
    `Expected low combat player add priority validation_error 400, got ${lowPriorityAddCombatState.status} ${JSON.stringify(lowPriorityAddCombatState.payload)}`,
  );
}

const addPlayerCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march", turn_value: "19", initiative_priority: "3" } },
);
const addedPlayerCombatant = addPlayerCombatState.payload?.tracker?.combatants?.[0];
if (
  addPlayerCombatState.status !== 200 ||
  addPlayerCombatState.payload?.ok !== true ||
  addPlayerCombatState.payload?.changed !== true ||
  addPlayerCombatState.payload?.live_revision !== 17 ||
  addPlayerCombatState.payload?.tracker?.round_number !== 1 ||
  addPlayerCombatState.payload?.tracker?.current_turn_label !== "" ||
  addPlayerCombatState.payload?.tracker?.has_current_turn !== false ||
  addPlayerCombatState.payload?.tracker?.combatant_count !== 1 ||
  addedPlayerCombatant?.name !== "Arden March" ||
  addedPlayerCombatant?.character_slug !== "arden-march" ||
  addedPlayerCombatant?.source_kind !== "character" ||
  addedPlayerCombatant?.source_ref !== "arden-march" ||
  addedPlayerCombatant?.type_label !== "Player character" ||
  addedPlayerCombatant?.turn_value !== 19 ||
  addedPlayerCombatant?.initiative_bonus_label !== "+2" ||
  addedPlayerCombatant?.dexterity_modifier !== 2 ||
  addedPlayerCombatant?.initiative_priority !== 3 ||
  addedPlayerCombatant?.current_hp !== 38 ||
  addedPlayerCombatant?.max_hp !== 38 ||
  addedPlayerCombatant?.temp_hp !== 0 ||
  addedPlayerCombatant?.state_revision !== 8 ||
  addedPlayerCombatant?.movement_total !== 30 ||
  addedPlayerCombatant?.movement_remaining !== 30 ||
  addedPlayerCombatant?.has_action !== true ||
  addedPlayerCombatant?.has_bonus_action !== true ||
  addedPlayerCombatant?.has_reaction !== true ||
  addedPlayerCombatant?.is_current_turn !== false ||
  addPlayerCombatState.payload?.selected_combatant_id !== addedPlayerCombatant?.id ||
  addPlayerCombatState.payload?.selected_combatant?.name !== "Arden March" ||
  addPlayerCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  addPlayerCombatState.payload?.player_character_targets?.[0]?.combatant_id !== addedPlayerCombatant?.id ||
  addPlayerCombatState.payload?.player_character_targets?.[0]?.is_selected !== true ||
  addPlayerCombatState.payload?.available_character_choices?.map((item) => item.slug).join("|") !==
    "selene-brook|tobin-slate"
) {
  throw new Error(`Unexpected combat player add payload: ${JSON.stringify(addPlayerCombatState.payload)}`);
}
const addedPlayerCombatantId = Number(addedPlayerCombatant?.id || 0);

const combatAddAssertionDb = new Database(dbPath, { readonly: true });
const addedPlayerRow = combatAddAssertionDb
  .prepare(
    `
      SELECT
        combatant_type,
        player_detail_visible,
        source_kind,
        source_ref,
        display_name,
        turn_value,
        initiative_bonus,
        dexterity_modifier,
        initiative_priority,
        current_hp,
        max_hp,
        temp_hp,
        movement_total,
        movement_remaining,
        has_action,
        has_bonus_action,
        has_reaction,
        revision,
        created_by_user_id,
        updated_by_user_id
      FROM campaign_combatants
      WHERE campaign_slug = ?
        AND character_slug = ?
    `,
  )
  .get("linden-pass", "arden-march");
const trackerAfterPlayerAdd = combatAddAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatAddAssertionDb.close();
if (
  addedPlayerRow?.combatant_type !== "player_character" ||
  addedPlayerRow?.player_detail_visible !== 1 ||
  addedPlayerRow?.source_kind !== "character" ||
  addedPlayerRow?.source_ref !== "arden-march" ||
  addedPlayerRow?.display_name !== "Arden March" ||
  addedPlayerRow?.turn_value !== 19 ||
  addedPlayerRow?.initiative_bonus !== 2 ||
  addedPlayerRow?.dexterity_modifier !== 2 ||
  addedPlayerRow?.initiative_priority !== 3 ||
  addedPlayerRow?.current_hp !== 38 ||
  addedPlayerRow?.max_hp !== 38 ||
  addedPlayerRow?.temp_hp !== 0 ||
  addedPlayerRow?.movement_total !== 30 ||
  addedPlayerRow?.movement_remaining !== 30 ||
  addedPlayerRow?.has_action !== 1 ||
  addedPlayerRow?.has_bonus_action !== 1 ||
  addedPlayerRow?.has_reaction !== 1 ||
  addedPlayerRow?.revision !== 1 ||
  addedPlayerRow?.created_by_user_id !== 77 ||
  addedPlayerRow?.updated_by_user_id !== 77 ||
  trackerAfterPlayerAdd?.round_number !== 1 ||
  trackerAfterPlayerAdd?.current_combatant_id !== null ||
  trackerAfterPlayerAdd?.revision !== 17
) {
  throw new Error(
    `Unexpected combat player add database rows: ${JSON.stringify({ addedPlayerRow, trackerAfterPlayerAdd })}`,
  );
}

const duplicateAddPlayerCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/player-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { character_slug: "arden-march" } },
);
if (
  duplicateAddPlayerCombatState.status !== 400 ||
  duplicateAddPlayerCombatState.payload?.error?.code !== "validation_error" ||
  duplicateAddPlayerCombatState.payload?.error?.message !== "That player character is already in the combat tracker."
) {
  throw new Error(
    `Expected duplicate combat player add validation_error 400, got ${duplicateAddPlayerCombatState.status} ${JSON.stringify(duplicateAddPlayerCombatState.payload)}`,
  );
}

const fixtureAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST", body: { display_name: "Dock Bandit", max_hp: 9 } },
);
if (fixtureAddNpcCombatState.status !== 403 || fixtureAddNpcCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture combat NPC add forbidden 403, got ${fixtureAddNpcCombatState.status} ${fixtureAddNpcCombatState.payload?.error?.code}`,
  );
}

const playerAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST", body: { display_name: "Dock Bandit", max_hp: 9 } },
);
if (playerAddNpcCombatState.status !== 403 || playerAddNpcCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat NPC add forbidden 403, got ${playerAddNpcCombatState.status} ${playerAddNpcCombatState.payload?.error?.code}`,
  );
}

const missingAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { display_name: "Dock Bandit", max_hp: 9 } },
);
if (missingAddNpcCombatState.status !== 404 || missingAddNpcCombatState.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing combat NPC add JSON 404, got ${missingAddNpcCombatState.status} ${missingAddNpcCombatState.payload?.error?.code}`,
  );
}

const malformedAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: "{" },
);
if (malformedAddNpcCombatState.status !== 400 || malformedAddNpcCombatState.payload?.error?.code !== "validation_error") {
  throw new Error(
    `Expected malformed combat NPC add validation_error 400, got ${malformedAddNpcCombatState.status} ${malformedAddNpcCombatState.payload?.error?.code}`,
  );
}

const namelessAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { display_name: "  ", max_hp: 9 } },
);
if (
  namelessAddNpcCombatState.status !== 400 ||
  namelessAddNpcCombatState.payload?.error?.code !== "validation_error" ||
  namelessAddNpcCombatState.payload?.error?.message !== "NPC name is required."
) {
  throw new Error(
    `Expected nameless combat NPC add validation_error 400, got ${namelessAddNpcCombatState.status} ${JSON.stringify(namelessAddNpcCombatState.payload)}`,
  );
}

const missingMaxHpAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { display_name: "Dock Bandit" } },
);
if (
  missingMaxHpAddNpcCombatState.status !== 400 ||
  missingMaxHpAddNpcCombatState.payload?.error?.code !== "validation_error" ||
  missingMaxHpAddNpcCombatState.payload?.error?.message !== "Max HP is required."
) {
  throw new Error(
    `Expected missing max HP combat NPC add validation_error 400, got ${missingMaxHpAddNpcCombatState.status} ${JSON.stringify(missingMaxHpAddNpcCombatState.payload)}`,
  );
}

const invalidInitiativeAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { display_name: "Dock Bandit", initiative_bonus: "fast", max_hp: 9 } },
);
if (
  invalidInitiativeAddNpcCombatState.status !== 400 ||
  invalidInitiativeAddNpcCombatState.payload?.error?.code !== "validation_error" ||
  invalidInitiativeAddNpcCombatState.payload?.error?.message !== "Initiative bonus must be a whole number."
) {
  throw new Error(
    `Expected invalid initiative combat NPC add validation_error 400, got ${invalidInitiativeAddNpcCombatState.status} ${JSON.stringify(invalidInitiativeAddNpcCombatState.payload)}`,
  );
}

const negativeTempHpAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { display_name: "Dock Bandit", max_hp: 9, temp_hp: "-1" } },
);
if (
  negativeTempHpAddNpcCombatState.status !== 400 ||
  negativeTempHpAddNpcCombatState.payload?.error?.code !== "validation_error" ||
  negativeTempHpAddNpcCombatState.payload?.error?.message !== "Temp HP cannot be less than 0."
) {
  throw new Error(
    `Expected negative temp HP combat NPC add validation_error 400, got ${negativeTempHpAddNpcCombatState.status} ${JSON.stringify(negativeTempHpAddNpcCombatState.payload)}`,
  );
}

const tooHighCurrentHpAddNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { display_name: "Dock Bandit", current_hp: 10, max_hp: 9 } },
);
if (
  tooHighCurrentHpAddNpcCombatState.status !== 400 ||
  tooHighCurrentHpAddNpcCombatState.payload?.error?.code !== "validation_error" ||
  tooHighCurrentHpAddNpcCombatState.payload?.error?.message !== "Current HP cannot exceed max HP."
) {
  throw new Error(
    `Expected too-high current HP combat NPC add validation_error 400, got ${tooHighCurrentHpAddNpcCombatState.status} ${JSON.stringify(tooHighCurrentHpAddNpcCombatState.payload)}`,
  );
}

const addNpcCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/npc-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "POST",
    body: {
      display_name: "Dock Bandit",
      turn_value: "12",
      initiative_bonus: "1",
      dexterity_modifier: "",
      initiative_priority: "2",
      current_hp: "7",
      max_hp: "9",
      temp_hp: "2",
      movement_total: "25",
    },
  },
);
const addedNpcCombatant = addNpcCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.name === "Dock Bandit",
);
if (
  addNpcCombatState.status !== 200 ||
  addNpcCombatState.payload?.ok !== true ||
  addNpcCombatState.payload?.changed !== true ||
  addNpcCombatState.payload?.live_revision !== 18 ||
  addNpcCombatState.payload?.tracker?.round_number !== 1 ||
  addNpcCombatState.payload?.tracker?.current_turn_label !== "" ||
  addNpcCombatState.payload?.tracker?.has_current_turn !== false ||
  addNpcCombatState.payload?.tracker?.combatant_count !== 2 ||
  addNpcCombatState.payload?.selected_combatant?.name !== "Arden March" ||
  addNpcCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  addNpcCombatState.payload?.player_character_targets?.[0]?.name !== "Arden March" ||
  addNpcCombatState.payload?.available_character_choices?.map((item) => item.slug).join("|") !==
    "selene-brook|tobin-slate" ||
  addedNpcCombatant?.character_slug !== "" ||
  addedNpcCombatant?.source_kind !== "manual_npc" ||
  addedNpcCombatant?.source_ref !== "" ||
  addedNpcCombatant?.source_label !== "Manual NPC" ||
  addedNpcCombatant?.type_label !== "NPC" ||
  addedNpcCombatant?.turn_value !== 12 ||
  addedNpcCombatant?.initiative_bonus_label !== "+1" ||
  addedNpcCombatant?.dexterity_modifier !== 1 ||
  addedNpcCombatant?.initiative_priority !== 2 ||
  addedNpcCombatant?.current_hp !== 7 ||
  addedNpcCombatant?.max_hp !== 9 ||
  addedNpcCombatant?.temp_hp !== 2 ||
  addedNpcCombatant?.movement_total !== 25 ||
  addedNpcCombatant?.movement_remaining !== 25 ||
  addedNpcCombatant?.has_action !== true ||
  addedNpcCombatant?.has_bonus_action !== true ||
  addedNpcCombatant?.has_reaction !== true ||
  addedNpcCombatant?.is_current_turn !== false ||
  addedNpcCombatant?.npc_resource_counters?.length !== 0 ||
  addedNpcCombatant?.npc_resource_notes?.length !== 0
) {
  throw new Error(`Unexpected combat NPC add payload: ${JSON.stringify(addNpcCombatState.payload)}`);
}

const combatNpcAddAssertionDb = new Database(dbPath, { readonly: true });
const addedNpcRow = combatNpcAddAssertionDb
  .prepare(
    `
      SELECT
        id,
        combatant_type,
        character_slug,
        player_detail_visible,
        source_kind,
        source_ref,
        display_name,
        turn_value,
        initiative_bonus,
        dexterity_modifier,
        initiative_priority,
        current_hp,
        max_hp,
        temp_hp,
        movement_total,
        movement_remaining,
        has_action,
        has_bonus_action,
        has_reaction,
        revision,
        created_by_user_id,
        updated_by_user_id
      FROM campaign_combatants
      WHERE campaign_slug = ?
        AND display_name = ?
    `,
  )
  .get("linden-pass", "Dock Bandit");
const addedNpcCounterRows = combatNpcAddAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combatant_resource_counters WHERE combatant_id = ?")
  .get(addedNpcRow?.id || -1);
const addedNpcNoteRows = combatNpcAddAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combatant_resource_notes WHERE combatant_id = ?")
  .get(addedNpcRow?.id || -1);
const trackerAfterNpcAdd = combatNpcAddAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatNpcAddAssertionDb.close();
if (
  addedNpcRow?.combatant_type !== "npc" ||
  addedNpcRow?.character_slug !== null ||
  addedNpcRow?.player_detail_visible !== 0 ||
  addedNpcRow?.source_kind !== "manual_npc" ||
  addedNpcRow?.source_ref !== "" ||
  addedNpcRow?.display_name !== "Dock Bandit" ||
  addedNpcRow?.turn_value !== 12 ||
  addedNpcRow?.initiative_bonus !== 1 ||
  addedNpcRow?.dexterity_modifier !== 1 ||
  addedNpcRow?.initiative_priority !== 2 ||
  addedNpcRow?.current_hp !== 7 ||
  addedNpcRow?.max_hp !== 9 ||
  addedNpcRow?.temp_hp !== 2 ||
  addedNpcRow?.movement_total !== 25 ||
  addedNpcRow?.movement_remaining !== 25 ||
  addedNpcRow?.has_action !== 1 ||
  addedNpcRow?.has_bonus_action !== 1 ||
  addedNpcRow?.has_reaction !== 1 ||
  addedNpcRow?.revision !== 1 ||
  addedNpcRow?.created_by_user_id !== 77 ||
  addedNpcRow?.updated_by_user_id !== 77 ||
  addedNpcCounterRows?.count !== 0 ||
  addedNpcNoteRows?.count !== 0 ||
  trackerAfterNpcAdd?.round_number !== 1 ||
  trackerAfterNpcAdd?.current_combatant_id !== null ||
  trackerAfterNpcAdd?.revision !== 18
) {
  throw new Error(
    `Unexpected combat NPC add database rows: ${JSON.stringify({
      addedNpcRow,
      addedNpcCounterRows,
      addedNpcNoteRows,
      trackerAfterNpcAdd,
    })}`,
  );
}

const fixtureAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST", body: { statblock_id: 301 } },
);
if (fixtureAddStatblockCombatState.status !== 403 || fixtureAddStatblockCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture combat statblock add forbidden 403, got ${fixtureAddStatblockCombatState.status} ${fixtureAddStatblockCombatState.payload?.error?.code}`,
  );
}

const playerAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST", body: { statblock_id: 301 } },
);
if (playerAddStatblockCombatState.status !== 403 || playerAddStatblockCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat statblock add forbidden 403, got ${playerAddStatblockCombatState.status} ${playerAddStatblockCombatState.payload?.error?.code}`,
  );
}

const missingAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/combat/statblock-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { statblock_id: 301 } },
);
if (
  missingAddStatblockCombatState.status !== 404 ||
  missingAddStatblockCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat statblock add JSON 404, got ${missingAddStatblockCombatState.status} ${missingAddStatblockCombatState.payload?.error?.code}`,
  );
}

const malformedAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: "{" },
);
if (
  malformedAddStatblockCombatState.status !== 400 ||
  malformedAddStatblockCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat statblock add validation_error 400, got ${malformedAddStatblockCombatState.status} ${JSON.stringify(malformedAddStatblockCombatState.payload)}`,
  );
}

const invalidAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { statblock_id: 999999 } },
);
if (
  invalidAddStatblockCombatState.status !== 400 ||
  invalidAddStatblockCombatState.payload?.error?.code !== "validation_error" ||
  invalidAddStatblockCombatState.payload?.error?.message !== "Choose a valid DM Content statblock to add."
) {
  throw new Error(
    `Expected invalid combat statblock add validation_error 400, got ${invalidAddStatblockCombatState.status} ${JSON.stringify(invalidAddStatblockCombatState.payload)}`,
  );
}

const invalidTurnAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { statblock_id: 301, turn_value: "soon" } },
);
if (
  invalidTurnAddStatblockCombatState.status !== 400 ||
  invalidTurnAddStatblockCombatState.payload?.error?.code !== "validation_error" ||
  invalidTurnAddStatblockCombatState.payload?.error?.message !== "Turn value must be a whole number."
) {
  throw new Error(
    `Expected invalid turn combat statblock add validation_error 400, got ${invalidTurnAddStatblockCombatState.status} ${JSON.stringify(invalidTurnAddStatblockCombatState.payload)}`,
  );
}

const invalidPriorityAddStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { statblock_id: 301, initiative_priority: "0" } },
);
if (
  invalidPriorityAddStatblockCombatState.status !== 400 ||
  invalidPriorityAddStatblockCombatState.payload?.error?.code !== "validation_error" ||
  invalidPriorityAddStatblockCombatState.payload?.error?.message !== "Priority must be 1 or higher."
) {
  throw new Error(
    `Expected invalid priority combat statblock add validation_error 400, got ${invalidPriorityAddStatblockCombatState.status} ${JSON.stringify(invalidPriorityAddStatblockCombatState.payload)}`,
  );
}

const addStatblockCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "POST",
    body: {
      statblock_id: "301",
      initiative_priority: "3",
    },
  },
);
const addedStatblockCombatant = addStatblockCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.name === "Dock Tough",
);
if (
  addStatblockCombatState.status !== 200 ||
  addStatblockCombatState.payload?.ok !== true ||
  addStatblockCombatState.payload?.changed !== true ||
  addStatblockCombatState.payload?.live_revision !== 19 ||
  addStatblockCombatState.payload?.tracker?.round_number !== 1 ||
  addStatblockCombatState.payload?.tracker?.current_turn_label !== "" ||
  addStatblockCombatState.payload?.tracker?.has_current_turn !== false ||
  addStatblockCombatState.payload?.tracker?.combatant_count !== 3 ||
  addStatblockCombatState.payload?.selected_combatant?.name !== "Arden March" ||
  addStatblockCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  addStatblockCombatState.payload?.available_statblock_choices?.[0]?.id !== "301" ||
  addedStatblockCombatant?.character_slug !== "" ||
  addedStatblockCombatant?.source_kind !== "dm_statblock" ||
  addedStatblockCombatant?.source_ref !== "301" ||
  addedStatblockCombatant?.source_label !== "DM Content" ||
  addedStatblockCombatant?.type_label !== "NPC" ||
  addedStatblockCombatant?.turn_value !== 2 ||
  addedStatblockCombatant?.initiative_bonus_label !== "+2" ||
  addedStatblockCombatant?.dexterity_modifier !== 2 ||
  addedStatblockCombatant?.initiative_priority !== 3 ||
  addedStatblockCombatant?.current_hp !== 16 ||
  addedStatblockCombatant?.max_hp !== 16 ||
  addedStatblockCombatant?.temp_hp !== 0 ||
  addedStatblockCombatant?.movement_total !== 30 ||
  addedStatblockCombatant?.movement_remaining !== 30 ||
  addedStatblockCombatant?.has_action !== true ||
  addedStatblockCombatant?.has_bonus_action !== true ||
  addedStatblockCombatant?.has_reaction !== true ||
  addedStatblockCombatant?.is_current_turn !== false ||
  addedStatblockCombatant?.npc_resource_counters?.[0]?.resource_key !== "arcane-jolt" ||
  addedStatblockCombatant?.npc_resource_counters?.[0]?.label !== "Arcane Jolt" ||
  addedStatblockCombatant?.npc_resource_counters?.[0]?.current_value !== 2 ||
  addedStatblockCombatant?.npc_resource_counters?.[0]?.max_value !== 2 ||
  addedStatblockCombatant?.npc_resource_counters?.[0]?.reset_label !== "Per day" ||
  addedStatblockCombatant?.npc_resource_counters?.[0]?.source_label !== "DM Content" ||
  addedStatblockCombatant?.npc_resource_notes?.[0]?.label !== "At-will spellcasting" ||
  addedStatblockCombatant?.npc_resource_notes?.[0]?.note !== "light, mage hand" ||
  addedStatblockCombatant?.npc_resource_notes?.[0]?.source_label !== "DM Content" ||
  addedStatblockCombatant?.npc_resource_notes?.[1]?.label !== "Rust Breath" ||
  addedStatblockCombatant?.npc_resource_notes?.[1]?.note !== "Recharge 5-6" ||
  addedStatblockCombatant?.npc_resource_notes?.[1]?.source_label !== "DM Content"
) {
  throw new Error(`Unexpected combat statblock add payload: ${JSON.stringify(addStatblockCombatState.payload)}`);
}

const combatStatblockAddAssertionDb = new Database(dbPath, { readonly: true });
const addedStatblockRow = combatStatblockAddAssertionDb
  .prepare(
    `
      SELECT
        id,
        combatant_type,
        character_slug,
        player_detail_visible,
        source_kind,
        source_ref,
        display_name,
        turn_value,
        initiative_bonus,
        dexterity_modifier,
        initiative_priority,
        current_hp,
        max_hp,
        temp_hp,
        movement_total,
        movement_remaining,
        has_action,
        has_bonus_action,
        has_reaction,
        revision,
        created_by_user_id,
        updated_by_user_id
      FROM campaign_combatants
      WHERE campaign_slug = ?
        AND display_name = ?
        AND source_kind = ?
    `,
  )
  .get("linden-pass", "Dock Tough", "dm_statblock");
const addedStatblockCounterRows = combatStatblockAddAssertionDb
  .prepare(
    `
      SELECT resource_key, label, current_value, max_value, reset_label, source_label, created_by_user_id, updated_by_user_id
      FROM campaign_combatant_resource_counters
      WHERE combatant_id = ?
      ORDER BY id ASC
    `,
  )
  .all(addedStatblockRow?.id || -1);
const addedStatblockNoteRows = combatStatblockAddAssertionDb
  .prepare(
    `
      SELECT label, note, source_label, created_by_user_id
      FROM campaign_combatant_resource_notes
      WHERE combatant_id = ?
      ORDER BY id ASC
    `,
  )
  .all(addedStatblockRow?.id || -1);
const trackerAfterStatblockAdd = combatStatblockAddAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatStatblockAddAssertionDb.close();
if (
  addedStatblockRow?.combatant_type !== "npc" ||
  addedStatblockRow?.character_slug !== null ||
  addedStatblockRow?.player_detail_visible !== 0 ||
  addedStatblockRow?.source_kind !== "dm_statblock" ||
  addedStatblockRow?.source_ref !== "301" ||
  addedStatblockRow?.display_name !== "Dock Tough" ||
  addedStatblockRow?.turn_value !== 2 ||
  addedStatblockRow?.initiative_bonus !== 2 ||
  addedStatblockRow?.dexterity_modifier !== 2 ||
  addedStatblockRow?.initiative_priority !== 3 ||
  addedStatblockRow?.current_hp !== 16 ||
  addedStatblockRow?.max_hp !== 16 ||
  addedStatblockRow?.temp_hp !== 0 ||
  addedStatblockRow?.movement_total !== 30 ||
  addedStatblockRow?.movement_remaining !== 30 ||
  addedStatblockRow?.has_action !== 1 ||
  addedStatblockRow?.has_bonus_action !== 1 ||
  addedStatblockRow?.has_reaction !== 1 ||
  addedStatblockRow?.revision !== 1 ||
  addedStatblockRow?.created_by_user_id !== 77 ||
  addedStatblockRow?.updated_by_user_id !== 77 ||
  addedStatblockCounterRows.length !== 1 ||
  addedStatblockCounterRows[0]?.resource_key !== "arcane-jolt" ||
  addedStatblockCounterRows[0]?.label !== "Arcane Jolt" ||
  addedStatblockCounterRows[0]?.current_value !== 2 ||
  addedStatblockCounterRows[0]?.max_value !== 2 ||
  addedStatblockCounterRows[0]?.reset_label !== "Per day" ||
  addedStatblockCounterRows[0]?.source_label !== "DM Content" ||
  addedStatblockCounterRows[0]?.created_by_user_id !== 77 ||
  addedStatblockCounterRows[0]?.updated_by_user_id !== 77 ||
  addedStatblockNoteRows.length !== 2 ||
  addedStatblockNoteRows[0]?.label !== "At-will spellcasting" ||
  addedStatblockNoteRows[0]?.note !== "light, mage hand" ||
  addedStatblockNoteRows[0]?.source_label !== "DM Content" ||
  addedStatblockNoteRows[0]?.created_by_user_id !== 77 ||
  addedStatblockNoteRows[1]?.label !== "Rust Breath" ||
  addedStatblockNoteRows[1]?.note !== "Recharge 5-6" ||
  addedStatblockNoteRows[1]?.source_label !== "DM Content" ||
  addedStatblockNoteRows[1]?.created_by_user_id !== 77 ||
  trackerAfterStatblockAdd?.round_number !== 1 ||
  trackerAfterStatblockAdd?.current_combatant_id !== null ||
  trackerAfterStatblockAdd?.revision !== 19
) {
  throw new Error(
    `Unexpected combat statblock add database rows: ${JSON.stringify({
      addedStatblockRow,
      addedStatblockCounterRows,
      addedStatblockNoteRows,
      trackerAfterStatblockAdd,
    })}`,
  );
}

const fixtureAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST", body: { entry_key: "MM:monster:goblin" } },
);
if (
  fixtureAddSystemsMonsterCombatState.status !== 403 ||
  fixtureAddSystemsMonsterCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat Systems monster add forbidden 403, got ${fixtureAddSystemsMonsterCombatState.status} ${fixtureAddSystemsMonsterCombatState.payload?.error?.code}`,
  );
}

const playerAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST", body: { entry_key: "MM:monster:goblin" } },
);
if (
  playerAddSystemsMonsterCombatState.status !== 403 ||
  playerAddSystemsMonsterCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected player combat Systems monster add forbidden 403, got ${playerAddSystemsMonsterCombatState.status} ${playerAddSystemsMonsterCombatState.payload?.error?.code}`,
  );
}

const missingAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { entry_key: "MM:monster:goblin" } },
);
if (
  missingAddSystemsMonsterCombatState.status !== 404 ||
  missingAddSystemsMonsterCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat Systems monster add JSON 404, got ${missingAddSystemsMonsterCombatState.status} ${missingAddSystemsMonsterCombatState.payload?.error?.code}`,
  );
}

const malformedAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: "{" },
);
if (
  malformedAddSystemsMonsterCombatState.status !== 400 ||
  malformedAddSystemsMonsterCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat Systems monster add validation_error 400, got ${malformedAddSystemsMonsterCombatState.status} ${JSON.stringify(malformedAddSystemsMonsterCombatState.payload)}`,
  );
}

const invalidAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { entry_key: "MM:monster:not-real" } },
);
if (
  invalidAddSystemsMonsterCombatState.status !== 400 ||
  invalidAddSystemsMonsterCombatState.payload?.error?.code !== "validation_error" ||
  invalidAddSystemsMonsterCombatState.payload?.error?.message !== "Choose a valid Systems monster to add."
) {
  throw new Error(
    `Expected invalid combat Systems monster add validation_error 400, got ${invalidAddSystemsMonsterCombatState.status} ${JSON.stringify(invalidAddSystemsMonsterCombatState.payload)}`,
  );
}

const nonMonsterAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { entry_key: "PHB:spell:mage-hand" } },
);
if (
  nonMonsterAddSystemsMonsterCombatState.status !== 400 ||
  nonMonsterAddSystemsMonsterCombatState.payload?.error?.code !== "validation_error" ||
  nonMonsterAddSystemsMonsterCombatState.payload?.error?.message !== "Choose a valid Systems monster to add."
) {
  throw new Error(
    `Expected non-monster combat Systems monster add validation_error 400, got ${nonMonsterAddSystemsMonsterCombatState.status} ${JSON.stringify(nonMonsterAddSystemsMonsterCombatState.payload)}`,
  );
}

const invalidTurnAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { entry_key: "MM:monster:goblin", turn_value: "soon" } },
);
if (
  invalidTurnAddSystemsMonsterCombatState.status !== 400 ||
  invalidTurnAddSystemsMonsterCombatState.payload?.error?.code !== "validation_error" ||
  invalidTurnAddSystemsMonsterCombatState.payload?.error?.message !== "Turn value must be a whole number."
) {
  throw new Error(
    `Expected invalid turn combat Systems monster add validation_error 400, got ${invalidTurnAddSystemsMonsterCombatState.status} ${JSON.stringify(invalidTurnAddSystemsMonsterCombatState.payload)}`,
  );
}

const invalidPriorityAddSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { entry_key: "MM:monster:goblin", initiative_priority: "0" } },
);
if (
  invalidPriorityAddSystemsMonsterCombatState.status !== 400 ||
  invalidPriorityAddSystemsMonsterCombatState.payload?.error?.code !== "validation_error" ||
  invalidPriorityAddSystemsMonsterCombatState.payload?.error?.message !== "Priority must be 1 or higher."
) {
  throw new Error(
    `Expected invalid priority combat Systems monster add validation_error 400, got ${invalidPriorityAddSystemsMonsterCombatState.status} ${JSON.stringify(invalidPriorityAddSystemsMonsterCombatState.payload)}`,
  );
}

const addSystemsMonsterCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "POST",
    body: {
      entry_key: "MM:monster:goblin",
      initiative_priority: "4",
    },
  },
);
const addedSystemsMonsterCombatant = addSystemsMonsterCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.name === "Goblin",
);
if (
  addSystemsMonsterCombatState.status !== 200 ||
  addSystemsMonsterCombatState.payload?.ok !== true ||
  addSystemsMonsterCombatState.payload?.changed !== true ||
  addSystemsMonsterCombatState.payload?.live_revision !== 20 ||
  addSystemsMonsterCombatState.payload?.tracker?.round_number !== 1 ||
  addSystemsMonsterCombatState.payload?.tracker?.current_turn_label !== "" ||
  addSystemsMonsterCombatState.payload?.tracker?.has_current_turn !== false ||
  addSystemsMonsterCombatState.payload?.tracker?.combatant_count !== 4 ||
  addSystemsMonsterCombatState.payload?.selected_combatant?.name !== "Arden March" ||
  addSystemsMonsterCombatState.payload?.selected_player_character?.name !== "Arden March" ||
  addedSystemsMonsterCombatant?.character_slug !== "" ||
  addedSystemsMonsterCombatant?.source_kind !== "systems_monster" ||
  addedSystemsMonsterCombatant?.source_ref !== "MM:monster:goblin" ||
  addedSystemsMonsterCombatant?.source_label !== "Systems" ||
  addedSystemsMonsterCombatant?.type_label !== "NPC" ||
  addedSystemsMonsterCombatant?.turn_value !== 2 ||
  addedSystemsMonsterCombatant?.initiative_bonus_label !== "+2" ||
  addedSystemsMonsterCombatant?.dexterity_modifier !== 2 ||
  addedSystemsMonsterCombatant?.initiative_priority !== 4 ||
  addedSystemsMonsterCombatant?.current_hp !== 7 ||
  addedSystemsMonsterCombatant?.max_hp !== 7 ||
  addedSystemsMonsterCombatant?.temp_hp !== 0 ||
  addedSystemsMonsterCombatant?.movement_total !== 30 ||
  addedSystemsMonsterCombatant?.movement_remaining !== 30 ||
  addedSystemsMonsterCombatant?.has_action !== true ||
  addedSystemsMonsterCombatant?.has_bonus_action !== true ||
  addedSystemsMonsterCombatant?.has_reaction !== true ||
  addedSystemsMonsterCombatant?.is_current_turn !== false ||
  addedSystemsMonsterCombatant?.npc_resource_counters?.[0]?.resource_key !== "battle-cry" ||
  addedSystemsMonsterCombatant?.npc_resource_counters?.[0]?.label !== "Battle Cry" ||
  addedSystemsMonsterCombatant?.npc_resource_counters?.[0]?.current_value !== 1 ||
  addedSystemsMonsterCombatant?.npc_resource_counters?.[0]?.max_value !== 1 ||
  addedSystemsMonsterCombatant?.npc_resource_counters?.[0]?.reset_label !== "Per day" ||
  addedSystemsMonsterCombatant?.npc_resource_counters?.[0]?.source_label !== "Systems MM" ||
  addedSystemsMonsterCombatant?.npc_resource_notes?.[0]?.label !== "At-will spellcasting" ||
  addedSystemsMonsterCombatant?.npc_resource_notes?.[0]?.note !== "minor illusion, dancing lights" ||
  addedSystemsMonsterCombatant?.npc_resource_notes?.[0]?.source_label !== "Systems MM" ||
  addedSystemsMonsterCombatant?.npc_resource_notes?.[1]?.label !== "Snare Net" ||
  addedSystemsMonsterCombatant?.npc_resource_notes?.[1]?.note !== "Recharge 5-6" ||
  addedSystemsMonsterCombatant?.npc_resource_notes?.[1]?.source_label !== "Systems MM"
) {
  throw new Error(`Unexpected combat Systems monster add payload: ${JSON.stringify(addSystemsMonsterCombatState.payload)}`);
}

const combatSystemsMonsterAddAssertionDb = new Database(dbPath, { readonly: true });
const addedSystemsMonsterRow = combatSystemsMonsterAddAssertionDb
  .prepare(
    `
      SELECT
        id,
        combatant_type,
        character_slug,
        player_detail_visible,
        source_kind,
        source_ref,
        display_name,
        turn_value,
        initiative_bonus,
        dexterity_modifier,
        initiative_priority,
        current_hp,
        max_hp,
        temp_hp,
        movement_total,
        movement_remaining,
        has_action,
        has_bonus_action,
        has_reaction,
        revision,
        created_by_user_id,
        updated_by_user_id
      FROM campaign_combatants
      WHERE campaign_slug = ?
        AND display_name = ?
        AND source_kind = ?
    `,
  )
  .get("linden-pass", "Goblin", "systems_monster");
const addedSystemsMonsterCounterRows = combatSystemsMonsterAddAssertionDb
  .prepare(
    `
      SELECT resource_key, label, current_value, max_value, reset_label, source_label, created_by_user_id, updated_by_user_id
      FROM campaign_combatant_resource_counters
      WHERE combatant_id = ?
      ORDER BY id ASC
    `,
  )
  .all(addedSystemsMonsterRow?.id || -1);
const addedSystemsMonsterNoteRows = combatSystemsMonsterAddAssertionDb
  .prepare(
    `
      SELECT label, note, source_label, created_by_user_id
      FROM campaign_combatant_resource_notes
      WHERE combatant_id = ?
      ORDER BY id ASC
    `,
  )
  .all(addedSystemsMonsterRow?.id || -1);
const trackerAfterSystemsMonsterAdd = combatSystemsMonsterAddAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatSystemsMonsterAddAssertionDb.close();
if (
  addedSystemsMonsterRow?.combatant_type !== "npc" ||
  addedSystemsMonsterRow?.character_slug !== null ||
  addedSystemsMonsterRow?.player_detail_visible !== 0 ||
  addedSystemsMonsterRow?.source_kind !== "systems_monster" ||
  addedSystemsMonsterRow?.source_ref !== "MM:monster:goblin" ||
  addedSystemsMonsterRow?.display_name !== "Goblin" ||
  addedSystemsMonsterRow?.turn_value !== 2 ||
  addedSystemsMonsterRow?.initiative_bonus !== 2 ||
  addedSystemsMonsterRow?.dexterity_modifier !== 2 ||
  addedSystemsMonsterRow?.initiative_priority !== 4 ||
  addedSystemsMonsterRow?.current_hp !== 7 ||
  addedSystemsMonsterRow?.max_hp !== 7 ||
  addedSystemsMonsterRow?.temp_hp !== 0 ||
  addedSystemsMonsterRow?.movement_total !== 30 ||
  addedSystemsMonsterRow?.movement_remaining !== 30 ||
  addedSystemsMonsterRow?.has_action !== 1 ||
  addedSystemsMonsterRow?.has_bonus_action !== 1 ||
  addedSystemsMonsterRow?.has_reaction !== 1 ||
  addedSystemsMonsterRow?.revision !== 1 ||
  addedSystemsMonsterRow?.created_by_user_id !== 77 ||
  addedSystemsMonsterRow?.updated_by_user_id !== 77 ||
  addedSystemsMonsterCounterRows.length !== 1 ||
  addedSystemsMonsterCounterRows[0]?.resource_key !== "battle-cry" ||
  addedSystemsMonsterCounterRows[0]?.label !== "Battle Cry" ||
  addedSystemsMonsterCounterRows[0]?.current_value !== 1 ||
  addedSystemsMonsterCounterRows[0]?.max_value !== 1 ||
  addedSystemsMonsterCounterRows[0]?.reset_label !== "Per day" ||
  addedSystemsMonsterCounterRows[0]?.source_label !== "Systems MM" ||
  addedSystemsMonsterCounterRows[0]?.created_by_user_id !== 77 ||
  addedSystemsMonsterCounterRows[0]?.updated_by_user_id !== 77 ||
  addedSystemsMonsterNoteRows.length !== 2 ||
  addedSystemsMonsterNoteRows[0]?.label !== "At-will spellcasting" ||
  addedSystemsMonsterNoteRows[0]?.note !== "minor illusion, dancing lights" ||
  addedSystemsMonsterNoteRows[0]?.source_label !== "Systems MM" ||
  addedSystemsMonsterNoteRows[0]?.created_by_user_id !== 77 ||
  addedSystemsMonsterNoteRows[1]?.label !== "Snare Net" ||
  addedSystemsMonsterNoteRows[1]?.note !== "Recharge 5-6" ||
  addedSystemsMonsterNoteRows[1]?.source_label !== "Systems MM" ||
  addedSystemsMonsterNoteRows[1]?.created_by_user_id !== 77 ||
  trackerAfterSystemsMonsterAdd?.round_number !== 1 ||
  trackerAfterSystemsMonsterAdd?.current_combatant_id !== null ||
  trackerAfterSystemsMonsterAdd?.revision !== 20
) {
  throw new Error(
    `Unexpected combat Systems monster add database rows: ${JSON.stringify({
      addedSystemsMonsterRow,
      addedSystemsMonsterCounterRows,
      addedSystemsMonsterNoteRows,
      trackerAfterSystemsMonsterAdd,
    })}`,
  );
}

const addedSystemsMonsterCombatantId = Number(addedSystemsMonsterRow?.id || 0);

const fixtureTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { turn_value: "21" } },
);
if (
  fixtureTurnUpdateCombatState.status !== 403 ||
  fixtureTurnUpdateCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat turn update forbidden 403, got ${fixtureTurnUpdateCombatState.status} ${fixtureTurnUpdateCombatState.payload?.error?.code}`,
  );
}

const playerTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { turn_value: "21" } },
);
if (playerTurnUpdateCombatState.status !== 403 || playerTurnUpdateCombatState.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat turn update forbidden 403, got ${playerTurnUpdateCombatState.status} ${playerTurnUpdateCombatState.payload?.error?.code}`,
  );
}

const missingCampaignTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { turn_value: "21" } },
);
if (
  missingCampaignTurnUpdateCombatState.status !== 404 ||
  missingCampaignTurnUpdateCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat turn update campaign JSON 404, got ${missingCampaignTurnUpdateCombatState.status} ${missingCampaignTurnUpdateCombatState.payload?.error?.code}`,
  );
}

const malformedTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: "{" },
);
if (
  malformedTurnUpdateCombatState.status !== 400 ||
  malformedTurnUpdateCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat turn update validation_error 400, got ${malformedTurnUpdateCombatState.status} ${malformedTurnUpdateCombatState.payload?.error?.code}`,
  );
}

const missingTurnUpdateCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/turn",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { turn_value: "21" } },
);
if (
  missingTurnUpdateCombatState.status !== 400 ||
  missingTurnUpdateCombatState.payload?.error?.code !== "validation_error" ||
  missingTurnUpdateCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combat turn update validation_error 400, got ${missingTurnUpdateCombatState.status} ${JSON.stringify(missingTurnUpdateCombatState.payload)}`,
  );
}

const invalidTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { turn_value: "soon" } },
);
if (
  invalidTurnUpdateCombatState.status !== 400 ||
  invalidTurnUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidTurnUpdateCombatState.payload?.error?.message !== "Turn value must be a whole number."
) {
  throw new Error(
    `Expected invalid combat turn value validation_error 400, got ${invalidTurnUpdateCombatState.status} ${JSON.stringify(invalidTurnUpdateCombatState.payload)}`,
  );
}

const invalidPriorityTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { initiative_priority: "0" } },
);
if (
  invalidPriorityTurnUpdateCombatState.status !== 400 ||
  invalidPriorityTurnUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidPriorityTurnUpdateCombatState.payload?.error?.message !== "Priority must be 1 or higher."
) {
  throw new Error(
    `Expected invalid combat turn priority validation_error 400, got ${invalidPriorityTurnUpdateCombatState.status} ${JSON.stringify(invalidPriorityTurnUpdateCombatState.payload)}`,
  );
}

const staleTurnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { expected_combatant_revision: 999, turn_value: "21" } },
);
if (
  staleTurnUpdateCombatState.status !== 409 ||
  staleTurnUpdateCombatState.payload?.error?.code !== "state_conflict" ||
  staleTurnUpdateCombatState.payload?.error?.message !==
    "This combatant changed in another combat view. Refresh and try again."
) {
  throw new Error(
    `Expected stale combat turn update state_conflict 409, got ${staleTurnUpdateCombatState.status} ${JSON.stringify(staleTurnUpdateCombatState.payload)}`,
  );
}

const turnUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/turn`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { expected_combatant_revision: 1, turn_value: "21", initiative_priority: "2" } },
);
if (
  turnUpdateCombatState.status !== 200 ||
  turnUpdateCombatState.payload?.ok !== true ||
  turnUpdateCombatState.payload?.changed !== true ||
  turnUpdateCombatState.payload?.live_revision !== 21 ||
  turnUpdateCombatState.payload?.tracker?.round_number !== 1 ||
  turnUpdateCombatState.payload?.tracker?.current_turn_label !== "" ||
  turnUpdateCombatState.payload?.tracker?.has_current_turn !== false ||
  turnUpdateCombatState.payload?.selected_combatant_id !== addedSystemsMonsterCombatantId ||
  turnUpdateCombatState.payload?.selected_combatant?.name !== "Goblin" ||
  turnUpdateCombatState.payload?.selected_combatant?.turn_value !== 21 ||
  turnUpdateCombatState.payload?.selected_combatant?.initiative_priority !== 2 ||
  turnUpdateCombatState.payload?.selected_combatant?.combatant_revision !== 2 ||
  turnUpdateCombatState.payload?.selected_player_character?.name !== "Arden March"
) {
  throw new Error(`Unexpected combat turn update payload: ${JSON.stringify(turnUpdateCombatState.payload)}`);
}

const combatTurnUpdateAssertionDb = new Database(dbPath, { readonly: true });
const updatedSystemsMonsterRow = combatTurnUpdateAssertionDb
  .prepare(
    `
      SELECT turn_value, initiative_priority, revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedSystemsMonsterCombatantId);
const trackerAfterTurnUpdate = combatTurnUpdateAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatTurnUpdateAssertionDb.close();
if (
  updatedSystemsMonsterRow?.turn_value !== 21 ||
  updatedSystemsMonsterRow?.initiative_priority !== 2 ||
  updatedSystemsMonsterRow?.revision !== 2 ||
  updatedSystemsMonsterRow?.updated_by_user_id !== 77 ||
  trackerAfterTurnUpdate?.round_number !== 1 ||
  trackerAfterTurnUpdate?.current_combatant_id !== null ||
  trackerAfterTurnUpdate?.revision !== 21
) {
  throw new Error(
    `Unexpected combat turn update database rows: ${JSON.stringify({
      updatedSystemsMonsterRow,
      trackerAfterTurnUpdate,
    })}`,
  );
}

const fixtureVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { current_hp: "5" } },
);
if (
  fixtureVitalsUpdateCombatState.status !== 403 ||
  fixtureVitalsUpdateCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat vitals update forbidden 403, got ${fixtureVitalsUpdateCombatState.status} ${fixtureVitalsUpdateCombatState.payload?.error?.code}`,
  );
}

const playerNpcVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { current_hp: "5" } },
);
if (
  playerNpcVitalsUpdateCombatState.status !== 403 ||
  playerNpcVitalsUpdateCombatState.payload?.error?.code !== "forbidden" ||
  playerNpcVitalsUpdateCombatState.payload?.error?.message !== "You do not have permission to edit this combatant."
) {
  throw new Error(
    `Expected player combat NPC vitals update forbidden 403, got ${playerNpcVitalsUpdateCombatState.status} ${JSON.stringify(playerNpcVitalsUpdateCombatState.payload)}`,
  );
}

const missingCampaignVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { current_hp: "5" } },
);
if (
  missingCampaignVitalsUpdateCombatState.status !== 404 ||
  missingCampaignVitalsUpdateCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat vitals update campaign JSON 404, got ${missingCampaignVitalsUpdateCombatState.status} ${missingCampaignVitalsUpdateCombatState.payload?.error?.code}`,
  );
}

const malformedVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: "{" },
);
if (
  malformedVitalsUpdateCombatState.status !== 400 ||
  malformedVitalsUpdateCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat vitals update validation_error 400, got ${malformedVitalsUpdateCombatState.status} ${malformedVitalsUpdateCombatState.payload?.error?.code}`,
  );
}

const missingVitalsUpdateCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/vitals",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { current_hp: "5" } },
);
if (
  missingVitalsUpdateCombatState.status !== 400 ||
  missingVitalsUpdateCombatState.payload?.error?.code !== "validation_error" ||
  missingVitalsUpdateCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combat vitals update validation_error 400, got ${missingVitalsUpdateCombatState.status} ${JSON.stringify(missingVitalsUpdateCombatState.payload)}`,
  );
}

const invalidVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { current_hp: "soon" } },
);
if (
  invalidVitalsUpdateCombatState.status !== 400 ||
  invalidVitalsUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidVitalsUpdateCombatState.payload?.error?.message !== "Current HP must be a whole number."
) {
  throw new Error(
    `Expected invalid combat vitals current HP validation_error 400, got ${invalidVitalsUpdateCombatState.status} ${JSON.stringify(invalidVitalsUpdateCombatState.payload)}`,
  );
}

const invalidVitalsCeilingCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { current_hp: "12", max_hp: "7" } },
);
if (
  invalidVitalsCeilingCombatState.status !== 400 ||
  invalidVitalsCeilingCombatState.payload?.error?.code !== "validation_error" ||
  invalidVitalsCeilingCombatState.payload?.error?.message !== "Current HP cannot exceed max HP."
) {
  throw new Error(
    `Expected combat vitals HP ceiling validation_error 400, got ${invalidVitalsCeilingCombatState.status} ${JSON.stringify(invalidVitalsCeilingCombatState.payload)}`,
  );
}

const staleNpcVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { expected_combatant_revision: 999, current_hp: "5" } },
);
if (
  staleNpcVitalsUpdateCombatState.status !== 409 ||
  staleNpcVitalsUpdateCombatState.payload?.error?.code !== "state_conflict" ||
  staleNpcVitalsUpdateCombatState.payload?.error?.message !==
    "This combatant changed in another combat view. Refresh and try again."
) {
  throw new Error(
    `Expected stale combat NPC vitals update state_conflict 409, got ${staleNpcVitalsUpdateCombatState.status} ${JSON.stringify(staleNpcVitalsUpdateCombatState.payload)}`,
  );
}

const npcVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/vitals`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 2,
      current_hp: "5",
      max_hp: "11",
      temp_hp: "3",
      movement_total: "20",
    },
  },
);
if (
  npcVitalsUpdateCombatState.status !== 200 ||
  npcVitalsUpdateCombatState.payload?.ok !== true ||
  npcVitalsUpdateCombatState.payload?.changed !== true ||
  npcVitalsUpdateCombatState.payload?.live_revision !== 22 ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.id !== addedSystemsMonsterCombatantId ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.current_hp !== 5 ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.max_hp !== 11 ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.temp_hp !== 3 ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.movement_total !== 20 ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.movement_remaining !== 20 ||
  npcVitalsUpdateCombatState.payload?.selected_combatant?.combatant_revision !== 3
) {
  throw new Error(`Unexpected combat NPC vitals update payload: ${JSON.stringify(npcVitalsUpdateCombatState.payload)}`);
}

const combatNpcVitalsAssertionDb = new Database(dbPath, { readonly: true });
const updatedSystemsMonsterVitalsRow = combatNpcVitalsAssertionDb
  .prepare(
    `
      SELECT current_hp, max_hp, temp_hp, movement_total, movement_remaining, revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedSystemsMonsterCombatantId);
const trackerAfterNpcVitalsUpdate = combatNpcVitalsAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatNpcVitalsAssertionDb.close();
if (
  updatedSystemsMonsterVitalsRow?.current_hp !== 5 ||
  updatedSystemsMonsterVitalsRow?.max_hp !== 11 ||
  updatedSystemsMonsterVitalsRow?.temp_hp !== 3 ||
  updatedSystemsMonsterVitalsRow?.movement_total !== 20 ||
  updatedSystemsMonsterVitalsRow?.movement_remaining !== 20 ||
  updatedSystemsMonsterVitalsRow?.revision !== 3 ||
  updatedSystemsMonsterVitalsRow?.updated_by_user_id !== 77 ||
  trackerAfterNpcVitalsUpdate?.round_number !== 1 ||
  trackerAfterNpcVitalsUpdate?.current_combatant_id !== null ||
  trackerAfterNpcVitalsUpdate?.revision !== 22
) {
  throw new Error(
    `Unexpected combat NPC vitals update database rows: ${JSON.stringify({
      updatedSystemsMonsterVitalsRow,
      trackerAfterNpcVitalsUpdate,
    })}`,
  );
}

const stalePlayerVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedPlayerCombatantId}/vitals`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, current_hp: "34", temp_hp: "2" } },
);
if (
  stalePlayerVitalsUpdateCombatState.status !== 409 ||
  stalePlayerVitalsUpdateCombatState.payload?.error?.code !== "state_conflict" ||
  stalePlayerVitalsUpdateCombatState.payload?.error?.message !==
    "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale combat player vitals update state_conflict 409, got ${stalePlayerVitalsUpdateCombatState.status} ${JSON.stringify(stalePlayerVitalsUpdateCombatState.payload)}`,
  );
}

const playerVitalsUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedPlayerCombatantId}/vitals`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 8, current_hp: "34", temp_hp: "2" } },
);
const playerVitalsCombatant = playerVitalsUpdateCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.character_slug === "arden-march",
);
if (
  playerVitalsUpdateCombatState.status !== 200 ||
  playerVitalsUpdateCombatState.payload?.ok !== true ||
  playerVitalsUpdateCombatState.payload?.changed !== true ||
  playerVitalsUpdateCombatState.payload?.live_revision !== 23 ||
  playerVitalsCombatant?.id !== addedPlayerCombatantId ||
  playerVitalsCombatant?.current_hp !== 34 ||
  playerVitalsCombatant?.max_hp !== 38 ||
  playerVitalsCombatant?.temp_hp !== 2 ||
  playerVitalsCombatant?.state_revision !== 9 ||
  playerVitalsCombatant?.combatant_revision !== 2 ||
  playerVitalsUpdateCombatState.payload?.selected_player_character !== null ||
  (playerVitalsUpdateCombatState.payload?.player_character_targets || []).length !== 0
) {
  throw new Error(`Unexpected combat player vitals update payload: ${JSON.stringify(playerVitalsUpdateCombatState.payload)}`);
}

const combatPlayerVitalsAssertionDb = new Database(dbPath, { readonly: true });
const updatedArdenStateRow = combatPlayerVitalsAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", "arden-march");
const updatedArdenCombatantRow = combatPlayerVitalsAssertionDb
  .prepare(
    `
      SELECT current_hp, max_hp, temp_hp, movement_total, movement_remaining, revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedPlayerCombatantId);
const trackerAfterPlayerVitalsUpdate = combatPlayerVitalsAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatPlayerVitalsAssertionDb.close();
const updatedArdenState = JSON.parse(updatedArdenStateRow?.state_json || "{}");
if (
  updatedArdenStateRow?.revision !== 9 ||
  updatedArdenStateRow?.updated_by_user_id !== 79 ||
  updatedArdenState?.vitals?.current_hp !== 34 ||
  updatedArdenState?.vitals?.temp_hp !== 2 ||
  updatedArdenState?.vitals?.death_saves?.successes !== 0 ||
  updatedArdenState?.hit_dice?.pools?.[0]?.current !== 2 ||
  updatedArdenCombatantRow?.current_hp !== 34 ||
  updatedArdenCombatantRow?.max_hp !== 38 ||
  updatedArdenCombatantRow?.temp_hp !== 2 ||
  updatedArdenCombatantRow?.movement_total !== 30 ||
  updatedArdenCombatantRow?.movement_remaining !== 30 ||
  updatedArdenCombatantRow?.revision !== 2 ||
  updatedArdenCombatantRow?.updated_by_user_id !== 79 ||
  trackerAfterPlayerVitalsUpdate?.round_number !== 1 ||
  trackerAfterPlayerVitalsUpdate?.current_combatant_id !== null ||
  trackerAfterPlayerVitalsUpdate?.revision !== 23
) {
  throw new Error(
    `Unexpected combat player vitals update database rows: ${JSON.stringify({
      updatedArdenStateRow,
      updatedArdenState,
      updatedArdenCombatantRow,
      trackerAfterPlayerVitalsUpdate,
    })}`,
  );
}

const fixtureResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { movement_remaining: "7" } },
);
if (
  fixtureResourcesUpdateCombatState.status !== 403 ||
  fixtureResourcesUpdateCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat resources update forbidden 403, got ${fixtureResourcesUpdateCombatState.status} ${fixtureResourcesUpdateCombatState.payload?.error?.code}`,
  );
}

const playerNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { movement_remaining: "7" } },
);
if (
  playerNpcResourcesUpdateCombatState.status !== 403 ||
  playerNpcResourcesUpdateCombatState.payload?.error?.code !== "forbidden" ||
  playerNpcResourcesUpdateCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combat NPC resources update forbidden 403, got ${playerNpcResourcesUpdateCombatState.status} ${JSON.stringify(playerNpcResourcesUpdateCombatState.payload)}`,
  );
}

const missingCampaignResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { movement_remaining: "7" } },
);
if (
  missingCampaignResourcesUpdateCombatState.status !== 404 ||
  missingCampaignResourcesUpdateCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat resources update campaign JSON 404, got ${missingCampaignResourcesUpdateCombatState.status} ${missingCampaignResourcesUpdateCombatState.payload?.error?.code}`,
  );
}

const malformedResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: "{" },
);
if (
  malformedResourcesUpdateCombatState.status !== 400 ||
  malformedResourcesUpdateCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat resources update validation_error 400, got ${malformedResourcesUpdateCombatState.status} ${malformedResourcesUpdateCombatState.payload?.error?.code}`,
  );
}

const missingResourcesUpdateCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/resources",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { movement_remaining: "7" } },
);
if (
  missingResourcesUpdateCombatState.status !== 400 ||
  missingResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  missingResourcesUpdateCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combat resources update validation_error 400, got ${missingResourcesUpdateCombatState.status} ${JSON.stringify(missingResourcesUpdateCombatState.payload)}`,
  );
}

const invalidBooleanResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { has_action: "maybe" } },
);
if (
  invalidBooleanResourcesUpdateCombatState.status !== 400 ||
  invalidBooleanResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidBooleanResourcesUpdateCombatState.payload?.error?.message !== "has_action must be true or false."
) {
  throw new Error(
    `Expected invalid combat resources boolean validation_error 400, got ${invalidBooleanResourcesUpdateCombatState.status} ${JSON.stringify(invalidBooleanResourcesUpdateCombatState.payload)}`,
  );
}

const invalidMovementResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { movement_remaining: "far" } },
);
if (
  invalidMovementResourcesUpdateCombatState.status !== 400 ||
  invalidMovementResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidMovementResourcesUpdateCombatState.payload?.error?.message !== "Remaining movement must be a whole number."
) {
  throw new Error(
    `Expected invalid combat resources movement validation_error 400, got ${invalidMovementResourcesUpdateCombatState.status} ${JSON.stringify(invalidMovementResourcesUpdateCombatState.payload)}`,
  );
}

const highMovementResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { movement_remaining: "99" } },
);
if (
  highMovementResourcesUpdateCombatState.status !== 400 ||
  highMovementResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  highMovementResourcesUpdateCombatState.payload?.error?.message !==
    "Remaining movement cannot exceed total movement."
) {
  throw new Error(
    `Expected high combat resources movement validation_error 400, got ${highMovementResourcesUpdateCombatState.status} ${JSON.stringify(highMovementResourcesUpdateCombatState.payload)}`,
  );
}

const staleResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { expected_combatant_revision: 999, movement_remaining: "7" } },
);
if (
  staleResourcesUpdateCombatState.status !== 409 ||
  staleResourcesUpdateCombatState.payload?.error?.code !== "state_conflict" ||
  staleResourcesUpdateCombatState.payload?.error?.message !==
    "This combatant changed in another combat view. Refresh and try again."
) {
  throw new Error(
    `Expected stale combat resources update state_conflict 409, got ${staleResourcesUpdateCombatState.status} ${JSON.stringify(staleResourcesUpdateCombatState.payload)}`,
  );
}

const npcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 3,
      movement_remaining: "7",
      has_action: false,
      has_bonus_action: "true",
      has_reaction: false,
    },
  },
);
if (
  npcResourcesUpdateCombatState.status !== 200 ||
  npcResourcesUpdateCombatState.payload?.ok !== true ||
  npcResourcesUpdateCombatState.payload?.changed !== true ||
  npcResourcesUpdateCombatState.payload?.live_revision !== 24 ||
  npcResourcesUpdateCombatState.payload?.selected_combatant?.id !== addedSystemsMonsterCombatantId ||
  npcResourcesUpdateCombatState.payload?.selected_combatant?.movement_remaining !== 7 ||
  npcResourcesUpdateCombatState.payload?.selected_combatant?.has_action !== false ||
  npcResourcesUpdateCombatState.payload?.selected_combatant?.has_bonus_action !== true ||
  npcResourcesUpdateCombatState.payload?.selected_combatant?.has_reaction !== false ||
  npcResourcesUpdateCombatState.payload?.selected_combatant?.combatant_revision !== 4
) {
  throw new Error(`Unexpected combat NPC resources update payload: ${JSON.stringify(npcResourcesUpdateCombatState.payload)}`);
}

const combatNpcResourcesAssertionDb = new Database(dbPath, { readonly: true });
const updatedSystemsMonsterResourcesRow = combatNpcResourcesAssertionDb
  .prepare(
    `
      SELECT has_action, has_bonus_action, has_reaction, movement_remaining, revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedSystemsMonsterCombatantId);
const trackerAfterNpcResourcesUpdate = combatNpcResourcesAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatNpcResourcesAssertionDb.close();
if (
  updatedSystemsMonsterResourcesRow?.has_action !== 0 ||
  updatedSystemsMonsterResourcesRow?.has_bonus_action !== 1 ||
  updatedSystemsMonsterResourcesRow?.has_reaction !== 0 ||
  updatedSystemsMonsterResourcesRow?.movement_remaining !== 7 ||
  updatedSystemsMonsterResourcesRow?.revision !== 4 ||
  updatedSystemsMonsterResourcesRow?.updated_by_user_id !== 77 ||
  trackerAfterNpcResourcesUpdate?.round_number !== 1 ||
  trackerAfterNpcResourcesUpdate?.current_combatant_id !== null ||
  trackerAfterNpcResourcesUpdate?.revision !== 24
) {
  throw new Error(
    `Unexpected combat NPC resources update database rows: ${JSON.stringify({
      updatedSystemsMonsterResourcesRow,
      trackerAfterNpcResourcesUpdate,
    })}`,
  );
}

const playerResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedPlayerCombatantId}/resources`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 2,
      movement_remaining: "11",
      has_action: true,
      has_bonus_action: false,
      has_reaction: true,
    },
  },
);
const playerResourcesCombatant = playerResourcesUpdateCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.character_slug === "arden-march",
);
if (
  playerResourcesUpdateCombatState.status !== 200 ||
  playerResourcesUpdateCombatState.payload?.ok !== true ||
  playerResourcesUpdateCombatState.payload?.changed !== true ||
  playerResourcesUpdateCombatState.payload?.live_revision !== 25 ||
  playerResourcesCombatant?.id !== addedPlayerCombatantId ||
  playerResourcesCombatant?.movement_remaining !== 11 ||
  playerResourcesCombatant?.has_action !== true ||
  playerResourcesCombatant?.has_bonus_action !== false ||
  playerResourcesCombatant?.has_reaction !== true ||
  playerResourcesCombatant?.combatant_revision !== 3 ||
  playerResourcesCombatant?.state_revision !== 9
) {
  throw new Error(`Unexpected combat player resources update payload: ${JSON.stringify(playerResourcesUpdateCombatState.payload)}`);
}

const combatPlayerResourcesAssertionDb = new Database(dbPath, { readonly: true });
const updatedArdenResourcesRow = combatPlayerResourcesAssertionDb
  .prepare(
    `
      SELECT has_action, has_bonus_action, has_reaction, movement_remaining, revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedPlayerCombatantId);
const ardenStateAfterResources = combatPlayerResourcesAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", "arden-march");
const trackerAfterPlayerResourcesUpdate = combatPlayerResourcesAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatPlayerResourcesAssertionDb.close();
if (
  updatedArdenResourcesRow?.has_action !== 1 ||
  updatedArdenResourcesRow?.has_bonus_action !== 0 ||
  updatedArdenResourcesRow?.has_reaction !== 1 ||
  updatedArdenResourcesRow?.movement_remaining !== 11 ||
  updatedArdenResourcesRow?.revision !== 3 ||
  updatedArdenResourcesRow?.updated_by_user_id !== 79 ||
  ardenStateAfterResources?.revision !== 9 ||
  ardenStateAfterResources?.updated_by_user_id !== 79 ||
  trackerAfterPlayerResourcesUpdate?.round_number !== 1 ||
  trackerAfterPlayerResourcesUpdate?.current_combatant_id !== null ||
  trackerAfterPlayerResourcesUpdate?.revision !== 25
) {
  throw new Error(
    `Unexpected combat player resources update database rows: ${JSON.stringify({
      updatedArdenResourcesRow,
      ardenStateAfterResources,
      trackerAfterPlayerResourcesUpdate,
    })}`,
  );
}

const blockedSessionVitalsUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/arden-march/session/vitals",
  {},
  { method: "PATCH", body: { expected_revision: 9, current_hp: "31" } },
);
if (blockedSessionVitalsUpdate.status !== 401 || blockedSessionVitalsUpdate.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated character session vitals PATCH 401, got ${blockedSessionVitalsUpdate.status} ${blockedSessionVitalsUpdate.payload?.error?.code}`,
  );
}

const fixtureSessionVitalsUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/arden-march/session/vitals",
  {
    "X-CPW-Fixture-Role": "player",
  },
  { method: "PATCH", body: { expected_revision: 9, current_hp: "31" } },
);
if (
  fixtureSessionVitalsUpdate.status !== 403 ||
  fixtureSessionVitalsUpdate.payload?.error?.message !== "Character session state writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture character session vitals PATCH bearer requirement, got ${fixtureSessionVitalsUpdate.status} ${JSON.stringify(fixtureSessionVitalsUpdate.payload)}`,
  );
}

const unassignedPlayerSessionVitalsUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/selene-brook/session/vitals",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 1, current_hp: "31" } },
);
if (
  unassignedPlayerSessionVitalsUpdate.status !== 403 ||
  unassignedPlayerSessionVitalsUpdate.payload?.error?.message !==
    "You do not have permission to update this character from this view."
) {
  throw new Error(
    `Expected unassigned player character session vitals PATCH forbidden, got ${unassignedPlayerSessionVitalsUpdate.status} ${JSON.stringify(unassignedPlayerSessionVitalsUpdate.payload)}`,
  );
}

const staleSessionVitalsUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/arden-march/session/vitals",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, current_hp: "31" } },
);
if (
  staleSessionVitalsUpdate.status !== 409 ||
  staleSessionVitalsUpdate.payload?.error?.code !== "state_conflict" ||
  staleSessionVitalsUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale character session vitals PATCH conflict, got ${staleSessionVitalsUpdate.status} ${JSON.stringify(staleSessionVitalsUpdate.payload)}`,
  );
}

const playerSessionVitalsUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/arden-march/session/vitals",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_revision: 9,
      current_hp: "31",
      hp_delta: "-2",
      temp_hp: "6",
      temp_hp_delta: "1",
      hit_dice_current: { d6: "4" },
    },
  },
);
if (
  playerSessionVitalsUpdate.status !== 200 ||
  playerSessionVitalsUpdate.payload?.ok !== true ||
  playerSessionVitalsUpdate.payload?.character?.definition?.character_slug !== "arden-march" ||
  playerSessionVitalsUpdate.payload?.character?.state_record?.revision !== 10 ||
  playerSessionVitalsUpdate.payload?.character?.state_record?.state?.vitals?.current_hp !== 29 ||
  playerSessionVitalsUpdate.payload?.character?.state_record?.state?.vitals?.temp_hp !== 7 ||
  playerSessionVitalsUpdate.payload?.character?.state_record?.state?.hit_dice?.pools?.[0]?.faces !== 6 ||
  playerSessionVitalsUpdate.payload?.character?.state_record?.state?.hit_dice?.pools?.[0]?.current !== 4 ||
  playerSessionVitalsUpdate.payload?.character?.state_record?.state?.hit_dice?.pools?.[0]?.max !== 5
) {
  throw new Error(`Unexpected character session vitals PATCH payload: ${JSON.stringify(playerSessionVitalsUpdate.payload)}`);
}

const dndXianxiaActiveStateUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/arden-march/session/xianxia-active-state",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_revision: 10,
      active_stance_name: "Forbidden Stance",
      active_aura_name: "Forbidden Aura",
    },
  },
);
if (
  dndXianxiaActiveStateUpdate.status !== 400 ||
  dndXianxiaActiveStateUpdate.payload?.error?.code !== "validation_error" ||
  dndXianxiaActiveStateUpdate.payload?.error?.message !==
    "Active Stance and Aura state is only supported for Xianxia characters."
) {
  throw new Error(
    `Expected DND Xianxia active-state PATCH validation_error, got ${dndXianxiaActiveStateUpdate.status} ${JSON.stringify(dndXianxiaActiveStateUpdate.payload)}`,
  );
}

const sessionVitalsAssertionDb = new Database(dbPath, { readonly: true });
const ardenStateAfterSessionVitals = sessionVitalsAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", "arden-march");
sessionVitalsAssertionDb.close();
const ardenSessionVitalsState = JSON.parse(ardenStateAfterSessionVitals?.state_json || "{}");
if (
  ardenStateAfterSessionVitals?.revision !== 10 ||
  ardenStateAfterSessionVitals?.updated_by_user_id !== 79 ||
  ardenSessionVitalsState?.vitals?.current_hp !== 29 ||
  ardenSessionVitalsState?.vitals?.temp_hp !== 7 ||
  ardenSessionVitalsState?.hit_dice?.pools?.[0]?.faces !== 6 ||
  ardenSessionVitalsState?.hit_dice?.pools?.[0]?.current !== 4 ||
  ardenSessionVitalsState?.hit_dice?.pools?.[0]?.max !== 5
) {
  throw new Error(
    `Unexpected character session vitals database row: ${JSON.stringify({
      ardenStateAfterSessionVitals,
      ardenSessionVitalsState,
    })}`,
  );
}

const missingCharacterSessionVitalsUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/missing-character/session/vitals",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 1, current_hp: "1" } },
);
if (
  missingCharacterSessionVitalsUpdate.status !== 404 ||
  missingCharacterSessionVitalsUpdate.payload?.error?.code !== "content_character_not_found"
) {
  throw new Error(
    `Expected missing character session vitals PATCH JSON 404, got ${missingCharacterSessionVitalsUpdate.status} ${JSON.stringify(missingCharacterSessionVitalsUpdate.payload)}`,
  );
}

const fixtureNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "0" }] } },
);
if (
  fixtureNpcResourcesUpdateCombatState.status !== 403 ||
  fixtureNpcResourcesUpdateCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat NPC resources update forbidden 403, got ${fixtureNpcResourcesUpdateCombatState.status} ${fixtureNpcResourcesUpdateCombatState.payload?.error?.code}`,
  );
}

const playerNpcCounterResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "0" }] } },
);
if (
  playerNpcCounterResourcesUpdateCombatState.status !== 403 ||
  playerNpcCounterResourcesUpdateCombatState.payload?.error?.code !== "forbidden" ||
  playerNpcCounterResourcesUpdateCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combat NPC counter resources update forbidden 403, got ${playerNpcCounterResourcesUpdateCombatState.status} ${JSON.stringify(playerNpcCounterResourcesUpdateCombatState.payload)}`,
  );
}

const missingCampaignNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "0" }] } },
);
if (
  missingCampaignNpcResourcesUpdateCombatState.status !== 404 ||
  missingCampaignNpcResourcesUpdateCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat NPC resources update campaign JSON 404, got ${missingCampaignNpcResourcesUpdateCombatState.status} ${missingCampaignNpcResourcesUpdateCombatState.payload?.error?.code}`,
  );
}

const malformedNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: "{" },
);
if (
  malformedNpcResourcesUpdateCombatState.status !== 400 ||
  malformedNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat NPC resources update validation_error 400, got ${malformedNpcResourcesUpdateCombatState.status} ${malformedNpcResourcesUpdateCombatState.payload?.error?.code}`,
  );
}

const missingNpcResourcesUpdateCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/npc-resources",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "0" }] } },
);
if (
  missingNpcResourcesUpdateCombatState.status !== 400 ||
  missingNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  missingNpcResourcesUpdateCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combat NPC resources update validation_error 400, got ${missingNpcResourcesUpdateCombatState.status} ${JSON.stringify(missingNpcResourcesUpdateCombatState.payload)}`,
  );
}

const playerCharacterNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedPlayerCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "0" }] } },
);
if (
  playerCharacterNpcResourcesUpdateCombatState.status !== 400 ||
  playerCharacterNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  playerCharacterNpcResourcesUpdateCombatState.payload?.error?.message !== "Only NPC source resources can be edited here."
) {
  throw new Error(
    `Expected player-character combat NPC resources update validation_error 400, got ${playerCharacterNpcResourcesUpdateCombatState.status} ${JSON.stringify(playerCharacterNpcResourcesUpdateCombatState.payload)}`,
  );
}

const manualNpcNoCountersResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${Number(addedNpcRow?.id || 0)}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "0" }] } },
);
if (
  manualNpcNoCountersResourcesUpdateCombatState.status !== 400 ||
  manualNpcNoCountersResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  manualNpcNoCountersResourcesUpdateCombatState.payload?.error?.message !==
    "This NPC has no supported source-backed resource counters."
) {
  throw new Error(
    `Expected manual NPC resources update validation_error 400, got ${manualNpcNoCountersResourcesUpdateCombatState.status} ${JSON.stringify(manualNpcNoCountersResourcesUpdateCombatState.payload)}`,
  );
}

const nonListNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: { resource_key: "battle-cry", current_value: "0" } } },
);
if (
  nonListNpcResourcesUpdateCombatState.status !== 400 ||
  nonListNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  nonListNpcResourcesUpdateCombatState.payload?.error?.message !== "NPC resource counters must be sent as a list."
) {
  throw new Error(
    `Expected non-list combat NPC resources validation_error 400, got ${nonListNpcResourcesUpdateCombatState.status} ${JSON.stringify(nonListNpcResourcesUpdateCombatState.payload)}`,
  );
}

const emptyNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [] } },
);
if (
  emptyNpcResourcesUpdateCombatState.status !== 400 ||
  emptyNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  emptyNpcResourcesUpdateCombatState.payload?.error?.message !== "Choose at least one NPC resource counter to update."
) {
  throw new Error(
    `Expected empty combat NPC resources validation_error 400, got ${emptyNpcResourcesUpdateCombatState.status} ${JSON.stringify(emptyNpcResourcesUpdateCombatState.payload)}`,
  );
}

const nonObjectNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: ["battle-cry"] } },
);
if (
  nonObjectNpcResourcesUpdateCombatState.status !== 400 ||
  nonObjectNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  nonObjectNpcResourcesUpdateCombatState.payload?.error?.message !== "NPC resource row 1 must be an object."
) {
  throw new Error(
    `Expected non-object combat NPC resources validation_error 400, got ${nonObjectNpcResourcesUpdateCombatState.status} ${JSON.stringify(nonObjectNpcResourcesUpdateCombatState.payload)}`,
  );
}

const invalidKeyNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "missing", current_value: "0" }] } },
);
if (
  invalidKeyNpcResourcesUpdateCombatState.status !== 400 ||
  invalidKeyNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidKeyNpcResourcesUpdateCombatState.payload?.error?.message !== "Choose a valid NPC resource counter."
) {
  throw new Error(
    `Expected invalid-key combat NPC resources validation_error 400, got ${invalidKeyNpcResourcesUpdateCombatState.status} ${JSON.stringify(invalidKeyNpcResourcesUpdateCombatState.payload)}`,
  );
}

const invalidValueNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "many" }] } },
);
if (
  invalidValueNpcResourcesUpdateCombatState.status !== 400 ||
  invalidValueNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  invalidValueNpcResourcesUpdateCombatState.payload?.error?.message !== "Battle Cry current value must be a whole number."
) {
  throw new Error(
    `Expected invalid-value combat NPC resources validation_error 400, got ${invalidValueNpcResourcesUpdateCombatState.status} ${JSON.stringify(invalidValueNpcResourcesUpdateCombatState.payload)}`,
  );
}

const highValueNpcResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { counters: [{ resource_key: "battle-cry", current_value: "2" }] } },
);
if (
  highValueNpcResourcesUpdateCombatState.status !== 400 ||
  highValueNpcResourcesUpdateCombatState.payload?.error?.code !== "validation_error" ||
  highValueNpcResourcesUpdateCombatState.payload?.error?.message !== "Battle Cry cannot exceed 1."
) {
  throw new Error(
    `Expected high-value combat NPC resources validation_error 400, got ${highValueNpcResourcesUpdateCombatState.status} ${JSON.stringify(highValueNpcResourcesUpdateCombatState.payload)}`,
  );
}

const staleNpcCounterResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 999,
      counters: [{ resource_key: "battle-cry", current_value: "0" }],
    },
  },
);
if (
  staleNpcCounterResourcesUpdateCombatState.status !== 409 ||
  staleNpcCounterResourcesUpdateCombatState.payload?.error?.code !== "state_conflict" ||
  staleNpcCounterResourcesUpdateCombatState.payload?.error?.message !==
    "This combatant changed in another combat view. Refresh and try again."
) {
  throw new Error(
    `Expected stale combat NPC resources update state_conflict 409, got ${staleNpcCounterResourcesUpdateCombatState.status} ${JSON.stringify(staleNpcCounterResourcesUpdateCombatState.payload)}`,
  );
}

const npcCounterResourcesUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/npc-resources`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 4,
      counters: [{ resource_key: "battle-cry", current_value: "0" }],
    },
  },
);
if (
  npcCounterResourcesUpdateCombatState.status !== 200 ||
  npcCounterResourcesUpdateCombatState.payload?.ok !== true ||
  npcCounterResourcesUpdateCombatState.payload?.changed !== true ||
  npcCounterResourcesUpdateCombatState.payload?.live_revision !== 26 ||
  npcCounterResourcesUpdateCombatState.payload?.selected_combatant?.id !== addedSystemsMonsterCombatantId ||
  npcCounterResourcesUpdateCombatState.payload?.selected_combatant?.combatant_revision !== 5 ||
  npcCounterResourcesUpdateCombatState.payload?.selected_combatant?.npc_resource_counters?.[0]?.resource_key !==
    "battle-cry" ||
  npcCounterResourcesUpdateCombatState.payload?.selected_combatant?.npc_resource_counters?.[0]?.current_value !== 0
) {
  throw new Error(`Unexpected combat NPC counter resources update payload: ${JSON.stringify(npcCounterResourcesUpdateCombatState.payload)}`);
}

const combatNpcCounterResourcesAssertionDb = new Database(dbPath, { readonly: true });
const updatedSystemsMonsterNpcResourcesRow = combatNpcCounterResourcesAssertionDb
  .prepare(
    `
      SELECT revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedSystemsMonsterCombatantId);
const updatedSystemsMonsterCounterRow = combatNpcCounterResourcesAssertionDb
  .prepare(
    `
      SELECT current_value, updated_by_user_id
      FROM campaign_combatant_resource_counters
      WHERE combatant_id = ? AND resource_key = ?
    `,
  )
  .get(addedSystemsMonsterCombatantId, "battle-cry");
const trackerAfterNpcCounterResourcesUpdate = combatNpcCounterResourcesAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatNpcCounterResourcesAssertionDb.close();
if (
  updatedSystemsMonsterNpcResourcesRow?.revision !== 5 ||
  updatedSystemsMonsterNpcResourcesRow?.updated_by_user_id !== 77 ||
  updatedSystemsMonsterCounterRow?.current_value !== 0 ||
  updatedSystemsMonsterCounterRow?.updated_by_user_id !== 77 ||
  trackerAfterNpcCounterResourcesUpdate?.round_number !== 1 ||
  trackerAfterNpcCounterResourcesUpdate?.current_combatant_id !== null ||
  trackerAfterNpcCounterResourcesUpdate?.revision !== 26
) {
  throw new Error(
    `Unexpected combat NPC counter resources update database rows: ${JSON.stringify({
      updatedSystemsMonsterNpcResourcesRow,
      updatedSystemsMonsterCounterRow,
      trackerAfterNpcCounterResourcesUpdate,
    })}`,
  );
}

const fixturePlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { player_detail_visible: true } },
);
if (
  fixturePlayerDetailVisibilityCombatState.status !== 403 ||
  fixturePlayerDetailVisibilityCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat player detail visibility forbidden 403, got ${fixturePlayerDetailVisibilityCombatState.status} ${fixturePlayerDetailVisibilityCombatState.payload?.error?.code}`,
  );
}

const playerPlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { player_detail_visible: true } },
);
if (
  playerPlayerDetailVisibilityCombatState.status !== 403 ||
  playerPlayerDetailVisibilityCombatState.payload?.error?.code !== "forbidden" ||
  playerPlayerDetailVisibilityCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combat player detail visibility forbidden 403, got ${playerPlayerDetailVisibilityCombatState.status} ${JSON.stringify(playerPlayerDetailVisibilityCombatState.payload)}`,
  );
}

const missingCampaignPlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { player_detail_visible: true } },
);
if (
  missingCampaignPlayerDetailVisibilityCombatState.status !== 404 ||
  missingCampaignPlayerDetailVisibilityCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat player detail visibility campaign JSON 404, got ${missingCampaignPlayerDetailVisibilityCombatState.status} ${missingCampaignPlayerDetailVisibilityCombatState.payload?.error?.code}`,
  );
}

const missingCombatantPlayerDetailVisibilityCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/player-detail-visibility",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { player_detail_visible: true } },
);
if (
  missingCombatantPlayerDetailVisibilityCombatState.status !== 400 ||
  missingCombatantPlayerDetailVisibilityCombatState.payload?.error?.code !== "validation_error" ||
  missingCombatantPlayerDetailVisibilityCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combat player detail visibility validation_error 400, got ${missingCombatantPlayerDetailVisibilityCombatState.status} ${JSON.stringify(missingCombatantPlayerDetailVisibilityCombatState.payload)}`,
  );
}

const playerCharacterPlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedPlayerCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { player_detail_visible: true } },
);
if (
  playerCharacterPlayerDetailVisibilityCombatState.status !== 400 ||
  playerCharacterPlayerDetailVisibilityCombatState.payload?.error?.code !== "validation_error" ||
  playerCharacterPlayerDetailVisibilityCombatState.payload?.error?.message !==
    "Only NPC combatants can toggle player-facing detail visibility."
) {
  throw new Error(
    `Expected player-character combat player detail visibility validation_error 400, got ${playerCharacterPlayerDetailVisibilityCombatState.status} ${JSON.stringify(playerCharacterPlayerDetailVisibilityCombatState.payload)}`,
  );
}

const missingFlagPlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: {} },
);
if (
  missingFlagPlayerDetailVisibilityCombatState.status !== 400 ||
  missingFlagPlayerDetailVisibilityCombatState.payload?.error?.code !== "validation_error" ||
  missingFlagPlayerDetailVisibilityCombatState.payload?.error?.message !==
    "player_detail_visible must be true or false."
) {
  throw new Error(
    `Expected missing-flag combat player detail visibility validation_error 400, got ${missingFlagPlayerDetailVisibilityCombatState.status} ${JSON.stringify(missingFlagPlayerDetailVisibilityCombatState.payload)}`,
  );
}

const invalidFlagPlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { player_detail_visible: "sometimes" } },
);
if (
  invalidFlagPlayerDetailVisibilityCombatState.status !== 400 ||
  invalidFlagPlayerDetailVisibilityCombatState.payload?.error?.code !== "validation_error" ||
  invalidFlagPlayerDetailVisibilityCombatState.payload?.error?.message !==
    "player_detail_visible must be true or false."
) {
  throw new Error(
    `Expected invalid-flag combat player detail visibility validation_error 400, got ${invalidFlagPlayerDetailVisibilityCombatState.status} ${JSON.stringify(invalidFlagPlayerDetailVisibilityCombatState.payload)}`,
  );
}

const stalePlayerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 999,
      player_detail_visible: true,
    },
  },
);
if (
  stalePlayerDetailVisibilityCombatState.status !== 409 ||
  stalePlayerDetailVisibilityCombatState.payload?.error?.code !== "state_conflict" ||
  stalePlayerDetailVisibilityCombatState.payload?.error?.message !==
    "This combatant changed in another combat view. Refresh and try again."
) {
  throw new Error(
    `Expected stale combat player detail visibility state_conflict 409, got ${stalePlayerDetailVisibilityCombatState.status} ${JSON.stringify(stalePlayerDetailVisibilityCombatState.payload)}`,
  );
}

const playerDetailVisibilityCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/player-detail-visibility`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_combatant_revision: 5,
      player_detail_visible: true,
    },
  },
);
if (
  playerDetailVisibilityCombatState.status !== 200 ||
  playerDetailVisibilityCombatState.payload?.ok !== true ||
  playerDetailVisibilityCombatState.payload?.changed !== true ||
  playerDetailVisibilityCombatState.payload?.live_revision !== 27 ||
  playerDetailVisibilityCombatState.payload?.selected_combatant?.id !== addedSystemsMonsterCombatantId ||
  playerDetailVisibilityCombatState.payload?.selected_combatant?.combatant_revision !== 6 ||
  playerDetailVisibilityCombatState.payload?.selected_combatant?.player_detail_visible !== true
) {
  throw new Error(`Unexpected combat player detail visibility payload: ${JSON.stringify(playerDetailVisibilityCombatState.payload)}`);
}

const combatPlayerDetailVisibilityAssertionDb = new Database(dbPath, { readonly: true });
const updatedSystemsMonsterPlayerDetailRow = combatPlayerDetailVisibilityAssertionDb
  .prepare(
    `
      SELECT player_detail_visible, revision, updated_by_user_id
      FROM campaign_combatants
      WHERE id = ?
    `,
  )
  .get(addedSystemsMonsterCombatantId);
const trackerAfterPlayerDetailVisibility = combatPlayerDetailVisibilityAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision, updated_by_user_id FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatPlayerDetailVisibilityAssertionDb.close();
if (
  updatedSystemsMonsterPlayerDetailRow?.player_detail_visible !== 1 ||
  updatedSystemsMonsterPlayerDetailRow?.revision !== 6 ||
  updatedSystemsMonsterPlayerDetailRow?.updated_by_user_id !== 77 ||
  trackerAfterPlayerDetailVisibility?.round_number !== 1 ||
  trackerAfterPlayerDetailVisibility?.current_combatant_id !== null ||
  trackerAfterPlayerDetailVisibility?.revision !== 27 ||
  trackerAfterPlayerDetailVisibility?.updated_by_user_id !== 77
) {
  throw new Error(
    `Unexpected combat player detail visibility database rows: ${JSON.stringify({
      updatedSystemsMonsterPlayerDetailRow,
      trackerAfterPlayerDetailVisibility,
    })}`,
  );
}

const fixtureConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "POST", body: { name: "Dazed", duration_text: "Until end of next turn" } },
);
if (
  fixtureConditionCreateCombatState.status !== 403 ||
  fixtureConditionCreateCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat condition create forbidden 403, got ${fixtureConditionCreateCombatState.status} ${fixtureConditionCreateCombatState.payload?.error?.code}`,
  );
}

const playerConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST", body: { name: "Dazed", duration_text: "Until end of next turn" } },
);
if (
  playerConditionCreateCombatState.status !== 403 ||
  playerConditionCreateCombatState.payload?.error?.code !== "forbidden" ||
  playerConditionCreateCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combat condition create forbidden 403, got ${playerConditionCreateCombatState.status} ${JSON.stringify(playerConditionCreateCombatState.payload)}`,
  );
}

const missingCampaignConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { name: "Dazed", duration_text: "Until end of next turn" } },
);
if (
  missingCampaignConditionCreateCombatState.status !== 404 ||
  missingCampaignConditionCreateCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat condition create campaign JSON 404, got ${missingCampaignConditionCreateCombatState.status} ${missingCampaignConditionCreateCombatState.payload?.error?.code}`,
  );
}

const malformedConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: "{" },
);
if (
  malformedConditionCreateCombatState.status !== 400 ||
  malformedConditionCreateCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat condition create validation_error 400, got ${malformedConditionCreateCombatState.status} ${malformedConditionCreateCombatState.payload?.error?.code}`,
  );
}

const missingCombatantConditionCreateCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999/conditions",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { name: "Dazed", duration_text: "Until end of next turn" } },
);
if (
  missingCombatantConditionCreateCombatState.status !== 400 ||
  missingCombatantConditionCreateCombatState.payload?.error?.code !== "validation_error" ||
  missingCombatantConditionCreateCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combatant condition create validation_error 400, got ${missingCombatantConditionCreateCombatState.status} ${JSON.stringify(missingCombatantConditionCreateCombatState.payload)}`,
  );
}

const blankConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { name: "   ", duration_text: "Until end of next turn" } },
);
if (
  blankConditionCreateCombatState.status !== 400 ||
  blankConditionCreateCombatState.payload?.error?.code !== "validation_error" ||
  blankConditionCreateCombatState.payload?.error?.message !== "Condition name is required."
) {
  throw new Error(
    `Expected blank combat condition create validation_error 400, got ${blankConditionCreateCombatState.status} ${JSON.stringify(blankConditionCreateCombatState.payload)}`,
  );
}

const longConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { name: "X".repeat(81), duration_text: "Until end of next turn" } },
);
if (
  longConditionCreateCombatState.status !== 400 ||
  longConditionCreateCombatState.payload?.error?.code !== "validation_error" ||
  longConditionCreateCombatState.payload?.error?.message !== "Condition names must stay under 80 characters."
) {
  throw new Error(
    `Expected long-name combat condition create validation_error 400, got ${longConditionCreateCombatState.status} ${JSON.stringify(longConditionCreateCombatState.payload)}`,
  );
}

const longDurationConditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { name: "Dazed", duration_text: "Y".repeat(121) } },
);
if (
  longDurationConditionCreateCombatState.status !== 400 ||
  longDurationConditionCreateCombatState.payload?.error?.code !== "validation_error" ||
  longDurationConditionCreateCombatState.payload?.error?.message !==
    "Condition duration text must stay under 120 characters."
) {
  throw new Error(
    `Expected long-duration combat condition create validation_error 400, got ${longDurationConditionCreateCombatState.status} ${JSON.stringify(longDurationConditionCreateCombatState.payload)}`,
  );
}

const conditionCreateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}/conditions`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "POST", body: { name: "Dazed", duration_text: "Until end of next turn" } },
);
const conditionCreateCombatant = conditionCreateCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.id === addedSystemsMonsterCombatantId,
);
const createdCombatCondition = conditionCreateCombatant?.conditions?.find((condition) => condition.name === "Dazed");
if (
  conditionCreateCombatState.status !== 200 ||
  conditionCreateCombatState.payload?.ok !== true ||
  conditionCreateCombatState.payload?.changed !== true ||
  conditionCreateCombatState.payload?.live_revision !== 28 ||
  conditionCreateCombatant?.id !== addedSystemsMonsterCombatantId ||
  createdCombatCondition?.duration_text !== "Until end of next turn" ||
  typeof createdCombatCondition?.id !== "number"
) {
  throw new Error(`Unexpected combat condition create payload: ${JSON.stringify(conditionCreateCombatState.payload)}`);
}

const createdCombatConditionId = Number(createdCombatCondition.id);
const combatConditionCreateAssertionDb = new Database(dbPath, { readonly: true });
const createdCombatConditionRow = combatConditionCreateAssertionDb
  .prepare(
    `
      SELECT combatant_id, name, duration_text, created_by_user_id
      FROM campaign_combat_conditions
      WHERE id = ?
    `,
  )
  .get(createdCombatConditionId);
const trackerAfterConditionCreate = combatConditionCreateAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision, updated_by_user_id FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatConditionCreateAssertionDb.close();
if (
  createdCombatConditionRow?.combatant_id !== addedSystemsMonsterCombatantId ||
  createdCombatConditionRow?.name !== "Dazed" ||
  createdCombatConditionRow?.duration_text !== "Until end of next turn" ||
  createdCombatConditionRow?.created_by_user_id !== 77 ||
  trackerAfterConditionCreate?.round_number !== 1 ||
  trackerAfterConditionCreate?.current_combatant_id !== null ||
  trackerAfterConditionCreate?.revision !== 28 ||
  trackerAfterConditionCreate?.updated_by_user_id !== 77
) {
  throw new Error(
    `Unexpected combat condition create database rows: ${JSON.stringify({
      createdCombatConditionRow,
      trackerAfterConditionCreate,
    })}`,
  );
}

const fixtureConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { name: "Slowed", duration_text: "1 round" } },
);
if (
  fixtureConditionUpdateCombatState.status !== 403 ||
  fixtureConditionUpdateCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat condition update forbidden 403, got ${fixtureConditionUpdateCombatState.status} ${fixtureConditionUpdateCombatState.payload?.error?.code}`,
  );
}

const playerConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { name: "Slowed", duration_text: "1 round" } },
);
if (
  playerConditionUpdateCombatState.status !== 403 ||
  playerConditionUpdateCombatState.payload?.error?.code !== "forbidden" ||
  playerConditionUpdateCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combat condition update forbidden 403, got ${playerConditionUpdateCombatState.status} ${JSON.stringify(playerConditionUpdateCombatState.payload)}`,
  );
}

const missingCampaignConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { name: "Slowed", duration_text: "1 round" } },
);
if (
  missingCampaignConditionUpdateCombatState.status !== 404 ||
  missingCampaignConditionUpdateCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat condition update campaign JSON 404, got ${missingCampaignConditionUpdateCombatState.status} ${missingCampaignConditionUpdateCombatState.payload?.error?.code}`,
  );
}

const malformedConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: "{" },
);
if (
  malformedConditionUpdateCombatState.status !== 400 ||
  malformedConditionUpdateCombatState.payload?.error?.code !== "validation_error"
) {
  throw new Error(
    `Expected malformed combat condition update validation_error 400, got ${malformedConditionUpdateCombatState.status} ${malformedConditionUpdateCombatState.payload?.error?.code}`,
  );
}

const missingConditionUpdateCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/conditions/999999",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { name: "Slowed", duration_text: "1 round" } },
);
if (
  missingConditionUpdateCombatState.status !== 400 ||
  missingConditionUpdateCombatState.payload?.error?.code !== "validation_error" ||
  missingConditionUpdateCombatState.payload?.error?.message !== "That condition could not be found."
) {
  throw new Error(
    `Expected missing combat condition update validation_error 400, got ${missingConditionUpdateCombatState.status} ${JSON.stringify(missingConditionUpdateCombatState.payload)}`,
  );
}

const blankConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { name: "", duration_text: "1 round" } },
);
if (
  blankConditionUpdateCombatState.status !== 400 ||
  blankConditionUpdateCombatState.payload?.error?.code !== "validation_error" ||
  blankConditionUpdateCombatState.payload?.error?.message !== "Condition name is required."
) {
  throw new Error(
    `Expected blank combat condition update validation_error 400, got ${blankConditionUpdateCombatState.status} ${JSON.stringify(blankConditionUpdateCombatState.payload)}`,
  );
}

const longConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { name: "X".repeat(81), duration_text: "1 round" } },
);
if (
  longConditionUpdateCombatState.status !== 400 ||
  longConditionUpdateCombatState.payload?.error?.code !== "validation_error" ||
  longConditionUpdateCombatState.payload?.error?.message !== "Condition names must stay under 80 characters."
) {
  throw new Error(
    `Expected long-name combat condition update validation_error 400, got ${longConditionUpdateCombatState.status} ${JSON.stringify(longConditionUpdateCombatState.payload)}`,
  );
}

const longDurationConditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { name: "Slowed", duration_text: "Y".repeat(121) } },
);
if (
  longDurationConditionUpdateCombatState.status !== 400 ||
  longDurationConditionUpdateCombatState.payload?.error?.code !== "validation_error" ||
  longDurationConditionUpdateCombatState.payload?.error?.message !==
    "Condition duration text must stay under 120 characters."
) {
  throw new Error(
    `Expected long-duration combat condition update validation_error 400, got ${longDurationConditionUpdateCombatState.status} ${JSON.stringify(longDurationConditionUpdateCombatState.payload)}`,
  );
}

const conditionUpdateCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "PATCH", body: { name: "Slowed", duration_text: "1 round" } },
);
const conditionUpdateCombatant = conditionUpdateCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.id === addedSystemsMonsterCombatantId,
);
const updatedCombatCondition = conditionUpdateCombatant?.conditions?.find(
  (condition) => condition.id === createdCombatConditionId,
);
if (
  conditionUpdateCombatState.status !== 200 ||
  conditionUpdateCombatState.payload?.ok !== true ||
  conditionUpdateCombatState.payload?.changed !== true ||
  conditionUpdateCombatState.payload?.live_revision !== 29 ||
  conditionUpdateCombatant?.id !== addedSystemsMonsterCombatantId ||
  updatedCombatCondition?.name !== "Slowed" ||
  updatedCombatCondition?.duration_text !== "1 round"
) {
  throw new Error(`Unexpected combat condition update payload: ${JSON.stringify(conditionUpdateCombatState.payload)}`);
}

const combatConditionUpdateAssertionDb = new Database(dbPath, { readonly: true });
const updatedCombatConditionRow = combatConditionUpdateAssertionDb
  .prepare(
    `
      SELECT combatant_id, name, duration_text, created_by_user_id
      FROM campaign_combat_conditions
      WHERE id = ?
    `,
  )
  .get(createdCombatConditionId);
const trackerAfterConditionUpdate = combatConditionUpdateAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision, updated_by_user_id FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatConditionUpdateAssertionDb.close();
if (
  updatedCombatConditionRow?.combatant_id !== addedSystemsMonsterCombatantId ||
  updatedCombatConditionRow?.name !== "Slowed" ||
  updatedCombatConditionRow?.duration_text !== "1 round" ||
  updatedCombatConditionRow?.created_by_user_id !== 77 ||
  trackerAfterConditionUpdate?.round_number !== 1 ||
  trackerAfterConditionUpdate?.current_combatant_id !== null ||
  trackerAfterConditionUpdate?.revision !== 29 ||
  trackerAfterConditionUpdate?.updated_by_user_id !== 77
) {
  throw new Error(
    `Unexpected combat condition update database rows: ${JSON.stringify({
      updatedCombatConditionRow,
      trackerAfterConditionUpdate,
    })}`,
  );
}

const fixtureConditionDeleteCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "DELETE" },
);
if (
  fixtureConditionDeleteCombatState.status !== 403 ||
  fixtureConditionDeleteCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combat condition delete forbidden 403, got ${fixtureConditionDeleteCombatState.status} ${fixtureConditionDeleteCombatState.payload?.error?.code}`,
  );
}

const playerConditionDeleteCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "DELETE" },
);
if (
  playerConditionDeleteCombatState.status !== 403 ||
  playerConditionDeleteCombatState.payload?.error?.code !== "forbidden" ||
  playerConditionDeleteCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combat condition delete forbidden 403, got ${playerConditionDeleteCombatState.status} ${JSON.stringify(playerConditionDeleteCombatState.payload)}`,
  );
}

const missingCampaignConditionDeleteCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "DELETE" },
);
if (
  missingCampaignConditionDeleteCombatState.status !== 404 ||
  missingCampaignConditionDeleteCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combat condition delete campaign JSON 404, got ${missingCampaignConditionDeleteCombatState.status} ${missingCampaignConditionDeleteCombatState.payload?.error?.code}`,
  );
}

const missingConditionDeleteCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/conditions/999999",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "DELETE" },
);
if (
  missingConditionDeleteCombatState.status !== 400 ||
  missingConditionDeleteCombatState.payload?.error?.code !== "validation_error" ||
  missingConditionDeleteCombatState.payload?.error?.message !== "That condition could not be found."
) {
  throw new Error(
    `Expected missing combat condition delete validation_error 400, got ${missingConditionDeleteCombatState.status} ${JSON.stringify(missingConditionDeleteCombatState.payload)}`,
  );
}

const conditionDeleteCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/conditions/${createdCombatConditionId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "DELETE" },
);
const conditionDeleteCombatant = conditionDeleteCombatState.payload?.tracker?.combatants?.find(
  (combatant) => combatant.id === addedSystemsMonsterCombatantId,
);
if (
  conditionDeleteCombatState.status !== 200 ||
  conditionDeleteCombatState.payload?.ok !== true ||
  conditionDeleteCombatState.payload?.changed !== true ||
  conditionDeleteCombatState.payload?.live_revision !== 30 ||
  conditionDeleteCombatant?.conditions?.some((condition) => condition.id === createdCombatConditionId)
) {
  throw new Error(`Unexpected combat condition delete payload: ${JSON.stringify(conditionDeleteCombatState.payload)}`);
}

const combatConditionDeleteAssertionDb = new Database(dbPath, { readonly: true });
const deletedCombatConditionRows = combatConditionDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combat_conditions WHERE id = ?")
  .get(createdCombatConditionId);
const trackerAfterConditionDelete = combatConditionDeleteAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision, updated_by_user_id FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatConditionDeleteAssertionDb.close();
if (
  deletedCombatConditionRows?.count !== 0 ||
  trackerAfterConditionDelete?.round_number !== 1 ||
  trackerAfterConditionDelete?.current_combatant_id !== null ||
  trackerAfterConditionDelete?.revision !== 30 ||
  trackerAfterConditionDelete?.updated_by_user_id !== null
) {
  throw new Error(
    `Unexpected combat condition delete database rows: ${JSON.stringify({
      deletedCombatConditionRows,
      trackerAfterConditionDelete,
    })}`,
  );
}

const fixtureCombatantDeleteCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}`,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "DELETE" },
);
if (
  fixtureCombatantDeleteCombatState.status !== 403 ||
  fixtureCombatantDeleteCombatState.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected fixture combatant delete forbidden 403, got ${fixtureCombatantDeleteCombatState.status} ${fixtureCombatantDeleteCombatState.payload?.error?.code}`,
  );
}

const playerCombatantDeleteCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "DELETE" },
);
if (
  playerCombatantDeleteCombatState.status !== 403 ||
  playerCombatantDeleteCombatState.payload?.error?.code !== "forbidden" ||
  playerCombatantDeleteCombatState.payload?.error?.message !== "You do not have permission to manage combat."
) {
  throw new Error(
    `Expected player combatant delete forbidden 403, got ${playerCombatantDeleteCombatState.status} ${JSON.stringify(playerCombatantDeleteCombatState.payload)}`,
  );
}

const missingCampaignCombatantDeleteCombatState = await requestJson(
  `/api/v1/campaigns/definitely-not-a-campaign/combat/combatants/${addedSystemsMonsterCombatantId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "DELETE" },
);
if (
  missingCampaignCombatantDeleteCombatState.status !== 404 ||
  missingCampaignCombatantDeleteCombatState.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing combatant delete campaign JSON 404, got ${missingCampaignCombatantDeleteCombatState.status} ${missingCampaignCombatantDeleteCombatState.payload?.error?.code}`,
  );
}

const missingCombatantDeleteCombatState = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/combatants/999999",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "DELETE" },
);
if (
  missingCombatantDeleteCombatState.status !== 400 ||
  missingCombatantDeleteCombatState.payload?.error?.code !== "validation_error" ||
  missingCombatantDeleteCombatState.payload?.error?.message !== "That combatant could not be found."
) {
  throw new Error(
    `Expected missing combatant delete validation_error 400, got ${missingCombatantDeleteCombatState.status} ${JSON.stringify(missingCombatantDeleteCombatState.payload)}`,
  );
}

const combatantDeleteCombatState = await requestJson(
  `/api/v1/campaigns/linden-pass/combat/combatants/${addedSystemsMonsterCombatantId}`,
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
  { method: "DELETE" },
);
if (
  combatantDeleteCombatState.status !== 200 ||
  combatantDeleteCombatState.payload?.ok !== true ||
  combatantDeleteCombatState.payload?.changed !== true ||
  combatantDeleteCombatState.payload?.live_revision !== 31 ||
  combatantDeleteCombatState.payload?.tracker?.combatant_count !== 3 ||
  combatantDeleteCombatState.payload?.tracker?.combatants?.some(
    (combatant) => combatant.id === addedSystemsMonsterCombatantId,
  )
) {
  throw new Error(`Unexpected combatant delete payload: ${JSON.stringify(combatantDeleteCombatState.payload)}`);
}

const combatantDeleteAssertionDb = new Database(dbPath, { readonly: true });
const deletedCombatantRows = combatantDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combatants WHERE id = ?")
  .get(addedSystemsMonsterCombatantId);
const deletedCombatantConditionRows = combatantDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combat_conditions WHERE combatant_id = ?")
  .get(addedSystemsMonsterCombatantId);
const deletedCombatantCounterRows = combatantDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combatant_resource_counters WHERE combatant_id = ?")
  .get(addedSystemsMonsterCombatantId);
const deletedCombatantNoteRows = combatantDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_combatant_resource_notes WHERE combatant_id = ?")
  .get(addedSystemsMonsterCombatantId);
const trackerAfterCombatantDelete = combatantDeleteAssertionDb
  .prepare("SELECT round_number, current_combatant_id, revision, updated_by_user_id FROM campaign_combat_trackers WHERE campaign_slug = ?")
  .get("linden-pass");
combatantDeleteAssertionDb.close();
if (
  deletedCombatantRows?.count !== 0 ||
  deletedCombatantConditionRows?.count !== 0 ||
  deletedCombatantCounterRows?.count !== 0 ||
  deletedCombatantNoteRows?.count !== 0 ||
  trackerAfterCombatantDelete?.round_number !== 1 ||
  trackerAfterCombatantDelete?.current_combatant_id !== null ||
  trackerAfterCombatantDelete?.revision !== 31 ||
  trackerAfterCombatantDelete?.updated_by_user_id !== null
) {
  throw new Error(
    `Unexpected combatant delete database rows: ${JSON.stringify({
      deletedCombatantRows,
      deletedCombatantConditionRows,
      deletedCombatantCounterRows,
      deletedCombatantNoteRows,
      trackerAfterCombatantDelete,
    })}`,
  );
}

const missingCombatState = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/combat", {
  "X-CPW-Fixture-Role": "dm",
});
if (missingCombatState.status !== 404 || missingCombatState.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing combat state JSON 404, got ${missingCombatState.status} ${missingCombatState.payload?.error?.code}`,
  );
}

const blockedCombatMonsterSearch = await requestJson("/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob");
if (blockedCombatMonsterSearch.status !== 401 || blockedCombatMonsterSearch.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated combat Systems monster search to return auth_required 401, got ${blockedCombatMonsterSearch.status} ${blockedCombatMonsterSearch.payload?.error?.code}`,
  );
}

const playerCombatMonsterSearch = await requestJson("/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob", {
  "X-CPW-Fixture-Role": "player",
});
if (playerCombatMonsterSearch.status !== 403 || playerCombatMonsterSearch.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player combat Systems monster search forbidden 403, got ${playerCombatMonsterSearch.status} ${playerCombatMonsterSearch.payload?.error?.code}`,
  );
}

const bearerPlayerCombatMonsterSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
);
if (
  bearerPlayerCombatMonsterSearch.status !== 403 ||
  bearerPlayerCombatMonsterSearch.payload?.error?.code !== "forbidden"
) {
  throw new Error(
    `Expected player bearer combat Systems monster search forbidden 403, got ${bearerPlayerCombatMonsterSearch.status} ${bearerPlayerCombatMonsterSearch.payload?.error?.code}`,
  );
}

const shortCombatMonsterSearch = await requestJson("/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=g", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  shortCombatMonsterSearch.status !== 200 ||
  shortCombatMonsterSearch.payload?.message !== "Type at least 2 letters to search the Systems monster list." ||
  shortCombatMonsterSearch.payload?.results?.length !== 0
) {
  throw new Error(`Unexpected short combat Systems monster search payload: ${JSON.stringify(shortCombatMonsterSearch.payload)}`);
}

const dmCombatMonsterSearch = await requestJson("/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmCombatMonsterSearch.status !== 200 ||
  dmCombatMonsterSearch.payload?.message !== "Found 1 matching monster." ||
  dmCombatMonsterSearch.payload?.results?.length !== 1 ||
  dmCombatMonsterSearch.payload?.results?.[0]?.entry_key !== "MM:monster:goblin" ||
  dmCombatMonsterSearch.payload?.results?.[0]?.title !== "Goblin" ||
  dmCombatMonsterSearch.payload?.results?.[0]?.source_id !== "MM" ||
  dmCombatMonsterSearch.payload?.results?.[0]?.subtitle !== "HP 7 - Speed Walk 30 ft." ||
  dmCombatMonsterSearch.payload?.results?.[0]?.initiative_bonus !== "+2"
) {
  throw new Error(`Unexpected DM combat Systems monster search payload: ${JSON.stringify(dmCombatMonsterSearch.payload)}`);
}

const bearerAdminCombatMonsterSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
);
if (
  bearerAdminCombatMonsterSearch.status !== 200 ||
  bearerAdminCombatMonsterSearch.payload?.message !== "Found 1 matching monster." ||
  bearerAdminCombatMonsterSearch.payload?.results?.[0]?.entry_key !== "MM:monster:goblin"
) {
  throw new Error(
    `Unexpected bearer admin combat Systems monster search payload: ${JSON.stringify(bearerAdminCombatMonsterSearch.payload)}`,
  );
}

const campaignList = await requestJson("/api/v1/campaigns");
if (campaignList.status !== 200) {
  throw new Error(`Expected campaign list endpoint 200, got ${campaignList.status}`);
}
if (!Array.isArray(campaignList.payload?.campaigns) || campaignList.payload.campaigns.length !== 1) {
  throw new Error(`Expected one fixture campaign in list, got ${campaignList.payload?.campaigns?.length}`);
}
if (campaignList.payload.campaigns[0]?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected campaign list to include linden-pass, got ${campaignList.payload.campaigns[0]?.campaign?.slug}`);
}
if (campaignList.payload.campaigns[0]?.role !== "fixture_reader") {
  throw new Error(`Expected fixture_reader campaign list role, got ${campaignList.payload.campaigns[0]?.role}`);
}
if (campaignList.payload?.auth?.mode !== "fixture_read_only") {
  throw new Error(`Expected campaign list fixture auth, got ${campaignList.payload?.auth?.mode}`);
}

const campaign = await requestJson("/api/v1/campaigns/linden-pass");
if (campaign.status !== 200) {
  throw new Error(`Expected campaign endpoint 200, got ${campaign.status}`);
}
if (campaign.payload?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected campaign slug to be linden-pass, got ${campaign.payload?.campaign?.slug}`);
}
if (campaign.payload?.campaign?.systems_library_slug !== "DND-5E") {
  throw new Error(`Expected systems_library_slug to be DND-5E, got ${campaign.payload?.campaign?.systems_library_slug}`);
}
if (campaign.payload?.auth?.mode !== "fixture_read_only") {
  throw new Error(`Expected fixture auth mode, got ${campaign.payload?.auth?.mode}`);
}
if (campaign.payload?.permissions?.can_manage_dm_content !== false) {
  throw new Error("Expected read-only permissions in campaign response.");
}

const campaignHelp = await requestJson("/api/v1/campaigns/linden-pass/help");
if (campaignHelp.status !== 200 || campaignHelp.payload?.ok !== true) {
  throw new Error(`Expected campaign help endpoint 200 ok, got ${campaignHelp.status}`);
}
if (campaignHelp.payload?.viewer_role_label !== "Public visitor") {
  throw new Error(`Expected public visitor help role, got ${campaignHelp.payload?.viewer_role_label}`);
}
if (campaignHelp.payload?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected campaign help campaign slug linden-pass, got ${campaignHelp.payload?.campaign?.slug}`);
}
if (campaignHelp.payload?.available_surface_labels?.join("|") !== "Campaign Home") {
  throw new Error(`Expected public help surface labels to include only Campaign Home, got ${JSON.stringify(campaignHelp.payload?.available_surface_labels)}`);
}
if (campaignHelp.payload?.surfaces?.[0]?.links?.[0]?.href !== "/campaigns/linden-pass") {
  throw new Error(`Expected campaign help Flask campaign link, got ${campaignHelp.payload?.surfaces?.[0]?.links?.[0]?.href}`);
}

const blockedCampaignControl = await requestJson("/api/v1/campaigns/linden-pass/control");
if (blockedCampaignControl.status !== 401 || blockedCampaignControl.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated campaign control to return auth_required 401, got ${blockedCampaignControl.status} ${blockedCampaignControl.payload?.error?.code}`,
  );
}
const playerCampaignControl = await requestJson("/api/v1/campaigns/linden-pass/control", {
  "X-CPW-Fixture-Role": "player",
});
if (playerCampaignControl.status !== 403 || playerCampaignControl.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture player campaign control to return forbidden 403, got ${playerCampaignControl.status} ${playerCampaignControl.payload?.error?.code}`,
  );
}
if (playerCampaignControl.payload?.error?.message !== "You do not have permission to manage campaign visibility.") {
  throw new Error(`Expected campaign-control forbidden message, got ${playerCampaignControl.payload?.error?.message}`);
}
const bearerPlayerCampaignControl = await requestJson("/api/v1/campaigns/linden-pass/control", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (bearerPlayerCampaignControl.status !== 403 || bearerPlayerCampaignControl.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected bearer player campaign control to return forbidden 403, got ${bearerPlayerCampaignControl.status} ${bearerPlayerCampaignControl.payload?.error?.code}`,
  );
}
const dmCampaignControl = await requestJson("/api/v1/campaigns/linden-pass/control", {
  "X-CPW-Fixture-Role": "dm",
});
if (dmCampaignControl.status !== 200 || dmCampaignControl.payload?.ok !== true) {
  throw new Error(`Expected fixture DM campaign control endpoint 200 ok, got ${dmCampaignControl.status}`);
}
if (dmCampaignControl.payload?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected campaign control campaign slug linden-pass, got ${dmCampaignControl.payload?.campaign?.slug}`);
}
if (dmCampaignControl.payload?.links?.gen2_control_url !== "/app-next/campaigns/linden-pass/control") {
  throw new Error(`Expected Gen2 campaign control link, got ${dmCampaignControl.payload?.links?.gen2_control_url}`);
}
if (dmCampaignControl.payload?.can_set_private_visibility !== false) {
  throw new Error(`Expected fixture DM control can_set_private_visibility false, got ${dmCampaignControl.payload?.can_set_private_visibility}`);
}
const controlRowsByScope = Object.fromEntries(
  (dmCampaignControl.payload?.visibility_rows || []).map((row) => [row.scope, row]),
);
if (controlRowsByScope.campaign?.selected_visibility !== "public") {
  throw new Error(`Expected campaign control campaign visibility public, got ${controlRowsByScope.campaign?.selected_visibility}`);
}
if (controlRowsByScope.characters?.effective_visibility !== "dm") {
  throw new Error(`Expected campaign control characters effective visibility dm, got ${controlRowsByScope.characters?.effective_visibility}`);
}
if ((controlRowsByScope.campaign?.choices || []).some((choice) => choice.value === "private")) {
  throw new Error("Expected fixture DM campaign control choices to omit private visibility.");
}
const bearerAdminCampaignControl = await requestJson("/api/v1/campaigns/linden-pass/control", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (bearerAdminCampaignControl.status !== 200 || bearerAdminCampaignControl.payload?.can_set_private_visibility !== true) {
  throw new Error(
    `Expected bearer app-admin campaign control 200 with private visibility permission, got ${bearerAdminCampaignControl.status} ${bearerAdminCampaignControl.payload?.can_set_private_visibility}`,
  );
}
const adminCampaignRow = (bearerAdminCampaignControl.payload?.visibility_rows || []).find((row) => row.scope === "campaign");
if (!adminCampaignRow?.choices?.some((choice) => choice.value === "private")) {
  throw new Error(`Expected bearer app-admin campaign control choices to include private, got ${JSON.stringify(adminCampaignRow?.choices)}`);
}

const blockedCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  {},
  { method: "PATCH", body: { visibility: { campaign: "players" } } },
);
if (
  blockedCampaignControlPatch.status !== 401 ||
  blockedCampaignControlPatch.payload?.error?.code !== "auth_required"
) {
  throw new Error(
    `Expected unauthenticated campaign-control PATCH to return auth_required 401, got ${blockedCampaignControlPatch.status} ${blockedCampaignControlPatch.payload?.error?.code}`,
  );
}
const fixtureCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { "X-CPW-Fixture-Role": "dm" },
  { method: "PATCH", body: { visibility: { campaign: "players" } } },
);
if (
  fixtureCampaignControlPatch.status !== 403 ||
  fixtureCampaignControlPatch.payload?.error?.message !== "Campaign visibility updates require bearer API authentication."
) {
  throw new Error(
    `Expected fixture campaign-control PATCH to require bearer auth, got ${fixtureCampaignControlPatch.status} ${fixtureCampaignControlPatch.payload?.error?.message}`,
  );
}
const invalidCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { visibility: [] } },
);
if (
  invalidCampaignControlPatch.status !== 400 ||
  invalidCampaignControlPatch.payload?.error?.message !== "Visibility settings must be provided as an object."
) {
  throw new Error(
    `Expected campaign-control PATCH visibility-object validation, got ${invalidCampaignControlPatch.status} ${invalidCampaignControlPatch.payload?.error?.message}`,
  );
}
const invalidCampaignVisibilityChoicePatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { visibility: { campaign: null } } },
);
if (
  invalidCampaignVisibilityChoicePatch.status !== 400 ||
  invalidCampaignVisibilityChoicePatch.payload?.error?.message !== "Choose a valid visibility for Campaign."
) {
  throw new Error(
    `Expected campaign-control PATCH invalid campaign visibility validation, got ${invalidCampaignVisibilityChoicePatch.status} ${invalidCampaignVisibilityChoicePatch.payload?.error?.message}`,
  );
}
const playerCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: { visibility: { campaign: "players" } } },
);
if (playerCampaignControlPatch.status !== 403 || playerCampaignControlPatch.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player campaign-control PATCH to return forbidden 403, got ${playerCampaignControlPatch.status} ${playerCampaignControlPatch.payload?.error?.code}`,
  );
}
const dmPrivateCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { visibility: { campaign: "private" } } },
);
if (
  dmPrivateCampaignControlPatch.status !== 400 ||
  dmPrivateCampaignControlPatch.payload?.error?.message !== "Private visibility is reserved for app admins."
) {
  throw new Error(
    `Expected DM campaign-control PATCH private validation, got ${dmPrivateCampaignControlPatch.status} ${dmPrivateCampaignControlPatch.payload?.error?.message}`,
  );
}
const updateCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { visibility: { campaign: "players", wiki: "dm", session: "players" } } },
);
if (updateCampaignControlPatch.status !== 200 || updateCampaignControlPatch.payload?.ok !== true) {
  throw new Error(
    `Expected DM campaign-control PATCH update 200 ok, got ${updateCampaignControlPatch.status} ${JSON.stringify(updateCampaignControlPatch.payload)}`,
  );
}
if ((updateCampaignControlPatch.payload?.changed_scopes || []).join("|") !== "Campaign|Player Wiki") {
  throw new Error(`Expected campaign-control changed scopes Campaign/Player Wiki, got ${JSON.stringify(updateCampaignControlPatch.payload?.changed_scopes)}`);
}
if (updateCampaignControlPatch.payload?.message !== "Updated visibility for Campaign, Player Wiki.") {
  throw new Error(`Expected campaign-control update message, got ${updateCampaignControlPatch.payload?.message}`);
}
const updatedControlRowsByScope = Object.fromEntries(
  (updateCampaignControlPatch.payload?.visibility_rows || []).map((row) => [row.scope, row]),
);
if (updatedControlRowsByScope.campaign?.selected_visibility !== "players") {
  throw new Error(`Expected campaign visibility players after PATCH, got ${updatedControlRowsByScope.campaign?.selected_visibility}`);
}
if (updatedControlRowsByScope.wiki?.selected_visibility !== "dm") {
  throw new Error(`Expected wiki visibility dm after PATCH, got ${updatedControlRowsByScope.wiki?.selected_visibility}`);
}
if (updatedControlRowsByScope.session?.effective_visibility !== "players") {
  throw new Error(`Expected session effective visibility players after PATCH, got ${updatedControlRowsByScope.session?.effective_visibility}`);
}
const visibilityAssertionDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const persistedVisibilityRows = visibilityAssertionDb
  .prepare("SELECT scope, visibility, updated_by_user_id FROM campaign_visibility_settings ORDER BY scope ASC")
  .all();
if (
  JSON.stringify(
    persistedVisibilityRows.map((row) => ({
      scope: row.scope,
      visibility: row.visibility,
      updated_by_user_id: row.updated_by_user_id,
    })),
  ) !==
  JSON.stringify([
    { scope: "campaign", visibility: "players", updated_by_user_id: 81 },
    { scope: "wiki", visibility: "dm", updated_by_user_id: 81 },
  ])
) {
  throw new Error(`Expected persisted campaign visibility rows for changed scopes, got ${JSON.stringify(persistedVisibilityRows)}`);
}
const visibilityAuditRows = visibilityAssertionDb
  .prepare("SELECT actor_user_id, campaign_slug, event_type, metadata_json FROM auth_audit_log ORDER BY id ASC")
  .all();
visibilityAssertionDb.close();
if (visibilityAuditRows.length !== 2) {
  throw new Error(`Expected two campaign visibility audit rows, got ${JSON.stringify(visibilityAuditRows)}`);
}
for (const row of visibilityAuditRows) {
  const metadata = JSON.parse(row.metadata_json);
  if (
    row.actor_user_id !== 81 ||
    row.campaign_slug !== "linden-pass" ||
    row.event_type !== "campaign_visibility_updated" ||
    metadata.source !== "campaign_control_api"
  ) {
    throw new Error(`Unexpected campaign visibility audit row: ${JSON.stringify(row)}`);
  }
}
const repeatedCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/control/visibility",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { visibility: { campaign: "players", wiki: "dm", session: "players" } } },
);
if (
  repeatedCampaignControlPatch.status !== 200 ||
  repeatedCampaignControlPatch.payload?.changed_scopes?.length !== 0 ||
  repeatedCampaignControlPatch.payload?.message !== "Visibility settings already matched those values."
) {
  throw new Error(
    `Expected repeated campaign-control PATCH to report no changes, got ${repeatedCampaignControlPatch.status} ${JSON.stringify(repeatedCampaignControlPatch.payload)}`,
  );
}

const contentManagerHeaders = { "X-CPW-Fixture-Role": "dm" };
const bearerContentManagerHeaders = { Authorization: `Bearer ${liveApiToken}` };

const blockedContentConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config");
if (blockedContentConfig.status !== 401 || blockedContentConfig.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated content config to return auth_required 401, got ${blockedContentConfig.status} ${blockedContentConfig.payload?.error?.code}`,
  );
}
const playerContentConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config", {
  "X-CPW-Fixture-Role": "player",
});
if (playerContentConfig.status !== 403 || playerContentConfig.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture player content config to return forbidden 403, got ${playerContentConfig.status} ${playerContentConfig.payload?.error?.code}`,
  );
}
if (playerContentConfig.payload?.error?.message !== "You do not have permission to manage campaign content.") {
  throw new Error(`Expected content-management forbidden message, got ${playerContentConfig.payload?.error?.message}`);
}
const bearerPlayerContentConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (bearerPlayerContentConfig.status !== 403 || bearerPlayerContentConfig.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected bearer player content config to return forbidden 403, got ${bearerPlayerContentConfig.status} ${bearerPlayerContentConfig.payload?.error?.code}`,
  );
}
const outsiderContentConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config", {
  Authorization: `Bearer ${outsiderApiToken}`,
});
if (outsiderContentConfig.status !== 403 || outsiderContentConfig.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected bearer outsider content config to return forbidden 403, got ${outsiderContentConfig.status} ${outsiderContentConfig.payload?.error?.code}`,
  );
}

const bearerCampaignConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config", bearerContentManagerHeaders);
if (bearerCampaignConfig.status !== 200 || bearerCampaignConfig.payload?.config_file?.config?.current_session !== 2) {
  throw new Error(
    `Expected bearer app-admin content config endpoint 200 with current_session 2, got ${bearerCampaignConfig.status} ${bearerCampaignConfig.payload?.config_file?.config?.current_session}`,
  );
}

const campaignConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config", contentManagerHeaders);
if (campaignConfig.status !== 200) {
  throw new Error(`Expected content config endpoint 200, got ${campaignConfig.status}`);
}
if (campaignConfig.payload?.config_file?.campaign_slug !== "linden-pass") {
  throw new Error(`Expected content config campaign_slug linden-pass, got ${campaignConfig.payload?.config_file?.campaign_slug}`);
}
if (campaignConfig.payload?.config_file?.config?.current_session !== 2) {
  throw new Error(
    `Expected content config current_session 2, got ${campaignConfig.payload?.config_file?.config?.current_session}`,
  );
}
if (campaignConfig.payload?.config_file?.config?.title !== "Echoes of the Alloy Coast") {
  throw new Error(`Expected content config title, got ${campaignConfig.payload?.config_file?.config?.title}`);
}
if (!Array.isArray(campaignConfig.payload?.config_file?.config?.systems_sources)) {
  throw new Error(
    `Expected content config to include systems_sources array, got ${JSON.stringify(campaignConfig.payload?.config_file?.config?.systems_sources)}`,
  );
}
const editableFields = campaignConfig.payload?.config_file?.editable_fields;
const expectedEditableFields = [
  "current_session",
  "source_wiki_root",
  "summary",
  "system",
  "systems_library",
  "title",
];
if (!Array.isArray(editableFields) || editableFields.join("|") !== expectedEditableFields.join("|")) {
  throw new Error(`Expected exact editable fields ${JSON.stringify(expectedEditableFields)}, got ${JSON.stringify(editableFields)}`);
}
if (typeof campaignConfig.payload?.config_file?.updated_at !== "string" || !campaignConfig.payload?.config_file?.updated_at) {
  throw new Error(`Expected non-empty updated_at string, got ${campaignConfig.payload?.config_file?.updated_at}`);
}

const blockedContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  {},
  { method: "PATCH", body: { config: { summary: "Blocked" } } },
);
if (blockedContentConfigPatch.status !== 401 || blockedContentConfigPatch.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated content config PATCH 401, got ${blockedContentConfigPatch.status} ${blockedContentConfigPatch.payload?.error?.code}`,
  );
}

const fixtureContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  contentManagerHeaders,
  { method: "PATCH", body: { config: { summary: "Blocked" } } },
);
if (
  fixtureContentConfigPatch.status !== 403 ||
  fixtureContentConfigPatch.payload?.error?.message !== "Content config writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content config PATCH bearer requirement, got ${fixtureContentConfigPatch.status} ${fixtureContentConfigPatch.payload?.error?.message}`,
  );
}

const bearerPlayerContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PATCH", body: { config: { summary: "Blocked" } } },
);
if (
  bearerPlayerContentConfigPatch.status !== 403 ||
  bearerPlayerContentConfigPatch.payload?.error?.message !== "You do not have permission to manage campaign content."
) {
  throw new Error(
    `Expected bearer player content config PATCH forbidden, got ${bearerPlayerContentConfigPatch.status} ${bearerPlayerContentConfigPatch.payload?.error?.message}`,
  );
}

const invalidJsonContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: "[]" },
);
if (
  invalidJsonContentConfigPatch.status !== 400 ||
  invalidJsonContentConfigPatch.payload?.error?.message !== "Request body must be a JSON object."
) {
  throw new Error(
    `Expected content config PATCH JSON-object validation, got ${invalidJsonContentConfigPatch.status} ${invalidJsonContentConfigPatch.payload?.error?.message}`,
  );
}

const unsupportedContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { config: { hidden_lair: "yes" } } },
);
if (
  unsupportedContentConfigPatch.status !== 400 ||
  unsupportedContentConfigPatch.payload?.error?.message !== "Unsupported campaign config fields: hidden_lair"
) {
  throw new Error(
    `Expected unsupported content config field validation, got ${unsupportedContentConfigPatch.status} ${unsupportedContentConfigPatch.payload?.error?.message}`,
  );
}

const negativeSessionConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { config: { current_session: -1 } } },
);
if (
  negativeSessionConfigPatch.status !== 400 ||
  negativeSessionConfigPatch.payload?.error?.message !== "current_session must be zero or greater."
) {
  throw new Error(
    `Expected negative current_session validation, got ${negativeSessionConfigPatch.status} ${negativeSessionConfigPatch.payload?.error?.message}`,
  );
}

const updatedContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "PATCH",
    body: {
      config: {
        current_session: "3",
        summary: "Updated through the TypeScript API smoke test.",
        system: "xianxia",
        systems_library: "xianxia",
      },
    },
  },
);
if (
  updatedContentConfigPatch.status !== 200 ||
  updatedContentConfigPatch.payload?.config_file?.config?.current_session !== 3 ||
  updatedContentConfigPatch.payload?.config_file?.config?.summary !== "Updated through the TypeScript API smoke test." ||
  updatedContentConfigPatch.payload?.config_file?.config?.system !== "Xianxia" ||
  updatedContentConfigPatch.payload?.config_file?.config?.systems_library !== "Xianxia"
) {
  throw new Error(`Unexpected content config PATCH payload: ${JSON.stringify(updatedContentConfigPatch.payload)}`);
}

const campaignAfterContentConfigPatch = await requestJson("/api/v1/campaigns/linden-pass");
if (
  campaignAfterContentConfigPatch.status !== 200 ||
  campaignAfterContentConfigPatch.payload?.campaign?.current_session !== 3 ||
  campaignAfterContentConfigPatch.payload?.campaign?.system !== "Xianxia" ||
  campaignAfterContentConfigPatch.payload?.campaign?.systems_library_slug !== "Xianxia"
) {
  throw new Error(
    `Expected campaign detail to reflect content config PATCH, got ${JSON.stringify(campaignAfterContentConfigPatch.payload?.campaign)}`,
  );
}

const emptyContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH" },
);
if (
  emptyContentConfigPatch.status !== 200 ||
  emptyContentConfigPatch.payload?.config_file?.config?.current_session !== 3
) {
  throw new Error(`Expected empty content config PATCH to preserve config, got ${JSON.stringify(emptyContentConfigPatch.payload)}`);
}

const restoredContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "PATCH",
    body: {
      config: {
        current_session: 2,
        summary: "A public-safe sample campaign fixture used to verify wiki, session, combat, and character flows.",
        system: "DND 5E",
        systems_library: "DND5E",
      },
    },
  },
);
if (
  restoredContentConfigPatch.status !== 200 ||
  restoredContentConfigPatch.payload?.config_file?.config?.current_session !== 2 ||
  restoredContentConfigPatch.payload?.config_file?.config?.system !== "DND-5E" ||
  restoredContentConfigPatch.payload?.config_file?.config?.systems_library !== "DND-5E"
) {
  throw new Error(`Expected restored content config payload, got ${JSON.stringify(restoredContentConfigPatch.payload)}`);
}

const contentCharacters = await requestJson("/api/v1/campaigns/linden-pass/content/characters", contentManagerHeaders);
if (contentCharacters.status !== 200) {
  throw new Error(`Expected content characters list endpoint 200, got ${contentCharacters.status}`);
}
if (!Array.isArray(contentCharacters.payload?.characters) || contentCharacters.payload.characters.length !== 3) {
  throw new Error(`Expected 3 fixture content characters, got ${contentCharacters.payload?.characters?.length}`);
}
if (contentCharacters.payload.characters.map((item) => item.character_slug).join("|") !== "arden-march|selene-brook|tobin-slate") {
  throw new Error(
    `Expected fixture content characters to be sorted by slug, got ${JSON.stringify(contentCharacters.payload.characters)}`,
  );
}
const ardenSummary = contentCharacters.payload.characters[0];
if (ardenSummary.name !== "Arden March" || ardenSummary.status !== "active" || ardenSummary.import_status !== "clean") {
  throw new Error(`Unexpected Arden content character summary: ${JSON.stringify(ardenSummary)}`);
}
if (typeof ardenSummary.updated_at !== "string" || !ardenSummary.updated_at) {
  throw new Error(`Expected Arden content character summary updated_at, got ${ardenSummary.updated_at}`);
}

const contentCharacter = await requestJson(
  "/api/v1/campaigns/linden-pass/content/characters/arden-march",
  contentManagerHeaders,
);
if (contentCharacter.status !== 200) {
  throw new Error(`Expected content character detail endpoint 200, got ${contentCharacter.status}`);
}
if (contentCharacter.payload?.character_file?.character_slug !== "arden-march") {
  throw new Error(`Expected Arden character detail, got ${contentCharacter.payload?.character_file?.character_slug}`);
}
if (contentCharacter.payload?.character_file?.state_created !== false) {
  throw new Error(`Expected read-only fixture character state_created false, got ${contentCharacter.payload?.character_file?.state_created}`);
}
if (contentCharacter.payload?.character_file?.definition?.system !== "DND-5E") {
  throw new Error(`Expected Arden definition system DND-5E, got ${contentCharacter.payload?.character_file?.definition?.system}`);
}
if (contentCharacter.payload?.character_file?.definition?.proficiencies?.tool_expertise?.length !== 0) {
  throw new Error(
    `Expected Arden definition normalized tool_expertise array, got ${JSON.stringify(contentCharacter.payload?.character_file?.definition?.proficiencies)}`,
  );
}
if (contentCharacter.payload?.character_file?.import_metadata?.parser_version !== "fixture") {
  throw new Error(
    `Expected Arden import metadata parser_version fixture, got ${contentCharacter.payload?.character_file?.import_metadata?.parser_version}`,
  );
}

const missingContentCharacter = await requestJson(
  "/api/v1/campaigns/linden-pass/content/characters/missing-character",
  contentManagerHeaders,
);
if (missingContentCharacter.status !== 404 || missingContentCharacter.payload?.error?.code !== "content_character_not_found") {
  throw new Error(
    `Expected missing content character JSON 404, got ${missingContentCharacter.status} ${missingContentCharacter.payload?.error?.code}`,
  );
}

const managedCharacterSlug = "api-scout";
const managedCharacterPath = `/api/v1/campaigns/linden-pass/content/characters/${managedCharacterSlug}`;
const managedCharacterDefinition = structuredClone(contentCharacter.payload.character_file.definition);
managedCharacterDefinition.name = "API Scout";
managedCharacterDefinition.profile = {
  ...(managedCharacterDefinition.profile || {}),
  biography_markdown: "A remotely managed scout prepared through the TypeScript API.",
};
managedCharacterDefinition.features = [
  ...((Array.isArray(managedCharacterDefinition.features) ? managedCharacterDefinition.features : [])),
  {
    name: "Arcane Armor",
    description_markdown: "Smoke-test Armorer feature state support.",
  },
];
const managedCharacterImportMetadata = structuredClone(contentCharacter.payload.character_file.import_metadata);
managedCharacterImportMetadata.source_path = "api://campaigns/linden-pass/characters/api-scout";
managedCharacterImportMetadata.parser_version = "api-test";
managedCharacterImportMetadata.import_status = "managed";
const managedCharacterBody = {
  definition: managedCharacterDefinition,
  import_metadata: managedCharacterImportMetadata,
};

const blockedContentCharacterPut = await requestJson(
  managedCharacterPath,
  {},
  { method: "PUT", body: managedCharacterBody },
);
if (blockedContentCharacterPut.status !== 401 || blockedContentCharacterPut.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated content character PUT 401, got ${blockedContentCharacterPut.status} ${blockedContentCharacterPut.payload?.error?.code}`,
  );
}

const fixtureContentCharacterPut = await requestJson(
  managedCharacterPath,
  contentManagerHeaders,
  { method: "PUT", body: managedCharacterBody },
);
if (
  fixtureContentCharacterPut.status !== 403 ||
  fixtureContentCharacterPut.payload?.error?.message !== "Content character writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content character PUT bearer requirement, got ${fixtureContentCharacterPut.status} ${fixtureContentCharacterPut.payload?.error?.message}`,
  );
}

const bearerPlayerContentCharacterPut = await requestJson(
  managedCharacterPath,
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PUT", body: managedCharacterBody },
);
if (
  bearerPlayerContentCharacterPut.status !== 403 ||
  bearerPlayerContentCharacterPut.payload?.error?.message !== "You do not have permission to manage campaign content."
) {
  throw new Error(
    `Expected bearer player content character PUT forbidden, got ${bearerPlayerContentCharacterPut.status} ${bearerPlayerContentCharacterPut.payload?.error?.message}`,
  );
}

const invalidContentCharacterPut = await requestJson(
  managedCharacterPath,
  bearerContentManagerHeaders,
  { method: "PUT", body: { definition: [] } },
);
if (
  invalidContentCharacterPut.status !== 400 ||
  invalidContentCharacterPut.payload?.error?.message !== "Character definition must be an object."
) {
  throw new Error(
    `Expected content character PUT definition validation, got ${invalidContentCharacterPut.status} ${invalidContentCharacterPut.payload?.error?.message}`,
  );
}

const missingCampaignContentCharacterPut = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/content/characters/api-scout",
  bearerContentManagerHeaders,
  { method: "PUT", body: managedCharacterBody },
);
if (
  missingCampaignContentCharacterPut.status !== 404 ||
  missingCampaignContentCharacterPut.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing campaign content character PUT 404, got ${missingCampaignContentCharacterPut.status} ${missingCampaignContentCharacterPut.payload?.error?.code}`,
  );
}

const contentCharacterPut = await requestJson(
  managedCharacterPath,
  bearerContentManagerHeaders,
  { method: "PUT", body: managedCharacterBody },
);
if (
  contentCharacterPut.status !== 200 ||
  contentCharacterPut.payload?.character_file?.character_slug !== managedCharacterSlug ||
  contentCharacterPut.payload?.character_file?.definition?.character_slug !== managedCharacterSlug ||
  contentCharacterPut.payload?.character_file?.definition?.name !== "API Scout" ||
  contentCharacterPut.payload?.character_file?.import_metadata?.parser_version !== "api-test" ||
  contentCharacterPut.payload?.character_file?.state_created !== true
) {
  throw new Error(
    `Expected content character PUT payload, got ${contentCharacterPut.status} ${JSON.stringify(contentCharacterPut.payload)}`,
  );
}
const managedCharacterDefinitionPath = path.join(
  campaignsDir,
  "linden-pass",
  "characters",
  managedCharacterSlug,
  "definition.yaml",
);
const managedCharacterImportPath = path.join(
  campaignsDir,
  "linden-pass",
  "characters",
  managedCharacterSlug,
  "import.yaml",
);
if (
  !existsSync(managedCharacterDefinitionPath) ||
  !readFileSync(managedCharacterDefinitionPath, "utf8").includes("API Scout") ||
  !existsSync(managedCharacterImportPath) ||
  !readFileSync(managedCharacterImportPath, "utf8").includes("api-test")
) {
  throw new Error("Expected content character PUT to write definition/import YAML into the copied fixture tree.");
}
const dndStateAssertionDb = new Database(dbPath);
const managedCharacterStateRow = dndStateAssertionDb
  .prepare("SELECT revision, state_json FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
if (!managedCharacterStateRow || managedCharacterStateRow.revision !== 1) {
  dndStateAssertionDb.close();
  throw new Error(`Expected content character PUT to initialize SQLite state, got ${JSON.stringify(managedCharacterStateRow)}`);
}
const managedCharacterState = JSON.parse(managedCharacterStateRow.state_json);
if (
  managedCharacterState.status !== "active" ||
  managedCharacterState.vitals?.temp_hp !== 0 ||
  managedCharacterState.hit_dice?.pools?.[0]?.faces !== 6 ||
  managedCharacterState.hit_dice?.pools?.[0]?.current !== 5 ||
  managedCharacterState.spell_slots?.[0]?.level !== 1 ||
  managedCharacterState.spell_slots?.[0]?.max !== 4 ||
  managedCharacterState.resources?.[0]?.current !== 5
) {
  dndStateAssertionDb.close();
  throw new Error(`Expected initialized character state payload, got ${JSON.stringify(managedCharacterState)}`);
}
const assignmentTimestamp = "2026-06-25T12:30:00+00:00";
dndStateAssertionDb
  .prepare(
    "INSERT INTO character_assignments (user_id, campaign_slug, character_slug, assignment_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
  )
  .run(79, "linden-pass", managedCharacterSlug, "owner", assignmentTimestamp, assignmentTimestamp);
dndStateAssertionDb.close();

const fixtureSessionResourceUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/resources/sorcery-points`,
  {
    "X-CPW-Fixture-Role": "player",
  },
  { method: "PATCH", body: { expected_revision: 1, current: "3" } },
);
if (
  fixtureSessionResourceUpdate.status !== 403 ||
  fixtureSessionResourceUpdate.payload?.error?.message !== "Character session state writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture character session resource PATCH bearer requirement, got ${fixtureSessionResourceUpdate.status} ${JSON.stringify(fixtureSessionResourceUpdate.payload)}`,
  );
}

const staleSessionResourceUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/resources/sorcery-points`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, current: "3" } },
);
if (
  staleSessionResourceUpdate.status !== 409 ||
  staleSessionResourceUpdate.payload?.error?.code !== "state_conflict" ||
  staleSessionResourceUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale character session resource PATCH conflict, got ${staleSessionResourceUpdate.status} ${JSON.stringify(staleSessionResourceUpdate.payload)}`,
  );
}

const missingSessionResourceUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/resources/not-a-resource`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 1, current: "3" } },
);
if (
  missingSessionResourceUpdate.status !== 400 ||
  missingSessionResourceUpdate.payload?.error?.code !== "validation_error" ||
  missingSessionResourceUpdate.payload?.error?.message !== "Unknown resource: not-a-resource"
) {
  throw new Error(
    `Expected missing character session resource PATCH validation_error, got ${missingSessionResourceUpdate.status} ${JSON.stringify(missingSessionResourceUpdate.payload)}`,
  );
}

const playerSessionResourceUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/resources/sorcery-points`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 1, current: "3", delta: "-1" } },
);
if (
  playerSessionResourceUpdate.status !== 200 ||
  playerSessionResourceUpdate.payload?.ok !== true ||
  playerSessionResourceUpdate.payload?.character?.definition?.character_slug !== managedCharacterSlug ||
  playerSessionResourceUpdate.payload?.character?.state_record?.revision !== 2 ||
  playerSessionResourceUpdate.payload?.character?.state_record?.state?.resources?.[0]?.id !== "sorcery-points" ||
  playerSessionResourceUpdate.payload?.character?.state_record?.state?.resources?.[0]?.current !== 2
) {
  throw new Error(`Unexpected character session resource PATCH payload: ${JSON.stringify(playerSessionResourceUpdate.payload)}`);
}

const sessionResourceAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterResource = sessionResourceAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
sessionResourceAssertionDb.close();
const managedResourceState = JSON.parse(managedStateAfterResource?.state_json || "{}");
if (
  managedStateAfterResource?.revision !== 2 ||
  managedStateAfterResource?.updated_by_user_id !== 79 ||
  managedResourceState.resources?.[0]?.id !== "sorcery-points" ||
  managedResourceState.resources?.[0]?.current !== 2
) {
  throw new Error(
    `Unexpected character session resource database row: ${JSON.stringify({
      managedStateAfterResource,
      managedResourceState,
    })}`,
  );
}

const staleSessionSpellSlotsUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/spell-slots/1`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, used: "2" } },
);
if (
  staleSessionSpellSlotsUpdate.status !== 409 ||
  staleSessionSpellSlotsUpdate.payload?.error?.code !== "state_conflict" ||
  staleSessionSpellSlotsUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale character session spell slots PATCH conflict, got ${staleSessionSpellSlotsUpdate.status} ${JSON.stringify(staleSessionSpellSlotsUpdate.payload)}`,
  );
}

const missingSessionSpellSlotsUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/spell-slots/9`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 2, used: "2" } },
);
if (
  missingSessionSpellSlotsUpdate.status !== 400 ||
  missingSessionSpellSlotsUpdate.payload?.error?.code !== "validation_error" ||
  missingSessionSpellSlotsUpdate.payload?.error?.message !== "Unknown spell slot level: 9"
) {
  throw new Error(
    `Expected missing character session spell slots PATCH validation_error, got ${missingSessionSpellSlotsUpdate.status} ${JSON.stringify(missingSessionSpellSlotsUpdate.payload)}`,
  );
}

const playerSessionSpellSlotsUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/spell-slots/1`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 2, slot_lane_id: "main-slots", used: "2", delta_used: "-1" } },
);
if (
  playerSessionSpellSlotsUpdate.status !== 200 ||
  playerSessionSpellSlotsUpdate.payload?.ok !== true ||
  playerSessionSpellSlotsUpdate.payload?.character?.state_record?.revision !== 3 ||
  playerSessionSpellSlotsUpdate.payload?.character?.state_record?.state?.spell_slots?.[0]?.level !== 1 ||
  playerSessionSpellSlotsUpdate.payload?.character?.state_record?.state?.spell_slots?.[0]?.slot_lane_id !== "main-slots" ||
  playerSessionSpellSlotsUpdate.payload?.character?.state_record?.state?.spell_slots?.[0]?.used !== 1
) {
  throw new Error(`Unexpected character session spell slots PATCH payload: ${JSON.stringify(playerSessionSpellSlotsUpdate.payload)}`);
}

const sessionSpellSlotsAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterSpellSlots = sessionSpellSlotsAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
sessionSpellSlotsAssertionDb.close();
const managedSpellSlotsState = JSON.parse(managedStateAfterSpellSlots?.state_json || "{}");
if (
  managedStateAfterSpellSlots?.revision !== 3 ||
  managedStateAfterSpellSlots?.updated_by_user_id !== 79 ||
  managedSpellSlotsState.spell_slots?.[0]?.level !== 1 ||
  managedSpellSlotsState.spell_slots?.[0]?.slot_lane_id !== "main-slots" ||
  managedSpellSlotsState.spell_slots?.[0]?.used !== 1
) {
  throw new Error(
    `Unexpected character session spell slots database row: ${JSON.stringify({
      managedStateAfterSpellSlots,
      managedSpellSlotsState,
    })}`,
  );
}

const missingSessionInventoryUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/inventory/not-an-item`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 3, quantity: "2" } },
);
if (
  missingSessionInventoryUpdate.status !== 400 ||
  missingSessionInventoryUpdate.payload?.error?.code !== "validation_error" ||
  missingSessionInventoryUpdate.payload?.error?.message !== "Unknown inventory item: not-an-item"
) {
  throw new Error(
    `Expected missing character session inventory PATCH validation_error, got ${missingSessionInventoryUpdate.status} ${JSON.stringify(missingSessionInventoryUpdate.payload)}`,
  );
}

const playerSessionInventoryUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/inventory/light-crossbow-1`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 3, quantity: "5", delta: "-2" } },
);
if (
  playerSessionInventoryUpdate.status !== 200 ||
  playerSessionInventoryUpdate.payload?.ok !== true ||
  playerSessionInventoryUpdate.payload?.character?.state_record?.revision !== 4 ||
  playerSessionInventoryUpdate.payload?.character?.state_record?.state?.inventory?.[0]?.id !== "light-crossbow-1" ||
  playerSessionInventoryUpdate.payload?.character?.state_record?.state?.inventory?.[0]?.quantity !== 3
) {
  throw new Error(`Unexpected character session inventory PATCH payload: ${JSON.stringify(playerSessionInventoryUpdate.payload)}`);
}

const sessionInventoryAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterInventory = sessionInventoryAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
sessionInventoryAssertionDb.close();
const managedInventoryState = JSON.parse(managedStateAfterInventory?.state_json || "{}");
if (
  managedStateAfterInventory?.revision !== 4 ||
  managedStateAfterInventory?.updated_by_user_id !== 79 ||
  managedInventoryState.inventory?.[0]?.id !== "light-crossbow-1" ||
  managedInventoryState.inventory?.[0]?.quantity !== 3
) {
  throw new Error(
    `Unexpected character session inventory database row: ${JSON.stringify({
      managedStateAfterInventory,
      managedInventoryState,
    })}`,
  );
}

const staleSessionCurrencyUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/currency`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, gp: "12" } },
);
if (
  staleSessionCurrencyUpdate.status !== 409 ||
  staleSessionCurrencyUpdate.payload?.error?.code !== "state_conflict" ||
  staleSessionCurrencyUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale character session currency PATCH conflict, got ${staleSessionCurrencyUpdate.status} ${JSON.stringify(staleSessionCurrencyUpdate.payload)}`,
  );
}

const managedCurrencyBefore = managedInventoryState.currency || {};
const playerSessionCurrencyUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/currency`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 4, cp: "11", gp: "12", pp: "" } },
);
if (
  playerSessionCurrencyUpdate.status !== 200 ||
  playerSessionCurrencyUpdate.payload?.ok !== true ||
  playerSessionCurrencyUpdate.payload?.character?.state_record?.revision !== 5 ||
  playerSessionCurrencyUpdate.payload?.character?.state_record?.state?.currency?.cp !== 11 ||
  playerSessionCurrencyUpdate.payload?.character?.state_record?.state?.currency?.gp !== 12 ||
  playerSessionCurrencyUpdate.payload?.character?.state_record?.state?.currency?.sp !== (managedCurrencyBefore.sp ?? 0) ||
  playerSessionCurrencyUpdate.payload?.character?.state_record?.state?.currency?.ep !== (managedCurrencyBefore.ep ?? 0) ||
  playerSessionCurrencyUpdate.payload?.character?.state_record?.state?.currency?.pp !== (managedCurrencyBefore.pp ?? 0)
) {
  throw new Error(`Unexpected character session currency PATCH payload: ${JSON.stringify(playerSessionCurrencyUpdate.payload)}`);
}

const sessionCurrencyAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterCurrency = sessionCurrencyAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
sessionCurrencyAssertionDb.close();
const managedCurrencyState = JSON.parse(managedStateAfterCurrency?.state_json || "{}");
if (
  managedStateAfterCurrency?.revision !== 5 ||
  managedStateAfterCurrency?.updated_by_user_id !== 79 ||
  managedCurrencyState.currency?.cp !== 11 ||
  managedCurrencyState.currency?.gp !== 12 ||
  managedCurrencyState.currency?.sp !== (managedCurrencyBefore.sp ?? 0) ||
  managedCurrencyState.currency?.ep !== (managedCurrencyBefore.ep ?? 0) ||
  managedCurrencyState.currency?.pp !== (managedCurrencyBefore.pp ?? 0)
) {
  throw new Error(
    `Unexpected character session currency database row: ${JSON.stringify({
      managedStateAfterCurrency,
      managedCurrencyState,
    })}`,
  );
}

const staleSessionNotesUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/notes`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, player_notes_markdown: "This revision should conflict." } },
);
if (
  staleSessionNotesUpdate.status !== 409 ||
  staleSessionNotesUpdate.payload?.error?.code !== "state_conflict" ||
  staleSessionNotesUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale character session notes PATCH conflict, got ${staleSessionNotesUpdate.status} ${JSON.stringify(staleSessionNotesUpdate.payload)}`,
  );
}

const managedNotesBefore = managedCurrencyState.notes || {};
const managedNoteText = "  Remember the ash-yard contract.\nKeep whitespace.  ";
const playerSessionNotesUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/notes`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 5, player_notes_markdown: managedNoteText } },
);
if (
  playerSessionNotesUpdate.status !== 200 ||
  playerSessionNotesUpdate.payload?.ok !== true ||
  playerSessionNotesUpdate.payload?.character?.state_record?.revision !== 6 ||
  playerSessionNotesUpdate.payload?.character?.state_record?.state?.notes?.player_notes_markdown !== managedNoteText ||
  playerSessionNotesUpdate.payload?.character?.state_record?.state?.notes?.physical_description_markdown !==
    managedNotesBefore.physical_description_markdown ||
  playerSessionNotesUpdate.payload?.character?.state_record?.state?.notes?.background_markdown !==
    managedNotesBefore.background_markdown ||
  JSON.stringify(playerSessionNotesUpdate.payload?.character?.state_record?.state?.notes?.session_notes || []) !==
    JSON.stringify(managedNotesBefore.session_notes || [])
) {
  throw new Error(`Unexpected character session notes PATCH payload: ${JSON.stringify(playerSessionNotesUpdate.payload)}`);
}

const playerSessionNotesClear = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/notes`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 6, player_notes_markdown: null } },
);
if (
  playerSessionNotesClear.status !== 200 ||
  playerSessionNotesClear.payload?.ok !== true ||
  playerSessionNotesClear.payload?.character?.state_record?.revision !== 7 ||
  playerSessionNotesClear.payload?.character?.state_record?.state?.notes?.player_notes_markdown !== ""
) {
  throw new Error(`Unexpected character session notes clear payload: ${JSON.stringify(playerSessionNotesClear.payload)}`);
}

const sessionNotesAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterNotes = sessionNotesAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
sessionNotesAssertionDb.close();
const managedNotesState = JSON.parse(managedStateAfterNotes?.state_json || "{}");
if (
  managedStateAfterNotes?.revision !== 7 ||
  managedStateAfterNotes?.updated_by_user_id !== 79 ||
  managedNotesState.notes?.player_notes_markdown !== "" ||
  managedNotesState.notes?.physical_description_markdown !== managedNotesBefore.physical_description_markdown ||
  managedNotesState.notes?.background_markdown !== managedNotesBefore.background_markdown ||
  JSON.stringify(managedNotesState.notes?.session_notes || []) !== JSON.stringify(managedNotesBefore.session_notes || [])
) {
  throw new Error(
    `Unexpected character session notes database row: ${JSON.stringify({
      managedStateAfterNotes,
      managedNotesState,
    })}`,
  );
}

const staleSessionPersonalUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/personal`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_revision: 999,
      physical_description_markdown: "This revision should conflict.",
      background_markdown: "This revision should conflict.",
    },
  },
);
if (
  staleSessionPersonalUpdate.status !== 409 ||
  staleSessionPersonalUpdate.payload?.error?.code !== "state_conflict" ||
  staleSessionPersonalUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale character session personal PATCH conflict, got ${staleSessionPersonalUpdate.status} ${JSON.stringify(staleSessionPersonalUpdate.payload)}`,
  );
}

const personalPhysical = "Broad-shouldered and steady-eyed.";
const personalBackground = "Spent years running messages along the harbor roads.";
const dmSessionPersonalUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/personal`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_revision: 7,
      physical_description_markdown: personalPhysical,
      background_markdown: personalBackground,
    },
  },
);
if (
  dmSessionPersonalUpdate.status !== 200 ||
  dmSessionPersonalUpdate.payload?.ok !== true ||
  dmSessionPersonalUpdate.payload?.character?.state_record?.revision !== 8 ||
  dmSessionPersonalUpdate.payload?.character?.state_record?.state?.notes?.physical_description_markdown !==
    personalPhysical ||
  dmSessionPersonalUpdate.payload?.character?.state_record?.state?.notes?.background_markdown !== personalBackground ||
  dmSessionPersonalUpdate.payload?.character?.state_record?.state?.notes?.player_notes_markdown !== "" ||
  JSON.stringify(dmSessionPersonalUpdate.payload?.character?.state_record?.state?.notes?.session_notes || []) !==
    JSON.stringify(managedNotesBefore.session_notes || [])
) {
  throw new Error(`Unexpected character session personal PATCH payload: ${JSON.stringify(dmSessionPersonalUpdate.payload)}`);
}

const dmSessionPersonalClear = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/personal`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 8, physical_description_markdown: null, background_markdown: "" } },
);
if (
  dmSessionPersonalClear.status !== 200 ||
  dmSessionPersonalClear.payload?.ok !== true ||
  dmSessionPersonalClear.payload?.character?.state_record?.revision !== 9 ||
  dmSessionPersonalClear.payload?.character?.state_record?.state?.notes?.physical_description_markdown !== "" ||
  dmSessionPersonalClear.payload?.character?.state_record?.state?.notes?.background_markdown !== "" ||
  dmSessionPersonalClear.payload?.character?.state_record?.state?.notes?.player_notes_markdown !== ""
) {
  throw new Error(`Unexpected character session personal clear payload: ${JSON.stringify(dmSessionPersonalClear.payload)}`);
}

const sessionPersonalAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterPersonal = sessionPersonalAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
sessionPersonalAssertionDb.close();
const managedPersonalState = JSON.parse(managedStateAfterPersonal?.state_json || "{}");
if (
  managedStateAfterPersonal?.revision !== 9 ||
  managedStateAfterPersonal?.updated_by_user_id !== 81 ||
  managedPersonalState.notes?.player_notes_markdown !== "" ||
  managedPersonalState.notes?.physical_description_markdown !== "" ||
  managedPersonalState.notes?.background_markdown !== "" ||
  JSON.stringify(managedPersonalState.notes?.session_notes || []) !== JSON.stringify(managedNotesBefore.session_notes || [])
) {
  throw new Error(
    `Unexpected character session personal database row: ${JSON.stringify({
      managedStateAfterPersonal,
      managedPersonalState,
    })}`,
  );
}

const blockedRestPreview = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/rest-preview/long`,
);
if (blockedRestPreview.status !== 401 || blockedRestPreview.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated rest preview auth_required, got ${blockedRestPreview.status} ${JSON.stringify(blockedRestPreview.payload)}`,
  );
}

const blockedRestApply = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/rest/long`,
  {},
  { method: "POST", body: { expected_revision: 9 } },
);
if (blockedRestApply.status !== 401 || blockedRestApply.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated rest apply auth_required, got ${blockedRestApply.status} ${JSON.stringify(blockedRestApply.payload)}`,
  );
}

const noAccessRestPreview = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/rest-preview/long`,
  {
    Authorization: `Bearer ${outsiderApiToken}`,
  },
);
if (
  noAccessRestPreview.status !== 403 ||
  noAccessRestPreview.payload?.error?.code !== "forbidden" ||
  noAccessRestPreview.payload?.error?.message !== "You do not have access to this campaign scope."
) {
  throw new Error(
    `Expected no-access bearer rest preview forbidden, got ${noAccessRestPreview.status} ${JSON.stringify(noAccessRestPreview.payload)}`,
  );
}

const invalidRestPreview = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/rest-preview/overnight`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
);
if (
  invalidRestPreview.status !== 400 ||
  invalidRestPreview.payload?.error?.code !== "validation_error" ||
  invalidRestPreview.payload?.error?.message !== "Unsupported rest type: overnight"
) {
  throw new Error(
    `Expected invalid rest preview validation_error, got ${invalidRestPreview.status} ${JSON.stringify(invalidRestPreview.payload)}`,
  );
}

const dndLongRestPreview = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/rest-preview/long`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
);
if (
  dndLongRestPreview.status !== 200 ||
  dndLongRestPreview.payload?.ok !== true ||
  dndLongRestPreview.payload?.preview?.rest_type !== "long" ||
  dndLongRestPreview.payload?.preview?.label !== "Long Rest" ||
  !Array.isArray(dndLongRestPreview.payload?.preview?.changes) ||
  dndLongRestPreview.payload.preview.changes.length === 0 ||
  typeof dndLongRestPreview.payload?.preview?.adjustments?.current_hp !== "number" ||
  !Array.isArray(dndLongRestPreview.payload?.preview?.adjustments?.hit_dice?.pools) ||
  dndLongRestPreview.payload.preview.adjustments.hit_dice.pools[0]?.faces !== 6
) {
  throw new Error(`Unexpected DND long-rest preview payload: ${JSON.stringify(dndLongRestPreview.payload)}`);
}

const staleDndLongRestApply = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/rest/long`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "POST", body: { expected_revision: 999, current_hp: "17" } },
);
if (
  staleDndLongRestApply.status !== 409 ||
  staleDndLongRestApply.payload?.error?.code !== "state_conflict" ||
  staleDndLongRestApply.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale DND long-rest apply conflict, got ${staleDndLongRestApply.status} ${JSON.stringify(staleDndLongRestApply.payload)}`,
  );
}

const dndLongRestApply = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/rest/long`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  {
    method: "POST",
    body: {
      expected_revision: 9,
      current_hp: "17",
      hit_dice_current: { d6: "3" },
    },
  },
);
if (
  dndLongRestApply.status !== 200 ||
  dndLongRestApply.payload?.ok !== true ||
  dndLongRestApply.payload?.character?.state_record?.revision !== 10 ||
  dndLongRestApply.payload?.character?.state_record?.state?.vitals?.current_hp !== 17 ||
  dndLongRestApply.payload?.character?.state_record?.state?.resources?.[0]?.current !== 5 ||
  dndLongRestApply.payload?.character?.state_record?.state?.spell_slots?.[0]?.used !== 0 ||
  dndLongRestApply.payload?.character?.state_record?.state?.hit_dice?.pools?.[0]?.faces !== 6 ||
  dndLongRestApply.payload?.character?.state_record?.state?.hit_dice?.pools?.[0]?.current !== 3
) {
  throw new Error(`Unexpected DND long-rest apply payload: ${JSON.stringify(dndLongRestApply.payload)}`);
}

const dndRestAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterRest = dndRestAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
dndRestAssertionDb.close();
const managedRestState = JSON.parse(managedStateAfterRest?.state_json || "{}");
if (
  managedStateAfterRest?.revision !== 10 ||
  managedStateAfterRest?.updated_by_user_id !== 79 ||
  managedRestState.vitals?.current_hp !== 17 ||
  managedRestState.resources?.[0]?.current !== 5 ||
  managedRestState.spell_slots?.[0]?.used !== 0 ||
  managedRestState.hit_dice?.pools?.[0]?.current !== 3
) {
  throw new Error(
    `Unexpected DND rest database row: ${JSON.stringify({
      managedStateAfterRest,
      managedRestState,
    })}`,
  );
}

const staleFeatureStateUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/feature-states/arcane-armor`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, enabled: true } },
);
if (
  staleFeatureStateUpdate.status !== 409 ||
  staleFeatureStateUpdate.payload?.error?.code !== "state_conflict" ||
  staleFeatureStateUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale feature-state PATCH conflict, got ${staleFeatureStateUpdate.status} ${JSON.stringify(staleFeatureStateUpdate.payload)}`,
  );
}

const unsupportedFeatureStateUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/feature-states/not-supported`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 10, enabled: true } },
);
if (
  unsupportedFeatureStateUpdate.status !== 400 ||
  unsupportedFeatureStateUpdate.payload?.error?.code !== "validation_error" ||
  unsupportedFeatureStateUpdate.payload?.error?.message !== "Choose a supported feature state to update."
) {
  throw new Error(
    `Expected unsupported feature-state validation_error, got ${unsupportedFeatureStateUpdate.status} ${JSON.stringify(unsupportedFeatureStateUpdate.payload)}`,
  );
}

const missingFeatureOnSheetUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/characters/selene-brook/session/feature-states/arcane-armor",
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 1, enabled: true } },
);
if (
  missingFeatureOnSheetUpdate.status !== 400 ||
  missingFeatureOnSheetUpdate.payload?.error?.code !== "validation_error" ||
  missingFeatureOnSheetUpdate.payload?.error?.message !==
    "Arcane Armor state is only available for Armorer sheets with Arcane Armor."
) {
  throw new Error(
    `Expected missing Arcane Armor feature validation_error, got ${missingFeatureOnSheetUpdate.status} ${JSON.stringify(missingFeatureOnSheetUpdate.payload)}`,
  );
}

const playerFeatureStateUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/feature-states/arcane-armor`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 10, enabled: true } },
);
if (
  playerFeatureStateUpdate.status !== 200 ||
  playerFeatureStateUpdate.payload?.ok !== true ||
  playerFeatureStateUpdate.payload?.character?.state_record?.revision !== 11 ||
  playerFeatureStateUpdate.payload?.character?.state_record?.state?.feature_states?.arcane_armor?.enabled !== true
) {
  throw new Error(`Unexpected feature-state PATCH payload: ${JSON.stringify(playerFeatureStateUpdate.payload)}`);
}

const featureStateAssertionDb = new Database(dbPath, { readonly: true });
const managedStateAfterFeatureState = featureStateAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
featureStateAssertionDb.close();
const managedFeatureState = JSON.parse(managedStateAfterFeatureState?.state_json || "{}");
if (
  managedStateAfterFeatureState?.revision !== 11 ||
  managedStateAfterFeatureState?.updated_by_user_id !== 79 ||
  managedFeatureState.feature_states?.arcane_armor?.enabled !== true
) {
  throw new Error(
    `Unexpected feature-state database row: ${JSON.stringify({
      managedStateAfterFeatureState,
      managedFeatureState,
    })}`,
  );
}

const nonXianxiaInventoryEquippedUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${managedCharacterSlug}/session/xianxia-inventory/jade-sword/equipped`,
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 11, is_equipped: true } },
);
if (
  nonXianxiaInventoryEquippedUpdate.status !== 400 ||
  nonXianxiaInventoryEquippedUpdate.payload?.error?.code !== "validation_error" ||
  nonXianxiaInventoryEquippedUpdate.payload?.error?.message !== "Xianxia inventory operations require a Xianxia character."
) {
  throw new Error(
    `Expected non-Xianxia inventory equipped validation_error, got ${nonXianxiaInventoryEquippedUpdate.status} ${JSON.stringify(nonXianxiaInventoryEquippedUpdate.payload)}`,
  );
}

const contentCharactersAfterPut = await requestJson("/api/v1/campaigns/linden-pass/content/characters", contentManagerHeaders);
if (!contentCharactersAfterPut.payload?.characters?.some((item) => item.character_slug === managedCharacterSlug)) {
  throw new Error(`Expected content characters list to include ${managedCharacterSlug} after PUT.`);
}

const managedContentCharacter = await requestJson(managedCharacterPath, contentManagerHeaders);
if (
  managedContentCharacter.status !== 200 ||
  managedContentCharacter.payload?.character_file?.definition?.name !== "API Scout" ||
  managedContentCharacter.payload?.character_file?.state_created !== false
) {
  throw new Error(
    `Expected managed content character detail to return written YAML, got ${managedContentCharacter.status} ${JSON.stringify(managedContentCharacter.payload)}`,
  );
}

const fixtureContentCharacterDelete = await requestJson(
  managedCharacterPath,
  contentManagerHeaders,
  { method: "DELETE" },
);
if (
  fixtureContentCharacterDelete.status !== 403 ||
  fixtureContentCharacterDelete.payload?.error?.message !== "Content character writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content character DELETE bearer requirement, got ${fixtureContentCharacterDelete.status} ${fixtureContentCharacterDelete.payload?.error?.message}`,
  );
}

const contentCharacterDelete = await requestJson(
  managedCharacterPath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  contentCharacterDelete.status !== 200 ||
  contentCharacterDelete.payload?.deleted?.character_slug !== managedCharacterSlug ||
  contentCharacterDelete.payload?.deleted?.deleted_files !== true ||
  contentCharacterDelete.payload?.deleted?.deleted_state !== true ||
  contentCharacterDelete.payload?.deleted?.deleted_assignment !== true
) {
  throw new Error(
    `Expected content character DELETE payload, got ${contentCharacterDelete.status} ${JSON.stringify(contentCharacterDelete.payload)}`,
  );
}
if (existsSync(managedCharacterDefinitionPath) || existsSync(managedCharacterImportPath)) {
  throw new Error("Expected content character DELETE to remove managed definition/import files from the copied fixture tree.");
}
const dndDeleteAssertionDb = new Database(dbPath);
const remainingManagedState = dndDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
const remainingManagedAssignment = dndDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", managedCharacterSlug);
dndDeleteAssertionDb.close();
if (Number(remainingManagedState?.count) !== 0 || Number(remainingManagedAssignment?.count) !== 0) {
  throw new Error(
    `Expected content character DELETE to remove SQLite state and assignment, got state=${JSON.stringify(remainingManagedState)} assignment=${JSON.stringify(remainingManagedAssignment)}`,
  );
}

const missingManagedCharacterDelete = await requestJson(
  managedCharacterPath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  missingManagedCharacterDelete.status !== 404 ||
  missingManagedCharacterDelete.payload?.error?.code !== "content_character_not_found"
) {
  throw new Error(
    `Expected missing managed content character DELETE 404, got ${missingManagedCharacterDelete.status} ${missingManagedCharacterDelete.payload?.error?.code}`,
  );
}

const xianxiaContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  bearerContentManagerHeaders,
  { method: "PATCH", body: { config: { system: "xianxia", systems_library: "xianxia" } } },
);
if (
  xianxiaContentConfigPatch.status !== 200 ||
  xianxiaContentConfigPatch.payload?.config_file?.config?.system !== "Xianxia" ||
  xianxiaContentConfigPatch.payload?.config_file?.config?.systems_library !== "Xianxia"
) {
  throw new Error(`Expected Xianxia content config before character state smoke, got ${JSON.stringify(xianxiaContentConfigPatch.payload)}`);
}

const xianxiaCharacterSlug = "api-cultivator";
const xianxiaCharacterPath = `/api/v1/campaigns/linden-pass/content/characters/${xianxiaCharacterSlug}`;
const xianxiaDefinition = {
  name: "API Cultivator",
  status: "active",
  system: "xianxia",
  xianxia: {
    realm: "Mortal",
    energy_maxima: { jing: 3, qi: 2, shen: 1 },
    yin_yang: { yin_max: 2, yang_max: 1 },
    dao_max: 3,
    durability: {
      hp_max: 18,
      stance_max: 12,
      manual_armor_bonus: 1,
      defense: 11,
    },
    trained_skills: ["Tea Ceremony"],
    necessary_weapons: ["Jian"],
    martial_arts: [{ name: "Heavenly Palm", current_rank: "Initiate" }],
  },
};
const xianxiaCreateResponse = await requestJson(
  xianxiaCharacterPath,
  bearerContentManagerHeaders,
  { method: "PUT", body: { definition: xianxiaDefinition } },
);
if (
  xianxiaCreateResponse.status !== 200 ||
  xianxiaCreateResponse.payload?.character_file?.state_created !== true ||
  xianxiaCreateResponse.payload?.character_file?.definition?.system !== "Xianxia"
) {
  throw new Error(`Expected Xianxia content character create payload, got ${xianxiaCreateResponse.status} ${JSON.stringify(xianxiaCreateResponse.payload)}`);
}

const xianxiaStateSetupDb = new Database(dbPath);
const xianxiaInitialRow = xianxiaStateSetupDb
  .prepare("SELECT revision, state_json FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
if (!xianxiaInitialRow || xianxiaInitialRow.revision !== 1) {
  xianxiaStateSetupDb.close();
  throw new Error(`Expected Xianxia character create to initialize state, got ${JSON.stringify(xianxiaInitialRow)}`);
}
const xianxiaMutableState = JSON.parse(xianxiaInitialRow.state_json);
xianxiaMutableState.vitals.current_hp = 7;
xianxiaMutableState.vitals.temp_hp = -2;
xianxiaMutableState.xianxia.vitals.current_hp = 7;
xianxiaMutableState.xianxia.vitals.temp_hp = -2;
xianxiaMutableState.xianxia.vitals.current_stance = 5;
xianxiaMutableState.xianxia.vitals.temp_stance = -3;
xianxiaMutableState.xianxia.energies.jing.current = 2;
xianxiaMutableState.xianxia.yin_yang.yin_current = 1;
xianxiaMutableState.xianxia.dao.current = 2;
xianxiaMutableState.xianxia.active_stance = { name: "Stone Root" };
xianxiaMutableState.xianxia.active_aura = { name: "Azure Bell" };
xianxiaMutableState.xianxia.inventory = {
  enabled: true,
  quantities: [
    {
      id: "spirit-rice",
      name: "Spirit Rice",
      quantity: 2,
      item_type: "provision",
      item_nature: "mundane",
      notes: "Cook before travel.",
      tags: ["food"],
    },
    {
      id: "jade-sword",
      name: "Jade Sword",
      quantity: 1,
      item_type: "Weapon",
      item_nature: "mundane",
      equippable: true,
      is_equipped: false,
      notes: "Practice blade.",
      tags: ["weapon"],
    },
  ],
};
xianxiaMutableState.inventory = [
  {
    id: "spirit-rice",
    name: "Spirit Rice",
    quantity: 2,
    item_type: "provision",
    item_nature: "mundane",
    notes: "Cook before travel.",
    tags: ["food"],
  },
  {
    id: "jade-sword",
    name: "Jade Sword",
    quantity: 1,
    item_type: "Weapon",
    item_nature: "mundane",
    equippable: true,
    is_equipped: false,
    notes: "Practice blade.",
    tags: ["weapon"],
  },
];
xianxiaMutableState.notes.player_notes_markdown = "Keep the manual pool edits in SQLite.";
const editedXianxiaRevision = Number(xianxiaInitialRow.revision) + 1;
xianxiaStateSetupDb
  .prepare(
    "UPDATE character_state SET revision = ?, state_json = ?, updated_at = ?, updated_by_user_id = ? WHERE campaign_slug = ? AND character_slug = ?",
  )
  .run(
    editedXianxiaRevision,
    JSON.stringify(xianxiaMutableState),
    "2026-06-25T12:45:00+00:00",
    77,
    "linden-pass",
    xianxiaCharacterSlug,
  );
xianxiaStateSetupDb.close();

const updatedXianxiaDefinition = structuredClone(xianxiaDefinition);
updatedXianxiaDefinition.xianxia.energy_maxima = { jing: 1, qi: 2, shen: 1 };
updatedXianxiaDefinition.xianxia.yin_yang = { yin_max: 1, yang_max: 1 };
updatedXianxiaDefinition.xianxia.durability = {
  hp_max: 6,
  stance_max: 4,
  manual_armor_bonus: 1,
  defense: 11,
};
const xianxiaUpdateResponse = await requestJson(
  xianxiaCharacterPath,
  bearerContentManagerHeaders,
  { method: "PUT", body: { definition: updatedXianxiaDefinition } },
);
if (
  xianxiaUpdateResponse.status !== 200 ||
  xianxiaUpdateResponse.payload?.character_file?.state_created !== false
) {
  throw new Error(`Expected Xianxia content character update payload, got ${xianxiaUpdateResponse.status} ${JSON.stringify(xianxiaUpdateResponse.payload)}`);
}
const xianxiaDefinitionPath = path.join(
  campaignsDir,
  "linden-pass",
  "characters",
  xianxiaCharacterSlug,
  "definition.yaml",
);
const savedXianxiaDefinitionText = readFileSync(xianxiaDefinitionPath, "utf8");
if (
  savedXianxiaDefinitionText.includes("current_hp") ||
  savedXianxiaDefinitionText.includes("active_stance") ||
  savedXianxiaDefinitionText.includes("Keep the manual pool edits")
) {
  throw new Error("Expected Xianxia mutable state to stay out of definition.yaml after content character update.");
}
const xianxiaUpdateAssertionDb = new Database(dbPath);
const xianxiaUpdatedRow = xianxiaUpdateAssertionDb
  .prepare("SELECT revision, state_json FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaUpdateAssertionDb.close();
const xianxiaUpdatedState = JSON.parse(xianxiaUpdatedRow?.state_json || "{}");
if (
  Number(xianxiaUpdatedRow?.revision) !== editedXianxiaRevision + 1 ||
  xianxiaUpdatedState.vitals?.current_hp !== 6 ||
  xianxiaUpdatedState.vitals?.temp_hp !== 0 ||
  xianxiaUpdatedState.xianxia?.vitals?.current_hp !== 6 ||
  xianxiaUpdatedState.xianxia?.vitals?.current_stance !== 4 ||
  xianxiaUpdatedState.xianxia?.vitals?.temp_stance !== 0 ||
  xianxiaUpdatedState.xianxia?.energies?.jing?.current !== 1 ||
  xianxiaUpdatedState.xianxia?.yin_yang?.yin_current !== 1 ||
  xianxiaUpdatedState.xianxia?.yin_yang?.yang_current !== 1 ||
  xianxiaUpdatedState.xianxia?.dao?.current !== 2 ||
  xianxiaUpdatedState.xianxia?.active_stance?.name !== "Stone Root" ||
  xianxiaUpdatedState.xianxia?.active_aura?.name !== "Azure Bell" ||
  xianxiaUpdatedState.notes?.player_notes_markdown !== "Keep the manual pool edits in SQLite."
) {
  throw new Error(
    `Expected Xianxia mutable state reconciliation, got revision=${xianxiaUpdatedRow?.revision} state=${JSON.stringify(xianxiaUpdatedState)}`,
  );
}

const xianxiaSessionVitalsUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/vitals`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_revision: editedXianxiaRevision + 1,
      current_hp: "4",
      temp_hp: "-1",
      current_stance: "3",
      temp_stance: "2",
      current_jing: "5",
      current_qi: "1",
      current_shen: "0",
      current_yin: "2",
      current_yang: "1",
      current_dao: "3",
    },
  },
);
if (
  xianxiaSessionVitalsUpdate.status !== 200 ||
  xianxiaSessionVitalsUpdate.payload?.ok !== true ||
  xianxiaSessionVitalsUpdate.payload?.character?.definition?.character_slug !== xianxiaCharacterSlug ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.revision !== editedXianxiaRevision + 2 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.vitals?.current_hp !== 4 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.vitals?.temp_hp !== -1 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.vitals?.current_hp !== 6 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.vitals?.current_stance !== 3 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.vitals?.temp_stance !== 2 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.energies?.jing?.current !== 5 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.energies?.qi?.current !== 1 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.energies?.shen?.current !== 0 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.yin_yang?.yin_current !== 2 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.yin_yang?.yang_current !== 1 ||
  xianxiaSessionVitalsUpdate.payload?.character?.state_record?.state?.xianxia?.dao?.current !== 3
) {
  throw new Error(`Unexpected Xianxia session vitals PATCH payload: ${JSON.stringify(xianxiaSessionVitalsUpdate.payload)}`);
}

const xianxiaVitalsAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaVitalsRow = xianxiaVitalsAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaVitalsAssertionDb.close();
const xianxiaVitalsState = JSON.parse(xianxiaVitalsRow?.state_json || "{}");
if (
  Number(xianxiaVitalsRow?.revision) !== editedXianxiaRevision + 2 ||
  xianxiaVitalsRow?.updated_by_user_id !== 81 ||
  xianxiaVitalsState.vitals?.current_hp !== 4 ||
  xianxiaVitalsState.vitals?.temp_hp !== -1 ||
  xianxiaVitalsState.xianxia?.vitals?.current_hp !== 6 ||
  xianxiaVitalsState.xianxia?.vitals?.temp_hp !== 0 ||
  xianxiaVitalsState.xianxia?.vitals?.current_stance !== 3 ||
  xianxiaVitalsState.xianxia?.vitals?.temp_stance !== 2 ||
  xianxiaVitalsState.xianxia?.energies?.jing?.current !== 5 ||
  xianxiaVitalsState.xianxia?.energies?.qi?.current !== 1 ||
  xianxiaVitalsState.xianxia?.energies?.shen?.current !== 0 ||
  xianxiaVitalsState.xianxia?.yin_yang?.yin_current !== 2 ||
  xianxiaVitalsState.xianxia?.yin_yang?.yang_current !== 1 ||
  xianxiaVitalsState.xianxia?.dao?.current !== 3
) {
  throw new Error(
    `Unexpected Xianxia session vitals database row: ${JSON.stringify({
      xianxiaVitalsRow,
      xianxiaVitalsState,
    })}`,
  );
}

const xianxiaSessionInventoryUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/inventory/spirit-rice`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 2, quantity: "4", delta: "-1" } },
);
if (
  xianxiaSessionInventoryUpdate.status !== 200 ||
  xianxiaSessionInventoryUpdate.payload?.ok !== true ||
  xianxiaSessionInventoryUpdate.payload?.character?.state_record?.revision !== editedXianxiaRevision + 3 ||
  xianxiaSessionInventoryUpdate.payload?.character?.state_record?.state?.xianxia?.inventory?.quantities?.[0]?.id !== "spirit-rice" ||
  xianxiaSessionInventoryUpdate.payload?.character?.state_record?.state?.xianxia?.inventory?.quantities?.[0]?.quantity !== 3 ||
  xianxiaSessionInventoryUpdate.payload?.character?.state_record?.state?.inventory?.[0]?.id !== "spirit-rice" ||
  xianxiaSessionInventoryUpdate.payload?.character?.state_record?.state?.inventory?.[0]?.quantity !== 3
) {
  throw new Error(`Unexpected Xianxia session inventory PATCH payload: ${JSON.stringify(xianxiaSessionInventoryUpdate.payload)}`);
}

const xianxiaInventoryAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaInventoryRow = xianxiaInventoryAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaInventoryAssertionDb.close();
const xianxiaInventoryState = JSON.parse(xianxiaInventoryRow?.state_json || "{}");
if (
  Number(xianxiaInventoryRow?.revision) !== editedXianxiaRevision + 3 ||
  xianxiaInventoryRow?.updated_by_user_id !== 81 ||
  xianxiaInventoryState.xianxia?.inventory?.quantities?.[0]?.id !== "spirit-rice" ||
  xianxiaInventoryState.xianxia?.inventory?.quantities?.[0]?.quantity !== 3 ||
  xianxiaInventoryState.inventory?.[0]?.id !== "spirit-rice" ||
  xianxiaInventoryState.inventory?.[0]?.quantity !== 3
) {
  throw new Error(
    `Unexpected Xianxia session inventory database row: ${JSON.stringify({
      xianxiaInventoryRow,
      xianxiaInventoryState,
    })}`,
  );
}

const xianxiaInventoryEquippedPath =
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/xianxia-inventory/jade-sword/equipped`;
const anonymousXianxiaInventoryEquippedUpdate = await requestJson(
  xianxiaInventoryEquippedPath,
  {},
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 3, is_equipped: true } },
);
if (
  anonymousXianxiaInventoryEquippedUpdate.status !== 401 ||
  anonymousXianxiaInventoryEquippedUpdate.payload?.error?.code !== "auth_required"
) {
  throw new Error(
    `Expected anonymous Xianxia inventory equipped PATCH auth_required, got ${anonymousXianxiaInventoryEquippedUpdate.status} ${JSON.stringify(anonymousXianxiaInventoryEquippedUpdate.payload)}`,
  );
}

const fixtureXianxiaInventoryEquippedUpdate = await requestJson(
  xianxiaInventoryEquippedPath,
  {
    "X-CPW-Fixture-Role": "dm",
  },
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 3, is_equipped: true } },
);
if (
  fixtureXianxiaInventoryEquippedUpdate.status !== 403 ||
  fixtureXianxiaInventoryEquippedUpdate.payload?.error?.message !==
    "Character session state writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture Xianxia inventory equipped PATCH bearer requirement, got ${fixtureXianxiaInventoryEquippedUpdate.status} ${JSON.stringify(fixtureXianxiaInventoryEquippedUpdate.payload)}`,
  );
}

const staleXianxiaInventoryEquippedUpdate = await requestJson(
  xianxiaInventoryEquippedPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, is_equipped: true } },
);
if (
  staleXianxiaInventoryEquippedUpdate.status !== 409 ||
  staleXianxiaInventoryEquippedUpdate.payload?.error?.code !== "state_conflict" ||
  staleXianxiaInventoryEquippedUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale Xianxia inventory equipped PATCH conflict, got ${staleXianxiaInventoryEquippedUpdate.status} ${JSON.stringify(staleXianxiaInventoryEquippedUpdate.payload)}`,
  );
}

const unknownXianxiaInventoryEquippedUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/xianxia-inventory/missing-item/equipped`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 3, is_equipped: true } },
);
if (
  unknownXianxiaInventoryEquippedUpdate.status !== 400 ||
  unknownXianxiaInventoryEquippedUpdate.payload?.error?.code !== "validation_error" ||
  unknownXianxiaInventoryEquippedUpdate.payload?.error?.message !== "Unknown Xianxia inventory item: missing-item"
) {
  throw new Error(
    `Expected unknown Xianxia inventory equipped validation_error, got ${unknownXianxiaInventoryEquippedUpdate.status} ${JSON.stringify(unknownXianxiaInventoryEquippedUpdate.payload)}`,
  );
}

const nonEquippableXianxiaInventoryEquippedUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/xianxia-inventory/spirit-rice/equipped`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 3, is_equipped: true } },
);
if (
  nonEquippableXianxiaInventoryEquippedUpdate.status !== 400 ||
  nonEquippableXianxiaInventoryEquippedUpdate.payload?.error?.code !== "validation_error" ||
  nonEquippableXianxiaInventoryEquippedUpdate.payload?.error?.message !== "Cannot equip a non-equippable item."
) {
  throw new Error(
    `Expected non-equippable Xianxia inventory equipped validation_error, got ${nonEquippableXianxiaInventoryEquippedUpdate.status} ${JSON.stringify(nonEquippableXianxiaInventoryEquippedUpdate.payload)}`,
  );
}

const xianxiaInventoryEquippedUpdate = await requestJson(
  xianxiaInventoryEquippedPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 3, is_equipped: true } },
);
const equippedPayloadQuantities =
  xianxiaInventoryEquippedUpdate.payload?.character?.state_record?.state?.xianxia?.inventory?.quantities || [];
const equippedPayloadMirror = xianxiaInventoryEquippedUpdate.payload?.character?.state_record?.state?.inventory || [];
if (
  xianxiaInventoryEquippedUpdate.status !== 200 ||
  xianxiaInventoryEquippedUpdate.payload?.ok !== true ||
  xianxiaInventoryEquippedUpdate.payload?.character?.state_record?.revision !== editedXianxiaRevision + 4 ||
  equippedPayloadQuantities.find((item) => item?.id === "jade-sword")?.is_equipped !== true ||
  equippedPayloadMirror.find((item) => item?.id === "jade-sword")?.is_equipped !== true
) {
  throw new Error(`Unexpected Xianxia inventory equipped PATCH payload: ${JSON.stringify(xianxiaInventoryEquippedUpdate.payload)}`);
}

const xianxiaInventoryEquippedAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaInventoryEquippedRow = xianxiaInventoryEquippedAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaInventoryEquippedAssertionDb.close();
const xianxiaInventoryEquippedState = JSON.parse(xianxiaInventoryEquippedRow?.state_json || "{}");
const equippedDbQuantities = xianxiaInventoryEquippedState.xianxia?.inventory?.quantities || [];
const equippedDbMirror = xianxiaInventoryEquippedState.inventory || [];
if (
  Number(xianxiaInventoryEquippedRow?.revision) !== editedXianxiaRevision + 4 ||
  xianxiaInventoryEquippedRow?.updated_by_user_id !== 81 ||
  equippedDbQuantities.find((item) => item?.id === "jade-sword")?.is_equipped !== true ||
  equippedDbMirror.find((item) => item?.id === "jade-sword")?.is_equipped !== true
) {
  throw new Error(
    `Unexpected Xianxia inventory equipped database row: ${JSON.stringify({
      xianxiaInventoryEquippedRow,
      xianxiaInventoryEquippedState,
    })}`,
  );
}

const staleXianxiaActiveStateUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/xianxia-active-state`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: 999, active_stance_name: "Stale Crane" } },
);
if (
  staleXianxiaActiveStateUpdate.status !== 409 ||
  staleXianxiaActiveStateUpdate.payload?.error?.code !== "state_conflict" ||
  staleXianxiaActiveStateUpdate.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale Xianxia active-state PATCH conflict, got ${staleXianxiaActiveStateUpdate.status} ${JSON.stringify(staleXianxiaActiveStateUpdate.payload)}`,
  );
}

const xianxiaActiveStateUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/xianxia-active-state`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "PATCH",
    body: {
      expected_revision: editedXianxiaRevision + 4,
      active_stance_name: "  Flowing   Reed  ",
      active_aura_name: "",
    },
  },
);
if (
  xianxiaActiveStateUpdate.status !== 200 ||
  xianxiaActiveStateUpdate.payload?.ok !== true ||
  xianxiaActiveStateUpdate.payload?.character?.state_record?.revision !== editedXianxiaRevision + 5 ||
  xianxiaActiveStateUpdate.payload?.character?.state_record?.state?.xianxia?.active_stance?.name !== "Flowing Reed" ||
  xianxiaActiveStateUpdate.payload?.character?.state_record?.state?.xianxia?.active_aura !== null
) {
  throw new Error(`Unexpected Xianxia active-state PATCH payload: ${JSON.stringify(xianxiaActiveStateUpdate.payload)}`);
}

const xianxiaActiveStateAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaActiveStateRow = xianxiaActiveStateAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaActiveStateAssertionDb.close();
const xianxiaActiveState = JSON.parse(xianxiaActiveStateRow?.state_json || "{}");
if (
  Number(xianxiaActiveStateRow?.revision) !== editedXianxiaRevision + 5 ||
  xianxiaActiveStateRow?.updated_by_user_id !== 81 ||
  xianxiaActiveState.xianxia?.active_stance?.name !== "Flowing Reed" ||
  xianxiaActiveState.xianxia?.active_aura !== null
) {
  throw new Error(
    `Unexpected Xianxia active-state database row: ${JSON.stringify({
      xianxiaActiveStateRow,
      xianxiaActiveState,
    })}`,
  );
}

const xianxiaCurrencyBefore = xianxiaActiveState.xianxia?.currency || {};
const xianxiaSessionCurrencyUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/currency`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "PATCH", body: { expected_revision: editedXianxiaRevision + 5, coin: "7", supply: "-3", spirit_stones: "" } },
);
if (
  xianxiaSessionCurrencyUpdate.status !== 200 ||
  xianxiaSessionCurrencyUpdate.payload?.ok !== true ||
  xianxiaSessionCurrencyUpdate.payload?.character?.state_record?.revision !== editedXianxiaRevision + 6 ||
  xianxiaSessionCurrencyUpdate.payload?.character?.state_record?.state?.xianxia?.currency?.coin !== 7 ||
  xianxiaSessionCurrencyUpdate.payload?.character?.state_record?.state?.xianxia?.currency?.supply !== 0 ||
  xianxiaSessionCurrencyUpdate.payload?.character?.state_record?.state?.xianxia?.currency?.spirit_stones !==
    (xianxiaCurrencyBefore.spirit_stones ?? 0)
) {
  throw new Error(`Unexpected Xianxia session currency PATCH payload: ${JSON.stringify(xianxiaSessionCurrencyUpdate.payload)}`);
}

const xianxiaCurrencyAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaCurrencyRow = xianxiaCurrencyAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaCurrencyAssertionDb.close();
const xianxiaCurrencyState = JSON.parse(xianxiaCurrencyRow?.state_json || "{}");
if (
  Number(xianxiaCurrencyRow?.revision) !== editedXianxiaRevision + 6 ||
  xianxiaCurrencyRow?.updated_by_user_id !== 81 ||
  xianxiaCurrencyState.xianxia?.currency?.coin !== 7 ||
  xianxiaCurrencyState.xianxia?.currency?.supply !== 0 ||
  xianxiaCurrencyState.xianxia?.currency?.spirit_stones !== (xianxiaCurrencyBefore.spirit_stones ?? 0)
) {
  throw new Error(
    `Unexpected Xianxia session currency database row: ${JSON.stringify({
      xianxiaCurrencyRow,
      xianxiaCurrencyState,
    })}`,
  );
}

const xianxiaLongRestPreview = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/rest-preview/long`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
);
if (
  xianxiaLongRestPreview.status !== 200 ||
  xianxiaLongRestPreview.payload?.ok !== true ||
  xianxiaLongRestPreview.payload?.preview?.rest_type !== "long" ||
  xianxiaLongRestPreview.payload?.preview?.label !== "Long Rest" ||
  !Array.isArray(xianxiaLongRestPreview.payload?.preview?.changes) ||
  xianxiaLongRestPreview.payload.preview.changes.length === 0 ||
  xianxiaLongRestPreview.payload?.preview?.adjustments?.current_hp !== 6
) {
  throw new Error(`Unexpected Xianxia long-rest preview payload: ${JSON.stringify(xianxiaLongRestPreview.payload)}`);
}

const xianxiaLongRestApply = await requestJson(
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/rest/long`,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "POST",
    body: {
      expected_revision: editedXianxiaRevision + 6,
      current_hp: "",
      hit_dice_current: { d6: "1" },
    },
  },
);
if (
  xianxiaLongRestApply.status !== 200 ||
  xianxiaLongRestApply.payload?.ok !== true ||
  xianxiaLongRestApply.payload?.character?.state_record?.revision !== editedXianxiaRevision + 7 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.vitals?.current_hp !== 6 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.vitals?.current_hp !== 6 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.vitals?.current_stance !== 4 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.energies?.jing?.current !== 1 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.energies?.qi?.current !== 2 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.energies?.shen?.current !== 1 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.yin_yang?.yin_current !== 1 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.yin_yang?.yang_current !== 1 ||
  xianxiaLongRestApply.payload?.character?.state_record?.state?.xianxia?.dao?.current !== 3
) {
  throw new Error(`Unexpected Xianxia long-rest apply payload: ${JSON.stringify(xianxiaLongRestApply.payload)}`);
}

const xianxiaRestAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaRestRow = xianxiaRestAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaRestAssertionDb.close();
const xianxiaRestState = JSON.parse(xianxiaRestRow?.state_json || "{}");
if (
  Number(xianxiaRestRow?.revision) !== editedXianxiaRevision + 7 ||
  xianxiaRestRow?.updated_by_user_id !== 81 ||
  xianxiaRestState.vitals?.current_hp !== 6 ||
  xianxiaRestState.xianxia?.vitals?.current_hp !== 6 ||
  xianxiaRestState.xianxia?.vitals?.current_stance !== 4 ||
  xianxiaRestState.xianxia?.energies?.jing?.current !== 1 ||
  xianxiaRestState.xianxia?.energies?.qi?.current !== 2 ||
  xianxiaRestState.xianxia?.energies?.shen?.current !== 1 ||
  xianxiaRestState.xianxia?.yin_yang?.yin_current !== 1 ||
  xianxiaRestState.xianxia?.yin_yang?.yang_current !== 1 ||
  xianxiaRestState.xianxia?.dao?.current !== 3
) {
  throw new Error(
    `Unexpected Xianxia rest database row: ${JSON.stringify({
      xianxiaRestRow,
      xianxiaRestState,
    })}`,
  );
}

const xianxiaInventoryAddPath =
  `/api/v1/campaigns/linden-pass/characters/${xianxiaCharacterSlug}/session/xianxia-inventory`;
const staleXianxiaInventoryAdd = await requestJson(
  xianxiaInventoryAddPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "POST", body: { expected_revision: 999, item: { name: "Jade Charm" } } },
);
if (
  staleXianxiaInventoryAdd.status !== 409 ||
  staleXianxiaInventoryAdd.payload?.error?.code !== "state_conflict" ||
  staleXianxiaInventoryAdd.payload?.error?.message !== "This sheet changed in another session. Refresh and try again."
) {
  throw new Error(
    `Expected stale Xianxia inventory add conflict, got ${staleXianxiaInventoryAdd.status} ${JSON.stringify(staleXianxiaInventoryAdd.payload)}`,
  );
}

const missingNameXianxiaInventoryAdd = await requestJson(
  xianxiaInventoryAddPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  { method: "POST", body: { expected_revision: editedXianxiaRevision + 7, item: { quantity: 1 } } },
);
if (
  missingNameXianxiaInventoryAdd.status !== 400 ||
  missingNameXianxiaInventoryAdd.payload?.error?.code !== "validation_error" ||
  missingNameXianxiaInventoryAdd.payload?.error?.message !== "Inventory item requires a name."
) {
  throw new Error(
    `Expected missing-name Xianxia inventory add validation_error, got ${missingNameXianxiaInventoryAdd.status} ${JSON.stringify(missingNameXianxiaInventoryAdd.payload)}`,
  );
}

const duplicateXianxiaInventoryAdd = await requestJson(
  xianxiaInventoryAddPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "POST",
    body: {
      expected_revision: editedXianxiaRevision + 7,
      item: { id: "spirit-rice", name: "Duplicate Rice" },
    },
  },
);
if (
  duplicateXianxiaInventoryAdd.status !== 400 ||
  duplicateXianxiaInventoryAdd.payload?.error?.code !== "validation_error" ||
  duplicateXianxiaInventoryAdd.payload?.error?.message !== "Duplicate inventory item id: spirit-rice"
) {
  throw new Error(
    `Expected duplicate Xianxia inventory add validation_error, got ${duplicateXianxiaInventoryAdd.status} ${JSON.stringify(duplicateXianxiaInventoryAdd.payload)}`,
  );
}

const nonEquippableXianxiaInventoryAdd = await requestJson(
  xianxiaInventoryAddPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "POST",
    body: {
      expected_revision: editedXianxiaRevision + 7,
      item: {
        name: "Silk Robe",
        item_type: "Miscellaneous",
        equippable: false,
        is_equipped: true,
      },
    },
  },
);
if (
  nonEquippableXianxiaInventoryAdd.status !== 400 ||
  nonEquippableXianxiaInventoryAdd.payload?.error?.code !== "validation_error" ||
  nonEquippableXianxiaInventoryAdd.payload?.error?.message !== "Cannot equip non-equippable item."
) {
  throw new Error(
    `Expected non-equippable Xianxia inventory add validation_error, got ${nonEquippableXianxiaInventoryAdd.status} ${JSON.stringify(nonEquippableXianxiaInventoryAdd.payload)}`,
  );
}

const xianxiaInventoryAdd = await requestJson(
  xianxiaInventoryAddPath,
  {
    Authorization: `Bearer ${dmApiToken}`,
  },
  {
    method: "POST",
    body: {
      expected_revision: editedXianxiaRevision + 7,
      item: {
        name: "Jade Charm",
        quantity: "2",
        item_type: "Artifact",
        item_nature: "Relic",
        equippable: true,
        is_equipped: true,
        notes: "Hums quietly.",
        tags: ["relic"],
      },
    },
  },
);
const addedPayloadQuantities = xianxiaInventoryAdd.payload?.character?.state_record?.state?.xianxia?.inventory?.quantities || [];
const addedPayloadItem = addedPayloadQuantities.find((item) => item?.id === "artifact-jade-charm");
const addedPayloadMirror = xianxiaInventoryAdd.payload?.character?.state_record?.state?.inventory || [];
const addedMirrorItem = addedPayloadMirror.find((item) => item?.id === "artifact-jade-charm");
if (
  xianxiaInventoryAdd.status !== 200 ||
  xianxiaInventoryAdd.payload?.ok !== true ||
  xianxiaInventoryAdd.payload?.character?.state_record?.revision !== editedXianxiaRevision + 8 ||
  addedPayloadItem?.name !== "Jade Charm" ||
  addedPayloadItem?.quantity !== 2 ||
  addedPayloadItem?.item_type !== "Artifact" ||
  addedPayloadItem?.item_nature !== "Relic" ||
  addedPayloadItem?.equippable !== true ||
  addedPayloadItem?.is_equipped !== true ||
  addedPayloadItem?.notes !== "Hums quietly." ||
  addedPayloadItem?.tags?.[0] !== "relic" ||
  addedMirrorItem?.name !== "Jade Charm" ||
  addedMirrorItem?.quantity !== 2 ||
  addedMirrorItem?.item_type !== "Artifact" ||
  addedMirrorItem?.item_nature !== "Relic" ||
  addedMirrorItem?.is_equipped !== true
) {
  throw new Error(`Unexpected Xianxia inventory add POST payload: ${JSON.stringify(xianxiaInventoryAdd.payload)}`);
}

const xianxiaInventoryAddAssertionDb = new Database(dbPath, { readonly: true });
const xianxiaInventoryAddRow = xianxiaInventoryAddAssertionDb
  .prepare("SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
  .get("linden-pass", xianxiaCharacterSlug);
xianxiaInventoryAddAssertionDb.close();
const xianxiaInventoryAddState = JSON.parse(xianxiaInventoryAddRow?.state_json || "{}");
const addedDbQuantities = xianxiaInventoryAddState.xianxia?.inventory?.quantities || [];
const addedDbItem = addedDbQuantities.find((item) => item?.id === "artifact-jade-charm");
const addedDbMirror = xianxiaInventoryAddState.inventory || [];
const addedDbMirrorItem = addedDbMirror.find((item) => item?.id === "artifact-jade-charm");
if (
  Number(xianxiaInventoryAddRow?.revision) !== editedXianxiaRevision + 8 ||
  xianxiaInventoryAddRow?.updated_by_user_id !== 81 ||
  addedDbItem?.name !== "Jade Charm" ||
  addedDbItem?.quantity !== 2 ||
  addedDbItem?.item_type !== "Artifact" ||
  addedDbItem?.item_nature !== "Relic" ||
  addedDbItem?.equippable !== true ||
  addedDbItem?.is_equipped !== true ||
  addedDbMirrorItem?.id !== "artifact-jade-charm" ||
  addedDbMirrorItem?.is_equipped !== true
) {
  throw new Error(
    `Unexpected Xianxia inventory add database row: ${JSON.stringify({
      xianxiaInventoryAddRow,
      xianxiaInventoryAddState,
    })}`,
  );
}

const xianxiaDeleteResponse = await requestJson(
  xianxiaCharacterPath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  xianxiaDeleteResponse.status !== 200 ||
  xianxiaDeleteResponse.payload?.deleted?.deleted_files !== true ||
  xianxiaDeleteResponse.payload?.deleted?.deleted_state !== true ||
  xianxiaDeleteResponse.payload?.deleted?.deleted_assignment !== false
) {
  throw new Error(`Expected Xianxia content character delete payload, got ${xianxiaDeleteResponse.status} ${JSON.stringify(xianxiaDeleteResponse.payload)}`);
}

const restoredPostXianxiaContentConfigPatch = await requestJson(
  "/api/v1/campaigns/linden-pass/content/config",
  bearerContentManagerHeaders,
  {
    method: "PATCH",
    body: {
      config: {
        system: "DND 5E",
        systems_library: "DND5E",
      },
    },
  },
);
if (
  restoredPostXianxiaContentConfigPatch.status !== 200 ||
  restoredPostXianxiaContentConfigPatch.payload?.config_file?.config?.system !== "DND-5E" ||
  restoredPostXianxiaContentConfigPatch.payload?.config_file?.config?.systems_library !== "DND-5E"
) {
  throw new Error(`Expected DND config restore after Xianxia smoke, got ${JSON.stringify(restoredPostXianxiaContentConfigPatch.payload)}`);
}

const contentAssets = await requestJson("/api/v1/campaigns/linden-pass/content/assets", contentManagerHeaders);
if (contentAssets.status !== 200) {
  throw new Error(`Expected content assets list endpoint 200, got ${contentAssets.status}`);
}
if (!Array.isArray(contentAssets.payload?.assets) || contentAssets.payload.assets.length !== 2) {
  throw new Error(`Expected 2 fixture content assets, got ${contentAssets.payload?.assets?.length}`);
}
const lyraAsset = contentAssets.payload.assets.find((item) => item.asset_ref === "npcs/captain-lyra-vale.png");
if (!lyraAsset) {
  throw new Error("Expected Captain Lyra Vale fixture asset in content asset list.");
}
if (lyraAsset.relative_path !== "npcs/captain-lyra-vale.png") {
  throw new Error(`Unexpected Captain Lyra asset relative_path: ${lyraAsset.relative_path}`);
}
if (lyraAsset.size_bytes !== 69) {
  throw new Error(`Expected Captain Lyra asset size 69, got ${lyraAsset.size_bytes}`);
}
if (lyraAsset.media_type !== "image/png") {
  throw new Error(`Expected Captain Lyra asset media_type image/png, got ${lyraAsset.media_type}`);
}
if (lyraAsset.url !== "/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png") {
  throw new Error(`Unexpected Captain Lyra asset URL: ${lyraAsset.url}`);
}
if (Object.hasOwn(lyraAsset, "data_base64")) {
  throw new Error("Expected content asset list payload to omit data_base64.");
}

const contentAsset = await requestJson(
  "/api/v1/campaigns/linden-pass/content/assets/npcs/captain-lyra-vale.png",
  contentManagerHeaders,
);
if (contentAsset.status !== 200) {
  throw new Error(`Expected content asset detail endpoint 200, got ${contentAsset.status}`);
}
if (contentAsset.payload?.asset_file?.asset_ref !== "npcs/captain-lyra-vale.png") {
  throw new Error(`Expected Captain Lyra asset detail, got ${contentAsset.payload?.asset_file?.asset_ref}`);
}
if (contentAsset.payload?.asset_file?.media_type !== "image/png") {
  throw new Error(`Expected Captain Lyra asset detail PNG media type, got ${contentAsset.payload?.asset_file?.media_type}`);
}
const assetBytes = Buffer.from(contentAsset.payload?.asset_file?.data_base64 || "", "base64");
if (assetBytes.length !== 69) {
  throw new Error(`Expected Captain Lyra asset detail to include 69 bytes, got ${assetBytes.length}`);
}

const missingContentAsset = await requestJson(
  "/api/v1/campaigns/linden-pass/content/assets/definitely-not-an-asset.png",
  contentManagerHeaders,
);
if (missingContentAsset.status !== 404 || missingContentAsset.payload?.error?.code !== "content_asset_not_found") {
  throw new Error(
    `Expected missing content asset JSON 404, got ${missingContentAsset.status} ${missingContentAsset.payload?.error?.code}`,
  );
}

const managedAssetRef = "notes/api-sigil.txt";
const managedAssetPath = `/api/v1/campaigns/linden-pass/content/assets/${managedAssetRef}`;
const managedAssetBytes = Buffer.from("API managed asset bytes", "utf8");
const managedAssetBody = {
  asset_file: {
    filename: "ignored-by-url-path.txt",
    data_base64: managedAssetBytes.toString("base64"),
  },
};
const blockedContentAssetPut = await requestJson(
  managedAssetPath,
  {},
  { method: "PUT", body: managedAssetBody },
);
if (blockedContentAssetPut.status !== 401 || blockedContentAssetPut.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated content asset PUT 401, got ${blockedContentAssetPut.status} ${blockedContentAssetPut.payload?.error?.code}`,
  );
}

const fixtureContentAssetPut = await requestJson(
  managedAssetPath,
  contentManagerHeaders,
  { method: "PUT", body: managedAssetBody },
);
if (
  fixtureContentAssetPut.status !== 403 ||
  fixtureContentAssetPut.payload?.error?.message !== "Content asset writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content asset PUT bearer requirement, got ${fixtureContentAssetPut.status} ${fixtureContentAssetPut.payload?.error?.message}`,
  );
}

const bearerPlayerContentAssetPut = await requestJson(
  managedAssetPath,
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PUT", body: managedAssetBody },
);
if (
  bearerPlayerContentAssetPut.status !== 403 ||
  bearerPlayerContentAssetPut.payload?.error?.message !== "You do not have permission to manage campaign content."
) {
  throw new Error(
    `Expected bearer player content asset PUT forbidden, got ${bearerPlayerContentAssetPut.status} ${bearerPlayerContentAssetPut.payload?.error?.message}`,
  );
}

const invalidContentAssetPut = await requestJson(
  managedAssetPath,
  bearerContentManagerHeaders,
  { method: "PUT", body: { asset_file: { filename: "api-sigil.txt", data_base64: "%%%invalid%%%" } } },
);
if (
  invalidContentAssetPut.status !== 400 ||
  invalidContentAssetPut.payload?.error?.message !== "asset_file data_base64 must be valid base64."
) {
  throw new Error(
    `Expected content asset PUT base64 validation, got ${invalidContentAssetPut.status} ${invalidContentAssetPut.payload?.error?.message}`,
  );
}

const missingCampaignContentAssetPut = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/content/assets/notes/api-sigil.txt",
  bearerContentManagerHeaders,
  { method: "PUT", body: managedAssetBody },
);
if (
  missingCampaignContentAssetPut.status !== 404 ||
  missingCampaignContentAssetPut.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing campaign content asset PUT 404, got ${missingCampaignContentAssetPut.status} ${missingCampaignContentAssetPut.payload?.error?.code}`,
  );
}

const contentAssetPut = await requestJson(
  managedAssetPath,
  bearerContentManagerHeaders,
  { method: "PUT", body: managedAssetBody },
);
if (
  contentAssetPut.status !== 200 ||
  contentAssetPut.payload?.asset_file?.asset_ref !== managedAssetRef ||
  contentAssetPut.payload?.asset_file?.relative_path !== managedAssetRef ||
  contentAssetPut.payload?.asset_file?.media_type !== "text/plain" ||
  contentAssetPut.payload?.asset_file?.size_bytes !== managedAssetBytes.length
) {
  throw new Error(
    `Expected content asset PUT summary payload, got ${contentAssetPut.status} ${JSON.stringify(contentAssetPut.payload)}`,
  );
}
if (Object.hasOwn(contentAssetPut.payload?.asset_file || {}, "data_base64")) {
  throw new Error("Expected content asset PUT payload to omit data_base64.");
}
const managedAssetFilePath = path.join(campaignsDir, "linden-pass", "assets", ...managedAssetRef.split("/"));
if (!existsSync(managedAssetFilePath) || readFileSync(managedAssetFilePath).toString("utf8") !== "API managed asset bytes") {
  throw new Error("Expected content asset PUT to write managed asset bytes into the copied fixture tree.");
}

const contentAssetsAfterPut = await requestJson("/api/v1/campaigns/linden-pass/content/assets", contentManagerHeaders);
if (!contentAssetsAfterPut.payload?.assets?.some((item) => item.asset_ref === managedAssetRef)) {
  throw new Error(`Expected content assets list to include ${managedAssetRef} after PUT.`);
}

const managedContentAsset = await requestJson(managedAssetPath, contentManagerHeaders);
if (
  managedContentAsset.status !== 200 ||
  Buffer.from(managedContentAsset.payload?.asset_file?.data_base64 || "", "base64").toString("utf8") !==
    "API managed asset bytes"
) {
  throw new Error(
    `Expected managed content asset detail to return written bytes, got ${managedContentAsset.status} ${JSON.stringify(managedContentAsset.payload)}`,
  );
}

const fixtureContentAssetDelete = await requestJson(
  managedAssetPath,
  contentManagerHeaders,
  { method: "DELETE" },
);
if (
  fixtureContentAssetDelete.status !== 403 ||
  fixtureContentAssetDelete.payload?.error?.message !== "Content asset writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content asset DELETE bearer requirement, got ${fixtureContentAssetDelete.status} ${fixtureContentAssetDelete.payload?.error?.message}`,
  );
}

const contentAssetDelete = await requestJson(
  managedAssetPath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  contentAssetDelete.status !== 200 ||
  contentAssetDelete.payload?.deleted?.asset_ref !== managedAssetRef ||
  contentAssetDelete.payload?.deleted?.relative_path !== managedAssetRef
) {
  throw new Error(
    `Expected content asset DELETE payload, got ${contentAssetDelete.status} ${JSON.stringify(contentAssetDelete.payload)}`,
  );
}
if (existsSync(managedAssetFilePath)) {
  throw new Error("Expected content asset DELETE to remove managed asset from the copied fixture tree.");
}

const missingManagedAssetDelete = await requestJson(
  managedAssetPath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  missingManagedAssetDelete.status !== 404 ||
  missingManagedAssetDelete.payload?.error?.code !== "content_asset_not_found"
) {
  throw new Error(
    `Expected missing managed content asset DELETE 404, got ${missingManagedAssetDelete.status} ${missingManagedAssetDelete.payload?.error?.code}`,
  );
}

const contentPages = await requestJson("/api/v1/campaigns/linden-pass/content/pages", contentManagerHeaders);
if (contentPages.status !== 200) {
  throw new Error(`Expected content pages list endpoint 200, got ${contentPages.status}`);
}
if (!Array.isArray(contentPages.payload?.pages) || contentPages.payload.pages.length !== 29) {
  throw new Error(`Expected 29 fixture content pages, got ${contentPages.payload?.pages?.length}`);
}
for (const page of contentPages.payload.pages) {
  if (Object.hasOwn(page, "body_markdown")) {
    throw new Error(`Expected content page list payload to omit body_markdown for ${page.page_ref}`);
  }
}
const portMeridianInList = contentPages.payload.pages.find((item) => item.page_ref === "locations/port-meridian");
if (!portMeridianInList) {
  throw new Error("Expected Port Meridian content page in fixture list payload.");
}
if (portMeridianInList.relative_path !== "locations/port-meridian.md") {
  throw new Error(`Unexpected Port Meridian relative_path: ${portMeridianInList.relative_path}`);
}
if (portMeridianInList.page?.route_slug !== "locations/port-meridian") {
  throw new Error(`Unexpected Port Meridian route slug: ${portMeridianInList.page?.route_slug}`);
}
if (portMeridianInList.can_hard_delete !== true) {
  throw new Error(`Expected fixture Port Meridian hard-delete to be available, got ${portMeridianInList.can_hard_delete}`);
}
if (!Array.isArray(portMeridianInList.hard_delete_blockers) || portMeridianInList.hard_delete_blockers.length !== 0) {
  throw new Error(`Expected no Port Meridian hard-delete blockers, got ${JSON.stringify(portMeridianInList.hard_delete_blockers)}`);
}
if (portMeridianInList.removal_status_label !== "Hard delete available") {
  throw new Error(`Expected hard delete availability label, got ${portMeridianInList.removal_status_label}`);
}
if (portMeridianInList.removal_guidance !== "Hard delete is available after confirmation.") {
  throw new Error(`Expected hard delete guidance label, got ${portMeridianInList.removal_guidance}`);
}

const contentPage = await requestJson(
  "/api/v1/campaigns/linden-pass/content/pages/locations/port-meridian",
  contentManagerHeaders,
);
if (contentPage.status !== 200) {
  throw new Error(`Expected content page detail endpoint 200, got ${contentPage.status}`);
}
if (!contentPage.payload?.page_file || typeof contentPage.payload.page_file.body_markdown !== "string" || !contentPage.payload.page_file.body_markdown) {
  throw new Error("Expected content page detail payload to include non-empty body_markdown.");
}
if (contentPage.payload.page_file.page?.route_slug !== "locations/port-meridian") {
  throw new Error(`Expected Port Meridian content detail route slug, got ${contentPage.payload.page_file?.page?.route_slug}`);
}
if (!contentPage.payload.page_file.can_hard_delete) {
  throw new Error(`Expected fixture Port Meridian hard-delete to be available, got ${contentPage.payload.page_file.can_hard_delete}`);
}
if (typeof contentPage.payload.page_file.body_markdown !== "string" || !contentPage.payload.page_file.body_markdown.includes("Port Meridian is a layered trade city")) {
  throw new Error(`Unexpected Port Meridian body markdown: ${contentPage.payload.page_file?.body_markdown}`);
}

const missingContentPage = await requestJson(
  "/api/v1/campaigns/linden-pass/content/pages/definitely-not-a-page",
  contentManagerHeaders,
);
if (missingContentPage.status !== 404 || missingContentPage.payload?.error?.code !== "content_page_not_found") {
  throw new Error(`Expected missing content page JSON 404, got ${missingContentPage.status} ${missingContentPage.payload?.error?.code}`);
}

const managedPageRef = "notes/api-field-report";
const managedPagePath = `/api/v1/campaigns/linden-pass/content/pages/${managedPageRef}`;
const managedPageBody = {
  metadata: {
    title: "API Field Report",
    section: "Notes",
    type: "note",
    summary: "A published note created through the TypeScript content API.",
    published: true,
    reveal_after_session: 0,
  },
  body_markdown: "The tower relay is stable, but the east pier wards are flickering.",
};
const blockedContentPagePut = await requestJson(
  managedPagePath,
  {},
  { method: "PUT", body: managedPageBody },
);
if (blockedContentPagePut.status !== 401 || blockedContentPagePut.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated content page PUT 401, got ${blockedContentPagePut.status} ${blockedContentPagePut.payload?.error?.code}`,
  );
}

const fixtureContentPagePut = await requestJson(
  managedPagePath,
  contentManagerHeaders,
  { method: "PUT", body: managedPageBody },
);
if (
  fixtureContentPagePut.status !== 403 ||
  fixtureContentPagePut.payload?.error?.message !== "Content page writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content page PUT bearer requirement, got ${fixtureContentPagePut.status} ${fixtureContentPagePut.payload?.error?.message}`,
  );
}

const bearerPlayerContentPagePut = await requestJson(
  managedPagePath,
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PUT", body: managedPageBody },
);
if (
  bearerPlayerContentPagePut.status !== 403 ||
  bearerPlayerContentPagePut.payload?.error?.message !== "You do not have permission to manage campaign content."
) {
  throw new Error(
    `Expected bearer player content page PUT forbidden, got ${bearerPlayerContentPagePut.status} ${bearerPlayerContentPagePut.payload?.error?.message}`,
  );
}

const invalidContentPagePut = await requestJson(
  managedPagePath,
  bearerContentManagerHeaders,
  { method: "PUT", body: { metadata: [], body_markdown: "Nope" } },
);
if (
  invalidContentPagePut.status !== 400 ||
  invalidContentPagePut.payload?.error?.message !== "Page metadata must be an object."
) {
  throw new Error(
    `Expected content page PUT metadata validation, got ${invalidContentPagePut.status} ${invalidContentPagePut.payload?.error?.message}`,
  );
}

const missingCampaignContentPagePut = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/content/pages/notes/api-field-report",
  bearerContentManagerHeaders,
  { method: "PUT", body: managedPageBody },
);
if (
  missingCampaignContentPagePut.status !== 404 ||
  missingCampaignContentPagePut.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing campaign content page PUT 404, got ${missingCampaignContentPagePut.status} ${missingCampaignContentPagePut.payload?.error?.code}`,
  );
}

const contentPagePut = await requestJson(
  managedPagePath,
  bearerContentManagerHeaders,
  { method: "PUT", body: managedPageBody },
);
if (
  contentPagePut.status !== 200 ||
  contentPagePut.payload?.page_file?.page_ref !== managedPageRef ||
  contentPagePut.payload?.page_file?.page?.title !== "API Field Report" ||
  contentPagePut.payload?.page_file?.page?.is_visible !== true ||
  !contentPagePut.payload?.page_file?.body_markdown?.includes("east pier wards")
) {
  throw new Error(
    `Expected content page PUT payload, got ${contentPagePut.status} ${JSON.stringify(contentPagePut.payload)}`,
  );
}
const managedPageFilePath = path.join(campaignsDir, "linden-pass", "content", ...`${managedPageRef}.md`.split("/"));
if (!existsSync(managedPageFilePath) || !readFileSync(managedPageFilePath, "utf8").includes("API Field Report")) {
  throw new Error("Expected content page PUT to write markdown into the copied fixture tree.");
}

const contentPagesAfterPut = await requestJson("/api/v1/campaigns/linden-pass/content/pages", contentManagerHeaders);
if (!contentPagesAfterPut.payload?.pages?.some((item) => item.page_ref === managedPageRef)) {
  throw new Error(`Expected content pages list to include ${managedPageRef} after PUT.`);
}

const fixtureContentPageDelete = await requestJson(
  managedPagePath,
  contentManagerHeaders,
  { method: "DELETE" },
);
if (
  fixtureContentPageDelete.status !== 403 ||
  fixtureContentPageDelete.payload?.error?.message !== "Content page writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture content page DELETE bearer requirement, got ${fixtureContentPageDelete.status} ${fixtureContentPageDelete.payload?.error?.message}`,
  );
}

const contentPageDelete = await requestJson(
  managedPagePath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  contentPageDelete.status !== 200 ||
  contentPageDelete.payload?.deleted?.page_ref !== managedPageRef ||
  contentPageDelete.payload?.deleted?.relative_path !== `${managedPageRef}.md`
) {
  throw new Error(
    `Expected content page DELETE payload, got ${contentPageDelete.status} ${JSON.stringify(contentPageDelete.payload)}`,
  );
}
if (existsSync(managedPageFilePath)) {
  throw new Error("Expected content page DELETE to remove managed page from the copied fixture tree.");
}

const targetPageRef = "notes/api-reference-target";
const referrerPageRef = "notes/api-reference-hub";
const targetPagePath = `/api/v1/campaigns/linden-pass/content/pages/${targetPageRef}`;
const referrerPagePath = `/api/v1/campaigns/linden-pass/content/pages/${referrerPageRef}`;
const targetPageCreate = await requestJson(
  targetPagePath,
  bearerContentManagerHeaders,
  {
    method: "PUT",
    body: {
      metadata: {
        title: "API Reference Target",
        section: "Notes",
        type: "note",
        summary: "A page intended to be linked.",
        published: true,
        reveal_after_session: 0,
      },
      body_markdown: "This target page should be blocked from hard delete when linked.",
    },
  },
);
if (targetPageCreate.status !== 200) {
  throw new Error(`Expected target page create 200, got ${targetPageCreate.status}`);
}
const referrerPageCreate = await requestJson(
  referrerPagePath,
  bearerContentManagerHeaders,
  {
    method: "PUT",
    body: {
      metadata: {
        title: "API Reference Hub",
        section: "Notes",
        type: "note",
        summary: "This page links to the reference target.",
        published: true,
        reveal_after_session: 0,
      },
      body_markdown: "Cross-check with [[API Reference Target]].",
    },
  },
);
if (referrerPageCreate.status !== 200) {
  throw new Error(`Expected referrer page create 200, got ${referrerPageCreate.status}`);
}

const contentPagesWithBacklink = await requestJson("/api/v1/campaigns/linden-pass/content/pages", contentManagerHeaders);
const targetListing = contentPagesWithBacklink.payload?.pages?.find((item) => item.page_ref === targetPageRef);
if (
  targetListing?.can_hard_delete !== false ||
  !targetListing?.hard_delete_blockers?.some((blocker) => blocker.includes("Backlinked from API Reference Hub."))
) {
  throw new Error(`Expected backlink hard-delete blocker, got ${JSON.stringify(targetListing)}`);
}

const blockedPageDelete = await requestJson(
  targetPagePath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (
  blockedPageDelete.status !== 409 ||
  blockedPageDelete.payload?.error?.code !== "hard_delete_blocked" ||
  blockedPageDelete.payload?.error?.details?.removal_safety?.can_hard_delete !== false
) {
  throw new Error(
    `Expected hard-delete blocked response, got ${blockedPageDelete.status} ${JSON.stringify(blockedPageDelete.payload)}`,
  );
}

const forcedPageDelete = await requestJson(
  targetPagePath,
  bearerContentManagerHeaders,
  { method: "DELETE", body: { force: true } },
);
if (forcedPageDelete.status !== 200 || forcedPageDelete.payload?.deleted?.page_ref !== targetPageRef) {
  throw new Error(
    `Expected forced target page delete 200, got ${forcedPageDelete.status} ${JSON.stringify(forcedPageDelete.payload)}`,
  );
}
const referrerPageDelete = await requestJson(
  referrerPagePath,
  bearerContentManagerHeaders,
  { method: "DELETE" },
);
if (referrerPageDelete.status !== 200 || referrerPageDelete.payload?.deleted?.page_ref !== referrerPageRef) {
  throw new Error(
    `Expected referrer page delete 200, got ${referrerPageDelete.status} ${JSON.stringify(referrerPageDelete.payload)}`,
  );
}

const missing = await requestJson("/api/v1/campaigns/definitely-not-a-campaign");
if (missing.status !== 404) {
  throw new Error(`Expected missing campaign to return 404, got ${missing.status}`);
}
if (missing.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected campaign_not_found error code, got ${missing.payload?.error?.code}`);
}

const wikiHome = await requestJson("/api/v1/campaigns/linden-pass/wiki");
if (wikiHome.status !== 200) {
  throw new Error(`Expected wiki home 200, got ${wikiHome.status}`);
}
if (wikiHome.payload?.result_count !== 25) {
  throw new Error(`Expected 25 visible fixture wiki pages, got ${wikiHome.payload?.result_count}`);
}
if (wikiHome.payload?.overview_page !== null) {
  throw new Error("Expected deprecated Overview page to stay hidden from wiki home.");
}
if (wikiHome.payload?.latest_session_summary?.route_slug !== "sessions/session-2-the-brass-vault") {
  throw new Error(
    `Expected latest session summary route slug, got ${wikiHome.payload?.latest_session_summary?.route_slug}`,
  );
}
const wikiSections = wikiHome.payload?.section_navigation || [];
if (wikiSections[0]?.section_name !== "Sessions" || wikiSections[2]?.section_name !== "Locations") {
  throw new Error(`Expected Flask-compatible wiki section ordering, got ${JSON.stringify(wikiSections.slice(0, 3))}`);
}

const wikiSection = await requestJson("/api/v1/campaigns/linden-pass/wiki/sections/locations");
if (wikiSection.status !== 200) {
  throw new Error(`Expected wiki section 200, got ${wikiSection.status}`);
}
if (wikiSection.payload?.section_name !== "Locations" || wikiSection.payload?.page_count !== 5) {
  throw new Error(`Expected Locations section with five pages, got ${JSON.stringify(wikiSection.payload)}`);
}
if (wikiSection.payload?.show_subsections !== true) {
  throw new Error("Expected Locations section to expose subsection grouping.");
}
if (wikiSection.payload?.pages?.[0]?.route_slug !== "locations/harbor-row") {
  throw new Error(`Expected Harbor Row first in Locations section, got ${wikiSection.payload?.pages?.[0]?.route_slug}`);
}

const wikiPage = await requestJson("/api/v1/campaigns/linden-pass/wiki/pages/locations/port-meridian");
if (wikiPage.status !== 200) {
  throw new Error(`Expected wiki page 200, got ${wikiPage.status}`);
}
if (wikiPage.payload?.page?.route_slug !== "locations/port-meridian") {
  throw new Error(`Expected Port Meridian page, got ${wikiPage.payload?.page?.route_slug}`);
}
if (
  wikiPage.payload?.page?.body_html !==
  "<p>Port Meridian is a layered trade city of piers, markets, guild offices, and storm channels cut into the cliff.</p>"
) {
  throw new Error(`Unexpected Port Meridian body_html: ${wikiPage.payload?.page?.body_html}`);
}
if (wikiPage.payload?.page?.image !== null) {
  throw new Error("Expected Port Meridian to have no image payload.");
}

const imagePage = await requestJson("/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale");
if (imagePage.status !== 200) {
  throw new Error(`Expected Captain Lyra Vale page 200, got ${imagePage.status}`);
}
if (imagePage.payload?.page?.image?.media_type !== "image/png") {
  throw new Error(`Expected PNG image metadata, got ${JSON.stringify(imagePage.payload?.page?.image)}`);
}
if (imagePage.payload?.page?.image?.url !== "/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png") {
  throw new Error(`Expected Flask asset URL, got ${imagePage.payload?.page?.image?.url}`);
}

const missingWikiCampaign = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/wiki");
if (missingWikiCampaign.status !== 404 || missingWikiCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing wiki campaign JSON 404, got ${missingWikiCampaign.status}`);
}

const missingWikiSection = await requestJson("/api/v1/campaigns/linden-pass/wiki/sections/definitely-not-a-section");
if (missingWikiSection.status !== 404 || missingWikiSection.payload?.error?.code !== "wiki_section_not_found") {
  throw new Error(`Expected missing wiki section JSON 404, got ${missingWikiSection.status}`);
}

const missingWikiPage = await requestJson("/api/v1/campaigns/linden-pass/wiki/pages/definitely-not-a-page");
if (missingWikiPage.status !== 404 || missingWikiPage.payload?.error?.code !== "wiki_page_not_found") {
  throw new Error(`Expected missing wiki page JSON 404, got ${missingWikiPage.status}`);
}

const session = await requestJson("/api/v1/campaigns/linden-pass/session");
if (session.status !== 200 || session.payload?.ok !== true) {
  throw new Error(`Expected session endpoint 200 ok, got ${session.status}`);
}
if (session.payload?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected session campaign slug linden-pass, got ${session.payload?.campaign?.slug}`);
}
if (session.payload?.permissions?.can_manage_session !== false) {
  throw new Error(`Expected read-only session permissions, got ${session.payload?.permissions?.can_manage_session}`);
}
if (session.payload?.permissions?.can_post_messages !== false) {
  throw new Error(`Expected can_post_messages false, got ${session.payload?.permissions?.can_post_messages}`);
}
if (session.payload?.active_session !== null) {
  throw new Error(`Expected active_session null in fixture session response, got ${JSON.stringify(session.payload?.active_session)}`);
}
if (!Array.isArray(session.payload?.messages) || session.payload.messages.length !== 0) {
  throw new Error(`Expected empty messages array in fixture session response, got ${JSON.stringify(session.payload?.messages)}`);
}
if (session.payload?.session_message_recipient_player_choices?.length !== 0) {
  throw new Error("Expected no recipient choices in fixture session read mode.");
}
if (session.payload?.show_session_dm_passive_scores !== false) {
  throw new Error("Expected show_session_dm_passive_scores false in fixture session response.");
}
if (typeof session.payload?.session_revision !== "number" || session.payload.session_revision < 0) {
  throw new Error(`Expected non-negative numeric session_revision, got ${session.payload?.session_revision}`);
}
if (typeof session.payload?.session_view_token !== "string" || !/^[0-9a-f]{12}$/i.test(session.payload.session_view_token)) {
  throw new Error(`Expected 12-char hex session_view_token, got ${session.payload?.session_view_token}`);
}
if (session.payload?.staged_articles !== undefined) {
  throw new Error("Expected fixture read-only session response to omit staged_articles.");
}
if (session.payload?.revealed_articles !== undefined) {
  throw new Error("Expected fixture read-only session response to omit revealed_articles.");
}
if (session.payload?.session_logs !== undefined) {
  throw new Error("Expected fixture read-only session response to omit session_logs.");
}
if (session.payload?.session_dm_passive_scores !== undefined) {
  throw new Error("Expected fixture read-only session response to omit session_dm_passive_scores.");
}

const unchangedSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  "X-Live-Revision": String(session.payload?.session_revision),
  "X-Live-View-Token": String(session.payload?.session_view_token),
});
if (unchangedSession.status !== 200) {
  throw new Error(`Expected unchanged session short-circuit request 200, got ${unchangedSession.status}`);
}
if (
  unchangedSession.payload?.ok !== true ||
  unchangedSession.payload?.changed !== false ||
  unchangedSession.payload?.session_revision !== session.payload?.session_revision ||
  unchangedSession.payload?.session_view_token !== session.payload?.session_view_token ||
  Object.keys(unchangedSession.payload || {}).length !== 4
) {
  throw new Error(`Expected Flask-style unchanged payload, got ${JSON.stringify(unchangedSession.payload)}`);
}

const invalidBearerSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: "Bearer definitely-invalid-token",
});
if (invalidBearerSession.status !== 401 || invalidBearerSession.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected invalid bearer session request 401, got ${invalidBearerSession.status} ${invalidBearerSession.payload?.error?.code}`,
  );
}

const outsiderSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${outsiderApiToken}`,
});
if (outsiderSession.status !== 403 || outsiderSession.payload?.error?.code !== "forbidden") {
  throw new Error(`Expected outsider bearer session request forbidden 403, got ${outsiderSession.status}`);
}

const dmSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmSession.status !== 200 ||
  dmSession.payload?.session_revision !== 7 ||
  dmSession.payload?.permissions?.can_manage_session !== true ||
  dmSession.payload?.permissions?.can_post_messages !== true ||
  dmSession.payload?.active_session?.id !== 1 ||
  dmSession.payload?.active_session?.is_active !== true ||
  dmSession.payload?.messages?.length !== 3 ||
  dmSession.payload?.messages?.[1]?.recipient_scope !== "dm_only" ||
  dmSession.payload?.messages?.[1]?.recipient_label !== "DM" ||
  dmSession.payload?.staged_articles?.length !== 1 ||
  dmSession.payload?.staged_articles?.[0]?.source_kind !== "page" ||
  dmSession.payload?.staged_articles?.[0]?.source?.title !== "Captain Lyra Vale" ||
  dmSession.payload?.revealed_articles?.length !== 1 ||
  dmSession.payload?.revealed_articles?.[0]?.source_kind !== "systems" ||
  dmSession.payload?.revealed_articles?.[0]?.body_format !== "html" ||
  dmSession.payload?.revealed_articles?.[0]?.image?.url !== "/api/v1/campaigns/linden-pass/session/articles/102/image" ||
  dmSession.payload?.messages?.[2]?.article?.id !== 102 ||
  dmSession.payload?.messages?.[2]?.article?.image?.filename !== "revealed-note.png" ||
  dmSession.payload?.session_logs?.length !== 1 ||
  dmSession.payload?.session_logs?.[0]?.session?.id !== 2 ||
  dmSession.payload?.session_logs?.[0]?.message_count !== 1 ||
  dmSession.payload?.session_logs?.[0]?.detail_url !== "/api/v1/campaigns/linden-pass/session/logs/2" ||
  dmSession.payload?.show_session_dm_passive_scores !== true ||
  dmSession.payload?.session_dm_passive_scores?.length !== 0
) {
  throw new Error(`Unexpected DM session payload: ${JSON.stringify(dmSession.payload)}`);
}

const blockedDmContent = await requestJson("/api/v1/campaigns/linden-pass/dm-content");
if (blockedDmContent.status !== 401 || blockedDmContent.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated DM Content to return auth_required 401, got ${blockedDmContent.status} ${blockedDmContent.payload?.error?.code}`,
  );
}

const playerDmContent = await requestJson("/api/v1/campaigns/linden-pass/dm-content", {
  "X-CPW-Fixture-Role": "player",
});
if (playerDmContent.status !== 403 || playerDmContent.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture player DM Content to return forbidden 403, got ${playerDmContent.status} ${playerDmContent.payload?.error?.code}`,
  );
}

const dmContent = await requestJson("/api/v1/campaigns/linden-pass/dm-content", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmContent.status !== 200 ||
  dmContent.payload?.ok !== true ||
  dmContent.payload?.campaign?.slug !== "linden-pass" ||
  dmContent.payload?.permissions?.can_manage_dm_content !== true ||
  dmContent.payload?.statblocks?.length !== 1 ||
  dmContent.payload?.statblocks?.[0]?.title !== "Dock Tough" ||
  dmContent.payload?.statblocks?.[0]?.parser_feedback?.summary !==
    "Parsed combat fields: AC 12, HP 16, Speed 30 ft. (30 ft. movement), Init +2." ||
  dmContent.payload?.conditions?.length !== 1 ||
  dmContent.payload?.conditions?.[0]?.name !== "Salt-Burned" ||
  dmContent.payload?.subpage_counts?.statblocks !== 1 ||
  dmContent.payload?.subpage_counts?.conditions !== 1 ||
  dmContent.payload?.subpage_counts?.staged_articles !== 1 ||
  dmContent.payload?.subpage_counts?.systems !== 3 ||
  Number(dmContent.payload?.subpage_counts?.player_wiki || 0) <= 0
) {
  throw new Error(`Unexpected DM Content payload: ${JSON.stringify(dmContent.payload)}`);
}

const bearerDmContent = await requestJson("/api/v1/campaigns/linden-pass/dm-content", {
  Authorization: `Bearer ${dmApiToken}`,
});
if (
  bearerDmContent.status !== 200 ||
  bearerDmContent.payload?.ok !== true ||
  bearerDmContent.payload?.statblocks?.[0]?.title !== "Dock Tough" ||
  bearerDmContent.payload?.conditions?.[0]?.name !== "Salt-Burned"
) {
  throw new Error(`Unexpected bearer DM Content payload: ${JSON.stringify(bearerDmContent.payload)}`);
}

const fixtureStatblockCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/statblocks",
  { "X-CPW-Fixture-Role": "dm" },
  {
    method: "POST",
    body: {
      filename: "fixture-blocked.md",
      markdown_text: "# Fixture Blocked\n\nHit Points 5\nSpeed 30 ft.",
    },
  },
);
if (
  fixtureStatblockCreate.status !== 403 ||
  fixtureStatblockCreate.payload?.error?.message !== "DM Content writes require bearer API authentication."
) {
  throw new Error(`Expected fixture statblock create bearer requirement, got ${JSON.stringify(fixtureStatblockCreate.payload)}`);
}

const playerStatblockCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/statblocks",
  { Authorization: `Bearer ${playerApiToken}` },
  {
    method: "POST",
    body: {
      filename: "player-blocked.md",
      markdown_text: "# Player Blocked\n\nHit Points 5\nSpeed 30 ft.",
    },
  },
);
if (
  playerStatblockCreate.status !== 403 ||
  playerStatblockCreate.payload?.error?.message !== "You do not have permission to manage DM Content."
) {
  throw new Error(`Expected player statblock create forbidden, got ${JSON.stringify(playerStatblockCreate.payload)}`);
}

const invalidStatblockCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/statblocks",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: {
      filename: "bad-statblock.txt",
      markdown_text: "# Bad\n\nHit Points 5\nSpeed 30 ft.",
    },
  },
);
if (
  invalidStatblockCreate.status !== 400 ||
  invalidStatblockCreate.payload?.error?.message !== "DM Content statblock uploads must use .md or .markdown files."
) {
  throw new Error(`Expected invalid statblock create validation, got ${JSON.stringify(invalidStatblockCreate.payload)}`);
}

const statblockCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/statblocks",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: {
      filename: "dock-runner.md",
      subsection: "Malverine Minions",
      markdown_text: "# Dock Runner\n\nArmor Class 13\nHit Points 22\nSpeed 30 ft.\n\nDEX 14 (+2)\n",
    },
  },
);
const createdStatblock = statblockCreate.payload?.statblock;
if (
  statblockCreate.status !== 200 ||
  statblockCreate.payload?.ok !== true ||
  createdStatblock?.title !== "Dock Runner" ||
  createdStatblock?.subsection !== "Malverine Minions" ||
  createdStatblock?.parser_feedback?.summary !==
    "Parsed combat fields: AC 13, HP 22, Speed 30 ft. (30 ft. movement), Init +2." ||
  createdStatblock?.created_by_user_id !== 81 ||
  createdStatblock?.updated_by_user_id !== 81
) {
  throw new Error(`Unexpected statblock create payload: ${JSON.stringify(statblockCreate.payload)}`);
}

const emptyStatblockUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/statblocks/${createdStatblock.id}`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PUT", body: {} },
);
if (
  emptyStatblockUpdate.status !== 400 ||
  emptyStatblockUpdate.payload?.error?.message !== "Provide markdown_text, body_markdown, or subsection to update a statblock."
) {
  throw new Error(`Expected empty statblock update validation, got ${JSON.stringify(emptyStatblockUpdate.payload)}`);
}

const statblockUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/statblocks/${createdStatblock.id}`,
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "PUT",
    body: {
      subsection: "Dock Crew",
      markdown_text: "# Dock Runner Captain\n\nArmor Class 15\nHit Points 36\nSpeed 35 ft.\n\nDEX 16 (+3)\n",
    },
  },
);
if (
  statblockUpdate.status !== 200 ||
  statblockUpdate.payload?.statblock?.title !== "Dock Runner Captain" ||
  statblockUpdate.payload?.statblock?.subsection !== "Dock Crew" ||
  statblockUpdate.payload?.statblock?.max_hp !== 36 ||
  statblockUpdate.payload?.statblock?.movement_total !== 35 ||
  statblockUpdate.payload?.statblock?.initiative_bonus !== 3 ||
  statblockUpdate.payload?.statblock?.parser_feedback?.summary !==
    "Parsed combat fields: AC 15, HP 36, Speed 35 ft. (35 ft. movement), Init +3."
) {
  throw new Error(`Unexpected statblock update payload: ${JSON.stringify(statblockUpdate.payload)}`);
}

const missingStatblockDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/statblocks/999999",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  missingStatblockDelete.status !== 400 ||
  missingStatblockDelete.payload?.error?.message !== "That statblock could not be found."
) {
  throw new Error(`Expected missing statblock delete validation, got ${JSON.stringify(missingStatblockDelete.payload)}`);
}

const statblockDelete = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/statblocks/${createdStatblock.id}`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  statblockDelete.status !== 200 ||
  statblockDelete.payload?.statblock?.id !== createdStatblock.id ||
  statblockDelete.payload?.statblock?.title !== "Dock Runner Captain"
) {
  throw new Error(`Unexpected statblock delete payload: ${JSON.stringify(statblockDelete.payload)}`);
}

const duplicateConditionCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/conditions",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { name: "Salt Burned", description_markdown: "Duplicate normalized name." } },
);
if (
  duplicateConditionCreate.status !== 400 ||
  duplicateConditionCreate.payload?.error?.message !== "A custom condition with that name already exists."
) {
  throw new Error(`Expected duplicate condition validation, got ${JSON.stringify(duplicateConditionCreate.payload)}`);
}

const conditionCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/conditions",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: {
      name: "Off Balance",
      description_markdown: "The target has disadvantage on its next attack roll.",
    },
  },
);
const createdCondition = conditionCreate.payload?.condition;
if (
  conditionCreate.status !== 200 ||
  conditionCreate.payload?.ok !== true ||
  createdCondition?.name !== "Off Balance" ||
  createdCondition?.created_by_user_id !== 81 ||
  createdCondition?.updated_by_user_id !== 81
) {
  throw new Error(`Unexpected condition create payload: ${JSON.stringify(conditionCreate.payload)}`);
}

const emptyConditionUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/conditions/${createdCondition.id}`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PUT", body: {} },
);
if (
  emptyConditionUpdate.status !== 400 ||
  emptyConditionUpdate.payload?.error?.message !== "Provide name or description_markdown to update a custom condition."
) {
  throw new Error(`Expected empty condition update validation, got ${JSON.stringify(emptyConditionUpdate.payload)}`);
}

const conditionUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/conditions/${createdCondition.id}`,
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "PUT",
    body: {
      name: "Off Balance Revised",
      description_markdown: "The target has disadvantage on its next Dexterity check.",
    },
  },
);
if (
  conditionUpdate.status !== 200 ||
  conditionUpdate.payload?.condition?.name !== "Off Balance Revised" ||
  conditionUpdate.payload?.condition?.description_markdown !==
    "The target has disadvantage on its next Dexterity check."
) {
  throw new Error(`Unexpected condition update payload: ${JSON.stringify(conditionUpdate.payload)}`);
}

const playerConditionUpdate = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/conditions/${createdCondition.id}`,
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "PUT", body: { name: "Blocked" } },
);
if (playerConditionUpdate.status !== 403 || playerConditionUpdate.payload?.error?.code !== "forbidden") {
  throw new Error(`Expected player condition update forbidden, got ${JSON.stringify(playerConditionUpdate.payload)}`);
}

const missingConditionDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/dm-content/conditions/999999",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  missingConditionDelete.status !== 400 ||
  missingConditionDelete.payload?.error?.message !== "That custom condition could not be found."
) {
  throw new Error(`Expected missing condition delete validation, got ${JSON.stringify(missingConditionDelete.payload)}`);
}

const conditionDelete = await requestJson(
  `/api/v1/campaigns/linden-pass/dm-content/conditions/${createdCondition.id}`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  conditionDelete.status !== 200 ||
  conditionDelete.payload?.condition?.id !== createdCondition.id ||
  conditionDelete.payload?.condition?.name !== "Off Balance Revised"
) {
  throw new Error(`Unexpected condition delete payload: ${JSON.stringify(conditionDelete.payload)}`);
}

const dmContentAfterMutations = await requestJson("/api/v1/campaigns/linden-pass/dm-content", {
  Authorization: `Bearer ${dmApiToken}`,
});
if (
  dmContentAfterMutations.status !== 200 ||
  dmContentAfterMutations.payload?.statblocks?.length !== 1 ||
  dmContentAfterMutations.payload?.conditions?.length !== 1 ||
  dmContentAfterMutations.payload?.subpage_counts?.statblocks !== 1 ||
  dmContentAfterMutations.payload?.subpage_counts?.conditions !== 1 ||
  dmContentAfterMutations.payload?.statblocks?.some((statblock) => statblock.title === "Dock Runner Captain") ||
  dmContentAfterMutations.payload?.conditions?.some((condition) => condition.name === "Off Balance Revised")
) {
  throw new Error(`Unexpected DM Content payload after mutations: ${JSON.stringify(dmContentAfterMutations.payload)}`);
}

const missingDmContentCampaign = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/dm-content", {
  "X-CPW-Fixture-Role": "dm",
});
if (missingDmContentCampaign.status !== 404 || missingDmContentCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing DM Content campaign JSON 404, got ${missingDmContentCampaign.status} ${missingDmContentCampaign.payload?.error?.code}`,
  );
}

const unchangedDmSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  "X-CPW-Fixture-Role": "dm",
  "X-Live-Revision": String(dmSession.payload?.session_revision),
  "X-Live-View-Token": String(dmSession.payload?.session_view_token),
});
if (
  unchangedDmSession.status !== 200 ||
  unchangedDmSession.payload?.changed !== false ||
  unchangedDmSession.payload?.session_revision !== dmSession.payload?.session_revision ||
  unchangedDmSession.payload?.session_view_token !== dmSession.payload?.session_view_token ||
  Object.keys(unchangedDmSession.payload || {}).length !== 4
) {
  throw new Error(`Unexpected unchanged DM session payload: ${JSON.stringify(unchangedDmSession.payload)}`);
}

const bearerAdminSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerAdminSession.status !== 200 ||
  bearerAdminSession.payload?.session_revision !== 7 ||
  bearerAdminSession.payload?.permissions?.can_manage_session !== true ||
  bearerAdminSession.payload?.messages?.length !== 3 ||
  bearerAdminSession.payload?.staged_articles?.length !== 1 ||
  bearerAdminSession.payload?.session_logs?.[0]?.session?.id !== 2
) {
  throw new Error(`Unexpected bearer admin session payload: ${JSON.stringify(bearerAdminSession.payload)}`);
}

const unchangedBearerAdminSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${liveApiToken}`,
  "X-Live-Revision": String(bearerAdminSession.payload?.session_revision),
  "X-Live-View-Token": String(bearerAdminSession.payload?.session_view_token),
});
if (
  unchangedBearerAdminSession.status !== 200 ||
  unchangedBearerAdminSession.payload?.changed !== false ||
  unchangedBearerAdminSession.payload?.session_revision !== bearerAdminSession.payload?.session_revision ||
  unchangedBearerAdminSession.payload?.session_view_token !== bearerAdminSession.payload?.session_view_token ||
  Object.keys(unchangedBearerAdminSession.payload || {}).length !== 4
) {
  throw new Error(`Unexpected unchanged bearer admin session payload: ${JSON.stringify(unchangedBearerAdminSession.payload)}`);
}

const playerSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  "X-CPW-Fixture-Role": "player",
});
if (
  playerSession.status !== 200 ||
  playerSession.payload?.permissions?.can_manage_session !== false ||
  playerSession.payload?.permissions?.can_post_messages !== true ||
  playerSession.payload?.active_session?.id !== 1 ||
  playerSession.payload?.messages?.length !== 2 ||
  playerSession.payload?.messages?.some((message) => message.recipient_scope === "dm_only") ||
  playerSession.payload?.messages?.[1]?.article?.id !== 102 ||
  playerSession.payload?.staged_articles !== undefined ||
  playerSession.payload?.revealed_articles !== undefined ||
  playerSession.payload?.session_logs !== undefined ||
  playerSession.payload?.session_dm_passive_scores !== undefined
) {
  throw new Error(`Unexpected player session payload: ${JSON.stringify(playerSession.payload)}`);
}

const bearerPlayerSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (
  bearerPlayerSession.status !== 200 ||
  bearerPlayerSession.payload?.permissions?.can_manage_session !== false ||
  bearerPlayerSession.payload?.permissions?.can_post_messages !== true ||
  bearerPlayerSession.payload?.active_session?.id !== 1 ||
  bearerPlayerSession.payload?.messages?.length !== 2 ||
  bearerPlayerSession.payload?.messages?.some((message) => message.recipient_scope === "dm_only") ||
  bearerPlayerSession.payload?.staged_articles !== undefined ||
  bearerPlayerSession.payload?.session_logs !== undefined
) {
  throw new Error(`Unexpected bearer player session payload: ${JSON.stringify(bearerPlayerSession.payload)}`);
}

const blockedSessionMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  {},
  { method: "POST", body: { body: "No auth should not post." } },
);
if (blockedSessionMessage.status !== 401 || blockedSessionMessage.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session message POST 401, got ${blockedSessionMessage.status} ${blockedSessionMessage.payload?.error?.code}`,
  );
}

const fixtureSessionMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { "X-CPW-Fixture-Role": "player" },
  { method: "POST", body: { body: "Fixture role writes stay blocked." } },
);
if (fixtureSessionMessage.status !== 403 || fixtureSessionMessage.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture session message POST forbidden 403, got ${fixtureSessionMessage.status} ${fixtureSessionMessage.payload?.error?.code}`,
  );
}

const outsiderSessionMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${outsiderApiToken}` },
  { method: "POST", body: { body: "Outsider should not post." } },
);
if (outsiderSessionMessage.status !== 403 || outsiderSessionMessage.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected outsider session message POST forbidden 403, got ${outsiderSessionMessage.status} ${outsiderSessionMessage.payload?.error?.code}`,
  );
}

const malformedSessionMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST", body: "not-json" },
);
if (malformedSessionMessage.status !== 400 || malformedSessionMessage.payload?.error?.code !== "invalid_json") {
  throw new Error(
    `Expected malformed session message POST invalid_json 400, got ${malformedSessionMessage.status} ${malformedSessionMessage.payload?.error?.code}`,
  );
}

const blankSessionMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST", body: { body: "   " } },
);
if (
  blankSessionMessage.status !== 400 ||
  blankSessionMessage.payload?.error?.message !== "Enter a message before posting it to the chat."
) {
  throw new Error(
    `Expected blank session message validation, got ${blankSessionMessage.status} ${blankSessionMessage.payload?.error?.message}`,
  );
}

const invalidAudienceSessionMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST", body: { body: "Hello.", recipient_scope: "table" } },
);
if (
  invalidAudienceSessionMessage.status !== 400 ||
  invalidAudienceSessionMessage.payload?.error?.message !== "Message audience must be global, dm_only, or player."
) {
  throw new Error(
    `Expected invalid audience validation, got ${invalidAudienceSessionMessage.status} ${invalidAudienceSessionMessage.payload?.error?.message}`,
  );
}

const missingTargetPlayerMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { body: "Choose someone.", recipient_scope: "player" } },
);
if (
  missingTargetPlayerMessage.status !== 400 ||
  missingTargetPlayerMessage.payload?.error?.message !== "Choose a valid player for the targeted message."
) {
  throw new Error(
    `Expected missing target-player validation, got ${missingTargetPlayerMessage.status} ${missingTargetPlayerMessage.payload?.error?.message}`,
  );
}

const inactiveTargetPlayerMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { body: "Target inactive player.", recipient_scope: "player", recipient_user_id: 78 } },
);
if (
  inactiveTargetPlayerMessage.status !== 400 ||
  inactiveTargetPlayerMessage.payload?.error?.message !== "Choose an active campaign player for the targeted message."
) {
  throw new Error(
    `Expected inactive target-player validation, got ${inactiveTargetPlayerMessage.status} ${inactiveTargetPlayerMessage.payload?.error?.message}`,
  );
}

const playerDmOnlyMessageBody = "Player whispers to the DM.";
const playerDmOnlyMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST", body: { body: ` ${playerDmOnlyMessageBody} `, recipient_scope: "dm_only" } },
);
if (
  playerDmOnlyMessage.status !== 200 ||
  playerDmOnlyMessage.payload?.message?.body_text !== playerDmOnlyMessageBody ||
  playerDmOnlyMessage.payload?.message?.author_user_id !== 79 ||
  playerDmOnlyMessage.payload?.message?.author_display_name !== "Fixture Token Player" ||
  playerDmOnlyMessage.payload?.message?.recipient_scope !== "dm_only" ||
  playerDmOnlyMessage.payload?.message?.recipient_label !== "DM"
) {
  throw new Error(`Unexpected player DM-only message payload: ${JSON.stringify(playerDmOnlyMessage.payload)}`);
}

const dmTargetedMessageBody = "DM sends a targeted player note.";
const dmTargetedMessage = await requestJson(
  "/api/v1/campaigns/linden-pass/session/messages",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: { body: dmTargetedMessageBody, recipient_scope: "player", recipient_user_id: 79 },
  },
);
if (
  dmTargetedMessage.status !== 200 ||
  dmTargetedMessage.payload?.message?.body_text !== dmTargetedMessageBody ||
  dmTargetedMessage.payload?.message?.author_user_id !== 81 ||
  dmTargetedMessage.payload?.message?.recipient_scope !== "player" ||
  dmTargetedMessage.payload?.message?.recipient_user_id !== 79 ||
  dmTargetedMessage.payload?.message?.recipient_label !== "Fixture Token Player"
) {
  throw new Error(`Unexpected DM targeted message payload: ${JSON.stringify(dmTargetedMessage.payload)}`);
}

const playerSessionAfterMessageWrites = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${playerApiToken}`,
});
const playerSessionMessageBodiesAfterWrites = playerSessionAfterMessageWrites.payload?.messages?.map((message) => message.body_text) || [];
if (
  playerSessionAfterMessageWrites.status !== 200 ||
  !playerSessionMessageBodiesAfterWrites.includes(playerDmOnlyMessageBody) ||
  !playerSessionMessageBodiesAfterWrites.includes(dmTargetedMessageBody) ||
  playerSessionMessageBodiesAfterWrites.includes("DM-only note.") ||
  playerSessionAfterMessageWrites.payload?.session_message_recipient_player_choices?.[0]?.label !== "Fixture Token Player"
) {
  throw new Error(`Unexpected player session after message writes: ${JSON.stringify(playerSessionAfterMessageWrites.payload)}`);
}

const dmSessionAfterMessageWrites = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${dmApiToken}`,
});
const dmSessionMessagesAfterWrites = dmSessionAfterMessageWrites.payload?.messages || [];
if (
  dmSessionAfterMessageWrites.status !== 200 ||
  Number(dmSessionAfterMessageWrites.payload?.session_revision) !== Number(bearerAdminSession.payload?.session_revision) + 2 ||
  !dmSessionMessagesAfterWrites.some(
    (message) => message.body_text === playerDmOnlyMessageBody && message.recipient_scope === "dm_only",
  ) ||
  !dmSessionMessagesAfterWrites.some(
    (message) =>
      message.body_text === dmTargetedMessageBody &&
      message.recipient_scope === "player" &&
      message.recipient_label === "Fixture Token Player",
  )
) {
  throw new Error(`Unexpected DM session after message writes: ${JSON.stringify(dmSessionAfterMessageWrites.payload)}`);
}

const messageAssertionDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const messageAssertionRows = messageAssertionDb
  .prepare(
    "SELECT body_text, recipient_scope, recipient_user_id, author_user_id FROM campaign_session_messages WHERE body_text IN (?, ?) ORDER BY id ASC",
  )
  .all(playerDmOnlyMessageBody, dmTargetedMessageBody);
const messageRevisionRow = messageAssertionDb
  .prepare("SELECT revision, updated_by_user_id FROM campaign_session_states WHERE campaign_slug = ?")
  .get("linden-pass");
messageAssertionDb.close();
if (
  messageAssertionRows.length !== 2 ||
  messageAssertionRows[0]?.recipient_scope !== "dm_only" ||
  messageAssertionRows[0]?.author_user_id !== 79 ||
  messageAssertionRows[1]?.recipient_scope !== "player" ||
  messageAssertionRows[1]?.recipient_user_id !== 79 ||
  messageAssertionRows[1]?.author_user_id !== 81 ||
  Number(messageRevisionRow?.revision) !== Number(bearerAdminSession.payload?.session_revision) + 2 ||
  Number(messageRevisionRow?.updated_by_user_id) !== 81
) {
  throw new Error(
    `Expected persisted session messages and revision bump, got rows=${JSON.stringify(messageAssertionRows)} revision=${JSON.stringify(messageRevisionRow)}`,
  );
}

const missingSessionMessageCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/messages",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { body: "Missing campaign should return JSON 404." } },
);
if (missingSessionMessageCampaign.status !== 404 || missingSessionMessageCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing session message campaign JSON 404, got ${missingSessionMessageCampaign.status} ${missingSessionMessageCampaign.payload?.error?.code}`,
  );
}

const blockedSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  {},
  { method: "POST", body: { mode: "manual", title: "Blocked", body_markdown: "No auth." } },
);
if (blockedSessionArticleCreate.status !== 401 || blockedSessionArticleCreate.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session article create 401, got ${blockedSessionArticleCreate.status} ${blockedSessionArticleCreate.payload?.error?.code}`,
  );
}

const fixtureSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { "X-CPW-Fixture-Role": "dm" },
  { method: "POST", body: { mode: "manual", title: "Fixture blocked", body_markdown: "Fixture write." } },
);
if (fixtureSessionArticleCreate.status !== 403 || fixtureSessionArticleCreate.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture session article create forbidden 403, got ${fixtureSessionArticleCreate.status} ${fixtureSessionArticleCreate.payload?.error?.code}`,
  );
}

const playerSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST", body: { mode: "manual", title: "Player blocked", body_markdown: "Player write." } },
);
if (playerSessionArticleCreate.status !== 403 || playerSessionArticleCreate.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player session article create forbidden 403, got ${playerSessionArticleCreate.status} ${playerSessionArticleCreate.payload?.error?.code}`,
  );
}

const malformedSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: "not-json" },
);
if (malformedSessionArticleCreate.status !== 400 || malformedSessionArticleCreate.payload?.error?.code !== "invalid_json") {
  throw new Error(
    `Expected malformed session article create invalid_json 400, got ${malformedSessionArticleCreate.status} ${malformedSessionArticleCreate.payload?.error?.code}`,
  );
}

const invalidModeSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { mode: "lookup", title: "Bad mode", body_markdown: "Nope." } },
);
if (
  invalidModeSessionArticleCreate.status !== 400 ||
  invalidModeSessionArticleCreate.payload?.error?.message !== "Article mode must be 'manual', 'upload', or 'wiki'."
) {
  throw new Error(
    `Expected invalid session article mode validation, got ${invalidModeSessionArticleCreate.status} ${invalidModeSessionArticleCreate.payload?.error?.message}`,
  );
}

const manualArticleImageBytes = Buffer.from("manual-article-image");
const manualSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: {
      mode: "manual",
      title: "Table Sketch",
      image: {
        filename: "table-sketch.webp",
        media_type: "image/png",
        data_base64: manualArticleImageBytes.toString("base64"),
        alt_text: "Sketch alt",
        caption: "Sketch caption",
      },
    },
  },
);
if (
  manualSessionArticleCreate.status !== 200 ||
  manualSessionArticleCreate.payload?.article?.title !== "Table Sketch" ||
  manualSessionArticleCreate.payload?.article?.body_markdown !== "" ||
  manualSessionArticleCreate.payload?.article?.status !== "staged" ||
  manualSessionArticleCreate.payload?.article?.created_by_user_id !== 81 ||
  manualSessionArticleCreate.payload?.article?.image?.filename !== "table-sketch.webp" ||
  manualSessionArticleCreate.payload?.article?.image?.media_type !== "image/webp" ||
  manualSessionArticleCreate.payload?.article?.image?.alt_text !== "Sketch alt" ||
  manualSessionArticleCreate.payload?.article?.image?.caption !== "Sketch caption"
) {
  throw new Error(`Unexpected manual session article create payload: ${JSON.stringify(manualSessionArticleCreate.payload)}`);
}
const manualArticleId = manualSessionArticleCreate.payload.article.id;

const updatedManualSessionArticle = await requestJson(
  `/api/v1/campaigns/linden-pass/session/articles/${manualArticleId}`,
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "PUT",
    body: {
      title: "Updated Table Sketch",
      body_markdown: "A revised table clue.",
      image_alt_text: "Updated sketch alt",
      image_caption: "Updated sketch caption",
    },
  },
);
if (
  updatedManualSessionArticle.status !== 200 ||
  updatedManualSessionArticle.payload?.article?.title !== "Updated Table Sketch" ||
  updatedManualSessionArticle.payload?.article?.body_markdown !== "A revised table clue." ||
  updatedManualSessionArticle.payload?.article?.image?.alt_text !== "Updated sketch alt" ||
  updatedManualSessionArticle.payload?.article?.image?.caption !== "Updated sketch caption"
) {
  throw new Error(`Unexpected manual session article update payload: ${JSON.stringify(updatedManualSessionArticle.payload)}`);
}

const uploadSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: {
      mode: "upload",
      filename: "uploaded-clue.md",
      markdown_text:
        "---\ntitle: Uploaded Clue\nimage: clue.png\nimage_alt: Upload alt\nimage_caption: Upload caption\n---\n![Upload alt](clue.png)\n\nBody after image.",
      referenced_image: {
        filename: "clue.png",
        media_type: "image/png",
        data_base64: Buffer.from("upload-image").toString("base64"),
      },
    },
  },
);
if (
  uploadSessionArticleCreate.status !== 200 ||
  uploadSessionArticleCreate.payload?.article?.title !== "Uploaded Clue" ||
  uploadSessionArticleCreate.payload?.article?.body_markdown !== "Body after image." ||
  uploadSessionArticleCreate.payload?.article?.image?.filename !== "clue.png" ||
  uploadSessionArticleCreate.payload?.article?.image?.alt_text !== "Upload alt" ||
  uploadSessionArticleCreate.payload?.article?.image?.caption !== "Upload caption"
) {
  throw new Error(`Unexpected upload session article create payload: ${JSON.stringify(uploadSessionArticleCreate.payload)}`);
}
const uploadArticleId = uploadSessionArticleCreate.payload.article.id;

const missingReferencedImageArticle = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  {
    method: "POST",
    body: {
      mode: "upload",
      filename: "missing-image.md",
      markdown_text: "---\ntitle: Missing Image\nimage: missing.png\n---\nBody.",
    },
  },
);
if (
  missingReferencedImageArticle.status !== 400 ||
  missingReferencedImageArticle.payload?.error?.message !==
    "This markdown file references an image. Include referenced_image too."
) {
  throw new Error(
    `Expected missing referenced-image validation, got ${missingReferencedImageArticle.status} ${missingReferencedImageArticle.payload?.error?.message}`,
  );
}

const wikiPageSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { mode: "wiki", source_ref: "npcs/captain-lyra-vale" } },
);
if (
  wikiPageSessionArticleCreate.status !== 200 ||
  wikiPageSessionArticleCreate.payload?.article?.title !== "Captain Lyra Vale" ||
  wikiPageSessionArticleCreate.payload?.article?.source_kind !== "page" ||
  wikiPageSessionArticleCreate.payload?.article?.source_ref !== "npcs/captain-lyra-vale" ||
  !String(wikiPageSessionArticleCreate.payload?.article?.body_markdown || "").includes("Captain Lyra Vale coordinates") ||
  wikiPageSessionArticleCreate.payload?.article?.image?.filename !== "captain-lyra-vale.png" ||
  wikiPageSessionArticleCreate.payload?.article?.image?.media_type !== "image/png"
) {
  throw new Error(`Unexpected wiki page session article create payload: ${JSON.stringify(wikiPageSessionArticleCreate.payload)}`);
}

const systemsSessionArticleCreate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { mode: "wiki", source_ref: "systems:phb-item-chain-mail" } },
);
if (
  systemsSessionArticleCreate.status !== 200 ||
  systemsSessionArticleCreate.payload?.article?.title !== "Chain Mail" ||
  systemsSessionArticleCreate.payload?.article?.source_kind !== "systems" ||
  systemsSessionArticleCreate.payload?.article?.source_ref !== "phb-item-chain-mail" ||
  systemsSessionArticleCreate.payload?.article?.body_format !== "html" ||
  systemsSessionArticleCreate.payload?.article?.body_markdown !== "<p>A sample armor entry.</p>"
) {
  throw new Error(`Unexpected Systems session article create payload: ${JSON.stringify(systemsSessionArticleCreate.payload)}`);
}
const systemsArticleId = systemsSessionArticleCreate.payload.article.id;

const revealSystemsSessionArticle = await requestJson(
  `/api/v1/campaigns/linden-pass/session/articles/${systemsArticleId}/reveal`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  revealSystemsSessionArticle.status !== 200 ||
  revealSystemsSessionArticle.payload?.article?.id !== systemsArticleId ||
  revealSystemsSessionArticle.payload?.article?.status !== "revealed" ||
  revealSystemsSessionArticle.payload?.article?.revealed_by_user_id !== 81 ||
  revealSystemsSessionArticle.payload?.article?.revealed_in_session_id !== 1 ||
  revealSystemsSessionArticle.payload?.message?.message_type !== "article_reveal" ||
  revealSystemsSessionArticle.payload?.message?.article_id !== systemsArticleId ||
  revealSystemsSessionArticle.payload?.message?.article?.id !== systemsArticleId ||
  revealSystemsSessionArticle.payload?.message?.author_display_name !== "Fixture Token DM"
) {
  throw new Error(`Unexpected session article reveal payload: ${JSON.stringify(revealSystemsSessionArticle.payload)}`);
}

const duplicateRevealSystemsSessionArticle = await requestJson(
  `/api/v1/campaigns/linden-pass/session/articles/${systemsArticleId}/reveal`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  duplicateRevealSystemsSessionArticle.status !== 400 ||
  duplicateRevealSystemsSessionArticle.payload?.error?.message !== "That session article has already been revealed."
) {
  throw new Error(
    `Expected duplicate reveal validation, got ${duplicateRevealSystemsSessionArticle.status} ${duplicateRevealSystemsSessionArticle.payload?.error?.message}`,
  );
}

const updateRevealedSystemsSessionArticle = await requestJson(
  `/api/v1/campaigns/linden-pass/session/articles/${systemsArticleId}`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PUT", body: { title: "Should Fail", body_markdown: "No edit." } },
);
if (
  updateRevealedSystemsSessionArticle.status !== 400 ||
  updateRevealedSystemsSessionArticle.payload?.error?.message !==
    "Revealed session articles cannot be edited in the prep queue."
) {
  throw new Error(
    `Expected revealed article update validation, got ${updateRevealedSystemsSessionArticle.status} ${updateRevealedSystemsSessionArticle.payload?.error?.message}`,
  );
}

const deleteUploadSessionArticle = await requestJson(
  `/api/v1/campaigns/linden-pass/session/articles/${uploadArticleId}`,
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  deleteUploadSessionArticle.status !== 200 ||
  deleteUploadSessionArticle.payload?.article?.id !== uploadArticleId ||
  deleteUploadSessionArticle.payload?.article?.title !== "Uploaded Clue"
) {
  throw new Error(`Unexpected upload session article delete payload: ${JSON.stringify(deleteUploadSessionArticle.payload)}`);
}

const missingSessionArticleUpdate = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles/999999",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PUT", body: { title: "Missing", body_markdown: "Missing." } },
);
if (
  missingSessionArticleUpdate.status !== 400 ||
  missingSessionArticleUpdate.payload?.error?.message !== "That session article could not be found."
) {
  throw new Error(
    `Expected missing session article update validation, got ${missingSessionArticleUpdate.status} ${missingSessionArticleUpdate.payload?.error?.message}`,
  );
}

const missingSessionArticleReveal = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles/999999/reveal",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  missingSessionArticleReveal.status !== 400 ||
  missingSessionArticleReveal.payload?.error?.message !== "That session article could not be found."
) {
  throw new Error(
    `Expected missing session article reveal validation, got ${missingSessionArticleReveal.status} ${missingSessionArticleReveal.payload?.error?.message}`,
  );
}

const missingSessionArticleDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles/999999",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  missingSessionArticleDelete.status !== 400 ||
  missingSessionArticleDelete.payload?.error?.message !== "That session article could not be found."
) {
  throw new Error(
    `Expected missing session article delete validation, got ${missingSessionArticleDelete.status} ${missingSessionArticleDelete.payload?.error?.message}`,
  );
}

const missingSessionArticleCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/articles",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST", body: { mode: "manual", title: "Missing campaign", body_markdown: "Missing campaign." } },
);
if (missingSessionArticleCampaign.status !== 404 || missingSessionArticleCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing session article campaign JSON 404, got ${missingSessionArticleCampaign.status} ${missingSessionArticleCampaign.payload?.error?.code}`,
  );
}

const playerSessionAfterArticleWrites = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (
  playerSessionAfterArticleWrites.status !== 200 ||
  !playerSessionAfterArticleWrites.payload?.messages?.some(
    (message) => message.message_type === "article_reveal" && message.article?.id === systemsArticleId,
  ) ||
  playerSessionAfterArticleWrites.payload?.staged_articles !== undefined
) {
  throw new Error(`Unexpected player session after article writes: ${JSON.stringify(playerSessionAfterArticleWrites.payload)}`);
}

const articleAssertionDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const articleAssertionRows = articleAssertionDb
  .prepare(
    "SELECT id, title, status, source_page_ref, revealed_by_user_id, revealed_in_session_id FROM campaign_session_articles WHERE id IN (?, ?, ?, ?) ORDER BY id ASC",
  )
  .all(manualArticleId, uploadArticleId, wikiPageSessionArticleCreate.payload.article.id, systemsArticleId);
const articleImageRows = articleAssertionDb
  .prepare("SELECT article_id, filename, media_type, alt_text, caption FROM campaign_session_article_images WHERE article_id IN (?, ?, ?) ORDER BY article_id ASC")
  .all(manualArticleId, wikiPageSessionArticleCreate.payload.article.id, systemsArticleId);
const articleMessageRow = articleAssertionDb
  .prepare("SELECT message_type, article_id, author_user_id FROM campaign_session_messages WHERE article_id = ?")
  .get(systemsArticleId);
const articleRevisionRow = articleAssertionDb
  .prepare("SELECT revision, updated_by_user_id FROM campaign_session_states WHERE campaign_slug = ?")
  .get("linden-pass");
articleAssertionDb.close();
if (
  articleAssertionRows.length !== 3 ||
  articleAssertionRows.some((row) => Number(row.id) === Number(uploadArticleId)) ||
  !articleAssertionRows.some(
    (row) => Number(row.id) === Number(manualArticleId) && row.title === "Updated Table Sketch" && row.status === "staged",
  ) ||
  !articleAssertionRows.some(
    (row) =>
      Number(row.id) === Number(wikiPageSessionArticleCreate.payload.article.id) &&
      row.source_page_ref === "npcs/captain-lyra-vale",
  ) ||
  !articleAssertionRows.some(
    (row) =>
      Number(row.id) === Number(systemsArticleId) &&
      row.status === "revealed" &&
      row.source_page_ref === "systems:phb-item-chain-mail" &&
      Number(row.revealed_by_user_id) === 81 &&
      Number(row.revealed_in_session_id) === 1,
  ) ||
  !articleImageRows.some(
    (row) =>
      Number(row.article_id) === Number(manualArticleId) &&
      row.filename === "table-sketch.webp" &&
      row.alt_text === "Updated sketch alt" &&
      row.caption === "Updated sketch caption",
  ) ||
  !articleImageRows.some(
    (row) =>
      Number(row.article_id) === Number(wikiPageSessionArticleCreate.payload.article.id) &&
      row.filename === "captain-lyra-vale.png" &&
      row.media_type === "image/png",
  ) ||
  articleMessageRow?.message_type !== "article_reveal" ||
  Number(articleMessageRow?.author_user_id) !== 81 ||
  Number(articleRevisionRow?.revision) !== Number(messageRevisionRow?.revision) + 7 ||
  Number(articleRevisionRow?.updated_by_user_id) !== 81
) {
  throw new Error(
    `Expected persisted session article writes, got articles=${JSON.stringify(articleAssertionRows)} images=${JSON.stringify(articleImageRows)} message=${JSON.stringify(articleMessageRow)} revision=${JSON.stringify(articleRevisionRow)}`,
  );
}

const blockedSessionImage = await requestJson("/api/v1/campaigns/linden-pass/session/articles/102/image");
if (blockedSessionImage.status !== 401 || blockedSessionImage.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session article image 401, got ${blockedSessionImage.status} ${blockedSessionImage.payload?.error?.code}`,
  );
}

const dmStagedSessionImage = await requestBytes("/api/v1/campaigns/linden-pass/session/articles/101/image", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmStagedSessionImage.status !== 200 ||
  !dmStagedSessionImage.headers.get("content-type")?.startsWith("image/gif") ||
  !dmStagedSessionImage.headers.get("content-disposition")?.includes("staged-note.gif") ||
  Buffer.from(dmStagedSessionImage.body).toString("utf8") !== "staged-image"
) {
  throw new Error(
    `Unexpected DM staged session image response: ${dmStagedSessionImage.status} ${dmStagedSessionImage.headers.get("content-type")} ${Buffer.from(dmStagedSessionImage.body).toString("utf8")}`,
  );
}

const bearerAdminStagedSessionImage = await requestBytes("/api/v1/campaigns/linden-pass/session/articles/101/image", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerAdminStagedSessionImage.status !== 200 ||
  !bearerAdminStagedSessionImage.headers.get("content-type")?.startsWith("image/gif") ||
  Buffer.from(bearerAdminStagedSessionImage.body).toString("utf8") !== "staged-image"
) {
  throw new Error(`Unexpected bearer admin staged session image response: ${bearerAdminStagedSessionImage.status}`);
}

const playerStagedSessionImage = await requestJson("/api/v1/campaigns/linden-pass/session/articles/101/image", {
  "X-CPW-Fixture-Role": "player",
});
if (playerStagedSessionImage.status !== 404 || playerStagedSessionImage.payload?.error?.code !== "session_article_image_not_found") {
  throw new Error(
    `Expected player staged session image 404, got ${playerStagedSessionImage.status} ${playerStagedSessionImage.payload?.error?.code}`,
  );
}

const playerRevealedSessionImage = await requestBytes("/api/v1/campaigns/linden-pass/session/articles/102/image", {
  "X-CPW-Fixture-Role": "player",
});
if (
  playerRevealedSessionImage.status !== 200 ||
  !playerRevealedSessionImage.headers.get("content-type")?.startsWith("image/png") ||
  !playerRevealedSessionImage.headers.get("content-disposition")?.includes("revealed-note.png") ||
  Buffer.from(playerRevealedSessionImage.body).toString("utf8") !== "fixture-image"
) {
  throw new Error(
    `Unexpected player revealed session image response: ${playerRevealedSessionImage.status} ${playerRevealedSessionImage.headers.get("content-type")} ${Buffer.from(playerRevealedSessionImage.body).toString("utf8")}`,
  );
}

const bearerPlayerRevealedSessionImage = await requestBytes("/api/v1/campaigns/linden-pass/session/articles/102/image", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (
  bearerPlayerRevealedSessionImage.status !== 200 ||
  !bearerPlayerRevealedSessionImage.headers.get("content-type")?.startsWith("image/png") ||
  Buffer.from(bearerPlayerRevealedSessionImage.body).toString("utf8") !== "fixture-image"
) {
  throw new Error(`Unexpected bearer player revealed session image response: ${bearerPlayerRevealedSessionImage.status}`);
}

const missingSessionImage = await requestJson("/api/v1/campaigns/linden-pass/session/articles/999999/image", {
  "X-CPW-Fixture-Role": "dm",
});
if (missingSessionImage.status !== 404 || missingSessionImage.payload?.error?.code !== "session_article_image_not_found") {
  throw new Error(
    `Expected missing session article image JSON 404, got ${missingSessionImage.status} ${missingSessionImage.payload?.error?.code}`,
  );
}

const blockedSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/2");
if (blockedSessionLog.status !== 401 || blockedSessionLog.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session log detail 401, got ${blockedSessionLog.status} ${blockedSessionLog.payload?.error?.code}`,
  );
}

const playerSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/2", {
  "X-CPW-Fixture-Role": "player",
});
if (playerSessionLog.status !== 403 || playerSessionLog.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player session log detail forbidden 403, got ${playerSessionLog.status} ${playerSessionLog.payload?.error?.code}`,
  );
}

const bearerPlayerSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/2", {
  Authorization: `Bearer ${playerApiToken}`,
});
if (bearerPlayerSessionLog.status !== 403 || bearerPlayerSessionLog.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected bearer player session log detail forbidden 403, got ${bearerPlayerSessionLog.status} ${bearerPlayerSessionLog.payload?.error?.code}`,
  );
}

const dmSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/2", {
  "X-CPW-Fixture-Role": "dm",
});
if (
  dmSessionLog.status !== 200 ||
  dmSessionLog.payload?.ok !== true ||
  dmSessionLog.payload?.session?.id !== 2 ||
  dmSessionLog.payload?.session?.status !== "closed" ||
  dmSessionLog.payload?.session?.is_active !== false ||
  dmSessionLog.payload?.messages?.length !== 1 ||
  dmSessionLog.payload?.messages?.[0]?.body_text !== "A closed-session DM-only message." ||
  dmSessionLog.payload?.messages?.[0]?.recipient_scope !== "dm_only" ||
  dmSessionLog.payload?.messages?.[0]?.recipient_label !== "DM"
) {
  throw new Error(`Unexpected DM session log detail payload: ${JSON.stringify(dmSessionLog.payload)}`);
}

const bearerAdminSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/2", {
  Authorization: `Bearer ${liveApiToken}`,
});
if (
  bearerAdminSessionLog.status !== 200 ||
  bearerAdminSessionLog.payload?.session?.id !== 2 ||
  bearerAdminSessionLog.payload?.messages?.[0]?.recipient_scope !== "dm_only"
) {
  throw new Error(`Unexpected bearer admin session log detail payload: ${JSON.stringify(bearerAdminSessionLog.payload)}`);
}

const activeSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/1", {
  "X-CPW-Fixture-Role": "dm",
});
if (activeSessionLog.status !== 404 || activeSessionLog.payload?.error?.code !== "session_log_not_found") {
  throw new Error(
    `Expected active session log detail 404, got ${activeSessionLog.status} ${activeSessionLog.payload?.error?.code}`,
  );
}

const missingSessionLog = await requestJson("/api/v1/campaigns/linden-pass/session/logs/999999", {
  "X-CPW-Fixture-Role": "dm",
});
if (missingSessionLog.status !== 404 || missingSessionLog.payload?.error?.code !== "session_log_not_found") {
  throw new Error(
    `Expected missing session log detail JSON 404, got ${missingSessionLog.status} ${missingSessionLog.payload?.error?.code}`,
  );
}

const blockedSessionLogDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/session/logs/2",
  {},
  { method: "DELETE" },
);
if (blockedSessionLogDelete.status !== 401 || blockedSessionLogDelete.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session log delete 401, got ${blockedSessionLogDelete.status} ${blockedSessionLogDelete.payload?.error?.code}`,
  );
}

const fixtureSessionLogDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/session/logs/2",
  { "X-CPW-Fixture-Role": "dm" },
  { method: "DELETE" },
);
if (
  fixtureSessionLogDelete.status !== 403 ||
  fixtureSessionLogDelete.payload?.error?.message !== "Session log writes require bearer API authentication."
) {
  throw new Error(
    `Expected fixture session log delete forbidden, got ${fixtureSessionLogDelete.status} ${fixtureSessionLogDelete.payload?.error?.message}`,
  );
}

const playerSessionLogDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/session/logs/2",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "DELETE" },
);
if (
  playerSessionLogDelete.status !== 403 ||
  playerSessionLogDelete.payload?.error?.message !== "You do not have permission to manage this session."
) {
  throw new Error(
    `Expected player session log delete forbidden, got ${playerSessionLogDelete.status} ${playerSessionLogDelete.payload?.error?.message}`,
  );
}

const activeSessionLogDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/session/logs/1",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  activeSessionLogDelete.status !== 400 ||
  activeSessionLogDelete.payload?.error?.message !== "Close the live session before deleting its chat log."
) {
  throw new Error(
    `Expected active session log delete validation, got ${activeSessionLogDelete.status} ${activeSessionLogDelete.payload?.error?.message}`,
  );
}

const missingSessionLogDelete = await requestJson(
  "/api/v1/campaigns/linden-pass/session/logs/999999",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  missingSessionLogDelete.status !== 400 ||
  missingSessionLogDelete.payload?.error?.message !== "That chat log could not be found."
) {
  throw new Error(
    `Expected missing session log delete validation, got ${missingSessionLogDelete.status} ${missingSessionLogDelete.payload?.error?.message}`,
  );
}

const missingSessionLogDeleteCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/logs/2",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  missingSessionLogDeleteCampaign.status !== 404 ||
  missingSessionLogDeleteCampaign.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing session log delete campaign JSON 404, got ${missingSessionLogDeleteCampaign.status} ${missingSessionLogDeleteCampaign.payload?.error?.code}`,
  );
}

const logDeleteSetupDb = new Database(dbPath, { fileMustExist: true });
const closedLogArticleId = Number(
  logDeleteSetupDb.prepare("SELECT COALESCE(MAX(id), 0) + 1 AS id FROM campaign_session_articles").get().id,
);
logDeleteSetupDb
  .prepare(
    `
      INSERT INTO campaign_session_articles (
        id,
        campaign_slug,
        title,
        body_markdown,
        source_page_ref,
        status,
        created_at,
        created_by_user_id,
        revealed_at,
        revealed_by_user_id,
        revealed_in_session_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  )
  .run(
    closedLogArticleId,
    "linden-pass",
    "Closed Log Provenance",
    "A revealed article linked to the deleted chat log.",
    "",
    "revealed",
    "2026-06-24T10:35:00+00:00",
    42,
    "2026-06-24T10:35:00+00:00",
    42,
    2,
  );
logDeleteSetupDb.close();

const deleteSessionLogResponse = await requestJson(
  "/api/v1/campaigns/linden-pass/session/logs/2",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  deleteSessionLogResponse.status !== 200 ||
  deleteSessionLogResponse.payload?.ok !== true ||
  deleteSessionLogResponse.payload?.deleted_session_id !== 2
) {
  throw new Error(`Unexpected session log delete payload: ${JSON.stringify(deleteSessionLogResponse.payload)}`);
}

const logDeleteAssertionDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const deletedSessionRow = logDeleteAssertionDb.prepare("SELECT id FROM campaign_sessions WHERE id = ?").get(2);
const deletedSessionMessageCount = logDeleteAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_session_messages WHERE session_id = ?")
  .get(2);
const unlinkedClosedLogArticle = logDeleteAssertionDb
  .prepare("SELECT revealed_in_session_id FROM campaign_session_articles WHERE id = ?")
  .get(closedLogArticleId);
const logDeleteRevisionRow = logDeleteAssertionDb
  .prepare("SELECT revision, updated_by_user_id FROM campaign_session_states WHERE campaign_slug = ?")
  .get("linden-pass");
logDeleteAssertionDb.close();
if (
  deletedSessionRow !== undefined ||
  Number(deletedSessionMessageCount?.count) !== 0 ||
  unlinkedClosedLogArticle?.revealed_in_session_id !== null ||
  Number(logDeleteRevisionRow?.revision) !== Number(articleRevisionRow?.revision) + 1 ||
  Number(logDeleteRevisionRow?.updated_by_user_id) !== 81
) {
  throw new Error(
    `Expected deleted session log rows and revision bump, got session=${JSON.stringify(deletedSessionRow)} messages=${JSON.stringify(deletedSessionMessageCount)} article=${JSON.stringify(unlinkedClosedLogArticle)} revision=${JSON.stringify(logDeleteRevisionRow)}`,
  );
}

const missingSession = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/session");
if (missingSession.status !== 404 || missingSession.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing session campaign JSON 404, got ${missingSession.status}`);
}

const missingSessionImageCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/articles/102/image",
  {
    "X-CPW-Fixture-Role": "dm",
  },
);
if (missingSessionImageCampaign.status !== 404 || missingSessionImageCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing session image campaign JSON 404, got ${missingSessionImageCampaign.status} ${missingSessionImageCampaign.payload?.error?.code}`,
  );
}

const blockedSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
);
if (blockedSessionSourceSearch.status !== 401 || blockedSessionSourceSearch.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session article-source search 401, got ${blockedSessionSourceSearch.status} ${blockedSessionSourceSearch.payload?.error?.code}`,
  );
}

const playerSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
  {
    "X-CPW-Fixture-Role": "player",
  },
);
if (playerSessionSourceSearch.status !== 403 || playerSessionSourceSearch.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected player session article-source search forbidden 403, got ${playerSessionSourceSearch.status} ${playerSessionSourceSearch.payload?.error?.code}`,
  );
}

const bearerPlayerSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
  {
    Authorization: `Bearer ${playerApiToken}`,
  },
);
if (bearerPlayerSessionSourceSearch.status !== 403 || bearerPlayerSessionSourceSearch.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected bearer player session article-source search forbidden 403, got ${bearerPlayerSessionSourceSearch.status} ${bearerPlayerSessionSourceSearch.payload?.error?.code}`,
  );
}

const shortSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=c",
  {
    "X-CPW-Fixture-Role": "dm",
  },
);
if (
  shortSessionSourceSearch.status !== 200 ||
  shortSessionSourceSearch.payload?.message !==
    "Type at least 2 letters to search published wiki pages and Systems entries." ||
  shortSessionSourceSearch.payload?.results?.length !== 0
) {
  throw new Error(`Unexpected short session article-source search payload: ${JSON.stringify(shortSessionSourceSearch.payload)}`);
}

const wikiSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
  {
    "X-CPW-Fixture-Role": "dm",
  },
);
const captainSource = wikiSessionSourceSearch.payload?.results?.find(
  (result) => result.source_ref === "npcs/captain-lyra-vale",
);
if (
  wikiSessionSourceSearch.status !== 200 ||
  wikiSessionSourceSearch.payload?.message !== "Found 2 matching articles." ||
  wikiSessionSourceSearch.payload?.results?.length !== 2 ||
  captainSource?.source_kind !== "page" ||
  captainSource?.title !== "Captain Lyra Vale" ||
  captainSource?.subtitle !== "NPCs" ||
  captainSource?.kind_label !== "Wiki" ||
  captainSource?.select_label !== "Captain Lyra Vale - Wiki - NPCs"
) {
  throw new Error(`Unexpected wiki session article-source search payload: ${JSON.stringify(wikiSessionSourceSearch.payload)}`);
}

const bearerAdminWikiSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
  {
    Authorization: `Bearer ${liveApiToken}`,
  },
);
if (
  bearerAdminWikiSessionSourceSearch.status !== 200 ||
  bearerAdminWikiSessionSourceSearch.payload?.results?.length !== 2 ||
  !bearerAdminWikiSessionSourceSearch.payload?.results?.some(
    (result) => result.source_ref === "npcs/captain-lyra-vale" && result.source_kind === "page",
  )
) {
  throw new Error(
    `Unexpected bearer admin wiki session article-source search payload: ${JSON.stringify(bearerAdminWikiSessionSourceSearch.payload)}`,
  );
}

const systemsSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/linden-pass/session/article-sources/search?q=gob",
  {
    "X-CPW-Fixture-Role": "dm",
  },
);
if (
  systemsSessionSourceSearch.status !== 200 ||
  systemsSessionSourceSearch.payload?.message !== "Found 1 matching article." ||
  systemsSessionSourceSearch.payload?.results?.[0]?.source_kind !== "systems" ||
  systemsSessionSourceSearch.payload?.results?.[0]?.source_ref !== "systems:mm-monster-goblin" ||
  systemsSessionSourceSearch.payload?.results?.[0]?.title !== "Goblin" ||
  systemsSessionSourceSearch.payload?.results?.[0]?.subtitle !== "Monsters - MM" ||
  systemsSessionSourceSearch.payload?.results?.[0]?.kind_label !== "Systems" ||
  systemsSessionSourceSearch.payload?.results?.[0]?.select_label !== "Goblin - Systems - Monsters - MM"
) {
  throw new Error(`Unexpected Systems session article-source search payload: ${JSON.stringify(systemsSessionSourceSearch.payload)}`);
}

const missingSessionSourceSearch = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/article-sources/search?q=capt",
  {
    "X-CPW-Fixture-Role": "dm",
  },
);
if (missingSessionSourceSearch.status !== 404 || missingSessionSourceSearch.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing session article-source search campaign JSON 404, got ${missingSessionSourceSearch.status}`,
  );
}

const blockedSessionStart = await requestJson(
  "/api/v1/campaigns/linden-pass/session/start",
  {},
  { method: "POST" },
);
if (blockedSessionStart.status !== 401 || blockedSessionStart.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated session start 401, got ${blockedSessionStart.status} ${blockedSessionStart.payload?.error?.code}`,
  );
}

const fixtureSessionStart = await requestJson(
  "/api/v1/campaigns/linden-pass/session/start",
  { "X-CPW-Fixture-Role": "dm" },
  { method: "POST" },
);
if (fixtureSessionStart.status !== 403 || fixtureSessionStart.payload?.error?.code !== "forbidden") {
  throw new Error(
    `Expected fixture session start forbidden 403, got ${fixtureSessionStart.status} ${fixtureSessionStart.payload?.error?.code}`,
  );
}

const playerSessionStart = await requestJson(
  "/api/v1/campaigns/linden-pass/session/start",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST" },
);
if (
  playerSessionStart.status !== 403 ||
  playerSessionStart.payload?.error?.message !== "You do not have permission to manage this session."
) {
  throw new Error(
    `Expected player session start forbidden, got ${playerSessionStart.status} ${playerSessionStart.payload?.error?.message}`,
  );
}

const duplicateSessionStart = await requestJson(
  "/api/v1/campaigns/linden-pass/session/start",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  duplicateSessionStart.status !== 400 ||
  duplicateSessionStart.payload?.error?.message !== "A live session is already running for this campaign."
) {
  throw new Error(
    `Expected duplicate session start validation, got ${duplicateSessionStart.status} ${duplicateSessionStart.payload?.error?.message}`,
  );
}

const missingSessionStartCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/start",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (missingSessionStartCampaign.status !== 404 || missingSessionStartCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing session start campaign JSON 404, got ${missingSessionStartCampaign.status} ${missingSessionStartCampaign.payload?.error?.code}`,
  );
}

const playerSessionClose = await requestJson(
  "/api/v1/campaigns/linden-pass/session/close",
  { Authorization: `Bearer ${playerApiToken}` },
  { method: "POST" },
);
if (
  playerSessionClose.status !== 403 ||
  playerSessionClose.payload?.error?.message !== "You do not have permission to manage this session."
) {
  throw new Error(
    `Expected player session close forbidden, got ${playerSessionClose.status} ${playerSessionClose.payload?.error?.message}`,
  );
}

const closeSessionResponse = await requestJson(
  "/api/v1/campaigns/linden-pass/session/close",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  closeSessionResponse.status !== 200 ||
  closeSessionResponse.payload?.ok !== true ||
  closeSessionResponse.payload?.session?.id !== 1 ||
  closeSessionResponse.payload?.session?.status !== "closed" ||
  closeSessionResponse.payload?.session?.is_active !== false ||
  closeSessionResponse.payload?.session?.ended_by_user_id !== 81 ||
  typeof closeSessionResponse.payload?.session?.ended_at !== "string"
) {
  throw new Error(`Unexpected session close payload: ${JSON.stringify(closeSessionResponse.payload)}`);
}

const duplicateSessionClose = await requestJson(
  "/api/v1/campaigns/linden-pass/session/close",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  duplicateSessionClose.status !== 400 ||
  duplicateSessionClose.payload?.error?.message !== "There is no active session to close."
) {
  throw new Error(
    `Expected duplicate session close validation, got ${duplicateSessionClose.status} ${duplicateSessionClose.payload?.error?.message}`,
  );
}

const missingSessionCloseCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/close",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (missingSessionCloseCampaign.status !== 404 || missingSessionCloseCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing session close campaign JSON 404, got ${missingSessionCloseCampaign.status} ${missingSessionCloseCampaign.payload?.error?.code}`,
  );
}

const lifecycleAfterCloseDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const closedSessionRow = lifecycleAfterCloseDb
  .prepare("SELECT status, ended_by_user_id FROM campaign_sessions WHERE id = ?")
  .get(1);
const closeRevisionRow = lifecycleAfterCloseDb
  .prepare("SELECT revision, updated_by_user_id FROM campaign_session_states WHERE campaign_slug = ?")
  .get("linden-pass");
lifecycleAfterCloseDb.close();
if (
  closedSessionRow?.status !== "closed" ||
  Number(closedSessionRow?.ended_by_user_id) !== 81 ||
  Number(closeRevisionRow?.revision) !== Number(logDeleteRevisionRow?.revision) + 1 ||
  Number(closeRevisionRow?.updated_by_user_id) !== 81
) {
  throw new Error(
    `Expected closed session and revision bump, got session=${JSON.stringify(closedSessionRow)} revision=${JSON.stringify(closeRevisionRow)}`,
  );
}

const restartSessionResponse = await requestJson(
  "/api/v1/campaigns/linden-pass/session/start",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "POST" },
);
if (
  restartSessionResponse.status !== 200 ||
  restartSessionResponse.payload?.ok !== true ||
  restartSessionResponse.payload?.session?.status !== "active" ||
  restartSessionResponse.payload?.session?.is_active !== true ||
  restartSessionResponse.payload?.session?.started_by_user_id !== 81 ||
  restartSessionResponse.payload?.session?.ended_at !== null ||
  Number(restartSessionResponse.payload?.session?.id) <= 2
) {
  throw new Error(`Unexpected session restart payload: ${JSON.stringify(restartSessionResponse.payload)}`);
}

const dmSessionAfterLifecycle = await requestJson("/api/v1/campaigns/linden-pass/session", {
  Authorization: `Bearer ${dmApiToken}`,
});
if (
  dmSessionAfterLifecycle.status !== 200 ||
  dmSessionAfterLifecycle.payload?.active_session?.id !== restartSessionResponse.payload?.session?.id ||
  dmSessionAfterLifecycle.payload?.messages?.length !== 0 ||
  Number(dmSessionAfterLifecycle.payload?.session_revision) !== Number(closeRevisionRow?.revision) + 1 ||
  !dmSessionAfterLifecycle.payload?.session_logs?.some((entry) => entry.session?.id === 1 && entry.message_count >= 5)
) {
  throw new Error(`Unexpected DM session after lifecycle writes: ${JSON.stringify(dmSessionAfterLifecycle.payload)}`);
}

const blockedClearRevealedArticles = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles/revealed",
  {},
  { method: "DELETE" },
);
if (blockedClearRevealedArticles.status !== 401 || blockedClearRevealedArticles.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated clear revealed session articles 401, got ${blockedClearRevealedArticles.status} ${blockedClearRevealedArticles.payload?.error?.code}`,
  );
}

const clearRevealedArticles = await requestJson(
  "/api/v1/campaigns/linden-pass/session/articles/revealed",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (
  clearRevealedArticles.status !== 200 ||
  clearRevealedArticles.payload?.ok !== true ||
  !clearRevealedArticles.payload?.deleted_article_ids?.includes(102) ||
  !clearRevealedArticles.payload?.deleted_article_ids?.includes(systemsArticleId) ||
  clearRevealedArticles.payload?.deleted_articles?.length !== clearRevealedArticles.payload?.deleted_article_ids?.length
) {
  throw new Error(`Unexpected clear revealed session articles payload: ${JSON.stringify(clearRevealedArticles.payload)}`);
}

const missingClearRevealedCampaign = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/session/articles/revealed",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "DELETE" },
);
if (missingClearRevealedCampaign.status !== 404 || missingClearRevealedCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing clear revealed campaign JSON 404, got ${missingClearRevealedCampaign.status} ${missingClearRevealedCampaign.payload?.error?.code}`,
  );
}

const clearAssertionDb = new Database(dbPath, { fileMustExist: true, readonly: true });
const remainingRevealedArticleCount = clearAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_session_articles WHERE campaign_slug = ? AND status = 'revealed'")
  .get("linden-pass");
const remainingArticleRevealMessages = clearAssertionDb
  .prepare("SELECT COUNT(*) AS count FROM campaign_session_messages WHERE campaign_slug = ? AND article_id IS NOT NULL")
  .get("linden-pass");
const clearRevisionRow = clearAssertionDb
  .prepare("SELECT revision, updated_by_user_id FROM campaign_session_states WHERE campaign_slug = ?")
  .get("linden-pass");
clearAssertionDb.close();
if (
  Number(remainingRevealedArticleCount?.count) !== 0 ||
  Number(remainingArticleRevealMessages?.count) !== 0 ||
  Number(clearRevisionRow?.revision) !== Number(dmSessionAfterLifecycle.payload?.session_revision) + 1 ||
  Number(clearRevisionRow?.updated_by_user_id) !== 81
) {
  throw new Error(
    `Expected clear revealed persistence, got revealed=${JSON.stringify(remainingRevealedArticleCount)} messages=${JSON.stringify(remainingArticleRevealMessages)} revision=${JSON.stringify(clearRevisionRow)}`,
  );
}

const missingHelp = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/help");
if (missingHelp.status !== 404 || missingHelp.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing help campaign JSON 404, got ${missingHelp.status}`);
}

const missingCampaignControl = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/control", {
  "X-CPW-Fixture-Role": "dm",
});
if (missingCampaignControl.status !== 404 || missingCampaignControl.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing campaign control JSON 404, got ${missingCampaignControl.status}`);
}
const missingCampaignControlPatch = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/control/visibility",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { visibility: { campaign: "players" } } },
);
if (
  missingCampaignControlPatch.status !== 404 ||
  missingCampaignControlPatch.payload?.error?.code !== "campaign_not_found"
) {
  throw new Error(
    `Expected missing campaign control PATCH JSON 404, got ${missingCampaignControlPatch.status} ${missingCampaignControlPatch.payload?.error?.code}`,
  );
}

const missingCampaignConfig = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/content/config");
if (missingCampaignConfig.status !== 404 || missingCampaignConfig.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing content config campaign JSON 404, got ${missingCampaignConfig.status}`);
}
const missingCampaignConfigPatch = await requestJson(
  "/api/v1/campaigns/definitely-not-a-campaign/content/config",
  { Authorization: `Bearer ${dmApiToken}` },
  { method: "PATCH", body: { config: { summary: "Missing" } } },
);
if (missingCampaignConfigPatch.status !== 404 || missingCampaignConfigPatch.payload?.error?.code !== "campaign_not_found") {
  throw new Error(
    `Expected missing content config PATCH campaign JSON 404, got ${missingCampaignConfigPatch.status} ${missingCampaignConfigPatch.payload?.error?.code}`,
  );
}
const missingContentPages = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/content/pages");
if (missingContentPages.status !== 404 || missingContentPages.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing content pages campaign JSON 404, got ${missingContentPages.status}`);
}
const missingContentCharacters = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/content/characters");
if (missingContentCharacters.status !== 404 || missingContentCharacters.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing content characters campaign JSON 404, got ${missingContentCharacters.status}`);
}

ensureStopped();
process.exit(0);
