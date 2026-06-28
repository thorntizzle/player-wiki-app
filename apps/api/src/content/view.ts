import type {
  CampaignAssetFileRecord,
  CampaignCharacterFileRecord,
  CampaignConfigRecord,
  CampaignPageFileRecord,
  ContentPagePayload,
  ContentPageRemovalSafety,
  DeletedCharacterContent,
} from "./types.js";
import type { CharacterStateSnapshot } from "./characterState.js";
import type { CampaignViewModel } from "../campaigns/view.js";

const EDITABLE_FIELDS = [
  "current_session",
  "source_wiki_root",
  "summary",
  "system",
  "systems_library",
  "title",
];

export interface CampaignConfigPayload {
  ok: true;
  config_file: {
    campaign_slug: string;
    updated_at: string;
    config: Record<string, unknown>;
    editable_fields: string[];
  };
}

const FIXTURE_REMOVAL_SAFETY: ContentPageRemovalSafety = {
  can_hard_delete: true,
  hard_delete_blockers: [],
  removal_status_label: "Hard delete available",
  removal_guidance: "Hard delete is available after confirmation.",
  blockers_by_type: {
    backlinks: [],
    character_hooks: [],
    session_provenance: [],
  },
  samples: {
    backlinks: "",
    character_hooks: "",
    session_provenance: "",
  },
  page_title: "",
};

function normalizeRemovalSafety(
  record: CampaignPageFileRecord,
  removalSafety?: ContentPageRemovalSafety,
): ContentPageRemovalSafety {
  const source = removalSafety ?? FIXTURE_REMOVAL_SAFETY;
  return {
    can_hard_delete: source.can_hard_delete ?? true,
    hard_delete_blockers: source.hard_delete_blockers?.length ? source.hard_delete_blockers : [],
    blockers_by_type: {
      backlinks: source.blockers_by_type?.backlinks || [],
      character_hooks: source.blockers_by_type?.character_hooks || [],
      session_provenance: source.blockers_by_type?.session_provenance || [],
    },
    samples: {
      backlinks: source.samples?.backlinks || "",
      character_hooks: source.samples?.character_hooks || "",
      session_provenance: source.samples?.session_provenance || "",
    },
    page_title: source.page_title || record.page.title,
    removal_status_label: source.removal_status_label || "Hard delete available",
    removal_guidance: source.removal_guidance || "Hard delete is available after confirmation.",
  };
}

function withVisibilityDefaults(record: CampaignPageFileRecord): ContentPagePayload {
  return {
    page_ref: record.page_ref,
    relative_path: record.relative_path,
    updated_at: record.updated_at,
    metadata: record.metadata,
    page: record.page,
    removal_safety: normalizeRemovalSafety(record, FIXTURE_REMOVAL_SAFETY),
    can_hard_delete: true,
    hard_delete_blockers: [],
    removal_status_label: "Hard delete available",
    removal_guidance: "Hard delete is available after confirmation.",
  };
}

function recordString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
  }
  return fallback;
}

function asBool(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on", "equipped", "attuned"].includes(normalized)) {
      return true;
    }
    if (["0", "false", "no", "off", "none", "not equipped", "not attuned"].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function nonNegativeInt(value: unknown, fallback = 0): number {
  return Math.max(0, asInt(value, fallback));
}

function escapeHtml(rawValue: unknown): string {
  return String(rawValue ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderPlainMarkdownHtml(rawValue: unknown): string {
  const text = asString(rawValue);
  if (!text) {
    return "";
  }
  return text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => `<p>${escapeHtml(block).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

function formatModifier(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    const trimmed = value.trim();
    const numeric = Number(trimmed);
    if (!Number.isFinite(numeric)) {
      return trimmed;
    }
    value = numeric;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    const normalized = Math.trunc(value);
    return normalized >= 0 ? `+${normalized}` : String(normalized);
  }
  return "";
}

function titleCaseFromKey(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const STANDARD_DND_CLASS_HIT_DICE: Record<string, number> = {
  artificer: 8,
  barbarian: 12,
  bard: 8,
  cleric: 8,
  druid: 8,
  fighter: 10,
  monk: 8,
  paladin: 10,
  ranger: 10,
  rogue: 8,
  sorcerer: 6,
  warlock: 8,
  wizard: 6,
};

const VALID_HIT_DIE_FACES = new Set([4, 6, 8, 10, 12]);

export function buildCampaignConfigPayload(record: CampaignConfigRecord): CampaignConfigPayload {
  return {
    ok: true,
    config_file: {
      campaign_slug: record.campaign_slug,
      updated_at: record.updated_at,
      config: record.config,
      editable_fields: [...EDITABLE_FIELDS].sort(),
    },
  };
}

function campaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function flaskCampaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}

function profileClassLevelText(profile: Record<string, unknown>, fallback = "Character"): string {
  const classRows = asArray(profile.classes)
    .map(asRecord)
    .map((row) => {
      const systemsRef = asRecord(row.systems_ref);
      const className = asString(systemsRef.title) || asString(row.class_name);
      const classLevel = asInt(row.level, 0);
      if (className && classLevel > 0) {
        return `${className} ${classLevel}`;
      }
      if (className) {
        return className;
      }
      return classLevel > 0 ? `Level ${classLevel}` : "";
    })
    .filter((item) => item.length > 0);
  if (classRows.length > 0) {
    return classRows.join(" / ");
  }
  return asString(profile.class_level_text) || fallback;
}

function summarizeResourceValue(resource: Record<string, unknown>): string {
  const current = asInt(resource.current, 0);
  if (resource.max === null || resource.max === undefined) {
    return String(current);
  }
  return `${current} / ${asInt(resource.max, 0)}`;
}

function buildResourcePreview(state: Record<string, unknown>): Array<{ label: string; value: string }> {
  return asArray(state.resources)
    .map(asRecord)
    .sort((left, right) => {
      const leftOrder = asInt(left.display_order, 0);
      const rightOrder = asInt(right.display_order, 0);
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      return (asString(left.label) || "resource").toLowerCase().localeCompare((asString(right.label) || "resource").toLowerCase());
    })
    .slice(0, 3)
    .map((resource) => ({
      label: asString(resource.label) || "Resource",
      value: summarizeResourceValue(resource),
    }));
}

function normalizeSystemKey(value: unknown): string {
  return asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function isXianxiaSystem(value: unknown): boolean {
  return normalizeSystemKey(value) === "xianxia";
}

function extractHitDieFaces(value: unknown): number {
  if (value === null || value === undefined || value === "") {
    return 0;
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return extractHitDieFaces(record.faces ?? record.face ?? record.die);
  }
  let text = String(value).trim().toLowerCase();
  if (text.startsWith("d")) {
    text = text.slice(1);
  }
  const faces = Number.parseInt(text, 10);
  return VALID_HIT_DIE_FACES.has(faces) ? faces : 0;
}

function normalizeClassName(value: unknown): string {
  return asString(value)
    .toLowerCase()
    .replace(/[^a-z]/g, "");
}

function profileClassRows(profile: Record<string, unknown>): Record<string, unknown>[] {
  const rows = asArray(profile.classes)
    .map(asRecord)
    .filter((row) => Object.keys(row).length > 0);
  if (rows.length > 0) {
    return rows;
  }

  const classLevelText = asString(profile.class_level_text);
  const match = classLevelText.match(/^([A-Za-z][A-Za-z '\-]*)\s+(\d+)$/);
  if (!match) {
    return [];
  }
  return [{ class_name: match[1]?.trim() || "", level: asInt(match[2], 0) }];
}

function hitDieFacesForClassRow(classRow: Record<string, unknown>): number {
  for (const key of ["hit_die_faces", "hit_die_face", "hit_die"]) {
    const faces = extractHitDieFaces(classRow[key]);
    if (faces) {
      return faces;
    }
  }

  const metadata = asRecord(classRow.metadata);
  const metadataFaces = extractHitDieFaces(metadata.hit_die ?? metadata.hitDie);
  if (metadataFaces) {
    return metadataFaces;
  }

  const systemsRef = asRecord(classRow.systems_ref);
  const systemsRefFaces = extractHitDieFaces(systemsRef.hit_die ?? systemsRef.hitDie);
  if (systemsRefFaces) {
    return systemsRefFaces;
  }
  const systemsRefMetadata = asRecord(systemsRef.metadata);
  const systemsRefMetadataFaces = extractHitDieFaces(systemsRefMetadata.hit_die ?? systemsRefMetadata.hitDie);
  if (systemsRefMetadataFaces) {
    return systemsRefMetadataFaces;
  }

  const className = normalizeClassName(classRow.class_name ?? classRow.name);
  return STANDARD_DND_CLASS_HIT_DICE[className] ?? (className ? 8 : 0);
}

function deriveHitDiceMaxPools(definition: Record<string, unknown>): Array<{ faces: number; max: number }> {
  if (isXianxiaSystem(definition.system)) {
    return [];
  }

  const maxByFaces = new Map<number, number>();
  for (const classRow of profileClassRows(asRecord(definition.profile))) {
    const level = asInt(classRow.level, 0);
    if (level <= 0) {
      continue;
    }
    const faces = hitDieFacesForClassRow(classRow);
    if (!faces) {
      continue;
    }
    maxByFaces.set(faces, (maxByFaces.get(faces) ?? 0) + level);
  }

  return [...maxByFaces.entries()]
    .sort(([leftFaces], [rightFaces]) => leftFaces - rightFaces)
    .map(([faces, max]) => ({ faces, max }))
    .filter((pool) => pool.max > 0);
}

function existingHitDiceCurrentByFaces(rawState: unknown): Map<number, number> {
  const hitDiceState = asRecord(rawState);
  const currentByFaces = new Map<number, number>();

  for (const pool of asArray(hitDiceState.pools).map(asRecord)) {
    const faces = extractHitDieFaces(pool.faces ?? pool.die ?? pool.label);
    if (faces) {
      currentByFaces.set(faces, asInt(pool.current, 0));
    }
  }

  for (const [key, value] of Object.entries(hitDiceState)) {
    const faces = extractHitDieFaces(key);
    if (faces) {
      currentByFaces.set(faces, asInt(value, 0));
    }
  }
  return currentByFaces;
}

function hitDiceLongRestRegainAmount(definition: Record<string, unknown>): number {
  const totalLevel = deriveHitDiceMaxPools(definition).reduce((sum, pool) => sum + pool.max, 0);
  return totalLevel > 0 ? Math.max(1, Math.floor(totalLevel / 2)) : 0;
}

function buildHitDiceSummary(definition: Record<string, unknown>, state: Record<string, unknown>) {
  const existingCurrentByFaces = existingHitDiceCurrentByFaces(state.hit_dice);
  const pools = deriveHitDiceMaxPools(definition)
    .map((pool) => {
      const current = existingCurrentByFaces.get(pool.faces) ?? pool.max;
      return {
        faces: pool.faces,
        label: `d${pool.faces}`,
        current: Math.max(0, Math.min(current, pool.max)),
        max: pool.max,
        input_name: `hit_dice_d${pool.faces}`,
      };
    })
    .filter((pool) => pool.faces > 0);
  const value = pools.map((pool) => `${pool.label} ${pool.current}/${pool.max}`).join(" | ");
  const fullValue = pools
    .filter((pool) => pool.max > 0)
    .map((pool) => `${pool.max}d${pool.faces}`)
    .join(" + ");
  return {
    pools,
    value: value || "--",
    full_value: fullValue || "--",
    regain_on_long_rest: hitDiceLongRestRegainAmount(definition),
  };
}

function buildCharacterPortraitPayload(
  campaignSlug: string,
  record: CampaignCharacterFileRecord,
  assetByRef: Map<string, CampaignAssetFileRecord>,
) {
  const profile = asRecord(record.definition.profile);
  const assetRef = asString(profile.portrait_asset_ref);
  if (!assetRef) {
    return null;
  }
  const asset = assetByRef.get(assetRef);
  if (!asset) {
    return null;
  }
  return {
    asset_ref: assetRef,
    url: `/campaigns/${campaignSlug}/characters/${record.character_slug}/portrait`,
    media_type: asset.media_type,
    alt_text: asString(profile.portrait_alt) || asString(record.definition.name) || record.character_slug,
    caption: asString(profile.portrait_caption),
  };
}

interface CharacterDetailPermissions {
  can_edit_session: boolean;
  can_manage_session: boolean;
  can_use_controls: boolean;
  can_record_xianxia_dao_immolating_use: boolean;
}

interface CharacterDetailControls {
  available: boolean;
  assignment?: Record<string, unknown> | null;
  can_assign_owner: boolean;
  can_delete_character: boolean;
  current_user_is_owner: boolean;
  player_choices: Array<Record<string, unknown>>;
  links?: Record<string, string>;
}

export interface CharacterDetailLinkedSystemsEntry {
  slug: string;
  title: string;
  entry_type: string;
  metadata: Record<string, unknown>;
  rendered_html: string;
}

interface CharacterDetailPresenterSources {
  campaignPageRecords?: CampaignPageFileRecord[];
  systemsEntriesBySlug?: Map<string, CharacterDetailLinkedSystemsEntry>;
}

function buildEmptyArcaneArmorState() {
  return {
    available: false,
    feature_key: "",
    label: "",
    enabled: false,
    status_label: "",
    hands_free: false,
    hands_label: "",
    thunder_gauntlets_available: false,
    defensive_field_available: false,
  };
}

function buildEmptyEquipmentState() {
  const arcaneArmorState = buildEmptyArcaneArmorState();
  return {
    rows: [],
    attuned_count: 0,
    equipped_count: 0,
    max_attuned_items: 3,
    equipment_item_refs: [],
    attunable_item_refs: [],
    at_attunement_limit: false,
    over_attunement_limit: false,
    arcane_armor_state: arcaneArmorState,
  };
}

function buildOverviewStats(definition: Record<string, unknown>, state: Record<string, unknown>) {
  const profile = asRecord(definition.profile);
  const stats = asRecord(definition.stats);
  const vitals = asRecord(state.vitals);
  const overviewStats = [
    { label: "Class", value: asString(profile.class_level_text) || profileClassLevelText(profile) },
    { label: "Species", value: asString(profile.species) || "--" },
    { label: "Background", value: asString(profile.background) || "--" },
    { label: "Armor Class", value: asString(stats.armor_class) || String(asInt(stats.armor_class, 0) || "--") },
    {
      label: "Current HP",
      value: `${asInt(vitals.current_hp, asInt(stats.max_hp, 0))} / ${asInt(stats.max_hp, 0) || "--"}`,
    },
    { label: "Temp HP", value: String(asInt(vitals.temp_hp, 0)) },
    { label: "Initiative", value: formatModifier(stats.initiative_bonus) || "--" },
    { label: "Speed", value: asString(stats.speed) || "--" },
    { label: "Proficiency", value: formatModifier(stats.proficiency_bonus) || "--" },
    { label: "Passive Perception", value: String(asInt(stats.passive_perception, 0) || "--") },
    { label: "Passive Insight", value: String(asInt(stats.passive_insight, 0) || "--") },
    { label: "Passive Investigation", value: String(asInt(stats.passive_investigation, 0) || "--") },
  ];
  return {
    overviewStats,
    overviewStatRows: [overviewStats.slice(0, 4), overviewStats.slice(4, 8), overviewStats.slice(8, 12)],
  };
}

const ABILITY_LABELS: Record<string, { abbr: string; name: string }> = {
  str: { abbr: "STR", name: "Strength" },
  dex: { abbr: "DEX", name: "Dexterity" },
  con: { abbr: "CON", name: "Constitution" },
  int: { abbr: "INT", name: "Intelligence" },
  wis: { abbr: "WIS", name: "Wisdom" },
  cha: { abbr: "CHA", name: "Charisma" },
};

const SKILL_ABILITY_LOOKUP: Record<string, string> = {
  acrobatics: "dex",
  animal_handling: "wis",
  arcana: "int",
  athletics: "str",
  deception: "cha",
  history: "int",
  insight: "wis",
  intimidation: "cha",
  investigation: "int",
  medicine: "wis",
  nature: "int",
  perception: "wis",
  performance: "cha",
  persuasion: "cha",
  religion: "int",
  sleight_of_hand: "dex",
  stealth: "dex",
  survival: "wis",
};

function buildAbilitySkillPresentation(definition: Record<string, unknown>) {
  const abilityScores = asRecord(asRecord(definition.stats).ability_scores);
  const skills = asArray(definition.skills).map(asRecord).map((skill) => {
    const name = asString(skill.name);
    const skillKey = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    const proficiencyLevel = asString(skill.proficiency_level);
    return {
      name,
      bonus: formatModifier(skill.bonus) || asString(skill.bonus),
      proficiency_label: proficiencyLevel ? titleCaseFromKey(proficiencyLevel) : "",
      is_proficient: proficiencyLevel !== "" && proficiencyLevel !== "none",
      ability_key: asString(skill.ability_key) || SKILL_ABILITY_LOOKUP[skillKey] || "",
    };
  });
  const skillsByAbility = new Map<string, typeof skills>();
  for (const skill of skills) {
    if (!skillsByAbility.has(skill.ability_key)) {
      skillsByAbility.set(skill.ability_key, []);
    }
    skillsByAbility.get(skill.ability_key)!.push(skill);
  }
  const abilities = Object.entries(ABILITY_LABELS).map(([key, labels]) => {
    const ability = asRecord(abilityScores[key]);
    return {
      key,
      abbr: labels.abbr,
      name: labels.name,
      score: asInt(ability.score, 10),
      modifier: formatModifier(ability.modifier),
      save_bonus: formatModifier(ability.save_bonus),
      skills: skillsByAbility.get(key) || [],
    };
  });
  return { abilities, skills };
}

function buildProficiencyGroups(definition: Record<string, unknown>) {
  const proficiencies = asRecord(definition.proficiencies);
  const groups = [
    { title: "Armor", values_list: asArray(proficiencies.armor).map(asString).filter(Boolean) },
    { title: "Weapons", values_list: asArray(proficiencies.weapons).map(asString).filter(Boolean) },
    { title: "Tools", values_list: asArray(proficiencies.tools).map(asString).filter(Boolean) },
    { title: "Languages", values_list: asArray(proficiencies.languages).map(asString).filter(Boolean) },
  ];
  return groups.filter((group) => group.values_list.length > 0);
}

function buildReferenceSections(definition: Record<string, unknown>) {
  const profile = asRecord(definition.profile);
  const referenceNotes = asRecord(definition.reference_notes);
  const sections = [
    { title: "Biography", markdown: profile.biography_markdown },
    { title: "Personality", markdown: profile.personality_markdown },
    { title: "Additional Notes", markdown: referenceNotes.additional_notes_markdown },
    { title: "Allies and Organizations", markdown: referenceNotes.allies_and_organizations_markdown },
  ];
  for (const custom of asArray(referenceNotes.custom_sections).map(asRecord)) {
    sections.push({ title: asString(custom.title), markdown: custom.body_markdown });
  }
  return sections
    .map((section) => ({ title: asString(section.title), html: renderPlainMarkdownHtml(section.markdown) }))
    .filter((section) => section.title || section.html);
}

function normalizePageRefSlug(value: unknown): string {
  const record = asRecord(value);
  const rawValue = asString(record.slug) || asString(record.page_slug) || asString(record.page_ref) || asString(value);
  return rawValue.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "").trim();
}

function normalizeLookupKey(value: unknown): string {
  return asString(value).replace(/\\/g, "/").replace(/^\/+|\/+$/g, "").toLowerCase();
}

function displayText(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return "";
}

function buildCampaignPageIndex(records: CampaignPageFileRecord[] = []): Map<string, CampaignPageFileRecord> {
  const index = new Map<string, CampaignPageFileRecord>();
  for (const record of records) {
    if (!record.page.is_visible) {
      continue;
    }
    for (const key of [record.page_ref, record.page.route_slug]) {
      const normalized = normalizeLookupKey(key);
      if (normalized && !index.has(normalized)) {
        index.set(normalized, record);
      }
    }
  }
  return index;
}

function mergeLinkedPayload(...records: Record<string, unknown>[]): Record<string, unknown> {
  const merged: Record<string, unknown> = {};
  for (const record of records) {
    const systemsRef = asRecord(record.systems_ref);
    if (Object.keys(systemsRef).length > 0 && Object.keys(asRecord(merged.systems_ref)).length === 0) {
      merged.systems_ref = systemsRef;
    }
    const pageRef = normalizePageRefSlug(record.page_ref);
    if (pageRef && !normalizePageRefSlug(merged.page_ref)) {
      merged.page_ref = record.page_ref;
    }
    for (const key of ["description_markdown", "description_html"]) {
      if (asString(record[key]) && !asString(merged[key])) {
        merged[key] = record[key];
      }
    }
  }
  return merged;
}

function linkedSystemsEntry(
  payload: Record<string, unknown>,
  sources: CharacterDetailPresenterSources,
): CharacterDetailLinkedSystemsEntry | null {
  const slug = normalizeLookupKey(asRecord(payload.systems_ref).slug);
  if (!slug) {
    return null;
  }
  return sources.systemsEntriesBySlug?.get(slug) ?? null;
}

function linkedCampaignPage(
  payload: Record<string, unknown>,
  pageIndex: Map<string, CampaignPageFileRecord>,
): CampaignPageFileRecord | null {
  const pageRef = normalizeLookupKey(normalizePageRefSlug(payload.page_ref));
  return pageRef ? pageIndex.get(pageRef) ?? null : null;
}

function buildLinkedEntryHref(
  campaignSlug: string,
  payload: Record<string, unknown>,
  sources: CharacterDetailPresenterSources,
  pageIndex: Map<string, CampaignPageFileRecord>,
): string {
  const systemsRef = asRecord(payload.systems_ref);
  const explicitSystemsHref = asString(systemsRef.href);
  if (explicitSystemsHref) {
    return explicitSystemsHref;
  }
  const systemsSlug = asString(systemsRef.slug) || linkedSystemsEntry(payload, sources)?.slug || "";
  if (systemsSlug) {
    return campaignHref(campaignSlug, `systems/entries/${systemsSlug}`);
  }
  const explicitPageHref = asString(asRecord(payload.page_ref).href);
  if (explicitPageHref) {
    return explicitPageHref;
  }
  const page = linkedCampaignPage(payload, pageIndex);
  const pageSlug = page?.page.route_slug || normalizePageRefSlug(payload.page_ref);
  return pageSlug ? campaignHref(campaignSlug, `pages/${pageSlug}`) : "";
}

function itemPropertyRows(entry: CharacterDetailLinkedSystemsEntry): Array<[string, string]> {
  if (entry.entry_type !== "item") {
    return [];
  }
  const metadata = asRecord(entry.metadata);
  const armor = asRecord(metadata.armor);
  const rows: Array<[string, string]> = [];
  const properties = asArray(metadata.properties || metadata.property).map(asString).filter(Boolean);
  const weaponCategory = asString(metadata.weapon_category);
  const weaponType = displayText(metadata.weapon_type || metadata.type);
  const damage = displayText(metadata.damage);
  const versatileDamage = displayText(metadata.versatile_damage);
  const range = displayText(metadata.range);
  const armorClass = displayText(metadata.armor_class) || displayText(metadata.ac) || displayText(armor.ac);

  if (weaponCategory) {
    rows.push(["Weapon Category", titleCaseFromKey(weaponCategory)]);
  }
  if (weaponType) {
    rows.push(["Weapon Type", weaponType]);
  }
  if (damage) {
    rows.push(["Damage", damage]);
  }
  if (versatileDamage) {
    rows.push(["Versatile Damage", versatileDamage]);
  }
  if (range) {
    rows.push(["Range", range]);
  }
  if (properties.length > 0) {
    rows.push(["Weapon Properties", properties.join(", ")]);
  }
  if (armorClass) {
    rows.push(["Armor Class", armorClass]);
  }
  return rows;
}

function buildItemPropertiesHtml(entry: CharacterDetailLinkedSystemsEntry): string {
  const rows = itemPropertyRows(entry);
  if (rows.length === 0) {
    return "";
  }
  const rowHtml = rows
    .map(([label, value]) => `<li><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></li>`)
    .join("");
  return `<div class="item-property-summary"><h5>Item properties</h5><ul class="plain-list slot-list">${rowHtml}</ul></div>`;
}

function resolveLinkedEntryDescriptionHtml(
  payload: Record<string, unknown>,
  sources: CharacterDetailPresenterSources,
  pageIndex: Map<string, CampaignPageFileRecord>,
): string {
  const descriptionMarkdown = asString(payload.description_markdown);
  if (descriptionMarkdown) {
    return renderPlainMarkdownHtml(descriptionMarkdown);
  }
  const systemsEntry = linkedSystemsEntry(payload, sources);
  if (systemsEntry) {
    return asString(systemsEntry.rendered_html);
  }
  const page = linkedCampaignPage(payload, pageIndex);
  return page ? renderPlainMarkdownHtml(page.body_markdown) : "";
}

function resolveItemDescriptionHtml(
  payload: Record<string, unknown>,
  sources: CharacterDetailPresenterSources,
  pageIndex: Map<string, CampaignPageFileRecord>,
): string {
  const descriptionMarkdown = asString(payload.description_markdown);
  if (descriptionMarkdown) {
    return renderPlainMarkdownHtml(descriptionMarkdown);
  }
  const systemsEntry = linkedSystemsEntry(payload, sources);
  if (systemsEntry) {
    return `${buildItemPropertiesHtml(systemsEntry)}${asString(systemsEntry.rendered_html)}`;
  }
  return resolveLinkedEntryDescriptionHtml(payload, sources, pageIndex);
}

function inventoryStateRows(definition: Record<string, unknown>, state: Record<string, unknown>): Record<string, unknown>[] {
  const stateRows = asArray(state.inventory).map(asRecord);
  if (stateRows.length > 0) {
    return stateRows;
  }
  return asArray(definition.equipment_catalog).map(asRecord).map((item) => ({
    ...item,
    quantity: nonNegativeInt(item.quantity ?? item.default_quantity, 1),
    catalog_ref: asString(item.catalog_ref) || asString(item.id),
  }));
}

function buildInventoryPresentation(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
  campaignSlug: string,
  sources: CharacterDetailPresenterSources,
  pageIndex: Map<string, CampaignPageFileRecord>,
) {
  const catalogById = new Map(asArray(definition.equipment_catalog).map(asRecord).map((item) => [asString(item.id), item]));
  return inventoryStateRows(definition, state).map((row) => {
    const id = asString(row.id);
    const catalogRef = asString(row.catalog_ref) || id;
    const catalog = catalogById.get(catalogRef) || catalogById.get(id) || {};
    const name = asString(row.name) || asString(catalog.name) || "Item";
    const notes = asString(row.notes) || asString(catalog.notes);
    const linkedPayload = mergeLinkedPayload(row, catalog);
    return {
      id,
      item_ref: catalogRef,
      name,
      href: buildLinkedEntryHref(campaignSlug, linkedPayload, sources, pageIndex),
      description_html:
        asString(row.description_html) ||
        asString(catalog.description_html) ||
        resolveItemDescriptionHtml(linkedPayload, sources, pageIndex),
      quantity: nonNegativeInt(row.quantity ?? row.current_quantity ?? catalog.default_quantity, 1),
      weight: asString(row.weight) || asString(catalog.weight),
      notes,
      tags: [...new Set([...asArray(catalog.tags), ...asArray(row.tags)].map(asString).filter(Boolean))],
    };
  });
}

function isLikelyWeapon(item: Record<string, unknown>): boolean {
  const haystack = [item.name, item.category, item.item_type, item.type, ...(asArray(item.tags) as unknown[])]
    .map(asString)
    .join(" ")
    .toLowerCase();
  if (
    /(ammunition|arrow|bolt)/.test(haystack) &&
    !/(weapon|crossbow|bow|sword|staff|dagger|axe|mace|spear|hammer|blade)/.test(asString(item.category).toLowerCase())
  ) {
    return false;
  }
  return /(weapon|crossbow|bow|sword|staff|dagger|axe|mace|spear|hammer|blade)/.test(haystack);
}

function buildEquipmentState(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
  campaignSlug: string,
  sources: CharacterDetailPresenterSources,
  pageIndex: Map<string, CampaignPageFileRecord>,
) {
  const stateRows = inventoryStateRows(definition, state);
  const stateByRef = new Map<string, Record<string, unknown>>();
  for (const row of stateRows) {
    const id = asString(row.id);
    const catalogRef = asString(row.catalog_ref) || id;
    if (id) {
      stateByRef.set(id, row);
    }
    if (catalogRef) {
      stateByRef.set(catalogRef, row);
    }
  }
  const attunement = asRecord(state.attunement);
  const attunedRefs = new Set(asArray(attunement.attuned_item_refs).map(asString).filter(Boolean));
  const maxAttunedItems = nonNegativeInt(attunement.max_attuned_items, 3);
  const rows = asArray(definition.equipment_catalog).map(asRecord).map((item) => {
    const id = asString(item.id);
    const stateRow = stateByRef.get(id) || {};
    const itemRef = asString(stateRow.catalog_ref) || id;
    const isEquipped = asBool(stateRow.is_equipped ?? item.is_equipped ?? item.equipped, false);
    const isAttuned = attunedRefs.has(itemRef) || attunedRefs.has(id) || asBool(stateRow.is_attuned ?? item.is_attuned, false);
    const requiresAttunement = asBool(item.requires_attunement ?? item.attunement_required, false);
    const supportsWeaponWieldMode = asBool(item.supports_weapon_wield_mode, false) || isLikelyWeapon(item);
    const weaponWieldMode = asString(stateRow.weapon_wield_mode) || (supportsWeaponWieldMode && isEquipped ? "main_hand" : "");
    const linkedPayload = mergeLinkedPayload(item, stateRow);
    return {
      id,
      name: asString(item.name) || asString(stateRow.name) || "Item",
      quantity: nonNegativeInt(stateRow.quantity ?? item.default_quantity, 1),
      weight: asString(item.weight) || asString(stateRow.weight),
      notes: asString(stateRow.notes) || asString(item.notes),
      tags: asArray(item.tags).map(asString).filter(Boolean),
      href: buildLinkedEntryHref(campaignSlug, linkedPayload, sources, pageIndex),
      description_html:
        asString(item.description_html) ||
        asString(stateRow.description_html) ||
        resolveItemDescriptionHtml(linkedPayload, sources, pageIndex),
      source_label: asString(item.source_label) || asString(asRecord(item.systems_ref).source_label) || "Character sheet",
      is_equipped: isEquipped,
      equipped_label: isEquipped ? "Equipped" : "Not equipped",
      is_attuned: isAttuned,
      requires_attunement: requiresAttunement,
      supports_attunement: requiresAttunement,
      supports_weapon_wield_mode: supportsWeaponWieldMode,
      weapon_wield_mode: weaponWieldMode,
      weapon_wield_options: [
        { value: "main_hand", label: "Main Hand" },
        { value: "off_hand", label: "Off Hand" },
        { value: "two_handed", label: "Two-Handed" },
      ],
      attunement_hint: requiresAttunement ? "Requires attunement" : "",
    };
  });
  const equipmentItemRefs = rows.map((row) => row.id).filter(Boolean);
  const attunableItemRefs = rows.filter((row) => row.supports_attunement).map((row) => row.id).filter(Boolean);
  const attunedCount = rows.filter((row) => row.is_attuned).length;
  const arcaneArmorState = buildEmptyArcaneArmorState();
  return {
    rows,
    attuned_count: attunedCount,
    equipped_count: rows.filter((row) => row.is_equipped || row.weapon_wield_mode).length,
    max_attuned_items: maxAttunedItems,
    equipment_item_refs: equipmentItemRefs,
    attunable_item_refs: attunableItemRefs,
    at_attunement_limit: attunedCount >= maxAttunedItems,
    over_attunement_limit: attunedCount > maxAttunedItems,
    arcane_armor_state: arcaneArmorState,
  };
}

function spellLevelLabel(spell: Record<string, unknown>): string {
  const explicit = asString(spell.level_label);
  if (explicit) {
    return explicit;
  }
  const level = asInt(spell.level, -1);
  if (level === 0) {
    return "Cantrip";
  }
  if (level > 0) {
    return `${level}${level === 1 ? "st" : level === 2 ? "nd" : level === 3 ? "rd" : "th"} level`;
  }
  return "Spell";
}

function buildSpellPresentation(
  definition: Record<string, unknown>,
  campaignSlug: string,
  sources: CharacterDetailPresenterSources,
  pageIndex: Map<string, CampaignPageFileRecord>,
) {
  const spellcasting = asRecord(definition.spellcasting);
  const rawSpells = asArray(spellcasting.spells).map(asRecord);
  const spells = rawSpells.map((spell) => {
    const linkedPayload = mergeLinkedPayload(spell);
    return {
      name: asString(spell.name) || "Spell",
      href: buildLinkedEntryHref(campaignSlug, linkedPayload, sources, pageIndex),
      description_html: asString(spell.description_html) || resolveLinkedEntryDescriptionHtml(linkedPayload, sources, pageIndex),
      level_label: spellLevelLabel(spell),
      school: asString(spell.school),
      casting_time: asString(spell.casting_time),
      range: asString(spell.range),
      duration: asString(spell.duration),
      components: asString(spell.components),
      save_or_hit: asString(spell.save_or_hit),
      source: asString(spell.source),
      reference: asString(spell.reference),
      ...(asString(spell.at_higher_levels) ? { at_higher_levels: asString(spell.at_higher_levels) } : {}),
      badges: [
        asBool(spell.always_prepared, false) ? "Always prepared" : "",
        asBool(spell.prepared, false) ? "Prepared" : "",
        asString(spell.source_package_label),
      ].filter(Boolean),
      class_row_id: asString(spell.class_row_id),
      management_note: asString(spell.management_note),
    };
  });
  const section = {
    class_row_id: asString(asRecord(asArray(spellcasting.class_rows)[0]).id),
    title: asString(spellcasting.spellcasting_class) || "Spellcasting",
    spells,
    spell_level_sections: [
      {
        title: "Current spells",
        groups: Object.entries(
          spells.reduce<Record<string, typeof spells>>((groups, spell) => {
            groups[spell.level_label] ??= [];
            groups[spell.level_label].push(spell);
            return groups;
          }, {}),
        ).map(([title, groupedSpells]) => ({ title, spells: groupedSpells })),
      },
    ],
  };
  return {
    spellcasting_class: asString(spellcasting.spellcasting_class),
    spellcasting_ability: asString(spellcasting.spellcasting_ability),
    spell_save_dc: spellcasting.spell_save_dc ?? null,
    spell_attack_bonus: asString(spellcasting.spell_attack_bonus) || formatModifier(spellcasting.spell_attack_bonus),
    current_row_sections: spells.length ? [section] : [],
    row_sections: spells.length ? [section] : [],
  };
}

const XIANXIA_ENERGY_LABELS: Record<string, string> = { jing: "Jing", qi: "Qi", shen: "Shen" };
const XIANXIA_CURRENCY_LABELS: Record<string, string> = {
  coin: "Coin",
  supply: "Supply",
  spirit_stones: "Spirit Stones",
};

function xianxiaPool(key: string, label: string, current: unknown, max: unknown, temp?: unknown) {
  return {
    key,
    label,
    current: nonNegativeInt(current, nonNegativeInt(max, 0)),
    max: nonNegativeInt(max, 0),
    ...(nonNegativeInt(temp, 0) > 0 ? { temp: nonNegativeInt(temp, 0) } : {}),
  };
}

function xianxiaInventoryRows(definition: Record<string, unknown>, state: Record<string, unknown>) {
  const xianxiaState = asRecord(state.xianxia);
  const stateInventory = asRecord(xianxiaState.inventory);
  const rows = asArray(stateInventory.quantities).length
    ? asArray(stateInventory.quantities)
    : asArray(state.inventory).length
      ? asArray(state.inventory)
      : asArray(asRecord(definition.xianxia).inventory);
  return rows.map(asRecord).map((item) => ({
    id: asString(item.id) || asString(item.item_ref) || asString(item.name).toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    name: asString(item.name) || "Item",
    quantity: nonNegativeInt(item.quantity, 1),
    item_nature: asString(item.item_nature) || asString(item.nature),
    item_type: asString(item.item_type) || asString(item.type),
    notes: asString(item.notes),
    tags: asArray(item.tags).map(asString).filter(Boolean),
    catalog_ref: asString(item.catalog_ref),
    equippable: asBool(item.equippable, false),
    is_equipped: asBool(item.is_equipped ?? item.equipped, false),
    systems_ref: Object.keys(asRecord(item.systems_ref)).length ? asRecord(item.systems_ref) : null,
  }));
}

function buildXianxiaPresentation(definition: Record<string, unknown>, state: Record<string, unknown>) {
  const xianxia = asRecord(definition.xianxia);
  if (normalizeSystemKey(definition.system) !== "xianxia" && Object.keys(xianxia).length === 0) {
    return {};
  }
  const xianxiaState = asRecord(state.xianxia);
  const xianxiaVitals = asRecord(xianxiaState.vitals);
  const durability = asRecord(xianxia.durability);
  const energies = asRecord(xianxiaState.energies);
  const energyMaxima = asRecord(xianxia.energy_maxima);
  const yinYangState = asRecord(xianxiaState.yin_yang);
  const yinYangDefinition = asRecord(xianxia.yin_yang);
  const daoState = asRecord(xianxiaState.dao);
  const insight = asRecord(xianxia.insight);
  const inventory = xianxiaInventoryRows(definition, state);
  const currency = asRecord(xianxiaState.currency);
  const daoImmolating = asRecord(xianxia.dao_immolating_techniques);
  const activeStance = asRecord(xianxiaState.active_stance);
  const activeAura = asRecord(xianxiaState.active_aura);
  const realm = asString(xianxia.realm) || "Mortal";
  const actionsPerTurn = nonNegativeInt(xianxia.actions_per_turn, realm === "Divine" ? 4 : realm === "Immortal" ? 3 : 2);
  const manualArmorBonus = asInt(durability.manual_armor_bonus ?? xianxia.manual_armor_bonus, 0);
  const defense = asInt(durability.defense ?? xianxia.defense, 10 + manualArmorBonus);
  const attributes = asRecord(xianxia.attributes);
  const efforts = asRecord(xianxia.efforts);
  return {
    system_label: "Xianxia",
    subpages: [
      { slug: "overview", label: "Quick Reference" },
      { slug: "martial_arts", label: "Martial Arts" },
      { slug: "techniques", label: "Techniques" },
      { slug: "resources", label: "Resources" },
      { slug: "skills", label: "Skills" },
      { slug: "equipment", label: "Equipment" },
      { slug: "inventory", label: "Inventory" },
      { slug: "personal", label: "Personal" },
      { slug: "notes", label: "Notes" },
    ],
    identity: {
      realm,
      actions_per_turn: actionsPerTurn,
      honor: asString(xianxia.honor) || asString(xianxia.honor_rank),
      reputation: asString(xianxia.reputation),
    },
    attributes: Object.entries(attributes).map(([key, value]) => ({
      key,
      label: titleCaseFromKey(key),
      score: asInt(value, asInt(asRecord(value).score, 0)),
    })),
    efforts: Object.entries(efforts).map(([key, value]) => ({
      key,
      label: titleCaseFromKey(key),
      score: asInt(value, asInt(asRecord(value).score, 0)),
      damage: asString(asRecord(value).damage),
    })),
    resources: {
      durability: [
        xianxiaPool("hp", "HP", xianxiaVitals.current_hp ?? asRecord(state.vitals).current_hp, durability.hp_max ?? xianxia.hp_max, xianxiaVitals.temp_hp),
        xianxiaPool("stance", "Stance", xianxiaVitals.current_stance, durability.stance_max ?? xianxia.stance_max, xianxiaVitals.temp_stance),
      ],
      energies: Object.entries(XIANXIA_ENERGY_LABELS).map(([key, label]) =>
        xianxiaPool(key, label, asRecord(energies[key]).current, asRecord(xianxia.energies)[key] ?? energyMaxima[key]),
      ),
      yin_yang: [
        xianxiaPool("yin", "Yin", yinYangState.yin_current, yinYangDefinition.yin_max ?? xianxia.yin_max),
        xianxiaPool("yang", "Yang", yinYangState.yang_current, yinYangDefinition.yang_max ?? xianxia.yang_max),
      ],
      dao: { current: nonNegativeInt(daoState.current ?? xianxiaState.dao_current, 0), max: nonNegativeInt(xianxia.dao_max, 3) },
      insight: { available: nonNegativeInt(insight.available, 0), spent: nonNegativeInt(insight.spent, 0) },
    },
    skills: {
      trained: asArray(xianxia.trained_skills).map(asString).filter(Boolean).map((name) => ({ name })),
    },
    equipment: {
      manual_armor_bonus: manualArmorBonus,
      defense,
      equipped_items: inventory.filter((item) => item.is_equipped),
      equipped_weapons: inventory.filter((item) => item.is_equipped && /weapon|sword|jian|bow|staff/i.test(`${item.item_type} ${item.name}`)),
      equipped_armor: inventory.filter((item) => item.is_equipped && /armor/i.test(`${item.item_type} ${item.name}`)),
      equipped_artifacts: inventory.filter((item) => item.is_equipped && /artifact/i.test(`${item.item_nature} ${item.item_type}`)),
      necessary_weapons: asArray(xianxia.necessary_weapons).map(asString).filter(Boolean).map((name) => ({ name })),
      necessary_tools: asArray(xianxia.necessary_tools).map(asString).filter(Boolean).map((name) => ({ name })),
    },
    martial_arts: asArray(xianxia.martial_arts).map(asRecord).map((art) => ({
      name: asString(art.name) || "Martial Art",
      current_rank_label: asString(art.current_rank) || asString(art.rank),
      source_label: asString(art.source_label),
      notes: asString(art.notes),
    })),
    generic_techniques: asArray(xianxia.generic_techniques).map(asRecord).map((technique) => ({
      name: asString(technique.name) || "Technique",
      status_label: asString(technique.status_label) || asString(technique.approval_status),
      notes: asString(technique.notes),
      insight_cost: nonNegativeInt(technique.insight_cost, 0),
    })),
    basic_actions: [],
    inventory: {
      enabled: true,
      currency: Object.entries(XIANXIA_CURRENCY_LABELS).map(([key, label]) => ({
        key,
        label,
        amount: nonNegativeInt(currency[key], 0),
      })),
      quantities: inventory,
    },
    approval: {
      variants: asArray(xianxia.variants).map(asRecord),
      dao_immolating_prepared: asArray(daoImmolating.prepared).map(asRecord).map((record, index) => ({
        name: asString(record.name) || "Prepared note",
        notes: asString(record.notes),
        prepared_record_index: index,
      })),
      dao_immolating_use_history: asArray(daoImmolating.use_history).map(asRecord).map((record, index) => ({
        name: asString(record.name) || "Dao Immolating use",
        status_key: asString(record.approval_status) || asString(record.status_key),
        status_label: titleCaseFromKey(asString(record.approval_status) || asString(record.status_key)),
        approval_notes: asString(record.approval_notes),
        insight_cost: nonNegativeInt(record.insight_cost, 10),
        insight_spent: nonNegativeInt(record.insight_spent, 0),
        used: asBool(record.used, false),
        use_notes: asString(record.use_notes),
        use_record_index: index,
      })),
      approval_requests: asArray(xianxia.approval_requests).map(asRecord),
      status_groups: [
        {
          key: "dao_immolating_use_records",
          title: "Dao Immolating Use Records",
          empty_message: "No Dao Immolating use records.",
          records: asArray(daoImmolating.use_history).map(asRecord).map((record, index) => ({
            name: asString(record.name) || "Dao Immolating use",
            status_key: asString(record.approval_status) || asString(record.status_key),
            status_label: titleCaseFromKey(asString(record.approval_status) || asString(record.status_key)),
            approval_notes: asString(record.approval_notes),
            insight_cost: nonNegativeInt(record.insight_cost, 10),
            insight_spent: nonNegativeInt(record.insight_spent, 0),
            used: asBool(record.used, false),
            use_notes: asString(record.use_notes),
            use_record_index: index,
          })),
        },
      ],
    },
    active_state: {
      stance: {
        label: "Active Stance",
        name: asString(activeStance.name),
        status_label: asString(activeStance.name) ? `Active Stance: ${asString(activeStance.name)}` : "No active Stance",
      },
      aura: {
        label: "Active Aura",
        name: asString(activeAura.name),
        status_label: asString(activeAura.name) ? `Active Aura: ${asString(activeAura.name)}` : "No active Aura",
      },
    },
    quick_reference: {
      actions: { realm, actions_per_turn: String(actionsPerTurn), formula: "Realm-based action count" },
      defense: { base: 10, manual_armor_bonus: manualArmorBonus, value: defense, formula: "10 + manual armor bonus + modeled bonuses" },
      check_formula: {
        formula: "d20 + Attribute + Effort",
        spend_bonus: "+1 per relevant spend",
        summary: "Roll d20 plus the relevant Attribute and Effort.",
      },
    },
  };
}

export function buildCharacterDetailPayload({
  campaign,
  record,
  stateRecord,
  assetByRef,
  permissions,
  controls,
  campaignPageRecords = [],
  systemsEntriesBySlug = new Map(),
}: {
  campaign: CampaignViewModel;
  record: CampaignCharacterFileRecord;
  stateRecord: CharacterStateSnapshot;
  assetByRef: Map<string, CampaignAssetFileRecord>;
  permissions: CharacterDetailPermissions;
  controls: CharacterDetailControls | null;
  campaignPageRecords?: CampaignPageFileRecord[];
  systemsEntriesBySlug?: Map<string, CharacterDetailLinkedSystemsEntry>;
}) {
  const state = asRecord(stateRecord.state);
  const definition = record.definition;
  const systemKey = normalizeSystemKey(definition.system);
  const presenterSources = { campaignPageRecords, systemsEntriesBySlug };
  const pageIndex = buildCampaignPageIndex(campaignPageRecords);
  const equipmentState = systemKey === "xianxia"
    ? buildEmptyEquipmentState()
    : buildEquipmentState(definition, state, campaign.slug, presenterSources, pageIndex);
  const arcaneArmorState = equipmentState.arcane_armor_state;
  const notes = asRecord(state.notes);
  const overview = buildOverviewStats(definition, state);
  const abilitySkillPresentation = buildAbilitySkillPresentation(definition);
  const personalBackgroundMarkdown = asString(notes.background_markdown ?? notes.personal_background_markdown);
  return {
    ok: true,
    character: {
      definition: record.definition,
      import_metadata: record.import_metadata,
      state_record: {
        campaign_slug: campaign.slug,
        character_slug: record.character_slug,
        revision: stateRecord.revision,
        state: stateRecord.state,
        updated_at: stateRecord.updated_at ?? null,
        updated_by_user_id: stateRecord.updated_by_user_id ?? null,
      },
      permissions,
      controls,
      portrait: buildCharacterPortraitPayload(campaign.slug, record, assetByRef),
      overview_stat_rows: overview.overviewStatRows,
      overview_stats: overview.overviewStats,
      player_notes_markdown: asString(notes.player_notes_markdown),
      player_notes_html: renderPlainMarkdownHtml(notes.player_notes_markdown),
      physical_description_markdown: asString(notes.physical_description_markdown),
      physical_description_html: renderPlainMarkdownHtml(notes.physical_description_markdown),
      personal_background_markdown: personalBackgroundMarkdown,
      personal_background_html: renderPlainMarkdownHtml(personalBackgroundMarkdown),
      reference_sections: buildReferenceSections(definition),
      abilities: abilitySkillPresentation.abilities,
      skills: abilitySkillPresentation.skills,
      proficiency_groups: buildProficiencyGroups(definition),
      presented_inventory: systemKey === "xianxia" ? [] : buildInventoryPresentation(definition, state, campaign.slug, presenterSources, pageIndex),
      presented_spellcasting: systemKey === "xianxia" ? {} : buildSpellPresentation(definition, campaign.slug, presenterSources, pageIndex),
      presented_xianxia: buildXianxiaPresentation(definition, state),
      equipment_state: equipmentState,
      arcane_armor_state: arcaneArmorState,
    },
    links: {
      gen2_roster_url: campaignHref(campaign.slug, "characters"),
      flask_roster_url: flaskCampaignHref(campaign.slug, "characters"),
      gen2_character_url: campaignHref(campaign.slug, `characters/${record.character_slug}`),
      flask_character_url: flaskCampaignHref(campaign.slug, `characters/${record.character_slug}`),
    },
  };
}

export function buildCharacterRosterPayload({
  campaign,
  records,
  stateBySlug,
  assetByRef,
  query,
  canManageSession,
}: {
  campaign: CampaignViewModel;
  records: CampaignCharacterFileRecord[];
  stateBySlug: Map<string, CharacterStateSnapshot>;
  assetByRef: Map<string, CampaignAssetFileRecord>;
  query: string;
  canManageSession: boolean;
}) {
  const characterCards = records
    .map((record) => {
      const definition = record.definition;
      const profile = asRecord(definition.profile);
      const stats = asRecord(definition.stats);
      const snapshot = stateBySlug.get(record.character_slug) ?? { revision: 1, state: {} };
      const vitals = asRecord(snapshot.state.vitals);
      const classLevelText = profileClassLevelText(profile);
      const species = asString(profile.species);
      const background = asString(profile.background);
      const name = asString(definition.name) || record.character_slug;
      const searchText = [name, profileClassLevelText(profile, ""), species, background]
        .filter((item) => item.length > 0)
        .join(" ")
        .toLowerCase();
      return {
        slug: record.character_slug,
        name,
        status: asString(definition.status),
        class_level_text: classLevelText,
        species,
        background,
        system: asString(definition.system),
        href: campaignHref(campaign.slug, `characters/${record.character_slug}`),
        flask_href: flaskCampaignHref(campaign.slug, `characters/${record.character_slug}`),
        search_text: searchText,
        current_hp: asInt(vitals.current_hp, 0),
        max_hp: asInt(stats.max_hp, 0),
        temp_hp: asInt(vitals.temp_hp, 0),
        hit_dice: buildHitDiceSummary(definition, snapshot.state),
        resource_preview: buildResourcePreview(snapshot.state),
        portrait: buildCharacterPortraitPayload(campaign.slug, record, assetByRef),
        revision: snapshot.revision,
      };
    })
    .filter((card) => (query ? card.search_text.includes(query.toLowerCase()) : true));

  const systemKey = normalizeSystemKey(campaign.system);
  const characterCreateLane = systemKey === "xianxia" ? "xianxia" : systemKey === "dnd5e" ? "dnd5e" : "";
  const nativeCharacterCreateSupported = Boolean(characterCreateLane);
  const nativeCharacterToolsSupported = systemKey === "dnd5e";
  const canCreateCharacters = canManageSession && nativeCharacterCreateSupported;
  const canImportXianxiaCharacters = canCreateCharacters && characterCreateLane === "xianxia";
  return {
    ok: true,
    campaign,
    characters: characterCards,
    query,
    result_count: characterCards.length,
    tools: {
      can_create_characters: canCreateCharacters,
      can_import_xianxia_characters: canImportXianxiaCharacters,
      native_character_tools_supported: nativeCharacterToolsSupported,
      native_character_create_supported: nativeCharacterCreateSupported,
      character_create_lane: characterCreateLane,
    },
    links: {
      flask_roster_url: flaskCampaignHref(campaign.slug, "characters"),
      gen2_roster_url: campaignHref(campaign.slug, "characters"),
      ...(canCreateCharacters
        ? {
            flask_create_character_url: flaskCampaignHref(campaign.slug, "characters/new"),
            create_character_url: campaignHref(campaign.slug, "characters/new"),
          }
        : {}),
      ...(canImportXianxiaCharacters
        ? {
            flask_import_xianxia_url: flaskCampaignHref(campaign.slug, "characters/import/xianxia-manual"),
            import_xianxia_url: campaignHref(campaign.slug, "characters/import/xianxia-manual"),
          }
        : {}),
    },
  };
}

function buildContentCharacterSummaryPayload(record: CampaignCharacterFileRecord) {
  return {
    character_slug: record.character_slug,
    updated_at: record.updated_at,
    name: recordString(record.definition, "name"),
    status: recordString(record.definition, "status"),
    import_status: recordString(record.import_metadata, "import_status"),
  };
}

export function buildContentCharacterListPayload(
  records: CampaignCharacterFileRecord[],
): { ok: true; characters: ReturnType<typeof buildContentCharacterSummaryPayload>[] } {
  return {
    ok: true,
    characters: records.map(buildContentCharacterSummaryPayload),
  };
}

export function buildContentCharacterDetailPayload(
  record: CampaignCharacterFileRecord,
): {
  ok: true;
  character_file: {
    character_slug: string;
    updated_at: string;
    definition: Record<string, unknown>;
    import_metadata: Record<string, unknown>;
    state_created: boolean;
  };
} {
  return {
    ok: true,
    character_file: {
      character_slug: record.character_slug,
      updated_at: record.updated_at,
      definition: record.definition,
      import_metadata: record.import_metadata,
      state_created: record.state_created,
    },
  };
}

export function buildContentCharacterDeletePayload(
  deleted: DeletedCharacterContent,
): {
  ok: true;
  deleted: DeletedCharacterContent;
} {
  return {
    ok: true,
    deleted,
  };
}

function buildContentAssetFilePayload(
  campaignSlug: string,
  record: CampaignAssetFileRecord,
  includeData: boolean,
) {
  const payload: {
    asset_ref: string;
    relative_path: string;
    size_bytes: number;
    media_type: string;
    updated_at: string;
    url: string;
    data_base64?: string;
  } = {
    asset_ref: record.asset_ref,
    relative_path: record.relative_path,
    size_bytes: record.size_bytes,
    media_type: record.media_type,
    updated_at: record.updated_at,
    url: `/campaigns/${campaignSlug}/assets/${record.asset_ref}`,
  };

  if (includeData) {
    payload.data_base64 = record.data_base64 || "";
  }
  return payload;
}

export function buildContentAssetListPayload(
  campaignSlug: string,
  records: CampaignAssetFileRecord[],
): { ok: true; assets: ReturnType<typeof buildContentAssetFilePayload>[] } {
  return {
    ok: true,
    assets: records.map((record) => buildContentAssetFilePayload(campaignSlug, record, false)),
  };
}

export function buildContentAssetDetailPayload(
  campaignSlug: string,
  record: CampaignAssetFileRecord,
): { ok: true; asset_file: ReturnType<typeof buildContentAssetFilePayload> } {
  return {
    ok: true,
    asset_file: buildContentAssetFilePayload(campaignSlug, record, true),
  };
}

export function buildContentAssetWritePayload(
  campaignSlug: string,
  record: CampaignAssetFileRecord,
): { ok: true; asset_file: ReturnType<typeof buildContentAssetFilePayload> } {
  return {
    ok: true,
    asset_file: buildContentAssetFilePayload(campaignSlug, record, false),
  };
}

export function buildContentAssetDeletePayload(
  record: CampaignAssetFileRecord,
): { ok: true; deleted: { asset_ref: string; relative_path: string } } {
  return {
    ok: true,
    deleted: {
      asset_ref: record.asset_ref,
      relative_path: record.relative_path,
    },
  };
}

function buildContentPageFilePayload(
  record: CampaignPageFileRecord,
  includeBody: boolean,
  removalSafety?: ContentPageRemovalSafety,
): ContentPagePayload {
  const payload = withVisibilityDefaults(record);
  payload.removal_safety = normalizeRemovalSafety(record, removalSafety);
  payload.can_hard_delete = payload.removal_safety.can_hard_delete;
  payload.hard_delete_blockers = [...payload.removal_safety.hard_delete_blockers];
  payload.removal_status_label = payload.removal_safety.removal_status_label;
  payload.removal_guidance = payload.removal_safety.removal_guidance;

  if (includeBody) {
    payload.body_markdown = record.body_markdown;
  } else {
    delete payload.body_markdown;
  }
  return payload;
}

export function buildContentPageListPayload(
  records: CampaignPageFileRecord[],
  removalSafety?: Record<string, ContentPageRemovalSafety>,
): { ok: true; pages: ContentPagePayload[] } {
  return {
    ok: true,
    pages: records.map((record) =>
      buildContentPageFilePayload(record, false, removalSafety?.[record.page_ref]),
    ),
  };
}

export function buildContentPageDetailPayload(
  record: CampaignPageFileRecord,
  removalSafety?: ContentPageRemovalSafety,
): { ok: true; page_file: ContentPagePayload } {
  const payload = buildContentPageFilePayload(record, true, removalSafety);
  return {
    ok: true,
    page_file: payload,
  };
}

export function buildContentPageDeletePayload(
  record: CampaignPageFileRecord,
): { ok: true; deleted: { page_ref: string; relative_path: string } } {
  return {
    ok: true,
    deleted: {
      page_ref: record.page_ref,
      relative_path: record.relative_path,
    },
  };
}
