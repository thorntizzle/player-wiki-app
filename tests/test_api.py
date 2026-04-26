from __future__ import annotations

import base64
from copy import deepcopy
import json
from datetime import timedelta
from pathlib import Path
import zipfile

import yaml

from player_wiki.auth_store import AuthStore
from player_wiki.systems_importer import Dnd5eSystemsImporter
from player_wiki.xianxia_character_model import (
    XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION,
    XIANXIA_DEFINITION_FIELD_KEYS,
)


def api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def issue_api_token(app, user_email: str, *, label: str = "test-token") -> str:
    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_email(user_email)
        assert user is not None
        raw_token, _ = store.create_api_token(
            user.id,
            label=label,
            expires_in=timedelta(days=365),
        )
        return raw_token


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_character_definition(app, character_slug: str, mutator) -> None:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _import_systems_goblin(app, tmp_path) -> tuple[str, str]:
    data_root = tmp_path / "api-systems-dnd5e-source"
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
                            "entries": [
                                "{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."
                            ],
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
            if item.title == "Goblin"
        )
        return entry.entry_key, entry.slug


def _find_tracker_combatant(payload: dict[str, object], *, name: str | None = None, character_slug: str | None = None):
    for combatant in payload["tracker"]["combatants"]:
        if name is not None and combatant["name"] == name:
            return combatant
        if character_slug is not None and combatant["character_slug"] == character_slug:
            return combatant
    return None


def _build_systems_import_archive(tmp_path) -> bytes:
    data_root = tmp_path / "systems-import-archive"
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
                            "entries": [
                                "{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."
                            ],
                        }
                    ],
                }
            ]
        },
    )
    archive_path = tmp_path / "mm-import.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in data_root.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(data_root).as_posix())
    return archive_path.read_bytes()


def _build_unsafe_systems_import_archive(tmp_path) -> bytes:
    archive_path = tmp_path / "unsafe-systems-import.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../data/bestiary/bestiary-mm.json", "{}")
    return archive_path.read_bytes()


def test_api_me_and_campaigns_use_bearer_token_auth(client, app, users):
    token = issue_api_token(app, users["dm"]["email"], label="dm-api")

    me_response = client.get("/api/v1/me", headers=api_headers(token))

    assert me_response.status_code == 200
    me_payload = me_response.get_json()
    assert me_payload["ok"] is True
    assert me_payload["auth_source"] == "api_token"
    assert me_payload["user"]["email"] == users["dm"]["email"]

    campaigns_response = client.get("/api/v1/campaigns", headers=api_headers(token))

    assert campaigns_response.status_code == 200
    campaigns_payload = campaigns_response.get_json()
    assert campaigns_payload["campaigns"][0]["campaign"]["slug"] == "linden-pass"
    assert campaigns_payload["campaigns"][0]["role"] == "dm"

    with app.app_context():
        store = AuthStore()
        token_record = store.get_active_api_token(token)
        assert token_record is not None
        store.revoke_api_token(token_record.id)

    revoked_response = client.get("/api/v1/me", headers=api_headers(token))

    assert revoked_response.status_code == 401
    assert revoked_response.get_json()["error"]["code"] == "auth_required"


def test_api_session_endpoints_follow_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-api")

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))

    assert start_response.status_code == 200
    assert start_response.get_json()["session"]["is_active"] is True

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Sealed Orders",
            "body_markdown": "Deliver the crate to the eastern gate before moonrise.",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Sealed Orders"

    dm_session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert dm_session_response.status_code == 200
    dm_session_payload = dm_session_response.get_json()
    assert len(dm_session_payload["staged_articles"]) == 1
    assert dm_session_payload["staged_articles"][0]["title"] == "Sealed Orders"

    post_message_response = client.post(
        "/api/v1/campaigns/linden-pass/session/messages",
        headers=api_headers(player_token),
        json={"body": "We should check the contract before we sign anything."},
    )

    assert post_message_response.status_code == 200
    assert post_message_response.get_json()["message"]["author_display_name"] == "Party Player"

    player_before_reveal = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(player_token))

    assert player_before_reveal.status_code == 200
    player_before_payload = player_before_reveal.get_json()
    assert "staged_articles" not in player_before_payload
    assert all(message["article"] is None for message in player_before_payload["messages"])

    reveal_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles/1/reveal",
        headers=api_headers(dm_token),
    )

    assert reveal_response.status_code == 200
    assert reveal_response.get_json()["article"]["is_revealed"] is True

    player_after_reveal = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(player_token))

    assert player_after_reveal.status_code == 200
    player_after_payload = player_after_reveal.get_json()
    reveal_messages = [message for message in player_after_payload["messages"] if message["article"] is not None]
    assert len(reveal_messages) == 1
    assert reveal_messages[0]["article"]["title"] == "Sealed Orders"


def test_api_can_pull_visible_wiki_page_into_session_store(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-wiki-api")

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "wiki",
            "source_ref": "npcs/captain-lyra-vale",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Captain Lyra Vale"
    assert article_payload["body_format"] == "markdown"
    assert article_payload["source_kind"] == "page"
    assert article_payload["source_ref"] == "npcs/captain-lyra-vale"
    assert article_payload["source_page_ref"] == "npcs/captain-lyra-vale"
    assert article_payload["image"] is not None
    assert article_payload["image"]["filename"] == "captain-lyra-vale.png"
    assert article_payload["image"]["alt_text"] == "Portrait of Captain Lyra Vale."
    assert article_payload["image"]["caption"] == "Harbor watch captain and trusted ally of the crew."


def test_api_session_article_source_search_returns_wiki_pages_and_systems_entries(client, app, users, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-source-search-api")

    wiki_search = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers=api_headers(dm_token),
    )
    assert wiki_search.status_code == 200
    wiki_payload = wiki_search.get_json()
    assert wiki_payload["results"]
    captain_result = next(
        result for result in wiki_payload["results"] if result["source_ref"] == "npcs/captain-lyra-vale"
    )
    assert captain_result["source_kind"] == "page"

    systems_search = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=gob",
        headers=api_headers(dm_token),
    )
    assert systems_search.status_code == 200
    systems_payload = systems_search.get_json()
    assert systems_payload["results"]
    assert systems_payload["results"][0]["source_kind"] == "systems"
    assert systems_payload["results"][0]["source_ref"] == f"systems:{goblin_slug}"
    assert systems_payload["results"][0]["title"] == "Goblin"


def test_api_can_pull_visible_systems_entry_into_session_store(client, app, users, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-systems-api")

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "wiki",
            "source_ref": f"systems:{goblin_slug}",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Goblin"
    assert article_payload["body_format"] == "html"
    assert article_payload["source_kind"] == "systems"
    assert article_payload["source_ref"] == goblin_slug
    assert article_payload["source_page_ref"] == f"systems:{goblin_slug}"
    assert "Scimitar" in article_payload["body_markdown"]
    assert article_payload["image"] is None


def test_api_dm_content_endpoints_require_dm_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-dm-content-api")

    statblock_response = client.post(
        "/api/v1/campaigns/linden-pass/dm-content/statblocks",
        headers=api_headers(dm_token),
        json={
            "filename": "dock-runner.md",
            "subsection": "Malverine Minions",
            "markdown_text": (
                "# Dock Runner\n\n"
                "Armor Class 13\n"
                "Hit Points 22\n"
                "Speed 30 ft.\n\n"
                "DEX 14 (+2)\n"
            ),
        },
    )

    assert statblock_response.status_code == 200
    statblock_payload = statblock_response.get_json()["statblock"]
    assert statblock_payload["title"] == "Dock Runner"
    assert statblock_payload["subsection"] == "Malverine Minions"
    assert statblock_payload["parser_feedback"]["summary"] == (
        "Parsed combat fields: AC 13, HP 22, Speed 30 ft. (30 ft. movement), Init +2."
    )

    update_statblock_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/statblocks/{statblock_payload['id']}",
        headers=api_headers(dm_token),
        json={
            "subsection": "Dock Crew",
            "markdown_text": (
                "# Dock Runner Captain\n\n"
                "Armor Class 15\n"
                "Hit Points 36\n"
                "Speed 35 ft.\n\n"
                "DEX 16 (+3)\n"
            ),
        },
    )

    assert update_statblock_response.status_code == 200
    updated_statblock_payload = update_statblock_response.get_json()["statblock"]
    assert updated_statblock_payload["title"] == "Dock Runner Captain"
    assert updated_statblock_payload["subsection"] == "Dock Crew"
    assert updated_statblock_payload["max_hp"] == 36
    assert updated_statblock_payload["movement_total"] == 35
    assert updated_statblock_payload["initiative_bonus"] == 3
    assert updated_statblock_payload["parser_feedback"]["summary"] == (
        "Parsed combat fields: AC 15, HP 36, Speed 35 ft. (35 ft. movement), Init +3."
    )

    blocked_update_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/statblocks/{statblock_payload['id']}",
        headers=api_headers(player_token),
        json={"subsection": "Blocked"},
    )

    assert blocked_update_response.status_code == 403

    condition_response = client.post(
        "/api/v1/campaigns/linden-pass/dm-content/conditions",
        headers=api_headers(dm_token),
        json={
            "name": "Off Balance",
            "description_markdown": "The target has disadvantage on its next attack roll.",
        },
    )

    assert condition_response.status_code == 200
    condition_payload = condition_response.get_json()["condition"]
    assert condition_payload["name"] == "Off Balance"

    condition_update_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/conditions/{condition_payload['id']}",
        headers=api_headers(dm_token),
        json={
            "name": "Off Balance Revised",
            "description_markdown": "The target has disadvantage on its next Dexterity check.",
        },
    )

    assert condition_update_response.status_code == 200
    updated_condition_payload = condition_update_response.get_json()["condition"]
    assert updated_condition_payload["name"] == "Off Balance Revised"
    assert (
        updated_condition_payload["description_markdown"]
        == "The target has disadvantage on its next Dexterity check."
    )

    blocked_condition_update_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/conditions/{condition_payload['id']}",
        headers=api_headers(player_token),
        json={"name": "Blocked"},
    )

    assert blocked_condition_update_response.status_code == 403

    dm_content_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(dm_token))

    assert dm_content_response.status_code == 200
    dm_content_payload = dm_content_response.get_json()
    assert len(dm_content_payload["statblocks"]) == 1
    assert len(dm_content_payload["conditions"]) == 1
    assert dm_content_payload["statblocks"][0]["subsection"] == "Dock Crew"
    assert dm_content_payload["conditions"][0]["name"] == "Off Balance Revised"

    blocked_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(player_token))

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"


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

    personal_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/personal",
        headers=api_headers(owner_token),
        json={
            "expected_revision": updated_character["state_record"]["revision"],
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


def test_api_content_page_management_requires_dm_and_refreshes_repository(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-pages-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-content-pages-api")

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages",
        headers=api_headers(player_token),
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Field Report",
                "section": "Notes",
                "type": "note",
                "summary": "A published note created through the management API.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "The tower relay is stable, but the east pier wards are flickering.",
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.get_json()["page_file"]
    assert created_payload["page"]["title"] == "API Field Report"
    assert created_payload["page"]["route_slug"] == "notes/api-field-report"
    assert created_payload["page"]["is_visible"] is True

    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "api-field-report.md"
    assert page_path.exists()

    list_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages",
        headers=api_headers(dm_token),
    )

    assert list_response.status_code == 200
    page_refs = [item["page_ref"] for item in list_response.get_json()["pages"]]
    assert "notes/api-field-report" in page_refs

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    assert "east pier wards" in detail_response.get_json()["page_file"]["body_markdown"]

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        stored_page = campaign.pages.get("notes/api-field-report")
        assert stored_page is not None
        assert stored_page.title == "API Field Report"

    delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
    )

    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"]["page_ref"] == "notes/api-field-report"
    assert not page_path.exists()


def test_api_content_character_management_can_upsert_and_delete_files(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-characters-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-content-characters-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    source_character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"

    definition_payload = yaml.safe_load((source_character_dir / "definition.yaml").read_text(encoding="utf-8"))
    import_payload = yaml.safe_load((source_character_dir / "import.yaml").read_text(encoding="utf-8"))
    definition_payload["name"] = "API Scout"
    definition_payload["profile"]["biography_markdown"] = "A remotely managed scout prepared through the API."
    import_payload["source_path"] = "api://campaigns/linden-pass/characters/api-scout"
    import_payload["parser_version"] = "api-test"
    import_payload["import_status"] = "managed"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters",
        headers=api_headers(player_token),
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/api-scout",
        headers=api_headers(dm_token),
        json={
            "definition": definition_payload,
            "import_metadata": import_payload,
        },
    )

    assert create_response.status_code == 200
    character_file = create_response.get_json()["character_file"]
    assert character_file["definition"]["character_slug"] == "api-scout"
    assert character_file["definition"]["name"] == "API Scout"
    assert character_file["definition"]["system"] == "DND-5E"
    assert character_file["state_created"] is True

    list_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters",
        headers=api_headers(dm_token),
    )

    assert list_response.status_code == 200
    listed_slugs = [item["character_slug"] for item in list_response.get_json()["characters"]]
    assert "api-scout" in listed_slugs

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters/api-scout",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    assert detail_response.get_json()["character_file"]["import_metadata"]["parser_version"] == "api-test"
    assert detail_response.get_json()["character_file"]["definition"]["system"] == "DND-5E"

    with app.app_context():
        store = AuthStore()
        store.upsert_character_assignment(users["party"]["id"], "linden-pass", "api-scout")
        state_store = app.extensions["character_state_store"]
        assert state_store.get_state("linden-pass", "api-scout") is not None

    delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/content/characters/api-scout",
        headers=api_headers(dm_token),
    )

    assert delete_response.status_code == 200
    deleted_payload = delete_response.get_json()["deleted"]
    assert deleted_payload["character_slug"] == "api-scout"
    assert deleted_payload["deleted_files"] is True
    assert deleted_payload["deleted_state"] is True
    assert deleted_payload["deleted_assignment"] is True

    with app.app_context():
        store = AuthStore()
        state_store = app.extensions["character_state_store"]
        assert store.get_character_assignment("linden-pass", "api-scout") is None
        assert state_store.get_state("linden-pass", "api-scout") is None

    assert not (campaigns_dir / "linden-pass" / "characters" / "api-scout" / "definition.yaml").exists()


def test_api_content_dnd5e_definition_load_round_trips_unchanged(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-dnd5e-round-trip-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_path = character_dir / "definition.yaml"
    original_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    expected_definition = deepcopy(original_definition)
    expected_definition["system"] = "DND-5E"
    expected_definition["proficiencies"] = {
        "armor": list(original_definition["proficiencies"].get("armor") or []),
        "weapons": list(original_definition["proficiencies"].get("weapons") or []),
        "tools": list(original_definition["proficiencies"].get("tools") or []),
        "languages": list(original_definition["proficiencies"].get("languages") or []),
        "tool_expertise": list(original_definition["proficiencies"].get("tool_expertise") or []),
    }

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    loaded_definition = detail_response.get_json()["character_file"]["definition"]
    assert loaded_definition == expected_definition
    assert "xianxia" not in loaded_definition

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        assert record.definition.to_dict() == expected_definition

    save_loaded_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
        json={"definition": loaded_definition},
    )

    assert save_loaded_response.status_code == 200
    round_tripped_definition = save_loaded_response.get_json()["character_file"]["definition"]
    assert round_tripped_definition == expected_definition
    assert yaml.safe_load(definition_path.read_text(encoding="utf-8")) == expected_definition


def test_api_content_xianxia_definition_round_trips_through_save_and_load(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-round-trip-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    config_path = campaigns_dir / "linden-pass" / "campaign.yaml"
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_payload["system"] = "Xianxia"
    config_payload["systems_library"] = "Xianxia"
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    definition_payload = {
        "name": "Round Trip Cultivator",
        "status": "active",
        "system": "xianxia",
        "xianxia": {
            "realm": "Immortal",
            "action_count": "3",
            "honor": "venerable",
            "reputation": "Known among border sects",
            "attributes": {"str": "2", "dex": 1, "con": 3, "int": 0, "wis": 1, "cha": 0},
            "efforts": {
                "basic": 1,
                "weapon": 2,
                "guns_explosive": 0,
                "magic": 1,
                "ultimate": 1,
            },
            "energy_maxima": {"jing": "3", "qi": 2, "shen": 1},
            "yin_yang": {"yin_max": "2", "yang_max": "1"},
            "dao_max": 3,
            "insight": {"available": "5", "spent": "1"},
            "durability": {
                "hp_max": "18",
                "stance_max": "14",
                "manual_armor_bonus": "2",
                "defense": "99",
            },
            "skills": {"trained": ["Tea Ceremony", "Strategy", "Tea Ceremony"]},
            "equipment": {
                "necessary_weapons": [{"name": "Jian", "reason": "Required by Heavenly Palm"}],
                "necessary_tools": ["Calligraphy brush"],
            },
            "martial_arts": [
                {
                    "systems_ref": {"slug": "heavenly-palm", "entry_type": "martial_art"},
                    "current_rank": "Novice",
                    "learned_rank_refs": ["xianxia:heavenly-palm:initiate"],
                }
            ],
            "generic_techniques": [
                {"systems_ref": {"slug": "qi-blast", "entry_type": "generic_technique"}}
            ],
            "variants": [{"variant_type": "karmic_constraint", "name": "Falling Palm Oath"}],
            "dao_immolating_records": {
                "prepared": [{"name": "Ashen Bell"}],
                "history": [{"name": "River-Cleaving Spark", "approval_status": "approved"}],
            },
            "approval_requests": [{"request_type": "ascendant_art", "status": "pending"}],
            "companions": [{"name": "Ink phantom", "source_ref": "xianxia:ink-stained-historian"}],
            "advancement_history": [{"action": "gather_insight", "amount": 1}],
        },
    }

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/round-trip-cultivator",
        headers=api_headers(dm_token),
        json={"definition": definition_payload},
    )

    assert create_response.status_code == 200
    create_character_file = create_response.get_json()["character_file"]
    assert create_character_file["state_created"] is True
    saved_definition = create_character_file["definition"]
    saved_xianxia = saved_definition["xianxia"]

    assert saved_definition["campaign_slug"] == "linden-pass"
    assert saved_definition["character_slug"] == "round-trip-cultivator"
    assert saved_definition["system"] == "Xianxia"
    assert saved_xianxia["schema_version"] == XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION
    assert saved_xianxia["realm"] == "Immortal"
    assert saved_xianxia["actions_per_turn"] == 3
    assert saved_xianxia["honor"] == "Venerable"
    assert saved_xianxia["attributes"]["str"] == 2
    assert saved_xianxia["energies"]["jing"] == {"max": 3}
    assert saved_xianxia["durability"]["defense"] == 15
    assert saved_xianxia["skills"]["trained"] == ["Tea Ceremony", "Strategy"]
    assert saved_xianxia["equipment"]["necessary_tools"] == [{"name": "Calligraphy brush"}]
    assert saved_xianxia["dao_immolating_techniques"]["use_history"][0]["name"] == "River-Cleaving Spark"
    assert "vitals" not in saved_xianxia
    assert "active_stance" not in saved_xianxia
    assert "notes" not in saved_xianxia

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters/round-trip-cultivator",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    loaded_definition = detail_response.get_json()["character_file"]["definition"]
    assert loaded_definition == saved_definition

    definition_path = (
        campaigns_dir
        / "linden-pass"
        / "characters"
        / "round-trip-cultivator"
        / "definition.yaml"
    )
    saved_file_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    assert tuple(saved_file_definition["xianxia"]) == XIANXIA_DEFINITION_FIELD_KEYS
    assert saved_file_definition == saved_definition

    with app.app_context():
        record = app.extensions["character_repository"].get_character(
            "linden-pass",
            "round-trip-cultivator",
        )
        assert record is not None
        assert record.definition.to_dict() == saved_definition

    save_loaded_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/round-trip-cultivator",
        headers=api_headers(dm_token),
        json={"definition": loaded_definition},
    )

    assert save_loaded_response.status_code == 200
    round_tripped_file = save_loaded_response.get_json()["character_file"]
    assert round_tripped_file["state_created"] is False
    assert round_tripped_file["definition"] == saved_definition
    assert yaml.safe_load(definition_path.read_text(encoding="utf-8")) == saved_definition


def test_api_content_xianxia_definition_update_preserves_sqlite_mutable_state_split(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-character-split-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    config_path = campaigns_dir / "linden-pass" / "campaign.yaml"
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_payload["system"] = "Xianxia"
    config_payload["systems_library"] = "Xianxia"
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    definition_payload = {
        "name": "API Cultivator",
        "status": "active",
        "system": "xianxia",
        "xianxia": {
            "realm": "Mortal",
            "energy_maxima": {"jing": 3, "qi": 2, "shen": 1},
            "yin_yang": {"yin_max": 2, "yang_max": 1},
            "dao_max": 3,
            "durability": {
                "hp_max": 18,
                "stance_max": 12,
                "manual_armor_bonus": 1,
                "defense": 11,
            },
            "trained_skills": ["Tea Ceremony"],
            "necessary_weapons": ["Jian"],
            "martial_arts": [{"name": "Heavenly Palm", "current_rank": "Initiate"}],
        },
    }

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/api-cultivator",
        headers=api_headers(dm_token),
        json={"definition": definition_payload},
    )

    assert create_response.status_code == 200
    assert create_response.get_json()["character_file"]["state_created"] is True

    with app.app_context():
        repository = app.extensions["character_repository"]
        state_store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", "api-cultivator")
        assert record is not None
        mutable_state = deepcopy(record.state_record.state)
        mutable_state["vitals"]["current_hp"] = 7
        mutable_state["xianxia"]["vitals"]["current_hp"] = 7
        mutable_state["xianxia"]["vitals"]["current_stance"] = 5
        mutable_state["xianxia"]["energies"]["jing"]["current"] = 2
        mutable_state["xianxia"]["yin_yang"]["yin_current"] = 1
        mutable_state["xianxia"]["dao"]["current"] = 2
        mutable_state["xianxia"]["active_stance"] = {"name": "Stone Root"}
        mutable_state["notes"]["player_notes_markdown"] = "Keep the manual pool edits in SQLite."
        updated_state = state_store.replace_state(
            record.definition,
            mutable_state,
            expected_revision=record.state_record.revision,
        )
        edited_revision = updated_state.revision

    updated_definition_payload = deepcopy(definition_payload)
    updated_definition_payload["xianxia"]["energy_maxima"] = {"jing": 1, "qi": 2, "shen": 1}
    updated_definition_payload["xianxia"]["yin_yang"] = {"yin_max": 1, "yang_max": 1}
    updated_definition_payload["xianxia"]["durability"] = {
        "hp_max": 6,
        "stance_max": 4,
        "manual_armor_bonus": 1,
        "defense": 11,
    }

    update_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/api-cultivator",
        headers=api_headers(dm_token),
        json={"definition": updated_definition_payload},
    )

    assert update_response.status_code == 200
    assert update_response.get_json()["character_file"]["state_created"] is False

    definition_path = campaigns_dir / "linden-pass" / "characters" / "api-cultivator" / "definition.yaml"
    saved_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    saved_xianxia = saved_definition["xianxia"]
    assert saved_xianxia["durability"]["hp_max"] == 6
    assert saved_xianxia["durability"]["stance_max"] == 4
    assert saved_xianxia["energies"]["jing"] == {"max": 1}
    assert "vitals" not in saved_xianxia
    assert "active_stance" not in saved_xianxia
    assert "notes" not in saved_xianxia
    assert "hp_current" not in saved_definition

    with app.app_context():
        refreshed_record = app.extensions["character_repository"].get_character("linden-pass", "api-cultivator")
        assert refreshed_record is not None
        refreshed_state = refreshed_record.state_record.state

    assert refreshed_record.state_record.revision == edited_revision + 1
    assert refreshed_state["vitals"] == {"current_hp": 6, "temp_hp": 0}
    assert refreshed_state["xianxia"]["vitals"] == {
        "current_hp": 6,
        "temp_hp": 0,
        "current_stance": 4,
        "temp_stance": 0,
    }
    assert refreshed_state["xianxia"]["energies"]["jing"] == {"current": 1}
    assert refreshed_state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert refreshed_state["xianxia"]["dao"] == {"current": 2}
    assert refreshed_state["xianxia"]["active_stance"] == {"name": "Stone Root"}
    assert refreshed_state["notes"]["player_notes_markdown"] == "Keep the manual pool edits in SQLite."


def test_api_content_config_and_assets_refresh_repository_and_manage_files(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-config-assets-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-config-assets-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])

    blocked_config = client.get(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(player_token),
    )
    assert blocked_config.status_code == 403

    config_response = client.get(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(dm_token),
    )
    assert config_response.status_code == 200
    assert config_response.get_json()["config_file"]["config"]["current_session"] == 2

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.current_session == 2
        assert campaign.get_visible_page("sessions/session-3-stormglass-heist") is None

    update_response = client.patch(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(dm_token),
        json={
            "config": {
                "current_session": 3,
                "summary": "Updated through the API for repository refresh coverage.",
            }
        },
    )
    assert update_response.status_code == 200
    updated_config = update_response.get_json()["config_file"]["config"]
    assert updated_config["current_session"] == 3
    assert "repository refresh coverage" in updated_config["summary"]

    campaign_detail = client.get("/api/v1/campaigns/linden-pass", headers=api_headers(dm_token))
    assert campaign_detail.status_code == 200
    assert campaign_detail.get_json()["campaign"]["current_session"] == 3

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.current_session == 3
        assert campaign.get_visible_page("sessions/session-3-stormglass-heist") is not None

    blocked_assets = client.get(
        "/api/v1/campaigns/linden-pass/content/assets",
        headers=api_headers(player_token),
    )
    assert blocked_assets.status_code == 403

    asset_bytes = b"API managed asset bytes"
    asset_response = client.put(
        "/api/v1/campaigns/linden-pass/content/assets/notes/api-sigil.txt",
        headers=api_headers(dm_token),
        json={
            "asset_file": {
                "filename": "api-sigil.txt",
                "data_base64": base64.b64encode(asset_bytes).decode("ascii"),
            }
        },
    )
    assert asset_response.status_code == 200
    assert asset_response.get_json()["asset_file"]["asset_ref"] == "notes/api-sigil.txt"

    asset_list = client.get(
        "/api/v1/campaigns/linden-pass/content/assets",
        headers=api_headers(dm_token),
    )
    assert asset_list.status_code == 200
    asset_refs = [item["asset_ref"] for item in asset_list.get_json()["assets"]]
    assert "notes/api-sigil.txt" in asset_refs

    asset_detail = client.get(
        "/api/v1/campaigns/linden-pass/content/assets/notes/api-sigil.txt",
        headers=api_headers(dm_token),
    )
    assert asset_detail.status_code == 200
    assert base64.b64decode(asset_detail.get_json()["asset_file"]["data_base64"]) == asset_bytes

    asset_path = campaigns_dir / "linden-pass" / "assets" / "notes" / "api-sigil.txt"
    assert asset_path.exists()
    assert asset_path.read_bytes() == asset_bytes

    delete_asset = client.delete(
        "/api/v1/campaigns/linden-pass/content/assets/notes/api-sigil.txt",
        headers=api_headers(dm_token),
    )
    assert delete_asset.status_code == 200
    assert delete_asset.get_json()["deleted"]["asset_ref"] == "notes/api-sigil.txt"
    assert not asset_path.exists()


def test_api_content_config_can_select_xianxia_system_and_library(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-config-api")

    update_response = client.patch(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(dm_token),
        json={
            "config": {
                "system": "xianxia",
                "systems_library": "xianxia",
            }
        },
    )

    assert update_response.status_code == 200
    updated_config = update_response.get_json()["config_file"]["config"]
    assert updated_config["system"] == "Xianxia"
    assert updated_config["systems_library"] == "Xianxia"

    campaign_detail = client.get("/api/v1/campaigns/linden-pass", headers=api_headers(dm_token))
    assert campaign_detail.status_code == 200
    campaign_payload = campaign_detail.get_json()["campaign"]
    assert campaign_payload["system"] == "Xianxia"
    assert campaign_payload["systems_library_slug"] == "Xianxia"

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.system == "Xianxia"
        assert campaign.systems_library_slug == "Xianxia"
        assert app.extensions["systems_service"].get_campaign_library_slug("linden-pass") == "Xianxia"


def test_api_systems_endpoints_follow_source_visibility_and_allow_dm_policy_updates(client, app, users, tmp_path):
    goblin_entry_key, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-systems-api")

    dm_index = client.get("/api/v1/campaigns/linden-pass/systems", headers=api_headers(dm_token))
    assert dm_index.status_code == 200
    dm_sources = {item["source_id"] for item in dm_index.get_json()["sources"]}
    assert "MM" in dm_sources

    player_index = client.get("/api/v1/campaigns/linden-pass/systems", headers=api_headers(player_token))
    assert player_index.status_code == 200
    player_sources = {item["source_id"] for item in player_index.get_json()["sources"]}
    assert "MM" not in player_sources

    blocked_source = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        headers=api_headers(player_token),
    )
    assert blocked_source.status_code == 403

    source_detail = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        headers=api_headers(dm_token),
    )
    assert source_detail.status_code == 200
    source_payload = source_detail.get_json()
    assert source_payload["source"]["source_id"] == "MM"
    assert source_payload["entry_count"] == 1

    source_category = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        headers=api_headers(dm_token),
    )
    assert source_category.status_code == 200
    category_entries = source_category.get_json()["entries"]
    assert len(category_entries) == 1
    assert category_entries[0]["entry_key"] == goblin_entry_key
    assert category_entries[0]["title"] == "Goblin"

    entry_detail = client.get(
        f"/api/v1/campaigns/linden-pass/systems/entries/{goblin_slug}",
        headers=api_headers(dm_token),
    )
    assert entry_detail.status_code == 200
    assert entry_detail.get_json()["entry"]["title"] == "Goblin"
    assert entry_detail.get_json()["entry"]["entry_type"] == "monster"

    update_sources = client.put(
        "/api/v1/campaigns/linden-pass/systems/sources",
        headers=api_headers(dm_token),
        json={
            "updates": [
                {
                    "source_id": "XGE",
                    "is_enabled": True,
                    "default_visibility": "dm",
                }
            ]
        },
    )
    assert update_sources.status_code == 200
    xge_state = next(
        item for item in update_sources.get_json()["sources"] if item["source_id"] == "XGE"
    )
    assert xge_state["default_visibility"] == "dm"

    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state("linden-pass", "XGE")
        assert state is not None
        assert state.default_visibility == "dm"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("source_id") == "XGE" for event in events)


def test_api_systems_import_endpoints_require_admin_and_record_runs(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-import-api")
    archive_bytes = _build_systems_import_archive(tmp_path)
    import_payload = {
        "source_ids": ["MM"],
        "entry_types": ["monster"],
        "archive": {
            "filename": "mm-import.zip",
            "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
        },
    }

    blocked_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(dm_token),
        json=import_payload,
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    import_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json=import_payload,
    )
    assert import_response.status_code == 200
    import_payload = import_response.get_json()
    assert import_payload["ok"] is True

    import_result = import_payload["import_results"][0]
    assert import_result["source_id"] == "MM"
    assert import_result["import_version"] == "mm-import"
    assert import_result["imported_count"] == 1
    assert import_result["imported_by_type"] == {"monster": 1}
    assert import_result["source_files"] == ["data/bestiary/bestiary-mm.json"]

    import_run = import_payload["import_runs"][0]
    assert import_run["status"] == "completed"
    assert import_run["source_id"] == "MM"
    assert import_run["import_version"] == "mm-import"
    assert import_run["source_path"] == "api-upload:mm-import.zip"
    assert import_run["started_by_user_id"] == users["admin"]["id"]
    assert import_run["summary"]["entry_types"] == ["monster"]
    assert import_run["summary"]["imported_count"] == 1
    assert import_run["summary"]["source_files"] == ["data/bestiary/bestiary-mm.json"]

    blocked_runs = client.get("/api/v1/systems/import-runs", headers=api_headers(dm_token))
    assert blocked_runs.status_code == 403
    assert blocked_runs.get_json()["error"]["code"] == "forbidden"

    list_response = client.get("/api/v1/systems/import-runs?source_id=MM", headers=api_headers(admin_token))
    assert list_response.status_code == 200
    listed_run = list_response.get_json()["import_runs"][0]
    assert listed_run["id"] == import_run["id"]
    assert listed_run["summary"]["imported_count"] == 1

    detail_response = client.get(
        f"/api/v1/systems/import-runs/{import_run['id']}",
        headers=api_headers(admin_token),
    )
    assert detail_response.status_code == 200
    assert detail_response.get_json()["import_run"]["id"] == import_run["id"]

    dm_source = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        headers=api_headers(dm_token),
    )
    assert dm_source.status_code == 200
    imported_entries = dm_source.get_json()["entries"]
    assert len(imported_entries) == 1
    assert imported_entries[0]["title"] == "Goblin"


def test_api_systems_import_endpoint_rejects_unsafe_archives(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-unsafe-api")
    archive_bytes = _build_unsafe_systems_import_archive(tmp_path)

    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "unsafe-systems-import.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert "parent-relative paths" in payload["error"]["message"]


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

    live_state = client.get(
        "/api/v1/campaigns/linden-pass/combat/live-state",
        headers=api_headers(dm_token),
    )
    assert live_state.status_code == 200
    assert live_state.get_json()["tracker"]["combatant_count"] == 2


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

