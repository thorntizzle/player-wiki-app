import type { ComponentProps } from "react";

import { CharacterDndAbilitySkillsSection } from "./CharacterDndAbilitySkillsSection";
import { CharacterDndEquipmentSection } from "./CharacterDndEquipmentSection";
import { CharacterDndInventorySection } from "./CharacterDndInventorySection";
import { CharacterDndOverviewSection } from "./CharacterDndOverviewSection";
import { CharacterDndResourcesSection } from "./CharacterDndResourcesSection";
import { CharacterDndSpellsSection } from "./CharacterDndSpellsSection";
import type { CharacterSection } from "../characterPaneUtils";

type CharacterDndOverviewProps = ComponentProps<typeof CharacterDndOverviewSection>;
type CharacterDndResourcesProps = ComponentProps<typeof CharacterDndResourcesSection>;
type CharacterDndSpellsProps = ComponentProps<typeof CharacterDndSpellsSection>;
type CharacterDndEquipmentProps = ComponentProps<typeof CharacterDndEquipmentSection>;
type CharacterDndInventoryProps = ComponentProps<typeof CharacterDndInventorySection>;
type CharacterDndAbilitySkillsProps = ComponentProps<typeof CharacterDndAbilitySkillsSection>;

interface CharacterDndSectionsProps {
  activeCharacterSection: CharacterSection;
  overview: CharacterDndOverviewProps;
  resources: CharacterDndResourcesProps;
  spells: CharacterDndSpellsProps;
  equipment: CharacterDndEquipmentProps;
  inventory: CharacterDndInventoryProps;
  abilitySkills: CharacterDndAbilitySkillsProps;
}

export function CharacterDndSections({
  activeCharacterSection,
  overview,
  resources,
  spells,
  equipment,
  inventory,
  abilitySkills,
}: CharacterDndSectionsProps) {
  return (
    <>
      {activeCharacterSection === "overview" ? <CharacterDndOverviewSection {...overview} /> : null}
      {activeCharacterSection === "resources" ? <CharacterDndResourcesSection {...resources} /> : null}
      {activeCharacterSection === "spells" ? <CharacterDndSpellsSection {...spells} /> : null}
      {activeCharacterSection === "equipment" ? <CharacterDndEquipmentSection {...equipment} /> : null}
      {activeCharacterSection === "inventory" ? <CharacterDndInventorySection {...inventory} /> : null}
      {activeCharacterSection === "abilities" ? <CharacterDndAbilitySkillsSection {...abilitySkills} /> : null}
    </>
  );
}
