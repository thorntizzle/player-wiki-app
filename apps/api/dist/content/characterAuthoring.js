import { existsSync } from "node:fs";
import Database from "better-sqlite3";
const XIANXIA_ATTRIBUTE_KEYS = ["str", "dex", "con", "int", "wis", "cha"];
const XIANXIA_ATTRIBUTE_LABELS = {
    str: "Strength",
    dex: "Dexterity",
    con: "Constitution",
    int: "Intelligence",
    wis: "Wisdom",
    cha: "Charisma",
};
const XIANXIA_EFFORT_KEYS = ["basic", "weapon", "guns_explosive", "magic", "ultimate"];
const XIANXIA_EFFORT_LABELS = {
    basic: "Basic",
    weapon: "Weapon",
    guns_explosive: "Guns/Explosive",
    magic: "Magic",
    ultimate: "Ultimate",
};
const XIANXIA_ENERGY_KEYS = ["jing", "qi", "shen"];
const XIANXIA_ENERGY_LABELS = {
    jing: "Jing",
    qi: "Qi",
    shen: "Shen",
};
const XIANXIA_YIN_YANG_KEYS = ["yin", "yang"];
const XIANXIA_YIN_YANG_LABELS = {
    yin: "Yin",
    yang: "Yang",
};
const XIANXIA_CURRENCY_KEYS = ["coin", "supply", "spirit_stones"];
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
];
const XIANXIA_MARTIAL_ART_IMPORT_RANKS = [
    { key: "initiate", label: "Initiate" },
    { key: "novice", label: "Novice" },
    { key: "apprentice", label: "Apprentice" },
    { key: "master", label: "Master" },
    { key: "legendary", label: "Legendary" },
];
const XIANXIA_MARTIAL_ART_RANK_ORDER = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key);
const XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS = Object.fromEntries(XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => [rank.key, rank.label]));
const XIANXIA_REALM_ACTIONS = {
    mortal: 2,
    immortal: 3,
    divine: 4,
};
const XIANXIA_ITEM_TYPE_DEFAULT = "Miscellaneous";
const XIANXIA_ITEM_TYPE_ALIASES = {
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
const XIANXIA_ITEM_NATURE_ALIASES = {
    mundane: "Mundane",
    relic: "Relic",
    relics: "Relic",
    re_lic: "Relic",
};
const XIANXIA_INVENTORY_TAG_TYPE_ALIASES = {
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
const XIANXIA_REALM_ASCENSION_REALMS = ["Mortal", "Immortal", "Divine"];
const XIANXIA_REALM_ASCENSION_TARGETS = {
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
const NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE = "This campaign can still use the character roster, read-mode sheets, session-mode sheets, and Controls. Native DND-5E builder, edit, level-up, repair, retraining, PDF-import, and spellcasting tools are not implemented for this campaign system.";
const XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE = "Xianxia advancement and cultivation use their own character lane. Use the Xianxia Cultivation page instead of DND-5E level-up, repair, or retraining routes; remaining unmodeled advancement workflows should be added there.";
const ADVANCED_EDITOR_UNSUPPORTED_MESSAGE = "Advanced Editor is currently available only for DND-5E native character tools in Gen2.";
const CULTIVATION_UNSUPPORTED_MESSAGE = "Cultivation is only available for Xianxia character sheets.";
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
const ADVANCED_EDITOR_MIN_RECOVERABLE_PENALTY_ROWS = 3;
const ADVANCED_EDITOR_RECOVERABLE_PENALTY_FIELD_PATTERN = /^recoverable_penalty_(id|source|target|amount|notes)_([1-9]\d*)$/;
const ADVANCED_EDITOR_MIN_MANUAL_EQUIPMENT_ROWS = 3;
const ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND = "manual_edit";
const ADVANCED_EDITOR_MANUAL_EQUIPMENT_FIELD_PATTERN = /^manual_item_(id|name|page_ref|quantity|weight|notes)_([1-9]\d*)$/;
const CAMPAIGN_MECHANICS_SECTION = "Mechanics";
const CAMPAIGN_ITEMS_SECTION = "Items";
const ADVANCED_EDITOR_LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND = {
    campaign_page_feature: new Set(["feature", "feat"]),
    campaign_page_item: new Set(["item"]),
};
const ADVANCED_EDITOR_LINKED_CAMPAIGN_PAGE_REQUIRED_SECTION_BY_FIELD_KIND = {
    campaign_page_feature: CAMPAIGN_MECHANICS_SECTION,
    campaign_page_item: CAMPAIGN_ITEMS_SECTION,
};
const ADVANCED_EDITOR_MIN_CUSTOM_FEATURE_ROWS = 3;
const ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY = "custom_feature";
const ADVANCED_EDITOR_CUSTOM_FEATURE_RESOURCE_PREFIX = "custom_feature";
const ADVANCED_EDITOR_CUSTOM_FEATURE_FIELD_PATTERN = /^custom_feature_(id|name|page_ref|activation_type|description|resource_max|resource_reset_on)_([1-9]\d*)$/;
const ADVANCED_EDITOR_FEATURE_ACTIVATION_OPTIONS = [
    { value: "passive", label: "Passive" },
    { value: "action", label: "Action" },
    { value: "bonus_action", label: "Bonus Action" },
    { value: "reaction", label: "Reaction" },
    { value: "special", label: "Special" },
];
const ADVANCED_EDITOR_RESOURCE_RESET_OPTIONS = [
    { value: "manual", label: "Manual" },
    { value: "short_rest", label: "Short Rest" },
    { value: "long_rest", label: "Long Rest" },
];
const ADVANCED_EDITOR_FEATURE_ACTIVATION_VALUES = new Set(ADVANCED_EDITOR_FEATURE_ACTIVATION_OPTIONS.map((option) => option.value));
const ADVANCED_EDITOR_RESOURCE_RESET_VALUES = new Set(ADVANCED_EDITOR_RESOURCE_RESET_OPTIONS.map((option) => option.value));
const ADVANCED_EDITOR_PROFICIENCY_FIELDS = [
    {
        name: "languages_text",
        key: "languages",
        label: "Languages",
        helpText: "One entry per line. Save the full list you want on the sheet.",
    },
    {
        name: "armor_proficiencies_text",
        key: "armor",
        label: "Armor Proficiencies",
        helpText: "One entry per line. Use this for campaign-granted proficiencies or revisions.",
    },
    {
        name: "weapon_proficiencies_text",
        key: "weapons",
        label: "Weapon Proficiencies",
        helpText: "One entry per line. Use this for campaign-granted proficiencies or revisions.",
    },
    {
        name: "tool_proficiencies_text",
        key: "tools",
        label: "Tool Proficiencies",
        helpText: "One entry per line. Use this for campaign-granted proficiencies or revisions.",
    },
];
const ADVANCED_EDITOR_PROFICIENCY_FIELD_NAMES = new Set(ADVANCED_EDITOR_PROFICIENCY_FIELDS.map((field) => field.name));
const ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELDS = [
    {
        name: "stat_adjustment_max_hp",
        key: "max_hp",
        label: "Max HP Adjustment",
        helpText: "Apply a persistent bonus or penalty to max HP.",
    },
    {
        name: "stat_adjustment_armor_class",
        key: "armor_class",
        label: "Armor Class Adjustment",
        helpText: "Apply a persistent bonus or penalty to Armor Class.",
    },
    {
        name: "stat_adjustment_initiative_bonus",
        key: "initiative_bonus",
        label: "Initiative Adjustment",
        helpText: "Apply a persistent bonus or penalty to initiative.",
    },
    {
        name: "stat_adjustment_speed",
        key: "speed",
        label: "Speed Adjustment (ft.)",
        helpText: "Apply a persistent speed change in feet.",
    },
    {
        name: "stat_adjustment_passive_perception",
        key: "passive_perception",
        label: "Passive Perception Adjustment",
        helpText: "Apply a persistent bonus or penalty to passive Perception.",
    },
    {
        name: "stat_adjustment_passive_insight",
        key: "passive_insight",
        label: "Passive Insight Adjustment",
        helpText: "Apply a persistent bonus or penalty to passive Insight.",
    },
    {
        name: "stat_adjustment_passive_investigation",
        key: "passive_investigation",
        label: "Passive Investigation Adjustment",
        helpText: "Apply a persistent bonus or penalty to passive Investigation.",
    },
];
const ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELD_NAMES = new Set(ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELDS.map((field) => field.name));
const ADVANCED_EDITOR_RECOVERABLE_PENALTY_TARGET_OPTIONS = [
    { value: "max_hp", label: "Max HP" },
    { value: "ability_score:str", label: "Strength" },
    { value: "ability_score:dex", label: "Dexterity" },
    { value: "ability_score:con", label: "Constitution" },
    { value: "ability_score:int", label: "Intelligence" },
    { value: "ability_score:wis", label: "Wisdom" },
    { value: "ability_score:cha", label: "Charisma" },
];
const ADVANCED_EDITOR_SUPPORTED_FIELD_NAMES = new Set([
    ...ADVANCED_EDITOR_REFERENCE_FIELD_NAMES,
    ...ADVANCED_EDITOR_PROFICIENCY_FIELD_NAMES,
    ...ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELD_NAMES,
]);
const DND_SYSTEMS_OPTION_PREFIX = "systems:";
const DND_PHB_SOURCE_ID = "PHB";
const DND_SUPPORTED_NON_PHB_BASE_CLASSES = new Set(["TCE|artificer"]);
const DND_SUPPORTED_SUBORDINATE_SOURCES = new Set(["TCE", "SCAG", "XGE", "EGW", "DMG"]);
const DND_ABILITY_KEYS = ["str", "dex", "con", "int", "wis", "cha"];
const DND_ABILITY_LABELS = {
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
function normalizeSystemKey(value) {
    return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}
export function nativeCharacterCreateLane(system) {
    const systemKey = normalizeSystemKey(system);
    if (systemKey === "dnd5e") {
        return "dnd5e";
    }
    if (systemKey === "xianxia") {
        return "xianxia";
    }
    return "";
}
export function nativeCharacterCreateUnsupportedMessage(_system) {
    return NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE;
}
export function advancedEditorUnsupportedMessage() {
    return ADVANCED_EDITOR_UNSUPPORTED_MESSAGE;
}
export function characterAdvancedEditorIsSupported(campaign, definition) {
    return nativeCharacterCreateLane(campaign.system) === "dnd5e" && nativeCharacterCreateLane(definition.system) === "dnd5e";
}
export function characterCultivationIsSupported(campaign, definition) {
    const xianxiaDefinition = asRecord(definition.xianxia);
    return (nativeCharacterCreateLane(campaign.system) === "xianxia" &&
        nativeCharacterCreateLane(definition.system) === "xianxia" &&
        Object.keys(xianxiaDefinition).length > 0);
}
function characterAdvancementUnsupportedMessage(system) {
    if (nativeCharacterCreateLane(system) === "xianxia") {
        return XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE;
    }
    return NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE;
}
function campaignHref(campaignSlug, suffix = "") {
    const normalized = suffix.replace(/^\/+|\/+$/g, "");
    return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}
function flaskCampaignHref(campaignSlug, suffix = "") {
    const normalized = suffix.replace(/^\/+|\/+$/g, "");
    return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}
export function buildCharacterAuthoringLinks(campaign) {
    const campaignSlug = campaign.slug;
    const links = {
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
export function buildCharacterAdvancedEditorLinks(campaign, characterSlug) {
    return {
        ...buildCharacterAuthoringLinks(campaign),
        advanced_editor_url: campaignHref(campaign.slug, `characters/${characterSlug}/edit`),
        flask_advanced_editor_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}/edit`),
        character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
        gen2_character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
        flask_character_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}`),
    };
}
export function buildCharacterCultivationLinks(campaign, characterSlug) {
    return {
        ...buildCharacterAuthoringLinks(campaign),
        character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
        gen2_character_url: campaignHref(campaign.slug, `characters/${characterSlug}`),
        flask_character_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}`),
        cultivation_url: campaignHref(campaign.slug, `characters/${characterSlug}/cultivation`),
        flask_cultivation_url: flaskCampaignHref(campaign.slug, `characters/${characterSlug}/cultivation`),
    };
}
export function buildCharacterCultivationShellPayload({ campaign, characterSlug, definition, state, genericTechniqueOptions = [], }) {
    const supported = characterCultivationIsSupported(campaign, definition);
    return {
        lane: supported ? "xianxia" : "unsupported",
        supported,
        unsupported_message: supported ? "" : CULTIVATION_UNSUPPORTED_MESSAGE,
        links: buildCharacterCultivationLinks(campaign, characterSlug),
        cultivation: supported ? buildXianxiaCultivationContext(definition, state, genericTechniqueOptions, campaign.slug) : null,
    };
}
export function applyCharacterCultivationAction(definition, payload, context = {}) {
    const values = normalizeCultivationValues(payload);
    const action = String(payload.action || payload.cultivation_action || values.cultivation_action || "save_insight").trim();
    if (action === "save_insight") {
        return applyXianxiaSaveInsightAction(definition, values);
    }
    if (action === "record_gathering_insight") {
        return applyXianxiaGatheringInsightAction(definition, values);
    }
    if (action === "spend_cultivation_energy") {
        return applyXianxiaCultivationEnergyAction(definition, values);
    }
    if (action === "spend_meditation_yin_yang") {
        return applyXianxiaMeditationYinYangAction(definition, values);
    }
    if (action === "spend_conditioning") {
        return applyXianxiaConditioningAction(definition, values);
    }
    if (action === "spend_training") {
        return applyXianxiaTrainingAction(definition, values);
    }
    if (action === "advance_martial_art_rank") {
        return applyXianxiaMartialArtRankAction(definition, values, context.martialArtRows || []);
    }
    if (action === "learn_generic_technique") {
        return applyXianxiaGenericTechniqueAction(definition, values, context.genericTechniqueRows || []);
    }
    if (action === "start_realm_ascension_review") {
        return applyXianxiaRealmAscensionReviewAction(definition, values);
    }
    if (action === "reset_realm_ascension_stats") {
        return applyXianxiaRealmAscensionResetAction(definition, values);
    }
    if (action === "apply_immortal_realm_rebuild") {
        return applyXianxiaRealmAscensionRebuildAction(definition, values, "Mortal", "Immortal");
    }
    if (action === "apply_divine_realm_rebuild") {
        return applyXianxiaRealmAscensionRebuildAction(definition, values, "Immortal", "Divine");
    }
    if (action === "confirm_realm_ascension") {
        return applyXianxiaRealmAscensionConfirmationAction(definition, values);
    }
    return {
        status: "validation_error",
        message: "Unsupported cultivation action. Refresh the page and try again.",
    };
}
function applyXianxiaSaveInsightAction(definition, values) {
    let available;
    let spent;
    try {
        available = normalizeCultivationInt(values.insight_available, "Insight available");
        spent = normalizeCultivationInt(values.insight_spent, "Insight spent");
    }
    catch (error) {
        return {
            status: "validation_error",
            message: error instanceof Error ? error.message : "Invalid cultivation payload.",
        };
    }
    const nextDefinition = updateXianxiaInsightDefinition(definition, available, spent);
    return {
        status: "ok",
        definition: nextDefinition,
        message: "Insight counters saved.",
        anchor: "xianxia-cultivation-insight",
    };
}
function applyXianxiaGatheringInsightAction(definition, values) {
    let amount;
    try {
        amount = normalizeCultivationPositiveInt(values.insight_gain_amount, "Gathered Insight");
    }
    catch (error) {
        return { status: "validation_error", message: error instanceof Error ? error.message : "Invalid cultivation payload." };
    }
    const nextDefinition = recordXianxiaGatheringInsightDefinition(definition, {
        amount,
        downtime: collapseWhitespace(values.gathering_insight_downtime),
        notes: String(values.gathering_insight_notes || "").trim(),
    });
    return {
        status: "ok",
        definition: nextDefinition,
        message: "Gathering Insight recorded.",
        anchor: "xianxia-cultivation-gathering-insight",
    };
}
function applyXianxiaCultivationEnergyAction(definition, values) {
    const energyKey = normalizeCultivationEnergyKey(values.energy_key);
    if (!energyKey) {
        return { status: "validation_error", message: "Choose Jing, Qi, or Shen for Cultivation." };
    }
    const result = spendXianxiaCultivationEnergyDefinition(definition, {
        energyKey,
        notes: collapseWhitespace(values.cultivation_energy_notes),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Spent ${result.insightCost} Insight on Cultivation to increase ${result.energyName}.`,
        anchor: "xianxia-cultivation-energy",
    };
}
function applyXianxiaMeditationYinYangAction(definition, values) {
    const yinYangKey = normalizeCultivationYinYangKey(values.yin_yang_key);
    if (!yinYangKey) {
        return { status: "validation_error", message: "Choose Yin or Yang for Meditation." };
    }
    const result = spendXianxiaMeditationYinYangDefinition(definition, {
        yinYangKey,
        notes: collapseWhitespace(values.meditation_notes),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Spent ${result.insightCost} Insight on Meditation to increase ${result.yinYangName}.`,
        anchor: "xianxia-cultivation-meditation",
    };
}
function applyXianxiaConditioningAction(definition, values) {
    const conditioningTarget = normalizeCultivationConditioningTarget(values.conditioning_target);
    if (!conditioningTarget) {
        return { status: "validation_error", message: "Choose HP or an Effort for Conditioning." };
    }
    const result = spendXianxiaConditioningDefinition(definition, {
        conditioningTarget,
        effortKey: values.effort_key,
        notes: collapseWhitespace(values.conditioning_notes),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Spent ${result.insightCost} Insight on Conditioning to increase ${result.targetName}.`,
        anchor: "xianxia-cultivation-conditioning",
    };
}
function applyXianxiaTrainingAction(definition, values) {
    const trainingTarget = normalizeCultivationTrainingTarget(values.training_target);
    if (!trainingTarget) {
        return { status: "validation_error", message: "Choose Stance or an Attribute for Training." };
    }
    const result = spendXianxiaTrainingDefinition(definition, {
        trainingTarget,
        attributeKey: values.attribute_key,
        notes: collapseWhitespace(values.training_notes),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Spent ${result.insightCost} Insight on Training to increase ${result.targetName}.`,
        anchor: "xianxia-cultivation-training",
    };
}
function applyXianxiaMartialArtRankAction(definition, values, martialArtRows) {
    const rawMartialArtIndex = String(values.martial_art_index || "").trim();
    if (!rawMartialArtIndex) {
        return { status: "validation_error", message: "Martial Art selection is required." };
    }
    let martialArtIndex;
    try {
        martialArtIndex = normalizeCultivationInt(rawMartialArtIndex, "Martial Art selection");
    }
    catch (error) {
        return {
            status: "validation_error",
            message: error instanceof Error ? error.message : "Invalid cultivation payload.",
        };
    }
    const result = advanceXianxiaMartialArtRankDefinition(definition, {
        martialArtIndex,
        targetRankKey: values.target_rank_key,
        legendaryQuestNote: collapseWhitespace(values.legendary_quest_note),
        martialArtRows,
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Spent ${result.insightCost} Insight to advance ${result.martialArtName} to ${result.rankName}.`,
        anchor: "xianxia-cultivation-martial-arts",
    };
}
function applyXianxiaGenericTechniqueAction(definition, values, genericTechniqueRows) {
    const result = learnXianxiaGenericTechniqueDefinition(definition, {
        genericTechniqueEntryKey: values.generic_technique_entry_key,
        notes: collapseWhitespace(values.generic_technique_notes),
        genericTechniqueRows,
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Spent ${result.insightCost} Insight to learn ${result.techniqueName}.`,
        anchor: "xianxia-cultivation-techniques",
    };
}
function applyXianxiaRealmAscensionReviewAction(definition, values) {
    const result = startXianxiaRealmAscensionReviewDefinition(definition, {
        targetRealm: values.target_realm,
        gmReviewNote: collapseWhitespace(values.realm_ascension_gm_review_note),
        seclusionNotes: collapseWhitespace(values.realm_ascension_seclusion_notes),
        hpStanceTradeNotes: collapseWhitespace(values.realm_ascension_hp_stance_trade_notes),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Started Realm ascension review from ${result.currentRealm} to ${result.targetRealm}.`,
        anchor: "xianxia-cultivation-realm-ascension",
    };
}
function applyXianxiaRealmAscensionResetAction(definition, values) {
    const result = resetXianxiaRealmAscensionStatsDefinition(definition, {
        targetRealm: values.target_realm,
        notes: collapseWhitespace(values.realm_ascension_reset_notes),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Reset Attributes and Efforts for ${result.currentRealm} to ${result.targetRealm} Realm ascension.`,
        anchor: "xianxia-cultivation-realm-ascension",
    };
}
function applyXianxiaRealmAscensionRebuildAction(definition, values, expectedCurrentRealm, expectedTargetRealm) {
    const result = applyXianxiaRealmAscensionRebuildDefinition(definition, {
        targetRealm: values.target_realm,
        attributeScores: Object.fromEntries(XIANXIA_ATTRIBUTE_KEYS.map((key) => [key, values[`realm_rebuild_attribute_${key}`]])),
        effortScores: Object.fromEntries(XIANXIA_EFFORT_KEYS.map((key) => [key, values[`realm_rebuild_effort_${key}`]])),
        hpMaximumTrade: values.realm_ascension_trade_hp,
        stanceMaximumTrade: values.realm_ascension_trade_stance,
        notes: collapseWhitespace(values.realm_ascension_rebuild_notes),
        expectedCurrentRealm,
        expectedTargetRealm,
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Applied the ${result.targetRealm} rebuild budget for ${result.totalRebuildPoints} points and ${result.actionsPerTurn} actions.`,
        anchor: "xianxia-cultivation-realm-ascension",
    };
}
function applyXianxiaRealmAscensionConfirmationAction(definition, values) {
    const result = confirmXianxiaRealmAscensionDefinition(definition, {
        targetRealm: values.target_realm,
        gmConfirmationNote: collapseWhitespace(values.realm_ascension_gm_confirmation_note),
    });
    if (result.status === "validation_error") {
        return { status: "validation_error", message: result.message };
    }
    return {
        status: "ok",
        definition: result.definition,
        message: `Recorded GM confirmation for the ${result.targetRealm} Realm ascension.`,
        anchor: "xianxia-cultivation-realm-ascension",
    };
}
function normalizeCultivationValues(payload) {
    const rawValues = asRecord(payload.values);
    const source = Object.keys(rawValues).length > 0 ? rawValues : payload;
    const values = {};
    for (const [key, value] of Object.entries(source)) {
        const fieldName = String(key || "").trim();
        if (!fieldName) {
            continue;
        }
        values[fieldName] = value === null || value === undefined ? "" : String(value);
    }
    return values;
}
function normalizeCultivationEnergyKey(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (XIANXIA_ENERGY_KEYS.includes(normalized)) {
        return normalized;
    }
    return "";
}
function normalizeCultivationConditioningTarget(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (normalized === "hp" || normalized === "effort") {
        return normalized;
    }
    return "";
}
function normalizeCultivationEffortKey(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (XIANXIA_EFFORT_KEYS.includes(normalized)) {
        return normalized;
    }
    return "";
}
function normalizeCultivationTrainingTarget(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (normalized === "stance" || normalized === "attribute") {
        return normalized;
    }
    return "";
}
function normalizeCultivationAttributeKey(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (XIANXIA_ATTRIBUTE_KEYS.includes(normalized)) {
        return normalized;
    }
    return "";
}
function xianxiaEffortLabel(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (XIANXIA_EFFORT_KEYS.includes(normalized)) {
        return XIANXIA_EFFORT_LABELS[normalized];
    }
    return normalized ? humanizeSlug(normalized) : "Effort";
}
function xianxiaAttributeLabel(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (XIANXIA_ATTRIBUTE_KEYS.includes(normalized)) {
        return XIANXIA_ATTRIBUTE_LABELS[normalized];
    }
    return normalized ? humanizeSlug(normalized) : "Attribute";
}
function normalizeCultivationYinYangKey(value) {
    const normalized = String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (XIANXIA_YIN_YANG_KEYS.includes(normalized)) {
        return normalized;
    }
    return "";
}
function normalizeCultivationInt(value, fieldLabel, fallback = 0) {
    const rawValue = String(value || "").trim();
    if (!rawValue) {
        return fallback;
    }
    if (!/^-?\d+$/.test(rawValue)) {
        throw new Error(`${fieldLabel} must be a whole number.`);
    }
    const normalizedValue = Number.parseInt(rawValue, 10);
    if (normalizedValue < 0) {
        throw new Error(`${fieldLabel} must be zero or greater.`);
    }
    return normalizedValue;
}
function normalizeCultivationPositiveInt(value, fieldLabel) {
    const rawValue = String(value || "").trim();
    if (!rawValue) {
        throw new Error(`${fieldLabel} must be at least 1.`);
    }
    if (!/^-?\d+$/.test(rawValue)) {
        throw new Error(`${fieldLabel} must be a whole number.`);
    }
    const normalizedValue = Number.parseInt(rawValue, 10);
    if (normalizedValue <= 0) {
        throw new Error(`${fieldLabel} must be at least 1.`);
    }
    return normalizedValue;
}
function collapseWhitespace(value) {
    return String(value || "").trim().replace(/\s+/g, " ");
}
function updateXianxiaInsightDefinition(definition, available, spent) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const previousInsight = asRecord(xianxia.insight);
    const previousAvailable = nonNegativeLooseInt(previousInsight.available, 0);
    const previousSpent = nonNegativeLooseInt(previousInsight.spent, 0);
    xianxia.insight = { available, spent };
    if (available !== previousAvailable || spent !== previousSpent) {
        const history = asArray(xianxia.advancement_history)
            .map(asRecord)
            .filter((record) => Object.keys(record).length > 0);
        history.push({
            action: "insight_counter_adjustment",
            target: "Insight",
            insight_available_before: previousAvailable,
            insight_available_after: available,
            insight_available_delta: available - previousAvailable,
            insight_spent_before: previousSpent,
            insight_spent_after: spent,
            insight_spent_delta: spent - previousSpent,
        });
        xianxia.advancement_history = history;
    }
    nextDefinition.xianxia = xianxia;
    return nextDefinition;
}
function spendXianxiaCultivationEnergyDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const previousInsight = asRecord(xianxia.insight);
    const previousAvailable = nonNegativeLooseInt(previousInsight.available, 0);
    const previousSpent = nonNegativeLooseInt(previousInsight.spent, 0);
    const insightCost = XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST;
    const energyName = XIANXIA_ENERGY_LABELS[payload.energyKey];
    if (previousAvailable < insightCost) {
        return {
            status: "validation_error",
            message: `Cultivation needs ${insightCost} Insight to increase ${energyName}; only ${previousAvailable} available.`,
        };
    }
    const existingEnergies = asRecord(xianxia.energies);
    const energies = {};
    for (const key of XIANXIA_ENERGY_KEYS) {
        const energy = asRecord(existingEnergies[key]);
        const maximumIncrease = key === payload.energyKey ? 1 : 0;
        energies[key] = { max: nonNegativeLooseInt(energy.max, 0) + maximumIncrease };
    }
    const newMaximum = energies[payload.energyKey]?.max ?? 0;
    xianxia.energies = energies;
    xianxia.insight = {
        available: previousAvailable - insightCost,
        spent: previousSpent + insightCost,
    };
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0);
    const historyRow = {
        action: "cultivation_energy_increase",
        amount: insightCost,
        target: energyName,
        energy_key: payload.energyKey,
        energy_maximum_increase: 1,
        new_energy_maximum: newMaximum,
    };
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        insightCost,
        energyName,
        newMaximum,
    };
}
function spendXianxiaMeditationYinYangDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const previousInsight = asRecord(xianxia.insight);
    const previousAvailable = nonNegativeLooseInt(previousInsight.available, 0);
    const previousSpent = nonNegativeLooseInt(previousInsight.spent, 0);
    const insightCost = XIANXIA_MEDITATION_INSIGHT_COST;
    const yinYangName = XIANXIA_YIN_YANG_LABELS[payload.yinYangKey];
    if (previousAvailable < insightCost) {
        return {
            status: "validation_error",
            message: `Meditation needs ${insightCost} Insight to increase ${yinYangName}; only ${previousAvailable} available.`,
        };
    }
    const existingYinYang = asRecord(xianxia.yin_yang);
    const yinYang = {};
    for (const key of XIANXIA_YIN_YANG_KEYS) {
        const maxKey = `${key}_max`;
        const maximumIncrease = key === payload.yinYangKey ? 1 : 0;
        yinYang[maxKey] = Math.max(1, coerceLooseInt(existingYinYang[maxKey], 1)) + maximumIncrease;
    }
    const newMaximum = yinYang[`${payload.yinYangKey}_max`] ?? 0;
    xianxia.yin_yang = yinYang;
    xianxia.insight = {
        available: previousAvailable - insightCost,
        spent: previousSpent + insightCost,
    };
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0);
    const historyRow = {
        action: "meditation_yin_yang_increase",
        amount: insightCost,
        target: yinYangName,
        yin_yang_key: payload.yinYangKey,
        yin_yang_maximum_increase: 1,
        new_yin_yang_maximum: newMaximum,
    };
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        insightCost,
        yinYangName,
        newMaximum,
    };
}
function spendXianxiaConditioningDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const previousInsight = asRecord(xianxia.insight);
    const previousAvailable = nonNegativeLooseInt(previousInsight.available, 0);
    const previousSpent = nonNegativeLooseInt(previousInsight.spent, 0);
    const insightCost = XIANXIA_CONDITIONING_INSIGHT_COST;
    if (previousAvailable < insightCost) {
        const targetName = payload.conditioningTarget === "hp" ? "HP" : xianxiaEffortLabel(payload.effortKey);
        return {
            status: "validation_error",
            message: `Conditioning needs ${insightCost} Insight to increase ${targetName}; only ${previousAvailable} available.`,
        };
    }
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0);
    let targetName = "HP";
    let newValue = 0;
    let historyRow;
    if (payload.conditioningTarget === "hp") {
        const durability = asRecord(xianxia.durability);
        const currentHpMaximum = nonNegativeLooseInt(durability.hp_max, 10);
        if (currentHpMaximum >= XIANXIA_CONDITIONING_HP_MAXIMUM) {
            return {
                status: "validation_error",
                message: `Conditioning cannot increase HP above ${XIANXIA_CONDITIONING_HP_MAXIMUM}.`,
            };
        }
        const newHpMaximum = Math.min(XIANXIA_CONDITIONING_HP_MAXIMUM, currentHpMaximum + XIANXIA_CONDITIONING_HP_INCREASE);
        const maximumIncrease = newHpMaximum - currentHpMaximum;
        durability.hp_max = newHpMaximum;
        xianxia.durability = durability;
        newValue = newHpMaximum;
        historyRow = {
            action: "conditioning_hp_increase",
            amount: insightCost,
            target: "HP",
            hp_maximum_increase: maximumIncrease,
            new_hp_maximum: newHpMaximum,
            hp_maximum_cap: XIANXIA_CONDITIONING_HP_MAXIMUM,
        };
    }
    else {
        const effortKey = normalizeCultivationEffortKey(payload.effortKey);
        if (!effortKey) {
            return { status: "validation_error", message: "Choose a valid Effort for Conditioning." };
        }
        const efforts = asRecord(xianxia.efforts);
        const currentScore = nonNegativeLooseInt(efforts[effortKey], 0);
        const newScore = currentScore + XIANXIA_CONDITIONING_EFFORT_INCREASE;
        efforts[effortKey] = newScore;
        xianxia.efforts = efforts;
        targetName = XIANXIA_EFFORT_LABELS[effortKey];
        newValue = newScore;
        historyRow = {
            action: "conditioning_effort_increase",
            amount: insightCost,
            target: targetName,
            effort_key: effortKey,
            effort_point_increase: XIANXIA_CONDITIONING_EFFORT_INCREASE,
            new_effort_score: newScore,
        };
    }
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    xianxia.insight = {
        available: previousAvailable - insightCost,
        spent: previousSpent + insightCost,
    };
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        insightCost,
        targetName,
        newValue,
    };
}
function spendXianxiaTrainingDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const previousInsight = asRecord(xianxia.insight);
    const previousAvailable = nonNegativeLooseInt(previousInsight.available, 0);
    const previousSpent = nonNegativeLooseInt(previousInsight.spent, 0);
    const insightCost = XIANXIA_TRAINING_INSIGHT_COST;
    if (previousAvailable < insightCost) {
        const targetName = payload.trainingTarget === "stance" ? "Stance" : xianxiaAttributeLabel(payload.attributeKey);
        return {
            status: "validation_error",
            message: `Training needs ${insightCost} Insight to increase ${targetName}; only ${previousAvailable} available.`,
        };
    }
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0);
    let targetName = "Stance";
    let newValue = 0;
    let historyRow;
    if (payload.trainingTarget === "stance") {
        const durability = asRecord(xianxia.durability);
        const currentStanceMaximum = nonNegativeLooseInt(durability.stance_max, 10);
        if (currentStanceMaximum >= XIANXIA_TRAINING_STANCE_MAXIMUM) {
            return {
                status: "validation_error",
                message: `Training cannot increase Stance above ${XIANXIA_TRAINING_STANCE_MAXIMUM}.`,
            };
        }
        const newStanceMaximum = Math.min(XIANXIA_TRAINING_STANCE_MAXIMUM, currentStanceMaximum + XIANXIA_TRAINING_STANCE_INCREASE);
        const maximumIncrease = newStanceMaximum - currentStanceMaximum;
        durability.stance_max = newStanceMaximum;
        xianxia.durability = durability;
        newValue = newStanceMaximum;
        historyRow = {
            action: "training_stance_increase",
            amount: insightCost,
            target: "Stance",
            stance_maximum_increase: maximumIncrease,
            new_stance_maximum: newStanceMaximum,
            stance_maximum_cap: XIANXIA_TRAINING_STANCE_MAXIMUM,
        };
    }
    else {
        const attributeKey = normalizeCultivationAttributeKey(payload.attributeKey);
        if (!attributeKey) {
            return { status: "validation_error", message: "Choose a valid Attribute for Training." };
        }
        const attributes = asRecord(xianxia.attributes);
        const currentScore = nonNegativeLooseInt(attributes[attributeKey], 0);
        const newScore = currentScore + XIANXIA_TRAINING_ATTRIBUTE_INCREASE;
        attributes[attributeKey] = newScore;
        xianxia.attributes = attributes;
        targetName = XIANXIA_ATTRIBUTE_LABELS[attributeKey];
        newValue = newScore;
        historyRow = {
            action: "training_attribute_increase",
            amount: insightCost,
            target: targetName,
            attribute_key: attributeKey,
            attribute_point_increase: XIANXIA_TRAINING_ATTRIBUTE_INCREASE,
            new_attribute_score: newScore,
        };
    }
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    xianxia.insight = {
        available: previousAvailable - insightCost,
        spent: previousSpent + insightCost,
    };
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        insightCost,
        targetName,
        newValue,
    };
}
function advanceXianxiaMartialArtRankDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const martialArts = asArray(xianxia.martial_arts).map(asRecord).filter((record) => Object.keys(record).length > 0);
    if (payload.martialArtIndex < 0 || payload.martialArtIndex >= martialArts.length) {
        return { status: "validation_error", message: "Choose a recorded Martial Art to advance." };
    }
    const rankKey = normalizeRankKey(payload.targetRankKey);
    if (!XIANXIA_MARTIAL_ART_RANK_ORDER.includes(rankKey)) {
        return { status: "validation_error", message: "Choose a valid Martial Art rank to advance." };
    }
    const martialArt = { ...martialArts[payload.martialArtIndex] };
    const systemsRef = asRecord(martialArt.systems_ref);
    const systemsEntry = xianxiaMartialArtEntryForRecord(systemsRef, payload.martialArtRows);
    const martialArtName = xianxiaMartialArtName(martialArt, systemsEntry);
    const rankCatalog = xianxiaMartialArtRankCatalog(systemsEntry);
    if (rankCatalog.length === 0) {
        return { status: "validation_error", message: `${martialArtName} does not have structured rank metadata yet.` };
    }
    const targetRecord = martialArtRankRecordByKey(rankCatalog).get(rankKey);
    if (!targetRecord || xianxiaRankRecordIsIncomplete(targetRecord)) {
        return {
            status: "validation_error",
            message: `${martialArtName} does not have an available ${xianxiaMartialArtRankLabel(rankKey)} rank record.`,
        };
    }
    let learnedRankRefs = xianxiaLearnedRankRefs(martialArt);
    const learnedRankKeys = xianxiaLearnedRankKeys(martialArt, learnedRankRefs);
    if (learnedRankKeys.has(rankKey)) {
        return {
            status: "validation_error",
            message: `${martialArtName} already has ${xianxiaMartialArtRankLabel(rankKey)} recorded.`,
        };
    }
    if (rankKey === "legendary") {
        const missingPriorRanks = xianxiaMissingPriorRankKeys(rankCatalog, learnedRankKeys);
        if (missingPriorRanks.length > 0) {
            const missingRankNames = missingPriorRanks.map(xianxiaMartialArtRankLabel).join(", ");
            return {
                status: "validation_error",
                message: `Record ${missingRankNames} for ${martialArtName} before Legendary.`,
            };
        }
    }
    const nextRank = xianxiaNextAvailableRank(rankCatalog, learnedRankKeys);
    if (!nextRank) {
        return { status: "validation_error", message: `${martialArtName} has no additional structured rank to advance.` };
    }
    const nextRankKey = normalizeRankKey(nextRank.rank_key);
    if (nextRankKey !== rankKey) {
        return {
            status: "validation_error",
            message: `Advance ${martialArtName} to ${xianxiaMartialArtRankLabel(nextRankKey)} before ${xianxiaMartialArtRankLabel(rankKey)}.`,
        };
    }
    const insightCost = nonNegativeLooseInt(targetRecord.insight_cost, 0);
    const rankName = xianxiaMartialArtRankLabel(rankKey);
    if (insightCost <= 0) {
        return {
            status: "validation_error",
            message: `${martialArtName} ${rankName} does not have a positive Insight cost.`,
        };
    }
    const insight = asRecord(xianxia.insight);
    const available = nonNegativeLooseInt(insight.available, 0);
    const spent = nonNegativeLooseInt(insight.spent, 0);
    if (available < insightCost) {
        return {
            status: "validation_error",
            message: `${martialArtName} needs ${insightCost} Insight to advance to ${rankName}; only ${available} available.`,
        };
    }
    const energyMaximumIncreases = xianxiaRankEnergyMaximumIncreases(targetRecord);
    if (!Object.values(energyMaximumIncreases).some((increase) => increase > 0)) {
        return {
            status: "validation_error",
            message: `${martialArtName} ${rankName} does not have rank-granted Jing, Qi, or Shen maximum increases.`,
        };
    }
    const teacherBreakthroughRequirement = normalizeRankKey(targetRecord.teacher_breakthrough_requirement) || "none";
    const teacherBreakthroughNote = collapseWhitespace(targetRecord.teacher_breakthrough_note);
    const legendaryPrerequisiteNote = collapseWhitespace(targetRecord.legendary_prerequisite_note);
    if (rankKey === "legendary" && !payload.legendaryQuestNote) {
        return {
            status: "validation_error",
            message: `Record a quest or mythic-master note before advancing ${martialArtName} to Legendary.`,
        };
    }
    const rankRef = String(targetRecord.rank_ref || "").trim();
    learnedRankRefs = xianxiaEnsureRecordedLearnedRankRefs(learnedRankRefs, learnedRankKeys, rankCatalog);
    if (rankRef && !learnedRankRefs.includes(rankRef)) {
        learnedRankRefs.push(rankRef);
    }
    martialArt.current_rank_key = rankKey;
    martialArt.current_rank = rankName;
    martialArt.learned_rank_refs = learnedRankRefs;
    const rankEnergyMaximumIncreases = asRecord(martialArt.rank_energy_maximum_increases);
    rankEnergyMaximumIncreases[rankKey] = { ...energyMaximumIncreases };
    martialArt.rank_energy_maximum_increases = rankEnergyMaximumIncreases;
    if (teacherBreakthroughRequirement !== "none" || teacherBreakthroughNote) {
        const rankTeacherBreakthroughNotes = asRecord(martialArt.rank_teacher_breakthrough_notes);
        rankTeacherBreakthroughNotes[rankKey] = {
            requirement: teacherBreakthroughRequirement,
            note: teacherBreakthroughNote,
        };
        martialArt.rank_teacher_breakthrough_notes = rankTeacherBreakthroughNotes;
    }
    if (rankKey === "legendary") {
        const rankLegendaryNotes = asRecord(martialArt.rank_legendary_prerequisite_notes);
        const legendaryNote = {
            requirement: "quest_or_mythic_master",
            note: payload.legendaryQuestNote,
        };
        if (legendaryPrerequisiteNote) {
            legendaryNote.prerequisite_note = legendaryPrerequisiteNote;
        }
        rankLegendaryNotes[rankKey] = legendaryNote;
        martialArt.rank_legendary_prerequisite_notes = rankLegendaryNotes;
    }
    martialArt.insight_spent = nonNegativeLooseInt(martialArt.insight_spent, 0) + insightCost;
    martialArts[payload.martialArtIndex] = martialArt;
    xianxia.insight = { available: available - insightCost, spent: spent + insightCost };
    xianxia.energies = applyXianxiaEnergyMaximumIncreases(xianxia.energies, energyMaximumIncreases);
    xianxia.martial_arts = martialArts;
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0);
    const historyRow = {
        action: "martial_art_rank_advance",
        amount: insightCost,
        target: martialArtName,
        rank: rankName,
        energy_maximum_increases: { ...energyMaximumIncreases },
    };
    if (rankRef) {
        historyRow.rank_ref = rankRef;
    }
    if (Object.keys(systemsRef).length > 0) {
        historyRow.systems_ref = systemsRef;
    }
    if (teacherBreakthroughRequirement !== "none") {
        historyRow.teacher_breakthrough_requirement = teacherBreakthroughRequirement;
    }
    if (teacherBreakthroughNote) {
        historyRow.teacher_breakthrough_note = teacherBreakthroughNote;
    }
    if (rankKey === "legendary") {
        historyRow.legendary_prerequisite = "quest_or_mythic_master";
        historyRow.legendary_quest_note = payload.legendaryQuestNote;
        if (legendaryPrerequisiteNote) {
            historyRow.legendary_prerequisite_note = legendaryPrerequisiteNote;
        }
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return { status: "ok", definition: nextDefinition, insightCost, martialArtName, rankName };
}
function learnXianxiaGenericTechniqueDefinition(definition, payload) {
    const entryKey = String(payload.genericTechniqueEntryKey || "").trim();
    if (!entryKey) {
        return { status: "validation_error", message: "Choose a Generic Technique to learn." };
    }
    if (payload.genericTechniqueRows.length === 0) {
        return { status: "validation_error", message: "Generic Technique catalog is unavailable." };
    }
    const row = payload.genericTechniqueRows.find((candidate) => String(candidate.entry_key || "").trim() === entryKey) || null;
    const option = row ? buildXianxiaGenericTechniqueRecord(row) : null;
    if (!option) {
        return { status: "validation_error", message: "Choose an available Generic Technique to learn." };
    }
    const genericTechniqueKey = normalizeGenericTechniqueKey(option.generic_technique_key);
    if (XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS.has(genericTechniqueKey)) {
        return {
            status: "validation_error",
            message: `Use the dedicated ${option.name} spend form for this Insight spend.`,
        };
    }
    const insightCost = nonNegativeLooseInt(option.insight_cost, 0);
    if (insightCost <= 0) {
        return { status: "validation_error", message: `${option.name} does not have a positive Insight cost.` };
    }
    const knownMarkers = xianxiaKnownGenericTechniqueMarkers(definition);
    if (xianxiaGenericTechniqueRecordIsKnown(option, knownMarkers)) {
        return { status: "validation_error", message: `${option.name} is already learned.` };
    }
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const insight = asRecord(xianxia.insight);
    const available = nonNegativeLooseInt(insight.available, 0);
    const spent = nonNegativeLooseInt(insight.spent, 0);
    if (available < insightCost) {
        return {
            status: "validation_error",
            message: `${option.name} needs ${insightCost} Insight to learn; only ${available} available.`,
        };
    }
    const genericTechniques = asArray(xianxia.generic_techniques)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0)
        .map((record) => ({ ...record }));
    const learnedRecord = {
        name: option.name,
        systems_ref: { ...option.systems_ref },
        generic_technique_key: genericTechniqueKey,
        insight_spent: insightCost,
        support_state: String(option.support_state || "").trim(),
        learnable_without_master: Boolean(option.learnable_without_master),
        requires_master: Boolean(option.requires_master),
    };
    if (payload.notes) {
        learnedRecord.notes = payload.notes;
    }
    genericTechniques.push(learnedRecord);
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0)
        .map((record) => ({ ...record }));
    const historyRow = {
        action: "generic_technique_learned",
        amount: insightCost,
        target: option.name,
        generic_technique_key: genericTechniqueKey,
        systems_ref: { ...option.systems_ref },
        insight_cost: insightCost,
    };
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.generic_techniques = genericTechniques;
    xianxia.insight = { available: available - insightCost, spent: spent + insightCost };
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        techniqueName: option.name,
        insightCost,
    };
}
function startXianxiaRealmAscensionReviewDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const currentRealm = normalizeRealmLabel(xianxia.realm);
    const target = xianxiaRealmAscensionTargetForCurrent(currentRealm);
    if (!target) {
        return {
            status: "validation_error",
            message: `${currentRealm} characters do not have a further Realm ascension target.`,
        };
    }
    const targetRealm = String(target.target_realm || "").trim();
    if (normalizeRealmLabel(payload.targetRealm) !== targetRealm) {
        return {
            status: "validation_error",
            message: `Realm ascension must move from ${currentRealm} to ${targetRealm}.`,
        };
    }
    const statPrerequisite = xianxiaRealmStatPrerequisite(currentRealm, target, xianxiaAttributeRows(xianxia), xianxiaEffortRows(xianxia));
    if (!truthy(statPrerequisite.is_met)) {
        return { status: "validation_error", message: String(statPrerequisite.failure_message || "") };
    }
    if (!payload.gmReviewNote) {
        return {
            status: "validation_error",
            message: "Record a GM review note before starting Realm ascension review.",
        };
    }
    const history = xianxiaAdvancementHistory(xianxia);
    if (latestUnconfirmedRealmAscensionRebuild(history) !== null) {
        return {
            status: "validation_error",
            message: "Confirm the latest Realm rebuild before starting another Realm review.",
        };
    }
    const metBy = asRecord(statPrerequisite.met_by);
    const historyRow = {
        action: "realm_ascension_review_started",
        target: targetRealm,
        current_realm: currentRealm,
        target_realm: targetRealm,
        status: "pending_gm_review",
        seclusion_time: String(target.seclusion_time || "").trim(),
        rebuild_budget: nonNegativeLooseInt(target.rebuild_budget, 0),
        stat_cap: nonNegativeLooseInt(target.stat_cap, 0),
        actions_per_turn: nonNegativeLooseInt(target.actions_per_turn, 0),
        stat_max_prerequisite: {
            required_score: nonNegativeLooseInt(statPrerequisite.required_score, 0),
            met: true,
            stat_kind: String(metBy.kind || "").trim(),
            stat_key: String(metBy.key || "").trim(),
            stat_label: String(metBy.label || "").trim(),
            stat_score: nonNegativeLooseInt(metBy.score, 0),
        },
        gm_review_note: payload.gmReviewNote,
    };
    if (payload.seclusionNotes) {
        historyRow.seclusion_notes = payload.seclusionNotes;
    }
    if (payload.hpStanceTradeNotes) {
        historyRow.hp_stance_trade_notes = payload.hpStanceTradeNotes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return { status: "ok", definition: nextDefinition, currentRealm, targetRealm };
}
function resetXianxiaRealmAscensionStatsDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const currentRealm = normalizeRealmLabel(xianxia.realm);
    const target = xianxiaRealmAscensionTargetForCurrent(currentRealm);
    if (!target) {
        return {
            status: "validation_error",
            message: `${currentRealm} characters do not have a further Realm ascension target.`,
        };
    }
    const targetRealm = String(target.target_realm || "").trim();
    if (normalizeRealmLabel(payload.targetRealm) !== targetRealm) {
        return {
            status: "validation_error",
            message: `Realm ascension must move from ${currentRealm} to ${targetRealm}.`,
        };
    }
    const history = xianxiaAdvancementHistory(xianxia);
    const reviewIndex = latestRealmAscensionReviewIndex(history, currentRealm, targetRealm);
    if (reviewIndex === null) {
        return {
            status: "validation_error",
            message: "Start a pending Realm ascension review before resetting Attributes and Efforts.",
        };
    }
    if (hasRealmAscensionStatResetAfter(history, reviewIndex)) {
        return {
            status: "validation_error",
            message: "Attributes and Efforts have already been reset for this Realm ascension review.",
        };
    }
    const attributesBefore = xianxiaStatSummary(xianxiaAttributeRows(xianxia));
    const effortsBefore = xianxiaStatSummary(xianxiaEffortRows(xianxia));
    const preAscensionState = xianxiaRealmAscensionHistorySnapshot(xianxia);
    const preAscensionSummary = xianxiaRealmAscensionHistorySnapshotSummary(preAscensionState);
    xianxia.attributes = Object.fromEntries(XIANXIA_ATTRIBUTE_KEYS.map((key) => [key, 0]));
    xianxia.efforts = Object.fromEntries(XIANXIA_EFFORT_KEYS.map((key) => [key, 0]));
    const historyRow = {
        action: "realm_ascension_attributes_efforts_reset",
        target: targetRealm,
        current_realm: currentRealm,
        target_realm: targetRealm,
        status: "pending_rebuild",
        attributes_before_total: attributesBefore.total,
        attributes_after_total: 0,
        efforts_before_total: effortsBefore.total,
        efforts_after_total: 0,
        reset_scope: "Attributes and Efforts",
        preserved_scope: "Energies, Yin/Yang, HP, Stance, Insight, Martial Arts, Generic Techniques, variants, approval records, and notes",
        pre_ascension_summary: preAscensionSummary,
        pre_ascension_state: preAscensionState,
    };
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return { status: "ok", definition: nextDefinition, currentRealm, targetRealm };
}
function applyXianxiaRealmAscensionRebuildDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const currentRealm = normalizeRealmLabel(xianxia.realm);
    const target = xianxiaRealmAscensionTargetForCurrent(currentRealm);
    if (!target) {
        return {
            status: "validation_error",
            message: `${currentRealm} characters do not have a Realm rebuild target.`,
        };
    }
    const targetRealmForCurrent = String(target.target_realm || "").trim();
    if (currentRealm !== payload.expectedCurrentRealm || payload.expectedTargetRealm !== targetRealmForCurrent) {
        return {
            status: "validation_error",
            message: `The ${payload.expectedTargetRealm} rebuild budget applies only to ${payload.expectedCurrentRealm} to ${payload.expectedTargetRealm} ascension.`,
        };
    }
    if (normalizeRealmLabel(payload.targetRealm) !== payload.expectedTargetRealm) {
        return {
            status: "validation_error",
            message: `Realm ascension must move from ${currentRealm} to ${payload.expectedTargetRealm}.`,
        };
    }
    const history = xianxiaAdvancementHistory(xianxia);
    const reviewIndex = latestRealmAscensionReviewIndex(history, currentRealm, payload.expectedTargetRealm);
    if (reviewIndex === null) {
        return {
            status: "validation_error",
            message: `Start a pending Realm ascension review before applying the ${payload.expectedTargetRealm} rebuild.`,
        };
    }
    const resetIndex = latestRealmAscensionStatResetIndex(history, reviewIndex, payload.expectedTargetRealm);
    if (resetIndex === null) {
        return {
            status: "validation_error",
            message: `Reset Attributes and Efforts before applying the ${payload.expectedTargetRealm} rebuild budget.`,
        };
    }
    if (hasRealmAscensionRebuildAfter(history, resetIndex, payload.expectedTargetRealm)) {
        return {
            status: "validation_error",
            message: `The ${payload.expectedTargetRealm} rebuild budget has already been applied for this Realm ascension review.`,
        };
    }
    const resetEvent = asRecord(history[resetIndex]);
    const preAscensionState = asRecord(resetEvent.pre_ascension_state);
    const preAscensionSummary = String(resetEvent.pre_ascension_summary || "").trim();
    const rebuildBudget = nonNegativeLooseInt(target.rebuild_budget, 0);
    const statCap = nonNegativeLooseInt(target.stat_cap, 0);
    const actionsPerTurn = nonNegativeLooseInt(target.actions_per_turn, 0);
    const durability = asRecord(xianxia.durability);
    const hpMaximumBefore = nonNegativeLooseInt(durability.hp_max, 10);
    const stanceMaximumBefore = nonNegativeLooseInt(durability.stance_max, 10);
    const trade = validateRealmAscensionHpStanceTrade({
        hpMaximumTrade: payload.hpMaximumTrade,
        stanceMaximumTrade: payload.stanceMaximumTrade,
        hpMaximumBefore,
        stanceMaximumBefore,
    });
    const attributes = validateRealmRebuildScores(payload.attributeScores, {
        keys: XIANXIA_ATTRIBUTE_KEYS,
        labels: XIANXIA_ATTRIBUTE_LABELS,
        statCap,
        rebuildLabel: payload.expectedTargetRealm,
    });
    const efforts = validateRealmRebuildScores(payload.effortScores, {
        keys: XIANXIA_EFFORT_KEYS,
        labels: XIANXIA_EFFORT_LABELS,
        statCap,
        rebuildLabel: payload.expectedTargetRealm,
    });
    const totalRebuildPoints = attributes.total + efforts.total;
    const requiredRebuildPoints = rebuildBudget + trade.hpStanceTradePoints;
    const errors = [...trade.errors, ...attributes.errors, ...efforts.errors];
    if (totalRebuildPoints !== requiredRebuildPoints) {
        errors.push(`${payload.expectedTargetRealm} rebuild must spend exactly ${requiredRebuildPoints} Attribute/Effort points; submitted ${totalRebuildPoints}.`);
    }
    if (errors.length > 0) {
        return { status: "validation_error", message: errors.join("; ") };
    }
    const hpMaximumAfter = Math.max(0, hpMaximumBefore - trade.hpMaximumTrade);
    const stanceMaximumAfter = Math.max(0, stanceMaximumBefore - trade.stanceMaximumTrade);
    xianxia.durability = {
        ...durability,
        hp_max: hpMaximumAfter,
        stance_max: stanceMaximumAfter,
    };
    xianxia.realm = payload.expectedTargetRealm;
    xianxia.actions_per_turn = actionsPerTurn;
    xianxia.attributes = attributes.scores;
    xianxia.efforts = efforts.scores;
    const postAscensionState = xianxiaRealmAscensionHistorySnapshot(xianxia);
    const postAscensionSummary = xianxiaRealmAscensionHistorySnapshotSummary(postAscensionState);
    const historyRow = {
        action: payload.expectedTargetRealm === "Immortal"
            ? "realm_ascension_immortal_rebuild_applied"
            : "realm_ascension_divine_rebuild_applied",
        target: payload.expectedTargetRealm,
        current_realm: currentRealm,
        target_realm: payload.expectedTargetRealm,
        status: "applied_pending_final_confirmation",
        rebuild_budget: requiredRebuildPoints,
        stat_cap: statCap,
        actions_per_turn: actionsPerTurn,
        attributes_after_total: attributes.total,
        efforts_after_total: efforts.total,
        total_rebuild_points: totalRebuildPoints,
        post_ascension_summary: postAscensionSummary,
        post_ascension_state: postAscensionState,
    };
    if (Object.keys(preAscensionState).length > 0) {
        historyRow.pre_ascension_state = preAscensionState;
    }
    if (preAscensionSummary) {
        historyRow.pre_ascension_summary = preAscensionSummary;
    }
    if (trade.hpStanceTradePoints > 0) {
        Object.assign(historyRow, {
            hp_stance_trade_points: trade.hpStanceTradePoints,
            base_rebuild_budget: rebuildBudget,
            hp_maximum_trade: trade.hpMaximumTrade,
            stance_maximum_trade: trade.stanceMaximumTrade,
            hp_maximum_before: hpMaximumBefore,
            hp_maximum_after: hpMaximumAfter,
            stance_maximum_before: stanceMaximumBefore,
            stance_maximum_after: stanceMaximumAfter,
        });
    }
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        currentRealm,
        targetRealm: payload.expectedTargetRealm,
        totalRebuildPoints,
        actionsPerTurn,
    };
}
function confirmXianxiaRealmAscensionDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const currentRealm = normalizeRealmLabel(xianxia.realm);
    const normalizedTargetRealm = normalizeRealmLabel(payload.targetRealm);
    if (!payload.gmConfirmationNote) {
        return {
            status: "validation_error",
            message: "Record a GM confirmation note before confirming Realm ascension.",
        };
    }
    const history = xianxiaAdvancementHistory(xianxia);
    const rebuildIndex = latestUnconfirmedRealmAscensionRebuildIndex(history, normalizedTargetRealm);
    if (rebuildIndex === null) {
        return {
            status: "validation_error",
            message: "Apply a pending Realm rebuild before recording GM confirmation.",
        };
    }
    const rebuildEvent = asRecord(history[rebuildIndex]);
    const confirmedTargetRealm = normalizeRealmLabel(rebuildEvent.target_realm || rebuildEvent.target);
    if (normalizedTargetRealm && normalizedTargetRealm !== confirmedTargetRealm) {
        return {
            status: "validation_error",
            message: `GM confirmation target must match the pending ${confirmedTargetRealm} rebuild.`,
        };
    }
    if (currentRealm !== confirmedTargetRealm) {
        return {
            status: "validation_error",
            message: `GM confirmation for ${confirmedTargetRealm} requires the character to already be in the ${confirmedTargetRealm} Realm.`,
        };
    }
    rebuildEvent.status = "confirmed";
    history[rebuildIndex] = rebuildEvent;
    const historyRow = {
        action: "realm_ascension_gm_confirmation_recorded",
        target: confirmedTargetRealm,
        current_realm: String(rebuildEvent.current_realm || "").trim(),
        target_realm: confirmedTargetRealm,
        confirmed_realm: confirmedTargetRealm,
        status: "confirmed",
        confirmed_rebuild_action: String(rebuildEvent.action || "").trim(),
        confirmed_rebuild_index: rebuildIndex,
        actions_per_turn: nonNegativeLooseInt(rebuildEvent.actions_per_turn, 0),
        attributes_after_total: nonNegativeLooseInt(rebuildEvent.attributes_after_total, 0),
        efforts_after_total: nonNegativeLooseInt(rebuildEvent.efforts_after_total, 0),
        gm_confirmation_note: payload.gmConfirmationNote,
    };
    const postAscensionSummary = String(rebuildEvent.post_ascension_summary || "").trim();
    if (postAscensionSummary) {
        historyRow.post_ascension_summary = postAscensionSummary;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return {
        status: "ok",
        definition: nextDefinition,
        currentRealm: String(rebuildEvent.current_realm || "").trim(),
        targetRealm: confirmedTargetRealm,
    };
}
function recordXianxiaGatheringInsightDefinition(definition, payload) {
    const nextDefinition = deepCloneRecord(definition);
    const xianxia = asRecord(nextDefinition.xianxia);
    const previousInsight = asRecord(xianxia.insight);
    const previousAvailable = nonNegativeLooseInt(previousInsight.available, 0);
    const previousSpent = nonNegativeLooseInt(previousInsight.spent, 0);
    xianxia.insight = { available: previousAvailable + payload.amount, spent: previousSpent };
    const history = asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0);
    const historyRow = {
        action: "gathering_insight",
        amount: payload.amount,
        target: "Insight",
    };
    if (payload.downtime) {
        historyRow.downtime = payload.downtime;
    }
    if (payload.notes) {
        historyRow.notes = payload.notes;
    }
    history.push(historyRow);
    xianxia.advancement_history = history;
    nextDefinition.xianxia = xianxia;
    return nextDefinition;
}
function buildXianxiaCultivationContext(definition, state, genericTechniqueOptions, campaignSlug) {
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
    const stanceProjectedMaximum = Math.min(XIANXIA_TRAINING_STANCE_MAXIMUM, stanceMaximum + XIANXIA_TRAINING_STANCE_INCREASE);
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
function withInsightCost(row, insightCost, insightAvailable) {
    return {
        ...row,
        insight_cost: insightCost,
        has_enough_insight: insightAvailable >= insightCost,
        shortfall: Math.max(0, insightCost - insightAvailable),
    };
}
function buildXianxiaCultivationResources(definition, state) {
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
function xianxiaAttributeRows(xianxia) {
    const attributes = asRecord(xianxia.attributes);
    return XIANXIA_ATTRIBUTE_KEYS.map((key) => ({
        key,
        label: XIANXIA_ATTRIBUTE_LABELS[key],
        score: nonNegativeLooseInt(attributes[key], 0),
        current: nonNegativeLooseInt(attributes[key], 0),
    }));
}
function xianxiaEffortRows(xianxia) {
    const efforts = asRecord(xianxia.efforts);
    return XIANXIA_EFFORT_KEYS.map((key) => ({
        key,
        label: XIANXIA_EFFORT_LABELS[key],
        score: nonNegativeLooseInt(efforts[key], 0),
        current: nonNegativeLooseInt(efforts[key], 0),
    }));
}
function xianxiaMartialArtRows(xianxia, campaignSlug) {
    return asArray(xianxia.martial_arts).map((rawArt) => {
        const art = asRecord(rawArt);
        return {
            ...art,
            href: systemsEntryHref(asRecord(art.systems_ref), campaignSlug),
            rank_progress: xianxiaMartialArtRankProgress(art),
        };
    });
}
function xianxiaMartialArtRankProgress(art) {
    const learnedRankRefs = new Set(asArray(art.learned_rank_refs).map((ref) => String(ref || "").trim()).filter(Boolean));
    const rankRefs = asRecord(art.rank_refs);
    const currentRankKey = normalizeRankKey(art.current_rank_key || art.current_rank || "");
    const currentRankIndex = XIANXIA_MARTIAL_ART_RANK_ORDER.indexOf(currentRankKey);
    const steps = XIANXIA_MARTIAL_ART_RANK_ORDER.map((rankKey, index) => {
        const rankRef = String(rankRefs[rankKey] || "").trim();
        const isLearned = (currentRankIndex >= 0 && index <= currentRankIndex) ||
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
function xianxiaMartialArtRankInsightCost(rankKey) {
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
function xianxiaMartialArtAdvancementContext(art, insightAvailable) {
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
function xianxiaMartialArtEntryForRecord(systemsRef, martialArtRows) {
    const entryKey = String(systemsRef.entry_key || "").trim();
    if (entryKey) {
        const entry = martialArtRows.find((row) => String(row.entry_key || "").trim() === entryKey);
        if (entry) {
            return entry;
        }
    }
    const slug = String(systemsRef.slug || "").trim();
    if (slug) {
        return martialArtRows.find((row) => String(row.slug || "").trim() === slug) || null;
    }
    return null;
}
function xianxiaMartialArtName(martialArt, systemsEntry) {
    const systemsRef = asRecord(martialArt.systems_ref);
    return (String(martialArt.name || "").trim() ||
        String(systemsRef.title || "").trim() ||
        String(systemsEntry?.title || "").trim() ||
        "Martial Art");
}
function xianxiaMartialArtRankCatalog(systemsEntry) {
    if (!systemsEntry) {
        return [];
    }
    const metadata = parseJsonRecord(systemsEntry.metadata_json);
    const body = parseJsonRecord(systemsEntry.body_json);
    const martialArtBody = asRecord(body.xianxia_martial_art);
    const presentRecords = xianxiaRankRecordList(metadata.martial_art_rank_records ||
        metadata.xianxia_martial_art_rank_records ||
        martialArtBody.rank_records ||
        martialArtBody.xianxia_martial_art_rank_records);
    const missingRecords = xianxiaRankRecordList(metadata.martial_art_missing_rank_records ||
        metadata.xianxia_martial_art_missing_rank_records ||
        martialArtBody.missing_rank_records ||
        martialArtBody.xianxia_martial_art_missing_rank_records);
    return [...presentRecords, ...missingRecords].sort(compareXianxiaRankRecords);
}
function xianxiaRankRecordList(values) {
    return asArray(values).map(asRecord).filter((record) => Object.keys(record).length > 0);
}
function compareXianxiaRankRecords(left, right) {
    const leftOrder = xianxiaRankRecordOrder(left);
    const rightOrder = xianxiaRankRecordOrder(right);
    if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
    }
    return String(left.rank_name || left.rank_key || "")
        .toLowerCase()
        .localeCompare(String(right.rank_name || right.rank_key || "").toLowerCase());
}
function xianxiaRankRecordOrder(record) {
    const parsed = Number.parseInt(String(record.rank_order ?? ""), 10);
    if (Number.isFinite(parsed)) {
        return parsed;
    }
    const rankKey = normalizeRankKey(record.rank_key);
    const index = XIANXIA_MARTIAL_ART_RANK_ORDER.indexOf(rankKey);
    return index >= 0 ? index : 10000;
}
function martialArtRankRecordByKey(rankCatalog) {
    const lookup = new Map();
    for (const record of rankCatalog) {
        const rankKey = normalizeRankKey(record.rank_key);
        if (rankKey) {
            lookup.set(rankKey, record);
        }
    }
    return lookup;
}
function xianxiaRankRecordIsIncomplete(record) {
    return (truthy(record.is_incomplete_rank) ||
        record.rank_available_in_seed === false ||
        String(record.rank_completion_status || "").trim() === "missing_intentional_draft" ||
        String(record.incomplete_rank_reason || "").trim() === "intentional_draft_content");
}
function xianxiaLearnedRankRefs(martialArt) {
    const refs = [];
    for (const value of asArray(martialArt.learned_rank_refs)) {
        const ref = String(value || "").trim();
        if (ref && !refs.includes(ref)) {
            refs.push(ref);
        }
    }
    return refs;
}
function xianxiaLearnedRankKeys(martialArt, learnedRankRefs) {
    const learned = new Set();
    for (const ref of learnedRankRefs) {
        const rankKey = normalizeRankKey(String(ref).split(":").pop() || "");
        if (rankKey) {
            learned.add(rankKey);
        }
    }
    const currentRankKey = normalizeRankKey(martialArt.current_rank_key);
    if (currentRankKey) {
        learned.add(currentRankKey);
    }
    return learned;
}
function xianxiaNextAvailableRank(rankCatalog, learnedRankKeys) {
    for (const record of rankCatalog) {
        const rankKey = normalizeRankKey(record.rank_key);
        if (!rankKey || learnedRankKeys.has(rankKey)) {
            continue;
        }
        if (xianxiaRankRecordIsIncomplete(record)) {
            return null;
        }
        return record;
    }
    return null;
}
function xianxiaMissingPriorRankKeys(rankCatalog, learnedRankKeys) {
    const availableRankKeys = new Set(rankCatalog
        .filter((record) => !xianxiaRankRecordIsIncomplete(record))
        .map((record) => normalizeRankKey(record.rank_key))
        .filter(Boolean));
    const missing = [];
    for (const rankKey of XIANXIA_MARTIAL_ART_RANK_ORDER) {
        if (rankKey === "legendary") {
            break;
        }
        if (availableRankKeys.has(rankKey) && !learnedRankKeys.has(rankKey)) {
            missing.push(rankKey);
        }
    }
    return missing;
}
function xianxiaEnsureRecordedLearnedRankRefs(learnedRankRefs, learnedRankKeys, rankCatalog) {
    const refs = [...learnedRankRefs];
    for (const record of rankCatalog) {
        const rankKey = normalizeRankKey(record.rank_key);
        const rankRef = String(record.rank_ref || "").trim();
        if (rankKey && learnedRankKeys.has(rankKey) && rankRef && !refs.includes(rankRef)) {
            refs.push(rankRef);
        }
    }
    return refs;
}
function xianxiaRankEnergyMaximumIncreases(record) {
    const rawIncreases = asRecord(record.energy_maximum_increases || record.xianxia_energy_maximum_increases);
    return {
        jing: nonNegativeLooseInt(rawIncreases.jing, 0),
        qi: nonNegativeLooseInt(rawIncreases.qi, 0),
        shen: nonNegativeLooseInt(rawIncreases.shen, 0),
    };
}
function applyXianxiaEnergyMaximumIncreases(rawEnergies, increases) {
    const energies = asRecord(rawEnergies);
    const updated = {};
    for (const key of XIANXIA_ENERGY_KEYS) {
        const energy = asRecord(energies[key]);
        updated[key] = {
            max: nonNegativeLooseInt(energy.max, 0) + nonNegativeLooseInt(increases[key], 0),
        };
    }
    return updated;
}
function xianxiaMartialArtRankLabel(rankKey) {
    const normalized = normalizeRankKey(rankKey);
    return XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[normalized] || humanizeSlug(normalized) || "Rank";
}
function xianxiaRealmAscensionTargetForCurrent(currentRealm) {
    const normalizedRealm = normalizeRealmLabel(currentRealm);
    const target = asRecord(XIANXIA_REALM_ASCENSION_TARGETS[normalizedRealm]);
    return Object.keys(target).length > 0 ? { current_realm: normalizedRealm, ...target } : null;
}
function buildXianxiaRealmAscensionContext(xianxia) {
    const currentRealm = normalizeRealmLabel(xianxia.realm);
    const target = asRecord(xianxiaRealmAscensionTargetForCurrent(currentRealm));
    const hasTarget = Object.keys(target).length > 0;
    const history = asArray(xianxia.advancement_history).map(asRecord).filter((record) => Object.keys(record).length > 0);
    const latestReview = latestRealmAscensionEvent(history, "realm_ascension_review_started");
    const latestReset = latestRealmAscensionEvent(history, "realm_ascension_attributes_efforts_reset");
    const latestRebuild = [...history].reverse().find((record) => XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.has(String(record.action || ""))) ?? null;
    const pendingConfirmationRebuild = latestUnconfirmedRealmAscensionRebuild(history);
    const attributes = xianxiaStatSummary(xianxiaAttributeRows(xianxia));
    const efforts = xianxiaStatSummary(xianxiaEffortRows(xianxia));
    const statPrerequisite = xianxiaRealmStatPrerequisite(currentRealm, target, attributes.rows, efforts.rows);
    const context = {
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
    context.can_apply_rebuild = canApplyRealmRebuild(latestReview, latestReset, latestRealmAscensionRebuild(history, String(target.target_realm || "")), target);
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
function latestRealmAscensionEvent(history, action) {
    return [...history].reverse().find((record) => String(record.action || "") === action) ?? null;
}
function latestRealmAscensionRebuild(history, targetRealm) {
    return [...history]
        .reverse()
        .find((record) => XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.has(String(record.action || "")) &&
        String(record.target_realm || "").trim() === targetRealm) ?? null;
}
function latestUnconfirmedRealmAscensionRebuild(history, targetRealm = "") {
    const index = latestUnconfirmedRealmAscensionRebuildIndex(history, targetRealm);
    return index === null ? null : history[index];
}
function latestUnconfirmedRealmAscensionRebuildIndex(history, targetRealm = "") {
    const normalizedFilter = targetRealm ? normalizeRealmLabel(targetRealm) : "";
    for (let index = history.length - 1; index >= 0; index -= 1) {
        const record = history[index];
        if (!XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.has(String(record.action || ""))) {
            continue;
        }
        if (String(record.status || "").trim() !== "applied_pending_final_confirmation") {
            continue;
        }
        const recordTarget = normalizeRealmLabel(record.target_realm || record.target);
        if (normalizedFilter && recordTarget !== normalizedFilter) {
            continue;
        }
        const hasConfirmation = history.slice(index + 1).some((candidate) => String(candidate.action || "").trim() === "realm_ascension_gm_confirmation_recorded" &&
            normalizeRealmLabel(candidate.target_realm || candidate.target) === recordTarget);
        if (!hasConfirmation) {
            return index;
        }
    }
    return null;
}
function latestRealmAscensionReviewIndex(history, currentRealm, targetRealm) {
    for (let index = history.length - 1; index >= 0; index -= 1) {
        const record = history[index];
        if (String(record.action || "").trim() !== "realm_ascension_review_started") {
            continue;
        }
        if (String(record.status || "").trim() !== "pending_gm_review") {
            continue;
        }
        if (normalizeRealmLabel(record.current_realm) !== currentRealm) {
            continue;
        }
        if (normalizeRealmLabel(record.target_realm || record.target) !== targetRealm) {
            continue;
        }
        return index;
    }
    return null;
}
function hasRealmAscensionStatResetAfter(history, reviewIndex) {
    return history.slice(reviewIndex + 1).some((record) => String(record.action || "").trim() === "realm_ascension_attributes_efforts_reset");
}
function latestRealmAscensionStatResetIndex(history, reviewIndex, targetRealm) {
    for (let index = history.length - 1; index > reviewIndex; index -= 1) {
        const record = history[index];
        if (String(record.action || "").trim() !== "realm_ascension_attributes_efforts_reset") {
            continue;
        }
        if (String(record.status || "").trim() !== "pending_rebuild") {
            continue;
        }
        if (normalizeRealmLabel(record.target_realm || record.target) !== targetRealm) {
            continue;
        }
        return index;
    }
    return null;
}
function hasRealmAscensionRebuildAfter(history, resetIndex, targetRealm) {
    return history.slice(resetIndex + 1).some((record) => {
        if (!XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.has(String(record.action || ""))) {
            return false;
        }
        return normalizeRealmLabel(record.target_realm || record.target) === targetRealm;
    });
}
function validateRealmRebuildScores(values, options) {
    const scores = {};
    const errors = [];
    for (const key of options.keys) {
        const label = options.labels[key] || key;
        const rawValue = values[key];
        const rawText = rawValue === null || rawValue === undefined ? "" : String(rawValue).trim();
        if (!rawText) {
            errors.push(`${label} is required for the ${options.rebuildLabel} rebuild.`);
            scores[key] = 0;
            continue;
        }
        if (!/^-?\d+$/.test(rawText)) {
            errors.push(`${label} must be a whole number.`);
            scores[key] = 0;
            continue;
        }
        const score = Number.parseInt(rawText, 10);
        if (score < 0) {
            errors.push(`${label} cannot be negative.`);
            scores[key] = 0;
            continue;
        }
        if (score > options.statCap) {
            errors.push(`${label} cannot exceed ${options.statCap} for the ${options.rebuildLabel} rebuild.`);
        }
        scores[key] = score;
    }
    let total = 0;
    for (const key of options.keys) {
        total += nonNegativeLooseInt(scores[key], 0);
    }
    return { scores, total, errors };
}
function validateRealmAscensionHpStanceTrade({ hpMaximumTrade, stanceMaximumTrade, hpMaximumBefore, stanceMaximumBefore, }) {
    const errors = [];
    const hpTrade = validateRealmTradeAmount(hpMaximumTrade, {
        label: "HP maximum trade",
        currentMaximum: hpMaximumBefore,
        errors,
    });
    const stanceTrade = validateRealmTradeAmount(stanceMaximumTrade, {
        label: "Stance maximum trade",
        currentMaximum: stanceMaximumBefore,
        errors,
    });
    return {
        hpMaximumTrade: hpTrade,
        stanceMaximumTrade: stanceTrade,
        hpStanceTradePoints: Math.floor((hpTrade + stanceTrade) / XIANXIA_REALM_ASCENSION_TRADE_UNIT),
        errors,
    };
}
function validateRealmTradeAmount(value, { label, currentMaximum, errors, }) {
    const rawText = value === null || value === undefined ? "" : String(value).trim();
    if (!rawText) {
        return 0;
    }
    if (!/^-?\d+$/.test(rawText)) {
        errors.push(`${label} must be a whole number.`);
        return 0;
    }
    const amount = Number.parseInt(rawText, 10);
    if (amount < 0) {
        errors.push(`${label} cannot be negative.`);
        return 0;
    }
    if (amount % XIANXIA_REALM_ASCENSION_TRADE_UNIT !== 0) {
        errors.push(`${label} must be 0 or a multiple of ${XIANXIA_REALM_ASCENSION_TRADE_UNIT}.`);
    }
    if (amount > currentMaximum) {
        errors.push(`${label} cannot exceed the current maximum of ${currentMaximum}.`);
    }
    return amount;
}
function xianxiaAdvancementHistory(xianxia) {
    return asArray(xianxia.advancement_history)
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0)
        .map((record) => ({ ...record }));
}
function canResetRealmAscensionStats(latestReview, latestReset, target) {
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
function canApplyRealmRebuild(latestReview, latestReset, latestTargetRebuild, target) {
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
function xianxiaStatSummary(rows) {
    const total = rows.reduce((sum, row) => sum + nonNegativeLooseInt(row.score, 0), 0);
    const highest = rows.reduce((best, row) => {
        if (!best || nonNegativeLooseInt(row.score, 0) > nonNegativeLooseInt(best.score, 0)) {
            return row;
        }
        return best;
    }, null);
    return { rows, total, highest };
}
function xianxiaRealmStatPrerequisite(currentRealm, target, attributeRows, effortRows) {
    const normalizedRealm = normalizeRealmLabel(currentRealm);
    const targetRealm = String(target.target_realm || "").trim();
    const requiredScore = nonNegativeLooseInt(target.stat_max_prerequisite, 0);
    const candidates = [
        ...attributeRows.map((row) => ({ ...row, kind: "Attribute" })),
        ...effortRows.map((row) => ({ ...row, kind: "Effort" })),
    ].filter((row) => String(row.key || "").trim().length > 0);
    const metBy = candidates.find((row) => nonNegativeLooseInt(row.score, 0) >= requiredScore) ?? null;
    const highest = candidates.reduce((best, row) => {
        if (!best || nonNegativeLooseInt(row.score, 0) > nonNegativeLooseInt(best.score, 0)) {
            return row;
        }
        return best;
    }, null);
    const highestLabel = String(highest?.label || "None");
    const highestScore = nonNegativeLooseInt(highest?.score, 0);
    const targetLabel = targetRealm || "the next Realm";
    return {
        is_met: metBy !== null,
        required_score: requiredScore,
        met_by: metBy,
        highest,
        highest_label: highestLabel,
        highest_score: highestScore,
        requirement_text: `Requires at least one Attribute or Effort at ${requiredScore} before ascending from ${normalizedRealm} to ${targetLabel}.`,
        failure_message: metBy
            ? ""
            : `Realm ascension prerequisite not met: raise at least one Attribute or Effort to ${requiredScore} before ascending from ${normalizedRealm} to ${targetLabel}. Current highest Stat is ${highestLabel} at ${highestScore}.`,
    };
}
function xianxiaRealmAscensionHistorySnapshot(xianxia) {
    const attributes = Object.fromEntries(XIANXIA_ATTRIBUTE_KEYS.map((key) => [key, nonNegativeLooseInt(asRecord(xianxia.attributes)[key], 0)]));
    const efforts = Object.fromEntries(XIANXIA_EFFORT_KEYS.map((key) => [key, nonNegativeLooseInt(asRecord(xianxia.efforts)[key], 0)]));
    const energies = Object.fromEntries(XIANXIA_ENERGY_KEYS.map((key) => [key, { max: nonNegativeLooseInt(asRecord(asRecord(xianxia.energies)[key]).max, 0) }]));
    const yinYang = asRecord(xianxia.yin_yang);
    const dao = asRecord(xianxia.dao);
    const insight = asRecord(xianxia.insight);
    const durability = asRecord(xianxia.durability);
    const skills = asRecord(xianxia.skills);
    const equipment = asRecord(xianxia.equipment);
    const daoImmolating = asRecord(xianxia.dao_immolating_techniques);
    return {
        realm: normalizeRealmLabel(xianxia.realm),
        actions_per_turn: nonNegativeLooseInt(xianxia.actions_per_turn, 0),
        attributes,
        attributes_total: Object.values(attributes).reduce((sum, value) => sum + nonNegativeLooseInt(value, 0), 0),
        efforts,
        efforts_total: Object.values(efforts).reduce((sum, value) => sum + nonNegativeLooseInt(value, 0), 0),
        energies,
        yin_yang: {
            yin_max: nonNegativeLooseInt(yinYang.yin_max, 1),
            yang_max: nonNegativeLooseInt(yinYang.yang_max, 1),
        },
        dao: { max: nonNegativeLooseInt(dao.max, XIANXIA_DAO_DEFAULT_MAX) },
        insight: {
            available: nonNegativeLooseInt(insight.available, 0),
            spent: nonNegativeLooseInt(insight.spent, 0),
        },
        durability: {
            hp_max: nonNegativeLooseInt(durability.hp_max, 10),
            stance_max: nonNegativeLooseInt(durability.stance_max, 10),
            manual_armor_bonus: nonNegativeLooseInt(durability.manual_armor_bonus, 0),
            defense: nonNegativeLooseInt(durability.defense, 10),
        },
        skills: { trained: cleanStringList(asRecord(skills).trained) },
        equipment: {
            necessary_weapons: copyRecordList(equipment.necessary_weapons),
            necessary_tools: copyRecordList(equipment.necessary_tools),
        },
        martial_arts: copyRecordList(xianxia.martial_arts),
        generic_techniques: copyRecordList(xianxia.generic_techniques),
        variants: copyRecordList(xianxia.variants),
        dao_immolating_techniques: {
            prepared: copyRecordList(daoImmolating.prepared),
            use_history: copyRecordList(daoImmolating.use_history),
        },
        approval_requests: copyRecordList(xianxia.approval_requests),
        companions: copyRecordList(xianxia.companions),
    };
}
function xianxiaRealmAscensionHistorySnapshotSummary(snapshot) {
    const durability = asRecord(snapshot.durability);
    const insight = asRecord(snapshot.insight);
    return `${String(snapshot.realm || "Unknown")} Realm, ${nonNegativeLooseInt(snapshot.actions_per_turn, 0)} actions; Attributes ${nonNegativeLooseInt(snapshot.attributes_total, 0)}, Efforts ${nonNegativeLooseInt(snapshot.efforts_total, 0)}; HP max ${nonNegativeLooseInt(durability.hp_max, 0)}, Stance max ${nonNegativeLooseInt(durability.stance_max, 0)}; Insight ${nonNegativeLooseInt(insight.available, 0)} available/${nonNegativeLooseInt(insight.spent, 0)} spent; Martial Arts ${copyRecordList(snapshot.martial_arts).length}; Generic Techniques ${copyRecordList(snapshot.generic_techniques).length}`;
}
function copyRecordList(value) {
    const values = Array.isArray(value) ? value : value && typeof value === "object" ? [value] : [];
    return values
        .map(asRecord)
        .filter((record) => Object.keys(record).length > 0)
        .map((record) => JSON.parse(JSON.stringify(record)));
}
function cleanStringList(value) {
    const values = Array.isArray(value) ? value : typeof value === "string" ? [value] : [];
    return values.map(collapseWhitespace).filter(Boolean);
}
function xianxiaRealmTradeContext(durability) {
    const hpMax = nonNegativeLooseInt(durability.hp_max, 10);
    const stanceMax = nonNegativeLooseInt(durability.stance_max, 10);
    const hpMaximumTrade = Math.floor(Math.max(0, hpMax) / XIANXIA_REALM_ASCENSION_TRADE_UNIT) * XIANXIA_REALM_ASCENSION_TRADE_UNIT;
    const stanceMaximumTrade = Math.floor(Math.max(0, stanceMax) / XIANXIA_REALM_ASCENSION_TRADE_UNIT) * XIANXIA_REALM_ASCENSION_TRADE_UNIT;
    return {
        unit: XIANXIA_REALM_ASCENSION_TRADE_UNIT,
        available: hpMaximumTrade + stanceMaximumTrade >= XIANXIA_REALM_ASCENSION_TRADE_UNIT,
        hp_max: hpMax,
        stance_max: stanceMax,
        hp_maximum_trade: hpMaximumTrade,
        stance_maximum_trade: stanceMaximumTrade,
        max_trade_points: Math.floor(Math.max(0, hpMax + stanceMax) / XIANXIA_REALM_ASCENSION_TRADE_UNIT),
    };
}
function xianxiaCultivationHistoryRows(xianxia) {
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
            .filter((detail) => detail !== null),
    }));
}
const XIANXIA_CULTIVATION_HISTORY_DETAIL_LABELS = [
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
function systemsEntryHref(systemsRef, campaignSlug) {
    const slug = String(systemsRef.slug || "").trim();
    const safeCampaignSlug = String(campaignSlug || "").trim();
    return slug && safeCampaignSlug ? `/app-next/campaigns/${safeCampaignSlug}/systems/entries/${slug}` : "";
}
function normalizeRealmLabel(value) {
    const normalized = String(value || "").trim().toLowerCase();
    for (const realm of XIANXIA_REALM_ASCENSION_REALMS) {
        if (realm.toLowerCase() === normalized) {
            return realm;
        }
    }
    return "Mortal";
}
function stringifyEditorValue(value) {
    return value === null || value === undefined ? "" : String(value);
}
function buildReferenceField(name, label, helpText, value) {
    return {
        name,
        label,
        help_text: helpText,
        value: stringifyEditorValue(value),
    };
}
function joinEditorMultilineValues(value) {
    return asArray(value)
        .map((entry) => stringifyEditorValue(entry).trim())
        .filter(Boolean)
        .join("\n");
}
function parseEditorMultilineValues(value) {
    const values = [];
    const seen = new Set();
    for (const line of stringifyEditorValue(value).replace(/\r/g, "").split("\n")) {
        for (const fragment of line.split(",")) {
            const entry = fragment.trim();
            const normalized = entry.toLowerCase();
            if (!entry || seen.has(normalized)) {
                continue;
            }
            seen.add(normalized);
            values.push(entry);
        }
    }
    return values;
}
function normalizeEditorStatAdjustments(value) {
    const rawAdjustments = asRecord(value);
    const adjustments = {};
    for (const field of ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELDS) {
        const parsed = Number.parseInt(String(rawAdjustments[field.key] ?? "0").trim() || "0", 10);
        if (Number.isFinite(parsed) && parsed !== 0) {
            adjustments[field.key] = parsed;
        }
    }
    return adjustments;
}
function parseEditorStatAdjustments(values) {
    const adjustments = {};
    for (const field of ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELDS) {
        const rawValue = String(values[field.name] ?? "").trim();
        if (!rawValue) {
            continue;
        }
        if (!/^[-+]?\d+$/.test(rawValue)) {
            return { status: "validation_error", message: `The ${field.label.toLowerCase()} must be a whole number.` };
        }
        const parsed = Number.parseInt(rawValue, 10);
        if (parsed !== 0) {
            adjustments[field.key] = parsed;
        }
    }
    return { status: "ok", adjustments };
}
function normalizeEditorRecoverablePenaltyTarget(penalty) {
    const kind = stringifyEditorValue(penalty.kind).trim();
    if (kind === "max_hp") {
        return "max_hp";
    }
    if (kind === "ability_score") {
        const abilityKey = stringifyEditorValue(penalty.ability_key).trim().toLowerCase();
        return DND_ABILITY_KEYS.includes(abilityKey)
            ? `ability_score:${abilityKey}`
            : "";
    }
    return "";
}
function normalizeEditorRecoverablePenalties(value) {
    const penalties = [];
    for (const rawPenalty of asArray(value)) {
        const penalty = asRecord(rawPenalty);
        const target = normalizeEditorRecoverablePenaltyTarget(penalty);
        const amount = Number.parseInt(stringifyEditorValue(penalty.amount).trim(), 10);
        if (!target || !Number.isFinite(amount) || amount <= 0) {
            continue;
        }
        const normalized = {
            id: stringifyEditorValue(penalty.id).trim(),
            kind: target === "max_hp" ? "max_hp" : "ability_score",
            amount,
            source: stringifyEditorValue(penalty.source).split(/\s+/).filter(Boolean).join(" "),
            notes: stringifyEditorValue(penalty.notes).trim(),
        };
        if (target.startsWith("ability_score:")) {
            normalized.ability_key = target.split(":", 2)[1];
        }
        penalties.push(normalized);
    }
    return penalties;
}
function buildRecoverablePenaltyRows(value) {
    const penalties = normalizeEditorRecoverablePenalties(value);
    const rowCount = Math.max(penalties.length + 1, ADVANCED_EDITOR_MIN_RECOVERABLE_PENALTY_ROWS);
    const rows = [];
    for (let index = 1; index <= rowCount; index += 1) {
        const penalty = asRecord(penalties[index - 1]);
        rows.push({
            index,
            id: stringifyEditorValue(penalty.id).trim(),
            source: stringifyEditorValue(penalty.source).trim(),
            target: normalizeEditorRecoverablePenaltyTarget(penalty),
            amount: penalty.amount === null || penalty.amount === undefined ? "" : stringifyEditorValue(penalty.amount).trim(),
            notes: stringifyEditorValue(penalty.notes),
        });
    }
    return rows;
}
function parseEditorRecoverablePenaltyTarget(value) {
    const cleanValue = value.trim().toLowerCase();
    if (cleanValue === "max_hp") {
        return { status: "ok", kind: "max_hp", abilityKey: "" };
    }
    if (cleanValue.startsWith("ability_score:")) {
        const abilityKey = cleanValue.split(":", 2)[1] || "";
        if (DND_ABILITY_KEYS.includes(abilityKey)) {
            return { status: "ok", kind: "ability_score", abilityKey: abilityKey };
        }
    }
    return { status: "validation_error", message: "Choose a valid recoverable-penalty target." };
}
function maxEditorRecoverablePenaltyRowIndex(values) {
    let maxIndex = 0;
    for (const fieldName of Object.keys(values)) {
        const match = fieldName.match(ADVANCED_EDITOR_RECOVERABLE_PENALTY_FIELD_PATTERN);
        if (!match) {
            continue;
        }
        maxIndex = Math.max(maxIndex, Number.parseInt(match[2], 10));
    }
    return maxIndex;
}
function buildUniqueEditorId(prefix, name, usedIds) {
    const base = slugifyText(name) || prefix;
    let candidate = `${prefix}-${base}`;
    let index = 2;
    while (usedIds.has(candidate)) {
        candidate = `${prefix}-${base}-${index}`;
        index += 1;
    }
    return candidate;
}
function parseEditorRecoverablePenalties(values, existingPenalties) {
    const usedIds = new Set(existingPenalties.map((penalty) => stringifyEditorValue(penalty.id).trim()).filter(Boolean));
    const penalties = [];
    const rowCount = Math.max(maxEditorRecoverablePenaltyRowIndex(values), ADVANCED_EDITOR_MIN_RECOVERABLE_PENALTY_ROWS);
    for (let index = 1; index <= rowCount; index += 1) {
        const rawId = stringifyEditorValue(values[`recoverable_penalty_id_${index}`]).trim();
        const source = stringifyEditorValue(values[`recoverable_penalty_source_${index}`]).trim();
        const target = stringifyEditorValue(values[`recoverable_penalty_target_${index}`]).trim();
        const amountText = stringifyEditorValue(values[`recoverable_penalty_amount_${index}`]).trim();
        const notes = stringifyEditorValue(values[`recoverable_penalty_notes_${index}`]);
        const hasContent = Boolean(rawId || source || target || amountText || notes.trim());
        if (!hasContent) {
            continue;
        }
        if (!source) {
            return { status: "validation_error", message: "Each recoverable penalty needs a source label." };
        }
        if (!target) {
            return { status: "validation_error", message: "Each recoverable penalty needs a target." };
        }
        if (!/^[-+]?\d+$/.test(amountText)) {
            return {
                status: "validation_error",
                message: `The recoverable penalty amount for '${source}' must be a whole number.`,
            };
        }
        const amount = Number.parseInt(amountText, 10);
        if (amount < 0) {
            return {
                status: "validation_error",
                message: `The recoverable penalty amount for '${source}' cannot be negative.`,
            };
        }
        if (amount <= 0) {
            return { status: "validation_error", message: "Each recoverable penalty needs a positive amount." };
        }
        const parsedTarget = parseEditorRecoverablePenaltyTarget(target);
        if (parsedTarget.status === "validation_error") {
            return parsedTarget;
        }
        const penaltyId = rawId || buildUniqueEditorId("recoverable-penalty", source, usedIds);
        usedIds.add(penaltyId);
        const penalty = {
            id: penaltyId,
            kind: parsedTarget.kind,
            amount,
            source,
            notes: notes.trim(),
        };
        if (parsedTarget.abilityKey) {
            penalty.ability_key = parsedTarget.abilityKey;
        }
        penalties.push(penalty);
    }
    return { status: "ok", penalties };
}
function hasEditorRecoverablePenaltyValues(values) {
    return Object.keys(values).some((fieldName) => ADVANCED_EDITOR_RECOVERABLE_PENALTY_FIELD_PATTERN.test(fieldName));
}
function extractEditorPageRefValue(value) {
    if (typeof value === "string") {
        return value.trim();
    }
    const record = asRecord(value);
    return stringifyEditorValue(record.slug || record.page_ref || record.ref || record.path).trim();
}
function normalizeCampaignOptionStringList(value) {
    const rawItems = typeof value === "string"
        ? value.replaceAll("\r", "").replaceAll("\n", ",").split(",")
        : Array.isArray(value)
            ? value
            : [];
    const results = [];
    const seen = new Set();
    for (const rawItem of rawItems) {
        if (typeof rawItem === "object" && rawItem !== null) {
            continue;
        }
        const cleanItem = stringifyEditorValue(rawItem).trim();
        const normalized = cleanItem.toLowerCase();
        if (!cleanItem || seen.has(normalized)) {
            continue;
        }
        seen.add(normalized);
        results.push(cleanItem);
    }
    return results;
}
function normalizeAdvancedEditorCampaignOptionStatAdjustments(value) {
    const rawAdjustments = asRecord(value);
    const adjustments = {};
    for (const [key, rawValue] of Object.entries(rawAdjustments)) {
        const parsed = Number.parseInt(String(rawValue ?? "").trim(), 10);
        if (Number.isFinite(parsed) && parsed !== 0) {
            adjustments[key] = parsed;
        }
    }
    return adjustments;
}
function normalizeAdvancedEditorCampaignOptionSpellGrants(value) {
    const grants = [];
    const seen = new Set();
    for (const rawGrant of asArray(value)) {
        const grant = asRecord(rawGrant);
        const spellValue = stringifyEditorValue(grant.value).trim();
        if (!spellValue) {
            continue;
        }
        const marker = JSON.stringify([
            spellValue.toLowerCase(),
            stringifyEditorValue(grant.mark).trim().toLowerCase(),
            Boolean(grant.always_prepared),
            Boolean(grant.ritual),
        ]);
        if (seen.has(marker)) {
            continue;
        }
        seen.add(marker);
        grants.push({
            value: spellValue,
            mark: stringifyEditorValue(grant.mark).trim(),
            always_prepared: Boolean(grant.always_prepared),
            ritual: Boolean(grant.ritual),
        });
    }
    return grants;
}
function normalizeAdvancedEditorCampaignOptionResource(value) {
    const resource = asRecord(value);
    if (Object.keys(resource).length === 0) {
        return null;
    }
    const normalized = {};
    const label = stringifyEditorValue(resource.label || resource.name).trim();
    if (label) {
        normalized.label = label;
    }
    const maxValue = Number.parseInt(String(resource.max ?? resource.maximum ?? "").trim(), 10);
    if (Number.isFinite(maxValue) && maxValue >= 0) {
        normalized.max = maxValue;
    }
    const resetOn = stringifyEditorValue(resource.reset_on || resource.resetOn).trim().toLowerCase();
    if (resetOn) {
        normalized.reset_on = ADVANCED_EDITOR_RESOURCE_RESET_VALUES.has(resetOn) ? resetOn : "manual";
    }
    return Object.keys(normalized).length > 0 ? normalized : null;
}
function buildAdvancedEditorCampaignPageCharacterOption(record) {
    const rawOption = asRecord(asRecord(record.metadata).character_option);
    if (Object.keys(rawOption).length === 0) {
        return null;
    }
    const pageRef = stringifyEditorValue(record.page_ref).trim();
    const title = stringifyEditorValue(record.page.title).trim() || pageRef;
    const summary = stringifyEditorValue(record.page.summary).trim();
    const defaultKind = stringifyEditorValue(record.page.section).trim() === CAMPAIGN_ITEMS_SECTION ? "item" : "feature";
    const rawKind = stringifyEditorValue(rawOption.kind).trim().toLowerCase();
    const kind = ["feature", "item", "feat", "species", "background"].includes(rawKind) ? rawKind : defaultKind;
    const grants = asRecord(rawOption.grants);
    const proficiencies = asRecord(rawOption.proficiencies);
    const normalized = {
        kind,
        page_ref: pageRef,
        title,
        summary,
        display_name: stringifyEditorValue(rawOption.name).trim() || title,
        proficiencies: {
            armor: normalizeCampaignOptionStringList("armor" in proficiencies ? proficiencies.armor : grants.armor ?? rawOption.armor),
            weapons: normalizeCampaignOptionStringList("weapons" in proficiencies ? proficiencies.weapons : grants.weapons ?? rawOption.weapons),
            tools: normalizeCampaignOptionStringList("tools" in proficiencies ? proficiencies.tools : grants.tools ?? rawOption.tools),
            languages: normalizeCampaignOptionStringList("languages" in proficiencies ? proficiencies.languages : grants.languages ?? rawOption.languages),
            skills: normalizeCampaignOptionStringList("skills" in proficiencies ? proficiencies.skills : grants.skills ?? rawOption.skills),
        },
        stat_adjustments: normalizeAdvancedEditorCampaignOptionStatAdjustments("stat_adjustments" in grants ? grants.stat_adjustments : rawOption.stat_adjustments),
        spells: normalizeAdvancedEditorCampaignOptionSpellGrants("spells" in grants ? grants.spells : rawOption.spells),
    };
    if (rawOption.base_rule_refs !== undefined) {
        normalized.base_rule_refs = JSON.parse(JSON.stringify(rawOption.base_rule_refs));
    }
    if (rawOption.spell_support !== undefined) {
        normalized.spell_support = JSON.parse(JSON.stringify(rawOption.spell_support));
    }
    else if (rawOption.spellSupport !== undefined) {
        normalized.spell_support = JSON.parse(JSON.stringify(rawOption.spellSupport));
    }
    if (rawOption.spell_manager !== undefined) {
        normalized.spell_manager = JSON.parse(JSON.stringify(rawOption.spell_manager));
    }
    else if (rawOption.spellManager !== undefined) {
        normalized.spell_manager = JSON.parse(JSON.stringify(rawOption.spellManager));
    }
    if (kind === "feature" || kind === "feat" || kind === "species" || kind === "background") {
        const activationType = stringifyEditorValue(rawOption.activation_type || "passive").trim().toLowerCase();
        normalized.feature_name = stringifyEditorValue(rawOption.name).trim() || title;
        normalized.description_markdown = stringifyEditorValue(rawOption.description_markdown || rawOption.description || summary).trim();
        normalized.activation_type = ADVANCED_EDITOR_FEATURE_ACTIVATION_VALUES.has(activationType)
            ? activationType
            : "passive";
        const resource = normalizeAdvancedEditorCampaignOptionResource("resource" in grants ? grants.resource : rawOption.resource);
        if (resource) {
            normalized.resource = resource;
        }
        if (rawOption.additional_spells !== undefined) {
            normalized.additional_spells = JSON.parse(JSON.stringify(rawOption.additional_spells));
        }
        else if (rawOption.additionalSpells !== undefined) {
            normalized.additional_spells = JSON.parse(JSON.stringify(rawOption.additionalSpells));
        }
        if (rawOption.modeled_effects !== undefined) {
            normalized.modeled_effects = JSON.parse(JSON.stringify(rawOption.modeled_effects));
        }
        else if (rawOption.modeledEffects !== undefined) {
            normalized.modeled_effects = JSON.parse(JSON.stringify(rawOption.modeledEffects));
        }
        if (kind === "feat") {
            normalized.feat_name = stringifyEditorValue(rawOption.name).trim() || title;
        }
        else if (kind === "species") {
            normalized.species_name = stringifyEditorValue(rawOption.name).trim() || title;
            if (rawOption.size !== undefined) {
                normalized.size = JSON.parse(JSON.stringify(rawOption.size));
            }
            if (rawOption.speed !== undefined) {
                normalized.speed = JSON.parse(JSON.stringify(rawOption.speed));
            }
        }
        else if (kind === "background") {
            normalized.background_name = stringifyEditorValue(rawOption.name).trim() || title;
        }
        return normalized;
    }
    const parsedQuantity = Number.parseInt(String(rawOption.quantity ?? "").trim(), 10);
    const itemName = stringifyEditorValue(rawOption.item_name).trim()
        || stringifyEditorValue(rawOption.name).trim()
        || title;
    normalized.item_name = itemName;
    normalized.quantity = Number.isFinite(parsedQuantity) && parsedQuantity > 0 ? parsedQuantity : 1;
    normalized.weight = stringifyEditorValue(rawOption.weight).trim();
    normalized.notes = stringifyEditorValue(rawOption.notes).trim() || summary;
    normalized.display_name = normalized.display_name || itemName;
    return normalized;
}
function advancedEditorCampaignPageOptionAllowedForLinkedField(record, fieldKind, campaignOption) {
    const requiredSection = ADVANCED_EDITOR_LINKED_CAMPAIGN_PAGE_REQUIRED_SECTION_BY_FIELD_KIND[fieldKind];
    if (stringifyEditorValue(record.page.section).trim() !== requiredSection) {
        return false;
    }
    const optionKind = stringifyEditorValue(asRecord(campaignOption).kind).trim().toLowerCase();
    if (!optionKind) {
        return true;
    }
    return ADVANCED_EDITOR_LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND[fieldKind].has(optionKind);
}
function buildAdvancedEditorCampaignPageOptions(campaignPageRecords, fieldKind, includePageRefs = new Set()) {
    const options = [];
    for (const record of campaignPageRecords) {
        const pageRef = extractEditorPageRefValue(record.page_ref);
        if (!pageRef) {
            continue;
        }
        const title = stringifyEditorValue(record.page.title).trim() || pageRef;
        const section = stringifyEditorValue(record.page.section).trim();
        const subsection = stringifyEditorValue(record.page.subsection).trim();
        const campaignOption = buildAdvancedEditorCampaignPageCharacterOption(record);
        if (!includePageRefs.has(pageRef)
            && !advancedEditorCampaignPageOptionAllowedForLinkedField(record, fieldKind, campaignOption)) {
            continue;
        }
        const optionTitle = stringifyEditorValue(asRecord(campaignOption).display_name).trim() || title;
        const labelParts = [optionTitle];
        if (section) {
            labelParts.push(subsection ? `${section} / ${subsection}` : section);
        }
        options.push({
            value: pageRef,
            label: labelParts.join(" | "),
            title: optionTitle,
            campaign_option: campaignOption ? JSON.parse(JSON.stringify(campaignOption)) : null,
        });
    }
    return options;
}
function buildAdvancedEditorCampaignPageLookup(campaignPageRecords, fieldKind, includePageRefs = new Set()) {
    const lookup = {};
    for (const option of buildAdvancedEditorCampaignPageOptions(campaignPageRecords, fieldKind, includePageRefs)) {
        const pageRef = stringifyEditorValue(option.value).trim();
        if (!pageRef) {
            continue;
        }
        lookup[pageRef] = {
            page_ref: pageRef,
            label: stringifyEditorValue(option.label).trim() || pageRef,
            title: stringifyEditorValue(option.title).trim() || pageRef,
            campaign_option: asRecord(option.campaign_option),
        };
    }
    return lookup;
}
function normalizeSelectedAdvancedEditorCampaignPageRef(rawValue, campaignPageLookup) {
    const pageRef = extractEditorPageRefValue(rawValue);
    if (!pageRef) {
        return "";
    }
    if (!campaignPageLookup[pageRef]) {
        throw new Error("Choose a valid linked campaign page.");
    }
    return pageRef;
}
function editorManualEquipmentEntries(definition) {
    return asArray(definition.equipment_catalog)
        .map((value) => asRecord(value))
        .filter((item) => stringifyEditorValue(item.source_kind).trim() === ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND);
}
function buildManualEquipmentRows(definition) {
    const manualItems = editorManualEquipmentEntries(definition);
    const rowCount = Math.max(manualItems.length + 1, ADVANCED_EDITOR_MIN_MANUAL_EQUIPMENT_ROWS);
    const rows = [];
    for (let index = 1; index <= rowCount; index += 1) {
        const item = asRecord(manualItems[index - 1]);
        const quantity = item.default_quantity === null || item.default_quantity === undefined
            ? ""
            : stringifyEditorValue(item.default_quantity).trim();
        rows.push({
            index,
            id: stringifyEditorValue(item.id).trim(),
            name: stringifyEditorValue(item.name).trim(),
            page_ref: extractEditorPageRefValue(item.page_ref),
            quantity,
            weight: stringifyEditorValue(item.weight).trim(),
            notes: stringifyEditorValue(item.notes),
            campaign_option: { ...asRecord(item.campaign_option) },
        });
    }
    return rows;
}
function buildExistingManagedEquipmentRows(definition) {
    return asArray(definition.equipment_catalog)
        .map((value) => asRecord(value))
        .filter((item) => stringifyEditorValue(item.source_kind).trim() !== ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND)
        .map((item) => ({
        name: stringifyEditorValue(item.name).trim() || "Item",
        quantity: createContextInteger(item.default_quantity, 0),
        weight: stringifyEditorValue(item.weight).trim(),
    }));
}
function maxEditorManualEquipmentRowIndex(values) {
    let maxIndex = 0;
    for (const fieldName of Object.keys(values)) {
        const match = fieldName.match(ADVANCED_EDITOR_MANUAL_EQUIPMENT_FIELD_PATTERN);
        if (!match) {
            continue;
        }
        maxIndex = Math.max(maxIndex, Number.parseInt(match[2], 10));
    }
    return maxIndex;
}
function hasEditorManualEquipmentValues(values) {
    return Object.keys(values).some((fieldName) => ADVANCED_EDITOR_MANUAL_EQUIPMENT_FIELD_PATTERN.test(fieldName));
}
function parseEditorManualEquipmentQuantity(value) {
    const rawValue = value.trim();
    if (!rawValue) {
        return 1;
    }
    if (!/^[+-]?\d+$/.test(rawValue)) {
        return { status: "validation_error", message: "Custom equipment quantities must be whole numbers." };
    }
    const quantity = Number.parseInt(rawValue, 10);
    if (quantity < 0) {
        return { status: "validation_error", message: "Custom equipment quantities cannot be negative." };
    }
    return quantity;
}
function parseEditorManualEquipmentItems(values, definition, campaignPageLookup = {}) {
    const existingManualItems = editorManualEquipmentEntries(definition);
    const existingById = new Map(existingManualItems
        .map((item) => [stringifyEditorValue(item.id).trim(), item])
        .filter(([itemId]) => Boolean(itemId)));
    const usedIds = new Set([...existingById.keys()]);
    const items = [];
    const rowCount = Math.max(maxEditorManualEquipmentRowIndex(values), ADVANCED_EDITOR_MIN_MANUAL_EQUIPMENT_ROWS);
    for (let index = 1; index <= rowCount; index += 1) {
        const rawId = stringifyEditorValue(values[`manual_item_id_${index}`]).trim();
        const existing = rawId ? existingById.get(rawId) : undefined;
        const rawName = stringifyEditorValue(values[`manual_item_name_${index}`]).trim();
        let pageRef = stringifyEditorValue(values[`manual_item_page_ref_${index}`]).trim();
        const quantityText = stringifyEditorValue(values[`manual_item_quantity_${index}`]).trim();
        const weightText = stringifyEditorValue(values[`manual_item_weight_${index}`]).trim();
        const notesText = stringifyEditorValue(values[`manual_item_notes_${index}`]);
        const hasContent = Boolean(rawId || rawName || pageRef || quantityText || weightText || notesText.trim());
        if (!hasContent) {
            continue;
        }
        let campaignOption = {};
        try {
            pageRef = normalizeSelectedAdvancedEditorCampaignPageRef(pageRef, campaignPageLookup);
            campaignOption = asRecord(asRecord(campaignPageLookup[pageRef]).campaign_option);
            const optionKind = stringifyEditorValue(campaignOption.kind).trim().toLowerCase();
            if (!ADVANCED_EDITOR_LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND.campaign_page_item.has(optionKind)) {
                campaignOption = {};
            }
        }
        catch (error) {
            return {
                status: "validation_error",
                message: error instanceof Error ? error.message : "Choose a valid linked campaign page.",
            };
        }
        const name = rawName
            || stringifyEditorValue(campaignOption.item_name).trim()
            || stringifyEditorValue(campaignOption.display_name).trim()
            || stringifyEditorValue(campaignOption.name).trim()
            || stringifyEditorValue(asRecord(existing).name).trim()
            || stringifyEditorValue(asRecord(campaignPageLookup[pageRef]).title).trim();
        if (!name) {
            return { status: "validation_error", message: "Each custom equipment row needs an item name." };
        }
        const parsedQuantity = parseEditorManualEquipmentQuantity(String(quantityText || stringifyEditorValue(campaignOption.quantity)).trim());
        if (typeof parsedQuantity !== "number") {
            return parsedQuantity;
        }
        const weight = String(weightText || stringifyEditorValue(campaignOption.weight)).trim();
        const notes = String(notesText || stringifyEditorValue(campaignOption.notes)).trim();
        const preservedId = rawId || stringifyEditorValue(asRecord(existing).id).trim();
        if (preservedId) {
            usedIds.delete(preservedId);
        }
        const itemId = preservedId || buildUniqueEditorId("manual-item", name, usedIds);
        usedIds.add(itemId);
        const nextItem = { ...asRecord(existing) };
        delete nextItem.campaign_option;
        delete nextItem.systems_ref;
        delete nextItem.page_ref;
        nextItem.id = itemId;
        nextItem.name = name;
        nextItem.default_quantity = parsedQuantity;
        nextItem.weight = weight;
        nextItem.notes = notes;
        nextItem.source_kind = ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND;
        if (pageRef) {
            nextItem.page_ref = pageRef;
            if (Object.keys(campaignOption).length > 0) {
                nextItem.campaign_option = JSON.parse(JSON.stringify(campaignOption));
            }
            else {
                const existingCampaignOption = asRecord(asRecord(existing).campaign_option);
                if (Object.keys(existingCampaignOption).length > 0) {
                    nextItem.campaign_option = existingCampaignOption;
                }
            }
            const existingSystemsRef = asRecord(asRecord(existing).systems_ref);
            if (Object.keys(existingSystemsRef).length > 0) {
                nextItem.systems_ref = existingSystemsRef;
            }
        }
        items.push(nextItem);
    }
    const nextIds = new Set(items.map((item) => stringifyEditorValue(item.id).trim()).filter(Boolean));
    const removedItemIds = [...existingById.keys()].filter((itemId) => !nextIds.has(itemId));
    return { status: "ok", items, removedItemIds };
}
function editorCustomFeatureEntries(definition) {
    return asArray(definition.features)
        .map((value) => asRecord(value))
        .filter((feature) => stringifyEditorValue(feature.category).trim() === ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY);
}
function manualFeatureTrackerId(featureId) {
    return `${ADVANCED_EDITOR_CUSTOM_FEATURE_RESOURCE_PREFIX}:${featureId}`;
}
function resourceTemplateLookup(definition) {
    return new Map(asArray(definition.resource_templates)
        .map((value) => asRecord(value))
        .map((template) => [stringifyEditorValue(template.id).trim(), template])
        .filter(([templateId]) => Boolean(templateId)));
}
function normalizeEditorFeatureActivationType(value) {
    const cleanValue = stringifyEditorValue(value).trim().toLowerCase();
    return cleanValue || "passive";
}
function normalizeEditorFeatureResourceResetOn(value) {
    const cleanValue = stringifyEditorValue(value).trim().toLowerCase();
    return cleanValue || "manual";
}
function buildCustomFeatureRows(definition) {
    const customFeatures = editorCustomFeatureEntries(definition);
    const templates = resourceTemplateLookup(definition);
    const rowCount = Math.max(customFeatures.length + 1, ADVANCED_EDITOR_MIN_CUSTOM_FEATURE_ROWS);
    const rows = [];
    for (let index = 1; index <= rowCount; index += 1) {
        const feature = asRecord(customFeatures[index - 1]);
        const tracker = templates.get(stringifyEditorValue(feature.tracker_ref).trim()) ?? {};
        const resourceMax = tracker.max === null || tracker.max === undefined
            ? ""
            : stringifyEditorValue(tracker.max).trim();
        rows.push({
            index,
            id: stringifyEditorValue(feature.id).trim(),
            name: stringifyEditorValue(feature.name).trim(),
            page_ref: extractEditorPageRefValue(feature.page_ref),
            activation_type: normalizeEditorFeatureActivationType(feature.activation_type),
            description_markdown: stringifyEditorValue(feature.description_markdown),
            resource_max: resourceMax,
            resource_reset_on: normalizeEditorFeatureResourceResetOn(tracker.reset_on),
            spell_manager: { ...asRecord(feature.spell_manager) },
            campaign_option: { ...asRecord(feature.campaign_option) },
            choice_fields: [],
        });
    }
    return rows;
}
function maxEditorCustomFeatureRowIndex(values) {
    let maxIndex = 0;
    for (const fieldName of Object.keys(values)) {
        const match = fieldName.match(ADVANCED_EDITOR_CUSTOM_FEATURE_FIELD_PATTERN);
        if (!match) {
            continue;
        }
        maxIndex = Math.max(maxIndex, Number.parseInt(match[2], 10));
    }
    return maxIndex;
}
function hasEditorCustomFeatureValues(values) {
    return Object.keys(values).some((fieldName) => ADVANCED_EDITOR_CUSTOM_FEATURE_FIELD_PATTERN.test(fieldName));
}
function parseEditorCustomFeatureResourceMax(value, label) {
    const rawValue = value.trim();
    if (!rawValue) {
        return null;
    }
    if (!/^[+-]?\d+$/.test(rawValue)) {
        return { status: "validation_error", message: `The resource max for '${label}' must be a whole number.` };
    }
    const parsedValue = Number.parseInt(rawValue, 10);
    if (parsedValue < 0) {
        return { status: "validation_error", message: `The resource max for '${label}' cannot be negative.` };
    }
    return parsedValue;
}
function buildManualFeatureResourceTemplate({ trackerId, featureName, maxValue, resetOn, existingTemplate, displayOrder, }) {
    const cleanResetOn = normalizeEditorFeatureResourceResetOn(resetOn);
    const templateInitial = createContextInteger(asRecord(existingTemplate).initial_current, maxValue);
    return {
        id: trackerId,
        label: featureName,
        category: ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY,
        initial_current: Math.min(templateInitial, maxValue),
        max: maxValue,
        reset_on: cleanResetOn,
        reset_to: cleanResetOn === "short_rest" || cleanResetOn === "long_rest" ? "max" : "unchanged",
        rest_behavior: cleanResetOn === "short_rest" || cleanResetOn === "long_rest"
            ? "confirm_before_reset"
            : "manual_only",
        notes: stringifyEditorValue(asRecord(existingTemplate).notes).trim(),
        display_order: displayOrder,
    };
}
function parseEditorCustomFeatures(values, definition, campaignPageLookup = {}) {
    const existingFeatures = editorCustomFeatureEntries(definition);
    const existingById = new Map(existingFeatures
        .map((feature) => [stringifyEditorValue(feature.id).trim(), feature])
        .filter(([featureId]) => Boolean(featureId)));
    const templateById = resourceTemplateLookup(definition);
    const usedIds = new Set([...existingById.keys()]);
    const seenNames = new Set();
    const features = [];
    const resourceTemplates = [];
    const rowCount = Math.max(maxEditorCustomFeatureRowIndex(values), ADVANCED_EDITOR_MIN_CUSTOM_FEATURE_ROWS);
    for (let index = 1; index <= rowCount; index += 1) {
        const rawId = stringifyEditorValue(values[`custom_feature_id_${index}`]).trim();
        const existing = rawId ? existingById.get(rawId) : undefined;
        const rawName = stringifyEditorValue(values[`custom_feature_name_${index}`]).trim();
        let pageRef = stringifyEditorValue(values[`custom_feature_page_ref_${index}`]).trim();
        const activationType = normalizeEditorFeatureActivationType(values[`custom_feature_activation_type_${index}`]);
        const descriptionMarkdown = stringifyEditorValue(values[`custom_feature_description_${index}`]);
        const resourceMaxText = stringifyEditorValue(values[`custom_feature_resource_max_${index}`]).trim();
        const hasContent = Boolean(rawName || pageRef || descriptionMarkdown.trim() || resourceMaxText);
        if (!hasContent) {
            continue;
        }
        const name = rawName || stringifyEditorValue(asRecord(existing).name).trim();
        if (!name) {
            return { status: "validation_error", message: "Each custom feature needs a name." };
        }
        if (!ADVANCED_EDITOR_FEATURE_ACTIVATION_VALUES.has(activationType)) {
            return { status: "validation_error", message: "Choose a valid activation type for each custom feature." };
        }
        try {
            pageRef = normalizeSelectedAdvancedEditorCampaignPageRef(pageRef, campaignPageLookup);
        }
        catch (error) {
            return {
                status: "validation_error",
                message: error instanceof Error ? error.message : "Choose a valid linked campaign page.",
            };
        }
        const parsedResourceMax = parseEditorCustomFeatureResourceMax(resourceMaxText, name);
        if (typeof parsedResourceMax === "object" && parsedResourceMax !== null) {
            return parsedResourceMax;
        }
        const resourceMax = parsedResourceMax ?? 0;
        const resourceResetOn = normalizeEditorFeatureResourceResetOn(values[`custom_feature_resource_reset_on_${index}`]);
        if (!ADVANCED_EDITOR_RESOURCE_RESET_VALUES.has(resourceResetOn)) {
            return { status: "validation_error", message: "Choose a valid reset cadence for each custom feature." };
        }
        const normalizedName = slugifyText(name) || name.toLowerCase();
        if (seenNames.has(normalizedName)) {
            return { status: "validation_error", message: `Custom feature '${name}' is listed more than once.` };
        }
        seenNames.add(normalizedName);
        const preservedId = rawId || stringifyEditorValue(asRecord(existing).id).trim();
        if (preservedId) {
            usedIds.delete(preservedId);
        }
        const featureId = preservedId || buildUniqueEditorId("custom-feature", name, usedIds);
        usedIds.add(featureId);
        const nextFeature = { ...asRecord(existing) };
        delete nextFeature.campaign_option;
        delete nextFeature.systems_ref;
        delete nextFeature.page_ref;
        delete nextFeature.spell_manager;
        nextFeature.id = featureId;
        nextFeature.name = name;
        nextFeature.category = ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY;
        nextFeature.source = stringifyEditorValue(nextFeature.source).trim() || "Campaign";
        nextFeature.description_markdown = descriptionMarkdown.trim();
        nextFeature.activation_type = activationType;
        nextFeature.tracker_ref = null;
        if (pageRef) {
            nextFeature.page_ref = pageRef;
            const campaignOption = asRecord(asRecord(existing).campaign_option);
            if (Object.keys(campaignOption).length > 0) {
                nextFeature.campaign_option = campaignOption;
            }
            const systemsRef = asRecord(asRecord(existing).systems_ref);
            if (Object.keys(systemsRef).length > 0) {
                nextFeature.systems_ref = systemsRef;
            }
            const spellManager = asRecord(asRecord(existing).spell_manager);
            if (Object.keys(spellManager).length > 0) {
                nextFeature.spell_manager = spellManager;
            }
        }
        if (resourceMax > 0) {
            const trackerId = manualFeatureTrackerId(featureId);
            nextFeature.tracker_ref = trackerId;
            resourceTemplates.push(buildManualFeatureResourceTemplate({
                trackerId,
                featureName: name,
                maxValue: resourceMax,
                resetOn: resourceResetOn,
                existingTemplate: templateById.get(trackerId),
                displayOrder: resourceTemplates.length,
            }));
        }
        features.push(nextFeature);
    }
    const nextResourceIds = new Set(resourceTemplates.map((template) => stringifyEditorValue(template.id).trim()).filter(Boolean));
    const existingResourceIds = existingFeatures
        .map((feature) => stringifyEditorValue(feature.tracker_ref || manualFeatureTrackerId(stringifyEditorValue(feature.id))).trim())
        .filter(Boolean);
    const removedResourceIds = existingResourceIds.filter((resourceId) => !nextResourceIds.has(resourceId));
    return { status: "ok", features, resourceTemplates, removedResourceIds };
}
function adjustSpeedLabel(value, delta) {
    const cleanValue = stringifyEditorValue(value).trim();
    if (!cleanValue || delta === 0) {
        return cleanValue;
    }
    const match = cleanValue.match(/-?\d+/);
    if (!match || match.index === undefined) {
        return cleanValue;
    }
    const updatedValue = Math.max(Number.parseInt(match[0], 10) + delta, 0);
    return `${cleanValue.slice(0, match.index)}${updatedValue}${cleanValue.slice(match.index + match[0].length)}`;
}
function adjustAbilityScorePayload(value, delta) {
    const payload = { ...asRecord(value) };
    const currentScore = createContextInteger(payload.score);
    const currentModifier = abilityModifier(currentScore);
    const updatedScore = Math.max(currentScore + delta, 0);
    const updatedModifier = abilityModifier(updatedScore);
    const currentSaveBonus = Number.isFinite(Number(payload.save_bonus))
        ? createContextInteger(payload.save_bonus)
        : currentModifier;
    payload.score = updatedScore;
    payload.modifier = updatedModifier;
    payload.save_bonus = currentSaveBonus + (updatedModifier - currentModifier);
    return payload;
}
function applyEditorStatAdjustment(stats, key, value) {
    if (key === "max_hp") {
        stats.max_hp = Math.max(createContextInteger(stats.max_hp) + value, 1);
    }
    else if (key === "armor_class") {
        stats.armor_class = Math.max(createContextInteger(stats.armor_class) + value, 0);
    }
    else if (key === "initiative_bonus") {
        stats.initiative_bonus = createContextInteger(stats.initiative_bonus) + value;
    }
    else if (key === "speed") {
        stats.speed = adjustSpeedLabel(stats.speed, value);
    }
    else if (key === "passive_perception") {
        stats.passive_perception = Math.max(createContextInteger(stats.passive_perception) + value, 0);
    }
    else if (key === "passive_insight") {
        stats.passive_insight = Math.max(createContextInteger(stats.passive_insight) + value, 0);
    }
    else if (key === "passive_investigation") {
        stats.passive_investigation = Math.max(createContextInteger(stats.passive_investigation) + value, 0);
    }
}
function applyEditorRecoverableStatPenalties(stats, penalties, options = {}) {
    const nextStats = deepCloneRecord(stats);
    if (penalties.length === 0) {
        delete nextStats.recoverable_penalties;
        return nextStats;
    }
    const direction = options.reverse ? 1 : -1;
    const maxHpPenalty = penalties
        .filter((penalty) => stringifyEditorValue(penalty.kind).trim() === "max_hp")
        .reduce((total, penalty) => total + createContextInteger(penalty.amount), 0);
    if (maxHpPenalty !== 0) {
        nextStats.max_hp = Math.max(createContextInteger(nextStats.max_hp) + direction * maxHpPenalty, 0);
    }
    const abilityScores = deepCloneRecord(nextStats.ability_scores);
    for (const penalty of penalties) {
        if (stringifyEditorValue(penalty.kind).trim() !== "ability_score") {
            continue;
        }
        const abilityKey = stringifyEditorValue(penalty.ability_key).trim().toLowerCase();
        if (!DND_ABILITY_KEYS.includes(abilityKey)) {
            continue;
        }
        const delta = direction * createContextInteger(penalty.amount);
        const existingPayload = abilityScores[abilityKey];
        if (typeof existingPayload === "object" && existingPayload !== null && !Array.isArray(existingPayload)) {
            abilityScores[abilityKey] = adjustAbilityScorePayload(existingPayload, delta);
        }
        else {
            abilityScores[abilityKey] = Math.max(createContextInteger(existingPayload) + delta, 0);
        }
    }
    nextStats.ability_scores = abilityScores;
    if (!options.reverse) {
        nextStats.recoverable_penalties = penalties.map((penalty) => ({ ...penalty }));
    }
    return nextStats;
}
function stripEditorRecoverableStatPenalties(stats) {
    const existingPenalties = normalizeEditorRecoverablePenalties(stats.recoverable_penalties);
    const strippedStats = existingPenalties.length > 0
        ? applyEditorRecoverableStatPenalties(stats, existingPenalties, { reverse: true })
        : deepCloneRecord(stats);
    delete strippedStats.recoverable_penalties;
    return { stats: strippedStats, penalties: existingPenalties };
}
function stripEditorManualStatAdjustments(stats) {
    const nextStats = deepCloneRecord(stats);
    const existingAdjustments = normalizeEditorStatAdjustments(nextStats.manual_adjustments);
    delete nextStats.manual_adjustments;
    for (const [key, value] of Object.entries(existingAdjustments)) {
        applyEditorStatAdjustment(nextStats, key, -value);
    }
    return nextStats;
}
function applyEditorManualStatAdjustments(stats, adjustments) {
    const nextStats = deepCloneRecord(stats);
    for (const [key, value] of Object.entries(adjustments)) {
        applyEditorStatAdjustment(nextStats, key, value);
    }
    if (Object.keys(adjustments).length > 0) {
        nextStats.manual_adjustments = { ...adjustments };
    }
    else {
        delete nextStats.manual_adjustments;
    }
    return nextStats;
}
export function buildCharacterAdvancedEditorPayload({ campaign, characterSlug, definition, state, stateRevision, campaignPageRecords = [], }) {
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
    const proficiencies = asRecord(definition.proficiencies);
    const manualStatAdjustments = normalizeEditorStatAdjustments(asRecord(definition.stats).manual_adjustments);
    const recoverablePenaltyRows = buildRecoverablePenaltyRows(asRecord(definition.stats).recoverable_penalties);
    const equipment = buildManualEquipmentRows(definition);
    const features = buildCustomFeatureRows(definition);
    const featureLinkedPageRefs = new Set(features
        .map((feature) => extractEditorPageRefValue(feature.page_ref))
        .filter(Boolean));
    const equipmentLinkedPageRefs = new Set(equipment
        .map((item) => extractEditorPageRefValue(item.page_ref))
        .filter(Boolean));
    return {
        lane: "dnd5e",
        supported: true,
        unsupported_message: "",
        links,
        editor: {
            state_revision: stateRevision,
            proficiency_fields: ADVANCED_EDITOR_PROFICIENCY_FIELDS.map((field) => buildReferenceField(field.name, field.label, field.helpText, joinEditorMultilineValues(proficiencies[field.key]))),
            stat_adjustment_fields: ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELDS.map((field) => buildReferenceField(field.name, field.label, field.helpText, manualStatAdjustments[field.key] ?? "")),
            recoverable_penalty_rows: recoverablePenaltyRows,
            reference_fields: [
                buildReferenceField("physical_description_markdown", "Physical Description", "Markdown shown on the Personal page for durable appearance notes.", stateNotes.physical_description_markdown),
                buildReferenceField("background_markdown", "Background", "Markdown shown on the Personal page for durable background notes.", stateNotes.background_markdown ?? stateNotes.personal_background_markdown),
                buildReferenceField("biography_markdown", "Biography", "Markdown shown on the Notes page for reference-level character history.", profile.biography_markdown),
                buildReferenceField("personality_markdown", "Personality", "Markdown shown on the Notes page for personality traits, ideals, bonds, flaws, or similar notes.", profile.personality_markdown),
                buildReferenceField("additional_notes_markdown", "Additional Notes", "Markdown shown on the Notes page for other persistent reference material.", referenceNotes.additional_notes_markdown),
                buildReferenceField("allies_and_organizations_markdown", "Allies and Organizations", "Markdown shown on the Notes page for friendly factions, patrons, allies, or affiliations.", referenceNotes.allies_and_organizations_markdown),
            ],
            feature_rows: features,
            equipment_rows: equipment,
            activation_options: ADVANCED_EDITOR_FEATURE_ACTIVATION_OPTIONS.map((option) => ({ ...option })),
            resource_reset_options: ADVANCED_EDITOR_RESOURCE_RESET_OPTIONS.map((option) => ({ ...option })),
            recoverable_penalty_target_options: ADVANCED_EDITOR_RECOVERABLE_PENALTY_TARGET_OPTIONS.map((option) => ({ ...option })),
            campaign_page_options: buildAdvancedEditorCampaignPageOptions(campaignPageRecords, "campaign_page_feature", featureLinkedPageRefs),
            equipment_page_options: buildAdvancedEditorCampaignPageOptions(campaignPageRecords, "campaign_page_item", equipmentLinkedPageRefs),
            linked_feature_authoring_supported: true,
            linked_feature_authoring_message: "",
            existing_managed_equipment: buildExistingManagedEquipmentRows(definition),
        },
    };
}
export function applyCharacterAdvancedEditorReferenceUpdate(definition, payload, campaignPageRecords = []) {
    const rawValues = asRecord(payload.values);
    const values = {};
    for (const [rawKey, value] of Object.entries(rawValues)) {
        const fieldName = String(rawKey || "").trim();
        if (!fieldName) {
            continue;
        }
        if (Array.isArray(value)) {
            values[fieldName] = String(value.length > 0 ? value[value.length - 1] : "");
        }
        else if (value === null || value === undefined) {
            values[fieldName] = "";
        }
        else {
            values[fieldName] = String(value);
        }
    }
    const unsupportedFields = Object.keys(values).filter((fieldName) => !ADVANCED_EDITOR_SUPPORTED_FIELD_NAMES.has(fieldName) &&
        !ADVANCED_EDITOR_RECOVERABLE_PENALTY_FIELD_PATTERN.test(fieldName) &&
        !ADVANCED_EDITOR_MANUAL_EQUIPMENT_FIELD_PATTERN.test(fieldName) &&
        !ADVANCED_EDITOR_CUSTOM_FEATURE_FIELD_PATTERN.test(fieldName));
    if (unsupportedFields.length > 0) {
        return {
            status: "validation_error",
            message: `Unsupported Advanced Editor fields for the TypeScript reference/proficiency/stat-adjustment/recoverable-penalty/custom-feature/manual-equipment field slice: ${unsupportedFields.join(", ")}.`,
        };
    }
    const hasStatAdjustmentValues = Object.keys(values).some((fieldName) => ADVANCED_EDITOR_STAT_ADJUSTMENT_FIELD_NAMES.has(fieldName));
    const parsedStatAdjustments = hasStatAdjustmentValues ? parseEditorStatAdjustments(values) : null;
    if (parsedStatAdjustments?.status === "validation_error") {
        return parsedStatAdjustments;
    }
    const nextDefinition = JSON.parse(JSON.stringify(definition || {}));
    const campaignFeaturePageLookup = buildAdvancedEditorCampaignPageLookup(campaignPageRecords, "campaign_page_feature", new Set(editorCustomFeatureEntries(nextDefinition)
        .map((feature) => extractEditorPageRefValue(feature.page_ref))
        .filter(Boolean)));
    const campaignItemPageLookup = buildAdvancedEditorCampaignPageLookup(campaignPageRecords, "campaign_page_item", new Set(editorManualEquipmentEntries(nextDefinition)
        .map((item) => extractEditorPageRefValue(item.page_ref))
        .filter(Boolean)));
    const profile = { ...asRecord(nextDefinition.profile) };
    const referenceNotes = { ...asRecord(nextDefinition.reference_notes) };
    const proficiencies = { ...asRecord(nextDefinition.proficiencies) };
    const stateNoteValues = {};
    let manualEquipmentReconcile = { enabled: false, removedItemIds: [] };
    const strippedRecoverableStats = stripEditorRecoverableStatPenalties(asRecord(nextDefinition.stats));
    const parsedRecoverablePenalties = hasEditorRecoverablePenaltyValues(values)
        ? parseEditorRecoverablePenalties(values, strippedRecoverableStats.penalties)
        : null;
    if (parsedRecoverablePenalties?.status === "validation_error") {
        return parsedRecoverablePenalties;
    }
    const parsedManualEquipment = hasEditorManualEquipmentValues(values)
        ? parseEditorManualEquipmentItems(values, nextDefinition, campaignItemPageLookup)
        : null;
    if (parsedManualEquipment?.status === "validation_error") {
        return parsedManualEquipment;
    }
    const parsedCustomFeatures = hasEditorCustomFeatureValues(values)
        ? parseEditorCustomFeatures(values, nextDefinition, campaignFeaturePageLookup)
        : null;
    if (parsedCustomFeatures?.status === "validation_error") {
        return parsedCustomFeatures;
    }
    for (const [fieldName, value] of Object.entries(values)) {
        if (fieldName === "biography_markdown" || fieldName === "personality_markdown") {
            profile[fieldName] = value;
        }
        else if (fieldName === "additional_notes_markdown" || fieldName === "allies_and_organizations_markdown") {
            referenceNotes[fieldName] = value;
        }
        else if (ADVANCED_EDITOR_STATE_NOTE_FIELD_NAMES.has(fieldName)) {
            stateNoteValues[fieldName] = value;
        }
        else {
            const proficiencyField = ADVANCED_EDITOR_PROFICIENCY_FIELDS.find((field) => field.name === fieldName);
            if (proficiencyField) {
                proficiencies[proficiencyField.key] = parseEditorMultilineValues(value);
            }
        }
    }
    nextDefinition.profile = profile;
    nextDefinition.reference_notes = referenceNotes;
    nextDefinition.proficiencies = proficiencies;
    if (parsedRecoverablePenalties?.status === "ok" || parsedStatAdjustments?.status === "ok") {
        const baseStats = parsedRecoverablePenalties?.status === "ok"
            ? applyEditorRecoverableStatPenalties(strippedRecoverableStats.stats, parsedRecoverablePenalties.penalties)
            : asRecord(nextDefinition.stats);
        nextDefinition.stats = applyEditorManualStatAdjustments(stripEditorManualStatAdjustments(baseStats), parsedStatAdjustments?.status === "ok"
            ? parsedStatAdjustments.adjustments
            : normalizeEditorStatAdjustments(asRecord(nextDefinition.stats).manual_adjustments));
    }
    if (parsedManualEquipment?.status === "ok") {
        const baseEquipment = asArray(nextDefinition.equipment_catalog)
            .map((item) => asRecord(item))
            .filter((item) => stringifyEditorValue(item.source_kind).trim() !== ADVANCED_EDITOR_MANUAL_EQUIPMENT_SOURCE_KIND);
        nextDefinition.equipment_catalog = [...baseEquipment, ...parsedManualEquipment.items];
        manualEquipmentReconcile = {
            enabled: true,
            removedItemIds: parsedManualEquipment.removedItemIds,
            customFeatureResourceReconcile: manualEquipmentReconcile.customFeatureResourceReconcile,
        };
    }
    if (parsedCustomFeatures?.status === "ok") {
        const existingManualTrackerIds = new Set(editorCustomFeatureEntries(nextDefinition)
            .map((feature) => stringifyEditorValue(feature.tracker_ref || manualFeatureTrackerId(stringifyEditorValue(feature.id))).trim())
            .filter(Boolean));
        const baseFeatures = asArray(nextDefinition.features)
            .map((feature) => asRecord(feature))
            .filter((feature) => stringifyEditorValue(feature.category).trim() !== ADVANCED_EDITOR_CUSTOM_FEATURE_CATEGORY);
        nextDefinition.features = [...baseFeatures, ...parsedCustomFeatures.features];
        const baseResourceTemplates = asArray(nextDefinition.resource_templates)
            .map((template) => asRecord(template))
            .filter((template) => !existingManualTrackerIds.has(stringifyEditorValue(template.id).trim()));
        nextDefinition.resource_templates = [...baseResourceTemplates, ...parsedCustomFeatures.resourceTemplates];
        manualEquipmentReconcile.customFeatureResourceReconcile = {
            enabled: true,
            removedResourceIds: parsedCustomFeatures.removedResourceIds,
        };
    }
    return {
        status: "ok",
        definition: nextDefinition,
        stateNoteValues,
        manualEquipmentReconcile,
        values,
    };
}
function definitionSourceType(definition) {
    return stringifyEditorValue(asRecord(definition.source).source_type).trim();
}
function definitionCurrentLevel(definition) {
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
function buildCharacterAdvancementLinks({ campaign, characterSlug, definition, readinessStatus, kind, }) {
    const links = {
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
function buildLevelUpUnsupportedReadiness(definition, message) {
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
export function buildCharacterAdvancementShellPayload({ campaign, characterSlug, definition, kind, }) {
    const campaignLane = nativeCharacterCreateLane(campaign.system);
    const characterLane = nativeCharacterCreateLane(definition.system);
    const dndSupported = campaignLane === "dnd5e" && characterLane === "dnd5e";
    if (!dndSupported) {
        const unsupportedMessage = campaignLane !== "dnd5e"
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
function asRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value)
        ? value
        : {};
}
function asArray(value) {
    return Array.isArray(value) ? value : [];
}
function deepCloneRecord(value) {
    return JSON.parse(JSON.stringify(asRecord(value)));
}
function parseJsonRecord(rawValue) {
    try {
        return asRecord(JSON.parse(rawValue || "{}"));
    }
    catch {
        return {};
    }
}
function createContextInteger(value, fallback = 0) {
    const parsed = Number.parseInt(String(value ?? "").trim(), 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}
function sourceSeeds(campaignConfig) {
    const seeds = new Map();
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
function campaignCustomSourceId(campaignSlug) {
    const normalized = String(campaignSlug || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .replace(/\//g, "-")
        .toUpperCase();
    return `CUSTOM-${normalized || "CAMPAIGN"}`;
}
function loadEnabledSourceIds(database, campaign, campaignConfig) {
    const librarySlug = campaign.systems_library_slug || "";
    if (!librarySlug) {
        return [];
    }
    const seeds = sourceSeeds(campaignConfig);
    const rows = database
        .prepare(`
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
      `)
        .all(campaign.slug, librarySlug);
    return rows
        .filter((row) => {
        const configured = row.configured_enabled !== null || Boolean(row.configured_visibility);
        return configured ? Boolean(row.configured_enabled) : Boolean(seeds.get(row.source_id)?.enabled);
    })
        .map((row) => row.source_id);
}
function loadEnabledSystemsEntryRows(database, campaign, campaignConfig, entryType) {
    const enabledSourceIds = loadEnabledSourceIds(database, campaign, campaignConfig);
    const librarySlug = campaign.systems_library_slug || "";
    if (!librarySlug || enabledSourceIds.length === 0) {
        return [];
    }
    const placeholders = enabledSourceIds.map(() => "?").join(", ");
    return database
        .prepare(`
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
      `)
        .all(campaign.slug, librarySlug, ...enabledSourceIds, entryType.toLowerCase());
}
function loadEnabledMartialArtRows(database, campaign, campaignConfig) {
    return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "martial_art");
}
function normalizeRankKey(value) {
    return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}
function normalizeMartialArtOptionSlug(value) {
    return String(value ?? "").trim().toLowerCase();
}
function normalizeGenericTechniqueKey(value) {
    return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}
function firstPresent(...values) {
    for (const value of values) {
        if (value !== null && value !== undefined && value !== "") {
            return value;
        }
    }
    return "";
}
function normalizeLookup(value) {
    return String(value ?? "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
}
function normalizeDndSourceId(value) {
    return String(value ?? "").trim().toUpperCase();
}
function dndBaseClassKey(sourceId, className) {
    const normalizedSourceId = normalizeDndSourceId(sourceId);
    const normalizedClassName = normalizeLookup(className);
    return normalizedSourceId && normalizedClassName ? `${normalizedSourceId}|${normalizedClassName}` : "";
}
function dndSupportsBaseClass(sourceId, className) {
    const normalizedSourceId = normalizeDndSourceId(sourceId);
    if (normalizedSourceId === DND_PHB_SOURCE_ID) {
        return true;
    }
    return DND_SUPPORTED_NON_PHB_BASE_CLASSES.has(dndBaseClassKey(normalizedSourceId, className));
}
function dndSupportsSubordinateSource(sourceId) {
    const normalizedSourceId = normalizeDndSourceId(sourceId);
    return normalizedSourceId === DND_PHB_SOURCE_ID || DND_SUPPORTED_SUBORDINATE_SOURCES.has(normalizedSourceId);
}
function dndSupportsNativeClassEntry(row) {
    const metadata = parseJsonRecord(row.metadata_json);
    if (!String(row.title || "").trim() || !metadata.hit_die) {
        return false;
    }
    return dndSupportsBaseClass(row.source_id, row.title);
}
function dndSupportsNativeSubclassEntry(row, selectedClass) {
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
function dndEntryOption(row) {
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
function sanitizeDndEntrySelectionValue(rawValue, rows) {
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
function selectedDndEntry(rows, value) {
    const selectedValue = String(value ?? "").trim();
    if (!selectedValue) {
        return null;
    }
    return (rows.find((row) => {
        const option = dndEntryOption(row);
        return selectedValue === option.value || selectedValue === option.slug || selectedValue === option.page_ref;
    }) || null);
}
function dndClassRequiresSubclassAtLevelOne(selectedClass) {
    if (!selectedClass) {
        return false;
    }
    const metadata = parseJsonRecord(selectedClass.metadata_json);
    const subclassLevel = Number(firstPresent(metadata.subclass_level, metadata.subclassLevel, metadata.subclass_choice_level));
    return Number.isFinite(subclassLevel) && subclassLevel === 1;
}
function dndAbilityScorePreview(values) {
    return Object.fromEntries(DND_ABILITY_KEYS.map((key) => [key, createContextInteger(values[key], 10)]));
}
function dndCreatePreview({ selectedClass, selectedSpecies, selectedBackground, values, }) {
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
function abilityModifier(score) {
    return Math.floor((score - 10) / 2);
}
function dndAbilityChoiceSection(values) {
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
export function buildDndCharacterCreateContext({ dbPath, campaign, campaignConfig, values, }) {
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
    }
    catch (error) {
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
    }
    finally {
        database.close();
    }
}
function assertDndPilotEntry(row, expectedTitle, expectedType, fieldLabel) {
    if (!row) {
        throw new Error(`${fieldLabel} is required for the DND-5E create pilot.`);
    }
    if (normalizeDndSourceId(row.source_id) !== DND_PHB_SOURCE_ID ||
        normalizeLookup(row.title) !== expectedTitle ||
        String(row.entry_type || "") !== expectedType) {
        throw new Error("DND-5E character creation submit currently supports only the PHB Fighter / Human / Soldier pilot lane.");
    }
    return row;
}
function dndSystemsRef(row) {
    const metadata = parseJsonRecord(row.metadata_json);
    const ref = {
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
function dndAbilityScores(values) {
    return Object.fromEntries(DND_ABILITY_KEYS.map((key) => {
        const score = Math.min(30, Math.max(1, createContextInteger(values[key], 10)));
        return [
            key,
            {
                score,
                modifier: abilityModifier(score),
                save_bonus: abilityModifier(score) + (key === "str" || key === "con" ? 2 : 0),
            },
        ];
    }));
}
function dndAbilityScoreValue(abilityScores, key) {
    return createContextInteger(asRecord(abilityScores[key]).score, 10);
}
function dndSkillBonus(abilityScores, abilityKey, proficient) {
    return abilityModifier(dndAbilityScoreValue(abilityScores, abilityKey)) + (proficient ? 2 : 0);
}
function dndPilotEquipmentCatalog() {
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
function dndPilotAttacks(abilityScores) {
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
export function buildDndCreateCharacter({ dbPath, campaign, campaignConfig, values, }) {
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
        const selectedClass = assertDndPilotEntry(selectedDndEntry(classRows, normalizedValues.class_slug), DND_PILOT_CLASS, "class", "Class");
        const selectedSpecies = assertDndPilotEntry(selectedDndEntry(speciesRows, normalizedValues.species_slug), DND_PILOT_SPECIES, "race", "Species");
        const selectedBackground = assertDndPilotEntry(selectedDndEntry(backgroundRows, normalizedValues.background_slug), DND_PILOT_BACKGROUND, "background", "Background");
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
        const definition = {
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
    }
    catch (error) {
        if (error instanceof Error && error.message.includes("no such table")) {
            throw new Error("DND-5E character creation requires Systems source data.");
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function martialArtRankRecords(metadata, body) {
    const martialArtBody = asRecord(body.xianxia_martial_art);
    const rawRecords = metadata.xianxia_martial_art_rank_records ??
        metadata.martial_art_rank_records ??
        martialArtBody.xianxia_martial_art_rank_records ??
        martialArtBody.rank_records;
    return asArray(rawRecords)
        .map(asRecord)
        .filter((record) => record.rank_available_in_seed !== false)
        .map((record) => ({ ...record, rank_key: normalizeRankKey(record.rank_key) }))
        .filter((record) => Boolean(XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[String(record.rank_key || "")]));
}
function truthy(value) {
    if (typeof value === "boolean") {
        return value;
    }
    if (typeof value === "number") {
        return value !== 0;
    }
    const normalized = String(value ?? "").trim().toLowerCase();
    return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}
function buildXianxiaMartialArtOption(row, customSourceId) {
    const metadata = parseJsonRecord(row.metadata_json);
    const body = parseJsonRecord(row.body_json);
    const martialArtBody = asRecord(body.xianxia_martial_art);
    const rankRecords = martialArtRankRecords(metadata, body);
    let rankRefs = Object.fromEntries(rankRecords
        .map((record) => [String(record.rank_key || ""), String(record.rank_ref || "").trim()])
        .filter(([rankKey, rankRef]) => rankKey && rankRef));
    let availableRankKeys = XIANXIA_MARTIAL_ART_IMPORT_RANKS.map((rank) => rank.key).filter((rankKey) => rankKey in rankRefs);
    const customMartialArt = truthy(metadata.xianxia_custom_martial_art) ||
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
        martial_art_style: String(firstPresent(metadata.xianxia_martial_art_style, metadata.martial_art_style, martialArtBody.style, martialArtBody.martial_art_style)).trim(),
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
function xianxiaGenericTechniqueSortOrder(metadata, techniqueBody) {
    const parsed = Number(firstPresent(metadata.generic_technique_catalog_order, metadata.catalog_order, techniqueBody.catalog_order));
    return Number.isFinite(parsed) ? Math.trunc(parsed) : 10000;
}
function buildXianxiaGenericTechniqueRecord(row) {
    if (String(row.entry_type || "").trim().toLowerCase() !== "generic_technique") {
        return null;
    }
    const metadata = parseJsonRecord(row.metadata_json);
    const body = parseJsonRecord(row.body_json);
    const techniqueBody = asRecord(body.xianxia_generic_technique);
    const genericTechniqueKey = normalizeGenericTechniqueKey(firstPresent(metadata.generic_technique_key, metadata.xianxia_generic_technique_key, techniqueBody.key));
    const entryKey = String(row.entry_key || "").trim();
    if (!entryKey || !genericTechniqueKey) {
        return null;
    }
    const insightCost = Math.max(0, Number.parseInt(String(firstPresent(metadata.insight_cost, techniqueBody.insight_cost) || "0"), 10) || 0);
    const name = String(row.title || "").trim() || "Generic Technique";
    const slug = String(row.slug || "").trim();
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
        support_state: String(firstPresent(metadata.support_state, metadata.xianxia_support_state, techniqueBody.support_state, techniqueBody.xianxia_support_state) || "").trim(),
        prerequisites: parseTags(firstPresent(metadata.prerequisites, techniqueBody.prerequisites)),
        resource_costs: parseTags(firstPresent(metadata.resource_costs, techniqueBody.resource_costs)),
        range_tags: parseTags(firstPresent(metadata.range_tags, techniqueBody.range_tags)),
        effort_tags: parseTags(firstPresent(metadata.effort_tags, techniqueBody.effort_tags)),
        reset_cadence: String(firstPresent(metadata.reset_cadence, techniqueBody.reset_cadence) || "").trim(),
        learnable_without_master: truthy(firstPresent(metadata.learnable_without_master, techniqueBody.learnable_without_master)),
        requires_master: truthy(firstPresent(metadata.requires_master, techniqueBody.requires_master)),
        sort_order: xianxiaGenericTechniqueSortOrder(metadata, techniqueBody),
    };
}
function buildXianxiaGenericTechniqueOption(row, selectedEntryKeys) {
    const option = buildXianxiaGenericTechniqueRecord(row);
    if (!option || XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS.has(option.generic_technique_key) || option.insight_cost <= 0) {
        return null;
    }
    const selected = [option.entry_key, option.systems_ref.slug, option.generic_technique_key, option.name]
        .map((value) => String(value || "").trim().toLowerCase())
        .filter(Boolean)
        .some((value) => selectedEntryKeys.has(value));
    return {
        ...option,
        selected,
    };
}
function xianxiaKnownGenericTechniqueMarkers(definition) {
    const markers = {
        entryKeys: new Set(),
        slugs: new Set(),
        keys: new Set(),
        names: new Set(),
    };
    for (const rawTechnique of asArray(asRecord(definition.xianxia).generic_techniques)) {
        const technique = asRecord(rawTechnique);
        const systemsRef = asRecord(technique.systems_ref);
        const entryKey = String(firstPresent(systemsRef.entry_key, technique.entry_key) || "").trim().toLowerCase();
        if (entryKey) {
            markers.entryKeys.add(entryKey);
        }
        const slug = String(firstPresent(systemsRef.slug, technique.slug) || "").trim().toLowerCase();
        if (slug) {
            markers.slugs.add(slug);
        }
        const genericTechniqueKey = normalizeGenericTechniqueKey(firstPresent(technique.generic_technique_key, technique.technique_key, systemsRef.slug));
        if (genericTechniqueKey) {
            markers.keys.add(genericTechniqueKey);
        }
        const name = String(firstPresent(technique.name, technique.title, systemsRef.title) || "").trim().toLowerCase();
        if (name) {
            markers.names.add(name);
        }
    }
    return markers;
}
function xianxiaGenericTechniqueRecordIsKnown(option, knownMarkers) {
    const entryKey = String(firstPresent(option.systems_ref.entry_key, option.entry_key) || "").trim().toLowerCase();
    if (entryKey && knownMarkers.entryKeys.has(entryKey)) {
        return true;
    }
    const slug = String(option.systems_ref.slug || "").trim().toLowerCase();
    if (slug && knownMarkers.slugs.has(slug)) {
        return true;
    }
    const genericTechniqueKey = normalizeGenericTechniqueKey(firstPresent(option.generic_technique_key, slug));
    if (genericTechniqueKey && knownMarkers.keys.has(genericTechniqueKey)) {
        return true;
    }
    const name = String(option.name || "").trim().toLowerCase();
    return Boolean(name && knownMarkers.names.has(name));
}
export function xianxiaKnownGenericTechniqueOptionKeys(definition) {
    const markers = xianxiaKnownGenericTechniqueMarkers(definition);
    return [
        ...markers.entryKeys,
        ...markers.slugs,
        ...markers.keys,
        ...markers.names,
    ];
}
export function listXianxiaCultivationGenericTechniqueRows(dbPath, campaign, campaignConfig) {
    if (!campaign.systems_library_slug || !existsSync(dbPath)) {
        return [];
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "generic_technique").filter((row) => row.is_enabled_override !== 0);
    }
    catch (error) {
        if (error instanceof Error && error.message.includes("no such table")) {
            return [];
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function listXianxiaManualImportMartialArtOptions(dbPath, campaign, campaignConfig) {
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
    }
    catch (error) {
        if (error instanceof Error && error.message.includes("no such table")) {
            return [];
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function listXianxiaCultivationMartialArtRows(dbPath, campaign, campaignConfig) {
    if (!campaign.systems_library_slug || !existsSync(dbPath)) {
        return [];
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        return loadEnabledMartialArtRows(database, campaign, campaignConfig).filter((row) => row.is_enabled_override !== 0);
    }
    catch (error) {
        if (error instanceof Error && error.message.includes("no such table")) {
            return [];
        }
        throw error;
    }
    finally {
        database.close();
    }
}
export function listXianxiaCreateGenericTechniqueOptions(dbPath, campaign, campaignConfig, selectedEntryKeys = []) {
    if (!campaign.systems_library_slug || !existsSync(dbPath)) {
        return [];
    }
    const selected = new Set(selectedEntryKeys.map((entryKey) => String(entryKey || "").trim().toLowerCase()).filter(Boolean));
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        return loadEnabledSystemsEntryRows(database, campaign, campaignConfig, "generic_technique")
            .filter((row) => row.is_enabled_override !== 0)
            .map((row) => buildXianxiaGenericTechniqueOption(row, selected))
            .filter((option) => option !== null)
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
    }
    catch (error) {
        if (error instanceof Error && error.message.includes("no such table")) {
            return [];
        }
        throw error;
    }
    finally {
        database.close();
    }
}
function normalizeCharacterAuthoringValue(value) {
    if (Array.isArray(value)) {
        return value.map((item) => String(item ?? "").trim()).filter(Boolean).join(",");
    }
    return value === null || value === undefined ? "" : String(value);
}
function normalizeCharacterAuthoringValues(values) {
    return Object.fromEntries(Object.entries(values).map(([key, value]) => [String(key), normalizeCharacterAuthoringValue(value)]));
}
function isPresent(value) {
    return String(value ?? "").trim().length > 0;
}
function coerceInt(value, fieldName) {
    const candidate = String(value ?? "").trim();
    if (!candidate) {
        return 0;
    }
    if (!/^[+-]?\d+$/.test(candidate)) {
        throw new Error(`Invalid value for ${fieldName}.`);
    }
    return Number.parseInt(candidate, 10);
}
function parseStrictInt(value, fieldLabel) {
    const candidate = cleanScalar(value);
    if (!/^[+-]?\d+$/.test(candidate)) {
        throw new Error(`${fieldLabel} must be a whole number.`);
    }
    return Number.parseInt(candidate, 10);
}
function coerceLooseInt(value, defaultValue = 0) {
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
function nonNegativeLooseInt(value, defaultValue = 0) {
    return Math.max(0, coerceLooseInt(value, defaultValue));
}
function normalizeRealm(value) {
    const canonical = String(value || "")
        .trim()
        .toLowerCase();
    if (canonical === "mortal" || canonical === "immortal" || canonical === "divine") {
        return canonical[0].toUpperCase() + canonical.slice(1);
    }
    return "Mortal";
}
function normalizeHonor(value) {
    const canonical = String(value || "").trim().toLowerCase();
    for (const honor of ["Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"]) {
        if (honor.toLowerCase() === canonical) {
            return honor;
        }
    }
    return "Honorable";
}
function collectIndexedRows(values, prefix) {
    const rowNumbers = new Set();
    for (const key of Object.keys(values)) {
        const match = key.match(new RegExp(`^${prefix}_(\\d+)_(.+)$`));
        if (match) {
            rowNumbers.add(Number(match[1]));
        }
    }
    return Array.from(rowNumbers)
        .sort((left, right) => left - right)
        .map((rowIndex) => {
        const normalizedRow = {};
        const sourceFieldPrefix = `${prefix}_${rowIndex}_`;
        for (const [key, value] of Object.entries(values)) {
            if (key.startsWith(sourceFieldPrefix)) {
                normalizedRow[key.slice(sourceFieldPrefix.length)] = value;
            }
        }
        return normalizedRow;
    });
}
function extractValues(values, keys) {
    for (const key of keys) {
        const value = values[key];
        if (isPresent(value)) {
            return value;
        }
    }
    return "";
}
function normalizeCharacterName(value) {
    return String(value || "").trim();
}
function normalizeCreateName(value) {
    return cleanScalar(value).split(/\s+/).filter(Boolean).join(" ");
}
function slugifyText(value) {
    if (!value.trim()) {
        return "";
    }
    return value
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/gi, "-")
        .replace(/(^-|-$)+/g, "");
}
function normalizeCharacterSlug(value, fallbackSource) {
    return slugifyText(value) || slugifyText(fallbackSource);
}
function countTextRows(value) {
    return String(value || "")
        .split(/\r?\n/)
        .filter((row) => row.trim().length > 0).length;
}
function splitTextLines(value) {
    return String(value ?? "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
}
function splitPipeRow(value) {
    return value
        .split("|")
        .map((part) => part.trim())
        .filter((part) => part.length > 0);
}
function lookupKey(value) {
    return String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function humanizeSlug(value) {
    return value
        .replace(/[-_]+/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .replace(/\b\w/g, (match) => match.toUpperCase());
}
function parseTags(value) {
    if (Array.isArray(value)) {
        return value.map((item) => String(item ?? "").trim()).filter(Boolean);
    }
    return String(value ?? "")
        .split(/[,|]/)
        .map((item) => item.trim())
        .filter(Boolean);
}
function cleanScalar(value) {
    if (Array.isArray(value)) {
        return cleanScalar(value[0]);
    }
    return value === null || value === undefined ? "" : String(value).trim();
}
function scalarList(value) {
    if (value === null || value === undefined || value === "") {
        return [];
    }
    if (Array.isArray(value)) {
        return value;
    }
    if (typeof value === "object") {
        return Object.values(value);
    }
    return [value];
}
function formatLabelList(values) {
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
function normalizeToken(value) {
    return String(value ?? "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");
}
function parseBoolean(value) {
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
function appendNotesSection(baseNotes, title, lines) {
    const body = lines.map((line) => `- ${line}`).join("\n");
    return [baseNotes.trim(), `## ${title}\n\n${body}`].filter(Boolean).join("\n\n");
}
function buildXianxiaManualImportMartialArtRows(values) {
    const rowNumbers = new Set();
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
export function buildXianxiaManualImportContext({ dbPath, campaign, campaignConfig, values, }) {
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
export function buildXianxiaManualImportPayload(values) {
    const ignoredInputs = new Set(["active_stance", "active_aura"]);
    const payload = {};
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
function xianxiaIntegerMap(values, keys, prefix) {
    return Object.fromEntries(keys.map((key) => [key, coerceLooseInt(values[`${prefix}${key}`], 0)]));
}
function parseSkillText(value) {
    return splitTextLines(value).map((line) => {
        const parts = splitPipeRow(line);
        if (parts.length <= 1) {
            return parts[0] || "";
        }
        return { name: parts[0], notes: parts[1] };
    });
}
function collectTrainedSkills(values) {
    const rows = [
        ...parseSkillText(values.trained_skills_text),
        ...parseSkillText(values.skills_text),
        ...collectIndexedRows(values, "trained_skill"),
    ];
    const seen = new Set();
    const trainedSkills = [];
    const skillNotes = [];
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
function parseInventoryText(value) {
    return splitTextLines(value).map((line) => {
        const parts = splitPipeRow(line);
        const row = { name: parts[0] || "" };
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
function normalizeInventoryItemType(rawType, defaultValue = XIANXIA_ITEM_TYPE_DEFAULT) {
    const normalized = normalizeToken(rawType);
    return normalized ? (XIANXIA_ITEM_TYPE_ALIASES[normalized] ?? defaultValue) : defaultValue;
}
function normalizeInventoryItemNature(rawNature) {
    return XIANXIA_ITEM_NATURE_ALIASES[normalizeToken(rawNature)] ?? "Mundane";
}
function normalizeInventoryLegacyTags(tags, itemType) {
    const explicitType = normalizeInventoryItemType(itemType, "");
    const normalizedTags = [];
    const legacyTags = [];
    const inferredTypes = new Set();
    const nonMiscInferredTypes = new Set();
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
        }
        else {
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
function normalizeInventoryRows(values) {
    const rows = [
        ...parseInventoryText(values.inventory_text),
        ...collectIndexedRows(values, "manual_item"),
        ...collectIndexedRows(values, "inventory_item"),
    ];
    return rows
        .map((row) => {
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
        const normalized = {
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
        .filter((row) => Boolean(row));
}
function martialArtOptionLookup(options) {
    const lookup = new Map();
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
function matchMartialArtOption(row, lookup) {
    for (const key of [row.systems_ref_slug, row.martial_art_slug, row.slug, row.entry_key, row.name]) {
        const normalized = lookupKey(key);
        if (normalized && lookup.has(normalized)) {
            return lookup.get(normalized) || null;
        }
    }
    return null;
}
function martialArtSystemsRef(option) {
    const ref = {};
    for (const key of ["library_slug", "source_id", "entry_key", "slug", "title", "entry_type"]) {
        const value = String(option[key] ?? "").trim();
        if (value) {
            ref[key] = value;
        }
    }
    return ref;
}
function learnedRankRefsForOption(option, rankKey) {
    const normalizedRank = normalizeRankKey(rankKey);
    const rankIndex = XIANXIA_MARTIAL_ART_RANK_ORDER.indexOf(normalizedRank);
    if (rankIndex < 0) {
        return [];
    }
    const rankRefs = asRecord(option.rank_refs);
    const slug = String(option.slug || "").trim();
    return XIANXIA_MARTIAL_ART_RANK_ORDER.slice(0, rankIndex + 1)
        .map((rank) => String(rankRefs[rank] || (slug ? `xianxia:${slug}:${rank}` : "")).trim())
        .filter(Boolean);
}
function collectMartialArts(values, options) {
    const lookup = martialArtOptionLookup(options);
    return collectIndexedRows(values, "martial_art")
        .map((row) => {
        const selectedOption = matchMartialArtOption(row, lookup);
        const name = String(row.name || row.label || row.title || selectedOption?.title || "").trim();
        if (!name) {
            return null;
        }
        const rankKey = normalizeRankKey(row.current_rank_key || row.current_rank || row.rank || row.rank_key || "");
        const payload = {
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
        .filter((row) => Boolean(row));
}
function nestedRecordValue(values, key) {
    return asRecord(values[key]);
}
function validateCreationIntMap({ values, nestedKey, prefix, keys, labels, points, max, groupLabel, unsupportedLabel, }) {
    const errors = [];
    const missingLabels = [];
    const scores = {};
    const nested = nestedRecordValue(values, nestedKey);
    const unknownKeys = new Set();
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
        let score;
        try {
            score = parseStrictInt(cleaned, label);
        }
        catch (error) {
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
function validateXianxiaCreateAttributes(values) {
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
function validateXianxiaCreateEfforts(values) {
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
function validateXianxiaCreateEnergies(values) {
    const errors = [];
    const missingLabels = [];
    const scores = {};
    const nestedEnergies = nestedRecordValue(values, "energies");
    const nestedEnergyMaxima = nestedRecordValue(values, "energy_maxima");
    const unknownKeys = new Set();
    for (const key of Object.keys(values)) {
        if (key.startsWith("energy_") && key !== "energy_maxima") {
            const unprefixed = key.slice("energy_".length);
            if (!XIANXIA_ENERGY_KEYS.includes(unprefixed)) {
                unknownKeys.add(unprefixed);
            }
        }
    }
    for (const key of [...Object.keys(nestedEnergies), ...Object.keys(nestedEnergyMaxima)]) {
        if (!XIANXIA_ENERGY_KEYS.includes(key)) {
            unknownKeys.add(key);
        }
    }
    const unknown = [...unknownKeys].sort();
    if (unknown.length > 0) {
        errors.push(`Unsupported Xianxia energies: ${unknown.join(", ")}.`);
    }
    for (const key of XIANXIA_ENERGY_KEYS) {
        const label = key[0].toUpperCase() + key.slice(1);
        let rawValue;
        if (Object.hasOwn(values, `energy_${key}`)) {
            rawValue = values[`energy_${key}`];
        }
        else if (Object.hasOwn(nestedEnergyMaxima, key)) {
            rawValue = nestedEnergyMaxima[key];
        }
        else if (Object.hasOwn(nestedEnergies, key)) {
            const nestedEnergy = asRecord(nestedEnergies[key]);
            rawValue = Object.keys(nestedEnergy).length > 0 ? nestedEnergy.max : nestedEnergies[key];
        }
        const cleaned = cleanScalar(rawValue);
        if (cleaned === "") {
            missingLabels.push(label);
            continue;
        }
        let score;
        try {
            score = parseStrictInt(cleaned, label);
        }
        catch (error) {
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
            errors.push(`Xianxia Energies must spend exactly ${XIANXIA_ENERGY_CREATION_POINTS} creation points across Jing, Qi, and Shen; submitted total is ${total}.`);
        }
    }
    if (errors.length > 0) {
        throw new Error(errors.join(" "));
    }
    return Object.fromEntries(XIANXIA_ENERGY_KEYS.map((key) => [key, scores[key] ?? 0]));
}
function validateXianxiaCreateManualArmorBonus(values) {
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
function validateXianxiaCreateDaoCurrent(values) {
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
function extractXianxiaCreateTrainedSkillValues(values) {
    const indexed = Object.entries(values)
        .map(([key, value]) => {
        const match = key.match(/^trained_skill_(\d+)$/);
        return match ? [Number(match[1]), value] : null;
    })
        .filter((entry) => entry !== null && entry[0] > 0)
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
function normalizeTrainedSkillName(value) {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        const record = value;
        value = record.name ?? record.label;
    }
    return cleanScalar(value).split(/\s+/).filter(Boolean).join(" ");
}
function validateXianxiaCreateTrainedSkills(values) {
    const trainedSkills = extractXianxiaCreateTrainedSkillValues(values).map(normalizeTrainedSkillName).filter(Boolean);
    if (trainedSkills.length !== XIANXIA_TRAINED_SKILL_COUNT) {
        throw new Error(`Xianxia character creation requires exactly ${XIANXIA_TRAINED_SKILL_COUNT} trained skills; submitted ${trainedSkills.length}.`);
    }
    const seen = new Set();
    const duplicates = [];
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
function normalizeCreateMartialArtRankKey(value) {
    return cleanScalar(value).toLowerCase().replace(/[\s-]+/g, "_");
}
function coerceCreateMartialArtValue(value) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        return { slug: value, rank_key: "" };
    }
    const record = value;
    const systemsRef = asRecord(record.systems_ref);
    return {
        slug: record.slug ?? record.entry_slug ?? systemsRef.slug ?? systemsRef.entry_slug ?? record.systems_ref,
        rank_key: record.rank_key ?? record.current_rank_key ?? record.starting_rank_key ?? record.rank ?? record.current_rank,
    };
}
function extractXianxiaCreateMartialArtValues(values) {
    const indexed = [];
    for (let index = 1; index <= 3; index += 1) {
        const slugKey = `martial_art_${index}_slug`;
        const rankKey = `martial_art_${index}_rank`;
        const alternateSlugKey = `starting_martial_art_${index}_slug`;
        const alternateRankKey = `starting_martial_art_${index}_rank`;
        if (Object.hasOwn(values, slugKey) ||
            Object.hasOwn(values, rankKey) ||
            Object.hasOwn(values, alternateSlugKey) ||
            Object.hasOwn(values, alternateRankKey)) {
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
function normalizeXianxiaCreateMartialArtValues(values) {
    const normalized = extractXianxiaCreateMartialArtValues(values).map((record) => ({
        slug: normalizeMartialArtOptionSlug(record.slug),
        rank_key: normalizeCreateMartialArtRankKey(record.rank_key),
    }));
    while (normalized.length < 3) {
        normalized.push({ slug: "", rank_key: "" });
    }
    return normalized.slice(0, 3);
}
function createMartialArtOptionMap(options) {
    const lookup = new Map();
    for (const option of options) {
        const slug = normalizeMartialArtOptionSlug(option.slug);
        if (slug) {
            lookup.set(slug, option);
        }
    }
    return lookup;
}
function buildXianxiaStartingMartialArtRecord(option, rankKey) {
    const learnedRanks = rankKey === "novice" ? ["initiate", "novice"] : ["initiate"];
    const record = {
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
function validateXianxiaCreateMartialArts(values, options) {
    const optionsBySlug = createMartialArtOptionMap(options);
    const selectedValues = normalizeXianxiaCreateMartialArtValues(values).filter((value) => value.slug || value.rank_key);
    if (selectedValues.length === 0) {
        throw new Error("Xianxia character creation requires a starting Martial Arts package: one Novice plus one Initiate, or three Initiates.");
    }
    if (optionsBySlug.size === 0) {
        throw new Error("No enabled Xianxia Martial Art Systems entries are available for character creation.");
    }
    const errors = [];
    const records = [];
    const selectedOptions = [];
    const seenSlugs = new Set();
    const duplicateTitles = [];
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
            errors.push(`${option.title} does not have ${XIANXIA_MARTIAL_ART_IMPORT_RANK_LABELS[value.rank_key]} rank available in Systems metadata.`);
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
function normalizeGenericTechniqueEntryKeys(values) {
    let rawValues = values.gm_granted_generic_technique_entry_keys;
    if (rawValues === null || rawValues === undefined) {
        rawValues = values.gm_granted_generic_techniques;
    }
    return scalarList(rawValues)
        .map((rawValue) => {
        if (typeof rawValue === "object" && rawValue !== null && !Array.isArray(rawValue)) {
            const record = rawValue;
            const systemsRef = asRecord(record.systems_ref);
            rawValue = record.entry_key ?? systemsRef.entry_key;
        }
        return cleanScalar(rawValue);
    })
        .filter(Boolean);
}
function genericTechniqueOptionMap(options) {
    const lookup = new Map();
    for (const option of options) {
        const entryKey = String(option.entry_key || "").trim().toLowerCase();
        if (entryKey) {
            lookup.set(entryKey, option);
        }
    }
    return lookup;
}
function buildXianxiaGmGrantedGenericTechniqueRecord(option) {
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
function validateXianxiaCreateGmGrantedGenericTechniques(values, options) {
    const requestedEntryKeys = normalizeGenericTechniqueEntryKeys(values);
    if (requestedEntryKeys.length === 0) {
        return [];
    }
    const optionsByEntryKey = genericTechniqueOptionMap(options);
    if (optionsByEntryKey.size === 0) {
        throw new Error("No enabled Xianxia Generic Technique Systems entries are available for GM grants.");
    }
    const records = [];
    const errors = [];
    const seen = new Set();
    const duplicateTitles = [];
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
const MARTIAL_ART_STYLE_EQUIPMENT_HINTS = [
    [["jian sword"], "weapon", "Jian"],
    [["bo and spear", "staff and spear"], "weapon", "Bo staff or spear"],
    [["saber sword", "sabre sword"], "weapon", "Saber"],
    [["dagger"], "weapon", "Daggers"],
    [["sword martial art"], "weapon", "Sword"],
    [["instrument"], "tool", "Musical instrument"],
    [["puppet"], "tool", "Puppet"],
];
const TRAINED_SKILL_TOOL_HINTS = [
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
function equipmentSearchText(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9']+/g, " ").trim();
}
function containsEquipmentPhrase(value, phrase) {
    return ` ${equipmentSearchText(value)} `.includes(` ${equipmentSearchText(phrase)} `);
}
function appendEquipmentRecord(records, seen, name, reason) {
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
function inferXianxiaRequiredEquipment(martialArts, trainedSkills) {
    const weapons = [];
    const tools = [];
    const seenWeapons = new Set();
    const seenTools = new Set();
    for (const martialArt of martialArts) {
        const title = cleanScalar(martialArt.title || martialArt.name).split(/\s+/).filter(Boolean).join(" ");
        const style = cleanScalar(martialArt.martial_art_style || martialArt.style || martialArt.xianxia_martial_art_style)
            .split(/\s+/)
            .filter(Boolean)
            .join(" ");
        if (!title || !style) {
            continue;
        }
        const inferred = MARTIAL_ART_STYLE_EQUIPMENT_HINTS.find(([phrases]) => phrases.some((phrase) => containsEquipmentPhrase(style, phrase)));
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
        const inferred = TRAINED_SKILL_TOOL_HINTS.find(([phrases]) => phrases.some((phrase) => containsEquipmentPhrase(skillName, phrase)));
        if (inferred) {
            appendEquipmentRecord(tools, seenTools, inferred[1], `Required for ${skillName}`);
        }
    }
    return { necessary_weapons: weapons, necessary_tools: tools };
}
function buildXianxiaInitialState(definition, inventory, currency, playerNotesMarkdown, options = {}) {
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
        energies: Object.fromEntries(XIANXIA_ENERGY_KEYS.map((key) => [key, { current: nonNegativeLooseInt(asRecord(energies[key]).max, 0) }])),
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
function buildPreviewFromXianxiaImport(definition, initialState) {
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
function isWholeNumber(value) {
    return typeof value === "number" && Number.isInteger(value);
}
function requireExactInt(errors, path, value, expected) {
    if (!isWholeNumber(value)) {
        errors.push(`${path} must be a whole number.`);
        return;
    }
    if (value !== expected) {
        errors.push(`${path} must be ${expected}.`);
    }
}
function requireNonNegativeInt(errors, path, value) {
    if (!isWholeNumber(value)) {
        errors.push(`${path} must be a whole number.`);
        return;
    }
    if (value < 0) {
        errors.push(`${path} cannot be negative.`);
    }
}
function validateIntKeyMap(errors, path, value, keys) {
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
function validateEnergyMaxima(errors, value) {
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
    const unknown = Object.keys(energies).filter((key) => !XIANXIA_ENERGY_KEYS.includes(key)).sort();
    if (unknown.length > 0) {
        errors.push(`xianxia.energies uses unsupported keys: ${unknown.join(", ")}.`);
    }
}
function validateRecordList(errors, path, value) {
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
function validateXianxiaManualImportDefinition(definition) {
    const errors = [];
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
export function buildXianxiaCreateCharacter({ campaignSlug, values, martialArtOptions, genericTechniqueOptions, }) {
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
    const definition = {
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
    const initialState = buildXianxiaInitialState(definition, [], { coin: 0, supply: 0, spirit_stones: 0 }, "", { daoCurrent });
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
export function buildXianxiaManualImportCharacter({ campaignSlug, values, martialArtOptions, }) {
    const importPayload = buildXianxiaManualImportPayload(values);
    const normalizedValues = normalizeCharacterAuthoringValues(importPayload);
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
    const energies = Object.fromEntries(XIANXIA_ENERGY_KEYS.map((key) => [key, { max: coerceLooseInt(values[`energy_${key}_max`], 0) }]));
    const yinMax = coerceLooseInt(values.yin_max, 1);
    const yangMax = coerceLooseInt(values.yang_max, 1);
    const daoMax = coerceLooseInt(values.dao_max, 3);
    const hpMax = coerceLooseInt(values.hp_max, 10);
    const stanceMax = coerceLooseInt(values.stance_max, 10);
    const manualArmorBonus = coerceLooseInt(values.manual_armor_bonus, 0);
    const { trainedSkills, skillNotes } = collectTrainedSkills(values);
    const martialArts = collectMartialArts(values, martialArtOptions);
    const inventory = normalizeInventoryRows(values);
    const currency = Object.fromEntries(XIANXIA_CURRENCY_KEYS.map((key) => [key, nonNegativeLooseInt(values[key], 0)]));
    const playerNotesMarkdown = String(values.player_notes_markdown || "").trim();
    const additionalNotes = skillNotes.length > 0
        ? appendNotesSection(String(values.additional_notes_markdown || ""), "Imported skill notes", skillNotes)
        : String(values.additional_notes_markdown || "").trim();
    const definition = {
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
export function buildXianxiaManualImportPreview(values) {
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
    const trained_skill_count = countTextRows(normalizedValues.trained_skills_text || "") +
        trainedSkills.filter((row) => Object.values(row).some(isPresent)).length;
    const martial_art_count = martialArts.filter((row) => Object.values(row).some(isPresent)).length;
    const inventory_count = countTextRows(normalizedValues.inventory_text || "") +
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
