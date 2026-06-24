import type { ChangeEvent } from "react";

import {
  PLAYER_WIKI_SECTION_CHOICES,
  buildPageRefFromDraft,
  sectionChoiceForLabel,
  type DmPlayerWikiDraftState,
} from "../dmContentUtils";
import { readBinaryAsBase64 } from "../sessionArticleDrafts";

interface DmPlayerWikiDraftFieldsProps {
  idPrefix: string;
  draft: DmPlayerWikiDraftState;
  setDraft: (next: DmPlayerWikiDraftState) => void;
  includeSlug: boolean;
  disabled: boolean;
  onImageReadStatus: (errorMessage: string | null) => void;
}

export function DmPlayerWikiDraftFields({
  idPrefix,
  draft,
  setDraft,
  includeSlug,
  disabled,
  onImageReadStatus,
}: DmPlayerWikiDraftFieldsProps) {
  const updateDraft = (updates: Partial<DmPlayerWikiDraftState>) => setDraft({ ...draft, ...updates });
  const targetPageRef = buildPageRefFromDraft(draft);

  return (
    <>
      <label htmlFor={`${idPrefix}-title`} className="field">
        <span>Title</span>
        <input
          id={`${idPrefix}-title`}
          name="title"
          maxLength={200}
          value={draft.title}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
        />
      </label>
      {includeSlug ? (
        <>
          <label htmlFor={`${idPrefix}-slug`} className="field">
            <span>Slug</span>
            <input
              id={`${idPrefix}-slug`}
              name="slug_leaf"
              maxLength={120}
              value={draft.slugLeaf}
              placeholder="field-report"
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
            />
          </label>
          <p className="meta">Page file: {targetPageRef}.md</p>
        </>
      ) : null}
      <label htmlFor={`${idPrefix}-section`} className="field">
        <span>Section</span>
        <select
          id={`${idPrefix}-section`}
          name="section"
          value={draft.section}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => {
            const section = event.currentTarget.value;
            const currentDefaultType = sectionChoiceForLabel(draft.section).defaultType;
            const nextDefaultType = sectionChoiceForLabel(section).defaultType;
            updateDraft({
              section,
              pageType: draft.pageType && draft.pageType !== currentDefaultType ? draft.pageType : nextDefaultType,
            });
          }}
        >
          {PLAYER_WIKI_SECTION_CHOICES.map((choice) => (
            <option key={choice.label} value={choice.label}>
              {choice.label}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor={`${idPrefix}-type`} className="field">
        <span>Page type</span>
        <input
          id={`${idPrefix}-type`}
          name="page_type"
          maxLength={80}
          value={draft.pageType}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ pageType: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-subsection`} className="field">
        <span>Subsection</span>
        <input
          id={`${idPrefix}-subsection`}
          name="subsection"
          maxLength={120}
          value={draft.subsection}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ subsection: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-summary`} className="field">
        <span>Summary</span>
        <textarea
          id={`${idPrefix}-summary`}
          name="summary"
          rows={3}
          maxLength={400}
          value={draft.summary}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ summary: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-aliases`} className="field">
        <span>Aliases</span>
        <textarea
          id={`${idPrefix}-aliases`}
          name="aliases"
          rows={3}
          value={draft.aliases}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ aliases: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-reveal-after-session`} className="field">
        <span>Reveal after session</span>
        <input
          id={`${idPrefix}-reveal-after-session`}
          name="reveal_after_session"
          type="number"
          min={0}
          value={draft.revealAfterSession}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ revealAfterSession: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-display-order`} className="field">
        <span>Display order</span>
        <input
          id={`${idPrefix}-display-order`}
          name="display_order"
          type="number"
          min={0}
          value={draft.displayOrder}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ displayOrder: event.currentTarget.value })}
        />
      </label>
      <label className="checkbox-label">
        <input
          type="checkbox"
          name="published"
          checked={draft.published}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ published: event.currentTarget.checked })}
        />
        Published
      </label>
      <label htmlFor={`${idPrefix}-source-ref`} className="field">
        <span>Source reference</span>
        <input
          id={`${idPrefix}-source-ref`}
          name="source_ref"
          value={draft.sourceRef}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ sourceRef: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-image`} className="field">
        <span>Image path</span>
        <input
          id={`${idPrefix}-image`}
          name="image"
          value={draft.image}
          placeholder="npcs/example.webp"
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ image: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-image-upload`} className="field">
        <span>Upload image</span>
        <input
          id={`${idPrefix}-image-upload`}
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const file = event.currentTarget.files?.item(0);
            if (!file) {
              updateDraft({ imageUpload: null });
              return;
            }
            readBinaryAsBase64(file, (payload) => {
              if (!payload) {
                onImageReadStatus("Unable to read that image file.");
                return;
              }
              onImageReadStatus(null);
              updateDraft({ imageUpload: payload });
            });
          }}
        />
      </label>
      {draft.imageUpload ? <p className="status status-neutral">Selected image: {draft.imageUpload.filename}</p> : null}
      <label htmlFor={`${idPrefix}-image-alt`} className="field">
        <span>Image alt text</span>
        <input
          id={`${idPrefix}-image-alt`}
          name="image_alt"
          value={draft.imageAlt}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageAlt: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-image-caption`} className="field">
        <span>Image caption</span>
        <input
          id={`${idPrefix}-image-caption`}
          name="image_caption"
          value={draft.imageCaption}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageCaption: event.currentTarget.value })}
        />
      </label>
      <label htmlFor={`${idPrefix}-body`} className="field">
        <span>Markdown body</span>
        <textarea
          id={`${idPrefix}-body`}
          name="body_markdown"
          rows={18}
          value={draft.bodyMarkdown}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
        />
      </label>
    </>
  );
}
