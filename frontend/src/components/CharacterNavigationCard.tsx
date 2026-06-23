import type { MouseEvent } from "react";
import type { CharacterSummary } from "../api/types";
import type { CharacterSection } from "../characterPaneUtils";

type CharacterNavigationSection = {
  id: CharacterSection;
  label: string;
};

export function CharacterNavigationCard({
  activeCharacterSection,
  characterList,
  handleReadSurfaceSectionNavClick,
  isReadSurface,
  readSurfaceSectionUrl,
  selectCharacter,
  selectedSlug,
  visibleCharacterSections,
}: {
  activeCharacterSection: CharacterSection;
  characterList: CharacterSummary[];
  handleReadSurfaceSectionNavClick: (section: CharacterSection) => (event: MouseEvent<HTMLAnchorElement>) => void;
  isReadSurface: boolean;
  readSurfaceSectionUrl: (section: CharacterSection) => string;
  selectCharacter: (nextSlug: string | null) => void;
  selectedSlug: string | null;
  visibleCharacterSections: CharacterNavigationSection[];
}) {
  return (
    <div
      className={isReadSurface ? "character-subpage-nav-card" : "character-selector-card"}
      data-character-subpage-nav-card={isReadSurface ? "" : undefined}
    >
      {isReadSurface ? (
        <nav className="character-subpage-nav" aria-label="Character subpages">
          {visibleCharacterSections.map((section) => (
            <a
              key={section.id}
              href={readSurfaceSectionUrl(section.id)}
              className={activeCharacterSection === section.id ? "button-link" : "ghost-button"}
              data-character-read-subpage-link
              data-character-read-target-subpage={section.id}
              onClick={handleReadSurfaceSectionNavClick(section.id)}
            >
              {section.label}
            </a>
          ))}
        </nav>
      ) : (
        <label className="field" htmlFor="character-selector">
          <span>Character</span>
          <select
            id="character-selector"
            value={selectedSlug || ""}
            onChange={(event) => {
              selectCharacter(event.currentTarget.value || null);
            }}
          >
            {characterList.map((item) => (
              <option key={item.slug} value={item.slug}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
