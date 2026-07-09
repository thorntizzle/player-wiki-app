import { existsSync } from "node:fs";
import Database from "better-sqlite3";
const XIANXIA_SYSTEM_CODE = "xianxia";
const XIANXIA_DAO_IMMOLATING_INSIGHT_COST = 10;
const DND_CURRENCY_KEYS = ["cp", "sp", "ep", "gp", "pp"];
const XIANXIA_ENERGY_KEYS = ["jing", "qi", "shen"];
const XIANXIA_ENERGY_LABELS = {
    jing: "Jing",
    qi: "Qi",
    shen: "Shen",
};
const XIANXIA_CURRENCY_KEYS = ["coin", "supply", "spirit_stones"];
const VALID_HIT_DIE_FACES = new Set([4, 6, 8, 10, 12]);
const CHARACTER_STATE_CONFLICT_MESSAGE = "This sheet changed in another session. Refresh and try again.";
const CHARACTER_SHEET_EDIT_CONFLICT_MESSAGE = "This sheet changed before your batch save finished. Refresh and review the latest sheet before saving again. Session Character, Combat, or another tab may have changed nearby fields first; nothing was auto-merged.";
const CAMPAIGN_ITEMS_SECTION = "Items";
const ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND = "manual_edit";
const ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY = "custom_feature";
const ADVANCED_EDITOR_CUSTOM_FEATURE_RESOURCE_PREFIX = "custom_feature";
const ARTIFICER_INFUSIONS_FEATURE_KEY = "artificerinfusions";
const ENHANCED_DEFENSE_INFUSION_KEY = "enhanced-defense";
const KNOWN_ARTIFICER_INFUSION_TITLES = new Set([
    "arcanepropulsionarmor",
    "armorofmagicalstrength",
    "bootsofthewindingpath",
    "enhancedarcanefocus",
    "enhanceddefense",
    "enhancedweapon",
    "helmofawareness",
    "homunculusservant",
    "mindsharpener",
    "radiantweapon",
    "repeatingshot",
    "replicatemagicitem",
    "repulsionshield",
    "resistantarmor",
    "returningweapon",
    "spellrefuelingring",
]);
const ARTIFICER_INFUSION_KNOWN_CAPACITY_BY_LEVEL = [
    [18, 12],
    [14, 10],
    [10, 8],
    [6, 6],
    [2, 4],
];
const ARTIFICER_INFUSION_ACTIVE_CAPACITY_BY_LEVEL = [
    [18, 6],
    [14, 5],
    [10, 4],
    [6, 3],
    [2, 2],
];
const CAMPAIGN_ITEM_PAGE_SUPPORT_METADATA_KEYS = new Set([
    "ability_score_minimums",
    "attack_reminder_rules",
    "attunement",
    "base_item",
    "bonus_weapon",
    "bonus_weapon_attack",
    "bonus_weapon_damage",
    "defensive_rules",
    "rarity",
    "resource_template_bonuses",
    "spell_support",
    "armor",
    "armor_category",
    "damage",
    "damage_type",
    "dmg1",
    "is_magic_item",
    "magic",
    "properties",
    "requires_attunement",
    "type",
    "versatile_damage",
    "weapon",
    "weapon_category",
    "weapon_wield_modes",
]);
const STANDARD_DND_CLASS_HIT_DICE = {
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
function asRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value)
        ? value
        : {};
}
function asArray(value) {
    return Array.isArray(value) ? value : [];
}
function asString(value) {
    return typeof value === "string" ? value.trim() : "";
}
function parseJsonRecord(rawValue) {
    try {
        return asRecord(JSON.parse(String(rawValue || "{}")) ?? {});
    }
    catch {
        return {};
    }
}
function normalizeSystemKey(value) {
    return asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function asInt(value, fallback = 0) {
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
function hasSubmittedValue(value) {
    return value !== null && value !== undefined && String(value).trim() !== "";
}
function parseOptionalWholeNumber(value, fieldLabel) {
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
function parseRequiredWholeNumber(value, fieldLabel) {
    const parsed = parseOptionalWholeNumber(value, fieldLabel);
    if (parsed === null) {
        throw new Error(`${fieldLabel} is required.`);
    }
    return parsed;
}
function nonNegativeInt(value, fallback = 0) {
    return Math.max(0, asInt(value, fallback));
}
function clampInt(value, fallback = 0, maximum) {
    const normalized = nonNegativeInt(value, fallback);
    return maximum === undefined ? normalized : Math.min(normalized, Math.max(0, maximum));
}
function utcIsoTimestamp() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}
function openDatabase(config) {
    if (!config.dbPath || !existsSync(config.dbPath)) {
        return null;
    }
    return new Database(config.dbPath);
}
function emptyItemCatalog() {
    return {
        byEntryKey: new Map(),
        byPageRef: new Map(),
        bySlug: new Map(),
        byTitle: new Map(),
    };
}
function normalizeCatalogLookup(value) {
    return asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function addItemCatalogEntry(catalog, entry) {
    if (entry.entryKey && !catalog.byEntryKey.has(entry.entryKey)) {
        catalog.byEntryKey.set(entry.entryKey, entry);
    }
    if (entry.pageRef && !catalog.byPageRef.has(entry.pageRef)) {
        catalog.byPageRef.set(entry.pageRef, entry);
    }
    if (entry.slug && !catalog.bySlug.has(entry.slug)) {
        catalog.bySlug.set(entry.slug, entry);
    }
    const normalizedTitle = normalizeCatalogLookup(entry.title);
    if (normalizedTitle && !catalog.byTitle.has(normalizedTitle)) {
        catalog.byTitle.set(normalizedTitle, entry);
    }
}
function hasCatalogSupportValue(value) {
    if (value === null || value === undefined || value === "") {
        return false;
    }
    if (Array.isArray(value) && value.length === 0) {
        return false;
    }
    if (typeof value === "object" && value !== null && !Array.isArray(value) && Object.keys(value).length === 0) {
        return false;
    }
    return true;
}
function titleCaseEquipmentName(value) {
    return asString(value)
        .toLowerCase()
        .replace(/\b[a-z]/g, (match) => match.toUpperCase());
}
function buildCampaignItemPageSupportMetadata(title, bodyMarkdown, metadataJson) {
    const metadata = {};
    const lines = String(bodyMarkdown || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
    const classificationLine = lines.find((line) => line.startsWith("*") && line.endsWith("*"))?.replace(/^\*+|\*+$/g, "").trim()
        || lines[0]
        || "";
    if (classificationLine) {
        const rarityMatch = classificationLine.match(/\b(very rare|legendary|artifact|uncommon|common|rare)\b/i);
        if (rarityMatch?.[1]) {
            metadata.rarity = rarityMatch[1].toLowerCase();
        }
        if (classificationLine.toLowerCase().includes("requires attunement")) {
            metadata.attunement = classificationLine;
        }
        const weaponMatch = classificationLine.match(/\bweapon(?:\s*\(([^)]+)\)|\s*,\s*([^,]+))/i);
        const rawBaseItem = asString(weaponMatch?.[1] || weaponMatch?.[2]);
        if (rawBaseItem) {
            metadata.base_item = titleCaseEquipmentName(rawBaseItem);
        }
    }
    const bodyText = lines.join(" ");
    if (!metadata.attunement && bodyText.toLowerCase().includes("requires attunement")) {
        metadata.attunement = "requires attunement";
    }
    if (!metadata.base_item) {
        for (const pattern of [
            /\bcan be wielded as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])/i,
            /\bcan be used as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])/i,
            /\bfunctions as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])/i,
        ]) {
            const match = bodyText.match(pattern);
            if (match?.[1]) {
                metadata.base_item = titleCaseEquipmentName(match[1]);
                break;
            }
        }
    }
    const sharedBonusMatch = bodyText.match(/\+(\d+)\s+bonus to attack (?:and|rolls and) damage rolls/i);
    if (sharedBonusMatch?.[1]) {
        metadata.bonus_weapon = asInt(sharedBonusMatch[1], 0);
    }
    else {
        const attackBonusMatch = bodyText.match(/\+(\d+)\s+bonus to attack rolls/i);
        if (attackBonusMatch?.[1]) {
            metadata.bonus_weapon_attack = asInt(attackBonusMatch[1], 0);
        }
        const damageBonusMatch = bodyText.match(/\+(\d+)\s+bonus to damage rolls/i);
        if (damageBonusMatch?.[1]) {
            metadata.bonus_weapon_damage = asInt(damageBonusMatch[1], 0);
        }
    }
    for (const [key, value] of Object.entries(parseJsonRecord(metadataJson))) {
        if (CAMPAIGN_ITEM_PAGE_SUPPORT_METADATA_KEYS.has(key) && hasCatalogSupportValue(value)) {
            metadata[key] = value;
        }
    }
    if (!Object.keys(metadata).some((key) => hasCatalogSupportValue(metadata[key]))) {
        return {};
    }
    metadata.title = asString(title);
    return metadata;
}
function loadItemCatalog(database, campaignSlug) {
    const catalog = emptyItemCatalog();
    if (!tableExists(database, "systems_entries")) {
        return catalog;
    }
    try {
        const rows = database
            .prepare(`
          SELECT
            systems_entries.entry_key,
            systems_entries.source_id,
            systems_entries.slug,
            systems_entries.title,
            systems_entries.metadata_json
          FROM systems_entries
          LEFT JOIN systems_sources
            ON systems_sources.library_slug = systems_entries.library_slug
           AND systems_sources.source_id = systems_entries.source_id
          LEFT JOIN campaign_enabled_sources
            ON campaign_enabled_sources.campaign_slug = ?
           AND campaign_enabled_sources.library_slug = systems_entries.library_slug
           AND campaign_enabled_sources.source_id = systems_entries.source_id
          LEFT JOIN campaign_entry_overrides
            ON campaign_entry_overrides.campaign_slug = ?
           AND campaign_entry_overrides.library_slug = systems_entries.library_slug
           AND campaign_entry_overrides.entry_key = systems_entries.entry_key
          WHERE systems_entries.entry_type = 'item'
            AND (systems_sources.status IS NULL OR systems_sources.status = 'active')
            AND COALESCE(campaign_enabled_sources.is_enabled, 1) != 0
            AND COALESCE(campaign_entry_overrides.is_enabled_override, 1) != 0
          ORDER BY systems_entries.title ASC, systems_entries.id ASC
        `)
            .all(campaignSlug, campaignSlug);
        for (const row of rows) {
            addItemCatalogEntry(catalog, {
                entryKey: asString(row.entry_key),
                pageRef: "",
                sourceId: asString(row.source_id),
                slug: asString(row.slug),
                title: asString(row.title),
                metadata: parseJsonRecord(row.metadata_json),
            });
        }
    }
    catch {
        return emptyItemCatalog();
    }
    if (tableExists(database, "campaign_pages")) {
        try {
            const pageRows = database
                .prepare(`
            SELECT page_ref, route_slug, title, body_markdown, metadata_json
            FROM campaign_pages
            WHERE campaign_slug = ?
              AND section = ?
              AND published != 0
            ORDER BY display_order ASC, title ASC, page_ref ASC
          `)
                .all(campaignSlug, CAMPAIGN_ITEMS_SECTION);
            for (const row of pageRows) {
                const metadata = buildCampaignItemPageSupportMetadata(row.title, row.body_markdown, row.metadata_json);
                if (Object.keys(metadata).length === 0) {
                    continue;
                }
                addItemCatalogEntry(catalog, {
                    entryKey: "",
                    pageRef: asString(row.page_ref),
                    sourceId: "campaign-page",
                    slug: asString(row.route_slug || row.page_ref),
                    title: asString(row.title),
                    metadata,
                });
            }
        }
        catch {
            return catalog;
        }
    }
    return catalog;
}
function tableExists(database, tableName) {
    const row = database
        .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?")
        .get(tableName);
    return Boolean(row?.name);
}
function parseStateJson(rawJson) {
    try {
        return asRecord(JSON.parse(rawJson));
    }
    catch {
        return {};
    }
}
function readCharacterState(database, campaignSlug, characterSlug) {
    const row = database
        .prepare(`
        SELECT revision, state_json, updated_at, updated_by_user_id
        FROM character_state
        WHERE campaign_slug = ?
          AND character_slug = ?
      `)
        .get(campaignSlug, characterSlug);
    if (!row) {
        return null;
    }
    return {
        revision: Number(row.revision) || 0,
        state: parseStateJson(row.state_json),
        updated_at: row.updated_at ?? null,
        updated_by_user_id: row.updated_by_user_id ?? null,
    };
}
export function readCharacterStateSnapshot(config, campaignSlug, characterSlug, definition) {
    if (existsSync(config.dbPath)) {
        const database = new Database(config.dbPath, { fileMustExist: true, readonly: true });
        try {
            if (tableExists(database, "character_state")) {
                const existingState = readCharacterState(database, campaignSlug, characterSlug);
                if (existingState) {
                    return existingState;
                }
            }
        }
        finally {
            database.close();
        }
    }
    return {
        revision: 1,
        state: buildInitialState(definition),
        updated_at: null,
        updated_by_user_id: null,
    };
}
function characterIdentity(definition) {
    const campaignSlug = asString(definition.campaign_slug);
    const characterSlug = asString(definition.character_slug);
    return campaignSlug && characterSlug ? { campaignSlug, characterSlug } : null;
}
function definitionXianxia(definition) {
    return asRecord(definition.xianxia);
}
function definitionStats(definition) {
    return asRecord(definition.stats);
}
function definitionDurability(definition) {
    const xianxia = definitionXianxia(definition);
    return asRecord(xianxia.durability);
}
function definitionYinYang(definition) {
    return asRecord(definitionXianxia(definition).yin_yang);
}
function definitionEnergies(definition) {
    return asRecord(definitionXianxia(definition).energies);
}
function definitionEnergyMaxima(definition) {
    return asRecord(definitionXianxia(definition).energy_maxima);
}
function xianxiaHpMax(definition) {
    const xianxia = definitionXianxia(definition);
    return nonNegativeInt(definitionDurability(definition).hp_max ?? xianxia.hp_max ?? definitionStats(definition).max_hp, 10);
}
function xianxiaStanceMax(definition) {
    const xianxia = definitionXianxia(definition);
    return nonNegativeInt(definitionDurability(definition).stance_max ?? xianxia.stance_max, 10);
}
function xianxiaEnergyMax(definition, energyKey) {
    const energy = asRecord(definitionEnergies(definition)[energyKey]);
    return nonNegativeInt(energy.max ?? definitionEnergyMaxima(definition)[energyKey], 0);
}
function xianxiaYinMax(definition) {
    return nonNegativeInt(definitionYinYang(definition).yin_max ?? definitionXianxia(definition).yin_max, 1);
}
function xianxiaYangMax(definition) {
    return nonNegativeInt(definitionYinYang(definition).yang_max ?? definitionXianxia(definition).yang_max, 1);
}
function xianxiaDaoMax(definition) {
    return nonNegativeInt(asRecord(definitionXianxia(definition).dao).max ?? definitionXianxia(definition).dao_max, 3);
}
function normalizeDndCurrencyFromEquipment(definition) {
    const currency = { cp: 0, sp: 0, ep: 0, gp: 0, pp: 0, other: [] };
    for (const item of asArray(definition.equipment_catalog)) {
        const itemCurrency = asRecord(asRecord(item).currency);
        for (const denomination of DND_CURRENCY_KEYS) {
            currency[denomination] = asInt(currency[denomination], 0) + asInt(itemCurrency[denomination], 0);
        }
    }
    return currency;
}
function normalizeWeaponWieldModeValue(value) {
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
function normalizeEquipmentToken(value) {
    return asString(value)
        .toLowerCase()
        .replace(/[_-]+/g, " ")
        .replace(/[^a-z0-9 ]+/g, "")
        .replace(/\s+/g, " ")
        .trim();
}
function titleLookupCandidates(value) {
    const cleaned = asString(value);
    if (!cleaned) {
        return [];
    }
    const values = [cleaned];
    const baseItemName = splitMagicItemName(cleaned);
    if (baseItemName && baseItemName !== cleaned) {
        values.push(baseItemName);
    }
    if (cleaned.includes(",")) {
        values.push(cleaned.split(",").reverse().map((part) => part.trim()).join(" "));
    }
    values.push(cleaned.replace(/'/g, ""));
    values.push(cleaned.replace(/-/g, " "));
    const seen = new Set();
    const candidates = [];
    for (const value of values) {
        const normalized = normalizeCatalogLookup(value);
        if (normalized && !seen.has(normalized)) {
            seen.add(normalized);
            candidates.push(normalized);
        }
    }
    return candidates;
}
function splitMagicItemName(value) {
    const cleaned = asString(value);
    const prefixMatch = cleaned.match(/^\+(\d+)\s+(.+)$/);
    if (prefixMatch) {
        return asString(prefixMatch[2]);
    }
    const suffixMatch = cleaned.match(/^(.+?),\s*\+(\d+)$/);
    if (suffixMatch) {
        return asString(suffixMatch[1]);
    }
    return cleaned;
}
function equipmentTokens(values) {
    const tokens = new Set();
    for (const value of values) {
        const normalized = normalizeEquipmentToken(value);
        if (normalized) {
            tokens.add(normalized);
        }
    }
    return tokens;
}
function itemStringFields(item) {
    return equipmentTokens([
        item.item_type,
        item.type,
        item.category,
        item.equipment_category,
        item.weapon_category,
        item.armor_category,
        ...asArray(item.tags),
        ...asArray(item.properties),
        ...asArray(item.weapon_properties),
    ]);
}
function extractPageRefSlug(value) {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        const payload = value;
        return asString(payload.page_ref || payload.slug);
    }
    return asString(value);
}
function resolveCatalogEntry(item, catalog) {
    const pageRef = extractPageRefSlug(item.page_ref);
    if (pageRef && catalog.byPageRef.has(pageRef)) {
        return catalog.byPageRef.get(pageRef);
    }
    const systemsRef = asRecord(item.systems_ref);
    const entryKey = asString(systemsRef.entry_key);
    if (entryKey && catalog.byEntryKey.has(entryKey)) {
        return catalog.byEntryKey.get(entryKey);
    }
    const slug = asString(systemsRef.slug);
    if (slug && catalog.bySlug.has(slug)) {
        return catalog.bySlug.get(slug);
    }
    for (const candidate of [systemsRef.title, item.name]) {
        for (const lookup of titleLookupCandidates(candidate)) {
            const entry = catalog.byTitle.get(lookup);
            if (entry) {
                return entry;
            }
        }
    }
    return undefined;
}
function itemSupportMetadata(item, catalog) {
    const entry = resolveCatalogEntry(item, catalog);
    const metadata = { ...(entry?.metadata || {}) };
    for (const key of [
        "armor",
        "armor_category",
        "attunement",
        "base_item",
        "bonus_ac",
        "damage",
        "damage_type",
        "dmg1",
        "is_magic_item",
        "magic",
        "properties",
        "rarity",
        "requires_attunement",
        "type",
        "versatile_damage",
        "weapon",
        "weapon_category",
        "weapon_wield_modes",
    ]) {
        if (Object.hasOwn(item, key)) {
            metadata[key] = item[key];
        }
    }
    if (entry && !metadata.title) {
        metadata.title = entry.title;
    }
    if (entry?.pageRef && !metadata.page_ref) {
        metadata.page_ref = entry.pageRef;
    }
    return metadata;
}
function equipmentSupportItem(inventoryItem, definitionItem) {
    const supportItem = { ...inventoryItem, ...(definitionItem || {}) };
    if (!asString(supportItem.name)) {
        supportItem.name = asString(inventoryItem.name);
    }
    return supportItem;
}
function supportFields(item, metadata) {
    return equipmentTokens([
        ...Array.from(itemStringFields(item)),
        metadata.base_item,
        metadata.type,
        metadata.weapon_category,
        metadata.armor_category,
        ...asArray(metadata.properties),
        ...asArray(asRecord(metadata.weapon).properties),
        ...asArray(asRecord(metadata.armor).properties),
    ]);
}
function isAmmunitionItem(fields, normalizedName) {
    return (fields.has("ammunition") ||
        fields.has("ammo") ||
        /\b(ammunition|bolt|bolts|arrow|arrows|bullet|bullets)\b/.test(normalizedName));
}
function isWeaponItem(item, metadata, fields, normalizedName) {
    if (isAmmunitionItem(fields, normalizedName)) {
        return false;
    }
    const weapon = asRecord(metadata.weapon);
    const typeCode = asString(metadata.type || weapon.type).toUpperCase();
    if (item.is_weapon === true ||
        Object.keys(weapon).length > 0 ||
        typeCode === "M" ||
        typeCode === "R" ||
        Boolean(asString(metadata.damage || metadata.dmg1 || weapon.damage || weapon.dmg1)) ||
        fields.has("weapon") ||
        fields.has("melee weapon") ||
        fields.has("ranged weapon") ||
        fields.has("simple weapon") ||
        fields.has("martial weapon")) {
        return true;
    }
    return /\b(crossbow|bow|sword|dagger|staff|quarterstaff|mace|axe|hammer|spear|javelin|club|rapier|scimitar|whip)\b/.test(normalizedName);
}
function isArmorItem(item, metadata, fields, normalizedName) {
    const armor = asRecord(metadata.armor);
    const typeCode = asString(metadata.type || armor.type).toUpperCase();
    if (item.is_armor === true ||
        item.is_shield === true ||
        Object.keys(armor).length > 0 ||
        Boolean(asString(metadata.ac || metadata.base_ac || armor.ac || armor.base_ac)) ||
        ["LA", "MA", "HA", "S", "SHIELD"].includes(typeCode) ||
        fields.has("armor") ||
        fields.has("armour") ||
        fields.has("shield") ||
        fields.has("medium armor") ||
        fields.has("heavy armor") ||
        fields.has("light armor")) {
        return true;
    }
    return /\b(armor|armour|mail|plate|shield)\b/.test(normalizedName);
}
function requiresAttunement(item, metadata, fields) {
    const value = metadata.attunement ?? item.attunement;
    if (item.requires_attunement === true || metadata.requires_attunement === true) {
        return true;
    }
    const attunement = normalizeEquipmentToken(value);
    if (!attunement || ["false", "none", "no", "not required"].includes(attunement)) {
        return false;
    }
    return attunement.includes("requires attunement") || fields.has("requires attunement");
}
function isMagicItem(item, metadata, fields) {
    const rarity = normalizeEquipmentToken(metadata.rarity ?? item.rarity);
    return (item.is_magic_item === true ||
        metadata.is_magic_item === true ||
        item.magic === true ||
        metadata.magic === true ||
        fields.has("magic") ||
        fields.has("magic item") ||
        requiresAttunement(item, metadata, fields) ||
        Boolean(rarity && !["false", "none", "no", "not required", "unknown", "mundane", "common mundane"].includes(rarity)));
}
function weaponWieldModesForItem(item, metadata, fields, normalizedName) {
    const weapon = asRecord(metadata.weapon);
    const explicitModes = asArray(item.weapon_wield_modes || metadata.weapon_wield_modes)
        .map((mode) => normalizeWeaponWieldModeValue(mode))
        .filter((mode) => mode);
    if (explicitModes.length > 0) {
        return Array.from(new Set(explicitModes));
    }
    const typeCode = asString(metadata.type || weapon.type).toUpperCase();
    const versatileDamage = asString(metadata.versatile_damage || weapon.versatile_damage);
    if (fields.has("two handed") || fields.has("2h") || normalizedName.includes("longbow") || normalizedName.includes("shortbow")) {
        return ["two-handed"];
    }
    if (normalizedName.includes("crossbow") && !normalizedName.includes("hand crossbow")) {
        return ["two-handed"];
    }
    const modes = ["main-hand"];
    if (typeCode === "M" || fields.has("melee weapon") || fields.has("light") || /\b(sword|dagger|staff|quarterstaff|mace|axe|hammer|spear|club|rapier|scimitar|whip)\b/.test(normalizedName)) {
        modes.push("off-hand");
    }
    if (fields.has("versatile") ||
        Boolean(versatileDamage) ||
        /\b(quarterstaff|staff|spear|longsword|battleaxe|warhammer|trident)\b/.test(normalizedName)) {
        modes.push("two-handed");
    }
    return Array.from(new Set(modes));
}
function describeEquipmentStateSupport(item, catalog) {
    if (item.is_currency_only === true) {
        return {
            supportsEquippedState: false,
            supportsAttunement: false,
            supportsWeaponWieldMode: false,
            weaponWieldModes: [],
            isArmor: false,
            isMagicItem: false,
        };
    }
    const metadata = itemSupportMetadata(item, catalog);
    const fields = supportFields(item, metadata);
    const normalizedName = normalizeEquipmentToken(metadata.base_item || metadata.title || item.name);
    const isWeapon = isWeaponItem(item, metadata, fields, normalizedName);
    const isArmor = isArmorItem(item, metadata, fields, normalizedName);
    const magicItem = isMagicItem(item, metadata, fields);
    const supportsEquippedState = item.supports_equipped_state === true || isWeapon || isArmor || magicItem;
    const weaponWieldModes = isWeapon ? weaponWieldModesForItem(item, metadata, fields, normalizedName) : [];
    const supportsAttunement = supportsEquippedState && requiresAttunement(item, metadata, fields);
    return {
        supportsEquippedState,
        supportsAttunement,
        supportsWeaponWieldMode: weaponWieldModes.length > 0,
        weaponWieldModes,
        isArmor,
        isMagicItem: magicItem,
    };
}
function buildDefinitionItemLookup(definition) {
    const lookup = new Map();
    for (const rawItem of asArray(definition.equipment_catalog)) {
        const item = asRecord(rawItem);
        const itemId = asString(item.id);
        if (itemId) {
            lookup.set(itemId, item);
        }
    }
    return lookup;
}
function slugifyValue(value) {
    return asString(value)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}
function normalizeActiveInfusions(value) {
    const normalized = [];
    const seen = new Set();
    for (const rawEntry of asArray(value)) {
        const entry = asRecord(rawEntry);
        const name = asString(entry.name);
        const infusionKey = asString(entry.infusion_key || entry.key) || slugifyValue(name);
        if (!infusionKey || seen.has(infusionKey)) {
            continue;
        }
        seen.add(infusionKey);
        const payload = {
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
function itemHasActiveInfusion(item, infusionKey) {
    return normalizeActiveInfusions(item.active_infusions).some((entry) => asString(entry.infusion_key) === infusionKey);
}
function capacityForLevel(level, table) {
    for (const [minimumLevel, capacity] of table) {
        if (level >= minimumLevel) {
            return capacity;
        }
    }
    return 0;
}
function artificerLevelFromDefinition(definition) {
    const profile = asRecord(definition.profile);
    let total = 0;
    for (const rawClass of asArray(profile.classes)) {
        const classRow = asRecord(rawClass);
        const classRef = asRecord(classRow.class_ref || classRow.systems_ref);
        const className = normalizeCatalogLookup(classRow.class_name);
        const refTitle = normalizeCatalogLookup(classRef.title);
        const refSlug = normalizeCatalogLookup(classRef.slug);
        if (className !== "artificer" && refTitle !== "artificer" && !refSlug.includes("artificer")) {
            continue;
        }
        total += Math.max(asInt(classRow.level, 0), 0);
    }
    if (total > 0) {
        return total;
    }
    const classLevelText = asString(profile.class_level_text);
    const match = classLevelText.match(/\bArtificer\s+(\d+)\b/i);
    return match ? Math.max(asInt(match[1], 0), 0) : 0;
}
function artificerInfusionActiveCapacity(artificerLevel) {
    return capacityForLevel(artificerLevel, ARTIFICER_INFUSION_ACTIVE_CAPACITY_BY_LEVEL);
}
function artificerInfusionKey(value) {
    return slugifyValue(value);
}
function activeInfusionPayload(name, featureId) {
    const cleanName = asString(name);
    const infusionKey = artificerInfusionKey(cleanName);
    const payload = {
        infusion_key: infusionKey,
        name: cleanName,
    };
    const sourceFeatureId = asString(featureId);
    if (sourceFeatureId) {
        payload.source_feature_id = sourceFeatureId;
    }
    if (infusionKey === ENHANCED_DEFENSE_INFUSION_KEY) {
        payload.effect_key = "enhanced_defense";
    }
    return payload;
}
function knownInfusionNamesFromSummary(value) {
    const text = asString(value);
    if (!text) {
        return [];
    }
    const match = text.match(/known infusions at artificer level\s+\d+\s*:\s*(.+?)(?:\n\n|\r\n\r\n|$)/is);
    if (!match) {
        return [];
    }
    return match[1]
        .split(/\s+-\s+/)
        .map((part) => part.trim().replace(/[ .]+$/g, ""))
        .filter((part) => part.length > 0);
}
function baseInfusionName(value) {
    const cleanValue = asString(value);
    return normalizeCatalogLookup(cleanValue).startsWith("replicatemagicitem") ? "Replicate Magic Item" : cleanValue;
}
function knownArtificerInfusions(definition) {
    const features = asArray(definition.features).map((rawFeature) => asRecord(rawFeature));
    const parentIds = new Set();
    for (const feature of features) {
        const featureId = asString(feature.id);
        if (featureId && normalizeCatalogLookup(feature.name) === ARTIFICER_INFUSIONS_FEATURE_KEY) {
            parentIds.add(featureId);
        }
    }
    const known = [];
    const seenKeys = new Set();
    const addKnown = (name, featureId = "") => {
        const cleanName = asString(name);
        const key = artificerInfusionKey(cleanName);
        if (!cleanName || !key || seenKeys.has(key)) {
            return;
        }
        seenKeys.add(key);
        known.push(activeInfusionPayload(cleanName, featureId));
    };
    for (const feature of features) {
        const featureName = asString(feature.name);
        const normalizedName = normalizeCatalogLookup(featureName);
        if (normalizedName === ARTIFICER_INFUSIONS_FEATURE_KEY) {
            for (const summaryName of knownInfusionNamesFromSummary(feature.description_markdown)) {
                addKnown(summaryName);
            }
            continue;
        }
        const parentId = asString(feature.native_edit_parent_feature_id || feature.parent_feature_id);
        const baseName = normalizeCatalogLookup(baseInfusionName(featureName));
        if (parentIds.has(parentId) || KNOWN_ARTIFICER_INFUSION_TITLES.has(baseName)) {
            addKnown(featureName, feature.id);
        }
    }
    return known;
}
function hasArtificerInfusionFeature(definition) {
    return asArray(definition.features).some((rawFeature) => normalizeCatalogLookup(asRecord(rawFeature).name) === ARTIFICER_INFUSIONS_FEATURE_KEY);
}
function enhancedDefenseArmorClassBonus(equipmentCatalog, catalog) {
    return equipmentCatalog.some((item) => {
        if (!itemHasActiveInfusion(item, ENHANCED_DEFENSE_INFUSION_KEY) || item.is_equipped !== true) {
            return false;
        }
        return describeEquipmentStateSupport(item, catalog).isArmor;
    })
        ? 1
        : 0;
}
function enhancedDefenseRule(item, catalog) {
    if (!itemHasActiveInfusion(item, ENHANCED_DEFENSE_INFUSION_KEY)) {
        return null;
    }
    if (!describeEquipmentStateSupport(item, catalog).isArmor) {
        return null;
    }
    const itemName = asString(item.name) || "Infused item";
    const isEquipped = item.is_equipped === true;
    return {
        id: `artificer-infusion:enhanced-defense:${slugifyValue(itemName)}`,
        title: "Enhanced Defense",
        active: isEquipped,
        condition: "Applies while the infused armor or shield is equipped.",
        inactive_reason: isEquipped ? "" : "Equip the infused armor or shield to apply this Armor Class bonus.",
        effects: [
            {
                kind: "armor_class",
                label: itemName,
                summary: `${itemName} grants a +1 bonus to Armor Class while infused by Enhanced Defense.`,
            },
        ],
    };
}
function applyEnhancedDefenseAutomation(definition, previousEquipmentCatalog, equipmentCatalog, catalog) {
    const stats = { ...asRecord(definition.stats) };
    const previousBonus = enhancedDefenseArmorClassBonus(previousEquipmentCatalog, catalog);
    const nextBonus = enhancedDefenseArmorClassBonus(equipmentCatalog, catalog);
    if (hasSubmittedValue(stats.armor_class) && previousBonus !== nextBonus) {
        stats.armor_class = asInt(stats.armor_class, 0) + (nextBonus - previousBonus);
    }
    const defensiveState = { ...asRecord(stats.defensive_state) };
    const rules = asArray(defensiveState.rules)
        .map((rawRule) => ({ ...asRecord(rawRule) }))
        .filter((rule) => {
        const id = asString(rule.id);
        const title = asString(rule.title);
        return title !== "Enhanced Defense" && !id.startsWith("artificer-infusion:enhanced-defense:");
    });
    for (const item of equipmentCatalog) {
        const rule = enhancedDefenseRule(item, catalog);
        if (rule) {
            rules.push(rule);
        }
    }
    stats.defensive_state = { ...defensiveState, rules };
    return {
        ...definition,
        stats,
        equipment_catalog: equipmentCatalog,
    };
}
function buildInventoryState(definition) {
    const inventory = [];
    for (const rawItem of asArray(definition.equipment_catalog)) {
        const item = asRecord(rawItem);
        if (item.is_currency_only === true) {
            continue;
        }
        const payload = {
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
function buildInventoryStateItemFromDefinition(item, existingItem = {}) {
    const payload = {
        ...existingItem,
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
    else {
        delete payload.weapon_wield_mode;
    }
    const activeInfusions = normalizeActiveInfusions(item.active_infusions);
    if (activeInfusions.length > 0) {
        payload.active_infusions = activeInfusions;
    }
    else {
        delete payload.active_infusions;
    }
    return payload;
}
function manualEquipmentDefinitionItems(definition) {
    return asArray(definition.equipment_catalog)
        .map((item) => asRecord(item))
        .filter((item) => asString(item.source_kind) === ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND);
}
function inventoryItemRef(item) {
    const payload = asRecord(item);
    return asString(payload.catalog_ref || payload.id);
}
function reconcileAdvancedEditorManualEquipmentState(state, definition, removedItemIds) {
    const manualItems = manualEquipmentDefinitionItems(definition);
    const manualById = new Map(manualItems
        .map((item) => [asString(item.id), item])
        .filter(([itemId]) => Boolean(itemId)));
    const removed = new Set(removedItemIds.map((itemId) => asString(itemId)).filter(Boolean));
    const nextInventory = [];
    const seenManualIds = new Set();
    for (const rawItem of asArray(state.inventory)) {
        const item = { ...asRecord(rawItem) };
        const itemRef = inventoryItemRef(item);
        if (removed.has(itemRef)) {
            continue;
        }
        const manualItem = manualById.get(itemRef);
        if (manualItem) {
            nextInventory.push(buildInventoryStateItemFromDefinition(manualItem, item));
            seenManualIds.add(itemRef);
            continue;
        }
        nextInventory.push(item);
    }
    for (const item of manualItems) {
        const itemId = asString(item.id);
        if (!itemId || seenManualIds.has(itemId)) {
            continue;
        }
        nextInventory.push(buildInventoryStateItemFromDefinition(item));
    }
    state.inventory = nextInventory;
    state.attunement = normalizeAttunementState(nextInventory);
}
function isAdvancedEditorCustomFeatureResource(resource) {
    const resourceId = asString(resource.id);
    return (asString(resource.category) === ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY ||
        resourceId.startsWith(`${ADVANCED_EDITOR_CUSTOM_FEATURE_RESOURCE_PREFIX}:`));
}
function reconcileAdvancedEditorCustomFeatureResourcesState(state, definition, removedResourceIds) {
    const removed = new Set(removedResourceIds.map((resourceId) => asString(resourceId)).filter(Boolean));
    const templateRows = buildResourceStates(definition)
        .map((resource) => asRecord(resource))
        .filter(isAdvancedEditorCustomFeatureResource);
    const templateIds = new Set(templateRows.map((resource) => asString(resource.id)).filter(Boolean));
    const existingById = new Map(asArray(state.resources)
        .map((resource) => asRecord(resource))
        .map((resource) => [asString(resource.id), resource])
        .filter(([resourceId]) => Boolean(resourceId)));
    const nextResources = [];
    for (const rawResource of asArray(state.resources)) {
        const resource = { ...asRecord(rawResource) };
        const resourceId = asString(resource.id);
        if (!resourceId || removed.has(resourceId) || templateIds.has(resourceId)) {
            continue;
        }
        if (isAdvancedEditorCustomFeatureResource(resource)) {
            continue;
        }
        nextResources.push(resource);
    }
    for (const template of templateRows) {
        const resourceId = asString(template.id);
        const existing = existingById.get(resourceId);
        if (!existing) {
            nextResources.push(template);
            continue;
        }
        const maxValue = template.max === null || template.max === undefined
            ? undefined
            : nonNegativeInt(template.max, 0);
        nextResources.push({
            ...template,
            current: clampInt(existing.current, nonNegativeInt(template.current, 0), maxValue),
        });
    }
    state.resources = nextResources;
}
function normalizeAttunementState(inventory) {
    const attunedItemRefs = [];
    const seenRefs = new Set();
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
function attunementLimit(value) {
    if (value === 0 || value === "0" || !hasSubmittedValue(value)) {
        return 3;
    }
    return asInt(value, 3);
}
function buildResourceStates(definition) {
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
function buildSpellSlotStates(definition) {
    const spellcasting = asRecord(definition.spellcasting);
    const lanes = asArray(spellcasting.slot_lanes);
    const slots = [];
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
            const stateSlot = { level, max: maxSlots, used: 0 };
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
function normalizeClassName(value) {
    return asString(value).toLowerCase().replace(/[^a-z]+/g, "");
}
function extractHitDieFaces(value) {
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
function profileClassRows(definition) {
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
function hitDieFacesForClassRow(classRow) {
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
function buildHitDiceState(definition) {
    const maxByFaces = new Map();
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
function existingHitDiceCurrentByFaces(rawState) {
    const currentByFaces = new Map();
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
function normalizeHitDiceState(definition, rawState) {
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
function normalizeHitDiceStatePayload(definition, state) {
    const payload = copyState(state);
    const normalized = normalizeHitDiceState(definition, payload.hit_dice);
    if (asArray(normalized.pools).length > 0) {
        payload.hit_dice = normalized;
    }
    else {
        delete payload.hit_dice;
    }
    return payload;
}
function hitDiceLongRestRegainAmount(definition) {
    const totalLevel = asArray(buildHitDiceState(definition).pools)
        .map(asRecord)
        .reduce((total, pool) => total + nonNegativeInt(pool.max, 0), 0);
    return totalLevel > 0 ? Math.max(1, Math.floor(totalLevel / 2)) : 0;
}
function applyLongRestHitDiceRecovery(definition, state) {
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
function hitDiceSummaryFromState(definition, state) {
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
function hitDiceRestChanges(definition, beforeState, afterState) {
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
function normalizeHitDiceCurrentPayload(payload) {
    const rawValue = payload.hit_dice_current ?? payload.hit_dice;
    if (rawValue === null || rawValue === undefined || rawValue === "") {
        return null;
    }
    if (typeof rawValue !== "object" || Array.isArray(rawValue)) {
        throw new Error("Hit Dice must be submitted as an object keyed by die size.");
    }
    const valuesByFaces = new Map();
    for (const [rawFaces, current] of Object.entries(rawValue)) {
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
function applyHitDiceCurrentValues(definition, state, valuesByFaces) {
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
function normalizeNotes(value) {
    const notes = asRecord(value);
    return {
        player_notes_markdown: asString(notes.player_notes_markdown),
        physical_description_markdown: asString(notes.physical_description_markdown),
        background_markdown: asString(notes.background_markdown),
        session_notes: asArray(notes.session_notes),
    };
}
function normalizeActiveStateRecord(value) {
    if (typeof value === "string") {
        const name = asString(value);
        return name ? { name } : {};
    }
    const record = asRecord(value);
    const name = asString(record.name || record.label);
    return name ? { ...record, name } : {};
}
function normalizeXianxiaCurrency(value) {
    const currency = asRecord(value);
    const normalized = {};
    for (const key of XIANXIA_CURRENCY_KEYS) {
        normalized[key] = nonNegativeInt(currency[key], 0);
    }
    return normalized;
}
function normalizeXianxiaInventory(rawXianxiaInventory, sharedInventory) {
    if (Array.isArray(rawXianxiaInventory)) {
        return rawXianxiaInventory;
    }
    const rawInventoryRecord = asRecord(rawXianxiaInventory);
    if (Array.isArray(rawInventoryRecord.quantities)) {
        return rawInventoryRecord.quantities;
    }
    return asArray(sharedInventory);
}
function normalizeXianxiaStateFromShared(definition, state) {
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
    const energies = {};
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
            current_stance: clampInt(rawXianxiaVitals.current_stance ?? rawXianxiaVitals.stance_current ?? rawXianxia.stance_current, xianxiaStanceMax(definition), xianxiaStanceMax(definition)),
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
function buildXianxiaInitialState(definition) {
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
function buildDndInitialState(definition) {
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
function buildInitialState(definition) {
    return normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE
        ? buildXianxiaInitialState(definition)
        : buildDndInitialState(definition);
}
function copyState(state) {
    return JSON.parse(JSON.stringify(state));
}
function applyVitalsUpdate(state, payload) {
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
    }
    else {
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
function applyXianxiaVitalsUpdate(state, payload) {
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
    ]) {
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
function normalizeSubmittedXianxiaActiveStateValue(value) {
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
function applyXianxiaActiveStateUpdate(state, payload) {
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
function firstPayloadValue(payload, ...keys) {
    for (const key of keys) {
        if (Object.hasOwn(payload, key)) {
            return payload[key];
        }
    }
    return undefined;
}
function cleanCollapsedText(value) {
    return String(value || "")
        .split(/\s+/)
        .filter(Boolean)
        .join(" ")
        .trim();
}
function parseOptionalNonNegativeWholeNumber(value, fieldLabel) {
    const parsed = parseOptionalWholeNumber(value, fieldLabel);
    if (parsed === null) {
        return null;
    }
    if (parsed < 0) {
        throw new Error(`${fieldLabel} must be 0 or greater.`);
    }
    return parsed;
}
function parseRequiredNonNegativeWholeNumber(value, fieldLabel) {
    const parsed = parseOptionalNonNegativeWholeNumber(value, fieldLabel);
    if (parsed === null) {
        throw new Error(`${fieldLabel} is required.`);
    }
    return parsed;
}
function copyRecordList(value) {
    return asArray(value)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0)
        .map((record) => ({ ...record }));
}
function daoImmolatingPreparedReference(preparedRecords, preparedRecordIndex) {
    if (preparedRecordIndex === null) {
        return null;
    }
    if (preparedRecordIndex < 0 || preparedRecordIndex >= preparedRecords.length) {
        return null;
    }
    const preparedRecord = preparedRecords[preparedRecordIndex] ?? {};
    const preparedName = cleanCollapsedText(preparedRecord.name || preparedRecord.title || preparedRecord.label || preparedRecord.technique_name);
    const preparedNotes = cleanCollapsedText(preparedRecord.notes ||
        preparedRecord.prepared_notes ||
        preparedRecord.preparation_notes ||
        preparedRecord.description ||
        preparedRecord.description_markdown ||
        preparedRecord.text);
    const reference = { prepared_record_index: preparedRecordIndex };
    if (preparedName) {
        reference.prepared_record_name = preparedName;
    }
    if (preparedNotes) {
        reference.prepared_record_notes = preparedNotes;
    }
    return reference;
}
function approvalStatusKey(value) {
    const normalized = cleanCollapsedText(value).toLowerCase().replace(/[- ]+/g, "_");
    return normalized === "denied" ? "rejected" : normalized;
}
function truthyRecordValue(value) {
    if (typeof value === "boolean") {
        return value;
    }
    const normalized = String(value || "").trim().toLowerCase();
    return ["1", "true", "yes", "on"].includes(normalized);
}
function daoImmolatingUseRecordIsUsed(record) {
    for (const key of ["used", "one_use_used", "use_recorded", "spent"]) {
        if (truthyRecordValue(record[key])) {
            return true;
        }
    }
    const status = cleanCollapsedText(record.one_use_status || record.use_status).toLowerCase().replace(/[- ]+/g, "_");
    return ["used", "spent", "recorded", "expended"].includes(status);
}
function requestXianxiaDaoImmolatingUseDefinition(definition, payload) {
    const preparedRecordIndex = parseOptionalNonNegativeWholeNumber(firstPayloadValue(payload, "prepared_record_index", "dao_immolating_prepared_index"), "Prepared Dao Immolating Technique note");
    const cleanNotes = cleanCollapsedText(firstPayloadValue(payload, "notes", "dao_immolating_request_notes"));
    const nextDefinition = copyState(definition);
    const xianxia = { ...definitionXianxia(nextDefinition) };
    const daoImmolating = { ...asRecord(xianxia.dao_immolating_techniques) };
    const preparedRecords = copyRecordList(daoImmolating.prepared);
    const preparedReference = daoImmolatingPreparedReference(preparedRecords, preparedRecordIndex);
    if (preparedRecordIndex !== null && preparedReference === null) {
        throw new Error("Choose an existing prepared Dao Immolating Technique note.");
    }
    let cleanName = cleanCollapsedText(firstPayloadValue(payload, "request_name", "dao_immolating_request_name"));
    if (!cleanName && preparedReference) {
        cleanName = cleanCollapsedText(preparedReference.prepared_record_name);
    }
    if (!cleanName) {
        throw new Error("Enter a Dao Immolating Technique request name.");
    }
    const requestRecord = {
        name: cleanName,
        request_type: "dao_immolating_use",
        request_source: preparedReference ? "prepared_record" : "ad_hoc",
        approval_required: true,
        approval_status: "pending",
    };
    if (cleanNotes) {
        requestRecord.notes = cleanNotes;
    }
    if (preparedReference) {
        Object.assign(requestRecord, preparedReference);
    }
    daoImmolating.prepared = preparedRecords;
    daoImmolating.use_history = [...copyRecordList(daoImmolating.use_history), requestRecord];
    xianxia.dao_immolating_techniques = daoImmolating;
    nextDefinition.xianxia = xianxia;
    return nextDefinition;
}
function recordXianxiaDaoImmolatingUseDefinition(definition, payload) {
    const useRecordIndex = parseRequiredNonNegativeWholeNumber(firstPayloadValue(payload, "use_record_index", "dao_immolating_use_index"), "Dao Immolating Technique use");
    const cleanNotes = cleanCollapsedText(firstPayloadValue(payload, "notes", "dao_immolating_use_notes"));
    const nextDefinition = copyState(definition);
    const xianxia = { ...definitionXianxia(nextDefinition) };
    const daoImmolating = { ...asRecord(xianxia.dao_immolating_techniques) };
    const useHistory = copyRecordList(daoImmolating.use_history);
    if (useRecordIndex < 0 || useRecordIndex >= useHistory.length) {
        throw new Error("Choose a recorded Dao Immolating Technique use.");
    }
    const targetRecord = { ...(useHistory[useRecordIndex] ?? {}) };
    const requestName = cleanCollapsedText(targetRecord.name || targetRecord.title || "Dao Immolating Technique");
    if (approvalStatusKey(targetRecord.approval_status || targetRecord.status) !== "approved") {
        throw new Error("Only an approved Dao Immolating Technique use can spend Insight.");
    }
    if (daoImmolatingUseRecordIsUsed(targetRecord)) {
        throw new Error(`${requestName} has already been recorded as used.`);
    }
    const insight = asRecord(xianxia.insight);
    const available = nonNegativeInt(insight.available, 0);
    const spent = nonNegativeInt(insight.spent, 0);
    if (available < XIANXIA_DAO_IMMOLATING_INSIGHT_COST) {
        throw new Error(`Dao Immolating Technique use needs ${XIANXIA_DAO_IMMOLATING_INSIGHT_COST} Insight; only ${available} available.`);
    }
    targetRecord.insight_cost = XIANXIA_DAO_IMMOLATING_INSIGHT_COST;
    targetRecord.insight_spent = XIANXIA_DAO_IMMOLATING_INSIGHT_COST;
    targetRecord.one_use = true;
    targetRecord.used = true;
    targetRecord.one_use_status = "used";
    if (cleanNotes) {
        targetRecord.use_notes = cleanNotes;
    }
    useHistory[useRecordIndex] = targetRecord;
    xianxia.insight = {
        available: available - XIANXIA_DAO_IMMOLATING_INSIGHT_COST,
        spent: spent + XIANXIA_DAO_IMMOLATING_INSIGHT_COST,
    };
    xianxia.dao_immolating_techniques = {
        prepared: copyRecordList(daoImmolating.prepared),
        use_history: useHistory,
    };
    const history = copyRecordList(xianxia.advancement_history);
    const event = {
        action: "dao_immolating_technique_used",
        amount: XIANXIA_DAO_IMMOLATING_INSIGHT_COST,
        target: requestName,
        use_history_index: useRecordIndex,
        insight_cost: XIANXIA_DAO_IMMOLATING_INSIGHT_COST,
        one_use: true,
        one_use_status: "used",
    };
    if (cleanNotes) {
        event.notes = cleanNotes;
    }
    history.push(event);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return nextDefinition;
}
function findStateItemById(items, targetId, itemType) {
    const match = asArray(items).map(asRecord).find((item) => asString(item.id) === targetId);
    if (!match) {
        throw new Error(`Unknown ${itemType}: ${targetId}`);
    }
    return match;
}
function applyResourceUpdate(state, resourceId, payload) {
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
function normalizeSpellSlotLaneId(value) {
    return String(value || "").trim();
}
function applySpellSlotsUpdate(state, level, payload) {
    const slots = asArray(state.spell_slots);
    const cleanLaneId = normalizeSpellSlotLaneId(payload.slot_lane_id);
    let slot = slots.map(asRecord).find((item) => asInt(item.level, 0) === level &&
        normalizeSpellSlotLaneId(item.slot_lane_id) === cleanLaneId);
    if (!slot && cleanLaneId) {
        slot = slots.map(asRecord).find((item) => asInt(item.level, 0) === level && !normalizeSpellSlotLaneId(item.slot_lane_id));
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
function syncTopLevelXianxiaInventory(state, quantities) {
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
function normalizeXianxiaInventoryItemType(value) {
    const normalized = asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
    if (normalized === "weapon" || normalized === "weapons") {
        return "Weapon";
    }
    if (normalized === "armor" || normalized === "armors" || normalized === "armour" || normalized === "armours") {
        return "Armor";
    }
    if (normalized === "artifact" || normalized === "artifacts" || normalized === "relic" || normalized === "relics") {
        return "Artifact";
    }
    if (normalized === "consumable" || normalized === "consumables") {
        return "Consumable";
    }
    if (normalized === "misc" || normalized === "miscellaneous" || normalized === "tool" || normalized === "tools") {
        return "Miscellaneous";
    }
    return "Miscellaneous";
}
function normalizeXianxiaInventoryItemNature(value) {
    const normalized = asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
    if (normalized === "relic" || normalized === "relics") {
        return "Relic";
    }
    return "Mundane";
}
function normalizeStateBoolean(value) {
    if (typeof value === "boolean") {
        return value;
    }
    if (typeof value === "number") {
        return value !== 0;
    }
    const normalized = asString(value).toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
        return true;
    }
    if (["", "0", "false", "no", "off"].includes(normalized)) {
        return false;
    }
    return Boolean(value);
}
function normalizeSubmittedXianxiaInventoryTags(value) {
    if (Array.isArray(value)) {
        return value.map((item) => asString(item)).filter(Boolean);
    }
    const tag = asString(value);
    return tag ? [tag] : [];
}
function normalizeSubmittedXianxiaInventorySystemsRef(value) {
    const slug = asString(value);
    if (slug) {
        return { slug };
    }
    const record = asRecord(value);
    return Object.keys(record).length > 0 ? record : undefined;
}
function normalizeSubmittedXianxiaInventoryRows(value) {
    const rawRows = typeof value === "object" && value !== null && !Array.isArray(value)
        ? Object.entries(value)
            .filter(([key]) => key.trim() !== "")
            .map(([key, quantity]) => ({ id: key, quantity }))
        : typeof value === "string"
            ? [{ name: value, quantity: 1 }]
            : asArray(value);
    const rows = [];
    for (const rawRow of rawRows) {
        const row = typeof rawRow === "object" && rawRow !== null && !Array.isArray(rawRow)
            ? asRecord(rawRow)
            : { name: rawRow, quantity: 1 };
        const id = asString(row.id);
        const catalogRef = asString(row.catalog_ref);
        const name = asString(row.name || row.label);
        if (!id && !catalogRef && !name) {
            continue;
        }
        const itemType = normalizeXianxiaInventoryItemType(row.item_type);
        const itemNature = normalizeXianxiaInventoryItemNature(row.item_nature);
        const hasExplicitEquippable = Object.hasOwn(row, "equippable");
        const equippable = hasExplicitEquippable ? normalizeStateBoolean(row.equippable) : itemType === "Weapon" || itemType === "Armor";
        const normalized = {
            ...row,
            quantity: asInt(Object.hasOwn(row, "quantity") ? row.quantity : row.default_quantity, 0),
            item_type: itemType,
            item_nature: itemNature,
            equippable,
            is_equipped: normalizeStateBoolean(row.is_equipped) && equippable,
        };
        const tags = normalizeSubmittedXianxiaInventoryTags(row.tags);
        if (tags.length > 0) {
            normalized.tags = tags;
        }
        const systemsRef = normalizeSubmittedXianxiaInventorySystemsRef(row.systems_ref);
        if (systemsRef) {
            normalized.systems_ref = systemsRef;
        }
        if (id) {
            normalized.id = id;
        }
        if (catalogRef) {
            normalized.catalog_ref = catalogRef;
        }
        if (name) {
            normalized.name = name;
        }
        rows.push(normalized);
    }
    return rows;
}
function normalizeXianxiaInventoryStatePayload(state) {
    const xianxia = { ...asRecord(state.xianxia) };
    const rawInventory = xianxia.inventory;
    const inventory = asRecord(rawInventory);
    const rawQuantities = Array.isArray(rawInventory)
        ? rawInventory
        : Object.hasOwn(inventory, "quantities")
            ? inventory.quantities
            : inventory.items;
    const quantities = normalizeSubmittedXianxiaInventoryRows(rawQuantities ?? []);
    syncTopLevelXianxiaInventory(state, quantities);
}
function xianxiaInventoryRows(state) {
    const xianxiaInventory = asRecord(asRecord(state.xianxia).inventory);
    const rows = Array.isArray(xianxiaInventory.quantities)
        ? asArray(xianxiaInventory.quantities)
        : asArray(state.inventory);
    return rows.map((row) => ({ ...asRecord(row), quantity: asInt(asRecord(row).quantity, 0) }));
}
function submittedXianxiaInventoryText(value) {
    if (value === null || value === undefined) {
        return "";
    }
    return String(value).trim();
}
function shouldIncludeXianxiaInventoryPayloadValue(value) {
    return value !== null && value !== undefined && value !== "";
}
function submittedXianxiaInventoryItemPayload(payload) {
    const itemPayload = asRecord(payload.item);
    const source = typeof payload.item === "object" && payload.item !== null && !Array.isArray(payload.item)
        ? itemPayload
        : payload;
    const submitted = {};
    const setTextField = (field, value) => {
        const text = submittedXianxiaInventoryText(value);
        if (text) {
            submitted[field] = text;
        }
    };
    setTextField("id", source.id ?? source.item_id);
    setTextField("name", source.name);
    if (Object.hasOwn(source, "quantity")) {
        const quantity = parseOptionalWholeNumber(source.quantity, "Quantity");
        if (quantity !== null) {
            submitted.quantity = quantity;
        }
    }
    else {
        submitted.quantity = 1;
    }
    setTextField("item_nature", source.item_nature);
    setTextField("item_type", source.item_type);
    setTextField("notes", source.notes);
    setTextField("catalog_ref", source.catalog_ref);
    if (Object.hasOwn(source, "tags") && shouldIncludeXianxiaInventoryPayloadValue(source.tags)) {
        submitted.tags = source.tags;
    }
    if (Object.hasOwn(source, "systems_ref") && shouldIncludeXianxiaInventoryPayloadValue(source.systems_ref)) {
        submitted.systems_ref = source.systems_ref;
    }
    if (Object.hasOwn(source, "equippable") && shouldIncludeXianxiaInventoryPayloadValue(source.equippable)) {
        submitted.equippable = source.equippable;
    }
    if (Object.hasOwn(source, "is_equipped") && shouldIncludeXianxiaInventoryPayloadValue(source.is_equipped)) {
        submitted.is_equipped = source.is_equipped;
    }
    return submitted;
}
function existingXianxiaInventoryIds(rows) {
    return new Set(rows.map((row) => asString(row.id)).filter(Boolean));
}
function deriveXianxiaInventoryId(row, existingIds) {
    const itemType = asString(row.item_type);
    const name = asString(row.name || row.label);
    const catalogRef = asString(row.catalog_ref);
    const base = slugifyValue(name ? `${itemType} ${name}` : itemType) || slugifyValue(catalogRef) || "item";
    let candidate = base;
    let suffix = 2;
    while (existingIds.has(candidate)) {
        candidate = `${base}-${suffix}`;
        suffix += 1;
    }
    return candidate;
}
function applyXianxiaInventoryAddStateUpdate(state, payload) {
    normalizeXianxiaInventoryStatePayload(state);
    const itemPayload = submittedXianxiaInventoryItemPayload(payload);
    if (!Object.hasOwn(itemPayload, "name") && !Object.hasOwn(itemPayload, "catalog_ref")) {
        throw new Error("Inventory item requires a name.");
    }
    if (!Object.hasOwn(itemPayload, "quantity")) {
        itemPayload.quantity = 1;
    }
    const quantities = xianxiaInventoryRows(state);
    const existingIds = existingXianxiaInventoryIds(quantities);
    const explicitId = asString(itemPayload.id);
    if (explicitId) {
        if (existingIds.has(explicitId)) {
            throw new Error(`Duplicate inventory item id: ${explicitId}`);
        }
    }
    else {
        itemPayload.id = deriveXianxiaInventoryId(itemPayload, existingIds);
    }
    const submittedEquipped = Object.hasOwn(itemPayload, "is_equipped") && normalizeStateBoolean(itemPayload.is_equipped);
    const normalized = normalizeSubmittedXianxiaInventoryRows([itemPayload])[0];
    if (!normalized) {
        throw new Error("Inventory item requires a name.");
    }
    if (submittedEquipped && !Boolean(normalized.equippable)) {
        throw new Error("Cannot equip non-equippable item.");
    }
    quantities.push(normalized);
    syncTopLevelXianxiaInventory(state, normalizeSubmittedXianxiaInventoryRows(quantities));
}
function applyXianxiaInventoryRemoveStateUpdate(state, itemId) {
    normalizeXianxiaInventoryStatePayload(state);
    const quantities = xianxiaInventoryRows(state);
    const nextQuantities = quantities.filter((row) => asString(row.id) !== itemId);
    if (nextQuantities.length === quantities.length) {
        throw new Error(`Unknown Xianxia inventory item: ${itemId}`);
    }
    syncTopLevelXianxiaInventory(state, normalizeSubmittedXianxiaInventoryRows(nextQuantities));
}
function mergeXianxiaInventoryRow(existing, update) {
    const merged = { ...existing };
    const explicitEquippable = Object.hasOwn(update, "equippable");
    const itemType = asString(update.item_type);
    if (itemType) {
        merged.item_type = itemType;
    }
    if (Object.hasOwn(update, "item_nature")) {
        merged.item_nature = asString(update.item_nature);
    }
    if (Object.hasOwn(update, "name")) {
        merged.name = asString(update.name);
    }
    if (Object.hasOwn(update, "quantity")) {
        merged.quantity = asInt(update.quantity, 0);
    }
    if (Object.hasOwn(update, "notes")) {
        merged.notes = asString(update.notes);
    }
    if (Object.hasOwn(update, "tags")) {
        merged.tags = normalizeSubmittedXianxiaInventoryTags(update.tags);
    }
    if (Object.hasOwn(update, "catalog_ref")) {
        merged.catalog_ref = asString(update.catalog_ref);
    }
    if (Object.hasOwn(update, "equippable")) {
        merged.equippable = normalizeStateBoolean(update.equippable);
    }
    if (Object.hasOwn(update, "is_equipped")) {
        merged.is_equipped = normalizeStateBoolean(update.is_equipped);
    }
    if (Object.hasOwn(update, "systems_ref")) {
        const systemsRef = normalizeSubmittedXianxiaInventorySystemsRef(update.systems_ref);
        if (systemsRef) {
            merged.systems_ref = systemsRef;
        }
        else {
            delete merged.systems_ref;
        }
    }
    if (!explicitEquippable) {
        delete merged.equippable;
    }
    const normalized = normalizeSubmittedXianxiaInventoryRows([{ ...merged, id: asString(existing.id) }])[0] ?? {};
    if (!Boolean(normalized.equippable)) {
        normalized.is_equipped = false;
    }
    return normalized;
}
function applyXianxiaInventoryItemStateUpdate(state, itemId, payload) {
    normalizeXianxiaInventoryStatePayload(state);
    const quantities = xianxiaInventoryRows(state);
    const itemIndex = quantities.findIndex((row) => asString(row.id) === itemId);
    if (itemIndex < 0) {
        throw new Error(`Unknown Xianxia inventory item: ${itemId}`);
    }
    const itemPayload = submittedXianxiaInventoryItemPayload(payload);
    const merged = mergeXianxiaInventoryRow(quantities[itemIndex] ?? {}, itemPayload);
    merged.id = itemId;
    quantities[itemIndex] = merged;
    syncTopLevelXianxiaInventory(state, normalizeSubmittedXianxiaInventoryRows(quantities));
}
function applyInventoryQuantityUpdate(state, itemId, payload, isXianxia) {
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
function applyXianxiaInventoryEquippedStateUpdate(state, itemId, payload) {
    normalizeXianxiaInventoryStatePayload(state);
    const quantities = xianxiaInventoryRows(state);
    const item = quantities.find((row) => asString(row.id) === itemId);
    if (!item) {
        throw new Error(`Unknown Xianxia inventory item: ${itemId}`);
    }
    const isEquipped = Boolean(payload.is_equipped);
    if (isEquipped && !Boolean(item.equippable)) {
        throw new Error("Cannot equip a non-equippable item.");
    }
    item.is_equipped = isEquipped;
    syncTopLevelXianxiaInventory(state, quantities);
}
function applyCurrencyUpdate(state, payload, isXianxia) {
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
function normalizeSubmittedPlayerNotesMarkdown(value) {
    return value ? String(value) : "";
}
function applyPlayerNotesUpdate(state, payload) {
    const notes = { ...asRecord(state.notes) };
    notes.player_notes_markdown = normalizeSubmittedPlayerNotesMarkdown(payload.player_notes_markdown);
    state.notes = notes;
}
function normalizeSubmittedPersonalMarkdown(value) {
    return value ? String(value) : "";
}
function applyPersonalDetailsUpdate(state, payload) {
    const notes = { ...asRecord(state.notes) };
    notes.physical_description_markdown = normalizeSubmittedPersonalMarkdown(payload.physical_description_markdown);
    notes.background_markdown = normalizeSubmittedPersonalMarkdown(payload.background_markdown);
    state.notes = notes;
}
function requireSheetEditRecord(value, label) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error(`Sheet edit ${label} must be an object.`);
    }
    return value;
}
function requireSheetEditRows(value, label, rowLabel) {
    if (!Array.isArray(value)) {
        throw new Error(`Sheet edit ${label} must be a list.`);
    }
    return value.map((row) => {
        if (typeof row !== "object" || row === null || Array.isArray(row)) {
            throw new Error(`Each sheet edit ${rowLabel} row must be an object.`);
        }
        return row;
    });
}
function validateNoSheetEditRestAction(payload) {
    for (const key of ["rest", "rest_type", "rest_action", "short_rest", "long_rest", "hit_dice", "hit_dice_current"]) {
        if (Object.hasOwn(payload, key)) {
            throw new Error("Sheet edit batches do not apply rest actions.");
        }
    }
}
function applySheetEditBatch(state, definition, payload) {
    validateNoSheetEditRestAction(payload);
    const nextState = copyState(state);
    const isXianxia = normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE;
    let appliedChanges = false;
    if (payload.vitals !== null && payload.vitals !== undefined) {
        const vitals = requireSheetEditRecord(payload.vitals, "vitals");
        if (Object.hasOwn(vitals, "hp_delta") || Object.hasOwn(vitals, "temp_hp_delta") || Object.hasOwn(vitals, "clear_temp_hp")) {
            throw new Error("Sheet edit vitals must use absolute current values, not delta actions.");
        }
        if (Object.hasOwn(vitals, "current_hp") || Object.hasOwn(vitals, "temp_hp")) {
            applyVitalsUpdate(nextState, {
                current_hp: vitals.current_hp,
                temp_hp: vitals.temp_hp,
            });
            appliedChanges = true;
        }
    }
    if (payload.resources !== null && payload.resources !== undefined) {
        const rows = requireSheetEditRows(payload.resources, "resources", "resource");
        for (const entry of rows) {
            const resourceId = asString(entry.id);
            if (!resourceId) {
                throw new Error("Each sheet edit resource row needs an id.");
            }
            if (Object.hasOwn(entry, "delta")) {
                throw new Error("Sheet edit resources must use absolute current values, not delta actions.");
            }
            if (!Object.hasOwn(entry, "current")) {
                throw new Error(`Sheet edit resource '${resourceId}' is missing a current value.`);
            }
            applyResourceUpdate(nextState, resourceId, { current: entry.current });
            appliedChanges = true;
        }
    }
    if (payload.spell_slots !== null && payload.spell_slots !== undefined) {
        const rows = requireSheetEditRows(payload.spell_slots, "spell slots", "spell slot");
        for (const entry of rows) {
            if (Object.hasOwn(entry, "delta_used")) {
                throw new Error("Sheet edit spell slots must use absolute used values, not delta actions.");
            }
            if (!Object.hasOwn(entry, "level")) {
                throw new Error("Each sheet edit spell slot row needs a level.");
            }
            if (!Object.hasOwn(entry, "used")) {
                throw new Error("Each sheet edit spell slot row needs a used value.");
            }
            const level = parseRequiredWholeNumber(entry.level, "Spell slot level");
            applySpellSlotsUpdate(nextState, level, { slot_lane_id: entry.slot_lane_id, used: entry.used });
            appliedChanges = true;
        }
    }
    if (payload.inventory !== null && payload.inventory !== undefined) {
        const rows = requireSheetEditRows(payload.inventory, "inventory", "inventory");
        for (const entry of rows) {
            const itemId = asString(entry.id);
            if (!itemId) {
                throw new Error("Each sheet edit inventory row needs an id.");
            }
            if (Object.hasOwn(entry, "delta")) {
                throw new Error("Sheet edit inventory must use absolute quantities, not delta actions.");
            }
            if (!Object.hasOwn(entry, "quantity")) {
                throw new Error(`Sheet edit inventory row '${itemId}' is missing a quantity.`);
            }
            applyInventoryQuantityUpdate(nextState, itemId, { quantity: entry.quantity }, isXianxia);
            appliedChanges = true;
        }
    }
    if (payload.currency !== null && payload.currency !== undefined) {
        const currency = requireSheetEditRecord(payload.currency, "currency");
        if (Object.hasOwn(currency, "delta")) {
            throw new Error("Sheet edit currency must use absolute coin values, not delta actions.");
        }
        const hasXianxiaCurrency = XIANXIA_CURRENCY_KEYS.some((key) => Object.hasOwn(currency, key));
        const hasDndCurrency = DND_CURRENCY_KEYS.some((key) => Object.hasOwn(currency, key));
        if (isXianxia && hasXianxiaCurrency) {
            applyCurrencyUpdate(nextState, currency, true);
            appliedChanges = true;
        }
        else if (hasDndCurrency) {
            applyCurrencyUpdate(nextState, currency, false);
            appliedChanges = true;
        }
    }
    if (payload.notes !== null && payload.notes !== undefined) {
        const notes = requireSheetEditRecord(payload.notes, "notes");
        if (Object.hasOwn(notes, "player_notes_markdown")) {
            applyPlayerNotesUpdate(nextState, { player_notes_markdown: notes.player_notes_markdown });
            appliedChanges = true;
        }
    }
    if (payload.personal !== null && payload.personal !== undefined) {
        const personal = requireSheetEditRecord(payload.personal, "personal details");
        const notes = { ...asRecord(nextState.notes) };
        const hasPhysical = Object.hasOwn(personal, "physical_description_markdown");
        const hasBackground = Object.hasOwn(personal, "background_markdown");
        if (hasPhysical || hasBackground) {
            if (hasPhysical) {
                notes.physical_description_markdown = normalizeSubmittedPersonalMarkdown(personal.physical_description_markdown);
            }
            if (hasBackground) {
                notes.background_markdown = normalizeSubmittedPersonalMarkdown(personal.background_markdown);
            }
            nextState.notes = notes;
            appliedChanges = true;
        }
    }
    return { state: nextState, appliedChanges };
}
function normalizeFeatureStateKey(value) {
    const normalized = String(value ?? "").split(/\s+/).join(" ").trim().replace(/[- ]+/g, "_").toLowerCase();
    if (normalized === "arcane_armor" || normalized === "arcanearmor") {
        return "arcane_armor";
    }
    throw new Error("Choose a supported feature state to update.");
}
function definitionHasFeature(definition, featureName) {
    const target = featureName.split(/\s+/).join(" ").trim().toLowerCase();
    return asArray(definition.features).some((rawFeature) => {
        const feature = asRecord(rawFeature);
        return String(feature.name ?? "").split(/\s+/).join(" ").trim().toLowerCase() === target;
    });
}
function applyFeatureStateUpdate(state, definition, featureKey, payload) {
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
function applyEquipmentStateUpdate(state, definition, catalog, itemId, payload) {
    const normalizedItemId = asString(itemId);
    if (!normalizedItemId) {
        throw new Error("Choose a valid equipment entry to update.");
    }
    const definitionItemsByRef = buildDefinitionItemLookup(definition);
    const inventory = asArray(state.inventory).map((rawItem) => ({ ...asRecord(rawItem) }));
    const targetInventoryIndex = inventory.findIndex((item) => inventoryItemRef(item) === normalizedItemId);
    if (targetInventoryIndex < 0) {
        throw new Error("Choose a valid equipment entry to update.");
    }
    const targetInventory = inventory[targetInventoryIndex];
    const targetDefinitionItem = definitionItemsByRef.get(normalizedItemId);
    const targetSupport = describeEquipmentStateSupport(equipmentSupportItem(targetInventory, targetDefinitionItem), catalog);
    if (!targetSupport.supportsEquippedState) {
        throw new Error("That inventory row stays on Inventory because it does not support equipment state.");
    }
    let weaponWieldMode = "";
    let isEquipped;
    if (targetSupport.supportsWeaponWieldMode) {
        weaponWieldMode = normalizeWeaponWieldModeValue(payload.weapon_wield_mode);
        if (weaponWieldMode && !targetSupport.weaponWieldModes.includes(weaponWieldMode)) {
            throw new Error("Choose a valid wielding mode for that weapon.");
        }
        if (!weaponWieldMode && Boolean(payload.is_equipped) && targetSupport.weaponWieldModes.length > 0) {
            weaponWieldMode = targetSupport.weaponWieldModes[0] || "";
        }
        isEquipped = Boolean(weaponWieldMode);
    }
    else {
        isEquipped = Boolean(payload.is_equipped);
    }
    const requestedAttunement = Boolean(payload.is_attuned);
    if (requestedAttunement && !targetSupport.supportsAttunement) {
        throw new Error("Only items whose durable metadata explicitly requires attunement can be attuned.");
    }
    const isAttuned = requestedAttunement && targetSupport.supportsAttunement;
    const attunementPayload = asRecord(state.attunement);
    const maxAttunedItems = attunementLimit(attunementPayload.max_attuned_items);
    const currentlyAttunedRefs = new Set();
    for (const item of inventory) {
        const itemRef = inventoryItemRef(item);
        if (!itemRef || itemRef === normalizedItemId || item.is_attuned !== true) {
            continue;
        }
        const support = describeEquipmentStateSupport(equipmentSupportItem(item, definitionItemsByRef.get(itemRef)), catalog);
        if (support.supportsAttunement) {
            currentlyAttunedRefs.add(itemRef);
        }
    }
    const nextAttunedCount = currentlyAttunedRefs.size + (isAttuned ? 1 : 0);
    if (maxAttunedItems >= 0 && nextAttunedCount > maxAttunedItems) {
        throw new Error(`This character already has ${maxAttunedItems} attuned item${maxAttunedItems === 1 ? "" : "s"}. Clear one first.`);
    }
    const applyStateFields = (item) => {
        const updatedItem = { ...item, is_equipped: isEquipped, is_attuned: isAttuned };
        if (targetSupport.supportsWeaponWieldMode && weaponWieldMode) {
            updatedItem.weapon_wield_mode = weaponWieldMode;
        }
        else {
            delete updatedItem.weapon_wield_mode;
        }
        return updatedItem;
    };
    inventory[targetInventoryIndex] = applyStateFields(targetInventory);
    let foundDefinitionItem = false;
    const previousEquipmentCatalog = asArray(definition.equipment_catalog).map((rawItem) => ({ ...asRecord(rawItem) }));
    const equipmentCatalog = previousEquipmentCatalog.map((rawItem) => {
        const item = { ...rawItem };
        if (asString(item.id) !== normalizedItemId) {
            return item;
        }
        foundDefinitionItem = true;
        return applyStateFields(item);
    });
    if (!foundDefinitionItem) {
        throw new Error("Choose a valid equipment entry to update.");
    }
    const nextAttunedRefs = [];
    const seenAttunedRefs = new Set();
    for (const item of inventory) {
        const itemRef = inventoryItemRef(item);
        if (!itemRef || item.is_attuned !== true || seenAttunedRefs.has(itemRef)) {
            continue;
        }
        const support = describeEquipmentStateSupport(equipmentSupportItem(item, definitionItemsByRef.get(itemRef)), catalog);
        if (!support.supportsAttunement) {
            continue;
        }
        seenAttunedRefs.add(itemRef);
        nextAttunedRefs.push(itemRef);
    }
    return {
        state: {
            ...state,
            inventory,
            attunement: {
                max_attuned_items: maxAttunedItems,
                attuned_item_refs: nextAttunedRefs,
            },
        },
        definition: applyEnhancedDefenseAutomation(definition, previousEquipmentCatalog, equipmentCatalog, catalog),
    };
}
function applyArtificerInfusionsUpdate(state, definition, catalog, payload) {
    if (normalizeSystemKey(definition.system) !== "dnd5e") {
        throw new Error("Artificer infusions are only available for Artificer sheets with Infuse Item.");
    }
    const artificerLevel = artificerLevelFromDefinition(definition);
    const activeCapacity = artificerInfusionActiveCapacity(artificerLevel);
    const knownInfusions = knownArtificerInfusions(definition);
    const knownByKey = new Map();
    for (const knownInfusion of knownInfusions) {
        const infusionKey = asString(knownInfusion.infusion_key);
        if (infusionKey) {
            knownByKey.set(infusionKey, knownInfusion);
        }
    }
    if (!activeCapacity && !hasArtificerInfusionFeature(definition)) {
        throw new Error("Artificer infusions are only available for Artificer sheets with Infuse Item.");
    }
    if (knownByKey.size <= 0) {
        throw new Error("This Artificer sheet does not have modeled known infusions yet.");
    }
    const definitionItemsByRef = buildDefinitionItemLookup(definition);
    const inventory = asArray(state.inventory).map((rawItem) => ({ ...asRecord(rawItem) }));
    const inventoryByRef = new Map();
    for (const item of inventory) {
        const itemRef = inventoryItemRef(item);
        if (itemRef) {
            inventoryByRef.set(itemRef, item);
        }
    }
    const nextActiveRows = [];
    const seenInfusionKeys = new Set();
    const seenTargetRefs = new Set();
    for (const rawEntry of asArray(payload.active)) {
        const entry = asRecord(rawEntry);
        const infusionKey = asString(entry.infusion_key || entry.key);
        const targetItemRef = asString(entry.target_item_ref || entry.item_ref);
        if (!infusionKey || !targetItemRef) {
            continue;
        }
        const knownEntry = knownByKey.get(infusionKey);
        if (!knownEntry) {
            throw new Error("Choose a known Artificer infusion.");
        }
        if (seenInfusionKeys.has(infusionKey)) {
            throw new Error("Each known infusion can only be active once.");
        }
        if (seenTargetRefs.has(targetItemRef)) {
            throw new Error("Each item can only hold one active infusion.");
        }
        const inventoryItem = inventoryByRef.get(targetItemRef);
        const definitionItem = definitionItemsByRef.get(targetItemRef);
        if (!inventoryItem || !definitionItem) {
            throw new Error("Choose a valid inventory target for that infusion.");
        }
        const support = describeEquipmentStateSupport(equipmentSupportItem(inventoryItem, definitionItem), catalog);
        if (support.isMagicItem) {
            throw new Error("Artificer infusions can only target nonmagical items.");
        }
        if (infusionKey === ENHANCED_DEFENSE_INFUSION_KEY && !support.isArmor) {
            throw new Error("Enhanced Defense can only target nonmagical armor or a shield.");
        }
        seenInfusionKeys.add(infusionKey);
        seenTargetRefs.add(targetItemRef);
        nextActiveRows.push({
            infusionKey,
            targetItemRef,
            payload: activeInfusionPayload(knownEntry.name, knownEntry.source_feature_id),
        });
    }
    if (nextActiveRows.length > activeCapacity) {
        throw new Error(`This Artificer can keep ${activeCapacity} infusion${activeCapacity === 1 ? "" : "s"} active.`);
    }
    const activeByTarget = new Map();
    for (const row of nextActiveRows) {
        const rows = activeByTarget.get(row.targetItemRef) || [];
        rows.push({ ...row.payload });
        activeByTarget.set(row.targetItemRef, rows);
    }
    const nextInventory = inventory.map((item) => {
        const itemRef = inventoryItemRef(item);
        if (!itemRef || !definitionItemsByRef.has(itemRef)) {
            return item;
        }
        const activeInfusions = activeByTarget.get(itemRef) || [];
        const nextItem = { ...item };
        if (activeInfusions.length > 0) {
            nextItem.active_infusions = activeInfusions.map((entry) => ({ ...entry }));
        }
        else {
            delete nextItem.active_infusions;
        }
        return nextItem;
    });
    const previousEquipmentCatalog = asArray(definition.equipment_catalog).map((rawItem) => ({ ...asRecord(rawItem) }));
    const equipmentCatalog = previousEquipmentCatalog.map((rawItem) => {
        const item = { ...asRecord(rawItem) };
        const itemRef = asString(item.id);
        const activeInfusions = activeByTarget.get(itemRef) || [];
        if (activeInfusions.length > 0) {
            item.active_infusions = activeInfusions.map((entry) => ({ ...entry }));
        }
        else {
            delete item.active_infusions;
        }
        return item;
    });
    return {
        state: {
            ...state,
            inventory: nextInventory,
        },
        definition: applyEnhancedDefenseAutomation(definition, previousEquipmentCatalog, equipmentCatalog, catalog),
    };
}
function isXianxiaDefinition(definition) {
    return normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE;
}
function normalizeRestType(restType) {
    const rawRestType = String(restType ?? "");
    const normalized = rawRestType.trim().toLowerCase();
    if (normalized !== "short" && normalized !== "long") {
        throw new Error(`Unsupported rest type: ${rawRestType}`);
    }
    return normalized;
}
function restLabel(restType) {
    return restType === "short" ? "Short Rest" : "Long Rest";
}
function shouldResetResource(resource, restType) {
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
function resetResourceValue(resource) {
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
function resourceValueText(current, maxValue) {
    if (maxValue === null || maxValue === undefined) {
        return String(current);
    }
    return `${current} / ${asInt(maxValue, 0)}`;
}
function normalizeSpellSlotProgression(rawProgression) {
    return asArray(rawProgression)
        .map(asRecord)
        .map((slot) => ({
        level: asInt(slot.level, 0),
        max_slots: nonNegativeInt(slot.max_slots, 0),
    }))
        .filter((slot) => slot.level > 0);
}
function spellSlotLaneTitleMap(spellcasting) {
    const payload = asRecord(spellcasting);
    const rawLanes = asArray(payload.slot_lanes).map(asRecord).filter((lane) => Object.keys(lane).length > 0);
    if (rawLanes.length > 0) {
        const laneTitles = new Map();
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
function spellLevelLabel(level) {
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
function applyXianxiaOneDayRest(state, definition) {
    const xianxia = { ...asRecord(state.xianxia) };
    const vitals = { ...asRecord(xianxia.vitals) };
    const hpMax = xianxiaHpMax(definition);
    const stanceMax = xianxiaStanceMax(definition);
    vitals.current_hp = hpMax;
    vitals.current_stance = stanceMax;
    xianxia.vitals = vitals;
    const energies = {};
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
function appendPoolRecoveryChange(changes, label, current, maximum) {
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
function collectXianxiaOneDayRestChanges(state, definition) {
    const changes = [];
    const xianxia = asRecord(state.xianxia);
    const vitals = asRecord(xianxia.vitals);
    appendPoolRecoveryChange(changes, "HP", vitals.current_hp, xianxiaHpMax(definition));
    appendPoolRecoveryChange(changes, "Stance", vitals.current_stance, xianxiaStanceMax(definition));
    const energies = asRecord(xianxia.energies);
    for (const key of XIANXIA_ENERGY_KEYS) {
        const energy = asRecord(energies[key]);
        appendPoolRecoveryChange(changes, `${XIANXIA_ENERGY_LABELS[key]} Energy`, energy.current, xianxiaEnergyMax(definition, key));
    }
    const yinYang = asRecord(xianxia.yin_yang);
    appendPoolRecoveryChange(changes, "Yin", yinYang.yin_current, xianxiaYinMax(definition));
    appendPoolRecoveryChange(changes, "Yang", yinYang.yang_current, xianxiaYangMax(definition));
    return changes;
}
function modeledRestState(state, restType, definition) {
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
        }
        else {
            modeledState = applyLongRestHitDiceRecovery(definition, modeledState);
        }
    }
    else if (!isXianxiaDefinition(definition)) {
        modeledState = normalizeHitDiceStatePayload(definition, modeledState);
    }
    return modeledState;
}
function restAdjustmentsFromState(state, definition) {
    const vitals = asRecord(state.vitals);
    const adjustments = {
        current_hp: asInt(vitals.current_hp, 0),
    };
    const hitDice = hitDiceSummaryFromState(definition, state);
    if (asArray(hitDice.pools).length > 0) {
        adjustments.hit_dice = hitDice;
    }
    return adjustments;
}
function collectRestChanges(state, restType, definition) {
    const changes = [];
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
    }
    else {
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
function readCharacterStateForRest(config, campaignSlug, characterSlug, definition) {
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
    }
    finally {
        database.close();
    }
}
export function previewCharacterRest(config, campaignSlug, characterSlug, definition, restType) {
    let normalizedRest;
    try {
        normalizedRest = normalizeRestType(restType);
    }
    catch (error) {
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
export function canEditCharacterSessionState(config, campaignSlug, characterSlug, role, userId) {
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
            .prepare(`
          SELECT id
          FROM character_assignments
          WHERE user_id = ?
            AND campaign_slug = ?
            AND character_slug = ?
        `)
            .get(userId, campaignSlug, characterSlug);
        return Boolean(row?.id);
    }
    finally {
        database.close();
    }
}
export function updateCharacterSheetEdit(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
        validateNoSheetEditRestAction(payload);
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character sheet edit payload." };
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
            return { status: "state_conflict", message: CHARACTER_SHEET_EDIT_CONFLICT_MESSAGE };
        }
        let nextState;
        try {
            const batch = applySheetEditBatch(existingState.state, definition, payload);
            if (!batch.appliedChanges) {
                return { status: "validation_error", message: "No Character-page sheet edits were provided." };
            }
            nextState = batch.state;
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character sheet edit payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_SHEET_EDIT_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterAdvancedEditorReferenceState(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid advanced editor payload." };
    }
    const stateNoteValues = asRecord(payload.state_note_values);
    const manualEquipmentReconcile = asRecord(payload.manualEquipmentReconcile ?? payload.manual_equipment_reconcile);
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
        const notes = { ...asRecord(nextState.notes) };
        for (const [fieldName, value] of Object.entries(stateNoteValues)) {
            notes[fieldName] = value === null || value === undefined ? "" : String(value);
        }
        nextState.notes = notes;
        if (manualEquipmentReconcile.enabled === true) {
            reconcileAdvancedEditorManualEquipmentState(nextState, definition, asArray(manualEquipmentReconcile.removedItemIds).map((itemId) => asString(itemId)).filter(Boolean));
        }
        const customFeatureResourceReconcile = asRecord(manualEquipmentReconcile.customFeatureResourceReconcile
            ?? manualEquipmentReconcile.custom_feature_resource_reconcile);
        if (customFeatureResourceReconcile.enabled === true) {
            reconcileAdvancedEditorCustomFeatureResourcesState(nextState, definition, asArray(customFeatureResourceReconcile.removedResourceIds ?? customFeatureResourceReconcile.removed_resource_ids)
                .map((resourceId) => asString(resourceId))
                .filter(Boolean));
        }
        const vitals = { ...asRecord(nextState.vitals) };
        if (Object.hasOwn(vitals, "current_hp")) {
            vitals.current_hp = clampInt(vitals.current_hp, 0, nonNegativeInt(definitionStats(definition).max_hp, 0));
            nextState.vitals = vitals;
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterCultivationDefinitionState(config, campaignSlug, characterSlug, currentDefinition, nextDefinition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid cultivation payload." };
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
        existingState ??= { revision: 1, state: buildInitialState(currentDefinition) };
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        const nextState = normalizeSystemKey(nextDefinition.system) === XIANXIA_SYSTEM_CODE
            ? mergeXianxiaStateWithDefinition(nextDefinition, existingState.state)
            : copyState(existingState.state);
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionVitals(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    let hitDiceCurrentValues;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
        hitDiceCurrentValues = normalizeHitDiceCurrentPayload(payload);
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character vitals payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionResource(config, campaignSlug, characterSlug, definition, resourceId, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character resource payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionSpellSlots(config, campaignSlug, characterSlug, definition, levelValue, payload, updatedByUserId) {
    let expectedRevision;
    let level;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
        level = parseRequiredWholeNumber(levelValue, "Spell slot level");
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character spell slot payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionInventory(config, campaignSlug, characterSlug, definition, itemId, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character inventory payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaInventoryItem(config, campaignSlug, characterSlug, definition, itemId, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory item payload." };
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
                message: "Xianxia inventory operations require a Xianxia character.",
            };
        }
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        const nextState = copyState(existingState.state);
        try {
            applyXianxiaInventoryItemStateUpdate(nextState, itemId, payload);
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory item payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaInventoryRemove(config, campaignSlug, characterSlug, definition, itemId, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory remove payload." };
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
                message: "Xianxia inventory operations require a Xianxia character.",
            };
        }
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        const nextState = copyState(existingState.state);
        try {
            applyXianxiaInventoryRemoveStateUpdate(nextState, itemId);
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory remove payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaInventoryAdd(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory item payload." };
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
                message: "Xianxia inventory operations require a Xianxia character.",
            };
        }
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        const nextState = copyState(existingState.state);
        try {
            applyXianxiaInventoryAddStateUpdate(nextState, payload);
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory item payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaInventoryEquipped(config, campaignSlug, characterSlug, definition, itemId, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory equipment payload." };
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
                message: "Xianxia inventory operations require a Xianxia character.",
            };
        }
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        const nextState = copyState(existingState.state);
        try {
            applyXianxiaInventoryEquippedStateUpdate(nextState, itemId, payload);
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Xianxia inventory equipment payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaActiveState(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character active state payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaDaoImmolatingUseRequest(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Dao Immolating use request payload." };
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
        if (!isXianxiaDefinition(definition)) {
            return {
                status: "validation_error",
                message: "Dao Immolating use requests are only available for Xianxia character sheets.",
            };
        }
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        let nextDefinition;
        let nextState;
        try {
            nextDefinition = requestXianxiaDaoImmolatingUseDefinition(definition, payload);
            nextState = mergeXianxiaStateWithDefinition(nextDefinition, existingState.state);
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Dao Immolating use request payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionXianxiaDaoImmolatingUseRecord(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Dao Immolating use record payload." };
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
        if (!isXianxiaDefinition(definition)) {
            return {
                status: "validation_error",
                message: "Dao Immolating use records are only available for Xianxia character sheets.",
            };
        }
        if (existingState.revision !== expectedRevision) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        let nextDefinition;
        let nextState;
        try {
            nextDefinition = recordXianxiaDaoImmolatingUseDefinition(definition, payload);
            nextState = mergeXianxiaStateWithDefinition(nextDefinition, existingState.state);
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Dao Immolating use record payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionCurrency(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character currency payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionNotes(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionPersonal(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionFeatureState(config, campaignSlug, characterSlug, definition, featureKey, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character feature state payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function applyCharacterSessionRest(config, campaignSlug, characterSlug, definition, restType, payload, updatedByUserId) {
    let normalizedRest;
    let expectedRevision;
    let hitDiceCurrentValues;
    try {
        normalizedRest = normalizeRestType(restType);
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
        hitDiceCurrentValues = normalizeHitDiceCurrentPayload(payload);
    }
    catch (error) {
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
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character rest payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionEquipment(config, campaignSlug, characterSlug, definition, itemId, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character equipment payload." };
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
        let nextState;
        let nextDefinition;
        try {
            const result = applyEquipmentStateUpdate(copyState(existingState.state), definition, loadItemCatalog(database, campaignSlug), itemId, payload);
            nextState = result.state;
            nextDefinition = result.definition;
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character equipment payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
        }
        const updateResult = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (updateResult.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
    }
    finally {
        database.close();
    }
}
export function updateCharacterSessionArtificerInfusions(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Artificer infusion payload." };
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
        let nextState;
        let nextDefinition;
        try {
            const result = applyArtificerInfusionsUpdate(copyState(existingState.state), definition, loadItemCatalog(database, campaignSlug), payload);
            nextState = result.state;
            nextDefinition = result.definition;
        }
        catch (error) {
            return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid Artificer infusion payload." };
        }
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
        }
        const updateResult = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (updateResult.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now, definition: nextDefinition };
    }
    finally {
        database.close();
    }
}
function mergeXianxiaStateWithDefinition(definition, existingState) {
    const initialState = buildXianxiaInitialState(definition);
    const payload = { ...existingState };
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
export function updateCharacterPortraitRevision(config, campaignSlug, characterSlug, definition, payload, updatedByUserId) {
    let expectedRevision;
    try {
        expectedRevision = parseRequiredWholeNumber(payload.expected_revision, "Expected revision");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid character portrait payload." };
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
        const now = utcIsoTimestamp();
        if (stateRowMissing) {
            database
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(campaignSlug, characterSlug, expectedRevision + 1, JSON.stringify(nextState), now, updatedByUserId);
            return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
        }
        const result = database
            .prepare(`
          UPDATE character_state
          SET revision = revision + 1,
              state_json = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND revision = ?
        `)
            .run(JSON.stringify(nextState), now, updatedByUserId, campaignSlug, characterSlug, expectedRevision);
        if (result.changes <= 0) {
            return { status: "state_conflict", message: CHARACTER_STATE_CONFLICT_MESSAGE };
        }
        return { status: "ok", revision: expectedRevision + 1, state: nextState, updatedAt: now };
    }
    finally {
        database.close();
    }
}
export function persistCharacterStateForDefinition(config, definition, initialState) {
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
                .prepare(`
            INSERT INTO character_state (
              campaign_slug,
              character_slug,
              revision,
              state_json,
              updated_at,
              updated_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
          `)
                .run(identity.campaignSlug, identity.characterSlug, 1, JSON.stringify(initialState ?? buildInitialState(definition)), now, null);
            return { stateCreated: true };
        }
        if (normalizeSystemKey(definition.system) === XIANXIA_SYSTEM_CODE) {
            const mergedState = mergeXianxiaStateWithDefinition(definition, existingState.state);
            if (JSON.stringify(mergedState) !== JSON.stringify(existingState.state)) {
                database
                    .prepare(`
              UPDATE character_state
              SET revision = revision + 1,
                  state_json = ?,
                  updated_at = ?,
                  updated_by_user_id = ?
              WHERE campaign_slug = ?
                AND character_slug = ?
                AND revision = ?
            `)
                    .run(JSON.stringify(mergedState), now, null, identity.campaignSlug, identity.characterSlug, existingState.revision);
            }
        }
        return { stateCreated: false };
    }
    finally {
        database.close();
    }
}
export function deleteCharacterPersistence(config, campaignSlug, characterSlug) {
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
    }
    finally {
        database.close();
    }
}
