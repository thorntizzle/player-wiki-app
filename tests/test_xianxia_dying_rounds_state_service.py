from copy import deepcopy

import pytest

from player_wiki.character_service import build_initial_state, merge_state_with_definition, validate_state
from player_wiki.character_store import CharacterStateConflictError
from player_wiki.xianxia_character_model import (
    normalize_xianxia_state_payload,
    validate_xianxia_definition_payload,
)
from tests.test_xianxia_inventory_state_service import (
    _build_character_record, _dnd5e_definition, _with_state, _xianxia_definition,
)


@pytest.mark.parametrize(("value", "expected"), [
    (None, None), ("", None), (" \t", None), (0, 0), (6, 6), (" 04 ", 4), ("0", 0), ("6", 6),
])
def test_counter_normalization(value, expected):
    definition = _xianxia_definition("dying-normalization")
    state = normalize_xianxia_state_payload(definition, {"dying_rounds_remaining": value})
    assert state["dying_rounds_remaining"] == expected
    assert build_initial_state(definition)["xianxia"]["dying_rounds_remaining"] is None


@pytest.mark.parametrize("value", [True, False, -1, 7, 1.0, 1.5, [], {}, "-1", "+1", "1.0", "1e0", "١", "７", "abc", "9" * 5000])
def test_invalid_counter_never_writes(app, value):
    with app.app_context():
        record = _build_character_record(app, _xianxia_definition("dying-invalid"))
        service = app.extensions["character_state_service"]
        with pytest.raises(ValueError, match="whole number from 0 to 6"):
            service.update_xianxia_dying_rounds(record, expected_revision=record.state_record.revision,
                                               dying_rounds_remaining=value)
        actual = service.state_store.get_state(record.definition.campaign_slug, record.definition.character_slug)
        assert actual == record.state_record


def test_counter_save_clear_conflict_and_record_isolation(app):
    with app.app_context():
        record = _build_character_record(app, _xianxia_definition("dying-save"))
        service = app.extensions["character_state_service"]
        original = deepcopy(record.state_record.state)
        revision = record.state_record.revision
        for value in (0, 6, 6, None, None):
            before = deepcopy(record.state_record.state)
            updated = service.update_xianxia_dying_rounds(record, expected_revision=revision,
                                                         dying_rounds_remaining=value)
            assert record.state_record.state == before
            expected = deepcopy(before)
            expected["xianxia"]["dying_rounds_remaining"] = value
            assert updated.state == expected
            assert updated.revision == revision + 1
            revision = updated.revision
            record = _with_state(record, updated)
        stale = record
        hp = service.update_vitals(record, expected_revision=revision, current_hp=0)
        for value in (4, None):
            with pytest.raises(CharacterStateConflictError):
                service.update_xianxia_dying_rounds(stale, expected_revision=revision, dying_rounds_remaining=value)
            assert service.state_store.get_state(record.definition.campaign_slug, record.definition.character_slug) == hp
        assert original["status"] == hp.state["status"]
        with pytest.raises(TypeError):
            service.update_xianxia_dying_rounds(record, expected_revision=revision)
        dnd = _build_character_record(app, _dnd5e_definition("dying-dnd"))
        with pytest.raises(ValueError, match="Xianxia"):
            service.update_xianxia_dying_rounds(dnd, expected_revision=dnd.state_record.revision, dying_rounds_remaining=4)


def test_existing_mutations_and_progression_preserve_counter(app):
    with app.app_context():
        record = _build_character_record(app, _xianxia_definition("dying-preserve"))
        service = app.extensions["character_state_service"]
        updated = service.update_xianxia_dying_rounds(record, expected_revision=record.state_record.revision,
                                                     dying_rounds_remaining=4)
        record = _with_state(record, updated)
        operations = [
            lambda r: service.update_vitals(r, expected_revision=r.state_record.revision, current_hp=0),
            lambda r: service.update_vitals(r, expected_revision=r.state_record.revision, current_hp=8,
                                           temp_hp=2, current_stance=3, temp_stance=1, current_jing=1,
                                           current_qi=0, current_shen=0, current_yin=0, current_yang=1, current_dao=2),
            lambda r: service.update_xianxia_active_state(r, expected_revision=r.state_record.revision,
                                                          active_stance_name="Lotus", active_aura_name="Mist"),
            lambda r: service.update_currency(r, expected_revision=r.state_record.revision, values={"coin": 5, "supply": 3, "spirit_stones": 1}),
            lambda r: service.update_player_notes(r, expected_revision=r.state_record.revision, notes_markdown="Preserve me"),
            lambda r: service.add_xianxia_inventory_item(r, {"name": "Blade", "item_type": "Weapon", "quantity": 2}, expected_revision=r.state_record.revision),
            lambda r: service.apply_rest(r, "long", expected_revision=r.state_record.revision),
        ]
        for operation in operations:
            updated = operation(record)
            assert updated.state["xianxia"]["dying_rounds_remaining"] == 4
            record = _with_state(record, updated)
        item_id = record.state_record.state["xianxia"]["inventory"]["quantities"][0]["id"]
        for operation in (
            lambda r: service.update_xianxia_inventory_quantity(r, item_id, expected_revision=r.state_record.revision, quantity=1),
            lambda r: service.update_xianxia_inventory_equipped_state(r, item_id, expected_revision=r.state_record.revision, is_equipped=True),
            lambda r: service.remove_xianxia_inventory_item(r, item_id, expected_revision=r.state_record.revision),
        ):
            updated = operation(record)
            assert updated.state["xianxia"]["dying_rounds_remaining"] == 4
            record = _with_state(record, updated)
        upgraded = deepcopy(record.definition)
        upgraded.xianxia["durability"]["hp_max"] = 20
        merged = merge_state_with_definition(upgraded, record.state_record.state)
        assert validate_state(upgraded, merged)["xianxia"]["dying_rounds_remaining"] == 4


@pytest.mark.parametrize("key", ["dying", "dying_rounds", "dying_rounds_remaining"])
def test_definition_excludes_mutable_counter(key):
    payload = _xianxia_definition("dying-definition").to_dict()
    payload["xianxia"][key] = 4
    with pytest.raises(ValueError, match="mutable Character state"):
        validate_xianxia_definition_payload(payload)
