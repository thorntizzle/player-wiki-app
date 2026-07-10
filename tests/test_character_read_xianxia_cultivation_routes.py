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

def test_xianxia_cultivation_route_is_separate_from_dnd_level_up(
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
        data=_valid_xianxia_create_data("Cultivation Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/cultivation-crane"
    )

    sheet_response = client.get("/campaigns/linden-pass/characters/cultivation-crane")
    assert sheet_response.status_code == 200
    sheet_html = sheet_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/cultivation-crane/cultivation" in sheet_html
    assert "/campaigns/linden-pass/characters/cultivation-crane/level-up" not in sheet_html
    assert "Level up" not in sheet_html
    assert "Cultivation" in sheet_html

    cultivation_response = client.get(
        "/campaigns/linden-pass/characters/cultivation-crane/cultivation"
    )
    assert cultivation_response.status_code == 200
    cultivation_html = cultivation_response.get_data(as_text=True)
    assert "Character cultivation" in cultivation_html
    assert "Insight-based advancement for this Xianxia character." in cultivation_html
    assert "Available" in cultivation_html
    assert "Spent" in cultivation_html
    assert "Demon&#39;s Fist" in cultivation_html
    assert "Heavenly Palm" in cultivation_html
    assert "No advancement history is recorded on this sheet yet." in cultivation_html
    assert "DND-5E native sheet model" not in cultivation_html
    assert "/campaigns/linden-pass/characters/cultivation-crane/level-up" not in cultivation_html


def test_xianxia_cultivation_route_records_realm_ascension_review_subflow(
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
        data=_valid_xianxia_create_data("Realm Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_response = client.get(
        "/campaigns/linden-pass/characters/realm-crane/cultivation"
    )
    assert cultivation_response.status_code == 200
    cultivation_html = cultivation_response.get_data(as_text=True)
    assert "Realm Ascension" in cultivation_html
    assert 'name="cultivation_action" value="start_realm_ascension_review"' in cultivation_html
    assert 'name="target_realm" value="Immortal"' in cultivation_html
    assert "Current Realm" in cultivation_html
    assert "Mortal" in cultivation_html
    assert "Target Realm" in cultivation_html
    assert "Immortal" in cultivation_html
    assert "1 year" in cultivation_html
    assert "15 points" in cultivation_html
    assert "Max 6 per Stat" in cultivation_html
    assert "Stat prerequisite" in cultivation_html
    assert "Not met" in cultivation_html
    assert "Need one Stat at 10" in cultivation_html
    assert "Current highest Stat is Strength at 3." in cultivation_html
    assert "Start Realm Review" in cultivation_html

    starting_revision = _character_state_revision(app, "realm-crane")
    unmet_response = client.post(
        "/campaigns/linden-pass/characters/realm-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": (
                "GM approved the review, but the stat threshold is still missing."
            ),
        },
        follow_redirects=True,
    )
    assert unmet_response.status_code == 200
    assert (
        "Realm ascension prerequisite not met: raise at least one Attribute or "
        "Effort to 10 before ascending from Mortal to Immortal."
        in unmet_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "realm-crane") == starting_revision
    assert _read_character_definition(app, "realm-crane")["xianxia"]["advancement_history"] == []

    _write_character_definition(
        app,
        "realm-crane",
        lambda payload: payload["xianxia"]["attributes"].__setitem__("str", 10),
    )

    ready_html = client.get(
        "/campaigns/linden-pass/characters/realm-crane/cultivation"
    ).get_data(as_text=True)
    ready_text = " ".join(ready_html.split())
    assert "Met" in ready_html
    assert "Need one Stat at 10" in ready_html
    assert "highest Strength 10" in ready_text

    invalid_response = client.post(
        "/campaigns/linden-pass/characters/realm-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": " ",
        },
        follow_redirects=True,
    )
    assert invalid_response.status_code == 200
    assert (
        "Record a GM review note before starting Realm ascension review."
        in invalid_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "realm-crane") == starting_revision

    review_note = "GM approved the review after the Immortal threshold scene."
    review_response = client.post(
        "/campaigns/linden-pass/characters/realm-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": review_note,
            "realm_ascension_seclusion_notes": "One year in a sealed cave.",
            "realm_ascension_hp_stance_trade_notes": "No trade chosen yet.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302
    assert review_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/realm-crane/cultivation#xianxia-cultivation-realm-ascension"
    )

    definition_payload = _read_character_definition(app, "realm-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["realm"] == "Mortal"
    assert xianxia["actions_per_turn"] == 2
    assert xianxia["attributes"] == {
        "str": 10,
        "dex": 0,
        "con": 3,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 3,
        "weapon": 1,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 0,
    }
    assert len(xianxia["martial_arts"]) == 3
    assert xianxia["generic_techniques"] == []
    assert xianxia["advancement_history"] == [
        {
            "action": "realm_ascension_review_started",
            "target": "Immortal",
            "current_realm": "Mortal",
            "target_realm": "Immortal",
            "status": "pending_gm_review",
            "seclusion_time": "1 year",
            "rebuild_budget": 15,
            "stat_cap": 6,
            "actions_per_turn": 3,
            "stat_max_prerequisite": {
                "required_score": 10,
                "met": True,
                "stat_kind": "Attribute",
                "stat_key": "str",
                "stat_label": "Strength",
                "stat_score": 10,
            },
            "gm_review_note": review_note,
            "seclusion_notes": "One year in a sealed cave.",
            "hp_stance_trade_notes": "No trade chosen yet.",
        }
    ]
    assert _character_state_revision(app, "realm-crane") == starting_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/realm-crane/cultivation"
    ).get_data(as_text=True)
    assert "Latest Realm Review" in updated_html
    assert "Realm Ascension Review Started" in updated_html
    assert "Stat prerequisite:" in updated_html
    assert "Strength" in updated_html
    assert "met required" in updated_html
    assert "GM review note:" in updated_html
    assert review_note in updated_html
    assert "Seclusion notes:" in updated_html
    assert "One year in a sealed cave." in updated_html
    assert "HP/Stance trade notes:" in updated_html
    assert "No trade chosen yet." in updated_html


def test_xianxia_cultivation_route_resets_only_realm_ascension_stats(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["attributes"] = {
            "str": 10,
            "dex": 2,
            "con": 4,
            "int": 1,
            "wis": 3,
            "cha": 2,
        }
        xianxia["efforts"] = {
            "basic": 4,
            "weapon": 3,
            "guns_explosive": 2,
            "magic": 5,
            "ultimate": 1,
        }
        xianxia["energies"] = {
            "jing": {"max": 4},
            "qi": {"max": 5},
            "shen": {"max": 6},
        }
        xianxia["yin_yang"] = {"yin_max": 3, "yang_max": 4}
        xianxia["dao"] = {"max": 3}
        xianxia["insight"] = {"available": 7, "spent": 2}
        xianxia["durability"] = {
            "hp_max": 28,
            "stance_max": 26,
            "manual_armor_bonus": 2,
            "defense": 16,
        }
        xianxia["generic_techniques"] = [
            {
                "name": "Cloud Step",
                "generic_technique_key": "cloud_step",
                "systems_ref": {"slug": "cloud-step"},
            }
        ]
        xianxia["variants"] = [{"name": "Approved variant", "status": "approved"}]
        xianxia["dao_immolating_techniques"] = {
            "prepared": [{"name": "Last Dawn"}],
            "use_history": [
                {
                    "name": "Old Flame",
                    "approval_required": True,
                    "approval_status": "pending",
                    "insight_cost": 10,
                    "one_use": True,
                }
            ],
        }
        xianxia["approval_requests"] = [{"name": "Constraint", "status": "pending"}]
        xianxia["companions"] = [{"name": "Paper Crane"}]

    def _prepare_state(payload: dict) -> None:
        payload["vitals"]["current_hp"] = 17
        payload["vitals"]["temp_hp"] = 3
        payload["notes"]["player_notes_markdown"] = "Keep this player note."
        xianxia_state = payload["xianxia"]
        xianxia_state["vitals"] = {
            "current_hp": 17,
            "temp_hp": 3,
            "current_stance": 14,
            "temp_stance": 2,
        }
        xianxia_state["energies"] = {
            "jing": {"current": 2},
            "qi": {"current": 3},
            "shen": {"current": 4},
        }
        xianxia_state["yin_yang"] = {"yin_current": 2, "yang_current": 3}
        xianxia_state["dao"] = {"current": 2}
        xianxia_state["active_stance"] = {"name": "Mountain Root"}
        xianxia_state["active_aura"] = {"name": "Quiet Moon"}
        xianxia_state["notes"] = {"player_notes_markdown": "Keep this player note."}

    _write_campaign_config(app, _mutate_campaign)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Reset Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "reset-crane", _prepare_definition)
    _write_character_state(app, "reset-crane", _prepare_state)

    review_revision = _character_state_revision(app, "reset-crane")
    review_response = client.post(
        "/campaigns/linden-pass/characters/reset-crane/cultivation",
        data={
            "expected_revision": str(review_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "GM review is approved for the reset step.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302

    review_html = client.get(
        "/campaigns/linden-pass/characters/reset-crane/cultivation"
    ).get_data(as_text=True)
    assert "Reset Rebuild Stats" in review_html
    assert 'name="cultivation_action" value="reset_realm_ascension_stats"' in review_html

    reset_revision = _character_state_revision(app, "reset-crane")
    reset_response = client.post(
        "/campaigns/linden-pass/characters/reset-crane/cultivation",
        data={
            "expected_revision": str(reset_revision),
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
            "realm_ascension_reset_notes": "Ready for the Immortal rebuild budget.",
        },
        follow_redirects=False,
    )
    assert reset_response.status_code == 302
    assert reset_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/reset-crane/cultivation#xianxia-cultivation-realm-ascension"
    )

    definition_payload = _read_character_definition(app, "reset-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["attributes"] == {
        "str": 0,
        "dex": 0,
        "con": 0,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 0,
        "weapon": 0,
        "guns_explosive": 0,
        "magic": 0,
        "ultimate": 0,
    }
    assert xianxia["realm"] == "Mortal"
    assert xianxia["actions_per_turn"] == 2
    assert xianxia["energies"] == {
        "jing": {"max": 4},
        "qi": {"max": 5},
        "shen": {"max": 6},
    }
    assert xianxia["yin_yang"] == {"yin_max": 3, "yang_max": 4}
    assert xianxia["dao"] == {"max": 3}
    assert xianxia["insight"] == {"available": 7, "spent": 2}
    assert xianxia["durability"]["hp_max"] == 28
    assert xianxia["durability"]["stance_max"] == 26
    assert xianxia["durability"]["manual_armor_bonus"] == 2
    assert xianxia["durability"]["defense"] == 12
    assert len(xianxia["martial_arts"]) == 3
    assert xianxia["generic_techniques"] == [
        {
            "name": "Cloud Step",
            "systems_ref": {"slug": "cloud-step"},
            "generic_technique_key": "cloud_step",
        }
    ]
    assert xianxia["variants"] == [{"name": "Approved variant", "status": "approved"}]
    assert xianxia["dao_immolating_techniques"] == {
        "prepared": [{"name": "Last Dawn"}],
        "use_history": [
            {
                "name": "Old Flame",
                "approval_required": True,
                "approval_status": "pending",
                "insight_cost": 10,
                "one_use": True,
            }
        ],
    }
    assert xianxia["approval_requests"] == [{"name": "Constraint", "status": "pending"}]
    assert xianxia["companions"] == [{"name": "Paper Crane"}]
    reset_event = xianxia["advancement_history"][-1]
    _assert_event_contains(
        reset_event,
        {
            "action": "realm_ascension_attributes_efforts_reset",
            "target": "Immortal",
            "current_realm": "Mortal",
            "target_realm": "Immortal",
            "status": "pending_rebuild",
            "attributes_before_total": 22,
            "attributes_after_total": 0,
            "efforts_before_total": 15,
            "efforts_after_total": 0,
            "reset_scope": "Attributes and Efforts",
            "preserved_scope": (
                "Energies, Yin/Yang, HP, Stance, Insight, Martial Arts, "
                "Generic Techniques, variants, approval records, and notes"
            ),
            "notes": "Ready for the Immortal rebuild budget.",
        },
    )
    assert reset_event["pre_ascension_state"]["realm"] == "Mortal"
    assert reset_event["pre_ascension_state"]["actions_per_turn"] == 2
    assert reset_event["pre_ascension_state"]["attributes"] == {
        "str": 10,
        "dex": 2,
        "con": 4,
        "int": 1,
        "wis": 3,
        "cha": 2,
    }
    assert reset_event["pre_ascension_state"]["efforts"] == {
        "basic": 4,
        "weapon": 3,
        "guns_explosive": 2,
        "magic": 5,
        "ultimate": 1,
    }
    assert reset_event["pre_ascension_state"]["durability"]["hp_max"] == 28
    assert reset_event["pre_ascension_state"]["durability"]["stance_max"] == 26
    assert reset_event["pre_ascension_state"]["insight"] == {
        "available": 7,
        "spent": 2,
    }
    assert len(reset_event["pre_ascension_state"]["martial_arts"]) == 3
    assert reset_event["pre_ascension_state"]["generic_techniques"] == [
        {
            "name": "Cloud Step",
            "systems_ref": {"slug": "cloud-step"},
            "generic_technique_key": "cloud_step",
        }
    ]
    assert (
        reset_event["pre_ascension_summary"]
        == "Mortal Realm, 2 actions; Attributes 22, Efforts 15; HP max 28, "
        "Stance max 26; Insight 7 available/2 spent; Martial Arts 3; "
        "Generic Techniques 1"
    )

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "reset-crane")
        assert record is not None
        state = record.state_record.state
    assert state["vitals"] == {"current_hp": 17, "temp_hp": 3}
    assert state["notes"]["player_notes_markdown"] == "Keep this player note."
    assert state["xianxia"] == {
        "schema_version": 1,
        "vitals": {
            "current_hp": 17,
            "temp_hp": 3,
            "current_stance": 14,
            "temp_stance": 2,
        },
        "energies": {
            "jing": {"current": 2},
            "qi": {"current": 3},
            "shen": {"current": 4},
        },
        "yin_yang": {"yin_current": 2, "yang_current": 3},
        "dao": {"current": 2},
        "active_stance": {"name": "Mountain Root"},
        "active_aura": {"name": "Quiet Moon"},
        "currency": {"coin": 0, "supply": 0, "spirit_stones": 0},
        "inventory": {"enabled": False, "quantities": []},
        "notes": {"player_notes_markdown": "Keep this player note."},
    }
    assert _character_state_revision(app, "reset-crane") == reset_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/reset-crane/cultivation"
    ).get_data(as_text=True)
    assert "Latest Attribute/Effort Reset" in updated_html
    assert 'name="cultivation_action" value="reset_realm_ascension_stats"' not in updated_html
    assert "22 to 0" in updated_html
    assert "15 to 0" in updated_html
    assert "Pre-ascension state:" in updated_html
    assert "Mortal Realm, 2 actions; Attributes 22, Efforts 15" in updated_html


def test_xianxia_cultivation_route_applies_immortal_rebuild_budget(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["attributes"]["str"] = 10
        xianxia["energies"] = {
            "jing": {"max": 4},
            "qi": {"max": 5},
            "shen": {"max": 6},
        }
        xianxia["yin_yang"] = {"yin_max": 3, "yang_max": 4}
        xianxia["insight"] = {"available": 7, "spent": 2}
        xianxia["durability"] = {
            "hp_max": 28,
            "stance_max": 26,
            "manual_armor_bonus": 2,
            "defense": 16,
        }
        xianxia["generic_techniques"] = [
            {
                "name": "Cloud Step",
                "generic_technique_key": "cloud_step",
                "systems_ref": {"slug": "cloud-step"},
            }
        ]
        xianxia["variants"] = [{"name": "Approved variant", "status": "approved"}]
        xianxia["approval_requests"] = [{"name": "Constraint", "status": "pending"}]

    def _prepare_state(payload: dict) -> None:
        payload["vitals"]["current_hp"] = 17
        payload["vitals"]["temp_hp"] = 3
        xianxia_state = payload["xianxia"]
        xianxia_state["vitals"] = {
            "current_hp": 17,
            "temp_hp": 3,
            "current_stance": 14,
            "temp_stance": 2,
        }
        xianxia_state["energies"] = {
            "jing": {"current": 2},
            "qi": {"current": 3},
            "shen": {"current": 4},
        }
        xianxia_state["yin_yang"] = {"yin_current": 2, "yang_current": 3}
        xianxia_state["dao"] = {"current": 2}

    _write_campaign_config(app, _mutate_campaign)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Immortal Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "immortal-crane", _prepare_definition)
    _write_character_state(app, "immortal-crane", _prepare_state)

    review_revision = _character_state_revision(app, "immortal-crane")
    review_response = client.post(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation",
        data={
            "expected_revision": str(review_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "GM review approved for rebuild math.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302

    reset_revision = _character_state_revision(app, "immortal-crane")
    reset_response = client.post(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation",
        data={
            "expected_revision": str(reset_revision),
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
            "realm_ascension_reset_notes": "Ready for point assignment.",
        },
        follow_redirects=False,
    )
    assert reset_response.status_code == 302

    rebuild_html = client.get(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation"
    ).get_data(as_text=True)
    assert "Apply Immortal Rebuild" in rebuild_html
    assert 'name="cultivation_action" value="apply_immortal_realm_rebuild"' in rebuild_html
    assert "Spend exactly 15 total Attribute/Effort points" in rebuild_html

    rebuild_revision = _character_state_revision(app, "immortal-crane")
    invalid_total_response = client.post(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "3",
            "realm_rebuild_attribute_con": "0",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "2",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "0",
            "realm_rebuild_effort_ultimate": "0",
        },
        follow_redirects=True,
    )
    assert invalid_total_response.status_code == 200
    assert (
        "Immortal rebuild must spend exactly 15 Attribute/Effort points; submitted 14."
        in invalid_total_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "immortal-crane") == rebuild_revision

    invalid_cap_response = client.post(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "7",
            "realm_rebuild_attribute_dex": "0",
            "realm_rebuild_attribute_con": "0",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "3",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "2",
            "realm_rebuild_effort_ultimate": "0",
        },
        follow_redirects=True,
    )
    assert invalid_cap_response.status_code == 200
    assert (
        "Strength cannot exceed 6 for the Immortal rebuild."
        in invalid_cap_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "immortal-crane") == rebuild_revision

    valid_response = client.post(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "2",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_rebuild_notes": "GM approved the Immortal rebuild math.",
        },
        follow_redirects=False,
    )
    assert valid_response.status_code == 302
    assert valid_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation#xianxia-cultivation-realm-ascension"
    )

    definition_payload = _read_character_definition(app, "immortal-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["realm"] == "Immortal"
    assert xianxia["actions_per_turn"] == 3
    assert xianxia["attributes"] == {
        "str": 6,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 3,
        "weapon": 2,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 0,
    }
    assert xianxia["energies"] == {
        "jing": {"max": 4},
        "qi": {"max": 5},
        "shen": {"max": 6},
    }
    assert xianxia["yin_yang"] == {"yin_max": 3, "yang_max": 4}
    assert xianxia["insight"] == {"available": 7, "spent": 2}
    assert xianxia["durability"]["hp_max"] == 28
    assert xianxia["durability"]["stance_max"] == 26
    assert xianxia["durability"]["manual_armor_bonus"] == 2
    assert xianxia["durability"]["defense"] == 13
    assert xianxia["generic_techniques"] == [
        {
            "name": "Cloud Step",
            "systems_ref": {"slug": "cloud-step"},
            "generic_technique_key": "cloud_step",
        }
    ]
    assert xianxia["variants"] == [{"name": "Approved variant", "status": "approved"}]
    assert xianxia["approval_requests"] == [{"name": "Constraint", "status": "pending"}]
    rebuild_event = xianxia["advancement_history"][-1]
    _assert_event_contains(
        rebuild_event,
        {
            "action": "realm_ascension_immortal_rebuild_applied",
            "target": "Immortal",
            "current_realm": "Mortal",
            "target_realm": "Immortal",
            "status": "applied_pending_final_confirmation",
            "rebuild_budget": 15,
            "stat_cap": 6,
            "actions_per_turn": 3,
            "attributes_after_total": 9,
            "efforts_after_total": 6,
            "total_rebuild_points": 15,
            "notes": "GM approved the Immortal rebuild math.",
        },
    )
    assert rebuild_event["pre_ascension_state"]["realm"] == "Mortal"
    assert rebuild_event["pre_ascension_state"]["attributes"]["str"] == 10
    assert rebuild_event["pre_ascension_state"]["attributes_total"] == 13
    assert rebuild_event["pre_ascension_state"]["efforts_total"] == 5
    assert rebuild_event["post_ascension_state"]["realm"] == "Immortal"
    assert rebuild_event["post_ascension_state"]["actions_per_turn"] == 3
    assert rebuild_event["post_ascension_state"]["attributes"] == {
        "str": 6,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert rebuild_event["post_ascension_state"]["efforts"] == {
        "basic": 3,
        "weapon": 2,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 0,
    }
    assert rebuild_event["post_ascension_state"]["energies"] == {
        "jing": {"max": 4},
        "qi": {"max": 5},
        "shen": {"max": 6},
    }
    assert rebuild_event["post_ascension_state"]["yin_yang"] == {
        "yin_max": 3,
        "yang_max": 4,
    }
    assert rebuild_event["post_ascension_state"]["durability"]["hp_max"] == 28
    assert rebuild_event["post_ascension_state"]["durability"]["stance_max"] == 26
    assert (
        rebuild_event["pre_ascension_summary"]
        == "Mortal Realm, 2 actions; Attributes 13, Efforts 5; HP max 28, "
        "Stance max 26; Insight 7 available/2 spent; Martial Arts 3; "
        "Generic Techniques 1"
    )
    assert (
        rebuild_event["post_ascension_summary"]
        == "Immortal Realm, 3 actions; Attributes 9, Efforts 6; HP max 28, "
        "Stance max 26; Insight 7 available/2 spent; Martial Arts 3; "
        "Generic Techniques 1"
    )

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "immortal-crane")
        assert record is not None
        state = record.state_record.state
    assert state["vitals"] == {"current_hp": 17, "temp_hp": 3}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 17,
        "temp_hp": 3,
        "current_stance": 14,
        "temp_stance": 2,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 3},
        "shen": {"current": 4},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 2, "yang_current": 3}
    assert state["xianxia"]["dao"] == {"current": 2}
    assert _character_state_revision(app, "immortal-crane") == rebuild_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/immortal-crane/cultivation"
    ).get_data(as_text=True)
    assert "Latest Immortal Rebuild" in updated_html
    assert "Realm Ascension Immortal Rebuild Applied" in updated_html
    assert "15 of 15" in updated_html
    assert "Pre-ascension state:" in updated_html
    assert "Post-ascension state:" in updated_html
    assert "Immortal Realm, 3 actions; Attributes 9, Efforts 6" in updated_html
    assert 'name="cultivation_action" value="apply_immortal_realm_rebuild"' not in updated_html


def test_xianxia_cultivation_route_records_realm_ascension_gm_confirmation(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["attributes"]["str"] = 10
        xianxia["durability"] = {
            "hp_max": 28,
            "stance_max": 26,
            "manual_armor_bonus": 2,
            "defense": 16,
        }

    _write_campaign_config(app, _mutate_campaign)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Confirm Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "confirm-crane", _prepare_definition)

    review_revision = _character_state_revision(app, "confirm-crane")
    review_response = client.post(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation",
        data={
            "expected_revision": str(review_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "GM approves the ascension review.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302

    reset_revision = _character_state_revision(app, "confirm-crane")
    reset_response = client.post(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation",
        data={
            "expected_revision": str(reset_revision),
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
        },
        follow_redirects=False,
    )
    assert reset_response.status_code == 302

    rebuild_revision = _character_state_revision(app, "confirm-crane")
    rebuild_response = client.post(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "2",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_rebuild_notes": "Rebuild math is ready for final review.",
        },
        follow_redirects=False,
    )
    assert rebuild_response.status_code == 302

    confirm_html = client.get(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation"
    ).get_data(as_text=True)
    assert "Confirm Immortal Ascension" in confirm_html
    assert 'name="cultivation_action" value="confirm_realm_ascension"' in confirm_html
    assert 'name="realm_ascension_gm_confirmation_note"' in confirm_html

    confirmation_revision = _character_state_revision(app, "confirm-crane")
    invalid_response = client.post(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation",
        data={
            "expected_revision": str(confirmation_revision),
            "cultivation_action": "confirm_realm_ascension",
            "target_realm": "Immortal",
            "realm_ascension_gm_confirmation_note": " ",
        },
        follow_redirects=True,
    )
    assert invalid_response.status_code == 200
    assert (
        "Record a GM confirmation note before confirming Realm ascension."
        in invalid_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "confirm-crane") == confirmation_revision

    confirmation_note = "GM confirms the final Immortal ascension scene."
    valid_response = client.post(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation",
        data={
            "expected_revision": str(confirmation_revision),
            "cultivation_action": "confirm_realm_ascension",
            "target_realm": "Immortal",
            "realm_ascension_gm_confirmation_note": confirmation_note,
        },
        follow_redirects=False,
    )
    assert valid_response.status_code == 302
    assert valid_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation#xianxia-cultivation-realm-ascension"
    )

    definition_payload = _read_character_definition(app, "confirm-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["realm"] == "Immortal"
    assert xianxia["actions_per_turn"] == 3
    assert xianxia["attributes"] == {
        "str": 6,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 3,
        "weapon": 2,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 0,
    }
    rebuild_event = xianxia["advancement_history"][-2]
    confirmation_event = xianxia["advancement_history"][-1]
    assert rebuild_event["action"] == "realm_ascension_immortal_rebuild_applied"
    assert rebuild_event["status"] == "confirmed"
    _assert_event_contains(
        confirmation_event,
        {
            "action": "realm_ascension_gm_confirmation_recorded",
            "target": "Immortal",
            "current_realm": "Mortal",
            "target_realm": "Immortal",
            "confirmed_realm": "Immortal",
            "status": "confirmed",
            "confirmed_rebuild_action": "realm_ascension_immortal_rebuild_applied",
            "confirmed_rebuild_index": 2,
            "actions_per_turn": 3,
            "attributes_after_total": 9,
            "efforts_after_total": 6,
            "gm_confirmation_note": confirmation_note,
        },
    )
    assert (
        confirmation_event["post_ascension_summary"]
        == "Immortal Realm, 3 actions; Attributes 9, Efforts 6; HP max 28, "
        "Stance max 26; Insight 0 available/0 spent; Martial Arts 3; "
        "Generic Techniques 0"
    )
    assert _character_state_revision(app, "confirm-crane") == confirmation_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/confirm-crane/cultivation"
    ).get_data(as_text=True)
    assert "Latest GM Confirmation" in updated_html
    assert "GM confirmation note:" in updated_html
    assert confirmation_note in updated_html
    assert "Confirmed state:" in updated_html
    assert 'name="cultivation_action" value="confirm_realm_ascension"' not in updated_html


def test_xianxia_cultivation_route_supports_legal_realm_hp_stance_trade(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["attributes"]["str"] = 10
        xianxia["durability"] = {
            "hp_max": 28,
            "stance_max": 26,
            "manual_armor_bonus": 2,
            "defense": 16,
        }

    def _prepare_state(payload: dict) -> None:
        payload["vitals"]["current_hp"] = 17
        payload["vitals"]["temp_hp"] = 3
        payload["xianxia"]["vitals"] = {
            "current_hp": 17,
            "temp_hp": 3,
            "current_stance": 14,
            "temp_stance": 2,
        }

    _write_campaign_config(app, _mutate_campaign)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Trade Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "trade-crane", _prepare_definition)
    _write_character_state(app, "trade-crane", _prepare_state)

    review_revision = _character_state_revision(app, "trade-crane")
    review_response = client.post(
        "/campaigns/linden-pass/characters/trade-crane/cultivation",
        data={
            "expected_revision": str(review_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "GM review approved the trade option.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302

    reset_revision = _character_state_revision(app, "trade-crane")
    reset_response = client.post(
        "/campaigns/linden-pass/characters/trade-crane/cultivation",
        data={
            "expected_revision": str(reset_revision),
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
        },
        follow_redirects=False,
    )
    assert reset_response.status_code == 302

    rebuild_html = client.get(
        "/campaigns/linden-pass/characters/trade-crane/cultivation"
    ).get_data(as_text=True)
    assert "Optional HP/Stance trade" in rebuild_html
    assert 'name="realm_ascension_trade_hp"' in rebuild_html
    assert 'name="realm_ascension_trade_stance"' in rebuild_html
    assert "Current max 28" in rebuild_html
    assert "Current max 26" in rebuild_html

    rebuild_revision = _character_state_revision(app, "trade-crane")
    invalid_trade_response = client.post(
        "/campaigns/linden-pass/characters/trade-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "2",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_trade_hp": "5",
            "realm_ascension_trade_stance": "0",
        },
        follow_redirects=True,
    )
    assert invalid_trade_response.status_code == 200
    assert (
        "HP maximum trade must be 0 or a multiple of 10."
        in invalid_trade_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "trade-crane") == rebuild_revision

    valid_trade_response = client.post(
        "/campaigns/linden-pass/characters/trade-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "2",
            "realm_rebuild_effort_guns_explosive": "1",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "1",
            "realm_ascension_trade_hp": "10",
            "realm_ascension_trade_stance": "10",
            "realm_ascension_rebuild_notes": "Traded durability for a wider rebuild.",
        },
        follow_redirects=False,
    )
    assert valid_trade_response.status_code == 302
    assert valid_trade_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/trade-crane/cultivation#xianxia-cultivation-realm-ascension"
    )

    definition_payload = _read_character_definition(app, "trade-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["realm"] == "Immortal"
    assert xianxia["durability"]["hp_max"] == 18
    assert xianxia["durability"]["stance_max"] == 16
    assert xianxia["durability"]["defense"] == 13
    rebuild_event = xianxia["advancement_history"][-1]
    _assert_event_contains(
        rebuild_event,
        {
            "action": "realm_ascension_immortal_rebuild_applied",
            "target": "Immortal",
            "current_realm": "Mortal",
            "target_realm": "Immortal",
            "status": "applied_pending_final_confirmation",
            "rebuild_budget": 17,
            "stat_cap": 6,
            "actions_per_turn": 3,
            "attributes_after_total": 9,
            "efforts_after_total": 8,
            "total_rebuild_points": 17,
            "hp_stance_trade_points": 2,
            "base_rebuild_budget": 15,
            "hp_maximum_trade": 10,
            "stance_maximum_trade": 10,
            "hp_maximum_before": 28,
            "hp_maximum_after": 18,
            "stance_maximum_before": 26,
            "stance_maximum_after": 16,
            "notes": "Traded durability for a wider rebuild.",
        },
    )
    assert rebuild_event["pre_ascension_state"]["realm"] == "Mortal"
    assert rebuild_event["pre_ascension_state"]["attributes_total"] == 13
    assert rebuild_event["pre_ascension_state"]["efforts_total"] == 5
    assert rebuild_event["pre_ascension_state"]["durability"]["hp_max"] == 28
    assert rebuild_event["pre_ascension_state"]["durability"]["stance_max"] == 26
    assert rebuild_event["post_ascension_state"]["realm"] == "Immortal"
    assert rebuild_event["post_ascension_state"]["attributes_total"] == 9
    assert rebuild_event["post_ascension_state"]["efforts_total"] == 8
    assert rebuild_event["post_ascension_state"]["durability"]["hp_max"] == 18
    assert rebuild_event["post_ascension_state"]["durability"]["stance_max"] == 16
    assert (
        rebuild_event["pre_ascension_summary"]
        == "Mortal Realm, 2 actions; Attributes 13, Efforts 5; HP max 28, "
        "Stance max 26; Insight 0 available/0 spent; Martial Arts 3; "
        "Generic Techniques 0"
    )
    assert (
        rebuild_event["post_ascension_summary"]
        == "Immortal Realm, 3 actions; Attributes 9, Efforts 8; HP max 18, "
        "Stance max 16; Insight 0 available/0 spent; Martial Arts 3; "
        "Generic Techniques 0"
    )

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "trade-crane")
        assert record is not None
        state = record.state_record.state
    assert state["vitals"] == {"current_hp": 17, "temp_hp": 3}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 17,
        "temp_hp": 3,
        "current_stance": 14,
        "temp_stance": 2,
    }
    assert _character_state_revision(app, "trade-crane") == rebuild_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/trade-crane/cultivation"
    ).get_data(as_text=True)
    assert "17 of 17" in updated_html
    assert "Base budget:" in updated_html
    assert "HP/Stance trade points:" in updated_html
    assert "HP maximum:" in updated_html
    assert "28 to 18" in updated_html
    assert "Stance maximum:" in updated_html
    assert "26 to 16" in updated_html
    assert "Post-ascension state:" in updated_html
    assert "Immortal Realm, 3 actions; Attributes 9, Efforts 8" in updated_html


def test_xianxia_cultivation_route_records_divine_ascension_seclusion_time(
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

    def _make_immortal(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["realm"] = "Immortal"
        xianxia["actions_per_turn"] = 3
        xianxia["attributes"]["str"] = 15

    _write_campaign_config(app, _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Divine Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "divine-crane", _make_immortal)

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/divine-crane/cultivation"
    ).get_data(as_text=True)
    assert 'name="target_realm" value="Divine"' in cultivation_html
    assert "Immortal" in cultivation_html
    assert "Divine" in cultivation_html
    assert "100 years" in cultivation_html
    assert "25 points" in cultivation_html
    assert "Max 12 per Stat" in cultivation_html
    assert "Need one Stat at 15" in cultivation_html

    starting_revision = _character_state_revision(app, "divine-crane")
    review_note = "GM approved the review after the Divine threshold scene."
    review_response = client.post(
        "/campaigns/linden-pass/characters/divine-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Divine",
            "realm_ascension_gm_review_note": review_note,
            "realm_ascension_seclusion_notes": "One hundred years beyond the gate.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302

    xianxia = _read_character_definition(app, "divine-crane")["xianxia"]
    assert xianxia["realm"] == "Immortal"
    assert xianxia["actions_per_turn"] == 3
    assert xianxia["advancement_history"] == [
        {
            "action": "realm_ascension_review_started",
            "target": "Divine",
            "current_realm": "Immortal",
            "target_realm": "Divine",
            "status": "pending_gm_review",
            "seclusion_time": "100 years",
            "rebuild_budget": 25,
            "stat_cap": 12,
            "actions_per_turn": 4,
            "stat_max_prerequisite": {
                "required_score": 15,
                "met": True,
                "stat_kind": "Attribute",
                "stat_key": "str",
                "stat_label": "Strength",
                "stat_score": 15,
            },
            "gm_review_note": review_note,
            "seclusion_notes": "One hundred years beyond the gate.",
        }
    ]
    assert _character_state_revision(app, "divine-crane") == starting_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/divine-crane/cultivation"
    ).get_data(as_text=True)
    assert "Latest Realm Review" in updated_html
    assert "Seclusion:" in updated_html
    assert "100 years" in updated_html


def test_xianxia_cultivation_route_applies_divine_rebuild_budget(
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

    def _make_immortal(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["realm"] = "Immortal"
        xianxia["actions_per_turn"] = 3
        xianxia["attributes"]["str"] = 15
        xianxia["energies"] = {
            "jing": {"max": 4},
            "qi": {"max": 5},
            "shen": {"max": 6},
        }
        xianxia["yin_yang"] = {"yin_max": 3, "yang_max": 4}
        xianxia["insight"] = {"available": 9, "spent": 6}
        xianxia["durability"] = {
            "hp_max": 31,
            "stance_max": 29,
            "manual_armor_bonus": 2,
            "defense": 27,
        }
        xianxia["generic_techniques"] = [
            {
                "name": "Cloud Step",
                "generic_technique_key": "cloud_step",
                "systems_ref": {"slug": "cloud-step"},
            }
        ]
        xianxia["variants"] = [{"name": "Approved variant", "status": "approved"}]
        xianxia["approval_requests"] = [{"name": "Constraint", "status": "pending"}]

    def _prepare_state(payload: dict) -> None:
        payload["vitals"]["current_hp"] = 19
        payload["vitals"]["temp_hp"] = 4
        xianxia_state = payload["xianxia"]
        xianxia_state["vitals"] = {
            "current_hp": 19,
            "temp_hp": 4,
            "current_stance": 16,
            "temp_stance": 3,
        }
        xianxia_state["energies"] = {
            "jing": {"current": 2},
            "qi": {"current": 3},
            "shen": {"current": 4},
        }
        xianxia_state["yin_yang"] = {"yin_current": 2, "yang_current": 3}
        xianxia_state["dao"] = {"current": 2}

    _write_campaign_config(app, _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Divine Rebuild Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "divine-rebuild-crane", _make_immortal)
    _write_character_state(app, "divine-rebuild-crane", _prepare_state)

    review_revision = _character_state_revision(app, "divine-rebuild-crane")
    review_response = client.post(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation",
        data={
            "expected_revision": str(review_revision),
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Divine",
            "realm_ascension_gm_review_note": "GM review approved for Divine rebuild.",
        },
        follow_redirects=False,
    )
    assert review_response.status_code == 302

    reset_revision = _character_state_revision(app, "divine-rebuild-crane")
    reset_response = client.post(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation",
        data={
            "expected_revision": str(reset_revision),
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Divine",
            "realm_ascension_reset_notes": "Ready for Divine point assignment.",
        },
        follow_redirects=False,
    )
    assert reset_response.status_code == 302

    rebuild_html = client.get(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation"
    ).get_data(as_text=True)
    assert "Apply Divine Rebuild" in rebuild_html
    assert 'name="cultivation_action" value="apply_divine_realm_rebuild"' in rebuild_html
    assert "Spend exactly 25 total Attribute/Effort points" in rebuild_html

    rebuild_revision = _character_state_revision(app, "divine-rebuild-crane")
    invalid_total_response = client.post(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_divine_realm_rebuild",
            "target_realm": "Divine",
            "realm_rebuild_attribute_str": "12",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "4",
            "realm_rebuild_effort_weapon": "3",
            "realm_rebuild_effort_guns_explosive": "1",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
        },
        follow_redirects=True,
    )
    assert invalid_total_response.status_code == 200
    assert (
        "Divine rebuild must spend exactly 25 Attribute/Effort points; submitted 24."
        in invalid_total_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "divine-rebuild-crane") == rebuild_revision

    invalid_cap_response = client.post(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_divine_realm_rebuild",
            "target_realm": "Divine",
            "realm_rebuild_attribute_str": "13",
            "realm_rebuild_attribute_dex": "0",
            "realm_rebuild_attribute_con": "0",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "4",
            "realm_rebuild_effort_weapon": "4",
            "realm_rebuild_effort_guns_explosive": "2",
            "realm_rebuild_effort_magic": "2",
            "realm_rebuild_effort_ultimate": "0",
        },
        follow_redirects=True,
    )
    assert invalid_cap_response.status_code == 200
    assert (
        "Strength cannot exceed 12 for the Divine rebuild."
        in invalid_cap_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "divine-rebuild-crane") == rebuild_revision

    valid_response = client.post(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation",
        data={
            "expected_revision": str(rebuild_revision),
            "cultivation_action": "apply_divine_realm_rebuild",
            "target_realm": "Divine",
            "realm_rebuild_attribute_str": "12",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "4",
            "realm_rebuild_effort_weapon": "3",
            "realm_rebuild_effort_guns_explosive": "2",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_rebuild_notes": "GM approved the Divine rebuild math.",
        },
        follow_redirects=False,
    )
    assert valid_response.status_code == 302
    assert valid_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation#xianxia-cultivation-realm-ascension"
    )

    definition_payload = _read_character_definition(app, "divine-rebuild-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["realm"] == "Divine"
    assert xianxia["actions_per_turn"] == 4
    assert xianxia["attributes"] == {
        "str": 12,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 4,
        "weapon": 3,
        "guns_explosive": 2,
        "magic": 1,
        "ultimate": 0,
    }
    assert xianxia["energies"] == {
        "jing": {"max": 4},
        "qi": {"max": 5},
        "shen": {"max": 6},
    }
    assert xianxia["yin_yang"] == {"yin_max": 3, "yang_max": 4}
    assert xianxia["insight"] == {"available": 9, "spent": 6}
    assert xianxia["durability"]["hp_max"] == 31
    assert xianxia["durability"]["stance_max"] == 29
    assert xianxia["durability"]["manual_armor_bonus"] == 2
    assert xianxia["durability"]["defense"] == 13
    assert xianxia["generic_techniques"] == [
        {
            "name": "Cloud Step",
            "systems_ref": {"slug": "cloud-step"},
            "generic_technique_key": "cloud_step",
        }
    ]
    assert xianxia["variants"] == [{"name": "Approved variant", "status": "approved"}]
    assert xianxia["approval_requests"] == [{"name": "Constraint", "status": "pending"}]
    rebuild_event = xianxia["advancement_history"][-1]
    _assert_event_contains(
        rebuild_event,
        {
            "action": "realm_ascension_divine_rebuild_applied",
            "target": "Divine",
            "current_realm": "Immortal",
            "target_realm": "Divine",
            "status": "applied_pending_final_confirmation",
            "rebuild_budget": 25,
            "stat_cap": 12,
            "actions_per_turn": 4,
            "attributes_after_total": 15,
            "efforts_after_total": 10,
            "total_rebuild_points": 25,
            "notes": "GM approved the Divine rebuild math.",
        },
    )
    assert rebuild_event["pre_ascension_state"]["realm"] == "Immortal"
    assert rebuild_event["pre_ascension_state"]["actions_per_turn"] == 3
    assert rebuild_event["pre_ascension_state"]["attributes_total"] == 18
    assert rebuild_event["pre_ascension_state"]["efforts_total"] == 5
    assert rebuild_event["pre_ascension_state"]["insight"] == {
        "available": 9,
        "spent": 6,
    }
    assert rebuild_event["post_ascension_state"]["realm"] == "Divine"
    assert rebuild_event["post_ascension_state"]["actions_per_turn"] == 4
    assert rebuild_event["post_ascension_state"]["attributes"] == {
        "str": 12,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert rebuild_event["post_ascension_state"]["efforts"] == {
        "basic": 4,
        "weapon": 3,
        "guns_explosive": 2,
        "magic": 1,
        "ultimate": 0,
    }
    assert rebuild_event["post_ascension_state"]["durability"]["hp_max"] == 31
    assert rebuild_event["post_ascension_state"]["durability"]["stance_max"] == 29
    assert (
        rebuild_event["pre_ascension_summary"]
        == "Immortal Realm, 3 actions; Attributes 18, Efforts 5; HP max 31, "
        "Stance max 29; Insight 9 available/6 spent; Martial Arts 3; "
        "Generic Techniques 1"
    )
    assert (
        rebuild_event["post_ascension_summary"]
        == "Divine Realm, 4 actions; Attributes 15, Efforts 10; HP max 31, "
        "Stance max 29; Insight 9 available/6 spent; Martial Arts 3; "
        "Generic Techniques 1"
    )

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "divine-rebuild-crane")
        assert record is not None
        state = record.state_record.state
    assert state["vitals"] == {"current_hp": 19, "temp_hp": 4}
    assert state["xianxia"]["vitals"] == {
        "current_hp": 19,
        "temp_hp": 4,
        "current_stance": 16,
        "temp_stance": 3,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 3},
        "shen": {"current": 4},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 2, "yang_current": 3}
    assert state["xianxia"]["dao"] == {"current": 2}
    assert _character_state_revision(app, "divine-rebuild-crane") == rebuild_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/divine-rebuild-crane/cultivation"
    ).get_data(as_text=True)
    assert "Latest Divine Rebuild" in updated_html
    assert "Realm Ascension Divine Rebuild Applied" in updated_html
    assert "25 of 25" in updated_html
    assert "Post-ascension state:" in updated_html
    assert "Divine Realm, 4 actions; Attributes 15, Efforts 10" in updated_html
    assert "apply_divine_realm_rebuild" not in updated_html


def test_xianxia_cultivation_route_covers_realm_ascension_matrix_and_preservation(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload["xianxia"]
        xianxia["attributes"] = {
            "str": 10,
            "dex": 2,
            "con": 4,
            "int": 1,
            "wis": 3,
            "cha": 2,
        }
        xianxia["efforts"] = {
            "basic": 4,
            "weapon": 3,
            "guns_explosive": 2,
            "magic": 5,
            "ultimate": 1,
        }
        xianxia["energies"] = {
            "jing": {"max": 4},
            "qi": {"max": 5},
            "shen": {"max": 6},
        }
        xianxia["yin_yang"] = {"yin_max": 3, "yang_max": 4}
        xianxia["insight"] = {"available": 11, "spent": 7}
        xianxia["durability"] = {
            "hp_max": 32,
            "stance_max": 34,
            "manual_armor_bonus": 2,
            "defense": 16,
        }
        xianxia["generic_techniques"] = [
            {
                "name": "Cloud Step",
                "generic_technique_key": "cloud_step",
                "systems_ref": {"slug": "cloud-step"},
            }
        ]
        xianxia["variants"] = [{"name": "Approved variant", "status": "approved"}]
        xianxia["dao_immolating_techniques"] = {
            "prepared": [{"name": "Last Dawn"}],
            "use_history": [
                {
                    "name": "Old Flame",
                    "approval_required": True,
                    "approval_status": "pending",
                    "insight_cost": 10,
                    "one_use": True,
                }
            ],
        }
        xianxia["approval_requests"] = [{"name": "Constraint", "status": "pending"}]
        xianxia["companions"] = [{"name": "Paper Crane"}]

    def _prepare_state(payload: dict) -> None:
        payload["vitals"]["current_hp"] = 21
        payload["vitals"]["temp_hp"] = 4
        payload["notes"]["player_notes_markdown"] = "Preserve this note."
        xianxia_state = payload["xianxia"]
        xianxia_state["vitals"] = {
            "current_hp": 21,
            "temp_hp": 4,
            "current_stance": 18,
            "temp_stance": 3,
        }
        xianxia_state["energies"] = {
            "jing": {"current": 2},
            "qi": {"current": 3},
            "shen": {"current": 4},
        }
        xianxia_state["yin_yang"] = {"yin_current": 2, "yang_current": 3}
        xianxia_state["dao"] = {"current": 2}
        xianxia_state["active_stance"] = {"name": "Mountain Root"}
        xianxia_state["active_aura"] = {"name": "Quiet Moon"}
        xianxia_state["notes"] = {"player_notes_markdown": "Preserve this note."}

    def _post_cultivation(
        *,
        action: str,
        expected_revision: int,
        data: dict[str, str],
        follow_redirects: bool = False,
    ):
        return client.post(
            "/campaigns/linden-pass/characters/ascension-matrix-crane/cultivation",
            data={
                "expected_revision": str(expected_revision),
                "cultivation_action": action,
                **data,
            },
            follow_redirects=follow_redirects,
        )

    def _assert_non_reset_data_preserved() -> None:
        definition_payload = _read_character_definition(app, "ascension-matrix-crane")
        xianxia = definition_payload["xianxia"]
        assert xianxia["energies"] == expected_energies
        assert xianxia["yin_yang"] == expected_yin_yang
        assert xianxia["insight"] == expected_insight
        assert xianxia["durability"]["hp_max"] == 32
        assert xianxia["durability"]["stance_max"] == 34
        assert xianxia["durability"]["manual_armor_bonus"] == 2
        assert xianxia["martial_arts"] == expected_martial_arts
        assert xianxia["generic_techniques"] == expected_generic_techniques
        assert xianxia["variants"] == expected_variants
        assert xianxia["dao_immolating_techniques"] == expected_dao_immolating
        assert xianxia["approval_requests"] == expected_approval_requests
        assert xianxia["companions"] == expected_companions

        with app.app_context():
            repository = app.extensions["character_repository"]
            record = repository.get_character("linden-pass", "ascension-matrix-crane")
            assert record is not None
            state = record.state_record.state
        assert state["vitals"] == {"current_hp": 21, "temp_hp": 4}
        assert state["notes"]["player_notes_markdown"] == "Preserve this note."
        assert state["xianxia"]["vitals"] == {
            "current_hp": 21,
            "temp_hp": 4,
            "current_stance": 18,
            "temp_stance": 3,
        }
        assert state["xianxia"]["energies"] == {
            "jing": {"current": 2},
            "qi": {"current": 3},
            "shen": {"current": 4},
        }
        assert state["xianxia"]["yin_yang"] == {
            "yin_current": 2,
            "yang_current": 3,
        }
        assert state["xianxia"]["dao"] == {"current": 2}
        assert state["xianxia"]["active_stance"] == {"name": "Mountain Root"}
        assert state["xianxia"]["active_aura"] == {"name": "Quiet Moon"}
        assert state["xianxia"]["notes"] == {
            "player_notes_markdown": "Preserve this note."
        }

    _write_campaign_config(app, _mutate_campaign)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Ascension Matrix Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    _write_character_definition(app, "ascension-matrix-crane", _prepare_definition)
    _write_character_state(app, "ascension-matrix-crane", _prepare_state)

    initial_definition = _read_character_definition(app, "ascension-matrix-crane")
    initial_xianxia = initial_definition["xianxia"]
    expected_energies = deepcopy(initial_xianxia["energies"])
    expected_yin_yang = deepcopy(initial_xianxia["yin_yang"])
    expected_insight = deepcopy(initial_xianxia["insight"])
    expected_martial_arts = deepcopy(initial_xianxia["martial_arts"])
    expected_generic_techniques = deepcopy(initial_xianxia["generic_techniques"])
    expected_variants = deepcopy(initial_xianxia["variants"])
    expected_dao_immolating = deepcopy(initial_xianxia["dao_immolating_techniques"])
    expected_approval_requests = deepcopy(initial_xianxia["approval_requests"])
    expected_companions = deepcopy(initial_xianxia["companions"])

    starting_revision = _character_state_revision(app, "ascension-matrix-crane")
    illegal_target_response = _post_cultivation(
        action="start_realm_ascension_review",
        expected_revision=starting_revision,
        data={
            "target_realm": "Divine",
            "realm_ascension_gm_review_note": "Trying to skip Immortal.",
        },
        follow_redirects=True,
    )
    assert illegal_target_response.status_code == 200
    assert (
        "Realm ascension must move from Mortal to Immortal."
        in illegal_target_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "ascension-matrix-crane") == starting_revision
    assert _read_character_definition(app, "ascension-matrix-crane") == initial_definition

    review_response = _post_cultivation(
        action="start_realm_ascension_review",
        expected_revision=starting_revision,
        data={
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "GM approved Mortal to Immortal review.",
        },
    )
    assert review_response.status_code == 302

    reset_revision = _character_state_revision(app, "ascension-matrix-crane")
    reset_response = _post_cultivation(
        action="reset_realm_ascension_stats",
        expected_revision=reset_revision,
        data={"target_realm": "Immortal"},
    )
    assert reset_response.status_code == 302

    wrong_rebuild_revision = _character_state_revision(app, "ascension-matrix-crane")
    wrong_rebuild_response = _post_cultivation(
        action="apply_divine_realm_rebuild",
        expected_revision=wrong_rebuild_revision,
        data={"target_realm": "Divine"},
        follow_redirects=True,
    )
    assert wrong_rebuild_response.status_code == 200
    assert (
        "The Divine rebuild budget applies only to Immortal to Divine ascension."
        in wrong_rebuild_response.get_data(as_text=True)
    )
    assert (
        _character_state_revision(app, "ascension-matrix-crane")
        == wrong_rebuild_revision
    )
    _assert_non_reset_data_preserved()

    immortal_rebuild_response = _post_cultivation(
        action="apply_immortal_realm_rebuild",
        expected_revision=wrong_rebuild_revision,
        data={
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "3",
            "realm_rebuild_effort_weapon": "2",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_rebuild_notes": "Mortal to Immortal matrix rebuild.",
        },
    )
    assert immortal_rebuild_response.status_code == 302

    xianxia = _read_character_definition(app, "ascension-matrix-crane")["xianxia"]
    assert xianxia["realm"] == "Immortal"
    assert xianxia["actions_per_turn"] == 3
    assert xianxia["attributes"] == {
        "str": 6,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 3,
        "weapon": 2,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 0,
    }
    assert xianxia["advancement_history"][-1]["action"] == (
        "realm_ascension_immortal_rebuild_applied"
    )
    _assert_non_reset_data_preserved()

    confirmation_revision = _character_state_revision(app, "ascension-matrix-crane")
    confirmation_response = _post_cultivation(
        action="confirm_realm_ascension",
        expected_revision=confirmation_revision,
        data={
            "target_realm": "Immortal",
            "realm_ascension_gm_confirmation_note": "GM confirmed Immortal rebuild.",
        },
    )
    assert confirmation_response.status_code == 302

    _write_character_definition(
        app,
        "ascension-matrix-crane",
        lambda payload: payload["xianxia"]["attributes"].__setitem__("str", 15),
    )

    divine_review_revision = _character_state_revision(app, "ascension-matrix-crane")
    divine_review_response = _post_cultivation(
        action="start_realm_ascension_review",
        expected_revision=divine_review_revision,
        data={
            "target_realm": "Divine",
            "realm_ascension_gm_review_note": "GM approved Immortal to Divine review.",
        },
    )
    assert divine_review_response.status_code == 302

    divine_reset_revision = _character_state_revision(app, "ascension-matrix-crane")
    divine_reset_response = _post_cultivation(
        action="reset_realm_ascension_stats",
        expected_revision=divine_reset_revision,
        data={"target_realm": "Divine"},
    )
    assert divine_reset_response.status_code == 302

    divine_rebuild_revision = _character_state_revision(app, "ascension-matrix-crane")
    divine_rebuild_response = _post_cultivation(
        action="apply_divine_realm_rebuild",
        expected_revision=divine_rebuild_revision,
        data={
            "target_realm": "Divine",
            "realm_rebuild_attribute_str": "12",
            "realm_rebuild_attribute_dex": "2",
            "realm_rebuild_attribute_con": "1",
            "realm_rebuild_attribute_int": "0",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "4",
            "realm_rebuild_effort_weapon": "3",
            "realm_rebuild_effort_guns_explosive": "2",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_rebuild_notes": "Immortal to Divine matrix rebuild.",
        },
    )
    assert divine_rebuild_response.status_code == 302

    xianxia = _read_character_definition(app, "ascension-matrix-crane")["xianxia"]
    assert xianxia["realm"] == "Divine"
    assert xianxia["actions_per_turn"] == 4
    assert xianxia["attributes"] == {
        "str": 12,
        "dex": 2,
        "con": 1,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert xianxia["efforts"] == {
        "basic": 4,
        "weapon": 3,
        "guns_explosive": 2,
        "magic": 1,
        "ultimate": 0,
    }
    assert xianxia["advancement_history"][-1]["action"] == (
        "realm_ascension_divine_rebuild_applied"
    )
    _assert_non_reset_data_preserved()


def test_xianxia_cultivation_route_tracks_insight_available_and_spent(
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
        data=_valid_xianxia_create_data("Insight Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_response = client.get(
        "/campaigns/linden-pass/characters/insight-crane/cultivation"
    )
    assert cultivation_response.status_code == 200
    cultivation_html = cultivation_response.get_data(as_text=True)
    assert 'name="insight_available"' in cultivation_html
    assert 'name="insight_spent"' in cultivation_html

    starting_revision = _character_state_revision(app, "insight-crane")
    update_response = client.post(
        "/campaigns/linden-pass/characters/insight-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "insight_available": "7",
            "insight_spent": "3",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302
    assert update_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/insight-crane/cultivation#xianxia-cultivation-insight"
    )

    definition_payload = _read_character_definition(app, "insight-crane")
    assert definition_payload["xianxia"]["insight"] == {"available": 7, "spent": 3}
    assert definition_payload["xianxia"]["advancement_history"] == [
        {
            "action": "insight_counter_adjustment",
            "target": "Insight",
            "insight_available_before": 0,
            "insight_available_after": 7,
            "insight_available_delta": 7,
            "insight_spent_before": 0,
            "insight_spent_after": 3,
            "insight_spent_delta": 3,
        }
    ]
    assert _character_state_revision(app, "insight-crane") == starting_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/insight-crane/cultivation"
    ).get_data(as_text=True)
    assert 'name="insight_available"' in updated_html
    assert 'value="7"' in updated_html
    assert 'name="insight_spent"' in updated_html
    assert 'value="3"' in updated_html
    assert "Insight Counter Adjustment" in updated_html
    assert "Available Insight before:" in updated_html
    assert "Available Insight after:" in updated_html
    assert "Available Insight change:" in updated_html
    assert "Spent Insight before:" in updated_html
    assert "Spent Insight after:" in updated_html
    assert "Spent Insight change:" in updated_html

    resources_html = client.get(
        "/campaigns/linden-pass/characters/insight-crane?page=resources"
    ).get_data(as_text=True)
    assert "<h3>Insight</h3>" in resources_html
    assert "Spent 3" in resources_html

    current_revision = _character_state_revision(app, "insight-crane")
    invalid_response = client.post(
        "/campaigns/linden-pass/characters/insight-crane/cultivation",
        data={
            "expected_revision": str(current_revision),
            "insight_available": "-1",
            "insight_spent": "4",
        },
        follow_redirects=True,
    )
    assert invalid_response.status_code == 200
    assert "Insight available must be zero or greater." in invalid_response.get_data(as_text=True)
    assert _read_character_definition(app, "insight-crane")["xianxia"]["insight"] == {
        "available": 7,
        "spent": 3,
    }
    assert len(
        _read_character_definition(app, "insight-crane")["xianxia"]["advancement_history"]
    ) == 1
    assert _character_state_revision(app, "insight-crane") == current_revision


def test_xianxia_cultivation_route_records_gathering_insight_downtime_gains(
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
        data=_valid_xianxia_create_data("Insight Gatherer"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_response = client.get(
        "/campaigns/linden-pass/characters/insight-gatherer/cultivation"
    )
    assert cultivation_response.status_code == 200
    cultivation_html = cultivation_response.get_data(as_text=True)
    assert 'name="cultivation_action" value="record_gathering_insight"' in cultivation_html
    assert 'name="insight_gain_amount"' in cultivation_html
    assert 'name="gathering_insight_downtime"' in cultivation_html
    assert 'name="gathering_insight_notes"' in cultivation_html

    starting_revision = _character_state_revision(app, "insight-gatherer")
    gain_response = client.post(
        "/campaigns/linden-pass/characters/insight-gatherer/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "record_gathering_insight",
            "insight_gain_amount": "4",
            "gathering_insight_downtime": "3 days between sessions",
            "gathering_insight_notes": "Meditated under storm clouds.",
        },
        follow_redirects=False,
    )
    assert gain_response.status_code == 302
    assert gain_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/insight-gatherer/cultivation#xianxia-cultivation-gathering-insight"
    )

    definition_payload = _read_character_definition(app, "insight-gatherer")
    assert definition_payload["xianxia"]["insight"] == {"available": 4, "spent": 0}
    assert definition_payload["xianxia"]["advancement_history"] == [
        {
            "action": "gathering_insight",
            "amount": 4,
            "target": "Insight",
            "downtime": "3 days between sessions",
            "notes": "Meditated under storm clouds.",
        }
    ]
    assert _character_state_revision(app, "insight-gatherer") == starting_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/insight-gatherer/cultivation"
    ).get_data(as_text=True)
    assert "Gathering Insight" in updated_html
    assert "Amount:" in updated_html
    assert "4" in updated_html
    assert "Downtime:" in updated_html
    assert "3 days between sessions" in updated_html
    assert "Notes:" in updated_html
    assert "Meditated under storm clouds." in updated_html

    current_revision = _character_state_revision(app, "insight-gatherer")
    invalid_response = client.post(
        "/campaigns/linden-pass/characters/insight-gatherer/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "record_gathering_insight",
            "insight_gain_amount": "0",
        },
        follow_redirects=True,
    )
    assert invalid_response.status_code == 200
    assert "Gathered Insight must be at least 1." in invalid_response.get_data(as_text=True)
    assert _read_character_definition(app, "insight-gatherer")["xianxia"]["insight"] == {
        "available": 4,
        "spent": 0,
    }
    assert _character_state_revision(app, "insight-gatherer") == current_revision


def test_xianxia_cultivation_route_spends_insight_to_increase_energy(
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
        data=_valid_xianxia_create_data("Energy Cultivator"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/energy-cultivator/cultivation"
    ).get_data(as_text=True)
    assert 'name="cultivation_action" value="spend_cultivation_energy"' in cultivation_html
    assert 'name="energy_key" value="qi"' in cultivation_html
    assert "Spend 1 Insight to increase Qi by 1." in cultivation_html
    assert "Needs 1 more available Insight." in cultivation_html

    starting_revision = _character_state_revision(app, "energy-cultivator")
    insufficient_response = client.post(
        "/campaigns/linden-pass/characters/energy-cultivator/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "spend_cultivation_energy",
            "energy_key": "qi",
        },
        follow_redirects=True,
    )
    assert insufficient_response.status_code == 200
    assert (
        "Cultivation needs 1 Insight to increase Qi; only 0 available."
        in insufficient_response.get_data(as_text=True)
    )
    definition_payload = _read_character_definition(app, "energy-cultivator")
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["energies"] == {
        "jing": {"max": 1},
        "qi": {"max": 1},
        "shen": {"max": 1},
    }
    assert definition_payload["xianxia"]["advancement_history"] == []
    assert _character_state_revision(app, "energy-cultivator") == starting_revision

    insight_response = client.post(
        "/campaigns/linden-pass/characters/energy-cultivator/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    current_revision = _character_state_revision(app, "energy-cultivator")
    spend_response = client.post(
        "/campaigns/linden-pass/characters/energy-cultivator/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "spend_cultivation_energy",
            "energy_key": "qi",
            "cultivation_energy_notes": "Cultivated a moonlit reservoir.",
        },
        follow_redirects=False,
    )
    assert spend_response.status_code == 302
    assert spend_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/energy-cultivator/cultivation#xianxia-cultivation-energy"
    )

    definition_payload = _read_character_definition(app, "energy-cultivator")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 1, "spent": 1}
    assert xianxia["energies"] == {
        "jing": {"max": 1},
        "qi": {"max": 2},
        "shen": {"max": 1},
    }
    assert xianxia["advancement_history"][-1] == {
        "action": "cultivation_energy_increase",
        "amount": 1,
        "target": "Qi",
        "energy_key": "qi",
        "energy_maximum_increase": 1,
        "new_energy_maximum": 2,
        "notes": "Cultivated a moonlit reservoir.",
    }
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "energy-cultivator")
        assert record is not None
        assert record.state_record.state["xianxia"]["energies"] == {
            "jing": {"current": 1},
            "qi": {"current": 1},
            "shen": {"current": 1},
        }
    assert _character_state_revision(app, "energy-cultivator") == current_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/energy-cultivator/cultivation"
    ).get_data(as_text=True)
    assert "Current 1 / Max 2" in updated_html
    assert "Cultivation Energy Increase" in updated_html
    assert "Target:" in updated_html
    assert "Qi" in updated_html
    assert "Energy maximum increase:" in updated_html
    assert "New Energy maximum:" in updated_html
    assert "Cultivated a moonlit reservoir." in updated_html

    resources_html = client.get(
        "/campaigns/linden-pass/characters/energy-cultivator?page=resources"
    ).get_data(as_text=True)
    assert "<h3>Qi</h3>" in resources_html
    assert "Current 1 / Max 2" in resources_html


def test_xianxia_cultivation_route_spends_insight_on_meditation_to_increase_yin_yang(
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
        data=_valid_xianxia_create_data("Meditation Adept"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/meditation-adept/cultivation"
    ).get_data(as_text=True)
    assert 'name="cultivation_action" value="spend_meditation_yin_yang"' in cultivation_html
    assert 'name="yin_yang_key" value="yin"' in cultivation_html
    assert 'name="yin_yang_key" value="yang"' in cultivation_html
    assert "Spend 1 Insight to increase Yin by 1." in cultivation_html
    assert "Spend 1 Insight to increase Yang by 1." in cultivation_html
    assert "Needs 1 more available Insight." in cultivation_html

    starting_revision = _character_state_revision(app, "meditation-adept")
    insufficient_response = client.post(
        "/campaigns/linden-pass/characters/meditation-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "yin",
        },
        follow_redirects=True,
    )
    assert insufficient_response.status_code == 200
    assert (
        "Meditation needs 1 Insight to increase Yin; only 0 available."
        in insufficient_response.get_data(as_text=True)
    )
    definition_payload = _read_character_definition(app, "meditation-adept")
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["yin_yang"] == {
        "yin_max": 1,
        "yang_max": 1,
    }
    assert definition_payload["xianxia"]["advancement_history"] == []
    assert _character_state_revision(app, "meditation-adept") == starting_revision

    insight_response = client.post(
        "/campaigns/linden-pass/characters/meditation-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    current_revision = _character_state_revision(app, "meditation-adept")
    spend_response = client.post(
        "/campaigns/linden-pass/characters/meditation-adept/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "yang",
            "meditation_notes": "Balanced breath at dawn.",
        },
        follow_redirects=False,
    )
    assert spend_response.status_code == 302
    assert spend_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/meditation-adept/cultivation#xianxia-cultivation-meditation"
    )

    definition_payload = _read_character_definition(app, "meditation-adept")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 1, "spent": 1}
    assert xianxia["yin_yang"] == {
        "yin_max": 1,
        "yang_max": 2,
    }
    assert xianxia["advancement_history"][-1] == {
        "action": "meditation_yin_yang_increase",
        "amount": 1,
        "target": "Yang",
        "yin_yang_key": "yang",
        "yin_yang_maximum_increase": 1,
        "new_yin_yang_maximum": 2,
        "notes": "Balanced breath at dawn.",
    }
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "meditation-adept")
        assert record is not None
        assert record.state_record.state["xianxia"]["yin_yang"] == {
            "yin_current": 1,
            "yang_current": 1,
        }
    assert _character_state_revision(app, "meditation-adept") == current_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/meditation-adept/cultivation"
    ).get_data(as_text=True)
    assert "Meditation Yin Yang Increase" in updated_html
    assert "Target:" in updated_html
    assert "Yang" in updated_html
    assert "Yin/Yang maximum increase:" in updated_html
    assert "New Yin/Yang maximum:" in updated_html
    assert "Balanced breath at dawn." in updated_html

    resources_html = client.get(
        "/campaigns/linden-pass/characters/meditation-adept?page=resources"
    ).get_data(as_text=True)
    assert "<h3>Yang</h3>" in resources_html
    assert "Current 1 / Max 2" in resources_html


def test_xianxia_cultivation_route_spends_insight_on_conditioning_for_hp_or_effort(
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
        data=_valid_xianxia_create_data("Conditioning Adept"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation"
    ).get_data(as_text=True)
    assert 'name="cultivation_action" value="spend_conditioning"' in cultivation_html
    assert 'name="conditioning_target" value="hp"' in cultivation_html
    assert 'name="conditioning_target" value="effort"' in cultivation_html
    assert 'name="effort_key" value="magic"' in cultivation_html
    assert "Spend 1 Insight to increase HP maximum by 10." in cultivation_html
    assert "Spend 1 Insight to add 2 Magic points." in cultivation_html
    assert "Needs 1 more available Insight." in cultivation_html

    starting_revision = _character_state_revision(app, "conditioning-adept")
    insufficient_response = client.post(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "hp",
        },
        follow_redirects=True,
    )
    assert insufficient_response.status_code == 200
    assert (
        "Conditioning needs 1 Insight to increase HP; only 0 available."
        in insufficient_response.get_data(as_text=True)
    )
    definition_payload = _read_character_definition(app, "conditioning-adept")
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["durability"]["hp_max"] == 10
    assert definition_payload["xianxia"]["efforts"]["magic"] == 1
    assert definition_payload["xianxia"]["advancement_history"] == []
    assert _character_state_revision(app, "conditioning-adept") == starting_revision

    insight_response = client.post(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    current_revision = _character_state_revision(app, "conditioning-adept")
    hp_response = client.post(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "hp",
            "conditioning_notes": "Stone-body breathing.",
        },
        follow_redirects=False,
    )
    assert hp_response.status_code == 302
    assert hp_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation#xianxia-cultivation-conditioning"
    )

    definition_payload = _read_character_definition(app, "conditioning-adept")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 1, "spent": 1}
    assert xianxia["durability"]["hp_max"] == 20
    assert xianxia["efforts"]["magic"] == 1
    assert xianxia["advancement_history"][-1] == {
        "action": "conditioning_hp_increase",
        "amount": 1,
        "target": "HP",
        "hp_maximum_increase": 10,
        "new_hp_maximum": 20,
        "hp_maximum_cap": 50,
        "notes": "Stone-body breathing.",
    }
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "conditioning-adept")
        assert record is not None
        assert record.state_record.state["vitals"]["current_hp"] == 10
        assert record.state_record.state["xianxia"]["vitals"]["current_hp"] == 10
    assert _character_state_revision(app, "conditioning-adept") == current_revision + 1

    effort_revision = _character_state_revision(app, "conditioning-adept")
    effort_response = client.post(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation",
        data={
            "expected_revision": str(effort_revision),
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "effort",
            "effort_key": "magic",
            "conditioning_notes": "Refined spell-force output.",
        },
        follow_redirects=False,
    )
    assert effort_response.status_code == 302

    definition_payload = _read_character_definition(app, "conditioning-adept")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 0, "spent": 2}
    assert xianxia["durability"]["hp_max"] == 20
    assert xianxia["efforts"]["magic"] == 3
    assert xianxia["advancement_history"][-1] == {
        "action": "conditioning_effort_increase",
        "amount": 1,
        "target": "Magic",
        "effort_key": "magic",
        "effort_point_increase": 2,
        "new_effort_score": 3,
        "notes": "Refined spell-force output.",
    }
    assert _character_state_revision(app, "conditioning-adept") == effort_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/conditioning-adept/cultivation"
    ).get_data(as_text=True)
    assert "Current max 20 / Cap 50" in updated_html
    assert "Current score 3" in updated_html
    assert "Conditioning Hp Increase" in updated_html
    assert "HP maximum increase:" in updated_html
    assert "New HP maximum:" in updated_html
    assert "Conditioning Effort Increase" in updated_html
    assert "Effort point increase:" in updated_html
    assert "New Effort score:" in updated_html

    resources_html = client.get(
        "/campaigns/linden-pass/characters/conditioning-adept?page=resources"
    ).get_data(as_text=True)
    assert "<h3>HP</h3>" in resources_html
    assert "Current 10 / Max 20" in resources_html


def test_xianxia_cultivation_route_spends_insight_on_training_for_stance_or_attribute(
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
        data=_valid_xianxia_create_data("Training Adept"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/training-adept/cultivation"
    ).get_data(as_text=True)
    assert 'name="cultivation_action" value="spend_training"' in cultivation_html
    assert 'name="training_target" value="stance"' in cultivation_html
    assert 'name="training_target" value="attribute"' in cultivation_html
    assert 'name="attribute_key" value="con"' in cultivation_html
    assert "Spend 1 Insight to increase Stance maximum by 10." in cultivation_html
    assert "Spend 1 Insight to add 2 Constitution points." in cultivation_html
    assert "Needs 1 more available Insight." in cultivation_html

    starting_revision = _character_state_revision(app, "training-adept")
    insufficient_response = client.post(
        "/campaigns/linden-pass/characters/training-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "spend_training",
            "training_target": "stance",
        },
        follow_redirects=True,
    )
    assert insufficient_response.status_code == 200
    assert (
        "Training needs 1 Insight to increase Stance; only 0 available."
        in insufficient_response.get_data(as_text=True)
    )
    definition_payload = _read_character_definition(app, "training-adept")
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["durability"]["stance_max"] == 10
    assert definition_payload["xianxia"]["attributes"]["con"] == 3
    assert definition_payload["xianxia"]["advancement_history"] == []
    assert _character_state_revision(app, "training-adept") == starting_revision

    insight_response = client.post(
        "/campaigns/linden-pass/characters/training-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    current_revision = _character_state_revision(app, "training-adept")
    stance_response = client.post(
        "/campaigns/linden-pass/characters/training-adept/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "spend_training",
            "training_target": "stance",
            "training_notes": "Holding horse stance beneath the waterfall.",
        },
        follow_redirects=False,
    )
    assert stance_response.status_code == 302
    assert stance_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/training-adept/cultivation#xianxia-cultivation-training"
    )

    definition_payload = _read_character_definition(app, "training-adept")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 1, "spent": 1}
    assert xianxia["durability"]["stance_max"] == 20
    assert xianxia["attributes"]["con"] == 3
    assert xianxia["advancement_history"][-1] == {
        "action": "training_stance_increase",
        "amount": 1,
        "target": "Stance",
        "stance_maximum_increase": 10,
        "new_stance_maximum": 20,
        "stance_maximum_cap": 50,
        "notes": "Holding horse stance beneath the waterfall.",
    }
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "training-adept")
        assert record is not None
        assert record.state_record.state["xianxia"]["vitals"]["current_stance"] == 10
    assert _character_state_revision(app, "training-adept") == current_revision + 1

    attribute_revision = _character_state_revision(app, "training-adept")
    attribute_response = client.post(
        "/campaigns/linden-pass/characters/training-adept/cultivation",
        data={
            "expected_revision": str(attribute_revision),
            "cultivation_action": "spend_training",
            "training_target": "attribute",
            "attribute_key": "con",
            "training_notes": "Tempered core and breath.",
        },
        follow_redirects=False,
    )
    assert attribute_response.status_code == 302

    definition_payload = _read_character_definition(app, "training-adept")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 0, "spent": 2}
    assert xianxia["durability"]["stance_max"] == 20
    assert xianxia["durability"]["defense"] == 15
    assert xianxia["attributes"]["con"] == 5
    assert xianxia["advancement_history"][-1] == {
        "action": "training_attribute_increase",
        "amount": 1,
        "target": "Constitution",
        "attribute_key": "con",
        "attribute_point_increase": 2,
        "new_attribute_score": 5,
        "notes": "Tempered core and breath.",
    }
    assert _character_state_revision(app, "training-adept") == attribute_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/training-adept/cultivation"
    ).get_data(as_text=True)
    assert "Current max 20 / Cap 50" in updated_html
    assert "Current score 5" in updated_html
    assert "Training Stance Increase" in updated_html
    assert "Stance maximum increase:" in updated_html
    assert "New Stance maximum:" in updated_html
    assert "Training Attribute Increase" in updated_html
    assert "Attribute point increase:" in updated_html
    assert "New Attribute score:" in updated_html

    resources_html = client.get(
        "/campaigns/linden-pass/characters/training-adept?page=resources"
    ).get_data(as_text=True)
    assert "<h3>Stance</h3>" in resources_html
    assert "Current 10 / Max 20" in resources_html

    equipment_html = client.get(
        "/campaigns/linden-pass/characters/training-adept?page=equipment"
    ).get_data(as_text=True)
    assert "Defense calculation" in equipment_html
    assert "Constitution" in equipment_html
    assert "Defense = 10 + 0 + 5" in equipment_html
    assert "15" in equipment_html


def test_xianxia_cultivation_route_spends_insight_to_learn_generic_technique(
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
    with app.app_context():
        app.extensions["repository_store"].refresh()
        systems_service = app.extensions["systems_service"]
        systems_service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        qi_blast = systems_service.get_entry_by_slug_for_campaign("linden-pass", "qi-blast")
        assert qi_blast is not None

    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Technique Adept"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/technique-adept/cultivation"
    ).get_data(as_text=True)
    assert 'name="cultivation_action" value="learn_generic_technique"' in cultivation_html
    assert f'name="generic_technique_entry_key" value="{qi_blast.entry_key}"' in cultivation_html
    assert "Spend 1 Insight to learn Qi Blast." in cultivation_html
    assert "Needs 1 more available Insight." in cultivation_html

    starting_revision = _character_state_revision(app, "technique-adept")
    insufficient_response = client.post(
        "/campaigns/linden-pass/characters/technique-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": qi_blast.entry_key,
        },
        follow_redirects=True,
    )
    assert insufficient_response.status_code == 200
    assert "Qi Blast needs 1 Insight to learn; only 0 available." in insufficient_response.get_data(
        as_text=True
    )
    definition_payload = _read_character_definition(app, "technique-adept")
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["generic_techniques"] == []
    assert definition_payload["xianxia"]["advancement_history"] == []
    assert _character_state_revision(app, "technique-adept") == starting_revision

    insight_response = client.post(
        "/campaigns/linden-pass/characters/technique-adept/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    current_revision = _character_state_revision(app, "technique-adept")
    learn_response = client.post(
        "/campaigns/linden-pass/characters/technique-adept/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": qi_blast.entry_key,
            "generic_technique_notes": "Focused breath into a visible strike.",
        },
        follow_redirects=False,
    )
    assert learn_response.status_code == 302
    assert learn_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/technique-adept/cultivation#xianxia-cultivation-techniques"
    )

    definition_payload = _read_character_definition(app, "technique-adept")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 1, "spent": 1}
    assert len(xianxia["generic_techniques"]) == 1
    learned_technique = xianxia["generic_techniques"][0]
    assert learned_technique["name"] == "Qi Blast"
    assert learned_technique["systems_ref"]["entry_key"] == qi_blast.entry_key
    assert learned_technique["systems_ref"]["slug"] == "qi-blast"
    assert learned_technique["generic_technique_key"] == "qi_blast"
    assert learned_technique["insight_spent"] == 1
    assert learned_technique["support_state"] == "reference_only"
    assert learned_technique["learnable_without_master"] is True
    assert learned_technique["requires_master"] is False
    assert learned_technique["notes"] == "Focused breath into a visible strike."
    assert xianxia["advancement_history"][-1] == {
        "action": "generic_technique_learned",
        "amount": 1,
        "target": "Qi Blast",
        "generic_technique_key": "qi_blast",
        "systems_ref": learned_technique["systems_ref"],
        "insight_cost": 1,
        "notes": "Focused breath into a visible strike.",
    }
    assert _character_state_revision(app, "technique-adept") == current_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/technique-adept/cultivation"
    ).get_data(as_text=True)
    assert "Generic Technique Learned" in updated_html
    assert "Generic Technique key:" in updated_html
    assert "qi_blast" in updated_html
    assert "Focused breath into a visible strike." in updated_html

    sheet_html = client.get(
        "/campaigns/linden-pass/characters/technique-adept?page=techniques"
    ).get_data(as_text=True)
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in sheet_html
    assert "Qi Blast" in sheet_html
    assert "Insight 1" in sheet_html
    assert "Learnable without a Master" in sheet_html

    duplicate_revision = _character_state_revision(app, "technique-adept")
    duplicate_response = client.post(
        "/campaigns/linden-pass/characters/technique-adept/cultivation",
        data={
            "expected_revision": str(duplicate_revision),
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": qi_blast.entry_key,
        },
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "Qi Blast is already learned." in duplicate_response.get_data(as_text=True)
    assert _character_state_revision(app, "technique-adept") == duplicate_revision


def test_xianxia_cultivation_route_spends_insight_to_advance_martial_art_rank(
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
        data=_valid_xianxia_create_data("Rank Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    starting_revision = _character_state_revision(app, "rank-crane")
    insight_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    cultivation_html = client.get(
        "/campaigns/linden-pass/characters/rank-crane/cultivation"
    ).get_data(as_text=True)
    assert (
        'name="cultivation_action" value="advance_martial_art_rank"'
        in cultivation_html
    )
    assert 'name="target_rank_key" value="novice"' in cultivation_html
    assert "Spend 1 Insight to advance to Novice." in cultivation_html

    current_revision = _character_state_revision(app, "rank-crane")
    advance_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(current_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "novice",
        },
        follow_redirects=False,
    )
    assert advance_response.status_code == 302
    assert advance_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/rank-crane/cultivation#xianxia-cultivation-martial-arts"
    )

    definition_payload = _read_character_definition(app, "rank-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 1, "spent": 1}
    assert xianxia["energies"] == {
        "jing": {"max": 2},
        "qi": {"max": 2},
        "shen": {"max": 1},
    }
    first_art = xianxia["martial_arts"][0]
    assert first_art["current_rank_key"] == "novice"
    assert first_art["current_rank"] == "Novice"
    assert "xianxia:demons-fist:novice" in first_art["learned_rank_refs"]
    assert first_art["rank_energy_maximum_increases"] == {
        "novice": {"jing": 1, "qi": 1, "shen": 0}
    }
    assert first_art["insight_spent"] == 1
    assert xianxia["advancement_history"][-1] == {
        "action": "martial_art_rank_advance",
        "amount": 1,
        "target": "Demon's Fist",
        "rank": "Novice",
        "rank_ref": "xianxia:demons-fist:novice",
        "systems_ref": first_art["systems_ref"],
        "energy_maximum_increases": {"jing": 1, "qi": 1, "shen": 0},
    }
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "rank-crane")
        assert record is not None
        assert record.state_record.state["xianxia"]["energies"] == {
            "jing": {"current": 1},
            "qi": {"current": 1},
            "shen": {"current": 1},
        }
    assert _character_state_revision(app, "rank-crane") == current_revision + 1

    updated_html = client.get(
        "/campaigns/linden-pass/characters/rank-crane/cultivation"
    ).get_data(as_text=True)
    assert "Current rank: Novice" in updated_html
    assert "Spend 1 Insight to advance to Apprentice." in updated_html
    teacher_note = (
        "Requires learning under a Master. Teacher requirements are stored as notes "
        "for now rather than enforced advancement blockers."
    )
    assert teacher_note in updated_html
    assert "Martial Art Rank Advance" in updated_html
    assert "Rank:" in updated_html
    assert "Novice" in updated_html

    next_revision = _character_state_revision(app, "rank-crane")
    apprentice_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(next_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "apprentice",
        },
        follow_redirects=False,
    )
    assert apprentice_response.status_code == 302
    assert apprentice_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/rank-crane/cultivation#xianxia-cultivation-martial-arts"
    )

    definition_payload = _read_character_definition(app, "rank-crane")
    xianxia = definition_payload["xianxia"]
    assert xianxia["insight"] == {"available": 0, "spent": 2}
    assert xianxia["energies"] == {
        "jing": {"max": 3},
        "qi": {"max": 2},
        "shen": {"max": 2},
    }
    first_art = xianxia["martial_arts"][0]
    assert first_art["current_rank_key"] == "apprentice"
    assert first_art["current_rank"] == "Apprentice"
    assert "xianxia:demons-fist:apprentice" in first_art["learned_rank_refs"]
    assert first_art["rank_energy_maximum_increases"] == {
        "novice": {"jing": 1, "qi": 1, "shen": 0},
        "apprentice": {"jing": 1, "qi": 0, "shen": 1},
    }
    assert first_art["rank_teacher_breakthrough_notes"] == {
        "apprentice": {
            "requirement": "master",
            "note": teacher_note,
        }
    }
    assert xianxia["advancement_history"][-1] == {
        "action": "martial_art_rank_advance",
        "amount": 1,
        "target": "Demon's Fist",
        "rank": "Apprentice",
        "rank_ref": "xianxia:demons-fist:apprentice",
        "systems_ref": first_art["systems_ref"],
        "energy_maximum_increases": {"jing": 1, "qi": 0, "shen": 1},
        "teacher_breakthrough_requirement": "master",
        "teacher_breakthrough_note": teacher_note,
    }

    apprentice_html = client.get(
        "/campaigns/linden-pass/characters/rank-crane/cultivation"
    ).get_data(as_text=True)
    assert "Teacher/breakthrough note:" in apprentice_html
    assert teacher_note in apprentice_html
    resources_html = client.get(
        "/campaigns/linden-pass/characters/rank-crane?page=resources"
    ).get_data(as_text=True)
    assert "<h3>Jing</h3>" in resources_html
    assert "<h3>Qi</h3>" in resources_html
    assert "Current 1 / Max 3" in resources_html
    assert "Current 1 / Max 2" in resources_html
    assert "<h3>Shen</h3>" in resources_html
    assert "Current 1 / Max 2" in resources_html

    insight_revision = _character_state_revision(app, "rank-crane")
    insight_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(insight_revision),
            "cultivation_action": "save_insight",
            "insight_available": "2",
            "insight_spent": "2",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    master_revision = _character_state_revision(app, "rank-crane")
    master_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(master_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "master",
        },
        follow_redirects=False,
    )
    assert master_response.status_code == 302

    master_html = client.get(
        "/campaigns/linden-pass/characters/rank-crane/cultivation"
    ).get_data(as_text=True)
    legendary_requirement = (
        "Requires all previous ranks in the Martial Art plus a quest or "
        "mythic-level master; primarily narrative completion rather than a "
        "purely mechanical purchase."
    )
    assert 'name="target_rank_key" value="legendary"' in master_html
    assert 'name="legendary_quest_note"' in master_html
    assert "Quest or mythic-master note" in master_html
    assert legendary_requirement in master_html

    legendary_revision = _character_state_revision(app, "rank-crane")
    missing_note_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(legendary_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "legendary",
            "legendary_quest_note": " ",
        },
        follow_redirects=True,
    )
    assert missing_note_response.status_code == 200
    assert (
        "Record a quest or mythic-master note before advancing Demon&#39;s Fist to Legendary."
        in missing_note_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "rank-crane") == legendary_revision

    legendary_note = "Completed the Furnace Trial with a mythic-level master."
    legendary_response = client.post(
        "/campaigns/linden-pass/characters/rank-crane/cultivation",
        data={
            "expected_revision": str(legendary_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "legendary",
            "legendary_quest_note": legendary_note,
        },
        follow_redirects=False,
    )
    assert legendary_response.status_code == 302

    definition_payload = _read_character_definition(app, "rank-crane")
    xianxia = definition_payload["xianxia"]
    first_art = xianxia["martial_arts"][0]
    assert xianxia["insight"] == {"available": 0, "spent": 4}
    assert first_art["current_rank_key"] == "legendary"
    assert first_art["current_rank"] == "Legendary"
    assert "xianxia:demons-fist:legendary" in first_art["learned_rank_refs"]
    assert first_art["rank_legendary_prerequisite_notes"] == {
        "legendary": {
            "requirement": "quest_or_mythic_master",
            "note": legendary_note,
            "prerequisite_note": legendary_requirement,
        }
    }
    assert xianxia["advancement_history"][-1] == {
        "action": "martial_art_rank_advance",
        "amount": 1,
        "target": "Demon's Fist",
        "rank": "Legendary",
        "rank_ref": "xianxia:demons-fist:legendary",
        "systems_ref": first_art["systems_ref"],
        "energy_maximum_increases": {"jing": 2, "qi": 1, "shen": 1},
        "teacher_breakthrough_requirement": "ascension_breakthrough",
        "teacher_breakthrough_note": "Requires an Ascension Breakthrough.",
        "legendary_prerequisite": "quest_or_mythic_master",
        "legendary_quest_note": legendary_note,
        "legendary_prerequisite_note": legendary_requirement,
    }

    legendary_html = client.get(
        "/campaigns/linden-pass/characters/rank-crane/cultivation"
    ).get_data(as_text=True)
    assert "Current rank: Legendary" in legendary_html
    assert "Legendary quest/mythic-master note:" in legendary_html
    assert legendary_note in legendary_html


def test_xianxia_cultivation_rank_advance_requires_next_rank_and_insight(
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
        data=_valid_xianxia_create_data("Rank Guard Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    starting_revision = _character_state_revision(app, "rank-guard-crane")
    skip_response = client.post(
        "/campaigns/linden-pass/characters/rank-guard-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "apprentice",
        },
        follow_redirects=True,
    )
    assert skip_response.status_code == 200
    assert (
        "Advance Demon&#39;s Fist to Novice before Apprentice."
        in skip_response.get_data(as_text=True)
    )
    assert _read_character_definition(app, "rank-guard-crane")["xianxia"]["insight"] == {
        "available": 0,
        "spent": 0,
    }
    assert _character_state_revision(app, "rank-guard-crane") == starting_revision

    insufficient_response = client.post(
        "/campaigns/linden-pass/characters/rank-guard-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "novice",
        },
        follow_redirects=True,
    )
    assert insufficient_response.status_code == 200
    assert (
        "Demon&#39;s Fist needs 1 Insight to advance to Novice; only 0 available."
        in insufficient_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "rank-guard-crane") == starting_revision

    legendary_skip_response = client.post(
        "/campaigns/linden-pass/characters/rank-guard-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "legendary",
            "legendary_quest_note": "Completed a mythic-master quest.",
        },
        follow_redirects=True,
    )
    assert legendary_skip_response.status_code == 200
    assert (
        "Record Novice, Apprentice, Master for Demon&#39;s Fist before Legendary."
        in legendary_skip_response.get_data(as_text=True)
    )
    assert _character_state_revision(app, "rank-guard-crane") == starting_revision


def test_xianxia_cultivation_spend_matrix_preserves_history_and_mutable_pools(
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
        data=_valid_xianxia_create_data("Spend Matrix Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    def _lower_mutable_pools(payload: dict) -> None:
        payload.setdefault("vitals", {})["current_hp"] = 6
        xianxia = payload.setdefault("xianxia", {})
        xianxia.setdefault("vitals", {})["current_hp"] = 6
        xianxia.setdefault("vitals", {})["current_stance"] = 4
        xianxia["energies"] = {
            "jing": {"current": 0},
            "qi": {"current": 1},
            "shen": {"current": 1},
        }
        xianxia["yin_yang"] = {
            "yin_current": 0,
            "yang_current": 1,
        }

    _write_character_state(app, "spend-matrix-crane", _lower_mutable_pools)

    starting_revision = _character_state_revision(app, "spend-matrix-crane")
    insight_response = client.post(
        "/campaigns/linden-pass/characters/spend-matrix-crane/cultivation",
        data={
            "expected_revision": str(starting_revision),
            "cultivation_action": "save_insight",
            "insight_available": "5",
            "insight_spent": "0",
        },
        follow_redirects=False,
    )
    assert insight_response.status_code == 302

    spend_actions = [
        {
            "cultivation_action": "spend_cultivation_energy",
            "energy_key": "jing",
            "cultivation_energy_notes": "Deepened the lower furnace.",
        },
        {
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "yin",
            "meditation_notes": "Settled the cold current.",
        },
        {
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "hp",
            "conditioning_notes": "Hardened breath and bone.",
        },
        {
            "cultivation_action": "spend_training",
            "training_target": "stance",
            "training_notes": "Held the stance through the night.",
        },
    ]
    for form_data in spend_actions:
        current_revision = _character_state_revision(app, "spend-matrix-crane")
        response = client.post(
            "/campaigns/linden-pass/characters/spend-matrix-crane/cultivation",
            data={"expected_revision": str(current_revision), **form_data},
            follow_redirects=False,
        )
        assert response.status_code == 302

    pre_invalid_payload = _read_character_definition(app, "spend-matrix-crane")
    pre_invalid_revision = _character_state_revision(app, "spend-matrix-crane")
    skip_rank_response = client.post(
        "/campaigns/linden-pass/characters/spend-matrix-crane/cultivation",
        data={
            "expected_revision": str(pre_invalid_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "master",
        },
        follow_redirects=True,
    )
    assert skip_rank_response.status_code == 200
    assert (
        "Advance Demon&#39;s Fist to Novice before Master."
        in skip_rank_response.get_data(as_text=True)
    )
    assert _read_character_definition(app, "spend-matrix-crane") == pre_invalid_payload
    assert _character_state_revision(app, "spend-matrix-crane") == pre_invalid_revision

    rank_response = client.post(
        "/campaigns/linden-pass/characters/spend-matrix-crane/cultivation",
        data={
            "expected_revision": str(pre_invalid_revision),
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "novice",
        },
        follow_redirects=False,
    )
    assert rank_response.status_code == 302

    final_payload = _read_character_definition(app, "spend-matrix-crane")
    final_revision = _character_state_revision(app, "spend-matrix-crane")
    no_insight_response = client.post(
        "/campaigns/linden-pass/characters/spend-matrix-crane/cultivation",
        data={
            "expected_revision": str(final_revision),
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "yang",
        },
        follow_redirects=True,
    )
    assert no_insight_response.status_code == 200
    assert (
        "Meditation needs 1 Insight to increase Yang; only 0 available."
        in no_insight_response.get_data(as_text=True)
    )
    assert _read_character_definition(app, "spend-matrix-crane") == final_payload
    assert _character_state_revision(app, "spend-matrix-crane") == final_revision

    xianxia = final_payload["xianxia"]
    assert xianxia["insight"] == {"available": 0, "spent": 5}
    assert xianxia["energies"] == {
        "jing": {"max": 3},
        "qi": {"max": 2},
        "shen": {"max": 1},
    }
    assert xianxia["yin_yang"] == {"yin_max": 2, "yang_max": 1}
    assert xianxia["durability"]["hp_max"] == 20
    assert xianxia["durability"]["stance_max"] == 20

    first_art = xianxia["martial_arts"][0]
    assert first_art["current_rank_key"] == "novice"
    assert first_art["current_rank"] == "Novice"
    assert first_art["rank_energy_maximum_increases"] == {
        "novice": {"jing": 1, "qi": 1, "shen": 0}
    }

    history = xianxia["advancement_history"]
    assert [event["action"] for event in history] == [
        "insight_counter_adjustment",
        "cultivation_energy_increase",
        "meditation_yin_yang_increase",
        "conditioning_hp_increase",
        "training_stance_increase",
        "martial_art_rank_advance",
    ]
    assert history[0]["insight_available_before"] == 0
    assert history[0]["insight_available_after"] == 5
    assert history[-1]["rank"] == "Novice"
    assert history[-1]["energy_maximum_increases"] == {
        "jing": 1,
        "qi": 1,
        "shen": 0,
    }

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "spend-matrix-crane")
        assert record is not None
        state = record.state_record.state
        assert state["vitals"]["current_hp"] == 6
        assert state["xianxia"]["vitals"]["current_hp"] == 6
        assert state["xianxia"]["vitals"]["current_stance"] == 4
        assert state["xianxia"]["energies"] == {
            "jing": {"current": 0},
            "qi": {"current": 1},
            "shen": {"current": 1},
        }
        assert state["xianxia"]["yin_yang"] == {
            "yin_current": 0,
            "yang_current": 1,
        }
