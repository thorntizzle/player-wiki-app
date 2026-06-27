import assert from "node:assert/strict";
import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";

import { buildCombatReadOnlyPayload } from "../dist/combat/view.js";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const tempRoot = mkdtempSync(path.join(tmpdir(), "cpw-combat-selected-pc-"));
const campaignsDir = path.join(tempRoot, "campaigns");
const dbPath = path.join(tempRoot, "player_wiki.sqlite3");

try {
  cpSync(path.join(repoRoot, "tests", "fixtures", "sample_campaigns"), campaignsDir, { recursive: true });

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
    .run("linden-pass", "arden-march", 8, JSON.stringify({ vitals: { current_hp: 38, temp_hp: 0 } }), "2026-06-25T09:05:00+00:00", 77);

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
  insertCombatant.run(501, "linden-pass", "npc", null, 1, "manual_npc", "", "Clockwork Hound", 18, 4, 2, 1, 22, 28, 3, 40, 25, 1, 0, 1, 6);
  insertCombatant.run(502, "linden-pass", "player_character", "arden-march", 0, "character", "arden-march", "Arden March", 15, 2, 2, 2, 38, 38, 0, 30, 30, 1, 1, 1, 4);
  database
    .prepare("INSERT INTO campaign_combat_trackers (campaign_slug, round_number, current_combatant_id, revision) VALUES (?, ?, ?, ?)")
    .run("linden-pass", 3, 501, 12);
  database.close();

  const payload = await buildCombatReadOnlyPayload(
    { campaignsDir, dbPath, host: "127.0.0.1", port: 0, corsOrigin: "", fixtureAuthEnabled: true },
    { slug: "linden-pass", title: "Linden Pass", system: "DND-5E", systems_library_slug: "DND-5E" },
    "dm",
  );

  assert.equal(payload.ok, true);
  assert.equal(payload.selected_player_character?.character_slug, "arden-march");
  const sectionLabels = payload.selected_player_combat_sections.map((section) => section.label);
  assert.deepEqual(sectionLabels, ["Attacks", "Features"]);

  const attacks = payload.selected_player_combat_sections.find((section) => section.slug === "attacks");
  assert.deepEqual(
    attacks?.attacks?.map((attack) => attack.name),
    ["Light Crossbow", "Quarterstaff"],
  );
  assert.equal(attacks?.attacks?.[0]?.attack_bonus, "5");
  assert.equal(attacks?.attacks?.[0]?.damage, "1d8+2 piercing");

  const features = payload.selected_player_combat_sections.find((section) => section.slug === "features");
  assert.equal(features?.count, 3);
  assert.deepEqual(
    features?.feature_groups?.[0]?.features.map((feature) => feature.name),
    ["Sorcerous Recovery", "Wild Surge", "Chaos Reserve"],
  );
  assert.match(features?.feature_groups?.[0]?.features[0]?.description_html ?? "", /Spend sorcery points/);
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
