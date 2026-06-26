import path from "node:path";
import { promises as fs } from "node:fs";
import { fileURLToPath } from "node:url";

import { Hono, type Context } from "hono";
import { serve } from "@hono/node-server";

import { getApiConfig } from "./config.js";
import { getCampaignBySlug, listCampaigns, listCampaignSlugs } from "./campaigns/repository.js";
import { buildCampaignHelpPayload } from "./help/view.js";
import { ROUTES } from "./routes.js";
import { buildSessionStatePayload } from "./session/view.js";
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
  getCampaignContentAsset,
  getCampaignContentCharacter,
  getCampaignContentPage,
  listCampaignContentAssets,
  listCampaignContentCharacters,
  listCampaignContentPages,
  sanitizeContentAssetRef,
  sanitizeContentCharacterSlug,
  sanitizeContentPageRef,
} from "./content/repository.js";
import {
  buildCampaignConfigPayload,
  buildContentAssetDetailPayload,
  buildContentAssetListPayload,
  buildContentCharacterDetailPayload,
  buildContentCharacterListPayload,
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
  status: 404 | 400 | 401 | 403 | 500,
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

function hasFixtureAdminAuth(ctx: { req: { header: (name: string) => string | undefined } }): boolean {
  return fixtureRole(ctx) === "admin";
}

function fixtureRole(ctx: { req: { header: (name: string) => string | undefined } }): FixtureSystemsRole | null {
  const role = (ctx.req.header("X-CPW-Fixture-Role") || "").trim().toLowerCase();
  if (role === "player" || role === "dm" || role === "admin") {
    return role;
  }
  return null;
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

function contentPageNotFound(campaignSlug: string, pageRef: string) {
  return jsonError(
    "content_page_not_found",
    `Could not find content page '${pageRef}' in campaign '${campaignSlug}'.`,
    404,
    { campaign_slug: campaignSlug, page_ref: pageRef },
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

app.get(ROUTES.systemsImportRuns, async (ctx) => {
  if (!hasFixtureAdminAuth(ctx)) {
    const error = authRequired();
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
  if (!hasFixtureAdminAuth(ctx)) {
    const error = authRequired();
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

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

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

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

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

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

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

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

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

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

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

  const role = fixtureRole(ctx);
  if (!role) {
    const error = authRequired();
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

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

  const payload = buildSessionStatePayload(campaign);
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

app.get(ROUTES.campaignConfig, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaignConfig = await getCampaignConfigFile(config, campaignSlug);
  if (!campaignConfig) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildCampaignConfigPayload(campaignConfig));
});

app.get(ROUTES.contentAssets, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
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

app.get(ROUTES.contentPages, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  const pages = await listCampaignContentPages(config, campaignSlug);
  if (!pages) {
    const error = campaignNotFound(campaignSlug);
    return ctx.json({ ok: error.ok, error: error.error }, error.status);
  }

  return ctx.json(buildContentPageListPayload(pages));
});

app.get(ROUTES.contentPage, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
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

  return ctx.json(buildContentPageDetailPayload(page));
});

app.get(ROUTES.contentCharacters, async (ctx) => {
  const campaignSlug = ctx.req.param("campaignSlug") || "";
  const campaign = await getCampaignBySlug(config, campaignSlug);
  if (!campaign) {
    const error = campaignNotFound(campaignSlug);
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
