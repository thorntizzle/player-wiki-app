import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";
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

type SqliteDatabase = Database.Database;

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

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
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
