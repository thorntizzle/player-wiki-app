import { createHash } from "node:crypto";
import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";
import type { ApiConfig } from "../config.js";
import { listCampaignContentCharacters } from "../content/repository.js";
import type { CampaignCharacterFileRecord } from "../content/types.js";
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

const COMBAT_SOURCE_LABELS: Record<string, string> = {
  character: "Character",
  manual_npc: "Manual NPC",
  dm_statblock: "DM Content",
  systems_monster: "Systems",
};

interface CombatTrackerPayload {
  round_number: number;
  current_turn_label: string;
  has_current_turn: boolean;
  combatant_count: number;
  combatants: PresentedCombatant[];
}

interface AvailableCharacterChoice {
  slug: string;
  name: string;
  subtitle: string;
  initiative_bonus: string;
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

interface CombatTrackerRow {
  round_number: number;
  current_combatant_id: number | null;
  revision: number;
}

interface CombatantRow {
  id: number;
  combatant_type: string;
  character_slug: string | null;
  player_detail_visible: number;
  source_kind: string;
  source_ref: string;
  display_name: string;
  turn_value: number;
  initiative_bonus: number;
  dexterity_modifier: number;
  initiative_priority: number;
  current_hp: number;
  max_hp: number;
  temp_hp: number;
  movement_total: number;
  movement_remaining: number;
  has_action: number;
  has_bonus_action: number;
  has_reaction: number;
  revision: number;
}

interface CombatConditionRow {
  id: number;
  combatant_id: number;
  name: string;
  duration_text: string;
}

interface CombatResourceCounterRow {
  id: number;
  combatant_id: number;
  resource_key: string;
  label: string;
  current_value: number;
  max_value: number;
  reset_label: string;
  source_label: string;
}

interface CombatResourceNoteRow {
  id: number;
  combatant_id: number;
  label: string;
  note: string;
  source_label: string;
}

type PresentedCombatant = Record<string, unknown>;

interface CombatRuntimeState {
  liveRevision: number;
  tracker: CombatTrackerPayload;
  selectedCombatantId: number | null;
  selectedCombatant: PresentedCombatant | null;
  selectedPlayerCharacter: PresentedCombatant | null;
  playerCharacterTargets: Record<string, unknown>[];
  existingCharacterSlugs: Set<string>;
}

export interface CombatReadOnlyPayload {
  ok: true;
  campaign: CampaignViewModel;
  combat_system_supported: boolean;
  changed: true;
  live_revision: number;
  live_view_token: string;
  tracker: CombatTrackerPayload;
  selected_combatant_id: number | null;
  selected_combatant: PresentedCombatant | null;
  selected_player_character: PresentedCombatant | null;
  selected_player_combat_sections: [];
  player_character_targets: Record<string, unknown>[];
  available_character_choices: AvailableCharacterChoice[];
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

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
  }
  return fallback;
}

function asBoolean(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    return !["", "0", "false", "no", "off"].includes(value.trim().toLowerCase());
  }
  return false;
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

function emptyCombatRuntimeState(): CombatRuntimeState {
  return {
    liveRevision: COMBAT_READONLY_REVISION,
    tracker: {
      round_number: 1,
      current_turn_label: "",
      has_current_turn: false,
      combatant_count: 0,
      combatants: [],
    },
    selectedCombatantId: null,
    selectedCombatant: null,
    selectedPlayerCharacter: null,
    playerCharacterTargets: [],
    existingCharacterSlugs: new Set(),
  };
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

function profileClassLevelText(profile: Record<string, unknown>, defaultValue = "Character"): string {
  const classRows = Array.isArray(profile.classes) ? profile.classes : [];
  const parts: string[] = [];
  for (const classRow of classRows) {
    const row = asRecord(classRow);
    const systemsRef = asRecord(row.systems_ref);
    const className = asString(systemsRef.title) || asString(row.class_name);
    const classLevel = asNumber(row.level);
    if (className && classLevel > 0) {
      parts.push(`${className} ${classLevel}`);
    } else if (className) {
      parts.push(className);
    } else if (classLevel > 0) {
      parts.push(`Level ${classLevel}`);
    }
  }
  if (parts.length > 0) {
    return parts.join(" / ");
  }

  return asString(profile.class_level_text) || defaultValue;
}

function serializeCharacterChoice(record: CampaignCharacterFileRecord): AvailableCharacterChoice {
  const definition = record.definition;
  const profile = asRecord(definition.profile);
  const stats = asRecord(definition.stats);
  return {
    slug: record.character_slug,
    name: asString(definition.name) || record.character_slug,
    subtitle: profileClassLevelText(profile).trim(),
    initiative_bonus: String(asNumber(stats.initiative_bonus)),
  };
}

function listAvailableCharacterChoices(
  records: CampaignCharacterFileRecord[],
  canManageCombat: boolean,
  existingCharacterSlugs: Set<string>,
): AvailableCharacterChoice[] {
  if (!canManageCombat) {
    return [];
  }
  return records
    .filter((record) => asString(record.definition.status) === "active")
    .filter((record) => !existingCharacterSlugs.has(record.character_slug))
    .map(serializeCharacterChoice);
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

function characterRecordMap(records: CampaignCharacterFileRecord[]): Map<string, CampaignCharacterFileRecord> {
  return new Map(records.map((record) => [record.character_slug, record]));
}

function rowsByCombatantId<T extends { combatant_id: number }>(rows: T[]): Map<number, T[]> {
  const grouped = new Map<number, T[]>();
  for (const row of rows) {
    const existing = grouped.get(row.combatant_id) || [];
    existing.push(row);
    grouped.set(row.combatant_id, existing);
  }
  return grouped;
}

function combatantSourceKind(row: CombatantRow): string {
  return row.source_kind || (row.character_slug ? "character" : "manual_npc");
}

function presentCombatant(options: {
  row: CombatantRow;
  currentCombatantId: number | null;
  canManageCombat: boolean;
  characterRecordsBySlug: Map<string, CampaignCharacterFileRecord>;
  conditions: CombatConditionRow[];
  resourceCounters: CombatResourceCounterRow[];
  resourceNotes: CombatResourceNoteRow[];
}): PresentedCombatant {
  const row = options.row;
  const isPlayerCharacter = row.combatant_type === "player_character";
  const isNpc = row.combatant_type === "npc";
  const characterSlug = String(row.character_slug || "");
  const characterRecord = characterSlug ? options.characterRecordsBySlug.get(characterSlug) : undefined;
  const definition = characterRecord?.definition || {};
  const profile = asRecord(definition.profile);
  const stats = asRecord(definition.stats);
  const playerDetailVisible = asBoolean(row.player_detail_visible) || isPlayerCharacter;
  const showDetail = options.canManageCombat || isPlayerCharacter || playerDetailVisible;
  const sourceKind = combatantSourceKind(row);
  const sourceLabel = COMBAT_SOURCE_LABELS[sourceKind] || "Unknown source";
  const subtitle = characterRecord ? profileClassLevelText(profile, "").trim() : sourceLabel;

  return {
    id: Number(row.id),
    name: String(row.display_name || ""),
    character_slug: characterSlug,
    source_kind: showDetail ? sourceKind : "",
    source_ref: showDetail ? String(row.source_ref || "") : "",
    source_label: showDetail ? sourceLabel : "",
    type_label: isPlayerCharacter ? "Player character" : "NPC",
    subtitle: showDetail ? subtitle : "",
    show_detail: showDetail,
    player_detail_visible: playerDetailVisible,
    turn_value: Number(row.turn_value || 0),
    initiative_bonus_label: showDetail ? formatInitiativeBonus(Number(row.initiative_bonus || 0)) : "",
    dexterity_modifier: options.canManageCombat ? Number(row.dexterity_modifier || 0) : null,
    dexterity_modifier_label: options.canManageCombat ? formatInitiativeBonus(Number(row.dexterity_modifier || 0)) : "",
    initiative_priority: options.canManageCombat ? Math.max(1, Number(row.initiative_priority || 1)) : 0,
    initiative_priority_label:
      options.canManageCombat && Number(row.initiative_priority || 0) > 0 ? String(row.initiative_priority) : "",
    current_hp: showDetail ? Number(row.current_hp || 0) : null,
    max_hp: showDetail ? Number(row.max_hp || 0) : null,
    temp_hp: showDetail ? Number(row.temp_hp || 0) : null,
    hit_dice: null,
    movement_total: showDetail ? Number(row.movement_total || 0) : null,
    movement_remaining: showDetail ? Number(row.movement_remaining || 0) : null,
    speed_label: showDetail ? asString(stats.speed) || `${Number(row.movement_total || 0)} ft.` : "",
    has_action: showDetail ? asBoolean(row.has_action) : false,
    has_bonus_action: showDetail ? asBoolean(row.has_bonus_action) : false,
    has_reaction: showDetail ? asBoolean(row.has_reaction) : false,
    is_current_turn: Number(row.id) === options.currentCombatantId,
    can_edit_vitals: options.canManageCombat,
    can_edit_resources: options.canManageCombat,
    can_open_character_page: false,
    can_open_status_page: options.canManageCombat,
    can_toggle_player_detail_visibility: options.canManageCombat && isNpc,
    can_manage_combat: options.canManageCombat,
    combatant_revision: Math.max(1, Number(row.revision || 1)),
    state_revision: null,
    npc_resource_counters: showDetail
      ? options.resourceCounters.map((counter) => ({
          resource_key: String(counter.resource_key || ""),
          label: String(counter.label || ""),
          current_value: Number(counter.current_value || 0),
          max_value: Number(counter.max_value || 0),
          reset_label: String(counter.reset_label || ""),
          source_label: String(counter.source_label || ""),
          can_edit: options.canManageCombat && isNpc,
        }))
      : [],
    npc_resource_notes: showDetail
      ? options.resourceNotes.map((note) => ({
          label: String(note.label || ""),
          note: String(note.note || ""),
          source_label: String(note.source_label || ""),
        }))
      : [],
    conditions: options.conditions.map((condition) => ({
      id: Number(condition.id),
      name: String(condition.name || ""),
      duration_text: String(condition.duration_text || ""),
    })),
  };
}

function selectCombatPayload(
  campaignSlug: string,
  tracker: CombatTrackerPayload,
  canManageCombat: boolean,
): Pick<
  CombatRuntimeState,
  "selectedCombatantId" | "selectedCombatant" | "selectedPlayerCharacter" | "playerCharacterTargets"
> {
  const combatants = tracker.combatants;
  const selectedCombatant =
    combatants.find((combatant) => combatant.is_current_turn === true) || combatants[0] || null;
  const selectedCombatantId =
    typeof selectedCombatant?.id === "number" ? Number(selectedCombatant.id) : null;
  const playerCharacters = combatants.filter((combatant) => asString(combatant.character_slug));
  const selectedPlayerCharacter =
    playerCharacters.find((combatant) => combatant.id === selectedCombatantId) ||
    (canManageCombat ? playerCharacters[0] : null) ||
    null;
  const playerCharacterTargets = canManageCombat
    ? playerCharacters.map((combatant) => ({
        combatant_id: combatant.id,
        character_slug: combatant.character_slug,
        name: combatant.name,
        subtitle: combatant.subtitle,
        is_selected: selectedPlayerCharacter !== null && combatant.id === selectedPlayerCharacter.id,
        href: `/app-next/campaigns/${campaignSlug}/combat?combatant=${combatant.id}`,
        flask_href: `/campaigns/${campaignSlug}/combat?combatant=${combatant.id}`,
      }))
    : [];

  return {
    selectedCombatantId,
    selectedCombatant,
    selectedPlayerCharacter,
    playerCharacterTargets,
  };
}

function readCombatTrackerRow(database: SqliteDatabase, campaignSlug: string): CombatTrackerRow | null {
  return (
    (database
      .prepare(
        `
          SELECT round_number, current_combatant_id, revision
          FROM campaign_combat_trackers
          WHERE campaign_slug = ?
        `,
      )
      .get(campaignSlug) as CombatTrackerRow | undefined) || null
  );
}

function readCombatantRows(database: SqliteDatabase, campaignSlug: string): CombatantRow[] {
  return database
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
          revision
        FROM campaign_combatants
        WHERE campaign_slug = ?
        ORDER BY
          turn_value DESC,
          dexterity_modifier DESC,
          initiative_priority ASC,
          display_name COLLATE NOCASE ASC,
          id ASC
      `,
    )
    .all(campaignSlug) as CombatantRow[];
}

function readCombatConditionRows(database: SqliteDatabase, campaignSlug: string): CombatConditionRow[] {
  return database
    .prepare(
      `
        SELECT c.id, c.combatant_id, c.name, c.duration_text
        FROM campaign_combat_conditions AS c
        JOIN campaign_combatants AS e ON e.id = c.combatant_id
        WHERE e.campaign_slug = ?
        ORDER BY c.created_at ASC, c.id ASC
      `,
    )
    .all(campaignSlug) as CombatConditionRow[];
}

function readCombatResourceCounterRows(database: SqliteDatabase, campaignSlug: string): CombatResourceCounterRow[] {
  return database
    .prepare(
      `
        SELECT
          c.id,
          c.combatant_id,
          c.resource_key,
          c.label,
          c.current_value,
          c.max_value,
          c.reset_label,
          c.source_label
        FROM campaign_combatant_resource_counters AS c
        JOIN campaign_combatants AS e ON e.id = c.combatant_id
        WHERE e.campaign_slug = ?
        ORDER BY c.id ASC
      `,
    )
    .all(campaignSlug) as CombatResourceCounterRow[];
}

function readCombatResourceNoteRows(database: SqliteDatabase, campaignSlug: string): CombatResourceNoteRow[] {
  return database
    .prepare(
      `
        SELECT n.id, n.combatant_id, n.label, n.note, n.source_label
        FROM campaign_combatant_resource_notes AS n
        JOIN campaign_combatants AS e ON e.id = n.combatant_id
        WHERE e.campaign_slug = ?
        ORDER BY n.id ASC
      `,
    )
    .all(campaignSlug) as CombatResourceNoteRow[];
}

function loadCombatRuntimeState(
  dbPath: string,
  campaignSlug: string,
  canManageCombat: boolean,
  characterRecords: CampaignCharacterFileRecord[],
): CombatRuntimeState {
  if (!existsSync(dbPath)) {
    return emptyCombatRuntimeState();
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const trackerRow = readCombatTrackerRow(database, campaignSlug);
    const combatantRows = readCombatantRows(database, campaignSlug);
    const conditionsByCombatant = rowsByCombatantId(readCombatConditionRows(database, campaignSlug));
    const countersByCombatant = rowsByCombatantId(readCombatResourceCounterRows(database, campaignSlug));
    const notesByCombatant = rowsByCombatantId(readCombatResourceNoteRows(database, campaignSlug));
    const currentCombatantId =
      trackerRow?.current_combatant_id === null || trackerRow?.current_combatant_id === undefined
        ? null
        : Number(trackerRow.current_combatant_id);
    const characterRecordsBySlug = characterRecordMap(characterRecords);
    const combatants = combatantRows.map((row) =>
      presentCombatant({
        row,
        currentCombatantId,
        canManageCombat,
        characterRecordsBySlug,
        conditions: conditionsByCombatant.get(row.id) || [],
        resourceCounters: countersByCombatant.get(row.id) || [],
        resourceNotes: notesByCombatant.get(row.id) || [],
      }),
    );
    const currentCombatant = combatantRows.find((row) => Number(row.id) === currentCombatantId);
    const tracker: CombatTrackerPayload = {
      round_number: Math.max(1, Number(trackerRow?.round_number || 1)),
      current_turn_label: currentCombatant ? String(currentCombatant.display_name || "") : "",
      has_current_turn: Boolean(currentCombatant),
      combatant_count: combatants.length,
      combatants,
    };
    return {
      liveRevision: trackerRow ? Math.max(1, Number(trackerRow.revision || 1)) : COMBAT_READONLY_REVISION,
      tracker,
      existingCharacterSlugs: new Set(
        combatantRows.map((row) => String(row.character_slug || "")).filter(Boolean),
      ),
      ...selectCombatPayload(campaignSlug, tracker, canManageCombat),
    };
  } catch (error) {
    if (isNoSuchTableOrColumnError(error)) {
      return emptyCombatRuntimeState();
    }
    throw error;
  } finally {
    database.close();
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

export async function buildCombatReadOnlyPayload(
  config: ApiConfig,
  campaign: CampaignViewModel,
  role: FixtureCombatRole,
): Promise<CombatReadOnlyPayload> {
  const canManageCombat = role === "dm" || role === "admin";
  const canAccessScopedPlayerTools = role === "player" || canManageCombat;
  const canAccessDmContent = canManageCombat;
  const combatSystemSupported = supportsCombatTracker(campaign.system);
  const characterRecords =
    combatSystemSupported ? (await listCampaignContentCharacters(config, campaign.slug)) || [] : [];
  const combatRuntime = combatSystemSupported
    ? loadCombatRuntimeState(config.dbPath, campaign.slug, canManageCombat, characterRecords)
    : emptyCombatRuntimeState();
  const availableCharacterChoices = combatSystemSupported
    ? listAvailableCharacterChoices(characterRecords, canManageCombat, combatRuntime.existingCharacterSlugs)
    : [];
  const dmContentChoices = combatSystemSupported
    ? loadDmContentCombatChoices(config.dbPath, campaign.slug, canAccessDmContent)
    : {
        availableStatblockChoices: [],
        combatConditionOptions: [...DND_5E_CONDITION_OPTIONS],
      };
  return {
    ok: true,
    campaign,
    combat_system_supported: combatSystemSupported,
    changed: true,
    live_revision: combatRuntime.liveRevision,
    live_view_token: buildCombatLiveViewToken(role, combatRuntime.selectedCombatantId),
    tracker: combatRuntime.tracker,
    selected_combatant_id: combatRuntime.selectedCombatantId,
    selected_combatant: combatRuntime.selectedCombatant,
    selected_player_character: combatRuntime.selectedPlayerCharacter,
    selected_player_combat_sections: [],
    player_character_targets: combatRuntime.playerCharacterTargets,
    available_character_choices: availableCharacterChoices,
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
