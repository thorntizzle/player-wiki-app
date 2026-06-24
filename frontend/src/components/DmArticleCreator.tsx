import type { ChangeEvent, FormEvent } from "react";

import type {
  SessionArticleCreatePayload,
  SessionArticleCreatePayloadManual,
  SessionArticleCreatePayloadUpload,
  SessionArticleCreatePayloadWiki,
  SessionArticleSourceResult,
} from "../api/types";
import {
  readBinaryAsBase64,
  type ArticleMode,
  type ManualArticleDraftState,
  type UploadArticleDraftState,
} from "../sessionArticleDrafts";

interface DmArticleCreatorProps {
  mode: ArticleMode;
  setMode: (mode: ArticleMode) => void;
  sourceQuery: string;
  setSourceQuery: (value: string) => void;
  sourceStatus: string | null;
  setSourceStatus: (value: string | null) => void;
  sourceResults: SessionArticleSourceResult[];
  selectedSourceRef: string;
  setSelectedSourceRef: (value: string) => void;
  manualDraft: ManualArticleDraftState;
  setManualDraft: (state: ManualArticleDraftState) => void;
  uploadDraft: UploadArticleDraftState;
  setUploadDraft: (state: UploadArticleDraftState) => void;
  onSearchSources: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCreate: (payload: SessionArticleCreatePayload) => void;
  isCreating: boolean;
  className?: string;
  id?: string;
}

export function DmArticleCreator({
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
  className = "card",
  id,
}: DmArticleCreatorProps) {
  const idSeed = id === "dm-content-staged-article-store" ? "dm-content" : "session";
  const manualModeRadioId = `${idSeed}-article-mode-manual`;
  const uploadModeRadioId = `${idSeed}-article-mode-upload`;
  const wikiModeRadioId = `${idSeed}-article-mode-wiki`;
  const manualModeLabel = `${idSeed}-manual`;
  const uploadModeLabel = `${idSeed}-upload`;
  const wikiModeLabel = `${idSeed}-wiki`;
  const manualImageInputId = `${idSeed}-manual-image-file`;
  const uploadReferencedImageInputId = `${idSeed}-upload-referenced-image-file`;
  const wikiSearchInputId = `${idSeed}-wiki-search`;

  const instructions =
    mode === "manual"
      ? "Use a title with markdown body or an image and create an unrevealed article."
      : mode === "upload"
        ? "Upload mode needs a filename and markdown body."
        : "Search and select a source, then pull into staged articles.";
  const mergedClassName = Array.from(new Set(`card ${className ?? ""}`.split(/\s+/).filter(Boolean))).join(" ");
  const wikiSearchStatusText = sourceStatus ?? "Type at least 2 letters to search published wiki pages and Systems entries.";
  const selectedSource = selectedSourceRef
    ? sourceResults.find((result) => result.source_ref === selectedSourceRef)
    : null;
  const selectedSourceLabel = selectedSource?.select_label || selectedSource?.title || "";

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "wiki") {
      await onSearchSources(event);
    }
  };

  return (
    <article className={mergedClassName} id={id}>
      <h2>Stage session articles</h2>
      <form className="stack-form" onSubmit={onSubmit}>
        <input
          className="session-form-mode-radio session-form-mode-radio--manual"
          type="radio"
          id={manualModeRadioId}
          name={`${idSeed}-article-mode`}
          value="manual"
          checked={mode === "manual"}
          onChange={() => setMode("manual")}
        />
        <input
          className="session-form-mode-radio session-form-mode-radio--upload"
          type="radio"
          id={uploadModeRadioId}
          name={`${idSeed}-article-mode`}
          value="upload"
          checked={mode === "upload"}
          onChange={() => setMode("upload")}
        />
        <input
          className="session-form-mode-radio session-form-mode-radio--wiki"
          type="radio"
          id={wikiModeRadioId}
          name={`${idSeed}-article-mode`}
          value="wiki"
          checked={mode === "wiki"}
          onChange={() => setMode("wiki")}
        />
        <div
          className="session-form-mode-toggle"
          role="radiogroup"
          aria-label={id === "dm-content-staged-article-store" ? "Staged article input mode" : "Session article input mode"}
        >
          <label className="ghost-button" htmlFor={manualModeRadioId}>
            Manual
          </label>
          <label className="ghost-button" htmlFor={uploadModeRadioId}>
            Upload
          </label>
          <label className="ghost-button" htmlFor={wikiModeRadioId}>
            Lookup
          </label>
        </div>
        <p className="status status-neutral">{instructions}</p>

        {mode === "manual" ? (
          <div className="session-article-mode-panel session-article-mode-panel--manual" data-session-article-mode-panel="manual">
            <label className="field" htmlFor={`${manualModeLabel}-title`}>
              <span>Title</span>
              <input
                id={`${manualModeLabel}-title`}
                value={manualDraft.title}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setManualDraft({ ...manualDraft, title: event.currentTarget.value });
                }}
              />
            </label>
            <label className="field" htmlFor={`${manualModeLabel}-body`}>
              <span>Body</span>
              <textarea
                id={`${manualModeLabel}-body`}
                rows={8}
                value={manualDraft.body}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                  setManualDraft({ ...manualDraft, body: event.currentTarget.value });
                }}
              />
            </label>
            <div className="field session-file-field">
              <span>Image</span>
              <input
                className="session-file-input"
                id={manualImageInputId}
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.gif"
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  const file = event.currentTarget.files?.item(0);
                  if (!file) {
                    setManualDraft({ ...manualDraft, image: null });
                    return;
                  }
                  readBinaryAsBase64(file, (payload) => {
                    setManualDraft({ ...manualDraft, image: payload });
                  });
                }}
              />
              <label className="session-file-dropzone" htmlFor={manualImageInputId} tabIndex={0}>
                <strong>Drag and drop a file here</strong>
                <span className="meta">or use Browse to choose one</span>
                <span className="session-file-dropzone__browse">Browse</span>
                <span className="meta session-file-dropzone__name">
                  {manualDraft.image ? manualDraft.image.filename : "No file selected."}
                </span>
              </label>
            </div>
            <label className="field" htmlFor={`${manualModeLabel}-image-alt`}>
              <span>Image alt text</span>
              <input
                id={`${manualModeLabel}-image-alt`}
                value={manualDraft.imageAltText}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setManualDraft({ ...manualDraft, imageAltText: event.currentTarget.value });
                }}
              />
            </label>
            <label className="field" htmlFor={`${manualModeLabel}-image-caption`}>
              <span>Image caption</span>
              <input
                id={`${manualModeLabel}-image-caption`}
                value={manualDraft.imageCaption}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setManualDraft({ ...manualDraft, imageCaption: event.currentTarget.value });
                }}
              />
            </label>
            <button
              type="button"
              className="button"
              disabled={
                isCreating
                || !manualDraft.title.trim()
                || (!manualDraft.body.trim() && !manualDraft.image)
              }
              onClick={() =>
                onCreate({
                  mode: "manual",
                  title: manualDraft.title.trim(),
                  body_markdown: manualDraft.body,
                  image: manualDraft.image
                    ? {
                        ...manualDraft.image,
                        alt_text: manualDraft.imageAltText.trim() || null,
                        caption: manualDraft.imageCaption.trim() || null,
                      }
                    : undefined,
                } satisfies SessionArticleCreatePayloadManual)
              }
            >
              {isCreating ? "Creating..." : "Create"}
            </button>
          </div>
        ) : null}

        {mode === "upload" ? (
          <div className="session-article-mode-panel session-article-mode-panel--upload" data-session-article-mode-panel="upload">
            <p className="meta">
              The article title comes from markdown frontmatter, then <code># Heading</code>, then the filename.
            </p>
            <label className="field" htmlFor={`${uploadModeLabel}-filename`}>
              <span>Source filename</span>
              <input
                id={`${uploadModeLabel}-filename`}
                value={uploadDraft.filename}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setUploadDraft({ ...uploadDraft, filename: event.currentTarget.value });
                }}
                placeholder="notes.md"
              />
            </label>
            <label className="field" htmlFor={`${uploadModeLabel}-markdown`}>
              <span>Markdown text</span>
              <textarea
                id={`${uploadModeLabel}-markdown`}
                rows={8}
                value={uploadDraft.markdown}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                  setUploadDraft({ ...uploadDraft, markdown: event.currentTarget.value });
                }}
              />
            </label>
            <div className="field session-file-field">
              <span>Referenced image</span>
              <input
                className="session-file-input"
                id={uploadReferencedImageInputId}
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
              <label className="session-file-dropzone" htmlFor={uploadReferencedImageInputId} tabIndex={0}>
                <strong>Drag and drop a file here</strong>
                <span className="meta">or use Browse to choose one</span>
                <span className="session-file-dropzone__browse">Browse</span>
                <span className="meta session-file-dropzone__name">
                  {uploadDraft.image ? uploadDraft.image.filename : "No file selected."}
                </span>
              </label>
            </div>
            <p className="meta">
              If markdown references an image in frontmatter or an embedded image tag, upload that image here.
            </p>
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
          </div>
        ) : null}

        {mode === "wiki" ? (
          <div className="session-article-mode-panel session-article-mode-panel--wiki" data-session-article-mode-panel="wiki">
            <label className="field" htmlFor={wikiSearchInputId}>
              <span>Search</span>
              <input
                id={wikiSearchInputId}
                type="search"
                value={sourceQuery}
                autoComplete="off"
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setSourceQuery(event.currentTarget.value);
                  setSourceStatus(null);
                  setSelectedSourceRef("");
                }}
              />
            </label>
            <label className="field" htmlFor={`${wikiModeLabel}-source-results`}>
              <span>Matching articles</span>
              <select
                id={`${wikiModeLabel}-source-results`}
                value={selectedSourceRef}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                  setSelectedSourceRef(event.currentTarget.value);
                }}
                disabled={sourceResults.length === 0}
              >
                <option value="">Search to load matching articles</option>
                {sourceResults.map((result) => (
                  <option key={result.source_ref} value={result.source_ref}>
                    {result.title}
                  </option>
                ))}
              </select>
            </label>
            <p className="meta" data-session-article-source-status>
              {wikiSearchStatusText}
            </p>
            <div className="wiki-selection">
              <p className="status status-neutral">
                {selectedSourceRef
                  ? selectedSourceLabel
                    ? `Selected source: ${selectedSourceLabel}`
                    : "Selected source ready."
                  : "No source selected"}
              </p>
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
            <button type="submit">Search</button>
          </div>
        ) : null}
      </form>
    </article>
  );
}
