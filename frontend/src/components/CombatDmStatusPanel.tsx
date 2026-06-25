import { useState } from "react";
import type {
  CombatCondition,
  CombatNpcResourcesPatchPayload,
  CombatResourcesPatchPayload,
  CombatTurnPatchPayload,
  CombatVitalsPatchPayload,
  CombatantSummary,
} from "../api/types";

interface CombatVitalsDraft {
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatResourcesDraft {
  movementRemaining: string;
  hasAction: boolean;
  hasBonusAction: boolean;
  hasReaction: boolean;
}

type CombatNpcResourceDrafts = Record<string, string>;

interface CombatTurnDraft {
  turnValue: string;
  initiativePriority: string;
}

interface CombatConditionDraft {
  name: string;
  durationText: string;
}

interface CombatDmStatusPanelProps {
  canManageCombat: boolean;
  selectedCombatant: CombatantSummary | null;
  trackerRoundNumber: number | null;
  conditionOptions: string[];
  turnDraft: CombatTurnDraft;
  vitalsDraft: CombatVitalsDraft;
  resourcesDraft: CombatResourcesDraft;
  npcResourceDrafts: CombatNpcResourceDrafts;
  conditionDraft: CombatConditionDraft;
  isUpdatingTurn: boolean;
  isUpdatingVitals: boolean;
  isUpdatingResources: boolean;
  isUpdatingNpcResources: boolean;
  isAddingCondition: boolean;
  isDeletingCondition: boolean;
  isSettingCurrent: boolean;
  isDeletingCombatant: boolean;
  onTurnDraftChange: (updates: Partial<CombatTurnDraft>) => void;
  onVitalsDraftChange: (updates: Partial<CombatVitalsDraft>) => void;
  onResourcesDraftChange: (updates: Partial<CombatResourcesDraft>) => void;
  onNpcResourceDraftChange: (resourceKey: string, value: string) => void;
  onConditionDraftChange: (updates: Partial<CombatConditionDraft>) => void;
  onUpdateTurn: (payload: CombatTurnPatchPayload) => void;
  onUpdateVitals: (payload: CombatVitalsPatchPayload) => void;
  onUpdateResources: (payload: CombatResourcesPatchPayload) => void;
  onUpdateNpcResources: (payload: CombatNpcResourcesPatchPayload) => void;
  onAddCondition: (draft: CombatConditionDraft) => void;
  onDeleteCondition: (condition: CombatCondition) => void;
  onSetCurrent: () => void;
  onDeleteCombatant: () => void;
}

export function CombatDmStatusPanel({
  canManageCombat,
  selectedCombatant,
  trackerRoundNumber,
  conditionOptions,
  turnDraft,
  vitalsDraft,
  resourcesDraft,
  npcResourceDrafts,
  conditionDraft,
  isUpdatingTurn,
  isUpdatingVitals,
  isUpdatingResources,
  isUpdatingNpcResources,
  isAddingCondition,
  isDeletingCondition,
  isSettingCurrent,
  isDeletingCombatant,
  onTurnDraftChange,
  onVitalsDraftChange,
  onResourcesDraftChange,
  onNpcResourceDraftChange,
  onConditionDraftChange,
  onUpdateTurn,
  onUpdateVitals,
  onUpdateResources,
  onUpdateNpcResources,
  onAddCondition,
  onDeleteCondition,
  onSetCurrent,
  onDeleteCombatant,
}: CombatDmStatusPanelProps) {
  const [deleteCombatantConfirmed, setDeleteCombatantConfirmed] = useState(false);

  if (!canManageCombat) {
    return (
      <article className="card">
        <p>DM combat status requires combat management access.</p>
      </article>
    );
  }
  if (!selectedCombatant) {
    return (
      <article className="card">
        <h3>No selected combatant</h3>
        <p>Add combatants in DM Controls, then select one from the turn order.</p>
      </article>
    );
  }

  const isPlayerCharacter = Boolean(selectedCombatant.character_slug);
  const npcResourceCounters = selectedCombatant.npc_resource_counters ?? [];
  const npcResourceNotes = selectedCombatant.npc_resource_notes ?? [];
  const editableNpcResourceCounters = npcResourceCounters.filter((counter) => counter.can_edit);
  const hasNpcResourceReference = !isPlayerCharacter && (npcResourceCounters.length > 0 || npcResourceNotes.length > 0);
  const removeCombatantHint = !deleteCombatantConfirmed
    ? "Check Confirm removal to enable this action."
    : isDeletingCombatant
      ? "Selected combatant removal is already in progress."
      : "";
  const vitalsPayload = (): CombatVitalsPatchPayload => {
    const base: CombatVitalsPatchPayload = {
      current_hp: vitalsDraft.currentHp,
      temp_hp: vitalsDraft.tempHp,
    };
    if (isPlayerCharacter) {
      base.expected_revision = selectedCombatant.state_revision;
    } else {
      base.expected_combatant_revision = selectedCombatant.combatant_revision;
      base.max_hp = vitalsDraft.maxHp;
      base.movement_total = vitalsDraft.movementTotal;
    }
    return base;
  };

  return (
    <>
      <section className="combat-dm-snapshot-controls" aria-label="DM tactical controls">
        <article className="combat-snapshot-control-block">
          <div className="section-heading combat-status-snapshot__heading">
            <div>
              <p className="card-kicker">Authority</p>
              <h2>Turn Focus</h2>
            </div>
            <div className="combatant-badges">
              <span className="combat-badge">Round {trackerRoundNumber ?? "?"}</span>
              <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
              {selectedCombatant.is_current_turn ? (
                <span className="combat-badge combat-badge--active">Current turn</span>
              ) : (
                <button
                  type="button"
                  className="combat-badge combat-badge--button combat-status-snapshot__set-current"
                  onClick={onSetCurrent}
                  disabled={isSettingCurrent}
                >
                  {isSettingCurrent ? "Setting..." : "Set current"}
                </button>
              )}
            </div>
          </div>
          <p id="combat-turn-editor-help" className="meta">
            Turn value orders initiative. Priority breaks ties after turn value.
          </p>
          <form
            className="stack-form combat-status-authority-form"
            aria-describedby="combat-turn-editor-help"
            onSubmit={(event) => {
              event.preventDefault();
              onUpdateTurn({
                expected_combatant_revision: selectedCombatant.combatant_revision,
                turn_value: turnDraft.turnValue,
                initiative_priority: turnDraft.initiativePriority,
              });
            }}
          >
            <label className="field">
              <span>Turn value</span>
              <input
                type="number"
                value={turnDraft.turnValue}
                onChange={(event) => onTurnDraftChange({ turnValue: event.currentTarget.value })}
              />
            </label>
            <label className="field">
              <span>Priority</span>
              <input
                type="number"
                min="1"
                value={turnDraft.initiativePriority}
                onChange={(event) => onTurnDraftChange({ initiativePriority: event.currentTarget.value })}
              />
            </label>
            <button type="submit" disabled={isUpdatingTurn}>
              {isUpdatingTurn ? "Saving..." : "Save turn"}
            </button>
          </form>
        </article>

        {!isPlayerCharacter ? (
          <>
            <article className="combat-snapshot-control-block">
              <div>
                <p className="meta">Snapshot</p>
                <h3>Vitals</h3>
              </div>
              <p id="combat-vitals-editor-help" className="meta">
                Current and temp HP save for every combatant. NPC maximums appear when editable.
              </p>
              <div className="combat-summary-grid combat-summary-grid--snapshot">
                <form
                  className="combat-stat combat-stat--editable"
                  aria-describedby="combat-vitals-editor-help"
                  onSubmit={(event) => {
                    event.preventDefault();
                    onUpdateVitals(vitalsPayload());
                  }}
                >
                  <span className="meta">HP</span>
                  <div className="combat-inline-value">
                    <input
                      className="combat-stat-input combat-stat-input--number"
                      aria-label="DM Current HP"
                      aria-describedby="combat-vitals-editor-help"
                      type="number"
                      value={vitalsDraft.currentHp}
                      onChange={(event) => onVitalsDraftChange({ currentHp: event.currentTarget.value })}
                    />
                    <span className="combat-inline-divider">/</span>
                    <strong>{vitalsDraft.maxHp}</strong>
                  </div>
                </form>
                <form
                  className="combat-stat combat-stat--editable"
                  aria-describedby="combat-vitals-editor-help"
                  onSubmit={(event) => {
                    event.preventDefault();
                    onUpdateVitals(vitalsPayload());
                  }}
                >
                  <span className="meta">Temp HP</span>
                  <input
                    className="combat-stat-input combat-stat-input--single"
                    aria-label="DM Temp HP"
                    aria-describedby="combat-vitals-editor-help"
                    type="number"
                    min="0"
                    value={vitalsDraft.tempHp}
                    onChange={(event) => onVitalsDraftChange({ tempHp: event.currentTarget.value })}
                  />
                </form>
                <label className="field">
                  <span>Max HP</span>
                  <input
                    aria-label="DM Max HP"
                    aria-describedby="combat-vitals-editor-help"
                    type="number"
                    min="0"
                    value={vitalsDraft.maxHp}
                    onChange={(event) => onVitalsDraftChange({ maxHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Movement total</span>
                  <input
                    aria-label="DM Movement total"
                    aria-describedby="combat-vitals-editor-help"
                    type="number"
                    min="0"
                    value={vitalsDraft.movementTotal}
                    onChange={(event) => onVitalsDraftChange({ movementTotal: event.currentTarget.value })}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => onUpdateVitals(vitalsPayload())}
                  aria-label="Save DM vitals"
                  aria-describedby="combat-vitals-editor-help"
                  disabled={isUpdatingVitals}
                >
                  {isUpdatingVitals ? "Saving..." : "Save vitals"}
                </button>
              </div>
            </article>

            <article className="combat-snapshot-control-block">
              <div>
                <p className="meta">Round tools</p>
                <h3>Action Economy</h3>
              </div>
              <p id="combat-economy-editor-help" className="meta">
                Checked actions are available. Movement left saves with the action economy.
              </p>
              <form
                className="combat-resource-strip combat-inline-resource-form"
                aria-describedby="combat-economy-editor-help"
                onSubmit={(event) => {
                  event.preventDefault();
                  onUpdateResources({
                    expected_combatant_revision: selectedCombatant.combatant_revision,
                    movement_remaining: resourcesDraft.movementRemaining,
                    has_action: resourcesDraft.hasAction,
                    has_bonus_action: resourcesDraft.hasBonusAction,
                    has_reaction: resourcesDraft.hasReaction,
                  });
                }}
              >
                <label className="combat-stat">
                  <span className="meta">Move left</span>
                  <div className="combat-inline-value">
                    <input
                      className="combat-stat-input combat-stat-input--number"
                      aria-label="DM Movement Remaining"
                      aria-describedby="combat-economy-editor-help"
                      type="number"
                      min="0"
                      value={resourcesDraft.movementRemaining}
                      onChange={(event) => onResourcesDraftChange({ movementRemaining: event.currentTarget.value })}
                    />
                    <span className="combat-inline-divider">/</span>
                    <strong>{vitalsDraft.movementTotal}</strong>
                  </div>
                </label>
                <label className="combat-resource-toggle">
                  <input
                    type="checkbox"
                    checked={resourcesDraft.hasAction}
                    onChange={(event) => onResourcesDraftChange({ hasAction: event.currentTarget.checked })}
                  />
                  <span className="combat-resource">Action</span>
                </label>
                <label className="combat-resource-toggle">
                  <input
                    type="checkbox"
                    checked={resourcesDraft.hasBonusAction}
                    onChange={(event) => onResourcesDraftChange({ hasBonusAction: event.currentTarget.checked })}
                  />
                  <span className="combat-resource">Bonus action</span>
                </label>
                <label className="combat-resource-toggle">
                  <input
                    type="checkbox"
                    checked={resourcesDraft.hasReaction}
                    onChange={(event) => onResourcesDraftChange({ hasReaction: event.currentTarget.checked })}
                  />
                  <span className="combat-resource">Reaction</span>
                </label>
                <button type="submit" aria-describedby="combat-economy-editor-help" disabled={isUpdatingResources}>
                  {isUpdatingResources ? "Saving..." : "Save economy"}
                </button>
              </form>
            </article>
          </>
        ) : null}

        {hasNpcResourceReference ? (
          <article className="combat-snapshot-control-block combat-npc-resource-panel">
            <div>
              <p className="meta">Source</p>
              <h3>NPC Resources</h3>
            </div>
            {npcResourceCounters.length ? (
              <form
                className="combat-npc-resource-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!editableNpcResourceCounters.length) {
                    return;
                  }
                  onUpdateNpcResources({
                    expected_combatant_revision: selectedCombatant.combatant_revision,
                    counters: editableNpcResourceCounters.map((counter) => ({
                      resource_key: counter.resource_key,
                      current_value: npcResourceDrafts[counter.resource_key] ?? String(counter.current_value),
                    })),
                  });
                }}
              >
                <div className="combat-npc-resource-list">
                  {npcResourceCounters.map((counter) => (
                    <label className="combat-npc-resource-row" key={counter.resource_key}>
                      <span className="combat-npc-resource-row__identity">
                        <strong>{counter.label}</strong>
                        <span className="meta">
                          {[counter.reset_label, counter.source_label].filter(Boolean).join(" | ")}
                        </span>
                      </span>
                      <span className="combat-npc-resource-row__value">
                        <input
                          aria-label={`${counter.label} current uses`}
                          type="number"
                          min="0"
                          max={counter.max_value}
                          value={npcResourceDrafts[counter.resource_key] ?? String(counter.current_value)}
                          disabled={!counter.can_edit || isUpdatingNpcResources}
                          onChange={(event) => onNpcResourceDraftChange(counter.resource_key, event.currentTarget.value)}
                        />
                        <span className="combat-inline-divider">/</span>
                        <strong>{counter.max_value}</strong>
                      </span>
                    </label>
                  ))}
                </div>
                {editableNpcResourceCounters.length ? (
                  <button type="submit" disabled={isUpdatingNpcResources}>
                    {isUpdatingNpcResources ? "Saving..." : "Save NPC resources"}
                  </button>
                ) : null}
              </form>
            ) : null}
            {npcResourceNotes.length ? (
              <div className="combat-npc-resource-notes" aria-label="Unsupported source mechanics">
                {npcResourceNotes.map((note) => (
                  <div className="combat-npc-resource-note" key={`${note.label}-${note.note}`}>
                    <strong>{note.label}</strong>
                    <p className="meta">{note.note}</p>
                    {note.source_label ? <span className="meta">{note.source_label}</span> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ) : null}

        <article className="combat-snapshot-control-block">
          <datalist id="gen2-combat-condition-options">
            {conditionOptions.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
          <section className="combat-conditions combat-conditions--compact combat-status-conditions">
            <div className="section-heading">
              <h3>Conditions</h3>
              <details className="combat-condition-editor combat-condition-editor--add">
                <summary>Add condition</summary>
                <form
                  className="combat-condition-editor__form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    onAddCondition(conditionDraft);
                  }}
                >
                  <label className="field">
                    <span>Condition</span>
                    <input
                      type="text"
                      list="gen2-combat-condition-options"
                      value={conditionDraft.name}
                      onChange={(event) => onConditionDraftChange({ name: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Duration</span>
                    <input
                      type="text"
                      value={conditionDraft.durationText}
                      onChange={(event) => onConditionDraftChange({ durationText: event.currentTarget.value })}
                    />
                  </label>
                  <button type="submit" disabled={isAddingCondition}>
                    {isAddingCondition ? "Adding..." : "Add condition"}
                  </button>
                </form>
              </details>
            </div>
            {selectedCombatant.conditions.length ? (
              <div className="combat-condition-list">
                {selectedCombatant.conditions.map((condition) => (
                  <div className="combat-condition-item" key={condition.id}>
                    <div>
                      <strong>{condition.name}</strong>
                      {condition.duration_text ? <p className="meta">{condition.duration_text}</p> : null}
                    </div>
                    <div className="combat-condition-actions">
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => onDeleteCondition(condition)}
                        disabled={isDeletingCondition}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="meta">No conditions are active on this combatant.</p>
            )}
          </section>
        </article>
      </section>

      <section className="combat-snapshot-control-block combat-danger-card">
        <div>
          <p className="meta">Cleanup</p>
          <h3>Selected combatant</h3>
        </div>
        <form
          className="confirmed-action"
          onSubmit={(event) => {
            event.preventDefault();
            onDeleteCombatant();
            setDeleteCombatantConfirmed(false);
          }}
        >
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={deleteCombatantConfirmed}
              disabled={isDeletingCombatant}
              onChange={(event) => setDeleteCombatantConfirmed(event.currentTarget.checked)}
            />
            Confirm removal
          </label>
          <button
            type="submit"
            className="ghost-button"
            disabled={!deleteCombatantConfirmed || isDeletingCombatant}
            aria-describedby={removeCombatantHint ? "combat-remove-combatant-hint" : undefined}
          >
            {isDeletingCombatant ? "Removing..." : "Remove selected combatant"}
          </button>
          {removeCombatantHint ? (
            <p id="combat-remove-combatant-hint" className="meta">
              {removeCombatantHint}
            </p>
          ) : null}
        </form>
      </section>
    </>
  );
}
