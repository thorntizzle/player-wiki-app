import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";

export type FixtureSystemsRole = "player" | "dm" | "admin";

export interface SystemsLibrary {
  library_slug: string;
  title: string;
  system_code: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SystemsSourceState {
  source_id: string;
  title: string;
  library_slug: string;
  license_class: string;
  license_class_label: string;
  public_visibility_allowed: boolean;
  requires_unofficial_notice: boolean;
  status: string;
  is_enabled: boolean;
  default_visibility: string;
  is_configured: boolean;
  entry_count: number;
  permissions: {
    can_access: boolean;
    can_manage: boolean;
  };
}

export interface SystemsSourceListPayload {
  campaign: CampaignViewModel;
  library: SystemsLibrary | null;
  sources: SystemsSourceState[];
  permissions: {
    can_manage_systems: boolean;
  };
}

export interface SystemsEntrySummary {
  id: number;
  library_slug: string;
  source_id: string;
  entry_key: string;
  entry_type: string;
  entry_type_label: string;
  slug: string;
  title: string;
  source_page: string;
  source_path: string;
  player_safe_default: boolean;
  dm_heavy: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemsEntryOverride {
  entry_key: string;
  visibility_override: string | null;
  is_enabled_override: boolean | null;
  updated_at: string;
  updated_by_user_id: number | null;
}

export interface SystemsEntryRecord extends SystemsEntrySummary {
  metadata: Record<string, unknown>;
  body: unknown;
  rendered_html: string;
  source_state: SystemsSourceState | null;
  override: SystemsEntryOverride | null;
}

export interface SystemsEntryGroup {
  entry_type: string;
  entry_type_label: string;
  count: number;
}

export interface SystemsRulesReferenceResult {
  title: string;
  entry_type: string;
  entry_type_label: string;
  source_id: string;
  slug: string;
  reference_scope: string;
}

export interface SystemsSourceDetailPayload {
  campaign: CampaignViewModel;
  source: SystemsSourceState;
  entry_groups: SystemsEntryGroup[];
  book_entries: SystemsEntrySummary[];
  entry_count: number;
  browsable_entry_count: number;
  hidden_entry_types: string[];
  has_rules_reference_search: boolean;
  rules_reference_search_meta: string;
  rules_reference_scope_note: string;
  reference_query: string;
  rules_reference_results: SystemsRulesReferenceResult[];
  book_visibility_policy_note: string;
  permissions: {
    can_manage_systems: boolean;
  };
}

export type SystemsSourceDetailResult =
  | { status: "ok"; payload: SystemsSourceDetailPayload }
  | { status: "not_found" }
  | { status: "forbidden"; message: string };

export interface SystemsSourceCategoryPayload {
  campaign: CampaignViewModel;
  source: SystemsSourceState;
  entry_groups: SystemsEntryGroup[];
  entry_type: string;
  entry_type_label: string;
  query: string;
  entry_count: number;
  filtered_entry_count: number;
  entries: SystemsEntrySummary[];
  permissions: {
    can_manage_systems: boolean;
  };
}

export type SystemsSourceCategoryResult =
  | { status: "ok"; payload: SystemsSourceCategoryPayload }
  | { status: "not_found" }
  | { status: "forbidden"; message: string };

export interface SystemsEntryDetailPayload {
  campaign: CampaignViewModel;
  entry: SystemsEntryRecord;
  permissions: {
    can_manage_systems: boolean;
  };
  links: {
    flask_entry_url: string;
    flask_source_url: string;
    flask_source_category_url: string;
    dm_content_systems_url: string;
  };
}

export type SystemsEntryDetailResult =
  | { status: "ok"; payload: SystemsEntryDetailPayload }
  | { status: "not_found" }
  | { status: "forbidden"; message: string };

interface SystemsLibraryRow {
  library_slug: string;
  title: string;
  system_code: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface SystemsSourceRow {
  source_id: string;
  title: string;
  library_slug: string;
  license_class: string;
  public_visibility_allowed: number;
  requires_unofficial_notice: number;
  status: string;
  configured_enabled: number | null;
  configured_visibility: string | null;
  entry_count: number;
}

interface SystemsEntryRow {
  id: number;
  library_slug: string;
  source_id: string;
  entry_key: string;
  entry_type: string;
  slug: string;
  title: string;
  source_page: string;
  source_path: string;
  search_text: string;
  player_safe_default: number;
  dm_heavy: number;
  metadata_json: string;
  body_json: string;
  rendered_html: string;
  created_at: string;
  updated_at: string;
}

interface CampaignEntryOverrideRow {
  entry_key: string;
  visibility_override: string | null;
  is_enabled_override: number | null;
  updated_at: string;
  updated_by_user_id: number | null;
}

interface CampaignSourceSeed {
  source_id: string;
  enabled?: boolean;
  default_visibility?: string;
}

const LICENSE_CLASS_LABELS: Record<string, string> = {
  app_reference: "App-authored reference",
  proprietary_private: "Proprietary - private campaign use",
  srd_cc: "SRD - Creative Commons",
  open_license: "Open license",
  custom_campaign: "Custom campaign",
};

const VISIBILITY_VALUES = new Set(["public", "players", "dm", "private"]);
const SYSTEMS_ENTRY_TYPE_LABELS: Record<string, string> = {
  action: "Actions",
  background: "Backgrounds",
  book: "Book Chapters",
  class: "Classes",
  classfeature: "Class Features",
  condition: "Conditions",
  disease: "Diseases",
  feat: "Feats",
  item: "Items",
  monster: "Monsters",
  optionalfeature: "Optional Features",
  race: "Races",
  rule: "Rules",
  sense: "Senses",
  skill: "Skills",
  spell: "Spells",
  status: "Statuses",
  subclass: "Subclasses",
  subclassfeature: "Subclass Features",
  variantrule: "Variant Rules",
  attribute: "Attributes",
  effort: "Efforts",
  energy: "Energies",
  yin_yang: "Yin/Yang",
  dao: "Dao",
  realm: "Realms",
  honor_rank: "Honor Ranks",
  skill_rule: "Skill Rules",
  equipment: "Equipment",
  armor: "Armor",
  martial_art: "Martial Arts",
  martial_art_rank: "Martial Art Ranks",
  technique: "Techniques",
  maneuver: "Maneuvers",
  stance: "Stances",
  aura: "Auras",
  generic_technique: "Generic Techniques",
  basic_action: "Basic Actions",
  karmic_constraint_rule: "Karmic Constraint Rules",
  ascendant_art_rule: "Ascendant Art Rules",
  dao_immolating_rule: "Dao Immolating Rules",
  range_rule: "Range Rules",
  timing_rule: "Timing Rules",
  critical_hit_rule: "Critical Hit Rules",
  sneak_attack_rule: "Sneak Attack Rules",
  dying_rule: "Dying Rules",
  minion_tag: "Minion Tags",
  companion_rule: "Companion Rules",
  gm_approval_rule: "GM Approval Rules",
};
const SYSTEMS_ENTRY_TYPE_ORDER = [
  "book",
  "class",
  "subclass",
  "classfeature",
  "subclassfeature",
  "spell",
  "feat",
  "optionalfeature",
  "item",
  "race",
  "rule",
  "background",
  "action",
  "skill",
  "sense",
  "variantrule",
  "condition",
  "status",
  "disease",
  "monster",
  "basic_action",
  "attribute",
  "effort",
  "energy",
  "yin_yang",
  "dao",
  "realm",
  "honor_rank",
  "skill_rule",
  "equipment",
  "armor",
  "martial_art",
  "martial_art_rank",
  "technique",
  "maneuver",
  "stance",
  "aura",
  "generic_technique",
  "karmic_constraint_rule",
  "ascendant_art_rule",
  "dao_immolating_rule",
  "range_rule",
  "timing_rule",
  "critical_hit_rule",
  "sneak_attack_rule",
  "dying_rule",
  "minion_tag",
  "companion_rule",
  "gm_approval_rule",
] as const;
const SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES = new Set(["classfeature", "optionalfeature", "subclassfeature"]);
const RULES_REFERENCE_ENTRY_TYPES = new Set(["book", "rule"]);

function titleCaseFallback(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(normalized)) {
      return false;
    }
  }
  return undefined;
}

function normalizeVisibility(value: unknown, fallback = "dm"): string {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  return VISIBILITY_VALUES.has(normalized) ? normalized : fallback;
}

function entryTypeLabel(entryType: string): string {
  const normalized = String(entryType || "").trim().toLowerCase();
  return SYSTEMS_ENTRY_TYPE_LABELS[normalized] || titleCaseFallback(normalized.replace(/-/g, " "));
}

function entryTypeSortKey(entryType: string): [number, string] {
  const normalized = String(entryType || "").trim().toLowerCase();
  const index = SYSTEMS_ENTRY_TYPE_ORDER.indexOf(normalized as (typeof SYSTEMS_ENTRY_TYPE_ORDER)[number]);
  return [index >= 0 ? index : SYSTEMS_ENTRY_TYPE_ORDER.length, normalized];
}

function clampVisibilityForSource(source: SystemsSourceRow, visibility: string): string {
  if (visibility === "public" && !Boolean(source.public_visibility_allowed)) {
    return "players";
  }
  return visibility;
}

function parseSourceSeeds(campaignConfig: Record<string, unknown>): Map<string, CampaignSourceSeed> {
  const seeds = new Map<string, CampaignSourceSeed>();
  const rawSources = campaignConfig.systems_sources;
  if (!Array.isArray(rawSources)) {
    return seeds;
  }

  for (const rawSource of rawSources) {
    const record = asRecord(rawSource);
    const sourceId = String(record.source_id || "").trim();
    if (!sourceId) {
      continue;
    }
    seeds.set(sourceId, {
      source_id: sourceId,
      enabled: asBoolean(record.enabled),
      default_visibility: normalizeVisibility(record.default_visibility, ""),
    });
  }
  return seeds;
}

function serializeLibrary(row: SystemsLibraryRow | undefined): SystemsLibrary | null {
  if (!row) {
    return null;
  }
  return {
    library_slug: String(row.library_slug),
    title: String(row.title),
    system_code: String(row.system_code),
    status: String(row.status),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function canManageSystems(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function canAccessSource(role: FixtureSystemsRole, isEnabled: boolean, visibility: string): boolean {
  if (canManageSystems(role)) {
    return true;
  }
  if (!isEnabled) {
    return false;
  }
  return visibility === "public" || visibility === "players";
}

function serializeSourceState(
  row: SystemsSourceRow,
  seed: CampaignSourceSeed | undefined,
  role: FixtureSystemsRole,
): SystemsSourceState {
  const isConfigured = row.configured_enabled !== null || Boolean(row.configured_visibility);
  const seededEnabled = seed?.enabled ?? false;
  const isEnabled = isConfigured ? Boolean(row.configured_enabled) : seededEnabled;
  const fallbackVisibility = seed?.default_visibility || "dm";
  const configuredVisibility = row.configured_visibility || "";
  const defaultVisibility = clampVisibilityForSource(
    row,
    normalizeVisibility(isConfigured ? configuredVisibility : fallbackVisibility, "dm"),
  );
  const canManage = canManageSystems(role);
  const canAccess = canAccessSource(role, isEnabled, defaultVisibility);

  return {
    source_id: String(row.source_id),
    title: String(row.title),
    library_slug: String(row.library_slug),
    license_class: String(row.license_class),
    license_class_label: LICENSE_CLASS_LABELS[row.license_class] || titleCaseFallback(String(row.license_class)),
    public_visibility_allowed: Boolean(row.public_visibility_allowed),
    requires_unofficial_notice: Boolean(row.requires_unofficial_notice),
    status: String(row.status),
    is_enabled: isEnabled,
    default_visibility: defaultVisibility,
    is_configured: isConfigured,
    entry_count: isEnabled ? Number(row.entry_count || 0) : 0,
    permissions: {
      can_access: canAccess,
      can_manage: canManage,
    },
  };
}

function emptyPayload(campaign: CampaignViewModel, canManage: boolean): SystemsSourceListPayload {
  return {
    campaign,
    library: null,
    sources: [],
    permissions: {
      can_manage_systems: canManage,
    },
  };
}

function isNoSuchTableError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("no such table");
}

function parseJsonValue(rawValue: string, fallback: unknown = {}): unknown {
  try {
    return JSON.parse(rawValue || "null") ?? fallback;
  } catch {
    return fallback;
  }
}

function parseMetadata(row: SystemsEntryRow): Record<string, unknown> {
  return asRecord(parseJsonValue(row.metadata_json, {}));
}

function serializeEntrySummary(row: SystemsEntryRow): SystemsEntrySummary {
  return {
    id: Number(row.id),
    library_slug: String(row.library_slug),
    source_id: String(row.source_id),
    entry_key: String(row.entry_key),
    entry_type: String(row.entry_type),
    entry_type_label: entryTypeLabel(row.entry_type),
    slug: String(row.slug),
    title: String(row.title),
    source_page: String(row.source_page || ""),
    source_path: String(row.source_path || ""),
    player_safe_default: Boolean(row.player_safe_default),
    dm_heavy: Boolean(row.dm_heavy),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function serializeEntryOverride(row: CampaignEntryOverrideRow | undefined): SystemsEntryOverride | null {
  if (!row) {
    return null;
  }
  const visibilityOverride = row.visibility_override ? String(row.visibility_override) : null;
  return {
    entry_key: String(row.entry_key),
    visibility_override: visibilityOverride,
    is_enabled_override: row.is_enabled_override === null ? null : Boolean(row.is_enabled_override),
    updated_at: String(row.updated_at),
    updated_by_user_id: row.updated_by_user_id === null ? null : Number(row.updated_by_user_id),
  };
}

function serializeEntryRecord(
  row: SystemsEntryRow,
  sourceState: SystemsSourceState | null,
  override: SystemsEntryOverride | null,
): SystemsEntryRecord {
  return {
    ...serializeEntrySummary(row),
    metadata: parseMetadata(row),
    body: parseJsonValue(row.body_json, {}),
    rendered_html: String(row.rendered_html || ""),
    source_state: sourceState,
    override,
  };
}

function coerceSortableInt(value: unknown, fallback: number): number {
  const parsed = Number.parseInt(String(value || "").trim(), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function entrySourceBrowseSortKey(row: SystemsEntryRow): [number, number, number, number, string, number] {
  const metadata = parseMetadata(row);
  if (row.entry_type === "book") {
    return [
      0,
      coerceSortableInt(metadata.chapter_index, 10_000),
      coerceSortableInt(metadata.target_order, 10_000),
      coerceSortableInt(row.source_page, 10_000),
      String(row.title).toLowerCase(),
      Number(row.id),
    ];
  }
  return [
    1,
    10_000,
    10_000,
    coerceSortableInt(row.source_page, 10_000),
    String(row.title).toLowerCase(),
    Number(row.id),
  ];
}

function compareEntryRowsForBrowse(left: SystemsEntryRow, right: SystemsEntryRow): number {
  const leftKey = entrySourceBrowseSortKey(left);
  const rightKey = entrySourceBrowseSortKey(right);
  for (let index = 0; index < leftKey.length; index += 1) {
    const leftValue = leftKey[index];
    const rightValue = rightKey[index];
    if (typeof leftValue === "number" && typeof rightValue === "number") {
      if (leftValue !== rightValue) {
        return leftValue - rightValue;
      }
    } else {
      const comparison = String(leftValue).localeCompare(String(rightValue));
      if (comparison !== 0) {
        return comparison;
      }
    }
  }
  return 0;
}

function filterAccessibleEntryRows(rows: SystemsEntryRow[], role: FixtureSystemsRole): SystemsEntryRow[] {
  if (canManageSystems(role)) {
    return rows;
  }
  return rows.filter((row) => Boolean(row.player_safe_default) && !Boolean(row.dm_heavy));
}

function buildEntryGroups(rows: SystemsEntryRow[]): SystemsEntryGroup[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const entryType = String(row.entry_type);
    counts.set(entryType, (counts.get(entryType) || 0) + 1);
  }

  const groups = [...counts.entries()].map(([entryType, count]) => ({
    entry_type: entryType,
    entry_type_label: entryTypeLabel(entryType),
    count,
  }));
  groups.sort((left, right) => {
    const leftHidden = SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(left.entry_type) ? 1 : 0;
    const rightHidden = SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(right.entry_type) ? 1 : 0;
    if (leftHidden !== rightHidden) {
      return leftHidden - rightHidden;
    }
    const [leftOrder, leftType] = entryTypeSortKey(left.entry_type);
    const [rightOrder, rightType] = entryTypeSortKey(right.entry_type);
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return leftType.localeCompare(rightType);
  });
  return groups;
}

function entryMatchesCategoryQuery(row: SystemsEntryRow, query: string): boolean {
  const terms = normalizeLookup(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) {
    return true;
  }
  const title = String(row.title || "").toLowerCase();
  const entryType = String(row.entry_type || "").toLowerCase();
  return terms.every((term) => title.includes(term) || entryType.includes(term));
}

function loadAccessibleSourceEntries(
  database: Database.Database,
  librarySlug: string,
  sourceId: string,
  role: FixtureSystemsRole,
  options: {
    entryType?: string;
    query?: string;
  } = {},
): SystemsEntryRow[] {
  const rows = database
    .prepare(
      `
        SELECT
          id,
          library_slug,
          source_id,
          entry_key,
          entry_type,
          slug,
          title,
          source_page,
          source_path,
          search_text,
          player_safe_default,
          dm_heavy,
          metadata_json,
          body_json,
          rendered_html,
          created_at,
          updated_at
        FROM systems_entries
        WHERE library_slug = ?
          AND source_id = ?
        ORDER BY title ASC, id ASC
      `,
    )
    .all(librarySlug, sourceId) as SystemsEntryRow[];
  const normalizedEntryType = String(options.entryType || "").trim().toLowerCase();
  const filteredRows = normalizedEntryType
    ? rows.filter((row) => String(row.entry_type || "").trim().toLowerCase() === normalizedEntryType)
    : rows;
  return filterAccessibleEntryRows(filteredRows, role)
    .filter((row) => entryMatchesCategoryQuery(row, options.query || ""))
    .sort(compareEntryRowsForBrowse);
}

function loadCampaignEntryOverride(
  database: Database.Database,
  campaignSlug: string,
  entryKey: string,
): SystemsEntryOverride | null {
  try {
    return serializeEntryOverride(
      database
        .prepare(
          `
            SELECT
              entry_key,
              visibility_override,
              is_enabled_override,
              updated_at,
              updated_by_user_id
            FROM campaign_entry_overrides
            WHERE campaign_slug = ?
              AND entry_key = ?
          `,
        )
        .get(campaignSlug, entryKey) as CampaignEntryOverrideRow | undefined,
    );
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return null;
    }
    throw error;
  }
}

function loadSourceRow(
  database: Database.Database,
  campaignSlug: string,
  librarySlug: string,
  sourceId: string,
): SystemsSourceRow | undefined {
  return database
    .prepare(
      `
        SELECT
          systems_sources.source_id,
          systems_sources.title,
          systems_sources.library_slug,
          systems_sources.license_class,
          systems_sources.public_visibility_allowed,
          systems_sources.requires_unofficial_notice,
          systems_sources.status,
          campaign_enabled_sources.is_enabled AS configured_enabled,
          campaign_enabled_sources.default_visibility AS configured_visibility,
          (
            SELECT COUNT(*)
            FROM systems_entries
            WHERE systems_entries.library_slug = systems_sources.library_slug
              AND systems_entries.source_id = systems_sources.source_id
          ) AS entry_count
        FROM systems_sources
        LEFT JOIN campaign_enabled_sources
          ON campaign_enabled_sources.campaign_slug = ?
         AND campaign_enabled_sources.library_slug = systems_sources.library_slug
         AND campaign_enabled_sources.source_id = systems_sources.source_id
        WHERE systems_sources.library_slug = ?
          AND systems_sources.source_id = ?
      `,
    )
    .get(campaignSlug, librarySlug, sourceId) as SystemsSourceRow | undefined;
}

function effectiveEntryVisibility(
  row: SystemsEntryRow,
  sourceState: SystemsSourceState,
  override: SystemsEntryOverride | null,
): string {
  const overrideVisibility = normalizeVisibility(override?.visibility_override || "", "");
  if (overrideVisibility) {
    if (overrideVisibility === "public" && !sourceState.public_visibility_allowed) {
      return "players";
    }
    return overrideVisibility;
  }
  if (Boolean(row.player_safe_default) && !Boolean(row.dm_heavy)) {
    return sourceState.default_visibility;
  }
  return "dm";
}

function canAccessEntry(
  row: SystemsEntryRow,
  role: FixtureSystemsRole,
  sourceState: SystemsSourceState,
  override: SystemsEntryOverride | null,
): boolean {
  if (role === "admin") {
    return true;
  }
  if (!sourceState.permissions.can_access || !sourceState.is_enabled || override?.is_enabled_override === false) {
    return false;
  }
  if (canManageSystems(role)) {
    return true;
  }
  const visibility = effectiveEntryVisibility(row, sourceState, override);
  return visibility === "public" || visibility === "players";
}

function referenceSearchValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => referenceSearchValues(item));
  }
  if (typeof value === "object" && value !== null) {
    const record = asRecord(value);
    return ["title", "label", "name"].flatMap((key) => {
      const cleaned = String(record[key] || "").trim();
      return cleaned ? [cleaned] : [];
    });
  }
  const cleaned = String(value || "").trim();
  return cleaned ? [cleaned] : [];
}

function normalizeLookup(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function buildRulesReferenceSearchText(row: SystemsEntryRow): string {
  const metadata = parseMetadata(row);
  const searchParts = [row.title, row.source_id, row.entry_type];
  if (row.entry_type === "book") {
    searchParts.push(
      String(metadata.section_label || "").trim(),
      ...referenceSearchValues(metadata.headers),
      ...referenceSearchValues(metadata.section_outline),
    );
  } else if (row.entry_type === "rule") {
    searchParts.push(
      String(metadata.rule_key || "").trim(),
      String(metadata.formula || "").trim(),
      ...referenceSearchValues(metadata.aliases),
      ...referenceSearchValues(metadata.rule_facets),
    );
  }
  searchParts.push(...referenceSearchValues(metadata.reference_terms));
  return searchParts
    .filter((part) => String(part || "").trim())
    .map((part) => normalizeLookup(String(part)))
    .join(" ");
}

function serializeRulesReferenceResult(row: SystemsEntryRow): SystemsRulesReferenceResult {
  const metadata = parseMetadata(row);
  let referenceScope = "";
  if (row.entry_type === "book") {
    const scopeParts = [String(metadata.section_label || "").trim()];
    const chapterTitle = String(metadata.chapter_title || "").trim();
    if (chapterTitle && chapterTitle !== row.title) {
      scopeParts.push(chapterTitle);
    }
    referenceScope = scopeParts.filter(Boolean).join(" | ");
  } else if (row.entry_type === "rule") {
    const facets = Array.isArray(metadata.rule_facets)
      ? metadata.rule_facets.map((value) => String(value).trim()).filter(Boolean)
      : [];
    const aliases = Array.isArray(metadata.aliases)
      ? metadata.aliases.map((value) => String(value).trim()).filter(Boolean)
      : [];
    const summaryValues = facets.length > 0 ? facets : aliases;
    if (summaryValues.length > 0) {
      referenceScope = summaryValues.slice(0, 3).join(", ");
    }
  }

  return {
    title: String(row.title),
    entry_type: String(row.entry_type),
    entry_type_label: entryTypeLabel(row.entry_type),
    source_id: String(row.source_id),
    slug: String(row.slug),
    reference_scope: referenceScope,
  };
}

function buildRulesReferenceSearchMeta(rows: SystemsEntryRow[]): string {
  const hasBook = rows.some((row) => row.entry_type === "book");
  const hasRule = rows.some((row) => row.entry_type === "rule");
  if (hasBook && hasRule) {
    return "Searches only this source's book chapters and rules entries using curated metadata like chapter labels, section headings, aliases, formulas, and rule facets. It does not search full entry body text.";
  }
  if (hasBook) {
    return "Searches only this source's book chapters using curated metadata like chapter labels and section headings. It does not search full entry body text.";
  }
  if (hasRule) {
    return "Searches only this source's rules entries using curated metadata like aliases, formulas, and rule facets. It does not search full entry body text.";
  }
  return "";
}

export function buildCampaignSystemsSourceListPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
): SystemsSourceListPayload {
  const canManage = canManageSystems(role);
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug || !existsSync(dbPath)) {
    return emptyPayload(campaign, canManage);
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const library = serializeLibrary(
      database
        .prepare(
          `
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `,
        )
        .get(librarySlug) as SystemsLibraryRow | undefined,
    );
    if (!library) {
      return emptyPayload(campaign, canManage);
    }

    const seeds = parseSourceSeeds(campaignConfig);
    const rows = database
      .prepare(
        `
          SELECT
            systems_sources.source_id,
            systems_sources.title,
            systems_sources.library_slug,
            systems_sources.license_class,
            systems_sources.public_visibility_allowed,
            systems_sources.requires_unofficial_notice,
            systems_sources.status,
            campaign_enabled_sources.is_enabled AS configured_enabled,
            campaign_enabled_sources.default_visibility AS configured_visibility,
            (
              SELECT COUNT(*)
              FROM systems_entries
              WHERE systems_entries.library_slug = systems_sources.library_slug
                AND systems_entries.source_id = systems_sources.source_id
            ) AS entry_count
          FROM systems_sources
          LEFT JOIN campaign_enabled_sources
            ON campaign_enabled_sources.campaign_slug = ?
           AND campaign_enabled_sources.library_slug = systems_sources.library_slug
           AND campaign_enabled_sources.source_id = systems_sources.source_id
          WHERE systems_sources.library_slug = ?
          ORDER BY LOWER(systems_sources.title), systems_sources.source_id
        `,
      )
      .all(campaign.slug, librarySlug) as SystemsSourceRow[];
    const sources = rows
      .map((row) => serializeSourceState(row, seeds.get(row.source_id), role))
      .filter((state) => canManage || (state.is_enabled && state.permissions.can_access));

    return {
      campaign,
      library,
      sources,
      permissions: {
        can_manage_systems: canManage,
      },
    };
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return emptyPayload(campaign, canManage);
    }
    throw error;
  } finally {
    database.close();
  }
}

export function buildCampaignSystemsSourceDetailPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  sourceId: string,
  role: FixtureSystemsRole,
  referenceQuery = "",
): SystemsSourceDetailResult {
  const canManage = canManageSystems(role);
  const librarySlug = campaign.systems_library_slug || "";
  const normalizedSourceId = String(sourceId || "").trim();
  if (!librarySlug || !normalizedSourceId || !existsSync(dbPath)) {
    return { status: "not_found" };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const library = serializeLibrary(
      database
        .prepare(
          `
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `,
        )
        .get(librarySlug) as SystemsLibraryRow | undefined,
    );
    if (!library) {
      return { status: "not_found" };
    }

    const seeds = parseSourceSeeds(campaignConfig);
    const row = loadSourceRow(database, campaign.slug, librarySlug, normalizedSourceId);
    if (!row) {
      return { status: "not_found" };
    }

    const source = serializeSourceState(row, seeds.get(row.source_id), role);
    if (!source.permissions.can_access) {
      return { status: "forbidden", message: "You do not have access to this systems source." };
    }
    if (!source.is_enabled) {
      return { status: "not_found" };
    }

    const accessibleEntries = loadAccessibleSourceEntries(database, librarySlug, normalizedSourceId, role);
    const allEntryGroups = buildEntryGroups(accessibleEntries);
    const entryGroups = allEntryGroups.filter(
      (group) => !SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(group.entry_type),
    );
    const rulesReferenceEntries = accessibleEntries.filter((entry) => RULES_REFERENCE_ENTRY_TYPES.has(entry.entry_type));
    const cleanedReferenceQuery = String(referenceQuery || "").trim();
    const normalizedReferenceTerms = cleanedReferenceQuery
      ? cleanedReferenceQuery.split(/\s+/).map(normalizeLookup).filter(Boolean)
      : [];
    const rulesReferenceResults =
      normalizedReferenceTerms.length > 0
        ? rulesReferenceEntries
            .filter((entry) => {
              const searchText = buildRulesReferenceSearchText(entry);
              return normalizedReferenceTerms.every((term) => searchText.includes(term));
            })
            .slice(0, 100)
            .map(serializeRulesReferenceResult)
        : [];

    return {
      status: "ok",
      payload: {
        campaign,
        source,
        entry_groups: entryGroups,
        book_entries: accessibleEntries.filter((entry) => entry.entry_type === "book").map(serializeEntrySummary),
        entry_count: allEntryGroups.reduce((count, group) => count + group.count, 0),
        browsable_entry_count: entryGroups.reduce((count, group) => count + group.count, 0),
        hidden_entry_types: allEntryGroups
          .filter((group) => SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(group.entry_type))
          .map((group) => group.entry_type),
        has_rules_reference_search: rulesReferenceEntries.length > 0,
        rules_reference_search_meta: buildRulesReferenceSearchMeta(rulesReferenceEntries),
        rules_reference_scope_note: "",
        reference_query: cleanedReferenceQuery,
        rules_reference_results: rulesReferenceResults,
        book_visibility_policy_note: "",
        permissions: {
          can_manage_systems: canManage,
        },
      },
    };
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "not_found" };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function buildCampaignSystemsSourceCategoryPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  sourceId: string,
  entryType: string,
  role: FixtureSystemsRole,
  query = "",
): SystemsSourceCategoryResult {
  const canManage = canManageSystems(role);
  const librarySlug = campaign.systems_library_slug || "";
  const normalizedSourceId = String(sourceId || "").trim();
  const normalizedEntryType = String(entryType || "").trim().toLowerCase();
  if (!librarySlug || !normalizedSourceId || !normalizedEntryType || !existsSync(dbPath)) {
    return { status: "not_found" };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const library = serializeLibrary(
      database
        .prepare(
          `
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `,
        )
        .get(librarySlug) as SystemsLibraryRow | undefined,
    );
    if (!library) {
      return { status: "not_found" };
    }

    const seeds = parseSourceSeeds(campaignConfig);
    const row = loadSourceRow(database, campaign.slug, librarySlug, normalizedSourceId);
    if (!row) {
      return { status: "not_found" };
    }

    const source = serializeSourceState(row, seeds.get(row.source_id), role);
    if (!source.permissions.can_access) {
      return { status: "forbidden", message: "You do not have access to this systems source." };
    }
    if (!source.is_enabled) {
      return { status: "not_found" };
    }

    const accessibleEntries = loadAccessibleSourceEntries(database, librarySlug, normalizedSourceId, role);
    const allEntryGroups = buildEntryGroups(accessibleEntries);
    const entryGroups = allEntryGroups.filter(
      (group) => !SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(group.entry_type),
    );
    const allCategoryEntries = loadAccessibleSourceEntries(database, librarySlug, normalizedSourceId, role, {
      entryType: normalizedEntryType,
    });
    if (allCategoryEntries.length <= 0) {
      return { status: "not_found" };
    }

    const cleanedQuery = String(query || "").trim();
    const entries = cleanedQuery
      ? allCategoryEntries.filter((entry) => entryMatchesCategoryQuery(entry, cleanedQuery))
      : allCategoryEntries;

    return {
      status: "ok",
      payload: {
        campaign,
        source,
        entry_groups: entryGroups,
        entry_type: normalizedEntryType,
        entry_type_label: entryTypeLabel(normalizedEntryType),
        query: cleanedQuery,
        entry_count: allCategoryEntries.length,
        filtered_entry_count: entries.length,
        entries: entries.map(serializeEntrySummary),
        permissions: {
          can_manage_systems: canManage,
        },
      },
    };
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "not_found" };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function buildCampaignSystemsEntryDetailPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  entrySlug: string,
  role: FixtureSystemsRole,
): SystemsEntryDetailResult {
  const canManage = canManageSystems(role);
  const librarySlug = campaign.systems_library_slug || "";
  const normalizedEntrySlug = String(entrySlug || "").trim();
  if (!librarySlug || !normalizedEntrySlug || !existsSync(dbPath)) {
    return { status: "not_found" };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const library = serializeLibrary(
      database
        .prepare(
          `
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `,
        )
        .get(librarySlug) as SystemsLibraryRow | undefined,
    );
    if (!library) {
      return { status: "not_found" };
    }

    const entry = database
      .prepare(
        `
          SELECT
            id,
            library_slug,
            source_id,
            entry_key,
            entry_type,
            slug,
            title,
            source_page,
            source_path,
            search_text,
            player_safe_default,
            dm_heavy,
            metadata_json,
            body_json,
            rendered_html,
            created_at,
            updated_at
          FROM systems_entries
          WHERE library_slug = ?
            AND slug = ?
        `,
      )
      .get(librarySlug, normalizedEntrySlug) as SystemsEntryRow | undefined;
    if (!entry) {
      return { status: "not_found" };
    }

    const sourceRow = loadSourceRow(database, campaign.slug, librarySlug, entry.source_id);
    if (!sourceRow) {
      return { status: "not_found" };
    }

    const seeds = parseSourceSeeds(campaignConfig);
    const sourceState = serializeSourceState(sourceRow, seeds.get(sourceRow.source_id), role);
    const override = loadCampaignEntryOverride(database, campaign.slug, entry.entry_key);
    if (!canAccessEntry(entry, role, sourceState, override)) {
      return { status: "forbidden", message: "You do not have access to this systems entry." };
    }

    return {
      status: "ok",
      payload: {
        campaign,
        entry: serializeEntryRecord(entry, sourceState, override),
        permissions: {
          can_manage_systems: canManage,
        },
        links: {
          flask_entry_url: `/campaigns/${campaign.slug}/systems/entries/${entry.slug}`,
          flask_source_url: `/campaigns/${campaign.slug}/systems/sources/${entry.source_id}`,
          flask_source_category_url: `/campaigns/${campaign.slug}/systems/sources/${entry.source_id}/types/${entry.entry_type}`,
          dm_content_systems_url: canManage
            ? `/campaigns/${campaign.slug}/dm-content/systems?entry_key=${encodeURIComponent(entry.entry_key)}#systems-entry-overrides`
            : "",
        },
      },
    };
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "not_found" };
    }
    throw error;
  } finally {
    database.close();
  }
}
