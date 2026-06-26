import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";
import type { FixtureSystemsRole } from "../systems/sources.js";

type SqliteDatabase = Database.Database;

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

function isNoSuchTableError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("no such table");
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
