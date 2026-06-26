import { promises as fs } from "node:fs";
import path from "node:path";

import { parse as parseYaml } from "yaml";

import { getApiConfig, type ApiConfig } from "../config.js";
import type { WikiCampaignConfig, WikiPageRecord } from "./types.js";

const FRONTMATTER_PATTERN = /^---\s*\n([\s\S]*?)\n---\s*\n?/;
const OBSIDIAN_LINK_PATTERN = /\[\[([^\]]+)\]\]/g;

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

interface CampaignData {
  campaign: WikiCampaignConfig;
  pages: Map<string, WikiPageRecord>;
  aliasIndex: Map<string, string>;
}

const repositoryCache = new Map<string, Promise<CampaignData | null>>();

let currentConfig: ApiConfig = getApiConfig();

export function setWikiConfig(config: ApiConfig): void {
  currentConfig = config;
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
    if (Number.isFinite(parsed)) {
      return Math.trunc(parsed);
    }
  }
  return fallback;
}

function asNumberOrDefault(value: unknown, fallback = DEFAULT_DISPLAY_ORDER): number {
  return asNumber(value, fallback);
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
    if (normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on") {
      return true;
    }
    if (normalized === "false" || normalized === "0" || normalized === "no" || normalized === "off") {
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
    return value.map((entry) => asString(entry)).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean);
  }
  return [];
}

export function slugify(value: string): string {
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

export function sectionSortKey(section: string): [number, string] {
  return [SECTION_ORDER[section] ?? 1000, section.toLowerCase()];
}

export function subsectionSortKey(section: string, subsection: string): [number, string] {
  const sectionSubsections = SUBSECTION_ORDER[section] || {};
  return [sectionSubsections[subsection] ?? 1000, subsection.toLowerCase()];
}

export function pageSortKey(
  page: WikiPageRecord,
): [number, string, number, string, number, number, string] {
  const [sectionRank, normalizedSection] = sectionSortKey(page.section);
  const [subsectionRank, normalizedSubsection] = subsectionSortKey(page.section, page.subsection);
  const sessionOrder =
    page.section === "Sessions" && page.page_type === "session" && page.reveal_after_session > 0
      ? page.reveal_after_session
      : DEFAULT_DISPLAY_ORDER;
  return [
    sectionRank,
    normalizedSection,
    subsectionRank,
    normalizedSubsection,
    page.display_order,
    sessionOrder,
    page.title.toLowerCase(),
  ];
}

function parseFrontmatter(rawText: string): { metadata: Record<string, unknown>; body: string } {
  const normalized = rawText.replace(/\r\n/g, "\n");
  const match = normalized.match(FRONTMATTER_PATTERN);
  if (!match) {
    return { metadata: {}, body: normalized };
  }
  try {
    const parsed = parseYaml(match[1] || "") || {};
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return { metadata: parsed as Record<string, unknown>, body: normalized.slice(match[0].length) };
    }
  } catch {
    // ignore malformed YAML and treat as plain markdown body
  }
  return { metadata: {}, body: normalized.slice(match[0].length) };
}

function extractObsidianTargets(markdownText: string): string[] {
  const targets: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = OBSIDIAN_LINK_PATTERN.exec(markdownText)) !== null) {
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

function normalizeDefaultSection(relativeSlug: string): string {
  const head = relativeSlug.split("/")[0] || "";
  if (!head) {
    return "Pages";
  }
  return head.replace(/-/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
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

function parseCampaignConfig(configPath: string): Promise<WikiCampaignConfig | null> {
  return (async () => {
    let rawPayload: string;
    try {
      rawPayload = await fs.readFile(configPath, "utf-8");
    } catch {
      return null;
    }

    let parsed: unknown = {};
    try {
      parsed = parseYaml(rawPayload) || {};
    } catch {
      return null;
    }

    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return null;
    }

    const slug = asString((parsed as Record<string, unknown>).slug);
    if (!slug) {
      return null;
    }

    const title = asString((parsed as Record<string, unknown>).title);
    const system = asString((parsed as Record<string, unknown>).system);
    const summary = asStringOrDefault((parsed as Record<string, unknown>).summary);
    if (!title || !system) {
      return null;
    }

    const configDir = path.dirname(configPath);
    return {
      title,
      slug,
      summary,
      system,
      current_session: asNumber((parsed as Record<string, unknown>).current_session),
      systems_library_slug: asString((parsed as Record<string, unknown>).systems_library) || null,
      content_dir: path.resolve(configDir, asStringOrDefault((parsed as Record<string, unknown>).player_content_dir) || "content"),
      assets_dir: path.resolve(configDir, asStringOrDefault((parsed as Record<string, unknown>).asset_dir) || "assets"),
    };
  })();
}

function isPageVisible(campaign: WikiCampaignConfig, page: WikiPageRecord): boolean {
  return (
    page.published &&
    !DEPRECATED_SECTIONS.has(page.section.trim().toLowerCase()) &&
    !DEPRECATED_PAGE_TYPES.has(page.page_type.trim().toLowerCase()) &&
    page.reveal_after_session <= campaign.current_session
  );
}

function mapDisplayType(
  section: string,
  subsection: string,
  pageType: string,
): string {
  if (section === "Gods") {
    return (
      {
        "Primeval Gods": "primeval god",
        "Modern Gods": "modern god",
        "Fallen Gods": "fallen god",
      }[subsection] || pageType
    );
  }
  return pageType;
}

function sortPages(pages: WikiPageRecord[]): WikiPageRecord[] {
  return [...pages].sort((left, right) => {
    const leftSort = pageSortKey(left);
    const rightSort = pageSortKey(right);
    for (let index = 0; index < leftSort.length; index += 1) {
      if (leftSort[index] === rightSort[index]) {
        continue;
      }
      return leftSort[index] < rightSort[index] ? -1 : 1;
    }
    return 0;
  });
}

function buildAliasIndex(visiblePages: Iterable<WikiPageRecord>): Map<string, string> {
  const index = new Map<string, string>();
  for (const page of visiblePages) {
    const keys = [page.route_slug, page.title, ...page.aliases];
    for (const key of keys) {
      const normalized = normalizeLookup(key);
      if (!normalized || index.has(normalized)) {
        continue;
      }
      index.set(normalized, page.route_slug);
    }
  }
  return index;
}

function escapeHtml(rawText: string): string {
  return rawText
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function extractLinkLabel(rawTarget: string): string {
  const [, labelPart = "", heading = ""] = rawTarget.match(/^[^|#]+(?:\|([^#]*))?(?:#(.*))?$/) || [];
  const label = (labelPart || heading || rawTarget).trim();
  return label || rawTarget;
}

function resolveObsidianLinks(markdownText: string, campaignSlug: string, aliasIndex: Map<string, string>): string {
  return markdownText.replace(OBSIDIAN_LINK_PATTERN, (_, rawTarget) => {
    const targetPart = asString(rawTarget).split("|", 1)[0]?.split("#", 1)[0]?.trim() ?? "";
    const label = extractLinkLabel(asString(rawTarget));
    const targetSlug = aliasIndex.get(normalizeLookup(targetPart));
    if (!targetSlug) {
      return `<span class=\"broken-link\">${escapeHtml(label)}</span>`;
    }
    return `<a href=\"/app-next/campaigns/${campaignSlug}/pages/${targetSlug}\">${escapeHtml(label)}</a>`;
  });
}

function renderMarkdown(markdownText: string, campaignSlug: string, visiblePages: WikiPageRecord[]): string {
  const aliasIndex = buildAliasIndex(visiblePages);
  const normalized = escapeHtml(markdownText.trim());
  const linkedMarkdown = resolveObsidianLinks(normalized, campaignSlug, aliasIndex);
  const blocks = linkedMarkdown.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  return blocks
    .map((block) => {
      if (/^#{1,6}\s+/.test(block)) {
        const headingMatch = block.match(/^(#{1,6})\s+(.*)$/);
        if (headingMatch) {
          const depth = Math.min(headingMatch[1]!.length, 6);
          return `<h${depth}>${headingMatch[2]!.trim()}</h${depth}>`;
        }
      }
      if (/^(?:- |\* |\d+\. )/.test(block)) {
        return `<p>${block.replace(/\n/g, "<br />")}</p>`;
      }
      return `<p>${block.replace(/\n/g, "<br />")}</p>`;
    })
    .join("");
}

async function listCampaignMarkdownFiles(contentRoot: string): Promise<string[]> {
  const stack: string[] = [contentRoot];
  const found: string[] = [];

  while (stack.length > 0) {
    const dir = stack.pop();
    if (!dir) {
      continue;
    }

    let entries: { name: string; isDirectory: () => boolean; isFile: () => boolean }[];
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

async function buildCampaignData(config: WikiCampaignConfig): Promise<CampaignData> {
  const filePaths = await listCampaignMarkdownFiles(config.content_dir);
  const pages = new Map<string, WikiPageRecord>();
  const bySlug = new Map<string, string>();

  for (const filePath of filePaths) {
    const rawText = await fs.readFile(filePath, "utf-8");
    const { metadata, body } = parseFrontmatter(rawText);
    const relative = path.relative(config.content_dir, filePath).replace(/\\/g, "/");
    const defaultSlug = slugify(relative.replace(/\.[^.]+$/, ""));
    const section = parseSectionHeader(asString(metadata.section) || normalizeDefaultSection(defaultSlug));
    const routeSlug = slugify(asString(metadata.slug) || defaultSlug);

    if (bySlug.has(routeSlug)) {
      throw new Error(`Duplicate wiki page slug '${routeSlug}' in campaign '${config.slug}'.`);
    }
    bySlug.set(routeSlug, filePath);

    const page: WikiPageRecord = {
      page_ref: routeSlug,
      title: asString(metadata.title) || titleFromSlug(defaultSlug),
      route_slug: routeSlug,
      section,
      subsection: asString(metadata.subsection),
      page_type: asString(metadata.type) || "page",
      display_type: "",
      summary: asString(metadata.summary),
      display_order: asNumberOrDefault(metadata.display_order, DEFAULT_DISPLAY_ORDER),
      reveal_after_session: asNumber(metadata.reveal_after_session),
      is_pinned: false,
      image_ref: asString(metadata.image),
      image_alt: asString(metadata.image_alt) || asString(metadata.title) || titleFromSlug(defaultSlug),
      image_caption: asString(metadata.image_caption),
      body_markdown: body.trim(),
      body_html: null,
      aliases: asStringArray(metadata.aliases),
      source_path: filePath,
      raw_link_targets: extractObsidianTargets(body),
      resolved_links: [],
      backlinks: [],
      published: asBoolean(metadata.published, true),
    };
    page.display_type = mapDisplayType(page.section, page.subsection, page.page_type);
    page.is_pinned = page.display_order < DEFAULT_DISPLAY_ORDER;
    pages.set(routeSlug, page);
  }

  const visibleForIndexing = buildAliasIndex(
    Array.from(pages.values()).filter((page) => isPageVisible(config, page)),
  );

  const backlinkIndex = new Map<string, Set<string>>();
  for (const page of pages.values()) {
    if (!isPageVisible(config, page)) {
      page.resolved_links = [];
      page.backlinks = [];
      continue;
    }

    const resolved: string[] = [];
    for (const rawTarget of page.raw_link_targets) {
      const targetSlug = visibleForIndexing.get(normalizeLookup(rawTarget));
      if (!targetSlug) {
        continue;
      }
      resolved.push(targetSlug);
      if (!backlinkIndex.has(targetSlug)) {
        backlinkIndex.set(targetSlug, new Set());
      }
      backlinkIndex.get(targetSlug)!.add(page.route_slug);
    }
    page.resolved_links = resolved;
  }

  for (const [targetSlug, sourceSlugs] of backlinkIndex.entries()) {
    const targetPage = pages.get(targetSlug);
    if (!targetPage) {
      continue;
    }
    targetPage.backlinks = sortPages(
      Array.from(sourceSlugs)
        .map((slug) => pages.get(slug))
        .filter(
          (entry): entry is WikiPageRecord =>
            entry !== undefined && isPageVisible(config, entry),
        ),
    ).map((page) => page.route_slug);
  }

  return { campaign: config, pages, aliasIndex: visibleForIndexing };
}

function parseSectionHeader(section: string): string {
  return section.trim() || "Pages";
}

function asConfigCampaign(config: ApiConfig, campaignSlug: string): Promise<CampaignData | null> {
  const cacheKey = `${config.campaignsDir}::${campaignSlug}`;
  if (!repositoryCache.has(cacheKey)) {
    repositoryCache.set(
      cacheKey,
      (async () => {
        if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(campaignSlug)) {
          return null;
        }
        const configPath = path.resolve(config.campaignsDir, campaignSlug, "campaign.yaml");
        const campaignConfig = await parseCampaignConfig(configPath);
        if (!campaignConfig || campaignConfig.slug !== campaignSlug) {
          return null;
        }
        try {
          const contentStats = await fs.stat(campaignConfig.content_dir);
          if (!contentStats.isDirectory()) {
            return null;
          }
        } catch {
          return null;
        }
        return buildCampaignData(campaignConfig);
      })(),
    );
  }
  return repositoryCache.get(cacheKey)!;
}

function sessionSummarySort(left: WikiPageRecord, right: WikiPageRecord): number {
  const leftKey = [left.reveal_after_session, left.title.toLowerCase(), left.route_slug.toLowerCase()];
  const rightKey = [right.reveal_after_session, right.title.toLowerCase(), right.route_slug.toLowerCase()];
  for (let index = 0; index < leftKey.length; index += 1) {
    if (leftKey[index] === rightKey[index]) {
      continue;
    }
    return leftKey[index] < rightKey[index] ? -1 : 1;
  }
  return 0;
}

export interface WikiRepository {
  getCampaign: (campaignSlug: string) => Promise<WikiCampaignConfig | null>;
  listVisiblePages: (campaignSlug: string) => Promise<WikiPageRecord[]>;
  getPage: (campaignSlug: string, pageSlug: string) => Promise<WikiPageRecord | null>;
  getSectionPages: (campaignSlug: string, sectionSlug: string) => Promise<WikiPageRecord[]>;
  searchPages: (campaignSlug: string, query: string) => Promise<WikiPageRecord[]>;
  getPageBodyHtml: (campaignSlug: string, pageSlug: string) => Promise<string | null>;
  getLatestSessionSummaryPage: (campaignSlug: string) => Promise<WikiPageRecord | null>;
  getBacklinks: (campaignSlug: string, pageSlug: string) => Promise<WikiPageRecord[]>;
}

export const campaignWikiRepository: WikiRepository = {
  async getCampaign(campaignSlug: string) {
    const repository = await asConfigCampaign(currentConfig, campaignSlug);
    return repository?.campaign ?? null;
  },

  async listVisiblePages(campaignSlug: string) {
    const repository = await asConfigCampaign(currentConfig, campaignSlug);
    if (!repository) {
      return [];
    }
    return sortPages(Array.from(repository.pages.values()).filter((page) => isPageVisible(repository.campaign, page)));
  },

  async getPage(campaignSlug: string, pageSlug: string) {
    const repository = await asConfigCampaign(currentConfig, campaignSlug);
    if (!repository) {
      return null;
    }
    const page = repository.pages.get(slugify(pageSlug));
    if (!page || !isPageVisible(repository.campaign, page)) {
      return null;
    }
    return page;
  },

  async getSectionPages(campaignSlug: string, sectionSlug: string) {
    const visible = await campaignWikiRepository.listVisiblePages(campaignSlug);
    return sortPages(visible.filter((page) => slugify(page.section) === sectionSlug));
  },

  async searchPages(campaignSlug: string, query: string) {
    const pages = await campaignWikiRepository.listVisiblePages(campaignSlug);
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return pages;
    }
    return pages.filter((page) => {
      const haystack = [page.title, page.subsection, page.summary, page.body_markdown, ...page.aliases]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalized);
    });
  },

  async getPageBodyHtml(campaignSlug: string, pageSlug: string) {
    const page = await campaignWikiRepository.getPage(campaignSlug, pageSlug);
    if (!page) {
      return null;
    }
    if (page.body_html !== null) {
      return page.body_html;
    }
    const repository = await asConfigCampaign(currentConfig, campaignSlug);
    if (!repository) {
      return null;
    }
    const pages = await campaignWikiRepository.listVisiblePages(campaignSlug);
    page.body_html = renderMarkdown(page.body_markdown, repository.campaign.slug, pages);
    return page.body_html;
  },

  async getLatestSessionSummaryPage(campaignSlug: string) {
    const repository = await asConfigCampaign(currentConfig, campaignSlug);
    if (!repository) {
      return null;
    }
    const candidates = sortPages(
      Array.from(repository.pages.values()).filter(
        (page) =>
          isPageVisible(repository.campaign, page) &&
          page.section === "Sessions" &&
          page.page_type === "session",
      ),
    );
    if (!candidates.length) {
      return null;
    }
    return candidates.sort(sessionSummarySort).at(-1) ?? null;
  },

  async getBacklinks(campaignSlug: string, pageSlug: string) {
    const repository = await asConfigCampaign(currentConfig, campaignSlug);
    if (!repository) {
      return [];
    }
    const page = repository.pages.get(slugify(pageSlug));
    if (!page || !isPageVisible(repository.campaign, page)) {
      return [];
    }
    return page.backlinks
      .map((slug) => repository.pages.get(slug))
      .filter((entry): entry is WikiPageRecord => Boolean(entry))
      .filter((entry) => isPageVisible(repository.campaign, entry))
      .sort((left, right) => {
        const leftSort = pageSortKey(left);
        const rightSort = pageSortKey(right);
        for (let index = 0; index < leftSort.length; index += 1) {
          if (leftSort[index] === rightSort[index]) {
            continue;
          }
          return leftSort[index] < rightSort[index] ? -1 : 1;
        }
        return 0;
      });
  },
};

export function clearCampaignCache(): void {
  repositoryCache.clear();
}
