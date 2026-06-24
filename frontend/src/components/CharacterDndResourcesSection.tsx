import type { Dispatch, FocusEvent, FormEvent, SetStateAction } from "react";
import { readNumber, readString } from "../characterValueUtils";

export function CharacterDndResourcesSection({
  canEdit,
  isSaving,
  resourceDrafts,
  resources,
  setResourceDrafts,
  submitResource,
  submitResourceOnBlur,
}: {
  canEdit: boolean;
  isSaving: boolean;
  resourceDrafts: Record<string, string>;
  resources: Record<string, unknown>[];
  setResourceDrafts: Dispatch<SetStateAction<Record<string, string>>>;
  submitResource: (event: FormEvent<HTMLFormElement>, resourceId: string) => void;
  submitResourceOnBlur: (event: FocusEvent<HTMLInputElement>) => void;
}) {
  return (
    <section className="read-section" id="session-resources">
      <div className="section-heading">
        <h2>Resources</h2>
      </div>
      {resources.length ? (
        <div className={`resource-grid resource-grid--compact${canEdit ? " resource-grid--editable" : ""}`}>
          {resources.map((resource) => {
            const id = readString(resource.id);
            const resourceLabel = readString(resource.label, id || "Resource");
            const resetLabel = readString(resource["reset_label"] || resource["resetLabel"] || resource["reset_on"]);
            return (
              <article
                className={`resource-card${canEdit && id ? " session-resource-card session-resource-card--compact" : ""}`}
                key={id || resourceLabel}
              >
                <h4>{resourceLabel}</h4>
                <p className="resource-card__value">
                  {readNumber(resource.current)} / {readNumber(resource.max)}
                </p>
                {resetLabel ? <p className="meta">{resetLabel}</p> : null}
                {resource.notes ? <p className="meta">{readString(resource.notes)}</p> : null}
                {canEdit && id ? (
                  <form
                    className="session-inline-form session-inline-form--compact-resource"
                    onSubmit={(event) => submitResource(event, id)}
                    data-character-autosubmit
                    data-character-sheet-edit-form="resource"
                    data-character-sheet-edit-row-id={id}
                  >
                    <label className="session-field" htmlFor={`resource-${id}`}>
                      <span>Current</span>
                      <input
                        id={`resource-${id}`}
                        type="number"
                        min="0"
                        value={resourceDrafts[id] ?? ""}
                        onChange={(event) =>
                          setResourceDrafts({ ...resourceDrafts, [id]: event.currentTarget.value })
                        }
                        onBlur={submitResourceOnBlur}
                      />
                    </label>
                    <button type="submit" className="visually-hidden" disabled={isSaving || !canEdit}>
                      Update {resourceLabel}
                    </button>
                  </form>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <article className="detail-card character-empty-state">
          <p className="meta">No tracked resources.</p>
        </article>
      )}
    </section>
  );
}
