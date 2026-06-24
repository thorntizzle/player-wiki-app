import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FocusEvent, FormEvent, MouseEvent } from "react";
import type {
  CharacterCurrencyPatchPayload,
  CharacterDetailResponse,
  CharacterEquipmentRow,
  CharacterPresentedSpell,
  CharacterXianxiaInventoryItem,
  CharacterXianxiaNamedRecord,
  CharacterRestPreviewResponse,
  CharacterSummary,
} from "../api/types";
import type {
  CharacterEquipmentDraft,
} from "../characterPaneDrafts";
import {
  useCharacterPaneDraftState,
} from "../characterPaneDrafts";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { useApiClient } from "../apiClientContext";
import { TOAST_DISMISS_MS, ToastNotice } from "../components/feedback";
import {
  CharacterDetailDialog,
  type CharacterDetailDialogState,
} from "../components/CharacterDetailDialog";
import { useCharacterPaneMutations } from "../characterPaneMutations";
import { CharacterControlsSection } from "../components/CharacterControlsSection";
import { CharacterEmbeddedSectionNav } from "../components/CharacterEmbeddedSectionNav";
import { CharacterHeader } from "../components/CharacterHeader";
import { CharacterNavigationCard } from "../components/CharacterNavigationCard";
import { CharacterPortraitManager } from "../components/CharacterPortraitManager";
import { CharacterSummaryCard } from "../components/CharacterSummaryCard";
import { CharacterSystemSummarySection } from "../components/CharacterSystemSummarySection";
import { CharacterVitalsBar } from "../components/CharacterVitalsBar";
import { CharacterDndSections } from "../components/CharacterDndSections";
import { CharacterNotesSection } from "../components/CharacterNotesSection";
import { CharacterXianxiaSections } from "../components/CharacterXianxiaSections";
import {
  readNumber,
  readString,
} from "../characterValueUtils";
import {
  characterSystem,
  characterReadSectionUrl,
  defaultCharacterReadSection,
  draftKey,
  itemDetailDialogState,
  isDndCharacter,
  isXianxiaCharacter,
  normalizeActiveCharacterSectionForSystem,
  parseCharacterNumberInput,
  spellDetailDialogState,
  visibleCharacterSectionsForSystem,
  xianxiaDaoUseRecordDraftKey,
  xianxiaInventoryDraftFromItem,
  xianxiaInventoryPayloadFromDraft,
  type CharacterItemDetailInput,
  type CharacterSection,
  type CharacterXianxiaInventoryDraft,
} from "../characterPaneUtils";
import { buildCharacterPaneModel } from "../characterPaneModel";
import { buildCharacterPaneXianxiaModel } from "../characterPaneXianxiaModel";
import { readBinaryAsBase64 } from "../sessionArticleDrafts";

export function CharacterPane({
  campaignSlug,
  initialCharacterSlug = null,
  initialSection = null,
  surface = "session",
  onSelectedCharacterChange,
}: {
  campaignSlug: string;
  initialCharacterSlug?: string | null;
  initialSection?: CharacterSection | null;
  surface?: "session" | "read" | "combat";
  onSelectedCharacterChange?: (characterSlug: string) => void;
}) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(initialCharacterSlug);
  const [activeCharacterSection, setActiveCharacterSection] = useState<CharacterSection>(initialSection ?? "overview");
  const [restPreview, setRestPreview] = useState<CharacterRestPreviewResponse["preview"] | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [detailDialog, setDetailDialog] = useState<CharacterDetailDialogState | null>(null);
  const portraitFileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!statusMessage) {
      return undefined;
    }
    const timer = window.setTimeout(() => setStatusMessage(null), TOAST_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [statusMessage]);

  const listQuery = useQuery({
    queryKey: ["characters", campaignSlug, ""],
    queryFn: () => apiClient.getCharacters(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  const characterList: CharacterSummary[] = listQuery.data?.characters ?? [];

  useEffect(() => {
    if (initialCharacterSlug !== selectedSlug) {
      setSelectedSlug(initialCharacterSlug || null);
    }
  }, [initialCharacterSlug]);

  useEffect(() => {
    if (initialSection && initialSection !== activeCharacterSection) {
      setActiveCharacterSection(initialSection);
    }
  }, [initialSection]);

  useEffect(() => {
    if (!initialCharacterSlug && !selectedSlug && characterList.length > 0) {
      setSelectedSlug(characterList[0].slug);
    }
  }, [characterList, initialCharacterSlug, selectedSlug]);

  const detailQuery = useQuery({
    queryKey: ["character-detail", campaignSlug, selectedSlug],
    queryFn: () => {
      if (!selectedSlug) {
        throw new Error("No character selected");
      }
      return apiClient.getCharacter(campaignSlug, selectedSlug);
    },
    enabled: Boolean(campaignSlug) && Boolean(selectedSlug),
    retry: false,
  });

  const {
    arcaneArmorEnabled: arcaneArmorDraft,
    controlsDraft,
    currencyDraft,
    equipmentDrafts,
    inventoryDrafts,
    newXianxiaInventoryDraft,
    notesDraft,
    portraitDraft,
    resourceDrafts,
    setArcaneArmorDraft,
    setControlsDraft,
    setCurrencyDraft,
    setEquipmentDrafts,
    setInventoryDrafts,
    setNewXianxiaInventoryDraft,
    setNotesDraft,
    setPortraitDraft,
    setResourceDrafts,
    setSpellSlotDrafts,
    setVitalsDraft,
    setXianxiaActiveDraft,
    setXianxiaDaoRequestDraft,
    setXianxiaDaoUseNotesDrafts,
    setXianxiaInventoryDrafts,
    setXianxiaVitalsDraft,
    spellSlotDrafts,
    vitalsDraft,
    xianxiaActiveDraft,
    xianxiaDaoRequestDraft,
    xianxiaDaoUseNotesDrafts,
    xianxiaInventoryDrafts,
    xianxiaVitalsDraft,
  } = useCharacterPaneDraftState({
    character: detailQuery.data?.character,
    portraitFileInputRef,
    selectedSlug,
  });

  useEffect(() => {
    if (listQuery.error && isAuthError(listQuery.error)) {
      setAuthRequired(true);
    }
  }, [listQuery.error, setAuthRequired]);

  useEffect(() => {
    if (detailQuery.error && isAuthError(detailQuery.error)) {
      setAuthRequired(true);
    }
  }, [detailQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!detailDialog) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDetailDialog(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [detailDialog]);

  const detail = detailQuery.data as CharacterDetailResponse | undefined;
  const detailRecord = detail?.character;
  const detailLinks = detail?.links ?? {};
  const detailProgressionRepairUrl = detailLinks.progression_repair_url || detailLinks.flask_progression_repair_url;
  const selectedCharacterSheetUrl = selectedSlug
    ? `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(selectedSlug)}`
    : "";
  const hasReadHeaderManagementActions = Boolean(
    detailLinks.advanced_editor_url ||
      detailLinks.level_up_url ||
      detailLinks.retraining_url ||
      detailProgressionRepairUrl ||
      detailLinks.cultivation_url,
  );
  const selected = characterList.find((item) => item.slug === selectedSlug);
  const selectedPortrait = detailRecord?.portrait ?? selected?.portrait ?? null;
  const permissions = detailRecord?.permissions;
  const controls = detailRecord?.controls ?? null;
  const canEdit = Boolean(permissions?.can_edit_session);
  const canRecordXianxiaDaoUse = Boolean(
    permissions?.can_record_xianxia_dao_immolating_use ?? permissions?.can_manage_session,
  );
  const isDnd = isDndCharacter(detailRecord);
  const isXianxia = isXianxiaCharacter(detailRecord);
  const {
    arcaneArmorState,
    currency,
    dndAbilities,
    dndProficiencyGroups,
    equipmentRows,
    equipmentState,
    hasDndAbilitySkillsContent,
    hasOverviewStatRows,
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
  } = useMemo(() => buildCharacterPaneModel(detailRecord, { isXianxia }), [detailRecord, isXianxia]);
  const revision = detailRecord?.state_record.revision ?? 0;
  const xianxiaModel = buildCharacterPaneXianxiaModel(presentedXianxia);

  const isReadSurface = surface === "read";
  const isCombatSurface = surface === "combat";
  const canUseControls = isReadSurface && Boolean(permissions?.can_use_controls && controls?.available);
  const canManagePortrait = isReadSurface && canEdit;
  const surfaceMetaLabel = isReadSurface ? "Character sheet" : isCombatSurface ? "Combat Character" : "Session Character";
  const surfaceHeading = isReadSurface ? "Character Sheet" : isCombatSurface ? "Combat Character" : "Session Character";
  const embeddedHeaderDetails = selected
    ? [selected.class_level_text, selected.species, selected.background].filter((value) => Boolean(value))
    : [];
  const normalizedActiveCharacterSection = normalizeActiveCharacterSectionForSystem(activeCharacterSection, {
    canUseControls,
    hasDetailRecord: Boolean(detailRecord),
    isDnd,
    isXianxia,
  });

  useEffect(() => {
    if (normalizedActiveCharacterSection !== activeCharacterSection) {
      setActiveCharacterSection(normalizedActiveCharacterSection);
    }
  }, [activeCharacterSection, normalizedActiveCharacterSection]);

  const dndVisibleCharacterSections = visibleCharacterSectionsForSystem(true, canUseControls);
  const xianxiaVisibleCharacterSections = visibleCharacterSectionsForSystem(false, canUseControls);
  const visibleCharacterSections = isDnd ? dndVisibleCharacterSections : xianxiaVisibleCharacterSections;
  const readSurfaceDefaultSection = defaultCharacterReadSection(isXianxia);
  const readSurfaceSectionUrl = (section: CharacterSection) =>
    characterReadSectionUrl(campaignSlug, selectedSlug, section, readSurfaceDefaultSection);
  const handleReadSurfaceSectionNavClick = (section: CharacterSection) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (!selectedSlug) {
      return;
    }
    event.preventDefault();
    selectCharacterSection(section);
  };

  const {
    addXianxiaInventoryItem,
    applyRest,
    assignCharacterOwner,
    clearCharacterOwner,
    deleteCharacterMutation,
    deletePortrait,
    patchCurrency,
    patchEquipmentState,
    patchFeatureState,
    patchInventory,
    patchNotes,
    patchResource,
    patchSpellSlot,
    patchVitals,
    patchXianxiaActiveState,
    patchXianxiaInventoryEquipped,
    patchXianxiaInventoryItem,
    postXianxiaDaoUseRecord,
    postXianxiaDaoUseRequest,
    previewRest,
    removeXianxiaInventoryItem,
    upsertPortrait,
  } = useCharacterPaneMutations({
    campaignSlug,
    selectedSlug,
    refetchCharacterList: listQuery.refetch,
    setControlsDraft,
    setErrorMessage,
    setNewXianxiaInventoryDraft,
    setPortraitDraft,
    setRestPreview,
    setStatusMessage,
    setXianxiaDaoRequestDraft,
    portraitFileInputRef,
  });

  const portraitMutationPending = upsertPortrait.isPending || deletePortrait.isPending;
  const controlsMutationPending =
    assignCharacterOwner.isPending || clearCharacterOwner.isPending || deleteCharacterMutation.isPending;

  const parseNumberInput = (value: string, label: string): number | null => {
    const result = parseCharacterNumberInput(value, label);
    if (result.errorMessage) {
      setErrorMessage(result.errorMessage);
      setStatusMessage(null);
      return null;
    }
    return result.value;
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
    upsertPortrait.mutate({
      expected_revision: revision,
      portrait_file: portraitDraft.file,
      alt_text: portraitDraft.altText,
      caption: portraitDraft.caption,
    });
  };

  const removePortrait = () => {
    deletePortrait.mutate({ expected_revision: revision });
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
    assignCharacterOwner.mutate({ user_id: userId });
  };

  const clearCharacterAssignment = () => {
    if (!selectedSlug || !controls?.can_assign_owner) {
      setStatusMessage(null);
      setErrorMessage("Only admins can clear character owners.");
      return;
    }
    setStatusMessage("Saving...");
    clearCharacterOwner.mutate();
  };

  const submitCharacterDelete = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedSlug || !controls?.can_delete_character) {
      setStatusMessage(null);
      setErrorMessage("You do not have permission to delete this character.");
      return;
    }
    setStatusMessage("Deleting...");
    deleteCharacterMutation.mutate({
      confirm_character_slug: controlsDraft.deleteConfirmation.trim(),
    });
  };

  const openItemDetail = (item: CharacterItemDetailInput) => {
    setDetailDialog(itemDetailDialogState(item));
  };

  const openSpellDetail = (spell: CharacterPresentedSpell) => {
    setDetailDialog(spellDetailDialogState(spell));
  };

  const submitVitals = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const currentHp = parseNumberInput(vitalsDraft.currentHp, "current HP");
    const tempHp = parseNumberInput(vitalsDraft.tempHp, "temp HP");

    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (currentHp === null || tempHp === null) {
      return;
    }

    setStatusMessage("Saving...");
    patchVitals.mutate({
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
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }

    setStatusMessage("Saving...");
    patchVitals.mutate({
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
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchXianxiaActiveState.mutate({
      expected_revision: revision,
      active_stance_name: xianxiaActiveDraft.activeStanceName,
      active_aura_name: xianxiaActiveDraft.activeAuraName,
    });
  };

  const submitXianxiaDaoUseRequest = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
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
    postXianxiaDaoUseRequest.mutate({
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
    postXianxiaDaoUseRecord.mutate({
      expected_revision: revision,
      use_record_index: record.use_record_index,
      notes: (xianxiaDaoUseNotesDrafts[xianxiaDaoUseRecordDraftKey(record)] ?? "").trim(),
    });
  };

  const submitResource = (event: FormEvent<HTMLFormElement>, resourceId: string) => {
    event.preventDefault();
    const current = parseNumberInput(resourceDrafts[resourceId] ?? "", "resource value");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (current === null) {
      return;
    }
    setStatusMessage("Saving...");
    patchResource.mutate({ resourceId, payload: { expected_revision: revision, current } });
  };

  const submitResourceOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || patchResource.isPending) {
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
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (used === null) {
      return;
    }
    setStatusMessage("Saving...");
    patchSpellSlot.mutate({
      level,
      payload: { expected_revision: revision, slot_lane_id: slotLaneId, used },
    });
  };

  const submitSpellSlotOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || patchSpellSlot.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitInventory = (event: FormEvent<HTMLFormElement>, itemId: string) => {
    event.preventDefault();
    const quantity = parseNumberInput(inventoryDrafts[itemId] ?? "", "quantity");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (quantity === null) {
      return;
    }
    setStatusMessage("Saving...");
    patchInventory.mutate({ itemId, payload: { expected_revision: revision, quantity } });
  };

  const submitInventoryOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || patchInventory.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitXianxiaInventoryAdd = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (!newXianxiaInventoryDraft.name.trim()) {
      setErrorMessage("Enter an item name.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    addXianxiaInventoryItem.mutate({
      expected_revision: revision,
      item: xianxiaInventoryPayloadFromDraft(newXianxiaInventoryDraft),
    });
  };

  const submitXianxiaInventoryUpdate = (event: FormEvent<HTMLFormElement>, item: CharacterXianxiaInventoryItem) => {
    event.preventDefault();
    const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (!draft.name.trim()) {
      setErrorMessage("Enter an item name.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    patchXianxiaInventoryItem.mutate({
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
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchXianxiaInventoryEquipped.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        is_equipped: isEquipped,
      },
    });
  };

  const removeXianxiaInventory = (item: CharacterXianxiaInventoryItem) => {
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    removeXianxiaInventoryItem.mutate({
      itemId: item.id,
      payload: { expected_revision: revision },
    });
  };

  const submitArcaneArmorState = (event?: FormEvent<HTMLFormElement>, enabled = arcaneArmorDraft) => {
    event?.preventDefault();
    const featureKey = readString(arcaneArmorState?.feature_key, "arcane_armor");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchFeatureState.mutate({
      featureKey,
      payload: {
        expected_revision: revision,
        enabled,
      },
    });
  };

  const submitEquipmentStatePatch = (item: CharacterEquipmentRow, draft: CharacterEquipmentDraft) => {
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchEquipmentState.mutate({
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
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
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
    patchCurrency.mutate(payload);
  };

  const submitCurrencyOnBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!canEdit || patchCurrency.isPending) {
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const submitNotes = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchNotes.mutate({
      expected_revision: revision,
      player_notes_markdown: notesDraft.notes,
    });
  };

  const selectCharacter = (nextSlug: string | null) => {
    setSelectedSlug(nextSlug);
    setActiveCharacterSection("overview");
    setRestPreview(null);
    setStatusMessage(null);
    setErrorMessage(null);
    setDetailDialog(null);
    if (nextSlug) {
      onSelectedCharacterChange?.(nextSlug);
    }
  };

  const selectCharacterSection = (section: CharacterSection) => {
    setActiveCharacterSection(section);
    if (!isReadSurface || !selectedSlug) {
      return;
    }
    const nextUrl = characterReadSectionUrl(campaignSlug, selectedSlug, section, defaultCharacterReadSection(isXianxia));
    window.history.replaceState(null, "", nextUrl);
  };

  return (
    <div className={isReadSurface ? "page-layout character-layout character-read-content" : "session-pane-content"}>
      <article
        className={
          isReadSurface
            ? "article card character-sheet character-read-shell"
            : "article card character-sheet session-character-sheet"
        }
        data-character-read-shell-root={isReadSurface ? "" : undefined}
        data-character-read-shell-page={isReadSurface ? activeCharacterSection || "overview" : undefined}
        data-character-read-shell-mode={isReadSurface ? "read" : undefined}
      >
        <CharacterHeader
          detailLinks={detailLinks}
          detailProgressionRepairUrl={detailProgressionRepairUrl}
          embeddedHeaderDetails={embeddedHeaderDetails}
          hasReadHeaderManagementActions={hasReadHeaderManagementActions}
          isCombatSurface={isCombatSurface}
          isReadSurface={isReadSurface}
          selectedCharacterSheetUrl={selectedCharacterSheetUrl}
          selectedName={selected?.name}
          surfaceHeading={surfaceHeading}
          surfaceMetaLabel={surfaceMetaLabel}
        />

        <CharacterNavigationCard
          activeCharacterSection={activeCharacterSection}
          characterList={characterList}
          handleReadSurfaceSectionNavClick={handleReadSurfaceSectionNavClick}
          isReadSurface={isReadSurface}
          readSurfaceSectionUrl={readSurfaceSectionUrl}
          selectCharacter={selectCharacter}
          selectedSlug={selectedSlug}
          visibleCharacterSections={visibleCharacterSections}
        />

        {listQuery.isLoading ? <p className="status status-neutral">Loading characters...</p> : null}
        {detailQuery.isLoading ? <p className="status status-neutral">Loading character...</p> : null}

        {selected ? (
          <CharacterSummaryCard
            currentHp={readNumber(vitals.current_hp, selected.current_hp)}
            maxHp={readNumber(stats.max_hp, selected.max_hp)}
            selected={selected}
            selectedPortrait={selectedPortrait}
            systemLabel={characterSystem(detailRecord)}
            tempHp={readNumber(vitals.temp_hp, selected.temp_hp)}
          >
            {canManagePortrait ? (
              <CharacterPortraitManager
                handlePortraitFileChange={handlePortraitFileChange}
                portraitDraft={portraitDraft}
                portraitFileInputRef={portraitFileInputRef}
                portraitMutationPending={portraitMutationPending}
                removePortrait={removePortrait}
                selectedPortrait={selectedPortrait}
                setPortraitDraft={setPortraitDraft}
                submitPortrait={submitPortrait}
              />
            ) : null}
          </CharacterSummaryCard>
        ) : null}

        {selected && detailRecord ? (
          <>
            <CharacterVitalsBar
              canEdit={canEdit}
              isRestApplying={applyRest.isPending}
              isRestPreviewLoading={previewRest.isPending}
              isVitalsSaving={patchVitals.isPending}
              isXianxia={isXianxia}
              maxHp={readNumber(stats.max_hp, selected?.max_hp)}
              onApplyRest={(restType) =>
                applyRest.mutate({
                  restType,
                  payload: { expected_revision: revision },
                })
              }
              onClearRestPreview={() => setRestPreview(null)}
              onPreviewRest={(restType) => previewRest.mutate(restType)}
              restPreview={restPreview}
              setVitalsDraft={setVitalsDraft}
              setXianxiaVitalsDraft={setXianxiaVitalsDraft}
              submitVitals={submitVitals}
              submitXianxiaVitals={submitXianxiaVitals}
              surfaceMetaLabel={surfaceMetaLabel}
              vitalsDraft={vitalsDraft}
              xianxiaVitalsDraft={xianxiaVitalsDraft}
            />

            {isDnd && !isReadSurface ? (
              <CharacterEmbeddedSectionNav
                activeCharacterSection={activeCharacterSection}
                selectCharacterSection={selectCharacterSection}
                sections={dndVisibleCharacterSections}
                variant="dnd"
              />
            ) : null}
            {isXianxia && !isReadSurface ? (
              <CharacterEmbeddedSectionNav
                activeCharacterSection={activeCharacterSection}
                selectCharacterSection={selectCharacterSection}
                sections={xianxiaVisibleCharacterSections}
                variant="xianxia"
              />
            ) : null}

            {isXianxia ? (
              <CharacterXianxiaSections
                activeCharacterSection={activeCharacterSection}
                equipment={{
                  defenseReference: xianxiaModel.defenseReference,
                  equipment: presentedXianxia.equipment,
                }}
                inventory={{
                  canEdit,
                  currency,
                  currencyDraft,
                  inventory: xianxiaModel.inventory,
                  isAddingInventoryItem: addXianxiaInventoryItem.isPending,
                  isCurrencySaving: patchCurrency.isPending,
                  isRemovingInventoryItem: removeXianxiaInventoryItem.isPending,
                  isUpdatingInventoryItem: patchXianxiaInventoryItem.isPending,
                  newXianxiaInventoryDraft,
                  removeXianxiaInventory,
                  setCurrencyDraft,
                  setNewXianxiaInventoryDraft,
                  setXianxiaInventoryDrafts,
                  submitCurrency,
                  submitCurrencyOnBlur,
                  submitXianxiaInventoryAdd,
                  submitXianxiaInventoryUpdate,
                  toggleXianxiaInventoryEquipped,
                  xianxiaCurrency: xianxiaModel.currency,
                  xianxiaInventoryDrafts,
                }}
                martialArts={{
                  martialArts: presentedXianxia.martial_arts,
                }}
                personal={{
                  personalBackgroundHtml,
                  physicalDescriptionHtml,
                  portrait: detailRecord?.portrait,
                }}
                quickReference={{
                  hasSkillUseGuardrail: xianxiaModel.hasSkillUseGuardrail,
                  hasXianxiaHonorInteractions: xianxiaModel.hasHonorInteractions,
                  hasXianxiaStanceBreak: xianxiaModel.hasStanceBreak,
                  presentedXianxia,
                  skillUseGuardrailReferenceLines: xianxiaModel.skillUseGuardrailReferenceLines,
                  skillUseGuardrailRuleHref: xianxiaModel.skillUseGuardrailRuleHref,
                  skillUseGuardrailRuleTitle: xianxiaModel.skillUseGuardrailRuleTitle,
                  xianxiaActionReference: xianxiaModel.actionReference,
                  xianxiaDefenseReference: xianxiaModel.defenseReference,
                  xianxiaHonorContexts: xianxiaModel.honorContexts,
                  xianxiaHonorInteractions: xianxiaModel.honorInteractions,
                  xianxiaHonorReferenceLines: xianxiaModel.honorReferenceLines,
                  xianxiaInsight: xianxiaModel.insight,
                  xianxiaRuleTextReferences: xianxiaModel.ruleTextReferences,
                  xianxiaStanceBreak: xianxiaModel.stanceBreak,
                  xianxiaStanceBreakRecoveryLines: xianxiaModel.stanceBreakRecoveryLines,
                  xianxiaStanceBreakReferenceLines: xianxiaModel.stanceBreakReferenceLines,
                }}
                resources={{
                  activeStateStatus: xianxiaModel.activeStateStatus,
                  canEdit,
                  durability: xianxiaModel.durability,
                  energies: xianxiaModel.energies,
                  insight: xianxiaModel.insight,
                  isActiveStateSaving: patchXianxiaActiveState.isPending,
                  setXianxiaActiveDraft,
                  submitXianxiaActiveState,
                  xianxiaActiveDraft,
                  xianxiaDao: xianxiaModel.dao,
                  yinYang: xianxiaModel.yinYang,
                }}
                skills={{
                  hasSkillUseGuardrail: xianxiaModel.hasSkillUseGuardrail,
                  skillUseGuardrailReferenceLines: xianxiaModel.skillUseGuardrailReferenceLines,
                  skillUseGuardrailRuleHref: xianxiaModel.skillUseGuardrailRuleHref,
                  skillUseGuardrailRuleTitle: xianxiaModel.skillUseGuardrailRuleTitle,
                  trainedSkills: presentedXianxia.skills?.trained ?? [],
                }}
                techniques={{
                  approval: presentedXianxia.approval,
                  basicActions: presentedXianxia.basic_actions,
                  canEdit,
                  canRecordXianxiaDaoUse,
                  genericTechniques: presentedXianxia.generic_techniques,
                  isDaoUseRecordSaving: postXianxiaDaoUseRecord.isPending,
                  isDaoUseRequestSaving: postXianxiaDaoUseRequest.isPending,
                  setXianxiaDaoRequestDraft,
                  setXianxiaDaoUseNotesDrafts,
                  submitXianxiaDaoUseRecord,
                  submitXianxiaDaoUseRequest,
                  xianxiaDaoRequestDraft,
                  xianxiaDaoUseNotesDrafts,
                  xianxiaInsight: xianxiaModel.insight,
                }}
              />
            ) : null}

            {isDnd ? (
              <CharacterDndSections
                activeCharacterSection={activeCharacterSection}
                abilitySkills={{
                  abilities: dndAbilities,
                  hasContent: hasDndAbilitySkillsContent,
                  proficiencyGroups: dndProficiencyGroups,
                }}
                equipment={{
                  arcaneArmorDraft,
                  arcaneArmorState,
                  canEdit,
                  equipmentDrafts,
                  equipmentRows,
                  equipmentState,
                  isCombatSurface,
                  isEquipmentStateSaving: patchEquipmentState.isPending,
                  isFeatureStateSaving: patchFeatureState.isPending,
                  openItemDetail,
                  setArcaneArmorDraft,
                  setEquipmentDrafts,
                  submitArcaneArmorState,
                  submitEquipmentState,
                  submitEquipmentStatePatch,
                }}
                inventory={{
                  canEdit,
                  currencyDraft,
                  inventory,
                  inventoryDrafts,
                  isCurrencySaving: patchCurrency.isPending,
                  isInventorySaving: patchInventory.isPending,
                  openItemDetail,
                  presentedInventoryByKey,
                  setCurrencyDraft,
                  setInventoryDrafts,
                  submitCurrency,
                  submitCurrencyOnBlur,
                  submitInventory,
                  submitInventoryOnBlur,
                }}
                overview={{
                  hasOverviewStatRows,
                  overviewStatRows,
                  overviewStats,
                }}
                resources={{
                  canEdit,
                  isSaving: patchResource.isPending,
                  resourceDrafts,
                  resources,
                  setResourceDrafts,
                  submitResource,
                  submitResourceOnBlur,
                }}
                spells={{
                  canEdit,
                  isSaving: patchSpellSlot.isPending,
                  openSpellDetail,
                  presentedSpellGroups,
                  presentedSpells,
                  rawSpellGroups,
                  spellcasting,
                  spells,
                  spellSlotDrafts,
                  spellSlots,
                  setSpellSlotDrafts,
                  submitSpellSlot,
                  submitSpellSlotOnBlur,
                }}
              />
            ) : null}

            {isReadSurface && activeCharacterSection === "controls" && canUseControls && controls ? (
              <CharacterControlsSection
                characterName={selected.name}
                characterSlug={selected.slug}
                clearCharacterAssignment={clearCharacterAssignment}
                controls={controls}
                controlsDraft={controlsDraft}
                controlsMutationPending={controlsMutationPending}
                isAssigningOwner={assignCharacterOwner.isPending}
                isClearingOwner={clearCharacterOwner.isPending}
                isDeletingCharacter={deleteCharacterMutation.isPending}
                setControlsDraft={setControlsDraft}
                submitCharacterAssignment={submitCharacterAssignment}
                submitCharacterDelete={submitCharacterDelete}
              />
            ) : null}

            {((isDnd || isXianxia) ? activeCharacterSection === "notes" : !isDnd) ? (
              <CharacterNotesSection
                canEdit={canEdit}
                isSaving={patchNotes.isPending}
                notesDraft={notesDraft}
                playerNotesHtml={playerNotesHtml}
                referenceSections={referenceSections}
                setNotesDraft={setNotesDraft}
                submitNotes={submitNotes}
              />
            ) : null}

            {!isDnd && !isXianxia ? (
              <CharacterSystemSummarySection
                currentHp={vitals.current_hp}
                systemLabel={characterSystem(detailRecord)}
                tempHp={vitals.temp_hp}
              />
            ) : null}
          </>
        ) : null}

        {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      </article>
      <ToastNotice message={statusMessage} />
      <CharacterDetailDialog detail={detailDialog} onClose={() => setDetailDialog(null)} />
    </div>
  );
}

