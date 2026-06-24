import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FocusEvent, FormEvent, MouseEvent } from "react";
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
} from "../characterPaneDrafts";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { queryClient, useApiClient } from "../apiClientContext";
import { TOAST_DISMISS_MS, ToastNotice } from "../components/feedback";
import {
  CharacterDetailDialog,
  type CharacterDetailDialogState,
} from "../components/CharacterDetailDialog";
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
import { CharacterPersonalSection } from "../components/CharacterPersonalSection";
import { CharacterXianxiaEquipmentSection } from "../components/CharacterXianxiaEquipmentSection";
import { CharacterXianxiaInventorySection } from "../components/CharacterXianxiaInventorySection";
import { CharacterXianxiaMartialArtsSection } from "../components/CharacterXianxiaMartialArtsSection";
import { CharacterXianxiaQuickReferenceSection } from "../components/CharacterXianxiaQuickReferenceSection";
import { CharacterXianxiaResourcesSection } from "../components/CharacterXianxiaResourcesSection";
import { CharacterXianxiaSkillsSection } from "../components/CharacterXianxiaSkillsSection";
import { CharacterXianxiaTechniquesSection } from "../components/CharacterXianxiaTechniquesSection";
import {
  asRecord,
  asRecordArray,
  asStringArray,
  readNumber,
  readString,
} from "../characterValueUtils";
import {
  characterSystem,
  characterReadSectionUrl,
  collectPresentedSpells,
  defaultCharacterReadSection,
  draftKey,
  groupSpellsByLevel,
  itemDetailDialogState,
  isDndCharacter,
  isXianxiaCharacter,
  joinDisplay,
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

            {isXianxia && activeCharacterSection === "quick-reference" ? (
              <CharacterXianxiaQuickReferenceSection
                hasSkillUseGuardrail={hasSkillUseGuardrail}
                hasXianxiaHonorInteractions={hasXianxiaHonorInteractions}
                hasXianxiaStanceBreak={hasXianxiaStanceBreak}
                presentedXianxia={presentedXianxia}
                skillUseGuardrailReferenceLines={skillUseGuardrailReferenceLines}
                skillUseGuardrailRuleHref={skillUseGuardrailRuleHref}
                skillUseGuardrailRuleTitle={skillUseGuardrailRuleTitle}
                xianxiaActionReference={xianxiaActionReference}
                xianxiaDefenseReference={xianxiaDefenseReference}
                xianxiaHonorContexts={xianxiaHonorContexts}
                xianxiaHonorInteractions={xianxiaHonorInteractions}
                xianxiaHonorReferenceLines={xianxiaHonorReferenceLines}
                xianxiaInsight={xianxiaInsight}
                xianxiaRuleTextReferences={xianxiaRuleTextReferences}
                xianxiaStanceBreak={xianxiaStanceBreak}
                xianxiaStanceBreakRecoveryLines={xianxiaStanceBreakRecoveryLines}
                xianxiaStanceBreakReferenceLines={xianxiaStanceBreakReferenceLines}
              />
            ) : null}
            {isXianxia && activeCharacterSection === "martial-arts" ? (
              <CharacterXianxiaMartialArtsSection martialArts={presentedXianxia.martial_arts} />
            ) : null}
            {isXianxia && activeCharacterSection === "techniques" ? (
              <CharacterXianxiaTechniquesSection
                approval={presentedXianxia.approval}
                basicActions={presentedXianxia.basic_actions}
                canEdit={canEdit}
                canRecordXianxiaDaoUse={canRecordXianxiaDaoUse}
                genericTechniques={presentedXianxia.generic_techniques}
                isDaoUseRecordSaving={postXianxiaDaoUseRecord.isPending}
                isDaoUseRequestSaving={postXianxiaDaoUseRequest.isPending}
                setXianxiaDaoRequestDraft={setXianxiaDaoRequestDraft}
                setXianxiaDaoUseNotesDrafts={setXianxiaDaoUseNotesDrafts}
                submitXianxiaDaoUseRecord={submitXianxiaDaoUseRecord}
                submitXianxiaDaoUseRequest={submitXianxiaDaoUseRequest}
                xianxiaDaoRequestDraft={xianxiaDaoRequestDraft}
                xianxiaDaoUseNotesDrafts={xianxiaDaoUseNotesDrafts}
                xianxiaInsight={xianxiaInsight}
              />
            ) : null}
            {isXianxia && activeCharacterSection === "resources" ? (
              <CharacterXianxiaResourcesSection
                activeStateStatus={xianxiaActiveStateStatus}
                canEdit={canEdit}
                durability={xianxiaDurability}
                energies={xianxiaEnergies}
                insight={xianxiaInsight}
                isActiveStateSaving={patchXianxiaActiveState.isPending}
                setXianxiaActiveDraft={setXianxiaActiveDraft}
                submitXianxiaActiveState={submitXianxiaActiveState}
                xianxiaActiveDraft={xianxiaActiveDraft}
                xianxiaDao={xianxiaDao}
                yinYang={xianxiaYinYang}
              />
            ) : null}

            {isXianxia && activeCharacterSection === "skills" ? (
              <CharacterXianxiaSkillsSection
                hasSkillUseGuardrail={hasSkillUseGuardrail}
                skillUseGuardrailReferenceLines={skillUseGuardrailReferenceLines}
                skillUseGuardrailRuleHref={skillUseGuardrailRuleHref}
                skillUseGuardrailRuleTitle={skillUseGuardrailRuleTitle}
                trainedSkills={presentedXianxia.skills?.trained ?? []}
              />
            ) : null}

            {isXianxia && activeCharacterSection === "equipment" ? (
              <CharacterXianxiaEquipmentSection
                defenseReference={xianxiaDefenseReference}
                equipment={presentedXianxia.equipment}
              />
            ) : null}

            {isXianxia && activeCharacterSection === "inventory" ? (
              <CharacterXianxiaInventorySection
                canEdit={canEdit}
                currency={currency}
                currencyDraft={currencyDraft}
                inventory={xianxiaInventory}
                isAddingInventoryItem={addXianxiaInventoryItem.isPending}
                isCurrencySaving={patchCurrency.isPending}
                isRemovingInventoryItem={removeXianxiaInventoryItem.isPending}
                isUpdatingInventoryItem={patchXianxiaInventoryItem.isPending}
                newXianxiaInventoryDraft={newXianxiaInventoryDraft}
                setCurrencyDraft={setCurrencyDraft}
                setNewXianxiaInventoryDraft={setNewXianxiaInventoryDraft}
                setXianxiaInventoryDrafts={setXianxiaInventoryDrafts}
                submitCurrency={submitCurrency}
                submitCurrencyOnBlur={submitCurrencyOnBlur}
                submitXianxiaInventoryAdd={submitXianxiaInventoryAdd}
                submitXianxiaInventoryUpdate={submitXianxiaInventoryUpdate}
                toggleXianxiaInventoryEquipped={toggleXianxiaInventoryEquipped}
                removeXianxiaInventory={removeXianxiaInventory}
                xianxiaCurrency={xianxiaCurrency}
                xianxiaInventoryDrafts={xianxiaInventoryDrafts}
              />
            ) : null}

            {isXianxia && activeCharacterSection === "personal" ? (
              <CharacterPersonalSection
                personalBackgroundHtml={personalBackgroundHtml}
                physicalDescriptionHtml={physicalDescriptionHtml}
                portrait={detailRecord?.portrait}
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

