import type { ReactNode } from "react";
import type { CharacterPortrait, CharacterSummary } from "../api/types";

export function CharacterSummaryCard({
  children,
  currentHp,
  maxHp,
  selected,
  selectedPortrait,
  systemLabel,
  tempHp,
}: {
  children?: ReactNode;
  currentHp: number;
  maxHp: number;
  selected: CharacterSummary;
  selectedPortrait: CharacterPortrait | null;
  systemLabel: string;
  tempHp: number;
}) {
  return (
    <article className="character-summary">
      <div className="character-summary__main">
        {selectedPortrait ? (
          <figure className="character-portrait">
            <img src={selectedPortrait.url} alt={selectedPortrait.alt_text || selected.name} />
            {selectedPortrait.caption ? <figcaption className="meta">{selectedPortrait.caption}</figcaption> : null}
          </figure>
        ) : null}
        <div>
          <h3>{selected.name}</h3>
          <p>
            HP: {currentHp} / {maxHp}
          </p>
          <p>Temp HP: {tempHp}</p>
          {selected.hit_dice?.value ? <p>Hit Dice: {selected.hit_dice.value}</p> : null}
          <p>Class: {selected.class_level_text || "Unknown"}</p>
          <p>System: {systemLabel}</p>
        </div>
      </div>
      {selected.resource_preview?.length ? (
        <ul className="plain-list resource-preview-list">
          {selected.resource_preview.map((resource) => (
            <li key={`${resource.label}-${resource.value}`}>
              <span>{resource.label}</span>
              <strong>{resource.value}</strong>
            </li>
          ))}
        </ul>
      ) : null}
      {children}
    </article>
  );
}
