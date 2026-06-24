import { Fragment } from "react";

import type { CombatantSummary, CombatPlayerCharacterTarget } from "../api/types";
import { CharacterPane } from "../pages/CharacterPane";

interface CombatPlayerWorkspaceProps {
  campaignSlug: string;
  selectedCharacterSlug: string | null;
  selectedPlayerCharacter: CombatantSummary | null;
  playerCharacterTargets: CombatPlayerCharacterTarget[];
  onSelectCombatant: (combatantId: number) => void;
  onSelectedCharacterChange: (characterSlug: string) => void;
}

export function CombatPlayerWorkspace({
  campaignSlug,
  selectedCharacterSlug,
  selectedPlayerCharacter,
  playerCharacterTargets,
  onSelectCombatant,
  onSelectedCharacterChange,
}: CombatPlayerWorkspaceProps) {
  return (
    <section className="combat-pc-workspace">
      <div className="section-heading">
        <div>
          <p className="meta">Selected PC workspace</p>
          <h2>{selectedPlayerCharacter?.name ?? "No tracked PC in combat"}</h2>
        </div>
        {playerCharacterTargets.length ? (
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
        ) : null}
      </div>
      {selectedCharacterSlug ? (
        <CharacterPane
          campaignSlug={campaignSlug}
          initialCharacterSlug={selectedCharacterSlug}
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
