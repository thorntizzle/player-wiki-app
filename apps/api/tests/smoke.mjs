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

const missingSession = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/session");
if (missingSession.status !== 404 || missingSession.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing session campaign JSON 404, got ${missingSession.status}`);
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
