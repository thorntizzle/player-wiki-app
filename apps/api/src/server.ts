import path from "node:path";
import { promises as fs } from "node:fs";
import { fileURLToPath } from "node:url";

import { Hono, type Context } from "hono";
import { serve } from "@hono/node-server";

import {
  apiTokenRoleForCampaign,
  readApiTokenAuthContext,
  updateApiTokenAccountSettings,
  type AuthRouteRole,
} from "./auth/repository.js";
import {
  buildApiTokenAccountSettingsPayload,
  buildApiTokenMePayload,
  buildFixtureAccountSettingsPayload,
  buildFixtureMePayload,
} from "./auth/view.js";
import { getApiConfig } from "./config.js";
import {
  buildCampaignControlPayload,
  campaignRoleCanAccessScope,
  campaignRoleCanManageVisibility,
  updateCampaignVisibilitySettings,
} from "./campaigns/control.js";
import { getCampaignBySlug, listCampaigns, listCampaignSlugs } from "./campaigns/repository.js";
import type { CampaignViewModel } from "./campaigns/view.js";
import {
  addCombatCondition,
  addNpcCombatant,
  addPlayerCombatant,
  addStatblockCombatant,
  addSystemsMonsterCombatant,
  advanceCombatTurn,
  buildCombatReadOnlyPayload,
  clearCombatTracker,
  deleteCombatCondition,
  deleteCombatant,
  setCurrentCombatant,
  supportsCombatTracker,
  updateCombatCondition,
  updateCombatantNpcResources,
  updateCombatantPlayerDetailVisibility,
  updateCombatantResources,
  updateCombatantTurn,
  updateCombatantVitals,
} from "./combat/view.js";
import {
  buildDmContentPayload,
  createDmContentCondition,
  createDmContentStatblock,
  deleteDmContentCondition,
  deleteDmContentStatblock,
  updateDmContentCondition,
  updateDmContentStatblock,
} from "./dmContent/view.js";
import { buildCampaignHelpPayload } from "./help/view.js";
import { ROUTES } from "./routes.js";
import { buildSessionArticleSourceSearchPayload } from "./session/sourceSearch.js";
import {
  buildSessionLogDetailPayload,
  buildSessionStatePayload,
  clearRevealedSessionArticles,
  closeSession,
  createSessionArticle,
  deleteSessionArticle,
  deleteSessionLog,
  postSessionMessage,
  readSessionArticleImage,
  revealSessionArticle,
  startSession,
  updateSessionArticle,
} from "./session/view.js";
import { getSystemsImportRun, listSystemsImportRuns } from "./systems/importRuns.js";
import {
  buildCombatSystemsMonsterSearchPayload,
  buildCampaignSystemsEntryDetailPayload,
  buildCampaignSystemsIndexPayload,
  buildCampaignSystemsSourceCategoryPayload,
  buildCampaignSystemsSourceDetailPayload,
  buildCampaignSystemsSourceListPayload,
  type FixtureSystemsRole,
} from "./systems/sources.js";
import { getCampaignConfigFile } from "./content/repository.js";
import {
  buildCampaignContentPageRemovalSafety,
  deleteCampaignContentAsset,
  deleteCampaignContentCharacter,
  deleteCampaignContentPage,
  getCampaignContentAsset,
  getCampaignContentCharacter,
  getCampaignContentPage,
  listCampaignContentAssets,
  listCampaignContentCharacters,
  listCampaignContentPages,
  sanitizeContentAssetRef,
  sanitizeContentCharacterSlug,
  sanitizeContentPageRef,
  updateCampaignConfigFile,
  writeCampaignContentAsset,
  writeCampaignContentCharacter,
  writeCampaignContentPage,
} from "./content/repository.js";
import {
  applyCharacterSessionRest,
  canEditCharacterSessionState,
  previewCharacterRest,
  updateCharacterSessionCurrency,
  updateCharacterSessionFeatureState,
  updateCharacterSessionInventory,
  updateCharacterSessionNotes,
  updateCharacterSessionPersonal,
  updateCharacterSessionResource,
  updateCharacterSessionSpellSlots,
  updateCharacterSessionXianxiaActiveState,
  updateCharacterSessionXianxiaInventoryEquipped,
  updateCharacterSessionVitals,
} from "./content/characterState.js";
import {
  buildCampaignConfigPayload,
  buildContentAssetDeletePayload,
  buildContentAssetDetailPayload,
  buildContentAssetListPayload,
  buildContentAssetWritePayload,
  buildContentCharacterDeletePayload,
  buildContentCharacterDetailPayload,
  buildContentCharacterListPayload,
  buildContentPageDeletePayload,
  buildContentPageDetailPayload,
  buildContentPageListPayload,
} from "./content/view.js";
import { campaignWikiRepository, sectionSortKey, setWikiConfig, slugify } from "./wiki/repository.js";
import {
  serializeCampaign,
  serializePublicWikiPage,
  serializePublicWikiSectionGroup,
  serializeSectionNavigation,
  splitPagesBySubsection,
} from "./wiki/view.js";
import type { WikiCampaignConfig, WikiPagePayload, WikiPageRecord } from "./wiki/types.js";

const app = new Hono();

const config = getApiConfig();
setWikiConfig(config);

function fixtureAuthBlock() {
  return {
    mode: "fixture_read_only",
    runtime: "fixture-only",
    campaigns_dir: config.campaignsDir,
  };
}

function readOnlyPermissions() {
  return {
    mode: "read_only",
    can_manage_visibility: false,
    can_manage_content: false,
    can_manage_systems: false,
    can_manage_combat: false,
    can_manage_session: false,
    can_manage_dm_content: false,
    can_post_session_messages: false,
  };
}

function jsonError(
  code: string,
  message: string,
  status: 404 | 400 | 401 | 403 | 409 | 500,
  details: Record<string, unknown> = {},
) {
  return {
    ok: false,
    error: {
      code,
      message,
      details: {
        runtime: "fixture_read_only",
        ...details,
      },
    },
    status,
  };
}

function campaignNotFound(campaignSlug: string) {
  return jsonError(
    "campaign_not_found",
    `Could not load campaign '${campaignSlug}' from fixture directory.`,
    404,
    {
      campaign_slug: campaignSlug,
      campaigns_dir: config.campaignsDir,
    },
  );
}

function authRequired() {
  return {
    ok: false,
    error: {
      code: "auth_required",
      message: "Authentication required.",
    },
    status: 401 as const,
  };
}

function validationError(message: string) {
  return {
    ok: false,
    error: {
      code: "validation_error",
      message,
    },
    status: 400 as const,
  };
}

function stateConflict(message: string) {
  return {
    ok: false,
    error: {
      code: "state_conflict",
      message,
    },
    status: 409 as const,
  };
}

function invalidJson(message: string) {
  return {
    ok: false,
    error: {
      code: "invalid_json",
      message,
    },
    status: 400 as const,
  };
}

async function readJsonObject(ctx: Context): Promise<{ status: "ok"; payload: Record<string, unknown> } | { status: "error"; message: string }> {
  try {
    const payload = await ctx.req.json();
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { status: "error", message: "Request body must be a JSON object." };
    }
    return { status: "ok", payload: payload as Record<string, unknown> };
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : "Invalid JSON payload." };
  }
}

async function readOptionalJsonObject(
  ctx: Context,
): Promise<{ status: "ok"; payload: Record<string, unknown> } | { status: "error"; message: string }> {
  const rawPayload = await ctx.req.text();
  if (!rawPayload.trim()) {
    return { status: "ok", payload: {} };
  }
  try {
    const payload = JSON.parse(rawPayload);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { status: "error", message: "Request body must be a JSON object." };
    }
    return { status: "ok", payload: payload as Record<string, unknown> };
  } catch {
    return { status: "error", message: "Request body must be a JSON object." };
  }
}

function notFound(code: string, message: string) {
  return {
    ok: false,
    error: {
      code,
      message,
    },
    status: 404 as const,
  };
}

function forbidden(message: string) {
  return {
    ok: false,
    error: {
      code: "forbidden",
      message,
    },
    status: 403 as const,
  };
}

function fixtureRole(ctx: { req: { header: (name: string) => string | undefined } }): FixtureSystemsRole | null {
  const role = (ctx.req.header("X-CPW-Fixture-Role") || "").trim().toLowerCase();
  if (role === "player" || role === "dm" || role === "admin") {
    return role;
  }
  return null;
}

type RoleResolution =
  | { kind: "authenticated"; role: FixtureSystemsRole; actorUserId?: number; actorDisplayName?: string }
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "forbidden"; message: string };

type CampaignVisibilityWriteResolution =
  | { kind: "authenticated"; role: FixtureSystemsRole; actorUserId: number }
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "forbidden"; message: string };

function roleResolutionError(result: Exclude<RoleResolution, { kind: "authenticated" }>) {
  if (result.kind === "forbidden") {
    return forbidden(result.message);
  }
  return authRequired();
}

function toFixtureSystemsRole(role: AuthRouteRole): FixtureSystemsRole {
  return role;
}

type SessionManagerWriteResolution =
  | {
      kind: "authenticated";
      role: FixtureSystemsRole;
      actor: { id: number; display_name: string };
    }
  | {
      kind: "error";
      error: ReturnType<typeof authRequired> | ReturnType<typeof forbidden>;
    };

function resolveSessionManagerBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
  fixtureForbiddenMessage: string,
): SessionManagerWriteResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid") {
    return { kind: "error", error: authRequired() };
  }
  if (apiAuth.kind !== "authenticated") {
    if (fixtureRole(ctx)) {
      return { kind: "error", error: forbidden(fixtureForbiddenMessage) };
    }
    return { kind: "error", error: authRequired() };
  }

  const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
  if (role !== "dm" && role !== "admin") {
    return {
      kind: "error",
      error: forbidden("You do not have permission to manage this session."),
    };
  }
  return {
    kind: "authenticated",
    role: toFixtureSystemsRole(role),
    actor: {
      id: apiAuth.context.user.id,
      display_name: apiAuth.context.user.display_name,
    },
  };
}

function resolveCampaignRole(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (!role) {
      return { kind: "forbidden", message: "You do not have access to this campaign scope." };
    }
    return {
      kind: "authenticated",
      role: toFixtureSystemsRole(role),
      actorUserId: apiAuth.context.user.id,
      actorDisplayName: apiAuth.context.user.display_name,
    };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  const role = fixtureRole(ctx);
  return role ? { kind: "authenticated", role } : { kind: "missing" };
}

function resolveContentManagerRole(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const forbiddenMessage = "You do not have permission to manage campaign content.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role === "admin" || role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(role) };
    }
    return { kind: "forbidden", message: forbiddenMessage };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  const role = fixtureRole(ctx);
  if (role === "admin" || role === "dm") {
    return { kind: "authenticated", role };
  }
  if (role === "player") {
    return { kind: "forbidden", message: forbiddenMessage };
  }
  return { kind: "missing" };
}

function resolveContentManagerBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
  fixtureForbiddenMessage: string,
): RoleResolution {
  const forbiddenMessage = "You do not have permission to manage campaign content.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role === "admin" || role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message: forbiddenMessage };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: fixtureForbiddenMessage };
  }
  return { kind: "missing" };
}

function resolveDmContentBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role === "admin" || role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message: "You do not have permission to manage DM Content." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: "DM Content writes require bearer API authentication." };
  }
  return { kind: "missing" };
}

function resolveCombatManagerBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role === "admin" || role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message: "You do not have permission to manage combat." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: "Combat writes require bearer API authentication." };
  }
  return { kind: "missing" };
}

function resolveCombatBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role) {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message: "You do not have access to this campaign scope." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: "Combat writes require bearer API authentication." };
  }
  return { kind: "missing" };
}

function resolveCharacterSessionBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role) {
      return {
        kind: "authenticated",
        role: toFixtureSystemsRole(role),
        actorUserId: apiAuth.context.user.id,
        actorDisplayName: apiAuth.context.user.display_name,
      };
    }
    return { kind: "forbidden", message: "You do not have access to this campaign scope." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: "Character session state writes require bearer API authentication." };
  }
  return { kind: "missing" };
}

function resolveCampaignVisibilityManagerRole(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaign: CampaignViewModel,
): RoleResolution {
  const forbiddenMessage = "You do not have permission to manage campaign visibility.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaign.slug);
    if (role && campaignRoleCanManageVisibility(config.dbPath, campaign, role)) {
      return { kind: "authenticated", role: toFixtureSystemsRole(role) };
    }
    return { kind: "forbidden", message: forbiddenMessage };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  const role = fixtureRole(ctx);
  if (role && campaignRoleCanManageVisibility(config.dbPath, campaign, role)) {
    return { kind: "authenticated", role };
  }
  if (role) {
    return { kind: "forbidden", message: forbiddenMessage };
  }
  return { kind: "missing" };
}

function resolveCampaignVisibilityWriter(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaign: CampaignViewModel,
): CampaignVisibilityWriteResolution {
  const forbiddenMessage = "You do not have permission to manage campaign visibility.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaign.slug);
    if (role && campaignRoleCanManageVisibility(config.dbPath, campaign, role)) {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message: forbiddenMessage };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  const role = fixtureRole(ctx);
  if (role) {
    return {
      kind: "forbidden",
      message: "Campaign visibility updates require bearer API authentication.",
    };
  }
  return { kind: "missing" };
}

function resolveAppAdminAuth(ctx: { req: { header: (name: string) => string | undefined } }): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    if (apiAuth.context.user.is_admin) {
      return { kind: "authenticated", role: "admin" };
    }
    return { kind: "forbidden", message: "You do not have permission to use the admin API." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  return fixtureRole(ctx) === "admin" ? { kind: "authenticated", role: "admin" } : { kind: "missing" };
}

function parsePositiveInteger(rawValue: string): number | null {
  const parsed = Number(rawValue.trim());
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function campaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function flaskCampaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}

function groupPagesBySection(pages: WikiPageRecord[]): Map<string, WikiPageRecord[]> {
  const grouped = new Map<string, WikiPageRecord[]>();
  for (const page of pages) {
    if (!grouped.has(page.section)) {
      grouped.set(page.section, []);
    }
    grouped.get(page.section)!.push(page);
  }
  return grouped;
}

function sortSectionNames(sectionNames: Iterable<string>): string[] {
  return [...sectionNames].sort((left, right) => {
    const leftSort = sectionSortKey(left);
    const rightSort = sectionSortKey(right);
    if (leftSort[0] !== rightSort[0]) {
      return leftSort[0] - rightSort[0];
    }
    return leftSort[1].localeCompare(rightSort[1]);
  });
}

function isSafeAssetRef(assetRef: string): boolean {
  const normalized = assetRef.replace(/\\/g, "/");
  return Boolean(normalized) && !normalized.startsWith("/") && !normalized.split("/").includes("..");
}

async function assetExists(campaign: WikiCampaignConfig, assetRef: string): Promise<boolean> {
  if (!isSafeAssetRef(assetRef)) {
    return false;
  }
  const assetPath = path.resolve(campaign.assets_dir, assetRef);
  const assetsRoot = path.resolve(campaign.assets_dir);
  if (assetPath !== assetsRoot && !assetPath.startsWith(`${assetsRoot}${path.sep}`)) {
    return false;
  }
  try {
    const stats = await fs.stat(assetPath);
    return stats.isFile();
  } catch {
    return false;
  }
}

async function serializePageList(
  campaign: WikiCampaignConfig,
  pages: WikiPageRecord[],
): Promise<WikiPagePayload[]> {
  return Promise.all(
    pages.map((page) =>
      serializePublicWikiPage(campaign, page, {
        includeImage: false,
        assetsExist: (assetRef) => assetExists(campaign, assetRef),
      }),
    ),
  );
}

function pageSlugFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/wiki/pages/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  try {
    return decodeURIComponent(pathname.slice(prefix.length));
  } catch {
    return pathname.slice(prefix.length);
  }
}

function contentPageRefFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/content/pages/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  try {
    return (
      sanitizeContentPageRef(
        pathname.slice(prefix.length),
      ) || ""
    );
  } catch {
    return "";
  }
}

function rawContentPageRefFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/content/pages/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  return pathname.slice(prefix.length);
}

function contentAssetRefFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/content/assets/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  try {
    return (
      sanitizeContentAssetRef(
        pathname.slice(prefix.length),
      ) || ""
    );
  } catch {
    return "";
  }
}

function rawContentAssetRefFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/content/assets/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  return pathname.slice(prefix.length);
}

function contentPageNotFound(campaignSlug: string, pageRef: string) {
  return jsonError(
    "content_page_not_found",
    `Could not find content page '${pageRef}' in campaign '${campaignSlug}'.`,
    404,
    { campaign_slug: campaignSlug, page_ref: pageRef },
  );
}

function hardDeleteBlocked(pageRef: string, removalSafety: unknown) {
  return jsonError(
    "hard_delete_blocked",
    "Hard delete blocked for this content page.",
    409,
    {
      page_ref: pageRef,
      removal_safety: removalSafety,
      force_query_param: "force",
      force_required: true,
    },
  );
}

function contentAssetNotFound(campaignSlug: string, assetRef: string) {
  return jsonError(
    "content_asset_not_found",
    `Could not find content asset '${assetRef}' in campaign '${campaignSlug}'.`,
    404,
    { campaign_slug: campaignSlug, asset_ref: assetRef },
  );
}

function contentCharacterNotFound(campaignSlug: string, characterSlug: string) {
  return jsonError(
    "content_character_not_found",
    `Could not find content character '${characterSlug}' in campaign '${campaignSlug}'.`,
    404,
    { campaign_slug: campaignSlug, character_slug: characterSlug },
  );
}

function parseLiveRevisionHeader(ctx: { req: { header: (name: string) => string | undefined } }): number | null {
  const rawValue = ctx.req.header("X-Live-Revision")?.trim() || "";
  if (!rawValue) {
    return null;
  }
  const parsed = Number(rawValue);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function parseLiveViewTokenHeader(ctx: { req: { header: (name: string) => string | undefined } }): string {
  return ctx.req.header("X-Live-View-Token")?.trim() || "";
}

function parseBooleanFlag(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (value === null || value === undefined) {
    return false;
  }
  return ["1", "true", "yes", "on"].includes(String(value).trim().toLowerCase());
}

function inlineContentDisposition(filename: string): string {
  const sanitized = filename.replace(/[\r\n"]/g, "").trim() || "session-article-image";
  return `inline; filename="${sanitized}"`;
}

app.get(ROUTES.healthz, async (ctx) => {
  const campaigns = await listCampaignSlugs(config.campaignsDir);
  return ctx.json({
    status: "ok",
    environment: config.environment,
    runtime_mode: config.runtimeMode,
    campaign_count: campaigns.length,
    data: {
      campaigns_dir: config.campaignsDir,
    },
  });
});

app.get(ROUTES.appState, async (ctx) =>
  ctx.json({
    ok: true,
    app: {
      ...config.app,
      db_path: config.dbPath,
      campaigns_dir: config.campaignsDir,
    },
  }),
);

app.get(ROUTES.me, async (ctx) => {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    return ctx.json(buildApiTokenMePayload(config, apiAuth.context));
  }
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaigns = await listCampaigns(config);
  return ctx.json(buildFixtureMePayload(config, campaigns, role));
});

app.get(ROUTES.meSettings, async (ctx) => {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    return ctx.json(buildApiTokenAccountSettingsPayload(apiAuth.context));
  }
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildFixtureAccountSettingsPayload(role));
});

app.patch(ROUTES.meSettingsUpdate, async (ctx) => {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (apiAuth.kind !== "authenticated") {
    if (fixtureRole(ctx)) {
      const error = forbidden("Account settings updates require bearer API authentication.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateApiTokenAccountSettings(config.dbPath, apiAuth.context, jsonPayload.payload);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    user: apiAuth.context.user,
    preferences: result.preferences,
  });
});

app.get(ROUTES.systemsImportRuns, async (ctx) => {
  const auth = resolveAppAdminAuth(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const rawLimit = (ctx.req.query("limit") || "20").trim();
  const parsedLimit = Number(rawLimit);
  if (!Number.isInteger(parsedLimit)) {
    const error = validationError("limit must be an integer.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const importRuns = listSystemsImportRuns(config.dbPath, {
    librarySlug: (ctx.req.query("library_slug") || "").trim() || null,
    sourceId: (ctx.req.query("source_id") || "").trim() || null,
    limit: parsedLimit,
  });

  return ctx.json({
    ok: true,
    import_runs: importRuns,
  });
});

app.get(ROUTES.systemsImportRun, async (ctx) => {
  const auth = resolveAppAdminAuth(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const importRunId = parsePositiveInteger(ctx.req.param("importRunId") || "");
  if (importRunId === null) {
    const error = notFound("systems_import_run_not_found", "Could not find that Systems import run.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const importRun = getSystemsImportRun(config.dbPath, importRunId);
  if (!importRun) {
    const error = notFound("systems_import_run_not_found", "Could not find that Systems import run.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    import_run: importRun,
  });
});

async function systemsIndexResponse(ctx: Context) {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  return ctx.json({
    ok: true,
    ...buildCampaignSystemsIndexPayload(
      config.dbPath,
      campaign,
      campaignConfig?.config || {},
      role,
      ctx.req.query("q") || "",
      ctx.req.query("reference_q") || "",
    ),
  });
}

app.get(ROUTES.systemsIndex, systemsIndexResponse);
app.get(ROUTES.systemsSearch, systemsIndexResponse);

app.get(ROUTES.systemsSources, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  return ctx.json({
    ok: true,
    ...buildCampaignSystemsSourceListPayload(config.dbPath, campaign, campaignConfig?.config || {}, role),
  });
});

app.get(ROUTES.systemsSourceDetail, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = buildCampaignSystemsSourceDetailPayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    ctx.req.param("sourceId") || "",
    role,
    ctx.req.query("reference_q") || "",
  );
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = notFound("systems_source_not_found", "Could not find that Systems source.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    ...result.payload,
  });
});

app.get(ROUTES.systemsSourceCategory, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = buildCampaignSystemsSourceCategoryPayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    ctx.req.param("sourceId") || "",
    ctx.req.param("entryType") || "",
    role,
    ctx.req.query("q") || "",
  );
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = notFound("systems_source_category_not_found", "Could not find that Systems source category.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    ...result.payload,
  });
});

app.get(ROUTES.systemsEntryDetail, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = buildCampaignSystemsEntryDetailPayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    ctx.req.param("entrySlug") || "",
    role,
  );
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = notFound("systems_entry_not_found", "Could not find that Systems entry.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    ...result.payload,
  });
});

app.get(ROUTES.combatSystemsMonsterSearch, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = buildCombatSystemsMonsterSearchPayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    role,
    ctx.req.query("q") || "",
  );
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ok: true,
    ...result.payload,
  });
});

function combatUnchangedResponse(payload: { live_revision: number; live_view_token: string }) {
  return {
    ok: true,
    changed: false,
    live_revision: payload.live_revision,
    live_view_token: payload.live_view_token,
  };
}

app.get(ROUTES.combatState, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const payload = await buildCombatReadOnlyPayload(config, campaign, role);
  const requestedRevision = parseLiveRevisionHeader(ctx);
  const requestedViewToken = parseLiveViewTokenHeader(ctx);
  if (
    requestedRevision === payload.live_revision &&
    requestedViewToken.length > 0 &&
    requestedViewToken === payload.live_view_token
  ) {
    return ctx.json(combatUnchangedResponse(payload));
  }

  return ctx.json(payload);
});

app.get(ROUTES.combatLiveState, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const payload = await buildCombatReadOnlyPayload(config, campaign, role);
  const requestedRevision = parseLiveRevisionHeader(ctx);
  const requestedViewToken = parseLiveViewTokenHeader(ctx);
  if (
    requestedRevision === payload.live_revision &&
    requestedViewToken.length > 0 &&
    requestedViewToken === payload.live_view_token
  ) {
    return ctx.json(combatUnchangedResponse(payload));
  }

  return ctx.json(payload);
});

app.post(ROUTES.combatAdvanceTurn, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = advanceCombatTurn(config.dbPath, campaign.slug, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatClear, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = clearCombatTracker(config.dbPath, campaign.slug, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatPlayerCombatants, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = await addPlayerCombatant(config, campaign.slug, jsonPayload.payload, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatNpcCombatants, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = addNpcCombatant(config.dbPath, campaign.slug, jsonPayload.payload, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatStatblockCombatants, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = addStatblockCombatant(config.dbPath, campaign.slug, jsonPayload.payload, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatSystemsMonsters, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = addSystemsMonsterCombatant(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    jsonPayload.payload,
    actorUserId,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatSetCurrent, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = setCurrentCombatant(config.dbPath, campaign.slug, combatantId, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.patch(ROUTES.combatCombatantTurn, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCombatantTurn(config.dbPath, campaign.slug, combatantId, jsonPayload.payload, actorUserId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.patch(ROUTES.combatCombatantVitals, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = await updateCombatantVitals(
    config,
    campaign.slug,
    combatantId,
    jsonPayload.payload,
    actorUserId,
    auth.role,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.patch(ROUTES.combatCombatantResources, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCombatantResources(
    config.dbPath,
    campaign.slug,
    combatantId,
    jsonPayload.payload,
    actorUserId,
    auth.role,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.patch(ROUTES.combatCombatantNpcResources, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCombatantNpcResources(
    config.dbPath,
    campaign.slug,
    combatantId,
    jsonPayload.payload,
    actorUserId,
    auth.role,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.patch(ROUTES.combatCombatantPlayerDetailVisibility, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCombatantPlayerDetailVisibility(
    config.dbPath,
    campaign.slug,
    combatantId,
    jsonPayload.payload,
    actorUserId,
    auth.role,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.post(ROUTES.combatCombatantConditions, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = addCombatCondition(
    config.dbPath,
    campaign.slug,
    combatantId,
    jsonPayload.payload,
    actorUserId,
    auth.role,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.patch(ROUTES.combatConditionUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const conditionId = parsePositiveInteger(ctx.req.param("conditionId") || "");
  if (conditionId === null) {
    const error = validationError("Choose a valid condition.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const actorUserId = auth.actorUserId;
  if (typeof actorUserId !== "number") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCombatCondition(
    config.dbPath,
    campaign.slug,
    conditionId,
    jsonPayload.payload,
    actorUserId,
    auth.role,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.delete(ROUTES.combatCondition, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const conditionId = parsePositiveInteger(ctx.req.param("conditionId") || "");
  if (conditionId === null) {
    const error = validationError("Choose a valid condition.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = deleteCombatCondition(config.dbPath, campaign.slug, conditionId, auth.role);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.delete(ROUTES.combatCombatant, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCombatManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!supportsCombatTracker(campaign.system)) {
    const error = validationError(
      `Combat tracker support for ${campaign.system || "this system"} is not available yet.`,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const combatantId = parsePositiveInteger(ctx.req.param("combatantId") || "");
  if (combatantId === null) {
    const error = validationError("Choose a valid combatant.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = deleteCombatant(config.dbPath, campaign.slug, combatantId, auth.role);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "forbidden") {
    const error = forbidden(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildCombatReadOnlyPayload(config, campaign, auth.role));
});

app.get(ROUTES.campaignList, async (ctx) => {
  const campaigns = await listCampaigns(config);
  return ctx.json({
    ok: true,
    campaigns: campaigns.map((campaign) => ({
      campaign,
      role: "fixture_reader",
    })),
    auth: fixtureAuthBlock(),
  });
});

app.get(ROUTES.campaignDetail, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    return ctx.json(
      {
        ok: false,
        error: {
          code: "campaign_not_found",
          message: `Could not load campaign '${campaignSlug}' from fixture directory.`,
          details: {
            campaign_slug: campaignSlug,
            campaigns_dir: config.campaignsDir,
            runtime: "fixture_read_only",
          },
        },
      },
      404,
    );
  }

  return ctx.json({
    ok: true,
    campaign,
    role: "fixture_reader",
    auth_source: "fixture",
    visibility: {
      campaign_scope: "read_only_fixture",
      can_access_dm_content: false,
      can_manage_visibility: false,
    },
    auth: {
      mode: "fixture_read_only",
      message: "Read-only fixture mode is active; this surface does not evaluate live auth.",
    },
    permissions: readOnlyPermissions(),
    fixture_auth: fixtureAuthBlock(),
  });
});

app.get(ROUTES.campaignHelp, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildCampaignHelpPayload(campaign));
});

app.get(ROUTES.campaignControl, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignVisibilityManagerRole(ctx, campaign);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildCampaignControlPayload(config.dbPath, campaign, auth.role));
});

app.patch(ROUTES.campaignControlVisibility, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignVisibilityWriter(ctx, campaign);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const rawVisibility = jsonPayload.payload.visibility;
  if (!rawVisibility || typeof rawVisibility !== "object" || Array.isArray(rawVisibility)) {
    const error = validationError("Visibility settings must be provided as an object.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCampaignVisibilitySettings(
    config.dbPath,
    campaign,
    auth.role,
    auth.actorUserId,
    rawVisibility as Record<string, unknown>,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ...buildCampaignControlPayload(config.dbPath, campaign, auth.role),
    changed_scopes: result.changedScopes,
    message: result.changedScopes.length
      ? `Updated visibility for ${result.changedScopes.join(", ")}.`
      : "Visibility settings already matched those values.",
  });
});

app.get(ROUTES.wikiHome, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await campaignWikiRepository.getCampaign(campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const query = (ctx.req.query("q") || "").trim();
  const navigationPages = await campaignWikiRepository.searchPages(campaignSlug, "");
  const pages = query ? await campaignWikiRepository.searchPages(campaignSlug, query) : navigationPages;
  const grouped = groupPagesBySection(pages);
  const groupedSections = await Promise.all(
    sortSectionNames(grouped.keys()).map((sectionName) =>
      serializePublicWikiSectionGroup(campaign, sectionName, grouped.get(sectionName) || [], {
        assetsExist: (assetRef) => assetExists(campaign, assetRef),
      }),
    ),
  );

  const latestSessionSummaryPage = query
    ? null
    : await campaignWikiRepository.getLatestSessionSummaryPage(campaignSlug);
  const latestSessionSummary = latestSessionSummaryPage
    ? await serializePublicWikiPage(campaign, latestSessionSummaryPage, {
        includeImage: false,
        assetsExist: (assetRef) => assetExists(campaign, assetRef),
      })
    : null;

  return ctx.json({
    ok: true,
    campaign: serializeCampaign(campaign),
    frontend_mode: "gen2",
    can_view_wiki: true,
    wiki_visibility_label: "Public",
    query,
    result_count: pages.length,
    grouped_sections: groupedSections,
    overview_page: null,
    latest_session_summary: latestSessionSummary,
    message: "",
    section_navigation: serializeSectionNavigation(campaign, navigationPages),
    links: {
      flask_campaign_url: flaskCampaignHref(campaign.slug),
      campaign_url: campaignHref(campaign.slug),
      gen2_campaign_url: campaignHref(campaign.slug),
    },
  });
});

app.get(ROUTES.wikiSection, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const sectionSlug = ctx.req.param("sectionSlug") || "";
  const campaign = await campaignWikiRepository.getCampaign(campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pages = await campaignWikiRepository.getSectionPages(campaignSlug, sectionSlug);
  if (!pages.length) {
    const error = jsonError(
      "wiki_section_not_found",
      `Could not find wiki section '${sectionSlug}' in campaign '${campaignSlug}'.`,
      404,
      { campaign_slug: campaignSlug, section_slug: sectionSlug },
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const sectionName = pages[0]!.section;
  const navigationPages = await campaignWikiRepository.searchPages(campaignSlug, "");
  const splitPages = await splitPagesBySubsection(campaign, sectionName, pages, {
    assetsExist: (assetRef) => assetExists(campaign, assetRef),
  });

  return ctx.json({
    ok: true,
    campaign: serializeCampaign(campaign),
    frontend_mode: "gen2",
    section_name: sectionName,
    section_slug: sectionSlug,
    page_count: pages.length,
    pages: await serializePageList(campaign, pages),
    ...splitPages,
    section_navigation: serializeSectionNavigation(campaign, navigationPages),
    links: {
      flask_section_url: flaskCampaignHref(campaign.slug, `sections/${sectionSlug}`),
      campaign_url: campaignHref(campaign.slug),
      gen2_campaign_url: campaignHref(campaign.slug),
    },
  });
});

app.get(ROUTES.wikiPage, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const pageSlug = pageSlugFromWildcard(ctx.req.path, campaignSlug);
  const campaign = await campaignWikiRepository.getCampaign(campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const page = await campaignWikiRepository.getPage(campaignSlug, pageSlug);
  const bodyHtml = await campaignWikiRepository.getPageBodyHtml(campaignSlug, pageSlug);
  if (!page || bodyHtml === null) {
    const error = jsonError(
      "wiki_page_not_found",
      `Could not find wiki page '${pageSlug}' in campaign '${campaignSlug}'.`,
      404,
      { campaign_slug: campaignSlug, page_slug: pageSlug },
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const navigationPages = await campaignWikiRepository.searchPages(campaignSlug, "");
  const backlinks = await campaignWikiRepository.getBacklinks(campaignSlug, pageSlug);
  const pagePayload = await serializePublicWikiPage(campaign, page, {
    includeImage: true,
    assetsExist: (assetRef) => assetExists(campaign, assetRef),
  });
  return ctx.json({
    ok: true,
    campaign: serializeCampaign(campaign),
    frontend_mode: "gen2",
    page: {
      ...pagePayload,
      body_html: bodyHtml,
    },
    backlinks: await serializePageList(campaign, backlinks),
    section_navigation: serializeSectionNavigation(campaign, navigationPages),
    links: {
      flask_page_url: flaskCampaignHref(campaign.slug, `pages/${page.route_slug}`),
      campaign_url: campaignHref(campaign.slug),
      section_url: campaignHref(campaign.slug, `sections/${slugify(page.section)}`),
      gen2_campaign_url: campaignHref(campaign.slug),
      gen2_section_url: campaignHref(campaign.slug, `sections/${slugify(page.section)}`),
    },
  });
});

app.get(ROUTES.sessionState, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind === "invalid" || auth.kind === "forbidden") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = auth.kind === "authenticated" ? auth.role : null;
  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const payload = await buildSessionStatePayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    role,
    auth.kind === "authenticated" ? auth.actorUserId || null : null,
  );
  const requestedRevision = parseLiveRevisionHeader(ctx);
  const requestedViewToken = parseLiveViewTokenHeader(ctx);
  if (
    requestedRevision === payload.session_revision &&
    requestedViewToken.length > 0 &&
    requestedViewToken === payload.session_view_token
  ) {
    return ctx.json({
      ok: true,
      changed: false,
      session_revision: payload.session_revision,
      session_view_token: payload.session_view_token,
    });
  }

  return ctx.json(payload);
});

app.get(ROUTES.dmContentState, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (auth.role === "player") {
    const error = forbidden("You do not have access to this campaign scope.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const playerWikiPages = await campaignWikiRepository.listVisiblePages(campaign.slug);
  return ctx.json(buildDmContentPayload(config.dbPath, campaign, auth.role, playerWikiPages.length));
});

app.post(ROUTES.dmContentStatblockCreate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveDmContentBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = createDmContentStatblock(config.dbPath, campaign.slug, jsonPayload.payload, auth.actorUserId || 0);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, ...result.payload });
});

app.put(ROUTES.dmContentStatblockUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveDmContentBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const statblockId = parsePositiveInteger(ctx.req.param("statblockId") || "");
  if (!statblockId) {
    const error = validationError("That statblock could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateDmContentStatblock(config.dbPath, campaign.slug, statblockId, jsonPayload.payload, auth.actorUserId || 0);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, ...result.payload });
});

app.delete(ROUTES.dmContentStatblockDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveDmContentBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const statblockId = parsePositiveInteger(ctx.req.param("statblockId") || "");
  if (!statblockId) {
    const error = validationError("That statblock could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = deleteDmContentStatblock(config.dbPath, campaign.slug, statblockId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, ...result.payload });
});

app.post(ROUTES.dmContentConditionCreate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveDmContentBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = createDmContentCondition(config.dbPath, campaign.slug, jsonPayload.payload, auth.actorUserId || 0);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, ...result.payload });
});

app.put(ROUTES.dmContentConditionUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveDmContentBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const conditionDefinitionId = parsePositiveInteger(ctx.req.param("conditionDefinitionId") || "");
  if (!conditionDefinitionId) {
    const error = validationError("That custom condition could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateDmContentCondition(
    config.dbPath,
    campaign.slug,
    conditionDefinitionId,
    jsonPayload.payload,
    auth.actorUserId || 0,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, ...result.payload });
});

app.delete(ROUTES.dmContentConditionDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveDmContentBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const conditionDefinitionId = parsePositiveInteger(ctx.req.param("conditionDefinitionId") || "");
  if (!conditionDefinitionId) {
    const error = validationError("That custom condition could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = deleteDmContentCondition(config.dbPath, campaign.slug, conditionDefinitionId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, ...result.payload });
});

app.post(ROUTES.sessionStart, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (apiAuth.kind !== "authenticated") {
    if (fixtureRole(ctx)) {
      const error = forbidden("Session lifecycle writes require bearer API authentication.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = apiTokenRoleForCampaign(apiAuth.context, campaign.slug);
  if (role !== "dm" && role !== "admin") {
    const error = forbidden("You do not have permission to manage this session.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = startSession(config.dbPath, campaign, { id: apiAuth.context.user.id });
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    session: result.session,
  });
});

app.post(ROUTES.sessionClose, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (apiAuth.kind !== "authenticated") {
    if (fixtureRole(ctx)) {
      const error = forbidden("Session lifecycle writes require bearer API authentication.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = apiTokenRoleForCampaign(apiAuth.context, campaign.slug);
  if (role !== "dm" && role !== "admin") {
    const error = forbidden("You do not have permission to manage this session.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = closeSession(config.dbPath, campaign, { id: apiAuth.context.user.id });
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    session: result.session,
  });
});

app.post(ROUTES.sessionMessageCreate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (apiAuth.kind !== "authenticated") {
    if (fixtureRole(ctx)) {
      const error = forbidden("Session message writes require bearer API authentication.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = apiTokenRoleForCampaign(apiAuth.context, campaign.slug);
  if (!role) {
    const error = forbidden("You do not have access to this campaign scope.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await postSessionMessage(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    toFixtureSystemsRole(role),
    {
      id: apiAuth.context.user.id,
      display_name: apiAuth.context.user.display_name,
    },
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    message: result.message,
  });
});

app.post(ROUTES.sessionArticleCreate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(
    ctx,
    campaign.slug,
    "Session article writes require bearer API authentication.",
  );
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await createSessionArticle(
    config.dbPath,
    config.campaignsDir,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    { id: auth.actor.id },
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    article: result.article,
  });
});

app.put(ROUTES.sessionArticleUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(
    ctx,
    campaign.slug,
    "Session article writes require bearer API authentication.",
  );
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
  }

  const articleId = parsePositiveInteger(ctx.req.param("articleId") || "");
  if (articleId === null) {
    const error = validationError("That session article could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await updateSessionArticle(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    { id: auth.actor.id },
    articleId,
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    article: result.article,
  });
});

app.post(ROUTES.sessionArticleReveal, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(
    ctx,
    campaign.slug,
    "Session article writes require bearer API authentication.",
  );
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
  }

  const articleId = parsePositiveInteger(ctx.req.param("articleId") || "");
  if (articleId === null) {
    const error = validationError("That session article could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await revealSessionArticle(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actor,
    articleId,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    article: result.article,
    message: result.message,
  });
});

app.delete(ROUTES.sessionArticlesRevealedClear, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(
    ctx,
    campaign.slug,
    "Session article writes require bearer API authentication.",
  );
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await clearRevealedSessionArticles(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    { id: auth.actor.id },
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    deleted_articles: result.deletedArticles,
    deleted_article_ids: result.deletedArticleIds,
  });
});

app.delete(ROUTES.sessionArticleDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(
    ctx,
    campaign.slug,
    "Session article writes require bearer API authentication.",
  );
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
  }

  const articleId = parsePositiveInteger(ctx.req.param("articleId") || "");
  if (articleId === null) {
    const error = validationError("That session article could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await deleteSessionArticle(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    { id: auth.actor.id },
    articleId,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    article: result.article,
  });
});

app.get(ROUTES.sessionArticleImage, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const articleId = parsePositiveInteger(ctx.req.param("articleId") || "");
  if (articleId === null) {
    const error = notFound("session_article_image_not_found", "Could not find that session article image.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = readSessionArticleImage(config.dbPath, campaign.slug, articleId, role);
  if (result.status === "not_found") {
    const error = notFound("session_article_image_not_found", "Could not find that session article image.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return new Response(result.data, {
    status: 200,
    headers: {
      "Content-Type": result.mediaType,
      "Content-Disposition": inlineContentDisposition(result.filename),
      "Content-Length": String(result.data.byteLength),
    },
  });
});

app.get(ROUTES.sessionLogDetail, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;
  if (role === "player") {
    const error = forbidden("You do not have permission to manage this session.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const sessionId = parsePositiveInteger(ctx.req.param("sessionId") || "");
  if (sessionId === null) {
    const error = notFound("session_log_not_found", "Could not find that session log.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await buildSessionLogDetailPayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    sessionId,
    role,
  );
  if (result.status === "not_found") {
    const error = notFound("session_log_not_found", "Could not find that session log.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(result.payload);
});

app.delete(ROUTES.sessionLogDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(ctx, campaign.slug, "Session log writes require bearer API authentication.");
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
  }

  const sessionId = parsePositiveInteger(ctx.req.param("sessionId") || "");
  if (sessionId === null) {
    const error = validationError("That chat log could not be found.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = deleteSessionLog(config.dbPath, campaign, { id: auth.actor.id }, sessionId);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    deleted_session_id: result.deletedSessionId,
  });
});

app.get(ROUTES.sessionArticleSourceSearch, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const role = auth.role;

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = await buildSessionArticleSourceSearchPayload(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    role,
    ctx.req.query("q") || "",
  );
  if (result.status === "forbidden") {
    const error = forbidden(result.message || "You do not have permission to manage this session.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    ...result.payload,
  });
});

app.get(ROUTES.campaignConfig, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaignConfig = await getCampaignConfigFile(config, campaignSlug);
  if (!campaignConfig) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaignSlug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildCampaignConfigPayload(campaignConfig));
});

app.patch(ROUTES.campaignConfigUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaignConfig = await getCampaignConfigFile(config, campaignSlug);
  if (!campaignConfig) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaignConfig.campaign_slug,
    "Content config writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updates =
    typeof jsonPayload.payload.config === "object" &&
    jsonPayload.payload.config !== null &&
    !Array.isArray(jsonPayload.payload.config)
      ? jsonPayload.payload.config
      : jsonPayload.payload;
  const result = await updateCampaignConfigFile(config, campaignConfig.campaign_slug, updates);
  if (result.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildCampaignConfigPayload(result.record));
});

app.get(ROUTES.contentAssets, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const assets = await listCampaignContentAssets(config, campaignSlug);
  if (!assets) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentAssetListPayload(campaignSlug, assets));
});

app.get(ROUTES.contentAsset, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const assetRef = contentAssetRefFromWildcard(ctx.req.path, campaignSlug);
  if (!assetRef) {
    const error = contentAssetNotFound(campaignSlug, assetRef);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const asset = await getCampaignContentAsset(config, campaignSlug, assetRef);
  if (!asset) {
    const error = contentAssetNotFound(campaignSlug, assetRef);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentAssetDetailPayload(campaignSlug, asset));
});

app.put(ROUTES.contentAssetUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaign.slug,
    "Content asset writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const assetRef = rawContentAssetRefFromWildcard(ctx.req.path, campaignSlug);
  const result = await writeCampaignContentAsset(config, campaign.slug, assetRef, jsonPayload.payload);
  if (result.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentAssetWritePayload(campaign.slug, result.record));
});

app.delete(ROUTES.contentAssetDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaign.slug,
    "Content asset writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const assetRef = rawContentAssetRefFromWildcard(ctx.req.path, campaignSlug);
  const result = await deleteCampaignContentAsset(config, campaign.slug, assetRef);
  if (result.status === "not_found") {
    const sanitizedAssetRef = sanitizeContentAssetRef(assetRef) || assetRef;
    const error = contentAssetNotFound(campaign.slug, sanitizedAssetRef);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentAssetDeletePayload(result.record));
});

app.get(ROUTES.contentPages, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pages = await listCampaignContentPages(config, campaignSlug);
  if (!pages) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const removalSafety = buildCampaignContentPageRemovalSafety(pages);
  return ctx.json(buildContentPageListPayload(pages, removalSafety));
});

app.get(ROUTES.contentPage, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pageRef = contentPageRefFromWildcard(ctx.req.path, campaignSlug);
  if (!pageRef) {
    const error = contentPageNotFound(campaignSlug, pageRef);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const page = await getCampaignContentPage(config, campaignSlug, pageRef);
  if (!page) {
    const error = contentPageNotFound(campaignSlug, pageRef);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pages = await listCampaignContentPages(config, campaignSlug);
  const removalSafety = pages ? buildCampaignContentPageRemovalSafety(pages) : {};
  return ctx.json(buildContentPageDetailPayload(page, removalSafety[page.page_ref]));
});

app.put(ROUTES.contentPageUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaign.slug,
    "Content page writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pageRef = rawContentPageRefFromWildcard(ctx.req.path, campaignSlug);
  const result = await writeCampaignContentPage(config, campaign.slug, pageRef, jsonPayload.payload);
  if (result.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentPageDetailPayload(result.record, result.removalSafety[result.record.page_ref]));
});

app.delete(ROUTES.contentPageDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaign.slug,
    "Content page writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pageRef = rawContentPageRefFromWildcard(ctx.req.path, campaignSlug);
  const existing = await getCampaignContentPage(config, campaign.slug, pageRef);
  if (!existing) {
    const sanitizedPageRef = sanitizeContentPageRef(pageRef) || pageRef;
    const error = contentPageNotFound(campaign.slug, sanitizedPageRef);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pages = await listCampaignContentPages(config, campaign.slug);
  const removalSafety = pages ? buildCampaignContentPageRemovalSafety(pages) : {};
  const pageSafety = removalSafety[existing.page_ref];

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const force =
    parseBooleanFlag(new URL(ctx.req.url).searchParams.get("force")) ||
    parseBooleanFlag(jsonPayload.payload.force);

  if (pageSafety && !force && !pageSafety.can_hard_delete) {
    const error = hardDeleteBlocked(existing.page_ref, pageSafety);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = await deleteCampaignContentPage(config, campaign.slug, existing.page_ref);
  if (result.status === "not_found") {
    const error = contentPageNotFound(campaign.slug, existing.page_ref);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentPageDeletePayload(result.record));
});

app.get(ROUTES.contentCharacters, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characters = await listCampaignContentCharacters(config, campaignSlug);
  if (!characters) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentCharacterListPayload(characters));
});

app.get(ROUTES.contentCharacter, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaignSlug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaignSlug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaignSlug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentCharacterDetailPayload(character));
});

app.put(ROUTES.contentCharacterUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaign.slug,
    "Content character writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = await writeCampaignContentCharacter(
    config,
    campaign.slug,
    ctx.req.param("characterSlug") || "",
    jsonPayload.payload,
  );
  if (result.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentCharacterDetailPayload(result.record));
});

app.delete(ROUTES.contentCharacterDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveContentManagerBearerWrite(
    ctx,
    campaign.slug,
    "Content character writes require bearer API authentication.",
  );
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = await deleteCampaignContentCharacter(
    config,
    campaign.slug,
    ctx.req.param("characterSlug") || "",
  );
  if (result.status === "not_found") {
    const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentCharacterDeletePayload(result.deleted));
});

app.get(ROUTES.characterRestPreview, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to use rest actions for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = previewCharacterRest(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("restType") || "",
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    preview: result.preview,
  });
});

app.post(ROUTES.characterSessionRest, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = applyCharacterSessionRest(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("restType") || "",
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionVitals, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionVitals(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionResource, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionResource(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("resourceId") || "",
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionSpellSlots, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionSpellSlots(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("level") || "",
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionInventory, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionInventory(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("itemId") || "",
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionXianxiaActiveState, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionXianxiaActiveState(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionCurrency, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionCurrency(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionNotes, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionNotes(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionPersonal, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters")) {
    const error = forbidden("You do not have access to this campaign scope.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionPersonal(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionFeatureState, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionFeatureState(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("featureKey") || "",
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.patch(ROUTES.characterSessionXianxiaInventoryEquipped, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveCharacterSessionBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const characterSlug = sanitizeContentCharacterSlug(ctx.req.param("characterSlug") || "") || "";
  if (!characterSlug) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const character = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!character) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to update this character from this view.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionXianxiaInventoryEquipped(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    ctx.req.param("itemId") || "",
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (result.status === "state_conflict") {
    const error = stateConflict(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedCharacter = await getCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (!updatedCharacter) {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: updatedCharacter.definition,
      import_metadata: updatedCharacter.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
  });
});

app.notFound((ctx) =>
  ctx.json(
    {
      ok: false,
      error: {
        code: "not_found",
        message: "The requested endpoint does not exist in fixture mode.",
        details: {
          runtime: "fixture_read_only",
        },
      },
    },
    404,
  ),
);

const port = Number(process.env.PORT || 3000);
const startup = async () => {
  const server = serve({
    fetch: app.fetch,
    port,
  });
  return server;
};

function isMainModule(): boolean {
  const entrypoint = process.argv[1];
  if (!entrypoint) {
    return false;
  }
  return path.resolve(entrypoint) === fileURLToPath(import.meta.url);
}

if (isMainModule()) {
  startup().then(() => {
    console.info(`[campaign-player-wiki-typescript-api] listening on :${port}`);
  });
}

export function getApp() {
  return app;
}

export { startup };
export default app;
