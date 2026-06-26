import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { ApiConfig } from "../config.js";

type SqliteDatabase = InstanceType<typeof Database>;

interface CharacterStateRow {
  revision: number;
  state_json: string;
}

export interface CharacterStatePersistenceResult {
  stateCreated: boolean;
}

export interface DeletedCharacterPersistenceResult {
  deletedState: boolean;
  deletedAssignment: boolean;
}

export type CharacterSessionVitalsUpdateResult =
  | { status: "ok"; revision: number; state: Record<string, unknown>; updatedAt: string }
  | { status: "not_found" }
  | { status: "state_conflict"; message: string }
  | { status: "validation_error"; message: string };

export type CharacterSessionResourceUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionSpellSlotsUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionInventoryUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionXianxiaActiveStateUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionCurrencyUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionNotesUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionPersonalUpdateResult = CharacterSessionVitalsUpdateResult;

export type CharacterSessionFeatureStateUpdateResult = CharacterSessionVitalsUpdateResult;

export interface CharacterRestChangePayload {
  label: string;
  from_value: string;
  to_value: string;
}

export interface CharacterRestPreviewPayload {
  rest_type: "short" | "long";
  label: string;
  changes: CharacterRestChangePayload[];
  adjustments: Record<string, unknown>;
}

export type CharacterRestPreviewResult =
  | { status: "ok"; preview: CharacterRestPreviewPayload }
  | { status: "validation_error"; message: string };

export type CharacterSessionRestApplyResult = CharacterSessionVitalsUpdateResult;

const XIANXIA_SYSTEM_CODE = "xianxia";
const DND_CURRENCY_KEYS = ["cp", "sp", "ep", "gp", "pp"] as const;
const XIANXIA_ENERGY_KEYS = ["jing", "qi", "shen"] as const;
const XIANXIA_ENERGY_LABELS: Record<(typeof XIANXIA_ENERGY_KEYS)[number], string> = {
  jing: "Jing",
  qi: "Qi",
  shen: "Shen",
};
const XIANXIA_CURRENCY_KEYS = ["coin", "supply", "spirit_stones"] as const;
const VALID_HIT_DIE_FACES = new Set([4, 6, 8, 10, 12]);
const CHARACTER_STATE_CONFLICT_MESSAGE = "This sheet changed in another session. Refresh and try again.";
const STANDARD_DND_CLASS_HIT_DICE: Record<string, number> = {
  artificer: 8,
  barbarian: 12,
  bard: 8,
  cleric: 8,
  druid: 8,
  fighter: 10,
  monk: 8,
  paladin: 10,
  ranger: 10,
  rogue: 8,
  sorcerer: 6,
  warlock: 8,
  wizard: 6,
};

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

function normalizeSystemKey(value: unknown): string {
  return asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value.trim());
    if (Number.isFinite(parsed)) {
      return Math.trunc(parsed);
    }
  }
  return fallback;
}

function hasSubmittedValue(value: unknown): boolean {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function parseOptionalWholeNumber(value: unknown, fieldLabel: string): number | null {
  if (!hasSubmittedValue(value)) {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }
  const rawValue = String(value).trim();
  if (!/^[+-]?\d+$/.test(rawValue)) {
    throw new Error(`${fieldLabel} must be an integer.`);
  }
  return Number.parseInt(rawValue, 10);
}

function parseRequiredWholeNumber(value: unknown, fieldLabel: string): number {
  const parsed = parseOptionalWholeNumber(value, fieldLabel);
  if (parsed === null) {
    throw new Error(`${fieldLabel} is required.`);
  }
  return parsed;
}

function nonNegativeInt(value: unknown, fallback = 0): number {
  return Math.max(0, asInt(value, fallback));
}

function clampInt(value: unknown, fallback = 0, maximum?: number): number {
  const normalized = nonNegativeInt(value, fallback);
  return maximum === undefined ? normalized : Math.min(normalized, Math.max(0, maximum));
}

function utcIsoTimestamp(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

function openDatabase(config: ApiConfig): SqliteDatabase | null {
  if (!config.dbPath || !existsSync(config.dbPath)) {
    return null;
  }
  return new Database(config.dbPath);
}

function tableExists(database: SqliteDatabase, tableName: string): boolean {
  const row = database
    .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?")
    .get(tableName) as { name?: string } | undefined;
  return Boolean(row?.name);
}

function parseStateJson(rawJson: string): Record<string, unknown> {
  try {
    return asRecord(JSON.parse(rawJson));
  } catch {
    return {};
  }
}

function readCharacterState(
  database: SqliteDatabase,
  campaignSlug: string,
  characterSlug: string,
): { revision: number; state: Record<string, unknown> } | null {
  const row = database
    .prepare(
      `
        SELECT revision, state_json
        FROM character_state
        WHERE campaign_slug = ?
          AND character_slug = ?
      `,
    )
    .get(campaignSlug, characterSlug) as CharacterStateRow | undefined;
  if (!row) {
    return null;
  }
  return {
    revision: Number(row.revision) || 0,
    state: parseStateJson(row.state_json),
  };
}

function characterIdentity(definition: Record<string, unknown>): { campaignSlug: string; characterSlug: string } | null {
  const campaignSlug = asString(definition.campaign_slug);
  const characterSlug = asString(definition.character_slug);
  return campaignSlug && characterSlug ? { campaignSlug, characterSlug } : null;
}

function definitionXianxia(definition: Record<string, unknown>): Record<string, unknown> {
  return asRecord(definition.xianxia);
}

function definitionStats(definition: Record<string, unknown>): Record<string, unknown> {
  return asRecord(definition.stats);
}

function definitionDurability(definition: Record<string, unknown>): Record<string, unknown> {
  const xianxia = definitionXianxia(definition);
  return asRecord(xianxia.durability);
}

function definitionYinYang(definition: Record<string, unknown>): Record<string, unknown> {
  return asRecord(definitionXianxia(definition).yin_yang);
}

function definitionEnergies(definition: Record<string, unknown>): Record<string, unknown> {
  return asRecord(definitionXianxia(definition).energies);
}

function definitionEnergyMaxima(definition: Record<string, unknown>): Record<string, unknown> {
  return asRecord(definitionXianxia(definition).energy_maxima);
}

function xianxiaHpMax(definition: Record<string, unknown>): number {
  const xianxia = definitionXianxia(definition);
  return nonNegativeInt(definitionDurability(definition).hp_max ?? xianxia.hp_max ?? definitionStats(definition).max_hp, 10);
}

function xianxiaStanceMax(definition: Record<string, unknown>): number {
  const xianxia = definitionXianxia(definition);
  return nonNegativeInt(definitionDurability(definition).stance_max ?? xianxia.stance_max, 10);
}

function xianxiaEnergyMax(definition: Record<string, unknown>, energyKey: string): number {
  const energy = asRecord(definitionEnergies(definition)[energyKey]);
  return nonNegativeInt(energy.max ?? definitionEnergyMaxima(definition)[energyKey], 0);
}

function xianxiaYinMax(definition: Record<string, unknown>): number {
  return nonNegativeInt(definitionYinYang(definition).yin_max ?? definitionXianxia(definition).yin_max, 1);
}

function xianxiaYangMax(definition: Record<string, unknown>): number {
  return nonNegativeInt(definitionYinYang(definition).yang_max ?? definitionXianxia(definition).yang_max, 1);
}

function xianxiaDaoMax(definition: Record<string, unknown>): number {
  return nonNegativeInt(asRecord(definitionXianxia(definition).dao).max ?? definitionXianxia(definition).dao_max, 3);
}

function normalizeDndCurrencyFromEquipment(definition: Record<string, unknown>): Record<string, unknown> {
  const currency: Record<string, unknown> = { cp: 0, sp: 0, ep: 0, gp: 0, pp: 0, other: [] };
  for (const item of asArray(definition.equipment_catalog)) {
    const itemCurrency = asRecord(asRecord(item).currency);
    for (const denomination of DND_CURRENCY_KEYS) {
      currency[denomination] = asInt(currency[denomination], 0) + asInt(itemCurrency[denomination], 0);
    }
  }
  return currency;
}

function normalizeWeaponWieldModeValue(value: unknown): string {
  const normalized = asString(value)
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/[^a-z0-9 ]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized === "main hand") {
    return "main-hand";
  }
  if (normalized === "off hand") {
    return "off-hand";
  }
  if (normalized === "two handed") {
    return "two-handed";
  }
  return "";
}

function slugifyValue(value: unknown): string {
  return asString(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizeActiveInfusions(value: unknown): Record<string, unknown>[] {
  const normalized: Record<string, unknown>[] = [];
  const seen = new Set<string>();
  for (const rawEntry of asArray(value)) {
    const entry = asRecord(rawEntry);
    const name = asString(entry.name);
    const infusionKey = asString(entry.infusion_key || entry.key) || slugifyValue(name);
    if (!infusionKey || seen.has(infusionKey)) {
      continue;
    }
    seen.add(infusionKey);

    const payload: Record<string, unknown> = {
      infusion_key: infusionKey,
      name: name || infusionKey.replace(/-/g, " ").replace(/\b\w/g, (match) => match.toUpperCase()),
    };
    const sourceFeatureId = asString(entry.source_feature_id);
    if (sourceFeatureId) {
      payload.source_feature_id = sourceFeatureId;
    }
    if (infusionKey === "enhanced-defense") {
      payload.effect_key = "enhanced_defense";
    }
    normalized.push(payload);
  }
  return normalized;
}

function buildInventoryState(definition: Record<string, unknown>): unknown[] {
  const inventory: unknown[] = [];
  for (const rawItem of asArray(definition.equipment_catalog)) {
    const item = asRecord(rawItem);
    if (item.is_currency_only === true) {
      continue;
    }
    const payload: Record<string, unknown> = {
      id: item.id ?? null,
      catalog_ref: item.id ?? null,
      name: item.name ?? null,
      quantity: asInt(item.default_quantity, 0),
      weight: item.weight ?? null,
      is_equipped: Boolean(item.is_equipped),
      is_attuned: Boolean(item.is_attuned),
      charges_current: item.charges_current ?? null,
      charges_max: item.charges_max ?? null,
      notes: item.notes ?? "",
      tags: asArray(item.tags),
    };
    const weaponWieldMode = normalizeWeaponWieldModeValue(item.weapon_wield_mode);
    if (weaponWieldMode) {
      payload.weapon_wield_mode = weaponWieldMode;
    }
    const activeInfusions = normalizeActiveInfusions(item.active_infusions);
    if (activeInfusions.length > 0) {
      payload.active_infusions = activeInfusions;
    }
    inventory.push(payload);
  }
  return inventory;
}

function inventoryItemRef(item: unknown): string {
  const payload = asRecord(item);
  return asString(payload.catalog_ref || payload.id);
}

function normalizeAttunementState(inventory: unknown[]): Record<string, unknown> {
  const attunedItemRefs: string[] = [];
  const seenRefs = new Set<string>();
  for (const item of inventory) {
    const payload = asRecord(item);
    const itemRef = inventoryItemRef(payload);
    if (!itemRef || payload.is_attuned !== true || seenRefs.has(itemRef)) {
      continue;
    }
    seenRefs.add(itemRef);
    attunedItemRefs.push(itemRef);
  }
  return {
    max_attuned_items: 3,
    attuned_item_refs: attunedItemRefs,
  };
}

function buildResourceStates(definition: Record<string, unknown>): unknown[] {
  return asArray(definition.resource_templates).map((rawTemplate) => {
    const template = asRecord(rawTemplate);
    const maxValue = template.max === null || template.max === undefined ? null : nonNegativeInt(template.max, 0);
    return {
      id: template.id ?? "",
      label: template.label ?? "",
      category: template.category ?? "",
      current: clampInt(template.initial_current ?? template.current, maxValue ?? 0, maxValue ?? undefined),
      max: maxValue,
      reset_on: template.reset_on ?? "manual",
      reset_to: template.reset_to ?? "unchanged",
      rest_behavior: template.rest_behavior ?? "manual_only",
      notes: template.notes ?? "",
      display_order: asInt(template.display_order, 0),
    };
  });
}

function buildSpellSlotStates(definition: Record<string, unknown>): unknown[] {
  const spellcasting = asRecord(definition.spellcasting);
  const lanes = asArray(spellcasting.slot_lanes);
  const slots: unknown[] = [];
  for (const rawLane of lanes) {
    const lane = asRecord(rawLane);
    const laneId = asString(lane.id);
    for (const rawSlot of asArray(lane.slot_progression)) {
      const slot = asRecord(rawSlot);
      const level = asInt(slot.level, 0);
      const maxSlots = nonNegativeInt(slot.max_slots, 0);
      if (level <= 0 || maxSlots <= 0) {
        continue;
      }
      const stateSlot: Record<string, unknown> = { level, max: maxSlots, used: 0 };
      if (laneId) {
        stateSlot.slot_lane_id = laneId;
      }
      slots.push(stateSlot);
    }
  }
  if (slots.length === 0) {
    for (const rawSlot of asArray(spellcasting.slot_progression)) {
      const slot = asRecord(rawSlot);
      const level = asInt(slot.level, 0);
      const maxSlots = nonNegativeInt(slot.max_slots, 0);
      if (level > 0 && maxSlots > 0) {
        slots.push({ level, max: maxSlots, used: 0 });
      }
    }
  }
  return slots;
}

function normalizeClassName(value: unknown): string {
  return asString(value).toLowerCase().replace(/[^a-z]+/g, "");
}

function extractHitDieFaces(value: unknown): number {
  if (value === null || value === undefined || value === "") {
    return 0;
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    const record = asRecord(value);
    return extractHitDieFaces(record.faces ?? record.face ?? record.die);
  }
  const parsed = Number.parseInt(String(value).trim().toLowerCase().replace(/^d/, ""), 10);
  return VALID_HIT_DIE_FACES.has(parsed) ? parsed : 0;
}

function profileClassRows(definition: Record<string, unknown>): Record<string, unknown>[] {
  const profile = asRecord(definition.profile);
  const rows = asArray(profile.classes)
    .map(asRecord)
    .filter((row) => Object.keys(row).length > 0);
  if (rows.length > 0) {
    return rows;
  }
  const classLevelText = asString(profile.class_level_text);
  const match = classLevelText.match(/^([A-Za-z][A-Za-z '\-]*)\s+(\d+)$/);
  if (!match) {
    return [];
  }
  return [{ class_name: match[1]?.trim() || "", level: Number.parseInt(match[2] || "0", 10) }];
}

function hitDieFacesForClassRow(classRow: Record<string, unknown>): number {
  for (const key of ["hit_die_faces", "hit_die_face", "hit_die"]) {
    const faces = extractHitDieFaces(classRow[key]);
    if (faces) {
      return faces;
    }
  }
  const metadata = asRecord(classRow.metadata);
  const metadataFaces = extractHitDieFaces(metadata.hit_die ?? metadata.hitDie);
  if (metadataFaces) {
    return metadataFaces;
  }
  const systemsRef = asRecord(classRow.systems_ref);
  const systemsFaces = extractHitDieFaces(systemsRef.hit_die ?? systemsRef.hitDie);
  if (systemsFaces) {
    return systemsFaces;
  }
  const systemsMetadata = asRecord(systemsRef.metadata);
  const systemsMetadataFaces = extractHitDieFaces(systemsMetadata.hit_die ?? systemsMetadata.hitDie);
  if (systemsMetadataFaces) {
    return systemsMetadataFaces;
  }
  const className = normalizeClassName(classRow.class_name || classRow.name);
  return STANDARD_DND_CLASS_HIT_DICE[className] ?? (className ? 8 : 0);
}

function buildHitDiceState(definition: Record<string, unknown>): Record<string, unknown> {
  const maxByFaces = new Map<number, number>();
  for (const classRow of profileClassRows(definition)) {
    const level = nonNegativeInt(classRow.level, 0);
    const faces = hitDieFacesForClassRow(classRow);
    if (level > 0 && faces > 0) {
      maxByFaces.set(faces, (maxByFaces.get(faces) ?? 0) + level);
    }
  }
  return {
    pools: [...maxByFaces.entries()]
      .sort(([leftFaces], [rightFaces]) => leftFaces - rightFaces)
      .map(([faces, max]) => ({ faces, current: max, max })),
  };
}

function existingHitDiceCurrentByFaces(rawState: unknown): Map<number, number> {
  const currentByFaces = new Map<number, number>();
  for (const rawPool of asArray(asRecord(rawState).pools)) {
    const pool = asRecord(rawPool);
    const faces = asInt(pool.faces ?? pool.die_size ?? pool.die, 0);
    if (faces <= 0) {
      continue;
    }
    currentByFaces.set(faces, nonNegativeInt(pool.current, 0));
  }
  return currentByFaces;
}

function normalizeHitDiceState(definition: Record<string, unknown>, rawState: unknown): Record<string, unknown> {
  const derived = asArray(buildHitDiceState(definition).pools).map(asRecord);
  const existingCurrentByFaces = existingHitDiceCurrentByFaces(rawState);
  const pools = derived
    .map((pool) => {
      const faces = asInt(pool.faces, 0);
      const max = nonNegativeInt(pool.max, 0);
      const existingCurrent = existingCurrentByFaces.get(faces);
      return {
        faces,
        current: Math.max(0, Math.min(existingCurrent ?? max, max)),
        max,
      };
    })
    .filter((pool) => pool.faces > 0 && pool.max > 0);
  return { pools };
}

function normalizeHitDiceStatePayload(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
): Record<string, unknown> {
  const payload = copyState(state);
  const normalized = normalizeHitDiceState(definition, payload.hit_dice);
  if (asArray(normalized.pools).length > 0) {
    payload.hit_dice = normalized;
  } else {
    delete payload.hit_dice;
  }
  return payload;
}

function hitDiceLongRestRegainAmount(definition: Record<string, unknown>): number {
  const totalLevel = asArray(buildHitDiceState(definition).pools)
    .map(asRecord)
    .reduce((total, pool) => total + nonNegativeInt(pool.max, 0), 0);
  return totalLevel > 0 ? Math.max(1, Math.floor(totalLevel / 2)) : 0;
}

function applyLongRestHitDiceRecovery(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
): Record<string, unknown> {
  const payload = normalizeHitDiceStatePayload(definition, state);
  const hitDice = { ...asRecord(payload.hit_dice) };
  const pools = asArray(hitDice.pools).map((rawPool) => ({ ...asRecord(rawPool) }));
  let remaining = hitDiceLongRestRegainAmount(definition);
  if (remaining <= 0) {
    return payload;
  }

  for (const pool of [...pools].sort((left, right) => asInt(right.faces, 0) - asInt(left.faces, 0))) {
    if (remaining <= 0) {
      break;
    }
    const current = nonNegativeInt(pool.current, 0);
    const maximum = nonNegativeInt(pool.max, 0);
    const missing = Math.max(0, maximum - current);
    if (missing <= 0) {
      continue;
    }
    const recovered = Math.min(missing, remaining);
    pool.current = current + recovered;
    remaining -= recovered;
  }

  hitDice.pools = pools.sort((left, right) => asInt(left.faces, 0) - asInt(right.faces, 0));
  payload.hit_dice = hitDice;
  return payload;
}

function hitDiceSummaryFromState(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
): Record<string, unknown> {
  const normalized = normalizeHitDiceState(definition, state.hit_dice);
  const pools = asArray(normalized.pools)
    .map(asRecord)
    .map((pool) => {
      const faces = asInt(pool.faces, 0);
      return {
        faces,
        label: `d${faces}`,
        current: asInt(pool.current, 0),
        max: asInt(pool.max, 0),
        input_name: `hit_dice_d${faces}`,
      };
    })
    .filter((pool) => pool.faces > 0);
  const value = pools.map((pool) => `${pool.label} ${pool.current}/${pool.max}`).join(" | ");
  const fullValue = pools
    .filter((pool) => pool.max > 0)
    .map((pool) => `${pool.max}d${pool.faces}`)
    .join(" + ");
  return {
    pools,
    value: value || "--",
    full_value: fullValue || "--",
    regain_on_long_rest: hitDiceLongRestRegainAmount(definition),
  };
}

function hitDiceRestChanges(
  definition: Record<string, unknown>,
  beforeState: Record<string, unknown>,
  afterState: Record<string, unknown>,
): CharacterRestChangePayload[] {
  const before = hitDiceSummaryFromState(definition, beforeState);
  const after = hitDiceSummaryFromState(definition, afterState);
  if (before.value === after.value) {
    return [];
  }
  return [
    {
      label: "Hit Dice",
      from_value: String(before.value),
      to_value: String(after.value),
    },
  ];
}

function normalizeHitDiceCurrentPayload(payload: Record<string, unknown>): Map<number, unknown> | null {
  const rawValue = payload.hit_dice_current ?? payload.hit_dice;
  if (rawValue === null || rawValue === undefined || rawValue === "") {
    return null;
  }
  if (typeof rawValue !== "object" || Array.isArray(rawValue)) {
    throw new Error("Hit Dice must be submitted as an object keyed by die size.");
  }
  const valuesByFaces = new Map<number, unknown>();
  for (const [rawFaces, current] of Object.entries(rawValue as Record<string, unknown>)) {
    if (!hasSubmittedValue(current)) {
      continue;
    }
    const normalizedFaces = rawFaces.startsWith("d") ? rawFaces.slice(1) : rawFaces;
    const faces = Number.parseInt(normalizedFaces, 10);
    if (!/^\d+$/.test(normalizedFaces) || !Number.isFinite(faces)) {
      throw new Error("Hit Dice keys must be die sizes such as 6, 8, or d10.");
    }
    valuesByFaces.set(faces, current);
  }
  return valuesByFaces.size > 0 ? valuesByFaces : null;
}

function applyHitDiceCurrentValues(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
  valuesByFaces: Map<number, unknown>,
): Record<string, unknown> {
  const normalized = normalizeHitDiceState(definition, state.hit_dice);
  const pools = asArray(normalized.pools).map((rawPool) => {
    const pool = asRecord(rawPool);
    const faces = asInt(pool.faces, 0);
    const max = nonNegativeInt(pool.max, 0);
    const submittedCurrent = valuesByFaces.get(faces);
    const current = submittedCurrent === undefined
      ? nonNegativeInt(pool.current, 0)
      : parseRequiredWholeNumber(submittedCurrent, "Hit Dice");
    return {
      faces,
      current: Math.max(0, Math.min(current, max)),
      max,
    };
  });
  return { ...state, hit_dice: { pools } };
}

function normalizeNotes(value: unknown): Record<string, unknown> {
  const notes = asRecord(value);
  return {
    player_notes_markdown: asString(notes.player_notes_markdown),
    physical_description_markdown: asString(notes.physical_description_markdown),
    background_markdown: asString(notes.background_markdown),
    session_notes: asArray(notes.session_notes),
  };
}

function normalizeActiveStateRecord(value: unknown): Record<string, unknown> {
  if (typeof value === "string") {
    const name = asString(value);
    return name ? { name } : {};
  }
  const record = asRecord(value);
  const name = asString(record.name || record.label);
  return name ? { ...record, name } : {};
}

function normalizeXianxiaCurrency(value: unknown): Record<string, number> {
  const currency = asRecord(value);
  const normalized: Record<string, number> = {};
  for (const key of XIANXIA_CURRENCY_KEYS) {
    normalized[key] = nonNegativeInt(currency[key], 0);
  }
  return normalized;
}

function normalizeXianxiaInventory(rawXianxiaInventory: unknown, sharedInventory: unknown): unknown[] {
  if (Array.isArray(rawXianxiaInventory)) {
    return rawXianxiaInventory;
  }
  const rawInventoryRecord = asRecord(rawXianxiaInventory);
  if (Array.isArray(rawInventoryRecord.quantities)) {
    return rawInventoryRecord.quantities;
  }
  return asArray(sharedInventory);
}

function normalizeXianxiaStateFromShared(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
): Record<string, unknown> {
  const rawXianxia = asRecord(state.xianxia);
  const rawXianxiaVitals = asRecord(rawXianxia.vitals);
  const sharedVitals = asRecord(state.vitals);
  const currentHpSource = Object.hasOwn(sharedVitals, "current_hp")
    ? sharedVitals.current_hp
    : rawXianxiaVitals.current_hp ?? rawXianxia.hp_current ?? rawXianxia.current_hp;
  const tempHpSource = Object.hasOwn(sharedVitals, "temp_hp")
    ? sharedVitals.temp_hp
    : rawXianxiaVitals.temp_hp ?? rawXianxia.hp_temp ?? rawXianxia.temp_hp;
  const rawEnergies = asRecord(rawXianxia.energies);
  const rawYinYang = asRecord(rawXianxia.yin_yang);
  const rawDao = asRecord(rawXianxia.dao);
  const energies: Record<string, Record<string, number>> = {};
  for (const key of XIANXIA_ENERGY_KEYS) {
    const energyMax = xianxiaEnergyMax(definition, key);
    energies[key] = {
      current: clampInt(asRecord(rawEnergies[key]).current ?? asRecord(rawXianxia.energies_current)[key], energyMax, energyMax),
    };
  }

  return {
    schema_version: asInt(rawXianxia.schema_version, 1),
    vitals: {
      current_hp: clampInt(currentHpSource, xianxiaHpMax(definition), xianxiaHpMax(definition)),
      temp_hp: clampInt(tempHpSource, 0),
      current_stance: clampInt(
        rawXianxiaVitals.current_stance ?? rawXianxiaVitals.stance_current ?? rawXianxia.stance_current,
        xianxiaStanceMax(definition),
        xianxiaStanceMax(definition),
      ),
      temp_stance: clampInt(rawXianxiaVitals.temp_stance ?? rawXianxiaVitals.stance_temp ?? rawXianxia.stance_temp, 0),
    },
    energies,
    yin_yang: {
      yin_current: clampInt(rawYinYang.yin_current ?? rawXianxia.yin_current, xianxiaYinMax(definition), xianxiaYinMax(definition)),
      yang_current: clampInt(rawYinYang.yang_current ?? rawXianxia.yang_current, xianxiaYangMax(definition), xianxiaYangMax(definition)),
    },
    dao: {
      current: clampInt(rawDao.current ?? rawXianxia.dao_current, 0, xianxiaDaoMax(definition)),
    },
    active_stance: normalizeActiveStateRecord(rawXianxia.active_stance),
    active_aura: normalizeActiveStateRecord(rawXianxia.active_aura),
    currency: normalizeXianxiaCurrency(asRecord(rawXianxia.currency)),
    inventory: normalizeXianxiaInventory(rawXianxia.inventory, state.inventory),
    notes: {
      ...asRecord(rawXianxia.notes),
      player_notes_markdown: asString(asRecord(state.notes).player_notes_markdown),
    },
  };
}

function buildXianxiaInitialState(definition: Record<string, unknown>): Record<string, unknown> {
  const xianxiaState = normalizeXianxiaStateFromShared(definition, {});
  const inventory = buildInventoryState(definition);
  return {
    status: asString(definition.status) || "active",
    vitals: {
      current_hp: asInt(asRecord(xianxiaState.vitals).current_hp, 0),
      temp_hp: asInt(asRecord(xianxiaState.vitals).temp_hp, 0),
    },
    resources: [],
    inventory,
    currency: normalizeDndCurrencyFromEquipment(definition),
    spell_slots: [],
    attunement: normalizeAttunementState(inventory),
    notes: normalizeNotes({}),
    xianxia: xianxiaState,
  };
}

function buildDndInitialState(definition: Record<string, unknown>): Record<string, unknown> {
  const maxHp = nonNegativeInt(definitionStats(definition).max_hp, 0);
  const inventory = buildInventoryState(definition);
  return {
    status: asString(definition.status) || "active",
    vitals: {
      current_hp: maxHp,
      temp_hp: 0,
      death_saves: { successes: 0, failures: 0 },
    },
    hit_dice: buildHitDiceState(definition),
    resources: buildResourceStates(definition),
    inventory,
    currency: normalizeDndCurrencyFromEquipment(definition),
    spell_slots: buildSpellSlotStates(definition),
    attunement: normalizeAttunementState(inventory),
    notes: normalizeNotes({}),
  };
}

function buildInitialState(definition: Record<string, unknown>): Record<string, unknown> {
  return normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE
    ? buildXianxiaInitialState(definition)
    : buildDndInitialState(definition);
}

function copyState(state: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(state)) as Record<string, unknown>;
}

function applyVitalsUpdate(state: Record<string, unknown>, payload: Record<string, unknown>): void {
  const vitals = { ...asRecord(state.vitals) };
  let currentHp = asInt(vitals.current_hp, 0);
  let tempHp = asInt(vitals.temp_hp, 0);
  const currentHpValue = parseOptionalWholeNumber(payload.current_hp, "Current HP");
  if (currentHpValue !== null) {
    currentHp = currentHpValue;
  }
  const hpDeltaValue = parseOptionalWholeNumber(payload.hp_delta, "HP delta");
  if (hpDeltaValue !== null) {
    currentHp += hpDeltaValue;
  }

  if (Boolean(payload.clear_temp_hp)) {
    tempHp = 0;
  } else {
    const tempHpValue = parseOptionalWholeNumber(payload.temp_hp, "Temp HP");
    if (tempHpValue !== null) {
      tempHp = tempHpValue;
    }
  }
  const tempHpDeltaValue = parseOptionalWholeNumber(payload.temp_hp_delta, "Temp HP delta");
  if (tempHpDeltaValue !== null) {
    tempHp += tempHpDeltaValue;
  }

  vitals.current_hp = currentHp;
  vitals.temp_hp = tempHp;
  state.vitals = vitals;
}

function applyXianxiaVitalsUpdate(state: Record<string, unknown>, payload: Record<string, unknown>): void {
  const xianxia = { ...asRecord(state.xianxia) };
  const vitals = { ...asRecord(xianxia.vitals) };
  const currentStance = parseOptionalWholeNumber(payload.current_stance, "Current Stance");
  if (currentStance !== null) {
    vitals.current_stance = currentStance;
  }
  const tempStance = parseOptionalWholeNumber(payload.temp_stance, "Temp Stance");
  if (tempStance !== null) {
    vitals.temp_stance = tempStance;
  }
  xianxia.vitals = vitals;

  const energies = { ...asRecord(xianxia.energies) };
  for (const [payloadKey, energyKey, label] of [
    ["current_jing", "jing", "Jing"],
    ["current_qi", "qi", "Qi"],
    ["current_shen", "shen", "Shen"],
  ] as const) {
    const energyValue = parseOptionalWholeNumber(payload[payloadKey], label);
    if (energyValue === null) {
      continue;
    }
    energies[energyKey] = { ...asRecord(energies[energyKey]), current: energyValue };
  }
  xianxia.energies = energies;

  const yinYang = { ...asRecord(xianxia.yin_yang) };
  const currentYin = parseOptionalWholeNumber(payload.current_yin, "Yin");
  if (currentYin !== null) {
    yinYang.yin_current = currentYin;
  }
  const currentYang = parseOptionalWholeNumber(payload.current_yang, "Yang");
  if (currentYang !== null) {
    yinYang.yang_current = currentYang;
  }
  xianxia.yin_yang = yinYang;

  const dao = { ...asRecord(xianxia.dao) };
  const currentDao = parseOptionalWholeNumber(payload.current_dao, "Dao");
  if (currentDao !== null) {
    dao.current = currentDao;
  }
  xianxia.dao = dao;
  state.xianxia = xianxia;
}

function normalizeSubmittedXianxiaActiveStateValue(value: unknown): Record<string, unknown> | null | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  const normalized = String(value || "")
    .split(/\s+/)
    .filter((part) => part.length > 0)
    .join(" ")
    .trim();
  return normalized ? { name: normalized } : null;
}

function applyXianxiaActiveStateUpdate(state: Record<string, unknown>, payload: Record<string, unknown>): void {
  const xianxia = { ...asRecord(state.xianxia) };
  if (Object.hasOwn(payload, "active_stance_name")) {
    const activeStance = normalizeSubmittedXianxiaActiveStateValue(payload.active_stance_name);
    if (activeStance !== undefined) {
      xianxia.active_stance = activeStance;
    }
  }
  if (Object.hasOwn(payload, "active_aura_name")) {
    const activeAura = normalizeSubmittedXianxiaActiveStateValue(payload.active_aura_name);
    if (activeAura !== undefined) {
      xianxia.active_aura = activeAura;
    }
  }
  state.xianxia = xianxia;
}

function findStateItemById(items: unknown, targetId: string, itemType: string): Record<string, unknown> {
  const match = asArray(items).map(asRecord).find((item) => asString(item.id) === targetId);
  if (!match) {
    throw new Error(`Unknown ${itemType}: ${targetId}`);
  }
  return match;
}

function applyResourceUpdate(state: Record<string, unknown>, resourceId: string, payload: Record<string, unknown>): void {
  const resources = asArray(state.resources);
  const resource = findStateItemById(resources, resourceId, "resource");
  let current = asInt(resource.current, 0);
  const currentValue = parseOptionalWholeNumber(payload.current, "Current");
  if (currentValue !== null) {
    current = currentValue;
  }
  const deltaValue = parseOptionalWholeNumber(payload.delta, "Delta");
  if (deltaValue !== null) {
    current += deltaValue;
  }
  resource.current = current;
  state.resources = resources;
}

function normalizeSpellSlotLaneId(value: unknown): string {
  return String(value || "").trim();
}

function applySpellSlotsUpdate(
  state: Record<string, unknown>,
  level: number,
  payload: Record<string, unknown>,
): void {
  const slots = asArray(state.spell_slots);
  const cleanLaneId = normalizeSpellSlotLaneId(payload.slot_lane_id);
  let slot = slots.map(asRecord).find(
    (item) =>
      asInt(item.level, 0) === level &&
      normalizeSpellSlotLaneId(item.slot_lane_id) === cleanLaneId,
  );
  if (!slot && cleanLaneId) {
    slot = slots.map(asRecord).find(
      (item) => asInt(item.level, 0) === level && !normalizeSpellSlotLaneId(item.slot_lane_id),
    );
    if (slot) {
      slot.slot_lane_id = cleanLaneId;
    }
  }
  if (!slot) {
    const laneLabel = cleanLaneId ? ` in slot lane '${cleanLaneId}'` : "";
    throw new Error(`Unknown spell slot level: ${level}${laneLabel}`);
  }

  let used = asInt(slot.used, 0);
  const usedValue = parseOptionalWholeNumber(payload.used, "Used spell slots");
  if (usedValue !== null) {
    used = usedValue;
  }
  const deltaUsedValue = parseOptionalWholeNumber(payload.delta_used, "Spell slot delta");
  if (deltaUsedValue !== null) {
    used += deltaUsedValue;
  }
  slot.used = used;
  state.spell_slots = slots;
}

function syncTopLevelXianxiaInventory(state: Record<string, unknown>, quantities: Record<string, unknown>[]): void {
  const xianxia = { ...asRecord(state.xianxia) };
  xianxia.inventory = {
    enabled: quantities.length > 0,
    quantities,
  };
  state.xianxia = xianxia;
  state.inventory = quantities.map((item) => ({
    id: item.id,
    catalog_ref: item.catalog_ref,
    name: item.name,
    quantity: asInt(item.quantity, 0),
    item_type: item.item_type,
    item_nature: item.item_nature,
    equippable: Boolean(item.equippable),
    is_equipped: Boolean(item.is_equipped),
    weight: item.weight,
    is_attuned: Boolean(item.is_attuned),
    charges_current: item.charges_current,
    charges_max: item.charges_max,
    notes: item.notes ?? "",
    tags: asArray(item.tags),
    legacy_tags: asArray(item.legacy_tags),
    systems_ref: item.systems_ref,
  }));
}

function xianxiaInventoryRows(state: Record<string, unknown>): Record<string, unknown>[] {
  const xianxiaInventory = asRecord(asRecord(state.xianxia).inventory);
  const rows = Array.isArray(xianxiaInventory.quantities)
    ? asArray(xianxiaInventory.quantities)
    : asArray(state.inventory);
  return rows.map((row) => ({ ...asRecord(row), quantity: asInt(asRecord(row).quantity, 0) }));
}

function applyInventoryQuantityUpdate(
  state: Record<string, unknown>,
  itemId: string,
  payload: Record<string, unknown>,
  isXianxia: boolean,
): void {
  if (isXianxia) {
    const quantities = xianxiaInventoryRows(state);
    const item = quantities.find((row) => asString(row.id) === itemId);
    if (!item) {
      throw new Error(`Unknown Xianxia inventory item: ${itemId}`);
    }
    let quantity = asInt(item.quantity, 0);
    const quantityValue = parseOptionalWholeNumber(payload.quantity, "Quantity");
    if (quantityValue !== null) {
      quantity = quantityValue;
    }
    const deltaValue = parseOptionalWholeNumber(payload.delta, "Quantity delta");
    if (deltaValue !== null) {
      quantity += deltaValue;
    }
    item.quantity = quantity;
    syncTopLevelXianxiaInventory(state, quantities);
    return;
  }

  const inventory = asArray(state.inventory);
  const item = findStateItemById(inventory, itemId, "inventory item");
  let quantity = asInt(item.quantity, 0);
  const quantityValue = parseOptionalWholeNumber(payload.quantity, "Quantity");
  if (quantityValue !== null) {
    quantity = quantityValue;
  }
  const deltaValue = parseOptionalWholeNumber(payload.delta, "Quantity delta");
  if (deltaValue !== null) {
    quantity += deltaValue;
  }
  item.quantity = quantity;
  state.inventory = inventory;
}

function applyCurrencyUpdate(
  state: Record<string, unknown>,
  payload: Record<string, unknown>,
  isXianxia: boolean,
): void {
  if (isXianxia) {
    const xianxia = { ...asRecord(state.xianxia) };
    const currency = { ...asRecord(xianxia.currency) };
    for (const key of XIANXIA_CURRENCY_KEYS) {
      const value = parseOptionalWholeNumber(payload[key], key.replace(/_/g, " "));
      if (value !== null) {
        currency[key] = Math.max(0, value);
      }
      if (!Object.hasOwn(currency, key)) {
        currency[key] = 0;
      }
    }
    xianxia.currency = currency;
    state.xianxia = xianxia;
    return;
  }

  const currency = { ...asRecord(state.currency) };
  for (const key of DND_CURRENCY_KEYS) {
    const value = parseOptionalWholeNumber(payload[key], key.toUpperCase());
    if (value !== null) {
      currency[key] = value;
    }
    if (!Object.hasOwn(currency, key)) {
      currency[key] = 0;
    }
  }
  state.currency = currency;
}

function normalizeSubmittedPlayerNotesMarkdown(value: unknown): string {
  return value ? String(value) : "";
}

function applyPlayerNotesUpdate(state: Record<string, unknown>, payload: Record<string, unknown>): void {
  const notes = { ...asRecord(state.notes) };
  notes.player_notes_markdown = normalizeSubmittedPlayerNotesMarkdown(payload.player_notes_markdown);
  state.notes = notes;
}

function normalizeSubmittedPersonalMarkdown(value: unknown): string {
  return value ? String(value) : "";
}

function applyPersonalDetailsUpdate(state: Record<string, unknown>, payload: Record<string, unknown>): void {
  const notes = { ...asRecord(state.notes) };
  notes.physical_description_markdown = normalizeSubmittedPersonalMarkdown(payload.physical_description_markdown);
  notes.background_markdown = normalizeSubmittedPersonalMarkdown(payload.background_markdown);
  state.notes = notes;
}

function normalizeFeatureStateKey(value: unknown): string {
  const normalized = String(value ?? "").split(/\s+/).join(" ").trim().replace(/[- ]+/g, "_").toLowerCase();
  if (normalized === "arcane_armor" || normalized === "arcanearmor") {
    return "arcane_armor";
  }
  throw new Error("Choose a supported feature state to update.");
}

function definitionHasFeature(definition: Record<string, unknown>, featureName: string): boolean {
  const target = featureName.split(/\s+/).join(" ").trim().toLowerCase();
  return asArray(definition.features).some((rawFeature) => {
    const feature = asRecord(rawFeature);
    return String(feature.name ?? "").split(/\s+/).join(" ").trim().toLowerCase() === target;
  });
}

function applyFeatureStateUpdate(
  state: Record<string, unknown>,
  definition: Record<string, unknown>,
  featureKey: string,
  payload: Record<string, unknown>,
): void {
  const normalizedKey = normalizeFeatureStateKey(featureKey);
  if (normalizedKey === "arcane_armor" && !definitionHasFeature(definition, "arcane armor")) {
    throw new Error("Arcane Armor state is only available for Armorer sheets with Arcane Armor.");
  }

  const featureStates = { ...asRecord(state.feature_states) };
  const featureState = { ...asRecord(featureStates[normalizedKey]) };
  featureState.enabled = Boolean(payload.enabled);
  featureStates[normalizedKey] = featureState;
  state.feature_states = featureStates;
}

function isXianxiaDefinition(definition: Record<string, unknown>): boolean {
  return normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE;
}

function normalizeRestType(restType: unknown): "short" | "long" {
  const rawRestType = String(restType ?? "");
  const normalized = rawRestType.trim().toLowerCase();
  if (normalized !== "short" && normalized !== "long") {
    throw new Error(`Unsupported rest type: ${rawRestType}`);
  }
  return normalized;
}

function restLabel(restType: "short" | "long"): string {
  return restType === "short" ? "Short Rest" : "Long Rest";
}

function shouldResetResource(resource: Record<string, unknown>, restType: "short" | "long"): boolean {
  const resetOn = asString(resource.reset_on || "manual").toLowerCase();
  const restBehavior = asString(resource.rest_behavior).toLowerCase();
  if (restBehavior === "manual_only") {
    return false;
  }
  if (restType === "short") {
    return resetOn === "short_rest";
  }
  return resetOn === "short_rest" || resetOn === "long_rest";
}

function resetResourceValue(resource: Record<string, unknown>): number {
  const resetTo = asString(resource.reset_to || "unchanged").toLowerCase();
  const current = asInt(resource.current, 0);
  const maxValue = resource.max;
  if (resetTo === "unchanged") {
    return current;
  }
  if (resetTo === "max") {
    return maxValue === null || maxValue === undefined ? current : asInt(maxValue, current);
  }
  if (resetTo === "zero" || resetTo === "0") {
    return 0;
  }
  return Number.parseInt(resetTo, 10);
}

function resourceValueText(current: number, maxValue: unknown): string {
  if (maxValue === null || maxValue === undefined) {
    return String(current);
  }
  return `${current} / ${asInt(maxValue, 0)}`;
}

function normalizeSpellSlotProgression(rawProgression: unknown): Record<string, number>[] {
  return asArray(rawProgression)
    .map(asRecord)
    .map((slot) => ({
      level: asInt(slot.level, 0),
      max_slots: nonNegativeInt(slot.max_slots, 0),
    }))
    .filter((slot) => slot.level > 0);
}

function spellSlotLaneTitleMap(spellcasting: unknown): Map<string, string> {
  const payload = asRecord(spellcasting);
  const rawLanes = asArray(payload.slot_lanes).map(asRecord).filter((lane) => Object.keys(lane).length > 0);
  if (rawLanes.length > 0) {
    const laneTitles = new Map<string, string>();
    rawLanes.forEach((lane, index) => {
      const laneId = normalizeSpellSlotLaneId(lane.id || lane.slot_lane_id || `slot-lane-${index + 1}`);
      laneTitles.set(laneId, asString(lane.title) || "Spell slots");
    });
    return laneTitles;
  }
  return normalizeSpellSlotProgression(payload.slot_progression).length > 0
    ? new Map([["", "Spell slots"]])
    : new Map();
}

function spellLevelLabel(level: number): string {
  if (level === 1) {
    return "1st level";
  }
  if (level === 2) {
    return "2nd level";
  }
  if (level === 3) {
    return "3rd level";
  }
  return `${level}th level`;
}

function applyXianxiaOneDayRest(state: Record<string, unknown>, definition: Record<string, unknown>): void {
  const xianxia = { ...asRecord(state.xianxia) };
  const vitals = { ...asRecord(xianxia.vitals) };
  const hpMax = xianxiaHpMax(definition);
  const stanceMax = xianxiaStanceMax(definition);
  vitals.current_hp = hpMax;
  vitals.current_stance = stanceMax;
  xianxia.vitals = vitals;

  const energies: Record<string, Record<string, number>> = {};
  for (const key of XIANXIA_ENERGY_KEYS) {
    energies[key] = { current: xianxiaEnergyMax(definition, key) };
  }
  xianxia.energies = energies;
  xianxia.yin_yang = {
    yin_current: xianxiaYinMax(definition),
    yang_current: xianxiaYangMax(definition),
  };
  state.xianxia = xianxia;

  const sharedVitals = { ...asRecord(state.vitals) };
  sharedVitals.current_hp = hpMax;
  state.vitals = sharedVitals;
}

function appendPoolRecoveryChange(
  changes: CharacterRestChangePayload[],
  label: string,
  current: unknown,
  maximum: number,
): void {
  const currentValue = Math.max(0, asInt(current, 0));
  const maxValue = Math.max(0, Math.trunc(maximum));
  if (currentValue === maxValue) {
    return;
  }
  changes.push({
    label,
    from_value: resourceValueText(currentValue, maxValue),
    to_value: resourceValueText(maxValue, maxValue),
  });
}

function collectXianxiaOneDayRestChanges(
  state: Record<string, unknown>,
  definition: Record<string, unknown>,
): CharacterRestChangePayload[] {
  const changes: CharacterRestChangePayload[] = [];
  const xianxia = asRecord(state.xianxia);
  const vitals = asRecord(xianxia.vitals);
  appendPoolRecoveryChange(changes, "HP", vitals.current_hp, xianxiaHpMax(definition));
  appendPoolRecoveryChange(changes, "Stance", vitals.current_stance, xianxiaStanceMax(definition));

  const energies = asRecord(xianxia.energies);
  for (const key of XIANXIA_ENERGY_KEYS) {
    const energy = asRecord(energies[key]);
    appendPoolRecoveryChange(
      changes,
      `${XIANXIA_ENERGY_LABELS[key]} Energy`,
      energy.current,
      xianxiaEnergyMax(definition, key),
    );
  }

  const yinYang = asRecord(xianxia.yin_yang);
  appendPoolRecoveryChange(changes, "Yin", yinYang.yin_current, xianxiaYinMax(definition));
  appendPoolRecoveryChange(changes, "Yang", yinYang.yang_current, xianxiaYangMax(definition));
  return changes;
}

function modeledRestState(
  state: Record<string, unknown>,
  restType: "short" | "long",
  definition: Record<string, unknown>,
): Record<string, unknown> {
  let modeledState = copyState(state);
  for (const rawResource of asArray(modeledState.resources)) {
    const resource = asRecord(rawResource);
    if (shouldResetResource(resource, restType)) {
      resource.current = resetResourceValue(resource);
    }
  }

  if (restType === "long") {
    for (const rawSlot of asArray(modeledState.spell_slots)) {
      asRecord(rawSlot).used = 0;
    }
    if (isXianxiaDefinition(definition)) {
      applyXianxiaOneDayRest(modeledState, definition);
    } else {
      modeledState = applyLongRestHitDiceRecovery(definition, modeledState);
    }
  } else if (!isXianxiaDefinition(definition)) {
    modeledState = normalizeHitDiceStatePayload(definition, modeledState);
  }
  return modeledState;
}

function restAdjustmentsFromState(
  state: Record<string, unknown>,
  definition: Record<string, unknown>,
): Record<string, unknown> {
  const vitals = asRecord(state.vitals);
  const adjustments: Record<string, unknown> = {
    current_hp: asInt(vitals.current_hp, 0),
  };
  const hitDice = hitDiceSummaryFromState(definition, state);
  if (asArray(hitDice.pools).length > 0) {
    adjustments.hit_dice = hitDice;
  }
  return adjustments;
}

function collectRestChanges(
  state: Record<string, unknown>,
  restType: "short" | "long",
  definition: Record<string, unknown>,
): CharacterRestChangePayload[] {
  const changes: CharacterRestChangePayload[] = [];
  for (const rawResource of asArray(state.resources)) {
    const resource = asRecord(rawResource);
    if (!shouldResetResource(resource, restType)) {
      continue;
    }
    const nextCurrent = resetResourceValue(resource);
    const current = asInt(resource.current, 0);
    if (current === nextCurrent) {
      continue;
    }
    changes.push({
      label: asString(resource.label) || "Resource",
      from_value: resourceValueText(current, resource.max),
      to_value: resourceValueText(nextCurrent, resource.max),
    });
  }

  if (restType !== "long") {
    return changes;
  }

  if (isXianxiaDefinition(definition)) {
    changes.push(...collectXianxiaOneDayRestChanges(state, definition));
  } else {
    const restedState = applyLongRestHitDiceRecovery(definition, state);
    changes.push(...hitDiceRestChanges(definition, state, restedState));
  }

  const laneTitles = spellSlotLaneTitleMap(definition.spellcasting);
  const totalLanes = laneTitles.size;
  for (const rawSlot of asArray(state.spell_slots)) {
    const slot = asRecord(rawSlot);
    const used = asInt(slot.used, 0);
    const maxSlots = asInt(slot.max, 0);
    if (used <= 0) {
      continue;
    }
    const laneId = normalizeSpellSlotLaneId(slot.slot_lane_id);
    const laneTitle = laneTitles.get(laneId) || "Spell slots";
    let label = `${spellLevelLabel(asInt(slot.level, 0))} spell slots`;
    if (totalLanes > 1) {
      label = `${laneTitle}: ${label}`;
    }
    changes.push({
      label,
      from_value: `${maxSlots - used} available / ${maxSlots}`,
      to_value: `${maxSlots} available / ${maxSlots}`,
    });
  }

  return changes;
}

function readCharacterStateForRest(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
): { status: "ok"; revision: number; state: Record<string, unknown> } | { status: "validation_error"; message: string } {
  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }
    const existingState = readCharacterState(database, campaignSlug, characterSlug);
    return {
      status: "ok",
      revision: existingState?.revision ?? 1,
      state: existingState?.state ?? buildInitialState(definition),
    };
  } finally {
    database.close();
  }
}

export function previewCharacterRest(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  restType: string,
): CharacterRestPreviewResult {
  let normalizedRest: "short" | "long";
  try {
    normalizedRest = normalizeRestType(restType);
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid rest type." };
  }

  const stateResult = readCharacterStateForRest(config, campaignSlug, characterSlug, definition);
  if (stateResult.status === "validation_error") {
    return stateResult;
  }

  const modeledState = modeledRestState(stateResult.state, normalizedRest, definition);
  return {
    status: "ok",
    preview: {
      rest_type: normalizedRest,
      label: restLabel(normalizedRest),
      changes: collectRestChanges(stateResult.state, normalizedRest, definition),
      adjustments: restAdjustmentsFromState(modeledState, definition),
    },
  };
}

export function canEditCharacterSessionState(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  role: string,
  userId: number | undefined,
): boolean {
  if (role === "admin" || role === "dm") {
    return true;
  }
  if (role !== "player" || userId === undefined) {
    return false;
  }
  const database = openDatabase(config);
  if (!database) {
    return false;
  }
  try {
    if (!tableExists(database, "character_assignments")) {
      return false;
    }
    const row = database
      .prepare(
        `
          SELECT id
          FROM character_assignments
          WHERE user_id = ?
            AND campaign_slug = ?
            AND character_slug = ?
        `,
      )
      .get(userId, campaignSlug, characterSlug) as { id?: number } | undefined;
    return Boolean(row?.id);
  } finally {
    database.close();
  }
}

export function updateCharacterSessionVitals(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionVitalsUpdateResult {
  let expectedRevision: number;
  let hitDiceCurrentValues: Map<number, unknown> | null;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    hitDiceCurrentValues = normalizeHitDiceCurrentPayload(payload);
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character vitals payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    let nextState = copyState(existingState.state);
    try {
      applyVitalsUpdate(nextState, payload);
      if (hitDiceCurrentValues && normalizeSystemKey(definition.system) !== XIANXIA_SYSTEM_CODE) {
        nextState = applyHitDiceCurrentValues(definition, nextState, hitDiceCurrentValues);
      }
      if (normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE) {
        applyXianxiaVitalsUpdate(nextState, payload);
      }
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character vitals payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionResource(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  resourceId: string,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionResourceUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character resource payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    try {
      applyResourceUpdate(nextState, resourceId, payload);
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character resource payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionSpellSlots(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  levelValue: unknown,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionSpellSlotsUpdateResult {
  let expectedRevision: number;
  let level: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    level = parseRequiredWholeNumber(levelValue, "Spell slot level");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character spell slot payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    try {
      applySpellSlotsUpdate(nextState, level, payload);
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character spell slot payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionInventory(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  itemId: string,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionInventoryUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character inventory payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    try {
      applyInventoryQuantityUpdate(nextState, itemId, payload, normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE);
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character inventory payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionXianxiaActiveState(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionXianxiaActiveStateUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character active state payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (normalizeSystemKey(definition.system) !== XIANXIA_SYSTEM_CODE) {
      return {
        status: "validation_error",
        message: "Active Stance and Aura state is only supported for Xianxia characters.",
      };
    }

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    try {
      applyXianxiaActiveStateUpdate(nextState, payload);
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character active state payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionCurrency(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionCurrencyUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character currency payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    try {
      applyCurrencyUpdate(nextState, payload, normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE);
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character currency payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionNotes(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionNotesUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character notes payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    applyPlayerNotesUpdate(nextState, payload);

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionPersonal(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionPersonalUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character personal payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    applyPersonalDetailsUpdate(nextState, payload);

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function updateCharacterSessionFeatureState(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  featureKey: string,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionFeatureStateUpdateResult {
  let expectedRevision: number;
  try {
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character feature state payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    const nextState = copyState(existingState.state);
    try {
      applyFeatureStateUpdate(nextState, definition, featureKey, payload);
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character feature state payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

export function applyCharacterSessionRest(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
  definition: Record<string, unknown>,
  restType: string,
  payload: Record<string, unknown>,
  updatedByUserId: number,
): CharacterSessionRestApplyResult {
  let normalizedRest: "short" | "long";
  let expectedRevision: number;
  let hitDiceCurrentValues: Map<number, unknown> | null;
  try {
    normalizedRest = normalizeRestType(restType);
    expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    hitDiceCurrentValues = normalizeHitDiceCurrentPayload(payload);
  } catch (error) {
    return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character rest payload." };
  }

  const database = openDatabase(config);
  if (!database) {
    return { status: "validation_error", message: "Character state store is not available." };
  }

  try {
    if (!tableExists(database, "character_state")) {
      return { status: "validation_error", message: "Character state store is not available." };
    }

    let existingState = readCharacterState(database, campaignSlug, characterSlug);
    const stateRowMissing = !existingState;
    existingState ??= { revision: 1, state: buildInitialState(definition) };

    if (existingState.revision !== expectedRevision) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }

    let nextState = modeledRestState(existingState.state, normalizedRest, definition);
    try {
      if (hasSubmittedValue(payload.current_hp)) {
        applyVitalsUpdate(nextState, { current_hp: payload.current_hp });
      }
      if (hitDiceCurrentValues && !isXianxiaDefinition(definition)) {
        nextState = applyHitDiceCurrentValues(definition, nextState, hitDiceCurrentValues);
      }
    } catch (error) {
      return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character rest payload." };
    }

    const now = utcIsoTimestamp();
    if (stateRowMissing) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
      return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }

    const result = database
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
      .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
    if (result.changes <= 0) {
      return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
    }
    return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
  } finally {
    database.close();
  }
}

function mergeXianxiaStateWithDefinition(
  definition: Record<string, unknown>,
  existingState: Record<string, unknown>,
): Record<string, unknown> {
  const initialState = buildXianxiaInitialState(definition);
  const payload: Record<string, unknown> = { ...existingState };
  payload.status = asString(payload.status) || asString(definition.status) || "active";
  payload.resources = [];
  payload.spell_slots = [];
  payload.inventory = Array.isArray(payload.inventory) ? payload.inventory : initialState.inventory;
  payload.currency = Object.keys(asRecord(payload.currency)).length > 0 ? asRecord(payload.currency) : initialState.currency;
  payload.attunement = {
    max_attuned_items: nonNegativeInt(asRecord(payload.attunement).max_attuned_items, 3),
    attuned_item_refs: asArray(asRecord(payload.attunement).attuned_item_refs),
  };
  payload.notes = normalizeNotes(payload.notes);
  payload.xianxia = normalizeXianxiaStateFromShared(definition, payload);
  const xianxiaVitals = asRecord(asRecord(payload.xianxia).vitals);
  payload.vitals = {
    current_hp: asInt(xianxiaVitals.current_hp, 0),
    temp_hp: asInt(xianxiaVitals.temp_hp, 0),
  };
  delete payload.hit_dice;
  return payload;
}

export function persistCharacterStateForDefinition(
  config: ApiConfig,
  definition: Record<string, unknown>,
): CharacterStatePersistenceResult {
  const identity = characterIdentity(definition);
  if (!identity) {
    return { stateCreated: false };
  }
  const database = openDatabase(config);
  if (!database) {
    return { stateCreated: false };
  }
  try {
    if (!tableExists(database, "character_state")) {
      return { stateCreated: false };
    }

    const existingState = readCharacterState(database, identity.campaignSlug, identity.characterSlug);
    const now = utcIsoTimestamp();
    if (!existingState) {
      database
        .prepare(
          `
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(identity.campaignSlug, identity.characterSlug, 1, JSON.stringify(buildInitialState(definition)), now, null);
      return { stateCreated: true };
    }

    if (normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE) {
      const mergedState = mergeXianxiaStateWithDefinition(definition, existingState.state);
      if (JSON.stringify(mergedState) !== JSON.stringify(existingState.state)) {
        database
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
          .run(
            JSON.stringify(mergedState),
            now,
            null,
            identity.campaignSlug,
            identity.characterSlug,
            existingState.revision,
          );
      }
    }

    return { stateCreated: false };
  } finally {
    database.close();
  }
}

export function deleteCharacterPersistence(
  config: ApiConfig,
  campaignSlug: string,
  characterSlug: string,
): DeletedCharacterPersistenceResult {
  const database = openDatabase(config);
  if (!database) {
    return { deletedState: false, deletedAssignment: false };
  }
  try {
    const deletedState = tableExists(database, "character_state")
      ? database
          .prepare("DELETE FROM character_state WHERE campaign_slug = ? AND character_slug = ?")
          .run(campaignSlug, characterSlug).changes > 0
      : false;
    const deletedAssignment = tableExists(database, "character_assignments")
      ? database
          .prepare("DELETE FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?")
          .run(campaignSlug, characterSlug).changes > 0
      : false;
    return { deletedState, deletedAssignment };
  } finally {
    database.close();
  }
}
