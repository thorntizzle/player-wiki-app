import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { MouseEvent } from "react";
import type {
  CharacterDetailResponse,
  CharacterPresentedSpell,
  CharacterRestPreviewResponse,
  CharacterSummary,
} from "../api/types";
import {
  useCharacterPaneDraftState,
} from "../characterPaneDrafts";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { useApiClient } from "../apiClientContext";
import { ToastNotice, useToastNotice } from "../components/feedback";
import {
  CharacterDetailDialog,
  type CharacterDetailDialogState,
} from "../components/CharacterDetailDialog";
import { useCharacterPaneMutations } from "../characterPaneMutations";
import { CharacterControlsSection } from "../components/CharacterControlsSection";
import { CharacterEmbeddedSectionNav } from "../components/CharacterEmbeddedSectionNav";
import { CharacterHeader } from "../components/CharacterHeader";
import { CharacterNavigationCard } from "../components/CharacterNavigationCard";
import { CharacterPortraitSection } from "../components/CharacterPortraitSection";
import { CharacterSummaryCard } from "../components/CharacterSummaryCard";
import { CharacterSystemSummarySection } from "../components/CharacterSystemSummarySection";
import { CharacterVitalsBar } from "../components/CharacterVitalsBar";
import { CharacterDndSections } from "../components/CharacterDndSections";
import { CharacterNotesSection } from "../components/CharacterNotesSection";
import { CharacterXianxiaSections } from "../components/CharacterXianxiaSections";
import {
  readNumber,
} from "../characterValueUtils";
import {
  characterSystem,
  characterReadSectionUrl,
  defaultCharacterReadSection,
  itemDetailDialogState,
  isDndCharacter,
  isXianxiaCharacter,
  normalizeActiveCharacterSectionForSystem,
  spellDetailDialogState,
  visibleCharacterSectionsForSystem,
  type CharacterItemDetailInput,
  type CharacterSection,
} from "../characterPaneUtils";
import { buildCharacterPaneModel } from "../characterPaneModel";
import { buildCharacterPaneXianxiaModel } from "../characterPaneXianxiaModel";
import { useCharacterPaneSubmitHandlers } from "../characterPaneSubmitHandlers";

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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [detailDialog, setDetailDialog] = useState<CharacterDetailDialogState | null>(null);
  const detailDialogReturnFocusRef = useRef<HTMLElement | null>(null);
  const portraitFileInputRef = useRef<HTMLInputElement | null>(null);
  const {
    clearToast,
    setToastMessage: setStatusMessage,
    toastMessage: statusMessage,
    toastTone,
  } = useToastNotice();

  const listQuery = useQuery({
    queryKey: ["characters", campaignSlug, ""],
    queryFn: () => apiClient.getCharacters(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  const characterList: CharacterSummary[] = listQuery.data?.characters ?? [];

  const rememberDetailDialogTrigger = () => {
    const activeElement = document.activeElement;
    detailDialogReturnFocusRef.current = activeElement instanceof HTMLElement ? activeElement : null;
  };

  const closeDetailDialog = () => {
    setDetailDialog(null);
    const focusTarget = detailDialogReturnFocusRef.current;
    detailDialogReturnFocusRef.current = null;
    if (focusTarget && document.contains(focusTarget)) {
      window.requestAnimationFrame(() => {
        focusTarget.focus({ preventScroll: true });
      });
    }
  };

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
        closeDetailDialog();
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
  const isSessionSurface = surface === "session";
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

  const characterPaneMutations = useCharacterPaneMutations({
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
    patchXianxiaInventoryItem,
    postXianxiaDaoUseRecord,
    postXianxiaDaoUseRequest,
    previewRest,
    removeXianxiaInventoryItem,
    upsertPortrait,
  } = characterPaneMutations;

  const portraitMutationPending = upsertPortrait.isPending || deletePortrait.isPending;
  const controlsMutationPending =
    assignCharacterOwner.isPending || clearCharacterOwner.isPending || deleteCharacterMutation.isPending;

  const openItemDetail = (item: CharacterItemDetailInput) => {
    rememberDetailDialogTrigger();
    setDetailDialog(itemDetailDialogState(item));
  };

  const openSpellDetail = (spell: CharacterPresentedSpell) => {
    rememberDetailDialogTrigger();
    setDetailDialog(spellDetailDialogState(spell));
  };

  const {
    clearCharacterAssignment,
    handlePortraitFileChange,
    removePortrait,
    removeXianxiaInventory,
    submitArcaneArmorState,
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
  } = useCharacterPaneSubmitHandlers({
    arcaneArmorDraft,
    arcaneArmorState,
    canEdit,
    canRecordXianxiaDaoUse,
    controls,
    controlsDraft,
    currencyDraft,
    equipmentDrafts,
    inventoryDrafts,
    isXianxia,
    mutations: characterPaneMutations,
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
  });

  const selectCharacter = (nextSlug: string | null) => {
    setSelectedSlug(nextSlug);
    setActiveCharacterSection("overview");
    setRestPreview(null);
    clearToast();
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
      {isSessionSurface ? (
        <CharacterNavigationCard
          activeCharacterSection={activeCharacterSection}
          characterList={characterList}
          handleReadSurfaceSectionNavClick={handleReadSurfaceSectionNavClick}
          isReadSurface={isReadSurface}
          readSurfaceSectionUrl={readSurfaceSectionUrl}
          selectCharacter={selectCharacter}
          selectedCharacterSheetUrl={selectedCharacterSheetUrl}
          selectedSlug={selectedSlug}
          showCharacterSheetLink
          visibleCharacterSections={visibleCharacterSections}
        />
      ) : null}
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
        {!isSessionSurface ? (
          <>
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
          </>
        ) : null}

        {listQuery.isLoading ? <p className="status status-neutral">Loading characters...</p> : null}
        {detailQuery.isLoading ? <p className="status status-neutral">Loading character...</p> : null}

        {selected ? (
          <CharacterSummaryCard
            selected={selected}
            selectedPortrait={selectedPortrait}
          />
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
                  sectionId: "xianxia-personal",
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
                personal={{
                  personalBackgroundHtml,
                  physicalDescriptionHtml,
                  sectionId: "dnd-personal",
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

            {activeCharacterSection === "portrait" && selected ? (
              <CharacterPortraitSection
                canManagePortrait={canManagePortrait}
                handlePortraitFileChange={handlePortraitFileChange}
                portraitDraft={portraitDraft}
                portraitFileInputRef={portraitFileInputRef}
                portraitMutationPending={portraitMutationPending}
                removePortrait={removePortrait}
                selectedName={selected.name}
                selectedPortrait={selectedPortrait}
                setPortraitDraft={setPortraitDraft}
                submitPortrait={submitPortrait}
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
      <ToastNotice message={statusMessage} tone={toastTone} />
      <CharacterDetailDialog detail={detailDialog} onClose={closeDetailDialog} />
    </div>
  );
}

