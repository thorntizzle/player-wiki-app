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

def test_xianxia_roster_uses_system_policy_to_show_xianxia_create_without_dnd_affordances(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Create character" in html
    assert "/campaigns/linden-pass/characters/new" in html
    assert "Xianxia character creator" in html
    assert "PHB level 1 character" not in html
    assert "Native character creation and progression stay hidden here" not in html


def test_dnd5e_character_routes_keep_native_affordances_with_xianxia_policy_present(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "DND-5E"
        payload["systems_library"] = "DND-5E"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    builder = client.get("/campaigns/linden-pass/characters/new")
    sheet = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert roster.status_code == 200
    roster_html = roster.get_data(as_text=True)
    assert "Create character" in roster_html
    assert "/campaigns/linden-pass/characters/new" in roster_html
    assert "PHB level 1 character" in roster_html
    assert "Native character creation and progression stay hidden here" not in roster_html

    assert builder.status_code == 200
    builder_html = builder.get_data(as_text=True)
    assert "Native Level 1 Builder" in builder_html
    assert XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE not in builder_html

    assert sheet.status_code == 200
    sheet_html = sheet.get_data(as_text=True)
    assert "Advanced Editor" in sheet_html
    assert "/campaigns/linden-pass/characters/arden-march/edit" in sheet_html
    assert "Open sheet edit view" not in sheet_html
    assert "Sheet edit view" not in sheet_html
    assert "?page=spellcasting" in sheet_html
    assert app_module.NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE not in sheet_html


def test_xianxia_native_character_create_route_uses_xianxia_context_and_submit_path(
    app, client, sign_in, users, get_character
):
    def _attribute_data() -> dict[str, str]:
        return {
            "attribute_str": "1",
            "attribute_dex": "1",
            "attribute_con": "1",
            "attribute_int": "1",
            "attribute_wis": "1",
            "attribute_cha": "1",
        }

    def _armored_attribute_data() -> dict[str, str]:
        data = _attribute_data()
        data["attribute_con"] = "3"
        data["attribute_wis"] = "0"
        data["attribute_cha"] = "0"
        return data

    def _effort_data() -> dict[str, str]:
        return {
            "effort_basic": "1",
            "effort_weapon": "1",
            "effort_guns_explosive": "1",
            "effort_magic": "1",
            "effort_ultimate": "1",
        }

    def _energy_data() -> dict[str, str]:
        return {
            "energy_jing": "1",
            "energy_qi": "1",
            "energy_shen": "1",
        }

    def _skill_data() -> dict[str, str]:
        return {
            "trained_skill_1": "Fishing",
            "trained_skill_2": "Court Etiquette",
            "trained_skill_3": "Calligraphy",
        }

    def _martial_art_data() -> dict[str, str]:
        return {
            "martial_art_1_slug": "demons-fist",
            "martial_art_1_rank": "novice",
            "martial_art_2_slug": "heavenly-palm",
            "martial_art_2_rank": "initiate",
            "martial_art_3_slug": "",
            "martial_art_3_rank": "",
        }

    def _three_initiate_martial_art_data() -> dict[str, str]:
        return {
            "martial_art_1_slug": "demons-fist",
            "martial_art_1_rank": "initiate",
            "martial_art_2_slug": "heavenly-palm",
            "martial_art_2_rank": "initiate",
            "martial_art_3_slug": "taoist-blade",
            "martial_art_3_rank": "initiate",
        }

    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
            }
        ]

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    assert roster.status_code == 200
    roster_html = roster.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/new" in roster_html
    assert "Create character" in roster_html
    assert "PHB level 1 character" not in roster_html
    assert "imported PDF" not in roster_html

    create_response = client.get("/campaigns/linden-pass/characters/new")
    assert create_response.status_code == 200
    create_html = create_response.get_data(as_text=True)
    assert "Xianxia Character" in create_html
    assert "Starting Defaults" in create_html
    assert '<span class="meta">Realm</span>' in create_html
    realm_default_index = create_html.index('<span class="meta">Realm</span>')
    realm_default_html = create_html[realm_default_index: realm_default_index + 120]
    assert "<strong>Mortal</strong>" in realm_default_html
    assert '<span class="meta">Actions</span>' in create_html
    actions_default_index = create_html.index('<span class="meta">Actions</span>')
    actions_default_html = create_html[actions_default_index: actions_default_index + 120]
    assert "<strong>2</strong>" in actions_default_html
    assert "Yin / Yang" in create_html
    assert "1 / 1" in create_html
    assert '<span class="meta">Dao</span>' in create_html
    dao_default_index = create_html.index('<span class="meta">Dao</span>')
    dao_default_html = create_html[dao_default_index: dao_default_index + 120]
    assert "<strong>0 / 3</strong>" in dao_default_html
    assert 'name="manual_armor_bonus"' in create_html
    manual_armor_input_index = create_html.index('name="manual_armor_bonus"')
    manual_armor_input_html = create_html[manual_armor_input_index - 80: manual_armor_input_index + 180]
    assert 'value="0"' in manual_armor_input_html
    assert 'min="0"' in manual_armor_input_html
    assert '<span class="meta">Armor</span>' in create_html
    assert 'name="dao_current"' in create_html
    dao_input_index = create_html.index('name="dao_current"')
    dao_input_html = create_html[dao_input_index - 80: dao_input_index + 180]
    assert 'value="0"' in dao_input_html
    assert 'max="3"' in dao_input_html
    assert '<span class="meta">Insight</span>' in create_html
    insight_default_index = create_html.index('<span class="meta">Insight</span>')
    insight_default_html = create_html[insight_default_index: insight_default_index + 120]
    assert "<strong>0</strong>" in insight_default_html
    for attribute_label in (
        "Strength",
        "Dexterity",
        "Constitution",
        "Intelligence",
        "Wisdom",
        "Charisma",
    ):
        assert attribute_label in create_html
    for effort_label in ("Basic", "Weapon", "Guns/Explosive", "Magic", "Ultimate"):
        assert effort_label in create_html
    for energy_label in ("Jing", "Qi", "Shen"):
        assert energy_label in create_html
    for skill_label in ("Trained Skill 1", "Trained Skill 2", "Trained Skill 3"):
        assert skill_label in create_html
    assert 'name="trained_skill_1"' in create_html
    assert 'name="trained_skill_2"' in create_html
    assert 'name="trained_skill_3"' in create_html
    assert "Starting Martial Arts" in create_html
    assert 'name="martial_art_1_slug"' in create_html
    assert 'name="martial_art_1_rank"' in create_html
    assert 'value="demons-fist"' in create_html
    assert 'value="heavenly-palm"' in create_html
    assert 'value="initiate"' in create_html
    assert 'value="novice"' in create_html
    assert "Native Level 1 Builder" not in create_html
    assert "Spell Preview" not in create_html
    assert XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE not in create_html

    missing_name = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "", "character_slug": ""},
        follow_redirects=False,
    )
    assert missing_name.status_code == 400
    assert "Character name is required." in missing_name.get_data(as_text=True)

    missing_attributes = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "Attribute Gap", "character_slug": ""},
        follow_redirects=False,
    )
    assert missing_attributes.status_code == 400
    assert (
        "Missing Xianxia attributes: Strength, Dexterity, Constitution, "
        "Intelligence, Wisdom, and Charisma."
    ) in missing_attributes.get_data(as_text=True)

    invalid_attributes = _attribute_data()
    invalid_attributes["attribute_dex"] = "quick"
    invalid_attribute_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Attribute Typo",
            "character_slug": "",
            **invalid_attributes,
            **_effort_data(),
        },
        follow_redirects=False,
    )
    assert invalid_attribute_response.status_code == 400
    assert "Dexterity must be a whole number." in invalid_attribute_response.get_data(as_text=True)

    over_budget_attributes = _attribute_data()
    over_budget_attributes["attribute_str"] = "2"
    over_budget_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Attribute Overbudget",
            "character_slug": "",
            **over_budget_attributes,
            **_effort_data(),
        },
        follow_redirects=False,
    )
    assert over_budget_response.status_code == 400
    assert (
        "Xianxia Attributes must spend exactly 6 creation points; submitted total is 7."
    ) in over_budget_response.get_data(as_text=True)

    over_cap_attributes = _attribute_data()
    over_cap_attributes["attribute_str"] = "4"
    over_cap_attributes["attribute_wis"] = "0"
    over_cap_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Attribute Overcap",
            "character_slug": "",
            **over_cap_attributes,
            **_effort_data(),
        },
        follow_redirects=False,
    )
    assert over_cap_response.status_code == 400
    assert "Strength cannot exceed 3 at character creation." in over_cap_response.get_data(as_text=True)

    missing_efforts = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "Effort Gap", "character_slug": "", **_attribute_data()},
        follow_redirects=False,
    )
    assert missing_efforts.status_code == 400
    assert "Missing Xianxia efforts: Basic, Weapon, Guns/Explosive, Magic, and Ultimate." in (
        missing_efforts.get_data(as_text=True)
    )

    invalid_efforts = _effort_data()
    invalid_efforts["effort_magic"] = "arcane"
    invalid_effort_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Effort Typo",
            "character_slug": "",
            **_attribute_data(),
            **invalid_efforts,
        },
        follow_redirects=False,
    )
    assert invalid_effort_response.status_code == 400
    assert "Magic must be a whole number." in invalid_effort_response.get_data(as_text=True)

    negative_efforts = _effort_data()
    negative_efforts["effort_weapon"] = "-1"
    negative_effort_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Effort Negative",
            "character_slug": "",
            **_attribute_data(),
            **negative_efforts,
        },
        follow_redirects=False,
    )
    assert negative_effort_response.status_code == 400
    assert "Weapon cannot be negative." in negative_effort_response.get_data(as_text=True)

    over_budget_efforts = _effort_data()
    over_budget_efforts["effort_basic"] = "2"
    over_budget_effort_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Effort Overbudget",
            "character_slug": "",
            **_attribute_data(),
            **over_budget_efforts,
        },
        follow_redirects=False,
    )
    assert over_budget_effort_response.status_code == 400
    assert (
        "Xianxia Efforts must spend exactly 5 creation points; submitted total is 6."
    ) in over_budget_effort_response.get_data(as_text=True)

    over_cap_efforts = _effort_data()
    over_cap_efforts["effort_weapon"] = "0"
    over_cap_efforts["effort_guns_explosive"] = "0"
    over_cap_efforts["effort_magic"] = "4"
    over_cap_efforts["effort_ultimate"] = "0"
    over_cap_effort_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Effort Overcap",
            "character_slug": "",
            **_attribute_data(),
            **over_cap_efforts,
        },
        follow_redirects=False,
    )
    assert over_cap_effort_response.status_code == 400
    assert "Magic cannot exceed 3 at character creation." in over_cap_effort_response.get_data(
        as_text=True
    )

    missing_energies = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Energy Gap",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
        },
        follow_redirects=False,
    )
    assert missing_energies.status_code == 400
    assert "Missing Xianxia energies: Jing, Qi, and Shen." in missing_energies.get_data(
        as_text=True
    )

    invalid_energies = _energy_data()
    invalid_energies["energy_qi"] = "flowing"
    invalid_energy_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Energy Typo",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **invalid_energies,
        },
        follow_redirects=False,
    )
    assert invalid_energy_response.status_code == 400
    assert "Qi must be a whole number." in invalid_energy_response.get_data(as_text=True)

    negative_energies = _energy_data()
    negative_energies["energy_shen"] = "-1"
    negative_energy_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Energy Negative",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **negative_energies,
        },
        follow_redirects=False,
    )
    assert negative_energy_response.status_code == 400
    assert "Shen cannot be negative." in negative_energy_response.get_data(as_text=True)

    over_budget_energies = _energy_data()
    over_budget_energies["energy_jing"] = "2"
    over_budget_energy_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Energy Overbudget",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **over_budget_energies,
        },
        follow_redirects=False,
    )
    assert over_budget_energy_response.status_code == 400
    assert (
        "Xianxia Energies must spend exactly 3 creation points across Jing, Qi, and Shen; "
        "submitted total is 4."
    ) in over_budget_energy_response.get_data(as_text=True)

    under_budget_energies = _energy_data()
    under_budget_energies["energy_shen"] = "0"
    under_budget_energy_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Energy Underbudget",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **under_budget_energies,
        },
        follow_redirects=False,
    )
    assert under_budget_energy_response.status_code == 400
    assert (
        "Xianxia Energies must spend exactly 3 creation points across Jing, Qi, and Shen; "
        "submitted total is 2."
    ) in under_budget_energy_response.get_data(as_text=True)

    missing_skills_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Skill Gap",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
        },
        follow_redirects=False,
    )
    assert missing_skills_response.status_code == 400
    assert (
        "Xianxia character creation requires exactly 3 trained skills; submitted 0."
    ) in missing_skills_response.get_data(as_text=True)

    partial_skills = _skill_data()
    partial_skills["trained_skill_3"] = ""
    partial_skills_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Skill Partial",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **partial_skills,
        },
        follow_redirects=False,
    )
    assert partial_skills_response.status_code == 400
    assert (
        "Xianxia character creation requires exactly 3 trained skills; submitted 2."
    ) in partial_skills_response.get_data(as_text=True)

    duplicate_skills = _skill_data()
    duplicate_skills["trained_skill_3"] = "fishing"
    duplicate_skills_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Skill Duplicate",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **duplicate_skills,
        },
        follow_redirects=False,
    )
    assert duplicate_skills_response.status_code == 400
    assert "Xianxia trained skills must be distinct; duplicates: fishing." in (
        duplicate_skills_response.get_data(as_text=True)
    )

    missing_martial_arts_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Martial Gap",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
        },
        follow_redirects=False,
    )
    assert missing_martial_arts_response.status_code == 400
    assert (
        "Xianxia character creation requires a starting Martial Arts package: "
        "one Novice plus one Initiate, or three Initiates."
    ) in missing_martial_arts_response.get_data(as_text=True)

    illegal_two_initiates = _martial_art_data()
    illegal_two_initiates["martial_art_1_rank"] = "initiate"
    illegal_two_initiates_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Two Initiates",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **illegal_two_initiates,
        },
        follow_redirects=False,
    )
    assert illegal_two_initiates_response.status_code == 400
    assert (
        "Starting Martial Arts must be one Novice plus one Initiate, or three Initiates."
    ) in illegal_two_initiates_response.get_data(as_text=True)

    illegal_novice_plus_two = _three_initiate_martial_art_data()
    illegal_novice_plus_two["martial_art_1_rank"] = "novice"
    illegal_novice_plus_two_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Novice Plus Two",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **illegal_novice_plus_two,
        },
        follow_redirects=False,
    )
    assert illegal_novice_plus_two_response.status_code == 400
    assert (
        "Starting Martial Arts must be one Novice plus one Initiate, or three Initiates."
    ) in illegal_novice_plus_two_response.get_data(as_text=True)

    unavailable_novice = _martial_art_data()
    unavailable_novice["martial_art_1_slug"] = "rippling-melodies"
    unavailable_novice["martial_art_1_rank"] = "novice"
    unavailable_novice_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Unavailable Novice",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **unavailable_novice,
        },
        follow_redirects=False,
    )
    assert unavailable_novice_response.status_code == 400
    assert (
        "Rippling Melodies does not have Novice rank available in Systems metadata."
    ) in unavailable_novice_response.get_data(as_text=True)

    unknown_martial_art = _martial_art_data()
    unknown_martial_art["martial_art_1_slug"] = "missing-art"
    unknown_martial_art_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Unknown Art",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **unknown_martial_art,
        },
        follow_redirects=False,
    )
    assert unknown_martial_art_response.status_code == 400
    assert "Unsupported starting Martial Art: missing-art." in unknown_martial_art_response.get_data(
        as_text=True
    )

    invalid_armor_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Armor Typo",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            "manual_armor_bonus": "silk",
        },
        follow_redirects=False,
    )
    assert invalid_armor_response.status_code == 400
    assert "Manual armor bonus must be a whole number." in invalid_armor_response.get_data(
        as_text=True
    )

    negative_armor_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Armor Negative",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            "manual_armor_bonus": "-1",
        },
        follow_redirects=False,
    )
    assert negative_armor_response.status_code == 400
    assert "Manual armor bonus cannot be negative." in negative_armor_response.get_data(
        as_text=True
    )

    invalid_dao_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Dao Typo",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **_martial_art_data(),
            "dao_current": "flowing",
        },
        follow_redirects=False,
    )
    assert invalid_dao_response.status_code == 400
    assert "Starting Dao must be a whole number." in invalid_dao_response.get_data(as_text=True)

    over_cap_dao_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Dao Overcap",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **_martial_art_data(),
            "dao_current": "4",
        },
        follow_redirects=False,
    )
    assert over_cap_dao_response.status_code == 400
    assert "Starting Dao cannot exceed 3 at character creation." in over_cap_dao_response.get_data(
        as_text=True
    )

    submit_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Lotus Wake",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **_martial_art_data(),
            "generic_techniques": "Cloud-Stepping Feint",
            "starting_armor": "Silk armor",
            "starting_supplies": "Spirit rice",
            "starting_coin": "100 gp",
            "non_required_gear": "Travel lantern",
        },
        follow_redirects=False,
    )
    assert submit_response.status_code == 302
    assert submit_response.headers["Location"].endswith("/campaigns/linden-pass/characters/lotus-wake")

    definition_payload = _read_character_definition(app, "lotus-wake")
    assert definition_payload["system"] == XIANXIA_SYSTEM_CODE
    assert definition_payload["source"]["source_type"] == "xianxia_character_builder"
    assert definition_payload["spellcasting"] == {}
    assert definition_payload["proficiencies"] == {
        "armor": [],
        "weapons": [],
        "tools": [],
        "languages": [],
        "tool_expertise": [],
    }
    assert definition_payload["attacks"] == []
    assert definition_payload["features"] == []
    assert definition_payload["equipment_catalog"] == []
    assert definition_payload["xianxia"]["realm"] == "Mortal"
    assert definition_payload["xianxia"]["actions_per_turn"] == 2
    assert definition_payload["xianxia"]["honor"] == "Honorable"
    assert definition_payload["xianxia"]["reputation"] == "Unknown"
    assert definition_payload["xianxia"]["attributes"] == {
        "str": 1,
        "dex": 1,
        "con": 1,
        "int": 1,
        "wis": 1,
        "cha": 1,
    }
    assert definition_payload["xianxia"]["efforts"] == {
        "basic": 1,
        "weapon": 1,
        "guns_explosive": 1,
        "magic": 1,
        "ultimate": 1,
    }
    assert definition_payload["xianxia"]["energies"] == {
        "jing": {"max": 1},
        "qi": {"max": 1},
        "shen": {"max": 1},
    }
    assert definition_payload["xianxia"]["durability"] == {
        "hp_max": 10,
        "stance_max": 10,
        "manual_armor_bonus": 0,
        "defense": 11,
    }
    assert definition_payload["xianxia"]["yin_yang"] == {"yin_max": 1, "yang_max": 1}
    assert definition_payload["xianxia"]["dao"] == {"max": 3}
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["skills"] == {
        "trained": ["Fishing", "Court Etiquette", "Calligraphy"]
    }
    assert definition_payload["xianxia"]["equipment"] == {
        "necessary_weapons": [],
        "necessary_tools": [
            {"name": "Fishing rod, spear, or net", "reason": "Required for Fishing"},
            {"name": "Calligraphy brush", "reason": "Required for Calligraphy"},
        ],
    }
    assert definition_payload["xianxia"]["martial_arts"] == [
        {
            "name": "Demon's Fist",
            "systems_ref": {
                "library_slug": XIANXIA_SYSTEM_CODE,
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "entry_key": "xianxia|martial_art|xianxia-homebrew|demons-fist",
                "slug": "demons-fist",
                "title": "Demon's Fist",
                "entry_type": "martial_art",
            },
            "current_rank": "Novice",
            "current_rank_key": "novice",
            "learned_rank_refs": [
                "xianxia:demons-fist:initiate",
                "xianxia:demons-fist:novice",
            ],
            "starting_package": True,
            "rank_records_status": "rank_advancement_metadata_seeded",
        },
        {
            "name": "Heavenly Palm",
            "systems_ref": {
                "library_slug": XIANXIA_SYSTEM_CODE,
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "entry_key": "xianxia|martial_art|xianxia-homebrew|heavenly-palm",
                "slug": "heavenly-palm",
                "title": "Heavenly Palm",
                "entry_type": "martial_art",
            },
            "current_rank": "Initiate",
            "current_rank_key": "initiate",
            "learned_rank_refs": ["xianxia:heavenly-palm:initiate"],
            "starting_package": True,
            "rank_records_status": "rank_advancement_metadata_seeded",
        },
    ]
    assert definition_payload["xianxia"]["generic_techniques"] == []
    assert definition_payload["xianxia"]["variants"] == []
    assert definition_payload["xianxia"]["dao_immolating_techniques"] == {
        "prepared": [],
        "use_history": [],
    }
    assert definition_payload["xianxia"]["approval_requests"] == []
    assert definition_payload["xianxia"]["companions"] == []
    assert definition_payload["xianxia"]["advancement_history"] == []

    import_payload = yaml.safe_load(
        (
            app.config["TEST_CAMPAIGNS_DIR"]
            / "linden-pass"
            / "characters"
            / "lotus-wake"
            / "import.yaml"
        ).read_text(encoding="utf-8")
    )
    assert import_payload["source_path"] == "builder://xianxia-create"

    record = get_character("lotus-wake")
    assert record is not None
    assert record.definition.system == XIANXIA_SYSTEM_CODE
    state = record.state_record.state
    assert state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert state["spell_slots"] == []
    assert state["resources"] == []
    assert state["inventory"] == []
    assert state["currency"] == {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0, "other": []}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 0,
        "current_stance": 10,
        "temp_stance": 0,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert state["xianxia"]["dao"] == {"current": 0}
    assert state["xianxia"]["currency"] == {
        "coin": 0,
        "supply": 0,
        "spirit_stones": 0,
    }
    assert state["xianxia"]["inventory"] == {"enabled": False, "quantities": []}

    armored_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Armored Wake",
            "character_slug": "",
            **_armored_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **_martial_art_data(),
            "manual_armor_bonus": "2",
        },
        follow_redirects=False,
    )
    assert armored_response.status_code == 302
    assert armored_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/armored-wake"
    )

    armored_definition_payload = _read_character_definition(app, "armored-wake")
    assert armored_definition_payload["xianxia"]["attributes"]["con"] == 3
    assert armored_definition_payload["xianxia"]["durability"] == {
        "hp_max": 10,
        "stance_max": 10,
        "manual_armor_bonus": 2,
        "defense": 15,
    }

    grant_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Dao Granted",
            "character_slug": "",
            **_attribute_data(),
            **_effort_data(),
            **_energy_data(),
            **_skill_data(),
            **_three_initiate_martial_art_data(),
            "dao_current": "2",
        },
        follow_redirects=False,
    )
    assert grant_response.status_code == 302
    assert grant_response.headers["Location"].endswith("/campaigns/linden-pass/characters/dao-granted")

    grant_definition_payload = _read_character_definition(app, "dao-granted")
    assert grant_definition_payload["xianxia"]["dao"] == {"max": 3}
    assert grant_definition_payload["xianxia"]["equipment"] == {
        "necessary_weapons": [
            {"name": "Jian", "reason": "Required by Taoist Blade"},
        ],
        "necessary_tools": [
            {"name": "Fishing rod, spear, or net", "reason": "Required for Fishing"},
            {"name": "Calligraphy brush", "reason": "Required for Calligraphy"},
        ],
    }
    assert [
        martial_art["current_rank_key"]
        for martial_art in grant_definition_payload["xianxia"]["martial_arts"]
    ] == ["initiate", "initiate", "initiate"]
    grant_record = get_character("dao-granted")
    assert grant_record is not None
    assert grant_record.state_record.state["xianxia"]["dao"] == {"current": 2}

    expected_messages = {
        "edit": app_module.NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE,
        "level-up": XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
        "progression-repair": XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
        "retraining": XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
    }
    for route_suffix, expected_message in expected_messages.items():
        for method_name in ("get", "post"):
            response = getattr(client, method_name)(
                f"/campaigns/linden-pass/characters/arden-march/{route_suffix}",
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")
            route_landing = client.get(response.headers["Location"])
            assert expected_message in route_landing.get_data(as_text=True)

    landing = client.get("/campaigns/linden-pass/characters/arden-march")
    html = landing.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/arden-march/edit" not in html
    assert "/campaigns/linden-pass/characters/arden-march/level-up" not in html
    assert "/campaigns/linden-pass/characters/arden-march/progression-repair" not in html
    assert "/campaigns/linden-pass/characters/arden-march/retraining" not in html
    assert "Edit character" not in html
    assert "Level up" not in html
    assert "Prepare for level-up" not in html


def test_xianxia_create_picker_allows_seeded_and_gm_custom_martial_arts(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
            }
        ]

    _write_campaign_config(app, _mutate)
    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        service.create_custom_campaign_entry(
            "linden-pass",
            title="Jade Meteor Palm",
            entry_type="martial_art",
            slug_leaf="jade-meteor-palm",
            provenance="GM table custom art",
            visibility="dm",
            search_metadata="starter option jade meteor",
            body_markdown=(
                "## Ranks\n"
                "Initiate: Jade energy gathers in the palm.\n\n"
                "Novice: The strike falls like a meteor."
            ),
            actor_user_id=users["dm"]["id"],
            can_set_private=True,
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.get("/campaigns/linden-pass/characters/new")
    assert create_response.status_code == 200
    create_html = create_response.get_data(as_text=True)
    assert 'value="demons-fist"' in create_html
    assert 'value="custom-linden-pass-jade-meteor-palm"' in create_html
    assert "Jade Meteor Palm (CUSTOM-LINDEN-PASS)" in create_html

    submit_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            "name": "Jade Lotus",
            "character_slug": "",
            "attribute_str": "1",
            "attribute_dex": "1",
            "attribute_con": "1",
            "attribute_int": "1",
            "attribute_wis": "1",
            "attribute_cha": "1",
            "effort_basic": "1",
            "effort_weapon": "1",
            "effort_guns_explosive": "1",
            "effort_magic": "1",
            "effort_ultimate": "1",
            "energy_jing": "1",
            "energy_qi": "1",
            "energy_shen": "1",
            "trained_skill_1": "Fishing",
            "trained_skill_2": "Court Etiquette",
            "trained_skill_3": "Calligraphy",
            "martial_art_1_slug": "demons-fist",
            "martial_art_1_rank": "novice",
            "martial_art_2_slug": "custom-linden-pass-jade-meteor-palm",
            "martial_art_2_rank": "initiate",
            "martial_art_3_slug": "",
            "martial_art_3_rank": "",
        },
        follow_redirects=False,
    )

    assert submit_response.status_code == 302
    assert submit_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/jade-lotus"
    )
    definition_payload = _read_character_definition(app, "jade-lotus")
    martial_arts = definition_payload["xianxia"]["martial_arts"]
    assert [art["systems_ref"]["slug"] for art in martial_arts] == [
        "demons-fist",
        "custom-linden-pass-jade-meteor-palm",
    ]
    custom_art = martial_arts[1]
    assert custom_art["systems_ref"] == {
        "library_slug": XIANXIA_SYSTEM_CODE,
        "source_id": "CUSTOM-LINDEN-PASS",
        "entry_key": "xianxia|custom|linden-pass|jade-meteor-palm",
        "slug": "custom-linden-pass-jade-meteor-palm",
        "title": "Jade Meteor Palm",
        "entry_type": "martial_art",
    }
    assert custom_art["current_rank"] == "Initiate"
    assert custom_art["current_rank_key"] == "initiate"
    assert custom_art["learned_rank_refs"] == [
        "xianxia:custom-linden-pass-jade-meteor-palm:initiate"
    ]
    assert custom_art["rank_records_status"] == "gm_authored_custom_markdown"
    assert custom_art["custom_martial_art"] is True
    assert custom_art["xianxia_custom_martial_art"] is True


def test_xianxia_read_sheet_keeps_shared_controls_without_dnd_authoring(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Controls" in html
    assert "Assignment controls" in html
    assert "Delete character" in html
    assert "Edit character" not in html
    assert "Level up" not in html
    assert "Prepare for level-up" not in html
    assert "?page=spellcasting" not in html


def test_xianxia_character_sheet_renders_and_links_xianxia_systems_entries(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
            }
        ]

    _write_campaign_config(app, _mutate_campaign)

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        service.ensure_builtin_library_seeded(DND_5E_SYSTEM_CODE)
        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            title="DND Impostor Xianxia Source",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            DND_5E_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            entry_types=["martial_art"],
            entries=[
                {
                    "entry_key": "dnd-5e|martial_art|xianxia-homebrew|demons-fist",
                    "entry_type": "martial_art",
                    "slug": "demons-fist",
                    "title": "DND Demon's Fist",
                    "search_text": "demon fist dnd impostor",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"facet": "martial_art"},
                    "body": {},
                    "rendered_html": "<p>DND impostor fist body must not render.</p>",
                }
            ],
        )
        demons_fist = service.get_entry_by_slug_for_campaign("linden-pass", "demons-fist")
        assert demons_fist is not None
        assert demons_fist.library_slug == XIANXIA_SYSTEM_CODE

    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Systems Link Crane"),
        follow_redirects=False,
    )
    martial_arts_response = client.get(
        "/campaigns/linden-pass/characters/systems-link-crane?mode=read&page=martial_arts"
    )
    techniques_response = client.get(
        "/campaigns/linden-pass/characters/systems-link-crane?mode=read&page=techniques"
    )
    entry_response = client.get("/campaigns/linden-pass/systems/entries/demons-fist")

    assert create_response.status_code == 302
    assert martial_arts_response.status_code == 200
    assert techniques_response.status_code == 200
    assert entry_response.status_code == 200
    martial_arts_html = martial_arts_response.get_data(as_text=True)
    techniques_html = techniques_response.get_data(as_text=True)
    entry_html = entry_response.get_data(as_text=True)

    assert 'href="/campaigns/linden-pass/systems/entries/demons-fist"' in martial_arts_html
    assert "#xianxia-demons-fist-initiate" in martial_arts_html
    assert 'href="/campaigns/linden-pass/systems/entries/recoup"' in techniques_html
    assert "DND Demon" not in martial_arts_html
    assert "DND Demon" not in techniques_html
    assert "Demon" in entry_html
    assert "Qi Fist Technique" in entry_html
    assert "DND Demon" not in entry_html
    assert "DND impostor fist body must not render." not in entry_html


def test_xianxia_generic_techniques_and_basic_actions_browse_search_and_link_from_sheet(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
            }
        ]

    _write_campaign_config(app, _mutate_campaign)

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        qi_blast = service.get_entry_by_slug_for_campaign("linden-pass", "qi-blast")
        throat_jab = service.get_entry_by_slug_for_campaign("linden-pass", "throat-jab")

        assert qi_blast is not None
        assert qi_blast.library_slug == XIANXIA_SYSTEM_CODE
        assert qi_blast.entry_type == "generic_technique"
        assert throat_jab is not None
        assert throat_jab.library_slug == XIANXIA_SYSTEM_CODE
        assert throat_jab.entry_type == "basic_action"

    def _mutate_character(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["classes"] = [
            {
                "row_id": "xianxia-row-1",
                "class_name": "Mortal Cultivator",
                "level": 0,
            }
        ]
        profile["class_level_text"] = "Mortal Cultivator"
        profile["class_ref"] = {}
        profile["subclass_ref"] = {}
        profile["species"] = ""
        profile["species_ref"] = {}
        profile["background"] = ""
        profile["background_ref"] = {}
        payload["profile"] = profile
        payload["system"] = XIANXIA_SYSTEM_CODE
        payload["spellcasting"] = {}
        payload["features"] = []
        payload["xianxia"] = {
            **dict(payload.get("xianxia") or {}),
            "generic_techniques": [
                {
                    "name": "Qi Blast",
                    "systems_ref": _systems_ref(qi_blast),
                }
            ],
        }

    _write_character_definition(app, "arden-march", _mutate_character)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}"
    )
    generic_category_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/generic_technique"
    )
    basic_action_category_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/basic_action"
    )
    generic_search_response = client.get("/campaigns/linden-pass/systems/search?q=Qi+Blast")
    basic_action_search_response = client.get("/campaigns/linden-pass/systems/search?q=Throat+Jab")
    generic_entry_response = client.get("/campaigns/linden-pass/systems/entries/qi-blast")
    basic_action_entry_response = client.get("/campaigns/linden-pass/systems/entries/throat-jab")
    sheet_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=techniques")

    assert source_response.status_code == 200
    source_html = source_response.get_data(as_text=True)
    assert "Xianxia Homebrew" in source_html
    assert "Generic Techniques" in source_html
    assert "Basic Actions" in source_html
    assert (
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/generic_technique"
        in source_html
    )
    assert (
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/basic_action"
        in source_html
    )

    assert generic_category_response.status_code == 200
    generic_category_html = generic_category_response.get_data(as_text=True)
    assert "Xianxia Homebrew: Generic Techniques" in generic_category_html
    assert "Qi Blast" in generic_category_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in generic_category_html

    assert basic_action_category_response.status_code == 200
    basic_action_category_html = basic_action_category_response.get_data(as_text=True)
    assert "Xianxia Homebrew: Basic Actions" in basic_action_category_html
    assert "Throat Jab" in basic_action_category_html
    assert "/campaigns/linden-pass/systems/entries/throat-jab" in basic_action_category_html

    assert generic_search_response.status_code == 200
    generic_search_html = generic_search_response.get_data(as_text=True)
    assert "Qi Blast" in generic_search_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in generic_search_html

    assert basic_action_search_response.status_code == 200
    basic_action_search_html = basic_action_search_response.get_data(as_text=True)
    assert "Throat Jab" in basic_action_search_html
    assert "/campaigns/linden-pass/systems/entries/throat-jab" in basic_action_search_html

    assert generic_entry_response.status_code == 200
    generic_entry_html = generic_entry_response.get_data(as_text=True)
    assert "Spend a point of Qi" in generic_entry_html
    assert "Insight Cost" in generic_entry_html

    assert basic_action_entry_response.status_code == 200
    basic_action_entry_html = basic_action_entry_response.get_data(as_text=True)
    assert "Basic Action Details" in basic_action_entry_html
    assert "1 Round" in basic_action_entry_html

    assert sheet_response.status_code == 200
    sheet_html = sheet_response.get_data(as_text=True)
    assert 'href="/campaigns/linden-pass/systems/entries/qi-blast"' in sheet_html
    assert 'href="/campaigns/linden-pass/systems/entries/throat-jab"' in sheet_html
    assert "Generic Techniques" in sheet_html
    assert "Basic Actions" in sheet_html
    assert "?page=spellcasting" not in sheet_html


def test_xianxia_read_view_exposes_xianxia_shell_subpages_and_keeps_cultivation_direct(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Shell Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/shell-crane"
    )

    response = client.get("/campaigns/linden-pass/characters/shell-crane?mode=read")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    target_subpages = _read_shell_target_subpages(html)
    assert target_subpages == [
        "quick",
        "martial_arts",
        "techniques",
        "resources",
        "skills",
        "equipment",
        "inventory",
        "portrait",
        "personal",
        "notes",
        "controls",
    ]
    assert "Quick Reference" in html
    assert "Martial Arts" in html
    assert "Techniques" in html
    assert "Resources" in html
    assert "Skills" in html
    assert "Equipment" in html
    assert "Inventory" in html
    assert "Portrait" in html
    assert "Personal" in html
    assert "Notes" in html
    assert "Controls" in html
    assert "/campaigns/linden-pass/characters/shell-crane/cultivation" in html
    assert 'data-character-read-target-subpage="cultivation"' not in html
    assert 'data-character-read-target-subpage="spellcasting"' not in html
    assert 'data-character-read-target-subpage="features"' not in html
