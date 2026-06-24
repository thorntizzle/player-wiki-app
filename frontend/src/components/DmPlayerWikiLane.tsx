import type { ChangeEvent, Dispatch, FormEvent, SetStateAction } from "react";

import type { ContentPageFileSummary } from "../api/types";
import type { DmPlayerWikiDraftState } from "../dmContentUtils";
import { DmPlayerWikiDraftFields } from "./DmPlayerWikiDraftFields";
import { DmPlayerWikiPageCard } from "./DmPlayerWikiPageCard";

interface DmPlayerWikiLaneProps {
  canManagePlayerWiki: boolean;
  deleteConfirm: Record<string, boolean>;
  editDrafts: Record<string, DmPlayerWikiDraftState>;
  encodedCampaignSlug: string;
  filteredPlayerWikiPages: ContentPageFileSummary[];
  isArchiving: boolean;
  isDeleting: boolean;
  isLoading: boolean;
  isSaving: boolean;
  onArchive: (pageRef: string) => void;
  onCreateDraft: (draft: DmPlayerWikiDraftState) => void;
  onDelete: (pageRef: string) => void;
  onDeleteConfirmChange: (pageRef: string, checked: boolean) => void;
  onDraftChange: (pageRef: string, next: DmPlayerWikiDraftState) => void;
  onImageReadStatus: (errorMessage: string | null) => void;
  onLoadEditDraft: (pageRef: string) => void;
  onSaveEditDraft: (pageRef: string, draft: DmPlayerWikiDraftState) => void;
  playerWikiCreateDraft: DmPlayerWikiDraftState;
  playerWikiPages: ContentPageFileSummary[];
  playerWikiQuery: string;
  setPlayerWikiCreateDraft: Dispatch<SetStateAction<DmPlayerWikiDraftState>>;
  setPlayerWikiQuery: Dispatch<SetStateAction<string>>;
}

export function DmPlayerWikiLane({
  canManagePlayerWiki,
  deleteConfirm,
  editDrafts,
  encodedCampaignSlug,
  filteredPlayerWikiPages,
  isArchiving,
  isDeleting,
  isLoading,
  isSaving,
  onArchive,
  onCreateDraft,
  onDelete,
  onDeleteConfirmChange,
  onDraftChange,
  onImageReadStatus,
  onLoadEditDraft,
  onSaveEditDraft,
  playerWikiCreateDraft,
  playerWikiPages,
  playerWikiQuery,
  setPlayerWikiCreateDraft,
  setPlayerWikiQuery,
}: DmPlayerWikiLaneProps) {
  const renderPlayerWikiPageCard = (pageFile: ContentPageFileSummary) => {
    const editDraft = editDrafts[pageFile.page_ref];
    const deleteConfirmed = Boolean(deleteConfirm[pageFile.page_ref]);
    return (
      <DmPlayerWikiPageCard
        key={pageFile.page_ref}
        canManagePlayerWiki={canManagePlayerWiki}
        deleteConfirmed={deleteConfirmed}
        editDraft={editDraft}
        encodedCampaignSlug={encodedCampaignSlug}
        isArchiving={isArchiving}
        isDeleting={isDeleting}
        isSaving={isSaving}
        onArchive={onArchive}
        onDelete={onDelete}
        onDeleteConfirmChange={onDeleteConfirmChange}
        onDraftChange={onDraftChange}
        onImageReadStatus={onImageReadStatus}
        onLoadEditDraft={onLoadEditDraft}
        onSaveEditDraft={onSaveEditDraft}
        pageFile={pageFile}
      />
    );
  };

  return (
    <div className="split-grid dm-content-staged-grid">
      <section className="card dm-player-wiki-create">
        <div className="section-heading">
          <h2>Create player wiki page</h2>
        </div>
        <form
          className="stack-form dm-content-wiki-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            onCreateDraft(playerWikiCreateDraft);
          }}
        >
          <DmPlayerWikiDraftFields
            idPrefix="dm-player-wiki-create"
            draft={playerWikiCreateDraft}
            setDraft={setPlayerWikiCreateDraft}
            includeSlug={true}
            disabled={!canManagePlayerWiki}
            onImageReadStatus={onImageReadStatus}
          />
          <button type="submit" disabled={!canManagePlayerWiki || isSaving}>
            {isSaving ? "Saving..." : "Create wiki page"}
          </button>
        </form>
      </section>

      <section className="card dm-player-wiki-library">
        <div className="section-heading">
          <h2>Player wiki pages</h2>
          <p className="meta">{playerWikiPages.length} page{playerWikiPages.length === 1 ? "" : "s"}</p>
        </div>
        <form
          className="search-form dm-player-wiki-search"
          onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
        >
          <label htmlFor="dm-player-wiki-search">Search pages</label>
          <input
            id="dm-player-wiki-search"
            type="search"
            value={playerWikiQuery}
            placeholder="Title, section, path, summary"
            onChange={(event: ChangeEvent<HTMLInputElement>) => setPlayerWikiQuery(event.currentTarget.value)}
          />
        </form>
        {isLoading ? <p className="status status-neutral">Loading Player Wiki pages ...</p> : null}
        {!isLoading && filteredPlayerWikiPages.length ? (
          <div className="dm-content-list dm-player-wiki-list">
            {filteredPlayerWikiPages.map(renderPlayerWikiPageCard)}
          </div>
        ) : null}
        {!isLoading && !filteredPlayerWikiPages.length ? (
          <p className="status status-neutral">
            {playerWikiQuery ? "No Player Wiki pages matched that search." : "No Player Wiki pages have been published yet."}
          </p>
        ) : null}
      </section>
    </div>
  );
}
