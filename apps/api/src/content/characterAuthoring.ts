import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";

type SqliteDatabase = InstanceType<typeof Database>;

interface SystemsSourceAccessRow {
  source_id: string;
  configured_enabled: number | null;
  configured_visibility: string | null;
}

interface SystemsEntryRow {
  library_slug: string;
  source_id: string;
  entry_key: string;
  entry_type: string;
  slug: string;
  title: string;
  metadata_json: string;
  body_json: string;
  is_enabled_override: number | null;
}

const XIANXIA_ATTRIBUTE_KEYS = ["str", "dex", "con", "int", "wis", "cha"] as const;
const XIANXIA_ATTRIBUTE_LABELS: Record<(typeof XIANXIA_ATTRIBUTE_KEYS)[number], string> = {
  str: "Strength",
  dex: "Dexterity",
  con: "Constitution",
  int: "Intelligence",
  wis: "Wisdom",
  cha: "Charisma",
};
const XIANXIA_EFFORT_KEYS = ["basic", "weapon", "guns_explosive", "magic", "ultimate"] as const;
const XIANXIA_EFFORT_LABELS: Record<(typeof XIANXIA_EFFORT_KEYS)[number], string> = {
  basic: "Basic",
  weapon: "Weapon",
  guns_explosive: "Guns/Explosive",
  magic: "Magic",
  ultimate: "Ultimate",
};
const XIANXIA_ENERGY_KEYS = ["jing", "qi", "shen"] as const;
const XIANXIA_CURRENCY_KEYS = ["coin", "supply", "spirit_stones"] as const;
const XIANXIA_DEFINITION_FIELD_KEYS = [
  "schema_version",
  "realm",
  "actions_per_turn",
  "honor",
  "reputation",
  "attributes",
  "efforts",
  "energies",
  "yin_yang",
  "dao",
  "insight",
  "durability",
  "skills",
  "equipment",
  "martial_arts",
  "generic_techniques",
  "variants",
  "dao_immolating_techniques",
  "approval_requests",
  "companions",
  "advancement_history",
] as const;
const XIANXIA_MARTIAL_ART_IMPORT_RANKS = [
  { key: "initiate", label: "Initiate" },
  { key: "novice", label: "Novice" },
  { key: "apprentice", label: "Apprentice" },
  { key: "master", label: "Master" },
  { key: "legendary", label: "Legendary" },
] as const;
const XIANXIA_MARTIAL_ART_RANK_ORDER = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key);
const XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS = Object.fromEntries(
  XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => [rank.key, rank.label]),
) as Record<string, string>;
const XIANXIA_REALM_ACTIONS: Record<string, number> = {
  mortal: 2,
  immortal: 3,
  divine: 4,
};
const XIANXIA_ITEM_TYPE_DEFAULT = "Miscellaneous";
const XIANXIA_ITEM_TYPE_ALIASES: Record<string, string> = {
  weapon: "Weapon",
  weapons: "Weapon",
  blade: "Weapon",
  blade_weapon: "Weapon",
  armor: "Armor",
  armour: "Armor",
  armors: "Armor",
  armours: "Armor",
  artifact: "Artifact",
  artifacts: "Artifact",
  relic: "Artifact",
  relics: "Artifact",
  consumable: "Consumable",
  consumables: "Consumable",
  tool: "Miscellaneous",
  tools: "Miscellaneous",
  treasure: "Miscellaneous",
  misc: "Miscellaneous",
  miscellaneous: "Miscellaneous",
  misc_item: "Miscellaneous",
};
const XIANXIA_ITEM_NATURE_ALIASES: Record<string, string> = {
  mundane: "Mundane",
  relic: "Relic",
  relics: "Relic",
  re_lic: "Relic",
};
const XIANXIA_INVENTORY_TAG_TYPE_ALIASES: Record<string, string> = {
  weapon: "Weapon",
  weapons: "Weapon",
  blade: "Weapon",
  blade_weapon: "Weapon",
  armor: "Armor",
  armour: "Armor",
  armors: "Armor",
  armours: "Armor",
  artifact: "Artifact",
  artifacts: "Artifact",
  relic: "Artifact",
  relics: "Artifact",
  consumable: "Consumable",
  consumables: "Consumable",
  treasure: "Miscellaneous",
  tool: "Miscellaneous",
  tools: "Miscellaneous",
  equipment: "Miscellaneous",
};
const XIANXIA_MANUAL_IMPORTER_SOURCE_PATH = "importer://xianxia-manual";
const XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE = "xianxia_manual_importer";
const XIANXIA_MANUAL_IMPORTER_VERSION = "2026-05-13.0";
const XIANXIA_MANUAL_IMPORTER_IMPORTED_FROM = "Manual Xianxia character importer";
const XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS = new Set(["cultivation", "meditation", "conditioning", "training"]);
const NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE =
  "This campaign can still use the character roster, read-mode sheets, session-mode sheets, and Controls. Native DND-5E builder, edit, level-up, repair, retraining, PDF-import, and spellcasting tools are not implemented for this campaign system.";

export interface XianxiaManualImportBuildResult {
  definition: Record<string, unknown>;
  importMetadata: Record<string, unknown>;
  initialState: Record<string, unknown>;
  preview: Record<string, unknown>;
}

function normalizeSystemKey(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

export function nativeCharacterCreateLane(system: unknown): "dnd5e" | "xianxia" | "" {
  const systemKey = normalizeSystemKey(system);
  if (systemKey === "dnd5e") {
    return "dnd5e";
  }
  if (systemKey === "xianxia") {
    return "xianxia";
  }
  return "";
}

export function nativeCharacterCreateUnsupportedMessage(_system: unknown): string {
  return NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE;
}

function campaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function flaskCampaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}

export function buildCharacterAuthoringLinks(campaign: CampaignViewModel) {
  const campaignSlug = campaign.slug;
  const links: Record<string, string> = {
    flask_roster_url: flaskCampaignHref(campaignSlug, "characters"),
    gen2_roster_url: campaignHref(campaignSlug, "characters"),
    flask_create_character_url: flaskCampaignHref(campaignSlug, "characters/new"),
    create_character_url: campaignHref(campaignSlug, "characters/new"),
    flask_create_url: flaskCampaignHref(campaignSlug, "characters/new"),
    gen2_create_url: campaignHref(campaignSlug, "characters/new"),
  };
  if (nativeCharacterCreateLane(campaign.system) === "xianxia") {
    links.flask_import_xianxia_url = flaskCampaignHref(campaignSlug, "characters/import/xianxia-manual");
    links.import_xianxia_url = campaignHref(campaignSlug, "characters/import/xianxia-manual");
    links.gen2_import_xianxia_url = campaignHref(campaignSlug, "characters/import/xianxia-manual");
  }
  return links;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function parseJsonRecord(rawValue: string): Record<string, unknown> {
  try {
    return asRecord(JSON.parse(rawValue || "{}"));
  } catch {
    return {};
  }
}

function sourceSeeds(campaignConfig: Record<string, unknown>): Map<string, { enabled: boolean }> {
  const seeds = new Map<string, { enabled: boolean }>();
  for (const rawSource of asArray(campaignConfig.systems_sources)) {
    const source = asRecord(rawSource);
    const sourceId = String(source.source_id || "").trim();
    if (!sourceId) {
      continue;
    }
    seeds.set(sourceId, { enabled: Boolean(source.enabled) });
  }
  return seeds;
}

function campaignCustomSourceId(campaignSlug: string): string {
  const normalized = String(campaignSlug || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/\//g, "-")
    .toUpperCase();
  return `CUSTOM-${normalized || "CAMPAIGN"}`;
}

function loadEnabledSourceIds(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
): string[] {
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug) {
    return [];
  }
  const seeds = sourceSeeds(campaignConfig);
  const rows = database
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
        ORDER BY LOWER(systems_sources.title), systems_sources.source_id
      `,
    )
    .all(campaign.slug, librarySlug) as SystemsSourceAccessRow[];

  return rows
    .filter((row) => {
      const configured = row.configured_enabled !== null || Boolean(row.configured_visibility);
      return configured ? Boolean(row.configured_enabled) : Boolean(seeds.get(row.source_id)?.enabled);
    })
    .map((row) => row.source_id);
}

function loadEnabledSystemsEntryRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  entryType: string,
): SystemsEntryRow[] {
  const enabledSourceIds = loadEnabledSourceIds(database, campaign, campaignConfig);
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug || enabledSourceIds.length === 0) {
    return [];
  }
  const placeholders = enabledSourceIds.map(() => "?").join(", ");
  return database
    .prepare(
      `
        SELECT
          systems_entries.library_slug,
          systems_entries.source_id,
          systems_entries.entry_key,
          systems_entries.entry_type,
          systems_entries.slug,
          systems_entries.title,
          systems_entries.metadata_json,
          systems_entries.body_json,
          campaign_entry_overrides.is_enabled_override AS is_enabled_override
        FROM systems_entries
        LEFT JOIN campaign_entry_overrides
          ON campaign_entry_overrides.campaign_slug = ?
         AND campaign_entry_overrides.library_slug = systems_entries.library_slug
         AND campaign_entry_overrides.entry_key = systems_entries.entry_key
        WHERE systems_entries.library_slug = ?
          AND systems_entries.source_id IN (${placeholders})
          AND LOWER(systems_entries.entry_type) = ?
        ORDER BY LOWER(systems_entries.title), systems_entries.source_id
      `,
    )
    .all(campaign.slug, librarySlug, ...enabledSourceIds, entryType.toLowerCase()) as SystemsEntryRow[];
}

function loadEnabledMartialArtRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
): SystemsEntryRow[] {
  return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "martial_art");
}

function normalizeRankKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function normalizeMartialArtOptionSlug(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeGenericTechniqueKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function firstPresent(...values: unknown[]): unknown {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return "";
}

function martialArtRankRecords(metadata: Record<string, unknown>, body: Record<string, unknown>) {
  const martialArtBody = asRecord(body.xianxia_martial_art);
  const rawRecords =
    metadata.xianxia_martial_art_rank_records ??
    metadata.martial_art_rank_records ??
    martialArtBody.xianxia_martial_art_rank_records ??
    martialArtBody.rank_records;
  return asArray(rawRecords)
    .map(asRecord)
    .filter((record) => record.rank_available_in_seed !== false)
    .map((record) => ({ ...record, rank_key: normalizeRankKey(record.rank_key) }))
    .filter((record) => Boolean(XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[String(record.rank_key || "")])) as Array<
    Record<string, unknown> & { rank_key: string }
  >;
}

function truthy(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}

function buildXianxiaMartialArtOption(row: SystemsEntryRow, customSourceId: string) {
  const metadata = parseJsonRecord(row.metadata_json);
  const body = parseJsonRecord(row.body_json);
  const martialArtBody = asRecord(body.xianxia_martial_art);
  const rankRecords = martialArtRankRecords(metadata, body);
  let rankRefs = Object.fromEntries(
    rankRecords
      .map((record) => [String(record.rank_key || ""), String(record.rank_ref || "").trim()])
      .filter(([rankKey, rankRef]) => rankKey && rankRef),
  ) as Record<string, string>;
  let availableRankKeys = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key).filter((rankKey) => rankKey in rankRefs);
  const customMartialArt =
    truthy(metadata.xianxia_custom_martial_art) ||
    truthy(metadata.custom_martial_art) ||
    truthy(martialArtBody.xianxia_custom_martial_art) ||
    (customSourceId && row.source_id.toLowerCase() === customSourceId.toLowerCase());
  if (customMartialArt && availableRankKeys.length === 0) {
    availableRankKeys = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key);
    rankRefs = Object.fromEntries(availableRankKeys.map((rankKey) => [rankKey, `xianxia:${row.slug}:${rankKey}`]));
  }

  const rawSortOrder = metadata.martial_art_catalog_order;
  const parsedSortOrder = Number(rawSortOrder);
  return {
    slug: normalizeMartialArtOptionSlug(row.slug),
    title: String(row.title || "").trim(),
    entry_key: String(row.entry_key || "").trim(),
    entry_type: String(row.entry_type || "").trim(),
    source_id: String(row.source_id || "").trim(),
    library_slug: String(row.library_slug || "").trim(),
    martial_art_style: String(
      firstPresent(
        metadata.xianxia_martial_art_style,
        metadata.martial_art_style,
        martialArtBody.style,
        martialArtBody.martial_art_style,
      ),
    ).trim(),
    available_rank_keys: availableRankKeys,
    available_rank_labels: availableRankKeys
      .map((rankKey) => XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[rankKey])
      .filter(Boolean),
    available_starting_rank_keys: ["initiate", "novice"].filter((rankKey) => rankKey in rankRefs),
    rank_refs: rankRefs,
    rank_records_status: String(metadata.rank_records_status || "").trim(),
    custom_martial_art: customMartialArt,
    sort_order: Number.isFinite(parsedSortOrder) ? Math.trunc(parsedSortOrder) : 10000,
  };
}

function xianxiaGenericTechniqueSortOrder(metadata: Record<string, unknown>, techniqueBody: Record<string, unknown>): number {
  const parsed = Number(
    firstPresent(metadata.generic_technique_catalog_order, metadata.catalog_order, techniqueBody.catalog_order),
  );
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 10000;
}

function buildXianxiaGenericTechniqueOption(row: SystemsEntryRow, selectedEntryKeys: Set<string>) {
  const metadata = parseJsonRecord(row.metadata_json);
  const body = parseJsonRecord(row.body_json);
  const techniqueBody = asRecord(body.xianxia_generic_technique);
  const genericTechniqueKey = normalizeGenericTechniqueKey(
    firstPresent(metadata.generic_technique_key, metadata.xianxia_generic_technique_key, techniqueBody.key),
  );
  const entryKey = String(row.entry_key || "").trim();
  if (!entryKey || !genericTechniqueKey || XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS.has(genericTechniqueKey)) {
    return null;
  }

  const insightCost = Math.max(0, Number.parseInt(String(firstPresent(metadata.insight_cost, techniqueBody.insight_cost) || "0"), 10) || 0);
  if (insightCost <= 0) {
    return null;
  }

  return {
    name: String(row.title || "").trim() || "Generic Technique",
    entry_key: entryKey,
    systems_ref: {
      library_slug: String(row.library_slug || "").trim(),
      source_id: String(row.source_id || "").trim(),
      entry_key: entryKey,
      slug: String(row.slug || "").trim(),
      title: String(row.title || "").trim(),
      entry_type: String(row.entry_type || "").trim(),
    },
    generic_technique_key: genericTechniqueKey,
    insight_cost: insightCost,
    support_state: String(
      firstPresent(
        metadata.support_state,
        metadata.xianxia_support_state,
        techniqueBody.support_state,
        techniqueBody.xianxia_support_state,
      ) || "",
    ).trim(),
    learnable_without_master: truthy(firstPresent(metadata.learnable_without_master, techniqueBody.learnable_without_master)),
    requires_master: truthy(firstPresent(metadata.requires_master, techniqueBody.requires_master)),
    sort_order: xianxiaGenericTechniqueSortOrder(metadata, techniqueBody),
    selected: selectedEntryKeys.has(entryKey.toLowerCase()),
  };
}

export function listXianxiaManualImportMartialArtOptions(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
) {
  if (!campaign.systems_library_slug || !existsSync(dbPath)) {
    return [];
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const customSourceId = campaignCustomSourceId(campaign.slug);
    return loadEnabledMartialArtRows(database, campaign, campaignConfig)
      .filter((row) => row.is_enabled_override !== 0)
      .map((row) => buildXianxiaMartialArtOption(row, customSourceId))
      .sort((left, right) => {
        if (left.sort_order !== right.sort_order) {
          return left.sort_order - right.sort_order;
        }
        const titleComparison = left.title.toLowerCase().localeCompare(right.title.toLowerCase());
        if (titleComparison !== 0) {
          return titleComparison;
        }
        return left.source_id.toLowerCase().localeCompare(right.source_id.toLowerCase());
      });
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return [];
    }
    throw error;
  } finally {
    database.close();
  }
}

export function listXianxiaCreateGenericTechniqueOptions(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  selectedEntryKeys: string[] = [],
) {
  if (!campaign.systems_library_slug || !existsSync(dbPath)) {
    return [];
  }

  const selected = new Set(selectedEntryKeys.map((entryKey) => String(entryKey || "").trim().toLowerCase()).filter(Boolean));
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "generic_technique")
      .filter((row) => row.is_enabled_override !== 0)
      .map((row) => buildXianxiaGenericTechniqueOption(row, selected))
      .filter((option): option is NonNullable<typeof option> => option !== null)
      .sort((left, right) => {
        if (left.sort_order !== right.sort_order) {
          return left.sort_order - right.sort_order;
        }
        const titleComparison = left.name.toLowerCase().localeCompare(right.name.toLowerCase());
        if (titleComparison !== 0) {
          return titleComparison;
        }
        return left.systems_ref.source_id.toLowerCase().localeCompare(right.systems_ref.source_id.toLowerCase());
      });
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return [];
    }
    throw error;
  } finally {
    database.close();
  }
}

function normalizeCharacterAuthoringValues(values: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [String(key), value === null || value === undefined ? "" : String(value)]),
  );
}

function isPresent(value: unknown): boolean {
  return String(value ?? "").trim().length > 0;
}

function coerceInt(value: string, fieldName: string): number {
  const candidate = String(value ?? "").trim();
  if (!candidate) {
    return 0;
  }
  if (!/^[+-]?\d+$/.test(candidate)) {
    throw new Error(`Invalid value for ${fieldName}.`);
  }
  return Number.parseInt(candidate, 10);
}

function coerceLooseInt(value: unknown, defaultValue = 0): number {
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }
  const candidate = String(value ?? "").trim();
  if (!candidate) {
    return defaultValue;
  }
  const parsed = Number.parseInt(candidate, 10);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function nonNegativeLooseInt(value: unknown, defaultValue = 0): number {
  return Math.max(0, coerceLooseInt(value, defaultValue));
}

function normalizeRealm(value: string): string {
  const canonical = String(value || "")
    .trim()
    .toLowerCase();
  if (canonical === "mortal" || canonical === "immortal" || canonical === "divine") {
    return canonical[0].toUpperCase() + canonical.slice(1);
  }
  return "Mortal";
}

function normalizeHonor(value: string): string {
  const canonical = String(value || "").trim().toLowerCase();
  for (const honor of ["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"]) {
    if (honor.toLowerCase() === canonical) {
      return honor;
    }
  }
  return "Honorable";
}

function collectIndexedRows(values: Record<string, string>, prefix: string): Array<Record<string, string>> {
  const rowNumbers = new Set<number>();
  for (const key of Object.keys(values)) {
    const match = key.match(new RegExp(`^${prefix}_(\\d+)_(.+)$`));
    if (match) {
      rowNumbers.add(Number(match[1]));
    }
  }

  return Array.from(rowNumbers)
    .sort((left, right) => left - right)
    .map((rowIndex) => {
      const normalizedRow: Record<string, string> = {};
      const sourceFieldPrefix = `${prefix}_${rowIndex}_`;
      for (const [key, value] of Object.entries(values)) {
        if (key.startsWith(sourceFieldPrefix)) {
          normalizedRow[key.slice(sourceFieldPrefix.length)] = value;
        }
      }
      return normalizedRow;
    });
}

function extractValues(values: Record<string, string>, keys: string[]): string {
  for (const key of keys) {
    const value = values[key];
    if (isPresent(value)) {
      return value;
    }
  }
  return "";
}

function normalizeCharacterName(value: string): string {
  return String(value || "").trim();
}

function slugifyText(value: string): string {
  if (!value.trim()) {
    return "";
  }
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/(^-|-$)+/g, "");
}

function normalizeCharacterSlug(value: string, fallbackSource: string): string {
  return slugifyText(value) || slugifyText(fallbackSource);
}

function countTextRows(value: string): number {
  return String(value || "")
    .split(/\r?\n/)
    .filter((row) => row.trim().length > 0).length;
}

function splitTextLines(value: unknown): string[] {
  return String(value ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function splitPipeRow(value: string): string[] {
  return value
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function lookupKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function humanizeSlug(value: string): string {
  return value
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function parseTags(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  return String(value ?? "")
    .split(/[,|]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeToken(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function parseBoolean(value: unknown): boolean | undefined {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  const normalized = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on", "equipped", "enabled", "used", "recorded"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off", "disabled"].includes(normalized)) {
    return false;
  }
  return undefined;
}

function appendNotesSection(baseNotes: string, title: string, lines: string[]): string {
  const body = lines.map((line) => `- ${line}`).join("\n");
  return [baseNotes.trim(), `## ${title}\n\n${body}`].filter(Boolean).join("\n\n");
}

function buildXianxiaManualImportMartialArtRows(values: Record<string, string>) {
  const rowNumbers = new Set<number>();
  for (const key of Object.keys(values)) {
    const match = key.match(/^martial_art_(\d+)_(slug|name|rank|teacher|breakthrough|notes)$/);
    if (match) {
      rowNumbers.add(Number(match[1]));
    }
  }
  const rowCount = Math.max(3, ...rowNumbers);
  return Array.from({ length: rowCount }, (_, index) => {
    const rowIndex = index + 1;
    return {
      index: rowIndex,
      slug_input_name: `martial_art_${rowIndex}_slug`,
      name_input_name: `martial_art_${rowIndex}_name`,
      rank_input_name: `martial_art_${rowIndex}_rank`,
      teacher_input_name: `martial_art_${rowIndex}_teacher`,
      breakthrough_input_name: `martial_art_${rowIndex}_breakthrough`,
      notes_input_name: `martial_art_${rowIndex}_notes`,
      selected_slug: values[`martial_art_${rowIndex}_slug`] || "",
      name: values[`martial_art_${rowIndex}_name`] || "",
      rank: values[`martial_art_${rowIndex}_rank`] || "",
      teacher: values[`martial_art_${rowIndex}_teacher`] || "",
      breakthrough: values[`martial_art_${rowIndex}_breakthrough`] || "",
      notes: values[`martial_art_${rowIndex}_notes`] || "",
    };
  });
}

export function buildXianxiaManualImportContext({
  dbPath,
  campaign,
  campaignConfig,
  values,
}: {
  dbPath: string;
  campaign: CampaignViewModel;
  campaignConfig: Record<string, unknown>;
  values: Record<string, unknown>;
}) {
  const normalizedValues = normalizeCharacterAuthoringValues(values);
  return {
    values: normalizedValues,
    realm_choices: ["Mortal", "Immortal", "Divine"],
    honor_choices: ["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"],
    martial_art_rank_choices: XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => ({ ...rank })),
    martial_art_rows: buildXianxiaManualImportMartialArtRows(normalizedValues),
    attribute_fields: XIANXIA_ATTRIBUTE_KEYS.map((key) => ({
      key,
      label: XIANXIA_ATTRIBUTE_LABELS[key],
      input_name: `attribute_${key}`,
      value: normalizedValues[`attribute_${key}`] || "0",
    })),
    effort_fields: XIANXIA_EFFORT_KEYS.map((key) => ({
      key,
      label: XIANXIA_EFFORT_LABELS[key],
      input_name: `effort_${key}`,
      value: normalizedValues[`effort_${key}`] || "0",
    })),
    energy_fields: XIANXIA_ENERGY_KEYS.map((key) => ({
      key,
      label: key[0].toUpperCase() + key.slice(1),
      max_input_name: `energy_${key}_max`,
      max_value: normalizedValues[`energy_${key}_max`] || "0",
    })),
    martial_art_options: listXianxiaManualImportMartialArtOptions(dbPath, campaign, campaignConfig),
    preview: null,
  };
}

export function buildXianxiaManualImportPayload(values: Record<string, string>): Record<string, unknown> {
  const ignoredInputs = new Set(["active_stance", "active_aura"]);
  const payload: Record<string, string> = {};
  for (const [key, value] of Object.entries(values)) {
    if (!ignoredInputs.has(key)) {
      payload[key] = value;
    }
  }
  return {
    ...payload,
    energy_maxima: {
      jing: values.energy_jing_max || "",
      qi: values.energy_qi_max || "",
      shen: values.energy_shen_max || "",
    },
    state: {
      xianxia: {
        currency: {
          coin: values.coin || "",
          supply: values.supply || "",
          spirit_stones: values.spirit_stones || "",
        },
        notes: {
          player_notes_markdown: values.player_notes_markdown || "",
        },
      },
    },
  };
}

function xianxiaIntegerMap(values: Record<string, string>, keys: readonly string[], prefix: string): Record<string, number> {
  return Object.fromEntries(keys.map((key) => [key, coerceLooseInt(values[`${prefix}${key}`], 0)]));
}

function parseSkillText(value: unknown): Array<Record<string, string> | string> {
  return splitTextLines(value).map((line) => {
    const parts = splitPipeRow(line);
    if (parts.length <= 1) {
      return parts[0] || "";
    }
    return { name: parts[0], notes: parts[1] };
  });
}

function collectTrainedSkills(values: Record<string, string>): { trainedSkills: string[]; skillNotes: string[] } {
  const rows: Array<Record<string, string> | string> = [
    ...parseSkillText(values.trained_skills_text),
    ...parseSkillText(values.skills_text),
    ...collectIndexedRows(values, "trained_skill"),
  ];
  const seen = new Set<string>();
  const trainedSkills: string[] = [];
  const skillNotes: string[] = [];
  for (const row of rows) {
    if (typeof row === "string") {
      const name = row.trim();
      const key = name.toLowerCase();
      if (name && !seen.has(key)) {
        seen.add(key);
        trainedSkills.push(name);
      }
      continue;
    }
    const name = String(row.name || row.label || row.skill || "").trim();
    const key = name.toLowerCase();
    if (name && !seen.has(key)) {
      seen.add(key);
      trainedSkills.push(name);
    }
    const notes = String(row.notes || row.note || row.description || row.source_notes || row.text || "").trim();
    if (name && notes) {
      skillNotes.push(`${name}: ${notes}`);
    }
  }
  return { trainedSkills, skillNotes };
}

function parseInventoryText(value: unknown): Array<Record<string, unknown>> {
  return splitTextLines(value).map((line) => {
    const parts = splitPipeRow(line);
    const row: Record<string, unknown> = { name: parts[0] || "" };
    if (parts[1]) {
      row.quantity = parts[1];
    }
    if (parts[2]) {
      row.tags = parseTags(parts[2]);
    }
    if (parts[3]) {
      row.notes = parts[3];
    }
    return row;
  });
}

function normalizeInventoryItemType(rawType: unknown, defaultValue = XIANXIA_ITEM_TYPE_DEFAULT): string {
  const normalized = normalizeToken(rawType);
  return normalized ? (XIANXIA_ITEM_TYPE_ALIASES[normalized] ?? defaultValue) : defaultValue;
}

function normalizeInventoryItemNature(rawNature: unknown): string {
  return XIANXIA_ITEM_NATURE_ALIASES[normalizeToken(rawNature)] ?? "Mundane";
}

function normalizeInventoryLegacyTags(
  tags: string[],
  itemType: unknown,
): { itemType: string; tags: string[]; legacyTags: string[] } {
  const explicitType = normalizeInventoryItemType(itemType, "");
  const normalizedTags: string[] = [];
  const legacyTags: string[] = [];
  const inferredTypes = new Set<string>();
  const nonMiscInferredTypes = new Set<string>();
  for (const tag of tags) {
    const normalizedTag = String(tag ?? "").trim();
    if (!normalizedTag) {
      continue;
    }
    normalizedTags.push(normalizedTag);
    const mappedType = XIANXIA_INVENTORY_TAG_TYPE_ALIASES[normalizeToken(normalizedTag)];
    if (mappedType) {
      inferredTypes.add(mappedType);
      if (mappedType !== XIANXIA_ITEM_TYPE_DEFAULT) {
        nonMiscInferredTypes.add(mappedType);
      }
    } else {
      legacyTags.push(normalizedTag);
    }
  }

  if (explicitType) {
    return { itemType: explicitType, tags: normalizedTags, legacyTags };
  }
  if (nonMiscInferredTypes.size === 1) {
    return { itemType: [...nonMiscInferredTypes][0] ?? XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
  }
  if (nonMiscInferredTypes.size > 1) {
    return { itemType: XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
  }
  if (inferredTypes.size === 1) {
    return { itemType: [...inferredTypes][0] ?? XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
  }
  return { itemType: XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
}

function normalizeInventoryRows(values: Record<string, string>): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [
    ...parseInventoryText(values.inventory_text),
    ...collectIndexedRows(values, "manual_item"),
    ...collectIndexedRows(values, "inventory_item"),
  ];
  return rows
    .map<Record<string, unknown> | null>((row) => {
      const name = String(row.name || row.label || "").trim();
      const id = String(row.id || row.item_id || "").trim() || slugifyText(name);
      if (!name && !id) {
        return null;
      }
      const tags = parseTags(row.tags);
      const tagNormalization = normalizeInventoryLegacyTags(tags, row.item_type || row.type);
      const itemType = tagNormalization.itemType;
      const itemNature = normalizeInventoryItemNature(row.item_nature || row.nature);
      const explicitEquippable = parseBoolean(row.equippable);
      const isEquipped = parseBoolean(row.is_equipped);
      const normalized: Record<string, unknown> = {
        id,
        catalog_ref: String(row.catalog_ref || "").trim(),
        name,
        quantity: Math.max(0, coerceLooseInt(row.quantity, 1)),
        notes: String(row.notes || row.note || "").trim(),
        tags: tagNormalization.tags,
        item_type: itemType,
        item_nature: itemNature,
        equippable: explicitEquippable ?? (itemType === "Weapon" || itemType === "Armor"),
        is_equipped: isEquipped ?? false,
      };
      if (tagNormalization.legacyTags.length > 0) {
        normalized.legacy_tags = tagNormalization.legacyTags;
      }
      return normalized;
    })
    .filter((row): row is Record<string, unknown> => Boolean(row));
}

function martialArtOptionLookup(options: Array<Record<string, unknown>>): Map<string, Record<string, unknown>> {
  const lookup = new Map<string, Record<string, unknown>>();
  for (const option of options) {
    for (const key of [option.slug, option.title, option.entry_key]) {
      const normalized = lookupKey(key);
      if (normalized) {
        lookup.set(normalized, option);
      }
    }
  }
  return lookup;
}

function matchMartialArtOption(row: Record<string, string>, lookup: Map<string, Record<string, unknown>>) {
  for (const key of [row.systems_ref_slug, row.martial_art_slug, row.slug, row.entry_key, row.name]) {
    const normalized = lookupKey(key);
    if (normalized && lookup.has(normalized)) {
      return lookup.get(normalized) || null;
    }
  }
  return null;
}

function martialArtSystemsRef(option: Record<string, unknown>): Record<string, string> {
  const ref: Record<string, string> = {};
  for (const key of ["library_slug", "source_id", "entry_key", "slug", "title", "entry_type"]) {
    const value = String(option[key] ?? "").trim();
    if (value) {
      ref[key] = value;
    }
  }
  return ref;
}

function learnedRankRefsForOption(option: Record<string, unknown>, rankKey: string): string[] {
  const normalizedRank = normalizeRankKey(rankKey);
  const rankIndex = (XIANXIA_MARTIAL_ART_RANK_ORDER as readonly string[]).indexOf(normalizedRank);
  if (rankIndex < 0) {
    return [];
  }
  const rankRefs = asRecord(option.rank_refs);
  const slug = String(option.slug || "").trim();
  return XIANXIA_MARTIAL_ART_RANK_ORDER.slice(0, rankIndex + 1)
    .map((rank) => String(rankRefs[rank] || (slug ? `xianxia:${slug}:${rank}` : "")).trim())
    .filter(Boolean);
}

function collectMartialArts(values: Record<string, string>, options: Array<Record<string, unknown>>): Record<string, unknown>[] {
  const lookup = martialArtOptionLookup(options);
  return collectIndexedRows(values, "martial_art")
    .map((row) => {
      const selectedOption = matchMartialArtOption(row, lookup);
      const name = String(row.name || row.label || row.title || selectedOption?.title || "").trim();
      if (!name) {
        return null;
      }
      const rankKey = normalizeRankKey(row.current_rank_key || row.current_rank || row.rank || row.rank_key || "");
      const payload: Record<string, unknown> = {
        name: selectedOption ? String(selectedOption.title || name).trim() : name,
      };
      if (selectedOption) {
        payload.systems_ref = martialArtSystemsRef(selectedOption);
        const rankStatus = String(selectedOption.rank_records_status || "").trim();
        if (rankStatus) {
          payload.rank_records_status = rankStatus;
        }
        if (selectedOption.custom_martial_art === true) {
          payload.custom_martial_art = true;
          payload.xianxia_custom_martial_art = true;
        }
      }
      if (rankKey) {
        payload.current_rank_key = rankKey;
        payload.current_rank = XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[rankKey] || humanizeSlug(rankKey);
        if (selectedOption) {
          payload.learned_rank_refs = learnedRankRefsForOption(selectedOption, rankKey);
        }
      }
      for (const key of ["teacher", "breakthrough", "notes"]) {
        const value = String(row[key] || "").trim();
        if (value) {
          payload[key] = value;
        }
      }
      return payload;
    })
    .filter((row): row is Record<string, unknown> => Boolean(row));
}

function buildXianxiaInitialState(
  definition: Record<string, unknown>,
  inventory: Record<string, unknown>[],
  currency: Record<string, number>,
  playerNotesMarkdown: string,
): Record<string, unknown> {
  const xianxia = asRecord(definition.xianxia);
  const durability = asRecord(xianxia.durability);
  const energies = asRecord(xianxia.energies);
  const yinYang = asRecord(xianxia.yin_yang);
  const dao = asRecord(xianxia.dao);
  const hpMax = nonNegativeLooseInt(durability.hp_max, 10);
  const stanceMax = nonNegativeLooseInt(durability.stance_max, 10);
  const xianxiaState = {
    schema_version: 1,
    vitals: {
      current_hp: hpMax,
      temp_hp: 0,
      current_stance: stanceMax,
      temp_stance: 0,
    },
    energies: Object.fromEntries(
      XIANXIA_ENERGY_KEYS.map((key) => [key, { current: nonNegativeLooseInt(asRecord(energies[key]).max, 0) }]),
    ),
    yin_yang: {
      yin_current: nonNegativeLooseInt(yinYang.yin_max, 1),
      yang_current: nonNegativeLooseInt(yinYang.yang_max, 1),
    },
    dao: {
      current: 0,
    },
    currency,
    inventory: {
      enabled: inventory.length > 0,
      quantities: inventory,
    },
    notes: {
      player_notes_markdown: playerNotesMarkdown,
    },
  };
  return {
    status: String(definition.status || "active"),
    vitals: {
      current_hp: hpMax,
      temp_hp: 0,
    },
    resources: [],
    inventory,
    currency: { cp: 0, sp: 0, ep: 0, gp: 0, pp: 0, other: [] },
    spell_slots: [],
    attunement: { max_attuned_items: 3, attuned_item_refs: [] },
    notes: {
      player_notes_markdown: playerNotesMarkdown,
      physical_description_markdown: "",
      background_markdown: "",
      session_notes: [],
    },
    xianxia: xianxiaState,
  };
}

function buildPreviewFromXianxiaImport(definition: Record<string, unknown>, initialState: Record<string, unknown>) {
  const xianxia = asRecord(definition.xianxia);
  const xianxiaState = asRecord(initialState.xianxia);
  const vitals = asRecord(xianxiaState.vitals);
  const inventory = asRecord(xianxiaState.inventory);
  return {
    name: String(definition.name || ""),
    slug: String(definition.character_slug || ""),
    realm: xianxia.realm,
    actions_per_turn: xianxia.actions_per_turn,
    trained_skill_count: asArray(asRecord(xianxia.skills).trained).length,
    martial_art_count: asArray(xianxia.martial_arts).length,
    inventory_count: asArray(inventory.quantities).length,
    hp: vitals.current_hp,
    hp_max: asRecord(xianxia.durability).hp_max,
    stance: vitals.current_stance,
    stance_max: asRecord(xianxia.durability).stance_max,
  };
}

function isWholeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function requireExactInt(errors: string[], path: string, value: unknown, expected: number): void {
  if (!isWholeNumber(value)) {
    errors.push(`${path} must be a whole number.`);
    return;
  }
  if (value !== expected) {
    errors.push(`${path} must be ${expected}.`);
  }
}

function requireNonNegativeInt(errors: string[], path: string, value: unknown): void {
  if (!isWholeNumber(value)) {
    errors.push(`${path} must be a whole number.`);
    return;
  }
  if (value < 0) {
    errors.push(`${path} cannot be negative.`);
  }
}

function validateIntKeyMap(errors: string[], path: string, value: unknown, keys: readonly string[]): void {
  const record = asRecord(value);
  if (Object.keys(record).length === 0 && (typeof value !== "object" || value === null || Array.isArray(value))) {
    errors.push(`${path} must be an object.`);
    return;
  }
  for (const key of keys) {
    requireNonNegativeInt(errors, `${path}.${key}`, record[key]);
  }
  const unknown = Object.keys(record).filter((key) => !keys.includes(key)).sort();
  if (unknown.length > 0) {
    errors.push(`${path} uses unsupported keys: ${unknown.join(", ")}.`);
  }
}

function validateEnergyMaxima(errors: string[], value: unknown): void {
  const energies = asRecord(value);
  if (Object.keys(energies).length === 0 && (typeof value !== "object" || value === null || Array.isArray(value))) {
    errors.push("xianxia.energies must be an object.");
    return;
  }
  for (const key of XIANXIA_ENERGY_KEYS) {
    const energy = asRecord(energies[key]);
    if (Object.keys(energy).length === 0 && (typeof energies[key] !== "object" || energies[key] === null || Array.isArray(energies[key]))) {
      errors.push(`xianxia.energies.${key} must be an object.`);
      continue;
    }
    requireNonNegativeInt(errors, `xianxia.energies.${key}.max`, energy.max);
    const unknown = Object.keys(energy).filter((energyKey) => energyKey !== "max").sort();
    if (unknown.length > 0) {
      errors.push(`xianxia.energies.${key} uses unsupported keys: ${unknown.join(", ")}.`);
    }
  }
  const unknown = Object.keys(energies).filter((key) => !(XIANXIA_ENERGY_KEYS as readonly string[]).includes(key)).sort();
  if (unknown.length > 0) {
    errors.push(`xianxia.energies uses unsupported keys: ${unknown.join(", ")}.`);
  }
}

function validateRecordList(errors: string[], path: string, value: unknown): void {
  if (!Array.isArray(value)) {
    errors.push(`${path} must be a list.`);
    return;
  }
  value.forEach((item, index) => {
    if (typeof item !== "object" || item === null || Array.isArray(item)) {
      errors.push(`${path}[${index}] must be an object.`);
    }
  });
}

function validateXianxiaManualImportDefinition(definition: Record<string, unknown>): void {
  const errors: string[] = [];
  const xianxia = asRecord(definition.xianxia);
  const fieldKeys = Object.keys(xianxia);
  if (fieldKeys.join("|") !== XIANXIA_DEFINITION_FIELD_KEYS.join("|")) {
    errors.push(`xianxia must use the stable definition field order: ${XIANXIA_DEFINITION_FIELD_KEYS.join(", ")}.`);
  }

  requireExactInt(errors, "xianxia.schema_version", xianxia.schema_version, 1);
  const realm = String(xianxia.realm || "");
  if (!["Mortal", "Immortal", "Divine"].includes(realm)) {
    errors.push("xianxia.realm must be one of: Mortal, Immortal, Divine.");
  }
  requireNonNegativeInt(errors, "xianxia.actions_per_turn", xianxia.actions_per_turn);
  const expectedActions = XIANXIA_REALM_ACTIONS[realm.toLowerCase()];
  if (expectedActions !== undefined && xianxia.actions_per_turn !== expectedActions) {
    errors.push(`xianxia.actions_per_turn must match the ${realm} realm default of ${expectedActions}.`);
  }
  if (!["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"].includes(String(xianxia.honor || ""))) {
    errors.push("xianxia.honor must be one of: Venerable, Majestic, Honorable, Disgraced, Demonic.");
  }
  if (!String(xianxia.reputation || "").trim()) {
    errors.push("xianxia.reputation is required.");
  }

  validateIntKeyMap(errors, "xianxia.attributes", xianxia.attributes, XIANXIA_ATTRIBUTE_KEYS);
  validateIntKeyMap(errors, "xianxia.efforts", xianxia.efforts, XIANXIA_EFFORT_KEYS);
  validateEnergyMaxima(errors, xianxia.energies);
  const yinYang = asRecord(xianxia.yin_yang);
  requireNonNegativeInt(errors, "xianxia.yin_yang.yin_max", yinYang.yin_max);
  requireNonNegativeInt(errors, "xianxia.yin_yang.yang_max", yinYang.yang_max);
  const dao = asRecord(xianxia.dao);
  requireExactInt(errors, "xianxia.dao.max", dao.max, 3);
  const insight = asRecord(xianxia.insight);
  requireNonNegativeInt(errors, "xianxia.insight.available", insight.available);
  requireNonNegativeInt(errors, "xianxia.insight.spent", insight.spent);
  const durability = asRecord(xianxia.durability);
  for (const key of ["hp_max", "stance_max", "manual_armor_bonus", "defense"]) {
    requireNonNegativeInt(errors, `xianxia.durability.${key}`, durability[key]);
  }
  const skills = asRecord(xianxia.skills);
  if (!Array.isArray(skills.trained) || skills.trained.some((skill) => !String(skill || "").trim())) {
    errors.push("xianxia.skills.trained must be a list of non-empty strings.");
  }
  const equipment = asRecord(xianxia.equipment);
  validateRecordList(errors, "xianxia.equipment.necessary_weapons", equipment.necessary_weapons);
  validateRecordList(errors, "xianxia.equipment.necessary_tools", equipment.necessary_tools);
  for (const path of [
    "martial_arts",
    "generic_techniques",
    "variants",
    "approval_requests",
    "companions",
    "advancement_history",
  ]) {
    validateRecordList(errors, `xianxia.${path}`, xianxia[path]);
  }

  if (errors.length > 0) {
    throw new Error(errors.join(" "));
  }
}

export function buildXianxiaManualImportCharacter({
  campaignSlug,
  values,
  martialArtOptions,
}: {
  campaignSlug: string;
  values: Record<string, string>;
  martialArtOptions: Array<Record<string, unknown>>;
}): XianxiaManualImportBuildResult {
  const importPayload = buildXianxiaManualImportPayload(values);
  const normalizedValues = normalizeCharacterAuthoringValues(importPayload as Record<string, unknown>);
  const name = normalizeCharacterName(values.name || values.character_name || values.title || "");
  if (!name) {
    throw new Error("character name is required.");
  }
  const characterSlug = normalizeCharacterSlug(values.character_slug || values.slug || "", name);
  if (!characterSlug) {
    throw new Error("character_slug is required.");
  }

  const realm = normalizeRealm(values.realm);
  const honor = normalizeHonor(values.honor);
  const attributes = xianxiaIntegerMap(normalizedValues, XIANXIA_ATTRIBUTE_KEYS, "attribute_");
  const efforts = xianxiaIntegerMap(normalizedValues, XIANXIA_EFFORT_KEYS, "effort_");
  const energies = Object.fromEntries(
    XIANXIA_ENERGY_KEYS.map((key) => [key, { max: coerceLooseInt(values[`energy_${key}_max`], 0) }]),
  );
  const yinMax = coerceLooseInt(values.yin_max, 1);
  const yangMax = coerceLooseInt(values.yang_max, 1);
  const daoMax = coerceLooseInt(values.dao_max, 3);
  const hpMax = coerceLooseInt(values.hp_max, 10);
  const stanceMax = coerceLooseInt(values.stance_max, 10);
  const manualArmorBonus = coerceLooseInt(values.manual_armor_bonus, 0);
  const { trainedSkills, skillNotes } = collectTrainedSkills(values);
  const martialArts = collectMartialArts(values, martialArtOptions);
  const inventory = normalizeInventoryRows(values);
  const currency = Object.fromEntries(
    XIANXIA_CURRENCY_KEYS.map((key) => [key, nonNegativeLooseInt(values[key], 0)]),
  ) as Record<string, number>;
  const playerNotesMarkdown = String(values.player_notes_markdown || "").trim();
  const additionalNotes = skillNotes.length > 0
    ? appendNotesSection(String(values.additional_notes_markdown || ""), "Imported skill notes", skillNotes)
    : String(values.additional_notes_markdown || "").trim();

  const definition: Record<string, unknown> = {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    name,
    status: values.status || "active",
    system: "Xianxia",
    profile: {
      class_level_text: values.class_level_text || `${realm} Xianxia Character`,
      realm,
      honor,
      reputation: values.reputation || "Unknown",
    },
    stats: {},
    skills: [],
    proficiencies: { armor: [], weapons: [], tools: [], languages: [], tool_expertise: [] },
    attacks: [],
    features: [],
    spellcasting: {},
    equipment_catalog: [],
    reference_notes: {
      additional_notes_markdown: additionalNotes,
      allies_and_organizations_markdown: values.allies_and_organizations_markdown || "",
      custom_sections: [],
    },
    resource_templates: [],
    source: {
      source_path: XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
      source_type: XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE,
      imported_from: XIANXIA_MANUAL_IMPORTER_IMPORTED_FROM,
      imported_at: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
      parse_warnings: [],
    },
    xianxia: {
      schema_version: 1,
      realm,
      actions_per_turn: XIANXIA_REALM_ACTIONS[realm.toLowerCase()],
      honor,
      reputation: values.reputation || "Unknown",
      attributes,
      efforts,
      energies,
      yin_yang: { yin_max: yinMax, yang_max: yangMax },
      dao: { max: daoMax },
      insight: {
        available: coerceLooseInt(values.insight_available, 0),
        spent: coerceLooseInt(values.insight_spent, 0),
      },
      durability: {
        hp_max: hpMax,
        stance_max: stanceMax,
        manual_armor_bonus: manualArmorBonus,
        defense: 10 + manualArmorBonus + coerceLooseInt(attributes.con, 0),
      },
      skills: { trained: trainedSkills },
      equipment: { necessary_weapons: [], necessary_tools: [] },
      martial_arts: martialArts,
      generic_techniques: [],
      variants: [],
      dao_immolating_techniques: { prepared: [], use_history: [] },
      approval_requests: [],
      companions: [],
      advancement_history: [],
    },
  };
  validateXianxiaManualImportDefinition(definition);
  const initialState = buildXianxiaInitialState(definition, inventory, currency, playerNotesMarkdown);
  const importMetadata = {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    source_path: XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
    imported_at_utc: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    parser_version: XIANXIA_MANUAL_IMPORTER_VERSION,
    import_status: "clean",
    warnings: [],
  };
  return {
    definition,
    importMetadata,
    initialState,
    preview: buildPreviewFromXianxiaImport(definition, initialState),
  };
}

export function buildXianxiaManualImportPreview(values: Record<string, string>) {
  if (!normalizeCharacterName(values.name)) {
    throw new Error("character name is required.");
  }

  const normalizedValues = normalizeCharacterAuthoringValues(values);
  const realm = normalizeRealm(values.realm);
  const name = normalizeCharacterName(values.name);
  const slug = normalizeCharacterSlug(values.character_slug || values.slug || "", name);
  const trainedSkills = collectIndexedRows(normalizedValues, "trained_skill");
  const martialArts = collectIndexedRows(normalizedValues, "martial_art");
  const inventoryItems = collectIndexedRows(normalizedValues, "manual_item");
  const additionalInventoryRows = collectIndexedRows(normalizedValues, "inventory_item");

  const trained_skill_count =
    countTextRows(normalizedValues.trained_skills_text || "") +
    trainedSkills.filter((row) => Object.values(row).some(isPresent)).length;
  const martial_art_count = martialArts.filter((row) => Object.values(row).some(isPresent)).length;
  const inventory_count =
    countTextRows(normalizedValues.inventory_text || "") +
    inventoryItems.filter((row) => Object.values(row).some(isPresent)).length +
    additionalInventoryRows.filter((row) => Object.values(row).some(isPresent)).length;

  const hp_max = coerceInt(extractValues(normalizedValues, ["hp_max", "durability_hp_max", "max_hp"]), "hp_max");
  const stance_max = coerceInt(extractValues(normalizedValues, ["stance_max", "durability_stance_max"]), "stance_max");

  return {
    name,
    slug,
    realm,
    actions_per_turn: XIANXIA_REALM_ACTIONS[realm.toLowerCase()],
    trained_skill_count,
    martial_art_count,
    inventory_count,
    hp: hp_max,
    hp_max,
    stance: stance_max,
    stance_max,
  };
}
