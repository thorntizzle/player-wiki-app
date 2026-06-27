import { promises as fs } from "node:fs";
import path from "node:path";

import { parse, stringify } from "yaml";

import type { ApiConfig } from "../config.js";
import { getCampaignBySlug } from "../campaigns/repository.js";
import { deleteCharacterPersistence, persistCharacterStateForDefinition } from "./characterState.js";
import type {
  CampaignAssetFileRecord,
  CampaignCharacterFileRecord,
  CampaignConfigRecord,
  CampaignPageFileRecord,
  CharacterPortraitPayload,
  ContentPage,
  ContentPageRemovalSafety,
  DeletedCharacterContent,
} from "./types.js";

const FRONTMATTER_PATTERN = /^---\s*\n([\s\S]*?)\n---\s*\n?/;
const SECTION_ORDER: Record<string, number> = {
  Sessions: 10,
  Notes: 15,
  Locations: 20,
  NPCs: 30,
  Races: 35,
  Factions: 40,
  Gods: 45,
  Discoveries: 50,
  Bestiary: 55,
  Items: 60,
  Spells: 70,
  Mechanics: 80,
  Lore: 90,
};

const SUBSECTION_ORDER: Record<string, Record<string, number>> = {
  Factions: {
    "Major Powers": 0,
    "Campaign Institutions": 10,
    "Major Guilds": 20,
    "Minor Guilds": 30,
  },
  Gods: {
    "Primeval Gods": 0,
    "Modern Gods": 10,
    "Fallen Gods": 20,
  },
  Locations: {
    "Districts and City Areas": 0,
    "Civic and Institutional Sites": 10,
    "Venues and Residences": 20,
    "Infrastructure and Underworks": 30,
  },
  NPCs: {
    "Civic Leadership and Justice": 0,
    "Local Allies and Service Contacts": 10,
    "Public Hosts and Arena Figures": 20,
    "Market Weave Case and Hidden Networks": 30,
    "Foreign Powers and Envoys": 40,
    "Dranian and Temporal Figures": 50,
    "Sky Dwarf Airship Crew": 60,
  },
  Mechanics: {
    "Variant and House Rules": 0,
    "Class Modifications": 10,
    Weapons: 20,
    Facilities: 30,
    "Downtime Rules": 40,
  },
};

const DEPRECATED_SECTIONS = new Set(["overview"]);
const DEPRECATED_PAGE_TYPES = new Set(["overview"]);
const DEFAULT_DISPLAY_ORDER = 10_000;
const DND_5E_SYSTEM_CODE = "DND-5E";
const XIANXIA_SYSTEM_CODE = "Xianxia";
const CAMPAIGN_CONFIG_EDITABLE_KEYS = new Set([
  "current_session",
  "source_wiki_root",
  "summary",
  "system",
  "systems_library",
  "title",
]);

interface CampaignContentContext {
  currentSession: number;
  contentDir: string;
  assetsDir: string;
  charactersDir: string;
  system: string;
}

interface CampaignContentContextOptions {
  requireContentDir?: boolean;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asStringOrDefault(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value.trim() : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
  }
  return fallback;
}

function asBoolean(value: unknown, fallback = true): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(normalized)) {
      return true;
    }
    if (["false", "0", "no", "off"].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function asStringArray(value: unknown): string[] {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map(asString).filter((item) => item.length > 0);
  }
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }
  return [];
}

function parseYamlRecord(rawText: string): Record<string, unknown> {
  try {
    return asRecord(parse(rawText) || {});
  } catch {
    return {};
  }
}

function dumpYamlRecord(payload: Record<string, unknown>): string {
  return `${stringify(payload, { sortMapEntries: false }).trimEnd()}\n`;
}

function toIsoTimestamp(value: Date): string {
  const normalized = new Date(value);
  normalized.setMilliseconds(0);
  return normalized.toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

function normalizeCampaignSlugFromConfig(value: unknown): string {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : "";
}

function parseFrontmatter(rawText: string): { metadata: Record<string, unknown>; body: string } {
  const normalized = rawText.replace(/\r\n/g, "\n");
  const match = normalized.match(FRONTMATTER_PATTERN);
  if (!match) {
    return { metadata: {}, body: normalized };
  }

  try {
    const metadata = parse(match[1] || "");
    if (typeof metadata === "object" && metadata !== null && !Array.isArray(metadata)) {
      return { metadata: metadata as Record<string, unknown>, body: normalized.slice(match[0].length) };
    }
  } catch {
    // fall through and treat it as markdown with no metadata
  }
  return { metadata: {}, body: normalized.slice(match[0].length) };
}

function slugify(value: string): string {
  const cleaned = value
    .replace(/\\/g, "/")
    .replace(/[^a-zA-Z0-9\s/_-]/g, "")
    .trim()
    .toLowerCase();
  return cleaned
    .split("/")
    .map((segment) => segment.trim().replace(/\s+/g, "-").replace(/-+/g, "-"))
    .filter(Boolean)
    .join("/");
}

function sectionSortKey(section: string): [number, string] {
  return [SECTION_ORDER[section] ?? 1000, section.toLowerCase()];
}

function subsectionSortKey(section: string, subsection: string): [number, string] {
  const sectionSubsections = SUBSECTION_ORDER[section] || {};
  return [sectionSubsections[subsection] ?? 1000, subsection.toLowerCase()];
}

function pageSortKey(page: ContentPage): [number, string, number, string, number, number, string] {
  const [sectionRank, sectionName] = sectionSortKey(page.section);
  const [subsectionRank, subsectionName] = subsectionSortKey(page.section, page.subsection);
  const sessionOrder =
    page.section === "Sessions" && page.page_type === "session" && page.reveal_after_session > 0
      ? page.reveal_after_session
      : DEFAULT_DISPLAY_ORDER;
  return [
    sectionRank,
    sectionName,
    subsectionRank,
    subsectionName,
    page.display_order,
    sessionOrder,
    page.title.toLowerCase(),
  ];
}

function isDeprecatedIdentity(section: string, pageType: string): boolean {
  return DEPRECATED_SECTIONS.has(section.trim().toLowerCase()) || DEPRECATED_PAGE_TYPES.has(pageType.trim().toLowerCase());
}

function isPageVisible(currentSession: number, page: ContentPage): boolean {
  return page.published && !isDeprecatedIdentity(page.section, page.page_type) && page.reveal_after_session <= currentSession;
}

function titleFromSlug(value: string): string {
  const tail = value.split("/").at(-1) ?? value;
  const words = tail.replace(/-/g, " ").trim();
  return words
    ? words
        .split(/\s+/)
        .filter(Boolean)
        .map((word) => word[0]!.toUpperCase() + word.slice(1))
        .join(" ")
    : value;
}

function normalizeDefaultSection(relativeSlug: string): string {
  const head = relativeSlug.split("/")[0] || "";
  if (!head) {
    return "Pages";
  }
  return head.replace(/-/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function isSafeContentRef(value: string): boolean {
  const normalized = value.replace(/\\/g, "/");
  if (!normalized || normalized.startsWith("/") || normalized.endsWith("/")) {
    return false;
  }
  if (!normalized || normalized.includes("..")) {
    return false;
  }
  const segments = normalized.split("/");
  return segments.every((segment) => segment.length > 0 && segment !== "." && segment !== "..");
}

function normalizeContentRef(value: string): string | null {
  if (!value) {
    return null;
  }
  let normalized = value.replace(/\\/g, "/");
  if (normalized.endsWith(".md")) {
    normalized = normalized.slice(0, -3);
  }
  if (!isSafeContentRef(normalized)) {
    return null;
  }
  return normalized;
}

function normalizeAssetRef(value: string): string | null {
  const normalized = value.trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!normalized) {
    return null;
  }
  const segments = normalized.split("/");
  if (segments.some((segment) => segment.length === 0 || segment === "." || segment === "..")) {
    return null;
  }
  return segments.join("/");
}

function normalizeCharacterSlug(value: string): string | null {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(normalized)) {
    return null;
  }
  return normalized;
}

function normalizeContentCharacterWriteSlug(
  rawCharacterSlug: string,
): { status: "ok"; character_slug: string } | { status: "validation_error"; message: string } {
  let decoded = rawCharacterSlug;
  try {
    decoded = decodeURIComponent(rawCharacterSlug);
  } catch {
    // keep the raw value so normal safety checks can produce the validation message.
  }

  const normalized = normalizeCharacterSlug(decoded);
  if (!normalized) {
    return {
      status: "validation_error",
      message: "Character slug must contain only letters, numbers, underscores, or hyphens.",
    };
  }
  return { status: "ok", character_slug: normalized };
}

function resolveSafeAssetPath(assetsDir: string, assetRef: string): string | null {
  const safeAssetRef = normalizeAssetRef(assetRef);
  if (!safeAssetRef) {
    return null;
  }

  const assetsRoot = path.resolve(assetsDir);
  const resolvedPath = path.resolve(assetsRoot, ...safeAssetRef.split("/"));
  if (resolvedPath !== assetsRoot && !resolvedPath.startsWith(`${assetsRoot}${path.sep}`)) {
    return null;
  }
  return resolvedPath;
}

function invalidAssetRefMessage(rawAssetRef: string): string {
  const normalized = rawAssetRef.trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  return normalized ? "Relative file references must stay within the campaign directory." : "A relative file reference is required.";
}

function normalizeContentWriteRef(rawPageRef: string): { status: "ok"; page_ref: string } | { status: "validation_error"; message: string } {
  let decoded = rawPageRef;
  try {
    decoded = decodeURIComponent(rawPageRef);
  } catch {
    // keep the raw value so normal safety checks can produce the validation message.
  }

  const normalized = decoded.trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!normalized) {
    return { status: "validation_error", message: "A relative file reference is required." };
  }

  const extension = path.posix.extname(normalized);
  if (extension && extension.toLowerCase() !== ".md") {
    return { status: "validation_error", message: "Only .md files are supported." };
  }

  const withoutExtension = normalized.toLowerCase().endsWith(".md")
    ? normalized.slice(0, -3)
    : normalized;
  if (!isSafeContentRef(withoutExtension)) {
    return { status: "validation_error", message: "Relative file references must stay within the campaign directory." };
  }
  return { status: "ok", page_ref: withoutExtension };
}

function renderMarkdownWithFrontmatter(metadata: Record<string, unknown>, bodyMarkdown: string): string {
  return `---\n${dumpYamlRecord(metadata)}---\n\n${bodyMarkdown.trim()}\n`;
}

function extractObsidianTargets(markdownText: string): string[] {
  const pattern = /\[\[([^\]]+)\]\]/g;
  const targets: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(markdownText)) !== null) {
    const rawTarget = asString(match[1]);
    if (!rawTarget) {
      continue;
    }
    const targetPart = rawTarget.split("|", 1)[0]?.split("#", 1)[0]?.trim() ?? "";
    if (targetPart) {
      targets.push(targetPart);
    }
  }
  return targets;
}

function normalizeLookup(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function formatUsageSample(values: string[], limit = 3): string {
  const uniqueValues: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const cleaned = value.split(/\s+/).join(" ").trim();
    const normalized = cleaned.toLowerCase();
    if (!cleaned || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    uniqueValues.push(cleaned);
  }

  if (uniqueValues.length === 0) {
    return "";
  }

  const shown = uniqueValues.slice(0, limit);
  const remaining = uniqueValues.length - shown.length;
  return remaining > 0 ? `${shown.join(", ")}, and ${remaining} more` : shown.join(", ");
}

function decodeEmbeddedAssetFile(
  payload: unknown,
): { status: "ok"; data_blob: Buffer } | { status: "validation_error"; message: string } {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { status: "validation_error", message: "asset_file must be an object." };
  }

  const record = payload as Record<string, unknown>;
  const filename = String(record.filename || "").trim();
  const dataBase64 = String(record.data_base64 || "").trim();
  if (!filename) {
    return { status: "validation_error", message: "asset_file filename is required." };
  }
  if (!dataBase64) {
    return { status: "validation_error", message: "asset_file data_base64 is required." };
  }
  if (dataBase64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(dataBase64)) {
    return { status: "validation_error", message: "asset_file data_base64 must be valid base64." };
  }

  const dataBlob = Buffer.from(dataBase64, "base64");
  if (dataBlob.toString("base64").replace(/=+$/g, "") !== dataBase64.replace(/=+$/g, "")) {
    return { status: "validation_error", message: "asset_file data_base64 must be valid base64." };
  }
  return { status: "ok", data_blob: dataBlob };
}

async function pruneEmptyParentDirs(startDir: string, stopDir: string): Promise<void> {
  const stopPath = path.resolve(stopDir);
  let currentPath = path.resolve(startDir);
  while (currentPath !== stopPath && currentPath.startsWith(`${stopPath}${path.sep}`)) {
    try {
      await fs.rmdir(currentPath);
    } catch {
      return;
    }
    currentPath = path.dirname(currentPath);
  }
}

function resolveSafeCharacterDir(charactersDir: string, characterSlug: string): string | null {
  const safeCharacterSlug = normalizeCharacterSlug(characterSlug);
  if (!safeCharacterSlug) {
    return null;
  }

  const charactersRoot = path.resolve(charactersDir);
  const resolvedPath = path.resolve(charactersRoot, safeCharacterSlug);
  if (resolvedPath !== charactersRoot && !resolvedPath.startsWith(`${charactersRoot}${path.sep}`)) {
    return null;
  }
  return resolvedPath;
}

const ASSET_MEDIA_TYPE_BY_EXTENSION: Record<string, string> = {
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".json": "application/json",
  ".md": "text/markdown",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain",
  ".webp": "image/webp",
};

const CHARACTER_PORTRAIT_MEDIA_TYPE_BY_EXTENSION: Record<string, string> = {
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
};

const MAX_CHARACTER_PORTRAIT_BYTES = 8 * 1024 * 1024;

function guessAssetMediaType(filePath: string): string {
  return ASSET_MEDIA_TYPE_BY_EXTENSION[path.extname(filePath).toLowerCase()] || "application/octet-stream";
}

function normalizeSystemCode(value: unknown): string {
  const rawValue = asString(value);
  const normalizedKey = rawValue.toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (normalizedKey === "dnd5e") {
    return DND_5E_SYSTEM_CODE;
  }
  if (normalizedKey === "xianxia") {
    return XIANXIA_SYSTEM_CODE;
  }
  return rawValue;
}

function defaultSystemsLibrarySlug(value: unknown): string {
  return normalizeSystemCode(value);
}

function stringFromPythonTruthy(value: unknown): string {
  if (value === null || value === undefined || value === false || value === 0 || value === "") {
    return "";
  }
  return String(value).trim();
}

function normalizeCurrentSession(value: unknown): { status: "ok"; value: number } | { status: "error"; message: string } {
  let normalizedValue: number;
  if (typeof value === "number" && Number.isFinite(value)) {
    normalizedValue = Math.trunc(value);
  } else if (typeof value === "boolean") {
    normalizedValue = value ? 1 : 0;
  } else if (typeof value === "string" && /^[-+]?\d+$/.test(value.trim())) {
    normalizedValue = Number.parseInt(value.trim(), 10);
  } else {
    return { status: "error", message: "current_session must be an integer." };
  }

  if (normalizedValue < 0) {
    return { status: "error", message: "current_session must be zero or greater." };
  }
  return { status: "ok", value: normalizedValue };
}

function normalizeCampaignConfigUpdates(
  updates: unknown,
): { status: "ok"; updates: Record<string, unknown> } | { status: "error"; message: string } {
  if (typeof updates !== "object" || updates === null || Array.isArray(updates)) {
    return { status: "error", message: "Campaign config updates must be an object." };
  }

  const source = updates as Record<string, unknown>;
  const unsupportedKeys = Object.keys(source)
    .filter((key) => !CAMPAIGN_CONFIG_EDITABLE_KEYS.has(key))
    .sort();
  if (unsupportedKeys.length > 0) {
    return { status: "error", message: `Unsupported campaign config fields: ${unsupportedKeys.join(", ")}` };
  }

  const normalized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(source)) {
    if (key === "current_session") {
      const currentSession = normalizeCurrentSession(value);
      if (currentSession.status === "error") {
        return currentSession;
      }
      normalized[key] = currentSession.value;
      continue;
    }

    let normalizedValue = stringFromPythonTruthy(value);
    if (key === "title" && !normalizedValue) {
      return { status: "error", message: "Campaign title is required." };
    }
    if (key === "system") {
      normalizedValue = normalizeSystemCode(normalizedValue);
    } else if (key === "systems_library") {
      normalizedValue = defaultSystemsLibrarySlug(normalizedValue);
    }
    normalized[key] = normalizedValue;
  }

  return { status: "ok", updates: normalized };
}

function dedupeProficiencyValues(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  const deduped: string[] = [];
  for (const item of value) {
    const cleaned = asString(item);
    const normalized = cleaned.toLowerCase();
    if (!cleaned || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    deduped.push(cleaned);
  }
  return deduped;
}

function normalizeCharacterProficiencies(value: unknown): Record<string, string[]> {
  const source = asRecord(value);
  const toolExpertise = dedupeProficiencyValues(source.tool_expertise);
  const rawTools = Array.isArray(source.tools) ? source.tools : [];
  return {
    armor: dedupeProficiencyValues(source.armor),
    weapons: dedupeProficiencyValues(source.weapons),
    tools: dedupeProficiencyValues([...rawTools, ...toolExpertise]),
    languages: dedupeProficiencyValues(source.languages),
    tool_expertise: toolExpertise,
  };
}

function normalizePythonYamlTimestampString(value: unknown): string {
  if (value instanceof Date) {
    return toIsoTimestamp(value).replace("T", " ");
  }
  const rawValue = asString(value);
  const match = rawValue.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?Z$/);
  return match ? `${match[1]} ${match[2]}+00:00` : rawValue;
}

function normalizeCharacterDefinition(
  source: Record<string, unknown>,
  campaignSlug: string,
  characterSlug: string,
  campaignSystem: string,
): Record<string, unknown> {
  const normalizedSystem =
    normalizeSystemCode(source.system ?? source.system_code ?? campaignSystem) || DND_5E_SYSTEM_CODE;
  const payload: Record<string, unknown> = {
    campaign_slug: asString(source.campaign_slug) || campaignSlug,
    character_slug: asString(source.character_slug) || characterSlug,
    name: asString(source.name) || titleFromSlug(characterSlug),
    status: asString(source.status) || "active",
    system: normalizedSystem,
    profile: asRecord(source.profile),
    stats: asRecord(source.stats),
    skills: Array.isArray(source.skills) ? source.skills : [],
    proficiencies: normalizeCharacterProficiencies(source.proficiencies),
    attacks: Array.isArray(source.attacks) ? source.attacks : [],
    features: Array.isArray(source.features) ? source.features : [],
    spellcasting: asRecord(source.spellcasting),
    equipment_catalog: Array.isArray(source.equipment_catalog) ? source.equipment_catalog : [],
    reference_notes: asRecord(source.reference_notes),
    resource_templates: Array.isArray(source.resource_templates) ? source.resource_templates : [],
    source: asRecord(source.source),
  };

  if (normalizedSystem === XIANXIA_SYSTEM_CODE) {
    payload.xianxia = asRecord(source.xianxia);
  }
  return payload;
}

function normalizeCharacterImportMetadata(
  source: Record<string, unknown>,
  campaignSlug: string,
  characterSlug: string,
): Record<string, unknown> {
  return {
    campaign_slug: asString(source.campaign_slug) || campaignSlug,
    character_slug: asString(source.character_slug) || characterSlug,
    source_path: asString(source.source_path),
    imported_at_utc: normalizePythonYamlTimestampString(source.imported_at_utc),
    parser_version: asString(source.parser_version),
    import_status: asString(source.import_status),
    warnings: Array.isArray(source.warnings) ? source.warnings : [],
  };
}

async function loadCampaignContentContext(
  config: ApiConfig,
  campaignSlug: string,
  options: CampaignContentContextOptions = {},
): Promise<CampaignContentContext | null> {
  const safeCampaign = await getCampaignBySlug(config, campaignSlug);
  if (!safeCampaign) {
    return null;
  }

  const configPath = path.resolve(config.campaignsDir, safeCampaign.slug, "campaign.yaml");
  const campaignDir = path.dirname(configPath);
  let rawPayload: string;
  try {
    rawPayload = await fs.readFile(configPath, "utf-8");
  } catch {
    return null;
  }

  let parsed: unknown = {};
  try {
    parsed = parse(rawPayload);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }

  const source = asRecord(parsed);
  const currentSession = asNumber(source.current_session ?? safeCampaign.current_session, 0);
  const contentDir = path.resolve(
    campaignDir,
    asStringOrDefault((source as Record<string, unknown>).player_content_dir, "content"),
  );
  const assetsDir = path.resolve(
    campaignDir,
    asStringOrDefault((source as Record<string, unknown>).asset_dir, "assets"),
  );
  const charactersDir = path.resolve(
    campaignDir,
    asStringOrDefault((source as Record<string, unknown>).character_dir, "characters"),
  );
  const system =
    normalizeSystemCode((source as Record<string, unknown>).system ?? safeCampaign.system) || DND_5E_SYSTEM_CODE;

  if (options.requireContentDir ?? true) {
    try {
      const contentStats = await fs.stat(contentDir);
      if (!contentStats.isDirectory()) {
        return null;
      }
    } catch {
      return null;
    }
  }

  return { currentSession, contentDir, assetsDir, charactersDir, system };
}

async function listCampaignMarkdownFiles(contentDir: string): Promise<string[]> {
  const stack: string[] = [contentDir];
  const found: string[] = [];

  while (stack.length > 0) {
    const dir = stack.pop();
    if (!dir) {
      continue;
    }

    let entries: { isDirectory: () => boolean; isFile: () => boolean; name: string }[] = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const child = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        stack.push(child);
        continue;
      }
      if (entry.isFile() && entry.name.toLowerCase().endsWith(".md")) {
        found.push(child);
      }
    }
  }

  found.sort();
  return found;
}

async function listCampaignAssetFiles(assetsDir: string): Promise<string[]> {
  const stack: string[] = [assetsDir];
  const found: string[] = [];

  try {
    const assetsStats = await fs.stat(assetsDir);
    if (!assetsStats.isDirectory()) {
      return [];
    }
  } catch {
    return [];
  }

  while (stack.length > 0) {
    const dir = stack.pop();
    if (!dir) {
      continue;
    }

    let entries: { isDirectory: () => boolean; isFile: () => boolean; name: string }[] = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const child = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        stack.push(child);
        continue;
      }
      if (entry.isFile()) {
        found.push(child);
      }
    }
  }

  found.sort();
  return found;
}

async function listCampaignCharacterDirectories(charactersDir: string): Promise<string[]> {
  try {
    const charactersStats = await fs.stat(charactersDir);
    if (!charactersStats.isDirectory()) {
      return [];
    }
  } catch {
    return [];
  }

  let entries: { isDirectory: () => boolean; name: string }[] = [];
  try {
    entries = await fs.readdir(charactersDir, { withFileTypes: true });
  } catch {
    return [];
  }

  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(charactersDir, entry.name))
    .sort();
}

function toPageFromFile(
  campaign: CampaignContentContext,
  filePath: string,
  contentDir: string,
  rawText: string,
  stats: { mtime: Date },
): CampaignPageFileRecord {
  const normalizedText = rawText.replace(/\r\n/g, "\n");
  const { metadata, body } = parseFrontmatter(normalizedText);
  const metadataRecord = asRecord(metadata);
  const relative = path.relative(contentDir, filePath).replace(/\\/g, "/");
  const relativeWithoutExtension = relative.replace(/\.[^.]+$/, "");
  const pageRef = relativeWithoutExtension;
  const routeTitle = asString(metadataRecord.title) || titleFromSlug(relativeWithoutExtension);
  const routeSlug = slugify(asString(metadataRecord.slug) || pageRef);
  const section = asString(metadataRecord.section) || normalizeDefaultSection(relativeWithoutExtension);
  const subsection = asString(metadataRecord.subsection);
  const pageType = asString(metadataRecord.type) || "page";
  const displayOrder = asNumber(metadataRecord.display_order, DEFAULT_DISPLAY_ORDER);
  const revealAfterSession = asNumber(metadataRecord.reveal_after_session);
  const aliases = Array.isArray(metadataRecord.aliases)
    ? asStringArray(metadataRecord.aliases)
    : asString(metadataRecord.aliases)
      ? asStringArray(metadataRecord.aliases)
      : [];

  const page: ContentPage = {
    title: routeTitle,
    route_slug: routeSlug,
    section,
    subsection,
    page_type: pageType,
    display_order: displayOrder,
    published: asBoolean(metadataRecord.published, true),
    aliases,
    summary: asString(metadataRecord.summary),
    image_path: asString(metadataRecord.image),
    image_alt: asString(metadataRecord.image_alt),
    image_caption: asString(metadataRecord.image_caption),
    reveal_after_session: revealAfterSession,
    source_ref: asString(metadataRecord.source_ref),
    is_pinned: displayOrder < DEFAULT_DISPLAY_ORDER,
    is_visible: isPageVisible(campaign.currentSession, {
      title: routeTitle,
      route_slug: routeSlug,
      section,
      subsection,
      page_type: pageType,
      display_order: displayOrder,
      published: asBoolean(metadataRecord.published, true),
      aliases,
      summary: asString(metadataRecord.summary),
      image_path: asString(metadataRecord.image),
      image_alt: asString(metadataRecord.image_alt) || routeTitle,
      image_caption: asString(metadataRecord.image_caption),
      reveal_after_session: revealAfterSession,
      source_ref: asString(metadataRecord.source_ref),
      is_pinned: displayOrder < DEFAULT_DISPLAY_ORDER,
      is_visible: false,
    }),
  };

  return {
    page_ref: pageRef,
    relative_path: `${relativeWithoutExtension}.md`,
    updated_at: toIsoTimestamp(stats.mtime),
    metadata: metadataRecord,
    body_markdown: body.trim(),
    page,
  };
}

function toAssetFileRecord(
  filePath: string,
  assetsDir: string,
  stats: { mtime: Date; size: number },
): CampaignAssetFileRecord {
  const relativePath = path.relative(assetsDir, filePath).replace(/\\/g, "/");
  return {
    asset_ref: relativePath,
    relative_path: relativePath,
    file_path: filePath,
    size_bytes: stats.size,
    media_type: guessAssetMediaType(filePath),
    updated_at: toIsoTimestamp(stats.mtime),
  };
}

async function toCharacterFileRecord(
  campaign: CampaignContentContext,
  campaignSlug: string,
  characterSlug: string,
  options: { stateCreated?: boolean } = {},
): Promise<CampaignCharacterFileRecord | null> {
  const characterDir = resolveSafeCharacterDir(campaign.charactersDir, characterSlug);
  if (!characterDir) {
    return null;
  }

  const definitionPath = path.join(characterDir, "definition.yaml");
  const importPath = path.join(characterDir, "import.yaml");
  let definitionRaw: string;
  let importRaw: string;
  let definitionStats;
  let importStats;
  try {
    [definitionRaw, importRaw, definitionStats, importStats] = await Promise.all([
      fs.readFile(definitionPath, "utf-8"),
      fs.readFile(importPath, "utf-8"),
      fs.stat(definitionPath),
      fs.stat(importPath),
    ]);
  } catch {
    return null;
  }

  const updatedAt = definitionStats.mtime.getTime() >= importStats.mtime.getTime()
    ? definitionStats.mtime
    : importStats.mtime;
  return {
    character_slug: characterSlug,
    character_dir: characterDir,
    definition: normalizeCharacterDefinition(
      parseYamlRecord(definitionRaw),
      campaignSlug,
      characterSlug,
      campaign.system,
    ),
    import_metadata: normalizeCharacterImportMetadata(
      parseYamlRecord(importRaw),
      campaignSlug,
      characterSlug,
    ),
    updated_at: toIsoTimestamp(updatedAt),
    state_created: options.stateCreated ?? false,
  };
}

function comparePageSort(pageA: CampaignPageFileRecord, pageB: CampaignPageFileRecord): number {
  const leftSort = pageSortKey(pageA.page);
  const rightSort = pageSortKey(pageB.page);
  for (let index = 0; index < leftSort.length; index += 1) {
    if (leftSort[index] === rightSort[index]) {
      continue;
    }
    return leftSort[index] < rightSort[index] ? -1 : 1;
  }
  if (pageA.relative_path === pageB.relative_path) {
    return pageA.page_ref < pageB.page_ref ? -1 : pageA.page_ref > pageB.page_ref ? 1 : 0;
  }
  return pageA.relative_path.localeCompare(pageB.relative_path);
}

async function listCampaignContentPageRecords(config: ApiConfig, campaignSlug: string): Promise<CampaignPageFileRecord[]> {
  const campaign = await loadCampaignContentContext(config, campaignSlug);
  if (!campaign) {
    return [];
  }

  const filePaths = await listCampaignMarkdownFiles(campaign.contentDir);
  const records: CampaignPageFileRecord[] = [];
  for (const filePath of filePaths) {
    let rawText: string;
    let fileStats;
    try {
      [rawText, fileStats] = await Promise.all([fs.readFile(filePath, "utf-8"), fs.stat(filePath)]);
    } catch {
      continue;
    }
    records.push(toPageFromFile(campaign, filePath, campaign.contentDir, rawText, fileStats));
  }
  return records.sort(comparePageSort);
}

function stripDuplicateContentRefs(records: CampaignPageFileRecord[]): CampaignPageFileRecord[] {
  const seen = new Set<string>();
  const deduped: CampaignPageFileRecord[] = [];
  for (const record of records) {
    if (seen.has(record.page_ref)) {
      continue;
    }
    seen.add(record.page_ref);
    deduped.push(record);
  }
  return deduped;
}

function toCampaignConfigRecord(
  campaignSlug: string,
  config: Record<string, unknown>,
  updatedAt: string,
): CampaignConfigRecord {
  const parsedSlug = normalizeCampaignSlugFromConfig(config.slug);
  return {
    campaign_slug: parsedSlug || campaignSlug,
    updated_at: updatedAt,
    config,
  };
}

export async function getCampaignConfigFile(
  config: ApiConfig,
  campaignSlug: string,
): Promise<CampaignConfigRecord | null> {
  const safeCampaign = await getCampaignBySlug(config, campaignSlug);
  if (!safeCampaign) {
    return null;
  }

  const campaignConfigPath = path.resolve(config.campaignsDir, campaignSlug, "campaign.yaml");
  let rawPayload: string;
  let fileStats;

  try {
    [rawPayload, fileStats] = await Promise.all([
      fs.readFile(campaignConfigPath, "utf-8"),
      fs.stat(campaignConfigPath),
    ]);
  } catch {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = parse(rawPayload);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }

  const configRecord = asRecord(parsed);
  return toCampaignConfigRecord(
    safeCampaign.slug,
    configRecord,
    toIsoTimestamp(fileStats.mtime),
  );
}

export async function updateCampaignConfigFile(
  config: ApiConfig,
  campaignSlug: string,
  updates: unknown,
): Promise<
  | {
      status: "ok";
      record: CampaignConfigRecord;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const safeCampaign = await getCampaignBySlug(config, campaignSlug);
  if (!safeCampaign) {
    return { status: "not_found" };
  }

  const campaignConfigPath = path.resolve(config.campaignsDir, safeCampaign.slug, "campaign.yaml");
  let rawPayload: string;
  try {
    rawPayload = await fs.readFile(campaignConfigPath, "utf-8");
  } catch {
    return { status: "not_found" };
  }

  let parsed: unknown;
  try {
    parsed = parse(rawPayload);
  } catch {
    return { status: "validation_error", message: "Campaign config could not be parsed." };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { status: "validation_error", message: "Campaign config updates must be an object." };
  }

  const normalizedUpdates = normalizeCampaignConfigUpdates(updates);
  if (normalizedUpdates.status === "error") {
    return { status: "validation_error", message: normalizedUpdates.message };
  }

  const updatedConfig = {
    ...(parsed as Record<string, unknown>),
    ...normalizedUpdates.updates,
  };
  await fs.writeFile(campaignConfigPath, dumpYamlRecord(updatedConfig), "utf-8");
  const refreshedRecord = await getCampaignConfigFile(config, safeCampaign.slug);
  if (!refreshedRecord) {
    return { status: "not_found" };
  }
  return { status: "ok", record: refreshedRecord };
}

export async function listCampaignContentPages(
  config: ApiConfig,
  campaignSlug: string,
): Promise<CampaignPageFileRecord[] | null> {
  const campaign = await loadCampaignContentContext(config, campaignSlug);
  if (!campaign) {
    return null;
  }
  const records = await listCampaignContentPageRecords(config, campaignSlug);
  return stripDuplicateContentRefs(records);
}

export function buildCampaignContentPageRemovalSafety(
  records: CampaignPageFileRecord[],
): Record<string, ContentPageRemovalSafety> {
  const visibleRecords = records.filter((record) => record.page.is_visible);
  const aliasIndex = new Map<string, string>();
  const titlesByRef = new Map<string, string>();

  for (const record of visibleRecords) {
    titlesByRef.set(record.page_ref, record.page.title);
    for (const key of [record.page_ref, record.page.route_slug, record.page.title, ...record.page.aliases]) {
      const normalized = normalizeLookup(key);
      if (normalized && !aliasIndex.has(normalized)) {
        aliasIndex.set(normalized, record.page_ref);
      }
    }
  }

  const backlinksByRef = new Map<string, Set<string>>();
  for (const record of visibleRecords) {
    for (const rawTarget of extractObsidianTargets(record.body_markdown)) {
      const targetRef = aliasIndex.get(normalizeLookup(rawTarget));
      if (!targetRef || targetRef === record.page_ref) {
        continue;
      }
      if (!backlinksByRef.has(targetRef)) {
        backlinksByRef.set(targetRef, new Set());
      }
      backlinksByRef.get(targetRef)!.add(record.page.title);
    }
  }

  const safetyByRef: Record<string, ContentPageRemovalSafety> = {};
  for (const record of records) {
    const backlinks = [...(backlinksByRef.get(record.page_ref) || new Set<string>())].sort();
    const backlinkSample = formatUsageSample(backlinks);
    const hardDeleteBlockers = backlinkSample ? [`Backlinked from ${backlinkSample}.`] : [];
    const canHardDelete = hardDeleteBlockers.length === 0;
    safetyByRef[record.page_ref] = {
      can_hard_delete: canHardDelete,
      hard_delete_blockers: hardDeleteBlockers,
      removal_status_label: canHardDelete ? "Hard delete available" : "Hard delete blocked",
      removal_guidance: canHardDelete
        ? "Hard delete is available after confirmation."
        : "Unpublish/archive this page or clear the references before deleting its file.",
      blockers_by_type: {
        backlinks,
        character_hooks: [],
        session_provenance: [],
      },
      samples: {
        backlinks: backlinkSample,
        character_hooks: "",
        session_provenance: "",
      },
      page_title: titlesByRef.get(record.page_ref) || record.page.title || record.page_ref,
    };
  }
  return safetyByRef;
}

export async function writeCampaignContentPage(
  config: ApiConfig,
  campaignSlug: string,
  rawPageRef: string,
  payload: unknown,
): Promise<
  | {
      status: "ok";
      record: CampaignPageFileRecord;
      removalSafety: Record<string, ContentPageRemovalSafety>;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const pageRefResult = normalizeContentWriteRef(rawPageRef);
  if (pageRefResult.status === "validation_error") {
    return pageRefResult;
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { status: "validation_error", message: "Request body must be a JSON object." };
  }
  const payloadRecord = payload as Record<string, unknown>;
  const metadata = payloadRecord.metadata ?? {};
  const bodyMarkdown = payloadRecord.body_markdown ?? "";
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return { status: "validation_error", message: "Page metadata must be an object." };
  }
  if (typeof bodyMarkdown !== "string") {
    return { status: "validation_error", message: "body_markdown must be a string." };
  }

  const pageRef = pageRefResult.page_ref;
  const filePath = path.resolve(campaign.contentDir, ...`${pageRef}.md`.split("/"));
  const contentRoot = path.resolve(campaign.contentDir);
  if (filePath !== contentRoot && !filePath.startsWith(`${contentRoot}${path.sep}`)) {
    return { status: "validation_error", message: "Resolved file path escapes the campaign directory." };
  }

  const normalizedMetadata = { ...(metadata as Record<string, unknown>) };
  normalizedMetadata.slug ??= pageRef;
  const normalizedSection = asString(normalizedMetadata.section) || normalizeDefaultSection(pageRef);
  const normalizedPageType = asString(normalizedMetadata.type) || "page";
  if (pageRef === "index" || pageRef.startsWith("overview/") || isDeprecatedIdentity(normalizedSection, normalizedPageType)) {
    return { status: "validation_error", message: "Overview wiki pages are deprecated. Choose a supported section." };
  }

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, renderMarkdownWithFrontmatter(normalizedMetadata, bodyMarkdown), "utf-8");

  const fileStats = await fs.stat(filePath);
  const rawText = await fs.readFile(filePath, "utf-8");
  const record = toPageFromFile(campaign, filePath, campaign.contentDir, rawText, fileStats);
  const records = stripDuplicateContentRefs(await listCampaignContentPageRecords(config, campaignSlug));
  return {
    status: "ok",
    record,
    removalSafety: buildCampaignContentPageRemovalSafety(records),
  };
}

export async function deleteCampaignContentPage(
  config: ApiConfig,
  campaignSlug: string,
  rawPageRef: string,
): Promise<
  | {
      status: "ok";
      record: CampaignPageFileRecord;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const pageRefResult = normalizeContentWriteRef(rawPageRef);
  if (pageRefResult.status === "validation_error") {
    return pageRefResult;
  }

  const pageRef = pageRefResult.page_ref;
  const existing = await getCampaignContentPage(config, campaignSlug, pageRef);
  if (!existing) {
    return { status: "not_found" };
  }

  const filePath = path.resolve(campaign.contentDir, ...`${pageRef}.md`.split("/"));
  try {
    const fileStats = await fs.stat(filePath);
    if (!fileStats.isFile()) {
      return { status: "not_found" };
    }
  } catch {
    return { status: "not_found" };
  }

  await fs.unlink(filePath);
  await pruneEmptyParentDirs(path.dirname(filePath), campaign.contentDir);
  return { status: "ok", record: existing };
}

export async function listCampaignContentAssets(
  config: ApiConfig,
  campaignSlug: string,
): Promise<CampaignAssetFileRecord[] | null> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return null;
  }

  const filePaths = await listCampaignAssetFiles(campaign.assetsDir);
  const records: CampaignAssetFileRecord[] = [];
  for (const filePath of filePaths) {
    let fileStats;
    try {
      fileStats = await fs.stat(filePath);
    } catch {
      continue;
    }
    records.push(toAssetFileRecord(filePath, campaign.assetsDir, fileStats));
  }
  return records;
}

export async function listCampaignContentCharacters(
  config: ApiConfig,
  campaignSlug: string,
): Promise<CampaignCharacterFileRecord[] | null> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return null;
  }

  const characterDirs = await listCampaignCharacterDirectories(campaign.charactersDir);
  const records: CampaignCharacterFileRecord[] = [];
  for (const characterDir of characterDirs) {
    const record = await toCharacterFileRecord(campaign, campaignSlug, path.basename(characterDir));
    if (record) {
      records.push(record);
    }
  }
  return records;
}

export async function writeCampaignContentCharacter(
  config: ApiConfig,
  campaignSlug: string,
  rawCharacterSlug: string,
  payload: unknown,
): Promise<
  | {
      status: "ok";
      record: CampaignCharacterFileRecord;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const characterSlugResult = normalizeContentCharacterWriteSlug(rawCharacterSlug);
  if (characterSlugResult.status === "validation_error") {
    return characterSlugResult;
  }
  const characterSlug = characterSlugResult.character_slug;

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { status: "validation_error", message: "Request body must be a JSON object." };
  }
  const payloadRecord = payload as Record<string, unknown>;
  const definitionPayload = payloadRecord.definition;
  if (!definitionPayload || typeof definitionPayload !== "object" || Array.isArray(definitionPayload)) {
    return { status: "validation_error", message: "Character definition must be an object." };
  }
  const importMetadataPayload = payloadRecord.import_metadata;
  if (
    importMetadataPayload !== undefined &&
    importMetadataPayload !== null &&
    (typeof importMetadataPayload !== "object" || Array.isArray(importMetadataPayload))
  ) {
    return { status: "validation_error", message: "import_metadata must be an object when provided." };
  }

  const existingRecord = await getCampaignContentCharacter(config, campaignSlug, characterSlug);
  const defaultImportMetadata: Record<string, unknown> = existingRecord
    ? { ...existingRecord.import_metadata }
    : {
        campaign_slug: campaignSlug,
        character_slug: characterSlug,
        source_path: `api://campaigns/${campaignSlug}/characters/${characterSlug}`,
        imported_at_utc: toIsoTimestamp(new Date()),
        parser_version: "api-v1",
        import_status: "managed",
        warnings: [],
      };

  if (importMetadataPayload && typeof importMetadataPayload === "object" && !Array.isArray(importMetadataPayload)) {
    Object.assign(defaultImportMetadata, importMetadataPayload as Record<string, unknown>);
  }
  defaultImportMetadata.campaign_slug = campaignSlug;
  defaultImportMetadata.character_slug = characterSlug;
  defaultImportMetadata.imported_at_utc =
    asString(defaultImportMetadata.imported_at_utc) || toIsoTimestamp(new Date());
  defaultImportMetadata.parser_version = asString(defaultImportMetadata.parser_version) || "api-v1";
  defaultImportMetadata.import_status = asString(defaultImportMetadata.import_status) || "managed";
  if (!Array.isArray(defaultImportMetadata.warnings)) {
    defaultImportMetadata.warnings = [];
  }

  const normalizedDefinitionPayload: Record<string, unknown> = {
    ...(definitionPayload as Record<string, unknown>),
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
  };
  normalizedDefinitionPayload.status = asString(normalizedDefinitionPayload.status) || "active";
  normalizedDefinitionPayload.system =
    normalizeSystemCode(normalizedDefinitionPayload.system ?? normalizedDefinitionPayload.system_code ?? campaign.system) ||
    DND_5E_SYSTEM_CODE;
  normalizedDefinitionPayload.name = asString(normalizedDefinitionPayload.name) || titleFromSlug(characterSlug);

  const normalizedDefinition = normalizeCharacterDefinition(
    normalizedDefinitionPayload,
    campaignSlug,
    characterSlug,
    campaign.system,
  );
  const normalizedImportMetadata = normalizeCharacterImportMetadata(
    defaultImportMetadata,
    campaignSlug,
    characterSlug,
  );

  const characterDir = resolveSafeCharacterDir(campaign.charactersDir, characterSlug);
  if (!characterDir) {
    return { status: "validation_error", message: "Character slug must contain only letters, numbers, underscores, or hyphens." };
  }

  await fs.mkdir(characterDir, { recursive: true });
  await Promise.all([
    fs.writeFile(path.join(characterDir, "definition.yaml"), dumpYamlRecord(normalizedDefinition), "utf-8"),
    fs.writeFile(path.join(characterDir, "import.yaml"), dumpYamlRecord(normalizedImportMetadata), "utf-8"),
  ]);

  const statePersistence = persistCharacterStateForDefinition(config, normalizedDefinition);
  const record = await toCharacterFileRecord(campaign, campaignSlug, characterSlug, {
    stateCreated: statePersistence.stateCreated,
  });
  if (!record) {
    return { status: "validation_error", message: "Character files were not readable after writing." };
  }
  return { status: "ok", record };
}

export async function createCampaignContentCharacter(
  config: ApiConfig,
  campaignSlug: string,
  rawCharacterSlug: string,
  definitionPayload: Record<string, unknown>,
  importMetadataPayload: Record<string, unknown>,
  initialState?: Record<string, unknown>,
): Promise<
  | {
      status: "ok";
      record: CampaignCharacterFileRecord;
    }
  | {
      status: "not_found";
    }
  | {
      status: "character_exists";
      message: string;
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const characterSlugResult = normalizeContentCharacterWriteSlug(rawCharacterSlug);
  if (characterSlugResult.status === "validation_error") {
    return characterSlugResult;
  }
  const characterSlug = characterSlugResult.character_slug;
  const characterDir = resolveSafeCharacterDir(campaign.charactersDir, characterSlug);
  if (!characterDir) {
    return { status: "validation_error", message: "Character slug must contain only letters, numbers, underscores, or hyphens." };
  }

  const definitionPath = path.join(characterDir, "definition.yaml");
  const importPath = path.join(characterDir, "import.yaml");
  const [definitionExists, importExists] = await Promise.all([
    fs.access(definitionPath).then(() => true, () => false),
    fs.access(importPath).then(() => true, () => false),
  ]);
  if (definitionExists || importExists) {
    return {
      status: "character_exists",
      message: `A character with slug '${characterSlug}' already exists in this campaign.`,
    };
  }

  const normalizedDefinition = normalizeCharacterDefinition(
    {
      ...definitionPayload,
      campaign_slug: campaignSlug,
      character_slug: characterSlug,
      system: definitionPayload.system ?? campaign.system,
    },
    campaignSlug,
    characterSlug,
    campaign.system,
  );
  const normalizedImportMetadata = normalizeCharacterImportMetadata(
    {
      ...importMetadataPayload,
      campaign_slug: campaignSlug,
      character_slug: characterSlug,
    },
    campaignSlug,
    characterSlug,
  );

  await fs.mkdir(characterDir, { recursive: true });
  await Promise.all([
    fs.writeFile(definitionPath, dumpYamlRecord(normalizedDefinition), "utf-8"),
    fs.writeFile(importPath, dumpYamlRecord(normalizedImportMetadata), "utf-8"),
  ]);

  const statePersistence = persistCharacterStateForDefinition(config, normalizedDefinition, initialState);
  const record = await toCharacterFileRecord(campaign, campaignSlug, characterSlug, {
    stateCreated: statePersistence.stateCreated,
  });
  if (!record) {
    return { status: "validation_error", message: "Character files were not readable after writing." };
  }
  return { status: "ok", record };
}

export async function deleteCampaignContentCharacter(
  config: ApiConfig,
  campaignSlug: string,
  rawCharacterSlug: string,
): Promise<
  | {
      status: "ok";
      deleted: DeletedCharacterContent;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const characterSlugResult = normalizeContentCharacterWriteSlug(rawCharacterSlug);
  if (characterSlugResult.status === "validation_error") {
    return characterSlugResult;
  }
  const characterSlug = characterSlugResult.character_slug;
  const characterDir = resolveSafeCharacterDir(campaign.charactersDir, characterSlug);
  if (!characterDir) {
    return { status: "validation_error", message: "Character slug must contain only letters, numbers, underscores, or hyphens." };
  }

  let deletedFiles = false;
  for (const fileName of ["definition.yaml", "import.yaml"]) {
    try {
      await fs.unlink(path.join(characterDir, fileName));
      deletedFiles = true;
    } catch {
      // Missing files do not make the delete fail; Flask also deletes whichever side exists.
    }
  }

  try {
    const entries = await fs.readdir(characterDir);
    if (entries.length === 0) {
      await fs.rmdir(characterDir);
    }
  } catch {
    // Missing or non-empty directories are handled through the deleted flags.
  }

  const portraitAssetsDir = path.resolve(campaign.assetsDir, "characters", characterSlug);
  const assetsRoot = path.resolve(campaign.assetsDir);
  let deletedAssets = false;
  if (portraitAssetsDir.startsWith(`${assetsRoot}${path.sep}`)) {
    try {
      const stats = await fs.stat(portraitAssetsDir);
      if (stats.isDirectory()) {
        await fs.rm(portraitAssetsDir, { recursive: true, force: true });
        deletedAssets = true;
      }
    } catch {
      // No portrait asset directory to remove.
    }
  }

  const deletedPersistence = deleteCharacterPersistence(config, campaignSlug, characterSlug);

  if (!deletedFiles && !deletedAssets && !deletedPersistence.deletedState && !deletedPersistence.deletedAssignment) {
    return { status: "not_found" };
  }

  return {
    status: "ok",
    deleted: {
      character_slug: characterSlug,
      deleted_files: deletedFiles,
      deleted_state: deletedPersistence.deletedState,
      deleted_assignment: deletedPersistence.deletedAssignment,
      deleted_assets: deletedAssets,
    },
  };
}

export async function getCampaignContentPage(
  config: ApiConfig,
  campaignSlug: string,
  rawPageRef: string,
): Promise<CampaignPageFileRecord | null> {
  let pageRef = rawPageRef;
  try {
    pageRef = decodeURIComponent(rawPageRef);
  } catch {
    // keep raw value to preserve failure semantics.
  }

  const safePageRef = normalizeContentRef(pageRef);
  if (!safePageRef) {
    return null;
  }

  const records = await listCampaignContentPageRecords(config, campaignSlug);
  const found = records.find((record) => record.page_ref === safePageRef);
  return found ?? null;
}

export async function getCampaignContentAsset(
  config: ApiConfig,
  campaignSlug: string,
  rawAssetRef: string,
): Promise<CampaignAssetFileRecord | null> {
  let assetRef = rawAssetRef;
  try {
    assetRef = decodeURIComponent(rawAssetRef);
  } catch {
    // keep raw value to preserve failure semantics.
  }

  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return null;
  }

  const assetPath = resolveSafeAssetPath(campaign.assetsDir, assetRef);
  if (!assetPath) {
    return null;
  }

  let fileStats;
  try {
    fileStats = await fs.stat(assetPath);
    if (!fileStats.isFile()) {
      return null;
    }
  } catch {
    return null;
  }

  const record = toAssetFileRecord(assetPath, campaign.assetsDir, fileStats);
  record.data_base64 = (await fs.readFile(assetPath)).toString("base64");
  return record;
}

export async function writeCampaignContentAsset(
  config: ApiConfig,
  campaignSlug: string,
  rawAssetRef: string,
  payload: unknown,
): Promise<
  | {
      status: "ok";
      record: CampaignAssetFileRecord;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const assetRef = sanitizeContentAssetRef(rawAssetRef);
  if (!assetRef) {
    return { status: "validation_error", message: invalidAssetRefMessage(rawAssetRef) };
  }

  const assetFile = decodeEmbeddedAssetFile(
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as Record<string, unknown>).asset_file
      : undefined,
  );
  if (assetFile.status === "validation_error") {
    return assetFile;
  }

  const assetPath = resolveSafeAssetPath(campaign.assetsDir, assetRef);
  if (!assetPath) {
    return { status: "validation_error", message: "Resolved file path escapes the campaign directory." };
  }

  try {
    const existingStats = await fs.stat(assetPath);
    if (existingStats.isDirectory()) {
      return { status: "validation_error", message: "Asset file references must point to files, not directories." };
    }
  } catch {
    // Missing files are created below.
  }

  await fs.mkdir(path.dirname(assetPath), { recursive: true });
  await fs.writeFile(assetPath, assetFile.data_blob);
  const fileStats = await fs.stat(assetPath);
  return { status: "ok", record: toAssetFileRecord(assetPath, campaign.assetsDir, fileStats) };
}

export async function deleteCampaignContentAsset(
  config: ApiConfig,
  campaignSlug: string,
  rawAssetRef: string,
): Promise<
  | {
      status: "ok";
      record: CampaignAssetFileRecord;
    }
  | {
      status: "not_found";
    }
  | {
      status: "validation_error";
      message: string;
    }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const assetRef = sanitizeContentAssetRef(rawAssetRef);
  if (!assetRef) {
    return { status: "validation_error", message: invalidAssetRefMessage(rawAssetRef) };
  }

  const assetPath = resolveSafeAssetPath(campaign.assetsDir, assetRef);
  if (!assetPath) {
    return { status: "validation_error", message: "Resolved file path escapes the campaign directory." };
  }

  let fileStats;
  try {
    fileStats = await fs.stat(assetPath);
    if (!fileStats.isFile()) {
      return { status: "not_found" };
    }
  } catch {
    return { status: "not_found" };
  }

  const record = toAssetFileRecord(assetPath, campaign.assetsDir, fileStats);
  await fs.unlink(assetPath);
  await pruneEmptyParentDirs(path.dirname(assetPath), campaign.assetsDir);
  return { status: "ok", record };
}

function decodeCharacterPortraitFile(
  value: unknown,
): { status: "ok"; extension: string; media_type: string; data_blob: Buffer } | { status: "validation_error"; message: string } {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { status: "validation_error", message: "portrait_file must be an object." };
  }
  const record = value as Record<string, unknown>;
  const filename = asString(record.filename);
  if (!filename) {
    return { status: "validation_error", message: "Choose an image file before saving the portrait." };
  }
  const extension = path.extname(filename).toLowerCase();
  const mediaType = CHARACTER_PORTRAIT_MEDIA_TYPE_BY_EXTENSION[extension];
  if (!mediaType) {
    return { status: "validation_error", message: "Character portraits must be PNG, JPG, GIF, or WEBP files." };
  }
  const rawData = asString(record.data_base64);
  if (!rawData) {
    return { status: "validation_error", message: "portrait_file data_base64 is required." };
  }
  let dataBlob: Buffer;
  try {
    dataBlob = Buffer.from(rawData, "base64");
  } catch {
    return { status: "validation_error", message: "portrait_file data_base64 must be valid base64." };
  }
  if (dataBlob.toString("base64").replace(/=+$/, "") !== rawData.replace(/\s/g, "").replace(/=+$/, "")) {
    return { status: "validation_error", message: "portrait_file data_base64 must be valid base64." };
  }
  if (dataBlob.byteLength === 0) {
    return { status: "validation_error", message: "Uploaded portrait files cannot be empty." };
  }
  if (dataBlob.byteLength > MAX_CHARACTER_PORTRAIT_BYTES) {
    return { status: "validation_error", message: "Character portraits must stay under 8 MB." };
  }
  return { status: "ok", extension, media_type: mediaType, data_blob: dataBlob };
}

function normalizeCharacterPortraitText(
  value: unknown,
  fieldLabel: string,
  maxLength: number,
): { status: "ok"; value: string } | { status: "validation_error"; message: string } {
  const normalized = asString(value);
  if (normalized.length > maxLength) {
    return { status: "validation_error", message: `${fieldLabel} must stay under ${maxLength} characters.` };
  }
  return { status: "ok", value: normalized };
}

export function validateCampaignContentCharacterPortraitUpload(
  payload: unknown,
): { status: "ok" } | { status: "validation_error"; message: string } {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { status: "validation_error", message: "Request body must be a JSON object." };
  }
  const payloadRecord = payload as Record<string, unknown>;
  const portraitFile = decodeCharacterPortraitFile(payloadRecord.portrait_file);
  if (portraitFile.status === "validation_error") {
    return portraitFile;
  }
  const altText = normalizeCharacterPortraitText(payloadRecord.alt_text, "Portrait alt text", 200);
  if (altText.status === "validation_error") {
    return altText;
  }
  const caption = normalizeCharacterPortraitText(payloadRecord.caption, "Portrait captions", 300);
  if (caption.status === "validation_error") {
    return caption;
  }
  return { status: "ok" };
}

function characterPortraitPayload(
  campaignSlug: string,
  assetRef: string,
  mediaType: string,
  altText: string,
  caption: string,
): CharacterPortraitPayload {
  return {
    asset_ref: assetRef,
    media_type: mediaType,
    alt_text: altText,
    caption,
    url: `/campaigns/${campaignSlug}/assets/${assetRef}`,
  };
}

function characterPortraitProfile(definition: Record<string, unknown>): Record<string, unknown> {
  return asRecord(definition.profile);
}

export async function writeCampaignContentCharacterPortrait(
  config: ApiConfig,
  campaignSlug: string,
  rawCharacterSlug: string,
  payload: unknown,
  importMetadata: Record<string, unknown>,
): Promise<
  | { status: "ok"; record: CampaignCharacterFileRecord; portrait: CharacterPortraitPayload }
  | { status: "not_found" }
  | { status: "validation_error"; message: string }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const characterSlugResult = normalizeContentCharacterWriteSlug(rawCharacterSlug);
  if (characterSlugResult.status === "validation_error") {
    return characterSlugResult;
  }
  const characterSlug = characterSlugResult.character_slug;
  const existingRecord = await getCampaignContentCharacter(config, campaignSlug, characterSlug);
  if (!existingRecord) {
    return { status: "not_found" };
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { status: "validation_error", message: "Request body must be a JSON object." };
  }
  const payloadRecord = payload as Record<string, unknown>;
  const portraitFile = decodeCharacterPortraitFile(payloadRecord.portrait_file);
  if (portraitFile.status === "validation_error") {
    return portraitFile;
  }
  const altText = normalizeCharacterPortraitText(payloadRecord.alt_text, "Portrait alt text", 200);
  if (altText.status === "validation_error") {
    return altText;
  }
  const caption = normalizeCharacterPortraitText(payloadRecord.caption, "Portrait captions", 300);
  if (caption.status === "validation_error") {
    return caption;
  }

  const profile = characterPortraitProfile(existingRecord.definition);
  const existingAssetRef = asString(profile.portrait_asset_ref);
  const nextAssetRef = `characters/${characterSlug}/portrait${portraitFile.extension}`;
  const assetPath = resolveSafeAssetPath(campaign.assetsDir, nextAssetRef);
  if (!assetPath) {
    return { status: "validation_error", message: "Resolved file path escapes the campaign directory." };
  }

  const writeResult = await writeCampaignContentCharacter(config, campaignSlug, characterSlug, {
    definition: {
      ...existingRecord.definition,
      profile: {
        ...profile,
        portrait_asset_ref: nextAssetRef,
        portrait_alt: altText.value,
        portrait_caption: caption.value,
      },
    },
    import_metadata: importMetadata,
  });
  if (writeResult.status !== "ok") {
    return writeResult;
  }

  await fs.mkdir(path.dirname(assetPath), { recursive: true });
  await fs.writeFile(assetPath, portraitFile.data_blob);
  if (existingAssetRef && existingAssetRef !== nextAssetRef) {
    const existingAssetPath = resolveSafeAssetPath(campaign.assetsDir, existingAssetRef);
    if (existingAssetPath) {
      try {
        const existingStats = await fs.stat(existingAssetPath);
        if (existingStats.isFile()) {
          await fs.unlink(existingAssetPath);
          await pruneEmptyParentDirs(path.dirname(existingAssetPath), campaign.assetsDir);
        }
      } catch {
        // Replaced portrait assets may already be absent on fixture copies.
      }
    }
  }

  const updatedRecord = await getCampaignContentCharacter(config, campaignSlug, characterSlug);
  if (!updatedRecord) {
    return { status: "validation_error", message: "Character files were not readable after writing." };
  }
  return {
    status: "ok",
    record: updatedRecord,
    portrait: characterPortraitPayload(campaignSlug, nextAssetRef, portraitFile.media_type, altText.value, caption.value),
  };
}

export async function deleteCampaignContentCharacterPortrait(
  config: ApiConfig,
  campaignSlug: string,
  rawCharacterSlug: string,
  importMetadata: Record<string, unknown>,
): Promise<
  | { status: "ok"; record: CampaignCharacterFileRecord; deleted: CharacterPortraitPayload }
  | { status: "not_found" }
  | { status: "validation_error"; message: string }
> {
  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return { status: "not_found" };
  }

  const characterSlugResult = normalizeContentCharacterWriteSlug(rawCharacterSlug);
  if (characterSlugResult.status === "validation_error") {
    return characterSlugResult;
  }
  const characterSlug = characterSlugResult.character_slug;
  const existingRecord = await getCampaignContentCharacter(config, campaignSlug, characterSlug);
  if (!existingRecord) {
    return { status: "not_found" };
  }

  const profile = characterPortraitProfile(existingRecord.definition);
  const existingAssetRef = asString(profile.portrait_asset_ref);
  if (!existingAssetRef) {
    return { status: "validation_error", message: "That character does not currently have a portrait." };
  }
  const existingMediaType =
    ASSET_MEDIA_TYPE_BY_EXTENSION[path.posix.extname(existingAssetRef).toLowerCase()] || "application/octet-stream";
  const existingAltText = asString(profile.portrait_alt);
  const existingCaption = asString(profile.portrait_caption);
  const nextProfile = { ...profile };
  delete nextProfile.portrait_asset_ref;
  delete nextProfile.portrait_alt;
  delete nextProfile.portrait_caption;

  const writeResult = await writeCampaignContentCharacter(config, campaignSlug, characterSlug, {
    definition: {
      ...existingRecord.definition,
      profile: nextProfile,
    },
    import_metadata: importMetadata,
  });
  if (writeResult.status !== "ok") {
    return writeResult;
  }

  const existingAssetPath = resolveSafeAssetPath(campaign.assetsDir, existingAssetRef);
  if (existingAssetPath) {
    try {
      const existingStats = await fs.stat(existingAssetPath);
      if (existingStats.isFile()) {
        await fs.unlink(existingAssetPath);
        await pruneEmptyParentDirs(path.dirname(existingAssetPath), campaign.assetsDir);
      }
    } catch {
      // Missing file does not change the profile removal result.
    }
  }

  const updatedRecord = await getCampaignContentCharacter(config, campaignSlug, characterSlug);
  if (!updatedRecord) {
    return { status: "validation_error", message: "Character files were not readable after writing." };
  }
  return {
    status: "ok",
    record: updatedRecord,
    deleted: characterPortraitPayload(campaignSlug, existingAssetRef, existingMediaType, existingAltText, existingCaption),
  };
}

export async function getCampaignContentCharacter(
  config: ApiConfig,
  campaignSlug: string,
  rawCharacterSlug: string,
): Promise<CampaignCharacterFileRecord | null> {
  let characterSlug = rawCharacterSlug;
  try {
    characterSlug = decodeURIComponent(rawCharacterSlug);
  } catch {
    // keep raw value to preserve failure semantics.
  }

  const safeCharacterSlug = normalizeCharacterSlug(characterSlug);
  if (!safeCharacterSlug) {
    return null;
  }

  const campaign = await loadCampaignContentContext(config, campaignSlug, { requireContentDir: false });
  if (!campaign) {
    return null;
  }

  return toCharacterFileRecord(campaign, campaignSlug, safeCharacterSlug);
}

export function sanitizeContentPageRef(rawPageRef: string): string | null {
  try {
    return normalizeContentRef(decodeURIComponent(rawPageRef));
  } catch {
    return normalizeContentRef(rawPageRef);
  }
}

export function sanitizeContentAssetRef(rawAssetRef: string): string | null {
  try {
    return normalizeAssetRef(decodeURIComponent(rawAssetRef));
  } catch {
    return normalizeAssetRef(rawAssetRef);
  }
}

export function sanitizeContentCharacterSlug(rawCharacterSlug: string): string | null {
  try {
    return normalizeCharacterSlug(decodeURIComponent(rawCharacterSlug));
  } catch {
    return normalizeCharacterSlug(rawCharacterSlug);
  }
}
