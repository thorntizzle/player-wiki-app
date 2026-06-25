import path from "node:path";
import { promises as fs } from "node:fs";
import { fileURLToPath } from "node:url";

import { Hono } from "hono";
import { serve } from "@hono/node-server";

import { getApiConfig } from "./config.js";
import { getCampaignBySlug, listCampaignSlugs } from "./campaigns/repository.js";
import { ROUTES } from "./routes.js";
import { buildSessionStatePayload } from "./session/view.js";
import { getCampaignConfigFile } from "./content/repository.js";
import { buildCampaignConfigPayload } from "./content/view.js";
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
  status: 404 | 400 | 500,
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
