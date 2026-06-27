import { existsSync } from "node:fs";

import Database from "better-sqlite3";
import { unzipSync } from "fflate";

import { slugify } from "../wiki/repository.js";

type SqliteDatabase = Database.Database;

export interface Dnd5eImportResult {
  source_id: string;
  import_run_id: number;
  import_version: string;
  imported_count: number;
  imported_by_type: Record<string, number>;
  source_files: string[];
}

export interface SystemsImportRun {
  id: number;
  library_slug: string;
  source_id: string;
  status: string;
  import_version: string;
  source_path: string;
  summary: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
  started_by_user_id: number | null;
}

export type Dnd5eImportRouteResult =
  | { status: "ok"; import_results: Dnd5eImportResult[]; import_runs: SystemsImportRun[] }
  | { status: "validation_error"; message: string };

interface EmbeddedArchiveFile {
  filename: string;
  data_blob: Buffer;
}

interface ImportPayload {
  sourceIds: string[];
  entryTypes: string[] | null;
  archive: EmbeddedArchiveFile;
  importVersion: string;
  sourcePathLabel: string;
}

interface DatasetDefinition {
  entryType: string;
  relativePath: string;
  jsonKey: string;
  splitBySource?: boolean;
}

interface PreparedEntry {
  entry_key: string;
  entry_type: string;
  slug: string;
  title: string;
  source_page: string;
  source_path: string;
  search_text: string;
  player_safe_default: boolean;
  dm_heavy: boolean;
  metadata: Record<string, unknown>;
  body: Record<string, unknown>;
  rendered_html: string;
}

interface SystemsImportRunRow {
  id: number;
  library_slug: string;
  source_id: string;
  status: string;
  import_version: string | null;
  source_path: string | null;
  summary_json: string | null;
  started_at: string;
  completed_at: string | null;
  started_by_user_id: number | null;
}

const DND_5E_LIBRARY_SLUG = "DND-5E";

export const DND5E_SUPPORTED_ENTRY_TYPES = [
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
] as const;

const SUPPORTED_ENTRY_TYPE_SET = new Set<string>(DND5E_SUPPORTED_ENTRY_TYPES);
const PLAYER_SAFE_SOURCE_IDS = new Set(["PHB", "SCAG", "XGE", "TCE", "EGW"]);
const PLAYER_SAFE_ENTRY_TYPES = new Set([
  "action",
  "background",
  "class",
  "classfeature",
  "condition",
  "feat",
  "item",
  "optionalfeature",
  "race",
  "sense",
  "skill",
  "spell",
  "status",
  "subclass",
  "subclassfeature",
  "variantrule",
]);
const UNSUPPORTED_CLASS_VARIANT_SOURCE_IDS = new Set(["XPHB", "EFA"]);
const SUPPORTED_SUBCLASS_SOURCE_IDS = new Set(["PHB", "SCAG", "XGE", "TCE", "EGW", "DMG", "MM", "MTF", "VGM"]);
const MEDIA_KEYS = new Set([
  "altArt",
  "foundryImg",
  "hasFluff",
  "hasFluffImages",
  "hasToken",
  "image",
  "images",
  "soundClip",
  "token",
  "tokenHref",
  "tokenUrl",
]);

const DATASETS: DatasetDefinition[] = [
  { entryType: "spell", relativePath: "data/spells/spells-{source_slug}.json", jsonKey: "spell", splitBySource: true },
  { entryType: "monster", relativePath: "data/bestiary/bestiary-{source_slug}.json", jsonKey: "monster", splitBySource: true },
  { entryType: "action", relativePath: "data/actions.json", jsonKey: "action" },
  { entryType: "condition", relativePath: "data/conditionsdiseases.json", jsonKey: "condition" },
  { entryType: "disease", relativePath: "data/conditionsdiseases.json", jsonKey: "disease" },
  { entryType: "status", relativePath: "data/conditionsdiseases.json", jsonKey: "status" },
  { entryType: "background", relativePath: "data/backgrounds.json", jsonKey: "background" },
  { entryType: "feat", relativePath: "data/feats.json", jsonKey: "feat" },
  { entryType: "item", relativePath: "data/items-base.json", jsonKey: "baseitem" },
  { entryType: "item", relativePath: "data/items.json", jsonKey: "item" },
  { entryType: "item", relativePath: "data/magicvariants.json", jsonKey: "magicvariant" },
  { entryType: "optionalfeature", relativePath: "data/optionalfeatures.json", jsonKey: "optionalfeature" },
  { entryType: "race", relativePath: "data/races.json", jsonKey: "race" },
  { entryType: "sense", relativePath: "data/senses.json", jsonKey: "sense" },
  { entryType: "skill", relativePath: "data/skills.json", jsonKey: "skill" },
  { entryType: "variantrule", relativePath: "data/variantrules.json", jsonKey: "variantrule" },
  { entryType: "class", relativePath: "data/class/index.json", jsonKey: "class" },
  { entryType: "classfeature", relativePath: "data/class/index.json", jsonKey: "classFeature" },
  { entryType: "subclass", relativePath: "data/class/index.json", jsonKey: "subclass" },
  { entryType: "subclassfeature", relativePath: "data/class/index.json", jsonKey: "subclassFeature" },
];

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function utcIsoTimestamp(date = new Date()): string {
  return date.toISOString().replace("Z", "+00:00");
}

function titleFromFilename(filename: string): string {
  return filename.replace(/\.[^.]+$/, "").trim();
}

function decodeEmbeddedArchive(payload: unknown): EmbeddedArchiveFile | { error: string } {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { error: "archive must be an object." };
  }
  const record = payload as Record<string, unknown>;
  const filename = String(record.filename || "").trim();
  const dataBase64 = String(record.data_base64 || "").trim();
  if (!filename) {
    return { error: "archive filename is required." };
  }
  if (!dataBase64) {
    return { error: "archive data_base64 is required." };
  }
  if (dataBase64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(dataBase64)) {
    return { error: "archive data_base64 must be valid base64." };
  }
  const dataBlob = Buffer.from(dataBase64, "base64");
  if (dataBlob.toString("base64").replace(/=+$/g, "") !== dataBase64.replace(/=+$/g, "")) {
    return { error: "archive data_base64 must be valid base64." };
  }
  return { filename, data_blob: dataBlob };
}

function normalizeSourceIds(value: unknown): string[] | { error: string } {
  if (!Array.isArray(value)) {
    return { error: "source_ids must be an array of source IDs." };
  }
  const sourceIds = Array.from(
    new Set(value.map((item) => String(item || "").trim().toUpperCase()).filter(Boolean)),
  );
  if (sourceIds.length === 0) {
    return { error: "At least one source ID is required." };
  }
  return sourceIds;
}

function normalizeEntryTypes(value: unknown): string[] | null | { error: string } {
  if (value === null || value === undefined) {
    return null;
  }
  if (!Array.isArray(value)) {
    return { error: "entry_types must be an array when provided." };
  }
  const entryTypes = Array.from(new Set(value.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean)));
  const invalid = entryTypes.filter((entryType) => !SUPPORTED_ENTRY_TYPE_SET.has(entryType)).sort();
  if (invalid.length > 0) {
    return { error: `Unsupported entry_types: ${invalid.join(", ")}` };
  }
  return entryTypes;
}

function normalizeImportPayload(payload: Record<string, unknown>): ImportPayload | { error: string } {
  const sourceIds = normalizeSourceIds(payload.source_ids);
  if (!Array.isArray(sourceIds)) {
    return sourceIds;
  }
  const entryTypes = normalizeEntryTypes(payload.entry_types);
  if (entryTypes && !Array.isArray(entryTypes)) {
    return entryTypes;
  }
  const archive = decodeEmbeddedArchive(payload.archive);
  if ("error" in archive) {
    return archive;
  }
  const archiveFilename = archive.filename.trim();
  if (!archiveFilename.toLowerCase().endsWith(".zip")) {
    return { error: "archive filename must end with .zip." };
  }
  const importVersion = String(payload.import_version || "").trim() || titleFromFilename(archiveFilename);
  const sourcePathLabel = String(payload.source_path_label || "").trim() || `api-upload:${archiveFilename}`;
  return {
    sourceIds,
    entryTypes,
    archive,
    importVersion,
    sourcePathLabel,
  };
}

function normalizeArchiveMemberName(rawName: string): string | null {
  const slashNormalized = rawName.replace(/\\/g, "/");
  const normalized = slashNormalized.replace(/^\/+|\/+$/g, "");
  if (!normalized) {
    return null;
  }
  const parts = normalized.split("/").filter(Boolean);
  if (slashNormalized.startsWith("/") || /^[A-Za-z]:\//.test(slashNormalized) || parts.includes("..")) {
    throw new Error("Import archives must not contain absolute or parent-relative paths.");
  }
  return parts.join("/");
}

function readArchiveFiles(archiveBytes: Buffer): Map<string, Buffer> | { error: string } {
  let rawFiles: Record<string, Uint8Array>;
  try {
    rawFiles = unzipSync(new Uint8Array(archiveBytes));
  } catch {
    return { error: "Import archive must be a valid ZIP file." };
  }
  const files = new Map<string, Buffer>();
  try {
    for (const [rawName, data] of Object.entries(rawFiles)) {
      const normalizedName = normalizeArchiveMemberName(rawName);
      if (!normalizedName || normalizedName.endsWith("/")) {
        continue;
      }
      files.set(normalizedName, Buffer.from(data));
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Import archive contains an unsafe file path." };
  }
  if (files.size === 0) {
    return { error: "Import archive did not contain any files." };
  }
  return files;
}

function resolveDataRootPrefix(files: Map<string, Buffer>): string | { error: string } {
  const names = Array.from(files.keys());
  const hasRootData = names.some((name) => name.startsWith("data/"));
  if (hasRootData) {
    return "";
  }
  const topLevelDirs = new Set<string>();
  for (const name of names) {
    const [topLevel] = name.split("/");
    if (topLevel) {
      topLevelDirs.add(topLevel);
    }
  }
  if (topLevelDirs.size === 1) {
    const [topLevel] = Array.from(topLevelDirs);
    const prefix = `${topLevel}/`;
    if (names.some((name) => name.startsWith(`${prefix}data/`))) {
      return prefix;
    }
  }
  return {
    error:
      "Import archives must contain a compatible DND 5E source data/ directory at the root or inside one top-level folder.",
  };
}

function readJsonFile(files: Map<string, Buffer>, dataRootPrefix: string, relativePath: string): unknown | null {
  const bytes = files.get(`${dataRootPrefix}${relativePath}`);
  if (!bytes) {
    return null;
  }
  return JSON.parse(bytes.toString("utf8"));
}

function datasetPath(dataset: DatasetDefinition, sourceId: string): string {
  return dataset.splitBySource
    ? dataset.relativePath.replace("{source_slug}", sourceId.toLowerCase())
    : dataset.relativePath;
}

function cleanData(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(cleanData);
  }
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (MEDIA_KEYS.has(key)) {
        continue;
      }
      output[key] = cleanData(nested);
    }
    return output;
  }
  return value;
}

function extractText(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(extractText).filter(Boolean).join(" ");
  }
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>).map(extractText).filter(Boolean).join(" ");
  }
  return "";
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeInlineTags(value: string): string {
  return value.replace(/\{@([^{}]+)\}/g, (_match, body: string) => {
    const parts = String(body).split("|");
    const [tagAndText, fallbackText] = parts;
    const pieces = String(tagAndText).trim().split(/\s+/);
    const tag = pieces.shift()?.toLowerCase() || "";
    const primaryText = pieces.join(" ").trim() || String(fallbackText || "").trim();
    if (tag === "hit") {
      return primaryText.startsWith("+") || primaryText.startsWith("-") ? primaryText : `+${primaryText}`;
    }
    if (tag === "h") {
      return "Hit:";
    }
    if (tag === "dc") {
      return `DC ${primaryText}`;
    }
    return primaryText || tag;
  });
}

function renderEntriesHtml(value: unknown): string {
  if (!value) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map(renderEntriesHtml).filter(Boolean).join("\n");
  }
  if (typeof value === "string") {
    return `<p>${escapeHtml(normalizeInlineTags(value))}</p>`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const name = String(record.name || "").trim();
    const entries = renderEntriesHtml(record.entries);
    if (name && entries) {
      return `<section><h3>${escapeHtml(name)}</h3>${entries}</section>`;
    }
    return entries || `<pre>${escapeHtml(JSON.stringify(cleanData(value), null, 2))}</pre>`;
  }
  return `<p>${escapeHtml(String(value))}</p>`;
}

function normalizeLookup(value: string): string {
  return slugify(value).replace(/\//g, "-").replace(/-/g, " ").trim().toLowerCase();
}

function identitySeed(entryType: string, rawEntry: Record<string, unknown>): string {
  const title = String(rawEntry.name || "").trim();
  const className = String(rawEntry.className || "").trim();
  const subclassShortName = String(rawEntry.shortName || rawEntry.name || "").trim();
  if (entryType === "subclass" && className) {
    return slugify(`${className}-${subclassShortName}`).replace(/\//g, "-") || normalizeLookup(title);
  }
  return slugify(title).replace(/\//g, "-") || normalizeLookup(title) || "entry";
}

function makeUniqueIdentifier(base: string, used: Set<string>, page: unknown): string {
  if (!used.has(base)) {
    used.add(base);
    return base;
  }
  const pageValue = String(page || "").trim();
  if (pageValue) {
    const withPage = `${base}-p${pageValue}`;
    if (!used.has(withPage)) {
      used.add(withPage);
      return withPage;
    }
  }
  let suffix = 2;
  while (true) {
    const candidate = `${base}-${suffix}`;
    if (!used.has(candidate)) {
      used.add(candidate);
      return candidate;
    }
    suffix += 1;
  }
}

function shouldSkipEntry(entryType: string, rawEntry: Record<string, unknown>): boolean {
  if (entryType === "subclass" || entryType === "subclassfeature") {
    const classSource = String(rawEntry.classSource || "").toUpperCase();
    if (UNSUPPORTED_CLASS_VARIANT_SOURCE_IDS.has(classSource)) {
      return true;
    }
  }
  if (entryType === "subclassfeature") {
    const subclassSource = String(rawEntry.subclassSource || "").toUpperCase();
    if (subclassSource && !SUPPORTED_SUBCLASS_SOURCE_IDS.has(subclassSource)) {
      return true;
    }
  }
  return false;
}

function isPlayerSafeDefault(sourceId: string, entryType: string): boolean {
  return PLAYER_SAFE_SOURCE_IDS.has(sourceId) && PLAYER_SAFE_ENTRY_TYPES.has(entryType);
}

function isDmHeavy(sourceId: string, entryType: string): boolean {
  return !isPlayerSafeDefault(sourceId, entryType);
}

function buildMetadata(entryType: string, rawEntry: Record<string, unknown>): Record<string, unknown> {
  const metadata: Record<string, unknown> = {};
  for (const key of [
    "level",
    "school",
    "time",
    "range",
    "components",
    "duration",
    "classes",
    "size",
    "type",
    "alignment",
    "ac",
    "hp",
    "speed",
    "str",
    "dex",
    "con",
    "int",
    "wis",
    "cha",
    "rarity",
    "reqAttune",
    "weight",
    "value",
    "weaponCategory",
    "dmg1",
    "dmg2",
    "dmgType",
    "property",
    "className",
    "classSource",
    "subclassSource",
  ]) {
    if (Object.hasOwn(rawEntry, key)) {
      metadata[key] = cleanData(rawEntry[key]);
    }
  }
  if (entryType === "monster") {
    metadata.abilities = {
      str: rawEntry.str,
      dex: rawEntry.dex,
      con: rawEntry.con,
      int: rawEntry.int,
      wis: rawEntry.wis,
      cha: rawEntry.cha,
    };
  }
  metadata.imported_entry_type = entryType;
  return metadata;
}

function buildBody(rawEntry: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  const bodyKeyMap: Array<[string, string]> = [
    ["entries", "entries"],
    ["entriesHigherLevel", "entriesHigherLevel"],
    ["action", "actions"],
    ["trait", "traits"],
    ["reaction", "reactions"],
    ["legendary", "legendary_actions"],
    ["bonus", "bonus_actions"],
    ["variant", "variants"],
  ];
  for (const [rawKey, bodyKey] of bodyKeyMap) {
    if (Object.hasOwn(rawEntry, rawKey)) {
      body[bodyKey] = cleanData(rawEntry[rawKey]);
    }
  }
  if (Object.keys(body).length === 0) {
    body.raw = cleanData(rawEntry);
  }
  return body;
}

function buildRenderedHtml(entryType: string, body: Record<string, unknown>): string {
  const sections: string[] = [];
  const labeledKeys: Array<[string, string]> = [
    ["entries", "Details"],
    ["entriesHigherLevel", "At Higher Levels"],
    ["traits", "Traits"],
    ["actions", "Actions"],
    ["bonus_actions", "Bonus Actions"],
    ["reactions", "Reactions"],
    ["legendary_actions", "Legendary Actions"],
    ["variants", "Variants"],
  ];
  for (const [key, label] of labeledKeys) {
    if (!Object.hasOwn(body, key)) {
      continue;
    }
    const rendered = renderEntriesHtml(body[key]);
    if (rendered) {
      sections.push(`<section class="systems-entry-section"><h2>${label}</h2>${rendered}</section>`);
    }
  }
  if (sections.length > 0) {
    return sections.join("\n");
  }
  return `<section class="systems-entry-section"><h2>${escapeHtml(entryType)}</h2>${renderEntriesHtml(body.raw)}</section>`;
}

function buildEntry(
  librarySlug: string,
  entryType: string,
  rawEntry: Record<string, unknown>,
  sourcePath: string,
  usedEntryKeys: Set<string>,
  usedSlugs: Set<string>,
): PreparedEntry | null {
  const title = String(rawEntry.name || "").trim();
  const sourceId = String(rawEntry.source || "").trim().toUpperCase();
  if (!title || !sourceId || shouldSkipEntry(entryType, rawEntry)) {
    return null;
  }
  const metadata = buildMetadata(entryType, rawEntry);
  const body = buildBody(rawEntry);
  const renderedHtml = buildRenderedHtml(entryType, body);
  const seed = identitySeed(entryType, rawEntry);
  const entryKey = makeUniqueIdentifier(
    `${librarySlug.toLowerCase()}|${entryType}|${sourceId.toLowerCase()}|${seed}`,
    usedEntryKeys,
    rawEntry.page,
  );
  const slug = makeUniqueIdentifier(`${sourceId.toLowerCase()}-${entryType}-${seed}`, usedSlugs, rawEntry.page);
  const searchText = [title, entryType, sourceId, extractText(metadata), extractText(body)].filter(Boolean).join(" ").toLowerCase();
  return {
    entry_key: entryKey,
    entry_type: entryType,
    slug,
    title,
    source_page: String(rawEntry.page || ""),
    source_path: sourcePath,
    search_text: searchText,
    player_safe_default: isPlayerSafeDefault(sourceId, entryType),
    dm_heavy: isDmHeavy(sourceId, entryType),
    metadata,
    body,
    rendered_html: renderedHtml,
  };
}

function rawEntriesForDataset(payload: unknown, dataset: DatasetDefinition): Record<string, unknown>[] {
  const record = asRecord(payload);
  const rawEntries = record[dataset.jsonKey];
  if (!Array.isArray(rawEntries)) {
    return [];
  }
  return rawEntries.filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null && !Array.isArray(entry));
}

function ensureSupportedSource(database: SqliteDatabase, librarySlug: string, sourceId: string): boolean {
  const row = database
    .prepare("SELECT source_id FROM systems_sources WHERE library_slug = ? AND source_id = ?")
    .get(librarySlug, sourceId) as { source_id: string } | undefined;
  return Boolean(row);
}

function parseSummary(rawValue: string | null): Record<string, unknown> {
  if (!rawValue) {
    return {};
  }
  try {
    const parsed = JSON.parse(rawValue);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}

function serializeImportRun(row: SystemsImportRunRow): SystemsImportRun {
  return {
    id: Number(row.id),
    library_slug: String(row.library_slug),
    source_id: String(row.source_id),
    status: String(row.status),
    import_version: String(row.import_version || ""),
    source_path: String(row.source_path || ""),
    summary: parseSummary(row.summary_json),
    started_at: String(row.started_at),
    completed_at: row.completed_at === null ? null : String(row.completed_at),
    started_by_user_id: row.started_by_user_id === null ? null : Number(row.started_by_user_id),
  };
}

function loadImportRun(database: SqliteDatabase, importRunId: number): SystemsImportRun | null {
  const row = database
    .prepare(
      `
        SELECT
          id,
          library_slug,
          source_id,
          status,
          import_version,
          source_path,
          summary_json,
          started_at,
          completed_at,
          started_by_user_id
        FROM systems_import_runs
        WHERE id = ?
      `,
    )
    .get(importRunId) as SystemsImportRunRow | undefined;
  return row ? serializeImportRun(row) : null;
}

function createImportRun(
  database: SqliteDatabase,
  librarySlug: string,
  sourceId: string,
  importVersion: string,
  sourcePath: string,
  entryTypes: string[],
  actorUserId: number | null,
): SystemsImportRun {
  const now = utcIsoTimestamp();
  const result = database
    .prepare(
      `
        INSERT INTO systems_import_runs (
          library_slug,
          source_id,
          status,
          import_version,
          source_path,
          summary_json,
          started_at,
          started_by_user_id
        )
        VALUES (?, ?, 'started', ?, ?, ?, ?, ?)
      `,
    )
    .run(librarySlug, sourceId, importVersion, sourcePath, JSON.stringify({ entry_types: entryTypes }), now, actorUserId);
  const run = loadImportRun(database, Number(result.lastInsertRowid));
  if (!run) {
    throw new Error("Failed to create import run.");
  }
  return run;
}

function completeImportRun(database: SqliteDatabase, importRunId: number, summary: Record<string, unknown>): void {
  database
    .prepare(
      `
        UPDATE systems_import_runs
        SET status = 'completed',
            summary_json = ?,
            completed_at = ?
        WHERE id = ?
      `,
    )
    .run(JSON.stringify(summary), utcIsoTimestamp(), importRunId);
}

function failImportRun(database: SqliteDatabase, importRunId: number, summary: Record<string, unknown>): void {
  database
    .prepare(
      `
        UPDATE systems_import_runs
        SET status = 'failed',
            summary_json = ?,
            completed_at = ?
        WHERE id = ?
      `,
    )
    .run(JSON.stringify(summary), utcIsoTimestamp(), importRunId);
}

function replaceEntriesForSource(
  database: SqliteDatabase,
  librarySlug: string,
  sourceId: string,
  entries: PreparedEntry[],
  entryTypes: string[],
): number {
  const now = utcIsoTimestamp();
  const entryTypePlaceholders = entryTypes.map(() => "?").join(", ");
  const entryTypeClause = entryTypePlaceholders ? ` AND entry_type IN (${entryTypePlaceholders})` : "";
  const params = [librarySlug, sourceId, ...entryTypes];
  const existingKeys = (
    database
      .prepare(
        `
          SELECT entry_key
          FROM systems_entries
          WHERE library_slug = ?
            AND source_id = ?${entryTypeClause}
        `,
      )
      .all(...params) as Array<{ entry_key: string }>
  ).map((row) => String(row.entry_key));

  if (existingKeys.length > 0) {
    const keyPlaceholders = existingKeys.map(() => "?").join(", ");
    try {
      database
        .prepare(
          `
            DELETE FROM systems_entry_links
            WHERE library_slug = ?
              AND (
                from_entry_key IN (${keyPlaceholders})
                OR to_entry_key IN (${keyPlaceholders})
              )
          `,
        )
        .run(librarySlug, ...existingKeys, ...existingKeys);
    } catch (error) {
      if (!(error instanceof Error) || !error.message.includes("no such table")) {
        throw error;
      }
    }
  }

  database
    .prepare(
      `
        DELETE FROM systems_entries
        WHERE library_slug = ?
          AND source_id = ?${entryTypeClause}
      `,
    )
    .run(...params);

  if (entries.length === 0) {
    return 0;
  }

  const insertEntry = database.prepare(
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
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
  );
  for (const entry of entries) {
    insertEntry.run(
      librarySlug,
      sourceId,
      entry.entry_key,
      entry.entry_type,
      entry.slug,
      entry.title,
      entry.source_page,
      entry.source_path,
      entry.search_text,
      entry.player_safe_default ? 1 : 0,
      entry.dm_heavy ? 1 : 0,
      JSON.stringify(entry.metadata),
      JSON.stringify(entry.body),
      entry.rendered_html,
      now,
      now,
    );
  }
  return entries.length;
}

function loadEntriesForSource(
  files: Map<string, Buffer>,
  dataRootPrefix: string,
  librarySlug: string,
  sourceId: string,
  entryTypes: string[],
): { entries: PreparedEntry[]; importedByType: Record<string, number>; sourceFiles: string[] } {
  const entries: PreparedEntry[] = [];
  const importedByType: Record<string, number> = {};
  const sourceFiles: string[] = [];
  const seenSourceFiles = new Set<string>();
  const usedEntryKeys = new Set<string>();
  const usedSlugs = new Set<string>();

  for (const dataset of DATASETS) {
    if (!entryTypes.includes(dataset.entryType)) {
      continue;
    }
    const relativePath = datasetPath(dataset, sourceId);
    const payload = readJsonFile(files, dataRootPrefix, relativePath);
    if (payload === null) {
      continue;
    }
    const rawEntries = rawEntriesForDataset(payload, dataset).filter(
      (entry) => String(entry.source || "").trim().toUpperCase() === sourceId,
    );
    if (rawEntries.length === 0) {
      continue;
    }
    if (!seenSourceFiles.has(relativePath)) {
      seenSourceFiles.add(relativePath);
      sourceFiles.push(relativePath);
    }
    for (const rawEntry of rawEntries) {
      const entry = buildEntry(librarySlug, dataset.entryType, rawEntry, relativePath, usedEntryKeys, usedSlugs);
      if (!entry) {
        continue;
      }
      entries.push(entry);
      importedByType[entry.entry_type] = (importedByType[entry.entry_type] || 0) + 1;
    }
  }
  return { entries, importedByType, sourceFiles };
}

function importOneSource(
  database: SqliteDatabase,
  files: Map<string, Buffer>,
  dataRootPrefix: string,
  payload: ImportPayload,
  sourceId: string,
  actorUserId: number | null,
): Dnd5eImportResult {
  if (!sourceId) {
    throw new Error("Choose a source ID to import.");
  }
  if (!ensureSupportedSource(database, DND_5E_LIBRARY_SLUG, sourceId)) {
    throw new Error(`Unsupported DND 5E source ID: ${sourceId}`);
  }
  const entryTypes = payload.entryTypes && payload.entryTypes.length > 0
    ? payload.entryTypes
    : [...DND5E_SUPPORTED_ENTRY_TYPES];
  const importRun = createImportRun(
    database,
    DND_5E_LIBRARY_SLUG,
    sourceId,
    payload.importVersion,
    payload.sourcePathLabel,
    entryTypes,
    actorUserId,
  );
  const importedByType: Record<string, number> = {};
  const sourceFiles: string[] = [];
  try {
    let importedCount = 0;
    const runImport = database.transaction(() => {
      const loaded = loadEntriesForSource(files, dataRootPrefix, DND_5E_LIBRARY_SLUG, sourceId, entryTypes);
      Object.assign(importedByType, loaded.importedByType);
      sourceFiles.push(...loaded.sourceFiles);
      importedCount = replaceEntriesForSource(database, DND_5E_LIBRARY_SLUG, sourceId, loaded.entries, entryTypes);
      const summary = {
        entry_types: entryTypes,
        imported_by_type: importedByType,
        imported_count: importedCount,
        source_files: sourceFiles,
      };
      completeImportRun(database, importRun.id, summary);
    });
    runImport();
    return {
      source_id: sourceId,
      import_run_id: importRun.id,
      import_version: payload.importVersion,
      imported_count: importedCount,
      imported_by_type: importedByType,
      source_files: sourceFiles,
    };
  } catch (error) {
    failImportRun(database, importRun.id, {
      entry_types: entryTypes,
      imported_by_type: importedByType,
      source_files: sourceFiles,
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

export function importDnd5eSystemsArchive(
  dbPath: string,
  payload: Record<string, unknown>,
  actorUserId: number | null,
): Dnd5eImportRouteResult {
  if (!existsSync(dbPath)) {
    return { status: "validation_error", message: "DND 5E source data root not found: database" };
  }
  const normalizedPayload = normalizeImportPayload(payload);
  if ("error" in normalizedPayload) {
    return { status: "validation_error", message: normalizedPayload.error };
  }
  const files = readArchiveFiles(normalizedPayload.archive.data_blob);
  if ("error" in files) {
    return { status: "validation_error", message: files.error };
  }
  const dataRootPrefix = resolveDataRootPrefix(files);
  if (typeof dataRootPrefix !== "string") {
    return { status: "validation_error", message: dataRootPrefix.error };
  }

  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const importResults = normalizedPayload.sourceIds.map((sourceId) =>
      importOneSource(database, files, dataRootPrefix, normalizedPayload, sourceId, actorUserId),
    );
    const importRuns = importResults
      .map((result) => loadImportRun(database, result.import_run_id))
      .filter((run): run is SystemsImportRun => run !== null);
    return {
      status: "ok",
      import_results: importResults,
      import_runs: importRuns,
    };
  } catch (error) {
    return {
      status: "validation_error",
      message: error instanceof Error ? error.message : String(error),
    };
  } finally {
    database.close();
  }
}
