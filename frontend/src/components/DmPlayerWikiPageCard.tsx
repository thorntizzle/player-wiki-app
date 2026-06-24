import type { ChangeEvent, FormEvent } from "react";

import type { ContentPageFileSummary } from "../api/types";
import {
  playerWikiRemovalSafety,
  playerWikiStatusLabel,
  simpleSlug,
  type DmPlayerWikiDraftState,
} from "../dmContentUtils";
import { DmPlayerWikiDraftFields } from "./DmPlayerWikiDraftFields";

interface DmPlayerWikiPageCardProps {
  pageFile: ContentPageFileSummary;
  editDraft?: DmPlayerWikiDraftState;
  deleteConfirmed: boolean;
  encodedCampaignSlug: string;
  canManagePlayerWiki: boolean;
  isArchiving: boolean;
  isDeleting: boolean;
  isSaving: boolean;
  onArchive: (pageRef: string) => void;
  onDelete: (pageRef: string) => void;
  onDeleteConfirmChange: (pageRef: string, checked: boolean) => void;
  onDraftChange: (pageRef: string, next: DmPlayerWikiDraftState) => void;
  onImageReadStatus: (errorMessage: string | null) => void;
  onLoadEditDraft: (pageRef: string) => void | Promise<void>;
  onSaveEditDraft: (pageRef: string, draft: DmPlayerWikiDraftState) => void;
}

export function DmPlayerWikiPageCard({
  pageFile,
  editDraft,
  deleteConfirmed,
  encodedCampaignSlug,
  canManagePlayerWiki,
  isArchiving,
  isDeleting,
  isSaving,
  onArchive,
  onDelete,
  onDeleteConfirmChange,
  onDraftChange,
  onImageReadStatus,
  onLoadEditDraft,
  onSaveEditDraft,
}: DmPlayerWikiPageCardProps) {
  const safety = playerWikiRemovalSafety(pageFile);
  const encodedPageRef = pageFile.page_ref
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  const pageId = `wiki-page-${simpleSlug(pageFile.page_ref)}`;

  return (
    <article className="dm-content-item dm-player-wiki-card" id={pageId}>
      <div className="dm-content-item__header">
        <div>
          <h3>{pageFile.page.title || pageFile.page_ref}</h3>
          {pageFile.page.summary ? <p className="meta">{pageFile.page.summary}</p> : null}
        </div>
        <div className="badge-list">
          <span className="meta-badge">{playerWikiStatusLabel(pageFile)}</span>
          <span className="meta-badge">{pageFile.page.section || "Unsectioned"}</span>
          {pageFile.page.subsection ? <span className="meta-badge">{pageFile.page.subsection}</span> : null}
          {pageFile.page.image_path ? <span className="meta-badge">Image</span> : null}
          <span className="meta-badge">{safety.removal_status_label}</span>
        </div>
      </div>
      <details className="feature-detail dm-maintenance-detail">
        <summary>Maintenance details</summary>
        <p className="meta">Publish location: {pageFile.page_ref}.md</p>
        {pageFile.page.source_ref ? <p className="meta">Original source: {pageFile.page.source_ref}</p> : null}
      </details>
      <div className="dm-content-removal-safety">
        <p className="meta">
          <strong>Removal safety:</strong> {safety.removal_guidance}
        </p>
        {safety.hard_delete_blockers.length ? (
          <ul className="plain-list">
            {safety.hard_delete_blockers.map((blocker) => (
              <li className="meta" key={blocker}>
                {blocker}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="dm-content-item__actions">
        <button
          type="button"
          className="ghost-button"
          disabled={!canManagePlayerWiki}
          onClick={() => void onLoadEditDraft(pageFile.page_ref)}
        >
          Edit
        </button>
        {pageFile.page.is_visible ? (
          <a
            className="ghost-button"
            href={`/app-next/campaigns/${encodedCampaignSlug}/pages/${encodedPageRef}`}
          >
            Open
          </a>
        ) : null}
        <button
          type="button"
          className="ghost-button"
          disabled={!canManagePlayerWiki || isArchiving || !pageFile.page.published}
          onClick={() => onArchive(pageFile.page_ref)}
        >
          {isArchiving ? "Archiving..." : "Unpublish/archive"}
        </button>
        {safety.can_hard_delete ? (
          <form className="dm-content-delete-form">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={deleteConfirmed}
                disabled={!canManagePlayerWiki || !safety.can_hard_delete}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  onDeleteConfirmChange(pageFile.page_ref, event.currentTarget.checked)
                }
              />
              Confirm hard delete
            </label>
            <button
              type="button"
              className="ghost-button"
              disabled={!canManagePlayerWiki || !safety.can_hard_delete || !deleteConfirmed || isDeleting}
              onClick={() => onDelete(pageFile.page_ref)}
            >
              {isDeleting ? "Deleting..." : "Delete file"}
            </button>
          </form>
        ) : null}
      </div>
      {editDraft ? (
        <form
          className="stack-form dm-content-wiki-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            onSaveEditDraft(pageFile.page_ref, editDraft);
          }}
        >
          <p className="meta">Editing publish location: {pageFile.page_ref}.md</p>
          <DmPlayerWikiDraftFields
            idPrefix={`dm-player-wiki-edit-${simpleSlug(pageFile.page_ref)}`}
            draft={editDraft}
            setDraft={(next) => onDraftChange(pageFile.page_ref, next)}
            includeSlug={false}
            disabled={!canManagePlayerWiki}
            onImageReadStatus={onImageReadStatus}
          />
          <div className="dm-content-item__actions">
            <button type="submit" disabled={!canManagePlayerWiki || isSaving}>
              {isSaving ? "Saving..." : "Save wiki page"}
            </button>
          </div>
        </form>
      ) : null}
    </article>
  );
}
