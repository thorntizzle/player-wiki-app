import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "@tanstack/react-router";

import { apiErrorMessage } from "../api/client";
import type {
  SessionArticle,
  SessionArticleCreatePayload,
  SessionArticleSourceResult,
  SessionDmPassiveScoreRow,
  SessionLogSummary,
  SessionPayload,
} from "../api/types";
import { useApiClient } from "../apiClientContext";
import { DmArticleCreator } from "../components/DmArticleCreator";
import { ToastNotice, useToastNotice } from "../components/feedback";
import {
  renderArticleBody,
  resolveArticleImage,
  SessionArticleReferenceActions,
  SessionArticleSourceLine,
} from "../components/SessionArticleDisplay";
import type { StagedArticleDraftState } from "../dmContentUtils";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import {
  buildEmptyManualArticleDraft,
  type ArticleMode,
  type EmbeddedImageInput,
  type ManualArticleDraftState,
} from "../sessionArticleDrafts";
import { useSessionDmMutations } from "../sessionDmMutations";
import { formatTimestamp } from "../timeFormatting";

function formatSourceSearchStatus(message: string | undefined, resultCount: number): string {
  const trimmedMessage = message?.trim();
  if (trimmedMessage) {
    return trimmedMessage;
  }
  if (resultCount > 0) {
    return `Found ${resultCount} matching article${resultCount === 1 ? "" : "s"}.`;
  }
  return "No published wiki or Systems articles matched that search.";
}

type DmPaneView = "tools" | "staged" | "revealed" | "stage" | "logs";

const readDmPaneView = (search: string): DmPaneView => {
  const requested = new URLSearchParams(search).get("dm_view");
  return requested === "staged" || requested === "revealed" || requested === "stage" || requested === "logs"
    ? requested
    : "tools";
};

const DmPaneViewNav = ({
  activeView,
  setActiveView,
}: {
  activeView: DmPaneView;
  setActiveView: (next: DmPaneView) => void;
}) => (
  <div className="hero-actions session-tab-strip" aria-label="Session DM views">
    <button
      type="button"
      className={activeView === "tools" ? "tab-button button-link" : "tab-button ghost-button"}
      aria-pressed={activeView === "tools"}
      onClick={() => setActiveView("tools")}
    >
      DM Tools
    </button>
    <button
      type="button"
      className={activeView === "staged" ? "tab-button button-link" : "tab-button ghost-button"}
      aria-pressed={activeView === "staged"}
      onClick={() => setActiveView("staged")}
    >
      Staged Articles
    </button>
    <button
      type="button"
      className={activeView === "revealed" ? "tab-button button-link" : "tab-button ghost-button"}
      aria-pressed={activeView === "revealed"}
      onClick={() => setActiveView("revealed")}
    >
      Revealed Articles
    </button>
    <button
      type="button"
      className={activeView === "stage" ? "tab-button button-link" : "tab-button ghost-button"}
      aria-pressed={activeView === "stage"}
      onClick={() => setActiveView("stage")}
    >
      Stage Session Articles
    </button>
    <button
      type="button"
      className={activeView === "logs" ? "tab-button button-link" : "tab-button ghost-button"}
      aria-pressed={activeView === "logs"}
      onClick={() => setActiveView("logs")}
    >
      Chat Logs
    </button>
  </div>
);

export function DmPane({
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
  const location = useLocation();
  const navigate = useNavigate();
  const activeDmView = readDmPaneView(location.searchStr);
  const { apiClient } = useApiClient();
  const stagedArticles: SessionArticle[] = payload?.staged_articles ?? [];
  const revealedArticles: SessionArticle[] = payload?.revealed_articles ?? [];
  const sessionLogs: SessionLogSummary[] = payload?.session_logs ?? [];
  const passiveScores: SessionDmPassiveScoreRow[] = payload?.session_dm_passive_scores ?? [];
  const shouldShowPassiveScores = Boolean(payload?.show_session_dm_passive_scores);
  const activeSession = payload?.active_session;
  const activeMessageCount = payload?.messages.length ?? 0;
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState<ManualArticleDraftState>(buildEmptyManualArticleDraft);
  const [uploadDraft, setUploadDraft] = useState({ filename: "", markdown: "", image: null as EmbeddedImageInput | null });
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceResults, setSourceResults] = useState<SessionArticleSourceResult[]>([]);
  const [sourceStatus, setSourceStatus] = useState<string | null>(null);
  const [selectedSourceRef, setSelectedSourceRef] = useState("");
  const [stagedDrafts, setStagedDrafts] = useState<Record<number, StagedArticleDraftState>>({});
  const [paneError, setPaneError] = useState<string | null>(null);
  const [selectedLogSessionId, setSelectedLogSessionId] = useState<number | null>(null);
  const [deleteArticleConfirm, setDeleteArticleConfirm] = useState<Record<number, boolean>>({});
  const [deleteLogConfirm, setDeleteLogConfirm] = useState<Record<number, boolean>>({});
  const [clearRevealedConfirmed, setClearRevealedConfirmed] = useState(false);
  const [closeSessionConfirmed, setCloseSessionConfirmed] = useState(false);
  const { clearToast, showToast, toastMessage, toastTone } = useToastNotice({ defaultTone: "success" });

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

  const {
    clearRevealedMutation,
    closeSessionMutation,
    createArticleMutation,
    deleteArticleMutation,
    deleteLogMutation,
    revealArticleMutation,
    startSessionMutation,
    updateArticleMutation,
  } = useSessionDmMutations({
    apiClient,
    campaignSlug,
    selectedLogSessionId,
    setAuthRequired,
    showToastMessage: showToast,
    setPaneError,
    setManualDraft,
    setSelectedLogSessionId,
    refetch,
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

  const setArticleDeleteConfirmed = (articleId: number, confirmed: boolean) => {
    setDeleteArticleConfirm((current) => ({
      ...current,
      [articleId]: confirmed,
    }));
  };

  const deleteArticle = (articleId: number) => {
    deleteArticleMutation.mutate(articleId);
    setArticleDeleteConfirmed(articleId, false);
  };

  const setLogDeleteConfirmed = (sessionId: number, confirmed: boolean) => {
    setDeleteLogConfirm((current) => ({
      ...current,
      [sessionId]: confirmed,
    }));
  };

  const deleteLog = (sessionId: number) => {
    deleteLogMutation.mutate(sessionId);
    setLogDeleteConfirmed(sessionId, false);
  };

  const clearRevealedArticles = () => {
    clearRevealedMutation.mutate();
    setClearRevealedConfirmed(false);
  };

  const closeSession = () => {
    closeSessionMutation.mutate();
    setCloseSessionConfirmed(false);
  };

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
      setSourceStatus(formatSourceSearchStatus(response.message, response.results.length));
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
    clearToast();
  };

  const statusText = startSessionMutation.isPending ? "Starting session..." : closeSessionMutation.isPending ? "Closing session..." : null;
  const setDmPaneView = (next: DmPaneView) => {
    const params = new URLSearchParams(location.searchStr);
    if (next === "tools") {
      params.delete("dm_view");
    } else {
      params.set("dm_view", next);
    }
    const search = params.toString();
    const nextLocation = `${location.pathname}${search ? `?${search}` : ""}`;
    void navigate({ to: nextLocation as never, resetScroll: false });
  };
  const subviewClass = (view: DmPaneView) => (
    activeDmView === view ? "session-dm-subview" : "session-dm-subview pane-hidden"
  );

  return (
    <>
      <ToastNotice message={toastMessage} tone={toastTone} />
      <div className="page-layout session-layout session-layout--single">
        <section className="session-column">
          <DmPaneViewNav activeView={activeDmView} setActiveView={setDmPaneView} />

          <div className={subviewClass("tools")}>
            {shouldShowPassiveScores ? (
              <details className="section-block section-block--collapsible session-passive-scores-bar" id="session-passive-scores" open>
                <summary className="section-toggle-summary">
                  <span className="section-toggle-summary__content">
                    <span className="section-title">Passive scores</span>
                    <span className="meta">{passiveScores.length}</span>
                  </span>
                  <span className="section-toggle-chevron" aria-hidden="true"></span>
                </summary>
                <div className="section-block__body">
                  {passiveScores.length ? (
                    <div className="session-passive-score-list">
                      {passiveScores.map((row) => (
                        <article className="session-passive-score-card" key={row.name}>
                          <h4>{row.name}</h4>
                          <div className="session-passive-score-grid">
                            <p>
                              <span className="session-passive-score-label">Passive Perception</span>
                              <span className="session-passive-score-value">{row.passive_perception}</span>
                            </p>
                            <p>
                              <span className="session-passive-score-label">Passive Insight</span>
                              <span className="session-passive-score-value">{row.passive_insight}</span>
                            </p>
                            <p>
                              <span className="session-passive-score-label">Passive Investigation</span>
                              <span className="session-passive-score-value">{row.passive_investigation}</span>
                            </p>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="status status-neutral">
                      No visible DND-5E characters are currently available on the DM session surface.
                    </p>
                  )}
                </div>
              </details>
            ) : null}

            <article className="card session-sidebar-card" id="session-dm-references">
              <div className="section-heading">
                <h2>DM references</h2>
                <p className="meta">Coming soon</p>
              </div>
              <p className="meta">Use this area for future DM reference materials.</p>
            </article>

            <article className="card session-sidebar-card" id="session-controls">
              <div className="section-heading">
                <h2>Live session</h2>
                <p className="meta">{activeSession ? "Chat open" : "Chat closed"}</p>
              </div>
              {activeSession ? (
                <>
                  <p>The session is live for players and the DM.</p>
                  <p className="meta">Started {formatTimestamp(activeSession.started_at)}</p>
                  <p className="meta">
                    {activeMessageCount} chat entr{activeMessageCount === 1 ? "y" : "ies"}
                  </p>
                </>
              ) : (
                <>
                  <p>No active session is running right now.</p>
                  <p className="meta">Start the session here to open chat on the player Session page.</p>
                </>
              )}
              <div className="session-status-controls">
                <h3>Session controls</h3>
                {!activeSession ? (
                  <p>Start a session here to open chat on the player Session page and reveal staged handouts.</p>
                ) : null}
                {statusText ? <p className="meta">{statusText}</p> : null}
                {startSessionMutation.error ? (
                  <p className="status status-error">{apiErrorMessage(startSessionMutation.error)}</p>
                ) : null}
                {closeSessionMutation.error ? (
                  <p className="status status-error">{apiErrorMessage(closeSessionMutation.error)}</p>
                ) : null}
                {paneError ? <p className="status status-error">{paneError}</p> : null}
              </div>
              <div className="session-actions-row">
                {activeSession ? (
                  <form
                    className="confirmed-action"
                    onSubmit={(event) => {
                      event.preventDefault();
                      closeSession();
                    }}
                  >
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={closeSessionConfirmed}
                        disabled={closeSessionMutation.isPending}
                        onChange={(event) => setCloseSessionConfirmed(event.currentTarget.checked)}
                      />
                      Confirm close
                    </label>
                    <button
                      type="submit"
                      className="ghost-button"
                      disabled={closeSessionMutation.isPending || !closeSessionConfirmed}
                    >
                      {closeSessionMutation.isPending ? "Closing..." : "Close session"}
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => startSessionMutation.mutate()}
                    disabled={startSessionMutation.isPending}
                  >
                    {startSessionMutation.isPending ? "Starting..." : "Begin session"}
                  </button>
                )}
              </div>
            </article>
          </div>

          <div className={subviewClass("staged")}>
            <article className="card session-sidebar-card" id="session-staged-articles">
              <div className="section-heading">
                <h2>Staged articles</h2>
                <p className="meta">{stagedArticles.length}</p>
              </div>
              {stagedArticles.length ? (
                <div className="session-article-stack">
                  {stagedArticles.map((article) => {
                    const savedLabel = article.created_at ? `Saved ${formatTimestamp(article.created_at)}` : null;
                    const draft = stagedDrafts[article.id] ?? {
                      title: article.title,
                      body: article.body_markdown,
                      imageAltText: article.image?.alt_text || "",
                      imageCaption: article.image?.caption || "",
                    };
                    const deleteConfirmed = Boolean(deleteArticleConfirm[article.id]);

                    return (
                      <details className="feature-detail session-article-detail" data-session-article-id={article.id} key={article.id}>
                        <summary>
                          <span>{article.title}</span>
                          {savedLabel ? <span className="meta">{savedLabel}</span> : null}
                        </summary>
                        {article.image ? (
                          <figure className="article-figure">
                            <img className="article-image" src={resolveArticleImage(campaignSlug, article)} alt={article.image.alt_text || "Article image"} />
                            {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                          </figure>
                        ) : null}
                        <SessionArticleSourceLine article={article} />
                        {renderArticleBody(article, "article-body--compact")}
                        <details className="session-article-edit-detail">
                          <summary>Edit prep draft</summary>
                          <form
                            className="stack-form session-article-edit-form"
                            onSubmit={(event: FormEvent<HTMLFormElement>) => {
                              event.preventDefault();
                              const articlePayload: {
                                title: string;
                                body_markdown: string;
                                image_alt_text?: string;
                                image_caption?: string;
                              } = {
                                title: draft.title,
                                body_markdown: draft.body,
                              };
                              if (article.image) {
                                articlePayload.image_alt_text = draft.imageAltText || "";
                                articlePayload.image_caption = draft.imageCaption || "";
                              }
                              updateArticleMutation.mutate({
                                id: article.id,
                                payload: articlePayload,
                              });
                            }}
                          >
                            <label className="field" htmlFor={`dm-stage-title-${article.id}`}>
                              <span>Title</span>
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
                            </label>
                            <label className="field" htmlFor={`dm-stage-body-${article.id}`}>
                              <span>Body (markdown or html)</span>
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
                            </label>
                            <label className="field" htmlFor={`dm-stage-alt-${article.id}`}>
                              <span>Image alt text (optional)</span>
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
                            </label>
                            <label className="field" htmlFor={`dm-stage-caption-${article.id}`}>
                              <span>Image caption (optional)</span>
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
                            </label>
                            <button
                              type="submit"
                              className="ghost-button"
                              disabled={updateArticleMutation.isPending}
                            >
                              {updateArticleMutation.isPending ? "Saving..." : "Update prep draft"}
                            </button>
                          </form>
                        </details>
                        <div className="session-article-detail__actions">
                          <SessionArticleReferenceActions article={article} includePromotionLinks />
                          {activeSession ? (
                            <button
                              type="button"
                              className="ghost-button"
                              disabled={revealArticleMutation.isPending}
                              onClick={() => revealArticleMutation.mutate(article.id)}
                            >
                              {revealArticleMutation.isPending ? "Revealing..." : "Reveal in chat"}
                            </button>
                          ) : (
                            <p className="meta">Begin a session before revealing this article.</p>
                          )}
                          <form
                            className="confirmed-action"
                            onSubmit={(event) => {
                              event.preventDefault();
                              deleteArticle(article.id);
                            }}
                          >
                            <label className="checkbox-label">
                              <input
                                type="checkbox"
                                checked={deleteConfirmed}
                                disabled={deleteArticleMutation.isPending}
                                onChange={(event) => setArticleDeleteConfirmed(article.id, event.currentTarget.checked)}
                              />
                              Confirm delete
                            </label>
                            <button
                              type="submit"
                              className="ghost-button"
                              disabled={!deleteConfirmed || deleteArticleMutation.isPending}
                            >
                              {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                            </button>
                          </form>
                        </div>
                      </details>
                    );
                  })}
                </div>
              ) : (
                <p className="meta">No unrevealed session articles are waiting right now.</p>
              )}
            </article>
          </div>

          <div className={subviewClass("revealed")}>
            {revealedArticles.length ? (
              <article className="card session-sidebar-card" id="session-revealed-articles">
                <div className="section-heading">
                  <div>
                    <h2>Revealed articles</h2>
                    <p className="meta">{revealedArticles.length}</p>
                  </div>
                  <form
                    className="confirmed-action"
                    onSubmit={(event) => {
                      event.preventDefault();
                      clearRevealedArticles();
                    }}
                  >
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={clearRevealedConfirmed}
                        disabled={clearRevealedMutation.isPending || !revealedArticles.length}
                        onChange={(event) => setClearRevealedConfirmed(event.currentTarget.checked)}
                      />
                      Confirm clear
                    </label>
                    <button
                      type="submit"
                      className="ghost-button"
                      disabled={clearRevealedMutation.isPending || !revealedArticles.length || !clearRevealedConfirmed}
                    >
                      {clearRevealedMutation.isPending ? "Clearing..." : "Clear all"}
                    </button>
                  </form>
                </div>
                <div className="session-article-stack">
                  {revealedArticles.map((article) => {
                    const revealedLabel = article.revealed_at
                      ? `Revealed ${formatTimestamp(article.revealed_at)}`
                      : article.created_at
                        ? `Revealed ${formatTimestamp(article.created_at)}`
                        : null;
                    const deleteConfirmed = Boolean(deleteArticleConfirm[article.id]);
                    return (
                      <details className="feature-detail session-article-detail" data-session-article-id={article.id} key={article.id}>
                        <summary>
                          <span>{article.title}</span>
                          {revealedLabel ? <span className="meta">{revealedLabel}</span> : null}
                        </summary>
                        {article.image ? (
                          <figure className="article-figure">
                            <img
                              className="article-image"
                              src={resolveArticleImage(campaignSlug, article)}
                              alt={article.image.alt_text || "Article image"}
                            />
                            {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                          </figure>
                        ) : null}
                        <SessionArticleSourceLine article={article} />
                        {renderArticleBody(article, "article-body--compact")}
                        <div className="session-article-detail__actions">
                          <SessionArticleReferenceActions article={article} includePromotionLinks />
                          <form
                            className="confirmed-action"
                            onSubmit={(event) => {
                              event.preventDefault();
                              deleteArticle(article.id);
                            }}
                          >
                            <label className="checkbox-label">
                              <input
                                type="checkbox"
                                checked={deleteConfirmed}
                                disabled={deleteArticleMutation.isPending}
                                onChange={(event) => setArticleDeleteConfirmed(article.id, event.currentTarget.checked)}
                              />
                              Confirm delete
                            </label>
                            <button
                              type="submit"
                              className="ghost-button"
                              disabled={!deleteConfirmed || deleteArticleMutation.isPending}
                            >
                              {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                            </button>
                          </form>
                        </div>
                      </details>
                    );
                  })}
                </div>
              </article>
            ) : (
              <article className="card session-sidebar-card" id="session-revealed-articles">
                <div className="section-heading">
                  <h2>Revealed articles</h2>
                  <p className="meta">{revealedArticles.length}</p>
                </div>
                <p className="meta">No revealed session articles are visible yet.</p>
              </article>
            )}
          </div>

          <div className={subviewClass("stage")}>
            <DmArticleCreator
              className="card session-sidebar-card"
              id="session-article-store"
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
                setSourceStatus(null);
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
          </div>

          <div className={subviewClass("logs")}>
            <article className="card session-sidebar-card" id="session-chat-logs">
              <div className="section-heading">
                <h2>Chat logs</h2>
                <p className="meta">{sessionLogs.length}</p>
              </div>
              {sessionLogs.length ? (
                <div className="session-log-row">
                  <ul className="plain-list session-log-list">
                    {sessionLogs.map((entry) => {
                      const sessionLabel = entry.session.started_at
                        ? `Session log from ${formatTimestamp(entry.session.started_at)}`
                        : `Session ${entry.session.id}`;
                      const messageMeta = `${entry.message_count} message${entry.message_count === 1 ? "" : "s"}`;
                      const deleteConfirmed = Boolean(deleteLogConfirm[entry.session.id]);
                      return (
                        <li key={entry.session.id}>
                          <div className="session-log-list__row">
                            <button
                              type="button"
                              className={`session-log-list__content ${entry.session.id === selectedLogSessionId ? "active" : ""}`}
                              onClick={() => setSelectedLogSessionId(entry.session.id)}
                            >
                              <strong>{sessionLabel}</strong>
                              <p className="meta">
                                {messageMeta}
                                {entry.last_message_at ? ` | Last message ${formatTimestamp(entry.last_message_at)}` : null}
                              </p>
                            </button>
                            <form
                              className="confirmed-action"
                              onSubmit={(event) => {
                                event.preventDefault();
                                deleteLog(entry.session.id);
                              }}
                            >
                              <label className="checkbox-label">
                                <input
                                  type="checkbox"
                                  checked={deleteConfirmed}
                                  disabled={deleteLogMutation.isPending}
                                  onChange={(event) => setLogDeleteConfirmed(entry.session.id, event.currentTarget.checked)}
                                />
                                Confirm delete
                              </label>
                              <button
                                type="submit"
                                className="ghost-button"
                                disabled={!deleteConfirmed || deleteLogMutation.isPending}
                              >
                                {deleteLogMutation.isPending ? "Deleting..." : "Delete log"}
                              </button>
                            </form>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                  <div className="session-log-detail">
                    {logQuery.isLoading ? (
                      <p className="status status-neutral">Loading log detail...</p>
                    ) : null}
                    {logQuery.error ? <p className="status status-error">Unable to load log details.</p> : null}
                    {logQuery.data ? (
                      <div>
                        <h4>Messages</h4>
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
                <p className="meta">Closed sessions will appear here after the first live run.</p>
              )}
            </article>
          </div>
        </section>
      </div>
    </>
  );
}
