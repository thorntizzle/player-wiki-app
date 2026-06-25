import type {
  ContentPageFileRecord,
  ContentPageFileSummary,
  ContentPageMetadata,
  ContentPageRemovalSafety,
  CustomSystemsEntry,
  CustomSystemsEntryPayload,
  DmContentConditionDefinition,
  DmContentStatblock,
  DmContentSystemsResponse,
  SessionArticle,
} from "./api/types";
import type { EmbeddedImageInput } from "./sessionArticleDrafts";

export interface StagedArticleDraftState {
  title: string;
  body: string;
  imageAltText: string;
  imageCaption: string;
  image?: EmbeddedImageInput | null;
}

export interface DmContentConditionDraftState {
  name: string;
  description: string;
}

export interface DmPlayerWikiDraftState {
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

export type DmContentLane = "statblocks" | "staged-articles" | "conditions" | "player-wiki" | "systems";

export interface DmContentStatblockDraftState {
  filename: string;
  subsection: string;
  markdown: string;
}

export interface DmContentSystemsCustomDraftState {
  title: string;
  slugLeaf: string;
  entryType: string;
  visibility: string;
  provenance: string;
  searchMetadata: string;
  bodyMarkdown: string;
  sourcePageRef: string;
  itemMechanicsReviewStatus: string;
  itemBaseItem: string;
  itemBonusWeapon: string;
  itemBonusAc: string;
  itemArmorType: string;
  itemArmorAc: string;
  itemDamage: string;
  itemVersatileDamage: string;
  itemRange: string;
  itemProperties: string;
  itemRarity: string;
  itemAttunement: string;
}

export function buildInitialStagedArticleDraft(article: SessionArticle): StagedArticleDraftState {
  return {
    title: article.title,
    body: article.body_markdown,
    imageAltText: article.image?.alt_text || "",
    imageCaption: article.image?.caption || "",
    image: null,
  };
}

export const PLAYER_WIKI_SECTION_CHOICES = [
  { label: "NPCs", targetSubdir: "npcs", defaultType: "npc" },
  { label: "Locations", targetSubdir: "locations", defaultType: "location" },
  { label: "Factions", targetSubdir: "factions", defaultType: "faction" },
  { label: "Items", targetSubdir: "items", defaultType: "item" },
  { label: "Gods", targetSubdir: "gods", defaultType: "god" },
  { label: "Bestiary", targetSubdir: "bestiary", defaultType: "monster" },
  { label: "Lore", targetSubdir: "lore", defaultType: "lore" },
  { label: "Mechanics", targetSubdir: "mechanics", defaultType: "rule" },
  { label: "Notes", targetSubdir: "notes", defaultType: "note" },
  { label: "Races", targetSubdir: "races", defaultType: "race" },
  { label: "Sessions", targetSubdir: "sessions", defaultType: "session" },
  { label: "Spells", targetSubdir: "spells", defaultType: "spell" },
];

export function simpleSlug(value: string, fallback = "page"): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || fallback;
}

export function sectionChoiceForLabel(section: string) {
  const normalized = section.trim().toLowerCase();
  return (
    PLAYER_WIKI_SECTION_CHOICES.find((choice) => choice.label.toLowerCase() === normalized) ??
    PLAYER_WIKI_SECTION_CHOICES.find((choice) => choice.label === "Notes") ??
    PLAYER_WIKI_SECTION_CHOICES[0]
  );
}

export function buildInitialPlayerWikiDraft(): DmPlayerWikiDraftState {
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

export function buildInitialSystemsCustomDraft(payload?: DmContentSystemsResponse | null): DmContentSystemsCustomDraftState {
  return {
    title: "",
    slugLeaf: "",
    entryType: payload?.custom_entry_type_choices[0]?.value ?? "rule",
    visibility: payload?.custom_entry_default_visibility ?? "players",
    provenance: "",
    searchMetadata: "",
    bodyMarkdown: "",
    sourcePageRef: "",
    itemMechanicsReviewStatus: "draft",
    itemBaseItem: "",
    itemBonusWeapon: "",
    itemBonusAc: "",
    itemArmorType: "",
    itemArmorAc: "",
    itemDamage: "",
    itemVersatileDamage: "",
    itemRange: "",
    itemProperties: "",
    itemRarity: "",
    itemAttunement: "",
  };
}

export function buildSystemsCustomDraftFromEntry(entry: CustomSystemsEntry): DmContentSystemsCustomDraftState {
  const review = entry.item_mechanics;
  return {
    title: entry.title,
    slugLeaf: entry.slug,
    entryType: entry.entry_type || "rule",
    visibility: entry.visibility || "players",
    provenance: entry.provenance || "",
    searchMetadata: entry.search_metadata || "",
    bodyMarkdown: entry.body_markdown || "",
    sourcePageRef: entry.source_page_ref || entry.linked_published_page_ref || review?.source_page_ref || "",
    itemMechanicsReviewStatus: review?.review_status || "draft",
    itemBaseItem: "",
    itemBonusWeapon: "",
    itemBonusAc: "",
    itemArmorType: "",
    itemArmorAc: "",
    itemDamage: "",
    itemVersatileDamage: "",
    itemRange: "",
    itemProperties: "",
    itemRarity: "",
    itemAttunement: "",
  };
}

export function buildCustomSystemsPayload(draft: DmContentSystemsCustomDraftState): CustomSystemsEntryPayload {
  const payload: CustomSystemsEntryPayload = {
    title: draft.title.trim(),
    slug_leaf: draft.slugLeaf.trim(),
    entry_type: draft.entryType,
    visibility: draft.visibility,
    provenance: draft.provenance,
    search_metadata: draft.searchMetadata,
    body_markdown: draft.bodyMarkdown,
  };
  if (draft.entryType === "item") {
    payload.source_page_ref = draft.sourcePageRef.trim();
    payload.item_mechanics_review_status = draft.itemMechanicsReviewStatus || "draft";
    const itemMechanics = buildManualItemMechanicsPayload(draft);
    if (Object.keys(itemMechanics).length) {
      payload.item_mechanics = itemMechanics;
    }
  }
  return payload;
}

function buildManualItemMechanicsPayload(draft: DmContentSystemsCustomDraftState): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  addStringField(payload, "base_item", draft.itemBaseItem);
  addNumberField(payload, "bonus_weapon", draft.itemBonusWeapon);
  addNumberField(payload, "bonus_ac", draft.itemBonusAc);
  addStringField(payload, "type", draft.itemArmorType);
  addNumberField(payload, "ac", draft.itemArmorAc);
  addStringField(payload, "damage", draft.itemDamage);
  addStringField(payload, "versatile_damage", draft.itemVersatileDamage);
  addStringField(payload, "range", draft.itemRange);
  addStringField(payload, "properties", draft.itemProperties);
  addStringField(payload, "rarity", draft.itemRarity);
  addStringField(payload, "attunement", draft.itemAttunement);
  return payload;
}

function addStringField(payload: Record<string, unknown>, key: string, value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    payload[key] = trimmed;
  }
}

function addNumberField(payload: Record<string, unknown>, key: string, value: string): void {
  const trimmed = value.trim();
  if (!trimmed) {
    return;
  }
  const parsed = Number(trimmed);
  payload[key] = Number.isFinite(parsed) ? parsed : trimmed;
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

export function buildPlayerWikiDraftFromRecord(record: ContentPageFileRecord): DmPlayerWikiDraftState {
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

export function buildPageRefFromDraft(draft: DmPlayerWikiDraftState): string {
  const choice = sectionChoiceForLabel(draft.section);
  const slugLeaf = simpleSlug(draft.slugLeaf || draft.title, "page");
  return `${choice.targetSubdir}/${slugLeaf}`;
}

function parseNonNegativeInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

export function buildPlayerWikiMetadata(
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

export function buildPlayerWikiAssetRef(pageRef: string, image: EmbeddedImageInput): string {
  return `wiki-pages/${simpleSlug(pageRef, "wiki-page")}${imageExtension(image)}`;
}

export function playerWikiStatusLabel(pageFile: ContentPageFileSummary): string {
  if (pageFile.page.is_visible) {
    return "Visible";
  }
  if (!pageFile.page.published) {
    return "Unpublished";
  }
  return `Reveals after session ${pageFile.page.reveal_after_session}`;
}

export function playerWikiRemovalSafety(pageFile: ContentPageFileSummary): ContentPageRemovalSafety {
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

export function buildInitialStatblockDraft(statblock: DmContentStatblock): DmContentStatblockDraftState {
  return {
    filename: statblock.source_filename || `${statblock.title || "statblock"}.md`,
    subsection: statblock.subsection || "",
    markdown: statblock.body_markdown || "",
  };
}

export function buildInitialConditionDraft(condition: DmContentConditionDefinition): DmContentConditionDraftState {
  return {
    name: condition.name || "",
    description: condition.description_markdown || "",
  };
}

export function formatInitiativeBonus(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}
