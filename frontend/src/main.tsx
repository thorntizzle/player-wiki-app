import React, { useState, useEffect, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
  useLocation,
  useParams,
} from "@tanstack/react-router";
import { QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FocusEvent, FormEvent } from "react";
import "./styles.css";
import { apiErrorMessage } from "./api/client";
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
  ContentPageFileRecord,
  ContentPageFileSummary,
  ContentPageMetadata,
  ContentPageRemovalSafety,
  ContentPageUpsertPayload,
  CombatAvailableCharacterChoice,
  CombatAvailableStatblockChoice,
  CombatSystemsMonsterSearchResult,
  CombatLiveStatePayload,
  CombatPayload,
  CombatCondition,
  CombatAddNpcPayload,
  CombatTurnPatchPayload,
  CombatVitalsPatchPayload,
  CombatResourcesPatchPayload,
  CombatantSummary,
  DmContentStatblock,
  DmContentStatblockCreatePayload,
  DmContentStatblockUpdatePayload,
  DmContentConditionCreatePayload,
  DmContentConditionDefinition,
  DmContentConditionUpdatePayload,
  DmContentSystemsResponse,
  CustomSystemsEntry,
  CustomSystemsEntryPayload,
  SystemsSourceRow,
  SessionArticle,
  SessionArticleCreatePayload,
  SessionArticleSourceResult,
  SessionArticleUpdatePayload,
  SessionDmPassiveScoreRow,
  SessionLogSummary,
  SessionPayload,
} from "./api/types";
import {
  coerceSessionPane,
  isAuthRequiredFromError as isAuthError,
  resolveSessionLivePayload,
  type SessionRoutePane,
} from "./sessionRouteState";
import {
  queryClient,
  useApiClient,
} from "./apiClientContext";
import { getApiErrorMessage } from "./apiErrors";
import {
  ApiErrorNotice,
  TOAST_DISMISS_MS,
  ToastNotice,
} from "./components/feedback";
import {
  asRecord,
  asRecordArray,
  asStringArray,
  boolFromUnknown,
  numberFromUnknown,
  readNumber,
  readString,
  stringFromUnknown,
} from "./characterValueUtils";
import { AccountSettingsPage } from "./routes/AccountSettingsPage";
import { CampaignControlPage } from "./routes/CampaignControlPage";
import { CampaignHelpPage } from "./routes/CampaignHelpPage";
import { WikiArticlePage, WikiHomePage, WikiSectionPage } from "./routes/WikiRoutes";
import {
  SystemsEntryPage,
  SystemsIndexPage,
  SystemsSourceCategoryPage,
  SystemsSourcePage,
} from "./routes/SystemsRoutes";
import { AdminDashboardPage, AdminUserDetailPage } from "./routes/AdminRoutes";
import { CampaignListPage } from "./routes/CampaignPickerPage";
import {
  CharacterAdvancedEditorPage,
  CharacterCreatePage,
  CharacterCultivationPage,
  CharacterLevelUpPage,
  CharacterProgressionRepairPage,
  CharacterRetrainingPage,
  CharacterXianxiaManualImportPage,
} from "./routes/CharacterAuthoringRoutes";
import { AppShell } from "./AppShell";
import { CharacterRosterPage } from "./routes/CharacterRosterPage";
import { SessionPane } from "./routes/SessionRoutes";
import { DmArticleCreator } from "./components/DmArticleCreator";
import {
  renderArticleBody,
  resolveArticleImage,
  SessionArticleReferenceActions,
  SessionArticleSourceLine,
} from "./components/SessionArticleDisplay";
import {
  CharacterDetailDialog,
  type CharacterDetailDialogState,
  type DetailFact,
} from "./components/CharacterDetailDialog";
import {
  buildEmptyManualArticleDraft,
  readBinaryAsBase64,
  readTextFile,
  type ArticleMode,
  type EmbeddedImageInput,
  type ManualArticleDraftState,
} from "./sessionArticleDrafts";
import { formatTimestamp } from "./timeFormatting";

declare global {
  interface Window {
    __cpwAppLoadingBegin?: () => void;
    __cpwAppLoadingReady?: () => void;
  }
}

interface CharacterVitalsDraft {
  expectedRevision: number;
  currentHp: string;
  tempHp: string;
}

interface CharacterXianxiaVitalsDraft extends CharacterVitalsDraft {
  currentStance: string;
  tempStance: string;
  currentJing: string;
  currentQi: string;
  currentShen: string;
  currentYin: string;
  currentYang: string;
  currentDao: string;
}

type CharacterXianxiaVitalsField = Exclude<keyof CharacterXianxiaVitalsDraft, "expectedRevision">;

interface CharacterXianxiaActiveStateDraft {
  expectedRevision: number;
  activeStanceName: string;
  activeAuraName: string;
}

interface CharacterXianxiaInventoryDraft {
  name: string;
  quantity: string;
  itemNature: string;
  itemType: string;
  notes: string;
  tags: string;
  catalogRef: string;
  equippable: boolean;
  isEquipped: boolean;
}

interface CharacterXianxiaDaoUseRequestDraft {
  requestName: string;
  notes: string;
  preparedRecordIndex: string;
}

interface CharacterNotesDraft {
  expectedRevision: number;
  notes: string;
}

interface CharacterEquipmentDraft {
  isEquipped: boolean;
  isAttuned: boolean;
  weaponWieldMode: string;
}

interface CharacterPortraitDraft {
  file: EmbeddedImageInput | null;
  fileName: string;
  altText: string;
  caption: string;
}

interface CharacterControlsDraft {
  assignedUserId: string;
  deleteConfirmation: string;
}

type CharacterSection =
  | "overview"
  | "quick-reference"
  | "martial-arts"
  | "resources"
  | "spells"
  | "techniques"
  | "equipment"
  | "inventory"
  | "abilities"
  | "skills"
  | "personal"
  | "notes"
  | "controls";
type PaneName = SessionRoutePane;
type CombatView = "player" | "status" | "controls";

interface CombatVitalsDraft {
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatResourcesDraft {
  movementRemaining: string;
  hasAction: boolean;
  hasBonusAction: boolean;
  hasReaction: boolean;
}

interface CombatTurnDraft {
  turnValue: string;
  initiativePriority: string;
}

interface CombatConditionDraft {
  name: string;
  durationText: string;
}

interface CombatPlayerSeedDraft {
  characterSlug: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatNpcSeedDraft {
  displayName: string;
  turnValue: string;
  initiativeBonus: string;
  dexterityModifier: string;
  initiativePriority: string;
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatStatblockSeedDraft {
  statblockId: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatSystemsSeedDraft {
  entryKey: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

function asCharacterXianxiaNamedRecord(value: unknown): CharacterXianxiaNamedRecord {
  const record = asRecord(value);
  return {
    ...record,
    name: readString(record.name),
  } as CharacterXianxiaNamedRecord;
}

function draftKey(...parts: Array<string | number | null | undefined>): string {
  return parts.map((part) => String(part ?? "")).join("::");
}

function spellLevelLabel(value: string): string {
  const label = value.trim();
  return label || "Spells";
}

function spellLevelSortValue(label: string): number {
  const normalized = label.toLowerCase();
  if (normalized.includes("cantrip")) {
    return 0;
  }
  const match = normalized.match(/\b(\d+)(?:st|nd|rd|th)?\b/);
  return match ? Number(match[1]) : 999;
}

function groupSpellsByLevel<T>(
  spells: T[],
  levelLabelFor: (spell: T) => string,
): Array<{ key: string; label: string; spells: T[] }> {
  const groups = new Map<string, { key: string; label: string; sort: number; index: number; spells: T[] }>();
  spells.forEach((spell, index) => {
    const label = spellLevelLabel(levelLabelFor(spell));
    const sort = spellLevelSortValue(label);
    const key = draftKey(sort, label.toLowerCase());
    const group = groups.get(key);
    if (group) {
      group.spells.push(spell);
    } else {
      groups.set(key, { key, label, sort, index, spells: [spell] });
    }
  });
  return Array.from(groups.values())
    .sort((a, b) => a.sort - b.sort || a.index - b.index || a.label.localeCompare(b.label))
    .map(({ key, label, spells: groupedSpells }) => ({ key, label, spells: groupedSpells }));
}

function compactSpellDetailLine(values: string[]): string {
  return values.filter((value) => value && value !== "--").join(" | ");
}

function presentedSpellCardDetailLine(spell: CharacterPresentedSpell): string {
  return compactSpellDetailLine([
    spell.casting_time,
    spell.range,
    spell.duration,
    spell.components,
    spell.save_or_hit,
  ]);
}

function rawSpellCardDetailLine(spell: Record<string, unknown>): string {
  return compactSpellDetailLine([
    readString(spell.casting_time),
    readString(spell.range),
    readString(spell.duration),
    readString(spell.components),
  ]);
}

function collectPresentedSpells(character: CharacterRecord | undefined): CharacterPresentedSpell[] {
  const spellcasting = character?.presented_spellcasting;
  const sections =
    spellcasting?.current_row_sections?.length
      ? spellcasting.current_row_sections
      : spellcasting?.row_sections ?? [];
  const spells: CharacterPresentedSpell[] = [];
  const seen = new Set<string>();

  const addSpell = (spell: CharacterPresentedSpell) => {
    const key = draftKey(spell.class_row_id, spell.name, spell.level_label).toLowerCase();
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    spells.push(spell);
  };

  for (const section of sections) {
    for (const spell of section.spells ?? []) {
      addSpell(spell);
    }
    for (const levelSection of section.spell_level_sections ?? []) {
      for (const group of levelSection.groups ?? []) {
        for (const spell of group.spells ?? []) {
          addSpell(spell);
        }
      }
    }
  }

  return spells;
}

function spellDetailFacts(spell: CharacterPresentedSpell): DetailFact[] {
  const levelAndSchool = [spell.level_label, spell.school ? `(${spell.school})` : ""].filter(Boolean).join(" ");
  return [
    { label: "Level", value: levelAndSchool },
    { label: "Casting time", value: spell.casting_time },
    { label: "Range", value: spell.range },
    { label: "Duration", value: spell.duration },
    { label: "Components", value: spell.components },
    { label: "Save / attack", value: spell.save_or_hit },
  ].filter((fact) => fact.value && fact.value !== "--");
}

function characterSystem(character: CharacterRecord | undefined): string {
  return readString(character?.definition?.system, "DND-5E");
}

function isDndCharacter(character: CharacterRecord | undefined): boolean {
  return characterSystem(character).toLowerCase() === "dnd-5e";
}

function isXianxiaCharacter(character: CharacterRecord | undefined): boolean {
  return characterSystem(character).toLowerCase() === "xianxia";
}

const dndCharacterSections: Array<{ id: CharacterSection; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "resources", label: "Resources" },
  { id: "spells", label: "Spells" },
  { id: "equipment", label: "Equipment" },
  { id: "inventory", label: "Inventory" },
  { id: "abilities", label: "Abilities and Skills" },
  { id: "notes", label: "Notes" },
];

const xianxiaCharacterSections: Array<{ id: CharacterSection; label: string }> = [
  { id: "quick-reference", label: "Quick Reference" },
  { id: "martial-arts", label: "Martial Arts" },
  { id: "techniques", label: "Techniques" },
  { id: "resources", label: "Resources" },
  { id: "skills", label: "Skills" },
  { id: "equipment", label: "Equipment" },
  { id: "inventory", label: "Inventory" },
  { id: "personal", label: "Personal" },
  { id: "notes", label: "Notes" },
];

function normalizeCharacterSection(value: string | null): CharacterSection | null {
  switch ((value || "").trim().toLowerCase()) {
    case "overview":
    case "quick":
      return "overview";
    case "quick-reference":
      return "quick-reference";
    case "martial-arts":
      return "martial-arts";
    case "resources":
      return "resources";
    case "spells":
    case "spellcasting":
      return "spells";
    case "techniques":
      return "techniques";
    case "equipment":
      return "equipment";
    case "inventory":
      return "inventory";
    case "abilities":
    case "abilities-and-skills":
      return "abilities";
    case "skills":
      return "skills";
    case "personal":
      return "personal";
    case "notes":
      return "notes";
    case "controls":
      return "controls";
    default:
      return null;
  }
}

const xianxiaVitalsFields: Array<{ key: CharacterXianxiaVitalsField; label: string }> = [
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

function joinDisplay(values: Array<string | number | null | undefined>): string {
  return values.map((value) => String(value ?? "").trim()).filter(Boolean).join(" | ");
}

function xianxiaDaoUseRecordDraftKey(record: CharacterXianxiaNamedRecord): string {
  if (record.use_record_index !== undefined) {
    return String(record.use_record_index);
  }
  return draftKey(record.name, record.status, record.approval_timestamp);
}

function normalizeTagsInput(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function xianxiaInventoryDraftFromItem(item?: CharacterXianxiaInventoryItem): CharacterXianxiaInventoryDraft {
  return {
    name: item?.name ?? "",
    quantity: String(item?.quantity ?? 1),
    itemNature: item?.item_nature || "Mundane",
    itemType: item?.item_type || "Miscellaneous",
    notes: item?.notes ?? "",
    tags: (item?.tags ?? []).join(", "),
    catalogRef: item?.catalog_ref ?? "",
    equippable: Boolean(item?.equippable),
    isEquipped: Boolean(item?.is_equipped),
  };
}

function xianxiaInventoryPayloadFromDraft(draft: CharacterXianxiaInventoryDraft): CharacterXianxiaInventoryItemPayload {
  const quantity = Number(draft.quantity);
  return {
    name: draft.name.trim(),
    quantity: Number.isFinite(quantity) ? quantity : 1,
    item_nature: draft.itemNature.trim() || "Mundane",
    item_type: draft.itemType.trim() || "Miscellaneous",
    notes: draft.notes.trim(),
    tags: normalizeTagsInput(draft.tags),
    catalog_ref: draft.catalogRef.trim(),
    equippable: draft.equippable,
    is_equipped: draft.isEquipped,
  };
}

function isCombatUnchangedPayload(payload: CombatLiveStatePayload): payload is Extract<CombatLiveStatePayload, { changed: false }> {
  return payload.changed === false;
}

function resolveCombatLivePayload(
  previous: CombatPayload | undefined,
  liveResponse: CombatLiveStatePayload,
): CombatPayload | null {
  if (isCombatUnchangedPayload(liveResponse)) {
    return previous ?? null;
  }
  if (previous) {
    return {
      ...liveResponse,
      available_character_choices: liveResponse.available_character_choices?.length
        ? liveResponse.available_character_choices
        : previous.available_character_choices,
      available_statblock_choices: liveResponse.available_statblock_choices?.length
        ? liveResponse.available_statblock_choices
        : previous.available_statblock_choices,
      combat_condition_options: liveResponse.combat_condition_options?.length
        ? liveResponse.combat_condition_options
        : previous.combat_condition_options,
    };
  }
  return liveResponse;
}

function CharacterPane({
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
  const [vitalsDraft, setVitalsDraft] = useState<CharacterVitalsDraft>({
    expectedRevision: 0,
    currentHp: "",
    tempHp: "",
  });
  const [xianxiaVitalsDraft, setXianxiaVitalsDraft] = useState<CharacterXianxiaVitalsDraft>({
    expectedRevision: 0,
    currentHp: "",
    tempHp: "",
    currentStance: "",
    tempStance: "",
    currentJing: "",
    currentQi: "",
    currentShen: "",
    currentYin: "",
    currentYang: "",
    currentDao: "",
  });
  const [xianxiaActiveDraft, setXianxiaActiveDraft] = useState<CharacterXianxiaActiveStateDraft>({
    expectedRevision: 0,
    activeStanceName: "",
    activeAuraName: "",
  });
  const [notesDraft, setNotesDraft] = useState<CharacterNotesDraft>({ expectedRevision: 0, notes: "" });
  const [resourceDrafts, setResourceDrafts] = useState<Record<string, string>>({});
  const [spellSlotDrafts, setSpellSlotDrafts] = useState<Record<string, string>>({});
  const [inventoryDrafts, setInventoryDrafts] = useState<Record<string, string>>({});
  const [equipmentDrafts, setEquipmentDrafts] = useState<Record<string, CharacterEquipmentDraft>>({});
  const [xianxiaInventoryDrafts, setXianxiaInventoryDrafts] = useState<Record<string, CharacterXianxiaInventoryDraft>>({});
  const [newXianxiaInventoryDraft, setNewXianxiaInventoryDraft] = useState<CharacterXianxiaInventoryDraft>(
    xianxiaInventoryDraftFromItem(),
  );
  const [xianxiaDaoRequestDraft, setXianxiaDaoRequestDraft] = useState<CharacterXianxiaDaoUseRequestDraft>({
    requestName: "",
    notes: "",
    preparedRecordIndex: "",
  });
  const [xianxiaDaoUseNotesDrafts, setXianxiaDaoUseNotesDrafts] = useState<Record<string, string>>({});
  const [arcaneArmorDraft, setArcaneArmorDraft] = useState(false);
  const [currencyDraft, setCurrencyDraft] = useState<Record<string, string>>({});
  const [portraitDraft, setPortraitDraft] = useState<CharacterPortraitDraft>({
    file: null,
    fileName: "",
    altText: "",
    caption: "",
  });
  const [controlsDraft, setControlsDraft] = useState<CharacterControlsDraft>({
    assignedUserId: "",
    deleteConfirmation: "",
  });
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
    const character = detailQuery.data.character;
    const state = asRecord(character.state_record.state);
    const vitals = asRecord(state.vitals);
    const xianxiaState = asRecord(state.xianxia);
    const xianxiaVitals = asRecord(xianxiaState.vitals);
    const xianxiaEnergies = asRecord(xianxiaState.energies);
    const xianxiaYinYang = asRecord(xianxiaState.yin_yang);
    const xianxiaDao = asRecord(xianxiaState.dao);
    const presentedXianxia = character.presented_xianxia;
    const notes = asRecord(state.notes);
    const nextResourceDrafts: Record<string, string> = {};
    for (const resource of asRecordArray(state.resources)) {
      const id = readString(resource.id);
      if (id) {
        nextResourceDrafts[id] = String(readNumber(resource.current));
      }
    }
    const nextSpellSlotDrafts: Record<string, string> = {};
    for (const slot of asRecordArray(state.spell_slots)) {
      const key = draftKey(readNumber(slot.level), readString(slot.slot_lane_id));
      nextSpellSlotDrafts[key] = String(readNumber(slot.used));
    }
    const nextInventoryDrafts: Record<string, string> = {};
    for (const item of asRecordArray(state.inventory)) {
      const id = readString(item.id);
      if (id) {
        nextInventoryDrafts[id] = String(readNumber(item.quantity, 1));
      }
    }
    const nextXianxiaInventoryDrafts: Record<string, CharacterXianxiaInventoryDraft> = {};
    for (const item of presentedXianxia?.inventory?.quantities ?? []) {
      if (item.id) {
        nextXianxiaInventoryDrafts[item.id] = xianxiaInventoryDraftFromItem(item);
        nextInventoryDrafts[item.id] = String(readNumber(item.quantity, 1));
      }
    }
    const nextXianxiaDaoUseNotesDrafts: Record<string, string> = {};
    for (const group of presentedXianxia?.approval?.status_groups ?? []) {
      if (group.key !== "dao_immolating_use_records") {
        continue;
      }
      for (const record of group.records) {
        nextXianxiaDaoUseNotesDrafts[xianxiaDaoUseRecordDraftKey(record)] = readString(record.use_notes);
      }
    }
    const equipmentState = detailQuery.data.character.equipment_state;
    const nextEquipmentDrafts: Record<string, CharacterEquipmentDraft> = {};
    for (const item of equipmentState?.rows ?? []) {
      if (item.id) {
        nextEquipmentDrafts[item.id] = {
          isEquipped: Boolean(item.is_equipped),
          isAttuned: Boolean(item.is_attuned),
          weaponWieldMode: item.weapon_wield_mode || "",
        };
      }
    }
    setEquipmentDrafts(nextEquipmentDrafts);
    setXianxiaInventoryDrafts(nextXianxiaInventoryDrafts);
    setXianxiaDaoUseNotesDrafts(nextXianxiaDaoUseNotesDrafts);
    setXianxiaDaoRequestDraft({ requestName: "", notes: "", preparedRecordIndex: "" });
    setArcaneArmorDraft(Boolean((detailQuery.data.character.arcane_armor_state ?? equipmentState?.arcane_armor_state)?.enabled));
    const currency = isXianxiaCharacter(character) ? asRecord(xianxiaState.currency) : asRecord(state.currency);
    const nextCurrencyDraft: Record<string, string> = {};
    for (const key of ["cp", "sp", "ep", "gp", "pp", "coin", "supply", "spirit_stones"]) {
      if (currency[key] !== undefined) {
        nextCurrencyDraft[key] = String(readNumber(currency[key]));
      }
    }
    setVitalsDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      currentHp: String(readNumber(vitals.current_hp, 0)),
      tempHp: String(readNumber(vitals.temp_hp, 0)),
    });
    setXianxiaVitalsDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
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
    });
    setXianxiaActiveDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      activeStanceName: presentedXianxia?.active_state?.stance?.name ?? "",
      activeAuraName: presentedXianxia?.active_state?.aura?.name ?? "",
    });
    setNotesDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      notes: readString(notes.player_notes_markdown),
    });
    setResourceDrafts(nextResourceDrafts);
    setSpellSlotDrafts(nextSpellSlotDrafts);
    setInventoryDrafts(nextInventoryDrafts);
    setCurrencyDraft(nextCurrencyDraft);
    setPortraitDraft({
      file: null,
      fileName: "",
      altText: character.portrait?.alt_text ?? "",
      caption: character.portrait?.caption ?? "",
    });
    setControlsDraft({
      assignedUserId: character.controls?.assignment?.user_id ? String(character.controls.assignment.user_id) : "",
      deleteConfirmation: "",
    });
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
              <section className="read-section" id="character-quick-abilities-skills">
                <div className="section-heading">
                  <h2>Abilities and Skills</h2>
                </div>
                {hasDndAbilitySkillsContent ? (
                  <>
                    <div className="ability-grid ability-grid--skills">
                      {dndAbilities.map((ability, abilityIndex) => {
                        const abilityRecord = asRecord(ability);
                        const abilitySkills = asRecordArray(abilityRecord.skills);
                        const abilityScoreValue = readNumber(abilityRecord.score, NaN);
                        const abilityScore = Number.isNaN(abilityScoreValue) ? "--" : String(abilityScoreValue);
                        const abilityName = readString(abilityRecord.name);
                        return (
                          <article
                            className="ability-card ability-card--skills"
                            key={readString(abilityRecord.key, `ability-${abilityIndex}`)}
                          >
                            <div className="ability-card__summary">
                              <h3 className="ability-card__name">
                                {abilityName || readString(abilityRecord.key, "Ability")}
                              </h3>
                              <strong className="ability-card__score">{abilityScore}</strong>
                              <div className="ability-card__values">
                                <span className="ability-card__value">
                                  <span>Modifier</span>
                                  <strong>{readString(abilityRecord.modifier)}</strong>
                                </span>
                                <span className="ability-card__value">
                                  <span>Save</span>
                                  <strong>{readString(abilityRecord.save_bonus)}</strong>
                                </span>
                              </div>
                            </div>
                            {abilitySkills.length ? (
                              <ul className="plain-list ability-skill-list">
                                {abilitySkills.map((skill, skillIndex) => {
                                  const skillRecord = asRecord(skill);
                                  const isProficient = Boolean(skillRecord.is_proficient);
                                  const proficiencyLabel = readString(skillRecord.proficiency_label);
                                  const normalizedProficiency = proficiencyLabel.toLowerCase();
                                  const proficiencyClass =
                                    normalizedProficiency === "expertise"
                                      ? "ability-skill-list__item--expertise"
                                      : isProficient
                                        ? "ability-skill-list__item--proficient"
                                        : "";
                                  const skillName = readString(skillRecord.name);
                                  const skillBonus = readString(skillRecord.bonus);
                                  return (
                                    <li
                                      className={["ability-skill-list__item", proficiencyClass].filter(Boolean).join(" ")}
                                      key={readString(skillRecord.name, `skill-${abilityIndex}-${skillIndex}`)}
                                    >
                                      <span className="ability-skill-list__pill">
                                        <span className="ability-skill-list__name">{skillName}</span>
                                        <strong className="ability-skill-list__bonus">{skillBonus}</strong>
                                        {proficiencyLabel && proficiencyLabel !== "None" ? (
                                          <span className="visually-hidden">{proficiencyLabel}</span>
                                        ) : null}
                                      </span>
                                    </li>
                                  );
                                })}
                              </ul>
                            ) : (
                              <p className="meta">No linked skills</p>
                            )}
                          </article>
                        );
                      })}
                    </div>

                    {dndProficiencyGroups.length ? (
                      <div className="detail-cluster">
                        <div>
                          <h3>Proficiencies</h3>
                          <div className="detail-grid">
                            {dndProficiencyGroups.map((group) => {
                              const groupRecord = asRecord(group);
                              return (
                                <article className="detail-card" key={readString(groupRecord.title)}>
                                  <h4>{readString(groupRecord.title)}</h4>
                                  <p>{asStringArray(groupRecord.values_list).join(", ")}</p>
                                </article>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <article className="detail-card">
                    <p className="meta">No ability or skill details are recorded on this sheet yet.</p>
                  </article>
                )}
              </section>
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

interface StagedArticleDraftState {
  title: string;
  body: string;
  imageAltText: string;
  imageCaption: string;
  image?: EmbeddedImageInput | null;
}

interface DmContentConditionDraftState {
  name: string;
  description: string;
}

interface DmPlayerWikiDraftState {
  title: string;
  slugLeaf: string;
  section: string;
  pageType: string;
  subsection: string;
  summary: string;
  aliases: string;
  revealAfterSession: string;
  displayOrder: string;
  published: boolean;
  sourceRef: string;
  image: string;
  imageAlt: string;
  imageCaption: string;
  bodyMarkdown: string;
  imageUpload: EmbeddedImageInput | null;
}

type DmContentLane = "statblocks" | "staged-articles" | "conditions" | "player-wiki" | "systems";

interface DmContentStatblockDraftState {
  filename: string;
  subsection: string;
  markdown: string;
}

interface DmContentSystemsCustomDraftState {
  title: string;
  slugLeaf: string;
  entryType: string;
  visibility: string;
  provenance: string;
  searchMetadata: string;
  bodyMarkdown: string;
}

const PLAYER_WIKI_SECTION_CHOICES = [
  { label: "NPCs", targetSubdir: "npcs", defaultType: "npc" },
  { label: "Locations", targetSubdir: "locations", defaultType: "location" },
  { label: "Factions", targetSubdir: "factions", defaultType: "faction" },
  { label: "Items", targetSubdir: "items", defaultType: "item" },
  { label: "Gods", targetSubdir: "gods", defaultType: "god" },
  { label: "Lore", targetSubdir: "lore", defaultType: "lore" },
  { label: "Mechanics", targetSubdir: "mechanics", defaultType: "rule" },
  { label: "Notes", targetSubdir: "notes", defaultType: "note" },
  { label: "Races", targetSubdir: "races", defaultType: "race" },
  { label: "Sessions", targetSubdir: "sessions", defaultType: "session" },
  { label: "Spells", targetSubdir: "spells", defaultType: "spell" },
];

function simpleSlug(value: string, fallback = "page"): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || fallback;
}

function sectionChoiceForLabel(section: string) {
  const normalized = section.trim().toLowerCase();
  return (
    PLAYER_WIKI_SECTION_CHOICES.find((choice) => choice.label.toLowerCase() === normalized) ??
    PLAYER_WIKI_SECTION_CHOICES.find((choice) => choice.label === "Notes") ??
    PLAYER_WIKI_SECTION_CHOICES[0]
  );
}

function buildInitialPlayerWikiDraft(): DmPlayerWikiDraftState {
  return {
    title: "",
    slugLeaf: "",
    section: "Notes",
    pageType: "note",
    subsection: "",
    summary: "",
    aliases: "",
    revealAfterSession: "0",
    displayOrder: "10000",
    published: true,
    sourceRef: "",
    image: "",
    imageAlt: "",
    imageCaption: "",
    bodyMarkdown: "",
    imageUpload: null,
  };
}

function buildInitialSystemsCustomDraft(payload?: DmContentSystemsResponse | null): DmContentSystemsCustomDraftState {
  return {
    title: "",
    slugLeaf: "",
    entryType: payload?.custom_entry_type_choices[0]?.value ?? "rule",
    visibility: payload?.custom_entry_default_visibility ?? "players",
    provenance: "",
    searchMetadata: "",
    bodyMarkdown: "",
  };
}

function buildSystemsCustomDraftFromEntry(entry: CustomSystemsEntry): DmContentSystemsCustomDraftState {
  return {
    title: entry.title,
    slugLeaf: entry.slug,
    entryType: entry.entry_type || "rule",
    visibility: entry.visibility || "players",
    provenance: entry.provenance || "",
    searchMetadata: entry.search_metadata || "",
    bodyMarkdown: entry.body_markdown || "",
  };
}

function buildCustomSystemsPayload(draft: DmContentSystemsCustomDraftState): CustomSystemsEntryPayload {
  return {
    title: draft.title.trim(),
    slug_leaf: draft.slugLeaf.trim(),
    entry_type: draft.entryType,
    visibility: draft.visibility,
    provenance: draft.provenance,
    search_metadata: draft.searchMetadata,
    body_markdown: draft.bodyMarkdown,
  };
}

function metadataString(metadata: ContentPageMetadata, key: string): string {
  const value = metadata[key];
  if (value === undefined || value === null) {
    return "";
  }
  return String(value);
}

function metadataNumberText(metadata: ContentPageMetadata, key: string, fallback: number): string {
  const value = Number(metadata[key]);
  return Number.isFinite(value) ? String(value) : String(fallback);
}

function metadataBoolean(metadata: ContentPageMetadata, key: string, fallback: boolean): boolean {
  const value = metadata[key];
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function aliasTextFromMetadata(metadata: ContentPageMetadata, page: ContentPageFileSummary["page"]): string {
  const metadataAliases = metadata.aliases;
  if (Array.isArray(metadataAliases)) {
    return metadataAliases.map((value) => String(value || "").trim()).filter(Boolean).join("\n");
  }
  if (typeof metadataAliases === "string") {
    return metadataAliases;
  }
  return page.aliases.join("\n");
}

function buildPlayerWikiDraftFromRecord(record: ContentPageFileRecord): DmPlayerWikiDraftState {
  const metadata = record.metadata ?? {};
  const page = record.page;
  return {
    title: page.title || metadataString(metadata, "title"),
    slugLeaf: record.page_ref.split("/").pop() || "",
    section: page.section || metadataString(metadata, "section") || "Notes",
    pageType: page.page_type || metadataString(metadata, "type") || "note",
    subsection: page.subsection || metadataString(metadata, "subsection"),
    summary: page.summary || metadataString(metadata, "summary"),
    aliases: aliasTextFromMetadata(metadata, page),
    revealAfterSession: String(page.reveal_after_session ?? metadataNumberText(metadata, "reveal_after_session", 0)),
    displayOrder: String(page.display_order ?? metadataNumberText(metadata, "display_order", 10000)),
    published: metadataBoolean(metadata, "published", page.published),
    sourceRef: page.source_ref || metadataString(metadata, "source_ref"),
    image: page.image_path || metadataString(metadata, "image"),
    imageAlt: page.image_alt || metadataString(metadata, "image_alt"),
    imageCaption: page.image_caption || metadataString(metadata, "image_caption"),
    bodyMarkdown: record.body_markdown || "",
    imageUpload: null,
  };
}

function buildPageRefFromDraft(draft: DmPlayerWikiDraftState): string {
  const choice = sectionChoiceForLabel(draft.section);
  const slugLeaf = simpleSlug(draft.slugLeaf || draft.title, "page");
  return `${choice.targetSubdir}/${slugLeaf}`;
}

function parseNonNegativeInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function buildPlayerWikiMetadata(
  draft: DmPlayerWikiDraftState,
  pageRef: string,
  imageRef: string,
): ContentPageMetadata {
  return {
    slug: pageRef,
    title: draft.title.trim(),
    section: draft.section.trim() || "Notes",
    type: draft.pageType.trim() || sectionChoiceForLabel(draft.section).defaultType,
    subsection: draft.subsection.trim(),
    summary: draft.summary.trim(),
    aliases: draft.aliases
      .split(/\r?\n|,/)
      .map((value) => value.trim())
      .filter(Boolean),
    reveal_after_session: parseNonNegativeInteger(draft.revealAfterSession, 0),
    display_order: parseNonNegativeInteger(draft.displayOrder, 10000),
    published: draft.published,
    source_ref: draft.sourceRef.trim(),
    image: imageRef.trim(),
    image_alt: draft.imageAlt.trim(),
    image_caption: draft.imageCaption.trim(),
  };
}

function imageExtension(image: EmbeddedImageInput): string {
  const filenameExtension = image.filename.match(/\.([a-z0-9]+)$/i)?.[1]?.toLowerCase();
  if (filenameExtension) {
    return `.${filenameExtension}`;
  }
  if (image.media_type === "image/jpeg") {
    return ".jpg";
  }
  if (image.media_type === "image/png") {
    return ".png";
  }
  if (image.media_type === "image/gif") {
    return ".gif";
  }
  if (image.media_type === "image/webp") {
    return ".webp";
  }
  return ".bin";
}

function buildPlayerWikiAssetRef(pageRef: string, image: EmbeddedImageInput): string {
  return `wiki-pages/${simpleSlug(pageRef, "wiki-page")}${imageExtension(image)}`;
}

function playerWikiStatusLabel(pageFile: ContentPageFileSummary): string {
  if (pageFile.page.is_visible) {
    return "Visible";
  }
  if (!pageFile.page.published) {
    return "Unpublished";
  }
  return `Reveals after session ${pageFile.page.reveal_after_session}`;
}

function playerWikiRemovalSafety(pageFile: ContentPageFileSummary): ContentPageRemovalSafety {
  const nested = pageFile.removal_safety;
  const blockers = pageFile.hard_delete_blockers ?? nested?.hard_delete_blockers ?? [];
  const canHardDelete = pageFile.can_hard_delete ?? nested?.can_hard_delete ?? blockers.length === 0;
  return {
    can_hard_delete: canHardDelete,
    hard_delete_blockers: blockers,
    removal_status_label:
      pageFile.removal_status_label ?? nested?.removal_status_label ?? (canHardDelete ? "Hard delete available" : "Hard delete blocked"),
    removal_guidance:
      pageFile.removal_guidance ??
      nested?.removal_guidance ??
      (canHardDelete
        ? "Hard delete is available after confirmation."
        : "Unpublish/archive this page or clear the references before deleting its file."),
    page_title: nested?.page_title,
  };
}

function buildInitialStatblockDraft(statblock: DmContentStatblock): DmContentStatblockDraftState {
  return {
    filename: statblock.source_filename || `${statblock.title || "statblock"}.md`,
    subsection: statblock.subsection || "",
    markdown: statblock.body_markdown || "",
  };
}

function buildInitialConditionDraft(condition: DmContentConditionDefinition): DmContentConditionDraftState {
  return {
    name: condition.name || "",
    description: condition.description_markdown || "",
  };
}

function formatInitiativeBonus(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function DmPane({
  campaignSlug,
  payload,
  refetch,
  setAuthRequired,
}: {
  campaignSlug: string;
  payload: SessionPayload | undefined;
  refetch: () => void;
  setAuthRequired: (required: boolean) => void;
}) {
  const { apiClient } = useApiClient();
  const stagedArticles: SessionArticle[] = payload?.staged_articles ?? [];
  const revealedArticles: SessionArticle[] = payload?.revealed_articles ?? [];
  const sessionLogs: SessionLogSummary[] = payload?.session_logs ?? [];
  const passiveScores: SessionDmPassiveScoreRow[] = payload?.session_dm_passive_scores ?? [];
  const shouldShowPassiveScores = Boolean(payload?.show_session_dm_passive_scores);
  const activeSession = payload?.active_session;
  const activeMessageCount = payload?.messages.length ?? 0;
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState<ManualArticleDraftState>(buildEmptyManualArticleDraft);
  const [uploadDraft, setUploadDraft] = useState({ filename: "", markdown: "", image: null as EmbeddedImageInput | null });
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceResults, setSourceResults] = useState<SessionArticleSourceResult[]>([]);
  const [sourceStatus, setSourceStatus] = useState<string | null>(null);
  const [selectedSourceRef, setSelectedSourceRef] = useState("");
  const [stagedDrafts, setStagedDrafts] = useState<Record<number, StagedArticleDraftState>>({});
  const [uiMessage, setUiMessage] = useState<string | null>(null);
  const [paneError, setPaneError] = useState<string | null>(null);
  const [selectedLogSessionId, setSelectedLogSessionId] = useState<number | null>(null);

  useEffect(() => {
    setStagedDrafts((current) => {
      const next: Record<number, StagedArticleDraftState> = {};
      for (const article of stagedArticles) {
        const existing = current[article.id];
        next[article.id] = existing ?? {
          title: article.title,
          body: article.body_markdown,
          imageAltText: article.image?.alt_text || "",
          imageCaption: article.image?.caption || "",
        };
      }
      return next;
    });
  }, [stagedArticles]);

  useEffect(() => {
    if (!sessionLogs.length) {
      setSelectedLogSessionId(null);
      return;
    }
    if (selectedLogSessionId !== null && !sessionLogs.some((entry) => entry.session.id === selectedLogSessionId)) {
      setSelectedLogSessionId(sessionLogs[0]?.session.id ?? null);
    }
  }, [sessionLogs, selectedLogSessionId]);

  const startSessionMutation = useMutation({
    mutationFn: () => apiClient.startSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session started.");
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const closeSessionMutation = useMutation({
    mutationFn: () => apiClient.closeSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session closed.");
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(campaignSlug, payload),
    onSuccess: () => {
      setUiMessage("Article created.");
      setPaneError(null);
      setManualDraft(buildEmptyManualArticleDraft());
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateArticleMutation = useMutation({
    mutationFn: (args: { id: number; payload: { title: string; body_markdown: string; image_alt_text?: string; image_caption?: string } }) =>
      apiClient.updateSessionArticle(campaignSlug, args.id, args.payload),
    onSuccess: () => {
      setUiMessage("Article updated.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const revealArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.revealSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article revealed.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article deleted.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const clearRevealedMutation = useMutation({
    mutationFn: () => apiClient.clearRevealedSessionArticles(campaignSlug),
    onSuccess: () => {
      setUiMessage("Revealed articles cleared.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteLogMutation = useMutation({
    mutationFn: (sessionId: number) => apiClient.deleteSessionLog(campaignSlug, sessionId),
    onSuccess: (_data, sessionId) => {
      setUiMessage("Session log deleted.");
      setPaneError(null);
      if (selectedLogSessionId === sessionId) {
        setSelectedLogSessionId(null);
      }
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const logQuery = useQuery({
    queryKey: ["session-log-detail", campaignSlug, selectedLogSessionId],
    queryFn: () => {
      if (selectedLogSessionId === null) {
        throw new Error("No session selected.");
      }
      return apiClient.getSessionLog(campaignSlug, selectedLogSessionId);
    },
    enabled: Boolean(campaignSlug) && selectedLogSessionId !== null,
    retry: false,
  });

  useEffect(() => {
    if (logQuery.error && isAuthError(logQuery.error)) {
      setAuthRequired(true);
    }
  }, [logQuery.error, setAuthRequired]);

  const searchSources = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = sourceQuery.trim();
    if (!query) {
      setSourceStatus("Search with a query.");
      return;
    }
    setSourceStatus("Searching ...");
    try {
      const response = await apiClient.searchSessionArticleSources(campaignSlug, query);
      setSourceResults(response.results);
      setSourceStatus(response.message || "Search complete.");
      if (!response.results.length) {
        setSelectedSourceRef("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSourceResults([]);
      setSourceStatus(null);
      setPaneError(apiErrorMessage(error));
    }
  };

  const createArticle = (createPayload: SessionArticleCreatePayload) => {
    setPaneError(null);
    createArticleMutation.mutate(createPayload);
  };

  const clearArticleStatus = () => {
    setPaneError(null);
    setUiMessage(null);
  };

  const statusText = startSessionMutation.isPending ? "Starting session..." : closeSessionMutation.isPending ? "Closing session..." : null;

  return (
    <div className="page-layout session-layout">
      <section className="session-column">
        {shouldShowPassiveScores ? (
          <details className="section-block section-block--collapsible session-passive-scores-bar" id="session-passive-scores" open>
            <summary className="section-toggle-summary">
              <span className="section-toggle-summary__content">
                <span className="section-title">Passive scores</span>
                <span className="meta">{passiveScores.length}</span>
              </span>
              <span className="section-toggle-chevron" aria-hidden="true"></span>
            </summary>
            <div className="section-block__body">
              {passiveScores.length ? (
                <div className="session-passive-score-list">
                  {passiveScores.map((row) => (
                    <article className="session-passive-score-card" key={row.name}>
                      <h4>{row.name}</h4>
                      <div className="session-passive-score-grid">
                        <p>
                          <span className="session-passive-score-label">Passive Perception</span>
                          <span className="session-passive-score-value">{row.passive_perception}</span>
                        </p>
                        <p>
                          <span className="session-passive-score-label">Passive Insight</span>
                          <span className="session-passive-score-value">{row.passive_insight}</span>
                        </p>
                        <p>
                          <span className="session-passive-score-label">Passive Investigation</span>
                          <span className="session-passive-score-value">{row.passive_investigation}</span>
                        </p>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="status status-neutral">
                  No visible DND-5E characters are currently available on the DM session surface.
                </p>
              )}
            </div>
          </details>
        ) : null}

        <article className="card session-sidebar-card" id="session-staged-articles">
          <div className="section-heading">
            <h2>Staged articles</h2>
            <p className="meta">{stagedArticles.length}</p>
          </div>
          {stagedArticles.length ? (
            <div className="session-article-stack">
              {stagedArticles.map((article) => {
                const savedLabel = article.created_at ? `Saved ${formatTimestamp(article.created_at)}` : null;
                const draft = stagedDrafts[article.id] ?? {
                  title: article.title,
                  body: article.body_markdown,
                  imageAltText: article.image?.alt_text || "",
                  imageCaption: article.image?.caption || "",
                };

                return (
                  <details className="feature-detail session-article-detail" data-session-article-id={article.id} key={article.id}>
                    <summary>
                      <span>{article.title}</span>
                      {savedLabel ? <span className="meta">{savedLabel}</span> : null}
                    </summary>
                    {article.image ? (
                      <figure className="article-figure">
                        <img className="article-image" src={resolveArticleImage(campaignSlug, article)} alt={article.image.alt_text || "Article image"} />
                        {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                      </figure>
                    ) : null}
                    <SessionArticleSourceLine article={article} />
                    {renderArticleBody(article, "article-body--compact")}
                    <details className="session-article-edit-detail">
                      <summary>Edit prep draft</summary>
                      <form
                        className="stack-form session-article-edit-form"
                        onSubmit={(event: FormEvent<HTMLFormElement>) => {
                          event.preventDefault();
                          const articlePayload: {
                            title: string;
                            body_markdown: string;
                            image_alt_text?: string;
                            image_caption?: string;
                          } = {
                            title: draft.title,
                            body_markdown: draft.body,
                          };
                          if (article.image) {
                            articlePayload.image_alt_text = draft.imageAltText || "";
                            articlePayload.image_caption = draft.imageCaption || "";
                          }
                          updateArticleMutation.mutate({
                            id: article.id,
                            payload: articlePayload,
                          });
                        }}
                      >
                        <label className="field" htmlFor={`dm-stage-title-${article.id}`}>
                          <span>Title</span>
                          <input
                            id={`dm-stage-title-${article.id}`}
                            value={draft.title}
                            onChange={(event: ChangeEvent<HTMLInputElement>) => {
                              setStagedDrafts({
                                ...stagedDrafts,
                                [article.id]: {
                                  ...draft,
                                  title: event.currentTarget.value,
                                },
                              });
                            }}
                          />
                        </label>
                        <label className="field" htmlFor={`dm-stage-body-${article.id}`}>
                          <span>Body (markdown or html)</span>
                          <textarea
                            id={`dm-stage-body-${article.id}`}
                            rows={6}
                            value={draft.body}
                            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                              setStagedDrafts({
                                ...stagedDrafts,
                                [article.id]: {
                                  ...draft,
                                  body: event.currentTarget.value,
                                },
                              });
                            }}
                          />
                        </label>
                        <label className="field" htmlFor={`dm-stage-alt-${article.id}`}>
                          <span>Image alt text (optional)</span>
                          <input
                            id={`dm-stage-alt-${article.id}`}
                            value={draft.imageAltText}
                            onChange={(event: ChangeEvent<HTMLInputElement>) => {
                              setStagedDrafts({
                                ...stagedDrafts,
                                [article.id]: {
                                  ...draft,
                                  imageAltText: event.currentTarget.value,
                                },
                              });
                            }}
                          />
                        </label>
                        <label className="field" htmlFor={`dm-stage-caption-${article.id}`}>
                          <span>Image caption (optional)</span>
                          <input
                            id={`dm-stage-caption-${article.id}`}
                            value={draft.imageCaption}
                            onChange={(event: ChangeEvent<HTMLInputElement>) => {
                              setStagedDrafts({
                                ...stagedDrafts,
                                [article.id]: {
                                  ...draft,
                                  imageCaption: event.currentTarget.value,
                                },
                              });
                            }}
                          />
                        </label>
                        <button
                          type="submit"
                          className="ghost-button"
                          disabled={updateArticleMutation.isPending}
                        >
                          {updateArticleMutation.isPending ? "Saving..." : "Update prep draft"}
                        </button>
                      </form>
                    </details>
                    <div className="session-article-detail__actions">
                      <SessionArticleReferenceActions article={article} includePromotionLinks />
                      {activeSession ? (
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={revealArticleMutation.isPending}
                          onClick={() => revealArticleMutation.mutate(article.id)}
                        >
                          {revealArticleMutation.isPending ? "Revealing..." : "Reveal in chat"}
                        </button>
                      ) : (
                        <p className="meta">Begin a session before revealing this article.</p>
                      )}
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={deleteArticleMutation.isPending}
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="meta">No unrevealed session articles are waiting right now.</p>
          )}
        </article>

        {revealedArticles.length ? (
          <article className="card session-sidebar-card" id="session-revealed-articles">
            <div className="section-heading">
              <div>
                <h2>Revealed articles</h2>
                <p className="meta">{revealedArticles.length}</p>
              </div>
              <button
                type="button"
                className="ghost-button"
                disabled={clearRevealedMutation.isPending || !revealedArticles.length}
                onClick={() => clearRevealedMutation.mutate()}
              >
                {clearRevealedMutation.isPending ? "Clearing..." : "Clear all"}
              </button>
            </div>
            <div className="session-article-stack">
              {revealedArticles.map((article) => {
                const revealedLabel = article.revealed_at
                  ? `Revealed ${formatTimestamp(article.revealed_at)}`
                  : article.created_at
                    ? `Revealed ${formatTimestamp(article.created_at)}`
                    : null;
                return (
                  <details className="feature-detail session-article-detail" data-session-article-id={article.id} key={article.id}>
                    <summary>
                      <span>{article.title}</span>
                      {revealedLabel ? <span className="meta">{revealedLabel}</span> : null}
                    </summary>
                    {article.image ? (
                      <figure className="article-figure">
                        <img
                          className="article-image"
                          src={resolveArticleImage(campaignSlug, article)}
                          alt={article.image.alt_text || "Article image"}
                        />
                        {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                      </figure>
                    ) : null}
                    <SessionArticleSourceLine article={article} />
                    {renderArticleBody(article, "article-body--compact")}
                    <div className="session-article-detail__actions">
                      <SessionArticleReferenceActions article={article} includePromotionLinks />
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                        disabled={deleteArticleMutation.isPending}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          </article>
        ) : null}

        <article className="card session-sidebar-card" id="session-chat-logs">
          <div className="section-heading">
            <h2>Chat logs</h2>
            <p className="meta">{sessionLogs.length}</p>
          </div>
          {sessionLogs.length ? (
            <div className="session-log-row">
              <ul className="plain-list session-log-list">
                {sessionLogs.map((entry) => {
                  const sessionLabel = entry.session.started_at
                    ? `Session log from ${formatTimestamp(entry.session.started_at)}`
                    : `Session ${entry.session.id}`;
                  const messageMeta = `${entry.message_count} message${entry.message_count === 1 ? "" : "s"}`;
                  return (
                    <li key={entry.session.id}>
                      <div className="session-log-list__row">
                        <button
                          type="button"
                          className={`session-log-list__content ${entry.session.id === selectedLogSessionId ? "active" : ""}`}
                          onClick={() => setSelectedLogSessionId(entry.session.id)}
                        >
                          <strong>{sessionLabel}</strong>
                          <p className="meta">
                            {messageMeta}
                            {entry.last_message_at ? ` | Last message ${formatTimestamp(entry.last_message_at)}` : null}
                          </p>
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => deleteLogMutation.mutate(entry.session.id)}
                          disabled={deleteLogMutation.isPending}
                        >
                          {deleteLogMutation.isPending ? "Deleting..." : "Delete log"}
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="session-log-detail">
                {logQuery.isLoading ? (
                  <p className="status status-neutral">Loading log detail...</p>
                ) : null}
                {logQuery.error ? <p className="status status-error">Unable to load log details.</p> : null}
                {logQuery.data ? (
                  <div>
                    <div className="session-log-detail-head">
                      <h4>Messages</h4>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}
                        disabled={deleteLogMutation.isPending}
                      >
                        {deleteLogMutation.isPending ? "Deleting..." : "Delete log"}
                      </button>
                    </div>
                    <ol className="log-messages">
                      {logQuery.data.messages.map((entry) => (
                        <li key={entry.id}>
                          <strong>{entry.author_display_name}</strong> [{formatTimestamp(entry.created_at)}]
                          <p>{entry.body_text}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : (
                  <p className="status status-neutral">Select a log to inspect.</p>
                )}
              </div>
            </div>
          ) : (
            <p className="meta">Closed sessions will appear here after the first live run.</p>
          )}
        </article>
      </section>

      <aside className="session-sidebar">
        <article className="card session-sidebar-card" id="session-controls">
          <div className="section-heading">
            <h2>Live session</h2>
            <p className="meta">{activeSession ? "Chat open" : "Chat closed"}</p>
          </div>
          {activeSession ? (
            <>
              <p>The session is live for players and the DM.</p>
              <p className="meta">Started {formatTimestamp(activeSession.started_at)}</p>
              <p className="meta">
                {activeMessageCount} chat entr{activeMessageCount === 1 ? "y" : "ies"}
              </p>
            </>
          ) : (
            <>
              <p>No active session is running right now.</p>
              <p className="meta">Start the session here to open chat on the player Session page.</p>
            </>
          )}
          <div className="session-status-controls">
            <h3>Session controls</h3>
            {!activeSession ? (
              <p>Start a session here to open chat on the player Session page and reveal staged handouts.</p>
            ) : null}
            {statusText || uiMessage ? <p className="meta">{statusText || uiMessage}</p> : null}
            {startSessionMutation.error ? (
              <p className="status status-error">{apiErrorMessage(startSessionMutation.error)}</p>
            ) : null}
            {closeSessionMutation.error ? <p className="status status-error">{apiErrorMessage(closeSessionMutation.error)}</p> : null}
            {paneError ? <p className="status status-error">{paneError}</p> : null}
          </div>
          <div className="session-actions-row">
            {activeSession ? (
              <button type="button" onClick={() => closeSessionMutation.mutate()} disabled={closeSessionMutation.isPending}>
                {closeSessionMutation.isPending ? "Closing..." : "Close session"}
              </button>
            ) : (
              <button type="button" onClick={() => startSessionMutation.mutate()} disabled={startSessionMutation.isPending}>
                {startSessionMutation.isPending ? "Starting..." : "Begin session"}
              </button>
            )}
          </div>
        </article>
        <DmArticleCreator
          className="card session-sidebar-card"
          id="session-article-store"
          mode={mode}
          setMode={(next) => {
            clearArticleStatus();
            setMode(next);
          }}
          sourceQuery={sourceQuery}
          setSourceQuery={setSourceQuery}
          sourceStatus={sourceStatus}
          setSourceStatus={setSourceStatus}
          sourceResults={sourceResults}
          selectedSourceRef={selectedSourceRef}
          setSelectedSourceRef={(next) => {
            setSelectedSourceRef(next);
            setSourceStatus(null);
          }}
          manualDraft={manualDraft}
          setManualDraft={(next) => {
            clearArticleStatus();
            setManualDraft(next);
          }}
          uploadDraft={uploadDraft}
          setUploadDraft={(next) => {
            clearArticleStatus();
            setUploadDraft(next);
          }}
          onSearchSources={searchSources}
          onCreate={createArticle}
          isCreating={createArticleMutation.isPending}
        />
      </aside>
    </div>
  );
}

function DmContentSystemsLane({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [sourceDrafts, setSourceDrafts] = useState<Record<string, { isEnabled: boolean; defaultVisibility: string }>>({});
  const [acknowledgeProprietary, setAcknowledgeProprietary] = useState(false);
  const [overrideDraft, setOverrideDraft] = useState({ entryKey: "", visibilityOverride: "", enablementOverride: "" });
  const [customCreateDraft, setCustomCreateDraft] = useState<DmContentSystemsCustomDraftState>(() => buildInitialSystemsCustomDraft());
  const [customEditDrafts, setCustomEditDrafts] = useState<Record<string, DmContentSystemsCustomDraftState>>({});
  const [customQuery, setCustomQuery] = useState("");
  const [systemsMessage, setSystemsMessage] = useState<string | null>(null);
  const [systemsError, setSystemsError] = useState<string | null>(null);

  const systemsQuery = useQuery({
    queryKey: ["dm-content-systems", campaignSlug],
    queryFn: () => apiClient.getDmContentSystems(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(systemsQuery.error)) {
      setAuthRequired(true);
    }
  }, [setAuthRequired, systemsQuery.error]);

  useEffect(() => {
    const payload = systemsQuery.data;
    if (!payload) {
      return;
    }
    setSourceDrafts((current) => {
      const next: Record<string, { isEnabled: boolean; defaultVisibility: string }> = {};
      for (const source of payload.source_rows) {
        next[source.source_id] = current[source.source_id] ?? {
          isEnabled: source.is_enabled,
          defaultVisibility: source.default_visibility,
        };
      }
      return next;
    });
    setCustomEditDrafts((current) => {
      const next: Record<string, DmContentSystemsCustomDraftState> = {};
      for (const source of payload.custom_entry_source_rows) {
        for (const entry of source.entries) {
          next[entry.slug] = current[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
        }
      }
      return next;
    });
    setCustomCreateDraft((current) => {
      if (current.title || current.bodyMarkdown || current.provenance || current.searchMetadata) {
        return current;
      }
      return {
        ...current,
        entryType: payload.custom_entry_type_choices.some((choice) => choice.value === current.entryType)
          ? current.entryType
          : payload.custom_entry_type_choices[0]?.value ?? current.entryType,
        visibility: current.visibility || payload.custom_entry_default_visibility,
      };
    });
  }, [systemsQuery.data]);

  const updateSourcesMutation = useMutation({
    mutationFn: () => {
      const payload = systemsQuery.data;
      if (!payload) {
        throw new Error("Systems payload is not loaded.");
      }
      return apiClient.updateSystemsSources(campaignSlug, {
        acknowledge_proprietary: acknowledgeProprietary,
        updates: payload.source_rows.map((source) => {
          const draft = sourceDrafts[source.source_id] ?? {
            isEnabled: source.is_enabled,
            defaultVisibility: source.default_visibility,
          };
          return {
            source_id: source.source_id,
            is_enabled: draft.isEnabled,
            default_visibility: draft.defaultVisibility,
          };
        }),
      });
    },
    onSuccess: () => {
      setSystemsMessage("Systems source policy saved.");
      setSystemsError(null);
      setAcknowledgeProprietary(false);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const updateOverrideMutation = useMutation({
    mutationFn: () => {
      const entryKey = overrideDraft.entryKey.trim();
      if (!entryKey) {
        throw new Error("Entry key is required.");
      }
      const enablement = overrideDraft.enablementOverride === "enabled"
        ? true
        : overrideDraft.enablementOverride === "disabled"
          ? false
          : null;
      return apiClient.updateSystemsEntryOverride(campaignSlug, entryKey, {
        visibility_override: overrideDraft.visibilityOverride || null,
        is_enabled_override: enablement,
      });
    },
    onSuccess: () => {
      setSystemsMessage("Systems entry override saved.");
      setSystemsError(null);
      setOverrideDraft({ entryKey: "", visibilityOverride: "", enablementOverride: "" });
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const createCustomMutation = useMutation({
    mutationFn: () => apiClient.createSystemsCustomEntry(campaignSlug, buildCustomSystemsPayload(customCreateDraft)),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry created: ${response.entry.title}.`);
      setSystemsError(null);
      setCustomCreateDraft(buildInitialSystemsCustomDraft(response.systems));
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const updateCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => {
      const draft = customEditDrafts[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
      return apiClient.updateSystemsCustomEntry(campaignSlug, entry.slug, buildCustomSystemsPayload(draft));
    },
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry updated: ${response.entry.title}.`);
      setSystemsError(null);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const archiveCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => apiClient.archiveSystemsCustomEntry(campaignSlug, entry.slug),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry archived: ${response.entry.title}.`);
      setSystemsError(null);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const restoreCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => apiClient.restoreSystemsCustomEntry(campaignSlug, entry.slug),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry restored: ${response.entry.title}.`);
      setSystemsError(null);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const payload = systemsQuery.data;
  const pageError = getApiErrorMessage(systemsQuery.error);
  const canManageSystems = Boolean(payload?.permissions.can_manage_systems);
  const allCustomEntries = useMemo(() => {
    const entries = (payload?.custom_entry_source_rows ?? []).flatMap((source) => source.entries);
    const query = customQuery.trim().toLowerCase();
    if (!query) {
      return entries;
    }
    return entries.filter((entry) => (
      [
        entry.title,
        entry.entry_key,
        entry.entry_type_label,
        entry.source_id,
        entry.visibility_label,
        entry.status_label,
        entry.provenance,
        entry.search_metadata,
        entry.body_markdown,
      ].join(" ").toLowerCase().includes(query)
    ));
  }, [customQuery, payload?.custom_entry_source_rows]);

  const renderCustomFields = ({
    idPrefix,
    draft,
    setDraft,
    includeSlug,
    disabled,
  }: {
    idPrefix: string;
    draft: DmContentSystemsCustomDraftState;
    setDraft: (next: DmContentSystemsCustomDraftState) => void;
    includeSlug: boolean;
    disabled: boolean;
  }) => {
    const updateDraft = (updates: Partial<DmContentSystemsCustomDraftState>) => setDraft({ ...draft, ...updates });
    return (
      <>
        <div className="builder-field-grid">
          <label htmlFor={`${idPrefix}-title`} className="field">
            <span>Title</span>
            <input
              id={`${idPrefix}-title`}
              value={draft.title}
              disabled={disabled}
              maxLength={200}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
            />
          </label>
          {includeSlug ? (
            <label htmlFor={`${idPrefix}-slug`} className="field">
              <span>URL slug</span>
              <input
                id={`${idPrefix}-slug`}
                value={draft.slugLeaf}
                disabled={disabled}
                maxLength={120}
                placeholder="harbor-spark"
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
              />
            </label>
          ) : null}
          <label htmlFor={`${idPrefix}-type`} className="field">
            <span>Entry type</span>
            <select
              id={`${idPrefix}-type`}
              value={draft.entryType}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft({ entryType: event.currentTarget.value })}
            >
              {(payload?.custom_entry_type_choices ?? [{ value: "rule", label: "Rule" }]).map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
          <label htmlFor={`${idPrefix}-visibility`} className="field">
            <span>Visibility</span>
            <select
              id={`${idPrefix}-visibility`}
              value={draft.visibility}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft({ visibility: event.currentTarget.value })}
            >
              {(payload?.custom_entry_visibility_choices ?? []).map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
        </div>
        <label htmlFor={`${idPrefix}-provenance`} className="field">
          <span>Source/provenance</span>
          <input
            id={`${idPrefix}-provenance`}
            value={draft.provenance}
            disabled={disabled}
            maxLength={500}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ provenance: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-search`} className="field">
          <span>Searchable metadata</span>
          <textarea
            id={`${idPrefix}-search`}
            rows={3}
            value={draft.searchMetadata}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ searchMetadata: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-body`} className="field">
          <span>Rendered body</span>
          <textarea
            id={`${idPrefix}-body`}
            rows={10}
            value={draft.bodyMarkdown}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
          />
        </label>
      </>
    );
  };

  if (systemsQuery.isLoading) {
    return <p className="status status-neutral">Loading Systems management ...</p>;
  }

  if (pageError) {
    return (
      <ApiErrorNotice
        isLoading={systemsQuery.isLoading}
        message={pageError}
        onAuth={() => setAuthRequired(true)}
      />
    );
  }

  if (!payload) {
    return <p className="status status-error">Systems management could not be loaded.</p>;
  }

  return (
    <div className="dm-content-systems-lane">
      {systemsError ? <p className="status status-error">{systemsError}</p> : null}
      {systemsMessage ? <p className="status status-neutral">{systemsMessage}</p> : null}

      <section className="card" id="systems-source-enablement">
        <div className="section-heading">
          <div>
            <h2>Source Enablement</h2>
            <p className="meta">Systems Policy</p>
            <p className="meta">Library: {payload.systems_library || "Not configured"}</p>
            <p className="meta">Systems scope visibility: {payload.systems_scope_visibility_label}</p>
          </div>
        </div>
        {payload.has_proprietary_sources ? (
          <p className="meta">
            Proprietary-source acknowledgement: {payload.policy.proprietary_acknowledged ? "recorded" : "not yet recorded in the systems policy"}
          </p>
        ) : null}
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            updateSourcesMutation.mutate();
          }}
        >
          {payload.source_rows.map((source: SystemsSourceRow) => {
            const draft = sourceDrafts[source.source_id] ?? {
              isEnabled: source.is_enabled,
              defaultVisibility: source.default_visibility,
            };
            return (
              <div className="field" key={source.source_id}>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={draft.isEnabled}
                    disabled={!canManageSystems}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const checked = event.currentTarget.checked;
                      setSourceDrafts((current) => ({
                        ...current,
                        [source.source_id]: {
                          ...(current[source.source_id] ?? draft),
                          isEnabled: checked,
                        },
                      }));
                    }}
                  />
                  {source.title} ({source.source_id})
                </label>
                <p className="meta">{source.license_class_label}</p>
                <p className="meta">{source.entry_count} imported entr{source.entry_count === 1 ? "y" : "ies"}</p>
                <label htmlFor={`systems-source-${source.source_id}-visibility`} className="field">
                  <span>Default visibility</span>
                  <select
                    id={`systems-source-${source.source_id}-visibility`}
                    value={draft.defaultVisibility}
                    disabled={!canManageSystems}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                      const visibility = event.currentTarget.value;
                      setSourceDrafts((current) => ({
                        ...current,
                        [source.source_id]: {
                          ...(current[source.source_id] ?? draft),
                          defaultVisibility: visibility,
                        },
                      }));
                    }}
                  >
                    {(source.choices ?? []).map((choice) => (
                      <option key={choice.value} value={choice.value} disabled={choice.disabled}>
                        {choice.label}{choice.disabled ? " (not allowed)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {!source.public_visibility_allowed ? (
                  <p className="meta">This source is restricted from public visibility by policy.</p>
                ) : null}
              </div>
            );
          })}
          {payload.has_proprietary_sources && !payload.policy.proprietary_acknowledged ? (
            <label className="field">
              <span>Proprietary-source acknowledgement</span>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={acknowledgeProprietary}
                  disabled={!canManageSystems}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setAcknowledgeProprietary(event.currentTarget.checked)}
                />
                I understand proprietary systems sources are for private campaign use only and must not be made public or redistributed.
              </label>
            </label>
          ) : null}
          <button type="submit" disabled={!canManageSystems || updateSourcesMutation.isPending}>
            {updateSourcesMutation.isPending ? "Saving..." : "Save systems sources"}
          </button>
        </form>
      </section>

      <section className="card" id="systems-shared-core-permission">
        <div className="section-heading">
          <div>
            <h2>Shared/Core Editing</h2>
            <p className="meta">
              Campaign DM editing is {payload.policy.allow_dm_shared_core_entry_edits ? "enabled" : "disabled"} for shared-library Systems entries.
            </p>
          </div>
        </div>
        <p className="meta">
          When enabled by an app admin, DMs for this campaign can use the same shared/core editor as app admins.
          This changes the shared library row itself, not only this campaign's override.
        </p>
        {payload.permissions.can_manage_shared_core_entry_edit_permission ? (
          <a className="ghost-button" href={`${payload.links.flask_systems_control_url}#systems-shared-core-permission`}>
            Open shared/core permission form
          </a>
        ) : (
          <p className="meta">Only app admins can change whether campaign DMs may edit shared/core Systems entries.</p>
        )}
      </section>

      <section className="card" id="systems-entry-overrides">
        <div className="section-heading">
          <h2>Entry Overrides</h2>
          <p className="meta">{payload.entry_override_count} saved override{payload.entry_override_count === 1 ? "" : "s"}</p>
        </div>
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            updateOverrideMutation.mutate();
          }}
        >
          <label htmlFor="systems-entry-override-key" className="field">
            <span>Entry key</span>
            <input
              id="systems-entry-override-key"
              value={overrideDraft.entryKey}
              placeholder="dnd-5e|spell|phb|fireball"
              disabled={!canManageSystems}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setOverrideDraft({ ...overrideDraft, entryKey: event.currentTarget.value })}
            />
          </label>
          <label htmlFor="systems-entry-override-visibility" className="field">
            <span>Visibility override</span>
            <select
              id="systems-entry-override-visibility"
              value={overrideDraft.visibilityOverride}
              disabled={!canManageSystems}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => setOverrideDraft({ ...overrideDraft, visibilityOverride: event.currentTarget.value })}
            >
              <option value="">Inherit source default</option>
              {payload.custom_entry_visibility_choices.map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
          <label htmlFor="systems-entry-override-enabled" className="field">
            <span>Enablement override</span>
            <select
              id="systems-entry-override-enabled"
              value={overrideDraft.enablementOverride}
              disabled={!canManageSystems}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => setOverrideDraft({ ...overrideDraft, enablementOverride: event.currentTarget.value })}
            >
              <option value="">Inherit source enablement</option>
              <option value="enabled">Enabled</option>
              <option value="disabled">Disabled</option>
            </select>
          </label>
          <button type="submit" disabled={!canManageSystems || updateOverrideMutation.isPending}>
            {updateOverrideMutation.isPending ? "Saving..." : "Save entry override"}
          </button>
        </form>
        {payload.entry_override_rows.length ? (
          <div className="dm-content-list systems-override-list">
            {payload.entry_override_rows.map((override) => (
              <article className="dm-content-item" key={override.entry_key}>
                <div className="dm-content-item__header">
                  <div>
                    <h3>{override.entry_href ? <a href={override.entry_href}>{override.entry_title}</a> : override.entry_title}</h3>
                    <p className="meta">{override.entry_key}</p>
                    {override.source_label ? (
                      <p className="meta">{override.source_label}{override.entry_type_label ? ` | ${override.entry_type_label}` : ""}</p>
                    ) : null}
                  </div>
                  <div className="badge-list">
                    <span className="meta-badge">{override.visibility_label}</span>
                    <span className="meta-badge">{override.enablement_label}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="status status-neutral">No campaign-specific Systems entry overrides have been saved yet.</p>
        )}
      </section>

      <section className="card" id="systems-custom-entries">
        <div className="section-heading">
          <h2>Custom Entries</h2>
          <p className="meta">{payload.custom_entry_count} custom campaign entr{payload.custom_entry_count === 1 ? "y" : "ies"}</p>
        </div>
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            createCustomMutation.mutate();
          }}
        >
          {renderCustomFields({
            idPrefix: "systems-custom-create",
            draft: customCreateDraft,
            setDraft: setCustomCreateDraft,
            includeSlug: true,
            disabled: !canManageSystems,
          })}
          <button type="submit" disabled={!canManageSystems || createCustomMutation.isPending}>
            {createCustomMutation.isPending ? "Saving..." : "Create custom entry"}
          </button>
        </form>

        <form className="search-form" onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}>
          <label htmlFor="systems-custom-search">Search custom entries</label>
          <input
            id="systems-custom-search"
            type="search"
            value={customQuery}
            placeholder="Title, type, status, source, body"
            onChange={(event: ChangeEvent<HTMLInputElement>) => setCustomQuery(event.currentTarget.value)}
          />
        </form>

        {allCustomEntries.length ? (
          <div className="dm-content-list systems-custom-list">
            {allCustomEntries.map((entry) => {
              const draft = customEditDrafts[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
              return (
                <article className="dm-content-item" key={entry.entry_key}>
                  <div className="dm-content-item__header">
                    <div>
                      <h3>{entry.title}</h3>
                      <p className="meta">{entry.source_id} | {entry.visibility_label} | {entry.status_label}</p>
                    </div>
                    <div className="badge-list">
                      <span className="meta-badge">{entry.entry_type_label}</span>
                    </div>
                  </div>
                  <div className="dm-content-item__actions">
                    {entry.href ? (
                      <a className="ghost-button" href={entry.href}>
                        Open entry
                      </a>
                    ) : null}
                    {entry.is_archived ? (
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!canManageSystems || restoreCustomMutation.isPending}
                        onClick={() => restoreCustomMutation.mutate(entry)}
                      >
                        {restoreCustomMutation.isPending ? "Restoring..." : "Restore"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!canManageSystems || archiveCustomMutation.isPending}
                        onClick={() => archiveCustomMutation.mutate(entry)}
                      >
                        {archiveCustomMutation.isPending ? "Archiving..." : "Archive"}
                      </button>
                    )}
                  </div>
                  <details className="feature-detail">
                    <summary>Review or edit custom entry</summary>
                    {entry.provenance ? <p className="meta">Source/provenance: {entry.provenance}</p> : null}
                    {entry.search_metadata ? <p className="meta">Search metadata: {entry.search_metadata}</p> : null}
                    {entry.body_markdown ? <pre className="dm-content-preview dm-content-preview--compact">{entry.body_markdown}</pre> : null}
                    <form
                      className="stack-form"
                      onSubmit={(event: FormEvent<HTMLFormElement>) => {
                        event.preventDefault();
                        updateCustomMutation.mutate(entry);
                      }}
                    >
                      {renderCustomFields({
                        idPrefix: `systems-custom-edit-${entry.id}`,
                        draft,
                        setDraft: (next) => setCustomEditDrafts((current) => ({ ...current, [entry.slug]: next })),
                        includeSlug: false,
                        disabled: !canManageSystems,
                      })}
                      <div className="badge-list">
                        <button type="submit" disabled={!canManageSystems || updateCustomMutation.isPending}>
                          {updateCustomMutation.isPending ? "Saving..." : "Update custom entry"}
                        </button>
                      </div>
                    </form>
                  </details>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="status status-neutral">
            {customQuery ? "No custom Systems entries matched that search." : "No custom campaign Systems entries have been authored yet."}
          </p>
        )}
      </section>

      <section className="card" id="systems-shared-imports">
        <div className="section-heading">
          <h2>Shared Source Imports</h2>
          <p className="meta">DND-5E ZIP import remains on the permission-gated Flask form for this slice.</p>
        </div>
        {payload.permissions.can_import_shared_systems && payload.supports_dnd5e_import ? (
          <a className="ghost-button" href={`${payload.links.flask_systems_lane_url}#systems-shared-imports`}>
            Open admin import form
          </a>
        ) : (
          <p className="status status-neutral">
            Shared-source ZIP imports are limited to app admins. Campaign DMs can review import runs and manage campaign policy here.
          </p>
        )}
      </section>

      <section className="card" id="systems-import-history">
        <div className="section-heading">
          <h2>Import-Run History</h2>
          <p className="meta">{payload.import_run_count} recent shared-library run{payload.import_run_count === 1 ? "" : "s"}</p>
        </div>
        {payload.import_run_rows.length ? (
          <div className="dm-content-list systems-import-history">
            {payload.import_run_rows.map((run) => (
              <article className="dm-content-item" key={run.id}>
                <div className="dm-content-item__header">
                  <div>
                    <h3>{run.source_id} import #{run.id}</h3>
                    <p className="meta">Started {formatTimestamp(run.started_at)}{run.completed_at ? ` | Completed ${formatTimestamp(run.completed_at)}` : ""}</p>
                    {run.import_version ? <p className="meta">Import version: {run.import_version}</p> : null}
                    {run.type_summary.length ? (
                      <p className="meta">{run.type_summary.map((item) => `${item.entry_type_label}: ${item.count}`).join(", ")}</p>
                    ) : null}
                    {run.error ? <p className="meta">Error: {run.error}</p> : null}
                  </div>
                  <div className="badge-list">
                    <span className="meta-badge">{run.status}</span>
                    {run.imported_count !== null ? <span className="meta-badge">{run.imported_count} entries</span> : null}
                    {run.source_file_count !== null ? <span className="meta-badge">{run.source_file_count} files</span> : null}
                  </div>
                </div>
                {run.source_files.length ? (
                  <details className="feature-detail">
                    <summary>Review imported files and entry counts</summary>
                    <ul className="plain-list">
                      {run.source_files.map((sourceFile) => <li className="meta" key={sourceFile}>{sourceFile}</li>)}
                    </ul>
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="status status-neutral">No Systems import runs have been recorded yet.</p>
        )}
      </section>
    </div>
  );
}

function DmContentPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/dm-content",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const encodedCampaignSlug = encodeURIComponent(resolvedCampaignSlug);
  const location = useLocation();
  const requestedLane = new URLSearchParams(location.search).get("lane");
  const activeLane: DmContentLane = requestedLane === "staged-articles"
    ? "staged-articles"
    : requestedLane === "conditions"
      ? "conditions"
      : requestedLane === "player-wiki"
        ? "player-wiki"
        : requestedLane === "systems"
          ? "systems"
          : "statblocks";
  const { apiClient, setAuthRequired } = useApiClient();
  const [statblockCreateDraft, setStatblockCreateDraft] = useState<DmContentStatblockDraftState>({
    filename: "gen2-statblock.md",
    subsection: "",
    markdown: "",
  });
  const [statblockQuery, setStatblockQuery] = useState("");
  const [statblockDrafts, setStatblockDrafts] = useState<Record<number, DmContentStatblockDraftState>>({});
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState<ManualArticleDraftState>(buildEmptyManualArticleDraft);
  const [uploadDraft, setUploadDraft] = useState({
    filename: "",
    markdown: "",
    image: null as EmbeddedImageInput | null,
  });
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceResults, setSourceResults] = useState<SessionArticleSourceResult[]>([]);
  const [sourceStatus, setSourceStatus] = useState<string | null>(null);
  const [selectedSourceRef, setSelectedSourceRef] = useState("");
  const [stagedDrafts, setStagedDrafts] = useState<Record<number, StagedArticleDraftState>>({});
  const [conditionCreateDraft, setConditionCreateDraft] = useState<DmContentConditionDraftState>({
    name: "",
    description: "",
  });
  const [conditionQuery, setConditionQuery] = useState("");
  const [conditionDrafts, setConditionDrafts] = useState<Record<number, DmContentConditionDraftState>>({});
  const [playerWikiCreateDraft, setPlayerWikiCreateDraft] = useState<DmPlayerWikiDraftState>(() => buildInitialPlayerWikiDraft());
  const [playerWikiQuery, setPlayerWikiQuery] = useState("");
  const [playerWikiEditDrafts, setPlayerWikiEditDrafts] = useState<Record<string, DmPlayerWikiDraftState>>({});
  const [playerWikiDeleteConfirm, setPlayerWikiDeleteConfirm] = useState<Record<string, boolean>>({});
  const [uiMessage, setUiMessage] = useState<string | null>(null);
  const [paneError, setPaneError] = useState<string | null>(null);

  const dmContentQuery = useQuery({
    queryKey: ["dm-content", resolvedCampaignSlug],
    queryFn: () => apiClient.getDmContent(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  const sessionQuery = useQuery({
    queryKey: ["dm-content-staged-articles", resolvedCampaignSlug],
    queryFn: async () => {
      const response = await apiClient.getSessionLiveState(resolvedCampaignSlug);
      const resolved = resolveSessionLivePayload(undefined, response);
      if (resolved.state === "full" || resolved.state === "reuse") {
        return resolved.payload;
      }
      throw new Error("Unable to load staged articles.");
    },
    enabled: Boolean(resolvedCampaignSlug) && activeLane === "staged-articles",
    retry: false,
  });

  const contentPagesQuery = useQuery({
    queryKey: ["dm-content-player-wiki-pages", resolvedCampaignSlug],
    queryFn: () => apiClient.getContentPages(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug) && activeLane === "player-wiki",
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(dmContentQuery.error) || isAuthError(sessionQuery.error) || isAuthError(contentPagesQuery.error)) {
      setAuthRequired(true);
    }
  }, [contentPagesQuery.error, dmContentQuery.error, sessionQuery.error, setAuthRequired]);

  const statblocks: DmContentStatblock[] = dmContentQuery.data?.statblocks ?? [];
  const conditions: DmContentConditionDefinition[] = dmContentQuery.data?.conditions ?? [];
  const canManageDmContent = dmContentQuery.data?.permissions.can_manage_dm_content ?? false;

  const stagedArticles: SessionArticle[] = sessionQuery.data?.staged_articles ?? [];
  const canManageSession = sessionQuery.data?.permissions.can_manage_session ?? false;
  const playerWikiPages: ContentPageFileSummary[] = contentPagesQuery.data?.pages ?? [];
  const canManagePlayerWiki = Boolean(contentPagesQuery.data?.ok);

  useEffect(() => {
    setStatblockDrafts((current) => {
      const next: Record<number, DmContentStatblockDraftState> = {};
      for (const statblock of statblocks) {
        next[statblock.id] = current[statblock.id] ?? buildInitialStatblockDraft(statblock);
      }
      return next;
    });
  }, [statblocks]);

  useEffect(() => {
    setConditionDrafts((current) => {
      const next: Record<number, DmContentConditionDraftState> = {};
      for (const condition of conditions) {
        next[condition.id] = current[condition.id] ?? buildInitialConditionDraft(condition);
      }
      return next;
    });
  }, [conditions]);

  useEffect(() => {
    setStagedDrafts((current) => {
      const next: Record<number, StagedArticleDraftState> = {};
      for (const article of stagedArticles) {
        const existing = current[article.id];
        next[article.id] = existing ?? {
          title: article.title,
          body: article.body_markdown,
          imageAltText: article.image?.alt_text || "",
          imageCaption: article.image?.caption || "",
          image: null,
        };
      }
      return next;
    });
  }, [stagedArticles]);

  const filteredStatblocks = useMemo(() => {
    const query = statblockQuery.trim().toLowerCase();
    if (!query) {
      return statblocks;
    }
    return statblocks.filter((statblock) => (
      statblock.title.toLowerCase().includes(query)
      || statblock.subsection.toLowerCase().includes(query)
      || statblock.source_filename.toLowerCase().includes(query)
      || statblock.body_markdown.toLowerCase().includes(query)
    ));
  }, [statblocks, statblockQuery]);

  const topLevelStatblocks = filteredStatblocks.filter((statblock) => !statblock.subsection);
  const statblockSubsectionGroups = useMemo(() => {
    const groups = new Map<string, DmContentStatblock[]>();
    for (const statblock of filteredStatblocks) {
      if (!statblock.subsection) {
        continue;
      }
      const current = groups.get(statblock.subsection) ?? [];
      current.push(statblock);
      groups.set(statblock.subsection, current);
    }
    return Array.from(groups.entries()).map(([name, groupedStatblocks]) => ({
      name,
      statblocks: groupedStatblocks,
    }));
  }, [filteredStatblocks]);

  const filteredConditions = useMemo(() => {
    const query = conditionQuery.trim().toLowerCase();
    if (!query) {
      return conditions;
    }
    return conditions.filter(
      (condition) =>
        condition.name.toLowerCase().includes(query)
        || condition.description_markdown.toLowerCase().includes(query),
    );
  }, [conditions, conditionQuery]);

  const filteredPlayerWikiPages = useMemo(() => {
    const query = playerWikiQuery.trim().toLowerCase();
    if (!query) {
      return playerWikiPages;
    }
    return playerWikiPages.filter((pageFile) => {
      const searchText = [
        pageFile.page_ref,
        pageFile.page.title,
        pageFile.page.section,
        pageFile.page.subsection,
        pageFile.page.page_type,
        pageFile.page.summary,
        pageFile.page.source_ref,
        pageFile.page.image_path,
      ].join(" ").toLowerCase();
      return searchText.includes(query);
    });
  }, [playerWikiPages, playerWikiQuery]);

  const createStatblockMutation = useMutation({
    mutationFn: (payload: DmContentStatblockCreatePayload) => apiClient.createDmContentStatblock(resolvedCampaignSlug, payload),
    onSuccess: (response) => {
      setUiMessage(`Statblock saved: ${response.statblock.title}. ${response.statblock.parser_feedback.summary}`);
      setPaneError(null);
      setStatblockCreateDraft({ filename: "gen2-statblock.md", subsection: "", markdown: "" });
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateStatblockMutation = useMutation({
    mutationFn: (args: { id: number; payload: DmContentStatblockUpdatePayload }) =>
      apiClient.updateDmContentStatblock(resolvedCampaignSlug, args.id, args.payload),
    onSuccess: (response) => {
      setUiMessage(`Statblock updated: ${response.statblock.title}. ${response.statblock.parser_feedback.summary}`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteStatblockMutation = useMutation({
    mutationFn: (statblockId: number) => apiClient.deleteDmContentStatblock(resolvedCampaignSlug, statblockId),
    onSuccess: (response) => {
      setUiMessage(`Statblock deleted: ${response.statblock.title}.`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const createConditionMutation = useMutation({
    mutationFn: (payload: DmContentConditionCreatePayload) => apiClient.createDmContentCondition(resolvedCampaignSlug, payload),
    onSuccess: (response) => {
      setUiMessage(`Condition saved: ${response.condition.name}.`);
      setPaneError(null);
      setConditionCreateDraft({ name: "", description: "" });
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateConditionMutation = useMutation({
    mutationFn: (args: { id: number; payload: DmContentConditionUpdatePayload }) =>
      apiClient.updateDmContentCondition(resolvedCampaignSlug, args.id, args.payload),
    onSuccess: (response) => {
      setUiMessage(`Condition updated: ${response.condition.name}.`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteConditionMutation = useMutation({
    mutationFn: (conditionId: number) => apiClient.deleteDmContentCondition(resolvedCampaignSlug, conditionId),
    onSuccess: (response) => {
      setUiMessage(`Condition deleted: ${response.condition.name}.`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const savePlayerWikiPageMutation = useMutation({
    mutationFn: async (args: { mode: "create" | "edit"; pageRef: string; draft: DmPlayerWikiDraftState }) => {
      let imageRef = args.draft.image.trim();
      if (args.draft.imageUpload) {
        imageRef = buildPlayerWikiAssetRef(args.pageRef, args.draft.imageUpload);
        await apiClient.upsertContentAsset(resolvedCampaignSlug, imageRef, {
          asset_file: {
            filename: args.draft.imageUpload.filename,
            data_base64: args.draft.imageUpload.data_base64,
            media_type: args.draft.imageUpload.media_type,
          },
        });
      }
      const payload: ContentPageUpsertPayload = {
        metadata: buildPlayerWikiMetadata(args.draft, args.pageRef, imageRef),
        body_markdown: args.draft.bodyMarkdown,
      };
      return apiClient.upsertContentPage(resolvedCampaignSlug, args.pageRef, payload);
    },
    onSuccess: (response, args) => {
      const title = response.page_file.page.title || args.pageRef;
      setUiMessage(args.mode === "create" ? `Player Wiki page created: ${title}.` : `Player Wiki page updated: ${title}.`);
      setPaneError(null);
      if (args.mode === "create") {
        setPlayerWikiCreateDraft(buildInitialPlayerWikiDraft());
      }
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      void contentPagesQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const archivePlayerWikiPageMutation = useMutation({
    mutationFn: async (pageRef: string) => {
      const detail = await apiClient.getContentPage(resolvedCampaignSlug, pageRef);
      const draft = {
        ...buildPlayerWikiDraftFromRecord(detail.page_file),
        published: false,
        imageUpload: null,
      };
      const payload: ContentPageUpsertPayload = {
        metadata: buildPlayerWikiMetadata(draft, detail.page_file.page_ref, draft.image),
        body_markdown: draft.bodyMarkdown,
      };
      return apiClient.upsertContentPage(resolvedCampaignSlug, detail.page_file.page_ref, payload);
    },
    onSuccess: (response) => {
      setUiMessage(`Player Wiki page archived: ${response.page_file.page.title}.`);
      setPaneError(null);
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      void contentPagesQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deletePlayerWikiPageMutation = useMutation({
    mutationFn: (pageRef: string) => apiClient.deleteContentPage(resolvedCampaignSlug, pageRef),
    onSuccess: (response) => {
      const pageRef = response.deleted.page_ref;
      setUiMessage(`Player Wiki page deleted: ${pageRef}.`);
      setPaneError(null);
      setPlayerWikiDeleteConfirm((current) => ({
        ...current,
        [pageRef]: false,
      }));
      setPlayerWikiEditDrafts((current) => {
        const next = { ...current };
        delete next[pageRef];
        return next;
      });
      void contentPagesQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const loadPlayerWikiEditDraft = async (pageRef: string) => {
    setPaneError(null);
    setUiMessage("Loading Player Wiki editor...");
    try {
      const response = await apiClient.getContentPage(resolvedCampaignSlug, pageRef);
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      setUiMessage(`Editor loaded: ${response.page_file.page.title}.`);
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    }
  };

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(resolvedCampaignSlug, payload),
    onSuccess: () => {
      setUiMessage("Article staged.");
      setPaneError(null);
      setManualDraft(buildEmptyManualArticleDraft());
      setUploadDraft({ filename: "", markdown: "", image: null });
      setSelectedSourceRef("");
      void sessionQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateArticleMutation = useMutation({
    mutationFn: (args: { id: number; payload: StagedArticleDraftState; hasExistingImage: boolean }) => {
      const imagePayload = args.payload.image
        ? {
            ...args.payload.image,
            alt_text: args.payload.imageAltText || null,
            caption: args.payload.imageCaption || null,
          }
        : undefined;
      const articlePayload: SessionArticleUpdatePayload = {
        title: args.payload.title,
        body_markdown: args.payload.body,
      };
      if (imagePayload) {
        articlePayload.image = imagePayload;
      } else if (args.hasExistingImage) {
        articlePayload.image_alt_text = args.payload.imageAltText || "";
        articlePayload.image_caption = args.payload.imageCaption || "";
      }
      return apiClient.updateSessionArticle(resolvedCampaignSlug, args.id, articlePayload);
    },
    onSuccess: (_response, args) => {
      setUiMessage("Article updated.");
      setPaneError(null);
      setStagedDrafts((current) => ({
        ...current,
        [args.id]: {
          ...current[args.id],
          image: null,
        },
      }));
      void sessionQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(resolvedCampaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article removed.");
      setPaneError(null);
      void sessionQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const searchSources = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = sourceQuery.trim();
    if (!query) {
      setSourceStatus("Search with a query.");
      return;
    }
    setSourceStatus("Searching ...");
    try {
      const response = await apiClient.searchSessionArticleSources(resolvedCampaignSlug, query);
      setSourceResults(response.results);
      setSourceStatus(response.message || "Search complete.");
      if (!response.results.length) {
        setSelectedSourceRef("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSourceResults([]);
      setSourceStatus(null);
      setPaneError(apiErrorMessage(error));
    }
  };

  const clearArticleStatus = () => {
    setPaneError(null);
    setUiMessage(null);
  };
  const pageError = activeLane === "staged-articles"
    ? getApiErrorMessage(sessionQuery.error)
    : activeLane === "player-wiki"
      ? getApiErrorMessage(contentPagesQuery.error)
      : activeLane === "systems"
        ? null
      : getApiErrorMessage(dmContentQuery.error);
  const dmContentSystemsQuery = useQuery({
    queryKey: ["dm-content-systems", resolvedCampaignSlug],
    queryFn: () => apiClient.getDmContentSystems(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug) && activeLane === "systems",
    retry: false,
  });
  const dmContentLede = activeLane === "staged-articles"
    ? "Session reveal article prep."
    : activeLane === "systems"
      ? "Systems policy, custom entries, imports, and history."
      : activeLane === "conditions"
        ? "Custom combat conditions."
        : activeLane === "player-wiki"
          ? "Published player wiki page management."
          : "DM-side statblocks for Combat NPC seeding.";
  const dmContentLaneCounts = {
    statblocks: dmContentQuery.data?.subpage_counts?.statblocks ?? (dmContentQuery.data?.statblocks.length ?? 0),
    conditions: dmContentQuery.data?.subpage_counts?.conditions ?? (dmContentQuery.data?.conditions.length ?? 0),
    stagedArticles: dmContentQuery.data?.subpage_counts?.staged_articles ?? stagedArticles.length,
    playerWiki: dmContentQuery.data?.subpage_counts?.player_wiki ?? playerWikiPages.length,
    systems: dmContentQuery.data?.subpage_counts?.systems ?? (dmContentSystemsQuery.data?.source_count ?? 0),
  };
  const pageIsLoading = activeLane === "staged-articles"
    ? sessionQuery.isLoading
    : activeLane === "player-wiki"
      ? contentPagesQuery.isLoading
      : activeLane === "systems"
        ? false
      : dmContentQuery.isLoading;

  const renderPlayerWikiDraftFields = ({
    idPrefix,
    draft,
    setDraft,
    includeSlug,
    disabled,
  }: {
    idPrefix: string;
    draft: DmPlayerWikiDraftState;
    setDraft: (next: DmPlayerWikiDraftState) => void;
    includeSlug: boolean;
    disabled: boolean;
  }) => {
    const updateDraft = (updates: Partial<DmPlayerWikiDraftState>) => setDraft({ ...draft, ...updates });
    const targetPageRef = buildPageRefFromDraft(draft);
    return (
      <>
        <label htmlFor={`${idPrefix}-title`} className="field">
          <span>Title</span>
          <input
            id={`${idPrefix}-title`}
            name="title"
            maxLength={200}
            value={draft.title}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
          />
        </label>
        {includeSlug ? (
          <>
            <label htmlFor={`${idPrefix}-slug`} className="field">
              <span>Slug</span>
              <input
                id={`${idPrefix}-slug`}
                name="slug_leaf"
                maxLength={120}
                value={draft.slugLeaf}
                placeholder="field-report"
                disabled={disabled}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
              />
            </label>
            <p className="meta">Page file: {targetPageRef}.md</p>
          </>
        ) : null}
        <label htmlFor={`${idPrefix}-section`} className="field">
          <span>Section</span>
          <select
            id={`${idPrefix}-section`}
            name="section"
            value={draft.section}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLSelectElement>) => {
              const section = event.currentTarget.value;
              const currentDefaultType = sectionChoiceForLabel(draft.section).defaultType;
              const nextDefaultType = sectionChoiceForLabel(section).defaultType;
              updateDraft({
                section,
                pageType: draft.pageType && draft.pageType !== currentDefaultType ? draft.pageType : nextDefaultType,
              });
            }}
          >
            {PLAYER_WIKI_SECTION_CHOICES.map((choice) => (
              <option key={choice.label} value={choice.label}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor={`${idPrefix}-type`} className="field">
          <span>Page type</span>
          <input
            id={`${idPrefix}-type`}
            name="page_type"
            maxLength={80}
            value={draft.pageType}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ pageType: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-subsection`} className="field">
          <span>Subsection</span>
          <input
            id={`${idPrefix}-subsection`}
            name="subsection"
            maxLength={120}
            value={draft.subsection}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ subsection: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-summary`} className="field">
          <span>Summary</span>
          <textarea
            id={`${idPrefix}-summary`}
            name="summary"
            rows={3}
            maxLength={400}
            value={draft.summary}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ summary: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-aliases`} className="field">
          <span>Aliases</span>
          <textarea
            id={`${idPrefix}-aliases`}
            name="aliases"
            rows={3}
            value={draft.aliases}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ aliases: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-reveal-after-session`} className="field">
          <span>Reveal after session</span>
          <input
            id={`${idPrefix}-reveal-after-session`}
            name="reveal_after_session"
            type="number"
            min={0}
            value={draft.revealAfterSession}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ revealAfterSession: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-display-order`} className="field">
          <span>Display order</span>
          <input
            id={`${idPrefix}-display-order`}
            name="display_order"
            type="number"
            min={0}
            value={draft.displayOrder}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ displayOrder: event.currentTarget.value })}
          />
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            name="published"
            checked={draft.published}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ published: event.currentTarget.checked })}
          />
          Published
        </label>
        <label htmlFor={`${idPrefix}-source-ref`} className="field">
          <span>Source reference</span>
          <input
            id={`${idPrefix}-source-ref`}
            name="source_ref"
            value={draft.sourceRef}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ sourceRef: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-image`} className="field">
          <span>Image path</span>
          <input
            id={`${idPrefix}-image`}
            name="image"
            value={draft.image}
            placeholder="npcs/example.webp"
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ image: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-image-upload`} className="field">
          <span>Upload image</span>
          <input
            id={`${idPrefix}-image-upload`}
            type="file"
            accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const file = event.currentTarget.files?.item(0);
              if (!file) {
                updateDraft({ imageUpload: null });
                return;
              }
              readBinaryAsBase64(file, (payload) => {
                if (!payload) {
                  setPaneError("Unable to read that image file.");
                  setUiMessage(null);
                  return;
                }
                setPaneError(null);
                updateDraft({ imageUpload: payload });
              });
            }}
          />
        </label>
        {draft.imageUpload ? <p className="status status-neutral">Selected image: {draft.imageUpload.filename}</p> : null}
        <label htmlFor={`${idPrefix}-image-alt`} className="field">
          <span>Image alt text</span>
          <input
            id={`${idPrefix}-image-alt`}
            name="image_alt"
            value={draft.imageAlt}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageAlt: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-image-caption`} className="field">
          <span>Image caption</span>
          <input
            id={`${idPrefix}-image-caption`}
            name="image_caption"
            value={draft.imageCaption}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageCaption: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-body`} className="field">
          <span>Markdown body</span>
          <textarea
            id={`${idPrefix}-body`}
            name="body_markdown"
            rows={18}
            value={draft.bodyMarkdown}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
          />
        </label>
      </>
    );
  };

  const renderStatblockCard = (statblock: DmContentStatblock) => {
    const draft = statblockDrafts[statblock.id] ?? buildInitialStatblockDraft(statblock);
    return (
      <article className="dm-content-item dm-statblock-card" id={`dm-statblock-${statblock.id}`} key={statblock.id}>
        <div className="dm-content-item__header">
          <div>
            <h3>{statblock.title}</h3>
            <p className="meta">Source file: {statblock.source_filename}</p>
          </div>
          <div className="badge-list dm-statblock-badges">
            {statblock.armor_class !== null ? <span className="meta-badge">AC {statblock.armor_class}</span> : null}
            <span className="meta-badge">HP {statblock.max_hp}</span>
            <span className="meta-badge">Speed {statblock.speed_text}</span>
            <span className="meta-badge">Init {formatInitiativeBonus(statblock.initiative_bonus)}</span>
          </div>
        </div>
        <p className="status status-neutral">{statblock.parser_feedback.summary}</p>
        <p className="meta">Combat seed source: dm_statblock:{statblock.id}.</p>
        <details className="feature-detail">
          <summary>View statblock text</summary>
          <pre className="dm-content-preview">{statblock.body_markdown}</pre>
        </details>
        {canManageDmContent ? (
          <>
            <details className="feature-detail">
              <summary>Edit statblock source</summary>
              <form
                className="stack-form"
                onSubmit={(event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  updateStatblockMutation.mutate({
                    id: statblock.id,
                    payload: {
                      subsection: String(formData.get("subsection") || ""),
                      markdown_text: String(formData.get("markdown_text") || ""),
                    },
                  });
                }}
              >
                <label className="field">
                  <span>Subsection</span>
                  <input
                    id={`dm-statblock-subsection-${statblock.id}`}
                    name="subsection"
                    value={draft.subsection}
                    disabled={!canManageDmContent}
                    maxLength={80}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const subsection = event.currentTarget.value;
                      setStatblockDrafts((current) => ({
                        ...current,
                        [statblock.id]: {
                          ...(current[statblock.id] ?? draft),
                          subsection,
                        },
                      }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>Source markdown body</span>
                  <textarea
                    id={`dm-statblock-markdown-${statblock.id}`}
                    name="markdown_text"
                    rows={12}
                    value={draft.markdown}
                    disabled={!canManageDmContent}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                      const markdown = event.currentTarget.value;
                      setStatblockDrafts((current) => ({
                        ...current,
                        [statblock.id]: {
                          ...(current[statblock.id] ?? draft),
                          markdown,
                        },
                      }));
                    }}
                  />
                </label>
                <button type="submit" disabled={!canManageDmContent || updateStatblockMutation.isPending}>
                  {updateStatblockMutation.isPending ? "Saving..." : "Save statblock"}
                </button>
              </form>
            </details>
            <div className="dm-content-item__actions">
              <button
                type="button"
                className="ghost-button"
                disabled={!canManageDmContent || deleteStatblockMutation.isPending}
                onClick={() => deleteStatblockMutation.mutate(statblock.id)}
              >
                {deleteStatblockMutation.isPending ? "Deleting..." : "Delete statblock"}
              </button>
            </div>
          </>
        ) : null}
      </article>
    );
  };

  const renderConditionCard = (condition: DmContentConditionDefinition) => {
    const draft = conditionDrafts[condition.id] ?? buildInitialConditionDraft(condition);
    const hasDescription = condition.description_markdown.trim().length > 0;
    return (
      <article className="dm-content-item dm-condition-card" id={`dm-condition-${condition.id}`} key={condition.id}>
        <div className="dm-content-item__header">
          <div>
            <h3>{condition.name}</h3>
          </div>
        </div>
        {hasDescription ? (
          <pre className="dm-content-preview dm-content-preview--compact">{condition.description_markdown}</pre>
        ) : (
          <p className="meta">No description saved.</p>
        )}
        {canManageDmContent ? (
          <details className="feature-detail">
            <summary>Edit condition</summary>
              <form
                className="stack-form"
                onSubmit={(event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  const updatedName = String(formData.get("name") || "").trim();
                  const description = String(formData.get("description_markdown") || "");
                  updateConditionMutation.mutate({
                    id: condition.id,
                    payload: {
                      name: updatedName || condition.name,
                      description_markdown: description,
                    },
                  });
                }}
              >
                <label className="field">
                  <span>Condition name</span>
                  <input
                    id={`dm-condition-name-${condition.id}`}
                    name="name"
                    value={draft.name}
                    disabled={!canManageDmContent}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const name = event.currentTarget.value;
                      setConditionDrafts((current) => ({
                        ...current,
                        [condition.id]: {
                          ...(current[condition.id] ?? draft),
                          name,
                        },
                      }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>Description</span>
                  <textarea
                    id={`dm-condition-description-${condition.id}`}
                    name="description_markdown"
                    rows={8}
                    value={draft.description}
                    disabled={!canManageDmContent}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                      const description = event.currentTarget.value;
                      setConditionDrafts((current) => ({
                        ...current,
                        [condition.id]: {
                          ...(current[condition.id] ?? draft),
                          description,
                        },
                      }));
                    }}
                  />
                </label>
                <button type="submit" disabled={!canManageDmContent || updateConditionMutation.isPending}>
                  {updateConditionMutation.isPending ? "Saving..." : "Save condition"}
                </button>
              </form>
          </details>
        ) : null}
        {canManageDmContent ? (
          <div className="dm-content-item__actions">
            <button
              type="button"
              className="ghost-button"
              disabled={!canManageDmContent || deleteConditionMutation.isPending}
              onClick={() => deleteConditionMutation.mutate(condition.id)}
            >
              {deleteConditionMutation.isPending ? "Deleting..." : "Delete condition"}
            </button>
          </div>
        ) : null}
      </article>
    );
  };

  const renderPlayerWikiPageCard = (pageFile: ContentPageFileSummary) => {
    const safety = playerWikiRemovalSafety(pageFile);
    const editDraft = playerWikiEditDrafts[pageFile.page_ref];
    const deleteConfirmed = Boolean(playerWikiDeleteConfirm[pageFile.page_ref]);
    const encodedPageRef = pageFile.page_ref
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
    const isDeleting = deletePlayerWikiPageMutation.isPending;
    const pageId = `wiki-page-${simpleSlug(pageFile.page_ref)}`;
    return (
      <article
        className="dm-content-item dm-player-wiki-card"
        key={pageFile.page_ref}
        id={pageId}
      >
        <div className="dm-content-item__header">
          <div>
            <h3>{pageFile.page.title || pageFile.page_ref}</h3>
            <p className="meta">{pageFile.page_ref}.md</p>
            {pageFile.page.summary ? <p className="meta">{pageFile.page.summary}</p> : null}
          </div>
          <div className="badge-list">
            <span className="meta-badge">{playerWikiStatusLabel(pageFile)}</span>
            <span className="meta-badge">{pageFile.page.section || "Unsectioned"}</span>
            {pageFile.page.subsection ? <span className="meta-badge">{pageFile.page.subsection}</span> : null}
            {pageFile.page.image_path ? <span className="meta-badge">Image</span> : null}
            <span className="meta-badge">{safety.removal_status_label}</span>
          </div>
        </div>
        {pageFile.page.source_ref ? <p className="meta">Source: {pageFile.page.source_ref}</p> : null}
        <div className="dm-content-removal-safety">
          <p className="meta">
            <strong>Removal safety:</strong> {safety.removal_guidance}
          </p>
          {safety.hard_delete_blockers.length ? (
            <ul className="plain-list">
              {safety.hard_delete_blockers.map((blocker) => (
                <li className="meta" key={blocker}>
                  {blocker}
            </li>
          ))}
        </ul>
      ) : null}
        </div>
        <div className="dm-content-item__actions">
          <button
            type="button"
            className="ghost-button"
            disabled={!canManagePlayerWiki}
            onClick={() => void loadPlayerWikiEditDraft(pageFile.page_ref)}
          >
            Edit
          </button>
          {pageFile.page.is_visible ? (
            <a
              className="ghost-button"
              href={`/app-next/campaigns/${encodedCampaignSlug}/pages/${encodedPageRef}`}
            >
              Open
            </a>
          ) : null}
          <button
            type="button"
            className="ghost-button"
            disabled={!canManagePlayerWiki || archivePlayerWikiPageMutation.isPending || !pageFile.page.published}
            onClick={() => archivePlayerWikiPageMutation.mutate(pageFile.page_ref)}
          >
            {archivePlayerWikiPageMutation.isPending ? "Archiving..." : "Unpublish/archive"}
          </button>
          {safety.can_hard_delete ? (
            <form className="dm-content-delete-form">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={deleteConfirmed}
                  disabled={!canManagePlayerWiki || !safety.can_hard_delete}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const checked = event.currentTarget.checked;
                    setPlayerWikiDeleteConfirm((current) => ({
                      ...current,
                      [pageFile.page_ref]: checked,
                    }));
                  }}
                />
                Confirm hard delete
              </label>
              <button
                type="button"
                className="ghost-button"
                disabled={!canManagePlayerWiki || !safety.can_hard_delete || !deleteConfirmed || isDeleting}
                onClick={() => deletePlayerWikiPageMutation.mutate(pageFile.page_ref)}
              >
                {isDeleting ? "Deleting..." : "Delete file"}
              </button>
            </form>
          ) : null}
        </div>
        {editDraft ? (
          <form
            className="stack-form dm-content-wiki-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              if (!editDraft.title.trim()) {
                setPaneError("Player Wiki page title is required.");
                setUiMessage(null);
                return;
              }
              savePlayerWikiPageMutation.mutate({
                mode: "edit",
                pageRef: pageFile.page_ref,
                draft: editDraft,
              });
            }}
          >
            <p className="meta">Page file: {pageFile.page_ref}.md</p>
            {renderPlayerWikiDraftFields({
              idPrefix: `dm-player-wiki-edit-${simpleSlug(pageFile.page_ref)}`,
              draft: editDraft,
              setDraft: (next) => {
                setPlayerWikiEditDrafts((current) => ({
                  ...current,
                  [pageFile.page_ref]: next,
                }));
              },
              includeSlug: false,
              disabled: !canManagePlayerWiki,
            })}
            <div className="dm-content-item__actions">
              <button type="submit" disabled={!canManagePlayerWiki || savePlayerWikiPageMutation.isPending}>
                {savePlayerWikiPageMutation.isPending ? "Saving..." : "Save wiki page"}
              </button>
            </div>
          </form>
        ) : null}
      </article>
    );
  };

  return (
    <>
      <section className="hero compact dm-content-hero">
        <p className="eyebrow">DM content</p>
        <h1>DM Content</h1>
        <p className="lede">{dmContentLede}</p>
        <nav className="character-subpage-nav dm-content-subpage-nav" aria-label="DM Content subpages">
          <a
            className={activeLane === "statblocks" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content`}
          >
            <span>Statblocks</span>
            <span className="meta-badge">{dmContentLaneCounts.statblocks}</span>
          </a>
          <a
            className={activeLane === "staged-articles" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=staged-articles`}
          >
            <span>Staged Articles</span>
            <span className="meta-badge">{dmContentLaneCounts.stagedArticles}</span>
          </a>
          <a
            className={activeLane === "conditions" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=conditions`}
          >
            <span>Conditions</span>
            <span className="meta-badge">{dmContentLaneCounts.conditions}</span>
          </a>
          <a
            className={activeLane === "player-wiki" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=player-wiki`}
          >
            <span>Player Wiki</span>
            <span className="meta-badge">{dmContentLaneCounts.playerWiki}</span>
          </a>
          <a
            className={activeLane === "systems" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=systems`}
          >
            <span>Systems</span>
            <span className="meta-badge">{dmContentLaneCounts.systems}</span>
          </a>
        </nav>
      </section>

      <ApiErrorNotice
        isLoading={pageIsLoading}
        message={pageError}
        onAuth={() => setAuthRequired(true)}
      />

      {paneError ? <p className="status status-error">{paneError}</p> : null}
      {uiMessage ? <p className="status status-neutral">{uiMessage}</p> : null}
      {activeLane === "statblocks" && !canManageDmContent && !dmContentQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage DM Content statblocks.</p>
      ) : null}
      {activeLane === "conditions" && !canManageDmContent && !dmContentQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage DM Content conditions.</p>
      ) : null}
      {activeLane === "staged-articles" && !canManageSession && !sessionQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage staged articles.</p>
      ) : null}
      {activeLane === "player-wiki" && !canManagePlayerWiki && !contentPagesQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage Player Wiki pages.</p>
      ) : null}

      {activeLane === "statblocks" ? (
        <div className="split-grid dm-content-staged-grid">
          <section className="card dm-statblock-create">
            <div className="section-heading">
              <h2>Create statblock</h2>
              <p className="meta">Upload or paste markdown for DM-side encounter prep.</p>
            </div>
            <form
              className="stack-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                createStatblockMutation.mutate({
                  filename: String(formData.get("filename") || "gen2-statblock.md").trim() || "gen2-statblock.md",
                  subsection: String(formData.get("subsection") || ""),
                  markdown_text: String(formData.get("markdown_text") || ""),
                });
              }}
            >
              <label className="field">
                <span>Import markdown file</span>
                <input
                  id="dm-statblock-create-file-import"
                  type="file"
                  accept=".md,.markdown,text/markdown,text/plain"
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const file = event.currentTarget.files?.item(0);
                    if (!file) {
                      return;
                    }
                    readTextFile(file, (payload) => {
                      if (!payload) {
                        setPaneError("Unable to read that markdown file.");
                        setUiMessage(null);
                        return;
                      }
                      setPaneError(null);
                      setUiMessage(null);
                      setStatblockCreateDraft((current) => ({
                        ...current,
                        filename: payload.filename,
                        markdown: payload.text,
                      }));
                    });
                  }}
                />
              </label>
              <label className="field">
                <span>Source filename</span>
                <input
                  id="dm-statblock-create-filename"
                  name="filename"
                  value={statblockCreateDraft.filename}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const filename = event.currentTarget.value;
                    setStatblockCreateDraft((current) => ({
                      ...current,
                      filename,
                    }));
                  }}
                />
              </label>
              <label className="field">
                <span>Subsection</span>
                <input
                  id="dm-statblock-create-subsection"
                  name="subsection"
                  maxLength={80}
                  value={statblockCreateDraft.subsection}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const subsection = event.currentTarget.value;
                    setStatblockCreateDraft((current) => ({
                      ...current,
                      subsection,
                    }));
                  }}
                />
              </label>
              <label className="field">
                <span>Source markdown body</span>
                <textarea
                  id="dm-statblock-create-markdown"
                  name="markdown_text"
                  rows={16}
                  value={statblockCreateDraft.markdown}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                    const markdown = event.currentTarget.value;
                    setStatblockCreateDraft((current) => ({
                      ...current,
                      markdown,
                    }));
                  }}
                />
              </label>
              <button type="submit" disabled={!canManageDmContent || createStatblockMutation.isPending}>
                {createStatblockMutation.isPending ? "Saving..." : "Save statblock"}
              </button>
            </form>
          </section>

          <section className="card dm-statblock-library">
            <div className="section-heading">
              <div>
                <h2>Statblock library</h2>
                <p className="meta">Uploaded here for DM-side encounter prep. Campaigns can pull these directly into Combat.</p>
              </div>
            </div>
            <form
              className="search-form dm-statblock-search"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label htmlFor="dm-statblock-search">Search statblocks</label>
              <input
                id="dm-statblock-search"
                type="search"
                value={statblockQuery}
                placeholder="Title, subsection, source, text"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setStatblockQuery(event.currentTarget.value)}
              />
            </form>
            {dmContentQuery.isLoading ? <p className="status status-neutral">Loading statblocks ...</p> : null}
            {!dmContentQuery.isLoading && filteredStatblocks.length ? (
              <div className="dm-content-list dm-statblock-groups">
                {topLevelStatblocks.map(renderStatblockCard)}
                {statblockSubsectionGroups.map((group) => (
                  <details className="section-block section-block--collapsible" key={group.name} open>
                    <summary className="section-toggle-summary">
                      <span className="section-toggle-summary__content">
                        <span className="section-title">{group.name}</span>
                        <span className="meta">{group.statblocks.length} statblock{group.statblocks.length === 1 ? "" : "s"}</span>
                      </span>
                      <span className="section-toggle-chevron" aria-hidden="true" />
                    </summary>
                    <div className="section-block__body">
                      <div className="dm-content-list">
                        {group.statblocks.map(renderStatblockCard)}
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            ) : null}
            {!dmContentQuery.isLoading && !filteredStatblocks.length ? (
              <p className="status status-neutral">
                {statblockQuery ? "No statblocks matched that search." : "No DM statblocks have been uploaded yet."}
              </p>
            ) : null}
          </section>
        </div>
      ) : activeLane === "conditions" ? (
        <div className="split-grid dm-content-staged-grid">
          <section className="card dm-condition-create">
            <div className="section-heading">
              <h2>Create condition</h2>
              <p className="meta">Custom combat condition reminder.</p>
            </div>
            <form
              className="stack-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                const name = String(formData.get("name") || "").trim();
                const description = String(formData.get("description_markdown") || "");
                if (!name) {
                  setPaneError("Condition name is required.");
                  setUiMessage(null);
                  return;
                }
                createConditionMutation.mutate({
                  name,
                  description_markdown: description,
                });
              }}
            >
              <label className="field">
                <span>Condition name</span>
                <input
                  id="dm-condition-create-name"
                  name="name"
                  value={conditionCreateDraft.name}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const name = event.currentTarget.value;
                    setConditionCreateDraft((current) => ({
                      ...current,
                      name,
                    }));
                  }}
                />
              </label>
              <label className="field">
                <span>Description</span>
                <textarea
                  id="dm-condition-create-description"
                  name="description_markdown"
                  rows={10}
                  value={conditionCreateDraft.description}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                    const description = event.currentTarget.value;
                    setConditionCreateDraft((current) => ({
                      ...current,
                      description,
                    }));
                  }}
                />
              </label>
              <button type="submit" disabled={!canManageDmContent || createConditionMutation.isPending}>
                {createConditionMutation.isPending ? "Saving..." : "Save condition"}
              </button>
            </form>
          </section>

          <section className="card dm-condition-library">
            <div className="section-heading">
              <div>
                <h2>Custom conditions</h2>
                <p className="meta">These names appear in the combat condition picker alongside the standard DND-5E condition list.</p>
              </div>
            </div>
            <form
              className="search-form dm-condition-search"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label htmlFor="dm-condition-search">Search conditions</label>
              <input
                id="dm-condition-search"
                type="search"
                value={conditionQuery}
                placeholder="Name or description"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setConditionQuery(event.currentTarget.value)}
              />
            </form>
            {dmContentQuery.isLoading ? <p className="status status-neutral">Loading conditions ...</p> : null}
            {!dmContentQuery.isLoading && filteredConditions.length ? (
              <div className="dm-content-list dm-condition-list">
                {filteredConditions.map(renderConditionCard)}
              </div>
            ) : null}
            {!dmContentQuery.isLoading && !filteredConditions.length ? (
              <p className="status status-neutral">
                {conditionQuery ? "No conditions matched that search." : "No custom conditions have been created yet."}
              </p>
            ) : null}
          </section>
        </div>
      ) : activeLane === "player-wiki" ? (
        <div className="split-grid dm-content-staged-grid">
          <section className="card dm-player-wiki-create">
            <div className="section-heading">
              <h2>Create player wiki page</h2>
              <p className="meta">Direct authoring for durable player-facing reference pages.</p>
            </div>
            <form
              className="stack-form dm-content-wiki-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                if (!playerWikiCreateDraft.title.trim()) {
                  setPaneError("Player Wiki page title is required.");
                  setUiMessage(null);
                  return;
                }
                savePlayerWikiPageMutation.mutate({
                  mode: "create",
                  pageRef: buildPageRefFromDraft(playerWikiCreateDraft),
                  draft: playerWikiCreateDraft,
                });
              }}
            >
              {renderPlayerWikiDraftFields({
                idPrefix: "dm-player-wiki-create",
                draft: playerWikiCreateDraft,
                setDraft: setPlayerWikiCreateDraft,
                includeSlug: true,
                disabled: !canManagePlayerWiki,
              })}
              <button type="submit" disabled={!canManagePlayerWiki || savePlayerWikiPageMutation.isPending}>
                {savePlayerWikiPageMutation.isPending ? "Saving..." : "Create wiki page"}
              </button>
            </form>
          </section>

          <section className="card dm-player-wiki-library">
            <div className="section-heading">
              <h2>Player wiki pages</h2>
              <p className="meta">{playerWikiPages.length} page{playerWikiPages.length === 1 ? "" : "s"}</p>
            </div>
            <form
              className="search-form dm-player-wiki-search"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label htmlFor="dm-player-wiki-search">Search pages</label>
              <input
                id="dm-player-wiki-search"
                type="search"
                value={playerWikiQuery}
                placeholder="Title, section, path, summary"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setPlayerWikiQuery(event.currentTarget.value)}
              />
            </form>
            {contentPagesQuery.isLoading ? <p className="status status-neutral">Loading Player Wiki pages ...</p> : null}
            {!contentPagesQuery.isLoading && filteredPlayerWikiPages.length ? (
              <div className="dm-content-list dm-player-wiki-list">
                {filteredPlayerWikiPages.map(renderPlayerWikiPageCard)}
              </div>
            ) : null}
            {!contentPagesQuery.isLoading && !filteredPlayerWikiPages.length ? (
              <p className="status status-neutral">
                {playerWikiQuery ? "No Player Wiki pages matched that search." : "No Player Wiki pages have been published yet."}
              </p>
            ) : null}
          </section>
        </div>
      ) : activeLane === "systems" ? (
        <DmContentSystemsLane campaignSlug={resolvedCampaignSlug} />
      ) : (
        <div className="split-grid dm-content-staged-grid">
          <DmArticleCreator
            className="card"
            id="dm-content-staged-article-store"
            mode={mode}
            setMode={(next) => {
              clearArticleStatus();
              setMode(next);
            }}
            sourceQuery={sourceQuery}
            setSourceQuery={setSourceQuery}
            sourceStatus={sourceStatus}
            setSourceStatus={setSourceStatus}
            sourceResults={sourceResults}
            selectedSourceRef={selectedSourceRef}
            setSelectedSourceRef={(next) => {
              setSelectedSourceRef(next);
              setSourceStatus(null);
            }}
            manualDraft={manualDraft}
            setManualDraft={(next) => {
              clearArticleStatus();
              setManualDraft(next);
            }}
            uploadDraft={uploadDraft}
            setUploadDraft={(next) => {
              clearArticleStatus();
              setUploadDraft(next);
            }}
            onSearchSources={searchSources}
            onCreate={(payload) => {
              clearArticleStatus();
              createArticleMutation.mutate(payload);
            }}
            isCreating={createArticleMutation.isPending}
          />

          <article className="card" id="dm-content-staged-articles-queue">
            <div className="section-heading">
              <div>
                <h2>Session reveal queue</h2>
                <p className="meta">Articles created here go straight into the same staged queue used on Session DM.</p>
              </div>
              <p className="meta">{stagedArticles.length}</p>
            </div>
            {stagedArticles.length ? (
              <div className="session-article-stack">
                {stagedArticles.map((article) => {
                  const draft = stagedDrafts[article.id] ?? {
                    title: article.title,
                    body: article.body_markdown,
                    imageAltText: article.image?.alt_text || "",
                    imageCaption: article.image?.caption || "",
                    image: null,
                  };
                  const savedLabel = article.created_at ? `Saved ${formatTimestamp(article.created_at)}` : null;
                  return (
                    <details
                      className="feature-detail session-article-detail"
                      data-session-article-id={article.id}
                      key={article.id}
                    >
                      <summary>
                        <span>{article.title}</span>
                        {savedLabel ? <span className="meta">{savedLabel}</span> : null}
                      </summary>
                      {article.image ? (
                        <figure className="article-figure">
                          <img
                            className="article-image"
                            src={resolveArticleImage(resolvedCampaignSlug, article)}
                            alt={article.image.alt_text || "Article image"}
                          />
                          {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                        </figure>
                      ) : null}
                      <SessionArticleSourceLine article={article} />
                      {renderArticleBody(article, "article-body--compact")}
                      <details className="session-article-edit-detail">
                        <summary>Edit prep draft</summary>
                        <form
                          className="stack-form session-article-edit-form"
                          onSubmit={(event: FormEvent<HTMLFormElement>) => {
                            event.preventDefault();
                            const formData = new FormData(event.currentTarget);
                            const currentDraft = stagedDrafts[article.id] ?? draft;
                            updateArticleMutation.mutate({
                              id: article.id,
                              hasExistingImage: Boolean(article.image),
                              payload: {
                                title: String(formData.get("title") || ""),
                                body: String(formData.get("body_markdown") || ""),
                                imageAltText: String(formData.get("image_alt_text") || ""),
                                imageCaption: String(formData.get("image_caption") || ""),
                                image: currentDraft.image ?? null,
                              },
                            });
                          }}
                        >
                          <label className="field">
                            <span>Title</span>
                            <input
                              id={`dm-content-stage-title-${article.id}`}
                              name="title"
                              value={draft.title}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const title = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    title,
                                  },
                                }));
                              }}
                            />
                          </label>
                          <label className="field">
                            <span>Body</span>
                            <textarea
                              id={`dm-content-stage-body-${article.id}`}
                              name="body_markdown"
                              rows={8}
                              value={draft.body}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                                const body = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    body,
                                  },
                                }));
                              }}
                            />
                          </label>
                          <div className="field session-file-field">
                            <span>{article.image ? "Replace image" : "Image"}</span>
                            <input
                              id={`dm-content-stage-image-${article.id}`}
                              className="session-file-input"
                              type="file"
                              accept=".png,.jpg,.jpeg,.webp,.gif"
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const file = event.currentTarget.files?.item(0);
                                if (!file) {
                                  setStagedDrafts((current) => ({
                                    ...current,
                                    [article.id]: {
                                      ...(current[article.id] ?? draft),
                                      image: null,
                                    },
                                  }));
                                  return;
                                }
                                readBinaryAsBase64(file, (payload) => {
                                  setStagedDrafts((current) => ({
                                    ...current,
                                    [article.id]: {
                                      ...(current[article.id] ?? draft),
                                      image: payload,
                                    },
                                  }));
                                });
                              }}
                            />
                            <label className="session-file-dropzone" htmlFor={`dm-content-stage-image-${article.id}`} tabIndex={0}>
                              <span>Drag and drop a file here</span>
                              <span className="meta">or use Browse to choose one</span>
                              <span className="session-file-dropzone__browse">Browse</span>
                              <span className="meta session-file-dropzone__name">No file selected.</span>
                            </label>
                          </div>
                          <label className="field">
                            <span>Image alt text</span>
                            <input
                              id={`dm-content-stage-alt-${article.id}`}
                              name="image_alt_text"
                              value={draft.imageAltText}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const imageAltText = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    imageAltText,
                                  },
                                }));
                              }}
                            />
                          </label>
                          <label className="field">
                            <span>Image caption</span>
                            <input
                              id={`dm-content-stage-caption-${article.id}`}
                              name="image_caption"
                              value={draft.imageCaption}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const imageCaption = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    imageCaption,
                                  },
                                }));
                              }}
                            />
                          </label>
                          {draft.image ? <p className="status status-neutral">Selected image: {draft.image.filename}</p> : null}
                          <button
                            type="submit"
                            className="ghost-button"
                            disabled={!canManageSession || updateArticleMutation.isPending}
                          >
                            {updateArticleMutation.isPending ? "Saving..." : "Update prep draft"}
                          </button>
                        </form>
                      </details>
                      <div className="session-article-detail__actions">
                        <SessionArticleReferenceActions article={article} includePromotionLinks />
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={!canManageSession || deleteArticleMutation.isPending}
                          onClick={() => deleteArticleMutation.mutate(article.id)}
                        >
                          {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                        </button>
                      </div>
                    </details>
                );
              })}
            </div>
          ) : (
            <p className="status status-neutral">No staged articles.</p>
          )}
          </article>
      </div>
      )}
    </>
  );
}

function CharacterDetailPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug",
  });
  const location = useLocation();
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const initialSection = normalizeCharacterSection(new URLSearchParams(location.search).get("page"));

  return (
    <CharacterPane
      campaignSlug={campaignSlug}
      initialCharacterSlug={characterSlug}
      initialSection={initialSection}
      surface="read"
      onSelectedCharacterChange={(nextSlug) => {
        window.history.pushState(
          null,
          "",
          `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(nextSlug)}`,
        );
      }}
    />
  );
}

function CombatPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/combat",
  });
  const location = useLocation();
  const campaignSlug = params.campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const readSearchView = (search: string): CombatView => {
    const requested = new URLSearchParams(search).get("view");
    return requested === "status" || requested === "controls" ? requested : "player";
  };
  const [selectedCombatantId, setSelectedCombatantId] = useState<number | null>(() => {
    const parsed = Number(new URLSearchParams(window.location.search).get("combatant") || "");
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  });
  const [activeCombatView, setActiveCombatView] = useState<CombatView>(() => readSearchView(window.location.search));
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [vitalsDraft, setVitalsDraft] = useState<CombatVitalsDraft>({
    currentHp: "",
    maxHp: "",
    tempHp: "",
    movementTotal: "",
  });
  const [resourcesDraft, setResourcesDraft] = useState<CombatResourcesDraft>({
    movementRemaining: "",
    hasAction: false,
    hasBonusAction: false,
    hasReaction: false,
  });
  const [turnDraft, setTurnDraft] = useState<CombatTurnDraft>({ turnValue: "", initiativePriority: "1" });
  const [conditionDraft, setConditionDraft] = useState<CombatConditionDraft>({ name: "", durationText: "" });
  const [playerSeedDraft, setPlayerSeedDraft] = useState<CombatPlayerSeedDraft>({
    characterSlug: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [npcSeedDraft, setNpcSeedDraft] = useState<CombatNpcSeedDraft>({
    displayName: "",
    turnValue: "",
    initiativeBonus: "0",
    dexterityModifier: "",
    initiativePriority: "1",
    currentHp: "",
    maxHp: "",
    tempHp: "0",
    movementTotal: "30",
  });
  const [statblockSeedDraft, setStatblockSeedDraft] = useState<CombatStatblockSeedDraft>({
    statblockId: "",
    displayName: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [systemsSeedDraft, setSystemsSeedDraft] = useState<CombatSystemsSeedDraft>({
    entryKey: "",
    displayName: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [combatAddMode, setCombatAddMode] = useState<"player" | "systems" | "dm-content" | "custom">(
    "player",
  );
  const [systemsSearchQuery, setSystemsSearchQuery] = useState("");
  const [systemsSearchStatus, setSystemsSearchStatus] = useState<string | null>(null);
  const [systemsSearchResults, setSystemsSearchResults] = useState<CombatSystemsMonsterSearchResult[]>([]);
  const [confirmClearTracker, setConfirmClearTracker] = useState(false);

  useEffect(() => {
    const currentSearch = window.location.search;
    const params = new URLSearchParams(currentSearch);
    const parsed = Number(params.get("combatant") || "");
    setSelectedCombatantId(Number.isFinite(parsed) && parsed > 0 ? parsed : null);
    setActiveCombatView(readSearchView(currentSearch));
  }, [location.href]);

  const combatQuery = useQuery({
    queryKey: ["combat", campaignSlug, activeCombatView, selectedCombatantId],
    queryFn: async () => {
      const previous = queryClient.getQueryData<CombatPayload>([
        "combat",
        campaignSlug,
        activeCombatView,
        selectedCombatantId,
      ]);
      if (!previous) {
        return apiClient.getCombat(campaignSlug, selectedCombatantId);
      }
      const liveResponse = await apiClient.getCombatLiveState(campaignSlug, {
        liveRevision: previous.live_revision,
        liveViewToken: previous.live_view_token,
        combatantId: selectedCombatantId,
      });
      const resolved = resolveCombatLivePayload(previous, liveResponse);
      return resolved ?? apiClient.getCombat(campaignSlug, selectedCombatantId);
    },
    enabled: Boolean(campaignSlug),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && !data.combat_system_supported) {
        return false;
      }
      return data?.poll_settings?.active_interval_ms ?? 3000;
    },
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(combatQuery.error)) {
      setAuthRequired(true);
    }
  }, [combatQuery.error, setAuthRequired]);

  const payload = combatQuery.data;
  const tracker = payload?.tracker;
  const selectedCombatant = payload?.selected_combatant ?? null;
  const selectedCombatantMeta = selectedCombatant
    ? selectedCombatant.subtitle || selectedCombatant.source_label || selectedCombatant.type_label
    : "";
  const selectedPlayerCharacter = payload?.selected_player_character ?? null;
  const selectedCharacterSlug = selectedPlayerCharacter?.character_slug || null;
  const selectedCombatantKicker =
    selectedCombatant?.character_slug && selectedCombatant.character_slug === selectedCharacterSlug
      ? "Combat workspace"
      : "Combat snapshot";
  const canManageCombat = Boolean(payload?.permissions.can_manage_combat);
  const canAccessDmContent = Boolean(payload?.permissions.can_access_dm_content);
  const canAccessSystems = Boolean(payload?.permissions.can_access_systems);
  const effectiveCombatView: CombatView = canManageCombat ? activeCombatView : "player";
  const paneError = getApiErrorMessage(combatQuery.error);
  const availableCharacters: CombatAvailableCharacterChoice[] = payload?.available_character_choices ?? [];
  const availableStatblocks: CombatAvailableStatblockChoice[] = payload?.available_statblock_choices ?? [];
  const conditionOptions = payload?.combat_condition_options ?? [];
  const encodedCampaignSlug = encodeURIComponent(campaignSlug);

  useEffect(() => {
    if (!canAccessSystems && combatAddMode === "systems") {
      setCombatAddMode("player");
    } else if (!canAccessDmContent && combatAddMode === "dm-content") {
      setCombatAddMode("player");
    }
  }, [canAccessSystems, canAccessDmContent, combatAddMode]);

  const setCombatUrl = (view: CombatView, combatantId: number | null) => {
    const params = new URLSearchParams();
    if (view !== "player") {
      params.set("view", view);
    }
    if (combatantId) {
      params.set("combatant", String(combatantId));
    }
    const query = params.toString();
    window.history.pushState(null, "", `/app-next/campaigns/${encodedCampaignSlug}/combat${query ? `?${query}` : ""}`);
  };

  useEffect(() => {
    if (!payload?.permissions.can_manage_combat) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (!params.has("view") && activeCombatView === "player") {
      setActiveCombatView("status");
      setCombatUrl("status", selectedCombatantId);
    }
  }, [payload?.permissions.can_manage_combat]);

  useEffect(() => {
    if (!selectedCombatant) {
      return;
    }
    setVitalsDraft({
      currentHp: String(readNumber(selectedCombatant.current_hp)),
      maxHp: String(readNumber(selectedCombatant.max_hp)),
      tempHp: String(readNumber(selectedCombatant.temp_hp)),
      movementTotal: String(readNumber(selectedCombatant.movement_total)),
    });
    setResourcesDraft({
      movementRemaining: String(readNumber(selectedCombatant.movement_remaining)),
      hasAction: Boolean(selectedCombatant.has_action),
      hasBonusAction: Boolean(selectedCombatant.has_bonus_action),
      hasReaction: Boolean(selectedCombatant.has_reaction),
    });
    setTurnDraft({
      turnValue: String(readNumber(selectedCombatant.turn_value)),
      initiativePriority: String(readNumber(selectedCombatant.initiative_priority, 1)),
    });
    setConditionDraft({ name: "", durationText: "" });
  }, [selectedCombatant?.id]);

  const selectCombatant = (combatantId: number) => {
    setSelectedCombatantId(combatantId);
    setCombatUrl(effectiveCombatView, combatantId);
  };

  const selectCombatView = (view: CombatView) => {
    setActiveCombatView(view);
    setCombatUrl(view, selectedCombatantId);
  };

  const selectCharacterTarget = (characterSlug: string) => {
    const target = payload?.player_character_targets.find((item) => item.character_slug === characterSlug);
    if (target?.combatant_id) {
      selectCombatant(target.combatant_id);
    }
  };

  const replaceCombatPayload = (response: CombatPayload, message: string) => {
    queryClient.setQueryData(["combat", campaignSlug, activeCombatView, selectedCombatantId], response);
    setStatusMessage(message);
    setErrorMessage(null);
    void combatQuery.refetch();
  };

  const handleCombatMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage(null);
    setErrorMessage(apiErrorMessage(error));
  };

  const updateTurnMutation = useMutation({
    mutationFn: (draft: CombatTurnPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantTurn(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Turn order saved."),
    onError: handleCombatMutationError,
  });

  const updateVitalsMutation = useMutation({
    mutationFn: (draft: CombatVitalsPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantVitals(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Vitals saved."),
    onError: handleCombatMutationError,
  });

  const updateResourcesMutation = useMutation({
    mutationFn: (draft: CombatResourcesPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantResources(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Action economy saved."),
    onError: handleCombatMutationError,
  });

  const addConditionMutation = useMutation({
    mutationFn: (draft: CombatConditionDraft) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.addCombatCondition(campaignSlug, selectedCombatant.id, {
        name: draft.name.trim(),
        duration_text: draft.durationText.trim(),
      });
    },
    onSuccess: (response) => {
      setConditionDraft({ name: "", durationText: "" });
      replaceCombatPayload(response, "Condition added.");
    },
    onError: handleCombatMutationError,
  });

  const deleteConditionMutation = useMutation({
    mutationFn: (condition: CombatCondition) =>
      apiClient.deleteCombatCondition(campaignSlug, condition.id, selectedCombatant?.id ?? null),
    onSuccess: (response) => replaceCombatPayload(response, "Condition removed."),
    onError: handleCombatMutationError,
  });

  const setCurrentMutation = useMutation({
    mutationFn: () => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.setCurrentCombatant(campaignSlug, selectedCombatant.id);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Current turn set."),
    onError: handleCombatMutationError,
  });

  const advanceTurnMutation = useMutation({
    mutationFn: () => apiClient.advanceCombatTurn(campaignSlug, selectedCombatant?.id ?? null),
    onSuccess: (response) => replaceCombatPayload(response, "Turn advanced."),
    onError: handleCombatMutationError,
  });

  const clearCombatMutation = useMutation({
    mutationFn: () => apiClient.clearCombat(campaignSlug),
    onSuccess: (response) => {
      setSelectedCombatantId(null);
      setConfirmClearTracker(false);
      replaceCombatPayload(response, "Combat tracker cleared.");
    },
    onError: handleCombatMutationError,
  });

  const deleteCombatantMutation = useMutation({
    mutationFn: () => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.deleteCombatant(campaignSlug, selectedCombatant.id);
    },
    onSuccess: (response) => {
      setSelectedCombatantId(response.selected_combatant_id ?? null);
      replaceCombatPayload(response, "Combatant removed.");
    },
    onError: handleCombatMutationError,
  });

  const addPlayerMutation = useMutation({
    mutationFn: () =>
      apiClient.addCombatPlayer(
        campaignSlug,
        {
          character_slug: playerSeedDraft.characterSlug,
          turn_value: playerSeedDraft.turnValue,
          initiative_priority: playerSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setPlayerSeedDraft({ characterSlug: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "Player character added.");
    },
    onError: handleCombatMutationError,
  });

  const addNpcMutation = useMutation({
    mutationFn: () => {
      const payload: CombatAddNpcPayload = {
        display_name: npcSeedDraft.displayName.trim(),
        turn_value: npcSeedDraft.turnValue,
        initiative_bonus: npcSeedDraft.initiativeBonus,
        dexterity_modifier: npcSeedDraft.dexterityModifier,
        initiative_priority: npcSeedDraft.initiativePriority,
        current_hp: npcSeedDraft.currentHp,
        max_hp: npcSeedDraft.maxHp,
        temp_hp: npcSeedDraft.tempHp,
        movement_total: npcSeedDraft.movementTotal,
      };
      return apiClient.addCombatNpc(campaignSlug, payload, selectedCombatantId);
    },
    onSuccess: (response) => {
      setNpcSeedDraft({
        displayName: "",
        turnValue: "",
        initiativeBonus: "0",
        dexterityModifier: "",
        initiativePriority: "1",
        currentHp: "",
        maxHp: "",
        tempHp: "0",
        movementTotal: "30",
      });
      replaceCombatPayload(response, "NPC added.");
    },
    onError: handleCombatMutationError,
  });

  const addStatblockMutation = useMutation({
    mutationFn: () =>
      apiClient.addCombatStatblock(
        campaignSlug,
        {
          statblock_id: statblockSeedDraft.statblockId,
          display_name: statblockSeedDraft.displayName.trim(),
          turn_value: statblockSeedDraft.turnValue,
          initiative_priority: statblockSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setStatblockSeedDraft({ statblockId: "", displayName: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "DM Content statblock added.");
    },
    onError: handleCombatMutationError,
  });

  const addSystemsMonsterMutation = useMutation({
    mutationFn: (entryKey: string) =>
      apiClient.addCombatSystemsMonster(
        campaignSlug,
        {
          entry_key: entryKey,
          display_name: systemsSeedDraft.displayName.trim(),
          turn_value: systemsSeedDraft.turnValue,
          initiative_priority: systemsSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setSystemsSeedDraft({ entryKey: "", displayName: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "Systems monster added.");
    },
    onError: handleCombatMutationError,
  });

  const searchSystemsMonsters = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = systemsSearchQuery.trim();
    if (query.length < 2) {
      setSystemsSearchStatus("Type at least 2 letters to search Systems monsters.");
      setSystemsSearchResults([]);
      return;
    }
    setSystemsSearchStatus("Searching Systems monsters ...");
    try {
      const response = await apiClient.searchCombatSystemsMonsters(campaignSlug, query);
      setSystemsSearchResults(response.results);
      setSystemsSearchStatus(response.message);
      setErrorMessage(null);
    } catch (error) {
      handleCombatMutationError(error);
      setSystemsSearchResults([]);
      setSystemsSearchStatus(null);
    }
  };

  const renderCombatantCard = (combatant: CombatantSummary) => {
    const isSelected = selectedCombatant?.id === combatant.id;
    return (
      <button
        type="button"
        className={isSelected ? "combatant-card combatant-card--selected" : "combatant-card"}
        key={combatant.id}
        onClick={() => selectCombatant(combatant.id)}
        aria-pressed={isSelected}
      >
        <span className="combatant-card__topline">
          <strong>{combatant.name}</strong>
          {combatant.is_current_turn ? <span className="pill">Current</span> : null}
        </span>
        <span className="meta">{combatant.subtitle || combatant.type_label}</span>
        <span className="combatant-card__stats">
          <span>Turn {combatant.turn_value}</span>
          {combatant.show_detail ? (
            <span>
              HP {readNumber(combatant.current_hp)} / {readNumber(combatant.max_hp)}
              {readNumber(combatant.temp_hp) ? ` +${readNumber(combatant.temp_hp)} temp` : ""}
            </span>
          ) : (
            <span>Hidden detail</span>
          )}
        </span>
        {combatant.conditions.length ? (
          <span className="combatant-card__conditions">
            {combatant.conditions.map((condition) => condition.name).join(", ")}
          </span>
        ) : null}
      </button>
    );
  };

  const renderCombatViewSwitch = () => {
    if (!canManageCombat) {
      return null;
    }
    return (
      <nav aria-label="DM encounter subview">
        {[
          { id: "status" as CombatView, label: "DM status", activeClass: "button-link", inactiveClass: "ghost-button" },
          { id: "controls" as CombatView, label: "Controls", activeClass: "button-link", inactiveClass: "ghost-button" },
        ].map((view) => (
          <button
            type="button"
            key={view.id}
            className={effectiveCombatView === view.id ? view.activeClass : view.inactiveClass}
            onClick={() => selectCombatView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </nav>
    );
  };

  const renderDmStatus = () => {
    if (!canManageCombat) {
      return (
        <article className="card">
          <p>DM combat status requires combat management access.</p>
        </article>
      );
    }
    if (!selectedCombatant) {
      return (
        <article className="card">
          <h3>No selected combatant</h3>
          <p>Add combatants in DM Controls, then select one from the turn order.</p>
        </article>
      );
    }
    const isPlayerCharacter = Boolean(selectedCombatant.character_slug);
    const vitalsPayload = (): CombatVitalsPatchPayload => {
      const base: CombatVitalsPatchPayload = {
        current_hp: vitalsDraft.currentHp,
        temp_hp: vitalsDraft.tempHp,
      };
      if (isPlayerCharacter) {
        base.expected_revision = selectedCombatant.state_revision;
      } else {
        base.expected_combatant_revision = selectedCombatant.combatant_revision;
        base.max_hp = vitalsDraft.maxHp;
        base.movement_total = vitalsDraft.movementTotal;
      }
      return base;
    };

    return (
      <>
        <section className="combat-dm-grid" aria-label="DM tactical controls">
          <article className="card combat-control-card">
            <div className="section-heading combat-status-snapshot__heading">
              <div>
                <p className="card-kicker">Authority</p>
                <h2>Turn Focus</h2>
              </div>
              <div className="combatant-badges">
                <span className="combat-badge">Round {tracker?.round_number ?? "?"}</span>
                <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
                {selectedCombatant.is_current_turn ? (
                  <span className="combat-badge combat-badge--active">Current turn</span>
                ) : (
                  <button
                    type="button"
                    className="combat-badge combat-badge--button combat-status-snapshot__set-current"
                    onClick={() => setCurrentMutation.mutate()}
                    disabled={setCurrentMutation.isPending}
                  >
                    {setCurrentMutation.isPending ? "Setting..." : "Set current"}
                  </button>
                )}
              </div>
            </div>
            <form
              className="stack-form combat-status-authority-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateTurnMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  turn_value: turnDraft.turnValue,
                  initiative_priority: turnDraft.initiativePriority,
                });
              }}
            >
              <label className="field">
                <span>Turn value</span>
                <input
                  type="number"
                  value={turnDraft.turnValue}
                  onChange={(event) => setTurnDraft({ ...turnDraft, turnValue: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Priority</span>
                <input
                  type="number"
                  min="1"
                  value={turnDraft.initiativePriority}
                  onChange={(event) =>
                    setTurnDraft({ ...turnDraft, initiativePriority: event.currentTarget.value })
                  }
                />
              </label>
              <button type="submit" disabled={updateTurnMutation.isPending}>
                {updateTurnMutation.isPending ? "Saving..." : "Save turn"}
              </button>
            </form>
            <div className="hero-actions combat-turn-actions">
              <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
                {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
              </button>
            </div>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Snapshot</p>
              <h3>Vitals</h3>
            </div>
            <div className="combat-summary-grid combat-summary-grid--snapshot">
              <form
                className="combat-stat combat-stat--editable"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateVitalsMutation.mutate(vitalsPayload());
                }}
              >
                <span className="meta">HP</span>
                <div className="combat-inline-value">
                  <input
                    className="combat-stat-input combat-stat-input--number"
                    aria-label="DM Current HP"
                    type="number"
                    value={vitalsDraft.currentHp}
                    onChange={(event) => setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })}
                  />
                  <span className="combat-inline-divider">/</span>
                  <strong>{vitalsDraft.maxHp}</strong>
                </div>
              </form>
              <form
                className="combat-stat combat-stat--editable"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateVitalsMutation.mutate(vitalsPayload());
                }}
              >
                <span className="meta">Temp HP</span>
                <input
                  className="combat-stat-input combat-stat-input--single"
                  aria-label="DM Temp HP"
                  type="number"
                  min="0"
                  value={vitalsDraft.tempHp}
                  onChange={(event) => setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })}
                />
              </form>
              {!isPlayerCharacter ? (
                <>
                  <label className="field">
                    <span>Max HP</span>
                    <input
                      aria-label="DM Max HP"
                      type="number"
                      min="0"
                      value={vitalsDraft.maxHp}
                      onChange={(event) => setVitalsDraft({ ...vitalsDraft, maxHp: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Movement total</span>
                    <input
                      aria-label="DM Movement total"
                      type="number"
                      min="0"
                      value={vitalsDraft.movementTotal}
                      onChange={(event) =>
                        setVitalsDraft({ ...vitalsDraft, movementTotal: event.currentTarget.value })
                      }
                    />
                  </label>
                </>
              ) : null}
              <button type="button" onClick={() => updateVitalsMutation.mutate(vitalsPayload())} aria-label="Save DM vitals" disabled={updateVitalsMutation.isPending}>
                {updateVitalsMutation.isPending ? "Saving..." : "Save vitals"}
              </button>
            </div>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Round tools</p>
              <h3>Action Economy</h3>
            </div>
            <form
              className="combat-resource-strip combat-inline-resource-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateResourcesMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  movement_remaining: resourcesDraft.movementRemaining,
                  has_action: resourcesDraft.hasAction,
                  has_bonus_action: resourcesDraft.hasBonusAction,
                  has_reaction: resourcesDraft.hasReaction,
                });
              }}
            >
              <label className="combat-stat">
                <span className="meta">Movement</span>
                <div className="combat-inline-value">
                  <input
                    className="combat-stat-input combat-stat-input--number"
                    aria-label="DM Movement Remaining"
                    type="number"
                    min="0"
                    value={resourcesDraft.movementRemaining}
                    onChange={(event) =>
                      setResourcesDraft({ ...resourcesDraft, movementRemaining: event.currentTarget.value })
                    }
                  />
                  <span className="combat-inline-divider">/</span>
                  <strong>{vitalsDraft.movementTotal}</strong>
                </div>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasAction}
                  onChange={(event) => setResourcesDraft({ ...resourcesDraft, hasAction: event.currentTarget.checked })}
                />
                <span className="combat-resource">Action</span>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasBonusAction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasBonusAction: event.currentTarget.checked })
                  }
                />
                <span className="combat-resource">Bonus action</span>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasReaction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasReaction: event.currentTarget.checked })
                  }
                />
                <span className="combat-resource">Reaction</span>
              </label>
              <button type="submit" disabled={updateResourcesMutation.isPending}>
                {updateResourcesMutation.isPending ? "Saving..." : "Save economy"}
              </button>
            </form>
          </article>

          <article className="card combat-control-card">
            <datalist id="gen2-combat-condition-options">
              {conditionOptions.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
            <section className="combat-conditions combat-conditions--compact combat-status-conditions">
              <div className="section-heading">
                <h3>Conditions</h3>
                <details className="combat-condition-editor combat-condition-editor--add">
                  <summary>Add condition</summary>
                  <form
                    className="combat-condition-editor__form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addConditionMutation.mutate(conditionDraft);
                    }}
                  >
                    <label className="field">
                      <span>Condition</span>
                      <input
                        type="text"
                        list="gen2-combat-condition-options"
                        value={conditionDraft.name}
                        onChange={(event) => setConditionDraft({ ...conditionDraft, name: event.currentTarget.value })}
                      />
                    </label>
                    <label className="field">
                      <span>Duration</span>
                      <input
                        type="text"
                        value={conditionDraft.durationText}
                        onChange={(event) =>
                          setConditionDraft({ ...conditionDraft, durationText: event.currentTarget.value })
                        }
                      />
                    </label>
                    <button type="submit" disabled={addConditionMutation.isPending}>
                      {addConditionMutation.isPending ? "Adding..." : "Add condition"}
                    </button>
                  </form>
                </details>
              </div>
              {selectedCombatant.conditions.length ? (
                <div className="combat-condition-list">
                  {selectedCombatant.conditions.map((condition) => (
                    <div className="combat-condition-item" key={condition.id}>
                      <div>
                        <strong>{condition.name}</strong>
                        {condition.duration_text ? <p className="meta">{condition.duration_text}</p> : null}
                      </div>
                      <div className="combat-condition-actions">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => deleteConditionMutation.mutate(condition)}
                          disabled={deleteConditionMutation.isPending}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="meta">No conditions are active on this combatant.</p>
              )}
            </section>
          </article>
        </section>

        {selectedCombatant.character_slug ? (
          <section className="combat-pc-workspace">
            <div className="section-heading">
              <div>
                <p className="meta">Selected PC detail</p>
                <h2>{selectedCombatant.name}</h2>
              </div>
            </div>
            <CharacterPane campaignSlug={campaignSlug} initialCharacterSlug={selectedCombatant.character_slug} surface="combat" />
          </section>
        ) : null}

        <section className="card combat-danger-card">
          <div>
            <p className="meta">Cleanup</p>
            <h3>Selected combatant</h3>
          </div>
          <button type="button" className="ghost-button" onClick={() => deleteCombatantMutation.mutate()}>
            {deleteCombatantMutation.isPending ? "Removing..." : "Remove selected combatant"}
          </button>
        </section>
      </>
    );
  };

  const renderDmControls = () => {
    if (!canManageCombat) {
      return (
        <article className="card">
          <p>DM combat controls require combat management access.</p>
        </article>
      );
    }
    return (
      <section className="combat-controls-layout" aria-label="DM combat controls">
        <article className="card combat-control-card">
          <div>
            <p className="meta">Encounter controls</p>
            <h3>Tracker</h3>
          </div>
          <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
            {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
          </button>
        </article>

        <section className="card sidebar-card">
          <h2>Add combatant</h2>
          <div className="combat-add-combatant-mode-switcher" role="radiogroup" aria-label="Add combatant type">
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--player"
              id="combat-add-mode-player"
              name="combat-add-mode"
              type="radio"
              value="player"
              checked={combatAddMode === "player"}
              onChange={() => setCombatAddMode("player")}
            />
            {canAccessSystems ? (
              <input
                className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--systems"
                id="combat-add-mode-systems"
                name="combat-add-mode"
                type="radio"
                value="systems"
                checked={combatAddMode === "systems"}
                onChange={() => setCombatAddMode("systems")}
              />
            ) : null}
            {canAccessDmContent ? (
              <input
                className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--dm-content"
                id="combat-add-mode-dm-content"
                name="combat-add-mode"
                type="radio"
                value="dm-content"
                checked={combatAddMode === "dm-content"}
                onChange={() => setCombatAddMode("dm-content")}
              />
            ) : null}
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--custom"
              id="combat-add-mode-custom"
              name="combat-add-mode"
              type="radio"
              value="custom"
              checked={combatAddMode === "custom"}
              onChange={() => setCombatAddMode("custom")}
            />
            <div className="combat-add-combatant-mode-toggle">
              <label className="ghost-button" htmlFor="combat-add-mode-player">
                Add player character
              </label>
              {canAccessSystems ? (
                <label className="ghost-button" htmlFor="combat-add-mode-systems">
                  Add NPC from Systems
                </label>
              ) : null}
              {canAccessDmContent ? (
                <label className="ghost-button" htmlFor="combat-add-mode-dm-content">
                  Add NPC from DM Content
                </label>
              ) : null}
              <label className="ghost-button" htmlFor="combat-add-mode-custom">
                Add custom combatant
              </label>
            </div>

            <div
              className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--player ${
                combatAddMode === "player" ? "combat-add-combatant-mode-panel--active" : ""
              }`}
            >
              {availableCharacters.length ? (
                <form
                  className="stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    addPlayerMutation.mutate();
                  }}
                >
                  <label className="field">
                    <span>Character</span>
                    <select
                      value={playerSeedDraft.characterSlug}
                      onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, characterSlug: event.currentTarget.value })}
                    >
                      <option value="">Choose character</option>
                      {availableCharacters.map((choice) => (
                        <option key={choice.slug} value={choice.slug}>
                          {choice.name} {choice.subtitle ? `- ${choice.subtitle}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Turn value</span>
                    <input
                      type="number"
                      value={playerSeedDraft.turnValue}
                      onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, turnValue: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={playerSeedDraft.initiativePriority}
                      onChange={(event) =>
                        setPlayerSeedDraft({ ...playerSeedDraft, initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                  <button type="submit" disabled={addPlayerMutation.isPending}>
                    {addPlayerMutation.isPending ? "Adding..." : "Add player character"}
                  </button>
                </form>
              ) : (
                <p className="meta">All visible player characters are already in the tracker.</p>
              )}
            </div>

            {canAccessSystems ? (
              <div
                className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--systems ${
                  combatAddMode === "systems" ? "combat-add-combatant-mode-panel--active" : ""
                }`}
              >
                <form className="stack-form" onSubmit={searchSystemsMonsters}>
                  <label className="field">
                    <span>Search monsters</span>
                    <input
                      type="search"
                      value={systemsSearchQuery}
                      onChange={(event) => setSystemsSearchQuery(event.currentTarget.value)}
                    />
                  </label>
                  <button type="submit">Search</button>
                </form>
                {systemsSearchStatus ? <p className="status status-neutral">{systemsSearchStatus}</p> : null}
                <div className="combat-systems-results">
                  {systemsSearchResults.map((result) => (
                    <article className="compact-card" key={result.entry_key}>
                      <div>
                        <strong>{result.title}</strong>
                        <p className="meta">
                          {result.source_id} - {result.subtitle} - Init {result.initiative_bonus}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => addSystemsMonsterMutation.mutate(result.entry_key)}
                        disabled={addSystemsMonsterMutation.isPending}
                      >
                        Add
                      </button>
                    </article>
                  ))}
                </div>
                <div className="stack-form">
                  <label className="field">
                    <span>Display name</span>
                    <input
                      type="text"
                      value={systemsSeedDraft.displayName}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, displayName: event.currentTarget.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Turn value</span>
                    <input
                      type="number"
                      value={systemsSeedDraft.turnValue}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, turnValue: event.currentTarget.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={systemsSeedDraft.initiativePriority}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {canAccessDmContent ? (
              <div
                className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--dm-content ${
                  combatAddMode === "dm-content" ? "combat-add-combatant-mode-panel--active" : ""
                }`}
              >
                {availableStatblocks.length ? (
                  <form
                    className="stack-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addStatblockMutation.mutate();
                    }}
                  >
                    <label className="field">
                      <span>Statblock</span>
                      <select
                        value={statblockSeedDraft.statblockId}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, statblockId: event.currentTarget.value })
                        }
                      >
                        <option value="">Choose statblock</option>
                        {availableStatblocks.map((choice) => (
                          <option key={choice.id} value={choice.id}>
                            {choice.title} - {choice.subtitle}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Display name override</span>
                      <input
                        type="text"
                        value={statblockSeedDraft.displayName}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, displayName: event.currentTarget.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Turn override</span>
                      <input
                        type="number"
                        value={statblockSeedDraft.turnValue}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, turnValue: event.currentTarget.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Priority</span>
                      <input
                        type="number"
                        min="1"
                        value={statblockSeedDraft.initiativePriority}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, initiativePriority: event.currentTarget.value })
                        }
                      />
                    </label>
                    <button type="submit" disabled={addStatblockMutation.isPending}>
                      {addStatblockMutation.isPending ? "Adding..." : "Add statblock"}
                    </button>
                  </form>
                ) : (
                  <p className="meta">Upload statblocks on the DM Content page to use them here.</p>
                )}
              </div>
            ) : null}

            <div
              className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--custom ${
                combatAddMode === "custom" ? "combat-add-combatant-mode-panel--active" : ""
              }`}
            >
              <form
                className="stack-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  addNpcMutation.mutate();
                }}
              >
                <label className="field">
                  <span>Name</span>
                  <input
                    type="text"
                    value={npcSeedDraft.displayName}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, displayName: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Turn value</span>
                  <input
                    type="number"
                    value={npcSeedDraft.turnValue}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, turnValue: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Initiative bonus</span>
                  <input
                    type="number"
                    value={npcSeedDraft.initiativeBonus}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, initiativeBonus: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Dex mod</span>
                  <input
                    type="number"
                    value={npcSeedDraft.dexterityModifier}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, dexterityModifier: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Current HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.currentHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, currentHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Max HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.maxHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, maxHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Temp HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.tempHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, tempHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Movement</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.movementTotal}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, movementTotal: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Priority</span>
                  <input
                    type="number"
                    min="1"
                    value={npcSeedDraft.initiativePriority}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, initiativePriority: event.currentTarget.value })
                    }
                  />
                </label>
                <button type="submit" disabled={addNpcMutation.isPending}>
                  {addNpcMutation.isPending ? "Adding..." : "Add NPC combatant"}
                </button>
              </form>
            </div>
          </div>
        </section>

        <section className="card sidebar-card">
          <h2>Encounter cleanup</h2>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={confirmClearTracker}
              onChange={(event) => setConfirmClearTracker(event.currentTarget.checked)}
            />
            Confirm clear tracker
          </label>
          <button
            type="button"
            className="ghost-button"
            onClick={() => clearCombatMutation.mutate()}
            disabled={!confirmClearTracker || clearCombatMutation.isPending}
          >
            {clearCombatMutation.isPending ? "Clearing..." : "Clear tracker"}
          </button>
        </section>
      </section>
    );
  };

  const renderPlayerWorkspace = () => (
    <section className="combat-pc-workspace">
      <div className="section-heading">
        <div>
          <p className="meta">Selected PC workspace</p>
          <h2>{selectedPlayerCharacter?.name ?? "No tracked PC in combat"}</h2>
        </div>
        {payload?.player_character_targets.length ? (
          <div className="combat-target-list">
            {payload.player_character_targets.map((target) => (
              <React.Fragment key={target.combatant_id}>
                <button
                  type="button"
                  className={target.is_selected ? "button-link" : "ghost-button"}
                  onClick={() => selectCombatant(target.combatant_id)}
                >
                  {target.name}
                </button>
                {target.subtitle ? <p className="meta">{target.subtitle}</p> : null}
              </React.Fragment>
            ))}
          </div>
        ) : null}
      </div>
      {selectedCharacterSlug ? (
        <CharacterPane
          campaignSlug={campaignSlug}
          initialCharacterSlug={selectedCharacterSlug}
          surface="combat"
          onSelectedCharacterChange={selectCharacterTarget}
        />
      ) : (
        <section className="card auth-card">
          <h2>No tracked player character available</h2>
          <p>
            There is not currently a tracked player character you can open from combat.
            Once a DM adds your character to the tracker, it will appear here.
          </p>
        </section>
      )}
    </section>
  );

  return (
    <>
      <section className="hero compact combat-hero">
        <p className="eyebrow">
          {effectiveCombatView === "status"
            ? "DM status"
            : effectiveCombatView === "controls"
              ? "Encounter controls"
              : "Combat tracker"}
        </p>
        <h1>
          {effectiveCombatView === "status"
            ? "DM status"
            : effectiveCombatView === "controls"
              ? "Encounter controls"
              : "Combat"}
        </h1>
        <p className="lede">
          {effectiveCombatView === "status" || effectiveCombatView === "controls"
            ? "Encounter setup, seeding, cleanup, and authority changes."
            : selectedPlayerCharacter
              ? "Keep your tracked character open as your in-combat workspace."
              : "Live encounter tracker."}
        </p>
        {canManageCombat && effectiveCombatView !== "player" ? renderCombatViewSwitch() : null}
      </section>

      <ApiErrorNotice
        isLoading={combatQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}

      {payload && !payload.combat_system_supported ? (
        <section className="card auth-card">
          <h2>Combat tracker not configured for {payload.campaign.system || "this system"} yet</h2>
          <p>
            This route is a placeholder for the campaign system lane. The current combat tracker is
            DND-5E-only, so no encounter automation is available here for {payload.campaign.system || "this system"} yet.
          </p>
          <div className="hero-actions">
            <a className="button-link" href={payload.links?.flask_campaign_url || `/campaigns/${encodeURIComponent(campaignSlug)}`}>
              Open Campaign Home
            </a>
            {payload.links?.flask_characters_url ? (
              <a className="ghost-button" href={payload.links.flask_characters_url}>
                Open Characters
              </a>
            ) : null}
            {payload.links?.flask_session_url ? (
              <a className="ghost-button" href={payload.links.flask_session_url}>
                Open Session
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {payload?.combat_system_supported ? (
        <>
          <section className="combat-summary-band" aria-label="Encounter summary">
            <article>
              <span className="meta">Round</span>
              <strong>{tracker?.round_number ?? 1}</strong>
            </article>
            <article>
              <span className="meta">Current turn</span>
              <strong>{tracker?.current_turn_label || "None"}</strong>
            </article>
            <article>
              <span className="meta">Combatants</span>
              <strong>{tracker?.combatant_count ?? 0}</strong>
            </article>
          </section>

          {tracker?.combatants.length ? (
            <section className="combat-carousel" aria-label="Combatant carousel">
              <div className="section-heading">
                <div>
                  <h2>Turn Order</h2>
                  <p className="meta">Initiative is pinned here while the main panel shows your tracked character.</p>
                </div>
              </div>
              <div className="combat-carousel-track">
                {tracker.combatants.map((combatant) => renderCombatantCard(combatant))}
              </div>
              <div className="combat-turn-order-jump">
                <label className="combat-turn-order-jump__label" htmlFor="combat-turn-order-jump-select">
                  Jump to combatant
                </label>
                <select
                  id="combat-turn-order-jump-select"
                  className="combat-turn-order-jump__select"
                  value={selectedCombatant?.id ?? ""}
                  onChange={(event) => selectCombatant(Number(event.currentTarget.value))}
                >
                  {tracker.combatants.map((combatant) => (
                    <option key={combatant.id} value={combatant.id}>
                      {combatant.name} - turn {combatant.turn_value}
                    </option>
                  ))}
                </select>
              </div>
            </section>
          ) : (
            <section className="card">
              <h3>No combatants</h3>
              <p>The tracker is empty. Use the Encounter controls or DM controls to seed the encounter for now.</p>
            </section>
          )}

          {selectedCombatant ? (
            <section className="combat-selected-snapshot card combat-character-snapshot">
              <div className="section-heading">
                <div>
                  <p className="card-kicker">{selectedCombatantKicker}</p>
                  <h2>{selectedCombatant.name}</h2>
                  {selectedCombatantMeta ? (
                    <p className="meta">{selectedCombatantMeta}</p>
                  ) : null}
                </div>
                <div className="combatant-badges">
                  <span className="combat-badge">Round {tracker?.round_number ?? 1}</span>
                  <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
                  {selectedCombatant.initiative_bonus_label !== "0" ? (
                    <span className="combat-badge combat-badge--muted">Init {selectedCombatant.initiative_bonus_label}</span>
                  ) : null}
                  {selectedCombatant.is_current_turn ? (
                    <span className="combat-badge combat-badge--active">Current turn</span>
                  ) : null}
                </div>
              </div>
              {selectedCombatant.show_detail ? (
                <div className="combat-selected-snapshot__stats">
                  <span>HP {readNumber(selectedCombatant.current_hp)} / {readNumber(selectedCombatant.max_hp)}</span>
                  <span>Move {readNumber(selectedCombatant.movement_remaining)} / {readNumber(selectedCombatant.movement_total)}</span>
                  <span>{selectedCombatant.has_action ? "Action" : "No action"}</span>
                  <span>{selectedCombatant.has_bonus_action ? "Bonus" : "No bonus"}</span>
                  <span>{selectedCombatant.has_reaction ? "Reaction" : "No reaction"}</span>
                </div>
              ) : (
                <p className="meta">Detailed stats are currently hidden from players.</p>
              )}
            </section>
          ) : null}

          {effectiveCombatView === "status" ? renderDmStatus() : null}
          {effectiveCombatView === "controls" ? renderDmControls() : null}
          {effectiveCombatView === "player" ? renderPlayerWorkspace() : null}
        </>
      ) : null}
    </>
  );
}

function SessionPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/session",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { setAuthRequired } = useApiClient();
  const { apiClient } = useApiClient();
  const [activePane, setActivePane] = useState<PaneName>("session");

  const sessionQuery = useQuery({
    queryKey: ["session", resolvedCampaignSlug],
    queryFn: async () => {
      const previous = queryClient.getQueryData<SessionPayload>(["session", resolvedCampaignSlug]);
      const response = await apiClient.getSessionLiveState(
        resolvedCampaignSlug,
        previous
          ? {
              sessionRevision: previous.session_revision,
              sessionViewToken: previous.session_view_token,
            }
          : undefined,
      );
      const resolution = resolveSessionLivePayload(previous, response);
      if (resolution.state === "needs-refresh") {
        return apiClient.getSession(resolvedCampaignSlug);
      }
      return resolution.payload;
    },
    enabled: Boolean(resolvedCampaignSlug),
    refetchInterval: (query) => {
      return query.state.data?.active_session?.is_active ? 3000 : 8000;
    },
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sessionQuery.error)) {
      setAuthRequired(true);
    }
  }, [sessionQuery.error, setAuthRequired]);

  const payload = sessionQuery.data;
  const canManage = payload?.permissions.can_manage_session ?? false;
  const sessionIsActive = Boolean(payload?.active_session?.is_active);
  const sessionStatusLabel = sessionIsActive ? "Session active" : "Session inactive";

  useEffect(() => {
    setActivePane((previousActivePane) => coerceSessionPane(previousActivePane, canManage));
  }, [canManage]);

  const paneError = getApiErrorMessage(sessionQuery.error);

  return (
    <section className="session-page-shell">
      <section className="hero compact session-hero">
        <p className="eyebrow">Session Workspace</p>
        <div className="session-hero__title-row">
          <h1>Session</h1>
          <span
            className={
              sessionIsActive
                ? "session-hero__status session-hero__status--active"
                : "session-hero__status session-hero__status--inactive"
            }
            data-session-header-status
          >
            <span className="session-hero__status-dot" aria-hidden="true" />
            {sessionStatusLabel}
          </span>
        </div>
        <p className="lede">Live play workspace.</p>
        <div className="hero-actions session-tab-strip">
          <button
            type="button"
            className={activePane === "session" ? "tab-button button-link" : "tab-button ghost-button"}
            onClick={() => setActivePane("session")}
          >
            Session
          </button>
          <button
            type="button"
            className={activePane === "character" ? "tab-button button-link" : "tab-button ghost-button"}
            onClick={() => setActivePane("character")}
          >
            Character
          </button>
          {canManage ? (
            <button
              type="button"
              className={activePane === "dm" ? "tab-button button-link" : "tab-button ghost-button"}
              onClick={() => setActivePane("dm")}
            >
              DM
            </button>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice
        isLoading={sessionQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />

      <div className="pane-stack">
        <div className={activePane === "session" ? "pane pane-visible" : "pane pane-hidden"}>
          <SessionPane
            campaignSlug={resolvedCampaignSlug}
            payload={payload}
            refetch={() => sessionQuery.refetch()}
            setAuthRequired={setAuthRequired}
          />
        </div>
        <div className={activePane === "character" ? "pane pane-visible" : "pane pane-hidden"}>
          <CharacterPane campaignSlug={resolvedCampaignSlug} />
        </div>
        {canManage ? (
          <div className={activePane === "dm" ? "pane pane-visible" : "pane pane-hidden"}>
            <DmPane
              campaignSlug={resolvedCampaignSlug}
              payload={payload}
              refetch={() => sessionQuery.refetch()}
              setAuthRequired={setAuthRequired}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}

const rootRoute = createRootRoute({
  component: AppShell,
});

const campaignsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: CampaignListPage,
});

const accountSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: AccountSettingsPage,
});

const adminDashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: AdminDashboardPage,
});

const adminUserDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users/$userId",
  component: AdminUserDetailPage,
});

const campaignHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug",
  component: WikiHomePage,
});

const campaignHelpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/help",
  component: CampaignHelpPage,
});

const campaignControlRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/control",
  component: CampaignControlPage,
});

const campaignWikiSectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/sections/$sectionSlug",
  component: WikiSectionPage,
});

const campaignWikiPageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/pages/$",
  component: WikiArticlePage,
});

const campaignSystemsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems",
  component: SystemsIndexPage,
});

const campaignSystemsSourceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId",
  component: SystemsSourcePage,
});

const campaignSystemsSourceCategoryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType",
  component: SystemsSourceCategoryPage,
});

const campaignSystemsEntryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/entries/$entrySlug",
  component: SystemsEntryPage,
});

const campaignCharacterRosterRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters",
  component: CharacterRosterPage,
});

const campaignCharacterCreateRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/new",
  component: CharacterCreatePage,
});

const campaignCharacterXianxiaManualImportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/import/xianxia-manual",
  component: CharacterXianxiaManualImportPage,
});

const campaignCharacterAdvancedEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/edit",
  component: CharacterAdvancedEditorPage,
});

const campaignCharacterRetrainingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/retraining",
  component: CharacterRetrainingPage,
});

const campaignCharacterLevelUpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/level-up",
  component: CharacterLevelUpPage,
});

const campaignCharacterProgressionRepairRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair",
  component: CharacterProgressionRepairPage,
});

const campaignCharacterCultivationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation",
  component: CharacterCultivationPage,
});

const campaignCharacterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug",
  component: CharacterDetailPage,
});

const campaignCombatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/combat",
  component: CombatPage,
});

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const campaignDmContentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/dm-content",
  component: DmContentPage,
});

const routeTree = rootRoute.addChildren([
  campaignsRoute,
  accountSettingsRoute,
  adminDashboardRoute,
  adminUserDetailRoute,
  campaignHomeRoute,
  campaignHelpRoute,
  campaignControlRoute,
  campaignWikiSectionRoute,
  campaignWikiPageRoute,
  campaignSystemsRoute,
  campaignSystemsSourceRoute,
  campaignSystemsSourceCategoryRoute,
  campaignSystemsEntryRoute,
  campaignCharacterRosterRoute,
  campaignCharacterCreateRoute,
  campaignCharacterXianxiaManualImportRoute,
  campaignCharacterAdvancedEditorRoute,
  campaignCharacterRetrainingRoute,
  campaignCharacterLevelUpRoute,
  campaignCharacterProgressionRepairRoute,
  campaignCharacterCultivationRoute,
  campaignCharacterDetailRoute,
  campaignCombatRoute,
  campaignSessionRoute,
  campaignDmContentRoute,
]);
const router = createRouter({
  routeTree,
  basepath: "/app-next",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (root !== null) {
  createRoot(root).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
