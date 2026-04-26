from __future__ import annotations

from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
from player_wiki.character_service import build_initial_state, validate_state
from player_wiki.system_policy import DND_5E_SYSTEM_CODE, XIANXIA_SYSTEM_CODE
from player_wiki.xianxia_character_model import (
    XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION,
    XIANXIA_CHARACTER_STATE_SCHEMA_VERSION,
    XIANXIA_DEFINITION_FIELD_KEYS,
    XIANXIA_STATE_FIELD_KEYS,
    XianxiaDefinitionValidationError,
    validate_xianxia_definition_payload,
    xianxia_definition_validation_errors,
)


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


def test_xianxia_definition_normalizes_stable_definition_fields():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "realm": "immortal",
                "action_count": "3",
                "honor": "majestic",
                "reputation": "Known in the Eastern Ward",
                "attributes": {"str": 1, "dex": 2, "con": 3, "int": 0, "wis": 0, "cha": 0},
                "efforts": {
                    "basic": 1,
                    "weapon": 2,
                    "guns_explosive": 0,
                    "magic": 1,
                    "ultimate": 1,
                },
                "energy_maxima": {"jing": 2, "qi": 3, "shen": 1},
                "yin_yang": {"yin_max": "2", "yang_max": "1"},
                "dao_max": 3,
                "insight": {"available": 4, "spent": 2},
                "durability": {
                    "hp_max": 18,
                    "stance_max": 14,
                    "manual_armor_bonus": 2,
                    "defense": 15,
                },
                "skills": {"trained": ["Tea Ceremony", "Strategy", "Tea Ceremony"]},
                "equipment": {
                    "necessary_weapons": [{"name": "Jian", "reason": "Required by Heavenly Palm"}],
                    "necessary_tools": ["Calligraphy brush"],
                },
                "martial_arts": [
                    {
                        "systems_ref": {"slug": "heavenly-palm", "entry_type": "martial_art"},
                        "current_rank": "Novice",
                        "learned_rank_refs": ["xianxia:heavenly-palm:initiate"],
                    }
                ],
                "generic_techniques": [
                    {"systems_ref": {"slug": "qi-blast", "entry_type": "generic_technique"}}
                ],
                "variants": [{"variant_type": "karmic_constraint", "name": "Falling Palm Oath"}],
                "dao_immolating_records": {
                    "prepared": [{"name": "Ashen Bell"}],
                    "history": [{"name": "River-Cleaving Spark", "approval_status": "approved"}],
                },
                "approval_requests": [{"request_type": "ascendant_art", "status": "pending"}],
                "companions": [{"name": "Ink phantom", "source_ref": "xianxia:ink-stained-historian"}],
                "advancement_history": [{"action": "gather_insight", "amount": 1}],
            },
        )
    )

    xianxia = definition.to_dict()["xianxia"]

    assert tuple(xianxia) == XIANXIA_DEFINITION_FIELD_KEYS
    assert xianxia["schema_version"] == XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION
    assert xianxia["realm"] == "Immortal"
    assert xianxia["actions_per_turn"] == 3
    assert xianxia["honor"] == "Majestic"
    assert xianxia["reputation"] == "Known in the Eastern Ward"
    assert xianxia["attributes"] == {"str": 1, "dex": 2, "con": 3, "int": 0, "wis": 0, "cha": 0}
    assert xianxia["efforts"]["guns_explosive"] == 0
    assert xianxia["efforts"]["magic"] == 1
    assert xianxia["energies"] == {"jing": {"max": 2}, "qi": {"max": 3}, "shen": {"max": 1}}
    assert xianxia["yin_yang"] == {"yin_max": 2, "yang_max": 1}
    assert xianxia["dao"] == {"max": 3}
    assert xianxia["insight"] == {"available": 4, "spent": 2}
    assert xianxia["durability"] == {
        "hp_max": 18,
        "stance_max": 14,
        "manual_armor_bonus": 2,
        "defense": 15,
    }
    assert xianxia["skills"]["trained"] == ["Tea Ceremony", "Strategy"]
    assert xianxia["equipment"]["necessary_weapons"] == [
        {"name": "Jian", "reason": "Required by Heavenly Palm"}
    ]
    assert xianxia["equipment"]["necessary_tools"] == [{"name": "Calligraphy brush"}]
    assert xianxia["martial_arts"][0]["current_rank"] == "Novice"
    assert xianxia["generic_techniques"][0]["systems_ref"]["slug"] == "qi-blast"
    assert xianxia["variants"][0]["variant_type"] == "karmic_constraint"
    assert xianxia["dao_immolating_techniques"]["prepared"][0]["name"] == "Ashen Bell"
    assert xianxia["dao_immolating_techniques"]["use_history"][0]["approval_status"] == "approved"
    assert xianxia["approval_requests"][0]["status"] == "pending"
    assert xianxia["companions"][0]["name"] == "Ink phantom"
    assert xianxia["advancement_history"][0]["action"] == "gather_insight"
    assert "dying" not in xianxia


def test_xianxia_definition_accepts_requirements_sketch_top_level_aliases():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            realm="Divine",
            actions_per_turn=4,
            attributes={"str": 4, "dex": 3, "con": 2, "int": 1, "wis": 0, "cha": 0},
            efforts={"basic": 1, "weapon": 1, "guns_explosive": 1, "magic": 2, "ultimate": 3},
            energies={"jing": {"max": 5}, "qi": {"max": 4}, "shen": {"max": 3}},
            yin_max=2,
            yang_max=2,
            hp_max=24,
            stance_max=20,
            manual_armor_bonus=1,
            defense=13,
            trained_skills=["Fishing", "Court Etiquette", "Fishing"],
            necessary_weapons=["Spear"],
            necessary_tools=[{"name": "Fishing net", "reason": "Required for Fishing"}],
            martial_arts=["Heavenly Palm"],
            generic_techniques=["Qi Blast"],
            dao_max=3,
            insight_available=1,
            insight_spent=0,
        )
    )

    xianxia = definition.to_dict()["xianxia"]

    assert xianxia["realm"] == "Divine"
    assert xianxia["actions_per_turn"] == 4
    assert xianxia["attributes"]["str"] == 4
    assert xianxia["efforts"]["magic"] == 2
    assert xianxia["energies"]["jing"] == {"max": 5}
    assert xianxia["yin_yang"] == {"yin_max": 2, "yang_max": 2}
    assert xianxia["durability"]["hp_max"] == 24
    assert xianxia["durability"]["stance_max"] == 20
    assert xianxia["durability"]["manual_armor_bonus"] == 1
    assert xianxia["durability"]["defense"] == 13
    assert xianxia["skills"]["trained"] == ["Fishing", "Court Etiquette"]
    assert xianxia["equipment"]["necessary_weapons"] == [{"name": "Spear"}]
    assert xianxia["equipment"]["necessary_tools"] == [
        {"name": "Fishing net", "reason": "Required for Fishing"}
    ]
    assert xianxia["martial_arts"] == [{"name": "Heavenly Palm"}]
    assert xianxia["generic_techniques"] == [{"name": "Qi Blast"}]
    assert xianxia["dao"] == {"max": 3}
    assert xianxia["insight"] == {"available": 1, "spent": 0}


def test_xianxia_definition_validation_helpers_accept_stable_payloads():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system_code="xianxia",
            xianxia={
                "realm": "Mortal",
                "actions_per_turn": 2,
                "attributes": {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1},
                "efforts": {
                    "basic": 1,
                    "weapon": 1,
                    "guns_explosive": 1,
                    "magic": 1,
                    "ultimate": 1,
                },
                "energy_maxima": {"jing": 1, "qi": 1, "shen": 1},
                "yin_yang": {"yin_max": 1, "yang_max": 1},
                "dao_max": 3,
                "insight": {"available": 0, "spent": 0},
                "durability": {
                    "hp_max": 10,
                    "stance_max": 10,
                    "manual_armor_bonus": 0,
                    "defense": 11,
                },
                "skills": {"trained": ["Tea Ceremony"]},
                "equipment": {"necessary_weapons": [{"name": "Jian"}], "necessary_tools": []},
                "martial_arts": [{"systems_ref": {"slug": "heavenly-palm"}}],
            },
        )
    )
    payload = definition.to_dict()

    assert xianxia_definition_validation_errors(payload) == []
    assert validate_xianxia_definition_payload(payload)["xianxia"] == payload["xianxia"]


def test_xianxia_definition_validation_helpers_report_invalid_payloads():
    payload = _minimal_definition_payload(
        system="xianxia",
        xianxia={
            "realm": "Mortal",
            "actions_per_turn": 3,
            "attributes": {"str": -1},
            "efforts": {"magic": -1},
            "energy_maxima": {"jing": -1},
            "yin_yang": {"yin_max": -1},
            "dao_max": 4,
            "insight": {"available": -1},
            "durability": {"hp_max": -1, "manual_armor_bonus": -1},
            "martial_arts": [{}],
            "dying": {"rounds_remaining": 4},
        },
    )

    errors = xianxia_definition_validation_errors(payload)

    assert "xianxia.actions_per_turn must match the Mortal realm default of 2." in errors
    assert "xianxia.attributes.str cannot be negative." in errors
    assert "xianxia.efforts.magic cannot be negative." in errors
    assert "xianxia.energies.jing.max cannot be negative." in errors
    assert "xianxia.yin_yang.yin_max cannot be negative." in errors
    assert "xianxia.dao.max must be 3." in errors
    assert "xianxia.insight.available cannot be negative." in errors
    assert "xianxia.durability.hp_max cannot be negative." in errors
    assert "xianxia.durability.manual_armor_bonus cannot be negative." in errors
    assert "xianxia.martial_arts[0] must be a non-empty object." in errors
    assert (
        "xianxia.dying is not valid Xianxia definition data. "
        "Dying Rounds belong to a future combat-state shape."
    ) in errors

    try:
        validate_xianxia_definition_payload(payload)
    except XianxiaDefinitionValidationError as exc:
        assert exc.errors == errors
    else:
        raise AssertionError("Expected XianxiaDefinitionValidationError")


def test_dnd5e_definition_does_not_emit_xianxia_definition_payload():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="dnd5e",
            xianxia={"realm": "Mortal", "martial_arts": ["Heavenly Palm"]},
        )
    )

    assert definition.system == DND_5E_SYSTEM_CODE
    assert "xianxia" not in definition.to_dict()
    assert xianxia_definition_validation_errors(definition.to_dict()) == []


def test_xianxia_initial_state_defines_mutable_session_state_shape():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "energy_maxima": {"jing": 2, "qi": 3, "shen": 1},
                "yin_yang": {"yin_max": 2, "yang_max": 1},
                "durability": {"hp_max": 18, "stance_max": 14},
            },
        )
    )

    state = build_initial_state(definition)
    xianxia_state = state["xianxia"]

    assert tuple(xianxia_state) == XIANXIA_STATE_FIELD_KEYS
    assert xianxia_state["schema_version"] == XIANXIA_CHARACTER_STATE_SCHEMA_VERSION
    assert state["vitals"] == {"current_hp": 18, "temp_hp": 0}
    assert state["resources"] == []
    assert state["spell_slots"] == []
    assert xianxia_state["vitals"] == {
        "current_hp": 18,
        "temp_hp": 0,
        "current_stance": 14,
        "temp_stance": 0,
    }
    assert xianxia_state["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 3},
        "shen": {"current": 1},
    }
    assert xianxia_state["yin_yang"] == {"yin_current": 2, "yang_current": 1}
    assert xianxia_state["dao"] == {"current": 0}
    assert xianxia_state["active_stance"] is None
    assert xianxia_state["active_aura"] is None
    assert xianxia_state["inventory"] == {"enabled": False, "quantities": []}
    assert xianxia_state["notes"] == {"player_notes_markdown": ""}
    assert "dying" not in xianxia_state


def test_xianxia_state_normalizes_requirement_sketch_aliases_without_dying_rounds():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "energy_maxima": {"jing": 2, "qi": 3, "shen": 1},
                "yin_yang": {"yin_max": 2, "yang_max": 2},
                "durability": {"hp_max": 18, "stance_max": 14},
            },
        )
    )

    state = validate_state(
        definition,
        {
            "status": "active",
            "vitals": {"current_hp": "17", "temp_hp": "3"},
            "inventory": [{"id": "spirit-rice", "name": "Spirit rice", "quantity": "2"}],
            "currency": {},
            "attunement": {},
            "notes": {"player_notes_markdown": "Watch for the Azure Bell timer."},
            "xianxia": {
                "stance_current": "9",
                "stance_temp": "2",
                "energies_current": {"jing": "1", "qi": "2", "shen": "0"},
                "yin_current": "1",
                "yang_current": "2",
                "dao_current": "3",
                "active_stance": "Stone Root",
                "active_aura": {"name": "Azure Bell", "systems_ref": {"slug": "azure-bell"}},
                "dying": {"rounds_remaining": 4},
            },
        },
    )

    xianxia_state = state["xianxia"]

    assert state["vitals"] == {"current_hp": 17, "temp_hp": 3}
    assert state["resources"] == []
    assert state["spell_slots"] == []
    assert xianxia_state["vitals"] == {
        "current_hp": 17,
        "temp_hp": 3,
        "current_stance": 9,
        "temp_stance": 2,
    }
    assert xianxia_state["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 2},
        "shen": {"current": 0},
    }
    assert xianxia_state["yin_yang"] == {"yin_current": 1, "yang_current": 2}
    assert xianxia_state["dao"] == {"current": 3}
    assert xianxia_state["active_stance"] == {"name": "Stone Root"}
    assert xianxia_state["active_aura"] == {"name": "Azure Bell", "systems_ref": {"slug": "azure-bell"}}
    assert xianxia_state["inventory"] == {
        "enabled": True,
        "quantities": [{"id": "spirit-rice", "name": "Spirit rice", "quantity": 2}],
    }
    assert xianxia_state["notes"] == {"player_notes_markdown": "Watch for the Azure Bell timer."}
    assert "dying" not in xianxia_state


def test_dnd5e_initial_state_does_not_emit_xianxia_mutable_state():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="dnd5e",
            stats={"max_hp": 12},
            xianxia={"durability": {"hp_max": 18, "stance_max": 14}},
        )
    )

    state = build_initial_state(definition)

    assert state["vitals"] == {
        "current_hp": 12,
        "temp_hp": 0,
        "death_saves": {"successes": 0, "failures": 0},
    }
    assert "xianxia" not in state
