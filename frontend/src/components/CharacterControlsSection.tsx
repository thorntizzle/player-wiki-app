import { useState, type Dispatch, type FormEvent, type SetStateAction } from "react";
import type { CharacterControls } from "../api/types";
import type { CharacterControlsDraft } from "../characterPaneDrafts";

export function CharacterControlsSection({
  characterName,
  characterSlug,
  clearCharacterAssignment,
  controls,
  controlsDraft,
  controlsMutationPending,
  isAssigningOwner,
  isClearingOwner,
  isDeletingCharacter,
  setControlsDraft,
  submitCharacterAssignment,
  submitCharacterDelete,
}: {
  characterName: string;
  characterSlug: string;
  clearCharacterAssignment: () => void;
  controls: CharacterControls;
  controlsDraft: CharacterControlsDraft;
  controlsMutationPending: boolean;
  isAssigningOwner: boolean;
  isClearingOwner: boolean;
  isDeletingCharacter: boolean;
  setControlsDraft: Dispatch<SetStateAction<CharacterControlsDraft>>;
  submitCharacterAssignment: (event: FormEvent<HTMLFormElement>) => void;
  submitCharacterDelete: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const [clearAssignmentConfirmed, setClearAssignmentConfirmed] = useState(false);

  return (
    <section className="read-section character-controls-panel">
      <div className="section-heading">
        <h2>Controls</h2>
      </div>
      <div className="detail-grid character-controls-grid">
        <article className="detail-card">
          <h3>Player controls</h3>
          {controls.current_user_is_owner ? (
            <p>Player-controls workspace for {characterName}.</p>
          ) : (
            <p>Character management controls for campaign staff.</p>
          )}
        </article>
        <article className="detail-card">
          <h3>Current owner</h3>
          {controls.assignment ? (
            <>
              <p>
                <strong>{controls.assignment.display_name}</strong>
                {controls.assignment.email ? <span className="meta"> | {controls.assignment.email}</span> : null}
              </p>
              <p className="meta">
                Assignment: {controls.assignment.assignment_type
                  ? `${controls.assignment.assignment_type.charAt(0).toUpperCase()}${controls.assignment.assignment_type.slice(1)}`
                  : "Owner"}
              </p>
              {controls.assignment.admin_href ? (
                <a className="ghost-button" href={controls.assignment.admin_href}>
                  Open user record
                </a>
              ) : null}
            </>
          ) : (
            <p className="meta">No player owner assigned yet.</p>
          )}
        </article>
      </div>

      {controls.can_assign_owner ? (
        <div className="detail-grid character-controls-grid">
          <article className="detail-card character-controls-manager">
            <h3>Assignment controls</h3>
            <p className="meta">Assignments require an active player membership in this campaign.</p>
            {controls.player_choices.length ? (
              <form onSubmit={submitCharacterAssignment} className="stack-form">
                <label className="field">
                  <span>Assign owner</span>
                  <select
                    id="character-owner-assignment"
                    value={controlsDraft.assignedUserId}
                    disabled={controlsMutationPending}
                    required
                    onChange={(event) =>
                      setControlsDraft({ ...controlsDraft, assignedUserId: event.currentTarget.value })
                    }
                  >
                    <option value="">Choose a player</option>
                    {controls.player_choices.map((choice) => (
                      <option key={choice.user_id} value={String(choice.user_id)}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="submit" disabled={controlsMutationPending || !controlsDraft.assignedUserId}>
                  {isAssigningOwner ? "Saving..." : "Save assignment"}
                </button>
              </form>
            ) : (
              <p className="meta">No active player memberships are available for assignment in this campaign.</p>
            )}
            {controls.assignment ? (
              <form
                className="confirmed-action"
                onSubmit={(event) => {
                  event.preventDefault();
                  clearCharacterAssignment();
                  setClearAssignmentConfirmed(false);
                }}
              >
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={clearAssignmentConfirmed}
                    disabled={controlsMutationPending}
                    onChange={(event) => setClearAssignmentConfirmed(event.currentTarget.checked)}
                  />
                  Confirm clear
                </label>
                <button type="submit" className="ghost-button" disabled={controlsMutationPending || !clearAssignmentConfirmed}>
                  {isClearingOwner ? "Clearing..." : "Clear assignment"}
                </button>
              </form>
            ) : null}
          </article>
        </div>
      ) : null}

      {controls.can_delete_character ? (
        <div className="detail-grid character-controls-grid">
          <article className="detail-card character-controls-card--danger">
            <h3>Delete character</h3>
            <p>
              Deleting a character removes the file-backed definition/import metadata, the live character state, and any
              current player assignment.
            </p>
            <form onSubmit={submitCharacterDelete} className="stack-form character-delete-form">
              <label className="field">
                <span>
                  Type this character's URL name to confirm: <code>{characterSlug}</code>
                </span>
                <input
                  id="character-delete-confirmation"
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={controlsDraft.deleteConfirmation}
                  disabled={controlsMutationPending}
                  onChange={(event) =>
                    setControlsDraft({ ...controlsDraft, deleteConfirmation: event.currentTarget.value })
                  }
                />
              </label>
              <button
                type="submit"
                className="button-danger"
                disabled={controlsMutationPending || controlsDraft.deleteConfirmation.trim() !== characterSlug}
              >
                {isDeletingCharacter ? "Deleting..." : "Delete character"}
              </button>
            </form>
          </article>
        </div>
      ) : null}
    </section>
  );
}
