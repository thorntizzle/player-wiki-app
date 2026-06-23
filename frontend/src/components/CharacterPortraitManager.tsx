import type { ChangeEvent, Dispatch, FormEvent, Ref, SetStateAction } from "react";
import type { CharacterPortrait } from "../api/types";
import type { CharacterPortraitDraft } from "../characterPaneDrafts";

export function CharacterPortraitManager({
  handlePortraitFileChange,
  portraitDraft,
  portraitFileInputRef,
  portraitMutationPending,
  removePortrait,
  selectedPortrait,
  setPortraitDraft,
  submitPortrait,
}: {
  handlePortraitFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  portraitDraft: CharacterPortraitDraft;
  portraitFileInputRef: Ref<HTMLInputElement>;
  portraitMutationPending: boolean;
  removePortrait: () => void;
  selectedPortrait: CharacterPortrait | null;
  setPortraitDraft: Dispatch<SetStateAction<CharacterPortraitDraft>>;
  submitPortrait: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="stack-form character-portrait-manager" onSubmit={submitPortrait}>
      <label className="field" htmlFor="character-portrait-file">
        <span>Portrait image</span>
        <input
          id="character-portrait-file"
          ref={portraitFileInputRef}
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
          disabled={portraitMutationPending}
          onChange={handlePortraitFileChange}
        />
      </label>
      <label className="field" htmlFor="character-portrait-alt">
        <span>Alt text</span>
        <input
          id="character-portrait-alt"
          type="text"
          maxLength={200}
          value={portraitDraft.altText}
          disabled={portraitMutationPending}
          onChange={(event) => setPortraitDraft((current) => ({ ...current, altText: event.currentTarget.value }))}
        />
      </label>
      <label className="field" htmlFor="character-portrait-caption">
        <span>Caption</span>
        <input
          id="character-portrait-caption"
          type="text"
          maxLength={300}
          value={portraitDraft.caption}
          disabled={portraitMutationPending}
          onChange={(event) => setPortraitDraft((current) => ({ ...current, caption: event.currentTarget.value }))}
        />
      </label>
      <div className="hero-actions character-portrait-manager__actions">
        <button className="button" type="submit" disabled={portraitMutationPending || !portraitDraft.file}>
          Save portrait
        </button>
        {selectedPortrait ? (
          <button type="button" className="ghost-button" disabled={portraitMutationPending} onClick={removePortrait}>
            Remove portrait
          </button>
        ) : null}
        {portraitDraft.fileName ? <span className="meta">{portraitDraft.fileName}</span> : null}
      </div>
    </form>
  );
}
