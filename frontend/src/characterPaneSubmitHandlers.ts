import type { ChangeEvent, Dispatch, FocusEvent, FormEvent, SetStateAction } from "react";

import type {
  CharacterArcaneArmorState,
  CharacterControls,
  CharacterCurrencyPatchPayload,
  CharacterEquipmentRow,
  CharacterSummary,
  CharacterXianxiaInventoryItem,
  CharacterXianxiaNamedRecord,
} from "./api/types";
import type {
  CharacterControlsDraft,
  CharacterArtificerInfusionDrafts,
  CharacterEquipmentDraft,
  CharacterNotesDraft,
  CharacterPortraitDraft,
  CharacterVitalsDraft,
  CharacterXianxiaActiveStateDraft,
  CharacterXianxiaDaoUseRequestDraft,
  CharacterXianxiaVitalsDraft,
} from "./characterPaneDrafts";
import type { useCharacterPaneMutations } from "./characterPaneMutations";
import {
  draftKey,
  parseCharacterNumberInput,
  xianxiaDaoUseRecordDraftKey,
  xianxiaInventoryDraftFromItem,
  xianxiaInventoryPayloadFromDraft,
  type CharacterXianxiaInventoryDraft,
} from "./characterPaneUtils";
import { readNumber, readString } from "./characterValueUtils";
import { readBinaryAsBase64 } from "./sessionArticleDrafts";

type CharacterPaneMutationBundle = ReturnType<typeof useCharacterPaneMutations>;

export function useCharacterPaneSubmitHandlers({
  arcaneArmorDraft,
  arcaneArmorState,
  artificerInfusionDrafts,
  canEdit,
  canRecordXianxiaDaoUse,
  controls,
  controlsDraft,
  currencyDraft,
  equipmentDrafts,
  inventoryDrafts,
  isXianxia,
  mutations,
  newXianxiaInventoryDraft,
  notesDraft,
  portraitDraft,
  resourceDrafts,
  revision,
  selected,
  selectedSlug,
  setErrorMessage,
  setPortraitDraft,
  setStatusMessage,
  spellSlotDrafts,
  vitalsDraft,
  xianxiaActiveDraft,
  xianxiaDaoRequestDraft,
  xianxiaDaoUseNotesDrafts,
  xianxiaInventoryDrafts,
  xianxiaVitalsDraft,
}: {
  arcaneArmorDraft: boolean;
  arcaneArmorState?: CharacterArcaneArmorState | null;
  artificerInfusionDrafts: CharacterArtificerInfusionDrafts;
  canEdit: boolean;
  canRecordXianxiaDaoUse: boolean;
  controls?: CharacterControls | null;
  controlsDraft: CharacterControlsDraft;
  currencyDraft: Record<string, string>;
  equipmentDrafts: Record<string, CharacterEquipmentDraft>;
  inventoryDrafts: Record<string, string>;
  isXianxia: boolean;
  mutations: CharacterPaneMutationBundle;
  newXianxiaInventoryDraft: CharacterXianxiaInventoryDraft;
  notesDraft: CharacterNotesDraft;
  portraitDraft: CharacterPortraitDraft;
  resourceDrafts: Record<string, string>;
  revision: number;
  selected?: CharacterSummary;
  selectedSlug: string | null;
  setErrorMessage: Dispatch<SetStateAction<string | null>>;
  setPortraitDraft: Dispatch<SetStateAction<CharacterPortraitDraft>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  spellSlotDrafts: Record<string, string>;
  vitalsDraft: CharacterVitalsDraft;
  xianxiaActiveDraft: CharacterXianxiaActiveStateDraft;
  xianxiaDaoRequestDraft: CharacterXianxiaDaoUseRequestDraft;
  xianxiaDaoUseNotesDrafts: Record<string, string>;
  xianxiaInventoryDrafts: Record<string, CharacterXianxiaInventoryDraft>;
  xianxiaVitalsDraft: CharacterXianxiaVitalsDraft;
}) {
  const parseNumberInput = (value: string, label: string): number | null => {
    const result = parseCharacterNumberInput(value, label);
    if (result.errorMessage) {
      setErrorMessage(result.errorMessage);
      setStatusMessage(null);
      return null;
    }
    return result.value;
  };

  const requireEditableCharacter = () => {
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return false;
    }
    return true;
  };

  const handlePortraitFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0] ?? null;
    if (!file) {
      setPortraitDraft((current) => ({ ...current, file: null, fileName: "" }));
      return;
    }
    readBinaryAsBase64(file, (payload) => {
      if (!payload) {
        setPortraitDraft((current) => ({ ...current, file: null, fileName: "" }));
        setStatusMessage(null);
        setErrorMessage("Could not read the portrait file.");
        return;
      }
      setPortraitDraft((current) => ({ ...current, file: payload, fileName: file.name }));
      setErrorMessage(null);
    });
  };

  const submitPortrait = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!portraitDraft.file) {
      setStatusMessage(null);
      setErrorMessage("Choose an image file before saving the portrait.");
      return;
    }
    mutations.upsertPortrait.mutate({
      expected_revision: revision,
      portrait_file: portraitDraft.file,
      alt_text: portraitDraft.altText,
      caption: portraitDraft.caption,
    });
  };

  const removePortrait = () => {
    mutations.deletePortrait.mutate({ expected_revision: revision });
  };

  const submitCharacterAssignment = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedSlug || !controls?.can_assign_owner) {
      setStatusMessage(null);
      setErrorMessage("Only admins can assign character owners.");
      return;
    }
    const userId = Number(controlsDraft.assignedUserId);
    if (!Number.isInteger(userId) || userId <= 0) {
      setStatusMessage(null);
      setErrorMessage("Choose a valid player to assign.");
      return;
    }
    setStatusMessage("Saving...");
    mutations.assignCharacterOwner.mutate({ user_id: userId });
  };

  const clearCharacterAssignment = () => {
    if (!selectedSlug || !controls?.can_assign_owner) {
      setStatusMessage(null);
      setErrorMessage("Only admins can clear character owners.");
      return;
    }
    setStatusMessage("Saving...");
    mutations.clearCharacterOwner.mutate();
  };

  const submitCharacterDelete = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedSlug || !controls?.can_delete_character) {
      setStatusMessage(null);
      setErrorMessage("You do not have permission to delete this character.");
      return;
    }
    setStatusMessage("Deleting...");
    mutations.deleteCharacterMutation.mutate({
      confirm_character_slug: controlsDraft.deleteConfirmation.trim(),
    });
  };

  const submitVitals = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const currentHp = parseNumberInput(vitalsDraft.currentHp, "current HP");
    const tempHp = parseNumberInput(vitalsDraft.tempHp, "temp HP");

    if (!requireEditableCharacter() || currentHp === null || tempHp === null) {
      return;
    }

    setStatusMessage("Saving...");
    mutations.patchVitals.mutate({
      expected_revision: revision,
      current_hp: currentHp,
      temp_hp: tempHp,
    });
  };

  const submitXianxiaVitals = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = [
      ["current HP", xianxiaVitalsDraft.currentHp],
      ["temp HP", xianxiaVitalsDraft.tempHp],
      ["current Stance", xianxiaVitalsDraft.currentStance],
      ["temp Stance", xianxiaVitalsDraft.tempStance],
      ["current Jing", xianxiaVitalsDraft.currentJing],
      ["current Qi", xianxiaVitalsDraft.currentQi],
      ["current Shen", xianxiaVitalsDraft.currentShen],
      ["current Yin", xianxiaVitalsDraft.currentYin],
      ["current Yang", xianxiaVitalsDraft.currentYang],
      ["current Dao", xianxiaVitalsDraft.currentDao],
    ] as const;
    const parsed = new Map<string, number>();
    for (const [label, value] of fields) {
      const numberValue = parseNumberInput(value, label);
      if (numberValue === null) {
        return;
      }
      parsed.set(label, numberValue);
    }
    if (!requireEditableCharacter()) {
      return;
    }

    setStatusMessage("Saving...");
    mutations.patchVitals.mutate({
      expected_revision: revision,
      current_hp: parsed.get("current HP"),
      temp_hp: parsed.get("temp HP"),
      current_stance: parsed.get("current Stance"),
      temp_stance: parsed.get("temp Stance"),
      current_jing: parsed.get("current Jing"),
      current_qi: parsed.get("current Qi"),
      current_shen: parsed.get("current Shen"),
      current_yin: parsed.get("current Yin"),
      current_yang: parsed.get("current Yang"),
      current_dao: parsed.get("current Dao"),
    });
  };

  const submitXianxiaActiveState = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchXianxiaActiveState.mutate({
      expected_revision: revision,
      active_stance_name: xianxiaActiveDraft.activeStanceName,
      active_aura_name: xianxiaActiveDraft.activeAuraName,
    });
  };

  const submitXianxiaDaoUseRequest = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!requireEditableCharacter()) {
      return;
    }
    const requestName = xianxiaDaoRequestDraft.requestName.trim();
    const preparedRecordIndexText = xianxiaDaoRequestDraft.preparedRecordIndex.trim();
    let preparedRecordIndex: number | null = null;
    if (preparedRecordIndexText) {
      const parsedIndex = parseNumberInput(preparedRecordIndexText, "prepared Dao Immolating note");
      if (parsedIndex === null) {
        return;
      }
      preparedRecordIndex = parsedIndex;
    }
    if (!requestName && preparedRecordIndex === null) {
      setErrorMessage("Enter a request name or choose a prepared Dao Immolating note.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    mutations.postXianxiaDaoUseRequest.mutate({
      expected_revision: revision,
      request_name: requestName,
      notes: xianxiaDaoRequestDraft.notes.trim(),
      prepared_record_index: preparedRecordIndex,
    });
  };

  const submitXianxiaDaoUseRecord = (
    event: FormEvent<HTMLFormElement>,
    record: CharacterXianxiaNamedRecord,
  ) => {
    event.preventDefault();
    if (!selected || !canRecordXianxiaDaoUse) {
      setErrorMessage("Only session managers can record Dao Immolating one-use spends.");
      setStatusMessage(null);
      return;
    }
    if (record.use_record_index === undefined) {
      setErrorMessage("Choose a valid Dao Immolating use record.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    mutations.postXianxiaDaoUseRecord.mutate({
      expected_revision: revision,
      use_record_index: record.use_record_index,
      notes: (xianxiaDaoUseNotesDrafts[xianxiaDaoUseRecordDraftKey(record)] ?? "").trim(),
    });
  };

  const submitResource = (event: FormEvent<HTMLFormElement>, resourceId: string) => {
    event.preventDefault();
    const current = parseNumberInput(resourceDrafts[resourceId] ?? "", "resource value");
    if (!requireEditableCharacter() || current === null) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchResource.mutate({ resourceId, payload: { expected_revision: revision, current } });
  };

  const submitResourceOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || mutations.patchResource.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitSpellSlot = (event: FormEvent<HTMLFormElement>, slot: Record<string, unknown>) => {
    event.preventDefault();
    const level = readNumber(slot.level);
    const slotLaneId = readString(slot.slot_lane_id);
    const key = draftKey(level, slotLaneId);
    const used = parseNumberInput(spellSlotDrafts[key] ?? "", "used slot count");
    if (!requireEditableCharacter() || used === null) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchSpellSlot.mutate({
      level,
      payload: { expected_revision: revision, slot_lane_id: slotLaneId, used },
    });
  };

  const submitSpellSlotOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || mutations.patchSpellSlot.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitInventory = (event: FormEvent<HTMLFormElement>, itemId: string) => {
    event.preventDefault();
    const quantity = parseNumberInput(inventoryDrafts[itemId] ?? "", "quantity");
    if (!requireEditableCharacter() || quantity === null) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchInventory.mutate({ itemId, payload: { expected_revision: revision, quantity } });
  };

  const submitInventoryOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || mutations.patchInventory.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitXianxiaInventoryAdd = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!requireEditableCharacter()) {
      return;
    }
    if (!newXianxiaInventoryDraft.name.trim()) {
      setErrorMessage("Enter an item name.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    mutations.addXianxiaInventoryItem.mutate({
      expected_revision: revision,
      item: xianxiaInventoryPayloadFromDraft(newXianxiaInventoryDraft),
    });
  };

  const submitXianxiaInventoryUpdate = (event: FormEvent<HTMLFormElement>, item: CharacterXianxiaInventoryItem) => {
    event.preventDefault();
    const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
    if (!requireEditableCharacter()) {
      return;
    }
    if (!draft.name.trim()) {
      setErrorMessage("Enter an item name.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchXianxiaInventoryItem.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        item: {
          ...xianxiaInventoryPayloadFromDraft(draft),
          id: item.id,
        },
      },
    });
  };

  const toggleXianxiaInventoryEquipped = (item: CharacterXianxiaInventoryItem, isEquipped: boolean) => {
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchXianxiaInventoryEquipped.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        is_equipped: isEquipped,
      },
    });
  };

  const removeXianxiaInventory = (item: CharacterXianxiaInventoryItem) => {
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.removeXianxiaInventoryItem.mutate({
      itemId: item.id,
      payload: { expected_revision: revision },
    });
  };

  const submitArcaneArmorState = (event?: FormEvent<HTMLFormElement>, enabled = arcaneArmorDraft) => {
    event?.preventDefault();
    const featureKey = readString(arcaneArmorState?.feature_key, "arcane_armor");
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchFeatureState.mutate({
      featureKey,
      payload: {
        expected_revision: revision,
        enabled,
      },
    });
  };

  const submitArtificerInfusionsPatch = (drafts: CharacterArtificerInfusionDrafts = artificerInfusionDrafts) => {
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchArtificerInfusions.mutate({
      expected_revision: revision,
      active: Object.entries(drafts)
        .filter(([, targetItemRef]) => readString(targetItemRef))
        .map(([infusionKey, targetItemRef]) => ({
          infusion_key: infusionKey,
          target_item_ref: readString(targetItemRef),
        })),
    });
  };

  const submitArtificerInfusions = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitArtificerInfusionsPatch();
  };

  const submitEquipmentStatePatch = (item: CharacterEquipmentRow, draft: CharacterEquipmentDraft) => {
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchEquipmentState.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        is_equipped: draft.isEquipped,
        is_attuned: draft.isAttuned,
        weapon_wield_mode: item.supports_weapon_wield_mode ? draft.weaponWieldMode : "",
      },
    });
  };

  const submitEquipmentState = (event: FormEvent<HTMLFormElement>, item: CharacterEquipmentRow) => {
    event.preventDefault();
    const draft = equipmentDrafts[item.id] ?? {
      isEquipped: Boolean(item.is_equipped),
      isAttuned: Boolean(item.is_attuned),
      weaponWieldMode: item.weapon_wield_mode || "",
    };
    submitEquipmentStatePatch(item, draft);
  };

  const submitCurrency = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!requireEditableCharacter()) {
      return;
    }
    const payload: CharacterCurrencyPatchPayload = { expected_revision: revision };
    const currencyKeys = isXianxia ? ["coin", "supply", "spirit_stones"] : ["cp", "sp", "ep", "gp", "pp"];
    for (const key of currencyKeys) {
      if (currencyDraft[key] !== undefined) {
        const value = parseNumberInput(currencyDraft[key], key.replace("_", " ").toUpperCase());
        if (value === null) {
          return;
        }
        payload[key as "cp" | "sp" | "ep" | "gp" | "pp" | "coin" | "supply" | "spirit_stones"] = value;
      }
    }
    setStatusMessage("Saving...");
    mutations.patchCurrency.mutate(payload);
  };

  const submitCurrencyOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || mutations.patchCurrency.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitNotes = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!requireEditableCharacter()) {
      return;
    }
    setStatusMessage("Saving...");
    mutations.patchNotes.mutate({
      expected_revision: revision,
      player_notes_markdown: notesDraft.notes,
    });
  };

  const clearNotes = () => {
    if (!requireEditableCharacter()) {
      return;
    }
    if (!notesDraft.notes.trim()) {
      return;
    }
    setStatusMessage("Deleting note...");
    mutations.patchNotes.mutate({
      expected_revision: revision,
      player_notes_markdown: "",
    });
  };

  return {
    clearNotes,
    clearCharacterAssignment,
    handlePortraitFileChange,
    removePortrait,
    removeXianxiaInventory,
    submitArcaneArmorState,
    submitArtificerInfusions,
    submitArtificerInfusionsPatch,
    submitCharacterAssignment,
    submitCharacterDelete,
    submitCurrency,
    submitCurrencyOnBlur,
    submitEquipmentState,
    submitEquipmentStatePatch,
    submitInventory,
    submitInventoryOnBlur,
    submitNotes,
    submitPortrait,
    submitResource,
    submitResourceOnBlur,
    submitSpellSlot,
    submitSpellSlotOnBlur,
    submitVitals,
    submitXianxiaActiveState,
    submitXianxiaDaoUseRecord,
    submitXianxiaDaoUseRequest,
    submitXianxiaInventoryAdd,
    submitXianxiaInventoryUpdate,
    submitXianxiaVitals,
    toggleXianxiaInventoryEquipped,
  };
}
