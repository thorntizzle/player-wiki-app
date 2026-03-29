from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .auth_store import isoformat, utcnow
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

CHARACTER_BUILDER_VERSION = "2026-03-29.5"
PHB_SOURCE_ID = "PHB"
DEFAULT_EXPERIENCE_MODEL = "Milestone"
DEFAULT_ABILITY_SCORE = 10

ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")
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
SPELLCASTING_ABILITY_BY_CLASS = {
    "Bard": "Charisma",
    "Cleric": "Wisdom",
    "Druid": "Wisdom",
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
) -> dict[str, Any]:
    values = dict(form_values or {})
    class_options = _list_phb_entries(systems_service, campaign_slug, "class")
    species_options = _list_phb_entries(systems_service, campaign_slug, "race")
    background_options = _list_phb_entries(systems_service, campaign_slug, "background")
    feat_options = _list_phb_entries(systems_service, campaign_slug, "feat")
    item_catalog = _build_item_catalog(_list_phb_entries(systems_service, campaign_slug, "item"))
    spell_catalog = _build_spell_catalog(_list_phb_entries(systems_service, campaign_slug, "spell"))

    selected_class = _resolve_selected_entry(class_options, values.get("class_slug", ""))
    selected_species = _resolve_selected_entry(species_options, values.get("species_slug", ""))
    selected_background = _resolve_selected_entry(background_options, values.get("background_slug", ""))

    subclass_options = _list_subclass_options(systems_service, campaign_slug, selected_class)
    selected_subclass = _resolve_selected_entry(subclass_options, values.get("subclass_slug", ""))

    class_progression = (
        systems_service.build_class_feature_progression_for_class_entry(campaign_slug, selected_class)
        if selected_class is not None
        else []
    )
    subclass_progression = (
        systems_service.build_subclass_feature_progression_for_subclass_entry(campaign_slug, selected_subclass)
        if selected_subclass is not None
        else []
    )
    requires_subclass = _class_requires_subclass_at_level_one(selected_class, class_progression)

    preview_values = _normalize_preview_values(values)
    equipment_groups = _build_equipment_groups(
        selected_class=selected_class,
        selected_background=selected_background,
        item_catalog=item_catalog,
        values=preview_values,
    )

    choice_sections = _build_choice_sections(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        feat_options=feat_options,
        class_progression=class_progression,
        equipment_groups=equipment_groups,
        spell_catalog=spell_catalog,
        values=preview_values,
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
        "item_catalog": item_catalog,
        "spell_catalog": spell_catalog,
        "limitations": [
            "Enter final level-1 ability scores after any species bonuses.",
            "Native attack rows now cover basic PHB weapons, off-hand attacks, and key level-1 fighting-style adjustments, but a few advanced damage riders still need manual follow-up.",
            "Gold-alternative loadouts and a few class-specific spell extras still need manual follow-up.",
        ],
        "preview": preview,
    }


def build_level_one_character_definition(
    campaign_slug: str,
    builder_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    values = _normalize_preview_values(form_values or {})
    selected_class = builder_context.get("selected_class")
    selected_species = builder_context.get("selected_species")
    selected_background = builder_context.get("selected_background")
    selected_subclass = builder_context.get("selected_subclass")
    choice_sections = list(builder_context.get("choice_sections") or [])
    class_progression = list(builder_context.get("class_progression") or [])
    subclass_progression = list(builder_context.get("subclass_progression") or [])
    equipment_groups = list(builder_context.get("equipment_groups") or [])
    item_catalog = dict(builder_context.get("item_catalog") or {})
    spell_catalog = dict(builder_context.get("spell_catalog") or {})
    limitations = list(builder_context.get("limitations") or [])

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

    ability_scores = _parse_ability_scores(values)
    proficiency_bonus = 2
    fixed_proficiencies, selected_choices = _resolve_builder_choices(choice_sections, values)
    proficiencies = _build_level_one_proficiencies(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        fixed_proficiencies=fixed_proficiencies,
        selected_choices=selected_choices,
    )
    skills = _build_skills_payload(ability_scores, proficiencies["skills"], proficiency_bonus)

    selected_feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
    )
    features, resource_templates = _build_feature_payloads(
        selected_feature_entries,
        ability_scores=ability_scores,
    )
    equipment_catalog = _build_level_one_equipment_catalog(equipment_groups)
    attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=proficiencies["weapons"],
        selected_choices=selected_choices,
    )

    stats = _build_level_one_stats(
        selected_class=selected_class,
        selected_species=selected_species,
        ability_scores=ability_scores,
        skills=skills,
        proficiency_bonus=proficiency_bonus,
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
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
    )

    source_path = "builder://phb-level-1"
    source = {
        "source_path": source_path,
        "source_type": "native_character_builder",
        "imported_from": "In-app PHB Level 1 Builder",
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


def _list_phb_entries(
    systems_service: Any,
    campaign_slug: str,
    entry_type: str,
) -> list[SystemsEntryRecord]:
    library = systems_service.get_campaign_library(campaign_slug)
    if library is None:
        return []
    entries = systems_service.store.list_entries_for_campaign_source(
        campaign_slug,
        library.library_slug,
        PHB_SOURCE_ID,
        entry_type=entry_type,
        limit=None,
    )
    return [entry for entry in entries if systems_service.is_entry_enabled_for_campaign(campaign_slug, entry)]


def _list_subclass_options(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
) -> list[SystemsEntryRecord]:
    if selected_class is None:
        return []
    options = _list_phb_entries(systems_service, campaign_slug, "subclass")
    return [
        entry
        for entry in options
        if str(entry.metadata.get("class_name") or "").strip() == selected_class.title
        and str(entry.metadata.get("class_source") or "").strip().upper() == selected_class.source_id
    ]


def _resolve_selected_entry(
    options: list[SystemsEntryRecord],
    selected_slug: str,
) -> SystemsEntryRecord | None:
    cleaned_slug = str(selected_slug or "").strip()
    if cleaned_slug:
        for entry in options:
            if entry.slug == cleaned_slug:
                return entry
        return None
    return options[0] if options else None


def _entry_option(entry: SystemsEntryRecord) -> dict[str, str]:
    return {"slug": entry.slug, "title": entry.title, "source_id": entry.source_id}


def _class_requires_subclass_at_level_one(
    selected_class: SystemsEntryRecord | None,
    class_progression: list[dict[str, Any]],
) -> bool:
    if selected_class is None:
        return False
    subclass_title = str(selected_class.metadata.get("subclass_title") or "").strip()
    if not subclass_title:
        return False
    normalized_subclass_title = normalize_lookup(subclass_title)
    for group in class_progression:
        if int(group.get("level") or 0) != 1:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            label = normalize_lookup(feature_row.get("label"))
            if normalized_subclass_title and normalized_subclass_title in label:
                return True
            if "choose subclass feature" in label:
                return True
    return False


def _build_choice_sections(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    class_progression: list[dict[str, Any]],
    equipment_groups: list[dict[str, Any]],
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []

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

    equipment_fields = _build_equipment_choice_fields(equipment_groups)
    if equipment_fields:
        sections.append({"title": "Equipment Choices", "fields": equipment_fields})

    spell_fields = _build_spell_choice_fields(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        spell_catalog=spell_catalog,
        values=values,
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
    fields: list[dict[str, Any]] = []
    index = 0
    for group in class_progression:
        if int(group.get("level") or 0) != 1:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            embedded_card = dict(feature_row.get("embedded_card") or {})
            option_groups = list(embedded_card.get("option_groups") or [])
            if not option_groups:
                continue
            feature_label = str(feature_row.get("label") or "Feature").strip()
            for option_group in option_groups:
                index += 1
                field_name = f"class_option_{index}"
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
                        "group_key": field_name,
                        "kind": "optionalfeature",
                    }
                )
    return fields


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
                    "options": [_choice_option(entry.title, entry.slug) for entry in feat_options],
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


def _build_item_catalog(item_entries: list[SystemsEntryRecord]) -> dict[str, Any]:
    by_title: dict[str, SystemsEntryRecord] = {}
    for entry in item_entries:
        normalized_title = normalize_lookup(entry.title)
        if normalized_title and normalized_title not in by_title:
            by_title[normalized_title] = entry
    return {
        "entries": list(item_entries),
        "by_title": by_title,
        "phb_weapon_profiles": _load_phb_weapon_profiles(),
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


def _build_level_one_equipment_catalog(equipment_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    merged_catalog: list[dict[str, Any]] = []
    merged_index_by_key: dict[tuple[str, str, str, str, bool], int] = {}
    for spec in selected_specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        systems_ref = dict(spec.get("systems_ref") or {})
        notes = str(spec.get("notes") or "").strip()
        weight = str(spec.get("weight") or "").strip()
        is_currency_only = bool(spec.get("is_currency_only"))
        merge_key = (
            normalize_lookup(name),
            str(systems_ref.get("slug") or ""),
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
                "currency": dict(spec.get("currency") or {}),
                "is_currency_only": is_currency_only,
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


def _build_level_one_attacks(
    *,
    equipment_catalog: list[dict[str, Any]],
    item_catalog: dict[str, Any],
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    weapon_proficiencies: list[str],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    attacks: list[dict[str, Any]] = []
    attack_contexts = _build_weapon_attack_contexts(
        equipment_catalog=equipment_catalog,
        item_catalog=item_catalog,
        ability_scores=ability_scores,
        weapon_proficiencies=weapon_proficiencies,
    )
    has_archery = _has_fighting_style(selected_choices, "phb-optionalfeature-archery", "Archery")
    has_dueling = _has_fighting_style(selected_choices, "phb-optionalfeature-dueling", "Dueling")
    has_great_weapon_fighting = _has_fighting_style(
        selected_choices,
        "phb-optionalfeature-great-weapon-fighting",
        "Great Weapon Fighting",
    )
    has_two_weapon_fighting = _has_fighting_style(
        selected_choices,
        "phb-optionalfeature-two-weapon-fighting",
        "Two-Weapon Fighting",
    )
    off_hand_context = _resolve_off_hand_attack_context(attack_contexts)
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
        if has_archery and str(profile.get("type") or "").strip().upper() == "R":
            attack_bonus += 2
        damage_bonus = int(context["ability_modifier"] or 0)
        if has_dueling and _qualifies_for_dueling(context, off_hand_context=off_hand_context):
            damage_bonus += 2
        attacks.append(
            _build_weapon_attack_payload(
                context,
                attack_bonus=attack_bonus,
                damage_bonus=damage_bonus,
                notes=_build_weapon_attack_notes(
                    profile,
                    great_weapon_fighting=has_great_weapon_fighting,
                    has_shield=has_shield,
                    off_hand_context=off_hand_context,
                    show_range=not has_thrown_variant,
                    show_versatile=not has_two_handed_variant,
                ),
                index=len(attacks) + 1,
            )
        )
        if has_thrown_variant:
            attacks.append(
                _build_weapon_attack_payload(
                    context,
                    attack_bonus=attack_bonus,
                    damage_bonus=damage_bonus,
                    notes=_build_weapon_attack_notes(
                        profile,
                        great_weapon_fighting=False,
                        has_shield=has_shield,
                        off_hand_context=off_hand_context,
                        show_versatile=False,
                    ),
                    index=len(attacks) + 1,
                    name_suffix=" (thrown)",
                    category_override="ranged weapon",
                )
            )
        if has_two_handed_variant:
            two_handed_profile = dict(profile)
            two_handed_profile["damage"] = str(profile.get("versatile_damage") or "").strip()
            two_handed_attack_bonus = int(context["ability_modifier"] or 0)
            if bool(context["is_proficient"]):
                two_handed_attack_bonus += proficiency_bonus
            two_handed_damage_bonus = int(context["ability_modifier"] or 0)
            attacks.append(
                _build_weapon_attack_payload(
                    context,
                    attack_bonus=two_handed_attack_bonus,
                    damage_bonus=two_handed_damage_bonus,
                    notes=_build_weapon_attack_notes(
                        two_handed_profile,
                        great_weapon_fighting=has_great_weapon_fighting,
                        has_shield=False,
                        off_hand_context=None,
                        show_versatile=False,
                        wielded_two_handed=True,
                    ),
                    index=len(attacks) + 1,
                    name_suffix=" (two-handed)",
                    profile_override=two_handed_profile,
                )
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
        attacks.append(
            _build_weapon_attack_payload(
                off_hand_context,
                attack_bonus=off_hand_attack_bonus,
                damage_bonus=off_hand_damage_bonus,
                notes=_build_weapon_attack_notes(
                    dict(off_hand_context["profile"] or {}),
                    bonus_action=True,
                    great_weapon_fighting=False,
                    has_shield=False,
                    off_hand_context=off_hand_context,
                ),
                index=len(attacks) + 1,
                name_suffix=" (off-hand)",
            )
        )
    return attacks


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
            }
        )
    return contexts


def _build_weapon_attack_payload(
    context: dict[str, Any],
    *,
    attack_bonus: int,
    damage_bonus: int,
    notes: str,
    index: int,
    name_suffix: str = "",
    category_override: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = dict(profile_override or context["profile"] or {})
    attack_name = f"{str(context.get('attack_name') or '').strip()}{name_suffix}"
    return {
        "id": f"{slugify(attack_name)}-{index}",
        "name": attack_name,
        "category": str(category_override or _weapon_attack_category(profile)),
        "attack_bonus": attack_bonus,
        "damage": _format_weapon_damage(profile, damage_bonus),
        "damage_type": DAMAGE_TYPE_LABELS.get(str(profile.get("damage_type") or "").strip().upper(), ""),
        "notes": notes,
        "systems_ref": dict(dict(context.get("item") or {}).get("systems_ref") or {}) or None,
    }


def _resolve_off_hand_attack_context(attack_contexts: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible_contexts: list[dict[str, Any]] = []
    for context in attack_contexts:
        profile = dict(context.get("profile") or {})
        if str(profile.get("type") or "").strip().upper() != "M":
            continue
        if "L" not in set(profile.get("properties") or []):
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
    systems_ref = dict(item.get("systems_ref") or {})
    candidate_titles = [
        str(systems_ref.get("title") or "").strip(),
        str(item.get("name") or "").strip(),
    ]
    profiles = dict(item_catalog.get("phb_weapon_profiles") or {})
    for title in candidate_titles:
        profile = profiles.get(normalize_lookup(title))
        if profile is not None:
            return dict(profile)
    return None


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
    normalized_proficiencies = {normalize_lookup(value) for value in weapon_proficiencies if str(value or "").strip()}
    normalized_name = normalize_lookup(attack_name)
    weapon_category = str(profile.get("weapon_category") or "").strip().lower()
    if normalized_name in normalized_proficiencies:
        return True
    if weapon_category == "simple" and normalize_lookup("Simple Weapons") in normalized_proficiencies:
        return True
    if weapon_category == "martial" and normalize_lookup("Martial Weapons") in normalized_proficiencies:
        return True
    return False


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


def _format_weapon_damage(profile: dict[str, Any], damage_bonus: int) -> str:
    base_damage = str(profile.get("damage") or "").strip()
    if not base_damage:
        return "--"
    bonus_text = ""
    if damage_bonus > 0:
        bonus_text = f"+{damage_bonus}"
    elif damage_bonus < 0:
        bonus_text = str(damage_bonus)
    damage_type = DAMAGE_TYPE_LABELS.get(str(profile.get("damage_type") or "").strip().upper(), "").strip()
    if damage_type:
        return f"{base_damage}{bonus_text} {damage_type}"
    return f"{base_damage}{bonus_text}"


def _build_weapon_attack_notes(
    profile: dict[str, Any],
    *,
    bonus_action: bool = False,
    great_weapon_fighting: bool = False,
    has_shield: bool = False,
    off_hand_context: dict[str, Any] | None = None,
    show_range: bool = True,
    show_versatile: bool = True,
    wielded_two_handed: bool = False,
) -> str:
    properties = set(profile.get("properties") or [])
    notes: list[str] = []
    if "A" in properties:
        notes.append("Ammunition")
    if "LD" in properties:
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


def _build_spell_choice_fields(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None,
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    del selected_subclass
    if selected_class is None:
        return []
    class_name = selected_class.title
    spell_rules = LEVEL_ONE_SPELL_RULES_BY_CLASS.get(class_name)
    if not spell_rules:
        return []
    fields: list[dict[str, Any]] = []

    cantrip_options = _build_spell_options_for_class_level(class_name, "0", spell_catalog)
    if cantrip_options:
        for index in range(int(spell_rules.get("cantrip_count") or 0)):
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

    spell_mode = str(spell_rules.get("level_one_mode") or "")
    level_one_options = _build_spell_options_for_class_level(class_name, "1", spell_catalog)
    if not level_one_options:
        return fields
    if spell_mode == "wizard":
        spellbook_count = int(spell_rules.get("spellbook_count") or 0)
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

        prepared_count = _level_one_spell_selection_count(spell_rules, values)
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
        return fields

    level_one_count = _level_one_spell_selection_count(spell_rules, values)
    label_prefix = "Known Spell" if spell_mode == "known" else "Prepared Spell"
    help_text = (
        f"Choose a {class_name} spell you know."
        if spell_mode == "known"
        else f"Choose a {class_name} spell you have prepared."
    )
    for index in range(level_one_count):
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
    return fields


def _build_spell_options_for_class_level(
    class_name: str,
    level_key: str,
    spell_catalog: dict[str, Any],
) -> list[dict[str, str]]:
    titles = list(
        dict(dict(spell_catalog.get("phb_level_one_lists") or {}).get(class_name) or {}).get(str(level_key)) or []
    )
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
    spell_catalog: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any]:
    ability_scores = _coerce_ability_scores(values)
    proficiency_bonus = 2
    class_name = selected_class.title if selected_class is not None else ""
    con_modifier = _ability_modifier(ability_scores.get("con", DEFAULT_ABILITY_SCORE))
    hit_die = int(((selected_class.metadata if selected_class is not None else {}) or {}).get("hit_die", {}).get("faces") or 0)
    fixed_proficiencies, selected_choices = _resolve_builder_choices(choice_sections, values, strict=False)
    proficiencies = _build_level_one_proficiencies(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        fixed_proficiencies=fixed_proficiencies,
        selected_choices=selected_choices,
    )
    feature_entries = _collect_level_one_feature_entries(
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
    )
    equipment_catalog = _build_level_one_equipment_catalog(equipment_groups)
    attacks = _build_level_one_attacks(
        equipment_catalog=equipment_catalog,
        item_catalog={"phb_weapon_profiles": _load_phb_weapon_profiles()},
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
        weapon_proficiencies=proficiencies["weapons"],
        selected_choices=selected_choices,
    )
    spellcasting = (
        _build_level_one_spellcasting(
            selected_class=selected_class,
            selected_subclass=selected_subclass,
            ability_scores=ability_scores,
            proficiency_bonus=proficiency_bonus,
            choice_sections=choice_sections,
            selected_choices=selected_choices,
            spell_catalog=spell_catalog,
        )
        if selected_class is not None
        else {"spells": []}
    )
    feature_names = [
        str(feature.get("name") or feature.get("label") or "").strip()
        for feature in feature_entries
        if str(feature.get("name") or feature.get("label") or "").strip()
    ]
    return {
        "class_level_text": f"{class_name} 1" if class_name else "Level 1",
        "max_hp": max(hit_die + con_modifier, 1) if hit_die else 0,
        "speed": _extract_speed_label(selected_species),
        "size": _extract_size_label(selected_species),
        "proficiency_bonus": proficiency_bonus,
        "saving_throws": [_humanize_saving_throw(code) for code in _class_save_proficiencies(selected_class)],
        "languages": list(proficiencies["languages"]),
        "features": feature_names,
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
    for section in choice_sections:
        grouped_values: dict[str, list[str]] = {}
        for field in list(section.get("fields") or []):
            field_name = str(field.get("name") or "")
            group_key = str(field.get("group_key") or field_name)
            raw_value = str(values.get(field_name) or "").strip()
            allowed_values = {str(option.get("value") or "").strip() for option in list(field.get("options") or [])}
            if not raw_value:
                if strict:
                    raise CharacterBuildError(f"{field.get('label') or 'A required choice'} is required.")
                continue
            if raw_value not in allowed_values:
                if strict:
                    raise CharacterBuildError(f"{field.get('label') or 'A choice'} is not valid for the current selection.")
                continue
            if raw_value:
                grouped_values.setdefault(group_key, []).append(raw_value)
        for group_key, group_values in grouped_values.items():
            if strict and len(group_values) != len(set(group_values)):
                raise CharacterBuildError("Choose distinct options when a choice group grants more than one selection.")
            selected_choices[group_key] = group_values

    fixed_proficiencies = {
        "skills": [],
        "languages": [],
        "tools": [],
    }
    return fixed_proficiencies, selected_choices


def _build_level_one_proficiencies(
    *,
    selected_class: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    fixed_proficiencies: dict[str, list[str]],
    selected_choices: dict[str, list[str]],
) -> dict[str, list[str]]:
    del fixed_proficiencies
    armor = _dedupe_preserve_order(_extract_class_armor_proficiencies(selected_class))
    weapons = _dedupe_preserve_order(_extract_class_weapon_proficiencies(selected_class))
    tools = _dedupe_preserve_order(
        _extract_class_tool_proficiencies(selected_class)
        + _extract_fixed_tool_proficiencies(selected_species)
        + _extract_fixed_tool_proficiencies(selected_background)
    )
    languages = _dedupe_preserve_order(
        _extract_fixed_languages(selected_species)
        + _extract_fixed_languages(selected_background)
        + selected_choices.get("species_languages", [])
        + selected_choices.get("background_languages", [])
    )
    skills = _dedupe_preserve_order(
        _extract_fixed_skills(selected_species)
        + _extract_fixed_skills(selected_background)
        + selected_choices.get("class_skills", [])
        + selected_choices.get("species_skills", [])
    )
    return {
        "armor": armor,
        "weapons": weapons,
        "tools": tools,
        "languages": languages,
        "skills": skills,
    }


def _build_skills_payload(
    ability_scores: dict[str, int],
    proficient_skills: list[str],
    proficiency_bonus: int,
) -> list[dict[str, Any]]:
    proficient_lookup = {normalize_lookup(skill) for skill in proficient_skills}
    rows: list[dict[str, Any]] = []
    for normalized_skill, label in SKILL_LABELS.items():
        ability_key = SKILL_ABILITY_KEYS[normalized_skill]
        modifier = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE))
        is_proficient = normalized_skill in proficient_lookup
        rows.append(
            {
                "name": label,
                "bonus": modifier + (proficiency_bonus if is_proficient else 0),
                "proficiency_level": "proficient" if is_proficient else "none",
            }
        )
    return rows


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
) -> list[dict[str, Any]]:
    del selected_class
    feature_entries: list[dict[str, Any]] = []

    class_option_index = 0
    for group in class_progression:
        if int(group.get("level") or 0) != 1:
            continue
        for feature_row in list(group.get("feature_rows") or []):
            label = str(feature_row.get("label") or "").strip()
            if "choose subclass feature" in normalize_lookup(label):
                continue
            embedded_card = dict(feature_row.get("embedded_card") or {})
            option_groups = list(embedded_card.get("option_groups") or [])
            if option_groups:
                for option_group in option_groups:
                    class_option_index += 1
                    group_key = f"class_option_{class_option_index}"
                    selected_slug = next((slug for slug in selected_choices.get(group_key, []) if slug), "")
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
                    feature_entries.append(
                        {
                            "kind": "optionalfeature",
                            "entry": None,
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

    for group in subclass_progression:
        if int(group.get("level") or 0) != 1:
            continue
        for feature_row in list(group.get("feature_rows") or []):
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

    if selected_species is not None:
        feature_entries.extend(_extract_species_feature_entries(selected_species))
    if selected_background is not None:
        feature_entries.extend(_extract_background_feature_entries(selected_background))

    for feat_slug in selected_choices.get("species_feats", []):
        feat_title = _resolve_choice_label(choice_sections, "species_feats", feat_slug) or feat_slug
        feature_entries.append(
            {
                "kind": "feat",
                "entry": None,
                "name": feat_title,
                "label": feat_title,
                "slug": feat_slug,
            }
        )

    return feature_entries


def _build_feature_payloads(
    feature_entries: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    features: list[dict[str, Any]] = []
    resource_templates: list[dict[str, Any]] = []
    display_order = 0
    seen_feature_names: set[str] = set()

    for index, feature_entry in enumerate(feature_entries, start=1):
        feature_payload, tracker_template = _build_feature_payload(
            feature_entry,
            index=index,
            display_order=display_order,
            ability_scores=ability_scores,
        )
        if feature_payload is None:
            continue
        feature_name = str(feature_payload.get("name") or "").strip()
        normalized_name = normalize_lookup(feature_name)
        if not feature_name or normalized_name in seen_feature_names:
            continue
        seen_feature_names.add(normalized_name)
        features.append(feature_payload)
        if tracker_template is not None:
            resource_templates.append(tracker_template)
            display_order += 1
    return features, resource_templates


def _resolve_choice_label(
    choice_sections: list[dict[str, Any]],
    group_key: str,
    selected_value: str,
) -> str:
    normalized_value = str(selected_value or "").strip()
    if not normalized_value:
        return ""
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            if str(field.get("group_key") or "") != group_key:
                continue
            for option in list(field.get("options") or []):
                if str(option.get("value") or "").strip() == normalized_value:
                    return str(option.get("label") or "").strip()
    return ""


def _build_feature_payload(
    feature_entry: dict[str, Any],
    *,
    index: int,
    display_order: int,
    ability_scores: dict[str, int],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    entry = feature_entry.get("entry")
    kind = str(feature_entry.get("kind") or "")

    if isinstance(entry, SystemsEntryRecord):
        feature_name = str(entry.title or "").strip()
        feature_payload = {
            "id": f"{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": _character_feature_category(entry.entry_type),
            "source": entry.source_id,
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": _systems_ref_from_entry(entry),
        }
        tracker_template = _build_feature_tracker_template(
            feature_name,
            ability_scores=ability_scores,
            display_order=display_order,
        )
        if tracker_template is not None:
            feature_payload["tracker_ref"] = tracker_template["id"]
            feature_payload["activation_type"] = str(tracker_template.get("activation_type") or "passive")
            tracker_template.pop("activation_type", None)
        return feature_payload, tracker_template

    if kind == "optionalfeature":
        slug = str(feature_entry.get("slug") or "").strip()
        feature_name = str(feature_entry.get("label") or "").strip()
        if not slug or not feature_name:
            return None, None
        return (
            {
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
            },
            None,
        )

    if kind == "species_trait":
        feature_name = str(feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        if not feature_name or not isinstance(systems_entry, SystemsEntryRecord):
            return None, None
        return (
            {
                "id": f"{slugify(feature_name)}-{index}",
                "name": feature_name,
                "category": "species_trait",
                "source": systems_entry.source_id,
                "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
                "activation_type": "passive",
                "tracker_ref": None,
                "systems_ref": _systems_ref_from_entry(systems_entry),
            },
            None,
        )

    if kind == "background_feature":
        feature_name = str(feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        if not feature_name or not isinstance(systems_entry, SystemsEntryRecord):
            return None, None
        return (
            {
                "id": f"{slugify(feature_name)}-{index}",
                "name": feature_name,
                "category": "background_feature",
                "source": systems_entry.source_id,
                "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
                "activation_type": "passive",
                "tracker_ref": None,
                "systems_ref": _systems_ref_from_entry(systems_entry),
            },
            None,
        )

    if kind == "feat":
        slug = str(feature_entry.get("slug") or "").strip()
        feature_name = str(feature_entry.get("title") or feature_entry.get("label") or "").strip()
        if not slug or not feature_name:
            return None, None
        return (
            {
                "id": f"{slugify(feature_name)}-{index}",
                "name": feature_name,
                "category": "feat",
                "source": PHB_SOURCE_ID,
                "description_markdown": "",
                "activation_type": "passive",
                "tracker_ref": None,
                "systems_ref": {
                    "entry_key": "",
                    "entry_type": "feat",
                    "title": feature_name,
                    "slug": slug,
                    "source_id": PHB_SOURCE_ID,
                },
            },
            None,
        )

    return None, None


def _build_level_one_stats(
    *,
    selected_class: SystemsEntryRecord,
    selected_species: SystemsEntryRecord,
    ability_scores: dict[str, int],
    skills: list[dict[str, Any]],
    proficiency_bonus: int,
) -> dict[str, Any]:
    class_metadata = dict(selected_class.metadata or {})
    hit_die_faces = int((class_metadata.get("hit_die") or {}).get("faces") or 0)
    con_modifier = _ability_modifier(ability_scores["con"])
    skill_lookup = {normalize_lookup(skill["name"]): skill for skill in skills}
    passive_perception = 10 + int((skill_lookup.get("perception") or {}).get("bonus") or _ability_modifier(ability_scores["wis"]))
    passive_insight = 10 + int((skill_lookup.get("insight") or {}).get("bonus") or _ability_modifier(ability_scores["wis"]))
    passive_investigation = 10 + int((skill_lookup.get("investigation") or {}).get("bonus") or _ability_modifier(ability_scores["int"]))
    save_proficiencies = set(_class_save_proficiencies(selected_class))

    return {
        "max_hp": max(hit_die_faces + con_modifier, 1),
        "armor_class": 10 + _ability_modifier(ability_scores["dex"]),
        "initiative_bonus": _ability_modifier(ability_scores["dex"]),
        "speed": _extract_speed_label(selected_species),
        "proficiency_bonus": proficiency_bonus,
        "passive_perception": passive_perception,
        "passive_insight": passive_insight,
        "passive_investigation": passive_investigation,
        "ability_scores": {
            ability_key: {
                "score": score,
                "modifier": _ability_modifier(score),
                "save_bonus": _ability_modifier(score) + (proficiency_bonus if ability_key in save_proficiencies else 0),
            }
            for ability_key, score in ability_scores.items()
        },
    }


def _build_level_one_profile(
    *,
    name: str,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    selected_species: SystemsEntryRecord,
    selected_background: SystemsEntryRecord,
    values: dict[str, str],
) -> dict[str, Any]:
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
        "species_ref": _systems_ref_from_entry(selected_species),
        "background": selected_background.title,
        "background_ref": _systems_ref_from_entry(selected_background),
        "alignment": str(values.get("alignment") or "").strip(),
        "experience_model": str(values.get("experience_model") or DEFAULT_EXPERIENCE_MODEL).strip(),
        "size": _extract_size_label(selected_species),
        "biography_markdown": "",
        "personality_markdown": "",
    }


def _build_level_one_spellcasting(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
) -> dict[str, Any]:
    ability_name = SPELLCASTING_ABILITY_BY_CLASS.get(selected_class.title)
    if not ability_name:
        return {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "spells": [],
        }
    ability_key = next(key for key, label in ABILITY_LABELS.items() if label == ability_name)
    modifier = _ability_modifier(ability_scores[ability_key])
    spell_payloads = _build_level_one_spell_payloads(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        choice_sections=choice_sections,
        selected_choices=selected_choices,
        spell_catalog=spell_catalog,
    )
    return {
        "spellcasting_class": selected_class.title,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier,
        "spell_attack_bonus": proficiency_bonus + modifier,
        "slot_progression": list(LEVEL_ONE_SPELL_SLOTS_BY_CLASS.get(selected_class.title, [])),
        "spells": spell_payloads,
    }


def _build_level_one_spell_payloads(
    *,
    selected_class: SystemsEntryRecord,
    selected_subclass: SystemsEntryRecord | None,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    spell_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    spell_rules = LEVEL_ONE_SPELL_RULES_BY_CLASS.get(selected_class.title)
    if not spell_rules:
        return []

    spells_by_key: dict[str, dict[str, Any]] = {}
    for selected_value in selected_choices.get("spell_cantrips", []):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=selected_value,
            spell_catalog=spell_catalog,
            mark="Cantrip",
        )

    spell_mode = str(spell_rules.get("level_one_mode") or "")
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

    subclass_key = normalize_lookup(selected_subclass.title) if selected_subclass is not None else ""
    for spell_title in LEVEL_ONE_ALWAYS_PREPARED_SPELLS_BY_SUBCLASS.get(subclass_key, []):
        _add_spell_to_payloads(
            spells_by_key,
            selected_value=spell_title,
            spell_catalog=spell_catalog,
            is_always_prepared=True,
        )

    return list(spells_by_key.values())


def _add_spell_to_payloads(
    spells_by_key: dict[str, dict[str, Any]],
    *,
    selected_value: str,
    spell_catalog: dict[str, Any],
    mark: str = "",
    is_always_prepared: bool = False,
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
        spells_by_key[payload_key] = spell_payload
        return

    existing_payload["mark"] = _merge_spell_mark(
        str(existing_payload.get("mark") or "").strip(),
        mark,
    )
    if is_always_prepared:
        existing_payload["is_always_prepared"] = True


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
        "is_ritual": False,
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


def _summarize_preview_spell(spell: dict[str, Any]) -> str:
    name = str(spell.get("name") or "").strip()
    badges = []
    if bool(spell.get("is_always_prepared")):
        badges.append("Always prepared")
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


def _build_feature_tracker_template(
    feature_name: str,
    *,
    ability_scores: dict[str, int],
    display_order: int,
) -> dict[str, Any] | None:
    normalized = normalize_lookup(feature_name)
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
        return {
            "id": "rage",
            "label": "Rage",
            "category": "class_feature",
            "initial_current": 2,
            "max": 2,
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
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Bardic Inspiration",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    return None


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
