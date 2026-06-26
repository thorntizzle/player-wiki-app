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
        metadata_json = ?
      WHERE library_slug = ?
        AND entry_key = ?
    `,
  )
  .run(
    JSON.stringify({ abilities: { dex: 14 }, hp: { average: 7 }, speed: { walk: 30 } }),
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
    "## Dock Tough\nArmor Class: 12\nHit Points: 16\nSpeed: 30 ft.\nDEX 14 (+2)",
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
if (
  playerCombatState.status !== 200 ||
  playerCombatState.payload?.ok !== true ||
  playerCombatState.payload?.changed !== true ||
  playerCombatState.payload?.campaign?.slug !== "linden-pass" ||
  playerCombatState.payload?.combat_system_supported !== true ||
  playerCombatState.payload?.live_revision !== 0 ||
  typeof playerCombatState.payload?.live_view_token !== "string" ||
  playerCombatState.payload.live_view_token.length !== 12 ||
  playerCombatState.payload?.tracker?.round_number !== 1 ||
  playerCombatState.payload?.tracker?.combatant_count !== 0 ||
  playerCombatState.payload?.tracker?.combatants?.length !== 0 ||
  playerCombatState.payload?.selected_combatant_id !== null ||
  playerCombatState.payload?.selected_combatant !== null ||
  playerCombatState.payload?.selected_player_character !== null ||
  playerCombatState.payload?.player_character_targets?.length !== 0 ||
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
if (
  dmCombatState.status !== 200 ||
  dmCombatState.payload?.permissions?.can_manage_combat !== true ||
  dmCombatState.payload?.permissions?.can_access_dm_content !== true ||
  dmCombatState.payload?.available_character_choices?.length !== 0 ||
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
  xianxiaUpdatedState.notes?.player_notes_markdown !== "Keep the manual pool edits in SQLite."
) {
  throw new Error(
    `Expected Xianxia mutable state reconciliation, got revision=${xianxiaUpdatedRow?.revision} state=${JSON.stringify(xianxiaUpdatedState)}`,
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
