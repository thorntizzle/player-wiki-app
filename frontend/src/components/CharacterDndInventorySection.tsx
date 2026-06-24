import type { Dispatch, FocusEvent, FormEvent, SetStateAction } from "react";
import type { CharacterPresentedInventoryItem } from "../api/types";
import { readNumber, readString } from "../characterValueUtils";

type ItemDetailInput = {
  name: string;
  href?: string;
  description_html?: string;
  notes?: string;
};

export function CharacterDndInventorySection({
  canEdit,
  currencyDraft,
  inventory,
  inventoryDrafts,
  isCurrencySaving,
  isInventorySaving,
  openItemDetail,
  presentedInventoryByKey,
  setCurrencyDraft,
  setInventoryDrafts,
  submitCurrency,
  submitCurrencyOnBlur,
  submitInventory,
  submitInventoryOnBlur,
}: {
  canEdit: boolean;
  currencyDraft: Record<string, string>;
  inventory: Record<string, unknown>[];
  inventoryDrafts: Record<string, string>;
  isCurrencySaving: boolean;
  isInventorySaving: boolean;
  openItemDetail: (item: ItemDetailInput) => void;
  presentedInventoryByKey: ReadonlyMap<string, CharacterPresentedInventoryItem>;
  setCurrencyDraft: Dispatch<SetStateAction<Record<string, string>>>;
  setInventoryDrafts: Dispatch<SetStateAction<Record<string, string>>>;
  submitCurrency: (event: FormEvent<HTMLFormElement>) => void;
  submitCurrencyOnBlur: (event: FocusEvent<HTMLInputElement>) => void;
  submitInventory: (event: FormEvent<HTMLFormElement>, itemId: string) => void;
  submitInventoryOnBlur: (event: FocusEvent<HTMLInputElement>) => void;
}) {
  return (
    <section className="read-section" id="session-inventory">
      <div className="section-heading">
        <h2>Inventory</h2>
      </div>
      {inventory.length ? (
        <div className="inventory-list">
          {inventory.map((item) => {
            const id = readString(item.id);
            const itemRef = readString(item.catalog_ref, id);
            const presentedItem = presentedInventoryByKey.get(itemRef) ?? presentedInventoryByKey.get(id);
            const itemName = readString(presentedItem?.name, readString(item.name, "Item"));
            const itemNotes = readString(presentedItem?.notes, readString(item.notes));
            const itemHref = readString(presentedItem?.href);
            const itemDescriptionHtml = readString(presentedItem?.description_html);
            const itemTags = presentedItem?.tags?.length ? presentedItem.tags : [];
            return (
              <article className="inventory-row" key={id || itemRef || itemName}>
                <div className="inventory-row__header">
                  <h3>{itemHref ? <a href={itemHref}>{itemName}</a> : itemName}</h3>
                </div>
                {itemTags.length ? <p className="meta">{itemTags.join(", ")}</p> : null}
                {canEdit && id ? (
                  item.weight ? <p className="meta">{readString(item.weight)}</p> : null
                ) : (
                  <p className="meta">
                    Qty {readNumber(item.quantity, 1)}
                    {item.weight ? ` | ${readString(item.weight)}` : ""}
                  </p>
                )}
                {itemDescriptionHtml || itemNotes || itemHref ? (
                  <button
                    type="button"
                    className="ghost-button item-detail-button"
                    onClick={() =>
                      openItemDetail({
                        name: itemName,
                        href: itemHref,
                        description_html: itemDescriptionHtml,
                        notes: itemNotes,
                      })
                    }
                  >
                    Item details
                  </button>
                ) : null}
                {canEdit && id ? (
                  <form
                    onSubmit={(event) => submitInventory(event, id)}
                    className="session-inline-form inventory-row__quantity-form"
                    data-character-autosubmit
                    data-character-sheet-edit-form="inventory"
                    data-character-sheet-edit-row-id={id}
                  >
                    <label className="session-field" htmlFor={`inventory-${id}`}>
                      <span>Quantity</span>
                      <input
                        id={`inventory-${id}`}
                        type="number"
                        min="0"
                        value={inventoryDrafts[id] ?? ""}
                        onChange={(event) =>
                          setInventoryDrafts({ ...inventoryDrafts, [id]: event.currentTarget.value })
                        }
                        onBlur={submitInventoryOnBlur}
                      />
                    </label>
                    <button type="submit" className="visually-hidden" disabled={isInventorySaving || !canEdit}>
                      Update {itemName} quantity
                    </button>
                  </form>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
      <div className="detail-grid">
        <article className="detail-card">
          <h3>Currency</h3>
          <div className="currency-grid" id="session-currency">
            {["cp", "sp", "ep", "gp", "pp"].map((key) => (
              <form key={key} onSubmit={submitCurrency} className="currency-form currency-box">
                <div className="currency-box__header">
                  <span id={`currency-${key}-label`}>{key.toUpperCase()}</span>
                </div>
                <input
                  className="currency-box__amount"
                  id={`currency-${key}`}
                  aria-labelledby={`currency-${key}-label`}
                  type="number"
                  min="0"
                  value={currencyDraft[key] ?? "0"}
                  disabled={!canEdit}
                  onChange={(event) => setCurrencyDraft({ ...currencyDraft, [key]: event.currentTarget.value })}
                  onBlur={submitCurrencyOnBlur}
                />
                <button type="submit" className="visually-hidden" disabled={isCurrencySaving || !canEdit}>
                  Update {key.toUpperCase()}
                </button>
              </form>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
