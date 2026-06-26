import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";

const DEFAULT_PORT = 39873;
const port = Number(process.env.CPW_SMOKE_PORT || DEFAULT_PORT);
const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const campaignsDir =
  process.env.CPW_CAMPAIGNS_DIR ||
  fileURLToPath(new URL("../../../tests/fixtures/sample_campaigns", import.meta.url));
const smokeTempDir = mkdtempSync(path.join(tmpdir(), "cpw-api-smoke-"));
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
  dmCombatState.payload?.available_statblock_choices?.length !== 0 ||
  dmCombatState.payload?.combat_condition_options?.includes("Prone") !== true ||
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
