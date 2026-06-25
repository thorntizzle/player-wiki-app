import type { CharacterPortrait, CharacterSummary } from "../api/types";

export function CharacterSummaryCard({
  selected,
  selectedPortrait,
}: {
  selected: CharacterSummary;
  selectedPortrait: CharacterPortrait | null;
}) {
  const identityDetails = [selected.class_level_text, selected.species, selected.background].filter(Boolean);

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
          {identityDetails.length ? <p>{identityDetails.join(" | ")}</p> : null}
        </div>
      </div>
    </article>
  );
}
