import type { ChangeEvent, Dispatch, FormEvent, SetStateAction } from "react";

import type {
  DmContentConditionCreatePayload,
  DmContentConditionDefinition,
  DmContentConditionUpdatePayload,
} from "../api/types";
import {
  buildInitialConditionDraft,
  type DmContentConditionDraftState,
} from "../dmContentUtils";
import { DmContentConditionCard } from "./DmContentCards";

interface DmConditionsLaneProps {
  canManageDmContent: boolean;
  conditionCreateDraft: DmContentConditionDraftState;
  conditionDrafts: Record<number, DmContentConditionDraftState>;
  conditionQuery: string;
  filteredConditions: DmContentConditionDefinition[];
  isCreating: boolean;
  isDeleting: boolean;
  isLoading: boolean;
  isUpdating: boolean;
  onCreate: (payload: DmContentConditionCreatePayload) => void;
  onDelete: (id: number) => void;
  onDraftChange: (condition: DmContentConditionDefinition, updates: Partial<DmContentConditionDraftState>) => void;
  onUpdate: (id: number, payload: DmContentConditionUpdatePayload) => void;
  onValidationError: (message: string) => void;
  setConditionCreateDraft: Dispatch<SetStateAction<DmContentConditionDraftState>>;
  setConditionQuery: Dispatch<SetStateAction<string>>;
}

export function DmConditionsLane({
  canManageDmContent,
  conditionCreateDraft,
  conditionDrafts,
  conditionQuery,
  filteredConditions,
  isCreating,
  isDeleting,
  isLoading,
  isUpdating,
  onCreate,
  onDelete,
  onDraftChange,
  onUpdate,
  onValidationError,
  setConditionCreateDraft,
  setConditionQuery,
}: DmConditionsLaneProps) {
  const renderConditionCard = (condition: DmContentConditionDefinition) => {
    const draft = conditionDrafts[condition.id] ?? buildInitialConditionDraft(condition);
    return (
      <DmContentConditionCard
        key={condition.id}
        condition={condition}
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
      <section className="card dm-condition-create">
        <div className="section-heading">
          <h2>Create condition</h2>
        </div>
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            const name = String(formData.get("name") || "").trim();
            const description = String(formData.get("description_markdown") || "");
            if (!name) {
              onValidationError("Condition name is required.");
              return;
            }
            onCreate({
              name,
              description_markdown: description,
            });
          }}
        >
          <label className="field">
            <span>Condition name</span>
            <input
              id="dm-condition-create-name"
              name="name"
              value={conditionCreateDraft.name}
              disabled={!canManageDmContent}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const name = event.currentTarget.value;
                setConditionCreateDraft((current) => ({
                  ...current,
                  name,
                }));
              }}
            />
          </label>
          <label className="field">
            <span>Description</span>
            <textarea
              id="dm-condition-create-description"
              name="description_markdown"
              rows={10}
              value={conditionCreateDraft.description}
              disabled={!canManageDmContent}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                const description = event.currentTarget.value;
                setConditionCreateDraft((current) => ({
                  ...current,
                  description,
                }));
              }}
            />
          </label>
          <button type="submit" disabled={!canManageDmContent || isCreating}>
            {isCreating ? "Saving..." : "Save condition"}
          </button>
        </form>
      </section>

      <section className="card dm-condition-library">
        <div className="section-heading">
          <div>
            <h2>Custom conditions</h2>
            <p className="meta">These names appear in the combat condition picker alongside the standard DND-5E condition list.</p>
          </div>
        </div>
        <form
          className="search-form dm-condition-search"
          onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
        >
          <label htmlFor="dm-condition-search">Search conditions</label>
          <input
            id="dm-condition-search"
            type="search"
            value={conditionQuery}
            placeholder="Name or description"
            onChange={(event: ChangeEvent<HTMLInputElement>) => setConditionQuery(event.currentTarget.value)}
          />
        </form>
        {isLoading ? <p className="status status-neutral">Loading conditions ...</p> : null}
        {!isLoading && filteredConditions.length ? (
          <div className="dm-content-list dm-condition-list">
            {filteredConditions.map(renderConditionCard)}
          </div>
        ) : null}
        {!isLoading && !filteredConditions.length ? (
          <p className="status status-neutral">
            {conditionQuery ? "No conditions matched that search." : "No custom conditions have been created yet."}
          </p>
        ) : null}
      </section>
    </div>
  );
}
