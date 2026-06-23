import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

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
import { formatTimestamp } from "../timeFormatting";

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
      setManualDraft(buildEmptyManualArticleDraft());
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
      apiClient.updateSessionArticle(campaignSlug, args.id, args.payload),
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
    <div className="page-layout session-layout">
      <section className="session-column">
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
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={deleteArticleMutation.isPending}
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="meta">No unrevealed session articles are waiting right now.</p>
          )}
        </article>

        {revealedArticles.length ? (
          <article className="card session-sidebar-card" id="session-revealed-articles">
            <div className="section-heading">
              <div>
                <h2>Revealed articles</h2>
                <p className="meta">{revealedArticles.length}</p>
              </div>
              <button
                type="button"
                className="ghost-button"
                disabled={clearRevealedMutation.isPending || !revealedArticles.length}
                onClick={() => clearRevealedMutation.mutate()}
              >
                {clearRevealedMutation.isPending ? "Clearing..." : "Clear all"}
              </button>
            </div>
            <div className="session-article-stack">
              {revealedArticles.map((article) => {
                const revealedLabel = article.revealed_at
                  ? `Revealed ${formatTimestamp(article.revealed_at)}`
                  : article.created_at
                    ? `Revealed ${formatTimestamp(article.created_at)}`
                    : null;
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
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                        disabled={deleteArticleMutation.isPending}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          </article>
        ) : null}

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
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => deleteLogMutation.mutate(entry.session.id)}
                          disabled={deleteLogMutation.isPending}
                        >
                          {deleteLogMutation.isPending ? "Deleting..." : "Delete log"}
                        </button>
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
                    <div className="session-log-detail-head">
                      <h4>Messages</h4>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}
                        disabled={deleteLogMutation.isPending}
                      >
                        {deleteLogMutation.isPending ? "Deleting..." : "Delete log"}
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
            <p className="meta">Closed sessions will appear here after the first live run.</p>
          )}
        </article>
      </section>

      <aside className="session-sidebar">
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
            {statusText || uiMessage ? <p className="meta">{statusText || uiMessage}</p> : null}
            {startSessionMutation.error ? (
              <p className="status status-error">{apiErrorMessage(startSessionMutation.error)}</p>
            ) : null}
            {closeSessionMutation.error ? <p className="status status-error">{apiErrorMessage(closeSessionMutation.error)}</p> : null}
            {paneError ? <p className="status status-error">{paneError}</p> : null}
          </div>
          <div className="session-actions-row">
            {activeSession ? (
              <button type="button" onClick={() => closeSessionMutation.mutate()} disabled={closeSessionMutation.isPending}>
                {closeSessionMutation.isPending ? "Closing..." : "Close session"}
              </button>
            ) : (
              <button type="button" onClick={() => startSessionMutation.mutate()} disabled={startSessionMutation.isPending}>
                {startSessionMutation.isPending ? "Starting..." : "Begin session"}
              </button>
            )}
          </div>
        </article>
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
      </aside>
    </div>
  );
}
