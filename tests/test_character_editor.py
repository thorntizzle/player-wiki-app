from __future__ import annotations

from types import SimpleNamespace

import pytest

import player_wiki.character_editor as character_editor
from player_wiki.character_models import CharacterDefinition, CharacterImportMetadata


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


def _spell_catalog_for_artificer(spell_names: list[str]) -> dict[str, object]:
    entries = []
    for index, spell_name in enumerate(spell_names, start=1):
        slug = f"test-spell-{index}"
        entries.append(
            SimpleNamespace(
                slug=slug,
                title=spell_name,
                source_id="TCE",
                source_page="",
                entry_key=f"dnd-5e|spell|tce|{slug}",
                entry_type="spell",
                metadata={"level": 1, "class_lists": {"TCE": ["Artificer"]}},
            )
        )
    return {
        "entries": entries,
        "by_slug": {entry.slug: entry for entry in entries},
        "by_title": {character_editor.normalize_lookup(entry.title): entry for entry in entries},
    }


def _minimal_import_metadata() -> CharacterImportMetadata:
    return CharacterImportMetadata(
        campaign_slug="linden-pass",
        character_slug="test-artificer",
        source_path="test",
        imported_at_utc="",
        parser_version="test",
        import_status="ok",
        warnings=[],
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


def test_prepared_spell_management_context_allows_existing_class_list_row_toggles():
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
                "mark": "Prepared",
                "source": "Artificer",
                "class_row_id": "class-row-1",
            },
        ]
    )
    manager = character_editor.build_character_spell_management_context(definition, spell_catalog={})
    section = dict((manager or {}).get("sections", [])[0])
    rows_by_name = {str(row.get("name") or ""): row for row in list(section.get("rows") or [])}

    assert rows_by_name["Magic Missile"]["can_toggle_prepared"] is True
    assert rows_by_name["Magic Missile"]["is_prepared"] is False
    assert rows_by_name["Magic Missile"]["can_remove"] is False
    assert rows_by_name["Cure Wounds"]["can_toggle_prepared"] is True
    assert rows_by_name["Cure Wounds"]["is_prepared"] is True
    assert rows_by_name["Cure Wounds"]["can_remove"] is False


def test_prepared_spell_management_update_enforces_prepared_limit():
    spell_names = [
        "Absorb Elements",
        "Catapult",
        "Cure Wounds",
        "Detect Magic",
        "Faerie Fire",
        "Magic Missile",
    ]
    definition = _minimal_artificer_definition(
        [
            {
                "name": spell_name,
                "level": 1,
                "mark": "Prepared" if index < 5 else "",
                "source": "Artificer",
                "class_row_id": "class-row-1",
            }
            for index, spell_name in enumerate(spell_names)
        ]
    )
    spell_catalog = _spell_catalog_for_artificer(spell_names)
    manager = character_editor.build_character_spell_management_context(
        definition,
        spell_catalog=spell_catalog,
    )
    section = dict((manager or {}).get("sections", [])[0])
    rows_by_name = {str(row.get("name") or ""): row for row in list(section.get("rows") or [])}

    assert section["current_prepared_count"] == 5
    assert section["target_prepared_count"] == 5
    with pytest.raises(character_editor.CharacterEditValidationError, match="already at the current prepared-spell count"):
        character_editor.apply_character_spell_management_edit(
            "linden-pass",
            definition,
            _minimal_import_metadata(),
            spell_catalog=spell_catalog,
            operation="update",
            spell_key=rows_by_name["Magic Missile"]["spell_key"],
            prepared_value="1",
            target_class_row_id="class-row-1",
        )
