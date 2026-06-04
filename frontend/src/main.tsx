import React, { useState, useEffect, useMemo, useContext, createContext } from "react";
import { createRoot } from "react-dom/client";
import {
  Link,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  useParams,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";
import "./styles.css";
import {
  CampaignApiClient,
  apiErrorMessage,
  isApiError,
} from "./api/client";
import type {
  CampaignEntry,
  CharacterDetailResponse,
  CharacterRecord,
  CharacterSummary,
  CharacterNotesPatchPayload,
  CharacterVitalsPatchPayload,
  SessionArticle,
  SessionArticleCreatePayload,
  SessionArticleCreatePayloadManual,
  SessionArticleCreatePayloadUpload,
  SessionArticleCreatePayloadWiki,
  SessionArticleSourceResult,
  SessionLogSummary,
  SessionMessage,
  SessionPayload,
  SessionWikiLookupPreviewResponse,
  SessionWikiLookupSearchResult,
} from "./api/types";

interface ApiMessageEnvelope {
  status: number;
  message: string;
}

interface EmbeddedImageInput {
  filename: string;
  data_base64: string;
  media_type: string;
}

interface CharacterVitalsDraft {
  expectedRevision: number;
  currentHp: string;
  tempHp: string;
}

interface CharacterNotesDraft {
  expectedRevision: number;
  notes: string;
}

type PaneName = "session" | "character" | "dm";
type ArticleMode = "manual" | "upload" | "wiki";

interface ApiClientContextValue {
  apiClient: CampaignApiClient;
  apiToken: string;
  setApiToken: (token: string) => void;
  authRequired: boolean;
  setAuthRequired: (required: boolean) => void;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2500,
      refetchOnWindowFocus: false,
    },
  },
});

const ApiClientContext = createContext<ApiClientContextValue | null>(null);

function useApiClient(): ApiClientContextValue {
  const context = useContext(ApiClientContext);
  if (context === null) {
    throw new Error("CampaignApiClient context is missing.");
  }
  return context;
}

function isAuthError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}

function getApiErrorMessage(error: unknown): ApiMessageEnvelope | null {
  if (isApiError(error)) {
    return { status: error.status, message: error.message };
  }
  if (error instanceof Error) {
    return { status: 0, message: error.message };
  }
  return null;
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "N/A";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function resolveArticleImage(slug: string, article: SessionArticle): string {
  if (article.image?.url) {
    return article.image.url;
  }
  return `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${article.id}/image`;
}

function renderArticleBody(article: SessionArticle): JSX.Element {
  if (article.body_format === "html") {
    return <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: article.body_markdown }} />;
  }
  return <pre className="article-body markdown-body">{article.body_markdown}</pre>;
}

function ApiErrorNotice({
  isLoading,
  message,
  onAuth,
}: {
  isLoading: boolean;
  message: ApiMessageEnvelope | null;
  onAuth: () => void;
}) {
  if (isLoading) {
    return <p className="status status-neutral">Loading ...</p>;
  }
  if (!message) {
    return null;
  }
  if (message.status === 401) {
    return (
      <p className="status status-error">
        {message.message}
        <button type="button" className="link-like-button" onClick={onAuth}>
          Open sign-in
        </button>
      </p>
    );
  }
  return <p className="status status-error">{message.message}</p>;
}

function AuthNotice() {
  const { authRequired, setAuthRequired } = useApiClient();
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  if (!authRequired) {
    return null;
  }

  return (
    <section className="panel auth-notice">
      <h3>Authentication required</h3>
      <p className="status status-error">
        Your cookie or API token did not authenticate this request. Sign in to restore session.
      </p>
      <a className="button button-secondary" href={signInHref}>
        Sign in
      </a>
      <button type="button" className="button" onClick={() => setAuthRequired(false)}>
        Continue without token
      </button>
    </section>
  );
}

function AppShell() {
  const [apiToken, setApiToken] = useState(() => {
    try {
      return localStorage.getItem("cpw-pilot-api-token") || "";
    } catch {
      return "";
    }
  });
  const [authRequired, setAuthRequired] = useState(false);

  const apiClient = useMemo(() => {
    return new CampaignApiClient({
      bearerToken: apiToken,
    });
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

  return (
    <ApiClientContext.Provider value={{ apiClient, apiToken, setApiToken: setStoredToken, authRequired, setAuthRequired }}>
      <div className="session-shell">
        <header className="topbar">
          <div className="brand-block">
            <Link to="/" className="brand-link">
              Session Companion
            </Link>
            <p className="subtitle">app-next / /app-next/campaigns/.../session</p>
          </div>
          <label className="token-row" htmlFor="pilot-api-token">
            <span>API token (optional)</span>
            <input
              id="pilot-api-token"
              type="password"
              value={apiToken}
              placeholder="Bearer token for API-only testing"
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setStoredToken(event.currentTarget.value);
              }}
            />
          </label>
          <a
            className="button button-secondary sign-in-link"
            href={`/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`}
          >
            Sign in
          </a>
        </header>
        <AuthNotice />
        <main className="main-shell">
          <Outlet />
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}

function CampaignListPage() {
  const { apiClient, setAuthRequired } = useApiClient();

  const appQuery = useQuery({
    queryKey: ["app"],
    queryFn: () => apiClient.getAppState(),
    retry: false,
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiClient.getCampaigns(),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(appQuery.error) || isAuthError(campaignsQuery.error)) {
      setAuthRequired(true);
    }
  }, [appQuery.error, campaignsQuery.error, setAuthRequired]);

  const appError = getApiErrorMessage(appQuery.error);
  const campaignError = getApiErrorMessage(campaignsQuery.error);
  const campaigns: CampaignEntry[] = campaignsQuery.data?.campaigns ?? [];

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Available Campaigns</h2>
      </div>
      <ApiErrorNotice
        isLoading={appQuery.isLoading || campaignsQuery.isLoading}
        message={appError ?? campaignError}
        onAuth={() => setAuthRequired(true)}
      />
      {appQuery.data?.app ? (
        <p className="subtitle">
          Runtime: {appQuery.data.app.runtime}
          {appQuery.data.app.version ? ` - ${appQuery.data.app.version}` : ""}
        </p>
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
            <Link to="/campaigns/$campaignSlug/session" params={{ campaignSlug: entry.campaign.slug }} className="button">
              Open Session
            </Link>
          </article>
        ))}
        {!appQuery.isLoading && !campaignsQuery.isLoading && !campaigns.length && !campaignError ? (
          <p className="status status-neutral">No campaigns are visible to this account.</p>
        ) : null}
      </div>
    </section>
  );
}
function SessionArticlesPanel({
  campaignSlug,
  articles,
  title,
  emptyText,
}: {
  campaignSlug: string;
  articles: SessionArticle[];
  title: string;
  emptyText: string;
}) {
  return (
    <article className="panel panel-nested">
      <div className="panel-header">
        <h3>{title}</h3>
        <span className="pill">{articles.length} article(s)</span>
      </div>
      {articles.length ? (
        <div className="article-stack">
          {articles.map((article) => (
            <details className="article-card" key={article.id}>
              <summary>
                <strong>{article.title}</strong>
                <span className="article-kind">{article.source_kind || "unclassified"}</span>
              </summary>
              <div className="article-meta">
                {article.image ? (
                  <img
                    className="article-image"
                    src={resolveArticleImage(campaignSlug, article)}
                    alt={article.image.alt_text || "Session article image"}
                  />
                ) : null}
                {article.created_at ? <time>{formatTimestamp(article.created_at)}</time> : null}
              </div>
              {renderArticleBody(article)}
            </details>
          ))}
        </div>
      ) : (
        <p className="status status-neutral">{emptyText}</p>
      )}
    </article>
  );
}

function SessionPaneChat({
  payload,
  messageDraft,
  setMessageDraft,
  sendError,
  onSend,
  isSending,
}: {
  payload: SessionPayload | undefined;
  messageDraft: string;
  setMessageDraft: (value: string) => void;
  sendError: string | null;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  isSending: boolean;
}) {
  const messages: SessionMessage[] = payload?.messages ?? [];

  return (
    <article className="panel panel-nested">
      <div className="panel-header">
        <h3>Session chat</h3>
        <span className="pill">{payload?.active_session ? `Session #${payload.active_session.id}` : "No active session"}</span>
      </div>
      <div className="chat-list">
        {messages.length ? (
          messages.map((message) => (
            <article key={message.id} className="chat-item">
              <p className="chat-meta">
                {message.author_display_name} - {formatTimestamp(message.created_at)}
              </p>
              <p>{message.body_text}</p>
            </article>
          ))
        ) : (
          <p className="status status-neutral">No messages yet.</p>
        )}
      </div>
      {payload?.permissions.can_post_messages ? (
        <form onSubmit={onSend} className="chat-composer">
          <label htmlFor="session-message-body" className="chat-label">
            Post Session Message
          </label>
          <textarea
            id="session-message-body"
            rows={5}
            value={messageDraft}
            placeholder="Type chat text"
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setMessageDraft(event.currentTarget.value);
            }}
          />
          <div className="chat-actions">
            <button type="submit" disabled={isSending || payload?.active_session === null}>
              {isSending ? "Sending..." : "Send"}
            </button>
            <span>{payload?.permissions.can_manage_session ? "DM view" : "Player view"}</span>
          </div>
          {sendError ? <p className="status status-error">{sendError}</p> : null}
        </form>
      ) : (
        <p className="status status-neutral">You do not have permission to post messages.</p>
      )}
    </article>
  );
}

function SessionPaneWikiLookup({
  canShow,
  query,
  setQuery,
  queryStatus,
  results,
  onSearch,
  previewRef,
  onSelectPreview,
  previewLoading,
  previewHtml,
  previewError,
  clearStatus,
}: {
  canShow: boolean;
  query: string;
  setQuery: (value: string) => void;
  queryStatus: string | null;
  results: SessionWikiLookupSearchResult[];
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
  previewRef: string | null;
  onSelectPreview: (pageRef: string) => void;
  previewLoading: boolean;
  previewHtml: string;
  previewError: string | null;
  clearStatus: () => void;
}) {
  if (!canShow) {
    return <p className="status status-neutral">This campaign does not expose wiki lookup.</p>;
  }

  return (
    <article className="panel panel-nested">
      <h3>Player wiki lookup</h3>
      <form onSubmit={onSearch} className="wiki-search">
        <label htmlFor="wiki-search-query" className="chat-label">
          Search published pages / systems
        </label>
        <div className="search-row">
          <input
            id="wiki-search-query"
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setQuery(event.currentTarget.value);
              clearStatus();
            }}
            placeholder="harbor, rules, artifact"
          />
          <button type="submit">Search</button>
        </div>
      </form>
      {queryStatus ? <p className="status status-neutral">{queryStatus}</p> : null}
      {results.length ? (
        <div className="wiki-result-stack">
          {results.map((result) => {
            const pageRef = result.page_ref || result.source_ref || "";
            return (
              <button
                className="wiki-result-row"
                type="button"
                key={pageRef}
                onClick={() => onSelectPreview(pageRef)}
                disabled={!pageRef}
              >
                <strong>{result.title}</strong>
                <p>{result.subtitle}</p>
              </button>
            );
          })}
        </div>
      ) : null}
      {previewRef ? (
        <div className="wiki-preview">
          <div className="preview-title">Preview: {previewRef}</div>
          {previewLoading ? <p className="status status-neutral">Loading preview ...</p> : null}
          {previewError ? <p className="status status-error">{previewError}</p> : null}
          {previewHtml ? <div className="wiki-preview-html" dangerouslySetInnerHTML={{ __html: previewHtml }} /> : null}
        </div>
      ) : null}
    </article>
  );
}

function readBinaryAsBase64(file: File, callback: (payload: EmbeddedImageInput | null) => void): void {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const data = reader.result;
    if (typeof data !== "string") {
      callback(null);
      return;
    }
    callback({
      filename: file.name,
      data_base64: data.split(",", 2)[1] || "",
      media_type: file.type || "application/octet-stream",
    });
  });
  reader.addEventListener("error", () => callback(null));
  reader.readAsDataURL(file);
}

function DmArticleCreator({
  mode,
  setMode,
  sourceQuery,
  setSourceQuery,
  sourceStatus,
  setSourceStatus,
  sourceResults,
  selectedSourceRef,
  setSelectedSourceRef,
  manualDraft,
  setManualDraft,
  uploadDraft,
  setUploadDraft,
  onSearchSources,
  onCreate,
  isCreating,
}: {
  mode: ArticleMode;
  setMode: (mode: ArticleMode) => void;
  sourceQuery: string;
  setSourceQuery: (value: string) => void;
  sourceStatus: string | null;
  setSourceStatus: (value: string | null) => void;
  sourceResults: SessionArticleSourceResult[];
  selectedSourceRef: string;
  setSelectedSourceRef: (value: string) => void;
  manualDraft: { title: string; body: string };
  setManualDraft: (state: { title: string; body: string }) => void;
  uploadDraft: { filename: string; markdown: string; image: EmbeddedImageInput | null };
  setUploadDraft: (state: { filename: string; markdown: string; image: EmbeddedImageInput | null }) => void;
  onSearchSources: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCreate: (payload: SessionArticleCreatePayload) => void;
  isCreating: boolean;
}) {
  const instructions =
    mode === "manual"
      ? "Use title and markdown body and create an unrevealed article."
      : mode === "upload"
        ? "Upload mode needs a filename and markdown body."
        : "Search and select a source, then pull into staged articles.";

  return (
    <article className="panel panel-nested">
      <h3>Stage an article</h3>
      <div className="segmented">
        <button
          type="button"
          className={mode === "manual" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("manual")}
        >
          Manual
        </button>
        <button
          type="button"
          className={mode === "upload" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("upload")}
        >
          Upload
        </button>
        <button
          type="button"
          className={mode === "wiki" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("wiki")}
        >
          Wiki / Systems
        </button>
      </div>
      <p className="status status-neutral">{instructions}</p>

      {mode === "manual" ? (
        <section className="session-form">
          <label htmlFor="dm-manual-title" className="chat-label">Title</label>
          <input
            id="dm-manual-title"
            value={manualDraft.title}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setManualDraft({ ...manualDraft, title: event.currentTarget.value });
            }}
          />
          <label htmlFor="dm-manual-body" className="chat-label">Markdown body</label>
          <textarea
            id="dm-manual-body"
            rows={8}
            value={manualDraft.body}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setManualDraft({ ...manualDraft, body: event.currentTarget.value });
            }}
          />
          <button
            type="button"
            className="button"
            disabled={isCreating || !manualDraft.title.trim() || !manualDraft.body.trim()}
            onClick={() =>
              onCreate({
                mode: "manual",
                title: manualDraft.title.trim(),
                body_markdown: manualDraft.body,
              } satisfies SessionArticleCreatePayloadManual)
            }
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </section>
      ) : null}

      {mode === "upload" ? (
        <section className="session-form">
          <label htmlFor="dm-upload-filename" className="chat-label">Source filename</label>
          <input
            id="dm-upload-filename"
            value={uploadDraft.filename}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setUploadDraft({ ...uploadDraft, filename: event.currentTarget.value });
            }}
            placeholder="notes.md"
          />
          <label htmlFor="dm-upload-markdown" className="chat-label">Markdown text</label>
          <textarea
            id="dm-upload-markdown"
            rows={8}
            value={uploadDraft.markdown}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setUploadDraft({ ...uploadDraft, markdown: event.currentTarget.value });
            }}
          />
          <label className="chat-label">Referenced image (optional)</label>
          <input
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.gif"
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const file = event.currentTarget.files?.item(0);
              if (!file) {
                setUploadDraft({ ...uploadDraft, image: null });
                return;
              }
              readBinaryAsBase64(file, (payload) => {
                setUploadDraft({ ...uploadDraft, image: payload });
              });
            }}
          />
          <button
            type="button"
            disabled={isCreating || !uploadDraft.filename.trim() || !uploadDraft.markdown.trim()}
            onClick={() =>
              onCreate({
                mode: "upload",
                filename: uploadDraft.filename.trim(),
                markdown_text: uploadDraft.markdown,
                referenced_image: uploadDraft.image ?? undefined,
              } satisfies SessionArticleCreatePayloadUpload)
            }
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </section>
      ) : null}

      {mode === "wiki" ? (
        <section className="session-form">
          <form onSubmit={onSearchSources} className="wiki-search">
            <label htmlFor="dm-wiki-search" className="chat-label">Search wiki / systems</label>
            <div className="search-row">
              <input
                id="dm-wiki-search"
                value={sourceQuery}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setSourceQuery(event.currentTarget.value);
                  setSourceStatus(null);
                  setSelectedSourceRef("");
                }}
              />
              <button type="submit">Search</button>
            </div>
          </form>
          {sourceStatus ? <p className="status status-neutral">{sourceStatus}</p> : null}
          {sourceResults.length ? (
            <div className="wiki-result-stack">
              {sourceResults.map((result) => (
                <button
                  key={result.source_ref}
                  type="button"
                  className="wiki-result-row"
                  onClick={() => setSelectedSourceRef(result.source_ref)}
                >
                  <strong>{result.title}</strong>
                  <p>{result.subtitle}</p>
                </button>
              ))}
            </div>
          ) : null}
          <div className="wiki-selection">
            <p className="status status-neutral">{selectedSourceRef ? `Source selected: ${selectedSourceRef}` : "No source selected"}</p>
            <button
              type="button"
              disabled={isCreating || !selectedSourceRef}
              onClick={() =>
                onCreate({
                  mode: "wiki",
                  source_ref: selectedSourceRef,
                } satisfies SessionArticleCreatePayloadWiki)
              }
            >
              {isCreating ? "Creating..." : "Pull source"}
            </button>
          </div>
        </section>
      ) : null}
    </article>
  );
}
function SessionPane({
  campaignSlug,
  payload,
  refetch,
  setAuthRequired,
}: {
  campaignSlug: string;
  payload: SessionPayload | undefined;
  refetch: () => void;
  setAuthRequired: (required: boolean) => void;
}) {
  const { apiClient } = useApiClient();
  const [messageDraft, setMessageDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);

  const [wikiQuery, setWikiQuery] = useState("");
  const [wikiStatus, setWikiStatus] = useState<string | null>(null);
  const [wikiResults, setWikiResults] = useState<SessionWikiLookupSearchResult[]>([]);
  const [wikiPreviewRef, setWikiPreviewRef] = useState<string | null>(null);
  const [wikiPreviewLoading, setWikiPreviewLoading] = useState(false);
  const [wikiPreviewHtml, setWikiPreviewHtml] = useState("");
  const [wikiPreviewError, setWikiPreviewError] = useState<string | null>(null);

  const postMessage = useMutation({
    mutationFn: (body: string) => apiClient.postSessionMessage(campaignSlug, body),
    onSuccess: () => {
      setMessageDraft("");
      setSendError(null);
      refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSendError(apiErrorMessage(error));
    },
  });

  const doSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = wikiQuery.trim();
    if (!query) {
      setWikiStatus("Enter a search query first.");
      return;
    }
    setWikiStatus("Searching ...");
    try {
      const result = await apiClient.searchPlayerSessionWiki(campaignSlug, query);
      setWikiResults(result.results);
      setWikiStatus(result.message || "Search complete.");
      if (!result.results.length) {
        setWikiPreviewRef(null);
        setWikiPreviewHtml("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setWikiResults([]);
      setWikiStatus(null);
      setWikiPreviewError(apiErrorMessage(error));
    }
  };

  const doPreview = async (pageRef: string) => {
    setWikiPreviewRef(pageRef);
    setWikiPreviewLoading(true);
    setWikiPreviewError(null);
    try {
      const response: SessionWikiLookupPreviewResponse = await apiClient.previewPlayerSessionWiki(campaignSlug, pageRef);
      setWikiPreviewHtml(response.preview_html || "");
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setWikiPreviewHtml("");
      setWikiPreviewError(apiErrorMessage(error));
    } finally {
      setWikiPreviewLoading(false);
    }
  };

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = messageDraft.trim();
    if (!body) {
      setSendError("Type a message first.");
      return;
    }
    if (!payload?.permissions.can_post_messages) {
      setSendError("You do not have permission to post messages.");
      return;
    }
    if (!payload?.active_session) {
      setSendError("No active session.");
      return;
    }
    postMessage.mutate(body);
  };

  const canShowWikiLookup = payload?.permissions.can_access_wiki_lookup ?? true;

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>Session: {payload?.campaign.title ?? campaignSlug}</h2>
          <span className="pill">Player</span>
        </div>
        <div className="status-row">
          <article className="stat-card">
            <h3>Session</h3>
            <p>{payload?.active_session ? payload.active_session.status : "inactive"}</p>
          </article>
          <article className="stat-card">
            <h3>Messages</h3>
            <p>{payload?.messages.length ?? 0}</p>
          </article>
          <article className="stat-card">
            <h3>Session ID</h3>
            <p>{payload?.active_session?.id ?? "none"}</p>
          </article>
        </div>
      </section>

      <div className="split-grid">
        <SessionArticlesPanel
          campaignSlug={campaignSlug}
          articles={payload?.revealed_articles ?? []}
          title="Revealed articles"
          emptyText="No revealed articles yet."
        />
        <SessionPaneWikiLookup
          canShow={canShowWikiLookup}
          query={wikiQuery}
          setQuery={setWikiQuery}
          queryStatus={wikiStatus}
          results={wikiResults}
          onSearch={doSearch}
          previewRef={wikiPreviewRef}
          onSelectPreview={doPreview}
          previewLoading={wikiPreviewLoading}
          previewHtml={wikiPreviewHtml}
          previewError={wikiPreviewError}
          clearStatus={() => {
            setWikiPreviewError(null);
            setWikiStatus(null);
          }}
        />
      </div>
      <SessionPaneChat
        payload={payload}
        messageDraft={messageDraft}
        setMessageDraft={setMessageDraft}
        sendError={sendError}
        onSend={sendMessage}
        isSending={postMessage.isPending}
      />
    </div>
  );
}

function CharacterPane({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [vitalsDraft, setVitalsDraft] = useState<CharacterVitalsDraft>({
    expectedRevision: 0,
    currentHp: "",
    tempHp: "",
  });
  const [notesDraft, setNotesDraft] = useState<CharacterNotesDraft>({ expectedRevision: 0, notes: "" });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["characters", campaignSlug],
    queryFn: () => apiClient.getCharacters(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  const characterList: CharacterSummary[] = listQuery.data?.characters ?? [];

  useEffect(() => {
    if (!selectedSlug && characterList.length > 0) {
      setSelectedSlug(characterList[0].slug);
    }
  }, [characterList, selectedSlug]);

  const detailQuery = useQuery({
    queryKey: ["character-detail", campaignSlug, selectedSlug],
    queryFn: () => {
      if (!selectedSlug) {
        throw new Error("No character selected");
      }
      return apiClient.getCharacter(campaignSlug, selectedSlug);
    },
    enabled: Boolean(campaignSlug) && Boolean(selectedSlug),
    retry: false,
  });

  useEffect(() => {
    if (listQuery.error && isAuthError(listQuery.error)) {
      setAuthRequired(true);
    }
  }, [listQuery.error, setAuthRequired]);

  useEffect(() => {
    if (detailQuery.error && isAuthError(detailQuery.error)) {
      setAuthRequired(true);
    }
  }, [detailQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!detailQuery.data) {
      return;
    }
    const state = detailQuery.data.character.state_record.state as Record<string, unknown>;
    const vitals = (state?.vitals as Record<string, unknown>) || {};
    const notes = (state?.notes as Record<string, unknown>) || {};
    setVitalsDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      currentHp: String((vitals.current_hp as number | null) ?? ""),
      tempHp: String((vitals.temp_hp as number | null) ?? ""),
    });
    setNotesDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      notes: String((notes.player_notes_markdown as string | undefined) ?? ""),
    });
  }, [detailQuery.data?.character.state_record.revision]);

  const detail = detailQuery.data as CharacterDetailResponse | undefined;
  const selected = characterList.find((item) => item.slug === selectedSlug);
  const permissions = detail?.character.permissions;

  const patchVitals = useMutation({
    mutationFn: (payload: CharacterVitalsPatchPayload) =>
      apiClient.patchCharacterVitals(campaignSlug, selectedSlug || "", payload),
    onSuccess: () => {
      void detailQuery.refetch();
      void listQuery.refetch();
      setStatusMessage("Vitals saved.");
      setErrorMessage(null);
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setStatusMessage(null);
      setErrorMessage(apiErrorMessage(error));
    },
  });

  const patchNotes = useMutation({
    mutationFn: (payload: CharacterNotesPatchPayload) =>
      apiClient.patchCharacterNotes(campaignSlug, selectedSlug || "", payload),
    onSuccess: () => {
      void detailQuery.refetch();
      setStatusMessage("Notes saved.");
      setErrorMessage(null);
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setStatusMessage(null);
      setErrorMessage(apiErrorMessage(error));
    },
  });

  const submitVitals = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const currentHp = Number(vitalsDraft.currentHp);
    const tempHp = Number(vitalsDraft.tempHp);

    if (!selected || !permissions?.can_edit_session) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (!Number.isFinite(currentHp) || !Number.isFinite(tempHp)) {
      setErrorMessage("Enter valid HP numbers.");
      return;
    }

    setStatusMessage("Saving...");
    patchVitals.mutate({
      expected_revision: vitalsDraft.expectedRevision,
      current_hp: currentHp,
      temp_hp: tempHp,
    });
  };

  const submitNotes = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !permissions?.can_edit_session) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchNotes.mutate({
      expected_revision: notesDraft.expectedRevision,
      player_notes_markdown: notesDraft.notes,
    });
  };

  const state = detail ? (detail.character.state_record.state as Record<string, unknown>) : {};
  const vitals = (state?.vitals as Record<string, unknown>) || {};

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>Session Character</h2>
          <a href={`/campaigns/${campaignSlug}/characters`} className="button button-secondary">
            Character route
          </a>
        </div>

        <label className="chat-label" htmlFor="character-selector">
          Character
        </label>
        <select
          id="character-selector"
          value={selectedSlug || ""}
          onChange={(event) => setSelectedSlug(event.currentTarget.value || null)}
        >
          {characterList.map((item) => (
            <option key={item.slug} value={item.slug}>
              {item.name} ({item.slug})
            </option>
          ))}
        </select>

        {selected ? (
          <article className="character-summary">
            <h3>
              {selected.name} ({selected.slug})
            </h3>
            <p>
              HP: {(vitals.current_hp as number | null) ?? selected.current_hp} / {(vitals.max_hp as number | null) ?? selected.max_hp}
            </p>
            <p>Temp HP: {(vitals.temp_hp as number | null) ?? selected.temp_hp}</p>
            <p>Class: {selected.class_level_text || "Unknown"}</p>
            <p>Status: {selected.status}</p>
            <p>Revision: {selected.revision}</p>
          </article>
        ) : null}

        {selected ? (
          <>
            <section className="session-character-form">
              <h3>Vitals</h3>
              <form onSubmit={submitVitals} className="inline-two-col">
                <label htmlFor="character-current-hp" className="chat-label">
                  Current HP
                </label>
                <input
                  id="character-current-hp"
                  type="number"
                  value={vitalsDraft.currentHp}
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })
                  }
                />
                <label htmlFor="character-temp-hp" className="chat-label">
                  Temp HP
                </label>
                <input
                  id="character-temp-hp"
                  type="number"
                  value={vitalsDraft.tempHp}
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })
                  }
                />
                <div />
                <button type="submit" disabled={patchVitals.isPending || !permissions?.can_edit_session}>
                  {patchVitals.isPending ? "Saving..." : "Save vitals"}
                </button>
              </form>
            </section>
            <section className="session-character-form">
              <h3>Player notes</h3>
              <form onSubmit={submitNotes}>
                <label htmlFor="character-player-notes" className="chat-label">
                  Player notes
                </label>
                <textarea
                  id="character-player-notes"
                  rows={8}
                  value={notesDraft.notes}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                    setNotesDraft({ ...notesDraft, notes: event.currentTarget.value })
                  }
                />
                <button type="submit" disabled={patchNotes.isPending || !permissions?.can_edit_session}>
                  {patchNotes.isPending ? "Saving..." : "Save notes"}
                </button>
              </form>
            </section>
          </>
        ) : null}

        {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
        {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
      </section>
    </div>
  );
}

interface StagedArticleDraftState {
  title: string;
  body: string;
  imageAltText: string;
  imageCaption: string;
}

function DmPane({
  campaignSlug,
  payload,
  refetch,
  setAuthRequired,
}: {
  campaignSlug: string;
  payload: SessionPayload | undefined;
  refetch: () => void;
  setAuthRequired: (required: boolean) => void;
}) {
  const { apiClient } = useApiClient();
  const stagedArticles: SessionArticle[] = payload?.staged_articles ?? [];
  const revealedArticles: SessionArticle[] = payload?.revealed_articles ?? [];
  const sessionLogs: SessionLogSummary[] = payload?.session_logs ?? [];
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState({ title: "", body: "" });
  const [uploadDraft, setUploadDraft] = useState({ filename: "", markdown: "", image: null as EmbeddedImageInput | null });
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceResults, setSourceResults] = useState<SessionArticleSourceResult[]>([]);
  const [sourceStatus, setSourceStatus] = useState<string | null>(null);
  const [selectedSourceRef, setSelectedSourceRef] = useState("");
  const [stagedDrafts, setStagedDrafts] = useState<Record<number, StagedArticleDraftState>>({});
  const [uiMessage, setUiMessage] = useState<string | null>(null);
  const [paneError, setPaneError] = useState<string | null>(null);
  const [selectedLogSessionId, setSelectedLogSessionId] = useState<number | null>(null);

  useEffect(() => {
    setStagedDrafts((current) => {
      const next: Record<number, StagedArticleDraftState> = {};
      for (const article of stagedArticles) {
        const existing = current[article.id];
        next[article.id] = existing ?? {
          title: article.title,
          body: article.body_markdown,
          imageAltText: article.image?.alt_text || "",
          imageCaption: article.image?.caption || "",
        };
      }
      return next;
    });
  }, [stagedArticles]);

  useEffect(() => {
    if (!sessionLogs.length) {
      setSelectedLogSessionId(null);
      return;
    }
    if (selectedLogSessionId !== null && !sessionLogs.some((entry) => entry.session.id === selectedLogSessionId)) {
      setSelectedLogSessionId(sessionLogs[0]?.session.id ?? null);
    }
  }, [sessionLogs, selectedLogSessionId]);

  const startSessionMutation = useMutation({
    mutationFn: () => apiClient.startSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session started.");
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const closeSessionMutation = useMutation({
    mutationFn: () => apiClient.closeSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session closed.");
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(campaignSlug, payload),
    onSuccess: () => {
      setUiMessage("Article created.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateArticleMutation = useMutation({
    mutationFn: (args: { id: number; payload: { title: string; body_markdown: string; image_alt_text?: string; image_caption?: string } }) =>
      apiClient.updateSessionArticle(campaignSlug, args.id, {
        title: args.payload.title,
        body_markdown: args.payload.body_markdown,
        image_alt_text: args.payload.image_alt_text,
        image_caption: args.payload.image_caption,
      }),
    onSuccess: () => {
      setUiMessage("Article updated.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const revealArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.revealSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article revealed.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article deleted.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const clearRevealedMutation = useMutation({
    mutationFn: () => apiClient.clearRevealedSessionArticles(campaignSlug),
    onSuccess: () => {
      setUiMessage("Revealed articles cleared.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteLogMutation = useMutation({
    mutationFn: (sessionId: number) => apiClient.deleteSessionLog(campaignSlug, sessionId),
    onSuccess: (_data, sessionId) => {
      setUiMessage("Session log deleted.");
      setPaneError(null);
      if (selectedLogSessionId === sessionId) {
        setSelectedLogSessionId(null);
      }
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const logQuery = useQuery({
    queryKey: ["session-log-detail", campaignSlug, selectedLogSessionId],
    queryFn: () => {
      if (selectedLogSessionId === null) {
        throw new Error("No session selected.");
      }
      return apiClient.getSessionLog(campaignSlug, selectedLogSessionId);
    },
    enabled: Boolean(campaignSlug) && selectedLogSessionId !== null,
    retry: false,
  });

  useEffect(() => {
    if (logQuery.error && isAuthError(logQuery.error)) {
      setAuthRequired(true);
    }
  }, [logQuery.error, setAuthRequired]);

  const searchSources = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = sourceQuery.trim();
    if (!query) {
      setSourceStatus("Search with a query.");
      return;
    }
    setSourceStatus("Searching ...");
    try {
      const response = await apiClient.searchSessionArticleSources(campaignSlug, query);
      setSourceResults(response.results);
      setSourceStatus(response.message || "Search complete.");
      if (!response.results.length) {
        setSelectedSourceRef("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSourceResults([]);
      setSourceStatus(null);
      setPaneError(apiErrorMessage(error));
    }
  };

  const createArticle = (createPayload: SessionArticleCreatePayload) => {
    setPaneError(null);
    createArticleMutation.mutate(createPayload);
  };

  const clearArticleStatus = () => {
    setPaneError(null);
    setUiMessage(null);
  };

  const statusText = startSessionMutation.isPending ? "Starting session..." : closeSessionMutation.isPending ? "Closing session..." : null;

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>DM controls</h2>
          <span className="pill">{payload?.active_session ? `Session #${payload.active_session.id}` : "No active session"}</span>
        </div>
        <div className="status-row">
          <article className="stat-card">
            <h3>Session state</h3>
            <p>{payload?.active_session ? payload.active_session.status : "inactive"}</p>
          </article>
          <article className="stat-card">
            <h3>Controls</h3>
            <div className="session-actions-row">
              <button type="button" onClick={() => startSessionMutation.mutate()} disabled={startSessionMutation.isPending}>
                {startSessionMutation.isPending ? "Starting..." : "Begin session"}
              </button>
              <button
                type="button"
                onClick={() => closeSessionMutation.mutate()}
                disabled={closeSessionMutation.isPending || !payload?.active_session}
              >
                {closeSessionMutation.isPending ? "Closing..." : "Close session"}
              </button>
            </div>
          </article>
          <article className="stat-card">
            <h3>Lifecycle</h3>
            <p>{statusText || uiMessage || "Ready."}</p>
          </article>
        </div>
        {startSessionMutation.error ? <p className="status status-error">{apiErrorMessage(startSessionMutation.error)}</p> : null}
        {closeSessionMutation.error ? <p className="status status-error">{apiErrorMessage(closeSessionMutation.error)}</p> : null}
        {paneError ? <p className="status status-error">{paneError}</p> : null}
        {uiMessage ? <p className="status status-neutral">{uiMessage}</p> : null}
      </section>

      <div className="split-grid">
        <DmArticleCreator
          mode={mode}
          setMode={(next) => {
            clearArticleStatus();
            setMode(next);
          }}
          sourceQuery={sourceQuery}
          setSourceQuery={setSourceQuery}
          sourceStatus={sourceStatus}
          setSourceStatus={setSourceStatus}
          sourceResults={sourceResults}
          selectedSourceRef={selectedSourceRef}
          setSelectedSourceRef={(next) => {
            setSelectedSourceRef(next);
            setSourceStatus(`Source selected: ${next}`);
          }}
          manualDraft={manualDraft}
          setManualDraft={(next) => {
            clearArticleStatus();
            setManualDraft(next);
          }}
          uploadDraft={uploadDraft}
          setUploadDraft={(next) => {
            clearArticleStatus();
            setUploadDraft(next);
          }}
          onSearchSources={searchSources}
          onCreate={createArticle}
          isCreating={createArticleMutation.isPending}
        />
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Staged articles</h3>
            <span className="pill">{stagedArticles.length}</span>
          </div>
          <p className="status status-neutral">Unrevealed staged articles are editable and ready for reveal.</p>
          {stagedArticles.length ? (
            <div className="article-stack">
              {stagedArticles.map((article) => {
                const draft = stagedDrafts[article.id] ?? {
                  title: article.title,
                  body: article.body_markdown,
                  imageAltText: article.image?.alt_text || "",
                  imageCaption: article.image?.caption || "",
                };

                return (
                  <details className="article-card" key={article.id}>
                    <summary>
                      <strong>{article.title}</strong>
                    </summary>
                    <label htmlFor={`dm-stage-title-${article.id}`} className="chat-label">
                      Title
                    </label>
                    <input
                      id={`dm-stage-title-${article.id}`}
                      value={draft.title}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            title: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <label htmlFor={`dm-stage-body-${article.id}`} className="chat-label">
                      Body (markdown or html)
                    </label>
                    <textarea
                      id={`dm-stage-body-${article.id}`}
                      rows={6}
                      value={draft.body}
                      onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            body: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <label htmlFor={`dm-stage-alt-${article.id}`} className="chat-label">
                      Image alt text (optional)
                    </label>
                    <input
                      id={`dm-stage-alt-${article.id}`}
                      value={draft.imageAltText}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            imageAltText: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <label htmlFor={`dm-stage-caption-${article.id}`} className="chat-label">
                      Image caption (optional)
                    </label>
                    <input
                      id={`dm-stage-caption-${article.id}`}
                      value={draft.imageCaption}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            imageCaption: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <div className="article-actions">
                      <button
                        type="button"
                        disabled={updateArticleMutation.isPending}
                        onClick={() =>
                          updateArticleMutation.mutate({
                            id: article.id,
                            payload: {
                              title: draft.title,
                              body_markdown: draft.body,
                              image_alt_text: draft.imageAltText || "",
                              image_caption: draft.imageCaption || "",
                            },
                          })
                        }
                      >
                        {updateArticleMutation.isPending ? "Saving..." : "Save draft"}
                      </button>
                      <button
                        type="button"
                        className="button-danger"
                        disabled={revealArticleMutation.isPending}
                        onClick={() => revealArticleMutation.mutate(article.id)}
                      >
                        {revealArticleMutation.isPending ? "Revealing..." : "Reveal"}
                      </button>
                      <button
                        type="button"
                        className="button-danger"
                        disabled={deleteArticleMutation.isPending}
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="status status-neutral">No staged articles.</p>
          )}
        </section>
      </div>

      <section className="split-grid">
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Revealed articles</h3>
            <span className="pill">{revealedArticles.length}</span>
          </div>
          <div className="session-surface-subhead">
            <button
              type="button"
              className="button-danger"
              disabled={clearRevealedMutation.isPending || !revealedArticles.length}
              onClick={() => clearRevealedMutation.mutate()}
            >
              {clearRevealedMutation.isPending ? "Clearing..." : "Clear all revealed"}
            </button>
          </div>
          {revealedArticles.length ? (
            <div className="article-stack">
              {revealedArticles.map((article) => (
                <details className="article-card" key={article.id}>
                  <summary>
                    <strong>{article.title}</strong>
                    <span className="article-kind">{article.source_kind || "unclassified"}</span>
                  </summary>
                  {article.image ? (
                    <img className="article-image" src={resolveArticleImage(campaignSlug, article)} alt={article.image.alt_text || "Article image"} />
                  ) : null}
                  {renderArticleBody(article)}
                  <div className="article-actions">
                    <button
                      type="button"
                      className="button-danger"
                      onClick={() => deleteArticleMutation.mutate(article.id)}
                      disabled={deleteArticleMutation.isPending}
                    >
                      {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <p className="status status-neutral">No revealed articles.</p>
          )}
        </section>
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Session logs</h3>
            <span className="pill">{sessionLogs.length}</span>
          </div>
          {sessionLogs.length ? (
            <div className="session-log-row">
              <div className="session-log-list">
                {sessionLogs.map((entry) => (
                  <button
                    type="button"
                    key={entry.session.id}
                    className={`session-log-list-row ${entry.session.id === selectedLogSessionId ? "active" : ""}`}
                    onClick={() => setSelectedLogSessionId(entry.session.id)}
                  >
                    <strong>Session {entry.session.id}</strong>
                    <span>{entry.message_count} messages</span>
                    <small>{formatTimestamp(entry.last_message_at)}</small>
                  </button>
                ))}
              </div>
              <div className="session-log-detail">
                {logQuery.isLoading ? (
                  <p className="status status-neutral">Loading log detail...</p>
                ) : null}
                {logQuery.error ? <p className="status status-error">Unable to load log details.</p> : null}
                {logQuery.data ? (
                  <div>
                    <div className="session-log-detail-head">
                      <h4>Messages</h4>
                      <button
                        type="button"
                        className="button-danger"
                        onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}
                        disabled={deleteLogMutation.isPending}
                      >
                        {deleteLogMutation.isPending ? "Deleting..." : "Delete this log"}
                      </button>
                    </div>
                    <ol className="log-messages">
                      {logQuery.data.messages.map((entry) => (
                        <li key={entry.id}>
                          <strong>{entry.author_display_name}</strong> [{formatTimestamp(entry.created_at)}]
                          <p>{entry.body_text}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : (
                  <p className="status status-neutral">Select a log to inspect.</p>
                )}
              </div>
            </div>
          ) : (
            <p className="status status-neutral">No closed session logs.</p>
          )}
        </section>
      </section>
    </div>
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
    queryFn: () => apiClient.getSession(resolvedCampaignSlug),
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

  useEffect(() => {
    if (!canManage && activePane === "dm") {
      setActivePane("session");
    }
  }, [activePane, canManage]);

  const paneError = getApiErrorMessage(sessionQuery.error);

  return (
    <section className="panel">
      <div className="panel-header">
        <Link to="/" className="button button-secondary">
          Back to list
        </Link>
        <h2>Session: {payload?.campaign.title ?? resolvedCampaignSlug}</h2>
        {canManage ? <span className="pill">DM+</span> : null}
      </div>

      <ApiErrorNotice
        isLoading={sessionQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />

      <div className="session-tab-strip">
        <button
          type="button"
          className={activePane === "session" ? "tab-button active" : "tab-button"}
          onClick={() => setActivePane("session")}
        >
          Session
        </button>
        <button
          type="button"
          className={activePane === "character" ? "tab-button active" : "tab-button"}
          onClick={() => setActivePane("character")}
        >
          Character
        </button>
        {canManage ? (
          <button
            type="button"
            className={activePane === "dm" ? "tab-button active" : "tab-button"}
            onClick={() => setActivePane("dm")}
          >
            DM
          </button>
        ) : null}
      </div>

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

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const routeTree = rootRoute.addChildren([campaignsRoute, campaignSessionRoute]);
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
