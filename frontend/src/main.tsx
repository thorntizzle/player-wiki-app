import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
  useLocation,
  useParams,
} from "@tanstack/react-router";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import "./styles.css";
import type {
  SessionPayload,
} from "./api/types";
import {
  coerceSessionPane,
  isAuthRequiredFromError as isAuthError,
  resolveSessionLivePayload,
  type SessionRoutePane,
} from "./sessionRouteState";
import {
  queryClient,
  useApiClient,
} from "./apiClientContext";
import { getApiErrorMessage } from "./apiErrors";
import { ApiErrorNotice } from "./components/feedback";
import { AccountSettingsPage } from "./routes/AccountSettingsPage";
import { CampaignControlPage } from "./routes/CampaignControlPage";
import { CampaignHelpPage } from "./routes/CampaignHelpPage";
import { WikiArticlePage, WikiHomePage, WikiSectionPage } from "./routes/WikiRoutes";
import {
  SystemsEntryPage,
  SystemsIndexPage,
  SystemsSourceCategoryPage,
  SystemsSourcePage,
} from "./routes/SystemsRoutes";
import { AdminDashboardPage, AdminUserDetailPage } from "./routes/AdminRoutes";
import { CampaignListPage } from "./routes/CampaignPickerPage";
import {
  CharacterAdvancedEditorPage,
  CharacterCreatePage,
  CharacterCultivationPage,
  CharacterLevelUpPage,
  CharacterProgressionRepairPage,
  CharacterRetrainingPage,
  CharacterXianxiaManualImportPage,
} from "./routes/CharacterAuthoringRoutes";
import { CharacterPane } from "./routes/CharacterPane";
import { DmContentPage } from "./routes/DmContentPage";
import { CombatPage } from "./routes/CombatPage";
import { DmPane } from "./routes/SessionDmPane";
import { AppShell } from "./AppShell";
import { CharacterRosterPage } from "./routes/CharacterRosterPage";
import { SessionPane } from "./routes/SessionRoutes";
import { normalizeCharacterSection } from "./characterPaneUtils";

declare global {
  interface Window {
    __cpwAppLoadingBegin?: () => void;
    __cpwAppLoadingReady?: () => void;
  }
}

type PaneName = SessionRoutePane;
function CharacterDetailPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug",
  });
  const location = useLocation();
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const initialSection = normalizeCharacterSection(new URLSearchParams(location.search).get("page"));

  return (
    <CharacterPane
      campaignSlug={campaignSlug}
      initialCharacterSlug={characterSlug}
      initialSection={initialSection}
      surface="read"
      onSelectedCharacterChange={(nextSlug) => {
        window.history.pushState(
          null,
          "",
          `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(nextSlug)}`,
        );
      }}
    />
  );
}

function SessionPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/session",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { setAuthRequired } = useApiClient();
  const { apiClient } = useApiClient();
  const [activePane, setActivePane] = useState<PaneName>("session");

  const sessionQuery = useQuery({
    queryKey: ["session", resolvedCampaignSlug],
    queryFn: async () => {
      const previous = queryClient.getQueryData<SessionPayload>(["session", resolvedCampaignSlug]);
      const response = await apiClient.getSessionLiveState(
        resolvedCampaignSlug,
        previous
          ? {
              sessionRevision: previous.session_revision,
              sessionViewToken: previous.session_view_token,
            }
          : undefined,
      );
      const resolution = resolveSessionLivePayload(previous, response);
      if (resolution.state === "needs-refresh") {
        return apiClient.getSession(resolvedCampaignSlug);
      }
      return resolution.payload;
    },
    enabled: Boolean(resolvedCampaignSlug),
    refetchInterval: (query) => {
      return query.state.data?.active_session?.is_active ? 3000 : 8000;
    },
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sessionQuery.error)) {
      setAuthRequired(true);
    }
  }, [sessionQuery.error, setAuthRequired]);

  const payload = sessionQuery.data;
  const canManage = payload?.permissions.can_manage_session ?? false;
  const sessionIsActive = Boolean(payload?.active_session?.is_active);
  const sessionStatusLabel = sessionIsActive ? "Session active" : "Session inactive";

  useEffect(() => {
    setActivePane((previousActivePane) => coerceSessionPane(previousActivePane, canManage));
  }, [canManage]);

  const paneError = getApiErrorMessage(sessionQuery.error);

  return (
    <section className="session-page-shell">
      <section className="hero compact session-hero">
        <p className="eyebrow">Session Workspace</p>
        <div className="session-hero__title-row">
          <h1>Session</h1>
          <span
            className={
              sessionIsActive
                ? "session-hero__status session-hero__status--active"
                : "session-hero__status session-hero__status--inactive"
            }
            data-session-header-status
          >
            <span className="session-hero__status-dot" aria-hidden="true" />
            {sessionStatusLabel}
          </span>
        </div>
        <p className="lede">Live play workspace.</p>
        <div className="hero-actions session-tab-strip">
          <button
            type="button"
            className={activePane === "session" ? "tab-button button-link" : "tab-button ghost-button"}
            onClick={() => setActivePane("session")}
          >
            Session
          </button>
          <button
            type="button"
            className={activePane === "character" ? "tab-button button-link" : "tab-button ghost-button"}
            onClick={() => setActivePane("character")}
          >
            Character
          </button>
          {canManage ? (
            <button
              type="button"
              className={activePane === "dm" ? "tab-button button-link" : "tab-button ghost-button"}
              onClick={() => setActivePane("dm")}
            >
              DM
            </button>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice
        isLoading={sessionQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />

      <div className="pane-stack">
        <div className={activePane === "session" ? "pane pane-visible" : "pane pane-hidden"}>
          <SessionPane
            campaignSlug={resolvedCampaignSlug}
            payload={payload}
            refetch={() => sessionQuery.refetch()}
            setAuthRequired={setAuthRequired}
          />
        </div>
        <div className={activePane === "character" ? "pane pane-visible" : "pane pane-hidden"}>
          <CharacterPane campaignSlug={resolvedCampaignSlug} />
        </div>
        {canManage ? (
          <div className={activePane === "dm" ? "pane pane-visible" : "pane pane-hidden"}>
            <DmPane
              campaignSlug={resolvedCampaignSlug}
              payload={payload}
              refetch={() => sessionQuery.refetch()}
              setAuthRequired={setAuthRequired}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}

const rootRoute = createRootRoute({
  component: AppShell,
});

const campaignsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: CampaignListPage,
});

const accountSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: AccountSettingsPage,
});

const adminDashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: AdminDashboardPage,
});

const adminUserDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users/$userId",
  component: AdminUserDetailPage,
});

const campaignHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug",
  component: WikiHomePage,
});

const campaignHelpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/help",
  component: CampaignHelpPage,
});

const campaignControlRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/control",
  component: CampaignControlPage,
});

const campaignWikiSectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/sections/$sectionSlug",
  component: WikiSectionPage,
});

const campaignWikiPageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/pages/$",
  component: WikiArticlePage,
});

const campaignSystemsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems",
  component: SystemsIndexPage,
});

const campaignSystemsSourceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId",
  component: SystemsSourcePage,
});

const campaignSystemsSourceCategoryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType",
  component: SystemsSourceCategoryPage,
});

const campaignSystemsEntryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/entries/$entrySlug",
  component: SystemsEntryPage,
});

const campaignCharacterRosterRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters",
  component: CharacterRosterPage,
});

const campaignCharacterCreateRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/new",
  component: CharacterCreatePage,
});

const campaignCharacterXianxiaManualImportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/import/xianxia-manual",
  component: CharacterXianxiaManualImportPage,
});

const campaignCharacterAdvancedEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/edit",
  component: CharacterAdvancedEditorPage,
});

const campaignCharacterRetrainingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/retraining",
  component: CharacterRetrainingPage,
});

const campaignCharacterLevelUpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/level-up",
  component: CharacterLevelUpPage,
});

const campaignCharacterProgressionRepairRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair",
  component: CharacterProgressionRepairPage,
});

const campaignCharacterCultivationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation",
  component: CharacterCultivationPage,
});

const campaignCharacterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug",
  component: CharacterDetailPage,
});

const campaignCombatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/combat",
  component: CombatPage,
});

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const campaignDmContentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/dm-content",
  component: DmContentPage,
});

const routeTree = rootRoute.addChildren([
  campaignsRoute,
  accountSettingsRoute,
  adminDashboardRoute,
  adminUserDetailRoute,
  campaignHomeRoute,
  campaignHelpRoute,
  campaignControlRoute,
  campaignWikiSectionRoute,
  campaignWikiPageRoute,
  campaignSystemsRoute,
  campaignSystemsSourceRoute,
  campaignSystemsSourceCategoryRoute,
  campaignSystemsEntryRoute,
  campaignCharacterRosterRoute,
  campaignCharacterCreateRoute,
  campaignCharacterXianxiaManualImportRoute,
  campaignCharacterAdvancedEditorRoute,
  campaignCharacterRetrainingRoute,
  campaignCharacterLevelUpRoute,
  campaignCharacterProgressionRepairRoute,
  campaignCharacterCultivationRoute,
  campaignCharacterDetailRoute,
  campaignCombatRoute,
  campaignSessionRoute,
  campaignDmContentRoute,
]);
const router = createRouter({
  routeTree,
  basepath: "/app-next",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (root !== null) {
  createRoot(root).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
