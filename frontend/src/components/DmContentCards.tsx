import type { ChangeEvent, FormEvent } from "react";

import type {
  DmContentConditionDefinition,
  DmContentConditionUpdatePayload,
  DmContentStatblock,
  DmContentStatblockUpdatePayload,
} from "../api/types";
import {
  formatInitiativeBonus,
  type DmContentConditionDraftState,
  type DmContentStatblockDraftState,
} from "../dmContentUtils";

interface DmContentStatblockCardProps {
  statblock: DmContentStatblock;
  draft: DmContentStatblockDraftState;
  canManageDmContent: boolean;
  isUpdating: boolean;
  isDeleting: boolean;
  onDraftChange: (statblock: DmContentStatblock, updates: Partial<DmContentStatblockDraftState>) => void;
  onUpdate: (id: number, payload: DmContentStatblockUpdatePayload) => void;
  onDelete: (id: number) => void;
}

export function DmContentStatblockCard({
  statblock,
  draft,
  canManageDmContent,
  isUpdating,
  isDeleting,
  onDraftChange,
  onUpdate,
  onDelete,
}: DmContentStatblockCardProps) {
  const submitUpdate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    onUpdate(statblock.id, {
      subsection: String(formData.get("subsection") || ""),
      markdown_text: String(formData.get("markdown_text") || ""),
    });
  };

  return (
    <article className="dm-content-item dm-statblock-card" id={`dm-statblock-${statblock.id}`} key={statblock.id}>
      <div className="dm-content-item__header">
        <div>
          <h3>{statblock.title}</h3>
          <p className="meta">Source file: {statblock.source_filename}</p>
        </div>
        <div className="badge-list dm-statblock-badges">
          {statblock.armor_class !== null ? <span className="meta-badge">AC {statblock.armor_class}</span> : null}
          <span className="meta-badge">HP {statblock.max_hp}</span>
          <span className="meta-badge">Speed {statblock.speed_text}</span>
          <span className="meta-badge">Init {formatInitiativeBonus(statblock.initiative_bonus)}</span>
        </div>
      </div>
      <p className="status status-neutral">{statblock.parser_feedback.summary}</p>
      <p className="meta">Combat seed source: dm_statblock:{statblock.id}.</p>
      <details className="feature-detail">
        <summary>View statblock text</summary>
        <pre className="dm-content-preview">{statblock.body_markdown}</pre>
      </details>
      {canManageDmContent ? (
        <>
          <details className="feature-detail">
            <summary>Edit statblock source</summary>
            <form className="stack-form" onSubmit={submitUpdate}>
              <label className="field">
                <span>Subsection</span>
                <input
                  id={`dm-statblock-subsection-${statblock.id}`}
                  name="subsection"
                  value={draft.subsection}
                  disabled={!canManageDmContent}
                  maxLength={80}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    onDraftChange(statblock, { subsection: event.currentTarget.value });
                  }}
                />
              </label>
              <label className="field">
                <span>Source markdown body</span>
                <textarea
                  id={`dm-statblock-markdown-${statblock.id}`}
                  name="markdown_text"
                  rows={12}
                  value={draft.markdown}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                    onDraftChange(statblock, { markdown: event.currentTarget.value });
                  }}
                />
              </label>
              <button type="submit" disabled={!canManageDmContent || isUpdating}>
                {isUpdating ? "Saving..." : "Save statblock"}
              </button>
            </form>
          </details>
          <div className="dm-content-item__actions">
            <button
              type="button"
              className="ghost-button"
              disabled={!canManageDmContent || isDeleting}
              onClick={() => onDelete(statblock.id)}
            >
              {isDeleting ? "Deleting..." : "Delete statblock"}
            </button>
          </div>
        </>
      ) : null}
    </article>
  );
}

interface DmContentConditionCardProps {
  condition: DmContentConditionDefinition;
  draft: DmContentConditionDraftState;
  canManageDmContent: boolean;
  isUpdating: boolean;
  isDeleting: boolean;
  onDraftChange: (condition: DmContentConditionDefinition, updates: Partial<DmContentConditionDraftState>) => void;
  onUpdate: (id: number, payload: DmContentConditionUpdatePayload) => void;
  onDelete: (id: number) => void;
}

export function DmContentConditionCard({
  condition,
  draft,
  canManageDmContent,
  isUpdating,
  isDeleting,
  onDraftChange,
  onUpdate,
  onDelete,
}: DmContentConditionCardProps) {
  const hasDescription = condition.description_markdown.trim().length > 0;
  const submitUpdate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const updatedName = String(formData.get("name") || "").trim();
    const description = String(formData.get("description_markdown") || "");
    onUpdate(condition.id, {
      name: updatedName || condition.name,
      description_markdown: description,
    });
  };

  return (
    <article className="dm-content-item dm-condition-card" id={`dm-condition-${condition.id}`} key={condition.id}>
      <div className="dm-content-item__header">
        <div>
          <h3>{condition.name}</h3>
        </div>
      </div>
      {hasDescription ? (
        <pre className="dm-content-preview dm-content-preview--compact">{condition.description_markdown}</pre>
      ) : (
        <p className="meta">No description saved.</p>
      )}
      {canManageDmContent ? (
        <details className="feature-detail">
          <summary>Edit condition</summary>
          <form className="stack-form" onSubmit={submitUpdate}>
            <label className="field">
              <span>Condition name</span>
              <input
                id={`dm-condition-name-${condition.id}`}
                name="name"
                value={draft.name}
                disabled={!canManageDmContent}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  onDraftChange(condition, { name: event.currentTarget.value });
                }}
              />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                id={`dm-condition-description-${condition.id}`}
                name="description_markdown"
                rows={8}
                value={draft.description}
                disabled={!canManageDmContent}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                  onDraftChange(condition, { description: event.currentTarget.value });
                }}
              />
            </label>
            <button type="submit" disabled={!canManageDmContent || isUpdating}>
              {isUpdating ? "Saving..." : "Save condition"}
            </button>
          </form>
        </details>
      ) : null}
      {canManageDmContent ? (
        <div className="dm-content-item__actions">
          <button
            type="button"
            className="ghost-button"
            disabled={!canManageDmContent || isDeleting}
            onClick={() => onDelete(condition.id)}
          >
            {isDeleting ? "Deleting..." : "Delete condition"}
          </button>
        </div>
      ) : null}
    </article>
  );
}
