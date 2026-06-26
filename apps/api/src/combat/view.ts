import { createHash } from "node:crypto";
import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";
import type { FixtureSystemsRole } from "../systems/sources.js";

export type FixtureCombatRole = FixtureSystemsRole;

type SqliteDatabase = Database.Database;

const COMBAT_READONLY_REVISION = 0;

const DND_5E_CONDITION_OPTIONS = [
  "Blinded",
  "Charmed",
  "Deafened",
  "Exhaustion",
  "Frightened",
  "Grappled",
  "Incapacitated",
  "Invisible",
  "Paralyzed",
  "Petrified",
  "Poisoned",
  "Prone",
  "Restrained",
  "Stunned",
  "Unconscious",
] as const;

interface CombatTrackerPayload {
  round_number: number;
  current_turn_label: string;
  has_current_turn: boolean;
  combatant_count: number;
  combatants: [];
}

interface AvailableStatblockChoice {
  id: string;
  title: string;
  subtitle: string;
  initiative_bonus: string;
}

interface DMStatblockChoiceRow {
  id: number;
  title: string;
  max_hp: number;
  speed_text: string;
  initiative_bonus: number;
}

interface DMConditionOptionRow {
  name: string;
}

export interface CombatReadOnlyPayload {
  ok: true;
  campaign: CampaignViewModel;
  combat_system_supported: boolean;
  changed: true;
  live_revision: number;
  live_view_token: string;
  tracker: CombatTrackerPayload;
  selected_combatant_id: null;
  selected_combatant: null;
  selected_player_character: null;
  selected_player_combat_sections: [];
  player_character_targets: [];
  available_character_choices: [];
  available_statblock_choices: AvailableStatblockChoice[];
  combat_condition_options: string[];
  poll_settings: {
    active_interval_ms: number;
    idle_interval_ms: number;
    idle_threshold_ms: number;
  };
  links: {
    flask_combat_url: string;
    flask_campaign_url: string;
    flask_characters_url: string;
    flask_session_url: string;
    flask_dm_status_url: string;
    flask_dm_controls_url: string;
    flask_status_url: string;
  };
  permissions: {
    can_manage_combat: boolean;
    can_access_dm_content: boolean;
    can_access_systems: boolean;
  };
}

function normalizeSystemKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function supportsCombatTracker(system: string): boolean {
  return normalizeSystemKey(system) === "dnd5e";
}

function isNoSuchTableOrColumnError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.message.includes("no such table") || error.message.includes("no such column"))
  );
}

function formatInitiativeBonus(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function buildLiveHash(...parts: unknown[]): string {
  const normalized = parts.map((part) => String(part ?? "").trim().toLowerCase()).join("||");
  return createHash("sha1").update(normalized).digest("hex").slice(0, 12);
}

function serializeStatblockChoice(row: DMStatblockChoiceRow): AvailableStatblockChoice {
  return {
    id: String(row.id),
    title: String(row.title || ""),
    subtitle: `HP ${Number(row.max_hp || 0)} - Speed ${String(row.speed_text || "")}`,
    initiative_bonus: formatInitiativeBonus(Number(row.initiative_bonus || 0)),
  };
}

function listAvailableStatblockChoices(
  database: SqliteDatabase,
  campaignSlug: string,
  canAccessDmContent: boolean,
): AvailableStatblockChoice[] {
  if (!canAccessDmContent) {
    return [];
  }
  try {
    return (
      database
        .prepare(
          `
            SELECT id, title, max_hp, speed_text, initiative_bonus
            FROM campaign_dm_statblocks
            WHERE campaign_slug = ?
            ORDER BY updated_at DESC, title COLLATE NOCASE ASC, id DESC
          `,
        )
        .all(campaignSlug) as DMStatblockChoiceRow[]
    ).map(serializeStatblockChoice);
  } catch (error) {
    if (isNoSuchTableOrColumnError(error)) {
      return [];
    }
    throw error;
  }
}

function listCombatConditionOptions(database: SqliteDatabase, campaignSlug: string): string[] {
  try {
    const conditionNames = (
      database
        .prepare(
          `
            SELECT name
            FROM campaign_dm_condition_definitions
            WHERE campaign_slug = ?
            ORDER BY name COLLATE NOCASE ASC, id ASC
          `,
        )
        .all(campaignSlug) as DMConditionOptionRow[]
    ).map((row) => String(row.name || "").trim()).filter(Boolean);
    return [...new Set<string>([...DND_5E_CONDITION_OPTIONS, ...conditionNames])].sort();
  } catch (error) {
    if (isNoSuchTableOrColumnError(error)) {
      return [...DND_5E_CONDITION_OPTIONS];
    }
    throw error;
  }
}

function loadDmContentCombatChoices(
  dbPath: string,
  campaignSlug: string,
  canAccessDmContent: boolean,
): {
  availableStatblockChoices: AvailableStatblockChoice[];
  combatConditionOptions: string[];
} {
  if (!existsSync(dbPath)) {
    return {
      availableStatblockChoices: [],
      combatConditionOptions: [...DND_5E_CONDITION_OPTIONS],
    };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    return {
      availableStatblockChoices: listAvailableStatblockChoices(database, campaignSlug, canAccessDmContent),
      combatConditionOptions: listCombatConditionOptions(database, campaignSlug),
    };
  } finally {
    database.close();
  }
}

export function buildCombatLiveViewToken(role: FixtureCombatRole, selectedCombatantId: number | null): string {
  const canManageCombat = role === "dm" || role === "admin";
  return buildLiveHash("combat", "player", canManageCombat ? "1" : "0", selectedCombatantId ?? "");
}

export function buildCombatReadOnlyPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  role: FixtureCombatRole,
): CombatReadOnlyPayload {
  const canManageCombat = role === "dm" || role === "admin";
  const canAccessScopedPlayerTools = role === "player" || canManageCombat;
  const canAccessDmContent = canManageCombat;
  const combatSystemSupported = supportsCombatTracker(campaign.system);
  const dmContentChoices = combatSystemSupported
    ? loadDmContentCombatChoices(dbPath, campaign.slug, canAccessDmContent)
    : {
        availableStatblockChoices: [],
        combatConditionOptions: [...DND_5E_CONDITION_OPTIONS],
      };
  return {
    ok: true,
    campaign,
    combat_system_supported: combatSystemSupported,
    changed: true,
    live_revision: COMBAT_READONLY_REVISION,
    live_view_token: buildCombatLiveViewToken(role, null),
    tracker: {
      round_number: 1,
      current_turn_label: "",
      has_current_turn: false,
      combatant_count: 0,
      combatants: [],
    },
    selected_combatant_id: null,
    selected_combatant: null,
    selected_player_character: null,
    selected_player_combat_sections: [],
    player_character_targets: [],
    available_character_choices: [],
    available_statblock_choices: dmContentChoices.availableStatblockChoices,
    combat_condition_options: dmContentChoices.combatConditionOptions,
    poll_settings: {
      active_interval_ms: 500,
      idle_interval_ms: 3000,
      idle_threshold_ms: 30000,
    },
    links: {
      flask_combat_url: `/campaigns/${campaign.slug}/combat`,
      flask_campaign_url: `/campaigns/${campaign.slug}`,
      flask_characters_url: canAccessScopedPlayerTools ? `/campaigns/${campaign.slug}/characters` : "",
      flask_session_url: canAccessScopedPlayerTools ? `/campaigns/${campaign.slug}/session` : "",
      flask_dm_status_url: canManageCombat ? `/campaigns/${campaign.slug}/combat/dm` : "",
      flask_dm_controls_url: canManageCombat ? `/campaigns/${campaign.slug}/combat/dm?view=controls` : "",
      flask_status_url: canManageCombat ? `/campaigns/${campaign.slug}/combat/status` : "",
    },
    permissions: {
      can_manage_combat: canManageCombat,
      can_access_dm_content: canAccessDmContent,
      can_access_systems: canAccessScopedPlayerTools,
    },
  };
}
