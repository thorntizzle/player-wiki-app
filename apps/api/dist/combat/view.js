import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import Database from "better-sqlite3";
import { persistCharacterStateForDefinition } from "../content/characterState.js";
import { listCampaignContentCharacters } from "../content/repository.js";
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
];
const COMBAT_SOURCE_LABELS = {
    character: "Character",
    manual_npc: "Manual NPC",
    dm_statblock: "DM Content",
    systems_monster: "Systems",
};
const STATBLOCK_DEX_MODIFIER_PATTERN = /\bDEX\s+\d+\s+\(([+-]\d+)\)/i;
const NPC_RESOURCE_TAG_PATTERN = /\{@[a-zA-Z0-9_-]+\s+([^}|]+)(?:\|[^}]*)?\}/g;
const NPC_RESOURCE_MARKDOWN_DECORATION_PATTERN = /[*_`#>\[\]]+/g;
const NPC_RESOURCE_DAILY_LIST_PATTERN = /(\d+)\s*\/\s*day(\s+each)?\s*:\s*([^.;\n]+)/gi;
const NPC_RESOURCE_NAMED_DAILY_PATTERN = /([A-Za-z][A-Za-z0-9 '\-,]{1,90}?)\s*\((\d+)\s*\/\s*day\)/gi;
const NPC_RESOURCE_EXPLICIT_COUNTER_PATTERN = /^\s*(?:[-*]\s*)?([A-Za-z][^:|/]{1,80}?)\s*[:|-]\s*(\d+)\s*\/\s*(\d+)\b/i;
const NPC_RESOURCE_AT_WILL_PATTERN = /\bat\s+will\s*:\s*([^.;\n]+)/gi;
const NPC_RESOURCE_RECHARGE_PATTERN = /\((recharge\s+\d+\s*[-+]\s*\d+)\)/gi;
class CombatMutationConflictError extends Error {
}
function resetCombatantTurnResources(database, campaignSlug, combatantId, actorUserId, now, missingMessage) {
    const combatantUpdate = database
        .prepare(`
        UPDATE campaign_combatants
        SET has_action = 1,
            has_bonus_action = 1,
            has_reaction = 1,
            movement_remaining = movement_total,
            revision = revision + 1,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ? AND id = ?
      `)
        .run(now, actorUserId, campaignSlug, combatantId);
    if (combatantUpdate.changes !== 1) {
        throw new CombatMutationConflictError(missingMessage);
    }
}
function normalizeSystemKey(value) {
    return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function asRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value)
        ? value
        : {};
}
function asString(value) {
    return typeof value === "string" ? value.trim() : "";
}
function payloadString(value) {
    if (value === null || value === undefined) {
        return "";
    }
    return String(value).trim();
}
function asNumber(value, fallback = 0) {
    if (typeof value === "number" && Number.isFinite(value)) {
        return Math.trunc(value);
    }
    if (typeof value === "string" && value.trim()) {
        const parsed = Number(value.trim());
        return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
    }
    return fallback;
}
function asBoolean(value) {
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
function utcIsoTimestamp() {
    return new Date().toISOString().replace("Z", "+00:00");
}
export function supportsCombatTracker(system) {
    return normalizeSystemKey(system) === "dnd5e";
}
function isNoSuchTableOrColumnError(error) {
    return (error instanceof Error &&
        (error.message.includes("no such table") || error.message.includes("no such column")));
}
function formatInitiativeBonus(value) {
    return value > 0 ? `+${value}` : String(value);
}
function normalizeNpcResourceText(value) {
    return String(value || "")
        .replace(/\r\n/g, "\n")
        .replace(/\u2013|\u2014/g, "-")
        .replace(NPC_RESOURCE_TAG_PATTERN, "$1")
        .replace(/\s+/g, " ")
        .trim();
}
function cleanNpcResourceLabel(value) {
    return normalizeNpcResourceText(value)
        .replace(NPC_RESOURCE_MARKDOWN_DECORATION_PATTERN, "")
        .replace(/^\s*[-:|.]+\s*/, "")
        .replace(/\s*[-:|.]+\s*$/, "")
        .trim();
}
function splitLimitedUseItems(value) {
    return normalizeNpcResourceText(value)
        .replace(/\band\b/gi, ",")
        .split(/[,;]/)
        .map((item) => cleanNpcResourceLabel(item))
        .filter(Boolean);
}
function npcResourceKey(label) {
    return label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "resource";
}
function appendNpcResourceCounter(counters, seenKeys, options) {
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
function appendNpcResourceNote(notes, seenNotes, options) {
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
function labelBeforeNpcResourceMatch(line, matchStart) {
    const prefix = line.slice(0, matchStart).trim();
    const parts = prefix.split(/[.;]/);
    return cleanNpcResourceLabel(parts[parts.length - 1] || "");
}
function titleCaseNpcResourceNote(value) {
    return cleanNpcResourceLabel(value.toLowerCase()).replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}
function buildNpcResourceSeedsFromMarkdown(markdownText, sourceLabel) {
    const counters = [];
    const notes = [];
    const seenCounterKeys = new Set();
    const seenNotes = new Set();
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
function collectStructuredNpcResourceText(value) {
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
        const lines = [];
        const name = normalizeNpcResourceText(payloadString(record.name));
        if (name) {
            lines.push(name);
        }
        if (Object.hasOwn(record, "entries")) {
            lines.push(...collectStructuredNpcResourceText(record.entries));
        }
        else if (Object.hasOwn(record, "entry")) {
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
function buildNpcResourceSeedsFromStructuredValue(value, sourceLabel) {
    return buildNpcResourceSeedsFromMarkdown(collectStructuredNpcResourceText(value).join("\n"), sourceLabel);
}
function extractStatblockDexterityModifier(markdownText, fallback) {
    const match = STATBLOCK_DEX_MODIFIER_PATTERN.exec(markdownText || "");
    if (!match) {
        return fallback;
    }
    const parsed = Number(match[1]);
    return Number.isSafeInteger(parsed) ? parsed : fallback;
}
function parseJsonObject(rawJson) {
    try {
        return asRecord(JSON.parse(rawJson || "{}"));
    }
    catch {
        return {};
    }
}
function parseJsonUnknown(rawJson) {
    try {
        return JSON.parse(rawJson || "{}");
    }
    catch {
        return {};
    }
}
function parseCampaignSourceSeeds(campaignConfig) {
    const seeds = new Map();
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
function coerceMonsterInteger(value, defaultValue = 0) {
    const parsed = Number.parseInt(String(value ?? "").trim(), 10);
    return Number.isFinite(parsed) ? parsed : defaultValue;
}
function extractMonsterHpAverage(value) {
    const record = asRecord(value);
    if (Object.keys(record).length > 0) {
        return coerceMonsterInteger(record.average, 0);
    }
    return coerceMonsterInteger(value, 0);
}
function extractMaxDistance(value) {
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
function emptyCombatRuntimeState() {
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
function buildLiveHash(...parts) {
    const normalized = parts.map((part) => String(part ?? "").trim().toLowerCase()).join("||");
    return createHash("sha1").update(normalized).digest("hex").slice(0, 12);
}
function serializeStatblockChoice(row) {
    return {
        id: String(row.id),
        title: String(row.title || ""),
        subtitle: `HP ${Number(row.max_hp || 0)} - Speed ${String(row.speed_text || "")}`,
        initiative_bonus: formatInitiativeBonus(Number(row.initiative_bonus || 0)),
    };
}
function profileClassLevelText(profile, defaultValue = "Character") {
    const classRows = Array.isArray(profile.classes) ? profile.classes : [];
    const parts = [];
    for (const classRow of classRows) {
        const row = asRecord(classRow);
        const systemsRef = asRecord(row.systems_ref);
        const className = asString(systemsRef.title) || asString(row.class_name);
        const classLevel = asNumber(row.level);
        if (className && classLevel > 0) {
            parts.push(`${className} ${classLevel}`);
        }
        else if (className) {
            parts.push(className);
        }
        else if (classLevel > 0) {
            parts.push(`Level ${classLevel}`);
        }
    }
    if (parts.length > 0) {
        return parts.join(" / ");
    }
    return asString(profile.class_level_text) || defaultValue;
}
function serializeCharacterChoice(record) {
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
function parseStateJson(rawJson) {
    try {
        return asRecord(JSON.parse(rawJson));
    }
    catch {
        return {};
    }
}
function readCharacterStateSnapshot(database, campaignSlug, characterSlug) {
    try {
        const row = database
            .prepare(`
          SELECT character_slug, revision, state_json
          FROM character_state
          WHERE campaign_slug = ?
            AND character_slug = ?
        `)
            .get(campaignSlug, characterSlug);
        return row
            ? {
                revision: Math.max(1, Number(row.revision || 1)),
                state: parseStateJson(row.state_json),
            }
            : null;
    }
    catch (error) {
        if (isNoSuchTableOrColumnError(error)) {
            return null;
        }
        throw error;
    }
}
function readCharacterStateSnapshots(database, campaignSlug) {
    const snapshots = new Map();
    try {
        const rows = database
            .prepare(`
          SELECT character_slug, revision, state_json
          FROM character_state
          WHERE campaign_slug = ?
        `)
            .all(campaignSlug);
        for (const row of rows) {
            snapshots.set(String(row.character_slug || ""), {
                revision: Math.max(1, Number(row.revision || 1)),
                state: parseStateJson(row.state_json),
            });
        }
    }
    catch (error) {
        if (isNoSuchTableOrColumnError(error)) {
            return snapshots;
        }
        throw error;
    }
    return snapshots;
}
function readCharacterStateVitals(database, campaignSlug, characterSlug) {
    const snapshot = readCharacterStateSnapshot(database, campaignSlug, characterSlug);
    return snapshot ? asRecord(snapshot.state.vitals) : {};
}
function parseMovementTotal(value) {
    const matches = [...payloadString(value).matchAll(/\d+/g)].map((match) => Number(match[0]));
    return matches.length > 0 ? Math.max(...matches) : 0;
}
function extractDexterityModifier(stats) {
    const abilityScores = asRecord(stats.ability_scores);
    const dexterity = abilityScores.dex ??
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
function parseWholeInteger(value) {
    if (!/^[+-]?\d+$/.test(value)) {
        return null;
    }
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : null;
}
function parseCombatInteger(value, label, defaultValue, minimum = 0) {
    const normalized = value === null || value === undefined ? "" : payloadString(value);
    const parsed = normalized === ""
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
function parseCombatBoolean(payload, key, label, defaultValue) {
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
function parseInitiativePriority(value, defaultValue) {
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
function parseOptionalCombatantRevision(value) {
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
function parseExpectedCharacterStateRevision(value) {
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
function buildPlayerCharacterSnapshot(database, campaignSlug, record) {
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
function listAvailableCharacterChoices(records, canManageCombat, existingCharacterSlugs) {
    if (!canManageCombat) {
        return [];
    }
    return records
        .filter((record) => asString(record.definition.status) === "active")
        .filter((record) => !existingCharacterSlugs.has(record.character_slug))
        .map(serializeCharacterChoice);
}
function listAvailableStatblockChoices(database, campaignSlug, canAccessDmContent) {
    if (!canAccessDmContent) {
        return [];
    }
    try {
        return database
            .prepare(`
            SELECT id, title, max_hp, speed_text, initiative_bonus
            FROM campaign_dm_statblocks
            WHERE campaign_slug = ?
            ORDER BY updated_at DESC, title COLLATE NOCASE ASC, id DESC
          `)
            .all(campaignSlug).map(serializeStatblockChoice);
    }
    catch (error) {
        if (isNoSuchTableOrColumnError(error)) {
            return [];
        }
        throw error;
    }
}
function readDmStatblockDetailRow(database, campaignSlug, statblockId) {
    return (database
        .prepare(`
          SELECT id, title, body_markdown, max_hp, speed_text, movement_total, initiative_bonus
          FROM campaign_dm_statblocks
          WHERE campaign_slug = ? AND id = ?
        `)
        .get(campaignSlug, statblockId) || null);
}
function readSystemsMonsterEntryRow(database, librarySlug, entryKey) {
    return (database
        .prepare(`
          SELECT source_id, entry_key, entry_type, title, metadata_json, body_json
          FROM systems_entries
          WHERE library_slug = ? AND entry_key = ?
        `)
        .get(librarySlug, entryKey) || null);
}
function readSystemsSourceAccessRow(database, campaignSlug, librarySlug, sourceId) {
    return (database
        .prepare(`
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
        `)
        .get(campaignSlug, librarySlug, sourceId) || null);
}
function isSystemsSourceEnabledForCampaign(database, campaignSlug, librarySlug, sourceId, sourceSeeds) {
    const sourceRow = readSystemsSourceAccessRow(database, campaignSlug, librarySlug, sourceId);
    if (!sourceRow) {
        return false;
    }
    const isConfigured = sourceRow.configured_enabled !== null || Boolean(sourceRow.configured_visibility);
    return isConfigured ? Boolean(sourceRow.configured_enabled) : Boolean(sourceSeeds.get(sourceId)?.enabled);
}
function isSystemsEntryEnabledForCampaign(database, campaignSlug, librarySlug, entry, sourceSeeds) {
    if (!isSystemsSourceEnabledForCampaign(database, campaignSlug, librarySlug, entry.source_id, sourceSeeds)) {
        return false;
    }
    const override = database
        .prepare(`
        SELECT is_enabled_override
        FROM campaign_entry_overrides
        WHERE campaign_slug = ?
          AND library_slug = ?
          AND entry_key = ?
      `)
        .get(campaignSlug, librarySlug, entry.entry_key);
    return override?.is_enabled_override !== 0;
}
function listCombatConditionOptions(database, campaignSlug) {
    try {
        const conditionNames = database
            .prepare(`
            SELECT name
            FROM campaign_dm_condition_definitions
            WHERE campaign_slug = ?
            ORDER BY name COLLATE NOCASE ASC, id ASC
          `)
            .all(campaignSlug).map((row) => String(row.name || "").trim()).filter(Boolean);
        return [...new Set([...DND_5E_CONDITION_OPTIONS, ...conditionNames])].sort();
    }
    catch (error) {
        if (isNoSuchTableOrColumnError(error)) {
            return [...DND_5E_CONDITION_OPTIONS];
        }
        throw error;
    }
}
function characterRecordMap(records) {
    return new Map(records.map((record) => [record.character_slug, record]));
}
function rowsByCombatantId(rows) {
    const grouped = new Map();
    for (const row of rows) {
        const existing = grouped.get(row.combatant_id) || [];
        existing.push(row);
        grouped.set(row.combatant_id, existing);
    }
    return grouped;
}
function combatantSourceKind(row) {
    return row.source_kind || (row.character_slug ? "character" : "manual_npc");
}
function presentCombatant(options) {
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
        initiative_priority_label: options.canManageCombat && Number(row.initiative_priority || 0) > 0 ? String(row.initiative_priority) : "",
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
function selectCombatPayload(campaignSlug, tracker, canManageCombat) {
    const combatants = tracker.combatants;
    const selectedCombatant = combatants.find((combatant) => combatant.is_current_turn === true) || combatants[0] || null;
    const selectedCombatantId = typeof selectedCombatant?.id === "number" ? Number(selectedCombatant.id) : null;
    const playerCharacters = combatants.filter((combatant) => asString(combatant.character_slug));
    const selectedPlayerCharacter = playerCharacters.find((combatant) => combatant.id === selectedCombatantId) ||
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
function readCombatTrackerRow(database, campaignSlug) {
    return (database
        .prepare(`
          SELECT round_number, current_combatant_id, revision
          FROM campaign_combat_trackers
          WHERE campaign_slug = ?
        `)
        .get(campaignSlug) || null);
}
function ensureCombatTrackerRow(database, campaignSlug, actorUserId) {
    const existing = readCombatTrackerRow(database, campaignSlug);
    if (existing) {
        return existing;
    }
    database
        .prepare(`
        INSERT INTO campaign_combat_trackers (
          campaign_slug,
          round_number,
          current_combatant_id,
          revision,
          updated_at,
          updated_by_user_id
        )
        VALUES (?, 1, NULL, 1, ?, ?)
      `)
        .run(campaignSlug, utcIsoTimestamp(), actorUserId);
    const created = readCombatTrackerRow(database, campaignSlug);
    if (!created) {
        throw new Error("Failed to persist campaign combat tracker.");
    }
    return created;
}
function readCombatantRows(database, campaignSlug) {
    return database
        .prepare(`
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
      `)
        .all(campaignSlug);
}
function readCombatantRow(database, campaignSlug, combatantId) {
    return (database
        .prepare(`
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
        `)
        .get(campaignSlug, combatantId) || null);
}
function readCombatConditionRows(database, campaignSlug) {
    return database
        .prepare(`
        SELECT c.id, c.combatant_id, c.name, c.duration_text
        FROM campaign_combat_conditions AS c
        JOIN campaign_combatants AS e ON e.id = c.combatant_id
        WHERE e.campaign_slug = ?
        ORDER BY c.created_at ASC, c.id ASC
      `)
        .all(campaignSlug);
}
function readCombatResourceCounterRows(database, campaignSlug) {
    return database
        .prepare(`
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
      `)
        .all(campaignSlug);
}
function readCombatResourceCounterRowsForCombatant(database, campaignSlug, combatantId) {
    return database
        .prepare(`
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
      `)
        .all(campaignSlug, combatantId);
}
function readCombatResourceNoteRows(database, campaignSlug) {
    return database
        .prepare(`
        SELECT n.id, n.combatant_id, n.label, n.note, n.source_label
        FROM campaign_combatant_resource_notes AS n
        JOIN campaign_combatants AS e ON e.id = n.combatant_id
        WHERE e.campaign_slug = ?
        ORDER BY n.id ASC
      `)
        .all(campaignSlug);
}
function loadCombatRuntimeState(dbPath, campaignSlug, canManageCombat, characterRecords) {
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
        const currentCombatantId = trackerRow?.current_combatant_id === null || trackerRow?.current_combatant_id === undefined
            ? null
            : Number(trackerRow.current_combatant_id);
        const characterRecordsBySlug = characterRecordMap(characterRecords);
        const characterStateBySlug = readCharacterStateSnapshots(database, campaignSlug);
        const combatants = combatantRows.map((row) => presentCombatant({
            row,
            currentCombatantId,
            canManageCombat,
            characterRecordsBySlug,
            characterStateBySlug,
            conditions: conditionsByCombatant.get(row.id) || [],
            resourceCounters: countersByCombatant.get(row.id) || [],
            resourceNotes: notesByCombatant.get(row.id) || [],
        }));
        const currentCombatant = combatantRows.find((row) => Number(row.id) === currentCombatantId);
        const tracker = {
            round_number: Math.max(1, Number(trackerRow?.round_number || 1)),
            current_turn_label: currentCombatant ? String(currentCombatant.display_name || "") : "",
            has_current_turn: Boolean(currentCombatant),
            combatant_count: combatants.length,
            combatants,
        };
        return {
            liveRevision: trackerRow ? Math.max(1, Number(trackerRow.revision || 1)) : COMBAT_READONLY_REVISION,
            tracker,
            existingCharacterSlugs: new Set(combatantRows.map((row) => String(row.character_slug || "")).filter(Boolean)),
            ...selectCombatPayload(campaignSlug, tracker, canManageCombat),
        };
    }
    catch (error) {
        if (isNoSuchTableOrColumnError(error)) {
            return emptyCombatRuntimeState();
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function setCurrentCombatant(dbPath, campaignSlug, combatantId, actorUserId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeSetCurrent = database.transaction(() => {
            const combatant = readCombatantRow(database, campaignSlug, combatantId);
            if (!combatant) {
                return { status: "validation_error", message: "That combatant could not be found." };
            }
            const tracker = ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            resetCombatantTurnResources(database, campaignSlug, combatantId, actorUserId, now, "That combatant could not be found.");
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET round_number = ?,
                current_combatant_id = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(Math.max(1, Number(tracker.round_number || 1)), combatantId, now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The current turn could not be updated.");
            }
            return { status: "ok" };
        });
        return writeSetCurrent();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function updateCombatantTurn(dbPath, campaignSlug, combatantId, payload, actorUserId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const expectedRevision = parseOptionalCombatantRevision(payload.expected_combatant_revision);
    if (!expectedRevision.ok) {
        return { status: "validation_error", message: expectedRevision.message };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeTurnValue = database.transaction(() => {
            const combatant = readCombatantRow(database, campaignSlug, combatantId);
            if (!combatant) {
                return { status: "validation_error", message: "That combatant could not be found." };
            }
            const turnValue = parseCombatInteger(payload.turn_value, "Turn value", Number(combatant.turn_value || 0), null);
            if (!turnValue.ok) {
                return { status: "validation_error", message: turnValue.message };
            }
            const initiativePriority = parseInitiativePriority(payload.initiative_priority, Number(combatant.initiative_priority || 1));
            if (!initiativePriority.ok) {
                return { status: "validation_error", message: initiativePriority.message };
            }
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            const parameters = [
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
                .prepare(`
            UPDATE campaign_combatants
            SET turn_value = ?,
                initiative_priority = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `)
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
                .prepare(`
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The combat tracker could not be updated.");
            }
            return { status: "ok" };
        });
        return writeTurnValue();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function isCombatManager(role) {
    return role === "dm" || role === "admin";
}
function actorOwnsCharacter(database, campaignSlug, characterSlug, actorUserId) {
    try {
        const row = database
            .prepare(`
          SELECT 1 AS allowed
          FROM character_assignments
          WHERE campaign_slug = ?
            AND character_slug = ?
            AND user_id = ?
          LIMIT 1
        `)
            .get(campaignSlug, characterSlug, actorUserId);
        return Boolean(row?.allowed);
    }
    catch (error) {
        if (isNoSuchTableOrColumnError(error)) {
            return false;
        }
        throw error;
    }
}
function bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now) {
    ensureCombatTrackerRow(database, campaignSlug, actorUserId);
    const trackerUpdate = database
        .prepare(`
        UPDATE campaign_combat_trackers
        SET revision = revision + 1,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ?
      `)
        .run(now, actorUserId, campaignSlug);
    if (trackerUpdate.changes !== 1) {
        throw new CombatMutationConflictError("The combat tracker could not be updated.");
    }
}
function updateNpcCombatantVitals(database, campaignSlug, combatant, payload, actorUserId) {
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
    const movementTotal = parseCombatInteger(payload.movement_total, "Movement", Number(combatant.movement_total || 0), 0);
    if (!movementTotal.ok) {
        return { status: "validation_error", message: movementTotal.message };
    }
    if (currentHp.value > maxHp.value) {
        return { status: "validation_error", message: "Current HP cannot exceed max HP." };
    }
    ensureCombatTrackerRow(database, campaignSlug, actorUserId);
    const now = utcIsoTimestamp();
    const parameters = [
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
        .prepare(`
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
      `)
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
function updatePlayerCombatantVitals(database, campaignSlug, combatant, record, payload, actorUserId) {
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
        .run(JSON.stringify(nextState), now, actorUserId, campaignSlug, combatant.character_slug, expectedRevision.value);
    if (stateUpdate.changes !== 1) {
        return {
            status: "state_conflict",
            message: "This sheet changed in another session. Refresh and try again.",
        };
    }
    const movementTotal = parseMovementTotal(stats.speed);
    const combatantUpdate = database
        .prepare(`
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
      `)
        .run(asString(definition.name) || combatant.character_slug, asNumber(stats.initiative_bonus), extractDexterityModifier(stats), currentHp.value, maxHp, tempHp.value, movementTotal, Math.min(Number(combatant.movement_remaining || 0), movementTotal), now, actorUserId, campaignSlug, combatant.id);
    if (combatantUpdate.changes !== 1) {
        throw new CombatMutationConflictError("That combat tracker row could not be updated.");
    }
    bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
    return { status: "ok" };
}
export async function updateCombatantVitals(config, campaignSlug, combatantId, payload, actorUserId, actorRole) {
    if (!existsSync(config.dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const characterRecords = (await listCampaignContentCharacters(config, campaignSlug)) || [];
    const characterRecordsBySlug = characterRecordMap(characterRecords);
    const database = new Database(config.dbPath, { fileMustExist: true });
    try {
        const writeVitals = database.transaction(() => {
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
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function updateCombatantResources(dbPath, campaignSlug, combatantId, payload, actorUserId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeResources = database.transaction(() => {
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
            }
            else if (!manager) {
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
            const hasBonusAction = parseCombatBoolean(payload, "has_bonus_action", "has_bonus_action", asBoolean(combatant.has_bonus_action));
            if (!hasBonusAction.ok) {
                return { status: "validation_error", message: hasBonusAction.message };
            }
            const hasReaction = parseCombatBoolean(payload, "has_reaction", "has_reaction", asBoolean(combatant.has_reaction));
            if (!hasReaction.ok) {
                return { status: "validation_error", message: hasReaction.message };
            }
            const movementRemaining = parseCombatInteger(payload.movement_remaining, "Remaining movement", Number(combatant.movement_remaining || 0), 0);
            if (!movementRemaining.ok) {
                return { status: "validation_error", message: movementRemaining.message };
            }
            if (movementRemaining.value > Number(combatant.movement_total || 0)) {
                return { status: "validation_error", message: "Remaining movement cannot exceed total movement." };
            }
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            const parameters = [
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
                .prepare(`
            UPDATE campaign_combatants
            SET has_action = ?,
                has_bonus_action = ?,
                has_reaction = ?,
                movement_remaining = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `)
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
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function updateCombatantNpcResources(dbPath, campaignSlug, combatantId, payload, actorUserId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeNpcResources = database.transaction(() => {
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
            const valuesByKey = new Map();
            for (let index = 0; index < counterValues.length; index += 1) {
                const counterValue = counterValues[index];
                if (typeof counterValue !== "object" || counterValue === null || Array.isArray(counterValue)) {
                    return { status: "validation_error", message: `NPC resource row ${index + 1} must be an object.` };
                }
                const counterPayload = counterValue;
                const resourceKey = payloadString(counterPayload.resource_key);
                const counter = countersByKey.get(resourceKey);
                if (!resourceKey || !counter) {
                    return { status: "validation_error", message: "Choose a valid NPC resource counter." };
                }
                const currentValue = parseCombatInteger(counterPayload.current_value, `${counter.label} current value`, Number(counter.current_value || 0), 0);
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
            const combatantParameters = [now, actorUserId, campaignSlug, combatantId];
            let expectedRevisionClause = "";
            if (expectedRevision.value !== null) {
                expectedRevisionClause = " AND revision = ?";
                combatantParameters.push(expectedRevision.value);
            }
            const combatantUpdate = database
                .prepare(`
            UPDATE campaign_combatants
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `)
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
            const counterUpdate = database.prepare(`
          UPDATE campaign_combatant_resource_counters
          SET current_value = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE combatant_id = ? AND resource_key = ?
        `);
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
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function updateCombatantPlayerDetailVisibility(dbPath, campaignSlug, combatantId, payload, actorUserId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeVisibility = database.transaction(() => {
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
            const playerDetailVisible = parseCombatBoolean(payload, "player_detail_visible", "player_detail_visible", asBoolean(combatant.player_detail_visible));
            if (!playerDetailVisible.ok) {
                return { status: "validation_error", message: playerDetailVisible.message };
            }
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            const parameters = [
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
                .prepare(`
            UPDATE campaign_combatants
            SET player_detail_visible = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ? AND id = ?${expectedRevisionClause}
          `)
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
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function addCombatCondition(dbPath, campaignSlug, combatantId, payload, actorUserId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeCondition = database.transaction(() => {
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
                .prepare(`
            INSERT INTO campaign_combat_conditions (
              combatant_id,
              name,
              duration_text,
              created_at,
              created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?)
          `)
                .run(combatant.id, name, durationText, now, actorUserId);
            bumpCombatTrackerRevision(database, campaignSlug, actorUserId, now);
            return { status: "ok" };
        });
        return writeCondition();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function updateCombatCondition(dbPath, campaignSlug, conditionId, payload, actorUserId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeCondition = database.transaction(() => {
            if (!isCombatManager(actorRole)) {
                return { status: "forbidden", message: "You do not have permission to manage combat." };
            }
            const condition = database
                .prepare(`
              SELECT c.id
              FROM campaign_combat_conditions AS c
              JOIN campaign_combatants AS e ON e.id = c.combatant_id
              WHERE e.campaign_slug = ? AND c.id = ?
            `)
                .get(campaignSlug, conditionId) || null;
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
                .prepare(`
            UPDATE campaign_combat_conditions
            SET name = ?,
                duration_text = ?
            WHERE id = ?
          `)
                .run(name, durationText, conditionId);
            if (updateResult.changes !== 1) {
                throw new CombatMutationConflictError("That condition could not be found.");
            }
            bumpCombatTrackerRevision(database, campaignSlug, actorUserId, utcIsoTimestamp());
            return { status: "ok" };
        });
        return writeCondition();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function deleteCombatCondition(dbPath, campaignSlug, conditionId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const deleteCondition = database.transaction(() => {
            if (!isCombatManager(actorRole)) {
                return { status: "forbidden", message: "You do not have permission to manage combat." };
            }
            const condition = database
                .prepare(`
              SELECT c.id
              FROM campaign_combat_conditions AS c
              JOIN campaign_combatants AS e ON e.id = c.combatant_id
              WHERE e.campaign_slug = ? AND c.id = ?
            `)
                .get(campaignSlug, conditionId) || null;
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
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function deleteCombatant(dbPath, campaignSlug, combatantId, actorRole) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const deleteCombatantRow = database.transaction(() => {
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
                .prepare(`
            UPDATE campaign_combat_trackers
            SET current_combatant_id = NULL
            WHERE campaign_slug = ? AND current_combatant_id = ?
          `)
                .run(campaignSlug, combatantId);
            bumpCombatTrackerRevision(database, campaignSlug, null, utcIsoTimestamp());
            return { status: "ok" };
        });
        return deleteCombatantRow();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function advanceCombatTurn(dbPath, campaignSlug, actorUserId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeAdvanceTurn = database.transaction(() => {
            const tracker = ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const combatants = readCombatantRows(database, campaignSlug);
            if (combatants.length === 0) {
                return { status: "validation_error", message: "Add combatants before advancing turn order." };
            }
            const currentCombatantId = tracker.current_combatant_id === null || tracker.current_combatant_id === undefined
                ? null
                : Number(tracker.current_combatant_id);
            const currentIndex = combatants.findIndex((combatant) => Number(combatant.id) === currentCombatantId);
            const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % combatants.length;
            const nextRound = currentIndex < 0
                ? Math.max(1, Number(tracker.round_number || 1))
                : nextIndex === 0
                    ? Number(tracker.round_number || 1) + 1
                    : Number(tracker.round_number || 1);
            const nextCombatant = combatants[nextIndex];
            if (!nextCombatant) {
                return { status: "validation_error", message: "Add combatants before advancing turn order." };
            }
            const now = utcIsoTimestamp();
            resetCombatantTurnResources(database, campaignSlug, Number(nextCombatant.id), actorUserId, now, "The turn order could not be advanced.");
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET round_number = ?,
                current_combatant_id = ?,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(Math.max(1, nextRound), Number(nextCombatant.id), now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The turn order could not be advanced.");
            }
            return { status: "ok" };
        });
        return writeAdvanceTurn();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function clearCombatTracker(dbPath, campaignSlug, actorUserId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeClearTracker = database.transaction(() => {
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            database
                .prepare(`
            DELETE FROM campaign_combat_conditions
            WHERE combatant_id IN (
              SELECT id FROM campaign_combatants WHERE campaign_slug = ?
            )
          `)
                .run(campaignSlug);
            database
                .prepare(`
            DELETE FROM campaign_combatant_resource_counters
            WHERE combatant_id IN (
              SELECT id FROM campaign_combatants WHERE campaign_slug = ?
            )
          `)
                .run(campaignSlug);
            database
                .prepare(`
            DELETE FROM campaign_combatant_resource_notes
            WHERE combatant_id IN (
              SELECT id FROM campaign_combatants WHERE campaign_slug = ?
            )
          `)
                .run(campaignSlug);
            database.prepare("DELETE FROM campaign_combatants WHERE campaign_slug = ?").run(campaignSlug);
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET round_number = 1,
                current_combatant_id = NULL,
                revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The combat tracker could not be cleared.");
            }
            return { status: "ok" };
        });
        return writeClearTracker();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function addPlayerCombatant(config, campaignSlug, payload, actorUserId) {
    if (!existsSync(config.dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const characterSlug = payloadString(payload.character_slug);
    const characterRecords = (await listCampaignContentCharacters(config, campaignSlug)) || [];
    const record = characterRecords.find((candidate) => candidate.character_slug === characterSlug &&
        asString(candidate.definition.status) === "active");
    if (!record) {
        return {
            status: "validation_error",
            message: "Choose a valid player character to add to the tracker.",
        };
    }
    persistCharacterStateForDefinition(config, record.definition);
    const database = new Database(config.dbPath, { fileMustExist: true });
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
        const writeAddPlayer = database.transaction(() => {
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const existingCombatant = readCombatantRows(database, campaignSlug).find((combatant) => combatant.character_slug === record.character_slug);
            if (existingCombatant) {
                return {
                    status: "validation_error",
                    message: "That player character is already in the combat tracker.",
                };
            }
            const now = utcIsoTimestamp();
            try {
                database
                    .prepare(`
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
            `)
                    .run(campaignSlug, record.character_slug, record.character_slug, asString(record.definition.name) || record.character_slug, turnValue.value, snapshot.initiativeBonus, snapshot.dexterityModifier, initiativePriority.value, snapshot.currentHp, snapshot.maxHp, snapshot.tempHp, snapshot.movementTotal, snapshot.movementTotal, now, now, actorUserId, actorUserId);
            }
            catch (error) {
                if (error instanceof Error && error.message.includes("UNIQUE constraint failed")) {
                    throw new CombatMutationConflictError("That player character is already in the combat tracker.");
                }
                throw error;
            }
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The combat tracker could not be updated.");
            }
            return { status: "ok" };
        });
        return writeAddPlayer();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function addNpcCombatant(dbPath, campaignSlug, payload, actorUserId) {
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
    const dexterityModifier = parseCombatInteger(payload.dexterity_modifier, "Dexterity modifier", initiativeBonus.value, null);
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
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const writeAddNpc = database.transaction(() => {
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            try {
                database
                    .prepare(`
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
            `)
                    .run(campaignSlug, displayName, turnValue.value, initiativeBonus.value, dexterityModifier.value, initiativePriority.value, currentHp.value, maxHp.value, tempHp.value, movementTotal.value, movementTotal.value, now, now, actorUserId, actorUserId);
            }
            catch (error) {
                if (error instanceof Error && error.message.includes("constraint failed")) {
                    throw new CombatMutationConflictError("Unable to create combatant.");
                }
                throw error;
            }
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The combat tracker could not be updated.");
            }
            return { status: "ok" };
        });
        return writeAddNpc();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function insertNpcResourceSeeds(database, combatantId, counterSeeds, noteSeeds, actorUserId, now) {
    const counterInsert = database.prepare(`
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
    `);
    for (const seed of counterSeeds) {
        counterInsert.run(combatantId, seed.resourceKey, seed.label, seed.currentValue, seed.maxValue, seed.resetLabel, seed.sourceLabel, now, now, actorUserId, actorUserId);
    }
    const noteInsert = database.prepare(`
      INSERT INTO campaign_combatant_resource_notes (
        combatant_id,
        label,
        note,
        source_label,
        created_at,
        created_by_user_id
      )
      VALUES (?, ?, ?, ?, ?, ?)
    `);
    for (const seed of noteSeeds) {
        noteInsert.run(combatantId, seed.label, seed.note, seed.sourceLabel, now, actorUserId);
    }
}
export function addStatblockCombatant(dbPath, campaignSlug, payload, actorUserId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const statblockId = parseWholeInteger(payloadString(payload.statblock_id));
    if (statblockId === null || statblockId < 1) {
        return { status: "validation_error", message: "Choose a valid DM Content statblock to add." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const statblock = readDmStatblockDetailRow(database, campaignSlug, statblockId);
        if (!statblock) {
            return { status: "validation_error", message: "Choose a valid DM Content statblock to add." };
        }
        const initiativeBonus = Number(statblock.initiative_bonus || 0);
        const turnRaw = payload.turn_value === null || payload.turn_value === undefined || payloadString(payload.turn_value) === ""
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
        const writeAddStatblock = database.transaction(() => {
            ensureCombatTrackerRow(database, campaignSlug, actorUserId);
            const now = utcIsoTimestamp();
            let combatantId = 0;
            try {
                const insertResult = database
                    .prepare(`
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
            `)
                    .run(campaignSlug, String(statblock.id), displayName, turnValue.value, initiativeBonus, dexterityModifier, initiativePriority.value, maxHp, maxHp, movementTotal, movementTotal, now, now, actorUserId, actorUserId);
                combatantId = Number(insertResult.lastInsertRowid);
                insertNpcResourceSeeds(database, combatantId, resourceSeeds.counters, resourceSeeds.notes, actorUserId, now);
            }
            catch (error) {
                if (error instanceof Error && error.message.includes("constraint failed")) {
                    throw new CombatMutationConflictError("Unable to create combatant.");
                }
                throw error;
            }
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(now, actorUserId, campaignSlug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The combat tracker could not be updated.");
            }
            return { status: "ok" };
        });
        return writeAddStatblock();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function addSystemsMonsterCombatant(dbPath, campaign, campaignConfig, payload, actorUserId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Combat storage is not initialized." };
    }
    const entryKey = payloadString(payload.entry_key);
    const librarySlug = campaign.systems_library_slug || "";
    if (!entryKey || !librarySlug) {
        return { status: "validation_error", message: "Choose a valid Systems monster to add." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const entry = readSystemsMonsterEntryRow(database, librarySlug, entryKey);
        const sourceSeeds = parseCampaignSourceSeeds(campaignConfig);
        if (!entry ||
            String(entry.entry_type || "").trim().toLowerCase() !== "monster" ||
            !isSystemsEntryEnabledForCampaign(database, campaign.slug, librarySlug, entry, sourceSeeds)) {
            return { status: "validation_error", message: "Choose a valid Systems monster to add." };
        }
        const metadata = parseJsonObject(entry.metadata_json);
        const abilities = asRecord(metadata.abilities);
        const dexterityScore = coerceMonsterInteger(abilities.dex, 10);
        const initiativeBonus = Math.floor((dexterityScore - 10) / 2);
        const maxHp = Math.max(0, extractMonsterHpAverage(metadata.hp));
        const movementTotal = Math.max(0, extractMaxDistance(metadata.speed));
        const turnRaw = payload.turn_value === null || payload.turn_value === undefined || payloadString(payload.turn_value) === ""
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
        const writeAddSystemsMonster = database.transaction(() => {
            ensureCombatTrackerRow(database, campaign.slug, actorUserId);
            const now = utcIsoTimestamp();
            try {
                const insertResult = database
                    .prepare(`
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
            `)
                    .run(campaign.slug, entry.entry_key, displayName, turnValue.value, initiativeBonus, initiativeBonus, initiativePriority.value, maxHp, maxHp, movementTotal, movementTotal, now, now, actorUserId, actorUserId);
                insertNpcResourceSeeds(database, Number(insertResult.lastInsertRowid), resourceSeeds.counters, resourceSeeds.notes, actorUserId, now);
            }
            catch (error) {
                if (error instanceof Error && error.message.includes("constraint failed")) {
                    throw new CombatMutationConflictError("Unable to create combatant.");
                }
                throw error;
            }
            const trackerUpdate = database
                .prepare(`
            UPDATE campaign_combat_trackers
            SET revision = revision + 1,
                updated_at = ?,
                updated_by_user_id = ?
            WHERE campaign_slug = ?
          `)
                .run(now, actorUserId, campaign.slug);
            if (trackerUpdate.changes !== 1) {
                throw new CombatMutationConflictError("The combat tracker could not be updated.");
            }
            return { status: "ok" };
        });
        return writeAddSystemsMonster();
    }
    catch (error) {
        if (error instanceof CombatMutationConflictError) {
            return { status: "validation_error", message: error.message };
        }
        if (isNoSuchTableOrColumnError(error)) {
            return { status: "validation_error", message: "Combat storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function loadDmContentCombatChoices(dbPath, campaignSlug, canAccessDmContent) {
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
    }
    finally {
        database.close();
    }
}
export function buildCombatLiveViewToken(role, selectedCombatantId) {
    const canManageCombat = role === "dm" || role === "admin";
    return buildLiveHash("combat", "player", canManageCombat ? "1" : "0", selectedCombatantId ?? "");
}
export async function buildCombatReadOnlyPayload(config, campaign, role) {
    const canManageCombat = role === "dm" || role === "admin";
    const canAccessScopedPlayerTools = role === "player" || canManageCombat;
    const canAccessDmContent = canManageCombat;
    const combatSystemSupported = supportsCombatTracker(campaign.system);
    const characterRecords = combatSystemSupported ? (await listCampaignContentCharacters(config, campaign.slug)) || [] : [];
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
