import { createHash } from "node:crypto";
import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";
import { buildCampaignSystemsEntryDetailPayload, type FixtureSystemsRole } from "../systems/sources.js";
import { campaignWikiRepository } from "../wiki/repository.js";

export const SESSION_READONLY_REVISION = 0;

type SessionSourceKind = "" | "page" | "systems";

interface SessionRow {
  id: number;
  campaign_slug: string;
  status: string;
  started_at: string;
  started_by_user_id: number | null;
  ended_at: string | null;
  ended_by_user_id: number | null;
}

interface SessionStateRow {
  campaign_slug: string;
  revision: number;
}

interface SessionArticleRow {
  id: number;
  campaign_slug: string;
  title: string;
  body_markdown: string;
  source_page_ref: string;
  status: string;
  created_at: string;
  created_by_user_id: number | null;
  revealed_at: string | null;
  revealed_by_user_id: number | null;
  revealed_in_session_id: number | null;
}

interface SessionArticleImageRow {
  article_id: number;
  filename: string;
  media_type: string;
  alt_text: string;
  caption: string;
  updated_at: string;
}

interface SessionArticleImageBlobRow extends SessionArticleImageRow {
  data_blob: Uint8Array;
  article_status: string;
  revealed_in_session_id: number | null;
}

interface SessionMessageRow {
  id: number;
  session_id: number;
  campaign_slug: string;
  message_type: string;
  body_text: string;
  recipient_scope: string;
  recipient_user_id: number | null;
  author_user_id: number | null;
  author_display_name: string;
  article_id: number | null;
  created_at: string;
}

interface SessionSummaryRow extends SessionRow {
  message_count: number;
  last_message_at: string | null;
}

export interface SessionPermissionBlock {
  can_manage_session: boolean;
  can_post_messages: boolean;
}

export interface SessionRecordPayload {
  id: number;
  campaign_slug: string;
  status: string;
  started_at: string | null;
  started_by_user_id: number | null;
  ended_at: string | null;
  ended_by_user_id: number | null;
  is_active: boolean;
}

export interface SessionArticleImagePayload {
  filename: string;
  media_type: string;
  alt_text: string;
  caption: string;
  updated_at: string | null;
  url: string;
}

export interface SessionArticlePayload {
  id: number;
  campaign_slug: string;
  title: string;
  body_markdown: string;
  body_format: "markdown" | "html";
  source_page_ref: string;
  source_kind: string;
  source_ref: string;
  status: string;
  created_at: string | null;
  created_by_user_id: number | null;
  revealed_at: string | null;
  revealed_by_user_id: number | null;
  revealed_in_session_id: number | null;
  is_revealed: boolean;
  links: {
    source_url: string;
    published_page_url: string;
    player_wiki_editor_url: string;
    convert_url: string;
  };
  source: {
    title: string;
    label: string;
    action_label: string;
    missing_message: string;
  };
  converted_page: null;
  image: SessionArticleImagePayload | null;
}

export interface SessionMessagePayload {
  id: number;
  session_id: number;
  campaign_slug: string;
  message_type: string;
  body_text: string;
  author_user_id: number | null;
  author_display_name: string;
  article_id: number | null;
  created_at: string | null;
  recipient_scope: string;
  recipient_user_id: number | null;
  recipient_label: string;
  article: SessionArticlePayload | null;
}

export interface SessionLogSummaryPayload {
  session: SessionRecordPayload;
  message_count: number;
  last_message_at: string | null;
  detail_url: string;
}

export interface SessionStatePayload {
  ok: true;
  campaign: CampaignViewModel;
  permissions: SessionPermissionBlock;
  active_session: SessionRecordPayload | null;
  messages: SessionMessagePayload[];
  session_message_recipient_player_choices: [];
  show_session_dm_passive_scores: boolean;
  session_revision: number;
  session_view_token: string;
  staged_articles?: SessionArticlePayload[];
  revealed_articles?: SessionArticlePayload[];
  session_logs?: SessionLogSummaryPayload[];
  session_dm_passive_scores?: [];
}

export interface SessionArticleImageReadResult {
  status: "ok" | "not_found";
  filename: string;
  mediaType: string;
  data: Uint8Array;
}

export interface SessionLogDetailPayload {
  ok: true;
  session: SessionRecordPayload;
  messages: SessionMessagePayload[];
}

export type SessionLogDetailResult =
  | {
      status: "ok";
      payload: SessionLogDetailPayload;
    }
  | {
      status: "not_found";
    };

function stableHexDigest(value: string): string {
  return createHash("sha1").update(value).digest("hex");
}

function canManageSession(role: FixtureSystemsRole | null): boolean {
  return role === "dm" || role === "admin";
}

function canPostMessages(role: FixtureSystemsRole | null): boolean {
  return role === "player" || role === "dm" || role === "admin";
}

function isNoSuchTableError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("no such table");
}

function isoString(value: unknown): string | null {
  const rawValue = String(value ?? "").trim();
  return rawValue || null;
}

function parseSessionArticleSourceRef(value: string): [SessionSourceKind, string] {
  const normalized = String(value || "").trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!normalized) {
    return ["", ""];
  }
  const colonIndex = normalized.indexOf(":");
  if (colonIndex >= 0) {
    const sourceKind = normalized.slice(0, colonIndex).trim().toLowerCase();
    const sourceRef = normalized.slice(colonIndex + 1).trim().replace(/^\/+|\/+$/g, "");
    if (sourceKind === "systems" && sourceRef) {
      return ["systems", sourceRef];
    }
    if (sourceKind === "page" && sourceRef) {
      return ["page", sourceRef];
    }
  }
  return ["page", normalized];
}

export function buildSessionViewToken(
  campaign: CampaignViewModel,
  sessionRevision: number,
  role: FixtureSystemsRole | null = null,
): string {
  const rawToken = [
    "fixture-read-only-session-state-v2",
    campaign.slug,
    campaign.system,
    String(campaign.current_session ?? ""),
    String(sessionRevision),
    canManageSession(role) ? "manage" : "view",
    canPostMessages(role) ? "post" : "read",
  ].join("|");
  return stableHexDigest(rawToken).slice(0, 12);
}

function emptySessionPayload(campaign: CampaignViewModel, role: FixtureSystemsRole | null = null): SessionStatePayload {
  const sessionRevision = SESSION_READONLY_REVISION;
  const manageSession = canManageSession(role);
  const payload: SessionStatePayload = {
    ok: true,
    campaign,
    permissions: {
      can_manage_session: manageSession,
      can_post_messages: canPostMessages(role),
    },
    active_session: null,
    messages: [],
    session_message_recipient_player_choices: [],
    show_session_dm_passive_scores: false,
    session_revision: sessionRevision,
    session_view_token: buildSessionViewToken(campaign, sessionRevision, role),
  };
  if (manageSession) {
    payload.staged_articles = [];
    payload.revealed_articles = [];
    payload.session_logs = [];
    payload.session_dm_passive_scores = [];
    payload.show_session_dm_passive_scores = campaign.system.trim().toLowerCase() === "dnd-5e";
  }
  return payload;
}

function serializeSessionRecord(row: SessionRow | null | undefined): SessionRecordPayload | null {
  if (!row) {
    return null;
  }
  return {
    id: Number(row.id),
    campaign_slug: String(row.campaign_slug),
    status: String(row.status),
    started_at: isoString(row.started_at),
    started_by_user_id: row.started_by_user_id === null ? null : Number(row.started_by_user_id),
    ended_at: isoString(row.ended_at),
    ended_by_user_id: row.ended_by_user_id === null ? null : Number(row.ended_by_user_id),
    is_active: String(row.status) === "active",
  };
}

function loadStateRevision(database: Database.Database, campaignSlug: string): number {
  const row = database
    .prepare("SELECT campaign_slug, revision FROM campaign_session_states WHERE campaign_slug = ?")
    .get(campaignSlug) as SessionStateRow | undefined;
  return row ? Number(row.revision || 0) : SESSION_READONLY_REVISION;
}

function loadActiveSession(database: Database.Database, campaignSlug: string): SessionRow | null {
  return (
    (database
      .prepare(
        `
          SELECT id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id
          FROM campaign_sessions
          WHERE campaign_slug = ?
            AND status = 'active'
          ORDER BY started_at DESC, id DESC
          LIMIT 1
        `,
      )
      .get(campaignSlug) as SessionRow | undefined) || null
  );
}

function loadArticles(database: Database.Database, campaignSlug: string, statuses: string[]): SessionArticleRow[] {
  const placeholders = statuses.map(() => "?").join(", ");
  return database
    .prepare(
      `
        SELECT
          id,
          campaign_slug,
          title,
          body_markdown,
          source_page_ref,
          status,
          created_at,
          created_by_user_id,
          revealed_at,
          revealed_by_user_id,
          revealed_in_session_id
        FROM campaign_session_articles
        WHERE campaign_slug = ?
          AND status IN (${placeholders})
        ORDER BY created_at ASC, id ASC
      `,
    )
    .all(campaignSlug, ...statuses) as SessionArticleRow[];
}

function loadAllArticles(database: Database.Database, campaignSlug: string): SessionArticleRow[] {
  return database
    .prepare(
      `
        SELECT
          id,
          campaign_slug,
          title,
          body_markdown,
          source_page_ref,
          status,
          created_at,
          created_by_user_id,
          revealed_at,
          revealed_by_user_id,
          revealed_in_session_id
        FROM campaign_session_articles
        WHERE campaign_slug = ?
        ORDER BY created_at ASC, id ASC
      `,
    )
    .all(campaignSlug) as SessionArticleRow[];
}

function loadArticleImages(database: Database.Database, articleIds: number[]): Map<number, SessionArticleImageRow> {
  const uniqueIds = [...new Set(articleIds.map((id) => Math.trunc(id)).filter((id) => id > 0))];
  if (uniqueIds.length === 0) {
    return new Map();
  }
  const placeholders = uniqueIds.map(() => "?").join(", ");
  const rows = database
    .prepare(
      `
        SELECT article_id, filename, media_type, alt_text, caption, updated_at
        FROM campaign_session_article_images
        WHERE article_id IN (${placeholders})
      `,
    )
    .all(...uniqueIds) as SessionArticleImageRow[];
  return new Map(rows.map((row) => [Number(row.article_id), row]));
}

function loadArticleImageBlob(
  database: Database.Database,
  campaignSlug: string,
  articleId: number,
): SessionArticleImageBlobRow | null {
  return (
    (database
      .prepare(
        `
          SELECT
            image.article_id,
            image.filename,
            image.media_type,
            image.alt_text,
            image.caption,
            image.data_blob,
            image.updated_at,
            article.status AS article_status,
            article.revealed_in_session_id
          FROM campaign_session_article_images AS image
          JOIN campaign_session_articles AS article ON article.id = image.article_id
          WHERE article.campaign_slug = ?
            AND article.id = ?
          LIMIT 1
        `,
      )
      .get(campaignSlug, articleId) as SessionArticleImageBlobRow | undefined) || null
  );
}

function loadMessages(
  database: Database.Database,
  campaignSlug: string,
  sessionId: number,
  role: FixtureSystemsRole,
): SessionMessageRow[] {
  const manager = canManageSession(role);
  const rows = database
    .prepare(
      `
        SELECT
          id,
          session_id,
          campaign_slug,
          message_type,
          body_text,
          recipient_scope,
          recipient_user_id,
          author_user_id,
          author_display_name,
          article_id,
          created_at
        FROM campaign_session_messages
        WHERE campaign_slug = ?
          AND session_id = ?
        ORDER BY created_at ASC, id ASC
      `,
    )
    .all(campaignSlug, sessionId) as SessionMessageRow[];
  return manager ? rows : rows.filter((row) => String(row.recipient_scope || "global") === "global");
}

function loadSessionLogs(database: Database.Database, campaignSlug: string, limit = 20): SessionSummaryRow[] {
  return database
    .prepare(
      `
        SELECT
          s.id,
          s.campaign_slug,
          s.status,
          s.started_at,
          s.started_by_user_id,
          s.ended_at,
          s.ended_by_user_id,
          COUNT(m.id) AS message_count,
          MAX(m.created_at) AS last_message_at
        FROM campaign_sessions AS s
        LEFT JOIN campaign_session_messages AS m ON m.session_id = s.id
        WHERE s.campaign_slug = ?
          AND s.status = 'closed'
        GROUP BY s.id
        ORDER BY s.started_at DESC, s.id DESC
        LIMIT ?
      `,
    )
    .all(campaignSlug, Math.max(1, Math.trunc(limit))) as SessionSummaryRow[];
}

function loadSessionLog(database: Database.Database, campaignSlug: string, sessionId: number): SessionRow | null {
  return (
    (database
      .prepare(
        `
          SELECT id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id
          FROM campaign_sessions
          WHERE campaign_slug = ?
            AND id = ?
            AND status = 'closed'
          LIMIT 1
        `,
      )
      .get(campaignSlug, sessionId) as SessionRow | undefined) || null
  );
}

async function buildSourceMetadata(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole | null,
  sourceKind: SessionSourceKind,
  sourceRef: string,
) {
  const metadata = {
    title: "",
    label: "",
    action_label: "",
    missing_message: "",
    url: "",
  };
  if (!sourceKind || !sourceRef) {
    return metadata;
  }
  if (sourceKind === "page") {
    metadata.label = "published wiki page";
    metadata.action_label = "View published page";
    metadata.missing_message = "The original published wiki page is not currently visible in the player wiki.";
    const page = await campaignWikiRepository.getPage(campaign.slug, sourceRef);
    if (page) {
      metadata.title = page.title;
      metadata.url = `/campaigns/${campaign.slug}/pages/${page.route_slug}`;
    }
    return metadata;
  }
  metadata.label = "Systems entry";
  metadata.action_label = "View Systems entry";
  metadata.missing_message = "The original Systems entry is not currently visible in this campaign.";
  if (role) {
    const result = buildCampaignSystemsEntryDetailPayload(
      dbPath,
      campaign,
      campaignConfig,
      sourceRef,
      role,
    );
    if (result.status === "ok") {
      metadata.title = String(result.payload.entry.title || "");
      metadata.url = `/campaigns/${campaign.slug}/systems/entries/${result.payload.entry.slug}`;
    }
  }
  return metadata;
}

function serializeArticleImage(
  campaignSlug: string,
  articleId: number,
  image: SessionArticleImageRow | undefined,
): SessionArticleImagePayload | null {
  if (!image) {
    return null;
  }
  return {
    filename: String(image.filename || ""),
    media_type: String(image.media_type || ""),
    alt_text: String(image.alt_text || ""),
    caption: String(image.caption || ""),
    updated_at: isoString(image.updated_at),
    url: `/api/v1/campaigns/${campaignSlug}/session/articles/${articleId}/image`,
  };
}

async function serializeArticle(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole | null,
  article: SessionArticleRow,
  image: SessionArticleImageRow | undefined,
): Promise<SessionArticlePayload> {
  const [sourceKind, sourceRef] = parseSessionArticleSourceRef(article.source_page_ref);
  const source = await buildSourceMetadata(dbPath, campaign, campaignConfig, role, sourceKind, sourceRef);
  return {
    id: Number(article.id),
    campaign_slug: String(article.campaign_slug),
    title: String(article.title || ""),
    body_markdown: String(article.body_markdown || ""),
    body_format: sourceKind === "systems" ? "html" : "markdown",
    source_page_ref: String(article.source_page_ref || ""),
    source_kind: sourceKind,
    source_ref: sourceRef,
    status: String(article.status || ""),
    created_at: isoString(article.created_at),
    created_by_user_id: article.created_by_user_id === null ? null : Number(article.created_by_user_id),
    revealed_at: isoString(article.revealed_at),
    revealed_by_user_id: article.revealed_by_user_id === null ? null : Number(article.revealed_by_user_id),
    revealed_in_session_id:
      article.revealed_in_session_id === null ? null : Number(article.revealed_in_session_id),
    is_revealed: String(article.status) === "revealed",
    links: {
      source_url: source.url,
      published_page_url: "",
      player_wiki_editor_url: "",
      convert_url: "",
    },
    source: {
      title: source.title,
      label: source.label,
      action_label: source.action_label,
      missing_message: source.missing_message,
    },
    converted_page: null,
    image: serializeArticleImage(campaign.slug, Number(article.id), image),
  };
}

async function serializeMessages(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  messages: SessionMessageRow[],
  articlesById: Map<number, SessionArticleRow>,
  imagesByArticleId: Map<number, SessionArticleImageRow>,
): Promise<SessionMessagePayload[]> {
  const payloads: SessionMessagePayload[] = [];
  for (const message of messages) {
    const article = message.article_id === null ? undefined : articlesById.get(Number(message.article_id));
    payloads.push({
      id: Number(message.id),
      session_id: Number(message.session_id),
      campaign_slug: String(message.campaign_slug),
      message_type: String(message.message_type || ""),
      body_text: String(message.body_text || ""),
      author_user_id: message.author_user_id === null ? null : Number(message.author_user_id),
      author_display_name: String(message.author_display_name || ""),
      article_id: message.article_id === null ? null : Number(message.article_id),
      created_at: isoString(message.created_at),
      recipient_scope: String(message.recipient_scope || "global"),
      recipient_user_id: message.recipient_user_id === null ? null : Number(message.recipient_user_id),
      recipient_label:
        String(message.recipient_scope || "global") === "dm_only"
          ? "DM"
          : message.recipient_user_id
            ? `User ${message.recipient_user_id}`
            : "",
      article: article
        ? await serializeArticle(
            dbPath,
            campaign,
            campaignConfig,
            role,
            article,
            imagesByArticleId.get(Number(article.id)),
          )
        : null,
    });
  }
  return payloads;
}

function serializeSessionLogSummary(campaignSlug: string, row: SessionSummaryRow): SessionLogSummaryPayload {
  return {
    session: serializeSessionRecord(row)!,
    message_count: Number(row.message_count || 0),
    last_message_at: isoString(row.last_message_at),
    detail_url: `/api/v1/campaigns/${campaignSlug}/session/logs/${Number(row.id)}`,
  };
}

export async function buildSessionStatePayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown> = {},
  role: FixtureSystemsRole | null = null,
): Promise<SessionStatePayload> {
  if (!role || !existsSync(dbPath)) {
    return emptySessionPayload(campaign, role);
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const manageSession = canManageSession(role);
    const sessionRevision = loadStateRevision(database, campaign.slug);
    const activeSession = loadActiveSession(database, campaign.slug);
    const articleStatuses = manageSession ? ["staged", "revealed"] : ["revealed"];
    const articles = loadArticles(database, campaign.slug, articleStatuses);
    const articleImages = loadArticleImages(database, articles.map((article) => Number(article.id)));
    const articlesById = new Map(articles.map((article) => [Number(article.id), article]));
    const messages = activeSession ? loadMessages(database, campaign.slug, Number(activeSession.id), role) : [];

    const payload: SessionStatePayload = {
      ok: true,
      campaign,
      permissions: {
        can_manage_session: manageSession,
        can_post_messages: canPostMessages(role),
      },
      active_session: serializeSessionRecord(activeSession),
      messages: await serializeMessages(
        dbPath,
        campaign,
        campaignConfig,
        role,
        messages,
        articlesById,
        articleImages,
      ),
      session_message_recipient_player_choices: [],
      show_session_dm_passive_scores: false,
      session_revision: sessionRevision,
      session_view_token: buildSessionViewToken(campaign, sessionRevision, role),
    };

    if (manageSession) {
      payload.staged_articles = await Promise.all(
        articles
          .filter((article) => String(article.status) === "staged")
          .map((article) =>
            serializeArticle(dbPath, campaign, campaignConfig, role, article, articleImages.get(Number(article.id))),
          ),
      );
      payload.revealed_articles = await Promise.all(
        articles
          .filter((article) => String(article.status) === "revealed")
          .map((article) =>
            serializeArticle(dbPath, campaign, campaignConfig, role, article, articleImages.get(Number(article.id))),
          ),
      );
      payload.session_logs = loadSessionLogs(database, campaign.slug, 20).map((row) =>
        serializeSessionLogSummary(campaign.slug, row),
      );
      payload.show_session_dm_passive_scores = campaign.system.trim().toLowerCase() === "dnd-5e";
      payload.session_dm_passive_scores = [];
    }

    return payload;
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return emptySessionPayload(campaign, role);
    }
    throw error;
  } finally {
    database.close();
  }
}

export function readSessionArticleImage(
  dbPath: string,
  campaignSlug: string,
  articleId: number,
  role: FixtureSystemsRole,
): SessionArticleImageReadResult {
  if (!existsSync(dbPath)) {
    return {
      status: "not_found",
      filename: "",
      mediaType: "",
      data: new Uint8Array(),
    };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = loadArticleImageBlob(database, campaignSlug, articleId);
    if (!row) {
      return {
        status: "not_found",
        filename: "",
        mediaType: "",
        data: new Uint8Array(),
      };
    }

    if (!canManageSession(role)) {
      const activeSession = loadActiveSession(database, campaignSlug);
      if (
        !activeSession ||
        String(row.article_status) !== "revealed" ||
        row.revealed_in_session_id === null ||
        Number(row.revealed_in_session_id) !== Number(activeSession.id)
      ) {
        return {
          status: "not_found",
          filename: "",
          mediaType: "",
          data: new Uint8Array(),
        };
      }
    }

    return {
      status: "ok",
      filename: String(row.filename || "session-article-image"),
      mediaType: String(row.media_type || "application/octet-stream"),
      data: Uint8Array.from(row.data_blob),
    };
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return {
        status: "not_found",
        filename: "",
        mediaType: "",
        data: new Uint8Array(),
      };
    }
    throw error;
  } finally {
    database.close();
  }
}

export async function buildSessionLogDetailPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  sessionId: number,
  role: FixtureSystemsRole,
): Promise<SessionLogDetailResult> {
  if (!canManageSession(role) || !existsSync(dbPath)) {
    return { status: "not_found" };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const session = loadSessionLog(database, campaign.slug, sessionId);
    if (!session) {
      return { status: "not_found" };
    }
    const articles = loadAllArticles(database, campaign.slug);
    const articleImages = loadArticleImages(database, articles.map((article) => Number(article.id)));
    const articlesById = new Map(articles.map((article) => [Number(article.id), article]));
    const messages = loadMessages(database, campaign.slug, Number(session.id), role);
    return {
      status: "ok",
      payload: {
        ok: true,
        session: serializeSessionRecord(session)!,
        messages: await serializeMessages(
          dbPath,
          campaign,
          campaignConfig,
          role,
          messages,
          articlesById,
          articleImages,
        ),
      },
    };
  } catch (error) {
    if (isNoSuchTableError(error)) {
      return { status: "not_found" };
    }
    throw error;
  } finally {
    database.close();
  }
}
