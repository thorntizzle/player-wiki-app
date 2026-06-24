import type { CharacterSection } from "../characterPaneUtils";

type CharacterEmbeddedSection = {
  id: CharacterSection;
  label: string;
};

export function CharacterEmbeddedSectionNav({
  activeCharacterSection,
  selectCharacterSection,
  sections,
  variant,
}: {
  activeCharacterSection: CharacterSection;
  selectCharacterSection: (section: CharacterSection) => void;
  sections: CharacterEmbeddedSection[];
  variant: "dnd" | "xianxia";
}) {
  if (variant === "dnd") {
    return (
      <nav className="combat-workspace-nav session-character-section-nav" aria-label="Session character sections">
        {sections.map((section) => {
          const isActive = activeCharacterSection === section.id;
          return (
            <button
              key={section.id}
              type="button"
              className={`ghost-button combat-workspace-button${isActive ? " combat-workspace-button--active" : ""}`}
              aria-pressed={isActive}
              aria-current={isActive ? "page" : undefined}
              onClick={() => selectCharacterSection(section.id)}
            >
              {section.label}
            </button>
          );
        })}
      </nav>
    );
  }

  return (
    <div className="character-subpage-nav-card">
      <nav className="character-subpage-nav" aria-label="Character subpages">
        {sections.map((section) => {
          const isActive = activeCharacterSection === section.id;
          return (
            <button
              key={section.id}
              type="button"
              className={isActive ? "button-link" : "ghost-button"}
              aria-pressed={isActive}
              aria-current={isActive ? "page" : undefined}
              onClick={() => selectCharacterSection(section.id)}
            >
              {section.label}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
