import type { Dispatch, FocusEvent, FormEvent, SetStateAction } from "react";
import type { CharacterXianxiaInventoryItem } from "../api/types";
import {
  joinDisplay,
  xianxiaInventoryDraftFromItem,
  type CharacterXianxiaInventoryDraft,
} from "../characterPaneUtils";
import { readNumber } from "../characterValueUtils";

type XianxiaCurrencyEntry = {
  key: string;
  label: string;
  amount: number;
  description?: string;
};

export function CharacterXianxiaInventorySection({
  canEdit,
  currency,
  currencyDraft,
  inventory,
  isAddingInventoryItem,
  isCurrencySaving,
  isRemovingInventoryItem,
  isUpdatingInventoryItem,
  newXianxiaInventoryDraft,
  setCurrencyDraft,
  setNewXianxiaInventoryDraft,
  setXianxiaInventoryDrafts,
  submitCurrency,
  submitCurrencyOnBlur,
  submitXianxiaInventoryAdd,
  submitXianxiaInventoryUpdate,
  toggleXianxiaInventoryEquipped,
  removeXianxiaInventory,
  xianxiaCurrency,
  xianxiaInventoryDrafts,
}: {
  canEdit: boolean;
  currency: Record<string, unknown>;
  currencyDraft: Record<string, string>;
  inventory: CharacterXianxiaInventoryItem[];
  isAddingInventoryItem: boolean;
  isCurrencySaving: boolean;
  isRemovingInventoryItem: boolean;
  isUpdatingInventoryItem: boolean;
  newXianxiaInventoryDraft: CharacterXianxiaInventoryDraft;
  setCurrencyDraft: Dispatch<SetStateAction<Record<string, string>>>;
  setNewXianxiaInventoryDraft: Dispatch<SetStateAction<CharacterXianxiaInventoryDraft>>;
  setXianxiaInventoryDrafts: Dispatch<SetStateAction<Record<string, CharacterXianxiaInventoryDraft>>>;
  submitCurrency: (event: FormEvent<HTMLFormElement>) => void;
  submitCurrencyOnBlur: (event: FocusEvent<HTMLInputElement>) => void;
  submitXianxiaInventoryAdd: (event: FormEvent<HTMLFormElement>) => void;
  submitXianxiaInventoryUpdate: (event: FormEvent<HTMLFormElement>, item: CharacterXianxiaInventoryItem) => void;
  toggleXianxiaInventoryEquipped: (item: CharacterXianxiaInventoryItem, isEquipped: boolean) => void;
  removeXianxiaInventory: (item: CharacterXianxiaInventoryItem) => void;
  xianxiaCurrency: XianxiaCurrencyEntry[];
  xianxiaInventoryDrafts: Record<string, CharacterXianxiaInventoryDraft>;
}) {
  const currencyEntries = xianxiaCurrency.length
    ? xianxiaCurrency
    : [
        { key: "coin", label: "Coin", amount: readNumber(currency.coin) },
        { key: "supply", label: "Supply", amount: readNumber(currency.supply) },
        { key: "spirit_stones", label: "Spirit Stones", amount: readNumber(currency.spirit_stones) },
      ];

  return (
    <section className="read-section" id="xianxia-inventory">
      <div className="section-heading">
        <h2>Inventory</h2>
      </div>
      {inventory.length ? (
        <div className="inventory-list">
          {inventory.map((item) => {
            const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
            return (
              <article className="inventory-row" key={item.id}>
                <div className="inventory-row__header">
                  <h4>{item.name}</h4>
                  <strong>x{item.quantity}</strong>
                </div>
                <p className="meta">{joinDisplay([item.item_nature, item.item_type, item.is_equipped ? "Equipped" : ""])}</p>
                {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                {item.notes ? <p className="meta">{item.notes}</p> : null}
                {canEdit ? (
                  <div className="detail-cluster">
                    <details className="detail-card">
                      <summary>Edit item</summary>
                      <form onSubmit={(event) => submitXianxiaInventoryUpdate(event, item)} className="stack-form">
                        <div className="builder-field-grid">
                          <label className="session-field" htmlFor={`xianxia-inventory-name-${item.id}`}>
                            <span>Name</span>
                            <input
                              id={`xianxia-inventory-name-${item.id}`}
                              value={draft.name}
                              onChange={(event) =>
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, name: event.currentTarget.value },
                                })
                              }
                            />
                          </label>
                          <label className="session-field" htmlFor={`xianxia-inventory-quantity-${item.id}`}>
                            <span>Quantity</span>
                            <input
                              id={`xianxia-inventory-quantity-${item.id}`}
                              type="number"
                              min="0"
                              value={draft.quantity}
                              onChange={(event) =>
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, quantity: event.currentTarget.value },
                                })
                              }
                            />
                          </label>
                          <label className="session-field" htmlFor={`xianxia-inventory-nature-${item.id}`}>
                            <span>Nature</span>
                            <select
                              id={`xianxia-inventory-nature-${item.id}`}
                              value={draft.itemNature}
                              onChange={(event) =>
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, itemNature: event.currentTarget.value },
                                })
                              }
                            >
                              <option value="Mundane">Mundane</option>
                              <option value="Relic">Relic</option>
                            </select>
                          </label>
                          <label className="session-field" htmlFor={`xianxia-inventory-type-${item.id}`}>
                            <span>Type</span>
                            <select
                              id={`xianxia-inventory-type-${item.id}`}
                              value={draft.itemType}
                              onChange={(event) =>
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, itemType: event.currentTarget.value },
                                })
                              }
                            >
                              <option value="Weapon">Weapon</option>
                              <option value="Armor">Armor</option>
                              <option value="Artifact">Artifact</option>
                              <option value="Consumable">Consumable</option>
                              <option value="Miscellaneous">Miscellaneous</option>
                            </select>
                          </label>
                          <label className="session-field" htmlFor={`xianxia-inventory-tags-${item.id}`}>
                            <span>Tags</span>
                            <input
                              id={`xianxia-inventory-tags-${item.id}`}
                              value={draft.tags}
                              onChange={(event) =>
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, tags: event.currentTarget.value },
                                })
                              }
                            />
                          </label>
                          <label className="session-field" htmlFor={`xianxia-inventory-notes-${item.id}`}>
                            <span>Notes</span>
                            <textarea
                              id={`xianxia-inventory-notes-${item.id}`}
                              rows={3}
                              value={draft.notes}
                              onChange={(event) =>
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, notes: event.currentTarget.value },
                                })
                              }
                            />
                          </label>
                        </div>
                        <label className="toggle-row">
                          <input
                            type="checkbox"
                            checked={draft.equippable}
                            onChange={(event) =>
                              setXianxiaInventoryDrafts({
                                ...xianxiaInventoryDrafts,
                                [item.id]: { ...draft, equippable: event.currentTarget.checked },
                              })
                            }
                          />
                          Equippable
                        </label>
                        {draft.equippable ? (
                          <label className="toggle-row">
                            <input
                              type="checkbox"
                              checked={draft.isEquipped}
                              onChange={(event) => {
                                const isEquipped = event.currentTarget.checked;
                                setXianxiaInventoryDrafts({
                                  ...xianxiaInventoryDrafts,
                                  [item.id]: { ...draft, isEquipped },
                                });
                                toggleXianxiaInventoryEquipped(item, isEquipped);
                              }}
                            />
                            Equipped
                          </label>
                        ) : null}
                        <button type="submit" disabled={isUpdatingInventoryItem}>
                          {isUpdatingInventoryItem ? "Saving..." : "Save item"}
                        </button>
                      </form>
                    </details>
                    <button
                      type="button"
                      className="button-link subtle"
                      disabled={isRemovingInventoryItem}
                      onClick={() => removeXianxiaInventory(item)}
                    >
                      {isRemovingInventoryItem ? "Removing..." : "Remove"}
                    </button>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <article className="detail-card character-empty-state">
          <p className="meta">No Xianxia inventory items.</p>
        </article>
      )}
      {canEdit ? (
        <article className="detail-card session-card" id="xianxia-inventory-add">
          <h3>Add inventory item</h3>
          <form onSubmit={submitXianxiaInventoryAdd} className="stack-form">
            <div className="builder-field-grid">
              <label className="session-field" htmlFor="xianxia-new-item-name">
                <span>Name</span>
                <input
                  id="xianxia-new-item-name"
                  value={newXianxiaInventoryDraft.name}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, name: event.currentTarget.value })
                  }
                />
              </label>
              <label className="session-field" htmlFor="xianxia-new-item-quantity">
                <span>Quantity</span>
                <input
                  id="xianxia-new-item-quantity"
                  type="number"
                  min="0"
                  value={newXianxiaInventoryDraft.quantity}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, quantity: event.currentTarget.value })
                  }
                />
              </label>
              <label className="session-field" htmlFor="xianxia-new-item-nature">
                <span>Nature</span>
                <select
                  id="xianxia-new-item-nature"
                  value={newXianxiaInventoryDraft.itemNature}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemNature: event.currentTarget.value })
                  }
                >
                  <option value="Mundane">Mundane</option>
                  <option value="Relic">Relic</option>
                </select>
              </label>
              <label className="session-field" htmlFor="xianxia-new-item-type">
                <span>Type</span>
                <select
                  id="xianxia-new-item-type"
                  value={newXianxiaInventoryDraft.itemType}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemType: event.currentTarget.value })
                  }
                >
                  <option value="Weapon">Weapon</option>
                  <option value="Armor">Armor</option>
                  <option value="Artifact">Artifact</option>
                  <option value="Consumable">Consumable</option>
                  <option value="Miscellaneous">Miscellaneous</option>
                </select>
              </label>
              <label className="session-field" htmlFor="xianxia-new-item-tags">
                <span>Tags</span>
                <input
                  id="xianxia-new-item-tags"
                  value={newXianxiaInventoryDraft.tags}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, tags: event.currentTarget.value })
                  }
                />
              </label>
              <label className="session-field" htmlFor="xianxia-new-item-notes">
                <span>Notes</span>
                <textarea
                  id="xianxia-new-item-notes"
                  rows={3}
                  value={newXianxiaInventoryDraft.notes}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, notes: event.currentTarget.value })
                  }
                />
              </label>
            </div>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={newXianxiaInventoryDraft.equippable}
                onChange={(event) =>
                  setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, equippable: event.currentTarget.checked })
                }
              />
              Equippable
            </label>
            {newXianxiaInventoryDraft.equippable ? (
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={newXianxiaInventoryDraft.isEquipped}
                  onChange={(event) =>
                    setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, isEquipped: event.currentTarget.checked })
                  }
                />
                Equipped
              </label>
            ) : null}
            <button type="submit" className="button-link" disabled={isAddingInventoryItem}>
              {isAddingInventoryItem ? "Adding..." : "Add item"}
            </button>
          </form>
        </article>
      ) : null}
      <div className="detail-grid" id="session-currency">
        <article className="detail-card session-card">
          <h3>Currency</h3>
          <div className="currency-grid">
            {currencyEntries.map((entry) => (
              <form key={entry.key} onSubmit={submitCurrency} className="currency-form currency-box">
                <div className="currency-box__header">
                  <span>{entry.label}</span>
                </div>
                <input
                  className="currency-box__amount"
                  id={`currency-${entry.key}`}
                  type="number"
                  min="0"
                  value={currencyDraft[entry.key] ?? String(entry.amount ?? 0)}
                  disabled={!canEdit}
                  onChange={(event) => setCurrencyDraft({ ...currencyDraft, [entry.key]: event.currentTarget.value })}
                  onBlur={submitCurrencyOnBlur}
                />
                {entry.description ? <p className="meta">{entry.description}</p> : null}
                <button type="submit" className="visually-hidden" disabled={isCurrencySaving || !canEdit}>
                  Update {entry.label}
                </button>
              </form>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
