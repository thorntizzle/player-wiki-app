import { useState, type ChangeEvent, type FormEvent } from "react";

import type { SessionArticle } from "../api/types";
import {
  buildInitialStagedArticleDraft,
  type StagedArticleDraftState,
} from "../dmContentUtils";
import { readBinaryAsBase64 } from "../sessionArticleDrafts";
import { formatTimestamp } from "../timeFormatting";
import {
  renderArticleBody,
  resolveArticleImage,
  SessionArticleReferenceActions,
  SessionArticleSourceLine,
} from "./SessionArticleDisplay";

interface DmStagedArticleQueueProps {
  campaignSlug: string;
  stagedArticles: SessionArticle[];
  stagedDrafts: Record<number, StagedArticleDraftState>;
  canManageSession: boolean;
  isUpdating: boolean;
  isDeleting: boolean;
  onDraftChange: (
    article: SessionArticle,
    fallbackDraft: StagedArticleDraftState,
    updates: Partial<StagedArticleDraftState>,
  ) => void;
  onUpdateArticle: (args: { id: number; payload: StagedArticleDraftState; hasExistingImage: boolean }) => void;
  onDeleteArticle: (articleId: number) => void;
}

export function DmStagedArticleQueue({
  campaignSlug,
  stagedArticles,
  stagedDrafts,
  canManageSession,
  isUpdating,
  isDeleting,
  onDraftChange,
  onUpdateArticle,
  onDeleteArticle,
}: DmStagedArticleQueueProps) {
  const [deleteConfirmByArticle, setDeleteConfirmByArticle] = useState<Record<number, boolean>>({});

  const setDeleteConfirmed = (articleId: number, confirmed: boolean) => {
    setDeleteConfirmByArticle((current) => ({
      ...current,
      [articleId]: confirmed,
    }));
  };

  return (
    <article className="card" id="dm-content-staged-articles-queue">
      <div className="section-heading">
        <div>
          <h2>Session reveal queue</h2>
          <p className="meta">Articles created here go straight into the same staged queue used on Session DM.</p>
        </div>
        <p className="meta">{stagedArticles.length}</p>
      </div>
      {stagedArticles.length ? (
        <div className="session-article-stack">
          {stagedArticles.map((article) => {
            const draft = stagedDrafts[article.id] ?? buildInitialStagedArticleDraft(article);
            const savedLabel = article.created_at ? `Saved ${formatTimestamp(article.created_at)}` : null;
            const deleteConfirmed = Boolean(deleteConfirmByArticle[article.id]);
            return (
              <details
                className="feature-detail session-article-detail"
                data-session-article-id={article.id}
                key={article.id}
              >
                <summary>
                  <span>{article.title}</span>
                  {savedLabel ? <span className="meta">{savedLabel}</span> : null}
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
                <details className="session-article-edit-detail">
                  <summary>Edit prep draft</summary>
                  <form
                    className="stack-form session-article-edit-form"
                    onSubmit={(event: FormEvent<HTMLFormElement>) => {
                      event.preventDefault();
                      const formData = new FormData(event.currentTarget);
                      const currentDraft = stagedDrafts[article.id] ?? draft;
                      onUpdateArticle({
                        id: article.id,
                        hasExistingImage: Boolean(article.image),
                        payload: {
                          title: String(formData.get("title") || ""),
                          body: String(formData.get("body_markdown") || ""),
                          imageAltText: String(formData.get("image_alt_text") || ""),
                          imageCaption: String(formData.get("image_caption") || ""),
                          image: currentDraft.image ?? null,
                        },
                      });
                    }}
                  >
                    <label className="field">
                      <span>Title</span>
                      <input
                        id={`dm-content-stage-title-${article.id}`}
                        name="title"
                        value={draft.title}
                        disabled={!canManageSession}
                        onChange={(event: ChangeEvent<HTMLInputElement>) => {
                          onDraftChange(article, draft, { title: event.currentTarget.value });
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>Body</span>
                      <textarea
                        id={`dm-content-stage-body-${article.id}`}
                        name="body_markdown"
                        rows={8}
                        value={draft.body}
                        disabled={!canManageSession}
                        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                          onDraftChange(article, draft, { body: event.currentTarget.value });
                        }}
                      />
                    </label>
                    <div className="field session-file-field">
                      <span>{article.image ? "Replace image" : "Image"}</span>
                      <input
                        id={`dm-content-stage-image-${article.id}`}
                        className="session-file-input"
                        type="file"
                        accept=".png,.jpg,.jpeg,.webp,.gif"
                        disabled={!canManageSession}
                        onChange={(event: ChangeEvent<HTMLInputElement>) => {
                          const file = event.currentTarget.files?.item(0);
                          if (!file) {
                            onDraftChange(article, draft, { image: null });
                            return;
                          }
                          readBinaryAsBase64(file, (payload) => {
                            onDraftChange(article, draft, { image: payload });
                          });
                        }}
                      />
                      <label className="session-file-dropzone" htmlFor={`dm-content-stage-image-${article.id}`} tabIndex={0}>
                        <span>Drag and drop a file here</span>
                        <span className="meta">or use Browse to choose one</span>
                        <span className="session-file-dropzone__browse">Browse</span>
                        <span className="meta session-file-dropzone__name">No file selected.</span>
                      </label>
                    </div>
                    <label className="field">
                      <span>Image alt text</span>
                      <input
                        id={`dm-content-stage-alt-${article.id}`}
                        name="image_alt_text"
                        value={draft.imageAltText}
                        disabled={!canManageSession}
                        onChange={(event: ChangeEvent<HTMLInputElement>) => {
                          onDraftChange(article, draft, { imageAltText: event.currentTarget.value });
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>Image caption</span>
                      <input
                        id={`dm-content-stage-caption-${article.id}`}
                        name="image_caption"
                        value={draft.imageCaption}
                        disabled={!canManageSession}
                        onChange={(event: ChangeEvent<HTMLInputElement>) => {
                          onDraftChange(article, draft, { imageCaption: event.currentTarget.value });
                        }}
                      />
                    </label>
                    {draft.image ? <p className="status status-neutral">Selected image: {draft.image.filename}</p> : null}
                    <button
                      type="submit"
                      className="ghost-button"
                      disabled={!canManageSession || isUpdating}
                    >
                      {isUpdating ? "Saving..." : "Update prep draft"}
                    </button>
                  </form>
                </details>
                <div className="session-article-detail__actions">
                  <SessionArticleReferenceActions article={article} includePromotionLinks />
                  <form
                    className="confirmed-action"
                    onSubmit={(event: FormEvent<HTMLFormElement>) => {
                      event.preventDefault();
                      onDeleteArticle(article.id);
                      setDeleteConfirmed(article.id, false);
                    }}
                  >
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={deleteConfirmed}
                        disabled={!canManageSession || isDeleting}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setDeleteConfirmed(article.id, event.currentTarget.checked)
                        }
                      />
                      Confirm delete
                    </label>
                    <button
                      type="submit"
                      className="ghost-button"
                      disabled={!canManageSession || !deleteConfirmed || isDeleting}
                    >
                      {isDeleting ? "Deleting..." : "Delete article"}
                    </button>
                  </form>
                </div>
              </details>
            );
          })}
        </div>
      ) : (
        <p className="status status-neutral">No staged articles.</p>
      )}
    </article>
  );
}
