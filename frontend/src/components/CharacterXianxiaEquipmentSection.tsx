import { Fragment } from "react";
import type { CharacterPresentedXianxia } from "../api/types";
import { readNumber, readString, stringFromUnknown } from "../characterValueUtils";

export function CharacterXianxiaEquipmentSection({
  defenseReference,
  equipment,
}: {
  defenseReference: Record<string, unknown>;
  equipment: CharacterPresentedXianxia["equipment"];
}) {
  return (
    <section className="read-section" id="xianxia-equipment">
      <div className="section-heading">
        <h2>Equipment</h2>
      </div>
      <div className="detail-grid">
        <article className="detail-card">
          <h3>Defense calculation</h3>
          {Object.keys(defenseReference).length ? (
            <>
              <p><strong>{stringFromUnknown(defenseReference.value, "--")}</strong></p>
              <ul className="plain-list slot-list">
                <li><span>Base</span><strong>{stringFromUnknown(defenseReference.base, "--")}</strong></li>
                <li><span>Manual armor bonus</span><strong>{stringFromUnknown(defenseReference.manual_armor_bonus, "--")}</strong></li>
                <li><span>Constitution</span><strong>{stringFromUnknown(defenseReference.constitution, "--")}</strong></li>
              </ul>
              <p className="meta">Defense = {readString(defenseReference.formula, "")}</p>
            </>
          ) : (
            <p><strong>{stringFromUnknown(equipment?.defense, "--")}</strong></p>
          )}
          <p className="meta">Manual armor bonus: {readNumber(equipment?.manual_armor_bonus, 0)}</p>
        </article>
        <article className="detail-card">
          <h3>Necessary weapons</h3>
          {equipment?.necessary_weapons?.length ? (
            <ul className="plain-list slot-list">
              {equipment.necessary_weapons.map((record, index) => (
                <li key={`${record.name}-${index}`}>
                  <span>{record.name}</span>
                  {record.reason ? <strong>{record.reason}</strong> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta">No necessary weapons are recorded on this sheet yet.</p>
          )}
        </article>
        <article className="detail-card">
          <h3>Necessary tools</h3>
          {equipment?.necessary_tools?.length ? (
            <ul className="plain-list slot-list">
              {equipment.necessary_tools.map((record, index) => (
                <li key={`${record.name}-${index}`}>
                  <span>{record.name}</span>
                  {record.reason ? <strong>{record.reason}</strong> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta">No necessary tools are recorded on this sheet yet.</p>
          )}
        </article>
        <article className="detail-card">
          <h3>Equipped inventory</h3>
          {equipment?.equipped_items?.length ? (
            <ul className="plain-list slot-list">
              {equipment.equipped_items.map((item) => (
                <Fragment key={item.id}>
                  <li>
                    <span>{item.name}</span>
                    <strong>{readString(item.item_type)}</strong>
                  </li>
                  {readString(item.item_type) === "Armor" ? (
                    <li className="meta">Armor is displayed here only; Defense still uses the manual armor bonus above.</li>
                  ) : null}
                  {item.notes ? <li className="meta">{item.notes}</li> : null}
                </Fragment>
              ))}
            </ul>
          ) : (
            <p className="meta">No equippable inventory is currently marked equipped.</p>
          )}
        </article>
      </div>
    </section>
  );
}
