import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { ChangeEvent } from "react";

import { CampaignApiClient } from "./api/client";
import type { CampaignVisibilityMap } from "./api/types";
import { ApiClientContext, queryClient } from "./apiClientContext";
import { RouteSuspenseFallback, useAppLoadingReadiness } from "./appLoadingReadiness";
import { appNextHrefToRouterPath, campaignRouteHref, normalizeFrontendMode, routeFrontendMode } from "./campaignLinks";
import { AuthNotice } from "./components/AuthNotice";
import { CampaignGlobalSearch } from "./components/CampaignGlobalSearch";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";

function parseCampaignSlugFromPath(pathname: string): string {
  const appNextMatch = pathname.match(/^\/app-next\/campaigns\/([^/?#]+)/);
  if (appNextMatch && appNextMatch[1]) {
    return decodeURIComponent(appNextMatch[1]);
  }
  const routedMatch = pathname.match(/^\/campaigns\/([^/?#]+)/);
  if (routedMatch && routedMatch[1]) {
    return decodeURIComponent(routedMatch[1]);
  }
  return "";
}

function campaignVisibilityCanAccess(visibility: CampaignVisibilityMap | undefined, scope: string): boolean {
  return Boolean(visibility?.[scope]?.can_access);
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const [routeSuspensePending, setRouteSuspensePending] = useState(false);
  useAppLoadingReadiness(location.pathname, routeSuspensePending);
  const [apiToken, setApiToken] = useState(() => {
    try {
      return localStorage.getItem("cpw-pilot-api-token") || "";
    } catch {
      return "";
    }
  });
  const [authRequired, setAuthRequired] = useState(false);
  const [navigationLabel, setNavigationLabel] = useState<string | null>(null);
  const hasMounted = useRef(false);

  const apiClient = useMemo(() => {
    return new CampaignApiClient({
      bearerToken: apiToken,
    });
  }, [apiToken]);

  useEffect(() => {
    if (!hasMounted.current) {
      hasMounted.current = true;
      return;
    }
    void queryClient.invalidateQueries();
  }, [apiToken]);

  const setStoredToken = (next: string) => {
    const trimmed = next.trim();
    setApiToken(trimmed);
    try {
      if (trimmed) {
        localStorage.setItem("cpw-pilot-api-token", trimmed);
      } else {
        localStorage.removeItem("cpw-pilot-api-token");
      }
    } catch {
      // localStorage may be unavailable in private mode.
    }
    if (authRequired) {
      setAuthRequired(false);
    }
  };

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await apiClient.getMe();
      } catch (error) {
        if (isAuthError(error)) {
          return null;
        }
        throw error;
      }
    },
    retry: false,
  });

  const campaignSlug = parseCampaignSlugFromPath(location.pathname);
  const campaignQuery = useQuery({
    queryKey: ["campaign", campaignSlug],
    queryFn: () => apiClient.getCampaign(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(campaignQuery.error) || (Boolean(apiToken) && isAuthError(meQuery.error))) {
      setAuthRequired(true);
    }
  }, [apiToken, campaignQuery.error, meQuery.error, setAuthRequired]);

  useEffect(() => {
    const themeKey = meQuery.data?.preferences?.theme_key;
    if (themeKey) {
      document.documentElement.dataset.theme = themeKey;
    }
  }, [meQuery.data?.preferences?.theme_key]);

  const user = meQuery.data?.user ?? null;
  const preferredFrontendMode = normalizeFrontendMode(meQuery.data?.preferences?.frontend_mode);
  const campaign = campaignQuery.data?.campaign;
  const campaignPermissions = campaignQuery.data?.permissions;
  const campaignVisibility = campaignQuery.data?.visibility;
  const encodedCampaignSlug = encodeURIComponent(campaignSlug);
  const shellRouteMode = useMemo(
    () => routeFrontendMode(preferredFrontendMode),
    [location.pathname, preferredFrontendMode],
  );

  const navItems = useMemo(
    () => [
      {
        href: campaignRouteHref(campaignSlug, "", shellRouteMode),
        label: "Campaign Home",
        isGen2: shellRouteMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "campaign"),
      },
      {
        href: campaignRouteHref(campaignSlug, "session", shellRouteMode),
        label: "Session",
        isGen2: shellRouteMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "session"),
      },
      {
        href: campaignRouteHref(campaignSlug, "combat", shellRouteMode),
        label: "Combat",
        isGen2: shellRouteMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "combat"),
      },
      {
        href: campaignRouteHref(campaignSlug, "characters", shellRouteMode),
        label: "Characters",
        isGen2: shellRouteMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "characters"),
      },
      {
        href: campaignRouteHref(campaignSlug, "systems", shellRouteMode),
        label: "Systems",
        isGen2: shellRouteMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "systems"),
      },
      {
        href: campaignRouteHref(campaignSlug, "dm-content", shellRouteMode),
        label: "DM Content",
        isGen2: shellRouteMode === "gen2",
        show:
          campaignVisibilityCanAccess(campaignVisibility, "dm_content")
          || campaignPermissions?.can_manage_dm_content === true
          || campaignPermissions?.can_manage_content === true,
      },
      {
        href: campaignRouteHref(campaignSlug, "control", shellRouteMode),
        label: "Control",
        isGen2: shellRouteMode === "gen2",
        show: campaignPermissions?.can_manage_visibility === true,
      },
      {
        href: campaignRouteHref(campaignSlug, "help", shellRouteMode),
        label: "Help",
        isGen2: shellRouteMode === "gen2",
        show: Boolean(campaignQuery.data),
      },
    ],
    [
      campaignPermissions?.can_manage_content,
      campaignPermissions?.can_manage_dm_content,
      campaignPermissions?.can_manage_visibility,
      campaignQuery.data,
      campaignVisibility,
      campaignSlug,
      shellRouteMode,
    ],
  );

  const visibleNavItems = navItems.filter((entry) => entry.show);
  const nextUrl = `${window.location.pathname}${window.location.search}`;
  const signInHref = `/sign-in?next=${encodeURIComponent(nextUrl)}`;
  const currentAppPath = `/app-next${location.pathname}`;
  const campaignBasePath = `/app-next/campaigns/${encodedCampaignSlug}`;
  const isNavItemActive = (label: string, href: string) => {
    if (label === "Campaign Home") {
      return currentAppPath === campaignBasePath;
    }
    if (label === "Session") {
      return currentAppPath === `${campaignBasePath}/session`;
    }
    if (label === "Combat") {
      return currentAppPath.startsWith(`${campaignBasePath}/combat`);
    }
    if (label === "Characters") {
      return currentAppPath.startsWith(`${campaignBasePath}/characters`);
    }
    if (label === "Systems") {
      return currentAppPath.startsWith(`${campaignBasePath}/systems`);
    }
    if (label === "DM Content") {
      return currentAppPath.startsWith(`${campaignBasePath}/dm-content`);
    }
    if (label === "Control") {
      return currentAppPath === `${campaignBasePath}/control`;
    }
    if (label === "Help") {
      return currentAppPath === `${campaignBasePath}/help`;
    }
    return currentAppPath === href || currentAppPath.startsWith(`${href}/`);
  };

  return (
    <ApiClientContext.Provider
      value={{
        apiClient,
        apiToken,
        setApiToken: setStoredToken,
        authRequired,
        setAuthRequired,
        preferredFrontendMode,
        user,
      }}
    >
      <div className="session-shell">
        <header className={campaign ? "topbar topbar--campaign" : "topbar"}>
          <div className="brand-block">
            <Link to="/" className="brand-link">
              Campaign Player Wiki
            </Link>
          </div>
          {campaign ? (
            <div className="topbar-campaign" aria-label="Current campaign">
              <span>{campaign.title}</span>
            </div>
          ) : null}
          <div className="topbar-controls">
            <details className="api-token-details">
              <summary>API token</summary>
              <label className="token-row" htmlFor="pilot-api-token">
                <span>Optional bearer token for API-only testing</span>
                <input
                  id="pilot-api-token"
                  type="password"
                  value={apiToken}
                  placeholder="Bearer token"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    setStoredToken(event.currentTarget.value);
                  }}
                />
              </label>
            </details>
            <div className="account-row">
              {user ? (
                <>
                  {user.is_admin ? (
                    <a className="header-link" href="/app-next/admin">
                      Admin
                    </a>
                  ) : null}
                  <a className="header-link" href="/app-next/account">
                    Account
                  </a>
                  <span className="user-badge">
                    {user.display_name}
                    {user.is_admin ? <span className="meta">Admin</span> : null}
                  </span>
                  <form method="post" action="/sign-out">
                    <button type="submit" className="ghost-button">
                      Sign out
                    </button>
                  </form>
                </>
              ) : (
                <a className="ghost-button" href={signInHref}>
                  Sign in
                </a>
              )}
            </div>
          </div>
        </header>
        {campaign ? (
          <div className="campaign-nav-row">
            <nav className="campaign-nav-strip" aria-label="Campaign navigation">
              {visibleNavItems.map((item) => (
                <a
                  key={item.label}
                  className={isNavItemActive(item.label, item.href) ? "campaign-nav-link is-active" : "campaign-nav-link"}
                  href={item.href}
                  onClick={(event) => {
                    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                      return;
                    }
                    if (item.isGen2) {
                      event.preventDefault();
                      window.__cpwAppLoadingBegin?.();
                      void navigate({ to: appNextHrefToRouterPath(item.href) as never });
                    } else {
                      setNavigationLabel(item.label);
                    }
                  }}
                >
                  {item.label}
                </a>
              ))}
            </nav>
            {navigationLabel ? (
              <p className="navigation-status" role="status">
                Loading {navigationLabel}...
              </p>
            ) : null}
          </div>
        ) : null}
        {campaign ? <CampaignGlobalSearch campaignSlug={campaignSlug} /> : null}
        <AuthNotice />
        <main className="main-shell">
          <React.Suspense fallback={<RouteSuspenseFallback setRouteSuspensePending={setRouteSuspensePending} />}>
            <Outlet />
          </React.Suspense>
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}
