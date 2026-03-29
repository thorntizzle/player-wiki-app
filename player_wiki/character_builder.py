from __future__ import annotations

import re
from typing import Any

from .auth_store import isoformat, utcnow
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

CHARACTER_BUILDER_VERSION = "2026-03-29.1"
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

    choice_sections = _build_choice_sections(
        selected_class=selected_class,
        selected_species=selected_species,
        selected_background=selected_background,
        feat_options=feat_options,
        class_progression=class_progression,
        values=values,
    )

    preview_values = _normalize_preview_values(values)
    preview = _build_level_one_preview(
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        selected_species=selected_species,
        selected_background=selected_background,
        class_progression=class_progression,
        subclass_progression=subclass_progression,
        choice_sections=choice_sections,
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
        "limitations": [
            "Enter final level-1 ability scores after any species bonuses.",
            "This first creator slice does not yet auto-populate starting equipment, attacks, or spell selections.",
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
        ability_scores=ability_scores,
        proficiency_bonus=proficiency_bonus,
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
        attacks=[],
        features=features,
        spellcasting=spellcasting,
        equipment_catalog=[],
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
    selected_species: SystemsEntryRecord | None,
    selected_background: SystemsEntryRecord | None,
    feat_options: list[SystemsEntryRecord],
    class_progression: list[dict[str, Any]],
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
    choice_sections: list[dict[str, Any]],
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
            if strict and not raw_value:
                raise CharacterBuildError(f"{field.get('label') or 'A required choice'} is required.")
            if raw_value and raw_value not in allowed_values:
                raise CharacterBuildError(f"{field.get('label') or 'A choice'} is not valid for the current selection.")
            if raw_value:
                grouped_values.setdefault(group_key, []).append(raw_value)
        for group_key, group_values in grouped_values.items():
            if len(group_values) != len(set(group_values)):
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
    ability_scores: dict[str, int],
    proficiency_bonus: int,
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
    return {
        "spellcasting_class": selected_class.title,
        "spellcasting_ability": ability_name,
        "spell_save_dc": 8 + proficiency_bonus + modifier,
        "spell_attack_bonus": proficiency_bonus + modifier,
        "slot_progression": list(LEVEL_ONE_SPELL_SLOTS_BY_CLASS.get(selected_class.title, [])),
        "spells": [],
    }


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
