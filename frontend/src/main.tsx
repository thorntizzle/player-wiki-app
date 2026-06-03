import React, { createContext, useContext, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Link, createRootRoute, createRoute, createRouter, RouterProvider, Outlet, useParams } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";
import "./styles.css";
import { CampaignApiClient, apiErrorMessage, isApiError } from "./api/client";
import type { CampaignEntry, SessionMessage, SessionPayload } from "./api/types";

interface ApiClientContextValue {
  apiClient: CampaignApiClient;
  apiToken: string;
  setApiToken: (token: string) => void;
}

interface ApiMessage {
  status: number;
  message: string;
}

const ApiClientContext = createContext<ApiClientContextValue | null>(null);

function useApiClient(): ApiClientContextValue {
  const context = useContext(ApiClientContext);
  if (context === null) {
    throw new Error("CampaignApiClient context is missing.");
  }
  return context;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
    },
  },
});

function toApiMessage(error: unknown): ApiMessage | null {
  if (isApiError(error)) {
    return { status: error.status, message: error.message };
  }
  if (error instanceof Error) {
    return { status: 0, message: error.message };
  }
  return null;
}

function ApiStateMessage({ isLoading, message }: { isLoading: boolean; message: ApiMessage | null }) {
  if (isLoading) {
    return <p className="status status-neutral">Loading...</p>;
  }
  if (!message) {
    return null;
  }
  return <p className="status status-error">{message.message}</p>;
}

function AppShell() {
  const [apiToken, setApiToken] = useState(() => {
    try {
      return localStorage.getItem("cpw-pilot-api-token") || "";
    } catch {
      return "";
    }
  });

  const apiClient = useMemo(() => new CampaignApiClient({ bearerToken: apiToken }), [apiToken]);

  return (
    <ApiClientContext.Provider value={{ apiClient, apiToken, setApiToken }}>
      <div className="session-pilot">
        <header className="topbar">
          <div className="brand-block">
            <Link to="/" className="brand-link">
              Session Companion
            </Link>
          </div>
          <label className="token-row" htmlFor="pilot-api-token">
            <span>API token</span>
            <input
              id="pilot-api-token"
              type="password"
              value={apiToken}
              placeholder="Optional: bearer token for API-only access"
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const nextToken = event.currentTarget.value;
                setApiToken(nextToken);
                try {
                  if (nextToken.trim()) {
                    localStorage.setItem("cpw-pilot-api-token", nextToken.trim());
                  } else {
                    localStorage.removeItem("cpw-pilot-api-token");
                  }
                } catch {
                  // localStorage may be unavailable in some private sessions.
                }
              }}
            />
          </label>
        </header>
        <main className="main-shell">
          <Outlet />
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}

function CampaignListPage() {
  const { apiClient } = useApiClient();

  const appQuery = useQuery({
    queryKey: ["app"],
    queryFn: () => apiClient.getAppState(),
    retry: false,
  });
  const campaignQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiClient.getCampaigns(),
    retry: false,
  });

  const appError = toApiMessage(appQuery.error);
  const campaignError = toApiMessage(campaignQuery.error);
  const campaigns: CampaignEntry[] = campaignQuery.data?.campaigns ?? [];

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Available Campaigns</h2>
      </div>
      <ApiStateMessage
        isLoading={appQuery.isLoading || campaignQuery.isLoading}
        message={appError ?? campaignError}
      />
      {appQuery.data?.app ? (
        <p className="subtitle">
          Runtime: {appQuery.data.app.runtime}
          {appQuery.data.app.version ? ` - v${appQuery.data.app.version}` : ""}
        </p>
      ) : null}
      {!appQuery.isLoading && !campaignQuery.isLoading && campaigns.length === 0 && !campaignError ? (
        <p className="status status-neutral">No campaigns are visible to this account.</p>
      ) : null}
      <div className="campaign-grid">
        {campaigns.map((entry) => (
          <article className="card" key={entry.campaign.slug}>
            <h3>{entry.campaign.title}</h3>
            <p className="subtitle">{entry.campaign.slug}</p>
            <p>{entry.campaign.summary}</p>
            <p>
              <strong>System:</strong> {entry.campaign.system}
            </p>
            <p>
              <strong>Role:</strong> {entry.role}
            </p>
            <Link
              to="/campaigns/$campaignSlug/session"
              params={{ campaignSlug: entry.campaign.slug }}
              className="button"
            >
              Open Session
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}

function SessionPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/session",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";

  const { apiClient } = useApiClient();

  const { data, isLoading, error, refetch } = useQuery<SessionPayload, Error>({
    queryKey: ["session", resolvedCampaignSlug],
    queryFn: () => apiClient.getSession(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    refetchInterval: (query) => {
      const current = query.state.data;
      return current?.active_session?.is_active ? 4000 : 12000;
    },
    retry: false,
  });

  const [draftMessage, setDraftMessage] = useState("");
  const [messageError, setMessageError] = useState<string | null>(null);
  const postMessage = useMutation({
    mutationFn: (body: string) => apiClient.postSessionMessage(resolvedCampaignSlug, body),
    onSuccess: async () => {
      await refetch();
      setDraftMessage("");
      setMessageError(null);
    },
    onError: (mutationError) => setMessageError(apiErrorMessage(mutationError)),
  });

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = draftMessage.trim();
    if (!body) {
      setMessageError("Type a message before sending.");
      return;
    }
    if (!data?.permissions.can_post_messages) {
      setMessageError("You do not have permission to post messages to this session.");
      return;
    }
    setMessageError(null);
    postMessage.mutate(body);
  };
  const revealedArticles =
    data?.revealed_articles ??
    Array.from(
      new Map(
        (data?.messages ?? [])
          .map((message) => message.article)
          .filter((article): article is NonNullable<SessionMessage["article"]> => article !== null)
          .map((article) => [article.id, article]),
      ).values(),
    );

  return (
    <section className="panel">
      <div className="panel-header">
        <Link to="/" className="button button-secondary">
          Back to list
        </Link>
        <h2>Session: {data?.campaign.title ?? resolvedCampaignSlug}</h2>
      </div>

      <ApiStateMessage isLoading={isLoading} message={toApiMessage(error)} />

      {data ? (
        <>
          <section className="status-row">
            <article className="stat-card">
              <h3>Live session</h3>
              <p>{data.active_session?.status ?? "inactive"}</p>
            </article>
            <article className="stat-card">
              <h3>Session ID</h3>
              <p>{data.active_session?.id ?? "No active session"}</p>
            </article>
            <article className="stat-card">
              <h3>Messages</h3>
              <p>{data.messages.length}</p>
            </article>
          </section>

          <div className="split-grid">
            <article className="panel panel-nested">
              <h3>Revealed Articles</h3>
              {revealedArticles.length ? (
                <ul>
                  {revealedArticles.map((article) => (
                    <li key={article.id}>
                      <strong>{article.title}</strong>
                      <p>{article.body_markdown || "No article body."}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="status status-neutral">No revealed articles yet.</p>
              )}
            </article>

            {data.permissions.can_manage_session ? (
              <article className="panel panel-nested">
                <h3>Staged Articles</h3>
                {data.staged_articles?.length ? (
                  <ul>
                    {data.staged_articles.map((article) => (
                      <li key={article.id}>
                        <strong>{article.title}</strong>
                        <p>{article.body_markdown || "No article body."}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="status status-neutral">No staged articles.</p>
                )}
              </article>
            ) : null}
          </div>

          <article className="panel panel-nested chat-panel">
            <h3>Session chat</h3>
            <div className="chat-list">
              {data.messages.length ? (
                data.messages.map((message: SessionMessage) => (
                  <article key={message.id} className="chat-item">
                    <p className="chat-meta">{message.author_display_name}</p>
                    <p>{message.body_text}</p>
                  </article>
                ))
              ) : (
                <p className="status status-neutral">No messages yet.</p>
              )}
            </div>

            {data.permissions.can_post_messages ? (
              <form onSubmit={sendMessage} className="chat-composer">
                <label htmlFor="message-body" className="chat-label">
                  Post Session Message
                </label>
                <textarea
                  id="message-body"
                  value={draftMessage}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                    setDraftMessage(event.currentTarget.value);
                  }}
                  placeholder="Type chat text here."
                />
                <div className="chat-actions">
                  <button type="submit" disabled={postMessage.isPending}>
                    {postMessage.isPending ? "Sending..." : "Send"}
                  </button>
                  <span>{data.permissions.can_manage_session ? "DM mode" : "Player mode"}</span>
                </div>
                {messageError ? <p className="status status-error">{messageError}</p> : null}
              </form>
            ) : (
              <p className="status status-neutral">
                You do not have permission to post messages for this campaign session.
              </p>
            )}
          </article>
        </>
      ) : null}
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

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const routeTree = rootRoute.addChildren([campaignsRoute, campaignSessionRoute]);
const router = createRouter({ routeTree, basepath: "/app-next" });

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
