import React, { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FocusEvent, FormEvent } from "react";
import { apiErrorMessage } from "../api/client";
import type {
  CharacterCurrencyPatchPayload,
  CharacterDetailResponse,
  CharacterEquipmentRow,
  CharacterEquipmentStatePatchPayload,
  CharacterFeatureStatePatchPayload,
  CharacterInventoryPatchPayload,
  CharacterPresentedInventoryItem,
  CharacterPresentedSpell,
  CharacterPresentedXianxia,
  CharacterPortraitUpsertPayload,
  CharacterRecord,
  CharacterXianxiaDaoUseRecordPayload,
  CharacterXianxiaDaoUseRequestPayload,
  CharacterXianxiaInventoryItem,
  CharacterXianxiaInventoryItemPayload,
  CharacterXianxiaNamedRecord,
  CharacterNotesPatchPayload,
  CharacterResourcePatchPayload,
  CharacterRestApplyResponse,
  CharacterRestPreviewResponse,
  CharacterSpellSlotsPatchPayload,
  CharacterSummary,
  CharacterVitalsPatchPayload,
} from "../api/types";
import type {
  CharacterControlsDraft,
  CharacterEquipmentDraft,
  CharacterNotesDraft,
  CharacterPortraitDraft,
  CharacterVitalsDraft,
  CharacterXianxiaActiveStateDraft,
  CharacterXianxiaDaoUseRequestDraft,
  CharacterXianxiaVitalsDraft,
} from "../characterPaneDrafts";
import {
  buildCharacterPaneDraftSnapshot,
  emptyCharacterControlsDraft,
  emptyCharacterNotesDraft,
  emptyCharacterPortraitDraft,
  emptyCharacterVitalsDraft,
  emptyCharacterXianxiaActiveStateDraft,
  emptyCharacterXianxiaDaoUseRequestDraft,
  emptyCharacterXianxiaVitalsDraft,
  xianxiaVitalsFields,
} from "../characterPaneDrafts";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { queryClient, useApiClient } from "../apiClientContext";
import { TOAST_DISMISS_MS, ToastNotice } from "../components/feedback";
import {
  CharacterDetailDialog,
  type CharacterDetailDialogState,
} from "../components/CharacterDetailDialog";
import { CharacterDndAbilitySkillsSection } from "../components/CharacterDndAbilitySkillsSection";
import {
  asRecord,
  asRecordArray,
  asStringArray,
  boolFromUnknown,
  numberFromUnknown,
  readNumber,
  readString,
  stringFromUnknown,
} from "../characterValueUtils";
import {
  asCharacterXianxiaNamedRecord,
  characterSystem,
  collectPresentedSpells,
  dndCharacterSections,
  draftKey,
  groupSpellsByLevel,
  isDndCharacter,
  isXianxiaCharacter,
  joinDisplay,
  presentedSpellCardDetailLine,
  rawSpellCardDetailLine,
  spellDetailFacts,
  xianxiaCharacterSections,
  xianxiaDaoUseRecordDraftKey,
  xianxiaInventoryDraftFromItem,
  xianxiaInventoryPayloadFromDraft,
  type CharacterSection,
  type CharacterXianxiaInventoryDraft,
} from "../characterPaneUtils";
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
  const [vitalsDraft, setVitalsDraft] = useState<CharacterVitalsDraft>(emptyCharacterVitalsDraft);
  const [xianxiaVitalsDraft, setXianxiaVitalsDraft] = useState<CharacterXianxiaVitalsDraft>(
    emptyCharacterXianxiaVitalsDraft,
  );
  const [xianxiaActiveDraft, setXianxiaActiveDraft] = useState<CharacterXianxiaActiveStateDraft>(
    emptyCharacterXianxiaActiveStateDraft,
  );
  const [notesDraft, setNotesDraft] = useState<CharacterNotesDraft>(emptyCharacterNotesDraft);
  const [resourceDrafts, setResourceDrafts] = useState<Record<string, string>>({});
  const [spellSlotDrafts, setSpellSlotDrafts] = useState<Record<string, string>>({});
  const [inventoryDrafts, setInventoryDrafts] = useState<Record<string, string>>({});
  const [equipmentDrafts, setEquipmentDrafts] = useState<Record<string, CharacterEquipmentDraft>>({});
  const [xianxiaInventoryDrafts, setXianxiaInventoryDrafts] = useState<Record<string, CharacterXianxiaInventoryDraft>>({});
  const [newXianxiaInventoryDraft, setNewXianxiaInventoryDraft] = useState<CharacterXianxiaInventoryDraft>(
    xianxiaInventoryDraftFromItem(),
  );
  const [xianxiaDaoRequestDraft, setXianxiaDaoRequestDraft] = useState<CharacterXianxiaDaoUseRequestDraft>(
    emptyCharacterXianxiaDaoUseRequestDraft,
  );
  const [xianxiaDaoUseNotesDrafts, setXianxiaDaoUseNotesDrafts] = useState<Record<string, string>>({});
  const [arcaneArmorDraft, setArcaneArmorDraft] = useState(false);
  const [currencyDraft, setCurrencyDraft] = useState<Record<string, string>>({});
  const [portraitDraft, setPortraitDraft] = useState<CharacterPortraitDraft>(emptyCharacterPortraitDraft);
  const [controlsDraft, setControlsDraft] = useState<CharacterControlsDraft>(emptyCharacterControlsDraft);
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

  useEffect(() => {
    if (!detailQuery.data) {
      return;
    }
    const draftSnapshot = buildCharacterPaneDraftSnapshot(detailQuery.data.character);
    setEquipmentDrafts(draftSnapshot.equipmentDrafts);
    setXianxiaInventoryDrafts(draftSnapshot.xianxiaInventoryDrafts);
    setXianxiaDaoUseNotesDrafts(draftSnapshot.xianxiaDaoUseNotesDrafts);
    setXianxiaDaoRequestDraft(emptyCharacterXianxiaDaoUseRequestDraft());
    setArcaneArmorDraft(draftSnapshot.arcaneArmorEnabled);
    setVitalsDraft(draftSnapshot.vitalsDraft);
    setXianxiaVitalsDraft(draftSnapshot.xianxiaVitalsDraft);
    setXianxiaActiveDraft(draftSnapshot.xianxiaActiveDraft);
    setNotesDraft(draftSnapshot.notesDraft);
    setResourceDrafts(draftSnapshot.resourceDrafts);
    setSpellSlotDrafts(draftSnapshot.spellSlotDrafts);
    setInventoryDrafts(draftSnapshot.inventoryDrafts);
    setCurrencyDraft(draftSnapshot.currencyDraft);
    setPortraitDraft(draftSnapshot.portraitDraft);
    setControlsDraft(draftSnapshot.controlsDraft);
    if (portraitFileInputRef.current) {
      portraitFileInputRef.current.value = "";
    }
  }, [
    detailQuery.data?.character.state_record.revision,
    detailQuery.data?.character.controls?.assignment?.user_id,
    selectedSlug,
  ]);

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
  const definition = asRecord(detailRecord?.definition);
  const stats = asRecord(definition.stats);
  const spellcasting = asRecord(definition.spellcasting);
  const state = asRecord(detailRecord?.state_record.state);
  const overviewStatRowPayload = detailRecord?.overview_stat_rows;
  const rawOverviewStatRows = Array.isArray(overviewStatRowPayload) ? overviewStatRowPayload : [];
  const hasOverviewStatRows = rawOverviewStatRows.length > 0;
  const overviewStatRows = rawOverviewStatRows.map((row) => asRecordArray(row));
  const overviewStats = asRecordArray(detailRecord?.overview_stats);
  const xianxiaState = asRecord(state.xianxia);
  const vitals = asRecord(state.vitals);
  const resources = asRecordArray(state.resources);
  const spellSlots = asRecordArray(state.spell_slots);
  const inventory = asRecordArray(state.inventory);
  const currency = isXianxia ? asRecord(xianxiaState.currency) : asRecord(state.currency);
  const playerNotesHtml = readString(detailRecord?.player_notes_html);
  const physicalDescriptionHtml = readString(detailRecord?.physical_description_html);
  const personalBackgroundHtml = readString(detailRecord?.personal_background_html);
  const referenceSections = asRecordArray(detailRecord?.reference_sections);
  const dndAbilities = asRecordArray(detailRecord?.abilities);
  const dndSkills = asRecordArray(detailRecord?.skills);
  const dndProficiencyGroups = asRecordArray(detailRecord?.proficiency_groups);
  const hasDndAbilitySkillsContent = Boolean(dndAbilities.length || dndSkills.length || dndProficiencyGroups.length);
  const spells = asRecordArray(spellcasting.spells);
  const equipmentState = detailRecord?.equipment_state;
  const equipmentRows = equipmentState?.rows ?? [];
  const arcaneArmorState = detailRecord?.arcane_armor_state ?? equipmentState?.arcane_armor_state;
  const revision = detailRecord?.state_record.revision ?? 0;
  const presentedXianxia: CharacterPresentedXianxia = detailRecord?.presented_xianxia ?? {};
  const xianxiaInventory = presentedXianxia.inventory?.quantities ?? [];
  const xianxiaCurrency = presentedXianxia.inventory?.currency ?? [];
  const xianxiaDurability = presentedXianxia.resources?.durability ?? [];
  const xianxiaEnergies = presentedXianxia.resources?.energies ?? [];
  const xianxiaYinYang = presentedXianxia.resources?.yin_yang ?? [];
  const xianxiaDao = presentedXianxia.resources?.dao;
  const xianxiaInsight = presentedXianxia.resources?.insight;
  const xianxiaActionReference = asRecord(presentedXianxia.quick_reference?.actions);
  const xianxiaDefenseReference = asRecord(presentedXianxia.quick_reference?.defense);
  const skillUseGuardrails = asRecord(presentedXianxia.quick_reference?.skill_use_guardrails);
  const skillUseGuardrailRuleHref = readString(skillUseGuardrails.rule_href);
  const skillUseGuardrailRuleTitle = readString(skillUseGuardrails.rule_title, "Skills");
  const skillUseGuardrailReferenceLines = asStringArray(skillUseGuardrails.reference_lines);
  const hasSkillUseGuardrail = Boolean(skillUseGuardrailRuleHref) || skillUseGuardrailReferenceLines.length > 0;
  const xianxiaHonorInteractions = asRecord(presentedXianxia.quick_reference?.honor_interactions);
  const xianxiaHonorContexts = asRecordArray(xianxiaHonorInteractions.contexts);
  const xianxiaHonorReferenceLines = asStringArray(xianxiaHonorInteractions.reference_lines);
  const hasXianxiaHonorInteractions = Boolean(
    xianxiaHonorContexts.length ||
      xianxiaHonorReferenceLines.length ||
      readString(xianxiaHonorInteractions.summary) ||
      readString(xianxiaHonorInteractions.rule_href) ||
      readString(xianxiaHonorInteractions.status_label) ||
      readString(xianxiaHonorInteractions.status) ||
      readString(xianxiaHonorInteractions.support) ||
      readString(xianxiaHonorInteractions.support_label),
  );
  const xianxiaRuleTextReferences = asRecordArray(presentedXianxia.quick_reference?.rule_text_references);
  const xianxiaStanceBreak = asRecord(presentedXianxia.quick_reference?.stance_break);
  const xianxiaStanceBreakReferenceLines = asStringArray(xianxiaStanceBreak.reference_lines);
  const xianxiaStanceBreakRecoveryLines = asStringArray(xianxiaStanceBreak.recovery_lines);
  const hasXianxiaStanceBreak = Boolean(
    xianxiaStanceBreakReferenceLines.length ||
      xianxiaStanceBreakRecoveryLines.length ||
      readString(xianxiaStanceBreak.status_label) ||
      readString(xianxiaStanceBreak.status) ||
      readString(xianxiaStanceBreak.rule_href),
  );
  const xianxiaActiveStateStatus = joinDisplay([
    readString(presentedXianxia.active_state?.stance?.status_label),
    readString(presentedXianxia.active_state?.aura?.status_label),
  ]);
  const presentedSpells = collectPresentedSpells(detailRecord);
  const presentedSpellGroups = groupSpellsByLevel(presentedSpells, (spell) => spell.level_label);
  const rawSpellGroups = groupSpellsByLevel(spells, (spell) => readString(spell.level_label));
  const presentedInventory = detailRecord?.presented_inventory ?? [];
  const presentedInventoryByKey = useMemo(() => {
    const lookup = new Map<string, CharacterPresentedInventoryItem>();
    for (const item of presentedInventory) {
      for (const key of [item.id, item.item_ref]) {
        if (key) {
          lookup.set(key, item);
        }
      }
    }
    return lookup;
  }, [presentedInventory]);

  const isReadSurface = surface === "read";
  const isCombatSurface = surface === "combat";
  const canUseControls = isReadSurface && Boolean(permissions?.can_use_controls && controls?.available);
  const canManagePortrait = isReadSurface && canEdit;
  const surfaceMetaLabel = isReadSurface ? "Character sheet" : isCombatSurface ? "Combat Character" : "Session Character";
  const surfaceHeading = isReadSurface ? "Character Sheet" : isCombatSurface ? "Combat Character" : "Session Character";
  const embeddedHeaderDetails = selected
    ? [selected.class_level_text, selected.species, selected.background].filter((value) => Boolean(value))
    : [];

  useEffect(() => {
    if (isXianxia && activeCharacterSection === "overview") {
      setActiveCharacterSection("quick-reference");
    }
    if (isDnd && activeCharacterSection === "quick-reference") {
      setActiveCharacterSection("overview");
    }
    if (activeCharacterSection === "controls" && detailRecord && !canUseControls) {
      setActiveCharacterSection(isXianxia ? "quick-reference" : "overview");
    }
  }, [activeCharacterSection, canUseControls, detailRecord, isDnd, isXianxia]);

  const dndVisibleCharacterSections = canUseControls
    ? [...dndCharacterSections, { id: "controls" as CharacterSection, label: "Controls" }]
    : dndCharacterSections;
  const xianxiaVisibleCharacterSections = canUseControls
    ? [...xianxiaCharacterSections, { id: "controls" as CharacterSection, label: "Controls" }]
    : xianxiaCharacterSections;
  const visibleCharacterSections = isDnd ? dndVisibleCharacterSections : xianxiaVisibleCharacterSections;
  const readSurfaceSectionBaseUrl = selectedSlug
    ? `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(selectedSlug)}`
    : "";
  const readSurfaceDefaultSection = isXianxia ? "quick-reference" : "overview";
  const readSurfaceSectionUrl = (section: CharacterSection) => {
    if (section === readSurfaceDefaultSection) {
      return readSurfaceSectionBaseUrl;
    }
    return `${readSurfaceSectionBaseUrl}?page=${encodeURIComponent(section)}`;
  };
  const handleReadSurfaceSectionNavClick = (section: CharacterSection) => (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (!selectedSlug) {
      return;
    }
    event.preventDefault();
    selectCharacterSection(section);
  };

  const handleMutationSuccess = (response: { character: CharacterRecord }, message: string) => {
    if (selectedSlug) {
      const previousDetail = queryClient.getQueryData<CharacterDetailResponse>(["character-detail", campaignSlug, selectedSlug]);
      queryClient.setQueryData<CharacterDetailResponse>(["character-detail", campaignSlug, selectedSlug], {
        ok: true,
        character: response.character,
        links: previousDetail?.links,
      });
    }
    void listQuery.refetch();
    setStatusMessage(message);
    setErrorMessage(null);
  };

  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage(null);
    setErrorMessage(apiErrorMessage(error));
  };

  const patchVitals = useMutation({
    mutationFn: (payload: CharacterVitalsPatchPayload) =>
      apiClient.patchCharacterVitals(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Vitals saved."),
    onError: handleMutationError,
  });

  const patchResource = useMutation({
    mutationFn: ({ resourceId, payload }: { resourceId: string; payload: CharacterResourcePatchPayload }) =>
      apiClient.patchCharacterResource(campaignSlug, selectedSlug || "", resourceId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Resource saved."),
    onError: handleMutationError,
  });

  const patchSpellSlot = useMutation({
    mutationFn: ({ level, payload }: { level: number; payload: CharacterSpellSlotsPatchPayload }) =>
      apiClient.patchCharacterSpellSlots(campaignSlug, selectedSlug || "", level, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Spell slots saved."),
    onError: handleMutationError,
  });

  const patchInventory = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: CharacterInventoryPatchPayload }) =>
      apiClient.patchCharacterInventory(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory saved."),
    onError: handleMutationError,
  });

  const patchEquipmentState = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: CharacterEquipmentStatePatchPayload }) =>
      apiClient.patchCharacterEquipmentState(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Equipment state saved."),
    onError: handleMutationError,
  });

  const patchFeatureState = useMutation({
    mutationFn: ({ featureKey, payload }: { featureKey: string; payload: CharacterFeatureStatePatchPayload }) =>
      apiClient.patchCharacterFeatureState(campaignSlug, selectedSlug || "", featureKey, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Feature state saved."),
    onError: handleMutationError,
  });

  const patchXianxiaActiveState = useMutation({
    mutationFn: (payload: { expected_revision: number; active_stance_name?: string; active_aura_name?: string }) =>
      apiClient.patchCharacterXianxiaActiveState(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Active Stance and Aura saved."),
    onError: handleMutationError,
  });

  const postXianxiaDaoUseRequest = useMutation({
    mutationFn: (payload: CharacterXianxiaDaoUseRequestPayload) =>
      apiClient.postCharacterXianxiaDaoUseRequest(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setXianxiaDaoRequestDraft({ requestName: "", notes: "", preparedRecordIndex: "" });
      handleMutationSuccess(response, "Dao Immolating use request recorded.");
    },
    onError: handleMutationError,
  });

  const postXianxiaDaoUseRecord = useMutation({
    mutationFn: (payload: CharacterXianxiaDaoUseRecordPayload) =>
      apiClient.postCharacterXianxiaDaoUseRecord(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Dao Immolating one-use spend recorded."),
    onError: handleMutationError,
  });

  const addXianxiaInventoryItem = useMutation({
    mutationFn: (payload: { expected_revision: number; item: CharacterXianxiaInventoryItemPayload }) =>
      apiClient.addCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setNewXianxiaInventoryDraft(xianxiaInventoryDraftFromItem());
      handleMutationSuccess(response, "Inventory item added.");
    },
    onError: handleMutationError,
  });

  const patchXianxiaInventoryItem = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number; item: CharacterXianxiaInventoryItemPayload } }) =>
      apiClient.patchCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory item saved."),
    onError: handleMutationError,
  });

  const removeXianxiaInventoryItem = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number } }) =>
      apiClient.removeCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory item removed."),
    onError: handleMutationError,
  });

  const patchXianxiaInventoryEquipped = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number; is_equipped: boolean } }) =>
      apiClient.patchCharacterXianxiaInventoryEquipped(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Equipment state saved."),
    onError: handleMutationError,
  });

  const patchCurrency = useMutation({
    mutationFn: (payload: CharacterCurrencyPatchPayload) =>
      apiClient.patchCharacterCurrency(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Currency saved."),
    onError: handleMutationError,
  });

  const patchNotes = useMutation({
    mutationFn: (payload: CharacterNotesPatchPayload) =>
      apiClient.patchCharacterNotes(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Notes saved."),
    onError: handleMutationError,
  });

  const upsertPortrait = useMutation({
    mutationFn: (payload: CharacterPortraitUpsertPayload) =>
      apiClient.upsertCharacterPortrait(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      handleMutationSuccess(response, "Portrait saved.");
      setPortraitDraft((current) => ({ ...current, file: null, fileName: "" }));
      if (portraitFileInputRef.current) {
        portraitFileInputRef.current.value = "";
      }
    },
    onError: handleMutationError,
  });

  const deletePortrait = useMutation({
    mutationFn: (payload: { expected_revision: number }) =>
      apiClient.deleteCharacterPortrait(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      handleMutationSuccess(response, "Portrait removed.");
      setPortraitDraft({ file: null, fileName: "", altText: "", caption: "" });
      if (portraitFileInputRef.current) {
        portraitFileInputRef.current.value = "";
      }
    },
    onError: handleMutationError,
  });

  const portraitMutationPending = upsertPortrait.isPending || deletePortrait.isPending;

  const assignCharacterOwner = useMutation({
    mutationFn: (payload: { user_id: number }) =>
      apiClient.assignCharacterOwner(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, response.message || "Assignment saved."),
    onError: handleMutationError,
  });

  const clearCharacterOwner = useMutation({
    mutationFn: () => apiClient.clearCharacterOwner(campaignSlug, selectedSlug || ""),
    onSuccess: (response) => {
      setControlsDraft((current) => ({ ...current, assignedUserId: "" }));
      handleMutationSuccess(response, response.message || "Assignment cleared.");
    },
    onError: handleMutationError,
  });

  const deleteCharacterMutation = useMutation({
    mutationFn: (payload: { confirm_character_slug: string }) =>
      apiClient.deleteCharacter(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setStatusMessage(response.message || "Character deleted.");
      setErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["characters", campaignSlug] });
      window.location.assign(response.links?.gen2_roster_url || `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters`);
    },
    onError: handleMutationError,
  });

  const controlsMutationPending =
    assignCharacterOwner.isPending || clearCharacterOwner.isPending || deleteCharacterMutation.isPending;

  const previewRest = useMutation({
    mutationFn: (restType: "short" | "long") => apiClient.getCharacterRestPreview(campaignSlug, selectedSlug || "", restType),
    onSuccess: (response) => {
      setRestPreview(response.preview);
      setStatusMessage(null);
      setErrorMessage(null);
    },
    onError: handleMutationError,
  });

  const applyRest = useMutation({
    mutationFn: ({ restType, payload }: { restType: "short" | "long"; payload: { expected_revision: number } }) =>
      apiClient.applyCharacterRest(campaignSlug, selectedSlug || "", restType, payload),
    onSuccess: (response: CharacterRestApplyResponse) => {
      setRestPreview(null);
      handleMutationSuccess(response, "Rest applied.");
    },
    onError: handleMutationError,
  });

  const parseNumberInput = (value: string, label: string): number | null => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      setErrorMessage(`Enter a valid ${label}.`);
      setStatusMessage(null);
      return null;
    }
    return parsed;
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

  const openItemDetail = (item: { name: string; href?: string; description_html?: string; notes?: string }) => {
    setDetailDialog({
      eyebrow: "Item details",
      title: item.name || "Item",
      html: item.description_html || "",
      notes: item.notes || "",
      href: item.href || "",
    });
  };

  const openSpellDetail = (spell: CharacterPresentedSpell) => {
    const source = [spell.source, spell.reference].filter(Boolean).join(" | ");
    setDetailDialog({
      eyebrow: [spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell details",
      title: spell.name || "Spell",
      html: spell.description_html || "",
      notes: spell.management_note || "",
      href: spell.href || "",
      facts: [...spellDetailFacts(spell), ...(source ? [{ label: "Source", value: source }] : [])],
      badges: spell.badges ?? [],
    });
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

  const renderXianxiaRecordBody = (record: unknown): string => {
    const source = asRecord(record);
    return readString(source.body_html, readString(source.description_html));
  };

  const renderXianxiaRecordHtml = (record: unknown): JSX.Element | null => {
    const bodyHtml = renderXianxiaRecordBody(record);
    if (!bodyHtml) {
      return null;
    }
    return <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: bodyHtml }} />;
  };

  const renderXianxiaPoolCards = (
    pools: Array<{ key: string; label: string; current: number; max: number; temp?: number }>,
    options?: {
      className?: string;
      keyPrefix?: string;
    },
  ) =>
    pools.map((pool) => (
      <article className={options?.className ?? "resource-card"} key={options?.keyPrefix ? `${options.keyPrefix}-${pool.key}` : pool.key}>
        <h3>{pool.label}</h3>
        <p className="resource-card__value">
          Current {pool.current} / Max {pool.max}
        </p>
        {pool.temp ? <p className="meta">Temporary {pool.label}: {pool.temp}</p> : null}
      </article>
    ));

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
    const defaultSection = isXianxia ? "quick-reference" : "overview";
    const basePath = `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(selectedSlug)}`;
    const nextUrl = section === defaultSection ? basePath : `${basePath}?page=${encodeURIComponent(section)}`;
    window.history.replaceState(null, "", nextUrl);
  };

  const renderSessionSection = ({
    id,
    title,
    className,
    children,
  }: {
    id?: string;
    title: string;
    className?: string;
    children: React.ReactNode;
  }) => (
    <section className={`read-section${className ? ` ${className}` : ""}`} id={id}>
      <div className="section-heading">
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );

  const CharacterShell = "article";

  return (
    <div className={isReadSurface ? "page-layout character-layout character-read-content" : "session-pane-content"}>
      <CharacterShell
        className={
          isReadSurface
            ? "article card character-sheet character-read-shell"
            : "article card character-sheet session-character-sheet"
        }
        data-character-read-shell-root={isReadSurface ? "" : undefined}
        data-character-read-shell-page={isReadSurface ? activeCharacterSection || "overview" : undefined}
        data-character-read-shell-mode={isReadSurface ? "read" : undefined}
      >
        {isReadSurface ? (
          <header className="character-header">
            <div className="character-header__top">
              <div className="character-header__identity">
                <p className="eyebrow">Character sheet</p>
                <h1>{selected?.name || surfaceHeading}</h1>
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
        ) : (
          <header className="character-header">
            <div className="character-header__top">
              <div className="character-header__identity">
                <p className="eyebrow">{surfaceMetaLabel}</p>
                <h2>{selected?.name || surfaceHeading}</h2>
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
        )}

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
            <>
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
            </>
          )}
        </div>

        {listQuery.isLoading ? <p className="status status-neutral">Loading characters...</p> : null}
        {detailQuery.isLoading ? <p className="status status-neutral">Loading character...</p> : null}

        {selected ? (
          <article className="character-summary">
            <div className="character-summary__main">
              {selectedPortrait ? (
                <figure className="character-portrait">
                  <img src={selectedPortrait.url} alt={selectedPortrait.alt_text || selected.name} />
                  {selectedPortrait.caption ? <figcaption className="meta">{selectedPortrait.caption}</figcaption> : null}
                </figure>
              ) : null}
              <div>
                <h3>{selected.name}</h3>
                <p>
                  HP: {readNumber(vitals.current_hp, selected.current_hp)} / {readNumber(stats.max_hp, selected.max_hp)}
                </p>
                <p>Temp HP: {readNumber(vitals.temp_hp, selected.temp_hp)}</p>
                {selected.hit_dice?.value ? <p>Hit Dice: {selected.hit_dice.value}</p> : null}
                <p>Class: {selected.class_level_text || "Unknown"}</p>
                <p>System: {characterSystem(detailRecord)}</p>
              </div>
            </div>
            {selected.resource_preview?.length ? (
              <ul className="plain-list resource-preview-list">
                {selected.resource_preview.map((resource) => (
                  <li key={`${resource.label}-${resource.value}`}>
                    <span>{resource.label}</span>
                    <strong>{resource.value}</strong>
                  </li>
                ))}
              </ul>
            ) : null}
            {canManagePortrait ? (
              <form className="stack-form character-portrait-manager" onSubmit={submitPortrait}>
                <label className="field" htmlFor="character-portrait-file">
                  <span>Portrait image</span>
                  <input
                    id="character-portrait-file"
                    ref={portraitFileInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
                    disabled={portraitMutationPending}
                    onChange={handlePortraitFileChange}
                  />
                </label>
                <label className="field" htmlFor="character-portrait-alt">
                  <span>Alt text</span>
                  <input
                    id="character-portrait-alt"
                    type="text"
                    maxLength={200}
                    value={portraitDraft.altText}
                    disabled={portraitMutationPending}
                    onChange={(event) => setPortraitDraft((current) => ({ ...current, altText: event.currentTarget.value }))}
                  />
                </label>
                <label className="field" htmlFor="character-portrait-caption">
                  <span>Caption</span>
                  <input
                    id="character-portrait-caption"
                    type="text"
                    maxLength={300}
                    value={portraitDraft.caption}
                    disabled={portraitMutationPending}
                    onChange={(event) => setPortraitDraft((current) => ({ ...current, caption: event.currentTarget.value }))}
                  />
                </label>
                <div className="hero-actions character-portrait-manager__actions">
                  <button className="button" type="submit" disabled={portraitMutationPending || !portraitDraft.file}>
                    Save portrait
                  </button>
                  {selectedPortrait ? (
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={portraitMutationPending}
                      onClick={removePortrait}
                    >
                      Remove portrait
                    </button>
                  ) : null}
                  {portraitDraft.fileName ? <span className="meta">{portraitDraft.fileName}</span> : null}
                </div>
              </form>
            ) : null}
          </article>
        ) : null}

        {selected && detailRecord ? (
          <>
            <section className="session-bar session-bar--compact" id="session-vitals">
              <div className="session-bar__summary">
                <p className="eyebrow">{surfaceMetaLabel}</p>
                <h2>Vitals</h2>
              </div>
              <div className="session-bar__actions" id="session-rest">
                <button
                  type="button"
                  className="ghost-button"
                  disabled={previewRest.isPending || !canEdit}
                  onClick={() => previewRest.mutate("short")}
                >
                  Short rest
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={previewRest.isPending || !canEdit}
                  onClick={() => previewRest.mutate("long")}
                >
                  Long rest
                </button>
              </div>
              {isXianxia ? (
                <form onSubmit={submitXianxiaVitals} className="session-vitals-form session-vitals-form--compact">
                  {xianxiaVitalsFields.map((field) => (
                    <div className="session-vitals-form__group" key={field.key}>
                      <label htmlFor={`xianxia-${field.key}`} className="session-field">
                        <span>{field.label}</span>
                        <input
                          id={`xianxia-${field.key}`}
                          type="number"
                          value={xianxiaVitalsDraft[field.key]}
                          disabled={!canEdit}
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            setXianxiaVitalsDraft({
                              ...xianxiaVitalsDraft,
                              [field.key]: event.currentTarget.value,
                            })
                          }
                        />
                      </label>
                    </div>
                  ))}
                  <button type="submit" disabled={patchVitals.isPending || !canEdit}>
                    {patchVitals.isPending ? "Saving..." : "Save Xianxia pools"}
                  </button>
                </form>
              ) : (
                <form onSubmit={submitVitals} className="session-vitals-form session-vitals-form--compact">
                  <div className="session-vitals-form__group">
                    <label htmlFor="character-current-hp" className="session-field">
                      <span>Current HP</span>
                      <div className="session-number-inline">
                        <input
                          id="character-current-hp"
                          type="number"
                          value={vitalsDraft.currentHp}
                          disabled={!canEdit}
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })
                          }
                        />
                        <span> / {readNumber(stats.max_hp, selected?.max_hp)}</span>
                      </div>
                    </label>
                  </div>
                  <div className="session-vitals-form__group">
                    <label htmlFor="character-temp-hp" className="session-field">
                      <span>Temp HP</span>
                      <input
                        id="character-temp-hp"
                        type="number"
                        value={vitalsDraft.tempHp}
                        disabled={!canEdit}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })
                        }
                      />
                    </label>
                  </div>
                  <button type="submit" disabled={patchVitals.isPending || !canEdit}>
                    {patchVitals.isPending ? "Saving..." : "Save vitals"}
                  </button>
                </form>
              )}
              {restPreview ? (
                <section className="card session-card">
                  <div className="section-heading">
                    <h2>{restPreview.label} confirmation</h2>
                  </div>
                  <ul className="plain-list rest-preview-list">
                    {restPreview.changes.length ? (
                      restPreview.changes.map((change) => (
                        <li key={`${change.label}-${change.from_value}-${change.to_value}`}>
                          <strong>{change.label}</strong>: <span>{change.from_value} {"->"} {change.to_value}</span>
                        </li>
                      ))
                    ) : (
                      <li>No modeled state changes will be applied by this {restPreview.label.toLowerCase()}.</li>
                    )}
                  </ul>
                  <div className="hero-actions">
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={applyRest.isPending || !canEdit}
                      onClick={() =>
                        applyRest.mutate({
                          restType: restPreview.rest_type === "short" ? "short" : "long",
                          payload: { expected_revision: revision },
                        })
                      }
                    >
                      {applyRest.isPending ? "Applying..." : "Apply"}
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => setRestPreview(null)}
                      disabled={applyRest.isPending}
                    >
                      Cancel
                    </button>
                  </div>
                </section>
              ) : null}
            </section>

            {isDnd && !isReadSurface ? (
              <nav className="combat-workspace-nav session-character-section-nav" aria-label="Session character sections">
                {dndVisibleCharacterSections.map((section) => {
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
            ) : null}
            {isXianxia && !isReadSurface ? (
              <div className="character-subpage-nav-card">
                <nav className="character-subpage-nav" aria-label="Character subpages">
                  {xianxiaVisibleCharacterSections.map((section) => {
                    const isActive = activeCharacterSection === section.id;
                    return (
                      <button
                        key={section.id}
                        type="button"
                        className={isActive ? "button-link" : "ghost-button"}
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => selectCharacterSection(section.id)}
                      >
                        {section.label}
                      </button>
                    );
                  })}
                </nav>
              </div>
            ) : null}

            {isXianxia && activeCharacterSection === "quick-reference" ? (
              renderSessionSection({
                id: "xianxia-quick-reference",
                title: "Quick Reference",
                children: (
                  <>
                    <div className="glance-grid">
                      <article className="glance-card">
                        <span className="meta">Realm</span>
                        <strong>{readString(xianxiaActionReference.realm, readString(presentedXianxia.identity?.realm, "--"))}</strong>
                      </article>
                      <article className="glance-card">
                        <span className="meta">Actions per turn</span>
                        <strong>
                          {readString(
                            xianxiaActionReference.actions_per_turn,
                            stringFromUnknown(presentedXianxia.identity?.actions_per_turn, "--"),
                          )}
                        </strong>
                      </article>
                      <article className="glance-card">
                        <span className="meta">Defense</span>
                        <strong>
                          {stringFromUnknown(
                            xianxiaDefenseReference.value,
                            stringFromUnknown(presentedXianxia.equipment?.defense, "--"),
                          )}
                        </strong>
                      </article>
                      <article className="glance-card">
                        <span className="meta">Honor</span>
                        <strong>{readString(presentedXianxia.identity?.honor, "--")}</strong>
                      </article>
                      <article className="glance-card">
                        <span className="meta">Reputation</span>
                        <strong>{readString(presentedXianxia.identity?.reputation, "--")}</strong>
                      </article>
                      <article className="glance-card">
                        <span className="meta">Insight</span>
                        <strong>{xianxiaInsight ? `${xianxiaInsight.available} available / ${xianxiaInsight.spent} spent` : "--"}</strong>
                      </article>
                    </div>
                    <section className="read-section" id="xianxia-action-count">
                      <div className="section-heading">
                        <h2>Action count</h2>
                      </div>
                      <div className="glance-grid">
                        <article className="glance-card">
                          <span className="meta">Realm</span>
                          <strong>{readString(xianxiaActionReference.realm, readString(presentedXianxia.identity?.realm, "--"))}</strong>
                        </article>
                        <article className="glance-card">
                          <span className="meta">Actions per turn</span>
                          <strong>
                            {readString(
                              xianxiaActionReference.actions_per_turn,
                              stringFromUnknown(presentedXianxia.identity?.actions_per_turn, "--"),
                            )}
                          </strong>
                        </article>
                      </div>
                      {readString(xianxiaActionReference.formula) ? (
                        <p className="meta">Actions per turn = {readString(xianxiaActionReference.formula)}</p>
                      ) : null}
                    </section>
                    <section className="read-section" id="xianxia-defense-derivation">
                      <div className="section-heading">
                        <h2>Defense calculation</h2>
                      </div>
                      <div className="glance-grid">
                        <article className="glance-card">
                          <span className="meta">Base</span>
                          <strong>{stringFromUnknown(xianxiaDefenseReference.base, "--")}</strong>
                        </article>
                        <article className="glance-card">
                          <span className="meta">Manual armor bonus</span>
                          <strong>{stringFromUnknown(xianxiaDefenseReference.manual_armor_bonus, "--")}</strong>
                        </article>
                        <article className="glance-card">
                          <span className="meta">Constitution</span>
                          <strong>{stringFromUnknown(xianxiaDefenseReference.constitution, "--")}</strong>
                        </article>
                        <article className="glance-card">
                          <span className="meta">Defense</span>
                          <strong>
                            {stringFromUnknown(xianxiaDefenseReference.value, stringFromUnknown(presentedXianxia.equipment?.defense, "--"))}
                          </strong>
                        </article>
                      </div>
                      {readString(xianxiaDefenseReference.formula) ? (
                        <p className="meta">Defense = {readString(xianxiaDefenseReference.formula)}</p>
                      ) : null}
                    </section>
                    {(
                      readString(asRecord(presentedXianxia.quick_reference?.check_formula).formula) ||
                      readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus) ||
                      readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary)
                    ) ? (
                      <section className="read-section" id="xianxia-check-formula">
                        <div className="section-heading">
                          <h2>Check formula</h2>
                        </div>
                        <div className="glance-grid">
                          {readString(asRecord(presentedXianxia.quick_reference?.check_formula).formula) ? (
                            <article className="glance-card">
                              <span className="meta">Check</span>
                              <strong>{readString(asRecord(presentedXianxia.quick_reference?.check_formula).formula)}</strong>
                            </article>
                          ) : null}
                          {(readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus) ||
                          readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus_detail)) ? (
                            <article className="glance-card">
                              <span className="meta">Spend bonus</span>
                              <strong>{readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus, "--")}</strong>
                              {readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus_detail) ? (
                                <span className="meta">
                                  {readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus_detail)}
                                </span>
                              ) : null}
                            </article>
                          ) : null}
                        </div>
                        {readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary) ? (
                          <p className="meta">
                            Check formula = {readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary)}
                          </p>
                        ) : null}
                      </section>
                    ) : null}
                    {(
                      asRecordArray(asRecord(presentedXianxia.quick_reference?.difficulty_states).states).length ||
                      readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary)
                    ) ? (
                      <section className="read-section" id="xianxia-difficulty-states">
                        <div className="section-heading">
                          <h2>Difficulty states</h2>
                        </div>
                        <div className="glance-grid">
                          {asRecordArray(asRecord(presentedXianxia.quick_reference?.difficulty_states).states).map((state) => (
                            <article className="glance-card" key={readString(state.key, readString(state.label))}>
                              <span className="meta">{readString(state.label)}</span>
                              <strong>{readString(state.adjustment_label)}</strong>
                              <span className="meta">Final DC adjustment</span>
                            </article>
                          ))}
                        </div>
                        {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary) ? (
                          <p className="meta">
                            Difficulty states = {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary)}.
                          </p>
                        ) : null}
                        {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).resolution_note) ? (
                          <p className="meta">
                            {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).resolution_note)}
                          </p>
                        ) : null}
                      </section>
                    ) : null}
                    {hasXianxiaHonorInteractions ? (
                      <section className="read-section" id="xianxia-honor-interactions">
                        <div className="section-heading">
                          <h2>Honor interactions</h2>
                          {readString(xianxiaHonorInteractions.rule_href) ? (
                            <a className="button-link subtle" href={readString(xianxiaHonorInteractions.rule_href)}>
                              {`${readString(xianxiaHonorInteractions.rule_title, "Honor")} rule`}
                            </a>
                          ) : null}
                        </div>
                        {xianxiaHonorContexts.length ? (
                          <div className="glance-grid">
                            {xianxiaHonorContexts.map((context) => (
                              <article className="glance-card" key={readString(context.key, readString(context.label))}>
                                <span className="meta">{readString(context.label)}</span>
                                <strong>{readString(context.modifier_label, "--")}</strong>
                                <span className="meta">Interaction modifier</span>
                              </article>
                            ))}
                          </div>
                        ) : null}
                        <article className="detail-card">
                          <div className="section-heading">
                            <h3>Honor context</h3>
                            {readString(xianxiaHonorInteractions.status_label, readString(xianxiaHonorInteractions.status)) ? (
                              <span className="meta">
                                {readString(xianxiaHonorInteractions.status_label, readString(xianxiaHonorInteractions.status))}
                              </span>
                            ) : null}
                          </div>
                          {(readString(xianxiaHonorInteractions.support) || readString(xianxiaHonorInteractions.support_label)) ? (
                            <p className="meta">
                              {readString(xianxiaHonorInteractions.support, readString(xianxiaHonorInteractions.support_label))}
                            </p>
                          ) : null}
                          {xianxiaHonorReferenceLines.map((line, index) => (
                            <p key={`${line}-${index}`}>{line}</p>
                          ))}
                          {readString(xianxiaHonorInteractions.summary) ? (
                            <p className="meta">Honor interactions = {readString(xianxiaHonorInteractions.summary)}.</p>
                          ) : null}
                        </article>
                      </section>
                    ) : null}
                    {hasSkillUseGuardrail ? (
                      <section className="read-section" id="xianxia-skill-use-guardrails">
                        <div className="section-heading">
                          <h2>Skill use guardrails</h2>
                          {skillUseGuardrailRuleHref ? (
                            <a className="button-link subtle" href={skillUseGuardrailRuleHref}>
                              {`${skillUseGuardrailRuleTitle} rule`}
                            </a>
                          ) : null}
                        </div>
                        <article className="detail-card">
                          {skillUseGuardrailReferenceLines.map((line, index) => (
                            <p key={`${line}-${index}`}>{line}</p>
                          ))}
                        </article>
                      </section>
                    ) : null}
                    {xianxiaRuleTextReferences.length ? (
                      <section className="read-section" id="xianxia-rule-text-references">
                        <div className="section-heading">
                          <h2>Rules text references</h2>
                        </div>
                        <div className="detail-grid">
                          {xianxiaRuleTextReferences.map((reference) => (
                            <article className="detail-card" key={readString(reference.key, readString(reference.title))}>
                              <div className="section-heading">
                                <h3>{readString(reference.title, "Rule text reference")}</h3>
                                {readString(reference.support) || readString(reference.support_label) ? (
                                  <span className="meta">
                                    {readString(reference.support, readString(reference.support_label))}
                                  </span>
                                ) : null}
                              </div>
                              {readString(reference.rule_href) ? (
                                <p>
                                  <a href={readString(reference.rule_href)}>{`${readString(reference.title, "Rule")} rule`}</a>
                                </p>
                              ) : null}
                              {asStringArray(reference.reference_lines).map((line, index) => (
                                <p key={`${readString(reference.title, "Rule")}-${index}`}>{line}</p>
                              ))}
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}
                    {hasXianxiaStanceBreak ? (
                      <section className="read-section" id="xianxia-stance-break">
                        <div className="section-heading">
                          <h2>Stance Break</h2>
                          {readString(xianxiaStanceBreak.rule_href) ? (
                            <a className="button-link subtle" href={readString(xianxiaStanceBreak.rule_href)}>
                              {`${readString(xianxiaStanceBreak.rule_title, "Stance Break")} rule`}
                            </a>
                          ) : null}
                        </div>
                        <article className="detail-card">
                          <div className="section-heading">
                            <h3>Current Stance</h3>
                            {readString(xianxiaStanceBreak.status_label, readString(xianxiaStanceBreak.status)) ? (
                              <span className="meta">
                                {readString(xianxiaStanceBreak.status_label, readString(xianxiaStanceBreak.status))}
                              </span>
                            ) : null}
                          </div>
                          {xianxiaStanceBreakReferenceLines.map((line, index) => (
                            <p key={`${line}-${index}`}>{line}</p>
                          ))}
                          {xianxiaStanceBreakRecoveryLines.map((line, index) => (
                            <p key={`${line}-${index}`} className="meta">
                              {line}
                            </p>
                          ))}
                        </article>
                      </section>
                    ) : null}
                    {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).length ? (
                      <section className="read-section" id="xianxia-effort-damage">
                        <div className="section-heading">
                          <h2>Effort damage</h2>
                        </div>
                        <div className="glance-grid">
                          {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).map((entry) => (
                            <article className="glance-card" key={readString(entry.key, readString(entry.label))}>
                              <span className="meta">{readString(entry.label, "Effort")}</span>
                              <strong>{readString(entry.damage, "--")}</strong>
                              <span className="meta">Score {stringFromUnknown(entry.score, "--")}</span>
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}
                    {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).length ? (
                      <section className="read-section" id="xianxia-active-state-reminders">
                        <div className="section-heading">
                          <h2>Active Stance and Aura</h2>
                        </div>
                        <div className="detail-grid">
                          {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).map((reminder) => (
                            <article className="detail-card" key={readString(reminder.label, readString(reminder.title))}>
                              <div className="section-heading">
                                <h3>{readString(reminder.title, readString(reminder.label))}</h3>
                                {readString(reminder.status_label) ? (
                                  <span className="meta">{readString(reminder.status_label)}</span>
                                ) : null}
                              </div>
                              {readString(reminder.rule_href) ? (
                                <p>
                                  <a href={readString(reminder.rule_href)}>{`${readString(reminder.title, "Active stance and aura")} rule`}</a>
                                </p>
                              ) : null}
                              {readString(reminder.support_label) ? (
                                <p className="meta">{readString(reminder.support_label)}</p>
                              ) : null}
                              {asStringArray(reminder.reference_lines).map((line, index) => (
                                <p key={`${readString(reminder.label)}-${index}`}>{line}</p>
                              ))}
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}
                  </>
                ),
              })
            ) : null}

            {isXianxia && activeCharacterSection === "martial-arts" ? (
              renderSessionSection({
                id: "xianxia-martial-arts",
                title: "Martial Arts",
                children: (
                  <>
                    {asRecordArray(presentedXianxia.martial_arts).length ? (
                      <div className="feature-groups">
                        <section className="feature-group">
                          <div className="feature-stack">
                            {asRecordArray(presentedXianxia.martial_arts).map((rawArt, artIndex) => {
                              const art = asRecord(rawArt);
                              const rankProgress = asRecord(art.rank_progress);
                              const rankProgressSteps = asRecordArray(rankProgress.steps);
                              const learnedRanks = asRecordArray(art.learned_rank_refs);
                              const rankProgressSummary = readString(rankProgress.summary);
                              const rankProgressIncompleteNote = readString(rankProgress.incomplete_note);
                              const hasRankProgress = Boolean(
                                rankProgressSummary || rankProgressIncompleteNote || rankProgressSteps.length,
                              );
                              const bodyHtml = readString(art.body_html);
                              const artHref = readString(art.href);
                              return (
                                <article
                                  className="feature-row"
                                  key={draftKey(readString(art.name, "Martial Art"), stringFromUnknown(art.key), artIndex)}
                                >
                                  <div className="feature-row__header">
                                    <h3>{artHref ? <a href={artHref}>{readString(art.name, "Martial Art")}</a> : readString(art.name, "Martial Art")}</h3>
                                    <p className="meta">
                                      {joinDisplay([
                                        readString(art.systems_slug)
                                          ? `Source: ${readString(art.systems_slug)}${readString(art.systems_source_id) ? ` (${readString(art.systems_source_id)})` : ""}`
                                          : "",
                                        readString(art.current_rank) ? `Current rank: ${readString(art.current_rank)}` : "Rank not recorded",
                                        readString(art.current_rank_key)
                                          ? `Current rank key: ${readString(art.current_rank_key)}`
                                          : "",
                                        readString(art.rank_records_status)
                                          ? readString(art.rank_records_status).replace(/_/g, " ")
                                          : "",
                                        boolFromUnknown(art.starting_package) ? "Starting package" : "",
                                        boolFromUnknown(art.custom) ? "Custom Martial Art" : "",
                                      ])}
                                    </p>
                                  </div>
                                  {bodyHtml ? (
                                    <div className="detail-cluster">
                                      <details className="detail-card">
                                        <summary>Martial Art details</summary>
                                        <article dangerouslySetInnerHTML={{ __html: bodyHtml }} />
                                      </details>
                                    </div>
                                  ) : null}
                                  {hasRankProgress ? (
                                    <div className="detail-cluster">
                                      <div>
                                        <h4>Rank progress</h4>
                                        {rankProgressSummary ? <p className="meta">{rankProgressSummary}</p> : null}
                                        {rankProgressIncompleteNote ? (
                                          <p className="meta">
                                            <strong>Intentional draft content:</strong> {rankProgressIncompleteNote}
                                          </p>
                                        ) : null}
                                        {rankProgressSteps.length ? (
                                          <div className="skill-grid">
                                            {rankProgressSteps.map((rawStep) => {
                                              const step = asRecord(rawStep);
                                              const stepHref = readString(step.href);
                                              return (
                                                <div
                                                  className={
                                                    boolFromUnknown(step.is_learned)
                                                      ? "skill-pill skill-pill--proficient"
                                                      : "skill-pill"
                                                  }
                                                  key={readString(step.key, readString(step.label))}
                                                >
                                                  {stepHref ? (
                                                    <a href={stepHref}>{readString(step.label, "Rank step")}</a>
                                                  ) : (
                                                    <span>{readString(step.label, "Rank step")}</span>
                                                  )}
                                                  <span className="meta">{readString(step.status_label)}</span>
                                                </div>
                                              );
                                            })}
                                          </div>
                                        ) : null}
                                      </div>
                                    </div>
                                  ) : null}
                                  {learnedRanks.length ? (
                                    <div className="detail-cluster">
                                      <details className="detail-card">
                                        <summary>Learned rank abilities</summary>
                                        <div className="feature-stack">
                                          <div className="detail-cluster">
                                            <p>
                                              <strong>Learned ranks</strong>
                                            </p>
                                            <div className="skill-grid">
                                              {learnedRanks.map((rawRank, rankIndex) => {
                                                const rank = asRecord(rawRank);
                                                const rankHref = readString(rank.href);
                                                return (
                                                  <div
                                                    className={
                                                      !boolFromUnknown(rank.is_incomplete)
                                                        ? "skill-pill skill-pill--proficient"
                                                        : "skill-pill"
                                                    }
                                                    key={draftKey(readString(rank.key, readString(rank.label)), rankIndex)}
                                                  >
                                                    {rankHref ? (
                                                      <a href={rankHref}>{readString(rank.label, "Learned rank")}</a>
                                                    ) : (
                                                      <span>{readString(rank.label, "Learned rank")}</span>
                                                    )}
                                                    <span className="meta">{readString(rank.status_label)}</span>
                                                  </div>
                                                );
                                              })}
                                            </div>
                                          </div>
                                          {learnedRanks.map((rawRank, rankIndex) => {
                                            const rank = asRecord(rawRank);
                                            const rankAbilities = asRecordArray(rank.abilities);
                                            const rankLabel = readString(rank.label, "Rank");
                                            const rankInsightCost = numberFromUnknown(rank.insight_cost);
                                            if (!rankAbilities.length) {
                                              return null;
                                            }
                                            return (
                                              <div className="detail-cluster" key={draftKey(readString(rank.key), rankLabel, rankIndex)}>
                                                <p>
                                                  <strong>{`${rankLabel} Rank`}</strong>
                                                </p>
                                                <ul className="plain-list">
                                                  {readString(rank.rank_ref) ? <li className="meta">{`Rank ref: ${readString(rank.rank_ref)}`}</li> : null}
                                                  {readString(rank.energy_bonus_text) ? (
                                                    <li className="meta">{`Energy bonuses: ${readString(rank.energy_bonus_text)}`}</li>
                                                  ) : null}
                                                  {rankInsightCost ? <li className="meta">{`Insight cost: ${rankInsightCost}`}</li> : null}
                                                  {readString(rank.prerequisite_text) ? (
                                                    <li className="meta">{`Prerequisite: ${readString(rank.prerequisite_text)}`}</li>
                                                  ) : null}
                                                  {readString(rank.teacher_breakthrough_note) ? (
                                                    <li className="meta">{`Teacher/breakthrough: ${readString(rank.teacher_breakthrough_note)}`}</li>
                                                  ) : null}
                                                  {readString(rank.legendary_prerequisite_note) ? (
                                                    <li className="meta">{`Legendary prerequisite: ${readString(rank.legendary_prerequisite_note)}`}</li>
                                                  ) : null}
                                                </ul>
                                                <p>
                                                  <strong>{`${rankLabel} abilities`}</strong>
                                                </p>
                                                {rankAbilities.map((rawAbility) => {
                                                  const ability = asRecord(rawAbility);
                                                  const abilityHref = readString(ability.href);
                                                  const abilityText = readString(ability.text);
                                                  return (
                                                    <details className="feature-detail" key={draftKey(readString(ability.key), readString(ability.name))}>
                                                      <summary>
                                                        <div className="feature-row__header">
                                                          <h4>
                                                            {abilityHref ? <a href={abilityHref}>{readString(ability.name, "Ability")}</a> : readString(ability.name, "Ability")}
                                                          </h4>
                                                          <p className="meta">
                                                            {joinDisplay([
                                                              readString(ability.rank_label) ? `Rank: ${readString(ability.rank_label)}` : "",
                                                              readString(ability.kind) ? `Kind: ${readString(ability.kind)}` : "",
                                                              readString(ability.support_label) ? `Support: ${readString(ability.support_label)}` : "",
                                                            ])}
                                                          </p>
                                                        </div>
                                                      </summary>
                                                      <article>
                                                        {readString(ability.source_ref) ? (
                                                          <p className="meta">
                                                            <strong>Ability ref:</strong> {readString(ability.source_ref)}
                                                          </p>
                                                        ) : null}
                                                        {readString(ability.resource_cost_text) ? (
                                                          <p className="meta">
                                                            <strong>Costs:</strong> {readString(ability.resource_cost_text)}
                                                          </p>
                                                        ) : null}
                                                        {readString(ability.range_text) ? (
                                                          <p className="meta">
                                                            <strong>Range:</strong> {readString(ability.range_text)}
                                                          </p>
                                                        ) : null}
                                                        {readString(ability.damage_effort_text) ? (
                                                          <p className="meta">
                                                            <strong>Damage/Effort:</strong> {readString(ability.damage_effort_text)}
                                                          </p>
                                                        ) : null}
                                                        {readString(ability.duration_text) ? (
                                                          <p className="meta">
                                                            <strong>Duration:</strong> {readString(ability.duration_text)}
                                                          </p>
                                                        ) : null}
                                                        {abilityText ? (
                                                          <div className="article-body article-body--compact">
                                                            <p>{abilityText}</p>
                                                          </div>
                                                        ) : null}
                                                        {boolFromUnknown(ability.is_incomplete_rank) ? (
                                                          <p className="meta">
                                                            <strong>Incomplete draft:</strong>
                                                            {readString(ability.incomplete_rank_status)}
                                                            {readString(ability.incomplete_rank_status) && readString(ability.incomplete_rank_note) ? " - " : ""}
                                                            {readString(ability.incomplete_rank_note)}
                                                          </p>
                                                        ) : null}
                                                      </article>
                                                    </details>
                                                  );
                                                })}
                                              </div>
                                            );
                                          })}
                                        </div>
                                      </details>
                                    </div>
                                  ) : null}
                                </article>
                              );
                            })}
                          </div>
                        </section>
                      </div>
                    ) : (
                      <article className="detail-card">
                        <p className="meta">No Martial Arts are recorded on this sheet yet.</p>
                      </article>
                    )}
                  </>
                ),
              })
            ) : null}

            {isXianxia && activeCharacterSection === "techniques" ? (
              <section className="read-section" id="xianxia-techniques">
                <div className="section-heading">
                  <h2>Techniques</h2>
                </div>
                <div className="detail-grid">
                  <article className="detail-card">
                    <h3>Known Generic Techniques</h3>
                    {asRecordArray(presentedXianxia.generic_techniques).length ? (
                      <ul className="plain-list slot-list">
                        {asRecordArray(presentedXianxia.generic_techniques).map((data, index) => {
                          const techniqueName = readString(data.name, "Unnamed technique");
                          const techniqueHref = readString(data.href);
                          const techniqueBody = renderXianxiaRecordBody(data);
                          const supportLabel = readString(data.support_label);
                          const insightCost = readNumber(data.insight_cost);
                          const prerequisites = readString(data.prerequisites);
                          const resourceCosts = readString(data.resource_costs);
                          const rangeTags = readString(data.range_tags);
                          const effortTags = readString(data.effort_tags);
                          const resetCadence = readString(data.reset_cadence);
                          const learnableWithoutMaster = boolFromUnknown(data.learnable_without_master);
                          const requiresMaster = boolFromUnknown(data.requires_master);
                          const metaLine = [
                            rangeTags ? `Range: ${rangeTags}` : "",
                            effortTags ? `Effort: ${effortTags}` : "",
                            resetCadence ? `Reset: ${resetCadence}` : "",
                          ]
                            .filter(Boolean)
                            .join(" | ");

                          const detailsKey = draftKey("xianxia-generic-technique", techniqueName, techniqueHref);
                          return (
                            <React.Fragment key={`${detailsKey}-${index}`}>
                              <li>
                                {techniqueHref ? (
                                  <a href={techniqueHref}>{techniqueName}</a>
                                ) : (
                                  <span>{techniqueName}</span>
                                )}
                                {supportLabel ? <strong>{supportLabel}</strong> : null}
                                {insightCost ? <span className="meta">Insight {insightCost}</span> : null}
                              </li>
                              {techniqueBody ? (
                                <li>
                                  <details className="detail-card">
                                    <summary>Technique details</summary>
                                    <article>{renderXianxiaRecordHtml(data)}</article>
                                  </details>
                                </li>
                              ) : null}
                              {prerequisites ? <li className="meta">Prerequisites: {prerequisites}</li> : null}
                              {resourceCosts ? <li className="meta">Resource Costs: {resourceCosts}</li> : null}
                              {metaLine ? <li className="meta">{metaLine}</li> : null}
                              {learnableWithoutMaster || requiresMaster ? (
                                <li className="meta">
                                  {learnableWithoutMaster ? "Learnable without a Master" : requiresMaster ? "Master required" : null}
                                </li>
                              ) : null}
                            </React.Fragment>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="meta">No Generic Techniques are recorded on this sheet yet.</p>
                    )}
                  </article>
                  <article className="detail-card">
                    <h3>Basic Actions</h3>
                    {asRecordArray(presentedXianxia.basic_actions).length ? (
                      <ul className="plain-list slot-list">
                        {asRecordArray(presentedXianxia.basic_actions).map((data, index) => {
                          const actionName = readString(data.title, readString(data.name, "Unnamed action"));
                          const actionHref = readString(data.href);
                          const supportLabel = readString(data.support_label);
                          const actionBody = renderXianxiaRecordBody(data);
                          const rangeTags = readString(data.range_tags);
                          const timingTags = readString(data.timing_tags);
                          const metaLine = [rangeTags ? `Range: ${rangeTags}` : "", timingTags ? `Timing: ${timingTags}` : ""]
                            .filter(Boolean)
                            .join(" | ");
                          const detailKey = draftKey("xianxia-basic-action", actionName, actionHref);

                          return (
                            <React.Fragment key={`${detailKey}-${index}`}>
                              <li>
                                {actionHref ? <a href={actionHref}>{actionName}</a> : <span>{actionName}</span>}
                                {supportLabel ? <strong>{supportLabel}</strong> : null}
                              </li>
                              {actionBody ? (
                                <li>
                                  <details className="detail-card">
                                    <summary>Action details</summary>
                                    <article>{renderXianxiaRecordHtml(data)}</article>
                                  </details>
                                </li>
                              ) : null}
                              {metaLine ? <li className="meta">{metaLine}</li> : null}
                            </React.Fragment>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="meta">No Basic Action Systems entries are available for this campaign.</p>
                    )}
                  </article>
                  {asRecordArray(presentedXianxia.approval?.status_groups).map((group, groupIndex) => {
                    const groupKey = readString(group.key);
                    const groupTitle = readString(group.title, "Approval records");
                    const groupId = groupKey ? `xianxia-approval-${groupKey.replace(/_/g, "-")}` : undefined;
                    const approvalRecords = asRecordArray(group.records);
                    const isDaoImmolatingUseRecords = groupKey === "dao_immolating_use_records";
                    const canRecordThisDaoUse =
                      isDaoImmolatingUseRecords &&
                      canRecordXianxiaDaoUse &&
                      approvalRecords.some(
                        (record) =>
                          readString(record.status_key) === "approved" &&
                          !boolFromUnknown(record.used) &&
                          record.use_record_index !== undefined,
                      );

                    return (
                      <article className="detail-card" key={groupKey || draftKey("xianxia-approval-group", groupIndex)} id={groupId}>
                        <h3>{groupTitle}</h3>
                        {approvalRecords.length ? (
                          <ul className="plain-list slot-list">
                            {approvalRecords.map((record, recordIndex) => {
                              const data = asCharacterXianxiaNamedRecord(record);
                              const recordName = readString(data.name, "Unnamed record");
                              const statusLabel = readString(data.status_label, readString(data.status, "Unknown"));
                              const statusKey = readString(data.status_key, "unknown");
                              const typeLabel = readString(data.type_label, readString(data.type));
                              const sourceLabel = readString(data.source_label);
                              const approvalTimestamp = readString(data.approval_timestamp);
                              const notes = readString(data.notes);
                              const baseAbilityRef = readString(data.base_ability_ref);
                              const baseAbilityKind = readString(data.base_ability_kind);
                              const techniqueAnchor = readString(data.technique_anchor_label);
                              const techniqueAnchorWarning = readString(data.technique_anchor_warning);
                              const insightCost = isDaoImmolatingUseRecords
                                ? readNumber(data.insight_cost, 10)
                                : readNumber(data.insight_cost);
                              const preparedRecordName = readString(data.prepared_record_name);
                              const preparedRecordIndex = readNumber(data.prepared_record_index, 0);
                              const preparedRecordNotes = readString(data.prepared_record_notes);
                              const oneUseUsed = boolFromUnknown(data.used);
                              const insightSpent = readNumber(data.insight_spent);
                              const useRecordDraftKey = xianxiaDaoUseRecordDraftKey(data);
                              const useNotes = xianxiaDaoUseNotesDrafts[useRecordDraftKey] ?? "";
                              const spendDisabled = insightCost > (xianxiaInsight?.available ?? 0);
                              const canRecordThisRecord =
                                isDaoImmolatingUseRecords &&
                                canRecordThisDaoUse &&
                                readString(data.status_key) === "approved" &&
                                !boolFromUnknown(data.used) &&
                                data.use_record_index !== undefined;

                              return (
                                <React.Fragment
                                  key={`${groupKey ?? "approval"}-${recordName}-${data.use_record_index ?? recordIndex}-${recordIndex}`}
                                >
                                  <li className="approval-record__heading">
                                    <span>{recordName}</span>
                                    <span className={`meta-badge approval-state-badge approval-state-badge--${statusKey}`}>
                                      Approval state: {statusLabel}
                                    </span>
                                  </li>
                                  {(typeLabel || sourceLabel) ? <li className="meta">{joinDisplay([typeLabel, sourceLabel])}</li> : null}
                                  {notes ? <li className="meta">{notes}</li> : null}
                                  {approvalTimestamp ? <li className="meta">Approval timestamp: {approvalTimestamp}</li> : null}
                                  {groupKey && ["karmic_constraints", "ascendant_arts"].includes(groupKey) ? (
                                    <>
                                      {baseAbilityRef ? <li className="meta">Base ability ref: {baseAbilityRef}</li> : null}
                                      {baseAbilityKind ? <li className="meta">Base ability kind: {baseAbilityKind}</li> : null}
                                      {techniqueAnchor ? <li className="meta">Technique anchor: {techniqueAnchor}</li> : null}
                                      {techniqueAnchorWarning ? <li className="meta">{techniqueAnchorWarning}</li> : null}
                                    </>
                                  ) : null}
                                  {isDaoImmolatingUseRecords ? (
                                    <>
                                      <li className="meta">Insight cost: {insightCost}</li>
                                      {(preparedRecordName || preparedRecordNotes || data.prepared_record_index !== undefined) ? (
                                        <li className="meta">
                                          Prepared support: {preparedRecordName || `Prepared note #${preparedRecordIndex + 1}`}
                                        </li>
                                      ) : null}
                                      {preparedRecordNotes ? <li className="meta">{preparedRecordNotes}</li> : null}
                                      {oneUseUsed ? (
                                        <li className="meta">One-use history: used; Insight spent {insightSpent}</li>
                                      ) : (
                                        <li className="meta">One-use history: not recorded yet</li>
                                      )}
                                      {data.use_notes && oneUseUsed ? <li className="meta">{data.use_notes}</li> : null}
                                      {canRecordThisRecord ? (
                                        <li>
                                          <form
                                            onSubmit={(event) => submitXianxiaDaoUseRecord(event, data)}
                                            className="session-vitals-form"
                                          >
                                            <label
                                              htmlFor={`xianxia-dao-use-notes-${useRecordDraftKey}`}
                                              className="session-field"
                                            >
                                              <span>Use notes</span>
                                              <textarea
                                                id={`xianxia-dao-use-notes-${useRecordDraftKey}`}
                                                rows={2}
                                                value={useNotes}
                                                onChange={(event) =>
                                                  setXianxiaDaoUseNotesDrafts({
                                                    ...xianxiaDaoUseNotesDrafts,
                                                    [useRecordDraftKey]: event.currentTarget.value,
                                                  })
                                                }
                                              />
                                            </label>
                                            {spendDisabled ? <p className="meta">Needs {insightCost} Insight.</p> : null}
                                            <button
                                              type="submit"
                                              className="button-link"
                                              disabled={postXianxiaDaoUseRecord.isPending || spendDisabled}
                                            >
                                              {postXianxiaDaoUseRecord.isPending ? "Saving..." : "Record one-use spend"}
                                            </button>
                                          </form>
                                        </li>
                                      ) : null}
                                    </>
                                  ) : null}
                                </React.Fragment>
                              );
                            })}
                          </ul>
                        ) : (
                          <p className="meta">{readString(group.empty_message)}</p>
                        )}
                      </article>
                    );
                  })}
                  <article className="detail-card">
                    <h3>Prepared Dao Immolating Techniques</h3>
                    {asRecordArray(presentedXianxia.approval?.dao_immolating_prepared).length ? (
                      <ul className="plain-list slot-list">
                        {asRecordArray(presentedXianxia.approval?.dao_immolating_prepared).map((data, index) => {
                          const recordName = readString(data.name, `Prepared note ${index + 1}`);
                          const supportLabel = readString(data.status, readString(data.type));
                          return (
                            <React.Fragment key={`xianxia-dao-immolating-prepared-${recordName}-${index}`}>
                              <li>
                                <span>{recordName}</span>
                                {supportLabel ? <strong>{supportLabel}</strong> : null}
                              </li>
                              {readString(data.notes) ? <li className="meta">{readString(data.notes)}</li> : null}
                            </React.Fragment>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="meta">No prepared Dao Immolating Technique notes yet.</p>
                    )}
                  </article>
                  {canEdit ? (
                    <article className="detail-card" id="xianxia-dao-immolating-use-request">
                      <h3>Ad Hoc Dao Immolating Use Request</h3>
                      <form onSubmit={submitXianxiaDaoUseRequest} className="session-vitals-form">
                        <label className="session-field" htmlFor="xianxia-dao-request-name">
                          <span>Request name</span>
                          <input
                            id="xianxia-dao-request-name"
                            value={xianxiaDaoRequestDraft.requestName}
                            required={!(asRecordArray(presentedXianxia.approval?.dao_immolating_prepared).length > 0)}
                            disabled={postXianxiaDaoUseRequest.isPending}
                            onChange={(event) =>
                              setXianxiaDaoRequestDraft({
                                ...xianxiaDaoRequestDraft,
                                requestName: event.currentTarget.value,
                              })
                            }
                          />
                        </label>
                        {asRecordArray(presentedXianxia.approval?.dao_immolating_prepared).length ? (
                          <>
                            <label className="session-field" htmlFor="xianxia-dao-prepared-record">
                              <span>Prepared note</span>
                              <select
                                id="xianxia-dao-prepared-record"
                                value={xianxiaDaoRequestDraft.preparedRecordIndex}
                                disabled={postXianxiaDaoUseRequest.isPending}
                                onChange={(event) =>
                                  setXianxiaDaoRequestDraft({
                                    ...xianxiaDaoRequestDraft,
                                    preparedRecordIndex: event.currentTarget.value,
                                  })
                                }
                              >
                                <option value="">No prepared note</option>
                                {asRecordArray(presentedXianxia.approval?.dao_immolating_prepared).map((record, index) => {
                                  const preparedRecordName = readString(record.name, `Prepared note ${index + 1}`);
                                  return (
                                    <option key={draftKey(preparedRecordName, index)} value={String(index)}>
                                      {preparedRecordName}
                                    </option>
                                  );
                                })}
                              </select>
                            </label>
                          </>
                        ) : null}
                        <label className="session-field" htmlFor="xianxia-dao-request-notes">
                          <span>Request notes</span>
                          <textarea
                            id="xianxia-dao-request-notes"
                            rows={3}
                            value={xianxiaDaoRequestDraft.notes}
                            disabled={postXianxiaDaoUseRequest.isPending}
                            onChange={(event) =>
                              setXianxiaDaoRequestDraft({
                                ...xianxiaDaoRequestDraft,
                                notes: event.currentTarget.value,
                              })
                            }
                          />
                        </label>
                        <button type="submit" className="button-link" disabled={postXianxiaDaoUseRequest.isPending}>
                          {postXianxiaDaoUseRequest.isPending ? "Saving..." : "Record use request"}
                        </button>
                      </form>
                    </article>
                  ) : null}
                </div>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "resources" ? (
              <section className="read-section" id="xianxia-resources">
                <div className="section-heading">
                  <h2>Resources</h2>
                </div>
                <div className="resource-grid">
                  {xianxiaDurability.length ? renderXianxiaPoolCards(xianxiaDurability, { keyPrefix: "durability" }) : null}
                  {xianxiaEnergies.length ? renderXianxiaPoolCards(xianxiaEnergies, { keyPrefix: "energies" }) : null}
                  {xianxiaYinYang.length ? renderXianxiaPoolCards(xianxiaYinYang, { keyPrefix: "yin-yang" }) : null}
                  {xianxiaDao ? (
                    <article className="resource-card">
                      <h3>Dao</h3>
                      <p className="resource-card__value">
                        Current {xianxiaDao.current} / Max {xianxiaDao.max}
                      </p>
                    </article>
                  ) : null}
                  {xianxiaInsight ? (
                    <article className="resource-card">
                      <h3>Insight</h3>
                      <p className="resource-card__value">{readNumber(xianxiaInsight.available, 0)}</p>
                      <p className="meta">Spent {readNumber(xianxiaInsight.spent, 0)}</p>
                    </article>
                  ) : null}
                </div>
                <article className="detail-card" id="session-active-state">
                  <div className="section-heading">
                    <h3>Active Stance and Aura</h3>
                    {xianxiaActiveStateStatus ? <p className="meta">{xianxiaActiveStateStatus}</p> : null}
                  </div>
                  <form onSubmit={submitXianxiaActiveState} className="session-vitals-form">
                    <label className="session-field" htmlFor="xianxia-active-stance">
                      <span>Active Stance</span>
                      <input
                        id="xianxia-active-stance"
                        value={xianxiaActiveDraft.activeStanceName}
                        disabled={!canEdit}
                        onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeStanceName: event.currentTarget.value })}
                      />
                    </label>
                    <label className="session-field" htmlFor="xianxia-active-aura">
                      <span>Active Aura</span>
                      <input
                        id="xianxia-active-aura"
                        value={xianxiaActiveDraft.activeAuraName}
                        disabled={!canEdit}
                        onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeAuraName: event.currentTarget.value })}
                      />
                    </label>
                    <button type="submit" className="button-link" disabled={patchXianxiaActiveState.isPending || !canEdit}>
                      {patchXianxiaActiveState.isPending ? "Saving..." : "Save Active Stance and Aura"}
                    </button>
                  </form>
                </article>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "skills" ? (
              <section className="read-section" id="xianxia-skills">
                <div className="section-heading">
                  <h2>Skills</h2>
                </div>
                {presentedXianxia.skills?.trained?.length ? (
                  <div className="skill-grid">
                    {presentedXianxia.skills.trained.map((skill) => (
                      <div className="skill-pill skill-pill--proficient" key={skill.name}>
                        <span>{skill.name}</span>
                        <span className="meta">Trained</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <article className="detail-card">
                    <p className="meta">No trained skills are recorded on this sheet yet.</p>
                  </article>
                )}
                {hasSkillUseGuardrail ? (
                  <div className="detail-cluster" id="xianxia-skills-guardrail">
                    <div className="section-heading">
                      <h3>Skill use guardrails</h3>
                      {skillUseGuardrailRuleHref ? (
                        <a className="button-link subtle" href={skillUseGuardrailRuleHref}>
                          {`${skillUseGuardrailRuleTitle} rule`}
                        </a>
                      ) : null}
                    </div>
                    {skillUseGuardrailReferenceLines.length ? (
                      <article className="detail-card">
                        {skillUseGuardrailReferenceLines.map((line, index) => (
                          <p key={`${line}-${index}`}>{line}</p>
                        ))}
                      </article>
                    ) : null}
                  </div>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "equipment" ? (
              <section className="read-section" id="xianxia-equipment">
                <div className="section-heading">
                  <h2>Equipment</h2>
                </div>
                <div className="detail-grid">
                  <article className="detail-card">
                    <h3>Defense calculation</h3>
                    {Object.keys(xianxiaDefenseReference).length ? (
                      <>
                        <p><strong>{stringFromUnknown(xianxiaDefenseReference.value, "--")}</strong></p>
                        <ul className="plain-list slot-list">
                          <li><span>Base</span><strong>{stringFromUnknown(xianxiaDefenseReference.base, "--")}</strong></li>
                          <li><span>Manual armor bonus</span><strong>{stringFromUnknown(xianxiaDefenseReference.manual_armor_bonus, "--")}</strong></li>
                          <li><span>Constitution</span><strong>{stringFromUnknown(xianxiaDefenseReference.constitution, "--")}</strong></li>
                        </ul>
                        <p className="meta">Defense = {readString(xianxiaDefenseReference.formula, "")}</p>
                      </>
                    ) : (
                      <p><strong>{stringFromUnknown(presentedXianxia.equipment?.defense, "--")}</strong></p>
                    )}
                    <p className="meta">Manual armor bonus: {readNumber(presentedXianxia.equipment?.manual_armor_bonus, 0)}</p>
                  </article>
                  <article className="detail-card">
                    <h3>Necessary weapons</h3>
                    {presentedXianxia.equipment?.necessary_weapons?.length ? (
                      <ul className="plain-list slot-list">
                        {presentedXianxia.equipment.necessary_weapons.map((record, index) => (
                          <li key={`${record.name}-${index}`}>
                            <span>{record.name}</span>
                            {record.reason ? <strong>{record.reason}</strong> : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="meta">No necessary weapons are recorded on this sheet yet.</p>
                    )}
                  </article>
                  <article className="detail-card">
                    <h3>Necessary tools</h3>
                    {presentedXianxia.equipment?.necessary_tools?.length ? (
                      <ul className="plain-list slot-list">
                        {presentedXianxia.equipment.necessary_tools.map((record, index) => (
                          <li key={`${record.name}-${index}`}>
                            <span>{record.name}</span>
                            {record.reason ? <strong>{record.reason}</strong> : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="meta">No necessary tools are recorded on this sheet yet.</p>
                    )}
                  </article>
                  <article className="detail-card">
                    <h3>Equipped inventory</h3>
                    {presentedXianxia.equipment?.equipped_items?.length ? (
                      <ul className="plain-list slot-list">
                        {presentedXianxia.equipment.equipped_items.map((item) => (
                          <React.Fragment key={item.id}>
                            <li>
                              <span>{item.name}</span>
                              <strong>{readString(item.item_type)}</strong>
                            </li>
                            {readString(item.item_type) === "Armor" ? (
                              <li className="meta">Armor is displayed here only; Defense still uses the manual armor bonus above.</li>
                            ) : null}
                            {item.notes ? <li className="meta">{item.notes}</li> : null}
                          </React.Fragment>
                        ))}
                      </ul>
                    ) : (
                      <p className="meta">No equippable inventory is currently marked equipped.</p>
                    )}
                  </article>
                </div>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "inventory" ? (
              <section className="read-section" id="xianxia-inventory">
                <div className="section-heading">
                  <h2>Inventory</h2>
                </div>
                {xianxiaInventory.length ? (
                  <div className="inventory-list">
                    {xianxiaInventory.map((item) => {
                      const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
                      return (
                        <article className="inventory-row" key={item.id}>
                          <div className="inventory-row__header">
                            <h4>{item.name}</h4>
                            <strong>x{item.quantity}</strong>
                          </div>
                          <p className="meta">{joinDisplay([item.item_nature, item.item_type, item.is_equipped ? "Equipped" : ""])}</p>
                          {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                          {item.notes ? <p className="meta">{item.notes}</p> : null}
                          {canEdit ? (
                            <div className="detail-cluster">
                              <details className="detail-card">
                                <summary>Edit item</summary>
                                <form onSubmit={(event) => submitXianxiaInventoryUpdate(event, item)} className="stack-form">
                                  <div className="builder-field-grid">
                                    <label className="session-field" htmlFor={`xianxia-inventory-name-${item.id}`}>
                                      <span>Name</span>
                                      <input
                                        id={`xianxia-inventory-name-${item.id}`}
                                        value={draft.name}
                                        onChange={(event) =>
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, name: event.currentTarget.value },
                                          })
                                        }
                                      />
                                    </label>
                                    <label className="session-field" htmlFor={`xianxia-inventory-quantity-${item.id}`}>
                                      <span>Quantity</span>
                                      <input
                                        id={`xianxia-inventory-quantity-${item.id}`}
                                        type="number"
                                        min="0"
                                        value={draft.quantity}
                                        onChange={(event) =>
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, quantity: event.currentTarget.value },
                                          })
                                        }
                                      />
                                    </label>
                                    <label className="session-field" htmlFor={`xianxia-inventory-nature-${item.id}`}>
                                      <span>Nature</span>
                                      <select
                                        id={`xianxia-inventory-nature-${item.id}`}
                                        value={draft.itemNature}
                                        onChange={(event) =>
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, itemNature: event.currentTarget.value },
                                          })
                                        }
                                      >
                                        <option value="Mundane">Mundane</option>
                                        <option value="Relic">Relic</option>
                                      </select>
                                    </label>
                                    <label className="session-field" htmlFor={`xianxia-inventory-type-${item.id}`}>
                                      <span>Type</span>
                                      <select
                                        id={`xianxia-inventory-type-${item.id}`}
                                        value={draft.itemType}
                                        onChange={(event) =>
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, itemType: event.currentTarget.value },
                                          })
                                        }
                                      >
                                        <option value="Weapon">Weapon</option>
                                        <option value="Armor">Armor</option>
                                        <option value="Artifact">Artifact</option>
                                        <option value="Consumable">Consumable</option>
                                        <option value="Miscellaneous">Miscellaneous</option>
                                      </select>
                                    </label>
                                    <label className="session-field" htmlFor={`xianxia-inventory-tags-${item.id}`}>
                                      <span>Tags</span>
                                      <input
                                        id={`xianxia-inventory-tags-${item.id}`}
                                        value={draft.tags}
                                        onChange={(event) =>
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, tags: event.currentTarget.value },
                                          })
                                        }
                                      />
                                    </label>
                                    <label className="session-field" htmlFor={`xianxia-inventory-notes-${item.id}`}>
                                      <span>Notes</span>
                                      <textarea
                                        id={`xianxia-inventory-notes-${item.id}`}
                                        rows={3}
                                        value={draft.notes}
                                        onChange={(event) =>
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, notes: event.currentTarget.value },
                                          })
                                        }
                                      />
                                    </label>
                                  </div>
                                  <label className="toggle-row">
                                    <input
                                      type="checkbox"
                                      checked={draft.equippable}
                                      onChange={(event) =>
                                        setXianxiaInventoryDrafts({
                                          ...xianxiaInventoryDrafts,
                                          [item.id]: { ...draft, equippable: event.currentTarget.checked },
                                        })
                                      }
                                    />
                                    Equippable
                                  </label>
                                  {draft.equippable ? (
                                    <label className="toggle-row">
                                      <input
                                        type="checkbox"
                                        checked={draft.isEquipped}
                                        onChange={(event) => {
                                          const isEquipped = event.currentTarget.checked;
                                          setXianxiaInventoryDrafts({
                                            ...xianxiaInventoryDrafts,
                                            [item.id]: { ...draft, isEquipped },
                                          });
                                          toggleXianxiaInventoryEquipped(item, isEquipped);
                                        }}
                                      />
                                      Equipped
                                    </label>
                                  ) : null}
                                  <button type="submit" disabled={patchXianxiaInventoryItem.isPending}>
                                    {patchXianxiaInventoryItem.isPending ? "Saving..." : "Save item"}
                                  </button>
                                </form>
                              </details>
                              <button
                                type="button"
                                className="button-link subtle"
                                disabled={removeXianxiaInventoryItem.isPending}
                                onClick={() => removeXianxiaInventory(item)}
                              >
                                {removeXianxiaInventoryItem.isPending ? "Removing..." : "Remove"}
                              </button>
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No Xianxia inventory items.</p>
                )}
                {canEdit ? (
                  <article className="detail-card session-card" id="xianxia-inventory-add">
                    <h3>Add inventory item</h3>
                    <form onSubmit={submitXianxiaInventoryAdd} className="stack-form">
                      <div className="builder-field-grid">
                        <label className="session-field" htmlFor="xianxia-new-item-name">
                          <span>Name</span>
                          <input
                            id="xianxia-new-item-name"
                            value={newXianxiaInventoryDraft.name}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, name: event.currentTarget.value })
                            }
                          />
                        </label>
                        <label className="session-field" htmlFor="xianxia-new-item-quantity">
                          <span>Quantity</span>
                          <input
                            id="xianxia-new-item-quantity"
                            type="number"
                            min="0"
                            value={newXianxiaInventoryDraft.quantity}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, quantity: event.currentTarget.value })
                            }
                          />
                        </label>
                        <label className="session-field" htmlFor="xianxia-new-item-nature">
                          <span>Nature</span>
                          <select
                            id="xianxia-new-item-nature"
                            value={newXianxiaInventoryDraft.itemNature}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemNature: event.currentTarget.value })
                            }
                          >
                            <option value="Mundane">Mundane</option>
                            <option value="Relic">Relic</option>
                          </select>
                        </label>
                        <label className="session-field" htmlFor="xianxia-new-item-type">
                          <span>Type</span>
                          <select
                            id="xianxia-new-item-type"
                            value={newXianxiaInventoryDraft.itemType}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemType: event.currentTarget.value })
                            }
                          >
                            <option value="Weapon">Weapon</option>
                            <option value="Armor">Armor</option>
                            <option value="Artifact">Artifact</option>
                            <option value="Consumable">Consumable</option>
                            <option value="Miscellaneous">Miscellaneous</option>
                          </select>
                        </label>
                        <label className="session-field" htmlFor="xianxia-new-item-tags">
                          <span>Tags</span>
                          <input
                            id="xianxia-new-item-tags"
                            value={newXianxiaInventoryDraft.tags}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, tags: event.currentTarget.value })
                            }
                          />
                        </label>
                        <label className="session-field" htmlFor="xianxia-new-item-notes">
                          <span>Notes</span>
                          <textarea
                            id="xianxia-new-item-notes"
                            rows={3}
                            value={newXianxiaInventoryDraft.notes}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, notes: event.currentTarget.value })
                            }
                          />
                        </label>
                      </div>
                      <label className="toggle-row">
                        <input
                          type="checkbox"
                          checked={newXianxiaInventoryDraft.equippable}
                          onChange={(event) =>
                            setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, equippable: event.currentTarget.checked })
                          }
                        />
                        Equippable
                      </label>
                      {newXianxiaInventoryDraft.equippable ? (
                        <label className="toggle-row">
                          <input
                            type="checkbox"
                            checked={newXianxiaInventoryDraft.isEquipped}
                            onChange={(event) =>
                              setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, isEquipped: event.currentTarget.checked })
                            }
                          />
                          Equipped
                        </label>
                      ) : null}
                      <button type="submit" className="button-link" disabled={addXianxiaInventoryItem.isPending}>
                        {addXianxiaInventoryItem.isPending ? "Adding..." : "Add item"}
                      </button>
                    </form>
                  </article>
                ) : null}
                <div className="detail-grid" id="session-currency">
                  <article className="detail-card session-card">
                    <h3>Currency</h3>
                    <div className="currency-grid">
                      {(xianxiaCurrency.length ? xianxiaCurrency : [
                        { key: "coin", label: "Coin", amount: readNumber(currency.coin) },
                        { key: "supply", label: "Supply", amount: readNumber(currency.supply) },
                        { key: "spirit_stones", label: "Spirit Stones", amount: readNumber(currency.spirit_stones) },
                      ]).map((entry) => (
                        <form key={entry.key} onSubmit={submitCurrency} className="currency-form currency-box">
                          <div className="currency-box__header">
                            <span>{entry.label}</span>
                          </div>
                          <input
                            className="currency-box__amount"
                            id={`currency-${entry.key}`}
                            type="number"
                            min="0"
                            value={currencyDraft[entry.key] ?? String(entry.amount ?? 0)}
                            disabled={!canEdit}
                            onChange={(event) => setCurrencyDraft({ ...currencyDraft, [entry.key]: event.currentTarget.value })}
                            onBlur={submitCurrencyOnBlur}
                          />
                          {entry.description ? <p className="meta">{entry.description}</p> : null}
                          <button type="submit" className="visually-hidden" disabled={patchCurrency.isPending || !canEdit}>
                            Update {entry.label}
                          </button>
                        </form>
                      ))}
                    </div>
                  </article>
                </div>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "personal" ? (
              <section className="read-section" id="xianxia-personal">
                <div className="section-heading">
                  <h2>Personal</h2>
                </div>
                <div className="reference-stack">
                  {detailRecord?.portrait ? (
                    <article className="detail-card" id="character-personal-portrait">
                      <figure>
                        <img
                          className="article-image"
                          src={detailRecord.portrait.url}
                          alt={detailRecord.portrait.alt_text || "Character portrait"}
                        />
                        {detailRecord.portrait.caption ? (
                          <figcaption className="meta article-image__caption">
                            {detailRecord.portrait.caption}
                          </figcaption>
                        ) : null}
                      </figure>
                    </article>
                  ) : null}
                  {physicalDescriptionHtml ? (
                    <article className="detail-card">
                      <h3>Physical Description</h3>
                      <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: physicalDescriptionHtml }} />
                    </article>
                  ) : null}
                  {personalBackgroundHtml ? (
                    <article className="detail-card">
                      <h3>Background</h3>
                      <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: personalBackgroundHtml }} />
                    </article>
                  ) : null}
                  {!detailRecord?.portrait && !physicalDescriptionHtml && !personalBackgroundHtml ? (
                    <article className="detail-card">
                      <p className="meta">No personal details yet.</p>
                    </article>
                  ) : null}
                </div>
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "overview" ? (
              <section className="read-section" id="character-overview">
                <div className="section-heading">
                  <h2>At a glance</h2>
                </div>
                {hasOverviewStatRows ? (
                  <>
                    {overviewStatRows.map((row, rowIndex) => (
                      <div className={`glance-grid glance-grid--row glance-grid--quick-row-${rowIndex + 1}`} key={`glance-row-${rowIndex}`}>
                        {row.map((stat) => (
                          <div className="glance-card" key={`${rowIndex}-${readString(stat.label)}`}>
                            <span className="meta">{readString(stat.label, "--")}</span>
                            <strong>{readString(stat.value, "--")}</strong>
                          </div>
                        ))}
                      </div>
                    ))}
                  </>
                ) : (
                  <div className="glance-grid">
                    {overviewStats.map((stat) => (
                      <div className="glance-card" key={readString(stat.label, "overview-stat")}>
                        <span className="meta">{readString(stat.label, "--")}</span>
                        <strong>{readString(stat.value, "--")}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "resources" ? (
              <section className="read-section" id="session-resources">
                <div className="section-heading">
                  <h2>Resources</h2>
                </div>
                {resources.length ? (
                  <div className={`resource-grid resource-grid--compact${canEdit ? " resource-grid--editable" : ""}`}>
                    {resources.map((resource) => {
                      const id = readString(resource.id);
                      const resourceLabel = readString(resource.label, id || "Resource");
                      const resetLabel = readString(
                        resource["reset_label"] || resource["resetLabel"] || resource["reset_on"],
                      );
                      return (
                        <article
                          className={`resource-card${canEdit && id ? " session-resource-card session-resource-card--compact" : ""}`}
                          key={id || resourceLabel}
                        >
                          <h4>{resourceLabel}</h4>
                          <p className="resource-card__value">
                            {readNumber(resource.current)} / {readNumber(resource.max)}
                          </p>
                          {resetLabel ? <p className="meta">{resetLabel}</p> : null}
                          {resource.notes ? <p className="meta">{readString(resource.notes)}</p> : null}
                          {canEdit && id ? (
                            <form
                              className="session-inline-form session-inline-form--compact-resource"
                              onSubmit={(event) => submitResource(event, id)}
                              data-character-autosubmit
                              data-character-sheet-edit-form="resource"
                              data-character-sheet-edit-row-id={id}
                            >
                              <label className="session-field" htmlFor={`resource-${id}`}>
                                <span>Current</span>
                                <input
                                  id={`resource-${id}`}
                                  type="number"
                                  min="0"
                                  value={resourceDrafts[id] ?? ""}
                                  onChange={(event) =>
                                    setResourceDrafts({ ...resourceDrafts, [id]: event.currentTarget.value })
                                  }
                                  onBlur={submitResourceOnBlur}
                                />
                              </label>
                              <button type="submit" className="visually-hidden" disabled={patchResource.isPending || !canEdit}>
                                Update {resourceLabel}
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No tracked resources.</p>
                )}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "spells" ? (
              <section className="read-section" id="session-spell-slots">
                <div className="section-heading">
                  <h2>Spells</h2>
                </div>
                <div className="detail-grid spellcasting-summary-grid">
                  <article className="detail-card spellcasting-class-card">
                    <h3>Spellcasting</h3>
                    <p className="meta">Ability: {String(spellcasting.spellcasting_ability ?? "--")}</p>
                    <p className="meta">Save DC: {String(spellcasting.spell_save_dc ?? "--")}</p>
                    <p className="meta">Attack: {String(spellcasting.spell_attack_bonus ?? "--")}</p>
                  </article>
                </div>
                {spellSlots.length ? (
                  <div className="spell-slot-editor-list spell-slot-editor-list--compact">
                    {spellSlots.map((slot) => {
                      const level = readNumber(slot.level);
                      const slotLaneId = readString(slot.slot_lane_id);
                      const key = draftKey(level, slotLaneId);
                      const used = readNumber(slot.used);
                      const max = readNumber(slot.max);
                      const available = readNumber(slot.available, Math.max(0, max - used));
                      const slotLabel = readString(slot.label, `Level ${level}`);
                      return (
                        <article className="detail-card" key={key}>
                          {canEdit ? (
                            <form
                              onSubmit={(event) => submitSpellSlot(event, slot)}
                              className="session-inline-form"
                              data-character-sheet-edit-form="spell-slot"
                              data-character-sheet-edit-level={level}
                              data-character-sheet-edit-slot-lane-id={slotLaneId}
                              data-character-autosubmit
                            >
                              <div className="section-heading">
                                <h3>{slotLabel}</h3>
                                <span className="meta">
                                  {available} available / {max}
                                </span>
                              </div>
                              <label className="session-field" htmlFor={`spell-slot-${key}`}>
                                <span>Used</span>
                                <input
                                  id={`spell-slot-${key}`}
                                  type="number"
                                  min="0"
                                  max={max}
                                  value={spellSlotDrafts[key] ?? ""}
                                  onChange={(event) =>
                                    setSpellSlotDrafts({ ...spellSlotDrafts, [key]: event.currentTarget.value })
                                  }
                                  onBlur={submitSpellSlotOnBlur}
                                />
                              </label>
                              <button type="submit" className="visually-hidden" disabled={patchSpellSlot.isPending || !canEdit}>
                                Update {slotLabel}
                              </button>
                            </form>
                          ) : (
                            <>
                              <div className="section-heading">
                                <h3>{slotLabel}</h3>
                                <span className="meta">
                                  {available} available / {max}
                                </span>
                              </div>
                              <p>Used {used} / {max}</p>
                            </>
                          )}
                        </article>
                      );
                    })}
                  </div>
                ) : null}
                {presentedSpells.length ? (
                  <div className="spell-level-groups">
                    {presentedSpellGroups.map((group) => (
                      <section className="spell-level-group" key={group.key}>
                        <div className="spell-level-group__heading">
                          <h3>{group.label}</h3>
                        </div>
                        <div className="spell-card-grid spell-card-grid--level">
                          {group.spells.map((spell) => {
                            const detailLine = presentedSpellCardDetailLine(spell);
                            const levelSchool = [spell.level_label, spell.school].filter(Boolean).join(" | ");
                            const spellCardContent = (
                              <>
                                <span className="spell-card__name">{spell.name || "Spell"}</span>
                                <span className="spell-card__eyebrow">{levelSchool || "Spell"}</span>
                                {spell.badges?.length ? (
                                  <span className="badge-list spell-card__badges">
                                    {spell.badges.map((badge) => (
                                      <span className="meta-badge" key={badge}>
                                        {badge}
                                      </span>
                                    ))}
                                  </span>
                                ) : null}
                                {detailLine ? <span className="spell-card__meta">{detailLine}</span> : null}
                              </>
                            );
                            return (
                              <article
                                className="spell-card"
                                key={draftKey(spell.class_row_id, spell.name, spell.level_label)}
                              >
                                {spell.description_html || spell.href ? (
                                  <button
                                    type="button"
                                    className="spell-card__main"
                                    aria-haspopup="dialog"
                                    onClick={() => openSpellDetail(spell)}
                                  >
                                    {spellCardContent}
                                  </button>
                                ) : (
                                  <span className="spell-card__main">{spellCardContent}</span>
                                )}
                              </article>
                            );
                          })}
                        </div>
                      </section>
                    ))}
                  </div>
                ) : spells.length ? (
                  <div className="spell-level-groups">
                    {rawSpellGroups.map((group) => (
                      <section className="spell-level-group" key={group.key}>
                        <div className="spell-level-group__heading">
                          <h3>{group.label}</h3>
                        </div>
                        <div className="spell-card-grid spell-card-grid--level">
                          {group.spells.map((spell) => {
                            const mark = readString(spell.mark);
                            const detailLine = rawSpellCardDetailLine(spell);
                            const levelSchool = [readString(spell.level_label), readString(spell.school)]
                              .filter(Boolean)
                              .join(" | ");
                            return (
                              <article className="spell-card" key={readString(spell.id, readString(spell.name))}>
                                <span className="spell-card__main">
                                  <span className="spell-card__name">{readString(spell.name, "Spell")}</span>
                                  {levelSchool ? <span className="spell-card__eyebrow">{levelSchool}</span> : null}
                                  {mark ? (
                                    <span className="badge-list spell-card__badges">
                                      <span className="meta-badge">{mark}</span>
                                    </span>
                                  ) : null}
                                  {detailLine ? <span className="spell-card__meta">{detailLine}</span> : null}
                                </span>
                              </article>
                            );
                          })}
                        </div>
                      </section>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}


            {isDnd && activeCharacterSection === "equipment" ? (
              <section className="read-section" id="character-equipment">
                <div className="section-heading">
                  <h2>Equipment</h2>
                </div>
                {equipmentState ? (
                  <div className="detail-grid">
                    <article className="detail-card">
                      <h3>Attuned items</h3>
                      <p>
                        <strong>
                          {equipmentState.attuned_count} / {equipmentState.max_attuned_items}
                        </strong>
                      </p>
                      <p className="meta">
                        Attunement is separate from equipped state and usually has room for up to {equipmentState.max_attuned_items} items.
                      </p>
                      {equipmentState.over_attunement_limit ? (
                        <p className="meta">This sheet is currently over the normal attunement limit.</p>
                      ) : null}
                    </article>
                    <article className="detail-card">
                      <h3>Equipped items</h3>
                      <p>
                        <strong>{equipmentState.equipped_count}</strong>
                      </p>
                      <p className="meta">
                        Armor and magic items use equipped state; weapons also track an applicable wielding mode.
                      </p>
                    </article>
                  </div>
                ) : null}
                {arcaneArmorState?.available ? (
                  <article className="detail-card character-edit-row" id="character-arcane-armor-state">
                    <div className="section-heading">
                      <h3>{readString(arcaneArmorState.label, "Arcane Armor")}</h3>
                      <span className="meta">
                        {[
                          readString(arcaneArmorState.status_label),
                          arcaneArmorState.enabled ? readString(arcaneArmorState.hands_label) : "",
                        ]
                          .filter(Boolean)
                          .join(" | ")}
                      </span>
                    </div>
                    {canEdit ? (
                      <form onSubmit={submitArcaneArmorState} className="stack-form" data-character-autosubmit>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            name="enabled"
                            value="1"
                            checked={arcaneArmorDraft}
                            disabled={patchFeatureState.isPending || !canEdit}
                            onChange={(event) => {
                              const nextArcaneArmorState = event.currentTarget.checked;
                              setArcaneArmorDraft(nextArcaneArmorState);
                              submitArcaneArmorState(undefined, nextArcaneArmorState);
                            }}
                          />
                          Arcane Armor enabled
                        </label>
                      </form>
                    ) : null}
                  </article>
                ) : null}
                {equipmentRows.length ? (
                  <div className="equipment-state-grid" id={isCombatSurface ? "combat-character-equipment-state" : "character-equipment-state"}>
                    {equipmentRows.map((item) => {
                      const draft = equipmentDrafts[item.id] ?? {
                        isEquipped: Boolean(item.is_equipped),
                        isAttuned: Boolean(item.is_attuned),
                        weaponWieldMode: item.weapon_wield_mode || "",
                      };
                      return (
                        <article className="detail-card character-edit-row" key={item.id || item.name}>
                          <div className="section-heading">
                            <h3>
                              {item.href ? <a href={item.href}>{readString(item.name, "Item")}</a> : readString(item.name, "Item")}
                            </h3>
                            <span className="meta">{readString(item.source_label)}</span>
                          </div>
                          <p className="meta">
                            {[readString(item.equipped_label), item.requires_attunement ? (item.is_attuned ? "Attuned" : "Not attuned") : ""]
                              .filter(Boolean)
                              .join(" | ")}
                          </p>
                          {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                          {item.description_html || item.notes || item.href ? (
                            <button type="button" className="ghost-button item-detail-button" onClick={() => openItemDetail(item)}>
                              Item details
                            </button>
                          ) : null}
                          {canEdit ? (
                            <form
                              onSubmit={(event) => submitEquipmentState(event, item)}
                              className="stack-form"
                              data-character-autosubmit
                              data-character-sheet-edit-form="equipment-state"
                            >
                              <div className="detail-grid">
                                {item.supports_weapon_wield_mode ? (
                                  <label>
                                    Wielding
                                    <select
                                      id={`equipment-wield-${item.id}`}
                                      name="weapon_wield_mode"
                                      value={draft.weaponWieldMode}
                                      disabled={patchEquipmentState.isPending || !canEdit}
                                      onChange={(event) => {
                                        const nextDraft = { ...draft, weaponWieldMode: event.currentTarget.value };
                                        setEquipmentDrafts({
                                          ...equipmentDrafts,
                                          [item.id]: nextDraft,
                                        });
                                        submitEquipmentStatePatch(item, nextDraft);
                                      }}
                                    >
                                      <option value="">Not equipped</option>
                                      {item.weapon_wield_options.map((option) => (
                                        <option value={option.value} key={option.value}>
                                          {option.label}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                ) : (
                                  <label className="checkbox-label">
                                    <input
                                      type="checkbox"
                                      name="is_equipped"
                                      value="1"
                                      checked={draft.isEquipped}
                                      disabled={patchEquipmentState.isPending || !canEdit}
                                      onChange={(event) => {
                                        const nextDraft = { ...draft, isEquipped: event.currentTarget.checked };
                                        setEquipmentDrafts({
                                          ...equipmentDrafts,
                                          [item.id]: nextDraft,
                                        });
                                        submitEquipmentStatePatch(item, nextDraft);
                                      }}
                                    />
                                    Equipped
                                  </label>
                                )}
                                {item.requires_attunement ? (
                                  <label className="checkbox-label">
                                    <input
                                      type="checkbox"
                                      name="is_attuned"
                                      value="1"
                                      checked={draft.isAttuned}
                                      disabled={patchEquipmentState.isPending || !canEdit}
                                      onChange={(event) => {
                                        const nextDraft = { ...draft, isAttuned: event.currentTarget.checked };
                                        setEquipmentDrafts({
                                          ...equipmentDrafts,
                                          [item.id]: nextDraft,
                                        });
                                        submitEquipmentStatePatch(item, nextDraft);
                                      }}
                                    />
                                    Attuned
                                  </label>
                                ) : null}
                              </div>
                              {item.attunement_hint && item.attunement_hint !== "Requires attunement" ? (
                                <p className="meta">{item.attunement_hint}</p>
                              ) : null}
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No equipment state rows.</p>
                )}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "inventory" ? (
              <section className="read-section" id="session-inventory">
                <div className="section-heading">
                  <h2>Inventory</h2>
                </div>
                {inventory.length ? (
                  <div className="inventory-list">
                    {inventory.map((item) => {
                      const id = readString(item.id);
                      const itemRef = readString(item.catalog_ref, id);
                      const presentedItem = presentedInventoryByKey.get(itemRef) ?? presentedInventoryByKey.get(id);
                      const itemName = readString(presentedItem?.name, readString(item.name, "Item"));
                      const itemNotes = readString(presentedItem?.notes, readString(item.notes));
                      const itemHref = readString(presentedItem?.href);
                      const itemDescriptionHtml = readString(presentedItem?.description_html);
                      const itemTags = presentedItem?.tags?.length ? presentedItem.tags : [];
                      return (
                        <article className="inventory-row" key={id || itemRef || itemName}>
                          <div className="inventory-row__header">
                            <h3>{itemHref ? <a href={itemHref}>{itemName}</a> : itemName}</h3>
                          </div>
                          {itemTags.length ? <p className="meta">{itemTags.join(", ")}</p> : null}
                          {canEdit && id ? (
                            item.weight ? <p className="meta">{readString(item.weight)}</p> : null
                          ) : (
                            <p className="meta">
                              Qty {readNumber(item.quantity, 1)}
                              {item.weight ? ` | ${readString(item.weight)}` : ""}
                            </p>
                          )}
                          {itemDescriptionHtml || itemNotes || itemHref ? (
                            <button
                              type="button"
                              className="ghost-button item-detail-button"
                              onClick={() =>
                                openItemDetail({
                                  name: itemName,
                                  href: itemHref,
                                  description_html: itemDescriptionHtml,
                                  notes: itemNotes,
                                })
                              }
                            >
                              Item details
                            </button>
                          ) : null}
                          {canEdit && id ? (
                            <form
                              onSubmit={(event) => submitInventory(event, id)}
                              className="session-inline-form inventory-row__quantity-form"
                              data-character-autosubmit
                              data-character-sheet-edit-form="inventory"
                              data-character-sheet-edit-row-id={id}
                            >
                              <label className="session-field" htmlFor={`inventory-${id}`}>
                                <span>Quantity</span>
                                <input
                                  id={`inventory-${id}`}
                                  type="number"
                                  min="0"
                                  value={inventoryDrafts[id] ?? ""}
                                  onChange={(event) =>
                                    setInventoryDrafts({ ...inventoryDrafts, [id]: event.currentTarget.value })
                                  }
                                  onBlur={submitInventoryOnBlur}
                                />
                              </label>
                              <button type="submit" className="visually-hidden" disabled={patchInventory.isPending || !canEdit}>
                                Update {itemName} quantity
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : null}
                <div className="detail-grid">
                  <article className="detail-card">
                    <h3>Currency</h3>
                    <div className="currency-grid" id="session-currency">
                      {["cp", "sp", "ep", "gp", "pp"].map((key) => (
                        <form key={key} onSubmit={submitCurrency} className="currency-form currency-box">
                          <div className="currency-box__header">
                            <span>{key.toUpperCase()}</span>
                          </div>
                          <input
                            className="currency-box__amount"
                            id={`currency-${key}`}
                            type="number"
                            min="0"
                            value={currencyDraft[key] ?? "0"}
                            disabled={!canEdit}
                            onChange={(event) => setCurrencyDraft({ ...currencyDraft, [key]: event.currentTarget.value })}
                            onBlur={submitCurrencyOnBlur}
                          />
                          <button type="submit" className="visually-hidden" disabled={patchCurrency.isPending || !canEdit}>
                            Update {key.toUpperCase()}
                          </button>
                        </form>
                      ))}
                    </div>
                  </article>
                </div>
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "abilities" ? (
              <CharacterDndAbilitySkillsSection
                abilities={dndAbilities}
                hasContent={hasDndAbilitySkillsContent}
                proficiencyGroups={dndProficiencyGroups}
              />
            ) : null}

            {isReadSurface && activeCharacterSection === "controls" && canUseControls && controls ? (
              <section className="read-section character-controls-panel">
                <div className="section-heading">
                  <h2>Controls</h2>
                </div>
                <div className="detail-grid character-controls-grid">
                  <article className="detail-card">
                    <h3>Player controls</h3>
                    {controls.current_user_is_owner ? (
                      <p>Player-controls workspace for {selected.name}.</p>
                    ) : (
                      <p>Character management controls for campaign staff.</p>
                    )}
                  </article>
                  <article className="detail-card">
                    <h3>Current owner</h3>
                    {controls.assignment ? (
                      <>
                        <p>
                          <strong>{controls.assignment.display_name}</strong>
                          {controls.assignment.email ? <span className="meta"> | {controls.assignment.email}</span> : null}
                        </p>
                        <p className="meta">
                          Assignment: {controls.assignment.assignment_type
                            ? `${controls.assignment.assignment_type.charAt(0).toUpperCase()}${controls.assignment.assignment_type.slice(1)}`
                            : "Owner"}
                        </p>
                        {controls.assignment.admin_href ? (
                          <a className="ghost-button" href={controls.assignment.admin_href}>
                            Open user record
                          </a>
                        ) : null}
                      </>
                    ) : (
                      <p className="meta">No player owner assigned yet.</p>
                    )}
                  </article>
                </div>

                {controls.can_assign_owner ? (
                  <div className="detail-grid character-controls-grid">
                    <article className="detail-card character-controls-manager">
                      <h3>Assignment controls</h3>
                      <p className="meta">Assignments require an active player membership in this campaign.</p>
                      {controls.player_choices.length ? (
                        <form onSubmit={submitCharacterAssignment} className="stack-form">
                          <label className="field">
                            <span>Assign owner</span>
                            <select
                              id="character-owner-assignment"
                              value={controlsDraft.assignedUserId}
                              disabled={controlsMutationPending}
                              required
                              onChange={(event) =>
                                setControlsDraft({ ...controlsDraft, assignedUserId: event.currentTarget.value })
                              }
                            >
                              <option value="">Choose a player</option>
                              {controls.player_choices.map((choice) => (
                                <option key={choice.user_id} value={String(choice.user_id)}>
                                  {choice.label}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button type="submit" disabled={controlsMutationPending || !controlsDraft.assignedUserId}>
                            {assignCharacterOwner.isPending ? "Saving..." : "Save assignment"}
                          </button>
                        </form>
                      ) : (
                        <p className="meta">No active player memberships are available for assignment in this campaign.</p>
                      )}
                      {controls.assignment ? (
                        <form className="stack-form" onSubmit={(event) => { event.preventDefault(); clearCharacterAssignment(); }}>
                          <button type="submit" disabled={controlsMutationPending}>
                            {clearCharacterOwner.isPending ? "Clearing..." : "Clear assignment"}
                          </button>
                        </form>
                      ) : null}
                    </article>
                  </div>
                ) : null}

                {controls.can_delete_character ? (
                  <div className="detail-grid character-controls-grid">
                    <article className="detail-card character-controls-card--danger">
                      <h3>Delete character</h3>
                      <p>
                        Deleting a character removes the file-backed definition/import metadata, the live character state,
                        and any current assignment for this character slug.
                      </p>
                      <form onSubmit={submitCharacterDelete} className="stack-form">
                        <label className="field">
                          <span>
                            Type <code>{selected.slug}</code> to confirm
                          </span>
                          <input
                            id="character-delete-confirmation"
                            type="text"
                            autoComplete="off"
                            spellCheck={false}
                            value={controlsDraft.deleteConfirmation}
                            disabled={controlsMutationPending}
                            onChange={(event) =>
                              setControlsDraft({ ...controlsDraft, deleteConfirmation: event.currentTarget.value })
                            }
                          />
                        </label>
                        <button
                          type="submit"
                          disabled={controlsMutationPending || controlsDraft.deleteConfirmation.trim() !== selected.slug}
                        >
                          {deleteCharacterMutation.isPending ? "Deleting..." : "Delete character"}
                        </button>
                      </form>
                    </article>
                  </div>
                ) : null}
              </section>
            ) : null}

            {((isDnd || isXianxia) ? activeCharacterSection === "notes" : !isDnd) ? (
              <section className="read-section" id="session-notes">
                <div className="section-heading">
                  <h2>Notes</h2>
                </div>
                <div className="reference-stack">
                  {playerNotesHtml ? (
                    <article className="detail-card">
                      <h3>Note</h3>
                      <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: playerNotesHtml }} />
                    </article>
                  ) : null}
                  {referenceSections.length ? (
                    referenceSections.map((section, sectionIndex) => (
                      <article className="detail-card" key={readString(section.title, `reference-section-${sectionIndex}`)}>
                        <h3>{readString(section.title)}</h3>
                        <div
                          className="article-body article-body--compact"
                          dangerouslySetInnerHTML={{ __html: readString(section.html) }}
                        />
                      </article>
                    ))
                  ) : null}
                  {!playerNotesHtml && !referenceSections.length ? (
                    <article className="detail-card">
                      <p className="meta">No notes yet.</p>
                    </article>
                  ) : null}
                </div>
                {canEdit ? (
                  <article className="detail-card session-card">
                    <form className="stack-form" data-character-sheet-edit-form="notes" onSubmit={submitNotes}>
                      <label className="field">
                        <span>Markdown note</span>
                        <textarea
                          name="player_notes_markdown"
                          rows={8}
                          value={notesDraft.notes}
                          disabled={!canEdit}
                          onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                            setNotesDraft({ ...notesDraft, notes: event.currentTarget.value })
                          }
                        />
                      </label>
                      <button type="submit" disabled={patchNotes.isPending || !canEdit}>
                        {patchNotes.isPending ? "Saving..." : "Save note"}
                      </button>
                    </form>
                  </article>
                ) : null}
              </section>
            ) : null}

            {!isDnd && !isXianxia ? (
              <section className="read-section" id="character-system-summary">
                <div className="section-heading">
                  <h2>{characterSystem(detailRecord)}</h2>
                </div>
                <div className="detail-grid">
                  <article className="detail-card">
                    <h3>Current HP</h3>
                    <strong>{String(vitals.current_hp ?? "--")}</strong>
                  </article>
                  <article className="detail-card">
                    <h3>Temp HP</h3>
                    <strong>{String(vitals.temp_hp ?? "--")}</strong>
                  </article>
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      </CharacterShell>
      <ToastNotice message={statusMessage} />
      <CharacterDetailDialog detail={detailDialog} onClose={() => setDetailDialog(null)} />
    </div>
  );
}

