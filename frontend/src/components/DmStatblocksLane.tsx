import type { ChangeEvent, Dispatch, FormEvent, SetStateAction } from "react";

import type {
  DmContentStatblock,
  DmContentStatblockCreatePayload,
  DmContentStatblockUpdatePayload,
} from "../api/types";
import {
  buildInitialStatblockDraft,
  type DmContentStatblockDraftState,
} from "../dmContentUtils";
import { readTextFile } from "../sessionArticleDrafts";
import { DmContentStatblockCard } from "./DmContentCards";

interface DmStatblockSubsectionGroup {
  name: string;
  statblocks: DmContentStatblock[];
}

interface DmStatblocksLaneProps {
  canManageDmContent: boolean;
  filteredStatblocks: DmContentStatblock[];
  isCreating: boolean;
  isDeleting: boolean;
  isLoading: boolean;
  isUpdating: boolean;
  onCreate: (payload: DmContentStatblockCreatePayload) => void;
  onDelete: (id: number) => void;
  onDraftChange: (statblock: DmContentStatblock, updates: Partial<DmContentStatblockDraftState>) => void;
  onFileReadStatus: (errorMessage: string | null) => void;
  onUpdate: (id: number, payload: DmContentStatblockUpdatePayload) => void;
  setStatblockCreateDraft: Dispatch<SetStateAction<DmContentStatblockDraftState>>;
  setStatblockQuery: Dispatch<SetStateAction<string>>;
  statblockCreateDraft: DmContentStatblockDraftState;
  statblockDrafts: Record<number, DmContentStatblockDraftState>;
  statblockQuery: string;
  statblockSubsectionGroups: DmStatblockSubsectionGroup[];
  topLevelStatblocks: DmContentStatblock[];
}

export function DmStatblocksLane({
  canManageDmContent,
  filteredStatblocks,
  isCreating,
  isDeleting,
  isLoading,
  isUpdating,
  onCreate,
  onDelete,
  onDraftChange,
  onFileReadStatus,
  onUpdate,
  setStatblockCreateDraft,
  setStatblockQuery,
  statblockCreateDraft,
  statblockDrafts,
  statblockQuery,
  statblockSubsectionGroups,
  topLevelStatblocks,
}: DmStatblocksLaneProps) {
  const renderStatblockCard = (statblock: DmContentStatblock) => {
    const draft = statblockDrafts[statblock.id] ?? buildInitialStatblockDraft(statblock);
    return (
      <DmContentStatblockCard
        key={statblock.id}
        statblock={statblock}
        draft={draft}
        canManageDmContent={canManageDmContent}
        isUpdating={isUpdating}
        isDeleting={isDeleting}
        onDraftChange={onDraftChange}
        onUpdate={onUpdate}
        onDelete={onDelete}
      />
    );
  };

  return (
    <div className="split-grid dm-content-staged-grid">
      <section className="card dm-statblock-create">
        <div className="section-heading">
          <h2>Create statblock</h2>
        </div>
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            onCreate({
              filename: String(formData.get("filename") || "gen2-statblock.md").trim() || "gen2-statblock.md",
              subsection: String(formData.get("subsection") || ""),
              markdown_text: String(formData.get("markdown_text") || ""),
            });
          }}
        >
          <label className="field">
            <span>Import markdown file</span>
            <input
              id="dm-statblock-create-file-import"
              type="file"
              accept=".md,.markdown,text/markdown,text/plain"
              disabled={!canManageDmContent}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const file = event.currentTarget.files?.item(0);
                if (!file) {
                  return;
                }
                readTextFile(file, (payload) => {
                  if (!payload) {
                    onFileReadStatus("Unable to read that markdown file.");
                    return;
                  }
                  onFileReadStatus(null);
                  setStatblockCreateDraft((current) => ({
                    ...current,
                    filename: payload.filename,
                    markdown: payload.text,
                  }));
                });
              }}
            />
          </label>
          <label className="field">
            <span>Source filename</span>
            <input
              id="dm-statblock-create-filename"
              name="filename"
              value={statblockCreateDraft.filename}
              disabled={!canManageDmContent}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const filename = event.currentTarget.value;
                setStatblockCreateDraft((current) => ({
                  ...current,
                  filename,
                }));
              }}
            />
          </label>
          <label className="field">
            <span>Subsection</span>
            <input
              id="dm-statblock-create-subsection"
              name="subsection"
              maxLength={80}
              value={statblockCreateDraft.subsection}
              disabled={!canManageDmContent}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const subsection = event.currentTarget.value;
                setStatblockCreateDraft((current) => ({
                  ...current,
                  subsection,
                }));
              }}
            />
          </label>
          <label className="field">
            <span>Source markdown body</span>
            <textarea
              id="dm-statblock-create-markdown"
              name="markdown_text"
              rows={16}
              value={statblockCreateDraft.markdown}
              disabled={!canManageDmContent}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                const markdown = event.currentTarget.value;
                setStatblockCreateDraft((current) => ({
                  ...current,
                  markdown,
                }));
              }}
            />
          </label>
          <button type="submit" disabled={!canManageDmContent || isCreating}>
            {isCreating ? "Saving..." : "Save statblock"}
          </button>
        </form>
      </section>

      <section className="card dm-statblock-library">
        <div className="section-heading">
          <div>
            <h2>Statblock library</h2>
            <p className="meta">Uploaded here for DM-side encounter prep. Campaigns can pull these directly into Combat.</p>
          </div>
        </div>
        <form
          className="search-form dm-statblock-search"
          onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
        >
          <label htmlFor="dm-statblock-search">Search statblocks</label>
          <input
            id="dm-statblock-search"
            type="search"
            value={statblockQuery}
            placeholder="Title, subsection, source, text"
            onChange={(event: ChangeEvent<HTMLInputElement>) => setStatblockQuery(event.currentTarget.value)}
          />
        </form>
        {isLoading ? <p className="status status-neutral">Loading statblocks ...</p> : null}
        {!isLoading && filteredStatblocks.length ? (
          <div className="dm-content-list dm-statblock-groups">
            {topLevelStatblocks.map(renderStatblockCard)}
            {statblockSubsectionGroups.map((group) => (
              <details className="section-block section-block--collapsible" key={group.name} open>
                <summary className="section-toggle-summary">
                  <span className="section-toggle-summary__content">
                    <span className="section-title">{group.name}</span>
                    <span className="meta">{group.statblocks.length} statblock{group.statblocks.length === 1 ? "" : "s"}</span>
                  </span>
                  <span className="section-toggle-chevron" aria-hidden="true" />
                </summary>
                <div className="section-block__body">
                  <div className="dm-content-list">
                    {group.statblocks.map(renderStatblockCard)}
                  </div>
                </div>
              </details>
            ))}
          </div>
        ) : null}
        {!isLoading && !filteredStatblocks.length ? (
          <p className="status status-neutral">
            {statblockQuery ? "No statblocks matched that search." : "No DM statblocks have been uploaded yet."}
          </p>
        ) : null}
      </section>
    </div>
  );
}
