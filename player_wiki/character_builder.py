from __future__ import annotations

from copy import deepcopy
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import g, has_request_context

from .auth_store import isoformat, utcnow
from .character_adjustments import apply_manual_stat_adjustments, apply_stat_adjustments, strip_manual_stat_adjustments
from .character_campaign_options import (
    build_campaign_page_character_option,
    collect_campaign_option_proficiency_grants,
    collect_campaign_option_spell_grants,
    collect_campaign_option_stat_adjustments,
)
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

CHARACTER_BUILDER_VERSION = "2026-04-08.05"
PHB_SOURCE_ID = "PHB"
DEFAULT_EXPERIENCE_MODEL = "Milestone"
DEFAULT_ABILITY_SCORE = 10
NATIVE_LEVEL_UP_READY = "ready"
NATIVE_LEVEL_UP_REPAIRABLE = "repairable"
NATIVE_LEVEL_UP_UNSUPPORTED = "unsupported"
IMPORTED_CHARACTER_SOURCE_TYPES = frozenset({"markdown_character_sheet", "pdf_character_sheet_annotations"})
CAMPAIGN_FEATURE_CHOICE_SLOTS = 2
CAMPAIGN_ITEM_CHOICE_SLOTS = 3
CAMPAIGN_MECHANICS_SECTION = "Mechanics"
CAMPAIGN_ITEMS_SECTION = "Items"
CAMPAIGN_SESSIONS_SECTION = "Sessions"
CAMPAIGN_PAGE_OPTION_PREFIX = "page:"
SYSTEMS_OPTION_PREFIX = "systems:"
CAMPAIGN_PAGE_SOURCE_ID = "Campaign"
CHOICE_SECTIONS_REGION_ID = "choice-sections"
ATTACK_NAME_SUFFIX_PATTERN = re.compile(r"\s*\(([^)]*)\)\s*$")
ATTACK_MODE_WEAPON_THROWN = "weapon:thrown"
ATTACK_MODE_WEAPON_TWO_HANDED = "weapon:two-handed"
ATTACK_MODE_WEAPON_OFF_HAND = "weapon:off-hand"
ATTACK_MODE_FEAT_CHARGER_PHB = "feat:phb-feat-charger"
ATTACK_MODE_FEAT_CHARGER_XPHB = "feat:xphb-feat-charger"
ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS = "feat:phb-feat-crossbow-expert:bonus"
ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER = "feat:phb-feat-great-weapon-master"
ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS = "feat:phb-feat-polearm-master:bonus"
ATTACK_MODE_FEAT_SHARPSHOOTER = "feat:phb-feat-sharpshooter"
ATTACK_MODE_EFFECT_PREFIX = "effect:attack-mode"
ATTACK_MODE_TARGET_ALL = "all"
ATTACK_MODE_TARGET_MELEE = "melee"
ATTACK_MODE_TARGET_RANGED = "ranged"
ATTACK_MODE_TARGET_FIREARM = "firearm"
ATTACK_MODE_EFFECT_TARGETS = frozenset(
    {
        ATTACK_MODE_TARGET_ALL,
        ATTACK_MODE_TARGET_MELEE,
        ATTACK_MODE_TARGET_RANGED,
        ATTACK_MODE_TARGET_FIREARM,
    }
)
ATTACK_MODE_COMPONENT_LABELS = {
    ATTACK_MODE_WEAPON_THROWN: "thrown",
    ATTACK_MODE_WEAPON_TWO_HANDED: "two-handed",
    ATTACK_MODE_WEAPON_OFF_HAND: "off-hand",
    ATTACK_MODE_FEAT_CHARGER_PHB: "charger",
    ATTACK_MODE_FEAT_CHARGER_XPHB: "charger",
    ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS: "crossbow expert",
    ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER: "great weapon master",
    ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS: "polearm master",
    ATTACK_MODE_FEAT_SHARPSHOOTER: "sharpshooter",
}
ATTACK_MODE_COMPONENT_PRIORITY = {
    ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS: 10,
    ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS: 20,
    ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER: 30,
    ATTACK_MODE_FEAT_SHARPSHOOTER: 40,
    ATTACK_MODE_FEAT_CHARGER_PHB: 50,
    ATTACK_MODE_FEAT_CHARGER_XPHB: 50,
    ATTACK_MODE_WEAPON_OFF_HAND: 60,
    ATTACK_MODE_WEAPON_TWO_HANDED: 70,
    ATTACK_MODE_WEAPON_THROWN: 80,
}
PREVIEW_SUMMARY_REGION_ID = "preview-summary"
PREVIEW_FEATURES_REGION_ID = "preview-features"
PREVIEW_RESOURCES_REGION_ID = "preview-resources"
PREVIEW_SPELLS_REGION_ID = "preview-spells"
PREVIEW_SCOPE_REGION_ID = "preview-scope"
PREVIEW_EQUIPMENT_REGION_ID = "preview-equipment"
PREVIEW_ATTACKS_REGION_ID = "preview-attacks"
PREVIEW_SPELL_SLOTS_REGION_ID = "preview-spell-slots"
LEVEL_ONE_PREVIEW_REGION_IDS = (
    PREVIEW_SUMMARY_REGION_ID,
    PREVIEW_FEATURES_REGION_ID,
    PREVIEW_RESOURCES_REGION_ID,
    PREVIEW_SPELLS_REGION_ID,
    PREVIEW_SCOPE_REGION_ID,
    PREVIEW_EQUIPMENT_REGION_ID,
    PREVIEW_ATTACKS_REGION_ID,
)
LEVEL_ONE_LIVE_REGION_IDS = (CHOICE_SECTIONS_REGION_ID, *LEVEL_ONE_PREVIEW_REGION_IDS)
LEVEL_UP_PREVIEW_REGION_IDS = (
    PREVIEW_SUMMARY_REGION_ID,
    PREVIEW_FEATURES_REGION_ID,
    PREVIEW_RESOURCES_REGION_ID,
    PREVIEW_SPELLS_REGION_ID,
    PREVIEW_SCOPE_REGION_ID,
    PREVIEW_SPELL_SLOTS_REGION_ID,
)
LEVEL_UP_LIVE_REGION_IDS = (CHOICE_SECTIONS_REGION_ID, *LEVEL_UP_PREVIEW_REGION_IDS)
CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND = {
    "species": {"species"},
    "background": {"background", "backgrounds"},
    "feat": {"feat", "feats"},
}

ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")
LEVEL_ONE_BUILDER_STATIC_KEYS = frozenset(
    {
        "name",
        "character_slug",
        "alignment",
        "experience_model",
        "class_slug",
        "subclass_slug",
        "species_slug",
        "background_slug",
        *ABILITY_KEYS,
    }
)
LEVEL_UP_BUILDER_STATIC_KEYS = frozenset({"hp_gain", "subclass_slug"})
ABILITY_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}
SKILL_LABELS = {
    "acrobatics": "Acrobatics",
    "animal handling": "Animal Handling",
    "arcana": "Arcana",
    "athletics": "Athletics",
    "deception": "Deception",
    "history": "History",
    "insight": "Insight",
    "intimidation": "Intimidation",
    "investigation": "Investigation",
    "medicine": "Medicine",
    "nature": "Nature",
    "perception": "Perception",
    "performance": "Performance",
    "persuasion": "Persuasion",
    "religion": "Religion",
    "sleight of hand": "Sleight of Hand",
    "stealth": "Stealth",
    "survival": "Survival",
}
SKILL_ABILITY_KEYS = {
    "acrobatics": "dex",
    "animal handling": "wis",
    "arcana": "int",
    "athletics": "str",
    "deception": "cha",
    "history": "int",
    "insight": "wis",
    "intimidation": "cha",
    "investigation": "int",
    "medicine": "wis",
    "nature": "int",
    "perception": "wis",
    "performance": "cha",
    "persuasion": "cha",
    "religion": "int",
    "sleight of hand": "dex",
    "stealth": "dex",
    "survival": "wis",
}
SKILL_PROFICIENCY_LEVEL_RANKS = {
    "none": 0,
    "half_proficient": 1,
    "proficient": 2,
    "expertise": 3,
}
STANDARD_LANGUAGE_OPTIONS = [
    "Common",
    "Dwarvish",
    "Elvish",
    "Giant",
    "Gnomish",
    "Goblin",
    "Halfling",
    "Orc",
]
COMMON_TOOL_PROFICIENCY_OPTIONS = [
    "Alchemist's Supplies",
    "Bagpipes",
    "Brewer's Supplies",
    "Calligrapher's Supplies",
    "Carpenter's Tools",
    "Cartographer's Tools",
    "Cobbler's Tools",
    "Cook's Utensils",
    "Dice Set",
    "Disguise Kit",
    "Dragonchess Set",
    "Drum",
    "Dulcimer",
    "Flute",
    "Forgery Kit",
    "Glassblower's Tools",
    "Herbalism Kit",
    "Horn",
    "Jeweler's Tools",
    "Leatherworker's Tools",
    "Lute",
    "Lyre",
    "Mason's Tools",
    "Navigator's Tools",
    "Painter's Supplies",
    "Pan Flute",
    "Playing Card Set",
    "Poisoner's Kit",
    "Potter's Tools",
    "Shawm",
    "Smith's Tools",
    "Thieves' Tools",
    "Tinker's Tools",
    "Three-Dragon Ante Set",
    "Vehicles (Land)",
    "Vehicles (Water)",
    "Viol",
    "Weaver's Tools",
    "Woodcarver's Tools",
]
SIZE_LABELS = {
    "T": "Tiny",
    "S": "Small",
    "M": "Medium",
    "L": "Large",
    "H": "Huge",
    "G": "Gargantuan",
}
REDUNDANT_SPECIES_TRAIT_NAMES = {
    "age",
    "size",
    "speed",
    "languages",
    "language",
    "ability score increase",
    "skills",
    "skill",
    "feat",
}
ABILITY_SCORE_IMPROVEMENT_NAMES = {
    normalize_lookup("Ability Score Improvement"),
    normalize_lookup("Ability Score Increase"),
}
SPELLCASTING_ABILITY_BY_CLASS = {
    "Bard": "Charisma",
    "Cleric": "Wisdom",
    "Druid": "Wisdom",
    "Paladin": "Charisma",
    "Ranger": "Wisdom",
    "Sorcerer": "Charisma",
    "Warlock": "Charisma",
    "Wizard": "Intelligence",
}
LEVEL_ONE_SPELL_SLOTS_BY_CLASS = {
    "Bard": [{"level": 1, "max_slots": 2}],
    "Cleric": [{"level": 1, "max_slots": 2}],
    "Druid": [{"level": 1, "max_slots": 2}],
    "Sorcerer": [{"level": 1, "max_slots": 2}],
    "Warlock": [{"level": 1, "max_slots": 1}],
    "Wizard": [{"level": 1, "max_slots": 2}],
}
LEVEL_ONE_SPELL_RULES_BY_CLASS = {
    "Bard": {"cantrip_count": 2, "level_one_mode": "known", "level_one_count": 4},
    "Cleric": {"cantrip_count": 3, "level_one_mode": "prepared", "ability_key": "wis"},
    "Druid": {"cantrip_count": 2, "level_one_mode": "prepared", "ability_key": "wis"},
    "Sorcerer": {"cantrip_count": 4, "level_one_mode": "known", "level_one_count": 2},
    "Warlock": {"cantrip_count": 2, "level_one_mode": "known", "level_one_count": 2},
    "Wizard": {
        "cantrip_count": 3,
        "level_one_mode": "wizard",
        "spellbook_count": 6,
        "ability_key": "int",
    },
}
LEVEL_TWO_SPELL_SLOTS_BY_CLASS = {
    "Bard": [{"level": 1, "max_slots": 3}],
    "Cleric": [{"level": 1, "max_slots": 3}],
    "Druid": [{"level": 1, "max_slots": 3}],
    "Paladin": [{"level": 1, "max_slots": 2}],
    "Ranger": [{"level": 1, "max_slots": 2}],
    "Sorcerer": [{"level": 1, "max_slots": 3}],
    "Warlock": [{"level": 1, "max_slots": 2}],
    "Wizard": [{"level": 1, "max_slots": 3}],
}
LEVEL_TWO_SPELL_RULES_BY_CLASS = {
    "Bard": {"spell_mode": "known", "new_level_one_spells": 1},
    "Cleric": {"spell_mode": "prepared", "ability_key": "wis"},
    "Druid": {"spell_mode": "prepared", "ability_key": "wis"},
    "Paladin": {"spell_mode": "prepared", "ability_key": "cha", "starts_spellcasting": True},
    "Ranger": {"spell_mode": "known", "new_level_one_spells": 2, "starts_spellcasting": True},
    "Sorcerer": {"spell_mode": "known", "new_level_one_spells": 1},
    "Warlock": {"spell_mode": "known", "new_level_one_spells": 1},
    "Wizard": {"spell_mode": "wizard", "ability_key": "int", "new_spellbook_spells": 2},
}
EXTRA_PHB_LEVEL_ONE_SPELL_LISTS = {
    "Paladin": {
        "1": [
            "Bless",
            "Command",
            "Compelled Duel",
            "Cure Wounds",
            "Detect Evil and Good",
            "Detect Magic",
            "Detect Poison and Disease",
            "Divine Favor",
            "Heroism",
            "Protection from Evil and Good",
            "Purify Food and Drink",
            "Searing Smite",
            "Shield of Faith",
            "Thunderous Smite",
            "Wrathful Smite",
        ]
    },
    "Ranger": {
        "1": [
            "Alarm",
            "Animal Friendship",
            "Cure Wounds",
            "Detect Magic",
            "Detect Poison and Disease",
            "Ensnaring Strike",
            "Fog Cloud",
            "Goodberry",
            "Hail of Thorns",
            "Hunter's Mark",
            "Jump",
            "Longstrider",
            "Speak with Animals",
        ]
    },
}
NATIVE_LEVEL_UP_LIMITATIONS = [
    "Native level-up currently advances one level at a time for single-class native characters whose base class has imported native progression support.",
    "Hit point gain is entered manually so your table can choose rolled or fixed HP.",
    "Prepared-caster level-up currently preserves existing prepared spells and adds the new picks needed for the next level.",
    "Some advanced feat side effects and non-structured campaign spell access still need manual follow-up.",
]
LEVEL_ONE_ALWAYS_PREPARED_SPELLS_BY_SUBCLASS = {
    normalize_lookup("Knowledge Domain"): ["Command", "Identify"],
    normalize_lookup("Life Domain"): ["Bless", "Cure Wounds"],
    normalize_lookup("Light Domain"): ["Burning Hands", "Faerie Fire"],
    normalize_lookup("Nature Domain"): ["Animal Friendship", "Speak with Animals"],
    normalize_lookup("Tempest Domain"): ["Fog Cloud", "Thunderwave"],
    normalize_lookup("Trickery Domain"): ["Charm Person", "Disguise Self"],
    normalize_lookup("War Domain"): ["Divine Favor", "Shield of Faith"],
}
ITEM_TITLES_BY_EQUIPMENT_TYPE = {
    "weaponSimple": [
        "Club",
        "Dagger",
        "Greatclub",
        "Handaxe",
        "Javelin",
        "Light Hammer",
        "Mace",
        "Quarterstaff",
        "Sickle",
        "Spear",
        "Light Crossbow",
        "Dart",
        "Shortbow",
        "Sling",
    ],
    "weaponSimpleMelee": [
        "Club",
        "Dagger",
        "Greatclub",
        "Handaxe",
        "Javelin",
        "Light Hammer",
        "Mace",
        "Quarterstaff",
        "Sickle",
        "Spear",
    ],
    "weaponMartial": [
        "Battleaxe",
        "Flail",
        "Glaive",
        "Greataxe",
        "Greatsword",
        "Halberd",
        "Lance",
        "Longsword",
        "Maul",
        "Morningstar",
        "Pike",
        "Rapier",
        "Scimitar",
        "Shortsword",
        "Trident",
        "War Pick",
        "Warhammer",
        "Whip",
        "Blowgun",
        "Hand Crossbow",
        "Heavy Crossbow",
        "Longbow",
        "Net",
    ],
    "weaponMartialMelee": [
        "Battleaxe",
        "Flail",
        "Glaive",
        "Greataxe",
        "Greatsword",
        "Halberd",
        "Lance",
        "Longsword",
        "Maul",
        "Morningstar",
        "Pike",
        "Rapier",
        "Scimitar",
        "Shortsword",
        "Trident",
        "War Pick",
        "Warhammer",
        "Whip",
    ],
    "focusSpellcastingArcane": ["Crystal", "Orb", "Rod", "Staff", "Wand"],
    "focusSpellcastingHoly": ["Amulet", "Emblem", "Reliquary"],
    "focusSpellcastingDruidic": ["Sprig of Mistletoe", "Totem", "Wooden Staff", "Yew Wand"],
}
ITEM_TYPE_CODES_BY_EQUIPMENT_TYPE = {
    "instrumentMusical": {"INS"},
    "setGaming": {"GS"},
    "toolArtisan": {"AT"},
}
DAMAGE_TYPE_LABELS = {
    "B": "bludgeoning",
    "P": "piercing",
    "S": "slashing",
}
WEAPON_PROPERTY_LABELS = {
    "A": "Ammunition",
    "F": "Finesse",
    "H": "Heavy",
    "L": "Light",
    "LD": "Loading",
    "R": "Reach",
    "S": "Special",
    "T": "Thrown",
    "2H": "Two-Handed",
    "V": "Versatile",
}
INLINE_TAG_PATTERN = re.compile(r"{@[^ }]+\s+([^}]+)}")


class CharacterBuildError(ValueError):
    pass


def build_level_one_builder_context(
    systems_service: Any,
    campaign_slug: str,
    form_values: dict[str, str] | None = None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    preview_values = _normalize_preview_values(form_values or {})
    static_bundle = _build_common_builder_static_bundle(
        systems_service,
        campaign_slug,
        campaign_page_records=campaign_page_records,
    )
    class_options = list(static_bundle.get("supported_class_entries") or [])
    species_options = list(static_bundle.get("species_options") or [])
    background_options = list(static_bundle.get("background_options") or [])
    feat_options = list(static_bundle.get("feat_options") or [])
    feat_catalog = dict(static_bundle.get("feat_catalog") or {})
    optionalfeature_catalog = dict(static_bundle.get("optionalfeature_catalog") or {})
    item_catalog = dict(static_bundle.get("item_catalog") or {})
    spell_catalog = dict(static_bundle.get("spell_catalog") or {})
    campaign_feature_options = list(static_bundle.get("campaign_feature_options") or [])
    campaign_item_options = list(static_bundle.get("campaign_item_options") or [])

    preview_values["class_slug"] = _sanitize_entry_selection_value(preview_values.get("class_slug"), class_options)
    preview_values["species_slug"] = _sanitize_entry_selection_value(preview_values.get("species_slug"), species_options)
    preview_values["background_slug"] = _sanitize_entry_selection_value(
        preview_values.get("background_slug"),
        background_options,
    )
    selected_class = _resolve_selected_entry(class_options, preview_values.get("class_slug", ""))
    selected_species = _resolve_selected_entry(species_options, preview_values.get("species_slug", ""))
    selected_background = _resolve_selected_entry(background_options, preview_values.get("background_slug", ""))

    subclass_options = _list_subclass_options(
        systems_service,
        campaign_slug,
        selected_class,
        subclass_entries=list(static_bundle.get("subclass_entries") or []),
    )
    preview_values["subclass_slug"] = _sanitize_entry_selection_value(
        preview_values.get("subclass_slug"),
        subclass_options,
    )
    selected_subclass = _resolve_selected_entry(subclass_options, preview_values.get("subclass_slug", ""))

    class_progression = _class_progression_for_builder(systems_service, campaign_slug, selected_class)
    subclass_progression = _subclass_progression_for_builder(systems_service, campaign_slug, selected_subclass)
    requires_subclass = _class_requires_subclass_at_level_one(selected_class, class_progression)

    equipment_groups = _build_equipment_groups(
        selected_class=selected_class,
        selected_background=selected_background,
        item_catalog=item_catalog,
        values=preview_values,
    )

    preview_values, choice_sections = _stabilize_choice_section_values(
        preview_values,
        static_keys=LEVEL_ONE_BUILDER_STATIC_KEYS,
        build_sections=lambda current_values: _build_choice_sections(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            selected_species=selected_species,
            selected_background=selected_background,
            feat_options=feat_options,
            feat_catalog=feat_catalog,
            optionalfeature_catalog=optionalfeature_catalog,
            class_progression=class_progression,
            subclass_progression=subclass_progression,
            equipment_groups=equipment_groups,
            campaign_feature_options=campaign_feature_options,
            campaign_item_options=campaign_item_options,
            item_catalog=item_catalog,
            spell_catalog=spell_catalog,
            values=current_values,
        ),
    )
    choice_sections = _annotate_builder_choice_sections(
        choice_sections,
        preview_region_ids=LEVEL_ONE_PREVIEW_REGION_IDS,
    )

    preview = _build_level_one_preview(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        equipment_groups=equipment_groups,
        choice_sections=choice_sections,
        feat_catalog=feat_catalog,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        values=preview_values,
    )

    return {
        "values": preview_values,
        "class_options": [_entry_option(entry) for entry in class_options],
        "species_options": [_entry_option(entry) for entry in species_options],
        "background_options": [_entry_option(entry) for entry in background_options],
        "subclass_options": [_entry_option(entry) for entry in subclass_options],
        "selected_class": selected_class,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_subclass": selected_subclass,
        "requires_subclass": requires_subclass,
        "choice_sections": choice_sections,
        "class_progression": class_progression,
        "subclass_progression": subclass_progression,
        "equipment_groups": equipment_groups,
        "feat_catalog": feat_catalog,
        "optionalfeature_catalog": optionalfeature_catalog,
        "item_catalog": item_catalog,
        "spell_catalog": spell_catalog,
        "limitations": [
            "Base classes now come from the campaign's enabled Systems sources when their native progression metadata is available, while older PHB fallback data still covers previously imported local classes.",
            "Species, backgrounds, and feats can come from either enabled Systems entries or published campaign pages that expose structured character-option metadata.",
            "Published campaign wiki features and items can also be linked in during creation through the optional campaign content fields.",
            "Enter level-1 ability scores after species bonuses. Native feat-driven ability increases are applied automatically.",
            "Native attack rows now cover basic PHB weapons, off-hand attacks, key level-1 fighting-style adjustments, and the current modeled feat attack variants, but a few advanced riders still need manual follow-up.",
            "Gold-alternative loadouts, non-structured campaign spell access, and a few remaining feat/spell edge cases still need manual follow-up.",
        ],
        "preview": preview,
        "preview_region_ids": list(LEVEL_ONE_PREVIEW_REGION_IDS),
        "preview_regions_csv": ",".join(LEVEL_ONE_PREVIEW_REGION_IDS),
        "live_region_ids": list(LEVEL_ONE_LIVE_REGION_IDS),
        "live_regions_csv": ",".join(LEVEL_ONE_LIVE_REGION_IDS),
    }


def build_level_one_character_definition(
    campaign_slug: str,
    builder_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    selected_class = builder_context.get("selected_class")
    selected_species = builder_context.get("selected_species")
    selected_background = builder_context.get("selected_background")
    selected_subclass = builder_context.get("selected_subclass")
    choice_sections = list(builder_context.get("choice_sections") or [])
    class_progression = list(builder_context.get("class_progression") or [])
    subclass_progression = list(builder_context.get("subclass_progression") or [])
    equipment_groups = list(builder_context.get("equipment_groups") or [])
    feat_catalog = dict(builder_context.get("feat_catalog") or {})
    optionalfeature_catalog = dict(builder_context.get("optionalfeature_catalog") or {})
    item_catalog = dict(builder_context.get("item_catalog") or {})
    spell_catalog = dict(builder_context.get("spell_catalog") or {})
    limitations = list(builder_context.get("limitations") or [])
    context_values = builder_context.get("values")
    values = _normalize_preview_values(
        _sanitize_choice_section_values(
            {
                **(dict(context_values) if isinstance(context_values, dict) else {}),
                **{key: str(value) for key, value in dict(form_values or {}).items()},
            },
            choice_sections=choice_sections,
            static_keys=LEVEL_ONE_BUILDER_STATIC_KEYS,
        )
    )

    if selected_class is None:
        raise CharacterBuildError("Choose a class to build the character.")
    if selected_species is None:
        raise CharacterBuildError("Choose a species to build the character.")
    if selected_background is None:
        raise CharacterBuildError("Choose a background to build the character.")
    if builder_context.get("requires_subclass") and selected_subclass is None:
        raise CharacterBuildError("Choose a subclass for this class at level 1.")

    name = str(values.get("name") or "").strip()
    if not name:
        raise CharacterBuildError("Character name is required.")
    character_slug = slugify(str(values.get("character_slug") or "").strip() or name)
    if not character_slug:
        raise CharacterBuildError("Character slug is required.")

    feat_selections = _resolve_builder_feat_selections(values, feat_catalog)
    ability_scores = _apply_feat_ability_score_bonuses(
        _parse_ability_scores(values),
        feat_selections=feat_selections,
        selected_choices={},
        strict=False,
    )
    proficiency_bonus = 2
    fixed_proficiencies, selected_choices = _resolve_builder_choices(choice_sections, values)
    ability_scores = _apply_feat_ability_score_bonuses(
        _parse_ability_scores(values),
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    selected_feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_selected_entries([selected_species, selected_background])
        + _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(selected_feature_entries)
    )
    proficiencies = _build_level_one_proficiencies(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        fixed_proficiencies=fixed_proficiencies,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        campaign_option_payloads=selected_campaign_option_payloads,
    )
    skills = _build_skills_payload(ability_scores, proficiencies["skills"], proficiency_bonus)

    features, resource_templates = _build_feature_payloads(
        selected_feature_entries,
        ability_scores=ability_scores,
        current_level=1,
    )
    equipment_catalog = _build_level_one_equipment_catalog(
        equipment_groups,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        item_catalog=item_catalog,
    )
    attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=proficiencies["weapons"],
        selected_choices=selected_choices,
        features=features,
    )

    stats = _build_level_one_stats(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        ability_scores=ability_scores,
        skills=skills,
        proficiency_bonus=proficiency_bonus,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        current_level=1,
        equipment_catalog=equipment_catalog,
        features=features,
        item_catalog=item_catalog,
        campaign_option_payloads=selected_campaign_option_payloads,
    )
    profile = _build_level_one_profile(
        name=name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        values=values,
    )
    spellcasting = _build_level_one_spellcasting(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        feature_entries=selected_feature_entries,
        campaign_option_payloads=selected_campaign_option_payloads,
    )

    source_path = "builder://native-level-1"
    source = {
        "source_path": source_path,
        "source_type": "native_character_builder",
        "imported_from": "In-app Native Level 1 Builder",
        "imported_at": isoformat(utcnow()),
        "parse_warnings": list(limitations),
    }
    definition = CharacterDefinition(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        name=name,
        status="active",
        profile=profile,
        stats=stats,
        skills=skills,
        proficiencies={
            "armor": proficiencies["armor"],
            "weapons": proficiencies["weapons"],
            "tools": proficiencies["tools"],
            "languages": proficiencies["languages"],
        },
        attacks=attacks,
        features=features,
        spellcasting=spellcasting,
        equipment_catalog=equipment_catalog,
        reference_notes={
            "additional_notes_markdown": "",
            "allies_and_organizations_markdown": "",
            "custom_sections": [],
        },
        resource_templates=resource_templates,
        source=source,
    )
    definition = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        resolved_class=selected_class,
        resolved_subclass=selected_subclass,
        resolved_species=selected_species,
        resolved_background=selected_background,
    )
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        source_path=source_path,
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="warning" if limitations else "clean",
        warnings=list(limitations),
    )
    return definition, import_metadata


def supports_native_level_up(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_slug: str = "",
    campaign_page_records: list[Any] | None = None,
) -> bool:
    if systems_service is not None and str(campaign_slug or "").strip():
        readiness = native_level_up_readiness(
            systems_service,
            campaign_slug,
            definition,
            campaign_page_records=campaign_page_records,
        )
        return str(readiness.get("status") or "").strip() == NATIVE_LEVEL_UP_READY
    return _native_level_up_support_error(definition) == ""


def native_level_up_readiness(
    systems_service: Any,
    campaign_slug: str,
    definition: CharacterDefinition,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    source_type = _character_source_type(definition)
    is_native = source_type == "native_character_builder"
    is_imported = source_type in IMPORTED_CHARACTER_SOURCE_TYPES
    current_level = _resolve_native_character_level(definition)

    if not is_native and not is_imported:
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": "Level-up currently supports native in-app characters and imported character sheets only.",
            "reasons": ["This character source is outside the current native progression flow."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    classes = list((definition.profile or {}).get("classes") or [])
    if len(classes) != 1:
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": f"Level-up currently supports single-class {character_label} characters only.",
            "reasons": ["This sheet must stay single-class for the current level-up flow."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    if current_level < 1:
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": f"This {character_label} character is missing a valid current level.",
            "reasons": ["The character needs a valid level before native level-up can continue."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    if current_level >= 20:
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": f"This {character_label} character is already at level 20.",
            "reasons": ["The current native level-up flow stops at level 20."],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
        }

    class_payload = dict(classes[0] or {})
    enabled_class_options = _list_campaign_enabled_entries(systems_service, campaign_slug, "class")
    class_options = [entry for entry in enabled_class_options if _supports_native_class_entry(entry)]
    species_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "race"),
        campaign_page_records or [],
        kind="species",
    )
    background_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "background"),
        campaign_page_records or [],
        kind="background",
    )

    profile_class_ref = definition.profile.get("class_ref")
    class_row_ref = class_payload.get("systems_ref")
    selected_enabled_class = _resolve_profile_entry(
        enabled_class_options,
        profile_class_ref or class_row_ref,
        fallback_title=_native_character_class_name(definition),
    )
    if selected_enabled_class is not None and not _supports_native_class_entry(selected_enabled_class):
        character_label = "imported" if is_imported else "native"
        return {
            "status": NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": (
                f"This {character_label} character's base class does not yet expose the progression metadata "
                "needed for native level-up."
            ),
            "reasons": [
                "This class is enabled in Systems, but its progression metadata is still outside the current native level-up flow."
            ],
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
            "selected_class": None,
            "selected_species": None,
            "selected_background": None,
            "selected_subclass": None,
            "spell_repair_rows": [],
        }

    selected_class = _resolve_profile_entry(
        class_options,
        profile_class_ref or class_row_ref,
        fallback_title=_native_character_class_name(definition),
    )
    selected_species = _resolve_profile_entry(
        species_options,
        definition.profile.get("species_ref"),
        page_ref=definition.profile.get("species_page_ref"),
        fallback_title=str(definition.profile.get("species") or "").strip(),
    )
    selected_background = _resolve_profile_entry(
        background_options,
        definition.profile.get("background_ref"),
        page_ref=definition.profile.get("background_page_ref"),
        fallback_title=str(definition.profile.get("background") or "").strip(),
    )

    repair_reasons: list[str] = []
    if selected_class is None:
        repair_reasons.append("Choose a supported base class link for this character.")
    elif is_imported:
        if not _systems_ref_slug(profile_class_ref):
            repair_reasons.append("Confirm the supported base class link on the character profile before leveling up.")
        if not _systems_ref_slug(class_row_ref):
            repair_reasons.append("Confirm the class row link so native level-up can extend the imported class baseline cleanly.")
    if selected_species is None:
        repair_reasons.append("Choose a species link that the native level-up flow can resolve.")
    elif is_imported and not _has_profile_entry_link(
        definition.profile.get("species_ref"),
        page_ref=definition.profile.get("species_page_ref"),
    ):
        repair_reasons.append("Confirm the species link so native level-up can keep using the imported baseline.")
    if selected_background is None:
        repair_reasons.append("Choose a background link that the native level-up flow can resolve.")
    elif is_imported and not _has_profile_entry_link(
        definition.profile.get("background_ref"),
        page_ref=definition.profile.get("background_page_ref"),
    ):
        repair_reasons.append("Confirm the background link so native level-up can keep using the imported baseline.")

    subclass_options: list[SystemsEntryRecord] = []
    selected_subclass: SystemsEntryRecord | None = None
    if selected_class is not None:
        subclass_options = _list_subclass_options(systems_service, campaign_slug, selected_class)
        selected_subclass = _resolve_profile_entry(
            subclass_options,
            definition.profile.get("subclass_ref") or dict((classes[0] or {}).get("subclass_ref") or {}),
            fallback_title=_native_character_subclass_name(definition),
        )
        class_progression = systems_service.build_class_feature_progression_for_class_entry(campaign_slug, selected_class)
        if _class_requires_subclass_at_level(selected_class, class_progression, current_level) and selected_subclass is None:
            repair_reasons.append(
                f"Choose a {str(selected_class.metadata.get('subclass_title') or 'subclass').strip() or 'subclass'} link before leveling up."
            )
        elif (
            is_imported
            and _class_requires_subclass_at_level(selected_class, class_progression, current_level)
            and not _systems_ref_slug(definition.profile.get("subclass_ref"))
        ):
            repair_reasons.append(
                f"Confirm the {str(selected_class.metadata.get('subclass_title') or 'subclass').strip() or 'subclass'} link before leveling up."
            )

    spell_repair_rows: list[dict[str, Any]] = []
    if is_imported and selected_class is not None:
        spell_repair_rows = _build_imported_spell_repair_rows(
            definition,
            selected_class=selected_class,
        )
        if spell_repair_rows:
            repair_reasons.append("Classify the current imported spell rows so native spell progression can trust them.")

    if repair_reasons:
        return {
            "status": NATIVE_LEVEL_UP_REPAIRABLE if is_imported else NATIVE_LEVEL_UP_UNSUPPORTED,
            "message": (
                "This imported character needs a quick progression repair before native level-up."
                if is_imported
                else "This native character is missing enabled links needed for level-up."
            ),
            "reasons": repair_reasons,
            "source_type": source_type,
            "is_native": is_native,
            "is_imported": is_imported,
            "current_level": current_level,
            "selected_class": selected_class,
            "selected_species": selected_species,
            "selected_background": selected_background,
            "selected_subclass": selected_subclass,
            "spell_repair_rows": spell_repair_rows,
        }

    return {
        "status": NATIVE_LEVEL_UP_READY,
        "message": "",
        "reasons": [],
        "source_type": source_type,
        "is_native": is_native,
        "is_imported": is_imported,
        "current_level": current_level,
        "selected_class": selected_class,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_subclass": selected_subclass,
        "spell_repair_rows": spell_repair_rows,
    }


def _character_source_type(definition: CharacterDefinition) -> str:
    return str((definition.source or {}).get("source_type") or "").strip()


def _native_character_subclass_name(definition: CharacterDefinition) -> str:
    classes = list((definition.profile or {}).get("classes") or [])
    if classes:
        class_payload = dict(classes[0] or {})
        subclass_ref = dict(class_payload.get("subclass_ref") or {})
        return str(subclass_ref.get("title") or class_payload.get("subclass_name") or "").strip()
    subclass_ref = dict((definition.profile or {}).get("subclass_ref") or {})
    return str(subclass_ref.get("title") or "").strip()


def _native_progression_payload(source_payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(source_payload or {})
    payload = dict(source.get("native_progression") or {})
    hp_baseline = dict(payload.get("hp_baseline") or {})
    try:
        baseline_level = int(hp_baseline.get("level") or 0)
        baseline_max_hp = int(hp_baseline.get("max_hp") or 0)
    except (TypeError, ValueError):
        baseline_level = 0
        baseline_max_hp = 0
    if baseline_level > 0 and baseline_max_hp > 0:
        payload["hp_baseline"] = {
            "level": baseline_level,
            "max_hp": baseline_max_hp,
        }
    else:
        payload.pop("hp_baseline", None)
    history = [dict(entry) for entry in list(payload.get("history") or []) if isinstance(entry, dict)]
    if history:
        payload["history"] = history
    return payload


def _native_progression_hp_baseline(source_payload: dict[str, Any] | None) -> dict[str, int] | None:
    payload = _native_progression_payload(source_payload)
    hp_baseline = dict(payload.get("hp_baseline") or {})
    try:
        level = int(hp_baseline.get("level") or 0)
        max_hp = int(hp_baseline.get("max_hp") or 0)
    except (TypeError, ValueError):
        return None
    if level <= 0 or max_hp <= 0:
        return None
    return {"level": level, "max_hp": max_hp}


def _ensure_native_progression_hp_baseline(
    source_payload: dict[str, Any] | None,
    *,
    level: int,
    max_hp: int,
    baseline_repaired: bool = False,
) -> dict[str, Any]:
    source = dict(source_payload or {})
    if _native_progression_hp_baseline(source) is not None:
        if baseline_repaired:
            native_progression = _native_progression_payload(source)
            native_progression["baseline_repaired_at"] = isoformat(utcnow())
            source["native_progression"] = native_progression
        return source
    clean_level = max(int(level or 0), 0)
    clean_max_hp = max(int(max_hp or 0), 0)
    if clean_level <= 0 or clean_max_hp <= 0:
        return source
    native_progression = _native_progression_payload(source)
    native_progression["hp_baseline"] = {"level": clean_level, "max_hp": clean_max_hp}
    if baseline_repaired:
        native_progression["baseline_repaired_at"] = isoformat(utcnow())
    source["native_progression"] = native_progression
    return source


def _seed_source_hp_baseline_from_definition(
    source_payload: dict[str, Any] | None,
    definition: CharacterDefinition,
    *,
    baseline_repaired: bool = False,
) -> dict[str, Any]:
    current_level = _resolve_native_character_level(definition)
    base_stats = _definition_base_stats_without_adjustments(definition)
    try:
        max_hp = int(base_stats.get("max_hp") or 0)
    except (TypeError, ValueError):
        max_hp = 0
    return _ensure_native_progression_hp_baseline(
        source_payload,
        level=current_level,
        max_hp=max_hp,
        baseline_repaired=baseline_repaired,
    )


def _with_native_progression_event(
    source_payload: dict[str, Any] | None,
    *,
    kind: str,
    target_level: int,
    previous_level: int | None = None,
    baseline_repaired: bool = False,
    hp_gain: int | None = None,
    max_hp_delta: int | None = None,
) -> dict[str, Any]:
    source = dict(source_payload or {})
    native_progression = _native_progression_payload(source)
    if baseline_repaired:
        native_progression["baseline_repaired_at"] = isoformat(utcnow())
    history = [dict(entry) for entry in list(native_progression.get("history") or []) if isinstance(entry, dict)]
    event: dict[str, Any] = {
        "kind": str(kind or "").strip() or "managed",
        "at": isoformat(utcnow()),
        "target_level": int(target_level or 0),
    }
    if previous_level is not None:
        event["from_level"] = int(previous_level)
        event["to_level"] = int(target_level or 0)
    if hp_gain is not None:
        event["hp_gain"] = int(hp_gain)
    if max_hp_delta is not None:
        event["max_hp_delta"] = int(max_hp_delta)
    history.append(event)
    native_progression["history"] = history
    source["native_progression"] = native_progression
    return source


def _build_imported_spell_repair_rows(
    definition: CharacterDefinition,
    *,
    selected_class: SystemsEntryRecord,
) -> list[dict[str, Any]]:
    spell_mode = _spellcasting_mode_for_class(selected_class.title, selected_class=selected_class)
    if not spell_mode:
        return []
    rows: list[dict[str, Any]] = []
    mark_options = _imported_spell_mark_options(spell_mode)
    if not mark_options:
        return rows
    for index, spell in enumerate(list((definition.spellcasting or {}).get("spells") or []), start=1):
        payload = dict(spell or {})
        name = str(payload.get("name") or "").strip()
        mark = str(payload.get("mark") or "").strip()
        if not name or mark:
            continue
        rows.append(
            {
                "index": index,
                "name": name,
                "field_name": f"repair_spell_mark_{index}",
                "selected": "",
                "options": [_choice_option(label, value) for value, label in mark_options],
            }
        )
    return rows


def _imported_spell_mark_options(spell_mode: str) -> list[tuple[str, str]]:
    if spell_mode == "known":
        return [("Cantrip", "Cantrip"), ("Known", "Known")]
    if spell_mode == "prepared":
        return [("Cantrip", "Cantrip"), ("Prepared", "Prepared"), ("Known", "Known")]
    if spell_mode == "wizard":
        return [
            ("Cantrip", "Cantrip"),
            ("Spellbook", "Spellbook"),
            ("Prepared + Spellbook", "Prepared + Spellbook"),
            ("Prepared", "Prepared"),
            ("Known", "Known"),
        ]
    return []


def build_native_level_up_context(
    systems_service: Any,
    campaign_slug: str,
    definition: CharacterDefinition,
    form_values: dict[str, str] | None = None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    support_error = _native_level_up_support_error(
        definition,
        systems_service=systems_service,
        campaign_slug=campaign_slug,
        campaign_page_records=campaign_page_records,
    )
    if support_error:
        raise CharacterBuildError(support_error)

    values = _normalize_level_up_values(definition, form_values or {})
    current_level = _resolve_native_character_level(definition)
    next_level = current_level + 1
    static_bundle = _build_common_builder_static_bundle(
        systems_service,
        campaign_slug,
        campaign_page_records=campaign_page_records,
    )
    class_options = list(static_bundle.get("supported_class_entries") or [])
    species_options = list(static_bundle.get("species_options") or [])
    background_options = list(static_bundle.get("background_options") or [])
    feat_options = list(static_bundle.get("feat_options") or [])
    feat_catalog = dict(static_bundle.get("feat_catalog") or {})
    optionalfeature_catalog = dict(static_bundle.get("optionalfeature_catalog") or {})
    item_catalog = dict(static_bundle.get("item_catalog") or {})
    spell_catalog = dict(static_bundle.get("spell_catalog") or {})

    selected_class = _resolve_profile_entry(
        class_options,
        definition.profile.get("class_ref"),
        fallback_title=_native_character_class_name(definition),
    )
    selected_species = _resolve_profile_entry(
        species_options,
        definition.profile.get("species_ref"),
        page_ref=definition.profile.get("species_page_ref"),
        fallback_title=str(definition.profile.get("species") or "").strip(),
    )
    selected_background = _resolve_profile_entry(
        background_options,
        definition.profile.get("background_ref"),
        page_ref=definition.profile.get("background_page_ref"),
        fallback_title=str(definition.profile.get("background") or "").strip(),
    )
    if selected_class is None or selected_species is None or selected_background is None:
        raise CharacterBuildError("This native character is missing enabled Systems links needed for level-up.")
    if not _supports_native_class_entry(selected_class):
        raise CharacterBuildError("This native character's base class does not yet expose the progression metadata needed for native level-up.")

    subclass_options = _list_subclass_options(
        systems_service,
        campaign_slug,
        selected_class,
        subclass_entries=list(static_bundle.get("subclass_entries") or []),
    )
    existing_subclass_slug = _systems_ref_slug(definition.profile.get("subclass_ref"))
    if existing_subclass_slug and not str(values.get("subclass_slug") or "").strip():
        values["subclass_slug"] = existing_subclass_slug
    values["subclass_slug"] = _sanitize_entry_selection_value(values.get("subclass_slug"), subclass_options)
    selected_subclass = _resolve_selected_entry(subclass_options, values.get("subclass_slug", ""))

    class_progression = _class_progression_for_builder(systems_service, campaign_slug, selected_class)
    requires_subclass = (
        _class_requires_subclass_at_level(selected_class, class_progression, next_level)
        and selected_subclass is None
    )
    subclass_progression = _subclass_progression_for_builder(systems_service, campaign_slug, selected_subclass)
    ability_scores = _ability_scores_from_definition(definition)
    values, choice_sections = _stabilize_choice_section_values(
        values,
        static_keys=LEVEL_UP_BUILDER_STATIC_KEYS,
        build_sections=lambda current_values: _build_level_up_choice_sections(
            definition=definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feat_options=feat_options,
            feat_catalog=feat_catalog,
            subclass_options=subclass_options,
            requires_subclass=requires_subclass,
            class_progression=class_progression,
            subclass_progression=subclass_progression,
            optionalfeature_catalog=optionalfeature_catalog,
            item_catalog=item_catalog,
            spell_catalog=spell_catalog,
            target_level=next_level,
            current_ability_scores=ability_scores,
            values=current_values,
        ),
    )
    choice_sections = _annotate_builder_choice_sections(
        choice_sections,
        preview_region_ids=LEVEL_UP_PREVIEW_REGION_IDS,
    )
    preview = _build_native_level_up_preview(
        definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        feat_catalog=feat_catalog,
        choice_sections=choice_sections,
        optionalfeature_catalog=optionalfeature_catalog,
        spell_catalog=spell_catalog,
        target_level=next_level,
        current_ability_scores=ability_scores,
        values=values,
    )
    return {
        "values": values,
        "character_name": definition.name,
        "current_level": current_level,
        "next_level": next_level,
        "campaign_slug": campaign_slug,
        "campaign_page_records": list(campaign_page_records or []),
        "systems_service": systems_service,
        "selected_class": selected_class,
        "selected_species": selected_species,
        "selected_background": selected_background,
        "selected_subclass": selected_subclass,
        "subclass_options": [_entry_option(entry) for entry in subclass_options],
        "feat_options": [_entry_option(entry) for entry in feat_options],
        "feat_catalog": feat_catalog,
        "optionalfeature_catalog": optionalfeature_catalog,
        "requires_subclass": requires_subclass,
        "choice_sections": choice_sections,
        "class_progression": class_progression,
        "subclass_progression": subclass_progression,
        "item_catalog": item_catalog,
        "spell_catalog": spell_catalog,
        "limitations": list(NATIVE_LEVEL_UP_LIMITATIONS),
        "preview": preview,
        "preview_region_ids": list(LEVEL_UP_PREVIEW_REGION_IDS),
        "preview_regions_csv": ",".join(LEVEL_UP_PREVIEW_REGION_IDS),
        "live_region_ids": list(LEVEL_UP_LIVE_REGION_IDS),
        "live_regions_csv": ",".join(LEVEL_UP_LIVE_REGION_IDS),
    }


def build_native_level_up_character_definition(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    level_up_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
    *,
    current_import_metadata: CharacterImportMetadata | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata, int]:
    support_error = _native_level_up_support_error(
        current_definition,
        systems_service=level_up_context.get("systems_service"),
        campaign_slug=str(level_up_context.get("campaign_slug") or campaign_slug or "").strip(),
        campaign_page_records=level_up_context.get("campaign_page_records"),
    )
    if support_error:
        raise CharacterBuildError(support_error)

    selected_class = level_up_context.get("selected_class")
    selected_species = level_up_context.get("selected_species")
    selected_background = level_up_context.get("selected_background")
    selected_subclass = level_up_context.get("selected_subclass")
    choice_sections = list(level_up_context.get("choice_sections") or [])
    class_progression = list(level_up_context.get("class_progression") or [])
    subclass_progression = list(level_up_context.get("subclass_progression") or [])
    feat_options = list(level_up_context.get("feat_options") or [])
    feat_catalog = dict(level_up_context.get("feat_catalog") or {})
    optionalfeature_catalog = dict(level_up_context.get("optionalfeature_catalog") or {})
    spell_catalog = dict(level_up_context.get("spell_catalog") or {})
    context_values = level_up_context.get("values")
    values = _normalize_level_up_values(
        current_definition,
        _sanitize_choice_section_values(
            {
                **(dict(context_values) if isinstance(context_values, dict) else {}),
                **{key: str(value) for key, value in dict(form_values or {}).items()},
            },
            choice_sections=choice_sections,
            static_keys=LEVEL_UP_BUILDER_STATIC_KEYS,
        ),
    )
    if selected_class is None or selected_species is None or selected_background is None:
        raise CharacterBuildError("This native character is missing the class, species, or background needed for level-up.")
    if level_up_context.get("requires_subclass") and selected_subclass is None:
        raise CharacterBuildError("Choose a subclass before leveling up this character.")

    current_level = int(level_up_context.get("current_level") or _resolve_native_character_level(current_definition))
    target_level = int(level_up_context.get("next_level") or (current_level + 1))
    if target_level != current_level + 1:
        raise CharacterBuildError("Level-up currently advances one level at a time.")

    hp_gain = _parse_level_up_hit_point_gain(values)
    _, selected_choices = _resolve_builder_choices(choice_sections, values)
    base_ability_scores, level_up_feat_entries, _ = _resolve_level_up_ability_score_choices(
        current_ability_scores=_ability_scores_from_definition(current_definition),
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
        strict=True,
    )
    feat_selections = _resolve_level_up_feat_selections(
        values,
        feat_catalog,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    new_feature_entries = _collect_progression_feature_entries_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    new_feature_entries.extend(level_up_feat_entries)
    new_feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(new_feature_entries)
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        base_ability_scores,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=True,
    )
    proficiency_bonus = _proficiency_bonus_for_level(target_level)
    existing_skill_proficiency_levels = _skill_proficiency_levels_from_rows(
        list(current_definition.skills or []),
        ability_scores=_ability_scores_from_definition(current_definition),
        proficiency_bonus=int(
            (current_definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(current_level)
        ),
    )
    campaign_option_proficiencies = collect_campaign_option_proficiency_grants(selected_campaign_option_payloads)
    for skill_name in (
        _extract_feat_skill_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("skills") or [])
    ):
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        existing_skill_proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
            existing_skill_proficiency_levels.get(normalized_skill),
            "proficient",
        )
    skills = _build_skills_payload_from_levels(
        ability_scores,
        existing_skill_proficiency_levels,
        proficiency_bonus,
    )

    new_features, _ = _build_feature_payloads(
        new_feature_entries,
        ability_scores=ability_scores,
        current_level=target_level,
    )
    merged_features = _merge_feature_payloads(list(current_definition.features or []), new_features)
    merged_features, derived_resource_templates = _apply_tracker_templates_to_feature_payloads(
        merged_features,
        ability_scores=ability_scores,
        current_level=target_level,
    )

    combined_selected_choices = _merge_selected_choice_maps(
        _extract_existing_feature_choice_map(current_definition),
        selected_choices,
    )
    item_catalog = _build_item_catalog([])
    item_catalog = dict(level_up_context.get("item_catalog") or item_catalog)
    attacks = _build_level_one_attacks(
        equipment_catalog=list(current_definition.equipment_catalog or []),
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=_dedupe_preserve_order(
            list((current_definition.proficiencies or {}).get("weapons") or [])
            + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
        ),
        selected_choices=combined_selected_choices,
        features=merged_features,
    )
    total_hp_delta = hp_gain + _feat_hit_point_bonus(
        feat_selections,
        current_level=target_level,
    )
    definition = CharacterDefinition(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        name=current_definition.name,
        status=current_definition.status,
        profile=_build_leveled_profile(
            current_definition=current_definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            target_level=target_level,
        ),
        stats=_build_leveled_stats(
            current_definition=current_definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            ability_scores=ability_scores,
            skills=skills,
            proficiency_bonus=proficiency_bonus,
            hp_gain=hp_gain,
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            current_level=target_level,
            equipment_catalog=list(current_definition.equipment_catalog or []),
            features=merged_features,
            item_catalog=item_catalog,
            selected_campaign_option_payloads=selected_campaign_option_payloads,
        ),
        skills=skills,
        proficiencies={
            "armor": _dedupe_preserve_order(
                list((current_definition.proficiencies or {}).get("armor") or [])
                + _extract_feat_armor_proficiencies(feat_selections, selected_choices)
                + list(campaign_option_proficiencies.get("armor") or [])
            ),
            "weapons": _dedupe_preserve_order(
                list((current_definition.proficiencies or {}).get("weapons") or [])
                + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
                + list(campaign_option_proficiencies.get("weapons") or [])
            ),
            "tools": _dedupe_preserve_order(
                list((current_definition.proficiencies or {}).get("tools") or [])
                + _extract_feat_tool_proficiencies(feat_selections, selected_choices)
                + list(campaign_option_proficiencies.get("tools") or [])
            ),
            "languages": _dedupe_preserve_order(
                list((current_definition.proficiencies or {}).get("languages") or [])
                + _extract_feat_language_proficiencies(feat_selections, selected_choices)
                + list(campaign_option_proficiencies.get("languages") or [])
            ),
        },
        attacks=attacks,
        features=merged_features,
        spellcasting=_build_level_up_spellcasting(
            current_definition=current_definition,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feat_selections=feat_selections,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            spell_catalog=spell_catalog,
            target_level=target_level,
            feature_entries=new_feature_entries,
            selected_campaign_option_payloads=selected_campaign_option_payloads,
        ),
        equipment_catalog=list(current_definition.equipment_catalog or []),
        reference_notes=dict(current_definition.reference_notes or {}),
        resource_templates=_merge_resource_templates(
            list(current_definition.resource_templates or []),
            derived_resource_templates,
        ),
        source=_build_leveled_source(
            current_definition.source,
            target_level,
            current_level=current_level,
            current_definition=current_definition,
            hp_gain=hp_gain,
            max_hp_delta=total_hp_delta,
        ),
    )
    definition = normalize_definition_to_native_model(
        definition,
        item_catalog=item_catalog,
        spell_catalog=spell_catalog,
        resolved_class=selected_class,
        resolved_subclass=selected_subclass,
        resolved_species=selected_species,
        resolved_background=selected_background,
    )
    import_metadata = _build_leveled_import_metadata(
        campaign_slug=campaign_slug,
        current_definition=current_definition,
        current_import_metadata=current_import_metadata,
        target_level=target_level,
    )
    return definition, import_metadata, total_hp_delta


def build_imported_progression_repair_context(
    systems_service: Any,
    campaign_slug: str,
    definition: CharacterDefinition,
    *,
    form_values: dict[str, str] | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if _character_source_type(definition) not in IMPORTED_CHARACTER_SOURCE_TYPES:
        raise CharacterBuildError("Only imported character sheets use the progression repair flow.")

    values = {key: str(value) for key, value in dict(form_values or {}).items()}
    current_level = max(_resolve_native_character_level(definition), 1)
    readiness = native_level_up_readiness(
        systems_service,
        campaign_slug,
        definition,
        campaign_page_records=campaign_page_records,
    )

    class_options = _list_supported_class_entries(systems_service, campaign_slug)
    species_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "race"),
        campaign_page_records or [],
        kind="species",
    )
    background_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "background"),
        campaign_page_records or [],
        kind="background",
    )
    feat_options = _build_mixed_character_options(
        _list_campaign_enabled_entries(systems_service, campaign_slug, "feat"),
        campaign_page_records or [],
        kind="feat",
    )
    optionalfeature_options = list(_list_campaign_enabled_entries(systems_service, campaign_slug, "optionalfeature"))

    selected_class = _resolve_profile_entry(
        class_options,
        definition.profile.get("class_ref"),
        fallback_title=_native_character_class_name(definition),
    )

    values.setdefault(
        "repair_class_slug",
        _entry_selection_value(selected_class) if selected_class is not None else "",
    )
    values.setdefault(
        "repair_species_slug",
        _entry_selection_value(
            _resolve_profile_entry(
                species_options,
                definition.profile.get("species_ref"),
                page_ref=definition.profile.get("species_page_ref"),
                fallback_title=str(definition.profile.get("species") or "").strip(),
            )
        )
        if species_options
        else "",
    )
    values.setdefault(
        "repair_background_slug",
        _entry_selection_value(
            _resolve_profile_entry(
                background_options,
                definition.profile.get("background_ref"),
                page_ref=definition.profile.get("background_page_ref"),
                fallback_title=str(definition.profile.get("background") or "").strip(),
            )
        )
        if background_options
        else "",
    )
    values.setdefault(
        "repair_subclass_slug",
        _entry_selection_value(
            _resolve_profile_entry(
                _list_subclass_options(systems_service, campaign_slug, selected_class) if selected_class is not None else [],
                definition.profile.get("subclass_ref") or dict((definition.profile.get("classes") or [{}])[0].get("subclass_ref") or {}),
                fallback_title=_native_character_subclass_name(definition),
            )
        )
        if selected_class is not None
        else "",
    )
    selected_class_for_values = _resolve_selected_entry(class_options, values.get("repair_class_slug", ""))
    subclass_options = (
        _list_subclass_options(systems_service, campaign_slug, selected_class_for_values)
        if selected_class_for_values is not None
        else []
    )

    feat_row_count = 2 if current_level >= 4 or any(str((feature.get("category") or "")).strip() == "feat" for feature in list(definition.features or [])) else 0
    optionalfeature_row_count = 3 if current_level >= 2 else 0
    feat_rows = []
    for index in range(1, feat_row_count + 1):
        field_name = f"repair_feat_{index}"
        feat_rows.append(
            {
                "index": index,
                "name": field_name,
                "selected": str(values.get(field_name) or "").strip(),
                "options": [_choice_option(_entry_option_label(entry), _entry_selection_value(entry) or entry.slug) for entry in feat_options],
            }
        )
    optionalfeature_rows = []
    for index in range(1, optionalfeature_row_count + 1):
        field_name = f"repair_optionalfeature_{index}"
        optionalfeature_rows.append(
            {
                "index": index,
                "name": field_name,
                "selected": str(values.get(field_name) or "").strip(),
                "options": [_choice_option(entry.title, str(entry.slug or "").strip()) for entry in optionalfeature_options if str(entry.slug or "").strip()],
            }
        )

    spell_rows = []
    selected_spell_class = _resolve_selected_entry(
        class_options,
        values.get("repair_class_slug") or (_entry_selection_value(selected_class) if selected_class is not None else ""),
    )
    for row in _build_imported_spell_repair_rows(definition, selected_class=selected_spell_class) if selected_spell_class is not None else []:
        field_name = str(row.get("field_name") or "").strip()
        if field_name:
            row = dict(row)
            row["selected"] = str(values.get(field_name) or row.get("selected") or "").strip()
            spell_rows.append(row)

    return {
        "values": values,
        "character_name": definition.name,
        "current_level": current_level,
        "readiness": readiness,
        "class_options": [_entry_option(entry) for entry in class_options],
        "species_options": [_entry_option(entry) for entry in species_options],
        "background_options": [_entry_option(entry) for entry in background_options],
        "subclass_options": [_entry_option(entry) for entry in subclass_options],
        "feat_rows": feat_rows,
        "optionalfeature_rows": optionalfeature_rows,
        "spell_rows": spell_rows,
        "class_entries": class_options,
        "species_entries": species_options,
        "background_entries": background_options,
        "subclass_entries": subclass_options,
        "feat_entries": feat_options,
        "optionalfeature_entries": optionalfeature_options,
        "systems_service": systems_service,
        "campaign_page_records": list(campaign_page_records or []),
        "item_catalog": dict(_build_common_builder_static_bundle(
            systems_service,
            campaign_slug,
            campaign_page_records=campaign_page_records,
        ).get("item_catalog") or {}),
        "spell_catalog": dict(_build_common_builder_static_bundle(
            systems_service,
            campaign_slug,
            campaign_page_records=campaign_page_records,
        ).get("spell_catalog") or {}),
    }


def apply_imported_progression_repairs(
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata,
    repair_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    if _character_source_type(current_definition) not in IMPORTED_CHARACTER_SOURCE_TYPES:
        raise CharacterBuildError("Only imported character sheets can use progression repair.")

    values = {key: str(value) for key, value in dict(form_values or {}).items()}
    class_entries = list(repair_context.get("class_entries") or [])
    species_entries = list(repair_context.get("species_entries") or [])
    background_entries = list(repair_context.get("background_entries") or [])
    subclass_entries = list(repair_context.get("subclass_entries") or [])
    feat_entries = list(repair_context.get("feat_entries") or [])
    optionalfeature_entries = list(repair_context.get("optionalfeature_entries") or [])

    selected_class = _resolve_selected_entry(class_entries, values.get("repair_class_slug", ""))
    selected_species = _resolve_selected_entry(species_entries, values.get("repair_species_slug", ""))
    selected_background = _resolve_selected_entry(background_entries, values.get("repair_background_slug", ""))
    selected_subclass = _resolve_selected_entry(subclass_entries, values.get("repair_subclass_slug", ""))

    missing_refs = []
    if selected_class is None:
        missing_refs.append("class")
    if selected_species is None:
        missing_refs.append("species")
    if selected_background is None:
        missing_refs.append("background")
    if missing_refs:
        joined = ", ".join(missing_refs)
        raise CharacterBuildError(f"Choose the missing {joined} links before saving progression repair.")

    ability_scores = _ability_scores_from_definition(current_definition)
    current_level = max(_resolve_native_character_level(current_definition), 1)

    repaired_feature_entries: list[dict[str, Any]] = []
    for row in list(repair_context.get("feat_rows") or []):
        selected_value = str(values.get(str(row.get("name") or "").strip()) or "").strip()
        selected_entry = _resolve_selected_entry(feat_entries, selected_value)
        if selected_entry is None:
            continue
        repaired_feature_entries.append(
            {
                "kind": "feat",
                "slug": str(selected_entry.slug or "").strip(),
                "title": selected_entry.title,
                "label": selected_entry.title,
                "systems_entry": selected_entry,
                "page_ref": _entry_page_ref(selected_entry),
                "campaign_option": _entry_campaign_option(selected_entry) or None,
            }
        )
    optionalfeature_lookup = {
        str(entry.slug or "").strip(): entry
        for entry in optionalfeature_entries
        if str(entry.slug or "").strip()
    }
    for row in list(repair_context.get("optionalfeature_rows") or []):
        selected_value = str(values.get(str(row.get("name") or "").strip()) or "").strip()
        selected_entry = optionalfeature_lookup.get(selected_value)
        if selected_entry is None:
            continue
        repaired_feature_entries.append(
            {
                "kind": "optionalfeature",
                "slug": str(selected_entry.slug or "").strip(),
                "label": selected_entry.title,
            }
        )

    repaired_features, _unused_templates = _build_feature_payloads(
        repaired_feature_entries,
        ability_scores=ability_scores,
        current_level=current_level,
    )
    merged_features = _merge_feature_payloads(list(current_definition.features or []), repaired_features)
    merged_features, derived_resource_templates = _apply_tracker_templates_to_feature_payloads(
        merged_features,
        ability_scores=ability_scores,
        current_level=current_level,
    )

    profile = dict(current_definition.profile or {})
    classes = [dict(row or {}) for row in list(profile.get("classes") or [])]
    class_payload = dict(classes[0] or {}) if classes else {}
    class_payload["class_name"] = selected_class.title
    class_payload["level"] = current_level
    class_payload["systems_ref"] = _systems_ref_from_entry(selected_class)
    if selected_subclass is not None:
        class_payload["subclass_name"] = selected_subclass.title
        class_payload["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
        profile["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
    classes = [class_payload]
    profile["classes"] = classes
    profile["class_ref"] = _systems_ref_from_entry(selected_class)
    profile["class_level_text"] = f"{selected_class.title} {current_level}"

    species_page_ref = _entry_page_ref(selected_species)
    profile["species"] = selected_species.title
    profile["species_ref"] = None if species_page_ref else _systems_ref_from_entry(selected_species)
    profile["species_page_ref"] = species_page_ref or None

    background_page_ref = _entry_page_ref(selected_background)
    profile["background"] = selected_background.title
    profile["background_ref"] = None if background_page_ref else _systems_ref_from_entry(selected_background)
    profile["background_page_ref"] = background_page_ref or None

    spellcasting = dict(current_definition.spellcasting or {})
    repaired_spells = [dict(payload or {}) for payload in list(spellcasting.get("spells") or [])]
    for row in list(repair_context.get("spell_rows") or []):
        field_name = str(row.get("field_name") or "").strip()
        if not field_name:
            continue
        selected_mark = str(values.get(field_name) or "").strip()
        if not selected_mark:
            continue
        spell_index = max(int(row.get("index") or 0) - 1, 0)
        if spell_index >= len(repaired_spells):
            continue
        repaired_spells[spell_index]["mark"] = selected_mark
    spellcasting["spells"] = _normalize_spell_payloads(repaired_spells)

    payload = deepcopy(current_definition.to_dict())
    payload["campaign_slug"] = campaign_slug
    payload["character_slug"] = current_definition.character_slug
    payload["profile"] = profile
    payload["features"] = merged_features
    payload["resource_templates"] = _merge_resource_templates(
        list(current_definition.resource_templates or []),
        derived_resource_templates,
    )
    payload["spellcasting"] = spellcasting
    payload["source"] = _with_native_progression_event(
        _seed_source_hp_baseline_from_definition(
            current_definition.source,
            current_definition,
            baseline_repaired=True,
        ),
        kind="repair",
        target_level=current_level,
        baseline_repaired=True,
    )

    definition = normalize_definition_to_native_model(
        CharacterDefinition.from_dict(payload),
        item_catalog=dict(repair_context.get("item_catalog") or {}),
        spell_catalog=dict(repair_context.get("spell_catalog") or {}),
        systems_service=repair_context.get("systems_service"),
        campaign_page_records=list(repair_context.get("campaign_page_records") or []),
        resolved_class=selected_class,
        resolved_subclass=selected_subclass,
        resolved_species=selected_species,
        resolved_background=selected_background,
    )
    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        source_path=str(
            current_import_metadata.source_path
            or (current_definition.source or {}).get("source_path")
            or f"managed://{campaign_slug}/{current_definition.character_slug}"
        ),
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="managed",
        warnings=list(current_import_metadata.warnings or []),
    )
    return definition, import_metadata


def _list_phb_entries(
    systems_service: Any,
    campaign_slug: str,
    entry_type: str,
) -> list[SystemsEntryRecord]:
    return [
        entry
        for entry in _list_campaign_enabled_entries(systems_service, campaign_slug, entry_type)
        if str(entry.source_id or "").strip().upper() == PHB_SOURCE_ID
    ]


def _builder_request_cache() -> dict[tuple[Any, ...], Any] | None:
    if not has_request_context():
        return None
    cache = getattr(g, "_character_builder_request_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    g._character_builder_request_cache = cache
    return cache


def _builder_cache_get(cache_key: tuple[Any, ...], build_value):
    cache = _builder_request_cache()
    if cache is None:
        return build_value()
    if cache_key not in cache:
        cache[cache_key] = build_value()
    return cache[cache_key]


def _builder_request_page_key(campaign_page_records: list[Any] | None) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                page_ref
                for page_ref in (
                    _extract_campaign_page_ref(record)
                    for record in list(campaign_page_records or [])
                )
                if page_ref
            }
        )
    )


def _sort_entries_for_builder(entries: list[SystemsEntryRecord]) -> list[SystemsEntryRecord]:
    deduped_entries: list[SystemsEntryRecord] = []
    seen_entry_keys: set[str] = set()
    for entry in list(entries or []):
        entry_key = str(entry.entry_key or "").strip()
        if entry_key and entry_key in seen_entry_keys:
            continue
        if entry_key:
            seen_entry_keys.add(entry_key)
        deduped_entries.append(entry)
    return sorted(
        deduped_entries,
        key=lambda entry: (
            normalize_lookup(entry.title),
            str(entry.source_id or "").strip().upper(),
            str(entry.slug or "").strip(),
        ),
    )


def _build_common_builder_static_bundle(
    systems_service: Any,
    campaign_slug: str,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    page_key = _builder_request_page_key(campaign_page_records)

    def _build_bundle() -> dict[str, Any]:
        page_records = list(campaign_page_records or [])
        class_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "class")
        subclass_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "subclass")
        race_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "race")
        background_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "background")
        feat_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "feat")
        optionalfeature_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "optionalfeature")
        item_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "item")
        spell_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "spell")
        species_options = _build_mixed_character_options(
            race_entries,
            page_records,
            kind="species",
        )
        background_options = _build_mixed_character_options(
            background_entries,
            page_records,
            kind="background",
        )
        feat_options = _build_mixed_character_options(
            feat_entries,
            page_records,
            kind="feat",
        )
        return {
            "class_entries": class_entries,
            "supported_class_entries": [
                entry for entry in class_entries if _supports_native_class_entry(entry)
            ],
            "subclass_entries": subclass_entries,
            "species_options": species_options,
            "background_options": background_options,
            "feat_options": feat_options,
            "feat_catalog": _build_feat_catalog(feat_options),
            "optionalfeature_catalog": _build_entry_slug_catalog(optionalfeature_entries),
            "item_catalog": _build_item_catalog(item_entries),
            "spell_catalog": _build_spell_catalog(spell_entries),
            "campaign_feature_options": _build_campaign_page_choice_options(
                page_records,
                include_items=False,
            ),
            "campaign_item_options": _build_campaign_page_choice_options(
                page_records,
                include_items=True,
            ),
        }

    return dict(
        _builder_cache_get(
            ("builder-static-bundle", campaign_slug, page_key),
            _build_bundle,
        )
    )


def _class_progression_for_builder(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    return list(
        _builder_cache_get(
            ("class-progression", campaign_slug, str(selected_class.entry_key or "").strip()),
            lambda: systems_service.build_class_feature_progression_for_class_entry(campaign_slug, selected_class),
        )
        or []
    )


def _subclass_progression_for_builder(
    systems_service: Any,
    campaign_slug: str,
    selected_subclass: SystemsEntryRecord | None,
) -> list[dict[str, Any]]:
    if selected_subclass is None:
        return []
    return list(
        _builder_cache_get(
            ("subclass-progression", campaign_slug, str(selected_subclass.entry_key or "").strip()),
            lambda: systems_service.build_subclass_feature_progression_for_subclass_entry(campaign_slug, selected_subclass),
        )
        or []
    )


def _list_supported_class_entries(
    systems_service: Any,
    campaign_slug: str,
) -> list[SystemsEntryRecord]:
    static_bundle = _build_common_builder_static_bundle(systems_service, campaign_slug)
    return list(static_bundle.get("supported_class_entries") or [])


def _supports_native_class_entry(entry: SystemsEntryRecord | None) -> bool:
    if not isinstance(entry, SystemsEntryRecord):
        return False
    metadata = dict(entry.metadata or {})
    if not str(entry.title or "").strip() or not metadata.get("hit_die"):
        return False
    if str(entry.source_id or "").strip().upper() == PHB_SOURCE_ID:
        return True
    progression = _class_spell_progression(str(entry.title or "").strip(), selected_class=entry)
    return any(
        progression.get(key)
        for key in (
            "spellcasting_ability",
            "caster_progression",
            "prepared_spells",
            "prepared_spells_change",
            "cantrip_progression",
            "spells_known_progression",
            "spells_known_progression_fixed",
            "prepared_spells_progression",
            "slot_progression",
        )
    )


def _list_campaign_enabled_entries(
    systems_service: Any,
    campaign_slug: str,
    entry_type: str,
) -> list[SystemsEntryRecord]:
    def _load_entries() -> list[SystemsEntryRecord]:
        list_enabled_entries = getattr(systems_service, "list_enabled_entries_for_campaign", None)
        if callable(list_enabled_entries):
            return _sort_entries_for_builder(
                list_enabled_entries(
                    campaign_slug,
                    entry_type=entry_type,
                    limit=None,
                )
            )

        library = systems_service.get_campaign_library(campaign_slug)
        if library is None:
            return []
        enabled_source_ids = [
            str(row.source.source_id or "").strip()
            for row in list(systems_service.list_campaign_source_states(campaign_slug) or [])
            if getattr(row, "is_enabled", False) and str(getattr(row.source, "source_id", "") or "").strip()
        ]
        if not enabled_source_ids:
            return []

        entries: list[SystemsEntryRecord] = []
        for source_id in enabled_source_ids:
            entries.extend(
                systems_service.list_entries_for_campaign_source(
                    campaign_slug,
                    source_id,
                    entry_type=entry_type,
                    limit=None,
                )
            )
        is_entry_enabled = getattr(systems_service, "is_entry_enabled_for_campaign", None)
        if callable(is_entry_enabled):
            entries = [
                entry
                for entry in entries
                if is_entry_enabled(campaign_slug, entry)
            ]
        return _sort_entries_for_builder(entries)

    return list(
        _builder_cache_get(
            ("enabled-entries", campaign_slug, entry_type),
            _load_entries,
        )
        or []
    )


def _list_subclass_options(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
    *,
    subclass_entries: list[SystemsEntryRecord] | None = None,
) -> list[SystemsEntryRecord]:
    if selected_class is None:
        return []
    options = list(subclass_entries or _list_campaign_enabled_entries(systems_service, campaign_slug, "subclass"))
    return [
        entry
        for entry in options
        if str(entry.metadata.get("class_name") or "").strip() == selected_class.title
        and str(entry.metadata.get("class_source") or "").strip().upper() == selected_class.source_id
    ]


def _build_mixed_character_options(
    systems_entries: list[SystemsEntryRecord],
    campaign_page_records: list[Any],
    *,
    kind: str,
) -> list[SystemsEntryRecord]:
    options = list(systems_entries or [])
    options.extend(_build_campaign_page_entries(campaign_page_records, kind=kind))
    return options


def _build_campaign_page_entries(
    campaign_page_records: list[Any],
    *,
    kind: str,
) -> list[SystemsEntryRecord]:
    entries: list[SystemsEntryRecord] = []
    seen_page_refs: set[str] = set()
    for record in list(campaign_page_records or []):
        entry = _build_campaign_page_entry(record, kind=kind)
        if entry is None:
            continue
        page_ref = _entry_page_ref(entry)
        if page_ref in seen_page_refs:
            continue
        seen_page_refs.add(page_ref)
        entries.append(entry)
    return sorted(entries, key=lambda entry: (normalize_lookup(entry.title), _entry_page_ref(entry)))


def _build_campaign_page_entry(
    record: Any,
    *,
    kind: str,
) -> SystemsEntryRecord | None:
    page_ref = _extract_campaign_page_ref(record)
    page = getattr(record, "page", None)
    if not page_ref or page is None:
        return None
    section = str(getattr(page, "section", "") or "").strip()
    if section == CAMPAIGN_SESSIONS_SECTION:
        return None

    campaign_option = build_campaign_page_character_option(
        record,
        default_kind="item" if section == CAMPAIGN_ITEMS_SECTION else "feature",
    )
    if not isinstance(campaign_option, dict):
        return None
    if str(campaign_option.get("kind") or "").strip() != kind:
        return None
    if not _campaign_page_option_allowed_for_mixed_source(
        record,
        kind=kind,
    ):
        return None

    title = str(campaign_option.get("display_name") or getattr(page, "title", "") or page_ref).strip() or page_ref
    entry_type = {
        "feat": "feat",
        "species": "race",
        "background": "background",
    }.get(kind, kind)
    metadata: dict[str, Any] = {
        "page_ref": page_ref,
        "campaign_option": deepcopy(campaign_option),
    }
    if kind == "feat":
        for key in (
            "ability",
            "skill_proficiencies",
            "language_proficiencies",
            "tool_proficiencies",
            "weapon_proficiencies",
            "armor_proficiencies",
            "saving_throw_proficiencies",
            "skill_tool_language_proficiencies",
            "optionalfeature_progression",
            "additional_spells",
            "spell_support",
            "modeled_effects",
        ):
            if key in campaign_option:
                metadata[key] = deepcopy(campaign_option.get(key))
    elif kind == "species":
        for key in ("size", "speed", "languages", "skill_proficiencies", "tool_proficiencies", "feats", "spell_support"):
            if key in campaign_option:
                metadata[key] = deepcopy(campaign_option.get(key))
    elif kind == "background":
        for key in ("skill_proficiencies", "language_proficiencies", "tool_proficiencies", "spell_support"):
            if key in campaign_option:
                metadata[key] = deepcopy(campaign_option.get(key))

    now = utcnow()
    return SystemsEntryRecord(
        id=0,
        library_slug="campaign-pages",
        source_id=CAMPAIGN_PAGE_SOURCE_ID,
        entry_key=f"campaign-page|{entry_type}|{page_ref}",
        entry_type=entry_type,
        slug=f"campaign-page-{slugify(page_ref)}",
        title=title,
        source_page="",
        source_path=page_ref,
        search_text=" ".join(
            part
            for part in (
                title,
                str(getattr(page, "summary", "") or "").strip(),
                section,
                str(getattr(page, "subsection", "") or "").strip(),
            )
            if part
        ).casefold(),
        player_safe_default=True,
        dm_heavy=False,
        metadata=metadata,
        body={"entries": []},
        rendered_html="",
        created_at=now,
        updated_at=now,
    )


def _campaign_page_option_allowed_for_mixed_source(
    record: Any,
    *,
    kind: str,
) -> bool:
    if kind not in CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND:
        return True
    page = getattr(record, "page", None)
    if page is None:
        return False
    section = str(getattr(page, "section", "") or "").strip()
    if section != CAMPAIGN_MECHANICS_SECTION:
        return False
    subsection = normalize_lookup(str(getattr(page, "subsection", "") or "").strip())
    if not subsection:
        return True
    return subsection in CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND.get(kind, set())


def _entry_page_ref(entry: Any) -> str:
    metadata = dict((getattr(entry, "metadata", None) or {}) if not isinstance(entry, dict) else (entry.get("metadata") or {}))
    return str(
        metadata.get("page_ref")
        or (entry.get("page_ref") if isinstance(entry, dict) else "")
        or ""
    ).strip()


def _entry_campaign_option(entry: Any) -> dict[str, Any]:
    metadata = dict((getattr(entry, "metadata", None) or {}) if not isinstance(entry, dict) else (entry.get("metadata") or {}))
    campaign_option = dict(metadata.get("campaign_option") or {})
    if campaign_option:
        return campaign_option
    if isinstance(entry, dict) and isinstance(entry.get("campaign_option"), dict):
        return dict(entry.get("campaign_option") or {})
    return {}


def _entry_selection_value(entry: Any) -> str:
    page_ref = _entry_page_ref(entry)
    if page_ref:
        return f"{CAMPAIGN_PAGE_OPTION_PREFIX}{page_ref}"
    slug = _entry_option_slug(entry)
    if slug:
        return f"{SYSTEMS_OPTION_PREFIX}{slug}"
    return ""


def _resolve_selected_entry(
    options: list[SystemsEntryRecord],
    selected_slug: str,
) -> SystemsEntryRecord | None:
    cleaned_slug = str(selected_slug or "").strip()
    if cleaned_slug:
        for entry in options:
            if cleaned_slug in {
                entry.slug,
                _entry_selection_value(entry),
                _entry_page_ref(entry),
            }:
                return entry
            if cleaned_slug == f"{SYSTEMS_OPTION_PREFIX}{entry.slug}" and entry.slug:
                return entry
        return None
    return options[0] if options else None


def _entry_option(entry: SystemsEntryRecord) -> dict[str, str]:
    return {
        "slug": entry.slug,
        "value": _entry_selection_value(entry) or entry.slug,
        "title": entry.title,
        "source_id": entry.source_id,
        "page_ref": _entry_page_ref(entry),
        "campaign_option": _entry_campaign_option(entry) or None,
        "label": _entry_option_label(entry),
    }


def _entry_option_title(entry: Any) -> str:
    if isinstance(entry, SystemsEntryRecord):
        return str(entry.title or "").strip()
    if isinstance(entry, dict):
        return str(entry.get("title") or "").strip()
    return ""


def _entry_option_label(entry: Any) -> str:
    title = _entry_option_title(entry)
    if _entry_page_ref(entry):
        return f"{title} (Campaign)" if title else "Campaign"
    source_id = _entry_option_source_id(entry)
    if title and source_id and str(source_id).strip().upper() != PHB_SOURCE_ID:
        return f"{title} ({source_id})"
    return title


def _entry_option_slug(entry: Any) -> str:
    if isinstance(entry, SystemsEntryRecord):
        return str(entry.slug or "").strip()
    if isinstance(entry, dict):
        return str(entry.get("slug") or "").strip()
    return ""


def _entry_option_source_id(entry: Any) -> str:
    if isinstance(entry, SystemsEntryRecord):
        return str(entry.source_id or "").strip()
    if isinstance(entry, dict):
        return str(entry.get("source_id") or "").strip()
    return ""


def _systems_ref_slug(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("slug") or "").strip()


def _has_profile_entry_link(
    systems_ref: Any,
    *,
    page_ref: Any = None,
) -> bool:
    return bool(_systems_ref_slug(systems_ref) or _extract_campaign_page_ref(page_ref))


def _resolve_profile_entry(
    options: list[SystemsEntryRecord],
    systems_ref: Any,
    *,
    page_ref: Any = None,
    fallback_title: str = "",
) -> SystemsEntryRecord | None:
    selected_page_ref = _extract_campaign_page_ref(page_ref)
    if selected_page_ref:
        resolved = next((entry for entry in options if _entry_page_ref(entry) == selected_page_ref), None)
        if resolved is not None:
            return resolved
    selected_slug = _systems_ref_slug(systems_ref)
    if selected_slug:
        resolved = _resolve_selected_entry(options, selected_slug)
        if resolved is not None:
            return resolved
    normalized_title = normalize_lookup(fallback_title)
    if not normalized_title:
        return None
    return next((entry for entry in options if normalize_lookup(entry.title) == normalized_title), None)


def _resolve_definition_sheet_entries(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
) -> dict[str, SystemsEntryRecord | None]:
    selected_class = resolved_class if isinstance(resolved_class, SystemsEntryRecord) else None
    selected_subclass = resolved_subclass if isinstance(resolved_subclass, SystemsEntryRecord) else None
    selected_species = resolved_species if isinstance(resolved_species, SystemsEntryRecord) else None
    selected_background = resolved_background if isinstance(resolved_background, SystemsEntryRecord) else None
    if systems_service is None:
        return {
            "selected_class": selected_class,
            "selected_subclass": selected_subclass,
            "selected_species": selected_species,
            "selected_background": selected_background,
        }

    static_bundle = _build_common_builder_static_bundle(
        systems_service,
        definition.campaign_slug,
        campaign_page_records=campaign_page_records,
    )
    classes = [dict(row or {}) for row in list((definition.profile or {}).get("classes") or [])]
    class_payload = dict(classes[0] or {}) if classes else {}
    if selected_class is None:
        selected_class = _resolve_profile_entry(
            list(static_bundle.get("supported_class_entries") or []),
            (definition.profile or {}).get("class_ref") or class_payload.get("systems_ref"),
            fallback_title=_native_character_class_name(definition),
        )
    if selected_species is None:
        selected_species = _resolve_profile_entry(
            list(static_bundle.get("species_options") or []),
            (definition.profile or {}).get("species_ref"),
            page_ref=(definition.profile or {}).get("species_page_ref"),
            fallback_title=str((definition.profile or {}).get("species") or "").strip(),
        )
    if selected_background is None:
        selected_background = _resolve_profile_entry(
            list(static_bundle.get("background_options") or []),
            (definition.profile or {}).get("background_ref"),
            page_ref=(definition.profile or {}).get("background_page_ref"),
            fallback_title=str((definition.profile or {}).get("background") or "").strip(),
        )
    if selected_subclass is None and selected_class is not None:
        subclass_options = _list_subclass_options(
            systems_service,
            definition.campaign_slug,
            selected_class,
            subclass_entries=list(static_bundle.get("subclass_entries") or []),
        )
        selected_subclass = _resolve_profile_entry(
            subclass_options,
            (definition.profile or {}).get("subclass_ref") or class_payload.get("subclass_ref"),
            fallback_title=_native_character_subclass_name(definition),
        )
    return {
        "selected_class": selected_class,
        "selected_subclass": selected_subclass,
        "selected_species": selected_species,
        "selected_background": selected_background,
    }


def _effective_item_catalog_for_definition(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if item_catalog:
        return dict(item_catalog)
    if systems_service is not None:
        static_bundle = _build_common_builder_static_bundle(
            systems_service,
            definition.campaign_slug,
            campaign_page_records=campaign_page_records,
        )
        resolved_catalog = dict(static_bundle.get("item_catalog") or {})
        if resolved_catalog:
            return resolved_catalog
    return _build_item_catalog([])


def _effective_spell_catalog_for_definition(
    definition: CharacterDefinition,
    *,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if spell_catalog:
        return dict(spell_catalog)
    if systems_service is not None:
        static_bundle = _build_common_builder_static_bundle(
            systems_service,
            definition.campaign_slug,
            campaign_page_records=campaign_page_records,
        )
        resolved_catalog = dict(static_bundle.get("spell_catalog") or {})
        if resolved_catalog:
            return resolved_catalog
    return _build_spell_catalog([])


def _definition_spellcasting_class_name(definition: CharacterDefinition) -> str:
    spellcasting_class = str((definition.spellcasting or {}).get("spellcasting_class") or "").strip()
    if spellcasting_class:
        return spellcasting_class
    class_name = _native_character_class_name(definition)
    if class_name:
        return class_name
    class_level_text = str((definition.profile or {}).get("class_level_text") or "").strip()
    match = re.match(r"([A-Za-z][A-Za-z' -]+)", class_level_text)
    return str(match.group(1) or "").strip() if match is not None else ""


def _infer_definition_save_proficiencies(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    selected_class: SystemsEntryRecord | None = None,
) -> set[str]:
    save_proficiencies = set(_class_save_proficiencies(selected_class))
    if proficiency_bonus <= 0:
        return save_proficiencies
    ability_payloads = dict((definition.stats or {}).get("ability_scores") or {})
    save_bonus_map = (
        _effect_save_bonus_map(_extract_character_effect_keys(list(definition.features or [])))
        if selected_class is not None
        else {}
    )
    for ability_key in ABILITY_KEYS:
        try:
            save_bonus = int(
                dict(
                    ability_payloads.get(ability_key)
                    or ability_payloads.get(str(ABILITY_LABELS.get(ability_key, "")).lower())
                    or {}
                ).get("save_bonus")
            )
        except (TypeError, ValueError):
            continue
        inferred_bonus = save_bonus - int(save_bonus_map.get(ability_key) or 0)
        if inferred_bonus - _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) >= proficiency_bonus:
            save_proficiencies.add(ability_key)
    return save_proficiencies


def _definition_base_stats_without_adjustments(definition: CharacterDefinition) -> dict[str, Any]:
    stats, _manual_adjustments = strip_manual_stat_adjustments(dict(definition.stats or {}))
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    return stats


def _extract_character_effect_keys(features: list[dict[str, Any]] | None) -> list[str]:
    results: list[str] = []
    for feature in list(features or []):
        results.extend(_effect_keys_for_feature(feature))
    return _dedupe_preserve_order(results)


def _split_effect_key(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").strip().split(":") if part.strip()]


def _parse_effect_skill_names(value: Any) -> list[str]:
    results: list[str] = []
    for raw_skill in str(value or "").split(","):
        normalized_skill = normalize_lookup(raw_skill)
        if normalized_skill in SKILL_LABELS:
            results.append(normalized_skill)
    return _dedupe_preserve_order(results)


def _parse_effect_ability_keys(value: Any) -> list[str]:
    results: list[str] = []
    for raw_ability in str(value or "").split(","):
        normalized_ability = normalize_lookup(raw_ability)
        if normalized_ability in ABILITY_KEYS:
            results.append(normalized_ability)
    return _dedupe_preserve_order(results)


def _skill_targets_for_effect_key(effect_key: Any) -> list[str]:
    parts = _split_effect_key(effect_key)
    if len(parts) < 2 or normalize_lookup(parts[0]) != normalize_lookup("half-proficiency"):
        return []
    target_kind = normalize_lookup(parts[1])
    if target_kind == normalize_lookup("all"):
        return list(SKILL_LABELS.keys())
    if target_kind == normalize_lookup("skills") and len(parts) >= 3:
        return _parse_effect_skill_names(parts[2])
    if target_kind == normalize_lookup("abilities") and len(parts) >= 3:
        ability_keys = set(_parse_effect_ability_keys(parts[2]))
        return [
            normalized_skill
            for normalized_skill, ability_key in SKILL_ABILITY_KEYS.items()
            if ability_key in ability_keys
        ]
    return []


def _initiative_half_proficiency_bonus(effect_keys: list[str], *, proficiency_bonus: int) -> int:
    half_bonus = proficiency_bonus // 2
    if half_bonus <= 0:
        return 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) < 2 or normalize_lookup(parts[0]) != normalize_lookup("half-proficiency"):
            continue
        target_kind = normalize_lookup(parts[1])
        if target_kind == normalize_lookup("all"):
            return half_bonus
        if target_kind == normalize_lookup("abilities") and len(parts) >= 3:
            if "dex" in set(_parse_effect_ability_keys(parts[2])):
                return half_bonus
    return 0


def _effect_skill_bonus_map(effect_keys: list[str]) -> dict[str, int]:
    bonuses: dict[str, int] = {}
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 3 or normalize_lookup(parts[0]) != normalize_lookup("skill-bonus"):
            continue
        normalized_skill = normalize_lookup(parts[1])
        if normalized_skill not in SKILL_LABELS:
            continue
        try:
            bonus = int(parts[2])
        except ValueError:
            continue
        bonuses[normalized_skill] = int(bonuses.get(normalized_skill) or 0) + bonus
    return bonuses


def _effect_save_bonus_map(effect_keys: list[str]) -> dict[str, int]:
    bonuses: dict[str, int] = {}
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) < 3 or normalize_lookup(parts[0]) != normalize_lookup("save-bonus"):
            continue
        target_kind = normalize_lookup(parts[1])
        target_ability_keys: list[str] = []
        raw_bonus = ""
        if target_kind == normalize_lookup("all") and len(parts) == 3:
            target_ability_keys = list(ABILITY_KEYS)
            raw_bonus = parts[2]
        elif target_kind == normalize_lookup("abilities") and len(parts) == 4:
            target_ability_keys = _parse_effect_ability_keys(parts[2])
            raw_bonus = parts[3]
        if not target_ability_keys:
            continue
        try:
            bonus = int(raw_bonus)
        except ValueError:
            continue
        for ability_key in target_ability_keys:
            bonuses[ability_key] = int(bonuses.get(ability_key) or 0) + bonus
    return bonuses


def _effect_passive_bonus(effect_keys: list[str], *, skill_name: str) -> int:
    normalized_skill = normalize_lookup(skill_name)
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 3 or normalize_lookup(parts[0]) != normalize_lookup("passive-bonus"):
            continue
        if normalize_lookup(parts[1]) != normalized_skill:
            continue
        try:
            bonus += int(parts[2])
        except ValueError:
            continue
    return bonus


def _effect_initiative_bonus(effect_keys: list[str], *, proficiency_bonus: int) -> int:
    bonus = _initiative_half_proficiency_bonus(effect_keys, proficiency_bonus=proficiency_bonus)
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("initiative-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus


def _effect_speed_bonus(effect_keys: list[str]) -> int:
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("speed-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus


def _effect_weapon_attack_bonus(effect_keys: list[str]) -> int:
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("weapon-attack-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus


def _effect_weapon_damage_bonus(effect_keys: list[str]) -> int:
    bonus = 0
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 2 or normalize_lookup(parts[0]) != normalize_lookup("weapon-damage-bonus"):
            continue
        try:
            bonus += int(parts[1])
        except ValueError:
            continue
    return bonus


def _attack_mode_component_sort_key(component: str) -> tuple[int, str]:
    clean_component = str(component or "").strip().casefold()
    if clean_component.startswith(f"{ATTACK_MODE_EFFECT_PREFIX}:"):
        return (55, clean_component)
    return (int(ATTACK_MODE_COMPONENT_PRIORITY.get(clean_component, 999)), clean_component)


def _normalize_attack_mode_key(value: Any) -> str:
    if isinstance(value, str):
        raw_components = value.split("|")
    elif isinstance(value, (list, tuple, set)):
        raw_components = list(value)
    else:
        return ""
    components: list[str] = []
    seen: set[str] = set()
    for raw_component in raw_components:
        clean_component = str(raw_component or "").strip().casefold()
        if not clean_component or clean_component in seen:
            continue
        seen.add(clean_component)
        components.append(clean_component)
    return "|".join(sorted(components, key=_attack_mode_component_sort_key))


def _attack_mode_components(mode_key: Any) -> list[str]:
    normalized_mode_key = _normalize_attack_mode_key(mode_key)
    if not normalized_mode_key:
        return []
    return [component for component in normalized_mode_key.split("|") if component]


def _attack_mode_component_label(component: Any) -> str:
    clean_component = str(component or "").strip().casefold()
    label = str(ATTACK_MODE_COMPONENT_LABELS.get(clean_component) or "").strip()
    if label:
        return label
    prefix = f"{ATTACK_MODE_EFFECT_PREFIX}:"
    if clean_component.startswith(prefix):
        parts = clean_component.split(":")
        if len(parts) >= 4:
            return parts[3].replace("-", " ").strip()
    return ""


def _attack_variant_label_from_mode_key(mode_key: Any) -> str:
    labels: list[str] = []
    for component in _attack_mode_components(mode_key):
        label = _attack_mode_component_label(component)
        if not label:
            return ""
        labels.append(label)
    return ", ".join(labels)


def _attack_name_suffix(variant_label: str) -> str:
    clean_label = str(variant_label or "").strip()
    if not clean_label:
        return ""
    return f" ({clean_label})"


def _extract_attack_name_suffix_label(name: Any) -> str:
    clean_name = str(name or "").strip()
    if not clean_name:
        return ""
    match = ATTACK_NAME_SUFFIX_PATTERN.search(clean_name)
    if match is None:
        return ""
    return str(match.group(1) or "").strip()


def _legacy_attack_mode_component(label: str, *, notes: str = "") -> str:
    normalized_label = normalize_lookup(label)
    if not normalized_label:
        return ""
    component_map = {
        normalize_lookup("thrown"): ATTACK_MODE_WEAPON_THROWN,
        normalize_lookup("two-handed"): ATTACK_MODE_WEAPON_TWO_HANDED,
        normalize_lookup("off-hand"): ATTACK_MODE_WEAPON_OFF_HAND,
        normalize_lookup("crossbow expert"): ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS,
        normalize_lookup("great weapon master"): ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER,
        normalize_lookup("polearm master"): ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS,
        normalize_lookup("sharpshooter"): ATTACK_MODE_FEAT_SHARPSHOOTER,
    }
    if normalized_label == normalize_lookup("charger"):
        normalized_notes = normalize_lookup(notes)
        if normalize_lookup("+1d8 damage") in normalized_notes or normalize_lookup("once per turn") in normalized_notes:
            return ATTACK_MODE_FEAT_CHARGER_XPHB
        return ATTACK_MODE_FEAT_CHARGER_PHB
    return str(component_map.get(normalized_label) or "")


def _attack_mode_key_from_variant_label(variant_label: Any, *, notes: Any = "") -> str:
    raw_label = str(variant_label or "").strip()
    if not raw_label:
        return ""
    components: list[str] = []
    for label in [part.strip() for part in raw_label.split(",") if part.strip()]:
        component = _legacy_attack_mode_component(label, notes=str(notes or ""))
        if not component:
            return ""
        components.append(component)
    return _normalize_attack_mode_key(components)


def _normalize_attack_variant_label(
    *,
    raw_variant_label: Any,
    mode_key: Any,
    attack_name: Any,
    notes: Any,
) -> str:
    clean_variant_label = str(raw_variant_label or "").strip()
    if clean_variant_label:
        inferred_mode_key = _attack_mode_key_from_variant_label(clean_variant_label, notes=notes)
        if inferred_mode_key:
            return _attack_variant_label_from_mode_key(inferred_mode_key)
        return clean_variant_label
    canonical_variant_label = _attack_variant_label_from_mode_key(mode_key)
    if canonical_variant_label:
        return canonical_variant_label
    inferred_suffix_label = _extract_attack_name_suffix_label(attack_name)
    inferred_mode_key = _attack_mode_key_from_variant_label(inferred_suffix_label, notes=notes)
    if inferred_mode_key:
        return _attack_variant_label_from_mode_key(inferred_mode_key)
    return ""


def _effect_attack_mode_component(*, target_kind: str, variant_label: str) -> str:
    clean_target_kind = normalize_lookup(target_kind)
    clean_variant_label = str(variant_label or "").strip()
    if clean_target_kind not in ATTACK_MODE_EFFECT_TARGETS or not clean_variant_label:
        return ""
    label_slug = slugify(clean_variant_label)
    if not label_slug:
        return ""
    return f"{ATTACK_MODE_EFFECT_PREFIX}:{clean_target_kind}:{label_slug}"


def _normalize_attack_mode_extra_damage(value: Any) -> str:
    clean_value = str(value or "").strip()
    if normalize_lookup(clean_value) in {"", "0", "none", "no", "false", "n-a", "na"}:
        return ""
    return clean_value


def _attack_mode_note_text(
    *,
    variant_label: str,
    attack_delta: int,
    damage_delta: int,
    extra_damage: str,
) -> str:
    clean_label = str(variant_label or "").strip()
    adjustments: list[str] = []
    if attack_delta:
        adjustments.append(f"{attack_delta:+d} attack")
    if damage_delta:
        adjustments.append(f"{damage_delta:+d} damage")
    if extra_damage:
        adjustments.append(f"+{extra_damage} damage")
    if not clean_label:
        return ""
    if not adjustments:
        return clean_label.title()
    return f"{clean_label.title()} ({', '.join(adjustments)})"


def _effect_attack_mode_descriptors(effect_keys: list[str]) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    seen_descriptors: set[tuple[str, int, int, str]] = set()
    for effect_key in list(effect_keys or []):
        parts = _split_effect_key(effect_key)
        if len(parts) != 6 or normalize_lookup(parts[0]) != normalize_lookup("attack-mode"):
            continue
        target_kind = normalize_lookup(parts[1])
        variant_label = str(parts[2] or "").strip()
        if target_kind not in ATTACK_MODE_EFFECT_TARGETS or not variant_label:
            continue
        try:
            attack_delta = int(parts[3])
            damage_delta = int(parts[4])
        except ValueError:
            continue
        extra_damage = _normalize_attack_mode_extra_damage(parts[5])
        if attack_delta == 0 and damage_delta == 0 and not extra_damage:
            continue
        mode_component = _effect_attack_mode_component(target_kind=target_kind, variant_label=variant_label)
        descriptor_key = (mode_component, attack_delta, damage_delta, extra_damage)
        if not mode_component or descriptor_key in seen_descriptors:
            continue
        seen_descriptors.add(descriptor_key)
        descriptors.append(
            {
                "target_kind": target_kind,
                "variant_label": _attack_mode_component_label(mode_component),
                "attack_delta": attack_delta,
                "damage_delta": damage_delta,
                "extra_damage": extra_damage,
                "mode_component": mode_component,
                "note": _attack_mode_note_text(
                    variant_label=variant_label,
                    attack_delta=attack_delta,
                    damage_delta=damage_delta,
                    extra_damage=extra_damage,
                ),
            }
        )
    return descriptors


def _combine_attack_extra_damage(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        clean_value = _normalize_attack_mode_extra_damage(value)
        if clean_value:
            parts.append(clean_value)
    return "+".join(parts)


def _append_attack_note_text(base_notes: Any, extra_note: Any) -> str:
    base_text = str(base_notes or "").strip().rstrip(".")
    extra_text = str(extra_note or "").strip().rstrip(".")
    if not base_text:
        return f"{extra_text}." if extra_text else ""
    if not extra_text:
        return f"{base_text}."
    if normalize_lookup(extra_text) in normalize_lookup(base_text):
        return f"{base_text}."
    return f"{base_text}, {extra_text}."


def _attack_mode_descriptor_applies_to_context(
    descriptor: dict[str, Any],
    context: dict[str, Any],
    *,
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> bool:
    target_kind = normalize_lookup(str(descriptor.get("target_kind") or "").strip())
    if not target_kind:
        return False
    if target_kind == ATTACK_MODE_TARGET_ALL:
        return True
    profile = dict(profile_override or context.get("profile") or {})
    effective_category = normalize_lookup(category_override or _weapon_attack_category(profile))
    if target_kind == ATTACK_MODE_TARGET_MELEE:
        return effective_category == normalize_lookup("melee weapon")
    if target_kind == ATTACK_MODE_TARGET_RANGED:
        return effective_category == normalize_lookup("ranged weapon")
    if target_kind == ATTACK_MODE_TARGET_FIREARM:
        return _weapon_uses_firearm_proficiency(profile, attack_name=str(context.get("attack_name") or "").strip())
    return False


def _infer_attack_mode_key_from_payload(payload: dict[str, Any]) -> str:
    explicit_mode_key = _normalize_attack_mode_key(payload.get("mode_key"))
    if explicit_mode_key:
        return explicit_mode_key
    variant_label_mode_key = _attack_mode_key_from_variant_label(
        payload.get("variant_label"),
        notes=payload.get("notes"),
    )
    if variant_label_mode_key:
        return variant_label_mode_key
    return _attack_mode_key_from_variant_label(
        _extract_attack_name_suffix_label(payload.get("name")),
        notes=payload.get("notes"),
    )


def _extract_attack_feature_slugs(features: list[dict[str, Any]] | None) -> set[str]:
    slugs: set[str] = set()
    for feature in list(features or []):
        systems_ref = dict(feature.get("systems_ref") or {})
        slug = normalize_lookup(str(systems_ref.get("slug") or "").strip())
        if slug:
            slugs.add(slug)
    return slugs


def _collect_attack_support_flags(features: list[dict[str, Any]] | None) -> dict[str, bool]:
    feature_slugs = _extract_attack_feature_slugs(features)
    effect_keys = {
        normalize_lookup(str(value or "").strip())
        for value in _extract_character_effect_keys(features)
        if str(value or "").strip()
    }

    def has_slug(*raw_slugs: str) -> bool:
        return any(normalize_lookup(raw_slug) in feature_slugs for raw_slug in raw_slugs if str(raw_slug or "").strip())

    return {
        "charger_phb": has_slug("phb-feat-charger") or normalize_lookup("charger-phb") in effect_keys,
        "charger_xphb": has_slug("xphb-feat-charger") or normalize_lookup("charger-xphb") in effect_keys,
        "crossbow_expert": has_slug("phb-feat-crossbow-expert"),
        "dual_wielder": has_slug("phb-feat-dual-wielder"),
        "great_weapon_master": has_slug("phb-feat-great-weapon-master"),
        "gunner": has_slug("tce-feat-gunner"),
        "martial_adept": has_slug("phb-feat-martial-adept"),
        "polearm_master": has_slug("phb-feat-polearm-master"),
        "savage_attacker": has_slug("phb-feat-savage-attacker"),
        "sharpshooter": has_slug("phb-feat-sharpshooter"),
        "tavern_brawler": has_slug("phb-feat-tavern-brawler", "xphb-feat-tavern-brawler")
        or normalize_lookup("tavern-brawler") in effect_keys,
    }


def _derive_definition_max_hp(
    definition: CharacterDefinition,
    *,
    current_level: int,
) -> int | None:
    hp_baseline = _native_progression_hp_baseline(definition.source)
    if hp_baseline is None:
        return None
    baseline_level = int(hp_baseline.get("level") or 0)
    if current_level < baseline_level or baseline_level <= 0:
        return None
    derived_max_hp = int(hp_baseline.get("max_hp") or 0)
    if current_level == baseline_level:
        return max(derived_max_hp, 1)
    native_progression = _native_progression_payload(definition.source)
    gains_by_level: dict[int, int] = {}
    for event in list(native_progression.get("history") or []):
        if not isinstance(event, dict):
            continue
        try:
            event_level = int(event.get("to_level") or event.get("target_level") or 0)
        except (TypeError, ValueError):
            continue
        if event_level <= baseline_level or event_level > current_level:
            continue
        if "max_hp_delta" in event:
            delta_field = "max_hp_delta"
        elif "hp_gain" in event:
            delta_field = "hp_gain"
        else:
            continue
        try:
            gains_by_level[event_level] = int(event.get(delta_field) or 0)
        except (TypeError, ValueError):
            return None
    for level in range(baseline_level + 1, current_level + 1):
        if level not in gains_by_level:
            return None
        derived_max_hp += gains_by_level[level]
    return max(derived_max_hp, 1)


def _derive_definition_skills(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> list[dict[str, Any]]:
    existing_rows = [dict(row or {}) for row in list(definition.skills or [])]
    if not existing_rows:
        return []
    proficiency_levels = _skill_proficiency_levels_from_rows(
        existing_rows,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    campaign_option_proficiencies = collect_campaign_option_proficiency_grants(
        _campaign_option_payloads_from_definition(definition)
    )
    for skill_name in list(campaign_option_proficiencies.get("skills") or []):
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
            proficiency_levels.get(normalized_skill),
            "proficient",
        )
    effect_keys = _extract_character_effect_keys(list(definition.features or []))
    for effect_key in effect_keys:
        for normalized_skill in _skill_targets_for_effect_key(effect_key):
            proficiency_levels[normalized_skill] = _max_skill_proficiency_level(
                proficiency_levels.get(normalized_skill),
                "half_proficient",
            )
    return _build_skills_payload_from_levels(
        ability_scores,
        proficiency_levels,
        proficiency_bonus,
        skill_bonus_map=_effect_skill_bonus_map(effect_keys),
    )


def _derive_definition_stats(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    skills: list[dict[str, Any]],
    features: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    selected_class: SystemsEntryRecord | None = None,
    selected_species: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    stats, manual_adjustments = strip_manual_stat_adjustments(dict(definition.stats or {}))
    existing_ability_scores = dict(stats.get("ability_scores") or {})
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    save_proficiencies = _infer_definition_save_proficiencies(
        definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        selected_class=selected_class,
    )
    effect_keys = _extract_character_effect_keys(features)
    save_bonus_map = _effect_save_bonus_map(effect_keys)
    skill_lookup = {normalize_lookup(skill.get("name")): dict(skill) for skill in list(skills or [])}
    if skill_lookup:
        stats["passive_perception"] = 10 + int(
            (skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
        ) + _effect_passive_bonus(effect_keys, skill_name="Perception")
        stats["passive_insight"] = 10 + int(
            (skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
        ) + _effect_passive_bonus(effect_keys, skill_name="Insight")
        stats["passive_investigation"] = 10 + int(
            (skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"])
        ) + _effect_passive_bonus(effect_keys, skill_name="Investigation")
    stats["proficiency_bonus"] = proficiency_bonus
    stats["initiative_bonus"] = _ability_modifier(ability_scores["dex"]) + _effect_initiative_bonus(
        effect_keys,
        proficiency_bonus=proficiency_bonus,
    )
    normalized_ability_scores = {
        ability_key: {
            "score": score,
            "modifier": _ability_modifier(score),
            "save_bonus": _ability_modifier(score)
            + (proficiency_bonus if ability_key in save_proficiencies else 0)
            + int(save_bonus_map.get(ability_key) or 0),
        }
        for ability_key, score in ability_scores.items()
    }
    stats["ability_scores"] = {}
    for ability_key, payload in normalized_ability_scores.items():
        if ability_key in existing_ability_scores or str(ABILITY_LABELS.get(ability_key, "")).lower() not in existing_ability_scores:
            stats["ability_scores"][ability_key] = dict(payload)
        alias_key = str(ABILITY_LABELS.get(ability_key, "")).lower()
        if alias_key in existing_ability_scores:
            stats["ability_scores"][alias_key] = dict(payload)
    derived_armor_class = _derive_armor_class_from_character_inputs(
        ability_scores=ability_scores,
        equipment_catalog=list(definition.equipment_catalog or []),
        features=features,
        class_names=_character_profile_class_names(definition),
        subclass_names=_character_profile_subclass_names(definition),
        item_catalog=item_catalog,
        allow_plain_unarmored_base=_character_source_type(definition) == "native_character_builder",
    )
    if derived_armor_class is not None:
        stats["armor_class"] = derived_armor_class
    derived_speed = ""
    if selected_species is not None:
        derived_speed = _apply_speed_bonus_to_label(
            _extract_speed_label(selected_species),
            _effect_speed_bonus(effect_keys),
        )
    if derived_speed:
        stats["speed"] = derived_speed
    derived_max_hp = _derive_definition_max_hp(
        definition,
        current_level=max(_resolve_native_character_level(definition), 0),
    )
    if derived_max_hp is not None:
        stats["max_hp"] = derived_max_hp
    stats = apply_stat_adjustments(stats, campaign_option_adjustments)
    return apply_manual_stat_adjustments(stats, manual_adjustments)


def _derive_definition_spellcasting(
    definition: CharacterDefinition,
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    current_level: int,
    selected_class: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    spellcasting = dict(definition.spellcasting or {})
    spellcasting["spells"] = _normalize_spell_payloads(list(spellcasting.get("spells") or []))
    class_name = _definition_spellcasting_class_name(definition)
    existing_class_name = str(spellcasting.get("spellcasting_class") or "").strip()
    progression = _class_spell_progression(class_name, selected_class=selected_class) if class_name and selected_class is not None else {}
    ability_name = (
        _spellcasting_ability_name_for_class(class_name, selected_class=selected_class)
        if class_name and selected_class is not None
        else ""
    )
    existing_ability_name = str(spellcasting.get("spellcasting_ability") or "").strip()
    if not ability_name and existing_ability_name in set(ABILITY_LABELS.values()):
        ability_name = existing_ability_name
    slot_progression = (
        _spell_slot_progression_for_class_level(
            class_name,
            current_level,
            selected_class=selected_class,
        )
        if selected_class is not None
        else list(spellcasting.get("slot_progression") or [])
    )
    if class_name and (ability_name or slot_progression or existing_class_name):
        spellcasting["spellcasting_class"] = class_name
    elif not ability_name and not slot_progression and not existing_class_name:
        spellcasting["spellcasting_class"] = ""
    if ability_name:
        ability_key = next((key for key, label in ABILITY_LABELS.items() if label == ability_name), "")
        if ability_key:
            modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE))
            spellcasting["spellcasting_ability"] = ability_name
            spellcasting["spell_save_dc"] = 8 + proficiency_bonus + modifier
            spellcasting["spell_attack_bonus"] = proficiency_bonus + modifier
    elif not existing_ability_name:
        spellcasting["spellcasting_ability"] = ""
    if progression or selected_class is not None or existing_class_name:
        spellcasting["slot_progression"] = slot_progression
    return spellcasting


def _derive_definition_core_sheet_payloads(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    del spell_catalog
    resolved_entries = _resolve_definition_sheet_entries(
        definition,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        resolved_class=resolved_class,
        resolved_subclass=resolved_subclass,
        resolved_species=resolved_species,
        resolved_background=resolved_background,
    )
    effective_item_catalog = _effective_item_catalog_for_definition(
        definition,
        item_catalog=item_catalog,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    ability_scores = _ability_scores_from_definition(definition)
    current_level = _resolve_native_character_level(definition)
    proficiency_bonus = (
        _proficiency_bonus_for_level(current_level)
        if current_level > 0
        else int((definition.stats or {}).get("proficiency_bonus") or 2)
    )
    normalized_features, derived_resource_templates = _apply_tracker_templates_to_feature_payloads(
        _normalize_feature_payloads(list(definition.features or [])),
        ability_scores=ability_scores,
        current_level=max(current_level, 1),
    )
    normalized_equipment = _normalize_equipment_payloads(list(definition.equipment_catalog or []))
    normalized_payload = deepcopy(definition.to_dict())
    normalized_payload["features"] = normalized_features
    normalized_payload["equipment_catalog"] = normalized_equipment
    normalized_definition = CharacterDefinition.from_dict(normalized_payload)
    skills = _derive_definition_skills(
        normalized_definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
    )
    stats = _derive_definition_stats(
        normalized_definition,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        skills=skills,
        features=normalized_features,
        item_catalog=effective_item_catalog,
        selected_class=resolved_entries.get("selected_class"),
        selected_species=resolved_entries.get("selected_species"),
    )
    derived_payload = deepcopy(normalized_payload)
    derived_payload["skills"] = skills
    derived_payload["stats"] = stats
    derived_definition = CharacterDefinition.from_dict(derived_payload)
    return {
        "features": normalized_features,
        "equipment_catalog": normalized_equipment,
        "skills": skills,
        "stats": stats,
        "attacks": _recalculate_definition_attacks(
            derived_definition,
            item_catalog=effective_item_catalog,
        ),
        "spellcasting": _derive_definition_spellcasting(
            derived_definition,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
            current_level=max(current_level, 1),
            selected_class=resolved_entries.get("selected_class"),
        ),
        "resource_templates": _normalize_resource_template_payloads(
            _merge_resource_templates(
                list(definition.resource_templates or []),
                derived_resource_templates,
            )
        ),
    }


def _resolve_native_character_level(definition: CharacterDefinition) -> int:
    classes = list((definition.profile or {}).get("classes") or [])
    if classes:
        return max(int((classes[0] or {}).get("level") or 0), 0)
    class_level_text = str((definition.profile or {}).get("class_level_text") or "").strip()
    match = re.search(r"(\d+)\s*$", class_level_text)
    if match:
        return int(match.group(1))
    return 0


def _native_character_class_name(definition: CharacterDefinition) -> str:
    classes = list((definition.profile or {}).get("classes") or [])
    if classes:
        class_payload = dict(classes[0] or {})
        class_ref = dict(class_payload.get("systems_ref") or {})
        return str(class_ref.get("title") or class_payload.get("class_name") or "").strip()
    class_ref = dict((definition.profile or {}).get("class_ref") or {})
    return str(class_ref.get("title") or "").strip()


def _native_level_up_support_error(
    definition: CharacterDefinition,
    *,
    systems_service: Any | None = None,
    campaign_slug: str = "",
    campaign_page_records: list[Any] | None = None,
) -> str:
    if systems_service is not None and str(campaign_slug or "").strip():
        readiness = native_level_up_readiness(
            systems_service,
            campaign_slug,
            definition,
            campaign_page_records=campaign_page_records,
        )
        return str(readiness.get("message") or "").strip()

    source_type = _character_source_type(definition)
    if source_type != "native_character_builder":
        return "Level-up currently supports native in-app characters only."
    classes = list((definition.profile or {}).get("classes") or [])
    if len(classes) != 1:
        return "Level-up currently supports single-class native characters only."
    class_payload = dict(classes[0] or {})
    class_ref = dict(class_payload.get("systems_ref") or (definition.profile or {}).get("class_ref") or {})
    if not str(class_ref.get("title") or class_payload.get("class_name") or "").strip():
        return "This native character is missing the class link needed for level-up."
    current_level = _resolve_native_character_level(definition)
    if current_level < 1:
        return "This native character is missing a valid current level."
    if current_level >= 20:
        return "This native character is already at level 20."
    return ""


def _normalize_level_up_values(
    definition: CharacterDefinition,
    values: dict[str, str],
) -> dict[str, str]:
    normalized = {key: str(value) for key, value in dict(values or {}).items()}
    normalized.setdefault("hp_gain", "")
    existing_subclass_slug = _systems_ref_slug((definition.profile or {}).get("subclass_ref"))
    if existing_subclass_slug and not str(normalized.get("subclass_slug") or "").strip():
        normalized["subclass_slug"] = existing_subclass_slug
    return normalized


def _sanitize_entry_selection_value(
    raw_value: Any,
    options: list[SystemsEntryRecord],
) -> str:
    allowed_values = {
        candidate
        for entry in list(options or [])
        for candidate in (
            _entry_selection_value(entry),
            _entry_page_ref(entry),
            _entry_option_slug(entry),
        )
        if str(candidate or "").strip()
    }
    selected_value = _normalize_selected_choice_value(str(raw_value or "").strip(), allowed_values)
    return selected_value if selected_value in allowed_values else ""


def _sanitize_choice_section_values(
    values: dict[str, str],
    *,
    choice_sections: list[dict[str, Any]],
    static_keys: frozenset[str] | set[str],
) -> dict[str, str]:
    sanitized = {key: str(values.get(key) or "") for key in static_keys if key in values}
    selected_by_group: dict[str, set[str]] = {}
    for section in list(choice_sections or []):
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "").strip()
            if not field_name:
                continue
            allowed_values = {
                str(option.get("value") or "").strip()
                for option in list(field.get("options") or [])
                if str(option.get("value") or "").strip()
            }
            raw_value = str(values.get(field_name) or "").strip()
            selected_value = _normalize_selected_choice_value(raw_value, allowed_values)
            if selected_value not in allowed_values:
                continue
            group_key = str(field.get("group_key") or field_name).strip() or field_name
            if selected_value in selected_by_group.setdefault(group_key, set()):
                continue
            selected_by_group[group_key].add(selected_value)
            sanitized[field_name] = selected_value
    return sanitized


def _field_live_preview_region_ids(
    field: dict[str, Any],
    *,
    preview_region_ids: tuple[str, ...],
) -> tuple[str, ...]:
    field_name = str(field.get("name") or "").strip()
    kind = str(field.get("kind") or "").strip()
    preview_set = set(preview_region_ids)

    def _matching_region_ids(*region_ids: str) -> tuple[str, ...]:
        return tuple(region_id for region_id in region_ids if region_id in preview_set)

    if field_name == "hp_gain":
        return _matching_region_ids(PREVIEW_SUMMARY_REGION_ID)
    if kind in {"spell", "spell_support_replace_from", "spell_support_replace_to"} or field_name.startswith(
        (
            "spell_",
            "wizard_",
            "bonus_spell_known_",
            "levelup_spell_",
            "levelup_wizard_",
            "levelup_prepared_",
            "levelup_bonus_spell_known_",
            "levelup_spell_support_",
        )
    ):
        return _matching_region_ids(PREVIEW_SPELLS_REGION_ID)
    if kind == "campaign_page_item":
        return _matching_region_ids(
            PREVIEW_SUMMARY_REGION_ID,
            PREVIEW_EQUIPMENT_REGION_ID,
            PREVIEW_ATTACKS_REGION_ID,
        )
    if kind == "campaign_page_feature":
        return _matching_region_ids(
            PREVIEW_FEATURES_REGION_ID,
            PREVIEW_RESOURCES_REGION_ID,
            PREVIEW_SPELLS_REGION_ID,
        )
    if kind in {"subclass", "feat", "optionalfeature", "asi_mode", "feat_spell_source"} or field_name.startswith(
        (
            "class_option_",
            "levelup_class_option_",
            "levelup_subclass_option_",
            "species_feat_",
            "levelup_feat_",
        )
    ):
        return (CHOICE_SECTIONS_REGION_ID, *preview_region_ids)
    return tuple(preview_region_ids)


def _annotate_builder_choice_sections(
    choice_sections: list[dict[str, Any]],
    *,
    preview_region_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    annotated_sections: list[dict[str, Any]] = []
    for section in list(choice_sections or []):
        section_copy = dict(section)
        section_copy["fields"] = []
        for raw_field in list(section.get("fields") or []):
            field = dict(raw_field)
            region_ids = _field_live_preview_region_ids(
                field,
                preview_region_ids=preview_region_ids,
            )
            field["live_preview_trigger"] = "change"
            field["live_preview_regions"] = ",".join(region_ids)
            field["live_preview_debounce_ms"] = 120
            section_copy["fields"].append(field)
        annotated_sections.append(section_copy)
    return annotated_sections


def _stabilize_choice_section_values(
    values: dict[str, str],
    *,
    static_keys: frozenset[str] | set[str],
    build_sections,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    current_values = {key: str(value) for key, value in dict(values or {}).items()}
    section_cache: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}

    def _build_sections(current_snapshot: dict[str, str]) -> list[dict[str, Any]]:
        cache_key = tuple(sorted((str(key), str(value)) for key, value in current_snapshot.items()))
        if cache_key not in section_cache:
            section_cache[cache_key] = list(build_sections(current_snapshot) or [])
        return section_cache[cache_key]

    choice_sections = _build_sections(current_values)
    for _ in range(4):
        sanitized_values = _sanitize_choice_section_values(
            current_values,
            choice_sections=choice_sections,
            static_keys=static_keys,
        )
        if sanitized_values == current_values:
            break
        current_values = sanitized_values
        choice_sections = _build_sections(current_values)
    return current_values, choice_sections


def _class_requires_subclass_at_level(
    selected_class: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
    target_level: int,
) -> bool:
    if selected_class is None:
        return False
    subclass_title = str(selected_class.metadata.get("subclass_title") or "").strip()
    if not subclass_title:
        return False
    normalized_subclass_title = normalize_lookup(subclass_title)
    for group in class_progression:
        if int(group.get("level") or 0) != target_level:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            label = normalize_lookup(feature_row.get("label"))
            if normalized_subclass_title and normalized_subclass_title in label:
                return True
            if "choose subclass feature" in label:
                return True
    return False


def _class_requires_subclass_at_level_one(
    selected_class: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
) -> bool:
    return _class_requires_subclass_at_level(selected_class, class_progression, 1)


def _build_choice_sections(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    feat_catalog: dict[str, Any],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    equipment_groups: list[dict[str, Any]],
    campaign_feature_options: list[dict[str, str]],
    campaign_item_options: list[dict[str, str]],
    item_catalog: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    feat_selections = _resolve_builder_feat_selections(values, feat_catalog)

    class_fields = _build_class_skill_fields(selected_class, values)
    class_option_fields = _build_class_option_fields(class_progression, values)
    if class_fields or class_option_fields:
        sections.append({"title": "Class Choices", "fields": class_fields + class_option_fields})

    species_fields = _build_species_choice_fields(selected_species, feat_options, values)
    if species_fields:
        sections.append({"title": "Species Choices", "fields": species_fields})

    background_fields = _build_background_choice_fields(selected_background, values)
    if background_fields:
        sections.append({"title": "Background Choices", "fields": background_fields})

    feat_fields = _build_feat_choice_fields(
        feat_selections=feat_selections,
        values=values,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
    )
    if feat_fields:
        sections.append({"title": "Feat Choices", "fields": feat_fields})

    equipment_fields = _build_equipment_choice_fields(equipment_groups)
    if equipment_fields:
        sections.append({"title": "Equipment Choices", "fields": equipment_fields})

    campaign_feature_fields = _build_campaign_feature_choice_fields(campaign_feature_options, values)
    if campaign_feature_fields:
        sections.append({"title": "Campaign Features", "fields": campaign_feature_fields})

    campaign_item_fields = _build_campaign_item_choice_fields(campaign_item_options, values)
    if campaign_item_fields:
        sections.append({"title": "Campaign Equipment", "fields": campaign_item_fields})

    preview_choice_sections = list(sections)
    _, preview_selected_choices = _resolve_builder_choices(preview_choice_sections, values, strict=False)
    selected_feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=preview_choice_sections,
        selected_choices=preview_selected_choices,
        feat_selections=feat_selections,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    preview_campaign_option_payloads = (
        _campaign_option_payloads_from_selected_entries([selected_species, selected_background])
        + _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(selected_feature_entries)
    )
    spell_fields = _build_spell_choice_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        feature_entries=selected_feature_entries,
        campaign_option_payloads=preview_campaign_option_payloads,
    )
    if spell_fields:
        sections.append({"title": "Spell Choices", "fields": spell_fields})

    return sections


def _build_level_up_choice_sections(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    feat_catalog: dict[str, Any],
    subclass_options: list[SystemsEntryRecord],
    requires_subclass: bool,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
    spell_catalog: dict[str, Any],
    target_level: int,
    current_ability_scores: dict[str, int],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    class_fields: list[dict[str, Any]] = []
    ability_fields = _build_level_up_ability_score_fields(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
    )
    preview_ability_scores, level_up_feat_entries, _ = _resolve_level_up_ability_score_choices(
        current_ability_scores=current_ability_scores,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
        strict=False,
    )
    if requires_subclass:
        class_fields.append(
            {
                "name": "subclass_slug",
                "label": str(selected_class.metadata.get("subclass_title") or "Subclass").strip(),
                "help_text": f"Choose your {selected_class.title} subclass.",
                "options": [_choice_option(_entry_option_label(entry), entry.slug) for entry in subclass_options],
                "selected": str(values.get("subclass_slug") or "").strip(),
                "group_key": "subclass_slug",
                "kind": "subclass",
            }
        )
    class_fields.extend(
        _build_progression_option_fields(
            class_progression,
            target_level=target_level,
            values=values,
            field_prefix="levelup_class_option",
            group_key_prefix="levelup_class_options",
        )
    )
    class_fields.extend(
        _build_progression_option_fields(
            subclass_progression,
            target_level=target_level,
            values=values,
            field_prefix="levelup_subclass_option",
            group_key_prefix="levelup_subclass_options",
        )
    )
    if class_fields:
        sections.append({"title": "Class Choices", "fields": class_fields})
    if ability_fields:
        sections.append({"title": "Ability Score Improvement", "fields": ability_fields})

    feat_selections = _resolve_level_up_feat_selections(
        values,
        feat_catalog,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    feat_fields = _build_feat_choice_fields(
        feat_selections=feat_selections,
        values=values,
        optionalfeature_catalog=optionalfeature_catalog,
        item_catalog=item_catalog,
    )
    if feat_fields:
        sections.append({"title": "Feat Choices", "fields": feat_fields})

    preview_choice_sections = list(sections)
    _, preview_selected_choices = _resolve_builder_choices(preview_choice_sections, values, strict=False)
    preview_ability_scores = _apply_feat_ability_score_bonuses(
        preview_ability_scores,
        feat_selections=feat_selections,
        selected_choices=preview_selected_choices,
        strict=False,
    )
    preview_feature_entries = _collect_progression_feature_entries_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=preview_selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    preview_feature_entries.extend(level_up_feat_entries)
    preview_feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=preview_selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    spell_fields = _build_level_up_spell_choice_fields(
        definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        target_level=target_level,
        ability_scores=preview_ability_scores,
        values=values,
        feature_entries=preview_feature_entries,
    )
    if spell_fields:
        sections.append({"title": "Spell Choices", "fields": spell_fields})
    return sections


def _build_class_skill_fields(
    selected_class: SystemsEntryRecord | None,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    starting_proficiencies = dict(selected_class.metadata.get("starting_proficiencies") or {})
    skill_blocks = list(starting_proficiencies.get("skills") or [])
    fields: list[dict[str, Any]] = []
    for block in skill_blocks:
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        options = [_choice_option(_skill_label(option), option) for option in list(choose.get("from") or [])]
        count = int(choose.get("count") or 0)
        if not options or count <= 0:
            continue
        for index in range(count):
            field_name = f"class_skill_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Class Skill {index + 1}",
                    "help_text": f"Choose {count} skill{'s' if count != 1 else ''} from {selected_class.title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "class_skills",
                    "kind": "skill",
                }
            )
    return fields


def _build_class_option_fields(
    class_progression: list[dict[str, Any]],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    return _build_progression_option_fields(
        class_progression,
        target_level=1,
        values=values,
        field_prefix="class_option",
    )


def _build_progression_option_fields(
    progression: list[dict[str, Any]],
    *,
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    group_key_prefix: str | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    index = 0
    for group in progression:
        if int(group.get("level") or 0) != target_level:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            embedded_card = dict(feature_row.get("embedded_card") or {})
            option_groups = list(embedded_card.get("option_groups") or [])
            if not option_groups:
                continue
            feature_label = str(feature_row.get("label") or "Feature").strip()
            for option_group in option_groups:
                index += 1
                field_name = f"{field_prefix}_{index}"
                options = [
                    _choice_option(str(option.get("label") or ""), str(option.get("slug") or ""))
                    for option in list(option_group.get("options") or [])
                    if str(option.get("slug") or "").strip()
                ]
                if not options:
                    continue
                fields.append(
                    {
                        "name": field_name,
                        "label": feature_label,
                        "help_text": f"Choose an option for {feature_label}.",
                        "options": options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": str(group_key_prefix or field_name),
                        "kind": "optionalfeature",
                    }
    )
    return fields


def _count_ability_score_improvements_for_level(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
) -> int:
    count = 0
    for progression in (class_progression, subclass_progression):
        for group in progression:
            if int(group.get("level") or 0) != target_level:
                continue
            for feature_row in list(group.get("feature_rows") or []):
                label = normalize_lookup(feature_row.get("label"))
                if label in ABILITY_SCORE_IMPROVEMENT_NAMES:
                    count += 1
    return count


def _build_level_up_ability_score_fields(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    feat_options: list[Any],
    target_level: int,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    improvement_count = _count_ability_score_improvements_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    if improvement_count <= 0:
        return []

    ability_options = [_choice_option(label, key) for key, label in ABILITY_LABELS.items()]
    feat_field_options = [
        _choice_option(_entry_option_label(entry), _entry_selection_value(entry) or _entry_option_slug(entry))
        for entry in feat_options
        if _entry_selection_value(entry) or _entry_option_slug(entry)
    ]
    mode_options = [
        _choice_option("Ability Scores", "ability_scores"),
        _choice_option("Feat", "feat"),
    ]

    fields: list[dict[str, Any]] = []
    for index in range(1, improvement_count + 1):
        mode_field_name = f"levelup_asi_mode_{index}"
        selected_mode = str(values.get(mode_field_name) or "ability_scores").strip() or "ability_scores"
        fields.append(
            {
                "name": mode_field_name,
                "label": f"Improvement {index}",
                "help_text": "Choose whether this advancement is an ability score increase or a feat.",
                "options": mode_options,
                "selected": selected_mode,
                "group_key": mode_field_name,
                "kind": "asi_mode",
            }
        )
        if selected_mode == "feat":
            feat_field_name = f"levelup_feat_{index}"
            fields.append(
                {
                    "name": feat_field_name,
                    "label": f"Feat {index}",
                    "help_text": "Choose the feat gained from this ability score improvement.",
                    "options": feat_field_options,
                    "selected": str(values.get(feat_field_name) or "").strip(),
                    "group_key": feat_field_name,
                    "kind": "feat",
                }
            )
            continue

        first_field_name = f"levelup_asi_ability_{index}_1"
        second_field_name = f"levelup_asi_ability_{index}_2"
        fields.append(
            {
                "name": first_field_name,
                "label": f"Ability Increase {index}.1",
                "help_text": "Choose the first +1 ability increase. Pick the same ability twice to gain +2.",
                "options": ability_options,
                "selected": str(values.get(first_field_name) or "").strip(),
                "group_key": first_field_name,
                "kind": "ability",
            }
        )
        fields.append(
            {
                "name": second_field_name,
                "label": f"Ability Increase {index}.2",
                "help_text": "Choose the second +1 ability increase. Pick the same ability twice to gain +2.",
                "options": ability_options,
                "selected": str(values.get(second_field_name) or "").strip(),
                "group_key": second_field_name,
                "kind": "ability",
            }
        )
    return fields


def _resolve_level_up_ability_score_choices(
    *,
    current_ability_scores: dict[str, int],
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    feat_options: list[Any],
    target_level: int,
    values: dict[str, str],
    strict: bool,
) -> tuple[dict[str, int], list[dict[str, Any]], list[str]]:
    updated_scores = dict(current_ability_scores)
    feat_entries: list[dict[str, Any]] = []
    summaries: list[str] = []
    feat_lookup = {
        candidate: _entry_option_title(entry)
        for entry in feat_options
        for candidate in (
            _entry_selection_value(entry),
            _entry_option_slug(entry),
            _entry_page_ref(entry),
        )
        if candidate
    }

    improvement_count = _count_ability_score_improvements_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    for index in range(1, improvement_count + 1):
        mode_field_name = f"levelup_asi_mode_{index}"
        mode = str(values.get(mode_field_name) or "ability_scores").strip() or "ability_scores"
        if mode == "feat":
            feat_field_name = f"levelup_feat_{index}"
            feat_slug = str(values.get(feat_field_name) or "").strip()
            if not feat_slug:
                if strict:
                    raise CharacterBuildError("Choose a feat or ability score increase for this level.")
                continue
            feat_title = feat_lookup.get(feat_slug)
            if not feat_title:
                if strict:
                    raise CharacterBuildError("Choose a valid feat for this ability score improvement.")
                continue
            feat_entry = next(
                (
                    entry
                    for entry in feat_options
                    if feat_slug in {
                        _entry_selection_value(entry),
                        _entry_option_slug(entry),
                        _entry_page_ref(entry),
                    }
                ),
                None,
            )
            feat_entries.append(
                {
                    "kind": "feat",
                    "entry": None,
                    "name": feat_title,
                    "label": feat_title,
                    "slug": feat_slug,
                    "systems_entry": feat_entry if isinstance(feat_entry, SystemsEntryRecord) else None,
                    "page_ref": _entry_page_ref(feat_entry),
                    "campaign_option": _entry_campaign_option(feat_entry) or None,
                }
            )
            summaries.append(feat_title)
            continue

        first_field_name = f"levelup_asi_ability_{index}_1"
        second_field_name = f"levelup_asi_ability_{index}_2"
        selected_keys = [
            str(values.get(first_field_name) or "").strip(),
            str(values.get(second_field_name) or "").strip(),
        ]
        if not all(selected_keys):
            if strict:
                raise CharacterBuildError("Choose both ability score increases for this level.")
            continue
        for ability_key in selected_keys:
            if ability_key not in ABILITY_KEYS:
                if strict:
                    raise CharacterBuildError("Choose valid abilities for this ability score improvement.")
                break
        else:
            increments: dict[str, int] = {}
            for ability_key in selected_keys:
                increments[ability_key] = increments.get(ability_key, 0) + 1
            for ability_key, increment in increments.items():
                next_score = int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + increment
                if next_score > 20:
                    if strict:
                        raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} cannot exceed 20 from an ability score improvement.")
                    break
            else:
                for ability_key, increment in increments.items():
                    updated_scores[ability_key] = int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + increment
                if selected_keys[0] == selected_keys[1]:
                    summaries.append(f"{ABILITY_LABELS[selected_keys[0]]} +2")
                else:
                    summaries.append(
                        f"{ABILITY_LABELS[selected_keys[0]]} +1, {ABILITY_LABELS[selected_keys[1]]} +1"
                    )
                continue
        if not strict:
            continue
        raise CharacterBuildError("Choose valid ability score increases for this level.")
    return updated_scores, feat_entries, summaries


def _build_species_choice_fields(
    selected_species: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_species is None:
        return []
    fields: list[dict[str, Any]] = []
    metadata = dict(selected_species.metadata or {})

    skill_blocks = list(metadata.get("skill_proficiencies") or [])
    species_skill_count = 0
    for block in skill_blocks:
        if not isinstance(block, dict):
            continue
        any_count = int(block.get("any") or 0)
        for _ in range(any_count):
            species_skill_count += 1
            field_name = f"species_skill_{species_skill_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Species Skill {species_skill_count}",
                    "help_text": "Choose a species-granted skill proficiency.",
                    "options": [_choice_option(label, token) for token, label in _all_skill_options()],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "species_skills",
                    "kind": "skill",
                }
            )

    language_blocks = list(metadata.get("languages") or [])
    species_language_count = 0
    for block in language_blocks:
        if not isinstance(block, dict):
            continue
        any_standard = int(block.get("anyStandard") or 0)
        for _ in range(any_standard):
            species_language_count += 1
            field_name = f"species_language_{species_language_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Species Language {species_language_count}",
                    "help_text": "Choose an extra standard language.",
                    "options": [_choice_option(label, label) for label in STANDARD_LANGUAGE_OPTIONS],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "species_languages",
                    "kind": "language",
                }
            )

    feat_blocks = list(metadata.get("feats") or [])
    feat_count = 0
    for block in feat_blocks:
        if not isinstance(block, dict):
            continue
        any_count = int(block.get("any") or 0)
        for _ in range(any_count):
            feat_count += 1
            field_name = f"species_feat_{feat_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": "Species Feat",
                    "help_text": "Choose a feat granted by your species.",
                    "options": [
                        _choice_option(_entry_option_label(entry), _entry_selection_value(entry) or entry.slug)
                        for entry in feat_options
                        if _entry_selection_value(entry) or entry.slug
                    ],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "species_feats",
                    "kind": "feat",
                }
            )

    return fields


def _build_background_choice_fields(
    selected_background: SystemsEntryRecord | None,
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if selected_background is None:
        return []
    fields: list[dict[str, Any]] = []
    metadata = dict(selected_background.metadata or {})
    language_blocks = list(metadata.get("language_proficiencies") or [])
    background_language_count = 0
    for block in language_blocks:
        if not isinstance(block, dict):
            continue
        any_standard = int(block.get("anyStandard") or 0)
        for _ in range(any_standard):
            background_language_count += 1
            field_name = f"background_language_{background_language_count}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"Background Language {background_language_count}",
                    "help_text": "Choose a background language.",
                    "options": [_choice_option(label, label) for label in STANDARD_LANGUAGE_OPTIONS],
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "background_languages",
                    "kind": "language",
                }
            )
    return fields


def _build_feat_choice_fields(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for selection in feat_selections:
        fields.extend(
            _build_feat_choice_fields_for_selection(
                selection=selection,
                values=values,
                optionalfeature_catalog=optionalfeature_catalog,
                item_catalog=item_catalog,
            )
        )
    return fields


def _build_feat_choice_fields_for_selection(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return []

    metadata = dict(feat_entry.metadata or {})
    feat_title = feat_entry.title
    fields: list[dict[str, Any]] = []
    ability_options = [_choice_option(label, key) for key, label in ABILITY_LABELS.items()]
    skill_options = [_choice_option(label, token) for token, label in _all_skill_options()]
    language_options = [_choice_option(label, label) for label in STANDARD_LANGUAGE_OPTIONS]
    tool_options = _tool_proficiency_options(item_catalog)
    weapon_options = _weapon_proficiency_options(item_catalog)

    ability_choice_index = 0
    for block in list(metadata.get("ability") or []):
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        options = [
            _choice_option(ABILITY_LABELS.get(str(option), _humanize_words(str(option))), str(option))
            for option in list(choose.get("from") or [])
            if str(option) in ABILITY_KEYS
        ]
        count = max(int(choose.get("count") or 1), 0)
        if not options or count <= 0:
            continue
        for _ in range(count):
            ability_choice_index += 1
            field_name = _feat_field_name(instance_key, "ability", ability_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Ability",
                    "help_text": f"Choose the ability increased by {feat_title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "ability"),
                    "kind": "feat_ability",
                }
            )

    skill_choice_index = 0
    for block in list(metadata.get("skill_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        options = [
            _choice_option(_skill_label(option), str(option))
            for option in list(choose.get("from") or [])
            if normalize_lookup(str(option)) in SKILL_LABELS
        ]
        count = int(choose.get("count") or 0)
        if not options and int(block.get("any") or 0) > 0:
            options = skill_options
            count = int(block.get("any") or 0)
        if not options or count <= 0:
            continue
        for _ in range(count):
            skill_choice_index += 1
            field_name = _feat_field_name(instance_key, "skills", skill_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Skill {skill_choice_index}",
                    "help_text": f"Choose a skill granted by {feat_title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "skills"),
                    "kind": "feat_skill",
                }
            )

    language_choice_index = 0
    for block in list(metadata.get("language_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        count = int(block.get("anyStandard") or block.get("any") or 0)
        if count <= 0:
            continue
        for _ in range(count):
            language_choice_index += 1
            field_name = _feat_field_name(instance_key, "languages", language_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Language {language_choice_index}",
                    "help_text": f"Choose a language granted by {feat_title}.",
                    "options": language_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "languages"),
                    "kind": "feat_language",
                }
            )

    tool_choice_index = 0
    for block in list(metadata.get("tool_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        any_artisan_count = int(block.get("anyArtisansTool") or 0)
        any_tool_count = int(block.get("any") or block.get("anyTool") or 0)
        if any_artisan_count > 0:
            for _ in range(any_artisan_count):
                tool_choice_index += 1
                field_name = _feat_field_name(instance_key, "tools", tool_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Tool {tool_choice_index}",
                        "help_text": f"Choose an artisan's tool granted by {feat_title}.",
                        "options": _tool_proficiency_options(item_catalog, artisan_only=True),
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "tools"),
                        "kind": "feat_tool",
                    }
                )
        if any_tool_count > 0:
            for _ in range(any_tool_count):
                tool_choice_index += 1
                field_name = _feat_field_name(instance_key, "tools", tool_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Tool {tool_choice_index}",
                        "help_text": f"Choose a tool granted by {feat_title}.",
                        "options": tool_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "tools"),
                        "kind": "feat_tool",
                    }
                )

    weapon_choice_index = 0
    for block in list(metadata.get("weapon_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        choose = dict(block.get("choose") or {})
        count = int(choose.get("count") or 0)
        if count <= 0:
            continue
        for _ in range(count):
            weapon_choice_index += 1
            field_name = _feat_field_name(instance_key, "weapons", weapon_choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} Weapon {weapon_choice_index}",
                    "help_text": f"Choose a weapon granted by {feat_title}.",
                    "options": weapon_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, "weapons"),
                    "kind": "feat_weapon",
                }
            )

    mixed_choice_index = 0
    for block in list(metadata.get("skill_tool_language_proficiencies") or []):
        if not isinstance(block, dict):
            continue
        for choose_block in list(block.get("choose") or []):
            if not isinstance(choose_block, dict):
                continue
            count = int(choose_block.get("count") or 0)
            if count <= 0:
                continue
            options: list[dict[str, str]] = []
            from_values = [str(value or "").strip() for value in list(choose_block.get("from") or [])]
            if "anySkill" in from_values:
                options.extend(
                    _choice_option(f"Skill: {label}", f"skill:{token}")
                    for token, label in _all_skill_options()
                )
            if "anyTool" in from_values:
                options.extend(
                    _choice_option(f"Tool: {option['label']}", f"tool:{option['value']}")
                    for option in tool_options
                )
            if "anyLanguage" in from_values:
                options.extend(
                    _choice_option(f"Language: {option['label']}", f"language:{option['value']}")
                    for option in language_options
                )
            if not options:
                continue
            for _ in range(count):
                mixed_choice_index += 1
                field_name = _feat_field_name(instance_key, "skill_tool_language", mixed_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Choice {mixed_choice_index}",
                        "help_text": f"Choose a skill, tool, or language granted by {feat_title}.",
                        "options": options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "skill_tool_language"),
                        "kind": "feat_mixed_proficiency",
                    }
                )

    if normalize_lookup(feat_title) != normalize_lookup("Resilient"):
        save_choice_index = 0
        for block in list(metadata.get("saving_throw_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            choose = dict(block.get("choose") or {})
            options = [
                _choice_option(ABILITY_LABELS.get(str(option), _humanize_words(str(option))), str(option))
                for option in list(choose.get("from") or [])
                if str(option) in ABILITY_KEYS
            ]
            count = max(int(choose.get("count") or 1), 0)
            if not options or count <= 0:
                continue
            for _ in range(count):
                save_choice_index += 1
                field_name = _feat_field_name(instance_key, "saving_throws", save_choice_index)
                fields.append(
                    {
                        "name": field_name,
                        "label": f"{feat_title} Saving Throw",
                        "help_text": f"Choose the saving throw proficiency granted by {feat_title}.",
                        "options": ability_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": _feat_group_key(instance_key, "saving_throws"),
                        "kind": "feat_save",
                    }
                )

    for section in _feat_optionalfeature_sections(feat_entry, optionalfeature_catalog):
        section_index = int(section.get("index") or 0)
        if section_index <= 0:
            continue
        category = _feat_optionalfeature_category(section_index)
        options = [dict(option) for option in list(section.get("options") or []) if str(option.get("value") or "").strip()]
        if not options:
            continue
        choice_count = max(int(section.get("count") or 0), 0)
        if choice_count <= 0:
            continue
        section_title = str(section.get("title") or "Optional Feature").strip() or "Optional Feature"
        for choice_index in range(1, choice_count + 1):
            field_name = _feat_field_name(instance_key, category, choice_index)
            label_suffix = f" {choice_index}" if choice_count > 1 else ""
            fields.append(
                {
                    "name": field_name,
                    "label": f"{feat_title} {section_title}{label_suffix}",
                    "help_text": f"Choose an option for {section_title} from {feat_title}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": _feat_group_key(instance_key, category),
                    "kind": "feat_optionalfeature",
                }
            )

    spell_source_field = _build_feat_spell_source_field(
        selection=selection,
        values=values,
    )
    if spell_source_field is not None:
        fields.append(spell_source_field)

    return fields


def _feat_optionalfeature_category(section_index: int) -> str:
    return f"optionalfeature_{section_index}"


def _feat_optionalfeature_sections(
    feat_entry: SystemsEntryRecord,
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    metadata = dict(feat_entry.metadata or {})
    sections: list[dict[str, Any]] = []
    for index, raw_section in enumerate(list(metadata.get("optionalfeature_progression") or []), start=1):
        if not isinstance(raw_section, dict):
            continue
        feature_types = {
            normalize_lookup(value)
            for value in list(raw_section.get("featureType") or [])
            if str(value or "").strip()
        }
        if not feature_types:
            continue
        count = _optionalfeature_progression_choice_count(raw_section.get("progression"))
        if count <= 0:
            continue
        options: list[dict[str, str]] = []
        seen_values: set[str] = set()
        for entry in sorted(
            list(optionalfeature_catalog.values()),
            key=lambda candidate: (normalize_lookup(candidate.title), str(candidate.slug or "").strip()),
        ):
            entry_feature_types = {
                normalize_lookup(value)
                for value in list(dict(entry.metadata or {}).get("feature_type") or [])
                if str(value or "").strip()
            }
            if not entry_feature_types or not (entry_feature_types & feature_types):
                continue
            value = str(entry.slug or "").strip()
            if not value or value in seen_values:
                continue
            seen_values.add(value)
            options.append(_choice_option(entry.title, value))
        if not options:
            continue
        title = _clean_embedded_text(str(raw_section.get("name") or "").strip()) or "Optional Feature"
        sections.append(
            {
                "index": index,
                "title": title,
                "count": count,
                "options": options,
            }
        )
    return sections


def _optionalfeature_progression_choice_count(raw_progression: Any) -> int:
    if isinstance(raw_progression, (int, float)):
        return max(int(raw_progression), 0)
    if not isinstance(raw_progression, dict):
        return 0
    count = 0
    for raw_value in raw_progression.values():
        try:
            count = max(count, int(raw_value or 0))
        except (TypeError, ValueError):
            continue
    return count


@lru_cache(maxsize=1)
def _load_phb_level_one_spell_lists() -> dict[str, dict[str, list[str]]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_level_one_spell_lists.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, list[str]]] = {}
    for class_name, levels in payload.items():
        if not isinstance(levels, dict):
            continue
        normalized[str(class_name)] = {
            str(level_key): [str(item).strip() for item in list(level_values or []) if str(item).strip()]
            for level_key, level_values in levels.items()
        }
    for class_name, levels in EXTRA_PHB_LEVEL_ONE_SPELL_LISTS.items():
        class_payload = normalized.setdefault(str(class_name), {})
        for level_key, titles in levels.items():
            existing_titles = list(class_payload.get(str(level_key)) or [])
            merged_titles = existing_titles + [title for title in titles if title not in existing_titles]
            class_payload[str(level_key)] = merged_titles
    return normalized


@lru_cache(maxsize=1)
def _load_phb_class_progression() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_class_progression.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for class_name, raw_progression in payload.items():
        if not isinstance(raw_progression, dict):
            continue
        normalized[str(class_name)] = {
            "spellcasting_ability": str(raw_progression.get("spellcasting_ability") or "").strip(),
            "caster_progression": str(raw_progression.get("caster_progression") or "").strip(),
            "cantrip_progression": [int(value or 0) for value in list(raw_progression.get("cantrip_progression") or [])],
            "spells_known_progression": [
                int(value or 0) for value in list(raw_progression.get("spells_known_progression") or [])
            ],
            "spells_known_progression_fixed": [
                int(value or 0) for value in list(raw_progression.get("spells_known_progression_fixed") or [])
            ],
            "prepared_spells": str(raw_progression.get("prepared_spells") or "").strip(),
            "prepared_spells_progression": [
                int(value or 0) for value in list(raw_progression.get("prepared_spells_progression") or [])
            ],
            "slot_progression": [
                [
                    {
                        "level": int(dict(slot or {}).get("level") or 0),
                        "max_slots": int(dict(slot or {}).get("max_slots") or 0),
                    }
                    for slot in list(level_slots or [])
                    if int(dict(slot or {}).get("level") or 0) > 0 and int(dict(slot or {}).get("max_slots") or 0) > 0
                ]
                for level_slots in list(raw_progression.get("slot_progression") or [])
            ],
        }
    return normalized


@lru_cache(maxsize=1)
def _load_phb_weapon_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_weapon_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for title, profile in payload.items():
        if not isinstance(profile, dict):
            continue
        normalized[normalize_lookup(title)] = {
            "title": str(title).strip(),
            "type": str(profile.get("type") or "").strip(),
            "weapon_category": str(profile.get("weapon_category") or "").strip(),
            "properties": [str(item).strip() for item in list(profile.get("properties") or []) if str(item).strip()],
            "damage": str(profile.get("damage") or "").strip(),
            "versatile_damage": str(profile.get("versatile_damage") or "").strip(),
            "damage_type": str(profile.get("damage_type") or "").strip(),
            "range": str(profile.get("range") or "").strip(),
        }
    return normalized


@lru_cache(maxsize=1)
def _load_phb_armor_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_armor_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for title, profile in payload.items():
        if not isinstance(profile, dict):
            continue
        dex_cap = profile.get("dex_cap")
        minimum_strength = profile.get("minimum_strength")
        normalized[normalize_lookup(title)] = {
            "title": str(title).strip(),
            "type": str(profile.get("type") or "").strip().upper(),
            "armor_category": str(profile.get("armor_category") or "").strip().lower(),
            "base_ac": int(profile.get("base_ac") or 0),
            "uses_dex": bool(profile.get("uses_dex")),
            "dex_cap": None if dex_cap in (None, "", False) else int(dex_cap),
            "is_shield": bool(profile.get("is_shield")),
            "bonus_ac": int(profile.get("bonus_ac") or 0),
            "minimum_strength": None if minimum_strength in (None, "", False) else int(minimum_strength),
            "stealth_disadvantage": bool(profile.get("stealth_disadvantage")),
        }
    return normalized


def _build_item_catalog(item_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_title: dict[str, SystemsEntryRecord] = {}
    by_slug: dict[str, SystemsEntryRecord] = {}
    for entry in item_entries:
        normalized_title = normalize_lookup(entry.title)
        if normalized_title and normalized_title not in by_title:
            by_title[normalized_title] = entry
        slug = str(entry.slug or "").strip()
        if slug and slug not in by_slug:
            by_slug[slug] = entry
    return {
        "entries": list(item_entries),
        "by_title": by_title,
        "by_slug": by_slug,
        "phb_weapon_profiles": _load_phb_weapon_profiles(),
        "phb_armor_profiles": _load_phb_armor_profiles(),
    }


def _build_spell_catalog(spell_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_title: dict[str, SystemsEntryRecord] = {}
    by_slug: dict[str, SystemsEntryRecord] = {}
    for entry in spell_entries:
        normalized_title = normalize_lookup(entry.title)
        if normalized_title and normalized_title not in by_title:
            by_title[normalized_title] = entry
        if entry.slug:
            by_slug[entry.slug] = entry
    return {
        "entries": list(spell_entries),
        "by_title": by_title,
        "by_slug": by_slug,
        "phb_level_one_lists": _load_phb_level_one_spell_lists(),
    }


def _build_feat_catalog(feat_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_slug: dict[str, SystemsEntryRecord] = {}
    by_value: dict[str, SystemsEntryRecord] = {}
    for entry in feat_entries:
        slug = str(entry.slug or "").strip()
        if slug and slug not in by_slug:
            by_slug[slug] = entry
        for candidate in (_entry_selection_value(entry), _entry_page_ref(entry), slug):
            clean_candidate = str(candidate or "").strip()
            if clean_candidate and clean_candidate not in by_value:
                by_value[clean_candidate] = entry
    return {
        "entries": list(feat_entries),
        "by_slug": by_slug,
        "by_value": by_value,
    }


def _build_entry_slug_catalog(entries: list[SystemsEntryRecord]) -> dict[str, SystemsEntryRecord]:
    by_slug: dict[str, SystemsEntryRecord] = {}
    for entry in list(entries or []):
        slug = str(entry.slug or "").strip()
        if slug and slug not in by_slug:
            by_slug[slug] = entry
    return by_slug


def _item_type_code(entry: SystemsEntryRecord) -> str:
    raw_value = str((entry.metadata or {}).get("type") or "").strip()
    return raw_value.split("|", 1)[0].strip().upper()


def _tool_proficiency_options(
    item_catalog: dict[str, Any],
    *,
    artisan_only: bool = False,
) -> list[dict[str, str]]:
    allowed_type_codes = {"AT"} if artisan_only else {"AT", "GS", "INS"}
    dynamic_titles = [
        entry.title
        for entry in list(item_catalog.get("entries") or [])
        if _item_type_code(entry) in allowed_type_codes and str(entry.title or "").strip()
    ]
    fallback_titles = [
        title
        for title in COMMON_TOOL_PROFICIENCY_OPTIONS
        if not artisan_only
        or title.endswith("Supplies")
        or title.endswith("Tools")
        or title.endswith("Utensils")
    ]
    merged_titles = _dedupe_preserve_order(dynamic_titles + fallback_titles)
    return [_choice_option(title, title) for title in merged_titles]


def _weapon_proficiency_options(item_catalog: dict[str, Any]) -> list[dict[str, str]]:
    profile_titles = [
        str(dict(profile or {}).get("title") or "").strip()
        for profile in list(dict(item_catalog.get("phb_weapon_profiles") or {}).values())
    ]
    return [_choice_option(title, title) for title in _dedupe_preserve_order(profile_titles)]


def _resolve_builder_feat_selections(
    values: dict[str, str],
    feat_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    by_value = dict(feat_catalog.get("by_value") or {})
    selections: list[dict[str, Any]] = []
    for field_name in sorted(values.keys()):
        if not str(field_name).startswith("species_feat_"):
            continue
        feat_slug = str(values.get(field_name) or "").strip()
        feat_entry = by_value.get(feat_slug)
        if feat_entry is None and feat_slug and SYSTEMS_OPTION_PREFIX not in feat_slug and CAMPAIGN_PAGE_OPTION_PREFIX not in feat_slug:
            feat_entry = by_value.get(f"{SYSTEMS_OPTION_PREFIX}{feat_slug}")
        if feat_entry is None:
            continue
        selections.append(
            {
                "instance_key": str(field_name),
                "selection_value": feat_slug,
                "slug": _entry_option_slug(feat_entry) or feat_slug,
                "entry": feat_entry,
                "label": _entry_option_title(feat_entry) or feat_slug,
                "page_ref": _entry_page_ref(feat_entry),
                "campaign_option": _entry_campaign_option(feat_entry) or None,
            }
        )
    return selections


def _resolve_level_up_feat_selections(
    values: dict[str, str],
    feat_catalog: dict[str, Any],
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
) -> list[dict[str, Any]]:
    by_value = dict(feat_catalog.get("by_value") or {})
    improvement_count = _count_ability_score_improvements_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    selections: list[dict[str, Any]] = []
    for index in range(1, improvement_count + 1):
        if str(values.get(f"levelup_asi_mode_{index}") or "ability_scores").strip() != "feat":
            continue
        field_name = f"levelup_feat_{index}"
        feat_slug = str(values.get(field_name) or "").strip()
        feat_entry = by_value.get(feat_slug)
        if feat_entry is None and feat_slug and SYSTEMS_OPTION_PREFIX not in feat_slug and CAMPAIGN_PAGE_OPTION_PREFIX not in feat_slug:
            feat_entry = by_value.get(f"{SYSTEMS_OPTION_PREFIX}{feat_slug}")
        if feat_entry is None:
            continue
        selections.append(
            {
                "instance_key": field_name,
                "selection_value": feat_slug,
                "slug": _entry_option_slug(feat_entry) or feat_slug,
                "entry": feat_entry,
                "label": _entry_option_title(feat_entry) or feat_slug,
                "page_ref": _entry_page_ref(feat_entry),
                "campaign_option": _entry_campaign_option(feat_entry) or None,
            }
        )
    return selections


def _feat_field_name(instance_key: str, category: str, index: int) -> str:
    return f"feat_{instance_key}_{category}_{index}"


def _feat_group_key(instance_key: str, category: str) -> str:
    return f"feat:{instance_key}:{category}"


def _feat_selected_values(
    selected_choices: dict[str, list[str]],
    instance_key: str,
    category: str,
) -> list[str]:
    return list(selected_choices.get(_feat_group_key(instance_key, category)) or [])


def _feat_spell_choice_field_name(instance_key: str, category: str, spec_index: int, choice_index: int) -> str:
    return f"feat_{instance_key}_{category}_{spec_index}_{choice_index}"


def _feat_spell_block_options(feat_entry: SystemsEntryRecord) -> list[dict[str, str]]:
    metadata = dict(feat_entry.metadata or {})
    blocks = [dict(block) for block in list(metadata.get("additional_spells") or []) if isinstance(block, dict)]
    if len(blocks) <= 1:
        return []
    labels: list[str] = []
    for index, block in enumerate(blocks, start=1):
        label = _clean_embedded_text(str(block.get("name") or "").strip()) or f"Spell List {index}"
        labels.append(label)
    if len(set(normalize_lookup(label) for label in labels if label)) != len(labels):
        return []
    return [_choice_option(label, str(index)) for index, label in enumerate(labels, start=1)]


def _build_feat_spell_source_field(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any] | None:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return None
    options = _feat_spell_block_options(feat_entry)
    if not options:
        return None
    field_name = _feat_field_name(instance_key, "spell_source", 1)
    return {
        "name": field_name,
        "label": f"{feat_entry.title} Spell List",
        "help_text": f"Choose the spell list used by {feat_entry.title}.",
        "options": options,
        "selected": str(values.get(field_name) or "").strip(),
        "group_key": field_name,
        "kind": "feat_spell_source",
    }


def _selected_feat_additional_spell_blocks(
    *,
    selection: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return []
    metadata = dict(feat_entry.metadata or {})
    blocks = [dict(block) for block in list(metadata.get("additional_spells") or []) if isinstance(block, dict)]
    options = _feat_spell_block_options(feat_entry)
    if not options:
        return blocks
    field_name = _feat_field_name(instance_key, "spell_source", 1)
    selected_value = str(values.get(field_name) or "").strip()
    if not selected_value:
        return []
    try:
        selected_index = int(selected_value)
    except ValueError:
        return []
    if 1 <= selected_index <= len(blocks):
        return [blocks[selected_index - 1]]
    return []


def _build_equipment_groups(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    item_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    class_starting_equipment = dict((selected_class.metadata if selected_class is not None else {}) or {}).get(
        "starting_equipment"
    )
    if isinstance(class_starting_equipment, dict):
        groups.extend(
            _build_starting_equipment_groups(
                prefix="class",
                label_prefix="Class Equipment",
                raw_groups=list(class_starting_equipment.get("defaultData") or []),
                item_catalog=item_catalog,
                values=values,
            )
        )

    background_starting_equipment = dict((selected_background.metadata if selected_background is not None else {}) or {}).get(
        "starting_equipment"
    )
    if isinstance(background_starting_equipment, list):
        groups.extend(
            _build_starting_equipment_groups(
                prefix="background",
                label_prefix="Background Equipment",
                raw_groups=background_starting_equipment,
                item_catalog=item_catalog,
                values=values,
            )
        )
    return groups


def _build_starting_equipment_groups(
    *,
    prefix: str,
    label_prefix: str,
    raw_groups: list[Any],
    item_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    choice_index = 0
    for raw_group in raw_groups:
        option_bundles = _build_equipment_group_option_bundles(raw_group, item_catalog)
        if not option_bundles:
            continue
        field_name = None
        selected = ""
        if len(option_bundles) > 1:
            choice_index += 1
            field_name = f"{prefix}_equipment_{choice_index}"
            for option_index, option in enumerate(option_bundles, start=1):
                option["value"] = f"{field_name}:{option_index}"
            selected = str(values.get(field_name) or "").strip()
        else:
            option_bundles[0]["value"] = f"{prefix}_equipment_fixed_{len(groups) + 1}"
        groups.append(
            {
                "field_name": field_name,
                "field_label": f"{label_prefix} {choice_index}" if field_name else "",
                "help_text": f"Choose {label_prefix.lower()}." if field_name else "",
                "selected": selected,
                "options": option_bundles,
            }
        )
    return groups


def _build_equipment_group_option_bundles(
    raw_group: Any,
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(raw_group, dict):
        return []
    alternatives: list[Any]
    option_keys = [key for key in raw_group.keys() if key != "_"]
    if option_keys:
        alternatives = [raw_group.get(key) for key in option_keys]
    else:
        alternatives = [raw_group.get("_")]

    option_bundles: list[dict[str, Any]] = []
    for alternative in alternatives:
        bundles = _expand_equipment_bundle_specs(alternative, item_catalog)
        for bundle in bundles:
            option_bundles.append(
                {
                    "label": _describe_equipment_bundle(bundle),
                    "value": "",
                    "equipment_bundle": bundle,
                }
            )
    return option_bundles


def _expand_equipment_bundle_specs(
    raw_specs: Any,
    item_catalog: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    specs_list = raw_specs if isinstance(raw_specs, list) else [raw_specs]
    bundles: list[list[dict[str, Any]]] = [[]]
    for raw_spec in specs_list:
        candidate_specs = _expand_equipment_spec(raw_spec, item_catalog)
        if not candidate_specs:
            continue
        next_bundles: list[list[dict[str, Any]]] = []
        for bundle in bundles:
            for candidate in candidate_specs:
                next_bundles.append(bundle + [candidate])
        bundles = next_bundles or bundles
    return bundles


def _expand_equipment_spec(
    raw_spec: Any,
    item_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(raw_spec, str):
        return [_build_equipment_item_spec(raw_spec, item_catalog=item_catalog)]
    if not isinstance(raw_spec, dict):
        return []

    equipment_type = str(raw_spec.get("equipmentType") or "").strip()
    if equipment_type:
        candidates = []
        for entry in _list_item_entries_for_equipment_type(equipment_type, item_catalog):
            candidates.append(
                _build_equipment_item_spec(
                    entry.title,
                    item_catalog=item_catalog,
                    quantity=int(raw_spec.get("quantity") or 1),
                    forced_entry=entry,
                )
            )
        return candidates

    if raw_spec.get("item"):
        return [
            _build_equipment_item_spec(
                str(raw_spec.get("item") or ""),
                item_catalog=item_catalog,
                quantity=int(raw_spec.get("quantity") or 1),
                display_name=str(raw_spec.get("displayName") or "").strip() or None,
                special_text=str(raw_spec.get("special") or "").strip() or None,
                contained_value=raw_spec.get("containsValue"),
            )
        ]

    if raw_spec.get("value") is not None:
        currency = _currency_seed_from_cp(raw_spec.get("value"))
        label = _format_currency_seed(currency)
        if not label:
            return []
        return [
            {
                "name": label,
                "quantity": 1,
                "weight": "",
                "notes": "",
                "systems_ref": None,
                "currency": currency,
                "is_currency_only": True,
            }
        ]

    special_name = str(raw_spec.get("displayName") or raw_spec.get("special") or "").strip()
    if special_name:
        currency = _currency_seed_from_cp(raw_spec.get("containsValue"))
        return [
            {
                "name": special_name,
                "quantity": int(raw_spec.get("quantity") or 1),
                "weight": "",
                "notes": "",
                "systems_ref": None,
                "currency": currency,
                "is_currency_only": False,
            }
        ]
    return []


def _build_equipment_item_spec(
    item_reference: str,
    *,
    item_catalog: dict[str, Any],
    quantity: int = 1,
    display_name: str | None = None,
    special_text: str | None = None,
    contained_value: Any = None,
    forced_entry: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    entry = forced_entry or _resolve_item_entry(item_reference, item_catalog)
    name = display_name or (entry.title if entry is not None else _humanize_item_reference(item_reference))
    currency = _currency_seed_from_cp(contained_value)
    notes_parts = [part for part in (special_text,) if part]
    return {
        "name": name,
        "quantity": max(int(quantity or 1), 1),
        "weight": _format_weight_value((entry.metadata or {}).get("weight")) if entry is not None else "",
        "notes": " ".join(notes_parts).strip(),
        "systems_ref": _systems_ref_from_entry(entry),
        "currency": currency,
        "is_currency_only": False,
    }


def _resolve_item_entry(
    item_reference: str,
    item_catalog: dict[str, Any],
) -> SystemsEntryRecord | None:
    normalized_reference = normalize_lookup(_humanize_item_reference(item_reference))
    return dict(item_catalog.get("by_title") or {}).get(normalized_reference)


def _list_item_entries_for_equipment_type(
    equipment_type: str,
    item_catalog: dict[str, Any],
) -> list[SystemsEntryRecord]:
    by_title = dict(item_catalog.get("by_title") or {})
    exact_titles = list(ITEM_TITLES_BY_EQUIPMENT_TYPE.get(equipment_type) or [])
    if exact_titles:
        return [
            entry
            for title in exact_titles
            for entry in [by_title.get(normalize_lookup(title))]
            if entry is not None
        ]
    type_codes = set(ITEM_TYPE_CODES_BY_EQUIPMENT_TYPE.get(equipment_type) or set())
    if type_codes:
        return sorted(
            [
                entry
                for entry in list(item_catalog.get("entries") or [])
                if str(entry.metadata.get("type") or "").strip() in type_codes
            ],
            key=lambda entry: entry.title.lower(),
        )
    return []


def _describe_equipment_bundle(bundle: list[dict[str, Any]]) -> str:
    return ", ".join(_describe_equipment_spec(spec) for spec in bundle if _describe_equipment_spec(spec))


def _describe_equipment_spec(spec: dict[str, Any]) -> str:
    name = str(spec.get("name") or "").strip()
    quantity = int(spec.get("quantity") or 1)
    if not name:
        return ""
    if quantity > 1:
        return f"{quantity} x {name}"
    return name


def _build_level_one_equipment_catalog(
    equipment_groups: list[dict[str, Any]],
    *,
    choice_sections: list[dict[str, Any]] | None = None,
    selected_choices: dict[str, list[str]] | None = None,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected_specs: list[dict[str, Any]] = []
    for group in equipment_groups:
        options = list(group.get("options") or [])
        if not options:
            continue
        selected_value = str(group.get("selected") or "").strip()
        selected_option = next(
            (option for option in options if str(option.get("value") or "").strip() == selected_value),
            None,
        )
        if selected_option is None:
            selected_option = options[0]
        selected_specs.extend(list(selected_option.get("equipment_bundle") or []))
    if choice_sections and selected_choices:
        selected_specs.extend(
            _build_selected_campaign_item_specs(
                choice_sections=choice_sections,
                selected_choices=selected_choices,
            )
        )

    merged_catalog: list[dict[str, Any]] = []
    merged_index_by_key: dict[tuple[str, str, str, str, str, bool], int] = {}
    for spec in selected_specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        systems_ref = dict(spec.get("systems_ref") or {})
        page_ref = str(spec.get("page_ref") or "").strip()
        notes = str(spec.get("notes") or "").strip()
        weight = str(spec.get("weight") or "").strip()
        is_currency_only = bool(spec.get("is_currency_only"))
        merge_key = (
            normalize_lookup(name),
            str(systems_ref.get("slug") or ""),
            page_ref,
            notes,
            weight,
            is_currency_only,
        )
        existing_index = merged_index_by_key.get(merge_key)
        if existing_index is None:
            row = {
                "id": f"{slugify(name)}-{len(merged_catalog) + 1}",
                "name": name,
                "default_quantity": max(int(spec.get("quantity") or 1), 1),
                "weight": weight,
                "notes": notes,
                "systems_ref": systems_ref or None,
                "page_ref": page_ref or None,
                "currency": dict(spec.get("currency") or {}),
                "is_currency_only": is_currency_only,
                "source_kind": str(spec.get("source_kind") or "").strip(),
                "campaign_option": dict(spec.get("campaign_option") or {}) or None,
                "is_equipped": _default_equipment_item_equipped(spec, item_catalog=item_catalog),
            }
            merged_index_by_key[merge_key] = len(merged_catalog)
            merged_catalog.append(row)
            continue

        merged_row = merged_catalog[existing_index]
        merged_row["default_quantity"] = int(merged_row.get("default_quantity") or 0) + max(
            int(spec.get("quantity") or 1),
            1,
        )
        merged_row["currency"] = _merge_currency_seed(
            dict(merged_row.get("currency") or {}),
            dict(spec.get("currency") or {}),
        )
    return merged_catalog


def _default_equipment_item_equipped(
    item: dict[str, Any],
    *,
    item_catalog: dict[str, Any] | None = None,
) -> bool:
    if bool(item.get("is_currency_only")):
        return False
    if _resolve_weapon_profile(item, item_catalog or {}) is not None:
        return True
    if _resolve_armor_profile(item, item_catalog or {}) is not None:
        return True
    return False


def _build_level_one_attacks(
    *,
    equipment_catalog: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    weapon_proficiencies: list[str],
    selected_choices: dict[str, list[str]],
    features: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    attacks: list[dict[str, Any]] = []
    attack_contexts = _build_weapon_attack_contexts(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        weapon_proficiencies=weapon_proficiencies,
    )
    has_archery = _has_fighting_style(selected_choices, "phb-optionalfeature-archery", "Archery") or _character_has_named_feature(
        features,
        "Archery",
        "phb-optionalfeature-archery",
    )
    has_dueling = _has_fighting_style(selected_choices, "phb-optionalfeature-dueling", "Dueling") or _character_has_named_feature(
        features,
        "Dueling",
        "phb-optionalfeature-dueling",
    )
    has_great_weapon_fighting = _has_fighting_style(
        selected_choices,
        "phb-optionalfeature-great-weapon-fighting",
        "Great Weapon Fighting",
    ) or _character_has_named_feature(
        features,
        "Great Weapon Fighting",
        "phb-optionalfeature-great-weapon-fighting",
    )
    has_two_weapon_fighting = _has_fighting_style(
        selected_choices,
        "phb-optionalfeature-two-weapon-fighting",
        "Two-Weapon Fighting",
    ) or _character_has_named_feature(
        features,
        "Two-Weapon Fighting",
        "phb-optionalfeature-two-weapon-fighting",
    )
    active_effect_keys = list(_extract_character_effect_keys(features))
    attack_support_flags = _collect_attack_support_flags(features)
    shared_weapon_attack_bonus = _effect_weapon_attack_bonus(active_effect_keys)
    shared_weapon_damage_bonus = _effect_weapon_damage_bonus(active_effect_keys)
    structured_mode_descriptors = _effect_attack_mode_descriptors(active_effect_keys)
    has_charger_phb = bool(attack_support_flags.get("charger_phb"))
    has_charger_xphb = bool(attack_support_flags.get("charger_xphb"))
    has_crossbow_expert = bool(attack_support_flags.get("crossbow_expert"))
    has_dual_wielder = bool(attack_support_flags.get("dual_wielder"))
    has_great_weapon_master = bool(attack_support_flags.get("great_weapon_master"))
    has_gunner = bool(attack_support_flags.get("gunner"))
    has_martial_adept = bool(attack_support_flags.get("martial_adept"))
    has_polearm_master = bool(attack_support_flags.get("polearm_master"))
    has_savage_attacker = bool(attack_support_flags.get("savage_attacker"))
    has_sharpshooter = bool(attack_support_flags.get("sharpshooter"))
    has_tavern_brawler = bool(attack_support_flags.get("tavern_brawler"))
    off_hand_context = _resolve_off_hand_attack_context(
        attack_contexts,
        allow_non_light=has_dual_wielder,
    )
    crossbow_expert_bonus_context = _resolve_crossbow_expert_bonus_attack_context(attack_contexts)
    has_shield = any(_is_shield_item(item) for item in equipment_catalog)

    for context in attack_contexts:
        profile = dict(context["profile"] or {})
        has_thrown_variant = _supports_thrown_attack_variant(profile)
        has_two_handed_variant = _supports_versatile_two_handed_attack(
            profile,
            has_shield=has_shield,
            off_hand_context=off_hand_context,
        )
        attack_bonus = int(context["ability_modifier"] or 0)
        if bool(context["is_proficient"]):
            attack_bonus += proficiency_bonus
        attack_bonus += int(context.get("item_attack_bonus") or 0)
        attack_bonus += shared_weapon_attack_bonus
        if has_archery and str(profile.get("type") or "").strip().upper() == "R":
            attack_bonus += 2
        damage_bonus = int(context["ability_modifier"] or 0)
        damage_bonus += int(context.get("item_damage_bonus") or 0)
        damage_bonus += shared_weapon_damage_bonus
        if has_dueling and _qualifies_for_dueling(context, off_hand_context=off_hand_context):
            damage_bonus += 2
        ignore_loading = (
            (has_crossbow_expert and _qualifies_for_crossbow_expert(context))
            or (has_gunner and _qualifies_for_gunner(context))
        )
        base_attack_notes = _build_weapon_attack_notes(
            profile,
            great_weapon_fighting=has_great_weapon_fighting,
            has_shield=has_shield,
            ignore_loading=ignore_loading,
            off_hand_context=off_hand_context,
            show_range=not has_thrown_variant,
            show_versatile=not has_two_handed_variant,
            extra_notes=_base_attack_feat_notes(
                context,
                has_charger_phb=has_charger_phb,
                has_charger_xphb=has_charger_xphb,
                has_crossbow_expert=has_crossbow_expert,
                has_great_weapon_master=has_great_weapon_master,
                has_gunner=has_gunner,
                has_martial_adept=has_martial_adept,
                has_polearm_master=has_polearm_master,
                has_savage_attacker=has_savage_attacker,
                has_sharpshooter=has_sharpshooter,
                ranged_attack=False,
            ),
        )
        _append_weapon_attack_payloads(
            attacks,
            context,
            attack_bonus=attack_bonus,
            damage_bonus=damage_bonus,
            extra_damage=None,
            notes=base_attack_notes,
            structured_mode_descriptors=structured_mode_descriptors,
        )
        if has_great_weapon_master and _qualifies_for_great_weapon_master(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus - 5,
                damage_bonus=damage_bonus + 10,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    )
                    + ["Great Weapon Master (-5 attack, +10 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="great weapon master",
                mode_key=ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER,
            )
        if has_polearm_master and _qualifies_for_polearm_master(context):
            polearm_bonus_profile = dict(profile)
            polearm_bonus_profile["damage"] = "1d4"
            polearm_bonus_profile["damage_type"] = "B"
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    polearm_bonus_profile,
                    bonus_action=True,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=False,
                    show_versatile=False,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                        include_polearm_master_note=False,
                    )
                    + ["Polearm Master bonus attack"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="polearm master",
                mode_key=ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS,
                profile_override=polearm_bonus_profile,
            )
            if has_two_handed_variant:
                polearm_two_handed_profile = dict(polearm_bonus_profile)
                polearm_two_handed_damage_bonus = int(context["ability_modifier"] or 0)
                _append_weapon_attack_payloads(
                    attacks,
                    context,
                    attack_bonus=attack_bonus,
                    damage_bonus=polearm_two_handed_damage_bonus,
                    extra_damage=None,
                    notes=_build_weapon_attack_notes(
                        polearm_two_handed_profile,
                        bonus_action=True,
                        great_weapon_fighting=has_great_weapon_fighting,
                        has_shield=False,
                        off_hand_context=None,
                        show_range=False,
                        show_versatile=False,
                        wielded_two_handed=True,
                        extra_notes=_base_attack_feat_notes(
                            context,
                            has_charger_phb=has_charger_phb,
                            has_charger_xphb=has_charger_xphb,
                            has_crossbow_expert=has_crossbow_expert,
                            has_great_weapon_master=has_great_weapon_master,
                            has_gunner=has_gunner,
                            has_martial_adept=has_martial_adept,
                            has_polearm_master=has_polearm_master,
                            has_savage_attacker=has_savage_attacker,
                            has_sharpshooter=has_sharpshooter,
                            ranged_attack=False,
                            include_polearm_master_note=False,
                        )
                        + ["Polearm Master bonus attack"],
                    ),
                    structured_mode_descriptors=structured_mode_descriptors,
                    variant_label="polearm master, two-handed",
                    mode_key=f"{ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS}|{ATTACK_MODE_WEAPON_TWO_HANDED}",
                    profile_override=polearm_two_handed_profile,
                )
        if has_charger_xphb and _qualifies_for_charger(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                extra_damage="1d8",
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    )
                    + ["Charger (move 10 feet straight, +1d8 damage, once per turn)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="charger",
                mode_key=ATTACK_MODE_FEAT_CHARGER_XPHB,
            )
        if has_thrown_variant:
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=False,
                    has_shield=has_shield,
                    off_hand_context=off_hand_context,
                    show_versatile=False,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=True,
                    ),
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="thrown",
                mode_key=ATTACK_MODE_WEAPON_THROWN,
                category_override="ranged weapon",
            )
        if has_two_handed_variant:
            two_handed_profile = dict(profile)
            two_handed_profile["damage"] = str(profile.get("versatile_damage") or "").strip()
            two_handed_attack_bonus = int(context["ability_modifier"] or 0)
            if bool(context["is_proficient"]):
                two_handed_attack_bonus += proficiency_bonus
            two_handed_damage_bonus = int(context["ability_modifier"] or 0)
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=two_handed_attack_bonus,
                damage_bonus=two_handed_damage_bonus,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    two_handed_profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=False,
                    off_hand_context=None,
                    show_versatile=False,
                    wielded_two_handed=True,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    ),
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="two-handed",
                mode_key=ATTACK_MODE_WEAPON_TWO_HANDED,
                profile_override=two_handed_profile,
            )
        if has_sharpshooter and _qualifies_for_sharpshooter(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus - 5,
                damage_bonus=damage_bonus + 10,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=False,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=True,
                    )
                    + ["Sharpshooter (-5 attack, +10 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="sharpshooter",
                mode_key=ATTACK_MODE_FEAT_SHARPSHOOTER,
            )
        if has_charger_phb and _qualifies_for_charger(context):
            _append_weapon_attack_payloads(
                attacks,
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus + 5,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    profile,
                    bonus_action=True,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    ignore_loading=ignore_loading,
                    off_hand_context=off_hand_context,
                    show_range=False,
                    show_versatile=not has_two_handed_variant,
                    extra_notes=_base_attack_feat_notes(
                        context,
                        has_charger_phb=has_charger_phb,
                        has_charger_xphb=has_charger_xphb,
                        has_crossbow_expert=has_crossbow_expert,
                        has_great_weapon_master=has_great_weapon_master,
                        has_gunner=has_gunner,
                        has_martial_adept=has_martial_adept,
                        has_polearm_master=has_polearm_master,
                        has_savage_attacker=has_savage_attacker,
                        has_sharpshooter=has_sharpshooter,
                        ranged_attack=False,
                    )
                    + ["Charger (after Dash, move 10 feet straight for +5 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="charger",
                mode_key=ATTACK_MODE_FEAT_CHARGER_PHB,
            )

    if off_hand_context is not None:
        off_hand_damage_bonus = (
            int(off_hand_context["ability_modifier"] or 0)
            if has_two_weapon_fighting
            else min(int(off_hand_context["ability_modifier"] or 0), 0)
        )
        off_hand_attack_bonus = int(off_hand_context["ability_modifier"] or 0)
        if bool(off_hand_context["is_proficient"]):
            off_hand_attack_bonus += proficiency_bonus
        _append_weapon_attack_payloads(
            attacks,
            off_hand_context,
            attack_bonus=off_hand_attack_bonus,
            damage_bonus=off_hand_damage_bonus,
            extra_damage=None,
            notes=_build_weapon_attack_notes(
                dict(off_hand_context["profile"] or {}),
                bonus_action=True,
                great_weapon_fighting=False,
                has_shield=False,
                off_hand_context=off_hand_context,
                show_versatile=False,
                extra_notes=_base_attack_feat_notes(
                    off_hand_context,
                    has_charger_phb=has_charger_phb,
                    has_charger_xphb=has_charger_xphb,
                    has_crossbow_expert=has_crossbow_expert,
                    has_great_weapon_master=has_great_weapon_master,
                    has_gunner=has_gunner,
                    has_martial_adept=has_martial_adept,
                    has_polearm_master=has_polearm_master,
                    has_savage_attacker=has_savage_attacker,
                    has_sharpshooter=has_sharpshooter,
                    ranged_attack=False,
                ),
            ),
            structured_mode_descriptors=structured_mode_descriptors,
            variant_label="off-hand",
            mode_key=ATTACK_MODE_WEAPON_OFF_HAND,
        )
    if has_crossbow_expert and crossbow_expert_bonus_context is not None:
        crossbow_profile = dict(crossbow_expert_bonus_context["profile"] or {})
        crossbow_attack_bonus = int(crossbow_expert_bonus_context["ability_modifier"] or 0)
        if bool(crossbow_expert_bonus_context["is_proficient"]):
            crossbow_attack_bonus += proficiency_bonus
        if has_archery and str(crossbow_profile.get("type") or "").strip().upper() == "R":
            crossbow_attack_bonus += 2
        crossbow_damage_bonus = int(crossbow_expert_bonus_context["ability_modifier"] or 0)
        crossbow_extra_notes = _base_attack_feat_notes(
            crossbow_expert_bonus_context,
            has_charger_phb=has_charger_phb,
            has_charger_xphb=has_charger_xphb,
            has_crossbow_expert=has_crossbow_expert,
            has_great_weapon_master=has_great_weapon_master,
            has_gunner=has_gunner,
            has_martial_adept=has_martial_adept,
            has_polearm_master=has_polearm_master,
            has_savage_attacker=has_savage_attacker,
            has_sharpshooter=has_sharpshooter,
            ranged_attack=True,
        ) + ["Crossbow Expert bonus attack"]
        _append_weapon_attack_payloads(
            attacks,
            crossbow_expert_bonus_context,
            attack_bonus=crossbow_attack_bonus,
            damage_bonus=crossbow_damage_bonus,
            extra_damage=None,
            notes=_build_weapon_attack_notes(
                crossbow_profile,
                bonus_action=True,
                great_weapon_fighting=False,
                has_shield=has_shield,
                ignore_loading=True,
                off_hand_context=off_hand_context,
                extra_notes=crossbow_extra_notes,
            ),
            structured_mode_descriptors=structured_mode_descriptors,
            variant_label="crossbow expert",
            mode_key=ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS,
        )
        if has_sharpshooter and _qualifies_for_sharpshooter(crossbow_expert_bonus_context):
            _append_weapon_attack_payloads(
                attacks,
                crossbow_expert_bonus_context,
                attack_bonus=crossbow_attack_bonus - 5,
                damage_bonus=crossbow_damage_bonus + 10,
                extra_damage=None,
                notes=_build_weapon_attack_notes(
                    crossbow_profile,
                    bonus_action=True,
                    great_weapon_fighting=False,
                    has_shield=has_shield,
                    ignore_loading=True,
                    off_hand_context=off_hand_context,
                    extra_notes=crossbow_extra_notes + ["Sharpshooter (-5 attack, +10 damage)"],
                ),
                structured_mode_descriptors=structured_mode_descriptors,
                variant_label="crossbow expert, sharpshooter",
                mode_key=f"{ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS}|{ATTACK_MODE_FEAT_SHARPSHOOTER}",
            )
    if has_tavern_brawler:
        attacks.append(
            _build_unarmed_attack_payload(
                ability_scores=ability_scores,
                proficiency_bonus=proficiency_bonus,
                index=len(attacks) + 1,
            )
        )
    return attacks


def _extract_feat_effect_keys(features: list[dict[str, Any]] | None) -> list[str]:
    results: list[str] = []
    for feature in list(features or []):
        category = normalize_lookup(str(feature.get("category") or "").strip())
        systems_ref = dict(feature.get("systems_ref") or {})
        entry_type = normalize_lookup(str(systems_ref.get("entry_type") or "").strip())
        if category != normalize_lookup("feat") and entry_type != normalize_lookup("feat"):
            continue
        results.extend(_effect_keys_for_feature(feature))
    return _dedupe_preserve_order(results)


def _effect_keys_for_feature(feature: dict[str, Any]) -> list[str]:
    systems_ref = dict(feature.get("systems_ref") or {})
    campaign_option = dict(feature.get("campaign_option") or {})
    feature_name = str(feature.get("name") or systems_ref.get("title") or "").strip()
    effect_keys: list[str] = []
    if feature_name:
        effect_keys.append(feature_name)
        normalized_name = normalize_lookup(feature_name)
        source_id = str(systems_ref.get("source_id") or feature.get("source") or "").strip().upper()
        if normalized_name == normalize_lookup("Charger"):
            effect_keys.append("charger-xphb" if source_id == "XPHB" else "charger-phb")
        if normalized_name == normalize_lookup("Alert"):
            effect_keys.append("initiative-bonus:5")
        if normalized_name == normalize_lookup("Mobile"):
            effect_keys.append("speed-bonus:10")
        if normalized_name == normalize_lookup("Observant"):
            effect_keys.extend(
                [
                    "passive-bonus:Perception:5",
                    "passive-bonus:Investigation:5",
                ]
            )
        if normalized_name == normalize_lookup("Jack of All Trades"):
            effect_keys.append("half-proficiency:all")
        if normalized_name == normalize_lookup("Remarkable Athlete"):
            effect_keys.append("half-proficiency:abilities:str,dex,con")
        if normalized_name == normalize_lookup("Tavern Brawler"):
            effect_keys.append("tavern-brawler")
    for effect in list(campaign_option.get("modeled_effects") or []):
        clean_effect = str(effect or "").strip()
        if clean_effect:
            effect_keys.append(clean_effect)
    return effect_keys


def _feat_effect_keys_for_feature(feature: dict[str, Any]) -> list[str]:
    return _effect_keys_for_feature(feature)


def _qualifies_for_crossbow_expert(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    if not bool(context.get("is_proficient")):
        return False
    if str(profile.get("type") or "").strip().upper() != "R":
        return False
    return "crossbow" in normalize_lookup(str(context.get("attack_name") or "").strip())


def _qualifies_for_gunner(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    if not bool(context.get("is_proficient")):
        return False
    if str(profile.get("type") or "").strip().upper() != "R":
        return False
    return _weapon_uses_firearm_proficiency(profile, attack_name=str(context.get("attack_name") or "").strip())


def _qualifies_for_charger(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    return bool(context.get("is_proficient")) and str(profile.get("type") or "").strip().upper() == "M"


def _qualifies_for_crossbow_expert_bonus_attack(context: dict[str, Any]) -> bool:
    if not _qualifies_for_crossbow_expert(context):
        return False
    item = dict(context.get("item") or {})
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(context.get("attack_name") or "").strip(),
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
        str(systems_ref.get("slug") or "").strip(),
    ]
    normalized_candidates = {
        normalize_lookup(value)
        for value in candidate_values
        if str(value or "").strip()
    }
    return bool(
        normalized_candidates
        & {
            normalize_lookup("Hand Crossbow"),
            normalize_lookup("phb-item-hand-crossbow"),
        }
    )


def _resolve_crossbow_expert_bonus_attack_context(
    attack_contexts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for context in attack_contexts:
        if _qualifies_for_crossbow_expert_bonus_attack(context):
            return context
    return None


def _qualifies_for_great_weapon_master(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    properties = set(profile.get("properties") or [])
    return bool(context.get("is_proficient")) and str(profile.get("type") or "").strip().upper() == "M" and "H" in properties


def _qualifies_for_polearm_master(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    if str(profile.get("type") or "").strip().upper() != "M":
        return False
    item = dict(context.get("item") or {})
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(context.get("attack_name") or "").strip(),
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
    ]
    normalized_candidates = {
        normalize_lookup(value)
        for value in candidate_values
        if str(value or "").strip()
    }
    return bool(
        normalized_candidates
        & {
            normalize_lookup("Glaive"),
            normalize_lookup("Halberd"),
            normalize_lookup("Quarterstaff"),
            normalize_lookup("Spear"),
            normalize_lookup("Staff"),
            normalize_lookup("Wooden Staff"),
        }
    )


def _qualifies_for_savage_attacker(context: dict[str, Any], *, ranged_attack: bool) -> bool:
    profile = dict(context.get("profile") or {})
    return not ranged_attack and str(profile.get("type") or "").strip().upper() == "M"


def _qualifies_for_sharpshooter(context: dict[str, Any]) -> bool:
    profile = dict(context.get("profile") or {})
    return bool(context.get("is_proficient")) and str(profile.get("type") or "").strip().upper() == "R"


def _base_attack_feat_notes(
    context: dict[str, Any],
    *,
    has_charger_phb: bool = False,
    has_charger_xphb: bool = False,
    has_crossbow_expert: bool,
    has_great_weapon_master: bool,
    has_gunner: bool = False,
    has_martial_adept: bool,
    has_polearm_master: bool,
    has_savage_attacker: bool,
    has_sharpshooter: bool,
    ranged_attack: bool,
    include_polearm_master_note: bool = True,
) -> list[str]:
    notes: list[str] = []
    if has_crossbow_expert and _qualifies_for_crossbow_expert(context):
        notes.append("Crossbow Expert (ignore loading, no adjacent disadvantage)")
    if has_gunner and _qualifies_for_gunner(context):
        notes.append("Gunner (ignore loading, no adjacent disadvantage)")
    if has_great_weapon_master and _qualifies_for_great_weapon_master(context):
        notes.append("Great Weapon Master (bonus attack on crit or kill)")
    if has_martial_adept and not ranged_attack:
        notes.append("Martial Adept maneuvers available")
    if (
        has_polearm_master
        and include_polearm_master_note
        and not ranged_attack
        and _qualifies_for_polearm_master(context)
    ):
        notes.append("Polearm Master (bonus attack, opportunity attack when creatures enter reach)")
    if has_savage_attacker and _qualifies_for_savage_attacker(context, ranged_attack=ranged_attack):
        notes.append("Savage Attacker (reroll damage once per turn)")
    if has_sharpshooter and _qualifies_for_sharpshooter(context):
        notes.append("Sharpshooter (ignore cover, no long-range disadvantage)")
    return notes


def _build_weapon_attack_contexts(
    *,
    equipment_catalog: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    ability_scores: dict[str, int],
    weapon_proficiencies: list[str],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for item in equipment_catalog:
        profile = _resolve_weapon_profile(item, item_catalog)
        if profile is None:
            continue
        attack_name = str(item.get("name") or profile.get("title") or "").strip()
        if not attack_name:
            continue
        ability_key = _weapon_attack_ability_key(profile, ability_scores)
        contexts.append(
            {
                "item": dict(item),
                "profile": dict(profile),
                "attack_name": attack_name,
                "ability_key": ability_key,
                "ability_modifier": _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)),
                "is_proficient": _is_proficient_with_weapon(profile, weapon_proficiencies, attack_name),
                "quantity": max(int(item.get("default_quantity") or 1), 1),
                "item_attack_bonus": _active_weapon_profile_bonus(item, profile, key="item_attack_bonus"),
                "item_damage_bonus": _active_weapon_profile_bonus(item, profile, key="item_damage_bonus"),
            }
        )
    return contexts


def _build_weapon_attack_payload(
    context: dict[str, Any],
    *,
    attack_bonus: int,
    damage_bonus: int,
    extra_damage: str | None = None,
    notes: str,
    index: int,
    variant_label: str = "",
    mode_key: str = "",
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = dict(profile_override or context["profile"] or {})
    clean_mode_key = _normalize_attack_mode_key(mode_key)
    clean_variant_label = _normalize_attack_variant_label(
        raw_variant_label=variant_label,
        mode_key=clean_mode_key,
        attack_name=context.get("attack_name"),
        notes=notes,
    )
    attack_name = f"{str(context.get('attack_name') or '').strip()}{_attack_name_suffix(clean_variant_label)}"
    equipment_ref = str(dict(context.get("item") or {}).get("id") or "").strip()
    raw_page_ref = dict(context.get("item") or {}).get("page_ref")
    payload = {
        "id": f"{slugify(attack_name)}-{index}",
        "name": attack_name,
        "category": str(category_override or _weapon_attack_category(profile)),
        "attack_bonus": attack_bonus,
        "damage": _format_weapon_damage(profile, damage_bonus, extra_damage=extra_damage),
        "damage_type": DAMAGE_TYPE_LABELS.get(str(profile.get("damage_type") or "").strip().upper(), ""),
        "notes": notes,
        "systems_ref": dict(dict(context.get("item") or {}).get("systems_ref") or {}) or None,
        "page_ref": dict(raw_page_ref) if isinstance(raw_page_ref, dict) else raw_page_ref or None,
        "equipment_refs": [equipment_ref] if equipment_ref else [],
    }
    if clean_mode_key:
        payload["mode_key"] = clean_mode_key
    if clean_variant_label:
        payload["variant_label"] = clean_variant_label
    return payload


def _append_weapon_attack_payloads(
    attacks: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    attack_bonus: int,
    damage_bonus: int,
    extra_damage: str | None,
    notes: str,
    structured_mode_descriptors: list[dict[str, Any]] | None = None,
    variant_label: str = "",
    mode_key: str = "",
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> None:
    payload = _build_weapon_attack_payload(
        context,
        attack_bonus=attack_bonus,
        damage_bonus=damage_bonus,
        extra_damage=extra_damage,
        notes=notes,
        index=len(attacks) + 1,
        variant_label=variant_label,
        mode_key=mode_key,
        category_override=category_override,
        profile_override=profile_override,
    )
    attacks.append(payload)
    for descriptor in list(structured_mode_descriptors or []):
        if not _attack_mode_descriptor_applies_to_context(
            descriptor,
            context,
            category_override=category_override,
            profile_override=profile_override,
        ):
            continue
        descriptor_mode_component = str(descriptor.get("mode_component") or "").strip()
        if not descriptor_mode_component:
            continue
        combined_mode_key = _normalize_attack_mode_key([payload.get("mode_key"), descriptor_mode_component])
        attacks.append(
            _build_weapon_attack_payload(
                context,
                attack_bonus=attack_bonus + int(descriptor.get("attack_delta") or 0),
                damage_bonus=damage_bonus + int(descriptor.get("damage_delta") or 0),
                extra_damage=_combine_attack_extra_damage(extra_damage, descriptor.get("extra_damage")),
                notes=_append_attack_note_text(notes, descriptor.get("note")),
                index=len(attacks) + 1,
                mode_key=combined_mode_key,
                category_override=category_override,
                profile_override=profile_override,
            )
        )


def _resolve_off_hand_attack_context(
    attack_contexts: list[dict[str, Any]],
    *,
    allow_non_light: bool = False,
) -> dict[str, Any] | None:
    eligible_contexts: list[dict[str, Any]] = []
    for context in attack_contexts:
        profile = dict(context.get("profile") or {})
        if str(profile.get("type") or "").strip().upper() != "M":
            continue
        properties = set(profile.get("properties") or [])
        if "2H" in properties:
            continue
        if not allow_non_light and "L" not in properties:
            continue
        quantity = max(int(context.get("quantity") or 1), 1)
        for _ in range(quantity):
            eligible_contexts.append(context)
            if len(eligible_contexts) >= 2:
                return eligible_contexts[1]
    return None


def _resolve_weapon_profile(
    item: dict[str, Any],
    item_catalog: dict[str, Any],
) -> dict[str, Any] | None:
    entry = _resolve_item_entry(item, item_catalog)
    metadata = dict((entry.metadata if isinstance(entry, SystemsEntryRecord) else {}) or {})
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_titles = [
        str(systems_ref.get("title") or "").strip(),
        str(item.get("name") or "").strip(),
        str(metadata.get("base_item") or "").split("|", 1)[0].strip(),
    ]
    profiles = dict(item_catalog.get("phb_weapon_profiles") or _load_phb_weapon_profiles())
    resolved_requires_attunement = _metadata_requires_attunement(metadata.get("attunement"))
    for title in candidate_titles:
        base_title, parsed_bonus = _split_magic_item_name(title)
        profile = profiles.get(normalize_lookup(base_title))
        if profile is None:
            continue
        attack_bonus, damage_bonus = _resolve_weapon_bonus_from_metadata(
            metadata,
            fallback_bonus=parsed_bonus,
        )
        resolved_profile = dict(profile)
        resolved_profile["item_attack_bonus"] = attack_bonus
        resolved_profile["item_damage_bonus"] = damage_bonus
        resolved_profile["requires_attunement"] = resolved_requires_attunement
        return resolved_profile
    return None


def _active_weapon_profile_bonus(item: dict[str, Any], profile: dict[str, Any], *, key: str) -> int:
    if not bool(item.get("is_equipped", False)):
        return 0
    if bool(profile.get("requires_attunement")) and not bool(item.get("is_attuned", False)):
        return 0
    return int(profile.get(key) or 0)


def _resolve_item_entry(
    item: Any,
    item_catalog: dict[str, Any] | None,
) -> SystemsEntryRecord | None:
    if not item_catalog:
        return None
    by_title = dict(item_catalog.get("by_title") or {})
    by_slug = dict(item_catalog.get("by_slug") or {})
    candidate_titles: list[str] = []
    if isinstance(item, dict):
        systems_ref = dict(item.get("systems_ref") or {})
        slug = str(systems_ref.get("slug") or "").strip()
        if slug:
            entry = by_slug.get(slug)
            if isinstance(entry, SystemsEntryRecord):
                return entry
        candidate_titles.extend(
            [
                str(systems_ref.get("title") or "").strip(),
                str(item.get("name") or "").strip(),
            ]
        )
    else:
        raw_reference = str(item or "").strip()
        if raw_reference:
            candidate_titles.extend(
                [
                    raw_reference.split("|", 1)[0].strip(),
                    _humanize_item_reference(raw_reference),
                ]
            )
    for title in candidate_titles:
        if not title:
            continue
        entry = by_title.get(normalize_lookup(title))
        if isinstance(entry, SystemsEntryRecord):
            return entry
    return None


def _parse_optional_int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"[-+]?\d+", str(value))
    if match is None:
        return None
    return int(match.group(0))


def _build_armor_profile(
    *,
    title: str,
    type_code: str,
    base_ac: int,
    bonus_ac: int = 0,
    minimum_strength: int | None = None,
    stealth_disadvantage: bool = False,
) -> dict[str, Any] | None:
    normalized_type = str(type_code or "").split("|", 1)[0].strip().upper()
    if normalized_type not in {"LA", "MA", "HA", "S"}:
        return None
    armor_category = {
        "LA": "light",
        "MA": "medium",
        "HA": "heavy",
        "S": "shield",
    }[normalized_type]
    return {
        "title": str(title or "").strip(),
        "type": normalized_type,
        "armor_category": armor_category,
        "base_ac": int(base_ac),
        "uses_dex": normalized_type in {"LA", "MA"},
        "dex_cap": 2 if normalized_type == "MA" else None,
        "is_shield": normalized_type == "S",
        "bonus_ac": int(bonus_ac or 0),
        "minimum_strength": minimum_strength,
        "stealth_disadvantage": bool(stealth_disadvantage),
    }


def _armor_profile_from_entry(entry: SystemsEntryRecord | None) -> dict[str, Any] | None:
    if not isinstance(entry, SystemsEntryRecord):
        return None
    metadata = dict(entry.metadata or {})
    type_code = str(metadata.get("type") or "").split("|", 1)[0].strip().upper()
    base_ac = _parse_optional_int_value(metadata.get("ac"))
    if base_ac is None:
        return None
    return _build_armor_profile(
        title=entry.title,
        type_code=type_code,
        base_ac=base_ac,
        bonus_ac=_parse_optional_int_value(metadata.get("bonus_ac")) or 0,
        minimum_strength=_parse_optional_int_value(metadata.get("strength")),
        stealth_disadvantage=bool(metadata.get("stealth_disadvantage")),
    )


def _split_magic_item_name(raw_name: Any) -> tuple[str, int]:
    cleaned = str(raw_name or "").strip()
    if not cleaned:
        return "", 0
    prefix_match = re.match(r"^\+(\d+)\s+(.+)$", cleaned)
    if prefix_match is not None:
        return prefix_match.group(2).strip(), int(prefix_match.group(1))
    suffix_match = re.match(r"^(.+?),\s*\+(\d+)$", cleaned)
    if suffix_match is not None:
        return suffix_match.group(1).strip(), int(suffix_match.group(2))
    return cleaned, 0


def _metadata_requires_attunement(value: Any) -> bool:
    if value in (None, "", False, [], {}):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized or normalized in {"false", "none", "no", "not required"}:
            return False
    return True


def _resolve_weapon_bonus_from_metadata(
    metadata: dict[str, Any],
    *,
    fallback_bonus: int = 0,
) -> tuple[int, int]:
    shared_bonus = (
        _parse_optional_int_value(metadata.get("bonus_weapon"))
        or _parse_optional_int_value(metadata.get("bonus"))
        or fallback_bonus
    )
    attack_bonus = (
        _parse_optional_int_value(metadata.get("bonus_weapon_attack"))
        or _parse_optional_int_value(metadata.get("bonus_attack_rolls"))
        or shared_bonus
    )
    damage_bonus = (
        _parse_optional_int_value(metadata.get("bonus_weapon_damage"))
        or _parse_optional_int_value(metadata.get("bonus_damage_rolls"))
        or shared_bonus
    )
    return int(attack_bonus or 0), int(damage_bonus or 0)


def _resolve_armor_profile(
    item: dict[str, Any],
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    entry = _resolve_item_entry(item, item_catalog)
    entry_profile = _armor_profile_from_entry(entry)
    if entry_profile is not None:
        return entry_profile

    armor_profiles = dict((item_catalog or {}).get("phb_armor_profiles") or _load_phb_armor_profiles())
    metadata = dict((entry.metadata if isinstance(entry, SystemsEntryRecord) else {}) or {})
    bonus_ac = _parse_optional_int_value(metadata.get("bonus_ac")) or 0
    candidate_titles = []
    base_item = str(metadata.get("base_item") or "").split("|", 1)[0].strip()
    if base_item:
        candidate_titles.append(base_item)
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_titles.extend(
        [
            str(systems_ref.get("title") or "").strip(),
            str(item.get("name") or "").strip(),
        ]
    )
    seen_candidates: set[str] = set()
    for raw_title in candidate_titles:
        base_title, parsed_bonus = _split_magic_item_name(raw_title)
        effective_bonus = bonus_ac or parsed_bonus
        for candidate in _merge_name_candidates(base_title):
            if candidate in seen_candidates:
                continue
            seen_candidates.add(candidate)
            profile = armor_profiles.get(candidate)
            if profile is None:
                continue
            resolved_profile = dict(profile)
            resolved_profile["bonus_ac"] = int(resolved_profile.get("bonus_ac") or 0) + int(effective_bonus or 0)
            return resolved_profile
    return None


def _character_profile_class_names(
    definition: CharacterDefinition,
    *,
    fallback_class_name: str = "",
) -> list[str]:
    classes = []
    for class_payload in list((definition.profile or {}).get("classes") or []):
        class_name = str(dict(class_payload or {}).get("class_name") or "").strip()
        if class_name:
            classes.append(class_name)
    class_ref = dict((definition.profile or {}).get("class_ref") or {})
    fallback = str(
        fallback_class_name
        or class_ref.get("title")
        or (definition.profile or {}).get("class_name")
        or ""
    ).strip()
    if fallback and fallback not in classes:
        classes.append(fallback)
    return classes


def _character_profile_subclass_names(
    definition: CharacterDefinition,
    *,
    fallback_subclass_name: str = "",
) -> list[str]:
    subclasses = []
    for class_payload in list((definition.profile or {}).get("classes") or []):
        subclass_name = str(dict(class_payload or {}).get("subclass_name") or "").strip()
        if subclass_name:
            subclasses.append(subclass_name)
    fallback = str(fallback_subclass_name or _native_character_subclass_name(definition) or "").strip()
    if fallback and fallback not in subclasses:
        subclasses.append(fallback)
    return subclasses


def _character_has_named_feature(features: list[dict[str, Any]] | None, *feature_values: str) -> bool:
    normalized_targets = {normalize_lookup(value) for value in feature_values if str(value or "").strip()}
    for feature in list(features or []):
        systems_ref = dict(feature.get("systems_ref") or {})
        candidates = (
            str(feature.get("name") or "").strip(),
            str(systems_ref.get("title") or "").strip(),
            str(systems_ref.get("slug") or "").strip(),
        )
        if any(normalize_lookup(candidate) in normalized_targets for candidate in candidates if candidate):
            return True
    return False


def _derive_armor_class_from_character_inputs(
    *,
    ability_scores: dict[str, int],
    equipment_catalog: list[dict[str, Any]],
    features: list[dict[str, Any]] | None,
    class_names: list[str] | None,
    subclass_names: list[str] | None,
    item_catalog: dict[str, Any] | None = None,
    allow_plain_unarmored_base: bool,
) -> int | None:
    dex_modifier = _ability_modifier(int(ability_scores.get("dex", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
    con_modifier = _ability_modifier(int(ability_scores.get("con", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
    wis_modifier = _ability_modifier(int(ability_scores.get("wis", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE))
    normalized_classes = {normalize_lookup(name) for name in list(class_names or []) if str(name or "").strip()}
    normalized_subclasses = {normalize_lookup(name) for name in list(subclass_names or []) if str(name or "").strip()}

    all_items = [dict(item or {}) for item in list(equipment_catalog or [])]
    equipped_items = [item for item in all_items if bool(item.get("is_equipped"))]
    equipped_armor_profiles = [
        (item, profile)
        for item in equipped_items
        if (profile := _resolve_armor_profile(item, item_catalog)) is not None
    ]
    armor_items = equipped_items if any(not bool(profile.get("is_shield")) for _, profile in equipped_armor_profiles) else all_items
    resolved_profiles = [
        (item, profile)
        for item in armor_items
        if (profile := _resolve_armor_profile(item, item_catalog)) is not None
    ]

    shield_bonus = max(
        (
            int(profile.get("base_ac") or 0) + int(profile.get("bonus_ac") or 0)
            for _, profile in resolved_profiles
            if bool(profile.get("is_shield"))
        ),
        default=0,
    )
    armor_profiles = [profile for _, profile in resolved_profiles if not bool(profile.get("is_shield"))]
    has_armor = bool(armor_profiles)
    has_shield = shield_bonus > 0

    has_barbarian_unarmored_defense = normalize_lookup("Barbarian") in normalized_classes
    has_monk_unarmored_defense = normalize_lookup("Monk") in normalized_classes
    has_draconic_resilience = normalize_lookup("Draconic Bloodline") in normalized_subclasses or _character_has_named_feature(
        features,
        "Draconic Resilience",
    )
    has_defense_fighting_style = _character_has_named_feature(features, "Defense", "phb-optionalfeature-defense")

    candidate_values: list[int] = []
    for profile in armor_profiles:
        base_ac = int(profile.get("base_ac") or 0)
        bonus_ac = int(profile.get("bonus_ac") or 0)
        armor_category = str(profile.get("armor_category") or "").strip().lower()
        total = base_ac + bonus_ac
        if armor_category == "light":
            total += dex_modifier
        elif armor_category == "medium":
            dex_cap = profile.get("dex_cap")
            total += min(dex_modifier, int(dex_cap if dex_cap is not None else 2))
        if has_defense_fighting_style:
            total += 1
        total += shield_bonus
        candidate_values.append(total)

    if not has_armor:
        if allow_plain_unarmored_base:
            candidate_values.append(10 + dex_modifier + shield_bonus)
        if has_barbarian_unarmored_defense:
            candidate_values.append(10 + dex_modifier + con_modifier + shield_bonus)
        if has_draconic_resilience:
            candidate_values.append(13 + dex_modifier + shield_bonus)
        if has_monk_unarmored_defense and not has_shield:
            candidate_values.append(10 + dex_modifier + wis_modifier)

    if not candidate_values:
        return None
    return max(candidate_values)


def _recalculate_definition_armor_class(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats, manual_adjustments = strip_manual_stat_adjustments(dict(definition.stats or {}))
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    derived_armor_class = _derive_armor_class_from_character_inputs(
        ability_scores=_ability_scores_from_definition(definition),
        equipment_catalog=list(definition.equipment_catalog or []),
        features=list(definition.features or []),
        class_names=_character_profile_class_names(definition),
        subclass_names=_character_profile_subclass_names(definition),
        item_catalog=item_catalog or {},
        allow_plain_unarmored_base=_character_source_type(definition) == "native_character_builder",
    )
    if derived_armor_class is None:
        return dict(definition.stats or {})
    stats["armor_class"] = derived_armor_class
    stats = apply_stat_adjustments(stats, campaign_option_adjustments)
    return apply_manual_stat_adjustments(stats, manual_adjustments)


def _recalculate_definition_attacks(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    effective_item_catalog = dict(item_catalog or _build_item_catalog([]))
    equipment_catalog = list(definition.equipment_catalog or [])
    if not equipment_catalog:
        return _normalize_attack_payloads(list(definition.attacks or []))
    has_structured_equipment = any(
        bool(dict(item.get("systems_ref") or {}))
        or bool(_normalize_page_ref_payload(item.get("page_ref")))
        or bool(item.get("is_equipped", False))
        or bool(item.get("is_attuned", False))
        for item in equipment_catalog
    )
    if not has_structured_equipment:
        return _normalize_attack_payloads(list(definition.attacks or []))
    recalculated_attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=effective_item_catalog,
        ability_scores=_ability_scores_from_definition(definition),
        proficiency_bonus=int(
            (definition.stats or {}).get("proficiency_bonus")
            or _proficiency_bonus_for_level(_resolve_native_character_level(definition))
        ),
        weapon_proficiencies=[
            str(value).strip()
            for value in list((definition.proficiencies or {}).get("weapons") or [])
            if str(value).strip()
        ],
        selected_choices={},
        features=list(definition.features or []),
    )
    if not recalculated_attacks and list(definition.attacks or []):
        return _normalize_attack_payloads(list(definition.attacks or []))
    return _normalize_attack_payloads(
        recalculated_attacks
    )


def _weapon_attack_ability_key(
    profile: dict[str, Any],
    ability_scores: dict[str, int],
) -> str:
    if str(profile.get("type") or "").strip().upper() == "R":
        return "dex"
    if "F" in set(profile.get("properties") or []):
        str_score = int(ability_scores.get("str", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        dex_score = int(ability_scores.get("dex", DEFAULT_ABILITY_SCORE) or DEFAULT_ABILITY_SCORE)
        return "dex" if dex_score > str_score else "str"
    return "str"


def _is_proficient_with_weapon(
    profile: dict[str, Any],
    weapon_proficiencies: list[str],
    attack_name: str,
) -> bool:
    normalized_proficiencies: set[str] = set()
    for value in weapon_proficiencies:
        normalized_proficiencies.update(_weapon_proficiency_name_candidates(value))
    normalized_attack_names = _weapon_proficiency_name_candidates(attack_name)
    normalized_attack_names.update(_weapon_proficiency_name_candidates(profile.get("title")))
    weapon_category = str(profile.get("weapon_category") or "").strip().lower()
    if normalized_attack_names & normalized_proficiencies:
        return True
    if weapon_category == "simple" and normalize_lookup("Simple Weapons") in normalized_proficiencies:
        return True
    if weapon_category == "martial" and normalize_lookup("Martial Weapons") in normalized_proficiencies:
        return True
    if _weapon_uses_firearm_proficiency(profile, attack_name=attack_name):
        return normalize_lookup("Firearms") in normalized_proficiencies
    return False


def _weapon_proficiency_name_candidates(value: Any) -> set[str]:
    base_name, _parsed_bonus = _split_magic_item_name(value)
    candidates: set[str] = set()
    for raw_candidate in (value, base_name):
        for candidate in _merge_name_candidates(raw_candidate):
            if candidate:
                candidates.add(candidate)
            candidates.update(_singularize_lookup_variants(candidate))
    return candidates


def _singularize_lookup_variants(value: Any) -> set[str]:
    normalized = normalize_lookup(value)
    if not normalized:
        return set()
    variants = {normalized}
    if normalized.endswith("ves") and len(normalized) > 3:
        stem = normalized[:-3]
        variants.add(f"{stem}f")
        variants.add(f"{stem}fe")
    if normalized.endswith("ies") and len(normalized) > 3:
        variants.add(f"{normalized[:-3]}y")
    if normalized.endswith("es") and len(normalized) > 2:
        variants.add(normalized[:-2])
    if normalized.endswith("s") and len(normalized) > 1:
        variants.add(normalized[:-1])
    return {candidate for candidate in variants if candidate}


def _weapon_uses_firearm_proficiency(profile: dict[str, Any], *, attack_name: str) -> bool:
    weapon_category = str(profile.get("weapon_category") or "").strip().lower()
    if weapon_category == "firearm":
        return True
    candidate_values = [
        str(profile.get("title") or "").strip(),
        str(attack_name or "").strip(),
    ]
    return any(
        normalize_lookup(value)
        in {
            normalize_lookup("Pistol"),
            normalize_lookup("Musket"),
            normalize_lookup("Pepperbox"),
            normalize_lookup("Blunderbuss"),
            normalize_lookup("Firearm"),
        }
        for value in candidate_values
        if str(value or "").strip()
    )


def _has_fighting_style(selected_choices: dict[str, list[str]], *style_values: str) -> bool:
    normalized_targets = {normalize_lookup(value) for value in style_values if str(value or "").strip()}
    for values in selected_choices.values():
        for value in values:
            if normalize_lookup(value) in normalized_targets:
                return True
    return False


def _qualifies_for_dueling(
    context: dict[str, Any],
    *,
    off_hand_context: dict[str, Any] | None,
) -> bool:
    profile = dict(context.get("profile") or {})
    properties = set(profile.get("properties") or [])
    if str(profile.get("type") or "").strip().upper() != "M":
        return False
    if "2H" in properties:
        return False
    if off_hand_context is not None:
        return False
    return True


def _supports_thrown_attack_variant(profile: dict[str, Any]) -> bool:
    properties = set(profile.get("properties") or [])
    return (
        str(profile.get("type") or "").strip().upper() == "M"
        and "T" in properties
        and bool(str(profile.get("range") or "").strip())
    )


def _supports_versatile_two_handed_attack(
    profile: dict[str, Any],
    *,
    has_shield: bool,
    off_hand_context: dict[str, Any] | None,
) -> bool:
    properties = set(profile.get("properties") or [])
    return (
        str(profile.get("type") or "").strip().upper() == "M"
        and "V" in properties
        and bool(str(profile.get("versatile_damage") or "").strip())
        and not has_shield
        and off_hand_context is None
    )


def _is_shield_item(item: dict[str, Any]) -> bool:
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_values = [
        str(item.get("name") or "").strip(),
        str(systems_ref.get("title") or "").strip(),
        str(systems_ref.get("slug") or "").strip(),
    ]
    return any(normalize_lookup(value) in {"shield", "phb item shield"} for value in candidate_values if value)


def _weapon_attack_category(profile: dict[str, Any]) -> str:
    return "ranged weapon" if str(profile.get("type") or "").strip().upper() == "R" else "melee weapon"


def _format_weapon_damage(profile: dict[str, Any], damage_bonus: int, *, extra_damage: str | None = None) -> str:
    base_damage = str(profile.get("damage") or "").strip()
    if not base_damage:
        return "--"
    parts = [base_damage]
    if str(extra_damage or "").strip():
        parts.append(str(extra_damage).strip())
    damage_text = "+".join(parts)
    bonus_text = ""
    if damage_bonus > 0:
        bonus_text = f"+{damage_bonus}"
    elif damage_bonus < 0:
        bonus_text = str(damage_bonus)
    damage_type = DAMAGE_TYPE_LABELS.get(str(profile.get("damage_type") or "").strip().upper(), "").strip()
    if damage_type:
        return f"{damage_text}{bonus_text} {damage_type}"
    return f"{damage_text}{bonus_text}"


def _build_unarmed_attack_payload(
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    index: int,
) -> dict[str, Any]:
    strength_modifier = _ability_modifier(ability_scores.get("str", DEFAULT_ABILITY_SCORE))
    damage_bonus = strength_modifier
    damage = "1d4"
    if damage_bonus > 0:
        damage = f"{damage}+{damage_bonus}"
    elif damage_bonus < 0:
        damage = f"{damage}{damage_bonus}"
    return {
        "id": f"unarmed-strike-{index}",
        "name": "Unarmed Strike",
        "category": "melee weapon",
        "attack_bonus": proficiency_bonus + strength_modifier,
        "damage": f"{damage} bludgeoning",
        "damage_type": "Bludgeoning",
        "notes": "Tavern Brawler enhanced unarmed strike.",
        "systems_ref": None,
    }


def _build_weapon_attack_notes(
    profile: dict[str, Any],
    *,
    bonus_action: bool = False,
    extra_notes: list[str] | None = None,
    great_weapon_fighting: bool = False,
    has_shield: bool = False,
    ignore_loading: bool = False,
    off_hand_context: dict[str, Any] | None = None,
    show_range: bool = True,
    show_versatile: bool = True,
    wielded_two_handed: bool = False,
) -> str:
    properties = set(profile.get("properties") or [])
    notes: list[str] = []
    if "A" in properties:
        notes.append("Ammunition")
    if "LD" in properties and not ignore_loading:
        notes.append("loading")
    attack_range = str(profile.get("range") or "").strip()
    if show_range and attack_range:
        notes.append(f"range {attack_range}")
    if show_versatile and "V" in properties and str(profile.get("versatile_damage") or "").strip():
        notes.append(f"Versatile ({str(profile.get('versatile_damage') or '').strip()})")
    if great_weapon_fighting and ("2H" in properties or wielded_two_handed):
        notes.append("Great Weapon Fighting (reroll 1s and 2s)")
    if bonus_action:
        notes.append("Bonus action")
    for note in list(extra_notes or []):
        note_text = str(note or "").strip().rstrip(".")
        if note_text:
            notes.append(note_text)
    if not notes:
        return ""
    return ", ".join(notes) + "."


def _build_equipment_choice_fields(equipment_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for group in equipment_groups:
        field_name = str(group.get("field_name") or "").strip()
        if not field_name:
            continue
        fields.append(
            {
                "name": field_name,
                "label": str(group.get("field_label") or "Equipment Choice"),
                "help_text": str(group.get("help_text") or "Choose your starting equipment."),
                "options": [
                    _choice_option(str(option.get("label") or ""), str(option.get("value") or ""))
                    for option in list(group.get("options") or [])
                    if str(option.get("value") or "").strip()
                ],
                "selected": str(group.get("selected") or "").strip(),
                "group_key": field_name,
                "kind": "equipment",
            }
        )
    return fields


def _build_campaign_page_choice_options(
    campaign_page_records: list[Any],
    *,
    include_items: bool,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_page_refs: set[str] = set()
    for record in list(campaign_page_records or []):
        page_ref = _extract_campaign_page_ref(record)
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            continue
        section = str(getattr(page, "section", "") or "").strip()
        if section == CAMPAIGN_SESSIONS_SECTION:
            continue
        campaign_option = build_campaign_page_character_option(
            record,
            default_kind="item" if section == CAMPAIGN_ITEMS_SECTION else "feature",
        )
        option_kind = (
            str((campaign_option or {}).get("kind") or "").strip()
            if campaign_option is not None
            else ("item" if section == CAMPAIGN_ITEMS_SECTION else "feature")
        )
        if include_items and option_kind != "item":
            continue
        if not include_items and option_kind != "feature":
            continue
        if page_ref in seen_page_refs:
            continue
        seen_page_refs.add(page_ref)
        title = str(getattr(page, "title", "") or "").strip() or page_ref
        option_title = str((campaign_option or {}).get("display_name") or title).strip() or title
        subsection = str(getattr(page, "subsection", "") or "").strip()
        summary = str(getattr(page, "summary", "") or "").strip()
        label_parts = [option_title]
        if section:
            label_parts.append(f"{section} / {subsection}" if subsection else section)
        options.append(
            {
                "value": page_ref,
                "label": " | ".join(part for part in label_parts if part),
                "title": option_title,
                "summary": summary,
                "campaign_option": dict(campaign_option or {}),
            }
        )
    return options


def _build_campaign_feature_choice_fields(
    campaign_feature_options: list[dict[str, str]],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if not campaign_feature_options:
        return []
    fields: list[dict[str, Any]] = []
    for index in range(1, CAMPAIGN_FEATURE_CHOICE_SLOTS + 1):
        field_name = f"campaign_feature_page_ref_{index}"
        fields.append(
            {
                "name": field_name,
                "label": f"Campaign Feature {index}",
                "help_text": "Optional. Link a published campaign wiki mechanic, boon, or other player-safe feature page into the character at creation time.",
                "options": [dict(option) for option in campaign_feature_options],
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": field_name,
                "kind": "campaign_page_feature",
                "required": False,
            }
        )
    return fields


def _build_campaign_item_choice_fields(
    campaign_item_options: list[dict[str, str]],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if not campaign_item_options:
        return []
    fields: list[dict[str, Any]] = []
    for index in range(1, CAMPAIGN_ITEM_CHOICE_SLOTS + 1):
        field_name = f"campaign_item_page_ref_{index}"
        fields.append(
            {
                "name": field_name,
                "label": f"Campaign Item {index}",
                "help_text": "Optional. Add a published campaign wiki item page to the new character's starting inventory.",
                "options": [dict(option) for option in campaign_item_options],
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": field_name,
                "kind": "campaign_page_item",
                "required": False,
            }
        )
    return fields


def _extract_campaign_page_ref(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("page_ref") or payload.get("slug") or "").strip()
    return str(getattr(payload, "page_ref", "") or "").strip()


def _selected_campaign_choice_options(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            kind = str(field.get("kind") or "").strip()
            if kind not in {"campaign_page_feature", "campaign_page_item"}:
                continue
            group_key = str(field.get("group_key") or field.get("name") or "").strip()
            for selected_value in list(selected_choices.get(group_key) or []):
                option = _resolve_choice_option(choice_sections, group_key, selected_value)
                if option:
                    option["field_kind"] = kind
                    options.append(option)
    return options


def _selected_campaign_option_payloads(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    extra_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payloads = [
        dict(option.get("campaign_option") or {})
        for option in _selected_campaign_choice_options(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
        )
        if isinstance(option.get("campaign_option"), dict)
    ]
    payloads.extend(
        dict(payload)
        for payload in list(extra_option_payloads or [])
        if isinstance(payload, dict) and dict(payload)
    )
    return payloads


def _campaign_option_payloads_from_selected_entries(entries: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for entry in list(entries or []):
        campaign_option = _entry_campaign_option(entry)
        if campaign_option:
            payloads.append(dict(campaign_option))
    return payloads


def _campaign_option_payloads_from_feat_selections(
    feat_selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for selection in list(feat_selections or []):
        campaign_option = dict(selection.get("campaign_option") or {})
        if not campaign_option:
            campaign_option = _entry_campaign_option(selection.get("entry"))
        if campaign_option:
            payloads.append(dict(campaign_option))
    return payloads


def _campaign_option_payloads_from_feature_entries(
    feature_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            continue
        campaign_option = _entry_campaign_option(entry)
        if campaign_option:
            payloads.append(dict(campaign_option))
    return payloads


def _campaign_option_payloads_from_definition(definition: CharacterDefinition) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for feature in list(definition.features or []):
        if isinstance(feature.get("campaign_option"), dict):
            payloads.append(dict(feature.get("campaign_option") or {}))
    for item in list(definition.equipment_catalog or []):
        if isinstance(item.get("campaign_option"), dict):
            payloads.append(dict(item.get("campaign_option") or {}))
    return payloads


def _spell_support_feature_entries_from_progressions(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
    selected_choices: dict[str, list[str]] | None = None,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def append_entry(entry: SystemsEntryRecord | None) -> None:
        if not isinstance(entry, SystemsEntryRecord):
            return
        if normalize_lookup(entry.entry_type) not in {
            normalize_lookup("classfeature"),
            normalize_lookup("subclassfeature"),
            normalize_lookup("optionalfeature"),
        }:
            return
        metadata = dict(entry.metadata or {})
        if not metadata.get("additional_spells") and not metadata.get("spell_support"):
            return
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if not entry_key or entry_key in seen_keys:
            return
        seen_keys.add(entry_key)
        feature_entries.append({"entry": entry})

    for progression in (class_progression, subclass_progression):
        for group in list(progression or []):
            if int(group.get("level") or 0) > target_level:
                continue
            for feature_row in list(group.get("feature_rows") or []):
                append_entry(feature_row.get("entry"))
    if selected_choices:
        for feature_entry in _collect_progression_feature_entries(
            progression=class_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_class_options",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
        for feature_entry in _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_subclass_options",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
        for feature_entry in _collect_progression_feature_entries(
            progression=class_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="class_option",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
        for feature_entry in _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="subclass_option",
            optionalfeature_catalog=optionalfeature_catalog,
        ):
            append_entry(feature_entry.get("entry"))
    return feature_entries


def _build_selected_campaign_item_specs(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for option in _selected_campaign_choice_options(
        choice_sections=choice_sections,
        selected_choices=selected_choices,
    ):
        page_ref = str(option.get("value") or "").strip()
        campaign_option = dict(option.get("campaign_option") or {})
        kind = str(campaign_option.get("kind") or "").strip()
        field_kind = str(option.get("field_kind") or "").strip()
        if kind and kind != "item":
            continue
        if not kind and field_kind != "campaign_page_item":
            continue
        title = str(
            campaign_option.get("item_name")
            or option.get("title")
            or option.get("label")
            or page_ref
        ).strip()
        if not page_ref or not title:
            continue
        specs.append(
            {
                "name": title,
                "quantity": int(campaign_option.get("quantity") or 1),
                "weight": str(campaign_option.get("weight") or "").strip(),
                "notes": str(campaign_option.get("notes") or option.get("summary") or "").strip(),
                "page_ref": page_ref,
                "source_kind": "builder_campaign_page",
                "campaign_option": campaign_option or None,
            }
        )
    return specs


def _build_spell_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    feat_spell_fields = _build_feat_spell_choice_fields(
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        target_level=1,
    )
    spell_support_fields = _build_spell_support_choice_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        group_key_prefix="spell_support",
        feature_entries=feature_entries,
    )
    if selected_class is None:
        return spell_support_fields + feat_spell_fields
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(class_name, selected_class=selected_class)
    cantrip_count = _spell_progression_value(
        class_name,
        "cantrip_progression",
        1,
        selected_class=selected_class,
    )
    spellbook_count = _spell_progression_value(
        class_name,
        "spells_known_progression_fixed",
        1,
        selected_class=selected_class,
    )
    level_one_count = _spell_progression_value(
        class_name,
        "spells_known_progression",
        1,
        selected_class=selected_class,
    )
    prepared_count = _prepared_spell_count_for_level(
        class_name,
        _coerce_ability_scores(values),
        1,
        selected_class=selected_class,
    )
    slot_progression = _spell_slot_progression_for_class_level(
        class_name,
        1,
        selected_class=selected_class,
    )
    has_level_one_spellcasting = bool(slot_progression) or cantrip_count > 0 or level_one_count > 0 or spellbook_count > 0
    fields: list[dict[str, Any]] = []
    if spell_mode and has_level_one_spellcasting:
        automatic_known_lookup_keys = _automatic_known_spell_lookup_keys(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=1,
            feature_entries=feature_entries,
        )
        automatic_spell_support_lookup_keys = _automatic_spell_support_lookup_keys(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=1,
            feature_entries=feature_entries,
        )
        selected_bonus_known_values = _selected_form_spell_values_by_field_prefix(values, prefix="bonus_spell_known_")

        cantrip_options = [
            option
            for option in _build_spell_options_for_class_level(
                class_name,
                "0",
                spell_catalog,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                feature_entries=feature_entries,
            )
            if str(option.get("value") or "").strip()
            not in (automatic_known_lookup_keys | automatic_spell_support_lookup_keys | selected_bonus_known_values)
        ]
        if cantrip_options:
            for index in range(cantrip_count):
                field_name = f"spell_cantrip_{index + 1}"
                fields.append(
                    {
                        "name": field_name,
                        "label": f"Cantrip {index + 1}",
                        "help_text": f"Choose a {class_name} cantrip.",
                        "options": cantrip_options,
                        "selected": str(values.get(field_name) or "").strip(),
                        "group_key": "spell_cantrips",
                        "kind": "spell",
                    }
                )

        fields.extend(
            _build_additional_known_spell_choice_fields(
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                spell_catalog=spell_catalog,
                target_level=1,
                values=values,
                field_prefix="bonus_spell_known",
                group_key_prefix="bonus_spell_known",
                feature_entries=feature_entries,
            )
        )
        fields.extend(spell_support_fields)
        level_one_options = [
            option
            for option in _build_spell_options_for_class_level(
                class_name,
                "1",
                spell_catalog,
                selected_class=selected_class,
                selected_subclass=selected_subclass,
                feature_entries=feature_entries,
            )
            if str(option.get("value") or "").strip()
            not in (automatic_known_lookup_keys | automatic_spell_support_lookup_keys | selected_bonus_known_values)
        ]
        automatic_prepared_lookup_keys = _automatic_prepared_spell_lookup_keys(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=1,
            feature_entries=feature_entries,
        )
        if spell_mode == "prepared" and automatic_prepared_lookup_keys:
            level_one_options = [
                option
                for option in level_one_options
                if str(option.get("value") or "").strip()
                not in (automatic_prepared_lookup_keys | automatic_spell_support_lookup_keys)
            ]
        if level_one_options:
            if spell_mode == "wizard":
                for index in range(spellbook_count):
                    field_name = f"wizard_spellbook_{index + 1}"
                    fields.append(
                        {
                            "name": field_name,
                            "label": f"Spellbook Spell {index + 1}",
                            "help_text": "Choose a 1st-level wizard spell for your spellbook.",
                            "options": level_one_options,
                            "selected": str(values.get(field_name) or "").strip(),
                            "group_key": "wizard_spellbook",
                            "kind": "spell",
                        }
                    )

                selected_spellbook_values = [
                    str(values.get(f"wizard_spellbook_{index + 1}") or "").strip()
                    for index in range(spellbook_count)
                    if str(values.get(f"wizard_spellbook_{index + 1}") or "").strip()
                ]
                prepared_options = (
                    [option for option in level_one_options if option["value"] in selected_spellbook_values]
                    if selected_spellbook_values
                    else level_one_options
                )
                for index in range(prepared_count):
                    field_name = f"wizard_prepared_{index + 1}"
                    fields.append(
                        {
                            "name": field_name,
                            "label": f"Prepared Spell {index + 1}",
                            "help_text": "Choose a prepared wizard spell from your selected spellbook spells.",
                            "options": prepared_options,
                            "selected": str(values.get(field_name) or "").strip(),
                            "group_key": "wizard_prepared",
                            "kind": "spell",
                        }
                    )
            else:
                selection_count = level_one_count if spell_mode == "known" else prepared_count
                label_prefix = "Known Spell" if spell_mode == "known" else "Prepared Spell"
                help_text = (
                    f"Choose a {class_name} spell you know."
                    if spell_mode == "known"
                    else f"Choose a {class_name} spell you have prepared."
                )
                for index in range(selection_count):
                    field_name = f"spell_level_one_{index + 1}"
                    fields.append(
                        {
                            "name": field_name,
                            "label": f"{label_prefix} {index + 1}",
                            "help_text": help_text,
                            "options": level_one_options,
                            "selected": str(values.get(field_name) or "").strip(),
                            "group_key": "spell_level_one",
                            "kind": "spell",
                        }
                    )
    else:
        fields.extend(spell_support_fields)

    replacement_fields = _build_level_one_spell_support_replacement_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        existing_fields=fields + feat_spell_fields,
        feature_entries=feature_entries,
        campaign_option_payloads=campaign_option_payloads,
    )
    return fields + replacement_fields + feat_spell_fields


def _build_level_one_spell_support_replacement_fields(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    existing_fields: list[dict[str, Any]],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    provisional_choice_sections = [{"title": "Spell Choices", "fields": list(existing_fields or [])}]
    _, provisional_selected_choices = _resolve_builder_choices(provisional_choice_sections, values, strict=False)
    provisional_spell_payloads = _build_level_one_spell_payloads(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=provisional_choice_sections,
        selected_choices=provisional_selected_choices,
        spell_catalog=spell_catalog,
        feature_entries=feature_entries,
        campaign_option_payloads=campaign_option_payloads,
    )
    return _build_spell_support_replacement_fields(
        existing_spells=provisional_spell_payloads,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        feature_entries=feature_entries,
    )


def _build_level_up_spell_choice_fields(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    target_level: int,
    ability_scores: dict[str, int],
    values: dict[str, str],
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(class_name, selected_class=selected_class)
    feat_spell_fields = _build_feat_spell_choice_fields(
        feat_selections=feat_selections,
        spell_catalog=spell_catalog,
        values=values,
        target_level=target_level,
    )
    slot_progression = _spell_slot_progression_for_class_level(
        class_name,
        target_level,
        selected_class=selected_class,
    )
    max_spell_level = max((int(slot.get("level") or 0) for slot in slot_progression), default=0)
    existing_spells = list((definition.spellcasting or {}).get("spells") or [])
    existing_cantrip_values = _spell_selection_values_by_mark(existing_spells, "Cantrip", exclude_bonus_known=True)
    existing_known_values = _spell_selection_values_by_mark(existing_spells, "Known", exclude_bonus_known=True)
    existing_prepared_values = _spell_selection_values_by_mark(existing_spells, "Prepared")
    existing_spellbook_values = _spell_selection_values_by_mark(existing_spells, "Spellbook")
    existing_always_prepared_values = {
        payload_key
        for spell_payload in existing_spells
        if bool(spell_payload.get("is_always_prepared")) and (payload_key := _spell_payload_key(spell_payload))
    }
    target_always_prepared_values = _automatic_prepared_spell_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
    )
    target_known_bonus_values = _automatic_known_spell_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
    )
    target_spell_support_lookup_keys = _automatic_spell_support_lookup_keys(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        exact_level=target_level,
        feature_entries=feature_entries,
    )
    selected_bonus_known_values = _selected_form_spell_values_by_field_prefix(values, prefix="levelup_bonus_spell_known_")

    fields: list[dict[str, Any]] = []
    fields.extend(
        _build_spell_support_choice_fields(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=target_level,
            exact_level=target_level,
            values=values,
            field_prefix="levelup_spell_support",
            group_key_prefix="levelup_spell_support",
            feature_entries=feature_entries,
        )
    )
    structured_replacement_fields = _build_spell_support_replacement_fields(
        existing_spells=existing_spells,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        values=values,
        field_prefix="levelup_spell_support",
        exact_level=target_level,
        feature_entries=feature_entries,
    )
    fields.extend(structured_replacement_fields)
    if not spell_mode:
        return fields + feat_spell_fields

    target_cantrip_count = _spell_progression_value(
        class_name,
        "cantrip_progression",
        target_level,
        selected_class=selected_class,
    )
    additional_cantrips = max(target_cantrip_count - len(existing_cantrip_values), 0)
    cantrip_options = [
        option
        for option in _build_spell_options_for_class_level(
            class_name,
            "0",
            spell_catalog,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feature_entries=feature_entries,
        )
        if option["value"]
        not in (
            existing_cantrip_values
            | target_known_bonus_values
            | target_spell_support_lookup_keys
            | selected_bonus_known_values
        )
    ]
    if cantrip_options:
        for index in range(additional_cantrips):
            field_name = f"levelup_spell_cantrip_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Cantrip {index + 1}",
                    "help_text": f"Choose a new {class_name} cantrip for level {target_level}.",
                    "options": cantrip_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_spell_cantrips",
                    "kind": "spell",
                }
            )

    fields.extend(
        _build_additional_known_spell_choice_fields(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            target_level=target_level,
            exact_level=target_level,
            values=values,
            field_prefix="levelup_bonus_spell_known",
            group_key_prefix="levelup_bonus_spell_known",
            feature_entries=feature_entries,
        )
    )

    if max_spell_level <= 0:
        return fields + feat_spell_fields

    spell_level_options = _build_spell_options_for_class_levels(
        class_name,
        range(1, max_spell_level + 1),
        spell_catalog,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feature_entries=feature_entries,
    )
    if not spell_level_options and spell_mode != "wizard":
        return fields + feat_spell_fields

    if spell_mode == "known":
        target_known_count = _spell_progression_value(
            class_name,
            "spells_known_progression",
            target_level,
            selected_class=selected_class,
        )
        additional_known = max(target_known_count - len(existing_known_values), 0)
        options = [
            option
            for option in spell_level_options
            if option["value"]
            not in (
                existing_known_values
                | target_known_bonus_values
                | target_spell_support_lookup_keys
                | selected_bonus_known_values
            )
        ]
        if additional_known > 0 and not options:
            return fields + feat_spell_fields
        for index in range(additional_known):
            field_name = f"levelup_spell_known_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Spell {index + 1}",
                    "help_text": f"Choose a new {class_name} spell for level {target_level}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_spell_known",
                    "kind": "spell",
                }
            )
        fields.extend(
            []
            if structured_replacement_fields
            else _build_level_up_known_spell_replacement_fields(
                existing_spells=existing_spells,
                existing_known_values=existing_known_values,
                replacement_options=options,
                spell_catalog=spell_catalog,
                values=values,
            )
        )
        return fields + feat_spell_fields

    if spell_mode == "prepared":
        target_prepared_count = _prepared_spell_count_for_level(
            class_name,
            ability_scores,
            target_level,
            selected_class=selected_class,
        )
        additional_prepared = max(target_prepared_count - len(existing_prepared_values), 0)
        excluded_values = (
            existing_prepared_values
            | existing_always_prepared_values
            | target_always_prepared_values
            | target_spell_support_lookup_keys
        )
        options = [option for option in spell_level_options if option["value"] not in excluded_values]
        if additional_prepared > 0 and not options:
            return fields + feat_spell_fields
        for index in range(additional_prepared):
            field_name = f"levelup_prepared_spell_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Prepared Spell {index + 1}",
                    "help_text": f"Choose a new prepared {class_name} spell for level {target_level}.",
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_prepared_spells",
                    "kind": "spell",
                }
            )
        return fields + feat_spell_fields

    if spell_mode == "wizard":
        new_spellbook_spells = _spell_progression_value(
            class_name,
            "spells_known_progression_fixed",
            target_level,
            selected_class=selected_class,
        )
        spellbook_options = [option for option in spell_level_options if option["value"] not in existing_spellbook_values]
        if new_spellbook_spells > 0 and not spellbook_options:
            return fields + feat_spell_fields
        for index in range(new_spellbook_spells):
            field_name = f"levelup_wizard_spellbook_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Spellbook Spell {index + 1}",
                    "help_text": f"Choose a wizard spell of 1st through level {max_spell_level} to add to your spellbook.",
                    "options": spellbook_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_wizard_spellbook",
                    "kind": "spell",
                }
            )
        new_spellbook_values = [
            str(values.get(f"levelup_wizard_spellbook_{index + 1}") or "").strip()
            for index in range(new_spellbook_spells)
            if str(values.get(f"levelup_wizard_spellbook_{index + 1}") or "").strip()
        ]
        prepared_options = [
            option
            for option in spell_level_options
            if option["value"] in (existing_spellbook_values | set(new_spellbook_values))
            and option["value"] not in (existing_prepared_values | target_always_prepared_values | target_spell_support_lookup_keys)
        ]
        target_prepared_count = _prepared_spell_count_for_level(
            class_name,
            ability_scores,
            target_level,
            selected_class=selected_class,
        )
        additional_prepared = max(target_prepared_count - len(existing_prepared_values), 0)
        if additional_prepared > 0 and not prepared_options:
            return fields + feat_spell_fields
        for index in range(additional_prepared):
            field_name = f"levelup_wizard_prepared_{index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"New Prepared Spell {index + 1}",
                    "help_text": "Choose an additional prepared wizard spell from your spellbook.",
                    "options": prepared_options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": "levelup_wizard_prepared",
                    "kind": "spell",
                }
            )
        return fields + feat_spell_fields

    return fields + feat_spell_fields


def _build_level_up_known_spell_replacement_fields(
    *,
    existing_spells: list[dict[str, Any]],
    existing_known_values: set[str],
    replacement_options: list[dict[str, str]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if not existing_known_values or not replacement_options:
        return []
    replace_from_options = _build_spell_options_from_payload_keys(
        payload_keys=existing_known_values,
        existing_spells=existing_spells,
        spell_catalog=spell_catalog,
    )
    if not replace_from_options:
        return []
    return [
        {
            "name": "levelup_spell_replace_from_1",
            "label": "Replace Known Spell",
            "help_text": "Optionally choose a spell you are replacing this level.",
            "options": replace_from_options,
            "selected": str(values.get("levelup_spell_replace_from_1") or "").strip(),
            "group_key": "levelup_spell_replace_from_1",
            "kind": "spell",
            "required": False,
        },
        {
            "name": "levelup_spell_replace_to_1",
            "label": "Replacement Spell",
            "help_text": "Choose the new spell that replaces your selected known spell.",
            "options": replacement_options,
            "selected": str(values.get("levelup_spell_replace_to_1") or "").strip(),
            "group_key": "levelup_spell_replace_to_1",
            "kind": "spell",
            "required": False,
        },
    ]


def _build_spell_options_from_payload_keys(
    *,
    payload_keys: set[str],
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    remaining_keys = set(payload_keys)
    for spell_payload in existing_spells:
        payload_key = _spell_payload_key(spell_payload)
        if not payload_key or payload_key not in remaining_keys:
            continue
        entry = _resolve_spell_entry(payload_key, spell_catalog)
        value = entry.slug if entry is not None else payload_key
        label = entry.title if entry is not None else str(spell_payload.get("name") or payload_key).strip()
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        remaining_keys.discard(payload_key)
        options.append(_choice_option(label, value))
    for payload_key in sorted(remaining_keys):
        entry = _resolve_spell_entry(payload_key, spell_catalog)
        value = entry.slug if entry is not None else payload_key
        label = entry.title if entry is not None else payload_key
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        options.append(_choice_option(label, value))
    return options


def _class_spell_progression(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    progression = dict(_load_phb_class_progression().get(str(class_name or "").strip()) or {})
    if selected_class is None:
        return progression

    metadata = dict(selected_class.metadata or {})
    for key in (
        "spellcasting_ability",
        "caster_progression",
        "prepared_spells",
        "prepared_spells_change",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            progression[key] = value
    for key in (
        "cantrip_progression",
        "spells_known_progression",
        "spells_known_progression_fixed",
        "prepared_spells_progression",
    ):
        values = [int(value or 0) for value in list(metadata.get(key) or [])]
        if values:
            progression[key] = values
    slot_rows: list[list[dict[str, Any]]] = []
    for row in list(metadata.get("slot_progression") or []):
        normalized_row: list[dict[str, Any]] = []
        for slot in list(row or []):
            slot_payload = dict(slot or {})
            level = int(slot_payload.get("level") or 0)
            max_slots = int(slot_payload.get("max_slots") or 0)
            if level > 0 and max_slots > 0:
                normalized_row.append({"level": level, "max_slots": max_slots})
        slot_rows.append(normalized_row)
    if slot_rows:
        progression["slot_progression"] = slot_rows
    return progression


def _spellcasting_mode_for_class(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> str:
    progression = _class_spell_progression(class_name, selected_class=selected_class)
    if list(progression.get("spells_known_progression_fixed") or []):
        return "wizard"
    if str(progression.get("prepared_spells") or "").strip() or list(progression.get("prepared_spells_progression") or []):
        return "prepared"
    if list(progression.get("spells_known_progression") or []):
        return "known"
    return ""


def _spellcasting_ability_name_for_class(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> str:
    progression = _class_spell_progression(class_name, selected_class=selected_class)
    ability_key = str(progression.get("spellcasting_ability") or "").strip()
    if ability_key in ABILITY_LABELS:
        return ABILITY_LABELS[ability_key]
    return SPELLCASTING_ABILITY_BY_CLASS.get(class_name, "")


def _spell_progression_value(
    class_name: str,
    key: str,
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> int:
    progression = _class_spell_progression(class_name, selected_class=selected_class)
    values = list(progression.get(key) or [])
    if 1 <= target_level <= len(values):
        return max(int(values[target_level - 1] or 0), 0)
    return 0


def _spell_slot_progression_for_class_level(
    class_name: str,
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> list[dict[str, Any]]:
    progression = _class_spell_progression(class_name, selected_class=selected_class)
    slot_rows = list(progression.get("slot_progression") or [])
    if 1 <= target_level <= len(slot_rows):
        return [dict(slot) for slot in list(slot_rows[target_level - 1] or [])]
    if target_level == 1:
        return list(LEVEL_ONE_SPELL_SLOTS_BY_CLASS.get(class_name, []))
    return []


def _prepared_spell_count_for_level(
    class_name: str,
    ability_scores: dict[str, int],
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> int:
    progression = _class_spell_progression(class_name, selected_class=selected_class)
    prepared_progression = list(progression.get("prepared_spells_progression") or [])
    if 1 <= target_level <= len(prepared_progression):
        return max(int(prepared_progression[target_level - 1] or 0), 0)
    formula = str(progression.get("prepared_spells") or "").strip()
    if formula:
        return _evaluate_prepared_spell_formula(formula, ability_scores, target_level)
    return 0


def _evaluate_prepared_spell_formula(
    formula: str,
    ability_scores: dict[str, int],
    target_level: int,
) -> int:
    match = re.fullmatch(r"<\$level\$>(?:\s*/\s*(\d+))?\s*\+\s*<\$([a-z]+)_mod\$>", str(formula or "").strip())
    if match is None:
        return 0
    divisor_text, ability_key = match.groups()
    clean_ability_key = str(ability_key or "").strip().lower()
    if clean_ability_key not in ABILITY_KEYS:
        return 0
    level_value = int(target_level or 0)
    if divisor_text:
        divisor = max(int(divisor_text or 1), 1)
        level_value //= divisor
    modifier = _ability_modifier(ability_scores.get(clean_ability_key, DEFAULT_ABILITY_SCORE))
    return max(level_value + modifier, 1)


def _build_spell_options_for_class_level(
    class_name: str,
    level_key: str,
    spell_catalog: dict[str, Any],
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    try:
        spell_level = int(str(level_key or "0").strip())
    except ValueError:
        spell_level = 0
    titles: list[str] = []
    if selected_class is not None:
        titles.extend(
            entry.title
            for entry in list(spell_catalog.get("entries") or [])
            if int((entry.metadata or {}).get("level") if (entry.metadata or {}).get("level") is not None else -1) == spell_level
            and _spell_entry_matches_class_list(entry, selected_class)
        )
    if not titles:
        titles.extend(
            dict(dict(spell_catalog.get("phb_level_one_lists") or {}).get(class_name) or {}).get(str(level_key)) or []
        )
    titles.extend(
        _expanded_spell_titles_for_level(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            spell_catalog=spell_catalog,
            spell_level=spell_level,
            feature_entries=feature_entries,
        )
    )
    return _build_spell_options_from_titles(titles, spell_catalog)


def _spell_entry_matches_class_list(
    spell_entry: SystemsEntryRecord,
    selected_class: SystemsEntryRecord,
) -> bool:
    class_lists = dict((spell_entry.metadata or {}).get("class_lists") or {})
    selected_source_id = str(selected_class.source_id or "").strip().upper()
    selected_title = normalize_lookup(selected_class.title)
    if selected_source_id:
        source_titles = [
            normalize_lookup(title)
            for title in list(class_lists.get(selected_source_id) or [])
            if str(title).strip()
        ]
        if selected_title and selected_title in source_titles:
            return True
    for titles in class_lists.values():
        normalized_titles = [normalize_lookup(title) for title in list(titles or []) if str(title).strip()]
        if selected_title and selected_title in normalized_titles:
            return True
    return False


def _build_spell_options_for_class_levels(
    class_name: str,
    level_keys: range | list[int],
    spell_catalog: dict[str, Any],
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for level_key in level_keys:
        for option in _build_spell_options_for_class_level(
            class_name,
            str(level_key),
            spell_catalog,
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feature_entries=feature_entries,
        ):
            value = str(option.get("value") or "").strip()
            if not value or value in seen_values:
                continue
            seen_values.add(value)
            options.append(dict(option))
    return options


def _level_one_spell_selection_count(spell_rules: dict[str, Any], values: dict[str, str]) -> int:
    explicit_count = spell_rules.get("level_one_count")
    if explicit_count is not None:
        return max(int(explicit_count or 0), 0)
    ability_key = str(spell_rules.get("ability_key") or "").strip()
    if ability_key and ability_key in ABILITY_KEYS:
        modifier = _ability_modifier(_coerce_ability_scores(values).get(ability_key, DEFAULT_ABILITY_SCORE))
        return max(1 + modifier, 1)
    return 0


def _normalize_preview_values(values: dict[str, str]) -> dict[str, str]:
    normalized = {key: str(value) for key, value in dict(values or {}).items()}
    normalized.setdefault("name", "")
    normalized.setdefault("character_slug", "")
    normalized.setdefault("alignment", "")
    normalized.setdefault("experience_model", DEFAULT_EXPERIENCE_MODEL)
    for ability_key in ABILITY_KEYS:
        normalized.setdefault(ability_key, str(DEFAULT_ABILITY_SCORE))
    return normalized


def _build_level_one_preview(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    equipment_groups: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    feat_catalog: dict[str, Any],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    item_catalog: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any]:
    feat_selections = _resolve_builder_feat_selections(values, feat_catalog)
    ability_scores = _coerce_ability_scores(values)
    proficiency_bonus = 2
    class_name = selected_class.title if selected_class is not None else ""
    fixed_proficiencies, selected_choices = _resolve_builder_choices(choice_sections, values, strict=False)
    feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_selected_entries([selected_species, selected_background])
        + _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(feature_entries)
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        ability_scores,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=False,
    )
    proficiencies = _build_level_one_proficiencies(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        fixed_proficiencies=fixed_proficiencies,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        feat_selections=feat_selections,
        campaign_option_payloads=selected_campaign_option_payloads,
    )
    skills = _build_skills_payload(ability_scores, proficiencies["skills"], proficiency_bonus)
    equipment_catalog = _build_level_one_equipment_catalog(
        equipment_groups,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        item_catalog=item_catalog,
    )
    spellcasting = (
        _build_level_one_spellcasting(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            feat_selections=feat_selections,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            spell_catalog=spell_catalog,
            feature_entries=feature_entries,
            campaign_option_payloads=selected_campaign_option_payloads,
        )
        if selected_class is not None
        else {"spells": []}
    )
    feature_payloads, resource_templates = _build_feature_payloads(
        feature_entries,
        ability_scores=ability_scores,
        current_level=1,
    )
    stats = (
        _build_level_one_stats(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            selected_species=selected_species,
            ability_scores=ability_scores,
            skills=skills,
            proficiency_bonus=proficiency_bonus,
            feat_selections=feat_selections,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            current_level=1,
            equipment_catalog=equipment_catalog,
            features=feature_payloads,
            item_catalog=item_catalog,
            campaign_option_payloads=selected_campaign_option_payloads,
        )
        if selected_class is not None and selected_species is not None
        else {}
    )
    attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=proficiencies["weapons"],
        selected_choices=selected_choices,
        features=feature_payloads,
    )
    feature_names = [
        str(feature.get("name") or feature.get("label") or "").strip()
        for feature in feature_payloads
        if str(feature.get("name") or feature.get("label") or "").strip()
    ]
    save_proficiencies = _dedupe_preserve_order(
        _class_save_proficiencies(selected_class)
        + _extract_feat_saving_throw_proficiencies(feat_selections, selected_choices)
    )
    return {
        "class_level_text": f"{class_name} 1" if class_name else "Level 1",
        "max_hp": int(stats.get("max_hp") or 0),
        "speed": str(stats.get("speed") or _extract_speed_label(selected_species)),
        "size": _extract_size_label(selected_species),
        "proficiency_bonus": proficiency_bonus,
        "saving_throws": [_humanize_saving_throw(code) for code in save_proficiencies],
        "languages": list(proficiencies["languages"]),
        "features": feature_names,
        "resources": [
            _summarize_preview_resource(template)
            for template in resource_templates
            if _summarize_preview_resource(template)
        ],
        "equipment": [
            _describe_equipment_spec(item)
            for item in equipment_catalog
            if not bool(item.get("is_currency_only")) and _describe_equipment_spec(item)
        ],
        "attacks": [
            f"{attack['name']} ({int(attack.get('attack_bonus') or 0):+d}, {attack.get('damage')})"
            for attack in attacks
            if str(attack.get("name") or "").strip()
        ],
        "starting_currency": _format_currency_seed(_collect_currency_seed_from_equipment(equipment_catalog)),
        "spells": [_summarize_preview_spell(spell) for spell in list(spellcasting.get("spells") or [])],
        "background": selected_background.title if selected_background is not None else "",
        "subclass": selected_subclass.title if selected_subclass is not None else "",
    }


def _parse_ability_scores(values: dict[str, str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for ability_key in ABILITY_KEYS:
        raw_value = str(values.get(ability_key) or "").strip()
        if not raw_value:
            raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} score is required.")
        try:
            score = int(raw_value)
        except ValueError as exc:
            raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} must be a whole number.") from exc
        if score < 1 or score > 30:
            raise CharacterBuildError(f"{ABILITY_LABELS[ability_key]} must be between 1 and 30.")
        scores[ability_key] = score
    return scores


def _coerce_ability_scores(values: dict[str, str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for ability_key in ABILITY_KEYS:
        try:
            scores[ability_key] = int(str(values.get(ability_key) or DEFAULT_ABILITY_SCORE).strip() or DEFAULT_ABILITY_SCORE)
        except ValueError:
            scores[ability_key] = DEFAULT_ABILITY_SCORE
    return scores


def _resolve_builder_choices(
    choice_sections: list[dict[str, Any]],
    values: dict[str, str],
    *,
    strict: bool = True,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    selected_choices: dict[str, list[str]] = {}
    paired_field_metadata: dict[str, dict[str, str]] = {}
    for section in choice_sections:
        grouped_values: dict[str, list[str]] = {}
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "")
            group_key = str(field.get("group_key") or field_name)
            is_required = bool(field.get("required", True))
            paired_field_name = str(field.get("paired_field_name") or "").strip()
            if paired_field_name:
                paired_field_metadata[field_name] = {
                    "label": str(field.get("label") or field_name).strip() or field_name,
                    "paired_field_name": paired_field_name,
                    "paired_label": str(field.get("paired_field_label") or paired_field_name).strip() or paired_field_name,
                }
            raw_value = str(values.get(field_name) or "").strip()
            allowed_values = {str(option.get("value") or "").strip() for option in list(field.get("options") or [])}
            selected_value = _normalize_selected_choice_value(raw_value, allowed_values)
            if not raw_value:
                if strict and is_required:
                    raise CharacterBuildError(f"{field.get('label') or 'A required choice'} is required.")
                continue
            if selected_value not in allowed_values:
                if strict:
                    raise CharacterBuildError(f"{field.get('label') or 'A choice'} is not valid for the current selection.")
                continue
            if selected_value:
                grouped_values.setdefault(group_key, []).append(selected_value)
        for group_key, group_values in grouped_values.items():
            if strict and len(group_values) != len(set(group_values)):
                raise CharacterBuildError("Choose distinct options when a choice group grants more than one selection.")
            selected_choices[group_key] = group_values
    if strict:
        _validate_paired_choice_fields(values, paired_field_metadata)

    fixed_proficiencies = {
        "skills": [],
        "languages": [],
        "tools": [],
    }
    return fixed_proficiencies, selected_choices


def _normalize_selected_choice_value(
    raw_value: str,
    allowed_values: set[str],
) -> str:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return ""
    if clean_value in allowed_values:
        return clean_value
    systems_value = f"{SYSTEMS_OPTION_PREFIX}{clean_value}"
    if systems_value in allowed_values:
        return systems_value
    page_value = f"{CAMPAIGN_PAGE_OPTION_PREFIX}{clean_value}"
    if page_value in allowed_values:
        return page_value
    return clean_value


def _validate_paired_choice_fields(
    values: dict[str, str],
    paired_field_metadata: dict[str, dict[str, str]],
) -> None:
    seen_pairs: set[tuple[str, str]] = set()
    for field_name, metadata in paired_field_metadata.items():
        paired_field_name = str(metadata.get("paired_field_name") or "").strip()
        if not paired_field_name:
            continue
        pair_key = tuple(sorted((field_name, paired_field_name)))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        left_value = str(values.get(field_name) or "").strip()
        right_value = str(values.get(paired_field_name) or "").strip()
        if bool(left_value) == bool(right_value):
            continue
        left_label = str(metadata.get("label") or field_name).strip() or field_name
        right_label = str(metadata.get("paired_label") or paired_field_name).strip() or paired_field_name
        raise CharacterBuildError(f"{left_label} and {right_label} must both be chosen together.")


def _apply_feat_ability_score_bonuses(
    base_scores: dict[str, int],
    *,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    strict: bool,
) -> dict[str, int]:
    updated_scores = dict(base_scores)
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        chosen_values = _feat_selected_values(selected_choices, instance_key, "ability")
        chosen_index = 0
        for block in list(metadata.get("ability") or []):
            if not isinstance(block, dict):
                continue
            for ability_key in ABILITY_KEYS:
                raw_bonus = block.get(ability_key)
                if isinstance(raw_bonus, (int, float)) and int(raw_bonus):
                    updated_scores[ability_key] = min(
                        int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + int(raw_bonus),
                        20,
                    )
            choose = dict(block.get("choose") or {})
            options = [str(option) for option in list(choose.get("from") or []) if str(option) in ABILITY_KEYS]
            count = max(int(choose.get("count") or 1), 0)
            amount = max(int(choose.get("amount") or 1), 1)
            if not options or count <= 0:
                continue
            selected_values = chosen_values[chosen_index : chosen_index + count]
            chosen_index += count
            if len(selected_values) < count:
                if strict:
                    raise CharacterBuildError(f"Choose the ability increase for {feat_entry.title}.")
                continue
            for ability_key in selected_values:
                if ability_key not in options:
                    if strict:
                        raise CharacterBuildError(f"Choose a valid ability increase for {feat_entry.title}.")
                    continue
                updated_scores[ability_key] = min(
                    int(updated_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + amount,
                    20,
                )
    return updated_scores


def _extract_feat_skill_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("skill_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if "choose" in block or int(block.get("any") or 0) > 0:
                results.extend(_skill_label(value) for value in _feat_selected_values(selected_choices, instance_key, "skills"))
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_skill_label(key))
        for value in _feat_selected_values(selected_choices, instance_key, "skill_tool_language"):
            if str(value).startswith("skill:"):
                results.append(_skill_label(str(value).split(":", 1)[1]))
    return _dedupe_preserve_order(results)


def _extract_feat_language_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("language_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if int(block.get("anyStandard") or block.get("any") or 0) > 0:
                results.extend(_feat_selected_values(selected_choices, instance_key, "languages"))
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_humanize_proficiency_value(key, category="languages"))
        for value in _feat_selected_values(selected_choices, instance_key, "skill_tool_language"):
            if str(value).startswith("language:"):
                results.append(str(value).split(":", 1)[1])
    return _dedupe_preserve_order(results)


def _extract_feat_tool_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("tool_proficiencies") or []):
            if isinstance(block, str):
                cleaned = _clean_embedded_text(block)
                if cleaned:
                    results.append(cleaned)
                continue
            if not isinstance(block, dict):
                continue
            if int(block.get("any") or block.get("anyTool") or block.get("anyArtisansTool") or 0) > 0:
                results.extend(_feat_selected_values(selected_choices, instance_key, "tools"))
                continue
            for key, value in block.items():
                if value is True:
                    cleaned = _clean_embedded_text(key)
                    if cleaned:
                        results.append(cleaned)
        for value in _feat_selected_values(selected_choices, instance_key, "skill_tool_language"):
            if str(value).startswith("tool:"):
                results.append(str(value).split(":", 1)[1])
    return _dedupe_preserve_order(results)


def _extract_feat_armor_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    del selected_choices
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if not isinstance(feat_entry, SystemsEntryRecord):
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("armor_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_humanize_proficiency_value(key, category="armor"))
    return _dedupe_preserve_order(results)


def _extract_feat_weapon_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("weapon_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if "choose" in block:
                results.extend(_feat_selected_values(selected_choices, instance_key, "weapons"))
                continue
            for key, value in block.items():
                if value is True:
                    results.append(_humanize_proficiency_value(key, category="weapons"))
    return _dedupe_preserve_order(results)


def _extract_feat_saving_throw_proficiencies(
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[str]:
    results: list[str] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        if normalize_lookup(feat_entry.title) == normalize_lookup("Resilient"):
            results.extend(
                ability_key
                for ability_key in _feat_selected_values(selected_choices, instance_key, "ability")
                if ability_key in ABILITY_KEYS
            )
            continue
        metadata = dict(feat_entry.metadata or {})
        for block in list(metadata.get("saving_throw_proficiencies") or []):
            if not isinstance(block, dict):
                continue
            if "choose" in block:
                results.extend(
                    ability_key
                    for ability_key in _feat_selected_values(selected_choices, instance_key, "saving_throws")
                    if ability_key in ABILITY_KEYS
                )
                continue
            for key, value in block.items():
                if value is True and key in ABILITY_KEYS:
                    results.append(key)
    return _dedupe_preserve_order(results)


def _feat_initiative_bonus(feat_selections: list[dict[str, Any]]) -> int:
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if isinstance(feat_entry, SystemsEntryRecord) and normalize_lookup(feat_entry.title) == normalize_lookup("Alert"):
            return 5
    return 0


def _feat_speed_bonus(feat_selections: list[dict[str, Any]]) -> int:
    bonus = 0
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if isinstance(feat_entry, SystemsEntryRecord) and normalize_lookup(feat_entry.title) == normalize_lookup("Mobile"):
            bonus += 10
    return bonus


def _apply_speed_bonus_to_label(speed_label: str, bonus: int) -> str:
    clean_label = str(speed_label or "").strip()
    if not clean_label or not bonus:
        return clean_label
    match = re.search(r"(\d+)", clean_label)
    if not match:
        return clean_label
    return clean_label[: match.start(1)] + str(int(match.group(1)) + int(bonus)) + clean_label[match.end(1) :]


def _feat_passive_bonus(
    feat_selections: list[dict[str, Any]],
    *,
    skill_name: str,
) -> int:
    normalized_skill = normalize_lookup(skill_name)
    bonus = 0
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if not isinstance(feat_entry, SystemsEntryRecord):
            continue
        normalized_title = normalize_lookup(feat_entry.title)
        if normalized_title == normalize_lookup("Observant") and normalized_skill in {"perception", "investigation"}:
            bonus += 5
    return bonus


def _feat_hit_point_bonus(
    feat_selections: list[dict[str, Any]],
    *,
    current_level: int,
) -> int:
    bonus = 0
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        if isinstance(feat_entry, SystemsEntryRecord) and normalize_lookup(feat_entry.title) == normalize_lookup("Tough"):
            bonus += max(int(current_level or 0), 0) * 2
    return bonus


def _build_level_one_proficiencies(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    fixed_proficiencies: dict[str, list[str]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    feat_selections: list[dict[str, Any]],
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, list[str]]:
    del fixed_proficiencies
    campaign_option_proficiencies = collect_campaign_option_proficiency_grants(
        _selected_campaign_option_payloads(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            extra_option_payloads=campaign_option_payloads,
        )
    )
    armor = _dedupe_preserve_order(
        _extract_class_armor_proficiencies(selected_class)
        + _extract_feat_armor_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("armor") or [])
    )
    weapons = _dedupe_preserve_order(
        _extract_class_weapon_proficiencies(selected_class)
        + _extract_feat_weapon_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("weapons") or [])
    )
    tools = _dedupe_preserve_order(
        _extract_class_tool_proficiencies(selected_class)
        + _extract_fixed_tool_proficiencies(selected_species)
        + _extract_fixed_tool_proficiencies(selected_background)
        + _extract_feat_tool_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("tools") or [])
    )
    languages = _dedupe_preserve_order(
        _extract_fixed_languages(selected_species)
        + _extract_fixed_languages(selected_background)
        + selected_choices.get("species_languages", [])
        + selected_choices.get("background_languages", [])
        + _extract_feat_language_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("languages") or [])
    )
    skills = _dedupe_preserve_order(
        _extract_fixed_skills(selected_species)
        + _extract_fixed_skills(selected_background)
        + selected_choices.get("class_skills", [])
        + selected_choices.get("species_skills", [])
        + _extract_feat_skill_proficiencies(feat_selections, selected_choices)
        + list(campaign_option_proficiencies.get("skills") or [])
    )
    return {
        "armor": armor,
        "weapons": weapons,
        "tools": tools,
        "languages": languages,
        "skills": skills,
    }


def _normalize_skill_proficiency_level(value: Any) -> str:
    if value in (None, "", False):
        return "none"
    normalized = normalize_lookup(str(value))
    if normalized == "expertise":
        return "expertise"
    if normalized in {"halfproficient", "halfproficiency"}:
        return "half_proficient"
    if normalized in {"proficient", "proficiency"}:
        return "proficient"
    return "none"


def _skill_proficiency_level_rank(value: Any) -> int:
    return int(SKILL_PROFICIENCY_LEVEL_RANKS.get(_normalize_skill_proficiency_level(value), 0))


def _max_skill_proficiency_level(*levels: Any) -> str:
    best_level = "none"
    best_rank = -1
    for level in levels:
        normalized = _normalize_skill_proficiency_level(level)
        rank = _skill_proficiency_level_rank(normalized)
        if rank > best_rank:
            best_level = normalized
            best_rank = rank
    return best_level


def _skill_proficiency_level_from_bonus(
    skill_name: Any,
    *,
    bonus: Any,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> str:
    normalized_skill = normalize_lookup(skill_name)
    ability_key = SKILL_ABILITY_KEYS.get(normalized_skill)
    if ability_key is None:
        return "none"
    try:
        clean_bonus = int(bonus)
    except (TypeError, ValueError):
        return "none"
    modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE))
    delta = clean_bonus - modifier
    if proficiency_bonus > 0 and delta >= proficiency_bonus * 2:
        return "expertise"
    if proficiency_bonus > 0 and delta >= proficiency_bonus:
        return "proficient"
    if proficiency_bonus > 1 and delta == (proficiency_bonus // 2):
        return "half_proficient"
    return "none"


def _skill_proficiency_levels_from_rows(
    skills: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
) -> dict[str, str]:
    levels: dict[str, str] = {}
    for row in list(skills or []):
        skill_name = str(row.get("name") or "").strip()
        normalized_skill = normalize_lookup(skill_name)
        if normalized_skill not in SKILL_LABELS:
            continue
        explicit_level = _normalize_skill_proficiency_level(row.get("proficiency_level"))
        inferred_level = _skill_proficiency_level_from_bonus(
            skill_name,
            bonus=row.get("bonus"),
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
        )
        levels[normalized_skill] = _max_skill_proficiency_level(
            levels.get(normalized_skill),
            explicit_level,
            inferred_level,
        )
    return levels


def _skill_proficiency_levels_from_names(
    proficient_skills: list[str],
) -> dict[str, str]:
    levels: dict[str, str] = {}
    for skill in list(proficient_skills or []):
        normalized_skill = normalize_lookup(skill)
        if normalized_skill not in SKILL_LABELS:
            continue
        levels[normalized_skill] = _max_skill_proficiency_level(
            levels.get(normalized_skill),
            "proficient",
        )
    return levels


def _build_skills_payload_from_levels(
    ability_scores: dict[str, int],
    proficiency_levels: dict[str, str],
    proficiency_bonus: int,
    *,
    skill_bonus_map: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    resolved_skill_bonus_map = dict(skill_bonus_map or {})
    for normalized_skill, label in SKILL_LABELS.items():
        ability_key = SKILL_ABILITY_KEYS[normalized_skill]
        modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE))
        proficiency_level = _normalize_skill_proficiency_level(proficiency_levels.get(normalized_skill))
        if proficiency_level == "expertise":
            proficiency_contribution = proficiency_bonus * 2
        elif proficiency_level == "proficient":
            proficiency_contribution = proficiency_bonus
        elif proficiency_level == "half_proficient":
            proficiency_contribution = proficiency_bonus // 2
        else:
            proficiency_contribution = 0
        rows.append(
            {
                "name": label,
                "bonus": modifier + proficiency_contribution + int(resolved_skill_bonus_map.get(normalized_skill) or 0),
                "proficiency_level": proficiency_level,
            }
        )
    return rows


def _build_skills_payload(
    ability_scores: dict[str, int],
    proficient_skills: list[str],
    proficiency_bonus: int,
) -> list[dict[str, Any]]:
    return _build_skills_payload_from_levels(
        ability_scores,
        _skill_proficiency_levels_from_names(proficient_skills),
        proficiency_bonus,
    )


def _collect_level_one_feature_entries(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    feat_selections: list[dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    del selected_class
    feature_entries: list[dict[str, Any]] = []

    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=class_progression,
            target_level=1,
            selected_choices=selected_choices,
            group_key="class_option",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=1,
            selected_choices=selected_choices,
            group_key="subclass_option",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )

    if selected_species is not None:
        feature_entries.extend(_extract_species_feature_entries(selected_species))
        species_page_ref = _entry_page_ref(selected_species)
        if species_page_ref:
            feature_entries.append(
                {
                    "kind": "species_trait",
                    "label": selected_species.title,
                    "description_markdown": str(
                        (_entry_campaign_option(selected_species) or {}).get("description_markdown") or ""
                    ).strip(),
                    "page_ref": species_page_ref,
                    "campaign_option": _entry_campaign_option(selected_species) or None,
                }
            )
    if selected_background is not None:
        feature_entries.extend(_extract_background_feature_entries(selected_background))
        background_page_ref = _entry_page_ref(selected_background)
        if background_page_ref:
            feature_entries.append(
                {
                    "kind": "background_feature",
                    "label": selected_background.title,
                    "description_markdown": str(
                        (_entry_campaign_option(selected_background) or {}).get("description_markdown") or ""
                    ).strip(),
                    "page_ref": background_page_ref,
                    "campaign_option": _entry_campaign_option(selected_background) or None,
                }
            )

    for selection in feat_selections:
        feat_entry = selection.get("entry")
        feat_slug = str(selection.get("slug") or selection.get("selection_value") or "").strip()
        feat_title = (
            str(selection.get("label") or "").strip()
            or (
                feat_entry.title
                if isinstance(feat_entry, SystemsEntryRecord)
                else _resolve_choice_label(choice_sections, "species_feats", feat_slug) or feat_slug
            )
        )
        feature_entries.append(
            {
                "kind": "feat",
                "entry": None,
                "name": feat_title,
                "label": feat_title,
                "slug": feat_slug,
                "systems_entry": feat_entry if isinstance(feat_entry, SystemsEntryRecord) else None,
                "page_ref": str(selection.get("page_ref") or "").strip(),
                "campaign_option": dict(selection.get("campaign_option") or {}) or None,
            }
        )

    feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )

    feature_entries.extend(
        _collect_selected_campaign_feature_entries(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
        )
    )

    return feature_entries


def _collect_selected_campaign_feature_entries(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    for option in _selected_campaign_choice_options(
        choice_sections=choice_sections,
        selected_choices=selected_choices,
    ):
        page_ref = str(option.get("value") or "").strip()
        campaign_option = dict(option.get("campaign_option") or {})
        kind = str(campaign_option.get("kind") or "").strip()
        field_kind = str(option.get("field_kind") or "").strip()
        if kind and kind != "feature":
            continue
        if not kind and field_kind != "campaign_page_feature":
            continue
        title = str(
            campaign_option.get("feature_name")
            or option.get("title")
            or option.get("label")
            or page_ref
        ).strip()
        if not page_ref or not title:
            continue
        feature_entries.append(
            {
                "kind": "campaign_page_feature",
                "entry": None,
                "name": title,
                "label": title,
                "page_ref": page_ref,
                "description_markdown": str(
                    campaign_option.get("description_markdown")
                    or option.get("summary")
                    or ""
                ).strip(),
                "activation_type": str(campaign_option.get("activation_type") or "passive").strip(),
                "campaign_option": campaign_option or None,
            }
        )
    return feature_entries


def _collect_feat_optionalfeature_entries(
    *,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    for selection in feat_selections:
        feat_entry = selection.get("entry")
        instance_key = str(selection.get("instance_key") or "").strip()
        if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
            continue
        for section in _feat_optionalfeature_sections(feat_entry, optionalfeature_catalog):
            section_index = int(section.get("index") or 0)
            if section_index <= 0:
                continue
            category = _feat_optionalfeature_category(section_index)
            for selected_value in _feat_selected_values(selected_choices, instance_key, category):
                selected_entry = optionalfeature_catalog.get(str(selected_value or "").strip())
                if not isinstance(selected_entry, SystemsEntryRecord):
                    continue
                feature_entries.append(
                    {
                        "kind": "optionalfeature",
                        "entry": selected_entry,
                        "name": selected_entry.title,
                        "label": selected_entry.title,
                        "slug": str(selected_entry.slug or "").strip(),
                    }
                )
    return feature_entries


def _collect_progression_feature_entries_for_level(
    *,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    target_level: int,
    selected_choices: dict[str, list[str]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=class_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_class_options",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    feature_entries.extend(
        _collect_progression_feature_entries(
            progression=subclass_progression,
            target_level=target_level,
            selected_choices=selected_choices,
            group_key="levelup_subclass_options",
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    return feature_entries


def _collect_progression_feature_entries(
    *,
    progression: list[dict[str, Any]],
    target_level: int,
    selected_choices: dict[str, list[str]],
    group_key: str,
    optionalfeature_catalog: dict[str, SystemsEntryRecord] | None = None,
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    selected_values = list(selected_choices.get(group_key) or [])
    if not selected_values:
        selected_value_lookup: dict[str, list[str]] = {}
        for key, values in selected_choices.items():
            clean_key = str(key or "").strip()
            if clean_key == group_key or clean_key.startswith(f"{group_key}_"):
                selected_value_lookup[clean_key] = list(values or [])
        for key in sorted(selected_value_lookup):
            selected_values.extend(selected_value_lookup[key])
    selected_index = 0
    for group in progression:
        if int(group.get("level") or 0) != target_level:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            label = str(feature_row.get("label") or "").strip()
            normalized_label = normalize_lookup(label)
            if "choose subclass feature" in normalized_label:
                continue
            if normalized_label in ABILITY_SCORE_IMPROVEMENT_NAMES:
                continue
            embedded_card = dict(feature_row.get("embedded_card") or {})
            option_groups = list(embedded_card.get("option_groups") or [])
            if option_groups:
                for option_group in option_groups:
                    selected_slug = selected_values[selected_index] if selected_index < len(selected_values) else ""
                    selected_index += 1
                    selected_option = next(
                        (
                            option
                            for option in list(option_group.get("options") or [])
                            if str(option.get("slug") or "").strip() == selected_slug
                        ),
                        None,
                    )
                    if selected_option is None:
                        continue
                    selected_entry = selected_option.get("entry")
                    if not isinstance(selected_entry, SystemsEntryRecord):
                        selected_entry = dict(optionalfeature_catalog or {}).get(
                            str(selected_option.get("slug") or "").strip()
                        )
                    feature_entries.append(
                        {
                            "kind": "optionalfeature",
                            "entry": selected_entry if isinstance(selected_entry, SystemsEntryRecord) else None,
                            "name": str(selected_option.get("label") or "").strip(),
                            "label": str(selected_option.get("label") or "").strip(),
                            "slug": str(selected_option.get("slug") or "").strip(),
                        }
                    )
                continue
            entry = feature_row.get("entry")
            if isinstance(entry, SystemsEntryRecord):
                feature_entries.append(
                    {
                        "kind": "systems",
                        "entry": entry,
                        "name": entry.title,
                        "label": entry.title,
                    }
                )
    return feature_entries


def _build_feature_payloads(
    feature_entries: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    current_level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    features: list[dict[str, Any]] = []
    seen_feature_names: set[str] = set()

    for index, feature_entry in enumerate(feature_entries, start=1):
        feature_payload = _build_feature_payload(
            feature_entry,
            index=index,
        )
        if feature_payload is None:
            continue
        feature_name = str(feature_payload.get("name") or "").strip()
        normalized_name = normalize_lookup(feature_name)
        if not feature_name or normalized_name in seen_feature_names:
            continue
        seen_feature_names.add(normalized_name)
        features.append(feature_payload)
    return _apply_tracker_templates_to_feature_payloads(
        features,
        ability_scores=ability_scores,
        current_level=current_level,
    )


def _resolve_choice_label(
    choice_sections: list[dict[str, Any]],
    group_key: str,
    selected_value: str,
) -> str:
    option = _resolve_choice_option(choice_sections, group_key, selected_value)
    return str(option.get("label") or "").strip()


def _resolve_choice_option(
    choice_sections: list[dict[str, Any]],
    group_key: str,
    selected_value: str,
) -> dict[str, Any]:
    normalized_value = str(selected_value or "").strip()
    if not normalized_value:
        return {}
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            if str(field.get("group_key") or "") != group_key:
                continue
            for option in list(field.get("options") or []):
                if str(option.get("value") or "").strip() == normalized_value:
                    return dict(option)
    return {}


def _build_feature_payload(
    feature_entry: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any] | None:
    entry = feature_entry.get("entry")
    kind = str(feature_entry.get("kind") or "")

    if isinstance(entry, SystemsEntryRecord):
        feature_name = str(entry.title or "").strip()
        page_ref = _entry_page_ref(entry)
        campaign_option = _entry_campaign_option(entry)
        feature_payload = {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": _character_feature_category(entry.entry_type),
            "source": CAMPAIGN_PAGE_SOURCE_ID if page_ref else entry.source_id,
            "description_markdown": str(campaign_option.get("description_markdown") or "").strip(),
            "activation_type": str(campaign_option.get("activation_type") or "passive").strip() or "passive",
            "tracker_ref": None,
            "systems_ref": None if page_ref else _systems_ref_from_entry(entry),
        }
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        return feature_payload

    if kind == "optionalfeature":
        slug = str(feature_entry.get("slug") or "").strip()
        feature_name = str(feature_entry.get("label") or "").strip()
        if not slug or not feature_name:
            return None
        return {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "class_feature",
            "source": PHB_SOURCE_ID,
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": {
                "entry_key": "",
                "entry_type": "optionalfeature",
                "title": feature_name,
                "slug": slug,
                "source_id": PHB_SOURCE_ID,
            },
        }

    if kind == "species_trait":
        feature_name = str(feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(systems_entry)).strip()
        campaign_option = dict(feature_entry.get("campaign_option") or {})
        if not feature_name or (not isinstance(systems_entry, SystemsEntryRecord) and not page_ref):
            return None
        feature_payload = {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "species_trait",
            "source": page_ref or (systems_entry.source_id if isinstance(systems_entry, SystemsEntryRecord) else ""),
            "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": _systems_ref_from_entry(systems_entry) if isinstance(systems_entry, SystemsEntryRecord) else None,
        }
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        return feature_payload

    if kind == "background_feature":
        feature_name = str(feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(systems_entry)).strip()
        campaign_option = dict(feature_entry.get("campaign_option") or {})
        if not feature_name or (not isinstance(systems_entry, SystemsEntryRecord) and not page_ref):
            return None
        feature_payload = {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "background_feature",
            "source": page_ref or (systems_entry.source_id if isinstance(systems_entry, SystemsEntryRecord) else ""),
            "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": _systems_ref_from_entry(systems_entry) if isinstance(systems_entry, SystemsEntryRecord) else None,
        }
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        return feature_payload

    if kind == "feat":
        slug = str(feature_entry.get("slug") or "").strip()
        feature_name = str(feature_entry.get("title") or feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(systems_entry)).strip()
        campaign_option = dict(feature_entry.get("campaign_option") or _entry_campaign_option(systems_entry) or {})
        if not (slug or page_ref) or not feature_name:
            return None
        feature_payload: dict[str, Any] = {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "feat",
            "source": (
                CAMPAIGN_PAGE_SOURCE_ID
                if page_ref
                else (systems_entry.source_id if isinstance(systems_entry, SystemsEntryRecord) else PHB_SOURCE_ID)
            ),
            "description_markdown": str(campaign_option.get("description_markdown") or "").strip(),
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": (
                None
                if page_ref
                else (
                    _systems_ref_from_entry(systems_entry)
                    if isinstance(systems_entry, SystemsEntryRecord)
                    else {
                        "entry_key": "",
                        "entry_type": "feat",
                        "title": feature_name,
                        "slug": slug,
                        "source_id": PHB_SOURCE_ID,
                    }
                )
            ),
        }
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        return feature_payload

    if kind == "campaign_page_feature":
        feature_name = str(feature_entry.get("label") or feature_entry.get("name") or "").strip()
        page_ref = str(feature_entry.get("page_ref") or "").strip()
        if not feature_name or not page_ref:
            return None
        return {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "custom_feature",
            "source": "Campaign",
            "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
            "activation_type": str(feature_entry.get("activation_type") or "passive").strip() or "passive",
            "tracker_ref": None,
            "page_ref": page_ref,
            "campaign_option": dict(feature_entry.get("campaign_option") or {}) or None,
        }

    return None


def _build_level_one_stats(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord,
    ability_scores: dict[str, int],
    skills: list[dict[str, Any]],
    proficiency_bonus: int,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    current_level: int,
    equipment_catalog: list[dict[str, Any]] | None = None,
    features: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_metadata = dict(selected_class.metadata or {})
    hit_die_faces = int((class_metadata.get("hit_die") or {}).get("faces") or 0)
    con_modifier = _ability_modifier(ability_scores["con"])
    skill_lookup = {normalize_lookup(skill["name"]): skill for skill in skills}
    passive_perception = 10 + int((skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"]))
    passive_insight = 10 + int((skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"]))
    passive_investigation = 10 + int((skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"]))
    save_proficiencies = set(
        _class_save_proficiencies(selected_class)
        + _extract_feat_saving_throw_proficiencies(feat_selections, selected_choices)
    )
    save_bonus_map = _effect_save_bonus_map(_extract_character_effect_keys(features or []))
    base_speed = _extract_speed_label(selected_species)
    armor_class = _derive_armor_class_from_character_inputs(
        ability_scores=ability_scores,
        equipment_catalog=equipment_catalog or [],
        features=features or [],
        class_names=[selected_class.title],
        subclass_names=[selected_subclass.title] if selected_subclass is not None else [],
        item_catalog=item_catalog or {},
        allow_plain_unarmored_base=True,
    )

    stats = {
        "max_hp": max(hit_die_faces + con_modifier, 1)
        + _feat_hit_point_bonus(feat_selections, current_level=current_level),
        "armor_class": armor_class,
        "initiative_bonus": _ability_modifier(ability_scores["dex"])
        + _feat_initiative_bonus(feat_selections),
        "speed": _apply_speed_bonus_to_label(base_speed, _feat_speed_bonus(feat_selections)),
        "proficiency_bonus": proficiency_bonus,
        "passive_perception": passive_perception + _feat_passive_bonus(feat_selections, skill_name="Perception"),
        "passive_insight": passive_insight,
        "passive_investigation": passive_investigation + _feat_passive_bonus(feat_selections, skill_name="Investigation"),
        "ability_scores": {
            ability_key: {
                "score": score,
                "modifier": _ability_modifier(score),
                "save_bonus": _ability_modifier(score)
                + (proficiency_bonus if ability_key in save_proficiencies else 0)
                + int(save_bonus_map.get(ability_key) or 0),
            }
            for ability_key, score in ability_scores.items()
        },
    }
    return apply_stat_adjustments(
        stats,
        collect_campaign_option_stat_adjustments(
            _selected_campaign_option_payloads(
                choice_sections=choice_sections,
                selected_choices=selected_choices,
                extra_option_payloads=campaign_option_payloads,
            )
        ),
    )


def _build_level_one_profile(
    *,
    name: str,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord,
    selected_background: SystemsEntryRecord,
    values: dict[str, str],
) -> dict[str, Any]:
    species_page_ref = _entry_page_ref(selected_species)
    background_page_ref = _entry_page_ref(selected_background)
    class_payload = {
        "class_name": selected_class.title,
        "subclass_name": selected_subclass.title if selected_subclass is not None else "",
        "level": 1,
        "systems_ref": _systems_ref_from_entry(selected_class),
    }
    if selected_subclass is not None:
        class_payload["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
    return {
        "sheet_name": name,
        "display_name": name,
        "class_level_text": f"{selected_class.title} 1",
        "classes": [class_payload],
        "class_ref": _systems_ref_from_entry(selected_class),
        "subclass_ref": _systems_ref_from_entry(selected_subclass) if selected_subclass is not None else None,
        "species": selected_species.title,
        "species_ref": None if species_page_ref else _systems_ref_from_entry(selected_species),
        "species_page_ref": species_page_ref or None,
        "background": selected_background.title,
        "background_ref": None if background_page_ref else _systems_ref_from_entry(selected_background),
        "background_page_ref": background_page_ref or None,
        "alignment": str(values.get("alignment") or "").strip(),
        "experience_model": str(values.get("experience_model") or DEFAULT_EXPERIENCE_MODEL).strip(),
        "size": _extract_size_label(selected_species),
        "biography_markdown": "",
        "personality_markdown": "",
    }


def _proficiency_bonus_for_level(level: int) -> int:
    clean_level = max(int(level or 1), 1)
    return 2 + ((clean_level - 1) // 4)


def _ability_scores_from_definition(definition: CharacterDefinition) -> dict[str, int]:
    ability_scores = dict((definition.stats or {}).get("ability_scores") or {})
    return {
        ability_key: int(
            dict(
                ability_scores.get(ability_key)
                or ability_scores.get(ABILITY_LABELS.get(ability_key, "").lower())
                or {}
            ).get("score")
            or DEFAULT_ABILITY_SCORE
        )
        for ability_key in ABILITY_KEYS
    }


def _parse_level_up_hit_point_gain(values: dict[str, str]) -> int:
    raw_value = str(values.get("hp_gain") or "").strip()
    if not raw_value:
        raise CharacterBuildError("Hit point gain is required to level up this character.")
    try:
        hp_gain = int(raw_value)
    except ValueError as exc:
        raise CharacterBuildError("Hit point gain must be a whole number.") from exc
    if hp_gain < 1:
        raise CharacterBuildError("Hit point gain must be at least 1.")
    return hp_gain


def _build_leveled_stats(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    ability_scores: dict[str, int],
    skills: list[dict[str, Any]],
    proficiency_bonus: int,
    hp_gain: int,
    feat_selections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    current_level: int,
    equipment_catalog: list[dict[str, Any]] | None = None,
    features: list[dict[str, Any]] | None = None,
    item_catalog: dict[str, Any] | None = None,
    selected_campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stats, manual_adjustments = strip_manual_stat_adjustments(dict(current_definition.stats or {}))
    campaign_option_adjustments = collect_campaign_option_stat_adjustments(
        _campaign_option_payloads_from_definition(current_definition)
    )
    if campaign_option_adjustments:
        stats = apply_stat_adjustments(
            stats,
            {key: -int(value) for key, value in campaign_option_adjustments.items()},
        )
    skill_lookup = {normalize_lookup(skill["name"]): skill for skill in skills}
    save_proficiencies = set(
        _class_save_proficiencies(selected_class)
        + _extract_feat_saving_throw_proficiencies(feat_selections, selected_choices)
    )
    save_bonus_map = _effect_save_bonus_map(
        _extract_character_effect_keys(features or list(current_definition.features or []))
    )
    feat_hp_bonus = _feat_hit_point_bonus(feat_selections, current_level=current_level)
    stats["max_hp"] = max(int(stats.get("max_hp") or 0) + hp_gain + feat_hp_bonus, 1)
    stats["proficiency_bonus"] = proficiency_bonus
    stats["passive_perception"] = 10 + int(
        (skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
    ) + _feat_passive_bonus(feat_selections, skill_name="Perception")
    stats["passive_insight"] = 10 + int(
        (skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"])
    )
    stats["passive_investigation"] = 10 + int(
        (skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"])
    ) + _feat_passive_bonus(feat_selections, skill_name="Investigation")
    stats["armor_class"] = _derive_armor_class_from_character_inputs(
        ability_scores=ability_scores,
        equipment_catalog=equipment_catalog or list(current_definition.equipment_catalog or []),
        features=features or list(current_definition.features or []),
        class_names=_character_profile_class_names(current_definition, fallback_class_name=selected_class.title),
        subclass_names=_character_profile_subclass_names(
            current_definition,
            fallback_subclass_name=selected_subclass.title if selected_subclass is not None else "",
        ),
        item_catalog=item_catalog or {},
        allow_plain_unarmored_base=True,
    )
    stats["initiative_bonus"] = _ability_modifier(ability_scores["dex"]) + _feat_initiative_bonus(feat_selections)
    stats["speed"] = _apply_speed_bonus_to_label(str(stats.get("speed") or ""), _feat_speed_bonus(feat_selections))
    stats["ability_scores"] = {
        ability_key: {
            "score": score,
            "modifier": _ability_modifier(score),
            "save_bonus": _ability_modifier(score)
            + (proficiency_bonus if ability_key in save_proficiencies else 0)
            + int(save_bonus_map.get(ability_key) or 0),
        }
        for ability_key, score in ability_scores.items()
    }
    combined_campaign_option_adjustments = dict(campaign_option_adjustments)
    for key, value in collect_campaign_option_stat_adjustments(selected_campaign_option_payloads or []).items():
        combined_campaign_option_adjustments[key] = int(combined_campaign_option_adjustments.get(key) or 0) + int(value)
    stats = apply_stat_adjustments(stats, combined_campaign_option_adjustments)
    return apply_manual_stat_adjustments(stats, manual_adjustments)


def _build_leveled_profile(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
) -> dict[str, Any]:
    profile = dict(current_definition.profile or {})
    classes = list(profile.get("classes") or [])
    class_payload = dict(classes[0] or {}) if classes else {}
    class_payload["class_name"] = selected_class.title
    class_payload["level"] = target_level
    class_payload["systems_ref"] = _systems_ref_from_entry(selected_class)
    class_payload["subclass_name"] = selected_subclass.title if selected_subclass is not None else ""
    if selected_subclass is not None:
        class_payload["subclass_ref"] = _systems_ref_from_entry(selected_subclass)
    else:
        class_payload.pop("subclass_ref", None)
    profile["classes"] = [class_payload]
    profile["class_level_text"] = f"{selected_class.title} {target_level}"
    profile["class_ref"] = _systems_ref_from_entry(selected_class)
    profile["subclass_ref"] = _systems_ref_from_entry(selected_subclass) if selected_subclass is not None else None
    return profile


def _build_leveled_source(
    source_payload: dict[str, Any],
    target_level: int,
    *,
    current_level: int | None = None,
    current_definition: CharacterDefinition | None = None,
    hp_gain: int | None = None,
    max_hp_delta: int | None = None,
) -> dict[str, Any]:
    source = dict(source_payload or {})
    if current_definition is not None:
        source = _seed_source_hp_baseline_from_definition(source, current_definition)
    source_type = str(source.get("source_type") or "").strip()
    if source_type in IMPORTED_CHARACTER_SOURCE_TYPES:
        source["imported_at"] = isoformat(utcnow())
        source["parse_warnings"] = list(source.get("parse_warnings") or [])
        source = _with_native_progression_event(
            source,
            kind="level_up",
            previous_level=current_level,
            target_level=target_level,
            hp_gain=hp_gain,
            max_hp_delta=max_hp_delta,
        )
        return source
    source.update(
        {
            "source_path": f"builder://native-level-{target_level}",
            "source_type": "native_character_builder",
            "imported_from": f"In-app Native Level {target_level} Builder",
            "imported_at": isoformat(utcnow()),
            "parse_warnings": [],
        }
    )
    return _with_native_progression_event(
        source,
        kind="level_up",
        previous_level=current_level,
        target_level=target_level,
        hp_gain=hp_gain,
        max_hp_delta=max_hp_delta,
    )


def _build_leveled_import_metadata(
    *,
    campaign_slug: str,
    current_definition: CharacterDefinition,
    current_import_metadata: CharacterImportMetadata | None,
    target_level: int,
) -> CharacterImportMetadata:
    source_type = _character_source_type(current_definition)
    if source_type in IMPORTED_CHARACTER_SOURCE_TYPES:
        existing_import = current_import_metadata
        return CharacterImportMetadata(
            campaign_slug=campaign_slug,
            character_slug=current_definition.character_slug,
            source_path=str(
                (existing_import.source_path if existing_import is not None else "")
                or (current_definition.source or {}).get("source_path")
                or f"managed://{campaign_slug}/{current_definition.character_slug}"
            ),
            imported_at_utc=isoformat(utcnow()),
            parser_version=CHARACTER_BUILDER_VERSION,
            import_status="managed",
            warnings=list(existing_import.warnings if existing_import is not None else []),
        )
    return CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=current_definition.character_slug,
        source_path=f"builder://native-level-{target_level}",
        imported_at_utc=isoformat(utcnow()),
        parser_version=CHARACTER_BUILDER_VERSION,
        import_status="clean",
        warnings=[],
    )


def _merge_feature_payloads(
    existing_features: list[dict[str, Any]],
    new_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [dict(feature) for feature in existing_features]
    seen_names = {
        normalize_lookup(str(feature.get("name") or "").strip())
        for feature in merged
        if str(feature.get("name") or "").strip()
    }
    for feature in new_features:
        feature_name = str(feature.get("name") or "").strip()
        normalized_name = normalize_lookup(feature_name)
        if not feature_name or normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        merged.append(dict(feature))
    return merged


def _apply_tracker_templates_to_feature_payloads(
    features: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    current_level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    updated_features: list[dict[str, Any]] = []
    resource_templates: list[dict[str, Any]] = []
    seen_template_ids: set[str] = set()
    display_order = 0

    for feature in features:
        feature_payload = dict(feature)
        tracker_template = _build_campaign_option_tracker_template(
            feature_payload,
            display_order=display_order,
            current_level=current_level,
        )
        if tracker_template is None:
            tracker_template = _build_feature_tracker_template(
                feature_payload,
                ability_scores=ability_scores,
                current_level=current_level,
                display_order=display_order,
            )
        if tracker_template is not None:
            tracker_id = str(tracker_template.get("id") or "").strip()
            if tracker_id:
                feature_payload["tracker_ref"] = tracker_id
            feature_payload["activation_type"] = str(
                tracker_template.get("activation_type") or feature_payload.get("activation_type") or "passive"
            )
            normalized_tracker = dict(tracker_template)
            normalized_tracker.pop("activation_type", None)
            if not tracker_id or tracker_id not in seen_template_ids:
                resource_templates.append(normalized_tracker)
                if tracker_id:
                    seen_template_ids.add(tracker_id)
                display_order += 1
        updated_features.append(feature_payload)

    return updated_features, resource_templates


def _build_campaign_option_tracker_template(
    feature_payload: dict[str, Any],
    *,
    display_order: int,
    current_level: int,
) -> dict[str, Any] | None:
    option = dict(feature_payload.get("campaign_option") or {})
    resource = dict(option.get("resource") or {})
    max_value = _resolve_campaign_option_resource_max(resource, current_level=current_level)
    if max_value <= 0:
        return None
    tracker_id = str(feature_payload.get("tracker_ref") or "").strip() or f"campaign-option-tracker:{feature_payload.get('id')}"
    reset_on = str(resource.get("reset_on") or "manual").strip().lower()
    return {
        "id": tracker_id,
        "label": str(resource.get("label") or feature_payload.get("name") or "").strip(),
        "category": "custom_feature",
        "initial_current": max_value,
        "max": max_value,
        "reset_on": reset_on,
        "reset_to": "max" if reset_on in {"short_rest", "long_rest"} else "unchanged",
        "rest_behavior": "confirm_before_reset" if reset_on in {"short_rest", "long_rest"} else "manual_only",
        "notes": str(feature_payload.get("name") or "").strip(),
        "display_order": display_order,
        "activation_type": str(feature_payload.get("activation_type") or "passive").strip() or "passive",
    }


def _resolve_campaign_option_resource_max(
    resource: dict[str, Any],
    *,
    current_level: int,
) -> int:
    max_value = int(resource.get("max") or 0)
    scaling = dict(resource.get("scaling") or {})
    if not scaling:
        return max_value
    mode = str(scaling.get("mode") or "").strip().lower()
    scaled_value = 0
    if mode == "level":
        scaled_value = max(int(current_level or 0), 0)
    elif mode == "half_level":
        scaled_value = _round_scaled_level_value(
            int(current_level or 0) / 2,
            round_mode=str(scaling.get("round") or "down").strip().lower() or "down",
        )
    elif mode == "proficiency_bonus":
        scaled_value = _proficiency_bonus_for_level(max(int(current_level or 0), 1))
    elif mode == "thresholds":
        for threshold in list(scaling.get("thresholds") or []):
            threshold_payload = dict(threshold or {}) if isinstance(threshold, dict) else {}
            minimum_level = int(threshold_payload.get("level") or 0)
            threshold_value = int(threshold_payload.get("value") or 0)
            if minimum_level > 0 and threshold_value > 0 and current_level >= minimum_level:
                scaled_value = threshold_value
    minimum_value = int(scaling.get("minimum") or 0)
    maximum_value = int(scaling.get("maximum") or 0)
    if minimum_value > 0:
        scaled_value = max(scaled_value, minimum_value)
    if maximum_value > 0:
        scaled_value = min(scaled_value, maximum_value)
    if scaled_value <= 0:
        return max_value
    return scaled_value


def _round_scaled_level_value(value: float, *, round_mode: str) -> int:
    if round_mode == "up":
        return int(-(-value // 1))
    if round_mode == "nearest":
        return int(round(value))
    return int(value // 1)


def _merge_resource_templates(
    existing_templates: list[dict[str, Any]],
    new_templates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    new_by_id = {
        str(template.get("id") or "").strip(): dict(template)
        for template in new_templates
        if str(template.get("id") or "").strip()
    }
    seen_ids: set[str] = set()
    for template in new_templates:
        template_id = str(template.get("id") or "").strip()
        if not template_id:
            merged.append(dict(template))
    for template in existing_templates:
        template_id = str(template.get("id") or "").strip()
        if template_id and template_id in new_by_id:
            merged.append(dict(new_by_id[template_id]))
            seen_ids.add(template_id)
            continue
        merged.append(dict(template))
        if template_id:
            seen_ids.add(template_id)
    for template in new_templates:
        template_id = str(template.get("id") or "").strip()
        if not template_id or template_id in seen_ids:
            continue
        merged.append(dict(template))
        seen_ids.add(template_id)
    return merged


def _extract_existing_feature_choice_map(definition: CharacterDefinition) -> dict[str, list[str]]:
    values: list[str] = []
    for feature in list(definition.features or []):
        feature_name = str(feature.get("name") or "").strip()
        if feature_name:
            values.append(feature_name)
        systems_ref = dict(feature.get("systems_ref") or {})
        feature_slug = str(systems_ref.get("slug") or "").strip()
        if feature_slug:
            values.append(feature_slug)
    return {"existing_features": _dedupe_preserve_order(values)}


def _merge_selected_choice_maps(*choice_maps: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for choice_map in choice_maps:
        for key, values in choice_map.items():
            merged.setdefault(str(key), [])
            merged[key] = _dedupe_preserve_order(merged[key] + [str(value).strip() for value in values if str(value).strip()])
    return merged


def _build_native_level_up_preview(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
    subclass_progression: list[dict[str, Any]],
    feat_options: list[dict[str, str]],
    feat_catalog: dict[str, Any],
    choice_sections: list[dict[str, Any]],
    optionalfeature_catalog: dict[str, SystemsEntryRecord],
    spell_catalog: dict[str, Any],
    target_level: int,
    current_ability_scores: dict[str, int],
    values: dict[str, str],
) -> dict[str, Any]:
    _, selected_choices = _resolve_builder_choices(choice_sections, values, strict=False)
    base_ability_scores, level_up_feat_entries, asi_summaries = _resolve_level_up_ability_score_choices(
        current_ability_scores=current_ability_scores,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        feat_options=feat_options,
        target_level=target_level,
        values=values,
        strict=False,
    )
    feat_selections = _resolve_level_up_feat_selections(
        values,
        feat_catalog,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
    )
    gained_feature_entries = _collect_progression_feature_entries_for_level(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        target_level=target_level,
        selected_choices=selected_choices,
        optionalfeature_catalog=optionalfeature_catalog,
    )
    gained_feature_entries.extend(level_up_feat_entries)
    gained_feature_entries.extend(
        _collect_feat_optionalfeature_entries(
            feat_selections=feat_selections,
            selected_choices=selected_choices,
            optionalfeature_catalog=optionalfeature_catalog,
        )
    )
    selected_campaign_option_payloads = (
        _campaign_option_payloads_from_feat_selections(feat_selections)
        + _campaign_option_payloads_from_feature_entries(gained_feature_entries)
    )
    ability_scores = _apply_feat_ability_score_bonuses(
        base_ability_scores,
        feat_selections=feat_selections,
        selected_choices=selected_choices,
        strict=False,
    )
    hp_gain = 0
    try:
        hp_gain = _parse_level_up_hit_point_gain(values)
    except CharacterBuildError:
        hp_gain = 0
    gained_features = [
        str(entry.get("label") or entry.get("name") or "").strip()
        for entry in gained_feature_entries
        if str(entry.get("label") or entry.get("name") or "").strip()
    ]
    gained_features.extend(summary for summary in asi_summaries if summary)
    gained_features = _dedupe_preserve_order(gained_features)
    new_spell_names = _summarize_level_up_spell_choices(
        definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        values=values,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=gained_feature_entries,
        extra_option_payloads=selected_campaign_option_payloads,
    )
    slot_progression = _level_up_slot_progression_for_class(
        selected_class.title,
        target_level,
        selected_class=selected_class,
    )
    slot_summary = [
        f"Level {int(slot.get('level') or 0)}: {int(slot.get('max_slots') or 0)} slots"
        for slot in slot_progression
        if int(slot.get("max_slots") or 0) > 0
    ]
    preview_feature_payloads, _ = _build_feature_payloads(
        gained_feature_entries,
        ability_scores=ability_scores,
        current_level=target_level,
    )
    _, preview_resource_templates = _apply_tracker_templates_to_feature_payloads(
        _merge_feature_payloads(list(definition.features or []), preview_feature_payloads),
        ability_scores=ability_scores,
        current_level=target_level,
    )
    merged_resource_templates = _merge_resource_templates(
        list(definition.resource_templates or []),
        preview_resource_templates,
    )
    preview_campaign_stat_adjustments = collect_campaign_option_stat_adjustments(selected_campaign_option_payloads)
    return {
        "class_level_text": f"{selected_class.title} {target_level}",
        "max_hp": max(
            int((definition.stats or {}).get("max_hp") or 0)
            + hp_gain
            + _feat_hit_point_bonus(feat_selections, current_level=target_level)
            + int(preview_campaign_stat_adjustments.get("max_hp") or 0),
            1,
        ),
        "gained_features": gained_features,
        "resources": [
            _summarize_preview_resource(template)
            for template in merged_resource_templates
            if _summarize_preview_resource(template)
        ],
        "spell_slots": slot_summary,
        "new_spells": new_spell_names,
    }


def _build_level_one_spellcasting(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_name = selected_class.title
    ability_name = _spellcasting_ability_name_for_class(class_name, selected_class=selected_class)
    spell_payloads = _build_level_one_spell_payloads(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        feature_entries=feature_entries,
        campaign_option_payloads=campaign_option_payloads,
    )
    slot_progression = _spell_slot_progression_for_class_level(
        class_name,
        1,
        selected_class=selected_class,
    )
    if not ability_name and not slot_progression and not spell_payloads:
        return {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "spells": [],
        }
    if not ability_name:
        return {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": slot_progression,
            "spells": spell_payloads,
        }
    ability_key = next(key for key, label in ABILITY_LABELS.items() if label == ability_name)
    modifier = _ability_modifier(ability_scores[ability_key])
    return {
        "spellcasting_class": class_name,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier,
        "spell_attack_bonus": proficiency_bonus + modifier,
        "slot_progression": slot_progression,
        "spells": spell_payloads,
    }


def _build_level_up_spellcasting(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    selected_campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_name = selected_class.title
    ability_name = _spellcasting_ability_name_for_class(class_name, selected_class=selected_class)
    slot_progression = _level_up_slot_progression_for_class(class_name, target_level, selected_class=selected_class)
    spell_payloads = _build_level_up_spell_payloads(
        current_definition=current_definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
        selected_campaign_option_payloads=selected_campaign_option_payloads,
    )

    if not ability_name:
        if not slot_progression and not spell_payloads:
            return dict(current_definition.spellcasting or {})
        return {
            "spellcasting_class": str((current_definition.spellcasting or {}).get("spellcasting_class") or ""),
            "spellcasting_ability": str((current_definition.spellcasting or {}).get("spellcasting_ability") or ""),
            "spell_save_dc": (current_definition.spellcasting or {}).get("spell_save_dc"),
            "spell_attack_bonus": (current_definition.spellcasting or {}).get("spell_attack_bonus"),
            "slot_progression": slot_progression,
            "spells": spell_payloads,
        }

    ability_key = next(key for key, label in ABILITY_LABELS.items() if label == ability_name)
    modifier = _ability_modifier(ability_scores[ability_key])
    return {
        "spellcasting_class": class_name,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier,
        "spell_attack_bonus": proficiency_bonus + modifier,
        "slot_progression": slot_progression,
        "spells": spell_payloads,
    }


def _build_level_up_spell_payloads(
    *,
    current_definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    selected_campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(class_name, selected_class=selected_class)
    existing_spells = list((current_definition.spellcasting or {}).get("spells") or [])
    spells_by_key: dict[str, dict[str, Any]] = {}
    for spell in existing_spells:
        payload_key = _spell_payload_key(spell)
        if payload_key:
            spells_by_key[payload_key] = dict(spell)
    values = _values_from_selected_choices(choice_sections, selected_choices)

    for selected_value in selected_choices.get("levelup_spell_cantrips", []):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark="Cantrip",
        )
    for selected_value in _selected_additional_known_spell_values(selected_choices, prefix="levelup_bonus_spell_known"):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
        )

    if spell_mode in {"known", "prepared"}:
        mark = "Known" if spell_mode == "known" else "Prepared"
        group_key = "levelup_spell_known" if spell_mode == "known" else "levelup_prepared_spells"
        if spell_mode == "known":
            replacement_from = str(values.get("levelup_spell_replace_from_1") or "").strip()
            replacement_to = str(values.get("levelup_spell_replace_to_1") or "").strip()
            if replacement_from and replacement_to:
                spells_by_key.pop(_spell_lookup_key(replacement_from, spell_catalog), None)
                _add_spell_to_payloads(
                    spells_by_key,
                    selected_value=replacement_to,
                    spell_catalog=spell_catalog,
                    mark="Known",
                )
        for selected_value in selected_choices.get(group_key, []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark=mark,
            )
    elif spell_mode == "wizard":
        existing_prepared = _spell_selection_values_by_mark(existing_spells, "Prepared")
        new_spellbook_values = list(selected_choices.get("levelup_wizard_spellbook", []))
        new_prepared_values = set(selected_choices.get("levelup_wizard_prepared", []))
        for selected_value in new_spellbook_values:
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Prepared + Spellbook" if selected_value in new_prepared_values else "Spellbook",
            )
        for selected_value in new_prepared_values:
            payload_key = _spell_lookup_key(selected_value, spell_catalog)
            existing_payload = spells_by_key.get(payload_key)
            if existing_payload is None:
                _add_spell_to_payloads(
                    spells_by_key,
                    selected_value=selected_value,
                    spell_catalog=spell_catalog,
                    mark="Prepared + Spellbook",
                )
                continue
            if "Prepared" not in str(existing_payload.get("mark") or ""):
                existing_payload["mark"] = _merge_spell_mark(str(existing_payload.get("mark") or "").strip(), "Prepared")
        for selected_value in existing_prepared:
            payload_key = _spell_lookup_key(selected_value, spell_catalog)
            existing_payload = spells_by_key.get(payload_key)
            if existing_payload is not None and "Prepared" not in str(existing_payload.get("mark") or ""):
                existing_payload["mark"] = _merge_spell_mark(str(existing_payload.get("mark") or "").strip(), "Prepared")

    for selected_value in _automatic_known_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        feature_entries=feature_entries,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
        )
    for selected_value in _automatic_prepared_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )
    _apply_spell_support_grants_to_payloads(
        spells_by_key,
        grants=_automatic_spell_support_grants(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            target_level=target_level,
            exact_level=target_level,
            feature_entries=feature_entries,
        ),
        spell_catalog=spell_catalog,
    )
    _apply_selected_spell_support_fields_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        values=values,
        field_prefix="levelup_spell_support",
        exact_level=target_level,
        feature_entries=feature_entries,
    )
    _apply_selected_feat_spell_fields_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
    )
    _apply_selected_campaign_option_spells_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        extra_option_payloads=selected_campaign_option_payloads,
    )
    for spell_title in _automatic_feat_known_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=target_level,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
        )
    for spell_title in _automatic_feat_prepared_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=target_level,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )
    for spell_grant in _automatic_feat_innate_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=target_level,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )
    for spell_grant in _automatic_innate_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )
    _apply_selected_spell_support_replacements_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=target_level,
        values=values,
        field_prefix="levelup_spell_support",
        exact_level=target_level,
        feature_entries=feature_entries,
    )

    return list(spells_by_key.values())


def _level_up_slot_progression_for_class(
    class_name: str,
    target_level: int,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> list[dict[str, Any]]:
    return _spell_slot_progression_for_class_level(
        class_name,
        target_level,
        selected_class=selected_class,
    )


def _build_level_one_spell_payloads(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    feature_entries: list[dict[str, Any]] | None = None,
    campaign_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    class_name = selected_class.title
    spell_mode = _spellcasting_mode_for_class(class_name, selected_class=selected_class)
    spells_by_key: dict[str, dict[str, Any]] = {}
    values = _values_from_selected_choices(choice_sections, selected_choices)
    for selected_value in selected_choices.get("spell_cantrips", []):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark="Cantrip",
        )
    for selected_value in _selected_additional_known_spell_values(selected_choices, prefix="bonus_spell_known"):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
        )

    if spell_mode == "known":
        for selected_value in selected_choices.get("spell_level_one", []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Known",
            )
    elif spell_mode == "prepared":
        for selected_value in selected_choices.get("spell_level_one", []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Prepared",
            )
    elif spell_mode == "wizard":
        prepared_values = set(selected_choices.get("wizard_prepared", []))
        for selected_value in selected_choices.get("wizard_spellbook", []):
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark="Prepared + Spellbook" if selected_value in prepared_values else "Spellbook",
            )

    for spell_title in _automatic_known_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=1,
        feature_entries=feature_entries,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
        )

    for spell_title in _automatic_prepared_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=1,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )

    _apply_spell_support_grants_to_payloads(
        spells_by_key,
        grants=_automatic_spell_support_grants(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            target_level=1,
            feature_entries=feature_entries,
        ),
        spell_catalog=spell_catalog,
    )
    _apply_selected_spell_support_fields_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        feature_entries=feature_entries,
    )
    for spell_title in _automatic_feat_known_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=1,
    ):
        _add_bonus_known_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
        )
    for spell_title in _automatic_feat_prepared_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=1,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )
    for spell_grant in _automatic_feat_innate_spell_values(
        feat_selections=feat_selections,
        values=values,
        target_level=1,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )
    for spell_grant in _automatic_innate_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=1,
        feature_entries=feature_entries,
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("name") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_ritual=bool(spell_grant.get("is_ritual")),
        )
    _apply_selected_feat_spell_fields_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
    )
    _apply_selected_campaign_option_spells_to_payloads(
        spells_by_key,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        extra_option_payloads=campaign_option_payloads,
    )
    _apply_selected_spell_support_replacements_to_payloads(
        spells_by_key,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        target_level=1,
        values=values,
        field_prefix="spell_support",
        feature_entries=feature_entries,
    )

    return list(spells_by_key.values())


def _spell_payload_key(spell_payload: dict[str, Any]) -> str:
    systems_ref = dict(spell_payload.get("systems_ref") or {})
    return str(systems_ref.get("slug") or spell_payload.get("name") or "").strip()


def _spell_lookup_key(selected_value: str, spell_catalog: dict[str, Any]) -> str:
    spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
    if spell_entry is not None:
        return spell_entry.slug
    return str(selected_value or "").strip()


def _spell_selection_values_by_mark(
    spell_payloads: list[dict[str, Any]],
    mark_fragment: str,
    *,
    exclude_bonus_known: bool = False,
) -> set[str]:
    values: set[str] = set()
    normalized_mark = normalize_lookup(mark_fragment)
    for spell_payload in spell_payloads:
        if exclude_bonus_known and bool(spell_payload.get("is_bonus_known")):
            continue
        if normalized_mark not in normalize_lookup(str(spell_payload.get("mark") or "")):
            continue
        payload_key = _spell_payload_key(spell_payload)
        if payload_key:
            values.add(payload_key)
    return values


def _selected_additional_known_spell_values(
    selected_choices: dict[str, list[str]],
    *,
    prefix: str,
) -> list[str]:
    values: list[str] = []
    for group_key, group_values in selected_choices.items():
        if not str(group_key).startswith(prefix):
            continue
        values.extend(str(value).strip() for value in group_values if str(value).strip())
    return _dedupe_preserve_order(values)


def _selected_form_spell_values_by_field_prefix(
    values: dict[str, str],
    *,
    prefix: str,
) -> set[str]:
    return {
        str(value).strip()
        for key, value in dict(values or {}).items()
        if str(key).startswith(prefix) and str(value).strip()
    }


def _values_from_selected_choices(
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "").strip()
            group_key = str(field.get("group_key") or field_name).strip()
            selected_value = next((value for value in list(selected_choices.get(group_key) or []) if str(value).strip()), "")
            if field_name and selected_value:
                values[field_name] = str(selected_value).strip()
    return values


def _selected_feat_spell_field_values(
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[tuple[dict[str, Any], str]]:
    values: list[tuple[dict[str, Any], str]] = []
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            kind = str(field.get("kind") or "").strip()
            if kind not in {"feat_spell_known", "feat_spell_prepared", "feat_spell_granted"}:
                continue
            group_key = str(field.get("group_key") or field.get("name") or "").strip()
            for selected_value in list(selected_choices.get(group_key) or []):
                clean_value = str(selected_value).strip()
                if clean_value:
                    values.append((dict(field), clean_value))
    return values


def _apply_selected_feat_spell_fields_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
) -> None:
    for field, selected_value in _selected_feat_spell_field_values(choice_sections, selected_choices):
        kind = str(field.get("kind") or "").strip()
        if kind == "feat_spell_known":
            _add_bonus_known_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
            )
            continue
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark=str(field.get("spell_mark") or "").strip(),
            is_always_prepared=bool(field.get("spell_is_always_prepared")),
            is_ritual=bool(field.get("spell_is_ritual")),
        )


def _apply_selected_campaign_option_spells_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    extra_option_payloads: list[dict[str, Any]] | None = None,
) -> None:
    for spell_grant in collect_campaign_option_spell_grants(
        _selected_campaign_option_payloads(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            extra_option_payloads=extra_option_payloads,
        )
    ):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=str(spell_grant.get("value") or "").strip(),
            spell_catalog=spell_catalog,
            mark=str(spell_grant.get("mark") or "").strip(),
            is_always_prepared=bool(spell_grant.get("always_prepared")),
            is_ritual=bool(spell_grant.get("ritual")),
        )


def _build_additional_known_spell_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    group_key_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    specs = _extract_additional_known_choice_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        options = _build_additional_spell_filter_options(str(spec.get("filter") or ""), spell_catalog)
        if not options:
            continue
        count = max(int(spec.get("count") or 1), 1)
        is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
        label_prefix = "Granted Cantrip" if is_cantrip else "Granted Spell"
        help_text = (
            "Choose a feature-granted bonus cantrip."
            if is_cantrip
            else "Choose a feature-granted bonus spell."
        )
        group_key = f"{group_key_prefix}_{spec_index}"
        for choice_index in range(count):
            field_name = f"{field_prefix}_{spec_index}_{choice_index + 1}"
            fields.append(
                {
                    "name": field_name,
                    "label": f"{label_prefix} {choice_index + 1}",
                    "help_text": help_text,
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": group_key,
                    "kind": "spell",
                }
            )
    return fields


def _build_spell_support_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    group_key_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    specs = _extract_spell_support_choice_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        options = _build_spell_support_options_from_spec(spec, spell_catalog)
        if not options:
            continue
        category = str(spec.get("category") or "").strip()
        count = max(int(spec.get("count") or 1), 1)
        is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
        label_prefix = str(spec.get("label_prefix") or "").strip()
        if not label_prefix:
            label_prefix = "Granted Cantrip" if is_cantrip else "Granted Spell"
        help_text = str(spec.get("help_text") or "").strip()
        if not help_text:
            help_text = (
                "Choose a feature-granted cantrip."
                if is_cantrip
                else "Choose a feature-granted spell."
            )
        group_key = f"{group_key_prefix}_{category}_{spec_index}"
        for choice_index in range(1, count + 1):
            field_name = _spell_support_choice_field_name(field_prefix, category, spec_index, choice_index)
            fields.append(
                {
                    "name": field_name,
                    "label": f"{label_prefix} {choice_index}",
                    "help_text": help_text,
                    "options": options,
                    "selected": str(values.get(field_name) or "").strip(),
                    "group_key": group_key,
                    "kind": f"spell_support_{category}",
                    "spell_mark": str(spec.get("mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("always_prepared")),
                    "spell_is_ritual": bool(spec.get("ritual")),
                }
            )
    return fields


def _build_spell_support_replacement_fields(
    *,
    existing_spells: list[dict[str, Any]],
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    specs = _extract_spell_support_replacement_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        to_options = _build_spell_support_options_from_spec(
            {
                "filter": str(spec.get("to_filter") or "").strip(),
                "options": list(spec.get("to_options") or []),
            },
            spell_catalog,
        )
        from_options = _build_spell_support_existing_options_from_replacement_spec(
            existing_spells=existing_spells,
            spell_catalog=spell_catalog,
            spec=spec,
        )
        if not from_options or not to_options:
            continue
        category = str(spec.get("category") or "known").strip() or "known"
        count = max(int(spec.get("count") or 1), 1)
        from_group_key = f"{field_prefix}_replace_{category}_{spec_index}_from"
        to_group_key = f"{field_prefix}_replace_{category}_{spec_index}_to"
        from_help_text = str(spec.get("help_text_from") or "").strip() or "Choose the spell you are replacing."
        to_help_text = str(spec.get("help_text_to") or "").strip() or "Choose the replacement spell."
        for choice_index in range(1, count + 1):
            from_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "from",
            )
            to_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "to",
            )
            fields.append(
                {
                    "name": from_name,
                    "label": f"Replace Spell {choice_index}",
                    "help_text": from_help_text,
                    "options": from_options,
                    "selected": str(values.get(from_name) or "").strip(),
                    "group_key": from_group_key,
                    "kind": "spell_support_replace_from",
                    "required": False,
                    "paired_field_name": to_name,
                    "paired_field_label": f"Replacement Spell {choice_index}",
                    "spell_mark": str(spec.get("mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("always_prepared")),
                    "spell_is_ritual": bool(spec.get("ritual")),
                }
            )
            fields.append(
                {
                    "name": to_name,
                    "label": f"Replacement Spell {choice_index}",
                    "help_text": to_help_text,
                    "options": to_options,
                    "selected": str(values.get(to_name) or "").strip(),
                    "group_key": to_group_key,
                    "kind": "spell_support_replace_to",
                    "required": False,
                    "paired_field_name": from_name,
                    "paired_field_label": f"Replace Spell {choice_index}",
                    "spell_mark": str(spec.get("mark") or "").strip(),
                    "spell_is_always_prepared": bool(spec.get("always_prepared")),
                    "spell_is_ritual": bool(spec.get("ritual")),
                }
            )
    return fields


def _build_spell_support_existing_options_from_replacement_spec(
    *,
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    spec: dict[str, Any],
) -> list[dict[str, str]]:
    allowed_payload_keys: set[str] = set()
    if list(spec.get("from_options") or []) or str(spec.get("from_filter") or "").strip():
        allowed_payload_keys = {
            str(option.get("value") or "").strip()
            for option in _build_spell_support_options_from_spec(
                {
                    "filter": str(spec.get("from_filter") or "").strip(),
                    "options": list(spec.get("from_options") or []),
                },
                spell_catalog,
            )
            if str(option.get("value") or "").strip()
        }
    return _build_spell_options_from_existing_payloads(
        existing_spells=existing_spells,
        spell_catalog=spell_catalog,
        filter_spec={
            "mark": str(spec.get("from_mark") or "").strip(),
            "level": int(spec.get("from_level") or 0),
            "payload_keys": allowed_payload_keys,
        },
    )


def _build_spell_support_options_from_spec(
    spec: dict[str, Any],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    option_values = list(spec.get("options") or [])
    filter_expression = str(spec.get("filter") or "").strip()
    options = _build_spell_options_from_references(option_values, spell_catalog)
    if filter_expression:
        options.extend(_build_additional_spell_filter_options(filter_expression, spell_catalog))
    deduped_options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for option in options:
        value = str(option.get("value") or "").strip()
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        deduped_options.append(dict(option))
    return deduped_options


def _build_spell_options_from_existing_payloads(
    *,
    existing_spells: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    filter_spec: dict[str, Any],
) -> list[dict[str, str]]:
    payload_keys: set[str] = set()
    for spell_payload in list(existing_spells or []):
        payload_key = _spell_payload_key(spell_payload)
        if not payload_key:
            continue
        spell_entry = _resolve_spell_entry(payload_key, spell_catalog)
        if not _spell_payload_matches_replacement_filter(
            spell_payload,
            spell_entry=spell_entry,
            filter_spec=filter_spec,
        ):
            continue
        payload_keys.add(payload_key)
    return _build_spell_options_from_payload_keys(
        payload_keys=payload_keys,
        existing_spells=existing_spells,
        spell_catalog=spell_catalog,
    )


def _spell_payload_matches_replacement_filter(
    spell_payload: dict[str, Any],
    *,
    spell_entry: SystemsEntryRecord | None,
    filter_spec: dict[str, Any],
) -> bool:
    allowed_payload_keys = {
        str(payload_key or "").strip()
        for payload_key in list(filter_spec.get("payload_keys") or [])
        if str(payload_key or "").strip()
    }
    payload_key = str((spell_entry.slug if spell_entry is not None else _spell_payload_key(spell_payload)) or "").strip()
    if allowed_payload_keys and payload_key not in allowed_payload_keys:
        return False
    mark_filter = normalize_lookup(str(filter_spec.get("mark") or "").strip())
    if mark_filter and mark_filter not in normalize_lookup(str(spell_payload.get("mark") or "").strip()):
        return False
    spell_level = int(filter_spec.get("level") or 0)
    if spell_level > 0 and (spell_entry is None or _spell_entry_level(spell_entry) != spell_level):
        return False
    return True


def _build_spell_options_from_references(
    values: list[str],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for raw_value in list(values or []):
        clean_value = str(raw_value or "").strip()
        if not clean_value:
            continue
        entry = _resolve_spell_entry(clean_value, spell_catalog)
        value = entry.slug if entry is not None else _normalize_additional_spell_reference(clean_value)
        label = entry.title if entry is not None else _normalize_additional_spell_reference(clean_value)
        if not value or not label or value in seen_values:
            continue
        seen_values.add(value)
        options.append(_choice_option(label, value))
    return options


def _apply_spell_support_grants_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    grants: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
) -> None:
    for grant in list(grants or []):
        selected_value = str(grant.get("value") or "").strip()
        if not selected_value:
            continue
        if bool(grant.get("bonus_known")):
            _add_bonus_known_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
            )
            continue
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark=str(grant.get("mark") or "").strip(),
            is_always_prepared=bool(grant.get("always_prepared")),
            is_ritual=bool(grant.get("ritual")),
        )


def _apply_selected_spell_support_fields_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> None:
    specs = _extract_spell_support_choice_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        category = str(spec.get("category") or "").strip()
        count = max(int(spec.get("count") or 1), 1)
        for choice_index in range(1, count + 1):
            field_name = _spell_support_choice_field_name(field_prefix, category, spec_index, choice_index)
            selected_value = str(values.get(field_name) or "").strip()
            if not selected_value:
                continue
            if category == "known":
                _add_bonus_known_spell_to_payloads(
                    spells_by_key,
                    selected_value=selected_value,
                    spell_catalog=spell_catalog,
                )
                continue
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=selected_value,
                spell_catalog=spell_catalog,
                mark=str(spec.get("mark") or "").strip(),
                is_always_prepared=bool(spec.get("always_prepared")),
                is_ritual=bool(spec.get("ritual")),
            )


def _apply_selected_spell_support_replacements_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    values: dict[str, str],
    field_prefix: str,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> None:
    specs = _extract_spell_support_replacement_specs(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    )
    for spec_index, spec in enumerate(specs, start=1):
        category = str(spec.get("category") or "known").strip() or "known"
        count = max(int(spec.get("count") or 1), 1)
        for choice_index in range(1, count + 1):
            from_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "from",
            )
            to_name = _spell_support_replacement_field_name(
                field_prefix,
                category,
                spec_index,
                choice_index,
                "to",
            )
            replacement_from = str(values.get(from_name) or "").strip()
            replacement_to = str(values.get(to_name) or "").strip()
            if not replacement_from or not replacement_to:
                continue
            spells_by_key.pop(_spell_lookup_key(replacement_from, spell_catalog), None)
            if category == "known":
                _add_bonus_known_spell_to_payloads(
                    spells_by_key,
                    selected_value=replacement_to,
                    spell_catalog=spell_catalog,
                )
                continue
            _add_spell_to_payloads(
                spells_by_key,
                selected_value=replacement_to,
                spell_catalog=spell_catalog,
                mark=str(spec.get("mark") or "").strip(),
                is_always_prepared=bool(spec.get("always_prepared")),
                is_ritual=bool(spec.get("ritual")),
            )


def _build_feat_spell_choice_fields(
    *,
    feat_selections: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    target_level: int,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for selection in feat_selections:
        fields.extend(
            _build_feat_spell_choice_fields_for_selection(
                selection=selection,
                spell_catalog=spell_catalog,
                values=values,
                target_level=target_level,
            )
        )
    return fields


def _build_feat_spell_choice_fields_for_selection(
    *,
    selection: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    target_level: int,
) -> list[dict[str, Any]]:
    feat_entry = selection.get("entry")
    instance_key = str(selection.get("instance_key") or "").strip()
    if not isinstance(feat_entry, SystemsEntryRecord) or not instance_key:
        return []

    fields: list[dict[str, Any]] = []
    known_specs: list[dict[str, Any]] = []
    prepared_specs: list[dict[str, Any]] = []
    granted_specs: list[dict[str, Any]] = []
    for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
        known_specs.extend(_extract_feat_known_choice_specs(block, target_level=target_level))
        prepared_specs.extend(_extract_feat_prepared_choice_specs(block, target_level=target_level))
        granted_specs.extend(_extract_feat_innate_choice_specs(block, target_level=target_level))

    for spec_index, spec in enumerate(known_specs, start=1):
        fields.extend(
            _build_feat_spell_fields_from_spec(
                feat_title=feat_entry.title,
                instance_key=instance_key,
                category="spell_known",
                spec_index=spec_index,
                spec=spec,
                spell_catalog=spell_catalog,
                values=values,
                default_label_prefix="Granted Spell",
                default_help_text="Choose a feat-granted spell.",
                kind="feat_spell_known",
            )
        )
    for spec_index, spec in enumerate(prepared_specs, start=1):
        spec = {
            **spec,
            "spell_mark": str(spec.get("spell_mark") or "").strip(),
            "spell_is_always_prepared": bool(spec.get("spell_is_always_prepared", True)),
        }
        fields.extend(
            _build_feat_spell_fields_from_spec(
                feat_title=feat_entry.title,
                instance_key=instance_key,
                category="spell_prepared",
                spec_index=spec_index,
                spec=spec,
                spell_catalog=spell_catalog,
                values=values,
                default_label_prefix="Granted Spell",
                default_help_text="Choose a feat-granted spell.",
                kind="feat_spell_prepared",
            )
        )
    for spec_index, spec in enumerate(granted_specs, start=1):
        fields.extend(
            _build_feat_spell_fields_from_spec(
                feat_title=feat_entry.title,
                instance_key=instance_key,
                category="spell_granted",
                spec_index=spec_index,
                spec=spec,
                spell_catalog=spell_catalog,
                values=values,
                default_label_prefix="Granted Spell",
                default_help_text="Choose a feat-granted spell.",
                kind="feat_spell_granted",
            )
        )
    return fields


def _build_feat_spell_fields_from_spec(
    *,
    feat_title: str,
    instance_key: str,
    category: str,
    spec_index: int,
    spec: dict[str, Any],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
    default_label_prefix: str,
    default_help_text: str,
    kind: str,
) -> list[dict[str, Any]]:
    options = _build_additional_spell_filter_options(str(spec.get("filter") or ""), spell_catalog)
    if not options:
        return []
    count = max(int(spec.get("count") or 1), 1)
    is_cantrip = _spell_options_are_cantrips(options, spell_catalog)
    label_prefix = str(spec.get("label_prefix") or "").strip() or ("Granted Cantrip" if is_cantrip else default_label_prefix)
    help_text = str(spec.get("help_text") or "").strip() or (
        "Choose a feat-granted cantrip." if is_cantrip else default_help_text
    )
    fields: list[dict[str, Any]] = []
    for choice_index in range(1, count + 1):
        field_name = _feat_spell_choice_field_name(instance_key, category, spec_index, choice_index)
        fields.append(
            {
                "name": field_name,
                "label": f"{feat_title} {label_prefix} {choice_index}",
                "help_text": help_text,
                "options": options,
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": field_name,
                "kind": kind,
                "spell_mark": str(spec.get("spell_mark") or "").strip(),
                "spell_is_always_prepared": bool(spec.get("spell_is_always_prepared")),
                "spell_is_ritual": bool(spec.get("spell_is_ritual")),
            }
        )
    return fields


def _iter_unlocked_additional_spell_values(
    raw_map: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[Any]:
    values: list[Any] = []
    for raw_unlock_level, raw_value in dict(raw_map or {}).items():
        if str(raw_unlock_level).strip() == "_":
            values.append(raw_value)
            continue
        unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
        if unlock_level is None:
            continue
        if exact_level is not None:
            if unlock_level != exact_level:
                continue
        elif unlock_level > target_level:
            continue
        values.append(raw_value)
    return values


def _extract_feat_known_choice_specs(block: dict[str, Any], *, target_level: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for raw_value in _iter_unlocked_additional_spell_values(block.get("known"), target_level=target_level):
        specs.extend(_extract_choose_additional_spell_specs(raw_value))
    return specs


def _extract_feat_prepared_choice_specs(block: dict[str, Any], *, target_level: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for raw_value in _iter_unlocked_additional_spell_values(block.get("prepared"), target_level=target_level):
        for spec in _extract_choose_additional_spell_specs(raw_value):
            specs.append({**spec, "spell_is_always_prepared": True})
    return specs


def _extract_feat_innate_choice_specs(block: dict[str, Any], *, target_level: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for raw_value in _iter_unlocked_additional_spell_values(block.get("innate"), target_level=target_level):
        innate_block = dict(raw_value or {})
        daily_map = dict(innate_block.get("daily") or {})
        for raw_daily_uses, daily_values in daily_map.items():
            ritual_filter = False
            for spec in _extract_choose_additional_spell_specs(daily_values):
                ritual_filter = _additional_spell_filter_requires_ritual(str(spec.get("filter") or ""))
                specs.append(
                    {
                        **spec,
                        "spell_mark": _format_innate_spell_mark(raw_daily_uses, is_ritual=ritual_filter),
                        "spell_is_ritual": ritual_filter,
                    }
                )
    return specs


def _extract_additional_known_choice_specs(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        for block in list(additional_spells or []):
            if not isinstance(block, dict):
                continue
            known_map = dict(block.get("known") or {})
            for raw_unlock_level, known_values in known_map.items():
                unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
                if unlock_level is None:
                    continue
                if exact_level is not None:
                    if unlock_level != exact_level:
                        continue
                elif unlock_level > target_level:
                    continue
                specs.extend(_extract_choose_additional_spell_specs(known_values))
    return specs


def _extract_choose_additional_spell_specs(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        specs: list[dict[str, Any]] = []
        for item in raw_value:
            specs.extend(_extract_choose_additional_spell_specs(item))
        return specs
    if not isinstance(raw_value, dict):
        return []
    specs: list[dict[str, Any]] = []
    choose_filter = str(raw_value.get("choose") or "").strip()
    if choose_filter:
        specs.append({"filter": choose_filter, "count": max(int(raw_value.get("count") or 1), 1)})
    if "_" in raw_value:
        specs.extend(_extract_choose_additional_spell_specs(raw_value.get("_")))
    return specs


def _build_additional_spell_filter_options(
    filter_expression: str,
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    criteria = _parse_additional_spell_filter(filter_expression)
    if not criteria:
        return []
    entries = list(spell_catalog.get("entries") or [])
    class_name = str(criteria.get("class_name") or "").strip()
    level = criteria.get("level")
    if class_name and level is not None:
        titles = list(
            dict(dict(spell_catalog.get("phb_level_one_lists") or {}).get(class_name) or {}).get(str(level)) or []
        )
        options = (
            _build_spell_options_from_titles(titles, spell_catalog)
            if titles
            else [
                _choice_option(entry.title, entry.slug or entry.title)
                for entry in entries
                if _spell_entry_matches_additional_filter(entry, criteria)
            ]
        )
    else:
        options = [
            _choice_option(entry.title, entry.slug or entry.title)
            for entry in entries
            if _spell_entry_matches_additional_filter(entry, criteria)
        ]
    seen_values: set[str] = set()
    filtered_options: list[dict[str, str]] = []
    for option in options:
        value = str(option.get("value") or "").strip()
        if not value:
            continue
        entry = _resolve_spell_entry(value, spell_catalog)
        if entry is None:
            entry = _resolve_spell_entry(str(option.get("label") or "").strip(), spell_catalog)
        if entry is None:
            continue
        if entry is not None and not _spell_entry_matches_additional_filter(entry, criteria):
            continue
        if value in seen_values:
            continue
        seen_values.add(value)
        filtered_options.append(dict(option))
    return filtered_options


def _parse_additional_spell_filter(filter_expression: str) -> dict[str, Any]:
    criteria: dict[str, Any] = {}
    for fragment in str(filter_expression or "").split("|"):
        key, _, value = fragment.partition("=")
        normalized_key = normalize_lookup(key).replace(" ", "_")
        clean_value = str(value or "").strip()
        if not normalized_key or not clean_value:
            continue
        if normalized_key == "level":
            try:
                criteria["level"] = int(clean_value)
            except ValueError:
                continue
        elif normalized_key == "class":
            criteria["class_name"] = _humanize_words(clean_value)
        elif normalized_key == "school":
            criteria["school"] = clean_value.upper()
        elif normalized_key in {"components_miscellaneous", "miscellaneous"} and normalize_lookup(clean_value) == "ritual":
            criteria["ritual"] = True
    return criteria


def _additional_spell_filter_requires_ritual(filter_expression: str) -> bool:
    return bool(_parse_additional_spell_filter(filter_expression).get("ritual"))


def _spell_entry_matches_additional_filter(entry: SystemsEntryRecord, criteria: dict[str, Any]) -> bool:
    metadata = dict(entry.metadata or {})
    level = criteria.get("level")
    if level is not None and _spell_entry_level(entry) != int(level):
        return False
    school = str(criteria.get("school") or "").strip().upper()
    if school and str(metadata.get("school") or "").strip().upper() != school:
        return False
    if bool(criteria.get("ritual")) and not bool(metadata.get("ritual")):
        return False
    class_name = str(criteria.get("class_name") or "").strip()
    if class_name:
        normalized_class_name = normalize_lookup(class_name)
        class_lists = dict(metadata.get("class_lists") or {})
        has_dynamic_match = any(
            normalized_class_name in {normalize_lookup(title) for title in list(titles or []) if str(title).strip()}
            for titles in class_lists.values()
        )
        if not has_dynamic_match:
            allowed_titles = set(
                dict(dict(_load_phb_level_one_spell_lists() or {}).get(class_name) or {}).get(str(_spell_entry_level(entry))) or []
            )
            if entry.title not in allowed_titles:
                return False
    return True


def _spell_options_are_cantrips(options: list[dict[str, str]], spell_catalog: dict[str, Any]) -> bool:
    if not options:
        return False
    for option in options:
        entry = _resolve_spell_entry(str(option.get("value") or "").strip(), spell_catalog)
        if entry is None or _spell_entry_level(entry) != 0:
            return False
    return True


def _spell_entry_level(entry: SystemsEntryRecord) -> int:
    return int(dict(entry.metadata or {}).get("level") or 0)


def _build_spell_options_from_titles(
    titles: list[str],
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    by_title = dict(spell_catalog.get("by_title") or {})
    options: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for title in titles:
        entry = by_title.get(normalize_lookup(title))
        value = entry.slug if entry is not None else title
        label = entry.title if entry is not None else title
        if value in seen_values:
            continue
        seen_values.add(value)
        options.append(_choice_option(label, value))
    return options


def _expanded_spell_titles_for_level(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    spell_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    titles: list[str] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        titles.extend(
            _extract_expanded_additional_spell_values(
                additional_spells,
                spell_catalog=spell_catalog,
                spell_level=spell_level,
            )
        )
    return _dedupe_preserve_order(titles)


def _extract_expanded_additional_spell_values(
    additional_spells: Any,
    *,
    spell_catalog: dict[str, Any],
    spell_level: int,
) -> list[str]:
    values: list[str] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        expanded_map = dict(block.get("expanded") or {})
        for raw_spell_level, expanded_values in expanded_map.items():
            unlock_level = _parse_additional_spell_unlock_level(raw_spell_level)
            if unlock_level != spell_level:
                continue
            values.extend(_resolve_additional_spell_option_titles(expanded_values, spell_catalog))
    return _dedupe_preserve_order(values)


def _additional_spell_metadata_entries(
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    *,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[Any]:
    values: list[Any] = []
    seen_entries: set[str] = set()
    for entry in (selected_class, selected_subclass):
        metadata = dict((entry.metadata if entry is not None else {}) or {})
        additional_spells = metadata.get("additional_spells")
        if additional_spells:
            values.append(additional_spells)
        if isinstance(entry, SystemsEntryRecord):
            seen_entries.add(str(entry.entry_key or entry.slug or entry.title or ""))
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            continue
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if not entry_key or entry_key in seen_entries:
            continue
        additional_spells = dict(entry.metadata or {}).get("additional_spells")
        if not additional_spells:
            continue
        values.append(additional_spells)
        seen_entries.add(entry_key)
    return values


def _spell_support_metadata_entries(
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    *,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[Any]:
    values: list[Any] = []
    seen_entries: set[str] = set()
    for entry in (selected_class, selected_subclass):
        metadata = dict((entry.metadata if entry is not None else {}) or {})
        spell_support = metadata.get("spell_support")
        if spell_support:
            values.append(spell_support)
        if isinstance(entry, SystemsEntryRecord):
            seen_entries.add(str(entry.entry_key or entry.slug or entry.title or ""))
    for feature_entry in list(feature_entries or []):
        entry = feature_entry.get("entry")
        if not isinstance(entry, SystemsEntryRecord):
            campaign_option = dict(feature_entry.get("campaign_option") or {})
            spell_support = campaign_option.get("spell_support")
            if spell_support:
                values.append(spell_support)
            continue
        entry_key = str(entry.entry_key or entry.slug or entry.title or "").strip()
        if entry_key and entry_key not in seen_entries:
            spell_support = dict(entry.metadata or {}).get("spell_support")
            if spell_support:
                values.append(spell_support)
                seen_entries.add(entry_key)
    return values


def _spell_support_choice_field_name(
    field_prefix: str,
    category: str,
    spec_index: int,
    choice_index: int,
) -> str:
    return f"{field_prefix}_{category}_{spec_index}_{choice_index}"


def _spell_support_replacement_field_name(
    field_prefix: str,
    category: str,
    spec_index: int,
    choice_index: int,
    part: str,
) -> str:
    return f"{field_prefix}_replace_{category}_{spec_index}_{part}_{choice_index}"


def _automatic_spell_support_grants(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for spell_support in _spell_support_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        grants.extend(
            _extract_spell_support_grants(
                spell_support,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    return _dedupe_spell_support_grants(grants)


def _automatic_spell_support_lookup_keys(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> set[str]:
    payload_keys: set[str] = set()
    for grant in _automatic_spell_support_grants(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        payload_key = _spell_lookup_key(str(grant.get("value") or "").strip(), spell_catalog)
        if payload_key:
            payload_keys.add(payload_key)
    return payload_keys


def _extract_spell_support_grants(
    spell_support: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for block in list(spell_support or []):
        if not isinstance(block, dict):
            continue
        for raw_value in _iter_unlocked_additional_spell_values(
            block.get("grants", block.get("fixed")),
            target_level=target_level,
            exact_level=exact_level,
        ):
            grants.extend(_extract_spell_support_grants_from_value(raw_value))
    return grants


def _extract_spell_support_grants_from_value(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        grants: list[dict[str, Any]] = []
        for item in raw_value:
            grants.extend(_extract_spell_support_grants_from_value(item))
        return grants
    if isinstance(raw_value, str):
        clean_value = _normalize_additional_spell_reference(raw_value)
        return (
            [
                {
                    "value": clean_value,
                    "mark": "Granted",
                    "always_prepared": False,
                    "ritual": False,
                    "bonus_known": False,
                }
            ]
            if clean_value
            else []
        )
    if not isinstance(raw_value, dict):
        return []

    grants: list[dict[str, Any]] = []
    if "_" in raw_value:
        grants.extend(_extract_spell_support_grants_from_value(raw_value.get("_")))
    clean_value = _normalize_additional_spell_reference(
        str(
            raw_value.get("spell")
            or raw_value.get("value")
            or raw_value.get("title")
            or raw_value.get("slug")
            or ""
        )
    )
    if not clean_value:
        return grants
    normalized_mark = str(raw_value.get("mark") or "").strip()
    bonus_known = bool(raw_value.get("bonus_known") or raw_value.get("is_bonus_known"))
    if not bonus_known and normalize_lookup(normalized_mark) in {"known", "cantrip"}:
        bonus_known = True
        normalized_mark = ""
    grants.append(
        {
            "value": clean_value,
            "mark": normalized_mark,
            "always_prepared": bool(raw_value.get("always_prepared") or raw_value.get("prepared")),
            "ritual": bool(raw_value.get("ritual") or raw_value.get("is_ritual")),
            "bonus_known": bonus_known,
        }
    )
    return grants


def _dedupe_spell_support_grants(grants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool, bool, bool]] = set()
    for grant in list(grants or []):
        payload = dict(grant or {})
        value = str(payload.get("value") or "").strip()
        if not value:
            continue
        marker = (
            value.casefold(),
            str(payload.get("mark") or "").strip().casefold(),
            bool(payload.get("always_prepared")),
            bool(payload.get("ritual")),
            bool(payload.get("bonus_known")),
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(payload)
    return deduped


def _extract_spell_support_choice_specs(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for spell_support in _spell_support_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        for block in list(spell_support or []):
            if not isinstance(block, dict):
                continue
            for raw_value in _iter_unlocked_additional_spell_values(
                block.get("choices", block.get("select")),
                target_level=target_level,
                exact_level=exact_level,
            ):
                specs.extend(_extract_spell_support_choice_specs_from_value(raw_value))
    return specs


def _extract_spell_support_choice_specs_from_value(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        specs: list[dict[str, Any]] = []
        for item in raw_value:
            specs.extend(_extract_spell_support_choice_specs_from_value(item))
        return specs
    if not isinstance(raw_value, dict):
        return []

    specs: list[dict[str, Any]] = []
    if "_" in raw_value:
        specs.extend(_extract_spell_support_choice_specs_from_value(raw_value.get("_")))
    category = normalize_lookup(str(raw_value.get("category") or raw_value.get("kind") or "").strip())
    if category not in {"known", "prepared", "granted"}:
        return specs
    filter_expression = str(raw_value.get("filter") or raw_value.get("choose") or "").strip()
    option_values = _flatten_additional_spell_values(raw_value.get("options", raw_value.get("spells")))
    if not filter_expression and not option_values:
        return specs
    specs.append(
        {
            "category": category,
            "filter": filter_expression,
            "options": option_values,
            "count": max(int(raw_value.get("count") or 1), 1),
            "label_prefix": str(raw_value.get("label_prefix") or "").strip(),
            "help_text": str(raw_value.get("help_text") or "").strip(),
            "always_prepared": bool(raw_value.get("always_prepared") or raw_value.get("prepared") or category == "prepared"),
            "ritual": bool(raw_value.get("ritual") or raw_value.get("is_ritual")),
            "mark": str(raw_value.get("mark") or ("Granted" if category == "granted" else "")).strip(),
        }
    )
    return specs


def _extract_spell_support_replacement_specs(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for spell_support in _spell_support_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        for block in list(spell_support or []):
            if not isinstance(block, dict):
                continue
            for raw_value in _iter_unlocked_additional_spell_values(
                block.get("replacement", block.get("replacements")),
                target_level=target_level,
                exact_level=exact_level,
            ):
                specs.extend(_extract_spell_support_replacement_specs_from_value(raw_value))
    return specs


def _extract_spell_support_replacement_specs_from_value(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        specs: list[dict[str, Any]] = []
        for item in raw_value:
            specs.extend(_extract_spell_support_replacement_specs_from_value(item))
        return specs
    if not isinstance(raw_value, dict):
        return []

    specs: list[dict[str, Any]] = []
    if "_" in raw_value:
        specs.extend(_extract_spell_support_replacement_specs_from_value(raw_value.get("_")))
    category = normalize_lookup(str(raw_value.get("category") or raw_value.get("kind") or "known").strip()) or "known"
    if category not in {"known", "prepared", "granted"}:
        return specs
    to_payload = dict(raw_value.get("to") or {}) if isinstance(raw_value.get("to"), dict) else {}
    if not to_payload:
        to_payload = dict(raw_value)
    from_payload = dict(raw_value.get("from") or {}) if isinstance(raw_value.get("from"), dict) else {}
    from_filter = str(from_payload.get("filter") or from_payload.get("choose") or "").strip()
    from_options = _flatten_additional_spell_values(from_payload.get("options", from_payload.get("spells")))
    to_filter = str(to_payload.get("filter") or to_payload.get("choose") or "").strip()
    to_options = _flatten_additional_spell_values(to_payload.get("options", to_payload.get("spells")))
    if not to_filter and not to_options:
        return specs
    specs.append(
        {
            "category": category,
            "count": max(int(raw_value.get("count") or 1), 1),
            "from_mark": str(from_payload.get("mark") or "").strip(),
            "from_level": int(from_payload.get("level") or 0),
            "from_filter": from_filter,
            "from_options": from_options,
            "to_filter": to_filter,
            "to_options": to_options,
            "mark": str(raw_value.get("mark") or to_payload.get("mark") or "").strip(),
            "always_prepared": bool(raw_value.get("always_prepared") or to_payload.get("always_prepared")),
            "ritual": bool(raw_value.get("ritual") or to_payload.get("ritual")),
            "help_text_from": str(raw_value.get("help_text_from") or "").strip(),
            "help_text_to": str(raw_value.get("help_text_to") or "").strip(),
        }
    )
    return specs


def _automatic_feat_known_spell_values(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    target_level: int,
) -> list[str]:
    spell_values: list[str] = []
    for selection in feat_selections:
        for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
            spell_values.extend(_extract_known_additional_spell_values([block], target_level=target_level))
    return _dedupe_preserve_order(spell_values)


def _automatic_feat_prepared_spell_values(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    target_level: int,
) -> list[str]:
    spell_values: list[str] = []
    for selection in feat_selections:
        for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
            spell_values.extend(_extract_prepared_additional_spell_values([block], target_level=target_level))
    return _dedupe_preserve_order(spell_values)


def _automatic_feat_innate_spell_values(
    *,
    feat_selections: list[dict[str, Any]],
    values: dict[str, str],
    target_level: int,
) -> list[dict[str, Any]]:
    spell_values: list[dict[str, Any]] = []
    for selection in feat_selections:
        for block in _selected_feat_additional_spell_blocks(selection=selection, values=values):
            spell_values.extend(_extract_innate_additional_spell_values([block], target_level=target_level))
    return _dedupe_innate_spell_values(spell_values)


def _automatic_known_spell_values(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    values: list[str] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        values.extend(
            _extract_known_additional_spell_values(
                additional_spells,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    return _dedupe_preserve_order(values)


def _automatic_known_spell_lookup_keys(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> set[str]:
    payload_keys: set[str] = set()
    for selected_value in _automatic_known_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        payload_key = _spell_lookup_key(selected_value, spell_catalog)
        if payload_key:
            payload_keys.add(payload_key)
    return payload_keys


def _extract_known_additional_spell_values(
    additional_spells: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[str]:
    values: list[str] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        known_map = dict(block.get("known") or {})
        for raw_unlock_level, known_values in known_map.items():
            unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
            if unlock_level is None:
                continue
            if exact_level is not None:
                if unlock_level != exact_level:
                    continue
            elif unlock_level > target_level:
                continue
            values.extend(_flatten_additional_spell_values(known_values))
    return _dedupe_preserve_order(values)


def _automatic_prepared_spell_values(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    values: list[str] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        values.extend(
            _extract_prepared_additional_spell_values(
                additional_spells,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    if not values and exact_level in {None, 1} and target_level >= 1 and selected_subclass is not None:
        subclass_key = normalize_lookup(selected_subclass.title)
        values.extend(LEVEL_ONE_ALWAYS_PREPARED_SPELLS_BY_SUBCLASS.get(subclass_key, []))
    return _dedupe_preserve_order(values)


def _automatic_prepared_spell_lookup_keys(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> set[str]:
    payload_keys: set[str] = set()
    for selected_value in _automatic_prepared_spell_values(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        target_level=target_level,
        exact_level=exact_level,
        feature_entries=feature_entries,
    ):
        payload_key = _spell_lookup_key(selected_value, spell_catalog)
        if payload_key:
            payload_keys.add(payload_key)
    return payload_keys


def _automatic_innate_spell_values(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    target_level: int,
    exact_level: int | None = None,
    feature_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for additional_spells in _additional_spell_metadata_entries(
        selected_class,
        selected_subclass,
        feature_entries=feature_entries,
    ):
        values.extend(
            _extract_innate_additional_spell_values(
                additional_spells,
                target_level=target_level,
                exact_level=exact_level,
            )
        )
    return _dedupe_innate_spell_values(values)


def _extract_prepared_additional_spell_values(
    additional_spells: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[str]:
    values: list[str] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        prepared_map = dict(block.get("prepared") or {})
        for raw_unlock_level, prepared_values in prepared_map.items():
            unlock_level = _parse_additional_spell_unlock_level(raw_unlock_level)
            if unlock_level is None:
                continue
            if exact_level is not None:
                if unlock_level != exact_level:
                    continue
            elif unlock_level > target_level:
                continue
            values.extend(_flatten_additional_spell_values(prepared_values))
    return _dedupe_preserve_order(values)


def _extract_innate_additional_spell_values(
    additional_spells: Any,
    *,
    target_level: int,
    exact_level: int | None = None,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for block in list(additional_spells or []):
        if not isinstance(block, dict):
            continue
        for raw_value in _iter_unlocked_additional_spell_values(
            block.get("innate"),
            target_level=target_level,
            exact_level=exact_level,
        ):
            innate_block = dict(raw_value or {})
            for raw_daily_uses, daily_values in dict(innate_block.get("daily") or {}).items():
                ritual = False
                for spec in _extract_choose_additional_spell_specs(daily_values):
                    ritual = ritual or _additional_spell_filter_requires_ritual(str(spec.get("filter") or ""))
                for spell_name in _flatten_additional_spell_values(daily_values):
                    values.append(
                        {
                            "name": spell_name,
                            "mark": _format_innate_spell_mark(raw_daily_uses, is_ritual=ritual),
                            "is_ritual": ritual,
                        }
                    )
    return _dedupe_innate_spell_values(values)


def _format_innate_spell_mark(raw_daily_uses: Any, *, is_ritual: bool) -> str:
    if is_ritual:
        return "Ritual"
    uses_match = re.search(r"(\d+)", str(raw_daily_uses or "").strip())
    if uses_match is not None:
        return f"{int(uses_match.group(1))} / Long Rest"
    clean_uses = str(raw_daily_uses or "").strip()
    if clean_uses:
        return f"{clean_uses} / Long Rest"
    return "Granted"


def _dedupe_innate_spell_values(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool]] = set()
    for spell_payload in list(values or []):
        payload = dict(spell_payload or {})
        spell_name = str(payload.get("name") or "").strip()
        mark = str(payload.get("mark") or "").strip()
        is_ritual = bool(payload.get("is_ritual"))
        marker = (normalize_lookup(spell_name), mark, is_ritual)
        if not spell_name or marker in seen:
            continue
        seen.add(marker)
        deduped.append(
            {
                "name": spell_name,
                "mark": mark,
                "is_ritual": is_ritual,
            }
        )
    return deduped


def _parse_additional_spell_unlock_level(raw_value: Any) -> int | None:
    if isinstance(raw_value, int):
        return raw_value
    match = re.search(r"(\d+)", str(raw_value or "").strip())
    if match is None:
        return None
    return int(match.group(1))


def _flatten_additional_spell_values(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        normalized_value = _normalize_additional_spell_reference(raw_value)
        return [normalized_value] if normalized_value else []
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_flatten_additional_spell_values(item))
        return values
    if isinstance(raw_value, dict):
        values: list[str] = []
        for key in ("_", "all"):
            if key in raw_value:
                values.extend(_flatten_additional_spell_values(raw_value.get(key)))
        return values
    return []


def _resolve_additional_spell_option_titles(raw_value: Any, spell_catalog: dict[str, Any]) -> list[str]:
    if isinstance(raw_value, str):
        normalized_value = _normalize_additional_spell_reference(raw_value)
        return [normalized_value] if normalized_value else []
    if isinstance(raw_value, list):
        values: list[str] = []
        for item in raw_value:
            values.extend(_resolve_additional_spell_option_titles(item, spell_catalog))
        return values
    if isinstance(raw_value, dict):
        values: list[str] = []
        if "all" in raw_value:
            values.extend(
                option["label"]
                for option in _build_additional_spell_filter_options(str(raw_value.get("all") or ""), spell_catalog)
            )
        if "_" in raw_value:
            values.extend(_resolve_additional_spell_option_titles(raw_value.get("_"), spell_catalog))
        return values
    return []


def _normalize_additional_spell_reference(raw_value: str) -> str:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return ""
    spell_tag_match = re.fullmatch(r"\{@spell ([^}]+)\}", clean_value)
    if spell_tag_match is not None:
        clean_value = spell_tag_match.group(1)
    if "|" in clean_value:
        clean_value = clean_value.split("|", 1)[0]
    if "#" in clean_value:
        clean_value = clean_value.split("#", 1)[0]
    return clean_value.replace("_", " ").strip()


def _summarize_level_up_spell_choices(
    *,
    definition: CharacterDefinition,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    feat_selections: list[dict[str, Any]],
    choice_sections: list[dict[str, Any]],
    values: dict[str, str],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
    target_level: int,
    feature_entries: list[dict[str, Any]] | None = None,
    extra_option_payloads: list[dict[str, Any]] | None = None,
) -> list[str]:
    existing_spell_payload_keys = {
        payload_key
        for spell_payload in list((definition.spellcasting or {}).get("spells") or [])
        if (payload_key := _spell_payload_key(spell_payload))
    }
    simulated_payloads = _build_level_up_spell_payloads(
        current_definition=definition,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        feat_selections=feat_selections,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
        target_level=target_level,
        feature_entries=feature_entries,
        selected_campaign_option_payloads=extra_option_payloads,
    )

    summaries: list[str] = []
    seen: set[str] = set()
    for spell_payload in simulated_payloads:
        payload_key = _spell_payload_key(spell_payload)
        if payload_key and payload_key in existing_spell_payload_keys:
            continue
        label = str(spell_payload.get("name") or "").strip()
        normalized_label = normalize_lookup(label)
        if not label or normalized_label in seen:
            continue
        seen.add(normalized_label)
        summaries.append(label)
    return summaries


def _add_spell_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
    mark: str = "",
    is_always_prepared: bool = False,
    is_bonus_known: bool = False,
    is_ritual: bool = False,
) -> None:
    spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
    spell_payload = _build_spell_payload(selected_value, spell_entry)
    payload_key = str((spell_entry.slug if spell_entry is not None else selected_value) or "").strip()
    if not payload_key:
        return

    existing_payload = spells_by_key.get(payload_key)
    if existing_payload is None:
        if mark:
            spell_payload["mark"] = mark
        if is_always_prepared:
            spell_payload["is_always_prepared"] = True
        if is_bonus_known:
            spell_payload["is_bonus_known"] = True
        if is_ritual:
            spell_payload["is_ritual"] = True
        spells_by_key[payload_key] = spell_payload
        return

    existing_payload["mark"] = _merge_spell_mark(
        str(existing_payload.get("mark") or "").strip(),
        mark,
    )
    if is_always_prepared:
        existing_payload["is_always_prepared"] = True
    if is_bonus_known:
        existing_payload["is_bonus_known"] = True
    if is_ritual:
        existing_payload["is_ritual"] = True


def _add_bonus_known_spell_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
) -> None:
    spell_entry = _resolve_spell_entry(selected_value, spell_catalog)
    mark = "Cantrip" if spell_entry is not None and _spell_entry_level(spell_entry) == 0 else "Known"
    _add_spell_to_payloads(
        spells_by_key,
        selected_value=selected_value,
        spell_catalog=spell_catalog,
        mark=mark,
        is_bonus_known=True,
    )


def _resolve_spell_entry(
    selected_value: str,
    spell_catalog: dict[str, Any],
) -> SystemsEntryRecord | None:
    clean_value = str(selected_value or "").strip()
    if not clean_value:
        return None
    by_slug = dict(spell_catalog.get("by_slug") or {})
    if clean_value in by_slug:
        return by_slug[clean_value]
    return dict(spell_catalog.get("by_title") or {}).get(normalize_lookup(clean_value))


def _build_spell_payload(
    selected_value: str,
    spell_entry: SystemsEntryRecord | None,
) -> dict[str, Any]:
    metadata = dict((spell_entry.metadata if spell_entry is not None else {}) or {})
    title = spell_entry.title if spell_entry is not None else str(selected_value or "").strip()
    source = spell_entry.source_id if spell_entry is not None else PHB_SOURCE_ID
    reference = (
        f"p. {spell_entry.source_page}"
        if spell_entry is not None and str(spell_entry.source_page or "").strip()
        else ""
    )
    return {
        "name": title,
        "casting_time": _format_spell_casting_time(metadata.get("casting_time")),
        "range": _format_spell_range(metadata.get("range")),
        "duration": _format_spell_duration(metadata.get("duration")),
        "components": _format_spell_components(metadata.get("components")),
        "save_or_hit": "",
        "source": source,
        "reference": reference,
        "mark": "",
        "is_always_prepared": False,
        "is_bonus_known": False,
        "is_ritual": bool(metadata.get("ritual")),
        "systems_ref": _systems_ref_from_entry(spell_entry),
    }


def _merge_spell_mark(existing_mark: str, new_mark: str) -> str:
    marks: list[str] = []
    for candidate in (existing_mark, new_mark):
        clean_candidate = str(candidate or "").strip()
        if not clean_candidate:
            continue
        for part in [part.strip() for part in clean_candidate.split("+")]:
            if part and part not in marks:
                marks.append(part)
    return " + ".join(marks)


_MERGE_NAME_ALIASES = {
    "chain mail": "chain mail armor",
    "chain mail armor": "chain mail armor",
    "crossbow, light": "light crossbow",
    "light crossbow": "light crossbow",
    "crossbow bolts": "crossbow bolts (20)",
    "crossbow bolts (20)": "crossbow bolts (20)",
    "rope, hempen (50 feet)": "hempen rope (50 feet)",
    "hempen rope (50 feet)": "hempen rope (50 feet)",
    "rations": "rations (1 day)",
    "rations (1 day)": "rations (1 day)",
}


def _merge_name_candidates(name: Any) -> list[str]:
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        return []
    candidates = [cleaned_name]
    if "," in cleaned_name:
        parts = [part.strip() for part in cleaned_name.split(",", 1)]
        if len(parts) == 2 and all(parts):
            candidates.append(f"{parts[1]} {parts[0]}")
    alias_variants = [_MERGE_NAME_ALIASES.get(candidate.lower(), "") for candidate in list(candidates)]
    candidates.extend(alias for alias in alias_variants if alias)

    normalized_candidates: list[str] = []
    for candidate in candidates:
        normalized = normalize_lookup(candidate)
        if normalized and normalized not in normalized_candidates:
            normalized_candidates.append(normalized)
    return normalized_candidates


def _normalize_spell_payloads(
    spell_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_spells: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for spell_payload in list(spell_payloads or []):
        payload = dict(spell_payload or {})
        name = str(payload.get("name") or "").strip()
        payload_key = _spell_payload_key(payload) or name
        if not payload_key:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_spells) + 1}"
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)

        explicit_identity = _normalize_explicit_link_identity(
            systems_ref=systems_ref,
            page_ref=normalized_page_ref,
        )
        candidate_keys: list[str] = []
        if explicit_identity:
            candidate_keys.append(explicit_identity)
        candidate_keys.extend(f"name:{candidate}" for candidate in _merge_name_candidates(name))

        existing_index = None
        for candidate_key in candidate_keys:
            candidate_index = index_by_key.get(candidate_key)
            if candidate_index is None:
                continue
            if candidate_key.startswith("name:") and explicit_identity:
                existing_payload = normalized_spells[candidate_index]
                existing_explicit_identity = _normalize_explicit_link_identity(
                    systems_ref=dict(existing_payload.get("systems_ref") or {}),
                    page_ref=existing_payload.get("page_ref"),
                )
                if existing_explicit_identity and existing_explicit_identity != explicit_identity:
                    continue
            existing_index = candidate_index
            break

        existing_payload = normalized_spells[existing_index] if existing_index is not None else None
        if existing_payload is None:
            existing_index = len(normalized_spells)
            normalized_spells.append(payload)
            for candidate_key in candidate_keys:
                index_by_key[candidate_key] = existing_index
            continue
        existing_payload["mark"] = _merge_spell_mark(
            str(existing_payload.get("mark") or "").strip(),
            str(payload.get("mark") or "").strip(),
        )
        for key in ("is_always_prepared", "is_bonus_known", "is_ritual"):
            if bool(payload.get(key)):
                existing_payload[key] = True
        for key in ("casting_time", "range", "duration", "components", "save_or_hit", "source", "reference"):
            if not str(existing_payload.get(key) or "").strip() and str(payload.get(key) or "").strip():
                existing_payload[key] = payload.get(key)
        if not existing_payload.get("systems_ref") and payload.get("systems_ref"):
            existing_payload["systems_ref"] = dict(payload.get("systems_ref") or {})
        if not existing_payload.get("page_ref") and payload.get("page_ref"):
            existing_payload["page_ref"] = payload.get("page_ref")
        if list(payload.get("campaign_option_sources") or []):
            existing_payload["campaign_option_sources"] = _dedupe_campaign_spell_sources(
                list(existing_payload.get("campaign_option_sources") or [])
                + list(payload.get("campaign_option_sources") or [])
            )
        updated_explicit_identity = _normalize_explicit_link_identity(
            systems_ref=dict(existing_payload.get("systems_ref") or {}),
            page_ref=existing_payload.get("page_ref"),
        )
        updated_keys: list[str] = []
        if updated_explicit_identity:
            updated_keys.append(updated_explicit_identity)
        updated_keys.extend(
            f"name:{candidate}"
            for candidate in _merge_name_candidates(str(existing_payload.get("name") or "").strip())
        )
        for candidate_key in updated_keys:
            index_by_key[candidate_key] = existing_index
    return normalized_spells


def _normalize_feature_payloads(
    feature_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_features: list[dict[str, Any]] = []
    for feature_payload in list(feature_payloads or []):
        payload = dict(feature_payload or {})
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_features) + 1}"
        payload["category"] = str(payload.get("category") or "").strip() or "class_feature"
        payload["source"] = str(payload.get("source") or "").strip()
        payload["description_markdown"] = str(payload.get("description_markdown") or "").strip()
        payload["activation_type"] = str(payload.get("activation_type") or "passive").strip() or "passive"
        tracker_ref = str(payload.get("tracker_ref") or "").strip()
        if tracker_ref:
            payload["tracker_ref"] = tracker_ref
        else:
            payload.pop("tracker_ref", None)
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)
        campaign_option = dict(payload.get("campaign_option") or {})
        if campaign_option:
            payload["campaign_option"] = campaign_option
        else:
            payload.pop("campaign_option", None)
        normalized_features.append(payload)
    return normalized_features


def _normalize_resource_template_payloads(
    resource_templates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_templates: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for template in list(resource_templates or []):
        payload = dict(template or {})
        template_id = str(payload.get("id") or "").strip()
        label = str(payload.get("label") or "").strip()
        if not template_id and not label:
            continue
        payload["id"] = template_id or f"resource-{slugify(label or 'template')}-{len(normalized_templates) + 1}"
        payload["label"] = label or payload["id"]
        payload["category"] = str(payload.get("category") or "custom_progress").strip() or "custom_progress"
        max_value = payload.get("max")
        payload["max"] = int(max_value) if max_value not in {"", None} else None
        initial_current = payload.get("initial_current")
        payload["initial_current"] = (
            int(initial_current)
            if initial_current not in {"", None}
            else payload.get("max")
        )
        payload["reset_on"] = str(payload.get("reset_on") or "manual").strip() or "manual"
        payload["reset_to"] = str(payload.get("reset_to") or "unchanged").strip() or "unchanged"
        payload["rest_behavior"] = str(payload.get("rest_behavior") or "manual_only").strip() or "manual_only"
        payload["notes"] = str(payload.get("notes") or "").strip()
        payload["display_order"] = int(payload.get("display_order") or 0)
        merge_key = payload["id"]
        existing_index = index_by_key.get(merge_key)
        if existing_index is None:
            index_by_key[merge_key] = len(normalized_templates)
            normalized_templates.append(payload)
            continue
        normalized_templates[existing_index] = payload
    return normalized_templates


def _normalize_attack_payloads(
    attack_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_attacks: list[dict[str, Any]] = []
    index_by_key: dict[tuple[Any, ...], int] = {}
    for attack_payload in list(attack_payloads or []):
        payload = dict(attack_payload or {})
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_attacks) + 1}"
        payload["category"] = str(payload.get("category") or "").strip()
        payload["damage"] = str(payload.get("damage") or "").strip()
        payload["damage_type"] = str(payload.get("damage_type") or "").strip()
        payload["notes"] = str(payload.get("notes") or "").strip()
        inferred_mode_key = _infer_attack_mode_key_from_payload(payload)
        if inferred_mode_key:
            payload["mode_key"] = inferred_mode_key
        else:
            payload.pop("mode_key", None)
        normalized_variant_label = _normalize_attack_variant_label(
            raw_variant_label=payload.get("variant_label"),
            mode_key=inferred_mode_key,
            attack_name=name,
            notes=payload.get("notes"),
        )
        if normalized_variant_label:
            payload["variant_label"] = normalized_variant_label
        else:
            payload.pop("variant_label", None)
        attack_bonus = payload.get("attack_bonus")
        if attack_bonus in {"", None}:
            payload["attack_bonus"] = None
        else:
            try:
                payload["attack_bonus"] = int(attack_bonus)
            except (TypeError, ValueError):
                pass
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        equipment_refs = _normalize_attack_equipment_refs(
            payload.get("equipment_refs"),
            fallback=payload.get("equipment_ref"),
        )
        if equipment_refs:
            payload["equipment_refs"] = equipment_refs
        else:
            payload.pop("equipment_refs", None)
        payload.pop("equipment_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)
        normalized_damage = _normalize_merge_text(payload.get("damage"))
        normalized_damage_type = _normalize_merge_text(payload.get("damage_type"))
        normalized_notes = _normalize_merge_text(payload.get("notes"))
        normalized_category = _normalize_merge_text(payload.get("category"))
        normalized_mode_key = str(payload.get("mode_key") or "").strip()
        normalized_page_identity = _extract_campaign_page_ref(normalized_page_ref)
        explicit_identity = _normalize_explicit_link_identity(
            systems_ref=systems_ref,
            page_ref=normalized_page_ref,
        )
        equipment_identity_keys = [
            f"equipment:{equipment_ref}"
            for equipment_ref in list(equipment_refs or [])
            if str(equipment_ref or "").strip()
        ]
        merge_key_tail = (
            payload.get("attack_bonus"),
            normalized_damage,
            normalized_damage_type,
            normalized_notes,
            normalized_category,
            normalized_mode_key,
            normalized_page_identity,
        )
        candidate_keys = []
        if explicit_identity:
            candidate_keys.append((explicit_identity, *merge_key_tail))
        candidate_keys.extend((equipment_identity, *merge_key_tail) for equipment_identity in equipment_identity_keys)
        candidate_keys.extend(
            (f"name:{candidate}", *merge_key_tail)
            for candidate in _merge_name_candidates(name)
        )
        existing_index = None
        for candidate_key in candidate_keys:
            candidate_index = index_by_key.get(candidate_key)
            if candidate_index is None:
                continue
            if (candidate_key[0].startswith("name:") or candidate_key[0].startswith("equipment:")) and explicit_identity:
                existing_payload = normalized_attacks[candidate_index]
                existing_explicit_identity = _normalize_explicit_link_identity(
                    systems_ref=dict(existing_payload.get("systems_ref") or {}),
                    page_ref=existing_payload.get("page_ref"),
                )
                if existing_explicit_identity and existing_explicit_identity != explicit_identity:
                    continue
            existing_index = candidate_index
            break
        if existing_index is None:
            existing_index = len(normalized_attacks)
            normalized_attacks.append(payload)
            for candidate_key in candidate_keys:
                index_by_key[candidate_key] = existing_index
            continue
        existing_payload = normalized_attacks[existing_index]
        if not existing_payload.get("systems_ref") and payload.get("systems_ref"):
            existing_payload["systems_ref"] = dict(payload.get("systems_ref") or {})
        if not existing_payload.get("page_ref") and payload.get("page_ref"):
            existing_payload["page_ref"] = payload.get("page_ref")
        if not existing_payload.get("mode_key") and payload.get("mode_key"):
            existing_payload["mode_key"] = str(payload.get("mode_key") or "").strip()
        if not existing_payload.get("variant_label") and payload.get("variant_label"):
            existing_payload["variant_label"] = str(payload.get("variant_label") or "").strip()
        merged_equipment_refs = _normalize_attack_equipment_refs(
            [
                *list(existing_payload.get("equipment_refs") or []),
                *list(payload.get("equipment_refs") or []),
            ]
        )
        if merged_equipment_refs:
            existing_payload["equipment_refs"] = merged_equipment_refs
        updated_mode_key = _infer_attack_mode_key_from_payload(existing_payload)
        if updated_mode_key:
            existing_payload["mode_key"] = updated_mode_key
        else:
            existing_payload.pop("mode_key", None)
        updated_variant_label = _normalize_attack_variant_label(
            raw_variant_label=existing_payload.get("variant_label"),
            mode_key=updated_mode_key,
            attack_name=existing_payload.get("name"),
            notes=existing_payload.get("notes"),
        )
        if updated_variant_label:
            existing_payload["variant_label"] = updated_variant_label
        else:
            existing_payload.pop("variant_label", None)
        updated_explicit_identity = _normalize_explicit_link_identity(
            systems_ref=dict(existing_payload.get("systems_ref") or {}),
            page_ref=existing_payload.get("page_ref"),
        )
        updated_merge_key_tail = (
            existing_payload.get("attack_bonus"),
            _normalize_merge_text(existing_payload.get("damage")),
            _normalize_merge_text(existing_payload.get("damage_type")),
            _normalize_merge_text(existing_payload.get("notes")),
            _normalize_merge_text(existing_payload.get("category")),
            str(existing_payload.get("mode_key") or "").strip(),
            _extract_campaign_page_ref(existing_payload.get("page_ref")),
        )
        updated_keys = []
        if updated_explicit_identity:
            updated_keys.append((updated_explicit_identity, *updated_merge_key_tail))
        updated_keys.extend(
            (f"equipment:{equipment_ref}", *updated_merge_key_tail)
            for equipment_ref in list(existing_payload.get("equipment_refs") or [])
            if str(equipment_ref or "").strip()
        )
        updated_keys.extend(
            (f"name:{candidate}", *updated_merge_key_tail)
            for candidate in _merge_name_candidates(str(existing_payload.get("name") or "").strip())
        )
        for candidate_key in updated_keys:
            index_by_key[candidate_key] = existing_index
    return normalized_attacks


def _normalize_attack_equipment_refs(
    raw_refs: Any,
    *,
    fallback: Any = None,
) -> list[str]:
    values = raw_refs
    if values is None or values == "" or values == [] or values == ():
        values = fallback
    if values is None or values == "" or values == [] or values == ():
        return []
    if isinstance(values, (list, tuple, set)):
        candidates = list(values)
    else:
        candidates = [values]
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean_value = str(candidate or "").strip()
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        normalized.append(clean_value)
    return normalized


def _normalize_equipment_payloads(
    equipment_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_equipment: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str, str, str, bool], int] = {}
    for equipment_payload in list(equipment_payloads or []):
        payload = dict(equipment_payload or {})
        currency = dict(payload.get("currency") or {})
        is_currency_only = bool(payload.get("is_currency_only"))
        name = str(payload.get("name") or "").strip() or (_format_currency_seed(currency) if currency else "")
        if not name:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_equipment) + 1}"
        quantity = payload.get("default_quantity", payload.get("quantity"))
        payload["default_quantity"] = _normalize_equipment_quantity(quantity, fallback=1 if name else 0)
        payload["weight"] = str(payload.get("weight") or "").strip()
        payload["notes"] = str(payload.get("notes") or "").strip()
        payload["source_kind"] = str(payload.get("source_kind") or "").strip()
        payload["is_equipped"] = bool(payload.get("is_equipped", False))
        payload["is_attuned"] = bool(payload.get("is_attuned", False))
        payload["charges_current"] = payload.get("charges_current")
        payload["charges_max"] = payload.get("charges_max")
        payload["tags"] = [str(tag).strip() for tag in list(payload.get("tags") or []) if str(tag).strip()]
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)
        campaign_option = dict(payload.get("campaign_option") or {})
        if campaign_option:
            payload["campaign_option"] = campaign_option
        else:
            payload.pop("campaign_option", None)
        payload["currency"] = currency
        payload["is_currency_only"] = is_currency_only
        explicit_identity = _normalize_explicit_link_identity(
            systems_ref=systems_ref,
            page_ref=normalized_page_ref,
        )
        merge_key_tail = (
            _extract_campaign_page_ref(normalized_page_ref),
            _normalize_merge_text(payload.get("notes")),
            _normalize_merge_text(payload.get("weight")),
            is_currency_only,
        )
        candidate_keys = []
        if explicit_identity:
            candidate_keys.append((explicit_identity, *merge_key_tail))
        candidate_keys.extend(
            (f"name:{candidate}", *merge_key_tail)
            for candidate in _merge_name_candidates(name)
        )
        existing_index = None
        for candidate_key in candidate_keys:
            candidate_index = index_by_key.get(candidate_key)
            if candidate_index is None:
                continue
            if candidate_key[0].startswith("name:") and explicit_identity:
                existing_payload = normalized_equipment[candidate_index]
                existing_explicit_identity = _normalize_explicit_link_identity(
                    systems_ref=dict(existing_payload.get("systems_ref") or {}),
                    page_ref=existing_payload.get("page_ref"),
                )
                if existing_explicit_identity and existing_explicit_identity != explicit_identity:
                    continue
            existing_index = candidate_index
            break
        if existing_index is None:
            existing_index = len(normalized_equipment)
            normalized_equipment.append(payload)
            for candidate_key in candidate_keys:
                index_by_key[candidate_key] = existing_index
            continue
        existing_payload = normalized_equipment[existing_index]
        existing_payload["default_quantity"] = int(existing_payload.get("default_quantity") or 0) + int(
            payload.get("default_quantity") or 0
        )
        existing_payload["currency"] = _merge_currency_seed(
            dict(existing_payload.get("currency") or {}),
            dict(payload.get("currency") or {}),
        )
        if not existing_payload.get("systems_ref") and payload.get("systems_ref"):
            existing_payload["systems_ref"] = dict(payload.get("systems_ref") or {})
        if not existing_payload.get("page_ref") and payload.get("page_ref"):
            existing_payload["page_ref"] = payload.get("page_ref")
        if not existing_payload.get("source_kind") and payload.get("source_kind"):
            existing_payload["source_kind"] = str(payload.get("source_kind") or "").strip()
        if not existing_payload.get("campaign_option") and payload.get("campaign_option"):
            existing_payload["campaign_option"] = dict(payload.get("campaign_option") or {})
        existing_payload["is_equipped"] = bool(existing_payload.get("is_equipped", False)) or bool(
            payload.get("is_equipped", False)
        )
        existing_payload["is_attuned"] = bool(existing_payload.get("is_attuned", False)) or bool(
            payload.get("is_attuned", False)
        )
        if existing_payload.get("charges_current") in ("", None) and payload.get("charges_current") not in ("", None):
            existing_payload["charges_current"] = payload.get("charges_current")
        if existing_payload.get("charges_max") in ("", None) and payload.get("charges_max") not in ("", None):
            existing_payload["charges_max"] = payload.get("charges_max")
        existing_payload["tags"] = _dedupe_preserve_order(
            list(existing_payload.get("tags") or []) + list(payload.get("tags") or [])
        )
        updated_explicit_identity = _normalize_explicit_link_identity(
            systems_ref=dict(existing_payload.get("systems_ref") or {}),
            page_ref=existing_payload.get("page_ref"),
        )
        updated_keys = []
        if updated_explicit_identity:
            updated_keys.append((updated_explicit_identity, *merge_key_tail))
        updated_keys.extend(
            (f"name:{candidate}", *merge_key_tail)
            for candidate in _merge_name_candidates(str(existing_payload.get("name") or "").strip())
        )
        for candidate_key in updated_keys:
            index_by_key[candidate_key] = existing_index
    return normalized_equipment


def _normalize_page_ref_payload(page_ref: Any) -> Any:
    if isinstance(page_ref, dict):
        return dict(page_ref)
    clean_page_ref = str(page_ref or "").strip()
    if clean_page_ref:
        return clean_page_ref
    return None


def _normalize_explicit_link_identity(*, systems_ref: dict[str, Any] | None, page_ref: Any) -> str:
    page_identity = _extract_campaign_page_ref(page_ref)
    if page_identity:
        return f"page:{normalize_lookup(page_identity)}"
    systems_payload = dict(systems_ref or {})
    systems_slug = str(systems_payload.get("slug") or "").strip()
    if systems_slug:
        return f"systems:{normalize_lookup(systems_slug)}"
    systems_entry_type = normalize_lookup(str(systems_payload.get("entry_type") or "").strip())
    systems_source_id = normalize_lookup(str(systems_payload.get("source_id") or "").strip())
    systems_title = str(systems_payload.get("title") or "").strip()
    if systems_title:
        qualifier = ":".join(part for part in (systems_entry_type, systems_source_id) if part)
        if qualifier:
            return f"systems-title:{qualifier}:{normalize_lookup(systems_title)}"
        return f"systems-title:{normalize_lookup(systems_title)}"
    return ""


def _normalize_merge_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_equipment_quantity(value: Any, *, fallback: int) -> int:
    if value in {"", None}:
        return max(int(fallback or 0), 0)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return max(int(fallback or 0), 0)


def _dedupe_campaign_spell_sources(sources: list[Any]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool, bool]] = set()
    for source in list(sources or []):
        payload = dict(source or {})
        marker = (
            str(payload.get("source_ref") or "").strip(),
            str(payload.get("mark") or "").strip(),
            bool(payload.get("always_prepared")),
            bool(payload.get("ritual")),
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(payload)
    return deduped


def normalize_definition_to_native_model(
    definition: CharacterDefinition,
    *,
    item_catalog: dict[str, Any] | None = None,
    spell_catalog: dict[str, Any] | None = None,
    systems_service: Any | None = None,
    campaign_page_records: list[Any] | None = None,
    resolved_class: SystemsEntryRecord | None = None,
    resolved_subclass: SystemsEntryRecord | None = None,
    resolved_species: SystemsEntryRecord | None = None,
    resolved_background: SystemsEntryRecord | None = None,
) -> CharacterDefinition:
    payload = deepcopy(definition.to_dict())
    payload["source"] = _seed_source_hp_baseline_from_definition(payload.get("source"), definition)
    seeded_definition = CharacterDefinition.from_dict(payload)
    payload.update(
        _derive_definition_core_sheet_payloads(
            seeded_definition,
            item_catalog=item_catalog,
            spell_catalog=spell_catalog,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            resolved_class=resolved_class,
            resolved_subclass=resolved_subclass,
            resolved_species=resolved_species,
            resolved_background=resolved_background,
        )
    )
    return CharacterDefinition.from_dict(payload)


def _summarize_preview_spell(spell: dict[str, Any]) -> str:
    name = str(spell.get("name") or "").strip()
    badges = []
    if bool(spell.get("is_always_prepared")):
        badges.append("Always prepared")
    elif bool(spell.get("is_bonus_known")):
        badges.append("Granted")
    mark = str(spell.get("mark") or "").strip()
    if mark:
        badges.append(mark)
    if not name:
        return ""
    if badges:
        return f"{name} ({', '.join(badges)})"
    return name


def _format_spell_casting_time(value: Any) -> str:
    blocks = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            cleaned = _clean_embedded_text(str(block or ""))
            if cleaned:
                parts.append(cleaned)
            continue
        amount = int(block.get("number") or 1)
        unit = str(block.get("unit") or "").replace("_", " ").strip()
        if not unit:
            continue
        label = unit if amount == 1 else f"{unit}s"
        parts.append(f"{amount} {label}")
    return ", ".join(parts) or "--"


def _format_spell_range(value: Any) -> str:
    if isinstance(value, str):
        return _clean_embedded_text(value) or "--"
    if not isinstance(value, dict):
        return "--"
    range_type = str(value.get("type") or "").strip().lower()
    if range_type == "point":
        distance = dict(value.get("distance") or {})
        distance_type = str(distance.get("type") or "").strip().lower()
        amount = distance.get("amount")
        if distance_type == "self":
            return "Self"
        if distance_type == "touch":
            return "Touch"
        if amount is not None:
            if distance_type == "feet":
                return f"{int(amount)} feet"
            if distance_type:
                return f"{amount} {distance_type}"
            return str(amount)
    if range_type == "special":
        return "Special"
    if range_type == "self":
        return "Self"
    return "--"


def _format_spell_duration(value: Any) -> str:
    blocks = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            cleaned = _clean_embedded_text(block)
            if cleaned:
                parts.append(cleaned)
            continue
        if not isinstance(block, dict):
            continue
        duration_type = str(block.get("type") or "").strip().lower()
        if duration_type == "instant":
            parts.append("Instantaneous")
            continue
        if duration_type == "permanent":
            parts.append("Permanent")
            continue
        if duration_type == "special":
            parts.append("Special")
            continue
        if duration_type == "timed":
            duration = dict(block.get("duration") or {})
            amount = int(duration.get("amount") or 1)
            unit = str(duration.get("type") or "").replace("_", " ").strip()
            if unit:
                label = unit if amount == 1 else f"{unit}s"
                prefix = "Concentration, up to " if bool(block.get("concentration")) else ""
                parts.append(f"{prefix}{amount} {label}")
    return ", ".join(parts) or "--"


def _format_spell_components(value: Any) -> str:
    if isinstance(value, str):
        return _clean_embedded_text(value) or "--"
    if not isinstance(value, dict):
        return "--"
    parts: list[str] = []
    if value.get("v"):
        parts.append("V")
    if value.get("s"):
        parts.append("S")
    material = value.get("m")
    if material:
        if isinstance(material, str):
            parts.append(f"M ({_clean_embedded_text(material)})")
        else:
            parts.append("M")
    return ", ".join(parts) or "--"


def _humanize_item_reference(value: str) -> str:
    base_value = str(value or "").split("|", 1)[0].strip()
    if not base_value:
        return ""
    if any(character.isupper() for character in base_value):
        return base_value
    return _humanize_words(base_value)


def _format_weight_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, int):
        return f"{value} lb."
    if isinstance(value, float):
        return f"{int(value) if value.is_integer() else value} lb."
    cleaned = _clean_embedded_text(str(value))
    return cleaned


def _currency_seed_from_cp(value: Any) -> dict[str, int]:
    try:
        total_cp = int(value or 0)
    except (TypeError, ValueError):
        return {}
    if total_cp <= 0:
        return {}
    gp, remainder = divmod(total_cp, 100)
    sp, cp = divmod(remainder, 10)
    return {"cp": cp, "sp": sp, "ep": 0, "gp": gp, "pp": 0}


def _merge_currency_seed(existing: dict[str, int], new: dict[str, int]) -> dict[str, int]:
    return {
        denomination: int(existing.get(denomination) or 0) + int(new.get(denomination) or 0)
        for denomination in ("cp", "sp", "ep", "gp", "pp")
    }


def _collect_currency_seed_from_equipment(equipment_catalog: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}
    for item in equipment_catalog:
        totals = _merge_currency_seed(totals, dict(item.get("currency") or {}))
    return totals


def _format_currency_seed(currency: dict[str, int]) -> str:
    parts = [
        f"{int(currency.get(denomination) or 0)} {denomination}"
        for denomination in ("pp", "gp", "ep", "sp", "cp")
        if int(currency.get(denomination) or 0) > 0
    ]
    return ", ".join(parts)


def _format_contained_value(value: Any) -> str:
    label = _format_currency_seed(_currency_seed_from_cp(value))
    if not label:
        return ""
    return f"Contains {label}."


def _extract_class_armor_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    raw_values = list(dict(selected_class.metadata.get("starting_proficiencies") or {}).get("armor") or [])
    return [_humanize_proficiency_value(value, category="armor") for value in raw_values]


def _extract_class_weapon_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    raw_values = list(dict(selected_class.metadata.get("starting_proficiencies") or {}).get("weapons") or [])
    return [_humanize_proficiency_value(value, category="weapons") for value in raw_values]


def _extract_class_tool_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    raw_values = list(dict(selected_class.metadata.get("starting_proficiencies") or {}).get("tools") or [])
    return [_clean_embedded_text(str(value or "")) for value in raw_values if _clean_embedded_text(str(value or ""))]


def _extract_fixed_skills(entry: SystemsEntryRecord | None) -> list[str]:
    if entry is None:
        return []
    metadata = dict(entry.metadata or {})
    raw_blocks = list(metadata.get("skill_proficiencies") or [])
    results: list[str] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        if "choose" in block or "any" in block:
            continue
        for key, value in block.items():
            if value is True:
                results.append(_skill_label(key))
    return results


def _extract_fixed_languages(entry: SystemsEntryRecord | None) -> list[str]:
    if entry is None:
        return []
    metadata = dict(entry.metadata or {})
    raw_blocks = list(metadata.get("languages") or metadata.get("language_proficiencies") or [])
    results: list[str] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if value is True:
                results.append(_humanize_proficiency_value(key, category="languages"))
    return results


def _extract_fixed_tool_proficiencies(entry: SystemsEntryRecord | None) -> list[str]:
    if entry is None:
        return []
    metadata = dict(entry.metadata or {})
    raw_blocks = list(metadata.get("tool_proficiencies") or [])
    results: list[str] = []
    for block in raw_blocks:
        if isinstance(block, str):
            cleaned = _clean_embedded_text(block)
            if cleaned:
                results.append(cleaned)
            continue
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if value is True:
                results.append(_clean_embedded_text(key))
    return results


def _extract_species_feature_entries(entry: SystemsEntryRecord) -> list[dict[str, Any]]:
    raw_entries = list((entry.body or {}).get("entries") or [])
    feature_entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        raw_name = str(raw_entry.get("name") or "").strip()
        normalized_name = normalize_lookup(raw_name.replace("Feature:", "").strip())
        if not raw_name or normalized_name in REDUNDANT_SPECIES_TRAIT_NAMES:
            continue
        description_markdown = _flatten_entry_markdown(raw_entry.get("entries"))
        if not description_markdown:
            continue
        feature_entries.append(
            {
                "kind": "species_trait",
                "label": raw_name.replace("Feature:", "").strip(),
                "description_markdown": description_markdown,
                "systems_entry": entry,
            }
        )
    return feature_entries


def _extract_background_feature_entries(entry: SystemsEntryRecord) -> list[dict[str, Any]]:
    raw_entries = list((entry.body or {}).get("entries") or [])
    feature_entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        if not bool(dict(raw_entry.get("data") or {}).get("isFeature")):
            continue
        raw_name = str(raw_entry.get("name") or "").strip()
        label = raw_name.replace("Feature:", "").strip() or entry.title
        description_markdown = _flatten_entry_markdown(raw_entry.get("entries"))
        if not description_markdown:
            continue
        feature_entries.append(
            {
                "kind": "background_feature",
                "label": label,
                "description_markdown": description_markdown,
                "systems_entry": entry,
            }
        )
    return feature_entries


def _flatten_entry_markdown(value: Any) -> str:
    blocks: list[str] = []
    if isinstance(value, str):
        return _clean_embedded_text(value)
    if isinstance(value, list):
        for item in value:
            rendered = _flatten_entry_markdown(item)
            if rendered:
                blocks.append(rendered)
        return "\n\n".join(blocks).strip()
    if isinstance(value, dict):
        nested_entries = value.get("entries")
        if nested_entries is not None:
            return _flatten_entry_markdown(nested_entries)
        if value.get("entry"):
            return _clean_embedded_text(str(value.get("entry") or ""))
    return ""


def _systems_ref_from_entry(entry: SystemsEntryRecord | None) -> dict[str, str] | None:
    if entry is None:
        return None
    return {
        "entry_key": entry.entry_key,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "slug": entry.slug,
        "source_id": entry.source_id,
    }


def _character_feature_category(entry_type: str) -> str:
    if entry_type == "feat":
        return "feat"
    if entry_type == "race":
        return "species_trait"
    if entry_type == "background":
        return "background_feature"
    return "class_feature"


def _resource_value_by_level(current_level: int, thresholds: list[tuple[int, int]]) -> int:
    value = 0
    for minimum_level, scaled_value in thresholds:
        if current_level >= minimum_level:
            value = scaled_value
    return value


def _feature_has_effect(effect_keys: set[str], *values: str) -> bool:
    return any(normalize_lookup(value) in effect_keys for value in values if str(value or "").strip())


def _build_feature_tracker_template(
    feature_payload: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    display_order: int,
) -> dict[str, Any] | None:
    feature_name = str(feature_payload.get("name") or "").strip()
    normalized = normalize_lookup(feature_name)
    effect_keys = {normalize_lookup(value) for value in _feat_effect_keys_for_feature(feature_payload) if str(value or "").strip()}
    if normalized == normalize_lookup("Second Wind"):
        return {
            "id": "second-wind",
            "label": "Second Wind",
            "category": "class_feature",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Second Wind",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if normalized == normalize_lookup("Rage"):
        uses = _resource_value_by_level(current_level, [(1, 2), (3, 3), (6, 4), (12, 5), (17, 6)]) or 2
        return {
            "id": "rage",
            "label": "Rage",
            "category": "class_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Rage",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if normalized == normalize_lookup("Bardic Inspiration"):
        uses = max(_ability_modifier(ability_scores.get("cha", DEFAULT_ABILITY_SCORE)), 1)
        return {
            "id": "bardic-inspiration",
            "label": "Bardic Inspiration",
            "category": "class_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "short_rest" if current_level >= 5 else "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Bardic Inspiration",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if normalized == normalize_lookup("Action Surge"):
        uses = _resource_value_by_level(current_level, [(2, 1), (17, 2)]) or 1
        return {
            "id": "action-surge",
            "label": "Action Surge",
            "category": "class_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Action Surge",
            "display_order": display_order,
            "activation_type": "special",
        }
    if normalized == normalize_lookup("Arcane Recovery"):
        return {
            "id": "arcane-recovery",
            "label": "Arcane Recovery",
            "category": "class_feature",
            "initial_current": 1,
            "max": 1,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Arcane Recovery",
            "display_order": display_order,
            "activation_type": "special",
        }
    if normalized == normalize_lookup("Divine Sense"):
        uses = max(1 + _ability_modifier(ability_scores.get("cha", DEFAULT_ABILITY_SCORE)), 1)
        return {
            "id": "divine-sense",
            "label": "Divine Sense",
            "category": "class_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Divine Sense",
            "display_order": display_order,
            "activation_type": "action",
        }
    if normalized == normalize_lookup("Lay on Hands"):
        pool = max(current_level * 5, 5)
        return {
            "id": "lay-on-hands",
            "label": "Lay on Hands",
            "category": "class_feature",
            "initial_current": pool,
            "max": pool,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Lay on Hands pool",
            "display_order": display_order,
            "activation_type": "action",
        }
    if normalized == normalize_lookup("Channel Divinity"):
        uses = _resource_value_by_level(current_level, [(2, 1), (6, 2), (18, 3)]) or 1
        return {
            "id": "channel-divinity",
            "label": "Channel Divinity",
            "category": "class_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Channel Divinity",
            "display_order": display_order,
            "activation_type": "passive",
        }
    if normalized == normalize_lookup("Wild Shape"):
        return {
            "id": "wild-shape",
            "label": "Wild Shape",
            "category": "class_feature",
            "initial_current": 2,
            "max": 2,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Wild Shape",
            "display_order": display_order,
            "activation_type": "action",
        }
    if normalized == normalize_lookup("War Priest"):
        uses = max(_ability_modifier(ability_scores.get("wis", DEFAULT_ABILITY_SCORE)), 1)
        return {
            "id": "war-priest",
            "label": "War Priest",
            "category": "subclass_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "War Priest",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if normalized == normalize_lookup("Arcane Shot"):
        return {
            "id": "arcane-shot",
            "label": "Arcane Shot",
            "category": "subclass_feature",
            "initial_current": 2,
            "max": 2,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Arcane Shot",
            "display_order": display_order,
            "activation_type": "special",
        }
    if normalized == normalize_lookup("Ki"):
        points = max(current_level, 2)
        return {
            "id": "ki",
            "label": "Ki",
            "category": "class_feature",
            "initial_current": points,
            "max": points,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Ki",
            "display_order": display_order,
            "activation_type": "passive",
        }
    if normalized == normalize_lookup("Font of Magic"):
        points = max(current_level, 2)
        return {
            "id": "sorcery-points",
            "label": "Sorcery Points",
            "category": "class_feature",
            "initial_current": points,
            "max": points,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Sorcery Points",
            "display_order": display_order,
            "activation_type": "passive",
        }
    if normalized == normalize_lookup("Combat Superiority"):
        dice = _resource_value_by_level(current_level, [(3, 4), (7, 5), (15, 6)]) or 4
        return {
            "id": "superiority-dice",
            "label": "Superiority Dice",
            "category": "class_feature",
            "initial_current": dice,
            "max": dice,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Combat Superiority",
            "display_order": display_order,
            "activation_type": "special",
        }
    if normalized == normalize_lookup("Indomitable"):
        uses = _resource_value_by_level(current_level, [(9, 1), (13, 2), (17, 3)]) or 1
        return {
            "id": "indomitable",
            "label": "Indomitable",
            "category": "class_feature",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Indomitable",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Chef"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "chef-treats",
            "label": "Chef Treats",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Chef treats",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if _feature_has_effect(effect_keys, "Poisoner"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "poisoner-doses",
            "label": "Poisoner Doses",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Poisoner doses",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if _feature_has_effect(effect_keys, "Gift of the Metallic Dragon"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "protective-wings",
            "label": "Protective Wings",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Protective Wings",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if _feature_has_effect(effect_keys, "Gift of the Gem Dragon"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "telekinetic-reprisal",
            "label": "Telekinetic Reprisal",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Telekinetic Reprisal",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if _feature_has_effect(effect_keys, "Lucky"):
        return {
            "id": "lucky",
            "label": "Lucky",
            "category": "feat",
            "initial_current": 3,
            "max": 3,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Lucky",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Martial Adept"):
        return {
            "id": "martial-adept",
            "label": "Martial Adept",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Superiority Die (d6)",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Metamagic Adept"):
        return {
            "id": "metamagic-adept",
            "label": "Metamagic Adept Sorcery Points",
            "category": "feat",
            "initial_current": 2,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Metamagic Adept Sorcery Points",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Adept of the Red Robes"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "magical-balance",
            "label": "Magical Balance",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Magical Balance",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Agent of Order"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "stasis-strike",
            "label": "Stasis Strike",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Stasis Strike",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Baleful Scion"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "grasp-of-avarice",
            "label": "Grasp of Avarice",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Grasp of Avarice",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Ember of the Fire Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "searing-ignition",
            "label": "Searing Ignition",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Searing Ignition",
            "display_order": display_order,
            "activation_type": "action",
        }
    if _feature_has_effect(effect_keys, "Fury of the Frost Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "frigid-retaliation",
            "label": "Frigid Retaliation",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Frigid Retaliation",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if _feature_has_effect(effect_keys, "Guile of the Cloud Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "cloudy-escape",
            "label": "Cloudy Escape",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Cloudy Escape",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if _feature_has_effect(effect_keys, "Keenness of the Stone Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "stone-throw",
            "label": "Stone Throw",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Stone Throw",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if _feature_has_effect(effect_keys, "Knight of the Crown"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "commanding-rally",
            "label": "Commanding Rally",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Commanding Rally",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if _feature_has_effect(effect_keys, "Knight of the Rose"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "bolstering-rally",
            "label": "Bolstering Rally",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Bolstering Rally",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if _feature_has_effect(effect_keys, "Knight of the Sword"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "demoralizing-strike",
            "label": "Demoralizing Strike",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Demoralizing Strike",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Righteous Heritor"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "soothe-pain",
            "label": "Soothe Pain",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Soothe Pain",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if _feature_has_effect(effect_keys, "Soul of the Storm Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "maelstrom-aura",
            "label": "Maelstrom Aura",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Maelstrom Aura",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if _feature_has_effect(effect_keys, "Squire of Solamnia"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "precise-strike",
            "label": "Precise Strike",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Precise Strike",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Strike of the Giants"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "strike-of-the-giants",
            "label": "Strike of the Giants",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Strike of the Giants",
            "display_order": display_order,
            "activation_type": "special",
        }
    if _feature_has_effect(effect_keys, "Boon of Recovery"):
        return {
            "id": "recover-vitality-dice",
            "label": "Recover Vitality Dice",
            "category": "feat",
            "initial_current": 10,
            "max": 10,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Recover Vitality d10s",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    return None


def _summarize_preview_resource(template: dict[str, Any]) -> str:
    label = str(template.get("label") or "").strip()
    if not label:
        return ""
    max_value = template.get("max")
    current_value = template.get("initial_current", max_value if max_value is not None else 0)
    summary = f"{label}: {int(current_value or 0)}"
    if max_value is not None:
        summary = f"{label}: {int(current_value or 0)} / {int(max_value or 0)}"
    reset_on = str(template.get("reset_on") or "").strip()
    if reset_on == "short_rest":
        return f"{summary} (Short Rest)"
    if reset_on == "long_rest":
        return f"{summary} (Long Rest)"
    return summary


def _class_save_proficiencies(selected_class: SystemsEntryRecord | None) -> list[str]:
    if selected_class is None:
        return []
    return [
        ability_key
        for ability_key in list(selected_class.metadata.get("proficiency") or [])
        if ability_key in ABILITY_KEYS
    ]


def _extract_size_label(entry: SystemsEntryRecord | None) -> str:
    if entry is None:
        return ""
    size_values = list(dict(entry.metadata or {}).get("size") or [])
    if not size_values:
        return ""
    return SIZE_LABELS.get(str(size_values[0] or "").strip().upper(), str(size_values[0] or "").strip())


def _extract_speed_label(entry: SystemsEntryRecord | None) -> str:
    if entry is None:
        return ""
    raw_speed = dict(entry.metadata or {}).get("speed")
    if isinstance(raw_speed, (int, float)):
        return f"{int(raw_speed)} ft."
    return str(raw_speed or "").strip()


def _ability_modifier(score: int) -> int:
    return (int(score) - 10) // 2


def _humanize_saving_throw(ability_key: str) -> str:
    return f"{ABILITY_LABELS.get(ability_key, ability_key.title())} Save"


def _choice_option(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


def _all_skill_options() -> list[tuple[str, str]]:
    return [(token, label) for token, label in SKILL_LABELS.items()]


def _skill_label(value: str) -> str:
    return SKILL_LABELS.get(normalize_lookup(value), _humanize_words(value))


def _humanize_proficiency_value(value: str, *, category: str) -> str:
    cleaned = _clean_embedded_text(value)
    normalized = normalize_lookup(cleaned)
    if category == "armor":
        return {
            "light": "Light Armor",
            "medium": "Medium Armor",
            "heavy": "Heavy Armor",
            "shield": "Shields",
        }.get(normalized, _humanize_words(cleaned))
    if category == "weapons":
        return {
            "simple": "Simple Weapons",
            "martial": "Martial Weapons",
            "firearms": "Firearms",
            "improvised": "Improvised Weapons",
        }.get(normalized, _humanize_words(cleaned))
    return _humanize_words(cleaned)


def _humanize_words(value: str) -> str:
    cleaned = str(value or "").replace("_", " ").strip()
    if not cleaned:
        return ""
    return " ".join(part.capitalize() for part in cleaned.split())


def _clean_embedded_text(value: str) -> str:
    rendered = str(value or "").strip()
    while True:
        updated = INLINE_TAG_PATTERN.sub(_replace_inline_tag, rendered)
        if updated == rendered:
            break
        rendered = updated
    return re.sub(r"\s+", " ", rendered).strip(" ,;")


def _replace_inline_tag(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    parts = [part.strip() for part in body.split("|")]
    if len(parts) >= 3 and parts[2]:
        return parts[2]
    if parts:
        return parts[0]
    return body


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        normalized = normalize_lookup(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped
