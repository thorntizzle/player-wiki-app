from __future__ import annotations

import pytest

from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
from player_wiki.character_service import (
    CharacterStateValidationError,
    build_initial_state,
    merge_state_with_definition,
    validate_state,
)
from player_wiki.system_policy import DND_5E_SYSTEM_CODE, XIANXIA_SYSTEM_CODE
from player_wiki.xianxia_character_model import (
    XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION,
    XIANXIA_CHARACTER_STATE_SCHEMA_VERSION,
    XIANXIA_DEFINITION_FIELD_KEYS,
    XIANXIA_STATE_FIELD_KEYS,
    XianxiaDefinitionValidationError,
    derive_xianxia_actions_per_turn,
    derive_xianxia_check_formula_strings,
    derive_xianxia_defense,
    derive_xianxia_effort_damage_strings,
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
                    "defense": 99,
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
    assert derive_xianxia_defense(attributes=xianxia["attributes"], manual_armor_bonus=2) == 15
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


def test_xianxia_definition_normalizes_karmic_constraint_approval_fields():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system=XIANXIA_SYSTEM_CODE,
            xianxia={
                "variants": [
                    {
                        "type": "Karmic Constraint",
                        "name": "Falling Palm Oath",
                        "gm_approval_notes": "  Approved by the GM for the duel.  ",
                        "approved_at": " 2026-04-25T19:30:00-04:00 ",
                    },
                    {
                        "variant_type": "karmic_constraints",
                        "name": "Sect-Binding Revision",
                        "status": "Denied",
                        "approval_required": False,
                        "approval_note": "Too binding for this rank.",
                        "gm_reviewed_at": "2026-04-26 09:15",
                    },
                ]
            },
        )
    )

    variants = definition.to_dict()["xianxia"]["variants"]

    assert variants[0] == {
        "type": "Karmic Constraint",
        "name": "Falling Palm Oath",
        "gm_approval_notes": "  Approved by the GM for the duel.  ",
        "approved_at": " 2026-04-25T19:30:00-04:00 ",
        "variant_type": "karmic_constraint",
        "approval_required": True,
        "approval_status": "pending",
        "approval_notes": "Approved by the GM for the duel.",
        "approval_timestamp": "2026-04-25T19:30:00-04:00",
    }
    assert variants[1]["variant_type"] == "karmic_constraint"
    assert variants[1]["approval_required"] is True
    assert variants[1]["approval_status"] == "rejected"
    assert variants[1]["status"] == "Denied"
    assert variants[1]["approval_notes"] == "Too binding for this rank."
    assert variants[1]["approval_timestamp"] == "2026-04-26 09:15"


def test_xianxia_definition_normalizes_ascendant_art_approval_fields():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system=XIANXIA_SYSTEM_CODE,
            xianxia={
                "variants": [
                    {
                        "variant_type": "ascendant_art",
                        "name": "Skyfire Crown",
                        "gm_note": "Approved as a temporary ascendant art.",
                        "gm_approved_at": "2026-04-25T20:00:00-04:00",
                    },
                    {
                        "type": "Ascendant Arts",
                        "name": "Moonlit Crown",
                        "request_status": "Denied",
                        "approval_required": False,
                    },
                ]
            },
        )
    )

    variants = definition.to_dict()["xianxia"]["variants"]

    assert variants[0] == {
        "variant_type": "ascendant_art",
        "name": "Skyfire Crown",
        "gm_note": "Approved as a temporary ascendant art.",
        "gm_approved_at": "2026-04-25T20:00:00-04:00",
        "approval_required": True,
        "approval_status": "pending",
        "approval_notes": "Approved as a temporary ascendant art.",
        "approval_timestamp": "2026-04-25T20:00:00-04:00",
    }
    assert variants[1]["variant_type"] == "ascendant_art"
    assert variants[1]["approval_required"] is True
    assert variants[1]["approval_status"] == "rejected"
    assert variants[1]["request_status"] == "Denied"


def test_xianxia_definition_normalizes_dao_immolating_use_approval_fields():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system=XIANXIA_SYSTEM_CODE,
            xianxia={
                "dao_immolating_records": {
                    "prepared": [{"name": "Ashen Bell"}],
                    "history": [
                        {"name": "River-Cleaving Spark"},
                        {
                            "name": "Sect-Burning Vow",
                            "status": "Denied",
                            "approval_required": False,
                            "approval_notes": "Rejected because the use was too broad.",
                            "approved_at": "2026-04-26T10:00:00-04:00",
                        },
                    ],
                }
            },
        )
    )

    dao_immolating = definition.to_dict()["xianxia"]["dao_immolating_techniques"]

    assert dao_immolating["prepared"] == [{"name": "Ashen Bell"}]
    assert dao_immolating["use_history"][0] == {
        "name": "River-Cleaving Spark",
        "approval_required": True,
        "approval_status": "pending",
        "insight_cost": 10,
        "one_use": True,
    }
    assert dao_immolating["use_history"][1]["approval_required"] is True
    assert dao_immolating["use_history"][1]["approval_status"] == "rejected"
    assert dao_immolating["use_history"][1]["insight_cost"] == 10
    assert dao_immolating["use_history"][1]["one_use"] is True
    assert dao_immolating["use_history"][1]["status"] == "Denied"
    assert dao_immolating["use_history"][1]["approval_notes"] == "Rejected because the use was too broad."
    assert dao_immolating["use_history"][1]["approval_timestamp"] == "2026-04-26T10:00:00-04:00"


def test_xianxia_definition_normalizes_used_dao_immolating_history_fields():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system=XIANXIA_SYSTEM_CODE,
            xianxia={
                "dao_immolating_techniques": {
                    "use_history": [
                        {
                            "name": "Ash-Bright Final Word",
                            "approval_status": "approved",
                            "use_status": "spent",
                            "spent_insight": "10",
                            "use_notes": "Used once against the jade magistrate.",
                        }
                    ],
                }
            },
        )
    )

    used_record = definition.to_dict()["xianxia"]["dao_immolating_techniques"]["use_history"][0]

    assert used_record["approval_required"] is True
    assert used_record["approval_status"] == "approved"
    assert used_record["insight_cost"] == 10
    assert used_record["one_use"] is True
    assert used_record["used"] is True
    assert used_record["one_use_status"] == "used"
    assert used_record["insight_spent"] == 10
    assert used_record["use_notes"] == "Used once against the jade magistrate."


def test_xianxia_definition_normalizes_optional_prepared_dao_immolating_notes():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system=XIANXIA_SYSTEM_CODE,
            xianxia={
                "dao_immolating_techniques": {
                    "prepared": [
                        "Ashen Bell",
                        {
                            "title": "Star-Severing Promise",
                            "prepared_notes": "  Prepared for later GM approval.  ",
                            "approval_required": False,
                        },
                        {"notes": "A nameless one-use vow to finish at the table."},
                    ],
                    "use_history": [],
                }
            },
        )
    )

    prepared_records = definition.to_dict()["xianxia"]["dao_immolating_techniques"]["prepared"]

    assert prepared_records == [
        {"name": "Ashen Bell"},
        {
            "name": "Star-Severing Promise",
            "approval_required": False,
            "notes": "Prepared for later GM approval.",
        },
        {"notes": "A nameless one-use vow to finish at the table."},
    ]
    assert "approval_status" not in prepared_records[1]


def test_xianxia_definition_normalizes_optional_prepared_dao_immolating_use_reference():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system=XIANXIA_SYSTEM_CODE,
            xianxia={
                "dao_immolating_techniques": {
                    "prepared": [{"name": "Dawn Ash Mercy"}],
                    "use_history": [
                        {
                            "name": "Dawn Ash Mercy",
                            "request_type": "dao_immolating_use",
                            "request_source": "prepared",
                            "prepared_index": "0",
                            "prepared_name": "  Dawn Ash Mercy  ",
                            "preparation_notes": "  Prepared before the duel.  ",
                        }
                    ],
                }
            },
        )
    )

    use_record = definition.to_dict()["xianxia"]["dao_immolating_techniques"]["use_history"][0]

    assert use_record["request_source"] == "prepared"
    assert use_record["prepared_record_index"] == 0
    assert use_record["prepared_record_name"] == "Dawn Ash Mercy"
    assert use_record["prepared_record_notes"] == "Prepared before the duel."
    assert use_record["approval_required"] is True
    assert use_record["approval_status"] == "pending"
    assert use_record["insight_cost"] == 10
    assert use_record["one_use"] is True
    assert "prepared_index" not in use_record
    assert "prepared_name" not in use_record
    assert "preparation_notes" not in use_record


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


@pytest.mark.parametrize(
    ("realm", "expected_actions"),
    (
        ("Mortal", 2),
        ("Immortal", 3),
        ("Divine", 4),
    ),
)
def test_xianxia_action_count_is_derived_from_realm(realm: str, expected_actions: int):
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "realm": realm,
                "actions_per_turn": 99,
                "action_count": "99",
            },
        )
    )

    xianxia = definition.to_dict()["xianxia"]

    assert derive_xianxia_actions_per_turn(realm) == expected_actions
    assert xianxia["realm"] == realm
    assert xianxia["actions_per_turn"] == expected_actions


def test_xianxia_effort_damage_strings_use_canonical_dice_and_effort_labels():
    assert derive_xianxia_effort_damage_strings() == {
        "basic": "1d4 + Basic",
        "weapon": "1d6 + Weapon",
        "guns_explosive": "1d8 + Guns/Explosive",
        "magic": "1d10 + Magic",
        "ultimate": "1d12 + Ultimate",
    }


def test_xianxia_check_formula_strings_use_gm_clarified_formula():
    assert derive_xianxia_check_formula_strings() == {
        "formula": "1d20 + Attribute + Realm modifier + situational modifiers",
        "spend_bonus": "+1d6",
        "spend_bonus_detail": "per spent Energy/Yin/Yang point",
        "summary": (
            "1d20 + Attribute + Realm modifier + situational modifiers, "
            "plus +1d6 per spent Energy/Yin/Yang point."
        ),
    }


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
        attacks=[{"name": "Duel Strike"}],
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
            "statuses": [{"name": "Burn"}],
            "attacks": [{"name": "Duel Strike"}],
            "target_effects": [{"target": "Bandit", "effect": "sealed"}],
            "action_resolution": {"last_roll": 20},
        },
    )

    errors = xianxia_definition_validation_errors(payload)

    assert not any("xianxia.actions_per_turn" in error for error in errors)
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
    assert (
        "xianxia.statuses is not valid Xianxia definition data. "
        "Status functionality belongs to a future combat-state shape."
    ) in errors
    assert (
        "xianxia.attacks is not valid Xianxia definition data. "
        "Attacks and attack resolution belong to a future combat automation shape."
    ) in errors
    assert (
        "xianxia.target_effects is not valid Xianxia definition data. "
        "Target effects belong to a future combat-state shape."
    ) in errors
    assert (
        "xianxia.action_resolution is not valid Xianxia definition data. "
        "Action resolution belongs to a future combat automation shape."
    ) in errors
    assert (
        "attacks is not valid Xianxia definition data. "
        "Attacks and attack resolution belong to a future combat automation shape."
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


def test_dnd5e_definition_load_preserves_existing_definition_fields():
    payload = _minimal_definition_payload(
        system="dnd5e",
        profile={
            "class_level_text": "Sorcerer 5",
            "classes": [{"class_name": "Sorcerer", "subclass_name": "Wild Surge", "level": 5}],
            "species": "Human",
            "background": "Courier",
        },
        stats={
            "max_hp": 38,
            "armor_class": 14,
            "proficiency_bonus": 3,
            "ability_scores": {
                "str": {"score": 10, "modifier": 0, "save_bonus": 0},
                "dex": {"score": 14, "modifier": 2, "save_bonus": 2},
                "con": {"score": 14, "modifier": 2, "save_bonus": 5},
                "int": {"score": 12, "modifier": 1, "save_bonus": 1},
                "wis": {"score": 12, "modifier": 1, "save_bonus": 1},
                "cha": {"score": 18, "modifier": 4, "save_bonus": 7},
            },
        },
        skills=[{"name": "Arcana", "bonus": 7, "proficiency_level": "proficient"}],
        proficiencies={
            "armor": [],
            "weapons": ["Daggers", "Light Crossbows", "Quarterstaffs"],
            "tools": ["Navigator's Tools"],
            "languages": ["Common", "Elvish"],
        },
        attacks=[
            {
                "name": "Crossbow, Light",
                "category": "ranged weapon",
                "attack_bonus": 5,
                "damage": "1d8+2 piercing",
                "notes": "Ammunition, loading, range 80/320.",
            }
        ],
        features=[
            {
                "name": "Wild Surge",
                "category": "class_feature",
                "tracker_ref": "wild-die",
                "description_markdown": "A volatile spark that can tilt a spell once each rest.",
            }
        ],
        spellcasting={
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [{"level": 1, "max_slots": 4}],
            "spells": [{"name": "Message", "source": "Sample Rules"}],
        },
        equipment_catalog=[{"id": "light-crossbow-1", "name": "Light Crossbow", "is_equipped": True}],
        reference_notes={"additional_notes_markdown": "Route notes."},
        resource_templates=[
            {
                "id": "sorcery-points",
                "label": "Sorcery Points",
                "max": 5,
                "reset_on": "long_rest",
            }
        ],
        source={"sheet_name": "System Marker", "imported_from": "System Marker.md"},
        xianxia={
            "realm": "Immortal",
            "martial_arts": [{"name": "Heavenly Palm"}],
        },
    )

    loaded = CharacterDefinition.from_dict(payload).to_dict()

    assert loaded["system"] == DND_5E_SYSTEM_CODE
    assert "xianxia" not in loaded
    for field in (
        "profile",
        "stats",
        "skills",
        "attacks",
        "features",
        "spellcasting",
        "equipment_catalog",
        "reference_notes",
        "resource_templates",
        "source",
    ):
        assert loaded[field] == payload[field]
    assert loaded["proficiencies"] == {
        "armor": [],
        "weapons": ["Daggers", "Light Crossbows", "Quarterstaffs"],
        "tools": ["Navigator's Tools"],
        "languages": ["Common", "Elvish"],
        "tool_expertise": [],
    }


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


def test_xianxia_state_normalizes_requirement_sketch_aliases_without_deferred_combat_state():
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
                "dying_rounds_remaining": 4,
                "statuses": [{"name": "Burn"}],
                "status_effects": [{"name": "Poison"}],
                "attacks": [{"name": "Duel Strike"}],
                "targets": [{"name": "Bandit"}],
                "target_effects": [{"target": "Bandit", "effect": "sealed"}],
                "action_resolution": {"last_roll": 20},
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
    for deferred_key in (
        "dying",
        "dying_rounds_remaining",
        "statuses",
        "status_effects",
        "attacks",
        "targets",
        "target_effects",
        "action_resolution",
    ):
        assert deferred_key not in xianxia_state


def test_xianxia_state_normalization_clamps_mutable_pools_to_current_maxima():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "energy_maxima": {"jing": 2, "qi": 1, "shen": 0},
                "yin_yang": {"yin_max": 1, "yang_max": 3},
                "dao_max": 3,
                "durability": {"hp_max": 10, "stance_max": 8},
            },
        )
    )

    state = validate_state(
        definition,
        {
            "status": "active",
            "vitals": {"current_hp": "99", "temp_hp": "-4"},
            "inventory": [],
            "currency": {},
            "attunement": {},
            "notes": {},
            "xianxia": {
                "vitals": {"current_stance": "22", "temp_stance": "-3"},
                "energies": {
                    "jing": {"current": "9"},
                    "qi": {"current": "-1"},
                    "shen": {"current": "6"},
                },
                "yin_yang": {"yin_current": "7", "yang_current": "-2"},
                "dao": {"current": "8"},
            },
        },
    )

    assert state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 0,
        "current_stance": 8,
        "temp_stance": 0,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 0}
    assert state["xianxia"]["dao"] == {"current": 3}


def test_merge_xianxia_state_with_definition_clamps_existing_pools_when_maxima_shrink():
    original_definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "energy_maxima": {"jing": 5, "qi": 4, "shen": 3},
                "yin_yang": {"yin_max": 4, "yang_max": 4},
                "dao_max": 3,
                "durability": {"hp_max": 20, "stance_max": 18},
            },
        )
    )
    smaller_definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="xianxia",
            xianxia={
                "energy_maxima": {"jing": 2, "qi": 1, "shen": 1},
                "yin_yang": {"yin_max": 1, "yang_max": 2},
                "dao_max": 3,
                "durability": {"hp_max": 12, "stance_max": 9},
            },
        )
    )
    state = build_initial_state(original_definition)
    state["vitals"]["current_hp"] = 19
    state["xianxia"]["vitals"]["current_hp"] = 19
    state["xianxia"]["vitals"]["current_stance"] = 17
    state["xianxia"]["energies"]["jing"]["current"] = 5
    state["xianxia"]["energies"]["qi"]["current"] = 4
    state["xianxia"]["energies"]["shen"]["current"] = 3
    state["xianxia"]["yin_yang"] = {"yin_current": 4, "yang_current": 4}
    state["xianxia"]["dao"] = {"current": 3}

    merged_state = merge_state_with_definition(smaller_definition, state)

    assert merged_state["vitals"]["current_hp"] == 12
    assert merged_state["xianxia"]["vitals"]["current_hp"] == 12
    assert merged_state["xianxia"]["vitals"]["current_stance"] == 9
    assert merged_state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert merged_state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 2}
    assert merged_state["xianxia"]["dao"] == {"current": 3}


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


def test_dnd5e_state_validation_still_rejects_hp_above_maximum():
    definition = CharacterDefinition.from_dict(
        _minimal_definition_payload(
            system="dnd5e",
            stats={"max_hp": 12},
        )
    )

    with pytest.raises(
        CharacterStateValidationError,
        match="current_hp must be between 0 and 12",
    ):
        validate_state(
            definition,
            {
                "status": "active",
                "vitals": {"current_hp": 13, "temp_hp": 0},
                "resources": [],
                "spell_slots": [],
                "inventory": [],
                "currency": {},
                "attunement": {},
                "notes": {},
            },
        )
