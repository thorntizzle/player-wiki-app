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
const XIANXIA_MARTIAL_ART_IMPORT_RANKS = [
  { key: "initiate", label: "Initiate" },
  { key: "novice", label: "Novice" },
  { key: "apprentice", label: "Apprentice" },
  { key: "master", label: "Master" },
  { key: "legendary", label: "Legendary" },
] as const;
const XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS = Object.fromEntries(
  XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => [rank.key, rank.label]),
) as Record<string, string>;
const XIANXIA_REALM_ACTIONS: Record<string, number> = {
  mortal: 2,
  immortal: 3,
  divine: 4,
};
const NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE =
  "This campaign can still use the character roster, read-mode sheets, session-mode sheets, and Controls. Native DND-5E builder, edit, level-up, repair, retraining, PDF-import, and spellcasting tools are not implemented for this campaign system.";

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
    flask_create_url: flaskCampaignHref(campaignSlug, "characters/new"),
    gen2_create_url: campaignHref(campaignSlug, "characters/new"),
  };
  if (nativeCharacterCreateLane(campaign.system) === "xianxia") {
    links.flask_import_xianxia_url = flaskCampaignHref(campaignSlug, "characters/import/xianxia-manual");
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

function loadEnabledMartialArtRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
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
          AND LOWER(systems_entries.entry_type) = 'martial_art'
        ORDER BY LOWER(systems_entries.title), systems_entries.source_id
      `,
    )
    .all(campaign.slug, librarySlug, ...enabledSourceIds) as SystemsEntryRow[];
}

function normalizeRankKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function normalizeMartialArtOptionSlug(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
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

function normalizeRealm(value: string): string {
  const canonical = String(value || "")
    .trim()
    .toLowerCase();
  if (canonical === "mortal" || canonical === "immortal" || canonical === "divine") {
    return canonical[0].toUpperCase() + canonical.slice(1);
  }
  return "Mortal";
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
