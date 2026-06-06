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
import type { ChangeEvent, FormEvent } from "react";
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
  SessionLogSummary,
  SessionMessage,
  SessionPayload,
  SessionWikiLookupPreviewResponse,
  SessionWikiLookupSearchResult,
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
}

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
    <aside className="panel character-authoring-sidebar">
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
      {listSections.map(([label, values]) => (
        <section className="character-authoring-preview-section" key={String(label)}>
          <h3>{label}</h3>
          <ul className="plain-list resource-preview-list">
            {(values as string[]).map((item) => (
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
    <aside className="panel character-authoring-sidebar">
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
      {listSections.map(([label, values]) => (
        <section className="character-authoring-preview-section" key={label}>
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
    <section className="panel character-authoring-page">
      <div className="panel-header">
        <div>
          <p className="meta">Character authoring</p>
          <h1>{create?.lane === "xianxia" ? "Create Xianxia Character" : "Create Character"}</h1>
          <p className="lede">Create native character records through the same campaign system lane used by the Flask builder.</p>
        </div>
        <div className="article-actions">
          {data?.links.gen2_roster_url ? (
            <a className="button button-secondary" href={data.links.gen2_roster_url}>
              Back to roster
            </a>
          ) : null}
          {data?.links.flask_create_url ? (
            <a className="button button-secondary" href={data.links.flask_create_url}>
              Flask create
            </a>
          ) : null}
          {data?.links.gen2_import_xianxia_url ? (
            <a className="button button-secondary" href={data.links.gen2_import_xianxia_url}>
              Import existing
            </a>
          ) : null}
        </div>
      </div>
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
              <button type="button" className="button button-secondary" onClick={() => refreshContext()}>
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
          <aside className="panel character-authoring-sidebar">
            <h2>Starting Defaults</h2>
            <div className="builder-preview-list">
              {Object.entries(create.defaults).map(([key, value]) => (
                <div key={key}>
                  <span className="meta">{key.replace(/_/g, " ")}</span>
                  <strong>{stringFromUnknown(value)}</strong>
                </div>
              ))}
            </div>
          </aside>
        </div>
      ) : null}
    </section>
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
    <section className="panel character-authoring-page">
      <div className="panel-header">
        <div>
          <p className="meta">Character importer</p>
          <h1>Import Existing Xianxia Character</h1>
          <p className="lede">Preview copied values, then create a normal native Xianxia sheet with SQLite-backed mutable state.</p>
        </div>
        <div className="article-actions">
          {links?.gen2_roster_url ? (
            <a className="button button-secondary" href={links.gen2_roster_url}>
              Back to roster
            </a>
          ) : null}
          {links?.flask_import_xianxia_url ? (
            <a className="button button-secondary" href={links.flask_import_xianxia_url}>
              Flask import
            </a>
          ) : null}
        </div>
      </div>
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
              <button type="button" className="button button-secondary" onClick={() => setRowCount((current) => current + 1)}>
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
          <aside className="panel character-authoring-sidebar">
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
          </aside>
        </div>
      ) : null}
    </section>
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
    <section className="page campaign-page character-authoring-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Character editor</p>
          <h1>Edit {characterName}</h1>
          <p className="lede">Advanced campaign-time adjustments and durable reference text for this character are managed here.</p>
        </div>
        <div className="button-row">
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.flask_advanced_editor_url ? (
            <a className="button button-secondary" href={data.links.flask_advanced_editor_url}>
              Flask editor
            </a>
          ) : null}
          {classLevelText ? <span className="meta">{classLevelText}</span> : null}
        </div>
      </div>

      <ApiErrorNotice isLoading={editorQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card">
          <h2>Advanced Editor Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character system uses a different authoring lane."}</p>
          <div className="button-row">
            {data.links.character_url ? (
              <a className="button" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="button button-secondary" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
            {data.links.flask_character_url ? (
              <a className="button button-secondary" href={data.links.flask_character_url}>
                Flask sheet
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

          <div className="builder-actions">
            <button type="submit" disabled={saveEditor.isPending}>
              {saveEditor.isPending ? "Saving..." : "Save character edits"}
            </button>
            {data?.links?.character_url ? (
              <a className="button button-secondary" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
          </div>
        </form>
      ) : null}
    </section>
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
    <section className="page campaign-page character-authoring-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Character progression</p>
          <h1>Prepare {characterName} For Native Level-Up</h1>
          <p className="lede">
            Repair imported baseline links and missing DND-5E progression details before advancing this character
            {repair?.current_level ? ` past level ${repair.current_level}` : ""}.
          </p>
          {classLevelText ? <p className="meta">{classLevelText}</p> : null}
        </div>
        <div className="button-row">
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.flask_progression_repair_url ? (
            <a className="button button-secondary" href={data.links.flask_progression_repair_url}>
              Flask repair
            </a>
          ) : null}
        </div>
      </div>

      <ApiErrorNotice isLoading={repairQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card">
          <h2>{data.lane === "ready" ? "Progression Repair Is Complete" : "Progression Repair Is Not Available In Gen2"}</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 progression repair."}</p>
          <div className="button-row">
            {data.links.level_up_url ? (
              <a className="button" href={data.links.level_up_url}>
                Level Up
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="button button-secondary" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
            {data.links.flask_character_url ? (
              <a className="button button-secondary" href={data.links.flask_character_url}>
                Flask sheet
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
              <button type="submit" disabled={submitRepair.isPending}>
                {submitRepair.isPending ? "Saving..." : "Save Repair"}
              </button>
              {data?.links?.character_url ? (
                <a className="button button-secondary" href={data.links.character_url}>
                  Cancel
                </a>
              ) : null}
            </div>
          </form>
        </article>
      ) : null}
    </section>
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
    <section className="page campaign-page character-authoring-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Character retraining</p>
          <h1>Retrain {characterName}</h1>
          {classLevelText ? <p className="lede">{classLevelText}</p> : null}
        </div>
        <div className="button-row">
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.advanced_editor_url ? (
            <a className="button button-secondary" href={data.links.advanced_editor_url}>
              Advanced Editor
            </a>
          ) : null}
          {data?.links?.flask_retraining_url ? (
            <a className="button button-secondary" href={data.links.flask_retraining_url}>
              Flask retraining
            </a>
          ) : null}
        </div>
      </div>

      <ApiErrorNotice isLoading={retrainingQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card">
          <h2>Retraining Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 retraining."}</p>
          <div className="button-row">
            {data.links.character_url ? (
              <a className="button" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.progression_repair_url ? (
              <a className="button button-secondary" href={data.links.progression_repair_url}>
                Progression repair
              </a>
            ) : data?.links?.flask_progression_repair_url ? (
              <a className="button button-secondary" href={data.links.flask_progression_repair_url}>
                Flask repair
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="button button-secondary" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
            {data.links.flask_character_url ? (
              <a className="button button-secondary" href={data.links.flask_character_url}>
                Flask sheet
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

            <div className="builder-actions">
              <button type="submit" disabled={submitRetraining.isPending}>
                {submitRetraining.isPending ? "Saving..." : "Save retraining"}
              </button>
              {data?.links?.character_url ? (
                <a className="button button-secondary" href={`${data.links.character_url}?page=features`}>
                  Cancel
                </a>
              ) : null}
            </div>
          </form>
        </article>
      ) : null}
    </section>
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
    <section className="page campaign-page character-authoring-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Character level-up</p>
          <h1>Level Up {characterName}</h1>
          {classLevelText ? <p className="lede">{classLevelText}</p> : null}
        </div>
        <div className="button-row">
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.flask_level_up_url ? (
            <a className="button button-secondary" href={data.links.flask_level_up_url}>
              Flask level-up
            </a>
          ) : null}
        </div>
      </div>

      <ApiErrorNotice isLoading={levelUpQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card">
          <h2>Level-Up Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 level-up."}</p>
          <div className="button-row">
            {data.links.character_url ? (
              <a className="button" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.progression_repair_url ? (
              <a className="button button-secondary" href={data.links.progression_repair_url}>
                Progression repair
              </a>
            ) : data.links.flask_progression_repair_url ? (
              <a className="button button-secondary" href={data.links.flask_progression_repair_url}>
                Flask repair
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="button button-secondary" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
            {data.links.flask_character_url ? (
              <a className="button button-secondary" href={data.links.flask_character_url}>
                Flask sheet
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
              <button type="button" className="button button-secondary" onClick={() => refreshContext()}>
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
    </section>
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
    <section className="page campaign-page character-authoring-page cultivation-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Character cultivation</p>
          <h1>Cultivation: {characterName}</h1>
          <p className="lede">Insight-based advancement for this Xianxia character.</p>
        </div>
        <div className="button-row">
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={`${data.links.character_url}?page=martial_arts`}>
              Martial Arts
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={`${data.links.character_url}?page=techniques`}>
              Techniques
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="button button-secondary" href={`${data.links.character_url}?page=resources`}>
              Resources
            </a>
          ) : null}
          {data?.links?.flask_cultivation_url ? (
            <a className="button button-secondary" href={data.links.flask_cultivation_url}>
              Flask Cultivation
            </a>
          ) : null}
          {classLevelText ? <span className="meta">{classLevelText}</span> : null}
        </div>
      </div>

      <ApiErrorNotice isLoading={cultivationQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card">
          <h2>Cultivation Is Not Available</h2>
          <p>{data.unsupported_message || "This character system uses a different advancement lane."}</p>
          <div className="button-row">
            {data.links.character_url ? (
              <a className="button" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.flask_character_url ? (
              <a className="button button-secondary" href={data.links.flask_character_url}>
                Flask sheet
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
    </section>
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

function renderArticleBody(article: SessionArticle): JSX.Element {
  if (article.body_format === "html") {
    return <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: article.body_markdown }} />;
  }
  return <pre className="article-body markdown-body">{article.body_markdown}</pre>;
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
      <a className="button button-secondary" href={sourceUrl}>
        {article.source?.action_label || "View source"}
      </a>
    );
  }

  if (sourceKind) {
    return article.source?.missing_message ? <span className="article-action-note">{article.source.missing_message}</span> : null;
  }

  const publishedPageUrl = getArticleUrl(article.links?.published_page_url);
  if (publishedPageUrl) {
    return (
      <a className="button button-secondary" href={publishedPageUrl}>
        View published page
      </a>
    );
  }

  const convertedTitle = article.converted_page?.title?.trim() || "";
  if (convertedTitle) {
    return (
      <span className="article-action-note">
        Converted to {convertedTitle}
        {article.converted_page?.reveal_after_session !== null && article.converted_page?.reveal_after_session !== undefined
          ? `; visible after session ${article.converted_page.reveal_after_session}`
          : ""}
        .
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
        <a className="button button-secondary" href={editorUrl}>
          Open in Player Wiki editor
        </a>
      ) : null}
      {convertUrl ? (
        <a className="button button-secondary" href={convertUrl}>
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

function AuthNotice() {
  const { authRequired, setApiToken } = useApiClient();
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  if (!authRequired) {
    return null;
  }

  return (
    <section className="panel auth-notice">
      <h3>Authentication required</h3>
      <p className="status status-error">
        Your cookie or API token did not authenticate this request. Sign in to restore session.
      </p>
      <a className="button button-secondary" href={signInHref}>
        Sign in
      </a>
      <button type="button" className="button" onClick={() => setApiToken("")}>
        Continue without token
      </button>
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
  const [campaignSearchQuery, setCampaignSearchQuery] = useState("");
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
    setCampaignSearchQuery(new URLSearchParams(window.location.search).get("q") || "");
  }, [location.pathname, location.search]);

  useEffect(() => {
    const themeKey = meQuery.data?.preferences?.theme_key;
    if (themeKey) {
      document.documentElement.dataset.theme = themeKey;
    }
  }, [meQuery.data?.preferences?.theme_key]);

  const user = meQuery.data?.user;
  const campaign = campaignQuery.data?.campaign;
  const campaignPermissions = campaignQuery.data?.permissions;
  const campaignVisibility = campaignQuery.data?.visibility;
  const encodedCampaignSlug = encodeURIComponent(campaignSlug);

  const navItems = useMemo(
    () => [
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}`,
        label: "Campaign Home",
        isGen2: true,
        show: campaignVisibilityCanAccess(campaignVisibility, "campaign"),
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/session`,
        label: "Session",
        isGen2: true,
        show: campaignVisibilityCanAccess(campaignVisibility, "session"),
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/combat`,
        label: "Combat",
        isGen2: true,
        show: campaignVisibilityCanAccess(campaignVisibility, "combat"),
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/characters`,
        label: "Characters",
        isGen2: true,
        show: campaignVisibilityCanAccess(campaignVisibility, "characters"),
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/systems`,
        label: "Systems",
        isGen2: true,
        show: campaignVisibilityCanAccess(campaignVisibility, "systems"),
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/dm-content`,
        label: "DM Content",
        isGen2: true,
        show:
          campaignVisibilityCanAccess(campaignVisibility, "dm_content")
          || campaignPermissions?.can_manage_dm_content === true
          || campaignPermissions?.can_manage_content === true,
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/control`,
        label: "Control",
        isGen2: true,
        show: campaignPermissions?.can_manage_visibility === true,
      },
      {
        href: `/app-next/campaigns/${encodedCampaignSlug}/help`,
        label: "Help",
        isGen2: true,
        show: Boolean(campaignQuery.data),
      },
    ],
    [
      campaignPermissions?.can_manage_content,
      campaignPermissions?.can_manage_dm_content,
      campaignPermissions?.can_manage_visibility,
      campaignQuery.data,
      campaignVisibility,
      encodedCampaignSlug,
    ],
  );

  const visibleNavItems = navItems.filter((entry) => entry.show);
  const campaignSearchAction = campaignSlug ? `/app-next/campaigns/${encodedCampaignSlug}` : "";
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
    <ApiClientContext.Provider value={{ apiClient, apiToken, setApiToken: setStoredToken, authRequired, setAuthRequired }}>
      <div className="session-shell">
        <header className={campaign ? "topbar topbar--campaign" : "topbar"}>
          <div className="brand-block">
            <Link to="/" className="brand-link">
              Campaign Player Wiki
            </Link>
            <p className="subtitle">Gen2 companion</p>
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
                    <a className="button button-secondary" href="/app-next/admin">
                      Admin
                    </a>
                  ) : null}
                  <a className="button button-secondary" href="/app-next/account">
                    Account
                  </a>
                  <span className="user-badge">
                    {user.display_name}
                    {user.is_admin ? <span className="user-badge__role">Admin</span> : null}
                  </span>
                  <form method="post" action="/sign-out">
                    <button type="submit" className="button button-secondary">
                      Sign out
                    </button>
                  </form>
                </>
              ) : (
                <a className="button button-secondary sign-in-link" href={signInHref}>
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
            {campaignVisibilityCanAccess(campaignVisibility, "wiki") ? (
              <form className="campaign-search-form" action={campaignSearchAction} method="get">
                <label htmlFor="gen2-campaign-search">Search</label>
                <input
                  id="gen2-campaign-search"
                  name="q"
                  type="search"
                  value={campaignSearchQuery}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setCampaignSearchQuery(event.currentTarget.value)}
                />
                <button
                  type="submit"
                  className="button button-secondary"
                  onClick={() => setNavigationLabel("Campaign Home")}
                >
                  Search
                </button>
              </form>
            ) : null}
            {navigationLabel ? (
              <p className="navigation-status" role="status">
                Loading {navigationLabel}...
              </p>
            ) : null}
          </div>
        ) : null}
        <AuthNotice />
        <main className="main-shell">
          <Outlet />
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}

function CampaignListPage() {
  const { apiClient, setAuthRequired } = useApiClient();

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

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Available Campaigns</h2>
      </div>
      <ApiErrorNotice
        isLoading={appQuery.isLoading || campaignsQuery.isLoading}
        message={appError ?? campaignError}
        onAuth={() => setAuthRequired(true)}
      />
      {appQuery.data?.app ? (
        <p className="subtitle">
          Runtime: {appQuery.data.app.runtime}
          {appQuery.data.app.version ? ` - ${appQuery.data.app.version}` : ""}
        </p>
      ) : null}
      <div className="campaign-grid">
        {campaigns.map((entry) => (
          <article className="card" key={entry.campaign.slug}>
            <h3>{entry.campaign.title}</h3>
            <p className="subtitle">{entry.campaign.slug}</p>
            <p>{entry.campaign.summary}</p>
            <p>
              <strong>System:</strong> {entry.campaign.system}
            </p>
            <p>
              <strong>Role:</strong> {entry.role}
            </p>
            <div className="article-actions">
              <a className="button" href={`/app-next/campaigns/${encodeURIComponent(entry.campaign.slug)}`}>
                Open Campaign
              </a>
              <Link to="/campaigns/$campaignSlug/session" params={{ campaignSlug: entry.campaign.slug }} className="button button-secondary">
                Open Session
              </Link>
            </div>
          </article>
        ))}
        {!appQuery.isLoading && !campaignsQuery.isLoading && !campaigns.length && !campaignError ? (
          <p className="status status-neutral">No campaigns are visible to this account.</p>
        ) : null}
      </div>
    </section>
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
      <div className="button-row">
        <button type="submit" className="button">
          Filter activity
        </button>
        <a className="button button-secondary" href={clearHref}>
          Clear
        </a>
        <a className="button button-secondary" href={data.export_url}>
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
      <div className="button-row">
        {pagination.has_previous ? (
          <a className="button button-secondary" href={pagination.previous_url}>
            Previous
          </a>
        ) : null}
        {pagination.has_next ? (
          <a className="button button-secondary" href={pagination.next_url}>
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
    <section className="admin-page">
      <div className="panel admin-hero">
        <p className="eyebrow">Admin</p>
        <h1>Admin dashboard</h1>
        <p className="lede">Use this screen for lighter operational work. The CLI remains the full-control path for bootstrap and recovery.</p>
        {data ? (
          <div className="button-row">
            <a className="button button-secondary" href={data.links.flask_admin_url}>
              Flask admin
            </a>
          </div>
        ) : null}
      </div>

      <ApiErrorNotice isLoading={dashboardQuery.isLoading} message={queryError} onAuth={() => setAuthRequired(true)} />
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}

      {data ? (
        <>
          <section className="page-layout admin-layout">
            <article className="panel admin-panel">
              <h2>Invite user</h2>
              <form
                className="stack-form"
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
                <button type="submit" className="button" disabled={inviteMutation.isPending}>
                  {inviteMutation.isPending ? "Creating..." : "Create invite"}
                </button>
              </form>
            </article>

            <aside className="panel admin-panel">
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

          <section className="section-list">
            <div className="section-heading">
              <h2>Users</h2>
              <p className="meta">{data.user_cards.length} total</p>
            </div>
            <div className="grid admin-user-grid">
              {data.user_cards.map((user) => (
                <article key={user.id} className="panel admin-user-card">
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

          <section className="section-list">
            <div className="section-heading">
              <h2>Recent activity</h2>
              <p className="meta">{data.pagination.total_events} matching events</p>
            </div>
            <article className="panel admin-panel">
              <AdminActivityFilters action="/app-next/admin" clearHref="/app-next/admin" data={data} />
              <AdminActivityList events={data.recent_audit_events} />
              <AdminPagination pagination={data.pagination} />
            </article>
          </section>
        </>
      ) : null}
    </section>
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
    <section className="admin-page admin-user-detail-page">
      <div className="panel admin-hero">
        <p className="eyebrow">Admin user detail</p>
        <h1>{data?.managed_user.display_name || "Admin user"}</h1>
        {data ? (
          <>
            <p className="lede">{data.managed_user.email}</p>
            <p className="meta">
              Status: {data.managed_user.status}
              {data.managed_user.is_admin ? " | App admin" : ""}
            </p>
            <div className="button-row">
              <a className="button button-secondary" href={data.links.gen2_admin_url}>
                Back to admin dashboard
              </a>
              <a className="button button-secondary" href={data.links.flask_user_url}>
                Flask user record
              </a>
            </div>
          </>
        ) : null}
      </div>

      <ApiErrorNotice isLoading={userQuery.isLoading} message={queryError} onAuth={() => setAuthRequired(true)} />
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}

      {data ? (
        <>
          <section className="page-layout admin-layout">
            <article className="panel admin-panel">
              <h2>Campaign membership</h2>
              <form
                className="stack-form"
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
                <button type="submit" className="button" disabled={mutationPending || !membershipDraft.campaign_slug}>
                  {setMembership.isPending ? "Saving..." : "Save membership"}
                </button>
              </form>
            </article>

            <article className="panel admin-panel">
              <h2>Character assignment</h2>
              <p className="meta">Assignments require an active player membership in the same campaign.</p>
              <form
                className="stack-form"
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
                <button type="submit" className="button" disabled={mutationPending || !assignmentDraft.character_ref}>
                  {assignCharacter.isPending ? "Assigning..." : "Assign character"}
                </button>
              </form>
            </article>
          </section>

          <section className="page-layout admin-layout">
            <article className="panel admin-panel">
              <h2>Current memberships</h2>
              {data.memberships.length ? (
                <ul className="plain-list admin-item-list">
                  {data.memberships.map((membership) => (
                    <li key={membership.id} className="admin-item-row">
                      <div>
                        <strong>{membership.campaign_title}</strong>
                        <span className="meta"> {membership.role} | {membership.status}</span>
                      </div>
                      <div className="button-row">
                        <a className="button button-secondary" href={`${data.links.gen2_user_url}?edit_membership_campaign_slug=${encodeURIComponent(membership.campaign_slug)}`}>
                          Edit
                        </a>
                        {membership.status !== "removed" ? (
                          <button type="button" className="button button-secondary" disabled={mutationPending} onClick={() => removeMembership.mutate(membership)}>
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

            <article className="panel admin-panel">
              <h2>Current assignments</h2>
              {data.assignments.length ? (
                <ul className="plain-list admin-item-list">
                  {data.assignments.map((assignment) => (
                    <li key={assignment.id} className="admin-item-row">
                      <div>
                        <strong>{assignment.campaign_title}</strong>
                        <span className="meta"> {assignment.character_slug} | {assignment.assignment_type}</span>
                      </div>
                      <div className="button-row">
                        <a
                          className="button button-secondary"
                          href={`${data.links.gen2_user_url}?edit_assignment_campaign_slug=${encodeURIComponent(assignment.campaign_slug)}&edit_assignment_character_slug=${encodeURIComponent(assignment.character_slug)}`}
                        >
                          Edit
                        </a>
                        <button type="button" className="button button-secondary" disabled={mutationPending} onClick={() => removeAssignment.mutate(assignment)}>
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
            <article className="panel admin-panel">
              <h2>Account actions</h2>
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
                {data.can_manage_account && data.managed_user.status === "disabled" ? (
                  <button type="button" className="button" disabled={mutationPending} onClick={() => enableUser.mutate()}>
                    {enableUser.isPending ? "Saving..." : "Re-enable user"}
                  </button>
                ) : null}
                {data.can_manage_account && data.managed_user.status !== "disabled" ? (
                  <button type="button" className="button button-secondary" disabled={mutationPending} onClick={() => disableUser.mutate()}>
                    {disableUser.isPending ? "Saving..." : "Disable user"}
                  </button>
                ) : null}
                {data.can_manage_account ? (
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
                      className="button-danger"
                      disabled={mutationPending || deleteConfirm.trim().toLowerCase() !== data.managed_user.email.toLowerCase()}
                      onClick={() => deleteUser.mutate()}
                    >
                      {deleteUser.isPending ? "Deleting..." : "Delete user"}
                    </button>
                  </div>
                ) : (
                  <p className="meta">Use a different admin account or the CLI if you ever need to change the account you are currently using.</p>
                )}
              </div>
            </article>

            <article className="panel admin-panel">
              <div className="panel-header">
                <h2>Recent activity for this user</h2>
                <p className="meta">{data.pagination.total_events} matching events</p>
              </div>
              <AdminActivityFilters action={data.links.gen2_user_url || `/app-next/admin/users/${userId}`} clearHref={data.links.gen2_user_url || `/app-next/admin/users/${userId}`} data={data} />
              <AdminActivityList events={data.recent_audit_events} />
              <AdminPagination pagination={data.pagination} />
            </article>
          </section>
        </>
      ) : null}
    </section>
  );
}

function AccountSettingsPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftThemeKey, setDraftThemeKey] = useState("");
  const [draftChatOrder, setDraftChatOrder] = useState("");
  const [draftFrontendMode, setDraftFrontendMode] = useState("");
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
    setDraftFrontendMode(preferences.frontend_mode || "");
  }, [
    settingsQuery.data?.preferences?.theme_key,
    settingsQuery.data?.preferences?.session_chat_order,
    settingsQuery.data?.preferences?.frontend_mode,
  ]);

  const saveSettings = useMutation({
    mutationFn: (payload: AccountSettingsUpdatePayload) => apiClient.patchAccountSettings(payload),
    onSuccess: (response) => {
      setStatusMessage("Account settings saved.");
      setDraftThemeKey(response.preferences.theme_key || "");
      setDraftChatOrder(response.preferences.session_chat_order || "");
      setDraftFrontendMode(response.preferences.frontend_mode || "");
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
  const frontendModeChoices = settingsQuery.data?.frontend_mode_choices ?? [];
  const user = settingsQuery.data?.user;
  const selectedTheme = themePresets.find((theme) => theme.key === (preferences?.theme_key || draftThemeKey));
  const selectedFrontendMode = preferences?.frontend_mode || draftFrontendMode || "flask";
  const campaignBackHref = draftFrontendMode === "gen2" ? "/app-next/" : "/campaigns";
  const hasDraft = Boolean(draftThemeKey || draftChatOrder || draftFrontendMode);
  const isUnchanged =
    draftThemeKey === (preferences?.theme_key || "") &&
    draftChatOrder === (preferences?.session_chat_order || "") &&
    draftFrontendMode === (preferences?.frontend_mode || "");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasDraft) {
      return;
    }
    setStatusMessage(null);
    saveSettings.mutate({
      theme_key: draftThemeKey,
      session_chat_order: draftChatOrder,
      frontend_mode: draftFrontendMode,
    });
  };

  return (
    <section className="account-settings-page">
      <div className="panel account-hero">
        <p className="eyebrow">Account settings</p>
        <h1>{user?.display_name ?? "Account"}</h1>
        <p className="lede">Save interface preferences to your account and use them everywhere you are signed in.</p>
        <p className="meta">
          Current theme: {selectedTheme?.label ?? preferences?.theme_key ?? "Loading"}
          {user?.is_admin ? " | App admin" : ""}
        </p>
      </div>

      <ApiErrorNotice isLoading={settingsQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {settingsQuery.data ? (
        <div className="account-settings-layout">
          <form className="panel account-settings-form" onSubmit={handleSubmit}>
            <section className="account-settings-group">
              <div className="panel-header">
                <div>
                  <h2>Color theme</h2>
                  <p className="meta">These presets restyle the shared app chrome, cards, forms, and reading surfaces.</p>
                </div>
              </div>
              <div className="settings-option-grid">
                {themePresets.map((theme) => {
                  const inputId = `account-theme-${theme.key}`;
                  const checked = draftThemeKey === theme.key;
                  return (
                    <label className={checked ? "settings-option is-selected" : "settings-option"} htmlFor={inputId} key={theme.key}>
                      <input
                        id={inputId}
                        type="radio"
                        name="theme_key"
                        value={theme.key}
                        checked={checked}
                        onChange={() => setDraftThemeKey(theme.key)}
                      />
                      <span className="settings-option__header">
                        <span>
                          <strong>{theme.label}</strong>
                          {preferences?.theme_key === theme.key ? <span className="meta settings-option__status">Current</span> : null}
                        </span>
                        <span className="settings-option__swatches" aria-hidden="true">
                          {theme.preview_colors.map((color) => (
                            <span className="settings-option__swatch" style={{ background: color }} key={color} />
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
              <div className="panel-header">
                <div>
                  <h2>Preferred frontend</h2>
                  <p className="meta">
                    This controls which interface campaign cards open by default when you are signed in. Flask remains available for fallback testing.
                  </p>
                </div>
              </div>
              <div className="settings-option-grid">
                {frontendModeChoices.map((choice) => {
                  const inputId = `account-frontend-mode-${choice.value}`;
                  const checked = draftFrontendMode === choice.value;
                  return (
                    <label className={checked ? "settings-option is-selected" : "settings-option"} htmlFor={inputId} key={choice.value}>
                      <input
                        id={inputId}
                        type="radio"
                        name="frontend_mode"
                        value={choice.value}
                        checked={checked}
                        onChange={() => setDraftFrontendMode(choice.value)}
                      />
                      <span className="settings-option__header">
                        <span>
                          <strong>{choice.label}</strong>
                          {preferences?.frontend_mode === choice.value ? (
                            <span className="meta settings-option__status">Current</span>
                          ) : null}
                        </span>
                      </span>
                      <span className="meta">{choice.description}</span>
                    </label>
                  );
                })}
              </div>
            </section>

            <section className="account-settings-group">
              <div className="panel-header">
                <div>
                  <h2>Live session chat order</h2>
                  <p className="meta">
                    This changes the order of the live Session chat window for your account only. Stored session logs stay chronological.
                  </p>
                </div>
              </div>
              <div className="settings-option-grid">
                {chatOrderChoices.map((choice) => {
                  const inputId = `account-chat-order-${choice.value}`;
                  const checked = draftChatOrder === choice.value;
                  return (
                    <label className={checked ? "settings-option is-selected" : "settings-option"} htmlFor={inputId} key={choice.value}>
                      <input
                        id={inputId}
                        type="radio"
                        name="session_chat_order"
                        value={choice.value}
                        checked={checked}
                        onChange={() => setDraftChatOrder(choice.value)}
                      />
                      <span className="settings-option__header">
                        <span>
                          <strong>{choice.label}</strong>
                          {preferences?.session_chat_order === choice.value ? (
                            <span className="meta settings-option__status">Current</span>
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
              <a className="button button-secondary" href="/account">
                Flask account
              </a>
              <a className="button button-secondary" href="/campaigns">
                Flask campaigns
              </a>
              {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
              {saveError ? <p className="status status-error">{saveError}</p> : null}
            </div>
          </form>

          <aside className="panel account-settings-sidebar">
            <h2>Account</h2>
            <p>
              <strong>{user?.display_name}</strong>
            </p>
            <p className="meta">{user?.email}</p>
            {user?.is_admin ? <p className="meta-badge">App admin</p> : null}
            <p className="meta">Theme, frontend, and live-session chat preferences are stored in the auth database and applied on every signed-in request.</p>
            <p className="meta">Preferred frontend: {selectedFrontendMode === "gen2" ? "Gen2 frontend" : "Stable Flask"}</p>
            <a className="ghost-button" href={campaignBackHref}>
              Back to campaigns
            </a>
            <a className="ghost-button" href="/campaigns">
              Open Flask campaigns
            </a>
          </aside>
        </div>
      ) : null}
    </section>
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
    <section className="campaign-control-page">
      <div className="panel campaign-control-hero">
        <p className="eyebrow">Control panel</p>
        <h1>Visibility</h1>
        <p className="lede">
          Control who can see the campaign, wiki, systems reference, session tools, combat tracker, DM content, and character section.
        </p>
      </div>

      <ApiErrorNotice isLoading={controlQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {data ? (
        <div className="page-layout campaign-control-layout">
          <form className="card campaign-control-form" onSubmit={handleSubmit}>
            <div className="section-heading">
              <div>
                <h2>Visibility settings</h2>
                <p className="meta">The campaign setting acts as the floor; each section can only become as open as that floor allows.</p>
              </div>
            </div>

            <div className="campaign-control-grid">
              {data.visibility_rows.map((row) => {
                const fieldId = `campaign-control-${row.scope}`;
                return (
                  <article className="campaign-control-row" key={row.scope}>
                    <label className="chat-label" htmlFor={fieldId}>
                      {row.label}
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
                    </label>
                    <div className="campaign-control-row__meta">
                      <span className="meta-badge">Effective: {row.effective_visibility_label}</span>
                      {row.configured_visibility_label ? (
                        <span className="meta">Configured: {row.configured_visibility_label}</span>
                      ) : (
                        <span className="meta">Using default: {row.default_visibility_label}</span>
                      )}
                    </div>
                    {row.is_overridden_by_campaign ? (
                      <p className="meta">The campaign-level visibility is currently more private than this section setting.</p>
                    ) : null}
                  </article>
                );
              })}
            </div>

            <div className="article-actions">
              <button type="submit" className="button" disabled={saveVisibility.isPending || isUnchanged}>
                {saveVisibility.isPending ? "Saving..." : "Save visibility"}
              </button>
              <a className="button button-secondary" href={data.links.flask_control_url}>
                Flask Control
              </a>
              {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
              {saveError ? <p className="status status-error">{saveError}</p> : null}
            </div>
          </form>

          <aside className="sidebar campaign-control-sidebar">
            <article className="card sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Visibility rules</h2>
                  <p className="meta">These labels match the Flask Control panel and campaign access checks.</p>
                </div>
              </div>
              <div className="reference-stack">
                {data.rules.map((rule) => (
                  <article className="help-detail-card" key={rule.label}>
                    <h3>{rule.label}</h3>
                    <p className="meta">{rule.description}</p>
                  </article>
                ))}
              </div>
            </article>

            <article className="card sidebar-card">
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
    </section>
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
    <section className="campaign-help-page">
      <div className="panel campaign-help-hero">
        <p className="eyebrow">Help</p>
        <h1>Help</h1>
        <p className="lede">
          Use this page for what each app surface is for, what the current access rules allow,
          and which first-pass limits still shape the workflow.
        </p>
        {data?.surfaces.length ? (
          <div className="help-anchor-row" aria-label="Help sections">
            {data.surfaces.map((surface) => (
              <a className="ghost-button" href={`#${surface.anchor}`} key={surface.anchor}>
                {surface.label}
              </a>
            ))}
          </div>
        ) : null}
      </div>

      <ApiErrorNotice isLoading={helpQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {data ? (
        <div className="page-layout campaign-help-layout">
          <section className="campaign-help-main">
            <article className="card campaign-help-current">
              <div className="section-heading">
                <div>
                  <h2>Current access</h2>
                  <p className="meta">This page holds the broader workflow notes so the main UI can stay focused on actions.</p>
                </div>
              </div>
              <div className="help-detail-grid">
                <article className="help-detail-card">
                  <h3>Viewer role</h3>
                  <p><strong>{data.viewer_role_label}</strong></p>
                  <p className="meta">{data.viewer_role_summary}</p>
                </article>
                <article className="help-detail-card">
                  <h3>Campaign system</h3>
                  <p><strong>{data.campaign_system_label}</strong></p>
                  <p className="meta">Some workflows below stay narrower when the campaign is not using DND-5E.</p>
                </article>
                <article className="help-detail-card">
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
                  <div className="article-actions">
                    {surface.links.map((link, index) => (
                      <a className={index === 0 ? "button" : "button button-secondary"} href={link.href} key={`${surface.anchor}-${link.href}`}>
                        {link.label}
                      </a>
                    ))}
                  </div>
                ) : null}

                <div className="help-detail-grid">
                  <article className="help-detail-card">
                    <h3>Use it for</h3>
                    <HelpList items={surface.capabilities} emptyText="No capabilities are listed for this surface." />
                  </article>
                  <article className="help-detail-card">
                    <h3>Current limits</h3>
                    <HelpList items={surface.limits} emptyText="No limits are listed for this surface." />
                  </article>
                  <article className="help-detail-card">
                    <h3>Access</h3>
                    <p><strong>{surface.status_label}</strong></p>
                    <p className="meta">{surface.access_note}</p>
                  </article>
                </div>

                {surface.guidance_cards.length ? (
                  <div className="help-detail-grid">
                    {surface.guidance_cards.map((card) => (
                      <article className="help-detail-card" key={`${surface.anchor}-${card.title}`}>
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

          <aside className="sidebar campaign-help-sidebar">
            <article className="card sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Visibility by scope</h2>
                  <p className="meta">The effective visibility here is the current floor after campaign-level and scope-level rules combine.</p>
                </div>
              </div>
              <div className="reference-stack">
                {data.visibility_rows.map((row) => (
                  <article className="help-detail-card" key={row.label}>
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

            <article className="card sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Cross-cutting limits</h2>
                  <p className="meta">These are the app-level constraints most likely to affect multiple surfaces.</p>
                </div>
              </div>
              <HelpList items={data.cross_cutting_limits} emptyText="No cross-cutting limits are visible for this viewer." />
            </article>

            <article className="card sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Account settings</h2>
                  <p className="meta">{data.account_note}</p>
                </div>
              </div>
              <div className="article-actions">
                {data.is_authenticated ? (
                  <a className="button" href={data.links.account_url}>Open Account</a>
                ) : (
                  <a className="button" href={data.links.sign_in_url}>Sign in</a>
                )}
                <a className="button button-secondary" href={data.links.flask_help_url}>Flask Help</a>
              </div>
            </article>
          </aside>
        </div>
      ) : null}
    </section>
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
}: {
  page: WikiPageSummary;
  featured?: boolean;
}) {
  return (
    <article className={featured ? "card page-card page-card--featured" : "card page-card"}>
      <p className="card-kicker">
        {page.subsection ? `${page.subsection} / ` : ""}
        {page.display_type}
      </p>
      <h3>
        <a href={page.href}>{page.title}</a>
      </h3>
      {page.summary ? <p className={featured ? "page-card__summary" : ""}>{page.summary}</p> : null}
    </article>
  );
}

function WikiPageGrid({
  pages,
  featured = false,
}: {
  pages: WikiPageSummary[];
  featured?: boolean;
}) {
  if (!pages.length) {
    return null;
  }
  return (
    <div className={featured ? "page-stack page-stack--featured" : "grid"}>
      {pages.map((page) => (
        <WikiPageCard key={page.page_ref} page={page} featured={featured} />
      ))}
    </div>
  );
}

function WikiSectionBrowse({
  data,
}: {
  data: WikiHomeResponse;
}) {
  if (!data.grouped_sections.length) {
    return null;
  }
  return (
    <section className="wiki-section-browse">
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
            section.pages.map((page) => <WikiPageCard key={page.page_ref} page={page} />)
          ) : (
            <article className="card page-card section-card" key={section.section_slug}>
              <p className="card-kicker">Section</p>
              <h3>
                <a href={section.href}>{section.section_name}</a>
              </h3>
              <p>
                {section.page_count} page{section.page_count === 1 ? "" : "s"} available in this section.
              </p>
              <p>
                <a href={section.href}>Open {section.section_name}</a>
              </p>
            </article>
          ),
        )}
      </div>
    </section>
  );
}

function WikiHomePage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
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

  return (
    <section className="panel wiki-home">
      <div className="panel-header">
        <div>
          <p className="meta">Campaign</p>
          <h1>Campaign Home</h1>
        </div>
        {data?.links.flask_campaign_url ? (
          <a className="button button-secondary" href={data.links.flask_campaign_url}>
            Flask view
          </a>
        ) : null}
      </div>
      <ApiErrorNotice isLoading={wikiQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <>
          <p className="lede">{data.campaign.summary}</p>
          {!data.can_view_wiki ? (
            <section className="card">
              <h2>Wiki visibility restricted</h2>
              <p>{data.message}</p>
            </section>
          ) : data.grouped_sections.length ? (
            <>
              {!data.query && data.overview_page ? (
                <article className="article card wiki-overview-card">
                  <p className="eyebrow">{data.overview_page.display_type} in {data.overview_page.section}</p>
                  <h2>
                    <a href={data.overview_page.href}>{data.overview_page.title}</a>
                  </h2>
                  {data.overview_page.summary ? <p className="lede">{data.overview_page.summary}</p> : null}
                  <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: data.overview_page.body_html }} />
                </article>
              ) : null}
              <WikiSectionBrowse data={data} />
            </>
          ) : (
            <section className="card">
              {data.query ? (
                <>
                  <h2>No matching pages</h2>
                  <p>Try a broader search term or remove the query.</p>
                </>
              ) : (
                <>
                  <h2>No visible pages yet</h2>
                  <p>This campaign does not currently have any published pages available to players.</p>
                </>
              )}
            </section>
          )}
        </>
      ) : null}
    </section>
  );
}

function WikiSectionPage() {
  const { campaignSlug, sectionSlug } = useParams({
    from: "/campaigns/$campaignSlug/sections/$sectionSlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSectionSlug = sectionSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
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
    <section className="panel wiki-section-page">
      <div className="panel-header">
        <div>
          <p className="meta">Section</p>
          <h1>{data?.section_name ?? resolvedSectionSlug}</h1>
          <p className="lede">Published player-facing pages in this section.</p>
        </div>
        <div className="article-actions">
          <a className="button button-secondary" href={`/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}`}>
            Campaign Home
          </a>
          {data?.links.flask_section_url ? (
            <a className="button button-secondary" href={data.links.flask_section_url}>
              Flask view
            </a>
          ) : null}
        </div>
      </div>
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
            <WikiPageGrid pages={topLevel.pinned} featured />
            <WikiPageGrid pages={topLevel.regular} />
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
                      <WikiPageGrid pages={split.pinned} featured />
                      <WikiPageGrid pages={split.regular} />
                    </div>
                  </details>
                );
              })}
            </section>
          </>
        ) : (
          <>
            <WikiPageGrid pages={allPages.pinned} featured />
            <WikiPageGrid pages={allPages.regular} />
          </>
        )
      ) : null}
    </section>
  );
}

function WikiArticlePage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/pages/$",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const pageSlug = params._splat ?? "";
  const { apiClient, setAuthRequired } = useApiClient();

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
  const showSummary = page?.summary && !["item", "spell", "mechanic"].includes(page.page_type);

  return (
    <section className="wiki-article-shell">
      <ApiErrorNotice isLoading={pageQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {page ? (
        <div className="page-layout">
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
                Campaign: <a href={data?.links.gen2_campaign_url}>{data?.campaign.title}</a>
              </p>
              <p className="meta">
                Section: <a href={data?.links.gen2_section_url}>{page.section}</a>
              </p>
              {data?.links.flask_page_url ? (
                <p className="meta">
                  Fallback: <a href={data.links.flask_page_url}>Open Flask page</a>
                </p>
              ) : null}
            </section>
            {data?.backlinks.length ? (
              <section className="card sidebar-card">
                <h2>Linked From</h2>
                <ul className="plain-list">
                  {data.backlinks.map((backlink) => (
                    <li key={backlink.page_ref}>
                      <a href={backlink.href}>{backlink.title}</a>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}
    </section>
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
    <a className="button button-secondary" href={`/app-next/campaigns/${encodeURIComponent(campaignSlug)}/dm-content?lane=systems`}>
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
        <li key={entry.entry_key}>
          <a href={systemsEntryHref(campaignSlug, entry.slug)}>{entry.title}</a>
          {showMeta ? (
            <span className="meta">
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
        <li key={`${entry.source_id}-${entry.slug}`}>
          <a href={systemsEntryHref(campaignSlug, entry.slug)}>{entry.title}</a>
          <span className="meta">
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
        <li key={group.entry_type}>
          <a href={systemsSourceCategoryHref(campaignSlug, sourceId, group.entry_type)}>
            {group.entry_type_label}
          </a>
          <span className="meta">
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
    <section className="panel systems-browse-page">
      <div className="panel-header">
        <div>
          <p className="meta">Systems wiki</p>
          <h1>Systems</h1>
          <p className="lede">Browse campaign-approved system sources and reference entries.</p>
        </div>
        <div className="article-actions">
          <a className="button button-secondary" href={`/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/systems`}>
            Flask view
          </a>
          <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage={Boolean(data?.permissions.can_manage_systems)} />
        </div>
      </div>
      <ApiErrorNotice isLoading={systemsQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="page-layout">
          <section className="article card">
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
          <aside className="sidebar">
            <section className="card sidebar-card">
              <h2>Available Sources</h2>
              {data.sources.length ? (
                <ul className="plain-list systems-entry-list">
                  {data.sources.map((source) => (
                    <li key={source.source_id}>
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
    </section>
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
    <section className="panel systems-browse-page">
      <div className="panel-header">
        <div>
          <p className="meta">Systems source</p>
          <h1>{data?.source.title ?? resolvedSourceId}</h1>
          {data ? <p className="lede">{data.source.source_id} | {data.source.license_class_label} | {data.source.default_visibility} visibility</p> : null}
        </div>
        <div className="article-actions">
          <a className="button button-secondary" href={systemsIndexHref(resolvedCampaignSlug)}>Systems</a>
          <a className="button button-secondary" href={`/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/systems/sources/${encodeURIComponent(resolvedSourceId)}`}>
            Flask view
          </a>
          <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage={Boolean(data?.permissions.can_manage_systems)} />
        </div>
      </div>
      <ApiErrorNotice isLoading={sourceQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="page-layout">
          <section className="article card">
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
          <aside className="sidebar">
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
    </section>
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
    <section className="panel systems-browse-page">
      <div className="panel-header">
        <div>
          <p className="meta">Systems source category</p>
          <h1>{data ? `${data.source.title}: ${data.entry_type_label}` : resolvedEntryType}</h1>
          {data ? <p className="lede">{data.source.source_id} | {data.source.license_class_label} | {data.source.default_visibility} visibility</p> : null}
        </div>
        <div className="article-actions">
          <a className="button button-secondary" href={systemsSourceHref(resolvedCampaignSlug, resolvedSourceId)}>Source</a>
          <a
            className="button button-secondary"
            href={`/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/systems/sources/${encodeURIComponent(resolvedSourceId)}/types/${encodeURIComponent(resolvedEntryType)}`}
          >
            Flask view
          </a>
          <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage={Boolean(data?.permissions.can_manage_systems)} />
        </div>
      </div>
      <ApiErrorNotice isLoading={categoryQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="page-layout">
          <section className="article card">
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
          <aside className="sidebar">
            <section className="card sidebar-card">
              <h2>Category Details</h2>
              <p className="meta">Source ID: {data.source.source_id}</p>
              <p className="meta">Category: {data.entry_type_label}</p>
              <p className="meta">Available entries: {data.entry_count}</p>
            </section>
          </aside>
        </div>
      ) : null}
    </section>
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
    <section className="systems-entry-shell">
      <ApiErrorNotice isLoading={entryQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {entry ? (
        <div className="page-layout">
          <article className="article card">
            <p className="eyebrow">Systems entry</p>
            <h1>{entry.title}</h1>
            <p className="lede">
              {entry.entry_type_label} | {entry.source_id}
              {sourceState?.license_class_label ? ` | ${sourceState.license_class_label}` : ""}
            </p>
            {entry.rendered_html ? (
              <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: entry.rendered_html }} />
            ) : (
              <>
                <p className="meta">This entry has been imported into the systems library, but it does not have rendered content yet.</p>
                <p className="meta">Entry key: {entry.entry_key}</p>
              </>
            )}
          </article>
          <aside className="sidebar">
            <section className="card sidebar-card">
              <h2>Entry Metadata</h2>
              <p className="meta">Type: {entry.entry_type_label}</p>
              <p className="meta">Source: {entry.source_id}</p>
              <p className="meta">Entry key: {entry.entry_key}</p>
              {entry.source_page ? <p className="meta">Source page: {entry.source_page}</p> : null}
            </section>
            <section className="card sidebar-card">
              <h2>Navigation</h2>
              <ul className="plain-list">
                <li><a href={systemsIndexHref(resolvedCampaignSlug)}>Systems landing</a></li>
                <li><a href={systemsSourceHref(resolvedCampaignSlug, entry.source_id)}>Source page</a></li>
                <li><a href={systemsSourceCategoryHref(resolvedCampaignSlug, entry.source_id, entry.entry_type)}>Source category</a></li>
                {data?.links.flask_entry_url ? <li><a href={data.links.flask_entry_url}>Open Flask entry</a></li> : null}
              </ul>
            </section>
            {data?.permissions.can_manage_systems ? (
              <section className="card sidebar-card">
                <h2>Entry Management</h2>
                {data.links.dm_content_systems_url ? (
                  <a className="button button-secondary" href={data.links.dm_content_systems_url}>Manage campaign override</a>
                ) : (
                  <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
                )}
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}
    </section>
  );
}

function SessionArticlesPanel({
  campaignSlug,
  articles,
  title,
  emptyText,
}: {
  campaignSlug: string;
  articles: SessionArticle[];
  title: string;
  emptyText: string;
}) {
  return (
    <article className="panel panel-nested">
      <div className="panel-header">
        <h3>{title}</h3>
        <span className="pill">{articles.length} article(s)</span>
      </div>
      {articles.length ? (
        <div className="article-stack">
          {articles.map((article) => (
            <details className="article-card" key={article.id}>
              <summary>
                <strong>{article.title}</strong>
                <span className="article-kind">{article.source_kind || "unclassified"}</span>
              </summary>
              <div className="article-meta">
                {article.image ? (
                  <img
                    className="article-image"
                    src={resolveArticleImage(campaignSlug, article)}
                    alt={article.image.alt_text || "Session article image"}
                  />
                ) : null}
                {article.created_at ? <time>{formatTimestamp(article.created_at)}</time> : null}
              </div>
              <SessionArticleSourceLine article={article} />
              {renderArticleBody(article)}
              <div className="article-actions">
                <SessionArticleReferenceActions article={article} includePromotionLinks={false} />
              </div>
            </details>
          ))}
        </div>
      ) : (
        <p className="status status-neutral">{emptyText}</p>
      )}
    </article>
  );
}

function SessionPaneChat({
  payload,
  messageDraft,
  setMessageDraft,
  sendError,
  onSend,
  isSending,
}: {
  payload: SessionPayload | undefined;
  messageDraft: string;
  setMessageDraft: (value: string) => void;
  sendError: string | null;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  isSending: boolean;
}) {
  const messages: SessionMessage[] = payload?.messages ?? [];

  return (
    <article className="panel panel-nested">
      <div className="panel-header">
        <h3>Session chat</h3>
        <span className="pill">{payload?.active_session ? `Session #${payload.active_session.id}` : "No active session"}</span>
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
      {payload?.permissions.can_post_messages ? (
        <form onSubmit={onSend} className="chat-composer">
          <label htmlFor="session-message-body" className="chat-label">
            Post Session Message
          </label>
          <textarea
            id="session-message-body"
            rows={5}
            value={messageDraft}
            placeholder="Type chat text"
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setMessageDraft(event.currentTarget.value);
            }}
          />
          <div className="chat-actions">
            <button type="submit" disabled={isSending || payload?.active_session === null}>
              {isSending ? "Sending..." : "Send"}
            </button>
            <span>{payload?.permissions.can_manage_session ? "DM view" : "Player view"}</span>
          </div>
          {sendError ? <p className="status status-error">{sendError}</p> : null}
        </form>
      ) : (
        <p className="status status-neutral">You do not have permission to post messages.</p>
      )}
    </article>
  );
}

function SessionPaneWikiLookup({
  canShow,
  query,
  setQuery,
  queryStatus,
  results,
  onSearch,
  previewRef,
  onSelectPreview,
  previewLoading,
  previewHtml,
  previewError,
  clearStatus,
}: {
  canShow: boolean;
  query: string;
  setQuery: (value: string) => void;
  queryStatus: string | null;
  results: SessionWikiLookupSearchResult[];
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
  previewRef: string | null;
  onSelectPreview: (pageRef: string) => void;
  previewLoading: boolean;
  previewHtml: string;
  previewError: string | null;
  clearStatus: () => void;
}) {
  if (!canShow) {
    return <p className="status status-neutral">This campaign does not expose wiki lookup.</p>;
  }

  return (
    <article className="panel panel-nested">
      <h3>Player wiki lookup</h3>
      <form onSubmit={onSearch} className="wiki-search">
        <label htmlFor="wiki-search-query" className="chat-label">
          Search published pages / systems
        </label>
        <div className="search-row">
          <input
            id="wiki-search-query"
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setQuery(event.currentTarget.value);
              clearStatus();
            }}
            placeholder="harbor, rules, artifact"
          />
          <button type="submit">Search</button>
        </div>
      </form>
      {queryStatus ? <p className="status status-neutral">{queryStatus}</p> : null}
      {results.length ? (
        <div className="wiki-result-stack">
          {results.map((result) => {
            const pageRef = result.page_ref || result.source_ref || "";
            return (
              <button
                className="wiki-result-row"
                type="button"
                key={pageRef}
                onClick={() => onSelectPreview(pageRef)}
                disabled={!pageRef}
              >
                <strong>{result.title}</strong>
                <p>{result.subtitle}</p>
              </button>
            );
          })}
        </div>
      ) : null}
      {previewRef ? (
        <div className="wiki-preview">
          <div className="preview-title">Preview: {previewRef}</div>
          {previewLoading ? <p className="status status-neutral">Loading preview ...</p> : null}
          {previewError ? <p className="status status-error">{previewError}</p> : null}
          {previewHtml ? <div className="wiki-preview-html" dangerouslySetInnerHTML={{ __html: previewHtml }} /> : null}
        </div>
      ) : null}
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
  manualDraft: { title: string; body: string };
  setManualDraft: (state: { title: string; body: string }) => void;
  uploadDraft: { filename: string; markdown: string; image: EmbeddedImageInput | null };
  setUploadDraft: (state: { filename: string; markdown: string; image: EmbeddedImageInput | null }) => void;
  onSearchSources: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCreate: (payload: SessionArticleCreatePayload) => void;
  isCreating: boolean;
}) {
  const instructions =
    mode === "manual"
      ? "Use title and markdown body and create an unrevealed article."
      : mode === "upload"
        ? "Upload mode needs a filename and markdown body."
        : "Search and select a source, then pull into staged articles.";

  return (
    <article className="panel panel-nested">
      <h3>Stage an article</h3>
      <div className="segmented">
        <button
          type="button"
          className={mode === "manual" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("manual")}
        >
          Manual
        </button>
        <button
          type="button"
          className={mode === "upload" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("upload")}
        >
          Upload
        </button>
        <button
          type="button"
          className={mode === "wiki" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("wiki")}
        >
          Wiki / Systems
        </button>
      </div>
      <p className="status status-neutral">{instructions}</p>

      {mode === "manual" ? (
        <section className="session-form">
          <label htmlFor="dm-manual-title" className="chat-label">Title</label>
          <input
            id="dm-manual-title"
            value={manualDraft.title}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setManualDraft({ ...manualDraft, title: event.currentTarget.value });
            }}
          />
          <label htmlFor="dm-manual-body" className="chat-label">Markdown body</label>
          <textarea
            id="dm-manual-body"
            rows={8}
            value={manualDraft.body}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setManualDraft({ ...manualDraft, body: event.currentTarget.value });
            }}
          />
          <button
            type="button"
            className="button"
            disabled={isCreating || !manualDraft.title.trim() || !manualDraft.body.trim()}
            onClick={() =>
              onCreate({
                mode: "manual",
                title: manualDraft.title.trim(),
                body_markdown: manualDraft.body,
              } satisfies SessionArticleCreatePayloadManual)
            }
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </section>
      ) : null}

      {mode === "upload" ? (
        <section className="session-form">
          <label htmlFor="dm-upload-filename" className="chat-label">Source filename</label>
          <input
            id="dm-upload-filename"
            value={uploadDraft.filename}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setUploadDraft({ ...uploadDraft, filename: event.currentTarget.value });
            }}
            placeholder="notes.md"
          />
          <label htmlFor="dm-upload-markdown" className="chat-label">Markdown text</label>
          <textarea
            id="dm-upload-markdown"
            rows={8}
            value={uploadDraft.markdown}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setUploadDraft({ ...uploadDraft, markdown: event.currentTarget.value });
            }}
          />
          <label className="chat-label">Referenced image (optional)</label>
          <input
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
        </section>
      ) : null}

      {mode === "wiki" ? (
        <section className="session-form">
          <form onSubmit={onSearchSources} className="wiki-search">
            <label htmlFor="dm-wiki-search" className="chat-label">Search wiki / systems</label>
            <div className="search-row">
              <input
                id="dm-wiki-search"
                value={sourceQuery}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setSourceQuery(event.currentTarget.value);
                  setSourceStatus(null);
                  setSelectedSourceRef("");
                }}
              />
              <button type="submit">Search</button>
            </div>
          </form>
          {sourceStatus ? <p className="status status-neutral">{sourceStatus}</p> : null}
          {sourceResults.length ? (
            <div className="wiki-result-stack">
              {sourceResults.map((result) => (
                <button
                  key={result.source_ref}
                  type="button"
                  className="wiki-result-row"
                  onClick={() => setSelectedSourceRef(result.source_ref)}
                >
                  <strong>{result.title}</strong>
                  <p>{result.subtitle}</p>
                </button>
              ))}
            </div>
          ) : null}
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
        </section>
      ) : null}
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

  const [wikiQuery, setWikiQuery] = useState("");
  const [wikiStatus, setWikiStatus] = useState<string | null>(null);
  const [wikiResults, setWikiResults] = useState<SessionWikiLookupSearchResult[]>([]);
  const [wikiPreviewRef, setWikiPreviewRef] = useState<string | null>(null);
  const [wikiPreviewLoading, setWikiPreviewLoading] = useState(false);
  const [wikiPreviewHtml, setWikiPreviewHtml] = useState("");
  const [wikiPreviewError, setWikiPreviewError] = useState<string | null>(null);

  const postMessage = useMutation({
    mutationFn: (body: string) => apiClient.postSessionMessage(campaignSlug, body),
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

  const doSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = wikiQuery.trim();
    if (!query) {
      setWikiStatus("Enter a search query first.");
      return;
    }
    setWikiStatus("Searching ...");
    try {
      const result = await apiClient.searchPlayerSessionWiki(campaignSlug, query);
      setWikiResults(result.results);
      setWikiStatus(result.message || "Search complete.");
      if (!result.results.length) {
        setWikiPreviewRef(null);
        setWikiPreviewHtml("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setWikiResults([]);
      setWikiStatus(null);
      setWikiPreviewError(apiErrorMessage(error));
    }
  };

  const doPreview = async (pageRef: string) => {
    setWikiPreviewRef(pageRef);
    setWikiPreviewLoading(true);
    setWikiPreviewError(null);
    try {
      const response: SessionWikiLookupPreviewResponse = await apiClient.previewPlayerSessionWiki(campaignSlug, pageRef);
      setWikiPreviewHtml(response.preview_html || "");
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setWikiPreviewHtml("");
      setWikiPreviewError(apiErrorMessage(error));
    } finally {
      setWikiPreviewLoading(false);
    }
  };

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
    postMessage.mutate(body);
  };

  const canShowWikiLookup = payload?.permissions.can_access_wiki_lookup ?? true;

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>Session: {payload?.campaign.title ?? campaignSlug}</h2>
          <span className="pill">Player</span>
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
      </section>

      <div className="split-grid">
        <SessionArticlesPanel
          campaignSlug={campaignSlug}
          articles={payload?.revealed_articles ?? []}
          title="Revealed articles"
          emptyText="No revealed articles yet."
        />
        <SessionPaneWikiLookup
          canShow={canShowWikiLookup}
          query={wikiQuery}
          setQuery={setWikiQuery}
          queryStatus={wikiStatus}
          results={wikiResults}
          onSearch={doSearch}
          previewRef={wikiPreviewRef}
          onSelectPreview={doPreview}
          previewLoading={wikiPreviewLoading}
          previewHtml={wikiPreviewHtml}
          previewError={wikiPreviewError}
          clearStatus={() => {
            setWikiPreviewError(null);
            setWikiStatus(null);
          }}
        />
      </div>
      <SessionPaneChat
        payload={payload}
        messageDraft={messageDraft}
        setMessageDraft={setMessageDraft}
        sendError={sendError}
        onSend={sendMessage}
        isSending={postMessage.isPending}
      />
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
  const detailProgressionRepairLabel = detailLinks.progression_repair_url ? "Progression repair" : "Flask repair";
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
  const profile = asRecord(definition.profile);
  const stats = asRecord(definition.stats);
  const spellcasting = asRecord(definition.spellcasting);
  const state = asRecord(detailRecord?.state_record.state);
  const xianxiaState = asRecord(state.xianxia);
  const vitals = asRecord(state.vitals);
  const resources = asRecordArray(state.resources);
  const spellSlots = asRecordArray(state.spell_slots);
  const inventory = asRecordArray(state.inventory);
  const currency = isXianxia ? asRecord(xianxiaState.currency) : asRecord(state.currency);
  const notes = asRecord(state.notes);
  const abilityScores = asRecord(stats.ability_scores);
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

  const submitEquipmentState = (event: FormEvent<HTMLFormElement>, item: CharacterEquipmentRow) => {
    event.preventDefault();
    const draft = equipmentDrafts[item.id] ?? {
      isEquipped: Boolean(item.is_equipped),
      isAttuned: Boolean(item.is_attuned),
      weaponWieldMode: item.weapon_wield_mode || "",
    };
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

  const submitArcaneArmorState = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
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
        enabled: arcaneArmorDraft,
      },
    });
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

  const openXianxiaRecordDetail = (record: CharacterXianxiaNamedRecord, eyebrow: string) => {
    setDetailDialog({
      eyebrow,
      title: record.name || "Xianxia record",
      html: readString(record.body_html, readString(record.description_html)),
      notes: joinDisplay([record.notes, record.prepared_record_notes, record.use_notes]),
      href: readString(record.href),
      facts: [
        { label: "Rank", value: readString(record.current_rank_label) },
        { label: "Status", value: readString(record.status_label, readString(record.status)) },
        { label: "Type", value: readString(record.type_label, readString(record.type)) },
        { label: "Source", value: readString(record.source_label) },
        { label: "Prepared", value: readString(record.prepared_record_name) },
        { label: "Approval timestamp", value: readString(record.approval_timestamp) },
        { label: "Insight cost", value: record.insight_cost ? String(record.insight_cost) : "" },
        { label: "Insight spent", value: record.insight_spent ? String(record.insight_spent) : "" },
        { label: "One-use status", value: readString(record.one_use_status_label, readString(record.one_use_status)) },
        { label: "Base ability ref", value: readString(record.base_ability_ref) },
        { label: "Base ability kind", value: readString(record.base_ability_kind) },
        { label: "Technique anchor", value: readString(record.technique_anchor_label) },
      ].filter((fact) => fact.value),
    });
  };

  const renderXianxiaRecordCard = (record: CharacterXianxiaNamedRecord, eyebrow: string) => (
    <article className="character-state-card" key={draftKey(eyebrow, record.name, record.href)}>
      <p className="meta">
        {joinDisplay([
          record.current_rank_label,
          record.status_label || record.status,
          record.type_label || record.type,
          record.source_label,
        ]) || eyebrow}
      </p>
      <h4>{record.name || "Unnamed record"}</h4>
      {record.reason ? <p className="meta">{record.reason}</p> : null}
      {record.rank_progress_label ? <p className="meta">{record.rank_progress_label}</p> : null}
      {record.body_html || record.description_html || record.notes || record.href || record.prepared_record_notes || record.use_notes ? (
        <button type="button" className="button button-secondary detail-button" onClick={() => openXianxiaRecordDetail(record, eyebrow)}>
          Details
        </button>
      ) : null}
    </article>
  );

  const renderXianxiaApprovalRecordCard = (
    record: CharacterXianxiaNamedRecord,
    groupTitle: string,
    groupKey: string,
  ) => {
    const isDaoUseRecord = groupKey === "dao_immolating_use_records";
    const useRecordDraftKey = xianxiaDaoUseRecordDraftKey(record);
    const insightCost = record.insight_cost ?? (isDaoUseRecord ? 10 : 0);
    const insightAvailable = xianxiaInsight?.available ?? 0;
    const canRecordThisDaoUse =
      isDaoUseRecord &&
      canRecordXianxiaDaoUse &&
      record.status_key === "approved" &&
      !record.used &&
      record.use_record_index !== undefined;
    const spendDisabled = insightCost > 0 && insightAvailable < insightCost;

    return (
      <article className="character-state-card" key={draftKey(groupKey, record.name, record.use_record_index, record.approval_timestamp)}>
        <p className="meta">
          {joinDisplay([
            record.status_label || record.status,
            record.type_label || record.type,
            record.source_label,
            insightCost ? `${insightCost} Insight` : "",
            record.used ? "Used" : record.one_use_status_label,
          ]) || groupTitle}
        </p>
        <h4>{record.name || "Unnamed record"}</h4>
        {record.notes ? <p>{record.notes}</p> : null}
        {record.prepared_record_name ? <p className="meta">Prepared note: {record.prepared_record_name}</p> : null}
        {record.approval_timestamp ? <p className="meta">Approval timestamp: {record.approval_timestamp}</p> : null}
        {record.use_notes ? <p className="meta">Use notes: {record.use_notes}</p> : null}
        {record.technique_anchor_warning ? <p className="status status-error">{record.technique_anchor_warning}</p> : null}
        {record.body_html ||
        record.description_html ||
        record.notes ||
        record.href ||
        record.prepared_record_notes ||
        record.use_notes ||
        record.technique_anchor_warning ? (
          <button type="button" className="button button-secondary detail-button" onClick={() => openXianxiaRecordDetail(record, groupTitle)}>
            Details
          </button>
        ) : null}
        {canRecordThisDaoUse ? (
          <form onSubmit={(event) => submitXianxiaDaoUseRecord(event, record)} className="inline-two-col">
            <label htmlFor={`xianxia-dao-use-notes-${useRecordDraftKey}`} className="chat-label">
              Use notes
            </label>
            <textarea
              id={`xianxia-dao-use-notes-${useRecordDraftKey}`}
              rows={2}
              value={xianxiaDaoUseNotesDrafts[useRecordDraftKey] ?? ""}
              onChange={(event) =>
                setXianxiaDaoUseNotesDrafts({
                  ...xianxiaDaoUseNotesDrafts,
                  [useRecordDraftKey]: event.currentTarget.value,
                })
              }
            />
            <div />
            <button type="submit" disabled={postXianxiaDaoUseRecord.isPending || spendDisabled}>
              {postXianxiaDaoUseRecord.isPending ? "Saving..." : "Record one-use spend"}
            </button>
            {spendDisabled ? <p className="status status-error">Needs {insightCost} Insight.</p> : null}
          </form>
        ) : null}
      </article>
    );
  };

  const renderXianxiaPoolCards = (pools: Array<{ key: string; label: string; current: number; max: number; temp?: number }>) => (
    <div className="character-card-grid">
      {pools.map((pool) => (
        <article className="character-state-card" key={pool.key}>
          <h4>{pool.label}</h4>
          <p>
            {pool.current} / {pool.max}
            {pool.temp !== undefined ? ` +${pool.temp} temp` : ""}
          </p>
        </article>
      ))}
    </div>
  );

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

  return (
    <div className={isReadSurface ? "session-pane-content character-read-content character-layout" : "session-pane-content"}>
      <section className={isReadSurface ? "panel character-read-shell" : "panel"}>
        <div className={isReadSurface ? "panel-header character-read-shell__header" : "panel-header"}>
          <div>
            <p className="meta">{surfaceMetaLabel}</p>
            <h2>{surfaceHeading}</h2>
          </div>
          <div className={isReadSurface ? "article-actions character-read-shell__actions" : "article-actions"}>
            {isReadSurface ? (
              <a href={`/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters`} className="button button-secondary">
                Roster
              </a>
            ) : isCombatSurface ? (
              <a href={`/campaigns/${encodeURIComponent(campaignSlug)}/combat`} className="button button-secondary">
                Flask Combat
              </a>
            ) : (
              <a
                href={
                  selectedSlug
                    ? `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(selectedSlug)}`
                    : `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters`
                }
                className="button button-secondary"
              >
                Character route
              </a>
            )}
          </div>
        </div>

        <div className={isReadSurface ? "character-selector-card" : undefined}>
          <label className="chat-label" htmlFor="character-selector">
            Character
          </label>
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
            {isReadSurface && detailRecord ? (
              <div className="button-row character-action-row">
                {detailLinks.flask_character_url ? (
                  <a className="button button-secondary" href={detailLinks.flask_character_url}>
                    Flask sheet
                  </a>
                ) : null}
                {detailLinks.advanced_editor_url ? (
                  <a className="button button-secondary" href={detailLinks.advanced_editor_url}>
                    Advanced Editor
                  </a>
                ) : null}
                {detailLinks.flask_advanced_editor_url ? (
                  <a className="button button-secondary" href={detailLinks.flask_advanced_editor_url}>
                    Flask editor
                  </a>
                ) : null}
                {detailLinks.level_up_url ? (
                  <a className="button button-secondary" href={detailLinks.level_up_url}>
                    Level Up
                  </a>
                ) : null}
                {detailLinks.flask_level_up_url ? (
                  <a className="button button-secondary" href={detailLinks.flask_level_up_url}>
                    Flask level-up
                  </a>
                ) : null}
                {detailLinks.retraining_url ? (
                  <a className="button button-secondary" href={detailLinks.retraining_url}>
                    Retraining
                  </a>
                ) : null}
                {detailLinks.flask_retraining_url ? (
                  <a className="button button-secondary" href={detailLinks.flask_retraining_url}>
                    Flask retraining
                  </a>
                ) : null}
                {detailProgressionRepairUrl ? (
                  <a className="button button-secondary" href={detailProgressionRepairUrl}>
                    {detailProgressionRepairLabel}
                  </a>
                ) : null}
                {detailLinks.cultivation_url ? (
                  <a className="button button-secondary" href={detailLinks.cultivation_url}>
                    Cultivation
                  </a>
                ) : null}
                {detailLinks.flask_cultivation_url ? (
                  <a className="button button-secondary" href={detailLinks.flask_cultivation_url}>
                    Flask Cultivation
                  </a>
                ) : null}
                {!detailProgressionRepairUrl ? (
                  <span className="meta">Progression repair appears when an imported DND-5E sheet needs it.</span>
                ) : null}
              </div>
            ) : null}
            {canManagePortrait ? (
              <form className="character-portrait-manager" onSubmit={submitPortrait}>
                <div className="character-portrait-manager__fields">
                  <label htmlFor="character-portrait-file">
                    Portrait image
                    <input
                      id="character-portrait-file"
                      ref={portraitFileInputRef}
                      type="file"
                      accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
                      disabled={portraitMutationPending}
                      onChange={handlePortraitFileChange}
                    />
                  </label>
                  <label htmlFor="character-portrait-alt">
                    Alt text
                    <input
                      id="character-portrait-alt"
                      type="text"
                      maxLength={200}
                      value={portraitDraft.altText}
                      disabled={portraitMutationPending}
                      onChange={(event) => setPortraitDraft((current) => ({ ...current, altText: event.currentTarget.value }))}
                    />
                  </label>
                  <label htmlFor="character-portrait-caption">
                    Caption
                    <input
                      id="character-portrait-caption"
                      type="text"
                      maxLength={300}
                      value={portraitDraft.caption}
                      disabled={portraitMutationPending}
                      onChange={(event) => setPortraitDraft((current) => ({ ...current, caption: event.currentTarget.value }))}
                    />
                  </label>
                </div>
                <div className="button-row character-portrait-manager__actions">
                  <button className="button" type="submit" disabled={portraitMutationPending || !portraitDraft.file}>
                    Save portrait
                  </button>
                  {selectedPortrait ? (
                    <button
                      type="button"
                      className="button button-secondary"
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
            <section className="session-character-form">
              <div className="panel-header compact-header">
                <h3>Vitals</h3>
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-secondary"
                    disabled={previewRest.isPending || !canEdit}
                    onClick={() => previewRest.mutate("short")}
                  >
                    Short rest
                  </button>
                  <button
                    type="button"
                    className="button button-secondary"
                    disabled={previewRest.isPending || !canEdit}
                    onClick={() => previewRest.mutate("long")}
                  >
                    Long rest
                  </button>
                </div>
              </div>
              {isXianxia ? (
                <form onSubmit={submitXianxiaVitals} className="inline-two-col">
                  {xianxiaVitalsFields.map((field) => (
                    <React.Fragment key={field.key}>
                      <label htmlFor={`xianxia-${field.key}`} className="chat-label">
                        {field.label}
                      </label>
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
                    </React.Fragment>
                  ))}
                  <div />
                  <button type="submit" disabled={patchVitals.isPending || !canEdit}>
                    {patchVitals.isPending ? "Saving..." : "Save Xianxia pools"}
                  </button>
                </form>
              ) : (
                <form onSubmit={submitVitals} className="inline-two-col">
                  <label htmlFor="character-current-hp" className="chat-label">
                    Current HP
                  </label>
                  <input
                    id="character-current-hp"
                    type="number"
                    value={vitalsDraft.currentHp}
                    disabled={!canEdit}
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })
                    }
                  />
                  <label htmlFor="character-temp-hp" className="chat-label">
                    Temp HP
                  </label>
                  <input
                    id="character-temp-hp"
                    type="number"
                    value={vitalsDraft.tempHp}
                    disabled={!canEdit}
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })
                    }
                  />
                  <div />
                  <button type="submit" disabled={patchVitals.isPending || !canEdit}>
                    {patchVitals.isPending ? "Saving..." : "Save vitals"}
                  </button>
                </form>
              )}
              {restPreview ? (
                <div className="rest-preview">
                  <div className="panel-header compact-header">
                    <h4>{restPreview.label}</h4>
                    <button
                      type="button"
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
                  </div>
                  <ul className="plain-list compact-list">
                    {restPreview.changes.map((change) => (
                      <li key={`${change.label}-${change.from_value}-${change.to_value}`}>
                        <strong>{change.label}</strong>: {change.from_value} {"->"} {change.to_value}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>

            {isDnd ? (
              <div className="section-tabs" role="tablist" aria-label="Session character sections">
                {dndVisibleCharacterSections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={activeCharacterSection === section.id ? "active" : ""}
                    onClick={() => selectCharacterSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </div>
            ) : null}
            {isXianxia ? (
              <div className="section-tabs" role="tablist" aria-label="Xianxia session character sections">
                {xianxiaVisibleCharacterSections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={activeCharacterSection === section.id ? "active" : ""}
                    onClick={() => selectCharacterSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </div>
            ) : null}

            {isXianxia && activeCharacterSection === "quick-reference" ? (
              <section className="session-character-form">
                <h3>Quick Reference</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Realm</strong>
                    <span>{String(presentedXianxia.identity?.realm ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Actions per turn</strong>
                    <span>{String(presentedXianxia.identity?.actions_per_turn ?? "--")}</span>
                    {asRecord(presentedXianxia.quick_reference?.actions).formula ? (
                      <p className="meta">{readString(asRecord(presentedXianxia.quick_reference?.actions).formula)}</p>
                    ) : null}
                  </article>
                  <article>
                    <strong>Defense</strong>
                    <span>{String(asRecord(presentedXianxia.quick_reference?.defense).value ?? presentedXianxia.equipment?.defense ?? "--")}</span>
                    {asRecord(presentedXianxia.quick_reference?.defense).formula ? (
                      <p className="meta">Defense = {readString(asRecord(presentedXianxia.quick_reference?.defense).formula)}</p>
                    ) : null}
                  </article>
                  <article>
                    <strong>Honor</strong>
                    <span>{String(presentedXianxia.identity?.honor ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Reputation</strong>
                    <span>{String(presentedXianxia.identity?.reputation ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Insight</strong>
                    <span>
                      {xianxiaInsight ? `${xianxiaInsight.available} available / ${xianxiaInsight.spent} spent` : "--"}
                    </span>
                  </article>
                </div>
                {asRecord(presentedXianxia.quick_reference?.check_formula).summary ? (
                  <article className="character-state-card">
                    <h4>Check formula</h4>
                    <p>{readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary)}</p>
                  </article>
                ) : null}
                {asRecord(presentedXianxia.quick_reference?.difficulty_states).summary ? (
                  <article className="character-state-card">
                    <h4>Difficulty states</h4>
                    <p>{readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary)}</p>
                    <p className="meta">{readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).resolution_note)}</p>
                  </article>
                ) : null}
                {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).length ? (
                  <div className="character-card-grid">
                    {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).map((entry) => (
                      <article className="character-state-card" key={readString(entry.key, readString(entry.label))}>
                        <h4>{readString(entry.label, "Effort")}</h4>
                        <p>{readString(entry.damage, "--")}</p>
                        <p className="meta">Score {String(entry.score ?? "--")}</p>
                      </article>
                    ))}
                  </div>
                ) : null}
                {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).length ? (
                  <div className="character-card-grid">
                    {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).map((reminder) => (
                      <article className="character-state-card" key={readString(reminder.label)}>
                        <h4>{readString(reminder.title, readString(reminder.label))}</h4>
                        <p>{readString(reminder.status_label)}</p>
                        {asStringArray(reminder.reference_lines).length ? (
                          <ul className="plain-list compact-list">
                            {asStringArray(reminder.reference_lines).map((line, index) => (
                              <li key={`${readString(reminder.label)}-${index}`}>{line}</li>
                            ))}
                          </ul>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "martial-arts" ? (
              <section className="session-character-form">
                <h3>Martial Arts</h3>
                {presentedXianxia.martial_arts?.length ? (
                  <div className="character-card-grid">
                    {presentedXianxia.martial_arts.map((record) => renderXianxiaRecordCard(record, "Martial Art"))}
                  </div>
                ) : (
                  <p className="status status-neutral">No martial arts recorded.</p>
                )}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "techniques" ? (
              <section className="session-character-form">
                <h3>Techniques</h3>
                {presentedXianxia.generic_techniques?.length ? (
                  <div className="character-card-grid">
                    {presentedXianxia.generic_techniques.map((record) => renderXianxiaRecordCard(record, "Generic Technique"))}
                  </div>
                ) : (
                  <p className="status status-neutral">No generic techniques recorded.</p>
                )}
                {presentedXianxia.basic_actions?.length ? (
                  <>
                    <h4>Basic actions</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.basic_actions.map((record) => renderXianxiaRecordCard(record, "Basic Action"))}
                    </div>
                  </>
                ) : null}
                {presentedXianxia.approval?.status_groups?.length ? (
                  <>
                    <h4>Approvals</h4>
                    {presentedXianxia.approval.status_groups.map((group) => (
                      <section className="xianxia-approval-group" key={group.key}>
                        <h5>{group.title}</h5>
                        {group.records.length ? (
                          <div className="character-card-grid">
                            {group.records.map((record) =>
                              renderXianxiaApprovalRecordCard(record, group.title, group.key),
                            )}
                          </div>
                        ) : (
                          <p className="meta">{group.empty_message}</p>
                        )}
                      </section>
                    ))}
                  </>
                ) : null}
                {presentedXianxia.approval?.dao_immolating_prepared?.length ? (
                  <>
                    <h4>Prepared Dao Immolating Techniques</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.approval.dao_immolating_prepared.map((record, index) =>
                        renderXianxiaRecordCard(
                          { ...record, source_label: joinDisplay([record.source_label, `Note ${index + 1}`]) },
                          "Prepared Dao Immolating Technique",
                        ),
                      )}
                    </div>
                  </>
                ) : null}
                {canEdit ? (
                  <form onSubmit={submitXianxiaDaoUseRequest} className="inline-two-col">
                    <label htmlFor="xianxia-dao-request-name" className="chat-label">
                      Dao Immolating request
                    </label>
                    <input
                      id="xianxia-dao-request-name"
                      value={xianxiaDaoRequestDraft.requestName}
                      disabled={postXianxiaDaoUseRequest.isPending}
                      onChange={(event) =>
                        setXianxiaDaoRequestDraft({
                          ...xianxiaDaoRequestDraft,
                          requestName: event.currentTarget.value,
                        })
                      }
                    />
                    {presentedXianxia.approval?.dao_immolating_prepared?.length ? (
                      <>
                        <label htmlFor="xianxia-dao-prepared-record" className="chat-label">
                          Prepared note
                        </label>
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
                          <option value="">None</option>
                          {presentedXianxia.approval.dao_immolating_prepared.map((record, index) => (
                            <option key={draftKey(record.name, index)} value={String(index)}>
                              {record.name || `Prepared note ${index + 1}`}
                            </option>
                          ))}
                        </select>
                      </>
                    ) : null}
                    <label htmlFor="xianxia-dao-request-notes" className="chat-label">
                      Request notes
                    </label>
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
                    <div />
                    <button type="submit" disabled={postXianxiaDaoUseRequest.isPending}>
                      {postXianxiaDaoUseRequest.isPending ? "Saving..." : "Record use request"}
                    </button>
                  </form>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "resources" ? (
              <section className="session-character-form">
                <h3>Resources</h3>
                {xianxiaDurability.length ? renderXianxiaPoolCards(xianxiaDurability) : null}
                {xianxiaEnergies.length ? renderXianxiaPoolCards(xianxiaEnergies) : null}
                {xianxiaYinYang.length ? renderXianxiaPoolCards(xianxiaYinYang) : null}
                {xianxiaDao ? (
                  <article className="character-state-card">
                    <h4>Dao</h4>
                    <p>
                      {xianxiaDao.current} / {xianxiaDao.max}
                    </p>
                  </article>
                ) : null}
                <form onSubmit={submitXianxiaActiveState} className="inline-two-col">
                  <label htmlFor="xianxia-active-stance" className="chat-label">
                    Active Stance
                  </label>
                  <input
                    id="xianxia-active-stance"
                    value={xianxiaActiveDraft.activeStanceName}
                    disabled={!canEdit}
                    onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeStanceName: event.currentTarget.value })}
                  />
                  <label htmlFor="xianxia-active-aura" className="chat-label">
                    Active Aura
                  </label>
                  <input
                    id="xianxia-active-aura"
                    value={xianxiaActiveDraft.activeAuraName}
                    disabled={!canEdit}
                    onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeAuraName: event.currentTarget.value })}
                  />
                  <div />
                  <button type="submit" disabled={patchXianxiaActiveState.isPending || !canEdit}>
                    {patchXianxiaActiveState.isPending ? "Saving..." : "Save active state"}
                  </button>
                </form>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "skills" ? (
              <section className="session-character-form">
                <h3>Skills</h3>
                <div className="ability-grid">
                  {presentedXianxia.attributes?.map((attribute) => (
                    <article className="character-state-card" key={attribute.key}>
                      <h4>{attribute.label}</h4>
                      <p>Score {attribute.score}</p>
                    </article>
                  ))}
                  {presentedXianxia.efforts?.map((effort) => (
                    <article className="character-state-card" key={effort.key}>
                      <h4>{effort.label}</h4>
                      <p>Score {effort.score}</p>
                      {effort.damage ? <p className="meta">{effort.damage}</p> : null}
                    </article>
                  ))}
                </div>
                {presentedXianxia.skills?.trained?.length ? (
                  <ul className="plain-list compact-list">
                    {presentedXianxia.skills.trained.map((skill) => (
                      <li key={skill.name}>{skill.name}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="status status-neutral">No trained skills recorded.</p>
                )}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "equipment" ? (
              <section className="session-character-form">
                <h3>Equipment</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Defense</strong>
                    <span>{String(presentedXianxia.equipment?.defense ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Manual armor bonus</strong>
                    <span>{String(presentedXianxia.equipment?.manual_armor_bonus ?? 0)}</span>
                  </article>
                </div>
                {presentedXianxia.equipment?.equipped_items?.length ? (
                  <div className="character-card-grid">
                    {presentedXianxia.equipment.equipped_items.map((item) => (
                      <article className="character-state-card" key={item.id}>
                        <h4>{item.name}</h4>
                        <p className="meta">{joinDisplay([item.item_nature, item.item_type, item.is_equipped ? "Equipped" : ""])}</p>
                        {item.notes ? <p className="meta">{item.notes}</p> : null}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="status status-neutral">No equipped Xianxia weapons, armor, or artifacts.</p>
                )}
                {presentedXianxia.equipment?.necessary_weapons?.length ? (
                  <>
                    <h4>Necessary weapons</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.equipment.necessary_weapons.map((record) => renderXianxiaRecordCard(record, "Necessary Weapon"))}
                    </div>
                  </>
                ) : null}
                {presentedXianxia.equipment?.necessary_tools?.length ? (
                  <>
                    <h4>Necessary tools</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.equipment.necessary_tools.map((record) => renderXianxiaRecordCard(record, "Necessary Tool"))}
                    </div>
                  </>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "inventory" ? (
              <section className="session-character-form">
                <h3>Inventory</h3>
                {xianxiaInventory.length ? (
                  <div className="character-card-grid">
                    {xianxiaInventory.map((item) => {
                      const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
                      return (
                        <article className="character-state-card" key={item.id}>
                          <h4>{item.name}</h4>
                          <p className="meta">{joinDisplay([`Qty ${item.quantity}`, item.item_nature, item.item_type, item.is_equipped ? "Equipped" : ""])}</p>
                          {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                          {item.notes ? <p className="meta">{item.notes}</p> : null}
                          {canEdit ? (
                            <form onSubmit={(event) => submitXianxiaInventoryUpdate(event, item)} className="equipment-state-form">
                              <label className="chat-label" htmlFor={`xianxia-inventory-name-${item.id}`}>
                                Name
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
                              <label className="chat-label" htmlFor={`xianxia-inventory-quantity-${item.id}`}>
                                Quantity
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
                              <label className="chat-label" htmlFor={`xianxia-inventory-nature-${item.id}`}>
                                Nature
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
                              <label className="chat-label" htmlFor={`xianxia-inventory-type-${item.id}`}>
                                Type
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
                              <label className="chat-label" htmlFor={`xianxia-inventory-tags-${item.id}`}>
                                Tags
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
                              <label className="chat-label" htmlFor={`xianxia-inventory-notes-${item.id}`}>
                                Notes
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
                              <button
                                type="button"
                                className="button-danger"
                                disabled={removeXianxiaInventoryItem.isPending}
                                onClick={() => removeXianxiaInventory(item)}
                              >
                                {removeXianxiaInventoryItem.isPending ? "Removing..." : "Remove"}
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No Xianxia inventory items.</p>
                )}
                {canEdit ? (
                  <form onSubmit={submitXianxiaInventoryAdd} className="equipment-state-form">
                    <h4>Add item</h4>
                    <label className="chat-label" htmlFor="xianxia-new-item-name">
                      Name
                      <input
                        id="xianxia-new-item-name"
                        value={newXianxiaInventoryDraft.name}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, name: event.currentTarget.value })}
                      />
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-quantity">
                      Quantity
                      <input
                        id="xianxia-new-item-quantity"
                        type="number"
                        min="0"
                        value={newXianxiaInventoryDraft.quantity}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, quantity: event.currentTarget.value })}
                      />
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-nature">
                      Nature
                      <select
                        id="xianxia-new-item-nature"
                        value={newXianxiaInventoryDraft.itemNature}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemNature: event.currentTarget.value })}
                      >
                        <option value="Mundane">Mundane</option>
                        <option value="Relic">Relic</option>
                      </select>
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-type">
                      Type
                      <select
                        id="xianxia-new-item-type"
                        value={newXianxiaInventoryDraft.itemType}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemType: event.currentTarget.value })}
                      >
                        <option value="Weapon">Weapon</option>
                        <option value="Armor">Armor</option>
                        <option value="Artifact">Artifact</option>
                        <option value="Consumable">Consumable</option>
                        <option value="Miscellaneous">Miscellaneous</option>
                      </select>
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-tags">
                      Tags
                      <input
                        id="xianxia-new-item-tags"
                        value={newXianxiaInventoryDraft.tags}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, tags: event.currentTarget.value })}
                      />
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-notes">
                      Notes
                      <textarea
                        id="xianxia-new-item-notes"
                        rows={3}
                        value={newXianxiaInventoryDraft.notes}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, notes: event.currentTarget.value })}
                      />
                    </label>
                    <label className="toggle-row">
                      <input
                        type="checkbox"
                        checked={newXianxiaInventoryDraft.equippable}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, equippable: event.currentTarget.checked })}
                      />
                      Equippable
                    </label>
                    {newXianxiaInventoryDraft.equippable ? (
                      <label className="toggle-row">
                        <input
                          type="checkbox"
                          checked={newXianxiaInventoryDraft.isEquipped}
                          onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, isEquipped: event.currentTarget.checked })}
                        />
                        Equipped
                      </label>
                    ) : null}
                    <button type="submit" disabled={addXianxiaInventoryItem.isPending}>
                      {addXianxiaInventoryItem.isPending ? "Adding..." : "Add item"}
                    </button>
                  </form>
                ) : null}
                <form onSubmit={submitCurrency} className="currency-grid">
                  {(xianxiaCurrency.length ? xianxiaCurrency : [
                    { key: "coin", label: "Coin", amount: readNumber(currency.coin) },
                    { key: "supply", label: "Supply", amount: readNumber(currency.supply) },
                    { key: "spirit_stones", label: "Spirit Stones", amount: readNumber(currency.spirit_stones) },
                  ]).map((entry) => (
                    <label key={entry.key} className="chat-label" htmlFor={`currency-${entry.key}`}>
                      {entry.label}
                      <input
                        id={`currency-${entry.key}`}
                        type="number"
                        min="0"
                        value={currencyDraft[entry.key] ?? String(entry.amount ?? 0)}
                        disabled={!canEdit}
                        onChange={(event) => setCurrencyDraft({ ...currencyDraft, [entry.key]: event.currentTarget.value })}
                      />
                    </label>
                  ))}
                  <button type="submit" disabled={patchCurrency.isPending || !canEdit}>
                    {patchCurrency.isPending ? "Saving..." : "Save currency"}
                  </button>
                </form>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "personal" ? (
              <section className="session-character-form">
                <h3>Personal</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Species</strong>
                    <span>{readString(profile.species, selected.species || "--")}</span>
                  </article>
                  <article>
                    <strong>Background</strong>
                    <span>{readString(profile.background, selected.background || "--")}</span>
                  </article>
                </div>
                {readString(profile.biography_markdown) ? <pre className="article-body markdown-body">{readString(profile.biography_markdown)}</pre> : null}
                {readString(profile.personality_markdown) ? <pre className="article-body markdown-body">{readString(profile.personality_markdown)}</pre> : null}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "overview" ? (
              <section className="session-character-form">
                <h3>Overview</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Armor Class</strong>
                    <span>{String(stats.armor_class ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Initiative</strong>
                    <span>{String(stats.initiative_bonus ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Speed</strong>
                    <span>{String(stats.speed ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Proficiency</strong>
                    <span>{String(stats.proficiency_bonus ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Species</strong>
                    <span>{readString(profile.species, selected.species || "--")}</span>
                  </article>
                  <article>
                    <strong>Background</strong>
                    <span>{readString(profile.background, selected.background || "--")}</span>
                  </article>
                </div>
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "resources" ? (
              <section className="session-character-form">
                <h3>Resources</h3>
                {resources.length ? (
                  <div className="character-card-grid">
                    {resources.map((resource) => {
                      const id = readString(resource.id);
                      return (
                        <article className="character-state-card" key={id || readString(resource.label)}>
                          <h4>{readString(resource.label, id || "Resource")}</h4>
                          <p>
                            {readNumber(resource.current)} / {readNumber(resource.max)}
                          </p>
                          {resource.notes ? <p className="meta">{readString(resource.notes)}</p> : null}
                          {canEdit && id ? (
                            <form onSubmit={(event) => submitResource(event, id)} className="compact-state-form">
                              <label className="chat-label" htmlFor={`resource-${id}`}>
                                Current
                              </label>
                              <input
                                id={`resource-${id}`}
                                type="number"
                                min="0"
                                value={resourceDrafts[id] ?? ""}
                                onChange={(event) =>
                                  setResourceDrafts({ ...resourceDrafts, [id]: event.currentTarget.value })
                                }
                              />
                              <button type="submit" disabled={patchResource.isPending}>
                                Save
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
              <section className="session-character-form">
                <h3>Spells</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Ability</strong>
                    <span>{String(spellcasting.spellcasting_ability ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Save DC</strong>
                    <span>{String(spellcasting.spell_save_dc ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Attack</strong>
                    <span>{String(spellcasting.spell_attack_bonus ?? "--")}</span>
                  </article>
                </div>
                {spellSlots.length ? (
                  <div className="character-card-grid">
                    {spellSlots.map((slot) => {
                      const level = readNumber(slot.level);
                      const slotLaneId = readString(slot.slot_lane_id);
                      const key = draftKey(level, slotLaneId);
                      return (
                        <article className="character-state-card" key={key}>
                          <h4>Level {level}</h4>
                          <p>
                            Used {readNumber(slot.used)} / {readNumber(slot.max)}
                          </p>
                          {canEdit ? (
                            <form onSubmit={(event) => submitSpellSlot(event, slot)} className="compact-state-form">
                              <label className="chat-label" htmlFor={`spell-slot-${key}`}>
                                Used
                              </label>
                              <input
                                id={`spell-slot-${key}`}
                                type="number"
                                min="0"
                                max={readNumber(slot.max)}
                                value={spellSlotDrafts[key] ?? ""}
                                onChange={(event) =>
                                  setSpellSlotDrafts({ ...spellSlotDrafts, [key]: event.currentTarget.value })
                                }
                              />
                              <button type="submit" disabled={patchSpellSlot.isPending}>
                                Save
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : null}
                {presentedSpells.length ? (
                  <div className="spell-card-list">
                    {presentedSpells.map((spell) => (
                      <article className="character-state-card" key={draftKey(spell.class_row_id, spell.name, spell.level_label)}>
                        <p className="meta">
                          {[spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell"}
                        </p>
                        <h4>{spell.name || "Spell"}</h4>
                        {spell.badges?.length ? (
                          <div className="badge-list">
                            {spell.badges.map((badge) => (
                              <span className="meta-badge" key={badge}>
                                {badge}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        <p className="meta">
                          {[spell.casting_time, spell.range].filter((value) => value && value !== "--").join(" | ")}
                        </p>
                        {spell.description_html || spell.href ? (
                          <button type="button" className="button button-secondary detail-button" onClick={() => openSpellDetail(spell)}>
                            Details
                          </button>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : spells.length ? (
                  <div className="spell-card-list">
                    {spells.map((spell) => (
                      <article className="character-state-card" key={readString(spell.id, readString(spell.name))}>
                        <h4>{readString(spell.name, "Spell")}</h4>
                        <p className="meta">
                          {[spell.mark, spell.casting_time, spell.range].map((value) => readString(value)).filter(Boolean).join(" | ")}
                        </p>
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "equipment" ? (
              <section className="session-character-form">
                <h3>Equipment</h3>
                {equipmentState ? (
                  <div className="stat-grid">
                    <article>
                      <strong>Attuned items</strong>
                      <span>
                        {equipmentState.attuned_count} / {equipmentState.max_attuned_items}
                      </span>
                      {equipmentState.over_attunement_limit ? (
                        <p className="meta">This sheet is currently over the normal attunement limit.</p>
                      ) : null}
                    </article>
                    <article>
                      <strong>Equipped items</strong>
                      <span>{equipmentState.equipped_count}</span>
                    </article>
                  </div>
                ) : null}
                {arcaneArmorState?.available ? (
                  <article className="character-state-card">
                    <h4>{readString(arcaneArmorState.label, "Arcane Armor")}</h4>
                    <p className="meta">
                      {[arcaneArmorState.status_label, arcaneArmorState.hands_label].map((value) => readString(value)).filter(Boolean).join(" | ")}
                    </p>
                    {canEdit ? (
                      <form onSubmit={submitArcaneArmorState} className="equipment-state-form">
                        <label className="toggle-row">
                          <input
                            type="checkbox"
                            checked={arcaneArmorDraft}
                            onChange={(event) => setArcaneArmorDraft(event.currentTarget.checked)}
                          />
                          Enabled
                        </label>
                        <button type="submit" disabled={patchFeatureState.isPending}>
                          {patchFeatureState.isPending ? "Saving..." : "Save feature state"}
                        </button>
                      </form>
                    ) : null}
                  </article>
                ) : null}
                {equipmentRows.length ? (
                  <div className="character-card-grid">
                    {equipmentRows.map((item) => {
                      const draft = equipmentDrafts[item.id] ?? {
                        isEquipped: Boolean(item.is_equipped),
                        isAttuned: Boolean(item.is_attuned),
                        weaponWieldMode: item.weapon_wield_mode || "",
                      };
                      return (
                        <article className="character-state-card" key={item.id || item.name}>
                          <h4>{item.name || "Item"}</h4>
                          <p className="meta">
                            {[item.equipped_label, item.is_attuned ? "Attuned" : item.requires_attunement ? "Not attuned" : "", item.source_label]
                              .filter(Boolean)
                              .join(" | ")}
                          </p>
                          {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                          {item.description_html || item.notes || item.href ? (
                            <button type="button" className="button button-secondary detail-button" onClick={() => openItemDetail(item)}>
                              Item details
                            </button>
                          ) : null}
                          {canEdit ? (
                            <form onSubmit={(event) => submitEquipmentState(event, item)} className="equipment-state-form">
                              {item.supports_weapon_wield_mode ? (
                                <label className="chat-label" htmlFor={`equipment-wield-${item.id}`}>
                                  Wielding
                                  <select
                                    id={`equipment-wield-${item.id}`}
                                    value={draft.weaponWieldMode}
                                    onChange={(event) =>
                                      setEquipmentDrafts({
                                        ...equipmentDrafts,
                                        [item.id]: { ...draft, weaponWieldMode: event.currentTarget.value },
                                      })
                                    }
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
                                <label className="toggle-row">
                                  <input
                                    type="checkbox"
                                    checked={draft.isEquipped}
                                    onChange={(event) =>
                                      setEquipmentDrafts({
                                        ...equipmentDrafts,
                                        [item.id]: { ...draft, isEquipped: event.currentTarget.checked },
                                      })
                                    }
                                  />
                                  Equipped
                                </label>
                              )}
                              {item.requires_attunement ? (
                                <label className="toggle-row">
                                  <input
                                    type="checkbox"
                                    checked={draft.isAttuned}
                                    onChange={(event) =>
                                      setEquipmentDrafts({
                                        ...equipmentDrafts,
                                        [item.id]: { ...draft, isAttuned: event.currentTarget.checked },
                                      })
                                    }
                                  />
                                  Attuned
                                </label>
                              ) : null}
                              {item.attunement_hint && item.attunement_hint !== "Requires attunement" ? (
                                <p className="meta">{item.attunement_hint}</p>
                              ) : null}
                              <button type="submit" disabled={patchEquipmentState.isPending}>
                                {patchEquipmentState.isPending ? "Saving..." : "Save equipment state"}
                              </button>
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
              <section className="session-character-form">
                <h3>Inventory</h3>
                {inventory.length ? (
                  <div className="character-card-grid">
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
                        <article className="character-state-card" key={id || itemRef || itemName}>
                          <h4>{itemName}</h4>
                          <p className="meta">
                            Qty {readNumber(item.quantity, 1)}
                            {item.weight ? ` | ${readString(item.weight)}` : ""}
                          </p>
                          {itemTags.length ? <p className="meta">{itemTags.join(", ")}</p> : null}
                          {itemDescriptionHtml || itemNotes || itemHref ? (
                            <button
                              type="button"
                              className="button button-secondary detail-button"
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
                            <form onSubmit={(event) => submitInventory(event, id)} className="compact-state-form">
                              <label className="chat-label" htmlFor={`inventory-${id}`}>
                                Quantity
                              </label>
                              <input
                                id={`inventory-${id}`}
                                type="number"
                                min="0"
                                value={inventoryDrafts[id] ?? ""}
                                onChange={(event) =>
                                  setInventoryDrafts({ ...inventoryDrafts, [id]: event.currentTarget.value })
                                }
                              />
                              <button type="submit" disabled={patchInventory.isPending}>
                                Save
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : null}
                <form onSubmit={submitCurrency} className="currency-grid">
                  {["cp", "sp", "ep", "gp", "pp"].map((key) => (
                    <label key={key} className="chat-label" htmlFor={`currency-${key}`}>
                      {key.toUpperCase()}
                      <input
                        id={`currency-${key}`}
                        type="number"
                        min="0"
                        value={currencyDraft[key] ?? "0"}
                        disabled={!canEdit}
                        onChange={(event) => setCurrencyDraft({ ...currencyDraft, [key]: event.currentTarget.value })}
                      />
                    </label>
                  ))}
                  <button type="submit" disabled={patchCurrency.isPending || !canEdit}>
                    {patchCurrency.isPending ? "Saving..." : "Save currency"}
                  </button>
                </form>
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "abilities" ? (
              <section className="session-character-form">
                <h3>Abilities and Skills</h3>
                <div className="ability-grid">
                  {Object.entries(abilityScores).map(([key, value]) => {
                    const ability = asRecord(value);
                    return (
                      <article className="character-state-card" key={key}>
                        <h4>{key}</h4>
                        <p>Score {String(ability.score ?? "--")}</p>
                        <p>Modifier {String(ability.modifier ?? "--")}</p>
                        <p>Save {String(ability.save_bonus ?? "--")}</p>
                      </article>
                    );
                  })}
                </div>
                <div className="stat-grid">
                  <article>
                    <strong>Passive Perception</strong>
                    <span>{String(stats.passive_perception ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Passive Insight</strong>
                    <span>{String(stats.passive_insight ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Passive Investigation</strong>
                    <span>{String(stats.passive_investigation ?? "--")}</span>
                  </article>
                </div>
              </section>
            ) : null}

            {isReadSurface && activeCharacterSection === "controls" && canUseControls && controls ? (
              <section className="session-character-form character-controls-panel">
                <h3>Controls</h3>
                <div className="character-card-grid character-controls-grid">
                  <article className="character-state-card">
                    <h4>Player controls</h4>
                    {controls.current_user_is_owner ? (
                      <p>Player-controls workspace for {selected.name}.</p>
                    ) : (
                      <p>Character management controls for campaign staff.</p>
                    )}
                  </article>
                  <article className="character-state-card">
                    <h4>Current owner</h4>
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
                          <a className="button button-secondary" href={controls.assignment.admin_href}>
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
                  <article className="character-state-card character-controls-manager">
                    <h4>Assignment controls</h4>
                    <p className="meta">Assignments require an active player membership in this campaign.</p>
                    {controls.player_choices.length ? (
                      <form onSubmit={submitCharacterAssignment} className="inline-two-col">
                        <label htmlFor="character-owner-assignment" className="chat-label">
                          Assign owner
                        </label>
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
                        <div />
                        <button type="submit" disabled={controlsMutationPending || !controlsDraft.assignedUserId}>
                          {assignCharacterOwner.isPending ? "Saving..." : "Save assignment"}
                        </button>
                      </form>
                    ) : (
                      <p className="meta">No active player memberships are available for assignment in this campaign.</p>
                    )}
                    {controls.assignment ? (
                      <div className="button-row">
                        <button
                          type="button"
                          className="button button-secondary"
                          disabled={controlsMutationPending}
                          onClick={clearCharacterAssignment}
                        >
                          {clearCharacterOwner.isPending ? "Clearing..." : "Clear assignment"}
                        </button>
                      </div>
                    ) : null}
                  </article>
                ) : null}

                {controls.can_delete_character ? (
                  <article className="character-state-card character-controls-danger">
                    <h4>Delete character</h4>
                    <p>
                      Deleting a character removes the file-backed definition/import metadata, the live character state,
                      and any current assignment for this character slug.
                    </p>
                    <form onSubmit={submitCharacterDelete} className="inline-two-col">
                      <label htmlFor="character-delete-confirmation" className="chat-label">
                        Type {selected.slug} to confirm
                      </label>
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
                      <div />
                      <button
                        type="submit"
                        disabled={controlsMutationPending || controlsDraft.deleteConfirmation.trim() !== selected.slug}
                      >
                        {deleteCharacterMutation.isPending ? "Deleting..." : "Delete character"}
                      </button>
                    </form>
                  </article>
                ) : null}

                {controls.links?.flask_controls_url ? (
                  <div className="button-row">
                    <a className="button button-secondary" href={controls.links.flask_controls_url}>
                      Flask Controls
                    </a>
                  </div>
                ) : null}
              </section>
            ) : null}

            {((isDnd || isXianxia) ? activeCharacterSection === "notes" : !isDnd) ? (
              <section className="session-character-form">
                <h3>Player notes</h3>
                <form onSubmit={submitNotes}>
                  <label htmlFor="character-player-notes" className="chat-label">
                    Player notes
                  </label>
                  <textarea
                    id="character-player-notes"
                    rows={8}
                    value={notesDraft.notes}
                    disabled={!canEdit}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                      setNotesDraft({ ...notesDraft, notes: event.currentTarget.value })
                    }
                  />
                  <button type="submit" disabled={patchNotes.isPending || !canEdit}>
                    {patchNotes.isPending ? "Saving..." : "Save notes"}
                  </button>
                </form>
              </section>
            ) : null}

            {!isDnd && !isXianxia ? (
              <section className="session-character-form">
                <h3>{characterSystem(detailRecord)}</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Current HP</strong>
                    <span>{String(vitals.current_hp ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Temp HP</strong>
                    <span>{String(vitals.temp_hp ?? "--")}</span>
                  </article>
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
        {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
      </section>
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
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState({ title: "", body: "" });
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
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>DM controls</h2>
          <span className="pill">{payload?.active_session ? `Session #${payload.active_session.id}` : "No active session"}</span>
        </div>
        <div className="status-row">
          <article className="stat-card">
            <h3>Session state</h3>
            <p>{payload?.active_session ? payload.active_session.status : "inactive"}</p>
          </article>
          <article className="stat-card">
            <h3>Controls</h3>
            <div className="session-actions-row">
              <button type="button" onClick={() => startSessionMutation.mutate()} disabled={startSessionMutation.isPending}>
                {startSessionMutation.isPending ? "Starting..." : "Begin session"}
              </button>
              <button
                type="button"
                onClick={() => closeSessionMutation.mutate()}
                disabled={closeSessionMutation.isPending || !payload?.active_session}
              >
                {closeSessionMutation.isPending ? "Closing..." : "Close session"}
              </button>
            </div>
          </article>
          <article className="stat-card">
            <h3>Lifecycle</h3>
            <p>{statusText || uiMessage || "Ready."}</p>
          </article>
        </div>
        {startSessionMutation.error ? <p className="status status-error">{apiErrorMessage(startSessionMutation.error)}</p> : null}
        {closeSessionMutation.error ? <p className="status status-error">{apiErrorMessage(closeSessionMutation.error)}</p> : null}
        {paneError ? <p className="status status-error">{paneError}</p> : null}
        {uiMessage ? <p className="status status-neutral">{uiMessage}</p> : null}
      </section>

      <div className="split-grid">
        <DmArticleCreator
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
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Staged articles</h3>
            <span className="pill">{stagedArticles.length}</span>
          </div>
          <p className="status status-neutral">Unrevealed staged articles are editable and ready for reveal.</p>
          {stagedArticles.length ? (
            <div className="article-stack">
              {stagedArticles.map((article) => {
                const draft = stagedDrafts[article.id] ?? {
                  title: article.title,
                  body: article.body_markdown,
                  imageAltText: article.image?.alt_text || "",
                  imageCaption: article.image?.caption || "",
                };

                return (
                  <details className="article-card" key={article.id}>
                    <summary>
                      <strong>{article.title}</strong>
                    </summary>
                    {article.image ? (
                      <img className="article-image" src={resolveArticleImage(campaignSlug, article)} alt={article.image.alt_text || "Article image"} />
                    ) : null}
                    <SessionArticleSourceLine article={article} />
                    <label htmlFor={`dm-stage-title-${article.id}`} className="chat-label">
                      Title
                    </label>
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
                    <label htmlFor={`dm-stage-body-${article.id}`} className="chat-label">
                      Body (markdown or html)
                    </label>
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
                    <label htmlFor={`dm-stage-alt-${article.id}`} className="chat-label">
                      Image alt text (optional)
                    </label>
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
                    <label htmlFor={`dm-stage-caption-${article.id}`} className="chat-label">
                      Image caption (optional)
                    </label>
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
                    <div className="article-actions">
                      <SessionArticleReferenceActions article={article} includePromotionLinks />
                      <button
                        type="button"
                        disabled={updateArticleMutation.isPending}
                        onClick={() => {
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
                        {updateArticleMutation.isPending ? "Saving..." : "Save draft"}
                      </button>
                      <button
                        type="button"
                        className="button-danger"
                        disabled={revealArticleMutation.isPending}
                        onClick={() => revealArticleMutation.mutate(article.id)}
                      >
                        {revealArticleMutation.isPending ? "Revealing..." : "Reveal"}
                      </button>
                      <button
                        type="button"
                        className="button-danger"
                        disabled={deleteArticleMutation.isPending}
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="status status-neutral">No staged articles.</p>
          )}
        </section>
      </div>

      <section className="split-grid">
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Revealed articles</h3>
            <span className="pill">{revealedArticles.length}</span>
          </div>
          <div className="session-surface-subhead">
            <button
              type="button"
              className="button-danger"
              disabled={clearRevealedMutation.isPending || !revealedArticles.length}
              onClick={() => clearRevealedMutation.mutate()}
            >
              {clearRevealedMutation.isPending ? "Clearing..." : "Clear all revealed"}
            </button>
          </div>
          {revealedArticles.length ? (
            <div className="article-stack">
              {revealedArticles.map((article) => (
                <details className="article-card" key={article.id}>
                  <summary>
                    <strong>{article.title}</strong>
                    <span className="article-kind">{article.source_kind || "unclassified"}</span>
                  </summary>
                  {article.image ? (
                    <img className="article-image" src={resolveArticleImage(campaignSlug, article)} alt={article.image.alt_text || "Article image"} />
                  ) : null}
                  <SessionArticleSourceLine article={article} />
                  {renderArticleBody(article)}
                  <div className="article-actions">
                    <SessionArticleReferenceActions article={article} includePromotionLinks />
                    <button
                      type="button"
                      className="button-danger"
                      onClick={() => deleteArticleMutation.mutate(article.id)}
                      disabled={deleteArticleMutation.isPending}
                    >
                      {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <p className="status status-neutral">No revealed articles.</p>
          )}
        </section>
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Session logs</h3>
            <span className="pill">{sessionLogs.length}</span>
          </div>
          {sessionLogs.length ? (
            <div className="session-log-row">
              <div className="session-log-list">
                {sessionLogs.map((entry) => (
                  <button
                    type="button"
                    key={entry.session.id}
                    className={`session-log-list-row ${entry.session.id === selectedLogSessionId ? "active" : ""}`}
                    onClick={() => setSelectedLogSessionId(entry.session.id)}
                  >
                    <strong>Session {entry.session.id}</strong>
                    <span>{entry.message_count} messages</span>
                    <small>{formatTimestamp(entry.last_message_at)}</small>
                  </button>
                ))}
              </div>
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
                        className="button-danger"
                        onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}
                        disabled={deleteLogMutation.isPending}
                      >
                        {deleteLogMutation.isPending ? "Deleting..." : "Delete this log"}
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
            <p className="status status-neutral">No closed session logs.</p>
          )}
        </section>
      </section>
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
        <label htmlFor={`${idPrefix}-title`} className="chat-label">Title</label>
        <input
          id={`${idPrefix}-title`}
          value={draft.title}
          disabled={disabled}
          maxLength={200}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
        />
        {includeSlug ? (
          <>
            <label htmlFor={`${idPrefix}-slug`} className="chat-label">URL slug</label>
            <input
              id={`${idPrefix}-slug`}
              value={draft.slugLeaf}
              disabled={disabled}
              maxLength={120}
              placeholder="harbor-spark"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
            />
          </>
        ) : null}
        <div className="dm-content-image-edit-row">
          <label htmlFor={`${idPrefix}-type`} className="chat-label">
            Entry type
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
          <label htmlFor={`${idPrefix}-visibility`} className="chat-label">
            Visibility
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
        <label htmlFor={`${idPrefix}-provenance`} className="chat-label">Source/provenance</label>
        <input
          id={`${idPrefix}-provenance`}
          value={draft.provenance}
          disabled={disabled}
          maxLength={500}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ provenance: event.currentTarget.value })}
        />
        <label htmlFor={`${idPrefix}-search`} className="chat-label">Searchable metadata</label>
        <textarea
          id={`${idPrefix}-search`}
          rows={3}
          value={draft.searchMetadata}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ searchMetadata: event.currentTarget.value })}
        />
        <label htmlFor={`${idPrefix}-body`} className="chat-label">Rendered body markdown</label>
        <textarea
          id={`${idPrefix}-body`}
          rows={10}
          value={draft.bodyMarkdown}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
        />
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

      <section className="panel panel-nested" id="systems-source-enablement">
        <div className="panel-header">
          <div>
            <h3>Source Enablement</h3>
            <p className="meta">Library: {payload.systems_library || "Not configured"} | Systems scope: {payload.systems_scope_visibility_label}</p>
          </div>
          <span className="pill">{payload.source_count}</span>
        </div>
        {payload.has_proprietary_sources ? (
          <p className="status status-neutral">
            Proprietary-source acknowledgement: {payload.policy.proprietary_acknowledged ? "recorded" : "not yet recorded"}
          </p>
        ) : null}
        <form
          className="session-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            updateSourcesMutation.mutate();
          }}
        >
          <div className="systems-source-grid">
            {payload.source_rows.map((source: SystemsSourceRow) => {
              const draft = sourceDrafts[source.source_id] ?? {
                isEnabled: source.is_enabled,
                defaultVisibility: source.default_visibility,
              };
              return (
                <article className="systems-source-card" key={source.source_id}>
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
                  <label htmlFor={`systems-source-${source.source_id}-visibility`} className="chat-label">
                    Default visibility
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
                </article>
              );
            })}
          </div>
          {payload.has_proprietary_sources && !payload.policy.proprietary_acknowledged ? (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={acknowledgeProprietary}
                disabled={!canManageSystems}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setAcknowledgeProprietary(event.currentTarget.checked)}
              />
              I understand proprietary systems sources are for private campaign use only.
            </label>
          ) : null}
          <button type="submit" disabled={!canManageSystems || updateSourcesMutation.isPending}>
            {updateSourcesMutation.isPending ? "Saving..." : "Save systems sources"}
          </button>
        </form>
      </section>

      <section className="panel panel-nested" id="systems-entry-overrides">
        <div className="panel-header">
          <div>
            <h3>Entry Overrides</h3>
            <p className="meta">{payload.entry_override_count} saved override{payload.entry_override_count === 1 ? "" : "s"}</p>
          </div>
        </div>
        <form
          className="session-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            updateOverrideMutation.mutate();
          }}
        >
          <label htmlFor="systems-entry-override-key" className="chat-label">Entry key</label>
          <input
            id="systems-entry-override-key"
            value={overrideDraft.entryKey}
            placeholder="dnd-5e|spell|phb|fireball"
            disabled={!canManageSystems}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setOverrideDraft({ ...overrideDraft, entryKey: event.currentTarget.value })}
          />
          <div className="dm-content-image-edit-row">
            <label htmlFor="systems-entry-override-visibility" className="chat-label">
              Visibility override
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
            <label htmlFor="systems-entry-override-enabled" className="chat-label">
              Enablement override
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
          </div>
          <button type="submit" disabled={!canManageSystems || updateOverrideMutation.isPending}>
            {updateOverrideMutation.isPending ? "Saving..." : "Save entry override"}
          </button>
        </form>
        {payload.entry_override_rows.length ? (
          <div className="article-stack systems-override-list">
            {payload.entry_override_rows.map((override) => (
              <article className="article-card" key={override.entry_key}>
                <h4>{override.entry_href ? <a href={override.entry_href}>{override.entry_title}</a> : override.entry_title}</h4>
                <p className="meta">{override.entry_key}</p>
                <p className="meta">{override.source_label}{override.entry_type_label ? ` | ${override.entry_type_label}` : ""}</p>
                <div className="badge-list">
                  <span className="meta-badge">{override.visibility_label}</span>
                  <span className="meta-badge">{override.enablement_label}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="status status-neutral">No campaign-specific Systems entry overrides have been saved yet.</p>
        )}
      </section>

      <section className="panel panel-nested" id="systems-custom-entries">
        <div className="panel-header">
          <div>
            <h3>Custom Entries</h3>
            <p className="meta">{payload.custom_entry_count} custom campaign entr{payload.custom_entry_count === 1 ? "y" : "ies"}</p>
          </div>
        </div>
        <form
          className="session-form"
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
          <div className="article-stack systems-custom-list">
            {allCustomEntries.map((entry) => {
              const draft = customEditDrafts[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
              return (
                <details className="article-card" key={entry.entry_key}>
                  <summary>
                    <strong>{entry.title}</strong>
                    <span className="article-kind">{entry.entry_type_label}</span>
                  </summary>
                  <p className="meta">{entry.source_id} | {entry.visibility_label} | {entry.status_label}</p>
                  {entry.href ? <a className="button button-secondary" href={entry.href}>Open entry</a> : null}
                  {entry.provenance ? <p className="meta">Source/provenance: {entry.provenance}</p> : null}
                  {entry.search_metadata ? <p className="meta">Search metadata: {entry.search_metadata}</p> : null}
                  {entry.body_markdown ? <pre className="dm-content-preview dm-content-preview--compact">{entry.body_markdown}</pre> : null}
                  <form
                    className="session-form"
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
                      {entry.is_archived ? (
                        <button
                          type="button"
                          className="button button-secondary"
                          disabled={!canManageSystems || restoreCustomMutation.isPending}
                          onClick={() => restoreCustomMutation.mutate(entry)}
                        >
                          {restoreCustomMutation.isPending ? "Restoring..." : "Restore"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="button-danger"
                          disabled={!canManageSystems || archiveCustomMutation.isPending}
                          onClick={() => archiveCustomMutation.mutate(entry)}
                        >
                          {archiveCustomMutation.isPending ? "Archiving..." : "Archive"}
                        </button>
                      )}
                    </div>
                  </form>
                </details>
              );
            })}
          </div>
        ) : (
          <p className="status status-neutral">
            {customQuery ? "No custom Systems entries matched that search." : "No custom campaign Systems entries have been authored yet."}
          </p>
        )}
      </section>

      <section className="panel panel-nested" id="systems-shared-imports">
        <div className="panel-header">
          <div>
            <h3>Shared Source Imports</h3>
            <p className="meta">DND-5E ZIP import remains on the permission-gated Flask form for this slice.</p>
          </div>
        </div>
        {payload.permissions.can_import_shared_systems && payload.supports_dnd5e_import ? (
          <a className="button button-secondary" href={`${payload.links.flask_systems_lane_url}#systems-shared-imports`}>
            Open admin import form
          </a>
        ) : (
          <p className="status status-neutral">
            Shared-source ZIP imports are limited to app admins. Campaign DMs can review import runs and manage campaign policy here.
          </p>
        )}
      </section>

      <section className="panel panel-nested" id="systems-import-history">
        <div className="panel-header">
          <div>
            <h3>Import-Run History</h3>
            <p className="meta">{payload.import_run_count} recent shared-library run{payload.import_run_count === 1 ? "" : "s"}</p>
          </div>
        </div>
        {payload.import_run_rows.length ? (
          <div className="article-stack systems-import-history">
            {payload.import_run_rows.map((run) => (
              <article className="article-card" key={run.id}>
                <h4>{run.source_id} import #{run.id}</h4>
                <p className="meta">Started {formatTimestamp(run.started_at)}{run.completed_at ? ` | Completed ${formatTimestamp(run.completed_at)}` : ""}</p>
                {run.import_version ? <p className="meta">Import version: {run.import_version}</p> : null}
                <div className="badge-list">
                  <span className="meta-badge">{run.status}</span>
                  {run.imported_count !== null ? <span className="meta-badge">{run.imported_count} entries</span> : null}
                  {run.source_file_count !== null ? <span className="meta-badge">{run.source_file_count} files</span> : null}
                </div>
                {run.type_summary.length ? (
                  <p className="meta">{run.type_summary.map((item) => `${item.entry_type_label}: ${item.count}`).join(", ")}</p>
                ) : null}
                {run.error ? <p className="meta">Error: {run.error}</p> : null}
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
  const [manualDraft, setManualDraft] = useState({ title: "", body: "" });
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
    enabled: Boolean(resolvedCampaignSlug) && (activeLane === "statblocks" || activeLane === "conditions"),
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
      setManualDraft({ title: "", body: "" });
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
  const pageTitle = activeLane === "statblocks"
    ? "DM Content: Statblocks"
    : activeLane === "conditions"
      ? "DM Content: Conditions"
      : activeLane === "player-wiki"
        ? "DM Content: Player Wiki"
        : activeLane === "systems"
          ? "DM Content: Systems"
          : "DM Content: Staged Articles";
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
        <label htmlFor={`${idPrefix}-title`} className="chat-label">
          Title
        </label>
        <input
          id={`${idPrefix}-title`}
          name="title"
          maxLength={200}
          value={draft.title}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
        />
        {includeSlug ? (
          <>
            <label htmlFor={`${idPrefix}-slug`} className="chat-label">
              Slug
            </label>
            <input
              id={`${idPrefix}-slug`}
              name="slug_leaf"
              maxLength={120}
              value={draft.slugLeaf}
              placeholder="field-report"
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
            />
            <p className="meta">Page file: {targetPageRef}.md</p>
          </>
        ) : null}
        <div className="dm-content-image-edit-row">
          <label htmlFor={`${idPrefix}-section`} className="chat-label">
            Section
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
          <label htmlFor={`${idPrefix}-type`} className="chat-label">
            Page type
            <input
              id={`${idPrefix}-type`}
              name="page_type"
              maxLength={80}
              value={draft.pageType}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ pageType: event.currentTarget.value })}
            />
          </label>
        </div>
        <label htmlFor={`${idPrefix}-subsection`} className="chat-label">
          Subsection
        </label>
        <input
          id={`${idPrefix}-subsection`}
          name="subsection"
          maxLength={120}
          value={draft.subsection}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ subsection: event.currentTarget.value })}
        />
        <label htmlFor={`${idPrefix}-summary`} className="chat-label">
          Summary
        </label>
        <textarea
          id={`${idPrefix}-summary`}
          name="summary"
          rows={3}
          maxLength={400}
          value={draft.summary}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ summary: event.currentTarget.value })}
        />
        <label htmlFor={`${idPrefix}-aliases`} className="chat-label">
          Aliases
        </label>
        <textarea
          id={`${idPrefix}-aliases`}
          name="aliases"
          rows={3}
          value={draft.aliases}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ aliases: event.currentTarget.value })}
        />
        <div className="dm-content-image-edit-row">
          <label htmlFor={`${idPrefix}-reveal-after-session`} className="chat-label">
            Reveal after session
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
          <label htmlFor={`${idPrefix}-display-order`} className="chat-label">
            Display order
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
        </div>
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
        <label htmlFor={`${idPrefix}-source-ref`} className="chat-label">
          Source reference
        </label>
        <input
          id={`${idPrefix}-source-ref`}
          name="source_ref"
          value={draft.sourceRef}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ sourceRef: event.currentTarget.value })}
        />
        <label htmlFor={`${idPrefix}-image`} className="chat-label">
          Image path
        </label>
        <input
          id={`${idPrefix}-image`}
          name="image"
          value={draft.image}
          placeholder="npcs/example.webp"
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ image: event.currentTarget.value })}
        />
        <label htmlFor={`${idPrefix}-image-upload`} className="chat-label">
          Upload image
        </label>
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
        {draft.imageUpload ? <p className="status status-neutral">Selected image: {draft.imageUpload.filename}</p> : null}
        <div className="dm-content-image-edit-row">
          <label htmlFor={`${idPrefix}-image-alt`} className="chat-label">
            Image alt text
            <input
              id={`${idPrefix}-image-alt`}
              name="image_alt"
              value={draft.imageAlt}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageAlt: event.currentTarget.value })}
            />
          </label>
          <label htmlFor={`${idPrefix}-image-caption`} className="chat-label">
            Image caption
            <input
              id={`${idPrefix}-image-caption`}
              name="image_caption"
              value={draft.imageCaption}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageCaption: event.currentTarget.value })}
            />
          </label>
        </div>
        <label htmlFor={`${idPrefix}-body`} className="chat-label">
          Markdown body
        </label>
        <textarea
          id={`${idPrefix}-body`}
          name="body_markdown"
          rows={18}
          value={draft.bodyMarkdown}
          disabled={disabled}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
        />
      </>
    );
  };

  const renderStatblockCard = (statblock: DmContentStatblock) => {
    const draft = statblockDrafts[statblock.id] ?? buildInitialStatblockDraft(statblock);
    return (
      <details className="article-card dm-statblock-card" key={statblock.id}>
        <summary className="dm-statblock-summary">
          <strong>{statblock.title}</strong>
          <span className="article-kind">{statblock.subsection || "top level"}</span>
        </summary>
        <div className="badge-list dm-statblock-badges">
          {statblock.armor_class !== null ? <span className="meta-badge">AC {statblock.armor_class}</span> : null}
          <span className="meta-badge">HP {statblock.max_hp}</span>
          <span className="meta-badge">Speed {statblock.speed_text}</span>
          <span className="meta-badge">Init {formatInitiativeBonus(statblock.initiative_bonus)}</span>
          <span className="meta-badge">Move {statblock.movement_total} ft.</span>
        </div>
        <p className="status status-neutral">{statblock.parser_feedback.summary}</p>
        <p className="meta">
          Source file: {statblock.source_filename}. Combat seed source: dm_statblock:{statblock.id}.
        </p>
        <details className="feature-detail">
          <summary>View source markdown</summary>
          <pre className="dm-content-preview">{statblock.body_markdown}</pre>
        </details>
        {canManageDmContent ? (
          <form
            className="session-form"
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
            <label htmlFor={`dm-statblock-subsection-${statblock.id}`} className="chat-label">
              Subsection
            </label>
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
            <label htmlFor={`dm-statblock-markdown-${statblock.id}`} className="chat-label">
              Source markdown body
            </label>
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
            <div className="article-actions">
              <button type="submit" disabled={!canManageDmContent || updateStatblockMutation.isPending}>
                {updateStatblockMutation.isPending ? "Saving..." : "Save statblock"}
              </button>
              <button
                type="button"
                className="button-danger"
                disabled={!canManageDmContent || deleteStatblockMutation.isPending}
                onClick={() => deleteStatblockMutation.mutate(statblock.id)}
              >
                {deleteStatblockMutation.isPending ? "Deleting..." : "Delete statblock"}
              </button>
            </div>
          </form>
        ) : null}
      </details>
    );
  };

  const renderConditionCard = (condition: DmContentConditionDefinition) => {
    const draft = conditionDrafts[condition.id] ?? buildInitialConditionDraft(condition);
    return (
      <details className="article-card dm-condition-card" key={condition.id}>
        <summary>
          <strong>{condition.name}</strong>
          <span className="article-kind">condition</span>
        </summary>
        <pre className="dm-content-preview">{condition.description_markdown}</pre>
        {canManageDmContent ? (
          <form
            className="session-form"
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
            <label htmlFor={`dm-condition-name-${condition.id}`} className="chat-label">
              Name
            </label>
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
            <label htmlFor={`dm-condition-description-${condition.id}`} className="chat-label">
              Description (markdown)
            </label>
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
            <div className="article-actions">
              <button type="submit" disabled={!canManageDmContent || updateConditionMutation.isPending}>
                {updateConditionMutation.isPending ? "Saving..." : "Save condition"}
              </button>
              <button
                type="button"
                className="button-danger"
                disabled={!canManageDmContent || deleteConditionMutation.isPending}
                onClick={() => deleteConditionMutation.mutate(condition.id)}
              >
                {deleteConditionMutation.isPending ? "Deleting..." : "Delete condition"}
              </button>
            </div>
          </form>
        ) : null}
      </details>
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
    return (
      <details
        className="article-card dm-player-wiki-card"
        key={pageFile.page_ref}
        onToggle={(event) => {
          const target = event.currentTarget;
          if (target.open && !playerWikiEditDrafts[pageFile.page_ref]) {
            void loadPlayerWikiEditDraft(pageFile.page_ref);
          }
        }}
      >
        <summary>
          <strong>{pageFile.page.title || pageFile.page_ref}</strong>
          <span className="article-kind">{pageFile.page_ref}.md</span>
        </summary>
        <div className="badge-list">
          <span className="meta-badge">{playerWikiStatusLabel(pageFile)}</span>
          <span className="meta-badge">{pageFile.page.section || "Unsectioned"}</span>
          {pageFile.page.subsection ? <span className="meta-badge">{pageFile.page.subsection}</span> : null}
          {pageFile.page.image_path ? <span className="meta-badge">Image</span> : null}
          <span className="meta-badge">{safety.removal_status_label}</span>
        </div>
        {pageFile.page.summary ? <p className="meta">{pageFile.page.summary}</p> : null}
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
        <div className="article-actions">
          {pageFile.page.is_visible ? (
            <a className="button button-secondary" href={`/app-next/campaigns/${encodedCampaignSlug}/pages/${encodedPageRef}`}>
              Open
            </a>
          ) : null}
          <a className="button button-secondary" href={`/campaigns/${encodedCampaignSlug}/dm-content/player-wiki/pages/${encodedPageRef}/edit`}>
            Flask editor
          </a>
          <button
            type="button"
            disabled={!canManagePlayerWiki || archivePlayerWikiPageMutation.isPending || !pageFile.page.published}
            onClick={() => archivePlayerWikiPageMutation.mutate(pageFile.page_ref)}
          >
            {archivePlayerWikiPageMutation.isPending ? "Archiving..." : "Unpublish/archive"}
          </button>
        </div>
        {editDraft ? (
          <form
            className="session-form dm-player-wiki-edit-form"
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
            <div className="article-actions">
              <button type="submit" disabled={!canManagePlayerWiki || savePlayerWikiPageMutation.isPending}>
                {savePlayerWikiPageMutation.isPending ? "Saving..." : "Save wiki page"}
              </button>
            </div>
          </form>
        ) : (
          <button type="button" disabled={!canManagePlayerWiki} onClick={() => void loadPlayerWikiEditDraft(pageFile.page_ref)}>
            Load editor
          </button>
        )}
        <div className="dm-content-delete-form">
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
            className="button-danger"
            disabled={!canManagePlayerWiki || !safety.can_hard_delete || !deleteConfirmed || isDeleting}
            onClick={() => deletePlayerWikiPageMutation.mutate(pageFile.page_ref)}
          >
            {isDeleting ? "Deleting..." : "Delete file"}
          </button>
        </div>
      </details>
    );
  };

  return (
    <section className="panel dm-content-gen2-page">
      <div className="panel-header">
        <Link to="/" className="button button-secondary">
          Back to list
        </Link>
        <h2>{pageTitle}</h2>
        {(activeLane === "statblocks" || activeLane === "conditions") && canManageDmContent ? <span className="pill">DM+</span> : null}
        {activeLane === "staged-articles" && canManageSession ? <span className="pill">DM+</span> : null}
        {activeLane === "player-wiki" && canManagePlayerWiki ? <span className="pill">DM+</span> : null}
      </div>

      <ApiErrorNotice
        isLoading={pageIsLoading}
        message={pageError}
        onAuth={() => setAuthRequired(true)}
      />

      <div className="dm-content-gen2-links">
        <a
          className={activeLane === "statblocks" ? "is-active" : ""}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content`}
        >
          Statblocks
        </a>
        <a
          className={activeLane === "staged-articles" ? "is-active" : ""}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=staged-articles`}
        >
          Staged Articles
        </a>
        <a
          className={activeLane === "conditions" ? "is-active" : ""}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=conditions`}
        >
          Conditions
        </a>
        <a
          className={activeLane === "player-wiki" ? "is-active" : ""}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=player-wiki`}
        >
          Player Wiki
        </a>
        <a
          className={activeLane === "systems" ? "is-active" : ""}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=systems`}
        >
          Systems
        </a>
        <a href={`/campaigns/${encodedCampaignSlug}/session/dm`}>Session DM</a>
      </div>

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
          <section className="panel panel-nested dm-statblock-create">
            <div className="panel-header">
              <h3>Create statblock</h3>
              <span className="pill">Markdown</span>
            </div>
            <form
              className="session-form"
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
              <label htmlFor="dm-statblock-create-file-import" className="chat-label">
                Import markdown file
              </label>
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
              <label htmlFor="dm-statblock-create-filename" className="chat-label">
                Source filename
              </label>
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
              <label htmlFor="dm-statblock-create-subsection" className="chat-label">
                Subsection
              </label>
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
              <label htmlFor="dm-statblock-create-markdown" className="chat-label">
                Source markdown body
              </label>
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
              <button type="submit" disabled={!canManageDmContent || createStatblockMutation.isPending}>
                {createStatblockMutation.isPending ? "Saving..." : "Save statblock"}
              </button>
            </form>
          </section>

          <section className="panel panel-nested dm-statblock-library">
            <div className="panel-header">
              <h3>Statblock library</h3>
              <span className="pill">{statblocks.length}</span>
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
              <div className="article-stack dm-statblock-groups">
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
                      <div className="article-stack">
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
          <section className="panel panel-nested dm-condition-create">
            <div className="panel-header">
              <h3>Create condition</h3>
              <span className="pill">Custom</span>
            </div>
            <form
              className="session-form"
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
              <label htmlFor="dm-condition-create-name" className="chat-label">
                Name
              </label>
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
              <label htmlFor="dm-condition-create-description" className="chat-label">
                Description (markdown)
              </label>
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
              <button type="submit" disabled={!canManageDmContent || createConditionMutation.isPending}>
                {createConditionMutation.isPending ? "Saving..." : "Save condition"}
              </button>
            </form>
          </section>

          <section className="panel panel-nested dm-condition-library">
            <div className="panel-header">
              <h3>Condition library</h3>
              <span className="pill">{conditions.length}</span>
            </div>
            <p className="status status-neutral">
              Custom conditions merge into the Combat condition picker alongside built-in DND-5E conditions.
            </p>
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
              <div className="article-stack dm-condition-list">
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
          <section className="panel panel-nested dm-player-wiki-create">
            <div className="panel-header">
              <h3>Create player wiki page</h3>
              <span className="pill">Markdown</span>
            </div>
            <form
              className="session-form"
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

          <section className="panel panel-nested dm-player-wiki-library">
            <div className="panel-header">
              <h3>Player wiki pages</h3>
              <span className="pill">{playerWikiPages.length}</span>
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
              <div className="article-stack dm-player-wiki-list">
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

        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Staged articles</h3>
            <span className="pill">{stagedArticles.length}</span>
          </div>
          {stagedArticles.length ? (
            <div className="article-stack">
              {stagedArticles.map((article) => {
                const draft = stagedDrafts[article.id] ?? {
                  title: article.title,
                  body: article.body_markdown,
                  imageAltText: article.image?.alt_text || "",
                  imageCaption: article.image?.caption || "",
                  image: null,
                };
                return (
                  <details className="article-card" key={article.id}>
                    <summary>
                      <strong>{article.title}</strong>
                      <span className="article-kind">{article.source_kind || "manual"}</span>
                    </summary>
                    {article.image ? (
                      <img
                        className="article-image"
                        src={resolveArticleImage(resolvedCampaignSlug, article)}
                        alt={article.image.alt_text || "Article image"}
                      />
                    ) : null}
                    <SessionArticleSourceLine article={article} />
                    <form
                      className="session-form"
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
                      <label htmlFor={`dm-content-stage-title-${article.id}`} className="chat-label">
                        Title
                      </label>
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
                      <label htmlFor={`dm-content-stage-body-${article.id}`} className="chat-label">
                        Body
                      </label>
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
                      <div className="dm-content-image-edit-row">
                        <label htmlFor={`dm-content-stage-alt-${article.id}`} className="chat-label">
                          Image alt text
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
                        <label htmlFor={`dm-content-stage-caption-${article.id}`} className="chat-label">
                          Image caption
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
                      </div>
                      <label htmlFor={`dm-content-stage-image-${article.id}`} className="chat-label">
                        Replacement image
                      </label>
                      <input
                        id={`dm-content-stage-image-${article.id}`}
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
                      {draft.image ? <p className="status status-neutral">Selected image: {draft.image.filename}</p> : null}
                      <div className="article-actions">
                        <SessionArticleReferenceActions article={article} includePromotionLinks />
                        <button
                          type="submit"
                          disabled={!canManageSession || updateArticleMutation.isPending}
                        >
                          {updateArticleMutation.isPending ? "Saving..." : "Save draft"}
                        </button>
                        <button
                          type="button"
                          className="button-danger"
                          disabled={!canManageSession || deleteArticleMutation.isPending}
                          onClick={() => deleteArticleMutation.mutate(article.id)}
                        >
                          {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                        </button>
                      </div>
                    </form>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="status status-neutral">No staged articles.</p>
          )}
        </section>
      </div>
      )}
    </section>
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

  return (
    <section className="panel character-roster-page">
      <div className="panel-header">
        <div>
          <p className="meta">Character roster</p>
          <h1>Characters</h1>
          <p className="lede">Open player sheets, use the shared inline state controls, and keep larger authoring workflows in Flask while Gen2 parity grows.</p>
        </div>
      </div>
      <ApiErrorNotice isLoading={rosterQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      <section className="card character-roster-tools">
        <div className="section-heading">
          <div>
            <h2>Roster tools</h2>
          </div>
          <div className="article-actions">
            {data?.links?.flask_roster_url ? (
              <a className="button button-secondary" href={data.links.flask_roster_url}>
                Flask roster
              </a>
            ) : null}
            {data?.links?.create_character_url ? (
              <a className="button button-secondary" href={data.links.create_character_url}>
                Create character
              </a>
            ) : null}
            {data?.links?.import_xianxia_url ? (
              <a className="button button-secondary" href={data.links.import_xianxia_url}>
                Import existing
              </a>
            ) : null}
          </div>
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
                  <a className="button button-secondary" href={character.href || `/app-next/campaigns/${encodeURIComponent(resolvedCampaignSlug)}/characters/${encodeURIComponent(character.slug)}`}>
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
    </section>
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
  const selectedPlayerCharacter = payload?.selected_player_character ?? null;
  const selectedCharacterSlug = selectedPlayerCharacter?.character_slug || null;
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
      <nav className="combat-view-switch" aria-label="Combat view">
        {[
          { id: "status" as CombatView, label: "DM Status" },
          { id: "controls" as CombatView, label: "DM Controls" },
          { id: "player" as CombatView, label: "Player View" },
        ].map((view) => (
          <button
            type="button"
            key={view.id}
            className={effectiveCombatView === view.id ? "tab-button active" : "tab-button"}
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
            <div className="compact-header">
              <div>
                <p className="meta">Authority</p>
                <h3>Turn Focus</h3>
              </div>
              {selectedCombatant.is_current_turn ? <span className="pill">Current</span> : null}
            </div>
            <form
              className="combat-inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateTurnMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  turn_value: turnDraft.turnValue,
                  initiative_priority: turnDraft.initiativePriority,
                });
              }}
            >
              <label className="chat-label">
                Turn value
                <input
                  type="number"
                  value={turnDraft.turnValue}
                  onChange={(event) => setTurnDraft({ ...turnDraft, turnValue: event.currentTarget.value })}
                />
              </label>
              <label className="chat-label">
                Priority
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
            <div className="button-row">
              <button type="button" onClick={() => setCurrentMutation.mutate()} disabled={setCurrentMutation.isPending}>
                {setCurrentMutation.isPending ? "Setting..." : "Set current"}
              </button>
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
            <form
              className="combat-inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateVitalsMutation.mutate(vitalsPayload());
              }}
            >
              <label className="chat-label">
                Current HP
                <input
                  aria-label="DM Current HP"
                  type="number"
                  value={vitalsDraft.currentHp}
                  onChange={(event) => setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })}
                />
              </label>
              <label className="chat-label">
                Temp HP
                <input
                  aria-label="DM Temp HP"
                  type="number"
                  min="0"
                  value={vitalsDraft.tempHp}
                  onChange={(event) => setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })}
                />
              </label>
              {!isPlayerCharacter ? (
                <>
                  <label className="chat-label">
                    Max HP
                    <input
                      aria-label="DM Max HP"
                      type="number"
                      min="0"
                      value={vitalsDraft.maxHp}
                      onChange={(event) => setVitalsDraft({ ...vitalsDraft, maxHp: event.currentTarget.value })}
                    />
                  </label>
                  <label className="chat-label">
                    Movement total
                    <input
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
              <button type="submit" aria-label="Save DM vitals" disabled={updateVitalsMutation.isPending}>
                {updateVitalsMutation.isPending ? "Saving..." : "Save vitals"}
              </button>
            </form>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Round tools</p>
              <h3>Action Economy</h3>
            </div>
            <form
              className="combat-inline-form"
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
              <label className="chat-label">
                Movement remaining
                <input
                  aria-label="DM Movement Remaining"
                  type="number"
                  min="0"
                  value={resourcesDraft.movementRemaining}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, movementRemaining: event.currentTarget.value })
                  }
                />
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasAction}
                  onChange={(event) => setResourcesDraft({ ...resourcesDraft, hasAction: event.currentTarget.checked })}
                />
                Action
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasBonusAction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasBonusAction: event.currentTarget.checked })
                  }
                />
                Bonus action
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasReaction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasReaction: event.currentTarget.checked })
                  }
                />
                Reaction
              </label>
              <button type="submit" disabled={updateResourcesMutation.isPending}>
                {updateResourcesMutation.isPending ? "Saving..." : "Save economy"}
              </button>
            </form>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Tactical state</p>
              <h3>Conditions</h3>
            </div>
            <datalist id="gen2-combat-condition-options">
              {conditionOptions.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
            {selectedCombatant.conditions.length ? (
              <div className="combat-condition-stack">
                {selectedCombatant.conditions.map((condition) => (
                  <div className="combat-condition-chip" key={condition.id}>
                    <span>
                      <strong>{condition.name}</strong>
                      {condition.duration_text ? <small>{condition.duration_text}</small> : null}
                    </span>
                    <button
                      type="button"
                      className="button button-secondary"
                      onClick={() => deleteConditionMutation.mutate(condition)}
                      disabled={deleteConditionMutation.isPending}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="meta">No conditions are active on this combatant.</p>
            )}
            <form
              className="combat-inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                addConditionMutation.mutate(conditionDraft);
              }}
            >
              <label className="chat-label">
                Condition
                <input
                  type="text"
                  list="gen2-combat-condition-options"
                  value={conditionDraft.name}
                  onChange={(event) => setConditionDraft({ ...conditionDraft, name: event.currentTarget.value })}
                />
              </label>
              <label className="chat-label">
                Duration
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
          </article>
        </section>

        {selectedCombatant.character_slug ? (
          <section className="combat-pc-workspace">
            <div className="compact-header">
              <div>
                <p className="meta">Selected PC detail</p>
                <h3>{selectedCombatant.name}</h3>
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
          <button type="button" className="button button-secondary" onClick={() => deleteCombatantMutation.mutate()}>
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
          <div className="button-row">
            <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
              {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
            </button>
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
              className="button button-secondary"
              onClick={() => clearCombatMutation.mutate()}
              disabled={!confirmClearTracker || clearCombatMutation.isPending}
            >
              {clearCombatMutation.isPending ? "Clearing..." : "Clear tracker"}
            </button>
          </div>
        </article>

        <article className="card combat-control-card">
          <div>
            <p className="meta">Player character</p>
            <h3>Add PC</h3>
          </div>
          {availableCharacters.length ? (
            <form
              className="combat-inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                addPlayerMutation.mutate();
              }}
            >
              <label className="chat-label">
                Character
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
              <label className="chat-label">
                Turn value
                <input
                  type="number"
                  value={playerSeedDraft.turnValue}
                  onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, turnValue: event.currentTarget.value })}
                />
              </label>
              <label className="chat-label">
                Priority
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
            <p className="meta">All available visible characters are already in the tracker.</p>
          )}
        </article>

        <article className="card combat-control-card">
          <div>
            <p className="meta">Manual NPC</p>
            <h3>Add NPC</h3>
          </div>
          <form
            className="combat-inline-form combat-inline-form--wide"
            onSubmit={(event) => {
              event.preventDefault();
              addNpcMutation.mutate();
            }}
          >
            <label className="chat-label">
              Name
              <input
                type="text"
                value={npcSeedDraft.displayName}
                onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, displayName: event.currentTarget.value })}
              />
            </label>
            <label className="chat-label">
              Turn
              <input
                type="number"
                value={npcSeedDraft.turnValue}
                onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, turnValue: event.currentTarget.value })}
              />
            </label>
            <label className="chat-label">
              Initiative bonus
              <input
                type="number"
                value={npcSeedDraft.initiativeBonus}
                onChange={(event) =>
                  setNpcSeedDraft({ ...npcSeedDraft, initiativeBonus: event.currentTarget.value })
                }
              />
            </label>
            <label className="chat-label">
              DEX mod
              <input
                type="number"
                value={npcSeedDraft.dexterityModifier}
                onChange={(event) =>
                  setNpcSeedDraft({ ...npcSeedDraft, dexterityModifier: event.currentTarget.value })
                }
              />
            </label>
            <label className="chat-label">
              Max HP
              <input
                type="number"
                min="0"
                value={npcSeedDraft.maxHp}
                onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, maxHp: event.currentTarget.value })}
              />
            </label>
            <label className="chat-label">
              Current HP
              <input
                type="number"
                min="0"
                value={npcSeedDraft.currentHp}
                onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, currentHp: event.currentTarget.value })}
              />
            </label>
            <label className="chat-label">
              Movement
              <input
                type="number"
                min="0"
                value={npcSeedDraft.movementTotal}
                onChange={(event) =>
                  setNpcSeedDraft({ ...npcSeedDraft, movementTotal: event.currentTarget.value })
                }
              />
            </label>
            <label className="chat-label">
              Priority
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
              {addNpcMutation.isPending ? "Adding..." : "Add manual NPC"}
            </button>
          </form>
        </article>

        <article className="card combat-control-card">
          <div>
            <p className="meta">DM Content</p>
            <h3>Add Statblock</h3>
          </div>
          {canAccessDmContent && availableStatblocks.length ? (
            <form
              className="combat-inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                addStatblockMutation.mutate();
              }}
            >
              <label className="chat-label">
                Statblock
                <select
                  value={statblockSeedDraft.statblockId}
                  onChange={(event) => setStatblockSeedDraft({ ...statblockSeedDraft, statblockId: event.currentTarget.value })}
                >
                  <option value="">Choose statblock</option>
                  {availableStatblocks.map((choice) => (
                    <option key={choice.id} value={choice.id}>
                      {choice.title} - {choice.subtitle}
                    </option>
                  ))}
                </select>
              </label>
              <label className="chat-label">
                Display name override
                <input
                  type="text"
                  value={statblockSeedDraft.displayName}
                  onChange={(event) =>
                    setStatblockSeedDraft({ ...statblockSeedDraft, displayName: event.currentTarget.value })
                  }
                />
              </label>
              <label className="chat-label">
                Turn override
                <input
                  type="number"
                  value={statblockSeedDraft.turnValue}
                  onChange={(event) =>
                    setStatblockSeedDraft({ ...statblockSeedDraft, turnValue: event.currentTarget.value })
                  }
                />
              </label>
              <label className="chat-label">
                Priority
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
            <p className="meta">
              {canAccessDmContent ? "No DM Content statblocks are available." : "DM Content access is required for statblock seeding."}
            </p>
          )}
        </article>

        <article className="card combat-control-card">
          <div>
            <p className="meta">Systems source</p>
            <h3>Add Systems Monster</h3>
          </div>
          {canAccessSystems ? (
            <>
              <form className="search-form" onSubmit={searchSystemsMonsters}>
                <label htmlFor="combat-systems-search">Search Systems monsters</label>
                <input
                  id="combat-systems-search"
                  type="search"
                  value={systemsSearchQuery}
                  onChange={(event) => setSystemsSearchQuery(event.currentTarget.value)}
                />
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
              <div className="combat-inline-form">
                <label className="chat-label">
                  Display name override
                  <input
                    type="text"
                    value={systemsSeedDraft.displayName}
                    onChange={(event) => setSystemsSeedDraft({ ...systemsSeedDraft, displayName: event.currentTarget.value })}
                  />
                </label>
                <label className="chat-label">
                  Turn override
                  <input
                    type="number"
                    value={systemsSeedDraft.turnValue}
                    onChange={(event) => setSystemsSeedDraft({ ...systemsSeedDraft, turnValue: event.currentTarget.value })}
                  />
                </label>
                <label className="chat-label">
                  Priority
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
            </>
          ) : (
            <p className="meta">Systems access is required for monster source search.</p>
          )}
        </article>
      </section>
    );
  };

  const renderPlayerWorkspace = () => (
    <section className="combat-pc-workspace">
      <div className="compact-header">
        <div>
          <p className="meta">Selected PC workspace</p>
          <h3>{selectedPlayerCharacter?.name ?? "No tracked PC in combat"}</h3>
        </div>
        {payload?.player_character_targets.length ? (
          <div className="button-row">
            {payload.player_character_targets.map((target) => (
              <button
                type="button"
                key={target.combatant_id}
                className={target.is_selected ? "tab-button active" : "tab-button"}
                onClick={() => selectCombatant(target.combatant_id)}
              >
                {target.name}
              </button>
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
        <article className="card">
          <p>No assigned player character is currently available in this tracker.</p>
          {payload?.links?.flask_combat_url ? (
            <a className="button button-secondary" href={payload.links.flask_combat_url}>
              Open Flask Combat
            </a>
          ) : null}
        </article>
      )}
    </section>
  );

  return (
    <section className="panel combat-page">
      <div className="panel-header">
        <div>
          <p className="meta">Live play</p>
          <h2>Combat: {payload?.campaign.title ?? campaignSlug}</h2>
        </div>
        <div className="article-actions">
          {payload?.links?.flask_combat_url ? (
            <a className="button button-secondary" href={payload.links.flask_combat_url}>
              Flask Combat
            </a>
          ) : null}
          {canManageCombat && payload?.links?.flask_dm_status_url ? (
            <a className="button button-secondary" href={payload.links.flask_dm_status_url}>
              DM Status
            </a>
          ) : null}
          {canManageCombat && payload?.links?.flask_dm_controls_url ? (
            <a className="button button-secondary" href={payload.links.flask_dm_controls_url}>
              DM Controls
            </a>
          ) : null}
        </div>
      </div>
      {renderCombatViewSwitch()}

      <ApiErrorNotice
        isLoading={combatQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}

      {payload && !payload.combat_system_supported ? (
        <section className="card">
          <h3>Combat tracker unavailable</h3>
          <p>This campaign system does not use the DND-5E combat tracker yet.</p>
          {payload.links?.flask_combat_url ? (
            <a className="button button-secondary" href={payload.links.flask_combat_url}>
              Open Flask Combat
            </a>
          ) : null}
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
              <div className="compact-header">
                <h3>Turn Order</h3>
                <label className="chat-label combat-jump-label">
                  Jump
                  <select
                    value={selectedCombatant?.id ?? ""}
                    onChange={(event) => selectCombatant(Number(event.currentTarget.value))}
                  >
                    {tracker.combatants.map((combatant) => (
                      <option key={combatant.id} value={combatant.id}>
                        {combatant.name} - turn {combatant.turn_value}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="combat-carousel-track">
                {tracker.combatants.map((combatant) => renderCombatantCard(combatant))}
              </div>
            </section>
          ) : (
            <section className="card">
              <h3>No combatants</h3>
              <p>The tracker is empty. Use the Flask DM controls to seed the encounter for now.</p>
            </section>
          )}

          {selectedCombatant ? (
            <section className="combat-selected-snapshot">
              <div>
                <p className="meta">Inspected combatant</p>
                <h3>{selectedCombatant.name}</h3>
                <p>{selectedCombatant.subtitle || selectedCombatant.source_label || selectedCombatant.type_label}</p>
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
    </section>
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
    <section className="panel">
      <div className="panel-header">
        <Link to="/" className="button button-secondary">
          Back to list
        </Link>
        <h2>Session: {payload?.campaign.title ?? resolvedCampaignSlug}</h2>
        {canManage ? <span className="pill">DM+</span> : null}
      </div>

      <ApiErrorNotice
        isLoading={sessionQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />

      <div className="session-tab-strip">
        <button
          type="button"
          className={activePane === "session" ? "tab-button active" : "tab-button"}
          onClick={() => setActivePane("session")}
        >
          Session
        </button>
        <button
          type="button"
          className={activePane === "character" ? "tab-button active" : "tab-button"}
          onClick={() => setActivePane("character")}
        >
          Character
        </button>
        {canManage ? (
          <button
            type="button"
            className={activePane === "dm" ? "tab-button active" : "tab-button"}
            onClick={() => setActivePane("dm")}
          >
            DM
          </button>
        ) : null}
      </div>

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
