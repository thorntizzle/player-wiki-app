import { spawn } from "node:child_process";
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

const smokeDb = new Database(dbPath);
smokeDb.exec(`
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
  "A closed-session message.",
  "global",
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

const requestJson = async (path, headers = {}) => {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    headers,
  });
  const payload = await response.json();
  return { status: response.status, payload };
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

const blockedImportRuns = await requestJson("/api/v1/systems/import-runs");
if (blockedImportRuns.status !== 401 || blockedImportRuns.payload?.error?.code !== "auth_required") {
  throw new Error(
    `Expected unauthenticated systems import runs request to return auth_required 401, got ${blockedImportRuns.status} ${blockedImportRuns.payload?.error?.code}`,
  );
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

const campaignConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config");
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

const contentCharacters = await requestJson("/api/v1/campaigns/linden-pass/content/characters");
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

const contentCharacter = await requestJson("/api/v1/campaigns/linden-pass/content/characters/arden-march");
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

const missingContentCharacter = await requestJson("/api/v1/campaigns/linden-pass/content/characters/missing-character");
if (missingContentCharacter.status !== 404 || missingContentCharacter.payload?.error?.code !== "content_character_not_found") {
  throw new Error(
    `Expected missing content character JSON 404, got ${missingContentCharacter.status} ${missingContentCharacter.payload?.error?.code}`,
  );
}

const contentAssets = await requestJson("/api/v1/campaigns/linden-pass/content/assets");
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

const contentAsset = await requestJson("/api/v1/campaigns/linden-pass/content/assets/npcs/captain-lyra-vale.png");
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

const missingContentAsset = await requestJson("/api/v1/campaigns/linden-pass/content/assets/definitely-not-an-asset.png");
if (missingContentAsset.status !== 404 || missingContentAsset.payload?.error?.code !== "content_asset_not_found") {
  throw new Error(
    `Expected missing content asset JSON 404, got ${missingContentAsset.status} ${missingContentAsset.payload?.error?.code}`,
  );
}

const contentPages = await requestJson("/api/v1/campaigns/linden-pass/content/pages");
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

const contentPage = await requestJson("/api/v1/campaigns/linden-pass/content/pages/locations/port-meridian");
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

const missingContentPage = await requestJson("/api/v1/campaigns/linden-pass/content/pages/definitely-not-a-page");
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

const missingSession = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/session");
if (missingSession.status !== 404 || missingSession.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing session campaign JSON 404, got ${missingSession.status}`);
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
