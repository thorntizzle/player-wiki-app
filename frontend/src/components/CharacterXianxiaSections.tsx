import type { ComponentProps } from "react";

import { CharacterPersonalSection } from "./CharacterPersonalSection";
import { CharacterXianxiaEquipmentSection } from "./CharacterXianxiaEquipmentSection";
import { CharacterXianxiaInventorySection } from "./CharacterXianxiaInventorySection";
import { CharacterXianxiaMartialArtsSection } from "./CharacterXianxiaMartialArtsSection";
import { CharacterXianxiaQuickReferenceSection } from "./CharacterXianxiaQuickReferenceSection";
import { CharacterXianxiaResourcesSection } from "./CharacterXianxiaResourcesSection";
import { CharacterXianxiaSkillsSection } from "./CharacterXianxiaSkillsSection";
import { CharacterXianxiaTechniquesSection } from "./CharacterXianxiaTechniquesSection";
import type { CharacterSection } from "../characterPaneUtils";

type CharacterXianxiaQuickReferenceProps = ComponentProps<typeof CharacterXianxiaQuickReferenceSection>;
type CharacterXianxiaMartialArtsProps = ComponentProps<typeof CharacterXianxiaMartialArtsSection>;
type CharacterXianxiaTechniquesProps = ComponentProps<typeof CharacterXianxiaTechniquesSection>;
type CharacterXianxiaResourcesProps = ComponentProps<typeof CharacterXianxiaResourcesSection>;
type CharacterXianxiaSkillsProps = ComponentProps<typeof CharacterXianxiaSkillsSection>;
type CharacterXianxiaEquipmentProps = ComponentProps<typeof CharacterXianxiaEquipmentSection>;
type CharacterXianxiaInventoryProps = ComponentProps<typeof CharacterXianxiaInventorySection>;
type CharacterPersonalProps = ComponentProps<typeof CharacterPersonalSection>;

interface CharacterXianxiaSectionsProps {
  activeCharacterSection: CharacterSection;
  quickReference: CharacterXianxiaQuickReferenceProps;
  martialArts: CharacterXianxiaMartialArtsProps;
  techniques: CharacterXianxiaTechniquesProps;
  resources: CharacterXianxiaResourcesProps;
  skills: CharacterXianxiaSkillsProps;
  equipment: CharacterXianxiaEquipmentProps;
  inventory: CharacterXianxiaInventoryProps;
  personal: CharacterPersonalProps;
}

export function CharacterXianxiaSections({
  activeCharacterSection,
  quickReference,
  martialArts,
  techniques,
  resources,
  skills,
  equipment,
  inventory,
  personal,
}: CharacterXianxiaSectionsProps) {
  return (
    <>
      {activeCharacterSection === "quick-reference" ? <CharacterXianxiaQuickReferenceSection {...quickReference} /> : null}
      {activeCharacterSection === "martial-arts" ? <CharacterXianxiaMartialArtsSection {...martialArts} /> : null}
      {activeCharacterSection === "techniques" ? <CharacterXianxiaTechniquesSection {...techniques} /> : null}
      {activeCharacterSection === "resources" ? <CharacterXianxiaResourcesSection {...resources} /> : null}
      {activeCharacterSection === "skills" ? <CharacterXianxiaSkillsSection {...skills} /> : null}
      {activeCharacterSection === "equipment" ? <CharacterXianxiaEquipmentSection {...equipment} /> : null}
      {activeCharacterSection === "inventory" ? <CharacterXianxiaInventorySection {...inventory} /> : null}
      {activeCharacterSection === "personal" ? <CharacterPersonalSection {...personal} /> : null}
    </>
  );
}
