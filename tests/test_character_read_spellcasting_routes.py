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

def test_xianxia_hides_dnd_spellcasting_read_and_session_affordances(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    session_response = client.get("/campaigns/linden-pass/session/character?character=arden-march&page=spells")

    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "At a glance" in read_html
    assert "?page=spellcasting" not in read_html
    assert "/spellcasting/" not in read_html
    assert "Spell slots" not in read_html
    assert 'class="spell-card' not in read_html

    assert session_response.status_code == 200
    session_html = session_response.get_data(as_text=True)
    assert "Quick Reference" in session_html
    assert "Martial Arts" in session_html
    assert "Spell slots" not in session_html
    assert "page=spells" not in session_html
    assert "/spellcasting/" not in session_html


def test_xianxia_blocks_dnd_spellcasting_management_routes(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?q=message"
    )
    assert search_response.status_code == 404
    assert search_response.get_json()["message"] == app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE

    spell_add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        follow_redirects=False,
    )
    assert spell_add_response.status_code == 302
    assert spell_add_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    spell_update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/update",
        follow_redirects=False,
    )
    assert spell_update_response.status_code == 302
    assert spell_update_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    spell_remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        follow_redirects=False,
    )
    assert spell_remove_response.status_code == 302
    assert spell_remove_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    slot_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/1",
        follow_redirects=False,
    )
    assert slot_response.status_code == 302
    assert slot_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    landing = client.get(spell_add_response.headers["Location"])
    assert app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE in landing.get_data(as_text=True)


def test_dnd5e_spellcasting_and_session_slots_remain_enabled_with_xianxia_policy_present(
    app, client, sign_in, users, get_character
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "DND-5E"
        payload["systems_library"] = "DND-5E"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?q=message"
    )

    assert search_response.status_code == 200
    assert (
        search_response.get_json()["message"]
        != app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE
    )

    record = get_character("arden-march")
    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 1},
        follow_redirects=False,
    )

    assert response.status_code == 302
    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 1


def test_xianxia_milestone1_dnd5e_read_and_session_spellcasting_surfaces_remain_dnd5e(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "DND-5E"
        payload["systems_library"] = "DND-5E"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    quick_reference = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")
    spellcasting = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    session_spellcasting = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=session&page=spellcasting"
    )

    assert quick_reference.status_code == 200
    quick_html = quick_reference.get_data(as_text=True)
    assert "?page=spellcasting" in quick_html
    assert "?page=martial_arts" not in quick_html
    assert "?page=techniques" not in quick_html
    assert "/cultivation" not in quick_html

    assert spellcasting.status_code == 200
    spellcasting_html = spellcasting.get_data(as_text=True)
    assert "Spellcasting" in spellcasting_html
    assert "Message" in spellcasting_html
    assert "1 action" in spellcasting_html
    assert "120 feet" in spellcasting_html
    assert "Martial Arts" not in spellcasting_html
    assert "Jing" not in spellcasting_html
    assert "Dao" not in spellcasting_html
    assert re.search(
        r'<h3 class="visually-hidden spell-slot-pool-title">',
        spellcasting_html,
    ) is not None

    assert session_spellcasting.status_code == 200
    session_html = session_spellcasting.get_data(as_text=True)
    assert "Spellcasting" in session_html
    assert "Spell slots" in session_html
    assert "Message" in session_html
    assert "Martial Arts" not in session_html
    assert "Stance" not in session_html
    assert "Dao" not in session_html


def test_spellcasting_subpage_is_only_shown_for_casters_and_holds_spell_list(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    caster_quick = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")
    caster_spellcasting = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    noncaster_quick = client.get("/campaigns/linden-pass/characters/tobin-slate?mode=read&page=quick")

    assert caster_quick.status_code == 200
    caster_quick_html = caster_quick.get_data(as_text=True)
    assert "?page=spellcasting" in caster_quick_html
    assert "Sorcerer" in caster_quick_html
    assert "Spell slots" in caster_quick_html
    assert 'class="spell-card' not in caster_quick_html

    assert caster_spellcasting.status_code == 200
    caster_spellcasting_html = caster_spellcasting.get_data(as_text=True)
    assert "Spellcasting" in caster_spellcasting_html
    assert "Message" in caster_spellcasting_html
    assert "1 action" in caster_spellcasting_html
    assert "120 feet" in caster_spellcasting_html
    assert "1 round" in caster_spellcasting_html
    assert "V, S, M" in caster_spellcasting_html

    assert noncaster_quick.status_code == 200
    noncaster_quick_html = noncaster_quick.get_data(as_text=True)
    assert "?page=spellcasting" not in noncaster_quick_html


def test_spellcasting_subpage_shows_supported_feat_spell_rows_as_read_only_sections(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-mage-hand", "title": "Mage Hand", "level": 0, "class_lists": {"TCE": ["Artificer"], "PHB": ["Wizard"]}},
            {"slug": "phb-spell-cure-wounds", "title": "Cure Wounds", "level": 1, "class_lists": {"TCE": ["Artificer"], "PHB": ["Cleric", "Druid"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 5"
        profile["classes"] = [{"class_name": "Fighter", "level": 5}]
        payload["profile"] = profile
        source_row_id = "feat-spell-source:artificer-initiate:species-feat-1"
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [],
            "source_rows": [
                {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feat",
                    "title": "Artificer Initiate",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 12,
                    "spell_attack_bonus": 4,
                }
            ],
            "spells": [
                _spell_payload(
                    spell_entries["phb-spell-mage-hand"],
                    source="PHB",
                    mark="Cantrip",
                    is_bonus_known=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="feat",
                    spell_source_row_title="Artificer Initiate",
                    spell_source_ability_key="int",
                    grant_source_label="Artificer Initiate",
                ),
                _spell_payload(
                    spell_entries["phb-spell-cure-wounds"],
                    source="PHB",
                    is_bonus_known=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="feat",
                    spell_source_row_title="Artificer Initiate",
                    spell_source_ability_key="int",
                    grant_source_label="Artificer Initiate",
                    spell_access_type="free_cast",
                    spell_access_uses=1,
                    spell_access_reset_on="long_rest",
                ),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Artificer Initiate" in html
    assert "Feat spells" in html
    assert "Intelligence spellcasting" in html
    assert "Save DC 12" in html
    assert "Attack +4" in html
    assert "Feature granted" in html
    assert "1 / Long Rest" in html
    assert "Feat-granted spells stay read-only here in this slice." in html
    assert "Prepare spell" not in html
    assert "Add spellbook spell" not in html
    assert "Remove cantrip" not in html


def test_spellcasting_subpage_groups_compact_cards_by_level_and_local_source_package(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-message", "title": "Message", "level": 0, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-sleep", "title": "Sleep", "level": 1, "class_lists": {"PHB": ["Sorcerer", "Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        source_row_id = "feat-spell-source:fey-touched"
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Sorcerer",
                    "level": 5,
                    "caster_progression": "full",
                    "spell_mode": "known",
                    "spellcasting_ability": "Charisma",
                    "spell_save_dc": 15,
                    "spell_attack_bonus": 7,
                },
            ],
            "source_rows": [
                {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feat",
                    "title": "Fey Touched",
                    "spellcasting_ability": "Charisma",
                    "spell_save_dc": 15,
                    "spell_attack_bonus": 7,
                }
            ],
            "spells": [
                _spell_payload(
                    spell_entries["phb-spell-message"],
                    source="PHB",
                    mark="Cantrip",
                    class_row_id="class-row-1",
                ),
                _spell_payload(
                    spell_entries["phb-spell-magic-missile"],
                    source="PHB",
                    mark="Known",
                    class_row_id="class-row-1",
                    at_higher_levels="The spell creates one more dart for each slot level above 1st.",
                ),
                _spell_payload(
                    spell_entries["phb-spell-sleep"],
                    source="PHB",
                    is_bonus_known=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="feat",
                    grant_source_label="Fey Touched",
                ),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "spellcasting-count-grid" not in html
    assert "spell-card-grid" in html
    assert html.count('class="spell-card"') == 3
    assert "data-character-spell-modal-trigger" in html
    assert "data-character-spell-modal" in html
    assert "<h4>Cantrips</h4>" in html
    assert "<h4>1st level</h4>" in html
    assert "Upcast" in html
    assert "Feat spells" in html
    assert "<h3>Fey Touched</h3>" not in html
    assert html.index("<h4>1st level</h4>") < html.index("Fey Touched") < html.index("Sleep")


def test_spellcasting_subpage_hides_armorer_always_prepared_source_package(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-message", "title": "Message", "level": 0, "class_lists": {"PHB": ["Artificer"]}},
            {"slug": "phb-spell-cure-wounds", "title": "Cure Wounds", "level": 1, "class_lists": {"PHB": ["Artificer"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Artificer"]}},
            {"slug": "phb-spell-thunderwave", "title": "Thunderwave", "level": 1, "class_lists": {"PHB": ["Artificer"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Artificer 5"
        profile["classes"] = [{"class_name": "Artificer", "level": 5}]
        payload["profile"] = profile
        source_row_id = "subclass-feature:armorer-spells"
        payload["spellcasting"] = {
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 16,
            "spell_attack_bonus": 8,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 2},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                    "caster_progression": "artificer",
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 16,
                    "spell_attack_bonus": 8,
                },
            ],
            "source_rows": [
                {
                    "source_row_id": source_row_id,
                    "source_row_kind": "source",
                    "title": "Armorer Spells",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 16,
                    "spell_attack_bonus": 8,
                }
            ],
            "spells": [
                _spell_payload(
                    spell_entries["phb-spell-message"],
                    source="Artificer",
                    mark="Cantrip",
                    class_row_id="class-row-1",
                ),
                _spell_payload(
                    spell_entries["phb-spell-cure-wounds"],
                    source="Artificer",
                    mark="Prepared",
                    class_row_id="class-row-1",
                ),
                _spell_payload(
                    spell_entries["phb-spell-magic-missile"],
                    source="Artificer",
                    is_always_prepared=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="source",
                    spell_source_row_title="Armorer Spells",
                    grant_source_label="Armorer Spells",
                ),
                _spell_payload(
                    spell_entries["phb-spell-thunderwave"],
                    source="Artificer",
                    is_always_prepared=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="source",
                    spell_source_row_title="Armorer Spells",
                    grant_source_label="Armorer Spells",
                ),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    current_panel_html = html.split('id="character-spell-current-view"', 1)[1]
    assert "Intelligence spellcasting" in html
    assert "Save DC 16" in html
    assert "Attack +8" in html
    assert "Prepared spells" in html
    assert "Preparation" in html
    assert "Magic Missile" in current_panel_html
    assert "Thunderwave" in current_panel_html
    assert current_panel_html.count("Always prepared") >= 2
    assert 'class="spell-source-package"' not in current_panel_html
    assert "<h5>Armorer Spells</h5>" not in current_panel_html


def test_spellcasting_subpage_can_manage_ritual_caster_ritual_book(app, client, sign_in, users):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-find-familiar", "title": "Find Familiar", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-alarm", "title": "Alarm", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    source_row_id = "feat-spell-source:phb-feat-ritual-caster:species-feat-1"

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 5"
        profile["classes"] = [{"class_name": "Fighter", "level": 5}]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["int"] = {"score": 14, "modifier": 2, "save_bonus": 2}
        stats["ability_scores"] = ability_scores
        stats["proficiency_bonus"] = 3
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "ritual-caster-1",
                "name": "Ritual Caster",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "activation_type": "passive",
                "systems_ref": {
                    "entry_key": "dnd-5e|feat|phb|ritual-caster",
                    "entry_type": "feat",
                    "title": "Ritual Caster",
                    "slug": "phb-feat-ritual-caster",
                    "source_id": "PHB",
                },
                "spell_manager": {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feat",
                    "title": "Ritual Caster (Wizard)",
                    "mode": "ritual_book",
                    "spell_list_class_name": "Wizard",
                    "spellcasting_ability": "Intelligence",
                    "spellcasting_ability_key": "int",
                    "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                },
            }
        ]
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [],
            "source_rows": [],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Ritual Caster (Wizard)" in page_html
    assert "Ritual book" in page_html
    assert "Add ritual spell" in page_html
    assert "No spells recorded yet for this class row." in page_html

    search_response = client.get(
        f"/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=ritual_book&q=detect&target_class_row_id={source_row_id}"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching ritual spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-detect-magic"]

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "ritual_book",
            "selected_value": "phb-spell-detect-magic",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    spells_by_name = {spell["name"]: spell for spell in updated_definition["spellcasting"]["spells"]}
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == source_row_id

    updated_page = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    updated_html = updated_page.get_data(as_text=True)
    assert "Detect Magic" in updated_html
    assert "Ritual Book" in updated_html
    assert "Remove from ritual book" in updated_html

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": f"feat:{source_row_id}::phb-spell-detect-magic",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    removed_definition = _read_character_definition(app, "arden-march")
    assert removed_definition["spellcasting"]["spells"] == []
    removed_page = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    removed_html = removed_page.get_data(as_text=True)
    assert "Ritual Caster (Wizard)" in removed_html
    assert "Add ritual spell" in removed_html
    assert "No spells recorded yet for this class row." in removed_html


def test_spellcasting_subpage_can_manage_campaign_feature_ritual_book(app, client, sign_in, users):
    _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-alarm", "title": "Alarm", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-find-familiar", "title": "Find Familiar", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    source_row_id = "feature-spell-source:mechanics-harbor-ritual-book:mechanics-harbor-ritual-book"

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 5"
        profile["classes"] = [{"class_name": "Fighter", "level": 5}]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["int"] = {"score": 14, "modifier": 2, "save_bonus": 2}
        stats["ability_scores"] = ability_scores
        stats["proficiency_bonus"] = 3
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "harbor-ritual-book-1",
                "name": "Harbor Ritual Book",
                "category": "custom_feature",
                "source": "Campaign",
                "description_markdown": "",
                "activation_type": "special",
                "page_ref": "mechanics/harbor-ritual-book",
                "spell_manager": {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feature",
                    "title": "Harbor Ritual Book",
                    "mode": "ritual_book",
                    "spell_list_class_name": "Wizard",
                    "spellcasting_ability": "Intelligence",
                    "spellcasting_ability_key": "int",
                    "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                },
            }
        ]
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [],
            "source_rows": [],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Harbor Ritual Book" in page_html
    assert "Ritual book" in page_html
    assert "Add ritual spell" in page_html

    search_response = client.get(
        f"/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=ritual_book&q=alarm&target_class_row_id={source_row_id}"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching ritual spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-alarm"]

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "ritual_book",
            "selected_value": "phb-spell-alarm",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    spells_by_name = {spell["name"]: spell for spell in updated_definition["spellcasting"]["spells"]}
    assert spells_by_name["Alarm"]["mark"] == "Ritual Book"
    assert spells_by_name["Alarm"]["spell_source_row_id"] == source_row_id

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": f"feature:{source_row_id}::phb-spell-alarm",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    removed_definition = _read_character_definition(app, "arden-march")
    assert removed_definition["spellcasting"]["spells"] == []


def test_spellcasting_subpage_can_search_add_and_remove_known_spells(app, client, sign_in, users):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-message", "title": "Message", "level": 0, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-shield", "title": "Shield", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-find-familiar", "title": "Find Familiar", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
            ],
            "spells": [
                _spell_payload(spell_entries["phb-spell-message"], source="Sorcerer"),
                _spell_payload(spell_entries["phb-spell-magic-missile"], source="Sorcerer"),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Known spells" in page_html
    assert "Add known spell" in page_html
    assert "Remove cantrip" not in page_html

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=spell&q=find"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spell",
            "selected_value": "phb-spell-shield",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    updated_spells = list((updated_definition.get("spellcasting") or {}).get("spells") or [])
    shield_spell = next(spell for spell in updated_spells if spell.get("name") == "Shield")
    assert shield_spell["mark"] == "Known"

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-shield",
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    final_definition = _read_character_definition(app, "arden-march")
    final_spell_names = [str(spell.get("name") or "") for spell in list((final_definition.get("spellcasting") or {}).get("spells") or [])]
    assert "Shield" not in final_spell_names


def test_spellcasting_cantrip_search_targets_sorcerer_row_by_list_name(
    app, client, sign_in, users
):
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["class"],
            entries=[
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-sorcerer",
                    "entry_type": "class",
                    "slug": "phb-class-sorcerer",
                    "title": "Sorcerer",
                    "source_page": "100",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "sorcerer class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 6},
                        "spellcasting_ability": "cha",
                        "caster_progression": "full",
                        "cantrip_progression": [4, 4, 5, 5, 5],
                    },
                    "body": {},
                    "rendered_html": "<p>Sorcerer.</p>",
                },
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "slug": "phb-class-wizard",
                    "title": "Wizard",
                    "source_page": "101",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "wizard class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 6},
                        "spellcasting_ability": "int",
                        "caster_progression": "full",
                        "cantrip_progression": [3, 3, 3, 3, 4],
                    },
                    "body": {},
                    "rendered_html": "<p>Wizard.</p>",
                },
            ],
        )

    _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-mage-hand", "title": "Mage Hand", "level": 0, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-fire-bolt", "title": "Fire Bolt", "level": 0, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        payload["profile"] = {
            "class_level_text": "Sorcerer 5 / Wizard 3",
            "classes": [
                {
                    "row_id": "class-row-1",
                    "class_name": "Sorcerer",
                    "level": 5,
                    "systems_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-sorcerer",
                        "entry_type": "class",
                        "title": "Sorcerer",
                        "slug": "phb-class-sorcerer",
                        "source_id": "PHB",
                    },
                },
                {
                    "row_id": "class-row-2",
                    "class_name": "Wizard",
                    "level": 3,
                    "systems_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                        "entry_type": "class",
                        "title": "Wizard",
                        "slug": "phb-class-wizard",
                        "source_id": "PHB",
                    },
                },
            ],
            "species": "Human",
            "background": "Courier",
            "alignment": "Neutral Good",
            "size": "Medium",
            "experience_model": "Milestone",
        }
        payload["source"] = {
            "source_path": "builder://native-multiclass",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-10T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Sorcerer (Wild Magic)",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-sorcerer",
                        "entry_type": "class",
                        "title": "Sorcerer",
                        "slug": "phb-class-sorcerer",
                        "source_id": "PHB",
                    },
                    "spell_list_class_name": "Sorcerer (PHB)",
                    "level": 5,
                    "caster_progression": "full",
                    "spell_mode": "known",
                    "spellcasting_ability": "Charisma",
                    "spell_save_dc": 15,
                    "spell_attack_bonus": 7,
                },
                {
                    "class_row_id": "class-row-2",
                    "class_name": "Wizard",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                        "entry_type": "class",
                        "title": "Wizard",
                        "slug": "phb-class-wizard",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "known",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 15,
                    "spell_attack_bonus": 5,
                },
            ],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=cantrip&q=mage&target_class_row_id=class-row-1"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload == {
        "results": [
            {
                "entry_slug": "phb-spell-mage-hand",
                "title": "Mage Hand",
                "level_label": "Cantrip",
                "source_id": "PHB",
                "select_label": "Mage Hand - Cantrip - PHB",
            }
        ],
        "message": "Found 1 matching cantrips.",
    }

    wizard_cantrip_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=cantrip&q=fire&target_class_row_id=class-row-1"
    )
    assert wizard_cantrip_response.status_code == 200
    assert wizard_cantrip_response.get_json() == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    invalid_add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "cantrip",
            "selected_value": "phb-spell-fire-bolt",
            "target_class_row_id": "class-row-1",
        },
        follow_redirects=False,
    )
    assert invalid_add_response.status_code == 302
    after_invalid = _read_character_definition(app, "arden-march")
    assert list((after_invalid.get("spellcasting") or {}).get("spells") or []) == []

    valid_add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "cantrip",
            "selected_value": "phb-spell-mage-hand",
            "target_class_row_id": "class-row-1",
        },
        follow_redirects=False,
    )
    assert valid_add_response.status_code == 302
    updated_definition = _read_character_definition(app, "arden-march")
    sorcerer_rows = [
        spell for spell in list((updated_definition.get("spellcasting") or {}).get("spells") or [])
        if str(spell.get("name") or "").strip() == "Mage Hand"
    ]
    assert len(sorcerer_rows) == 1
    assert sorcerer_rows[0]["class_row_id"] == "class-row-1"


def test_spellcasting_cantrip_search_falls_back_to_phb_class_list_for_sparse_spell_metadata(
    app, client, sign_in, users
):
    _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-firebolt", "title": "Fire Bolt", "level": 0},
            {"slug": "phb-spell-sacredflame", "title": "Sacred Flame", "level": 0},
            {"slug": "phb-spell-magicmissile", "title": "Magic Missile", "level": 1},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"row_id": "class-row-1", "class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Sorcerer",
                    "spell_list_class_name": "Sorcerer (PHB)",
                    "level": 5,
                    "caster_progression": "full",
                    "spell_mode": "known",
                    "spellcasting_ability": "Charisma",
                    "spell_save_dc": 15,
                    "spell_attack_bonus": 7,
                },
            ],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    valid_search = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=cantrip&q=fire&target_class_row_id=class-row-1"
    )
    assert valid_search.status_code == 200
    assert valid_search.get_json() == {
        "results": [
            {
                "entry_slug": "phb-spell-firebolt",
                "title": "Fire Bolt",
                "level_label": "Cantrip",
                "source_id": "PHB",
                "select_label": "Fire Bolt - Cantrip - PHB",
            }
        ],
        "message": "Found 1 matching cantrips.",
    }

    wrong_class_search = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=cantrip&q=sacred&target_class_row_id=class-row-1"
    )
    assert wrong_class_search.status_code == 200
    assert wrong_class_search.get_json() == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    leveled_spell_search = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=cantrip&q=magic&target_class_row_id=class-row-1"
    )
    assert leveled_spell_search.status_code == 200
    assert leveled_spell_search.get_json() == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    invalid_add = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "cantrip",
            "selected_value": "phb-spell-sacredflame",
            "target_class_row_id": "class-row-1",
        },
        follow_redirects=False,
    )
    assert invalid_add.status_code == 302
    after_invalid = _read_character_definition(app, "arden-march")
    assert list((after_invalid.get("spellcasting") or {}).get("spells") or []) == []

    valid_add = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "cantrip",
            "selected_value": "phb-spell-firebolt",
            "target_class_row_id": "class-row-1",
        },
        follow_redirects=False,
    )
    assert valid_add.status_code == 302
    updated_definition = _read_character_definition(app, "arden-march")
    added_spell = next(
        spell
        for spell in list((updated_definition.get("spellcasting") or {}).get("spells") or [])
        if str(spell.get("name") or "").strip() == "Fire Bolt"
    )
    assert added_spell["mark"] == "Cantrip"
    assert added_spell["class_row_id"] == "class-row-1"


def test_spellcasting_search_uses_enabled_systems_sources_only(app, client, sign_in, users):
    def _disable_tce(payload: dict) -> None:
        systems_sources = list(payload.get("systems_sources") or [])
        for index, source in enumerate(systems_sources):
            source_payload = dict(source or {})
            if str(source_payload.get("source_id") or "").strip().upper() != "TCE":
                continue
            source_payload["enabled"] = False
            systems_sources[index] = source_payload
        payload["systems_sources"] = systems_sources

    _write_campaign_config(app, _disable_tce)
    _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-shield", "title": "Shield", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}, "source_id": "PHB"},
            {"slug": "tce-spell-tashascausticbrew", "title": "Tasha's Caustic Brew", "level": 1, "class_lists": {"TCE": ["Sorcerer"]}, "source_id": "TCE"},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
            ],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    hidden_source_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=spell&q=tasha"
    )
    assert hidden_source_response.status_code == 200
    assert hidden_source_response.get_json() == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    visible_source_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=spell&q=shield"
    )
    assert visible_source_response.status_code == 200
    visible_payload = visible_source_response.get_json()
    assert visible_payload["message"] == "Found 1 matching spells."
    assert visible_payload["results"] == [
        {
            "entry_slug": "phb-spell-shield",
            "title": "Shield",
            "level_label": "1st-level",
            "source_id": "PHB",
            "select_label": "Shield - 1st-level - PHB",
        }
    ]


def test_spellcasting_subpage_can_prepare_spells_and_protect_always_prepared_entries(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-guidance", "title": "Guidance", "level": 0, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-cure-wounds", "title": "Cure Wounds", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-bless", "title": "Bless", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Cleric 5"
        profile["classes"] = [{"class_name": "Cleric", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Cleric",
            "spellcasting_ability": "Wisdom",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                _spell_payload(spell_entries["phb-spell-guidance"], source="Cleric"),
                _spell_payload(spell_entries["phb-spell-cure-wounds"], source="Cleric"),
                _spell_payload(spell_entries["phb-spell-bless"], source="Cleric (Always Prepared)", mark="P"),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Prepared spells" in page_html
    assert "Prepare spell" in page_html
    assert "Preparation" in page_html
    assert "Current spells" in page_html
    assert 'data-character-spellcasting-view-switch' in page_html
    assert 'data-character-spellcasting-view-button="current"' in page_html
    assert 'data-character-spellcasting-view-button="preparation"' in page_html
    assert 'data-character-spellcasting-view-panel="current"' in page_html
    assert 'data-character-spellcasting-view-panel="preparation"' in page_html
    assert 'class="spellcasting-count-grid spellcasting-view-count-grid"' in page_html
    assert page_html.index("spellcasting-view-count-grid") < page_html.index('id="character-spell-preparation-view"')
    assert re.search(r'id="character-spell-preparation-view"[^>]+hidden', page_html)
    styles_path = Path(app.root_path) / "static" / "styles.css"
    assert ".spellcasting-view-panel[hidden]" in styles_path.read_text(encoding="utf-8")
    assert "Always prepared" in page_html
    assert 'class="spell-source-package"' not in page_html
    assert page_html.count("Wisdom spellcasting") == 1
    preparation_panel_html = page_html.split('id="character-spell-preparation-view"', 1)[1].split(
        'id="character-spell-manager"',
        1,
    )[0]
    assert "<h3>Cleric 5</h3>" not in preparation_panel_html
    assert "Cure Wounds" in preparation_panel_html
    assert 'data-character-spell-modal-trigger' in preparation_panel_html
    assert "spell-preparation-detail-dialog" in preparation_panel_html

    session_response = client.get("/campaigns/linden-pass/session/character?character=arden-march&page=spells")
    assert session_response.status_code == 200
    session_html = session_response.get_data(as_text=True)
    assert "Always prepared" in session_html
    assert "Cure Wounds" not in session_html

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spell",
            "selected_value": "phb-spell-detect-magic",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    updated_spells = list((updated_definition.get("spellcasting") or {}).get("spells") or [])
    detect_magic = next(spell for spell in updated_spells if spell.get("name") == "Detect Magic")
    bless = next(spell for spell in updated_spells if spell.get("name") == "Bless")
    assert detect_magic["mark"] == "Prepared"
    assert bless["is_always_prepared"] is True

    protected_remove = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-bless",
        },
        follow_redirects=True,
    )
    assert protected_remove.status_code == 200
    protected_html = protected_remove.get_data(as_text=True)
    assert "cannot be removed here" in protected_html

    protected_definition = _read_character_definition(app, "arden-march")
    protected_spell_names = [str(spell.get("name") or "") for spell in list((protected_definition.get("spellcasting") or {}).get("spells") or [])]
    assert "Bless" in protected_spell_names

    cantrip_remove = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-guidance",
        },
        follow_redirects=True,
    )
    assert cantrip_remove.status_code == 200
    cantrip_html = cantrip_remove.get_data(as_text=True)
    assert "cannot be removed here" in cantrip_html

    cantrip_protected_definition = _read_character_definition(app, "arden-march")
    cantrip_protected_names = [
        str(spell.get("name") or "")
        for spell in list((cantrip_protected_definition.get("spellcasting") or {}).get("spells") or [])
    ]
    assert "Guidance" in cantrip_protected_names

    unprepare_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/update",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-detect-magic",
            "prepared_value": "0",
        },
        follow_redirects=False,
    )
    assert unprepare_response.status_code == 302

    final_definition = _read_character_definition(app, "arden-march")
    final_spells_by_name = {
        str(spell.get("name") or ""): spell
        for spell in list((final_definition.get("spellcasting") or {}).get("spells") or [])
    }
    assert final_spells_by_name["Detect Magic"]["mark"] == ""


def test_spellcasting_subpage_can_manage_wizard_spellbooks_and_prepare_spells(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-message", "title": "Message", "level": 0, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-shield", "title": "Shield", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 5"
        profile["classes"] = [{"class_name": "Wizard", "level": 5}]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        stats["ability_scores"] = {
            "intelligence": {"score": 16, "modifier": 3},
        }
        payload["stats"] = stats
        payload["spellcasting"] = {
            "spellcasting_class": "Wizard",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                _spell_payload(spell_entries["phb-spell-message"], source="Wizard", mark="O"),
                _spell_payload(spell_entries["phb-spell-magic-missile"], source="Wizard", mark="O"),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Wizard spellbook" in page_html
    assert "Add spellbook spell" in page_html
    assert "1 / 8" in page_html
    assert "1 / 5" not in page_html

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spellbook",
            "selected_value": "phb-spell-shield",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    updated_spells = list((updated_definition.get("spellcasting") or {}).get("spells") or [])
    magic_missile = next(spell for spell in updated_spells if spell.get("name") == "Magic Missile")
    shield_spell = next(spell for spell in updated_spells if spell.get("name") == "Shield")
    assert magic_missile["mark"] == "Prepared + Spellbook"
    assert shield_spell["mark"] == "Spellbook"

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/update",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-shield",
            "prepared_value": "1",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    final_definition = _read_character_definition(app, "arden-march")
    final_spells = list((final_definition.get("spellcasting") or {}).get("spells") or [])
    final_shield = next(spell for spell in final_spells if spell.get("name") == "Shield")
    assert final_shield["mark"] == "Prepared + Spellbook"


def test_spellcasting_subpage_groups_multiclass_rows_and_allows_same_spell_on_another_row(
    app, client, sign_in, users
):
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["class"],
            entries=[
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "slug": "phb-class-wizard",
                    "title": "Wizard",
                    "source_page": "100",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "wizard class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 6},
                        "spellcasting_ability": "int",
                        "caster_progression": "full",
                        "spells_known_progression_fixed": [6],
                    },
                    "body": {},
                    "rendered_html": "<p>Wizard.</p>",
                },
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-cleric",
                    "entry_type": "class",
                    "slug": "phb-class-cleric",
                    "title": "Cleric",
                    "source_page": "101",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "cleric class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 8},
                        "spellcasting_ability": "wis",
                        "caster_progression": "full",
                        "prepared_spells": "level + wis",
                    },
                    "body": {},
                    "rendered_html": "<p>Cleric.</p>",
                },
            ],
        )
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard", "Cleric"]}},
            {"slug": "phb-spell-bless", "title": "Bless", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 3 / Cleric 3"
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Wizard",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "title": "Wizard",
                    "slug": "phb-class-wizard",
                    "source_id": "PHB",
                },
            },
            {
                "row_id": "class-row-2",
                "class_name": "Cleric",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-cleric",
                    "entry_type": "class",
                    "title": "Cleric",
                    "slug": "phb-class-cleric",
                    "source_id": "PHB",
                },
            },
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://native-multiclass",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-08T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 3},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Wizard",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                        "entry_type": "class",
                        "title": "Wizard",
                        "slug": "phb-class-wizard",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "wizard",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                },
                {
                    "class_row_id": "class-row-2",
                    "class_name": "Cleric",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-cleric",
                        "entry_type": "class",
                        "title": "Cleric",
                        "slug": "phb-class-cleric",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Wisdom",
                    "spell_save_dc": 13,
                    "spell_attack_bonus": 5,
                },
            ],
            "spells": [
                {
                    **_spell_payload(spell_entries["phb-spell-detect-magic"], source="Wizard", mark="O"),
                    "class_row_id": "class-row-1",
                },
                {
                    **_spell_payload(spell_entries["phb-spell-bless"], source="Cleric", mark="P"),
                    "class_row_id": "class-row-2",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Multiclass Spellcasting" in page_html
    assert "Shared spell slots" in page_html
    assert "Wizard 3" in page_html
    assert "Cleric 3" in page_html

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=spell&q=detect&target_class_row_id=class-row-2"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-detect-magic"]

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spell",
            "selected_value": "phb-spell-detect-magic",
            "target_class_row_id": "class-row-2",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    detect_magic_rows = [
        str(spell.get("class_row_id") or "").strip()
        for spell in list((updated_definition.get("spellcasting") or {}).get("spells") or [])
        if str(spell.get("name") or "").strip() == "Detect Magic"
    ]
    assert detect_magic_rows == ["class-row-1", "class-row-2"]


def test_spell_management_search_uses_wizard_list_for_arcane_trickster_rows(app, client, sign_in, users):
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["class"],
            entries=[
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-rogue",
                    "entry_type": "class",
                    "slug": "phb-class-rogue",
                    "title": "Rogue",
                    "source_page": "101",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "rogue class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 8},
                        "subclass_title": "Roguish Archetype",
                    },
                    "body": {},
                    "rendered_html": "<p>Rogue.</p>",
                },
            ],
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["subclass"],
            entries=[
                {
                    "entry_key": "dnd-5e|subclass|phb|phb-subclass-arcane-trickster",
                    "entry_type": "subclass",
                    "slug": "phb-subclass-arcane-trickster",
                    "title": "Arcane Trickster",
                    "source_page": "98",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "arcane trickster rogue subclass",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "class_name": "Rogue",
                        "class_source": "PHB",
                    },
                    "body": {},
                    "rendered_html": "<p>Arcane Trickster.</p>",
                },
            ],
        )
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-bless", "title": "Bless", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-mage-hand", "title": "Mage Hand", "level": 0, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Rogue 3"
        profile["class_ref"] = {
            "entry_key": "dnd-5e|class|phb|phb-class-rogue",
            "entry_type": "class",
            "title": "Rogue",
            "slug": "phb-class-rogue",
            "source_id": "PHB",
        }
        profile["subclass_ref"] = {
            "entry_key": "dnd-5e|subclass|phb|phb-subclass-arcane-trickster",
            "entry_type": "subclass",
            "title": "Arcane Trickster",
            "slug": "phb-subclass-arcane-trickster",
            "source_id": "PHB",
        }
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Rogue",
                "subclass_name": "Arcane Trickster",
                "level": 3,
                "systems_ref": dict(profile["class_ref"]),
                "subclass_ref": dict(profile["subclass_ref"]),
            }
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://native-arcane-trickster",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-09T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "Rogue",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 13,
            "spell_attack_bonus": 5,
            "slot_progression": [
                {"level": 1, "max_slots": 2},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Rogue",
                    "spell_list_class_name": "Wizard",
                    "class_ref": dict(profile["class_ref"]),
                    "level": 3,
                    "caster_progression": "1/3",
                    "spell_mode": "known",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 13,
                    "spell_attack_bonus": 5,
                }
            ],
            "spells": [
                {
                    **_spell_payload(spell_entries["phb-spell-mage-hand"], source="Rogue", mark="Cantrip"),
                    "class_row_id": "class-row-1",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=spell&q=detect&target_class_row_id=class-row-1"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-detect-magic"]


def test_spellcasting_subpage_shows_and_updates_separate_slot_pools_for_wizard_warlock_multiclass(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-hex", "title": "Hex", "level": 1, "class_lists": {"PHB": ["Warlock"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 3 / Warlock 2"
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Wizard",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "title": "Wizard",
                    "slug": "phb-class-wizard",
                    "source_id": "PHB",
                },
            },
            {
                "row_id": "class-row-2",
                "class_name": "Warlock",
                "level": 2,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-warlock",
                    "entry_type": "class",
                    "title": "Warlock",
                    "slug": "phb-class-warlock",
                    "source_id": "PHB",
                },
            },
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://native-multiclass",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-09T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "slot_lanes": [
                {
                    "id": "class-row-1-slots",
                    "title": "Wizard spell slots",
                    "shared": False,
                    "row_ids": ["class-row-1"],
                    "slot_progression": [
                        {"level": 1, "max_slots": 4},
                        {"level": 2, "max_slots": 2},
                    ],
                },
                {
                    "id": "class-row-2-slots",
                    "title": "Warlock Pact Magic slots",
                    "shared": False,
                    "row_ids": ["class-row-2"],
                    "slot_progression": [
                        {"level": 1, "max_slots": 2},
                    ],
                },
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Wizard",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                        "entry_type": "class",
                        "title": "Wizard",
                        "slug": "phb-class-wizard",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "wizard",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                    "slot_lane_id": "class-row-1-slots",
                },
                {
                    "class_row_id": "class-row-2",
                    "class_name": "Warlock",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-warlock",
                        "entry_type": "class",
                        "title": "Warlock",
                        "slug": "phb-class-warlock",
                        "source_id": "PHB",
                    },
                    "level": 2,
                    "caster_progression": "pact",
                    "spell_mode": "known",
                    "spellcasting_ability": "Charisma",
                    "spell_save_dc": 13,
                    "spell_attack_bonus": 5,
                    "slot_lane_id": "class-row-2-slots",
                },
            ],
            "spells": [
                {
                    **_spell_payload(spell_entries["phb-spell-detect-magic"], source="Wizard", mark="O"),
                    "class_row_id": "class-row-1",
                },
                {
                    **_spell_payload(spell_entries["phb-spell-hex"], source="Warlock", mark="Known"),
                    "class_row_id": "class-row-2",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Spell slot pools are shown below" in page_html
    assert "Wizard spell slots" in page_html
    assert "Warlock Pact Magic slots" in page_html

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/1",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "session",
            "page": "spellcasting",
            "slot_lane_id": "class-row-2-slots",
            "used": "1",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "arden-march")
        assert record is not None
        wizard_slot = next(
            slot
            for slot in list(record.state_record.state.get("spell_slots") or [])
            if str(slot.get("slot_lane_id") or "") == "class-row-1-slots"
            and int(slot.get("level") or 0) == 1
        )
        warlock_slot = next(
            slot
            for slot in list(record.state_record.state.get("spell_slots") or [])
            if str(slot.get("slot_lane_id") or "") == "class-row-2-slots"
            and int(slot.get("level") or 0) == 1
        )
        assert wizard_slot["used"] == 0
        assert warlock_slot["used"] == 1
