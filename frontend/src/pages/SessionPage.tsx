import { useEffect, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { SessionPayload } from "../api/types";
import {
  coerceSessionPane,
  isAuthRequiredFromError as isAuthError,
  resolveSessionLivePayload,
  type SessionRoutePane,
} from "../sessionRouteState";
import { queryClient, useApiClient } from "../apiClientContext";
import { getApiErrorMessage } from "../apiErrors";
import { ApiErrorNotice } from "../components/feedback";
import { CharacterPane } from "./CharacterPane";
import { DmPane } from "./SessionDmPane";
import { SessionPane } from "./SessionRoutes";

type PaneName = SessionRoutePane;

export function SessionPage() {
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
