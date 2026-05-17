from __future__ import annotations

import pytest

from player_wiki.character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from player_wiki.character_service import build_initial_state
from player_wiki.character_state_service import CharacterStateService
from player_wiki.character_store import CharacterStateConflictError
from player_wiki.system_policy import DND_5E_SYSTEM_CODE, XIANXIA_SYSTEM_CODE


def _xianxia_definition(character_slug: str) -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": character_slug,
            "name": "Xianxia Test",
            "status": "active",
            "system": XIANXIA_SYSTEM_CODE,
            "xianxia": {
                "energy_maxima": {"jing": 2, "qi": 1, "shen": 0},
                "yin_yang": {"yin_max": 1, "yang_max": 1},
                "durability": {"hp_max": 10, "stance_max": 8},
            },
        }
    )


def _dnd5e_definition(character_slug: str) -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": character_slug,
            "name": "DND Test",
            "status": "active",
            "system": DND_5E_SYSTEM_CODE,
            "stats": {"max_hp": 10},
        }
    )


def _build_character_record(app, definition: CharacterDefinition, *, initial_state: dict | None = None) -> CharacterRecord:
    state_payload = initial_state or build_initial_state(definition)
    with app.app_context():
        state_store = app.extensions["character_state_store"]
        state_store.initialize_state_if_missing(
            definition,
            state_payload,
        )
        state_record = state_store.get_state(
            definition.campaign_slug,
            definition.character_slug,
        )
        assert state_record is not None

    return CharacterRecord(
        definition=definition,
        import_metadata=CharacterImportMetadata.from_dict(
            {
                "campaign_slug": definition.campaign_slug,
                "character_slug": definition.character_slug,
                "source_path": "test://state-service",
                "imported_at_utc": "2026-01-01T00:00:00Z",
                "parser_version": "test",
                "import_status": "ok",
                "warnings": [],
            }
        ),
        state_record=state_record,
    )


def _get_state_service(app) -> CharacterStateService:
    return app.extensions["character_state_service"]


def _with_state(record: CharacterRecord, state_record) -> CharacterRecord:
    return CharacterRecord(
        definition=record.definition,
        import_metadata=record.import_metadata,
        state_record=state_record,
    )


def _assert_top_level_sync(updated_record, *, expected_id: str, expected_name: str) -> None:
    inventory = updated_record.state["inventory"]
    match = next(
        (item for item in inventory if item.get("id") == expected_id),
        None,
    )
    assert match is not None
    assert match["name"] == expected_name


def test_xianxia_inventory_item_crud_preserves_legacy_tags_and_syncs_top_level_rows(app):
    initial_state = build_initial_state(_xianxia_definition("legacy-tags"))
    initial_state["xianxia"]["inventory"] = {
        "enabled": True,
        "quantities": [
            {
                "name": "Rune Ring",
                "quantity": 1,
                "tags": ["artifact", "moonstone", "sigil-mark"],
                "notes": "Legacy ring",
            }
        ],
    }
    with app.app_context():
        record = _build_character_record(app, _xianxia_definition("legacy-tags"), initial_state=initial_state)
        service = _get_state_service(app)

        added = service.add_xianxia_inventory_item(
            record,
            {
                "name": "Training Blade",
                "item_type": "Weapon",
                "quantity": "2",
                "notes": "Ceremonial steel",
                "tags": ["weapon", "ritual"],
                "catalog_ref": "sword-catalog-1",
                "systems_ref": {"slug": "training-blade", "entry_type": "artifact"},
            },
            expected_revision=record.state_record.revision,
        )

        top_level = added.state["inventory"]
        assert len(top_level) == 2
        legacy_entry = next(item for item in top_level if item["name"] == "Rune Ring")
        assert legacy_entry["legacy_tags"] == ["moonstone", "sigil-mark"]
        assert legacy_entry["tags"] == ["artifact", "moonstone", "sigil-mark"]

        row = next(item for item in added.state["xianxia"]["inventory"]["quantities"] if item["name"] == "Training Blade")
        assert row["id"] == "weapon-training-blade"
        assert row["catalog_ref"] == "sword-catalog-1"
        assert row["systems_ref"] == {"slug": "training-blade", "entry_type": "artifact"}
        assert row["equippable"] is True
        assert row["is_equipped"] is False

        top_level_row = next(
            item for item in added.state["inventory"] if item["name"] == "Training Blade"
        )
        assert top_level_row["catalog_ref"] == "sword-catalog-1"
        assert top_level_row["systems_ref"] == {"slug": "training-blade", "entry_type": "artifact"}

        _assert_top_level_sync(added, expected_id="weapon-training-blade", expected_name="Training Blade")

        updated = service.update_xianxia_inventory_quantity(
            _with_state(record, added),
            row["id"],
            expected_revision=added.revision,
            quantity=5,
        )
        weapon_row = next(
            item for item in updated.state["xianxia"]["inventory"]["quantities"] if item["name"] == "Training Blade"
        )
        assert weapon_row["quantity"] == 5
        _assert_top_level_sync(updated, expected_id="weapon-training-blade", expected_name="Training Blade")

        removed = service.remove_xianxia_inventory_item(
            _with_state(record, updated),
            row["id"],
            expected_revision=updated.revision,
        )
        assert len(removed.state["xianxia"]["inventory"]["quantities"]) == 1
        assert removed.state["xianxia"]["inventory"]["quantities"][0]["name"] == "Rune Ring"
        assert len(removed.state["inventory"]) == 1
        assert removed.state["inventory"][0]["name"] == "Rune Ring"


def test_xianxia_inventory_equipped_state_enforces_equippable_rules_and_id_ownership(app):
    with app.app_context():
        record = _build_character_record(app, _xianxia_definition("equip-rules"))
        service = _get_state_service(app)

        added_weapon = service.add_xianxia_inventory_item(
            record,
            {
                "name": "Cloak of Mists",
                "item_type": "Weapon",
                "equippable": "1",
                "is_equipped": "1",
            },
            expected_revision=record.state_record.revision,
        )
        weapon_id = added_weapon.state["xianxia"]["inventory"]["quantities"][0]["id"]
        assert added_weapon.state["inventory"][0]["is_equipped"] is True
        assert added_weapon.state["xianxia"]["inventory"]["quantities"][0]["equippable"] is True

        equipped = service.update_xianxia_inventory_equipped_state(
            _with_state(record, added_weapon),
            weapon_id,
            expected_revision=added_weapon.revision,
            is_equipped=False,
        )
        assert equipped.state["xianxia"]["inventory"]["quantities"][0]["is_equipped"] is False

        added_potion = service.add_xianxia_inventory_item(
            _with_state(record, equipped),
            {"name": "Spirit Rice", "item_type": "Consumable", "quantity": 1},
            expected_revision=equipped.revision,
        )
        potion_id = added_potion.state["xianxia"]["inventory"]["quantities"][1]["id"]
        with pytest.raises(ValueError, match="Cannot equip a non-equippable item"):
            service.update_xianxia_inventory_equipped_state(
                _with_state(record, added_potion),
                potion_id,
                expected_revision=added_potion.revision,
                is_equipped=True,
            )


def test_xianxia_inventory_update_requires_revisions_from_xianxia_records(app):
    with app.app_context():
        record = _build_character_record(app, _xianxia_definition("revision-safety"))
        service = _get_state_service(app)

        added = service.add_xianxia_inventory_item(
            record,
            {"name": "Dawn Bell", "item_type": "Miscellaneous"},
            expected_revision=record.state_record.revision,
        )

        with pytest.raises(CharacterStateConflictError):
            service.update_xianxia_inventory_item(
                _with_state(record, added),
                added.state["xianxia"]["inventory"]["quantities"][0]["id"],
                {"notes": "ignored"},
                expected_revision=record.state_record.revision,
            )


def test_xianxia_inventory_methods_reject_non_xianxia_records(app):
    with app.app_context():
        record = _build_character_record(app, _dnd5e_definition("dnd-bridge"))
        service = _get_state_service(app)

        with pytest.raises(ValueError, match="Xianxia inventory operations require a Xianxia character"):
            service.add_xianxia_inventory_item(
                record,
                {"name": "Iron Rations"},
                expected_revision=record.state_record.revision,
            )
        with pytest.raises(ValueError, match="Xianxia inventory operations require a Xianxia character"):
            service.update_xianxia_inventory_quantity(
                record,
                "missing",
                expected_revision=record.state_record.revision,
                quantity=3,
            )
