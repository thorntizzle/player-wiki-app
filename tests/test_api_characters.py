from __future__ import annotations

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

def test_api_character_endpoints_allow_assigned_owner_updates(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-api")
    other_player_token = issue_api_token(app, users["party"]["email"], label="other-character-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]

    notes_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "player_notes_markdown": "Remember to bring the ash-yard contract to the council.",
        },
    )

    assert notes_response.status_code == 200
    updated_character = notes_response.get_json()["character"]
    assert updated_character["state_record"]["revision"] == starting_revision + 1
    assert (
        updated_character["state_record"]["state"]["notes"]["player_notes_markdown"]
        == "Remember to bring the ash-yard contract to the council."
    )

    clear_notes_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(owner_token),
        json={
            "expected_revision": updated_character["state_record"]["revision"],
            "player_notes_markdown": "",
        },
    )

    assert clear_notes_response.status_code == 200
    cleared_character = clear_notes_response.get_json()["character"]
    assert cleared_character["state_record"]["revision"] == updated_character["state_record"]["revision"] + 1
    assert cleared_character["state_record"]["state"]["notes"]["player_notes_markdown"] == ""

    personal_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/personal",
        headers=api_headers(owner_token),
        json={
            "expected_revision": cleared_character["state_record"]["revision"],
            "physical_description_markdown": "Broad-shouldered and steady-eyed.",
            "background_markdown": "Spent years running messages along the harbor roads.",
        },
    )

    assert personal_response.status_code == 200
    personal_character = personal_response.get_json()["character"]
    assert personal_character["state_record"]["state"]["notes"]["physical_description_markdown"] == (
        "Broad-shouldered and steady-eyed."
    )
    assert personal_character["state_record"]["state"]["notes"]["background_markdown"] == (
        "Spent years running messages along the harbor roads."
    )

    stale_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "player_notes_markdown": "This revision should conflict.",
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"

    blocked_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(other_player_token),
        json={
            "expected_revision": starting_revision + 1,
            "player_notes_markdown": "Another player should not be able to edit this sheet.",
        },
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"
    assert blocked_response.get_json()["error"]["message"] == "You do not have permission to update this character from this view."


def test_api_character_sheet_edit_batch_updates_state_backed_sections_in_one_revision(
    client, app, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-sheet-edit-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]
    second_level_slot = next(
        item
        for item in character_payload["state_record"]["state"]["spell_slots"]
        if int(item.get("level") or 0) == 2
    )

    batch_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/sheet-edit",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "vitals": {
                "current_hp": 35,
                "temp_hp": 4,
            },
            "resources": [
                {
                    "id": "sorcery-points",
                    "current": 3,
                }
            ],
            "spell_slots": [
                {
                    "level": 2,
                    "slot_lane_id": second_level_slot.get("slot_lane_id", ""),
                    "used": 2,
                }
            ],
            "inventory": [
                {
                    "id": "crossbow-bolts-4",
                    "quantity": 18,
                }
            ],
            "currency": {
                "sp": 7,
                "gp": 125,
            },
            "notes": {
                "player_notes_markdown": "Batch note test",
            },
            "personal": {
                "physical_description_markdown": "Lean and weathered.",
                "background_markdown": "Raised around the salt docks.",
            },
        },
    )

    assert batch_response.status_code == 200
    updated_character = batch_response.get_json()["character"]
    updated_state = updated_character["state_record"]["state"]
    assert updated_character["state_record"]["revision"] == starting_revision + 1
    assert updated_state["vitals"]["current_hp"] == 35
    assert updated_state["vitals"]["temp_hp"] == 4
    assert {item["id"]: item for item in updated_state["resources"]}["sorcery-points"]["current"] == 3
    assert next(
        item
        for item in updated_state["spell_slots"]
        if int(item.get("level") or 0) == 2
        and str(item.get("slot_lane_id") or "") == str(second_level_slot.get("slot_lane_id") or "")
    )["used"] == 2
    assert {item["id"]: item for item in updated_state["inventory"]}["crossbow-bolts-4"]["quantity"] == 18
    assert updated_state["currency"]["gp"] == 125
    assert updated_state["currency"]["sp"] == 7
    assert updated_state["notes"]["player_notes_markdown"] == "Batch note test"
    assert updated_state["notes"]["physical_description_markdown"] == "Lean and weathered."
    assert updated_state["notes"]["background_markdown"] == "Raised around the salt docks."

    stale_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/sheet-edit",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "notes": {
                "player_notes_markdown": "This stale batch should conflict.",
            },
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"
    assert stale_response.get_json()["error"]["message"] == (
        "This sheet changed before your batch save finished. Refresh and review the latest sheet before saving "
        "again. Session Character, Combat, or another tab may have changed nearby fields first; nothing was "
        "auto-merged."
    )


def test_api_character_sheet_edit_batch_rejects_delta_actions(
    client, app, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-sheet-edit-delta-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]

    delta_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/sheet-edit",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "resources": [
                {
                    "id": "sorcery-points",
                    "delta": -1,
                }
            ],
        },
    )

    assert delta_response.status_code == 400
    assert delta_response.get_json()["error"]["code"] == "validation_error"
    assert "absolute current values" in delta_response.get_json()["error"]["message"]

    unchanged_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert unchanged_response.status_code == 200
    unchanged_state = unchanged_response.get_json()["character"]["state_record"]["state"]
    assert {item["id"]: item for item in unchanged_state["resources"]}["sorcery-points"]["current"] == (
        {item["id"]: item for item in character_payload["state_record"]["state"]["resources"]}["sorcery-points"]["current"]
    )


def test_api_character_item_action_use_spends_spell_slot_and_conflicts_when_stale(
    client,
    app,
    users,
    sign_in,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    item_path = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content" / "items" / "api-innovators-bolt.md"
    item_path.write_text(
        "\n".join(
            [
                "---",
                "title: API Innovator's Bolt",
                "section: Items",
                "page_type: item",
                "source_ref: API test item page",
                "published: true",
                "---",
                "",
                "*Weapon (pistol), very rare (requires attunement by an artificer)*",
                "",
                "A spell-slot-loaded firearm.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-item-action-use-api")
    import_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
        headers=api_headers(dm_token),
        json={
            "page_ref": "items/api-innovators-bolt",
            "visibility": "players",
            "item_mechanics_review_status": "approved",
            "item_mechanics": approved_innovators_bolt_item_mechanics(allowed_levels=[1, 2]),
        },
    )
    assert import_response.status_code == 200
    item_entry = import_response.get_json()["entry"]
    assert item_entry["linked_published_page_ref"] == "items/api-innovators-bolt"

    def add_innovators_bolt(definition):
        equipment = list(definition.get("equipment_catalog") or [])
        equipment.append(
            {
                "id": "api-innovators-bolt-1",
                "name": "API Innovator's Bolt",
                "default_quantity": 1,
                "weight": "",
                "notes": "",
                "page_ref": "items/api-innovators-bolt",
            }
        )
        definition["equipment_catalog"] = equipment

    def add_innovators_bolt_state(state):
        inventory = list(state.get("inventory") or [])
        inventory.append(
            {
                "id": "api-innovators-bolt-1",
                "catalog_ref": "api-innovators-bolt-1",
                "name": "API Innovator's Bolt",
                "quantity": 1,
                "is_equipped": True,
                "is_attuned": True,
            }
        )
        state["inventory"] = inventory
        for slot in list(state.get("spell_slots") or []):
            if int(slot.get("level") or 0) in {1, 2}:
                slot["used"] = 0

    _write_character_definition(app, "arden-march", add_innovators_bolt)
    _write_character_state(app, "arden-march", add_innovators_bolt_state)

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-item-action-use-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )
    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    action = next(
        item
        for item in character_payload["presented_item_use_actions"]
        if item["id"] == "innovators-bolt-enchanted-bullet"
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])
    read_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")
    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert 'id="character-item-use-actions"' in read_html
    assert "Enchanted Bullet" in read_html
    assert "Incendiary" in read_html
    assert "table-managed" in read_html

    session_response = client.get(
        "/campaigns/linden-pass/session/character?character=arden-march&page=equipment"
    )
    assert session_response.status_code == 200
    session_html = session_response.get_data(as_text=True)
    assert 'id="character-item-use-actions"' in session_html
    assert "Enchanted Bullet" in session_html
    assert "Booming" in session_html
    assert "Smoke" in session_html

    slot_option = next(option for option in action["slot_options"] if option["available"] > 1)
    matching_slot_before = next(
        item
        for item in character_payload["state_record"]["state"]["spell_slots"]
        if int(item.get("level") or 0) == int(slot_option["level"])
        and str(item.get("slot_lane_id") or "") == str(slot_option["slot_lane_id"] or "")
    )

    use_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/item-actions/innovators-bolt-enchanted-bullet/use",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character_payload["state_record"]["revision"],
            "choice_id": "incendiary",
            "slot_selection": slot_option["selection"],
        },
    )

    assert use_response.status_code == 200
    updated_character = use_response.get_json()["character"]
    matching_slot_after = next(
        item
        for item in updated_character["state_record"]["state"]["spell_slots"]
        if int(item.get("level") or 0) == int(slot_option["level"])
        and str(item.get("slot_lane_id") or "") == str(slot_option["slot_lane_id"] or "")
    )
    assert matching_slot_after["used"] == matching_slot_before["used"] + 1
    assert updated_character["state_record"]["revision"] == character_payload["state_record"]["revision"] + 1

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/item-actions/innovators-bolt-enchanted-bullet/use",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character_payload["state_record"]["revision"],
            "choice_id": "incendiary",
            "slot_selection": slot_option["selection"],
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_session_endpoints_cover_dnd_state_controls(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-state-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]
    second_level_slot = next(
        item
        for item in character_payload["state_record"]["state"]["spell_slots"]
        if int(item.get("level") or 0) == 2
    )

    resource_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/resources/sorcery-points",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "current": 1,
        },
    )

    assert resource_response.status_code == 200
    resource_character = resource_response.get_json()["character"]
    assert resource_character["state_record"]["revision"] == starting_revision + 1
    resource_state = resource_character["state_record"]["state"]
    assert {item["id"]: item for item in resource_state["resources"]}["sorcery-points"]["current"] == 1

    stale_resource_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/resources/sorcery-points",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "current": 2,
        },
    )

    assert stale_resource_response.status_code == 409
    assert stale_resource_response.get_json()["error"]["code"] == "state_conflict"

    spell_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/spell-slots/2",
        headers=api_headers(owner_token),
        json={
            "expected_revision": resource_character["state_record"]["revision"],
            "slot_lane_id": second_level_slot.get("slot_lane_id", ""),
            "used": 1,
        },
    )

    assert spell_response.status_code == 200
    spell_character = spell_response.get_json()["character"]
    spell_state = spell_character["state_record"]["state"]
    assert next(
        item
        for item in spell_state["spell_slots"]
        if int(item.get("level") or 0) == 2
        and str(item.get("slot_lane_id") or "") == str(second_level_slot.get("slot_lane_id") or "")
    )["used"] == 1

    inventory_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/inventory/crossbow-bolts-4",
        headers=api_headers(owner_token),
        json={
            "expected_revision": spell_character["state_record"]["revision"],
            "quantity": 17,
        },
    )

    assert inventory_response.status_code == 200
    inventory_character = inventory_response.get_json()["character"]
    inventory_state = inventory_character["state_record"]["state"]
    assert {item["id"]: item for item in inventory_state["inventory"]}["crossbow-bolts-4"]["quantity"] == 17

    currency_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/currency",
        headers=api_headers(owner_token),
        json={
            "expected_revision": inventory_character["state_record"]["revision"],
            "sp": 8,
            "gp": 12,
        },
    )

    assert currency_response.status_code == 200
    currency_character = currency_response.get_json()["character"]
    currency_state = currency_character["state_record"]["state"]
    assert currency_state["currency"]["sp"] == 8
    assert currency_state["currency"]["gp"] == 12

    preview_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/rest-preview/long",
        headers=api_headers(owner_token),
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.get_json()["preview"]
    assert preview_payload["rest_type"] == "long"
    assert preview_payload["label"] == "Long Rest"
    assert preview_payload["changes"]
    assert isinstance(preview_payload["adjustments"]["current_hp"], int)
    hit_dice_pools = preview_payload["adjustments"]["hit_dice"]["pools"]
    assert hit_dice_pools
    adjusted_hit_die_faces = str(hit_dice_pools[0]["faces"])

    rest_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/rest/long",
        headers=api_headers(owner_token),
        json={
            "expected_revision": currency_character["state_record"]["revision"],
            "current_hp": 7,
            "hit_dice_current": {adjusted_hit_die_faces: 0},
        },
    )

    assert rest_response.status_code == 200
    rested_character = rest_response.get_json()["character"]
    rested_state = rested_character["state_record"]["state"]
    assert rested_state["vitals"]["current_hp"] == 7
    assert next(
        pool
        for pool in rested_state["hit_dice"]["pools"]
        if str(pool["faces"]) == adjusted_hit_die_faces
    )["current"] == 0
    rested_sorcery = {item["id"]: item for item in rested_state["resources"]}["sorcery-points"]
    assert rested_sorcery["current"] == rested_sorcery["max"]
    assert next(
        item
        for item in rested_state["spell_slots"]
        if int(item.get("level") or 0) == 2
        and str(item.get("slot_lane_id") or "") == str(second_level_slot.get("slot_lane_id") or "")
    )["used"] == 0


def test_api_character_session_endpoints_cover_xianxia_state_controls(
    client,
    app,
    users,
    sign_in,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("API Session Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/api-session-crane"
    )

    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-session-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane",
        headers=api_headers(dm_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    assert character_payload["presented_xianxia"]["system_label"] == "Xianxia"
    assert character_payload["presented_xianxia"]["resources"]["durability"][0]["label"] == "HP"
    starting_revision = character_payload["state_record"]["revision"]

    vitals_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane/session/vitals",
        headers=api_headers(dm_token),
        json={
            "expected_revision": starting_revision,
            "current_hp": 7,
            "temp_hp": 2,
            "current_stance": 8,
            "temp_stance": 1,
            "current_jing": 0,
            "current_qi": 1,
            "current_shen": 1,
            "current_yin": 0,
            "current_yang": 1,
            "current_dao": 2,
        },
    )

    assert vitals_response.status_code == 200
    vitals_character = vitals_response.get_json()["character"]
    vitals_state = vitals_character["state_record"]["state"]
    assert vitals_state["vitals"] == {"current_hp": 7, "temp_hp": 2}
    assert vitals_state["xianxia"]["vitals"] == {
        "current_hp": 7,
        "temp_hp": 2,
        "current_stance": 8,
        "temp_stance": 1,
    }
    assert vitals_state["xianxia"]["energies"] == {
        "jing": {"current": 0},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert vitals_state["xianxia"]["yin_yang"] == {
        "yin_current": 0,
        "yang_current": 1,
    }
    assert vitals_state["xianxia"]["dao"] == {"current": 2}
    assert vitals_character["presented_xianxia"]["resources"]["dao"]["current"] == 2

    active_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-active-state",
        headers=api_headers(dm_token),
        json={
            "expected_revision": vitals_character["state_record"]["revision"],
            "active_stance_name": "Stone Root",
            "active_aura_name": "Azure Bell",
        },
    )

    assert active_response.status_code == 200
    active_character = active_response.get_json()["character"]
    active_state = active_character["state_record"]["state"]["xianxia"]
    assert active_state["active_stance"] == {"name": "Stone Root"}
    assert active_state["active_aura"] == {"name": "Azure Bell"}
    assert active_character["presented_xianxia"]["active_state"]["stance"]["name"] == "Stone Root"

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory",
        headers=api_headers(dm_token),
        json={
            "expected_revision": active_character["state_record"]["revision"],
            "item": {
                "name": "Spirit Fan",
                "quantity": 2,
                "item_nature": "Relic",
                "item_type": "Artifact",
                "notes": "Painted with cloud sigils.",
                "tags": ["focus"],
                "equippable": True,
                "is_equipped": False,
            },
        },
    )

    assert add_response.status_code == 200
    add_character = add_response.get_json()["character"]
    added_item = next(
        item
        for item in add_character["presented_xianxia"]["inventory"]["quantities"]
        if item["name"] == "Spirit Fan"
    )
    assert added_item["quantity"] == 2
    assert added_item["item_type"] == "Artifact"

    quantity_response = client.patch(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/inventory/{added_item['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_revision": add_character["state_record"]["revision"],
            "quantity": 3,
        },
    )

    assert quantity_response.status_code == 200
    quantity_character = quantity_response.get_json()["character"]
    quantity_item = next(
        item
        for item in quantity_character["presented_xianxia"]["inventory"]["quantities"]
        if item["id"] == added_item["id"]
    )
    assert quantity_item["quantity"] == 3

    update_response = client.patch(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory/{added_item['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_revision": quantity_character["state_record"]["revision"],
            "item": {
                "id": added_item["id"],
                "name": "Spirit Fan",
                "quantity": 4,
                "item_nature": "Relic",
                "item_type": "Artifact",
                "notes": "Painted with storm sigils.",
                "tags": ["focus", "storm"],
                "equippable": True,
                "is_equipped": False,
            },
        },
    )

    assert update_response.status_code == 200
    update_character = update_response.get_json()["character"]
    updated_item = next(
        item
        for item in update_character["presented_xianxia"]["inventory"]["quantities"]
        if item["id"] == added_item["id"]
    )
    assert updated_item["quantity"] == 4
    assert updated_item["notes"] == "Painted with storm sigils."
    assert updated_item["tags"] == ["focus", "storm"]

    equip_response = client.patch(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory/{added_item['id']}/equipped",
        headers=api_headers(dm_token),
        json={
            "expected_revision": update_character["state_record"]["revision"],
            "is_equipped": True,
        },
    )

    assert equip_response.status_code == 200
    equip_character = equip_response.get_json()["character"]
    equipped_item = next(
        item
        for item in equip_character["presented_xianxia"]["equipment"]["equipped_items"]
        if item["id"] == added_item["id"]
    )
    assert equipped_item["is_equipped"] is True

    remove_response = client.delete(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory/{added_item['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_revision": equip_character["state_record"]["revision"],
        },
    )

    assert remove_response.status_code == 200
    remove_character = remove_response.get_json()["character"]
    assert all(
        item["id"] != added_item["id"]
        for item in remove_character["presented_xianxia"]["inventory"]["quantities"]
    )


def test_api_character_session_endpoints_cover_xianxia_dao_immolating_actions(
    client,
    app,
    users,
    sign_in,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("API Dao Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload.setdefault("xianxia", {})
        xianxia["insight"] = {"available": 12, "spent": 0}
        dao_immolating = xianxia.setdefault("dao_immolating_techniques", {})
        dao_immolating["prepared"] = [
            {
                "name": "Ashen Bell",
                "notes": "Stored for a prepared request.",
            }
        ]
        dao_immolating["use_history"] = [
            {
                "name": "River-Cleaving Spark",
                "approval_status": "approved",
                "approval_notes": "Approved for this duel.",
            }
        ]

    _write_character_definition(app, "api-dao-crane", _prepare_definition)

    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-dao-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane",
        headers=api_headers(dm_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    assert character["permissions"]["can_record_xianxia_dao_immolating_use"] is True
    approval_group = next(
        group
        for group in character["presented_xianxia"]["approval"]["status_groups"]
        if group["key"] == "dao_immolating_use_records"
    )
    assert approval_group["records"][0]["use_record_index"] == 0
    assert approval_group["records"][0]["status_label"] == "Approved"
    assert approval_group["records"][0]["insight_cost"] == 10

    player_token = issue_api_token(app, users["party"]["email"], label="player-xianxia-dao-api")
    forbidden_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane/session/xianxia-dao-immolating-use-records",
        headers=api_headers(player_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "use_record_index": 0,
        },
    )

    assert forbidden_response.status_code == 403

    request_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane/session/xianxia-dao-immolating-use-requests",
        headers=api_headers(dm_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "prepared_record_index": 0,
            "notes": "Player called on the prepared bell.",
        },
    )

    assert request_response.status_code == 200
    request_character = request_response.get_json()["character"]
    request_history = request_character["definition"]["xianxia"]["dao_immolating_techniques"][
        "use_history"
    ]
    assert request_history[-1]["name"] == "Ashen Bell"
    assert request_history[-1]["request_type"] == "dao_immolating_use"
    assert request_history[-1]["request_source"] == "prepared_record"
    assert request_history[-1]["approval_status"] == "pending"
    assert request_history[-1]["prepared_record_index"] == 0
    request_group = next(
        group
        for group in request_character["presented_xianxia"]["approval"]["status_groups"]
        if group["key"] == "dao_immolating_use_records"
    )
    assert [record["status_label"] for record in request_group["records"]] == [
        "Approved",
        "Pending",
    ]

    record_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane/session/xianxia-dao-immolating-use-records",
        headers=api_headers(dm_token),
        json={
            "expected_revision": request_character["state_record"]["revision"],
            "use_record_index": 0,
            "notes": "Spent during the bridge duel.",
        },
    )

    assert record_response.status_code == 200
    record_character = record_response.get_json()["character"]
    xianxia_definition = record_character["definition"]["xianxia"]
    recorded_use = xianxia_definition["dao_immolating_techniques"]["use_history"][0]
    assert recorded_use["used"] is True
    assert recorded_use["one_use_status"] == "used"
    assert recorded_use["insight_spent"] == 10
    assert recorded_use["use_notes"] == "Spent during the bridge duel."
    assert xianxia_definition["insight"] == {"available": 2, "spent": 10}
    assert xianxia_definition["advancement_history"][-1]["action"] == "dao_immolating_technique_used"
    record_group = next(
        group
        for group in record_character["presented_xianxia"]["approval"]["status_groups"]
        if group["key"] == "dao_immolating_use_records"
    )
    assert record_group["records"][0]["used"] is True
    assert record_group["records"][0]["use_notes"] == "Spent during the bridge duel."


def test_api_character_session_equipment_state_endpoint_updates_wield_mode_and_rejects_invalid_rows(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-equipment-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    equipment_state = character["equipment_state"]
    assert equipment_state["rows"]
    quarterstaff = {item["id"]: item for item in equipment_state["rows"]}["quarterstaff-2"]
    assert quarterstaff["supports_weapon_wield_mode"] is True
    assert {"value": "two-handed", "label": "Two-Handed"} in quarterstaff["weapon_wield_options"]

    wield_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/quarterstaff-2",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "weapon_wield_mode": "two-handed",
        },
    )

    assert wield_response.status_code == 200
    wielded_character = wield_response.get_json()["character"]
    wielded_inventory = {
        item["catalog_ref"] if item.get("catalog_ref") else item["id"]: item
        for item in wielded_character["state_record"]["state"]["inventory"]
    }
    assert wielded_inventory["quarterstaff-2"]["is_equipped"] is True
    assert wielded_inventory["quarterstaff-2"]["weapon_wield_mode"] == "two-handed"
    wielded_equipment = {item["id"]: item for item in wielded_character["equipment_state"]["rows"]}
    assert wielded_equipment["quarterstaff-2"]["weapon_wield_mode"] == "two-handed"
    assert wielded_equipment["quarterstaff-2"]["equipped_label"] == "Two-Handed"

    stale_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/quarterstaff-2",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "weapon_wield_mode": "",
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"

    invalid_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/backpack-5",
        headers=api_headers(owner_token),
        json={
            "expected_revision": wielded_character["state_record"]["revision"],
            "is_equipped": True,
        },
    )

    assert invalid_response.status_code == 400
    assert invalid_response.get_json()["error"]["code"] == "validation_error"
    assert "does not support equipment state" in invalid_response.get_json()["error"]["message"]


def test_api_character_artificer_infusions_apply_enhanced_defense_and_note_only_effects(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    def _mutate_definition(payload: dict) -> None:
        payload["source"] = {
            "source_type": "native_character_builder",
            "source_path": "builder://arden-march",
            "imported_from": "In-app Native Level 6 Builder",
        }
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Artificer 6"
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Artificer",
                "subclass_name": "Armorer",
                "level": 6,
            }
        ]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
        stats["ability_scores"] = ability_scores
        stats["armor_class"] = 16
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "artificer-infusions-1",
                "name": "Artificer Infusions",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "You have invented numerous magical infusions.",
                "activation_type": "passive",
            },
            {
                "id": "enhanced-defense-1",
                "name": "Enhanced Defense",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "A creature gains a +1 bonus to Armor Class while wearing the infused item.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-1",
            },
            {
                "id": "homunculus-servant-1",
                "name": "Homunculus Servant",
                "category": "class_feature",
                "source": "TCoE 13",
                "description_markdown": "You learn intricate methods for creating a special homunculus.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-1",
            },
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
                "is_equipped": True,
                "is_attuned": False,
            },
            {
                "id": "backpack-1",
                "name": "Backpack",
                "default_quantity": 1,
                "weight": "5 lb.",
                "notes": "",
                "tags": [],
                "is_equipped": False,
                "is_attuned": False,
            },
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
                "is_equipped": True,
                "is_attuned": False,
                "tags": [],
            },
            {
                "id": "backpack-1",
                "catalog_ref": "backpack-1",
                "name": "Backpack",
                "quantity": 1,
                "weight": "5 lb.",
                "notes": "",
                "is_equipped": False,
                "is_attuned": False,
                "tags": [],
            },
        ]
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-artificer-infusions-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    infusions_state = character["equipment_state"]["artificer_infusions_state"]
    known_by_key = {entry["infusion_key"]: entry for entry in infusions_state["known"]}
    assert infusions_state["available"] is True
    assert infusions_state["artificer_level"] == 6
    assert infusions_state["known_capacity"] == 6
    assert infusions_state["active_capacity"] == 3
    assert "enhanced-defense" in known_by_key
    assert "homunculus-servant" in known_by_key
    assert known_by_key["enhanced-defense"]["target_options"] == [
        {"value": "scale-mail-1", "label": "Scale Mail"}
    ]
    assert any(option["value"] == "backpack-1" for option in known_by_key["homunculus-servant"]["target_options"])

    patch_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/artificer-infusions",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "active": [
                {"infusion_key": "enhanced-defense", "target_item_ref": "scale-mail-1"},
                {"infusion_key": "homunculus-servant", "target_item_ref": "backpack-1"},
            ],
        },
    )

    assert patch_response.status_code == 200
    updated_character = patch_response.get_json()["character"]
    updated_inventory = {
        item["catalog_ref"] if item.get("catalog_ref") else item["id"]: item
        for item in updated_character["state_record"]["state"]["inventory"]
    }
    assert updated_inventory["scale-mail-1"]["active_infusions"][0]["infusion_key"] == "enhanced-defense"
    assert updated_inventory["backpack-1"]["active_infusions"][0]["infusion_key"] == "homunculus-servant"
    assert updated_character["definition"]["stats"]["armor_class"] == 17
    overview_by_label = {stat["label"]: stat["value"] for stat in updated_character["overview_stats"]}
    assert overview_by_label["Armor Class"] == "17"
    defensive_rules = updated_character["definition"]["stats"]["defensive_state"]["rules"]
    assert any(rule["title"] == "Enhanced Defense" and rule["active"] is True for rule in defensive_rules)

    updated_infusions = updated_character["equipment_state"]["artificer_infusions_state"]
    active_by_key = {entry["infusion_key"]: entry for entry in updated_infusions["active"]}
    assert active_by_key["enhanced-defense"]["automation_status"] == "automated"
    assert active_by_key["homunculus-servant"]["automation_status"] == "note_only"
    assert active_by_key["homunculus-servant"]["effect_summary"] == (
        "Active note only; this infusion does not have automated effects yet."
    )


def test_api_character_detail_exposes_linked_item_and_spell_details(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    item_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-api-linked-quarterstaff",
        title="Quarterstaff",
        metadata={"weapon_category": "simple", "weapon_type": "M", "damage": "1d6", "properties": ["V"]},
        rendered_html="<p>API linked quarterstaff detail.</p>",
    )
    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-api-linked-detail",
        title="API Detail Spell",
        metadata={"level": 1, "school": "evocation"},
        rendered_html="<p>API linked spell detail.</p>",
    )

    def _mutate_definition(payload: dict) -> None:
        linked_item = False
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item in enumerate(equipment_catalog):
            item_payload = dict(item or {})
            if str(item_payload.get("id") or "").strip() != "quarterstaff-2":
                continue
            equipment_catalog[index] = {
                **item_payload,
                "name": "Quarterstaff",
                "systems_ref": _systems_ref(item_entry),
            }
            linked_item = True
        assert linked_item
        payload["equipment_catalog"] = equipment_catalog

        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {
            **dict(spells[0] or {}),
            "name": "API Detail Spell",
            "systems_ref": _systems_ref(spell_entry),
            "casting_time": "1 action",
            "range": "60 feet",
            "duration": "Instantaneous",
            "components": "V, S",
            "save_or_hit": "Dex save",
        }
        spellcasting["spells"] = spells
        spellcasting["spells"][0]["at_higher_levels"] = "At higher levels, the spell deals +1d8 healing per spell slot above 1st."
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", _mutate_definition)
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-linked-details-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    character = response.get_json()["character"]
    quarterstaff = {item["id"]: item for item in character["equipment_state"]["rows"]}["quarterstaff-2"]
    assert quarterstaff["href"].endswith("/systems/entries/phb-item-api-linked-quarterstaff")
    assert "API linked quarterstaff detail" in quarterstaff["description_html"]

    inventory_quarterstaff = {
        item["item_ref"]: item for item in character["presented_inventory"]
    }["quarterstaff-2"]
    assert inventory_quarterstaff["href"].endswith("/systems/entries/phb-item-api-linked-quarterstaff")
    assert "API linked quarterstaff detail" in inventory_quarterstaff["description_html"]

    def _find_presented_spell(payload: dict, spell_name: str) -> dict:
        spellcasting_payload = dict(payload.get("presented_spellcasting") or {})
        for section_key in ("current_row_sections", "row_sections", "preparation_row_sections"):
            for section in list(spellcasting_payload.get(section_key) or []):
                for spell in list(dict(section or {}).get("spells") or []):
                    if str(dict(spell).get("name") or "").strip() == spell_name:
                        return dict(spell)
                for level_section in list(dict(section or {}).get("spell_level_sections") or []):
                    for group in list(dict(level_section or {}).get("groups") or []):
                        for spell in list(dict(group or {}).get("spells") or []):
                            if str(dict(spell).get("name") or "").strip() == spell_name:
                                return dict(spell)
        raise AssertionError(f"Presented spell {spell_name!r} was not found.")

    detail_spell = _find_presented_spell(character, "API Detail Spell")
    assert detail_spell["href"].endswith("/systems/entries/phb-spell-api-linked-detail")
    assert "API linked spell detail" in detail_spell["description_html"]
    assert detail_spell["school"] == "Evocation"
    assert detail_spell["at_higher_levels"] == "At higher levels, the spell deals +1d8 healing per spell slot above 1st."
    assert detail_spell["is_upcastable"] is True


def test_api_character_detail_exposes_optional_higher_level_text_only_when_present(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    upcast_spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-api-upcast-detail",
        title="API Upcast Detail",
        metadata={
            "level": 1,
            "school": "evocation",
            "entries_higher_level": "At higher levels, the spell deals more damage.",
        },
        rendered_html="<p>API upcast detail spell.</p>",
    )
    base_spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-api-base-detail",
        title="API Base Detail",
        metadata={"level": 1, "school": "evocation"},
        rendered_html="<p>API base spell detail.</p>",
    )

    def _mutate_definition(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spellcasting["spells"] = [
            {
                "name": "API Upcast Detail",
                "systems_ref": _systems_ref(upcast_spell_entry),
                "casting_time": "1 action",
                "range": "Touch",
                "duration": "Instantaneous",
                "components": "V, S",
                "save_or_hit": "",
            },
            {
                "name": "API Base Detail",
                "systems_ref": _systems_ref(base_spell_entry),
                "casting_time": "1 action",
                "range": "Touch",
                "duration": "Instantaneous",
                "components": "V, S",
                "save_or_hit": "",
            },
        ]
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", _mutate_definition)
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-upcast-detail-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    character = response.get_json()["character"]

    def _find_presented_spell(payload: dict, spell_name: str) -> dict:
        spellcasting_payload = dict(payload.get("presented_spellcasting") or {})
        for section_key in ("current_row_sections", "row_sections", "preparation_row_sections"):
            for section in list(spellcasting_payload.get(section_key) or []):
                for spell in list(dict(section or {}).get("spells") or []):
                    if str(dict(spell).get("name") or "").strip() == spell_name:
                        return dict(spell)
                for level_section in list(dict(section or {}).get("spell_level_sections") or []):
                    for group in list(dict(level_section or {}).get("groups") or []):
                        for spell in list(dict(group or {}).get("spells") or []):
                            if str(dict(spell).get("name") or "").strip() == spell_name:
                                return dict(spell)
        raise AssertionError(f"Presented spell {spell_name!r} was not found.")

    upcast_spell = _find_presented_spell(character, "API Upcast Detail")
    non_upcast_spell = _find_presented_spell(character, "API Base Detail")
    assert upcast_spell["at_higher_levels"] == "At higher levels, the spell deals more damage."
    assert upcast_spell["is_upcastable"] is True
    assert "at_higher_levels" not in non_upcast_spell
    assert non_upcast_spell["is_upcastable"] is False


def test_api_character_session_equipment_state_endpoint_preserves_attunement_limit(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    item_ids = ["light-crossbow-1", "quarterstaff-2", "satchel-3", "crossbow-bolts-4"]
    entries = [
        _seed_systems_item_entry(
            app,
            slug=f"phb-item-api-attuned-relic-{index}",
            title=f"Attuned Relic {index}",
            metadata={"rarity": "rare", "attunement": "requires attunement"},
        )
        for index in range(1, 5)
    ]

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item_id in enumerate(item_ids):
            equipment_catalog[index] = {
                **dict(equipment_catalog[index]),
                "id": item_id,
                "name": f"Attuned Relic {index + 1}",
                "systems_ref": _systems_ref(entries[index]),
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item_id in enumerate(item_ids):
            inventory[index] = {
                **dict(inventory[index]),
                "id": item_id,
                "catalog_ref": item_id,
                "name": f"Attuned Relic {index + 1}",
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": item_ids[:3]}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-equipment-attunement-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]

    response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/crossbow-bolts-4",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "is_equipped": True,
            "is_attuned": True,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert "already has 3 attuned items" in response.get_json()["error"]["message"]


def test_api_character_session_feature_state_endpoint_updates_arcane_armor(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    def _mutate_definition(payload: dict) -> None:
        features = list(payload.get("features") or [])
        features.append({"name": "Arcane Armor", "description_markdown": "Armor model controls."})
        payload["features"] = features

    def _mutate_state(payload: dict) -> None:
        payload["feature_states"] = {"arcane_armor": {"enabled": False}}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-feature-state-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    assert character["arcane_armor_state"]["available"] is True
    assert character["arcane_armor_state"]["enabled"] is False

    response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/feature-states/arcane_armor",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "enabled": True,
        },
    )

    assert response.status_code == 200
    updated_character = response.get_json()["character"]
    assert updated_character["state_record"]["state"]["feature_states"]["arcane_armor"]["enabled"] is True
    assert updated_character["arcane_armor_state"]["enabled"] is True


def test_api_character_list_derives_multiclass_summary_from_class_rows(client, app, users):
    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 3"
        profile["classes"] = [
            {
                "class_name": "Fighter",
                "subclass_name": "",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|fighter",
                    "entry_type": "class",
                    "title": "Fighter",
                    "slug": "phb-class-fighter",
                    "source_id": "PHB",
                },
            },
            {
                "class_name": "Wizard",
                "subclass_name": "",
                "level": 2,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|wizard",
                    "entry_type": "class",
                    "title": "Wizard",
                    "slug": "phb-class-wizard",
                    "source_id": "PHB",
                },
            },
        ]
        payload["profile"] = profile

    _write_character_definition(app, "tobin-slate", _mutate)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-list-api")

    response = client.get("/api/v1/campaigns/linden-pass/characters", headers=api_headers(dm_token))

    assert response.status_code == 200
    payload = response.get_json()
    tobin = next(character for character in payload["characters"] if character["slug"] == "tobin-slate")
    assert tobin["class_level_text"] == "Fighter 3 / Wizard 2"


def test_api_character_roster_exposes_flask_links_search_and_portraits(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")

    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    portrait_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.png"
    )
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait_path.write_bytes(tiny_png)

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile.update(
            {
                "portrait_asset_ref": "characters/arden-march/portrait.png",
                "portrait_alt": "Arden portrait",
                "portrait_caption": "Shown on the Flask sheet.",
            }
        )
        payload["profile"] = profile

    _write_character_definition(app, "arden-march", _mutate)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters?q=arden",
        headers=api_headers(dm_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["query"] == "arden"
    assert payload["result_count"] == 1
    assert payload["tools"]["can_create_characters"] is True
    assert payload["links"]["flask_roster_url"] == "/campaigns/linden-pass/characters"
    assert payload["links"]["roster_url"] == "/campaigns/linden-pass/characters"
    assert payload["links"]["create_character_url"] == "/campaigns/linden-pass/characters/new"
    assert payload["links"]["flask_create_character_url"] == "/campaigns/linden-pass/characters/new"
    arden = payload["characters"][0]
    assert arden["slug"] == "arden-march"
    assert arden["href"] == "/campaigns/linden-pass/characters/arden-march"
    assert arden["flask_href"] == "/campaigns/linden-pass/characters/arden-march"
    assert arden["portrait"]["url"] == "/campaigns/linden-pass/characters/arden-march/portrait"
    assert arden["portrait"]["alt_text"] == "Arden portrait"
    assert arden["portrait"]["caption"] == "Shown on the Flask sheet."
    assert arden["hit_dice"]["value"]
    assert isinstance(arden["resource_preview"], list)

    portrait_response = client.get(arden["portrait"]["url"], headers=api_headers(dm_token))
    assert portrait_response.status_code == 200
    assert portrait_response.mimetype == "image/png"

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["character"]["portrait"]["url"] == arden["portrait"]["url"]
    assert detail_payload["character"]["permissions"]["can_use_controls"] is True
    assert detail_payload["character"]["controls"]["available"] is True
    assert detail_payload["character"]["controls"]["assignment"]["display_name"] == "Owner Player"
    assert detail_payload["character"]["controls"]["can_delete_character"] is True
    assert detail_payload["character"]["controls"]["can_assign_owner"] is False
    assert detail_payload["links"]["flask_character_url"] == "/campaigns/linden-pass/characters/arden-march"
    assert detail_payload["links"]["advanced_editor_url"] == "/campaigns/linden-pass/characters/arden-march/edit"
    assert detail_payload["links"]["flask_advanced_editor_url"] == "/campaigns/linden-pass/characters/arden-march/edit"


def test_api_character_detail_serializer_exposes_presenter_parity_payload_fields(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-detail-parity-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    character = response.get_json()["character"]

    assert isinstance(character["overview_stat_rows"], list)
    assert character["overview_stat_rows"]
    assert all(isinstance(row, list) for row in character["overview_stat_rows"])
    assert any(
        isinstance(stat, dict) and "label" in stat and "value" in stat for row in character["overview_stat_rows"] for stat in row
    )
    assert isinstance(character["overview_stats"], list)
    assert all(isinstance(stat, dict) for stat in character["overview_stats"])

    assert "player_notes_markdown" in character
    assert "player_notes_html" in character
    assert isinstance(character["player_notes_markdown"], str)
    assert isinstance(character["player_notes_html"], str)
    assert isinstance(character["reference_sections"], list)
    assert isinstance(character["physical_description_markdown"], str)
    assert isinstance(character["physical_description_html"], str)
    assert isinstance(character["personal_background_markdown"], str)
    assert isinstance(character["personal_background_html"], str)
    assert isinstance(character["abilities"], list)
    assert isinstance(character["skills"], list)
    assert isinstance(character["proficiency_groups"], list)


def test_api_character_advanced_editor_context_save_and_access(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-editor-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-editor-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-editor-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["links"]["advanced_editor_url"] == "/campaigns/linden-pass/characters/arden-march/edit"
    assert payload["links"]["flask_advanced_editor_url"] == "/campaigns/linden-pass/characters/arden-march/edit"
    editor = payload["editor"]
    assert editor["state_revision"] == payload["character"]["state_record"]["revision"]
    assert [field["name"] for field in editor["reference_fields"]][:2] == [
        "physical_description_markdown",
        "background_markdown",
    ]
    assert editor["feature_rows"]
    assert editor["equipment_rows"]

    owner_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(owner_token),
    )
    assert owner_response.status_code == 200
    assert owner_response.get_json()["supported"] is True

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    values = _advanced_editor_values(editor)
    values["physical_description_markdown"] = "Flask physical reference text."
    values["biography_markdown"] = "Flask biography reference text."
    values["stat_adjustment_speed"] = "5"
    update_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
        json={"expected_revision": editor["state_revision"], "values": values},
    )

    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"] == "Character details updated."
    assert updated_payload["editor"]["state_revision"] == editor["state_revision"] + 1
    assert updated_payload["character"]["definition"]["profile"]["biography_markdown"] == "Flask biography reference text."
    assert updated_payload["character"]["state_record"]["state"]["notes"]["physical_description_markdown"] == (
        "Flask physical reference text."
    )
    assert updated_payload["character"]["definition"]["stats"]["manual_adjustments"]["speed"] == 5

    stale_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
        json={"expected_revision": editor["state_revision"], "values": values},
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_retraining_context_save_and_access(client, app, users, set_campaign_visibility):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-drill.md"
    )
    feat_page_path.write_text(
        """---
title: Harbor Drill
section: Mechanics
subsection: Feats
published: true
summary: A harbor discipline that grants a fighting style.
character_option:
  kind: feat
  name: Harbor Drill
  description_markdown: Harbor veterans drill you into a practiced fighting style.
  optionalfeature_progression:
    - name: Fighting Style
      featureType:
        - FS:F
      progression:
        "1": 1
---
The harbor masters insist on repetition until every motion is clean.
""",
        encoding="utf-8",
    )

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
            entry_types=["optionalfeature"],
            entries=[
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|archery",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-archery",
                    "title": "Archery",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "archery fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Archery.</p>",
                },
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|defense",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-defense",
                    "title": "Defense",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "defense fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Defense.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-retraining-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-retraining-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-retraining-api")

    editor_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
    )
    assert editor_response.status_code == 200
    editor = editor_response.get_json()["editor"]
    editor_values = _advanced_editor_values(editor)
    editor_values.update(
        {
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-drill",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            "custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-archery",
        }
    )
    add_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
        json={"expected_revision": editor["state_revision"], "values": editor_values},
    )
    assert add_response.status_code == 200
    assert add_response.get_json()["links"]["retraining_url"] == (
        "/campaigns/linden-pass/characters/arden-march/retraining"
    )

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )
    assert detail_response.status_code == 200
    detail_links = detail_response.get_json()["links"]
    assert detail_links["retraining_url"] == "/campaigns/linden-pass/characters/arden-march/retraining"
    assert detail_links["flask_retraining_url"] == "/campaigns/linden-pass/characters/arden-march/retraining"

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["links"]["retraining_url"] == "/campaigns/linden-pass/characters/arden-march/retraining"
    assert payload["links"]["flask_retraining_url"] == "/campaigns/linden-pass/characters/arden-march/retraining"
    retraining = payload["retraining"]
    assert retraining["state_revision"] == payload["character"]["state_record"]["revision"]
    assert "retraining_context" not in payload["readiness"]
    row = next(
        row
        for row in retraining["feature_rows"]
        if any(field.get("name") == "custom_feature_optionalfeature_1_1_1" for field in row.get("choice_fields", []))
    )
    assert row["name"] == "Harbor Drill"
    choice_field = next(field for field in row["choice_fields"] if field["name"] == "custom_feature_optionalfeature_1_1_1")
    assert choice_field["name"] == "custom_feature_optionalfeature_1_1_1"
    assert choice_field["selected"] == "phb-optionalfeature-archery"

    owner_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(owner_token),
    )
    assert owner_response.status_code == 200
    assert owner_response.get_json()["supported"] is True

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    update_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
        json={
            "expected_revision": retraining["state_revision"],
            "values": {"custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-defense"},
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"] == "Retraining saved."
    assert updated_payload["character"]["state_record"]["revision"] == retraining["state_revision"] + 1

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
    assert record is not None
    feature_slugs = {
        str(dict(feature.get("systems_ref") or {}).get("slug") or "").strip()
        for feature in record.definition.features
    }
    retrained_crossbow = next(attack for attack in record.definition.attacks if "Crossbow" in attack["name"])
    latest_event = list((record.definition.source or {}).get("native_progression", {}).get("history") or [])[-1]
    assert "phb-optionalfeature-archery" not in feature_slugs
    assert "phb-optionalfeature-defense" in feature_slugs
    assert retrained_crossbow["attack_bonus"] == 5
    assert latest_event["action"] == "retrain"
    assert latest_event["kind"] == "retrain"

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
        json={
            "expected_revision": retraining["state_revision"],
            "values": {"custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-defense"},
        },
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_level_up_context_save_and_access(client, app, users, set_campaign_visibility, monkeypatch):
    set_campaign_visibility("linden-pass", characters="dm", session="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-level-up-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-level-up-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-level-up-api")

    def _ready_level_up(*_args, **_kwargs):
        return {
            "status": "ready",
            "message": "",
            "current_level": 5,
            "selected_class_rows": [
                {
                    "row_id": "class-row-1",
                    "row_level": 5,
                    "class_payload": {"class_name": "Sorcerer", "level": 5},
                }
            ],
        }

    def _level_up_context(_systems_service, campaign_slug, definition, form_values=None, **_kwargs):
        values = {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-1",
            "hp_gain": str(dict(form_values or {}).get("hp_gain") or ""),
        }
        return {
            "values": values,
            "character_name": definition.name,
            "current_level": 5,
            "next_level": 6,
            "campaign_slug": campaign_slug,
            "advancement_mode": "advance_existing",
            "mode_options": [{"value": "advance_existing", "label": "Advance existing class"}],
            "can_add_class": False,
            "current_class_rows": ["Sorcerer 5"],
            "target_row_options": [{"value": "class-row-1", "label": "Sorcerer 5"}],
            "target_class_row_id": "class-row-1",
            "row_current_level": 5,
            "row_target_level": 6,
            "new_class_options": [],
            "new_subclass_options": [],
            "multiclass_requirement_text": "",
            "multiclass_requirements_met": True,
            "subclass_options": [],
            "requires_subclass": False,
            "choice_sections": [],
            "limitations": ["Fixture level-up boundary."],
            "preview": {
                "class_level_text": "Sorcerer 6",
                "class_rows": ["Sorcerer 6"],
                "max_hp": 43,
                "gained_features": ["Font of Magic scaling"],
                "resources": ["Sorcery Points: 6"],
                "attacks": [],
                "spell_slots": [],
                "new_spells": [],
            },
            "field_live_preview": {},
            "preview_region_ids": [],
            "live_region_ids": [],
        }

    def _apply_level_up(_campaign_slug, current_definition, _level_up_context, form_values=None, **kwargs):
        payload = current_definition.to_dict()
        profile = dict(payload.get("profile") or {})
        classes = [dict(row or {}) for row in list(profile.get("classes") or [])]
        if classes:
            classes[0]["level"] = 6
        profile["classes"] = classes
        profile["class_level_text"] = "Sorcerer 6"
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        stats["max_hp"] = 43
        payload["stats"] = stats
        return CharacterDefinition.from_dict(payload), kwargs.get("current_import_metadata"), int(
            dict(form_values or {}).get("hp_gain") or 0
        )

    monkeypatch.setattr(api_module, "native_level_up_readiness", _ready_level_up)
    monkeypatch.setattr(api_module, "build_native_level_up_context", _level_up_context)
    monkeypatch.setattr(api_module, "build_native_level_up_character_definition", _apply_level_up)

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )
    assert detail_response.status_code == 200
    detail_links = detail_response.get_json()["links"]
    assert detail_links["level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    assert detail_links["flask_level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"

    owner_detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )
    assert owner_detail_response.status_code == 200
    owner_detail_links = owner_detail_response.get_json()["links"]
    assert owner_detail_links["level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    assert owner_detail_links["flask_level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    assert "advanced_editor_url" not in owner_detail_links
    assert "progression_repair_url" not in owner_detail_links

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up?hp_gain=5",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["links"]["level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    assert payload["links"]["flask_level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    level_up = payload["level_up"]
    assert level_up["state_revision"] == payload["character"]["state_record"]["revision"]
    assert level_up["current_level"] == 5
    assert level_up["next_level"] == 6
    assert level_up["values"]["hp_gain"] == "5"
    assert level_up["preview"]["class_level_text"] == "Sorcerer 6"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    update_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(owner_token),
        json={"expected_revision": level_up["state_revision"], "values": {"hp_gain": "5"}},
    )

    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"] == "Arden March advanced to level 6."
    assert updated_payload["character"]["definition"]["profile"]["class_level_text"] == "Sorcerer 6"
    assert updated_payload["character"]["state_record"]["revision"] == level_up["state_revision"] + 1
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    saved_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    assert saved_definition["profile"]["class_level_text"] == "Sorcerer 6"

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(owner_token),
        json={"expected_revision": level_up["state_revision"], "values": {"hp_gain": "5"}},
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_progression_repair_context_save_and_access(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-repair-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-repair-api")

    def _repairable_readiness(*_args, **_kwargs):
        return {
            "status": "repairable",
            "message": "This imported character needs a quick progression repair before native level-up.",
            "reasons": [
                "Choose a supported base class link for this character.",
                "Classify the current imported spell rows so native spell progression can trust them.",
            ],
        }

    def _repair_context(_systems_service, _campaign_slug, definition, form_values=None, **_kwargs):
        values = {
            "repair_class_slug_class-row-1": str(dict(form_values or {}).get("repair_class_slug_class-row-1") or ""),
            "repair_subclass_slug_class-row-1": str(
                dict(form_values or {}).get("repair_subclass_slug_class-row-1") or ""
            ),
            "repair_species_slug": str(dict(form_values or {}).get("repair_species_slug") or ""),
            "repair_background_slug": str(dict(form_values or {}).get("repair_background_slug") or ""),
            "repair_feat_1": str(dict(form_values or {}).get("repair_feat_1") or ""),
            "repair_spell_mark_1": str(dict(form_values or {}).get("repair_spell_mark_1") or ""),
            "repair_spell_class_row_1": str(dict(form_values or {}).get("repair_spell_class_row_1") or ""),
        }
        return {
            "values": values,
            "character_name": definition.name,
            "current_level": 5,
            "readiness": _repairable_readiness(),
            "class_rows": [
                {
                    "row_id": "class-row-1",
                    "row_level": 5,
                    "class_name": "Imported Sorcerer",
                    "class_field_name": "repair_class_slug_class-row-1",
                    "class_selected": values["repair_class_slug_class-row-1"],
                    "class_options": [{"value": "systems:sorcerer", "label": "Sorcerer"}],
                    "subclass_field_name": "repair_subclass_slug_class-row-1",
                    "subclass_selected": values["repair_subclass_slug_class-row-1"],
                    "subclass_options": [{"value": "systems:draconic-bloodline", "label": "Draconic Bloodline"}],
                }
            ],
            "species_options": [{"value": "systems:human", "label": "Human"}],
            "background_options": [{"value": "systems:acolyte", "label": "Acolyte"}],
            "feat_rows": [
                {
                    "index": 1,
                    "name": "repair_feat_1",
                    "selected": values["repair_feat_1"],
                    "options": [{"value": "systems:lucky", "label": "Lucky"}],
                }
            ],
            "optionalfeature_rows": [],
            "spell_rows": [
                {
                    "name": "Fire Bolt",
                    "field_name": "repair_spell_mark_1",
                    "selected": values["repair_spell_mark_1"],
                    "options": [{"value": "known", "label": "Known"}],
                    "class_row_field_name": "repair_spell_class_row_1",
                    "class_row_selected": values["repair_spell_class_row_1"],
                    "class_row_options": [{"value": "class-row-1", "label": "Imported Sorcerer 5"}],
                }
            ],
            "class_entries": [],
            "species_entries": [],
            "background_entries": [],
            "subclass_entries": [],
            "feat_entries": [],
            "optionalfeature_entries": [],
        }

    def _apply_repair(_campaign_slug, current_definition, current_import_metadata, _repair_context, form_values):
        assert dict(form_values).get("repair_class_slug_class-row-1") == "systems:sorcerer"
        payload = current_definition.to_dict()
        source = dict(payload.get("source") or {})
        native_progression = dict(source.get("native_progression") or {})
        native_progression["baseline_repaired_at"] = "2026-06-05T00:00:00Z"
        native_progression["history"] = list(native_progression.get("history") or []) + [
            {"kind": "repair", "action": "repair", "target_level": 5}
        ]
        source["native_progression"] = native_progression
        payload["source"] = source
        return CharacterDefinition.from_dict(payload), current_import_metadata

    monkeypatch.setattr(api_module, "native_level_up_readiness", _repairable_readiness)
    monkeypatch.setattr(api_module, "build_imported_progression_repair_context", _repair_context)
    monkeypatch.setattr(api_module, "apply_imported_progression_repairs", _apply_repair)

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )
    assert detail_response.status_code == 200
    detail_links = detail_response.get_json()["links"]
    assert detail_links["progression_repair_url"] == (
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    assert detail_links["flask_progression_repair_url"] == (
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )

    level_up_repairable_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(dm_token),
    )
    assert level_up_repairable_response.status_code == 200
    level_up_repairable_payload = level_up_repairable_response.get_json()
    assert level_up_repairable_payload["supported"] is False
    assert level_up_repairable_payload["lane"] == "repairable"
    assert level_up_repairable_payload["links"]["progression_repair_url"] == (
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )

    retraining_repairable_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
    )
    assert retraining_repairable_response.status_code == 200
    retraining_repairable_payload = retraining_repairable_response.get_json()
    assert retraining_repairable_payload["supported"] is False
    assert retraining_repairable_payload["lane"] == "repairable"
    assert retraining_repairable_payload["links"]["progression_repair_url"] == (
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(dm_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "repairable"
    assert payload["links"]["progression_repair_url"] == (
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    repair = payload["repair"]
    assert repair["state_revision"] == payload["character"]["state_record"]["revision"]
    assert repair["class_rows"][0]["class_field_name"] == "repair_class_slug_class-row-1"
    assert repair["species_options"][0]["label"] == "Human"
    assert repair["spell_rows"][0]["field_name"] == "repair_spell_mark_1"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    update_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(dm_token),
        json={
            "expected_revision": repair["state_revision"],
            "values": {
                "repair_class_slug_class-row-1": "systems:sorcerer",
                "repair_subclass_slug_class-row-1": "systems:draconic-bloodline",
                "repair_species_slug": "systems:human",
                "repair_background_slug": "systems:acolyte",
                "repair_feat_1": "systems:lucky",
                "repair_spell_mark_1": "known",
                "repair_spell_class_row_1": "class-row-1",
            },
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"].startswith("Progression repair saved")
    assert updated_payload["character"]["state_record"]["revision"] == repair["state_revision"] + 1

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    saved_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    latest_event = saved_definition["source"]["native_progression"]["history"][-1]
    assert latest_event["kind"] == "repair"
    assert latest_event["target_level"] == 5

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(dm_token),
        json={
            "expected_revision": repair["state_revision"],
            "values": {"repair_class_slug_class-row-1": "systems:sorcerer"},
        },
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_create_context_uses_flask_links_and_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-create-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-character-create-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(dm_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["lane"] == "dnd5e"
    assert payload["create"]["lane"] == "dnd5e"
    assert payload["links"]["create_character_url"] == "/campaigns/linden-pass/characters/new"
    assert payload["links"]["flask_create_character_url"] == "/campaigns/linden-pass/characters/new"
    assert payload["links"]["flask_create_url"] == "/campaigns/linden-pass/characters/new"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(player_token),
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    anonymous_response = client.get("/api/v1/campaigns/linden-pass/characters/create")

    assert anonymous_response.status_code == 401
    assert anonymous_response.get_json()["error"]["code"] == "auth_required"


def test_api_xianxia_create_manual_import_and_cultivation_write_native_records(
    client,
    app,
    users,
    set_campaign_visibility,
):
    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-authoring-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-xianxia-authoring-api")

    context_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(dm_token),
    )

    assert context_response.status_code == 200
    context_payload = context_response.get_json()
    assert context_payload["lane"] == "xianxia"
    assert context_payload["create"]["lane"] == "xianxia"
    assert context_payload["links"]["create_character_url"] == "/campaigns/linden-pass/characters/new"
    assert context_payload["links"]["import_xianxia_url"] == "/campaigns/linden-pass/characters/import/xianxia-manual"
    assert context_payload["links"]["flask_import_xianxia_url"] == "/campaigns/linden-pass/characters/import/xianxia-manual"

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(dm_token),
        json={"values": _valid_xianxia_create_data("Flask Crane", slug="flask-crane")},
    )

    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    assert create_payload["message"] == "Flask Crane created."
    assert create_payload["links"]["character_url"] == "/campaigns/linden-pass/characters/flask-crane"
    created_definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "flask-crane"
        / "definition.yaml"
    )
    created_definition = yaml.safe_load(created_definition_path.read_text(encoding="utf-8"))
    assert created_definition["system"] == "Xianxia"
    assert created_definition["xianxia"]["realm"] == "Mortal"

    unsupported_editor_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/advanced-editor",
        headers=api_headers(dm_token),
    )

    assert unsupported_editor_response.status_code == 200
    unsupported_editor_payload = unsupported_editor_response.get_json()
    assert unsupported_editor_payload["supported"] is False
    assert unsupported_editor_payload["lane"] == "unsupported"
    assert unsupported_editor_payload["editor"] is None
    assert unsupported_editor_payload["links"]["cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )
    assert unsupported_editor_payload["links"]["flask_cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )

    unsupported_level_up_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/level-up",
        headers=api_headers(dm_token),
    )
    assert unsupported_level_up_response.status_code == 200
    unsupported_level_up_payload = unsupported_level_up_response.get_json()
    assert unsupported_level_up_payload["supported"] is False
    assert unsupported_level_up_payload["lane"] == "unsupported"
    assert unsupported_level_up_payload["level_up"] is None
    assert unsupported_level_up_payload["links"]["cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )

    unsupported_retraining_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/retraining",
        headers=api_headers(dm_token),
    )
    assert unsupported_retraining_response.status_code == 200
    unsupported_retraining_payload = unsupported_retraining_response.get_json()
    assert unsupported_retraining_payload["supported"] is False
    assert unsupported_retraining_payload["lane"] == "unsupported"
    assert unsupported_retraining_payload["retraining"] is None
    assert unsupported_retraining_payload["links"]["cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )
    assert unsupported_retraining_payload["links"]["flask_cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )

    unsupported_repair_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/progression-repair",
        headers=api_headers(dm_token),
    )
    assert unsupported_repair_response.status_code == 200
    unsupported_repair_payload = unsupported_repair_response.get_json()
    assert unsupported_repair_payload["supported"] is False
    assert unsupported_repair_payload["lane"] == "unsupported"
    assert unsupported_repair_payload["repair"] is None
    assert unsupported_repair_payload["links"]["cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )

    blocked_level_up_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/level-up",
        headers=api_headers(player_token),
    )
    assert blocked_level_up_response.status_code == 403
    assert blocked_level_up_response.get_json()["error"]["code"] == "forbidden"

    blocked_retraining_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/retraining",
        headers=api_headers(player_token),
    )
    assert blocked_retraining_response.status_code == 403
    assert blocked_retraining_response.get_json()["error"]["code"] == "forbidden"

    blocked_repair_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/progression-repair",
        headers=api_headers(player_token),
    )
    assert blocked_repair_response.status_code == 403
    assert blocked_repair_response.get_json()["error"]["code"] == "forbidden"

    cultivation_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/cultivation",
        headers=api_headers(dm_token),
    )
    assert cultivation_response.status_code == 200
    cultivation_payload = cultivation_response.get_json()
    assert cultivation_payload["supported"] is True
    assert cultivation_payload["lane"] == "xianxia"
    assert cultivation_payload["links"]["cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )
    assert cultivation_payload["links"]["flask_cultivation_url"] == (
        "/campaigns/linden-pass/characters/flask-crane/cultivation"
    )
    assert cultivation_payload["cultivation"]["insight"]["available"] == 0
    cultivation_revision = cultivation_payload["character"]["state_record"]["revision"]

    blocked_cultivation_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/cultivation",
        headers=api_headers(player_token),
    )
    assert blocked_cultivation_response.status_code == 403
    assert blocked_cultivation_response.get_json()["error"]["code"] == "forbidden"

    def _mark_arden_dnd(payload: dict) -> None:
        payload["system"] = "DND-5E"

    _write_character_definition(app, "arden-march", _mark_arden_dnd)
    unsupported_cultivation_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/cultivation",
        headers=api_headers(dm_token),
    )
    assert unsupported_cultivation_response.status_code == 200
    unsupported_cultivation_payload = unsupported_cultivation_response.get_json()
    assert unsupported_cultivation_payload["supported"] is False
    assert unsupported_cultivation_payload["lane"] == "unsupported"
    assert unsupported_cultivation_payload["cultivation"] is None

    insight_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/cultivation",
        headers=api_headers(dm_token),
        json={
            "expected_revision": cultivation_revision,
            "action": "save_insight",
            "values": {
                "insight_available": "3",
                "insight_spent": "1",
            },
        },
    )
    assert insight_response.status_code == 200
    insight_payload = insight_response.get_json()
    assert insight_payload["message"] == "Insight counters saved."
    assert insight_payload["cultivation"]["insight"]["available"] == 3
    assert insight_payload["cultivation"]["insight"]["spent"] == 1
    assert insight_payload["character"]["state_record"]["revision"] == cultivation_revision + 1
    updated_definition = yaml.safe_load(created_definition_path.read_text(encoding="utf-8"))
    assert updated_definition["xianxia"]["insight"] == {"available": 3, "spent": 1}
    assert updated_definition["xianxia"]["advancement_history"][-1]["action"] == "insight_counter_adjustment"

    stale_cultivation_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/flask-crane/cultivation",
        headers=api_headers(dm_token),
        json={
            "expected_revision": cultivation_revision,
            "action": "record_gathering_insight",
            "values": {
                "insight_gain_amount": "1",
                "gathering_insight_downtime": "A quiet week",
            },
        },
    )
    assert stale_cultivation_response.status_code == 409
    assert stale_cultivation_response.get_json()["error"]["code"] == "state_conflict"

    import_values = _valid_xianxia_manual_import_data("Flask Imported Lotus", slug="flask-imported-lotus")
    preview_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
        headers=api_headers(dm_token),
        json={"values": import_values},
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.get_json()
    assert preview_payload["message"] == "Review the imported sheet summary, then confirm to create the character."
    assert preview_payload["import_context"]["preview"]["name"] == "Flask Imported Lotus"
    preview_definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "flask-imported-lotus"
        / "definition.yaml"
    )
    assert not preview_definition_path.exists()

    confirm_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
        headers=api_headers(dm_token),
        json={"values": import_values, "confirm_import": True},
    )

    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.get_json()
    assert confirm_payload["message"] == "Flask Imported Lotus imported."
    assert confirm_payload["links"]["character_url"] == "/campaigns/linden-pass/characters/flask-imported-lotus"
    imported_definition = yaml.safe_load(preview_definition_path.read_text(encoding="utf-8"))
    assert imported_definition["system"] == "Xianxia"
    assert imported_definition["source"]["source_path"] == "importer://xianxia-manual"


def test_api_character_controls_assignment_and_delete_use_flask_contract(client, app, users):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-character-controls-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-controls-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-character-controls-api")

    blocked_assign_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment",
        headers=api_headers(dm_token),
        json={"user_id": users["party"]["id"]},
    )

    assert blocked_assign_response.status_code == 403
    assert blocked_assign_response.get_json()["error"]["code"] == "forbidden"

    assign_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment",
        headers=api_headers(admin_token),
        json={"user_id": users["party"]["id"]},
    )

    assert assign_response.status_code == 200
    assigned_payload = assign_response.get_json()
    assert assigned_payload["message"] == "Assigned arden-march to party@example.com."
    assert assigned_payload["character"]["controls"]["assignment"]["display_name"] == "Party Player"
    assert assigned_payload["character"]["controls"]["can_assign_owner"] is True
    assert any(
        choice["user_id"] == users["party"]["id"] and choice["is_current"]
        for choice in assigned_payload["character"]["controls"]["player_choices"]
    )

    with app.app_context():
        store = AuthStore()
        assignment = store.get_character_assignment("linden-pass", "arden-march")
        assert assignment is not None
        assert assignment.user_id == users["party"]["id"]

    clear_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment",
        headers=api_headers(admin_token),
    )

    assert clear_response.status_code == 200
    assert clear_response.get_json()["character"]["controls"]["assignment"] is None

    with app.app_context():
        store = AuthStore()
        assert store.get_character_assignment("linden-pass", "arden-march") is None

    blocked_delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls",
        headers=api_headers(player_token),
        json={"confirm_character_slug": "arden-march"},
    )

    assert blocked_delete_response.status_code == 403
    assert blocked_delete_response.get_json()["error"]["code"] == "forbidden"

    invalid_delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls",
        headers=api_headers(dm_token),
        json={"confirm_character_slug": "not-arden-march"},
    )

    assert invalid_delete_response.status_code == 400
    assert invalid_delete_response.get_json()["error"]["message"] == "Type arden-march to confirm deletion."

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    assert definition_path.exists()

    delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls",
        headers=api_headers(dm_token),
        json={"confirm_character_slug": "arden-march"},
    )

    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["deleted_character_slug"] == "arden-march"
    assert delete_payload["links"]["roster_url"] == "/campaigns/linden-pass/characters"

    with app.app_context():
        store = AuthStore()
        state_store = app.extensions["character_state_store"]
        assert store.get_character_assignment("linden-pass", "arden-march") is None
        assert state_store.get_state("linden-pass", "arden-march") is None
    assert not definition_path.exists()


def test_api_character_portrait_upload_remove_uses_revisioned_contract(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    encoded_png = base64.b64encode(tiny_png).decode("ascii")
    portrait_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.webp"
    )
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-portrait-api")
    other_player_token = issue_api_token(app, users["party"]["email"], label="other-character-portrait-api")

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    starting_revision = detail_response.get_json()["character"]["state_record"]["revision"]

    upload_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(dm_token),
        json={
            "expected_revision": starting_revision,
            "portrait_file": {
                "filename": "updated-portrait.png",
                "data_base64": encoded_png,
                "media_type": "image/png",
            },
            "alt_text": "Arden updated portrait",
            "caption": "Uploaded through Flask.",
        },
    )

    assert upload_response.status_code == 200
    uploaded_character = upload_response.get_json()["character"]
    assert uploaded_character["state_record"]["revision"] == starting_revision + 1
    assert uploaded_character["portrait"]["asset_ref"] == "characters/arden-march/portrait.webp"
    assert uploaded_character["portrait"]["alt_text"] == "Arden updated portrait"
    assert uploaded_character["portrait"]["caption"] == "Uploaded through Flask."
    portrait_bytes = portrait_path.read_bytes()
    assert portrait_bytes[:4] == b"RIFF"
    assert portrait_bytes[8:12] == b"WEBP"
    profile = yaml.safe_load(definition_path.read_text(encoding="utf-8"))["profile"]
    assert profile["portrait_asset_ref"] == "characters/arden-march/portrait.webp"
    assert profile["portrait_alt"] == "Arden updated portrait"
    assert profile["portrait_caption"] == "Uploaded through Flask."

    portrait_response = client.get(uploaded_character["portrait"]["url"], headers=api_headers(dm_token))
    assert portrait_response.status_code == 200
    assert portrait_response.mimetype == "image/webp"
    portrait_response.close()

    stale_upload_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(dm_token),
        json={
            "expected_revision": starting_revision,
            "portrait_file": {
                "filename": "stale-portrait.png",
                "data_base64": encoded_png,
                "media_type": "image/png",
            },
        },
    )

    assert stale_upload_response.status_code == 409
    assert stale_upload_response.get_json()["error"]["code"] == "state_conflict"

    blocked_upload_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(other_player_token),
        json={
            "expected_revision": uploaded_character["state_record"]["revision"],
            "portrait_file": {
                "filename": "blocked.png",
                "data_base64": encoded_png,
                "media_type": "image/png",
            },
        },
    )

    assert blocked_upload_response.status_code == 403
    assert blocked_upload_response.get_json()["error"]["code"] == "forbidden"

    remove_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(dm_token),
        json={"expected_revision": uploaded_character["state_record"]["revision"]},
    )

    assert remove_response.status_code == 200
    removed_character = remove_response.get_json()["character"]
    assert removed_character["state_record"]["revision"] == starting_revision + 2
    assert removed_character["portrait"] is None
    assert not portrait_path.exists()
    profile = yaml.safe_load(definition_path.read_text(encoding="utf-8"))["profile"]
    assert "portrait_asset_ref" not in profile
    assert "portrait_alt" not in profile
    assert "portrait_caption" not in profile
