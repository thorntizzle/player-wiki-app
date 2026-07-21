from __future__ import annotations

import pytest

from tests.helpers.api_test_helpers import *
from tests.helpers.api_test_helpers import (
    _advanced_editor_values,
    _build_systems_import_archive,
    _build_unsafe_systems_import_archive,
    _configure_xianxia_campaign,
    _find_tracker_combatant,
    _import_systems_goblin,
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
    _valid_xianxia_create_data,
    _valid_xianxia_manual_import_data,
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
    _write_json,
)

def test_api_combat_endpoints_allow_dm_management_and_owner_player_vitals_updates(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-combat-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-combat-api")

    add_player = client.post(
        "/api/v1/campaigns/linden-pass/combat/player-combatants",
        headers=api_headers(dm_token),
        json={"character_slug": "arden-march", "turn_value": 18},
    )
    assert add_player.status_code == 200
    arden = _find_tracker_combatant(add_player.get_json(), character_slug="arden-march")
    assert arden is not None
    assert arden["turn_value"] == 18
    assert arden["state_revision"] is not None

    combatant_id = arden["id"]
    starting_revision = arden["state_revision"]

    owner_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}/vitals",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "current_hp": 35,
            "temp_hp": 4,
        },
    )
    assert owner_update.status_code == 200
    updated_arden = _find_tracker_combatant(owner_update.get_json(), character_slug="arden-march")
    assert updated_arden is not None
    assert updated_arden["current_hp"] == 35
    assert updated_arden["temp_hp"] == 4
    assert updated_arden["state_revision"] == starting_revision + 1

    blocked_ownerless = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}/vitals",
        headers=api_headers(player_token),
        json={
            "expected_revision": starting_revision + 1,
            "current_hp": 31,
            "temp_hp": 0,
        },
    )
    assert blocked_ownerless.status_code == 403

    add_npc = client.post(
        "/api/v1/campaigns/linden-pass/combat/npc-combatants",
        headers=api_headers(dm_token),
        json={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert add_npc.status_code == 200
    hound = _find_tracker_combatant(add_npc.get_json(), name="Clockwork Hound")
    assert hound is not None

    resources_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": hound["combatant_revision"],
            "has_action": True,
            "has_bonus_action": False,
            "has_reaction": False,
            "movement_remaining": 10,
        },
    )
    assert resources_update.status_code == 200
    refreshed_hound = _find_tracker_combatant(resources_update.get_json(), name="Clockwork Hound")
    assert refreshed_hound is not None
    assert refreshed_hound["movement_remaining"] == 10
    assert refreshed_hound["has_action"] is True
    assert refreshed_hound["has_bonus_action"] is False

    condition_update = client.post(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/conditions",
        headers=api_headers(dm_token),
        json={"name": "Restrained", "duration_text": "Until the end of round 2"},
    )
    assert condition_update.status_code == 200
    conditioned_hound = _find_tracker_combatant(condition_update.get_json(), name="Clockwork Hound")
    assert conditioned_hound is not None
    assert conditioned_hound["conditions"][0]["name"] == "Restrained"

    focused_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/vitals?combatant={hound['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": conditioned_hound["combatant_revision"],
            "current_hp": 19,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert focused_update.status_code == 200
    assert focused_update.get_json()["selected_combatant"]["id"] == hound["id"]
    assert focused_update.get_json()["selected_combatant"]["current_hp"] == 19

    live_state = client.get(
        "/api/v1/campaigns/linden-pass/combat/live-state",
        headers=api_headers(dm_token),
    )
    assert live_state.status_code == 200
    assert live_state.get_json()["tracker"]["combatant_count"] == 2


def test_api_combat_read_exposes_live_selection_and_fallback_links(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-read-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-combat-read-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-combat-read-api")

    add_player = client.post(
        "/api/v1/campaigns/linden-pass/combat/player-combatants",
        headers=api_headers(dm_token),
        json={"character_slug": "arden-march", "turn_value": 18},
    )
    assert add_player.status_code == 200
    arden = _find_tracker_combatant(add_player.get_json(), character_slug="arden-march")
    assert arden is not None

    add_npc = client.post(
        "/api/v1/campaigns/linden-pass/combat/npc-combatants",
        headers=api_headers(dm_token),
        json={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert add_npc.status_code == 200
    hound = _find_tracker_combatant(add_npc.get_json(), name="Clockwork Hound")
    assert hound is not None

    owner_read = client.get(
        f"/api/v1/campaigns/linden-pass/combat?combatant={hound['id']}",
        headers=api_headers(owner_token),
    )
    assert owner_read.status_code == 200
    payload = owner_read.get_json()

    assert payload["ok"] is True
    assert payload["changed"] is True
    assert payload["combat_system_supported"] is True
    assert isinstance(payload["live_revision"], int)
    assert isinstance(payload["live_view_token"], str)
    assert len(payload["live_view_token"]) == 12
    assert payload["selected_combatant"]["name"] == "Clockwork Hound"
    assert payload["selected_combatant_id"] == hound["id"]
    assert payload["selected_player_character"]["character_slug"] == "arden-march"
    combat_section_labels = [section["label"] for section in payload["selected_player_combat_sections"]]
    assert "Attacks" in combat_section_labels
    assert "Features" in combat_section_labels
    attacks_section = next(
        section for section in payload["selected_player_combat_sections"] if section["label"] == "Attacks"
    )
    assert [attack["name"] for attack in attacks_section["attacks"]] == [
        "Light Crossbow",
        "Quarterstaff",
        "Quarterstaff (two-handed)",
    ]
    assert payload["player_character_targets"] == [
        {
            "combatant_id": arden["id"],
            "character_slug": "arden-march",
            "name": "Arden March",
            "subtitle": "Sorcerer 5",
            "is_selected": True,
            "href": f"/campaigns/linden-pass/combat?combatant={arden['id']}",
            "flask_href": f"/campaigns/linden-pass/combat?combatant={arden['id']}",
        }
    ]
    assert payload["links"]["flask_combat_url"] == "/campaigns/linden-pass/combat"
    assert payload["links"]["flask_dm_status_url"] == ""
    assert payload["poll_settings"]["active_interval_ms"] == 500

    owner_character_list = client.get(
        "/api/v1/campaigns/linden-pass/characters",
        headers=api_headers(owner_token),
    )
    assert owner_character_list.status_code == 200
    assert [character["slug"] for character in owner_character_list.get_json()["characters"]] == ["arden-march"]

    owner_character_detail = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )
    assert owner_character_detail.status_code == 200

    unassigned_character_detail = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(player_token),
    )
    assert unassigned_character_detail.status_code == 403

    unchanged = client.get(
        f"/api/v1/campaigns/linden-pass/combat?combatant={hound['id']}",
        headers={
            **api_headers(owner_token),
            "X-Live-Revision": str(payload["live_revision"]),
            "X-Live-View-Token": payload["live_view_token"],
        },
    )
    assert unchanged.status_code == 200
    unchanged_payload = unchanged.get_json()
    assert unchanged_payload["changed"] is False
    assert unchanged_payload["live_revision"] == payload["live_revision"]
    assert unchanged_payload["live_view_token"] == payload["live_view_token"]
    assert set(unchanged_payload.keys()) == {"ok", "changed", "live_revision", "live_view_token"}

    live_read = client.get(
        f"/api/v1/campaigns/linden-pass/combat/live-state?combatant={hound['id']}",
        headers=api_headers(owner_token),
    )
    assert live_read.status_code == 200
    live_payload = live_read.get_json()
    assert live_payload["selected_combatant_id"] == hound["id"]
    assert live_payload["selected_combatant"]["name"] == "Clockwork Hound"

    unchanged_live = client.get(
        f"/api/v1/campaigns/linden-pass/combat/live-state?combatant={hound['id']}",
        headers={
            **api_headers(owner_token),
            "X-Live-Revision": str(live_payload["live_revision"]),
            "X-Live-View-Token": live_payload["live_view_token"],
        },
    )
    assert unchanged_live.status_code == 200
    assert unchanged_live.get_json() == {
        "ok": True,
        "changed": False,
        "live_revision": live_payload["live_revision"],
        "live_view_token": live_payload["live_view_token"],
    }

    dm_read = client.get("/api/v1/campaigns/linden-pass/combat", headers=api_headers(dm_token))
    assert dm_read.status_code == 200
    dm_payload = dm_read.get_json()
    dm_links = dm_payload["links"]
    assert dm_links["flask_dm_status_url"] == "/campaigns/linden-pass/combat/dm"
    assert dm_links["flask_dm_controls_url"] == "/campaigns/linden-pass/combat/dm?view=controls"
    assert dm_links["flask_status_url"] == "/campaigns/linden-pass/combat/dm"
    assert "Restrained" in dm_payload["combat_condition_options"]
    assert isinstance(dm_payload["available_character_choices"], list)
    assert isinstance(dm_payload["available_statblock_choices"], list)

    dm_live_read = client.get(
        "/api/v1/campaigns/linden-pass/combat/live-state",
        headers=api_headers(dm_token),
    )
    assert dm_live_read.status_code == 200
    dm_live_payload = dm_live_read.get_json()
    assert dm_payload["available_character_choices"]
    assert dm_live_payload["available_character_choices"] == []
    assert dm_live_payload["available_statblock_choices"] == []


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/campaigns/linden-pass/combat",
        "/api/v1/campaigns/linden-pass/combat/live-state",
    ),
)
def test_api_combat_reads_preserve_optional_identity_scope_access(
    client,
    app,
    users,
    path,
):
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-combat-read-access")
    outsider_token = issue_api_token(
        app,
        users["outsider"]["email"],
        label="outsider-combat-read-access",
    )

    missing = client.get(
        path.replace("linden-pass", "missing-campaign"),
        headers=api_headers(owner_token),
    )
    assert missing.status_code == 404

    anonymous = client.get(path, headers={"Accept": "application/json"})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    inaccessible = client.get(path, headers=api_headers(outsider_token))
    assert inaccessible.status_code == 403
    assert inaccessible.get_json()["error"]["code"] == "forbidden"

    accessible = client.get(path, headers=api_headers(owner_token))
    assert accessible.status_code == 200


def test_api_combat_reads_build_payload_before_matching_live_header_short_circuit(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-read-fault")
    paths = (
        "/api/v1/campaigns/linden-pass/combat",
        "/api/v1/campaigns/linden-pass/combat/live-state",
    )
    matching_headers = []
    for path in paths:
        response = client.get(path, headers=api_headers(dm_token))
        assert response.status_code == 200
        payload = response.get_json()
        matching_headers.append(
            {
                **api_headers(dm_token),
                "X-Live-Revision": str(payload["live_revision"]),
                "X-Live-View-Token": payload["live_view_token"],
            }
        )

    def fail_payload_construction(_campaign_slug):
        raise RuntimeError("combat payload construction fault")

    monkeypatch.setattr(
        app.extensions["campaign_combat_service"],
        "get_tracker",
        fail_payload_construction,
    )

    for path, headers in zip(paths, matching_headers, strict=True):
        with pytest.raises(RuntimeError, match="combat payload construction fault"):
            client.get(path, headers=headers)


def test_browser_and_api_preserve_distinct_condition_option_order_and_dedup(
    client, app, users, sign_in
):
    with app.app_context():
        service = app.extensions["campaign_dm_content_service"]
        for name in ("Aardvark Hex", "blinded", "Zephyr Hex"):
            service.create_condition_definition(
                "linden-pass",
                name=name,
                created_by_user_id=users["dm"]["id"],
            )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    browser_response = client.get("/campaigns/linden-pass/combat/dm")
    assert browser_response.status_code == 200
    browser_html = browser_response.get_data(as_text=True)
    assert browser_html.count('<option value="Blinded"></option>') == 1
    assert '<option value="blinded"></option>' not in browser_html
    assert browser_html.index('<option value="Blinded"></option>') < browser_html.index(
        '<option value="Aardvark Hex"></option>'
    )
    assert browser_html.index('<option value="Aardvark Hex"></option>') < browser_html.index(
        '<option value="Zephyr Hex"></option>'
    )

    dm_token = issue_api_token(app, users["dm"]["email"], label="condition-order-api")
    api_response = client.get(
        "/api/v1/campaigns/linden-pass/combat",
        headers=api_headers(dm_token),
    )
    assert api_response.status_code == 200
    api_options = api_response.get_json()["combat_condition_options"]
    assert api_options == sorted(set(api_options))
    assert "Blinded" in api_options
    assert "blinded" in api_options
    assert api_options.index("Aardvark Hex") < api_options.index("Blinded")
    assert api_options.index("Blinded") < api_options.index("blinded")


def test_api_combat_read_reports_unsupported_system_without_live_poll_targets(client, app, users):
    _configure_xianxia_campaign(app)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-xianxia-api")

    response = client.get("/api/v1/campaigns/linden-pass/combat", headers=api_headers(dm_token))
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["combat_system_supported"] is False
    assert payload["live_revision"] == 0
    assert payload["tracker"]["combatant_count"] == 0
    assert payload["selected_combatant"] is None
    assert payload["selected_player_character"] is None
    assert payload["player_character_targets"] == []
    assert payload["links"]["flask_combat_url"] == "/campaigns/linden-pass/combat"
    assert payload["links"]["flask_campaign_url"] == "/campaigns/linden-pass"
    assert payload["links"]["flask_characters_url"] == "/campaigns/linden-pass/characters"
    assert payload["links"]["flask_session_url"] == "/campaigns/linden-pass/session"

    live_response = client.get(
        "/api/v1/campaigns/linden-pass/combat/live-state",
        headers=api_headers(dm_token),
    )
    assert live_response.status_code == 200
    live_payload = live_response.get_json()
    assert live_payload["combat_system_supported"] is False
    assert live_payload["live_revision"] == 0
    assert live_payload["tracker"]["combatant_count"] == 0
    assert live_payload["player_character_targets"] == []
    assert live_payload["available_character_choices"] == []
    assert live_payload["available_statblock_choices"] == []


def test_api_combat_statblock_seed_uses_dex_modifier_for_tie_breaker(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-statblock-api")
    with app.app_context():
        statblock = app.extensions["campaign_dm_content_service"].create_statblock(
            "linden-pass",
            filename="alert-guard.md",
            data_blob=b"""---
title: Alert Guard
armor_class: 14
hp: 24
speed: 30 ft.
initiative_bonus: 7
---

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 10 (+0)  WIS 10 (+0)  CHA 10 (+0)

## Actions

### Spear

+4 to hit, 5 piercing damage.
""",
            created_by_user_id=users["dm"]["id"],
        )

    response = client.post(
        "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
        headers=api_headers(dm_token),
        json={"statblock_id": statblock.id},
    )

    assert response.status_code == 200
    combatant = _find_tracker_combatant(response.get_json(), name="Alert Guard")
    assert combatant is not None
    assert combatant["turn_value"] == 7
    assert combatant["initiative_bonus_label"] == "+7"
    assert combatant["dexterity_modifier"] == 2
    assert combatant["dexterity_modifier_label"] == "+2"


def test_api_combat_statblock_npc_resources_seed_patch_and_gate_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-npc-resources-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-combat-npc-resources-api")
    with app.app_context():
        statblock = app.extensions["campaign_dm_content_service"].create_statblock(
            "linden-pass",
            filename="hex-adept.md",
            data_blob=b"""---
title: Hex Adept
armor_class: 13
hp: 33
speed: 30 ft.
initiative_bonus: 2
---

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 10 (+0)  WIS 10 (+0)  CHA 16 (+3)

## Traits

### Innate Spellcasting

At will: detect magic, mage hand.
3/day each: misty step, charm person.
1/day: dimension door.

### Legendary Resistance (3/Day)

If the adept fails a saving throw, it can choose to succeed instead.

## Actions

### Fire Breath (Recharge 5-6)

The adept exhales fire in a 15-foot cone.
""",
            created_by_user_id=users["dm"]["id"],
        )

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
        headers=api_headers(dm_token),
        json={"statblock_id": statblock.id},
    )
    assert add_response.status_code == 200
    adept = _find_tracker_combatant(add_response.get_json(), name="Hex Adept")
    assert adept is not None
    counters = {counter["label"].lower(): counter for counter in adept["npc_resource_counters"]}
    assert counters["misty step"]["current_value"] == 3
    assert counters["misty step"]["max_value"] == 3
    assert counters["misty step"]["reset_label"] == "Per day"
    assert counters["misty step"]["can_edit"] is True
    assert counters["charm person"]["max_value"] == 3
    assert counters["dimension door"]["max_value"] == 1
    assert counters["legendary resistance"]["max_value"] == 3
    notes = {(note["label"], note["note"]) for note in adept["npc_resource_notes"]}
    assert ("At-will spellcasting", "detect magic, mage hand") in notes
    assert ("Fire Breath", "Recharge 5-6") in notes

    player_blocked = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{adept['id']}/npc-resources",
        headers=api_headers(player_token),
        json={
            "expected_combatant_revision": adept["combatant_revision"],
            "counters": [{"resource_key": counters["misty step"]["resource_key"], "current_value": 2}],
        },
    )
    assert player_blocked.status_code == 403

    update_response = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{adept['id']}/npc-resources?combatant={adept['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": adept["combatant_revision"],
            "counters": [{"resource_key": counters["misty step"]["resource_key"], "current_value": 1}],
        },
    )
    assert update_response.status_code == 200
    updated_adept = update_response.get_json()["selected_combatant"]
    updated_counters = {counter["label"].lower(): counter for counter in updated_adept["npc_resource_counters"]}
    assert updated_counters["misty step"]["current_value"] == 1
    assert updated_adept["combatant_revision"] == adept["combatant_revision"] + 1

    stale_response = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{adept['id']}/npc-resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": adept["combatant_revision"],
            "counters": [{"resource_key": counters["misty step"]["resource_key"], "current_value": 0}],
        },
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_combat_resource_update_rejects_stale_combatant_revision(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-conflict-api")

    add_npc = client.post(
        "/api/v1/campaigns/linden-pass/combat/npc-combatants",
        headers=api_headers(dm_token),
        json={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert add_npc.status_code == 200
    hound = _find_tracker_combatant(add_npc.get_json(), name="Clockwork Hound")
    assert hound is not None

    first_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": hound["combatant_revision"],
            "has_action": True,
            "has_bonus_action": True,
            "has_reaction": True,
            "movement_remaining": 10,
        },
    )
    assert first_update.status_code == 200

    stale_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": hound["combatant_revision"],
            "has_action": True,
            "has_bonus_action": False,
            "has_reaction": False,
            "movement_remaining": 5,
        },
    )
    assert stale_update.status_code == 409
    assert stale_update.get_json()["error"]["code"] == "state_conflict"
    assert stale_update.get_json()["error"]["message"] == (
        "This combatant changed in another combat view. Refresh and try again."
    )

    live_state = client.get("/api/v1/campaigns/linden-pass/combat/live-state", headers=api_headers(dm_token))
    assert live_state.status_code == 200
    refreshed_hound = _find_tracker_combatant(live_state.get_json(), name="Clockwork Hound")
    assert refreshed_hound is not None
    assert refreshed_hound["movement_remaining"] == 10
    assert refreshed_hound["has_bonus_action"] is True
    assert refreshed_hound["has_reaction"] is True


def test_api_combat_systems_monster_search_and_add_use_imported_entries(client, app, users, tmp_path):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-systems-api")

    search_response = client.get(
        "/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob",
        headers=api_headers(dm_token),
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching monster."
    assert search_payload["results"][0]["entry_key"] == goblin_entry_key
    assert search_payload["results"][0]["title"] == "Goblin"

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/combat/systems-monsters",
        headers=api_headers(dm_token),
        json={"entry_key": goblin_entry_key},
    )
    assert add_response.status_code == 200
    goblin = _find_tracker_combatant(add_response.get_json(), name="Goblin")
    assert goblin is not None
    assert goblin["turn_value"] == 2
    assert goblin["current_hp"] == 7
    assert goblin["movement_total"] == 30


def test_api_combat_systems_monster_resources_seed_from_limited_use_traits(client, app, users, tmp_path):
    data_root = tmp_path / "api-systems-npc-resources-source"
    _write_json(
        data_root / "data/bestiary/bestiary-mm.json",
        {
            "monster": [
                {
                    "name": "Hex Adept",
                    "source": "MM",
                    "page": 999,
                    "size": ["M"],
                    "type": {"type": "humanoid"},
                    "alignment": ["N"],
                    "ac": [{"ac": 13}],
                    "hp": {"average": 33, "formula": "6d8 + 6"},
                    "speed": {"walk": 30},
                    "str": 10,
                    "dex": 14,
                    "con": 12,
                    "int": 10,
                    "wis": 10,
                    "cha": 16,
                    "trait": [
                        {
                            "name": "Innate Spellcasting",
                            "entries": [
                                "At will: {@spell detect magic}, {@spell mage hand}.",
                                "3/day each: {@spell misty step}, {@spell charm person}.",
                            ],
                        },
                        {
                            "name": "Legendary Resistance (3/Day)",
                            "entries": ["If the adept fails a saving throw, it can choose to succeed instead."],
                        },
                    ],
                    "action": [
                        {
                            "name": "Arcane Burst (Recharge 5-6)",
                            "entries": ["The adept releases stored force."],
                        }
                    ],
                }
            ]
        },
    )
    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["monster"])
        entry = next(
            item
            for item in app.extensions["systems_service"].list_monster_entries_for_campaign("linden-pass")
            if item.title == "Hex Adept"
        )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-systems-npc-resources-api")

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/combat/systems-monsters",
        headers=api_headers(dm_token),
        json={"entry_key": entry.entry_key},
    )

    assert add_response.status_code == 200
    adept = _find_tracker_combatant(add_response.get_json(), name="Hex Adept")
    assert adept is not None
    counters = {counter["label"].lower(): counter for counter in adept["npc_resource_counters"]}
    assert counters["misty step"]["max_value"] == 3
    assert counters["charm person"]["current_value"] == 3
    assert counters["legendary resistance"]["source_label"] == "Systems MM"
    notes = {(note["label"], note["note"]) for note in adept["npc_resource_notes"]}
    assert ("At-will spellcasting", "detect magic, mage hand") in notes
    assert ("Arcane Burst", "Recharge 5-6") in notes
