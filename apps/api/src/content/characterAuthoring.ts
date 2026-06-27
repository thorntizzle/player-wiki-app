import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";

type SqliteDatabase = InstanceType<typeof Database>;

interface SystemsSourceAccessRow {
  source_id: string;
  configured_enabled: number | null;
  configured_visibility: string | null;
}

interface SystemsEntryRow {
  library_slug: string;
  source_id: string;
  entry_key: string;
  entry_type: string;
  slug: string;
  title: string;
  metadata_json: string;
  body_json: string;
  is_enabled_override: number | null;
}

const XIANXIA_ATTRIBUTE_KEYS = ["str", "dex", "con", "int", "wis", "cha"] as const;
const XIANXIA_ATTRIBUTE_LABELS: Record<(typeof XIANXIA_ATTRIBUTE_KEYS)[number], string> = {
  str: "Strength",
  dex: "Dexterity",
  con: "Constitution",
  int: "Intelligence",
  wis: "Wisdom",
  cha: "Charisma",
};
const XIANXIA_EFFORT_KEYS = ["basic", "weapon", "guns_explosive", "magic", "ultimate"] as const;
const XIANXIA_EFFORT_LABELS: Record<(typeof XIANXIA_EFFORT_KEYS)[number], string> = {
  basic: "Basic",
  weapon: "Weapon",
  guns_explosive: "Guns/Explosive",
  magic: "Magic",
  ultimate: "Ultimate",
};
const XIANXIA_ENERGY_KEYS = ["jing", "qi", "shen"] as const;
const XIANXIA_ENERGY_LABELS: Record<(typeof XIANXIA_ENERGY_KEYS)[number], string> = {
  jing: "Jing",
  qi: "Qi",
  shen: "Shen",
};
const XIANXIA_YIN_YANG_KEYS = ["yin", "yang"] as const;
const XIANXIA_YIN_YANG_LABELS: Record<(typeof XIANXIA_YIN_YANG_KEYS)[number], string> = {
  yin: "Yin",
  yang: "Yang",
};
const XIANXIA_CURRENCY_KEYS = ["coin", "supply", "spirit_stones"] as const;
const XIANXIA_DEFINITION_FIELD_KEYS = [
  "schema_version",
  "realm",
  "actions_per_turn",
  "honor",
  "reputation",
  "attributes",
  "efforts",
  "energies",
  "yin_yang",
  "dao",
  "insight",
  "durability",
  "skills",
  "equipment",
  "martial_arts",
  "generic_techniques",
  "variants",
  "dao_immolating_techniques",
  "approval_requests",
  "companions",
  "advancement_history",
] as const;
const XIANXIA_MARTIAL_ART_IMPORT_RANKS = [
  { key: "initiate", label: "Initiate" },
  { key: "novice", label: "Novice" },
  { key: "apprentice", label: "Apprentice" },
  { key: "master", label: "Master" },
  { key: "legendary", label: "Legendary" },
] as const;
const XIANXIA_MARTIAL_ART_RANK_ORDER = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key);
const XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS = Object.fromEntries(
  XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => [rank.key, rank.label]),
) as Record<string, string>;
const XIANXIA_REALM_ACTIONS: Record<string, number> = {
  mortal: 2,
  immortal: 3,
  divine: 4,
};
const XIANXIA_ITEM_TYPE_DEFAULT = "Miscellaneous";
const XIANXIA_ITEM_TYPE_ALIASES: Record<string, string> = {
  weapon: "Weapon",
  weapons: "Weapon",
  blade: "Weapon",
  blade_weapon: "Weapon",
  armor: "Armor",
  armour: "Armor",
  armors: "Armor",
  armours: "Armor",
  artifact: "Artifact",
  artifacts: "Artifact",
  relic: "Artifact",
  relics: "Artifact",
  consumable: "Consumable",
  consumables: "Consumable",
  tool: "Miscellaneous",
  tools: "Miscellaneous",
  treasure: "Miscellaneous",
  misc: "Miscellaneous",
  miscellaneous: "Miscellaneous",
  misc_item: "Miscellaneous",
};
const XIANXIA_ITEM_NATURE_ALIASES: Record<string, string> = {
  mundane: "Mundane",
  relic: "Relic",
  relics: "Relic",
  re_lic: "Relic",
};
const XIANXIA_INVENTORY_TAG_TYPE_ALIASES: Record<string, string> = {
  weapon: "Weapon",
  weapons: "Weapon",
  blade: "Weapon",
  blade_weapon: "Weapon",
  armor: "Armor",
  armour: "Armor",
  armors: "Armor",
  armours: "Armor",
  artifact: "Artifact",
  artifacts: "Artifact",
  relic: "Artifact",
  relics: "Artifact",
  consumable: "Consumable",
  consumables: "Consumable",
  treasure: "Miscellaneous",
  tool: "Miscellaneous",
  tools: "Miscellaneous",
  equipment: "Miscellaneous",
};
const XIANXIA_MANUAL_IMPORTER_SOURCE_PATH = "importer://xianxia-manual";
const XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE = "xianxia_manual_importer";
const XIANXIA_MANUAL_IMPORTER_VERSION = "2026-05-13.0";
const XIANXIA_MANUAL_IMPORTER_IMPORTED_FROM = "Manual Xianxia character importer";
const XIANXIA_CHARACTER_CREATE_SOURCE_PATH = "builder://xianxia-create";
const XIANXIA_CHARACTER_CREATE_SOURCE_TYPE = "xianxia_character_builder";
const XIANXIA_CHARACTER_CREATE_VERSION = "2026-04-26.06";
const XIANXIA_CHARACTER_CREATE_IMPORTED_FROM = "In-app Xianxia Character Creator";
const XIANXIA_ATTRIBUTE_CREATION_POINTS = 6;
const XIANXIA_ATTRIBUTE_MAX_AT_CREATION = 3;
const XIANXIA_EFFORT_CREATION_POINTS = 5;
const XIANXIA_EFFORT_MAX_AT_CREATION = 3;
const XIANXIA_ENERGY_CREATION_POINTS = 3;
const XIANXIA_TRAINED_SKILL_COUNT = 3;
const XIANXIA_DAO_DEFAULT_MAX = 3;
const XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST = 1;
const XIANXIA_MEDITATION_INSIGHT_COST = 1;
const XIANXIA_CONDITIONING_INSIGHT_COST = 1;
const XIANXIA_CONDITIONING_HP_INCREASE = 10;
const XIANXIA_CONDITIONING_HP_MAXIMUM = 50;
const XIANXIA_CONDITIONING_EFFORT_INCREASE = 2;
const XIANXIA_TRAINING_INSIGHT_COST = 1;
const XIANXIA_TRAINING_STANCE_INCREASE = 10;
const XIANXIA_TRAINING_STANCE_MAXIMUM = 50;
const XIANXIA_TRAINING_ATTRIBUTE_INCREASE = 2;
const XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS = new Set(["cultivation", "meditation", "conditioning", "training"]);
const XIANXIA_REALM_ASCENSION_REALMS = ["Mortal", "Immortal", "Divine"] as const;
const XIANXIA_REALM_ASCENSION_TARGETS: Record<string, Record<string, unknown>> = {
  Mortal: {
    current_realm: "Mortal",
    target_realm: "Immortal",
    seclusion_time: "1 year",
    rebuild_budget: 15,
    stat_cap: 6,
    actions_per_turn: 3,
    stat_max_prerequisite: 10,
  },
  Immortal: {
    current_realm: "Immortal",
    target_realm: "Divine",
    seclusion_time: "100 years",
    rebuild_budget: 25,
    stat_cap: 12,
    actions_per_turn: 4,
    stat_max_prerequisite: 15,
  },
};
const XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS = new Set([
  "realm_ascension_immortal_rebuild_applied",
  "realm_ascension_divine_realm_rebuild_applied",
  "realm_ascension_divine_rebuild_applied",
]);
const XIANXIA_REALM_ASCENSION_TRADE_UNIT = 10;
const NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE =
  "This campaign can still use the character roster, read-mode sheets, session-mode sheets, and Controls. Native DND-5E builder, edit, level-up, repair, retraining, PDF-import, and spellcasting tools are not implemented for this campaign system.";
const XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE =
  "Xianxia advancement and cultivation use their own character lane. Use the Xianxia Cultivation page instead of DND-5E level-up, repair, or retraining routes; remaining unmodeled advancement workflows should be added there.";
const ADVANCED_EDITOR_UNSUPPORTED_MESSAGE =
  "Advanced Editor is currently available only for DND-5E native character tools in Gen2.";
const CULTIVATION_UNSUPPORTED_MESSAGE =
  "Cultivation is only available for Xianxia character sheets.";
const ADVANCED_EDITOR_REFERENCE_FIELD_NAMES = new Set([
  "physical_description_markdown",
  "background_markdown",
  "biography_markdown",
  "personality_markdown",
  "additional_notes_markdown",
  "allies_and_organizations_markdown",
]);
const ADVANCED_EDITOR_STATE_NOTE_FIELD_NAMES = new Set([
  "physical_description_markdown",
  "background_markdown",
]);
const DND_SYSTEMS_OPTION_PREFIX = "systems:";
const DND_PHB_SOURCE_ID = "PHB";
const DND_SUPPORTED_NON_PHB_BASE_CLASSES = new Set(["TCE|artificer"]);
const DND_SUPPORTED_SUBORDINATE_SOURCES = new Set(["TCE", "SCAG", "XGE", "EGW", "DMG"]);
const DND_ABILITY_KEYS = ["str", "dex", "con", "int", "wis", "cha"] as const;
const DND_ABILITY_LABELS: Record<(typeof DND_ABILITY_KEYS)[number], string> = {
  str: "Strength",
  dex: "Dexterity",
  con: "Constitution",
  int: "Intelligence",
  wis: "Wisdom",
  cha: "Charisma",
};
const DND_CREATE_LIMITATIONS = [
  "Base classes come from enabled Systems rows inside the current native support lane: PHB base classes plus TCE Artificer.",
  "Species and backgrounds come from enabled Systems rows in the current supported source matrix for this TypeScript parity slice.",
  "DND-5E submit is limited to the narrow PHB Fighter pilot lane in the TypeScript API; full level-one builder parity remains pending.",
];
const DND_CHARACTER_CREATE_SOURCE_PATH = "builder://dnd5e-create-pilot";
const DND_CHARACTER_CREATE_SOURCE_TYPE = "dnd5e_character_builder_pilot";
const DND_CHARACTER_CREATE_VERSION = "2026-06-27.0";
const DND_CHARACTER_CREATE_IMPORTED_FROM = "In-app DND-5E Character Creator pilot";
const DND_PILOT_CLASS = "fighter";
const DND_PILOT_SPECIES = "human";
const DND_PILOT_BACKGROUND = "soldier";

export interface XianxiaManualImportBuildResult {
  definition: Record<string, unknown>;
  importMetadata: Record<string, unknown>;
  initialState: Record<string, unknown>;
  preview: Record<string, unknown>;
}

export interface XianxiaCreateBuildResult {
  definition: Record<string, unknown>;
  importMetadata: Record<string, unknown>;
  initialState: Record<string, unknown>;
}

export interface DndCreateContext {
  lane: "dnd5e";
  builder_ready: boolean;
  values: Record<string, string>;
  class_options: Array<Record<string, unknown>>;
  species_options: Array<Record<string, unknown>>;
  background_options: Array<Record<string, unknown>>;
  subclass_options: Array<Record<string, unknown>>;
  requires_subclass: boolean;
  choice_sections: Array<Record<string, unknown>>;
  preview: Record<string, unknown>;
  limitations: string[];
}

export interface DndCreateBuildResult {
  definition: Record<string, unknown>;
  importMetadata: Record<string, unknown>;
  initialState?: Record<string, unknown>;
}

export interface CharacterAdvancedEditorPayload {
  lane: "dnd5e" | "unsupported";
  supported: boolean;
  unsupported_message: string;
  links: Record<string, string>;
  editor: {
    state_revision: number;
    reference_fields: Array<Record<string, unknown>>;
    feature_rows: Array<Record<string, unknown>>;
    equipment_rows: Array<Record<string, unknown>>;
  } | null;
}

export type CharacterAdvancedEditorReferenceUpdate =
  | {
      status: "ok";
      definition: Record<string, unknown>;
      stateNoteValues: Record<string, string>;
      values: Record<string, string>;
    }
  | { status: "validation_error"; message: string };

export type CharacterAdvancementRouteKind = "level_up" | "retraining" | "progression_repair";

export interface CharacterAdvancementShellPayload {
  lane: "dnd5e" | "repairable" | "ready" | "unsupported";
  supported: boolean;
  unsupported_message: string;
  readiness: Record<string, unknown>;
  links: Record<string, string>;
  context: Record<string, unknown> | null;
}

export interface CharacterCultivationShellPayload {
  lane: "xianxia" | "unsupported";
  supported: boolean;
  unsupported_message: string;
  links: Record<string, string>;
  cultivation: Record<string, unknown> | null;
}

function normalizeSystemKey(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

export function nativeCharacterCreateLane(system: unknown): "dnd5e" | "xianxia" | "" {
  const systemKey = normalizeSystemKey(system);
  if (systemKey === "dnd5e") {
    return "dnd5e";
  }
  if (systemKey === "xianxia") {
    return "xianxia";
  }
  return "";
}

export function nativeCharacterCreateUnsupportedMessage(_system: unknown): string {
  return NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE;
}

export function advancedEditorUnsupportedMessage(): string {
  return ADVANCED_EDITOR_UNSUPPORTED_MESSAGE;
}

export function characterAdvancedEditorIsSupported(
  campaign: Pick<CampaignViewModel, "system">,
  definition: Record<string, unknown>,
): boolean {
  return nativeCharacterCreateLane(campaign.system) === "dnd5e" && nativeCharacterCreateLane(definition.system) === "dnd5e";
}

export function characterCultivationIsSupported(
  campaign: Pick<CampaignViewModel, "system">,
  definition: Record<string, unknown>,
): boolean {
  return nativeCharacterCreateLane(campaign.system) === "xianxia" && nativeCharacterCreateLane(definition.system) === "xianxia";
}

function characterAdvancementUnsupportedMessage(system: unknown): string {
  if (nativeCharacterCreateLane(system) === "xianxia") {
    return XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE;
  }
  return NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE;
}

function campaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function flaskCampaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}

export function buildCharacterAuthoringLinks(campaign: CampaignViewModel) {
  const campaignSlug = campaign.slug;
  const links: Record<string, string> = {
    flask_roster_url: flaskCampaignHref(campaignSlug, "characters"),
    gen2_roster_url: campaignHref(campaignSlug, "characters"),
    flask_create_character_url: flaskCampaignHref(campaignSlug, "characters/new"),
    create_character_url: campaignHref(campaignSlug, "characters/new"),
    flask_create_url: flaskCampaignHref(campaignSlug, "characters/new"),
    gen2_create_url: campaignHref(campaignSlug, "characters/new"),
  };
  if (nativeCharacterCreateLane(campaign.system) === "xianxia") {
    links.flask_import_xianxia_url = flaskCampaignHref(campaignSlug, "characters/import/xianxia-manual");
    links.import_xianxia_url = campaignHref(campaignSlug, "characters/import/xianxia-manual");
    links.gen2_import_xianxia_url = campaignHref(campaignSlug, "characters/import/xianxia-manual");
  }
  return links;
}

export function buildCharacterAdvancedEditorLinks(campaign: CampaignViewModel, characterSlug: string) {
  return {
    ...buildCharacterAuthoringLinks(campaign),
    advanced_editor_url: campaignHref(campaign.slug, `characters/${characterSlug}/edit`),
    flask_advanced_editor_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}/edit`),
    character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
    gen2_character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
    flask_character_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}`),
  };
}

export function buildCharacterCultivationLinks(campaign: CampaignViewModel, characterSlug: string) {
  return {
    ...buildCharacterAuthoringLinks(campaign),
    character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
    gen2_character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
    flask_character_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}`),
    cultivation_url: campaignHref(campaign.slug, `characters/${characterSlug}/cultivation`),
    flask_cultivation_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}/cultivation`),
  };
}

export function buildCharacterCultivationShellPayload({
  campaign,
  characterSlug,
  definition,
  state,
  genericTechniqueOptions = [],
}: {
  campaign: CampaignViewModel;
  characterSlug: string;
  definition: Record<string, unknown>;
  state: Record<string, unknown>;
  genericTechniqueOptions?: Array<Record<string, unknown>>;
}): CharacterCultivationShellPayload {
  const supported = characterCultivationIsSupported(campaign, definition);
  return {
    lane: supported ? "xianxia" : "unsupported",
    supported,
    unsupported_message: supported ? "" : CULTIVATION_UNSUPPORTED_MESSAGE,
    links: buildCharacterCultivationLinks(campaign, characterSlug),
    cultivation: supported ? buildXianxiaCultivationContext(definition, state, genericTechniqueOptions, campaign.slug) : null,
  };
}

function buildXianxiaCultivationContext(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
  genericTechniqueOptions: Array<Record<string, unknown>>,
  campaignSlug: string,
): Record<string, unknown> {
  const xianxia = asRecord(definition.xianxia);
  const resources = buildXianxiaCultivationResources(definition, state);
  const insight = asRecord(resources.insight);
  const insightAvailable = nonNegativeLooseInt(insight.available, 0);
  const energies = asArray(resources.energies)
    .map(asRecord)
    .map((energy) => withInsightCost(energy, XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST, insightAvailable));
  const yinYang = asArray(resources.yin_yang)
    .map(asRecord)
    .map((resource) => withInsightCost(resource, XIANXIA_MEDITATION_INSIGHT_COST, insightAvailable));
  const hpResource = asArray(resources.durability)
    .map(asRecord)
    .find((resource) => String(resource.key || "") === "hp") ?? {};
  const stanceResource = asArray(resources.durability)
    .map(asRecord)
    .find((resource) => String(resource.key || "") === "stance") ?? {};
  const hpMaximum = nonNegativeLooseInt(hpResource.max, 0);
  const hpProjectedMaximum = Math.min(XIANXIA_CONDITIONING_HP_MAXIMUM, hpMaximum + XIANXIA_CONDITIONING_HP_INCREASE);
  const stanceMaximum = nonNegativeLooseInt(stanceResource.max, 0);
  const stanceProjectedMaximum = Math.min(
    XIANXIA_TRAINING_STANCE_MAXIMUM,
    stanceMaximum + XIANXIA_TRAINING_STANCE_INCREASE,
  );
  return {
    insight,
    energies,
    yin_yang: yinYang,
    conditioning: {
      hp: {
        key: "hp",
        label: "HP",
        current: nonNegativeLooseInt(hpResource.current, 0),
        max: hpMaximum,
        cap: XIANXIA_CONDITIONING_HP_MAXIMUM,
        insight_cost: XIANXIA_CONDITIONING_INSIGHT_COST,
        hp_increase: Math.max(0, hpProjectedMaximum - hpMaximum),
        projected_max: hpProjectedMaximum,
        has_enough_insight: insightAvailable >= XIANXIA_CONDITIONING_INSIGHT_COST,
        shortfall: Math.max(0, XIANXIA_CONDITIONING_INSIGHT_COST - insightAvailable),
        can_increase: hpMaximum < XIANXIA_CONDITIONING_HP_MAXIMUM,
      },
      efforts: xianxiaEffortRows(xianxia).map((effort) => ({
        ...effort,
        insight_cost: XIANXIA_CONDITIONING_INSIGHT_COST,
        effort_increase: XIANXIA_CONDITIONING_EFFORT_INCREASE,
        has_enough_insight: insightAvailable >= XIANXIA_CONDITIONING_INSIGHT_COST,
        shortfall: Math.max(0, XIANXIA_CONDITIONING_INSIGHT_COST - insightAvailable),
      })),
    },
    training: {
      stance: {
        key: "stance",
        label: "Stance",
        current: nonNegativeLooseInt(stanceResource.current, 0),
        max: stanceMaximum,
        cap: XIANXIA_TRAINING_STANCE_MAXIMUM,
        insight_cost: XIANXIA_TRAINING_INSIGHT_COST,
        stance_increase: Math.max(0, stanceProjectedMaximum - stanceMaximum),
        projected_max: stanceProjectedMaximum,
        has_enough_insight: insightAvailable >= XIANXIA_TRAINING_INSIGHT_COST,
        shortfall: Math.max(0, XIANXIA_TRAINING_INSIGHT_COST - insightAvailable),
        can_increase: stanceMaximum < XIANXIA_TRAINING_STANCE_MAXIMUM,
      },
      attributes: xianxiaAttributeRows(xianxia).map((attribute) => ({
        ...attribute,
        insight_cost: XIANXIA_TRAINING_INSIGHT_COST,
        attribute_increase: XIANXIA_TRAINING_ATTRIBUTE_INCREASE,
        has_enough_insight: insightAvailable >= XIANXIA_TRAINING_INSIGHT_COST,
        shortfall: Math.max(0, XIANXIA_TRAINING_INSIGHT_COST - insightAvailable),
      })),
    },
    martial_arts: xianxiaMartialArtRows(xianxia, campaignSlug).map((art, index) => ({
      ...art,
      index,
      advancement: xianxiaMartialArtAdvancementContext(asRecord(art), insightAvailable),
    })),
    generic_techniques: asArray(xianxia.generic_techniques).map((rawTechnique) => {
      const technique = asRecord(rawTechnique);
      return {
        ...technique,
        href: systemsEntryHref(asRecord(technique.systems_ref), campaignSlug),
      };
    }),
    generic_technique_options: genericTechniqueOptions
      .filter((option) => !truthy(option.selected))
      .map((option) => {
        const insightCost = nonNegativeLooseInt(option.insight_cost, 0);
        return {
          ...option,
          href: systemsEntryHref(asRecord(option.systems_ref), campaignSlug),
          has_enough_insight: insightCost > 0 && insightAvailable >= insightCost,
          shortfall: Math.max(0, insightCost - insightAvailable),
        };
      }),
    realm_ascension: buildXianxiaRealmAscensionContext(xianxia),
    history: xianxiaCultivationHistoryRows(xianxia),
  };
}

function withInsightCost(row: Record<string, unknown>, insightCost: number, insightAvailable: number): Record<string, unknown> {
  return {
    ...row,
    insight_cost: insightCost,
    has_enough_insight: insightAvailable >= insightCost,
    shortfall: Math.max(0, insightCost - insightAvailable),
  };
}

function buildXianxiaCultivationResources(
  definition: Record<string, unknown>,
  state: Record<string, unknown>,
): Record<string, unknown> {
  const xianxia = asRecord(definition.xianxia);
  const xianxiaState = asRecord(state.xianxia);
  const sharedVitals = asRecord(state.vitals);
  const stateVitals = asRecord(xianxiaState.vitals);
  const stateEnergies = asRecord(xianxiaState.energies);
  const stateYinYang = asRecord(xianxiaState.yin_yang);
  const stateDao = asRecord(xianxiaState.dao);
  const insight = asRecord(xianxia.insight);
  const durability = asRecord(xianxia.durability);
  const energies = asRecord(xianxia.energies);
  const yinYang = asRecord(xianxia.yin_yang);
  return {
    insight: {
      available: nonNegativeLooseInt(insight.available, 0),
      spent: nonNegativeLooseInt(insight.spent, 0),
    },
    energies: XIANXIA_ENERGY_KEYS.map((key) => {
      const energy = asRecord(energies[key]);
      const stateEnergy = asRecord(stateEnergies[key]);
      return {
        key,
        label: XIANXIA_ENERGY_LABELS[key],
        current: nonNegativeLooseInt(stateEnergy.current, nonNegativeLooseInt(energy.max, 0)),
        max: nonNegativeLooseInt(energy.max, 0),
      };
    }),
    yin_yang: XIANXIA_YIN_YANG_KEYS.map((key) => {
      const maxKey = `${key}_max`;
      const currentKey = `${key}_current`;
      return {
        key,
        label: XIANXIA_YIN_YANG_LABELS[key],
        current: nonNegativeLooseInt(stateYinYang[currentKey], nonNegativeLooseInt(yinYang[maxKey], 1)),
        max: nonNegativeLooseInt(yinYang[maxKey], 1),
      };
    }),
    durability: [
      {
        key: "hp",
        label: "HP",
        current: nonNegativeLooseInt(stateVitals.current_hp ?? sharedVitals.current_hp, nonNegativeLooseInt(durability.hp_max, 10)),
        temp: nonNegativeLooseInt(stateVitals.temp_hp ?? sharedVitals.temp_hp, 0),
        max: nonNegativeLooseInt(durability.hp_max, 10),
      },
      {
        key: "stance",
        label: "Stance",
        current: nonNegativeLooseInt(stateVitals.current_stance, nonNegativeLooseInt(durability.stance_max, 10)),
        temp: nonNegativeLooseInt(stateVitals.temp_stance, 0),
        max: nonNegativeLooseInt(durability.stance_max, 10),
      },
      {
        key: "dao",
        label: "Dao",
        current: nonNegativeLooseInt(stateDao.current, 0),
        max: nonNegativeLooseInt(asRecord(xianxia.dao).max, XIANXIA_DAO_DEFAULT_MAX),
      },
    ],
  };
}

function xianxiaAttributeRows(xianxia: Record<string, unknown>): Array<Record<string, unknown>> {
  const attributes = asRecord(xianxia.attributes);
  return XIANXIA_ATTRIBUTE_KEYS.map((key) => ({
    key,
    label: XIANXIA_ATTRIBUTE_LABELS[key],
    score: nonNegativeLooseInt(attributes[key], 0),
    current: nonNegativeLooseInt(attributes[key], 0),
  }));
}

function xianxiaEffortRows(xianxia: Record<string, unknown>): Array<Record<string, unknown>> {
  const efforts = asRecord(xianxia.efforts);
  return XIANXIA_EFFORT_KEYS.map((key) => ({
    key,
    label: XIANXIA_EFFORT_LABELS[key],
    score: nonNegativeLooseInt(efforts[key], 0),
    current: nonNegativeLooseInt(efforts[key], 0),
  }));
}

function xianxiaMartialArtRows(xianxia: Record<string, unknown>, campaignSlug: string): Array<Record<string, unknown>> {
  return asArray(xianxia.martial_arts).map((rawArt) => {
    const art = asRecord(rawArt);
    return {
      ...art,
      href: systemsEntryHref(asRecord(art.systems_ref), campaignSlug),
      rank_progress: xianxiaMartialArtRankProgress(art),
    };
  });
}

function xianxiaMartialArtRankProgress(art: Record<string, unknown>): Record<string, unknown> {
  const learnedRankRefs = new Set(asArray(art.learned_rank_refs).map((ref) => String(ref || "").trim()).filter(Boolean));
  const rankRefs = asRecord(art.rank_refs);
  const currentRankKey = normalizeRankKey(art.current_rank_key || art.current_rank || "");
  const currentRankIndex = (XIANXIA_MARTIAL_ART_RANK_ORDER as readonly string[]).indexOf(currentRankKey);
  const steps = XIANXIA_MARTIAL_ART_RANK_ORDER.map((rankKey, index) => {
    const rankRef = String(rankRefs[rankKey] || "").trim();
    const isLearned =
      (currentRankIndex >= 0 && index <= currentRankIndex) ||
      (rankRef.length > 0 && learnedRankRefs.has(rankRef));
    const insightCost = xianxiaMartialArtRankInsightCost(rankKey);
    return {
      key: rankKey,
      label: XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[rankKey] || humanizeSlug(rankKey),
      rank_ref: rankRef,
      href: rankRef ? `#${rankRef}` : "",
      insight_cost: insightCost,
      is_learned: isLearned,
      is_current: rankKey === currentRankKey,
      is_incomplete: false,
      status_label: isLearned ? "Learned" : insightCost > 0 ? `Insight ${insightCost}` : "Available",
      teacher_breakthrough_requirement: "",
      teacher_breakthrough_note: "",
      legendary_prerequisite_note: "",
    };
  });
  return { steps };
}

function xianxiaMartialArtRankInsightCost(rankKey: string): number {
  if (rankKey === "initiate") {
    return 0;
  }
  if (rankKey === "novice") {
    return 1;
  }
  if (rankKey === "apprentice") {
    return 2;
  }
  if (rankKey === "master") {
    return 3;
  }
  if (rankKey === "legendary") {
    return 5;
  }
  return 0;
}

function xianxiaMartialArtAdvancementContext(art: Record<string, unknown>, insightAvailable: number): Record<string, unknown> {
  const steps = asArray(asRecord(art.rank_progress).steps).map(asRecord);
  const nextStep = steps.find((step) => !truthy(step.is_learned));
  if (!nextStep) {
    return {
      status: "complete",
      message: "No further structured rank is currently available.",
    };
  }
  if (truthy(nextStep.is_incomplete)) {
    return {
      status: "incomplete",
      message: "The next higher rank is marked as intentional draft content.",
    };
  }
  const nextRankKey = normalizeRankKey(nextStep.key);
  const insightCost = nonNegativeLooseInt(nextStep.insight_cost, 0);
  return {
    status: "available",
    next_rank_key: nextRankKey,
    next_rank_label: String(nextStep.label || XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[nextRankKey] || humanizeSlug(nextRankKey)),
    insight_cost: insightCost,
    has_enough_insight: insightCost > 0 && insightAvailable >= insightCost,
    shortfall: Math.max(0, insightCost - insightAvailable),
    teacher_breakthrough_requirement: String(nextStep.teacher_breakthrough_requirement || "").trim(),
    teacher_breakthrough_note: String(nextStep.teacher_breakthrough_note || "").trim(),
    requires_legendary_note: nextRankKey === "legendary",
    legendary_prerequisite_note: String(nextStep.legendary_prerequisite_note || "").trim(),
  };
}

function buildXianxiaRealmAscensionContext(xianxia: Record<string, unknown>): Record<string, unknown> {
  const currentRealm = normalizeRealmLabel(xianxia.realm);
  const target = asRecord(XIANXIA_REALM_ASCENSION_TARGETS[currentRealm]);
  const hasTarget = Object.keys(target).length > 0;
  const history = asArray(xianxia.advancement_history).map(asRecord).filter((record) => Object.keys(record).length > 0);
  const latestReview = latestRealmAscensionEvent(history, "realm_ascension_review_started");
  const latestReset = latestRealmAscensionEvent(history, "realm_ascension_attributes_efforts_reset");
  const latestRebuild = [...history].reverse().find((record) => XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.has(String(record.action || ""))) ?? null;
  const pendingConfirmationRebuild =
    latestRebuild && !truthy(latestRebuild.gm_confirmed) && !truthy(latestRebuild.confirmed) ? latestRebuild : null;
  const attributes = xianxiaStatSummary(xianxiaAttributeRows(xianxia));
  const efforts = xianxiaStatSummary(xianxiaEffortRows(xianxia));
  const statPrerequisite = xianxiaRealmStatPrerequisite(currentRealm, target, attributes.rows, efforts.rows);
  const context: Record<string, unknown> = {
    current_realm: currentRealm,
    available: hasTarget,
    target,
    attributes,
    efforts,
    stat_prerequisite: statPrerequisite,
    can_start_review: hasTarget && truthy(statPrerequisite.is_met) && pendingConfirmationRebuild === null,
    latest_review: latestReview,
    latest_reset: latestReset,
    latest_rebuild: latestRebuild,
    pending_confirmation_rebuild: pendingConfirmationRebuild,
    latest_confirmation: latestRealmAscensionEvent(history, "realm_ascension_gm_confirmation_recorded"),
    latest_immortal_rebuild: latestRealmAscensionRebuild(history, "Immortal"),
    latest_divine_rebuild: latestRealmAscensionRebuild(history, "Divine"),
    hp_stance_trade: xianxiaRealmTradeContext(asRecord(xianxia.durability)),
  };
  context.can_confirm_rebuild = pendingConfirmationRebuild !== null;
  context.can_reset_stats = canResetRealmAscensionStats(latestReview, latestReset, target);
  context.can_apply_rebuild = canApplyRealmRebuild(
    latestReview,
    latestReset,
    latestRealmAscensionRebuild(history, String(target.target_realm || "")),
    target,
  );
  context.can_apply_immortal_rebuild = truthy(context.can_apply_rebuild) && String(target.target_realm || "") === "Immortal";
  context.can_apply_divine_rebuild = truthy(context.can_apply_rebuild) && String(target.target_realm || "") === "Divine";
  if (pendingConfirmationRebuild !== null) {
    context.confirmation_blocking_message = "Confirm the latest Realm rebuild before starting another Realm review.";
  }
  if (!hasTarget) {
    context.message = "No further Realm ascension target is defined for this character.";
  }
  return context;
}

function latestRealmAscensionEvent(history: Array<Record<string, unknown>>, action: string): Record<string, unknown> | null {
  return [...history].reverse().find((record) => String(record.action || "") === action) ?? null;
}

function latestRealmAscensionRebuild(history: Array<Record<string, unknown>>, targetRealm: string): Record<string, unknown> | null {
  return [...history]
    .reverse()
    .find((record) =>
      XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.has(String(record.action || "")) &&
      String(record.target_realm || "").trim() === targetRealm,
    ) ?? null;
}

function canResetRealmAscensionStats(
  latestReview: Record<string, unknown> | null,
  latestReset: Record<string, unknown> | null,
  target: Record<string, unknown>,
): boolean {
  const targetRealm = String(target.target_realm || "").trim();
  if (!latestReview || !targetRealm) {
    return false;
  }
  if (String(latestReview.status || "").trim() !== "pending_gm_review") {
    return false;
  }
  if (String(latestReview.target_realm || latestReview.target || "").trim() !== targetRealm) {
    return false;
  }
  if (!latestReset) {
    return true;
  }
  return String(latestReset.target_realm || latestReset.target || "").trim() !== targetRealm;
}

function canApplyRealmRebuild(
  latestReview: Record<string, unknown> | null,
  latestReset: Record<string, unknown> | null,
  latestTargetRebuild: Record<string, unknown> | null,
  target: Record<string, unknown>,
): boolean {
  const targetRealm = String(target.target_realm || "").trim();
  if (!latestReview || !latestReset || !targetRealm) {
    return false;
  }
  if (String(latestReview.status || "").trim() !== "pending_gm_review") {
    return false;
  }
  if (String(latestReview.target_realm || latestReview.target || "").trim() !== targetRealm) {
    return false;
  }
  if (String(latestReset.status || "").trim() !== "pending_rebuild") {
    return false;
  }
  if (String(latestReset.target_realm || latestReset.target || "").trim() !== targetRealm) {
    return false;
  }
  return latestTargetRebuild === null;
}

function xianxiaStatSummary(rows: Array<Record<string, unknown>>): {
  rows: Array<Record<string, unknown>>;
  total: number;
  highest: Record<string, unknown> | null;
} {
  const total = rows.reduce((sum, row) => sum + nonNegativeLooseInt(row.score, 0), 0);
  const highest = rows.reduce<Record<string, unknown> | null>((best, row) => {
    if (!best || nonNegativeLooseInt(row.score, 0) > nonNegativeLooseInt(best.score, 0)) {
      return row;
    }
    return best;
  }, null);
  return { rows, total, highest };
}

function xianxiaRealmStatPrerequisite(
  _currentRealm: string,
  target: Record<string, unknown>,
  attributeRows: Array<Record<string, unknown>>,
  effortRows: Array<Record<string, unknown>>,
): Record<string, unknown> {
  const requiredScore = nonNegativeLooseInt(target.stat_max_prerequisite, 0);
  if (requiredScore <= 0) {
    return { is_met: false, required_score: 0, failure_message: "No Realm ascension target is available." };
  }
  const candidates: Array<Record<string, unknown>> = [
    ...attributeRows.map((row) => ({ ...row, kind: "attribute" })),
    ...effortRows.map((row) => ({ ...row, kind: "effort" })),
  ];
  const metBy = candidates.find((row) => nonNegativeLooseInt(row.score, 0) >= requiredScore) ?? null;
  const highest = candidates.reduce<Record<string, unknown> | null>((best, row) => {
    if (!best || nonNegativeLooseInt(row.score, 0) > nonNegativeLooseInt(best.score, 0)) {
      return row;
    }
    return best;
  }, null);
  return {
    is_met: metBy !== null,
    required_score: requiredScore,
    met_by: metBy,
    highest,
    failure_message: metBy
      ? ""
      : `Need one Stat at ${requiredScore}. Current highest Stat is ${String(highest?.label || "none")} at ${nonNegativeLooseInt(highest?.score, 0)}.`,
  };
}

function xianxiaRealmTradeContext(durability: Record<string, unknown>): Record<string, unknown> {
  const hpMax = nonNegativeLooseInt(durability.hp_max, 10);
  const stanceMax = nonNegativeLooseInt(durability.stance_max, 10);
  return {
    unit: XIANXIA_REALM_ASCENSION_TRADE_UNIT,
    hp_max: hpMax,
    stance_max: stanceMax,
    max_trade_points: Math.floor(Math.max(0, hpMax + stanceMax) / XIANXIA_REALM_ASCENSION_TRADE_UNIT),
  };
}

function xianxiaCultivationHistoryRows(xianxia: Record<string, unknown>): Array<Record<string, unknown>> {
  return asArray(xianxia.advancement_history)
    .map(asRecord)
    .filter((record) => Object.keys(record).length > 0)
    .map((record, index) => ({
      index: index + 1,
      action: humanizeSlug(String(record.action || record.type || "advancement")),
      details: XIANXIA_CULTIVATION_HISTORY_DETAIL_LABELS
        .map(([key, label]) => {
          let value = record[key];
          if (typeof value === "object" && value !== null && !Array.isArray(value)) {
            const valueRecord = asRecord(value);
            value = valueRecord.title || valueRecord.slug || valueRecord.entry_key;
          }
          const cleaned = String(value ?? "").trim();
          return cleaned ? { label, value: cleaned } : null;
        })
        .filter((detail): detail is { label: string; value: string } => detail !== null),
    }));
}

const XIANXIA_CULTIVATION_HISTORY_DETAIL_LABELS: Array<[string, string]> = [
  ["amount", "Amount"],
  ["insight_available_before", "Available Insight before"],
  ["insight_available_after", "Available Insight after"],
  ["insight_available_delta", "Available Insight change"],
  ["insight_spent_before", "Spent Insight before"],
  ["insight_spent_after", "Spent Insight after"],
  ["insight_spent_delta", "Spent Insight change"],
  ["downtime", "Downtime"],
  ["target", "Target"],
  ["energy_key", "Energy key"],
  ["energy_maximum_increase", "Energy maximum increase"],
  ["new_energy_maximum", "New Energy maximum"],
  ["yin_yang_key", "Yin/Yang key"],
  ["yin_yang_maximum_increase", "Yin/Yang maximum increase"],
  ["new_yin_yang_maximum", "New Yin/Yang maximum"],
  ["hp_maximum_increase", "HP maximum increase"],
  ["new_hp_maximum", "New HP maximum"],
  ["hp_maximum_cap", "HP maximum cap"],
  ["effort_key", "Effort key"],
  ["effort_point_increase", "Effort point increase"],
  ["new_effort_score", "New Effort score"],
  ["stance_maximum_increase", "Stance maximum increase"],
  ["new_stance_maximum", "New Stance maximum"],
  ["stance_maximum_cap", "Stance maximum cap"],
  ["attribute_key", "Attribute key"],
  ["attribute_point_increase", "Attribute point increase"],
  ["new_attribute_score", "New Attribute score"],
  ["rank", "Rank"],
  ["systems_ref", "Systems ref"],
  ["generic_technique_key", "Generic Technique key"],
  ["insight_cost", "Insight cost"],
  ["teacher_breakthrough_note", "Teacher/breakthrough note"],
  ["legendary_prerequisite_note", "Legendary requirement"],
  ["legendary_quest_note", "Legendary quest/mythic-master note"],
  ["current_realm", "Current Realm"],
  ["target_realm", "Target Realm"],
  ["status", "Status"],
  ["seclusion_time", "Seclusion time"],
  ["rebuild_budget", "Rebuild budget"],
  ["base_rebuild_budget", "Base rebuild budget"],
  ["stat_cap", "Stat cap"],
  ["actions_per_turn", "Actions per turn"],
  ["notes", "Notes"],
];

function systemsEntryHref(systemsRef: Record<string, unknown>, campaignSlug: string): string {
  const slug = String(systemsRef.slug || "").trim();
  const safeCampaignSlug = String(campaignSlug || "").trim();
  return slug && safeCampaignSlug ? `/app-next/campaigns/${safeCampaignSlug}/systems/entries/${slug}` : "";
}

function normalizeRealmLabel(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  for (const realm of XIANXIA_REALM_ASCENSION_REALMS) {
    if (realm.toLowerCase() === normalized) {
      return realm;
    }
  }
  return "Mortal";
}

function stringifyEditorValue(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function buildReferenceField(
  name: string,
  label: string,
  helpText: string,
  value: unknown,
): Record<string, unknown> {
  return {
    name,
    label,
    help_text: helpText,
    value: stringifyEditorValue(value),
  };
}

export function buildCharacterAdvancedEditorPayload({
  campaign,
  characterSlug,
  definition,
  state,
  stateRevision,
}: {
  campaign: CampaignViewModel;
  characterSlug: string;
  definition: Record<string, unknown>;
  state: Record<string, unknown>;
  stateRevision: number;
}): CharacterAdvancedEditorPayload {
  const supported = characterAdvancedEditorIsSupported(campaign, definition);
  const links = buildCharacterAdvancedEditorLinks(campaign, characterSlug);
  if (!supported) {
    return {
      lane: "unsupported",
      supported: false,
      unsupported_message: ADVANCED_EDITOR_UNSUPPORTED_MESSAGE,
      links,
      editor: null,
    };
  }

  const stateNotes = asRecord(state.notes);
  const profile = asRecord(definition.profile);
  const referenceNotes = asRecord(definition.reference_notes);
  const features = asArray(definition.features).map((value, index) => {
    const feature = asRecord(value);
    return {
      row_id: stringifyEditorValue(feature.id || feature.feature_key || feature.name || `feature-${index + 1}`),
      name: stringifyEditorValue(feature.name || `Feature ${index + 1}`),
      category: stringifyEditorValue(feature.category),
      tracker_ref: stringifyEditorValue(feature.tracker_ref),
      source: stringifyEditorValue(feature.source),
      description_markdown: stringifyEditorValue(feature.description_markdown),
    };
  });
  const equipment = asArray(definition.equipment_catalog).map((value, index) => {
    const item = asRecord(value);
    return {
      row_id: stringifyEditorValue(item.id || item.item_id || item.name || `equipment-${index + 1}`),
      name: stringifyEditorValue(item.name || `Equipment ${index + 1}`),
      default_quantity: item.default_quantity ?? null,
      weight: stringifyEditorValue(item.weight),
      is_equipped: Boolean(item.is_equipped),
      tags: asArray(item.tags).map((tag) => stringifyEditorValue(tag)).filter((tag) => tag.length > 0),
    };
  });

  return {
    lane: "dnd5e",
    supported: true,
    unsupported_message: "",
    links,
    editor: {
      state_revision: stateRevision,
      reference_fields: [
        buildReferenceField(
          "physical_description_markdown",
          "Physical Description",
          "Markdown shown on the Personal page for durable appearance notes.",
          stateNotes.physical_description_markdown,
        ),
        buildReferenceField(
          "background_markdown",
          "Background",
          "Markdown shown on the Personal page for durable background notes.",
          stateNotes.background_markdown ?? stateNotes.personal_background_markdown,
        ),
        buildReferenceField(
          "biography_markdown",
          "Biography",
          "Markdown shown on the Notes page for reference-level character history.",
          profile.biography_markdown,
        ),
        buildReferenceField(
          "personality_markdown",
          "Personality",
          "Markdown shown on the Notes page for personality traits, ideals, bonds, flaws, or similar notes.",
          profile.personality_markdown,
        ),
        buildReferenceField(
          "additional_notes_markdown",
          "Additional Notes",
          "Markdown shown on the Notes page for other persistent reference material.",
          referenceNotes.additional_notes_markdown,
        ),
        buildReferenceField(
          "allies_and_organizations_markdown",
          "Allies and Organizations",
          "Markdown shown on the Notes page for friendly factions, patrons, allies, or affiliations.",
          referenceNotes.allies_and_organizations_markdown,
        ),
      ],
      feature_rows: features,
      equipment_rows: equipment,
    },
  };
}

export function applyCharacterAdvancedEditorReferenceUpdate(
  definition: Record<string, unknown>,
  payload: Record<string, unknown>,
): CharacterAdvancedEditorReferenceUpdate {
  const rawValues = asRecord(payload.values);
  const values: Record<string, string> = {};
  for (const [rawKey, value] of Object.entries(rawValues)) {
    const fieldName = String(rawKey || "").trim();
    if (!fieldName) {
      continue;
    }
    if (Array.isArray(value)) {
      values[fieldName] = String(value.length > 0 ? value[value.length - 1] : "");
    } else if (value === null || value === undefined) {
      values[fieldName] = "";
    } else {
      values[fieldName] = String(value);
    }
  }

  const unsupportedFields = Object.keys(values).filter((fieldName) => !ADVANCED_EDITOR_REFERENCE_FIELD_NAMES.has(fieldName));
  if (unsupportedFields.length > 0) {
    return {
      status: "validation_error",
      message: `Unsupported Advanced Editor fields for the TypeScript reference-field slice: ${unsupportedFields.join(", ")}.`,
    };
  }

  const nextDefinition = JSON.parse(JSON.stringify(definition || {})) as Record<string, unknown>;
  const profile = { ...asRecord(nextDefinition.profile) };
  const referenceNotes = { ...asRecord(nextDefinition.reference_notes) };
  const stateNoteValues: Record<string, string> = {};

  for (const [fieldName, value] of Object.entries(values)) {
    if (fieldName === "biography_markdown" || fieldName === "personality_markdown") {
      profile[fieldName] = value;
    } else if (fieldName === "additional_notes_markdown" || fieldName === "allies_and_organizations_markdown") {
      referenceNotes[fieldName] = value;
    } else if (ADVANCED_EDITOR_STATE_NOTE_FIELD_NAMES.has(fieldName)) {
      stateNoteValues[fieldName] = value;
    }
  }

  nextDefinition.profile = profile;
  nextDefinition.reference_notes = referenceNotes;
  return {
    status: "ok",
    definition: nextDefinition,
    stateNoteValues,
    values,
  };
}

function definitionSourceType(definition: Record<string, unknown>): string {
  return stringifyEditorValue(asRecord(definition.source).source_type).trim();
}

function definitionCurrentLevel(definition: Record<string, unknown>): number {
  const profile = asRecord(definition.profile);
  const classRows = asArray(profile.classes);
  let summedLevel = 0;
  for (const value of classRows) {
    const row = asRecord(value);
    const level = Number(row.level);
    if (Number.isFinite(level) && level > 0) {
      summedLevel += level;
    }
  }
  if (summedLevel > 0) {
    return summedLevel;
  }

  const classLevelText = stringifyEditorValue(profile.class_level_text);
  const matchedLevels = [...classLevelText.matchAll(/\b(\d{1,2})\b/g)].map((match) => Number(match[1]));
  const parsedLevel = matchedLevels.reduce((total, level) => (Number.isFinite(level) ? total + level : total), 0);
  return parsedLevel > 0 ? parsedLevel : 1;
}

function buildCharacterAdvancementLinks({
  campaign,
  characterSlug,
  definition,
  readinessStatus,
  kind,
}: {
  campaign: CampaignViewModel;
  characterSlug: string;
  definition: Record<string, unknown>;
  readinessStatus: string;
  kind: CharacterAdvancementRouteKind;
}): Record<string, string> {
  const links: Record<string, string> = {
    flask_roster_url: flaskCampaignHref(campaign.slug, "characters"),
    character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
    flask_character_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}`),
  };
  const campaignLane = nativeCharacterCreateLane(campaign.system);
  const characterLane = nativeCharacterCreateLane(definition.system);
  if (campaignLane === "dnd5e" && characterLane === "dnd5e") {
    links.advanced_editor_url = campaignHref(campaign.slug, `characters/${characterSlug}/edit`);
    links.flask_advanced_editor_url = flaskCampaignHref(campaign.slug, `characters/${characterSlug}/edit`);
  }
  if (campaignLane === "xianxia" || characterLane === "xianxia") {
    links.cultivation_url = campaignHref(campaign.slug, `characters/${characterSlug}/cultivation`);
    links.flask_cultivation_url = flaskCampaignHref(campaign.slug, `characters/${characterSlug}/cultivation`);
  }
  if (kind === "level_up" && readinessStatus === "ready") {
    links.level_up_url = campaignHref(campaign.slug, `characters/${characterSlug}/level-up`);
    links.flask_level_up_url = flaskCampaignHref(campaign.slug, `characters/${characterSlug}/level-up`);
  }
  if (kind === "retraining" && readinessStatus === "ready") {
    links.retraining_url = campaignHref(campaign.slug, `characters/${characterSlug}/retraining`);
    links.flask_retraining_url = flaskCampaignHref(campaign.slug, `characters/${characterSlug}/retraining`);
  }
  if (readinessStatus === "repairable") {
    links.progression_repair_url = campaignHref(campaign.slug, `characters/${characterSlug}/progression-repair`);
    links.flask_progression_repair_url = flaskCampaignHref(campaign.slug, `characters/${characterSlug}/progression-repair`);
  }
  return links;
}

function buildLevelUpUnsupportedReadiness(definition: Record<string, unknown>, message: string): Record<string, unknown> {
  const sourceType = definitionSourceType(definition);
  return {
    status: "unsupported",
    message,
    reasons: ["This character source is outside the current native progression flow."],
    current_level: definitionCurrentLevel(definition),
    source_type: sourceType,
    is_native: sourceType === "native_character_builder",
    is_imported: sourceType === "pdf_import" || sourceType === "markdown_import",
  };
}

export function buildCharacterAdvancementShellPayload({
  campaign,
  characterSlug,
  definition,
  kind,
}: {
  campaign: CampaignViewModel;
  characterSlug: string;
  definition: Record<string, unknown>;
  kind: CharacterAdvancementRouteKind;
}): CharacterAdvancementShellPayload {
  const campaignLane = nativeCharacterCreateLane(campaign.system);
  const characterLane = nativeCharacterCreateLane(definition.system);
  const dndSupported = campaignLane === "dnd5e" && characterLane === "dnd5e";

  if (!dndSupported) {
    const unsupportedMessage =
      campaignLane !== "dnd5e"
        ? characterAdvancementUnsupportedMessage(campaign.system)
        : kind === "level_up"
          ? "Level-up is currently available only for DND-5E native character tools in Gen2."
        : kind === "retraining"
          ? "Retraining is currently available only for DND-5E native character tools in Gen2."
          : "Progression repair is currently available only for DND-5E imported character sheets in Gen2.";
    const readiness = {
      status: "unsupported",
      message: unsupportedMessage,
    };
    return {
      lane: "unsupported",
      supported: false,
      unsupported_message: unsupportedMessage,
      readiness,
      links: buildCharacterAdvancementLinks({
        campaign,
        characterSlug,
        definition,
        readinessStatus: "unsupported",
        kind,
      }),
      context: null,
    };
  }

  const levelUpMessage = "Level-up currently supports native in-app characters and imported character sheets only.";
  const levelUpReadiness = buildLevelUpUnsupportedReadiness(definition, levelUpMessage);
  if (kind === "retraining") {
    const readiness = {
      status: "empty",
      message: "This character does not currently have any supported structured retraining options.",
      level_up_readiness: levelUpReadiness,
      linked_feature_authoring: {
        supported: true,
        is_imported: false,
        message: "",
      },
    };
    return {
      lane: "unsupported",
      supported: false,
      unsupported_message: stringifyEditorValue(readiness.message),
      readiness,
      links: buildCharacterAdvancementLinks({
        campaign,
        characterSlug,
        definition,
        readinessStatus: "empty",
        kind,
      }),
      context: null,
    };
  }

  return {
    lane: "unsupported",
    supported: false,
    unsupported_message: levelUpMessage,
    readiness: levelUpReadiness,
    links: buildCharacterAdvancementLinks({
      campaign,
      characterSlug,
      definition,
      readinessStatus: "unsupported",
      kind,
    }),
    context: null,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function parseJsonRecord(rawValue: string): Record<string, unknown> {
  try {
    return asRecord(JSON.parse(rawValue || "{}"));
  } catch {
    return {};
  }
}

function createContextInteger(value: unknown, fallback = 0): number {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function sourceSeeds(campaignConfig: Record<string, unknown>): Map<string, { enabled: boolean }> {
  const seeds = new Map<string, { enabled: boolean }>();
  for (const rawSource of asArray(campaignConfig.systems_sources)) {
    const source = asRecord(rawSource);
    const sourceId = String(source.source_id || "").trim();
    if (!sourceId) {
      continue;
    }
    seeds.set(sourceId, { enabled: Boolean(source.enabled) });
  }
  return seeds;
}

function campaignCustomSourceId(campaignSlug: string): string {
  const normalized = String(campaignSlug || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/\//g, "-")
    .toUpperCase();
  return `CUSTOM-${normalized || "CAMPAIGN"}`;
}

function loadEnabledSourceIds(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
): string[] {
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug) {
    return [];
  }
  const seeds = sourceSeeds(campaignConfig);
  const rows = database
    .prepare(
      `
        SELECT
          systems_sources.source_id,
          campaign_enabled_sources.is_enabled AS configured_enabled,
          campaign_enabled_sources.default_visibility AS configured_visibility
        FROM systems_sources
        LEFT JOIN campaign_enabled_sources
          ON campaign_enabled_sources.campaign_slug = ?
         AND campaign_enabled_sources.library_slug = systems_sources.library_slug
         AND campaign_enabled_sources.source_id = systems_sources.source_id
        WHERE systems_sources.library_slug = ?
        ORDER BY LOWER(systems_sources.title), systems_sources.source_id
      `,
    )
    .all(campaign.slug, librarySlug) as SystemsSourceAccessRow[];

  return rows
    .filter((row) => {
      const configured = row.configured_enabled !== null || Boolean(row.configured_visibility);
      return configured ? Boolean(row.configured_enabled) : Boolean(seeds.get(row.source_id)?.enabled);
    })
    .map((row) => row.source_id);
}

function loadEnabledSystemsEntryRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  entryType: string,
): SystemsEntryRow[] {
  const enabledSourceIds = loadEnabledSourceIds(database, campaign, campaignConfig);
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug || enabledSourceIds.length === 0) {
    return [];
  }
  const placeholders = enabledSourceIds.map(() => "?").join(", ");
  return database
    .prepare(
      `
        SELECT
          systems_entries.library_slug,
          systems_entries.source_id,
          systems_entries.entry_key,
          systems_entries.entry_type,
          systems_entries.slug,
          systems_entries.title,
          systems_entries.metadata_json,
          systems_entries.body_json,
          campaign_entry_overrides.is_enabled_override AS is_enabled_override
        FROM systems_entries
        LEFT JOIN campaign_entry_overrides
          ON campaign_entry_overrides.campaign_slug = ?
         AND campaign_entry_overrides.library_slug = systems_entries.library_slug
         AND campaign_entry_overrides.entry_key = systems_entries.entry_key
        WHERE systems_entries.library_slug = ?
          AND systems_entries.source_id IN (${placeholders})
          AND LOWER(systems_entries.entry_type) = ?
        ORDER BY LOWER(systems_entries.title), systems_entries.source_id
      `,
    )
    .all(campaign.slug, librarySlug, ...enabledSourceIds, entryType.toLowerCase()) as SystemsEntryRow[];
}

function loadEnabledMartialArtRows(
  database: SqliteDatabase,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
): SystemsEntryRow[] {
  return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "martial_art");
}

function normalizeRankKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function normalizeMartialArtOptionSlug(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeGenericTechniqueKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function firstPresent(...values: unknown[]): unknown {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return "";
}

function normalizeLookup(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function normalizeDndSourceId(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function dndBaseClassKey(sourceId: unknown, className: unknown): string {
  const normalizedSourceId = normalizeDndSourceId(sourceId);
  const normalizedClassName = normalizeLookup(className);
  return normalizedSourceId && normalizedClassName ? `${normalizedSourceId}|${normalizedClassName}` : "";
}

function dndSupportsBaseClass(sourceId: unknown, className: unknown): boolean {
  const normalizedSourceId = normalizeDndSourceId(sourceId);
  if (normalizedSourceId === DND_PHB_SOURCE_ID) {
    return true;
  }
  return DND_SUPPORTED_NON_PHB_BASE_CLASSES.has(dndBaseClassKey(normalizedSourceId, className));
}

function dndSupportsSubordinateSource(sourceId: unknown): boolean {
  const normalizedSourceId = normalizeDndSourceId(sourceId);
  return normalizedSourceId === DND_PHB_SOURCE_ID || DND_SUPPORTED_SUBORDINATE_SOURCES.has(normalizedSourceId);
}

function dndSupportsNativeClassEntry(row: SystemsEntryRow): boolean {
  const metadata = parseJsonRecord(row.metadata_json);
  if (!String(row.title || "").trim() || !metadata.hit_die) {
    return false;
  }
  return dndSupportsBaseClass(row.source_id, row.title);
}

function dndSupportsNativeSubclassEntry(row: SystemsEntryRow, selectedClass: SystemsEntryRow | null): boolean {
  if (!dndSupportsSubordinateSource(row.source_id)) {
    return false;
  }
  const metadata = parseJsonRecord(row.metadata_json);
  const className = String(firstPresent(metadata.class_name, selectedClass?.title) || "").trim();
  const classSource = normalizeDndSourceId(firstPresent(metadata.class_source, selectedClass?.source_id));
  if (!className || !classSource || !dndSupportsBaseClass(classSource, className)) {
    return false;
  }
  if (!selectedClass) {
    return true;
  }
  return normalizeLookup(selectedClass.title) === normalizeLookup(className) && normalizeDndSourceId(selectedClass.source_id) === classSource;
}

function dndEntryOption(row: SystemsEntryRow): Record<string, unknown> {
  const metadata = parseJsonRecord(row.metadata_json);
  const slug = String(row.slug || "").trim();
  const pageRef = String(metadata.page_ref || "").trim();
  const value = pageRef ? `page:${pageRef}` : slug ? `${DND_SYSTEMS_OPTION_PREFIX}${slug}` : "";
  return {
    slug,
    value,
    title: String(row.title || "").trim(),
    source_id: String(row.source_id || "").trim(),
    entry_key: String(row.entry_key || "").trim(),
    page_ref: pageRef,
    campaign_option: asRecord(metadata.campaign_option),
    label: String(row.title || "").trim(),
  };
}

function sanitizeDndEntrySelectionValue(rawValue: unknown, rows: SystemsEntryRow[]): string {
  const value = String(rawValue ?? "").trim();
  if (!value) {
    return "";
  }
  for (const row of rows) {
    const option = dndEntryOption(row);
    const optionValue = String(option.value || "").trim();
    if (!optionValue) {
      continue;
    }
    for (const candidate of [option.value, option.slug, option.page_ref]) {
      if (value === String(candidate || "").trim()) {
        return optionValue;
      }
    }
  }
  return "";
}

function selectedDndEntry(rows: SystemsEntryRow[], value: unknown): SystemsEntryRow | null {
  const selectedValue = String(value ?? "").trim();
  if (!selectedValue) {
    return null;
  }
  return (
    rows.find((row) => {
      const option = dndEntryOption(row);
      return selectedValue === option.value || selectedValue === option.slug || selectedValue === option.page_ref;
    }) || null
  );
}

function dndClassRequiresSubclassAtLevelOne(selectedClass: SystemsEntryRow | null): boolean {
  if (!selectedClass) {
    return false;
  }
  const metadata = parseJsonRecord(selectedClass.metadata_json);
  const subclassLevel = Number(firstPresent(metadata.subclass_level, metadata.subclassLevel, metadata.subclass_choice_level));
  return Number.isFinite(subclassLevel) && subclassLevel === 1;
}

function dndAbilityScorePreview(values: Record<string, string>) {
  return Object.fromEntries(DND_ABILITY_KEYS.map((key) => [key, createContextInteger(values[key], 10)]));
}

function dndCreatePreview({
  selectedClass,
  selectedSpecies,
  selectedBackground,
  values,
}: {
  selectedClass: SystemsEntryRow | null;
  selectedSpecies: SystemsEntryRow | null;
  selectedBackground: SystemsEntryRow | null;
  values: Record<string, string>;
}): Record<string, unknown> {
  const classMetadata = selectedClass ? parseJsonRecord(selectedClass.metadata_json) : {};
  const speciesMetadata = selectedSpecies ? parseJsonRecord(selectedSpecies.metadata_json) : {};
  const classHitDie = createContextInteger(classMetadata.hit_die, 8);
  const constitutionModifier = abilityModifier(createContextInteger(values.con, 10));
  return {
    class_level_text: selectedClass ? `${selectedClass.title} 1` : "",
    max_hp: selectedClass ? Math.max(1, classHitDie + constitutionModifier) : "",
    speed: firstPresent(speciesMetadata.speed, speciesMetadata.walk_speed, ""),
    size: firstPresent(speciesMetadata.size, ""),
    starting_currency: selectedBackground ? `${selectedBackground.title} starting package` : "",
    saving_throws: asArray(classMetadata.saving_throw_proficiencies).map(String),
    languages: asArray(speciesMetadata.languages).map(String),
    features: [selectedClass?.title ? `${selectedClass.title} level 1 features` : "", selectedSpecies?.title || "", selectedBackground?.title || ""]
      .map(String)
      .filter(Boolean),
    resources: [],
    equipment: [],
    attacks: [],
    spells: [],
    ability_scores: dndAbilityScorePreview(values),
  };
}

function abilityModifier(score: number): number {
  return Math.floor((score - 10) / 2);
}

function dndAbilityChoiceSection(values: Record<string, string>): Record<string, unknown> {
  return {
    title: "Ability Scores",
    fields: DND_ABILITY_KEYS.map((key) => ({
      name: key,
      label: DND_ABILITY_LABELS[key],
      selected: values[key] || "10",
      help_text: "Enter the final level-1 score after species adjustments.",
      options: Array.from({ length: 30 }, (_, index) => {
        const value = String(index + 1);
        return { value, label: value };
      }),
    })),
  };
}

export function buildDndCharacterCreateContext({
  dbPath,
  campaign,
  campaignConfig,
  values,
}: {
  dbPath: string;
  campaign: CampaignViewModel;
  campaignConfig: Record<string, unknown>;
  values: Record<string, unknown>;
}): DndCreateContext {
  const normalizedValues = normalizeCharacterAuthoringValues(values);
  if (!campaign.systems_library_slug || !existsSync(dbPath)) {
    return {
      lane: "dnd5e",
      builder_ready: false,
      values: normalizedValues,
      class_options: [],
      species_options: [],
      background_options: [],
      subclass_options: [],
      requires_subclass: false,
      choice_sections: [],
      preview: {},
      limitations: DND_CREATE_LIMITATIONS,
    };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const classRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "class")
      .filter((row) => row.is_enabled_override !== 0)
      .filter(dndSupportsNativeClassEntry);
    const speciesRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "race")
      .filter((row) => row.is_enabled_override !== 0)
      .filter((row) => dndSupportsSubordinateSource(row.source_id));
    const backgroundRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "background")
      .filter((row) => row.is_enabled_override !== 0)
      .filter((row) => dndSupportsSubordinateSource(row.source_id));

    normalizedValues.class_slug = sanitizeDndEntrySelectionValue(normalizedValues.class_slug, classRows);
    normalizedValues.species_slug = sanitizeDndEntrySelectionValue(normalizedValues.species_slug, speciesRows);
    normalizedValues.background_slug = sanitizeDndEntrySelectionValue(normalizedValues.background_slug, backgroundRows);
    for (const abilityKey of DND_ABILITY_KEYS) {
      normalizedValues[abilityKey] = String(Math.min(30, Math.max(1, createContextInteger(normalizedValues[abilityKey], 10))));
    }

    const selectedClass = selectedDndEntry(classRows, normalizedValues.class_slug);
    const subclassRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "subclass")
      .filter((row) => row.is_enabled_override !== 0)
      .filter((row) => dndSupportsNativeSubclassEntry(row, selectedClass));
    normalizedValues.subclass_slug = sanitizeDndEntrySelectionValue(normalizedValues.subclass_slug, subclassRows);
    const selectedSpecies = selectedDndEntry(speciesRows, normalizedValues.species_slug);
    const selectedBackground = selectedDndEntry(backgroundRows, normalizedValues.background_slug);
    const requiresSubclass = dndClassRequiresSubclassAtLevelOne(selectedClass);

    return {
      lane: "dnd5e",
      builder_ready: Boolean(classRows.length && speciesRows.length && backgroundRows.length),
      values: normalizedValues,
      class_options: classRows.map(dndEntryOption),
      species_options: speciesRows.map(dndEntryOption),
      background_options: backgroundRows.map(dndEntryOption),
      subclass_options: subclassRows.map(dndEntryOption),
      requires_subclass: requiresSubclass,
      choice_sections: [dndAbilityChoiceSection(normalizedValues)],
      preview: dndCreatePreview({ selectedClass, selectedSpecies, selectedBackground, values: normalizedValues }),
      limitations: DND_CREATE_LIMITATIONS,
    };
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return {
        lane: "dnd5e",
        builder_ready: false,
        values: normalizedValues,
        class_options: [],
        species_options: [],
        background_options: [],
        subclass_options: [],
        requires_subclass: false,
        choice_sections: [],
        preview: {},
        limitations: DND_CREATE_LIMITATIONS,
      };
    }
    throw error;
  } finally {
    database.close();
  }
}

function assertDndPilotEntry(row: SystemsEntryRow | null, expectedTitle: string, expectedType: string, fieldLabel: string): SystemsEntryRow {
  if (!row) {
    throw new Error(`${fieldLabel} is required for the DND-5E create pilot.`);
  }
  if (
    normalizeDndSourceId(row.source_id) !== DND_PHB_SOURCE_ID ||
    normalizeLookup(row.title) !== expectedTitle ||
    String(row.entry_type || "") !== expectedType
  ) {
    throw new Error("DND-5E character creation submit currently supports only the PHB Fighter / Human / Soldier pilot lane.");
  }
  return row;
}

function dndSystemsRef(row: SystemsEntryRow): Record<string, unknown> {
  const metadata = parseJsonRecord(row.metadata_json);
  const ref: Record<string, unknown> = {
    source_id: row.source_id,
    entry_key: row.entry_key,
    slug: row.slug,
    title: row.title,
    entry_type: row.entry_type,
  };
  if (Object.keys(metadata).length > 0) {
    ref.metadata = metadata;
  }
  return ref;
}

function dndAbilityScores(values: Record<string, string>) {
  return Object.fromEntries(
    DND_ABILITY_KEYS.map((key) => {
      const score = Math.min(30, Math.max(1, createContextInteger(values[key], 10)));
      return [
        key,
        {
          score,
          modifier: abilityModifier(score),
          save_bonus: abilityModifier(score) + (key === "str" || key === "con" ? 2 : 0),
        },
      ];
    }),
  );
}

function dndAbilityScoreValue(abilityScores: Record<string, unknown>, key: (typeof DND_ABILITY_KEYS)[number]): number {
  return createContextInteger(asRecord(abilityScores[key]).score, 10);
}

function dndSkillBonus(abilityScores: Record<string, unknown>, abilityKey: (typeof DND_ABILITY_KEYS)[number], proficient: boolean): number {
  return abilityModifier(dndAbilityScoreValue(abilityScores, abilityKey)) + (proficient ? 2 : 0);
}

function dndPilotEquipmentCatalog(): Array<Record<string, unknown>> {
  return [
    {
      id: "chain-mail-1",
      name: "Chain Mail",
      default_quantity: 1,
      weight: "55 lb.",
      is_equipped: true,
      supports_equipped_state: true,
      tags: ["armor"],
    },
    {
      id: "shield-1",
      name: "Shield",
      default_quantity: 1,
      weight: "6 lb.",
      is_equipped: true,
      supports_equipped_state: true,
      tags: ["shield", "armor"],
    },
    {
      id: "longsword-1",
      name: "Longsword",
      default_quantity: 1,
      weight: "3 lb.",
      is_equipped: true,
      supports_equipped_state: true,
      weapon_wield_mode: "main-hand",
      weapon_wield_modes: ["main-hand", "two-handed"],
      tags: ["weapon", "martial weapon", "melee weapon"],
    },
    {
      id: "light-crossbow-1",
      name: "Light Crossbow",
      default_quantity: 1,
      weight: "5 lb.",
      tags: ["weapon", "simple weapon", "ranged weapon"],
    },
    {
      id: "crossbow-bolts-1",
      name: "Crossbow Bolts",
      default_quantity: 20,
      weight: "1.5 lb.",
      tags: ["ammunition"],
    },
    {
      id: "explorers-pack-1",
      name: "Explorer's Pack",
      default_quantity: 1,
      weight: "59 lb.",
      tags: ["gear"],
    },
    {
      id: "insignia-rank-1",
      name: "Insignia of Rank",
      default_quantity: 1,
      weight: "light",
      tags: ["background"],
    },
    {
      id: "starting-coin-1",
      name: "Starting Coin",
      is_currency_only: true,
      currency: { cp: 0, sp: 0, ep: 0, gp: 10, pp: 0 },
    },
  ];
}

function dndPilotAttacks(abilityScores: Record<string, unknown>): Array<Record<string, unknown>> {
  const strengthModifier = abilityModifier(dndAbilityScoreValue(abilityScores, "str"));
  const dexterityModifier = abilityModifier(dndAbilityScoreValue(abilityScores, "dex"));
  return [
    {
      name: "Longsword",
      category: "melee weapon",
      attack_bonus: strengthModifier + 2,
      damage: `1d8${strengthModifier >= 0 ? "+" : ""}${strengthModifier} slashing`,
      notes: "Versatile (1d10). Pilot lane uses a shield-and-longsword starting package.",
      equipment_ref: "longsword-1",
    },
    {
      name: "Light Crossbow",
      category: "ranged weapon",
      attack_bonus: dexterityModifier + 2,
      damage: `1d8${dexterityModifier >= 0 ? "+" : ""}${dexterityModifier} piercing`,
      notes: "Ammunition, loading, range 80/320.",
      equipment_ref: "light-crossbow-1",
    },
  ];
}

export function buildDndCreateCharacter({
  dbPath,
  campaign,
  campaignConfig,
  values,
}: {
  dbPath: string;
  campaign: CampaignViewModel;
  campaignConfig: Record<string, unknown>;
  values: Record<string, unknown>;
}): DndCreateBuildResult {
  const name = normalizeCreateName(values.name);
  if (!name) {
    throw new Error("Character name is required.");
  }
  const characterSlug = normalizeCharacterSlug(cleanScalar(values.character_slug), name);
  if (!characterSlug) {
    throw new Error("Character slug is required.");
  }
  if (!campaign.systems_library_slug || !existsSync(dbPath)) {
    throw new Error("DND-5E character creation requires an enabled Systems library.");
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const classRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "class")
      .filter((row) => row.is_enabled_override !== 0)
      .filter(dndSupportsNativeClassEntry);
    const speciesRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "race")
      .filter((row) => row.is_enabled_override !== 0)
      .filter((row) => dndSupportsSubordinateSource(row.source_id));
    const backgroundRows = loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "background")
      .filter((row) => row.is_enabled_override !== 0)
      .filter((row) => dndSupportsSubordinateSource(row.source_id));

    const normalizedValues = normalizeCharacterAuthoringValues(values);
    normalizedValues.class_slug = sanitizeDndEntrySelectionValue(normalizedValues.class_slug, classRows);
    normalizedValues.species_slug = sanitizeDndEntrySelectionValue(normalizedValues.species_slug, speciesRows);
    normalizedValues.background_slug = sanitizeDndEntrySelectionValue(normalizedValues.background_slug, backgroundRows);
    const selectedClass = assertDndPilotEntry(
      selectedDndEntry(classRows, normalizedValues.class_slug),
      DND_PILOT_CLASS,
      "class",
      "Class",
    );
    const selectedSpecies = assertDndPilotEntry(
      selectedDndEntry(speciesRows, normalizedValues.species_slug),
      DND_PILOT_SPECIES,
      "race",
      "Species",
    );
    const selectedBackground = assertDndPilotEntry(
      selectedDndEntry(backgroundRows, normalizedValues.background_slug),
      DND_PILOT_BACKGROUND,
      "background",
      "Background",
    );
    if (isPresent(normalizedValues.subclass_slug)) {
      throw new Error("DND-5E character creation submit currently does not support subclass choices.");
    }

    const classMetadata = parseJsonRecord(selectedClass.metadata_json);
    const speciesMetadata = parseJsonRecord(selectedSpecies.metadata_json);
    const hitDie = createContextInteger(classMetadata.hit_die, 10);
    const abilityScores = dndAbilityScores(normalizedValues);
    const conModifier = abilityModifier(dndAbilityScoreValue(abilityScores, "con"));
    const maxHp = Math.max(1, hitDie + conModifier);
    const createdAt = new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
    const speciesSpeed = createContextInteger(firstPresent(speciesMetadata.speed, speciesMetadata.walk_speed), 30);
    const equipmentCatalog = dndPilotEquipmentCatalog();
    const definition: Record<string, unknown> = {
      campaign_slug: campaign.slug,
      character_slug: characterSlug,
      name,
      status: "active",
      system: "DND-5E",
      profile: {
        class_level_text: "Fighter 1",
        classes: [
          {
            class_name: "Fighter",
            level: 1,
            hit_die_faces: hitDie,
            systems_ref: dndSystemsRef(selectedClass),
          },
        ],
        species: "Human",
        species_ref: dndSystemsRef(selectedSpecies),
        background: "Soldier",
        background_ref: dndSystemsRef(selectedBackground),
        alignment: "",
        size: String(firstPresent(speciesMetadata.size, "Medium")),
        experience_model: "Milestone",
      },
      stats: {
        max_hp: maxHp,
        armor_class: 18,
        initiative_bonus: abilityModifier(dndAbilityScoreValue(abilityScores, "dex")),
        speed: `${speciesSpeed} ft.`,
        proficiency_bonus: 2,
        passive_perception: 10 + dndSkillBonus(abilityScores, "wis", false),
        passive_insight: 10 + dndSkillBonus(abilityScores, "wis", false),
        passive_investigation: 10 + dndSkillBonus(abilityScores, "int", false),
        ability_scores: abilityScores,
      },
      skills: [
        { name: "Athletics", bonus: dndSkillBonus(abilityScores, "str", true), proficiency_level: "proficient" },
        { name: "Intimidation", bonus: dndSkillBonus(abilityScores, "cha", true), proficiency_level: "proficient" },
        { name: "Perception", bonus: dndSkillBonus(abilityScores, "wis", false), proficiency_level: "none" },
      ],
      proficiencies: {
        armor: ["All armor", "Shields"],
        weapons: ["Simple weapons", "Martial weapons"],
        tools: ["One gaming set", "Vehicles (land)"],
        languages: asArray(speciesMetadata.languages).map(String).filter(Boolean),
        tool_expertise: [],
      },
      attacks: dndPilotAttacks(abilityScores),
      features: [
        {
          id: "fighting-style-1",
          name: "Fighting Style",
          category: "class_feature",
          source: "PHB",
          description_markdown: "Pilot DND-5E character creation records the Fighter starting feature as reference text only.",
        },
        {
          id: "second-wind-1",
          name: "Second Wind",
          category: "class_feature",
          tracker_ref: "second-wind",
          source: "PHB",
          description_markdown: "You have one use of Second Wind. Full Fighter feature automation remains outside this pilot slice.",
        },
      ],
      spellcasting: {},
      equipment_catalog: equipmentCatalog,
      reference_notes: {
        additional_notes_markdown: "Created by the TypeScript DND-5E pilot lane. Full native builder parity remains pending.",
        allies_and_organizations_markdown: "",
        custom_sections: [],
      },
      resource_templates: [
        {
          id: "second-wind",
          label: "Second Wind",
          category: "class_feature",
          max: 1,
          initial_current: 1,
          reset_on: "short_rest",
          reset_to: "max",
          rest_behavior: "restore_full",
          display_order: 10,
        },
      ],
      source: {
        source_path: DND_CHARACTER_CREATE_SOURCE_PATH,
        source_type: DND_CHARACTER_CREATE_SOURCE_TYPE,
        imported_from: DND_CHARACTER_CREATE_IMPORTED_FROM,
        imported_at: createdAt,
        parse_warnings: [],
      },
    };
    const importMetadata = {
      campaign_slug: campaign.slug,
      character_slug: characterSlug,
      source_path: DND_CHARACTER_CREATE_SOURCE_PATH,
      imported_at_utc: createdAt,
      parser_version: DND_CHARACTER_CREATE_VERSION,
      import_status: "managed",
      warnings: [
        "Created by the narrow TypeScript DND-5E pilot lane; full level-one builder parity remains pending.",
      ],
    };
    return { definition, importMetadata };
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      throw new Error("DND-5E character creation requires Systems source data.");
    }
    throw error;
  } finally {
    database.close();
  }
}

function martialArtRankRecords(metadata: Record<string, unknown>, body: Record<string, unknown>) {
  const martialArtBody = asRecord(body.xianxia_martial_art);
  const rawRecords =
    metadata.xianxia_martial_art_rank_records ??
    metadata.martial_art_rank_records ??
    martialArtBody.xianxia_martial_art_rank_records ??
    martialArtBody.rank_records;
  return asArray(rawRecords)
    .map(asRecord)
    .filter((record) => record.rank_available_in_seed !== false)
    .map((record) => ({ ...record, rank_key: normalizeRankKey(record.rank_key) }))
    .filter((record) => Boolean(XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[String(record.rank_key || "")])) as Array<
    Record<string, unknown> & { rank_key: string }
  >;
}

function truthy(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}

function buildXianxiaMartialArtOption(row: SystemsEntryRow, customSourceId: string) {
  const metadata = parseJsonRecord(row.metadata_json);
  const body = parseJsonRecord(row.body_json);
  const martialArtBody = asRecord(body.xianxia_martial_art);
  const rankRecords = martialArtRankRecords(metadata, body);
  let rankRefs = Object.fromEntries(
    rankRecords
      .map((record) => [String(record.rank_key || ""), String(record.rank_ref || "").trim()])
      .filter(([rankKey, rankRef]) => rankKey && rankRef),
  ) as Record<string, string>;
  let availableRankKeys = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key).filter((rankKey) => rankKey in rankRefs);
  const customMartialArt =
    truthy(metadata.xianxia_custom_martial_art) ||
    truthy(metadata.custom_martial_art) ||
    truthy(martialArtBody.xianxia_custom_martial_art) ||
    (customSourceId && row.source_id.toLowerCase() === customSourceId.toLowerCase());
  if (customMartialArt && availableRankKeys.length === 0) {
    availableRankKeys = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key);
    rankRefs = Object.fromEntries(availableRankKeys.map((rankKey) => [rankKey, `xianxia:${row.slug}:${rankKey}`]));
  }

  const rawSortOrder = metadata.martial_art_catalog_order;
  const parsedSortOrder = Number(rawSortOrder);
  return {
    slug: normalizeMartialArtOptionSlug(row.slug),
    title: String(row.title || "").trim(),
    entry_key: String(row.entry_key || "").trim(),
    entry_type: String(row.entry_type || "").trim(),
    source_id: String(row.source_id || "").trim(),
    library_slug: String(row.library_slug || "").trim(),
    martial_art_style: String(
      firstPresent(
        metadata.xianxia_martial_art_style,
        metadata.martial_art_style,
        martialArtBody.style,
        martialArtBody.martial_art_style,
      ),
    ).trim(),
    available_rank_keys: availableRankKeys,
    available_rank_labels: availableRankKeys
      .map((rankKey) => XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[rankKey])
      .filter(Boolean),
    available_starting_rank_keys: ["initiate", "novice"].filter((rankKey) => rankKey in rankRefs),
    rank_refs: rankRefs,
    rank_records_status: String(metadata.rank_records_status || "").trim(),
    custom_martial_art: customMartialArt,
    sort_order: Number.isFinite(parsedSortOrder) ? Math.trunc(parsedSortOrder) : 10000,
  };
}

function xianxiaGenericTechniqueSortOrder(metadata: Record<string, unknown>, techniqueBody: Record<string, unknown>): number {
  const parsed = Number(
    firstPresent(metadata.generic_technique_catalog_order, metadata.catalog_order, techniqueBody.catalog_order),
  );
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 10000;
}

function buildXianxiaGenericTechniqueOption(row: SystemsEntryRow, selectedEntryKeys: Set<string>) {
  const metadata = parseJsonRecord(row.metadata_json);
  const body = parseJsonRecord(row.body_json);
  const techniqueBody = asRecord(body.xianxia_generic_technique);
  const genericTechniqueKey = normalizeGenericTechniqueKey(
    firstPresent(metadata.generic_technique_key, metadata.xianxia_generic_technique_key, techniqueBody.key),
  );
  const entryKey = String(row.entry_key || "").trim();
  if (!entryKey || !genericTechniqueKey || XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS.has(genericTechniqueKey)) {
    return null;
  }

  const insightCost = Math.max(0, Number.parseInt(String(firstPresent(metadata.insight_cost, techniqueBody.insight_cost) || "0"), 10) || 0);
  if (insightCost <= 0) {
    return null;
  }
  const name = String(row.title || "").trim() || "Generic Technique";
  const slug = String(row.slug || "").trim();
  const selected = [entryKey, slug, genericTechniqueKey, name]
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean)
    .some((value) => selectedEntryKeys.has(value));

  return {
    name,
    entry_key: entryKey,
    systems_ref: {
      library_slug: String(row.library_slug || "").trim(),
      source_id: String(row.source_id || "").trim(),
      entry_key: entryKey,
      slug,
      title: name,
      entry_type: String(row.entry_type || "").trim(),
    },
    generic_technique_key: genericTechniqueKey,
    insight_cost: insightCost,
    support_state: String(
      firstPresent(
        metadata.support_state,
        metadata.xianxia_support_state,
        techniqueBody.support_state,
        techniqueBody.xianxia_support_state,
      ) || "",
    ).trim(),
    prerequisites: parseTags(firstPresent(metadata.prerequisites, techniqueBody.prerequisites)),
    resource_costs: parseTags(firstPresent(metadata.resource_costs, techniqueBody.resource_costs)),
    range_tags: parseTags(firstPresent(metadata.range_tags, techniqueBody.range_tags)),
    effort_tags: parseTags(firstPresent(metadata.effort_tags, techniqueBody.effort_tags)),
    reset_cadence: String(firstPresent(metadata.reset_cadence, techniqueBody.reset_cadence) || "").trim(),
    learnable_without_master: truthy(firstPresent(metadata.learnable_without_master, techniqueBody.learnable_without_master)),
    requires_master: truthy(firstPresent(metadata.requires_master, techniqueBody.requires_master)),
    sort_order: xianxiaGenericTechniqueSortOrder(metadata, techniqueBody),
    selected,
  };
}

export function xianxiaKnownGenericTechniqueOptionKeys(definition: Record<string, unknown>): string[] {
  const markers = new Set<string>();
  for (const rawTechnique of asArray(asRecord(definition.xianxia).generic_techniques)) {
    const technique = asRecord(rawTechnique);
    const systemsRef = asRecord(technique.systems_ref);
    for (const value of [
      technique.entry_key,
      systemsRef.entry_key,
      technique.slug,
      systemsRef.slug,
      technique.name,
      technique.title,
      systemsRef.title,
    ]) {
      const normalized = String(value || "").trim().toLowerCase();
      if (normalized) {
        markers.add(normalized);
      }
    }
    const genericTechniqueKey = normalizeGenericTechniqueKey(
      firstPresent(technique.generic_technique_key, technique.technique_key, systemsRef.slug),
    );
    if (genericTechniqueKey) {
      markers.add(genericTechniqueKey);
    }
  }
  return [...markers];
}

export function listXianxiaManualImportMartialArtOptions(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
) {
  if (!campaign.systems_library_slug || !existsSync(dbPath)) {
    return [];
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const customSourceId = campaignCustomSourceId(campaign.slug);
    return loadEnabledMartialArtRows(database, campaign, campaignConfig)
      .filter((row) => row.is_enabled_override !== 0)
      .map((row) => buildXianxiaMartialArtOption(row, customSourceId))
      .sort((left, right) => {
        if (left.sort_order !== right.sort_order) {
          return left.sort_order - right.sort_order;
        }
        const titleComparison = left.title.toLowerCase().localeCompare(right.title.toLowerCase());
        if (titleComparison !== 0) {
          return titleComparison;
        }
        return left.source_id.toLowerCase().localeCompare(right.source_id.toLowerCase());
      });
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return [];
    }
    throw error;
  } finally {
    database.close();
  }
}

export function listXianxiaCreateGenericTechniqueOptions(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  selectedEntryKeys: string[] = [],
) {
  if (!campaign.systems_library_slug || !existsSync(dbPath)) {
    return [];
  }

  const selected = new Set(selectedEntryKeys.map((entryKey) => String(entryKey || "").trim().toLowerCase()).filter(Boolean));
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "generic_technique")
      .filter((row) => row.is_enabled_override !== 0)
      .map((row) => buildXianxiaGenericTechniqueOption(row, selected))
      .filter((option): option is NonNullable<typeof option> => option !== null)
      .sort((left, right) => {
        if (left.sort_order !== right.sort_order) {
          return left.sort_order - right.sort_order;
        }
        const titleComparison = left.name.toLowerCase().localeCompare(right.name.toLowerCase());
        if (titleComparison !== 0) {
          return titleComparison;
        }
        return left.systems_ref.source_id.toLowerCase().localeCompare(right.systems_ref.source_id.toLowerCase());
      });
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return [];
    }
    throw error;
  } finally {
    database.close();
  }
}

function normalizeCharacterAuthoringValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean).join(",");
  }
  return value === null || value === undefined ? "" : String(value);
}

function normalizeCharacterAuthoringValues(values: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [String(key), normalizeCharacterAuthoringValue(value)]),
  );
}

function isPresent(value: unknown): boolean {
  return String(value ?? "").trim().length > 0;
}

function coerceInt(value: string, fieldName: string): number {
  const candidate = String(value ?? "").trim();
  if (!candidate) {
    return 0;
  }
  if (!/^[+-]?\d+$/.test(candidate)) {
    throw new Error(`Invalid value for ${fieldName}.`);
  }
  return Number.parseInt(candidate, 10);
}

function parseStrictInt(value: unknown, fieldLabel: string): number {
  const candidate = cleanScalar(value);
  if (!/^[+-]?\d+$/.test(candidate)) {
    throw new Error(`${fieldLabel} must be a whole number.`);
  }
  return Number.parseInt(candidate, 10);
}

function coerceLooseInt(value: unknown, defaultValue = 0): number {
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }
  const candidate = String(value ?? "").trim();
  if (!candidate) {
    return defaultValue;
  }
  const parsed = Number.parseInt(candidate, 10);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function nonNegativeLooseInt(value: unknown, defaultValue = 0): number {
  return Math.max(0, coerceLooseInt(value, defaultValue));
}

function normalizeRealm(value: string): string {
  const canonical = String(value || "")
    .trim()
    .toLowerCase();
  if (canonical === "mortal" || canonical === "immortal" || canonical === "divine") {
    return canonical[0].toUpperCase() + canonical.slice(1);
  }
  return "Mortal";
}

function normalizeHonor(value: string): string {
  const canonical = String(value || "").trim().toLowerCase();
  for (const honor of ["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"]) {
    if (honor.toLowerCase() === canonical) {
      return honor;
    }
  }
  return "Honorable";
}

function collectIndexedRows(values: Record<string, string>, prefix: string): Array<Record<string, string>> {
  const rowNumbers = new Set<number>();
  for (const key of Object.keys(values)) {
    const match = key.match(new RegExp(`^${prefix}_(\\d+)_(.+)$`));
    if (match) {
      rowNumbers.add(Number(match[1]));
    }
  }

  return Array.from(rowNumbers)
    .sort((left, right) => left - right)
    .map((rowIndex) => {
      const normalizedRow: Record<string, string> = {};
      const sourceFieldPrefix = `${prefix}_${rowIndex}_`;
      for (const [key, value] of Object.entries(values)) {
        if (key.startsWith(sourceFieldPrefix)) {
          normalizedRow[key.slice(sourceFieldPrefix.length)] = value;
        }
      }
      return normalizedRow;
    });
}

function extractValues(values: Record<string, string>, keys: string[]): string {
  for (const key of keys) {
    const value = values[key];
    if (isPresent(value)) {
      return value;
    }
  }
  return "";
}

function normalizeCharacterName(value: string): string {
  return String(value || "").trim();
}

function normalizeCreateName(value: unknown): string {
  return cleanScalar(value).split(/\s+/).filter(Boolean).join(" ");
}

function slugifyText(value: string): string {
  if (!value.trim()) {
    return "";
  }
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/(^-|-$)+/g, "");
}

function normalizeCharacterSlug(value: string, fallbackSource: string): string {
  return slugifyText(value) || slugifyText(fallbackSource);
}

function countTextRows(value: string): number {
  return String(value || "")
    .split(/\r?\n/)
    .filter((row) => row.trim().length > 0).length;
}

function splitTextLines(value: unknown): string[] {
  return String(value ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function splitPipeRow(value: string): string[] {
  return value
    .split("|")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function lookupKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function humanizeSlug(value: string): string {
  return value
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function parseTags(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  return String(value ?? "")
    .split(/[,|]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function cleanScalar(value: unknown): string {
  if (Array.isArray(value)) {
    return cleanScalar(value[0]);
  }
  return value === null || value === undefined ? "" : String(value).trim();
}

function scalarList(value: unknown): unknown[] {
  if (value === null || value === undefined || value === "") {
    return [];
  }
  if (Array.isArray(value)) {
    return value;
  }
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>);
  }
  return [value];
}

function formatLabelList(values: string[]): string {
  if (values.length === 0) {
    return "";
  }
  if (values.length === 1) {
    return values[0] ?? "";
  }
  if (values.length === 2) {
    return `${values[0]} and ${values[1]}`;
  }
  return `${values.slice(0, -1).join(", ")}, and ${values[values.length - 1]}`;
}

function normalizeToken(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function parseBoolean(value: unknown): boolean | undefined {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  const normalized = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on", "equipped", "enabled", "used", "recorded"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off", "disabled"].includes(normalized)) {
    return false;
  }
  return undefined;
}

function appendNotesSection(baseNotes: string, title: string, lines: string[]): string {
  const body = lines.map((line) => `- ${line}`).join("\n");
  return [baseNotes.trim(), `## ${title}\n\n${body}`].filter(Boolean).join("\n\n");
}

function buildXianxiaManualImportMartialArtRows(values: Record<string, string>) {
  const rowNumbers = new Set<number>();
  for (const key of Object.keys(values)) {
    const match = key.match(/^martial_art_(\d+)_(slug|name|rank|teacher|breakthrough|notes)$/);
    if (match) {
      rowNumbers.add(Number(match[1]));
    }
  }
  const rowCount = Math.max(3, ...rowNumbers);
  return Array.from({ length: rowCount }, (_, index) => {
    const rowIndex = index + 1;
    return {
      index: rowIndex,
      slug_input_name: `martial_art_${rowIndex}_slug`,
      name_input_name: `martial_art_${rowIndex}_name`,
      rank_input_name: `martial_art_${rowIndex}_rank`,
      teacher_input_name: `martial_art_${rowIndex}_teacher`,
      breakthrough_input_name: `martial_art_${rowIndex}_breakthrough`,
      notes_input_name: `martial_art_${rowIndex}_notes`,
      selected_slug: values[`martial_art_${rowIndex}_slug`] || "",
      name: values[`martial_art_${rowIndex}_name`] || "",
      rank: values[`martial_art_${rowIndex}_rank`] || "",
      teacher: values[`martial_art_${rowIndex}_teacher`] || "",
      breakthrough: values[`martial_art_${rowIndex}_breakthrough`] || "",
      notes: values[`martial_art_${rowIndex}_notes`] || "",
    };
  });
}

export function buildXianxiaManualImportContext({
  dbPath,
  campaign,
  campaignConfig,
  values,
}: {
  dbPath: string;
  campaign: CampaignViewModel;
  campaignConfig: Record<string, unknown>;
  values: Record<string, unknown>;
}) {
  const normalizedValues = normalizeCharacterAuthoringValues(values);
  return {
    values: normalizedValues,
    realm_choices: ["Mortal", "Immortal", "Divine"],
    honor_choices: ["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"],
    martial_art_rank_choices: XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => ({ ...rank })),
    martial_art_rows: buildXianxiaManualImportMartialArtRows(normalizedValues),
    attribute_fields: XIANXIA_ATTRIBUTE_KEYS.map((key) => ({
      key,
      label: XIANXIA_ATTRIBUTE_LABELS[key],
      input_name: `attribute_${key}`,
      value: normalizedValues[`attribute_${key}`] || "0",
    })),
    effort_fields: XIANXIA_EFFORT_KEYS.map((key) => ({
      key,
      label: XIANXIA_EFFORT_LABELS[key],
      input_name: `effort_${key}`,
      value: normalizedValues[`effort_${key}`] || "0",
    })),
    energy_fields: XIANXIA_ENERGY_KEYS.map((key) => ({
      key,
      label: key[0].toUpperCase() + key.slice(1),
      max_input_name: `energy_${key}_max`,
      max_value: normalizedValues[`energy_${key}_max`] || "0",
    })),
    martial_art_options: listXianxiaManualImportMartialArtOptions(dbPath, campaign, campaignConfig),
    preview: null,
  };
}

export function buildXianxiaManualImportPayload(values: Record<string, string>): Record<string, unknown> {
  const ignoredInputs = new Set(["active_stance", "active_aura"]);
  const payload: Record<string, string> = {};
  for (const [key, value] of Object.entries(values)) {
    if (!ignoredInputs.has(key)) {
      payload[key] = value;
    }
  }
  return {
    ...payload,
    energy_maxima: {
      jing: values.energy_jing_max || "",
      qi: values.energy_qi_max || "",
      shen: values.energy_shen_max || "",
    },
    state: {
      xianxia: {
        currency: {
          coin: values.coin || "",
          supply: values.supply || "",
          spirit_stones: values.spirit_stones || "",
        },
        notes: {
          player_notes_markdown: values.player_notes_markdown || "",
        },
      },
    },
  };
}

function xianxiaIntegerMap(values: Record<string, string>, keys: readonly string[], prefix: string): Record<string, number> {
  return Object.fromEntries(keys.map((key) => [key, coerceLooseInt(values[`${prefix}${key}`], 0)]));
}

function parseSkillText(value: unknown): Array<Record<string, string> | string> {
  return splitTextLines(value).map((line) => {
    const parts = splitPipeRow(line);
    if (parts.length <= 1) {
      return parts[0] || "";
    }
    return { name: parts[0], notes: parts[1] };
  });
}

function collectTrainedSkills(values: Record<string, string>): { trainedSkills: string[]; skillNotes: string[] } {
  const rows: Array<Record<string, string> | string> = [
    ...parseSkillText(values.trained_skills_text),
    ...parseSkillText(values.skills_text),
    ...collectIndexedRows(values, "trained_skill"),
  ];
  const seen = new Set<string>();
  const trainedSkills: string[] = [];
  const skillNotes: string[] = [];
  for (const row of rows) {
    if (typeof row === "string") {
      const name = row.trim();
      const key = name.toLowerCase();
      if (name && !seen.has(key)) {
        seen.add(key);
        trainedSkills.push(name);
      }
      continue;
    }
    const name = String(row.name || row.label || row.skill || "").trim();
    const key = name.toLowerCase();
    if (name && !seen.has(key)) {
      seen.add(key);
      trainedSkills.push(name);
    }
    const notes = String(row.notes || row.note || row.description || row.source_notes || row.text || "").trim();
    if (name && notes) {
      skillNotes.push(`${name}: ${notes}`);
    }
  }
  return { trainedSkills, skillNotes };
}

function parseInventoryText(value: unknown): Array<Record<string, unknown>> {
  return splitTextLines(value).map((line) => {
    const parts = splitPipeRow(line);
    const row: Record<string, unknown> = { name: parts[0] || "" };
    if (parts[1]) {
      row.quantity = parts[1];
    }
    if (parts[2]) {
      row.tags = parseTags(parts[2]);
    }
    if (parts[3]) {
      row.notes = parts[3];
    }
    return row;
  });
}

function normalizeInventoryItemType(rawType: unknown, defaultValue = XIANXIA_ITEM_TYPE_DEFAULT): string {
  const normalized = normalizeToken(rawType);
  return normalized ? (XIANXIA_ITEM_TYPE_ALIASES[normalized] ?? defaultValue) : defaultValue;
}

function normalizeInventoryItemNature(rawNature: unknown): string {
  return XIANXIA_ITEM_NATURE_ALIASES[normalizeToken(rawNature)] ?? "Mundane";
}

function normalizeInventoryLegacyTags(
  tags: string[],
  itemType: unknown,
): { itemType: string; tags: string[]; legacyTags: string[] } {
  const explicitType = normalizeInventoryItemType(itemType, "");
  const normalizedTags: string[] = [];
  const legacyTags: string[] = [];
  const inferredTypes = new Set<string>();
  const nonMiscInferredTypes = new Set<string>();
  for (const tag of tags) {
    const normalizedTag = String(tag ?? "").trim();
    if (!normalizedTag) {
      continue;
    }
    normalizedTags.push(normalizedTag);
    const mappedType = XIANXIA_INVENTORY_TAG_TYPE_ALIASES[normalizeToken(normalizedTag)];
    if (mappedType) {
      inferredTypes.add(mappedType);
      if (mappedType !== XIANXIA_ITEM_TYPE_DEFAULT) {
        nonMiscInferredTypes.add(mappedType);
      }
    } else {
      legacyTags.push(normalizedTag);
    }
  }

  if (explicitType) {
    return { itemType: explicitType, tags: normalizedTags, legacyTags };
  }
  if (nonMiscInferredTypes.size === 1) {
    return { itemType: [...nonMiscInferredTypes][0] ?? XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
  }
  if (nonMiscInferredTypes.size > 1) {
    return { itemType: XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
  }
  if (inferredTypes.size === 1) {
    return { itemType: [...inferredTypes][0] ?? XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
  }
  return { itemType: XIANXIA_ITEM_TYPE_DEFAULT, tags: normalizedTags, legacyTags };
}

function normalizeInventoryRows(values: Record<string, string>): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [
    ...parseInventoryText(values.inventory_text),
    ...collectIndexedRows(values, "manual_item"),
    ...collectIndexedRows(values, "inventory_item"),
  ];
  return rows
    .map<Record<string, unknown> | null>((row) => {
      const name = String(row.name || row.label || "").trim();
      const id = String(row.id || row.item_id || "").trim() || slugifyText(name);
      if (!name && !id) {
        return null;
      }
      const tags = parseTags(row.tags);
      const tagNormalization = normalizeInventoryLegacyTags(tags, row.item_type || row.type);
      const itemType = tagNormalization.itemType;
      const itemNature = normalizeInventoryItemNature(row.item_nature || row.nature);
      const explicitEquippable = parseBoolean(row.equippable);
      const isEquipped = parseBoolean(row.is_equipped);
      const normalized: Record<string, unknown> = {
        id,
        catalog_ref: String(row.catalog_ref || "").trim(),
        name,
        quantity: Math.max(0, coerceLooseInt(row.quantity, 1)),
        notes: String(row.notes || row.note || "").trim(),
        tags: tagNormalization.tags,
        item_type: itemType,
        item_nature: itemNature,
        equippable: explicitEquippable ?? (itemType === "Weapon" || itemType === "Armor"),
        is_equipped: isEquipped ?? false,
      };
      if (tagNormalization.legacyTags.length > 0) {
        normalized.legacy_tags = tagNormalization.legacyTags;
      }
      return normalized;
    })
    .filter((row): row is Record<string, unknown> => Boolean(row));
}

function martialArtOptionLookup(options: Array<Record<string, unknown>>): Map<string, Record<string, unknown>> {
  const lookup = new Map<string, Record<string, unknown>>();
  for (const option of options) {
    for (const key of [option.slug, option.title, option.entry_key]) {
      const normalized = lookupKey(key);
      if (normalized) {
        lookup.set(normalized, option);
      }
    }
  }
  return lookup;
}

function matchMartialArtOption(row: Record<string, string>, lookup: Map<string, Record<string, unknown>>) {
  for (const key of [row.systems_ref_slug, row.martial_art_slug, row.slug, row.entry_key, row.name]) {
    const normalized = lookupKey(key);
    if (normalized && lookup.has(normalized)) {
      return lookup.get(normalized) || null;
    }
  }
  return null;
}

function martialArtSystemsRef(option: Record<string, unknown>): Record<string, string> {
  const ref: Record<string, string> = {};
  for (const key of ["library_slug", "source_id", "entry_key", "slug", "title", "entry_type"]) {
    const value = String(option[key] ?? "").trim();
    if (value) {
      ref[key] = value;
    }
  }
  return ref;
}

function learnedRankRefsForOption(option: Record<string, unknown>, rankKey: string): string[] {
  const normalizedRank = normalizeRankKey(rankKey);
  const rankIndex = (XIANXIA_MARTIAL_ART_RANK_ORDER as readonly string[]).indexOf(normalizedRank);
  if (rankIndex < 0) {
    return [];
  }
  const rankRefs = asRecord(option.rank_refs);
  const slug = String(option.slug || "").trim();
  return XIANXIA_MARTIAL_ART_RANK_ORDER.slice(0, rankIndex + 1)
    .map((rank) => String(rankRefs[rank] || (slug ? `xianxia:${slug}:${rank}` : "")).trim())
    .filter(Boolean);
}

function collectMartialArts(values: Record<string, string>, options: Array<Record<string, unknown>>): Record<string, unknown>[] {
  const lookup = martialArtOptionLookup(options);
  return collectIndexedRows(values, "martial_art")
    .map((row) => {
      const selectedOption = matchMartialArtOption(row, lookup);
      const name = String(row.name || row.label || row.title || selectedOption?.title || "").trim();
      if (!name) {
        return null;
      }
      const rankKey = normalizeRankKey(row.current_rank_key || row.current_rank || row.rank || row.rank_key || "");
      const payload: Record<string, unknown> = {
        name: selectedOption ? String(selectedOption.title || name).trim() : name,
      };
      if (selectedOption) {
        payload.systems_ref = martialArtSystemsRef(selectedOption);
        const rankStatus = String(selectedOption.rank_records_status || "").trim();
        if (rankStatus) {
          payload.rank_records_status = rankStatus;
        }
        if (selectedOption.custom_martial_art === true) {
          payload.custom_martial_art = true;
          payload.xianxia_custom_martial_art = true;
        }
      }
      if (rankKey) {
        payload.current_rank_key = rankKey;
        payload.current_rank = XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[rankKey] || humanizeSlug(rankKey);
        if (selectedOption) {
          payload.learned_rank_refs = learnedRankRefsForOption(selectedOption, rankKey);
        }
      }
      for (const key of ["teacher", "breakthrough", "notes"]) {
        const value = String(row[key] || "").trim();
        if (value) {
          payload[key] = value;
        }
      }
      return payload;
    })
    .filter((row): row is Record<string, unknown> => Boolean(row));
}

function nestedRecordValue(values: Record<string, unknown>, key: string): Record<string, unknown> {
  return asRecord(values[key]);
}

function validateCreationIntMap({
  values,
  nestedKey,
  prefix,
  keys,
  labels,
  points,
  max,
  groupLabel,
  unsupportedLabel,
}: {
  values: Record<string, unknown>;
  nestedKey: string;
  prefix: string;
  keys: readonly string[];
  labels: Record<string, string>;
  points: number;
  max: number;
  groupLabel: string;
  unsupportedLabel: string;
}): Record<string, number> {
  const errors: string[] = [];
  const missingLabels: string[] = [];
  const scores: Record<string, number> = {};
  const nested = nestedRecordValue(values, nestedKey);
  const unknownKeys = new Set<string>();
  for (const key of Object.keys(values)) {
    if (key.startsWith(prefix)) {
      const unprefixed = key.slice(prefix.length);
      if (!keys.includes(unprefixed)) {
        unknownKeys.add(unprefixed);
      }
    }
  }
  for (const key of Object.keys(nested)) {
    if (!keys.includes(key)) {
      unknownKeys.add(key);
    }
  }
  const unknown = [...unknownKeys].sort();
  if (unknown.length > 0) {
    errors.push(`Unsupported Xianxia ${unsupportedLabel}: ${unknown.join(", ")}.`);
  }

  for (const key of keys) {
    const label = labels[key] || key;
    const inputName = `${prefix}${key}`;
    const rawValue = Object.hasOwn(values, inputName) ? values[inputName] : nested[key];
    const cleaned = cleanScalar(rawValue);
    if (cleaned === "") {
      missingLabels.push(label);
      continue;
    }
    let score: number;
    try {
      score = parseStrictInt(cleaned, label);
    } catch (error) {
      errors.push(error instanceof Error ? error.message : `${label} must be a whole number.`);
      continue;
    }
    if (score < 0) {
      errors.push(`${label} cannot be negative.`);
      continue;
    }
    if (score > max) {
      errors.push(`${label} cannot exceed ${max} at character creation.`);
    }
    scores[key] = score;
  }

  if (missingLabels.length > 0) {
    errors.push(`Missing Xianxia ${unsupportedLabel}: ${formatLabelList(missingLabels)}.`);
  }
  if (Object.keys(scores).length === keys.length) {
    const total = Object.values(scores).reduce((sum, value) => sum + value, 0);
    if (total !== points) {
      errors.push(`Xianxia ${groupLabel} must spend exactly ${points} creation points; submitted total is ${total}.`);
    }
  }
  if (errors.length > 0) {
    throw new Error(errors.join(" "));
  }
  return Object.fromEntries(keys.map((key) => [key, scores[key] ?? 0]));
}

function validateXianxiaCreateAttributes(values: Record<string, unknown>): Record<string, number> {
  return validateCreationIntMap({
    values,
    nestedKey: "attributes",
    prefix: "attribute_",
    keys: XIANXIA_ATTRIBUTE_KEYS,
    labels: XIANXIA_ATTRIBUTE_LABELS,
    points: XIANXIA_ATTRIBUTE_CREATION_POINTS,
    max: XIANXIA_ATTRIBUTE_MAX_AT_CREATION,
    groupLabel: "Attributes",
    unsupportedLabel: "attributes",
  });
}

function validateXianxiaCreateEfforts(values: Record<string, unknown>): Record<string, number> {
  return validateCreationIntMap({
    values,
    nestedKey: "efforts",
    prefix: "effort_",
    keys: XIANXIA_EFFORT_KEYS,
    labels: XIANXIA_EFFORT_LABELS,
    points: XIANXIA_EFFORT_CREATION_POINTS,
    max: XIANXIA_EFFORT_MAX_AT_CREATION,
    groupLabel: "Efforts",
    unsupportedLabel: "efforts",
  });
}

function validateXianxiaCreateEnergies(values: Record<string, unknown>): Record<string, number> {
  const errors: string[] = [];
  const missingLabels: string[] = [];
  const scores: Record<string, number> = {};
  const nestedEnergies = nestedRecordValue(values, "energies");
  const nestedEnergyMaxima = nestedRecordValue(values, "energy_maxima");
  const unknownKeys = new Set<string>();
  for (const key of Object.keys(values)) {
    if (key.startsWith("energy_") && key !== "energy_maxima") {
      const unprefixed = key.slice("energy_".length);
      if (!XIANXIA_ENERGY_KEYS.includes(unprefixed as (typeof XIANXIA_ENERGY_KEYS)[number])) {
        unknownKeys.add(unprefixed);
      }
    }
  }
  for (const key of [...Object.keys(nestedEnergies), ...Object.keys(nestedEnergyMaxima)]) {
    if (!XIANXIA_ENERGY_KEYS.includes(key as (typeof XIANXIA_ENERGY_KEYS)[number])) {
      unknownKeys.add(key);
    }
  }
  const unknown = [...unknownKeys].sort();
  if (unknown.length > 0) {
    errors.push(`Unsupported Xianxia energies: ${unknown.join(", ")}.`);
  }

  for (const key of XIANXIA_ENERGY_KEYS) {
    const label = key[0]!.toUpperCase() + key.slice(1);
    let rawValue: unknown;
    if (Object.hasOwn(values, `energy_${key}`)) {
      rawValue = values[`energy_${key}`];
    } else if (Object.hasOwn(nestedEnergyMaxima, key)) {
      rawValue = nestedEnergyMaxima[key];
    } else if (Object.hasOwn(nestedEnergies, key)) {
      const nestedEnergy = asRecord(nestedEnergies[key]);
      rawValue = Object.keys(nestedEnergy).length > 0 ? nestedEnergy.max : nestedEnergies[key];
    }
    const cleaned = cleanScalar(rawValue);
    if (cleaned === "") {
      missingLabels.push(label);
      continue;
    }
    let score: number;
    try {
      score = parseStrictInt(cleaned, label);
    } catch (error) {
      errors.push(error instanceof Error ? error.message : `${label} must be a whole number.`);
      continue;
    }
    if (score < 0) {
      errors.push(`${label} cannot be negative.`);
      continue;
    }
    scores[key] = score;
  }

  if (missingLabels.length > 0) {
    errors.push(`Missing Xianxia energies: ${formatLabelList(missingLabels)}.`);
  }
  if (Object.keys(scores).length === XIANXIA_ENERGY_KEYS.length) {
    const total = Object.values(scores).reduce((sum, value) => sum + value, 0);
    if (total !== XIANXIA_ENERGY_CREATION_POINTS) {
      errors.push(
        `Xianxia Energies must spend exactly ${XIANXIA_ENERGY_CREATION_POINTS} creation points across Jing, Qi, and Shen; submitted total is ${total}.`,
      );
    }
  }
  if (errors.length > 0) {
    throw new Error(errors.join(" "));
  }
  return Object.fromEntries(XIANXIA_ENERGY_KEYS.map((key) => [key, scores[key] ?? 0]));
}

function validateXianxiaCreateManualArmorBonus(values: Record<string, unknown>): number {
  const durability = nestedRecordValue(values, "durability");
  const armor = nestedRecordValue(values, "armor");
  const rawValue = Object.hasOwn(values, "manual_armor_bonus")
    ? values.manual_armor_bonus
    : Object.hasOwn(values, "armor_bonus")
      ? values.armor_bonus
      : Object.hasOwn(durability, "manual_armor_bonus")
        ? durability.manual_armor_bonus
        : Object.hasOwn(durability, "armor_bonus")
          ? durability.armor_bonus
          : Object.hasOwn(armor, "manual_armor_bonus")
            ? armor.manual_armor_bonus
            : Object.hasOwn(armor, "armor_bonus")
              ? armor.armor_bonus
              : "";
  const cleaned = cleanScalar(rawValue);
  if (!cleaned) {
    return 0;
  }
  const manualArmorBonus = parseStrictInt(cleaned, "Manual armor bonus");
  if (manualArmorBonus < 0) {
    throw new Error("Manual armor bonus cannot be negative.");
  }
  return manualArmorBonus;
}

function validateXianxiaCreateDaoCurrent(values: Record<string, unknown>): number {
  const dao = nestedRecordValue(values, "dao");
  const rawValue = Object.hasOwn(values, "dao_current")
    ? values.dao_current
    : Object.hasOwn(dao, "current")
      ? dao.current
      : "";
  const cleaned = cleanScalar(rawValue);
  if (!cleaned) {
    return 0;
  }
  const daoCurrent = parseStrictInt(cleaned, "Starting Dao");
  if (daoCurrent < 0) {
    throw new Error("Starting Dao cannot be negative.");
  }
  if (daoCurrent > XIANXIA_DAO_DEFAULT_MAX) {
    throw new Error(`Starting Dao cannot exceed ${XIANXIA_DAO_DEFAULT_MAX} at character creation.`);
  }
  return daoCurrent;
}

function extractXianxiaCreateTrainedSkillValues(values: Record<string, unknown>): unknown[] {
  const indexed = Object.entries(values)
    .map(([key, value]) => {
      const match = key.match(/^trained_skill_(\d+)$/);
      return match ? ([Number(match[1]), value] as const) : null;
    })
    .filter((entry): entry is readonly [number, unknown] => entry !== null && entry[0] > 0)
    .sort((left, right) => left[0] - right[0])
    .map((entry) => entry[1]);
  if (indexed.length > 0) {
    return indexed;
  }
  if (Object.hasOwn(values, "trained_skills")) {
    return scalarList(values.trained_skills);
  }
  const skills = nestedRecordValue(values, "skills");
  if (Object.hasOwn(skills, "trained")) {
    return scalarList(skills.trained);
  }
  return [];
}

function normalizeTrainedSkillName(value: unknown): string {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    value = record.name ?? record.label;
  }
  return cleanScalar(value).split(/\s+/).filter(Boolean).join(" ");
}

function validateXianxiaCreateTrainedSkills(values: Record<string, unknown>): string[] {
  const trainedSkills = extractXianxiaCreateTrainedSkillValues(values).map(normalizeTrainedSkillName).filter(Boolean);
  if (trainedSkills.length !== XIANXIA_TRAINED_SKILL_COUNT) {
    throw new Error(
      `Xianxia character creation requires exactly ${XIANXIA_TRAINED_SKILL_COUNT} trained skills; submitted ${trainedSkills.length}.`,
    );
  }
  const seen = new Set<string>();
  const duplicates: string[] = [];
  for (const skill of trainedSkills) {
    const marker = skill.toLowerCase();
    if (seen.has(marker) && !duplicates.includes(skill)) {
      duplicates.push(skill);
    }
    seen.add(marker);
  }
  if (duplicates.length > 0) {
    throw new Error(`Xianxia trained skills must be distinct; duplicates: ${formatLabelList(duplicates)}.`);
  }
  return trainedSkills;
}

function normalizeCreateMartialArtRankKey(value: unknown): string {
  return cleanScalar(value).toLowerCase().replace(/[\s-]+/g, "_");
}

function coerceCreateMartialArtValue(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { slug: value, rank_key: "" };
  }
  const record = value as Record<string, unknown>;
  const systemsRef = asRecord(record.systems_ref);
  return {
    slug: record.slug ?? record.entry_slug ?? systemsRef.slug ?? systemsRef.entry_slug ?? record.systems_ref,
    rank_key: record.rank_key ?? record.current_rank_key ?? record.starting_rank_key ?? record.rank ?? record.current_rank,
  };
}

function extractXianxiaCreateMartialArtValues(values: Record<string, unknown>): Record<string, unknown>[] {
  const indexed: Record<string, unknown>[] = [];
  for (let index = 1; index <= 3; index += 1) {
    const slugKey = `martial_art_${index}_slug`;
    const rankKey = `martial_art_${index}_rank`;
    const alternateSlugKey = `starting_martial_art_${index}_slug`;
    const alternateRankKey = `starting_martial_art_${index}_rank`;
    if (
      Object.hasOwn(values, slugKey) ||
      Object.hasOwn(values, rankKey) ||
      Object.hasOwn(values, alternateSlugKey) ||
      Object.hasOwn(values, alternateRankKey)
    ) {
      indexed.push({
        slug: values[slugKey] ?? values[alternateSlugKey] ?? "",
        rank_key: values[rankKey] ?? values[alternateRankKey] ?? "",
      });
    }
  }
  if (indexed.length > 0) {
    return indexed;
  }
  if (Array.isArray(values.martial_arts)) {
    return values.martial_arts.map(coerceCreateMartialArtValue);
  }
  if (typeof values.martial_arts === "object" && values.martial_arts !== null) {
    return [coerceCreateMartialArtValue(values.martial_arts)];
  }
  return [];
}

function normalizeXianxiaCreateMartialArtValues(values: Record<string, unknown>): Array<{ slug: string; rank_key: string }> {
  const normalized = extractXianxiaCreateMartialArtValues(values).map((record) => ({
    slug: normalizeMartialArtOptionSlug(record.slug),
    rank_key: normalizeCreateMartialArtRankKey(record.rank_key),
  }));
  while (normalized.length < 3) {
    normalized.push({ slug: "", rank_key: "" });
  }
  return normalized.slice(0, 3);
}

function createMartialArtOptionMap(options: Array<Record<string, unknown>>): Map<string, Record<string, unknown>> {
  const lookup = new Map<string, Record<string, unknown>>();
  for (const option of options) {
    const slug = normalizeMartialArtOptionSlug(option.slug);
    if (slug) {
      lookup.set(slug, option);
    }
  }
  return lookup;
}

function buildXianxiaStartingMartialArtRecord(option: Record<string, unknown>, rankKey: string): Record<string, unknown> {
  const learnedRanks = rankKey === "novice" ? ["initiate", "novice"] : ["initiate"];
  const record: Record<string, unknown> = {
    name: String(option.title || "").trim(),
    systems_ref: martialArtSystemsRef(option),
    current_rank: XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[rankKey],
    current_rank_key: rankKey,
    learned_rank_refs: learnedRanks
      .map((learnedRank) => {
        const rankRefs = asRecord(option.rank_refs);
        return String(rankRefs[learnedRank] || (option.slug ? `xianxia:${option.slug}:${learnedRank}` : "")).trim();
      })
      .filter(Boolean),
    starting_package: true,
  };
  const rankStatus = String(option.rank_records_status || "").trim();
  if (rankStatus) {
    record.rank_records_status = rankStatus;
  }
  if (option.custom_martial_art === true) {
    record.custom_martial_art = true;
    record.xianxia_custom_martial_art = true;
  }
  return record;
}

function validateXianxiaCreateMartialArts(
  values: Record<string, unknown>,
  options: Array<Record<string, unknown>>,
): { records: Record<string, unknown>[]; options: Record<string, unknown>[] } {
  const optionsBySlug = createMartialArtOptionMap(options);
  const selectedValues = normalizeXianxiaCreateMartialArtValues(values).filter((value) => value.slug || value.rank_key);
  if (selectedValues.length === 0) {
    throw new Error("Xianxia character creation requires a starting Martial Arts package: one Novice plus one Initiate, or three Initiates.");
  }
  if (optionsBySlug.size === 0) {
    throw new Error("No enabled Xianxia Martial Art Systems entries are available for character creation.");
  }

  const errors: string[] = [];
  const records: Record<string, unknown>[] = [];
  const selectedOptions: Record<string, unknown>[] = [];
  const seenSlugs = new Set<string>();
  const duplicateTitles: string[] = [];
  for (const value of selectedValues) {
    if (!value.slug || !value.rank_key) {
      errors.push("Each selected starting Martial Art needs both a Martial Art and a rank.");
      continue;
    }
    const option = optionsBySlug.get(value.slug);
    if (!option) {
      errors.push(`Unsupported starting Martial Art: ${value.slug}.`);
      continue;
    }
    if (value.rank_key !== "initiate" && value.rank_key !== "novice") {
      errors.push("Starting Martial Art ranks must be Initiate or Novice.");
      continue;
    }
    const optionSlug = String(option.slug || "");
    if (seenSlugs.has(optionSlug)) {
      duplicateTitles.push(String(option.title || ""));
      continue;
    }
    seenSlugs.add(optionSlug);
    const availableRanks = new Set(asArray(option.available_starting_rank_keys).map((rank) => String(rank)));
    if (!availableRanks.has(value.rank_key)) {
      errors.push(
        `${option.title} does not have ${XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[value.rank_key]} rank available in Systems metadata.`,
      );
      continue;
    }
    records.push(buildXianxiaStartingMartialArtRecord(option, value.rank_key));
    selectedOptions.push({ ...option, current_rank_key: value.rank_key });
  }
  if (duplicateTitles.length > 0) {
    errors.push(`Starting Martial Arts must be distinct; duplicates: ${formatLabelList(duplicateTitles)}.`);
  }
  const rankKeys = records.map((record) => String(record.current_rank_key || ""));
  const legalNovicePackage = [...rankKeys].sort().join("|") === "initiate|novice";
  const legalInitiatePackage = rankKeys.join("|") === "initiate|initiate|initiate";
  if (records.length > 0 && !legalNovicePackage && !legalInitiatePackage) {
    errors.push("Starting Martial Arts must be one Novice plus one Initiate, or three Initiates.");
  }
  if (errors.length > 0) {
    throw new Error(errors.join(" "));
  }
  return { records, options: selectedOptions };
}

function normalizeGenericTechniqueEntryKeys(values: Record<string, unknown>): string[] {
  let rawValues = values.gm_granted_generic_technique_entry_keys;
  if (rawValues === null || rawValues === undefined) {
    rawValues = values.gm_granted_generic_techniques;
  }
  return scalarList(rawValues)
    .map((rawValue) => {
      if (typeof rawValue === "object" && rawValue !== null && !Array.isArray(rawValue)) {
        const record = rawValue as Record<string, unknown>;
        const systemsRef = asRecord(record.systems_ref);
        rawValue = record.entry_key ?? systemsRef.entry_key;
      }
      return cleanScalar(rawValue);
    })
    .filter(Boolean);
}

function genericTechniqueOptionMap(options: Array<Record<string, unknown>>): Map<string, Record<string, unknown>> {
  const lookup = new Map<string, Record<string, unknown>>();
  for (const option of options) {
    const entryKey = String(option.entry_key || "").trim().toLowerCase();
    if (entryKey) {
      lookup.set(entryKey, option);
    }
  }
  return lookup;
}

function buildXianxiaGmGrantedGenericTechniqueRecord(option: Record<string, unknown>): Record<string, unknown> {
  return {
    name: String(option.name || "").trim() || "Generic Technique",
    systems_ref: asRecord(option.systems_ref),
    generic_technique_key: String(option.generic_technique_key || "").trim(),
    insight_spent: 0,
    support_state: String(option.support_state || "").trim(),
    learnable_without_master: Boolean(option.learnable_without_master),
    requires_master: Boolean(option.requires_master),
    character_creation_grant: true,
    grant_source: "gm_granted_character_creation",
  };
}

function validateXianxiaCreateGmGrantedGenericTechniques(
  values: Record<string, unknown>,
  options: Array<Record<string, unknown>>,
): Record<string, unknown>[] {
  const requestedEntryKeys = normalizeGenericTechniqueEntryKeys(values);
  if (requestedEntryKeys.length === 0) {
    return [];
  }
  const optionsByEntryKey = genericTechniqueOptionMap(options);
  if (optionsByEntryKey.size === 0) {
    throw new Error("No enabled Xianxia Generic Technique Systems entries are available for GM grants.");
  }
  const records: Record<string, unknown>[] = [];
  const errors: string[] = [];
  const seen = new Set<string>();
  const duplicateTitles: string[] = [];
  for (const rawEntryKey of requestedEntryKeys) {
    const entryKey = rawEntryKey.trim().toLowerCase();
    const option = optionsByEntryKey.get(entryKey);
    if (!option) {
      errors.push(`Unsupported GM-granted Generic Technique: ${rawEntryKey}.`);
      continue;
    }
    if (seen.has(entryKey)) {
      duplicateTitles.push(String(option.name || ""));
      continue;
    }
    seen.add(entryKey);
    records.push(buildXianxiaGmGrantedGenericTechniqueRecord(option));
  }
  if (duplicateTitles.length > 0) {
    errors.push(`GM-granted Generic Techniques must be distinct; duplicates: ${formatLabelList(duplicateTitles)}.`);
  }
  if (errors.length > 0) {
    throw new Error(errors.join(" "));
  }
  return records;
}

const MARTIAL_ART_STYLE_EQUIPMENT_HINTS: Array<[string[], "weapon" | "tool", string]> = [
  [["jian sword"], "weapon", "Jian"],
  [["bo and spear", "staff and spear"], "weapon", "Bo staff or spear"],
  [["saber sword", "sabre sword"], "weapon", "Saber"],
  [["dagger"], "weapon", "Daggers"],
  [["sword martial art"], "weapon", "Sword"],
  [["instrument"], "tool", "Musical instrument"],
  [["puppet"], "tool", "Puppet"],
];
const TRAINED_SKILL_TOOL_HINTS: Array<[string[], string]> = [
  [["fishing", "fish"], "Fishing rod, spear, or net"],
  [["calligraphy", "scribe", "painting", "brushwork"], "Calligraphy brush"],
  [["tea ceremony", "tea making", "tea-making"], "Tea set"],
  [["medicine", "first aid", "healing", "herbalism", "herbalist"], "Medical kit or herbalism tools"],
  [["alchemy"], "Alchemy tools"],
  [["cooking", "cook", "culinary"], "Cooking tools"],
  [["smithing", "smith", "metalwork"], "Smithing tools"],
  [["carpentry", "woodcarving", "woodwork"], "Carpentry or woodcarving tools"],
  [["weaving", "tailoring", "sewing"], "Weaver's tools or sewing kit"],
  [["music", "musician", "instrument"], "Musical instrument"],
  [["navigation", "navigator", "sailing"], "Navigator's tools"],
  [["lockpicking", "lock picking", "thieves tools", "thieves' tools"], "Thieves' tools"],
];

function equipmentSearchText(value: unknown): string {
  return String(value || "").toLowerCase().replace(/[^a-z0-9']+/g, " ").trim();
}

function containsEquipmentPhrase(value: string, phrase: string): boolean {
  return ` ${equipmentSearchText(value)} `.includes(` ${equipmentSearchText(phrase)} `);
}

function appendEquipmentRecord(
  records: Array<Record<string, string>>,
  seen: Set<string>,
  name: string,
  reason: string,
): void {
  const cleanedName = name.split(/\s+/).filter(Boolean).join(" ");
  if (!cleanedName) {
    return;
  }
  const marker = equipmentSearchText(cleanedName);
  if (seen.has(marker)) {
    return;
  }
  seen.add(marker);
  records.push({ name: cleanedName, reason: reason.split(/\s+/).filter(Boolean).join(" ") });
}

function inferXianxiaRequiredEquipment(
  martialArts: Array<Record<string, unknown>>,
  trainedSkills: string[],
): Record<string, Array<Record<string, string>>> {
  const weapons: Array<Record<string, string>> = [];
  const tools: Array<Record<string, string>> = [];
  const seenWeapons = new Set<string>();
  const seenTools = new Set<string>();
  for (const martialArt of martialArts) {
    const title = cleanScalar(martialArt.title || martialArt.name).split(/\s+/).filter(Boolean).join(" ");
    const style = cleanScalar(martialArt.martial_art_style || martialArt.style || martialArt.xianxia_martial_art_style)
      .split(/\s+/)
      .filter(Boolean)
      .join(" ");
    if (!title || !style) {
      continue;
    }
    const inferred = MARTIAL_ART_STYLE_EQUIPMENT_HINTS.find(([phrases]) =>
      phrases.some((phrase) => containsEquipmentPhrase(style, phrase)),
    );
    if (!inferred) {
      continue;
    }
    const [, category, name] = inferred;
    appendEquipmentRecord(category === "weapon" ? weapons : tools, category === "weapon" ? seenWeapons : seenTools, name, `Required by ${title}`);
  }
  for (const skill of trainedSkills) {
    const skillName = skill.split(/\s+/).filter(Boolean).join(" ");
    if (!skillName) {
      continue;
    }
    const inferred = TRAINED_SKILL_TOOL_HINTS.find(([phrases]) =>
      phrases.some((phrase) => containsEquipmentPhrase(skillName, phrase)),
    );
    if (inferred) {
      appendEquipmentRecord(tools, seenTools, inferred[1], `Required for ${skillName}`);
    }
  }
  return { necessary_weapons: weapons, necessary_tools: tools };
}

function buildXianxiaInitialState(
  definition: Record<string, unknown>,
  inventory: Record<string, unknown>[],
  currency: Record<string, number>,
  playerNotesMarkdown: string,
  options: { daoCurrent?: number } = {},
): Record<string, unknown> {
  const xianxia = asRecord(definition.xianxia);
  const durability = asRecord(xianxia.durability);
  const energies = asRecord(xianxia.energies);
  const yinYang = asRecord(xianxia.yin_yang);
  const dao = asRecord(xianxia.dao);
  const hpMax = nonNegativeLooseInt(durability.hp_max, 10);
  const stanceMax = nonNegativeLooseInt(durability.stance_max, 10);
  const xianxiaState = {
    schema_version: 1,
    vitals: {
      current_hp: hpMax,
      temp_hp: 0,
      current_stance: stanceMax,
      temp_stance: 0,
    },
    energies: Object.fromEntries(
      XIANXIA_ENERGY_KEYS.map((key) => [key, { current: nonNegativeLooseInt(asRecord(energies[key]).max, 0) }]),
    ),
    yin_yang: {
      yin_current: nonNegativeLooseInt(yinYang.yin_max, 1),
      yang_current: nonNegativeLooseInt(yinYang.yang_max, 1),
    },
    dao: {
      current: Math.max(0, coerceLooseInt(options.daoCurrent, 0)),
    },
    currency,
    inventory: {
      enabled: inventory.length > 0,
      quantities: inventory,
    },
    notes: {
      player_notes_markdown: playerNotesMarkdown,
    },
  };
  return {
    status: String(definition.status || "active"),
    vitals: {
      current_hp: hpMax,
      temp_hp: 0,
    },
    resources: [],
    inventory,
    currency: { cp: 0, sp: 0, ep: 0, gp: 0, pp: 0, other: [] },
    spell_slots: [],
    attunement: { max_attuned_items: 3, attuned_item_refs: [] },
    notes: {
      player_notes_markdown: playerNotesMarkdown,
      physical_description_markdown: "",
      background_markdown: "",
      session_notes: [],
    },
    xianxia: xianxiaState,
  };
}

function buildPreviewFromXianxiaImport(definition: Record<string, unknown>, initialState: Record<string, unknown>) {
  const xianxia = asRecord(definition.xianxia);
  const xianxiaState = asRecord(initialState.xianxia);
  const vitals = asRecord(xianxiaState.vitals);
  const inventory = asRecord(xianxiaState.inventory);
  return {
    name: String(definition.name || ""),
    slug: String(definition.character_slug || ""),
    realm: xianxia.realm,
    actions_per_turn: xianxia.actions_per_turn,
    trained_skill_count: asArray(asRecord(xianxia.skills).trained).length,
    martial_art_count: asArray(xianxia.martial_arts).length,
    inventory_count: asArray(inventory.quantities).length,
    hp: vitals.current_hp,
    hp_max: asRecord(xianxia.durability).hp_max,
    stance: vitals.current_stance,
    stance_max: asRecord(xianxia.durability).stance_max,
  };
}

function isWholeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function requireExactInt(errors: string[], path: string, value: unknown, expected: number): void {
  if (!isWholeNumber(value)) {
    errors.push(`${path} must be a whole number.`);
    return;
  }
  if (value !== expected) {
    errors.push(`${path} must be ${expected}.`);
  }
}

function requireNonNegativeInt(errors: string[], path: string, value: unknown): void {
  if (!isWholeNumber(value)) {
    errors.push(`${path} must be a whole number.`);
    return;
  }
  if (value < 0) {
    errors.push(`${path} cannot be negative.`);
  }
}

function validateIntKeyMap(errors: string[], path: string, value: unknown, keys: readonly string[]): void {
  const record = asRecord(value);
  if (Object.keys(record).length === 0 && (typeof value !== "object" || value === null || Array.isArray(value))) {
    errors.push(`${path} must be an object.`);
    return;
  }
  for (const key of keys) {
    requireNonNegativeInt(errors, `${path}.${key}`, record[key]);
  }
  const unknown = Object.keys(record).filter((key) => !keys.includes(key)).sort();
  if (unknown.length > 0) {
    errors.push(`${path} uses unsupported keys: ${unknown.join(", ")}.`);
  }
}

function validateEnergyMaxima(errors: string[], value: unknown): void {
  const energies = asRecord(value);
  if (Object.keys(energies).length === 0 && (typeof value !== "object" || value === null || Array.isArray(value))) {
    errors.push("xianxia.energies must be an object.");
    return;
  }
  for (const key of XIANXIA_ENERGY_KEYS) {
    const energy = asRecord(energies[key]);
    if (Object.keys(energy).length === 0 && (typeof energies[key] !== "object" || energies[key] === null || Array.isArray(energies[key]))) {
      errors.push(`xianxia.energies.${key} must be an object.`);
      continue;
    }
    requireNonNegativeInt(errors, `xianxia.energies.${key}.max`, energy.max);
    const unknown = Object.keys(energy).filter((energyKey) => energyKey !== "max").sort();
    if (unknown.length > 0) {
      errors.push(`xianxia.energies.${key} uses unsupported keys: ${unknown.join(", ")}.`);
    }
  }
  const unknown = Object.keys(energies).filter((key) => !(XIANXIA_ENERGY_KEYS as readonly string[]).includes(key)).sort();
  if (unknown.length > 0) {
    errors.push(`xianxia.energies uses unsupported keys: ${unknown.join(", ")}.`);
  }
}

function validateRecordList(errors: string[], path: string, value: unknown): void {
  if (!Array.isArray(value)) {
    errors.push(`${path} must be a list.`);
    return;
  }
  value.forEach((item, index) => {
    if (typeof item !== "object" || item === null || Array.isArray(item)) {
      errors.push(`${path}[${index}] must be an object.`);
    }
  });
}

function validateXianxiaManualImportDefinition(definition: Record<string, unknown>): void {
  const errors: string[] = [];
  const xianxia = asRecord(definition.xianxia);
  const fieldKeys = Object.keys(xianxia);
  if (fieldKeys.join("|") !== XIANXIA_DEFINITION_FIELD_KEYS.join("|")) {
    errors.push(`xianxia must use the stable definition field order: ${XIANXIA_DEFINITION_FIELD_KEYS.join(", ")}.`);
  }

  requireExactInt(errors, "xianxia.schema_version", xianxia.schema_version, 1);
  const realm = String(xianxia.realm || "");
  if (!["Mortal", "Immortal", "Divine"].includes(realm)) {
    errors.push("xianxia.realm must be one of: Mortal, Immortal, Divine.");
  }
  requireNonNegativeInt(errors, "xianxia.actions_per_turn", xianxia.actions_per_turn);
  const expectedActions = XIANXIA_REALM_ACTIONS[realm.toLowerCase()];
  if (expectedActions !== undefined && xianxia.actions_per_turn !== expectedActions) {
    errors.push(`xianxia.actions_per_turn must match the ${realm} realm default of ${expectedActions}.`);
  }
  if (!["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"].includes(String(xianxia.honor || ""))) {
    errors.push("xianxia.honor must be one of: Venerable, Majestic, Honorable, Disgraced, Demonic.");
  }
  if (!String(xianxia.reputation || "").trim()) {
    errors.push("xianxia.reputation is required.");
  }

  validateIntKeyMap(errors, "xianxia.attributes", xianxia.attributes, XIANXIA_ATTRIBUTE_KEYS);
  validateIntKeyMap(errors, "xianxia.efforts", xianxia.efforts, XIANXIA_EFFORT_KEYS);
  validateEnergyMaxima(errors, xianxia.energies);
  const yinYang = asRecord(xianxia.yin_yang);
  requireNonNegativeInt(errors, "xianxia.yin_yang.yin_max", yinYang.yin_max);
  requireNonNegativeInt(errors, "xianxia.yin_yang.yang_max", yinYang.yang_max);
  const dao = asRecord(xianxia.dao);
  requireExactInt(errors, "xianxia.dao.max", dao.max, 3);
  const insight = asRecord(xianxia.insight);
  requireNonNegativeInt(errors, "xianxia.insight.available", insight.available);
  requireNonNegativeInt(errors, "xianxia.insight.spent", insight.spent);
  const durability = asRecord(xianxia.durability);
  for (const key of ["hp_max", "stance_max", "manual_armor_bonus", "defense"]) {
    requireNonNegativeInt(errors, `xianxia.durability.${key}`, durability[key]);
  }
  const skills = asRecord(xianxia.skills);
  if (!Array.isArray(skills.trained) || skills.trained.some((skill) => !String(skill || "").trim())) {
    errors.push("xianxia.skills.trained must be a list of non-empty strings.");
  }
  const equipment = asRecord(xianxia.equipment);
  validateRecordList(errors, "xianxia.equipment.necessary_weapons", equipment.necessary_weapons);
  validateRecordList(errors, "xianxia.equipment.necessary_tools", equipment.necessary_tools);
  for (const path of [
    "martial_arts",
    "generic_techniques",
    "variants",
    "approval_requests",
    "companions",
    "advancement_history",
  ]) {
    validateRecordList(errors, `xianxia.${path}`, xianxia[path]);
  }

  if (errors.length > 0) {
    throw new Error(errors.join(" "));
  }
}

export function buildXianxiaCreateCharacter({
  campaignSlug,
  values,
  martialArtOptions,
  genericTechniqueOptions,
}: {
  campaignSlug: string;
  values: Record<string, unknown>;
  martialArtOptions: Array<Record<string, unknown>>;
  genericTechniqueOptions: Array<Record<string, unknown>>;
}): XianxiaCreateBuildResult {
  const name = normalizeCreateName(values.name);
  if (!name) {
    throw new Error("Character name is required.");
  }
  const characterSlug = normalizeCharacterSlug(cleanScalar(values.character_slug), name);
  if (!characterSlug) {
    throw new Error("Character slug is required.");
  }

  const attributes = validateXianxiaCreateAttributes(values);
  const efforts = validateXianxiaCreateEfforts(values);
  const energyScores = validateXianxiaCreateEnergies(values);
  const manualArmorBonus = validateXianxiaCreateManualArmorBonus(values);
  const trainedSkills = validateXianxiaCreateTrainedSkills(values);
  const martialArtSelection = validateXianxiaCreateMartialArts(values, martialArtOptions);
  const genericTechniques = validateXianxiaCreateGmGrantedGenericTechniques(values, genericTechniqueOptions);
  const requiredEquipment = inferXianxiaRequiredEquipment(martialArtSelection.options, trainedSkills);
  const daoCurrent = validateXianxiaCreateDaoCurrent(values);
  const createdAt = new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
  const energies = Object.fromEntries(XIANXIA_ENERGY_KEYS.map((key) => [key, { max: energyScores[key] ?? 0 }]));

  const definition: Record<string, unknown> = {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    name,
    status: "active",
    system: "Xianxia",
    profile: {
      class_level_text: "Mortal Xianxia Character",
      realm: "Mortal",
      honor: "Honorable",
      reputation: "Unknown",
    },
    stats: {},
    skills: [],
    proficiencies: { armor: [], weapons: [], tools: [], languages: [], tool_expertise: [] },
    attacks: [],
    features: [],
    spellcasting: {},
    equipment_catalog: [],
    reference_notes: {
      additional_notes_markdown: "",
      allies_and_organizations_markdown: "",
      custom_sections: [],
    },
    resource_templates: [],
    source: {
      source_path: XIANXIA_CHARACTER_CREATE_SOURCE_PATH,
      source_type: XIANXIA_CHARACTER_CREATE_SOURCE_TYPE,
      imported_from: XIANXIA_CHARACTER_CREATE_IMPORTED_FROM,
      imported_at: createdAt,
      parse_warnings: [],
    },
    xianxia: {
      schema_version: 1,
      realm: "Mortal",
      actions_per_turn: 2,
      honor: "Honorable",
      reputation: "Unknown",
      attributes,
      efforts,
      energies,
      yin_yang: { yin_max: 1, yang_max: 1 },
      dao: { max: XIANXIA_DAO_DEFAULT_MAX },
      insight: {
        available: 0,
        spent: 0,
      },
      durability: {
        hp_max: 10,
        stance_max: 10,
        manual_armor_bonus: manualArmorBonus,
        defense: 10 + manualArmorBonus + coerceLooseInt(attributes.con, 0),
      },
      skills: { trained: trainedSkills },
      equipment: requiredEquipment,
      martial_arts: martialArtSelection.records,
      generic_techniques: genericTechniques,
      variants: [],
      dao_immolating_techniques: { prepared: [], use_history: [] },
      approval_requests: [],
      companions: [],
      advancement_history: [],
    },
  };
  validateXianxiaManualImportDefinition(definition);
  const initialState = buildXianxiaInitialState(
    definition,
    [],
    { coin: 0, supply: 0, spirit_stones: 0 },
    "",
    { daoCurrent },
  );
  const importMetadata = {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    source_path: XIANXIA_CHARACTER_CREATE_SOURCE_PATH,
    imported_at_utc: createdAt,
    parser_version: XIANXIA_CHARACTER_CREATE_VERSION,
    import_status: "clean",
    warnings: [],
  };
  return { definition, importMetadata, initialState };
}

export function buildXianxiaManualImportCharacter({
  campaignSlug,
  values,
  martialArtOptions,
}: {
  campaignSlug: string;
  values: Record<string, string>;
  martialArtOptions: Array<Record<string, unknown>>;
}): XianxiaManualImportBuildResult {
  const importPayload = buildXianxiaManualImportPayload(values);
  const normalizedValues = normalizeCharacterAuthoringValues(importPayload as Record<string, unknown>);
  const name = normalizeCharacterName(values.name || values.character_name || values.title || "");
  if (!name) {
    throw new Error("character name is required.");
  }
  const characterSlug = normalizeCharacterSlug(values.character_slug || values.slug || "", name);
  if (!characterSlug) {
    throw new Error("character_slug is required.");
  }

  const realm = normalizeRealm(values.realm);
  const honor = normalizeHonor(values.honor);
  const attributes = xianxiaIntegerMap(normalizedValues, XIANXIA_ATTRIBUTE_KEYS, "attribute_");
  const efforts = xianxiaIntegerMap(normalizedValues, XIANXIA_EFFORT_KEYS, "effort_");
  const energies = Object.fromEntries(
    XIANXIA_ENERGY_KEYS.map((key) => [key, { max: coerceLooseInt(values[`energy_${key}_max`], 0) }]),
  );
  const yinMax = coerceLooseInt(values.yin_max, 1);
  const yangMax = coerceLooseInt(values.yang_max, 1);
  const daoMax = coerceLooseInt(values.dao_max, 3);
  const hpMax = coerceLooseInt(values.hp_max, 10);
  const stanceMax = coerceLooseInt(values.stance_max, 10);
  const manualArmorBonus = coerceLooseInt(values.manual_armor_bonus, 0);
  const { trainedSkills, skillNotes } = collectTrainedSkills(values);
  const martialArts = collectMartialArts(values, martialArtOptions);
  const inventory = normalizeInventoryRows(values);
  const currency = Object.fromEntries(
    XIANXIA_CURRENCY_KEYS.map((key) => [key, nonNegativeLooseInt(values[key], 0)]),
  ) as Record<string, number>;
  const playerNotesMarkdown = String(values.player_notes_markdown || "").trim();
  const additionalNotes = skillNotes.length > 0
    ? appendNotesSection(String(values.additional_notes_markdown || ""), "Imported skill notes", skillNotes)
    : String(values.additional_notes_markdown || "").trim();

  const definition: Record<string, unknown> = {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    name,
    status: values.status || "active",
    system: "Xianxia",
    profile: {
      class_level_text: values.class_level_text || `${realm} Xianxia Character`,
      realm,
      honor,
      reputation: values.reputation || "Unknown",
    },
    stats: {},
    skills: [],
    proficiencies: { armor: [], weapons: [], tools: [], languages: [], tool_expertise: [] },
    attacks: [],
    features: [],
    spellcasting: {},
    equipment_catalog: [],
    reference_notes: {
      additional_notes_markdown: additionalNotes,
      allies_and_organizations_markdown: values.allies_and_organizations_markdown || "",
      custom_sections: [],
    },
    resource_templates: [],
    source: {
      source_path: XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
      source_type: XIANXIA_MANUAL_IMPORTER_SOURCE_TYPE,
      imported_from: XIANXIA_MANUAL_IMPORTER_IMPORTED_FROM,
      imported_at: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
      parse_warnings: [],
    },
    xianxia: {
      schema_version: 1,
      realm,
      actions_per_turn: XIANXIA_REALM_ACTIONS[realm.toLowerCase()],
      honor,
      reputation: values.reputation || "Unknown",
      attributes,
      efforts,
      energies,
      yin_yang: { yin_max: yinMax, yang_max: yangMax },
      dao: { max: daoMax },
      insight: {
        available: coerceLooseInt(values.insight_available, 0),
        spent: coerceLooseInt(values.insight_spent, 0),
      },
      durability: {
        hp_max: hpMax,
        stance_max: stanceMax,
        manual_armor_bonus: manualArmorBonus,
        defense: 10 + manualArmorBonus + coerceLooseInt(attributes.con, 0),
      },
      skills: { trained: trainedSkills },
      equipment: { necessary_weapons: [], necessary_tools: [] },
      martial_arts: martialArts,
      generic_techniques: [],
      variants: [],
      dao_immolating_techniques: { prepared: [], use_history: [] },
      approval_requests: [],
      companions: [],
      advancement_history: [],
    },
  };
  validateXianxiaManualImportDefinition(definition);
  const initialState = buildXianxiaInitialState(definition, inventory, currency, playerNotesMarkdown);
  const importMetadata = {
    campaign_slug: campaignSlug,
    character_slug: characterSlug,
    source_path: XIANXIA_MANUAL_IMPORTER_SOURCE_PATH,
    imported_at_utc: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    parser_version: XIANXIA_MANUAL_IMPORTER_VERSION,
    import_status: "clean",
    warnings: [],
  };
  return {
    definition,
    importMetadata,
    initialState,
    preview: buildPreviewFromXianxiaImport(definition, initialState),
  };
}

export function buildXianxiaManualImportPreview(values: Record<string, string>) {
  if (!normalizeCharacterName(values.name)) {
    throw new Error("character name is required.");
  }

  const normalizedValues = normalizeCharacterAuthoringValues(values);
  const realm = normalizeRealm(values.realm);
  const name = normalizeCharacterName(values.name);
  const slug = normalizeCharacterSlug(values.character_slug || values.slug || "", name);
  const trainedSkills = collectIndexedRows(normalizedValues, "trained_skill");
  const martialArts = collectIndexedRows(normalizedValues, "martial_art");
  const inventoryItems = collectIndexedRows(normalizedValues, "manual_item");
  const additionalInventoryRows = collectIndexedRows(normalizedValues, "inventory_item");

  const trained_skill_count =
    countTextRows(normalizedValues.trained_skills_text || "") +
    trainedSkills.filter((row) => Object.values(row).some(isPresent)).length;
  const martial_art_count = martialArts.filter((row) => Object.values(row).some(isPresent)).length;
  const inventory_count =
    countTextRows(normalizedValues.inventory_text || "") +
    inventoryItems.filter((row) => Object.values(row).some(isPresent)).length +
    additionalInventoryRows.filter((row) => Object.values(row).some(isPresent)).length;

  const hp_max = coerceInt(extractValues(normalizedValues, ["hp_max", "durability_hp_max", "max_hp"]), "hp_max");
  const stance_max = coerceInt(extractValues(normalizedValues, ["stance_max", "durability_stance_max"]), "stance_max");

  return {
    name,
    slug,
    realm,
    actions_per_turn: XIANXIA_REALM_ACTIONS[realm.toLowerCase()],
    trained_skill_count,
    martial_art_count,
    inventory_count,
    hp: hp_max,
    hp_max,
    stance: stance_max,
    stance_max,
  };
}
