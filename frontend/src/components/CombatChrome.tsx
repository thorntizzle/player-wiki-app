import type { CombatantSummary } from "../api/types";
import { readNumber } from "../characterValueUtils";

export type CombatView = "player" | "status" | "controls";

interface CombatViewSwitchProps {
  effectiveCombatView: CombatView;
  onSelect: (view: CombatView) => void;
}

export function CombatViewSwitch({ effectiveCombatView, onSelect }: CombatViewSwitchProps) {
  return (
    <nav aria-label="DM encounter subview">
      {[
        { id: "status" as CombatView, label: "DM status", activeClass: "button-link", inactiveClass: "ghost-button" },
        { id: "controls" as CombatView, label: "Controls", activeClass: "button-link", inactiveClass: "ghost-button" },
      ].map((view) => (
        <button
          type="button"
          key={view.id}
          className={effectiveCombatView === view.id ? view.activeClass : view.inactiveClass}
          onClick={() => onSelect(view.id)}
          aria-pressed={effectiveCombatView === view.id}
        >
          {view.label}
        </button>
      ))}
    </nav>
  );
}

interface CombatSummaryBandProps {
  roundNumber: number | null | undefined;
  currentTurnLabel: string | null | undefined;
  combatantCount: number | null | undefined;
}

export function CombatSummaryBand({ roundNumber, currentTurnLabel, combatantCount }: CombatSummaryBandProps) {
  return (
    <section className="combat-summary-band" aria-label="Encounter summary">
      <article>
        <span className="meta">Round</span>
        <strong>{roundNumber ?? 1}</strong>
      </article>
      <article>
        <span className="meta">Current turn</span>
        <strong>{currentTurnLabel || "None"}</strong>
      </article>
      <article>
        <span className="meta">Combatants</span>
        <strong>{combatantCount ?? 0}</strong>
      </article>
    </section>
  );
}

interface CombatantCarouselProps {
  combatants: CombatantSummary[];
  selectedCombatantId: number | null | undefined;
  onSelectCombatant: (combatantId: number) => void;
}

function CombatantCard({
  combatant,
  isSelected,
  onSelect,
}: {
  combatant: CombatantSummary;
  isSelected: boolean;
  onSelect: (combatantId: number) => void;
}) {
  return (
    <button
      type="button"
      className={isSelected ? "combatant-card combatant-card--selected" : "combatant-card"}
      onClick={() => onSelect(combatant.id)}
      aria-pressed={isSelected}
    >
      <span className="combatant-card__topline">
        <strong>{combatant.name}</strong>
        {combatant.is_current_turn ? <span className="pill">Current</span> : null}
      </span>
      <span className="meta">{combatant.subtitle || combatant.type_label}</span>
      <span className="combatant-card__stats">
        <span>Turn {combatant.turn_value}</span>
        {combatant.show_detail ? (
          <span>
            HP {readNumber(combatant.current_hp)} / {readNumber(combatant.max_hp)}
            {readNumber(combatant.temp_hp) ? ` +${readNumber(combatant.temp_hp)} temp` : ""}
          </span>
        ) : (
          <span>Hidden detail</span>
        )}
      </span>
      {combatant.conditions.length ? (
        <span className="combatant-card__conditions">
          {combatant.conditions.map((condition) => condition.name).join(", ")}
        </span>
      ) : null}
    </button>
  );
}

export function CombatantCarousel({
  combatants,
  selectedCombatantId,
  onSelectCombatant,
}: CombatantCarouselProps) {
  return (
    <section className="combat-carousel" aria-label="Combatant carousel">
      <div className="section-heading">
        <div>
          <h2>Turn Order</h2>
          <p className="meta">Initiative is pinned here while the main panel shows your tracked character.</p>
        </div>
      </div>
      <div className="combat-carousel-track">
        {combatants.map((combatant) => (
          <CombatantCard
            key={combatant.id}
            combatant={combatant}
            isSelected={selectedCombatantId === combatant.id}
            onSelect={onSelectCombatant}
          />
        ))}
      </div>
      <div className="combat-turn-order-jump">
        <label className="combat-turn-order-jump__label" htmlFor="combat-turn-order-jump-select">
          Jump to combatant
        </label>
        <select
          id="combat-turn-order-jump-select"
          className="combat-turn-order-jump__select"
          value={selectedCombatantId ?? ""}
          onChange={(event) => onSelectCombatant(Number(event.currentTarget.value))}
        >
          {combatants.map((combatant) => (
            <option key={combatant.id} value={combatant.id}>
              {combatant.name} - turn {combatant.turn_value}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}
