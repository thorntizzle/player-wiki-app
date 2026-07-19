from __future__ import annotations

import json

import pytest

from player_wiki.character_models import CharacterDefinition
from player_wiki.character_reconciliation import CharacterPublicationConflict
from player_wiki.character_service import build_initial_state
from player_wiki.character_store import CharacterStateConflictError
from player_wiki.campaign_content_service import write_campaign_character_file
from player_wiki.db import get_db
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

def test_api_player_wiki_read_endpoints_follow_visible_campaign_pages(client, app, users):
    player_token = issue_api_token(app, users["party"]["email"], label="player-wiki-api")
    note_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "notes"
        / "operations-brief.md"
    )
    note_path.write_text(
        (
            note_path.read_text(encoding="utf-8")
            + "\nLegacy route check: [Captain Lyra Vale](/campaigns/linden-pass/pages/npcs/captain-lyra-vale).\n"
            + "Stale app-next check: [Harbor Row](/app-next/campaigns/linden-pass/pages/locations/harbor-row).\n"
        ),
        encoding="utf-8",
    )
    bestiary_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "content" / "bestiary"
    bestiary_dir.mkdir(parents=True, exist_ok=True)
    (bestiary_dir / "clockwork-eel.md").write_text(
        "\n".join(
            [
                "---",
                "title: Clockwork Eel",
                "section: Bestiary",
                "type: monster",
                "reveal_after_session: 2",
                "summary: A hostile construct encountered by the party.",
                "---",
                "",
                "The party documented this enemy after the harbor job.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()

    home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(player_token))
    assert home_response.status_code == 200
    home_payload = home_response.get_json()
    assert home_payload["ok"] is True
    assert home_payload["frontend_mode"] == "flask"
    assert home_payload["can_view_wiki"] is True
    assert home_payload["overview_page"] is None
    assert home_payload["latest_session_summary"] is not None
    assert home_payload["latest_session_summary"]["title"] == "Session 2 - The Brass Vault"
    assert home_payload["latest_session_summary"]["route_slug"] == "sessions/session-2-the-brass-vault"
    assert home_payload["latest_session_summary"]["page_type"] == "session"
    assert all(section["section_name"] != "Overview" for section in home_payload["grouped_sections"])
    assert all(section["section_name"] != "Overview" for section in home_payload["section_navigation"])
    locations_group = next(section for section in home_payload["grouped_sections"] if section["section_name"] == "Locations")
    assert locations_group["href"] == "/campaigns/linden-pass/sections/locations"
    locations_nav_item = next(section for section in home_payload["section_navigation"] if section["section_name"] == "Locations")
    assert locations_nav_item == {
        "section_name": "Locations",
        "section_slug": "locations",
        "href": "/campaigns/linden-pass/sections/locations",
        "page_count": locations_group["page_count"],
    }
    bestiary_group = next(section for section in home_payload["grouped_sections"] if section["section_name"] == "Bestiary")
    assert bestiary_group["href"] == "/campaigns/linden-pass/sections/bestiary"
    bestiary_nav_item = next(section for section in home_payload["section_navigation"] if section["section_name"] == "Bestiary")
    assert bestiary_nav_item == {
        "section_name": "Bestiary",
        "section_slug": "bestiary",
        "href": "/campaigns/linden-pass/sections/bestiary",
        "page_count": 1,
    }

    search_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki?q=capt",
        headers=api_headers(player_token),
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["query"] == "capt"
    assert search_payload["overview_page"] is None
    assert search_payload["latest_session_summary"] is None
    assert search_payload["result_count"] >= 1
    search_pages = [
        page
        for section in search_payload["grouped_sections"]
        for page in section["pages"]
    ]
    captain = next(page for page in search_pages if page["page_ref"] == "npcs/captain-lyra-vale")
    assert captain["href"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    assert "source_ref" not in captain
    assert "aliases" not in captain
    assert any(section["section_name"] == "Locations" for section in search_payload["section_navigation"])

    section_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/sections/locations",
        headers=api_headers(player_token),
    )
    assert section_response.status_code == 200
    section_payload = section_response.get_json()
    assert section_payload["section_name"] == "Locations"
    assert section_payload["frontend_mode"] == "flask"
    assert section_payload["show_subsections"] is True
    assert section_payload["top_level_pages"][0]["title"] == "Port Meridian"
    assert section_payload["top_level_pages"][0]["href"].startswith("/campaigns/linden-pass/pages/")
    subsection_names = [group["subsection_name"] for group in section_payload["subsection_groups"]]
    assert "Civic and Institutional Sites" in subsection_names
    assert "Venues and Residences" in subsection_names
    assert any(section["section_slug"] == "locations" for section in section_payload["section_navigation"])
    bestiary_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/sections/bestiary",
        headers=api_headers(player_token),
    )
    assert bestiary_response.status_code == 200
    bestiary_payload = bestiary_response.get_json()
    assert bestiary_payload["section_name"] == "Bestiary"
    assert bestiary_payload["pages"][0]["title"] == "Clockwork Eel"
    assert bestiary_payload["pages"][0]["display_type"] == "monster"

    page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale",
        headers=api_headers(player_token),
    )
    assert page_response.status_code == 200
    page_payload = page_response.get_json()
    assert page_payload["page"]["title"] == "Captain Lyra Vale"
    assert page_payload["page"]["image"]["url"] == "/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png"
    assert page_payload["page"]["image"]["caption"] == "Harbor watch captain and trusted ally of the crew."
    assert "Captain Lyra Vale coordinates inspections" in page_payload["page"]["body_html"]
    assert page_payload["links"]["flask_page_url"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    assert page_payload["links"]["campaign_url"] == "/campaigns/linden-pass"
    assert page_payload["links"]["section_url"] == "/campaigns/linden-pass/sections/npcs"
    assert "gen2_campaign_url" not in page_payload["links"]
    assert any(section["section_slug"] == "npcs" for section in page_payload["section_navigation"])

    note_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/notes/operations-brief",
        headers=api_headers(player_token),
    )
    assert note_response.status_code == 200
    note_body = note_response.get_json()["page"]["body_html"]
    assert 'href="/campaigns/linden-pass/pages/npcs/captain-lyra-vale"' in note_body
    assert 'href="/campaigns/linden-pass/pages/locations/harbor-row"' in note_body
    assert "/app-next/app-next/" not in note_body
    assert 'href="/app-next/campaigns/linden-pass/pages/' not in note_body

    overview_section_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/sections/overview",
        headers=api_headers(player_token),
    )
    assert overview_section_response.status_code == 404
    overview_page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/index",
        headers=api_headers(player_token),
    )
    assert overview_page_response.status_code == 404

    with app.app_context():
        AuthStore().set_user_frontend_mode(users["party"]["id"], "flask")

    legacy_home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(player_token))
    assert legacy_home_response.status_code == 200
    legacy_home_payload = legacy_home_response.get_json()
    assert legacy_home_payload["frontend_mode"] == "flask"
    assert legacy_home_payload["overview_page"] is None
    assert legacy_home_payload["latest_session_summary"] is not None
    assert legacy_home_payload["latest_session_summary"]["title"] == "Session 2 - The Brass Vault"
    assert legacy_home_payload["latest_session_summary"]["route_slug"] == "sessions/session-2-the-brass-vault"
    assert all(section["section_name"] != "Overview" for section in legacy_home_payload["grouped_sections"])
    assert all(section["section_name"] != "Overview" for section in legacy_home_payload["section_navigation"])
    legacy_locations_group = next(section for section in legacy_home_payload["grouped_sections"] if section["section_name"] == "Locations")
    assert legacy_locations_group["href"] == "/campaigns/linden-pass/sections/locations"
    legacy_locations_nav_item = next(
        section for section in legacy_home_payload["section_navigation"] if section["section_name"] == "Locations"
    )
    assert legacy_locations_nav_item["href"] == "/campaigns/linden-pass/sections/locations"

    legacy_search_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki?q=capt",
        headers=api_headers(player_token),
    )
    assert legacy_search_response.status_code == 200
    legacy_search_pages = [
        page
        for section in legacy_search_response.get_json()["grouped_sections"]
        for page in section["pages"]
    ]
    legacy_captain = next(page for page in legacy_search_pages if page["page_ref"] == "npcs/captain-lyra-vale")
    assert legacy_captain["href"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"

    legacy_page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale",
        headers=api_headers(player_token),
    )
    assert legacy_page_response.status_code == 200
    legacy_page_payload = legacy_page_response.get_json()
    assert legacy_page_payload["links"]["campaign_url"] == "/campaigns/linden-pass"
    assert legacy_page_payload["links"]["section_url"] == "/campaigns/linden-pass/sections/npcs"
    assert legacy_page_payload["links"]["flask_page_url"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"


def test_api_player_wiki_home_reports_restricted_wiki_scope(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", wiki="dm")
    player_token = issue_api_token(app, users["party"]["email"], label="restricted-player-wiki-api")

    home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(player_token))
    assert home_response.status_code == 200
    home_payload = home_response.get_json()
    assert home_payload["can_view_wiki"] is False
    assert home_payload["grouped_sections"] == []
    assert home_payload["section_navigation"] == []
    assert "requires DM access" in home_payload["message"]

    page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale",
        headers=api_headers(player_token),
    )
    assert page_response.status_code == 403
    assert page_response.get_json()["error"]["code"] == "forbidden"


def test_campaign_home_renders_latest_session_summary_card(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'aria-label="Latest session summary"' in html
    assert "Latest session summary" in html
    assert "Session 2 - The Brass Vault" in html
    assert 'href="/campaigns/linden-pass/pages/sessions/session-2-the-brass-vault"' in html
    assert "Session 3 - Stormglass Heist" not in html

    search_response = client.get("/campaigns/linden-pass?q=capt")
    assert search_response.status_code == 200
    assert 'aria-label="Latest session summary"' not in search_response.get_data(as_text=True)


def test_api_player_wiki_home_selects_latest_published_session_summary_deterministically(
    client,
    app,
    users,
):
    sessions_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "content" / "sessions"
    for stem, summary in (
        ("session-2-alpha-incident", "Session 2 - Alpha Incident"),
        ("session-2-zeta-chronicle", "Session 2 - Zeta Chronicle"),
    ):
        (sessions_dir / f"{stem}.md").write_text(
            "\n".join(
                [
                    "---",
                    "title: " + summary,
                    "section: Sessions",
                    "type: session",
                    "reveal_after_session: 2",
                    "summary: " + summary,
                    "---",
                    "",
                    "Added as a deterministic test fixture for campaign-home session selection.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    with app.app_context():
        app.extensions["repository_store"].refresh()

    dm_token = issue_api_token(app, users["dm"]["email"], label="session-summary-deterministic-api")
    home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(dm_token))
    assert home_response.status_code == 200
    home_payload = home_response.get_json()
    assert home_payload["latest_session_summary"] is not None
    assert home_payload["latest_session_summary"]["title"] == "Session 2 - Zeta Chronicle"


def test_api_dm_content_endpoints_require_dm_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-dm-content-api")

    initial_dm_content_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(dm_token))
    assert initial_dm_content_response.status_code == 200
    initial_dm_content_payload = initial_dm_content_response.get_json()
    initial_statblock_count = len(initial_dm_content_payload["statblocks"])
    initial_condition_count = len(initial_dm_content_payload["conditions"])
    initial_counts = initial_dm_content_payload.get("subpage_counts", {})
    initial_staged_count = initial_counts.get("staged_articles")
    if initial_staged_count is None:
        session_status = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
        assert session_status.status_code == 200
        initial_staged_count = len(session_status.get_json()["staged_articles"])
    initial_player_wiki_count = initial_counts.get("player_wiki")
    if initial_player_wiki_count is None:
        initial_pages_response = client.get("/api/v1/campaigns/linden-pass/content/pages", headers=api_headers(dm_token))
        assert initial_pages_response.status_code == 200
        initial_player_wiki_count = len(initial_pages_response.get_json()["pages"])
    initial_systems_count = initial_counts.get("systems")
    if initial_systems_count is None:
        systems_payload = client.get(
            "/api/v1/campaigns/linden-pass/dm-content/systems",
            headers=api_headers(dm_token),
        )
        assert systems_payload.status_code == 200
        initial_systems_count = int(systems_payload.get_json().get("source_count") or 0)

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

    create_staged_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={"mode": "manual", "title": "DM Content Count Prep", "body_markdown": "A staged article for count coverage."},
    )
    assert create_staged_response.status_code == 200
    create_staged_payload = create_staged_response.get_json()
    assert create_staged_payload["article"]["title"] == "DM Content Count Prep"

    page_ref = "notes/dm-content-api-counts"
    create_page_response = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "DM Content API Count Page",
                "section": "Notes",
                "type": "note",
                "summary": "A temporary page used to cover subpage count parity in tests.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "API coverage for DM Content lane counts.",
        },
    )
    assert create_page_response.status_code == 200

    dm_content_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(dm_token))

    assert dm_content_response.status_code == 200
    dm_content_payload = dm_content_response.get_json()
    assert "subpage_counts" in dm_content_payload
    assert len(dm_content_payload["statblocks"]) == initial_statblock_count + 1
    assert len(dm_content_payload["conditions"]) == initial_condition_count + 1
    assert dm_content_payload["subpage_counts"]["statblocks"] == initial_statblock_count + 1
    assert dm_content_payload["subpage_counts"]["conditions"] == initial_condition_count + 1
    assert dm_content_payload["subpage_counts"]["player_wiki"] == initial_player_wiki_count + 1
    assert dm_content_payload["subpage_counts"]["staged_articles"] == initial_staged_count + 1
    assert dm_content_payload["subpage_counts"]["systems"] == initial_systems_count
    assert any(statblock["subsection"] == "Dock Crew" for statblock in dm_content_payload["statblocks"])
    assert any(condition["name"] == "Off Balance Revised" for condition in dm_content_payload["conditions"])

    blocked_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(player_token))

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"


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
    listed_pages = list_response.get_json()["pages"]
    assert any(item["page_ref"] == "notes/api-field-report" for item in listed_pages)
    listed_field_report = next(
        item for item in listed_pages if item["page_ref"] == "notes/api-field-report"
    )
    assert listed_field_report["can_hard_delete"] is True
    assert listed_field_report["hard_delete_blockers"] == []
    assert listed_field_report["removal_status_label"] == "Hard delete available"
    assert listed_field_report["removal_safety"]["can_hard_delete"] is True

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()["page_file"]
    assert "east pier wards" in detail_payload["body_markdown"]
    assert detail_payload["can_hard_delete"] is True
    assert detail_payload["removal_safety"]["can_hard_delete"] is True

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


def test_api_content_page_delete_preserves_missing_and_malformed_error_envelopes(
    client,
    app,
    users,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-delete-error-envelope")
    missing = client.delete(
        "/api/v1/campaigns/linden-pass/content/pages/notes/missing-delete-target",
        headers=api_headers(dm_token),
    )
    assert missing.status_code == 404

    page_ref = "notes/malformed-delete-target"
    created = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "Malformed Delete Target",
                "section": "Notes",
                "type": "note",
                "published": True,
            },
            "body_markdown": "This page must survive a malformed delete request.",
        },
    )
    assert created.status_code == 200
    page_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "content"
        / "notes"
        / "malformed-delete-target.md"
    )

    malformed = client.delete(
        f"/api/v1/campaigns/linden-pass/content/pages/{page_ref}",
        headers=api_headers(dm_token),
        data="[]",
        content_type="application/json",
    )
    assert malformed.status_code == 400
    payload = malformed.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert page_path.exists()
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_deletion_operations"
        ).fetchone()[0] == 0


@pytest.mark.parametrize("force_as_json", [False, True])
def test_api_content_page_management_blocks_deletion_when_page_is_referenced(
    client,
    app,
    users,
    force_as_json,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-pages-referenced-api")
    target_page_ref = "notes/api-reference-target"
    referencing_page_ref = "notes/api-reference-hub"

    create_target = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Reference Target",
                "section": "Notes",
                "type": "note",
                "summary": "A page intended to be linked.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "This target page should be blocked from hard delete when linked.",
        },
    )
    assert create_target.status_code == 200

    create_referrer = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{referencing_page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Reference Hub",
                "section": "Notes",
                "type": "note",
                "summary": "This page links to the reference target.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "Cross-check with [[API Reference Target]].",
        },
    )
    assert create_referrer.status_code == 200

    list_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages",
        headers=api_headers(dm_token),
    )

    assert list_response.status_code == 200
    listed_pages = list_response.get_json()["pages"]
    target_listing = next(item for item in listed_pages if item["page_ref"] == target_page_ref)
    assert target_listing["can_hard_delete"] is False
    assert any("Backlinked from API Reference Hub." in blocker for blocker in target_listing["hard_delete_blockers"])

    blocked_delete = client.delete(
        f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}",
        headers=api_headers(dm_token),
    )

    assert blocked_delete.status_code == 409
    blocked_payload = blocked_delete.get_json()
    assert blocked_payload["error"]["code"] == "hard_delete_blocked"
    assert blocked_payload["error"]["details"]["removal_safety"]["can_hard_delete"] is False
    assert any(
        "Backlinked from API Reference Hub." in blocker
        for blocker in blocked_payload["error"]["details"]["removal_safety"]["hard_delete_blockers"]
    )

    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    target_page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "api-reference-target.md"
    assert target_page_path.exists()

    forced_url = f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}"
    if not force_as_json:
        forced_url += "?force=true"
    forced_delete = client.delete(
        forced_url,
        headers=api_headers(dm_token),
        **({"json": {"force": True}} if force_as_json else {}),
    )
    assert forced_delete.status_code == 200
    assert forced_delete.get_json()["deleted"]["page_ref"] == target_page_ref
    assert not target_page_path.exists()


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


@pytest.mark.parametrize(
    "existing_parts",
    (
        ("definition.yaml",),
        ("import.yaml",),
        ("definition.yaml", "import.yaml"),
        ("state",),
        ("definition.yaml", "state"),
        ("import.yaml", "state"),
    ),
)
def test_api_content_character_update_rejects_partial_target_without_state_initialization(
    client,
    app,
    users,
    existing_parts,
):
    case_name = "-".join(part.removesuffix(".yaml") for part in existing_parts)
    dm_token = issue_api_token(app, users["dm"]["email"], label=f"partial-{case_name}")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    source_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_payload = yaml.safe_load(
        (source_dir / "definition.yaml").read_text(encoding="utf-8")
    )
    import_payload = yaml.safe_load(
        (source_dir / "import.yaml").read_text(encoding="utf-8")
    )
    slug = f"partial-{case_name}"
    target_dir = campaigns_dir / "linden-pass" / "characters" / slug
    original_files: dict[str, bytes | None] = {}
    for file_name in ("definition.yaml", "import.yaml"):
        if file_name in existing_parts:
            target_dir.mkdir(parents=True, exist_ok=True)
            source_bytes = (source_dir / file_name).read_bytes()
            (target_dir / file_name).write_bytes(source_bytes)
            original_files[file_name] = source_bytes
        else:
            original_files[file_name] = None
    if "state" in existing_parts:
        state_definition_payload = deepcopy(definition_payload)
        state_definition_payload["campaign_slug"] = "linden-pass"
        state_definition_payload["character_slug"] = slug
        state_definition = CharacterDefinition.from_dict(state_definition_payload)
        with app.app_context():
            state_result = app.extensions["character_state_store"].initialize_state_if_missing(
                state_definition,
                build_initial_state(state_definition),
            )
            assert state_result.created is True
    with app.app_context():
        original_state = get_db().execute(
            """
            SELECT revision, state_json, updated_at, updated_by_user_id
            FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        original_state = tuple(original_state) if original_state is not None else None

    response = client.put(
        f"/api/v1/campaigns/linden-pass/content/characters/{slug}",
        headers=api_headers(dm_token),
        json={
            "definition": definition_payload,
            "import_metadata": import_payload,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert "incomplete" in response.get_json()["error"]["message"].lower()
    for file_name, original_bytes in original_files.items():
        file_path = target_dir / file_name
        if original_bytes is None:
            assert not file_path.exists()
        else:
            assert file_path.read_bytes() == original_bytes
    with app.app_context():
        final_state = get_db().execute(
            """
            SELECT revision, state_json, updated_at, updated_by_user_id
            FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        final_state = tuple(final_state) if final_state is not None else None
        assert final_state == original_state
        assert get_db().execute(
            """
            SELECT 1 FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone() is None


def test_direct_character_content_writer_preserves_legacy_partial_target_initialization(
    app,
):
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_payload = yaml.safe_load(
        (character_dir / "definition.yaml").read_text(encoding="utf-8")
    )
    with app.app_context():
        state_store = app.extensions["character_state_store"]
        assert state_store.get_state("linden-pass", "arden-march") is None

        written = write_campaign_character_file(
            campaigns_dir,
            "linden-pass",
            "arden-march",
            definition_payload=definition_payload,
            import_metadata_payload=None,
            state_store=state_store,
            coordinator=None,
        )

        assert written.state_created is True
        assert state_store.get_state("linden-pass", "arden-march") is not None


def test_api_content_character_put_preserves_auth_and_validation_error_envelopes(
    client,
    app,
    users,
):
    player_token = issue_api_token(app, users["party"]["email"], label="player-character-put")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-put-error")
    url = "/api/v1/campaigns/linden-pass/content/characters/arden-march"

    forbidden_response = client.put(
        url,
        headers=api_headers(player_token),
        json={"definition": {}},
    )
    validation_response = client.put(
        url,
        headers=api_headers(dm_token),
        json={"definition": "not-an-object"},
    )

    assert forbidden_response.status_code == 403
    assert forbidden_response.get_json()["error"]["code"] == "forbidden"
    assert validation_response.status_code == 400
    assert validation_response.get_json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("conflict_type", "message"),
    (
        (CharacterStateConflictError, "Character state changed after it was loaded."),
        (CharacterPublicationConflict, "Character reconciliation ownership changed."),
        (CharacterPublicationConflict, "Character files changed after they were loaded."),
    ),
    ids=("stale-state", "concurrent-owner", "tampered-files"),
)
def test_api_content_character_update_translates_expected_conflicts_without_mutation(
    client,
    app,
    users,
    monkeypatch,
    conflict_type,
    message,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label=f"put-conflict-{conflict_type.__name__}")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    original_definition = definition_path.read_bytes()
    original_import = import_path.read_bytes()
    with app.app_context():
        definition = CharacterDefinition.from_dict(definition_payload)
        app.extensions["character_state_store"].initialize_state_if_missing(
            definition,
            build_initial_state(definition),
        )
        original_state = tuple(
            get_db().execute(
                """
                SELECT revision, state_json, updated_at, updated_by_user_id
                FROM character_state
                WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
                """
            ).fetchone()
        )
    coordinator = app.extensions["character_publication_coordinator"]

    def fail_expected_update(*args, **kwargs):
        raise conflict_type(message)

    monkeypatch.setattr(coordinator, "update", fail_expected_update)

    response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
        json={"definition": definition_payload},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": message,
    }
    assert definition_path.read_bytes() == original_definition
    assert import_path.read_bytes() == original_import
    with app.app_context():
        assert tuple(
            get_db().execute(
                """
                SELECT revision, state_json, updated_at, updated_by_user_id
                FROM character_state
                WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
                """
            ).fetchone()
        ) == original_state
        assert get_db().execute(
            """
            SELECT 1 FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
            """
        ).fetchone() is None


def test_api_content_character_update_refuses_active_reconciliation_without_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    from player_wiki import character_reconciliation

    dm_token = issue_api_token(app, users["dm"]["email"], label="put-active-reconciliation")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    original_definition = definition_path.read_bytes()
    original_import = import_path.read_bytes()
    with app.app_context():
        definition = CharacterDefinition.from_dict(definition_payload)
        app.extensions["character_state_store"].initialize_state_if_missing(
            definition,
            build_initial_state(definition),
        )
        original_state = tuple(
            get_db().execute(
                """
                SELECT revision, state_json, updated_at, updated_by_user_id
                FROM character_state
                WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
                """
            ).fetchone()
        )
    monkeypatch.setattr(
        character_reconciliation,
        "is_character_reconciliation_protected",
        lambda campaign_slug, character_slug: True,
    )

    response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
        json={"definition": definition_payload},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert "active reconciliation" in response.get_json()["error"]["message"].lower()
    assert definition_path.read_bytes() == original_definition
    assert import_path.read_bytes() == original_import
    with app.app_context():
        assert tuple(
            get_db().execute(
                """
                SELECT revision, state_json, updated_at, updated_by_user_id
                FROM character_state
                WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
                """
            ).fetchone()
        ) == original_state


def test_api_content_character_update_does_not_mask_unexpected_coordinator_fault(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="put-unexpected-fault")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_payload = yaml.safe_load(
        (character_dir / "definition.yaml").read_text(encoding="utf-8")
    )
    with app.app_context():
        definition = CharacterDefinition.from_dict(definition_payload)
        app.extensions["character_state_store"].initialize_state_if_missing(
            definition,
            build_initial_state(definition),
        )
    coordinator = app.extensions["character_publication_coordinator"]

    def fail_unexpectedly(*args, **kwargs):
        raise RuntimeError("unexpected coordinator fault")

    monkeypatch.setattr(coordinator, "update", fail_unexpectedly)

    with pytest.raises(RuntimeError, match="unexpected coordinator fault"):
        client.put(
            "/api/v1/campaigns/linden-pass/content/characters/arden-march",
            headers=api_headers(dm_token),
            json={"definition": definition_payload},
        )


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
        state_json = get_db().execute(
            """
            SELECT state_json FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
            """
        ).fetchone()[0]
        preserved_state_json = json.dumps(
            json.loads(state_json),
            indent=2,
            sort_keys=False,
        )
        get_db().execute(
            """
            UPDATE character_state
            SET state_json = ?, updated_at = '2026-01-02T03:04:05+00:00',
                updated_by_user_id = ?
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
            """,
            (preserved_state_json, users["dm"]["id"]),
        )
        get_db().commit()

    save_loaded_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
        json={"definition": loaded_definition},
    )

    assert save_loaded_response.status_code == 200
    round_tripped_definition = save_loaded_response.get_json()["character_file"]["definition"]
    assert round_tripped_definition == expected_definition
    assert yaml.safe_load(definition_path.read_text(encoding="utf-8")) == expected_definition
    with app.app_context():
        unchanged_state_row = get_db().execute(
            """
            SELECT revision, state_json, updated_at, updated_by_user_id
            FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
            """
        ).fetchone()
        assert tuple(unchanged_state_row) == (
            record.state_record.revision,
            preserved_state_json,
            "2026-01-02T03:04:05+00:00",
            users["dm"]["id"],
        )


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
        get_db().execute(
            """
            UPDATE character_state
            SET updated_at = '2026-01-02T03:04:05+00:00',
                updated_by_user_id = ?
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'api-cultivator'
            """,
            (users["dm"]["id"],),
        )
        get_db().commit()

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
        refreshed_state_row = get_db().execute(
            """
            SELECT revision, updated_at, updated_by_user_id
            FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'api-cultivator'
            """
        ).fetchone()

    assert refreshed_record.state_record.revision == edited_revision + 1
    assert refreshed_state_row["revision"] == edited_revision + 1
    assert refreshed_state_row["updated_at"] != "2026-01-02T03:04:05+00:00"
    assert refreshed_state_row["updated_by_user_id"] is None
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
    campaign_detail_payload = campaign_detail.get_json()
    assert campaign_detail_payload["campaign"]["current_session"] == 3
    assert campaign_detail_payload["permissions"]["can_manage_visibility"] is True

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
