from __future__ import annotations

import player_wiki.character_editor as character_editor
from player_wiki.character_models import CharacterDefinition


def _minimal_artificer_definition(spells: list[dict[str, object]]) -> CharacterDefinition:
    return CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="test-artificer",
        name="Test Artificer",
        status="active",
        profile={
            "class_level_text": "Artificer 5",
            "classes": [
                {
                    "row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                }
            ],
        },
        stats={
            "proficiency_bonus": 3,
            "ability_scores": {
                "int": {"score": 16, "modifier": 3},
            },
        },
        skills=[],
        proficiencies={},
        attacks=[],
        features=[],
        spellcasting={
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 2},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                }
            ],
            "spells": spells,
        },
        equipment_catalog=[],
        reference_notes={},
        resource_templates=[],
        source={},
    )


def test_normalize_spell_management_payload_prepared_mode_marks_only_prepared_spells_prepared():
    payload, _, _ = character_editor._normalize_spell_management_payload(
        raw_spell_payload={
            "name": "Magic Missile",
            "level": 1,
            "mark": "",
            "source": "Artificer",
        },
        spell_catalog={},
        mode="prepared",
        class_name="Artificer",
    )
    assert payload["mark"] == ""
    assert payload["is_always_prepared"] is False

    marked_payload, _, _ = character_editor._normalize_spell_management_payload(
        raw_spell_payload={
            "name": "Cure Wounds",
            "level": 1,
            "mark": "P",
            "source": "Artificer",
        },
        spell_catalog={},
        mode="prepared",
        class_name="Artificer",
    )
    assert marked_payload["mark"] == "Prepared"
    assert marked_payload["is_always_prepared"] is False

    always_prepared_payload, _, _ = character_editor._normalize_spell_management_payload(
        raw_spell_payload={
            "name": "Magic Missile",
            "level": 1,
            "mark": "",
            "is_always_prepared": True,
            "source": "Artificer (Always Prepared)",
        },
        spell_catalog={},
        mode="prepared",
        class_name="Artificer",
    )
    assert always_prepared_payload["mark"] == "Prepared"
    assert always_prepared_payload["is_always_prepared"] is True


def test_prepared_spell_management_context_excludes_unmarked_imported_rows_from_prepared_count():
    definition = _minimal_artificer_definition(
        [
            {
                "name": "Magic Missile",
                "level": 1,
                "mark": "",
                "source": "Artificer",
                "class_row_id": "class-row-1",
            },
            {
                "name": "Cure Wounds",
                "level": 1,
                "mark": "P",
                "source": "Artificer",
                "class_row_id": "class-row-1",
            },
            {
                "name": "Thunderwave",
                "level": 1,
                "mark": "",
                "is_always_prepared": True,
                "source": "Artificer (Always Prepared)",
                "class_row_id": "class-row-1",
            },
        ]
    )

    manager = character_editor.build_character_spell_management_context(definition, spell_catalog={})
    section = dict((manager or {}).get("sections", [])[0])
    rows_by_name = {str(row.get("name") or ""): row for row in list(section.get("rows") or [])}

    assert section["current_prepared_count"] == 1
    assert section["target_prepared_count"] == 5
    assert ("Prepared spells", "1 / 5") in {
        (count["label"], count["value"]) for count in list(section.get("counts") or [])
    }
    assert "Prepared" not in rows_by_name["Magic Missile"]["badges"]
    assert "Prepared" in rows_by_name["Cure Wounds"]["badges"]
    assert "Always prepared" in rows_by_name["Thunderwave"]["badges"]
