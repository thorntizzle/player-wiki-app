import { createHash } from "node:crypto";
import { existsSync } from "node:fs";

import { openSqliteDatabase, type SqliteDatabase } from "../sqlite.js";

import type { CampaignViewModel } from "../campaigns/view.js";
import type { ApiConfig } from "../config.js";
import { persistCharacterStateForDefinition } from "../content/characterState.js";
import { listCampaignContentCharacters } from "../content/repository.js";
import type { CampaignCharacterFileRecord } from "../content/types.js";
import type { FixtureSystemsRole } from "../systems/sources.js";

export type FixtureCombatRole = FixtureSystemsRole;


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

const COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS: Record<string, string> = {
  actions: "Actions",
  bonus_actions: "Bonus Actions",
  reactions: "Reactions",
  attacks: "Attacks",
  features: "Features",
};

const STATBLOCK_DEX_MODIFIER_PATTERN = /\bDEX\s+\d+\s+\(([+-]\d+)\)/i;
const NPC_RESOURCE_TAG_PATTERN = /\{@[a-zA-Z0-9_-]+\s+([^}|]+)(?:\|[^}]*)?\}/g;
const NPC_RESOURCE_MARKDOWN_DECORATION_PATTERN = /[*_`#>\[\]]+/g;
const NPC_RESOURCE_DAILY_LIST_PATTERN = /(\d+)\s*\/\s*day(\s+each)?\s*:\s*([^.;\n]+)/gi;
const NPC_RESOURCE_NAMED_DAILY_PATTERN = /([A-Za-z][A-Za-z0-9 '\-,]{1,90}?)\s*\((\d+)\s*\/\s*day\)/gi;
const NPC_RESOURCE_EXPLICIT_COUNTER_PATTERN =
  /^\s*(?:[-*]\s*)?([A-Za-z][^:|/]{1,80}?)\s*[:|-]\s*(\d+)\s*\/\s*(\d+)\b/i;
const NPC_RESOURCE_AT_WILL_PATTERN = /\bat\s+will\s*:\s*([^.;\n]+)/gi;
const NPC_RESOURCE_RECHARGE_PATTERN = /\((recharge\s+\d+\s*[-+]\s*\d+)\)/gi;

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

interface DMStatblockDetailRow extends DMStatblockChoiceRow {
  body_markdown: string;
  movement_total: number;
}

interface SystemsMonsterEntryRow {
  source_id: string;
  entry_key: string;
  entry_type: string;
  title: string;
  metadata_json: string;
  body_json: string;
}

interface SystemsSourceAccessRow {
  source_id: string;
  configured_enabled: number | null;
  configured_visibility: string | null;
}

interface CampaignSourceSeed {
  source_id: string;
  enabled?: boolean;
  default_visibility?: string;
}

interface NpcResourceCounterSeed {
  resourceKey: string;
  label: string;
  currentValue: number;
  maxValue: number;
  resetLabel: string;
  sourceLabel: string;
}

interface NpcResourceNoteSeed {
  label: string;
  note: string;
  sourceLabel: string;
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

interface CharacterStateRow {
  character_slug: string;
  revision: number;
  state_json: string;
}

interface CharacterStateSnapshot {
  revision: number;
  state: Record<string, unknown>;
}

type PresentedCombatant = Record<string, unknown>;

interface CombatCharacterWorkspaceFeature {
  name: string;
  href: string;
  group_title: string;
  metadata: string[];
  description_html: string;
}

interface CombatCharacterWorkspaceAttack {
  name: string;
  attack_bonus: string;
  damage: string;
  range: string;
  notes: string;
}

interface CombatCharacterWorkspaceHiddenAttack {
  name: string;
  href: string;
}

interface CombatCharacterWorkspaceFeatureGroup {
  title: string;
  features: CombatCharacterWorkspaceFeature[];
}

interface CombatCharacterWorkspaceSection {
  slug: string;
  label: string;
  count: number;
  features?: CombatCharacterWorkspaceFeature[];
  attacks?: CombatCharacterWorkspaceAttack[];
  hidden_attacks?: CombatCharacterWorkspaceHiddenAttack[];
  feature_groups?: CombatCharacterWorkspaceFeatureGroup[];
  empty_message: string;
}

interface CombatRuntimeState {
  liveRevision: number;
  tracker: CombatTrackerPayload;
  selectedCombatantId: number | null;
  selectedCombatant: PresentedCombatant | null;
  selectedPlayerCharacter: PresentedCombatant | null;
  selectedPlayerCombatSections: CombatCharacterWorkspaceSection[];
  playerCharacterTargets: Record<string, unknown>[];
  existingCharacterSlugs: Set<string>;
}

interface CombatReadOnlyOptions {
  requestedCombatantId?: number | null;
}

type CombatMutationResult =
  | { status: "ok" }
  | { status: "validation_error"; message: string }
  | { status: "forbidden"; message: string }
  | { status: "state_conflict"; message: string };

class CombatMutationConflictError extends Error {}

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
  selected_player_combat_sections: CombatCharacterWorkspaceSection[];
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

function resetCombatantTurnResources(
  database: SqliteDatabase,
  campaignSlug: string,
  combatantId: number,
  actorUserId: number,
  now: string,
  missingMessage: string,
): void {
  const combatantUpdate = database
    .prepare(
      `
        UPDATE campaign_combatants
        SET has_action = 1,
            has_bonus_action = 1,
            has_reaction = 1,
            movement_remaining = movement_total,
            revision = revision + 1,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ? AND id = ?
      `,
    )
    .run(now, actorUserId, campaignSlug, combatantId);
  if (combatantUpdate.changes !== 1) {
    throw new CombatMutationConflictError(missingMessage);
  }
}

function normalizeSystemKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function payloadString(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
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

function utcIsoTimestamp(): string {
  return new Date().toISOString().replace("Z", "+00:00");
}

export function supportsCombatTracker(system: string): boolean {
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

function normalizeNpcResourceText(value: string): string {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .replace(/\u2013|\u2014/g, "-")
    .replace(NPC_RESOURCE_TAG_PATTERN, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanNpcResourceLabel(value: string): string {
  return normalizeNpcResourceText(value)
    .replace(NPC_RESOURCE_MARKDOWN_DECORATION_PATTERN, "")
    .replace(/^\s*[-:|.]+\s*/, "")
    .replace(/\s*[-:|.]+\s*$/, "")
    .trim();
}

function splitLimitedUseItems(value: string): string[] {
  return normalizeNpcResourceText(value)
    .replace(/\band\b/gi, ",")
    .split(/[,;]/)
    .map((item) => cleanNpcResourceLabel(item))
    .filter(Boolean);
}

function npcResourceKey(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "resource";
}

function appendNpcResourceCounter(
  counters: NpcResourceCounterSeed[],
  seenKeys: Set<string>,
  options: {
    label: string;
    currentValue: number;
    maxValue: number;
    resetLabel: string;
    sourceLabel: string;
  },
): void {
  const label = cleanNpcResourceLabel(options.label);
  const maxValue = Math.trunc(options.maxValue);
  if (!label || maxValue < 1) {
    return;
  }
  const resourceKey = npcResourceKey(label);
  if (seenKeys.has(resourceKey)) {
    return;
  }
  seenKeys.add(resourceKey);
  counters.push({
    resourceKey,
    label,
    currentValue: Math.max(0, Math.min(Math.trunc(options.currentValue), maxValue)),
    maxValue,
    resetLabel: options.resetLabel,
    sourceLabel: options.sourceLabel,
  });
}

function appendNpcResourceNote(
  notes: NpcResourceNoteSeed[],
  seenNotes: Set<string>,
  options: { label: string; note: string; sourceLabel: string },
): void {
  const label = cleanNpcResourceLabel(options.label);
  const note = cleanNpcResourceLabel(options.note);
  if (!label || !note) {
    return;
  }
  const noteKey = `${label.toLowerCase()}||${note.toLowerCase()}`;
  if (seenNotes.has(noteKey)) {
    return;
  }
  seenNotes.add(noteKey);
  notes.push({ label, note, sourceLabel: options.sourceLabel });
}

function labelBeforeNpcResourceMatch(line: string, matchStart: number): string {
  const prefix = line.slice(0, matchStart).trim();
  const parts = prefix.split(/[.;]/);
  return cleanNpcResourceLabel(parts[parts.length - 1] || "");
}

function titleCaseNpcResourceNote(value: string): string {
  return cleanNpcResourceLabel(value.toLowerCase()).replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function buildNpcResourceSeedsFromMarkdown(
  markdownText: string,
  sourceLabel: string,
): {
  counters: NpcResourceCounterSeed[];
  notes: NpcResourceNoteSeed[];
} {
  const counters: NpcResourceCounterSeed[] = [];
  const notes: NpcResourceNoteSeed[] = [];
  const seenCounterKeys = new Set<string>();
  const seenNotes = new Set<string>();
  const lines = String(markdownText || "").replace(/\r\n/g, "\n").split("\n");

  for (const rawLine of lines) {
    const line = normalizeNpcResourceText(rawLine);
    if (!line) {
      continue;
    }

    const explicitMatch = NPC_RESOURCE_EXPLICIT_COUNTER_PATTERN.exec(line);
    if (explicitMatch) {
      const maxValue = Number(explicitMatch[3]);
      appendNpcResourceCounter(counters, seenCounterKeys, {
        label: explicitMatch[1] || "",
        currentValue: Math.min(Number(explicitMatch[2]), maxValue),
        maxValue,
        resetLabel: "Per source",
        sourceLabel,
      });
    }

    for (const match of line.matchAll(NPC_RESOURCE_NAMED_DAILY_PATTERN)) {
      const maxValue = Number(match[2]);
      appendNpcResourceCounter(counters, seenCounterKeys, {
        label: match[1] || "",
        currentValue: maxValue,
        maxValue,
        resetLabel: "Per day",
        sourceLabel,
      });
    }

    for (const match of line.matchAll(NPC_RESOURCE_DAILY_LIST_PATTERN)) {
      const maxValue = Number(match[1]);
      for (const label of splitLimitedUseItems(match[3] || "")) {
        appendNpcResourceCounter(counters, seenCounterKeys, {
          label,
          currentValue: maxValue,
          maxValue,
          resetLabel: "Per day",
          sourceLabel,
        });
      }
    }

    for (const match of line.matchAll(NPC_RESOURCE_AT_WILL_PATTERN)) {
      const note = splitLimitedUseItems(match[1] || "").join(", ") || cleanNpcResourceLabel(match[1] || "");
      if (note) {
        appendNpcResourceNote(notes, seenNotes, {
          label: "At-will spellcasting",
          note,
          sourceLabel,
        });
      }
    }

    for (const match of line.matchAll(NPC_RESOURCE_RECHARGE_PATTERN)) {
      appendNpcResourceNote(notes, seenNotes, {
        label: labelBeforeNpcResourceMatch(line, match.index || 0) || "Recharge",
        note: titleCaseNpcResourceNote(match[1] || ""),
        sourceLabel,
      });
    }
  }

  return { counters, notes };
}

function collectStructuredNpcResourceText(value: unknown): string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (typeof value === "string") {
    const cleaned = normalizeNpcResourceText(value);
    return cleaned ? [cleaned] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectStructuredNpcResourceText(item));
  }
  if (typeof value === "object") {
    const record = asRecord(value);
    const lines: string[] = [];
    const name = normalizeNpcResourceText(payloadString(record.name));
    if (name) {
      lines.push(name);
    }
    if (Object.hasOwn(record, "entries")) {
      lines.push(...collectStructuredNpcResourceText(record.entries));
    } else if (Object.hasOwn(record, "entry")) {
      lines.push(...collectStructuredNpcResourceText(record.entry));
    }
    for (const key of ["traits", "actions", "bonus_actions", "reactions", "legendary_actions", "mythic_actions"]) {
      if (Object.hasOwn(record, key)) {
        lines.push(...collectStructuredNpcResourceText(record[key]));
      }
    }
    return lines;
  }
  return [];
}

function buildNpcResourceSeedsFromStructuredValue(
  value: unknown,
  sourceLabel: string,
): {
  counters: NpcResourceCounterSeed[];
  notes: NpcResourceNoteSeed[];
} {
  return buildNpcResourceSeedsFromMarkdown(collectStructuredNpcResourceText(value).join("\n"), sourceLabel);
}

function extractStatblockDexterityModifier(markdownText: string, fallback: number): number {
  const match = STATBLOCK_DEX_MODIFIER_PATTERN.exec(markdownText || "");
  if (!match) {
    return fallback;
  }
  const parsed = Number(match[1]);
  return Number.isSafeInteger(parsed) ? parsed : fallback;
}

function parseJsonObject(rawJson: string): Record<string, unknown> {
  try {
    return asRecord(JSON.parse(rawJson || "{}"));
  } catch {
    return {};
  }
}

function parseJsonUnknown(rawJson: string): unknown {
  try {
    return JSON.parse(rawJson || "{}");
  } catch {
    return {};
  }
}

function parseCampaignSourceSeeds(campaignConfig: Record<string, unknown>): Map<string, CampaignSourceSeed> {
  const seeds = new Map<string, CampaignSourceSeed>();
  const rawSources = campaignConfig.systems_sources;
  if (!Array.isArray(rawSources)) {
    return seeds;
  }
  for (const rawSource of rawSources) {
    const record = asRecord(rawSource);
    const sourceId = payloadString(record.source_id);
    if (!sourceId) {
      continue;
    }
    seeds.set(sourceId, {
      source_id: sourceId,
      enabled: asBoolean(record.enabled),
      default_visibility: payloadString(record.default_visibility),
    });
  }
  return seeds;
}

function coerceMonsterInteger(value: unknown, defaultValue = 0): number {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function extractMonsterHpAverage(value: unknown): number {
  const record = asRecord(value);
  if (Object.keys(record).length > 0) {
    return coerceMonsterInteger(record.average, 0);
  }
  return coerceMonsterInteger(value, 0);
}

function extractMaxDistance(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string") {
    const distances = [...value.matchAll(/\d+/g)]
      .map((match) => Number.parseInt(match[0] || "", 10))
      .filter(Number.isFinite);
    return distances.length > 0 ? Math.max(...distances) : 0;
  }
  if (Array.isArray(value)) {
    const distances = value.map(extractMaxDistance);
    return distances.length > 0 ? Math.max(...distances) : 0;
  }
  if (typeof value === "object" && value !== null) {
    const distances = Object.values(value).map(extractMaxDistance);
    return distances.length > 0 ? Math.max(...distances) : 0;
  }
  return 0;
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
    selectedPlayerCombatSections: [],
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

function escapeHtml(rawText: string): string {
  return rawText
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderPlainMarkdownParagraphs(markdownText: string): string {
  const normalized = markdownText.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return "";
  }
  return normalized
    .split(/\n{2,}/)
    .map((block) => `<p>${escapeHtml(block).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

function titleCaseText(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function featureGroupTitle(feature: Record<string, unknown>): string {
  return (
    asString(feature.group_title) ||
    asString(feature.group) ||
    asString(feature.source) ||
    titleCaseText(asString(feature.category)) ||
    "Features"
  );
}

function featureMetadata(feature: Record<string, unknown>): string[] {
  const metadata = asArray(feature.metadata).map((item) => asString(item)).filter(Boolean);
  const source = asString(feature.source);
  if (source && !metadata.includes(source)) {
    metadata.push(source);
  }
  return metadata;
}

function serializeCombatWorkspaceFeature(
  feature: Record<string, unknown>,
  groupTitle: string,
): CombatCharacterWorkspaceFeature {
  return {
    name: asString(feature.name),
    href: asString(feature.href),
    group_title: groupTitle,
    metadata: featureMetadata(feature),
    description_html:
      asString(feature.description_html) || renderPlainMarkdownParagraphs(asString(feature.description_markdown)),
  };
}

function iterFeatureEntries(entries: unknown): Record<string, unknown>[] {
  const flattened: Record<string, unknown>[] = [];
  for (const item of asArray(entries)) {
    const feature = asRecord(item);
    if (Object.keys(feature).length === 0) {
      continue;
    }
    flattened.push(feature);
    flattened.push(...iterFeatureEntries(feature.children));
  }
  return flattened;
}

function characterFeatureEntries(record: CampaignCharacterFileRecord): Record<string, unknown>[] {
  const definition = record.definition;
  const groupedFeatures = asArray(definition.feature_groups).flatMap((group) => {
    const groupRecord = asRecord(group);
    const groupTitle = asString(groupRecord.title) || "Features";
    return iterFeatureEntries(groupRecord.entries).map((feature) => ({
      ...feature,
      group_title: asString(feature.group_title) || groupTitle,
    }));
  });
  const flatFeatures = asArray(definition.features).map(asRecord).filter((feature) => Object.keys(feature).length > 0);
  return [...groupedFeatures, ...flatFeatures];
}

function combatFeatureIsAvailable(feature: Record<string, unknown>): boolean {
  const availability = asRecord(feature.combat_availability);
  return Object.keys(availability).length === 0 || asBoolean(availability.available ?? true);
}

function normalizeAttackName(value: string): string {
  const match = value.match(/^Crossbow,\s*(Light|Heavy)$/i);
  if (match) {
    return `${match[1]} Crossbow`;
  }
  return value;
}

function serializeCombatWorkspaceAttack(attack: Record<string, unknown>): CombatCharacterWorkspaceAttack | null {
  const name = normalizeAttackName(asString(attack.name));
  if (!name) {
    return null;
  }
  return {
    name,
    attack_bonus: payloadString(attack.attack_bonus) || payloadString(attack.to_hit),
    damage: payloadString(attack.damage) || payloadString(attack.damage_label),
    range: payloadString(attack.range) || payloadString(attack.range_label),
    notes: payloadString(attack.notes) || payloadString(attack.description),
  };
}

function buildCombatCharacterWorkspaceSections(record: CampaignCharacterFileRecord): CombatCharacterWorkspaceSection[] {
  const actionFeatures: CombatCharacterWorkspaceFeature[] = [];
  const bonusActionFeatures: CombatCharacterWorkspaceFeature[] = [];
  const reactionFeatures: CombatCharacterWorkspaceFeature[] = [];
  const featureGroups = new Map<string, CombatCharacterWorkspaceFeature[]>();

  for (const feature of characterFeatureEntries(record)) {
    if (!combatFeatureIsAvailable(feature)) {
      continue;
    }
    const groupTitle = featureGroupTitle(feature);
    const serialized = serializeCombatWorkspaceFeature(feature, groupTitle);
    if (!serialized.name) {
      continue;
    }

    const activationType = asString(feature.activation_type).toLowerCase();
    if (activationType === "action") {
      actionFeatures.push(serialized);
    } else if (activationType === "bonus_action") {
      bonusActionFeatures.push(serialized);
    } else if (activationType === "reaction") {
      reactionFeatures.push(serialized);
    }

    const existing = featureGroups.get(groupTitle) || [];
    existing.push(serialized);
    featureGroups.set(groupTitle, existing);
  }

  const attacks = asArray(record.definition.attacks)
    .map((attack) => serializeCombatWorkspaceAttack(asRecord(attack)))
    .filter((attack): attack is CombatCharacterWorkspaceAttack => attack !== null);
  const hiddenAttacks = asArray(record.definition.hidden_attacks)
    .map((item) => {
      const attack = asRecord(item);
      const name = Object.keys(attack).length > 0 ? asString(attack.name) : asString(item);
      return name ? { name, href: asString(attack.href) } : null;
    })
    .filter((attack): attack is CombatCharacterWorkspaceHiddenAttack => attack !== null);
  const featureGroupSummaries = [...featureGroups.entries()].map(([title, features]) => ({ title, features }));

  const sections: CombatCharacterWorkspaceSection[] = [
    {
      slug: "actions",
      label: COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS.actions,
      count: actionFeatures.length,
      features: actionFeatures,
      empty_message: "No action-specific features are recorded on this sheet yet.",
    },
    {
      slug: "bonus_actions",
      label: COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS.bonus_actions,
      count: bonusActionFeatures.length,
      features: bonusActionFeatures,
      empty_message: "No bonus-action features are recorded on this sheet yet.",
    },
    {
      slug: "reactions",
      label: COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS.reactions,
      count: reactionFeatures.length,
      features: reactionFeatures,
      empty_message: "No reaction features are recorded on this sheet yet.",
    },
    {
      slug: "attacks",
      label: COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS.attacks,
      count: attacks.length,
      attacks,
      hidden_attacks: hiddenAttacks,
      empty_message: "No attacks are currently active on this sheet.",
    },
    {
      slug: "features",
      label: COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS.features,
      count: featureGroupSummaries.reduce((total, group) => total + group.features.length, 0),
      feature_groups: featureGroupSummaries,
      empty_message: "No feature details are recorded on this sheet yet.",
    },
  ];

  return sections.filter((section) => section.count > 0 || (section.hidden_attacks?.length ?? 0) > 0);
}

function parseStateJson(rawJson: string): Record<string, unknown> {
  try {
    return asRecord(JSON.parse(rawJson));
  } catch {
    return {};
  }
}

function readCharacterStateSnapshot(
  database: SqliteDatabase,
  campaignSlug: string,
  characterSlug: string,
): CharacterStateSnapshot | null {
  try {
    const row = database
      .prepare(
        `
          SELECT character_slug, revision, state_json
          FROM character_state
          WHERE campaign_slug = ?
            AND character_slug = ?
        `,
      )
      .get(campaignSlug, characterSlug) as CharacterStateRow | undefined;
    return row
      ? {
          revision: Math.max(1, Number(row.revision || 1)),
          state: parseStateJson(row.state_json),
        }
      : null;
  } catch (error) {
    if (isNoSuchTableOrColumnError(error)) {
      return null;
    }
    throw error;
  }
}

function readCharacterStateSnapshots(
  database: SqliteDatabase,
  campaignSlug: string,
): Map<string, CharacterStateSnapshot> {
  const snapshots = new Map<string, CharacterStateSnapshot>();
  try {
    const rows = database
      .prepare(
        `
          SELECT character_slug, revision, state_json
          FROM character_state
          WHERE campaign_slug = ?
        `,
      )
      .all(campaignSlug) as CharacterStateRow[];
    for (const row of rows) {
      snapshots.set(String(row.character_slug || ""), {
        revision: Math.max(1, Number(row.revision || 1)),
        state: parseStateJson(row.state_json),
      });
    }
  } catch (error) {
    if (isNoSuchTableOrColumnError(error)) {
      return snapshots;
    }
    throw error;
  }
  return snapshots;
}

function readCharacterStateVitals(
  database: SqliteDatabase,
  campaignSlug: string,
  characterSlug: string,
): Record<string, unknown> {
  const snapshot = readCharacterStateSnapshot(database, campaignSlug, characterSlug);
  return snapshot ? asRecord(snapshot.state.vitals) : {};
}

function parseMovementTotal(value: unknown): number {
  const matches = [...payloadString(value).matchAll(/\d+/g)].map((match) => Number(match[0]));
  return matches.length > 0 ? Math.max(...matches) : 0;
}

function extractDexterityModifier(stats: Record<string, unknown>): number {
  const abilityScores = asRecord(stats.ability_scores);
  const dexterity =
    abilityScores.dex ??
    abilityScores.DEX ??
    abilityScores.dexterity ??
    abilityScores.Dexterity ??
    abilityScores.DEXTERITY;
  if (typeof dexterity === "number" || typeof dexterity === "string") {
    const parsedScore = parseWholeInteger(payloadString(dexterity));
    return parsedScore === null ? 0 : Math.floor((parsedScore - 10) / 2);
  }

  const dexterityRecord = asRecord(dexterity);
  const rawModifier = dexterityRecord.modifier;
  if (rawModifier !== null && rawModifier !== undefined && payloadString(rawModifier) !== "") {
    const parsedModifier = parseWholeInteger(payloadString(rawModifier));
    return parsedModifier === null ? 0 : parsedModifier;
  }

  const rawScore = dexterityRecord.score;
  if (rawScore === null || rawScore === undefined || payloadString(rawScore) === "") {
    return 0;
  }
  const parsedScore = parseWholeInteger(payloadString(rawScore));
  return parsedScore === null ? 0 : Math.floor((parsedScore - 10) / 2);
}

function parseWholeInteger(value: string): number | null {
  if (!/^[+-]?\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function parseCombatInteger(
  value: unknown,
  label: string,
  defaultValue: number | null,
  minimum: number | null = 0,
): { ok: true; value: number } | { ok: false; message: string } {
  const normalized = value === null || value === undefined ? "" : payloadString(value);
  const parsed =
    normalized === ""
      ? defaultValue
      : parseWholeInteger(normalized);
  if (parsed === null) {
    return {
      ok: false,
      message: normalized === "" ? `${label} is required.` : `${label} must be a whole number.`,
    };
  }
  if (minimum !== null && parsed < minimum) {
    return { ok: false, message: `${label} cannot be less than ${minimum}.` };
  }
  return { ok: true, value: parsed };
}

function parseCombatBoolean(
  payload: Record<string, unknown>,
  key: string,
  label: string,
  defaultValue: boolean,
): { ok: true; value: boolean } | { ok: false; message: string } {
  if (!Object.hasOwn(payload, key)) {
    return { ok: true, value: defaultValue };
  }
  const value = payload[key];
  if (typeof value === "boolean") {
    return { ok: true, value };
  }
  if (typeof value === "number" && (value === 0 || value === 1)) {
    return { ok: true, value: value === 1 };
  }
  const normalized = value === null || value === undefined ? "" : String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return { ok: true, value: true };
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return { ok: true, value: false };
  }
  return { ok: false, message: `${label} must be true or false.` };
}

function parseInitiativePriority(
  value: unknown,
  defaultValue: number,
): { ok: true; value: number } | { ok: false; message: string } {
  if (value === null || value === undefined) {
    return { ok: true, value: Math.max(1, Math.trunc(defaultValue || 1)) };
  }
  const normalized = payloadString(value);
  if (!normalized) {
    return { ok: true, value: 1 };
  }
  const parsed = parseWholeInteger(normalized);
  if (parsed === null) {
    return { ok: false, message: "Priority must be a whole number." };
  }
  if (parsed < 1) {
    return { ok: false, message: "Priority must be 1 or higher." };
  }
  return { ok: true, value: parsed };
}

function parseOptionalCombatantRevision(
  value: unknown,
): { ok: true; value: number | null } | { ok: false; message: string } {
  const normalized = value === null || value === undefined ? "" : payloadString(value);
  if (!normalized) {
    return { ok: true, value: null };
  }
  const parsed = parseWholeInteger(normalized);
  if (parsed === null) {
    return { ok: false, message: "Expected combatant revision must be a whole number." };
  }
  return { ok: true, value: parsed };
}

function parseExpectedCharacterStateRevision(
  value: unknown,
): { ok: true; value: number } | { ok: false; message: string } {
  const normalized = value === null || value === undefined ? "" : payloadString(value);
  if (!normalized) {
    return { ok: false, message: "Expected revision is required." };
  }
  const parsed = parseWholeInteger(normalized);
  if (parsed === null) {
    return { ok: false, message: "Expected revision must be a whole number." };
  }
  return { ok: true, value: parsed };
}

function buildPlayerCharacterSnapshot(
  database: SqliteDatabase,
  campaignSlug: string,
  record: CampaignCharacterFileRecord,
): {
  initiativeBonus: number;
  dexterityModifier: number;
  currentHp: number;
  maxHp: number;
  tempHp: number;
  movementTotal: number;
} {
  const stats = asRecord(record.definition.stats);
  const vitals = readCharacterStateVitals(database, campaignSlug, record.character_slug);
  return {
    initiativeBonus: asNumber(stats.initiative_bonus),
    dexterityModifier: extractDexterityModifier(stats),
    currentHp: asNumber(vitals.current_hp),
    maxHp: asNumber(stats.max_hp),
    tempHp: asNumber(vitals.temp_hp),
    movementTotal: parseMovementTotal(stats.speed),
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

function readDmStatblockDetailRow(
  database: SqliteDatabase,
  campaignSlug: string,
  statblockId: number,
): DMStatblockDetailRow | null {
  return (
    (database
      .prepare(
        `
          SELECT id, title, body_markdown, max_hp, speed_text, movement_total, initiative_bonus
          FROM campaign_dm_statblocks
          WHERE campaign_slug = ? AND id = ?
        `,
      )
      .get(campaignSlug, statblockId) as DMStatblockDetailRow | undefined) || null
  );
}

function readSystemsMonsterEntryRow(
  database: SqliteDatabase,
  librarySlug: string,
  entryKey: string,
): SystemsMonsterEntryRow | null {
  return (
    (database
      .prepare(
        `
          SELECT source_id, entry_key, entry_type, title, metadata_json, body_json
          FROM systems_entries
          WHERE library_slug = ? AND entry_key = ?
        `,
      )
      .get(librarySlug, entryKey) as SystemsMonsterEntryRow | undefined) || null
  );
}

function readSystemsSourceAccessRow(
  database: SqliteDatabase,
  campaignSlug: string,
  librarySlug: string,
  sourceId: string,
): SystemsSourceAccessRow | null {
  return (
    (database
      .prepare(
        `
          SELECT
            systems_sources.source_id,
            campaign_enabled_sources.is_enabled AS configured_enabled,
            campaign_enabled_sources.default_visibility AS configured_visibility
          FROM systems_sources
          LEFT JOIN campaign_enabled_sources
            ON campaign_enabled_sources.campaign_slug = ?
           AND campaign_enabled_sources.library_slug = systems_sources.library_slug
           AND campaign_enabled_sources.source_id = systems_sources.source_id
          WHERE systems_sources.library_slug = ?
            AND systems_sources.source_id = ?
        `,
      )
      .get(campaignSlug, librarySlug, sourceId) as SystemsSourceAccessRow | undefined) || null
  );
}

function isSystemsSourceEnabledForCampaign(
  database: SqliteDatabase,
  campaignSlug: string,
  librarySlug: string,
  sourceId: string,
  sourceSeeds: Map<string, CampaignSourceSeed>,
): boolean {
  const sourceRow = readSystemsSourceAccessRow(database, campaignSlug, librarySlug, sourceId);
  if (!sourceRow) {
    return false;
  }
  const isConfigured = sourceRow.configured_enabled !== null || Boolean(sourceRow.configured_visibility);
  return isConfigured ? Boolean(sourceRow.configured_enabled) : Boolean(sourceSeeds.get(sourceId)?.enabled);
}

function isSystemsEntryEnabledForCampaign(
  database: SqliteDatabase,
  campaignSlug: string,
  librarySlug: string,
  entry: SystemsMonsterEntryRow,
  sourceSeeds: Map<string, CampaignSourceSeed>,
): boolean {
  if (!isSystemsSourceEnabledForCampaign(database, campaignSlug, librarySlug, entry.source_id, sourceSeeds)) {
    return false;
  }
  const override = database
    .prepare(
      `
        SELECT is_enabled_override
        FROM campaign_entry_overrides
        WHERE campaign_slug = ?
          AND library_slug = ?
          AND entry_key = ?
      `,
    )
    .get(campaignSlug, librarySlug, entry.entry_key) as { is_enabled_override: number | null } | undefined;
  return override?.is_enabled_override !== 0;
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
  characterStateBySlug: Map<string, CharacterStateSnapshot>;
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
  const characterState = characterSlug ? options.characterStateBySlug.get(characterSlug) : undefined;
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
    state_revision: isPlayerCharacter && characterState ? characterState.revision : null,
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
  requestedCombatantId: number | null,
): Pick<
  CombatRuntimeState,
  "selectedCombatantId" | "selectedCombatant" | "selectedPlayerCharacter" | "playerCharacterTargets"
> {
  const combatants = tracker.combatants;
  const requestedCombatant =
    canManageCombat && requestedCombatantId !== null
      ? combatants.find((combatant) => combatant.id === requestedCombatantId) || null
      : null;
  const selectedCombatant =
    requestedCombatant || combatants.find((combatant) => combatant.is_current_turn === true) || combatants[0] || null;
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

function ensureCombatTrackerRow(
  database: SqliteDatabase,
  campaignSlug: string,
  actorUserId: number | null,
): CombatTrackerRow {
  const existing = readCombatTrackerRow(database, campaignSlug);
  if (existing) {
    return existing;
  }
  database
    .prepare(
      `
        INSERT INTO campaign_combat_trackers (
          campaign_slug,
          round_number,
          current_combatant_id,
          revision,
          updated_at,
          updated_by_user_id
        )
        VALUES (?, 1, NULL, 1, ?, ?)
      `,
    )
    .run(campaignSlug, utcIsoTimestamp(), actorUserId);
  const created = readCombatTrackerRow(database, campaignSlug);
  if (!created) {
    throw new Error("Failed to persist campaign combat tracker.");
  }
  return created;
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

function readCombatantRow(database: SqliteDatabase, campaignSlug: string, combatantId: number): CombatantRow | null {
  return (
    (database
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
          WHERE campaign_slug = ? AND id = ?
        `,
      )
      .get(campaignSlug, combatantId) as CombatantRow | undefined) || null
  );
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

function readCombatResourceCounterRowsForCombatant(
  database: SqliteDatabase,
  campaignSlug: string,
  combatantId: number,
): CombatResourceCounterRow[] {
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
        WHERE e.campaign_slug = ? AND c.combatant_id = ?
        ORDER BY c.id ASC
      `,
    )
    .all(campaignSlug, combatantId) as CombatResourceCounterRow[];
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
  requestedCombatantId: number | null,
): CombatRuntimeState {
  if (!existsSync(dbPath)) {
    return emptyCombatRuntimeState();
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true, readonly: true });
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
    const characterStateBySlug = readCharacterStateSnapshots(database, campaignSlug);
    const combatants = combatantRows.map((row) =>
      presentCombatant({
        row,
        currentCombatantId,
        canManageCombat,
        characterRecordsBySlug,
        characterStateBySlug,
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
    const selectedPayload = selectCombatPayload(campaignSlug, tracker, canManageCombat, requestedCombatantId);
    const selectedPlayerSlug = asString(selectedPayload.selectedPlayerCharacter?.character_slug);
    const selectedPlayerRecord = selectedPlayerSlug ? characterRecordsBySlug.get(selectedPlayerSlug) : undefined;
    return {
      liveRevision: trackerRow ? Math.max(1, Number(trackerRow.revision || 1)) : COMBAT_READONLY_REVISION,
      tracker,
      existingCharacterSlugs: new Set(
        combatantRows.map((row) => String(row.character_slug || "")).filter(Boolean),
      ),
      ...selectedPayload,
      selectedPlayerCombatSections: selectedPlayerRecord
        ? buildCombatCharacterWorkspaceSections(selectedPlayerRecord)
        : [],
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

export function setCurrentCombatant(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  actorUserId: number,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeSetCurrent = database.transaction((): CombatMutationResult => {
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }

      const tracker = ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      resetCombatantTurnResources(
        database,
        campaignSlug,
        combatantId,
        actorUserId,
        now,
        "That combatant could not be found.",
      );

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET round_number = ?,
                current_combatant_id = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(Math.max(1, Number(tracker.round_number || 1)), combatantId, now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The current turn could not be updated.");
      }

      return { status: "ok" };
    });

    return writeSetCurrent();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function updateCombatantTurn(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const expectedRevision = parseOptionalCombatantRevision(payload.expected_combatant_revision);
  if (!expectedRevision.ok) {
    return { status: "validation_error", message: expectedRevision.message };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeTurnValue = database.transaction((): CombatMutationResult => {
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }

      const turnValue = parseCombatInteger(
        payload.turn_value,
        "Turn value",
        Number(combatant.turn_value || 0),
        null,
      );
      if (!turnValue.ok) {
        return { status: "validation_error", message: turnValue.message };
      }
      const initiativePriority = parseInitiativePriority(
        payload.initiative_priority,
        Number(combatant.initiative_priority || 1),
      );
      if (!initiativePriority.ok) {
        return { status: "validation_error", message: initiativePriority.message };
      }

      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      const parameters: unknown[] = [
        turnValue.value,
        initiativePriority.value,
        now,
        actorUserId,
        campaignSlug,
        combatantId,
      ];
      let expectedRevisionClause = "";
      if (expectedRevision.value !== null) {
        expectedRevisionClause = " AND revision = ?";
        parameters.push(expectedRevision.value);
      }
      const combatantUpdate = database
        .prepare(
          `
            UPDATE campaign_combatants
            SET turn_value = ?,
                initiative_priority = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `,
        )
        .run(...parameters);
      if (combatantUpdate.changes !== 1) {
        if (expectedRevision.value !== null) {
          return {
            status: "state_conflict",
            message: "This combatant changed in another combat view. Refresh and try again.",
          };
        }
        throw new CombatMutationConflictError("That turn value could not be saved.");
      }

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be updated.");
      }

      return { status: "ok" };
    });

    return writeTurnValue();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

function isCombatManager(role: FixtureCombatRole): boolean {
  return role === "dm" || role === "admin";
}

function actorOwnsCharacter(
  database: SqliteDatabase,
  campaignSlug: string,
  characterSlug: string,
  actorUserId: number,
): boolean {
  try {
    const row = database
      .prepare(
        `
          SELECT 1 AS allowed
          FROM character_assignments
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND user_id = ?
          LIMIT 1
        `,
      )
      .get(campaignSlug, characterSlug, actorUserId) as { allowed: number } | undefined;
    return Boolean(row?.allowed);
  } catch (error) {
    if (isNoSuchTableOrColumnError(error)) {
      return false;
    }
    throw error;
  }
}

function bumpCombatTrackerRevision(
  database: SqliteDatabase,
  campaignSlug: string,
  actorUserId: number | null,
  now: string,
): void {
  ensureCombatTrackerRow(database, campaignSlug, actorUserId);
  const trackerUpdate = database
    .prepare(
      `
        UPDATE campaign_combat_trackers
        SET revision = revision + 1,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ?
      `,
    )
    .run(now, actorUserId, campaignSlug);
  if (trackerUpdate.changes !== 1) {
    throw new CombatMutationConflictError("The combat tracker could not be updated.");
  }
}

function updateNpcCombatantVitals(
  database: SqliteDatabase,
  campaignSlug: string,
  combatant: CombatantRow,
  payload: Record<string, unknown>,
  actorUserId: number,
): CombatMutationResult {
  if (combatant.combatant_type !== "npc") {
    return { status: "validation_error", message: "Only NPC vitals can be edited directly here." };
  }

  const expectedRevision = parseOptionalCombatantRevision(payload.expected_combatant_revision);
  if (!expectedRevision.ok) {
    return { status: "validation_error", message: expectedRevision.message };
  }
  const maxHp = parseCombatInteger(payload.max_hp, "Max HP", Number(combatant.max_hp || 0), 0);
  if (!maxHp.ok) {
    return { status: "validation_error", message: maxHp.message };
  }
  const currentHp = parseCombatInteger(payload.current_hp, "Current HP", Number(combatant.current_hp || 0), 0);
  if (!currentHp.ok) {
    return { status: "validation_error", message: currentHp.message };
  }
  const tempHp = parseCombatInteger(payload.temp_hp, "Temp HP", Number(combatant.temp_hp || 0), 0);
  if (!tempHp.ok) {
    return { status: "validation_error", message: tempHp.message };
  }
  const movementTotal = parseCombatInteger(
    payload.movement_total,
    "Movement",
    Number(combatant.movement_total || 0),
    0,
  );
  if (!movementTotal.ok) {
    return { status: "validation_error", message: movementTotal.message };
  }
  if (currentHp.value > maxHp.value) {
    return { status: "validation_error", message: "Current HP cannot exceed max HP." };
  }

  ensureCombatTrackerRow(database, campaignSlug, actorUserId);
  const now = utcIsoTimestamp();
  const parameters: unknown[] = [
    currentHp.value,
    maxHp.value,
    tempHp.value,
    movementTotal.value,
    Math.min(Number(combatant.movement_remaining || 0), movementTotal.value),
    now,
    actorUserId,
    campaignSlug,
    combatant.id,
  ];
  let expectedRevisionClause = "";
  if (expectedRevision.value !== null) {
    expectedRevisionClause = " AND revision = ?";
    parameters.push(expectedRevision.value);
  }
  const combatantUpdate = database
    .prepare(
      `
        UPDATE campaign_combatants
        SET current_hp = ?,
            max_hp = ?,
            temp_hp = ?,
            movement_total = ?,
            movement_remaining = ?,
            revision = revision + 1,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
      `,
    )
    .run(...parameters);
  if (combatantUpdate.changes !== 1) {
    if (expectedRevision.value !== null) {
      return {
        status: "state_conflict",
        message: "This combatant changed in another combat view. Refresh and try again.",
      };
    }
    throw new CombatMutationConflictError("Those NPC vitals could not be saved.");
  }

  bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
  return { status: "ok" };
}

function updatePlayerCombatantVitals(
  database: SqliteDatabase,
  campaignSlug: string,
  combatant: CombatantRow,
  record: CampaignCharacterFileRecord,
  payload: Record<string, unknown>,
  actorUserId: number,
): CombatMutationResult {
  if (combatant.combatant_type !== "player_character" || !combatant.character_slug) {
    return { status: "validation_error", message: "Only player-character vitals can be edited here." };
  }

  const expectedRevision = parseExpectedCharacterStateRevision(payload.expected_revision);
  if (!expectedRevision.ok) {
    return { status: "validation_error", message: expectedRevision.message };
  }
  const snapshot = readCharacterStateSnapshot(database, campaignSlug, combatant.character_slug);
  if (!snapshot) {
    return {
      status: "validation_error",
      message: "That player character could not be loaded from the campaign data.",
    };
  }

  const vitals = asRecord(snapshot.state.vitals);
  const currentHp = parseCombatInteger(payload.current_hp, "Current HP", asNumber(vitals.current_hp), 0);
  if (!currentHp.ok) {
    return { status: "validation_error", message: currentHp.message };
  }
  const tempHp = parseCombatInteger(payload.temp_hp, "Temp HP", asNumber(vitals.temp_hp), 0);
  if (!tempHp.ok) {
    return { status: "validation_error", message: tempHp.message };
  }

  const definition = record.definition;
  const stats = asRecord(definition.stats);
  const maxHp = Math.max(0, asNumber(stats.max_hp));
  if (currentHp.value > maxHp) {
    return { status: "validation_error", message: "Current HP cannot exceed max HP." };
  }

  ensureCombatTrackerRow(database, campaignSlug, actorUserId);
  const now = utcIsoTimestamp();
  const nextState = {
    ...snapshot.state,
    vitals: {
      ...vitals,
      current_hp: currentHp.value,
      temp_hp: tempHp.value,
    },
  };
  const stateUpdate = database
    .prepare(
      `
        UPDATE character_state
        SET revision = revision + 1,
            state_json = ?,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ?
          AND character_slug = ?
          AND revision = ?
      `,
    )
    .run(JSON.stringify(nextState), now, actorUserId, campaignSlug, combatant.character_slug, expectedRevision.value);
  if (stateUpdate.changes !== 1) {
    return {
      status: "state_conflict",
      message: "This sheet changed in another session. Refresh and try again.",
    };
  }

  const movementTotal = parseMovementTotal(stats.speed);
  const combatantUpdate = database
    .prepare(
      `
        UPDATE campaign_combatants
        SET display_name = ?,
            initiative_bonus = ?,
            dexterity_modifier = ?,
            current_hp = ?,
            max_hp = ?,
            temp_hp = ?,
            movement_total = ?,
            movement_remaining = ?,
            revision = revision + 1,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ? AND id = ?
      `,
    )
    .run(
      asString(definition.name) || combatant.character_slug,
      asNumber(stats.initiative_bonus),
      extractDexterityModifier(stats),
      currentHp.value,
      maxHp,
      tempHp.value,
      movementTotal,
      Math.min(Number(combatant.movement_remaining || 0), movementTotal),
      now,
      actorUserId,
      campaignSlug,
      combatant.id,
    );
  if (combatantUpdate.changes !== 1) {
    throw new CombatMutationConflictError("That combat tracker row could not be updated.");
  }

  bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
  return { status: "ok" };
}

export async function updateCombatantVitals(
  config: ApiConfig,
  campaignSlug: string,
  combatantId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
  actorRole: FixtureCombatRole,
): Promise<CombatMutationResult> {
  if (!existsSync(config.dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const characterRecords = (await listCampaignContentCharacters(config, campaignSlug)) || [];
  const characterRecordsBySlug = characterRecordMap(characterRecords);
  const database = openSqliteDatabase(config.dbPath, { fileMustExist: true });
  try {
    const writeVitals = database.transaction((): CombatMutationResult => {
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }

      const manager = isCombatManager(actorRole);
      const characterSlug = String(combatant.character_slug || "");
      const isPlayerCharacter = combatant.combatant_type === "player_character" && Boolean(characterSlug);
      if (isPlayerCharacter) {
        if (!manager && !actorOwnsCharacter(database, campaignSlug, characterSlug, actorUserId)) {
          return { status: "forbidden", message: "You do not have permission to edit this combatant." };
        }
        const record = characterRecordsBySlug.get(characterSlug);
        if (!record) {
          return {
            status: "validation_error",
            message: "That player character could not be loaded from the campaign data.",
          };
        }
        return updatePlayerCombatantVitals(database, campaignSlug, combatant, record, payload, actorUserId);
      }

      if (!manager) {
        return { status: "forbidden", message: "You do not have permission to edit this combatant." };
      }
      return updateNpcCombatantVitals(database, campaignSlug, combatant, payload, actorUserId);
    });

    return writeVitals();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function updateCombatantResources(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeResources = database.transaction((): CombatMutationResult => {
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }

      const manager = isCombatManager(actorRole);
      const characterSlug = String(combatant.character_slug || "");
      const isPlayerCharacter = combatant.combatant_type === "player_character" && Boolean(characterSlug);
      if (isPlayerCharacter) {
        if (!manager && !actorOwnsCharacter(database, campaignSlug, characterSlug, actorUserId)) {
          return { status: "forbidden", message: "You do not have permission to edit this combatant." };
        }
      } else if (!manager) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }

      const expectedRevision = parseOptionalCombatantRevision(payload.expected_combatant_revision);
      if (!expectedRevision.ok) {
        return { status: "validation_error", message: expectedRevision.message };
      }
      const hasAction = parseCombatBoolean(payload, "has_action", "has_action", asBoolean(combatant.has_action));
      if (!hasAction.ok) {
        return { status: "validation_error", message: hasAction.message };
      }
      const hasBonusAction = parseCombatBoolean(
        payload,
        "has_bonus_action",
        "has_bonus_action",
        asBoolean(combatant.has_bonus_action),
      );
      if (!hasBonusAction.ok) {
        return { status: "validation_error", message: hasBonusAction.message };
      }
      const hasReaction = parseCombatBoolean(payload, "has_reaction", "has_reaction", asBoolean(combatant.has_reaction));
      if (!hasReaction.ok) {
        return { status: "validation_error", message: hasReaction.message };
      }
      const movementRemaining = parseCombatInteger(
        payload.movement_remaining,
        "Remaining movement",
        Number(combatant.movement_remaining || 0),
        0,
      );
      if (!movementRemaining.ok) {
        return { status: "validation_error", message: movementRemaining.message };
      }
      if (movementRemaining.value > Number(combatant.movement_total || 0)) {
        return { status: "validation_error", message: "Remaining movement cannot exceed total movement." };
      }

      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      const parameters: unknown[] = [
        hasAction.value ? 1 : 0,
        hasBonusAction.value ? 1 : 0,
        hasReaction.value ? 1 : 0,
        movementRemaining.value,
        now,
        actorUserId,
        campaignSlug,
        combatantId,
      ];
      let expectedRevisionClause = "";
      if (expectedRevision.value !== null) {
        expectedRevisionClause = " AND revision = ?";
        parameters.push(expectedRevision.value);
      }
      const combatantUpdate = database
        .prepare(
          `
            UPDATE campaign_combatants
            SET has_action = ?,
                has_bonus_action = ?,
                has_reaction = ?,
                movement_remaining = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `,
        )
        .run(...parameters);
      if (combatantUpdate.changes !== 1) {
        if (expectedRevision.value !== null) {
          return {
            status: "state_conflict",
            message: "This combatant changed in another combat view. Refresh and try again.",
          };
        }
        throw new CombatMutationConflictError("Those combat resources could not be saved.");
      }

      bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
      return { status: "ok" };
    });

    return writeResources();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function updateCombatantNpcResources(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeNpcResources = database.transaction((): CombatMutationResult => {
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }
      if (!isCombatManager(actorRole)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }
      if (combatant.combatant_type !== "npc") {
        return { status: "validation_error", message: "Only NPC source resources can be edited here." };
      }

      const expectedRevision = parseOptionalCombatantRevision(payload.expected_combatant_revision);
      if (!expectedRevision.ok) {
        return { status: "validation_error", message: expectedRevision.message };
      }

      const counterValues = payload.counters;
      if (!Array.isArray(counterValues)) {
        return { status: "validation_error", message: "NPC resource counters must be sent as a list." };
      }

      const existingCounters = readCombatResourceCounterRowsForCombatant(database, campaignSlug, combatantId);
      const countersByKey = new Map(existingCounters.map((counter) => [counter.resource_key, counter]));
      if (countersByKey.size === 0) {
        return {
          status: "validation_error",
          message: "This NPC has no supported source-backed resource counters.",
        };
      }

      const valuesByKey = new Map<string, number>();
      for (let index = 0; index < counterValues.length; index += 1) {
        const counterValue = counterValues[index];
        if (typeof counterValue !== "object" || counterValue === null || Array.isArray(counterValue)) {
          return { status: "validation_error", message: `NPC resource row ${index + 1} must be an object.` };
        }

        const counterPayload = counterValue as Record<string, unknown>;
        const resourceKey = payloadString(counterPayload.resource_key);
        const counter = countersByKey.get(resourceKey);
        if (!resourceKey || !counter) {
          return { status: "validation_error", message: "Choose a valid NPC resource counter." };
        }

        const currentValue = parseCombatInteger(
          counterPayload.current_value,
          `${counter.label} current value`,
          Number(counter.current_value || 0),
          0,
        );
        if (!currentValue.ok) {
          return { status: "validation_error", message: currentValue.message };
        }
        if (currentValue.value > Number(counter.max_value || 0)) {
          return { status: "validation_error", message: `${counter.label} cannot exceed ${counter.max_value}.` };
        }
        valuesByKey.set(resourceKey, currentValue.value);
      }

      if (valuesByKey.size === 0) {
        return { status: "validation_error", message: "Choose at least one NPC resource counter to update." };
      }

      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      const combatantParameters: unknown[] = [now, actorUserId, campaignSlug, combatantId];
      let expectedRevisionClause = "";
      if (expectedRevision.value !== null) {
        expectedRevisionClause = " AND revision = ?";
        combatantParameters.push(expectedRevision.value);
      }

      const combatantUpdate = database
        .prepare(
          `
            UPDATE campaign_combatants
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `,
        )
        .run(...combatantParameters);
      if (combatantUpdate.changes !== 1) {
        if (expectedRevision.value !== null) {
          return {
            status: "state_conflict",
            message: "This combatant changed in another combat view. Refresh and try again.",
          };
        }
        throw new CombatMutationConflictError("Those NPC resources could not be saved.");
      }

      const counterUpdate = database.prepare(
        `
          UPDATE campaign_combatant_resource_counters
          SET current_value = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE combatant_id = ? AND resource_key = ?
        `,
      );
      for (const [resourceKey, currentValue] of valuesByKey.entries()) {
        const update = counterUpdate.run(currentValue, now, actorUserId, combatantId, resourceKey);
        if (update.changes !== 1) {
          throw new CombatMutationConflictError("Those NPC resources could not be saved.");
        }
      }

      bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
      return { status: "ok" };
    });

    return writeNpcResources();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function updateCombatantPlayerDetailVisibility(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeVisibility = database.transaction((): CombatMutationResult => {
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }
      if (!isCombatManager(actorRole)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }
      if (combatant.combatant_type !== "npc") {
        return {
          status: "validation_error",
          message: "Only NPC combatants can toggle player-facing detail visibility.",
        };
      }
      if (!Object.hasOwn(payload, "player_detail_visible")) {
        return { status: "validation_error", message: "player_detail_visible must be true or false." };
      }

      const expectedRevision = parseOptionalCombatantRevision(payload.expected_combatant_revision);
      if (!expectedRevision.ok) {
        return { status: "validation_error", message: expectedRevision.message };
      }
      const playerDetailVisible = parseCombatBoolean(
        payload,
        "player_detail_visible",
        "player_detail_visible",
        asBoolean(combatant.player_detail_visible),
      );
      if (!playerDetailVisible.ok) {
        return { status: "validation_error", message: playerDetailVisible.message };
      }

      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      const parameters: unknown[] = [
        playerDetailVisible.value ? 1 : 0,
        now,
        actorUserId,
        campaignSlug,
        combatantId,
      ];
      let expectedRevisionClause = "";
      if (expectedRevision.value !== null) {
        expectedRevisionClause = " AND revision = ?";
        parameters.push(expectedRevision.value);
      }
      const combatantUpdate = database
        .prepare(
          `
            UPDATE campaign_combatants
            SET player_detail_visible = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `,
        )
        .run(...parameters);
      if (combatantUpdate.changes !== 1) {
        if (expectedRevision.value !== null) {
          return {
            status: "state_conflict",
            message: "This combatant changed in another combat view. Refresh and try again.",
          };
        }
        throw new CombatMutationConflictError("That NPC visibility setting could not be saved.");
      }

      bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
      return { status: "ok" };
    });

    return writeVisibility();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function addCombatCondition(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeCondition = database.transaction((): CombatMutationResult => {
      if (!isCombatManager(actorRole)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }
      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }

      const name = payloadString(payload.name);
      if (!name) {
        return { status: "validation_error", message: "Condition name is required." };
      }
      if (name.length > 80) {
        return { status: "validation_error", message: "Condition names must stay under 80 characters." };
      }

      const durationText = payloadString(payload.duration_text);
      if (durationText.length > 120) {
        return {
          status: "validation_error",
          message: "Condition duration text must stay under 120 characters.",
        };
      }

      const now = utcIsoTimestamp();
      database
        .prepare(
          `
            INSERT INTO campaign_combat_conditions (
              combatant_id,
              name,
              duration_text,
              created_at,
              created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?)
          `,
        )
        .run(combatant.id, name, durationText, now, actorUserId);
      bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
      return { status: "ok" };
    });

    return writeCondition();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function updateCombatCondition(
  dbPath: string,
  campaignSlug: string,
  conditionId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeCondition = database.transaction((): CombatMutationResult => {
      if (!isCombatManager(actorRole)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }

      const condition =
        (database
          .prepare(
            `
              SELECT c.id
              FROM campaign_combat_conditions AS c
              JOIN campaign_combatants AS e ON e.id = c.combatant_id
              WHERE e.campaign_slug = ? AND c.id = ?
            `,
          )
          .get(campaignSlug, conditionId) as { id: number } | undefined) || null;
      if (!condition) {
        return { status: "validation_error", message: "That condition could not be found." };
      }

      const name = payloadString(payload.name);
      if (!name) {
        return { status: "validation_error", message: "Condition name is required." };
      }
      if (name.length > 80) {
        return { status: "validation_error", message: "Condition names must stay under 80 characters." };
      }

      const durationText = payloadString(payload.duration_text);
      if (durationText.length > 120) {
        return {
          status: "validation_error",
          message: "Condition duration text must stay under 120 characters.",
        };
      }

      const updateResult = database
        .prepare(
          `
            UPDATE campaign_combat_conditions
            SET name = ?,
                duration_text = ?
            WHERE id = ?
          `,
        )
        .run(name, durationText, conditionId);
      if (updateResult.changes !== 1) {
        throw new CombatMutationConflictError("That condition could not be found.");
      }

      bumpCombatTrackerRevision(database, campaignSlug, actorUserId, utcIsoTimestamp());
      return { status: "ok" };
    });

    return writeCondition();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function deleteCombatCondition(
  dbPath: string,
  campaignSlug: string,
  conditionId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const deleteCondition = database.transaction((): CombatMutationResult => {
      if (!isCombatManager(actorRole)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }

      const condition =
        (database
          .prepare(
            `
              SELECT c.id
              FROM campaign_combat_conditions AS c
              JOIN campaign_combatants AS e ON e.id = c.combatant_id
              WHERE e.campaign_slug = ? AND c.id = ?
            `,
          )
          .get(campaignSlug, conditionId) as { id: number } | undefined) || null;
      if (!condition) {
        return { status: "validation_error", message: "That condition could not be found." };
      }

      const deleteResult = database
        .prepare("DELETE FROM campaign_combat_conditions WHERE id = ?")
        .run(conditionId);
      if (deleteResult.changes !== 1) {
        throw new CombatMutationConflictError("That condition could not be found.");
      }

      bumpCombatTrackerRevision(database, campaignSlug, null, utcIsoTimestamp());
      return { status: "ok" };
    });

    return deleteCondition();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function deleteCombatant(
  dbPath: string,
  campaignSlug: string,
  combatantId: number,
  actorRole: FixtureCombatRole,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const deleteCombatantRow = database.transaction((): CombatMutationResult => {
      if (!isCombatManager(actorRole)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
      }

      const combatant = readCombatantRow(database, campaignSlug, combatantId);
      if (!combatant) {
        return { status: "validation_error", message: "That combatant could not be found." };
      }

      database.prepare("DELETE FROM campaign_combat_conditions WHERE combatant_id = ?").run(combatantId);
      database.prepare("DELETE FROM campaign_combatant_resource_counters WHERE combatant_id = ?").run(combatantId);
      database.prepare("DELETE FROM campaign_combatant_resource_notes WHERE combatant_id = ?").run(combatantId);

      const deleteResult = database
        .prepare("DELETE FROM campaign_combatants WHERE campaign_slug = ? AND id = ?")
        .run(campaignSlug, combatantId);
      if (deleteResult.changes !== 1) {
        throw new CombatMutationConflictError("That combatant could not be found.");
      }

      ensureCombatTrackerRow(database, campaignSlug, null);
      database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET current_combatant_id = NULL
            WHERE campaign_slug = ? AND current_combatant_id = ?
          `,
        )
        .run(campaignSlug, combatantId);
      bumpCombatTrackerRevision(database, campaignSlug, null, utcIsoTimestamp());
      return { status: "ok" };
    });

    return deleteCombatantRow();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function advanceCombatTurn(dbPath: string, campaignSlug: string, actorUserId: number): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeAdvanceTurn = database.transaction((): CombatMutationResult => {
      const tracker = ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const combatants = readCombatantRows(database, campaignSlug);
      if (combatants.length === 0) {
        return { status: "validation_error", message: "Add combatants before advancing turn order." };
      }

      const currentCombatantId =
        tracker.current_combatant_id === null || tracker.current_combatant_id === undefined
          ? null
          : Number(tracker.current_combatant_id);
      const currentIndex = combatants.findIndex((combatant) => Number(combatant.id) === currentCombatantId);
      const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % combatants.length;
      const nextRound =
        currentIndex < 0
          ? Math.max(1, Number(tracker.round_number || 1))
          : nextIndex === 0
            ? Number(tracker.round_number || 1) + 1
            : Number(tracker.round_number || 1);
      const nextCombatant = combatants[nextIndex];
      if (!nextCombatant) {
        return { status: "validation_error", message: "Add combatants before advancing turn order." };
      }

      const now = utcIsoTimestamp();
      resetCombatantTurnResources(
        database,
        campaignSlug,
        Number(nextCombatant.id),
        actorUserId,
        now,
        "The turn order could not be advanced.",
      );

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET round_number = ?,
                current_combatant_id = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(Math.max(1, nextRound), Number(nextCombatant.id), now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The turn order could not be advanced.");
      }

      return { status: "ok" };
    });

    return writeAdvanceTurn();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function clearCombatTracker(dbPath: string, campaignSlug: string, actorUserId: number): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeClearTracker = database.transaction((): CombatMutationResult => {
      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      database
        .prepare(
          `
            DELETE FROM campaign_combat_conditions
            WHERE combatant_id IN (
              SELECT id FROM campaign_combatants WHERE campaign_slug = ?
            )
          `,
        )
        .run(campaignSlug);
      database
        .prepare(
          `
            DELETE FROM campaign_combatant_resource_counters
            WHERE combatant_id IN (
              SELECT id FROM campaign_combatants WHERE campaign_slug = ?
            )
          `,
        )
        .run(campaignSlug);
      database
        .prepare(
          `
            DELETE FROM campaign_combatant_resource_notes
            WHERE combatant_id IN (
              SELECT id FROM campaign_combatants WHERE campaign_slug = ?
            )
          `,
        )
        .run(campaignSlug);
      database.prepare("DELETE FROM campaign_combatants WHERE campaign_slug = ?").run(campaignSlug);

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET round_number = 1,
                current_combatant_id = NULL,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be cleared.");
      }

      return { status: "ok" };
    });

    return writeClearTracker();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export async function addPlayerCombatant(
  config: ApiConfig,
  campaignSlug: string,
  payload: Record<string, unknown>,
  actorUserId: number,
): Promise<CombatMutationResult> {
  if (!existsSync(config.dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const characterSlug = payloadString(payload.character_slug);
  const characterRecords = (await listCampaignContentCharacters(config, campaignSlug)) || [];
  const record = characterRecords.find(
    (candidate) =>
      candidate.character_slug === characterSlug &&
      asString(candidate.definition.status) === "active",
  );
  if (!record) {
    return {
      status: "validation_error",
      message: "Choose a valid player character to add to the tracker.",
    };
  }

  persistCharacterStateForDefinition(config, record.definition);

  const database = openSqliteDatabase(config.dbPath, { fileMustExist: true });
  try {
    const snapshot = buildPlayerCharacterSnapshot(database, campaignSlug, record);
    const turnValue = parseCombatInteger(payload.turn_value, "Turn value", snapshot.initiativeBonus, null);
    if (!turnValue.ok) {
      return { status: "validation_error", message: turnValue.message };
    }
    const initiativePriority = parseInitiativePriority(payload.initiative_priority, 1);
    if (!initiativePriority.ok) {
      return { status: "validation_error", message: initiativePriority.message };
    }

    const writeAddPlayer = database.transaction((): CombatMutationResult => {
      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const existingCombatant = readCombatantRows(database, campaignSlug).find(
        (combatant) => combatant.character_slug === record.character_slug,
      );
      if (existingCombatant) {
        return {
          status: "validation_error",
          message: "That player character is already in the combat tracker.",
        };
      }

      const now = utcIsoTimestamp();
      try {
        database
          .prepare(
            `
              INSERT INTO campaign_combatants (
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
                revision,
                created_at,
                updated_at,
                created_by_user_id,
                updated_by_user_id
              )
              VALUES (?, 'player_character', ?, 1, 'character', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 1, ?, ?, ?, ?)
            `,
          )
          .run(
            campaignSlug,
            record.character_slug,
            record.character_slug,
            asString(record.definition.name) || record.character_slug,
            turnValue.value,
            snapshot.initiativeBonus,
            snapshot.dexterityModifier,
            initiativePriority.value,
            snapshot.currentHp,
            snapshot.maxHp,
            snapshot.tempHp,
            snapshot.movementTotal,
            snapshot.movementTotal,
            now,
            now,
            actorUserId,
            actorUserId,
          );
      } catch (error) {
        if (error instanceof Error && error.message.includes("UNIQUE constraint failed")) {
          throw new CombatMutationConflictError("That player character is already in the combat tracker.");
        }
        throw error;
      }

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be updated.");
      }

      return { status: "ok" };
    });

    return writeAddPlayer();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function addNpcCombatant(
  dbPath: string,
  campaignSlug: string,
  payload: Record<string, unknown>,
  actorUserId: number,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const displayName = payloadString(payload.display_name);
  if (!displayName) {
    return { status: "validation_error", message: "NPC name is required." };
  }

  const turnValue = parseCombatInteger(payload.turn_value, "Turn value", 0, null);
  if (!turnValue.ok) {
    return { status: "validation_error", message: turnValue.message };
  }
  const initiativeBonus = parseCombatInteger(payload.initiative_bonus, "Initiative bonus", 0, null);
  if (!initiativeBonus.ok) {
    return { status: "validation_error", message: initiativeBonus.message };
  }
  const dexterityModifier = parseCombatInteger(
    payload.dexterity_modifier,
    "Dexterity modifier",
    initiativeBonus.value,
    null,
  );
  if (!dexterityModifier.ok) {
    return { status: "validation_error", message: dexterityModifier.message };
  }
  const initiativePriority = parseInitiativePriority(payload.initiative_priority, 1);
  if (!initiativePriority.ok) {
    return { status: "validation_error", message: initiativePriority.message };
  }
  const maxHp = parseCombatInteger(payload.max_hp, "Max HP", null, 0);
  if (!maxHp.ok) {
    return { status: "validation_error", message: maxHp.message };
  }
  const currentHp = parseCombatInteger(payload.current_hp, "Current HP", maxHp.value, 0);
  if (!currentHp.ok) {
    return { status: "validation_error", message: currentHp.message };
  }
  const tempHp = parseCombatInteger(payload.temp_hp, "Temp HP", 0, 0);
  if (!tempHp.ok) {
    return { status: "validation_error", message: tempHp.message };
  }
  const movementTotal = parseCombatInteger(payload.movement_total, "Movement", 0, 0);
  if (!movementTotal.ok) {
    return { status: "validation_error", message: movementTotal.message };
  }
  if (currentHp.value > maxHp.value) {
    return { status: "validation_error", message: "Current HP cannot exceed max HP." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const writeAddNpc = database.transaction((): CombatMutationResult => {
      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      try {
        database
          .prepare(
            `
              INSERT INTO campaign_combatants (
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
                revision,
                created_at,
                updated_at,
                created_by_user_id,
                updated_by_user_id
              )
              VALUES (?, 'npc', NULL, 0, 'manual_npc', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 1, ?, ?, ?, ?)
            `,
          )
          .run(
            campaignSlug,
            displayName,
            turnValue.value,
            initiativeBonus.value,
            dexterityModifier.value,
            initiativePriority.value,
            currentHp.value,
            maxHp.value,
            tempHp.value,
            movementTotal.value,
            movementTotal.value,
            now,
            now,
            actorUserId,
            actorUserId,
          );
      } catch (error) {
        if (error instanceof Error && error.message.includes("constraint failed")) {
          throw new CombatMutationConflictError("Unable to create combatant.");
        }
        throw error;
      }

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be updated.");
      }

      return { status: "ok" };
    });

    return writeAddNpc();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

function insertNpcResourceSeeds(
  database: SqliteDatabase,
  combatantId: number,
  counterSeeds: NpcResourceCounterSeed[],
  noteSeeds: NpcResourceNoteSeed[],
  actorUserId: number,
  now: string,
): void {
  const counterInsert = database.prepare(
    `
      INSERT INTO campaign_combatant_resource_counters (
        combatant_id,
        resource_key,
        label,
        current_value,
        max_value,
        reset_label,
        source_label,
        created_at,
        updated_at,
        created_by_user_id,
        updated_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  );
  for (const seed of counterSeeds) {
    counterInsert.run(
      combatantId,
      seed.resourceKey,
      seed.label,
      seed.currentValue,
      seed.maxValue,
      seed.resetLabel,
      seed.sourceLabel,
      now,
      now,
      actorUserId,
      actorUserId,
    );
  }

  const noteInsert = database.prepare(
    `
      INSERT INTO campaign_combatant_resource_notes (
        combatant_id,
        label,
        note,
        source_label,
        created_at,
        created_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?)
    `,
  );
  for (const seed of noteSeeds) {
    noteInsert.run(combatantId, seed.label, seed.note, seed.sourceLabel, now, actorUserId);
  }
}

export function addStatblockCombatant(
  dbPath: string,
  campaignSlug: string,
  payload: Record<string, unknown>,
  actorUserId: number,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const statblockId = parseWholeInteger(payloadString(payload.statblock_id));
  if (statblockId === null || statblockId < 1) {
    return { status: "validation_error", message: "Choose a valid DM Content statblock to add." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const statblock = readDmStatblockDetailRow(database, campaignSlug, statblockId);
    if (!statblock) {
      return { status: "validation_error", message: "Choose a valid DM Content statblock to add." };
    }

    const initiativeBonus = Number(statblock.initiative_bonus || 0);
    const turnRaw =
      payload.turn_value === null || payload.turn_value === undefined || payloadString(payload.turn_value) === ""
        ? initiativeBonus
        : payload.turn_value;
    const turnValue = parseCombatInteger(turnRaw, "Turn value", initiativeBonus, null);
    if (!turnValue.ok) {
      return { status: "validation_error", message: turnValue.message };
    }
    const initiativePriority = parseInitiativePriority(payload.initiative_priority, 1);
    if (!initiativePriority.ok) {
      return { status: "validation_error", message: initiativePriority.message };
    }

    const displayName = payloadString(payload.display_name) || String(statblock.title || "").trim();
    if (!displayName) {
      return { status: "validation_error", message: "NPC name is required." };
    }

    const dexterityModifier = extractStatblockDexterityModifier(String(statblock.body_markdown || ""), initiativeBonus);
    const maxHp = Math.max(0, Number(statblock.max_hp || 0));
    const movementTotal = Math.max(0, Number(statblock.movement_total || 0));
    const resourceSeeds = buildNpcResourceSeedsFromMarkdown(String(statblock.body_markdown || ""), "DM Content");

    const writeAddStatblock = database.transaction((): CombatMutationResult => {
      ensureCombatTrackerRow(database, campaignSlug, actorUserId);
      const now = utcIsoTimestamp();
      let combatantId = 0;
      try {
        const insertResult = database
          .prepare(
            `
              INSERT INTO campaign_combatants (
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
                revision,
                created_at,
                updated_at,
                created_by_user_id,
                updated_by_user_id
              )
              VALUES (?, 'npc', NULL, 0, 'dm_statblock', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1, 1, 1, 1, ?, ?, ?, ?)
            `,
          )
          .run(
            campaignSlug,
            String(statblock.id),
            displayName,
            turnValue.value,
            initiativeBonus,
            dexterityModifier,
            initiativePriority.value,
            maxHp,
            maxHp,
            movementTotal,
            movementTotal,
            now,
            now,
            actorUserId,
            actorUserId,
          );
        combatantId = Number(insertResult.lastInsertRowid);
        insertNpcResourceSeeds(database, combatantId, resourceSeeds.counters, resourceSeeds.notes, actorUserId, now);
      } catch (error) {
        if (error instanceof Error && error.message.includes("constraint failed")) {
          throw new CombatMutationConflictError("Unable to create combatant.");
        }
        throw error;
      }

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(now, actorUserId, campaignSlug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be updated.");
      }

      return { status: "ok" };
    });

    return writeAddStatblock();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function addSystemsMonsterCombatant(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  payload: Record<string, unknown>,
  actorUserId: number,
): CombatMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Combat storage is not initialized." };
  }

  const entryKey = payloadString(payload.entry_key);
  const librarySlug = campaign.systems_library_slug || "";
  if (!entryKey || !librarySlug) {
    return { status: "validation_error", message: "Choose a valid Systems monster to add." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const entry = readSystemsMonsterEntryRow(database, librarySlug, entryKey);
    const sourceSeeds = parseCampaignSourceSeeds(campaignConfig);
    if (
      !entry ||
      String(entry.entry_type || "").trim().toLowerCase() !== "monster" ||
      !isSystemsEntryEnabledForCampaign(database, campaign.slug, librarySlug, entry, sourceSeeds)
    ) {
      return { status: "validation_error", message: "Choose a valid Systems monster to add." };
    }

    const metadata = parseJsonObject(entry.metadata_json);
    const abilities = asRecord(metadata.abilities);
    const dexterityScore = coerceMonsterInteger(abilities.dex, 10);
    const initiativeBonus = Math.floor((dexterityScore - 10) / 2);
    const maxHp = Math.max(0, extractMonsterHpAverage(metadata.hp));
    const movementTotal = Math.max(0, extractMaxDistance(metadata.speed));
    const turnRaw =
      payload.turn_value === null || payload.turn_value === undefined || payloadString(payload.turn_value) === ""
        ? initiativeBonus
        : payload.turn_value;
    const turnValue = parseCombatInteger(turnRaw, "Turn value", initiativeBonus, null);
    if (!turnValue.ok) {
      return { status: "validation_error", message: turnValue.message };
    }
    const initiativePriority = parseInitiativePriority(payload.initiative_priority, 1);
    if (!initiativePriority.ok) {
      return { status: "validation_error", message: initiativePriority.message };
    }

    const displayName = payloadString(payload.display_name) || String(entry.title || "").trim();
    if (!displayName) {
      return { status: "validation_error", message: "NPC name is required." };
    }

    const sourceLabel = `Systems ${String(entry.source_id || "").trim()}`.trim() || "Systems";
    const resourceSeeds = buildNpcResourceSeedsFromStructuredValue(parseJsonUnknown(entry.body_json), sourceLabel);

    const writeAddSystemsMonster = database.transaction((): CombatMutationResult => {
      ensureCombatTrackerRow(database, campaign.slug, actorUserId);
      const now = utcIsoTimestamp();
      try {
        const insertResult = database
          .prepare(
            `
              INSERT INTO campaign_combatants (
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
                revision,
                created_at,
                updated_at,
                created_by_user_id,
                updated_by_user_id
              )
              VALUES (?, 'npc', NULL, 0, 'systems_monster', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1, 1, 1, 1, ?, ?, ?, ?)
            `,
          )
          .run(
            campaign.slug,
            entry.entry_key,
            displayName,
            turnValue.value,
            initiativeBonus,
            initiativeBonus,
            initiativePriority.value,
            maxHp,
            maxHp,
            movementTotal,
            movementTotal,
            now,
            now,
            actorUserId,
            actorUserId,
          );
        insertNpcResourceSeeds(
          database,
          Number(insertResult.lastInsertRowid),
          resourceSeeds.counters,
          resourceSeeds.notes,
          actorUserId,
          now,
        );
      } catch (error) {
        if (error instanceof Error && error.message.includes("constraint failed")) {
          throw new CombatMutationConflictError("Unable to create combatant.");
        }
        throw error;
      }

      const trackerUpdate = database
        .prepare(
          `
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `,
        )
        .run(now, actorUserId, campaign.slug);
      if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be updated.");
      }

      return { status: "ok" };
    });

    return writeAddSystemsMonster();
  } catch (error) {
    if (error instanceof CombatMutationConflictError) {
      return { status: "validation_error", message: error.message };
    }
    if (isNoSuchTableOrColumnError(error)) {
      return { status: "validation_error", message: "Combat storage is not initialized." };
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

  const database = openSqliteDatabase(dbPath, { fileMustExist: true, readonly: true });
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
  options: CombatReadOnlyOptions = {},
): Promise<CombatReadOnlyPayload> {
  const canManageCombat = role === "dm" || role === "admin";
  const canAccessScopedPlayerTools = role === "player" || canManageCombat;
  const canAccessDmContent = canManageCombat;
  const combatSystemSupported = supportsCombatTracker(campaign.system);
  const characterRecords =
    combatSystemSupported ? (await listCampaignContentCharacters(config, campaign.slug)) || [] : [];
  const requestedCombatantId = canManageCombat ? options.requestedCombatantId ?? null : null;
  const combatRuntime = combatSystemSupported
    ? loadCombatRuntimeState(config.dbPath, campaign.slug, canManageCombat, characterRecords, requestedCombatantId)
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
    selected_player_combat_sections: combatRuntime.selectedPlayerCombatSections,
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
