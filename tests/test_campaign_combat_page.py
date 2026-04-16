from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import player_wiki.campaign_combat_service as campaign_combat_service_module
from player_wiki.app import create_app
from player_wiki.config import Config
from player_wiki.db import init_database
from player_wiki.systems_importer import Dnd5eSystemsImporter
from tests.sample_data import TEST_CAMPAIGN_SLUG, build_test_campaigns_dir


def _async_headers():
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def _live_poll_headers(revision: int, view_token: str):
    headers = _async_headers()
    headers["X-Live-Revision"] = str(revision)
    headers["X-Live-View-Token"] = view_token
    return headers


def _assert_live_diagnostics_headers(response):
    assert response.headers["X-Live-Query-Count"]
    assert response.headers["X-Live-Query-Time-Ms"]
    assert response.headers["X-Live-Request-Time-Ms"]
    assert "db;dur=" in response.headers["Server-Timing"]
    assert "total;dur=" in response.headers["Server-Timing"]


def _get_tracker(app):
    with app.app_context():
        return app.extensions["campaign_combat_service"].get_tracker("linden-pass")


def _list_combatants(app):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_combatants("linden-pass")


def _find_combatant(app, *, name: str | None = None, character_slug: str | None = None):
    for combatant in _list_combatants(app):
        if name is not None and combatant.display_name == name:
            return combatant
        if character_slug is not None and combatant.character_slug == character_slug:
            return combatant
    return None


def _list_conditions(app, combatant_id: int):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_conditions_by_combatant("linden-pass").get(
            combatant_id,
            [],
        )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _import_systems_goblin(app, tmp_path) -> str:
    data_root = tmp_path / "combat-systems-dnd5e-source"
    _write_json(
        data_root / "data/bestiary/bestiary-mm.json",
        {
            "monster": [
                {
                    "name": "Goblin",
                    "source": "MM",
                    "page": 166,
                    "size": ["S"],
                    "type": {"type": "humanoid", "tags": ["goblinoid"]},
                    "alignment": ["N", "E"],
                    "ac": [{"ac": 15, "from": ["leather armor", "shield"]}],
                    "hp": {"average": 7, "formula": "2d6"},
                    "speed": {"walk": 30},
                    "str": 8,
                    "dex": 14,
                    "con": 10,
                    "int": 10,
                    "wis": 8,
                    "cha": 8,
                    "action": [
                        {
                            "name": "Scimitar",
                            "entries": ["{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."]
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
        entries = app.extensions["systems_service"].list_monster_entries_for_campaign("linden-pass")
        goblin = next(entry for entry in entries if entry.title == "Goblin")
        return goblin.entry_key


def _create_dm_statblock(
    app,
    *,
    created_by_user_id: int | None = None,
    markdown_text: str | None = None,
    filename: str = "brass-hound.md",
):
    markdown_text = markdown_text or """---
title: Brass Hound
armor_class: 15
hp: 30
speed: 40 ft.
initiative_bonus: 2
---

## Bite

+6 to hit, 8 piercing damage.
"""
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].create_statblock(
            TEST_CAMPAIGN_SLUG,
            filename=filename,
            data_blob=markdown_text.encode("utf-8"),
            created_by_user_id=created_by_user_id,
        )


def test_campaign_member_can_open_combat_page_and_campaign_links_to_it(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    combat_page = client.get("/campaigns/linden-pass/combat")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "Combat" in campaign_html
    assert '/campaigns/linden-pass/combat' in campaign_html

    assert combat_page.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    assert "Combat tracker" in combat_html
    assert "Turn order" in combat_html
    assert "Current limits" in combat_html
    assert "/campaigns/linden-pass/combat/character" not in combat_html
    assert 'data-combat-live-root' in combat_html
    assert 'data-loading="0"' in combat_html
    assert "window.__playerWikiLiveUiTools" in combat_html
    assert "uiStateTools.captureViewportAnchor(liveRoot)" in combat_html
    assert "/campaigns/linden-pass/combat/dm" not in combat_html
    assert "/campaigns/linden-pass/combat/status" not in combat_html
    assert "Add player character" not in combat_html
    assert "Add NPC from Systems" not in combat_html
    assert "Add custom NPC combatant" not in combat_html
    assert 'data-live-active-interval-ms="500"' in combat_html
    assert 'data-live-idle-interval-ms="3000"' in combat_html


def test_dm_and_admin_can_open_dm_only_combat_pages_and_players_cannot(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/combat/dm")
    status_page = client.get("/campaigns/linden-pass/combat/status")

    assert dm_page.status_code == 200
    assert status_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    status_html = status_page.get_data(as_text=True)
    assert "Encounter controls" in dm_html
    assert "Combat" in dm_html
    assert "/campaigns/linden-pass/combat/character" not in dm_html
    assert "Encounter status" in dm_html
    assert "Encounter controls" in dm_html
    assert "Formerly DM page. Existing /combat/dm links and bookmarks still work during the transition." in dm_html
    assert "Add player character" in dm_html
    assert "Add NPC from Systems" in dm_html
    assert "Add custom NPC combatant" in dm_html
    assert 'data-loading="0"' in dm_html
    assert "captureSystemsMonsterSearchState" in dm_html
    assert 'liveRoot.dataset.loading = "1";' in dm_html
    assert "const findMatchingForm = (root, descriptor) =>" in dm_html
    assert 'focusState.form = describeForm(root, form);' in dm_html
    assert "const fieldRoot = findMatchingForm(root, focusState.form) || root;" in dm_html
    assert "window.history.replaceState(null, \"\", nextPageUrl);" in dm_html
    assert "buildLiveHeaders({ allowShortCircuit: false })" in dm_html
    assert "window.location.assign(nextUrl);" not in dm_html
    assert "Encounter status (formerly Status)" in status_html
    assert "Formerly Status. Existing /combat/status links and bookmarks still work during the transition." in status_html
    assert 'data-live-active-interval-ms="500"' in dm_html
    assert 'data-live-idle-interval-ms="3000"' in dm_html
    assert 'data-live-active-interval-ms="1500"' in status_html
    assert 'data-live-idle-interval-ms="4000"' in status_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    player_dm_page = client.get("/campaigns/linden-pass/combat/dm")
    player_status_page = client.get("/campaigns/linden-pass/combat/status")
    assert player_dm_page.status_code == 403
    assert player_status_page.status_code == 403

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["admin"]["email"], users["admin"]["password"])

    admin_status_page = client.get("/campaigns/linden-pass/combat/status")
    assert admin_status_page.status_code == 200
    status_html = admin_status_page.get_data(as_text=True)
    assert "/campaigns/linden-pass/combat/status" in status_html
    assert 'data-combat-status-live-root' in status_html
    assert 'data-loading="0"' in status_html
    assert "window.__playerWikiCombatWorkspace" in status_html
    assert "window.__playerWikiLiveUiTools" in status_html
    assert "uiStateTools.captureViewportAnchor(liveRoot)" in status_html


def test_combat_live_state_and_async_updates_return_partials(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    add_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert add_player.status_code == 200
    add_player_payload = add_player.get_json()
    assert add_player_payload["ok"] is True
    assert "Player character added to the combat tracker." in add_player_payload["flash_html"]
    assert "Arden March" in add_player_payload["tracker_html"]
    assert "controls_html" not in add_player_payload

    glenn = _find_combatant(app, character_slug="arden-march")
    assert glenn is not None

    set_current = client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/set-current",
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert set_current.status_code == 200
    set_current_payload = set_current.get_json()
    assert set_current_payload["ok"] is True
    assert "Current turn updated." in set_current_payload["flash_html"]
    assert "Current turn" in set_current_payload["summary_html"]
    assert "Arden March" in set_current_payload["summary_html"]

    live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )

    assert live_state.status_code == 200
    live_payload = live_state.get_json()
    assert "Arden March" in live_payload["tracker_html"]
    assert "Current turn" in live_payload["summary_html"]
    assert live_payload["combat_state_token"]


def test_combat_live_state_short_circuits_when_revision_and_view_token_match(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    initial_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_live_state.headers["X-Live-State-Changed"] == "true"
    assert initial_live_state.headers["X-Live-Revision"] == str(initial_payload["live_revision"])
    assert initial_live_state.headers["X-Live-Payload-Bytes"]
    _assert_live_diagnostics_headers(initial_live_state)

    unchanged_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(unchanged_live_state)

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )

    refreshed_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert refreshed_live_state.status_code == 200
    refreshed_payload = refreshed_live_state.get_json()
    assert refreshed_payload["changed"] is True
    assert refreshed_payload["live_revision"] > initial_payload["live_revision"]
    assert "Current turn" in refreshed_payload["summary_html"]
    assert refreshed_live_state.headers["X-Live-State-Changed"] == "true"
    _assert_live_diagnostics_headers(refreshed_live_state)


def test_dm_can_add_systems_monster_to_combat_tracker(app, client, sign_in, users, tmp_path):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat/dm")
    assert combat_page.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    assert "Add NPC from Systems" in combat_html
    assert "Type at least 2 letters to search the Systems monster list." in combat_html
    assert "Goblin - MM" not in combat_html

    search_response = client.get(
        "/campaigns/linden-pass/combat/systems-monsters/search?q=gob",
        headers=_async_headers(),
    )

    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching monster."
    assert len(search_payload["results"]) == 1
    assert search_payload["results"][0]["entry_key"] == goblin_entry_key
    assert search_payload["results"][0]["title"] == "Goblin"
    assert search_payload["results"][0]["source_id"] == "MM"
    assert "HP 7" in search_payload["results"][0]["subtitle"]
    assert search_payload["results"][0]["initiative_bonus"] == "+2"

    response = client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "NPC combatant added from Systems (MM)." in payload["flash_html"]
    assert "Goblin" in payload["tracker_html"]

    combatant = _find_combatant(app, name="Goblin")
    assert combatant is not None
    assert combatant.turn_value == 2
    assert combatant.initiative_bonus == 2
    assert combatant.current_hp == 7
    assert combatant.max_hp == 7
    assert combatant.movement_total == 30


def test_dm_combat_dm_page_does_not_eager_load_system_monster_choices(
    app, client, sign_in, users, tmp_path, monkeypatch
):
    _import_systems_goblin(app, tmp_path)

    with app.app_context():
        systems_service = app.extensions["systems_service"]

    def fail_load(*args, **kwargs):
        raise AssertionError("combat page should not eagerly load Systems monster choices")

    monkeypatch.setattr(systems_service, "list_monster_entries_for_campaign", fail_load)
    monkeypatch.setattr(systems_service, "search_monster_entries_for_campaign", fail_load)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/combat/dm")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Add NPC from Systems" in body
    assert "Search monsters" in body
    assert "Goblin - MM" not in body


def test_dm_page_async_mutations_return_controls_partial_and_non_async_redirects_back_to_dm_page(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    async_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18, "combat_view": "dm"},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert async_response.status_code == 200
    async_payload = async_response.get_json()
    assert async_payload["ok"] is True
    assert "Arden March" in async_payload["tracker_html"]
    assert "Add player character" in async_payload["controls_html"]

    redirect_response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
            "combat_view": "dm",
        },
        follow_redirects=False,
    )

    assert redirect_response.status_code == 302
    assert redirect_response.headers["Location"].endswith("/campaigns/linden-pass/combat/dm#combat-tracker")


def test_dm_pages_split_tactical_status_edits_from_control_authority_actions(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    status_response = client.get(f"/campaigns/linden-pass/combat/status?combatant={hound.id}")
    controls_response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")

    assert status_response.status_code == 200
    assert controls_response.status_code == 200

    status_body = status_response.get_data(as_text=True)
    controls_body = controls_response.get_data(as_text=True)

    assert "Status edits" in status_body
    assert 'name="combat_view" value="status"' in status_body
    assert "Save HP" in status_body
    assert "Save temp HP" in status_body
    assert "Save movement" in status_body
    assert "Save action economy" in status_body
    assert "Set current turn" in status_body
    assert "combat-status-mutation" in status_body
    assert "hasFocusedFormControl" in status_body

    assert "Selected combatant authority" in controls_body
    assert "Open Encounter status" in controls_body
    assert "Save turn value" in controls_body
    assert "Show NPC detail to players" in controls_body
    assert "Save NPC structure" in controls_body
    assert "Remove combatant" in controls_body
    assert "Save HP" not in controls_body
    assert "Save temp HP" not in controls_body
    assert "Save movement" not in controls_body
    assert "Save action economy" not in controls_body


def test_status_page_async_mutations_return_status_partials_and_keep_selected_target(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/resources",
        data={
            "combat_view": "status",
            "combatant": hound.id,
            "has_action": "1",
            "movement_remaining": 10,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == hound.id
    assert "Combat resources updated." in payload["flash_html"]
    assert "Status edits" in payload["detail_html"]
    assert 'name="combat_view" value="status"' in payload["detail_html"]
    assert "Save movement" in payload["detail_html"]
    assert "Turn order" in payload["board_html"]


def test_dm_can_add_player_character_and_npc_combatants_and_turn_order_sorts_high_to_low(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    player_add = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    npc_add = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    assert player_add.status_code == 302
    assert npc_add.status_code == 302

    combatants = _list_combatants(app)
    assert [combatant.display_name for combatant in combatants] == [
        "Arden March",
        "Clockwork Hound",
    ]
    assert combatants[0].turn_value == 18
    assert combatants[1].current_hp == 22
    assert combatants[1].movement_total == 40


def test_dm_can_set_current_turn_and_advance_turn_refreshing_resources(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    glenn = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert glenn is not None
    assert hound is not None

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/resources",
        data={
            "movement_remaining": 0,
        },
        follow_redirects=False,
    )

    updated_glenn = _find_combatant(app, character_slug="arden-march")
    assert updated_glenn is not None
    assert updated_glenn.has_action is False
    assert updated_glenn.has_bonus_action is False
    assert updated_glenn.has_reaction is False
    assert updated_glenn.movement_remaining == 0

    set_current = client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/set-current",
        follow_redirects=False,
    )
    assert set_current.status_code == 302

    refreshed_glenn = _find_combatant(app, character_slug="arden-march")
    tracker = _get_tracker(app)
    assert refreshed_glenn is not None
    assert refreshed_glenn.has_action is True
    assert refreshed_glenn.has_bonus_action is True
    assert refreshed_glenn.has_reaction is True
    assert refreshed_glenn.movement_remaining == refreshed_glenn.movement_total
    assert tracker.current_combatant_id == glenn.id
    assert tracker.round_number == 1

    first_advance = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        follow_redirects=False,
    )
    assert first_advance.status_code == 302
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id == hound.id
    assert tracker.round_number == 1

    second_advance = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        follow_redirects=False,
    )
    assert second_advance.status_code == 302
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id == glenn.id
    assert tracker.round_number == 2


def test_owner_player_can_update_own_pc_vitals_from_combat_tracker(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    combatant = _find_combatant(app, character_slug="arden-march")
    assert record is not None
    assert combatant is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": 35,
            "temp_hp": 4,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    updated_record = get_character("arden-march")
    updated_combatant = _find_combatant(app, character_slug="arden-march")
    assert updated_record.state_record.state["vitals"]["current_hp"] == 35
    assert updated_record.state_record.state["vitals"]["temp_hp"] == 4
    assert updated_combatant is not None
    assert updated_combatant.current_hp == 35
    assert updated_combatant.temp_hp == 4


def test_owner_player_sees_inline_edit_controls_on_owned_tracked_pc(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-combat-inline-autosubmit' in body
    assert 'aria-label="Current HP for Arden March"' in body
    assert 'aria-label="Temp HP for Arden March"' in body
    assert 'aria-label="Remaining movement for Arden March"' in body
    assert "Save vitals" not in body
    assert "Save resources" not in body


def test_owner_player_combat_page_uses_character_workspace_layout(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Combat workspace" in body
    assert "Combat sections" in body
    assert "Turn order" in body
    assert "Actions" in body
    assert "Bonus Actions" in body
    assert "Reactions" in body
    assert "Abilities and Skills" in body
    assert "Your workspace" in body
    assert "Current limits" not in body
    assert "Encounter context" not in body


def test_owner_player_combat_workspace_links_back_to_session_character_when_session_is_active(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Session relationship" in body
    assert "Keep Combat for" in body
    assert "Keep Session for" in body
    assert "Rests, inventory quantities, currency, and player notes" in body
    assert '/campaigns/linden-pass/session/character?character=arden-march' in body
    assert '>Open Session Character<' in body
    assert '>Open Session<' in body
    assert "The Session Character link keeps this same sheet selected from the Session feature." in body


def test_owner_player_can_open_combat_character_page_for_assigned_tracked_pc(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat")
    response = client.get("/campaigns/linden-pass/combat/character")

    assert combat_page.status_code == 200
    assert response.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    body = response.get_data(as_text=True)
    assert f"/campaigns/linden-pass/combat/character?combatant={combatant.id}" in combat_html
    assert "Combat Character" in body
    assert "Arden March" in body
    assert "Combat snapshot" in body
    assert "Tracked player characters" in body
    assert "Open full sheet" not in body
    assert 'data-live-active-interval-ms="500"' in body
    assert 'data-live-idle-interval-ms="3000"' in body


def test_dm_combat_character_route_redirects_to_status_for_selected_target(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/character?combatant={combatant.id}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/campaigns/linden-pass/combat/status?combatant={combatant.id}"
    )


def test_player_without_owned_tracked_pc_gets_combat_character_empty_state(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat")
    response = client.get("/campaigns/linden-pass/combat/character")

    assert combat_page.status_code == 200
    assert response.status_code == 200
    assert "/campaigns/linden-pass/combat/character" not in combat_page.get_data(as_text=True)
    body = response.get_data(as_text=True)
    assert "No tracked player character available" in body


def test_unassigned_player_cannot_open_other_pc_combat_character_page(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/combat/character?character=arden-march")

    assert response.status_code == 403


def test_unassigned_player_cannot_update_other_pc_combat_vitals(app, client, sign_in, users, get_character):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "selene-brook", "turn_value": 14},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    record = get_character("selene-brook")
    combatant = _find_combatant(app, character_slug="selene-brook")
    assert record is not None
    assert combatant is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": 40,
            "temp_hp": 0,
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_owner_player_can_update_own_pc_resources_from_combat_views(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    tracker_resources = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={"movement_remaining": 5},
        follow_redirects=False,
    )

    assert tracker_resources.status_code == 302
    updated_combatant = _find_combatant(app, character_slug="arden-march")
    assert updated_combatant is not None
    assert updated_combatant.has_action is False
    assert updated_combatant.has_bonus_action is False
    assert updated_combatant.has_reaction is False
    assert updated_combatant.movement_remaining == 5

    record = get_character("arden-march")
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/resources/sorcery-points",
        data={"expected_revision": record.state_record.revision, "current": 3},
        follow_redirects=False,
    )

    assert resource_response.status_code == 302
    record = get_character("arden-march")
    resources = {item["id"]: item for item in record.state_record.state["resources"]}
    assert resources["sorcery-points"]["current"] == 3

    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 2},
        follow_redirects=False,
    )

    assert spell_response.status_code == 302
    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 2


def test_owner_player_combat_workspace_resource_mutations_redirect_back_to_combat(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/resources/sorcery-points",
        data={
            "expected_revision": record.state_record.revision,
            "current": 3,
            "combat_view": "combat",
        },
        follow_redirects=False,
    )

    assert resource_response.status_code == 302
    assert resource_response.headers["Location"].endswith(
        f"/campaigns/linden-pass/combat?combatant={combatant.id}#combat-character-resources"
    )

    record = get_character("arden-march")
    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={
            "expected_revision": record.state_record.revision,
            "used": 2,
            "combat_view": "combat",
        },
        follow_redirects=False,
    )

    assert spell_response.status_code == 302
    assert spell_response.headers["Location"].endswith(
        f"/campaigns/linden-pass/combat?combatant={combatant.id}#combat-character-spell-slots"
    )


def test_unassigned_player_cannot_update_other_pc_combat_resources_or_spell_slots(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    record = get_character("arden-march")
    assert combatant is not None
    assert record is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    tracker_resources = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={"movement_remaining": 5},
        follow_redirects=False,
    )
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/resources/sorcery-points",
        data={"expected_revision": record.state_record.revision, "current": 3},
        follow_redirects=False,
    )
    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 2},
        follow_redirects=False,
    )

    assert tracker_resources.status_code == 403
    assert resource_response.status_code == 403
    assert spell_response.status_code == 403


def test_dm_can_manage_npc_vitals_resources_and_conditions(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None

    vitals = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/vitals",
        data={"current_hp": 15, "max_hp": 22, "temp_hp": 3, "movement_total": 50},
        follow_redirects=False,
    )
    resources = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={
            "has_action": "1",
            "movement_remaining": 10,
        },
        follow_redirects=False,
    )
    add_condition = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/conditions",
        data={"condition_name": "Blinded", "duration_text": "Until end of next turn"},
        follow_redirects=False,
    )

    assert vitals.status_code == 302
    assert resources.status_code == 302
    assert add_condition.status_code == 302

    updated_combatant = _find_combatant(app, name="Clockwork Hound")
    conditions = _list_conditions(app, combatant.id)
    assert updated_combatant is not None
    assert updated_combatant.current_hp == 15
    assert updated_combatant.temp_hp == 3
    assert updated_combatant.movement_total == 50
    assert updated_combatant.has_action is True
    assert updated_combatant.has_bonus_action is False
    assert updated_combatant.has_reaction is False
    assert updated_combatant.movement_remaining == 10
    assert len(conditions) == 1
    assert conditions[0].name == "Blinded"

    delete_condition = client.post(
        f"/campaigns/linden-pass/combat/conditions/{conditions[0].id}/delete",
        follow_redirects=False,
    )
    assert delete_condition.status_code == 302
    assert _list_conditions(app, combatant.id) == []


def test_npc_detail_is_hidden_from_players_by_default_and_dm_can_reveal_per_npc(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Brass Sentry",
            "turn_value": 8,
            "current_hp": 18,
            "max_hp": 18,
            "temp_hp": 0,
            "movement_total": 30,
        },
        follow_redirects=False,
    )

    hound = _find_combatant(app, name="Clockwork Hound")
    sentry = _find_combatant(app, name="Brass Sentry")
    assert hound is not None
    assert sentry is not None
    assert hound.player_detail_visible is False
    assert sentry.player_detail_visible is False

    toggle = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/player-detail-visibility",
        data={"player_detail_visible": "1", "combat_view": "dm"},
        follow_redirects=False,
    )

    assert toggle.status_code == 302
    updated_hound = _find_combatant(app, name="Clockwork Hound")
    updated_sentry = _find_combatant(app, name="Brass Sentry")
    assert updated_hound is not None
    assert updated_sentry is not None
    assert updated_hound.player_detail_visible is True
    assert updated_sentry.player_detail_visible is False

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Clockwork Hound" in body
    assert "Brass Sentry" in body
    assert "22 / 22" in body
    assert "40 / 40" in body
    assert "18 / 18" not in body
    assert "30 / 30" not in body
    assert "Detailed NPC vitals and action economy are hidden from player view." in body


def test_player_cannot_toggle_npc_player_detail_visibility(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={"player_detail_visible": "1", "combat_view": "dm"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    refreshed = _find_combatant(app, name="Clockwork Hound")
    assert refreshed is not None
    assert refreshed.player_detail_visible is False


def test_dm_can_clear_combat_tracker(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    glenn = _find_combatant(app, character_slug="arden-march")
    assert glenn is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/set-current",
        follow_redirects=False,
    )

    response = client.post(
        "/campaigns/linden-pass/combat/clear",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _list_combatants(app) == []
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id is None
    assert tracker.round_number == 1


def test_player_cannot_clear_combat_tracker(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/campaigns/linden-pass/combat/clear",
        follow_redirects=False,
    )

    assert response.status_code == 403
    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None


def test_init_db_backfills_legacy_combatant_source_identity(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)

    db_path = tmp_path / "legacy-player-wiki.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE campaign_combatants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_slug TEXT NOT NULL,
            combatant_type TEXT NOT NULL,
            character_slug TEXT,
            display_name TEXT NOT NULL,
            turn_value INTEGER NOT NULL DEFAULT 0,
            initiative_bonus INTEGER NOT NULL DEFAULT 0,
            current_hp INTEGER NOT NULL DEFAULT 0,
            max_hp INTEGER NOT NULL DEFAULT 0,
            temp_hp INTEGER NOT NULL DEFAULT 0,
            movement_total INTEGER NOT NULL DEFAULT 0,
            movement_remaining INTEGER NOT NULL DEFAULT 0,
            has_action INTEGER NOT NULL DEFAULT 1,
            has_bonus_action INTEGER NOT NULL DEFAULT 1,
            has_reaction INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_user_id INTEGER,
            updated_by_user_id INTEGER
        );

        INSERT INTO campaign_combatants (
            campaign_slug,
            combatant_type,
            character_slug,
            display_name,
            turn_value,
            initiative_bonus,
            current_hp,
            max_hp,
            temp_hp,
            movement_total,
            movement_remaining,
            has_action,
            has_bonus_action,
            has_reaction,
            created_at,
            updated_at
        )
        VALUES
            ('linden-pass', 'player_character', 'arden-march', 'Arden March', 18, 3, 38, 38, 0, 30, 30, 1, 1, 1, '2026-03-31T12:00:00Z', '2026-03-31T12:00:00Z'),
            ('linden-pass', 'npc', NULL, 'Clockwork Hound', 12, 2, 22, 22, 0, 40, 40, 1, 1, 1, '2026-03-31T12:00:00Z', '2026-03-31T12:00:00Z');
        """
    )
    connection.commit()
    connection.close()

    app = create_app()
    app.config.update(TESTING=True, DB_PATH=db_path)

    with app.app_context():
        init_database()

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT display_name, character_slug, source_kind, source_ref
        FROM campaign_combatants
        ORDER BY id ASC
        """
    ).fetchall()
    connection.close()

    assert [dict(row) for row in rows] == [
        {
            "display_name": "Arden March",
            "character_slug": "arden-march",
            "source_kind": "character",
            "source_ref": "arden-march",
        },
        {
            "display_name": "Clockwork Hound",
            "character_slug": None,
            "source_kind": "manual_npc",
            "source_ref": "",
        },
    ]


def test_combat_page_renders_context_panel_and_dm_page_focuses_selected_combatant(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )

    combat_page = client.get("/campaigns/linden-pass/combat")
    dm_page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")

    assert combat_page.status_code == 200
    assert dm_page.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    dm_html = dm_page.get_data(as_text=True)
    assert "Encounter context" in combat_html
    assert "Arden March" in combat_html
    assert "Advance turn" not in combat_html
    assert "Clear tracker" not in combat_html
    assert "Set current" not in combat_html
    assert "Remove combatant" not in combat_html
    assert 'class="combat-badge combat-badge--editable"' not in combat_html
    assert 'aria-label="Speed for Clockwork Hound"' not in combat_html
    assert "Encounter controls owns setup, seeding, turn-order authority, structural NPC edits, removal, and cleanup." in combat_html
    assert "Focus combatant" in dm_html
    assert "Clockwork Hound - NPC - Turn 12" in dm_html
    assert "Arden March - Player character - Turn 18 - Current turn" in dm_html
    assert f'id="combatant-{hound.id}"' in dm_html
    assert f'id="combatant-{arden.id}"' not in dm_html
    assert dm_html.count('class="card combatant-card') == 1
    assert "Advance turn" in dm_html
    assert "Clear tracker" in dm_html
    assert "Save turn value" in dm_html
    assert "Remove combatant" in dm_html


def test_dm_live_state_renders_only_selected_combatant_card(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == hound.id
    assert "Focus combatant" in payload["summary_html"]
    assert f'id="combatant-{hound.id}"' in payload["tracker_html"]
    assert f'id="combatant-{arden.id}"' not in payload["tracker_html"]


def test_dm_live_state_does_not_short_circuit_when_focus_changes(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_payload["selected_combatant_id"] == arden.id

    changed_focus_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert changed_focus_live_state.status_code == 200
    changed_focus_payload = changed_focus_live_state.get_json()
    assert changed_focus_payload["changed"] is True
    assert changed_focus_payload["selected_combatant_id"] == hound.id
    assert changed_focus_payload["live_view_token"] != initial_payload["live_view_token"]
    assert f'id="combatant-{hound.id}"' in changed_focus_payload["tracker_html"]
    assert f'id="combatant-{arden.id}"' not in changed_focus_payload["tracker_html"]


def test_non_async_combat_mutations_preserve_explicit_combatant_focus_in_redirects(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    combat_redirect = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/resources",
        data={
            "has_action": "1",
            "movement_remaining": 15,
            "combatant": hound.id,
        },
        follow_redirects=False,
    )
    dm_redirect = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Brass Sentry",
            "turn_value": 8,
            "current_hp": 18,
            "max_hp": 18,
            "temp_hp": 0,
            "movement_total": 30,
            "combat_view": "dm",
            "combatant": hound.id,
        },
        follow_redirects=False,
    )

    assert combat_redirect.status_code == 302
    assert dm_redirect.status_code == 302
    assert "/campaigns/linden-pass/combat?combatant=" in combat_redirect.headers["Location"]
    assert f"combatant={hound.id}" in combat_redirect.headers["Location"]
    assert "/campaigns/linden-pass/combat/dm?combatant=" in dm_redirect.headers["Location"]
    assert f"combatant={hound.id}" in dm_redirect.headers["Location"]


def test_selected_combatant_pages_seed_canonical_focus_urls(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    combat_response = client.get(f"/campaigns/linden-pass/combat?combatant={hound.id}")
    controls_response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")
    status_response = client.get(f"/campaigns/linden-pass/combat/status?combatant={hound.id}")

    assert combat_response.status_code == 200
    assert controls_response.status_code == 200
    assert status_response.status_code == 200

    combat_body = combat_response.get_data(as_text=True)
    controls_body = controls_response.get_data(as_text=True)
    status_body = status_response.get_data(as_text=True)

    assert f'data-combat-live-url="/campaigns/linden-pass/combat/live-state?combatant={hound.id}"' in combat_body
    assert f"/campaigns/linden-pass/combat/status?combatant={hound.id}" in combat_body
    assert f"/campaigns/linden-pass/combat/dm?combatant={hound.id}" in combat_body
    assert f'data-combat-live-url="/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}"' in controls_body
    assert f'data-combat-live-url="/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}"' in status_body


def test_dm_status_page_returns_404_for_invalid_explicit_target(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/combat/status?combatant=9999")

    assert response.status_code == 404


def test_dm_status_page_renders_only_selected_pc_detail(app, client, sign_in, users, tmp_path):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(f"/campaigns/linden-pass/combat/status?combatant={arden.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Encounter status" in body
    assert "Turn order" in body
    assert "Encounter roster" not in body
    assert "combat-turn-order-row--selected" in body
    assert f"/campaigns/linden-pass/combat/status?combatant={arden.id}" in body
    assert 'id="combat-status-snapshot"' in body
    assert "Compact encounter status first" in body
    assert "Character sections" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert 'data-combat-section-toggle="resources"' in body
    assert 'data-combat-section-panel="spells"' in body
    assert "Arden March" in body
    assert "Resources" in body
    assert "Scimitar" not in body


def test_status_live_state_renders_player_workspace_sections_for_selected_pc(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == arden.id
    assert "Character sections" in payload["detail_html"]
    assert 'data-combat-section-group' in payload["detail_html"]
    assert 'data-combat-section-toggle="actions"' in payload["detail_html"]
    assert 'data-combat-section-panel="resources"' in payload["detail_html"]


def test_status_live_state_renders_npc_workspace_sections_for_selected_systems_monster(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == goblin.id
    assert "NPC sections" in payload["detail_html"]
    assert 'data-combat-section-group' in payload["detail_html"]
    assert 'data-combat-section-toggle="actions"' in payload["detail_html"]
    assert 'data-combat-section-toggle="abilities_skills"' in payload["detail_html"]
    assert 'data-combat-section-toggle="bonus_actions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="reactions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="legendary_actions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="lair_actions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="traits"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="resources"' not in payload["detail_html"]
    assert 'data-combat-section-panel="actions"' in payload["detail_html"]
    assert 'data-combat-section-panel="traits"' not in payload["detail_html"]


def test_dm_status_page_sidebar_selection_is_wired_for_in_place_detail_swaps(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    goblin = _find_combatant(app, name="Goblin")
    assert arden is not None
    assert goblin is not None

    response = client.get(f"/campaigns/linden-pass/combat/status?combatant={arden.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "data-combat-status-select" in body
    assert f'data-combatant-id="{arden.id}"' in body
    assert f'data-combatant-id="{goblin.id}"' in body
    assert "event.preventDefault();" in body
    assert 'fetch(buildUrl(liveUrl, nextCombatantId), {' in body
    assert 'renderPayload(payload, { force: true, updateHistory: true });' in body
    assert 'window.history.replaceState({}, "", buildUrl(baseViewUrl, selectedCombatantId));' in body
    assert "const workspaceTools = window.__playerWikiCombatWorkspace || null;" in body
    assert "workspaceTools.capture(detailRoot)" in body
    assert "workspaceTools.restore(" in body


def test_dm_status_page_can_render_systems_monster_detail(app, client, sign_in, users, tmp_path):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    response = client.get(f"/campaigns/linden-pass/combat/status?combatant={goblin.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="combat-status-snapshot"' in body
    assert "NPC sections" in body
    assert "Systems monster detail" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert 'data-combat-section-toggle="abilities_skills"' in body
    assert 'data-combat-section-toggle="bonus_actions"' not in body
    assert 'data-combat-section-toggle="reactions"' not in body
    assert 'data-combat-section-toggle="legendary_actions"' not in body
    assert 'data-combat-section-toggle="lair_actions"' not in body
    assert 'data-combat-section-toggle="traits"' not in body
    assert 'data-combat-section-toggle="resources"' not in body
    assert "Open Systems entry" in body
    assert "Scimitar" in body


def test_dm_status_page_can_render_dm_content_statblock_detail(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(app, created_by_user_id=users["dm"]["id"])
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    brass_hound = _find_combatant(app, name="Brass Hound")
    assert brass_hound is not None

    response = client.get(f"/campaigns/linden-pass/combat/status?combatant={brass_hound.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="combat-status-snapshot"' in body
    assert "NPC sections" in body
    assert "DM Content statblock detail" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert 'data-combat-section-toggle="bonus_actions"' not in body
    assert 'data-combat-section-toggle="reactions"' not in body
    assert 'data-combat-section-toggle="legendary_actions"' not in body
    assert 'data-combat-section-toggle="lair_actions"' not in body
    assert 'data-combat-section-toggle="traits"' not in body
    assert 'data-combat-section-toggle="resources"' not in body
    assert 'data-combat-section-toggle="abilities_skills"' not in body
    assert "Source file: brass-hound.md" in body
    assert "Bite" in body


def test_dm_status_page_groups_reference_npc_sections_under_reference_tab(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(
        app,
        created_by_user_id=users["dm"]["id"],
        filename="mirror-spy.md",
        markdown_text="""---
title: Mirror Spy
armor_class: 14
hp: 27
speed: 30 ft.
initiative_bonus: 3
---

## At-A-Glance

A cautious infiltrator who prefers disguise, distance, and retreat routes over fair fights.

## Statblock

Medium humanoid, neutral

## Tactics

Mirror Spy opens from range and only closes when an ally has already pinned the target.

## Scaling Notes

Increase hit points to 36 and add one extra reaction each round for a tougher version.

## Notes

Tracks party rumors and tries to escape instead of fighting to the death.

## Changeling

Can alter appearance between encounters to re-enter a scene under a different identity.

## Actions

### Dagger

+5 to hit, 5 piercing damage.
""",
    )
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    mirror_spy = _find_combatant(app, name="Mirror Spy")
    assert mirror_spy is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={mirror_spy.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == mirror_spy.id
    assert 'data-combat-default-section="reference"' in payload["detail_html"]
    assert 'data-combat-section-toggle="reference"' in payload["detail_html"]
    assert 'data-combat-section-panel="reference"' in payload["detail_html"]
    assert 'data-combat-section-toggle="actions"' in payload["detail_html"]
    assert "At-A-Glance" in payload["detail_html"]
    assert "Statblock" in payload["detail_html"]
    assert "Tactics" in payload["detail_html"]
    assert "Scaling Notes" in payload["detail_html"]
    assert "Notes" in payload["detail_html"]
    assert "Changeling" in payload["detail_html"]
    assert "Dagger" in payload["detail_html"]


def test_dm_status_page_shows_manual_npc_fallback_and_missing_source_fallback(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    statblock = _create_dm_statblock(app, created_by_user_id=users["dm"]["id"])
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    clockwork_hound = _find_combatant(app, name="Clockwork Hound")
    brass_hound = _find_combatant(app, name="Brass Hound")
    assert clockwork_hound is not None
    assert brass_hound is not None

    manual_response = client.get(f"/campaigns/linden-pass/combat/status?combatant={clockwork_hound.id}")
    assert manual_response.status_code == 200
    assert "added manually" in manual_response.get_data(as_text=True)

    with app.app_context():
        app.extensions["campaign_dm_content_service"].delete_statblock(TEST_CAMPAIGN_SLUG, statblock.id)

    missing_response = client.get(f"/campaigns/linden-pass/combat/status?combatant={brass_hound.id}")
    assert missing_response.status_code == 200
    missing_body = missing_response.get_data(as_text=True)
    assert "Source detail unavailable" in missing_body
    assert "no longer available" in missing_body


def test_status_live_state_preserves_selected_target_and_returns_selected_detail(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    goblin = _find_combatant(app, name="Goblin")
    assert arden is not None
    assert goblin is not None

    first_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert first_live_state.status_code == 200
    first_payload = first_live_state.get_json()
    assert first_payload["selected_combatant_id"] == goblin.id
    assert "Turn order" in first_payload["board_html"]
    assert "Encounter roster" not in first_payload["board_html"]
    assert "combat-turn-order-row--selected" in first_payload["board_html"]
    assert f"/campaigns/linden-pass/combat/status?combatant={goblin.id}" in first_payload["board_html"]
    assert "Goblin" in first_payload["detail_html"]
    assert "Scimitar" in first_payload["detail_html"]
    assert "Arden March" not in first_payload["detail_html"]

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )
    second_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert second_live_state.status_code == 200
    second_payload = second_live_state.get_json()
    assert second_payload["selected_combatant_id"] == goblin.id
    assert "Turn order" in second_payload["board_html"]
    assert "combat-turn-order-row--selected" in second_payload["board_html"]
    assert "Goblin" in second_payload["detail_html"]
    assert "Scimitar" in second_payload["detail_html"]


def test_status_live_state_short_circuits_for_unchanged_selected_target(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True

    unchanged_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(initial_live_state)
    _assert_live_diagnostics_headers(unchanged_live_state)


def test_combat_surface_live_payloads_report_canonical_focus_urls(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    combat_payload = client.get(
        f"/campaigns/linden-pass/combat/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()
    controls_payload = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()
    status_payload = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()

    assert combat_payload["page_url"] == f"/campaigns/linden-pass/combat?combatant={hound.id}"
    assert combat_payload["live_url"] == f"/campaigns/linden-pass/combat/live-state?combatant={hound.id}"
    assert controls_payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={hound.id}"
    assert controls_payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}"
    assert status_payload["page_url"] == f"/campaigns/linden-pass/combat/status?combatant={hound.id}"
    assert status_payload["live_url"] == f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}"


def test_status_live_state_falls_back_to_remaining_target_when_selected_combatant_disappears(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    delete_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 302

    fallback_response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )

    assert fallback_response.status_code == 200
    fallback_payload = fallback_response.get_json()
    assert fallback_payload["selected_combatant_id"] == arden.id
    assert fallback_payload["page_url"] == f"/campaigns/linden-pass/combat/status?combatant={arden.id}"
    assert fallback_payload["live_url"] == f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}"
    assert "Arden March" in fallback_payload["detail_html"]
    assert "Clockwork Hound" not in fallback_payload["detail_html"]


def test_combat_loading_styles_do_not_dim_live_combat_surfaces():
    css = Path("player_wiki/static/styles.css").read_text(encoding="utf-8")

    assert "combat-live-root][data-loading" not in css
    assert "combat-status-live-root][data-loading" not in css
    assert "combat-character-live-root][data-loading" not in css


def test_live_state_logs_slow_response_warning_without_live_diagnostics(
    app,
    client,
    sign_in,
    users,
    caplog,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    app.config.update(
        LIVE_DIAGNOSTICS=False,
        LIVE_SLOW_LOG_THRESHOLD_MS=0.01,
    )

    caplog.set_level(logging.WARNING)

    response = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )

    assert response.status_code == 200

    slow_records = [
        record
        for record in caplog.records
        if record.message.startswith("slow_live_response ")
    ]
    assert slow_records

    slow_payload = json.loads(slow_records[-1].message.split(" ", 1)[1])
    assert slow_payload["view"] == "combat"
    assert slow_payload["path"] == "/campaigns/linden-pass/combat/live-state"
    assert slow_payload["changed"] is True
    assert slow_payload["request_time_ms"] >= 0.01


def test_sync_player_character_snapshots_throttles_repeated_refreshes(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    combat_service.player_snapshot_sync_interval_seconds = 5.0
    current_time = {"value": 100.0}
    sync_lookup_calls: list[tuple[str, str]] = []
    original_get_visible_character = combat_service.character_repository.get_visible_character

    def count_lookup(campaign_slug: str, character_slug: str):
        sync_lookup_calls.append((campaign_slug, character_slug))
        return original_get_visible_character(campaign_slug, character_slug)

    monkeypatch.setattr(campaign_combat_service_module.time, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(combat_service.character_repository, "get_visible_character", count_lookup)

    with app.app_context():
        combat_service.sync_player_character_snapshots("linden-pass")
        current_time["value"] = 101.0
        combat_service.sync_player_character_snapshots("linden-pass")
        current_time["value"] = 106.0
        combat_service.sync_player_character_snapshots("linden-pass")

    assert sync_lookup_calls == [
        ("linden-pass", "arden-march"),
        ("linden-pass", "arden-march"),
    ]


def test_combat_live_requests_sync_player_snapshots_once_per_request(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    sync_calls: list[str] = []
    original_sync = combat_service.sync_player_character_snapshots

    def count_sync(campaign_slug: str):
        sync_calls.append(campaign_slug)
        return original_sync(campaign_slug)

    monkeypatch.setattr(combat_service, "sync_player_character_snapshots", count_sync)

    combat_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )
    assert combat_live_state.status_code == 200
    assert sync_calls == ["linden-pass"]

    sync_calls.clear()

    status_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )
    assert status_live_state.status_code == 200
    assert sync_calls == ["linden-pass"]

