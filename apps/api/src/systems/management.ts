import { existsSync } from "node:fs";

import { openSqliteDatabase, type SqliteDatabase } from "../sqlite.js";

import type { CampaignViewModel } from "../campaigns/view.js";
import { slugify } from "../wiki/repository.js";
import {
  entryTypeLabel,
  entryTypeSortKey,
  isNoSuchTableError,
  loadCampaignEntryOverrides,
  loadEntriesForSources,
  loadSourceRows,
  parseJsonValue,
  parseMetadata,
  parseSourceSeeds,
  serializeEntrySummary,
  serializeLibrary,
  serializeSourceState,
  SYSTEMS_ENTRY_TYPE_LABELS,
  type FixtureSystemsRole,
  type SystemsEntryOverride,
  type SystemsEntryRow,
  type SystemsLibrary,
  type SystemsLibraryRow,
  type SystemsSourceState,
} from "./sources.js";


interface CampaignSystemsPolicyRow {
  library_slug: string;
  status: string;
  allow_dm_shared_core_entry_edits: number | null;
  proprietary_acknowledged_at: string | null;
}

interface SystemsImportRunRow {
  id: number;
  library_slug: string;
  source_id: string;
  status: string;
  import_version: string;
  summary_json: string;
  started_at: string;
  completed_at: string | null;
  started_by_user_id: number | null;
}

interface CampaignPageRow {
  page_ref: string;
  title: string;
  source_ref: string;
  route_slug: string;
}

const VISIBILITY_LABELS: Record<string, string> = {
  public: "Public",
  players: "Players",
  dm: "DM",
  private: "Private",
};

const VISIBILITY_ORDER: Record<string, number> = {
  public: 0,
  players: 1,
  dm: 2,
  private: 3,
};

const DND5E_IMPORT_ENTRY_TYPES = [
  "action",
  "background",
  "book",
  "class",
  "classfeature",
  "condition",
  "disease",
  "feat",
  "item",
  "monster",
  "optionalfeature",
  "race",
  "sense",
  "skill",
  "spell",
  "status",
  "subclass",
  "subclassfeature",
  "variantrule",
];

const CAMPAIGN_ITEM_METADATA_KEYS = [
  "ability_score_minimums",
  "ac",
  "armor_profile",
  "attack_reminder_rules",
  "attunement",
  "base_item",
  "bonus",
  "bonus_ac",
  "bonus_attack_rolls",
  "bonus_damage_rolls",
  "bonus_weapon",
  "bonus_weapon_attack",
  "bonus_weapon_damage",
  "charges",
  "damage",
  "damage_type",
  "defensive_rules",
  "dmg1",
  "dmg2",
  "item_uses",
  "properties",
  "property",
  "range",
  "rarity",
  "recharge",
  "resource_template_bonuses",
  "spell_support",
  "stealth_disadvantage",
  "strength",
  "type",
  "versatile_damage",
  "weapon_category",
  "weapon_profile",
];

const XIANXIA_CUSTOM_ENTRY_FACETS: Record<string, { key: string; label: string; support_state?: string }> = {
  rule: { key: "rule", label: "Rule" },
  attribute: { key: "attribute", label: "Attribute" },
  effort: { key: "effort", label: "Effort" },
  energy: { key: "energy", label: "Energy" },
  yin_yang: { key: "yin_yang", label: "Yin/Yang" },
  dao: { key: "dao", label: "Dao" },
  realm: { key: "realm", label: "Realm" },
  honor_rank: { key: "honor_rank", label: "Honor Rank" },
  skill_rule: { key: "skill_rule", label: "Skill Rule" },
  equipment: { key: "equipment", label: "Equipment" },
  armor: { key: "armor", label: "Armor" },
  martial_art: { key: "martial_art", label: "Martial Art" },
  martial_art_rank: { key: "martial_art_rank", label: "Martial Art Rank" },
  technique: { key: "technique", label: "Technique" },
  maneuver: { key: "maneuver", label: "Maneuver" },
  stance: { key: "stance", label: "Stance" },
  aura: { key: "aura", label: "Aura" },
  generic_technique: { key: "generic_technique", label: "Generic Technique" },
  basic_action: { key: "basic_action", label: "Basic Action", support_state: "reference_only" },
  condition: { key: "condition", label: "Condition", support_state: "reference_only" },
  status: { key: "status", label: "Status", support_state: "reference_only" },
  range_rule: { key: "range_rule", label: "Range Rule" },
  timing_rule: { key: "timing_rule", label: "Timing Rule" },
  critical_hit_rule: { key: "critical_hit_rule", label: "Critical Hit Rule" },
  sneak_attack_rule: { key: "sneak_attack_rule", label: "Sneak Attack Rule" },
  dying_rule: { key: "dying_rule", label: "Dying Rule" },
  minion_tag: { key: "minion_tag", label: "Minion Tag" },
  companion_rule: { key: "companion_rule", label: "Companion Rule" },
  gm_approval_rule: { key: "gm_approval_rule", label: "GM Approval Rule" },
};

function canManageSystems(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function canSetPrivateVisibility(role: FixtureSystemsRole): boolean {
  return role === "admin";
}

function tableExists(database: SqliteDatabase, tableName: string): boolean {
  const row = database
    .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?")
    .get(tableName) as { name?: string } | undefined;
  return Boolean(row?.name);
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function normalizeVisibilityChoice(value: unknown): string {
  const visibility = String(value || "").trim().toLowerCase();
  return Object.hasOwn(VISIBILITY_ORDER, visibility) ? visibility : "";
}

function mostPrivateVisibility(left: string, right: string): string {
  return (VISIBILITY_ORDER[left] ?? -1) >= (VISIBILITY_ORDER[right] ?? -1) ? left : right;
}

function defaultSystemsScopeVisibility(campaign: CampaignViewModel): string {
  const system = String(campaign.system || "").trim().toLowerCase();
  return system === "xianxia" ? "dm" : "players";
}

function visibilityChoices(includePrivate: boolean) {
  const choices = [
    { value: "public", label: VISIBILITY_LABELS.public },
    { value: "players", label: VISIBILITY_LABELS.players },
    { value: "dm", label: VISIBILITY_LABELS.dm },
  ];
  if (includePrivate) {
    choices.push({ value: "private", label: VISIBILITY_LABELS.private });
  }
  return choices;
}

function compareEntryTypes(left: string, right: string): number {
  const leftKey = entryTypeSortKey(left);
  const rightKey = entryTypeSortKey(right);
  if (leftKey[0] !== rightKey[0]) {
    return leftKey[0] - rightKey[0];
  }
  return leftKey[1].localeCompare(rightKey[1]);
}

function loadLibrary(database: SqliteDatabase, librarySlug: string): SystemsLibrary | null {
  if (!librarySlug) {
    return null;
  }
  try {
    return serializeLibrary(
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
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return null;
    }
    throw error;
  }
}

function loadPolicy(database: SqliteDatabase, campaignSlug: string): CampaignSystemsPolicyRow | null {
  if (!tableExists(database, "campaign_system_policies")) {
    return null;
  }
  return (
    (database
      .prepare(
        `
          SELECT
            library_slug,
            status,
            allow_dm_shared_core_entry_edits,
            proprietary_acknowledged_at
          FROM campaign_system_policies
          WHERE campaign_slug = ?
        `,
      )
      .get(campaignSlug) as CampaignSystemsPolicyRow | undefined) || null
  );
}

function loadEffectiveSystemsScopeVisibility(database: SqliteDatabase, campaign: CampaignViewModel): string {
  const defaultCampaignVisibility = "public";
  const defaultSystemsVisibility = defaultSystemsScopeVisibility(campaign);
  if (!tableExists(database, "campaign_visibility_settings")) {
    return mostPrivateVisibility(defaultCampaignVisibility, defaultSystemsVisibility);
  }
  try {
    const rows = database
      .prepare(
        `
          SELECT scope, visibility
          FROM campaign_visibility_settings
          WHERE campaign_slug = ?
            AND scope IN ('campaign', 'systems')
        `,
      )
      .all(campaign.slug) as Array<{ scope?: string; visibility?: string }>;
    const visibilityByScope = new Map<string, string>();
    for (const row of rows) {
      const scope = String(row.scope || "").trim().toLowerCase();
      const visibility = normalizeVisibilityChoice(row.visibility);
      if (scope && visibility) {
        visibilityByScope.set(scope, visibility);
      }
    }
    return mostPrivateVisibility(
      visibilityByScope.get("campaign") || defaultCampaignVisibility,
      visibilityByScope.get("systems") || defaultSystemsVisibility,
    );
  } catch (error) {
    if (isNoSuchTableError(error) || (error instanceof Error && error.message.includes("no such column"))) {
      return mostPrivateVisibility(defaultCampaignVisibility, defaultSystemsVisibility);
    }
    throw error;
  }
}

function sourceRowsForManagement(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  librarySlug: string,
  systemsScopeVisibility: string,
) {
  if (!librarySlug) {
    return [];
  }

  const choices = visibilityChoices(canSetPrivateVisibility(role));
  try {
    const seeds = parseSourceSeeds(campaignConfig);
    return loadSourceRows(database, campaign.slug, librarySlug).map((row) => {
      const sourceState = serializeSourceState(row, seeds.get(row.source_id), role);
      const systemsVisibility = normalizeVisibilityChoice(systemsScopeVisibility) || "private";
      const sourceVisibility = mostPrivateVisibility(
        systemsVisibility,
        sourceState.default_visibility,
      );
      return {
        ...sourceState,
        permissions: {
          ...sourceState.permissions,
          can_access:
            role === "admin" ||
            (systemsVisibility !== "private" &&
            (sourceState.is_enabled &&
              (sourceVisibility === "public" ||
                sourceVisibility === "players" ||
                  (role === "dm" && sourceVisibility === "dm")))),
        },
        selected_visibility: sourceState.default_visibility,
        entry_count: Number(row.entry_count || 0),
        choices: choices.map((choice) => ({
          ...choice,
          disabled: choice.value === "public" && !Boolean(row.public_visibility_allowed),
        })),
      };
    });
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return [];
    }
    throw error;
  }
}

function visibilityLabel(value: string | null | undefined, fallback = ""): string {
  const normalized = String(value || "").trim();
  return normalized ? VISIBILITY_LABELS[normalized] || normalized : fallback;
}

function effectiveEntryVisibility(
  entry: SystemsEntryRow,
  sourceState: SystemsSourceState,
  override: SystemsEntryOverride | undefined,
): string {
  const overrideVisibility = normalizeVisibilityChoice(override?.visibility_override || "");
  if (overrideVisibility) {
    if (overrideVisibility === "public" && !sourceState.public_visibility_allowed) {
      return "players";
    }
    return overrideVisibility;
  }
  if (Boolean(entry.player_safe_default) && !Boolean(entry.dm_heavy)) {
    return sourceState.default_visibility;
  }
  return "dm";
}

function canAccessEntryLink(
  role: FixtureSystemsRole,
  systemsScopeVisibility: string,
  entry: SystemsEntryRow | undefined,
  sourceState: SystemsSourceState | undefined,
  override: SystemsEntryOverride | undefined,
): boolean {
  const overrideEnablement = override?.is_enabled_override as unknown;
  const isDisabledOverride = overrideEnablement === false || overrideEnablement === 0;
  if (!entry || !sourceState) {
    return false;
  }
  if (role === "admin") {
    return true;
  }
  if (normalizeVisibilityChoice(systemsScopeVisibility) === "private") {
    return false;
  }
  if (!sourceState.permissions.can_access || !sourceState.is_enabled || isDisabledOverride) {
    return false;
  }
  const visibility = mostPrivateVisibility(
    normalizeVisibilityChoice(systemsScopeVisibility) || "private",
    effectiveEntryVisibility(entry, sourceState, override),
  );
  if (role === "dm") {
    return visibility === "public" || visibility === "players" || visibility === "dm";
  }
  return visibility === "public" || visibility === "players";
}

function serializeOverrideRow(
  campaignSlug: string,
  role: FixtureSystemsRole,
  systemsScopeVisibility: string,
  override: SystemsEntryOverride,
  entry: SystemsEntryRow | undefined,
  sourceState: SystemsSourceState | undefined,
) {
  const visibilityOverride = override.visibility_override || "";
  let enablementLabel = "Inherit source enablement";
  if (override.is_enabled_override === true) {
    enablementLabel = "Enabled";
  } else if (override.is_enabled_override === false) {
    enablementLabel = "Disabled";
  }
  const entrySlug = entry ? String(entry.slug || "") : "";

  return {
    ...override,
    entry_title: entry ? String(entry.title || "") : "Unknown entry",
    entry_type: entry ? String(entry.entry_type || "") : "",
    entry_type_label: entry ? entryTypeLabel(entry.entry_type) : "",
    entry_slug: entrySlug,
    entry_href:
      entrySlug && canAccessEntryLink(role, systemsScopeVisibility, entry, sourceState, override)
        ? `/campaigns/${campaignSlug}/systems/entries/${entrySlug}`
        : "",
    source_id: entry ? String(entry.source_id || "") : "",
    source_label: sourceState
      ? `${sourceState.title} (${sourceState.source_id})`
      : entry
        ? String(entry.source_id || "")
        : "",
    visibility_label: visibilityOverride
      ? visibilityLabel(visibilityOverride)
      : "Inherit source default",
    enablement_label: enablementLabel,
  };
}

function entryByKey(rows: SystemsEntryRow[]): Map<string, SystemsEntryRow> {
  return new Map(rows.map((row) => [row.entry_key, row]));
}

function sourceStateById(rows: SystemsSourceState[]): Map<string, SystemsSourceState> {
  return new Map(rows.map((row) => [row.source_id, row]));
}

function loadEntryOverrideRows(
  database: SqliteDatabase,
  campaignSlug: string,
  librarySlug: string,
  sourceRows: SystemsSourceState[],
  role: FixtureSystemsRole,
  systemsScopeVisibility: string,
) {
  if (!librarySlug) {
    return [];
  }

  try {
    const overrides = [...loadCampaignEntryOverrides(database, campaignSlug, librarySlug).values()];
    const entries = entryByKey(
      loadEntriesForSources(
        database,
        librarySlug,
        sourceRows.map((source) => source.source_id),
      ),
    );
    const sources = sourceStateById(sourceRows);
    return overrides
      .sort((left, right) => left.entry_key.localeCompare(right.entry_key))
      .map((override) => {
        const entry = entries.get(override.entry_key);
        const sourceState = entry ? sources.get(entry.source_id) : undefined;
        return serializeOverrideRow(campaignSlug, role, systemsScopeVisibility, override, entry, sourceState);
      });
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return [];
    }
    throw error;
  }
}

function campaignItemReviewForMetadata(metadata: Record<string, unknown>) {
  const review = metadata.campaign_item_mechanics;
  if (typeof review === "object" && review !== null && !Array.isArray(review)) {
    return { ...(review as Record<string, unknown>) };
  }

  const hasReviewMetadata =
    Object.hasOwn(metadata, "campaign_item_mechanics") ||
    Object.hasOwn(metadata, "campaign_item_mechanics_version") ||
    Object.hasOwn(metadata, "campaign_item_mechanics_review_status");
  if (!hasReviewMetadata) {
    return null;
  }

  const modeledFields = [
    "ability_score_minimums",
    "ac",
    "armor_profile",
    "attack_reminder_rules",
    "attunement",
    "base_item",
    "bonus",
    "bonus_ac",
    "bonus_attack_rolls",
    "bonus_damage_rolls",
    "bonus_weapon",
    "bonus_weapon_attack",
    "bonus_weapon_damage",
    "charges",
    "damage",
    "damage_type",
    "defensive_rules",
    "dmg1",
    "dmg2",
    "item_uses",
    "properties",
    "property",
    "range",
    "rarity",
    "recharge",
    "resource_template_bonuses",
    "spell_support",
    "stealth_disadvantage",
    "strength",
    "type",
    "versatile_damage",
    "weapon_category",
    "weapon_profile",
  ].filter((key) => {
    const value = metadata[key];
    if (value === null || value === undefined || value === "") {
      return false;
    }
    if (Array.isArray(value) && value.length === 0) {
      return false;
    }
    if (typeof value === "object" && !Array.isArray(value) && Object.keys(value as Record<string, unknown>).length === 0) {
      return false;
    }
    return true;
  });

  return {
    version: String(metadata.campaign_item_mechanics_version || "2026-06-25"),
    review_status: String(metadata.campaign_item_mechanics_review_status || "draft"),
    support_state: String(metadata.campaign_item_mechanics_support_state || ""),
    modeled_fields: modeledFields,
    flags: Array.isArray(metadata.campaign_item_mechanics_flags) ? metadata.campaign_item_mechanics_flags : [],
    field_provenance: asRecord(metadata.campaign_item_mechanics_field_provenance),
  };
}

function customEntryDefaultVisibility(campaign: CampaignViewModel): string {
  const system = String(campaign.system || "").trim().toLowerCase();
  const librarySlug = String(campaign.systems_library_slug || "").trim().toLowerCase();
  return system === "xianxia" || librarySlug === "xianxia" ? "dm" : "players";
}

function isCampaignCustomEntry(campaignSlug: string, metadata: Record<string, unknown>): boolean {
  const customCampaignSlug = String(metadata.custom_campaign_slug || "").trim();
  return !customCampaignSlug || customCampaignSlug === campaignSlug;
}

function serializeCustomEntry(
  campaign: CampaignViewModel,
  role: FixtureSystemsRole,
  systemsScopeVisibility: string,
  entry: SystemsEntryRow,
  override: SystemsEntryOverride | undefined,
  sourceState: SystemsSourceState,
) {
  const metadata = parseMetadata(entry);
  const body = asRecord(parseJsonValue(entry.body_json, {}));
  const isArchived = override?.is_enabled_override === false;
  const visibility = override?.visibility_override || sourceState.default_visibility || customEntryDefaultVisibility(campaign);
  const linkedPublishedPageRef = String(metadata.linked_published_page_ref || metadata.page_ref || "").trim();

  return {
    ...serializeEntrySummary(entry),
    visibility,
    visibility_label: visibilityLabel(visibility, visibility),
    status_label: isArchived ? "Archived" : "Active",
    is_archived: isArchived,
    provenance: String(metadata.provenance || entry.source_path || ""),
    search_metadata: String(metadata.search_metadata || ""),
    body_markdown: String(body.markdown || metadata.body_markdown || ""),
    linked_published_page_ref: linkedPublishedPageRef,
    source_page_ref: linkedPublishedPageRef,
    item_mechanics: campaignItemReviewForMetadata(metadata),
    rendered_html: String(entry.rendered_html || ""),
    href: canAccessEntryLink(role, systemsScopeVisibility, entry, sourceState, override)
      ? `/campaigns/${campaign.slug}/systems/entries/${entry.slug}`
      : "",
    override: override || null,
  };
}

function loadCustomEntrySourceRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  librarySlug: string,
  sourceRows: SystemsSourceState[],
  role: FixtureSystemsRole,
  systemsScopeVisibility: string,
) {
  if (!librarySlug) {
    return { custom_entry_source_rows: [], custom_entry_count: 0 };
  }

  const customSourceRows = sourceRows.filter((source) => source.license_class === "custom_campaign");
  if (customSourceRows.length === 0) {
    return { custom_entry_source_rows: [], custom_entry_count: 0 };
  }

  try {
    const overrides = loadCampaignEntryOverrides(database, campaign.slug, librarySlug);
    let customEntryCount = 0;
    const rows = customSourceRows.map((sourceState) => {
      const entries = loadEntriesForSources(database, librarySlug, [sourceState.source_id])
        .filter((entry) => isCampaignCustomEntry(campaign.slug, parseMetadata(entry)))
        .map((entry) =>
          serializeCustomEntry(campaign, role, systemsScopeVisibility, entry, overrides.get(entry.entry_key), sourceState),
        );
      const activeEntryCount = entries.filter((entry) => !entry.is_archived).length;
      customEntryCount += entries.length;
      return {
        source_id: sourceState.source_id,
        title: sourceState.title,
        is_enabled: sourceState.is_enabled,
        default_visibility: sourceState.default_visibility,
        default_visibility_label: visibilityLabel(sourceState.default_visibility, sourceState.default_visibility),
        entry_count: entries.length,
        active_entry_count: activeEntryCount,
        archived_entry_count: entries.length - activeEntryCount,
        entries,
      };
    });
    return { custom_entry_source_rows: rows, custom_entry_count: customEntryCount };
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { custom_entry_source_rows: [], custom_entry_count: 0 };
    }
    throw error;
  }
}

function linkedCustomItemEntries(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  librarySlug: string,
  sourceRows: SystemsSourceState[],
): Map<string, SystemsEntryRow> {
  const entriesByPage = new Map<string, SystemsEntryRow>();
  if (!librarySlug) {
    return entriesByPage;
  }

  const customSourceIds = sourceRows
    .filter((source) => source.license_class === "custom_campaign")
    .map((source) => source.source_id);
  if (customSourceIds.length === 0) {
    return entriesByPage;
  }

  for (const entry of loadEntriesForSources(database, librarySlug, customSourceIds)) {
    if (entry.entry_type !== "item") {
      continue;
    }
    const metadata = parseMetadata(entry);
    if (!isCampaignCustomEntry(campaign.slug, metadata)) {
      continue;
    }
    const pageRef = String(metadata.linked_published_page_ref || metadata.page_ref || "").trim();
    if (pageRef && !entriesByPage.has(pageRef)) {
      entriesByPage.set(pageRef, entry);
    }
  }
  return entriesByPage;
}

function loadCampaignItemPageRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  librarySlug: string,
  sourceRows: SystemsSourceState[],
) {
  if (!tableExists(database, "campaign_pages")) {
    return [];
  }

  try {
    const entriesByPage = linkedCustomItemEntries(database, campaign, librarySlug, sourceRows);
    const pageRows = database
      .prepare(
        `
          SELECT page_ref, title, source_ref, route_slug
          FROM campaign_pages
          WHERE campaign_slug = ?
            AND section = 'Items'
          ORDER BY LOWER(title), page_ref
        `,
      )
      .all(campaign.slug) as CampaignPageRow[];
    return pageRows
      .filter((page) => String(page.page_ref || "").trim())
      .map((page) => {
        const pageRef = String(page.page_ref || "").trim();
        const entry = entriesByPage.get(pageRef);
        const metadata = entry ? parseMetadata(entry) : {};
        return {
          page_ref: pageRef,
          title: String(page.title || "").trim() || pageRef,
          source_ref: String(page.source_ref || "").trim(),
          route_slug: String(page.route_slug || "").trim(),
          has_structured_item: Boolean(entry),
          entry_slug: entry ? String(entry.slug || "").trim() : "",
          entry_title: entry ? String(entry.title || "").trim() : "",
          item_mechanics: entry ? campaignItemReviewForMetadata(metadata) : null,
        };
      });
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return [];
    }
    throw error;
  }
}

type SerializedCustomEntry = ReturnType<typeof serializeCustomEntry>;
type CustomSystemsEntryMutationResult =
  | { status: "ok"; entry: SerializedCustomEntry; systems: ReturnType<typeof buildDmContentSystemsPayload> }
  | { status: "validation_error"; message: string };

interface CampaignItemPageContentRow {
  page_ref: string;
  title: string;
  source_ref: string;
  metadata_json: string;
  body_markdown: string;
}

function utcIsoTimestamp(): string {
  return new Date().toISOString().replace("Z", "+00:00");
}

function customCampaignSourceId(campaignSlug: string): string {
  const normalizedCampaignSlug = slugify(String(campaignSlug || "")).replace(/\//g, "-").toUpperCase();
  return `CUSTOM-${normalizedCampaignSlug || "CAMPAIGN"}`;
}

function normalizeEntryType(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "");
}

function normalizeCustomSlugLeaf(value: unknown): string {
  return slugify(String(value || ""))
    .replace(/\//g, "-")
    .replace(/^-+|-+$/g, "");
}

function escapeHtml(rawText: string): string {
  return rawText
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderCustomEntryMarkdown(markdownText: string): string {
  const blocks = escapeHtml(markdownText.trim())
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);
  return blocks
    .map((block) => {
      const headingMatch = block.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        const depth = Math.min(headingMatch[1]!.length, 6);
        return `<h${depth}>${headingMatch[2]!.trim()}</h${depth}>`;
      }
      return `<p>${block.replace(/\n/g, "<br />")}</p>`;
    })
    .join("");
}

function normalizeCampaignItemReviewStatus(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
  if (normalized === "approved" || normalized === "approve" || normalized === "modeled") {
    return "approved";
  }
  if (normalized === "reference" || normalized === "reference_only") {
    return "reference_only";
  }
  if (normalized === "manual" || normalized === "manual_review" || normalized === "review") {
    return "manual_review";
  }
  return "draft";
}

function hasMeaningfulValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }
  return true;
}

function buildCampaignItemMechanicsMetadata(
  title: string,
  sourcePageRef: string,
  reviewStatus: unknown,
  explicitMechanics: unknown,
  sourcePageMetadata: Record<string, unknown>,
) {
  const mechanics = asRecord(explicitMechanics);
  const normalizedReview = normalizeCampaignItemReviewStatus(
    reviewStatus || mechanics.review_status || mechanics.campaign_item_mechanics_review_status,
  );
  const combinedMechanics = { ...sourcePageMetadata, ...mechanics };
  const modeledFields = CAMPAIGN_ITEM_METADATA_KEYS.filter((key) => hasMeaningfulValue(combinedMechanics[key]));
  const flags = Array.isArray(mechanics.flags) ? mechanics.flags : [];
  const fieldProvenance = asRecord(mechanics.field_provenance);
  const explicitSupportState = String(mechanics.support_state || "").trim();
  let supportState = explicitSupportState;
  if (!supportState && normalizedReview === "reference_only") {
    supportState = "reference_only";
  }
  if (!supportState && normalizedReview === "manual_review") {
    supportState = "manual_review";
  }
  if (!supportState && normalizedReview !== "approved") {
    supportState = modeledFields.length > 0 ? "manual_review" : "reference_only";
  }
  if (!supportState && modeledFields.length === 0) {
    supportState = "reference_only";
  }
  if (
    !supportState &&
    flags.some((flag) => asRecord(flag).support_state === "needs_implementation")
  ) {
    supportState = "needs_implementation";
  }
  if (!supportState) {
    supportState = "modeled";
  }
  const reviewPayload = {
    version: "2026-06-25",
    review_status: normalizedReview,
    support_state: supportState,
    modeled_fields: modeledFields,
    flags,
    field_provenance: fieldProvenance,
    source_page_ref: sourcePageRef,
    intake_mode: sourcePageRef ? "published_page" : "direct",
  };
  const metadata: Record<string, unknown> = {
    ...sourcePageMetadata,
    ...mechanics,
    campaign_item: true,
    campaign_item_mechanics_version: "2026-06-25",
    campaign_item_mechanics_review_status: normalizedReview,
    campaign_item_mechanics_support_state: supportState,
    campaign_item_mechanics_flags: flags,
    campaign_item_mechanics_field_provenance: fieldProvenance,
    campaign_item_mechanics: reviewPayload,
  };
  if (sourcePageRef) {
    metadata.linked_published_page_ref = sourcePageRef;
    metadata.page_ref = sourcePageRef;
  }
  if (!metadata.title) {
    metadata.title = title;
  }
  return metadata;
}

function normalizeIdentifier(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function stampXianxiaCustomEntryMetadata(
  metadata: Record<string, unknown>,
  body: Record<string, unknown>,
  entryType: string,
  slug: string,
  title: string,
) {
  const facet = XIANXIA_CUSTOM_ENTRY_FACETS[entryType];
  if (!facet) {
    return;
  }

  metadata.xianxia_custom_entry = true;
  metadata.xianxia_entry_facets = [facet.key];
  metadata.xianxia_entry_facet_labels = [facet.label];
  body.xianxia_custom_entry = true;
  body.xianxia_entry_facets = [facet.key];

  if (facet.support_state) {
    metadata.support_state = facet.support_state;
    metadata.xianxia_support_state = facet.support_state;
    body.support_state = facet.support_state;
    body.xianxia_support_state = facet.support_state;
  }

  if (facet.key !== "martial_art") {
    return;
  }

  const martialArtKey = normalizeIdentifier(slug) || normalizeIdentifier(title);
  metadata.catalog_role = "parent";
  metadata.xianxia_catalog_role = "parent";
  metadata.custom_martial_art = true;
  metadata.xianxia_custom_martial_art = true;
  metadata.martial_art_key = martialArtKey;
  metadata.xianxia_martial_art_key = martialArtKey;
  metadata.martial_art_slug = slug;
  metadata.xianxia_martial_art_slug = slug;
  metadata.rank_records_seeded = false;
  metadata.rank_records_status = "gm_authored_custom_markdown";
  metadata.rank_completion_status = "gm_authored_custom_markdown";
  metadata.xianxia_rank_completion_status = "gm_authored_custom_markdown";
  body.xianxia_martial_art = {
    catalog_role: "parent",
    custom_martial_art: true,
    xianxia_custom_martial_art: true,
    martial_art_key: martialArtKey,
    xianxia_martial_art_key: martialArtKey,
    martial_art_slug: slug,
    xianxia_martial_art_slug: slug,
    rank_records_seeded: false,
    rank_records_status: "gm_authored_custom_markdown",
    rank_completion_status: "gm_authored_custom_markdown",
    rank_records: [],
    xianxia_martial_art_rank_records: [],
    missing_rank_records: [],
    xianxia_martial_art_missing_rank_records: [],
    parent_note: "GM-created custom Martial Art authored through the campaign custom Systems entry path.",
  };
}

function loadEntryBySlug(database: SqliteDatabase, librarySlug: string, entrySlug: string): SystemsEntryRow | null {
  return (
    (database
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
      .get(librarySlug, entrySlug) as SystemsEntryRow | undefined) || null
  );
}

function loadCampaignEnabledSource(database: SqliteDatabase, campaignSlug: string, sourceId: string) {
  return database
    .prepare(
      `
        SELECT source_id
        FROM campaign_enabled_sources
        WHERE campaign_slug = ?
          AND source_id = ?
      `,
    )
    .get(campaignSlug, sourceId) as { source_id: string } | undefined;
}

function upsertCampaignSystemsPolicyForCustomEntry(
  database: SqliteDatabase,
  campaignSlug: string,
  librarySlug: string,
  actorUserId: number,
  now: string,
) {
  database
    .prepare(
      `
        INSERT INTO campaign_system_policies (
          campaign_slug,
          library_slug,
          status,
          allow_dm_shared_core_entry_edits,
          proprietary_acknowledged_at,
          proprietary_acknowledged_by_user_id,
          created_at,
          updated_at,
          updated_by_user_id
        )
        VALUES (?, ?, 'active', 0, NULL, NULL, ?, ?, ?)
        ON CONFLICT(campaign_slug) DO UPDATE SET
          library_slug = excluded.library_slug,
          status = excluded.status,
          allow_dm_shared_core_entry_edits = campaign_system_policies.allow_dm_shared_core_entry_edits,
          proprietary_acknowledged_at = campaign_system_policies.proprietary_acknowledged_at,
          proprietary_acknowledged_by_user_id = campaign_system_policies.proprietary_acknowledged_by_user_id,
          updated_at = excluded.updated_at,
          updated_by_user_id = excluded.updated_by_user_id
      `,
    )
    .run(campaignSlug, librarySlug, now, now, actorUserId);
}

function upsertCustomCampaignSource(
  database: SqliteDatabase,
  librarySlug: string,
  sourceId: string,
  title: string,
  now: string,
) {
  database
    .prepare(
      `
        INSERT INTO systems_sources (
          library_slug,
          source_id,
          title,
          license_class,
          license_url,
          attribution_text,
          public_visibility_allowed,
          requires_unofficial_notice,
          status,
          created_at,
          updated_at
        )
        VALUES (?, ?, ?, 'custom_campaign', '', '', 1, 0, 'active', ?, ?)
        ON CONFLICT(library_slug, source_id) DO UPDATE SET
          title = excluded.title,
          license_class = excluded.license_class,
          license_url = excluded.license_url,
          attribution_text = excluded.attribution_text,
          public_visibility_allowed = excluded.public_visibility_allowed,
          requires_unofficial_notice = excluded.requires_unofficial_notice,
          status = excluded.status,
          updated_at = excluded.updated_at
      `,
    )
    .run(librarySlug, sourceId, title, now, now);
}

function insertCampaignEnabledSourceIfMissing(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  librarySlug: string,
  sourceId: string,
  actorUserId: number,
  now: string,
) {
  if (loadCampaignEnabledSource(database, campaign.slug, sourceId)) {
    return;
  }
  database
    .prepare(
      `
        INSERT INTO campaign_enabled_sources (
          campaign_slug,
          library_slug,
          source_id,
          is_enabled,
          default_visibility,
          updated_at,
          updated_by_user_id
        )
        VALUES (?, ?, ?, 1, ?, ?, ?)
      `,
    )
    .run(campaign.slug, librarySlug, sourceId, customEntryDefaultVisibility(campaign), now, actorUserId);
}

function upsertCustomSystemsEntryRow(
  database: SqliteDatabase,
  {
    librarySlug,
    sourceId,
    entryKey,
    entryType,
    slug,
    title,
    provenance,
    searchText,
    visibility,
    metadata,
    body,
    renderedHtml,
    now,
  }: {
    librarySlug: string;
    sourceId: string;
    entryKey: string;
    entryType: string;
    slug: string;
    title: string;
    provenance: string;
    searchText: string;
    visibility: string;
    metadata: Record<string, unknown>;
    body: Record<string, unknown>;
    renderedHtml: string;
    now: string;
  },
) {
  const existing = database
    .prepare("SELECT created_at FROM systems_entries WHERE library_slug = ? AND entry_key = ?")
    .get(librarySlug, entryKey) as { created_at?: string } | undefined;
  database
    .prepare(
      `
        INSERT INTO systems_entries (
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
        )
        VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(library_slug, entry_key) DO UPDATE SET
          source_id = excluded.source_id,
          entry_type = excluded.entry_type,
          slug = excluded.slug,
          title = excluded.title,
          source_page = excluded.source_page,
          source_path = excluded.source_path,
          search_text = excluded.search_text,
          player_safe_default = excluded.player_safe_default,
          dm_heavy = excluded.dm_heavy,
          metadata_json = excluded.metadata_json,
          body_json = excluded.body_json,
          rendered_html = excluded.rendered_html,
          updated_at = excluded.updated_at
      `,
    )
    .run(
      librarySlug,
      sourceId,
      entryKey,
      entryType,
      slug,
      title,
      provenance,
      searchText,
      visibility === "public" || visibility === "players" ? 1 : 0,
      visibility === "dm" || visibility === "private" ? 1 : 0,
      JSON.stringify(metadata),
      JSON.stringify(body),
      renderedHtml,
      existing?.created_at || now,
      now,
    );
}

function upsertCampaignEntryOverrideForCustomEntry(
  database: SqliteDatabase,
  campaignSlug: string,
  librarySlug: string,
  entryKey: string,
  visibilityOverride: string | null,
  isEnabledOverride: boolean | null,
  actorUserId: number,
  now: string,
): SystemsEntryOverride {
  database
    .prepare(
      `
        INSERT INTO campaign_entry_overrides (
          campaign_slug,
          library_slug,
          entry_key,
          visibility_override,
          is_enabled_override,
          updated_at,
          updated_by_user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(campaign_slug, entry_key) DO UPDATE SET
          library_slug = excluded.library_slug,
          visibility_override = excluded.visibility_override,
          is_enabled_override = excluded.is_enabled_override,
          updated_at = excluded.updated_at,
          updated_by_user_id = excluded.updated_by_user_id
      `,
    )
    .run(
      campaignSlug,
      librarySlug,
      entryKey,
      visibilityOverride,
      isEnabledOverride === null ? null : isEnabledOverride ? 1 : 0,
      now,
      actorUserId,
    );
  return {
    entry_key: entryKey,
    visibility_override: visibilityOverride,
    is_enabled_override: isEnabledOverride,
    updated_at: now,
    updated_by_user_id: actorUserId,
  };
}

function insertCustomEntryAuditEvent(
  database: SqliteDatabase,
  actorUserId: number,
  campaignSlug: string,
  eventType: string,
  entry: SystemsEntryRow,
  now: string,
) {
  database
    .prepare(
      `
        INSERT INTO auth_audit_log (
          actor_user_id,
          target_user_id,
          campaign_slug,
          character_slug,
          event_type,
          metadata_json,
          created_at
        )
        VALUES (?, NULL, ?, NULL, ?, ?, ?)
      `,
    )
    .run(
      actorUserId,
      campaignSlug,
      eventType,
      JSON.stringify({
        entry_key: entry.entry_key,
        entry_slug: entry.slug,
        entry_type: eventType.endsWith("_created") || eventType.endsWith("_updated") ? entry.entry_type : undefined,
        source: "api",
      }),
      now,
    );
}

function insertItemMechanicsImportAuditEvent(
  database: SqliteDatabase,
  actorUserId: number,
  campaignSlug: string,
  entry: SystemsEntryRow,
  pageRef: string,
  now: string,
) {
  database
    .prepare(
      `
        INSERT INTO auth_audit_log (
          actor_user_id,
          target_user_id,
          campaign_slug,
          character_slug,
          event_type,
          metadata_json,
          created_at
        )
        VALUES (?, NULL, ?, NULL, ?, ?, ?)
      `,
    )
    .run(
      actorUserId,
      campaignSlug,
      "campaign_systems_item_mechanics_imported",
      JSON.stringify({
        entry_key: entry.entry_key,
        entry_slug: entry.slug,
        entry_type: entry.entry_type,
        page_ref: pageRef,
        source: "api",
      }),
      now,
    );
}

function loadPublishedItemPage(
  database: SqliteDatabase,
  campaignSlug: string,
  pageRef: string,
): CampaignItemPageContentRow | null {
  if (!tableExists(database, "campaign_pages")) {
    return null;
  }
  return (
    (database
      .prepare(
        `
          SELECT page_ref, title, source_ref, metadata_json, body_markdown
          FROM campaign_pages
          WHERE campaign_slug = ?
            AND page_ref = ?
            AND section = 'Items'
            AND published != 0
        `,
      )
      .get(campaignSlug, pageRef) as CampaignItemPageContentRow | undefined) || null
  );
}

function loadCustomItemEntryByLinkedPage(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  librarySlug: string,
  pageRef: string,
): SystemsEntryRow | null {
  const customSourceIds = loadSourceRows(database, campaign.slug, librarySlug)
    .filter((source) => source.license_class === "custom_campaign")
    .map((source) => source.source_id);
  for (const entry of loadEntriesForSources(database, librarySlug, customSourceIds)) {
    if (entry.entry_type !== "item") {
      continue;
    }
    const metadata = parseMetadata(entry);
    if (!isCampaignCustomEntry(campaign.slug, metadata)) {
      continue;
    }
    const linkedPageRef = String(metadata.linked_published_page_ref || metadata.page_ref || "").trim();
    if (linkedPageRef === pageRef) {
      return entry;
    }
  }
  return null;
}

function customSourceState(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  librarySlug: string,
  sourceId: string,
): SystemsSourceState | null {
  const seeds = parseSourceSeeds(campaignConfig);
  const sourceRow = loadSourceRows(database, campaign.slug, librarySlug).find((row) => row.source_id === sourceId);
  return sourceRow ? serializeSourceState(sourceRow, seeds.get(sourceRow.source_id), role) : null;
}

function existingCustomEntryContext(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  librarySlug: string,
  entrySlug: string,
  invalidMessage: string,
) {
  const entry = loadEntryBySlug(database, librarySlug, String(entrySlug || "").trim());
  if (!entry) {
    return { status: "validation_error" as const, message: invalidMessage };
  }
  const sourceState = customSourceState(database, campaign, campaignConfig, role, librarySlug, entry.source_id);
  if (!sourceState || sourceState.license_class !== "custom_campaign" || !isCampaignCustomEntry(campaign.slug, parseMetadata(entry))) {
    return { status: "validation_error" as const, message: invalidMessage };
  }
  return { status: "ok" as const, entry, sourceState };
}

function ensureCustomCampaignSource(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  librarySlug: string,
  actorUserId: number,
  now: string,
) {
  const library = loadLibrary(database, librarySlug);
  if (!library) {
    return { status: "validation_error" as const, message: "That campaign does not have a systems library configured." };
  }
  const sourceId = customCampaignSourceId(campaign.slug);
  upsertCustomCampaignSource(
    database,
    librarySlug,
    sourceId,
    `${campaign.title || campaign.slug} Custom Systems`,
    now,
  );
  upsertCampaignSystemsPolicyForCustomEntry(database, campaign.slug, librarySlug, actorUserId, now);
  insertCampaignEnabledSourceIfMissing(database, campaign, librarySlug, sourceId, actorUserId, now);
  const sourceState = customSourceState(database, campaign, campaignConfig, role, librarySlug, sourceId);
  if (!sourceState) {
    return { status: "validation_error" as const, message: "The custom Systems source is no longer available." };
  }
  return { status: "ok" as const, sourceId, sourceState };
}

function prepareCustomEntryWrite(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  librarySlug: string,
  sourceState: SystemsSourceState,
  sourceId: string,
  actorUserId: number,
  role: FixtureSystemsRole,
  payload: Record<string, unknown>,
  existingEntry: SystemsEntryRow | null,
) {
  const normalizedTitle = String(payload.title || "").trim();
  if (!normalizedTitle) {
    return { status: "validation_error" as const, message: "Custom Systems entries need a title." };
  }
  if (normalizedTitle.length > 200) {
    return { status: "validation_error" as const, message: "Custom Systems entry titles must stay under 200 characters." };
  }

  const normalizedEntryType = normalizeEntryType(payload.entry_type);
  if (!normalizedEntryType) {
    return { status: "validation_error" as const, message: "Choose an entry type before saving this custom Systems entry." };
  }

  const requestedVisibility =
    normalizeVisibilityChoice(payload.visibility) ||
    normalizeVisibilityChoice(sourceState.default_visibility) ||
    customEntryDefaultVisibility(campaign);
  if (requestedVisibility === "private" && !canSetPrivateVisibility(role)) {
    return { status: "validation_error" as const, message: "Private visibility is reserved for app admins." };
  }
  if (requestedVisibility === "public" && !sourceState.public_visibility_allowed) {
    return {
      status: "validation_error" as const,
      message: `${sourceState.title} cannot be made public because that source is marked as non-public.`,
    };
  }

  let normalizedProvenance = String(payload.provenance || "").trim();
  if (normalizedProvenance.length > 500) {
    return { status: "validation_error" as const, message: "Custom Systems provenance must stay under 500 characters." };
  }
  const normalizedSearchMetadata = String(payload.search_metadata || "").trim();
  if (normalizedSearchMetadata.length > 4000) {
    return {
      status: "validation_error" as const,
      message: "Custom Systems searchable metadata must stay under 4000 characters.",
    };
  }

  let normalizedBodyMarkdown = String(payload.body_markdown || "").trim();
  let normalizedSourcePageRef = String(payload.source_page_ref || "").trim();
  let sourcePageMetadata: Record<string, unknown> = {};
  if (normalizedSourcePageRef) {
    if (normalizedSourcePageRef.length > 500) {
      return { status: "validation_error" as const, message: "Linked item page references must stay under 500 characters." };
    }
    if (normalizedEntryType !== "item") {
      return { status: "validation_error" as const, message: "Only item custom Systems entries can link item mechanics pages." };
    }
    const linkedPage = loadPublishedItemPage(database, campaign.slug, normalizedSourcePageRef);
    if (!linkedPage) {
      return { status: "validation_error" as const, message: "Choose a valid published item page before saving item mechanics." };
    }
    normalizedSourcePageRef = String(linkedPage.page_ref || "").trim();
    sourcePageMetadata = asRecord(parseJsonValue(linkedPage.metadata_json, {}));
    if (!normalizedBodyMarkdown) {
      normalizedBodyMarkdown = String(linkedPage.body_markdown || "").trim();
    }
    if (!normalizedProvenance) {
      normalizedProvenance = `Published item page: ${String(linkedPage.title || "").trim() || normalizedSourcePageRef}`;
    }
  }

  if (!normalizedBodyMarkdown) {
    return { status: "validation_error" as const, message: "Custom Systems entries need a rendered body." };
  }
  if (normalizedBodyMarkdown.length > 100_000) {
    return { status: "validation_error" as const, message: "Custom Systems entry bodies must stay under 100,000 characters." };
  }

  const normalizedSlugLeaf = existingEntry
    ? ""
    : normalizeCustomSlugLeaf(payload.slug_leaf || normalizedTitle);
  if (!existingEntry && !normalizedSlugLeaf) {
    return { status: "validation_error" as const, message: "Choose a URL slug or title before saving a custom Systems entry." };
  }

  const slug = existingEntry ? existingEntry.slug : `${sourceId.toLowerCase()}-${normalizedSlugLeaf}`;
  const entryKey = existingEntry
    ? existingEntry.entry_key
    : `${librarySlug.toLowerCase()}|custom|${campaign.slug}|${normalizedSlugLeaf}`;
  const renderedHtml = renderCustomEntryMarkdown(normalizedBodyMarkdown);
  const searchText = [normalizedTitle, normalizedEntryType, sourceId, normalizedProvenance, normalizedSearchMetadata]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const metadata: Record<string, unknown> = {
    custom_campaign_slug: campaign.slug,
    provenance: normalizedProvenance,
    search_metadata: normalizedSearchMetadata,
    body_format: "markdown",
    body_markdown: normalizedBodyMarkdown,
    updated_by_user_id: actorUserId,
  };
  const body: Record<string, unknown> = {
    markdown: normalizedBodyMarkdown,
  };

  if (normalizedEntryType === "item") {
    const itemMetadata = buildCampaignItemMechanicsMetadata(
      normalizedTitle,
      normalizedSourcePageRef,
      payload.item_mechanics_review_status || payload.mechanics_review_status,
      payload.item_mechanics,
      sourcePageMetadata,
    );
    Object.assign(metadata, itemMetadata);
    body.item_mechanics = asRecord(itemMetadata.campaign_item_mechanics);
  }

  if (librarySlug.trim().toLowerCase() === "xianxia") {
    stampXianxiaCustomEntryMetadata(metadata, body, normalizedEntryType, slug, normalizedTitle);
  }

  return {
    status: "ok" as const,
    entryKey,
    entryType: normalizedEntryType,
    slug,
    title: normalizedTitle,
    provenance: normalizedProvenance,
    searchText,
    visibility: requestedVisibility,
    metadata,
    body,
    renderedHtml,
  };
}

function serializeMutatedCustomEntry(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  role: FixtureSystemsRole,
  systemsScopeVisibility: string,
  entry: SystemsEntryRow,
  override: SystemsEntryOverride,
  sourceState: SystemsSourceState,
): SerializedCustomEntry {
  const refreshedEntry = loadEntryBySlug(database, entry.library_slug, entry.slug) || entry;
  return serializeCustomEntry(campaign, role, systemsScopeVisibility, refreshedEntry, override, sourceState);
}

function buildCustomEntryMutationResponse(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  entry: SerializedCustomEntry,
): CustomSystemsEntryMutationResult {
  return {
    status: "ok",
    entry,
    systems: buildDmContentSystemsPayload(dbPath, campaign, campaignConfig, role),
  };
}

function customEntryMutationErrorMessage(error: unknown): string {
  if (isNoSuchTableError(error)) {
    return "Systems database is unavailable.";
  }
  return error instanceof Error ? error.message : String(error);
}

export function createCustomSystemsEntry(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  actorUserId: number,
  payload: Record<string, unknown>,
): CustomSystemsEntryMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Systems database is unavailable." };
  }
  const librarySlug = String(campaign.systems_library_slug || "").trim();
  if (!librarySlug) {
    return { status: "validation_error", message: "That campaign does not have a systems library configured." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const now = utcIsoTimestamp();
    let serializedEntry: SerializedCustomEntry | null = null;
    const writeChanges = database.transaction(() => {
      const source = ensureCustomCampaignSource(database, campaign, campaignConfig, role, librarySlug, actorUserId, now);
      if (source.status === "validation_error") {
        throw new Error(source.message);
      }
      const prepared = prepareCustomEntryWrite(
        database,
        campaign,
        librarySlug,
        source.sourceState,
        source.sourceId,
        actorUserId,
        role,
        payload,
        null,
      );
      if (prepared.status === "validation_error") {
        throw new Error(prepared.message);
      }
      if (loadEntryBySlug(database, librarySlug, prepared.slug)) {
        throw new Error("That custom Systems entry slug is already in use.");
      }
      upsertCustomSystemsEntryRow(database, {
        librarySlug,
        sourceId: source.sourceId,
        entryKey: prepared.entryKey,
        entryType: prepared.entryType,
        slug: prepared.slug,
        title: prepared.title,
        provenance: prepared.provenance,
        searchText: prepared.searchText,
        visibility: prepared.visibility,
        metadata: prepared.metadata,
        body: prepared.body,
        renderedHtml: prepared.renderedHtml,
        now,
      });
      const entry = loadEntryBySlug(database, librarySlug, prepared.slug);
      if (!entry) {
        throw new Error("Failed to reload custom Systems entry.");
      }
      const override = upsertCampaignEntryOverrideForCustomEntry(
        database,
        campaign.slug,
        librarySlug,
        entry.entry_key,
        prepared.visibility,
        null,
        actorUserId,
        now,
      );
      insertCustomEntryAuditEvent(database, actorUserId, campaign.slug, "campaign_systems_custom_entry_created", entry, now);
      const systemsScopeVisibility = loadEffectiveSystemsScopeVisibility(database, campaign);
      serializedEntry = serializeMutatedCustomEntry(database, campaign, role, systemsScopeVisibility, entry, override, source.sourceState);
    });
    try {
      writeChanges();
    } catch (error) {
      return { status: "validation_error", message: customEntryMutationErrorMessage(error) };
    }
    return buildCustomEntryMutationResponse(dbPath, campaign, campaignConfig, role, serializedEntry!);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "validation_error", message: "Systems database is unavailable." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function importCampaignItemMechanics(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  actorUserId: number,
  payload: Record<string, unknown>,
): CustomSystemsEntryMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Systems database is unavailable." };
  }
  const librarySlug = String(campaign.systems_library_slug || "").trim();
  if (!librarySlug) {
    return { status: "validation_error", message: "That campaign does not have a systems library configured." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const rawPageRef = String(payload.page_ref || "").trim();
    const page = loadPublishedItemPage(database, campaign.slug, rawPageRef);
    if (!page) {
      return { status: "validation_error", message: "Choose a valid published item page before importing item mechanics." };
    }
    const title = String(page.title || "").trim() || String(page.page_ref || "").trim();
    if (!title) {
      return { status: "validation_error", message: "Published item pages need a title before they can be imported." };
    }
    const bodyMarkdown = String(page.body_markdown || "").trim();
    if (!bodyMarkdown) {
      return { status: "validation_error", message: "Published item pages need a body before they can be imported." };
    }

    const normalizedPageRef = String(page.page_ref || rawPageRef || "").trim();
    const slugLeaf = normalizeCustomSlugLeaf(title);
    if (!slugLeaf) {
      return { status: "validation_error", message: "Published item pages need a usable title before they can be imported." };
    }

    const now = utcIsoTimestamp();
    let serializedEntry: SerializedCustomEntry | null = null;
    const writeChanges = database.transaction(() => {
      const source = ensureCustomCampaignSource(database, campaign, campaignConfig, role, librarySlug, actorUserId, now);
      if (source.status === "validation_error") {
        throw new Error(source.message);
      }

      let existingEntry = loadCustomItemEntryByLinkedPage(database, campaign, librarySlug, normalizedPageRef);
      const slug = `${source.sourceId.toLowerCase()}-${slugLeaf}`;
      const existingSlugEntry = loadEntryBySlug(database, librarySlug, slug);
      if (!existingEntry && existingSlugEntry) {
        if (!isCampaignCustomEntry(campaign.slug, parseMetadata(existingSlugEntry))) {
          throw new Error("That imported item Systems slug is already in use.");
        }
        existingEntry = existingSlugEntry;
      }

      const existingOverride = existingEntry
        ? loadCampaignEntryOverrides(database, campaign.slug, librarySlug).get(existingEntry.entry_key)
        : undefined;
      const requestedVisibility =
        String(payload.visibility || "").trim() ||
        existingOverride?.visibility_override ||
        customEntryDefaultVisibility(campaign);
      const pageSourceRef = String(page.source_ref || "").trim();
      const prepared = prepareCustomEntryWrite(
        database,
        campaign,
        librarySlug,
        source.sourceState,
        source.sourceId,
        actorUserId,
        role,
        {
          title,
          entry_type: "item",
          provenance: pageSourceRef || `Published item page: ${title}`,
          visibility: requestedVisibility,
          search_metadata: normalizedPageRef,
          body_markdown: bodyMarkdown,
          source_page_ref: normalizedPageRef,
          item_mechanics_review_status: payload.item_mechanics_review_status || payload.mechanics_review_status || "",
          item_mechanics: asRecord(payload.item_mechanics),
        },
        existingEntry,
      );
      if (prepared.status === "validation_error") {
        throw new Error(prepared.message);
      }
      upsertCustomSystemsEntryRow(database, {
        librarySlug,
        sourceId: existingEntry?.source_id || source.sourceId,
        entryKey: prepared.entryKey,
        entryType: prepared.entryType,
        slug: prepared.slug,
        title: prepared.title,
        provenance: prepared.provenance,
        searchText: prepared.searchText,
        visibility: prepared.visibility,
        metadata: prepared.metadata,
        body: prepared.body,
        renderedHtml: prepared.renderedHtml,
        now,
      });
      const entry = loadEntryBySlug(database, librarySlug, prepared.slug);
      if (!entry) {
        throw new Error("Failed to reload custom Systems entry.");
      }
      const override = upsertCampaignEntryOverrideForCustomEntry(
        database,
        campaign.slug,
        librarySlug,
        entry.entry_key,
        prepared.visibility,
        existingOverride?.is_enabled_override ?? null,
        actorUserId,
        now,
      );
      insertItemMechanicsImportAuditEvent(database, actorUserId, campaign.slug, entry, rawPageRef, now);
      const systemsScopeVisibility = loadEffectiveSystemsScopeVisibility(database, campaign);
      serializedEntry = serializeMutatedCustomEntry(database, campaign, role, systemsScopeVisibility, entry, override, source.sourceState);
    });
    try {
      writeChanges();
    } catch (error) {
      return { status: "validation_error", message: customEntryMutationErrorMessage(error) };
    }
    return buildCustomEntryMutationResponse(dbPath, campaign, campaignConfig, role, serializedEntry!);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "validation_error", message: "Systems database is unavailable." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function updateCustomSystemsEntry(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  actorUserId: number,
  entrySlug: string,
  payload: Record<string, unknown>,
): CustomSystemsEntryMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Systems database is unavailable." };
  }
  const librarySlug = String(campaign.systems_library_slug || "").trim();
  if (!librarySlug) {
    return { status: "validation_error", message: "That campaign does not have a systems library configured." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const context = existingCustomEntryContext(
      database,
      campaign,
      campaignConfig,
      role,
      librarySlug,
      entrySlug,
      "Choose a valid custom Systems entry before saving.",
    );
    if (context.status === "validation_error") {
      return context;
    }
    const now = utcIsoTimestamp();
    let serializedEntry: SerializedCustomEntry | null = null;
    const writeChanges = database.transaction(() => {
      upsertCampaignSystemsPolicyForCustomEntry(database, campaign.slug, librarySlug, actorUserId, now);
      const prepared = prepareCustomEntryWrite(
        database,
        campaign,
        librarySlug,
        context.sourceState,
        context.entry.source_id,
        actorUserId,
        role,
        payload,
        context.entry,
      );
      if (prepared.status === "validation_error") {
        throw new Error(prepared.message);
      }
      const existingSlugEntry = loadEntryBySlug(database, librarySlug, prepared.slug);
      if (existingSlugEntry && existingSlugEntry.entry_key !== prepared.entryKey) {
        throw new Error("That custom Systems entry slug is already in use.");
      }
      const existingOverride = loadCampaignEntryOverrides(database, campaign.slug, librarySlug).get(context.entry.entry_key);
      upsertCustomSystemsEntryRow(database, {
        librarySlug,
        sourceId: context.entry.source_id,
        entryKey: prepared.entryKey,
        entryType: prepared.entryType,
        slug: prepared.slug,
        title: prepared.title,
        provenance: prepared.provenance,
        searchText: prepared.searchText,
        visibility: prepared.visibility,
        metadata: prepared.metadata,
        body: prepared.body,
        renderedHtml: prepared.renderedHtml,
        now,
      });
      const entry = loadEntryBySlug(database, librarySlug, prepared.slug);
      if (!entry) {
        throw new Error("Failed to reload custom Systems entry.");
      }
      const override = upsertCampaignEntryOverrideForCustomEntry(
        database,
        campaign.slug,
        librarySlug,
        entry.entry_key,
        prepared.visibility,
        existingOverride?.is_enabled_override ?? null,
        actorUserId,
        now,
      );
      insertCustomEntryAuditEvent(database, actorUserId, campaign.slug, "campaign_systems_custom_entry_updated", entry, now);
      const systemsScopeVisibility = loadEffectiveSystemsScopeVisibility(database, campaign);
      serializedEntry = serializeMutatedCustomEntry(database, campaign, role, systemsScopeVisibility, entry, override, context.sourceState);
    });
    try {
      writeChanges();
    } catch (error) {
      return { status: "validation_error", message: customEntryMutationErrorMessage(error) };
    }
    return buildCustomEntryMutationResponse(dbPath, campaign, campaignConfig, role, serializedEntry!);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "validation_error", message: "Systems database is unavailable." };
    }
    throw error;
  } finally {
    database.close();
  }
}

function setCustomSystemsEntryArchivedState(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  actorUserId: number,
  entrySlug: string,
  archived: boolean,
): CustomSystemsEntryMutationResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "Systems database is unavailable." };
  }
  const librarySlug = String(campaign.systems_library_slug || "").trim();
  if (!librarySlug) {
    return { status: "validation_error", message: "That campaign does not have a systems library configured." };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const invalidMessage = archived
      ? "Choose a valid custom Systems entry before archiving."
      : "Choose a valid custom Systems entry before restoring.";
    const context = existingCustomEntryContext(database, campaign, campaignConfig, role, librarySlug, entrySlug, invalidMessage);
    if (context.status === "validation_error") {
      return context;
    }
    const now = utcIsoTimestamp();
    let serializedEntry: SerializedCustomEntry | null = null;
    const writeChanges = database.transaction(() => {
      upsertCampaignSystemsPolicyForCustomEntry(database, campaign.slug, librarySlug, actorUserId, now);
      const existingOverride = loadCampaignEntryOverrides(database, campaign.slug, librarySlug).get(context.entry.entry_key);
      const override = upsertCampaignEntryOverrideForCustomEntry(
        database,
        campaign.slug,
        librarySlug,
        context.entry.entry_key,
        existingOverride?.visibility_override ?? null,
        archived ? false : null,
        actorUserId,
        now,
      );
      insertCustomEntryAuditEvent(
        database,
        actorUserId,
        campaign.slug,
        archived ? "campaign_systems_custom_entry_archived" : "campaign_systems_custom_entry_restored",
        context.entry,
        now,
      );
      const systemsScopeVisibility = loadEffectiveSystemsScopeVisibility(database, campaign);
      serializedEntry = serializeMutatedCustomEntry(
        database,
        campaign,
        role,
        systemsScopeVisibility,
        context.entry,
        override,
        context.sourceState,
      );
    });
    writeChanges();
    return buildCustomEntryMutationResponse(dbPath, campaign, campaignConfig, role, serializedEntry!);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "validation_error", message: "Systems database is unavailable." };
    }
    throw error;
  } finally {
    database.close();
  }
}

export function archiveCustomSystemsEntry(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  actorUserId: number,
  entrySlug: string,
): CustomSystemsEntryMutationResult {
  return setCustomSystemsEntryArchivedState(dbPath, campaign, campaignConfig, role, actorUserId, entrySlug, true);
}

export function restoreCustomSystemsEntry(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  actorUserId: number,
  entrySlug: string,
): CustomSystemsEntryMutationResult {
  return setCustomSystemsEntryArchivedState(dbPath, campaign, campaignConfig, role, actorUserId, entrySlug, false);
}

function serializeImportRun(row: SystemsImportRunRow) {
  const summary = asRecord(parseJsonValue(row.summary_json, {}));
  const importedByType = asRecord(summary.imported_by_type);
  const typeSummary = Object.keys(importedByType)
    .sort()
    .map((entryType) => ({
      entry_type: entryType,
      entry_type_label: SYSTEMS_ENTRY_TYPE_LABELS[entryType] || entryType.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()),
      count: importedByType[entryType],
    }));
  const sourceFiles = Array.isArray(summary.source_files) ? summary.source_files : [];

  return {
    id: Number(row.id),
    library_slug: String(row.library_slug || ""),
    source_id: String(row.source_id || ""),
    status: String(row.status || ""),
    import_version: String(row.import_version || ""),
    imported_count: summary.imported_count,
    type_summary: typeSummary,
    source_files: sourceFiles,
    source_file_count: Array.isArray(summary.source_files) ? sourceFiles.length : null,
    error: String(summary.error || ""),
    started_at: String(row.started_at || ""),
    completed_at: row.completed_at === null ? null : String(row.completed_at || ""),
    started_by_user_id: row.started_by_user_id === null ? null : Number(row.started_by_user_id),
  };
}

function loadImportRunRows(database: SqliteDatabase, librarySlug: string) {
  if (!librarySlug || !tableExists(database, "systems_import_runs")) {
    return [];
  }
  const rows = database
    .prepare(
      `
        SELECT
          id,
          library_slug,
          source_id,
          status,
          import_version,
          summary_json,
          started_at,
          completed_at,
          started_by_user_id
        FROM systems_import_runs
        WHERE library_slug = ?
        ORDER BY started_at DESC, id DESC
        LIMIT 10
      `,
    )
    .all(librarySlug) as SystemsImportRunRow[];
  return rows.map(serializeImportRun);
}

function entryTypeChoices(entryTypes: string[]) {
  return [...entryTypes].sort(compareEntryTypes).map((entryType) => ({
    value: entryType,
    label: SYSTEMS_ENTRY_TYPE_LABELS[entryType] || entryTypeLabel(entryType),
  }));
}

function emptyManagementPayload(campaign: CampaignViewModel, role: FixtureSystemsRole) {
  const includePrivate = canSetPrivateVisibility(role);
  const customVisibility = customEntryDefaultVisibility(campaign);
  return {
    campaign,
    library: null,
    systems_library: campaign.systems_library_slug || "",
    systems_scope_visibility_label: VISIBILITY_LABELS.players,
    policy: {
      allow_dm_shared_core_entry_edits: false,
      proprietary_acknowledged: false,
    },
    source_rows: [],
    source_count: 0,
    has_proprietary_sources: false,
    entry_override_rows: [],
    entry_override_count: 0,
    campaign_item_page_rows: [],
    custom_entry_source_rows: [],
    custom_entry_count: 0,
    custom_entry_default_visibility: customVisibility,
    custom_entry_type_choices: entryTypeChoices(Object.keys(SYSTEMS_ENTRY_TYPE_LABELS)),
    custom_entry_visibility_choices: visibilityChoices(includePrivate),
    import_source_choices: [],
    import_entry_type_choices: entryTypeChoices(DND5E_IMPORT_ENTRY_TYPES),
    import_run_rows: [],
    import_run_count: 0,
    supports_dnd5e_import: String(campaign.systems_library_slug || "").trim().toLowerCase() === "dnd-5e",
    permissions: {
      can_manage_systems: canManageSystems(role),
      can_import_shared_systems: role === "admin",
      can_set_private_visibility: includePrivate,
      can_manage_shared_core_entry_edit_permission: role === "admin",
    },
    links: {
      flask_systems_lane_url: `/campaigns/${campaign.slug}/dm-content/systems`,
      flask_systems_control_url: `/campaigns/${campaign.slug}/systems/control-panel`,
    },
  };
}

export function buildDmContentSystemsPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
) {
  const baseline = emptyManagementPayload(campaign, role);
  if (!existsSync(dbPath)) {
    return baseline;
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true, readonly: true });
  try {
    const policy = loadPolicy(database, campaign.slug);
    const librarySlug = policy?.library_slug || campaign.systems_library_slug || "";
    const library = loadLibrary(database, librarySlug);
    const systemsScopeVisibility = loadEffectiveSystemsScopeVisibility(database, campaign);
    const sourceRows = sourceRowsForManagement(database, campaign, campaignConfig, role, librarySlug, systemsScopeVisibility);
    const sourceRowsForPayload = sourceRows.map((source) => source as SystemsSourceState);
    const importRunRows = loadImportRunRows(database, librarySlug);
    const entryOverrideRows = loadEntryOverrideRows(
      database,
      campaign.slug,
      librarySlug,
      sourceRowsForPayload,
      role,
      systemsScopeVisibility,
    );
    const customEntries = loadCustomEntrySourceRows(
      database,
      campaign,
      librarySlug,
      sourceRowsForPayload,
      role,
      systemsScopeVisibility,
    );

    return {
      ...baseline,
      library,
      systems_library: librarySlug,
      systems_scope_visibility_label: visibilityLabel(systemsScopeVisibility, systemsScopeVisibility),
      policy: {
        allow_dm_shared_core_entry_edits: Boolean(policy?.allow_dm_shared_core_entry_edits),
        proprietary_acknowledged: Boolean(policy?.proprietary_acknowledged_at),
      },
      source_rows: sourceRows,
      source_count: sourceRows.length,
      has_proprietary_sources: sourceRows.some((source) => source.license_class === "proprietary_private"),
      entry_override_rows: entryOverrideRows,
      entry_override_count: entryOverrideRows.length,
      campaign_item_page_rows: loadCampaignItemPageRows(database, campaign, librarySlug, sourceRowsForPayload),
      custom_entry_source_rows: customEntries.custom_entry_source_rows,
      custom_entry_count: customEntries.custom_entry_count,
      import_source_choices: sourceRows
        .filter((source) => source.source_id !== "RULES" && source.license_class !== "custom_campaign")
        .map((source) => ({
          source_id: source.source_id,
          title: source.title,
          license_class_label: source.license_class_label,
          entry_count: source.entry_count,
        })),
      import_run_rows: importRunRows,
      import_run_count: importRunRows.length,
      supports_dnd5e_import: librarySlug.trim().toLowerCase() === "dnd-5e",
    };
  } finally {
    database.close();
  }
}
