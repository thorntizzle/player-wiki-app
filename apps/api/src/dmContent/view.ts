import { existsSync } from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";
import { parse as parseYaml } from "yaml";

import type { CampaignViewModel } from "../campaigns/view.js";
import type { FixtureSystemsRole } from "../systems/sources.js";

type SqliteDatabase = Database.Database;

const ALLOWED_DM_CONTENT_MARKDOWN_EXTENSIONS = new Set([".markdown", ".md"]);
const FRONTMATTER_PATTERN = /^---\s*\n([\s\S]*?)\n---\s*\n?/;
const STATBLOCK_TITLE_HEADING_PATTERN = /^\s{0,3}#\s+(?<title>.*?)\s*#*\s*$/;
const STATBLOCK_NAME_LINE_PATTERN = /^\s*Name\s*:\s*(?<value>.+?)\s*$/im;
const STATBLOCK_ARMOR_CLASS_PATTERN = /^\s*\*{0,2}Armor Class\*{0,2}\s*:?\s*(?<value>\d+)\b/im;
const STATBLOCK_HIT_POINTS_PATTERN = /^\s*\*{0,2}Hit Points\*{0,2}\s*:?\s*(?<value>\d+)\b/im;
const STATBLOCK_SPEED_PATTERN = /^\s*\*{0,2}Speed\*{0,2}\s*:?\s*(?<value>.+?)\s*$/im;
const STATBLOCK_DEX_MODIFIER_PATTERN = /\bDEX\s+\d+\s+\((?<value>[+-]\d+)\)/im;
const STATBLOCK_MOVEMENT_VALUE_PATTERN = /(?<distance>\d+)/g;

interface StatblockRow {
  id: number;
  campaign_slug: string;
  title: string;
  body_markdown: string;
  source_filename: string;
  subsection: string;
  armor_class: number | null;
  max_hp: number;
  speed_text: string;
  movement_total: number;
  initiative_bonus: number;
  created_at: string;
  updated_at: string;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
}

interface ConditionRow {
  id: number;
  campaign_slug: string;
  name: string;
  description_markdown: string;
  created_at: string;
  updated_at: string;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
}

interface DMStatblockUpload {
  title: string;
  body_markdown: string;
  source_filename: string;
  subsection: string;
  armor_class: number | null;
  max_hp: number;
  speed_text: string;
  movement_total: number;
  initiative_bonus: number;
}

type DmContentMutationResult<T> =
  | { status: "ok"; payload: T }
  | { status: "validation_error"; message: string };

function utcIsoTimestamp(): string {
  return new Date().toISOString().replace("Z", "+00:00");
}

function isNoSuchTableError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("no such table");
}

function normalizeLookup(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function canManageDmContent(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function canManageSession(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function canManageSystems(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function formatInitiativeBonus(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function parseFrontmatter(rawText: string): { metadata: Record<string, unknown>; bodyMarkdown: string } {
  const normalized = rawText.replace(/\r\n/g, "\n");
  const match = FRONTMATTER_PATTERN.exec(normalized);
  if (!match) {
    return { metadata: {}, bodyMarkdown: normalized };
  }

  const parsed = parseYaml(match[1] || "") || {};
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("frontmatter_not_object");
  }
  return {
    metadata: parsed as Record<string, unknown>,
    bodyMarkdown: normalized.slice(match[0].length),
  };
}

function extractStatblockTitleHeading(markdownText: string): { title: string; bodyMarkdown: string } {
  const lines = markdownText.replace(/\r\n/g, "\n").split("\n");
  let lineIndex = 0;
  while (lineIndex < lines.length && !lines[lineIndex].trim()) {
    lineIndex += 1;
  }
  if (lineIndex >= lines.length) {
    return { title: "", bodyMarkdown: markdownText.trim() };
  }

  const match = STATBLOCK_TITLE_HEADING_PATTERN.exec(lines[lineIndex]);
  const title = String(match?.groups?.title || "").trim();
  if (!title) {
    return { title: "", bodyMarkdown: markdownText.trim() };
  }

  const bodyLines = lines.slice(lineIndex + 1);
  while (bodyLines.length > 0 && !String(bodyLines[0] || "").trim()) {
    bodyLines.shift();
  }
  return { title, bodyMarkdown: bodyLines.join("\n").trim() };
}

function fallbackTitleFromFilename(filename: string): string {
  let stem = path.parse(filename || "").name.trim();
  if (stem.toLowerCase().endsWith(" statblock")) {
    stem = stem.slice(0, -10).trim();
  }
  return stem;
}

function isGenericStatblockHeading(value: string): boolean {
  return normalizeLookup(value).includes("statblock");
}

function parseOptionalInt(value: unknown): number | null {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return null;
  }
  const match = /-?\d+/.exec(normalized);
  return match ? Number(match[0]) : null;
}

function searchInt(pattern: RegExp, value: string): number | null {
  const match = pattern.exec(value || "");
  return match?.groups?.value ? Number(match.groups.value) : null;
}

function parseMovementTotal(value: string): number {
  const distances = [...String(value || "").matchAll(STATBLOCK_MOVEMENT_VALUE_PATTERN)]
    .map((match) => Number(match.groups?.distance || 0))
    .filter((distance) => Number.isFinite(distance));
  return distances.length > 0 ? Math.max(...distances) : 0;
}

function extractStatblockDexterityModifier(markdownText: string, fallback = 0): number {
  const match = STATBLOCK_DEX_MODIFIER_PATTERN.exec(markdownText || "");
  if (!match?.groups?.value) {
    return fallback;
  }
  const parsed = Number(match.groups.value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeStatblockSubsection(value: unknown): string {
  const normalized = String(value || "").trim();
  if (normalized.length > 80) {
    throw new Error("Statblock subsection labels must stay under 80 characters.");
  }
  return normalized;
}

function buildParserFeedback(row: StatblockRow) {
  const armorClassLabel = row.armor_class !== null ? `AC ${row.armor_class}` : "AC not parsed";
  const movementLabel = row.movement_total > 0 ? `${row.movement_total} ft. movement` : "movement not parsed";
  return {
    armor_class: row.armor_class,
    max_hp: Number(row.max_hp),
    speed_text: String(row.speed_text || ""),
    movement_total: Number(row.movement_total || 0),
    initiative_bonus: Number(row.initiative_bonus || 0),
    summary:
      `Parsed combat fields: ${armorClassLabel}, HP ${Number(row.max_hp)}, ` +
      `Speed ${String(row.speed_text || "")} (${movementLabel}), Init ${formatInitiativeBonus(Number(row.initiative_bonus || 0))}.`,
  };
}

function serializeStatblock(row: StatblockRow) {
  return {
    id: Number(row.id),
    campaign_slug: String(row.campaign_slug),
    title: String(row.title || ""),
    body_markdown: String(row.body_markdown || ""),
    source_filename: String(row.source_filename || ""),
    subsection: String(row.subsection || ""),
    armor_class: row.armor_class === null ? null : Number(row.armor_class),
    max_hp: Number(row.max_hp || 0),
    speed_text: String(row.speed_text || ""),
    movement_total: Number(row.movement_total || 0),
    initiative_bonus: Number(row.initiative_bonus || 0),
    parser_feedback: buildParserFeedback(row),
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || ""),
    created_by_user_id: row.created_by_user_id === null ? null : Number(row.created_by_user_id),
    updated_by_user_id: row.updated_by_user_id === null ? null : Number(row.updated_by_user_id),
  };
}

function serializeCondition(row: ConditionRow) {
  return {
    id: Number(row.id),
    campaign_slug: String(row.campaign_slug),
    name: String(row.name || ""),
    description_markdown: String(row.description_markdown || ""),
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || ""),
    created_by_user_id: row.created_by_user_id === null ? null : Number(row.created_by_user_id),
    updated_by_user_id: row.updated_by_user_id === null ? null : Number(row.updated_by_user_id),
  };
}

function parseStatblockMarkdownUpload(options: {
  filename: string;
  markdownText: string;
  subsectionHint?: string;
  fallbackTitleHint?: string;
}): DMStatblockUpload {
  const normalizedFilename = path.basename(String(options.filename || "")).trim();
  if (!normalizedFilename) {
    throw new Error("Choose a markdown statblock file before uploading.");
  }

  const extension = path.extname(normalizedFilename).toLowerCase();
  if (!ALLOWED_DM_CONTENT_MARKDOWN_EXTENSIONS.has(extension)) {
    throw new Error("DM Content statblock uploads must use .md or .markdown files.");
  }

  const rawText = String(options.markdownText || "");
  if (!rawText) {
    throw new Error("Uploaded statblock files cannot be empty.");
  }

  let metadata: Record<string, unknown>;
  let bodyMarkdown: string;
  try {
    const parsed = parseFrontmatter(rawText);
    metadata = parsed.metadata;
    bodyMarkdown = parsed.bodyMarkdown;
  } catch (error) {
    if (error instanceof Error && error.message === "frontmatter_not_object") {
      throw new Error("Uploaded statblock frontmatter must be a YAML object.");
    }
    throw new Error("Uploaded statblock frontmatter must be valid YAML.");
  }

  let normalizedBody = bodyMarkdown.trim();
  const metadataTitle = String(metadata.title || metadata.name || "").trim();
  let heading = extractStatblockTitleHeading(normalizedBody);
  let headingTitle = heading.title;
  if (headingTitle && isGenericStatblockHeading(headingTitle)) {
    headingTitle = "";
  } else if (headingTitle) {
    normalizedBody = heading.bodyMarkdown;
  }

  const nameLineMatch = STATBLOCK_NAME_LINE_PATTERN.exec(normalizedBody);
  const nameLineTitle = String(nameLineMatch?.groups?.value || "").trim();
  const fallbackTitle = String(options.fallbackTitleHint || "").trim() || fallbackTitleFromFilename(normalizedFilename);
  const normalizedTitle = metadataTitle || headingTitle || nameLineTitle || fallbackTitle;
  if (!normalizedTitle) {
    throw new Error("The uploaded statblock needs a name or title.");
  }

  const normalizedSubsection = normalizeStatblockSubsection(
    options.subsectionHint || metadata.subsection || metadata.group || metadata.section,
  );

  let armorClass = parseOptionalInt(metadata.armor_class || metadata.ac);
  if (armorClass === null) {
    armorClass = searchInt(STATBLOCK_ARMOR_CLASS_PATTERN, normalizedBody);
  }

  let maxHp = parseOptionalInt(metadata.max_hp || metadata.hp);
  if (maxHp === null) {
    maxHp = searchInt(STATBLOCK_HIT_POINTS_PATTERN, normalizedBody);
  }
  if (maxHp === null) {
    throw new Error("The uploaded statblock needs a Hit Points value.");
  }

  let speedText = String(metadata.speed || "").trim();
  if (!speedText) {
    const speedMatch = STATBLOCK_SPEED_PATTERN.exec(normalizedBody);
    speedText = String(speedMatch?.groups?.value || "").trim();
  }
  if (!speedText) {
    throw new Error("The uploaded statblock needs a Speed value.");
  }

  const movementTotal = parseMovementTotal(speedText);
  if (movementTotal < 0) {
    throw new Error("The uploaded statblock has an invalid Speed value.");
  }

  let initiativeBonus = parseOptionalInt(metadata.initiative_bonus || metadata.initiative);
  if (initiativeBonus === null) {
    initiativeBonus = extractStatblockDexterityModifier(normalizedBody);
  }

  return {
    title: normalizedTitle,
    body_markdown: normalizedBody,
    source_filename: normalizedFilename,
    subsection: normalizedSubsection,
    armor_class: armorClass,
    max_hp: maxHp,
    speed_text: speedText,
    movement_total: movementTotal,
    initiative_bonus: initiativeBonus,
  };
}

function listStatblocks(database: SqliteDatabase, campaignSlug: string) {
  try {
    const rows = database
      .prepare(
        `SELECT *
         FROM campaign_dm_statblocks
         WHERE campaign_slug = ?
         ORDER BY updated_at DESC, title COLLATE NOCASE ASC, id DESC`,
      )
      .all(campaignSlug) as StatblockRow[];
    return rows.map(serializeStatblock);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return [];
    }
    throw error;
  }
}

function getStatblock(database: SqliteDatabase, campaignSlug: string, statblockId: number) {
  const row = database
    .prepare("SELECT * FROM campaign_dm_statblocks WHERE campaign_slug = ? AND id = ?")
    .get(campaignSlug, statblockId) as StatblockRow | undefined;
  return row ? serializeStatblock(row) : null;
}

function getStatblockRow(database: SqliteDatabase, campaignSlug: string, statblockId: number) {
  return database
    .prepare("SELECT * FROM campaign_dm_statblocks WHERE campaign_slug = ? AND id = ?")
    .get(campaignSlug, statblockId) as StatblockRow | undefined;
}

function listConditions(database: SqliteDatabase, campaignSlug: string) {
  try {
    const rows = database
      .prepare(
        `SELECT *
         FROM campaign_dm_condition_definitions
         WHERE campaign_slug = ?
         ORDER BY name COLLATE NOCASE ASC, id ASC`,
      )
      .all(campaignSlug) as ConditionRow[];
    return rows.map(serializeCondition);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return [];
    }
    throw error;
  }
}

function getCondition(database: SqliteDatabase, campaignSlug: string, conditionDefinitionId: number) {
  const row = database
    .prepare("SELECT * FROM campaign_dm_condition_definitions WHERE campaign_slug = ? AND id = ?")
    .get(campaignSlug, conditionDefinitionId) as ConditionRow | undefined;
  return row ? serializeCondition(row) : null;
}

function normalizeConditionPayload(
  database: SqliteDatabase,
  campaignSlug: string,
  options: {
    conditionDefinitionId?: number;
    name?: unknown;
    description_markdown?: unknown;
    existing?: ReturnType<typeof serializeCondition> | null;
  },
): { name: string; description_markdown: string } {
  const normalizedName =
    options.name === undefined ? String(options.existing?.name || "") : String(options.name || "").trim();
  if (!normalizedName) {
    throw new Error("Condition name is required.");
  }
  if (normalizedName.length > 80) {
    throw new Error("Condition names must stay under 80 characters.");
  }

  const normalizedDescription =
    options.description_markdown === undefined
      ? String(options.existing?.description_markdown || "")
      : String(options.description_markdown || "").trim();
  if (normalizedDescription.length > 4000) {
    throw new Error("Condition descriptions must stay under 4,000 characters.");
  }

  const normalizedNameLookup = normalizeLookup(normalizedName);
  const existingNames = listConditions(database, campaignSlug)
    .filter((condition) => condition.id !== options.conditionDefinitionId)
    .map((condition) => normalizeLookup(condition.name));
  if (existingNames.includes(normalizedNameLookup)) {
    throw new Error("A custom condition with that name already exists.");
  }

  return {
    name: normalizedName,
    description_markdown: normalizedDescription,
  };
}

function countStagedArticles(database: SqliteDatabase, campaignSlug: string): number {
  try {
    const row = database
      .prepare("SELECT COUNT(*) AS count FROM campaign_session_articles WHERE campaign_slug = ? AND status = 'staged'")
      .get(campaignSlug) as { count?: number } | undefined;
    return Number(row?.count || 0);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return 0;
    }
    throw error;
  }
}

function countSystemsSources(database: SqliteDatabase, campaign: CampaignViewModel): number {
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug) {
    return 0;
  }
  try {
    const row = database
      .prepare("SELECT COUNT(*) AS count FROM systems_sources WHERE library_slug = ?")
      .get(librarySlug) as { count?: number } | undefined;
    return Number(row?.count || 0);
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return 0;
    }
    throw error;
  }
}

export function createDmContentStatblock(
  dbPath: string,
  campaignSlug: string,
  payload: Record<string, unknown>,
  actorUserId: number,
): DmContentMutationResult<{ statblock: ReturnType<typeof serializeStatblock> }> {
  let upload: DMStatblockUpload;
  try {
    upload = parseStatblockMarkdownUpload({
      filename: String(payload.filename || "").trim(),
      markdownText: String(payload.markdown_text || ""),
      subsectionHint: String(payload.subsection || "").trim(),
    });
  } catch (error) {
    return {
      status: "validation_error",
      message: error instanceof Error ? error.message : "Invalid statblock payload.",
    };
  }

  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const now = utcIsoTimestamp();
    const result = database
      .prepare(
        `
          INSERT INTO campaign_dm_statblocks (
            campaign_slug,
            title,
            body_markdown,
            source_filename,
            subsection,
            armor_class,
            max_hp,
            speed_text,
            movement_total,
            initiative_bonus,
            created_at,
            updated_at,
            created_by_user_id,
            updated_by_user_id
          )
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `,
      )
      .run(
        campaignSlug,
        upload.title,
        upload.body_markdown,
        upload.source_filename,
        upload.subsection,
        upload.armor_class,
        upload.max_hp,
        upload.speed_text,
        upload.movement_total,
        upload.initiative_bonus,
        now,
        now,
        actorUserId,
        actorUserId,
      );
    const statblock = getStatblock(database, campaignSlug, Number(result.lastInsertRowid));
    if (!statblock) {
      throw new Error("Failed to persist DM statblock.");
    }
    return { status: "ok", payload: { statblock } };
  } finally {
    database.close();
  }
}

export function updateDmContentStatblock(
  dbPath: string,
  campaignSlug: string,
  statblockId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
): DmContentMutationResult<{ statblock: ReturnType<typeof serializeStatblock> }> {
  const hasMarkdownText = Object.hasOwn(payload, "markdown_text");
  const hasBodyMarkdown = Object.hasOwn(payload, "body_markdown");
  const hasSubsection = Object.hasOwn(payload, "subsection");
  if (!hasMarkdownText && !hasBodyMarkdown && !hasSubsection) {
    return {
      status: "validation_error",
      message: "Provide markdown_text, body_markdown, or subsection to update a statblock.",
    };
  }

  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const existing = getStatblockRow(database, campaignSlug, statblockId);
    if (!existing) {
      return { status: "validation_error", message: "That statblock could not be found." };
    }

    const existingExtension = path.extname(String(existing.source_filename || "")).toLowerCase();
    const sourceFilename = ALLOWED_DM_CONTENT_MARKDOWN_EXTENSIONS.has(existingExtension)
      ? String(existing.source_filename || "")
      : `${String(existing.title || "statblock")}.md`;
    const sourceBody = hasMarkdownText
      ? payload.markdown_text
      : hasBodyMarkdown
        ? payload.body_markdown
        : existing.body_markdown;
    const subsectionHint = hasSubsection ? payload.subsection : existing.subsection;

    let upload: DMStatblockUpload;
    try {
      upload = parseStatblockMarkdownUpload({
        filename: sourceFilename,
        markdownText: String(sourceBody || ""),
        subsectionHint: String(subsectionHint || "").trim(),
        fallbackTitleHint: existing.title,
      });
    } catch (error) {
      return {
        status: "validation_error",
        message: error instanceof Error ? error.message : "Invalid statblock payload.",
      };
    }

    const now = utcIsoTimestamp();
    const result = database
      .prepare(
        `
          UPDATE campaign_dm_statblocks
          SET title = ?,
              body_markdown = ?,
              subsection = ?,
              armor_class = ?,
              max_hp = ?,
              speed_text = ?,
              movement_total = ?,
              initiative_bonus = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ? AND id = ?
        `,
      )
      .run(
        upload.title,
        upload.body_markdown,
        upload.subsection,
        upload.armor_class,
        upload.max_hp,
        upload.speed_text,
        upload.movement_total,
        upload.initiative_bonus,
        now,
        actorUserId,
        campaignSlug,
        statblockId,
      );
    if (result.changes === 0) {
      return { status: "validation_error", message: "That statblock could not be found." };
    }
    const statblock = getStatblock(database, campaignSlug, statblockId);
    if (!statblock) {
      throw new Error("Failed to reload updated DM statblock.");
    }
    return { status: "ok", payload: { statblock } };
  } finally {
    database.close();
  }
}

export function deleteDmContentStatblock(
  dbPath: string,
  campaignSlug: string,
  statblockId: number,
): DmContentMutationResult<{ statblock: ReturnType<typeof serializeStatblock> }> {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const statblock = getStatblock(database, campaignSlug, statblockId);
    if (!statblock) {
      return { status: "validation_error", message: "That statblock could not be found." };
    }
    database
      .prepare("DELETE FROM campaign_dm_statblocks WHERE campaign_slug = ? AND id = ?")
      .run(campaignSlug, statblockId);
    return { status: "ok", payload: { statblock } };
  } finally {
    database.close();
  }
}

export function createDmContentCondition(
  dbPath: string,
  campaignSlug: string,
  payload: Record<string, unknown>,
  actorUserId: number,
): DmContentMutationResult<{ condition: ReturnType<typeof serializeCondition> }> {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    let conditionPayload: { name: string; description_markdown: string };
    try {
      conditionPayload = normalizeConditionPayload(database, campaignSlug, {
        name: payload.name,
        description_markdown: payload.description_markdown,
      });
    } catch (error) {
      return {
        status: "validation_error",
        message: error instanceof Error ? error.message : "Invalid condition payload.",
      };
    }

    const now = utcIsoTimestamp();
    const result = database
      .prepare(
        `
          INSERT INTO campaign_dm_condition_definitions (
            campaign_slug,
            name,
            description_markdown,
            created_at,
            updated_at,
            created_by_user_id,
            updated_by_user_id
          )
          VALUES (?, ?, ?, ?, ?, ?, ?)
        `,
      )
      .run(
        campaignSlug,
        conditionPayload.name,
        conditionPayload.description_markdown,
        now,
        now,
        actorUserId,
        actorUserId,
      );
    const condition = getCondition(database, campaignSlug, Number(result.lastInsertRowid));
    if (!condition) {
      throw new Error("Failed to persist DM condition definition.");
    }
    return { status: "ok", payload: { condition } };
  } finally {
    database.close();
  }
}

export function updateDmContentCondition(
  dbPath: string,
  campaignSlug: string,
  conditionDefinitionId: number,
  payload: Record<string, unknown>,
  actorUserId: number,
): DmContentMutationResult<{ condition: ReturnType<typeof serializeCondition> }> {
  const hasName = Object.hasOwn(payload, "name");
  const hasDescription = Object.hasOwn(payload, "description_markdown");
  if (!hasName && !hasDescription) {
    return {
      status: "validation_error",
      message: "Provide name or description_markdown to update a custom condition.",
    };
  }

  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const existing = getCondition(database, campaignSlug, conditionDefinitionId);
    if (!existing) {
      return { status: "validation_error", message: "That custom condition could not be found." };
    }

    let conditionPayload: { name: string; description_markdown: string };
    try {
      conditionPayload = normalizeConditionPayload(database, campaignSlug, {
        conditionDefinitionId,
        name: hasName ? payload.name : undefined,
        description_markdown: hasDescription ? payload.description_markdown : undefined,
        existing,
      });
    } catch (error) {
      return {
        status: "validation_error",
        message: error instanceof Error ? error.message : "Invalid condition payload.",
      };
    }

    const now = utcIsoTimestamp();
    const result = database
      .prepare(
        `
          UPDATE campaign_dm_condition_definitions
          SET name = ?,
              description_markdown = ?,
              updated_at = ?,
              updated_by_user_id = ?
          WHERE campaign_slug = ? AND id = ?
        `,
      )
      .run(
        conditionPayload.name,
        conditionPayload.description_markdown,
        now,
        actorUserId,
        campaignSlug,
        conditionDefinitionId,
      );
    if (result.changes === 0) {
      return { status: "validation_error", message: "That custom condition could not be found." };
    }
    const condition = getCondition(database, campaignSlug, conditionDefinitionId);
    if (!condition) {
      throw new Error("Failed to reload updated DM condition definition.");
    }
    return { status: "ok", payload: { condition } };
  } finally {
    database.close();
  }
}

export function deleteDmContentCondition(
  dbPath: string,
  campaignSlug: string,
  conditionDefinitionId: number,
): DmContentMutationResult<{ condition: ReturnType<typeof serializeCondition> }> {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const condition = getCondition(database, campaignSlug, conditionDefinitionId);
    if (!condition) {
      return { status: "validation_error", message: "That custom condition could not be found." };
    }
    database
      .prepare("DELETE FROM campaign_dm_condition_definitions WHERE campaign_slug = ? AND id = ?")
      .run(campaignSlug, conditionDefinitionId);
    return { status: "ok", payload: { condition } };
  } finally {
    database.close();
  }
}

export function buildDmContentPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  role: FixtureSystemsRole,
  playerWikiPageCount: number,
) {
  let statblocks: ReturnType<typeof serializeStatblock>[] = [];
  let conditions: ReturnType<typeof serializeCondition>[] = [];
  let stagedArticleCount = 0;
  let systemsLaneCount = 0;

  if (existsSync(dbPath)) {
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
      statblocks = listStatblocks(database, campaign.slug);
      conditions = listConditions(database, campaign.slug);
      stagedArticleCount = canManageSession(role) ? countStagedArticles(database, campaign.slug) : 0;
      systemsLaneCount = canManageSystems(role) ? countSystemsSources(database, campaign) : 0;
    } finally {
      database.close();
    }
  }

  return {
    ok: true,
    campaign,
    permissions: {
      can_manage_dm_content: canManageDmContent(role),
    },
    statblocks,
    conditions,
    subpage_counts: {
      statblocks: statblocks.length,
      conditions: conditions.length,
      player_wiki: canManageDmContent(role) ? playerWikiPageCount : 0,
      staged_articles: stagedArticleCount,
      systems: systemsLaneCount,
    },
  };
}
