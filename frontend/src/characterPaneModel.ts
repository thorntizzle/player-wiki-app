import type { CharacterPresentedInventoryItem, CharacterRecord } from "./api/types";
import { asRecord, asRecordArray, readString } from "./characterValueUtils";
import { collectPresentedSpells, groupSpellsByLevel } from "./characterPaneUtils";

export function buildCharacterPaneModel(
  character: CharacterRecord | undefined,
  { isXianxia }: { isXianxia: boolean },
) {
  const definition = asRecord(character?.definition);
  const stats = asRecord(definition.stats);
  const spellcasting = asRecord(definition.spellcasting);
  const state = asRecord(character?.state_record.state);
  const overviewStatRowPayload = character?.overview_stat_rows;
  const rawOverviewStatRows = Array.isArray(overviewStatRowPayload) ? overviewStatRowPayload : [];
  const overviewStatRows = rawOverviewStatRows.map((row) => asRecordArray(row));
  const overviewStats = asRecordArray(character?.overview_stats);
  const xianxiaState = asRecord(state.xianxia);
  const vitals = asRecord(state.vitals);
  const resources = asRecordArray(state.resources);
  const spellSlots = asRecordArray(state.spell_slots);
  const inventory = asRecordArray(state.inventory);
  const currency = isXianxia ? asRecord(xianxiaState.currency) : asRecord(state.currency);
  const playerNotesHtml = readString(character?.player_notes_html);
  const physicalDescriptionHtml = readString(character?.physical_description_html);
  const personalBackgroundHtml = readString(character?.personal_background_html);
  const referenceSections = asRecordArray(character?.reference_sections);
  const dndAbilities = asRecordArray(character?.abilities);
  const dndSkills = asRecordArray(character?.skills);
  const dndProficiencyGroups = asRecordArray(character?.proficiency_groups);
  const hasDndAbilitySkillsContent = Boolean(
    dndAbilities.length || dndSkills.length || dndProficiencyGroups.length,
  );
  const spells = asRecordArray(spellcasting.spells);
  const equipmentState = character?.equipment_state;
  const equipmentRows = equipmentState?.rows ?? [];
  const arcaneArmorState = character?.arcane_armor_state ?? equipmentState?.arcane_armor_state;
  const presentedXianxia = character?.presented_xianxia ?? {};
  const presentedSpells = collectPresentedSpells(character);
  const presentedSpellGroups = groupSpellsByLevel(presentedSpells, (spell) => spell.level_label);
  const rawSpellGroups = groupSpellsByLevel(spells, (spell) => readString(spell.level_label));
  const presentedInventory = character?.presented_inventory ?? [];
  const presentedInventoryByKey = buildPresentedInventoryLookup(presentedInventory);

  return {
    arcaneArmorState,
    currency,
    dndAbilities,
    dndProficiencyGroups,
    dndSkills,
    equipmentRows,
    equipmentState,
    hasDndAbilitySkillsContent,
    hasOverviewStatRows: rawOverviewStatRows.length > 0,
    inventory,
    overviewStatRows,
    overviewStats,
    personalBackgroundHtml,
    physicalDescriptionHtml,
    playerNotesHtml,
    presentedInventoryByKey,
    presentedSpellGroups,
    presentedSpells,
    presentedXianxia,
    rawSpellGroups,
    referenceSections,
    resources,
    spellcasting,
    spells,
    spellSlots,
    stats,
    vitals,
  };
}

function buildPresentedInventoryLookup(presentedInventory: CharacterPresentedInventoryItem[]) {
  const lookup = new Map<string, CharacterPresentedInventoryItem>();
  for (const item of presentedInventory) {
    for (const key of [item.id, item.item_ref]) {
      if (key) {
        lookup.set(key, item);
      }
    }
  }
  return lookup;
}
