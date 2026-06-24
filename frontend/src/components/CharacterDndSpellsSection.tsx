import type { Dispatch, FocusEvent, FormEvent, SetStateAction } from "react";
import type { CharacterPresentedSpell } from "../api/types";
import { readNumber, readString } from "../characterValueUtils";
import {
  draftKey,
  presentedSpellCardDetailLine,
  rawSpellCardDetailLine,
} from "../characterPaneUtils";

type SpellGroup<T> = {
  key: string;
  label: string;
  spells: T[];
};

export function CharacterDndSpellsSection({
  canEdit,
  isSaving,
  openSpellDetail,
  presentedSpellGroups,
  presentedSpells,
  rawSpellGroups,
  spellcasting,
  spells,
  spellSlotDrafts,
  spellSlots,
  setSpellSlotDrafts,
  submitSpellSlot,
  submitSpellSlotOnBlur,
}: {
  canEdit: boolean;
  isSaving: boolean;
  openSpellDetail: (spell: CharacterPresentedSpell) => void;
  presentedSpellGroups: SpellGroup<CharacterPresentedSpell>[];
  presentedSpells: CharacterPresentedSpell[];
  rawSpellGroups: SpellGroup<Record<string, unknown>>[];
  spellcasting: Record<string, unknown>;
  spells: Record<string, unknown>[];
  spellSlotDrafts: Record<string, string>;
  spellSlots: Record<string, unknown>[];
  setSpellSlotDrafts: Dispatch<SetStateAction<Record<string, string>>>;
  submitSpellSlot: (event: FormEvent<HTMLFormElement>, slot: Record<string, unknown>) => void;
  submitSpellSlotOnBlur: (event: FocusEvent<HTMLInputElement>) => void;
}) {
  return (
    <section className="read-section" id="session-spell-slots">
      <div className="section-heading">
        <h2>Spells</h2>
      </div>
      <div className="detail-grid spellcasting-summary-grid">
        <article className="detail-card spellcasting-class-card">
          <h3>Spellcasting</h3>
          <div className="spellcasting-summary-values" role="group" aria-label="Spellcasting values">
            <span className="spellcasting-summary-value">
              <span>Ability</span>
              <strong>{String(spellcasting.spellcasting_ability ?? "--")}</strong>
            </span>
            <span className="spellcasting-summary-value">
              <span>Save DC</span>
              <strong>{String(spellcasting.spell_save_dc ?? "--")}</strong>
            </span>
            <span className="spellcasting-summary-value">
              <span>Attack</span>
              <strong>{String(spellcasting.spell_attack_bonus ?? "--")}</strong>
            </span>
          </div>
        </article>
      </div>
      {spellSlots.length ? (
        <div className="spell-slot-editor-list spell-slot-editor-list--compact">
          {spellSlots.map((slot) => {
            const level = readNumber(slot.level);
            const slotLaneId = readString(slot.slot_lane_id);
            const key = draftKey(level, slotLaneId);
            const used = readNumber(slot.used);
            const max = readNumber(slot.max);
            const available = readNumber(slot.available, Math.max(0, max - used));
            const slotLabel = readString(slot.label, `Level ${level}`);
            return (
              <article className="detail-card" key={key}>
                {canEdit ? (
                  <form
                    onSubmit={(event) => submitSpellSlot(event, slot)}
                    className="session-inline-form"
                    data-character-sheet-edit-form="spell-slot"
                    data-character-sheet-edit-level={level}
                    data-character-sheet-edit-slot-lane-id={slotLaneId}
                    data-character-autosubmit
                  >
                    <div className="section-heading">
                      <h3>{slotLabel}</h3>
                      <span className="meta">
                        {available} available / {max}
                      </span>
                    </div>
                    <label className="session-field" htmlFor={`spell-slot-${key}`}>
                      <span>Used</span>
                      <input
                        id={`spell-slot-${key}`}
                        type="number"
                        min="0"
                        max={max}
                        value={spellSlotDrafts[key] ?? ""}
                        onChange={(event) =>
                          setSpellSlotDrafts({ ...spellSlotDrafts, [key]: event.currentTarget.value })
                        }
                        onBlur={submitSpellSlotOnBlur}
                      />
                    </label>
                    <button type="submit" className="visually-hidden" disabled={isSaving || !canEdit}>
                      Update {slotLabel}
                    </button>
                  </form>
                ) : (
                  <>
                    <div className="section-heading">
                      <h3>{slotLabel}</h3>
                      <span className="meta">
                        {available} available / {max}
                      </span>
                    </div>
                    <p>Used {used} / {max}</p>
                  </>
                )}
              </article>
            );
          })}
        </div>
      ) : null}
      {presentedSpells.length ? (
        <div className="spell-level-groups">
          {presentedSpellGroups.map((group) => (
            <section className="spell-level-group" key={group.key}>
              <div className="spell-level-group__heading">
                <h3>{group.label}</h3>
              </div>
              <div className="spell-card-grid spell-card-grid--level">
                {group.spells.map((spell) => {
                  const detailLine = presentedSpellCardDetailLine(spell);
                  const levelSchool = [spell.level_label, spell.school].filter(Boolean).join(" | ");
                  const spellCardContent = (
                    <>
                      <span className="spell-card__name">{spell.name || "Spell"}</span>
                      <span className="spell-card__eyebrow">{levelSchool || "Spell"}</span>
                      {spell.badges?.length ? (
                        <span className="badge-list spell-card__badges">
                          {spell.badges.map((badge) => (
                            <span className="meta-badge" key={badge}>
                              {badge}
                            </span>
                          ))}
                        </span>
                      ) : null}
                      {detailLine ? <span className="spell-card__meta">{detailLine}</span> : null}
                    </>
                  );
                  return (
                    <article className="spell-card" key={draftKey(spell.class_row_id, spell.name, spell.level_label)}>
                      {spell.description_html || spell.href ? (
                        <button
                          type="button"
                          className="spell-card__main"
                          aria-haspopup="dialog"
                          onClick={() => openSpellDetail(spell)}
                        >
                          {spellCardContent}
                        </button>
                      ) : (
                        <span className="spell-card__main">{spellCardContent}</span>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      ) : spells.length ? (
        <div className="spell-level-groups">
          {rawSpellGroups.map((group) => (
            <section className="spell-level-group" key={group.key}>
              <div className="spell-level-group__heading">
                <h3>{group.label}</h3>
              </div>
              <div className="spell-card-grid spell-card-grid--level">
                {group.spells.map((spell) => {
                  const mark = readString(spell.mark);
                  const detailLine = rawSpellCardDetailLine(spell);
                  const levelSchool = [readString(spell.level_label), readString(spell.school)]
                    .filter(Boolean)
                    .join(" | ");
                  return (
                    <article className="spell-card" key={readString(spell.id, readString(spell.name))}>
                      <span className="spell-card__main">
                        <span className="spell-card__name">{readString(spell.name, "Spell")}</span>
                        {levelSchool ? <span className="spell-card__eyebrow">{levelSchool}</span> : null}
                        {mark ? (
                          <span className="badge-list spell-card__badges">
                            <span className="meta-badge">{mark}</span>
                          </span>
                        ) : null}
                        {detailLine ? <span className="spell-card__meta">{detailLine}</span> : null}
                      </span>
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      ) : null}
    </section>
  );
}
