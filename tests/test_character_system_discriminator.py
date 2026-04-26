from __future__ import annotations

from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
from player_wiki.system_policy import DND_5E_SYSTEM_CODE, XIANXIA_SYSTEM_CODE


def _minimal_definition_payload(**overrides):
    payload = {
        "campaign_slug": "linden-pass",
        "character_slug": "system-marker",
        "name": "System Marker",
        "status": "active",
    }
    payload.update(overrides)
    return payload


def test_character_definition_defaults_legacy_payloads_to_dnd5e_system():
    definition = CharacterDefinition.from_dict(_minimal_definition_payload())

    assert definition.system == DND_5E_SYSTEM_CODE
    assert definition.to_dict()["system"] == DND_5E_SYSTEM_CODE


def test_character_definition_normalizes_explicit_xianxia_system_aliases():
    definition = CharacterDefinition.from_dict(_minimal_definition_payload(system="xianxia"))

    assert definition.system == XIANXIA_SYSTEM_CODE
    assert definition.to_dict()["system"] == XIANXIA_SYSTEM_CODE

    alias_definition = CharacterDefinition.from_dict(_minimal_definition_payload(system_code="xianxia"))
    assert alias_definition.system == XIANXIA_SYSTEM_CODE
    assert alias_definition.to_dict()["system"] == XIANXIA_SYSTEM_CODE


def test_native_dnd5e_normalizer_leaves_xianxia_definitions_untouched():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            profile={"realm": "Mortal"},
            stats={
                "attributes": {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1},
                "durability": {"hp_max": 10, "stance_max": 10},
            },
            source={"source_type": "xianxia_character_definition"},
        )
    )

    normalized = normalize_definition_to_native_model(definition)

    assert normalized.to_dict() == definition.to_dict()
