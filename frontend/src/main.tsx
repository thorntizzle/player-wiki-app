import React, { useState, useEffect, useMemo, useContext, createContext, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Link,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  useLocation,
  useParams,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FocusEvent, FormEvent } from "react";
import "./styles.css";
import {
  CampaignApiClient,
  apiErrorMessage,
  isApiError,
} from "./api/client";
import type {
  AdminAssignment,
  AdminAuditEvent,
  AdminDashboardResponse,
  AdminInvitePayload,
  AdminMembership,
  AdminUserDetailResponse,
  CampaignEntry,
  AccountSettingsUpdatePayload,
  CampaignControlResponse,
  CampaignControlVisibilityRow,
  CharacterAdvancedEditorContext,
  CharacterCultivationContext,
  CharacterCultivationStatRow,
  CharacterEditorChoiceField,
  CharacterEditorEquipmentRow,
  CharacterEditorFeatureRow,
  CharacterEditorField,
  CharacterEditorRecoverablePenaltyRow,
  CharacterBuilderOption,
  CharacterCreateContextResponse,
  CharacterCreateSubmitPayload,
  CharacterCurrencyPatchPayload,
  CharacterDndCreateContext,
  CharacterDndChoiceField,
  CampaignHelpResponse,
  CharacterDetailResponse,
  CharacterEquipmentRow,
  CharacterEquipmentStatePatchPayload,
  CharacterFeatureStatePatchPayload,
  CharacterInventoryPatchPayload,
  CharacterPresentedInventoryItem,
  CharacterPresentedSpell,
  CharacterPresentedXianxia,
  CharacterLevelUpContext,
  CharacterLevelUpPayload,
  CharacterProgressionRepairContext,
  CharacterProgressionRepairPayload,
  CharacterRetrainingContext,
  CharacterRetrainingPayload,
  CampaignVisibilityMap,
  CharacterPortraitUpsertPayload,
  CharacterRecord,
  CharacterXianxiaDaoUseRecordPayload,
  CharacterXianxiaDaoUseRequestPayload,
  CharacterXianxiaInventoryItem,
  CharacterXianxiaInventoryItemPayload,
  CharacterXianxiaManualImportContext,
  CharacterXianxiaManualImportRow,
  UserProfile,
  CharacterXianxiaNamedRecord,
  CharacterNotesPatchPayload,
  CharacterResourcePatchPayload,
  CharacterRestApplyResponse,
  CharacterRestPreviewResponse,
  CharacterSpellSlotsPatchPayload,
  CharacterSummary,
  CharacterVitalsPatchPayload,
  CharacterXianxiaCreateContext,
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
  SessionArticleCreatePayloadManual,
  SessionArticleCreatePayloadUpload,
  SessionArticleCreatePayloadWiki,
  SessionArticleSourceResult,
  SessionArticleUpdatePayload,
  SessionDmPassiveScoreRow,
  SessionLogSummary,
  SessionMessage,
  SessionPayload,
  SessionMessagePostPayload,
  SessionMessageRecipientPlayerChoice,
  CampaignReferenceSearchResult,
  SystemsEntryResponse,
  SystemsEntrySummary,
  SystemsIndexResponse,
  SystemsRulesReferenceResult,
  SystemsSourceBrowseGroup,
  SystemsSourceCategoryResponse,
  SystemsSourceResponse,
  WikiHomeResponse,
  WikiPageDetail,
  WikiPageResponse,
  WikiPageSummary,
  WikiSectionResponse,
  WikiSubsectionGroup,
} from "./api/types";
import {
  coerceSessionPane,
  isAuthRequiredFromError as isAuthError,
  resolveSessionLivePayload,
  type SessionRoutePane,
} from "./sessionRouteState";

interface ApiMessageEnvelope {
  status: number;
  message: string;
}

interface EmbeddedImageInput {
  filename: string;
  data_base64: string;
  media_type: string;
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

interface DetailFact {
  label: string;
  value: string;
}

interface CharacterDetailDialogState {
  eyebrow: string;
  title: string;
  html: string;
  notes?: string;
  href?: string;
  facts?: DetailFact[];
  badges?: string[];
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
type ArticleMode = "manual" | "upload" | "wiki";
type CombatView = "player" | "status" | "controls";

interface ManualArticleDraftState {
  title: string;
  body: string;
  image: EmbeddedImageInput | null;
  imageAltText: string;
  imageCaption: string;
}

function buildEmptyManualArticleDraft(): ManualArticleDraftState {
  return {
    title: "",
    body: "",
    image: null,
    imageAltText: "",
    imageCaption: "",
  };
}

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

interface ApiClientContextValue {
  apiClient: CampaignApiClient;
  apiToken: string;
  setApiToken: (token: string) => void;
  authRequired: boolean;
  setAuthRequired: (required: boolean) => void;
  preferredFrontendMode: FrontendMode;
  user: UserProfile | null;
}

type FrontendMode = "flask" | "gen2";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2500,
      refetchOnWindowFocus: false,
    },
  },
});

const ApiClientContext = createContext<ApiClientContextValue | null>(null);

function useApiClient(): ApiClientContextValue {
  const context = useContext(ApiClientContext);
  if (context === null) {
    throw new Error("CampaignApiClient context is missing.");
  }
  return context;
}

function parseCampaignSlugFromPath(pathname: string): string {
  const appNextMatch = pathname.match(/^\/app-next\/campaigns\/([^/?#]+)/);
  if (appNextMatch && appNextMatch[1]) {
    return decodeURIComponent(appNextMatch[1]);
  }
  const routedMatch = pathname.match(/^\/campaigns\/([^/?#]+)/);
  if (routedMatch && routedMatch[1]) {
    return decodeURIComponent(routedMatch[1]);
  }
  return "";
}

function normalizeFrontendMode(value: string | null | undefined): FrontendMode {
  return value === "gen2" ? "gen2" : "flask";
}

function campaignRouteHref(campaignSlug: string, suffix = "", frontendMode: FrontendMode = "flask"): string {
  const normalizedCampaignSlug = encodeURIComponent(campaignSlug);
  const base = frontendMode === "gen2" ? `/app-next/campaigns/${normalizedCampaignSlug}` : `/campaigns/${normalizedCampaignSlug}`;
  const normalizedSuffix = suffix.replace(/^\/+/, "");
  return normalizedSuffix ? `${base}/${normalizedSuffix}` : base;
}

function preferredCampaignLink(href: string, campaignSlug: string, frontendMode: FrontendMode): string {
  if (!href) {
    return href;
  }
  const normalizedCampaignSlug = encodeURIComponent(campaignSlug);
  const legacyPrefix = `/campaigns/${normalizedCampaignSlug}/`;
  const legacyBase = `/campaigns/${normalizedCampaignSlug}`;
  const gen2Prefix = `/app-next/campaigns/${normalizedCampaignSlug}/`;
  const gen2Base = `/app-next/campaigns/${normalizedCampaignSlug}`;
  const preferredBase = campaignRouteHref(campaignSlug, "", frontendMode);
  if (href === legacyBase || href === gen2Base) {
    return preferredBase;
  }
  if (href.startsWith(legacyPrefix)) {
    return `${preferredBase}/${href.slice(legacyPrefix.length)}`;
  }
  if (href.startsWith(gen2Prefix)) {
    return `${preferredBase}/${href.slice(gen2Prefix.length)}`;
  }
  return href;
}

function campaignVisibilityCanAccess(visibility: CampaignVisibilityMap | undefined, scope: string): boolean {
  return Boolean(visibility?.[scope]?.can_access);
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function readString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function readNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function draftKey(...parts: Array<string | number | null | undefined>): string {
  return parts.map((part) => String(part ?? "")).join("::");
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

function characterNameFromRecord(character: CharacterRecord | undefined): string {
  return readString(asRecord(character?.definition?.profile).name, readString(character?.definition?.name, "Character"));
}

function classLevelTextFromRecord(character: CharacterRecord | undefined): string {
  return readString(asRecord(character?.definition?.profile).class_level_text);
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

type CharacterAuthoringValues = Record<string, string | string[]>;

function optionValue(option: CharacterBuilderOption): string {
  return String(option.value || option.slug || option.entry_key || option.key || "");
}

function optionLabel(option: CharacterBuilderOption): string {
  const value = optionValue(option);
  const label = option.label || option.title || option.name || value;
  return option.source_id ? `${label} (${option.source_id})` : label;
}

function draftString(values: CharacterAuthoringValues, key: string, fallback = ""): string {
  const value = values[key];
  if (Array.isArray(value)) {
    return value[0] ?? fallback;
  }
  return value ?? fallback;
}

function draftStringArray(values: CharacterAuthoringValues, key: string): string[] {
  const value = values[key];
  return Array.isArray(value) ? value : value ? [value] : [];
}

function stringFromUnknown(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) {
    return fallback;
  }
  return String(value);
}

function numberFromUnknown(value: unknown, fallback = 0): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function boolFromUnknown(value: unknown): boolean {
  return value === true || value === "true" || value === 1 || value === "1";
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function recordListFromUnknown(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.map(recordFromUnknown).filter((item) => Object.keys(item).length > 0)
    : [];
}

function updateAuthoringValue(
  setValues: React.Dispatch<React.SetStateAction<CharacterAuthoringValues>>,
  key: string,
  value: string | string[],
) {
  setValues((current) => ({ ...current, [key]: value }));
}

function selectOptions(options: CharacterBuilderOption[]) {
  return options.map((option) => {
    const value = optionValue(option);
    return (
      <option key={value || optionLabel(option)} value={value}>
        {optionLabel(option)}
      </option>
    );
  });
}

function editorValuesFromContext(context: CharacterAdvancedEditorContext | null | undefined): Record<string, string> {
  const values: Record<string, string> = {};
  if (!context) {
    return values;
  }
  const copyField = (field: CharacterEditorField | CharacterEditorChoiceField) => {
    if (field.name) {
      values[field.name] = String(("options" in field ? field.selected : field.value) ?? "");
    }
  };
  context.proficiency_fields?.forEach(copyField);
  context.reference_fields?.forEach(copyField);
  context.stat_adjustment_fields?.forEach(copyField);
  context.recoverable_penalty_rows?.forEach((row) => {
    values[`recoverable_penalty_id_${row.index}`] = row.id ?? "";
    values[`recoverable_penalty_source_${row.index}`] = row.source ?? "";
    values[`recoverable_penalty_target_${row.index}`] = row.target ?? "";
    values[`recoverable_penalty_amount_${row.index}`] = row.amount ?? "";
    values[`recoverable_penalty_notes_${row.index}`] = row.notes ?? "";
  });
  context.feature_rows?.forEach((row) => {
    values[`custom_feature_id_${row.index}`] = row.id ?? "";
    values[`custom_feature_name_${row.index}`] = row.name ?? "";
    values[`custom_feature_page_ref_${row.index}`] = row.page_ref ?? "";
    values[`custom_feature_activation_type_${row.index}`] = row.activation_type ?? "";
    values[`custom_feature_description_${row.index}`] = row.description_markdown ?? "";
    values[`custom_feature_resource_max_${row.index}`] = row.resource_max ?? "";
    values[`custom_feature_resource_reset_on_${row.index}`] = row.resource_reset_on ?? "";
    row.choice_fields?.forEach(copyField);
  });
  context.equipment_rows?.forEach((row) => {
    values[`manual_item_id_${row.index}`] = row.id ?? "";
    values[`manual_item_name_${row.index}`] = row.name ?? "";
    values[`manual_item_page_ref_${row.index}`] = row.page_ref ?? "";
    values[`manual_item_quantity_${row.index}`] = row.quantity ?? "";
    values[`manual_item_weight_${row.index}`] = row.weight ?? "";
    values[`manual_item_notes_${row.index}`] = row.notes ?? "";
  });
  return values;
}

function editorSelectOptions(options: CharacterBuilderOption[], emptyLabel?: string) {
  return (
    <>
      {emptyLabel ? <option value="">{emptyLabel}</option> : null}
      {selectOptions(options)}
    </>
  );
}

function CharacterPreviewList({ preview }: { preview: Record<string, unknown> }) {
  const facts = ([
    ["Class / level", preview.class_level_text],
    ["Max HP", preview.max_hp],
    ["Speed", preview.speed],
    ["Size", preview.size],
    ["Carrying", preview.carrying_capacity],
    ["Push / drag / lift", preview.push_drag_lift],
    ["Currency", preview.starting_currency],
  ] as Array<[string, unknown]>).filter(([, value]) => value !== undefined && value !== null && String(value).trim());
  const listSections = ([
    ["Saving throws", asStringArray(preview.saving_throws)],
    ["Languages", asStringArray(preview.languages)],
    ["Features", asStringArray(preview.features)],
    ["Resources", asStringArray(preview.resources)],
    ["Equipment", asStringArray(preview.equipment)],
    ["Attacks", asStringArray(preview.attacks)],
    ["Spells", asStringArray(preview.spells)],
  ] as Array<[string, string[]]>).filter(([, values]) => Array.isArray(values) && values.length);

  return (
    <aside className="sidebar character-authoring-sidebar">
      <section className="card sidebar-card">
        <h2>Preview</h2>
        {facts.length ? (
          <div className="builder-preview-list">
            {facts.map(([label, value]) => (
              <div key={label}>
                <span className="meta">{label}</span>
                <strong>{stringFromUnknown(value, "Not set")}</strong>
              </div>
            ))}
          </div>
        ) : (
          <p className="meta">Choose core options to populate the preview.</p>
        )}
      </section>
      {listSections.map(([label, values]) => (
        <section className="card sidebar-card character-authoring-preview-section" key={String(label)}>
          <h3>{label}</h3>
          <ul className="plain-list resource-preview-list">
            {values.map((item) => (
              <li key={`${label}-${item}`}>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}

function characterLevelUpValuesFromContext(context: CharacterLevelUpContext | null | undefined): CharacterAuthoringValues {
  const values: CharacterAuthoringValues = { ...(context?.values ?? {}) };
  if (!context) {
    return values;
  }
  values.advancement_mode = draftString(values, "advancement_mode", context.advancement_mode || "advance_existing");
  values.target_class_row_id = draftString(values, "target_class_row_id", context.target_class_row_id || "");
  values.new_class_slug = draftString(values, "new_class_slug");
  values.new_subclass_slug = draftString(values, "new_subclass_slug");
  values.subclass_slug = draftString(values, "subclass_slug");
  values.hp_gain = draftString(values, "hp_gain");
  context.choice_sections?.forEach((section) => {
    section.fields?.forEach((field) => {
      if (field.name && values[field.name] === undefined) {
        values[field.name] = field.selected ?? "";
      }
    });
  });
  return values;
}

function characterAuthoringStringValues(values: CharacterAuthoringValues): Record<string, string> {
  const payload: Record<string, string> = {};
  Object.entries(values).forEach(([key, value]) => {
    payload[key] = Array.isArray(value) ? String(value[0] ?? "") : String(value ?? "");
  });
  return payload;
}

function characterProgressionRepairValuesFromContext(
  context: CharacterProgressionRepairContext | null | undefined,
): CharacterAuthoringValues {
  const values: CharacterAuthoringValues = { ...(context?.values ?? {}) };
  context?.class_rows?.forEach((row) => {
    if (row.class_field_name && values[row.class_field_name] === undefined) {
      values[row.class_field_name] = row.class_selected ?? "";
    }
    if (row.subclass_field_name && values[row.subclass_field_name] === undefined) {
      values[row.subclass_field_name] = row.subclass_selected ?? "";
    }
  });
  context?.feat_rows?.forEach((row) => {
    if (row.name && values[row.name] === undefined) {
      values[row.name] = row.selected ?? "";
    }
  });
  context?.optionalfeature_rows?.forEach((row) => {
    if (row.name && values[row.name] === undefined) {
      values[row.name] = row.selected ?? "";
    }
  });
  context?.spell_rows?.forEach((row) => {
    if (row.class_row_field_name && values[row.class_row_field_name] === undefined) {
      values[row.class_row_field_name] = row.class_row_selected ?? "";
    }
    if (row.field_name && values[row.field_name] === undefined) {
      values[row.field_name] = row.selected ?? "";
    }
  });
  return values;
}

function characterRetrainingValuesFromContext(context: CharacterRetrainingContext | null | undefined): CharacterAuthoringValues {
  const values: CharacterAuthoringValues = { ...(context?.values ?? {}) };
  context?.feature_rows?.forEach((row) => {
    row.choice_fields?.forEach((field) => {
      if (field.name && values[field.name] === undefined) {
        values[field.name] = field.selected ?? "";
      }
    });
  });
  return values;
}

function CharacterLevelUpPreviewList({ preview }: { preview: Record<string, unknown> }) {
  const facts = ([
    ["Class", preview.class_level_text],
    ["Max HP", preview.max_hp],
    ["Carry", preview.carrying_capacity],
    ["Push / Drag / Lift", preview.push_drag_lift],
  ] as Array<[string, unknown]>).filter(([, value]) => value !== undefined && value !== null && String(value).trim());
  const listSections = ([
    ["Class Rows", asStringArray(preview.class_rows)],
    ["Gained Features", asStringArray(preview.gained_features)],
    ["Resources", asStringArray(preview.resources)],
    ["Attacks", asStringArray(preview.attacks)],
    ["Spell Slots", asStringArray(preview.spell_slots)],
    ["New Spells", asStringArray(preview.new_spells)],
  ] as Array<[string, string[]]>).filter(([, values]) => values.length);

  return (
    <aside className="sidebar character-authoring-sidebar">
      <section className="card sidebar-card">
        <h2>Preview</h2>
        {facts.length ? (
          <div className="builder-preview-list">
            {facts.map(([label, value]) => (
              <div key={label}>
                <span className="meta">{label}</span>
                <strong>{stringFromUnknown(value, "Not set")}</strong>
              </div>
            ))}
          </div>
        ) : null}
      </section>
      {listSections.map(([label, values]) => (
        <section className="card sidebar-card character-authoring-preview-section" key={label}>
          <h3>{label}</h3>
          <ul className="plain-list resource-preview-list">
            {values.map((item) => (
              <li key={`${label}-${item}`}>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}

function isDndCreateContext(value: CharacterCreateContextResponse["create"] | undefined): value is CharacterDndCreateContext {
  return Boolean(value && value.lane === "dnd5e");
}

function isXianxiaCreateContext(value: CharacterCreateContextResponse["create"] | undefined): value is CharacterXianxiaCreateContext {
  return Boolean(value && value.lane === "xianxia");
}

function CharacterDndChoiceSelect({
  field,
  draftValues,
  setDraftValues,
  refreshContext,
}: {
  field: CharacterDndChoiceField;
  draftValues: CharacterAuthoringValues;
  setDraftValues: React.Dispatch<React.SetStateAction<CharacterAuthoringValues>>;
  refreshContext: (values?: CharacterAuthoringValues) => void;
}) {
  const value = draftString(draftValues, field.name, field.selected || "");
  return (
    <label className="field">
      <span>{field.label}</span>
      <select
        name={field.name}
        value={value}
        onChange={(event) => {
          const nextValues = { ...draftValues, [field.name]: event.currentTarget.value };
          setDraftValues(nextValues);
          refreshContext(nextValues);
        }}
      >
        <option value="">Choose an option</option>
        {selectOptions(field.options ?? [])}
      </select>
      {field.help_text ? <small>{field.help_text}</small> : null}
    </label>
  );
}

function CharacterCreatePage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/characters/new",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [contextValues, setContextValues] = useState<CharacterAuthoringValues>({});
  const [statusMessage, setStatusMessage] = useState("");

  const createQuery = useQuery({
    queryKey: ["character-create", resolvedCampaignSlug, JSON.stringify(contextValues)],
    queryFn: () => apiClient.getCharacterCreateContext(resolvedCampaignSlug, contextValues),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(createQuery.error)) {
      setAuthRequired(true);
    }
  }, [createQuery.error, setAuthRequired]);

  useEffect(() => {
    const create = createQuery.data?.create;
    if (!create || Object.keys(draftValues).length) {
      return;
    }
    if (isDndCreateContext(create)) {
      setDraftValues({ ...create.values });
    } else if (isXianxiaCreateContext(create)) {
      const nextValues: CharacterAuthoringValues = {};
      for (const field of [...create.attribute_fields, ...create.effort_fields, ...create.energy_fields, ...create.trained_skill_fields]) {
        nextValues[field.input_name] = field.value;
      }
      for (const field of create.martial_art_fields) {
        nextValues[field.art_input_name] = field.selected_slug;
        nextValues[field.rank_input_name] = field.selected_rank;
      }
      nextValues[create.manual_armor_field.input_name] = create.manual_armor_field.value;
      nextValues[create.dao_field.input_name] = create.dao_field.value;
      setDraftValues(nextValues);
    }
  }, [createQuery.data, draftValues]);

  const createMutation = useMutation({
    mutationFn: (payload: CharacterCreateSubmitPayload) => apiClient.createCharacter(resolvedCampaignSlug, payload),
    onSuccess: (payload) => {
      setStatusMessage(payload.message);
      if (payload.links.character_url) {
        window.location.assign(payload.links.character_url);
      }
    },
  });

  const error = getApiErrorMessage(createQuery.error || createMutation.error);
  const data = createQuery.data;
  const create = data?.create;

  const refreshContext = (values: CharacterAuthoringValues = draftValues) => {
    setContextValues({ ...values });
  };

  const submitCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatusMessage("");
    createMutation.mutate({ values: draftValues });
  };

  const updateValue = (key: string, value: string | string[], refresh = false) => {
    const nextValues = { ...draftValues, [key]: value };
    setDraftValues(nextValues);
    if (refresh) {
      refreshContext(nextValues);
    }
  };

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="meta">Character authoring</p>
        <h1>{create?.lane === "xianxia" ? "Create Xianxia Character" : "Create Character"}</h1>
        <p className="lede">Create native character records through the same campaign system lane used by the Flask builder.</p>
        <div className="hero-actions character-authoring-hero-actions">
          {data?.links.gen2_roster_url ? (
            <a className="ghost-button" href={data.links.gen2_roster_url}>
              Back to roster
            </a>
          ) : null}
          {data?.links.gen2_import_xianxia_url ? (
            <a className="ghost-button" href={data.links.gen2_import_xianxia_url}>
              Import existing
            </a>
          ) : null}
        </div>
      </section>
      <ApiErrorNotice isLoading={createQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {isDndCreateContext(create) ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitCreate}>
            {!create.builder_ready ? (
              <p className="status status-warning">The builder needs a supported base class plus enabled Systems species and backgrounds before it can create characters in this campaign.</p>
            ) : null}
            <section className="builder-section">
              <h2>Identity</h2>
              <div className="builder-field-grid">
                {[
                  ["name", "Character Name", "Zigzag Blackscar"],
                  ["character_slug", "Character Slug", "Auto-generated from name if blank"],
                  ["alignment", "Alignment", "Neutral Good"],
                  ["experience_model", "Experience Model", "Milestone"],
                ].map(([key, label, placeholder]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input
                      type="text"
                      name={key}
                      value={draftString(draftValues, key, create.values[key] || "")}
                      placeholder={placeholder}
                      onChange={(event) => updateValue(key, event.currentTarget.value)}
                    />
                  </label>
                ))}
              </div>
            </section>

            <section className="builder-section">
              <h2>Core Build</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Class</span>
                  <select
                    name="class_slug"
                    value={draftString(draftValues, "class_slug", create.values.class_slug || "")}
                    onChange={(event) => updateValue("class_slug", event.currentTarget.value, true)}
                  >
                    <option value="">Choose a class</option>
                    {selectOptions(create.class_options)}
                  </select>
                </label>
                {create.subclass_options.length || create.requires_subclass ? (
                  <label className="field">
                    <span>Subclass</span>
                    <select
                      name="subclass_slug"
                      value={draftString(draftValues, "subclass_slug", create.values.subclass_slug || "")}
                      onChange={(event) => updateValue("subclass_slug", event.currentTarget.value, true)}
                    >
                      <option value="">{create.requires_subclass ? "Choose a subclass" : "No subclass"}</option>
                      {selectOptions(create.subclass_options)}
                    </select>
                  </label>
                ) : null}
                <label className="field">
                  <span>Species</span>
                  <select
                    name="species_slug"
                    value={draftString(draftValues, "species_slug", create.values.species_slug || "")}
                    onChange={(event) => updateValue("species_slug", event.currentTarget.value, true)}
                  >
                    <option value="">Choose a species</option>
                    {selectOptions(create.species_options)}
                  </select>
                </label>
                <label className="field">
                  <span>Background</span>
                  <select
                    name="background_slug"
                    value={draftString(draftValues, "background_slug", create.values.background_slug || "")}
                    onChange={(event) => updateValue("background_slug", event.currentTarget.value, true)}
                  >
                    <option value="">Choose a background</option>
                    {selectOptions(create.background_options)}
                  </select>
                </label>
              </div>
            </section>

            <section className="builder-section">
              <h2>Ability Scores</h2>
              <div className="builder-ability-grid">
                {[
                  ["str", "Strength"],
                  ["dex", "Dexterity"],
                  ["con", "Constitution"],
                  ["int", "Intelligence"],
                  ["wis", "Wisdom"],
                  ["cha", "Charisma"],
                ].map(([key, label]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input
                      type="number"
                      name={key}
                      min={1}
                      max={30}
                      value={draftString(draftValues, key, create.values[key] || "10")}
                      onChange={(event) => updateValue(key, event.currentTarget.value)}
                    />
                  </label>
                ))}
              </div>
            </section>

            {create.choice_sections.map((section) => (
              <section className="builder-section" key={section.title}>
                <h2>{section.title}</h2>
                <div className="builder-field-grid">
                  {section.fields.map((field) => (
                    <CharacterDndChoiceSelect
                      key={field.name}
                      field={field}
                      draftValues={draftValues}
                      setDraftValues={setDraftValues}
                      refreshContext={refreshContext}
                    />
                  ))}
                </div>
              </section>
            ))}

            <div className="builder-actions">
              <button type="button" className="ghost-button" onClick={() => refreshContext()}>
                Refresh options
              </button>
              <button type="submit" disabled={!create.builder_ready || createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create character"}
              </button>
            </div>
          </form>
          <CharacterPreviewList preview={create.preview} />
        </div>
      ) : null}

      {isXianxiaCreateContext(create) ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitCreate}>
            <section className="builder-section">
              <h2>Identity</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Character Name</span>
                  <input type="text" name="name" value={draftString(draftValues, "name")} onChange={(event) => updateValue("name", event.currentTarget.value)} required />
                </label>
                <label className="field">
                  <span>Character Slug</span>
                  <input type="text" name="character_slug" value={draftString(draftValues, "character_slug")} onChange={(event) => updateValue("character_slug", event.currentTarget.value)} />
                </label>
              </div>
            </section>

            {([
              { title: "Attributes", fields: create.attribute_fields, inputType: "number" },
              { title: "Efforts", fields: create.effort_fields, inputType: "number" },
              { title: "Energies", fields: create.energy_fields, inputType: "number" },
              { title: "Trained Skills", fields: create.trained_skill_fields, inputType: "text" },
            ] as Array<{ title: string; fields: CharacterXianxiaCreateContext["attribute_fields"]; inputType: "number" | "text" }>).map(({ title, fields, inputType }) => (
              <section className="builder-section" key={title}>
                <h2>{title}</h2>
                <div className="builder-field-grid">
                  {fields.map((field) => (
                    <label className="field" key={field.input_name}>
                      <span>{field.label}</span>
                      <input
                        type={inputType}
                        name={field.input_name}
                        min={field.min ?? 0}
                        max={field.max}
                        step={1}
                        value={draftString(draftValues, field.input_name, field.value)}
                        onChange={(event) => updateValue(field.input_name, event.currentTarget.value)}
                        required
                      />
                    </label>
                  ))}
                </div>
              </section>
            ))}

            <section className="builder-section">
              <h2>Starting Martial Arts</h2>
              <div className="builder-field-grid">
                {create.martial_art_fields.map((field) => (
                  <React.Fragment key={field.index}>
                    <label className="field">
                      <span>Martial Art {field.index}</span>
                      <select
                        name={field.art_input_name}
                        value={draftString(draftValues, field.art_input_name, field.selected_slug)}
                        onChange={(event) => updateValue(field.art_input_name, event.currentTarget.value)}
                      >
                        <option value="">Choose Martial Art</option>
                        {selectOptions(create.martial_art_options)}
                      </select>
                    </label>
                    <label className="field">
                      <span>Starting Rank {field.index}</span>
                      <select
                        name={field.rank_input_name}
                        value={draftString(draftValues, field.rank_input_name, field.selected_rank)}
                        onChange={(event) => updateValue(field.rank_input_name, event.currentTarget.value)}
                      >
                        <option value="">Choose Rank</option>
                        {selectOptions(create.martial_art_rank_choices)}
                      </select>
                    </label>
                  </React.Fragment>
                ))}
              </div>
            </section>

            <section className="builder-section">
              <h2>GM Grants</h2>
              <div className="builder-field-grid">
                {[create.manual_armor_field, create.dao_field].map((field) => (
                  <label className="field" key={field.input_name}>
                    <span>{field.input_name === "dao_current" ? "Starting Dao" : "Manual Armor Bonus"}</span>
                    <input
                      type="number"
                      name={field.input_name}
                      min={field.min ?? 0}
                      max={field.max}
                      step={1}
                      value={draftString(draftValues, field.input_name, field.value)}
                      onChange={(event) => updateValue(field.input_name, event.currentTarget.value)}
                    />
                  </label>
                ))}
                {create.generic_technique_options.length ? (
                  <label className="field">
                    <span>GM-Granted Generic Techniques</span>
                    <select
                      name={create.gm_granted_generic_technique_input}
                      multiple
                      size={6}
                      value={draftStringArray(draftValues, create.gm_granted_generic_technique_input)}
                      onChange={(event) =>
                        updateValue(
                          create.gm_granted_generic_technique_input,
                          Array.from(event.currentTarget.selectedOptions).map((option) => option.value),
                        )
                      }
                    >
                      {selectOptions(create.generic_technique_options)}
                    </select>
                  </label>
                ) : null}
              </div>
            </section>

            <div className="builder-actions">
              <button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create character"}
              </button>
            </div>
          </form>
          <aside className="sidebar character-authoring-sidebar">
            <section className="card sidebar-card">
              <h2>Starting Defaults</h2>
              <div className="builder-preview-list">
                {Object.entries(create.defaults).map(([key, value]) => (
                  <div key={key}>
                    <span className="meta">{key.replace(/_/g, " ")}</span>
                    <strong>{stringFromUnknown(value)}</strong>
                  </div>
                ))}
              </div>
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function manualImportRows(context: CharacterXianxiaManualImportContext | undefined, rowCount: number, values: CharacterAuthoringValues): CharacterXianxiaManualImportRow[] {
  const baseRows = context?.martial_art_rows ?? [];
  const maxRows = Math.max(rowCount, baseRows.length, 3);
  return Array.from({ length: maxRows }, (_, offset) => {
    const index = offset + 1;
    const existing = baseRows.find((row) => row.index === index);
    return {
      index,
      slug_input_name: `martial_art_${index}_slug`,
      name_input_name: `martial_art_${index}_name`,
      rank_input_name: `martial_art_${index}_rank`,
      teacher_input_name: `martial_art_${index}_teacher`,
      breakthrough_input_name: `martial_art_${index}_breakthrough`,
      notes_input_name: `martial_art_${index}_notes`,
      selected_slug: draftString(values, `martial_art_${index}_slug`, existing?.selected_slug || ""),
      name: draftString(values, `martial_art_${index}_name`, existing?.name || ""),
      rank: draftString(values, `martial_art_${index}_rank`, existing?.rank || ""),
      teacher: draftString(values, `martial_art_${index}_teacher`, existing?.teacher || ""),
      breakthrough: draftString(values, `martial_art_${index}_breakthrough`, existing?.breakthrough || ""),
      notes: draftString(values, `martial_art_${index}_notes`, existing?.notes || ""),
    };
  });
}

function CharacterXianxiaManualImportPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/characters/import/xianxia-manual",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [contextValues, setContextValues] = useState<Record<string, string>>({});
  const [manualContext, setManualContext] = useState<CharacterXianxiaManualImportContext | null>(null);
  const [rowCount, setRowCount] = useState(3);
  const [statusMessage, setStatusMessage] = useState("");

  const importQuery = useQuery({
    queryKey: ["character-xianxia-import", resolvedCampaignSlug, JSON.stringify(contextValues)],
    queryFn: () => apiClient.getXianxiaManualImportContext(resolvedCampaignSlug, contextValues),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(importQuery.error)) {
      setAuthRequired(true);
    }
  }, [importQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!manualContext && importQuery.data?.import_context) {
      setManualContext(importQuery.data.import_context);
    }
  }, [importQuery.data, manualContext]);

  const importMutation = useMutation({
    mutationFn: ({ confirm }: { confirm: boolean }) =>
      apiClient.submitXianxiaManualImport(resolvedCampaignSlug, {
        values: Object.fromEntries(Object.entries(draftValues).map(([key, value]) => [key, Array.isArray(value) ? value.join("\n") : value])),
        confirm_import: confirm,
      }),
    onSuccess: (payload) => {
      setStatusMessage(payload.message || "");
      if ("character" in payload) {
        if (payload.links.character_url) {
          window.location.assign(payload.links.character_url);
        }
        return;
      }
      setManualContext(payload.import_context);
      setContextValues(payload.import_context.values);
    },
  });

  const context = manualContext || importQuery.data?.import_context;
  const links = importQuery.data?.links;
  const error = getApiErrorMessage(importQuery.error || importMutation.error);

  const updateValue = (key: string, value: string) => {
    updateAuthoringValue(setDraftValues, key, value);
  };

  const submitPreview = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatusMessage("");
    importMutation.mutate({ confirm: false });
  };

  const confirmImport = () => {
    setStatusMessage("");
    importMutation.mutate({ confirm: true });
  };

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="meta">Character importer</p>
        <h1>Import Existing Xianxia Character</h1>
        <p className="lede">Preview copied values, then create a normal native Xianxia sheet with SQLite-backed mutable state.</p>
        <div className="hero-actions character-authoring-hero-actions">
          {links?.gen2_roster_url ? (
            <a className="ghost-button" href={links.gen2_roster_url}>
              Back to roster
            </a>
          ) : null}
        </div>
      </section>
      <ApiErrorNotice isLoading={importQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}
      {context?.preview ? (
        <section className="card character-authoring-preview-card">
          <h2>Review Import</h2>
          <div className="builder-preview-list">
            {Object.entries(context.preview).map(([key, value]) => (
              <div key={key}>
                <span className="meta">{key.replace(/_/g, " ")}</span>
                <strong>{stringFromUnknown(value)}</strong>
              </div>
            ))}
          </div>
          <button type="button" onClick={confirmImport} disabled={importMutation.isPending}>
            {importMutation.isPending ? "Importing..." : "Confirm import"}
          </button>
        </section>
      ) : null}

      {context ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitPreview}>
            <section className="builder-section">
              <h2>Identity</h2>
              <div className="builder-field-grid">
                {[
                  ["name", "Character Name", ""],
                  ["character_slug", "Character Slug", ""],
                  ["reputation", "Reputation", "Unknown"],
                ].map(([key, label, fallback]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input type="text" name={key} value={draftString(draftValues, key, context.values[key] || fallback)} onChange={(event) => updateValue(key, event.currentTarget.value)} />
                  </label>
                ))}
                <label className="field">
                  <span>Realm</span>
                  <select name="realm" value={draftString(draftValues, "realm", context.values.realm || "Mortal")} onChange={(event) => updateValue("realm", event.currentTarget.value)}>
                    {context.realm_choices.map((realm) => (
                      <option key={realm} value={realm}>
                        {realm}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Honor</span>
                  <select name="honor" value={draftString(draftValues, "honor", context.values.honor || "Honorable")} onChange={(event) => updateValue("honor", event.currentTarget.value)}>
                    {context.honor_choices.map((honor) => (
                      <option key={honor} value={honor}>
                        {honor}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </section>

            {([
              { title: "Attributes", fields: context.attribute_fields },
              { title: "Efforts", fields: context.effort_fields },
            ] as Array<{ title: string; fields: CharacterXianxiaManualImportContext["attribute_fields"] }>).map(({ title, fields }) => (
              <section className="builder-section" key={title}>
                <h2>{title}</h2>
                <div className="builder-field-grid">
                  {fields.map((field) => (
                    <label className="field" key={field.input_name}>
                      <span>{field.label}</span>
                      <input type="number" name={field.input_name} value={draftString(draftValues, field.input_name, field.value)} step={1} onChange={(event) => updateValue(field.input_name, event.currentTarget.value)} />
                    </label>
                  ))}
                </div>
              </section>
            ))}

            <section className="builder-section">
              <h2>Resources</h2>
              <div className="builder-field-grid">
                {[
                  ["hp_max", "HP Max", "10"],
                  ["stance_max", "Stance Max", "10"],
                  ["manual_armor_bonus", "Manual Armor Bonus", "0"],
                  ["insight_available", "Insight Available", "0"],
                  ["insight_spent", "Insight Spent", "0"],
                  ["yin_max", "Yin Max", "1"],
                  ["yang_max", "Yang Max", "1"],
                  ["dao_max", "Dao Max", "3"],
                  ["coin", "Coin", "0"],
                  ["supply", "Supply", "0"],
                  ["spirit_stones", "Spirit Stones", "0"],
                ].map(([key, label, fallback]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input type="number" name={key} value={draftString(draftValues, key, context.values[key] || fallback)} step={1} onChange={(event) => updateValue(key, event.currentTarget.value)} />
                  </label>
                ))}
                {context.energy_fields.map((field) => (
                  <label className="field" key={field.max_input_name}>
                    <span>{field.label} Max</span>
                    <input type="number" name={field.max_input_name} value={draftString(draftValues, field.max_input_name, field.max_value)} step={1} onChange={(event) => updateValue(field.max_input_name, event.currentTarget.value)} />
                  </label>
                ))}
              </div>
            </section>

            <section className="builder-section">
              <h2>Skills</h2>
              <label className="field">
                <span>Trained Skills</span>
                <textarea name="trained_skills_text" rows={6} value={draftString(draftValues, "trained_skills_text", context.values.trained_skills_text || "")} onChange={(event) => updateValue("trained_skills_text", event.currentTarget.value)} />
              </label>
            </section>

            <section className="builder-section">
              <h2>Martial Arts</h2>
              <div className="manual-import-rows">
                {manualImportRows(context, rowCount, draftValues).map((row) => (
                  <article className="manual-import-row" key={row.index}>
                    <h3>Martial Art {row.index}</h3>
                    <div className="builder-field-grid">
                      <label className="field">
                        <span>Stored Martial Art</span>
                        <select name={row.slug_input_name} value={row.selected_slug} onChange={(event) => updateValue(row.slug_input_name, event.currentTarget.value)}>
                          <option value="">Unlinked/manual</option>
                          {selectOptions(context.martial_art_options)}
                        </select>
                      </label>
                      {[
                        [row.name_input_name, "Manual Name", row.name],
                        [row.rank_input_name, "Current Rank", row.rank],
                        [row.teacher_input_name, "Teacher", row.teacher],
                        [row.breakthrough_input_name, "Breakthrough", row.breakthrough],
                        [row.notes_input_name, "Notes", row.notes],
                      ].map(([key, label, value]) => (
                        <label className="field" key={key}>
                          <span>{label}</span>
                          <input type="text" name={key} value={value} onChange={(event) => updateValue(key, event.currentTarget.value)} />
                        </label>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
              <button type="button" className="ghost-button" onClick={() => setRowCount((current) => current + 1)}>
                Add Martial Art
              </button>
            </section>

            <section className="builder-section">
              <h2>Inventory And Notes</h2>
              <label className="field">
                <span>Manual Inventory</span>
                <textarea name="inventory_text" rows={8} value={draftString(draftValues, "inventory_text", context.values.inventory_text || "")} onChange={(event) => updateValue("inventory_text", event.currentTarget.value)} />
              </label>
              <label className="field">
                <span>Reference Notes</span>
                <textarea name="additional_notes_markdown" rows={5} value={draftString(draftValues, "additional_notes_markdown", context.values.additional_notes_markdown || "")} onChange={(event) => updateValue("additional_notes_markdown", event.currentTarget.value)} />
              </label>
              <label className="field">
                <span>Player Notes</span>
                <textarea name="player_notes_markdown" rows={5} value={draftString(draftValues, "player_notes_markdown", context.values.player_notes_markdown || "")} onChange={(event) => updateValue("player_notes_markdown", event.currentTarget.value)} />
              </label>
            </section>

            <div className="builder-actions">
              <button type="submit" disabled={importMutation.isPending}>
                {importMutation.isPending ? "Previewing..." : "Preview import"}
              </button>
            </div>
          </form>
          <aside className="sidebar character-authoring-sidebar">
            <section className="card sidebar-card">
              <h2>Available Martial Arts</h2>
              {context.martial_art_options.length ? (
                <ul className="plain-list resource-preview-list">
                  {context.martial_art_options.map((option) => (
                    <li key={optionValue(option)}>
                      <span>{optionLabel(option)}</span>
                      <strong>{option.available_rank_labels?.join(", ") || option.martial_art_style || optionValue(option)}</strong>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No enabled Martial Art Systems entries are available.</p>
              )}
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function CharacterAdvancedEditorPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/edit",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const editorQuery = useQuery({
    queryKey: ["character-advanced-editor", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterAdvancedEditor(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
  });

  const data = editorQuery.data;
  const editor = data?.editor ?? null;

  useEffect(() => {
    if (!editor || loadedRevision === editor.state_revision) {
      return;
    }
    setDraftValues(editorValuesFromContext(editor));
    setLoadedRevision(editor.state_revision);
    setErrorMessage(null);
  }, [editor, loadedRevision]);

  const updateDraftValue = (key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }));
  };

  const saveEditor = useMutation({
    mutationFn: () => {
      if (!editor) {
        throw new Error("The editor context has not loaded yet.");
      }
      return apiClient.updateCharacterAdvancedEditor(campaignSlug, characterSlug, {
        expected_revision: editor.state_revision,
        values: draftValues,
      });
    },
    onSuccess: (response) => {
      queryClient.setQueryData(["character-advanced-editor", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(editorValuesFromContext(response.editor));
      setLoadedRevision(response.editor?.state_revision ?? null);
      setStatusMessage(response.message || "Character details updated.");
      setErrorMessage(null);
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitEditor = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    saveEditor.mutate();
  };

  const renderField = (field: CharacterEditorField, options?: { textarea?: boolean; number?: boolean }) => (
    <article className="detail-card" key={field.name}>
      <label className="field">
        <span>{field.label}</span>
        {options?.textarea ? (
          <textarea
            name={field.name}
            rows={6}
            value={draftValues[field.name] ?? field.value ?? ""}
            onChange={(event) => updateDraftValue(field.name, event.currentTarget.value)}
          />
        ) : (
          <input
            type={options?.number ? "number" : "text"}
            name={field.name}
            value={draftValues[field.name] ?? field.value ?? ""}
            onChange={(event) => updateDraftValue(field.name, event.currentTarget.value)}
          />
        )}
      </label>
      {field.help_text ? <p className="meta">{field.help_text}</p> : null}
    </article>
  );

  const renderChoiceField = (field: CharacterEditorChoiceField) => (
    <label className="field" key={field.name}>
      <span>{field.label}</span>
      <select
        name={field.name}
        value={draftValues[field.name] ?? field.selected ?? ""}
        onChange={(event) => updateDraftValue(field.name, event.currentTarget.value)}
      >
        {editorSelectOptions(field.options, "Choose an option")}
      </select>
      {field.help_text ? <small>{field.help_text}</small> : null}
    </label>
  );

  const renderRecoverablePenalty = (row: CharacterEditorRecoverablePenaltyRow) => (
    <article className="detail-card character-edit-row" key={row.index}>
      <div className="character-edit-row__grid">
        <label className="field">
          <span>Source</span>
          <input
            type="text"
            value={draftValues[`recoverable_penalty_source_${row.index}`] ?? row.source ?? ""}
            onChange={(event) => updateDraftValue(`recoverable_penalty_source_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Target</span>
          <select
            value={draftValues[`recoverable_penalty_target_${row.index}`] ?? row.target ?? ""}
            onChange={(event) => updateDraftValue(`recoverable_penalty_target_${row.index}`, event.currentTarget.value)}
          >
            {editorSelectOptions(editor?.recoverable_penalty_target_options ?? [], "Choose a target")}
          </select>
        </label>
        <label className="field">
          <span>Penalty Amount</span>
          <input
            type="number"
            min={0}
            value={draftValues[`recoverable_penalty_amount_${row.index}`] ?? row.amount ?? ""}
            onChange={(event) => updateDraftValue(`recoverable_penalty_amount_${row.index}`, event.currentTarget.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>Notes</span>
        <textarea
          rows={3}
          value={draftValues[`recoverable_penalty_notes_${row.index}`] ?? row.notes ?? ""}
          onChange={(event) => updateDraftValue(`recoverable_penalty_notes_${row.index}`, event.currentTarget.value)}
        />
      </label>
    </article>
  );

  const renderFeatureRow = (row: CharacterEditorFeatureRow) => (
    <article className="detail-card character-edit-row" key={row.index}>
      <div className="character-edit-row__grid">
        <label className="field">
          <span>Name</span>
          <input
            type="text"
            value={draftValues[`custom_feature_name_${row.index}`] ?? row.name ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_name_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Activation</span>
          <select
            value={draftValues[`custom_feature_activation_type_${row.index}`] ?? row.activation_type ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_activation_type_${row.index}`, event.currentTarget.value)}
          >
            {editorSelectOptions(editor?.activation_options ?? [])}
          </select>
        </label>
      </div>
      <label className="field">
        <span>Linked Page</span>
        <select
          value={draftValues[`custom_feature_page_ref_${row.index}`] ?? row.page_ref ?? ""}
          onChange={(event) => updateDraftValue(`custom_feature_page_ref_${row.index}`, event.currentTarget.value)}
        >
          {editorSelectOptions(editor?.campaign_page_options ?? [], "No linked page")}
        </select>
      </label>
      <label className="field">
        <span>Description (Markdown)</span>
        <textarea
          rows={6}
          value={draftValues[`custom_feature_description_${row.index}`] ?? row.description_markdown ?? ""}
          onChange={(event) => updateDraftValue(`custom_feature_description_${row.index}`, event.currentTarget.value)}
        />
      </label>
      <div className="character-edit-row__grid">
        <label className="field">
          <span>Uses / Max</span>
          <input
            type="number"
            min={0}
            value={draftValues[`custom_feature_resource_max_${row.index}`] ?? row.resource_max ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_resource_max_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Reset On</span>
          <select
            value={draftValues[`custom_feature_resource_reset_on_${row.index}`] ?? row.resource_reset_on ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_resource_reset_on_${row.index}`, event.currentTarget.value)}
          >
            {editorSelectOptions(editor?.resource_reset_options ?? [])}
          </select>
        </label>
      </div>
      {row.choice_fields?.length ? <div className="detail-grid character-edit-grid">{row.choice_fields.map(renderChoiceField)}</div> : null}
      <p className="meta">Leave Uses / Max blank for a non-tracked feature. Existing spent values are preserved when you change the limit.</p>
    </article>
  );

  const renderEquipmentRow = (row: CharacterEditorEquipmentRow) => (
    <article className="detail-card character-edit-row" key={row.index}>
      <div className="character-edit-row__grid character-edit-row__grid--equipment">
        <label className="field">
          <span>Name</span>
          <input
            type="text"
            value={draftValues[`manual_item_name_${row.index}`] ?? row.name ?? ""}
            onChange={(event) => updateDraftValue(`manual_item_name_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Quantity</span>
          <input
            type="number"
            min={0}
            value={draftValues[`manual_item_quantity_${row.index}`] ?? row.quantity ?? ""}
            onChange={(event) => updateDraftValue(`manual_item_quantity_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Weight</span>
          <input
            type="text"
            value={draftValues[`manual_item_weight_${row.index}`] ?? row.weight ?? ""}
            onChange={(event) => updateDraftValue(`manual_item_weight_${row.index}`, event.currentTarget.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>Linked Page</span>
        <select
          value={draftValues[`manual_item_page_ref_${row.index}`] ?? row.page_ref ?? ""}
          onChange={(event) => updateDraftValue(`manual_item_page_ref_${row.index}`, event.currentTarget.value)}
        >
          {editorSelectOptions(editor?.equipment_page_options ?? [], "No linked page")}
        </select>
      </label>
      <label className="field">
        <span>Notes</span>
        <textarea
          rows={4}
          value={draftValues[`manual_item_notes_${row.index}`] ?? row.notes ?? ""}
          onChange={(event) => updateDraftValue(`manual_item_notes_${row.index}`, event.currentTarget.value)}
        />
      </label>
    </article>
  );

  const characterName = characterNameFromRecord(data?.character) || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);
  const loadingError = getApiErrorMessage(editorQuery.error);

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character editor</p>
        <h1>Edit {characterName}</h1>
        <p className="lede">Advanced campaign-time adjustments and durable reference text for this character are managed here.</p>
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {classLevelText ? <span className="meta">{classLevelText}</span> : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={editorQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Advanced Editor Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character system uses a different authoring lane."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="ghost-button" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {editor ? (
        <form className="card character-edit-sheet gen2-character-editor" onSubmit={submitEditor}>
          <section className="read-section">
            <div className="section-heading">
              <h2>Proficiencies</h2>
            </div>
            <div className="detail-grid character-edit-grid">{editor.proficiency_fields.map((field) => renderField(field, { textarea: true }))}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Reference Text</h2>
            </div>
            <div className="detail-grid character-edit-grid">{editor.reference_fields.map((field) => renderField(field, { textarea: true }))}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Campaign Adjustments</h2>
            </div>
            <p className="meta">Use these controlled numeric adjustments when campaign play has changed sheet math outside builder and level-up rules.</p>
            <div className="detail-grid character-edit-grid">{editor.stat_adjustment_fields.map((field) => renderField(field, { number: true }))}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Recoverable Penalties</h2>
            </div>
            <p className="meta">Track sourced max-HP and ability-score reductions here when the penalty can later be reduced or removed.</p>
            <div className="character-edit-stack">{editor.recoverable_penalty_rows.map(renderRecoverablePenalty)}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Custom Features</h2>
            </div>
            {editor.linked_feature_authoring_supported ? (
              <>
                <p className="meta">Campaign boons, curses, training rewards, and other custom feature text.</p>
                <div className="character-edit-stack">{editor.feature_rows.map(renderFeatureRow)}</div>
              </>
            ) : (
              <>
                <p className="meta">{editor.linked_feature_authoring_message}</p>
                <p className="meta">Other edit sections stay available while progression repair is pending.</p>
              </>
            )}
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Manual Equipment</h2>
            </div>
            {editor.existing_managed_equipment?.length ? (
              <article className="detail-card">
                <h3>Existing built-in equipment</h3>
                <ul className="plain-list">
                  {editor.existing_managed_equipment.map((item) => (
                    <li key={`${item.name}-${item.quantity ?? ""}-${item.weight ?? ""}`}>
                      <strong>{item.name}</strong>
                      {item.quantity ? ` x${item.quantity}` : ""}
                      {item.weight ? <span className="meta"> | {item.weight}</span> : null}
                    </li>
                  ))}
                </ul>
              </article>
            ) : null}
            <div className="character-edit-stack">{editor.equipment_rows.map(renderEquipmentRow)}</div>
          </section>

          <div className="hero-actions">
            <button type="submit" disabled={saveEditor.isPending}>
              {saveEditor.isPending ? "Saving..." : "Save character edits"}
            </button>
            {data?.links?.character_url ? (
              <a className="ghost-button" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
          </div>
        </form>
      ) : null}
    </>
  );
}

function CharacterProgressionRepairPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const repairQuery = useQuery({
    queryKey: ["character-progression-repair", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterProgressionRepair(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
    retry: false,
  });

  const data = repairQuery.data;
  const repair = data?.repair ?? null;

  useEffect(() => {
    if (isAuthError(repairQuery.error)) {
      setAuthRequired(true);
    }
  }, [repairQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!repair || loadedRevision === repair.state_revision) {
      return;
    }
    setDraftValues(characterProgressionRepairValuesFromContext(repair));
    setLoadedRevision(repair.state_revision);
    setErrorMessage(null);
  }, [repair, loadedRevision]);

  const updateValue = (key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }));
  };

  const submitRepair = useMutation({
    mutationFn: (payload: CharacterProgressionRepairPayload) =>
      apiClient.submitCharacterProgressionRepair(campaignSlug, characterSlug, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(["character-progression-repair", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(characterProgressionRepairValuesFromContext(response.repair));
      setLoadedRevision(response.repair?.state_revision ?? null);
      setStatusMessage(response.message || "Progression repair saved.");
      setErrorMessage(null);
      if (!response.supported && response.links.level_up_url) {
        window.location.assign(response.links.level_up_url);
      }
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!repair) {
      setErrorMessage({ status: 400, message: "The progression repair context has not loaded yet." });
      return;
    }
    setStatusMessage(null);
    setErrorMessage(null);
    submitRepair.mutate({
      expected_revision: repair.state_revision,
      values: characterAuthoringStringValues(draftValues),
    });
  };

  const loadingError = getApiErrorMessage(repairQuery.error);
  const characterName = characterNameFromRecord(data?.character) || repair?.character_name || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);
  const reasons = asStringArray(repair?.readiness?.reasons);

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character progression</p>
        <h1>Prepare {characterName} For Native Level-Up</h1>
        <p className="lede">
          Repair imported baseline links and missing DND-5E progression details before advancing this character
          {repair?.current_level ? ` past level ${repair.current_level}` : ""}.
        </p>
        {classLevelText ? <p className="meta">{classLevelText}</p> : null}
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={repairQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>{data.lane === "ready" ? "Progression Repair Is Complete" : "Progression Repair Is Not Available In Gen2"}</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 progression repair."}</p>
          <div className="hero-actions">
            {data.links.level_up_url ? (
              <a className="button-link" href={data.links.level_up_url}>
                Level Up
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="ghost-button" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {repair ? (
        <article className="card character-edit-sheet">
          <section className="read-section">
            <div className="section-heading">
              <div>
                <h2>Progression Repair</h2>
                {repair.readiness?.message ? <p className="meta">{repair.readiness.message}</p> : null}
              </div>
            </div>
            {reasons.length ? (
              <div className="builder-section">
                <h3>What Needs Repair</h3>
                <ul className="plain-list builder-feature-list">
                  {reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <form className="stack-form character-builder-form" onSubmit={submitForm}>
            {repair.class_rows?.length ? (
              <section className="builder-section">
                <h2>Class Rows</h2>
                <div className="builder-field-grid">
                  {repair.class_rows.map((row) => (
                    <React.Fragment key={row.row_id || row.class_field_name}>
                      <label className="field">
                        <span>
                          {row.class_name || "Class"}
                          {row.row_level ? ` ${row.row_level}` : ""}
                        </span>
                        <select
                          name={row.class_field_name}
                          value={draftString(draftValues, row.class_field_name, row.class_selected || "")}
                          onChange={(event) => updateValue(row.class_field_name, event.currentTarget.value)}
                        >
                          <option value="">Choose an option</option>
                          {selectOptions(row.class_options ?? [])}
                        </select>
                      </label>
                      <label className="field">
                        <span>Subclass Link</span>
                        <select
                          name={row.subclass_field_name}
                          value={draftString(draftValues, row.subclass_field_name, row.subclass_selected || "")}
                          onChange={(event) => updateValue(row.subclass_field_name, event.currentTarget.value)}
                        >
                          <option value="">No subclass link</option>
                          {selectOptions(row.subclass_options ?? [])}
                        </select>
                      </label>
                    </React.Fragment>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="builder-section">
              <h2>Baseline Links</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Species</span>
                  <select
                    name="repair_species_slug"
                    value={draftString(draftValues, "repair_species_slug")}
                    onChange={(event) => updateValue("repair_species_slug", event.currentTarget.value)}
                  >
                    <option value="">Choose an option</option>
                    {selectOptions(repair.species_options ?? [])}
                  </select>
                </label>
                <label className="field">
                  <span>Background</span>
                  <select
                    name="repair_background_slug"
                    value={draftString(draftValues, "repair_background_slug")}
                    onChange={(event) => updateValue("repair_background_slug", event.currentTarget.value)}
                  >
                    <option value="">Choose an option</option>
                    {selectOptions(repair.background_options ?? [])}
                  </select>
                </label>
              </div>
            </section>

            {repair.feat_rows?.length ? (
              <section className="builder-section">
                <h2>Prior Feats</h2>
                <div className="builder-field-grid">
                  {repair.feat_rows.map((row) => (
                    <label className="field" key={row.name}>
                      <span>Feat {row.index ?? ""}</span>
                      <select
                        name={row.name}
                        value={draftString(draftValues, row.name, row.selected || "")}
                        onChange={(event) => updateValue(row.name, event.currentTarget.value)}
                      >
                        <option value="">Leave unchanged</option>
                        {selectOptions(row.options ?? [])}
                      </select>
                      <small>Backfill older feat picks not linked cleanly.</small>
                    </label>
                  ))}
                </div>
              </section>
            ) : null}

            {repair.optionalfeature_rows?.length ? (
              <section className="builder-section">
                <h2>Prior Optional Features</h2>
                <div className="builder-field-grid">
                  {repair.optionalfeature_rows.map((row) => (
                    <label className="field" key={row.name}>
                      <span>Optional Feature {row.index ?? ""}</span>
                      <select
                        name={row.name}
                        value={draftString(draftValues, row.name, row.selected || "")}
                        onChange={(event) => updateValue(row.name, event.currentTarget.value)}
                      >
                        <option value="">Leave unchanged</option>
                        {selectOptions(row.options ?? [])}
                      </select>
                      <small>Repair prior fighting styles, maneuvers, and similar linked feature choices.</small>
                    </label>
                  ))}
                </div>
              </section>
            ) : null}

            {repair.spell_rows?.length ? (
              <section className="builder-section">
                <h2>Spell Baseline</h2>
                <div className="builder-field-grid">
                  {repair.spell_rows.map((row) => (
                    <React.Fragment key={row.field_name}>
                      {(row.class_row_options?.length ?? 0) > 1 && row.class_row_field_name ? (
                        <label className="field">
                          <span>{row.name || "Spell"} Class Row</span>
                          <select
                            name={row.class_row_field_name}
                            value={draftString(draftValues, row.class_row_field_name, row.class_row_selected || "")}
                            onChange={(event) => updateValue(row.class_row_field_name || "", event.currentTarget.value)}
                          >
                            <option value="">Choose a class row</option>
                            {selectOptions(row.class_row_options ?? [])}
                          </select>
                        </label>
                      ) : null}
                      <label className="field">
                        <span>{row.name || "Spell"}</span>
                        <select
                          name={row.field_name}
                          value={draftString(draftValues, row.field_name, row.selected || "")}
                          onChange={(event) => updateValue(row.field_name, event.currentTarget.value)}
                        >
                          <option value="">Choose a spell mark</option>
                          {selectOptions(row.options ?? [])}
                        </select>
                      </label>
                    </React.Fragment>
                  ))}
                </div>
              </section>
            ) : null}

            <div className="builder-actions">
              <button className="ghost-button" type="submit" disabled={submitRepair.isPending}>
                {submitRepair.isPending ? "Saving..." : "Save Repair"}
              </button>
              {data?.links?.character_url ? (
                <a className="ghost-button" href={data.links.character_url}>
                  Cancel
                </a>
              ) : null}
            </div>
          </form>
        </article>
      ) : null}
    </>
  );
}

function CharacterRetrainingPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/retraining",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const retrainingQuery = useQuery({
    queryKey: ["character-retraining", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterRetraining(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
    retry: false,
  });

  const data = retrainingQuery.data;
  const retraining = data?.retraining ?? null;

  useEffect(() => {
    if (isAuthError(retrainingQuery.error)) {
      setAuthRequired(true);
    }
  }, [retrainingQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!retraining || loadedRevision === retraining.state_revision) {
      return;
    }
    setDraftValues(characterRetrainingValuesFromContext(retraining));
    setLoadedRevision(retraining.state_revision);
    setErrorMessage(null);
  }, [retraining, loadedRevision]);

  const updateValue = (key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }));
  };

  const submitRetraining = useMutation({
    mutationFn: (payload: CharacterRetrainingPayload) => apiClient.submitCharacterRetraining(campaignSlug, characterSlug, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(["character-retraining", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(characterRetrainingValuesFromContext(response.retraining));
      setLoadedRevision(response.retraining?.state_revision ?? null);
      setStatusMessage(response.message || "Retraining saved.");
      setErrorMessage(null);
      if (response.links.character_url) {
        window.location.assign(`${response.links.character_url}?page=features`);
      }
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!retraining) {
      setErrorMessage({ status: 400, message: "The retraining context has not loaded yet." });
      return;
    }
    setStatusMessage(null);
    setErrorMessage(null);
    submitRetraining.mutate({
      expected_revision: retraining.state_revision,
      values: characterAuthoringStringValues(draftValues),
    });
  };

  const loadingError = getApiErrorMessage(retrainingQuery.error);
  const characterName = characterNameFromRecord(data?.character) || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character retraining</p>
        <h1>Retrain {characterName}</h1>
        {classLevelText ? <p className="lede">{classLevelText}</p> : null}
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.advanced_editor_url ? (
            <a className="ghost-button" href={data.links.advanced_editor_url}>
              Advanced Editor
            </a>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={retrainingQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Retraining Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 retraining."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.progression_repair_url ? (
              <a className="ghost-button" href={data.links.progression_repair_url}>
                Progression repair
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="ghost-button" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {retraining ? (
        <article className="card character-edit-sheet">
          {retraining.supported_scope?.length ? (
            <section className="read-section">
              <div className="section-heading">
                <h2>Supported Scope</h2>
              </div>
              <ul className="plain-list builder-feature-list">
                {retraining.supported_scope.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <form className="stack-form" onSubmit={submitForm}>
            <section className="read-section">
              <div className="section-heading">
                <h2>Structured Choices</h2>
              </div>
              <div className="character-edit-stack">
                {retraining.feature_rows.map((row) => (
                  <article className="detail-card character-edit-row" key={row.id || row.index}>
                    <div className="section-heading">
                      <div>
                        <h3>{row.name || "Linked Feature"}</h3>
                        {row.page_ref ? <p className="meta">{row.page_ref}</p> : null}
                      </div>
                      {row.activation_type ? <span className="meta">{row.activation_type.replace(/_/g, " ")}</span> : null}
                    </div>
                    {row.summary ? <p className="meta">{row.summary}</p> : null}
                    <div className="detail-grid character-edit-grid">
                      {(row.choice_fields ?? []).map((field) => (
                        <label className="field" key={field.name}>
                          <span>{field.label}</span>
                          <select
                            name={field.name}
                            value={draftString(draftValues, field.name, field.selected || "")}
                            onChange={(event) => updateValue(field.name, event.currentTarget.value)}
                          >
                            <option value="">Choose an option</option>
                            {selectOptions(field.options ?? [])}
                          </select>
                          {field.help_text ? <small>{field.help_text}</small> : null}
                        </label>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <div className="hero-actions">
              <button type="submit" disabled={submitRetraining.isPending}>
                {submitRetraining.isPending ? "Saving..." : "Save retraining"}
              </button>
              {data?.links?.character_url ? (
                <a className="ghost-button" href={`${data.links.character_url}?page=features`}>
                  Cancel
                </a>
              ) : null}
            </div>
          </form>
        </article>
      ) : null}
    </>
  );
}

function CharacterLevelUpPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/level-up",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [contextValues, setContextValues] = useState<CharacterAuthoringValues>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const levelUpQuery = useQuery({
    queryKey: ["character-level-up", campaignSlug, characterSlug, JSON.stringify(contextValues)],
    queryFn: () => apiClient.getCharacterLevelUp(campaignSlug, characterSlug, contextValues),
    enabled: Boolean(campaignSlug && characterSlug),
    retry: false,
  });

  const data = levelUpQuery.data;
  const levelUp = data?.level_up ?? null;

  useEffect(() => {
    if (isAuthError(levelUpQuery.error)) {
      setAuthRequired(true);
    }
  }, [levelUpQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!levelUp || loadedRevision === levelUp.state_revision) {
      return;
    }
    setDraftValues(characterLevelUpValuesFromContext(levelUp));
    setLoadedRevision(levelUp.state_revision);
    setErrorMessage(null);
  }, [levelUp, loadedRevision]);

  const refreshContext = (values: CharacterAuthoringValues = draftValues) => {
    setContextValues({ ...values });
  };

  const updateValue = (key: string, value: string, refresh = false) => {
    const nextValues = { ...draftValues, [key]: value };
    setDraftValues(nextValues);
    if (refresh) {
      refreshContext(nextValues);
    }
  };

  const submitLevelUp = useMutation({
    mutationFn: (payload: CharacterLevelUpPayload) => apiClient.submitCharacterLevelUp(campaignSlug, characterSlug, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(["character-level-up", campaignSlug, characterSlug, JSON.stringify(contextValues)], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(characterLevelUpValuesFromContext(response.level_up));
      setLoadedRevision(response.level_up?.state_revision ?? null);
      setStatusMessage(response.message || "Character advanced.");
      setErrorMessage(null);
      if (response.links.character_url) {
        window.location.assign(response.links.character_url);
      }
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!levelUp) {
      setErrorMessage({ status: 400, message: "The level-up context has not loaded yet." });
      return;
    }
    setStatusMessage(null);
    setErrorMessage(null);
    submitLevelUp.mutate({
      expected_revision: levelUp.state_revision,
      values: characterAuthoringStringValues(draftValues),
    });
  };

  const loadingError = getApiErrorMessage(levelUpQuery.error);
  const characterName = characterNameFromRecord(data?.character) || levelUp?.character_name || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);
  const advancementMode = draftString(draftValues, "advancement_mode", levelUp?.advancement_mode || "advance_existing");

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character level-up</p>
        <h1>Level Up {characterName}</h1>
        {classLevelText ? <p className="lede">{classLevelText}</p> : null}
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={levelUpQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Level-Up Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 level-up."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.progression_repair_url ? (
              <a className="ghost-button" href={data.links.progression_repair_url}>
                Progression repair
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="ghost-button" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {levelUp ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitForm}>
            <section className="builder-section">
              <h2>Advancement</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Mode</span>
                  <select
                    name="advancement_mode"
                    value={advancementMode}
                    onChange={(event) => updateValue("advancement_mode", event.currentTarget.value, true)}
                  >
                    {selectOptions(levelUp.mode_options ?? [])}
                  </select>
                </label>

                {advancementMode === "add_class" ? (
                  <>
                    <label className="field">
                      <span>New Class</span>
                      <select
                        name="new_class_slug"
                        value={draftString(draftValues, "new_class_slug")}
                        onChange={(event) => updateValue("new_class_slug", event.currentTarget.value, true)}
                      >
                        <option value="">Choose a class</option>
                        {selectOptions(levelUp.new_class_options ?? [])}
                      </select>
                    </label>
                    {levelUp.new_subclass_options?.length || levelUp.requires_subclass ? (
                      <label className="field">
                        <span>New Subclass</span>
                        <select
                          name="new_subclass_slug"
                          value={draftString(draftValues, "new_subclass_slug")}
                          onChange={(event) => updateValue("new_subclass_slug", event.currentTarget.value, true)}
                        >
                          <option value="">{levelUp.requires_subclass ? "Choose a subclass" : "No subclass"}</option>
                          {selectOptions(levelUp.new_subclass_options ?? [])}
                        </select>
                      </label>
                    ) : null}
                  </>
                ) : (
                  <label className="field">
                    <span>Class Row</span>
                    <select
                      name="target_class_row_id"
                      value={draftString(draftValues, "target_class_row_id", levelUp.target_class_row_id || "")}
                      onChange={(event) => updateValue("target_class_row_id", event.currentTarget.value, true)}
                    >
                      {selectOptions(levelUp.target_row_options ?? [])}
                    </select>
                  </label>
                )}

                {advancementMode !== "add_class" && (levelUp.subclass_options?.length || levelUp.requires_subclass) ? (
                  <label className="field">
                    <span>Subclass</span>
                    <select
                      name="subclass_slug"
                      value={draftString(draftValues, "subclass_slug")}
                      onChange={(event) => updateValue("subclass_slug", event.currentTarget.value, true)}
                    >
                      <option value="">{levelUp.requires_subclass ? "Choose a subclass" : "No subclass"}</option>
                      {selectOptions(levelUp.subclass_options ?? [])}
                    </select>
                  </label>
                ) : null}

                <label className="field">
                  <span>HP Gain</span>
                  <input
                    type="number"
                    name="hp_gain"
                    min={1}
                    value={draftString(draftValues, "hp_gain")}
                    onChange={(event) => updateValue("hp_gain", event.currentTarget.value)}
                  />
                </label>
              </div>
              {levelUp.multiclass_requirement_text ? (
                <p className={levelUp.multiclass_requirements_met ? "meta" : "status status-warning"}>
                  Multiclass requirement: {levelUp.multiclass_requirement_text}
                </p>
              ) : null}
            </section>

            {levelUp.choice_sections.map((section) => (
              <section className="builder-section" key={section.title}>
                <h2>{section.title}</h2>
                <div className="builder-field-grid">
                  {section.fields.map((field) => (
                    <CharacterDndChoiceSelect
                      key={field.name}
                      field={field}
                      draftValues={draftValues}
                      setDraftValues={setDraftValues}
                      refreshContext={refreshContext}
                    />
                  ))}
                </div>
              </section>
            ))}

            {levelUp.limitations?.length ? (
              <section className="builder-section">
                <h2>Limitations</h2>
                <ul className="plain-list">
                  {levelUp.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="builder-actions">
              <button type="button" className="ghost-button" onClick={() => refreshContext()}>
                Refresh preview
              </button>
              <button type="submit" disabled={submitLevelUp.isPending}>
                {submitLevelUp.isPending ? "Leveling..." : `Advance to level ${levelUp.next_level}`}
              </button>
            </div>
          </form>
          <CharacterLevelUpPreviewList preview={levelUp.preview ?? {}} />
        </div>
      ) : null}
    </>
  );
}

function CharacterCultivationPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const cultivationQuery = useQuery({
    queryKey: ["character-cultivation", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterCultivation(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
  });

  const data = cultivationQuery.data;
  const cultivation = data?.cultivation ?? null;
  const actionMutation = useMutation({
    mutationFn: ({ action, values }: { action: string; values: Record<string, string> }) => {
      if (!data) {
        throw new Error("The cultivation context has not loaded yet.");
      }
      return apiClient.runCharacterCultivationAction(campaignSlug, characterSlug, {
        expected_revision: data.character.state_record.revision,
        action,
        values,
      });
    },
    onSuccess: (response) => {
      queryClient.setQueryData(["character-cultivation", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setStatusMessage(response.message || "Cultivation updated.");
      setErrorMessage(null);
      if (response.anchor) {
        window.requestAnimationFrame(() => {
          document.getElementById(response.anchor || "")?.scrollIntoView({ block: "start" });
        });
      }
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitCultivationAction = (event: FormEvent<HTMLFormElement>, action: string) => {
    event.preventDefault();
    const values: Record<string, string> = {};
    new FormData(event.currentTarget).forEach((value, key) => {
      if (typeof value === "string") {
        values[key] = value;
      }
    });
    setStatusMessage(null);
    setErrorMessage(null);
    actionMutation.mutate({ action, values });
  };

  const renderActionForm = (
    action: string,
    buttonLabel: string,
    children: React.ReactNode,
    options: { disabled?: boolean } = {},
  ) => (
    <form className="stack-form cultivation-action-form" onSubmit={(event) => submitCultivationAction(event, action)}>
      {children}
      <div className="hero-actions">
        <button type="submit" disabled={actionMutation.isPending || options.disabled}>
          {actionMutation.isPending ? "Saving..." : buttonLabel}
        </button>
      </div>
    </form>
  );

  const renderSpendCard = (
    row: CharacterCultivationStatRow,
    options: {
      action: string;
      keyName: string;
      hiddenName: string;
      notesName: string;
      buttonPrefix: string;
      meta: string;
    },
  ) => {
    const label = stringFromUnknown(row.label || row.key || "Resource");
    const hasEnoughInsight = boolFromUnknown(row.has_enough_insight);
    return (
      <article className="feature-row cultivation-card" key={`${options.action}-${options.keyName}`}>
        <div className="feature-row__header">
          <h3>{label}</h3>
          <p className="meta">
            Current {numberFromUnknown(row.current)} / Max {numberFromUnknown(row.max)}
          </p>
        </div>
        {renderActionForm(
          options.action,
          `${options.buttonPrefix} ${label}`,
          <>
            <input type="hidden" name={options.hiddenName} value={options.keyName} />
            <p className="meta">{options.meta}</p>
            <label className="field">
              <span>Notes</span>
              <textarea name={options.notesName} rows={2} />
            </label>
            {!hasEnoughInsight ? <p className="meta">Needs {numberFromUnknown(row.shortfall)} more available Insight.</p> : null}
          </>,
          { disabled: !hasEnoughInsight },
        )}
      </article>
    );
  };

  const renderHistoryRecords = (records: Array<Record<string, unknown>>) =>
    records.length ? (
      <div className="feature-stack">
        {records.map((record, index) => (
          <article className="feature-row" key={`${stringFromUnknown(record.action, "record")}-${index}`}>
            <div className="feature-row__header">
              <h3>{stringFromUnknown(record.action || record.status || "Record").replace(/_/g, " ")}</h3>
              {record.target_realm ? <p className="meta">Target {stringFromUnknown(record.target_realm)}</p> : null}
            </div>
            <ul className="plain-list slot-list">
              {Object.entries(record)
                .filter(([key, value]) => {
                  if (["snapshot", "pre_ascension_snapshot", "post_ascension_snapshot"].includes(key)) {
                    return false;
                  }
                  return value !== null && value !== undefined && String(value).trim() !== "";
                })
                .slice(0, 12)
                .map(([key, value]) => (
                  <li key={key}>
                    <strong>{key.replace(/_/g, " ")}:</strong> {stringFromUnknown(value)}
                  </li>
                ))}
            </ul>
          </article>
        ))}
      </div>
    ) : null;

  const renderMartialArts = (context: CharacterCultivationContext) => {
    if (!context.martial_arts.length) {
      return (
        <article className="detail-card">
          <p className="meta">No Martial Arts are recorded on this sheet yet.</p>
        </article>
      );
    }
    return (
      <div className="feature-stack">
        {context.martial_arts.map((rawArt, fallbackIndex) => {
          const art = recordFromUnknown(rawArt);
          const index = numberFromUnknown(art.index, fallbackIndex);
          const advancement = recordFromUnknown(art.advancement);
          const rankProgress = recordFromUnknown(art.rank_progress);
          const steps = recordListFromUnknown(rankProgress.steps);
          const name = stringFromUnknown(art.name, "Martial Art");
          const href = stringFromUnknown(art.href);
          const available = stringFromUnknown(advancement.status) === "available";
          const hasEnoughInsight = boolFromUnknown(advancement.has_enough_insight);
          const nextRankLabel = stringFromUnknown(advancement.next_rank_label, "next rank");
          return (
            <article className="feature-row cultivation-card" key={`${name}-${index}`}>
              <div className="feature-row__header">
                <h3>{href ? <a href={href}>{name}</a> : name}</h3>
                <p className="meta">
                  {art.current_rank ? `Current rank: ${stringFromUnknown(art.current_rank)}` : "Rank not recorded"}
                  {art.rank_records_status ? ` | ${stringFromUnknown(art.rank_records_status).replace(/_/g, " ")}` : ""}
                </p>
              </div>
              {steps.length ? (
                <div className="skill-grid">
                  {steps.map((step) => (
                    <div
                      className={boolFromUnknown(step.is_learned) ? "skill-pill skill-pill--proficient" : "skill-pill"}
                      key={stringFromUnknown(step.key || step.label)}
                    >
                      {step.href ? (
                        <a href={stringFromUnknown(step.href)}>{stringFromUnknown(step.label)}</a>
                      ) : (
                        <span>{stringFromUnknown(step.label)}</span>
                      )}
                      <span className="meta">{stringFromUnknown(step.status_label)}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {available ? (
                renderActionForm(
                  "advance_martial_art_rank",
                  `Advance to ${nextRankLabel}`,
                  <>
                    <input type="hidden" name="martial_art_index" value={String(index)} />
                    <input type="hidden" name="target_rank_key" value={stringFromUnknown(advancement.next_rank_key)} />
                    <p className="meta">
                      Spend {numberFromUnknown(advancement.insight_cost)} Insight to advance to {nextRankLabel}.
                    </p>
                    {advancement.teacher_breakthrough_note ? (
                      <p className="meta">Teacher/Breakthrough: {stringFromUnknown(advancement.teacher_breakthrough_note)}</p>
                    ) : null}
                    {boolFromUnknown(advancement.requires_legendary_note) ? (
                      <label className="field">
                        <span>Quest or mythic-master note</span>
                        <textarea name="legendary_quest_note" rows={3} required />
                      </label>
                    ) : null}
                    {!hasEnoughInsight ? <p className="meta">Needs {numberFromUnknown(advancement.shortfall)} more available Insight.</p> : null}
                  </>,
                  { disabled: !hasEnoughInsight },
                )
              ) : advancement.message ? (
                <p className="meta">{stringFromUnknown(advancement.message)}</p>
              ) : null}
            </article>
          );
        })}
      </div>
    );
  };

  const renderGenericTechniques = (context: CharacterCultivationContext) => (
    <div className="feature-stack">
      {context.generic_techniques.length ? (
        <article className="detail-card">
          <h3>Known Generic Techniques</h3>
          <ul className="plain-list slot-list">
            {context.generic_techniques.map((rawTechnique, index) => {
              const technique = recordFromUnknown(rawTechnique);
              const href = stringFromUnknown(technique.href);
              const name = stringFromUnknown(technique.name, "Generic Technique");
              return (
                <li key={`${name}-${index}`}>
                  {href ? <a href={href}>{name}</a> : <strong>{name}</strong>}
                  {technique.insight_cost ? <span className="meta"> | Insight {stringFromUnknown(technique.insight_cost)}</span> : null}
                </li>
              );
            })}
          </ul>
        </article>
      ) : null}
      {context.generic_technique_options.map((rawTechnique, index) => {
        const technique = recordFromUnknown(rawTechnique);
        const name = stringFromUnknown(technique.name, "Generic Technique");
        const href = stringFromUnknown(technique.href);
        const entryKey = stringFromUnknown(technique.entry_key);
        const hasEnoughInsight = boolFromUnknown(technique.has_enough_insight);
        return (
          <article className="feature-row cultivation-card" key={`${entryKey || name}-${index}`}>
            <div className="feature-row__header">
              <h3>{href ? <a href={href}>{name}</a> : name}</h3>
              <p className="meta">
                Insight {numberFromUnknown(technique.insight_cost)}
                {technique.support_state ? ` | ${stringFromUnknown(technique.support_state).replace(/_/g, " ")}` : ""}
              </p>
            </div>
            {renderActionForm(
              "learn_generic_technique",
              `Learn ${name}`,
              <>
                <input type="hidden" name="generic_technique_entry_key" value={entryKey} />
                <label className="field">
                  <span>Notes</span>
                  <textarea name="generic_technique_notes" rows={2} />
                </label>
                {!hasEnoughInsight ? <p className="meta">Needs {numberFromUnknown(technique.shortfall)} more available Insight.</p> : null}
              </>,
              { disabled: !hasEnoughInsight },
            )}
          </article>
        );
      })}
      {!context.generic_techniques.length && !context.generic_technique_options.length ? (
        <article className="detail-card">
          <p className="meta">No Generic Technique options are currently available.</p>
        </article>
      ) : null}
    </div>
  );

  const renderRealmAscension = (context: CharacterCultivationContext) => {
    const ascension = recordFromUnknown(context.realm_ascension);
    const target = recordFromUnknown(ascension.target);
    const statPrerequisite = recordFromUnknown(ascension.stat_prerequisite);
    const attributes = recordFromUnknown(ascension.attributes);
    const efforts = recordFromUnknown(ascension.efforts);
    const attributeRows = recordListFromUnknown(attributes.rows);
    const effortRows = recordListFromUnknown(efforts.rows);
    const trade = recordFromUnknown(ascension.hp_stance_trade);
    const pendingConfirmation = recordFromUnknown(ascension.pending_confirmation_rebuild);
    const targetRealm = stringFromUnknown(target.target_realm || pendingConfirmation.target_realm);
    const rebuildAction = targetRealm === "Divine" ? "apply_divine_realm_rebuild" : "apply_immortal_realm_rebuild";

    return (
      <section className="read-section" id="xianxia-cultivation-realm-ascension">
        <div className="section-heading">
          <h2>Realm Ascension</h2>
        </div>
        <div className="glance-grid">
          <div className="glance-card">
            <span className="meta">Current Realm</span>
            <strong>{stringFromUnknown(ascension.current_realm, "Unknown")}</strong>
          </div>
          {boolFromUnknown(ascension.available) ? (
            <>
              <div className="glance-card">
                <span className="meta">Target Realm</span>
                <strong>{stringFromUnknown(target.target_realm)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Seclusion</span>
                <strong>{stringFromUnknown(target.seclusion_time)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Rebuild</span>
                <strong>{numberFromUnknown(target.rebuild_budget)} points</strong>
                <span className="meta">Max {numberFromUnknown(target.stat_cap)} per Stat</span>
              </div>
              <div className="glance-card">
                <span className="meta">Stat prerequisite</span>
                <strong>{boolFromUnknown(statPrerequisite.is_met) ? "Met" : "Not met"}</strong>
                <span className="meta">{stringFromUnknown(statPrerequisite.requirement_text)}</span>
              </div>
            </>
          ) : (
            <div className="glance-card">
              <span className="meta">Target Realm</span>
              <strong>None</strong>
            </div>
          )}
        </div>
        <article className="detail-card">
          <div className="detail-grid">
            <div>
              <h3>Attributes</h3>
              <p className="meta">Current total {numberFromUnknown(attributes.total)}</p>
              <ul className="plain-list slot-list">
                {attributeRows.map((stat) => (
                  <li key={stringFromUnknown(stat.key || stat.label)}>
                    <strong>{stringFromUnknown(stat.label)}:</strong> {numberFromUnknown(stat.score)}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Efforts</h3>
              <p className="meta">Current total {numberFromUnknown(efforts.total)}</p>
              <ul className="plain-list slot-list">
                {effortRows.map((stat) => (
                  <li key={stringFromUnknown(stat.key || stat.label)}>
                    <strong>{stringFromUnknown(stat.label)}:</strong> {numberFromUnknown(stat.score)}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </article>
        {boolFromUnknown(ascension.available) ? (
          <article className="detail-card session-card">
            {!boolFromUnknown(ascension.can_start_review) ? (
              <p className="meta">
                {stringFromUnknown(ascension.confirmation_blocking_message || statPrerequisite.failure_message)}
              </p>
            ) : null}
            {renderActionForm(
              "start_realm_ascension_review",
              "Start Realm Review",
              <>
                <input type="hidden" name="target_realm" value={stringFromUnknown(target.target_realm)} />
                <label className="field">
                  <span>GM review note</span>
                  <textarea name="realm_ascension_gm_review_note" rows={3} required />
                </label>
                <label className="field">
                  <span>Seclusion notes</span>
                  <textarea name="realm_ascension_seclusion_notes" rows={2} />
                </label>
                <label className="field">
                  <span>HP/Stance trade notes</span>
                  <textarea name="realm_ascension_hp_stance_trade_notes" rows={2} />
                </label>
              </>,
              { disabled: !boolFromUnknown(ascension.can_start_review) },
            )}
          </article>
        ) : (
          <article className="detail-card">
            <p className="meta">{stringFromUnknown(ascension.message)}</p>
          </article>
        )}
        {renderHistoryRecords(
          [
            recordFromUnknown(ascension.latest_review),
            recordFromUnknown(ascension.latest_reset),
            recordFromUnknown(ascension.latest_rebuild),
            recordFromUnknown(ascension.latest_confirmation),
          ].filter((record) => Object.keys(record).length > 0),
        )}
        {boolFromUnknown(ascension.can_reset_stats) ? (
          <article className="detail-card session-card">
            <h3>Reset Rebuild Stats</h3>
            {renderActionForm(
              "reset_realm_ascension_stats",
              "Reset Attributes and Efforts",
              <>
                <input type="hidden" name="target_realm" value={targetRealm} />
                <label className="field">
                  <span>Reset notes</span>
                  <textarea name="realm_ascension_reset_notes" rows={2} />
                </label>
              </>,
            )}
          </article>
        ) : null}
        {boolFromUnknown(ascension.can_apply_rebuild) ? (
          <article className="detail-card session-card">
            <h3>Apply {targetRealm} Rebuild</h3>
            {renderActionForm(
              rebuildAction,
              `Apply ${targetRealm} Rebuild`,
              <>
                <input type="hidden" name="target_realm" value={targetRealm} />
                <div className="detail-grid">
                  <div>
                    <h4>Attributes</h4>
                    <div className="builder-field-grid">
                      {attributeRows.map((stat) => (
                        <label className="field" key={stringFromUnknown(stat.key)}>
                          <span>{stringFromUnknown(stat.label)}</span>
                          <input
                            type="number"
                            min={0}
                            max={numberFromUnknown(target.stat_cap)}
                            name={`realm_rebuild_attribute_${stringFromUnknown(stat.key)}`}
                            defaultValue={numberFromUnknown(stat.score)}
                            required
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4>Efforts</h4>
                    <div className="builder-field-grid">
                      {effortRows.map((stat) => (
                        <label className="field" key={stringFromUnknown(stat.key)}>
                          <span>{stringFromUnknown(stat.label)}</span>
                          <input
                            type="number"
                            min={0}
                            max={numberFromUnknown(target.stat_cap)}
                            name={`realm_rebuild_effort_${stringFromUnknown(stat.key)}`}
                            defaultValue={numberFromUnknown(stat.score)}
                            required
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="detail-grid">
                  <label className="field">
                    <span>HP maximum traded</span>
                    <input
                      type="number"
                      min={0}
                      max={numberFromUnknown(trade.hp_maximum_trade)}
                      step={numberFromUnknown(trade.unit, 10)}
                      name="realm_ascension_trade_hp"
                      defaultValue={0}
                      disabled={!numberFromUnknown(trade.hp_maximum_trade)}
                    />
                  </label>
                  <label className="field">
                    <span>Stance maximum traded</span>
                    <input
                      type="number"
                      min={0}
                      max={numberFromUnknown(trade.stance_maximum_trade)}
                      step={numberFromUnknown(trade.unit, 10)}
                      name="realm_ascension_trade_stance"
                      defaultValue={0}
                      disabled={!numberFromUnknown(trade.stance_maximum_trade)}
                    />
                  </label>
                </div>
                <label className="field">
                  <span>Rebuild notes</span>
                  <textarea name="realm_ascension_rebuild_notes" rows={2} />
                </label>
              </>,
            )}
          </article>
        ) : null}
        {boolFromUnknown(ascension.can_confirm_rebuild) && Object.keys(pendingConfirmation).length ? (
          <article className="detail-card session-card">
            <h3>Confirm {targetRealm} Ascension</h3>
            {renderActionForm(
              "confirm_realm_ascension",
              "Confirm Realm Ascension",
              <>
                <input type="hidden" name="target_realm" value={targetRealm} />
                <label className="field">
                  <span>GM confirmation note</span>
                  <textarea name="realm_ascension_gm_confirmation_note" rows={3} required />
                </label>
              </>,
            )}
          </article>
        ) : null}
      </section>
    );
  };

  const loadingError = getApiErrorMessage(cultivationQuery.error);
  const characterName = characterNameFromRecord(data?.character) || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);

  return (
    <>
      <section className="hero compact character-cultivation-hero character-authoring-hero">
        <p className="eyebrow">Character cultivation</p>
        <h1>Cultivation: {characterName}</h1>
        <p className="lede">Insight-based advancement for this Xianxia character.</p>
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="ghost-button" href={`${data.links.character_url}?page=martial_arts`}>
              Martial Arts
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="ghost-button" href={`${data.links.character_url}?page=techniques`}>
              Techniques
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="ghost-button" href={`${data.links.character_url}?page=resources`}>
              Resources
            </a>
          ) : null}
          <a className="ghost-button" href="#xianxia-cultivation-realm-ascension">
            Realm Ascension
          </a>
          {classLevelText ? <span className="meta">{classLevelText}</span> : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={cultivationQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Cultivation Is Not Available</h2>
          <p>{data.unsupported_message || "This character system uses a different advancement lane."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {cultivation ? (
        <>
          <section className="read-section" id="xianxia-cultivation-insight">
            <div className="section-heading">
              <h2>Insight</h2>
            </div>
            <div className="glance-grid">
              <div className="glance-card">
                <span className="meta">Available</span>
                <strong>{numberFromUnknown(cultivation.insight.available)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Spent</span>
                <strong>{numberFromUnknown(cultivation.insight.spent)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Martial Arts</span>
                <strong>{cultivation.martial_arts.length}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Generic Techniques</span>
                <strong>{cultivation.generic_techniques.length}</strong>
              </div>
            </div>
            <article className="detail-card session-card">
              {renderActionForm(
                "save_insight",
                "Save Insight",
                <div className="detail-grid">
                  <label className="field">
                    <span>Insight available</span>
                    <input type="number" name="insight_available" min={0} step={1} defaultValue={cultivation.insight.available} />
                  </label>
                  <label className="field">
                    <span>Insight spent</span>
                    <input type="number" name="insight_spent" min={0} step={1} defaultValue={cultivation.insight.spent} />
                  </label>
                </div>,
              )}
            </article>
          </section>

          <section className="read-section" id="xianxia-cultivation-gathering-insight">
            <div className="section-heading">
              <h2>Gathering Insight</h2>
            </div>
            <article className="detail-card session-card">
              {renderActionForm(
                "record_gathering_insight",
                "Record Gain",
                <>
                  <div className="detail-grid">
                    <label className="field">
                      <span>Insight gained</span>
                      <input type="number" name="insight_gain_amount" min={1} step={1} defaultValue={1} />
                    </label>
                    <label className="field">
                      <span>Downtime</span>
                      <input type="text" name="gathering_insight_downtime" />
                    </label>
                  </div>
                  <label className="field">
                    <span>Notes</span>
                    <textarea name="gathering_insight_notes" rows={3} />
                  </label>
                </>,
              )}
            </article>
          </section>

          <section className="read-section" id="xianxia-cultivation-energy">
            <div className="section-heading">
              <h2>Cultivation</h2>
            </div>
            <div className="feature-stack">
              {cultivation.energies.length ? (
                cultivation.energies.map((energy) =>
                  renderSpendCard(energy, {
                    action: "spend_cultivation_energy",
                    keyName: stringFromUnknown(energy.key),
                    hiddenName: "energy_key",
                    notesName: "cultivation_energy_notes",
                    buttonPrefix: "Increase",
                    meta: `Spend ${numberFromUnknown(energy.insight_cost)} Insight to increase ${stringFromUnknown(energy.label)} by 1.`,
                  }),
                )
              ) : (
                <article className="detail-card">
                  <p className="meta">No Energy resources are recorded on this sheet yet.</p>
                </article>
              )}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-meditation">
            <div className="section-heading">
              <h2>Meditation</h2>
            </div>
            <div className="feature-stack">
              {cultivation.yin_yang.length ? (
                cultivation.yin_yang.map((resource) =>
                  renderSpendCard(resource, {
                    action: "spend_meditation_yin_yang",
                    keyName: stringFromUnknown(resource.key),
                    hiddenName: "yin_yang_key",
                    notesName: "meditation_notes",
                    buttonPrefix: "Increase",
                    meta: `Spend ${numberFromUnknown(resource.insight_cost)} Insight to increase ${stringFromUnknown(resource.label)} by 1.`,
                  }),
                )
              ) : (
                <article className="detail-card">
                  <p className="meta">No Yin/Yang resources are recorded on this sheet yet.</p>
                </article>
              )}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-conditioning">
            <div className="section-heading">
              <h2>Conditioning</h2>
            </div>
            <div className="feature-stack">
              <article className="feature-row cultivation-card">
                <div className="feature-row__header">
                  <h3>HP</h3>
                  <p className="meta">
                    Current max {numberFromUnknown(cultivation.conditioning.hp.max)} / Cap {numberFromUnknown(cultivation.conditioning.hp.cap)}
                  </p>
                </div>
                {renderActionForm(
                  "spend_conditioning",
                  "Increase HP",
                  <>
                    <input type="hidden" name="conditioning_target" value="hp" />
                    <p className="meta">
                      Spend {numberFromUnknown(cultivation.conditioning.hp.insight_cost)} Insight to increase HP maximum by{" "}
                      {numberFromUnknown(cultivation.conditioning.hp.hp_increase)}.
                    </p>
                    <label className="field">
                      <span>Notes</span>
                      <textarea name="conditioning_notes" rows={2} />
                    </label>
                  </>,
                  {
                    disabled:
                      !boolFromUnknown(cultivation.conditioning.hp.has_enough_insight) ||
                      !boolFromUnknown(cultivation.conditioning.hp.can_increase),
                  },
                )}
              </article>
              {cultivation.conditioning.efforts.map((effort) => (
                <article className="feature-row cultivation-card" key={stringFromUnknown(effort.key)}>
                  <div className="feature-row__header">
                    <h3>{stringFromUnknown(effort.label)}</h3>
                    <p className="meta">Current score {numberFromUnknown(effort.score)}</p>
                  </div>
                  {renderActionForm(
                    "spend_conditioning",
                    `Increase ${stringFromUnknown(effort.label)}`,
                    <>
                      <input type="hidden" name="conditioning_target" value="effort" />
                      <input type="hidden" name="effort_key" value={stringFromUnknown(effort.key)} />
                      <p className="meta">
                        Spend {numberFromUnknown(effort.insight_cost)} Insight to add {numberFromUnknown(effort.effort_increase)}{" "}
                        {stringFromUnknown(effort.label)} points.
                      </p>
                      <label className="field">
                        <span>Notes</span>
                        <textarea name="conditioning_notes" rows={2} />
                      </label>
                    </>,
                    { disabled: !boolFromUnknown(effort.has_enough_insight) },
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-training">
            <div className="section-heading">
              <h2>Training</h2>
            </div>
            <div className="feature-stack">
              <article className="feature-row cultivation-card">
                <div className="feature-row__header">
                  <h3>Stance</h3>
                  <p className="meta">
                    Current max {numberFromUnknown(cultivation.training.stance.max)} / Cap {numberFromUnknown(cultivation.training.stance.cap)}
                  </p>
                </div>
                {renderActionForm(
                  "spend_training",
                  "Increase Stance",
                  <>
                    <input type="hidden" name="training_target" value="stance" />
                    <p className="meta">
                      Spend {numberFromUnknown(cultivation.training.stance.insight_cost)} Insight to increase Stance maximum by{" "}
                      {numberFromUnknown(cultivation.training.stance.stance_increase)}.
                    </p>
                    <label className="field">
                      <span>Notes</span>
                      <textarea name="training_notes" rows={2} />
                    </label>
                  </>,
                  {
                    disabled:
                      !boolFromUnknown(cultivation.training.stance.has_enough_insight) ||
                      !boolFromUnknown(cultivation.training.stance.can_increase),
                  },
                )}
              </article>
              {cultivation.training.attributes.map((attribute) => (
                <article className="feature-row cultivation-card" key={stringFromUnknown(attribute.key)}>
                  <div className="feature-row__header">
                    <h3>{stringFromUnknown(attribute.label)}</h3>
                    <p className="meta">Current score {numberFromUnknown(attribute.score)}</p>
                  </div>
                  {renderActionForm(
                    "spend_training",
                    `Increase ${stringFromUnknown(attribute.label)}`,
                    <>
                      <input type="hidden" name="training_target" value="attribute" />
                      <input type="hidden" name="attribute_key" value={stringFromUnknown(attribute.key)} />
                      <p className="meta">
                        Spend {numberFromUnknown(attribute.insight_cost)} Insight to add {numberFromUnknown(attribute.attribute_increase)}{" "}
                        {stringFromUnknown(attribute.label)} points.
                      </p>
                      <label className="field">
                        <span>Notes</span>
                        <textarea name="training_notes" rows={2} />
                      </label>
                    </>,
                    { disabled: !boolFromUnknown(attribute.has_enough_insight) },
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-martial-arts">
            <div className="section-heading">
              <h2>Martial Arts</h2>
            </div>
            {renderMartialArts(cultivation)}
          </section>

          <section className="read-section" id="xianxia-cultivation-techniques">
            <div className="section-heading">
              <h2>Generic Techniques</h2>
            </div>
            {renderGenericTechniques(cultivation)}
          </section>

          {renderRealmAscension(cultivation)}

          <section className="read-section" id="xianxia-cultivation-history">
            <div className="section-heading">
              <h2>Advancement History</h2>
            </div>
            {cultivation.history.length ? (
              <div className="feature-stack">
                {cultivation.history.map((event) => (
                  <article className="feature-row" key={`${event.index}-${event.action}`}>
                    <div className="feature-row__header">
                      <h3>{event.action}</h3>
                      <p className="meta">Entry {event.index}</p>
                    </div>
                    {event.details?.length ? (
                      <ul className="plain-list slot-list">
                        {event.details.map((detail) => (
                          <li key={`${detail.label}-${detail.value}`}>
                            <strong>{detail.label}:</strong> {detail.value}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <article className="detail-card">
                <p className="meta">No advancement history is recorded on this sheet yet.</p>
              </article>
            )}
          </section>
        </>
      ) : null}
    </>
  );
}

function getApiErrorMessage(error: unknown): ApiMessageEnvelope | null {
  if (isApiError(error)) {
    return { status: error.status, message: error.message };
  }
  if (error instanceof Error) {
    return { status: 0, message: error.message };
  }
  return null;
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

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "N/A";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function resolveArticleImage(slug: string, article: SessionArticle): string {
  if (article.image?.url) {
    return article.image.url;
  }
  return `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${article.id}/image`;
}

function renderArticleBody(article: SessionArticle, extraClassName = ""): JSX.Element {
  const className = `article-body${extraClassName ? ` ${extraClassName}` : ""}`;
  if (article.body_format === "html") {
    return <div className={`${className} html-body`} dangerouslySetInnerHTML={{ __html: article.body_markdown }} />;
  }
  return <pre className={`${className} markdown-body`}>{article.body_markdown}</pre>;
}

function getArticleUrl(value: string | null | undefined): string {
  return typeof value === "string" && value.trim() ? value : "";
}

function getArticleSourceKindLabel(article: SessionArticle): string {
  if (article.source?.label) {
    return article.source.label;
  }
  if (article.source_kind === "page") {
    return "published wiki page";
  }
  if (article.source_kind === "systems") {
    return "Systems entry";
  }
  return article.source_kind || "";
}

function SessionArticleSourceLine({ article }: { article: SessionArticle }) {
  const sourceTitle = article.source?.title?.trim() || "";
  const sourceKind = article.source_kind?.trim() || "";
  const sourceUrl = getArticleUrl(article.links?.source_url);
  const sourceLabel = getArticleSourceKindLabel(article);

  if (sourceTitle) {
    return (
      <p className="article-context">
        Pulled from {sourceLabel || "source"}:{" "}
        {sourceUrl ? <a href={sourceUrl}>{sourceTitle}</a> : sourceTitle}
      </p>
    );
  }

  if (sourceKind && article.source?.missing_message) {
    return <p className="article-context">{article.source.missing_message}</p>;
  }

  return null;
}

function SessionArticleReferenceActions({
  article,
  includePromotionLinks,
}: {
  article: SessionArticle;
  includePromotionLinks: boolean;
}) {
  const sourceUrl = getArticleUrl(article.links?.source_url);
  const sourceKind = article.source_kind?.trim() || "";
  if (sourceUrl) {
    return (
      <a className="ghost-button" href={sourceUrl}>
        {article.source?.action_label || "View source"}
      </a>
    );
  }

  if (sourceKind) {
    return article.source?.missing_message ? <span className="meta">{article.source.missing_message}</span> : null;
  }

  const publishedPageUrl = getArticleUrl(article.links?.published_page_url);
  if (publishedPageUrl) {
    return (
      <a className="ghost-button" href={publishedPageUrl}>
        View published page
      </a>
    );
  }

  const convertedTitle = article.converted_page?.title?.trim() || "";
  if (convertedTitle) {
    const revealAfterSession = article.converted_page?.reveal_after_session;
    return (
      <span className="meta">
        Converted to {convertedTitle}
        {revealAfterSession !== null && revealAfterSession !== undefined ? `; visible after session ${revealAfterSession}` : ""}.
      </span>
    );
  }

  if (!includePromotionLinks) {
    return null;
  }

  const editorUrl = getArticleUrl(article.links?.player_wiki_editor_url);
  const convertUrl = getArticleUrl(article.links?.convert_url);

  return (
    <>
      {editorUrl ? (
        <a className="ghost-button" href={editorUrl}>
          Open in Player Wiki editor
        </a>
      ) : null}
      {convertUrl ? (
        <a className="ghost-button" href={convertUrl}>
          Convert to wiki page
        </a>
      ) : null}
    </>
  );
}

function CharacterDetailDialog({
  detail,
  onClose,
}: {
  detail: CharacterDetailDialogState | null;
  onClose: () => void;
}) {
  if (!detail) {
    return null;
  }
  return (
    <div className="detail-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="detail-modal"
        role="dialog"
        aria-modal="true"
        aria-label={detail.title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <p className="meta">{detail.eyebrow}</p>
            <h3>{detail.title}</h3>
          </div>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </header>
        {detail.badges?.length ? (
          <div className="badge-list">
            {detail.badges.map((badge) => (
              <span className="meta-badge" key={badge}>
                {badge}
              </span>
            ))}
          </div>
        ) : null}
        {detail.facts?.length ? (
          <dl className="detail-facts">
            {detail.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {detail.href ? (
          <p className="meta">
            <a href={detail.href}>Open source entry</a>
          </p>
        ) : null}
        {detail.notes ? <p>{detail.notes}</p> : null}
        {detail.html ? (
          <div className="article-body html-body detail-html" dangerouslySetInnerHTML={{ __html: detail.html }} />
        ) : (
          <p className="meta">No linked detail text is available yet.</p>
        )}
      </section>
    </div>
  );
}

function ApiErrorNotice({
  isLoading,
  message,
  onAuth,
}: {
  isLoading: boolean;
  message: ApiMessageEnvelope | null;
  onAuth: () => void;
}) {
  if (isLoading) {
    return <p className="status status-neutral">Loading ...</p>;
  }
  if (!message) {
    return null;
  }
  if (message.status === 401) {
    return (
      <p className="status status-error">
        {message.message}
        <button type="button" className="link-like-button" onClick={onAuth}>
          Open sign-in
        </button>
      </p>
    );
  }
  return <p className="status status-error">{message.message}</p>;
}

function CampaignGlobalSearch({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [query, setQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [results, setResults] = useState<CampaignReferenceSearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isDialogOpen, setDialogOpen] = useState(false);

  const searchDebounceTimer = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const searchAbortController = useRef<AbortController | null>(null);
  const previewAbortController = useRef<AbortController | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  const clearSearchState = (status: string) => {
    setStatusMessage(status);
    setResults([]);
    setShowResults(false);
  };

  const clearPendingSearch = () => {
    if (searchDebounceTimer.current !== null) {
      window.clearTimeout(searchDebounceTimer.current);
      searchDebounceTimer.current = null;
    }
    if (searchAbortController.current) {
      searchAbortController.current.abort();
      searchAbortController.current = null;
    }
  };

  const runSearch = async (rawQuery: string) => {
    const trimmedQuery = rawQuery.trim();
    if (!trimmedQuery) {
      clearSearchState("");
      return;
    }
    if (trimmedQuery.length < 2) {
      clearSearchState("Type at least 2 letters to search.");
      return;
    }

    if (searchAbortController.current) {
      searchAbortController.current.abort();
    }
    const controller = new AbortController();
    searchAbortController.current = controller;
    setStatusMessage("Searching...");
    setShowResults(false);

    try {
      const response = await apiClient.searchCampaignReferences(campaignSlug, trimmedQuery, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setResults(response.results);
      setShowResults(response.results.length > 0);
      setStatusMessage(response.message || "Search complete.");
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setResults([]);
      setShowResults(false);
      setStatusMessage("Could not search campaign references right now.");
    } finally {
      if (searchAbortController.current === controller) {
        searchAbortController.current = null;
      }
    }
  };

  const onQuerySubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearPendingSearch();
    void runSearch(query);
  };

  const onQueryInput = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.currentTarget.value;
    if (searchAbortController.current) {
      searchAbortController.current.abort();
      searchAbortController.current = null;
    }
    setQuery(next);
    setStatusMessage("");
    clearSearchState("");
    if (searchDebounceTimer.current !== null) {
      window.clearTimeout(searchDebounceTimer.current);
      searchDebounceTimer.current = null;
    }
    const trimmedQuery = next.trim();
    if (!trimmedQuery) {
      return;
    }
    if (trimmedQuery.length < 2) {
      setStatusMessage("Type at least 2 letters to search.");
      return;
    }

    searchDebounceTimer.current = window.setTimeout(() => {
      void runSearch(next);
    }, 250);
  };

  const onQueryKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearPendingSearch();
      void runSearch(query);
    }
  };

  const openDialog = () => {
    setDialogOpen(true);
    window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus({ preventScroll: true });
    });
  };

  const closeDialog = () => {
    if (previewAbortController.current) {
      previewAbortController.current.abort();
      previewAbortController.current = null;
    }
    setDialogOpen(false);
    setPreviewError(null);
    setPreviewHtml("");
    setPreviewLoading(false);

    const focusTarget = returnFocusRef.current;
    if (focusTarget && document.contains(focusTarget)) {
      focusTarget.focus({ preventScroll: true });
    }
    returnFocusRef.current = null;
  };

  const openPreview = (result: CampaignReferenceSearchResult, trigger: HTMLElement | null) => {
    const resultId = result.result_id.trim();
    if (!resultId) {
      return;
    }

    returnFocusRef.current = trigger;
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewHtml("");
    openDialog();

    if (previewAbortController.current) {
      previewAbortController.current.abort();
    }
    const controller = new AbortController();
    previewAbortController.current = controller;

    apiClient
      .previewCampaignReference(campaignSlug, resultId, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) {
          return;
        }
        setPreviewHtml(response.preview_html || "");
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isAuthError(error)) {
          setAuthRequired(true);
        }
        setPreviewError("Could not load that reference right now.");
      })
      .finally(() => {
        if (previewAbortController.current === controller) {
          previewAbortController.current = null;
        }
        if (!controller.signal.aborted) {
          setPreviewLoading(false);
        }
      });
  };

  useEffect(() => {
    if (!campaignSlug) {
      setQuery("");
      clearSearchState("");
      return;
    }
    setQuery("");
    clearSearchState("");
    setPreviewError(null);
    setPreviewHtml("");
    setPreviewLoading(false);
    setDialogOpen(false);
    if (previewAbortController.current) {
      previewAbortController.current.abort();
      previewAbortController.current = null;
    }

    return () => {
      clearPendingSearch();
      if (previewAbortController.current) {
        previewAbortController.current.abort();
        previewAbortController.current = null;
      }
    };
  }, [campaignSlug]);

  return (
    <section className="campaign-global-search" aria-label="Global campaign search">
      <form className="campaign-global-search__form" onSubmit={onQuerySubmit}>
        <label className="campaign-global-search__field">
          <span className="sr-only">Search wiki or Systems</span>
          <input
            type="search"
            value={query}
            autoComplete="off"
            placeholder="Search wiki or Systems"
            onChange={onQueryInput}
            onKeyDown={onQueryKeyDown}
          />
        </label>
        <button type="submit">Search</button>
      </form>
      <p className="meta campaign-global-search__status" aria-live="polite">
        {statusMessage}
      </p>
      {showResults ? (
        <div className="campaign-global-search__results">
          <div className="campaign-global-search-result-list">
            {results.map((result) => {
              const meta = result.subtitle ? `${result.kind_label} | ${result.subtitle}` : result.kind_label;
              return (
                <button
                  type="button"
                  className="campaign-global-search-result"
                  key={result.result_id}
                  onClick={(event) => {
                    openPreview(result, event.currentTarget);
                  }}
                >
                  <span className="campaign-global-search-result__title">{result.title}</span>
                  <span className="campaign-global-search-result__meta">{meta}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      {isDialogOpen ? (
        <div className="detail-modal-backdrop" role="presentation" onMouseDown={closeDialog}>
          <section
            className="spell-detail-dialog campaign-global-search-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="campaign-search-preview-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="spell-detail-dialog__panel campaign-global-search-dialog__panel">
              <header className="spell-detail-dialog__header">
                <div>
                  <p className="eyebrow">Reference preview</p>
                  <h2 id="campaign-search-preview-title">Campaign Search</h2>
                </div>
                <button type="button" className="ghost-button" ref={closeButtonRef} onClick={closeDialog}>
                  Close
                </button>
              </header>
              <div
                className="campaign-global-search-dialog__body"
                aria-live="polite"
                aria-busy={previewLoading ? "true" : "false"}
              >
                {previewLoading ? <p className="status status-neutral">Loading reference preview...</p> : null}
                {previewError ? <p className="status status-error">{previewError}</p> : null}
                {previewHtml ? <div dangerouslySetInnerHTML={{ __html: previewHtml }} /> : null}
                {!previewLoading && !previewError && !previewHtml ? (
                  <p className="status status-neutral">No reference preview is available.</p>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function AuthNotice() {
  const { authRequired, setApiToken } = useApiClient();
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  if (!authRequired) {
    return null;
  }

  return (
    <section className="card auth-notice">
      <div className="section-heading">
        <div>
          <h2>Authentication required</h2>
          <p className="status status-error">
            Your cookie or API token did not authenticate this request. Sign in to restore session.
          </p>
        </div>
      </div>
      <div className="hero-actions">
        <a className="button-link" href={signInHref}>
          Sign in
        </a>
        <button type="button" className="ghost-button" onClick={() => setApiToken("")}>
          Continue without token
        </button>
      </div>
    </section>
  );
}

function AppShell() {
  const location = useLocation();
  const [apiToken, setApiToken] = useState(() => {
    try {
      return localStorage.getItem("cpw-pilot-api-token") || "";
    } catch {
      return "";
    }
  });
  const [authRequired, setAuthRequired] = useState(false);
  const [navigationLabel, setNavigationLabel] = useState<string | null>(null);
  const hasMounted = useRef(false);

  const apiClient = useMemo(() => {
    return new CampaignApiClient({
      bearerToken: apiToken,
    });
  }, [apiToken]);

  useEffect(() => {
    if (!hasMounted.current) {
      hasMounted.current = true;
      return;
    }
    void queryClient.invalidateQueries();
  }, [apiToken]);

  const setStoredToken = (next: string) => {
    const trimmed = next.trim();
    setApiToken(trimmed);
    try {
      if (trimmed) {
        localStorage.setItem("cpw-pilot-api-token", trimmed);
      } else {
        localStorage.removeItem("cpw-pilot-api-token");
      }
    } catch {
      // localStorage may be unavailable in private mode.
    }
    if (authRequired) {
      setAuthRequired(false);
    }
  };

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await apiClient.getMe();
      } catch (error) {
        if (isAuthError(error)) {
          return null;
        }
        throw error;
      }
    },
    retry: false,
  });

  const campaignSlug = parseCampaignSlugFromPath(location.pathname);
  const campaignQuery = useQuery({
    queryKey: ["campaign", campaignSlug],
    queryFn: () => apiClient.getCampaign(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(campaignQuery.error) || (Boolean(apiToken) && isAuthError(meQuery.error))) {
      setAuthRequired(true);
    }
  }, [apiToken, campaignQuery.error, meQuery.error, setAuthRequired]);

  useEffect(() => {
    const themeKey = meQuery.data?.preferences?.theme_key;
    if (themeKey) {
      document.documentElement.dataset.theme = themeKey;
    }
  }, [meQuery.data?.preferences?.theme_key]);

  const user = meQuery.data?.user ?? null;
  const preferredFrontendMode = normalizeFrontendMode(meQuery.data?.preferences?.frontend_mode);
  const campaign = campaignQuery.data?.campaign;
  const campaignPermissions = campaignQuery.data?.permissions;
  const campaignVisibility = campaignQuery.data?.visibility;
  const encodedCampaignSlug = encodeURIComponent(campaignSlug);

  const navItems = useMemo(
    () => [
      {
        href: campaignRouteHref(campaignSlug, "", preferredFrontendMode),
        label: "Campaign Home",
        isGen2: preferredFrontendMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "campaign"),
      },
      {
        href: campaignRouteHref(campaignSlug, "session", preferredFrontendMode),
        label: "Session",
        isGen2: preferredFrontendMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "session"),
      },
      {
        href: campaignRouteHref(campaignSlug, "combat", preferredFrontendMode),
        label: "Combat",
        isGen2: preferredFrontendMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "combat"),
      },
      {
        href: campaignRouteHref(campaignSlug, "characters", preferredFrontendMode),
        label: "Characters",
        isGen2: preferredFrontendMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "characters"),
      },
      {
        href: campaignRouteHref(campaignSlug, "systems", preferredFrontendMode),
        label: "Systems",
        isGen2: preferredFrontendMode === "gen2",
        show: campaignVisibilityCanAccess(campaignVisibility, "systems"),
      },
      {
        href: campaignRouteHref(campaignSlug, "dm-content", preferredFrontendMode),
        label: "DM Content",
        isGen2: preferredFrontendMode === "gen2",
        show:
          campaignVisibilityCanAccess(campaignVisibility, "dm_content")
          || campaignPermissions?.can_manage_dm_content === true
          || campaignPermissions?.can_manage_content === true,
      },
      {
        href: campaignRouteHref(campaignSlug, "control", preferredFrontendMode),
        label: "Control",
        isGen2: preferredFrontendMode === "gen2",
        show: campaignPermissions?.can_manage_visibility === true,
      },
      {
        href: campaignRouteHref(campaignSlug, "help", preferredFrontendMode),
        label: "Help",
        isGen2: preferredFrontendMode === "gen2",
        show: Boolean(campaignQuery.data),
      },
    ],
    [
      campaignPermissions?.can_manage_content,
      campaignPermissions?.can_manage_dm_content,
      campaignPermissions?.can_manage_visibility,
      campaignQuery.data,
      campaignVisibility,
      campaignSlug,
      preferredFrontendMode,
    ],
  );

  const visibleNavItems = navItems.filter((entry) => entry.show);
  const nextUrl = `${window.location.pathname}${window.location.search}`;
  const signInHref = `/sign-in?next=${encodeURIComponent(nextUrl)}`;
  const currentAppPath = `/app-next${location.pathname}`;
  const campaignBasePath = `/app-next/campaigns/${encodedCampaignSlug}`;
  const isNavItemActive = (label: string, href: string) => {
    if (label === "Campaign Home") {
      return currentAppPath === campaignBasePath;
    }
    if (label === "Session") {
      return currentAppPath === `${campaignBasePath}/session`;
    }
    if (label === "Combat") {
      return currentAppPath.startsWith(`${campaignBasePath}/combat`);
    }
    if (label === "Characters") {
      return currentAppPath.startsWith(`${campaignBasePath}/characters`);
    }
    if (label === "Systems") {
      return currentAppPath.startsWith(`${campaignBasePath}/systems`);
    }
    if (label === "DM Content") {
      return currentAppPath.startsWith(`${campaignBasePath}/dm-content`);
    }
    if (label === "Control") {
      return currentAppPath === `${campaignBasePath}/control`;
    }
    if (label === "Help") {
      return currentAppPath === `${campaignBasePath}/help`;
    }
    return currentAppPath === href || currentAppPath.startsWith(`${href}/`);
  };

  return (
    <ApiClientContext.Provider
      value={{
        apiClient,
        apiToken,
        setApiToken: setStoredToken,
        authRequired,
        setAuthRequired,
        preferredFrontendMode,
        user,
      }}
    >
      <div className="session-shell">
        <header className={campaign ? "topbar topbar--campaign" : "topbar"}>
          <div className="brand-block">
            <Link to="/" className="brand-link">
              Campaign Player Wiki
            </Link>
          </div>
          {campaign ? (
            <div className="topbar-campaign" aria-label="Current campaign">
              <span>{campaign.title}</span>
            </div>
          ) : null}
          <div className="topbar-controls">
            <details className="api-token-details">
              <summary>API token</summary>
              <label className="token-row" htmlFor="pilot-api-token">
                <span>Optional bearer token for API-only testing</span>
                <input
                  id="pilot-api-token"
                  type="password"
                  value={apiToken}
                  placeholder="Bearer token"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    setStoredToken(event.currentTarget.value);
                  }}
                />
              </label>
            </details>
            <div className="account-row">
              {user ? (
                <>
                  {user.is_admin ? (
                    <a className="header-link" href="/app-next/admin">
                      Admin
                    </a>
                  ) : null}
                  <a className="header-link" href="/app-next/account">
                    Account
                  </a>
                  <span className="user-badge">
                    {user.display_name}
                    {user.is_admin ? <span className="meta">Admin</span> : null}
                  </span>
                  <form method="post" action="/sign-out">
                    <button type="submit" className="ghost-button">
                      Sign out
                    </button>
                  </form>
                </>
              ) : (
                <a className="ghost-button" href={signInHref}>
                  Sign in
                </a>
              )}
            </div>
          </div>
        </header>
        {campaign ? (
          <div className="campaign-nav-row">
            <nav className="campaign-nav-strip" aria-label="Campaign navigation">
              {visibleNavItems.map((item) => (
                <a
                  key={item.label}
                  className={isNavItemActive(item.label, item.href) ? "campaign-nav-link is-active" : "campaign-nav-link"}
                  href={item.href}
                  onClick={() => {
                    if (!item.isGen2) {
                      setNavigationLabel(item.label);
                    }
                  }}
                >
                  {item.label}
                </a>
              ))}
            </nav>
            {navigationLabel ? (
              <p className="navigation-status" role="status">
                Loading {navigationLabel}...
              </p>
            ) : null}
          </div>
        ) : null}
        {campaign ? <CampaignGlobalSearch campaignSlug={campaignSlug} /> : null}
        <AuthNotice />
        <main className="main-shell">
          <Outlet />
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}

function CampaignListPage() {
  const { apiClient, setAuthRequired, preferredFrontendMode, user } = useApiClient();

  const campaignRoleLabel = (value: string) =>
    value
      .replace(/_/g, " ")
      .split(" ")
      .filter(Boolean)
      .map((segment) => `${segment[0].toUpperCase()}${segment.slice(1)}`)
      .join(" ");

  const appQuery = useQuery({
    queryKey: ["app"],
    queryFn: () => apiClient.getAppState(),
    retry: false,
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiClient.getCampaigns(),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(appQuery.error) || isAuthError(campaignsQuery.error)) {
      setAuthRequired(true);
    }
  }, [appQuery.error, campaignsQuery.error, setAuthRequired]);

  const appError = getApiErrorMessage(appQuery.error);
  const campaignError = getApiErrorMessage(campaignsQuery.error);
  const campaigns: CampaignEntry[] = campaignsQuery.data?.campaigns ?? [];
  const campaignPickerHeroEyebrow = user
    ? "Campaign access"
    : "Campaign wiki";
  const campaignPickerHeadline = user
    ? "Select a campaign."
    : "Browse available campaigns.";
  const campaignPickerLede = user
    ? "Your account can see the campaigns listed here based on app-wide admin access, campaign membership, or public visibility."
    : "Public campaign wiki pages are available without signing in. Use an account only when you need admin or character access.";
  const emptyHeading = user ? "No campaign access assigned" : "No public campaigns available";
  const emptyLede = user
    ? "Your account is active, but it is not currently assigned to any campaigns."
    : "There are currently no public campaign wiki pages to browse.";

  return (
    <>
      <section className="hero compact campaign-picker-hero">
        <p className="eyebrow">{campaignPickerHeroEyebrow}</p>
        <h1>{campaignPickerHeadline}</h1>
        <p className="lede">
          {campaignPickerLede}
        </p>
      </section>
      <ApiErrorNotice
        isLoading={appQuery.isLoading || campaignsQuery.isLoading}
        message={appError ?? campaignError}
        onAuth={() => setAuthRequired(true)}
      />
      <section className="grid campaign-picker-grid">
        {campaigns.map((entry) => (
          <article className="card campaign-card" key={entry.campaign.slug}>
            <p className="card-kicker">{campaignRoleLabel(entry.role)}</p>
            <h2>{entry.campaign.title}</h2>
            <p>{entry.campaign.summary}</p>
            {entry.campaign.system ? <p className="meta">System: {entry.campaign.system}</p> : null}
            {entry.campaign.current_session !== null && entry.campaign.current_session !== undefined ? (
              <p className="meta">Visible through session {entry.campaign.current_session}</p>
            ) : null}
            <a className="button-link" href={campaignRouteHref(entry.campaign.slug, "", preferredFrontendMode)}>
              Open campaign
            </a>
          </article>
        ))}
      </section>
      {!appQuery.isLoading && !campaignsQuery.isLoading && !campaigns.length && !campaignError ? (
        <section className="card auth-card campaign-picker-empty">
          <h2>{emptyHeading}</h2>
          <p>{emptyLede}</p>
        </section>
      ) : null}
    </>
  );
}

function adminSearch(search: string): string {
  return search.startsWith("?") ? search : search ? `?${search}` : "";
}

function AdminActivityFilters({
  action,
  clearHref,
  data,
}: {
  action: string;
  clearHref: string;
  data: Pick<AdminDashboardResponse, "activity_filters" | "audit_event_type_choices" | "campaign_choices" | "export_url">;
}) {
  return (
    <form method="get" action={action} className="audit-filter-form admin-filter-form">
      <label className="field">
        <span>Search</span>
        <input
          type="text"
          name="audit_q"
          defaultValue={data.activity_filters.query}
          placeholder="user, campaign, character, event"
        />
      </label>
      <label className="field">
        <span>Event</span>
        <select name="audit_event_type" defaultValue={data.activity_filters.event_type}>
          <option value="">All events</option>
          {data.audit_event_type_choices.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Campaign</span>
        <select name="audit_campaign_slug" defaultValue={data.activity_filters.campaign_slug}>
          <option value="">All campaigns</option>
          {data.campaign_choices.map((campaign) => (
            <option key={campaign.slug} value={campaign.slug}>
              {campaign.title}
            </option>
          ))}
        </select>
      </label>
      <div className="audit-filter-form__actions">
        <button type="submit" className="button">
          Filter activity
        </button>
        <a className="ghost-button" href={clearHref}>
          Clear
        </a>
        <a className="ghost-button" href={data.export_url}>
          Export CSV
        </a>
      </div>
    </form>
  );
}

function AdminActivityList({ events }: { events: AdminAuditEvent[] }) {
  if (!events.length) {
    return <p className="meta">No audit activity matched the current filters.</p>;
  }

  return (
    <ul className="plain-list audit-list admin-audit-list">
      {events.map((event) => (
        <li
          key={event.id}
          className="audit-row admin-audit-row"
          data-event-type={event.event_type}
          data-campaign-slug={event.campaign_slug}
          data-character-slug={event.character_slug}
          data-actor-email={event.actor_email}
          data-target-email={event.target_email}
        >
          <div className="audit-row__header">
            <strong>{event.title}</strong>
            <span className="meta">{event.timestamp}</span>
          </div>
          <p className="meta">
            {event.actor ? (
              <>
                <a href={event.actor.href}>{event.actor.label}</a>
                {event.actor.meta ? <span> {event.actor.meta}</span> : null}
              </>
            ) : (
              "System"
            )}
            {event.target && (!event.actor || event.target.href !== event.actor.href) ? (
              <>
                {" -> "}
                <a href={event.target.href}>{event.target.label}</a>
                {event.target.meta ? <span> {event.target.meta}</span> : null}
              </>
            ) : null}
          </p>
          {event.scope ? <p className="meta">{event.scope}</p> : null}
          {event.details ? <p>{event.details}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function AdminPagination({ pagination }: Pick<AdminDashboardResponse, "pagination">) {
  return (
    <div className="pagination-bar admin-pagination">
      <p className="meta">
        Page {pagination.current_page} of {pagination.total_pages}
      </p>
      <div className="pagination-bar__actions">
        {pagination.has_previous ? (
          <a className="ghost-button" href={pagination.previous_url}>
            Previous
          </a>
        ) : null}
        {pagination.has_next ? (
          <a className="ghost-button" href={pagination.next_url}>
            Next
          </a>
        ) : null}
      </div>
    </div>
  );
}

function AdminDashboardPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  useLocation();
  const currentSearch = window.location.search;
  const [inviteDraft, setInviteDraft] = useState<AdminInvitePayload>({
    email: "",
    display_name: "",
    user_type: "player",
    campaign_slug: "",
  });
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const dashboardQuery = useQuery({
    queryKey: ["admin-dashboard", currentSearch],
    queryFn: () => apiClient.getAdminDashboard(adminSearch(currentSearch)),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(dashboardQuery.error)) {
      setAuthRequired(true);
    }
  }, [dashboardQuery.error, setAuthRequired]);

  useEffect(() => {
    const defaults = dashboardQuery.data?.invite_form_defaults;
    if (!defaults) {
      return;
    }
    setInviteDraft((current) => ({
      ...current,
      user_type: current.user_type || defaults.user_type,
      campaign_slug: current.campaign_slug || defaults.campaign_slug,
    }));
  }, [dashboardQuery.data?.invite_form_defaults]);

  const inviteMutation = useMutation({
    mutationFn: (payload: AdminInvitePayload) => apiClient.inviteAdminUser(payload),
    onSuccess: (response) => {
      setErrorMessage("");
      setStatusMessage(response.message || "Invite created.");
      setInviteDraft((current) => ({
        ...current,
        email: "",
        display_name: "",
      }));
      queryClient.setQueryData(["admin-user", response.managed_user.id, ""], response);
      void queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setStatusMessage("");
      setErrorMessage(apiErrorMessage(error));
    },
  });

  const queryError = getApiErrorMessage(dashboardQuery.error);
  const data = dashboardQuery.data;

  return (
    <>
      <section className="hero compact admin-hero">
        <p className="eyebrow">Admin</p>
        <h1>Admin dashboard</h1>
        <p className="lede">Use this screen for lighter operational work. The CLI remains the full-control path for bootstrap and recovery.</p>
      </section>

      <ApiErrorNotice isLoading={dashboardQuery.isLoading} message={queryError} onAuth={() => setAuthRequired(true)} />
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}

      {data ? (
        <>
          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Invite user</h2>
              <form
                className="stack-form admin-panel-form"
                onSubmit={(event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  inviteMutation.mutate(inviteDraft);
                }}
              >
                <label className="field">
                  <span>Email</span>
                  <input
                    id="admin-invite-email"
                    name="email"
                    type="email"
                    required
                    value={inviteDraft.email}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, email: value }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>Display name</span>
                  <input
                    id="admin-invite-display-name"
                    name="display_name"
                    type="text"
                    required
                    value={inviteDraft.display_name}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, display_name: value }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>User type</span>
                  <select
                    id="admin-invite-user-type"
                    name="user_type"
                    value={inviteDraft.user_type}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, user_type: value }));
                    }}
                  >
                    <option value="admin">Admin</option>
                    <option value="dm">DM</option>
                    <option value="player">Player</option>
                    <option value="standard">Standard user</option>
                  </select>
                </label>
                <label className="field">
                  <span>Campaign for DM or Player</span>
                  <select
                    id="admin-invite-campaign-slug"
                    name="campaign_slug"
                    value={inviteDraft.campaign_slug || ""}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, campaign_slug: value }));
                    }}
                  >
                    {data.campaign_choices.length ? (
                      data.campaign_choices.map((campaign) => (
                        <option key={campaign.slug} value={campaign.slug}>
                          {campaign.title}
                        </option>
                      ))
                    ) : (
                      <option value="">No campaigns available</option>
                    )}
                  </select>
                </label>
                <p className="meta">Admin is app-wide. DM and Player invites also create an active membership in the selected campaign.</p>
                <div className="admin-form-actions">
                  <button type="submit" className="button" disabled={inviteMutation.isPending}>
                    {inviteMutation.isPending ? "Creating..." : "Create invite"}
                  </button>
                </div>
              </form>
            </article>

            <aside className="card admin-panel">
              <h2>Campaigns</h2>
              <ul className="plain-list">
                {data.campaign_choices.map((campaign) => (
                  <li key={campaign.slug}>
                    {campaign.title} <span className="meta">({campaign.slug})</span>
                  </li>
                ))}
              </ul>
            </aside>
          </section>

          <section className="section-list admin-user-section">
            <div className="section-heading">
              <h2>Users</h2>
              <p className="meta">{data.user_cards.length} total</p>
            </div>
            <div className="grid admin-user-grid">
              {data.user_cards.map((user) => (
                <article key={user.id} className="card admin-user-card">
                  <p className="card-kicker">
                    {user.status}
                    {user.is_admin ? " | Admin" : ""}
                  </p>
                  <h3>
                    <a href={user.href}>{user.display_name}</a>
                  </h3>
                  <p>{user.email}</p>
                  {user.membership_summary.length ? <p className="meta">{user.membership_summary.join(" | ")}</p> : null}
                  {user.assignment_summary.length ? <p className="meta">Assignments: {user.assignment_summary.join(", ")}</p> : null}
                </article>
              ))}
            </div>
          </section>

          <section className="section-list admin-activity-section">
            <div className="section-heading">
              <h2>Recent activity</h2>
              <p className="meta">{data.pagination.total_events} matching events</p>
            </div>
            <article className="card admin-panel admin-activity-panel">
              <AdminActivityFilters action="/app-next/admin" clearHref="/app-next/admin" data={data} />
              <AdminActivityList events={data.recent_audit_events} />
              <AdminPagination pagination={data.pagination} />
            </article>
          </section>
        </>
      ) : null}
    </>
  );
}

function AdminUserDetailPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  const params = useParams({ from: "/admin/users/$userId" });
  useLocation();
  const currentSearch = window.location.search;
  const userId = Number(params.userId);
  const [membershipDraft, setMembershipDraft] = useState({ campaign_slug: "", role: "player", status: "active" });
  const [assignmentDraft, setAssignmentDraft] = useState({ character_ref: "" });
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const userQuery = useQuery({
    queryKey: ["admin-user", userId, currentSearch],
    queryFn: () => apiClient.getAdminUser(userId, adminSearch(currentSearch)),
    enabled: Number.isFinite(userId),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(userQuery.error)) {
      setAuthRequired(true);
    }
  }, [userQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!userQuery.data) {
      return;
    }
    setMembershipDraft(userQuery.data.membership_form_defaults);
    setAssignmentDraft(userQuery.data.assignment_form_defaults);
  }, [userQuery.data?.membership_form_defaults, userQuery.data?.assignment_form_defaults]);

  const handleDetailSuccess = (response: AdminUserDetailResponse) => {
    setErrorMessage("");
    setStatusMessage(response.message || "Admin user saved.");
    queryClient.setQueryData(["admin-user", response.managed_user.id, currentSearch], response);
    void queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["me"] });
  };

  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage("");
    setErrorMessage(apiErrorMessage(error));
  };

  const setMembership = useMutation({
    mutationFn: () => apiClient.setAdminUserMembership(userId, membershipDraft),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const removeMembership = useMutation({
    mutationFn: (membership: AdminMembership) => apiClient.removeAdminUserMembership(userId, { campaign_slug: membership.campaign_slug }),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const assignCharacter = useMutation({
    mutationFn: () => apiClient.assignAdminUserCharacter(userId, assignmentDraft),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const removeAssignment = useMutation({
    mutationFn: (assignment: AdminAssignment) => apiClient.removeAdminUserCharacterAssignment(userId, {
      campaign_slug: assignment.campaign_slug,
      character_slug: assignment.character_slug,
    }),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const issueInvite = useMutation({
    mutationFn: () => apiClient.issueAdminUserInvite(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const issuePasswordReset = useMutation({
    mutationFn: () => apiClient.issueAdminUserPasswordReset(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const disableUser = useMutation({
    mutationFn: () => apiClient.disableAdminUser(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const enableUser = useMutation({
    mutationFn: () => apiClient.enableAdminUser(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });
  const deleteUser = useMutation({
    mutationFn: () => apiClient.deleteAdminUser(userId, { confirm_email: deleteConfirm }),
    onSuccess: (response) => {
      setErrorMessage("");
      setStatusMessage(response.message || "User deleted.");
      void queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
      window.location.assign("/app-next/admin");
    },
    onError: handleMutationError,
  });

  const data = userQuery.data;
  const queryError = getApiErrorMessage(userQuery.error);
  const mutationPending =
    setMembership.isPending
    || removeMembership.isPending
    || assignCharacter.isPending
    || removeAssignment.isPending
    || issueInvite.isPending
    || issuePasswordReset.isPending
    || disableUser.isPending
    || enableUser.isPending
    || deleteUser.isPending;

  return (
    <>
      <section className="hero compact admin-hero">
        <p className="eyebrow">Admin user detail</p>
        <h1>{data?.managed_user.display_name || "Admin user"}</h1>
        {data ? (
          <>
            <p className="lede">{data.managed_user.email}</p>
            <p className="meta">
              Status: {data.managed_user.status}
              {data.managed_user.is_admin ? " | App admin" : ""}
            </p>
            <div className="hero-actions">
              <a className="ghost-button" href={data.links.gen2_admin_url}>
                Back to admin dashboard
              </a>
            </div>
          </>
        ) : null}
      </section>

      <ApiErrorNotice isLoading={userQuery.isLoading} message={queryError} onAuth={() => setAuthRequired(true)} />
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}

      {data ? (
        <>
          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Campaign membership</h2>
              <form
                className="stack-form admin-panel-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  setMembership.mutate();
                }}
              >
                <label className="field">
                  <span>Campaign</span>
                  <select
                    id="admin-membership-campaign-slug"
                    name="campaign_slug"
                    required
                    value={membershipDraft.campaign_slug}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setMembershipDraft((current) => ({ ...current, campaign_slug: value }));
                    }}
                  >
                    {data.campaign_choices.map((campaign) => (
                      <option key={campaign.slug} value={campaign.slug}>
                        {campaign.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Role</span>
                  <select
                    id="admin-membership-role"
                    name="role"
                    required
                    value={membershipDraft.role}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setMembershipDraft((current) => ({ ...current, role: value }));
                    }}
                  >
                    <option value="dm">DM</option>
                    <option value="player">Player</option>
                    <option value="observer">Observer</option>
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select
                    id="admin-membership-status"
                    name="status"
                    required
                    value={membershipDraft.status}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setMembershipDraft((current) => ({ ...current, status: value }));
                    }}
                  >
                    <option value="active">Active</option>
                    <option value="invited">Invited</option>
                    <option value="removed">Removed</option>
                  </select>
                </label>
                <div className="admin-form-actions">
                  <button type="submit" className="button" disabled={mutationPending || !membershipDraft.campaign_slug}>
                    {setMembership.isPending ? "Saving..." : "Save membership"}
                  </button>
                </div>
              </form>
            </article>

            <article className="card admin-panel">
              <h2>Character assignment</h2>
              <p className="meta">Assignments require an active player membership in the same campaign.</p>
              <form
                className="stack-form admin-panel-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  assignCharacter.mutate();
                }}
              >
                <label className="field">
                  <span>Character</span>
                  <select
                    id="admin-assignment-character-ref"
                    name="character_ref"
                    required
                    value={assignmentDraft.character_ref}
                    onChange={(event) => {
                      setAssignmentDraft({ character_ref: event.currentTarget.value });
                    }}
                  >
                    {data.character_choices.map((character) => (
                      <option key={character.value} value={character.value}>
                        {character.label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="admin-form-actions">
                  <button type="submit" className="button" disabled={mutationPending || !assignmentDraft.character_ref}>
                    {assignCharacter.isPending ? "Assigning..." : "Assign character"}
                  </button>
                </div>
              </form>
            </article>
          </section>

          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Current memberships</h2>
              {data.memberships.length ? (
                <ul className="plain-list admin-item-list">
                  {data.memberships.map((membership) => (
                    <li key={membership.id} className="admin-item-row">
                      <div>
                        <strong>{membership.campaign_title}</strong>
                        <span className="meta"> {membership.role} | {membership.status}</span>
                      </div>
                      <div className="admin-item-actions">
                        <a className="ghost-button" href={`${data.links.gen2_user_url}?edit_membership_campaign_slug=${encodeURIComponent(membership.campaign_slug)}`}>
                          Edit
                        </a>
                        {membership.status !== "removed" ? (
                          <button type="button" className="button" disabled={mutationPending} onClick={() => removeMembership.mutate(membership)}>
                            Remove
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No campaign memberships yet.</p>
              )}
            </article>

            <article className="card admin-panel">
              <h2>Current assignments</h2>
              {data.assignments.length ? (
                <ul className="plain-list admin-item-list">
                  {data.assignments.map((assignment) => (
                    <li key={assignment.id} className="admin-item-row">
                      <div>
                        <strong>{assignment.campaign_title}</strong>
                        <span className="meta"> {assignment.character_slug} | {assignment.assignment_type}</span>
                      </div>
                      <div className="admin-item-actions">
                        <a
                          className="ghost-button"
                          href={`${data.links.gen2_user_url}?edit_assignment_campaign_slug=${encodeURIComponent(assignment.campaign_slug)}&edit_assignment_character_slug=${encodeURIComponent(assignment.character_slug)}`}
                        >
                          Edit
                        </a>
                        <button type="button" className="button" disabled={mutationPending} onClick={() => removeAssignment.mutate(assignment)}>
                          Clear
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No character assignments yet.</p>
              )}
            </article>
          </section>

          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Account actions</h2>
              <div className="admin-action-stack admin-action-groups">
                <div className="admin-action-group">
                  <p className="admin-action-group__heading">Credential actions</p>
                  <div className="admin-action-stack">
                    {data.managed_user.status === "invited" ? (
                      <button type="button" className="button" disabled={mutationPending} onClick={() => issueInvite.mutate()}>
                        {issueInvite.isPending ? "Generating..." : "Generate invite link"}
                      </button>
                    ) : null}
                    {data.managed_user.status === "active" ? (
                      <button type="button" className="button" disabled={mutationPending} onClick={() => issuePasswordReset.mutate()}>
                        {issuePasswordReset.isPending ? "Generating..." : "Generate password reset link"}
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="admin-action-group">
                  <p className="admin-action-group__heading">Account state</p>
                  <div className="admin-action-stack">
                    {data.can_manage_account && data.managed_user.status === "disabled" ? (
                      <button type="button" className="button" disabled={mutationPending} onClick={() => enableUser.mutate()}>
                        {enableUser.isPending ? "Saving..." : "Re-enable user"}
                      </button>
                    ) : null}
                    {data.can_manage_account && data.managed_user.status !== "disabled" ? (
                      <button type="button" className="button" disabled={mutationPending} onClick={() => disableUser.mutate()}>
                        {disableUser.isPending ? "Saving..." : "Disable user"}
                      </button>
                    ) : null}
                  </div>
                </div>
                {data.can_manage_account ? (
                  <div className="admin-action-group admin-action-group--danger">
                    <p className="admin-action-group__heading">Destructive actions</p>
                    <div className="admin-danger-box">
                      <label className="field">
                        <span>Confirm delete by email</span>
                        <input
                          id="admin-delete-confirm-email"
                          name="confirm_email"
                          type="text"
                          value={deleteConfirm}
                          onChange={(event) => setDeleteConfirm(event.currentTarget.value)}
                          placeholder={data.managed_user.email}
                        />
                      </label>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={mutationPending || deleteConfirm.trim().toLowerCase() !== data.managed_user.email.toLowerCase()}
                        onClick={() => deleteUser.mutate()}
                      >
                        {deleteUser.isPending ? "Deleting..." : "Delete user"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="status status-error admin-non-admin-note">
                    Use a different admin account or the CLI if you ever need to change the account you are currently using.
                  </p>
                )}
              </div>
            </article>

            <article className="card admin-panel">
              <h2>Recent activity for this user</h2>
              <p className="meta">{data.pagination.total_events} matching events</p>
              <AdminActivityFilters action={data.links.gen2_user_url || `/app-next/admin/users/${userId}`} clearHref={data.links.gen2_user_url || `/app-next/admin/users/${userId}`} data={data} />
              <AdminActivityList events={data.recent_audit_events} />
              <AdminPagination pagination={data.pagination} />
            </article>
          </section>
        </>
      ) : null}
    </>
  );
}

function AccountSettingsPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftThemeKey, setDraftThemeKey] = useState("");
  const [draftChatOrder, setDraftChatOrder] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["account-settings"],
    queryFn: () => apiClient.getAccountSettings(),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(settingsQuery.error)) {
      setAuthRequired(true);
    }
  }, [settingsQuery.error, setAuthRequired]);

  useEffect(() => {
    const preferences = settingsQuery.data?.preferences;
    if (!preferences) {
      return;
    }
    setDraftThemeKey(preferences.theme_key || "");
    setDraftChatOrder(preferences.session_chat_order || "");
  }, [
    settingsQuery.data?.preferences?.theme_key,
    settingsQuery.data?.preferences?.session_chat_order,
  ]);

  const saveSettings = useMutation({
    mutationFn: (payload: AccountSettingsUpdatePayload) => apiClient.patchAccountSettings(payload),
    onSuccess: (response) => {
      setStatusMessage("Account settings saved.");
      setDraftThemeKey(response.preferences.theme_key || "");
      setDraftChatOrder(response.preferences.session_chat_order || "");
      if (response.preferences.theme_key) {
        document.documentElement.dataset.theme = response.preferences.theme_key;
      }
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      void queryClient.invalidateQueries({ queryKey: ["account-settings"] });
    },
    onError: (error) => {
      setStatusMessage(null);
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const error = getApiErrorMessage(settingsQuery.error);
  const saveError = saveSettings.error ? apiErrorMessage(saveSettings.error) : null;
  const preferences = settingsQuery.data?.preferences;
  const themePresets = settingsQuery.data?.theme_presets ?? [];
  const chatOrderChoices = settingsQuery.data?.session_chat_order_choices ?? [];
  const user = settingsQuery.data?.user;
  const selectedTheme = themePresets.find((theme) => theme.key === (preferences?.theme_key || draftThemeKey));
  const hasDraft = Boolean(draftThemeKey || draftChatOrder);
  const isUnchanged =
    draftThemeKey === (preferences?.theme_key || "") &&
    draftChatOrder === (preferences?.session_chat_order || "");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasDraft) {
      return;
    }
    setStatusMessage(null);
    saveSettings.mutate({
      theme_key: draftThemeKey,
      session_chat_order: draftChatOrder,
    });
  };

  return (
    <>
      <section className="hero compact account-hero">
        <p className="eyebrow">Account settings</p>
        <h1>{user?.display_name ?? "Account"}</h1>
        <p className="lede">Save interface preferences to your account and use them everywhere you are signed in.</p>
        <p className="meta">
          Current theme: {selectedTheme?.label ?? preferences?.theme_key ?? "Loading"}
          {user?.is_admin ? " | App admin" : ""}
        </p>
      </section>

      <ApiErrorNotice isLoading={settingsQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {settingsQuery.data ? (
        <section className="page-layout account-layout">
          <article className="card account-panel">
            <form onSubmit={handleSubmit}>
              <section className="account-settings-group">
                <h2>Color theme</h2>
                <p className="meta">These presets restyle the shared app chrome, cards, forms, and reading surfaces.</p>
                <div className="theme-grid">
                  {themePresets.map((theme) => {
                    const inputId = `account-theme-${theme.key}`;
                    const checked = draftThemeKey === theme.key;
                    return (
                      <label className={checked ? "theme-option is-selected" : "theme-option"} htmlFor={inputId} key={theme.key}>
                        <input
                          className="theme-option__input"
                          id={inputId}
                          type="radio"
                          name="theme_key"
                          value={theme.key}
                          checked={checked}
                          onChange={() => setDraftThemeKey(theme.key)}
                        />
                        <span className="theme-option__header">
                          <span>
                            <strong>{theme.label}</strong>
                            {preferences?.theme_key === theme.key ? <span className="meta theme-option__status">Current</span> : null}
                          </span>
                          <span className="theme-option__swatches" aria-hidden="true">
                            {theme.preview_colors.map((color) => (
                              <span className="theme-option__swatch" style={{ background: color }} key={color} />
                            ))}
                          </span>
                        </span>
                        <span className="meta">{theme.description}</span>
                      </label>
                    );
                  })}
                </div>
              </section>

              <section className="account-settings-group">
                <h2>Live session chat order</h2>
                <p className="meta">
                  This changes the order of the live Session chat window for your account only. Stored session logs stay chronological.
                </p>
                <div className="theme-grid">
                  {chatOrderChoices.map((choice) => {
                    const inputId = `account-chat-order-${choice.value}`;
                    const checked = draftChatOrder === choice.value;
                    return (
                      <label className={checked ? "theme-option is-selected" : "theme-option"} htmlFor={inputId} key={choice.value}>
                        <input
                          className="theme-option__input"
                          id={inputId}
                          type="radio"
                          name="session_chat_order"
                          value={choice.value}
                          checked={checked}
                          onChange={() => setDraftChatOrder(choice.value)}
                        />
                        <span className="theme-option__header">
                          <span>
                            <strong>{choice.label}</strong>
                            {preferences?.session_chat_order === choice.value ? (
                              <span className="meta theme-option__status">Current</span>
                            ) : null}
                          </span>
                        </span>
                        <span className="meta">{choice.description}</span>
                      </label>
                    );
                  })}
                </div>
              </section>

              <div className="account-settings-actions">
                <button type="submit" className="button" disabled={saveSettings.isPending || !hasDraft || isUnchanged}>
                  {saveSettings.isPending ? "Saving..." : "Save account settings"}
                </button>
                {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
                {saveError ? <p className="status status-error">{saveError}</p> : null}
              </div>
            </form>
          </article>

          <aside className="card account-sidebar">
            <h2>Account</h2>
            <p>
              <strong>{user?.display_name}</strong>
            </p>
            <p className="meta">{user?.email}</p>
            {user?.is_admin ? <p className="meta-badge">App admin</p> : null}
            <p className="meta">
              Theme and live-session chat preferences are stored in the auth database and applied on every signed-in request.
            </p>
            <a className="ghost-button" href="/campaigns">
              Back to campaigns
            </a>
          </aside>
        </section>
      ) : null}
    </>
  );
}

function buildControlVisibilityDraft(rows: CampaignControlVisibilityRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((accumulator, row) => {
    accumulator[row.scope] = row.selected_visibility;
    return accumulator;
  }, {});
}

function isControlDraftUnchanged(rows: CampaignControlVisibilityRow[], draft: Record<string, string>): boolean {
  if (!rows.length) {
    return true;
  }
  return rows.every((row) => (draft[row.scope] || "") === row.selected_visibility);
}

function CampaignControlPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/control",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftVisibility, setDraftVisibility] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState("");

  const controlQuery = useQuery({
    queryKey: ["campaign-control", resolvedCampaignSlug],
    queryFn: () => apiClient.getCampaignControl(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(controlQuery.error)) {
      setAuthRequired(true);
    }
  }, [controlQuery.error, setAuthRequired]);

  useEffect(() => {
    const rows = controlQuery.data?.visibility_rows;
    if (!rows) {
      return;
    }
    setDraftVisibility(buildControlVisibilityDraft(rows));
  }, [controlQuery.data?.visibility_rows]);

  const saveVisibility = useMutation({
    mutationFn: () => apiClient.patchCampaignControlVisibility(resolvedCampaignSlug, { visibility: draftVisibility }),
    onSuccess: (response) => {
      setStatusMessage(response.message);
      setDraftVisibility(buildControlVisibilityDraft(response.visibility_rows));
      void queryClient.invalidateQueries({ queryKey: ["campaign-control", resolvedCampaignSlug] });
      void queryClient.invalidateQueries({ queryKey: ["campaign", resolvedCampaignSlug] });
    },
    onError: (error) => {
      setStatusMessage("");
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const data: CampaignControlResponse | undefined = controlQuery.data;
  const error = getApiErrorMessage(controlQuery.error);
  const saveError = saveVisibility.error ? apiErrorMessage(saveVisibility.error) : null;
  const isUnchanged = data ? isControlDraftUnchanged(data.visibility_rows, draftVisibility) : true;

  const handleVisibilityChange = (scope: string, value: string) => {
    setDraftVisibility((previous) => ({
      ...previous,
      [scope]: value,
    }));
    setStatusMessage("");
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data) {
      return;
    }
    setStatusMessage("");
    saveVisibility.mutate();
  };

  return (
    <>
      <section className="hero compact campaign-control-hero">
        <p className="eyebrow">Control panel</p>
        <h1>Visibility</h1>
        <p className="lede">
          Control who can see the campaign, wiki, systems reference, session tools, combat tracker, DM content, and character section.
        </p>
      </section>

      <ApiErrorNotice isLoading={controlQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {data ? (
        <div className="page-layout campaign-control-layout">
          <article className="card campaign-control-panel">
            <div className="section-heading">
              <div>
                <h2>Visibility settings</h2>
                <p className="meta">
                  The campaign setting acts as the floor; each section can only become as open as that floor allows.
                </p>
              </div>
            </div>
            <form className="stack-form campaign-control-form" onSubmit={handleSubmit}>
              <div className="campaign-control-grid">
                {data.visibility_rows.map((row) => {
                  const fieldId = `campaign-control-${row.scope}`;
                  return (
                    <article className="campaign-control-row" key={row.scope}>
                      <div className="campaign-control-row__header">
                        <label className="campaign-control-row__label" htmlFor={fieldId}>
                          {row.label}
                        </label>
                        <select
                          id={fieldId}
                          value={draftVisibility[row.scope] || row.selected_visibility}
                          onChange={(event: ChangeEvent<HTMLSelectElement>) => handleVisibilityChange(row.scope, event.currentTarget.value)}
                        >
                          {row.choices.map((choice) => (
                            <option value={choice.value} key={`${row.scope}-${choice.value}`}>
                              {choice.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="campaign-control-row__meta">
                        <p className="meta">Effective visibility: {row.effective_visibility_label}</p>
                        <p className="meta">
                          Configured visibility:{" "}
                          {row.configured_visibility_label ? row.configured_visibility_label : "Not configured"}
                        </p>
                        <p className="meta">Default visibility: {row.default_visibility_label}</p>
                      </div>
                      {row.is_overridden_by_campaign ? (
                        <p className="meta">The campaign-level visibility is currently more private than this section setting.</p>
                      ) : null}
                    </article>
                  );
                })}
              </div>

              <div className="hero-actions">
                <button type="submit" className="button-link" disabled={saveVisibility.isPending || isUnchanged}>
                  {saveVisibility.isPending ? "Saving..." : "Save visibility"}
                </button>
              </div>
              {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
              {saveError ? <p className="status status-error">{saveError}</p> : null}
            </form>
          </article>

          <aside className="sidebar campaign-control-sidebar">
            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Visibility rules</h2>
                  <p className="meta">These labels match the Campaign Control panel and campaign access checks.</p>
                </div>
              </div>
              <div className="reference-stack">
                {data.rules.map((rule) => (
                  <article className="detail-card help-detail-card" key={rule.label}>
                    <h3>{rule.label}</h3>
                    <p className="meta">{rule.description}</p>
                  </article>
                ))}
              </div>
            </article>

            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Notes</h2>
                  <p className="meta">Changing visibility does not rewrite content; it only changes who can see routes.</p>
                </div>
              </div>
              <HelpList items={data.notes} emptyText="No additional visibility notes are available." />
            </article>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function HelpList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (!items.length) {
    if (!emptyText) {
      return null;
    }
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list help-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function CampaignHelpPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/help",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();

  const helpQuery = useQuery({
    queryKey: ["campaign-help", resolvedCampaignSlug],
    queryFn: () => apiClient.getCampaignHelp(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(helpQuery.error)) {
      setAuthRequired(true);
    }
  }, [helpQuery.error, setAuthRequired]);

  const data: CampaignHelpResponse | undefined = helpQuery.data;
  const error = getApiErrorMessage(helpQuery.error);

  return (
    <>
      <section className="hero compact campaign-help-hero">
        <p className="eyebrow">Help</p>
        <h1>Help</h1>
        <p className="lede">
          Use this page for what each app surface is for, what the current access rules allow,
          and which first-pass limits still shape the workflow.
        </p>
        {data?.surfaces.length ? (
          <div className="hero-actions help-anchor-row" aria-label="Help sections">
            {data.surfaces.map((surface, index) => (
              <a className={index === 0 ? "button-link" : "ghost-button"} href={`#${surface.anchor}`} key={surface.anchor}>
                {surface.label}
              </a>
            ))}
          </div>
        ) : null}
      </section>

      <ApiErrorNotice isLoading={helpQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {data ? (
        <div className="page-layout campaign-help-layout">
          <section className="session-column campaign-help-main">
            <article className="card campaign-help-current">
              <div className="section-heading">
                <div>
                  <h2>Current access</h2>
                  <p className="meta">This page holds the broader workflow notes so the main UI can stay focused on actions.</p>
                </div>
              </div>
              <div className="detail-grid help-detail-grid">
                <article className="detail-card help-detail-card">
                  <h3>Viewer role</h3>
                  <p><strong>{data.viewer_role_label}</strong></p>
                  <p className="meta">{data.viewer_role_summary}</p>
                </article>
                <article className="detail-card help-detail-card">
                  <h3>Campaign system</h3>
                  <p><strong>{data.campaign_system_label}</strong></p>
                  <p className="meta">Some workflows below stay narrower when the campaign is not using DND-5E.</p>
                </article>
                <article className="detail-card help-detail-card">
                  <h3>Open now</h3>
                  {data.available_surface_labels.length ? (
                    <p>{data.available_surface_labels.join(", ")}</p>
                  ) : (
                    <p className="meta">No additional campaign surfaces are open to this viewer right now.</p>
                  )}
                </article>
              </div>
            </article>

            {data.surfaces.map((surface) => (
              <article className="card campaign-help-surface" id={surface.anchor} key={surface.anchor}>
                <div className="section-heading">
                  <div>
                    <h2>{surface.label}</h2>
                    <p className="meta">{surface.summary}</p>
                  </div>
                  <span className="meta-badge">{surface.status_label}</span>
                </div>

                {surface.links.length ? (
                  <div className="hero-actions campaign-help-surface-actions">
                    {surface.links.map((link, index) => (
                      <a
                        className={index === 0 ? "button-link" : "ghost-button"}
                        href={link.href}
                        key={`${surface.anchor}-${link.href}`}
                      >
                        {link.label}
                      </a>
                    ))}
                  </div>
                ) : null}

                <div className="detail-grid help-detail-grid">
                  <article className="detail-card help-detail-card">
                    <h3>Use it for</h3>
                    <HelpList items={surface.capabilities} emptyText="No capabilities are listed for this surface." />
                  </article>
                  <article className="detail-card help-detail-card">
                    <h3>Current limits</h3>
                    <HelpList items={surface.limits} emptyText="No limits are listed for this surface." />
                  </article>
                  <article className="detail-card help-detail-card">
                    <h3>Access</h3>
                    <p><strong>{surface.status_label}</strong></p>
                    <p className="meta">{surface.access_note}</p>
                  </article>
                </div>

                {surface.guidance_cards.length ? (
                  <div className="detail-grid help-detail-grid">
                    {surface.guidance_cards.map((card) => (
                      <article className="detail-card help-detail-card" key={`${surface.anchor}-${card.title}`}>
                        <h3>{card.title}</h3>
                        {card.body ? <p>{card.body}</p> : null}
                        <HelpList items={card.items} emptyText="" />
                        {card.meta ? <p className="meta">{card.meta}</p> : null}
                      </article>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </section>

          <aside className="session-sidebar campaign-help-sidebar">
            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Visibility by scope</h2>
                  <p className="meta">The effective visibility here is the current floor after campaign-level and scope-level rules combine.</p>
                </div>
              </div>
              <div className="reference-stack">
                {data.visibility_rows.map((row) => (
                  <article className="detail-card help-detail-card" key={row.label}>
                    <div className="section-heading">
                      <h3>{row.label}</h3>
                      <span className="meta-badge">{row.visibility_label}</span>
                    </div>
                    <p className="meta">
                      {row.viewer_can_open
                        ? "This viewer can currently open this scope."
                        : "This viewer cannot currently open this scope."}
                    </p>
                  </article>
                ))}
              </div>
            </article>

            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Cross-cutting limits</h2>
                  <p className="meta">These are the app-level constraints most likely to affect multiple surfaces.</p>
                </div>
              </div>
              <HelpList items={data.cross_cutting_limits} emptyText="No cross-cutting limits are visible for this viewer." />
            </article>

            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Account settings</h2>
                  <p className="meta">{data.account_note}</p>
                </div>
              </div>
              <div className="hero-actions campaign-help-account-actions">
                {data.is_authenticated ? (
                  <a className="button-link" href={data.links.account_url}>Open Account</a>
                ) : (
                  <a className="button-link" href={data.links.sign_in_url}>Sign in</a>
                )}
              </div>
            </article>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function splitPinnedPages(pages: WikiPageSummary[]): { pinned: WikiPageSummary[]; regular: WikiPageSummary[] } {
  return {
    pinned: pages.filter((page) => page.is_pinned),
    regular: pages.filter((page) => !page.is_pinned),
  };
}

function WikiPageCard({
  page,
  featured = false,
  campaignSlug,
  frontendMode,
  headingLevel = "h3",
  kickerMode = "displayType",
}: {
  page: WikiPageSummary;
  featured?: boolean;
  campaignSlug: string;
  frontendMode: FrontendMode;
  headingLevel?: "h2" | "h3";
  kickerMode?: "displayType" | "sectionAndDisplayType";
}) {
  const cardKicker =
    kickerMode === "sectionAndDisplayType"
      ? `${page.section} \u00b7 ${page.display_type}`
      : page.display_type;
  const TitleElement = headingLevel;

  return (
    <article className={featured ? "card page-card page-card--featured" : "card page-card"}>
      <p className="card-kicker">{cardKicker}</p>
      <TitleElement>
        <a href={preferredCampaignLink(page.href, campaignSlug, frontendMode)}>{page.title}</a>
      </TitleElement>
      {page.summary ? <p className={featured ? "page-card__summary" : ""}>{page.summary}</p> : null}
    </article>
  );
}

function WikiPageGrid({
  pages,
  featured = false,
  campaignSlug,
  frontendMode,
  headingLevel,
  kickerMode,
}: {
  pages: WikiPageSummary[];
  featured?: boolean;
  campaignSlug: string;
  frontendMode: FrontendMode;
  headingLevel?: "h2" | "h3";
  kickerMode?: "displayType" | "sectionAndDisplayType";
}) {
  if (!pages.length) {
    return null;
  }
  return (
    <div className={featured ? "page-stack page-stack--featured" : "grid"}>
      {pages.map((page) => (
        <WikiPageCard
          key={page.page_ref}
          page={page}
          featured={featured}
          campaignSlug={campaignSlug}
          frontendMode={frontendMode}
          headingLevel={headingLevel}
          kickerMode={kickerMode}
        />
      ))}
    </div>
  );
}

function WikiSectionBrowse({
  data,
  campaignSlug,
  frontendMode,
}: {
  data: WikiHomeResponse;
  campaignSlug: string;
  frontendMode: FrontendMode;
}) {
  if (!data.grouped_sections.length) {
    return null;
  }
  return (
    <section className="section-list wiki-section-browse">
      <div className="section-block">
        <div className="section-heading">
          <h2>{data.query ? "Search Results" : "Browse By Section"}</h2>
          <p className="meta">
            {data.query
              ? `${data.result_count} match${data.result_count === 1 ? "" : "es"}`
              : `${data.grouped_sections.length} section${data.grouped_sections.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <div className="grid">
          {data.grouped_sections.map((section) =>
            data.query ? (
              section.pages.map((page) => (
                <WikiPageCard
                  key={page.page_ref}
                  page={page}
                  campaignSlug={campaignSlug}
                  frontendMode={frontendMode}
                  headingLevel="h3"
                  kickerMode="sectionAndDisplayType"
                />
              ))
            ) : (
              <article className="card page-card section-card" key={section.section_slug}>
                <p className="card-kicker">Section</p>
                <h3>
                  <a href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}>{section.section_name}</a>
                </h3>
                <p>
                  {section.page_count} page{section.page_count === 1 ? "" : "s"} available in this section.
                </p>
                <p>
                  <a href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}>Open {section.section_name}</a>
                </p>
              </article>
            ),
          )}
        </div>
      </div>
    </section>
  );
}

function WikiHomePage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired, preferredFrontendMode } = useApiClient();
  const query = new URLSearchParams(window.location.search).get("q") || "";

  const wikiQuery = useQuery({
    queryKey: ["wiki-home", resolvedCampaignSlug, query],
    queryFn: () => apiClient.getWikiHome(resolvedCampaignSlug, query),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(wikiQuery.error)) {
      setAuthRequired(true);
    }
  }, [wikiQuery.error, setAuthRequired]);

  const error = getApiErrorMessage(wikiQuery.error);
  const data = wikiQuery.data;
  const wikiFrontendMode = normalizeFrontendMode(data?.frontend_mode ?? preferredFrontendMode);

  return (
    <>
      <section className="hero compact wiki-home">
        <p className="meta">Campaign</p>
        <h1>Campaign Home</h1>
        <p className="lede">{data?.campaign.summary}</p>
      </section>
      <ApiErrorNotice isLoading={wikiQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <>
          {!data.can_view_wiki ? (
            <section className="card">
              <h2>Wiki visibility restricted</h2>
              <p>{data.message}</p>
            </section>
          ) : data.query ? (
            data.grouped_sections.length ? (
              <WikiSectionBrowse data={data} campaignSlug={resolvedCampaignSlug} frontendMode={wikiFrontendMode} />
            ) : (
              <section className="card">
                <h2>No matching pages</h2>
                <p>Try a broader search term or remove the query.</p>
              </section>
            )
          ) : data.overview_page ? (
            <section className="section-list">
              <div className="section-block">
                <article className="article card wiki-overview-card">
                  <p className="eyebrow">
                    {data.overview_page.display_type} in {data.overview_page.section}
                  </p>
                  <h2>
                    <a
                      href={preferredCampaignLink(data.overview_page.href, resolvedCampaignSlug, wikiFrontendMode)}
                    >
                      {data.overview_page.title}
                    </a>
                  </h2>
                  {data.overview_page.summary ? <p className="lede">{data.overview_page.summary}</p> : null}
                  <div
                    className="article-body html-body"
                    dangerouslySetInnerHTML={{ __html: data.overview_page.body_html }}
                  />
                </article>
              </div>
            </section>
          ) : data.grouped_sections.length ? (
            <WikiSectionBrowse data={data} campaignSlug={resolvedCampaignSlug} frontendMode={wikiFrontendMode} />
          ) : (
            <section className="card">
              <h2>No visible pages yet</h2>
              <p>This campaign does not currently have any published pages available to players.</p>
            </section>
          )}
        </>
      ) : null}
    </>
  );
}

function WikiSectionPage() {
  const { campaignSlug, sectionSlug } = useParams({
    from: "/campaigns/$campaignSlug/sections/$sectionSlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSectionSlug = sectionSlug ?? "";
  const { apiClient, setAuthRequired, preferredFrontendMode } = useApiClient();
  const [collapsedSubsections, setCollapsedSubsections] = useState<Set<string>>(() => new Set());

  const sectionQuery = useQuery({
    queryKey: ["wiki-section", resolvedCampaignSlug, resolvedSectionSlug],
    queryFn: () => apiClient.getWikiSection(resolvedCampaignSlug, resolvedSectionSlug),
    enabled: Boolean(resolvedCampaignSlug && resolvedSectionSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sectionQuery.error)) {
      setAuthRequired(true);
    }
  }, [sectionQuery.error, setAuthRequired]);

  useEffect(() => {
    setCollapsedSubsections(new Set());
  }, [resolvedCampaignSlug, resolvedSectionSlug]);

  const data = sectionQuery.data;
  const error = getApiErrorMessage(sectionQuery.error);
  const wikiFrontendMode = normalizeFrontendMode(data?.frontend_mode ?? preferredFrontendMode);
  const topLevel = splitPinnedPages(data?.top_level_pages ?? []);
  const allPages = splitPinnedPages(data?.pages ?? []);

  const setAllSubsectionsOpen = (open: boolean) => {
    if (!data) {
      return;
    }
    setCollapsedSubsections(open ? new Set() : new Set(data.subsection_groups.map((group) => group.subsection_name)));
  };

  const setSubsectionOpen = (group: WikiSubsectionGroup, open: boolean) => {
    const next = new Set(collapsedSubsections);
    if (open) {
      next.delete(group.subsection_name);
    } else {
      next.add(group.subsection_name);
    }
    setCollapsedSubsections(next);
  };

  return (
    <>
      <section className="hero compact wiki-section-page">
        <p className="meta">Section</p>
        <h1>{data?.section_name ?? resolvedSectionSlug}</h1>
        <p className="lede">Published player-facing pages in this section.</p>
      </section>
      <ApiErrorNotice isLoading={sectionQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        data.show_subsections ? (
          <>
            <div className="section-list__controls">
              <button className="ghost-button section-list__control" type="button" onClick={() => setAllSubsectionsOpen(false)}>
                Collapse all
              </button>
              <button className="ghost-button section-list__control" type="button" onClick={() => setAllSubsectionsOpen(true)}>
                Expand all
              </button>
            </div>
            <WikiPageGrid
              pages={topLevel.pinned}
              featured
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
              headingLevel="h2"
              kickerMode="displayType"
            />
            <WikiPageGrid
              pages={topLevel.regular}
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
              headingLevel="h2"
              kickerMode="displayType"
            />
            <section className="section-list">
              {data.subsection_groups.map((group) => {
                const split = splitPinnedPages(group.pages);
                const isOpen = !collapsedSubsections.has(group.subsection_name);
                return (
                  <details
                    className="section-block section-block--collapsible"
                    key={group.subsection_name}
                    open={isOpen}
                    onToggle={(event) => setSubsectionOpen(group, event.currentTarget.open)}
                  >
                    <summary className="section-toggle-summary">
                      <span className="section-toggle-summary__content">
                        <span className="section-title">{group.subsection_name}</span>
                        <span className="meta">
                          {group.page_count} page{group.page_count === 1 ? "" : "s"}
                        </span>
                      </span>
                      <span className="section-toggle-chevron" aria-hidden="true"></span>
                    </summary>
                    <div className="section-block__body">
                      <WikiPageGrid
                        pages={split.pinned}
                        featured
                        campaignSlug={resolvedCampaignSlug}
                        frontendMode={wikiFrontendMode}
                        headingLevel="h3"
                        kickerMode="displayType"
                      />
                      <WikiPageGrid
                        pages={split.regular}
                        campaignSlug={resolvedCampaignSlug}
                        frontendMode={wikiFrontendMode}
                        headingLevel="h3"
                        kickerMode="displayType"
                      />
                    </div>
                  </details>
                );
              })}
            </section>
          </>
        ) : (
          <>
            <WikiPageGrid
              pages={allPages.pinned}
              featured
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
              headingLevel="h2"
              kickerMode="displayType"
            />
            <WikiPageGrid
              pages={allPages.regular}
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
              headingLevel="h2"
              kickerMode="displayType"
            />
          </>
        )
      ) : null}
    </>
  );
}

function WikiArticlePage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/pages/$",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const pageSlug = params._splat ?? "";
  const { apiClient, setAuthRequired, preferredFrontendMode } = useApiClient();

  const pageQuery = useQuery({
    queryKey: ["wiki-page", campaignSlug, pageSlug],
    queryFn: () => apiClient.getWikiPage(campaignSlug, pageSlug),
    enabled: Boolean(campaignSlug && pageSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(pageQuery.error)) {
      setAuthRequired(true);
    }
  }, [pageQuery.error, setAuthRequired]);

  const data: WikiPageResponse | undefined = pageQuery.data;
  const page: WikiPageDetail | undefined = data?.page;
  const error = getApiErrorMessage(pageQuery.error);
  const wikiFrontendMode = normalizeFrontendMode(data?.frontend_mode ?? preferredFrontendMode);
  const showSummary = page?.summary && !["item", "spell", "mechanic"].includes(page.page_type);

  return (
    <>
      <ApiErrorNotice isLoading={pageQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {page ? (
        <section className="page-layout wiki-article-page">
          <article className="article card">
            <h1>{page.title}</h1>
            {showSummary ? <p className="lede">{page.summary}</p> : null}
            {page.image ? (
              <figure className="article-figure">
                <img className="article-image" src={page.image.url} alt={page.image.alt_text || page.title} />
                {page.image.caption ? <figcaption className="meta article-image__caption">{page.image.caption}</figcaption> : null}
              </figure>
            ) : null}
            <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: page.body_html }} />
          </article>
          <aside className="sidebar">
            <section className="card sidebar-card">
              <h2>Context</h2>
              <p className="meta">
                Campaign: <a href={data?.links.campaign_url ?? data?.links.gen2_campaign_url}>{data?.campaign.title}</a>
              </p>
              <p className="meta">
                Section: <a href={data?.links.section_url ?? data?.links.gen2_section_url}>{page.section}</a>
              </p>
            </section>
            {data?.backlinks.length ? (
              <section className="card sidebar-card">
                <h2>Linked From</h2>
                <ul className="plain-list">
                  {data.backlinks.map((backlink) => (
                    <li key={backlink.page_ref}>
                      <a href={preferredCampaignLink(backlink.href, campaignSlug, wikiFrontendMode)}>{backlink.title}</a>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </aside>
        </section>
      ) : null}
    </>
  );
}

function systemsIndexHref(campaignSlug: string): string {
  return `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/systems`;
}

function systemsSourceHref(campaignSlug: string, sourceId: string): string {
  return `${systemsIndexHref(campaignSlug)}/sources/${encodeURIComponent(sourceId)}`;
}

function systemsSourceCategoryHref(campaignSlug: string, sourceId: string, entryType: string): string {
  return `${systemsSourceHref(campaignSlug, sourceId)}/types/${encodeURIComponent(entryType)}`;
}

function systemsEntryHref(campaignSlug: string, entrySlug: string): string {
  return `${systemsIndexHref(campaignSlug)}/entries/${encodeURIComponent(entrySlug)}`;
}

function SystemsManageLink({ campaignSlug, canManage }: { campaignSlug: string; canManage: boolean }) {
  return canManage ? (
    <a
      className="ghost-button"
      href={`/app-next/campaigns/${encodeURIComponent(campaignSlug)}/dm-content?lane=systems`}
    >
      Systems settings
    </a>
  ) : null;
}

function SystemsEntryList({
  campaignSlug,
  entries,
  emptyText,
  showMeta = true,
}: {
  campaignSlug: string;
  entries: SystemsEntrySummary[];
  emptyText: string;
  showMeta?: boolean;
}) {
  if (!entries.length) {
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list systems-entry-list">
      {entries.map((entry) => (
        <li className="systems-list-row" key={entry.entry_key}>
          <a href={systemsEntryHref(campaignSlug, entry.slug)}>{entry.title}</a>
          {showMeta ? (
            <span className="meta systems-list-row__meta">
              {entry.source_id} | {entry.entry_type_label}
              {entry.source_page ? ` | p. ${entry.source_page}` : ""}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function SystemsRulesReferenceList({
  campaignSlug,
  results,
  emptyText,
}: {
  campaignSlug: string;
  results: SystemsRulesReferenceResult[];
  emptyText: string;
}) {
  if (!results.length) {
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list systems-entry-list">
      {results.map((entry) => (
        <li className="systems-list-row" key={`${entry.source_id}-${entry.slug}`}>
          <a href={systemsEntryHref(campaignSlug, entry.slug)}>{entry.title}</a>
          <span className="meta systems-list-row__meta">
            {entry.source_id} | {entry.entry_type_label}
            {entry.reference_scope ? ` | ${entry.reference_scope}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function SystemsCategoryList({
  campaignSlug,
  sourceId,
  groups,
  emptyText,
}: {
  campaignSlug: string;
  sourceId: string;
  groups: SystemsSourceBrowseGroup[];
  emptyText: string;
}) {
  if (!groups.length) {
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list systems-entry-list">
      {groups.map((group) => (
        <li className="systems-list-row" key={group.entry_type}>
          <a href={systemsSourceCategoryHref(campaignSlug, sourceId, group.entry_type)}>
            {group.entry_type_label}
          </a>
          <span className="meta systems-list-row__meta">
            {group.count} entr{group.count === 1 ? "y" : "ies"}
          </span>
        </li>
      ))}
    </ul>
  );
}

function SystemsIndexPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/systems",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q") || "";
  const referenceQuery = params.get("reference_q") || "";

  const systemsQuery = useQuery({
    queryKey: ["systems-index", resolvedCampaignSlug, query, referenceQuery],
    queryFn: () => apiClient.getSystemsIndex(resolvedCampaignSlug, query, referenceQuery),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(systemsQuery.error)) {
      setAuthRequired(true);
    }
  }, [systemsQuery.error, setAuthRequired]);

  const data: SystemsIndexResponse | undefined = systemsQuery.data;
  const error = getApiErrorMessage(systemsQuery.error);
  const action = systemsIndexHref(resolvedCampaignSlug);

  return (
    <>
      <section className="hero compact systems-hero">
        <div>
          <p className="eyebrow">Systems wiki</p>
          <h1>Systems</h1>
          <p className="lede">Browse campaign-approved system sources and reference entries.</p>
        </div>
        {data ? (
          data.permissions.can_manage_systems ? (
            <div className="hero-actions systems-hero-actions">
              <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
            </div>
          ) : null
        ) : null}
      </section>
      <ApiErrorNotice isLoading={systemsQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="systems-browse-grid page-layout">
          <section className="systems-search-band article card">
            <h2>Systems Search</h2>
            <form method="get" action={action} className="stack-form">
              {referenceQuery ? <input type="hidden" name="reference_q" value={referenceQuery} /> : null}
              <label className="field" htmlFor="systems-entry-search">
                <span>Search systems entries</span>
                <input id="systems-entry-search" type="search" name="q" defaultValue={data.query} placeholder="title, type, or source" />
              </label>
              <button type="submit">Search</button>
            </form>
            <p className="meta">Search matches titles, entry types, and source IDs only.</p>
            {data.query ? (
              <>
                <h3>Search Results</h3>
                <SystemsEntryList
                  campaignSlug={resolvedCampaignSlug}
                  entries={data.search_results}
                  emptyText="No imported systems entries matched that search yet."
                />
              </>
            ) : null}

            <section>
              <h2>Rules Reference Search</h2>
              {data.has_rules_reference_search ? (
                <>
                  <form method="get" action={action} className="stack-form">
                    {query ? <input type="hidden" name="q" value={query} /> : null}
                    <label className="field" htmlFor="systems-rules-search">
                      <span>Search rules references</span>
                      <input
                        id="systems-rules-search"
                        type="search"
                        name="reference_q"
                        defaultValue={data.reference_query}
                        placeholder="chapter heading, rule alias, or facet"
                      />
                    </label>
                    <button type="submit">Search</button>
                  </form>
                  <p className="meta">
                    Searches landing-page book-backed chapter pages and RULES entries by curated metadata, not full body text.
                  </p>
                </>
              ) : (
                <p className="meta">No landing-page rules-reference sources are currently available to this viewer.</p>
              )}
              {data.source_scoped_rules_reference_sources.length ? (
                <p className="meta">
                  Source-scoped rules searches stay on their source pages:{" "}
                  {data.source_scoped_rules_reference_sources.map((source, index) => (
                    <React.Fragment key={source.source_id}>
                      {index > 0 ? ", " : ""}
                      <a href={systemsSourceHref(resolvedCampaignSlug, source.source_id)}>{source.title}</a>
                    </React.Fragment>
                  ))}
                  .
                </p>
              ) : null}
              {data.reference_query ? (
                <>
                  <h3>Rules Reference Results</h3>
                  <SystemsRulesReferenceList
                    campaignSlug={resolvedCampaignSlug}
                    results={data.rules_reference_results}
                    emptyText="No rules references matched that metadata search yet."
                  />
                </>
              ) : null}
            </section>
          </section>
          <aside className="sidebar systems-browse-sidebar">
            <section className="card sidebar-card systems-source-card">
              <h2>Available Sources</h2>
              {data.sources.length ? (
                <ul className="plain-list systems-entry-list">
                  {data.sources.map((source) => (
                    <li className="systems-list-row" key={source.source_id}>
                      <a href={systemsSourceHref(resolvedCampaignSlug, source.source_id)}>{source.title}</a>
                      <p className="meta">{source.source_id} | {source.license_class_label}</p>
                      <p className="meta">{source.default_visibility} visibility | {source.entry_count} available entries</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No systems sources are currently available to this viewer.</p>
              )}
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function SystemsSourcePage() {
  const { campaignSlug, sourceId } = useParams({
    from: "/campaigns/$campaignSlug/systems/sources/$sourceId",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSourceId = sourceId ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const referenceQuery = new URLSearchParams(window.location.search).get("reference_q") || "";

  const sourceQuery = useQuery({
    queryKey: ["systems-source", resolvedCampaignSlug, resolvedSourceId, referenceQuery],
    queryFn: () => apiClient.getSystemsSource(resolvedCampaignSlug, resolvedSourceId, referenceQuery),
    enabled: Boolean(resolvedCampaignSlug && resolvedSourceId),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sourceQuery.error)) {
      setAuthRequired(true);
    }
  }, [sourceQuery.error, setAuthRequired]);

  const data: SystemsSourceResponse | undefined = sourceQuery.data;
  const error = getApiErrorMessage(sourceQuery.error);
  const action = systemsSourceHref(resolvedCampaignSlug, resolvedSourceId);

  return (
    <>
      <section className="hero compact systems-hero">
        <div>
          <p className="eyebrow">Systems source</p>
          <h1>{data?.source.title ?? resolvedSourceId}</h1>
          {data ? <p className="lede">{data.source.source_id} | {data.source.license_class_label} | {data.source.default_visibility} visibility</p> : null}
        </div>
        {data ? (
          data.permissions.can_manage_systems ? (
            <div className="hero-actions systems-hero-actions">
              <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
            </div>
          ) : null
        ) : null}
      </section>
      <ApiErrorNotice isLoading={sourceQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="systems-browse-grid page-layout">
          <section className="systems-source-band article card">
            <h2>Browse This Source</h2>
            {data.rules_reference_scope_note ? <p className="meta">{data.rules_reference_scope_note}</p> : null}
            {data.book_visibility_policy_note ? <p className="meta">{data.book_visibility_policy_note}</p> : null}
            {data.book_entries.length ? (
              <section>
                <h3>Book Chapters</h3>
                <SystemsEntryList
                  campaignSlug={resolvedCampaignSlug}
                  entries={data.book_entries}
                  emptyText="No book chapters are visible in this source."
                />
              </section>
            ) : null}
            {data.has_rules_reference_search ? (
              <section>
                <h3>Rules Reference Search</h3>
                <form method="get" action={action} className="stack-form">
                  <label className="field" htmlFor="systems-source-rules-search">
                    <span>Search this source's rules references</span>
                    <input
                      id="systems-source-rules-search"
                      type="search"
                      name="reference_q"
                      defaultValue={data.reference_query}
                      placeholder="chapter heading, rule alias, or facet"
                    />
                  </label>
                  <button type="submit">Search</button>
                </form>
                {data.rules_reference_search_meta ? <p className="meta">{data.rules_reference_search_meta}</p> : null}
                {data.reference_query ? (
                  <SystemsRulesReferenceList
                    campaignSlug={resolvedCampaignSlug}
                    results={data.rules_reference_results}
                    emptyText="No rules references matched that metadata search in this source."
                  />
                ) : null}
              </section>
            ) : null}
            {data.hidden_entry_types.length ? (
              <p className="meta">
                Some entry types are folded into their parent pages and remain searchable without appearing as separate source categories.
              </p>
            ) : null}
            <p className="meta">
              This source currently has {data.browsable_entry_count} browsable entr{data.browsable_entry_count === 1 ? "y" : "ies"} across {data.entry_groups.length} categor{data.entry_groups.length === 1 ? "y" : "ies"}.
            </p>
            <SystemsCategoryList
              campaignSlug={resolvedCampaignSlug}
              sourceId={data.source.source_id}
              groups={data.entry_groups}
              emptyText="No systems entries are currently available in this source for your access level."
            />
          </section>
          <aside className="sidebar systems-browse-sidebar">
            <section className="card sidebar-card">
              <h2>Source Details</h2>
              <p className="meta">Source ID: {data.source.source_id}</p>
              <p className="meta">Default visibility: {data.source.default_visibility}</p>
              <p className="meta">Available entries: {data.entry_count}</p>
            </section>
            {data.entry_groups.length ? (
              <section className="card sidebar-card">
                <h2>Content Categories</h2>
                <SystemsCategoryList
                  campaignSlug={resolvedCampaignSlug}
                  sourceId={data.source.source_id}
                  groups={data.entry_groups}
                  emptyText="No categories are visible."
                />
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}
    </>
  );
}

function SystemsSourceCategoryPage() {
  const { campaignSlug, sourceId, entryType } = useParams({
    from: "/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSourceId = sourceId ?? "";
  const resolvedEntryType = entryType ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const query = new URLSearchParams(window.location.search).get("q") || "";

  const categoryQuery = useQuery({
    queryKey: ["systems-source-category", resolvedCampaignSlug, resolvedSourceId, resolvedEntryType, query],
    queryFn: () => apiClient.getSystemsSourceCategory(resolvedCampaignSlug, resolvedSourceId, resolvedEntryType, query),
    enabled: Boolean(resolvedCampaignSlug && resolvedSourceId && resolvedEntryType),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(categoryQuery.error)) {
      setAuthRequired(true);
    }
  }, [categoryQuery.error, setAuthRequired]);

  const data: SystemsSourceCategoryResponse | undefined = categoryQuery.data;
  const error = getApiErrorMessage(categoryQuery.error);
  const action = systemsSourceCategoryHref(resolvedCampaignSlug, resolvedSourceId, resolvedEntryType);

  return (
    <>
      <section className="hero compact systems-hero">
        <div>
          <p className="eyebrow">Systems source category</p>
          <h1>{data ? `${data.source.title}: ${data.entry_type_label}` : resolvedEntryType}</h1>
          {data ? <p className="lede">{data.source.source_id} | {data.source.license_class_label} | {data.source.default_visibility} visibility</p> : null}
        </div>
        {data ? (
          data.permissions.can_manage_systems ? (
            <div className="hero-actions systems-hero-actions">
              <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
            </div>
          ) : null
        ) : null}
      </section>
      <ApiErrorNotice isLoading={categoryQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="systems-browse-grid page-layout">
          <section className="systems-category-band article card">
            <h2>Browse {data.entry_type_label}</h2>
            <form method="get" action={action} className="stack-form">
              <label className="field" htmlFor="systems-category-search">
                <span>Search this category</span>
                <input id="systems-category-search" type="search" name="q" defaultValue={data.query} placeholder="Search by title" />
              </label>
              <button type="submit">Search</button>
            </form>
            <p className="meta">Search matches titles and entry types only.</p>
            <p className="meta">
              {data.query
                ? `Showing ${data.filtered_entry_count} matching entries out of ${data.entry_count}.`
                : `Showing all ${data.entry_count} ${data.entry_type_label.toLowerCase()}.`}
            </p>
            <SystemsEntryList
              campaignSlug={resolvedCampaignSlug}
              entries={data.entries}
              emptyText={`No ${data.entry_type_label.toLowerCase()} matched that title/type search.`}
              showMeta={false}
            />
          </section>
          <aside className="sidebar systems-browse-sidebar">
            <section className="card sidebar-card">
              <h2>Category Details</h2>
              <p className="meta">Source ID: {data.source.source_id}</p>
              <p className="meta">Category: {data.entry_type_label}</p>
              <p className="meta">Available entries: {data.entry_count}</p>
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function SystemsEntryPage() {
  const { campaignSlug, entrySlug } = useParams({
    from: "/campaigns/$campaignSlug/systems/entries/$entrySlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedEntrySlug = entrySlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();

  const entryQuery = useQuery({
    queryKey: ["systems-entry", resolvedCampaignSlug, resolvedEntrySlug],
    queryFn: () => apiClient.getSystemsEntry(resolvedCampaignSlug, resolvedEntrySlug),
    enabled: Boolean(resolvedCampaignSlug && resolvedEntrySlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(entryQuery.error)) {
      setAuthRequired(true);
    }
  }, [entryQuery.error, setAuthRequired]);

  const data: SystemsEntryResponse | undefined = entryQuery.data;
  const entry = data?.entry;
  const error = getApiErrorMessage(entryQuery.error);
  const sourceState = entry?.source_state;

  return (
    <>
      {entry ? (
        <section className="hero compact systems-hero">
          <p className="eyebrow">Systems entry</p>
          <h1>{entry.title}</h1>
          <p className="lede">
            {entry.entry_type_label} | {entry.source_id}
            {sourceState?.license_class_label ? ` | ${sourceState.license_class_label}` : ""}
          </p>
        </section>
      ) : null}
      <ApiErrorNotice isLoading={entryQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {entry ? (
        <div className="page-layout">
          <article className="article card systems-entry-band">
            {entry.rendered_html ? (
              <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: entry.rendered_html }} />
            ) : (
              <>
                <p className="meta">This entry has been imported into the systems library, but it does not have rendered content yet.</p>
                <p className="meta">Entry key: {entry.entry_key}</p>
              </>
            )}
          </article>
          <aside className="sidebar systems-entry-sidebar">
            <section className="card sidebar-card systems-sidebar-card">
              <h2>Entry Metadata</h2>
              <p className="meta">Type: {entry.entry_type_label}</p>
              <p className="meta">Source: {entry.source_id}</p>
              <p className="meta">Entry key: {entry.entry_key}</p>
              {entry.source_page ? <p className="meta">Source page: {entry.source_page}</p> : null}
            </section>
            <section className="card sidebar-card systems-sidebar-card">
              <h2>Navigation</h2>
              <ul className="plain-list systems-entry-navigation">
                <li><a href={systemsIndexHref(resolvedCampaignSlug)}>Systems landing</a></li>
                <li><a href={systemsSourceHref(resolvedCampaignSlug, entry.source_id)}>Source page</a></li>
                <li><a href={systemsSourceCategoryHref(resolvedCampaignSlug, entry.source_id, entry.entry_type)}>Source category</a></li>
              </ul>
            </section>
            {data?.permissions.can_manage_systems ? (
              <section className="card sidebar-card systems-sidebar-card" id="systems-entry-management">
                <h2>Entry Management</h2>
                <p className="meta">
                  Shared library entry. Campaign DMs normally use overrides; app admins can allow trusted campaign DMs to edit shared/core content directly.
                </p>
                <div className="badge-list">
                  {data.links.dm_content_systems_url ? (
                    <a className="ghost-button" href={data.links.dm_content_systems_url}>Manage campaign override</a>
                  ) : (
                    <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
                  )}
                </div>
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}
    </>
  );
}

function SessionArticlesPanel({
  campaignSlug,
  articles,
  title,
  emptyText,
  className = "card session-articles-card",
}: {
  campaignSlug: string;
  articles: SessionArticle[];
  title: string;
  emptyText: string;
  className?: string;
}) {
  const mergedClassName = Array.from(new Set(`card ${className ?? ""}`.split(/\s+/).filter(Boolean))).join(" ");

  return (
    <article className={mergedClassName}>
      <div className="section-heading">
        <h2>{title}</h2>
        <p className="meta">{articles.length}</p>
      </div>
      {articles.length ? (
        <div className="session-article-stack">
          {articles.map((article) => {
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
                      alt={article.image.alt_text || article.title || "Article image"}
                    />
                    {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                  </figure>
                ) : null}
                <SessionArticleSourceLine article={article} />
                {renderArticleBody(article, "article-body--compact")}
                <div className="session-article-detail__actions">
                  <SessionArticleReferenceActions article={article} includePromotionLinks={false} />
                </div>
              </details>
            );
          })}
        </div>
      ) : (
        <p className="status status-neutral">{emptyText}</p>
      )}
    </article>
  );
}

function SessionPaneChat({
  payload,
}: {
  payload: SessionPayload | undefined;
}) {
  const messages: SessionMessage[] = payload?.messages ?? [];

  return (
    <article className="card session-chat-card" id="session-chat" data-session-chat-card>
      <div className="section-heading">
        <h2>Chat window</h2>
        <p className="meta">{payload?.active_session ? "Live feed" : "Waiting room"}</p>
      </div>
      <div className="chat-list">
        {messages.length ? (
          messages.map((message) => (
            <article key={message.id} className="chat-item">
              <p className="chat-meta">
                {message.author_display_name} - {formatTimestamp(message.created_at)}
              </p>
              <p>{message.body_text}</p>
            </article>
          ))
        ) : (
          <p className="status status-neutral">No messages yet.</p>
        )}
      </div>
    </article>
  );
}

function SessionPaneMessageComposer({
  payload,
  messageDraft,
  setMessageDraft,
  recipientScope,
  setRecipientScope,
  recipientPlayerId,
  setRecipientPlayerId,
  recipientPlayerChoices,
  sendError,
  onSend,
  isSending,
}: {
  payload: SessionPayload | undefined;
  messageDraft: string;
  setMessageDraft: (value: string) => void;
  recipientScope: "global" | "dm_only" | "player";
  setRecipientScope: (value: "global" | "dm_only" | "player") => void;
  recipientPlayerId: string;
  setRecipientPlayerId: (value: string) => void;
  recipientPlayerChoices: SessionMessageRecipientPlayerChoice[];
  sendError: string | null;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  isSending: boolean;
}) {
  return (
    <article className="card session-composer-card" id="session-chat-compose">
      <h2>Send message</h2>
      {payload?.permissions.can_post_messages ? (
        <form onSubmit={onSend} className="stack-form session-message-form">
          <label className="field">
            <span>Audience</span>
            <select
              value={recipientScope}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                setRecipientScope(event.currentTarget.value as "global" | "dm_only" | "player");
              }}
            >
              <option value="global">Global</option>
              <option value="dm_only">DM only</option>
              <option value="player">Specific player</option>
            </select>
          </label>
          <label className="field">
            <span>Player</span>
            <select
              value={recipientPlayerId}
              disabled={recipientScope !== "player" || !recipientPlayerChoices.length}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                setRecipientPlayerId(event.currentTarget.value);
              }}
            >
              {recipientPlayerChoices.length ? (
                recipientPlayerChoices.map((choice) => (
                  <option key={choice.user_id} value={String(choice.user_id)}>
                    {choice.label}
                  </option>
                ))
              ) : (
                <option value="">No players available</option>
              )}
            </select>
          </label>
          <label className="field">
            <span>Message</span>
            <textarea
              rows={5}
              value={messageDraft}
              placeholder="Type chat text"
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                setMessageDraft(event.currentTarget.value);
              }}
            />
          </label>
          <button type="submit" className="session-message-form__submit" disabled={isSending || payload?.active_session === null}>
            {isSending ? "Posting..." : "Post to chat"}
          </button>
          {sendError ? <p className="status status-error">{sendError}</p> : null}
        </form>
      ) : (
        <p className="status status-neutral">You do not have permission to post messages.</p>
      )}
    </article>
  );
}

function readBinaryAsBase64(file: File, callback: (payload: EmbeddedImageInput | null) => void): void {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const data = reader.result;
    if (typeof data !== "string") {
      callback(null);
      return;
    }
    callback({
      filename: file.name,
      data_base64: data.split(",", 2)[1] || "",
      media_type: file.type || "application/octet-stream",
    });
  });
  reader.addEventListener("error", () => callback(null));
  reader.readAsDataURL(file);
}

function readTextFile(file: File, callback: (payload: { filename: string; text: string } | null) => void): void {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const data = reader.result;
    if (typeof data !== "string") {
      callback(null);
      return;
    }
    callback({ filename: file.name, text: data });
  });
  reader.addEventListener("error", () => callback(null));
  reader.readAsText(file);
}

function DmArticleCreator({
  mode,
  setMode,
  sourceQuery,
  setSourceQuery,
  sourceStatus,
  setSourceStatus,
  sourceResults,
  selectedSourceRef,
  setSelectedSourceRef,
  manualDraft,
  setManualDraft,
  uploadDraft,
  setUploadDraft,
  onSearchSources,
  onCreate,
  isCreating,
  className = "card",
  id,
}: {
  mode: ArticleMode;
  setMode: (mode: ArticleMode) => void;
  sourceQuery: string;
  setSourceQuery: (value: string) => void;
  sourceStatus: string | null;
  setSourceStatus: (value: string | null) => void;
  sourceResults: SessionArticleSourceResult[];
  selectedSourceRef: string;
  setSelectedSourceRef: (value: string) => void;
  manualDraft: ManualArticleDraftState;
  setManualDraft: (state: ManualArticleDraftState) => void;
  uploadDraft: { filename: string; markdown: string; image: EmbeddedImageInput | null };
  setUploadDraft: (state: { filename: string; markdown: string; image: EmbeddedImageInput | null }) => void;
  onSearchSources: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCreate: (payload: SessionArticleCreatePayload) => void;
  isCreating: boolean;
  className?: string;
  id?: string;
}) {
  const idSeed = id === "dm-content-staged-article-store" ? "dm-content" : "session";
  const manualModeRadioId = `${idSeed}-article-mode-manual`;
  const uploadModeRadioId = `${idSeed}-article-mode-upload`;
  const wikiModeRadioId = `${idSeed}-article-mode-wiki`;
  const manualModeLabel = `${idSeed}-manual`;
  const uploadModeLabel = `${idSeed}-upload`;
  const wikiModeLabel = `${idSeed}-wiki`;
  const manualImageInputId = `${idSeed}-manual-image-file`;
  const uploadReferencedImageInputId = `${idSeed}-upload-referenced-image-file`;
  const wikiSearchInputId = `${idSeed}-wiki-search`;

  const instructions =
    mode === "manual"
      ? "Use a title with markdown body or an image and create an unrevealed article."
      : mode === "upload"
        ? "Upload mode needs a filename and markdown body."
        : "Search and select a source, then pull into staged articles.";
  const mergedClassName = Array.from(new Set(`card ${className ?? ""}`.split(/\s+/).filter(Boolean))).join(" ");
  const wikiSearchStatusText = sourceStatus ?? "Type at least 2 letters to search published wiki pages and Systems entries.";

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "wiki") {
      await onSearchSources(event);
    }
  };

  return (
    <article className={mergedClassName} id={id}>
      <h2>Stage session articles</h2>
      <form className="stack-form" onSubmit={onSubmit}>
        <input
          className="session-form-mode-radio session-form-mode-radio--manual"
          type="radio"
          id={manualModeRadioId}
          name={`${idSeed}-article-mode`}
          value="manual"
          checked={mode === "manual"}
          onChange={() => setMode("manual")}
        />
        <input
          className="session-form-mode-radio session-form-mode-radio--upload"
          type="radio"
          id={uploadModeRadioId}
          name={`${idSeed}-article-mode`}
          value="upload"
          checked={mode === "upload"}
          onChange={() => setMode("upload")}
        />
        <input
          className="session-form-mode-radio session-form-mode-radio--wiki"
          type="radio"
          id={wikiModeRadioId}
          name={`${idSeed}-article-mode`}
          value="wiki"
          checked={mode === "wiki"}
          onChange={() => setMode("wiki")}
        />
        <div className="session-form-mode-toggle" role="radiogroup" aria-label={id === "dm-content-staged-article-store" ? "Staged article input mode" : "Session article input mode"}>
          <label className="ghost-button" htmlFor={manualModeRadioId}>
            Manual
          </label>
          <label className="ghost-button" htmlFor={uploadModeRadioId}>
            Upload
          </label>
          <label className="ghost-button" htmlFor={wikiModeRadioId}>
            Lookup
          </label>
        </div>
        <p className="status status-neutral">{instructions}</p>

        {mode === "manual" ? (
          <div className="session-article-mode-panel session-article-mode-panel--manual" data-session-article-mode-panel="manual">
            <label className="field" htmlFor={`${manualModeLabel}-title`}>
              <span>Title</span>
              <input
                id={`${manualModeLabel}-title`}
                value={manualDraft.title}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setManualDraft({ ...manualDraft, title: event.currentTarget.value });
                }}
              />
            </label>
            <label className="field" htmlFor={`${manualModeLabel}-body`}>
              <span>Body</span>
              <textarea
                id={`${manualModeLabel}-body`}
                rows={8}
                value={manualDraft.body}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                  setManualDraft({ ...manualDraft, body: event.currentTarget.value });
                }}
              />
            </label>
            <div className="field session-file-field">
              <span>Image</span>
              <input
                className="session-file-input"
                id={manualImageInputId}
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.gif"
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  const file = event.currentTarget.files?.item(0);
                  if (!file) {
                    setManualDraft({ ...manualDraft, image: null });
                    return;
                  }
                  readBinaryAsBase64(file, (payload) => {
                    setManualDraft({ ...manualDraft, image: payload });
                  });
                }}
              />
              <label className="session-file-dropzone" htmlFor={manualImageInputId} tabIndex={0}>
                <strong>Drag and drop a file here</strong>
                <span className="meta">or use Browse to choose one</span>
                <span className="session-file-dropzone__browse">Browse</span>
                <span className="meta session-file-dropzone__name">
                  {manualDraft.image ? manualDraft.image.filename : "No file selected."}
                </span>
              </label>
            </div>
            <label className="field" htmlFor={`${manualModeLabel}-image-alt`}>
              <span>Image alt text</span>
              <input
                id={`${manualModeLabel}-image-alt`}
                value={manualDraft.imageAltText}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setManualDraft({ ...manualDraft, imageAltText: event.currentTarget.value });
                }}
              />
            </label>
            <label className="field" htmlFor={`${manualModeLabel}-image-caption`}>
              <span>Image caption</span>
              <input
                id={`${manualModeLabel}-image-caption`}
                value={manualDraft.imageCaption}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setManualDraft({ ...manualDraft, imageCaption: event.currentTarget.value });
                }}
              />
            </label>
            <button
              type="button"
              className="button"
              disabled={
                isCreating
                || !manualDraft.title.trim()
                || (!manualDraft.body.trim() && !manualDraft.image)
              }
              onClick={() =>
                onCreate({
                  mode: "manual",
                  title: manualDraft.title.trim(),
                  body_markdown: manualDraft.body,
                  image: manualDraft.image
                    ? {
                        ...manualDraft.image,
                        alt_text: manualDraft.imageAltText.trim() || null,
                        caption: manualDraft.imageCaption.trim() || null,
                      }
                    : undefined,
                } satisfies SessionArticleCreatePayloadManual)
              }
            >
              {isCreating ? "Creating..." : "Create"}
            </button>
          </div>
        ) : null}

        {mode === "upload" ? (
          <div className="session-article-mode-panel session-article-mode-panel--upload" data-session-article-mode-panel="upload">
            <p className="meta">
              The article title comes from markdown frontmatter, then <code># Heading</code>, then the filename.
            </p>
            <label className="field" htmlFor={`${uploadModeLabel}-filename`}>
              <span>Source filename</span>
              <input
                id={`${uploadModeLabel}-filename`}
                value={uploadDraft.filename}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setUploadDraft({ ...uploadDraft, filename: event.currentTarget.value });
                }}
                placeholder="notes.md"
              />
            </label>
            <label className="field" htmlFor={`${uploadModeLabel}-markdown`}>
              <span>Markdown text</span>
              <textarea
                id={`${uploadModeLabel}-markdown`}
                rows={8}
                value={uploadDraft.markdown}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                  setUploadDraft({ ...uploadDraft, markdown: event.currentTarget.value });
                }}
              />
            </label>
            <div className="field session-file-field">
              <span>Referenced image</span>
              <input
                className="session-file-input"
                id={uploadReferencedImageInputId}
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.gif"
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  const file = event.currentTarget.files?.item(0);
                  if (!file) {
                    setUploadDraft({ ...uploadDraft, image: null });
                    return;
                  }
                  readBinaryAsBase64(file, (payload) => {
                    setUploadDraft({ ...uploadDraft, image: payload });
                  });
                }}
              />
              <label className="session-file-dropzone" htmlFor={uploadReferencedImageInputId} tabIndex={0}>
                <strong>Drag and drop a file here</strong>
                <span className="meta">or use Browse to choose one</span>
                <span className="session-file-dropzone__browse">Browse</span>
                <span className="meta session-file-dropzone__name">
                  {uploadDraft.image ? uploadDraft.image.filename : "No file selected."}
                </span>
              </label>
            </div>
            <p className="meta">
              If markdown references an image in frontmatter or an embedded image tag, upload that image here.
            </p>
            <button
              type="button"
              disabled={isCreating || !uploadDraft.filename.trim() || !uploadDraft.markdown.trim()}
              onClick={() =>
                onCreate({
                  mode: "upload",
                  filename: uploadDraft.filename.trim(),
                  markdown_text: uploadDraft.markdown,
                  referenced_image: uploadDraft.image ?? undefined,
                } satisfies SessionArticleCreatePayloadUpload)
              }
            >
              {isCreating ? "Creating..." : "Create"}
            </button>
          </div>
        ) : null}

        {mode === "wiki" ? (
          <div className="session-article-mode-panel session-article-mode-panel--wiki" data-session-article-mode-panel="wiki">
            <label className="field" htmlFor={wikiSearchInputId}>
              <span>Search</span>
              <input
                id={wikiSearchInputId}
                type="search"
                value={sourceQuery}
                autoComplete="off"
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setSourceQuery(event.currentTarget.value);
                  setSourceStatus(null);
                  setSelectedSourceRef("");
                }}
              />
            </label>
            <label className="field" htmlFor={`${wikiModeLabel}-source-results`}>
              <span>Matching articles</span>
              <select
                id={`${wikiModeLabel}-source-results`}
                value={selectedSourceRef}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                  setSelectedSourceRef(event.currentTarget.value);
                }}
                disabled={sourceResults.length === 0}
              >
                <option value="">Search to load matching articles</option>
                {sourceResults.map((result) => (
                  <option key={result.source_ref} value={result.source_ref}>
                    {result.title}
                  </option>
                ))}
              </select>
            </label>
            <p className="meta" data-session-article-source-status>
              {wikiSearchStatusText}
            </p>
            <div className="wiki-selection">
              <p className="status status-neutral">{selectedSourceRef ? `Source selected: ${selectedSourceRef}` : "No source selected"}</p>
              <button
                type="button"
                disabled={isCreating || !selectedSourceRef}
                onClick={() =>
                  onCreate({
                    mode: "wiki",
                    source_ref: selectedSourceRef,
                  } satisfies SessionArticleCreatePayloadWiki)
                }
              >
                {isCreating ? "Creating..." : "Pull source"}
              </button>
            </div>
            <button type="submit">Search</button>
          </div>
        ) : null}
      </form>
    </article>
  );
}
function SessionPane({
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
  const [messageDraft, setMessageDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [recipientScope, setRecipientScope] = useState<"global" | "dm_only" | "player">("global");
  const [recipientPlayerId, setRecipientPlayerId] = useState("");
  const recipientPlayerChoices = payload?.session_message_recipient_player_choices ?? [];

  useEffect(() => {
    if (recipientScope !== "player") {
      setRecipientPlayerId("");
      return;
    }
    if (recipientPlayerChoices.length === 0) {
      setRecipientPlayerId("");
      return;
    }
    const validIds = new Set(recipientPlayerChoices.map((choice) => String(choice.user_id)));
    if (!validIds.has(recipientPlayerId)) {
      setRecipientPlayerId(String(recipientPlayerChoices[0].user_id));
    }
  }, [recipientScope, recipientPlayerChoices, recipientPlayerId]);

  const postMessage = useMutation({
    mutationFn: (payload: SessionMessagePostPayload) => apiClient.postSessionMessage(campaignSlug, payload),
    onSuccess: () => {
      setMessageDraft("");
      setSendError(null);
      refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSendError(apiErrorMessage(error));
    },
  });

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = messageDraft.trim();
    if (!body) {
      setSendError("Type a message first.");
      return;
    }
    if (!payload?.permissions.can_post_messages) {
      setSendError("You do not have permission to post messages.");
      return;
    }
    if (!payload?.active_session) {
      setSendError("No active session.");
      return;
    }
    if (recipientScope === "player" && !recipientPlayerChoices.length) {
      setSendError("No player recipients available.");
      return;
    }
    if (recipientScope === "player" && !recipientPlayerId) {
      setSendError("Choose a player recipient.");
      return;
    }

    const messagePayload: SessionMessagePostPayload = {
      body,
      recipient_scope: recipientScope,
    };
    if (recipientScope === "player") {
      messagePayload.recipient_user_id = Number(recipientPlayerId);
    }
    postMessage.mutate(messagePayload);
  };

  const revealedArticles = payload?.revealed_articles ?? [];
  return (
    <div className="page-layout session-layout session-layout--single">
      <section className="session-column">
        <article className="card session-status-card" data-session-status-card>
          <div className="section-heading">
            <h2>Live session</h2>
            <p className="meta">{payload?.active_session ? "Chat open" : "Chat closed"}</p>
          </div>
          <div className="status-row">
            <article className="stat-card">
              <h3>Session</h3>
              <p>{payload?.active_session ? payload.active_session.status : "inactive"}</p>
            </article>
            <article className="stat-card">
              <h3>Messages</h3>
              <p>{payload?.messages.length ?? 0}</p>
            </article>
            <article className="stat-card">
              <h3>Session ID</h3>
              <p>{payload?.active_session?.id ?? "none"}</p>
            </article>
          </div>
        </article>
        <SessionPaneChat
          payload={payload}
        />
        <SessionPaneMessageComposer
          payload={payload}
          messageDraft={messageDraft}
          setMessageDraft={setMessageDraft}
          recipientScope={recipientScope}
          setRecipientScope={setRecipientScope}
          recipientPlayerId={recipientPlayerId}
          setRecipientPlayerId={setRecipientPlayerId}
          recipientPlayerChoices={recipientPlayerChoices}
          sendError={sendError}
          onSend={sendMessage}
          isSending={postMessage.isPending}
        />
        {revealedArticles.length ? (
          <SessionArticlesPanel
            campaignSlug={campaignSlug}
            articles={revealedArticles}
            title="Revealed articles"
            emptyText="No revealed articles yet."
          />
        ) : null}
      </section>

    </div>
  );
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
  const notes = asRecord(state.notes);
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
      setStatusMessage(`${response.preview.label} preview loaded.`);
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
                      {item.name} ({item.slug})
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
                <h3>
                  {selected.name} ({selected.slug})
                </h3>
                <p>
                  HP: {readNumber(vitals.current_hp, selected.current_hp)} / {readNumber(stats.max_hp, selected.max_hp)}
                </p>
                <p>Temp HP: {readNumber(vitals.temp_hp, selected.temp_hp)}</p>
                {selected.hit_dice?.value ? <p>Hit Dice: {selected.hit_dice.value}</p> : null}
                <p>Class: {selected.class_level_text || "Unknown"}</p>
                <p>System: {characterSystem(detailRecord)}</p>
                <p>Status: {selected.status}</p>
                <p>Revision: {revision || selected.revision}</p>
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
                              const data = asRecord(record) as CharacterXianxiaNamedRecord;
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
                                  {(typeLabel || sourceLabel) ? (
                                    <li className="meta">{joinDisplay([typeLabel, sourceLabel], " | ")}</li>
                                  ) : null}
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
                                {asRecordArray(presentedXianxia.approval?.dao_immolating_prepared).map((record, index) => (
                                  <option key={draftKey(record.name, index)} value={String(index)}>
                                    {record.name || `Prepared note ${index + 1}`}
                                  </option>
                                ))}
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
                  <div className="resource-grid resource-grid--compact">
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
                              className="session-inline-form"
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
                  <div className="spell-card-grid">
                    {presentedSpells.map((spell) => {
                      const spellCardContent = (
                        <>
                          <span className="spell-card__eyebrow">
                            {[spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell"}
                          </span>
                          <span className="spell-card__name">{spell.name || "Spell"}</span>
                          {spell.badges?.length ? (
                            <span className="badge-list spell-card__badges">
                              {spell.badges.map((badge) => (
                                <span className="meta-badge" key={badge}>
                                  {badge}
                                </span>
                              ))}
                            </span>
                          ) : null}
                          <span className="spell-card__meta">
                            {[spell.casting_time, spell.range].filter((value) => value && value !== "--").join(" | ")}
                          </span>
                        </>
                      );
                      return (
                        <article className="spell-card" key={draftKey(spell.class_row_id, spell.name, spell.level_label)}>
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
                ) : spells.length ? (
                  <div className="spell-card-grid">
                    {spells.map((spell) => (
                      <article className="spell-card" key={readString(spell.id, readString(spell.name))}>
                        <span className="spell-card__main">
                          {[spell.level_label, spell.school].filter(Boolean).length ? (
                            <span className="spell-card__eyebrow">
                              {[spell.level_label, spell.school].filter(Boolean).join(" | ")}
                            </span>
                          ) : null}
                          <span className="spell-card__name">{readString(spell.name, "Spell")}</span>
                          <span className="spell-card__meta">
                            {[spell.mark, spell.casting_time, spell.range]
                              .map((value) => readString(value))
                              .filter((value) => value && value !== "--")
                              .join(" | ")}
                          </span>
                        </span>
                      </article>
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
                        return (
                          <article
                            className="ability-card ability-card--skills"
                            key={readString(abilityRecord.key, `ability-${abilityIndex}`)}
                          >
                            <div>
                              <p className="card-kicker">{readString(abilityRecord.abbr, readString(abilityRecord.key))}</p>
                              <h3>{abilityScore}</h3>
                              <p>{readString(abilityRecord.name)}</p>
                              <p className="meta">
                                Modifier {readString(abilityRecord.modifier)} | Save {readString(abilityRecord.save_bonus)}
                              </p>
                            </div>
                            {abilitySkills.length ? (
                              <ul className="plain-list ability-skill-list">
                                {abilitySkills.map((skill, skillIndex) => {
                                  const skillRecord = asRecord(skill);
                                  const isProficient = Boolean(skillRecord.is_proficient);
                                  const proficiencyLabel = readString(skillRecord.proficiency_label);
                                  return (
                                    <li
                                      className={
                                        isProficient
                                          ? "ability-skill-list__item ability-skill-list__item--proficient"
                                          : "ability-skill-list__item"
                                      }
                                      key={readString(skillRecord.name, `skill-${abilityIndex}-${skillIndex}`)}
                                    >
                                      <span>{readString(skillRecord.name)}</span>
                                      <strong>{readString(skillRecord.bonus)}</strong>
                                      {proficiencyLabel && proficiencyLabel !== "None" ? (
                                        <span className="meta">{proficiencyLabel}</span>
                                      ) : null}
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
        {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
      </CharacterShell>
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
  { label: "Overview", targetSubdir: "overview", defaultType: "overview" },
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
  return PLAYER_WIKI_SECTION_CHOICES.find((choice) => choice.label.toLowerCase() === normalized) ?? PLAYER_WIKI_SECTION_CHOICES[8];
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

function CharacterRosterPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/characters",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const initialQuery = new URLSearchParams(window.location.search).get("q") || "";
  const [searchDraft, setSearchDraft] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);

  const rosterQuery = useQuery({
    queryKey: ["characters", resolvedCampaignSlug, submittedQuery],
    queryFn: () => apiClient.getCharacters(resolvedCampaignSlug, submittedQuery),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(rosterQuery.error)) {
      setAuthRequired(true);
    }
  }, [rosterQuery.error, setAuthRequired]);

  const data = rosterQuery.data;
  const characters = data?.characters ?? [];
  const error = getApiErrorMessage(rosterQuery.error);
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = searchDraft.trim();
    const nextUrl = nextQuery
      ? `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters?q=${encodeURIComponent(nextQuery)}`
      : `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters`;
    window.history.pushState(null, "", nextUrl);
    setSubmittedQuery(nextQuery);
  };
  const hasCreateCharacterLink = Boolean(data?.links?.create_character_url);
  const characterCreateLane = data?.tools?.character_create_lane;
  const rosterMeta = hasCreateCharacterLink
    ? characterCreateLane === "xianxia"
      ? "Use the Xianxia character creator to start new native character records directly in the app."
      : "Use the current PHB level 1 builder to create new characters directly in the app."
    : "Native character creation and progression stay hidden here for campaigns outside the current DND-5E in-app toolset.";

  return (
    <>
      <section className="hero compact character-roster-hero">
        <p className="eyebrow">Character roster</p>
        <h1>Characters</h1>
        <p className="lede">Open player sheets, use the shared inline state controls, and keep larger authoring workflows in Flask while Gen2 parity grows.</p>
      </section>
      <ApiErrorNotice isLoading={rosterQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      <section className="card search-card character-roster-tools">
        <div className="section-heading">
          <div>
            <h2>{hasCreateCharacterLink ? "Roster tools" : "Roster"}</h2>
            <p className="meta">{rosterMeta}</p>
          </div>
          {data?.links?.create_character_url ? (
            <a className="button-link" href={data.links.create_character_url}>
              Create character
            </a>
          ) : null}
          {data?.links?.import_xianxia_url ? (
            <a className="button-link" href={data.links.import_xianxia_url}>
              Import existing character
            </a>
          ) : null}
        </div>
        <form className="search-form character-roster-search" onSubmit={submitSearch}>
          <input
            type="search"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.currentTarget.value)}
            placeholder="Search characters by name, class, species, or background"
            aria-label="Search characters"
          />
          <button type="submit">Search</button>
        </form>
        {data ? (
          <p className="meta">
            {data.result_count ?? characters.length} character{(data.result_count ?? characters.length) === 1 ? "" : "s"} visible
          </p>
        ) : null}
      </section>
      {data ? (
        <>
          {characters.length ? (
            <div className="character-roster-grid">
              {characters.map((character) => (
                <article className="card character-card" key={character.slug}>
                  <div className="character-card__top">
                    {character.portrait ? (
                      <img className="character-card__portrait" src={character.portrait.url} alt={character.portrait.alt_text || character.name} />
                    ) : null}
                    <div>
                      <p className="card-kicker">{character.class_level_text || character.system || "Character"}</p>
                      <h2>
                        <a href={character.href || `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters/${encodeURIComponent(character.slug)}`}>
                          {character.name}
                        </a>
                      </h2>
                      <p className="meta">
                        {[character.species, character.background].filter(Boolean).join(" | ") || character.status}
                      </p>
                    </div>
                  </div>
                  <div className="character-card__stats">
                    <article>
                      <span className="meta">HP</span>
                      <strong>
                        {character.current_hp} / {character.max_hp}
                      </strong>
                    </article>
                    <article>
                      <span className="meta">Temp HP</span>
                      <strong>{character.temp_hp}</strong>
                    </article>
                    {character.hit_dice?.value ? (
                      <article>
                        <span className="meta">Hit Dice</span>
                        <strong>{character.hit_dice.value}</strong>
                      </article>
                    ) : null}
                  </div>
                  {character.resource_preview?.length ? (
                    <ul className="plain-list resource-preview-list">
                      {character.resource_preview.map((resource) => (
                        <li key={`${character.slug}-${resource.label}`}>
                          <span>{resource.label}</span>
                          <strong>{resource.value}</strong>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <a
                    className="button-link"
                    href={
                      character.href || `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters/${encodeURIComponent(character.slug)}`
                    }
                  >
                    Open sheet
                  </a>
                </article>
              ))}
            </div>
          ) : (
            <section className="card">
              <h2>{submittedQuery ? "No matching characters" : "No visible characters yet"}</h2>
              <p>{submittedQuery ? "Try a broader search term or clear the current filter." : "This campaign does not currently have active player sheets available in the app."}</p>
            </section>
          )}
        </>
      ) : null}
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

  useEffect(() => {
    if (!canAccessSystems && combatAddMode === "systems") {
      setCombatAddMode("player");
    } else if (!canAccessDmContent && combatAddMode === "dm-content") {
      setCombatAddMode("player");
    }
  }, [canAccessSystems, canAccessDmContent, combatAddMode]);

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
            <article>
              <span className="meta">Live revision</span>
              <strong>{payload.live_revision}</strong>
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

  useEffect(() => {
    setActivePane((previousActivePane) => coerceSessionPane(previousActivePane, canManage));
  }, [canManage]);

  const paneError = getApiErrorMessage(sessionQuery.error);

  return (
    <section className="session-page-shell">
      <section className="hero compact session-hero">
        <p className="eyebrow">Session Workspace</p>
        <h1>Session</h1>
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
