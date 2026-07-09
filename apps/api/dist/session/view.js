import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";
import { parse as parseYaml } from "yaml";
import { buildCampaignSystemsEntryDetailPayload } from "../systems/sources.js";
import { campaignWikiRepository } from "../wiki/repository.js";
export const SESSION_READONLY_REVISION = 0;
const ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
};
const ALLOWED_SESSION_ARTICLE_MARKDOWN_EXTENSIONS = new Set([".markdown", ".md"]);
const FRONTMATTER_PATTERN = /^---\s*\n([\s\S]*?)\n---\s*\n?/;
const SESSION_ARTICLE_TITLE_HEADING_PATTERN = /^\s{0,3}#\s+(?<title>.*?)\s*#*\s*$/;
const SESSION_ARTICLE_MARKDOWN_IMAGE_PATTERN = /!\[(?<alt>[^\]]*)\]\((?<target><[^>]+>|[^)\s]+)(?:\s+"(?<title>[^"]*)")?\)/;
const SESSION_ARTICLE_OBSIDIAN_IMAGE_PATTERN = /!\[\[(?<target>[^\]|#]+)(?:#[^\]|]*)?(?:\|(?<label>[^\]]+))?\]\]/;
function stableHexDigest(value) {
    return createHash("sha1").update(value).digest("hex");
}
function canManageSession(role) {
    return role === "dm" || role === "admin";
}
function canPostMessages(role) {
    return role === "player" || role === "dm" || role === "admin";
}
function isNoSuchTableError(error) {
    return error instanceof Error && error.message.includes("no such table");
}
function isoString(value) {
    const rawValue = String(value ?? "").trim();
    return rawValue || null;
}
function utcIsoTimestamp() {
    return new Date().toISOString().replace("Z", "+00:00");
}
function basename(value) {
    return String(value || "").replace(/\\/g, "/").split("/").filter(Boolean).at(-1) || "";
}
function titleFromSlug(value) {
    const tail = String(value || "").split(/[\\/]/).at(-1) || String(value || "");
    const words = tail.replace(/\.[^.]*$/, "").replace(/[-_]+/g, " ").trim();
    return words
        ? words
            .split(/\s+/)
            .filter(Boolean)
            .map((word) => word[0].toUpperCase() + word.slice(1))
            .join(" ")
        : value;
}
function normalizeLookup(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function normalizeImageReference(value) {
    let normalized = String(value || "").trim();
    if (normalized.startsWith("<") && normalized.endsWith(">")) {
        normalized = normalized.slice(1, -1).trim();
    }
    return normalized.replace(/\\/g, "/");
}
function normalizeObsidianImageLabel(value) {
    const normalized = String(value || "").trim();
    if (!normalized || /^\d+(?:x\d+)?$/.test(normalized)) {
        return "";
    }
    return normalized;
}
function stripMarkdownImageToken(markdownText, start, end) {
    return (markdownText.slice(0, start) + markdownText.slice(end)).replace(/\n{3,}/g, "\n\n").trim();
}
function extractSessionArticleTitleHeading(markdownText) {
    const lines = String(markdownText || "").replace(/\r\n/g, "\n").split("\n");
    let lineIndex = 0;
    while (lineIndex < lines.length && !String(lines[lineIndex] || "").trim()) {
        lineIndex += 1;
    }
    if (lineIndex >= lines.length) {
        return { title: "", body: String(markdownText || "").trim() };
    }
    const match = String(lines[lineIndex] || "").match(SESSION_ARTICLE_TITLE_HEADING_PATTERN);
    const title = String(match?.groups?.title || "").trim();
    if (!title) {
        return { title: "", body: String(markdownText || "").trim() };
    }
    const bodyLines = lines.slice(lineIndex + 1);
    while (bodyLines.length > 0 && !String(bodyLines[0] || "").trim()) {
        bodyLines.shift();
    }
    return { title, body: bodyLines.join("\n").trim() };
}
function extractMarkdownImageReference(markdownText) {
    const normalizedText = String(markdownText || "");
    const obsidianMatch = SESSION_ARTICLE_OBSIDIAN_IMAGE_PATTERN.exec(normalizedText);
    const markdownMatch = SESSION_ARTICLE_MARKDOWN_IMAGE_PATTERN.exec(normalizedText);
    let chosenKind = "";
    let chosenMatch = null;
    if (obsidianMatch && markdownMatch) {
        chosenKind = obsidianMatch.index <= markdownMatch.index ? "obsidian" : "markdown";
        chosenMatch = chosenKind === "obsidian" ? obsidianMatch : markdownMatch;
    }
    else if (obsidianMatch) {
        chosenKind = "obsidian";
        chosenMatch = obsidianMatch;
    }
    else if (markdownMatch) {
        chosenKind = "markdown";
        chosenMatch = markdownMatch;
    }
    if (!chosenMatch) {
        return {
            title: "",
            body_markdown: normalizedText.trim(),
            image_reference: "",
            image_alt: "",
            image_caption: "",
        };
    }
    const imageReference = normalizeImageReference(chosenMatch.groups?.target || "");
    if (!imageReference) {
        return {
            title: "",
            body_markdown: normalizedText.trim(),
            image_reference: "",
            image_alt: "",
            image_caption: "",
        };
    }
    return {
        title: "",
        body_markdown: stripMarkdownImageToken(normalizedText, chosenMatch.index, chosenMatch.index + chosenMatch[0].length),
        image_reference: imageReference,
        image_alt: chosenKind === "obsidian"
            ? normalizeObsidianImageLabel(chosenMatch.groups?.label || "")
            : String(chosenMatch.groups?.alt || "").trim(),
        image_caption: chosenKind === "obsidian" ? "" : String(chosenMatch.groups?.title || "").trim(),
    };
}
function stripMatchingBodyImageReference(markdownText, imageReference) {
    const normalizedReference = normalizeImageReference(imageReference);
    if (!normalizedReference) {
        return String(markdownText || "").trim();
    }
    const normalizedBasename = basename(normalizedReference).toLowerCase();
    for (const pattern of [SESSION_ARTICLE_OBSIDIAN_IMAGE_PATTERN, SESSION_ARTICLE_MARKDOWN_IMAGE_PATTERN]) {
        const match = pattern.exec(markdownText);
        if (!match) {
            continue;
        }
        const target = normalizeImageReference(match.groups?.target || "");
        if (target === normalizedReference || basename(target).toLowerCase() === normalizedBasename) {
            return stripMarkdownImageToken(markdownText, match.index, match.index + match[0].length);
        }
    }
    return String(markdownText || "").trim();
}
function parseFrontmatter(rawText) {
    const normalized = String(rawText || "").replace(/\r\n/g, "\n");
    const match = normalized.match(FRONTMATTER_PATTERN);
    if (!match) {
        return { status: "ok", metadata: {}, body: normalized };
    }
    try {
        const parsed = parseYaml(match[1] || "") || {};
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
            return { status: "error", message: "Uploaded markdown frontmatter must be a YAML object." };
        }
        return { status: "ok", metadata: parsed, body: normalized.slice(match[0].length) };
    }
    catch {
        return { status: "error", message: "Uploaded markdown frontmatter must be valid YAML." };
    }
}
function parseArticleMarkdownUpload(filename, markdownText) {
    const normalizedFilename = basename(String(filename || "").trim());
    if (!normalizedFilename) {
        return { status: "validation_error", message: "Choose a markdown file before saving the session article." };
    }
    const extension = path.extname(normalizedFilename).toLowerCase();
    if (!ALLOWED_SESSION_ARTICLE_MARKDOWN_EXTENSIONS.has(extension)) {
        return {
            status: "validation_error",
            message: "Session article uploads must be Markdown files with .md or .markdown extensions.",
        };
    }
    const rawText = String(markdownText ?? "");
    if (!rawText) {
        return { status: "validation_error", message: "Uploaded markdown files cannot be empty." };
    }
    const parsed = parseFrontmatter(rawText.replace(/^\uFEFF/, ""));
    if (parsed.status === "error") {
        return { status: "validation_error", message: parsed.message };
    }
    const fallbackTitle = titleFromSlug(normalizedFilename);
    let normalizedTitle = String(parsed.metadata.title || "").trim();
    let normalizedBody = parsed.body.trim();
    const heading = extractSessionArticleTitleHeading(normalizedBody);
    let imageReference = normalizeImageReference(parsed.metadata.image || "");
    let imageAlt = String(parsed.metadata.image_alt || "").trim();
    let imageCaption = String(parsed.metadata.image_caption || "").trim();
    if (normalizedTitle) {
        if (heading.title && normalizeLookup(heading.title) === normalizeLookup(normalizedTitle)) {
            normalizedBody = heading.body;
        }
    }
    else if (heading.title) {
        normalizedTitle = heading.title;
        normalizedBody = heading.body;
    }
    else {
        normalizedTitle = fallbackTitle;
    }
    if (imageReference) {
        normalizedBody = stripMatchingBodyImageReference(normalizedBody, imageReference);
    }
    else {
        const extracted = extractMarkdownImageReference(normalizedBody);
        imageReference = extracted.image_reference;
        imageAlt = imageAlt || extracted.image_alt;
        imageCaption = imageCaption || extracted.image_caption;
        normalizedBody = extracted.body_markdown;
    }
    return {
        status: "ok",
        upload: {
            title: normalizedTitle,
            body_markdown: normalizedBody,
            image_reference: imageReference,
            image_alt: imageAlt,
            image_caption: imageCaption,
        },
    };
}
function decodeEmbeddedFile(payload, label) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return { status: "validation_error", message: `${label} must be an object.` };
    }
    const record = payload;
    const filename = String(record.filename || "").trim();
    const dataBase64 = String(record.data_base64 || "").trim();
    const mediaType = String(record.media_type || "").trim() || null;
    if (!filename) {
        return { status: "validation_error", message: `${label} filename is required.` };
    }
    if (!dataBase64) {
        return { status: "validation_error", message: `${label} data_base64 is required.` };
    }
    if (dataBase64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(dataBase64)) {
        return { status: "validation_error", message: `${label} data_base64 must be valid base64.` };
    }
    const dataBlob = Buffer.from(dataBase64, "base64");
    if (dataBlob.toString("base64").replace(/=+$/g, "") !== dataBase64.replace(/=+$/g, "")) {
        return { status: "validation_error", message: `${label} data_base64 must be valid base64.` };
    }
    return { status: "ok", filename, media_type: mediaType, data_blob: dataBlob };
}
function prepareArticleImageUpload(input) {
    const normalizedFilename = basename(String(input.filename || "").trim());
    if (!normalizedFilename) {
        return { status: "validation_error", message: "Choose an image file before saving the session article." };
    }
    const extension = path.extname(normalizedFilename).toLowerCase();
    const allowedMediaType = ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS[extension];
    if (!allowedMediaType) {
        return { status: "validation_error", message: "Session article images must be PNG, JPG, GIF, or WEBP files." };
    }
    const dataBlob = Buffer.from(input.data_blob);
    if (dataBlob.byteLength <= 0) {
        return { status: "validation_error", message: "Uploaded image files cannot be empty." };
    }
    if (dataBlob.byteLength > 8 * 1024 * 1024) {
        return { status: "validation_error", message: "Session article images must stay under 8 MB." };
    }
    return {
        status: "ok",
        image: {
            filename: normalizedFilename,
            media_type: allowedMediaType,
            data_blob: dataBlob,
            alt_text: String(input.alt_text || "").trim(),
            caption: String(input.caption || "").trim(),
        },
    };
}
function normalizeArticleFields(title, bodyMarkdown, hasContentImage) {
    const normalizedTitle = String(title || "").trim();
    const normalizedBody = String(bodyMarkdown || "").trim();
    if (!normalizedTitle) {
        return { status: "validation_error", message: "Session articles need a title." };
    }
    if (!normalizedBody && !hasContentImage) {
        return {
            status: "validation_error",
            message: "Session articles need body text or an image before they can be saved.",
        };
    }
    if (normalizedTitle.length > 200) {
        return { status: "validation_error", message: "Session article titles must stay under 200 characters." };
    }
    if (normalizedBody.length > 40_000) {
        return { status: "validation_error", message: "Session articles must stay under 40,000 characters." };
    }
    return { status: "ok", title: normalizedTitle, bodyMarkdown: normalizedBody };
}
function normalizeSessionArticleSourceRef(value) {
    const [sourceKind, sourceRef] = parseSessionArticleSourceRef(value);
    if (!sourceRef) {
        return "";
    }
    return sourceKind === "systems" ? `systems:${sourceRef}` : sourceRef;
}
function parseSessionArticleSourceRef(value) {
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
export function buildSessionViewToken(campaign, sessionRevision, role = null) {
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
function emptySessionPayload(campaign, role = null) {
    const sessionRevision = SESSION_READONLY_REVISION;
    const manageSession = canManageSession(role);
    const payload = {
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
function serializeSessionRecord(row) {
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
function loadStateRevision(database, campaignSlug) {
    const row = database
        .prepare("SELECT campaign_slug, revision FROM campaign_session_states WHERE campaign_slug = ?")
        .get(campaignSlug);
    return row ? Number(row.revision || 0) : SESSION_READONLY_REVISION;
}
function loadActiveSession(database, campaignSlug) {
    return (database
        .prepare(`
          SELECT id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id
          FROM campaign_sessions
          WHERE campaign_slug = ?
            AND status = 'active'
          ORDER BY started_at DESC, id DESC
          LIMIT 1
        `)
        .get(campaignSlug) || null);
}
function loadArticles(database, campaignSlug, statuses) {
    const placeholders = statuses.map(() => "?").join(", ");
    return database
        .prepare(`
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
      `)
        .all(campaignSlug, ...statuses);
}
function loadAllArticles(database, campaignSlug) {
    return database
        .prepare(`
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
      `)
        .all(campaignSlug);
}
function loadArticleImages(database, articleIds) {
    const uniqueIds = [...new Set(articleIds.map((id) => Math.trunc(id)).filter((id) => id > 0))];
    if (uniqueIds.length === 0) {
        return new Map();
    }
    const placeholders = uniqueIds.map(() => "?").join(", ");
    const rows = database
        .prepare(`
        SELECT article_id, filename, media_type, alt_text, caption, updated_at
        FROM campaign_session_article_images
        WHERE article_id IN (${placeholders})
      `)
        .all(...uniqueIds);
    return new Map(rows.map((row) => [Number(row.article_id), row]));
}
function loadArticleImageBlob(database, campaignSlug, articleId) {
    return (database
        .prepare(`
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
        `)
        .get(campaignSlug, articleId) || null);
}
function loadMessages(database, campaignSlug, sessionId, role, viewerUserId = null) {
    const manager = canManageSession(role);
    if (manager) {
        return database
            .prepare(`
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
      `)
            .all(campaignSlug, sessionId);
    }
    const viewerId = Math.trunc(Number(viewerUserId || 0));
    return database
        .prepare(`
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
          AND (
            COALESCE(recipient_scope, 'global') = 'global'
            OR (recipient_scope = 'player' AND recipient_user_id = ?)
            OR author_user_id = ?
          )
        ORDER BY created_at ASC, id ASC
      `)
        .all(campaignSlug, sessionId, viewerId, viewerId);
}
function loadActivePlayerRows(database, campaignSlug) {
    return database
        .prepare(`
        SELECT
          users.id AS user_id,
          users.display_name AS display_name
        FROM users
        JOIN campaign_memberships
          ON campaign_memberships.user_id = users.id
        WHERE campaign_memberships.campaign_slug = ?
          AND campaign_memberships.role = 'player'
          AND campaign_memberships.status = 'active'
          AND users.status = 'active'
        ORDER BY users.display_name ASC, users.email ASC
      `)
        .all(campaignSlug);
}
function buildRecipientLabelMap(activePlayers) {
    return new Map(activePlayers.map((row) => {
        const userId = Number(row.user_id);
        return [userId, String(row.display_name || "").trim() || `User ${userId}`];
    }));
}
function serializeActivePlayerChoices(activePlayers) {
    return activePlayers.map((row) => {
        const userId = Number(row.user_id);
        return {
            user_id: userId,
            label: String(row.display_name || "").trim() || `User ${userId}`,
        };
    });
}
function loadSessionLogs(database, campaignSlug, limit = 20) {
    return database
        .prepare(`
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
      `)
        .all(campaignSlug, Math.max(1, Math.trunc(limit)));
}
function loadSessionLog(database, campaignSlug, sessionId) {
    return (database
        .prepare(`
          SELECT id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id
          FROM campaign_sessions
          WHERE campaign_slug = ?
            AND id = ?
            AND status = 'closed'
          LIMIT 1
        `)
        .get(campaignSlug, sessionId) || null);
}
function loadSession(database, campaignSlug, sessionId) {
    return (database
        .prepare(`
          SELECT id, campaign_slug, status, started_at, started_by_user_id, ended_at, ended_by_user_id
          FROM campaign_sessions
          WHERE campaign_slug = ?
            AND id = ?
          LIMIT 1
        `)
        .get(campaignSlug, sessionId) || null);
}
function loadArticle(database, articleId) {
    return (database
        .prepare(`
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
          WHERE id = ?
          LIMIT 1
        `)
        .get(articleId) || null);
}
function loadArticleImage(database, articleId) {
    return (database
        .prepare(`
          SELECT article_id, filename, media_type, alt_text, caption, updated_at
          FROM campaign_session_article_images
          WHERE article_id = ?
          LIMIT 1
        `)
        .get(articleId) || null);
}
async function buildSourceMetadata(dbPath, campaign, campaignConfig, role, sourceKind, sourceRef) {
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
        const result = buildCampaignSystemsEntryDetailPayload(dbPath, campaign, campaignConfig, sourceRef, role);
        if (result.status === "ok") {
            metadata.title = String(result.payload.entry.title || "");
            metadata.url = `/campaigns/${campaign.slug}/systems/entries/${result.payload.entry.slug}`;
        }
    }
    return metadata;
}
function serializeArticleImage(campaignSlug, articleId, image) {
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
async function serializeArticle(dbPath, campaign, campaignConfig, role, article, image) {
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
        revealed_in_session_id: article.revealed_in_session_id === null ? null : Number(article.revealed_in_session_id),
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
async function serializeMessages(dbPath, campaign, campaignConfig, role, messages, articlesById, imagesByArticleId, recipientLabelsByUserId) {
    const payloads = [];
    for (const message of messages) {
        const article = message.article_id === null ? undefined : articlesById.get(Number(message.article_id));
        const recipientScope = String(message.recipient_scope || "global");
        const recipientUserId = message.recipient_user_id === null ? null : Number(message.recipient_user_id);
        let recipientLabel = "";
        if (recipientScope === "dm_only") {
            recipientLabel = "DM";
        }
        else if (recipientScope === "player") {
            recipientLabel =
                recipientUserId === null
                    ? "Unknown player"
                    : recipientLabelsByUserId.get(recipientUserId) || `User ${recipientUserId}`;
        }
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
            recipient_scope: recipientScope,
            recipient_user_id: recipientUserId,
            recipient_label: recipientLabel,
            article: article
                ? await serializeArticle(dbPath, campaign, campaignConfig, role, article, imagesByArticleId.get(Number(article.id)))
                : null,
        });
    }
    return payloads;
}
function serializeSessionLogSummary(campaignSlug, row) {
    return {
        session: serializeSessionRecord(row),
        message_count: Number(row.message_count || 0),
        last_message_at: isoString(row.last_message_at),
        detail_url: `/api/v1/campaigns/${campaignSlug}/session/logs/${Number(row.id)}`,
    };
}
async function serializeSingleArticle(dbPath, campaign, campaignConfig, role, article, image) {
    return serializeArticle(dbPath, campaign, campaignConfig, role, article, image || undefined);
}
async function serializeSingleMessage(dbPath, campaign, campaignConfig, role, message, article, image) {
    const activePlayers = (() => {
        if (!existsSync(dbPath)) {
            return new Map();
        }
        const database = new Database(dbPath, { fileMustExist: true, readonly: true });
        try {
            return buildRecipientLabelMap(loadActivePlayerRows(database, campaign.slug));
        }
        finally {
            database.close();
        }
    })();
    const messages = await serializeMessages(dbPath, campaign, campaignConfig, role, [message], new Map([[Number(article.id), article]]), image ? new Map([[Number(article.id), image]]) : new Map(), activePlayers);
    return messages[0];
}
function campaignAssetImageUpload(campaignsDir, campaignSlug, assetRef, altText, caption) {
    const normalizedRef = String(assetRef || "").trim().replace(/\\/g, "/").replace(/^\/+/, "");
    if (!normalizedRef) {
        return null;
    }
    const assetRoot = path.resolve(campaignsDir, campaignSlug, "assets");
    const assetPath = path.resolve(assetRoot, normalizedRef);
    if (!(assetPath === assetRoot || assetPath.startsWith(assetRoot + path.sep)) || !existsSync(assetPath)) {
        return null;
    }
    const image = prepareArticleImageUpload({
        filename: basename(normalizedRef),
        media_type: ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS[path.extname(normalizedRef).toLowerCase()] || "",
        data_blob: readFileSync(assetPath),
        alt_text: altText,
        caption,
    });
    return image.status === "ok" ? image.image : null;
}
export async function buildSessionStatePayload(dbPath, campaign, campaignConfig = {}, role = null, viewerUserId = null) {
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
        const activePlayers = loadActivePlayerRows(database, campaign.slug);
        const recipientLabels = buildRecipientLabelMap(activePlayers);
        const messages = activeSession ? loadMessages(database, campaign.slug, Number(activeSession.id), role, viewerUserId) : [];
        const payload = {
            ok: true,
            campaign,
            permissions: {
                can_manage_session: manageSession,
                can_post_messages: canPostMessages(role),
            },
            active_session: serializeSessionRecord(activeSession),
            messages: await serializeMessages(dbPath, campaign, campaignConfig, role, messages, articlesById, articleImages, recipientLabels),
            session_message_recipient_player_choices: canPostMessages(role) ? serializeActivePlayerChoices(activePlayers) : [],
            show_session_dm_passive_scores: false,
            session_revision: sessionRevision,
            session_view_token: buildSessionViewToken(campaign, sessionRevision, role),
        };
        if (manageSession) {
            payload.staged_articles = await Promise.all(articles
                .filter((article) => String(article.status) === "staged")
                .map((article) => serializeArticle(dbPath, campaign, campaignConfig, role, article, articleImages.get(Number(article.id)))));
            payload.revealed_articles = await Promise.all(articles
                .filter((article) => String(article.status) === "revealed")
                .map((article) => serializeArticle(dbPath, campaign, campaignConfig, role, article, articleImages.get(Number(article.id)))));
            payload.session_logs = loadSessionLogs(database, campaign.slug, 20).map((row) => serializeSessionLogSummary(campaign.slug, row));
            payload.show_session_dm_passive_scores = campaign.system.trim().toLowerCase() === "dnd-5e";
            payload.session_dm_passive_scores = [];
        }
        return payload;
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return emptySessionPayload(campaign, role);
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function readSessionArticleImage(dbPath, campaignSlug, articleId, role) {
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
            if (!activeSession ||
                String(row.article_status) !== "revealed" ||
                row.revealed_in_session_id === null ||
                Number(row.revealed_in_session_id) !== Number(activeSession.id)) {
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
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return {
                status: "not_found",
                filename: "",
                mediaType: "",
                data: new Uint8Array(),
            };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function normalizeRecipientScope(value) {
    if (value === null || value === undefined || String(value).trim() === "") {
        return "global";
    }
    return String(value).trim().toLowerCase();
}
function validateRecipientUserId(value) {
    if (typeof value === "boolean") {
        return null;
    }
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}
function bumpSessionRevision(database, campaignSlug, actorUserId, now) {
    const existing = database
        .prepare("SELECT revision FROM campaign_session_states WHERE campaign_slug = ?")
        .get(campaignSlug);
    if (!existing) {
        database
            .prepare(`
          INSERT INTO campaign_session_states (
            campaign_slug,
            revision,
            updated_at,
            updated_by_user_id
          ) VALUES (?, 1, ?, ?)
        `)
            .run(campaignSlug, now, actorUserId);
        return 1;
    }
    const nextRevision = Number(existing.revision || 0) + 1;
    database
        .prepare(`
        UPDATE campaign_session_states
        SET revision = ?,
            updated_at = ?,
            updated_by_user_id = ?
        WHERE campaign_slug = ?
      `)
        .run(nextRevision, now, actorUserId, campaignSlug);
    return nextRevision;
}
export function startSession(dbPath, campaign, actor) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Session storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const activeSession = loadActiveSession(database, campaign.slug);
        if (activeSession) {
            return { status: "validation_error", message: "A live session is already running for this campaign." };
        }
        const now = utcIsoTimestamp();
        const writeSession = database.transaction(() => {
            const insertResult = database
                .prepare(`
            INSERT INTO campaign_sessions (
              campaign_slug,
              status,
              started_at,
              started_by_user_id,
              ended_at,
              ended_by_user_id
            ) VALUES (?, 'active', ?, ?, NULL, NULL)
          `)
                .run(campaign.slug, now, actor.id);
            const sessionRevision = bumpSessionRevision(database, campaign.slug, actor.id, now);
            const session = loadSession(database, campaign.slug, Number(insertResult.lastInsertRowid));
            if (!session) {
                throw new Error("Failed to persist session lifecycle record.");
            }
            return { session, sessionRevision };
        });
        const result = writeSession();
        return {
            status: "ok",
            session: serializeSessionRecord(result.session),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "Session storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function closeSession(dbPath, campaign, actor) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "There is no active session to close." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const activeSession = loadActiveSession(database, campaign.slug);
        if (!activeSession) {
            return { status: "validation_error", message: "There is no active session to close." };
        }
        const now = utcIsoTimestamp();
        const writeSession = database.transaction(() => {
            const updateResult = database
                .prepare(`
            UPDATE campaign_sessions
            SET status = 'closed',
                ended_at = ?,
                ended_by_user_id = ?
            WHERE campaign_slug = ?
              AND id = ?
              AND status = 'active'
          `)
                .run(now, actor.id, campaign.slug, Number(activeSession.id));
            if (updateResult.changes !== 1) {
                return {
                    session: null,
                    sessionRevision: loadStateRevision(database, campaign.slug),
                };
            }
            const sessionRevision = bumpSessionRevision(database, campaign.slug, actor.id, now);
            return {
                session: loadSession(database, campaign.slug, Number(activeSession.id)),
                sessionRevision,
            };
        });
        const result = writeSession();
        if (!result.session) {
            return { status: "validation_error", message: "There is no active session to close." };
        }
        return {
            status: "ok",
            session: serializeSessionRecord(result.session),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "There is no active session to close." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
async function prepareSessionArticleCreateInput(dbPath, campaignsDir, campaign, campaignConfig, role, payload) {
    const mode = String(payload.mode || "manual").trim().toLowerCase();
    if (!["manual", "upload", "wiki"].includes(mode)) {
        return { status: "validation_error", message: "Article mode must be 'manual', 'upload', or 'wiki'." };
    }
    let title = "";
    let bodyMarkdown = "";
    let sourcePageRef = "";
    let image = null;
    if (mode === "upload") {
        const markdownUpload = parseArticleMarkdownUpload(payload.filename, payload.markdown_text);
        if (markdownUpload.status !== "ok") {
            return markdownUpload;
        }
        if (markdownUpload.upload.image_reference && payload.referenced_image === undefined) {
            return {
                status: "validation_error",
                message: "This markdown file references an image. Include referenced_image too.",
            };
        }
        if (payload.referenced_image !== undefined) {
            const embeddedFile = decodeEmbeddedFile(payload.referenced_image, "referenced_image");
            if (embeddedFile.status !== "ok") {
                return embeddedFile;
            }
            const preparedImage = prepareArticleImageUpload({
                filename: embeddedFile.filename,
                media_type: embeddedFile.media_type,
                data_blob: embeddedFile.data_blob,
                alt_text: markdownUpload.upload.image_alt,
                caption: markdownUpload.upload.image_caption,
            });
            if (preparedImage.status !== "ok") {
                return preparedImage;
            }
            image = preparedImage.image;
        }
        title = markdownUpload.upload.title;
        bodyMarkdown = markdownUpload.upload.body_markdown;
    }
    else if (mode === "wiki") {
        const [sourceKind, sourceRef] = parseSessionArticleSourceRef(String(payload.source_ref || payload.page_ref || ""));
        if (sourceKind === "systems") {
            const result = buildCampaignSystemsEntryDetailPayload(dbPath, campaign, campaignConfig, sourceRef, role);
            if (result.status !== "ok") {
                return {
                    status: "validation_error",
                    message: "Choose a visible published wiki page or Systems entry before pulling it into the session store.",
                };
            }
            const body = result.payload.entry.body;
            const rendered = typeof body === "object" && body !== null ? body.rendered : null;
            const sourceBodyHtml = String(result.payload.entry.rendered_html || "").trim() ||
                (typeof rendered === "object" && rendered !== null
                    ? String(rendered.summary_html || "").trim()
                    : "");
            if (!sourceBodyHtml) {
                return {
                    status: "validation_error",
                    message: "The selected Systems entry does not have rendered article content to pull into the session store.",
                };
            }
            title = result.payload.entry.title;
            bodyMarkdown = sourceBodyHtml;
            sourcePageRef = `systems:${result.payload.entry.slug}`;
        }
        else {
            const page = await campaignWikiRepository.getPage(campaign.slug, sourceRef);
            if (!page) {
                return {
                    status: "validation_error",
                    message: "Choose a visible published wiki page or Systems entry before pulling it into the session store.",
                };
            }
            if (page.image_ref) {
                image = campaignAssetImageUpload(campaignsDir, campaign.slug, page.image_ref, page.image_alt, page.image_caption);
            }
            title = page.title;
            bodyMarkdown = page.body_markdown.trim() || page.summary.trim();
            sourcePageRef = page.page_ref;
            if (!String(bodyMarkdown || "").trim() && image === null) {
                return {
                    status: "validation_error",
                    message: "The selected wiki page does not have any body text, summary, or image to pull into the session store.",
                };
            }
        }
    }
    else {
        if (payload.image !== undefined) {
            const embeddedFile = decodeEmbeddedFile(payload.image, "image");
            if (embeddedFile.status !== "ok") {
                return embeddedFile;
            }
            const imagePayload = payload.image;
            const preparedImage = prepareArticleImageUpload({
                filename: embeddedFile.filename,
                media_type: embeddedFile.media_type,
                data_blob: embeddedFile.data_blob,
                alt_text: imagePayload.alt_text,
                caption: imagePayload.caption,
            });
            if (preparedImage.status !== "ok") {
                return preparedImage;
            }
            image = preparedImage.image;
        }
        title = payload.title;
        bodyMarkdown = payload.body_markdown;
    }
    sourcePageRef = normalizeSessionArticleSourceRef(sourcePageRef);
    if (sourcePageRef.length > 400) {
        return {
            status: "validation_error",
            message: "Session article source references must stay under 400 characters.",
        };
    }
    const normalizedFields = normalizeArticleFields(title, bodyMarkdown, image !== null);
    if (normalizedFields.status !== "ok") {
        return normalizedFields;
    }
    return {
        status: "ok",
        title: normalizedFields.title,
        bodyMarkdown: normalizedFields.bodyMarkdown,
        sourcePageRef,
        image,
    };
}
function upsertArticleImage(database, articleId, image, now) {
    database
        .prepare(`
        INSERT INTO campaign_session_article_images (
          article_id,
          filename,
          media_type,
          alt_text,
          caption,
          data_blob,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(article_id) DO UPDATE SET
          filename = excluded.filename,
          media_type = excluded.media_type,
          alt_text = excluded.alt_text,
          caption = excluded.caption,
          data_blob = excluded.data_blob,
          updated_at = excluded.updated_at
      `)
        .run(articleId, image.filename, image.media_type, image.alt_text, image.caption, image.data_blob, now);
    const imageRow = loadArticleImage(database, articleId);
    if (!imageRow) {
        throw new Error("Failed to persist session article image.");
    }
    return imageRow;
}
export async function createSessionArticle(dbPath, campaignsDir, campaign, campaignConfig, role, actor, payload) {
    const prepared = await prepareSessionArticleCreateInput(dbPath, campaignsDir, campaign, campaignConfig, role, payload);
    if (prepared.status !== "ok") {
        return prepared;
    }
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Session storage is not initialized." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const now = utcIsoTimestamp();
        const writeArticle = database.transaction(() => {
            const insertResult = database
                .prepare(`
            INSERT INTO campaign_session_articles (
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
            ) VALUES (?, ?, ?, ?, 'staged', ?, ?, NULL, NULL, NULL)
          `)
                .run(campaign.slug, prepared.title, prepared.bodyMarkdown, prepared.sourcePageRef, now, actor.id);
            const articleId = Number(insertResult.lastInsertRowid);
            const imageRow = prepared.image ? upsertArticleImage(database, articleId, prepared.image, now) : null;
            const sessionRevision = bumpSessionRevision(database, campaign.slug, actor.id, now);
            const article = loadArticle(database, articleId);
            if (!article) {
                throw new Error("Failed to persist session article.");
            }
            return { article, imageRow, sessionRevision };
        });
        const result = writeArticle();
        return {
            status: "ok",
            article: await serializeSingleArticle(dbPath, campaign, campaignConfig, role, result.article, result.imageRow),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "Session storage is not initialized." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function updateSessionArticle(dbPath, campaign, campaignConfig, role, actor, articleId, payload) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "That session article could not be found." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const article = loadArticle(database, articleId);
        if (!article || article.campaign_slug !== campaign.slug) {
            return { status: "validation_error", message: "That session article could not be found." };
        }
        if (String(article.status) === "revealed") {
            return { status: "validation_error", message: "Revealed session articles cannot be edited in the prep queue." };
        }
        let imageUpload = null;
        if (payload.image !== undefined) {
            const embeddedFile = decodeEmbeddedFile(payload.image, "image");
            if (embeddedFile.status !== "ok") {
                return embeddedFile;
            }
            const imagePayload = payload.image;
            const preparedImage = prepareArticleImageUpload({
                filename: embeddedFile.filename,
                media_type: embeddedFile.media_type,
                data_blob: embeddedFile.data_blob,
                alt_text: imagePayload.alt_text,
                caption: imagePayload.caption,
            });
            if (preparedImage.status !== "ok") {
                return preparedImage;
            }
            imageUpload = preparedImage.image;
        }
        const existingImage = loadArticleImage(database, articleId);
        const wantsMetadataUpdate = payload.image_alt_text !== undefined || payload.image_caption !== undefined;
        if (wantsMetadataUpdate && imageUpload === null && existingImage === null) {
            return { status: "validation_error", message: "That session article does not have an image to update." };
        }
        const normalizedFields = normalizeArticleFields(payload.title, payload.body_markdown, imageUpload !== null || existingImage !== null);
        if (normalizedFields.status !== "ok") {
            return normalizedFields;
        }
        const now = utcIsoTimestamp();
        const writeArticle = database.transaction(() => {
            const updateResult = database
                .prepare(`
            UPDATE campaign_session_articles
            SET title = ?,
                body_markdown = ?
            WHERE id = ?
              AND campaign_slug = ?
              AND status = 'staged'
          `)
                .run(normalizedFields.title, normalizedFields.bodyMarkdown, articleId, campaign.slug);
            if (updateResult.changes !== 1) {
                return { article: null, imageRow: null, sessionRevision: loadStateRevision(database, campaign.slug) };
            }
            let imageRow = existingImage;
            if (imageUpload) {
                imageRow = upsertArticleImage(database, articleId, imageUpload, now);
            }
            else if (wantsMetadataUpdate) {
                const metadataResult = database
                    .prepare(`
              UPDATE campaign_session_article_images
              SET alt_text = ?,
                  caption = ?,
                  updated_at = ?
              WHERE article_id = ?
            `)
                    .run(String(payload.image_alt_text || "").trim(), String(payload.image_caption || "").trim(), now, articleId);
                if (metadataResult.changes !== 1) {
                    return { article: null, imageRow: null, sessionRevision: loadStateRevision(database, campaign.slug) };
                }
                imageRow = loadArticleImage(database, articleId);
            }
            const sessionRevision = bumpSessionRevision(database, campaign.slug, actor.id, now);
            return {
                article: loadArticle(database, articleId),
                imageRow,
                sessionRevision,
            };
        });
        const result = writeArticle();
        if (!result.article) {
            return {
                status: "validation_error",
                message: "That session article could not be updated. Refresh the page and try again.",
            };
        }
        return {
            status: "ok",
            article: await serializeSingleArticle(dbPath, campaign, campaignConfig, role, result.article, result.imageRow),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "That session article could not be found." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function revealSessionArticle(dbPath, campaign, campaignConfig, role, actor, articleId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "Begin a session before revealing articles in the chat." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const activeSession = loadActiveSession(database, campaign.slug);
        if (!activeSession) {
            return { status: "validation_error", message: "Begin a session before revealing articles in the chat." };
        }
        const article = loadArticle(database, articleId);
        if (!article || article.campaign_slug !== campaign.slug) {
            return { status: "validation_error", message: "That session article could not be found." };
        }
        if (String(article.status) === "revealed") {
            return { status: "validation_error", message: "That session article has already been revealed." };
        }
        const now = utcIsoTimestamp();
        const writeReveal = database.transaction(() => {
            const updateResult = database
                .prepare(`
            UPDATE campaign_session_articles
            SET status = 'revealed',
                revealed_at = ?,
                revealed_by_user_id = ?,
                revealed_in_session_id = ?
            WHERE id = ?
              AND campaign_slug = ?
              AND status = 'staged'
          `)
                .run(now, actor.id, Number(activeSession.id), articleId, campaign.slug);
            if (updateResult.changes !== 1) {
                return { article: null, imageRow: null, message: null, sessionRevision: loadStateRevision(database, campaign.slug) };
            }
            const messageResult = database
                .prepare(`
            INSERT INTO campaign_session_messages (
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
            ) VALUES (?, ?, 'article_reveal', '', 'global', NULL, ?, ?, ?, ?)
          `)
                .run(Number(activeSession.id), campaign.slug, actor.id, String(actor.display_name || "").trim() || `User ${actor.id}`, articleId, now);
            const sessionRevision = bumpSessionRevision(database, campaign.slug, actor.id, now);
            const message = database
                .prepare(`
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
            WHERE id = ?
          `)
                .get(Number(messageResult.lastInsertRowid));
            return {
                article: loadArticle(database, articleId),
                imageRow: loadArticleImage(database, articleId),
                message: message || null,
                sessionRevision,
            };
        });
        const result = writeReveal();
        if (!result.article || !result.message) {
            return {
                status: "validation_error",
                message: "That session article could not be revealed. Refresh the page and try again.",
            };
        }
        return {
            status: "ok",
            article: await serializeSingleArticle(dbPath, campaign, campaignConfig, role, result.article, result.imageRow),
            message: await serializeSingleMessage(dbPath, campaign, campaignConfig, role, result.message, result.article, result.imageRow),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "Begin a session before revealing articles in the chat." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function deleteSessionArticle(dbPath, campaign, campaignConfig, role, actor, articleId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "That session article could not be found." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const article = loadArticle(database, articleId);
        if (!article || article.campaign_slug !== campaign.slug) {
            return { status: "validation_error", message: "That session article could not be found." };
        }
        const now = utcIsoTimestamp();
        const writeDelete = database.transaction(() => {
            database
                .prepare("DELETE FROM campaign_session_messages WHERE campaign_slug = ? AND article_id = ?")
                .run(campaign.slug, articleId);
            const deleteResult = database
                .prepare("DELETE FROM campaign_session_articles WHERE id = ? AND campaign_slug = ?")
                .run(articleId, campaign.slug);
            if (deleteResult.changes !== 1) {
                return { sessionRevision: loadStateRevision(database, campaign.slug), deleted: false };
            }
            return { sessionRevision: bumpSessionRevision(database, campaign.slug, actor.id, now), deleted: true };
        });
        const result = writeDelete();
        if (!result.deleted) {
            return {
                status: "validation_error",
                message: "That session article could not be deleted. Refresh the page and try again.",
            };
        }
        return {
            status: "ok",
            article: await serializeSingleArticle(dbPath, campaign, campaignConfig, role, article, null),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "That session article could not be found." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function clearRevealedSessionArticles(dbPath, campaign, campaignConfig, role, actor) {
    if (!existsSync(dbPath)) {
        return { status: "ok", deletedArticles: [], deletedArticleIds: [], sessionRevision: SESSION_READONLY_REVISION };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const revealedArticles = loadArticles(database, campaign.slug, ["revealed"]);
        const now = utcIsoTimestamp();
        const writeClear = database.transaction(() => {
            for (const article of revealedArticles) {
                database
                    .prepare("DELETE FROM campaign_session_messages WHERE campaign_slug = ? AND article_id = ?")
                    .run(campaign.slug, Number(article.id));
                database
                    .prepare("DELETE FROM campaign_session_articles WHERE id = ? AND campaign_slug = ?")
                    .run(Number(article.id), campaign.slug);
            }
            const sessionRevision = revealedArticles.length > 0
                ? bumpSessionRevision(database, campaign.slug, actor.id, now)
                : loadStateRevision(database, campaign.slug);
            return { sessionRevision };
        });
        const result = writeClear();
        return {
            status: "ok",
            deletedArticles: await Promise.all(revealedArticles.map((article) => serializeSingleArticle(dbPath, campaign, campaignConfig, role, article, null))),
            deletedArticleIds: revealedArticles.map((article) => Number(article.id)),
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "ok", deletedArticles: [], deletedArticleIds: [], sessionRevision: SESSION_READONLY_REVISION };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function deleteSessionLog(dbPath, campaign, actor, sessionId) {
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "That chat log could not be found." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const session = loadSession(database, campaign.slug, sessionId);
        if (!session) {
            return { status: "validation_error", message: "That chat log could not be found." };
        }
        if (String(session.status) === "active") {
            return { status: "validation_error", message: "Close the live session before deleting its chat log." };
        }
        const now = utcIsoTimestamp();
        const writeDelete = database.transaction(() => {
            database
                .prepare("UPDATE campaign_session_articles SET revealed_in_session_id = NULL WHERE revealed_in_session_id = ?")
                .run(sessionId);
            database.prepare("DELETE FROM campaign_session_messages WHERE session_id = ?").run(sessionId);
            const deleteResult = database
                .prepare("DELETE FROM campaign_sessions WHERE campaign_slug = ? AND id = ? AND status = 'closed'")
                .run(campaign.slug, sessionId);
            if (deleteResult.changes !== 1) {
                return { deleted: false, sessionRevision: loadStateRevision(database, campaign.slug) };
            }
            return {
                deleted: true,
                sessionRevision: bumpSessionRevision(database, campaign.slug, actor.id, now),
            };
        });
        const result = writeDelete();
        if (!result.deleted) {
            return {
                status: "validation_error",
                message: "That chat log could not be deleted. Refresh the page and try again.",
            };
        }
        return {
            status: "ok",
            deletedSessionId: sessionId,
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "That chat log could not be found." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function postSessionMessage(dbPath, campaign, campaignConfig, role, actor, payload) {
    const bodyText = String(payload.body || "").trim();
    if (!bodyText) {
        return { status: "validation_error", message: "Enter a message before posting it to the chat." };
    }
    if (bodyText.length > 4000) {
        return { status: "validation_error", message: "Session chat messages must stay under 4,000 characters." };
    }
    if (!existsSync(dbPath)) {
        return { status: "validation_error", message: "The chat window opens when the DM begins a session." };
    }
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const activeSession = loadActiveSession(database, campaign.slug);
        if (!activeSession) {
            return { status: "validation_error", message: "The chat window opens when the DM begins a session." };
        }
        const recipientScope = normalizeRecipientScope(payload.recipient_scope);
        if (!["global", "dm_only", "player"].includes(recipientScope)) {
            return { status: "validation_error", message: "Message audience must be global, dm_only, or player." };
        }
        const activePlayers = loadActivePlayerRows(database, campaign.slug);
        const recipientLabels = buildRecipientLabelMap(activePlayers);
        let recipientUserId = null;
        if (recipientScope === "player") {
            recipientUserId = validateRecipientUserId(payload.recipient_user_id);
            if (recipientUserId === null) {
                return { status: "validation_error", message: "Choose a valid player for the targeted message." };
            }
            if (!recipientLabels.has(recipientUserId)) {
                return { status: "validation_error", message: "Choose an active campaign player for the targeted message." };
            }
        }
        const now = utcIsoTimestamp();
        const writeMessage = database.transaction(() => {
            const insertResult = database
                .prepare(`
            INSERT INTO campaign_session_messages (
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          `)
                .run(Number(activeSession.id), campaign.slug, "chat", bodyText, recipientScope, recipientUserId, actor.id, String(actor.display_name || "").trim() || `User ${actor.id}`, null, now);
            const sessionRevision = bumpSessionRevision(database, campaign.slug, actor.id, now);
            const message = database
                .prepare(`
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
            WHERE id = ?
          `)
                .get(Number(insertResult.lastInsertRowid));
            return { message, sessionRevision };
        });
        const result = writeMessage();
        const messages = await serializeMessages(dbPath, campaign, campaignConfig, role, [result.message], new Map(), new Map(), recipientLabels);
        return {
            status: "ok",
            message: messages[0],
            sessionRevision: result.sessionRevision,
        };
    }
    catch (error) {
        if (isNoSuchTableError(error)) {
            return { status: "validation_error", message: "The chat window opens when the DM begins a session." };
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export async function buildSessionLogDetailPayload(dbPath, campaign, campaignConfig, sessionId, role) {
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
        const recipientLabels = buildRecipientLabelMap(loadActivePlayerRows(database, campaign.slug));
        const messages = loadMessages(database, campaign.slug, Number(session.id), role);
        return {
            status: "ok",
            payload: {
                ok: true,
                session: serializeSessionRecord(session),
                messages: await serializeMessages(dbPath, campaign, campaignConfig, role, messages, articlesById, articleImages, recipientLabels),
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
