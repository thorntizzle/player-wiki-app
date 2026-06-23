import type { ChangeEvent, Dispatch, FormEvent, SetStateAction } from "react";
import type { CharacterNotesDraft } from "../characterPaneDrafts";
import { asRecord, readString } from "../characterValueUtils";

export function CharacterNotesSection({
  canEdit,
  isSaving,
  notesDraft,
  playerNotesHtml,
  referenceSections,
  setNotesDraft,
  submitNotes,
}: {
  canEdit: boolean;
  isSaving: boolean;
  notesDraft: CharacterNotesDraft;
  playerNotesHtml: string;
  referenceSections: Record<string, unknown>[];
  setNotesDraft: Dispatch<SetStateAction<CharacterNotesDraft>>;
  submitNotes: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="read-section" id="session-notes">
      <div className="section-heading">
        <h2>Notes</h2>
      </div>
      <div className="reference-stack">
        {playerNotesHtml ? (
          <article className="detail-card">
            <h3>Note</h3>
            <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: playerNotesHtml }} />
          </article>
        ) : null}
        {referenceSections.length
          ? referenceSections.map((section, sectionIndex) => {
              const sectionRecord = asRecord(section);
              return (
                <article
                  className="detail-card"
                  key={readString(sectionRecord.title, `reference-section-${sectionIndex}`)}
                >
                  <h3>{readString(sectionRecord.title)}</h3>
                  <div
                    className="article-body article-body--compact"
                    dangerouslySetInnerHTML={{ __html: readString(sectionRecord.html) }}
                  />
                </article>
              );
            })
          : null}
        {!playerNotesHtml && !referenceSections.length ? (
          <article className="detail-card">
            <p className="meta">No notes yet.</p>
          </article>
        ) : null}
      </div>
      {canEdit ? (
        <article className="detail-card session-card">
          <form className="stack-form" data-character-sheet-edit-form="notes" onSubmit={submitNotes}>
            <label className="field">
              <span>Markdown note</span>
              <textarea
                name="player_notes_markdown"
                rows={8}
                value={notesDraft.notes}
                disabled={!canEdit}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                  setNotesDraft({ ...notesDraft, notes: event.currentTarget.value })
                }
              />
            </label>
            <button type="submit" disabled={isSaving || !canEdit}>
              {isSaving ? "Saving..." : "Save note"}
            </button>
          </form>
        </article>
      ) : null}
    </section>
  );
}
