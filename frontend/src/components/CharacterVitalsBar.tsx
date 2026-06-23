import type { ChangeEvent, Dispatch, FormEvent, SetStateAction } from "react";
import type { CharacterRestPreviewResponse } from "../api/types";
import {
  xianxiaVitalsFields,
  type CharacterVitalsDraft,
  type CharacterXianxiaVitalsDraft,
} from "../characterPaneDrafts";

type RestType = "short" | "long";

export function CharacterVitalsBar({
  canEdit,
  isRestApplying,
  isRestPreviewLoading,
  isVitalsSaving,
  isXianxia,
  maxHp,
  onApplyRest,
  onClearRestPreview,
  onPreviewRest,
  restPreview,
  setVitalsDraft,
  setXianxiaVitalsDraft,
  submitVitals,
  submitXianxiaVitals,
  surfaceMetaLabel,
  vitalsDraft,
  xianxiaVitalsDraft,
}: {
  canEdit: boolean;
  isRestApplying: boolean;
  isRestPreviewLoading: boolean;
  isVitalsSaving: boolean;
  isXianxia: boolean;
  maxHp: number;
  onApplyRest: (restType: RestType) => void;
  onClearRestPreview: () => void;
  onPreviewRest: (restType: RestType) => void;
  restPreview: CharacterRestPreviewResponse["preview"] | null;
  setVitalsDraft: Dispatch<SetStateAction<CharacterVitalsDraft>>;
  setXianxiaVitalsDraft: Dispatch<SetStateAction<CharacterXianxiaVitalsDraft>>;
  submitVitals: (event: FormEvent<HTMLFormElement>) => void;
  submitXianxiaVitals: (event: FormEvent<HTMLFormElement>) => void;
  surfaceMetaLabel: string;
  vitalsDraft: CharacterVitalsDraft;
  xianxiaVitalsDraft: CharacterXianxiaVitalsDraft;
}) {
  return (
    <section className="session-bar session-bar--compact" id="session-vitals">
      <div className="session-bar__summary">
        <p className="eyebrow">{surfaceMetaLabel}</p>
        <h2>Vitals</h2>
      </div>
      <div className="session-bar__actions" id="session-rest">
        <button
          type="button"
          className="ghost-button"
          disabled={isRestPreviewLoading || !canEdit}
          onClick={() => onPreviewRest("short")}
        >
          Short rest
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={isRestPreviewLoading || !canEdit}
          onClick={() => onPreviewRest("long")}
        >
          Long rest
        </button>
      </div>
      {isXianxia ? (
        <form onSubmit={submitXianxiaVitals} className="session-vitals-form session-vitals-form--compact">
          {xianxiaVitalsFields.map((field) => (
            <div className="session-vitals-form__group" key={field.key}>
              <label htmlFor={`xianxia-${field.key}`} className="session-field">
                <span>{field.label}</span>
                <input
                  id={`xianxia-${field.key}`}
                  type="number"
                  value={xianxiaVitalsDraft[field.key]}
                  disabled={!canEdit}
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setXianxiaVitalsDraft({
                      ...xianxiaVitalsDraft,
                      [field.key]: event.currentTarget.value,
                    })
                  }
                />
              </label>
            </div>
          ))}
          <button type="submit" disabled={isVitalsSaving || !canEdit}>
            {isVitalsSaving ? "Saving..." : "Save Xianxia pools"}
          </button>
        </form>
      ) : (
        <form onSubmit={submitVitals} className="session-vitals-form session-vitals-form--compact">
          <div className="session-vitals-form__group">
            <label htmlFor="character-current-hp" className="session-field">
              <span>Current HP</span>
              <div className="session-number-inline">
                <input
                  id="character-current-hp"
                  type="number"
                  value={vitalsDraft.currentHp}
                  disabled={!canEdit}
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })
                  }
                />
                <span> / {maxHp}</span>
              </div>
            </label>
          </div>
          <div className="session-vitals-form__group">
            <label htmlFor="character-temp-hp" className="session-field">
              <span>Temp HP</span>
              <input
                id="character-temp-hp"
                type="number"
                value={vitalsDraft.tempHp}
                disabled={!canEdit}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })
                }
              />
            </label>
          </div>
          <button type="submit" disabled={isVitalsSaving || !canEdit}>
            {isVitalsSaving ? "Saving..." : "Save vitals"}
          </button>
        </form>
      )}
      {restPreview ? (
        <section className="card session-card">
          <div className="section-heading">
            <h2>{restPreview.label} confirmation</h2>
          </div>
          <ul className="plain-list rest-preview-list">
            {restPreview.changes.length ? (
              restPreview.changes.map((change) => (
                <li key={`${change.label}-${change.from_value}-${change.to_value}`}>
                  <strong>{change.label}</strong>: <span>{change.from_value} {"->"} {change.to_value}</span>
                </li>
              ))
            ) : (
              <li>No modeled state changes will be applied by this {restPreview.label.toLowerCase()}.</li>
            )}
          </ul>
          <div className="hero-actions">
            <button
              type="button"
              className="ghost-button"
              disabled={isRestApplying || !canEdit}
              onClick={() => onApplyRest(restPreview.rest_type === "short" ? "short" : "long")}
            >
              {isRestApplying ? "Applying..." : "Apply"}
            </button>
            <button type="button" className="ghost-button" onClick={onClearRestPreview} disabled={isRestApplying}>
              Cancel
            </button>
          </div>
        </section>
      ) : null}
    </section>
  );
}
