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
];

export const ROUTES = {
  healthz: IMPLEMENTED_ROUTES[0].honoPath,
  campaignDetail: IMPLEMENTED_ROUTES[1].honoPath,
  wikiHome: IMPLEMENTED_ROUTES[2].honoPath,
  wikiSection: IMPLEMENTED_ROUTES[3].honoPath,
  wikiPage: IMPLEMENTED_ROUTES[4].honoPath,
} as const;
