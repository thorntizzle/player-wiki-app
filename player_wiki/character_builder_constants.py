from __future__ import annotations

import re

from .repository import normalize_lookup

CHARACTER_BUILDER_VERSION = "2026-04-20.01"
BUILDER_STATIC_CACHE_MAX_ENTRIES = 12
BUILDER_PROGRESS_CACHE_MAX_ENTRIES = 64
BUILDER_STATIC_ENTRY_TYPES = (
    "background",
    "class",
    "feat",
    "item",
    "optionalfeature",
    "race",
    "spell",
    "subclass",
)
BUILDER_PROGRESS_ENTRY_TYPES = (
    "class",
    "classfeature",
    "optionalfeature",
    "subclass",
    "subclassfeature",
)
DEFAULT_EXPERIENCE_MODEL = "Milestone"
DEFAULT_ABILITY_SCORE = 10
NATIVE_LEVEL_UP_READY = "ready"
NATIVE_LEVEL_UP_REPAIRABLE = "repairable"
NATIVE_LEVEL_UP_UNSUPPORTED = "unsupported"
NATIVE_CLASS_SUPPORT_SUPPORTED = "supported"
NATIVE_CLASS_SUPPORT_BLOCKED = "blocked"
PROFILE_ENTRY_MATCH_PAGE_REF = "page_ref"
PROFILE_ENTRY_MATCH_SYSTEMS_SLUG = "systems_slug"
PROFILE_ENTRY_MATCH_SYSTEMS_SOURCE_TITLE = "systems_source_title"
PROFILE_ENTRY_MATCH_FALLBACK_TITLE = "fallback_title"
PROFILE_ENTRY_MATCH_AMBIGUOUS_SYSTEMS_SOURCE_TITLE = "ambiguous_systems_source_title"
PROFILE_ENTRY_MATCH_AMBIGUOUS_FALLBACK_TITLE = "ambiguous_fallback_title"
PROFILE_ENTRY_MATCH_UNRESOLVED_SOURCE_LOCKED = "unresolved_source_locked"
PROFILE_ENTRY_MATCH_UNRESOLVED = "unresolved"
NATIVE_SOURCE_MATRIX_SUBCLASS_ENTRY_TYPES = frozenset({"subclass", "subclassfeature"})
IMPORTED_CHARACTER_SOURCE_TYPES = frozenset({"markdown_character_sheet", "pdf_character_sheet_annotations"})
NATIVE_PROGRESSION_FEATURE_SOURCE_KIND = "native_progression"
CAMPAIGN_FEATURE_CHOICE_SLOTS = 2
CAMPAIGN_ITEM_CHOICE_SLOTS = 3
CAMPAIGN_MECHANICS_SECTION = "Mechanics"
CAMPAIGN_ITEMS_SECTION = "Items"
CAMPAIGN_SESSIONS_SECTION = "Sessions"
CAMPAIGN_PAGE_OPTION_PREFIX = "page:"
SYSTEMS_OPTION_PREFIX = "systems:"
CAMPAIGN_PAGE_SOURCE_ID = "Campaign"
ADVANCEMENT_REGION_ID = "advancement"
CHOICE_SECTIONS_REGION_ID = "choice-sections"
ATTACK_NAME_SUFFIX_PATTERN = re.compile(r"\s*\(([^)]*)\)\s*$")
ATTACK_MODE_WEAPON_THROWN = "weapon:thrown"
ATTACK_MODE_WEAPON_TWO_HANDED = "weapon:two-handed"
ATTACK_MODE_WEAPON_OFF_HAND = "weapon:off-hand"
WEAPON_WIELD_MODE_MAIN_HAND = "main-hand"
WEAPON_WIELD_MODE_OFF_HAND = "off-hand"
WEAPON_WIELD_MODE_TWO_HANDED = "two-handed"
WEAPON_WIELD_MODE_LABELS = {
    WEAPON_WIELD_MODE_MAIN_HAND: "Main Hand",
    WEAPON_WIELD_MODE_OFF_HAND: "Off Hand",
    WEAPON_WIELD_MODE_TWO_HANDED: "Two-Handed",
}
ATTACK_MODE_FEAT_CHARGER_PHB = "feat:phb-feat-charger"
ATTACK_MODE_FEAT_CHARGER_XPHB = "feat:xphb-feat-charger"
ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS = "feat:phb-feat-crossbow-expert:bonus"
ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER = "feat:phb-feat-great-weapon-master"
ATTACK_MODE_FEAT_GRAPPLER_PIN = "feat:phb-feat-grappler:pin"
ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS = "feat:phb-feat-polearm-master:bonus"
ATTACK_MODE_FEAT_SHARPSHOOTER = "feat:phb-feat-sharpshooter"
ATTACK_MODE_FEAT_SHIELD_MASTER_SHOVE = "feat:phb-feat-shield-master:shove"
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
    ATTACK_MODE_FEAT_GRAPPLER_PIN: "grappler",
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
    PREVIEW_ATTACKS_REGION_ID,
    PREVIEW_SCOPE_REGION_ID,
    PREVIEW_SPELL_SLOTS_REGION_ID,
)
LEVEL_UP_LIVE_REGION_IDS = (ADVANCEMENT_REGION_ID, CHOICE_SECTIONS_REGION_ID, *LEVEL_UP_PREVIEW_REGION_IDS)
BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS = 120
BUILDER_MODE_PREVIEW_DEBOUNCE_MS = 100
BUILDER_TEXT_PREVIEW_DEBOUNCE_MS = 650
CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND = {
    "species": {"species"},
    "background": {"background", "backgrounds"},
    "feat": {"feat", "feats"},
}
LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND = {
    "campaign_page_feature": frozenset({"feature", "feat"}),
    "campaign_page_item": frozenset({"item"}),
}
LINKED_CAMPAIGN_PAGE_REQUIRED_SECTION_BY_FIELD_KIND = {
    "campaign_page_feature": CAMPAIGN_MECHANICS_SECTION,
    "campaign_page_item": CAMPAIGN_ITEMS_SECTION,
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
LEVEL_UP_BUILDER_STATIC_KEYS = frozenset(
    {
        "hp_gain",
        "subclass_slug",
        "advancement_mode",
        "target_class_row_id",
        "new_class_slug",
        "new_subclass_slug",
    }
)
ABILITY_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}
SPELL_ACCESS_TYPE_AT_WILL = "at_will"
SPELL_ACCESS_TYPE_FREE_CAST = "free_cast"
SPELL_ACCESS_RESET_SHORT_REST = "short_rest"
SPELL_ACCESS_RESET_LONG_REST = "long_rest"
SPELL_ACCESS_RESET_SHORT_OR_LONG_REST = "short_or_long_rest"
SPELL_ACCESS_RESET_LABELS = {
    SPELL_ACCESS_RESET_SHORT_REST: "Short Rest",
    SPELL_ACCESS_RESET_LONG_REST: "Long Rest",
    SPELL_ACCESS_RESET_SHORT_OR_LONG_REST: "Short or Long Rest",
}
SUPPORTED_FREE_CAST_FEAT_SPELLS = {
    ("tce", "tcefeatartificerinitiate"): {
        "source_title": "Artificer Initiate",
        "ability_key": "int",
        "choice_fields": [
            {
                "category": "spell_known",
                "filter": "level=0|class=Artificer",
                "count": 1,
                "label_prefix": "Granted Cantrip",
                "help_text": "Choose an artificer cantrip granted by Artificer Initiate.",
                "prefer_known_mark": False,
            },
            {
                "category": "spell_known",
                "filter": "level=1|class=Artificer",
                "count": 1,
                "label_prefix": "Granted Spell",
                "help_text": "Choose a 1st-level artificer spell granted by Artificer Initiate.",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_FREE_CAST,
                "access_uses": 1,
                "access_reset_on": SPELL_ACCESS_RESET_LONG_REST,
            },
        ],
        "automatic_grants": [],
    },
    ("xge", "xgefeatdrowhighmagic"): {
        "source_title": "Drow High Magic",
        "ability_key": "cha",
        "choice_fields": [],
        "automatic_grants": [
            {
                "spell": "Detect Magic",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_AT_WILL,
            },
            {
                "spell": "Levitate",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_FREE_CAST,
                "access_uses": 1,
                "access_reset_on": SPELL_ACCESS_RESET_LONG_REST,
            },
            {
                "spell": "Dispel Magic",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_FREE_CAST,
                "access_uses": 1,
                "access_reset_on": SPELL_ACCESS_RESET_LONG_REST,
            },
        ],
    },
    ("xge", "xgefeatfeyteleportation"): {
        "source_title": "Fey Teleportation",
        "ability_key": "int",
        "choice_fields": [],
        "automatic_grants": [
            {
                "spell": "Misty Step",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_FREE_CAST,
                "access_uses": 1,
                "access_reset_on": SPELL_ACCESS_RESET_SHORT_OR_LONG_REST,
            }
        ],
    },
    ("xge", "xgefeatwoodelfmagic"): {
        "source_title": "Wood Elf Magic",
        "ability_key": "wis",
        "choice_fields": [
            {
                "category": "spell_known",
                "filter": "level=0|class=Druid",
                "count": 1,
                "label_prefix": "Granted Cantrip",
                "help_text": "Choose a druid cantrip granted by Wood Elf Magic.",
                "prefer_known_mark": False,
            }
        ],
        "automatic_grants": [
            {
                "spell": "Longstrider",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_FREE_CAST,
                "access_uses": 1,
                "access_reset_on": SPELL_ACCESS_RESET_LONG_REST,
            },
            {
                "spell": "Pass without Trace",
                "prefer_known_mark": False,
                "access_type": SPELL_ACCESS_TYPE_FREE_CAST,
                "access_uses": 1,
                "access_reset_on": SPELL_ACCESS_RESET_LONG_REST,
            },
        ],
    },
    ("phb", "phbfeatritualcaster"): {
        "source_title": "Ritual Caster",
        "source_field_label": "Ritual Caster Spell List",
        "source_field_help_text": "Choose the class spell list your ritual book uses.",
        "source_options": [
            {
                "value": "bard",
                "label": "Bard Spells",
                "class_name": "Bard",
                "source_title": "Ritual Caster (Bard)",
                "ability_key": "cha",
            },
            {
                "value": "cleric",
                "label": "Cleric Spells",
                "class_name": "Cleric",
                "source_title": "Ritual Caster (Cleric)",
                "ability_key": "wis",
            },
            {
                "value": "druid",
                "label": "Druid Spells",
                "class_name": "Druid",
                "source_title": "Ritual Caster (Druid)",
                "ability_key": "wis",
            },
            {
                "value": "sorcerer",
                "label": "Sorcerer Spells",
                "class_name": "Sorcerer",
                "source_title": "Ritual Caster (Sorcerer)",
                "ability_key": "cha",
            },
            {
                "value": "warlock",
                "label": "Warlock Spells",
                "class_name": "Warlock",
                "source_title": "Ritual Caster (Warlock)",
                "ability_key": "cha",
            },
            {
                "value": "wizard",
                "label": "Wizard Spells",
                "class_name": "Wizard",
                "source_title": "Ritual Caster (Wizard)",
                "ability_key": "int",
            },
        ],
        "choice_fields": [
            {
                "category": "spell_managed",
                "kind": "feat_spell_managed",
                "filter": "level=1|class={class_name}|miscellaneous=ritual",
                "count": 2,
                "label_prefix": "Ritual Spell",
                "help_text": "Choose a 1st-level ritual spell from the selected class list for your ritual book.",
                "spell_mark": "Ritual Book",
                "spell_is_ritual": True,
            }
        ],
        "automatic_grants": [],
        "manager_mode": "ritual_book",
        "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
    },
}
SKILL_LABELS = {
    "acrobatics": "Acrobatics",
    "animalhandling": "Animal Handling",
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
    "sleightofhand": "Sleight of Hand",
    "stealth": "Stealth",
    "survival": "Survival",
}
SKILL_ABILITY_KEYS = {
    "acrobatics": "dex",
    "animalhandling": "wis",
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
    "sleightofhand": "dex",
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
FEATURE_EXPERTISE_TOOL_VALUE_PREFIX = "tool:"
THIEVES_TOOLS_PROFICIENCY = "Thieves' Tools"
SIZE_LABELS = {
    "T": "Tiny",
    "S": "Small",
    "M": "Medium",
    "L": "Large",
    "H": "Huge",
    "G": "Gargantuan",
}
SIZE_CARRYING_CAPACITY_MULTIPLIERS = {
    "tiny": 0.5,
    "small": 1.0,
    "medium": 1.0,
    "large": 2.0,
    "huge": 4.0,
    "gargantuan": 8.0,
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
SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS = {"full", "1/2", "artificer", "1/3"}
MULTICLASS_SHARED_SLOT_REFERENCE_CLASS = "Wizard"
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
    "Native level-up currently advances one level at a time, including add-class multiclass starts and row-specific multiclass advancement.",
    "Hit point gain is entered manually so your table can choose rolled or fixed HP.",
    "Prepared-caster level-up currently preserves existing prepared spells and adds the new picks needed for the next level.",
    "Multiclass support in this slice covers shared-slot base casters, supported structured subclass-only spellcasting rows, Pact Magic base casters, and martial rows. Spell-bearing subclasses that still lack a structured supported spellcasting profile continue to need manual follow-up.",
    "Some advanced feat side effects and non-structured campaign spell access still need manual follow-up.",
]
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

__all__ = [
    'CHARACTER_BUILDER_VERSION',
    'BUILDER_STATIC_CACHE_MAX_ENTRIES',
    'BUILDER_PROGRESS_CACHE_MAX_ENTRIES',
    'BUILDER_STATIC_ENTRY_TYPES',
    'BUILDER_PROGRESS_ENTRY_TYPES',
    'DEFAULT_EXPERIENCE_MODEL',
    'DEFAULT_ABILITY_SCORE',
    'NATIVE_LEVEL_UP_READY',
    'NATIVE_LEVEL_UP_REPAIRABLE',
    'NATIVE_LEVEL_UP_UNSUPPORTED',
    'NATIVE_CLASS_SUPPORT_SUPPORTED',
    'NATIVE_CLASS_SUPPORT_BLOCKED',
    'PROFILE_ENTRY_MATCH_PAGE_REF',
    'PROFILE_ENTRY_MATCH_SYSTEMS_SLUG',
    'PROFILE_ENTRY_MATCH_SYSTEMS_SOURCE_TITLE',
    'PROFILE_ENTRY_MATCH_FALLBACK_TITLE',
    'PROFILE_ENTRY_MATCH_AMBIGUOUS_SYSTEMS_SOURCE_TITLE',
    'PROFILE_ENTRY_MATCH_AMBIGUOUS_FALLBACK_TITLE',
    'PROFILE_ENTRY_MATCH_UNRESOLVED_SOURCE_LOCKED',
    'PROFILE_ENTRY_MATCH_UNRESOLVED',
    'NATIVE_SOURCE_MATRIX_SUBCLASS_ENTRY_TYPES',
    'IMPORTED_CHARACTER_SOURCE_TYPES',
    'NATIVE_PROGRESSION_FEATURE_SOURCE_KIND',
    'CAMPAIGN_FEATURE_CHOICE_SLOTS',
    'CAMPAIGN_ITEM_CHOICE_SLOTS',
    'CAMPAIGN_MECHANICS_SECTION',
    'CAMPAIGN_ITEMS_SECTION',
    'CAMPAIGN_SESSIONS_SECTION',
    'CAMPAIGN_PAGE_OPTION_PREFIX',
    'SYSTEMS_OPTION_PREFIX',
    'CAMPAIGN_PAGE_SOURCE_ID',
    'ADVANCEMENT_REGION_ID',
    'CHOICE_SECTIONS_REGION_ID',
    'ATTACK_NAME_SUFFIX_PATTERN',
    'ATTACK_MODE_WEAPON_THROWN',
    'ATTACK_MODE_WEAPON_TWO_HANDED',
    'ATTACK_MODE_WEAPON_OFF_HAND',
    'WEAPON_WIELD_MODE_MAIN_HAND',
    'WEAPON_WIELD_MODE_OFF_HAND',
    'WEAPON_WIELD_MODE_TWO_HANDED',
    'WEAPON_WIELD_MODE_LABELS',
    'ATTACK_MODE_FEAT_CHARGER_PHB',
    'ATTACK_MODE_FEAT_CHARGER_XPHB',
    'ATTACK_MODE_FEAT_CROSSBOW_EXPERT_BONUS',
    'ATTACK_MODE_FEAT_GREAT_WEAPON_MASTER',
    'ATTACK_MODE_FEAT_GRAPPLER_PIN',
    'ATTACK_MODE_FEAT_POLEARM_MASTER_BONUS',
    'ATTACK_MODE_FEAT_SHARPSHOOTER',
    'ATTACK_MODE_FEAT_SHIELD_MASTER_SHOVE',
    'ATTACK_MODE_EFFECT_PREFIX',
    'ATTACK_MODE_TARGET_ALL',
    'ATTACK_MODE_TARGET_MELEE',
    'ATTACK_MODE_TARGET_RANGED',
    'ATTACK_MODE_TARGET_FIREARM',
    'ATTACK_MODE_EFFECT_TARGETS',
    'ATTACK_MODE_COMPONENT_LABELS',
    'ATTACK_MODE_COMPONENT_PRIORITY',
    'PREVIEW_SUMMARY_REGION_ID',
    'PREVIEW_FEATURES_REGION_ID',
    'PREVIEW_RESOURCES_REGION_ID',
    'PREVIEW_SPELLS_REGION_ID',
    'PREVIEW_SCOPE_REGION_ID',
    'PREVIEW_EQUIPMENT_REGION_ID',
    'PREVIEW_ATTACKS_REGION_ID',
    'PREVIEW_SPELL_SLOTS_REGION_ID',
    'LEVEL_ONE_PREVIEW_REGION_IDS',
    'LEVEL_ONE_LIVE_REGION_IDS',
    'LEVEL_UP_PREVIEW_REGION_IDS',
    'LEVEL_UP_LIVE_REGION_IDS',
    'BUILDER_CHOICE_PREVIEW_DEBOUNCE_MS',
    'BUILDER_MODE_PREVIEW_DEBOUNCE_MS',
    'BUILDER_TEXT_PREVIEW_DEBOUNCE_MS',
    'CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND',
    'LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND',
    'LINKED_CAMPAIGN_PAGE_REQUIRED_SECTION_BY_FIELD_KIND',
    'ABILITY_KEYS',
    'LEVEL_ONE_BUILDER_STATIC_KEYS',
    'LEVEL_UP_BUILDER_STATIC_KEYS',
    'ABILITY_LABELS',
    'SPELL_ACCESS_TYPE_AT_WILL',
    'SPELL_ACCESS_TYPE_FREE_CAST',
    'SPELL_ACCESS_RESET_SHORT_REST',
    'SPELL_ACCESS_RESET_LONG_REST',
    'SPELL_ACCESS_RESET_SHORT_OR_LONG_REST',
    'SPELL_ACCESS_RESET_LABELS',
    'SUPPORTED_FREE_CAST_FEAT_SPELLS',
    'SKILL_LABELS',
    'SKILL_ABILITY_KEYS',
    'SKILL_PROFICIENCY_LEVEL_RANKS',
    'STANDARD_LANGUAGE_OPTIONS',
    'COMMON_TOOL_PROFICIENCY_OPTIONS',
    'FEATURE_EXPERTISE_TOOL_VALUE_PREFIX',
    'THIEVES_TOOLS_PROFICIENCY',
    'SIZE_LABELS',
    'SIZE_CARRYING_CAPACITY_MULTIPLIERS',
    'REDUNDANT_SPECIES_TRAIT_NAMES',
    'ABILITY_SCORE_IMPROVEMENT_NAMES',
    'SPELLCASTING_ABILITY_BY_CLASS',
    'LEVEL_ONE_SPELL_SLOTS_BY_CLASS',
    'LEVEL_ONE_SPELL_RULES_BY_CLASS',
    'LEVEL_TWO_SPELL_SLOTS_BY_CLASS',
    'LEVEL_TWO_SPELL_RULES_BY_CLASS',
    'SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS',
    'MULTICLASS_SHARED_SLOT_REFERENCE_CLASS',
    'EXTRA_PHB_LEVEL_ONE_SPELL_LISTS',
    'NATIVE_LEVEL_UP_LIMITATIONS',
    'ITEM_TITLES_BY_EQUIPMENT_TYPE',
    'ITEM_TYPE_CODES_BY_EQUIPMENT_TYPE',
    'DAMAGE_TYPE_LABELS',
    'WEAPON_PROPERTY_LABELS',
    'INLINE_TAG_PATTERN'
]
