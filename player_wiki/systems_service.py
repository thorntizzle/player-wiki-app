from __future__ import annotations

from html import escape
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from flask import g, has_request_context
import markdown

from .auth_store import isoformat, utcnow
from .character_campaign_options import (
    build_campaign_page_character_option,
    normalize_campaign_base_rule_refs,
    normalize_campaign_overlay_support,
)
from .character_campaign_progression import build_campaign_page_progression_entries
from .campaign_visibility import (
    VISIBILITY_DM,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    is_valid_visibility,
    most_private_visibility,
    normalize_visibility_choice,
)
from .dnd5e_rules_reference import (
    DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY,
    DND5E_RULES_REFERENCE_SOURCE_ID,
    DND5E_RULES_REFERENCE_SOURCE_TITLE,
    DND5E_RULES_REFERENCE_VERSION,
    build_dnd5e_rules_reference_entries,
)
from .repository import normalize_lookup, slugify
from .repository_store import RepositoryStore
from .systems_models import (
    CampaignEntryOverrideRecord,
    CampaignSystemsPolicyRecord,
    SystemsEntryRecord,
    SystemsLibraryRecord,
    SystemsSourceRecord,
)
from .systems_store import SystemsStore

LICENSE_CLASS_LABELS = {
    "app_reference": "App-authored reference",
    "proprietary_private": "Proprietary - private campaign use",
    "srd_cc": "SRD - Creative Commons",
    "open_license": "Open license",
    "custom_campaign": "Custom campaign",
}

INLINE_TAG_PATTERN = re.compile(r"\{@([^{}]+)\}")

ATTACK_TAG_LABELS = {
    "mw": "Melee Weapon Attack:",
    "rw": "Ranged Weapon Attack:",
    "mw,rw": "Melee or Ranged Weapon Attack:",
    "ms": "Melee Spell Attack:",
    "rs": "Ranged Spell Attack:",
    "ms,rs": "Melee or Ranged Spell Attack:",
}

ARMOR_ITEM_TYPE_CODES = {"LA", "MA", "HA", "S"}
WEAPON_ITEM_TYPE_CODES = {"M", "R"}
PASSIVE_CHECK_SKILL_KEYS = {"insight", "investigation", "perception"}
RULES_REFERENCE_ENTRY_TYPES = ("book", "rule")
RULES_REFERENCE_SEARCH_SCOPE_GLOBAL = "global"
RULES_REFERENCE_SEARCH_SCOPE_SOURCE_ONLY = "source_only"
MECHANICS_IMPACT_CHARACTER_ENTRY_TYPES = frozenset(
    {
        "background",
        "class",
        "classfeature",
        "feat",
        "item",
        "optionalfeature",
        "race",
        "spell",
        "subclass",
        "subclassfeature",
    }
)
MECHANICS_IMPACT_COMBAT_ENTRY_TYPES = frozenset({"monster"})
MECHANICS_IMPACT_ENTRY_TYPE_LABELS = {
    "background": "Background",
    "class": "Class",
    "classfeature": "Class Feature",
    "feat": "Feat",
    "item": "Item",
    "monster": "Monster",
    "optionalfeature": "Optional Feature",
    "race": "Race",
    "spell": "Spell",
    "subclass": "Subclass",
    "subclassfeature": "Subclass Feature",
}
MECHANICS_IMPACT_RULE_METADATA_KEYS = {
    "formula": "formula",
    "formulas": "formulas",
    "rulefacets": "rule_facets",
    "rulekey": "rule_key",
    "sourceprovenance": "source_provenance",
}
MECHANICS_IMPACT_CHARACTER_METADATA_KEYS = {
    "baserulerefs": "base_rule_refs",
    "characteroption": "character_option",
    "characterprogression": "character_progression",
    "derivedstat": "derived_stat",
    "derivedstats": "derived_stats",
    "managedresource": "managed_resource",
    "managedresources": "managed_resources",
    "modeledeffects": "modeled_effects",
    "spellmanager": "spell_manager",
    "spellsupport": "spell_support",
}
MECHANICS_IMPACT_COMBAT_METADATA_KEYS = {
    "abilities": "abilities",
    "actions": "actions",
    "bonusactions": "bonus_actions",
    "hp": "hp",
    "initiative": "initiative",
    "legendaryactions": "legendary_actions",
    "reactions": "reactions",
    "speed": "speed",
    "traits": "traits",
}
PHB_BOOK_SECTION_RULE_KEY_MAP = {
    # Only link section anchors whose rule identity already exists as a stable RULES entry.
    "2-choose-a-class--hit-points-and-hit-dice": ("hit-points-and-hit-dice",),
    "2-choose-a-class--proficiency-bonus": ("proficiency-bonus",),
    "5-choose-equipment--armor-class": ("armor-class",),
    "ability-scores-and-modifiers": ("ability-scores-and-ability-modifiers",),
    "proficiency-bonus": ("proficiency-bonus",),
    "ability-checks--skills": ("skill-bonuses-and-proficiency",),
    "ability-checks--passive-checks": ("passive-checks",),
    "saving-throws": ("saving-throw-bonuses",),
    "movement--resting": ("hit-points-and-hit-dice",),
    "the-order-of-combat--initiative": ("initiative",),
    "making-an-attack": ("attack-rolls-and-attack-bonus",),
    "making-an-attack--attack-rolls": ("attack-rolls-and-attack-bonus",),
    "damage-and-healing--hit-points": ("hit-points-and-hit-dice",),
    "damage-and-healing--damage-rolls": ("damage-rolls",),
    "damage-and-healing--dropping-to-0-hit-points": ("hit-points-and-hit-dice",),
    "damage-and-healing--temporary-hit-points": ("hit-points-and-hit-dice",),
    "casting-a-spell--saving-throws": ("spell-attacks-and-save-dcs",),
    "casting-a-spell--attack-rolls": ("spell-attacks-and-save-dcs",),
}
BOOK_SECTION_ENTITY_TAG_ENTRY_TYPES = {
    "action": "action",
    "background": "background",
    "class": "class",
    "classfeature": "classfeature",
    "condition": "condition",
    "creature": "monster",
    "disease": "disease",
    "feat": "feat",
    "status": "status",
    "skill": "skill",
    "sense": "sense",
    "spell": "spell",
    "item": "item",
    "monster": "monster",
    "optfeature": "optionalfeature",
    "optionalfeature": "optionalfeature",
    "race": "race",
    "subclass": "subclass",
    "subclassfeature": "subclassfeature",
    "variantrule": "variantrule",
}
BOOK_SECTION_ENTITY_TYPE_ORDER = (
    "condition",
    "disease",
    "status",
    "action",
    "skill",
    "sense",
    "spell",
    "variantrule",
    "feat",
    "item",
    "background",
    "race",
    "class",
    "classfeature",
    "subclass",
    "subclassfeature",
    "monster",
    "optionalfeature",
)
BOOK_SECTION_ENTITY_GROUP_LABELS = {
    "condition": "Conditions",
    "disease": "Diseases",
    "status": "Statuses",
    "action": "Actions",
    "skill": "Skills",
    "sense": "Senses",
    "spell": "Spells",
    "variantrule": "Variant Rules",
    "feat": "Feats",
    "item": "Equipment",
    "background": "Backgrounds",
    "race": "Races",
    "class": "Classes",
    "classfeature": "Class Features",
    "subclass": "Subclasses",
    "subclassfeature": "Subclass Features",
    "monster": "Monsters",
    "optionalfeature": "Optional Features",
}
BOOK_SECTION_ENTITY_SOURCE_FALLBACKS = {
    "MM": {
        "action": ("PHB",),
        "condition": ("PHB",),
        "sense": ("PHB",),
        "skill": ("PHB",),
        "status": ("PHB",),
    },
}


def _normalized_nonempty_tuple(*values: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized_value = normalize_lookup(value)
        if normalized_value:
            normalized_values.append(normalized_value)
    return tuple(normalized_values)


VGM_MONSTER_LORE_WRAPPER_MONSTER_MATCHERS = {
    normalize_lookup("Beholders: Bad Dreams Come True"): {
        "group_keys": _normalized_nonempty_tuple("Beholders"),
        "type_keys": (),
        "tag_keys": (),
        "title_keys": _normalized_nonempty_tuple(
            "Beholder",
            "Death Tyrant",
            "Death Kiss",
            "Gauth",
            "Gazer",
            "Spectator",
        ),
        "title_prefix_keys": (),
        "title_suffix_keys": (),
    },
    normalize_lookup("Giants: World Shakers"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple(
            "cloud giant",
            "fire giant",
            "frost giant",
            "hill giant",
            "stone giant",
            "storm giant",
        ),
        "title_keys": _normalized_nonempty_tuple(
            "Cloud Giant",
            "Fire Giant",
            "Frost Giant",
            "Hill Giant",
            "Stone Giant",
            "Storm Giant",
            "Mouth of Grolantor",
        ),
        "title_prefix_keys": _normalized_nonempty_tuple(
            "Cloud Giant",
            "Fire Giant",
            "Frost Giant",
            "Hill Giant",
            "Stone Giant",
            "Storm Giant",
        ),
        "title_suffix_keys": (),
    },
    normalize_lookup("Gnolls: The Insatiable Hunger"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("gnoll"),
        "title_keys": _normalized_nonempty_tuple("Flind"),
        "title_prefix_keys": _normalized_nonempty_tuple("Gnoll"),
        "title_suffix_keys": (),
    },
    normalize_lookup("Goblinoids: The Conquering Host"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("goblinoid"),
        "title_keys": (),
        "title_prefix_keys": (),
        "title_suffix_keys": (),
    },
    normalize_lookup("Hags: Dark Sisterhood"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": (),
        "title_keys": (),
        "title_prefix_keys": (),
        "title_suffix_keys": _normalized_nonempty_tuple("Hag"),
    },
    normalize_lookup("Kobolds: Little Dragons"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("kobold"),
        "title_keys": (),
        "title_prefix_keys": _normalized_nonempty_tuple("Kobold"),
        "title_suffix_keys": (),
    },
    normalize_lookup("Mind Flayers: Scourge of Worlds"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": (),
        "title_keys": _normalized_nonempty_tuple(
            "Alhoon",
            "Elder Brain",
            "Intellect Devourer",
            "Mind Flayer",
            "Mindwitness",
            "Neothelid",
            "Ulitharid",
        ),
        "title_prefix_keys": _normalized_nonempty_tuple("Mind Flayer"),
        "title_suffix_keys": (),
    },
    normalize_lookup("Orcs: The Godsworn"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("orc"),
        "title_keys": _normalized_nonempty_tuple("Orc"),
        "title_prefix_keys": (),
        "title_suffix_keys": (),
    },
    normalize_lookup("Yuan-ti: Snake People"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("yuan-ti"),
        "title_keys": (),
        "title_prefix_keys": _normalized_nonempty_tuple("Yuan-ti"),
        "title_suffix_keys": (),
    },
}
VGM_CHARACTER_RACE_WRAPPER_RACE_MATCHERS = {
    normalize_lookup("Aasimar"): {
        "title_keys": _normalized_nonempty_tuple("Aasimar"),
        "base_race_keys": _normalized_nonempty_tuple("Aasimar"),
    },
    normalize_lookup("Firbolg"): {
        "title_keys": _normalized_nonempty_tuple("Firbolg"),
        "base_race_keys": (),
    },
    normalize_lookup("Goliath"): {
        "title_keys": _normalized_nonempty_tuple("Goliath"),
        "base_race_keys": (),
    },
    normalize_lookup("Kenku"): {
        "title_keys": _normalized_nonempty_tuple("Kenku"),
        "base_race_keys": (),
    },
    normalize_lookup("Lizardfolk"): {
        "title_keys": _normalized_nonempty_tuple("Lizardfolk"),
        "base_race_keys": (),
    },
    normalize_lookup("Tabaxi"): {
        "title_keys": _normalized_nonempty_tuple("Tabaxi"),
        "base_race_keys": (),
    },
    normalize_lookup("Triton"): {
        "title_keys": _normalized_nonempty_tuple("Triton"),
        "base_race_keys": (),
    },
    normalize_lookup("Monstrous Adventurers"): {
        "title_keys": _normalized_nonempty_tuple(
            "Bugbear",
            "Goblin",
            "Hobgoblin",
            "Kobold",
            "Orc",
            "Yuan-ti Pureblood",
        ),
        "base_race_keys": (),
    },
    normalize_lookup("Height and Weight"): {
        "title_keys": _normalized_nonempty_tuple(
            "Aasimar",
            "Firbolg",
            "Triton",
            "Bugbear",
            "Yuan-ti Pureblood",
        ),
        "base_race_keys": (),
    },
}
MTF_ANCESTRY_WRAPPER_RACE_MATCHERS = {
    normalize_lookup("Tiefling Subraces"): {
        "title_keys": (),
        "base_race_keys": _normalized_nonempty_tuple("Tiefling"),
    },
    normalize_lookup("Elf Subraces"): {
        "title_keys": (),
        "base_race_keys": _normalized_nonempty_tuple("Elf"),
    },
    normalize_lookup("Duergar Characters"): {
        "title_keys": _normalized_nonempty_tuple("Dwarf (Duergar)"),
        "base_race_keys": _normalized_nonempty_tuple("Dwarf"),
    },
    normalize_lookup("Gith Characters"): {
        "title_keys": _normalized_nonempty_tuple("Gith"),
        "base_race_keys": _normalized_nonempty_tuple("Gith"),
    },
    normalize_lookup("Deep Gnome Characters"): {
        "title_keys": _normalized_nonempty_tuple("Gnome (Deep)"),
        "base_race_keys": _normalized_nonempty_tuple("Gnome"),
    },
}
MTF_BOOK_WRAPPER_MONSTER_TITLE_KEYS = {
    normalize_lookup("Diabolical Cults"): _normalized_nonempty_tuple("Geryon", "Zariel"),
    normalize_lookup("Demonic Boons"): _normalized_nonempty_tuple(
        "Baphomet",
        "Demogorgon",
        "Fraz-Urb'luu",
        "Graz'zt",
        "Juiblex",
        "Orcus",
        "Yeenoghu",
        "Zuggtmoy",
    ),
    normalize_lookup("Elf Subraces"): _normalized_nonempty_tuple(
        "Autumn Eladrin",
        "Spring Eladrin",
        "Summer Eladrin",
        "Winter Eladrin",
    ),
    normalize_lookup("Duergar Characters"): _normalized_nonempty_tuple(
        "Duergar Despot",
        "Duergar Hammerer",
        "Duergar Kavalrachni",
        "Duergar Mind Master",
        "Duergar Screamer",
        "Duergar Soulblade",
        "Duergar Stone Guard",
        "Duergar Warlord",
        "Duergar Xarrorn",
    ),
    normalize_lookup("Gith Characters"): _normalized_nonempty_tuple(
        "Githyanki Gish",
        "Githyanki Kith'rak",
        "Githyanki Supreme Commander",
        "Githzerai Anarch",
        "Githzerai Enlightened",
    ),
}
MTF_BOOK_WRAPPER_FEAT_TITLE_KEYS = {
    normalize_lookup("Deep Gnome Characters"): _normalized_nonempty_tuple("Svirfneblin Magic"),
}
MTF_BOOK_WRAPPER_ITEM_TITLE_KEYS = {
    normalize_lookup("Elf Subraces"): _normalized_nonempty_tuple("Elven Trinket"),
    normalize_lookup("Gith Characters"): _normalized_nonempty_tuple("Greater Silver Sword", "Silver Sword"),
}
EGW_RACE_WRAPPER_RACE_MATCHERS = {
    normalize_lookup("Elves"): {
        "title_keys": (),
        "base_race_keys": _normalized_nonempty_tuple("Elf"),
    },
    normalize_lookup("Halflings"): {
        "title_keys": (),
        "base_race_keys": _normalized_nonempty_tuple("Halfling"),
    },
    normalize_lookup("Dragonborn"): {
        "title_keys": (),
        "base_race_keys": _normalized_nonempty_tuple("Dragonborn"),
    },
    normalize_lookup("Orcs and Half-Orcs"): {
        "title_keys": _normalized_nonempty_tuple("Orc"),
        "base_race_keys": (),
    },
}

SCAG_RACE_WRAPPER_TITLE_BY_KEY = {
    normalize_lookup("Dwarf"): "Dwarves",
    normalize_lookup("Dragonborn"): "Dragonborn",
    normalize_lookup("Elf"): "Elves",
    normalize_lookup("Gnome"): "Gnomes",
    normalize_lookup("Halfling"): "Halflings",
    normalize_lookup("Half-Elf"): "Half-Elves",
    normalize_lookup("Half-Orc"): "Half-Orcs",
    normalize_lookup("Human"): "Humans",
    normalize_lookup("Tiefling"): "Tieflings",
}
SCAG_RACE_WRAPPER_MATCH_ORDER = (
    normalize_lookup("Half-Elf"),
    normalize_lookup("Half-Orc"),
    normalize_lookup("Dragonborn"),
    normalize_lookup("Halfling"),
    normalize_lookup("Tiefling"),
    normalize_lookup("Dwarf"),
    normalize_lookup("Gnome"),
    normalize_lookup("Human"),
    normalize_lookup("Elf"),
)
SCAG_SUBCLASS_WRAPPER_TITLE_BY_CLASS_KEY = {
    normalize_lookup("Barbarian"): "Primal Paths",
    normalize_lookup("Bard"): "Bardic Colleges",
    normalize_lookup("Cleric"): "Divine Domain",
    normalize_lookup("Druid"): "Druid Circles",
    normalize_lookup("Fighter"): "Martial Archetype",
    normalize_lookup("Monk"): "Monastic Traditions",
    normalize_lookup("Paladin"): "Sacred Oath",
    normalize_lookup("Rogue"): "Roguish Archetypes",
    normalize_lookup("Sorcerer"): "Sorcerous Origin",
    normalize_lookup("Warlock"): "Otherworldly Patron",
    normalize_lookup("Wizard"): "Arcane Tradition",
}
SCAG_ITEM_WRAPPER_TITLE_BY_PAGE = {
    "121": "Primal Paths",
    "124": "Musical Instruments",
}
EGW_RACE_WRAPPER_TITLE_BY_KEY = {
    normalize_lookup("Dragonborn"): "Dragonborn",
    normalize_lookup("Elf"): "Elves",
    normalize_lookup("Halfling"): "Halflings",
    normalize_lookup("Orc"): "Orcs and Half-Orcs",
}
EGW_SUBCLASS_WRAPPER_TITLE_BY_CLASS_KEY = {
    normalize_lookup("Fighter"): "Fighter",
    normalize_lookup("Wizard"): "Wizard",
}
EGW_SPELL_WRAPPER_TITLES = (
    "Dunamancy Spells",
    "Spell Descriptions",
)
EGW_VESTIGE_ITEM_TITLE_KEYS = {
    normalize_lookup("Danoth's Visor"),
    normalize_lookup("Grimoire Infinitus"),
    normalize_lookup("Hide of the Feral Guardian"),
    normalize_lookup("Infiltrator's Key"),
    normalize_lookup("Stormgirdle"),
    normalize_lookup("Verminshroud"),
    normalize_lookup("Wreath of the Prism"),
}
EGW_BETRAYER_ITEM_TITLE_KEYS = {
    normalize_lookup("Blade of Broken Mirrors"),
    normalize_lookup("Grovelthrash"),
    normalize_lookup("Lash of Shadows"),
    normalize_lookup("Mace of the Black Crown"),
    normalize_lookup("Ruin's Wake"),
    normalize_lookup("Silken Spite"),
    normalize_lookup("The Bloody End"),
    normalize_lookup("Will of the Talon"),
}


def _systems_service_request_cache() -> dict[tuple[object, ...], object] | None:
    if not has_request_context():
        return None
    cache = getattr(g, "_systems_service_request_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    g._systems_service_request_cache = cache
    return cache


def _systems_service_cache_get(cache_key: tuple[object, ...], build_value):
    cache = _systems_service_request_cache()
    if cache is None:
        return build_value()
    if cache_key not in cache:
        cache[cache_key] = build_value()
    return cache[cache_key]


def _systems_service_cache_clear() -> None:
    if not has_request_context():
        return
    cache = getattr(g, "_systems_service_request_cache", None)
    if isinstance(cache, dict):
        cache.clear()


ABILITY_NAME_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}

DND_5E_SOURCE_CATALOG = (
    {
        "source_id": DND5E_RULES_REFERENCE_SOURCE_ID,
        "title": DND5E_RULES_REFERENCE_SOURCE_TITLE,
        "license_class": "open_license",
        "public_visibility_allowed": True,
        "requires_unofficial_notice": False,
        "default_visibility": VISIBILITY_PLAYERS,
        "enabled_by_default": True,
    },
    {
        "source_id": "PHB",
        "title": "Player's Handbook (2014)",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "DMG",
        "title": "Dungeon Master's Guide (2014)",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
        "book_entry_default_visibility": VISIBILITY_DM,
        "book_entry_policy_note": (
            "DMG chapter-backed rules pages default to DM visibility even if a campaign lowers "
            "the broader DMG source to surface specific player-facing DMG rows. Use entry "
            "overrides only when a chapter page should be intentionally exposed more broadly."
        ),
        "rules_reference_search_scope": RULES_REFERENCE_SEARCH_SCOPE_SOURCE_ONLY,
    },
    {
        "source_id": "MM",
        "title": "Monster Manual (2014)",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
    },
    {
        "source_id": "VGM",
        "title": "Volo's Guide to Monsters",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
        "book_entry_default_visibility": VISIBILITY_DM,
        "book_entry_policy_note": (
            "VGM wrapper pages default to DM visibility even if a campaign lowers the broader "
            "VGM source to surface specific player-facing VGM rows. Use entry overrides only "
            "when a wrapper page should be intentionally exposed more broadly."
        ),
    },
    {
        "source_id": "SCAG",
        "title": "Sword Coast Adventurer's Guide",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "XGE",
        "title": "Xanathar's Guide to Everything",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "TCE",
        "title": "Tasha's Cauldron of Everything",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "MTF",
        "title": "Mordenkainen's Tome of Foes",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
        "book_entry_default_visibility": VISIBILITY_DM,
        "book_entry_policy_note": (
            "MTF wrapper pages default to DM visibility even if a campaign lowers the broader "
            "MTF source to surface specific player-facing MTF rows. Use entry overrides only "
            "when a wrapper page should be intentionally exposed more broadly."
        ),
    },
    {
        "source_id": "EGW",
        "title": "Explorer's Guide to Wildemount",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
)

BUILTIN_LIBRARY_CATALOG = {
    "DND-5E": {
        "title": "DND 5E",
        "system_code": "DND-5E",
        "sources": DND_5E_SOURCE_CATALOG,
    }
}


class SystemsPolicyValidationError(ValueError):
    pass


@dataclass(slots=True)
class CampaignSourceState:
    source: SystemsSourceRecord
    is_enabled: bool
    default_visibility: str
    is_configured: bool


@dataclass(slots=True)
class SystemsMonsterCombatSeed:
    entry_key: str
    title: str
    source_id: str
    max_hp: int
    movement_total: int
    speed_label: str
    initiative_bonus: int


@dataclass(slots=True)
class SystemsMechanicsImpactSignal:
    label: str
    detail: str
    surface: str


@dataclass(slots=True)
class SystemsMechanicsImpactWarning:
    summary: str
    surfaces: tuple[str, ...]
    signals: tuple[SystemsMechanicsImpactSignal, ...]


def _find_structured_key_paths(
    value: object,
    target_keys: dict[str, str],
    *,
    prefix: str = "",
    limit: int = 6,
) -> list[str]:
    if limit <= 0:
        return []
    matches: list[str] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key_name = str(raw_key)
            key_path = f"{prefix}.{key_name}" if prefix else key_name
            display_key = target_keys.get(normalize_lookup(key_name))
            if display_key:
                matches.append(key_path if key_path == display_key else f"{key_path} ({display_key})")
                if len(matches) >= limit:
                    return matches
            matches.extend(
                _find_structured_key_paths(
                    child,
                    target_keys,
                    prefix=key_path,
                    limit=limit - len(matches),
                )
            )
            if len(matches) >= limit:
                return matches
    elif isinstance(value, list):
        child_prefix = f"{prefix}[]" if prefix else "[]"
        for child in value:
            matches.extend(
                _find_structured_key_paths(
                    child,
                    target_keys,
                    prefix=child_prefix,
                    limit=limit - len(matches),
                )
            )
            if len(matches) >= limit:
                return matches
    return matches


def _format_structured_key_paths(paths: list[str]) -> str:
    return ", ".join(paths[:6])


def _normalize_mechanics_impact_entry_type(value: object) -> str:
    return normalize_lookup(str(value or "").strip())


class SystemsService:
    def __init__(self, store: SystemsStore, repository_store: RepositoryStore) -> None:
        self.store = store
        self.repository_store = repository_store

    def get_campaign_custom_source_id(self, campaign_slug: str) -> str:
        normalized_campaign_slug = slugify(str(campaign_slug or "")).replace("/", "-").upper()
        if not normalized_campaign_slug:
            normalized_campaign_slug = "CAMPAIGN"
        return f"CUSTOM-{normalized_campaign_slug}"

    def ensure_builtin_library_seeded(self, library_slug: str) -> SystemsLibraryRecord | None:
        catalog = BUILTIN_LIBRARY_CATALOG.get(library_slug)
        existing_library = self.store.get_library(library_slug)
        if catalog is None:
            return existing_library

        # Normal page loads should not rewrite the Systems catalog on every read.
        library = existing_library
        if library is None:
            library = self.store.upsert_library(
                library_slug,
                title=str(catalog["title"]),
                system_code=str(catalog["system_code"]),
            )
        existing_source_ids = {
            source.source_id
            for source in self.store.list_sources(library_slug)
        }
        for source in catalog["sources"]:
            source_id = str(source["source_id"])
            if source_id in existing_source_ids:
                continue
            self.store.upsert_source(
                library_slug,
                source_id,
                title=str(source["title"]),
                license_class=str(source["license_class"]),
                public_visibility_allowed=bool(source.get("public_visibility_allowed", False)),
                requires_unofficial_notice=bool(source.get("requires_unofficial_notice", True)),
            )
        self._ensure_builtin_reference_entries_seeded(library.library_slug)
        return library

    def get_campaign_library_slug(self, campaign_slug: str) -> str:
        campaign = self._get_campaign(campaign_slug)
        if campaign is None:
            return ""
        if campaign.systems_library_slug:
            return campaign.systems_library_slug
        return campaign.system.strip()

    def get_campaign_library(self, campaign_slug: str) -> SystemsLibraryRecord | None:
        library_slug = self.get_campaign_library_slug(campaign_slug)
        if not library_slug:
            return None
        return self.ensure_builtin_library_seeded(library_slug)

    def ensure_campaign_custom_source(
        self,
        campaign_slug: str,
        *,
        actor_user_id: int | None = None,
    ) -> SystemsSourceRecord:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        campaign = self._get_campaign(campaign_slug)
        source_id = self.get_campaign_custom_source_id(campaign_slug)
        source_title = (
            f"{campaign.title} Custom Systems"
            if campaign is not None and str(campaign.title or "").strip()
            else f"{campaign_slug} Custom Systems"
        )
        source = self.store.upsert_source(
            library.library_slug,
            source_id,
            title=source_title,
            license_class="custom_campaign",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        self.store.upsert_campaign_policy(
            campaign_slug,
            library_slug=library.library_slug,
            updated_by_user_id=actor_user_id,
        )
        if self.store.get_campaign_enabled_source(campaign_slug, source.source_id) is None:
            self.store.upsert_campaign_enabled_source(
                campaign_slug,
                library_slug=library.library_slug,
                source_id=source.source_id,
                is_enabled=True,
                default_visibility=VISIBILITY_PLAYERS,
                updated_by_user_id=actor_user_id,
            )
        _systems_service_cache_clear()
        return source

    def is_campaign_custom_entry(self, campaign_slug: str, entry: SystemsEntryRecord) -> bool:
        source_state = self.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None:
            return False
        metadata = dict(entry.metadata or {})
        custom_campaign_slug = str(metadata.get("custom_campaign_slug") or "").strip()
        return source_state.source.license_class == "custom_campaign" and (
            not custom_campaign_slug or custom_campaign_slug == campaign_slug
        )

    def get_custom_campaign_entry_by_slug(
        self,
        campaign_slug: str,
        entry_slug: str,
    ) -> SystemsEntryRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        entry = self.store.get_entry_by_slug(library.library_slug, str(entry_slug or "").strip())
        if entry is None or not self.is_campaign_custom_entry(campaign_slug, entry):
            return None
        return entry

    def create_custom_campaign_entry(
        self,
        campaign_slug: str,
        *,
        title: str,
        entry_type: str,
        slug_leaf: str = "",
        provenance: str = "",
        visibility: str = VISIBILITY_PLAYERS,
        search_metadata: str = "",
        body_markdown: str = "",
        actor_user_id: int,
        can_set_private: bool,
    ) -> SystemsEntryRecord:
        source = self.ensure_campaign_custom_source(
            campaign_slug,
            actor_user_id=actor_user_id,
        )
        normalized_slug_leaf = slugify(slug_leaf or title).replace("/", "-").strip("-")
        if not normalized_slug_leaf:
            raise SystemsPolicyValidationError("Choose a URL slug or title before saving a custom Systems entry.")
        slug = f"{source.source_id.lower()}-{normalized_slug_leaf}"
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        existing = self.store.get_entry_by_slug(library.library_slug, slug)
        if existing is not None:
            raise SystemsPolicyValidationError("That custom Systems entry slug is already in use.")
        entry_key = f"{library.library_slug.lower()}|custom|{campaign_slug}|{normalized_slug_leaf}"
        return self._save_custom_campaign_entry(
            campaign_slug,
            source=source,
            entry_key=entry_key,
            slug=slug,
            title=title,
            entry_type=entry_type,
            provenance=provenance,
            visibility=visibility,
            search_metadata=search_metadata,
            body_markdown=body_markdown,
            actor_user_id=actor_user_id,
            can_set_private=can_set_private,
            is_enabled_override=None,
        )

    def update_custom_campaign_entry(
        self,
        campaign_slug: str,
        entry_slug: str,
        *,
        title: str,
        entry_type: str,
        provenance: str = "",
        visibility: str = VISIBILITY_PLAYERS,
        search_metadata: str = "",
        body_markdown: str = "",
        actor_user_id: int,
        can_set_private: bool,
    ) -> SystemsEntryRecord:
        existing = self.get_custom_campaign_entry_by_slug(campaign_slug, entry_slug)
        if existing is None:
            raise SystemsPolicyValidationError("Choose a valid custom Systems entry before saving.")
        source_state = self.get_campaign_source_state(campaign_slug, existing.source_id)
        if source_state is None:
            raise SystemsPolicyValidationError("The custom Systems source is no longer available.")
        override = self.store.get_campaign_entry_override(campaign_slug, existing.entry_key)
        return self._save_custom_campaign_entry(
            campaign_slug,
            source=source_state.source,
            entry_key=existing.entry_key,
            slug=existing.slug,
            title=title,
            entry_type=entry_type,
            provenance=provenance,
            visibility=visibility,
            search_metadata=search_metadata,
            body_markdown=body_markdown,
            actor_user_id=actor_user_id,
            can_set_private=can_set_private,
            is_enabled_override=override.is_enabled_override if override is not None else None,
        )

    def archive_custom_campaign_entry(
        self,
        campaign_slug: str,
        entry_slug: str,
        *,
        actor_user_id: int,
    ) -> SystemsEntryRecord:
        entry = self.get_custom_campaign_entry_by_slug(campaign_slug, entry_slug)
        if entry is None:
            raise SystemsPolicyValidationError("Choose a valid custom Systems entry before archiving.")
        override = self.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
        self.update_campaign_entry_override(
            campaign_slug,
            entry_key=entry.entry_key,
            visibility_override=override.visibility_override if override is not None else None,
            is_enabled_override=False,
            actor_user_id=actor_user_id,
            can_set_private=True,
        )
        return entry

    def restore_custom_campaign_entry(
        self,
        campaign_slug: str,
        entry_slug: str,
        *,
        actor_user_id: int,
    ) -> SystemsEntryRecord:
        entry = self.get_custom_campaign_entry_by_slug(campaign_slug, entry_slug)
        if entry is None:
            raise SystemsPolicyValidationError("Choose a valid custom Systems entry before restoring.")
        override = self.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
        self.update_campaign_entry_override(
            campaign_slug,
            entry_key=entry.entry_key,
            visibility_override=override.visibility_override if override is not None else None,
            is_enabled_override=None,
            actor_user_id=actor_user_id,
            can_set_private=True,
        )
        return entry

    def build_shared_core_entry_mechanics_impact_warning(
        self,
        entry: SystemsEntryRecord,
    ) -> SystemsMechanicsImpactWarning | None:
        raw_entry_type = str(entry.entry_type or "").strip()
        entry_type = _normalize_mechanics_impact_entry_type(raw_entry_type)
        metadata = dict(entry.metadata or {})
        body = dict(entry.body or {})
        signals: list[SystemsMechanicsImpactSignal] = []
        surfaces: set[str] = set()

        def add_signal(label: str, detail: str, surface: str) -> None:
            surfaces.add(surface)
            signals.append(
                SystemsMechanicsImpactSignal(
                    label=label,
                    detail=detail,
                    surface=surface,
                )
            )

        if entry_type in MECHANICS_IMPACT_CHARACTER_ENTRY_TYPES:
            entry_type_label = MECHANICS_IMPACT_ENTRY_TYPE_LABELS.get(
                entry_type,
                raw_entry_type.replace("_", " ").replace("-", " ").title(),
            )
            add_signal(
                "Character-facing entry type",
                (
                    f"{entry_type_label} entries can feed native "
                    "character creation, level-up, sheet links, spell or equipment catalogs, "
                    "or campaign option overlays when this source is enabled."
                ),
                "Character tools",
            )

        if entry_type in MECHANICS_IMPACT_COMBAT_ENTRY_TYPES:
            add_signal(
                "Combat-facing entry type",
                (
                    "Monster entries can seed combat NPCs; HP, speed, and Dexterity-derived "
                    "initiative are copied into combatants when the encounter is created."
                ),
                "Combat seeding",
            )

        rules_key_paths = _find_structured_key_paths(metadata, MECHANICS_IMPACT_RULE_METADATA_KEYS)
        rules_body_key_paths = _find_structured_key_paths(body, MECHANICS_IMPACT_RULE_METADATA_KEYS)
        if entry.source_id == DND5E_RULES_REFERENCE_SOURCE_ID or rules_key_paths or rules_body_key_paths:
            details = []
            if entry.source_id == DND5E_RULES_REFERENCE_SOURCE_ID:
                details.append("the shared RULES source")
            if rules_key_paths:
                details.append(f"metadata keys {_format_structured_key_paths(rules_key_paths)}")
            if rules_body_key_paths:
                details.append(f"body keys {_format_structured_key_paths(rules_body_key_paths)}")
            add_signal(
                "Rules reference identity and provenance",
                (
                    "This row carries stable rules-reference identity and source provenance used by related-rule "
                    f"links and character-math reference pages ({'; '.join(details)})."
                ),
                "Rules references",
            )

        character_key_paths = _find_structured_key_paths(metadata, MECHANICS_IMPACT_CHARACTER_METADATA_KEYS)
        character_body_key_paths = _find_structured_key_paths(body, MECHANICS_IMPACT_CHARACTER_METADATA_KEYS)
        if character_key_paths or character_body_key_paths:
            details = []
            if character_key_paths:
                details.append(f"metadata keys {_format_structured_key_paths(character_key_paths)}")
            if character_body_key_paths:
                details.append(f"body keys {_format_structured_key_paths(character_body_key_paths)}")
            add_signal(
                "Structured character mechanics",
                (
                    "Structured hooks on this row can be read by character option, progression, "
                    f"spell, resource, or derived-stat behavior ({'; '.join(details)})."
                ),
                "Character tools",
            )

        combat_key_paths = _find_structured_key_paths(metadata, MECHANICS_IMPACT_COMBAT_METADATA_KEYS)
        combat_body_key_paths = _find_structured_key_paths(body, MECHANICS_IMPACT_COMBAT_METADATA_KEYS)
        if combat_key_paths or combat_body_key_paths:
            details = []
            if combat_key_paths:
                details.append(f"metadata keys {_format_structured_key_paths(combat_key_paths)}")
            if combat_body_key_paths:
                details.append(f"body keys {_format_structured_key_paths(combat_body_key_paths)}")
            add_signal(
                "Structured combat mechanics",
                (
                    "Structured tactical fields on this row can affect combat seeding or "
                    f"encounter/session reference surfaces ({'; '.join(details)})."
                ),
                "Combat seeding",
            )

        if not signals:
            return None
        return SystemsMechanicsImpactWarning(
            summary=(
                "This shared/core Systems row participates in app-modeled behavior. "
                "Review the impacted surfaces before saving shared-library edits."
            ),
            surfaces=tuple(sorted(surfaces)),
            signals=tuple(signals),
        )

    def update_shared_core_entry(
        self,
        campaign_slug: str,
        entry_slug: str,
        *,
        title: str,
        source_page: str = "",
        source_path: str = "",
        search_text: str = "",
        player_safe_default: bool = False,
        dm_heavy: bool = False,
        metadata: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
        rendered_html: str = "",
    ) -> SystemsEntryRecord:
        existing = self.get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
        if existing is None:
            raise SystemsPolicyValidationError("Choose a valid shared/core Systems entry before saving.")
        source_state = self.get_campaign_source_state(campaign_slug, existing.source_id)
        if source_state is None:
            raise SystemsPolicyValidationError("The shared/core Systems source is no longer available.")
        if self.is_campaign_custom_entry(campaign_slug, existing):
            raise SystemsPolicyValidationError("Campaign custom entries must use the custom entry editor.")

        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise SystemsPolicyValidationError("Shared/core Systems entries need a title.")
        if len(normalized_title) > 200:
            raise SystemsPolicyValidationError("Shared/core Systems entry titles must stay under 200 characters.")

        normalized_source_page = str(source_page or "").strip()
        if len(normalized_source_page) > 80:
            raise SystemsPolicyValidationError("Shared/core Systems source pages must stay under 80 characters.")
        normalized_source_path = str(source_path or "").strip()
        if len(normalized_source_path) > 1000:
            raise SystemsPolicyValidationError("Shared/core Systems source paths must stay under 1000 characters.")
        normalized_search_text = str(search_text or "").strip()
        if len(normalized_search_text) > 40_000:
            raise SystemsPolicyValidationError("Shared/core Systems search text must stay under 40,000 characters.")
        normalized_rendered_html = str(rendered_html or "").strip()
        if len(normalized_rendered_html) > 500_000:
            raise SystemsPolicyValidationError("Shared/core Systems rendered HTML must stay under 500,000 characters.")

        entry = self.store.upsert_entry(
            existing.library_slug,
            existing.source_id,
            entry_key=existing.entry_key,
            entry_type=existing.entry_type,
            slug=existing.slug,
            title=normalized_title,
            source_page=normalized_source_page,
            source_path=normalized_source_path,
            search_text=normalized_search_text,
            player_safe_default=bool(player_safe_default),
            dm_heavy=bool(dm_heavy),
            metadata=dict(metadata or {}),
            body=dict(body or {}),
            rendered_html=normalized_rendered_html,
        )
        _systems_service_cache_clear()
        return entry

    def _save_custom_campaign_entry(
        self,
        campaign_slug: str,
        *,
        source: SystemsSourceRecord,
        entry_key: str,
        slug: str,
        title: str,
        entry_type: str,
        provenance: str,
        visibility: str,
        search_metadata: str,
        body_markdown: str,
        actor_user_id: int,
        can_set_private: bool,
        is_enabled_override: bool | None,
    ) -> SystemsEntryRecord:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise SystemsPolicyValidationError("Custom Systems entries need a title.")
        if len(normalized_title) > 200:
            raise SystemsPolicyValidationError("Custom Systems entry titles must stay under 200 characters.")
        normalized_entry_type = re.sub(r"[^a-z0-9_]+", "", str(entry_type or "").strip().lower())
        if not normalized_entry_type:
            raise SystemsPolicyValidationError("Choose an entry type before saving this custom Systems entry.")
        normalized_visibility = self._normalize_or_default_visibility(
            visibility,
            fallback=VISIBILITY_PLAYERS,
        )
        if normalized_visibility == VISIBILITY_PRIVATE and not can_set_private:
            raise SystemsPolicyValidationError("Private visibility is reserved for app admins.")
        if normalized_visibility == VISIBILITY_PUBLIC and not source.public_visibility_allowed:
            raise SystemsPolicyValidationError(
                f"{source.title} cannot be made public because that source is marked as non-public."
            )
        normalized_provenance = str(provenance or "").strip()
        if len(normalized_provenance) > 500:
            raise SystemsPolicyValidationError("Custom Systems provenance must stay under 500 characters.")
        normalized_search_metadata = str(search_metadata or "").strip()
        if len(normalized_search_metadata) > 4000:
            raise SystemsPolicyValidationError("Custom Systems searchable metadata must stay under 4000 characters.")
        normalized_body_markdown = str(body_markdown or "").strip()
        if not normalized_body_markdown:
            raise SystemsPolicyValidationError("Custom Systems entries need a rendered body.")
        if len(normalized_body_markdown) > 100_000:
            raise SystemsPolicyValidationError("Custom Systems entry bodies must stay under 100,000 characters.")
        rendered_html = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(normalized_body_markdown)
        search_text = " ".join(
            part
            for part in (
                normalized_title,
                normalized_entry_type,
                source.source_id,
                normalized_provenance,
                normalized_search_metadata,
            )
            if part
        ).lower()
        metadata = {
            "custom_campaign_slug": campaign_slug,
            "provenance": normalized_provenance,
            "search_metadata": normalized_search_metadata,
            "body_format": "markdown",
            "body_markdown": normalized_body_markdown,
            "updated_by_user_id": actor_user_id,
        }
        body = {
            "markdown": normalized_body_markdown,
        }
        existing_slug_entry = self.store.get_entry_by_slug(library.library_slug, slug)
        if existing_slug_entry is not None and existing_slug_entry.entry_key != entry_key:
            raise SystemsPolicyValidationError("That custom Systems entry slug is already in use.")
        entry = self.store.upsert_entry(
            library.library_slug,
            source.source_id,
            entry_key=entry_key,
            entry_type=normalized_entry_type,
            slug=slug,
            title=normalized_title,
            source_path=normalized_provenance,
            search_text=search_text,
            player_safe_default=normalized_visibility in {VISIBILITY_PUBLIC, VISIBILITY_PLAYERS},
            dm_heavy=normalized_visibility in {VISIBILITY_DM, VISIBILITY_PRIVATE},
            metadata=metadata,
            body=body,
            rendered_html=rendered_html,
        )
        self.update_campaign_entry_override(
            campaign_slug,
            entry_key=entry.entry_key,
            visibility_override=normalized_visibility,
            is_enabled_override=is_enabled_override,
            actor_user_id=actor_user_id,
            can_set_private=can_set_private,
        )
        _systems_service_cache_clear()
        refreshed_entry = self.store.get_entry(library.library_slug, entry.entry_key)
        if refreshed_entry is None:
            raise RuntimeError("Failed to reload custom Systems entry.")
        return refreshed_entry

    def get_campaign_policy(self, campaign_slug: str) -> CampaignSystemsPolicyRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        policy = self.store.get_campaign_policy(campaign_slug)
        if policy is not None:
            return policy
        now = utcnow()
        return CampaignSystemsPolicyRecord(
            campaign_slug=campaign_slug,
            library_slug=library.library_slug,
            status="active",
            proprietary_acknowledged_at=None,
            proprietary_acknowledged_by_user_id=None,
            created_at=now,
            updated_at=now,
            updated_by_user_id=None,
        )

    def list_campaign_source_states(self, campaign_slug: str) -> list[CampaignSourceState]:
        def _load_source_states() -> list[CampaignSourceState]:
            library = self.get_campaign_library(campaign_slug)
            if library is None:
                return []
            configured_by_id = {
                item.source_id: item
                for item in self.store.list_campaign_enabled_sources(campaign_slug)
                if item.library_slug == library.library_slug
            }
            seed_by_id = self._campaign_source_seed_map(campaign_slug)
            rows: list[CampaignSourceState] = []
            for source in self.store.list_sources(library.library_slug):
                configured = configured_by_id.get(source.source_id)
                seed = seed_by_id.get(source.source_id, {})
                if configured is not None:
                    is_enabled = configured.is_enabled
                    default_visibility = configured.default_visibility
                    is_configured = True
                else:
                    is_enabled = (
                        bool(seed.get("enabled"))
                        if "enabled" in seed
                        else self._default_enabled_for_source(source)
                    )
                    default_visibility = self._normalize_or_default_visibility(
                        seed.get("default_visibility"),
                        fallback=self._default_visibility_for_source(source),
                    )
                    is_configured = False
                rows.append(
                    CampaignSourceState(
                        source=source,
                        is_enabled=is_enabled,
                        default_visibility=self.clamp_visibility_for_source(source, default_visibility),
                        is_configured=is_configured,
                    )
                )
            return rows

        return list(
            _systems_service_cache_get(
                ("campaign-source-states", campaign_slug),
                _load_source_states,
            )
            or []
        )

    def _campaign_source_state_map(self, campaign_slug: str) -> dict[str, CampaignSourceState]:
        def _load_state_map() -> dict[str, CampaignSourceState]:
            return {
                row.source.source_id: row
                for row in self.list_campaign_source_states(campaign_slug)
                if row.source.source_id
            }

        return dict(
            _systems_service_cache_get(
                ("campaign-source-state-map", campaign_slug),
                _load_state_map,
            )
            or {}
        )

    def get_builder_static_revision(
        self,
        campaign_slug: str,
        *,
        entry_types: tuple[str, ...],
    ) -> tuple[object, ...] | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        normalized_entry_types = tuple(
            sorted(
                {
                    str(entry_type or "").strip()
                    for entry_type in tuple(entry_types or ())
                    if str(entry_type or "").strip()
                }
            )
        )
        if not normalized_entry_types:
            return None

        source_states = self.list_campaign_source_states(campaign_slug)
        source_key = tuple(
            (
                str(row.source.source_id or "").strip(),
                int(bool(row.is_enabled)),
                str(row.default_visibility or "").strip(),
                int(bool(row.is_configured)),
                str(row.source.status or "").strip(),
                isoformat(row.source.updated_at),
            )
            for row in source_states
        )
        enabled_source_ids = [
            str(row.source.source_id or "").strip()
            for row in source_states
            if row.is_enabled and str(row.source.source_id or "").strip()
        ]
        entries_revision = self.store.get_campaign_entries_revision(
            campaign_slug,
            library.library_slug,
            enabled_source_ids,
            list(normalized_entry_types),
        )
        overrides_revision = self.store.get_campaign_entry_overrides_revision(
            campaign_slug,
            library.library_slug,
        )
        return (
            library.library_slug,
            isoformat(library.updated_at),
            normalized_entry_types,
            source_key,
            entries_revision,
            overrides_revision,
        )

    def get_campaign_source_state(self, campaign_slug: str, source_id: str) -> CampaignSourceState | None:
        normalized_source_id = source_id.strip()
        if not normalized_source_id:
            return None
        return self._campaign_source_state_map(campaign_slug).get(normalized_source_id)

    def list_entry_type_counts_for_campaign_source(
        self,
        campaign_slug: str,
        source_id: str,
    ) -> list[tuple[str, int]]:
        state = self.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            return []
        return self.store.list_entry_type_counts_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
        )

    def list_entries_for_campaign_source(
        self,
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        state = self.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            return []
        entries = self.store.list_entries_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
            entry_type=entry_type,
            query=query,
            limit=limit,
        )
        if any(entry.entry_type == "book" for entry in entries):
            return sorted(entries, key=self._entry_source_browse_sort_key)
        return entries

    def list_enabled_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []

        normalized_query = str(query or "").strip()

        def _load_entries() -> list[SystemsEntryRecord]:
            enabled_source_ids = [
                str(row.source.source_id or "").strip()
                for row in self.list_campaign_source_states(campaign_slug)
                if row.is_enabled and str(row.source.source_id or "").strip()
            ]
            if not enabled_source_ids:
                return []
            return self.store.list_entries_for_campaign(
                campaign_slug,
                library.library_slug,
                enabled_source_ids,
                entry_type=entry_type,
                query=normalized_query,
                limit=limit,
            )

        return list(
            _systems_service_cache_get(
                (
                    "enabled-entries",
                    campaign_slug,
                    library.library_slug,
                    entry_type or "",
                    normalized_query,
                    limit,
                ),
                _load_entries,
            )
            or []
        )

    def count_entries_for_source(
        self,
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
    ) -> int:
        state = self.get_campaign_source_state(campaign_slug, source_id)
        if state is None:
            return 0
        return self.store.count_entries_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
            entry_type=entry_type,
        )

    def _class_feature_entries_by_class_identity(
        self,
        campaign_slug: str,
    ) -> dict[tuple[str, str], list[SystemsEntryRecord]]:
        def _load_lookup() -> dict[tuple[str, str], list[SystemsEntryRecord]]:
            lookup: dict[tuple[str, str], list[SystemsEntryRecord]] = defaultdict(list)
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type="classfeature",
                limit=None,
            ):
                class_name = str(candidate.metadata.get("class_name", "") or "").strip()
                class_source = str(candidate.metadata.get("class_source", "") or "").strip().upper()
                if class_name and class_source:
                    lookup[(class_name, class_source)].append(candidate)
            return dict(lookup)

        return dict(
            _systems_service_cache_get(
                ("class-feature-entries-by-class", campaign_slug),
                _load_lookup,
            )
            or {}
        )

    def _subclass_feature_entries_by_class_and_source(
        self,
        campaign_slug: str,
    ) -> dict[tuple[str, str, str], list[SystemsEntryRecord]]:
        def _load_lookup() -> dict[tuple[str, str, str], list[SystemsEntryRecord]]:
            lookup: dict[tuple[str, str, str], list[SystemsEntryRecord]] = defaultdict(list)
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type="subclassfeature",
                limit=None,
            ):
                class_name = str(candidate.metadata.get("class_name", "") or "").strip()
                class_source = str(candidate.metadata.get("class_source", "") or "").strip().upper()
                subclass_source = str(candidate.metadata.get("subclass_source", "") or "").strip().upper()
                if class_name and class_source and subclass_source:
                    lookup[(class_name, class_source, subclass_source)].append(candidate)
            return dict(lookup)

        return dict(
            _systems_service_cache_get(
                ("subclass-feature-entries-by-class-source", campaign_slug),
                _load_lookup,
            )
            or {}
        )

    def build_class_feature_progression_for_class_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []
        matching_entries = list(
            self._class_feature_entries_by_class_identity(campaign_slug).get(
                (
                    str(entry.title or "").strip(),
                    str(entry.source_id or "").strip().upper(),
                ),
                [],
            )
        )

        progression_rows = entry.body.get("feature_progression")
        matching_entries.extend(
            self._campaign_progression_entries_for_class_entry(campaign_slug, entry)
        )
        return self._build_feature_progression_groups(
            campaign_slug,
            matching_entries=matching_entries,
            progression_rows=progression_rows,
        )

    def build_subclass_feature_progression_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "subclass":
            return []
        class_name = str(entry.metadata.get("class_name", "") or "").strip()
        class_source = str(entry.metadata.get("class_source", "") or "").strip().upper()
        matching_entries = [
            candidate
            for candidate in self._subclass_feature_entries_by_class_and_source(campaign_slug).get(
                (
                    class_name,
                    class_source,
                    str(entry.source_id or "").strip().upper(),
                ),
                [],
            )
            and self._subclass_entry_matches_feature(entry, candidate)
        ]

        progression_rows = entry.body.get("feature_progression")
        matching_entries.extend(
            self._campaign_progression_entries_for_subclass_entry(campaign_slug, entry)
        )
        return self._build_feature_progression_groups(
            campaign_slug,
            matching_entries=matching_entries,
            progression_rows=progression_rows,
        )

    def _subclass_entry_matches_feature(
        self,
        subclass_entry: SystemsEntryRecord,
        subclass_feature_entry: SystemsEntryRecord,
    ) -> bool:
        subclass_title_variants = self._build_optionalfeature_title_variants(subclass_entry.title)
        feature_subclass_name = str(subclass_feature_entry.metadata.get("subclass_name", "") or "").strip()
        feature_title_variants = self._build_optionalfeature_title_variants(feature_subclass_name)
        return self._optionalfeature_titles_exactly_match(
            subclass_title_variants,
            feature_title_variants,
        ) or self._optionalfeature_titles_loosely_match(
            subclass_title_variants,
            feature_title_variants,
        )

    def build_class_starting_proficiency_rows(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []

        raw_rows = entry.body.get("starting_proficiencies")
        if not isinstance(raw_rows, list):
            return []

        skill_lookup = self._build_skill_entry_lookup(campaign_slug)
        rows: list[dict[str, object]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            name = str(raw_row.get("name", "") or "").strip()
            if not name:
                continue
            rows.append(
                {
                    "name": name,
                    "blocks": self._build_class_proficiency_blocks(
                        raw_row.get("entries"),
                        skill_lookup=skill_lookup if name.lower() == "skills" else None,
                    ),
                }
            )
        return [row for row in rows if row["blocks"]]

    def build_class_optionalfeature_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        class_feature_progression_groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []

        raw_progression = entry.metadata.get("optionalfeature_progression")
        if not isinstance(raw_progression, list):
            return []

        feature_type_lookup = self._build_optionalfeature_feature_type_lookup(campaign_slug)
        optionalfeature_lookup = self._build_optionalfeature_entry_lookup(campaign_slug)
        standalone_sections: list[dict[str, object]] = []
        for raw_section in raw_progression:
            section = self._build_class_optionalfeature_section(
                campaign_slug,
                raw_section,
                feature_type_lookup=feature_type_lookup,
                optionalfeature_lookup=optionalfeature_lookup,
            )
            if section is None:
                continue
            if not self._attach_optionalfeature_section_to_matching_class_feature(
                section,
                class_feature_progression_groups,
            ):
                standalone_sections.append(section)
        return standalone_sections

    def build_subclass_optionalfeature_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        subclass_feature_progression_groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if entry.entry_type != "subclass":
            return []

        raw_progression = entry.metadata.get("optionalfeature_progression")
        if not isinstance(raw_progression, list):
            return []

        feature_type_lookup = self._build_optionalfeature_feature_type_lookup(campaign_slug)
        optionalfeature_lookup = self._build_optionalfeature_entry_lookup(campaign_slug)
        standalone_sections: list[dict[str, object]] = []
        for raw_section in raw_progression:
            section = self._build_class_optionalfeature_section(
                campaign_slug,
                raw_section,
                feature_type_lookup=feature_type_lookup,
                optionalfeature_lookup=optionalfeature_lookup,
            )
            if section is None:
                continue
            if not self._attach_optionalfeature_section_to_matching_class_feature(
                section,
                subclass_feature_progression_groups,
            ):
                standalone_sections.append(section)
        return standalone_sections

    def build_feature_detail_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> dict[str, object] | None:
        if entry.entry_type not in {"classfeature", "subclassfeature", "optionalfeature"}:
            return None
        return self._build_embedded_feature_card(
            campaign_slug,
            entry,
            optionalfeature_lookup=self._build_optionalfeature_entry_lookup(campaign_slug),
        )

    def build_character_sheet_entry_body_html(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> str:
        body_entries = entry.body.get("entries")
        if body_entries is not None:
            body_html, _ = self._render_embedded_content(
                campaign_slug,
                body_entries,
                heading_level=5,
                extract_option_groups=False,
                optionalfeature_lookup=self._build_optionalfeature_entry_lookup(campaign_slug),
                preferred_source_id=entry.source_id,
            )
            if body_html.strip():
                return body_html

        if entry.entry_type == "class":
            progression_html = self._render_character_sheet_progression_groups(
                self.build_class_feature_progression_for_class_entry(campaign_slug, entry),
            )
            if progression_html:
                return progression_html
        if entry.entry_type == "subclass":
            progression_html = self._render_character_sheet_progression_groups(
                self.build_subclass_feature_progression_for_subclass_entry(campaign_slug, entry),
            )
            if progression_html:
                return progression_html

        return self._strip_systems_entry_summary_section(entry.rendered_html)

    def get_entry_by_slug_for_campaign(self, campaign_slug: str, entry_slug: str) -> SystemsEntryRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        return self.store.get_entry_by_slug(library.library_slug, entry_slug.strip())

    def get_entry_for_campaign(self, campaign_slug: str, entry_key: str) -> SystemsEntryRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        entry = self.store.get_entry(library.library_slug, entry_key.strip())
        if entry is None or not self.is_entry_enabled_for_campaign(campaign_slug, entry):
            return None
        return entry

    def build_related_rules_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.source_id == DND5E_RULES_REFERENCE_SOURCE_ID or entry.entry_type == "rule":
            return []

        rules_by_key = self._build_rules_reference_lookup(campaign_slug)
        if not rules_by_key:
            return []

        rule_keys = self._collect_related_rule_keys_for_entry(entry)
        return self._resolve_rule_entries_by_key(rules_by_key, rule_keys)

    def build_base_rule_refs_for_campaign_option(
        self,
        campaign_slug: str,
        campaign_option: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        option = dict(campaign_option or {})
        raw_refs = normalize_campaign_base_rule_refs(option.get("base_rule_refs"))
        if not raw_refs:
            return []

        rules_by_key = self._build_rules_reference_lookup(campaign_slug)
        resolved_refs: list[dict[str, object]] = []
        seen_keys: set[tuple[str, str]] = set()
        for raw_ref in raw_refs:
            resolved_ref = self._resolve_campaign_base_rule_ref(
                campaign_slug,
                raw_ref,
                rules_by_key=rules_by_key,
            )
            if resolved_ref is None:
                continue
            marker = (
                str(resolved_ref["entry"].entry_key or "").strip(),
                str(resolved_ref.get("anchor") or "").strip().casefold(),
            )
            if marker in seen_keys:
                continue
            seen_keys.add(marker)
            resolved_refs.append(resolved_ref)
        return resolved_refs

    def build_overlay_support_for_campaign_option(
        self,
        campaign_option: dict[str, object] | None,
        *,
        base_rule_refs: list[dict[str, object]] | None = None,
    ) -> dict[str, str] | None:
        if not list(base_rule_refs or []):
            return None
        option = dict(campaign_option or {})
        overlay_support = normalize_campaign_overlay_support(option.get("overlay_support"), option=option)
        if overlay_support == "modeled":
            return {
                "key": "modeled",
                "label": "Mechanically Modeled Overlay",
                "description": (
                    "This overlay uses existing structured campaign metadata that the app can already project on "
                    "supported character and build surfaces."
                ),
            }
        return {
            "key": "reference_only",
            "label": "Reference-Only Overlay",
            "description": (
                "This house rule stays visible beside the baseline links, but the app does not currently automate "
                "the change."
            ),
        }

    def build_active_campaign_overlays_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        overlay_cards: list[dict[str, object]] = []
        seen_markers: set[tuple[str, str]] = set()
        for record in self._list_visible_campaign_mechanics_page_records(campaign_slug):
            overlay_cards.extend(
                self._build_active_campaign_overlay_cards_from_record(
                    campaign_slug,
                    entry,
                    record,
                    seen_markers=seen_markers,
                )
            )
        return sorted(
            overlay_cards,
            key=lambda item: (
                normalize_lookup(str(item.get("title") or "")),
                str(item.get("page_ref") or "").casefold(),
            ),
        )

    def build_related_monsters_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.entry_type != "book":
            return []
        normalized_source_id = str(entry.source_id or "").strip().upper()
        if normalized_source_id == "VGM":
            matcher = VGM_MONSTER_LORE_WRAPPER_MONSTER_MATCHERS.get(normalize_lookup(entry.title))
            if not matcher:
                return []

            def build_value() -> list[SystemsEntryRecord]:
                related_entries: list[SystemsEntryRecord] = []
                seen_entry_keys: set[str] = set()
                for candidate in self.list_enabled_entries_for_campaign(
                    campaign_slug,
                    entry_type="monster",
                    limit=None,
                ):
                    if str(candidate.source_id or "").strip().upper() not in {"MM", "VGM"}:
                        continue
                    if candidate.entry_key in seen_entry_keys:
                        continue
                    if not self._monster_entry_matches_family(candidate, matcher):
                        continue
                    seen_entry_keys.add(candidate.entry_key)
                    related_entries.append(candidate)
                return sorted(
                    related_entries,
                    key=lambda candidate: (
                        *self._source_catalog_sort_key(candidate.source_id),
                        self._coerce_int(candidate.source_page, default=10_000),
                        candidate.title.lower(),
                        candidate.id,
                    ),
                )

            return _systems_service_cache_get(
                ("related_monsters_for_entry", campaign_slug, entry.entry_key),
                build_value,
            )

        title_keys = MTF_BOOK_WRAPPER_MONSTER_TITLE_KEYS.get(normalize_lookup(entry.title))
        if normalized_source_id != "MTF" or not title_keys:
            return []
        return self._build_curated_related_entries_for_entry(
            campaign_slug,
            entry=entry,
            entry_type="monster",
            source_ids=("MTF",),
            title_keys=title_keys,
            cache_prefix="related_monsters_for_entry",
        )

    def build_related_races_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.entry_type != "book":
            return []
        normalized_source_id = str(entry.source_id or "").strip().upper()
        if normalized_source_id == "VGM":
            matcher = VGM_CHARACTER_RACE_WRAPPER_RACE_MATCHERS.get(normalize_lookup(entry.title))
        elif normalized_source_id == "MTF":
            matcher = MTF_ANCESTRY_WRAPPER_RACE_MATCHERS.get(normalize_lookup(entry.title))
        elif normalized_source_id == "EGW":
            matcher = EGW_RACE_WRAPPER_RACE_MATCHERS.get(normalize_lookup(entry.title))
        else:
            matcher = None
        if not matcher:
            return []

        def build_value() -> list[SystemsEntryRecord]:
            related_entries: list[SystemsEntryRecord] = []
            seen_entry_keys: set[str] = set()
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type="race",
                limit=None,
            ):
                if str(candidate.source_id or "").strip().upper() != normalized_source_id:
                    continue
                if candidate.entry_key in seen_entry_keys:
                    continue
                if not self._race_entry_matches_wrapper(candidate, matcher):
                    continue
                seen_entry_keys.add(candidate.entry_key)
                related_entries.append(candidate)
            return sorted(
                related_entries,
                key=lambda candidate: (
                    self._coerce_int(candidate.source_page, default=10_000),
                    candidate.title.lower(),
                    candidate.id,
                ),
            )

        return _systems_service_cache_get(
            ("related_races_for_entry", campaign_slug, entry.entry_key),
            build_value,
        )

    def build_related_feats_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.entry_type != "book":
            return []
        if str(entry.source_id or "").strip().upper() != "MTF":
            return []
        title_keys = MTF_BOOK_WRAPPER_FEAT_TITLE_KEYS.get(normalize_lookup(entry.title))
        if not title_keys:
            return []
        return self._build_curated_related_entries_for_entry(
            campaign_slug,
            entry=entry,
            entry_type="feat",
            source_ids=("MTF",),
            title_keys=title_keys,
            cache_prefix="related_feats_for_entry",
        )

    def build_related_items_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.entry_type != "book":
            return []
        if str(entry.source_id or "").strip().upper() != "MTF":
            return []
        title_keys = MTF_BOOK_WRAPPER_ITEM_TITLE_KEYS.get(normalize_lookup(entry.title))
        if not title_keys:
            return []
        return self._build_curated_related_entries_for_entry(
            campaign_slug,
            entry=entry,
            entry_type="item",
            source_ids=("MTF",),
            title_keys=title_keys,
            cache_prefix="related_items_for_entry",
        )

    def build_source_context_sections_for_entry(
        self,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, str]]:
        if entry.entry_type != "book":
            return []
        if str(entry.source_id or "").strip().upper() != "VGM":
            return []

        raw_outline = (entry.metadata or {}).get("section_outline")
        if not isinstance(raw_outline, list) or not raw_outline:
            return []

        def build_value() -> list[dict[str, str]]:
            sections: list[dict[str, str]] = []
            seen_anchors: set[str] = set()
            for item in raw_outline:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                anchor = str(item.get("anchor") or "").strip()
                if not title or not anchor or anchor in seen_anchors:
                    continue
                if not self._is_vgm_source_context_section_title(title):
                    continue
                seen_anchors.add(anchor)
                section = {
                    "title": title,
                    "anchor": anchor,
                }
                page = str(item.get("page") or "").strip()
                if page:
                    section["page"] = page
                sections.append(section)
            return sections

        return _systems_service_cache_get(
            ("source_context_sections_for_entry", entry.entry_key),
            build_value,
        )

    def build_source_chapter_context_entries_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type == "book":
            return []
        source_id = str(entry.source_id or "").strip().upper()
        if not source_id:
            return []

        wrapper_titles = self._build_source_chapter_context_titles(entry)
        if not wrapper_titles:
            return []

        def build_value() -> list[dict[str, object]]:
            book_lookup = {
                normalize_lookup(candidate.title): candidate
                for candidate in self.list_entries_for_campaign_source(
                    campaign_slug,
                    source_id,
                    entry_type="book",
                    limit=None,
                )
            }
            context_entries: list[dict[str, object]] = []
            seen_entry_keys: set[str] = set()
            for title in wrapper_titles:
                candidate = book_lookup.get(normalize_lookup(title))
                if candidate is None or candidate.entry_key in seen_entry_keys:
                    continue
                seen_entry_keys.add(candidate.entry_key)
                metadata = dict(candidate.metadata or {})
                context_entries.append(
                    {
                        "entry": candidate,
                        "section_label": str(metadata.get("section_label") or "").strip(),
                        "chapter_title": str(metadata.get("chapter_title") or "").strip(),
                        "page": str(candidate.source_page or "").strip(),
                    }
                )
            return context_entries

        return _systems_service_cache_get(
            ("source_chapter_context_entries_for_entry", campaign_slug, entry.entry_key),
            build_value,
        )

    def _build_source_chapter_context_titles(
        self,
        entry: SystemsEntryRecord,
    ) -> tuple[str, ...]:
        source_id = str(entry.source_id or "").strip().upper()
        if source_id == "SCAG":
            return self._build_scag_source_chapter_context_titles(entry)
        if source_id == "EGW":
            return self._build_egw_source_chapter_context_titles(entry)
        return ()

    def build_related_rules_for_book_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> dict[str, list[SystemsEntryRecord]]:
        if entry.entry_type != "book" or str(entry.source_id or "").strip().upper() != "PHB":
            return {}

        raw_outline = (entry.metadata or {}).get("section_outline")
        if not isinstance(raw_outline, list) or not raw_outline:
            return {}

        rules_by_key = self._build_rules_reference_lookup(campaign_slug)
        if not rules_by_key:
            return {}

        related_by_anchor: dict[str, list[SystemsEntryRecord]] = {}
        for item in raw_outline:
            if not isinstance(item, dict):
                continue
            anchor = str(item.get("anchor") or "").strip()
            if not anchor:
                continue
            rule_keys = PHB_BOOK_SECTION_RULE_KEY_MAP.get(anchor, ())
            if not rule_keys:
                continue
            related_entries = self._resolve_rule_entries_by_key(rules_by_key, rule_keys)
            if related_entries:
                related_by_anchor[anchor] = related_entries
        return related_by_anchor

    def build_related_entities_for_book_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> dict[str, list[dict[str, object]]]:
        if entry.entry_type != "book":
            return {}

        raw_outline = (entry.metadata or {}).get("section_outline")
        if not isinstance(raw_outline, list) or not raw_outline:
            return {}

        body_entries = dict(entry.body or {}).get("entries")
        if body_entries in (None, "", [], {}):
            return {}

        visible_anchors = {
            str(item.get("anchor") or "").strip()
            for item in raw_outline
            if isinstance(item, dict) and str(item.get("anchor") or "").strip()
        }
        if not visible_anchors:
            return {}

        related_refs_by_anchor: dict[str, list[dict[str, str | None]]] = defaultdict(list)
        self._collect_book_section_entity_refs(
            body_entries,
            current_path=(),
            visible_anchors=visible_anchors,
            related_refs_by_anchor=related_refs_by_anchor,
        )
        if not related_refs_by_anchor:
            return {}

        entries_by_identity, exact_title_lookup = self._build_book_section_entity_lookups(campaign_slug)
        if not entries_by_identity and not exact_title_lookup:
            return {}

        current_source_id = str(entry.source_id or "").strip().upper()
        related_by_anchor: dict[str, list[dict[str, object]]] = {}
        for anchor, related_refs in related_refs_by_anchor.items():
            grouped_entries = self._resolve_book_section_entity_refs(
                related_refs,
                current_source_id=current_source_id,
                entries_by_identity=entries_by_identity,
                exact_title_lookup=exact_title_lookup,
            )
            if not grouped_entries:
                continue
            related_by_anchor[anchor] = grouped_entries
        return related_by_anchor

    def _build_rules_reference_lookup(self, campaign_slug: str) -> dict[str, SystemsEntryRecord]:
        rows = self.list_entries_for_campaign_source(
            campaign_slug,
            DND5E_RULES_REFERENCE_SOURCE_ID,
            entry_type="rule",
            limit=None,
        )
        lookup: dict[str, SystemsEntryRecord] = {}
        for entry in rows:
            metadata = dict(entry.metadata or {})
            rule_key = str(metadata.get("rule_key") or "").strip() or normalize_lookup(entry.title)
            if rule_key:
                lookup[rule_key] = entry
        return lookup

    def _resolve_rule_entries_by_key(
        self,
        rules_by_key: dict[str, SystemsEntryRecord],
        rule_keys: list[str] | tuple[str, ...],
    ) -> list[SystemsEntryRecord]:
        related_entries: list[SystemsEntryRecord] = []
        seen_entry_keys: set[str] = set()
        for rule_key in rule_keys:
            entry = rules_by_key.get(str(rule_key or "").strip())
            if entry is None or entry.entry_key in seen_entry_keys:
                continue
            seen_entry_keys.add(entry.entry_key)
            related_entries.append(entry)
        return related_entries

    def _resolve_campaign_base_rule_ref(
        self,
        campaign_slug: str,
        raw_ref: dict[str, object],
        *,
        rules_by_key: dict[str, SystemsEntryRecord],
    ) -> dict[str, object] | None:
        ref = dict(raw_ref or {})
        rule_key = str(ref.get("rule_key") or "").strip()
        entry_key = str(ref.get("entry_key") or "").strip()
        slug = str(ref.get("slug") or "").strip()
        expected_source_id = str(ref.get("source_id") or "").strip().upper()
        expected_entry_type = str(ref.get("entry_type") or "").strip().lower()
        anchor = str(ref.get("anchor") or "").strip()
        section_title = str(ref.get("section_title") or "").strip()

        entry: SystemsEntryRecord | None = None
        if rule_key:
            entry = rules_by_key.get(rule_key)
        if entry is None and entry_key:
            entry = self.get_entry_for_campaign(campaign_slug, entry_key)
        if entry is None and slug:
            entry = self.get_entry_by_slug_for_campaign(campaign_slug, slug)
        if entry is None or not self.is_entry_enabled_for_campaign(campaign_slug, entry):
            return None
        if expected_source_id and expected_source_id != str(entry.source_id or "").strip().upper():
            return None
        if expected_entry_type and expected_entry_type != str(entry.entry_type or "").strip().lower():
            return None

        label = entry.title
        if section_title and section_title.casefold() != str(entry.title or "").strip().casefold():
            label = f"{entry.title}: {section_title}"
        return {
            "entry": entry,
            "label": label,
            "anchor": anchor,
            "section_title": section_title,
        }

    def _build_curated_related_entries_for_entry(
        self,
        campaign_slug: str,
        *,
        entry: SystemsEntryRecord,
        entry_type: str,
        source_ids: tuple[str, ...],
        title_keys: tuple[str, ...],
        cache_prefix: str,
    ) -> list[SystemsEntryRecord]:
        normalized_source_ids = {
            str(source_id or "").strip().upper()
            for source_id in source_ids
            if str(source_id or "").strip()
        }
        if not normalized_source_ids or not title_keys:
            return []

        def build_value() -> list[SystemsEntryRecord]:
            related_entries: list[SystemsEntryRecord] = []
            seen_entry_keys: set[str] = set()
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type=entry_type,
                limit=None,
            ):
                if str(candidate.source_id or "").strip().upper() not in normalized_source_ids:
                    continue
                if candidate.entry_key in seen_entry_keys:
                    continue
                if normalize_lookup(candidate.title) not in title_keys:
                    continue
                seen_entry_keys.add(candidate.entry_key)
                related_entries.append(candidate)
            return sorted(
                related_entries,
                key=lambda candidate: (
                    *self._source_catalog_sort_key(candidate.source_id),
                    self._coerce_int(candidate.source_page, default=10_000),
                    candidate.title.lower(),
                    candidate.id,
                ),
            )

        return _systems_service_cache_get(
            (cache_prefix, campaign_slug, entry.entry_key),
            build_value,
        )

    def _monster_entry_matches_family(
        self,
        entry: SystemsEntryRecord,
        matcher: dict[str, tuple[str, ...]],
    ) -> bool:
        if entry.entry_type != "monster":
            return False

        title_key = normalize_lookup(entry.title)
        if title_key and title_key in matcher.get("title_keys", ()):
            return True
        if title_key and any(
            title_key.startswith(prefix_key) for prefix_key in matcher.get("title_prefix_keys", ())
        ):
            return True
        if title_key and any(
            title_key.endswith(suffix_key) for suffix_key in matcher.get("title_suffix_keys", ())
        ):
            return True

        metadata = dict(entry.metadata or {})
        group_keys = self._monster_metadata_group_keys(metadata.get("group"))
        if group_keys.intersection(matcher.get("group_keys", ())):
            return True

        type_keys, tag_keys = self._monster_metadata_type_keys(metadata.get("type"))
        if type_keys.intersection(matcher.get("type_keys", ())):
            return True
        if tag_keys.intersection(matcher.get("tag_keys", ())):
            return True
        return False

    def _race_entry_matches_wrapper(
        self,
        entry: SystemsEntryRecord,
        matcher: dict[str, tuple[str, ...]],
    ) -> bool:
        if entry.entry_type != "race":
            return False

        title_key = normalize_lookup(entry.title)
        if title_key and title_key in matcher.get("title_keys", ()):
            return True

        metadata = dict(entry.metadata or {})
        base_race_key = normalize_lookup(str(metadata.get("base_race_name") or ""))
        if base_race_key and base_race_key in matcher.get("base_race_keys", ()):
            return True
        return False

    def _build_scag_source_chapter_context_titles(
        self,
        entry: SystemsEntryRecord,
    ) -> tuple[str, ...]:
        if entry.entry_type == "race":
            wrapper_title = self._resolve_scag_race_wrapper_title(entry)
            return (wrapper_title,) if wrapper_title else ()
        if entry.entry_type in {"subclass", "subclassfeature"}:
            metadata = dict(entry.metadata or {})
            class_key = normalize_lookup(str(metadata.get("class_name") or ""))
            wrapper_title = SCAG_SUBCLASS_WRAPPER_TITLE_BY_CLASS_KEY.get(class_key, "")
            return (wrapper_title,) if wrapper_title else ()
        if entry.entry_type == "background":
            return ("Backgrounds",)
        if entry.entry_type == "item":
            wrapper_title = self._resolve_scag_item_wrapper_title(entry)
            return (wrapper_title,) if wrapper_title else ()
        return ()

    def _build_egw_source_chapter_context_titles(
        self,
        entry: SystemsEntryRecord,
    ) -> tuple[str, ...]:
        if entry.entry_type == "race":
            wrapper_title = self._resolve_egw_race_wrapper_title(entry)
            return (wrapper_title,) if wrapper_title else ()
        if entry.entry_type in {"subclass", "subclassfeature"}:
            metadata = dict(entry.metadata or {})
            class_key = normalize_lookup(str(metadata.get("class_name") or ""))
            wrapper_title = EGW_SUBCLASS_WRAPPER_TITLE_BY_CLASS_KEY.get(class_key, "")
            return (wrapper_title,) if wrapper_title else ()
        if entry.entry_type == "spell":
            return EGW_SPELL_WRAPPER_TITLES
        if entry.entry_type == "background":
            return ("Backgrounds",)
        if entry.entry_type == "item":
            return self._build_egw_item_source_chapter_context_titles(entry)
        return ()

    def _resolve_scag_race_wrapper_title(self, entry: SystemsEntryRecord) -> str:
        metadata = dict(entry.metadata or {})
        candidate_keys = [
            normalize_lookup(str(metadata.get("base_race_name") or "")),
            normalize_lookup(str(entry.title or "")),
        ]
        for candidate_key in candidate_keys:
            if not candidate_key:
                continue
            direct_match = SCAG_RACE_WRAPPER_TITLE_BY_KEY.get(candidate_key, "")
            if direct_match:
                return direct_match
            for race_key in SCAG_RACE_WRAPPER_MATCH_ORDER:
                if race_key and race_key in candidate_key:
                    return SCAG_RACE_WRAPPER_TITLE_BY_KEY.get(race_key, "")
        return ""

    def _resolve_egw_race_wrapper_title(self, entry: SystemsEntryRecord) -> str:
        metadata = dict(entry.metadata or {})
        candidate_keys = [
            normalize_lookup(str(metadata.get("base_race_name") or "")),
            normalize_lookup(str(entry.title or "")),
        ]
        for candidate_key in candidate_keys:
            if not candidate_key:
                continue
            wrapper_title = EGW_RACE_WRAPPER_TITLE_BY_KEY.get(candidate_key, "")
            if wrapper_title:
                return wrapper_title
        return ""

    def _build_egw_item_source_chapter_context_titles(
        self,
        entry: SystemsEntryRecord,
    ) -> tuple[str, ...]:
        normalized_title = normalize_lookup(str(entry.title or ""))
        if normalized_title in EGW_VESTIGE_ITEM_TITLE_KEYS:
            return ("Advancement of a Vestige of Divergence",)
        if normalized_title in EGW_BETRAYER_ITEM_TITLE_KEYS:
            return ("Betrayer Artifact Properties",)

        base_title = re.sub(
            r"\s+\((?:Dormant|Awakened|Exalted)\)\s*$",
            "",
            str(entry.title or ""),
            flags=re.IGNORECASE,
        ).strip()
        normalized_base_title = normalize_lookup(base_title)
        if normalized_base_title in EGW_VESTIGE_ITEM_TITLE_KEYS:
            return ("Advancement of a Vestige of Divergence",)
        if normalized_base_title in EGW_BETRAYER_ITEM_TITLE_KEYS:
            return ("Betrayer Artifact Properties",)
        return ()

    def _resolve_scag_item_wrapper_title(self, entry: SystemsEntryRecord) -> str:
        metadata = dict(entry.metadata or {})
        item_type_key = normalize_lookup(str(metadata.get("type") or ""))
        if item_type_key == normalize_lookup("INS"):
            return "Musical Instruments"

        title_key = normalize_lookup(entry.title)
        if title_key == normalize_lookup("Spiked Armor"):
            return "Primal Paths"

        page_key = str(entry.source_page or "").strip()
        return SCAG_ITEM_WRAPPER_TITLE_BY_PAGE.get(page_key, "")

    def _monster_metadata_group_keys(self, value: object) -> set[str]:
        keys: set[str] = set()
        raw_values = value if isinstance(value, list) else [value]
        for raw_value in raw_values:
            normalized_value = normalize_lookup(str(raw_value or ""))
            if normalized_value:
                keys.add(normalized_value)
        return keys

    def _monster_metadata_type_keys(self, value: object) -> tuple[set[str], set[str]]:
        type_keys: set[str] = set()
        tag_keys: set[str] = set()
        raw_values = value if isinstance(value, list) else [value]
        for raw_value in raw_values:
            if isinstance(raw_value, dict):
                normalized_type = normalize_lookup(str(raw_value.get("type") or ""))
                if normalized_type:
                    type_keys.add(normalized_type)
                raw_tags = raw_value.get("tags")
                tag_values = raw_tags if isinstance(raw_tags, list) else [raw_tags]
                for raw_tag in tag_values:
                    if isinstance(raw_tag, dict):
                        raw_tag = raw_tag.get("tag") or raw_tag.get("name") or raw_tag.get("value")
                    normalized_tag = normalize_lookup(str(raw_tag or ""))
                    if normalized_tag:
                        tag_keys.add(normalized_tag)
                continue

            normalized_type = normalize_lookup(str(raw_value or ""))
            if normalized_type:
                type_keys.add(normalized_type)
        return type_keys, tag_keys

    def _build_book_section_entity_lookups(
        self,
        campaign_slug: str,
    ) -> tuple[dict[tuple[str, str, str], SystemsEntryRecord], dict[tuple[str, str], list[SystemsEntryRecord]]]:
        def build_value():
            enabled_source_ids = [
                str(row.source.source_id or "").strip().upper()
                for row in self.list_campaign_source_states(campaign_slug)
                if row.is_enabled
            ]
            entries_by_identity: dict[tuple[str, str, str], SystemsEntryRecord] = {}
            exact_title_lookup: dict[tuple[str, str], list[SystemsEntryRecord]] = defaultdict(list)
            for source_id in enabled_source_ids:
                for entry_type in BOOK_SECTION_ENTITY_TYPE_ORDER:
                    for entry in self.list_entries_for_campaign_source(
                        campaign_slug,
                        source_id,
                        entry_type=entry_type,
                        limit=None,
                    ):
                        normalized_title = normalize_lookup(entry.title)
                        if not normalized_title:
                            continue
                        entries_by_identity.setdefault((source_id, entry_type, normalized_title), entry)
                        exact_title_lookup[(source_id, normalized_title)].append(entry)
            return entries_by_identity, dict(exact_title_lookup)

        return _systems_service_cache_get(
            ("book_section_entity_lookups", campaign_slug),
            build_value,
        )

    def _resolve_book_section_entity_refs(
        self,
        related_refs: list[dict[str, str | None]],
        *,
        current_source_id: str,
        entries_by_identity: dict[tuple[str, str, str], SystemsEntryRecord],
        exact_title_lookup: dict[tuple[str, str], list[SystemsEntryRecord]],
    ) -> list[dict[str, object]]:
        grouped_entries: dict[str, list[SystemsEntryRecord]] = defaultdict(list)
        seen_entry_keys: set[str] = set()
        for related_ref in related_refs:
            entry = self._resolve_book_section_entity_ref(
                related_ref,
                current_source_id=current_source_id,
                entries_by_identity=entries_by_identity,
                exact_title_lookup=exact_title_lookup,
            )
            if entry is None or entry.entry_key in seen_entry_keys:
                continue
            seen_entry_keys.add(entry.entry_key)
            grouped_entries[entry.entry_type].append(entry)

        groups: list[dict[str, object]] = []
        for entry_type in BOOK_SECTION_ENTITY_TYPE_ORDER:
            entries = grouped_entries.get(entry_type, [])
            if not entries:
                continue
            groups.append(
                {
                    "label": BOOK_SECTION_ENTITY_GROUP_LABELS.get(
                        entry_type,
                        entry_type.replace("_", " ").title(),
                    ),
                    "entries": entries,
                }
            )
        return groups

    def _resolve_book_section_entity_ref(
        self,
        related_ref: dict[str, str | None],
        *,
        current_source_id: str,
        entries_by_identity: dict[tuple[str, str, str], SystemsEntryRecord],
        exact_title_lookup: dict[tuple[str, str], list[SystemsEntryRecord]],
    ) -> SystemsEntryRecord | None:
        normalized_title = str(related_ref.get("title") or "").strip()
        if not normalized_title:
            return None
        explicit_source_id = str(related_ref.get("source_id") or "").strip().upper()
        entry_type = str(related_ref.get("entry_type") or "").strip().lower() or None
        source_ids = (
            (explicit_source_id,)
            if explicit_source_id
            else self._candidate_book_section_entity_source_ids(
                current_source_id=current_source_id,
                entry_type=entry_type,
            )
        )
        if not source_ids:
            return None

        if entry_type:
            for source_id in source_ids:
                entry = entries_by_identity.get((source_id, entry_type, normalized_title))
                if entry is not None:
                    return entry
            return None

        for source_id in source_ids:
            candidates = exact_title_lookup.get((source_id, normalized_title), [])
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _candidate_book_section_entity_source_ids(
        self,
        *,
        current_source_id: str,
        entry_type: str | None,
    ) -> tuple[str, ...]:
        normalized_source_id = str(current_source_id or "").strip().upper()
        if not normalized_source_id:
            return ()

        candidate_source_ids = [normalized_source_id]
        fallback_by_type = BOOK_SECTION_ENTITY_SOURCE_FALLBACKS.get(normalized_source_id, {})
        fallback_types = (entry_type,) if entry_type else BOOK_SECTION_ENTITY_TYPE_ORDER
        for fallback_type in fallback_types:
            normalized_fallback_type = str(fallback_type or "").strip().lower()
            if not normalized_fallback_type:
                continue
            for fallback_source_id in fallback_by_type.get(normalized_fallback_type, ()):
                normalized_fallback_source_id = str(fallback_source_id or "").strip().upper()
                if (
                    normalized_fallback_source_id
                    and normalized_fallback_source_id not in candidate_source_ids
                ):
                    candidate_source_ids.append(normalized_fallback_source_id)
        return tuple(candidate_source_ids)

    def _collect_book_section_entity_refs(
        self,
        value: object,
        *,
        current_path: tuple[str, ...],
        visible_anchors: set[str],
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
    ) -> None:
        if value is None:
            return
        current_anchor = self._resolve_visible_book_section_anchor(current_path, visible_anchors)
        if isinstance(value, str):
            self._collect_inline_book_section_entity_refs(
                value,
                visible_anchor=current_anchor,
                related_refs_by_anchor=related_refs_by_anchor,
            )
            return
        if isinstance(value, list):
            for item in value:
                self._collect_book_section_entity_refs(
                    item,
                    current_path=current_path,
                    visible_anchors=visible_anchors,
                    related_refs_by_anchor=related_refs_by_anchor,
                )
            return
        if not isinstance(value, dict):
            return

        next_path = current_path
        if self._is_book_navigation_section(value):
            name = self._clean_embedded_text(str(value.get("name", "") or ""))
            if name:
                next_path = (*current_path, name)
        next_anchor = self._resolve_visible_book_section_anchor(next_path, visible_anchors)
        self._collect_named_book_section_entity_refs(
            value,
            visible_anchor=next_anchor,
            related_refs_by_anchor=related_refs_by_anchor,
        )

        value_type = str(value.get("type", "") or "").strip().lower()
        nested_values: list[object] = []
        if value_type == "list":
            nested_values.append(value.get("items"))
        elif value_type == "table":
            nested_values.append(value.get("rows"))
            nested_values.append(value.get("rowsSpellProgression"))
        elif value_type == "options":
            nested_values.append(value.get("entries"))
        else:
            if value.get("entries") is not None:
                nested_values.append(value.get("entries"))
            elif value.get("entry") is not None:
                nested_values.append(value.get("entry"))
        for nested_value in nested_values:
            self._collect_book_section_entity_refs(
                nested_value,
                current_path=next_path,
                visible_anchors=visible_anchors,
                related_refs_by_anchor=related_refs_by_anchor,
            )

    def _collect_inline_book_section_entity_refs(
        self,
        value: str,
        *,
        visible_anchor: str | None,
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
    ) -> None:
        if not visible_anchor:
            return
        for match in INLINE_TAG_PATTERN.finditer(str(value or "")):
            body = match.group(1).strip()
            tag, _, remainder = body.partition(" ")
            tag_name = tag.lower().strip()
            entry_type = BOOK_SECTION_ENTITY_TAG_ENTRY_TYPES.get(tag_name)
            if not entry_type or not remainder.strip():
                continue
            resolved_entry_type, title, source_id = self._parse_book_section_entity_reference(
                tag_name,
                remainder,
                default_entry_type=entry_type,
            )
            if not resolved_entry_type or not title:
                continue
            self._append_book_section_entity_ref(
                related_refs_by_anchor,
                visible_anchor=visible_anchor,
                entry_type=resolved_entry_type,
                title=title,
                source_id=source_id,
            )

    def _collect_named_book_section_entity_refs(
        self,
        value: dict[str, object],
        *,
        visible_anchor: str | None,
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
    ) -> None:
        if not visible_anchor:
            return

        candidate_titles: list[str] = []
        name = self._clean_embedded_text(str(value.get("name", "") or ""))
        if name:
            candidate_titles.append(name)

        raw_aliases = value.get("alias")
        alias_values = raw_aliases if isinstance(raw_aliases, list) else [raw_aliases]
        for raw_alias in alias_values:
            alias = self._clean_embedded_text(str(raw_alias or ""))
            if alias:
                candidate_titles.append(alias)

        for title in candidate_titles:
            self._append_book_section_entity_ref(
                related_refs_by_anchor,
                visible_anchor=visible_anchor,
                entry_type=None,
                title=title,
                source_id=None,
            )

    def _append_book_section_entity_ref(
        self,
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
        *,
        visible_anchor: str,
        entry_type: str | None,
        title: str,
        source_id: str | None,
    ) -> None:
        normalized_title = normalize_lookup(self._clean_embedded_text(str(title or "")))
        if not normalized_title:
            return
        normalized_source_id = str(source_id or "").strip().upper() or None
        related_refs_by_anchor.setdefault(visible_anchor, []).append(
            {
                "entry_type": entry_type,
                "title": normalized_title,
                "source_id": normalized_source_id,
            }
        )

    def _parse_book_section_entity_reference(
        self,
        tag_name: str,
        raw_reference: str,
        *,
        default_entry_type: str,
    ) -> tuple[str | None, str, str | None]:
        parts = [part.strip() for part in str(raw_reference or "").split("|")]
        if not parts:
            return None, "", None
        title = self._clean_embedded_text(parts[0])
        if not title:
            return None, "", None

        normalized_tag = str(tag_name or "").strip().lower()
        if normalized_tag == "class":
            subclass_title = self._clean_embedded_text(parts[2]) if len(parts) > 2 else ""
            if subclass_title:
                return (
                    "subclass",
                    subclass_title,
                    self._normalize_book_section_source_id(parts[4] if len(parts) > 4 else "")
                    or self._normalize_book_section_source_id(parts[1] if len(parts) > 1 else ""),
                )
            return (
                default_entry_type,
                title,
                self._normalize_book_section_source_id(parts[1] if len(parts) > 1 else ""),
            )

        if normalized_tag == "subclass":
            return (
                default_entry_type,
                title,
                self._normalize_book_section_source_id(parts[4] if len(parts) > 4 else "")
                or self._normalize_book_section_source_id(parts[3] if len(parts) > 3 else "")
                or self._normalize_book_section_source_id(parts[2] if len(parts) > 2 else ""),
            )

        if normalized_tag == "classfeature":
            return (
                default_entry_type,
                title,
                self._normalize_book_section_source_id(parts[4] if len(parts) > 4 else "")
                or self._normalize_book_section_source_id(parts[2] if len(parts) > 2 else ""),
            )

        if normalized_tag == "subclassfeature":
            return (
                default_entry_type,
                title,
                self._normalize_book_section_source_id(parts[6] if len(parts) > 6 else "")
                or self._normalize_book_section_source_id(parts[4] if len(parts) > 4 else "")
                or self._normalize_book_section_source_id(parts[2] if len(parts) > 2 else ""),
            )

        return (
            default_entry_type,
            title,
            self._normalize_book_section_source_id(parts[1] if len(parts) > 1 else ""),
        )

    def _normalize_book_section_source_id(self, value: object) -> str | None:
        normalized_value = str(value or "").strip().upper()
        return normalized_value or None

    def _resolve_visible_book_section_anchor(
        self,
        current_path: tuple[str, ...],
        visible_anchors: set[str],
    ) -> str | None:
        if not current_path or not visible_anchors:
            return None
        for length in range(len(current_path), 0, -1):
            anchor = self._build_book_section_anchor(current_path[:length])
            if anchor in visible_anchors:
                return anchor
        return None

    def _build_book_section_anchor(self, path: tuple[str, ...]) -> str:
        parts: list[str] = []
        for item in path:
            cleaned_item = self._clean_embedded_text(str(item or ""))
            if not cleaned_item:
                continue
            anchor_part = slugify(cleaned_item).replace("/", "-") or normalize_lookup(cleaned_item)
            if anchor_part:
                parts.append(anchor_part)
        return "--".join(parts) or "book-section"

    def _is_book_navigation_section(self, value: object) -> bool:
        if not isinstance(value, dict):
            return False
        value_type = str(value.get("type", "") or "").strip().lower()
        if value_type not in {"", "section", "entries"}:
            return False
        if not self._clean_embedded_text(str(value.get("name", "") or "")):
            return False
        return value.get("entries") is not None or value.get("entry") is not None

    def _collect_related_rule_keys_for_entry(self, entry: SystemsEntryRecord) -> list[str]:
        metadata = dict(entry.metadata or {})
        title_key = normalize_lookup(entry.title)
        entry_type = str(entry.entry_type or "").strip().lower()
        rule_keys: list[str] = []

        def add_rule_key(rule_key: str) -> None:
            normalized_rule_key = str(rule_key or "").strip()
            if normalized_rule_key and normalized_rule_key not in rule_keys:
                rule_keys.append(normalized_rule_key)

        if entry_type == "skill":
            add_rule_key("ability-scores-and-ability-modifiers")
            add_rule_key("proficiency-bonus")
            add_rule_key("skill-bonuses-and-proficiency")
            if title_key in PASSIVE_CHECK_SKILL_KEYS:
                add_rule_key("passive-checks")
            return rule_keys

        if entry_type == "item":
            item_type = str(metadata.get("type") or "").strip().upper()
            is_armor = bool(metadata.get("armor")) or item_type in ARMOR_ITEM_TYPE_CODES or bool(metadata.get("ac"))
            is_weapon = item_type in WEAPON_ITEM_TYPE_CODES
            if is_armor:
                add_rule_key("armor-class")
            if is_weapon:
                add_rule_key("attack-rolls-and-attack-bonus")
                add_rule_key("damage-rolls")
            add_rule_key("equipped-items-inventory-and-attunement")
            return rule_keys

        if entry_type == "spell":
            add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type == "class":
            add_rule_key("proficiency-bonus")
            add_rule_key("hit-points-and-hit-dice")
            if self._entry_has_spellcasting_metadata(metadata):
                add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type == "subclass":
            if self._entry_has_spellcasting_metadata(metadata):
                add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type in {"classfeature", "subclassfeature", "feat", "optionalfeature"}:
            if metadata.get("additional_spells") is not None:
                add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type == "variantrule":
            if title_key == "encumbrance":
                add_rule_key("carrying-capacity-and-encumbrance")
            return rule_keys

        return rule_keys

    def _entry_has_spellcasting_metadata(self, metadata: dict[str, object]) -> bool:
        return any(
            metadata.get(key)
            for key in (
                "spellcasting_ability",
                "caster_progression",
                "prepared_spells",
                "prepared_spells_change",
                "prepared_spells_progression",
                "cantrip_progression",
                "spells_known_progression",
                "spells_known_progression_fixed",
                "slot_progression",
            )
        )

    def _entry_source_browse_sort_key(self, entry: SystemsEntryRecord) -> tuple[int, int, int, int, str, int]:
        if entry.entry_type == "book":
            return (
                0,
                self._coerce_int((entry.metadata or {}).get("chapter_index"), default=10_000),
                self._coerce_int((entry.metadata or {}).get("target_order"), default=10_000),
                self._coerce_int(entry.source_page, default=10_000),
                entry.title.lower(),
                entry.id,
            )
        return (1, 10_000, 10_000, entry.title.lower(), entry.id)

    def _source_catalog_sort_key(self, source_id: str) -> tuple[int, str]:
        normalized_source_id = str(source_id or "").strip().upper()
        for index, source in enumerate(DND_5E_SOURCE_CATALOG):
            if str(source.get("source_id") or "").strip().upper() == normalized_source_id:
                return (index, normalized_source_id)
        return (len(DND_5E_SOURCE_CATALOG), normalized_source_id)

    def _source_catalog_entry(
        self,
        source: SystemsSourceRecord | str,
        *,
        library_slug: str | None = None,
    ) -> dict[str, object] | None:
        if isinstance(source, SystemsSourceRecord):
            library_slug = source.library_slug
            source_id = source.source_id
        else:
            source_id = str(source or "").strip()
        resolved_library_slug = str(library_slug or "DND-5E").strip()
        if not resolved_library_slug or not str(source_id or "").strip():
            return None
        catalog = BUILTIN_LIBRARY_CATALOG.get(resolved_library_slug, {})
        normalized_source_id = str(source_id or "").strip().upper()
        for item in catalog.get("sources", ()):
            if str(item.get("source_id") or "").strip().upper() == normalized_source_id:
                return dict(item)
        return None

    def get_rules_reference_search_scope_for_source(
        self,
        source: SystemsSourceRecord | str,
        *,
        library_slug: str | None = None,
    ) -> str:
        catalog_entry = self._source_catalog_entry(source, library_slug=library_slug)
        scope = str(
            (catalog_entry or {}).get(
                "rules_reference_search_scope",
                RULES_REFERENCE_SEARCH_SCOPE_GLOBAL,
            )
            or RULES_REFERENCE_SEARCH_SCOPE_GLOBAL
        ).strip().lower()
        if scope not in {
            RULES_REFERENCE_SEARCH_SCOPE_GLOBAL,
            RULES_REFERENCE_SEARCH_SCOPE_SOURCE_ONLY,
        }:
            return RULES_REFERENCE_SEARCH_SCOPE_GLOBAL
        return scope

    def get_default_entry_visibility_for_campaign(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> str:
        source_state = self.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None or not source_state.is_enabled:
            return VISIBILITY_PRIVATE
        default_visibility = source_state.default_visibility
        entry_default_visibility = self._entry_default_visibility_for_source(
            source_state.source,
            entry,
        )
        if entry_default_visibility:
            default_visibility = most_private_visibility(default_visibility, entry_default_visibility)
        return self.clamp_visibility_for_source(source_state.source, default_visibility)

    def get_book_entry_policy_note_for_source(
        self,
        source: SystemsSourceRecord | str,
        *,
        library_slug: str | None = None,
    ) -> str:
        catalog_entry = self._source_catalog_entry(source, library_slug=library_slug)
        return str((catalog_entry or {}).get("book_entry_policy_note") or "").strip()

    def _rules_reference_entry_sort_key(self, entry: SystemsEntryRecord) -> tuple[int, str, int, int, str, int]:
        return (*self._source_catalog_sort_key(entry.source_id), *self._entry_source_browse_sort_key(entry))

    def _normalize_source_filter(self, source_ids: list[str] | None) -> list[str] | None:
        if source_ids is None:
            return None
        normalized = [
            str(source_id or "").strip().upper()
            for source_id in list(source_ids or [])
            if str(source_id or "").strip()
        ]
        return normalized

    def _entry_default_visibility_for_source(
        self,
        source: SystemsSourceRecord,
        entry: SystemsEntryRecord,
    ) -> str:
        if entry.entry_type != "book":
            return ""
        catalog_entry = self._source_catalog_entry(source)
        default_visibility = normalize_visibility_choice(
            str((catalog_entry or {}).get("book_entry_default_visibility") or "")
        )
        if is_valid_visibility(default_visibility):
            return default_visibility
        return ""

    def _reference_search_values(self, value: object) -> list[str]:
        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                values.extend(self._reference_search_values(item))
            return values
        if isinstance(value, dict):
            values: list[str] = []
            for key in ("title", "label", "name"):
                cleaned = str(value.get(key) or "").strip()
                if cleaned:
                    values.append(cleaned)
            return values
        cleaned = str(value or "").strip()
        return [cleaned] if cleaned else []

    def _build_rules_reference_search_text(self, entry: SystemsEntryRecord) -> str:
        metadata = dict(entry.metadata or {})
        search_parts: list[str] = [entry.title, entry.source_id, entry.entry_type]
        if entry.entry_type == "book":
            search_parts.extend(
                [
                    str(metadata.get("section_label") or "").strip(),
                    *self._reference_search_values(metadata.get("headers")),
                    *self._reference_search_values(metadata.get("section_outline")),
                ]
            )
        elif entry.entry_type == "rule":
            search_parts.extend(
                [
                    str(metadata.get("rule_key") or "").strip(),
                    str(metadata.get("formula") or "").strip(),
                    *self._reference_search_values(metadata.get("aliases")),
                    *self._reference_search_values(metadata.get("rule_facets")),
                ]
            )
        search_parts.extend(self._reference_search_values(metadata.get("reference_terms")))
        return " ".join(normalize_lookup(part) for part in search_parts if str(part or "").strip())

    def list_rules_reference_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        include_source_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        normalized_source_ids = self._normalize_source_filter(include_source_ids)
        if include_source_ids is not None and not normalized_source_ids:
            return []

        entries: list[SystemsEntryRecord] = []
        for entry_type in RULES_REFERENCE_ENTRY_TYPES:
            entries.extend(
                self.list_enabled_entries_for_campaign(
                    campaign_slug,
                    entry_type=entry_type,
                    limit=None,
                )
            )
        if normalized_source_ids is not None:
            entries = [entry for entry in entries if str(entry.source_id or "").strip().upper() in normalized_source_ids]
        entries = sorted(entries, key=self._rules_reference_entry_sort_key)
        if limit is not None:
            return entries[:limit]
        return entries

    def search_rules_reference_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        query: str,
        include_source_ids: list[str] | None = None,
        limit: int | None = 100,
    ) -> list[SystemsEntryRecord]:
        normalized_terms = [
            normalize_lookup(term)
            for term in str(query or "").split()
            if normalize_lookup(term)
        ]
        if not normalized_terms:
            return []

        matches = [
            entry
            for entry in self.list_rules_reference_entries_for_campaign(
                campaign_slug,
                include_source_ids=include_source_ids,
                limit=None,
            )
            if all(term in self._build_rules_reference_search_text(entry) for term in normalized_terms)
        ]
        if limit is not None:
            return matches[:limit]
        return matches

    def list_monster_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        limit: int = 1000,
    ) -> list[SystemsEntryRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        if not enabled_source_ids:
            return []
        entries = self.store.list_entries(
            library.library_slug,
            source_ids=enabled_source_ids,
            entry_type="monster",
            limit=limit,
        )
        return [entry for entry in entries if self.is_entry_enabled_for_campaign(campaign_slug, entry)]

    def build_monster_combat_seed(self, entry: SystemsEntryRecord) -> SystemsMonsterCombatSeed:
        if entry.entry_type != "monster":
            raise ValueError("Only monster entries can seed combat NPCs.")
        metadata = dict(entry.metadata or {})
        abilities = dict(metadata.get("abilities") or {})
        dex_score = self._coerce_int(abilities.get("dex"), default=10)
        initiative_bonus = (dex_score - 10) // 2
        speed = metadata.get("speed")
        return SystemsMonsterCombatSeed(
            entry_key=entry.entry_key,
            title=entry.title,
            source_id=entry.source_id,
            max_hp=self._extract_monster_hp_average(metadata.get("hp")),
            movement_total=self._extract_max_distance(speed),
            speed_label=self._format_speed_label(speed),
            initiative_bonus=initiative_bonus,
        )

    def search_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        query: str,
        include_source_ids: list[str] | None = None,
        entry_type: str | None = None,
        limit: int = 100,
    ) -> list[SystemsEntryRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []

        enabled_source_ids = {
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        }
        if include_source_ids is not None:
            enabled_source_ids &= {str(source_id).strip() for source_id in include_source_ids if str(source_id).strip()}
        if not enabled_source_ids:
            return []

        entries = self.store.search_entries(
            library.library_slug,
            query=query,
            source_ids=sorted(enabled_source_ids),
            entry_type=entry_type,
            limit=limit,
        )
        return [entry for entry in entries if self.is_entry_enabled_for_campaign(campaign_slug, entry)]

    def search_monster_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        query: str,
        limit: int = 30,
    ) -> list[SystemsEntryRecord]:
        return self.search_entries_for_campaign(
            campaign_slug,
            query=query,
            entry_type="monster",
            limit=limit,
        )

    def _campaign_entry_override_map(
        self,
        campaign_slug: str,
        library_slug: str,
    ) -> dict[str, CampaignEntryOverrideRecord]:
        def _load_override_map() -> dict[str, CampaignEntryOverrideRecord]:
            return {
                override.entry_key: override
                for override in self.store.list_campaign_entry_overrides(
                    campaign_slug,
                    library_slug,
                )
                if override.entry_key
            }

        return dict(
            _systems_service_cache_get(
                ("campaign-entry-override-map", campaign_slug, library_slug),
                _load_override_map,
            )
            or {}
        )

    def is_entry_enabled_for_campaign(self, campaign_slug: str, entry: SystemsEntryRecord) -> bool:
        source_state = self._campaign_source_state_map(campaign_slug).get(
            str(entry.source_id or "").strip()
        )
        if source_state is None or not source_state.is_enabled:
            return False
        override = self._campaign_entry_override_map(
            campaign_slug,
            source_state.source.library_slug,
        ).get(str(entry.entry_key or "").strip())
        if override is not None and override.is_enabled_override is False:
            return False
        return True

    def update_campaign_sources(
        self,
        campaign_slug: str,
        *,
        updates: list[dict[str, object]],
        actor_user_id: int,
        acknowledge_proprietary: bool,
        can_set_private: bool,
    ) -> list[SystemsSourceRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        current_policy = self.store.get_campaign_policy(campaign_slug)
        current_states = {row.source.source_id: row for row in self.list_campaign_source_states(campaign_slug)}
        source_records = {row.source.source_id: row.source for row in current_states.values()}
        normalized_updates: list[dict[str, object]] = []
        newly_enabled_proprietary = False
        for raw_update in updates:
            source_id = str(raw_update.get("source_id", "") or "").strip()
            source = source_records.get(source_id)
            if source is None:
                raise SystemsPolicyValidationError("Choose a valid systems source.")
            is_enabled = bool(raw_update.get("is_enabled", False))
            default_visibility = self._normalize_or_default_visibility(
                raw_update.get("default_visibility"),
                fallback=current_states[source_id].default_visibility,
            )
            if not is_valid_visibility(default_visibility):
                raise SystemsPolicyValidationError(f"Choose a valid visibility for {source.title}.")
            if default_visibility == VISIBILITY_PRIVATE and not can_set_private:
                raise SystemsPolicyValidationError("Private visibility is reserved for app admins.")
            if default_visibility == VISIBILITY_PUBLIC and not source.public_visibility_allowed:
                raise SystemsPolicyValidationError(
                    f"{source.title} cannot be made public because that source is marked as proprietary or otherwise non-public."
                )
            if (
                is_enabled
                and not current_states[source_id].is_enabled
                and source.license_class == "proprietary_private"
                and (current_policy is None or current_policy.proprietary_acknowledged_at is None)
            ):
                newly_enabled_proprietary = True
            normalized_updates.append(
                {
                    "source_id": source_id,
                    "is_enabled": is_enabled,
                    "default_visibility": self.clamp_visibility_for_source(source, default_visibility),
                }
            )

        if newly_enabled_proprietary and not acknowledge_proprietary:
            raise SystemsPolicyValidationError(
                "Acknowledge the proprietary-source notice before enabling a protected systems source."
            )

        self.store.upsert_campaign_policy(
            campaign_slug,
            library_slug=library.library_slug,
            proprietary_acknowledged_at=(
                isoformat(utcnow()) if newly_enabled_proprietary and acknowledge_proprietary else None
            ),
            proprietary_acknowledged_by_user_id=actor_user_id if newly_enabled_proprietary and acknowledge_proprietary else None,
            updated_by_user_id=actor_user_id,
        )

        changed_sources: list[SystemsSourceRecord] = []
        for update in normalized_updates:
            source_id = str(update["source_id"])
            current = current_states[source_id]
            if current.is_enabled == bool(update["is_enabled"]) and current.default_visibility == str(update["default_visibility"]) and current.is_configured:
                continue
            if current.is_enabled == bool(update["is_enabled"]) and current.default_visibility == str(update["default_visibility"]) and not current.is_configured:
                continue
            self.store.upsert_campaign_enabled_source(
                campaign_slug,
                library_slug=library.library_slug,
                source_id=source_id,
                is_enabled=bool(update["is_enabled"]),
                default_visibility=str(update["default_visibility"]),
                updated_by_user_id=actor_user_id,
            )
            source = source_records.get(source_id)
            if source is not None:
                changed_sources.append(source)
        if changed_sources:
            _systems_service_cache_clear()
        return changed_sources

    def update_campaign_entry_override(
        self,
        campaign_slug: str,
        *,
        entry_key: str,
        visibility_override: str | None,
        is_enabled_override: bool | None,
        actor_user_id: int,
        can_set_private: bool,
    ):
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        entry = self.store.get_entry(library.library_slug, entry_key.strip())
        if entry is None:
            raise SystemsPolicyValidationError("Choose a valid systems entry before saving an override.")
        source_state = self.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None:
            raise SystemsPolicyValidationError("That source is not available for this campaign.")
        normalized_visibility = None
        if visibility_override is not None and visibility_override != "":
            normalized_visibility = self._normalize_or_default_visibility(
                visibility_override,
                fallback=source_state.default_visibility,
            )
            if normalized_visibility == VISIBILITY_PRIVATE and not can_set_private:
                raise SystemsPolicyValidationError("Private visibility is reserved for app admins.")
            if normalized_visibility == VISIBILITY_PUBLIC and not source_state.source.public_visibility_allowed:
                raise SystemsPolicyValidationError(
                    f"{source_state.source.title} cannot be made public because that source is marked as proprietary or otherwise non-public."
                )
        self.store.upsert_campaign_policy(
            campaign_slug,
            library_slug=library.library_slug,
            updated_by_user_id=actor_user_id,
        )
        override = self.store.upsert_campaign_entry_override(
            campaign_slug,
            library_slug=library.library_slug,
            entry_key=entry.entry_key,
            visibility_override=normalized_visibility,
            is_enabled_override=is_enabled_override,
            updated_by_user_id=actor_user_id,
        )
        _systems_service_cache_clear()
        return override

    def clamp_visibility_for_source(self, source: SystemsSourceRecord, visibility: str) -> str:
        normalized = self._normalize_or_default_visibility(
            visibility,
            fallback=self._default_visibility_for_source(source),
        )
        if normalized == VISIBILITY_PUBLIC and not source.public_visibility_allowed:
            return VISIBILITY_PLAYERS
        return normalized

    def _get_campaign(self, campaign_slug: str):
        return self.repository_store.get().get_campaign(campaign_slug)

    def _campaign_source_seed_map(self, campaign_slug: str) -> dict[str, dict[str, object]]:
        campaign = self._get_campaign(campaign_slug)
        if campaign is None:
            return {}
        seed_map: dict[str, dict[str, object]] = {}
        for item in campaign.systems_source_defaults:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id", "") or "").strip()
            if not source_id:
                continue
            seed_map[source_id] = dict(item)
        return seed_map

    def _default_visibility_for_source(self, source: SystemsSourceRecord) -> str:
        catalog = BUILTIN_LIBRARY_CATALOG.get(source.library_slug, {})
        for item in catalog.get("sources", ()):
            if item["source_id"] == source.source_id:
                return str(item.get("default_visibility", VISIBILITY_DM))
        return VISIBILITY_DM

    def _default_enabled_for_source(self, source: SystemsSourceRecord) -> bool:
        catalog = BUILTIN_LIBRARY_CATALOG.get(source.library_slug, {})
        for item in catalog.get("sources", ()):
            if item["source_id"] == source.source_id:
                return bool(item.get("enabled_by_default", False))
        return False

    def _ensure_builtin_reference_entries_seeded(self, library_slug: str) -> None:
        if library_slug != "DND-5E":
            return
        expected_entries = build_dnd5e_rules_reference_entries()
        sentinel_entry = self.store.get_entry(library_slug, DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY)
        existing_count = self.store.count_entries_for_source(library_slug, DND5E_RULES_REFERENCE_SOURCE_ID)
        if (
            sentinel_entry is not None
            and sentinel_entry.source_id == DND5E_RULES_REFERENCE_SOURCE_ID
            and str((sentinel_entry.metadata or {}).get("seed_version") or "") == DND5E_RULES_REFERENCE_VERSION
            and existing_count == len(expected_entries)
        ):
            return
        self.store.replace_entries_for_source(
            library_slug,
            DND5E_RULES_REFERENCE_SOURCE_ID,
            entries=expected_entries,
        )

    def _normalize_or_default_visibility(self, value: object, *, fallback: str) -> str:
        normalized = normalize_visibility_choice(str(value or ""))
        if is_valid_visibility(normalized):
            return normalized
        return fallback

    def _build_skill_entry_lookup(self, campaign_slug: str) -> dict[str, SystemsEntryRecord]:
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        lookup: dict[str, SystemsEntryRecord] = {}
        for source_id in enabled_source_ids:
            for entry in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="skill",
                limit=None,
            ):
                lookup.setdefault(normalize_lookup(entry.title), entry)
        return lookup

    def _build_optionalfeature_entry_lookup(self, campaign_slug: str) -> dict[str, list[SystemsEntryRecord]]:
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        lookup: dict[str, list[SystemsEntryRecord]] = defaultdict(list)
        for source_id in enabled_source_ids:
            for entry in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="optionalfeature",
                limit=None,
            ):
                lookup[normalize_lookup(entry.title)].append(entry)
        return dict(lookup)

    def _build_optionalfeature_feature_type_lookup(
        self,
        campaign_slug: str,
    ) -> dict[str, list[SystemsEntryRecord]]:
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        lookup: dict[str, list[SystemsEntryRecord]] = defaultdict(list)
        for source_id in enabled_source_ids:
            for entry in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="optionalfeature",
                limit=None,
            ):
                for feature_type in self._normalize_optionalfeature_type_codes(entry.metadata.get("feature_type")):
                    lookup[feature_type].append(entry)
        for feature_type, entries in lookup.items():
            lookup[feature_type] = sorted(
                entries,
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
        return dict(lookup)

    def _build_feature_progression_groups(
        self,
        campaign_slug: str,
        *,
        matching_entries: list[SystemsEntryRecord],
        progression_rows: object,
    ) -> list[dict[str, object]]:
        if not matching_entries:
            return []
        if not isinstance(progression_rows, list):
            return []

        optionalfeature_lookup = self._build_optionalfeature_entry_lookup(campaign_slug)
        grouped_entries: dict[int, list[SystemsEntryRecord]] = defaultdict(list)
        for candidate in matching_entries:
            grouped_entries[self._coerce_int(candidate.metadata.get("level"), default=0)].append(candidate)

        rows: list[dict[str, object]] = []
        rendered_levels: set[int] = set()
        for group in progression_rows:
            if not isinstance(group, dict):
                continue
            level_label = str(group.get("name", "") or "").strip()
            level = self._extract_level_from_progression_label(level_label)
            if level > 0:
                rendered_levels.add(level)
            entries_for_level = sorted(
                grouped_entries.get(level, []),
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
            unmatched_entries = list(entries_for_level)
            feature_rows: list[dict[str, object]] = []
            raw_labels = group.get("entries")
            if isinstance(raw_labels, list):
                for raw_label in raw_labels:
                    label = str(raw_label or "").strip()
                    if not label:
                        continue
                    matched_entry = self._pop_matching_class_feature_entry(unmatched_entries, label)
                    feature_rows.append(
                        {
                            "label": label,
                            "entry": matched_entry,
                            "embedded_card": self._build_embedded_feature_card(
                                campaign_slug,
                                matched_entry,
                                optionalfeature_lookup=optionalfeature_lookup,
                            )
                            if matched_entry is not None
                            else None,
                        }
                    )
            for extra_entry in unmatched_entries:
                feature_rows.append(
                    {
                        "label": extra_entry.title,
                        "entry": extra_entry,
                        "embedded_card": self._build_embedded_feature_card(
                            campaign_slug,
                            extra_entry,
                            optionalfeature_lookup=optionalfeature_lookup,
                        ),
                    }
                )
            if not feature_rows:
                continue
            rows.append({"level": level, "level_label": level_label or f"Level {level}", "feature_rows": feature_rows})
        for level in sorted(level_key for level_key in grouped_entries if level_key > 0 and level_key not in rendered_levels):
            extra_entries = sorted(
                grouped_entries.get(level, []),
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
            if not extra_entries:
                continue
            rows.append(
                {
                    "level": level,
                    "level_label": f"Level {level}",
                    "feature_rows": [
                        {
                            "label": extra_entry.title,
                            "entry": extra_entry,
                            "embedded_card": self._build_embedded_feature_card(
                                campaign_slug,
                                extra_entry,
                                optionalfeature_lookup=optionalfeature_lookup,
                            ),
                        }
                        for extra_entry in extra_entries
                    ],
                }
            )
        return rows

    def _build_embedded_feature_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
        campaign_option = dict(entry.metadata.get("campaign_option") or {})
        base_rule_refs = self.build_base_rule_refs_for_campaign_option(campaign_slug, campaign_option)
        overlay_support = self.build_overlay_support_for_campaign_option(
            campaign_option,
            base_rule_refs=base_rule_refs,
        )
        base_rule_modification_summary = (
            dict(campaign_option.get("base_rule_modification_summary") or {})
            if isinstance(campaign_option.get("base_rule_modification_summary"), dict)
            else None
        )
        page_ref = str(entry.metadata.get("page_ref") or "").strip()
        if page_ref:
            return {
                "meta_badges": self._build_embedded_feature_badges(entry),
                "base_rule_refs": base_rule_refs,
                "overlay_support": overlay_support,
                "base_rule_modification_summary": base_rule_modification_summary,
                "body_html": self._build_campaign_page_body_html(campaign_slug, page_ref),
                "option_groups": [],
            }
        body_html, option_groups = self._render_embedded_content(
            campaign_slug,
            entry.body.get("entries"),
            heading_level=5,
            extract_option_groups=True,
            optionalfeature_lookup=optionalfeature_lookup,
            preferred_source_id=entry.source_id,
        )
        return {
            "meta_badges": self._build_embedded_feature_badges(entry),
            "base_rule_refs": base_rule_refs,
            "overlay_support": overlay_support,
            "base_rule_modification_summary": base_rule_modification_summary,
            "body_html": body_html,
            "option_groups": option_groups,
        }

    def _build_embedded_feature_badges(self, entry: SystemsEntryRecord) -> list[str]:
        entry_type_labels = {
            "classfeature": "Class Feature",
            "optionalfeature": "Optional Feature",
            "subclassfeature": "Subclass Feature",
        }
        badges: list[str] = []
        entry_type_label = entry_type_labels.get(entry.entry_type)
        if entry_type_label:
            badges.append(entry_type_label)

        class_name = str(entry.metadata.get("class_name", "") or "").strip()
        if class_name:
            badges.append(class_name)

        subclass_name = str(entry.metadata.get("subclass_name", "") or "").strip()
        if subclass_name:
            badges.append(subclass_name)

        if entry.source_id:
            badges.append(entry.source_id)

        level = self._coerce_int(entry.metadata.get("level"), default=0)
        if level > 0:
            badges.append(f"Level {level}")
        return badges

    def _campaign_progression_entries_for_class_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        return [
            candidate
            for candidate in self._list_campaign_progression_entries(campaign_slug)
            if candidate.entry_type == "classfeature"
            and self._campaign_progression_entry_matches_class(entry, candidate)
        ]

    def _campaign_progression_entries_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        return [
            candidate
            for candidate in self._list_campaign_progression_entries(campaign_slug)
            if candidate.entry_type == "subclassfeature"
            and self._campaign_progression_entry_matches_subclass(entry, candidate)
        ]

    def _list_campaign_progression_entries(self, campaign_slug: str) -> list[SystemsEntryRecord]:
        def _load_entries() -> list[SystemsEntryRecord]:
            entries: list[SystemsEntryRecord] = []
            seen_keys: set[str] = set()
            for record in self._list_visible_campaign_mechanics_page_records(campaign_slug):
                for entry in build_campaign_page_progression_entries(record):
                    entry_key = str(entry.entry_key or "").strip()
                    if entry_key and entry_key in seen_keys:
                        continue
                    if entry_key:
                        seen_keys.add(entry_key)
                    entries.append(entry)
            return entries

        return list(
            _systems_service_cache_get(
                ("campaign-progression-entries", campaign_slug),
                _load_entries,
            )
            or []
        )

    def _list_visible_campaign_mechanics_page_records(self, campaign_slug: str) -> list[object]:
        campaign = self._get_campaign(campaign_slug)
        page_store = getattr(self.repository_store, "page_store", None)
        if campaign is None or page_store is None:
            return []
        records = page_store.list_page_records(
            campaign_slug,
            content_dir=Path(campaign.player_content_dir),
            include_body=True,
        )
        return [
            record
            for record in records
            if (page := getattr(record, "page", None)) is not None
            and campaign.is_page_visible(page)
            and str(getattr(page, "section", "") or "").strip() == "Mechanics"
        ]

    def _build_active_campaign_overlay_cards_from_record(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        record: object,
        *,
        seen_markers: set[tuple[str, str]],
    ) -> list[dict[str, object]]:
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            return []
        page_title = str(getattr(page, "title", "") or "").strip() or page_ref
        body_html = self._build_campaign_page_body_html(campaign_slug, page_ref)

        overlay_cards: list[dict[str, object]] = []
        page_option = build_campaign_page_character_option(record, default_kind="feature")
        page_option_card = self._build_active_campaign_overlay_card(
            campaign_slug,
            entry,
            page_ref=page_ref,
            page_title=page_title,
            overlay_title=str(dict(page_option or {}).get("display_name") or page_title).strip() or page_title,
            overlay_key=f"page|{page_ref}",
            campaign_option=page_option,
            body_html=body_html,
            seen_markers=seen_markers,
        )
        if page_option_card is not None:
            overlay_cards.append(page_option_card)

        for progression_entry in build_campaign_page_progression_entries(record):
            page_progression_card = self._build_active_campaign_overlay_card(
                campaign_slug,
                entry,
                page_ref=page_ref,
                page_title=page_title,
                overlay_title=str(progression_entry.title or page_title).strip() or page_title,
                overlay_key=str(progression_entry.entry_key or "").strip()
                or f"progression|{page_ref}|{progression_entry.title}",
                campaign_option=dict(progression_entry.metadata.get("campaign_option") or {}),
                body_html=body_html,
                seen_markers=seen_markers,
            )
            if page_progression_card is not None:
                overlay_cards.append(page_progression_card)
        return overlay_cards

    def _build_active_campaign_overlay_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        page_ref: str,
        page_title: str,
        overlay_title: str,
        overlay_key: str,
        campaign_option: dict[str, object] | None,
        body_html: str,
        seen_markers: set[tuple[str, str]],
    ) -> dict[str, object] | None:
        option = dict(campaign_option or {})
        if not option:
            return None
        base_rule_refs = self.build_base_rule_refs_for_campaign_option(campaign_slug, option)
        matching_refs = self._filter_active_campaign_overlay_refs_for_entry(entry, base_rule_refs)
        if not matching_refs:
            return None
        target_labels, targets_entry_wide = self._build_overlay_target_labels_for_entry(entry, matching_refs)
        marker = (
            str(overlay_key or page_ref).strip().casefold(),
            "|".join(label.casefold() for label in target_labels)
            or ("entry" if targets_entry_wide else ""),
        )
        if marker in seen_markers:
            return None
        seen_markers.add(marker)
        return {
            "title": overlay_title,
            "page_ref": page_ref,
            "page_title": page_title,
            "overlay_support": self.build_overlay_support_for_campaign_option(
                option,
                base_rule_refs=base_rule_refs,
            ),
            "body_html": body_html,
            "target_labels": target_labels,
            "targets_entry_wide": targets_entry_wide,
        }

    def _filter_active_campaign_overlay_refs_for_entry(
        self,
        entry: SystemsEntryRecord,
        base_rule_refs: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        entry_key = str(entry.entry_key or "").strip()
        if not entry_key:
            return []
        matching_refs: list[dict[str, object]] = []
        seen_markers: set[tuple[str, str, str]] = set()
        for ref in list(base_rule_refs or []):
            ref_entry = ref.get("entry")
            if ref_entry is None or str(ref_entry.entry_key or "").strip() != entry_key:
                continue
            marker = (
                str(ref.get("label") or "").strip().casefold(),
                str(ref.get("anchor") or "").strip().casefold(),
                str(ref.get("section_title") or "").strip().casefold(),
            )
            if marker in seen_markers:
                continue
            seen_markers.add(marker)
            matching_refs.append(ref)
        return matching_refs

    def _build_overlay_target_labels_for_entry(
        self,
        entry: SystemsEntryRecord,
        matching_refs: list[dict[str, object]],
    ) -> tuple[list[str], bool]:
        book_section_lookup = self._build_book_section_title_lookup(entry)
        target_labels: list[str] = []
        seen_labels: set[str] = set()
        targets_entry_wide = False
        for ref in matching_refs:
            section_title = str(ref.get("section_title") or "").strip()
            anchor = str(ref.get("anchor") or "").strip()
            label = section_title or book_section_lookup.get(anchor, "")
            if label:
                marker = label.casefold()
                if marker in seen_labels:
                    continue
                seen_labels.add(marker)
                target_labels.append(label)
                continue
            if not anchor:
                targets_entry_wide = True
        return target_labels, targets_entry_wide

    def _build_book_section_title_lookup(self, entry: SystemsEntryRecord) -> dict[str, str]:
        if entry.entry_type != "book":
            return {}
        lookup: dict[str, str] = {}
        for raw_item in list((entry.metadata or {}).get("section_outline") or []):
            item = dict(raw_item or {}) if isinstance(raw_item, dict) else {}
            anchor = str(item.get("anchor") or "").strip()
            title = str(item.get("title") or "").strip()
            if anchor and title and anchor not in lookup:
                lookup[anchor] = title
        return lookup

    def _campaign_progression_entry_matches_class(
        self,
        class_entry: SystemsEntryRecord,
        progression_entry: SystemsEntryRecord,
    ) -> bool:
        class_name = str(progression_entry.metadata.get("class_name", "") or "").strip()
        if class_name != class_entry.title:
            return False
        class_source = str(progression_entry.metadata.get("class_source", "") or "").strip().upper()
        return not class_source or class_source == str(class_entry.source_id or "").strip().upper()

    def _campaign_progression_entry_matches_subclass(
        self,
        subclass_entry: SystemsEntryRecord,
        progression_entry: SystemsEntryRecord,
    ) -> bool:
        if not self._campaign_progression_entry_matches_class_name_only(subclass_entry, progression_entry):
            return False
        subclass_name = str(progression_entry.metadata.get("subclass_name", "") or "").strip()
        if subclass_name:
            subclass_title_variants = self._build_optionalfeature_title_variants(subclass_entry.title)
            feature_title_variants = self._build_optionalfeature_title_variants(subclass_name)
            if not (
                self._optionalfeature_titles_exactly_match(subclass_title_variants, feature_title_variants)
                or self._optionalfeature_titles_loosely_match(subclass_title_variants, feature_title_variants)
            ):
                return False
        subclass_source = str(progression_entry.metadata.get("subclass_source", "") or "").strip().upper()
        return not subclass_source or subclass_source == str(subclass_entry.source_id or "").strip().upper()

    def _campaign_progression_entry_matches_class_name_only(
        self,
        subclass_entry: SystemsEntryRecord,
        progression_entry: SystemsEntryRecord,
    ) -> bool:
        class_name = str(progression_entry.metadata.get("class_name", "") or "").strip()
        if class_name != str(subclass_entry.metadata.get("class_name", "") or "").strip():
            return False
        class_source = str(progression_entry.metadata.get("class_source", "") or "").strip().upper()
        subclass_class_source = str(subclass_entry.metadata.get("class_source", "") or "").strip().upper()
        return not class_source or class_source == subclass_class_source

    def _build_campaign_page_body_html(self, campaign_slug: str, page_ref: str) -> str:
        repository = self.repository_store.get()
        return str(repository.get_page_body_html(campaign_slug, page_ref) or "").strip()

    def _render_character_sheet_progression_groups(self, groups: list[dict[str, object]]) -> str:
        list_items: list[str] = []
        for group in groups:
            level_label = str(group.get("level_label") or "").strip()
            feature_rows = group.get("feature_rows")
            if not isinstance(feature_rows, list):
                continue
            labels = [
                str(row.get("label") or "").strip()
                for row in feature_rows
                if isinstance(row, dict) and str(row.get("label") or "").strip()
            ]
            if not labels:
                continue
            joined_labels = ", ".join(labels)
            if level_label:
                list_items.append(
                    f"<li><strong>{escape(level_label)}:</strong> {escape(joined_labels)}</li>"
                )
            else:
                list_items.append(f"<li>{escape(joined_labels)}</li>")
        if not list_items:
            return ""
        return "<p>Feature progression:</p><ul>" + "".join(list_items) + "</ul>"

    def _strip_systems_entry_summary_section(self, rendered_html: str) -> str:
        html = str(rendered_html or "").strip()
        if not html:
            return ""
        return re.sub(
            r"^\s*<section class=\"systems-entry-summary\">.*?</section>\s*",
            "",
            html,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

    def _build_embedded_optionalfeature_option(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
        return {
            "label": entry.title,
            "slug": entry.slug,
            "meta_badges": self._build_embedded_feature_badges(entry),
            "body_html": self._render_embedded_content(
                campaign_slug,
                entry.body.get("entries"),
                heading_level=6,
                extract_option_groups=False,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=entry.source_id,
            )[0],
        }

    def _build_embedded_option_group(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> dict[str, object]:
        count = self._coerce_int(value.get("count"), default=1)
        options: list[dict[str, object]] = []
        raw_entries = value.get("entries")
        if isinstance(raw_entries, list):
            for raw_option in raw_entries:
                resolved_entry = self._resolve_optionalfeature_entry(
                    raw_option,
                    optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
                label = self._format_feature_reference(raw_option)
                if resolved_entry is None:
                    if not label:
                        label = self._clean_embedded_text(str(raw_option or ""))
                    options.append(
                        {
                            "label": label,
                            "slug": None,
                            "meta_badges": [],
                            "body_html": "",
                        }
                    )
                    continue
                options.append(
                    self._build_embedded_optionalfeature_option(
                        campaign_slug,
                        resolved_entry,
                        optionalfeature_lookup=optionalfeature_lookup,
                    )
                )

        return {
            "summary_label": f"Choose {count} option{'s' if count != 1 else ''}",
            "options": options,
        }

    def _build_class_optionalfeature_section(
        self,
        campaign_slug: str,
        raw_section: object,
        *,
        feature_type_lookup: dict[str, list[SystemsEntryRecord]],
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object] | None:
        if not isinstance(raw_section, dict):
            return None
        title = self._clean_embedded_text(str(raw_section.get("name", "") or "")) or "Optional Features"
        feature_types = self._normalize_optionalfeature_type_codes(raw_section.get("featureType"))
        if not feature_types:
            return None

        options: list[dict[str, object]] = []
        seen_entry_keys: set[str] = set()
        for feature_type in feature_types:
            for entry in feature_type_lookup.get(feature_type, []):
                if entry.entry_key in seen_entry_keys:
                    continue
                seen_entry_keys.add(entry.entry_key)
                options.append(
                    self._build_embedded_optionalfeature_option(
                        campaign_slug,
                        entry,
                        optionalfeature_lookup=optionalfeature_lookup,
                    )
                )
        if not options:
            return None

        return {
            "title": title,
            "progression_text": self._format_optionalfeature_progression_text(raw_section.get("progression")),
            "options": options,
        }

    def _attach_optionalfeature_section_to_matching_class_feature(
        self,
        section: dict[str, object],
        class_feature_progression_groups: list[dict[str, object]],
    ) -> bool:
        section_title = normalize_lookup(str(section.get("title", "") or ""))
        section_title_variants = self._build_optionalfeature_title_variants(section_title)
        section_option_labels = self._collect_optionalfeature_section_option_labels(section)

        exact_matches: list[dict[str, object]] = []
        loose_matches: list[dict[str, object]] = []
        label_matches: list[dict[str, object]] = []
        for group in class_feature_progression_groups:
            if not isinstance(group, dict):
                continue
            feature_rows = group.get("feature_rows")
            if not isinstance(feature_rows, list):
                continue
            for row in feature_rows:
                if not isinstance(row, dict):
                    continue
                entry = row.get("entry")
                if not isinstance(entry, SystemsEntryRecord):
                    continue
                candidate_title = normalize_lookup(entry.title)
                candidate_title_variants = self._build_optionalfeature_title_variants(candidate_title)
                if self._optionalfeature_titles_exactly_match(section_title_variants, candidate_title_variants):
                    exact_matches.append(row)
                elif self._optionalfeature_titles_loosely_match(section_title_variants, candidate_title_variants):
                    loose_matches.append(row)
                if section_option_labels:
                    row_option_labels = self._collect_feature_row_optionalfeature_labels(row)
                    if (
                        row_option_labels
                        and (
                            row_option_labels == section_option_labels
                            or row_option_labels.issubset(section_option_labels)
                            or section_option_labels.issubset(row_option_labels)
                        )
                    ):
                        label_matches.append(row)

        if any(self._feature_row_already_surfaces_optionalfeatures(row) for row in label_matches):
            return True

        candidates = exact_matches or label_matches or loose_matches
        if not candidates:
            return False
        if any(self._feature_row_already_surfaces_optionalfeatures(row) for row in candidates):
            return True

        target_row = candidates[0]
        sections = target_row.setdefault("optionalfeature_sections", [])
        if isinstance(sections, list):
            sections.append(section)
        else:
            target_row["optionalfeature_sections"] = [section]
        return True

    def _feature_row_already_surfaces_optionalfeatures(self, row: dict[str, object]) -> bool:
        embedded_card = row.get("embedded_card")
        if isinstance(embedded_card, dict) and embedded_card.get("option_groups"):
            return True
        existing_sections = row.get("optionalfeature_sections")
        return isinstance(existing_sections, list) and bool(existing_sections)

    def _build_optionalfeature_title_variants(self, value: str) -> set[str]:
        normalized = normalize_lookup(value)
        if not normalized:
            return set()
        variants = {normalized}
        if normalized.endswith("s") and len(normalized) > 3:
            variants.add(normalized[:-1])
        return variants

    def _optionalfeature_titles_exactly_match(
        self,
        left_variants: set[str],
        right_variants: set[str],
    ) -> bool:
        return bool(left_variants and right_variants and (left_variants & right_variants))

    def _optionalfeature_titles_loosely_match(
        self,
        left_variants: set[str],
        right_variants: set[str],
    ) -> bool:
        if not left_variants or not right_variants:
            return False
        for left_value in left_variants:
            for right_value in right_variants:
                if left_value in right_value or right_value in left_value:
                    return True
        return False

    def _is_vgm_source_context_section_title(self, title: str) -> bool:
        normalized = normalize_lookup(title)
        if not normalized:
            return False
        if normalized.startswith("roleplaying"):
            return True
        if normalized == "regioneffects" or "lair" in normalized:
            return True
        if "tactics" in normalized:
            return True
        if normalized == "variantabilities" or normalized.startswith("variant") or normalized.endswith("variants"):
            return True
        return False

    def _collect_optionalfeature_section_option_labels(self, section: dict[str, object]) -> set[str]:
        options = section.get("options")
        if not isinstance(options, list):
            return set()
        labels = {
            normalize_lookup(str(option.get("label", "") or ""))
            for option in options
            if isinstance(option, dict)
        }
        return {label for label in labels if label}

    def _collect_feature_row_optionalfeature_labels(self, row: dict[str, object]) -> set[str]:
        labels: set[str] = set()
        embedded_card = row.get("embedded_card")
        if isinstance(embedded_card, dict):
            option_groups = embedded_card.get("option_groups")
            if isinstance(option_groups, list):
                for option_group in option_groups:
                    if not isinstance(option_group, dict):
                        continue
                    options = option_group.get("options")
                    if not isinstance(options, list):
                        continue
                    for option in options:
                        if not isinstance(option, dict):
                            continue
                        label = normalize_lookup(str(option.get("label", "") or ""))
                        if label:
                            labels.add(label)
        existing_sections = row.get("optionalfeature_sections")
        if isinstance(existing_sections, list):
            for section in existing_sections:
                if not isinstance(section, dict):
                    continue
                labels.update(self._collect_optionalfeature_section_option_labels(section))
        return labels

    def _normalize_optionalfeature_type_codes(self, value: object) -> list[str]:
        if isinstance(value, list):
            codes = [str(item or "").strip().upper() for item in value]
        elif value is None:
            codes = []
        else:
            code = str(value or "").strip().upper()
            codes = [code] if code else []
        return [code for code in codes if code]

    def _format_optionalfeature_progression_text(self, value: object) -> str:
        if isinstance(value, dict):
            parts = []
            for raw_level, raw_count in sorted(
                value.items(),
                key=lambda item: self._coerce_int(item[0], default=0),
            ):
                level = self._coerce_int(raw_level, default=0)
                count = self._coerce_int(raw_count, default=0)
                if level <= 0 or count <= 0:
                    continue
                parts.append(f"Level {level}: {count}")
            return ", ".join(parts)
        if isinstance(value, list):
            parts = []
            last_count: int | None = None
            for index, raw_count in enumerate(value, start=1):
                count = self._coerce_int(raw_count, default=0)
                if count <= 0 or count == last_count:
                    last_count = count
                    continue
                parts.append(f"Level {index}: {count}")
                last_count = count
            return ", ".join(parts)
        return ""

    def _render_embedded_content(
        self,
        campaign_slug: str,
        value: object,
        *,
        heading_level: int,
        extract_option_groups: bool,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        if value is None:
            return "", []
        if isinstance(value, str):
            text = self._clean_embedded_text(value)
            return (f"<p>{escape(text)}</p>" if text else ""), []
        if isinstance(value, (int, float)):
            return f"<p>{escape(str(value))}</p>", []
        if isinstance(value, list):
            html_parts: list[str] = []
            option_groups: list[dict[str, object]] = []
            for item in value:
                rendered_html, nested_option_groups = self._render_embedded_content(
                    campaign_slug,
                    item,
                    heading_level=heading_level,
                    extract_option_groups=extract_option_groups,
                    optionalfeature_lookup=optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
                if rendered_html:
                    html_parts.append(rendered_html)
                option_groups.extend(nested_option_groups)
            return "\n".join(html_parts), option_groups
        if isinstance(value, dict):
            value_type = str(value.get("type", "") or "").strip().lower()
            if self._looks_like_ability_block(value):
                return self._render_embedded_ability_scores(value), []
            if value_type == "list":
                items = value.get("items")
                if not isinstance(items, list):
                    return "", []
                list_items: list[str] = []
                option_groups: list[dict[str, object]] = []
                for item in items:
                    rendered_item, nested_option_groups = self._render_embedded_list_item(
                        campaign_slug,
                        item,
                        heading_level=heading_level,
                        extract_option_groups=extract_option_groups,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    )
                    if rendered_item:
                        list_items.append(rendered_item)
                    option_groups.extend(nested_option_groups)
                if not list_items:
                    return "", option_groups
                return "<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>", option_groups
            if value_type == "options":
                if extract_option_groups:
                    option_group = self._build_embedded_option_group(
                        campaign_slug,
                        value,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    )
                    return "", ([option_group] if option_group["options"] else [])
                return self._render_embedded_option_list(
                    campaign_slug,
                    value,
                    heading_level=heading_level,
                    optionalfeature_lookup=optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
            if value_type == "table":
                return self._render_embedded_table(value), []
            if value_type in {"abilitydc", "abilityattackmod"}:
                return self._render_embedded_ability_formula(value), []
            if value_type in {"refclassfeature", "refoptionalfeature", "refsubclassfeature"}:
                return (
                    self._render_embedded_reference(
                        campaign_slug,
                        value,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    ),
                    [],
                )

            name = self._clean_embedded_text(str(value.get("name", "") or ""))
            entries = value.get("entries")
            entry_value = entries if entries is not None else value.get("entry")
            rendered_entries, option_groups = self._render_embedded_content(
                campaign_slug,
                entry_value,
                heading_level=min(heading_level + 1, 6),
                extract_option_groups=extract_option_groups,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if name and rendered_entries:
                heading_tag = f"h{heading_level}"
                return f"<section><{heading_tag}>{escape(name)}</{heading_tag}>{rendered_entries}</section>", option_groups
            if name:
                return f"<p><strong>{escape(name)}.</strong></p>", option_groups
            return rendered_entries, option_groups
        text = self._clean_embedded_text(str(value or ""))
        return (f"<p>{escape(text)}</p>" if text else ""), []

    def _render_embedded_list_item(
        self,
        campaign_slug: str,
        item: object,
        *,
        heading_level: int,
        extract_option_groups: bool,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        if isinstance(item, dict) and str(item.get("type", "") or "").strip().lower() == "item":
            name = self._clean_embedded_text(str(item.get("name", "") or ""))
            entry_value = item.get("entry", item.get("entries"))
            entry_text, option_groups = self._render_embedded_content(
                campaign_slug,
                entry_value,
                heading_level=heading_level,
                extract_option_groups=extract_option_groups,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            stripped_entry_text = self._strip_outer_paragraph(entry_text)
            if name and stripped_entry_text:
                return f"<strong>{escape(name)}</strong> {stripped_entry_text}", option_groups
            if name:
                return f"<strong>{escape(name)}</strong>", option_groups
            return stripped_entry_text, option_groups
        rendered_html, option_groups = self._render_embedded_content(
            campaign_slug,
            item,
            heading_level=heading_level,
            extract_option_groups=extract_option_groups,
            optionalfeature_lookup=optionalfeature_lookup,
            preferred_source_id=preferred_source_id,
        )
        return self._strip_outer_paragraph(rendered_html), option_groups

    def _render_embedded_option_list(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        heading_level: int,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        parts: list[str] = []
        count = value.get("count")
        if count not in (None, ""):
            count_text = str(count).strip()
            if count_text:
                parts.append(f"<p>Choose {escape(count_text)} option{'s' if count_text != '1' else ''}:</p>")
        option_entries = value.get("entries")
        if not isinstance(option_entries, list):
            return "".join(parts), []
        list_items: list[str] = []
        for item in option_entries:
            rendered_item, _ = self._render_embedded_list_item(
                campaign_slug,
                item,
                heading_level=heading_level,
                extract_option_groups=False,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if rendered_item:
                list_items.append(rendered_item)
        if list_items:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
        return "".join(parts), []

    def _render_embedded_table(self, value: dict[str, object]) -> str:
        rows = value.get("rows")
        if not isinstance(rows, list):
            return ""
        parts = ['<div class="table-scroll"><table>']
        caption = self._clean_embedded_text(str(value.get("caption", "") or ""))
        if caption:
            parts.append(f"<caption>{escape(caption)}</caption>")
        headers = value.get("colLabels")
        if isinstance(headers, list) and headers:
            parts.append("<thead><tr>")
            for header in headers:
                header_text = self._clean_embedded_text(str(header or ""))
                parts.append(f"<th>{escape(header_text)}</th>")
            parts.append("</tr></thead>")
        parts.append("<tbody>")
        for row in rows:
            if not isinstance(row, list):
                continue
            parts.append("<tr>")
            for cell in row:
                cell_text = self._clean_embedded_text(str(cell or ""))
                parts.append(f"<td>{escape(cell_text)}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table></div>")
        return "".join(parts)

    def _render_embedded_ability_scores(self, value: dict[str, object]) -> str:
        headers: list[str] = []
        cells: list[str] = []
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            score = value.get(ability)
            if score is None:
                continue
            headers.append(f"<th>{escape(ability.upper())}</th>")
            cells.append(f"<td>{escape(str(score))}</td>")
        if not headers:
            return ""
        return (
            '<div class="table-scroll"><table>'
            + "<thead><tr>"
            + "".join(headers)
            + "</tr></thead><tbody><tr>"
            + "".join(cells)
            + "</tr></tbody></table></div>"
        )

    def _render_embedded_ability_formula(self, value: dict[str, object]) -> str:
        value_type = str(value.get("type", "") or "").strip().lower()
        name = self._clean_embedded_text(str(value.get("name", "") or "")) or "Spell"
        ability_phrase = self._format_embedded_ability_attribute_phrase(value.get("attributes"))
        if value_type == "abilitydc":
            formula = (
                f"8 + your proficiency bonus + your {ability_phrase} modifier"
                if ability_phrase
                else "8 + your proficiency bonus + your spellcasting ability modifier"
            )
            return f"<p><strong>{escape(name)} save DC:</strong> {escape(formula)}</p>"
        if value_type == "abilityattackmod":
            formula = (
                f"your proficiency bonus + your {ability_phrase} modifier"
                if ability_phrase
                else "your proficiency bonus + your spellcasting ability modifier"
            )
            return f"<p><strong>{escape(name)} attack modifier:</strong> {escape(formula)}</p>"
        return ""

    def _format_embedded_ability_attribute_phrase(self, value: object) -> str:
        if isinstance(value, list):
            labels = [
                ABILITY_NAME_LABELS.get(str(item or "").strip().lower(), str(item or "").strip())
                for item in value
                if str(item or "").strip()
            ]
        elif value is None:
            labels = []
        else:
            raw_value = str(value or "").strip()
            labels = [ABILITY_NAME_LABELS.get(raw_value.lower(), raw_value)] if raw_value else []
        if not labels:
            return ""
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} or {labels[1]}"
        return ", ".join(labels[:-1]) + f", or {labels[-1]}"

    def _render_embedded_reference(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> str:
        label = self._format_feature_reference(value)
        if not label:
            return ""
        value_type = str(value.get("type", "") or "").strip().lower()
        if value_type == "refoptionalfeature":
            resolved_entry = self._resolve_optionalfeature_entry(
                value,
                optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if resolved_entry is not None:
                href = self._build_entry_href(campaign_slug, resolved_entry.slug)
                return f'<p><a href="{escape(href)}">{escape(resolved_entry.title)}</a></p>'
        return f"<p>{escape(label)}</p>"

    def _build_entry_href(self, campaign_slug: str, entry_slug: str) -> str:
        return f"/campaigns/{campaign_slug}/systems/entries/{entry_slug}"

    def _resolve_optionalfeature_entry(
        self,
        value: object,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        *,
        preferred_source_id: str,
    ) -> SystemsEntryRecord | None:
        label, source_id = self._split_optionalfeature_reference(value)
        if not label:
            return None
        candidates = optionalfeature_lookup.get(normalize_lookup(label), [])
        if not candidates:
            return None
        if source_id:
            for candidate in candidates:
                if candidate.source_id.upper() == source_id:
                    return candidate
        for candidate in candidates:
            if candidate.source_id.upper() == preferred_source_id.upper():
                return candidate
        return candidates[0]

    def _split_optionalfeature_reference(self, value: object) -> tuple[str, str | None]:
        raw_reference = value
        if isinstance(value, dict):
            raw_reference = value.get("optionalfeature")
        if isinstance(raw_reference, str):
            parts = [part.strip() for part in raw_reference.split("|")]
            label = parts[0] if parts else ""
            source_id = parts[1].upper() if len(parts) > 1 and parts[1] else None
            return label, source_id
        return self._format_feature_reference(value), None

    def _format_feature_reference(self, value: object) -> str:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split("|")]
            return self._clean_embedded_text(parts[0]) if parts else ""
        if isinstance(value, dict):
            raw_reference = (
                value.get("classFeature")
                or value.get("subclassFeature")
                or value.get("optionalfeature")
            )
            label = self._format_feature_reference(raw_reference)
            if value.get("gainSubclassFeature") and label:
                return f"{label} (choose subclass feature)"
            return label
        return self._clean_embedded_text(str(value or ""))

    def _clean_embedded_text(self, value: str) -> str:
        stripped = self._strip_embedded_inline_tags(value)
        return re.sub(r"\s+", " ", stripped).strip()

    def _strip_embedded_inline_tags(self, value: str) -> str:
        rendered = str(value or "")
        while True:
            updated = INLINE_TAG_PATTERN.sub(self._replace_embedded_inline_tag, rendered)
            if updated == rendered:
                return updated
            rendered = updated

    def _replace_embedded_inline_tag(self, match: re.Match[str]) -> str:
        body = match.group(1).strip()
        tag, _, remainder = body.partition(" ")
        normalized_tag = tag.lower()
        raw_text = remainder.strip()
        primary_text = raw_text.split("|", 1)[0].strip()
        if normalized_tag == "atk":
            return ATTACK_TAG_LABELS.get(raw_text.lower(), primary_text or raw_text)
        if normalized_tag == "hit":
            if not primary_text:
                return ""
            if primary_text.startswith(("+", "-")):
                return primary_text
            return f"+{primary_text}"
        if normalized_tag == "h":
            return "Hit:"
        if normalized_tag == "dc":
            return f"DC {primary_text}"
        if normalized_tag in {"damage", "dice", "chance", "recharge", "skill", "condition", "status", "disease"}:
            return primary_text
        if normalized_tag in {
            "action",
            "background",
            "book",
            "class",
            "classfeature",
            "creature",
            "deity",
            "feat",
            "filter",
            "item",
            "language",
            "object",
            "optfeature",
            "race",
            "sense",
            "spell",
            "table",
            "trap",
            "variantrule",
            "vehicle",
        }:
            return primary_text
        return primary_text or raw_text or normalized_tag

    def _build_class_proficiency_blocks(
        self,
        value: object,
        *,
        skill_lookup: dict[str, SystemsEntryRecord] | None = None,
    ) -> list[dict[str, object]]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            return [{"kind": "text", "text": value}]
        if isinstance(value, list):
            if not value:
                return []
            if all(not isinstance(item, (dict, list)) for item in value):
                rendered = ", ".join(part for part in (str(item).strip() for item in value) if part)
                return [{"kind": "text", "text": rendered}] if rendered else []

            blocks: list[dict[str, object]] = []
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("choose"), dict):
                    choose = item.get("choose") or {}
                    raw_options = choose.get("from")
                    options: list[dict[str, str | None]] = []
                    if isinstance(raw_options, list):
                        for raw_option in raw_options:
                            label = self._humanize_skill_or_term(raw_option)
                            normalized = normalize_lookup(label)
                            linked_entry = skill_lookup.get(normalized) if skill_lookup else None
                            options.append(
                                {
                                    "label": linked_entry.title if linked_entry is not None else label,
                                    "slug": linked_entry.slug if linked_entry is not None else None,
                                }
                            )
                    blocks.append(
                        {
                            "kind": "choice",
                            "count": self._coerce_int(choose.get("count"), default=1),
                            "options": options,
                        }
                    )
                    continue
                rendered = self._format_proficiency_block_text(item)
                if rendered:
                    blocks.append({"kind": "text", "text": rendered})
            return blocks
        rendered = self._format_proficiency_block_text(value)
        return [{"kind": "text", "text": rendered}] if rendered else []

    def _format_proficiency_block_text(self, value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return ", ".join(
                part for part in (self._format_proficiency_block_text(item) for item in value) if part
            )
        if isinstance(value, dict):
            parts: list[str] = []
            for key, nested_value in value.items():
                rendered = self._format_proficiency_block_text(nested_value)
                if not rendered:
                    continue
                parts.append(f"{str(key).replace('_', ' ').title()}: {rendered}")
            return "; ".join(parts)
        return str(value).strip()

    def _humanize_skill_or_term(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return " ".join(part.capitalize() for part in text.split())

    def _extract_level_from_progression_label(self, value: str) -> int:
        match = re.search(r"(\d+)", str(value or ""))
        if match is None:
            return 0
        return self._coerce_int(match.group(1), default=0)

    def _normalize_class_feature_progression_label(self, value: str) -> str:
        cleaned = str(value or "").replace(" (choose subclass feature)", "").strip()
        return normalize_lookup(cleaned)

    def _pop_matching_class_feature_entry(
        self,
        candidates: list[SystemsEntryRecord],
        label: str,
    ) -> SystemsEntryRecord | None:
        normalized_label = self._normalize_class_feature_progression_label(label)
        for index, candidate in enumerate(candidates):
            if normalize_lookup(candidate.title) == normalized_label:
                return candidates.pop(index)
        return None

    def _looks_like_ability_block(self, value: dict[str, object]) -> bool:
        return any(key in value for key in ("str", "dex", "con", "int", "wis", "cha"))

    def _strip_outer_paragraph(self, html: str) -> str:
        cleaned = html.strip()
        if cleaned.startswith("<p>") and cleaned.endswith("</p>"):
            return cleaned[3:-4].strip()
        return cleaned

    def _coerce_int(self, value: object, *, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _extract_monster_hp_average(self, value: object) -> int:
        if isinstance(value, dict):
            return self._coerce_int(value.get("average"), default=0)
        return self._coerce_int(value, default=0)

    def _extract_max_distance(self, value: object) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            distances = [int(match) for match in re.findall(r"\d+", value)]
            return max(distances) if distances else 0
        if isinstance(value, list):
            distances = [self._extract_max_distance(item) for item in value]
            return max(distances) if distances else 0
        if isinstance(value, dict):
            distances = [self._extract_max_distance(item) for item in value.values()]
            return max(distances) if distances else 0
        return 0

    def _format_speed_label(self, value: object) -> str:
        if isinstance(value, (int, float)):
            return f"{int(value)} ft."
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            parts: list[str] = []
            for movement_type in ("walk", "burrow", "climb", "fly", "swim"):
                if movement_type not in value:
                    continue
                movement_value = value[movement_type]
                if movement_value is True:
                    rendered_value = "equal to walking speed"
                else:
                    distance = self._extract_max_distance(movement_value)
                    rendered_value = f"{distance} ft." if distance else str(movement_value).strip()
                parts.append(f"{movement_type.title()} {rendered_value}".strip())
            return ", ".join(parts)
        return ""
