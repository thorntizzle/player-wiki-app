from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import re

import player_wiki.app as app_module
import player_wiki.character_builder as character_builder_module
import pytest
import yaml
from player_wiki.auth_store import AuthStore
from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
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

def test_quick_reference_hides_item_backed_attacks_when_the_linked_item_is_not_equipped(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        attacks = list(payload.get("attacks") or [])
        if len(attacks) >= 2:
            attacks[0]["equipment_refs"] = ["light-crossbow-1"]
            attacks[1]["equipment_refs"] = ["quarterstaff-2"]
        payload["attacks"] = attacks

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for item in inventory:
            item_ref = str(item.get("catalog_ref") or item.get("id") or "").strip()
            if item_ref == "light-crossbow-1":
                item["is_equipped"] = False
            elif item_ref == "quarterstaff-2":
                item["is_equipped"] = True
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 2
    assert "Quarterstaff" in html
    assert "Hidden until equipped:" in html
    assert "Light Crossbow" in html


def test_quick_reference_can_fall_back_to_legacy_attack_name_matching_for_equipment_state(
    app, client, sign_in, users
):
    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for item in inventory:
            item_ref = str(item.get("catalog_ref") or item.get("id") or "").strip()
            if item_ref == "light-crossbow-1":
                item["is_equipped"] = False
            elif item_ref == "quarterstaff-2":
                item["is_equipped"] = True
        payload["inventory"] = inventory

    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 2
    assert "Quarterstaff" in html
    assert "Hidden until equipped:" in html
    assert "Light Crossbow" in html


def test_quick_reference_uses_explicit_weapon_wield_mode_for_versatile_attack_rows(app, client, sign_in, users):
    def _set_quarterstaff_mode(payload: dict, mode: str) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for item in equipment_catalog:
            if str(item.get("id") or "").strip() == "quarterstaff-2":
                item["is_equipped"] = True
                if mode:
                    item["weapon_wield_mode"] = mode
                else:
                    item.pop("weapon_wield_mode", None)
        payload["equipment_catalog"] = equipment_catalog

    def _set_quarterstaff_state(payload: dict, mode: str) -> None:
        inventory = list(payload.get("inventory") or [])
        for item in inventory:
            if str(item.get("catalog_ref") or item.get("id") or "").strip() == "quarterstaff-2":
                item["is_equipped"] = True
                if mode:
                    item["weapon_wield_mode"] = mode
                else:
                    item.pop("weapon_wield_mode", None)
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", lambda payload: _set_quarterstaff_mode(payload, "main-hand"))
    _write_character_state(app, "arden-march", lambda payload: _set_quarterstaff_state(payload, "main-hand"))

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        main_hand_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert "Quarterstaff (two-handed)" not in {attack["name"] for attack in main_hand_character["attacks"]}
        assert "Quarterstaff (two-handed)" in {attack["name"] for attack in main_hand_character["hidden_attacks"]}

    _write_character_definition(app, "arden-march", lambda payload: _set_quarterstaff_mode(payload, "two-handed"))
    _write_character_state(app, "arden-march", lambda payload: _set_quarterstaff_state(payload, "two-handed"))

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        two_handed_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert "Quarterstaff (two-handed)" in {attack["name"] for attack in two_handed_character["attacks"]}


def test_quick_reference_tolerates_legacy_string_page_refs_when_linking_attacks_to_equipment(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "manual-item-staff-of-the-crescent-moon",
                "name": "Staff of the Crescent Moon",
                "default_quantity": 1,
                "weight": "4 lb.",
                "notes": "",
                "page_ref": "items/staff-of-the-crescent-moon",
            }
        ]
        payload["attacks"] = [
            {
                "id": "staff-of-the-crescent-moon",
                "name": "Staff of the Crescent Moon",
                "category": "weapon",
                "attack_bonus": 7,
                "damage": "1d6+4 bludgeoning",
                "damage_type": "bludgeoning",
                "notes": "A crescent-tipped staff used in close quarters.",
                "page_ref": "actions/staff-of-the-crescent-moon",
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "catalog_ref": "manual-item-staff-of-the-crescent-moon",
                "name": "Staff of the Crescent Moon",
                "quantity": 1,
                "is_equipped": True,
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Staff of the Crescent Moon" in html


def test_quick_reference_renders_shield_master_helper_row_without_placeholder_math(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "shield-1",
                "name": "Shield",
                "default_quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-shield",
                    "title": "Shield",
                    "source_id": "PHB",
                },
            }
        ]
        payload["attacks"] = [
            {
                "id": "shield-shove-1",
                "name": "Shield Shove",
                "category": "special action",
                "attack_bonus": None,
                "damage": "",
                "damage_type": "",
                "notes": "Bonus action after taking the Attack action; Shield Master shove within 5 feet.",
                "mode_key": "feat:phb-feat-shield-master:shove",
                "equipment_refs": ["shield-1"],
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "shield-1",
                "catalog_ref": "shield-1",
                "name": "Shield",
                "quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "is_equipped": True,
                "is_attuned": False,
                "tags": [],
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Shield Shove" in html
    assert "Special Action" in html
    assert "Bonus action after taking the Attack action; Shield Master shove within 5 feet." in html
    assert "to hit" not in html
    assert "<strong>--</strong>" not in html


def test_quick_reference_renders_grappler_helper_row_without_placeholder_math(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "pin-grappled-creature-1",
                "name": "Pin Grappled Creature",
                "category": "special action",
                "attack_bonus": None,
                "damage": "",
                "damage_type": "",
                "notes": "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends.",
                "mode_key": "feat:phb-feat-grappler:pin",
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Pin Grappled Creature" in html
    assert "Special Action" in html
    assert "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends." in html
    assert "to hit" not in html
    assert "<strong>--</strong>" not in html


def test_quick_reference_renders_mounted_combatant_note_on_melee_attack_card(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "handaxe-1",
                "name": "Handaxe",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 slashing",
                "damage_type": "Slashing",
                "notes": "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount).",
            },
            {
                "id": "handaxe-thrown-2",
                "name": "Handaxe (thrown)",
                "category": "ranged weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 slashing",
                "damage_type": "Slashing",
                "notes": "range 20/60.",
            },
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Handaxe" in html
    assert "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount)." in html
    assert "Handaxe (thrown)" in html
    assert "range 20/60." in html


def test_quick_reference_hides_shield_master_helper_row_until_shield_is_equipped(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "shield-1",
                "name": "Shield",
                "default_quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-shield",
                    "title": "Shield",
                    "source_id": "PHB",
                },
            }
        ]
        payload["attacks"] = [
            {
                "id": "shield-shove-1",
                "name": "Shield Shove",
                "category": "special action",
                "attack_bonus": None,
                "damage": "",
                "damage_type": "",
                "notes": "Bonus action after taking the Attack action; Shield Master shove within 5 feet.",
                "mode_key": "feat:phb-feat-shield-master:shove",
                "equipment_refs": ["shield-1"],
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "shield-1",
                "catalog_ref": "shield-1",
                "name": "Shield",
                "quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "is_equipped": False,
                "is_attuned": False,
                "tags": [],
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 0
    assert "Hidden until equipped:" in html
    assert "Shield Shove" in html
    assert "Bonus action after taking the Attack action; Shield Master shove within 5 feet." not in html


def test_quick_reference_renders_shared_defensive_rules_section(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["features"] = [
            {
                "id": "heavy-armor-master-1",
                "name": "Heavy Armor Master",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "phb-feat-heavy-armor-master",
                    "title": "Heavy Armor Master",
                    "source_id": "PHB",
                },
            },
            {
                "id": "shield-master-1",
                "name": "Shield Master",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "phb-feat-shield-master",
                    "title": "Shield Master",
                    "source_id": "PHB",
                },
            },
        ]
        payload["equipment_catalog"] = [
            {
                "id": "chain-mail-1",
                "name": "Chain Mail",
                "default_quantity": 1,
                "is_equipped": True,
            },
            {
                "id": "shield-1",
                "name": "Shield",
                "default_quantity": 1,
                "is_equipped": True,
            },
        ]
        payload["stats"] = {
            **dict(payload.get("stats") or {}),
            "armor_class": 18,
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Defensive rules" in html
    assert "Heavy Armor Master" in html
    assert "Mitigation:</strong> Reduce nonmagical bludgeoning, piercing, and slashing damage from weapons by 3." in html
    assert "Shield Master" in html
    assert "Dex saves:</strong> Add +2 to Dexterity saves against spells or other harmful effects that target only you." in html
    assert "Reaction:</strong> If an effect lets you make a Dexterity save for half damage, you can use your reaction to take no damage on a success." in html
    assert html.count(">Active<") >= 2


def test_quick_reference_hides_combat_reminders_but_keeps_mage_slayer_defense(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "mace-1",
                "name": "Mace",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 bludgeoning",
                "damage_type": "Bludgeoning",
                "notes": "",
            },
            {
                "id": "rapier-1",
                "name": "Rapier",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d8+3 piercing",
                "damage_type": "Piercing",
                "notes": "",
            },
        ]
        payload["features"] = [
            {
                "id": "mage-slayer-1",
                "name": "Mage Slayer",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "phb-feat-mage-slayer",
                    "title": "Mage Slayer",
                    "source_id": "PHB",
                },
            },
            {
                "id": "crusher-1",
                "name": "Crusher",
                "category": "feat",
                "source": "TCE",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "tce-feat-crusher",
                    "title": "Crusher",
                    "source_id": "TCE",
                },
            },
            {
                "id": "piercer-1",
                "name": "Piercer",
                "category": "feat",
                "source": "TCE",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "tce-feat-piercer",
                    "title": "Piercer",
                    "source_id": "TCE",
                },
            },
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Combat reminders" not in html
    assert "Mage Slayer" in html
    assert "Spellcasting trigger:</strong> When a creature within 5 feet of you casts a spell, you can use your reaction to make a melee weapon attack against it." not in html
    assert "Crusher" not in html
    assert "Eligible attacks: Mace" not in html
    assert "Piercer" not in html
    assert "Eligible attacks: Rapier" not in html
    assert "Linked attacks" not in html
    assert "Defensive rules" in html
    assert "Spell saves:</strong> You have advantage on saving throws against spells cast by creatures within 5 feet of you." in html
