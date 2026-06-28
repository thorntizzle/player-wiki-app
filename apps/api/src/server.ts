import path from "node:path";
import { promises as fs } from "node:fs";
import { fileURLToPath } from "node:url";

import { Hono, type Context } from "hono";
import { serve } from "@hono/node-server";
import { deleteCookie, getCookie, setCookie } from "hono/cookie";

import { buildAdminDashboardPayload, buildAdminUserDetailPayload } from "./admin/view.js";
import {
  apiTokenRoleForCampaign,
  createUser,
  deleteCharacterAssignment,
  deleteUser,
  disableUser,
  enableUser,
  getActiveUserById,
  getCharacterAssignment,
  getMembership,
  getUserByEmail,
  getUserById,
  hasActivePlayerMembership,
  insertAuthAuditLog,
  issueInviteToken,
  issuePasswordResetToken,
  listActiveMembershipsForUser,
  listActivePlayerMembershipUsers,
  readApiTokenAuthContext,
  revokeAllUserApiTokens,
  revokeAllUserSessions,
  upsertCharacterAssignment,
  upsertMembership,
  updateApiTokenAccountSettings,
  type ApiTokenAuthContext,
  type AuthMembership,
  type AuthRouteRole,
  type AuthUser,
  type CharacterAssignment,
} from "./auth/repository.js";
import {
  buildApiTokenAccountSettingsPayload,
  buildApiTokenMePayload,
  buildApiTokenViewAsState,
  buildFixtureAccountSettingsPayload,
  buildFixtureMePayload,
} from "./auth/view.js";
import { getApiConfig } from "./config.js";
import { assertSqliteStartupSchema } from "./sqlite.js";
import {
  buildCampaignControlPayload,
  campaignRoleCanAccessScope,
  campaignRoleCanManageVisibility,
  campaignScopeIsPublic,
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
import { importDnd5eSystemsArchive } from "./systems/dndImport.js";
import { getSystemsImportRun, listSystemsImportRuns } from "./systems/importRuns.js";
import {
  archiveCustomSystemsEntry,
  buildDmContentSystemsPayload,
  createCustomSystemsEntry,
  importCampaignItemMechanics,
  restoreCustomSystemsEntry,
  updateCustomSystemsEntry,
} from "./systems/management.js";
import {
  buildCombatSystemsMonsterSearchPayload,
  buildCampaignSystemsEntryDetailPayload,
  buildCampaignSystemsIndexPayload,
  buildCampaignSystemsSourceCategoryPayload,
  buildCampaignSystemsSourceDetailPayload,
  buildCampaignSystemsSourceListPayload,
  entryTypeLabel,
  updateCampaignSystemsEntryOverride,
  updateCampaignSystemsSources,
  type FixtureSystemsRole,
} from "./systems/sources.js";
import {
  advancedEditorUnsupportedMessage,
  applyCharacterAdvancedEditorReferenceUpdate,
  applyCharacterCultivationAction,
  applyCharacterLevelUpUpdate,
  applyCharacterProgressionRepairUpdate,
  applyCharacterRetrainingUpdate,
  buildCharacterAdvancedEditorPayload,
  buildCharacterAdvancementShellPayload,
  buildCharacterAuthoringLinks,
  buildCharacterCultivationShellPayload,
  buildCharacterLevelUpPayload,
  buildCharacterProgressionRepairPayload,
  buildCharacterRetrainingPayload,
  buildDndCharacterCreateContext,
  buildDndCreateCharacter,
  buildXianxiaCreateCharacter,
  listAdvancedEditorOptionalFeatureRows,
  listAdvancedEditorSpellRows,
  listXianxiaCultivationGenericTechniqueRows,
  listXianxiaCultivationMartialArtRows,
  listXianxiaCreateGenericTechniqueOptions,
  buildXianxiaManualImportCharacter,
  buildXianxiaManualImportContext,
  characterAdvancedEditorIsSupported,
  characterCultivationIsSupported,
  listXianxiaManualImportMartialArtOptions,
  nativeCharacterCreateLane,
  nativeCharacterCreateUnsupportedMessage,
  xianxiaKnownGenericTechniqueOptionKeys,
} from "./content/characterAuthoring.js";
import { getCampaignConfigFile } from "./content/repository.js";
import {
  buildCampaignContentPageRemovalSafety,
  createCampaignContentCharacter,
  deleteCampaignContentAsset,
  deleteCampaignContentCharacter,
  deleteCampaignContentCharacterPortrait,
  deleteCampaignContentPage,
  getCampaignContentAsset,
  getCampaignContentCharacter,
  getCampaignContentPage,
  listCampaignContentAssets,
  listCampaignContentCharacters,
  listCampaignContentPages,
  readCampaignProtectedAsset,
  sanitizeContentAssetRef,
  sanitizeContentCharacterSlug,
  sanitizeContentPageRef,
  updateCampaignConfigFile,
  validateCampaignContentCharacterPortraitUpload,
  writeCampaignCharacterDefinitionFile,
  writeCampaignContentAsset,
  writeCampaignContentCharacter,
  writeCampaignContentCharacterPortrait,
  writeCampaignContentPage,
} from "./content/repository.js";
import {
  applyCharacterSessionRest,
  canEditCharacterSessionState,
  previewCharacterRest,
  readCharacterStateSnapshot,
  updateCharacterAdvancedEditorReferenceState,
  updateCharacterCultivationDefinitionState,
  updateCharacterLevelUpDefinitionState,
  updateCharacterSheetEdit,
  updateCharacterPortraitRevision,
  updateCharacterSessionArtificerInfusions,
  updateCharacterSessionCurrency,
  updateCharacterSessionEquipment,
  updateCharacterSessionFeatureState,
  updateCharacterSessionInventory,
  updateCharacterSessionNotes,
  updateCharacterSessionPersonal,
  updateCharacterSessionResource,
  updateCharacterSessionSpellSlots,
  updateCharacterSessionXianxiaActiveState,
  updateCharacterSessionXianxiaDaoImmolatingUseRecord,
  updateCharacterSessionXianxiaDaoImmolatingUseRequest,
  updateCharacterSessionXianxiaInventoryAdd,
  updateCharacterSessionXianxiaInventoryEquipped,
  updateCharacterSessionXianxiaInventoryItem,
  updateCharacterSessionXianxiaInventoryRemove,
  updateCharacterSessionVitals,
} from "./content/characterState.js";
import {
  buildCampaignConfigPayload,
  type CharacterDetailLinkedSystemsEntry,
  buildCharacterDetailPayload,
  buildCharacterRosterPayload,
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
import type { CampaignCharacterFileRecord } from "./content/types.js";
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

const VIEW_AS_COOKIE_NAME = "cpw_view_as_user_id";
const VIEW_AS_COOKIE_OPTIONS = {
  httpOnly: true,
  path: "/",
  sameSite: "Lax" as const,
};
const VIEW_AS_SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const VIEW_AS_READ_ONLY_MESSAGE = "View As mode is read-only for campaign API writes. Exit View As before making changes.";

type ViewAsResolution = {
  activeUser: AuthUser | null;
  memberships: AuthMembership[];
  shouldClearCookie: boolean;
};

type ApiTokenCampaignIdentity = {
  role: AuthRouteRole;
  user: AuthUser;
  authSource: "api_token" | "view_as";
};

function utcIsoTimestamp(value: Date = new Date()): string {
  const normalized = new Date(value);
  normalized.setMilliseconds(0);
  return normalized.toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

function buildManagedCharacterImportMetadata(
  campaignSlug: string,
  characterSlug: string,
  currentImportMetadata: Record<string, unknown>,
): Record<string, unknown> {
  return {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    source_path:
      typeof currentImportMetadata.source_path === "string" && currentImportMetadata.source_path.trim().length > 0
        ? currentImportMetadata.source_path.trim()
        : `managed://${campaignSlug}/${characterSlug}`,
    imported_at_utc: utcIsoTimestamp(),
    parser_version: "2026-04-21.01",
    import_status: "managed",
    warnings: [],
  };
}

function buildPreservedCharacterImportMetadata(
  campaignSlug: string,
  characterSlug: string,
  currentImportMetadata: Record<string, unknown>,
): Record<string, unknown> {
  return {
    ...currentImportMetadata,
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    source_path:
      typeof currentImportMetadata.source_path === "string" && currentImportMetadata.source_path.trim().length > 0
        ? currentImportMetadata.source_path.trim()
        : `managed://${campaignSlug}/${characterSlug}`,
    imported_at_utc:
      typeof currentImportMetadata.imported_at_utc === "string" && currentImportMetadata.imported_at_utc.trim().length > 0
        ? currentImportMetadata.imported_at_utc.trim()
        : utcIsoTimestamp(),
    parser_version:
      typeof currentImportMetadata.parser_version === "string" && currentImportMetadata.parser_version.trim().length > 0
        ? currentImportMetadata.parser_version.trim()
        : "api-v1",
    import_status:
      typeof currentImportMetadata.import_status === "string" && currentImportMetadata.import_status.trim().length > 0
        ? currentImportMetadata.import_status.trim()
        : "managed",
    warnings: Array.isArray(currentImportMetadata.warnings) ? currentImportMetadata.warnings : [],
  };
}

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

function requestedViewAsUserId(ctx: Context): number | null {
  const parsed = parsePositiveInteger(String(getCookie(ctx, VIEW_AS_COOKIE_NAME) || ""));
  return parsed === null ? null : parsed;
}

function setRequestedViewAsUserId(ctx: Context, userId: number): void {
  setCookie(ctx, VIEW_AS_COOKIE_NAME, String(userId), VIEW_AS_COOKIE_OPTIONS);
}

function clearRequestedViewAsUserId(ctx: Context): void {
  deleteCookie(ctx, VIEW_AS_COOKIE_NAME, VIEW_AS_COOKIE_OPTIONS);
}

function resolveViewAsState(ctx: Context, authContext: ApiTokenAuthContext): ViewAsResolution {
  const requestedUserId = requestedViewAsUserId(ctx);
  if (requestedUserId === null) {
    return { activeUser: null, memberships: [], shouldClearCookie: false };
  }
  if (!authContext.user.is_admin) {
    return { activeUser: null, memberships: [], shouldClearCookie: true };
  }
  const targetUser = getActiveUserById(config.dbPath, requestedUserId);
  if (!targetUser) {
    return { activeUser: null, memberships: [], shouldClearCookie: true };
  }
  return {
    activeUser: targetUser,
    memberships: listActiveMembershipsForUser(config.dbPath, targetUser.id),
    shouldClearCookie: false,
  };
}

function applyViewAsCookieState(ctx: Context, state: ViewAsResolution): void {
  if (state.shouldClearCookie) {
    clearRequestedViewAsUserId(ctx);
  }
}

function viewAsRoleForCampaign(memberships: AuthMembership[], campaignSlug: string): AuthRouteRole | null {
  const membership = memberships.find((item) => item.campaign_slug === campaignSlug && item.status === "active");
  if (membership?.role === "dm" || membership?.role === "player") {
    return membership.role;
  }
  return null;
}

function apiTokenCampaignIdentity(
  ctx: Context,
  authContext: ApiTokenAuthContext,
  campaignSlug: string,
): ApiTokenCampaignIdentity | null {
  const viewAs = resolveViewAsState(ctx, authContext);
  applyViewAsCookieState(ctx, viewAs);
  if (viewAs.activeUser) {
    if (viewAs.activeUser.is_admin) {
      return { role: "admin", user: viewAs.activeUser, authSource: "view_as" };
    }
    const viewAsRole = viewAsRoleForCampaign(viewAs.memberships, campaignSlug);
    return viewAsRole ? { role: viewAsRole, user: viewAs.activeUser, authSource: "view_as" } : null;
  }

  const role = apiTokenRoleForCampaign(authContext, campaignSlug);
  return role ? { role, user: authContext.user, authSource: "api_token" } : null;
}

function viewAsReadOnlyError() {
  return {
    ok: false,
    error: {
      code: "view_as_read_only",
      message: VIEW_AS_READ_ONLY_MESSAGE,
      details: {},
    },
    status: 403 as const,
  };
}

const viewAsReadOnlyGuard = async (ctx: Context, next: () => Promise<void>) => {
  if (VIEW_AS_SAFE_METHODS.has(ctx.req.method.toUpperCase())) {
    await next();
    return;
  }
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind !== "authenticated") {
    await next();
    return;
  }
  const viewAs = resolveViewAsState(ctx, apiAuth.context);
  applyViewAsCookieState(ctx, viewAs);
  if (viewAs.activeUser) {
    const error = viewAsReadOnlyError();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  await next();
};

app.use("/api/v1/campaigns", viewAsReadOnlyGuard);
app.use("/api/v1/campaigns/*", viewAsReadOnlyGuard);

type RoleResolution =
  | {
      kind: "authenticated";
      role: FixtureSystemsRole;
      actorUserId?: number;
      actorDisplayName?: string;
      actorUser?: AuthUser;
      authSource?: "api_token" | "view_as";
    }
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "forbidden"; message: string };

type CampaignVisibilityWriteResolution =
  | { kind: "authenticated"; role: FixtureSystemsRole; actorUserId: number }
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "forbidden"; message: string };

type CharacterControlsWriteResolution =
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

function writeResolutionError(result: { kind: "missing" } | { kind: "invalid" } | { kind: "forbidden"; message: string }) {
  if (result.kind === "forbidden") {
    return forbidden(result.message);
  }
  return authRequired();
}

function toFixtureSystemsRole(role: AuthRouteRole): FixtureSystemsRole {
  return role;
}

function isServerRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function collectCharacterSystemsRefSlugs(value: unknown, slugs = new Set<string>()): Set<string> {
  if (Array.isArray(value)) {
    for (const item of value) {
      collectCharacterSystemsRefSlugs(item, slugs);
    }
    return slugs;
  }
  if (!isServerRecord(value)) {
    return slugs;
  }

  const systemsRef = value.systems_ref;
  if (isServerRecord(systemsRef)) {
    const slug = typeof systemsRef.slug === "string" ? systemsRef.slug.trim() : "";
    if (slug) {
      slugs.add(slug);
    }
  }

  for (const item of Object.values(value)) {
    collectCharacterSystemsRefSlugs(item, slugs);
  }
  return slugs;
}

function isOptionalSqliteReadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error || "");
  return /no such (table|column)/i.test(message);
}

function buildCharacterDetailSystemsEntriesBySlug({
  campaign,
  campaignConfig,
  role,
  slugs,
}: {
  campaign: CampaignViewModel;
  campaignConfig: Record<string, unknown>;
  role: FixtureSystemsRole;
  slugs: Set<string>;
}): Map<string, CharacterDetailLinkedSystemsEntry> {
  const entriesBySlug = new Map<string, CharacterDetailLinkedSystemsEntry>();
  for (const rawSlug of slugs) {
    const slug = rawSlug.trim();
    if (!slug) {
      continue;
    }
    try {
      const result = buildCampaignSystemsEntryDetailPayload(config.dbPath, campaign, campaignConfig, slug, role);
      if (result.status !== "ok") {
        continue;
      }
      const entry = result.payload.entry;
      const linkedEntry = {
        slug: entry.slug,
        title: entry.title,
        entry_type: entry.entry_type,
        metadata: entry.metadata,
        rendered_html: entry.rendered_html,
      };
      entriesBySlug.set(slug.toLowerCase(), linkedEntry);
      entriesBySlug.set(entry.slug.toLowerCase(), linkedEntry);
    } catch (error) {
      // Optional linked presenter enrichment should not block character detail on old local DBs.
      if (!isOptionalSqliteReadError(error)) {
        throw error;
      }
    }
  }
  return entriesBySlug;
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

function resolveCampaignRole(ctx: Context, campaignSlug: string): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const identity = apiTokenCampaignIdentity(ctx, apiAuth.context, campaignSlug);
    if (!identity) {
      return { kind: "forbidden", message: "You do not have access to this campaign scope." };
    }
    return {
      kind: "authenticated",
      role: toFixtureSystemsRole(identity.role),
      actorUserId: identity.user.id,
      actorDisplayName: identity.user.display_name,
      authSource: identity.authSource,
    };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  const role = fixtureRole(ctx);
  return role ? { kind: "authenticated", role } : { kind: "missing" };
}

function resolveContentManagerRole(
  ctx: Context,
  campaignSlug: string,
): RoleResolution {
  const forbiddenMessage = "You do not have permission to manage campaign content.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const identity = apiTokenCampaignIdentity(ctx, apiAuth.context, campaignSlug);
    if (identity?.role === "admin" || identity?.role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(identity.role) };
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

function resolveCharacterControlsAssignmentWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
): CharacterControlsWriteResolution {
  const message = "You do not have permission to assign character owners.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    if (apiAuth.context.user.is_admin) {
      return { kind: "authenticated", role: "admin", actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message };
  }
  return { kind: "missing" };
}

function resolveCharacterControlsDeleteWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): CharacterControlsWriteResolution {
  const message = "You do not have permission to delete this character.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role === "admin" || role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message };
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

function resolveSystemsManagerBearerWrite(
  ctx: { req: { header: (name: string) => string | undefined } },
  campaignSlug: string,
): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const role = apiTokenRoleForCampaign(apiAuth.context, campaignSlug);
    if (role === "admin" || role === "dm") {
      return { kind: "authenticated", role: toFixtureSystemsRole(role), actorUserId: apiAuth.context.user.id };
    }
    return { kind: "forbidden", message: "You do not have permission to manage systems." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: "Systems source updates require bearer API authentication." };
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
  ctx: Context,
  campaign: CampaignViewModel,
): RoleResolution {
  const forbiddenMessage = "You do not have permission to manage campaign visibility.";
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    const identity = apiTokenCampaignIdentity(ctx, apiAuth.context, campaign.slug);
    if (identity && campaignRoleCanManageVisibility(config.dbPath, campaign, identity.role)) {
      return { kind: "authenticated", role: toFixtureSystemsRole(identity.role) };
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
      return {
        kind: "authenticated",
        role: "admin",
        actorUserId: apiAuth.context.user.id,
        actorDisplayName: apiAuth.context.user.display_name,
        actorUser: apiAuth.context.user,
      };
    }
    return { kind: "forbidden", message: "You do not have permission to use the admin API." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  return fixtureRole(ctx) === "admin" ? { kind: "authenticated", role: "admin" } : { kind: "missing" };
}

function resolveAppAdminBearerWrite(ctx: { req: { header: (name: string) => string | undefined } }): RoleResolution {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "authenticated") {
    if (apiAuth.context.user.is_admin) {
      return {
        kind: "authenticated",
        role: "admin",
        actorUserId: apiAuth.context.user.id,
        actorDisplayName: apiAuth.context.user.display_name,
        actorUser: apiAuth.context.user,
      };
    }
    return { kind: "forbidden", message: "You do not have permission to use the admin API." };
  }
  if (apiAuth.kind === "invalid") {
    return { kind: "invalid" };
  }

  if (fixtureRole(ctx)) {
    return { kind: "forbidden", message: "Admin membership updates require bearer API authentication." };
  }
  return { kind: "missing" };
}

function parsePositiveInteger(rawValue: string): number | null {
  const parsed = Number(rawValue.trim());
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function requestedCombatantFocusId(ctx: Context): number | null {
  return parsePositiveInteger(ctx.req.query("combatant") || "");
}

function campaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function flaskCampaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}

function escapeHtml(rawValue: unknown): string {
  return String(rawValue ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function pageContextLabel(page: WikiPageRecord): string {
  return [page.section, page.subsection].map((part) => part.trim()).filter(Boolean).join(" / ");
}

function pageMetaLabel(page: WikiPageRecord): string {
  return [page.section, page.subsection, page.display_type.replace(/\b\w/g, (char) => char.toUpperCase())]
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" / ");
}

function browserCompatibilityUnavailableHtml(message: string, className: string, includeModifier = true): string {
  const classes = includeModifier ? `${className} ${className}--empty` : className;
  return `<div class="${classes}"><p class="meta">${escapeHtml(message)}</p></div>`;
}

function browserGlobalPreviewHtml({
  kindLabel,
  title,
  meta,
  summary,
  url,
  bodyHtml,
  imageUrl = "",
  imageAlt = "",
  imageCaption = "",
}: {
  kindLabel: string;
  title: string;
  meta: string;
  summary: string;
  url: string;
  bodyHtml: string;
  imageUrl?: string;
  imageAlt?: string;
  imageCaption?: string;
}): string {
  const summaryHtml = summary ? `<p class="lede">${escapeHtml(summary)}</p>` : "";
  const metaHtml = meta ? `<p class="meta">${escapeHtml(meta)}</p>` : "";
  const imageHtml = imageUrl
    ? `<figure class="article-figure"><img class="article-image" src="${escapeHtml(imageUrl)}" alt="${escapeHtml(
        imageAlt || title,
      )}">${
        imageCaption ? `<figcaption class="meta article-image__caption">${escapeHtml(imageCaption)}</figcaption>` : ""
      }</figure>`
    : "";
  return `<article class="campaign-global-search-preview"><header class="campaign-global-search-preview__header"><p class="eyebrow">${escapeHtml(
    kindLabel,
  )}</p><h3>${escapeHtml(title)}</h3>${metaHtml}${summaryHtml}<p><a class="button-link" href="${escapeHtml(
    url,
  )}">Open dedicated page</a></p></header>${imageHtml}<div class="article-body article-body--compact">${bodyHtml}</div></article>`;
}

function browserSessionWikiPreviewHtml({
  page,
  url,
  bodyHtml,
  imageUrl = "",
}: {
  page: WikiPageRecord;
  url: string;
  bodyHtml: string;
  imageUrl?: string;
}): string {
  const summaryHtml =
    page.summary && !["item", "spell", "mechanic"].includes(page.page_type)
      ? `<p class="lede">${escapeHtml(page.summary)}</p>`
      : "";
  const imageHtml = imageUrl
    ? `<figure class="article-figure"><img class="article-image" src="${escapeHtml(imageUrl)}" alt="${escapeHtml(
        page.image_alt || page.title,
      )}">${
        page.image_caption
          ? `<figcaption class="meta article-image__caption">${escapeHtml(page.image_caption)}</figcaption>`
          : ""
      }</figure>`
    : "";
  return `<section class="session-wiki-lookup-result"><header class="session-wiki-lookup-result__header"><p class="eyebrow">Wiki article</p><h3>${escapeHtml(
    page.title,
  )}</h3><p class="meta">${escapeHtml(pageMetaLabel(page))}</p>${summaryHtml}<p class="meta"><a href="${escapeHtml(
    url,
  )}" target="_blank" rel="noopener noreferrer">Open full article in a new tab</a></p></header>${imageHtml}<div class="article-body article-body--compact">${bodyHtml}</div></section>`;
}

function resolveBrowserScopeAccess(
  ctx: Context,
  campaign: CampaignViewModel,
  scope: "campaign" | "wiki" | "systems" | "session",
): RoleResolution | { kind: "public" } {
  const auth = resolveCampaignRole(ctx, campaign.slug);
  if (auth.kind === "authenticated") {
    return campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, scope)
      ? auth
      : { kind: "forbidden", message: "You do not have access to this campaign scope." };
  }
  if (auth.kind === "invalid") {
    return auth;
  }
  return campaignScopeIsPublic(config.dbPath, campaign, scope) ? { kind: "public" } : auth;
}

function browserAccessError(result: Exclude<ReturnType<typeof resolveBrowserScopeAccess>, { kind: "authenticated" } | { kind: "public" }>) {
  if (result.kind === "forbidden") {
    return forbidden(result.message);
  }
  return authRequired();
}

function supportsCharacterControlsRoutes(_system: unknown): boolean {
  return true;
}

function requestQueryValues(ctx: Context): Record<string, string> {
  const searchParams = new URL(ctx.req.url).searchParams;
  return Object.fromEntries(Array.from(searchParams.entries()).map(([key, value]) => [key, value]));
}

const XIANXIA_CREATE_ATTRIBUTE_KEYS = ["str", "dex", "con", "int", "wis", "cha"] as const;
const XIANXIA_CREATE_ATTRIBUTE_LABELS: Record<(typeof XIANXIA_CREATE_ATTRIBUTE_KEYS)[number], string> = {
  str: "Strength",
  dex: "Dexterity",
  con: "Constitution",
  int: "Intelligence",
  wis: "Wisdom",
  cha: "Charisma",
};
const XIANXIA_CREATE_EFFORT_KEYS = ["basic", "weapon", "guns_explosive", "magic", "ultimate"] as const;
const XIANXIA_CREATE_EFFORT_LABELS: Record<(typeof XIANXIA_CREATE_EFFORT_KEYS)[number], string> = {
  basic: "Basic",
  weapon: "Weapon",
  guns_explosive: "Guns/Explosive",
  magic: "Magic",
  ultimate: "Ultimate",
};
const XIANXIA_CREATE_ENERGY_KEYS = ["jing", "qi", "shen"] as const;
const XIANXIA_CREATE_ENERGY_LABELS: Record<(typeof XIANXIA_CREATE_ENERGY_KEYS)[number], string> = {
  jing: "Jing",
  qi: "Qi",
  shen: "Shen",
};
const XIANXIA_CREATE_GM_GRANTED_GENERIC_TECHNIQUE_INPUT = "gm_granted_generic_technique_entry_keys";

function normalizeCharacterAuthoringValue(value: unknown): string {
  if (Array.isArray(value)) {
    return String(value[0] ?? "");
  }
  return value === null || value === undefined ? "" : String(value);
}

function normalizeCharacterAuthoringValues(values: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [String(key), normalizeCharacterAuthoringValue(value)]));
}

function createContextInteger(value: unknown, fallback = 0): number {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildCharacterCreateTools(campaign: CampaignViewModel, canAuthorCharacters: boolean) {
  const lane = nativeCharacterCreateLane(campaign.system);
  return {
    can_create_characters: canAuthorCharacters && Boolean(lane),
    can_import_xianxia_characters: canAuthorCharacters && lane === "xianxia",
    native_character_tools_supported: lane === "dnd5e",
    native_character_create_supported: Boolean(lane),
    character_create_lane: lane,
  };
}

function buildXianxiaCharacterCreateContext({
  dbPath,
  campaign,
  campaignConfig,
  values,
}: {
  dbPath: string;
  campaign: CampaignViewModel;
  campaignConfig: Record<string, unknown>;
  values: Record<string, unknown>;
}) {
  const normalizedValues = normalizeCharacterAuthoringValues(values);
  const manualArmorBonus = Math.max(0, createContextInteger(normalizedValues.manual_armor_bonus, 0));
  const constitution = Math.max(0, createContextInteger(normalizedValues.attribute_con, 0));
  return {
    lane: "xianxia",
    values: normalizedValues,
    attribute_fields: XIANXIA_CREATE_ATTRIBUTE_KEYS.map((key) => ({
      key,
      label: XIANXIA_CREATE_ATTRIBUTE_LABELS[key],
      input_name: `attribute_${key}`,
      value: normalizedValues[`attribute_${key}`] || "0",
      max: 3,
    })),
    effort_fields: XIANXIA_CREATE_EFFORT_KEYS.map((key) => ({
      key,
      label: XIANXIA_CREATE_EFFORT_LABELS[key],
      input_name: `effort_${key}`,
      value: normalizedValues[`effort_${key}`] || "0",
      max: 3,
    })),
    energy_fields: XIANXIA_CREATE_ENERGY_KEYS.map((key) => ({
      key,
      label: XIANXIA_CREATE_ENERGY_LABELS[key],
      input_name: `energy_${key}`,
      value: normalizedValues[`energy_${key}`] || "0",
      max: 3,
    })),
    trained_skill_fields: [1, 2, 3].map((index) => ({
      index,
      label: `Trained Skill ${index}`,
      input_name: `trained_skill_${index}`,
      value: normalizedValues[`trained_skill_${index}`] || "",
    })),
    martial_art_fields: [1, 2, 3].map((index) => ({
      index,
      art_input_name: `martial_art_${index}_slug`,
      rank_input_name: `martial_art_${index}_rank`,
      selected_slug: normalizedValues[`martial_art_${index}_slug`] || "",
      selected_rank: normalizedValues[`martial_art_${index}_rank`] || "",
    })),
    martial_art_options: listXianxiaManualImportMartialArtOptions(dbPath, campaign, campaignConfig),
    martial_art_rank_choices: [
      { key: "initiate", label: "Initiate" },
      { key: "novice", label: "Novice" },
    ],
    manual_armor_field: {
      input_name: "manual_armor_bonus",
      value: normalizedValues.manual_armor_bonus || "0",
      min: 0,
    },
    dao_field: {
      input_name: "dao_current",
      value: normalizedValues.dao_current || "0",
      min: 0,
      max: 3,
    },
    generic_technique_options: listXianxiaCreateGenericTechniqueOptions(
      dbPath,
      campaign,
      campaignConfig,
      [normalizedValues.gm_granted_generic_technique_entry_keys].filter(Boolean),
    ),
    gm_granted_generic_technique_input: XIANXIA_CREATE_GM_GRANTED_GENERIC_TECHNIQUE_INPUT,
    defaults: {
      realm: "Mortal",
      actions_per_turn: 2,
      honor: "Honorable",
      reputation: "Unknown",
      hp_max: 10,
      stance_max: 10,
      manual_armor_bonus: manualArmorBonus,
      defense: 10 + manualArmorBonus + constitution,
      yin_max: 1,
      yang_max: 1,
      dao_current: 0,
      dao_max: 3,
      insight_available: 0,
      insight_spent: 0,
    },
  };
}

function resetTtlHours(): number {
  const configured = Number(process.env.PLAYER_WIKI_RESET_TTL_HOURS || "");
  return Number.isFinite(configured) && configured > 0 ? configured : 24;
}

function inviteTtlHours(): number {
  const configured = Number(process.env.PLAYER_WIKI_INVITE_TTL_HOURS || "");
  return Number.isFinite(configured) && configured > 0 ? configured : 72;
}

function buildLocalUrl(pathValue: string): string {
  const baseUrl = String(config.app.base_url || "").trim().replace(/\/+$/g, "");
  const normalizedPath = pathValue.startsWith("/") ? pathValue : `/${pathValue}`;
  return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

function characterDefinitionName(record: CampaignCharacterFileRecord): string {
  const name = record.definition.name;
  return typeof name === "string" && name.trim() ? name.trim() : record.character_slug;
}

function serializeControlsAssignment(assignment: CharacterAssignment | null, assignedUser: AuthUser | null) {
  if (!assignment) {
    return null;
  }
  return {
    user_id: assignment.user_id,
    assignment_type: assignment.assignment_type,
    display_name: assignedUser?.display_name || "Unknown user",
    email: assignedUser?.email || null,
    status: assignedUser?.status || "",
    created_at: assignment.created_at,
    updated_at: assignment.updated_at,
  };
}

function buildCharacterControlsPayload(
  campaignSlug: string,
  record: CampaignCharacterFileRecord,
  message: string,
) {
  const characterSlug = record.character_slug;
  const assignment = getCharacterAssignment(config.dbPath, campaignSlug, characterSlug);
  const assignedUser = assignment ? getUserById(config.dbPath, assignment.user_id) : null;
  const playerChoices = listActivePlayerMembershipUsers(config.dbPath, campaignSlug).map((user) => ({
    user_id: user.id,
    label: `${user.display_name} (${user.email})`,
    email: user.email,
    display_name: user.display_name,
    is_current: assignment?.user_id === user.id,
  }));

  return {
    ok: true,
    message,
    character: {
      character_slug: characterSlug,
      updated_at: record.updated_at,
      name: characterDefinitionName(record),
      system: typeof record.definition.system === "string" ? record.definition.system : "",
      definition: record.definition,
      import_metadata: record.import_metadata,
      controls: {
        assignment: serializeControlsAssignment(assignment, assignedUser),
        can_assign_owner: true,
        player_choices: playerChoices,
      },
    },
    links: {
      gen2_character_url: campaignHref(campaignSlug, `characters/${characterSlug}`),
      flask_character_url: flaskCampaignHref(campaignSlug, `characters/${characterSlug}`),
      gen2_roster_url: campaignHref(campaignSlug, "characters"),
      flask_roster_url: flaskCampaignHref(campaignSlug, "characters"),
    },
  };
}

function buildCharacterReadControlsPayload(
  campaign: CampaignViewModel,
  record: CampaignCharacterFileRecord,
  auth: Extract<RoleResolution, { kind: "authenticated" }>,
) {
  const campaignSlug = campaign.slug;
  const characterSlug = record.character_slug;
  const assignment = getCharacterAssignment(config.dbPath, campaignSlug, characterSlug);
  const assignedUser = assignment ? getUserById(config.dbPath, assignment.user_id) : null;
  const canAssignOwner = auth.role === "admin";
  const canDeleteCharacter =
    auth.role === "admin" ||
    (auth.role === "dm" && campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "campaign"));
  const playerChoices = canAssignOwner
    ? listActivePlayerMembershipUsers(config.dbPath, campaignSlug).map((user) => ({
        user_id: user.id,
        label: `${user.display_name} (${user.email})`,
        email: user.email,
        display_name: user.display_name,
        is_current: assignment?.user_id === user.id,
      }))
    : [];

  return {
    available: true,
    assignment: serializeControlsAssignment(assignment, assignedUser),
    can_assign_owner: canAssignOwner,
    can_delete_character: canDeleteCharacter,
    current_user_is_owner: Boolean(auth.actorUserId && assignment?.user_id === auth.actorUserId),
    player_choices: playerChoices,
    links: {
      gen2_roster_url: campaignHref(campaignSlug, "characters"),
      flask_controls_url: flaskCampaignHref(campaignSlug, `characters/${characterSlug}?page=controls`),
    },
  };
}

function canReadCharacterDetail(
  campaign: CampaignViewModel,
  characterSlug: string,
  auth: Extract<RoleResolution, { kind: "authenticated" }>,
): boolean {
  if (campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters")) {
    return true;
  }
  const hasSessionModeSurfaceAccess =
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session") ||
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "combat");
  if (!hasSessionModeSurfaceAccess) {
    return false;
  }
  return canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId);
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

function campaignAssetPathFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/campaigns/${campaignSlug}/assets/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  return pathname.slice(prefix.length);
}

function rawContentAssetRefFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/content/assets/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  return pathname.slice(prefix.length);
}

function systemsEntryOverrideKeyFromWildcard(pathname: string, campaignSlug: string): string {
  const prefix = `/api/v1/campaigns/${campaignSlug}/systems/overrides/`;
  if (!pathname.startsWith(prefix)) {
    return "";
  }
  try {
    return decodeURIComponent(pathname.slice(prefix.length));
  } catch {
    return pathname.slice(prefix.length);
  }
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
    const viewAs = resolveViewAsState(ctx, apiAuth.context);
    applyViewAsCookieState(ctx, viewAs);
    return ctx.json(buildApiTokenMePayload(config, apiAuth.context, viewAs.activeUser));
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

app.post(ROUTES.meViewAsUpdate, async (ctx) => {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid" || apiAuth.kind === "missing") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (!apiAuth.context.user.is_admin) {
    const error = forbidden("Only app admins can use View As.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const rawUserId = jsonPayload.payload.user_id;
  if (rawUserId === null || rawUserId === undefined || rawUserId === "") {
    clearRequestedViewAsUserId(ctx);
    return ctx.json({ ok: true, view_as: buildApiTokenViewAsState(apiAuth.context, null) });
  }

  const targetUserId = parsePositiveInteger(String(rawUserId));
  if (targetUserId === null) {
    const error = validationError("Choose a valid user to view as.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (targetUserId === apiAuth.context.user.id) {
    clearRequestedViewAsUserId(ctx);
    return ctx.json({ ok: true, view_as: buildApiTokenViewAsState(apiAuth.context, null) });
  }

  const targetUser = getActiveUserById(config.dbPath, targetUserId);
  if (!targetUser) {
    const error = validationError("Choose an active user to view as.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  setRequestedViewAsUserId(ctx, targetUser.id);
  return ctx.json({ ok: true, view_as: buildApiTokenViewAsState(apiAuth.context, targetUser) });
});

app.delete(ROUTES.meViewAsClear, async (ctx) => {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid" || apiAuth.kind === "missing") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (!apiAuth.context.user.is_admin) {
    const error = forbidden("Only app admins can use View As.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  clearRequestedViewAsUserId(ctx);
  return ctx.json({ ok: true, view_as: buildApiTokenViewAsState(apiAuth.context, null) });
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

app.get(ROUTES.adminDashboard, async (ctx) => {
  const auth = resolveAppAdminAuth(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(await buildAdminDashboardPayload(config, auth.actorUser || null, requestQueryValues(ctx)));
});

app.get(ROUTES.adminUser, async (ctx) => {
  const auth = resolveAppAdminAuth(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  if (userId === null) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, userId, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(payload);
});

app.post(ROUTES.adminCreateInvite, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const email = String(jsonPayload.payload.email || "").trim();
  const displayName = String(jsonPayload.payload.display_name || "").trim();
  let requestedUserType = String(jsonPayload.payload.user_type || "").trim().toLowerCase();
  const campaignSlug = String(jsonPayload.payload.campaign_slug || "").trim();

  if (!requestedUserType) {
    const legacyIsAdmin = String(jsonPayload.payload.is_admin || "").trim();
    if (legacyIsAdmin === "1") {
      requestedUserType = "admin";
    } else if (legacyIsAdmin === "0") {
      requestedUserType = "standard";
    }
  }

  if (!["admin", "dm", "player", "standard"].includes(requestedUserType)) {
    const error = validationError("Choose a valid user type.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (
    (requestedUserType === "dm" || requestedUserType === "player") &&
    (!campaignSlug || !(await getCampaignBySlug(config, campaignSlug)))
  ) {
    const error = validationError("Choose a valid campaign for DM or Player invites.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (!email || !displayName) {
    const error = validationError("Email and display name are required.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (getUserByEmail(config.dbPath, email)) {
    const error = validationError(`User already exists: ${email}`);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const makeAdmin = requestedUserType === "admin";
  const user = createUser(config.dbPath, {
    email,
    displayName,
    isAdmin: makeAdmin,
    status: "invited",
  });
  const inviteToken = issueInviteToken(config.dbPath, user.id, {
    ttlHours: inviteTtlHours(),
    createdByUserId: auth.actorUserId ?? null,
  });

  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: user.id,
    campaignSlug: null,
    characterSlug: null,
    eventType: "user_created",
    metadata: { is_admin: makeAdmin, source: "admin_screen" },
  });
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: user.id,
    campaignSlug: null,
    characterSlug: null,
    eventType: "user_invited",
    metadata: { source: "admin_screen" },
  });

  if (requestedUserType === "dm" || requestedUserType === "player") {
    const membership = upsertMembership(config.dbPath, user.id, campaignSlug, {
      role: requestedUserType,
      status: "active",
    });
    insertAuthAuditLog(config.dbPath, {
      actorUserId: auth.actorUserId ?? null,
      targetUserId: user.id,
      campaignSlug,
      characterSlug: null,
      eventType: "membership_created",
      metadata: { role: membership.role, status: membership.status, source: "admin_screen" },
    });
  }

  const inviteUrl = buildLocalUrl(`/invite/${inviteToken}`);
  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, user.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json(
    {
      ...payload,
      message: `Invite URL: ${inviteUrl}`,
      invite_url: inviteUrl,
    },
    201,
  );
});

app.post(ROUTES.adminUserMembership, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  if (userId === null || !getUserById(config.dbPath, userId)) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignSlug = String(jsonPayload.payload.campaign_slug || "").trim();
  const role = String(jsonPayload.payload.role || "").trim();
  const status = String(jsonPayload.payload.status || "").trim();
  if (!campaignSlug || !(await getCampaignBySlug(config, campaignSlug))) {
    const error = validationError("Choose a valid campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (!["dm", "player", "observer"].includes(role)) {
    const error = validationError("Choose a valid campaign role.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (!["active", "invited", "removed"].includes(status)) {
    const error = validationError("Choose a valid membership status.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const previous = getMembership(config.dbPath, userId, campaignSlug, null);
  const membership = upsertMembership(config.dbPath, userId, campaignSlug, { role, status });
  const eventType =
    previous === null || previous.status === "removed"
      ? "membership_created"
      : membership.status === "removed"
        ? "membership_removed"
        : "membership_role_changed";
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: userId,
    campaignSlug,
    characterSlug: null,
    eventType,
    metadata: { role: membership.role, status: membership.status, source: "admin_screen" },
  });

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, userId, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Membership updated: ${campaignSlug} -> ${membership.role} (${membership.status})`,
  });
});

app.delete(ROUTES.adminUserMembershipRemove, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  if (userId === null || !getUserById(config.dbPath, userId)) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignSlug = String(jsonPayload.payload.campaign_slug || "").trim();
  const membership = getMembership(config.dbPath, userId, campaignSlug, null);
  if (!membership) {
    const error = validationError("Choose a valid membership to remove.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (membership.status === "removed") {
    const error = validationError("That membership is already removed.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const updatedMembership = upsertMembership(config.dbPath, userId, membership.campaign_slug, {
    role: membership.role,
    status: "removed",
  });
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: userId,
    campaignSlug: membership.campaign_slug,
    characterSlug: null,
    eventType: "membership_removed",
    metadata: { role: updatedMembership.role, status: updatedMembership.status, source: "admin_screen" },
  });

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, userId, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Removed membership for ${membership.campaign_slug}.`,
  });
});

app.post(ROUTES.adminUserAssignment, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  let rawAssignment = String(jsonPayload.payload.character_ref || "").trim();
  if (!rawAssignment) {
    const campaignSlug = String(jsonPayload.payload.campaign_slug || "").trim();
    const characterSlug = String(jsonPayload.payload.character_slug || "").trim();
    if (campaignSlug && characterSlug) {
      rawAssignment = `${campaignSlug}::${characterSlug}`;
    }
  }
  if (!rawAssignment.includes("::")) {
    const error = validationError("Choose a valid character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const delimiterIndex = rawAssignment.indexOf("::");
  const campaignSlug = rawAssignment.slice(0, delimiterIndex).trim();
  const characterSlug = rawAssignment.slice(delimiterIndex + 2).trim();
  const character = campaignSlug && characterSlug ? await getCampaignContentCharacter(config, campaignSlug, characterSlug) : null;
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = validationError("Choose a valid visible character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const membership = getMembership(config.dbPath, targetUser.id, campaignSlug, ["active"]);
  if (!membership || membership.role !== "player") {
    const error = validationError("Character owners must have an active player membership in that campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaign = await getCampaignBySlug(config, campaignSlug);
  const campaignTitle = campaign?.title || campaignSlug;
  const characterLabel = String(character.definition.name || "").trim() || characterSlug;
  const previous = getCharacterAssignment(config.dbPath, campaignSlug, characterSlug);
  const assignment = upsertCharacterAssignment(config.dbPath, targetUser.id, campaignSlug, characterSlug);
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: targetUser.id,
    campaignSlug,
    characterSlug,
    eventType: "character_assignment_created",
    metadata: {
      previous_user_id: previous?.user_id ?? null,
      assignment_type: assignment.assignment_type,
      source: "admin_screen",
    },
  });

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, targetUser.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Assigned ${characterLabel} in ${campaignTitle} to ${targetUser.email}.`,
  });
});

app.delete(ROUTES.adminUserAssignmentRemove, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignSlug = String(jsonPayload.payload.campaign_slug || "").trim();
  const characterSlug = String(jsonPayload.payload.character_slug || "").trim();
  const campaign = await getCampaignBySlug(config, campaignSlug);
  const campaignTitle = campaign?.title || campaignSlug;
  const character = campaignSlug && characterSlug ? await getCampaignContentCharacter(config, campaignSlug, characterSlug) : null;
  const characterLabel = character ? String(character.definition.name || "").trim() || characterSlug : characterSlug;
  const assignment = getCharacterAssignment(config.dbPath, campaignSlug, characterSlug);
  if (!assignment || assignment.user_id !== targetUser.id) {
    const error = validationError("Choose a valid character assignment to remove.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const removedAssignment = deleteCharacterAssignment(config.dbPath, campaignSlug, characterSlug);
  if (!removedAssignment) {
    const error = validationError("That character assignment no longer exists.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: targetUser.id,
    campaignSlug,
    characterSlug,
    eventType: "character_assignment_removed",
    metadata: {
      assignment_type: removedAssignment.assignment_type,
      source: "admin_screen",
    },
  });

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, targetUser.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Cleared assignment for ${characterLabel} in ${campaignTitle}.`,
  });
});

app.post(ROUTES.adminUserPasswordReset, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (targetUser.status !== "active") {
    const error = validationError("Password resets are only available for active users.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const resetToken = issuePasswordResetToken(config.dbPath, targetUser.id, {
    ttlHours: resetTtlHours(),
    createdByUserId: auth.actorUserId ?? null,
  });
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: targetUser.id,
    campaignSlug: null,
    characterSlug: null,
    eventType: "password_reset_issued",
    metadata: { source: "admin_screen" },
  });

  const resetUrl = buildLocalUrl(`/reset/${resetToken}`);
  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, targetUser.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Password reset URL: ${resetUrl}`,
    reset_url: resetUrl,
  });
});

app.post(ROUTES.adminUserInvite, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (targetUser.status !== "invited") {
    const error = validationError("Invite links are only available for invited users.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const inviteToken = issueInviteToken(config.dbPath, targetUser.id, {
    ttlHours: inviteTtlHours(),
    createdByUserId: auth.actorUserId ?? null,
  });
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: targetUser.id,
    campaignSlug: null,
    characterSlug: null,
    eventType: "user_invited",
    metadata: { source: "admin_screen" },
  });

  const inviteUrl = buildLocalUrl(`/invite/${inviteToken}`);
  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, targetUser.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Invite URL: ${inviteUrl}`,
    invite_url: inviteUrl,
  });
});

app.post(ROUTES.adminUserDisable, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (auth.actorUserId === targetUser.id) {
    const error = validationError("The admin screen will not disable the account you are currently using.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const disabledUser = disableUser(config.dbPath, targetUser.id);
  revokeAllUserSessions(config.dbPath, targetUser.id);
  revokeAllUserApiTokens(config.dbPath, targetUser.id);
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: targetUser.id,
    campaignSlug: null,
    characterSlug: null,
    eventType: "user_disabled",
    metadata: { source: "admin_screen" },
  });

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, targetUser.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message: `Disabled user ${disabledUser.email}.`,
  });
});

app.post(ROUTES.adminUserEnable, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (targetUser.status !== "disabled") {
    const error = validationError("Only disabled users can be re-enabled.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (auth.actorUserId === targetUser.id) {
    const error = validationError("The admin screen will not re-enable the account you are currently using.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const enabledUser = enableUser(config.dbPath, targetUser.id);
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: targetUser.id,
    campaignSlug: null,
    characterSlug: null,
    eventType: "user_enabled",
    metadata: { status: enabledUser.status, source: "admin_screen" },
  });

  const payload = await buildAdminUserDetailPayload(config, auth.actorUser || null, targetUser.id, requestQueryValues(ctx));
  if (!payload) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({
    ...payload,
    message:
      enabledUser.status === "active"
        ? `Re-enabled user ${enabledUser.email}.`
        : `Re-enabled user ${enabledUser.email}. The account is back in invited status.`,
  });
});

app.delete(ROUTES.adminUserDelete, async (ctx) => {
  const auth = resolveAppAdminBearerWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const userId = parsePositiveInteger(ctx.req.param("userId") || "");
  const targetUser = userId === null ? null : getUserById(config.dbPath, userId);
  if (!targetUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (auth.actorUserId === targetUser.id) {
    const error = validationError("The admin screen will not delete the account you are currently using.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readOptionalJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const confirmEmail = String(jsonPayload.payload.confirm_email || jsonPayload.payload.confirm_user_email || "").trim();
  if (confirmEmail.toLowerCase() !== targetUser.email.toLowerCase()) {
    const error = validationError("Type the user's email address to confirm deletion.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const deletedUser = deleteUser(config.dbPath, targetUser.id);
  if (!deletedUser) {
    const error = notFound("admin_user_not_found", "Could not find that admin user.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId ?? null,
    targetUserId: null,
    campaignSlug: null,
    characterSlug: null,
    eventType: "user_deleted",
    metadata: {
      email: deletedUser.email,
      status: deletedUser.status,
      is_admin: deletedUser.is_admin,
      source: "admin_screen",
    },
  });

  return ctx.json({
    ...(await buildAdminDashboardPayload(config, auth.actorUser || null, requestQueryValues(ctx))),
    message: `Deleted user ${deletedUser.email}.`,
    deleted_user: deletedUser,
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

app.post(ROUTES.systemsDnd5eImport, async (ctx) => {
  const apiAuth = readApiTokenAuthContext(config.dbPath, ctx.req.header("Authorization"));
  if (apiAuth.kind === "invalid") {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (apiAuth.kind !== "authenticated") {
    if (fixtureRole(ctx)) {
      const error = forbidden("DND 5E Systems imports require bearer API authentication.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (!apiAuth.context.user.is_admin) {
    const error = forbidden("You do not have permission to use the admin API.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = importDnd5eSystemsArchive(config.dbPath, jsonPayload.payload, apiAuth.context.user.id);
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    import_results: result.import_results,
    import_runs: result.import_runs,
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

app.put(ROUTES.systemsSources, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = updateCampaignSystemsSources(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, sources: result.sources });
});

app.put(ROUTES.systemsEntryOverrideUpdate, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = updateCampaignSystemsEntryOverride(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    systemsEntryOverrideKeyFromWildcard(ctx.req.path, campaign.slug),
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, override: result.override, entry: result.entry });
});

app.post(ROUTES.systemsCustomEntries, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = createCustomSystemsEntry(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, entry: result.entry, systems: result.systems });
});

app.post(ROUTES.systemsItemMechanicsImport, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = importCampaignItemMechanics(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, entry: result.entry, systems: result.systems });
});

app.put(ROUTES.systemsCustomEntry, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = updateCustomSystemsEntry(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    ctx.req.param("entrySlug") || "",
    jsonPayload.payload,
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, entry: result.entry, systems: result.systems });
});

app.post(ROUTES.systemsCustomEntryArchive, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = archiveCustomSystemsEntry(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    ctx.req.param("entrySlug") || "",
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, entry: result.entry, systems: result.systems });
});

app.post(ROUTES.systemsCustomEntryRestore, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSystemsManagerBearerWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = roleResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  const result = restoreCustomSystemsEntry(
    config.dbPath,
    campaign,
    campaignConfig?.config || {},
    auth.role,
    auth.actorUserId || 0,
    ctx.req.param("entrySlug") || "",
  );
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  return ctx.json({ ok: true, entry: result.entry, systems: result.systems });
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

  const payload = await buildCombatReadOnlyPayload(config, campaign, role, {
    requestedCombatantId: requestedCombatantFocusId(ctx),
  });
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

  const payload = await buildCombatReadOnlyPayload(config, campaign, role, {
    requestedCombatantId: requestedCombatantFocusId(ctx),
  });
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

  return ctx.json(
    await buildCombatReadOnlyPayload(config, campaign, auth.role, {
      requestedCombatantId: requestedCombatantFocusId(ctx),
    }),
  );
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

  if ((ctx.req.header("Authorization") || "").trim()) {
    const auth = resolveCampaignRole(ctx, campaign.slug);
    if (auth.kind !== "authenticated") {
      const error = roleResolutionError(auth);
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    const canManageCampaign = auth.role === "admin" || auth.role === "dm";
    return ctx.json({
      ok: true,
      campaign,
      role: auth.role,
      auth_source: auth.authSource || "api_token",
      visibility: {
        campaign: { effective: "public", can_access: true },
        wiki: { effective: "public", can_access: true },
        systems: { effective: "players", can_access: true },
        session: { effective: "players", can_access: true },
        combat: { effective: "players", can_access: true },
        dm_content: { effective: "dm", can_access: canManageCampaign },
        characters: { effective: "dm", can_access: canManageCampaign },
      },
      permissions: {
        mode: "authenticated",
        can_manage_visibility: campaignRoleCanManageVisibility(config.dbPath, campaign, auth.role),
        can_manage_content: canManageCampaign,
        can_manage_systems: canManageCampaign,
        can_manage_combat: canManageCampaign,
        can_manage_session: canManageCampaign,
        can_manage_dm_content: canManageCampaign,
        can_post_session_messages: true,
      },
    });
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

app.get(ROUTES.campaignGlobalSearch, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignAccess = resolveBrowserScopeAccess(ctx, campaign, "campaign");
  if (campaignAccess.kind !== "authenticated" && campaignAccess.kind !== "public") {
    const error = browserAccessError(campaignAccess);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const query = (ctx.req.query("q") || "").trim();
  if (query.length < 2) {
    return ctx.json({
      results: [],
      message: "Type at least 2 letters to search wiki pages and Systems entries.",
    });
  }

  const role = campaignAccess.kind === "authenticated" ? campaignAccess.role : null;
  const results: Array<{
    result_id: string;
    kind: string;
    kind_label: string;
    title: string;
    subtitle: string;
    select_label: string;
  }> = [];

  const canSearchWiki = role
    ? campaignRoleCanAccessScope(config.dbPath, campaign, role, "wiki")
    : campaignScopeIsPublic(config.dbPath, campaign, "wiki");
  if (canSearchWiki) {
    const wikiPages = await campaignWikiRepository.searchPages(campaign.slug, query);
    for (const page of wikiPages) {
      const subtitle = pageContextLabel(page);
      results.push({
        result_id: `wiki:${page.page_ref}`,
        kind: "wiki",
        kind_label: "Wiki",
        title: page.title,
        subtitle,
        select_label: subtitle ? `${page.title} - Wiki - ${subtitle}` : `${page.title} - Wiki`,
      });
      if (results.length >= 30) {
        break;
      }
    }
  }

  const canSearchSystems = role ? campaignRoleCanAccessScope(config.dbPath, campaign, role, "systems") : false;
  if (results.length < 30 && canSearchSystems && role) {
    const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
    const systemsPayload = buildCampaignSystemsIndexPayload(
      config.dbPath,
      campaign,
      campaignConfig?.config || {},
      role,
      query,
      "",
    );
    for (const entry of systemsPayload.search_results) {
      results.push({
        result_id: `systems:${entry.slug}`,
        kind: "systems",
        kind_label: "Systems",
        title: entry.title,
        subtitle: `${entry.entry_type_label} / ${entry.source_id}`,
        select_label: `${entry.title} - Systems - ${entry.entry_type_label} - ${entry.source_id}`,
      });
      if (results.length >= 30) {
        break;
      }
    }
  }

  return ctx.json({
    results,
    message:
      results.length === 30
        ? "Showing the first 30 matching references."
        : results.length > 0
          ? `Found ${results.length} matching reference${results.length === 1 ? "" : "s"}.`
          : "No visible wiki pages or Systems entries matched that search.",
  });
});

app.get(ROUTES.campaignGlobalSearchPreview, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  const wikiCampaign = await campaignWikiRepository.getCampaign(campaignSlug);
  if (!campaign || !wikiCampaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignAccess = resolveBrowserScopeAccess(ctx, campaign, "campaign");
  if (campaignAccess.kind !== "authenticated" && campaignAccess.kind !== "public") {
    const error = browserAccessError(campaignAccess);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const resultId = (ctx.req.query("result_id") || "").trim();
  if (!resultId) {
    return ctx.json({ preview_html: "" });
  }

  const [kind, ...refParts] = resultId.split(":");
  const ref = refParts.join(":").trim();
  const role = campaignAccess.kind === "authenticated" ? campaignAccess.role : null;
  if (kind === "wiki" && ref) {
    const canPreviewWiki = role
      ? campaignRoleCanAccessScope(config.dbPath, campaign, role, "wiki")
      : campaignScopeIsPublic(config.dbPath, campaign, "wiki");
    const page = canPreviewWiki ? await campaignWikiRepository.getPage(campaign.slug, ref) : null;
    const bodyHtml = page ? await campaignWikiRepository.getPageBodyHtml(campaign.slug, page.route_slug) : null;
    if (page && bodyHtml !== null) {
      const imageUrl = page.image_ref && (await assetExists(wikiCampaign, page.image_ref))
        ? flaskCampaignHref(campaign.slug, `assets/${page.image_ref}`)
        : "";
      return ctx.json({
        preview_html: browserGlobalPreviewHtml({
          kindLabel: "Wiki article",
          title: page.title,
          meta: pageMetaLabel(page),
          summary: ["item", "spell", "mechanic"].includes(page.page_type) ? "" : page.summary,
          url: flaskCampaignHref(campaign.slug, `pages/${page.route_slug}`),
          bodyHtml,
          imageUrl,
          imageAlt: page.image_alt || page.title,
          imageCaption: page.image_caption,
        }),
      });
    }
  }

  if (kind === "systems" && ref && role && campaignRoleCanAccessScope(config.dbPath, campaign, role, "systems")) {
    const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
    const result = buildCampaignSystemsEntryDetailPayload(config.dbPath, campaign, campaignConfig?.config || {}, ref, role);
    if (result.status === "ok") {
      const entry = result.payload.entry;
      const bodyHtml =
        String(entry.rendered_html || "").trim() ||
        '<p class="meta">This Systems entry does not have rendered article content yet.</p>';
      return ctx.json({
        preview_html: browserGlobalPreviewHtml({
          kindLabel: "Systems entry",
          title: entry.title,
          meta: `${entryTypeLabel(entry.entry_type)} / ${entry.source_id}`,
          summary: "",
          url: flaskCampaignHref(campaign.slug, `systems/entries/${entry.slug}`),
          bodyHtml,
        }),
      });
    }
  }

  return ctx.json(
    {
      preview_html: browserCompatibilityUnavailableHtml(
        "That reference is not currently visible.",
        "campaign-global-search-preview",
      ),
    },
    404,
  );
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

app.get(ROUTES.dmContentSystems, async (ctx) => {
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
    const error = forbidden("You do not have permission to manage systems.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignConfig = await getCampaignConfigFile(config, campaign.slug);
  return ctx.json({
    ok: true,
    ...buildDmContentSystemsPayload(config.dbPath, campaign, campaignConfig?.config || {}, auth.role),
  });
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

app.get(ROUTES.campaignAsset, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = notFound("campaign_asset_not_found", "Could not find that campaign asset.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const assetPath = campaignAssetPathFromWildcard(ctx.req.path, campaign.slug);
  if (!assetPath) {
    const error = notFound("campaign_asset_not_found", "Could not find that campaign asset.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!campaignScopeIsPublic(config.dbPath, campaign, "wiki")) {
    const auth = resolveCampaignRole(ctx, campaign.slug);
    if (auth.kind !== "authenticated") {
      const error = roleResolutionError(auth);
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    if (!campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "wiki")) {
      const error = forbidden("You do not have access to this campaign scope.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
  }

  const asset = await readCampaignProtectedAsset(config, campaign.slug, assetPath);
  if (!asset) {
    const error = notFound("campaign_asset_not_found", "Could not find that campaign asset.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return new Response(asset.data, {
    status: 200,
    headers: {
      "Content-Type": asset.record.media_type,
      "Content-Disposition": inlineContentDisposition(path.basename(asset.record.file_path)),
      "Content-Length": String(asset.data.byteLength),
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

app.get(ROUTES.sessionWikiLookupSearch, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const sessionAccess = resolveBrowserScopeAccess(ctx, campaign, "session");
  if (sessionAccess.kind !== "authenticated" && sessionAccess.kind !== "public") {
    const error = browserAccessError(sessionAccess);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const role = sessionAccess.kind === "authenticated" ? sessionAccess.role : null;
  const canSearchWiki = role
    ? campaignRoleCanAccessScope(config.dbPath, campaign, role, "wiki")
    : campaignScopeIsPublic(config.dbPath, campaign, "wiki");
  if (!canSearchWiki) {
    return ctx.json({
      results: [],
      message: "No player-visible wiki articles are available right now.",
    });
  }

  const query = (ctx.req.query("q") || "").trim();
  if (query.length < 2) {
    return ctx.json({
      results: [],
      message: "Type at least 2 letters to search player-visible wiki articles.",
    });
  }

  const pages = await campaignWikiRepository.searchPages(campaign.slug, query);
  const results = pages.slice(0, 30).map((page) => {
    const subtitle = pageContextLabel(page);
    return {
      page_ref: page.page_ref,
      title: page.title,
      subtitle,
      select_label: subtitle ? `${page.title} - ${subtitle}` : page.title,
    };
  });

  return ctx.json({
    results,
    message:
      results.length === 30
        ? "Showing the first 30 matching wiki articles."
        : results.length > 0
          ? `Found ${results.length} matching article${results.length === 1 ? "" : "s"}.`
          : "No player-visible wiki articles matched that search.",
  });
});

app.get(ROUTES.sessionWikiLookupPreview, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  const wikiCampaign = await campaignWikiRepository.getCampaign(campaignSlug);
  if (!campaign || !wikiCampaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const sessionAccess = resolveBrowserScopeAccess(ctx, campaign, "session");
  if (sessionAccess.kind !== "authenticated" && sessionAccess.kind !== "public") {
    const error = browserAccessError(sessionAccess);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pageRef = (ctx.req.query("page_ref") || "").trim();
  if (!pageRef) {
    return ctx.json({ preview_html: "" });
  }

  const role = sessionAccess.kind === "authenticated" ? sessionAccess.role : null;
  const canPreviewWiki = role
    ? campaignRoleCanAccessScope(config.dbPath, campaign, role, "wiki")
    : campaignScopeIsPublic(config.dbPath, campaign, "wiki");
  const page = canPreviewWiki ? await campaignWikiRepository.getPage(campaign.slug, pageRef) : null;
  const bodyHtml = page ? await campaignWikiRepository.getPageBodyHtml(campaign.slug, page.route_slug) : null;
  if (!page || bodyHtml === null) {
    return ctx.json(
      {
        preview_html: browserCompatibilityUnavailableHtml(
          "That article is not currently visible to players.",
          "session-wiki-lookup-empty",
          false,
        ),
      },
      404,
    );
  }

  const imageUrl =
    page.image_ref && (await assetExists(wikiCampaign, page.image_ref))
      ? flaskCampaignHref(campaign.slug, `assets/${page.image_ref}`)
      : "";
  return ctx.json({
    preview_html: browserSessionWikiPreviewHtml({
      page,
      url: flaskCampaignHref(campaign.slug, `pages/${page.route_slug}`),
      bodyHtml,
      imageUrl,
    }),
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

app.get(ROUTES.characterRoster, async (ctx) => {
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

  const characters = await listCampaignContentCharacters(config, campaign.slug);
  if (!characters) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const canAccessCharacterRoster = campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters");
  const visibleCharacters = characters.filter((record) => String(record.definition.status || "").trim() === "active");
  let rosterCharacters = visibleCharacters;
  if (!canAccessCharacterRoster) {
    rosterCharacters = visibleCharacters.filter((record) => {
      if (!auth.actorUserId) {
        return false;
      }
      const assignment = getCharacterAssignment(config.dbPath, campaign.slug, record.character_slug);
      return assignment?.user_id === auth.actorUserId;
    });
    if (rosterCharacters.length === 0) {
      const error = forbidden("You do not have access to campaign characters.");
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
  }

  const stateBySlug = new Map(
    rosterCharacters.map((record) => [
      record.character_slug,
      readCharacterStateSnapshot(config, campaign.slug, record.character_slug, record.definition),
    ]),
  );
  const assets = (await listCampaignContentAssets(config, campaign.slug)) ?? [];
  const assetByRef = new Map(assets.map((asset) => [asset.asset_ref, asset]));
  const query = (new URL(ctx.req.url).searchParams.get("q") || "").trim();
  return ctx.json(
    buildCharacterRosterPayload({
      campaign,
      records: rosterCharacters,
      stateBySlug,
      assetByRef,
      query,
      canManageSession:
        (auth.role === "admin" || auth.role === "dm") &&
        campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session"),
    }),
  );
});

app.get(ROUTES.characterCreateContext, async (ctx) => {
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

  const canAuthorCharacters =
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters") &&
    (auth.role === "admin" ||
      (auth.role === "dm" && campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session")));
  if (!canAuthorCharacters) {
    const error = forbidden("You do not have permission to create characters in this campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const lane = nativeCharacterCreateLane(campaign.system);
  if (!lane) {
    const error = jsonError("unsupported_campaign_system", nativeCharacterCreateUnsupportedMessage(campaign.system), 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const values = requestQueryValues(ctx);
  const configRecord = await getCampaignConfigFile(config, campaign.slug);
  const create =
    lane === "xianxia"
      ? buildXianxiaCharacterCreateContext({
          dbPath: config.dbPath,
          campaign,
          campaignConfig: configRecord?.config || {},
          values,
        })
      : buildDndCharacterCreateContext({
          dbPath: config.dbPath,
          campaign,
          campaignConfig: configRecord?.config || {},
          values,
        });

  return ctx.json({
    ok: true,
    campaign,
    lane,
    tools: buildCharacterCreateTools(campaign, canAuthorCharacters),
    links: buildCharacterAuthoringLinks(campaign),
    create,
  });
});

app.post(ROUTES.characterCreate, async (ctx) => {
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

  const canAuthorCharacters =
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters") &&
    (auth.role === "admin" ||
      (auth.role === "dm" && campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session")));
  if (!canAuthorCharacters) {
    const error = forbidden("You do not have permission to create characters in this campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const lane = nativeCharacterCreateLane(campaign.system);
  if (!lane) {
    const error = jsonError("unsupported_campaign_system", nativeCharacterCreateUnsupportedMessage(campaign.system), 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const payload = jsonPayload.payload;
  const rawValues =
    payload.values !== null &&
    payload.values !== undefined &&
    typeof payload.values === "object" &&
    !Array.isArray(payload.values)
      ? (payload.values as Record<string, unknown>)
      : payload;
  const configRecord = await getCampaignConfigFile(config, campaign.slug);

  let createPayload;
  try {
    if (lane === "dnd5e") {
      createPayload = buildDndCreateCharacter({
        dbPath: config.dbPath,
        campaign,
        campaignConfig: configRecord?.config || {},
        values: rawValues,
      });
    } else {
      const createContext = buildXianxiaCharacterCreateContext({
        dbPath: config.dbPath,
        campaign,
        campaignConfig: configRecord?.config || {},
        values: rawValues,
      });
      createPayload = buildXianxiaCreateCharacter({
        campaignSlug: campaign.slug,
        values: rawValues,
        martialArtOptions: createContext.martial_art_options,
        genericTechniqueOptions: createContext.generic_technique_options,
      });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid character payload.";
    const validation = validationError(message);
    return ctx.json({ ok: validation.ok, error: validation.error }, validation.status);
  }

  const createResult = await createCampaignContentCharacter(
    config,
    campaign.slug,
    String(createPayload.definition.character_slug || ""),
    createPayload.definition,
    createPayload.importMetadata,
    createPayload.initialState,
  );
  if (createResult.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (createResult.status === "validation_error") {
    const error = validationError(createResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (createResult.status === "character_exists") {
    const error = jsonError("character_exists", createResult.message, 409);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, createResult.record.character_slug, createResult.record.definition);
  return ctx.json({
    ok: true,
    message: `${String(createResult.record.definition.name || createResult.record.character_slug)} created.`,
    character: {
      definition: createResult.record.definition,
      import_metadata: createResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: createResult.record.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
    },
    links: {
      ...buildCharacterAuthoringLinks(campaign),
      character_url: `/app-next/campaigns/${campaign.slug}/characters/${createResult.record.character_slug}`,
      flask_character_url: `/campaigns/${campaign.slug}/characters/${createResult.record.character_slug}`,
    },
  });
});

app.get(ROUTES.characterXianxiaManualImportContext, async (ctx) => {
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

  const canAuthorCharacters =
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters") &&
    (auth.role === "admin" ||
      (auth.role === "dm" && campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session")));
  if (!canAuthorCharacters) {
    const error = forbidden("You do not have permission to create characters in this campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const lane = nativeCharacterCreateLane(campaign.system);
  if (!lane) {
    const error = jsonError("unsupported_campaign_system", nativeCharacterCreateUnsupportedMessage(campaign.system), 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (lane !== "xianxia") {
    const error = jsonError(
      "unsupported_campaign_system",
      "Manual Xianxia character import is only available for Xianxia campaigns.",
      400,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const configRecord = await getCampaignConfigFile(config, campaign.slug);
  return ctx.json({
    ok: true,
    campaign,
    lane,
    links: buildCharacterAuthoringLinks(campaign),
    import_context: buildXianxiaManualImportContext({
      dbPath: config.dbPath,
      campaign,
      campaignConfig: configRecord?.config || {},
      values: requestQueryValues(ctx),
    }),
  });
});

app.post(ROUTES.characterXianxiaManualImport, async (ctx) => {
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

  const canAuthorCharacters =
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "characters") &&
    (auth.role === "admin" ||
      (auth.role === "dm" && campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session")));
  if (!canAuthorCharacters) {
    const error = forbidden("You do not have permission to create characters in this campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const lane = nativeCharacterCreateLane(campaign.system);
  if (!lane) {
    const error = jsonError("unsupported_campaign_system", nativeCharacterCreateUnsupportedMessage(campaign.system), 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (lane !== "xianxia") {
    const error = jsonError(
      "unsupported_campaign_system",
      "Manual Xianxia character import is only available for Xianxia campaigns.",
      400,
    );
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const configRecord = await getCampaignConfigFile(config, campaign.slug);
  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = invalidJson(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const payload = jsonPayload.payload;
  const { values: nestedValues, confirm_import, ...otherPayload } = payload;
  const rawValues =
    nestedValues !== null &&
    nestedValues !== undefined &&
    typeof nestedValues === "object" &&
    !Array.isArray(nestedValues)
      ? nestedValues
      : otherPayload;
  if (typeof rawValues !== "object" || rawValues === null || Array.isArray(rawValues)) {
    const error = invalidJson("Request body must be a JSON object.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const values = Object.fromEntries(
    Object.entries(rawValues).map(([key, value]) => [String(key), value === null || value === undefined ? "" : String(value)]),
  ) as Record<string, string>;
  const confirmImport = Boolean(confirm_import);
  const importContext = buildXianxiaManualImportContext({
    dbPath: config.dbPath,
    campaign,
    campaignConfig: configRecord?.config || {},
    values,
  });
  let importResult;
  try {
    importResult = buildXianxiaManualImportCharacter({
      campaignSlug: campaign.slug,
      values,
      martialArtOptions: importContext.martial_art_options,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid import payload.";
    const validation = validationError(message);
    return ctx.json({ ok: validation.ok, error: validation.error }, validation.status);
  }

  if (confirmImport) {
    const createResult = await createCampaignContentCharacter(
      config,
      campaign.slug,
      String(importResult.definition.character_slug || ""),
      importResult.definition,
      importResult.importMetadata,
      importResult.initialState,
    );
    if (createResult.status === "not_found") {
      const error = campaignNotFound(campaignSlug);
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    if (createResult.status === "validation_error") {
      const error = validationError(createResult.message);
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }
    if (createResult.status === "character_exists") {
      const error = jsonError("character_exists", createResult.message, 409);
      return ctx.json({ ok: error.ok, error: error.error }, error.status);
    }

    const stateRecord = readCharacterStateSnapshot(config, campaign.slug, createResult.record.character_slug, createResult.record.definition);
    return ctx.json({
      ok: true,
      message: `${String(createResult.record.definition.name || createResult.record.character_slug)} imported.`,
      character: {
        definition: createResult.record.definition,
        import_metadata: createResult.record.import_metadata,
        state_record: {
          campaign_slug: campaign.slug,
          character_slug: createResult.record.character_slug,
          revision: stateRecord.revision,
          state: stateRecord.state,
          updated_at: stateRecord.updated_at ?? null,
          updated_by_user_id: stateRecord.updated_by_user_id ?? null,
        },
      },
      links: {
        ...buildCharacterAuthoringLinks(campaign),
        character_url: `/app-next/campaigns/${campaign.slug}/characters/${createResult.record.character_slug}`,
        flask_character_url: `/campaigns/${campaign.slug}/characters/${createResult.record.character_slug}`,
      },
    });
  }

  return ctx.json({
    ok: true,
    message: "Review the imported sheet summary, then confirm to create the character.",
    campaign,
    lane,
    links: buildCharacterAuthoringLinks(campaign),
    import_context: {
      ...importContext,
      preview: importResult.preview,
    },
  });
});

app.get(ROUTES.characterDetail, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canReadCharacterDetail(campaign, characterSlug, auth)) {
    const error = forbidden("You do not have access to this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const assets = (await listCampaignContentAssets(config, campaign.slug)) ?? [];
  const assetByRef = new Map(assets.map((asset) => [asset.asset_ref, asset]));
  const campaignPageRecords = (await listCampaignContentPages(config, campaign.slug)) ?? [];
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const linkedSystemsSlugs = collectCharacterSystemsRefSlugs(character.definition);
  collectCharacterSystemsRefSlugs(stateRecord.state, linkedSystemsSlugs);
  const systemsEntriesBySlug = buildCharacterDetailSystemsEntriesBySlug({
    campaign,
    campaignConfig,
    role: auth.role,
    slugs: linkedSystemsSlugs,
  });
  const canManageSession =
    (auth.role === "admin" || auth.role === "dm") &&
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session");
  const canEditSession = canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId);
  const canUseControls = supportsCharacterControlsRoutes(campaign.system) && canEditSession;

  return ctx.json(
    buildCharacterDetailPayload({
      campaign,
      record: character,
      stateRecord,
      assetByRef,
      permissions: {
        can_edit_session: canEditSession,
        can_manage_session: canManageSession,
        can_use_controls: canUseControls,
        can_record_xianxia_dao_immolating_use: canManageSession,
      },
      controls: canUseControls ? buildCharacterReadControlsPayload(campaign, character, auth) : null,
      campaignPageRecords,
      systemsEntriesBySlug,
    }),
  );
});

app.get(ROUTES.characterAdvancedEditor, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canReadCharacterDetail(campaign, characterSlug, auth)) {
    const error = forbidden("You do not have access to this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const campaignPageRecords = await listCampaignContentPages(config, campaign.slug) ?? [];
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const optionalFeatureRows = listAdvancedEditorOptionalFeatureRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const spellRows = listAdvancedEditorSpellRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const editorPayload = buildCharacterAdvancedEditorPayload({
    campaign,
    characterSlug,
    definition: character.definition,
    state: stateRecord.state,
    stateRevision: stateRecord.revision,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  });

  return ctx.json({
    ok: true,
    message: null,
    campaign,
    character: {
      definition: character.definition,
      import_metadata: character.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: character.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
    },
    lane: editorPayload.lane,
    supported: editorPayload.supported,
    unsupported_message: editorPayload.unsupported_message,
    links: editorPayload.links,
    editor: editorPayload.editor,
  });
});

app.put(ROUTES.characterAdvancedEditorUpdate, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to edit this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!characterAdvancedEditorIsSupported(campaign, character.definition)) {
    const error = jsonError("unsupported_campaign_system", advancedEditorUnsupportedMessage(), 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const campaignPageRecords = await listCampaignContentPages(config, campaign.slug) ?? [];
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const optionalFeatureRows = listAdvancedEditorOptionalFeatureRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const spellRows = listAdvancedEditorSpellRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const referenceUpdate = applyCharacterAdvancedEditorReferenceUpdate(
    character.definition,
    jsonPayload.payload,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  );
  if (referenceUpdate.status === "validation_error") {
    const error = validationError(referenceUpdate.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateResult = updateCharacterAdvancedEditorReferenceState(
    config,
    campaign.slug,
    characterSlug,
    referenceUpdate.definition,
    {
      expected_revision: jsonPayload.payload.expected_revision,
      state_note_values: referenceUpdate.stateNoteValues,
      manualEquipmentReconcile: referenceUpdate.manualEquipmentReconcile,
    },
    auth.actorUserId ?? 0,
  );
  if (stateResult.status === "state_conflict") {
    const error = stateConflict(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "validation_error") {
    const error = validationError(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: referenceUpdate.definition,
    import_metadata: buildManagedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  });
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const editorPayload = buildCharacterAdvancedEditorPayload({
    campaign,
    characterSlug,
    definition: writeResult.record.definition,
    state: stateResult.state,
    stateRevision: stateResult.revision,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  });

  return ctx.json({
    ok: true,
    message: "Character details updated.",
    campaign,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: writeResult.record.character_slug,
        revision: stateResult.revision,
        state: stateResult.state,
        updated_at: stateResult.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
    lane: editorPayload.lane,
    supported: editorPayload.supported,
    unsupported_message: editorPayload.unsupported_message,
    links: editorPayload.links,
    editor: editorPayload.editor,
  });
});

app.get(ROUTES.characterRetraining, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to retrain this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const campaignPageRecords = await listCampaignContentPages(config, campaign.slug) ?? [];
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const optionalFeatureRows = listAdvancedEditorOptionalFeatureRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const spellRows = listAdvancedEditorSpellRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const advancementPayload = buildCharacterRetrainingPayload({
    campaign,
    characterSlug,
    definition: character.definition,
    state: stateRecord.state,
    stateRevision: stateRecord.revision,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  });

  return ctx.json({
    ok: true,
    message: null,
    campaign,
    character: {
      definition: character.definition,
      import_metadata: character.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: character.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
    },
    lane: advancementPayload.lane,
    supported: advancementPayload.supported,
    unsupported_message: advancementPayload.unsupported_message,
    readiness: advancementPayload.readiness,
    retraining: advancementPayload.context,
    links: advancementPayload.links,
  });
});

app.post(ROUTES.characterRetrainingSubmit, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to retrain this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const campaignPageRecords = await listCampaignContentPages(config, campaign.slug) ?? [];
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const optionalFeatureRows = listAdvancedEditorOptionalFeatureRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const spellRows = listAdvancedEditorSpellRows({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
  });
  const advancementPayload = buildCharacterRetrainingPayload({
    campaign,
    characterSlug,
    definition: character.definition,
    state: stateRecord.state,
    stateRevision: stateRecord.revision,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  });
  if (!advancementPayload.supported || !advancementPayload.context) {
    const message = advancementPayload.supported
      ? "This character is not ready for Gen2 retraining."
      : advancementPayload.unsupported_message || "This character is not ready for Gen2 retraining.";
    const error = jsonError("unsupported_campaign_system", message, 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const retrainingUpdate = applyCharacterRetrainingUpdate(
    character.definition,
    jsonPayload.payload,
    advancementPayload.context,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  );
  if (retrainingUpdate.status === "validation_error") {
    const error = validationError(retrainingUpdate.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateResult = updateCharacterAdvancedEditorReferenceState(
    config,
    campaign.slug,
    characterSlug,
    retrainingUpdate.definition,
    {
      expected_revision: jsonPayload.payload.expected_revision,
      state_note_values: retrainingUpdate.stateNoteValues,
      manualEquipmentReconcile: retrainingUpdate.manualEquipmentReconcile,
    },
    auth.actorUserId ?? 0,
  );
  if (stateResult.status === "state_conflict") {
    const error = stateConflict(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "validation_error") {
    const error = validationError(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: retrainingUpdate.definition,
    import_metadata: buildManagedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  });
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const refreshedPayload = buildCharacterRetrainingPayload({
    campaign,
    characterSlug,
    definition: writeResult.record.definition,
    state: stateResult.state,
    stateRevision: stateResult.revision,
    campaignPageRecords,
    optionalFeatureRows,
    spellRows,
  });

  return ctx.json({
    ok: true,
    message: "Character retraining saved.",
    campaign,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: writeResult.record.character_slug,
        revision: stateResult.revision,
        state: stateResult.state,
        updated_at: stateResult.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
    lane: refreshedPayload.lane,
    supported: refreshedPayload.supported,
    unsupported_message: refreshedPayload.unsupported_message,
    readiness: refreshedPayload.readiness,
    retraining: refreshedPayload.context,
    links: refreshedPayload.links,
  });
});

app.get(ROUTES.characterLevelUp, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to level up this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const queryValues = Object.fromEntries(new URL(ctx.req.url).searchParams.entries());
  const advancementPayload = buildCharacterLevelUpPayload({
    campaign,
    characterSlug,
    definition: character.definition,
    stateRevision: stateRecord.revision,
    values: queryValues,
  });

  return ctx.json({
    ok: true,
    message: null,
    campaign,
    character: {
      definition: character.definition,
      import_metadata: character.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: character.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
    },
    lane: advancementPayload.lane,
    supported: advancementPayload.supported,
    unsupported_message: advancementPayload.unsupported_message,
    readiness: advancementPayload.readiness,
    level_up: advancementPayload.context,
    links: advancementPayload.links,
  });
});

app.post(ROUTES.characterLevelUpSubmit, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!canEditCharacterSessionState(config, campaign.slug, characterSlug, auth.role, auth.actorUserId)) {
    const error = forbidden("You do not have permission to level up this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const advancementPayload = buildCharacterLevelUpPayload({
    campaign,
    characterSlug,
    definition: character.definition,
    stateRevision: stateRecord.revision,
    values:
      typeof jsonPayload.payload.values === "object" && jsonPayload.payload.values !== null && !Array.isArray(jsonPayload.payload.values)
        ? (jsonPayload.payload.values as Record<string, unknown>)
        : {},
  });
  if (!advancementPayload.supported || !advancementPayload.context) {
    const message = advancementPayload.supported
      ? "This character is not ready for Gen2 level-up."
      : advancementPayload.unsupported_message || "This character is not ready for Gen2 level-up.";
    const error = jsonError("unsupported_campaign_system", message, 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const levelUpUpdate = applyCharacterLevelUpUpdate(character.definition, jsonPayload.payload, advancementPayload.context);
  if (levelUpUpdate.status === "validation_error") {
    const error = validationError(levelUpUpdate.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateResult = updateCharacterLevelUpDefinitionState(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    levelUpUpdate.definition,
    jsonPayload.payload,
    levelUpUpdate.hpGain,
    auth.actorUserId ?? 0,
  );
  if (stateResult.status === "state_conflict") {
    const error = stateConflict(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "validation_error") {
    const error = validationError(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: levelUpUpdate.definition,
    import_metadata: buildManagedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  });
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const refreshedPayload = buildCharacterLevelUpPayload({
    campaign,
    characterSlug,
    definition: writeResult.record.definition,
    stateRevision: stateResult.revision,
    values: levelUpUpdate.values,
  });

  return ctx.json({
    ok: true,
    message: "Character level-up saved.",
    campaign,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: writeResult.record.character_slug,
        revision: stateResult.revision,
        state: stateResult.state,
        updated_at: stateResult.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
    lane: refreshedPayload.lane,
    supported: refreshedPayload.supported,
    unsupported_message: refreshedPayload.unsupported_message,
    readiness: refreshedPayload.readiness,
    level_up: refreshedPayload.context,
    links: refreshedPayload.links,
  });
});

app.get(ROUTES.characterProgressionRepair, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const canManageSession =
    (auth.role === "admin" || auth.role === "dm") &&
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session");
  if (!canManageSession) {
    const error = forbidden("You do not have permission to repair progression for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const queryValues = Object.fromEntries(new URL(ctx.req.url).searchParams.entries());
  const advancementPayload = buildCharacterProgressionRepairPayload({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
    characterSlug,
    definition: character.definition,
    stateRevision: stateRecord.revision,
    values: queryValues,
  });

  return ctx.json({
    ok: true,
    message: null,
    campaign,
    character: {
      definition: character.definition,
      import_metadata: character.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: character.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
    },
    lane: advancementPayload.lane,
    supported: advancementPayload.supported,
    unsupported_message: advancementPayload.unsupported_message,
    readiness: advancementPayload.readiness,
    repair: advancementPayload.context,
    links: advancementPayload.links,
  });
});

app.post(ROUTES.characterProgressionRepairSubmit, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const canManageSession =
    (auth.role === "admin" || auth.role === "dm") &&
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session");
  if (!canManageSession) {
    const error = forbidden("You do not have permission to repair progression for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const campaignConfig = (await getCampaignConfigFile(config, campaign.slug))?.config || {};
  const advancementPayload = buildCharacterProgressionRepairPayload({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
    characterSlug,
    definition: character.definition,
    stateRevision: stateRecord.revision,
    values:
      typeof jsonPayload.payload.values === "object" && jsonPayload.payload.values !== null && !Array.isArray(jsonPayload.payload.values)
        ? (jsonPayload.payload.values as Record<string, unknown>)
        : {},
  });
  if (!advancementPayload.supported || !advancementPayload.context) {
    const message = advancementPayload.supported
      ? "This character is not ready for Gen2 progression repair."
      : advancementPayload.unsupported_message || "This character is not ready for Gen2 progression repair.";
    const error = jsonError("unsupported_campaign_system", message, 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const repairUpdate = applyCharacterProgressionRepairUpdate(
    character.definition,
    jsonPayload.payload,
    advancementPayload.context,
  );
  if (repairUpdate.status === "validation_error") {
    const error = validationError(repairUpdate.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateResult = updateCharacterAdvancedEditorReferenceState(
    config,
    campaign.slug,
    characterSlug,
    repairUpdate.definition,
    {
      expected_revision: jsonPayload.payload.expected_revision,
      state_note_values: {},
      manualEquipmentReconcile: { enabled: false, removedItemIds: [] },
    },
    auth.actorUserId ?? 0,
  );
  if (stateResult.status === "state_conflict") {
    const error = stateConflict(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "validation_error") {
    const error = validationError(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: repairUpdate.definition,
    import_metadata: buildManagedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  });
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const refreshedPayload = buildCharacterProgressionRepairPayload({
    dbPath: config.dbPath,
    campaign,
    campaignConfig,
    characterSlug,
    definition: writeResult.record.definition,
    stateRevision: stateResult.revision,
    values: repairUpdate.values,
  });
  const repairMessage =
    refreshedPayload.lane === "ready"
      ? `${String(writeResult.record.definition.name || "This character").trim()} is ready for native level-up.`
      : "Progression repair saved, but this character still needs a few more linked details before native level-up.";

  return ctx.json({
    ok: true,
    message: repairMessage,
    campaign,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: writeResult.record.character_slug,
        revision: stateResult.revision,
        state: stateResult.state,
        updated_at: stateResult.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
    lane: refreshedPayload.lane,
    supported: refreshedPayload.supported,
    unsupported_message: refreshedPayload.unsupported_message,
    readiness: refreshedPayload.readiness,
    repair: refreshedPayload.context,
    links: refreshedPayload.links,
  });
});

app.get(ROUTES.characterCultivation, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const canManageSession =
    (auth.role === "admin" || auth.role === "dm") &&
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session");
  if (!canManageSession) {
    const error = forbidden("You do not have permission to manage cultivation for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateRecord = readCharacterStateSnapshot(config, campaign.slug, character.character_slug, character.definition);
  const configRecord = await getCampaignConfigFile(config, campaign.slug);
  const cultivationPayload = buildCharacterCultivationShellPayload({
    campaign,
    characterSlug,
    definition: character.definition,
    state: stateRecord.state,
    genericTechniqueOptions: listXianxiaCreateGenericTechniqueOptions(
      config.dbPath,
      campaign,
      configRecord?.config || {},
      xianxiaKnownGenericTechniqueOptionKeys(character.definition),
    ),
  });

  return ctx.json({
    ok: true,
    campaign,
    character: {
      definition: character.definition,
      import_metadata: character.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: character.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
    },
    lane: cultivationPayload.lane,
    supported: cultivationPayload.supported,
    message: null,
    anchor: null,
    unsupported_message: cultivationPayload.unsupported_message,
    cultivation: cultivationPayload.cultivation,
    links: cultivationPayload.links,
  });
});

app.post(ROUTES.characterCultivation, async (ctx) => {
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
  if (!character || String(character.definition.status || "").trim() !== "active") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const canManageSession =
    (auth.role === "admin" || auth.role === "dm") &&
    campaignRoleCanAccessScope(config.dbPath, campaign, auth.role, "session");
  if (!canManageSession) {
    const error = forbidden("You do not have permission to manage cultivation for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!characterCultivationIsSupported(campaign, character.definition)) {
    const error = jsonError("unsupported_campaign_system", "Cultivation is only available for Xianxia character sheets.", 400);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const configRecord = await getCampaignConfigFile(config, campaign.slug);
  const campaignConfig = configRecord?.config || {};
  const cultivationAction = applyCharacterCultivationAction(character.definition, jsonPayload.payload, {
    genericTechniqueRows: listXianxiaCultivationGenericTechniqueRows(config.dbPath, campaign, campaignConfig),
    martialArtRows: listXianxiaCultivationMartialArtRows(config.dbPath, campaign, campaignConfig),
  });
  if (cultivationAction.status === "validation_error") {
    const error = validationError(cultivationAction.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const stateResult = updateCharacterCultivationDefinitionState(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    cultivationAction.definition,
    jsonPayload.payload,
    auth.actorUserId ?? 0,
  );
  if (stateResult.status === "state_conflict") {
    const error = stateConflict(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "validation_error") {
    const error = validationError(stateResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (stateResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const writeResult = await writeCampaignCharacterDefinitionFile(
    config,
    campaign.slug,
    characterSlug,
    cultivationAction.definition,
  );
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const cultivationPayload = buildCharacterCultivationShellPayload({
    campaign,
    characterSlug,
    definition: writeResult.record.definition,
    state: stateResult.state,
    genericTechniqueOptions: listXianxiaCreateGenericTechniqueOptions(
      config.dbPath,
      campaign,
      campaignConfig,
      xianxiaKnownGenericTechniqueOptionKeys(writeResult.record.definition),
    ),
  });

  return ctx.json({
    ok: true,
    campaign,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: writeResult.record.character_slug,
        revision: stateResult.revision,
        state: stateResult.state,
        updated_at: stateResult.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
    },
    lane: cultivationPayload.lane,
    supported: cultivationPayload.supported,
    message: cultivationAction.message,
    anchor: cultivationAction.anchor,
    unsupported_message: cultivationPayload.unsupported_message,
    cultivation: cultivationPayload.cultivation,
    links: cultivationPayload.links,
  });
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

app.post(ROUTES.characterControlsAssignment, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign || !supportsCharacterControlsRoutes(campaign.system)) {
    const error = campaignNotFound(campaignSlug);
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

  const auth = resolveCharacterControlsAssignmentWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = writeResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const rawTargetUserId = String(jsonPayload.payload.user_id ?? "").trim();
  if (!/^[+-]?\d+$/.test(rawTargetUserId)) {
    const error = validationError("Choose a valid player to assign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  const targetUserId = Number(rawTargetUserId);
  if (!Number.isSafeInteger(targetUserId)) {
    const error = validationError("Choose a valid player to assign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const targetUser = getActiveUserById(config.dbPath, targetUserId);
  if (!targetUser) {
    const error = validationError("Choose an active player account to assign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  if (!hasActivePlayerMembership(config.dbPath, targetUser.id, campaign.slug)) {
    const error = validationError("Character owners must have an active player membership in that campaign.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const previous = getCharacterAssignment(config.dbPath, campaign.slug, characterSlug);
  const assignment = upsertCharacterAssignment(config.dbPath, targetUser.id, campaign.slug, characterSlug);
  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId,
    targetUserId: targetUser.id,
    campaignSlug: campaign.slug,
    characterSlug,
    eventType: "character_assignment_created",
    metadata: {
      previous_user_id: previous?.user_id ?? null,
      assignment_type: assignment.assignment_type,
      source: "gen2_character_controls",
    },
  });

  return ctx.json(
    buildCharacterControlsPayload(
      campaign.slug,
      character,
      `Assigned ${characterSlug} to ${targetUser.email}.`,
    ),
  );
});

app.delete(ROUTES.characterControlsAssignment, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign || !supportsCharacterControlsRoutes(campaign.system)) {
    const error = campaignNotFound(campaignSlug);
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

  const auth = resolveCharacterControlsAssignmentWrite(ctx);
  if (auth.kind !== "authenticated") {
    const error = writeResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const assignment = getCharacterAssignment(config.dbPath, campaign.slug, characterSlug);
  if (!assignment) {
    const error = validationError("That character does not currently have an assigned player.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const removedAssignment = deleteCharacterAssignment(config.dbPath, campaign.slug, characterSlug);
  if (!removedAssignment) {
    const error = validationError("That character assignment no longer exists.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId,
    targetUserId: removedAssignment.user_id,
    campaignSlug: campaign.slug,
    characterSlug,
    eventType: "character_assignment_removed",
    metadata: {
      assignment_type: removedAssignment.assignment_type,
      source: "gen2_character_controls",
    },
  });

  return ctx.json(buildCharacterControlsPayload(campaign.slug, character, `Cleared assignment for ${characterSlug}.`));
});

app.delete(ROUTES.characterControlsDelete, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign || !supportsCharacterControlsRoutes(campaign.system)) {
    const error = campaignNotFound(campaignSlug);
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

  const auth = resolveCharacterControlsDeleteWrite(ctx, campaign.slug);
  if (auth.kind !== "authenticated") {
    const error = writeResolutionError(auth);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const confirmation = String(jsonPayload.payload.confirm_character_slug || "").trim();
  if (confirmation !== characterSlug) {
    const error = validationError(`Type ${characterSlug} to confirm deletion.`);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const previousAssignment = getCharacterAssignment(config.dbPath, campaign.slug, characterSlug);
  const result = await deleteCampaignContentCharacter(config, campaign.slug, characterSlug);
  if (result.status === "not_found") {
    const error = notFound("not_found", "That character no longer exists.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (result.status === "validation_error") {
    const error = validationError(result.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  insertAuthAuditLog(config.dbPath, {
    actorUserId: auth.actorUserId,
    targetUserId: previousAssignment?.user_id ?? null,
    campaignSlug: campaign.slug,
    characterSlug,
    eventType: "character_deleted",
    metadata: {
      deleted_files: result.deleted.deleted_files,
      deleted_state: result.deleted.deleted_state,
      deleted_assignment: result.deleted.deleted_assignment,
      deleted_assets: result.deleted.deleted_assets,
      source: "gen2_character_controls",
    },
  });

  return ctx.json({
    ok: true,
    message: `Deleted character ${characterDefinitionName(character)}.`,
    deleted_character_slug: characterSlug,
    deleted_character_name: characterDefinitionName(character),
    links: {
      gen2_roster_url: campaignHref(campaign.slug, "characters"),
      flask_roster_url: flaskCampaignHref(campaign.slug, "characters"),
    },
  });
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

app.patch(ROUTES.characterSheetEdit, async (ctx) => {
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
    const error = forbidden("You do not have permission to edit Character page state for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSheetEdit(
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

app.post(ROUTES.characterSessionXianxiaDaoImmolatingUseRequests, async (ctx) => {
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
    const error = forbidden("You do not have permission to request Dao Immolating use for this character.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionXianxiaDaoImmolatingUseRequest(
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

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: result.definition,
    import_metadata: buildManagedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  });
  if (writeResult.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
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

app.post(ROUTES.characterSessionXianxiaDaoImmolatingUseRecords, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const auth = resolveSessionManagerBearerWrite(
    ctx,
    campaign.slug,
    "Character session state writes require bearer API authentication.",
  );
  if (auth.kind === "error") {
    return ctx.json({ ok: auth.error.ok, error: auth.error.error }, auth.error.status);
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

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterSessionXianxiaDaoImmolatingUseRecord(
    config,
    campaign.slug,
    characterSlug,
    character.definition,
    jsonPayload.payload,
    auth.actor.id,
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

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: result.definition,
    import_metadata: buildManagedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  });
  if (writeResult.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
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
        updated_by_user_id: auth.actor.id,
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

app.patch(ROUTES.characterSessionEquipment, async (ctx) => {
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

  const result = updateCharacterSessionEquipment(
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

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: result.definition,
    import_metadata: character.import_metadata,
  });
  if (writeResult.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
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

app.patch(ROUTES.characterSessionArtificerInfusions, async (ctx) => {
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

  const result = updateCharacterSessionArtificerInfusions(
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

  const writeResult = await writeCampaignContentCharacter(config, campaign.slug, characterSlug, {
    definition: result.definition,
    import_metadata: character.import_metadata,
  });
  if (writeResult.status === "not_found") {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
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

app.put(ROUTES.characterPortraitUpdate, async (ctx) => {
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

  const preflight = validateCampaignContentCharacterPortraitUpload(jsonPayload.payload);
  if (preflight.status === "validation_error") {
    const error = validationError(preflight.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterPortraitRevision(
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

  const writeResult = await writeCampaignContentCharacterPortrait(
    config,
    campaign.slug,
    characterSlug,
    jsonPayload.payload,
    buildPreservedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  );
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
      portrait: writeResult.portrait,
    },
  });
});

app.delete(ROUTES.characterPortraitDelete, async (ctx) => {
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

  const profile =
    typeof character.definition.profile === "object" &&
    character.definition.profile !== null &&
    !Array.isArray(character.definition.profile)
      ? (character.definition.profile as Record<string, unknown>)
      : {};
  if (typeof profile.portrait_asset_ref !== "string" || !profile.portrait_asset_ref.trim()) {
    const error = validationError("That character does not currently have a portrait.");
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const jsonPayload = await readJsonObject(ctx);
  if (jsonPayload.status === "error") {
    const error = validationError(jsonPayload.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const result = updateCharacterPortraitRevision(
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

  const writeResult = await deleteCampaignContentCharacterPortrait(
    config,
    campaign.slug,
    characterSlug,
    buildPreservedCharacterImportMetadata(campaign.slug, characterSlug, character.import_metadata),
  );
  if (writeResult.status === "not_found") {
    const error = contentCharacterNotFound(campaign.slug, characterSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }
  if (writeResult.status === "validation_error") {
    const error = validationError(writeResult.message);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json({
    ok: true,
    character: {
      definition: writeResult.record.definition,
      import_metadata: writeResult.record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: characterSlug,
        revision: result.revision,
        state: result.state,
        updated_at: result.updatedAt,
        updated_by_user_id: auth.actorUserId ?? null,
      },
      portrait: null,
      deleted_portrait: writeResult.deleted,
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

app.post(ROUTES.characterSessionXianxiaInventoryAdd, async (ctx) => {
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

  const result = updateCharacterSessionXianxiaInventoryAdd(
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

app.delete(ROUTES.characterSessionXianxiaInventoryRemove, async (ctx) => {
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

  const result = updateCharacterSessionXianxiaInventoryRemove(
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

app.patch(ROUTES.characterSessionXianxiaInventoryItem, async (ctx) => {
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

  const result = updateCharacterSessionXianxiaInventoryItem(
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
  assertSqliteStartupSchema(config.dbPath);
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
  }).catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}

export function getApp() {
  return app;
}

export { startup };
export default app;
