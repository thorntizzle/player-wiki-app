import { createHash } from "node:crypto";

import type { CampaignViewModel } from "../campaigns/view.js";

export type FixtureCombatRole = "player" | "dm" | "admin";

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
  available_statblock_choices: [];
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

function buildLiveHash(...parts: unknown[]): string {
  const normalized = parts.map((part) => String(part ?? "").trim().toLowerCase()).join("||");
  return createHash("sha1").update(normalized).digest("hex").slice(0, 12);
}

export function buildCombatLiveViewToken(role: FixtureCombatRole, selectedCombatantId: number | null): string {
  const canManageCombat = role === "dm" || role === "admin";
  return buildLiveHash("combat", "player", canManageCombat ? "1" : "0", selectedCombatantId ?? "");
}

export function buildCombatReadOnlyPayload(campaign: CampaignViewModel, role: FixtureCombatRole): CombatReadOnlyPayload {
  const canManageCombat = role === "dm" || role === "admin";
  const canAccessScopedPlayerTools = role === "player" || canManageCombat;
  const canAccessDmContent = canManageCombat;
  return {
    ok: true,
    campaign,
    combat_system_supported: supportsCombatTracker(campaign.system),
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
    available_statblock_choices: [],
    combat_condition_options: [...DND_5E_CONDITION_OPTIONS],
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
