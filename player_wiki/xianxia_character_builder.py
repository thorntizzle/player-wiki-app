from __future__ import annotations

from typing import Any

from .auth_store import isoformat, utcnow
from .character_builder import CharacterBuildError
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_service import build_initial_state
from .repository import slugify
from .system_policy import XIANXIA_SYSTEM_CODE
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    XIANXIA_ENERGY_KEYS,
    derive_xianxia_actions_per_turn,
    derive_xianxia_defense,
    normalize_xianxia_state_payload,
    validate_xianxia_definition_payload,
)
from .xianxia_equipment_inference import infer_xianxia_required_equipment

XIANXIA_CHARACTER_BUILDER_VERSION = "2026-04-26.06"
XIANXIA_CHARACTER_CREATE_SOURCE_PATH = "builder://xianxia-create"
XIANXIA_REALM_DEFAULT = "Mortal"
XIANXIA_ACTIONS_PER_TURN_DEFAULT = derive_xianxia_actions_per_turn(XIANXIA_REALM_DEFAULT)
XIANXIA_ATTRIBUTE_CREATION_POINTS = 6
XIANXIA_ATTRIBUTE_MAX_AT_CREATION = 3
XIANXIA_EFFORT_CREATION_POINTS = 5
XIANXIA_EFFORT_MAX_AT_CREATION = 3
XIANXIA_ENERGY_CREATION_POINTS = 3
XIANXIA_HP_DEFAULT_MAX = 10
XIANXIA_STANCE_DEFAULT_MAX = 10
XIANXIA_MANUAL_ARMOR_BONUS_DEFAULT = 0
XIANXIA_YIN_DEFAULT_MAX = 1
XIANXIA_YANG_DEFAULT_MAX = 1
XIANXIA_DAO_DEFAULT_CURRENT = 0
XIANXIA_DAO_DEFAULT_MAX = 3
XIANXIA_INSIGHT_DEFAULT_AVAILABLE = 0
XIANXIA_INSIGHT_DEFAULT_SPENT = 0
XIANXIA_TRAINED_SKILL_COUNT = 3
XIANXIA_STARTING_MARTIAL_ART_SLOTS = 3
XIANXIA_STARTING_MARTIAL_ART_RANKS = (
    {"key": "initiate", "label": "Initiate"},
    {"key": "novice", "label": "Novice"},
)
XIANXIA_STARTING_MARTIAL_ART_LEARNED_RANKS = {
    "initiate": ("initiate",),
    "novice": ("initiate", "novice"),
}
XIANXIA_ENERGY_LABELS = {
    "jing": "Jing",
    "qi": "Qi",
    "shen": "Shen",
}
XIANXIA_MARTIAL_ART_RANK_LABELS = {
    "initiate": "Initiate",
    "novice": "Novice",
}


def build_xianxia_character_create_context(
    form_values: dict[str, str] | None = None,
    *,
    systems_service: Any | None = None,
    campaign_slug: str = "",
) -> dict[str, Any]:
    values = _normalize_xianxia_create_values(form_values or {})
    martial_art_options = _list_xianxia_create_martial_art_options(
        systems_service,
        campaign_slug,
    )
    manual_armor_bonus = values["manual_armor_bonus"]
    defense = derive_xianxia_defense(
        attributes=values["attributes"],
        manual_armor_bonus=manual_armor_bonus,
    )
    attribute_fields = [
        {
            "key": key,
            "label": XIANXIA_ATTRIBUTE_LABELS[key],
            "input_name": _xianxia_attribute_input_name(key),
            "value": values["attributes"][key],
            "max": XIANXIA_ATTRIBUTE_MAX_AT_CREATION,
        }
        for key in XIANXIA_ATTRIBUTE_KEYS
    ]
    effort_fields = [
        {
            "key": key,
            "label": XIANXIA_EFFORT_LABELS[key],
            "input_name": _xianxia_effort_input_name(key),
            "value": values["efforts"][key],
            "max": XIANXIA_EFFORT_MAX_AT_CREATION,
        }
        for key in XIANXIA_EFFORT_KEYS
    ]
    energy_fields = [
        {
            "key": key,
            "label": XIANXIA_ENERGY_LABELS[key],
            "input_name": _xianxia_energy_input_name(key),
            "value": values["energies"][key],
            "max": XIANXIA_ENERGY_CREATION_POINTS,
        }
        for key in XIANXIA_ENERGY_KEYS
    ]
    trained_skill_values = _normalize_xianxia_create_trained_skill_values(values)
    trained_skill_fields = [
        {
            "index": index,
            "label": f"Trained Skill {index}",
            "input_name": _xianxia_trained_skill_input_name(index),
            "value": trained_skill_values[index - 1] if index <= len(trained_skill_values) else "",
        }
        for index in range(1, XIANXIA_TRAINED_SKILL_COUNT + 1)
    ]
    martial_art_values = _normalize_xianxia_create_martial_art_values(values)
    martial_art_fields = [
        {
            "index": index,
            "art_input_name": _xianxia_martial_art_slug_input_name(index),
            "rank_input_name": _xianxia_martial_art_rank_input_name(index),
            "selected_slug": (
                martial_art_values[index - 1]["slug"]
                if index <= len(martial_art_values)
                else ""
            ),
            "selected_rank": (
                martial_art_values[index - 1]["rank_key"]
                if index <= len(martial_art_values)
                else ""
            ),
        }
        for index in range(1, XIANXIA_STARTING_MARTIAL_ART_SLOTS + 1)
    ]
    return {
        "values": values,
        "defaults": {
            "realm": XIANXIA_REALM_DEFAULT,
            "actions_per_turn": XIANXIA_ACTIONS_PER_TURN_DEFAULT,
            "honor": "Honorable",
            "reputation": "Unknown",
            "hp_max": XIANXIA_HP_DEFAULT_MAX,
            "stance_max": XIANXIA_STANCE_DEFAULT_MAX,
            "manual_armor_bonus": manual_armor_bonus,
            "defense": defense,
            "yin_max": XIANXIA_YIN_DEFAULT_MAX,
            "yang_max": XIANXIA_YANG_DEFAULT_MAX,
            "dao_current": XIANXIA_DAO_DEFAULT_CURRENT,
            "dao_max": XIANXIA_DAO_DEFAULT_MAX,
            "insight_available": XIANXIA_INSIGHT_DEFAULT_AVAILABLE,
            "insight_spent": XIANXIA_INSIGHT_DEFAULT_SPENT,
        },
        "attribute_fields": attribute_fields,
        "effort_fields": effort_fields,
        "energy_fields": energy_fields,
        "trained_skill_fields": trained_skill_fields,
        "manual_armor_field": {
            "input_name": "manual_armor_bonus",
            "value": manual_armor_bonus,
            "min": 0,
        },
        "dao_field": {
            "input_name": "dao_current",
            "value": values["dao_current"],
            "min": 0,
            "max": XIANXIA_DAO_DEFAULT_MAX,
        },
        "martial_art_options": martial_art_options,
        "martial_art_option_map": _build_xianxia_martial_art_option_map(martial_art_options),
        "martial_art_fields": martial_art_fields,
        "martial_art_rank_choices": list(XIANXIA_STARTING_MARTIAL_ART_RANKS),
    }


def build_xianxia_character_definition(
    campaign_slug: str,
    create_context: dict[str, Any],
    form_values: dict[str, str] | None = None,
) -> tuple[CharacterDefinition, CharacterImportMetadata]:
    context_values = create_context.get("values")
    values = _normalize_xianxia_create_values(
        {
            **(dict(context_values) if isinstance(context_values, dict) else {}),
            **{key: str(value) for key, value in dict(form_values or {}).items()},
        }
    )

    name = str(values.get("name") or "").strip()
    if not name:
        raise CharacterBuildError("Character name is required.")
    character_slug = slugify(str(values.get("character_slug") or "").strip() or name)
    if not character_slug:
        raise CharacterBuildError("Character slug is required.")
    attribute_scores = _validate_xianxia_create_attributes(form_values or {})
    effort_scores = _validate_xianxia_create_efforts(form_values or {})
    energy_scores = _validate_xianxia_create_energies(form_values or {})
    manual_armor_bonus = _validate_xianxia_create_manual_armor_bonus(form_values or {})
    trained_skills = _validate_xianxia_create_trained_skills(form_values or {})
    martial_art_selection = _validate_xianxia_create_starting_martial_art_selection(
        form_values or {},
        create_context.get("martial_art_option_map"),
    )
    martial_arts = martial_art_selection["records"]
    required_equipment = infer_xianxia_required_equipment(
        martial_arts=martial_art_selection["options"],
        trained_skills=trained_skills,
    )
    defense = derive_xianxia_defense(
        attributes=attribute_scores,
        manual_armor_bonus=manual_armor_bonus,
    )

    created_at = isoformat(utcnow())
    definition = CharacterDefinition.from_dict(
        {
            "campaign_slug": campaign_slug,
            "character_slug": character_slug,
            "name": name,
            "status": "active",
            "system": XIANXIA_SYSTEM_CODE,
            "profile": {
                "class_level_text": "Mortal Xianxia Character",
                "realm": XIANXIA_REALM_DEFAULT,
                "honor": "Honorable",
                "reputation": "Unknown",
            },
            "stats": {},
            "skills": [],
            "proficiencies": {
                "armor": [],
                "weapons": [],
                "tools": [],
                "languages": [],
                "tool_expertise": [],
            },
            "attacks": [],
            "features": [],
            "spellcasting": {},
            "equipment_catalog": [],
            "reference_notes": {
                "additional_notes_markdown": "",
                "allies_and_organizations_markdown": "",
                "custom_sections": [],
            },
            "resource_templates": [],
            "source": {
                "source_path": XIANXIA_CHARACTER_CREATE_SOURCE_PATH,
                "source_type": "xianxia_character_builder",
                "imported_from": "In-app Xianxia Character Creator",
                "imported_at": created_at,
                "parse_warnings": [],
            },
            "xianxia": {
                "realm": XIANXIA_REALM_DEFAULT,
                "actions_per_turn": XIANXIA_ACTIONS_PER_TURN_DEFAULT,
                "attributes": attribute_scores,
                "efforts": effort_scores,
                "energies": {key: {"max": energy_scores[key]} for key in XIANXIA_ENERGY_KEYS},
                "yin_yang": {
                    "yin_max": XIANXIA_YIN_DEFAULT_MAX,
                    "yang_max": XIANXIA_YANG_DEFAULT_MAX,
                },
                "dao": {
                    "max": XIANXIA_DAO_DEFAULT_MAX,
                },
                "insight": {
                    "available": XIANXIA_INSIGHT_DEFAULT_AVAILABLE,
                    "spent": XIANXIA_INSIGHT_DEFAULT_SPENT,
                },
                "durability": {
                    "hp_max": XIANXIA_HP_DEFAULT_MAX,
                    "stance_max": XIANXIA_STANCE_DEFAULT_MAX,
                    "manual_armor_bonus": manual_armor_bonus,
                    "defense": defense,
                },
                "skills": {
                    "trained": trained_skills,
                },
                "equipment": required_equipment,
                "martial_arts": martial_arts,
                "generic_techniques": [],
                "variants": [],
                "dao_immolating_techniques": {
                    "prepared": [],
                    "use_history": [],
                },
                "approval_requests": [],
                "companions": [],
                "advancement_history": [],
            },
        }
    )
    validated_payload = validate_xianxia_definition_payload(definition.to_dict())
    definition = CharacterDefinition.from_dict(validated_payload)

    import_metadata = CharacterImportMetadata(
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        source_path=XIANXIA_CHARACTER_CREATE_SOURCE_PATH,
        imported_at_utc=created_at,
        parser_version=XIANXIA_CHARACTER_BUILDER_VERSION,
        import_status="clean",
        warnings=[],
    )
    return definition, import_metadata


def build_xianxia_character_initial_state(
    definition: CharacterDefinition,
    form_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    dao_current = _validate_xianxia_create_dao_current(form_values or {})
    initial_state = build_initial_state(definition)
    xianxia_state = dict(initial_state.get("xianxia") or {})
    xianxia_state["dao"] = {"current": dao_current}
    initial_state["xianxia"] = normalize_xianxia_state_payload(definition, xianxia_state)
    return initial_state


def _normalize_xianxia_create_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": " ".join(str(values.get("name") or "").split()).strip(),
        "character_slug": slugify(str(values.get("character_slug") or "").strip()),
        "attributes": {
            key: _normalize_xianxia_create_attribute_value(values, key)
            for key in XIANXIA_ATTRIBUTE_KEYS
        },
        "efforts": {
            key: _normalize_xianxia_create_effort_value(values, key)
            for key in XIANXIA_EFFORT_KEYS
        },
        "energies": {
            key: _normalize_xianxia_create_energy_value(values, key)
            for key in XIANXIA_ENERGY_KEYS
        },
        "manual_armor_bonus": _normalize_xianxia_create_manual_armor_bonus_value(values),
        "dao_current": _normalize_xianxia_create_dao_current_value(values),
        "trained_skills": _normalize_xianxia_create_trained_skill_values(values),
        "martial_arts": _normalize_xianxia_create_martial_art_values(values),
    }


def _validate_xianxia_create_attributes(values: dict[str, Any]) -> dict[str, int]:
    errors: list[str] = []
    missing_labels: list[str] = []
    attribute_scores: dict[str, int] = {}
    raw_attributes = values.get("attributes")
    nested_attributes = raw_attributes if isinstance(raw_attributes, dict) else {}

    unknown_keys = sorted({
        *(
            raw_key.removeprefix("attribute_")
            for raw_key in values
            if raw_key.startswith("attribute_")
            and raw_key.removeprefix("attribute_") not in XIANXIA_ATTRIBUTE_KEYS
        ),
        *(key for key in nested_attributes if key not in XIANXIA_ATTRIBUTE_KEYS),
    })
    if unknown_keys:
        errors.append(f"Unsupported Xianxia attributes: {', '.join(unknown_keys)}.")

    for key in XIANXIA_ATTRIBUTE_KEYS:
        label = XIANXIA_ATTRIBUTE_LABELS[key]
        input_name = _xianxia_attribute_input_name(key)
        if input_name in values:
            raw_value = str(values.get(input_name) or "").strip()
        elif key in nested_attributes:
            raw_value = str(nested_attributes.get(key) or "").strip()
        else:
            missing_labels.append(label)
            continue
        if raw_value == "":
            missing_labels.append(label)
            continue
        try:
            attribute_score = int(raw_value)
        except ValueError:
            errors.append(f"{label} must be a whole number.")
            continue
        if attribute_score < 0:
            errors.append(f"{label} cannot be negative.")
            continue
        if attribute_score > XIANXIA_ATTRIBUTE_MAX_AT_CREATION:
            errors.append(
                f"{label} cannot exceed {XIANXIA_ATTRIBUTE_MAX_AT_CREATION} at character creation."
            )
        attribute_scores[key] = attribute_score

    if missing_labels:
        errors.append(f"Missing Xianxia attributes: {_format_label_list(missing_labels)}.")
    if len(attribute_scores) == len(XIANXIA_ATTRIBUTE_KEYS):
        attribute_total = sum(attribute_scores.values())
        if attribute_total != XIANXIA_ATTRIBUTE_CREATION_POINTS:
            errors.append(
                "Xianxia Attributes must spend exactly "
                f"{XIANXIA_ATTRIBUTE_CREATION_POINTS} creation points; submitted total is "
                f"{attribute_total}."
            )
    if errors:
        raise CharacterBuildError(" ".join(errors))

    return {key: attribute_scores[key] for key in XIANXIA_ATTRIBUTE_KEYS}


def _validate_xianxia_create_efforts(values: dict[str, Any]) -> dict[str, int]:
    errors: list[str] = []
    missing_labels: list[str] = []
    effort_scores: dict[str, int] = {}
    raw_efforts = values.get("efforts")
    nested_efforts = raw_efforts if isinstance(raw_efforts, dict) else {}

    unknown_keys = sorted({
        *(
            raw_key.removeprefix("effort_")
            for raw_key in values
            if raw_key.startswith("effort_")
            and raw_key.removeprefix("effort_") not in XIANXIA_EFFORT_KEYS
        ),
        *(key for key in nested_efforts if key not in XIANXIA_EFFORT_KEYS),
    })
    if unknown_keys:
        errors.append(f"Unsupported Xianxia efforts: {', '.join(unknown_keys)}.")

    for key in XIANXIA_EFFORT_KEYS:
        label = XIANXIA_EFFORT_LABELS[key]
        input_name = _xianxia_effort_input_name(key)
        if input_name in values:
            raw_value = str(values.get(input_name) or "").strip()
        elif key in nested_efforts:
            raw_value = str(nested_efforts.get(key) or "").strip()
        else:
            missing_labels.append(label)
            continue
        if raw_value == "":
            missing_labels.append(label)
            continue
        try:
            effort_score = int(raw_value)
        except ValueError:
            errors.append(f"{label} must be a whole number.")
            continue
        if effort_score < 0:
            errors.append(f"{label} cannot be negative.")
            continue
        if effort_score > XIANXIA_EFFORT_MAX_AT_CREATION:
            errors.append(
                f"{label} cannot exceed {XIANXIA_EFFORT_MAX_AT_CREATION} at character creation."
            )
        effort_scores[key] = effort_score

    if missing_labels:
        errors.append(f"Missing Xianxia efforts: {_format_label_list(missing_labels)}.")
    if len(effort_scores) == len(XIANXIA_EFFORT_KEYS):
        effort_total = sum(effort_scores.values())
        if effort_total != XIANXIA_EFFORT_CREATION_POINTS:
            errors.append(
                "Xianxia Efforts must spend exactly "
                f"{XIANXIA_EFFORT_CREATION_POINTS} creation points; submitted total is "
                f"{effort_total}."
            )
    if errors:
        raise CharacterBuildError(" ".join(errors))

    return {key: effort_scores[key] for key in XIANXIA_EFFORT_KEYS}


def _validate_xianxia_create_energies(values: dict[str, Any]) -> dict[str, int]:
    errors: list[str] = []
    missing_labels: list[str] = []
    energy_scores: dict[str, int] = {}
    raw_energies = values.get("energies")
    nested_energies = raw_energies if isinstance(raw_energies, dict) else {}
    raw_energy_maxima = values.get("energy_maxima")
    nested_energy_maxima = raw_energy_maxima if isinstance(raw_energy_maxima, dict) else {}

    unknown_keys = sorted({
        *(
            raw_key.removeprefix("energy_")
            for raw_key in values
            if raw_key.startswith("energy_")
            and raw_key.removeprefix("energy_") not in XIANXIA_ENERGY_KEYS
        ),
        *(key for key in nested_energies if key not in XIANXIA_ENERGY_KEYS),
        *(key for key in nested_energy_maxima if key not in XIANXIA_ENERGY_KEYS),
    })
    if unknown_keys:
        errors.append(f"Unsupported Xianxia energies: {', '.join(unknown_keys)}.")

    for key in XIANXIA_ENERGY_KEYS:
        label = XIANXIA_ENERGY_LABELS[key]
        input_name = _xianxia_energy_input_name(key)
        if input_name in values:
            raw_value = _clean_form_value(values.get(input_name))
        elif key in nested_energy_maxima:
            raw_value = _clean_form_value(nested_energy_maxima.get(key))
        elif key in nested_energies:
            nested_energy = nested_energies.get(key)
            if isinstance(nested_energy, dict):
                raw_value = _clean_form_value(nested_energy.get("max"))
            else:
                raw_value = _clean_form_value(nested_energy)
        else:
            missing_labels.append(label)
            continue
        if raw_value == "":
            missing_labels.append(label)
            continue
        try:
            energy_score = int(raw_value)
        except ValueError:
            errors.append(f"{label} must be a whole number.")
            continue
        if energy_score < 0:
            errors.append(f"{label} cannot be negative.")
            continue
        energy_scores[key] = energy_score

    if missing_labels:
        errors.append(f"Missing Xianxia energies: {_format_label_list(missing_labels)}.")
    if len(energy_scores) == len(XIANXIA_ENERGY_KEYS):
        energy_total = sum(energy_scores.values())
        if energy_total != XIANXIA_ENERGY_CREATION_POINTS:
            errors.append(
                "Xianxia Energies must spend exactly "
                f"{XIANXIA_ENERGY_CREATION_POINTS} creation points across Jing, Qi, and Shen; "
                f"submitted total is {energy_total}."
            )
    if errors:
        raise CharacterBuildError(" ".join(errors))

    return {key: energy_scores[key] for key in XIANXIA_ENERGY_KEYS}


def _validate_xianxia_create_dao_current(values: dict[str, Any]) -> int:
    raw_value = _normalize_xianxia_create_dao_current_value(values)
    if raw_value == "":
        return XIANXIA_DAO_DEFAULT_CURRENT
    try:
        dao_current = int(raw_value)
    except ValueError:
        raise CharacterBuildError("Starting Dao must be a whole number.") from None
    if dao_current < 0:
        raise CharacterBuildError("Starting Dao cannot be negative.")
    if dao_current > XIANXIA_DAO_DEFAULT_MAX:
        raise CharacterBuildError(
            f"Starting Dao cannot exceed {XIANXIA_DAO_DEFAULT_MAX} at character creation."
        )
    return dao_current


def _validate_xianxia_create_trained_skills(values: dict[str, Any]) -> list[str]:
    trained_skills = [
        _normalize_xianxia_trained_skill_name(value)
        for value in _extract_xianxia_trained_skill_values(values)
    ]
    trained_skills = [skill for skill in trained_skills if skill]
    if len(trained_skills) != XIANXIA_TRAINED_SKILL_COUNT:
        raise CharacterBuildError(
            "Xianxia character creation requires exactly "
            f"{XIANXIA_TRAINED_SKILL_COUNT} trained skills; submitted "
            f"{len(trained_skills)}."
        )

    seen: set[str] = set()
    duplicates: list[str] = []
    for skill in trained_skills:
        marker = skill.casefold()
        if marker in seen and skill not in duplicates:
            duplicates.append(skill)
        seen.add(marker)
    if duplicates:
        raise CharacterBuildError(
            "Xianxia trained skills must be distinct; duplicates: "
            f"{_format_label_list(duplicates)}."
        )
    return trained_skills


def _validate_xianxia_create_starting_martial_arts(
    values: dict[str, Any],
    option_map: Any,
) -> list[dict[str, Any]]:
    return _validate_xianxia_create_starting_martial_art_selection(
        values,
        option_map,
    )["records"]


def _validate_xianxia_create_starting_martial_art_selection(
    values: dict[str, Any],
    option_map: Any,
) -> dict[str, list[dict[str, Any]]]:
    options_by_slug = dict(option_map or {}) if isinstance(option_map, dict) else {}
    martial_art_values = _normalize_xianxia_create_martial_art_values(values)
    selected_values = [
        value
        for value in martial_art_values
        if str(value.get("slug") or "").strip() or str(value.get("rank_key") or "").strip()
    ]
    if not selected_values:
        raise CharacterBuildError(
            "Xianxia character creation requires a starting Martial Arts package: "
            "one Novice plus one Initiate, or three Initiates."
        )
    if not options_by_slug:
        raise CharacterBuildError(
            "No enabled Xianxia Martial Art Systems entries are available for character creation."
        )

    errors: list[str] = []
    selected_records: list[dict[str, Any]] = []
    selected_options: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    duplicate_titles: list[str] = []
    for value in selected_values:
        slug = str(value.get("slug") or "").strip()
        rank_key = str(value.get("rank_key") or "").strip()
        if not slug or not rank_key:
            errors.append("Each selected starting Martial Art needs both a Martial Art and a rank.")
            continue
        option = options_by_slug.get(_normalize_martial_art_option_slug(slug))
        if option is None:
            errors.append(f"Unsupported starting Martial Art: {slug}.")
            continue
        if rank_key not in XIANXIA_MARTIAL_ART_RANK_LABELS:
            errors.append("Starting Martial Art ranks must be Initiate or Novice.")
            continue
        option_slug = str(option["slug"])
        if option_slug in seen_slugs:
            duplicate_titles.append(str(option["title"]))
            continue
        seen_slugs.add(option_slug)
        available_rank_keys = set(option.get("available_starting_rank_keys") or ())
        if rank_key not in available_rank_keys:
            errors.append(
                f"{option['title']} does not have "
                f"{XIANXIA_MARTIAL_ART_RANK_LABELS[rank_key]} rank available in Systems metadata."
            )
            continue
        selected_records.append(
            _build_xianxia_starting_martial_art_record(option, rank_key)
        )
        selected_option = dict(option)
        selected_option["current_rank_key"] = rank_key
        selected_options.append(selected_option)

    if duplicate_titles:
        errors.append(
            "Starting Martial Arts must be distinct; duplicates: "
            f"{_format_label_list(duplicate_titles)}."
        )

    rank_keys = [str(record["current_rank_key"]) for record in selected_records]
    legal_novice_package = sorted(rank_keys) == ["initiate", "novice"]
    legal_initiate_package = rank_keys == ["initiate", "initiate", "initiate"]
    if selected_records and not (legal_novice_package or legal_initiate_package):
        errors.append(
            "Starting Martial Arts must be one Novice plus one Initiate, or three Initiates."
        )
    if errors:
        raise CharacterBuildError(" ".join(errors))
    return {"records": selected_records, "options": selected_options}


def _validate_xianxia_create_manual_armor_bonus(values: dict[str, Any]) -> int:
    raw_value = _normalize_xianxia_create_manual_armor_bonus_value(values)
    if raw_value == "":
        return XIANXIA_MANUAL_ARMOR_BONUS_DEFAULT
    try:
        manual_armor_bonus = int(raw_value)
    except ValueError:
        raise CharacterBuildError("Manual armor bonus must be a whole number.") from None
    if manual_armor_bonus < 0:
        raise CharacterBuildError("Manual armor bonus cannot be negative.")
    return manual_armor_bonus


def _normalize_xianxia_create_attribute_value(values: dict[str, Any], key: str) -> str:
    raw_attributes = values.get("attributes")
    if isinstance(raw_attributes, dict) and key in raw_attributes:
        value = raw_attributes.get(key)
    else:
        value = values.get(_xianxia_attribute_input_name(key), 0)
    return str(value if value is not None else "").strip()


def _normalize_xianxia_create_effort_value(values: dict[str, Any], key: str) -> str:
    raw_efforts = values.get("efforts")
    if isinstance(raw_efforts, dict) and key in raw_efforts:
        value = raw_efforts.get(key)
    else:
        value = values.get(_xianxia_effort_input_name(key), 0)
    return str(value if value is not None else "").strip()


def _normalize_xianxia_create_energy_value(values: dict[str, Any], key: str) -> str:
    raw_energy_maxima = values.get("energy_maxima")
    if isinstance(raw_energy_maxima, dict) and key in raw_energy_maxima:
        value = raw_energy_maxima.get(key)
        return _clean_form_value(value)
    raw_energies = values.get("energies")
    if isinstance(raw_energies, dict) and key in raw_energies:
        value = raw_energies.get(key)
        if isinstance(value, dict):
            value = value.get("max")
    else:
        value = values.get(_xianxia_energy_input_name(key), 0)
    return _clean_form_value(value)


def _normalize_xianxia_create_dao_current_value(values: dict[str, Any]) -> str:
    raw_dao = values.get("dao")
    if "dao_current" in values:
        value = values.get("dao_current")
    elif isinstance(raw_dao, dict) and "current" in raw_dao:
        value = raw_dao.get("current")
    else:
        value = XIANXIA_DAO_DEFAULT_CURRENT
    return _clean_form_value(value)


def _normalize_xianxia_create_manual_armor_bonus_value(values: dict[str, Any]) -> str:
    raw_durability = values.get("durability")
    raw_armor = values.get("armor")
    if "manual_armor_bonus" in values:
        value = values.get("manual_armor_bonus")
    elif "armor_bonus" in values:
        value = values.get("armor_bonus")
    elif isinstance(raw_durability, dict) and "manual_armor_bonus" in raw_durability:
        value = raw_durability.get("manual_armor_bonus")
    elif isinstance(raw_durability, dict) and "armor_bonus" in raw_durability:
        value = raw_durability.get("armor_bonus")
    elif isinstance(raw_armor, dict) and "manual_armor_bonus" in raw_armor:
        value = raw_armor.get("manual_armor_bonus")
    elif isinstance(raw_armor, dict) and "armor_bonus" in raw_armor:
        value = raw_armor.get("armor_bonus")
    else:
        value = XIANXIA_MANUAL_ARMOR_BONUS_DEFAULT
    return _clean_form_value(value)


def _normalize_xianxia_create_trained_skill_values(values: dict[str, Any]) -> list[str]:
    raw_values = _extract_xianxia_trained_skill_values(values)
    normalized = [_normalize_xianxia_trained_skill_name(value) for value in raw_values]
    if len(normalized) < XIANXIA_TRAINED_SKILL_COUNT:
        normalized.extend([""] * (XIANXIA_TRAINED_SKILL_COUNT - len(normalized)))
    return normalized


def _normalize_xianxia_create_martial_art_values(values: dict[str, Any]) -> list[dict[str, str]]:
    raw_values = _extract_xianxia_martial_art_values(values)
    normalized = [
        {
            "slug": _normalize_martial_art_option_slug(
                raw_value.get("slug")
                if isinstance(raw_value, dict)
                else ""
            ),
            "rank_key": _normalize_xianxia_starting_martial_art_rank_key(
                raw_value.get("rank_key")
                if isinstance(raw_value, dict)
                else ""
            ),
        }
        for raw_value in raw_values
    ]
    if len(normalized) < XIANXIA_STARTING_MARTIAL_ART_SLOTS:
        normalized.extend(
            {"slug": "", "rank_key": ""}
            for _ in range(XIANXIA_STARTING_MARTIAL_ART_SLOTS - len(normalized))
        )
    return normalized[:XIANXIA_STARTING_MARTIAL_ART_SLOTS]


def _extract_xianxia_martial_art_values(values: dict[str, Any]) -> list[dict[str, Any]]:
    indexed_values: list[dict[str, Any]] = []
    for index in range(1, XIANXIA_STARTING_MARTIAL_ART_SLOTS + 1):
        slug_key = _xianxia_martial_art_slug_input_name(index)
        rank_key = _xianxia_martial_art_rank_input_name(index)
        alternate_slug_key = f"starting_martial_art_{index}_slug"
        alternate_rank_key = f"starting_martial_art_{index}_rank"
        if (
            slug_key in values
            or rank_key in values
            or alternate_slug_key in values
            or alternate_rank_key in values
        ):
            indexed_values.append(
                {
                    "slug": values.get(slug_key, values.get(alternate_slug_key, "")),
                    "rank_key": values.get(rank_key, values.get(alternate_rank_key, "")),
                }
            )
    if indexed_values:
        return indexed_values

    raw_martial_arts = values.get("martial_arts")
    if isinstance(raw_martial_arts, (list, tuple)):
        return [_coerce_xianxia_martial_art_value(value) for value in raw_martial_arts]
    if isinstance(raw_martial_arts, dict):
        return [_coerce_xianxia_martial_art_value(raw_martial_arts)]
    return []


def _coerce_xianxia_martial_art_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"slug": value, "rank_key": ""}
    systems_ref = value.get("systems_ref")
    systems_ref = systems_ref if isinstance(systems_ref, dict) else {}
    return {
        "slug": (
            value.get("slug")
            or value.get("entry_slug")
            or systems_ref.get("slug")
            or systems_ref.get("entry_slug")
            or value.get("systems_ref")
        ),
        "rank_key": (
            value.get("rank_key")
            or value.get("current_rank_key")
            or value.get("starting_rank_key")
            or value.get("rank")
            or value.get("current_rank")
        ),
    }


def _extract_xianxia_trained_skill_values(values: dict[str, Any]) -> list[Any]:
    indexed_values: list[tuple[int, Any]] = []
    for raw_key, value in values.items():
        key = str(raw_key)
        if not key.startswith("trained_skill_"):
            continue
        suffix = key.removeprefix("trained_skill_")
        if not suffix.isdecimal():
            continue
        index = int(suffix)
        if index > 0:
            indexed_values.append((index, value))
    if indexed_values:
        return [value for _, value in sorted(indexed_values)]

    if "trained_skills" in values:
        return _coerce_trained_skill_values(values.get("trained_skills"))

    raw_skills = values.get("skills")
    if isinstance(raw_skills, dict) and "trained" in raw_skills:
        return _coerce_trained_skill_values(raw_skills.get("trained"))
    return []


def _coerce_trained_skill_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _normalize_xianxia_trained_skill_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("label")
    return " ".join(str(value or "").split()).strip()


def _xianxia_attribute_input_name(key: str) -> str:
    return f"attribute_{key}"


def _xianxia_effort_input_name(key: str) -> str:
    return f"effort_{key}"


def _xianxia_energy_input_name(key: str) -> str:
    return f"energy_{key}"


def _xianxia_trained_skill_input_name(index: int) -> str:
    return f"trained_skill_{index}"


def _xianxia_martial_art_slug_input_name(index: int) -> str:
    return f"martial_art_{index}_slug"


def _xianxia_martial_art_rank_input_name(index: int) -> str:
    return f"martial_art_{index}_rank"


def _list_xianxia_create_martial_art_options(
    systems_service: Any | None,
    campaign_slug: str,
) -> list[dict[str, Any]]:
    if systems_service is None or not str(campaign_slug or "").strip():
        return []
    list_entries = getattr(systems_service, "list_enabled_entries_for_campaign", None)
    if not callable(list_entries):
        return []
    entries = [
        entry
        for entry in list_entries(campaign_slug, entry_type="martial_art", limit=None)
        if str(getattr(entry, "entry_type", "") or "").strip().lower() == "martial_art"
    ]
    custom_source_id = ""
    get_custom_source_id = getattr(systems_service, "get_campaign_custom_source_id", None)
    if callable(get_custom_source_id):
        custom_source_id = str(get_custom_source_id(campaign_slug) or "").strip()
    options = [
        _build_xianxia_martial_art_option(
            entry,
            campaign_custom_source_id=custom_source_id,
        )
        for entry in entries
    ]
    return sorted(
        options,
        key=lambda option: (
            option["sort_order"],
            option["title"].casefold(),
            option["source_id"].casefold(),
        ),
    )


def _build_xianxia_martial_art_option(
    entry: Any,
    *,
    campaign_custom_source_id: str = "",
) -> dict[str, Any]:
    metadata = dict(getattr(entry, "metadata", {}) or {})
    body = dict(getattr(entry, "body", {}) or {})
    entry_source_id = str(getattr(entry, "source_id", "") or "").strip()
    rank_records = _xianxia_martial_art_rank_records(metadata, body)
    rank_refs = {
        str(record.get("rank_key") or "").strip(): str(record.get("rank_ref") or "").strip()
        for record in rank_records
        if str(record.get("rank_key") or "").strip()
    }
    available_rank_keys = tuple(
        rank_key
        for rank_key in ("initiate", "novice")
        if rank_key in rank_refs
    )
    is_custom_martial_art = bool(
        metadata.get("xianxia_custom_martial_art")
        or metadata.get("custom_martial_art")
        or dict(body.get("xianxia_martial_art") or {}).get("xianxia_custom_martial_art")
        or (
            campaign_custom_source_id
            and entry_source_id.casefold() == campaign_custom_source_id.casefold()
        )
    )
    if is_custom_martial_art and not available_rank_keys:
        available_rank_keys = ("initiate", "novice")
        rank_refs = {
            rank_key: f"xianxia:{getattr(entry, 'slug', '')}:{rank_key}"
            for rank_key in available_rank_keys
        }
    martial_art_body = dict(body.get("xianxia_martial_art") or {})
    martial_art_style = str(
        metadata.get("xianxia_martial_art_style")
        or metadata.get("martial_art_style")
        or martial_art_body.get("style")
        or martial_art_body.get("martial_art_style")
        or ""
    ).strip()
    catalog_order = metadata.get("martial_art_catalog_order")
    try:
        sort_order = int(catalog_order)
    except (TypeError, ValueError):
        sort_order = 10000
    return {
        "slug": _normalize_martial_art_option_slug(getattr(entry, "slug", "")),
        "title": str(getattr(entry, "title", "") or "").strip(),
        "entry_key": str(getattr(entry, "entry_key", "") or "").strip(),
        "entry_type": str(getattr(entry, "entry_type", "") or "").strip(),
        "source_id": entry_source_id,
        "library_slug": str(getattr(entry, "library_slug", "") or "").strip(),
        "martial_art_style": martial_art_style,
        "available_starting_rank_keys": available_rank_keys,
        "rank_refs": rank_refs,
        "rank_records_status": str(metadata.get("rank_records_status") or "").strip(),
        "custom_martial_art": is_custom_martial_art,
        "sort_order": sort_order,
    }


def _xianxia_martial_art_rank_records(
    metadata: dict[str, Any],
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_records = metadata.get("xianxia_martial_art_rank_records")
    if raw_records is None:
        raw_records = metadata.get("martial_art_rank_records")
    martial_art_body = body.get("xianxia_martial_art")
    if not raw_records and isinstance(martial_art_body, dict):
        raw_records = (
            martial_art_body.get("xianxia_martial_art_rank_records")
            or martial_art_body.get("rank_records")
        )
    records: list[dict[str, Any]] = []
    for record in list(raw_records or []):
        if not isinstance(record, dict):
            continue
        if record.get("rank_available_in_seed") is False:
            continue
        rank_key = _normalize_xianxia_starting_martial_art_rank_key(record.get("rank_key"))
        if rank_key not in XIANXIA_MARTIAL_ART_RANK_LABELS:
            continue
        records.append({**record, "rank_key": rank_key})
    return records


def _build_xianxia_martial_art_option_map(
    options: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        _normalize_martial_art_option_slug(option.get("slug")): option
        for option in options
        if _normalize_martial_art_option_slug(option.get("slug"))
    }


def _build_xianxia_starting_martial_art_record(
    option: dict[str, Any],
    rank_key: str,
) -> dict[str, Any]:
    learned_rank_refs = [
        _rank_ref_for_starting_martial_art(option, learned_rank_key)
        for learned_rank_key in XIANXIA_STARTING_MARTIAL_ART_LEARNED_RANKS[rank_key]
    ]
    record = {
        "name": option["title"],
        "systems_ref": {
            "library_slug": option["library_slug"],
            "source_id": option["source_id"],
            "entry_key": option["entry_key"],
            "slug": option["slug"],
            "title": option["title"],
            "entry_type": option["entry_type"],
        },
        "current_rank": XIANXIA_MARTIAL_ART_RANK_LABELS[rank_key],
        "current_rank_key": rank_key,
        "learned_rank_refs": learned_rank_refs,
        "starting_package": True,
    }
    if option.get("rank_records_status"):
        record["rank_records_status"] = option["rank_records_status"]
    if option.get("custom_martial_art"):
        record["custom_martial_art"] = True
        record["xianxia_custom_martial_art"] = True
    return record


def _rank_ref_for_starting_martial_art(option: dict[str, Any], rank_key: str) -> str:
    rank_ref = str(dict(option.get("rank_refs") or {}).get(rank_key) or "").strip()
    if rank_ref:
        return rank_ref
    return f"xianxia:{option['slug']}:{rank_key}"


def _normalize_martial_art_option_slug(value: Any) -> str:
    return str(value if value is not None else "").strip().casefold()


def _normalize_xianxia_starting_martial_art_rank_key(value: Any) -> str:
    normalized = str(value if value is not None else "").strip().lower().replace(" ", "_")
    normalized = normalized.replace("-", "_")
    return normalized


def _clean_form_value(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _format_label_list(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"
