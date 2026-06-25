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
  selectedCharacterSheetUrl = "",
  selectedSlug,
  showCharacterSheetLink = false,
  visibleCharacterSections,
}: {
  activeCharacterSection: CharacterSection;
  characterList: CharacterSummary[];
  handleReadSurfaceSectionNavClick: (section: CharacterSection) => (event: MouseEvent<HTMLAnchorElement>) => void;
  isReadSurface: boolean;
  readSurfaceSectionUrl: (section: CharacterSection) => string;
  selectCharacter: (nextSlug: string | null) => void;
  selectedCharacterSheetUrl?: string;
  selectedSlug: string | null;
  showCharacterSheetLink?: boolean;
  visibleCharacterSections: CharacterNavigationSection[];
}) {
  return (
    <div
      className={isReadSurface ? "character-subpage-nav-card" : "character-selector-card"}
      data-character-subpage-nav-card={isReadSurface ? "" : undefined}
    >
      {isReadSurface ? (
        <nav className="character-subpage-nav" aria-label="Character subpages">
          {visibleCharacterSections.map((section) => {
            const isActive = activeCharacterSection === section.id;
            return (
              <a
                key={section.id}
                href={readSurfaceSectionUrl(section.id)}
                className={isActive ? "button-link" : "ghost-button"}
                aria-current={isActive ? "page" : undefined}
                data-character-read-subpage-link
                data-character-read-target-subpage={section.id}
                onClick={handleReadSurfaceSectionNavClick(section.id)}
              >
                {section.label}
              </a>
            );
          })}
        </nav>
      ) : (
        <div className="character-selector-row">
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
          {showCharacterSheetLink && selectedCharacterSheetUrl ? (
            <a href={selectedCharacterSheetUrl} className="ghost-button">
              Open full character page
            </a>
          ) : null}
        </div>
      )}
    </div>
  );
}
