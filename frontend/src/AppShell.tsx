import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useIsFetching, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";

import { CampaignApiClient } from "./api/client";
import type { CampaignReferenceSearchResult, CampaignVisibilityMap } from "./api/types";
import { ApiClientContext, queryClient, useApiClient } from "./apiClientContext";
import { appNextHrefToRouterPath, campaignRouteHref, normalizeFrontendMode, routeFrontendMode } from "./campaignLinks";
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

function CampaignGlobalSearch({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [query, setQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [results, setResults] = useState<CampaignReferenceSearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isDialogOpen, setDialogOpen] = useState(false);

  const searchDebounceTimer = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const searchAbortController = useRef<AbortController | null>(null);
  const previewAbortController = useRef<AbortController | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  const clearSearchState = (status: string) => {
    setStatusMessage(status);
    setResults([]);
    setShowResults(false);
  };

  const clearPendingSearch = () => {
    if (searchDebounceTimer.current !== null) {
      window.clearTimeout(searchDebounceTimer.current);
      searchDebounceTimer.current = null;
    }
    if (searchAbortController.current) {
      searchAbortController.current.abort();
      searchAbortController.current = null;
    }
  };

  const runSearch = async (rawQuery: string) => {
    const trimmedQuery = rawQuery.trim();
    if (!trimmedQuery) {
      clearSearchState("");
      return;
    }
    if (trimmedQuery.length < 2) {
      clearSearchState("Type at least 2 letters to search.");
      return;
    }

    if (searchAbortController.current) {
      searchAbortController.current.abort();
    }
    const controller = new AbortController();
    searchAbortController.current = controller;
    setStatusMessage("Searching...");
    setShowResults(false);

    try {
      const response = await apiClient.searchCampaignReferences(campaignSlug, trimmedQuery, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setResults(response.results);
      setShowResults(response.results.length > 0);
      setStatusMessage(response.message || "Search complete.");
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setResults([]);
      setShowResults(false);
      setStatusMessage("Could not search campaign references right now.");
    } finally {
      if (searchAbortController.current === controller) {
        searchAbortController.current = null;
      }
    }
  };

  const onQuerySubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearPendingSearch();
    void runSearch(query);
  };

  const onQueryInput = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.currentTarget.value;
    if (searchAbortController.current) {
      searchAbortController.current.abort();
      searchAbortController.current = null;
    }
    setQuery(next);
    setStatusMessage("");
    clearSearchState("");
    if (searchDebounceTimer.current !== null) {
      window.clearTimeout(searchDebounceTimer.current);
      searchDebounceTimer.current = null;
    }
    const trimmedQuery = next.trim();
    if (!trimmedQuery) {
      return;
    }
    if (trimmedQuery.length < 2) {
      setStatusMessage("Type at least 2 letters to search.");
      return;
    }

    searchDebounceTimer.current = window.setTimeout(() => {
      void runSearch(next);
    }, 250);
  };

  const onQueryKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearPendingSearch();
      void runSearch(query);
    }
  };

  const openDialog = () => {
    setDialogOpen(true);
    window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus({ preventScroll: true });
    });
  };

  const closeDialog = () => {
    if (previewAbortController.current) {
      previewAbortController.current.abort();
      previewAbortController.current = null;
    }
    setDialogOpen(false);
    setPreviewError(null);
    setPreviewHtml("");
    setPreviewLoading(false);

    const focusTarget = returnFocusRef.current;
    if (focusTarget && document.contains(focusTarget)) {
      focusTarget.focus({ preventScroll: true });
    }
    returnFocusRef.current = null;
  };

  const openPreview = (result: CampaignReferenceSearchResult, trigger: HTMLElement | null) => {
    const resultId = result.result_id.trim();
    if (!resultId) {
      return;
    }

    returnFocusRef.current = trigger;
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewHtml("");
    openDialog();

    if (previewAbortController.current) {
      previewAbortController.current.abort();
    }
    const controller = new AbortController();
    previewAbortController.current = controller;

    apiClient
      .previewCampaignReference(campaignSlug, resultId, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) {
          return;
        }
        setPreviewHtml(response.preview_html || "");
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isAuthError(error)) {
          setAuthRequired(true);
        }
        setPreviewError("Could not load that reference right now.");
      })
      .finally(() => {
        if (previewAbortController.current === controller) {
          previewAbortController.current = null;
        }
        if (!controller.signal.aborted) {
          setPreviewLoading(false);
        }
      });
  };

  useEffect(() => {
    if (!campaignSlug) {
      setQuery("");
      clearSearchState("");
      return;
    }
    setQuery("");
    clearSearchState("");
    setPreviewError(null);
    setPreviewHtml("");
    setPreviewLoading(false);
    setDialogOpen(false);
    if (previewAbortController.current) {
      previewAbortController.current.abort();
      previewAbortController.current = null;
    }

    return () => {
      clearPendingSearch();
      if (previewAbortController.current) {
        previewAbortController.current.abort();
        previewAbortController.current = null;
      }
    };
  }, [campaignSlug]);

  return (
    <section className="campaign-global-search" aria-label="Global campaign search">
      <form className="campaign-global-search__form" onSubmit={onQuerySubmit}>
        <label className="campaign-global-search__field">
          <span className="sr-only">Search wiki or Systems</span>
          <input
            type="search"
            value={query}
            autoComplete="off"
            placeholder="Search wiki or Systems"
            onChange={onQueryInput}
            onKeyDown={onQueryKeyDown}
          />
        </label>
        <button type="submit">Search</button>
      </form>
      <p className="meta campaign-global-search__status" aria-live="polite">
        {statusMessage}
      </p>
      {showResults ? (
        <div className="campaign-global-search__results">
          <div className="campaign-global-search-result-list">
            {results.map((result) => {
              const meta = result.subtitle ? `${result.kind_label} | ${result.subtitle}` : result.kind_label;
              return (
                <button
                  type="button"
                  className="campaign-global-search-result"
                  key={result.result_id}
                  onClick={(event) => {
                    openPreview(result, event.currentTarget);
                  }}
                >
                  <span className="campaign-global-search-result__title">{result.title}</span>
                  <span className="campaign-global-search-result__meta">{meta}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      {isDialogOpen ? (
        <div className="detail-modal-backdrop" role="presentation" onMouseDown={closeDialog}>
          <section
            className="spell-detail-dialog campaign-global-search-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="campaign-search-preview-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="spell-detail-dialog__panel campaign-global-search-dialog__panel">
              <header className="spell-detail-dialog__header">
                <div>
                  <p className="eyebrow">Reference preview</p>
                  <h2 id="campaign-search-preview-title">Campaign Search</h2>
                </div>
                <button type="button" className="ghost-button" ref={closeButtonRef} onClick={closeDialog}>
                  Close
                </button>
              </header>
              <div
                className="campaign-global-search-dialog__body"
                aria-live="polite"
                aria-busy={previewLoading ? "true" : "false"}
              >
                {previewLoading ? <p className="status status-neutral">Loading reference preview...</p> : null}
                {previewError ? <p className="status status-error">{previewError}</p> : null}
                {previewHtml ? <div dangerouslySetInnerHTML={{ __html: previewHtml }} /> : null}
                {!previewLoading && !previewError && !previewHtml ? (
                  <p className="status status-neutral">No reference preview is available.</p>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function AuthNotice() {
  const { authRequired, setApiToken } = useApiClient();
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  if (!authRequired) {
    return null;
  }

  return (
    <section className="card auth-notice">
      <div className="section-heading">
        <div>
          <h2>Authentication required</h2>
          <p className="status status-error">
            Your cookie or API token did not authenticate this request. Sign in to restore session.
          </p>
        </div>
      </div>
      <div className="hero-actions">
        <a className="button-link" href={signInHref}>
          Sign in
        </a>
        <button type="button" className="ghost-button" onClick={() => setApiToken("")}>
          Continue without token
        </button>
      </div>
    </section>
  );
}
function useAppLoadingReadiness(locationPathname: string) {
  const activeFetchCount = useIsFetching();
  const previousLocationPathname = useRef<string | null>(null);
  const readyTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (previousLocationPathname.current === null) {
      previousLocationPathname.current = locationPathname;
      return;
    }
    if (previousLocationPathname.current !== locationPathname) {
      previousLocationPathname.current = locationPathname;
      window.__cpwAppLoadingBegin?.();
    }
  }, [locationPathname]);

  useEffect(() => {
    if (readyTimerRef.current !== null) {
      window.clearTimeout(readyTimerRef.current);
      readyTimerRef.current = null;
    }

    if (activeFetchCount > 0) {
      return undefined;
    }

    readyTimerRef.current = window.setTimeout(() => {
      if (queryClient.isFetching() === 0) {
        window.__cpwAppLoadingReady?.();
      }
      readyTimerRef.current = null;
    }, 180);

    return () => {
      if (readyTimerRef.current !== null) {
        window.clearTimeout(readyTimerRef.current);
        readyTimerRef.current = null;
      }
    };
  }, [activeFetchCount, locationPathname]);
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  useAppLoadingReadiness(location.pathname);
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
          <Outlet />
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}
