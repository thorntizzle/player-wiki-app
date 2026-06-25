import path from "node:path";
import { fileURLToPath } from "node:url";

import { Hono } from "hono";
import { serve } from "@hono/node-server";

import { getApiConfig } from "./config.js";
import { getCampaignBySlug, listCampaignSlugs } from "./campaigns/repository.js";
import { ROUTES } from "./routes.js";

const app = new Hono();

const config = getApiConfig();

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
