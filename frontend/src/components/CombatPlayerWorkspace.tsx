import { Fragment } from "react";

import type {
  CombatCharacterWorkspaceSection,
  CombatResourcesPatchPayload,
  CombatantSummary,
  CombatPlayerCharacterTarget,
} from "../api/types";
import { CombatCharacterSections } from "./CombatCharacterSections";
import { CharacterPane } from "../pages/CharacterPane";
import { readNumber } from "../characterValueUtils";

interface CombatVitalsDraft {
  movementTotal: string;
}

interface CombatResourcesDraft {
  movementRemaining: string;
  hasAction: boolean;
  hasBonusAction: boolean;
  hasReaction: boolean;
}

interface CombatPlayerWorkspaceProps {
  campaignSlug: string;
  selectedCharacterSlug: string | null;
  selectedCombatant: CombatantSummary | null;
  playerCharacterTargets: CombatPlayerCharacterTarget[];
  showTargetList?: boolean;
  showEmbeddedCharacterSelector?: boolean;
  combatSections: CombatCharacterWorkspaceSection[];
  vitalsDraft: CombatVitalsDraft;
  resourcesDraft: CombatResourcesDraft;
  isUpdatingResources: boolean;
  onSelectCombatant: (combatantId: number) => void;
  onSelectedCharacterChange: (characterSlug: string) => void;
  onResourcesDraftChange: (updates: Partial<CombatResourcesDraft>) => void;
  onUpdateResources: (combatant: CombatantSummary, payload: CombatResourcesPatchPayload) => void;
}

function CombatCharacterTacticalControls({
  selectedCombatant,
  vitalsDraft,
  resourcesDraft,
  isUpdatingResources,
  onResourcesDraftChange,
  onUpdateResources,
}: {
  selectedCombatant: CombatantSummary | null;
  vitalsDraft: CombatVitalsDraft;
  resourcesDraft: CombatResourcesDraft;
  isUpdatingResources: boolean;
  onResourcesDraftChange: (updates: Partial<CombatResourcesDraft>) => void;
  onUpdateResources: (combatant: CombatantSummary, payload: CombatResourcesPatchPayload) => void;
}) {
  if (!selectedCombatant?.show_detail || !selectedCombatant.can_edit_resources) {
    return null;
  }

  const movementTotal = vitalsDraft.movementTotal || String(readNumber(selectedCombatant.movement_total));

  return (
    <section className="combat-character-tactical-controls" aria-label="Combat movement and action controls">
      <div>
        <p className="meta">Combat controls</p>
        <h3>Movement and Action Economy</h3>
      </div>
      <form
        className="combat-resource-strip combat-inline-resource-form"
        onSubmit={(event) => {
          event.preventDefault();
          onUpdateResources(selectedCombatant, {
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
              aria-label="Combat Movement Remaining"
              type="number"
              min="0"
              value={resourcesDraft.movementRemaining}
              onChange={(event) => onResourcesDraftChange({ movementRemaining: event.currentTarget.value })}
            />
            <span className="combat-inline-divider">/</span>
            <strong>{movementTotal}</strong>
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
        <button type="submit" disabled={isUpdatingResources}>
          {isUpdatingResources ? "Saving..." : "Save economy"}
        </button>
      </form>
    </section>
  );
}

export function CombatPlayerWorkspace({
  campaignSlug,
  selectedCharacterSlug,
  selectedCombatant,
  playerCharacterTargets,
  showTargetList = false,
  showEmbeddedCharacterSelector = false,
  combatSections,
  vitalsDraft,
  resourcesDraft,
  isUpdatingResources,
  onSelectCombatant,
  onSelectedCharacterChange,
  onResourcesDraftChange,
  onUpdateResources,
}: CombatPlayerWorkspaceProps) {
  const hasCombatWorkspaceContent =
    Boolean(selectedCombatant?.can_edit_resources) || combatSections.some((section) => section.slug);

  return (
    <section className="combat-pc-workspace">
      {showTargetList && playerCharacterTargets.length ? (
        <div className="section-heading combat-character-target-heading">
          <div className="combat-target-list">
            {playerCharacterTargets.map((target) => (
              <Fragment key={target.combatant_id}>
                <button
                  type="button"
                  className={target.is_selected ? "button-link" : "ghost-button"}
                  onClick={() => onSelectCombatant(target.combatant_id)}
                >
                  {target.name}
                </button>
                {target.subtitle ? <p className="meta">{target.subtitle}</p> : null}
              </Fragment>
            ))}
          </div>
        </div>
      ) : null}
      {selectedCharacterSlug ? (
        <CharacterPane
          key={selectedCharacterSlug}
          campaignSlug={campaignSlug}
          combatWorkspaceContent={
            hasCombatWorkspaceContent ? (
              <>
                <CombatCharacterTacticalControls
                  selectedCombatant={selectedCombatant}
                  vitalsDraft={vitalsDraft}
                  resourcesDraft={resourcesDraft}
                  isUpdatingResources={isUpdatingResources}
                  onResourcesDraftChange={onResourcesDraftChange}
                  onUpdateResources={onUpdateResources}
                />
                <CombatCharacterSections sections={combatSections} />
              </>
            ) : null
          }
          initialCharacterSlug={selectedCharacterSlug}
          showEmbeddedCharacterSelector={showEmbeddedCharacterSelector}
          surface="combat"
          onSelectedCharacterChange={onSelectedCharacterChange}
        />
      ) : (
        <section className="card auth-card">
          <h2>No tracked player character available</h2>
          <p>
            There is not currently a tracked player character you can open from combat.
            Once a DM adds your character to the tracker, it will appear here.
          </p>
        </section>
      )}
    </section>
  );
}
