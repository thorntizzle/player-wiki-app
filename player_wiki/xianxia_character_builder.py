from __future__ import annotations

from typing import Any

from .auth_store import isoformat, utcnow
from .character_builder import CharacterBuildError
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import slugify
from .system_policy import XIANXIA_SYSTEM_CODE
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_ENERGY_KEYS,
    validate_xianxia_definition_payload,
)

XIANXIA_CHARACTER_BUILDER_VERSION = "2026-04-26.01"
XIANXIA_CHARACTER_CREATE_SOURCE_PATH = "builder://xianxia-create"
XIANXIA_ATTRIBUTE_CREATION_POINTS = 6
XIANXIA_ATTRIBUTE_MAX_AT_CREATION = 3


def build_xianxia_character_create_context(
    form_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = _normalize_xianxia_create_values(form_values or {})
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
    return {
        "values": values,
        "defaults": {
            "realm": "Mortal",
            "actions_per_turn": 2,
            "honor": "Honorable",
            "reputation": "Unknown",
            "hp_max": 10,
            "stance_max": 10,
            "manual_armor_bonus": 0,
            "defense": 10,
            "yin_max": 1,
            "yang_max": 1,
            "dao_max": 3,
            "insight_available": 0,
            "insight_spent": 0,
        },
        "attribute_fields": attribute_fields,
        "effort_keys": list(XIANXIA_EFFORT_KEYS),
        "energy_keys": list(XIANXIA_ENERGY_KEYS),
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
                "realm": "Mortal",
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
                "attributes": attribute_scores,
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


def _normalize_xianxia_create_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": " ".join(str(values.get("name") or "").split()).strip(),
        "character_slug": slugify(str(values.get("character_slug") or "").strip()),
        "attributes": {
            key: _normalize_xianxia_create_attribute_value(values, key)
            for key in XIANXIA_ATTRIBUTE_KEYS
        },
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


def _normalize_xianxia_create_attribute_value(values: dict[str, Any], key: str) -> str:
    raw_attributes = values.get("attributes")
    if isinstance(raw_attributes, dict) and key in raw_attributes:
        value = raw_attributes.get(key)
    else:
        value = values.get(_xianxia_attribute_input_name(key), 0)
    return str(value if value is not None else "").strip()


def _xianxia_attribute_input_name(key: str) -> str:
    return f"attribute_{key}"


def _format_label_list(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"
