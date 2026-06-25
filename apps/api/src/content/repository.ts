import { promises as fs } from "node:fs";
import path from "node:path";

import { parse } from "yaml";

import type { ApiConfig } from "../config.js";
import { getCampaignBySlug } from "../campaigns/repository.js";
import type { CampaignPageFileRecord, CampaignConfigRecord, ContentPage } from "./types.js";

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

interface CampaignContentContext {
  currentSession: number;
  contentDir: string;
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

async function loadCampaignContentContext(
  config: ApiConfig,
  campaignSlug: string,
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

  try {
    const contentStats = await fs.stat(contentDir);
    if (!contentStats.isDirectory()) {
      return null;
    }
  } catch {
    return null;
  }

  return { currentSession, contentDir };
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

export function sanitizeContentPageRef(rawPageRef: string): string | null {
  try {
    return normalizeContentRef(decodeURIComponent(rawPageRef));
  } catch {
    return normalizeContentRef(rawPageRef);
  }
}
