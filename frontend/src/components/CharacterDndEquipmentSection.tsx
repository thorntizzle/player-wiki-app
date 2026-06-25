import type { Dispatch, FormEvent, SetStateAction } from "react";
import type {
  CharacterArcaneArmorState,
  CharacterArtificerInfusionsState,
  CharacterEquipmentRow,
  CharacterEquipmentState,
} from "../api/types";
import type { CharacterArtificerInfusionDrafts, CharacterEquipmentDraft } from "../characterPaneDrafts";
import { readString } from "../characterValueUtils";

export function CharacterDndEquipmentSection({
  arcaneArmorDraft,
  arcaneArmorState,
  artificerInfusionDrafts,
  artificerInfusionsState,
  canEdit,
  equipmentDrafts,
  equipmentRows,
  equipmentState,
  isCombatSurface,
  isArtificerInfusionSaving,
  isEquipmentStateSaving,
  isFeatureStateSaving,
  openItemDetail,
  setArcaneArmorDraft,
  setArtificerInfusionDrafts,
  setEquipmentDrafts,
  submitArtificerInfusions,
  submitArtificerInfusionsPatch,
  submitArcaneArmorState,
  submitEquipmentState,
  submitEquipmentStatePatch,
}: {
  arcaneArmorDraft: boolean;
  arcaneArmorState: CharacterArcaneArmorState | undefined;
  artificerInfusionDrafts: CharacterArtificerInfusionDrafts;
  artificerInfusionsState: CharacterArtificerInfusionsState | undefined;
  canEdit: boolean;
  equipmentDrafts: Record<string, CharacterEquipmentDraft>;
  equipmentRows: CharacterEquipmentRow[];
  equipmentState: CharacterEquipmentState | undefined;
  isCombatSurface: boolean;
  isArtificerInfusionSaving: boolean;
  isEquipmentStateSaving: boolean;
  isFeatureStateSaving: boolean;
  openItemDetail: (item: CharacterEquipmentRow) => void;
  setArcaneArmorDraft: Dispatch<SetStateAction<boolean>>;
  setArtificerInfusionDrafts: Dispatch<SetStateAction<CharacterArtificerInfusionDrafts>>;
  setEquipmentDrafts: Dispatch<SetStateAction<Record<string, CharacterEquipmentDraft>>>;
  submitArtificerInfusions: (event: FormEvent<HTMLFormElement>) => void;
  submitArtificerInfusionsPatch: (drafts: CharacterArtificerInfusionDrafts) => void;
  submitArcaneArmorState: (event?: FormEvent<HTMLFormElement>, enabled?: boolean) => void;
  submitEquipmentState: (event: FormEvent<HTMLFormElement>, item: CharacterEquipmentRow) => void;
  submitEquipmentStatePatch: (item: CharacterEquipmentRow, draft: CharacterEquipmentDraft) => void;
}) {
  return (
    <section className="read-section" id="character-equipment">
      <div className="section-heading">
        <h2>Equipment</h2>
      </div>
      {equipmentState ? (
        <div className="detail-grid">
          <article className="detail-card">
            <h3>Attuned items</h3>
            <p>
              <strong>
                {equipmentState.attuned_count} / {equipmentState.max_attuned_items}
              </strong>
            </p>
            <p className="meta">
              Attunement is separate from equipped state and usually has room for up to {equipmentState.max_attuned_items} items.
            </p>
            {equipmentState.over_attunement_limit ? (
              <p className="meta">This sheet is currently over the normal attunement limit.</p>
            ) : null}
          </article>
          <article className="detail-card">
            <h3>Equipped items</h3>
            <p>
              <strong>{equipmentState.equipped_count}</strong>
            </p>
            <p className="meta">
              Armor and magic items use equipped state; weapons also track an applicable wielding mode.
            </p>
          </article>
        </div>
      ) : null}
      {arcaneArmorState?.available ? (
        <article className="detail-card character-edit-row" id="character-arcane-armor-state">
          <div className="section-heading">
            <h3>{readString(arcaneArmorState.label, "Arcane Armor")}</h3>
            <span className="meta">
              {[
                readString(arcaneArmorState.status_label),
                arcaneArmorState.enabled ? readString(arcaneArmorState.hands_label) : "",
              ]
                .filter(Boolean)
                .join(" | ")}
            </span>
          </div>
          {canEdit ? (
            <form onSubmit={submitArcaneArmorState} className="stack-form" data-character-autosubmit>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="enabled"
                  value="1"
                  checked={arcaneArmorDraft}
                  disabled={isFeatureStateSaving || !canEdit}
                  onChange={(event) => {
                    const nextArcaneArmorState = event.currentTarget.checked;
                    setArcaneArmorDraft(nextArcaneArmorState);
                    submitArcaneArmorState(undefined, nextArcaneArmorState);
                  }}
                />
                Arcane Armor enabled
              </label>
            </form>
          ) : null}
        </article>
      ) : null}
      {artificerInfusionsState?.available ? (
        <article className="detail-card character-edit-row" id="character-artificer-infusions">
          <div className="section-heading">
            <h3>Artificer Infusions</h3>
            <span className="meta">
              Level {artificerInfusionsState.artificer_level} | Active {artificerInfusionsState.active_count} /{" "}
              {artificerInfusionsState.active_capacity} | Known {artificerInfusionsState.known_count} /{" "}
              {artificerInfusionsState.known_capacity}
            </span>
          </div>
          {artificerInfusionsState.active.length ? (
            <ul className="feature-note-list">
              {artificerInfusionsState.active.map((infusion) => (
                <li key={`${infusion.infusion_key}-${infusion.target_item_ref}`}>
                  <strong>{readString(infusion.name, "Infusion")}</strong>: {readString(infusion.target_item_name, "Item")}
                  <span className="meta"> - {readString(infusion.effect_summary)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta">No active infusions selected.</p>
          )}
          {canEdit ? (
            <form
              onSubmit={submitArtificerInfusions}
              className="stack-form"
              data-character-autosubmit
              data-character-sheet-edit-form="artificer-infusions"
            >
              <div className="detail-grid">
                {artificerInfusionsState.known.map((infusion) => {
                  const currentTarget = artificerInfusionDrafts[infusion.infusion_key] ?? "";
                  return (
                    <label key={infusion.infusion_key}>
                      {readString(infusion.name, "Infusion")}
                      <select
                        name={`infusion_${infusion.infusion_key}`}
                        value={currentTarget}
                        disabled={isArtificerInfusionSaving || !canEdit}
                        onChange={(event) => {
                          const nextDrafts = {
                            ...artificerInfusionDrafts,
                            [infusion.infusion_key]: event.currentTarget.value,
                          };
                          setArtificerInfusionDrafts(nextDrafts);
                          submitArtificerInfusionsPatch(nextDrafts);
                        }}
                      >
                        <option value="">Not active</option>
                        {infusion.target_options.map((option) => (
                          <option value={option.value} key={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <span className="meta">
                        {infusion.automation_status === "automated" ? "Automated effect" : "Active note only"} -{" "}
                        {readString(infusion.effect_summary)}
                      </span>
                    </label>
                  );
                })}
              </div>
              <button
                type="submit"
                className="ghost-button resource-card__save"
                disabled={isArtificerInfusionSaving || !canEdit}
              >
                Save
              </button>
            </form>
          ) : null}
        </article>
      ) : null}
      {equipmentRows.length ? (
        <div className="equipment-state-grid" id={isCombatSurface ? "combat-character-equipment-state" : "character-equipment-state"}>
          {equipmentRows.map((item) => {
            const draft = equipmentDrafts[item.id] ?? {
              isEquipped: Boolean(item.is_equipped),
              isAttuned: Boolean(item.is_attuned),
              weaponWieldMode: item.weapon_wield_mode || "",
            };
            return (
              <article className="detail-card character-edit-row" key={item.id || item.name}>
                <div className="section-heading">
                  <h3>
                    {item.href ? <a href={item.href}>{readString(item.name, "Item")}</a> : readString(item.name, "Item")}
                  </h3>
                  <span className="meta">{readString(item.source_label)}</span>
                </div>
                <p className="meta">
                  {[readString(item.equipped_label), item.requires_attunement ? (item.is_attuned ? "Attuned" : "Not attuned") : ""]
                    .filter(Boolean)
                    .join(" | ")}
                </p>
                {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                {item.description_html || item.notes || item.href ? (
                  <button type="button" className="ghost-button item-detail-button" onClick={() => openItemDetail(item)}>
                    Item details
                  </button>
                ) : null}
                {canEdit ? (
                  <form
                    onSubmit={(event) => submitEquipmentState(event, item)}
                    className="stack-form"
                    data-character-autosubmit
                    data-character-sheet-edit-form="equipment-state"
                  >
                    <div className="detail-grid">
                      {item.supports_weapon_wield_mode ? (
                        <label>
                          Wielding
                          <select
                            id={`equipment-wield-${item.id}`}
                            name="weapon_wield_mode"
                            value={draft.weaponWieldMode}
                            disabled={isEquipmentStateSaving || !canEdit}
                            onChange={(event) => {
                              const nextDraft = { ...draft, weaponWieldMode: event.currentTarget.value };
                              setEquipmentDrafts({
                                ...equipmentDrafts,
                                [item.id]: nextDraft,
                              });
                              submitEquipmentStatePatch(item, nextDraft);
                            }}
                          >
                            <option value="">Not equipped</option>
                            {item.weapon_wield_options.map((option) => (
                              <option value={option.value} key={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            name="is_equipped"
                            value="1"
                            checked={draft.isEquipped}
                            disabled={isEquipmentStateSaving || !canEdit}
                            onChange={(event) => {
                              const nextDraft = { ...draft, isEquipped: event.currentTarget.checked };
                              setEquipmentDrafts({
                                ...equipmentDrafts,
                                [item.id]: nextDraft,
                              });
                              submitEquipmentStatePatch(item, nextDraft);
                            }}
                          />
                          Equipped
                        </label>
                      )}
                      {item.requires_attunement ? (
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            name="is_attuned"
                            value="1"
                            checked={draft.isAttuned}
                            disabled={isEquipmentStateSaving || !canEdit}
                            onChange={(event) => {
                              const nextDraft = { ...draft, isAttuned: event.currentTarget.checked };
                              setEquipmentDrafts({
                                ...equipmentDrafts,
                                [item.id]: nextDraft,
                              });
                              submitEquipmentStatePatch(item, nextDraft);
                            }}
                          />
                          Attuned
                        </label>
                      ) : null}
                    </div>
                    {item.attunement_hint && item.attunement_hint !== "Requires attunement" ? (
                      <p className="meta">{item.attunement_hint}</p>
                    ) : null}
                  </form>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <article className="detail-card character-empty-state">
          <p className="meta">No equipment state rows.</p>
        </article>
      )}
    </section>
  );
}
