import type {
  CharacterPresentedSpell,
  CharacterRecord,
  CharacterXianxiaInventoryItem,
  CharacterXianxiaInventoryItemPayload,
  CharacterXianxiaNamedRecord,
} from "./api/types";
import type { CharacterDetailDialogState, DetailFact } from "./components/CharacterDetailDialog";
import { asRecord, readString } from "./characterValueUtils";

export interface CharacterXianxiaInventoryDraft {
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

export type CharacterSection =
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
  | "portrait"
  | "personal"
  | "notes"
  | "controls";

export function asCharacterXianxiaNamedRecord(value: unknown): CharacterXianxiaNamedRecord {
  const record = asRecord(value);
  return {
    ...record,
    name: readString(record.name),
  } as CharacterXianxiaNamedRecord;
}

export function draftKey(...parts: Array<string | number | null | undefined>): string {
  return parts.map((part) => String(part ?? "")).join("::");
}

export interface CharacterNumberInputParseResult {
  value: number | null;
  errorMessage: string | null;
}

export function parseCharacterNumberInput(value: string, label: string): CharacterNumberInputParseResult {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return { value: null, errorMessage: `Enter a valid ${label}.` };
  }
  return { value: parsed, errorMessage: null };
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

export function groupSpellsByLevel<T>(
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

export function presentedSpellCardDetailLine(spell: CharacterPresentedSpell): string {
  return compactSpellDetailLine([
    spell.casting_time,
    spell.range,
    spell.duration,
    spell.components,
    spell.save_or_hit,
  ]);
}

export function rawSpellCardDetailLine(spell: Record<string, unknown>): string {
  return compactSpellDetailLine([
    readString(spell.casting_time),
    readString(spell.range),
    readString(spell.duration),
    readString(spell.components),
  ]);
}

export function collectPresentedSpells(character: CharacterRecord | undefined): CharacterPresentedSpell[] {
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

export function spellDetailFacts(spell: CharacterPresentedSpell): DetailFact[] {
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

export interface CharacterItemDetailInput {
  name: string;
  href?: string;
  description_html?: string;
  notes?: string;
}

export function itemDetailDialogState(item: CharacterItemDetailInput): CharacterDetailDialogState {
  return {
    eyebrow: "Item details",
    title: item.name || "Item",
    html: item.description_html || "",
    notes: item.notes || "",
    href: item.href || "",
  };
}

export function spellDetailDialogState(spell: CharacterPresentedSpell): CharacterDetailDialogState {
  const source = [spell.source, spell.reference].filter(Boolean).join(" | ");
  return {
    eyebrow: [spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell details",
    title: spell.name || "Spell",
    html: spell.description_html || "",
    notes: spell.management_note || "",
    href: spell.href || "",
    facts: [...spellDetailFacts(spell), ...(source ? [{ label: "Source", value: source }] : [])],
    badges: spell.badges ?? [],
  };
}

export function characterSystem(character: CharacterRecord | undefined): string {
  return readString(character?.definition?.system, "DND-5E");
}

export function isDndCharacter(character: CharacterRecord | undefined): boolean {
  return characterSystem(character).toLowerCase() === "dnd-5e";
}

export function isXianxiaCharacter(character: CharacterRecord | undefined): boolean {
  return characterSystem(character).toLowerCase() === "xianxia";
}

export const dndCharacterSections: Array<{ id: CharacterSection; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "resources", label: "Resources" },
  { id: "spells", label: "Spells" },
  { id: "equipment", label: "Equipment" },
  { id: "inventory", label: "Inventory" },
  { id: "abilities", label: "Abilities and Skills" },
  { id: "personal", label: "Personal" },
  { id: "portrait", label: "Portrait" },
  { id: "notes", label: "Notes" },
];

export const xianxiaCharacterSections: Array<{ id: CharacterSection; label: string }> = [
  { id: "quick-reference", label: "Quick Reference" },
  { id: "martial-arts", label: "Martial Arts" },
  { id: "techniques", label: "Techniques" },
  { id: "resources", label: "Resources" },
  { id: "skills", label: "Skills" },
  { id: "equipment", label: "Equipment" },
  { id: "inventory", label: "Inventory" },
  { id: "portrait", label: "Portrait" },
  { id: "personal", label: "Personal" },
  { id: "notes", label: "Notes" },
];

const characterControlsSection: { id: CharacterSection; label: string } = { id: "controls", label: "Controls" };

export function visibleCharacterSectionsForSystem(
  isDnd: boolean,
  canUseControls: boolean,
): Array<{ id: CharacterSection; label: string }> {
  const baseSections = isDnd ? dndCharacterSections : xianxiaCharacterSections;
  return canUseControls ? [...baseSections, characterControlsSection] : baseSections;
}

export function defaultCharacterReadSection(isXianxia: boolean): CharacterSection {
  return isXianxia ? "quick-reference" : "overview";
}

export function normalizeActiveCharacterSectionForSystem(
  activeSection: CharacterSection,
  {
    canUseControls,
    hasDetailRecord,
    isDnd,
    isXianxia,
  }: { canUseControls: boolean; hasDetailRecord: boolean; isDnd: boolean; isXianxia: boolean },
): CharacterSection {
  if (isXianxia && activeSection === "overview") {
    return "quick-reference";
  }
  if (isDnd && activeSection === "quick-reference") {
    return "overview";
  }
  if (activeSection === "controls" && hasDetailRecord && !canUseControls) {
    return defaultCharacterReadSection(isXianxia);
  }
  return activeSection;
}

export function characterReadSectionUrl(
  campaignSlug: string,
  characterSlug: string | null | undefined,
  section: CharacterSection,
  defaultSection: CharacterSection,
): string {
  if (!characterSlug) {
    return "";
  }
  const basePath = `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(characterSlug)}`;
  if (section === defaultSection) {
    return basePath;
  }
  return `${basePath}?page=${encodeURIComponent(section)}`;
}

export function normalizeCharacterSection(value: string | null): CharacterSection | null {
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
    case "portrait":
      return "portrait";
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

export function joinDisplay(values: Array<string | number | null | undefined>): string {
  return values.map((value) => String(value ?? "").trim()).filter(Boolean).join(" | ");
}

export function xianxiaDaoUseRecordDraftKey(record: CharacterXianxiaNamedRecord): string {
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

export function xianxiaInventoryDraftFromItem(item?: CharacterXianxiaInventoryItem): CharacterXianxiaInventoryDraft {
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

export function xianxiaInventoryPayloadFromDraft(draft: CharacterXianxiaInventoryDraft): CharacterXianxiaInventoryItemPayload {
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
