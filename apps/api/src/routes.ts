export type ImplementedRouteMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ImplementedRoute {
  method: ImplementedRouteMethod;
  honoPath: string;
  snapshotFamily: "api_v1" | "flask";
  snapshotPath: string;
  seedPath: string;
  routeFamily: string;
  missingResource?: {
    method: ImplementedRouteMethod;
    path: string;
    status: number;
    contentType: string;
    errorCode: string;
  };
}

export const IMPLEMENTED_ROUTES: ImplementedRoute[] = [
  {
    method: "GET",
    honoPath: "/healthz",
    snapshotFamily: "flask",
    snapshotPath: "/healthz",
    seedPath: "/healthz",
    routeFamily: "ops",
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>",
    seedPath: "/api/v1/campaigns/<campaign_slug>",
    routeFamily: "api_v1_campaigns",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/wiki",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/wiki",
    seedPath: "/api/v1/campaigns/<campaign_slug>/wiki",
    routeFamily: "api_v1_wiki",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign/wiki",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/wiki/sections/:sectionSlug",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/wiki/sections/<section_slug>",
    seedPath: "/api/v1/campaigns/<campaign_slug>/wiki/sections/<section_slug>",
    routeFamily: "api_v1_wiki",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/linden-pass/wiki/sections/definitely-not-a-section",
      status: 404,
      contentType: "application/json",
      errorCode: "wiki_section_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/wiki/pages/*",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/wiki/pages/<path:page_slug>",
    seedPath: "/api/v1/campaigns/<campaign_slug>/wiki/pages/<path:page_slug>",
    routeFamily: "api_v1_wiki",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/linden-pass/wiki/pages/definitely-not-a-page",
      status: 404,
      contentType: "application/json",
      errorCode: "wiki_page_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/session",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/session",
    seedPath: "/api/v1/campaigns/<campaign_slug>/session",
    routeFamily: "api_v1_session",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign/session",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/config",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/config",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/config",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign/content/config",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/pages",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/pages",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/pages",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign/content/pages",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/assets",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/assets",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/assets",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign/content/assets",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/assets/*",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/assets/<path:asset_ref>",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/assets/<path:asset_ref>",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/linden-pass/content/assets/definitely-not-an-asset.png",
      status: 404,
      contentType: "application/json",
      errorCode: "content_asset_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/pages/*",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/pages/<path:page_ref>",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/pages/<path:page_ref>",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/linden-pass/content/pages/definitely-not-a-page",
      status: 404,
      contentType: "application/json",
      errorCode: "content_page_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/characters",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/characters",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/characters",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/definitely-not-a-campaign/content/characters",
      status: 404,
      contentType: "application/json",
      errorCode: "campaign_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns/:campaignSlug/content/characters/:characterSlug",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>",
    seedPath: "/api/v1/campaigns/<campaign_slug>/content/characters/<character_slug>",
    routeFamily: "api_v1_content",
    missingResource: {
      method: "GET",
      path: "/api/v1/campaigns/linden-pass/content/characters/missing-character",
      status: 404,
      contentType: "application/json",
      errorCode: "content_character_not_found",
    },
  },
  {
    method: "GET",
    honoPath: "/api/v1/campaigns",
    snapshotFamily: "api_v1",
    snapshotPath: "/api/v1/campaigns",
    seedPath: "/api/v1/campaigns",
    routeFamily: "api_v1_campaigns",
  },
];

export const ROUTES = {
  healthz: IMPLEMENTED_ROUTES[0].honoPath,
  campaignDetail: IMPLEMENTED_ROUTES[1].honoPath,
  wikiHome: IMPLEMENTED_ROUTES[2].honoPath,
  wikiSection: IMPLEMENTED_ROUTES[3].honoPath,
  wikiPage: IMPLEMENTED_ROUTES[4].honoPath,
  sessionState: IMPLEMENTED_ROUTES[5].honoPath,
  campaignConfig: IMPLEMENTED_ROUTES[6].honoPath,
  contentPages: IMPLEMENTED_ROUTES[7].honoPath,
  contentAssets: IMPLEMENTED_ROUTES[8].honoPath,
  contentAsset: IMPLEMENTED_ROUTES[9].honoPath,
  contentPage: IMPLEMENTED_ROUTES[10].honoPath,
  contentCharacters: IMPLEMENTED_ROUTES[11].honoPath,
  contentCharacter: IMPLEMENTED_ROUTES[12].honoPath,
  campaignList: IMPLEMENTED_ROUTES[13].honoPath,
} as const;
