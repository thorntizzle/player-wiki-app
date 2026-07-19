from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import inspect
from pathlib import Path
import re

import player_wiki.app as app_module
import player_wiki.character_builder as character_builder_module
import pytest
import yaml
from player_wiki.auth_store import AuthStore
from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
from player_wiki.character_reconciliation import (
    CharacterPublicationCoordinator,
    CharacterReconciliationHooks,
)
from player_wiki.db import get_db
from player_wiki.system_policy import (
    DND_5E_SYSTEM_CODE,
    XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
    XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE,
    XIANXIA_SYSTEM_CODE,
)
from player_wiki.systems_models import SystemsEntryRecord
from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID
from tests.helpers.character_state_helpers import (
    _character_state_revision,
    _read_character_definition,
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.helpers.systems_seed_helpers import (
    _seed_systems_item_entry,
    _seed_systems_spell_entries,
    _systems_ref,
)
from tests.helpers.xianxia_character_helpers import _valid_xianxia_create_data
from tests.helpers.character_read_route_helpers import (
    TEST_JPG_BYTES,
    TEST_PNG_BYTES,
    _assert_event_contains,
    _character_read_shell_script_text,
    _read_shell_target_subpages,
    _seed_systems_entry,
    _spell_payload,
)

def test_equipment_manager_is_visible_to_editable_users_and_hidden_from_read_only_players(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["owner"]["email"], users["owner"]["password"])
    owner_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    owner_html = owner_response.get_data(as_text=True)

    assert owner_response.status_code == 200
    assert "Add Systems item" in owner_html
    assert "Add campaign item" in owner_html
    assert "Add custom item" in owner_html
    assert "Supplemental equipment" in owner_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    read_only_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    read_only_html = read_only_response.get_data(as_text=True)

    assert read_only_response.status_code == 200
    assert "Add Systems item" not in read_only_html
    assert "Add campaign item" not in read_only_html
    assert "Add custom item" not in read_only_html
    assert "Supplemental equipment" not in read_only_html


def test_equipment_manager_campaign_item_picker_only_lists_item_pages(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Stormglass Compass - Items" in html
    assert "Operations Brief - Notes" not in html
    assert "Captain Lyra Vale - NPCs" not in html


def test_inventory_subpage_shows_direct_remove_controls_only_to_editable_users(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _write_character_definition(
        app,
        "arden-march",
        lambda payload: payload.__setitem__(
            "source",
            {"source_type": "native_character_builder", "source_path": "builder://arden-march"},
        ),
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/add-manual",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "Dock Ledger",
            "quantity": "1",
            "weight": "",
            "notes": "Tracked on the inventory page.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    owner_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    owner_html = owner_response.get_data(as_text=True)

    assert owner_response.status_code == 200
    assert "Dock Ledger" in owner_html
    assert "Remove from inventory" in owner_html
    assert "Tracked inventory rows can be removed directly here." in owner_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    read_only_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    read_only_html = read_only_response.get_data(as_text=True)

    assert read_only_response.status_code == 200
    assert "Dock Ledger" in read_only_html
    assert "Remove from inventory" not in read_only_html
    assert "Tracked inventory rows can be removed directly here." not in read_only_html


def test_imported_inventory_rows_can_be_removed_from_inventory_page(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    inventory_html = inventory_response.get_data(as_text=True)

    assert inventory_response.status_code == 200
    assert "Backpack" in inventory_html
    assert "Remove from inventory" in inventory_html

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/backpack-5/remove",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "inventory",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    assert "Backpack" not in {str(item.get("name") or "") for item in list(updated_definition.get("equipment_catalog") or [])}

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        inventory_names = {
            str(item.get("name") or "")
            for item in list((record.state_record.state or {}).get("inventory") or [])
        }
        assert "Backpack" not in inventory_names


def test_equipment_subpage_is_separate_from_inventory_manager(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Attuned items" in html
    assert "Equipped items" in html
    assert "Save equipment state" not in html
    assert 'data-character-autosubmit' in html
    assert "Add Systems item" not in html
    assert "Supplemental equipment" not in html
    assert "Inventory and currency" not in html


def test_equipment_subpage_filters_inventory_only_rows_and_only_shows_attunement_for_required_magic_items(
    app, client, sign_in, users
):
    boots_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-boots-of-elvenkind",
        title="Boots of Elvenkind",
        metadata={"weight": 1, "rarity": "uncommon"},
    )
    compass_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-stormglass-compass",
        title="Stormglass Compass",
        metadata={"weight": 1, "rarity": "rare", "attunement": "requires attunement"},
    )

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog[2] = {
            **dict(equipment_catalog[2]),
            "name": "Boots of Elvenkind",
            "weight": "1 lb.",
            "systems_ref": _systems_ref(boots_entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        equipment_catalog[4] = {
            **dict(equipment_catalog[4]),
            "name": "Stormglass Compass",
            "weight": "1 lb.",
            "systems_ref": _systems_ref(compass_entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        inventory[2] = {
            **dict(inventory[2]),
            "name": "Boots of Elvenkind",
            "weight": "1 lb.",
            "is_equipped": False,
            "is_attuned": False,
        }
        inventory[4] = {
            **dict(inventory[4]),
            "name": "Stormglass Compass",
            "weight": "1 lb.",
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")
    assert page_response.status_code == 200
    html = page_response.get_data(as_text=True)
    assert 'id="character-equipment-state"' in html
    assert 'class="equipment-state-grid"' in html
    assert "Light Crossbow" in html
    assert "Quarterstaff" in html
    assert "Boots of Elvenkind" in html
    assert "Stormglass Compass" in html
    assert "Courier Satchel" not in html
    assert "Crossbow Bolts" not in html
    assert "Chalk" not in html
    assert html.count("Save equipment state") == 0
    assert html.count('data-character-sheet-edit-form="equipment-state"') == 4
    assert html.count('data-character-autosubmit') >= 4
    assert html.count('name="weapon_wield_mode"') == 2
    assert html.count('name="is_equipped"') == 2
    assert html.count('name="is_attuned"') == 1
    assert "Main Hand" in html
    assert "Off Hand" in html
    assert "Two-Handed" in html
    assert "Requires attunement" not in html
    assert "x1 | 1 lb." not in html
    assert "| 1 lb." not in html
    assert "Use attunement only when the item's rules call for it." not in html


def test_equipment_state_update_rejects_inventory_only_rows(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/backpack-5/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
            "is_attuned": "1",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302
    assert update_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=equipment#character-equipment-state"
    )

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "backpack-5"
        )
        state_item = next(
            item
            for item in list(record.state_record.state.get("inventory") or [])
            if str(item.get("catalog_ref") or item.get("id") or "") == "backpack-5"
        )
        assert definition_item.get("is_equipped") is not True
        assert definition_item.get("is_attuned") is not True
        assert state_item.get("is_equipped") is not True
        assert state_item.get("is_attuned") is not True
        assert record.state_record.state["attunement"]["attuned_item_refs"] == []


def test_equipment_state_update_preserves_three_item_attunement_limit_for_qualifying_items(
    app, client, sign_in, users
):
    item_ids = ["light-crossbow-1", "quarterstaff-2", "satchel-3", "crossbow-bolts-4"]
    entries = [
        _seed_systems_item_entry(
            app,
            slug=f"phb-item-attuned-relic-{index}",
            title=f"Attuned Relic {index}",
            metadata={"weight": 1, "rarity": "rare", "attunement": "requires attunement"},
        )
        for index in range(1, 5)
    ]

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, entry in enumerate(entries):
            equipment_catalog[index] = {
                **dict(equipment_catalog[index]),
                "name": f"Attuned Relic {index + 1}",
                "weight": "1 lb.",
                "systems_ref": _systems_ref(entry),
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index in range(4):
            inventory[index] = {
                **dict(inventory[index]),
                "name": f"Attuned Relic {index + 1}",
                "weight": "1 lb.",
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": item_ids[:3]}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/crossbow-bolts-4/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
            "is_attuned": "1",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "crossbow-bolts-4"
        )
        state_item = next(
            item
            for item in list(record.state_record.state.get("inventory") or [])
            if str(item.get("catalog_ref") or item.get("id") or "") == "crossbow-bolts-4"
        )
        assert definition_item["is_equipped"] is False
        assert definition_item["is_attuned"] is False
        assert state_item["is_equipped"] is False
        assert state_item["is_attuned"] is False
        assert record.state_record.state["attunement"]["attuned_item_refs"] == item_ids[:3]


def test_equipment_state_update_persists_weapon_wield_mode_for_weapon_rows(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/quarterstaff-2/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "weapon_wield_mode": "two-handed",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "quarterstaff-2"
        )
        state_item = next(
            item
            for item in list(record.state_record.state.get("inventory") or [])
            if str(item.get("catalog_ref") or item.get("id") or "") == "quarterstaff-2"
        )
        assert definition_item["weapon_wield_mode"] == "two-handed"
        assert definition_item["is_equipped"] is True
        assert state_item["weapon_wield_mode"] == "two-handed"
        assert state_item["is_equipped"] is True


def test_actual_browser_definition_runner_forwards_exact_publication_objects(
    app, client, sign_in, users, monkeypatch
):
    action_calls = []
    merge_calls = []
    publication_calls = []
    loaded_records = []
    original_action = app_module.build_shared_equipment_state_update_result
    raw_view = inspect.unwrap(app.view_functions["character_equipment_state_update"])
    view_freevars = dict(
        zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ())
    )
    runner = view_freevars["dependencies"].cell_contents.run_character_definition_mutation
    runner_freevars = dict(zip(runner.__code__.co_freevars, runner.__closure__ or ()))
    original_merge = app_module.merge_state_with_definition
    original_load = runner_freevars["load_character_context"].cell_contents

    def record_action(*args, **kwargs):
        result = original_action(*args, **kwargs)
        action_calls.append((args, kwargs, result))
        return result

    def record_merge(*args, **kwargs):
        result = original_merge(*args, **kwargs)
        merge_calls.append((args, kwargs, result))
        return result

    class SpyCoordinator:
        def recover_pending(self, *, limit=8):
            return {"recovered": 0, "conflict": 0, "pending": 0}

        def update(self, *args, **kwargs):
            publication_calls.append((args, kwargs))

    def record_load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        loaded_records.append(result[1])
        return result

    monkeypatch.setattr(
        app_module, "build_shared_equipment_state_update_result", record_action
    )
    monkeypatch.setattr(app_module, "merge_state_with_definition", record_merge)
    monkeypatch.setattr(
        runner_freevars["load_character_context"], "cell_contents", record_load
    )
    monkeypatch.setattr(
        runner_freevars["character_publication_coordinator"],
        "cell_contents",
        SpyCoordinator(),
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        prior = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
    assert prior is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/quarterstaff-2/state",
        data={
            "expected_revision": prior.state_record.revision,
            "mode": "read",
            "page": "equipment",
            "weapon_wield_mode": "two-handed",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert len(action_calls) == len(merge_calls) == len(publication_calls) == 1
    action_args, _action_kwargs, action_result = action_calls[0]
    merge_args, _merge_kwargs, merged_state = merge_calls[0]
    publication_args, publication_kwargs = publication_calls[0]
    assert any(action_args[1] is record for record in loaded_records)
    assert publication_args == (
        action_args[1],
        merge_args[0],
        action_result[1],
        merged_state,
    )
    assert publication_kwargs == {
        "expected_revision": action_args[1].state_record.revision,
        "updated_by_user_id": users["dm"]["id"],
    }


def test_browser_definition_runner_recovers_after_postcommit_failure(
    app, client, sign_in, users, monkeypatch
):
    original_coordinator = app.extensions["character_publication_coordinator"]

    def fail_after_commit(event, _operation_id):
        if event == "after_commit":
            raise RuntimeError("browser committed publication fault")

    fault_coordinator = CharacterPublicationCoordinator(
        campaigns_dir=original_coordinator.campaigns_dir,
        database_path=original_coordinator.database_path,
        state_store=original_coordinator.state_store,
        repository=original_coordinator.repository,
        hooks=CharacterReconciliationHooks(on_event=fail_after_commit),
    )
    raw_view = inspect.unwrap(app.view_functions["character_equipment_state_update"])
    view_freevars = dict(
        zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ())
    )
    runner = view_freevars["dependencies"].cell_contents.run_character_definition_mutation
    runner_freevars = dict(zip(runner.__code__.co_freevars, runner.__closure__ or ()))
    monkeypatch.setattr(
        runner_freevars["character_publication_coordinator"],
        "cell_contents",
        fault_coordinator,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        prior = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
    assert prior is not None

    with pytest.raises(RuntimeError, match="browser committed publication fault"):
        client.post(
            "/campaigns/linden-pass/characters/arden-march/equipment/quarterstaff-2/state",
            data={
                "expected_revision": prior.state_record.revision,
                "mode": "read",
                "page": "equipment",
                "weapon_wield_mode": "two-handed",
            },
            follow_redirects=False,
        )

    with app.app_context():
        row = get_db().execute(
            """
            SELECT state FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
            """
        ).fetchone()
        assert row is not None and row["state"] == "prepared"
        state = app.extensions["character_state_store"].get_state(
            "linden-pass", "arden-march"
        )
        assert state is not None
        assert state.revision == prior.state_record.revision + 1
        assert app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        ) is None
        assert original_coordinator.recover_key("linden-pass", "arden-march") is True
        recovered = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
        assert recovered is not None
        assert recovered.state_record.revision == prior.state_record.revision + 1


def test_native_equipment_state_update_recalculates_attunement_gated_magic_weapon_attacks(
    app, client, sign_in, users
):
    entry = _seed_systems_item_entry(
        app,
        slug="phb-item-plus-one-light-crossbow",
        title="+1 Light Crossbow",
        metadata={"weight": 5, "base_item": "Light Crossbow|PHB", "attunement": "requires attunement"},
    )

    def _mutate_definition(payload: dict) -> None:
        source = dict(payload.get("source") or {})
        source["source_type"] = "native_character_builder"
        source["source_path"] = "builder://arden-march"
        source["imported_from"] = "In-app Native Level 5 Builder"
        payload["source"] = source

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog[0] = {
            **dict(equipment_catalog[0]),
            "name": "+1 Light Crossbow",
            "weight": "5 lb.",
            "systems_ref": _systems_ref(entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        inventory[0] = {
            **dict(inventory[0]),
            "name": "+1 Light Crossbow",
            "weight": "5 lb.",
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    equip_only_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/light-crossbow-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
        },
        follow_redirects=False,
    )

    assert equip_only_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        attacks_by_name = {
            attack["name"]: attack
            for attack in list(record.definition.attacks or [])
        }
        assert attacks_by_name["+1 Light Crossbow"]["attack_bonus"] == 5
        assert attacks_by_name["+1 Light Crossbow"]["damage"] == "1d8+2 piercing"

    fully_active_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/light-crossbow-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
            "is_attuned": "1",
        },
        follow_redirects=False,
    )

    assert fully_active_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        attacks_by_name = {
            attack["name"]: attack
            for attack in list(record.definition.attacks or [])
        }
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "light-crossbow-1"
        )
        assert attacks_by_name["+1 Light Crossbow"]["attack_bonus"] == 6
        assert attacks_by_name["+1 Light Crossbow"]["damage"] == "1d8+3 piercing"
        assert definition_item["is_equipped"] is True
        assert definition_item["is_attuned"] is True
        assert record.state_record.state["attunement"]["attuned_item_refs"] == ["light-crossbow-1"]


def test_native_equipment_state_update_recalculates_medium_armor_master_armor_class(
    app, client, sign_in, users
):
    def _mutate_definition(payload: dict) -> None:
        payload["source"] = {
            "source_type": "native_character_builder",
            "source_path": "builder://arden-march",
            "imported_from": "In-app Native Level 5 Builder",
        }
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
        stats["ability_scores"] = ability_scores
        stats["armor_class"] = 13
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "medium-armor-master-1",
                "name": "Medium Armor Master",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "activation_type": "passive",
                "tracker_ref": None,
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "phb-feat-medium-armor-master",
                    "title": "Medium Armor Master",
                    "source_id": "PHB",
                },
            }
        ]
        payload["equipment_catalog"] = [
            {
                "id": "scale-mail-1",
                "name": "Scale Mail",
                "default_quantity": 1,
                "weight": "45 lb.",
                "notes": "",
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-scale-mail",
                    "title": "Scale Mail",
                    "source_id": "PHB",
                },
                "is_equipped": False,
                "is_attuned": False,
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "scale-mail-1",
                "catalog_ref": "scale-mail-1",
                "name": "Scale Mail",
                "quantity": 1,
                "weight": "45 lb.",
                "notes": "",
                "is_equipped": False,
                "is_attuned": False,
                "tags": [],
            }
        ]
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    equip_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/scale-mail-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
        },
        follow_redirects=False,
    )

    assert equip_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "scale-mail-1"
        )
        assert record.definition.stats["armor_class"] == 17
        assert definition_item["is_equipped"] is True

    unequip_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/scale-mail-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
        },
        follow_redirects=False,
    )

    assert unequip_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "scale-mail-1"
        )
        assert record.definition.stats["armor_class"] == 13
        assert definition_item["is_equipped"] is False


def test_imported_character_equipment_controls_can_search_and_add_systems_items_without_resetting_other_quantities(
    app, client, sign_in, users
):
    entry = _seed_systems_item_entry(app)

    _write_character_state(
        app,
        "selene-brook",
        lambda payload: payload.__setitem__(
            "inventory",
            [
                {
                    **dict(item),
                    "quantity": 11 if str(item.get("catalog_ref") or item.get("id") or "") == "arrows-2" else item.get("quantity"),
                }
                for item in list(payload.get("inventory") or [])
            ],
        ),
    )

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/selene-brook/equipment/systems-items/search?q=rope",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["results"]
    assert search_payload["results"][0]["entry_slug"] == entry.slug
    assert search_payload["results"][0]["title"] == "Rope"

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "selene-brook")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/selene-brook/equipment/add-systems",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "entry_slug": entry.slug,
            "quantity": "2",
            "notes": "Emergency climbing bundle.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302
    assert add_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/selene-brook?page=inventory#character-inventory-manager"
    )

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "selene-brook")
        assert record is not None
        supplemental = [
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        ]
        assert len(supplemental) == 1
        added_item = supplemental[0]
        assert added_item["name"] == "Rope"
        assert added_item["default_quantity"] == 2
        assert added_item["notes"] == "Emergency climbing bundle."
        assert added_item["systems_ref"]["slug"] == entry.slug

        inventory_by_ref = {
            str(item.get("catalog_ref") or item.get("id") or ""): dict(item)
            for item in list(record.state_record.state.get("inventory") or [])
        }
        assert inventory_by_ref[added_item["id"]]["quantity"] == 2
        assert inventory_by_ref["arrows-2"]["quantity"] == 11

    landing = client.get(add_response.headers["Location"])
    html = landing.get_data(as_text=True)
    assert "Rope" in html
    assert "Emergency climbing bundle." in html
    assert "Remove from inventory" in html
    assert "Remove item" in html


def test_native_character_equipment_controls_can_add_campaign_items_from_item_pages(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _write_character_definition(
        app,
        "arden-march",
        lambda payload: payload.__setitem__(
            "source",
            {"source_type": "native_character_builder", "source_path": "builder://arden-march"},
        ),
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/add-campaign-item",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "page_ref": "items/stormglass-compass",
            "quantity": "1",
            "weight": "",
            "notes": "Issued from the brass vault.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        )
        assert manual_item["name"] == "Stormglass Compass"
        assert manual_item["page_ref"] == "items/stormglass-compass"
        assert manual_item["notes"] == "Issued from the brass vault."
        revision = record.state_record.revision

    update_response = client.post(
        f"/campaigns/linden-pass/characters/arden-march/equipment/{manual_item['id']}/update",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "",
            "quantity": "2",
            "weight": "1 lb.",
            "page_ref": "items/stormglass-compass",
            "notes": "Retuned to the harbor beacons.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        )
        assert manual_item["name"] == "Stormglass Compass"
        assert manual_item["default_quantity"] == 2
        assert manual_item["weight"] == "1 lb."
        assert manual_item["page_ref"] == "items/stormglass-compass"
        assert manual_item["notes"] == "Retuned to the harbor beacons."


def test_native_character_equipment_controls_can_add_update_and_remove_manual_items(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _write_character_definition(
        app,
        "arden-march",
        lambda payload: payload.__setitem__(
            "source",
            {"source_type": "native_character_builder", "source_path": "builder://arden-march"},
        ),
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/add-manual",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "Harbor Pass",
            "quantity": "1",
            "weight": "",
            "notes": "Issued by the harbor office.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_items = [
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        ]
        assert len(manual_items) == 1
        manual_item = manual_items[0]
        assert not manual_item.get("page_ref")

        revision = record.state_record.revision

    update_response = client.post(
        f"/campaigns/linden-pass/characters/arden-march/equipment/{manual_item['id']}/update",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "Harbor Pass",
            "quantity": "3",
            "weight": "",
            "notes": "Stamped for repeat entry.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        )
        assert manual_item["default_quantity"] == 3
        assert manual_item["notes"] == "Stamped for repeat entry."
        revision = record.state_record.revision

    remove_response = client.post(
        f"/campaigns/linden-pass/characters/arden-march/equipment/{manual_item['id']}/remove",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        assert [
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        ] == []


def test_character_personal_portrait_can_be_uploaded_replaced_rendered_and_removed(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    upload_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "portrait",
            "portrait_alt": "Arden leaning over the harbor rail.",
            "portrait_caption": "Used on the portrait page.",
            "portrait_file": (BytesIO(TEST_PNG_BYTES), "arden-portrait.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert upload_response.status_code == 302
    assert upload_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=portrait#character-portrait-manager"
    )

    portrait_webp = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.webp"
    )
    assert portrait_webp.exists()
    portrait_bytes = portrait_webp.read_bytes()
    assert portrait_bytes[:4] == b"RIFF"
    assert portrait_bytes[8:12] == b"WEBP"

    read_portrait = client.get("/campaigns/linden-pass/characters/arden-march?page=portrait")
    read_html = read_portrait.get_data(as_text=True)
    assert read_portrait.status_code == 200
    assert "/campaigns/linden-pass/characters/arden-march/portrait" in read_html
    assert "Arden leaning over the harbor rail." in read_html
    assert "Used on the portrait page." in read_html
    assert "Remove portrait" in read_html

    session_portrait = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=portrait")
    session_html = session_portrait.get_data(as_text=True)
    assert session_portrait.status_code == 200
    assert "/campaigns/linden-pass/characters/arden-march/portrait" in session_html
    assert 'data-character-read-shell-mode="read"' in session_html
    assert "Remove portrait" in session_html
    assert "Save portrait" in session_html

    portrait_response = client.get("/campaigns/linden-pass/characters/arden-march/portrait")
    assert portrait_response.status_code == 200
    assert portrait_response.mimetype == "image/webp"
    assert portrait_response.data == portrait_bytes
    portrait_response.close()

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    read_only_portrait = client.get("/campaigns/linden-pass/characters/arden-march?page=portrait")
    read_only_html = read_only_portrait.get_data(as_text=True)
    assert read_only_portrait.status_code == 200
    assert "/campaigns/linden-pass/characters/arden-march/portrait" in read_only_html
    assert "Save portrait" not in read_only_html
    assert "Remove portrait" not in read_only_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    replace_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "portrait",
            "portrait_alt": "Arden in a second portrait.",
            "portrait_caption": "Updated portrait caption.",
            "portrait_file": (BytesIO(TEST_JPG_BYTES), "arden-portrait.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert replace_response.status_code == 302
    assert portrait_webp.exists()
    replacement_portrait_bytes = portrait_webp.read_bytes()
    assert replacement_portrait_bytes[:4] == b"RIFF"
    assert replacement_portrait_bytes[8:12] == b"WEBP"

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait/remove",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "portrait",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302
    assert remove_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=portrait#character-portrait-manager"
    )
    assert not portrait_webp.exists()

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        profile = dict(record.definition.profile or {})
        assert profile.get("portrait_asset_ref") in (None, "")


def test_non_equipment_character_save_persists_recovered_equipment_links(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _seed_systems_item_entry(
        app,
        slug="phb-item-chain-mail",
        title="Chain Mail",
        metadata={"type": "HA", "ac": 16},
    )

    def _mutate_definition(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "chain-mail-1",
                "name": "Chain Mail",
                "default_quantity": 1,
                "weight": "55 lb.",
                "notes": "",
                "is_equipped": True,
                "systems_ref": None,
                "page_ref": None,
            }
        ]

    _write_character_definition(app, "arden-march", _mutate_definition)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    revision = _character_state_revision(app, "arden-march")

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "portrait",
            "portrait_alt": "Arden leaning over the harbor rail.",
            "portrait_caption": "Used on the portrait page.",
            "portrait_file": (BytesIO(TEST_PNG_BYTES), "arden-portrait.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    definition = _read_character_definition(app, "arden-march")
    equipment_item = dict(definition["equipment_catalog"][0] or {})
    assert equipment_item["systems_ref"]["slug"] == "phb-item-chain-mail"
    assert equipment_item["systems_ref"]["title"] == "Chain Mail"
    assert equipment_item["systems_ref"]["entry_type"] == "item"
    assert equipment_item["systems_ref"]["source_id"] == "PHB"


def test_character_sheet_recovers_missing_equipment_links_for_inventory_and_equipment_rows(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _seed_systems_item_entry(
        app,
        slug="phb-item-chain-mail",
        title="Chain Mail",
        metadata={"type": "HA", "ac": 16},
    )
    _seed_systems_item_entry(
        app,
        slug="phb-item-stormglass-compass",
        title="Stormglass Compass",
        metadata={"weight": 1, "rarity": "rare"},
    )

    def _mutate_definition(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "chain-mail-1",
                "name": "Chain Mail",
                "default_quantity": 1,
                "weight": "55 lb.",
                "notes": "",
                "is_equipped": True,
                "systems_ref": None,
            },
            {
                "id": "stormglass-compass-2",
                "name": "Stormglass Compass",
                "default_quantity": 1,
                "weight": "1 lb.",
                "notes": "",
                "page_ref": None,
                "systems_ref": None,
            },
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "chain-mail-1",
                "catalog_ref": "chain-mail-1",
                "name": "Chain Mail",
                "quantity": 1,
                "weight": "55 lb.",
                "is_equipped": True,
                "is_attuned": False,
                "charges_current": None,
                "charges_max": None,
                "notes": "",
                "tags": [],
            },
            {
                "id": "stormglass-compass-2",
                "catalog_ref": "stormglass-compass-2",
                "name": "Stormglass Compass",
                "quantity": 1,
                "weight": "1 lb.",
                "is_equipped": False,
                "is_attuned": False,
                "charges_current": None,
                "charges_max": None,
                "notes": "",
                "tags": [],
            },
        ]

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")

    assert inventory_response.status_code == 200
    assert equipment_response.status_code == 200

    inventory_html = inventory_response.get_data(as_text=True)
    equipment_html = equipment_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/systems/entries/phb-item-stormglass-compass' in inventory_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-chain-mail' in equipment_html
    assert "Item properties" in equipment_html
    assert "<span>Armor Category</span><strong>Heavy armor</strong>" in equipment_html
    assert "<span>Armor Class</span><strong>16</strong>" in equipment_html
    assert "<span>Dexterity</span><strong>No Dex modifier</strong>" in equipment_html


def test_legacy_session_mode_inventory_renders_normal_character_view_without_batch_currency_editor(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=inventory")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Inventory and currency" in html
    assert 'data-character-read-shell-mode="read"' in html
    assert 'data-character-sheet-edit-form="inventory"' in html
    assert 'data-character-sheet-edit-form="currency"' in html
    assert 'name="mode" value="read"' in html
    assert 'name="cp"' in html
    assert 'name="sp"' in html
    assert 'name="ep"' in html
    assert 'name="gp"' in html
    assert 'name="pp"' in html
    assert 'class="currency-grid"' in html
    assert html.count('class="currency-grid"') == 1
    assert 'name="delta" value="cp:-1"' not in html
    assert 'data-character-autosubmit' in html
    assert "Save pending changes" not in html
    assert "Save currency" not in html
    assert 'class="meta-badge">x' not in html
    assert re.search(r'class="meta-badge">[^<]*\blb\.?', html) is None
