import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const tempRoot = mkdtempSync(path.join(tmpdir(), "cpw-combat-focus-query-"));
const campaignsDir = path.join(tempRoot, "campaigns");
const dbPath = path.join(tempRoot, "player_wiki.sqlite3");
const dmApiToken = "fixture-combat-focus-dm-token";
const playerApiToken = "fixture-combat-focus-player-token";
const hashToken = (rawToken) => createHash("sha256").update(rawToken, "utf8").digest("hex");

function seedCombatDatabase() {
  const database = new Database(dbPath);
  database.exec(`
    CREATE TABLE users (
      id INTEGER PRIMARY KEY,
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
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL,
      campaign_slug TEXT NOT NULL,
      role TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE api_tokens (
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL,
      label TEXT NOT NULL,
      token_hash TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL,
      last_used_at TEXT NOT NULL,
      expires_at TEXT,
      revoked_at TEXT,
      created_by_user_id INTEGER
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

    CREATE TABLE campaign_combatants (
      id INTEGER PRIMARY KEY,
      campaign_slug TEXT NOT NULL,
      combatant_type TEXT NOT NULL,
      character_slug TEXT,
      player_detail_visible INTEGER NOT NULL DEFAULT 0,
      source_kind TEXT NOT NULL DEFAULT '',
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
      updated_at TEXT NOT NULL DEFAULT '',
      updated_by_user_id INTEGER
    );

    CREATE TABLE campaign_combat_trackers (
      campaign_slug TEXT PRIMARY KEY,
      round_number INTEGER NOT NULL,
      current_combatant_id INTEGER,
      revision INTEGER NOT NULL,
      updated_at TEXT NOT NULL DEFAULT '',
      updated_by_user_id INTEGER
    );

    CREATE TABLE campaign_combat_conditions (
      id INTEGER PRIMARY KEY,
      combatant_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      duration_text TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE campaign_combatant_resource_counters (
      id INTEGER PRIMARY KEY,
      combatant_id INTEGER NOT NULL,
      resource_key TEXT NOT NULL,
      label TEXT NOT NULL,
      current_value INTEGER NOT NULL,
      max_value INTEGER NOT NULL,
      reset_label TEXT NOT NULL DEFAULT '',
      source_label TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE campaign_combatant_resource_notes (
      id INTEGER PRIMARY KEY,
      combatant_id INTEGER NOT NULL,
      label TEXT NOT NULL,
      note TEXT NOT NULL,
      source_label TEXT NOT NULL DEFAULT ''
    );
  `);

  database
    .prepare(
      "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    .run(
      77,
      "fixture-combat-focus-dm@example.com",
      "Fixture Combat DM",
      0,
      "active",
      null,
      1,
      "2026-06-25T08:00:00+00:00",
      "2026-06-25T08:00:00+00:00",
    );
  database
    .prepare(
      "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    .run(
      79,
      "fixture-combat-focus-player@example.com",
      "Fixture Combat Player",
      0,
      "active",
      null,
      1,
      "2026-06-25T08:01:00+00:00",
      "2026-06-25T08:01:00+00:00",
    );
  database
    .prepare(
      "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    )
    .run(501, 77, "linden-pass", "dm", "active", "2026-06-25T08:10:00+00:00", "2026-06-25T08:10:00+00:00");
  database
    .prepare(
      "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    )
    .run(
      502,
      79,
      "linden-pass",
      "player",
      "active",
      "2026-06-25T08:16:00+00:00",
      "2026-06-25T08:16:00+00:00",
    );
  database
    .prepare(
      "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    .run(
      901,
      77,
      "Combat Focus DM Token",
      hashToken(dmApiToken),
      "2026-06-25T08:40:00+00:00",
      "2026-06-25T08:40:00+00:00",
      null,
      null,
      null,
    );
  database
    .prepare(
      "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    .run(
      902,
      79,
      "Combat Focus Player Token",
      hashToken(playerApiToken),
      "2026-06-25T08:45:00+00:00",
      "2026-06-25T08:45:00+00:00",
      null,
      null,
      null,
    );

  database
    .prepare(
      "INSERT INTO character_state (campaign_slug, character_slug, revision, state_json, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?)",
    )
    .run(
      "linden-pass",
      "arden-march",
      8,
      JSON.stringify({ vitals: { current_hp: 38, temp_hp: 0 } }),
      "2026-06-25T09:05:00+00:00",
      77,
    );

  const insertCombatant = database.prepare(`
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
      revision
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  insertCombatant.run(
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
  );
  insertCombatant.run(
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
  );
  database
    .prepare(
      "INSERT INTO campaign_combat_trackers (campaign_slug, round_number, current_combatant_id, revision) VALUES (?, ?, ?, ?)",
    )
    .run("linden-pass", 3, 501, 12);
  database.close();
}

async function requestJson(app, path, role = "dm", headers = {}, method = "GET") {
  const fixtureHeaders = role ? { "X-CPW-Fixture-Role": role } : {};
  const response = await app.fetch(
    new Request(`http://127.0.0.1${path}`, {
      method,
      headers: {
        ...fixtureHeaders,
        ...headers,
      },
    }),
  );
  return { status: response.status, payload: await response.json() };
}

try {
  cpSync(path.join(repoRoot, "tests", "fixtures", "sample_campaigns"), campaignsDir, { recursive: true });
  seedCombatDatabase();

  process.env.CPW_CAMPAIGNS_DIR = campaignsDir;
  process.env.CPW_DB_PATH = dbPath;
  process.env.PORT = "0";
  const { getApp } = await import("../dist/server.js");
  const app = getApp();

  const dmDefault = await requestJson(app, "/api/v1/campaigns/linden-pass/combat");
  assert.equal(dmDefault.status, 200);
  assert.equal(dmDefault.payload.selected_combatant_id, 501);
  assert.equal(dmDefault.payload.selected_combatant?.name, "Clockwork Hound");
  assert.equal(dmDefault.payload.selected_player_character?.character_slug, "arden-march");
  assert.equal(dmDefault.payload.player_character_targets?.[0]?.is_selected, true);

  const dmPcFocus = await requestJson(app, "/api/v1/campaigns/linden-pass/combat?combatant=502");
  assert.equal(dmPcFocus.status, 200);
  assert.equal(dmPcFocus.payload.selected_combatant_id, 502);
  assert.equal(dmPcFocus.payload.selected_combatant?.name, "Arden March");
  assert.equal(dmPcFocus.payload.selected_player_character?.character_slug, "arden-march");
  assert.equal(dmPcFocus.payload.player_character_targets?.[0]?.is_selected, true);
  assert.notEqual(dmPcFocus.payload.live_view_token, dmDefault.payload.live_view_token);

  const dmNpcFocus = await requestJson(app, "/api/v1/campaigns/linden-pass/combat?combatant=501");
  assert.equal(dmNpcFocus.status, 200);
  assert.equal(dmNpcFocus.payload.selected_combatant_id, 501);
  assert.equal(dmNpcFocus.payload.selected_combatant?.name, "Clockwork Hound");

  const dmInvalidFocus = await requestJson(app, "/api/v1/campaigns/linden-pass/combat?combatant=999999");
  assert.equal(dmInvalidFocus.status, 200);
  assert.equal(dmInvalidFocus.payload.selected_combatant_id, 501);
  assert.equal(dmInvalidFocus.payload.live_view_token, dmDefault.payload.live_view_token);

  const dmLivePcFocus = await requestJson(app, "/api/v1/campaigns/linden-pass/combat/live-state?combatant=502");
  assert.equal(dmLivePcFocus.status, 200);
  assert.equal(dmLivePcFocus.payload.selected_combatant_id, 502);

  const dmLivePcUnchanged = await requestJson(app, "/api/v1/campaigns/linden-pass/combat/live-state?combatant=502", "dm", {
    "X-Live-Revision": String(dmLivePcFocus.payload.live_revision),
    "X-Live-View-Token": dmLivePcFocus.payload.live_view_token,
  });
  assert.equal(dmLivePcUnchanged.status, 200);
  assert.equal(dmLivePcUnchanged.payload.changed, false);
  assert.equal("tracker" in dmLivePcUnchanged.payload, false);

  const playerQueryRemainsLocal = await requestJson(app, "/api/v1/campaigns/linden-pass/combat?combatant=502", "player");
  assert.equal(playerQueryRemainsLocal.status, 200);
  assert.equal(playerQueryRemainsLocal.payload.selected_combatant_id, 501);
  assert.equal(playerQueryRemainsLocal.payload.selected_combatant?.name, "Clockwork Hound");
  assert.equal(playerQueryRemainsLocal.payload.selected_player_character, null);

  const dmAdvanceNpcFocus = await requestJson(
    app,
    "/api/v1/campaigns/linden-pass/combat/advance-turn?combatant=501",
    null,
    { Authorization: `Bearer ${dmApiToken}` },
    "POST",
  );
  assert.equal(dmAdvanceNpcFocus.status, 200);
  assert.equal(dmAdvanceNpcFocus.payload.tracker?.round_number, 3);
  assert.equal(dmAdvanceNpcFocus.payload.tracker?.current_turn_label, "Arden March");
  assert.equal(dmAdvanceNpcFocus.payload.selected_combatant_id, 501);
  assert.equal(dmAdvanceNpcFocus.payload.selected_combatant?.name, "Clockwork Hound");
  assert.equal(dmAdvanceNpcFocus.payload.selected_combatant?.is_current_turn, false);

  const dmAdvanceMissingFocus = await requestJson(
    app,
    "/api/v1/campaigns/linden-pass/combat/advance-turn",
    null,
    { Authorization: `Bearer ${dmApiToken}` },
    "POST",
  );
  assert.equal(dmAdvanceMissingFocus.status, 200);
  assert.equal(dmAdvanceMissingFocus.payload.tracker?.round_number, 4);
  assert.equal(dmAdvanceMissingFocus.payload.tracker?.current_turn_label, "Clockwork Hound");
  assert.equal(dmAdvanceMissingFocus.payload.selected_combatant_id, 501);
  assert.equal(dmAdvanceMissingFocus.payload.selected_combatant?.is_current_turn, true);

  const dmAdvanceInvalidFocus = await requestJson(
    app,
    "/api/v1/campaigns/linden-pass/combat/advance-turn?combatant=999999",
    null,
    { Authorization: `Bearer ${dmApiToken}` },
    "POST",
  );
  assert.equal(dmAdvanceInvalidFocus.status, 200);
  assert.equal(dmAdvanceInvalidFocus.payload.tracker?.round_number, 4);
  assert.equal(dmAdvanceInvalidFocus.payload.tracker?.current_turn_label, "Arden March");
  assert.equal(dmAdvanceInvalidFocus.payload.selected_combatant_id, 502);
  assert.equal(dmAdvanceInvalidFocus.payload.selected_combatant?.is_current_turn, true);

  const playerAdvanceWithFocus = await requestJson(
    app,
    "/api/v1/campaigns/linden-pass/combat/advance-turn?combatant=501",
    null,
    { Authorization: `Bearer ${playerApiToken}` },
    "POST",
  );
  assert.equal(playerAdvanceWithFocus.status, 403);
  assert.equal(playerAdvanceWithFocus.payload.error?.code, "forbidden");
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
