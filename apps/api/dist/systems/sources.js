import { existsSync } from "node:fs";
import Database from "better-sqlite3";
const LICENSE_CLASS_LABELS = {
    app_reference: "App-authored reference",
    proprietary_private: "Proprietary - private campaign use",
    srd_cc: "SRD - Creative Commons",
    open_license: "Open license",
    custom_campaign: "Custom campaign",
};
const VISIBILITY_VALUES = new Set(["public", "players", "dm", "private"]);
export const SYSTEMS_ENTRY_TYPE_LABELS = {
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
export const SYSTEMS_ENTRY_TYPE_ORDER = [
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
];
const SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES = new Set(["classfeature", "optionalfeature", "subclassfeature"]);
const RULES_REFERENCE_ENTRY_TYPES = new Set(["book", "rule"]);
const DND_SOURCE_ORDER = ["RULES", "PHB", "DMG", "MM", "VGM", "SCAG", "XGE", "TCE"];
function titleCaseFallback(value) {
    return value
        .replace(/_/g, " ")
        .replace(/\b\w/g, (character) => character.toUpperCase());
}
function asRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value)
        ? value
        : {};
}
function asBoolean(value) {
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
function utcIsoTimestamp(date = new Date()) {
    return date.toISOString().replace("Z", "+00:00");
}
function normalizeVisibility(value, fallback = "dm") {
    const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
    return VISIBILITY_VALUES.has(normalized) ? normalized : fallback;
}
export function entryTypeLabel(entryType) {
    const normalized = String(entryType || "").trim().toLowerCase();
    return SYSTEMS_ENTRY_TYPE_LABELS[normalized] || titleCaseFallback(normalized.replace(/-/g, " "));
}
export function entryTypeSortKey(entryType) {
    const normalized = String(entryType || "").trim().toLowerCase();
    const index = SYSTEMS_ENTRY_TYPE_ORDER.indexOf(normalized);
    return [index >= 0 ? index : SYSTEMS_ENTRY_TYPE_ORDER.length, normalized];
}
function clampVisibilityForSource(source, visibility) {
    if (visibility === "public" && !Boolean(source.public_visibility_allowed)) {
        return "players";
    }
    return visibility;
}
export function parseSourceSeeds(campaignConfig) {
    const seeds = new Map();
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
export function serializeLibrary(row) {
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
function canManageSystems(role) {
    return role === "dm" || role === "admin";
}
function supportsCombatTracker(system) {
    const normalized = String(system || "").trim().toLowerCase().replace(/\s+/g, "-");
    return normalized === "dnd-5e";
}
function canAccessSource(role, isEnabled, visibility) {
    if (canManageSystems(role)) {
        return true;
    }
    if (!isEnabled) {
        return false;
    }
    return visibility === "public" || visibility === "players";
}
export function serializeSourceState(row, seed, role) {
    const isConfigured = row.configured_enabled !== null || Boolean(row.configured_visibility);
    const seededEnabled = seed?.enabled ?? false;
    const isEnabled = isConfigured ? Boolean(row.configured_enabled) : seededEnabled;
    const fallbackVisibility = seed?.default_visibility || "dm";
    const configuredVisibility = row.configured_visibility || "";
    const defaultVisibility = clampVisibilityForSource(row, normalizeVisibility(isConfigured ? configuredVisibility : fallbackVisibility, "dm"));
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
function emptyPayload(campaign, canManage) {
    return {
        campaign,
        library: null,
        sources: [],
        permissions: {
            can_manage_systems: canManage,
        },
    };
}
function emptyIndexPayload(campaign, canManage, query = "", referenceQuery = "") {
    return {
        campaign,
        library: null,
        query,
        reference_query: referenceQuery,
        sources: [],
        search_results: [],
        has_rules_reference_search: false,
        rules_reference_results: [],
        source_scoped_rules_reference_sources: [],
        permissions: {
            can_manage_systems: canManage,
        },
    };
}
export function isNoSuchTableError(error) {
    return error instanceof Error && error.message.includes("no such table");
}
export function parseJsonValue(rawValue, fallback = {}) {
    try {
        return JSON.parse(rawValue || "null") ?? fallback;
    }
    catch {
        return fallback;
    }
}
export function parseMetadata(row) {
    return asRecord(parseJsonValue(row.metadata_json, {}));
}
export function serializeEntrySummary(row) {
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
function serializeEntryOverride(row) {
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
function serializeEntryRecord(row, sourceState, override) {
    return {
        ...serializeEntrySummary(row),
        metadata: parseMetadata(row),
        body: parseJsonValue(row.body_json, {}),
        rendered_html: String(row.rendered_html || ""),
        source_state: sourceState,
        override,
    };
}
function coerceWriteBool(value) {
    if (typeof value === "boolean") {
        return value;
    }
    if (typeof value === "number" && Number.isInteger(value) && (value === 0 || value === 1)) {
        return Boolean(value);
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
function coerceSortableInt(value, fallback) {
    const parsed = Number.parseInt(String(value || "").trim(), 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}
function coerceInt(value, fallback = 0) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}
function extractMonsterHpAverage(value) {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        return coerceInt(value.average, 0);
    }
    return coerceInt(value, 0);
}
function extractMaxDistance(value) {
    if (typeof value === "number") {
        return Math.trunc(value);
    }
    if (typeof value === "string") {
        const distances = [...value.matchAll(/\d+/g)].map((match) => Number.parseInt(match[0] || "", 10));
        return distances.length > 0 ? Math.max(...distances.filter(Number.isFinite)) : 0;
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
function formatSpeedLabel(value) {
    if (typeof value === "number") {
        return `${Math.trunc(value)} ft.`;
    }
    if (typeof value === "string") {
        return value.trim();
    }
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        const record = value;
        const parts = [];
        for (const movementType of ["walk", "burrow", "climb", "fly", "swim"]) {
            if (!Object.hasOwn(record, movementType)) {
                continue;
            }
            const movementValue = record[movementType];
            const renderedValue = movementValue === true
                ? "equal to walking speed"
                : extractMaxDistance(movementValue)
                    ? `${extractMaxDistance(movementValue)} ft.`
                    : String(movementValue || "").trim();
            parts.push(`${titleCaseFallback(movementType)} ${renderedValue}`.trim());
        }
        return parts.join(", ");
    }
    return "";
}
function entrySourceBrowseSortKey(row) {
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
function compareEntryRowsForBrowse(left, right) {
    const leftKey = entrySourceBrowseSortKey(left);
    const rightKey = entrySourceBrowseSortKey(right);
    for (let index = 0; index < leftKey.length; index += 1) {
        const leftValue = leftKey[index];
        const rightValue = rightKey[index];
        if (typeof leftValue === "number" && typeof rightValue === "number") {
            if (leftValue !== rightValue) {
                return leftValue - rightValue;
            }
        }
        else {
            const comparison = String(leftValue).localeCompare(String(rightValue));
            if (comparison !== 0) {
                return comparison;
            }
        }
    }
    return 0;
}
function filterAccessibleEntryRows(rows, role) {
    if (canManageSystems(role)) {
        return rows;
    }
    return rows.filter((row) => Boolean(row.player_safe_default) && !Boolean(row.dm_heavy));
}
function buildEntryGroups(rows) {
    const counts = new Map();
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
function entryMatchesCategoryQuery(row, query) {
    const terms = normalizeLookup(query).split(/\s+/).filter(Boolean);
    if (terms.length === 0) {
        return true;
    }
    const title = String(row.title || "").toLowerCase();
    const entryType = String(row.entry_type || "").toLowerCase();
    return terms.every((term) => title.includes(term) || entryType.includes(term));
}
function loadAccessibleSourceEntries(database, librarySlug, sourceId, role, options = {}) {
    const rows = database
        .prepare(`
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
      `)
        .all(librarySlug, sourceId);
    const normalizedEntryType = String(options.entryType || "").trim().toLowerCase();
    const filteredRows = normalizedEntryType
        ? rows.filter((row) => String(row.entry_type || "").trim().toLowerCase() === normalizedEntryType)
        : rows;
    return filterAccessibleEntryRows(filteredRows, role)
        .filter((row) => entryMatchesCategoryQuery(row, options.query || ""))
        .sort(compareEntryRowsForBrowse);
}
function loadCampaignEntryOverride(database, campaignSlug, entryKey) {
    try {
        return serializeEntryOverride(database
            .prepare(`
            SELECT
              entry_key,
              visibility_override,
              is_enabled_override,
              updated_at,
              updated_by_user_id
            FROM campaign_entry_overrides
            WHERE campaign_slug = ?
              AND entry_key = ?
          `)
            .get(campaignSlug, entryKey));
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return null;
        }
        throw error;
    }
}
export function loadCampaignEntryOverrides(database, campaignSlug, librarySlug) {
    const overrides = new Map();
    try {
        const rows = database
            .prepare(`
          SELECT
            entry_key,
            visibility_override,
            is_enabled_override,
            updated_at,
            updated_by_user_id
          FROM campaign_entry_overrides
          WHERE campaign_slug = ?
            AND library_slug = ?
        `)
            .all(campaignSlug, librarySlug);
        for (const row of rows) {
            const override = serializeEntryOverride(row);
            if (override) {
                overrides.set(override.entry_key, override);
            }
        }
    }
    catch (error) {
        if (!isNoSuchTableError(error)) {
            throw error;
        }
    }
    return overrides;
}
export function loadSourceRows(database, campaignSlug, librarySlug) {
    return database
        .prepare(`
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
      `)
        .all(campaignSlug, librarySlug);
}
function loadCampaignSystemsPolicy(database, campaignSlug) {
    return database
        .prepare(`
        SELECT
          campaign_slug,
          library_slug,
          status,
          allow_dm_shared_core_entry_edits,
          proprietary_acknowledged_at,
          proprietary_acknowledged_by_user_id,
          created_at,
          updated_at,
          updated_by_user_id
        FROM campaign_system_policies
        WHERE campaign_slug = ?
      `)
        .get(campaignSlug);
}
function loadEntryByKey(database, librarySlug, entryKey) {
    return database
        .prepare(`
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
          AND entry_key = ?
      `)
        .get(librarySlug, entryKey);
}
function upsertCampaignSystemsPolicy(database, { campaignSlug, librarySlug, actorUserId, now, proprietaryAcknowledgedAt, }) {
    const existing = loadCampaignSystemsPolicy(database, campaignSlug);
    database
        .prepare(`
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(campaign_slug) DO UPDATE SET
          library_slug = excluded.library_slug,
          status = excluded.status,
          allow_dm_shared_core_entry_edits = excluded.allow_dm_shared_core_entry_edits,
          proprietary_acknowledged_at = excluded.proprietary_acknowledged_at,
          proprietary_acknowledged_by_user_id = excluded.proprietary_acknowledged_by_user_id,
          updated_at = excluded.updated_at,
          updated_by_user_id = excluded.updated_by_user_id
      `)
        .run(campaignSlug, librarySlug, "active", existing?.allow_dm_shared_core_entry_edits ? 1 : 0, proprietaryAcknowledgedAt || existing?.proprietary_acknowledged_at || null, proprietaryAcknowledgedAt ? actorUserId : existing?.proprietary_acknowledged_by_user_id || null, existing?.created_at || now, now, actorUserId);
}
function upsertCampaignEnabledSource(database, { campaignSlug, librarySlug, sourceId, isEnabled, defaultVisibility, actorUserId, now, }) {
    database
        .prepare(`
        INSERT INTO campaign_enabled_sources (
          campaign_slug,
          library_slug,
          source_id,
          is_enabled,
          default_visibility,
          updated_at,
          updated_by_user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(campaign_slug, source_id) DO UPDATE SET
          library_slug = excluded.library_slug,
          is_enabled = excluded.is_enabled,
          default_visibility = excluded.default_visibility,
          updated_at = excluded.updated_at,
          updated_by_user_id = excluded.updated_by_user_id
      `)
        .run(campaignSlug, librarySlug, sourceId, isEnabled ? 1 : 0, defaultVisibility, now, actorUserId);
}
function upsertCampaignEntryOverride(database, { campaignSlug, librarySlug, entryKey, visibilityOverride, isEnabledOverride, actorUserId, now, }) {
    database
        .prepare(`
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
      `)
        .run(campaignSlug, librarySlug, entryKey, visibilityOverride, isEnabledOverride === null ? null : isEnabledOverride ? 1 : 0, now, actorUserId);
    return {
        entry_key: entryKey,
        visibility_override: visibilityOverride,
        is_enabled_override: isEnabledOverride,
        updated_at: now,
        updated_by_user_id: actorUserId,
    };
}
function insertSystemsSourceAuditEvent(database, { actorUserId, campaignSlug, librarySlug, sourceId, visibility, isEnabled, now, }) {
    database
        .prepare(`
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
      `)
        .run(actorUserId, campaignSlug, "campaign_systems_source_updated", JSON.stringify({
        library_slug: librarySlug,
        source_id: sourceId,
        visibility,
        is_enabled: isEnabled,
        source: "api",
    }), now);
}
function insertSystemsEntryOverrideAuditEvent(database, { actorUserId, campaignSlug, entryKey, visibility, now, }) {
    database
        .prepare(`
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
      `)
        .run(actorUserId, campaignSlug, "campaign_systems_entry_override_updated", JSON.stringify({
        entry_key: entryKey,
        visibility,
        source: "api",
    }), now);
}
export function updateCampaignSystemsSources(dbPath, campaign, campaignConfig, role, actorUserId, payload) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Systems database is unavailable." };
    }
    const librarySlug = String(campaign.systems_library_slug || "").trim();
    if (!librarySlug) {
        return { status: "validation_error", message: "That campaign does not have a systems library configured." };
    }
    const rawUpdates = payload.updates;
    if (!Array.isArray(rawUpdates)) {
        return { status: "validation_error", message: "updates must be an array." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
        if (!library) {
            return { status: "validation_error", message: "That campaign does not have a systems library configured." };
        }
        const seeds = parseSourceSeeds(campaignConfig);
        const currentRows = loadSourceRows(database, campaign.slug, librarySlug);
        const rowsBySourceId = new Map(currentRows.map((row) => [row.source_id, row]));
        const statesBySourceId = new Map(currentRows.map((row) => [row.source_id, serializeSourceState(row, seeds.get(row.source_id), role)]));
        const policy = loadCampaignSystemsPolicy(database, campaign.slug);
        const normalizedUpdates = [];
        let newlyEnabledProprietary = false;
        for (const rawUpdate of rawUpdates) {
            if (typeof rawUpdate !== "object" || rawUpdate === null || Array.isArray(rawUpdate)) {
                return { status: "validation_error", message: "Systems source updates must be objects." };
            }
            const record = asRecord(rawUpdate);
            const sourceId = String(record.source_id || "").trim();
            const row = rowsBySourceId.get(sourceId);
            const state = statesBySourceId.get(sourceId);
            if (!row || !state) {
                return { status: "validation_error", message: "Choose a valid systems source." };
            }
            if (typeof record.is_enabled !== "boolean") {
                return { status: "validation_error", message: "Source enablement must be true or false." };
            }
            const isEnabled = record.is_enabled;
            const requestedVisibility = normalizeVisibility(record.default_visibility, "");
            if (!VISIBILITY_VALUES.has(requestedVisibility)) {
                return { status: "validation_error", message: `Choose a valid visibility for ${row.title}.` };
            }
            if (requestedVisibility === "private" && role !== "admin") {
                return { status: "validation_error", message: "Private visibility is reserved for app admins." };
            }
            if (requestedVisibility === "public" && !Boolean(row.public_visibility_allowed)) {
                return {
                    status: "validation_error",
                    message: `${row.title} cannot be made public because that source is marked as proprietary or otherwise non-public.`,
                };
            }
            const defaultVisibility = clampVisibilityForSource(row, requestedVisibility);
            if (isEnabled &&
                !state.is_enabled &&
                row.license_class === "proprietary_private" &&
                !policy?.proprietary_acknowledged_at) {
                newlyEnabledProprietary = true;
            }
            normalizedUpdates.push({
                row,
                state,
                sourceId,
                isEnabled,
                defaultVisibility,
            });
        }
        if (newlyEnabledProprietary && !asBoolean(payload.acknowledge_proprietary)) {
            return {
                status: "validation_error",
                message: "Acknowledge the proprietary-source notice before enabling a protected systems source.",
            };
        }
        const now = utcIsoTimestamp();
        const changedUpdates = normalizedUpdates.filter((update) => update.state.is_enabled !== update.isEnabled || update.state.default_visibility !== update.defaultVisibility);
        const writeChanges = database.transaction(() => {
            upsertCampaignSystemsPolicy(database, {
                campaignSlug: campaign.slug,
                librarySlug,
                actorUserId,
                now,
                proprietaryAcknowledgedAt: newlyEnabledProprietary ? now : null,
            });
            for (const update of changedUpdates) {
                upsertCampaignEnabledSource(database, {
                    campaignSlug: campaign.slug,
                    librarySlug,
                    sourceId: update.sourceId,
                    isEnabled: update.isEnabled,
                    defaultVisibility: update.defaultVisibility,
                    actorUserId,
                    now,
                });
                insertSystemsSourceAuditEvent(database, {
                    actorUserId,
                    campaignSlug: campaign.slug,
                    librarySlug,
                    sourceId: update.sourceId,
                    visibility: update.defaultVisibility,
                    isEnabled: update.isEnabled,
                    now,
                });
            }
        });
        writeChanges();
        const refreshedRows = loadSourceRows(database, campaign.slug, librarySlug);
        return {
            status: "ok",
            sources: refreshedRows.map((row) => serializeSourceState(row, seeds.get(row.source_id), role)),
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "Systems database is unavailable." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function updateCampaignSystemsEntryOverride(dbPath, campaign, campaignConfig, role, actorUserId, entryKey, payload) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Systems database is unavailable." };
    }
    const librarySlug = String(campaign.systems_library_slug || "").trim();
    if (!librarySlug) {
        return { status: "validation_error", message: "That campaign does not have a systems library configured." };
    }
    const normalizedEntryKey = String(entryKey || "").trim();
    if (!normalizedEntryKey) {
        return { status: "validation_error", message: "Choose a valid systems entry before saving an override." };
    }
    const hasEnabledOverride = Object.hasOwn(payload, "is_enabled_override");
    let isEnabledOverride = null;
    if (hasEnabledOverride && payload.is_enabled_override !== null && payload.is_enabled_override !== undefined) {
        const parsed = coerceWriteBool(payload.is_enabled_override);
        if (parsed === undefined) {
            return { status: "validation_error", message: "is_enabled_override must be true or false." };
        }
        isEnabledOverride = parsed;
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
        if (!library) {
            return { status: "validation_error", message: "That campaign does not have a systems library configured." };
        }
        const entry = loadEntryByKey(database, librarySlug, normalizedEntryKey);
        if (!entry) {
            return { status: "validation_error", message: "Choose a valid systems entry before saving an override." };
        }
        const seeds = parseSourceSeeds(campaignConfig);
        const sourceRow = loadSourceRow(database, campaign.slug, librarySlug, entry.source_id);
        if (!sourceRow) {
            return { status: "validation_error", message: "That source is not available for this campaign." };
        }
        const sourceState = serializeSourceState(sourceRow, seeds.get(sourceRow.source_id), role);
        let visibilityOverride = null;
        if (payload.visibility_override !== null && payload.visibility_override !== undefined) {
            const requestedVisibility = String(payload.visibility_override).trim().toLowerCase();
            if (requestedVisibility) {
                if (!VISIBILITY_VALUES.has(requestedVisibility)) {
                    return { status: "validation_error", message: `Choose a valid visibility for ${sourceRow.title}.` };
                }
                if (requestedVisibility === "private" && role !== "admin") {
                    return { status: "validation_error", message: "Private visibility is reserved for app admins." };
                }
                if (requestedVisibility === "public" && !Boolean(sourceRow.public_visibility_allowed)) {
                    return {
                        status: "validation_error",
                        message: `${sourceRow.title} cannot be made public because that source is marked as proprietary or otherwise non-public.`,
                    };
                }
                visibilityOverride = requestedVisibility;
            }
        }
        const now = utcIsoTimestamp();
        let override = null;
        const writeChanges = database.transaction(() => {
            upsertCampaignSystemsPolicy(database, {
                campaignSlug: campaign.slug,
                librarySlug,
                actorUserId,
                now,
                proprietaryAcknowledgedAt: null,
            });
            override = upsertCampaignEntryOverride(database, {
                campaignSlug: campaign.slug,
                librarySlug,
                entryKey: entry.entry_key,
                visibilityOverride,
                isEnabledOverride,
                actorUserId,
                now,
            });
            insertSystemsEntryOverrideAuditEvent(database, {
                actorUserId,
                campaignSlug: campaign.slug,
                entryKey: entry.entry_key,
                visibility: visibilityOverride || "inherit",
                now,
            });
        });
        writeChanges();
        return {
            status: "ok",
            override: override,
            entry: serializeEntryRecord(entry, sourceState, override),
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "Systems database is unavailable." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function loadSourceRow(database, campaignSlug, librarySlug, sourceId) {
    return database
        .prepare(`
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
      `)
        .get(campaignSlug, librarySlug, sourceId);
}
export function loadEntriesForSources(database, librarySlug, sourceIds) {
    const cleanedSourceIds = [...new Set(sourceIds.map((sourceId) => String(sourceId || "").trim()).filter(Boolean))];
    if (cleanedSourceIds.length === 0) {
        return [];
    }
    const placeholders = cleanedSourceIds.map(() => "?").join(", ");
    return database
        .prepare(`
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
          AND source_id IN (${placeholders})
        ORDER BY title ASC, id ASC
      `)
        .all(librarySlug, ...cleanedSourceIds);
}
function loadSearchableEntriesForSources(database, librarySlug, sourceIds, entryType, query) {
    const normalizedEntryType = String(entryType || "").trim().toLowerCase();
    return loadEntriesForSources(database, librarySlug, sourceIds)
        .filter((row) => String(row.entry_type || "").trim().toLowerCase() === normalizedEntryType)
        .filter((row) => entryMatchesGlobalQuery(row, query));
}
function effectiveEntryVisibility(row, sourceState, override) {
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
function canAccessEntry(row, role, sourceState, override) {
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
function filterRowsForEntryAccess(rows, role, sourceStatesById, overridesByEntryKey) {
    return rows.filter((row) => {
        const sourceState = sourceStatesById.get(row.source_id);
        if (!sourceState) {
            return false;
        }
        return canAccessEntry(row, role, sourceState, overridesByEntryKey.get(row.entry_key) || null);
    });
}
function entryMatchesGlobalQuery(row, query) {
    const terms = normalizeLookup(query).split(/\s+/).filter(Boolean);
    if (terms.length === 0) {
        return false;
    }
    const title = String(row.title || "").toLowerCase();
    const entryType = String(row.entry_type || "").toLowerCase();
    const sourceId = String(row.source_id || "").toLowerCase();
    return terms.every((term) => title.includes(term) || entryType.includes(term) || sourceId.includes(term));
}
function sourceCatalogSortKey(sourceId) {
    const normalizedSourceId = String(sourceId || "").trim().toUpperCase();
    const index = DND_SOURCE_ORDER.indexOf(normalizedSourceId);
    return [index >= 0 ? index : DND_SOURCE_ORDER.length, normalizedSourceId];
}
function compareRulesReferenceRows(left, right) {
    const leftSourceKey = sourceCatalogSortKey(left.source_id);
    const rightSourceKey = sourceCatalogSortKey(right.source_id);
    if (leftSourceKey[0] !== rightSourceKey[0]) {
        return leftSourceKey[0] - rightSourceKey[0];
    }
    const sourceComparison = leftSourceKey[1].localeCompare(rightSourceKey[1]);
    if (sourceComparison !== 0) {
        return sourceComparison;
    }
    return compareEntryRowsForBrowse(left, right);
}
function rulesReferenceSearchScope(row) {
    return row.source_id.trim().toUpperCase() === "DMG" ? "source_only" : "global";
}
function referenceSearchValues(value) {
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
function normalizeLookup(value) {
    return value.trim().toLowerCase().replace(/\s+/g, " ");
}
function buildRulesReferenceSearchText(row) {
    const metadata = parseMetadata(row);
    const searchParts = [row.title, row.source_id, row.entry_type];
    if (row.entry_type === "book") {
        searchParts.push(String(metadata.section_label || "").trim(), ...referenceSearchValues(metadata.headers), ...referenceSearchValues(metadata.section_outline));
    }
    else if (row.entry_type === "rule") {
        searchParts.push(String(metadata.rule_key || "").trim(), String(metadata.formula || "").trim(), ...referenceSearchValues(metadata.aliases), ...referenceSearchValues(metadata.rule_facets));
    }
    searchParts.push(...referenceSearchValues(metadata.reference_terms));
    return searchParts
        .filter((part) => String(part || "").trim())
        .map((part) => normalizeLookup(String(part)))
        .join(" ");
}
function serializeRulesReferenceResult(row) {
    const metadata = parseMetadata(row);
    let referenceScope = "";
    if (row.entry_type === "book") {
        const scopeParts = [String(metadata.section_label || "").trim()];
        const chapterTitle = String(metadata.chapter_title || "").trim();
        if (chapterTitle && chapterTitle !== row.title) {
            scopeParts.push(chapterTitle);
        }
        referenceScope = scopeParts.filter(Boolean).join(" | ");
    }
    else if (row.entry_type === "rule") {
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
function serializeCombatSystemsMonsterSearchResult(row) {
    const metadata = parseMetadata(row);
    const abilities = asRecord(metadata.abilities);
    const dexScore = coerceInt(abilities.dex, 10);
    const initiativeBonus = Math.floor((dexScore - 10) / 2);
    const speed = metadata.speed;
    const movementTotal = extractMaxDistance(speed);
    const speedLabel = formatSpeedLabel(speed);
    return {
        entry_key: String(row.entry_key),
        title: String(row.title),
        source_id: String(row.source_id),
        subtitle: `HP ${extractMonsterHpAverage(metadata.hp)} - Speed ${speedLabel || `${movementTotal} ft.`}`,
        initiative_bonus: initiativeBonus > 0 ? `+${initiativeBonus}` : String(initiativeBonus),
    };
}
function buildRulesReferenceSearchMeta(rows) {
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
export function buildCombatSystemsMonsterSearchPayload(dbPath, campaign, campaignConfig, role, query = "") {
    if (!canManageSystems(role)) {
        return { status: "forbidden", message: "You do not have permission to manage combat." };
    }
    if (!supportsCombatTracker(campaign.system)) {
        return {
            status: "ok",
            payload: {
                results: [],
                message: "Combat tracker support for this campaign system is not available yet.",
            },
        };
    }
    const cleanedQuery = String(query || "").trim();
    if (cleanedQuery.length < 2) {
        return {
            status: "ok",
            payload: {
                results: [],
                message: "Type at least 2 letters to search the Systems monster list.",
            },
        };
    }
    const librarySlug = campaign.systems_library_slug || "";
    if (!librarySlug || !existsSync(dbPath)) {
        return {
            status: "ok",
            payload: {
                results: [],
                message: "No Systems monsters matched that search.",
            },
        };
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const seeds = parseSourceSeeds(campaignConfig);
        const enabledSourceStates = loadSourceRows(database, campaign.slug, librarySlug)
            .map((row) => serializeSourceState(row, seeds.get(row.source_id), role))
            .filter((state) => state.is_enabled);
        const sourceStatesById = new Map(enabledSourceStates.map((state) => [state.source_id, state]));
        const overridesByEntryKey = loadCampaignEntryOverrides(database, campaign.slug, librarySlug);
        const results = filterRowsForEntryAccess(loadSearchableEntriesForSources(database, librarySlug, enabledSourceStates.map((state) => state.source_id), "monster", cleanedQuery), role, sourceStatesById, overridesByEntryKey)
            .slice(0, 30)
            .map(serializeCombatSystemsMonsterSearchResult);
        const message = results.length === 30
            ? "Showing the first 30 matching monsters."
            : results.length > 0
                ? `Found ${results.length} matching monster${results.length === 1 ? "" : "s"}.`
                : "No Systems monsters matched that search.";
        return {
            status: "ok",
            payload: {
                results,
                message,
            },
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return {
                status: "ok",
                payload: {
                    results: [],
                    message: "No Systems monsters matched that search.",
                },
            };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function buildCampaignSystemsSourceListPayload(dbPath, campaign, campaignConfig, role) {
    const canManage = canManageSystems(role);
    const librarySlug = campaign.systems_library_slug || "";
    if (!librarySlug || !existsSync(dbPath)) {
        return emptyPayload(campaign, canManage);
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
        if (!library) {
            return emptyPayload(campaign, canManage);
        }
        const seeds = parseSourceSeeds(campaignConfig);
        const rows = loadSourceRows(database, campaign.slug, librarySlug);
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
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return emptyPayload(campaign, canManage);
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function buildCampaignSystemsIndexPayload(dbPath, campaign, campaignConfig, role, query = "", referenceQuery = "") {
    const canManage = canManageSystems(role);
    const librarySlug = campaign.systems_library_slug || "";
    const cleanedQuery = String(query || "").trim();
    const cleanedReferenceQuery = String(referenceQuery || "").trim();
    if (!librarySlug || !existsSync(dbPath)) {
        return emptyIndexPayload(campaign, canManage, cleanedQuery, cleanedReferenceQuery);
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
        if (!library) {
            return emptyIndexPayload(campaign, canManage, cleanedQuery, cleanedReferenceQuery);
        }
        const seeds = parseSourceSeeds(campaignConfig);
        const accessibleSourceStates = loadSourceRows(database, campaign.slug, librarySlug)
            .map((row) => serializeSourceState(row, seeds.get(row.source_id), role))
            .filter((state) => state.is_enabled && state.permissions.can_access);
        const sourceStatesById = new Map(accessibleSourceStates.map((state) => [state.source_id, state]));
        const sourceIds = accessibleSourceStates.map((state) => state.source_id);
        const overridesByEntryKey = loadCampaignEntryOverrides(database, campaign.slug, librarySlug);
        const accessibleRows = filterRowsForEntryAccess(loadEntriesForSources(database, librarySlug, sourceIds), role, sourceStatesById, overridesByEntryKey);
        const rulesReferenceRows = accessibleRows
            .filter((row) => RULES_REFERENCE_ENTRY_TYPES.has(row.entry_type))
            .sort(compareRulesReferenceRows);
        const sourceCards = accessibleSourceStates.map((source) => {
            const sourceRulesReferenceRows = rulesReferenceRows.filter((row) => row.source_id === source.source_id);
            return {
                ...source,
                has_rules_reference_entries: sourceRulesReferenceRows.length > 0,
                rules_reference_search_scope: rulesReferenceSearchScope(source),
            };
        });
        const globalRulesReferenceSourceIds = new Set(sourceCards
            .filter((source) => source.has_rules_reference_entries && source.rules_reference_search_scope === "global")
            .map((source) => source.source_id));
        const referenceTerms = cleanedReferenceQuery
            ? cleanedReferenceQuery.split(/\s+/).map(normalizeLookup).filter(Boolean)
            : [];
        const rulesReferenceResults = referenceTerms.length > 0
            ? rulesReferenceRows
                .filter((row) => globalRulesReferenceSourceIds.has(row.source_id))
                .filter((row) => {
                const searchText = buildRulesReferenceSearchText(row);
                return referenceTerms.every((term) => searchText.includes(term));
            })
                .slice(0, 100)
                .map(serializeRulesReferenceResult)
            : [];
        return {
            campaign,
            library,
            query: cleanedQuery,
            reference_query: cleanedReferenceQuery,
            sources: sourceCards,
            search_results: cleanedQuery
                ? accessibleRows.filter((row) => entryMatchesGlobalQuery(row, cleanedQuery)).slice(0, 250).map(serializeEntrySummary)
                : [],
            has_rules_reference_search: globalRulesReferenceSourceIds.size > 0,
            rules_reference_results: rulesReferenceResults,
            source_scoped_rules_reference_sources: sourceCards.filter((source) => source.has_rules_reference_entries && source.rules_reference_search_scope === "source_only"),
            permissions: {
                can_manage_systems: canManage,
            },
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return emptyIndexPayload(campaign, canManage, cleanedQuery, cleanedReferenceQuery);
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function searchSessionArticleSystemsSources(dbPath, campaign, campaignConfig, role, query, limit = 30) {
    const librarySlug = campaign.systems_library_slug || "";
    const cleanedQuery = String(query || "").trim();
    const safeLimit = Math.max(1, Math.trunc(limit));
    if (!librarySlug || cleanedQuery.length < 2 || !existsSync(dbPath)) {
        return [];
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
        if (!library) {
            return [];
        }
        const seeds = parseSourceSeeds(campaignConfig);
        const accessibleSourceStates = loadSourceRows(database, campaign.slug, librarySlug)
            .map((row) => serializeSourceState(row, seeds.get(row.source_id), role))
            .filter((state) => state.is_enabled && state.permissions.can_access);
        const sourceStatesById = new Map(accessibleSourceStates.map((state) => [state.source_id, state]));
        const overridesByEntryKey = loadCampaignEntryOverrides(database, campaign.slug, librarySlug);
        return filterRowsForEntryAccess(loadEntriesForSources(database, librarySlug, accessibleSourceStates.map((state) => state.source_id)), role, sourceStatesById, overridesByEntryKey)
            .filter((row) => entryMatchesGlobalQuery(row, cleanedQuery))
            .slice(0, safeLimit)
            .map((row) => {
            const label = entryTypeLabel(row.entry_type);
            const sourceId = String(row.source_id || "");
            return {
                source_ref: `systems:${String(row.slug || "")}`,
                source_kind: "systems",
                title: String(row.title || ""),
                subtitle: `${label} - ${sourceId}`,
                kind_label: "Systems",
                select_label: `${String(row.title || "")} - Systems - ${label} - ${sourceId}`,
            };
        });
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return [];
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function buildCampaignSystemsSourceDetailPayload(dbPath, campaign, campaignConfig, sourceId, role, referenceQuery = "") {
    const canManage = canManageSystems(role);
    const librarySlug = campaign.systems_library_slug || "";
    const normalizedSourceId = String(sourceId || "").trim();
    if (!librarySlug || !normalizedSourceId || !existsSync(dbPath)) {
        return { status: "not_found" };
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
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
        const entryGroups = allEntryGroups.filter((group) => !SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(group.entry_type));
        const rulesReferenceEntries = accessibleEntries.filter((entry) => RULES_REFERENCE_ENTRY_TYPES.has(entry.entry_type));
        const cleanedReferenceQuery = String(referenceQuery || "").trim();
        const normalizedReferenceTerms = cleanedReferenceQuery
            ? cleanedReferenceQuery.split(/\s+/).map(normalizeLookup).filter(Boolean)
            : [];
        const rulesReferenceResults = normalizedReferenceTerms.length > 0
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
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "not_found" };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function buildCampaignSystemsSourceCategoryPayload(dbPath, campaign, campaignConfig, sourceId, entryType, role, query = "") {
    const canManage = canManageSystems(role);
    const librarySlug = campaign.systems_library_slug || "";
    const normalizedSourceId = String(sourceId || "").trim();
    const normalizedEntryType = String(entryType || "").trim().toLowerCase();
    if (!librarySlug || !normalizedSourceId || !normalizedEntryType || !existsSync(dbPath)) {
        return { status: "not_found" };
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
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
        const entryGroups = allEntryGroups.filter((group) => !SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES.has(group.entry_type));
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
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "not_found" };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function buildCampaignSystemsEntryDetailPayload(dbPath, campaign, campaignConfig, entrySlug, role) {
    const canManage = canManageSystems(role);
    const librarySlug = campaign.systems_library_slug || "";
    const normalizedEntrySlug = String(entrySlug || "").trim();
    if (!librarySlug || !normalizedEntrySlug || !existsSync(dbPath)) {
        return { status: "not_found" };
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        const library = serializeLibrary(database
            .prepare(`
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `)
            .get(librarySlug));
        if (!library) {
            return { status: "not_found" };
        }
        const entry = database
            .prepare(`
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
        `)
            .get(librarySlug, normalizedEntrySlug);
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
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "not_found" };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
