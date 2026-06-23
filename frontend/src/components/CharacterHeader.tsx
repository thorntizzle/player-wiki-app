import type { CharacterDetailResponse } from "../api/types";

type CharacterHeaderLinks = NonNullable<CharacterDetailResponse["links"]>;

export function CharacterHeader({
  detailLinks,
  detailProgressionRepairUrl,
  embeddedHeaderDetails,
  hasReadHeaderManagementActions,
  isCombatSurface,
  isReadSurface,
  selectedCharacterSheetUrl,
  selectedName,
  surfaceHeading,
  surfaceMetaLabel,
}: {
  detailLinks: CharacterHeaderLinks;
  detailProgressionRepairUrl?: string;
  embeddedHeaderDetails: string[];
  hasReadHeaderManagementActions: boolean;
  isCombatSurface: boolean;
  isReadSurface: boolean;
  selectedCharacterSheetUrl: string;
  selectedName?: string | null;
  surfaceHeading: string;
  surfaceMetaLabel: string;
}) {
  if (isReadSurface) {
    return (
      <header className="character-header">
        <div className="character-header__top">
          <div className="character-header__identity">
            <p className="eyebrow">Character sheet</p>
            <h1>{selectedName || surfaceHeading}</h1>
          </div>
          {hasReadHeaderManagementActions ? (
            <div className="character-header__actions">
              {detailLinks.advanced_editor_url ? (
                <a className="ghost-button" href={detailLinks.advanced_editor_url}>
                  Advanced Editor
                </a>
              ) : null}
              {detailLinks.retraining_url ? (
                <a className="ghost-button" href={detailLinks.retraining_url}>
                  Retraining
                </a>
              ) : null}
              {detailLinks.level_up_url ? (
                <a className="ghost-button" href={detailLinks.level_up_url}>
                  Level up
                </a>
              ) : null}
              {detailProgressionRepairUrl ? (
                <a className="ghost-button" href={detailProgressionRepairUrl}>
                  {detailLinks.progression_repair_url ? "Progression repair" : "Prepare for level-up"}
                </a>
              ) : null}
              {detailLinks.cultivation_url ? (
                <a className="ghost-button" href={detailLinks.cultivation_url}>
                  Cultivation
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>
    );
  }

  return (
    <header className="character-header">
      <div className="character-header__top">
        <div className="character-header__identity">
          <p className="eyebrow">{surfaceMetaLabel}</p>
          <h2>{selectedName || surfaceHeading}</h2>
          {embeddedHeaderDetails.length ? <p className="lede">{embeddedHeaderDetails.join(" | ")}</p> : null}
        </div>
        {selectedCharacterSheetUrl ? (
          <div className="hero-actions">
            <a href={selectedCharacterSheetUrl} className="ghost-button">
              {isCombatSurface ? "Open full sheet" : "Open full character page"}
            </a>
          </div>
        ) : null}
      </div>
    </header>
  );
}
