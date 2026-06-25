import type { ChangeEvent, Dispatch, FormEvent, Ref, SetStateAction } from "react";
import type { CharacterPortrait } from "../api/types";
import type { CharacterPortraitDraft } from "../characterPaneDrafts";
import { CharacterPortraitManager } from "./CharacterPortraitManager";

export function CharacterPortraitSection({
  canManagePortrait,
  handlePortraitFileChange,
  portraitDraft,
  portraitFileInputRef,
  portraitMutationPending,
  removePortrait,
  selectedName,
  selectedPortrait,
  setPortraitDraft,
  submitPortrait,
}: {
  canManagePortrait: boolean;
  handlePortraitFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  portraitDraft: CharacterPortraitDraft;
  portraitFileInputRef: Ref<HTMLInputElement>;
  portraitMutationPending: boolean;
  removePortrait: () => void;
  selectedName: string;
  selectedPortrait: CharacterPortrait | null;
  setPortraitDraft: Dispatch<SetStateAction<CharacterPortraitDraft>>;
  submitPortrait: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="read-section character-portrait-section" id="character-portrait">
      <div className="section-heading">
        <h2>Portrait</h2>
      </div>
      <div className="reference-stack">
        {selectedPortrait ? (
          <article className="detail-card" id="character-portrait-current">
            <figure>
              <img className="article-image" src={selectedPortrait.url} alt={selectedPortrait.alt_text || selectedName} />
              {selectedPortrait.caption ? (
                <figcaption className="meta article-image__caption">{selectedPortrait.caption}</figcaption>
              ) : null}
            </figure>
          </article>
        ) : (
          <article className="detail-card character-empty-state">
            <p className="meta">No portrait yet.</p>
          </article>
        )}
        {canManagePortrait ? (
          <article className="detail-card session-card" id="character-portrait-manager">
            <CharacterPortraitManager
              handlePortraitFileChange={handlePortraitFileChange}
              portraitDraft={portraitDraft}
              portraitFileInputRef={portraitFileInputRef}
              portraitMutationPending={portraitMutationPending}
              removePortrait={removePortrait}
              selectedPortrait={selectedPortrait}
              setPortraitDraft={setPortraitDraft}
              submitPortrait={submitPortrait}
            />
          </article>
        ) : null}
      </div>
    </section>
  );
}
