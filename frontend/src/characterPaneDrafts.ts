import type { CharacterRecord } from "./api/types";
import { asRecord, asRecordArray, readNumber, readString } from "./characterValueUtils";
import {
  draftKey,
  isXianxiaCharacter,
  xianxiaDaoUseRecordDraftKey,
  xianxiaInventoryDraftFromItem,
  type CharacterXianxiaInventoryDraft,
} from "./characterPaneUtils";
import type { EmbeddedImageInput } from "./sessionArticleDrafts";

export interface CharacterVitalsDraft {
  expectedRevision: number;
  currentHp: string;
  tempHp: string;
}

export interface CharacterXianxiaVitalsDraft extends CharacterVitalsDraft {
  currentStance: string;
  tempStance: string;
  currentJing: string;
  currentQi: string;
  currentShen: string;
  currentYin: string;
  currentYang: string;
  currentDao: string;
}

export type CharacterXianxiaVitalsField = Exclude<keyof CharacterXianxiaVitalsDraft, "expectedRevision">;

export interface CharacterXianxiaActiveStateDraft {
  expectedRevision: number;
  activeStanceName: string;
  activeAuraName: string;
}

export interface CharacterXianxiaDaoUseRequestDraft {
  requestName: string;
  notes: string;
  preparedRecordIndex: string;
}

export interface CharacterNotesDraft {
  expectedRevision: number;
  notes: string;
}

export interface CharacterEquipmentDraft {
  isEquipped: boolean;
  isAttuned: boolean;
  weaponWieldMode: string;
}

export interface CharacterPortraitDraft {
  file: EmbeddedImageInput | null;
  fileName: string;
  altText: string;
  caption: string;
}

export interface CharacterControlsDraft {
  assignedUserId: string;
  deleteConfirmation: string;
}

export interface CharacterPaneDraftSnapshot {
  vitalsDraft: CharacterVitalsDraft;
  xianxiaVitalsDraft: CharacterXianxiaVitalsDraft;
  xianxiaActiveDraft: CharacterXianxiaActiveStateDraft;
  notesDraft: CharacterNotesDraft;
  resourceDrafts: Record<string, string>;
  spellSlotDrafts: Record<string, string>;
  inventoryDrafts: Record<string, string>;
  equipmentDrafts: Record<string, CharacterEquipmentDraft>;
  xianxiaInventoryDrafts: Record<string, CharacterXianxiaInventoryDraft>;
  xianxiaDaoUseNotesDrafts: Record<string, string>;
  arcaneArmorEnabled: boolean;
  currencyDraft: Record<string, string>;
  portraitDraft: CharacterPortraitDraft;
  controlsDraft: CharacterControlsDraft;
}

export const xianxiaVitalsFields: Array<{ key: CharacterXianxiaVitalsField; label: string }> = [
  { key: "currentHp", label: "Current HP" },
  { key: "tempHp", label: "Temp HP" },
  { key: "currentStance", label: "Current Stance" },
  { key: "tempStance", label: "Temp Stance" },
  { key: "currentJing", label: "Jing" },
  { key: "currentQi", label: "Qi" },
  { key: "currentShen", label: "Shen" },
  { key: "currentYin", label: "Yin" },
  { key: "currentYang", label: "Yang" },
  { key: "currentDao", label: "Dao" },
];

export function emptyCharacterVitalsDraft(): CharacterVitalsDraft {
  return {
    expectedRevision: 0,
    currentHp: "",
    tempHp: "",
  };
}

export function emptyCharacterXianxiaVitalsDraft(): CharacterXianxiaVitalsDraft {
  return {
    ...emptyCharacterVitalsDraft(),
    currentStance: "",
    tempStance: "",
    currentJing: "",
    currentQi: "",
    currentShen: "",
    currentYin: "",
    currentYang: "",
    currentDao: "",
  };
}

export function emptyCharacterXianxiaActiveStateDraft(): CharacterXianxiaActiveStateDraft {
  return {
    expectedRevision: 0,
    activeStanceName: "",
    activeAuraName: "",
  };
}

export function emptyCharacterXianxiaDaoUseRequestDraft(): CharacterXianxiaDaoUseRequestDraft {
  return {
    requestName: "",
    notes: "",
    preparedRecordIndex: "",
  };
}

export function emptyCharacterNotesDraft(): CharacterNotesDraft {
  return {
    expectedRevision: 0,
    notes: "",
  };
}

export function emptyCharacterPortraitDraft(): CharacterPortraitDraft {
  return {
    file: null,
    fileName: "",
    altText: "",
    caption: "",
  };
}

export function emptyCharacterControlsDraft(): CharacterControlsDraft {
  return {
    assignedUserId: "",
    deleteConfirmation: "",
  };
}

export function buildCharacterPaneDraftSnapshot(character: CharacterRecord): CharacterPaneDraftSnapshot {
  const state = asRecord(character.state_record.state);
  const vitals = asRecord(state.vitals);
  const xianxiaState = asRecord(state.xianxia);
  const xianxiaVitals = asRecord(xianxiaState.vitals);
  const xianxiaEnergies = asRecord(xianxiaState.energies);
  const xianxiaYinYang = asRecord(xianxiaState.yin_yang);
  const xianxiaDao = asRecord(xianxiaState.dao);
  const presentedXianxia = character.presented_xianxia;
  const notes = asRecord(state.notes);
  const revision = character.state_record.revision;

  const resourceDrafts: Record<string, string> = {};
  for (const resource of asRecordArray(state.resources)) {
    const id = readString(resource.id);
    if (id) {
      resourceDrafts[id] = String(readNumber(resource.current));
    }
  }

  const spellSlotDrafts: Record<string, string> = {};
  for (const slot of asRecordArray(state.spell_slots)) {
    const key = draftKey(readNumber(slot.level), readString(slot.slot_lane_id));
    spellSlotDrafts[key] = String(readNumber(slot.used));
  }

  const inventoryDrafts: Record<string, string> = {};
  for (const item of asRecordArray(state.inventory)) {
    const id = readString(item.id);
    if (id) {
      inventoryDrafts[id] = String(readNumber(item.quantity, 1));
    }
  }

  const xianxiaInventoryDrafts: Record<string, CharacterXianxiaInventoryDraft> = {};
  for (const item of presentedXianxia?.inventory?.quantities ?? []) {
    if (item.id) {
      xianxiaInventoryDrafts[item.id] = xianxiaInventoryDraftFromItem(item);
      inventoryDrafts[item.id] = String(readNumber(item.quantity, 1));
    }
  }

  const xianxiaDaoUseNotesDrafts: Record<string, string> = {};
  for (const group of presentedXianxia?.approval?.status_groups ?? []) {
    if (group.key !== "dao_immolating_use_records") {
      continue;
    }
    for (const record of group.records) {
      xianxiaDaoUseNotesDrafts[xianxiaDaoUseRecordDraftKey(record)] = readString(record.use_notes);
    }
  }

  const equipmentState = character.equipment_state;
  const equipmentDrafts: Record<string, CharacterEquipmentDraft> = {};
  for (const item of equipmentState?.rows ?? []) {
    if (item.id) {
      equipmentDrafts[item.id] = {
        isEquipped: Boolean(item.is_equipped),
        isAttuned: Boolean(item.is_attuned),
        weaponWieldMode: item.weapon_wield_mode || "",
      };
    }
  }

  const currency = isXianxiaCharacter(character) ? asRecord(xianxiaState.currency) : asRecord(state.currency);
  const currencyDraft: Record<string, string> = {};
  for (const key of ["cp", "sp", "ep", "gp", "pp", "coin", "supply", "spirit_stones"]) {
    if (currency[key] !== undefined) {
      currencyDraft[key] = String(readNumber(currency[key]));
    }
  }

  return {
    vitalsDraft: {
      expectedRevision: revision,
      currentHp: String(readNumber(vitals.current_hp, 0)),
      tempHp: String(readNumber(vitals.temp_hp, 0)),
    },
    xianxiaVitalsDraft: {
      expectedRevision: revision,
      currentHp: String(readNumber(vitals.current_hp, readNumber(xianxiaVitals.current_hp, 0))),
      tempHp: String(readNumber(vitals.temp_hp, readNumber(xianxiaVitals.temp_hp, 0))),
      currentStance: String(readNumber(xianxiaVitals.current_stance, 0)),
      tempStance: String(readNumber(xianxiaVitals.temp_stance, 0)),
      currentJing: String(readNumber(asRecord(xianxiaEnergies.jing).current, 0)),
      currentQi: String(readNumber(asRecord(xianxiaEnergies.qi).current, 0)),
      currentShen: String(readNumber(asRecord(xianxiaEnergies.shen).current, 0)),
      currentYin: String(readNumber(xianxiaYinYang.yin_current, 0)),
      currentYang: String(readNumber(xianxiaYinYang.yang_current, 0)),
      currentDao: String(readNumber(xianxiaDao.current, 0)),
    },
    xianxiaActiveDraft: {
      expectedRevision: revision,
      activeStanceName: presentedXianxia?.active_state?.stance?.name ?? "",
      activeAuraName: presentedXianxia?.active_state?.aura?.name ?? "",
    },
    notesDraft: {
      expectedRevision: revision,
      notes: readString(notes.player_notes_markdown),
    },
    resourceDrafts,
    spellSlotDrafts,
    inventoryDrafts,
    equipmentDrafts,
    xianxiaInventoryDrafts,
    xianxiaDaoUseNotesDrafts,
    arcaneArmorEnabled: Boolean((character.arcane_armor_state ?? equipmentState?.arcane_armor_state)?.enabled),
    currencyDraft,
    portraitDraft: {
      file: null,
      fileName: "",
      altText: character.portrait?.alt_text ?? "",
      caption: character.portrait?.caption ?? "",
    },
    controlsDraft: {
      assignedUserId: character.controls?.assignment?.user_id ? String(character.controls.assignment.user_id) : "",
      deleteConfirmation: "",
    },
  };
}
