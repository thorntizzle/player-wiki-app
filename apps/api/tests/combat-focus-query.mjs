import assert from "node:assert/strict";
import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const tempRoot = mkdtempSync(path.join(tmpdir(), "cpw-combat-focus-query-"));
const campaignsDir = path.join(tempRoot, "campaigns");
const dbPath = path.join(tempRoot, "player_wiki.sqlite3");

function seedCombatDatabase() {
  const database = new Database(dbPath);
  database.exec(`
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
      revision INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE campaign_combat_trackers (
      campaign_slug TEXT PRIMARY KEY,
      round_number INTEGER NOT NULL,
      current_combatant_id INTEGER,
      revision INTEGER NOT NULL
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

async function requestJson(app, path, role = "dm", headers = {}) {
  const response = await app.fetch(
    new Request(`http://127.0.0.1${path}`, {
      headers: {
        "X-CPW-Fixture-Role": role,
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
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
