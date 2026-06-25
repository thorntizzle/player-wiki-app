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
];

export const ROUTES = {
  healthz: IMPLEMENTED_ROUTES[0].honoPath,
  campaignDetail: IMPLEMENTED_ROUTES[1].honoPath,
} as const;
