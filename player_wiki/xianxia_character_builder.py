from __future__ import annotations

from typing import Any

from .auth_store import isoformat, utcnow
from .character_builder import CharacterBuildError
from .character_models import CharacterDefinition, CharacterImportMetadata
from .repository import slugify
from .system_policy import XIANXIA_SYSTEM_CODE
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_ENERGY_KEYS,
    validate_xianxia_definition_payload,
)

XIANXIA_CHARACTER_BUILDER_VERSION = "2026-04-26.01"
XIANXIA_CHARACTER_CREATE_SOURCE_PATH = "builder://xianxia-create"


def build_xianxia_character_create_context(
    form_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = _normalize_xianxia_create_values(form_values or {})
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
        "attribute_keys": list(XIANXIA_ATTRIBUTE_KEYS),
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
            "xianxia": {},
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


def _normalize_xianxia_create_values(values: dict[str, Any]) -> dict[str, str]:
    return {
        "name": " ".join(str(values.get("name") or "").split()).strip(),
        "character_slug": slugify(str(values.get("character_slug") or "").strip()),
    }
