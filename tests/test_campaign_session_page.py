from __future__ import annotations

import json
import shutil
from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from player_wiki.app import create_app
from player_wiki.auth_store import AuthStore
from player_wiki.config import Config
from player_wiki.db import init_database
from player_wiki.systems_importer import Dnd5eSystemsImporter
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG, build_test_campaigns_dir


TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _import_systems_goblin(app, tmp_path) -> str:
    data_root = tmp_path / "session-systems-dnd5e-source"
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
        return entry.slug


def seed_test_users(app):
    with app.app_context():
        store = AuthStore()

        owner_player = store.create_user(
            "owner@example.com",
            "Owner Player",
            status="active",
            password_hash=generate_password_hash("owner-pass"),
        )
        other_player = store.create_user(
            "party@example.com",
            "Party Player",
            status="active",
            password_hash=generate_password_hash("party-pass"),
        )
        dm = store.create_user(
            "dm@example.com",
            "Dungeon Master",
            status="active",
            password_hash=generate_password_hash("dm-pass"),
        )
        observer = store.create_user(
            "observer@example.com",
            "Observer",
            status="active",
            password_hash=generate_password_hash("observer-pass"),
        )
        outsider = store.create_user(
            "outsider@example.com",
            "Outsider",
            status="active",
            password_hash=generate_password_hash("outsider-pass"),
        )
        admin = store.create_user(
            "admin@example.com",
            "Admin User",
            is_admin=True,
            status="active",
            password_hash=generate_password_hash("admin-pass"),
        )

        store.upsert_membership(owner_player.id, TEST_CAMPAIGN_SLUG, role="player")
        store.upsert_membership(other_player.id, TEST_CAMPAIGN_SLUG, role="player")
        store.upsert_membership(dm.id, TEST_CAMPAIGN_SLUG, role="dm")
        store.upsert_membership(observer.id, TEST_CAMPAIGN_SLUG, role="observer")
        store.upsert_character_assignment(owner_player.id, TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)

        app.config["TEST_USERS"] = {
            "owner": {"email": "owner@example.com", "password": "owner-pass", "id": owner_player.id},
            "party": {"email": "party@example.com", "password": "party-pass", "id": other_player.id},
            "dm": {"email": "dm@example.com", "password": "dm-pass", "id": dm.id},
            "observer": {"email": "observer@example.com", "password": "observer-pass", "id": observer.id},
            "outsider": {"email": "outsider@example.com", "password": "outsider-pass", "id": outsider.id},
            "admin": {"email": "admin@example.com", "password": "admin-pass", "id": admin.id},
        }


@pytest.fixture()
def isolated_campaign_app(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)

    app = create_app()
    app.config.update(
        TESTING=True,
        DB_PATH=tmp_path / "player_wiki.sqlite3",
    )

    with app.app_context():
        init_database()

    seed_test_users(app)
    app.config["TEST_CAMPAIGNS_DIR"] = campaigns_dir
    return app


@pytest.fixture()
def isolated_campaign_client(isolated_campaign_app):
    return isolated_campaign_app.test_client()


@pytest.fixture()
def isolated_campaign_users(isolated_campaign_app):
    return isolated_campaign_app.config["TEST_USERS"]


@pytest.fixture()
def isolated_campaign_sign_in(isolated_campaign_client):
    def _sign_in(email: str, password: str):
        return isolated_campaign_client.post(
            "/sign-in",
            data={"email": email, "password": password},
            follow_redirects=False,
        )

    return _sign_in


def test_campaign_member_can_open_session_page_and_campaign_links_to_it(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    session_page = client.get("/campaigns/linden-pass/session")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "Open session page" not in campaign_html
    assert "Session" in campaign_html
    assert '/campaigns/linden-pass/session' in campaign_html

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Session controls" not in session_html
    assert "Open DM page" not in session_html
    assert "No active session is running right now." in session_html
    assert "The chat composer unlocks as soon as the DM begins a session." in session_html


def test_player_session_page_includes_lazy_wiki_lookup_widget(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Wiki article lookup" in session_html
    assert 'data-session-wiki-lookup-root' in session_html
    assert 'data-session-wiki-lookup-query' in session_html
    assert 'data-session-wiki-lookup-results' in session_html
    assert 'data-session-wiki-lookup-preview' in session_html
    assert 'data-loading="0"' in session_html
    assert 'aria-busy="false"' in session_html
    assert "Search player-visible wiki articles and read them here without leaving the live session page." in session_html
    assert "Type at least 2 letters to search player-visible wiki articles." in session_html
    assert "Search and choose a player-visible wiki article to read it here." in session_html


def test_session_page_only_shows_character_tab_for_users_with_session_character_access(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    party_page = client.get("/campaigns/linden-pass/session")

    assert party_page.status_code == 200
    party_html = party_page.get_data(as_text=True)
    assert "/campaigns/linden-pass/session/character" not in party_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    owner_page = client.get("/campaigns/linden-pass/session")

    assert owner_page.status_code == 200
    owner_html = owner_page.get_data(as_text=True)
    assert "/campaigns/linden-pass/session/character" in owner_html
    assert f'/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}' in owner_html
    assert ">Character<" in owner_html


def test_session_character_page_defaults_to_viewer_assigned_character(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Choose a character" not in html
    assert "Arden March" in html
    assert "Features and traits" not in html
    assert "Character sections" in html
    assert "combat-workspace-card" in html
    assert "combat-workspace-nav" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=spells" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=features" in html


def test_owner_can_open_session_character_subpage_without_leaving_session_feature(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=features"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Session Character" in html
    assert "Character chooser" in html
    assert "Character sections" in html
    assert "Arden March" in html
    assert "Features and traits" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=spells" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=features" in html
    assert "Enter session mode" not in html
    assert "Save personal details" not in html


def test_session_character_page_shows_edit_controls_only_while_session_is_active(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=overview"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Save vitals" in html
    assert 'name="return_view" value="session-character"' in html
    assert (
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
        "&amp;page=overview&amp;confirm_rest=short"
    ) in html


def test_session_character_page_explains_active_session_edit_scope(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=overview"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Session editing scope" in html
    assert "Edit here during an active session" in html
    assert "Vitals and rests on Overview" in html
    assert "Tracked resource counts and spell slot usage" in html
    assert "Inventory quantities and currency totals" in html
    assert "Player notes" in html
    assert "Use the full character page for" in html
    assert "Portrait, physical description, and background details" in html
    assert "Spell-list changes and other non-slot spell management" in html


def test_session_character_personal_updates_stay_on_full_character_page(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    personal_page = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=personal"
    )

    assert personal_page.status_code == 200
    personal_html = personal_page.get_data(as_text=True)
    assert "Save personal details" not in personal_html
    assert (
        "Portrait, physical description, and background changes stay on the full character page "
        "so this Session surface stays focused on live play."
    ) in personal_html
    assert f'/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}?page=personal' in personal_html

    record = get_character(ASSIGNED_CHARACTER_SLUG)
    assert record is not None
    original_notes = dict(record.state_record.state.get("notes") or {})

    response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/session/personal",
        data={
            "expected_revision": record.state_record.revision,
            "physical_description_markdown": "Session-only personal edit.",
            "background_markdown": "Should stay off the Session tab.",
            "mode": "session",
            "page": "personal",
            "return_view": "session-character",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Save personal details" not in html
    assert (
        "Portrait, physical description, and background changes stay on the full character page "
        "so this Session surface stays focused on live play."
    ) in html

    updated = get_character(ASSIGNED_CHARACTER_SLUG)
    assert updated is not None
    updated_notes = dict(updated.state_record.state.get("notes") or {})
    assert updated_notes.get("physical_description_markdown") == original_notes.get("physical_description_markdown")
    assert updated_notes.get("background_markdown") == original_notes.get("background_markdown")


def test_session_character_state_save_redirects_back_to_session_surface(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    record = get_character(ASSIGNED_CHARACTER_SLUG)
    assert record is not None

    response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": 34,
            "temp_hp": 3,
            "mode": "session",
            "page": "overview",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
        "&page=overview#session-vitals"
    ) in response.headers["Location"]

    updated = get_character(ASSIGNED_CHARACTER_SLUG)
    assert updated is not None
    assert updated.state_record.state["vitals"]["current_hp"] == 34
    assert updated.state_record.state["vitals"]["temp_hp"] == 3


def test_session_character_note_conflict_stays_on_session_surface(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    record = get_character(ASSIGNED_CHARACTER_SLUG)
    assert record is not None
    stale_revision = record.state_record.revision

    client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/session/resources/wild-die",
        data={"expected_revision": stale_revision, "current": 1},
        follow_redirects=False,
    )

    conflict = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/session/notes",
        data={
            "expected_revision": stale_revision,
            "player_notes_markdown": "Draft note from the session character tab.",
            "mode": "session",
            "page": "notes",
            "return_view": "session-character",
        },
        follow_redirects=True,
    )

    assert conflict.status_code == 409
    html = conflict.get_data(as_text=True)
    assert "Session Character" in html
    assert "Save note" in html
    assert "Draft note from the session character tab." in html
    assert "This sheet changed in another session. Refresh the page and try again." in html


def test_session_character_page_uses_combat_style_non_combat_section_nav(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "combat-workspace-card" in html
    assert "combat-workspace-nav" in html
    assert "Overview" in html
    assert "Spells" in html
    assert "Resources" in html
    assert "Features" in html
    assert "Equipment" in html
    assert "Inventory" in html
    assert "Abilities and Skills" in html
    assert "Notes" in html
    assert "Personal" in html
    assert ">Quick Reference<" not in html
    assert ">Spellcasting<" not in html
    assert ">Actions<" not in html
    assert ">Bonus Actions<" not in html
    assert ">Reactions<" not in html


def test_session_character_route_blocks_unassigned_player_from_explicit_character_access(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
    )

    assert response.status_code == 403


def test_session_character_legacy_page_aliases_stay_compatible(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    overview_response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=quick"
    )
    assert overview_response.status_code == 200
    overview_html = overview_response.get_data(as_text=True)
    assert "At a glance" in overview_html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=overview" in overview_html

    spells_response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=spellcasting"
    )
    assert spells_response.status_code == 200
    spells_html = spells_response.get_data(as_text=True)
    assert "Spells" in spells_html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=spells" in spells_html


def test_session_character_full_page_link_uses_nearest_sheet_context(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=resources"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        f'/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}?page=quick#character-quick-resources'
        in html
    )


def test_player_session_page_preserves_lookup_preview_during_article_load(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-session-live-root' in session_html
    assert 'data-loading="0"' in session_html
    assert "window.__playerWikiLiveUiTools" in session_html
    assert "uiStateTools.captureViewportAnchor(liveRoot)" in session_html
    assert 'const preserveExistingPreview = previewRoot.querySelector(".session-wiki-lookup-result") !== null;' in session_html
    assert 'liveRoot.dataset.loading = "1";' in session_html
    assert 'previewRoot.dataset.loading = isBusy ? "1" : "0";' in session_html
    assert 'previewRoot.setAttribute("aria-busy", isBusy ? "true" : "false");' in session_html


def test_session_loading_styles_do_not_dim_live_session_surfaces():
    css = Path("player_wiki/static/styles.css").read_text(encoding="utf-8")

    assert "session-live-root][data-loading" not in css


def test_session_dm_page_preserves_open_article_details_across_live_rerenders(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Open Detail Check",
            "body_markdown": "This article should keep its details state during live updates.",
        },
        follow_redirects=False,
    )

    session_page = client.get("/campaigns/linden-pass/session/dm")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-session-article-id="1"' in session_html
    assert 'const collectOpenSessionArticleIds = (root) => {' in session_html
    assert 'restoreOpenSessionArticleIds(stagedRoot, openSessionArticleIds);' in session_html
    assert 'restoreOpenSessionArticleIds(revealedRoot, openSessionArticleIds);' in session_html


def test_dm_can_open_session_page_and_session_dm_page(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")
    dm_page = client.get("/campaigns/linden-pass/session/dm")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Chat window" in session_html
    assert "Session controls" not in session_html
    assert '/campaigns/linden-pass/session/dm' in session_html
    assert "Back to wiki" not in session_html
    assert "Open DM page" not in session_html

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Session controls" in dm_html
    assert "Session article store" in dm_html
    assert "Chat logs" in dm_html
    assert "Back to wiki" not in dm_html
    assert "Open DM page" not in dm_html


def test_dm_can_start_session_and_player_can_post_messages(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    start = client.post("/campaigns/linden-pass/session/start", follow_redirects=True)

    assert start.status_code == 200
    start_html = start.get_data(as_text=True)
    assert "Session started. Players can now use the Session page chat." in start_html
    assert "Players can use the Session page chat" in start_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    post_message = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "We should check the contract before we sign anything."},
        follow_redirects=True,
    )

    assert post_message.status_code == 200
    body = post_message.get_data(as_text=True)
    assert "Message posted." in body
    assert "We should check the contract before we sign anything." in body


def test_session_start_and_message_support_async_partial_updates(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    start = client.post(
        "/campaigns/linden-pass/session/start",
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert start.status_code == 200
    start_payload = start.get_json()
    assert start_payload["ok"] is True
    assert start_payload["active_session_id"] == 1
    assert "Session started. Players can now use the Session page chat." in start_payload["flash_html"]
    assert "Players can use the Session page chat" in start_payload["status_html"]
    assert "composer_html" not in start_payload
    assert "Close session" in start_payload["controls_html"]

    post_message = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Keep watch on the stair while I inspect the seal."},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert post_message.status_code == 200
    message_payload = post_message.get_json()
    assert message_payload["ok"] is True
    assert "Message posted." in message_payload["flash_html"]
    assert "Keep watch on the stair while I inspect the seal." in message_payload["chat_html"]
    assert message_payload["anchor"] == "session-chat-compose"


def test_session_articles_stay_out_of_wiki_until_revealed_and_appear_in_chat(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Sealed Orders",
            "body_markdown": "Deliver the crate to the eastern gate before moonrise.",
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "Session article saved to the session store." in article_html
    assert "Sealed Orders" in article_html
    assert "Deliver the crate to the eastern gate before moonrise." in article_html

    search = client.get("/campaigns/linden-pass?q=Sealed+Orders")
    assert search.status_code == 200
    search_html = search.get_data(as_text=True)
    assert "No matching pages" in search_html
    assert "/campaigns/linden-pass/pages/" not in search_html

    reveal = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=True,
    )
    assert reveal.status_code == 200
    reveal_html = reveal.get_data(as_text=True)
    assert "Session article revealed on the player Session page and saved to the chat history." in reveal_html
    assert "Sealed Orders" in reveal_html
    assert "Deliver the crate to the eastern gate before moonrise." in reveal_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)
    assert player_view.status_code == 200
    assert "Sealed Orders" in player_html
    assert "Deliver the crate to the eastern gate before moonrise." in player_html


def test_dm_session_article_store_supports_manual_upload_and_lookup_modes(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    session_page = client.get("/campaigns/linden-pass/session/dm")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-session-article-mode-root' in session_html
    assert 'id="session-article-mode-manual"' in session_html
    assert 'id="session-article-mode-upload"' in session_html
    assert 'id="session-article-mode-wiki"' in session_html
    assert 'name="markdown_file"' in session_html
    assert 'name="referenced_image_file"' in session_html
    assert 'data-session-article-source-query' in session_html
    assert 'data-session-article-source-results' in session_html
    assert 'name="source_ref"' in session_html
    assert "Drag and drop a file here" in session_html
    assert "Browse" in session_html
    assert "Upload a UTF-8 Markdown file." in session_html
    assert "Search visible published wiki pages and accessible Systems entries" in session_html
    assert "Type at least 2 letters to search published wiki pages and Systems entries." in session_html


def test_dm_session_article_lookup_does_not_eager_load_source_choices(app, client, sign_in, users, monkeypatch):
    with app.app_context():
        page_store = app.extensions["campaign_page_store"]
        systems_service = app.extensions["systems_service"]

    def fail_page_search(*args, **kwargs):
        raise AssertionError("session DM page should not eagerly load article source search results")

    def fail_systems_search(*args, **kwargs):
        raise AssertionError("session DM page should not eagerly load Systems article source search results")

    monkeypatch.setattr(page_store, "search_page_records", fail_page_search)
    monkeypatch.setattr(systems_service, "search_entries_for_campaign", fail_systems_search)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    session_page = client.get("/campaigns/linden-pass/session/dm")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Search to load matching articles" in session_html
    assert "Captain Lyra Vale - Wiki" not in session_html


def test_player_session_wiki_lookup_does_not_eager_load_article_choices(app, client, sign_in, users, monkeypatch):
    with app.app_context():
        page_store = app.extensions["campaign_page_store"]

    def fail_page_search(*args, **kwargs):
        raise AssertionError("player session page should not eagerly load wiki lookup search results")

    monkeypatch.setattr(page_store, "search_page_records", fail_page_search)

    sign_in(users["party"]["email"], users["party"]["password"])
    session_page = client.get("/campaigns/linden-pass/session")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Search to load matching articles" in session_html
    assert "Captain Lyra Vale - NPCs" not in session_html


def test_dm_can_search_session_article_sources(client, sign_in, users, app, tmp_path):
    goblin_slug = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    wiki_search = client.get(
        "/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers=_async_headers(),
    )
    assert wiki_search.status_code == 200
    wiki_payload = wiki_search.get_json()
    assert wiki_payload["results"]
    captain_result = next(
        result for result in wiki_payload["results"] if result["source_ref"] == "npcs/captain-lyra-vale"
    )
    assert captain_result["source_kind"] == "page"
    assert captain_result["title"] == "Captain Lyra Vale"

    systems_search = client.get(
        "/campaigns/linden-pass/session/article-sources/search?q=gob",
        headers=_async_headers(),
    )
    assert systems_search.status_code == 200
    systems_payload = systems_search.get_json()
    assert systems_payload["results"]
    assert systems_payload["results"][0]["source_kind"] == "systems"
    assert systems_payload["results"][0]["source_ref"] == f"systems:{goblin_slug}"
    assert systems_payload["results"][0]["title"] == "Goblin"
    assert systems_payload["results"][0]["subtitle"] == "Monsters - MM"


def test_player_can_search_player_visible_session_wiki_articles(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    visible_search = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/search?q=capt",
        headers=_async_headers(),
    )
    assert visible_search.status_code == 200
    visible_payload = visible_search.get_json()
    assert visible_payload["results"]
    assert any(result["page_ref"] == "npcs/captain-lyra-vale" for result in visible_payload["results"])

    future_search = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/search?q=future-facing mission",
        headers=_async_headers(),
    )
    assert future_search.status_code == 200
    assert future_search.get_json()["results"] == []

    unpublished_search = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/search?q=hidden-content behavior",
        headers=_async_headers(),
    )
    assert unpublished_search.status_code == 200
    assert unpublished_search.get_json()["results"] == []


def test_player_can_load_inline_session_wiki_lookup_preview(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    preview = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/preview?page_ref=notes/operations-brief",
        headers=_async_headers(),
    )

    assert preview.status_code == 200
    preview_payload = preview.get_json()
    assert "Operations Brief" in preview_payload["preview_html"]
    assert "All crew members are expected to keep a low profile" in preview_payload["preview_html"]
    assert 'target="_blank"' in preview_payload["preview_html"]
    assert "/campaigns/linden-pass/pages/notes/operations-brief" in preview_payload["preview_html"]


def test_player_session_wiki_lookup_respects_player_visibility_floor_for_dm_viewer(
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", wiki="dm")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    search = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/search?q=capt",
        headers=_async_headers(),
    )

    assert search.status_code == 200
    payload = search.get_json()
    assert payload["results"] == []
    assert payload["message"] == "No player-visible wiki articles are available right now."


def test_dm_can_pull_visible_wiki_page_into_session_article_store(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "wiki",
            "source_ref": "npcs/captain-lyra-vale",
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "Published wiki page pulled into the session store." in article_html
    assert 'id="session-article-mode-wiki"' in article_html
    assert 'value="wiki"' in article_html
    assert 'checked' in article_html
    assert "Captain Lyra Vale" in article_html
    assert "Harbor watch captain and trusted ally of the crew." in article_html
    assert "View published page" in article_html
    assert "/campaigns/linden-pass/pages/npcs/captain-lyra-vale" in article_html
    assert "/campaigns/linden-pass/session-article-images/1" in article_html
    assert "Convert to wiki page" not in article_html

    with client.application.app_context():
        session_service = client.application.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)
        image = session_service.get_article_image("linden-pass", 1)

    assert article is not None
    assert article.title == "Captain Lyra Vale"
    assert article.source_page_ref == "npcs/captain-lyra-vale"
    assert image is not None
    assert image.filename == "captain-lyra-vale.png"
    assert image.alt_text == "Portrait of Captain Lyra Vale."
    assert image.caption == "Harbor watch captain and trusted ally of the crew."


def test_dm_can_pull_systems_entry_into_session_article_store(client, sign_in, users, app, tmp_path):
    goblin_slug = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "wiki",
            "source_ref": f"systems:{goblin_slug}",
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "Systems entry pulled into the session store." in article_html
    assert "Goblin" in article_html
    assert "Scimitar" in article_html
    assert f"/campaigns/linden-pass/systems/entries/{goblin_slug}" in article_html
    assert "View Systems entry" in article_html
    assert "Convert to wiki page" not in article_html

    with client.application.app_context():
        session_service = client.application.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)

    assert article is not None
    assert article.title == "Goblin"
    assert article.source_page_ref == f"systems:{goblin_slug}"
    assert "<p>" in article.body_markdown
    assert "Scimitar" in article.body_markdown


def test_pulled_wiki_page_can_be_revealed_in_session_chat(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "wiki",
            "source_ref": "notes/operations-brief",
        },
        follow_redirects=False,
    )

    reveal = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=True,
    )

    assert reveal.status_code == 200
    reveal_html = reveal.get_data(as_text=True)
    assert "Session article revealed on the player Session page and saved to the chat history." in reveal_html
    assert "Operations Brief" in reveal_html
    assert "All crew members are expected to keep a low profile" in reveal_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)

    assert player_view.status_code == 200
    assert "Operations Brief" in player_html
    assert "All crew members are expected to keep a low profile" in player_html


def test_pulled_systems_entry_can_be_revealed_in_session_chat(client, sign_in, users, app, tmp_path):
    goblin_slug = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "wiki",
            "source_ref": f"systems:{goblin_slug}",
        },
        follow_redirects=False,
    )

    reveal = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=True,
    )

    assert reveal.status_code == 200
    reveal_html = reveal.get_data(as_text=True)
    assert "Session article revealed on the player Session page and saved to the chat history." in reveal_html
    assert "Goblin" in reveal_html
    assert "Scimitar" in reveal_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)

    assert player_view.status_code == 200
    assert "Goblin" in player_html
    assert "Scimitar" in player_html


def test_dm_can_upload_markdown_file_into_session_article(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    markdown_bytes = (
        b"---\n"
        b"title: Ferry Note\n"
        b"---\n"
        b"# Ferry Note\n\n"
        b"Meet the ferryman at dusk.\n\n"
        b"Bring no lanterns.\n"
    )

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "upload",
            "markdown_file": (BytesIO(markdown_bytes), "ferry-note.md"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "Session article saved to the session store." in article_html
    assert 'id="session-article-mode-upload"' in article_html
    assert 'value="upload"' in article_html
    assert 'checked' in article_html
    assert "Ferry Note" in article_html
    assert "Meet the ferryman at dusk." in article_html
    assert "Bring no lanterns." in article_html

    with client.application.app_context():
        session_service = client.application.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)

    assert article is not None
    assert article.title == "Ferry Note"
    assert article.body_markdown == "Meet the ferryman at dusk.\n\nBring no lanterns."


def test_dm_can_upload_markdown_file_with_frontmatter_image_reference(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    markdown_bytes = (
        b"---\n"
        b"title: Ferry Token\n"
        b"image: notes/ferry-token.png\n"
        b"image_alt: A brass ferry token stamped with the river mark.\n"
        b"image_caption: Found tucked into the courier's satchel.\n"
        b"---\n"
        b"Use this token at the eastern dock after sunset.\n"
    )

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "upload",
            "markdown_file": (BytesIO(markdown_bytes), "ferry-token.md"),
            "referenced_image_file": (BytesIO(TEST_PNG_BYTES), "ferry-token.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "Session article saved to the session store." in article_html
    assert "/campaigns/linden-pass/session-article-images/1" in article_html
    assert "Found tucked into the courier&#39;s satchel." in article_html
    assert "Use this token at the eastern dock after sunset." in article_html

    with client.application.app_context():
        session_service = client.application.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)
        image = session_service.get_article_image("linden-pass", 1)

    assert article is not None
    assert article.title == "Ferry Token"
    assert image is not None
    assert image.filename == "ferry-token.png"
    assert image.alt_text == "A brass ferry token stamped with the river mark."
    assert image.caption == "Found tucked into the courier's satchel."
    assert image.data_blob == TEST_PNG_BYTES


def test_dm_can_upload_markdown_file_with_inline_image_reference(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    markdown_bytes = (
        b"# Ferry Token\n\n"
        b"![A brass ferry token](ferry-token.png \"Found tucked into the courier's satchel.\")\n\n"
        b"Use this token at the eastern dock after sunset.\n"
    )

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "upload",
            "markdown_file": (BytesIO(markdown_bytes), "ferry-token.md"),
            "referenced_image_file": (BytesIO(TEST_PNG_BYTES), "ferry-token.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "Session article saved to the session store." in article_html
    assert "/campaigns/linden-pass/session-article-images/1" in article_html
    assert "Found tucked into the courier&#39;s satchel." in article_html
    assert "Use this token at the eastern dock after sunset." in article_html

    with client.application.app_context():
        session_service = client.application.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)
        image = session_service.get_article_image("linden-pass", 1)

    assert article is not None
    assert article.title == "Ferry Token"
    assert article.body_markdown == "Use this token at the eastern dock after sunset."
    assert image is not None
    assert image.filename == "ferry-token.png"
    assert image.alt_text == "A brass ferry token"
    assert image.caption == "Found tucked into the courier's satchel."


def test_upload_mode_requires_referenced_image_file_when_markdown_points_to_one(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    markdown_bytes = (
        b"---\n"
        b"title: Ferry Token\n"
        b"image: notes/ferry-token.png\n"
        b"---\n"
        b"Use this token at the eastern dock after sunset.\n"
    )

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": "upload",
            "markdown_file": (BytesIO(markdown_bytes), "ferry-token.md"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    article_html = create_article.get_data(as_text=True)
    assert "This markdown file references an image. Upload the referenced image file too." in article_html
    assert "Ferry Token" not in article_html

    with client.application.app_context():
        session_service = client.application.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)

    assert article is None


def test_session_articles_support_images_with_dm_only_staging_access(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Portrait of the Courier",
            "body_markdown": "The courier's seal matches the crate markings.",
            "image_alt": "A courier wearing a wax-sealed satchel.",
            "image_caption": "Recovered from the courier's effects.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "courier-portrait.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    create_html = create_article.get_data(as_text=True)
    assert "/campaigns/linden-pass/session-article-images/1" in create_html
    assert "Recovered from the courier&#39;s effects." in create_html

    dm_image = client.get("/campaigns/linden-pass/session-article-images/1")
    assert dm_image.status_code == 200
    assert dm_image.mimetype == "image/png"
    assert dm_image.data == TEST_PNG_BYTES

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    staged_player_view = client.get("/campaigns/linden-pass/session")
    staged_player_html = staged_player_view.get_data(as_text=True)
    assert staged_player_view.status_code == 200
    assert "/campaigns/linden-pass/session-article-images/1" not in staged_player_html

    blocked_staged_image = client.get("/campaigns/linden-pass/session-article-images/1")
    assert blocked_staged_image.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post("/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=False)
    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)

    assert close.status_code == 302

    log_response = client.get(close.headers["Location"])
    log_html = log_response.get_data(as_text=True)
    assert log_response.status_code == 200
    assert "/campaigns/linden-pass/session-article-images/1" in log_html
    assert "Recovered from the courier&#39;s effects." in log_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    player_live_image = client.get("/campaigns/linden-pass/session-article-images/1")
    assert player_live_image.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Second Portrait",
            "body_markdown": "This one should show up live for the table.",
            "image_alt": "A second courier portrait.",
            "image_caption": "Displayed during the live reveal.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "second-portrait.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/articles/2/reveal", follow_redirects=False)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    revealed_player_view = client.get("/campaigns/linden-pass/session")
    revealed_player_html = revealed_player_view.get_data(as_text=True)
    assert revealed_player_view.status_code == 200
    assert "/campaigns/linden-pass/session-article-images/2" in revealed_player_html
    assert "Displayed during the live reveal." in revealed_player_html

    player_image = client.get("/campaigns/linden-pass/session-article-images/2")
    assert player_image.status_code == 200
    assert player_image.mimetype == "image/png"
    assert player_image.data == TEST_PNG_BYTES

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["outsider"]["email"], users["outsider"]["password"])

    outsider_image = client.get("/campaigns/linden-pass/session-article-images/2")
    assert outsider_image.status_code == 404


def test_player_session_live_state_endpoint_returns_updated_status_and_chat(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Check the courier's seal before opening the satchel."},
        follow_redirects=False,
    )

    live_state = client.get("/campaigns/linden-pass/session/live-state")

    assert live_state.status_code == 200
    payload = live_state.get_json()
    assert payload["active_session_id"] == 1
    assert "The session is live for players and the DM." in payload["status_html"]
    assert "Check the courier&#39;s seal before opening the satchel." in payload["chat_html"]

    client.post("/campaigns/linden-pass/session/close", follow_redirects=False)
    closed_state = client.get("/campaigns/linden-pass/session/live-state")
    closed_payload = closed_state.get_json()

    assert closed_state.status_code == 200
    assert closed_payload["active_session_id"] is None
    assert "No active session is running right now." in closed_payload["status_html"]
    assert "When the DM begins a session" in closed_payload["chat_html"]
    assert "controls_html" not in closed_payload


def test_dm_session_live_state_endpoint_returns_manager_payload_without_chat_or_composer(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Check the courier's seal before opening the satchel."},
        follow_redirects=False,
    )

    live_state = client.get("/campaigns/linden-pass/session/live-state?view=dm")

    assert live_state.status_code == 200
    payload = live_state.get_json()
    assert payload["active_session_id"] == 1
    assert "Players can use the Session page chat" in payload["status_html"]
    assert "Close session" in payload["controls_html"]
    assert "chat_html" not in payload
    assert "composer_html" not in payload


def test_session_live_state_short_circuits_when_revision_and_view_token_match(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    initial_live_state = client.get(
        "/campaigns/linden-pass/session/live-state?view=dm",
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
        "/campaigns/linden-pass/session/live-state?view=dm",
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

    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "This should advance the session live revision."},
        follow_redirects=False,
    )

    refreshed_live_state = client.get(
        "/campaigns/linden-pass/session/live-state?view=dm",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert refreshed_live_state.status_code == 200
    refreshed_payload = refreshed_live_state.get_json()
    assert refreshed_payload["changed"] is True
    assert refreshed_payload["live_revision"] > initial_payload["live_revision"]
    assert "controls_html" in refreshed_payload
    assert refreshed_live_state.headers["X-Live-State-Changed"] == "true"
    _assert_live_diagnostics_headers(refreshed_live_state)


def test_live_session_chat_shows_newest_entries_first_but_saved_log_stays_chronological(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Oldest live line."},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Middle Reveal",
            "body_markdown": "Middle reveal body.",
        },
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Newest live line."},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    live_page = client.get("/campaigns/linden-pass/session")
    live_html = live_page.get_data(as_text=True)

    assert live_page.status_code == 200
    newest_index = live_html.find("Newest live line.")
    reveal_index = live_html.find("Middle Reveal")
    oldest_index = live_html.find("Oldest live line.")
    assert -1 not in {newest_index, reveal_index, oldest_index}
    assert newest_index < reveal_index < oldest_index

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)
    assert close.status_code == 302

    log_response = client.get(close.headers["Location"])
    log_html = log_response.get_data(as_text=True)

    assert log_response.status_code == 200
    oldest_log_index = log_html.find("Oldest live line.")
    reveal_log_index = log_html.find("Middle Reveal")
    newest_log_index = log_html.find("Newest live line.")
    assert -1 not in {oldest_log_index, reveal_log_index, newest_log_index}
    assert oldest_log_index < reveal_log_index < newest_log_index


def test_live_session_chat_order_respects_viewer_preference(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "First line for preference test."},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Second line for preference test."},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    client.post(
        "/account/session-chat-order",
        data={"session_chat_order": "oldest_first"},
        follow_redirects=False,
    )

    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)

    assert player_view.status_code == 200
    first_index = player_html.find("First line for preference test.")
    second_index = player_html.find("Second line for preference test.")
    assert -1 not in {first_index, second_index}
    assert first_index < second_index

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_view = client.get("/campaigns/linden-pass/session")
    dm_html = dm_view.get_data(as_text=True)

    assert dm_view.status_code == 200
    dm_first_index = dm_html.find("First line for preference test.")
    dm_second_index = dm_html.find("Second line for preference test.")
    assert -1 not in {dm_first_index, dm_second_index}
    assert dm_second_index < dm_first_index


def test_session_articles_remain_visible_after_navigation_with_live_session(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Dock Ledger",
            "body_markdown": "Keep this staged while the live session is running.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Gate Pass",
            "body_markdown": "Reveal this while the table is still in session.",
        },
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/articles/2/reveal", follow_redirects=False)

    other_page = client.get("/campaigns/linden-pass")
    assert other_page.status_code == 200

    returned_page = client.get("/campaigns/linden-pass/session/dm")
    returned_html = returned_page.get_data(as_text=True)

    assert returned_page.status_code == 200
    assert "Dock Ledger" in returned_html
    assert "Keep this staged while the live session is running." in returned_html
    assert "Gate Pass" in returned_html
    assert "Reveal this while the table is still in session." in returned_html

    live_state = client.get("/campaigns/linden-pass/session/live-state?view=dm")
    payload = live_state.get_json()

    assert live_state.status_code == 200
    assert payload["active_session_id"] == 1
    assert "Dock Ledger" in payload["staged_articles_html"]
    assert "Keep this staged while the live session is running." in payload["staged_articles_html"]
    assert "Gate Pass" in payload["revealed_articles_html"]
    assert "Reveal this while the table is still in session." in payload["revealed_articles_html"]


def test_session_articles_remain_visible_after_navigation_without_live_session(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Unsent Orders",
            "body_markdown": "This should stay staged after the session ends.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Read Aloud Notice",
            "body_markdown": "This should stay listed as revealed after the session ends.",
        },
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/articles/2/reveal", follow_redirects=False)
    client.post("/campaigns/linden-pass/session/close", follow_redirects=False)

    other_page = client.get("/campaigns/linden-pass")
    assert other_page.status_code == 200

    returned_page = client.get("/campaigns/linden-pass/session/dm")
    returned_html = returned_page.get_data(as_text=True)

    assert returned_page.status_code == 200
    assert "No active session is running right now." in returned_html
    assert "Unsent Orders" in returned_html
    assert "This should stay staged after the session ends." in returned_html
    assert "Read Aloud Notice" in returned_html
    assert "This should stay listed as revealed after the session ends." in returned_html

    closed_state = client.get("/campaigns/linden-pass/session/live-state?view=dm")
    payload = closed_state.get_json()

    assert closed_state.status_code == 200
    assert payload["active_session_id"] is None
    assert "Unsent Orders" in payload["staged_articles_html"]
    assert "This should stay staged after the session ends." in payload["staged_articles_html"]
    assert "Read Aloud Notice" in payload["revealed_articles_html"]
    assert "This should stay listed as revealed after the session ends." in payload["revealed_articles_html"]


def test_dm_can_convert_session_article_into_published_wiki_page(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )

    create_article = isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Courier Seal",
            "body_markdown": "This note should become a published wiki document.",
            "image_alt": "A stamped courier seal.",
            "image_caption": "Shown to the party after the reveal.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "courier-seal.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert create_article.status_code == 302

    convert_page = isolated_campaign_client.get("/campaigns/linden-pass/session/articles/1/convert")
    assert convert_page.status_code == 200
    convert_html = convert_page.get_data(as_text=True)
    assert "Publish settings" in convert_html
    assert "Courier Seal" in convert_html

    publish_response = isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles/1/convert",
        data={
            "title": "Courier Seal",
            "slug_leaf": "courier-seal",
            "summary": "A recovered courier handout for the party reference.",
            "section": "Notes",
            "page_type": "note",
            "subsection": "",
            "reveal_after_session": "2",
        },
        follow_redirects=False,
    )

    assert publish_response.status_code == 302
    assert publish_response.headers["Location"].endswith("/campaigns/linden-pass/pages/notes/courier-seal")

    page_response = isolated_campaign_client.get(publish_response.headers["Location"])
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Courier Seal" in page_html
    assert "This note should become a published wiki document." in page_html
    assert '/campaigns/linden-pass/assets/session-articles/article-1-courier-seal.png' in page_html
    assert "Shown to the party after the reveal." in page_html

    campaigns_dir = isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
    published_file = campaigns_dir / "linden-pass" / "content" / "notes" / "courier-seal.md"
    published_text = published_file.read_text(encoding="utf-8")
    assert "source_ref: session-article:linden-pass:1" in published_text
    assert "section: Notes" in published_text
    assert "type: note" in published_text
    assert "image: session-articles/article-1-courier-seal.png" in published_text

    published_asset = campaigns_dir / "linden-pass" / "assets" / "session-articles" / "article-1-courier-seal.png"
    assert published_asset.read_bytes() == TEST_PNG_BYTES

    session_page = isolated_campaign_client.get("/campaigns/linden-pass/session/dm")
    session_html = session_page.get_data(as_text=True)
    assert session_page.status_code == 200
    assert "View published page" in session_html
    assert "/campaigns/linden-pass/pages/notes/courier-seal" in session_html


def test_dm_can_delete_staged_session_article(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Temporary Briefing",
            "body_markdown": "This staged article should be removable.",
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    assert "Temporary Briefing" in create_article.get_data(as_text=True)

    delete_article = client.post(
        "/campaigns/linden-pass/session/articles/1/delete",
        follow_redirects=True,
    )

    assert delete_article.status_code == 200
    delete_html = delete_article.get_data(as_text=True)
    assert "Session article deleted." in delete_html
    assert "Temporary Briefing" not in delete_html
    assert "This staged article should be removable." not in delete_html


def test_dm_can_delete_revealed_article_and_remove_it_from_chat_and_logs(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Burn After Reading",
            "body_markdown": "This revealed article should disappear cleanly.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=False,
    )

    delete_article = client.post(
        "/campaigns/linden-pass/session/articles/1/delete",
        follow_redirects=True,
    )

    assert delete_article.status_code == 200
    delete_html = delete_article.get_data(as_text=True)
    assert "Session article deleted. Related reveal entries were removed from chat and logs." in delete_html
    assert "Burn After Reading" not in delete_html
    assert "This revealed article should disappear cleanly." not in delete_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)
    assert player_view.status_code == 200
    assert "Burn After Reading" not in player_html
    assert "This revealed article should disappear cleanly." not in player_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)
    assert close.status_code == 302
    log_response = client.get(close.headers["Location"])
    log_html = log_response.get_data(as_text=True)
    assert log_response.status_code == 200
    assert "Burn After Reading" not in log_html
    assert "This revealed article should disappear cleanly." not in log_html


def test_dm_can_close_session_and_access_chat_log_but_player_cannot(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Keep this exchange in the session log."},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Ashcombe Note",
            "body_markdown": "The meeting has moved to the ash yard.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=False,
    )

    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)

    assert close.status_code == 302
    log_path = close.headers["Location"]
    assert "/campaigns/linden-pass/session/logs/" in log_path

    log_response = client.get(log_path)
    assert log_response.status_code == 200
    log_html = log_response.get_data(as_text=True)
    assert "Stored chat log" in log_html
    assert "Keep this exchange in the session log." in log_html
    assert "Ashcombe Note" in log_html
    assert "The meeting has moved to the ash yard." in log_html

    session_page = client.get("/campaigns/linden-pass/session/dm")
    session_html = session_page.get_data(as_text=True)
    assert "No active session is running right now." in session_html
    assert "Session log from" in session_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked_log = client.get(log_path)
    assert blocked_log.status_code == 403


def test_dm_can_delete_closed_chat_log(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "This log should be removable."},
        follow_redirects=False,
    )
    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)

    assert close.status_code == 302
    log_path = close.headers["Location"]

    delete_response = client.post(
        "/campaigns/linden-pass/session/logs/1/delete",
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    delete_html = delete_response.get_data(as_text=True)
    assert "Chat log deleted." in delete_html
    assert "Session log from" not in delete_html

    deleted_log = client.get(log_path)
    assert deleted_log.status_code == 404


def test_player_cannot_delete_closed_chat_log(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)
    assert close.status_code == 302

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    blocked_delete = client.post(
        "/campaigns/linden-pass/session/logs/1/delete",
        follow_redirects=False,
    )

    assert blocked_delete.status_code == 403


def test_player_cannot_delete_session_article(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Protected Article",
            "body_markdown": "Players should not be able to delete this.",
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    blocked_delete = client.post(
        "/campaigns/linden-pass/session/articles/1/delete",
        follow_redirects=False,
    )

    assert blocked_delete.status_code == 403


def test_observer_cannot_open_session_page_when_session_visibility_is_players(client, sign_in, users):
    sign_in(users["observer"]["email"], users["observer"]["password"])

    page = client.get("/campaigns/linden-pass/session")
    dm_page = client.get("/campaigns/linden-pass/session/dm")
    post_message = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Observer comment"},
        follow_redirects=False,
    )
    start_session = client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    assert page.status_code == 404
    assert dm_page.status_code == 404
    assert post_message.status_code == 404
    assert start_session.status_code == 404
