from __future__ import annotations

from tests.helpers.character_state_helpers import (
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.helpers.systems_import_helpers import _import_systems_goblin
from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import inspect
import json
import re
import shutil
import time
from io import BytesIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import yaml

import pytest
from werkzeug.security import generate_password_hash

import player_wiki.app as app_module
from player_wiki.app import create_app
from player_wiki.auth_store import AuthStore
from player_wiki.campaign_content_service import prepare_campaign_page_write
from player_wiki.campaign_session_service import CampaignSessionValidationError
from player_wiki.config import Config
from player_wiki.db import get_db, get_db_query_metrics, init_database, reset_db_query_metrics
from player_wiki.player_wiki_reconciliation import PlayerWikiReconciler, ReconciliationHooks
from player_wiki.session_article_publisher import (
    SessionArticlePublishError,
    SessionArticlePublishOptions,
    publish_session_article,
)
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG, build_test_campaigns_dir


TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
TEST_REPLACEMENT_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8"
    b"\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)

SESSION_DM_VIEW_KEYS = ("tools", "staged", "revealed", "article-store", "logs")


def assert_webp_bytes(data_blob: bytes) -> None:
    assert data_blob[:4] == b"RIFF"
    assert data_blob[8:12] == b"WEBP"


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _session_live_script_text() -> str:
    return (PROJECT_ROOT / "player_wiki" / "static" / "session-live.js").read_text(encoding="utf-8")


def _html_segment_after(html: str, marker: str, *, length: int = 2000) -> str:
    start = html.index(marker)
    return html[start : start + length]


def _html_segment_between(html: str, start_marker: str, end_marker: str) -> str:
    start = html.index(start_marker)
    end = html.index(end_marker, start + len(start_marker))
    return html[start:end]


def _inventory_item(record, item_ref: str) -> dict:
    return next(
        item
        for item in record.state_record.state.get("inventory", [])
        if str(item.get("catalog_ref") or item.get("id") or "") == item_ref
    )


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
    if "X-Live-Write-Count" in response.headers:
        assert response.headers["X-Live-Write-Count"]
        assert response.headers["X-Live-Write-Time-Ms"]
        assert response.headers["X-Live-Commit-Count"]
        assert response.headers["X-Live-Commit-Time-Ms"]


def _set_characters_system(app, system_code: str) -> None:
    characters_root = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters"
    for character_dir in sorted(characters_root.iterdir()):
        if not character_dir.is_dir():
            continue
        definition_path = character_dir / "definition.yaml"
        if not definition_path.is_file():
            continue
        payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
        payload["system"] = system_code
        definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _set_character_system(app, character_slug: str, system_code: str) -> None:
    payload_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    payload = yaml.safe_load(payload_path.read_text(encoding="utf-8")) or {}
    payload["system"] = system_code
    payload_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _find_combatant(app, *, character_slug: str):
    with app.app_context():
        for combatant in app.extensions["campaign_combat_service"].list_combatants("linden-pass"):
            if combatant.character_slug == character_slug:
                return combatant
    return None


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


def test_player_session_page_includes_global_search_widget(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-campaign-global-search-root' in session_html
    assert 'data-campaign-global-search-query' in session_html
    assert 'data-campaign-global-search-results' in session_html
    assert 'data-campaign-global-search-dialog' in session_html
    assert 'data-campaign-global-search-preview' in session_html
    assert 'data-session-wiki-lookup-root' not in session_html
    assert "Search player-visible wiki articles and read them here without leaving the live session page." not in session_html


@pytest.mark.parametrize("actor", ("party", "observer", "outsider"))
@pytest.mark.parametrize("query", ("", "?dm_view=unknown"))
def test_player_cannot_open_dm_session_workspace(client, sign_in, users, actor, query):
    sign_in(users[actor]["email"], users[actor]["password"])

    dm_page = client.get(f"/campaigns/linden-pass/session/dm{query}")

    assert dm_page.status_code == (403 if actor == "party" else 404)


@pytest.mark.parametrize("query", ("", "?dm_view=unknown", "?article_mode=upload&dm_view=unknown"))
def test_dm_session_bare_and_unknown_views_normalize_after_access_checks(
    client,
    sign_in,
    users,
    query,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(f"/campaigns/linden-pass/session/dm{query}", follow_redirects=False)

    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == "/campaigns/linden-pass/session/dm"
    assert parse_qs(location.query)["dm_view"] == ["tools"]
    if "article_mode=upload" in query:
        assert parse_qs(location.query)["article_mode"] == ["upload"]


def test_dm_session_valid_views_render_canonical_navigation_and_retained_dm_panes(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    for dm_view in SESSION_DM_VIEW_KEYS:
        response = client.get(f"/campaigns/linden-pass/session/dm?dm_view={dm_view}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert f'data-session-dm-active="{dm_view}"' in html
        assert html.count("data-session-dm-shell-root") == 1
        assert html.count('data-session-live-view="dm"') == 1
        for target in SESSION_DM_VIEW_KEYS:
            assert f'href="/campaigns/linden-pass/session/dm?dm_view={target}"' in html
        assert html.count('aria-current="page"') >= 1
        assert "Session DM tasks" in html
        assert "Session message composer" not in html
        assert html.count('data-session-dm-pane="tools"') == 1
        assert html.count('data-session-dm-pane="staged"') == 1
        assert html.count('data-session-dm-pane="revealed"') == 1
        assert html.count('data-session-dm-pane="article-store"') == 1
        assert html.count('data-session-dm-pane="logs"') == 1
        assert html.count("data-session-dm-pane-url=") == 5
        assert "data-session-dm-legacy-remainder" not in html
        assert html.count("data-session-staged-root") == 1
        assert html.count("data-session-revealed-root") == 1
        assert html.count("data-session-article-store-root") == 1
        assert html.count("data-session-logs-root") == 1
        if dm_view == "tools":
            assert html.count('id="session-controls"') == 1
            assert html.count("data-session-passive-scores-bar") == 1
            assert html.count('id="session-chat-logs"') == 0
        elif dm_view == "staged":
            assert html.count('id="session-controls"') == 0
            assert html.count("data-session-passive-scores-bar") == 0
            assert html.count('id="session-staged-articles"') == 1
            assert "No unrevealed session articles are waiting right now." in html
        elif dm_view == "revealed":
            assert html.count('id="session-controls"') == 0
            assert html.count("data-session-passive-scores-bar") == 0
            assert html.count('id="session-revealed-articles"') == 1
            assert "No revealed articles yet." in html
            assert "Clear all" not in html
        elif dm_view == "article-store":
            assert html.count('id="session-article-store"') == 1
            assert html.count("data-session-article-form") == 1
            assert "data-session-article-mutation-recovery" in html
            assert "article_mode=manual" in html
        elif dm_view == "logs":
            assert html.count('id="session-controls"') == 0
            assert html.count("data-session-passive-scores-bar") == 0
            assert html.count('id="session-chat-logs"') == 1
            assert "Chat logs" in html
        else:
            assert html.count('id="session-controls"') == 0
            assert html.count("data-session-passive-scores-bar") == 0
            assert html.count('id="session-chat-logs"') == 0


@pytest.mark.parametrize(
    ("dm_view", "expected_marker", "excluded_marker"),
    (
        ("tools", 'id="session-controls"', 'id="session-chat-logs"'),
        ("staged", 'id="session-staged-articles"', 'id="session-controls"'),
        ("revealed", 'id="session-revealed-articles"', 'id="session-controls"'),
        ("article-store", 'id="session-article-store"', 'id="session-controls"'),
        ("logs", 'id="session-chat-logs"', 'id="session-controls"'),
    ),
)
@pytest.mark.parametrize("manager", ("dm", "admin"))
def test_dm_session_retained_fragments_preserve_access_and_return_only_authorized_partial(
    client,
    sign_in,
    users,
    dm_view,
    expected_marker,
    excluded_marker,
    manager,
):
    sign_in(users[manager]["email"], users[manager]["password"])

    fragment = client.get(
        f"/campaigns/linden-pass/session/dm?dm_view={dm_view}",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert fragment.status_code == 200
    fragment_html = fragment.get_data(as_text=True)
    assert expected_marker in fragment_html
    assert excluded_marker not in fragment_html
    assert "data-session-dm-shell-root" not in fragment_html
    assert "data-session-live-root" not in fragment_html
    assert "Session DM tasks" not in fragment_html
    if dm_view == "staged":
        assert "No unrevealed session articles are waiting right now." in fragment_html
        assert "data-session-staged-root" not in fragment_html
    elif dm_view == "revealed":
        assert "No revealed articles yet." in fragment_html
        assert "Clear all" not in fragment_html
        assert "data-session-revealed-root" not in fragment_html
    elif dm_view == "article-store":
        assert "data-session-article-mode-root" in fragment_html
        assert "data-session-article-mutation-recovery" in fragment_html
        assert "data-session-article-store-root" not in fragment_html


@pytest.mark.parametrize("dm_view", ("logs", "revealed", "staged", "article-store"))
@pytest.mark.parametrize("actor", ("party", "observer", "outsider"))
def test_session_dm_fragment_requests_do_not_bypass_campaign_or_manager_access(
    client,
    sign_in,
    users,
    actor,
    dm_view,
):
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/dm?dm_view={dm_view}",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == (403 if actor == "party" else 404)


def test_dm_session_revealed_fragment_renders_content_and_scoped_clear_confirmation(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Revealed Fragment Token",
            "body_markdown": "Changed article content must remain manager-visible.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=False,
    )

    response = client.get(
        "/campaigns/linden-pass/session/dm?dm_view=revealed",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Revealed Fragment Token" in html
    assert "Changed article content must remain manager-visible." in html
    assert 'data-session-article-id="1"' in html
    assert 'data-presentation-dialog-trigger="session-clear-revealed-confirmation"' in html
    assert "data-session-dm-shell-root" not in html
    assert "data-session-revealed-root" not in html


def test_dm_session_staged_fragment_renders_editable_draft_and_actions(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Staged Fragment Draft",
            "body_markdown": "Retain this editable prep text.",
            "image_alt": "Staged fragment image.",
            "image_caption": "A retained staged caption.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "staged-fragment.png"),
        },
        follow_redirects=False,
    )

    response = client.get(
        "/campaigns/linden-pass/session/dm?dm_view=staged",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="session-staged-articles"' in html
    assert 'data-session-article-id="1"' in html
    assert 'class="stack-form session-article-edit-form"' in html
    for field_name in ("title", "body_markdown", "image_file", "image_alt", "image_caption"):
        assert f'name="{field_name}"' in html
    assert "Reveal in chat" in html
    assert "Open in Player Wiki editor" in html
    assert "Convert to wiki page" in html
    assert "Delete article" in html
    assert "data-session-dm-shell-root" not in html
    assert "data-session-staged-root" not in html


def test_staged_image_replacement_with_same_metadata_advances_token_and_cache_version(
    client,
    monkeypatch,
    sign_in,
    users,
):
    fixed_image_time = datetime(2026, 7, 20, 15, 30, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "player_wiki.campaign_session_store.utcnow",
        lambda: fixed_image_time,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Cache Stable Draft",
            "body_markdown": "The visible metadata remains unchanged.",
            "image_alt": "Stable image alt.",
            "image_caption": "Stable image caption.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "stable-image.png"),
        },
        follow_redirects=False,
    )
    initial_payload = client.get("/campaigns/linden-pass/session/live-state?view=dm").get_json()
    initial_image_url = re.search(
        r'src="([^"]*session-article-images/1\?v=[^"]+)"',
        initial_payload["staged_articles_html"],
    )
    assert initial_image_url is not None
    with client.application.app_context():
        initial_updated_at = get_db().execute(
            "SELECT updated_at FROM campaign_session_article_images WHERE article_id = 1"
        ).fetchone()["updated_at"]

    replacement = client.post(
        "/campaigns/linden-pass/session/articles/1",
        data={
            "title": "Cache Stable Draft",
            "body_markdown": "The visible metadata remains unchanged.",
            "image_alt": "Stable image alt.",
            "image_caption": "Stable image caption.",
            "image_file": (BytesIO(TEST_REPLACEMENT_PNG_BYTES), "stable-image.png"),
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert replacement.status_code == 200
    refreshed_payload = replacement.get_json()
    refreshed_image_url = re.search(
        r'src="([^"]*session-article-images/1\?v=[^"]+)"',
        refreshed_payload["staged_articles_html"],
    )
    assert refreshed_image_url is not None
    with client.application.app_context():
        refreshed_updated_at = get_db().execute(
            "SELECT updated_at FROM campaign_session_article_images WHERE article_id = 1"
        ).fetchone()["updated_at"]
    assert refreshed_updated_at == initial_updated_at
    assert refreshed_payload["manager_state_token"] != initial_payload["manager_state_token"]
    assert refreshed_image_url.group(1) != initial_image_url.group(1)
    assert client.get(refreshed_image_url.group(1).replace("&amp;", "&")).status_code == 200


def test_revealed_article_content_advances_manager_state_token_and_live_fragment(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    initial_state = client.get("/campaigns/linden-pass/session/live-state?view=dm")
    initial_payload = initial_state.get_json()

    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Manager Token Revealed Title",
            "body_markdown": "Manager token revealed body content.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=False,
    )
    refreshed_state = client.get("/campaigns/linden-pass/session/live-state?view=dm")
    refreshed_payload = refreshed_state.get_json()

    assert refreshed_state.status_code == 200
    assert refreshed_payload["manager_state_token"] != initial_payload["manager_state_token"]
    assert "Manager Token Revealed Title" in refreshed_payload["revealed_articles_html"]
    assert "Manager token revealed body content." in refreshed_payload["revealed_articles_html"]


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


def test_session_page_with_character_access_exposes_shell_switch_data_hooks(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")
    assert session_page.status_code == 200
    html = session_page.get_data(as_text=True)

    assert 'data-session-shell-root' in html
    assert 'data-session-shell-pane="session"' in html
    assert 'data-session-shell-pane="character"' in html
    assert 'data-session-switch="1"' in html
    assert 'data-session-switch-target="session"' in html
    assert 'data-session-switch-target="character"' in html
    assert 'data-session-live-view="session"' in html
    assert (
        f'data-session-switch-fragment-href="/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;fragment=1"'
        in html
    )
    assert (
        f'data-session-shell-pane-url="/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;fragment=1"'
        in html
    )
    assert '/static/session-shell.js?v=' in html
    assert '/static/session-live.js?v=' in html


def test_session_page_without_character_access_does_not_expose_shell_fragment_hooks(
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", session="public")
    sign_in(users["observer"]["email"], users["observer"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")
    assert session_page.status_code == 200
    html = session_page.get_data(as_text=True)

    assert "Session Character" not in html
    assert 'data-session-switch-target="character"' not in html
    assert 'data-session-shell-pane="character"' not in html
    assert 'data-session-switch-fragment-href="' not in html


def test_session_character_page_defaults_to_viewer_assigned_character(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Choose a character" not in html
    assert "Arden March" in html
    assert "Character sections" not in html
    assert "session-character-section-nav" in html
    assert "combat-workspace-nav" in html
    assert 'data-combat-section-group' in html
    assert 'data-combat-default-section="overview"' in html
    overview_panel = _html_segment_between(
        html,
        'data-combat-section-panel="overview"',
        'data-combat-section-panel="spells"',
    )
    features_panel = _html_segment_between(
        html,
        'data-combat-section-panel="features"',
        'data-combat-section-panel="equipment"',
    )
    assert "hidden" not in overview_panel
    assert "hidden" in features_panel
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=spells" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=features" in html


def test_session_character_fragment_route_returns_only_panel_html(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&fragment=1"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<html" not in html
    assert "<body" not in html
    assert '<section class="hero compact">' not in html
    assert 'data-session-shell-pane' not in html
    assert 'class="page-layout session-layout"' in html
    assert "Arden March" in html


def test_session_character_route_uses_shared_shell_when_fragment_not_requested(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<html" in html
    assert '<section class="hero compact">' in html
    assert "Session Workspace" in html
    assert "data-session-shell-root" in html
    assert 'data-session-shell-active="character"' in html
    assert 'data-session-shell-pane="session"' in html
    assert 'data-session-shell-pane="character"' in html
    assert 'data-session-live-view="session"' in html


def test_owner_can_open_session_character_subpage_without_leaving_session_feature(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=features"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Session Character" in html
    assert "Live session tools" not in html
    assert "Character chooser" not in html
    assert "Character sections" not in html
    assert "session-character-section-nav" in html
    assert "Arden March" in html
    assert "Features and traits" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=spells" in html
    assert f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&amp;page=features" in html
    assert "Enter session mode" not in html
    assert "Save personal details" not in html
    assert "/campaigns/linden-pass/session" in html
    assert 'href="/campaigns/linden-pass/help#session"' not in html


def test_session_character_equipment_page_filters_inventory_only_rows(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=equipment"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    equipment_panel = _html_segment_between(
        html,
        'data-combat-section-panel="equipment"',
        'data-combat-section-panel="inventory"',
    )
    inventory_panel = _html_segment_between(
        html,
        'data-combat-section-panel="inventory"',
        'data-combat-section-panel="abilities_skills"',
    )
    assert "Light Crossbow" in equipment_panel
    assert "Quarterstaff" in equipment_panel
    assert "Backpack" not in equipment_panel
    assert "Crossbow Bolts" not in equipment_panel
    assert "Chalk" not in equipment_panel
    assert "Backpack" in inventory_panel
    assert "Not attuned" not in equipment_panel
    assert "Save equipment state" not in equipment_panel
    assert 'data-character-spell-modal-trigger' in html
    assert "<summary>Item details</summary>" not in html


def test_session_character_page_keeps_single_sheet_players_out_of_a_redundant_roster_sidebar(
    client, sign_in, users
):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Live session tools" not in html
    assert "Character chooser" not in html
    assert ">Open Session<" not in html
    assert 'href="/campaigns/linden-pass/help#session"' not in html


def test_dm_session_character_page_keeps_character_chooser_for_cross_character_access(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Live session tools" not in html
    assert "Character chooser" in html
    assert "Open any session-enabled character sheet from the current campaign." in html


def test_dm_can_close_selected_session_character(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Session character" in html
    assert "Arden March" in html
    assert 'href="/campaigns/linden-pass/session/character?closed=1"' in html
    assert "Close character" in html

    closed_response = client.get("/campaigns/linden-pass/session/character?closed=1")

    assert closed_response.status_code == 200
    closed_html = closed_response.get_data(as_text=True)
    assert "Choose a character" in closed_html
    assert "Select a session-enabled character from the sidebar to open its sheet here." in closed_html
    assert "Character sections" not in closed_html
    assert "Close character" not in closed_html


def test_session_character_page_omits_permission_module_for_assigned_player(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Permission behavior" not in html
    assert "Current access: assigned-player access" not in html
    assert "Editing controls appear only during an active DM-started session" not in html
    assert "/campaigns/linden-pass/help#session" not in html
    assert "Open only their own session-enabled character here." not in html


def test_dm_session_character_page_omits_permission_module_for_cross_character_access(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Permission behavior" not in html
    assert "Current access: DM cross-character access" not in html
    assert "Open any session-enabled character sheet from the current campaign." in html


def test_admin_session_character_page_omits_permission_module_for_cross_character_access(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Permission behavior" not in html
    assert "Current access: admin cross-character access" not in html


def test_unassigned_player_session_character_page_explains_assignment_requirement(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No session character available" in html
    assert (
        "This account does not currently have a session-enabled character assigned in this "
        "campaign. Assigned players can open only their own session-enabled character here."
    ) in html
    assert "Current access:" not in html


def test_observer_session_character_page_explains_character_tab_is_unavailable(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", session="public")

    sign_in(users["observer"]["email"], users["observer"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Character tab unavailable" in html
    assert (
        "Observers stay on the main Session page. Only assigned players, DMs, and admins can "
        "open the Character surface."
    ) in html
    assert "Current access:" not in html


def test_session_character_page_shows_edit_controls_only_while_session_is_active(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=spells"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Current HP" in html
    assert "Save current HP" not in html
    assert "Save temp HP" not in html
    assert 'data-character-autosubmit' in html
    assert "Active session" not in html
    assert 'name="return_view" value="session-character"' in html
    assert (
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
        "&amp;page=spells&amp;confirm_rest=short"
    ) in html


def test_session_character_page_omits_active_session_edit_scope_note(
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
    assert "Session editing scope" not in html
    assert "Edit here during an active session" not in html
    assert "Session edits:" not in html
    assert "Full character page:" not in html
    assert "Vitals, rests, tracked resources, spell slots, equipment state, inventory quantities, " not in html
    assert (
        "Portrait page management, Advanced Editor reference text, spell-list changes, inventory add/remove work, "
        "and advanced maintenance."
    ) not in html
    assert "Character sections" not in html
    assert "session-character-section-nav" in html
    assert "Session character" in html


def test_session_character_page_omits_tracked_character_combat_shortcut_when_both_are_live(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": ASSIGNED_CHARACTER_SLUG, "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug=ASSIGNED_CHARACTER_SLUG)
    assert combatant is not None

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=overview"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Combat relationship" not in html
    assert "Prefer Combat:" not in html
    assert "Prefer Encounter status:" not in html
    assert "Combat relationship:" not in html
    assert "Open Combat" not in html
    assert "Open encounter status" not in html
    assert "The combat link keeps this character selected through the matching combatant deep link." not in html
    assert (
        "turn-by-turn movement, action economy, conditions, and turn order while the combat encounter is active."
    ) not in html
    assert (
        "Keep Session for the broader live-session workflow, rests, inventory quantities, "
        "currency, and player notes, plus HP/temp HP, tracked resources, and spell slot usage."
    ) not in html
    assert f"combatant={combatant.id}" not in html
    assert "At a glance" in html


def test_session_character_spells_page_combines_single_row_stats_into_slot_workspace(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=spells"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Spells" in html
    assert html.count("Charisma spellcasting") == 1
    assert html.count("Save DC 15") == 1
    assert html.count("Attack +7") == 1
    assert "Spell slots" in html
    assert "1st level" in html
    assert "4 available / 4" in html
    assert "2nd level" in html
    assert "3 available / 3" in html


def test_session_character_spells_summary_counts_always_prepared_current_spells(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["spellcasting"] = {
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_lanes": [
                {
                    "id": "class-row-1-slots",
                    "title": "Spell slots",
                    "shared": False,
                    "row_ids": ["class-row-1"],
                    "slot_progression": [
                        {"level": 1, "max_slots": 2},
                    ],
                },
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                    "caster_progression": "half",
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                    "slot_lane_id": "class-row-1-slots",
                },
            ],
            "spells": [
                {
                    "name": "Mending",
                    "spell_level": 0,
                    "mark": "Cantrip",
                    "class_row_id": "class-row-1",
                },
                {
                    "name": "Cure Wounds",
                    "spell_level": 1,
                    "mark": "Prepared",
                    "class_row_id": "class-row-1",
                },
                {
                    "name": "Magic Missile",
                    "spell_level": 1,
                    "mark": "",
                    "class_row_id": "class-row-1",
                    "is_always_prepared": True,
                    "grant_source_label": "Armorer",
                },
            ],
        }

    _write_character_definition(app, ASSIGNED_CHARACTER_SLUG, _mutate)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=spells"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    spells_panel = _html_segment_between(
        html,
        'data-combat-section-panel="spells"',
        'data-combat-section-panel="resources"',
    )
    assert "Cantrips" in spells_panel
    assert "Prepared spells" in spells_panel
    assert ">1</strong>" in _html_segment_after(spells_panel, "Cantrips", length=220)
    assert ">2</strong>" in _html_segment_after(spells_panel, "Prepared spells", length=220)
    assert "Always prepared" in spells_panel


def test_session_character_spells_page_keeps_multiclass_slot_pools_legible(
    app, client, sign_in, users
):
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
                    "name": "Detect Magic",
                    "casting_time": "1 action",
                    "range": "Self",
                    "duration": "10 minutes",
                    "components": "V, S",
                    "save_or_hit": "",
                    "source": "Wizard",
                    "reference": "page 20",
                    "mark": "Spellbook",
                    "class_row_id": "class-row-1",
                },
                {
                    "name": "Hex",
                    "casting_time": "1 bonus action",
                    "range": "90 feet",
                    "duration": "Concentration, up to 1 hour",
                    "components": "V, S, M",
                    "save_or_hit": "",
                    "source": "Warlock",
                    "reference": "page 24",
                    "mark": "Known",
                    "class_row_id": "class-row-2",
                },
            ],
        }

    _write_character_definition(app, ASSIGNED_CHARACTER_SLUG, _mutate)

    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=spells"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Wizard spell slots" in html
    assert "Warlock Pact Magic slots" in html
    assert "Wizard 3" in html
    assert "Warlock 2" in html
    assert html.count("Intelligence spellcasting") == 1
    assert html.count("Charisma spellcasting") == 1
    assert "Spell slot pools are shown below" not in html
    assert "Detect Magic" not in html
    assert "Hex" in html


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
    assert "Physical description and background are edited in Advanced Editor." in personal_html
    assert f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/edit" in personal_html
    assert "Open Advanced Editor" in personal_html

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
    assert "Physical description and background are edited in Advanced Editor." in html

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
    assert "session-character-section-nav" in html
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


def test_session_character_dnd_sections_mount_panels_and_workspace_script(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/session/character")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-combat-section-group' in html
    assert 'data-combat-section-toggle="overview"' in html
    assert 'data-combat-section-toggle="spells"' in html
    assert 'data-combat-section-panel="overview"' in html
    assert 'data-combat-section-panel="spells"' in html
    assert "window.__playerWikiCombatWorkspace" in html


def test_session_character_spells_direct_load_selects_spells_panel(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=spells"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-combat-default-section="spells"' in html
    spells_panel = _html_segment_between(
        html,
        'data-combat-section-panel="spells"',
        'data-combat-section-panel="resources"',
    )
    overview_panel = _html_segment_between(
        html,
        'data-combat-section-panel="overview"',
        'data-combat-section-panel="spells"',
    )
    assert "hidden" not in spells_panel.split(">", 1)[0]
    assert "hidden" in overview_panel.split(">", 1)[0]
    assert 'data-combat-section-toggle="spells"' in html
    assert 'aria-current="page"' in _html_segment_after(html, 'data-combat-section-toggle="spells"', length=250)


def test_session_character_active_controls_live_in_matching_dnd_panels(
    client,
    sign_in,
    users,
    set_campaign_visibility,
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
    overview_panel = _html_segment_between(
        html,
        'data-combat-section-panel="overview"',
        'data-combat-section-panel="spells"',
    )
    spells_panel = _html_segment_between(
        html,
        'data-combat-section-panel="spells"',
        'data-combat-section-panel="resources"',
    )
    resources_panel = _html_segment_between(
        html,
        'data-combat-section-panel="resources"',
        'data-combat-section-panel="features"',
    )
    inventory_panel = _html_segment_between(
        html,
        'data-combat-section-panel="inventory"',
        'data-combat-section-panel="abilities_skills"',
    )
    abilities_panel = _html_segment_between(
        html,
        'data-combat-section-panel="abilities_skills"',
        'data-combat-section-panel="notes"',
    )
    assert 'id="session-vitals"' in html
    assert f'name="page" value="overview"' in html
    assert 'data-character-sheet-edit-form="vitals"' not in overview_panel
    assert "glance-grid--quick-row-1" in overview_panel
    assert "glance-grid--quick-row-2" in overview_panel
    assert "glance-grid--quick-row-3" in overview_panel
    assert "glance-grid--quick-row-4" in overview_panel
    assert (
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
        "&amp;page=overview&amp;confirm_rest=short"
    ) in html
    assert 'data-character-sheet-edit-form="spell-slot"' in spells_panel
    assert "Use 1" not in spells_panel
    assert "Restore 1" not in spells_panel
    assert ">Save<" not in spells_panel
    assert "data-character-autosubmit" in spells_panel
    assert 'name="page" value="spells"' in spells_panel
    assert 'data-character-sheet-edit-form="resource"' in resources_panel
    assert "data-character-autosubmit" in resources_panel
    assert 'name="page" value="resources"' in resources_panel
    assert inventory_panel.count('data-character-sheet-edit-form="currency"') == 5
    assert inventory_panel.count('data-session-currency-autosubmit="1"') == 5
    assert inventory_panel.count('class="currency-grid"') == 1
    assert inventory_panel.find("Inventory and currency") < inventory_panel.find('class="currency-grid"')
    assert 'class="meta-badge">x' not in inventory_panel
    assert 'class="meta-badge">lb.' not in inventory_panel
    assert "<strong>x" not in inventory_panel
    assert "Tracked item" not in inventory_panel
    assert 'class="ability-grid ability-grid--skills"' in abilities_panel
    assert "ability-skill-list" in abilities_panel
    assert "<h3>Skills</h3>" not in abilities_panel


def test_session_character_inventory_row_links_and_details_adopt_shared_dialog(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item in enumerate(equipment_catalog):
            if str(item.get("id") or "") == "light-crossbow-1":
                equipment_catalog[index] = {
                    **dict(item),
                    "name": "Stormglass Compass",
                    "page_ref": "items/stormglass-compass",
                }
                break
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item in enumerate(inventory):
            if str(item.get("catalog_ref") or item.get("id") or "") == "light-crossbow-1":
                inventory[index] = {
                    **dict(item),
                    "name": "Stormglass Compass",
                    "notes": "A campaign-linked session inventory item.",
                }
                break
        payload["inventory"] = inventory

    _write_character_definition(app, ASSIGNED_CHARACTER_SLUG, _mutate_definition)
    _write_character_state(app, ASSIGNED_CHARACTER_SLUG, _mutate_state)

    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=inventory"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    inventory_panel = _html_segment_between(
        html,
        'data-combat-section-panel="inventory"',
        'data-combat-section-panel="abilities_skills"',
    )
    assert 'href="/campaigns/linden-pass/pages/items/stormglass-compass"' in inventory_panel
    assert "data-character-presentation-dialog-trigger-template" in inventory_panel
    assert 'data-character-spell-modal-trigger' in inventory_panel
    assert 'data-presentation-dialog-trigger="session-inventory-item-detail-' in inventory_panel
    assert 'data-character-spell-modal' in inventory_panel
    assert "data-presentation-dialog" in inventory_panel
    assert "data-presentation-dialog-close" in inventory_panel
    assert "data-presentation-dialog-initial-focus" in inventory_panel
    assert 'session-inventory-item-detail-' in inventory_panel
    assert 'aria-labelledby="session-inventory-item-detail-' in inventory_panel
    assert 'id="session-inventory-item-detail-' in inventory_panel
    assert '<details class="item-description-detail spell-card__fallback"' in inventory_panel
    assert "<summary>Item details</summary>" in inventory_panel
    assert "<noscript>" not in inventory_panel
    assert "A campaign-linked session inventory item." in inventory_panel

    fragment_response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
        "&page=inventory&fragment=1"
    )
    assert fragment_response.status_code == 200
    fragment_html = fragment_response.get_data(as_text=True)
    assert "data-session-character-presentation-dialog-scope" in fragment_html
    assert 'href="/campaigns/linden-pass/pages/items/stormglass-compass"' in fragment_html


@pytest.mark.parametrize(
    "page",
    [
        "overview",
        "spells",
        "resources",
        "features",
        "equipment",
        "inventory",
        "abilities_skills",
        "notes",
        "personal",
    ],
)
def test_session_character_dnd_session_vitals_controls_are_visible_on_all_sections(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    page,
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page={page}"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('id="session-vitals"') == 1
    assert html.find('id="session-vitals"') < html.find('data-combat-section-panel="overview"')
    assert f'name="page" value="{page}"' in html


def test_session_character_equipment_panel_exposes_state_controls_during_active_session(
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=equipment"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    equipment_panel = _html_segment_between(
        html,
        'data-combat-section-panel="equipment"',
        'data-combat-section-panel="inventory"',
    )
    assert 'data-character-sheet-edit-form="equipment-state"' in equipment_panel
    assert (
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}"
        "/equipment/quarterstaff-2/state"
    ) in equipment_panel
    assert 'name="return_view" value="session-character"' in equipment_panel
    assert 'name="page" value="equipment"' in equipment_panel
    assert 'name="weapon_wield_mode"' in equipment_panel
    assert 'data-character-autosubmit' in equipment_panel
    assert "Save equipment state" not in equipment_panel


def test_session_character_equipment_state_update_redirects_back_to_session_surface(
    client,
    sign_in,
    users,
    get_character,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    record = get_character(ASSIGNED_CHARACTER_SLUG)
    assert record is not None
    assert _inventory_item(record, "quarterstaff-2")["is_equipped"] is True

    response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/equipment/quarterstaff-2/state",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "session",
            "page": "equipment",
            "return_view": "session-character",
            "weapon_wield_mode": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        f"/campaigns/linden-pass/session/character?character={ASSIGNED_CHARACTER_SLUG}"
        "&page=equipment#character-equipment-state"
    ) in response.headers["Location"]

    updated = get_character(ASSIGNED_CHARACTER_SLUG)
    assert updated is not None
    updated_item = _inventory_item(updated, "quarterstaff-2")
    assert updated_item["is_equipped"] is False
    assert not updated_item.get("weapon_wield_mode")


def test_session_character_equipment_state_async_fragment_refreshes_character_panel(
    client,
    sign_in,
    users,
    get_character,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    record = get_character(ASSIGNED_CHARACTER_SLUG)
    assert record is not None

    response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/equipment/quarterstaff-2/state",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "session",
            "page": "equipment",
            "return_view": "session-character",
            "weapon_wield_mode": "",
            "fragment": "1",
        },
        headers=_async_headers(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<html" not in html
    assert "<body" not in html
    assert 'data-session-character-flash-stack' in html
    assert "Equipment state updated." in html
    assert 'data-combat-section-panel="equipment"' in html
    assert 'data-character-autosubmit' in html
    assert "Save equipment state" not in html

    updated = get_character(ASSIGNED_CHARACTER_SLUG)
    assert updated is not None
    assert _inventory_item(updated, "quarterstaff-2")["is_equipped"] is False


def test_session_character_stale_async_mutation_returns_character_fragment(
    client,
    sign_in,
    users,
    get_character,
    set_campaign_visibility,
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

    response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/equipment/quarterstaff-2/state",
        data={
            "expected_revision": stale_revision,
            "mode": "session",
            "page": "equipment",
            "return_view": "session-character",
            "weapon_wield_mode": "",
            "fragment": "1",
        },
        headers=_async_headers(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<html" not in html
    assert 'data-session-character-flash-stack' in html
    assert "This sheet changed in another session. Refresh the page and try again." in html
    assert 'data-combat-section-panel="equipment"' in html

    updated = get_character(ASSIGNED_CHARACTER_SLUG)
    assert updated is not None
    assert _inventory_item(updated, "quarterstaff-2")["is_equipped"] is True


def test_session_character_equipment_state_update_requires_active_session_for_session_surface(
    client,
    sign_in,
    users,
    get_character,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["owner"]["email"], users["owner"]["password"])
    record = get_character(ASSIGNED_CHARACTER_SLUG)
    assert record is not None
    assert _inventory_item(record, "quarterstaff-2")["is_equipped"] is True

    response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/equipment/quarterstaff-2/state",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "session",
            "page": "equipment",
            "return_view": "session-character",
            "weapon_wield_mode": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "The live session has ended. Session character editing is no longer available." in html
    assert "Equipment state updated." not in html

    updated = get_character(ASSIGNED_CHARACTER_SLUG)
    assert updated is not None
    assert _inventory_item(updated, "quarterstaff-2")["is_equipped"] is True


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


def test_player_session_page_mounts_global_search_outside_live_session_root(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-session-live-root' in session_html
    assert 'data-campaign-global-search-root' in session_html
    assert session_html.index('class="campaign-global-search"') < session_html.index('class="page-layout session-layout session-layout--single"')
    assert 'data-session-wiki-lookup-root' not in session_html
    assert 'data-loading="0"' in session_html
    assert '/static/session-live.js?v=' in session_html
    assert 'data-live-active-interval-ms="3000"' in session_html
    assert 'data-live-idle-interval-ms="6000"' in session_html
    assert session_html.count("data-live-read-status\n") == 1
    assert "Retry live update" in session_html
    session_script = _session_live_script_text()
    assert "window.__playerWikiLiveUiTools" in session_script
    assert "uiStateTools.captureViewportAnchor(liveRoot)" in session_script
    assert 'liveRoot.dataset.loading = "1";' not in session_script
    assert 'signal: readTicket ? readTicket.signal : undefined' in session_script
    assert 'asyncPolicy.settleRead(readTicket, "poll-error")' in session_script
    assert 'asyncPolicy.settleMutation(form, "mutation-unknown")' in session_script


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

    session_page = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-session-article-id="1"' in session_html
    assert '/static/session-live.js?v=' in session_html
    session_script = _session_live_script_text()
    assert 'const collectOpenSessionArticleIds = (root) => {' in session_script
    assert 'restoreOpenSessionArticleIds(stagedRoot, openSessionArticleIds);' in session_script
    assert 'restoreOpenSessionArticleIds(revealedRoot, openSessionArticleIds);' in session_script
    assert session_script.count('statusCard = liveRoot.querySelector("[data-session-status-card]");') == 3


def test_dm_can_open_session_page_and_session_dm_page(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")
    dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Chat window" in session_html
    assert "Session controls" in session_html
    assert 'data-session-shell-active="session"' in session_html
    assert 'data-session-shell-pane="dm"' in session_html
    assert 'data-session-live-view="dm"' in session_html
    assert '/campaigns/linden-pass/session/dm' in session_html
    assert "Back to wiki" not in session_html
    assert "Open DM page" not in session_html

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert 'data-session-shell-root' in dm_html
    assert 'data-session-shell-active="dm"' in dm_html
    assert "Session controls" in dm_html
    assert "DM Passive Scores" in dm_html
    assert 'data-session-dm-pane="tools"' in dm_html
    assert "Back to wiki" not in dm_html
    assert "Open DM page" not in dm_html
    assert 'data-live-active-interval-ms="2000"' in dm_html
    assert 'data-live-idle-interval-ms="5000"' in dm_html
    assert dm_html.count("data-live-read-status\n") == 2


def test_dm_session_layout_places_status_controls_in_sidebar_and_prioritizes_workflow_cards(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert 'id="session-controls"' in dm_html
    assert 'data-session-controls-root' in dm_html
    assert dm_html.count('id="session-controls"') == 1
    assert dm_html.count('<div data-session-controls-root>') == 1
    assert "Session controls" in dm_html
    assert "Session article store" not in dm_html
    assert 'data-session-dm-switch-target="article-store"' in dm_html

    sidebar_start = dm_html.find('<aside class="session-sidebar">')
    controls_index = dm_html.find('id="session-controls"')
    passive_scores_index = dm_html.find('data-session-passive-scores-bar')
    assert sidebar_start != -1 and controls_index != -1 and passive_scores_index != -1
    assert passive_scores_index < sidebar_start < controls_index
    assert dm_html.count('data-session-dm-pane="tools"') == 1
    assert dm_html.count('data-session-dm-pane="article-store"') == 1
    assert 'data-session-dm-legacy-remainder' not in dm_html

    sidebar_end = dm_html.find("</aside>", sidebar_start)
    assert sidebar_end != -1
    sidebar_segment = dm_html[sidebar_start:sidebar_end]
    assert 'data-session-passive-scores-bar' not in sidebar_segment


def test_dm_session_page_shows_passive_scores_for_active_dnd_characters(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert "DM Passive Scores" in dm_html
    assert 'data-session-passive-scores-bar' in dm_html
    assert '<h3 class="session-passive-score-card__name">Arden March</h3>' in dm_html
    assert '<h3 class="session-passive-score-card__name">Selene Brook</h3>' in dm_html
    assert '<h3 class="session-passive-score-card__name">Tobin Slate</h3>' in dm_html
    assert "Passive Perception" in dm_html
    assert "Passive Insight" in dm_html
    assert "Passive Investigation" in dm_html
    assert ">12</span>" in dm_html


def test_dm_session_page_hides_passive_scores_bar_for_xianxia_campaign(client, app, sign_in, users):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert "DM Passive Scores" not in dm_html
    assert 'data-session-passive-scores-bar' not in dm_html


def test_dm_session_page_filters_non_dnd_characters_from_passive_scores(
    client, app, sign_in, users
):
    _set_character_system(app, "arden-march", "xianxia")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert "DM Passive Scores" in dm_html
    assert '<h3 class="session-passive-score-card__name">Arden March</h3>' not in dm_html
    assert '<h3 class="session-passive-score-card__name">Selene Brook</h3>' in dm_html
    assert '<h3 class="session-passive-score-card__name">Tobin Slate</h3>' in dm_html


def test_dm_session_page_shows_empty_state_when_no_dnd_characters_are_visible(client, app, sign_in, users):
    _set_characters_system(app, "xianxia")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert "DM Passive Scores" in dm_html
    assert 'data-session-passive-scores-bar' in dm_html
    assert "No visible DND-5E characters are currently available on the DM session surface." in dm_html
    assert '<article class="session-passive-score-card"' not in dm_html


def test_dm_can_start_session_and_player_can_post_messages(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    start = client.post("/campaigns/linden-pass/session/start", follow_redirects=True)

    assert start.status_code == 200
    start_html = start.get_data(as_text=True)
    assert "Session started. Players can now use the Session page chat." in start_html
    assert "The session is live for players and the DM." in start_html

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


def test_session_message_batches_message_and_revision_commit(app, users):
    with app.app_context():
        service = app.extensions["campaign_session_service"]
        service.begin_session(TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"])

        reset_db_query_metrics()
        service.post_message(
            TEST_CAMPAIGN_SLUG,
            body_text="One batched table update.",
            author_display_name="Owner Player",
            author_user_id=users["owner"]["id"],
        )
        metrics = get_db_query_metrics()

    assert metrics["write_count"] >= 2
    assert metrics["commit_count"] == 1
    assert metrics["rollback_count"] == 0


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
    assert "The session is live for players and the DM." in start_payload["status_html"]
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


@pytest.mark.parametrize(
    ("form_data", "expected_scope", "expected_recipient_user_id"),
    (
        ({"body": "  Global transport text.  "}, "global", None),
        (
            {
                "body": "DM transport text.",
                "recipient_scope": "  DM_ONLY  ",
                "recipient_user_id": "ignored-for-dm-only",
            },
            "dm_only",
            "ignored-for-dm-only",
        ),
        (
            {
                "body": "Player transport text.",
                "recipient_scope": " PLAYER ",
                "recipient_user_id": "17",
            },
            "player",
            "17",
        ),
    ),
)
def test_session_message_route_preserves_exact_service_arguments(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    form_data,
    expected_scope,
    expected_recipient_user_id,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    service = app.extensions["campaign_session_service"]
    captured: dict[str, object] = {}

    def capture_post_message(campaign_slug, **kwargs):
        captured["campaign_slug"] = campaign_slug
        captured.update(kwargs)

    monkeypatch.setattr(service, "post_message", capture_post_message)

    response = client.post(
        "/campaigns/linden-pass/session/messages",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/session#session-chat-compose"
    )
    assert captured == {
        "campaign_slug": TEST_CAMPAIGN_SLUG,
        "body_text": form_data["body"],
        "author_display_name": "Dungeon Master",
        "author_user_id": users["dm"]["id"],
        "recipient_scope": expected_scope,
        "recipient_user_id": expected_recipient_user_id,
    }


@pytest.mark.parametrize(
    ("form_data", "start_session", "expected_message"),
    (
        ({"body": ""}, True, "Enter a message before posting it to the chat."),
        (
            {"body": "x" * 4001},
            True,
            "Session chat messages must stay under 4,000 characters.",
        ),
        (
            {"body": "Invalid audience.", "recipient_scope": "party"},
            True,
            "Message audience must be global, dm_only, or player.",
        ),
        (
            {"body": "Missing recipient.", "recipient_scope": "player"},
            True,
            "Choose a player when sending a targeted player message.",
        ),
        (
            {
                "body": "Invalid recipient.",
                "recipient_scope": "player",
                "recipient_user_id": "not-a-user",
            },
            True,
            "Choose a valid player for the targeted message.",
        ),
        (
            {
                "body": "Inactive recipient.",
                "recipient_scope": "player",
                "recipient_user_id": "{observer_user_id}",
            },
            True,
            "Choose an active campaign player for the targeted message.",
        ),
        (
            {"body": "No active session."},
            False,
            "The chat window opens when the DM begins a session.",
        ),
    ),
)
def test_session_message_validation_preserves_sync_async_and_revision_contracts(
    app,
    client,
    sign_in,
    users,
    form_data,
    start_session,
    expected_message,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    if start_session:
        client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    submitted = {
        key: (
            value.format(observer_user_id=users["observer"]["id"])
            if isinstance(value, str)
            else value
        )
        for key, value in form_data.items()
    }
    with app.app_context():
        service = app.extensions["campaign_session_service"]
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)

    sync_response = client.post(
        "/campaigns/linden-pass/session/messages",
        data=submitted,
        follow_redirects=True,
    )
    assert sync_response.status_code == 200
    assert sync_response.history[0].headers["Location"].endswith(
        "/campaigns/linden-pass/session#session-chat-compose"
    )
    assert expected_message in sync_response.get_data(as_text=True)

    async_response = client.post(
        "/campaigns/linden-pass/session/messages",
        data=submitted,
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert async_response.status_code == 200
    payload = async_response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == "session-chat-compose"
    assert expected_message in payload["flash_html"]

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before
        active_session = service.get_active_session(TEST_CAMPAIGN_SLUG)
        if active_session is not None:
            assert service.list_messages(active_session.id, can_manage_session=True) == []


@pytest.mark.parametrize("actor", ("observer", "outsider"))
def test_session_message_role_gate_denies_non_posting_roles_with_public_session_scope(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    actor,
):
    set_campaign_visibility(TEST_CAMPAIGN_SLUG, session="public")
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "This role cannot post."},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_session_message_rejects_missing_current_user_after_post_gate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    handler = inspect.unwrap(app.view_functions["campaign_session_post_message"])
    monkeypatch.setitem(
        handler.__globals__,
        "can_post_campaign_session_messages",
        lambda _campaign_slug: True,
    )
    monkeypatch.setitem(handler.__globals__, "get_current_user", lambda: None)

    response = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "No current user."},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_session_message_unexpected_service_fault_propagates(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]

    def fail_post_message(*_args, **_kwargs):
        raise RuntimeError("session message write unavailable")

    monkeypatch.setattr(service, "post_message", fail_post_message)

    with pytest.raises(RuntimeError, match="session message write unavailable"):
        client.post(
            "/campaigns/linden-pass/session/messages",
            data={"body": "Fault injection."},
            follow_redirects=False,
        )


def test_session_message_csrf_failure_precedes_mutation(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    with app.app_context():
        service = app.extensions["campaign_session_service"]
        active_session = service.get_active_session(TEST_CAMPAIGN_SLUG)
        assert active_session is not None
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)
    app.config["CSRF_ENABLED"] = True

    response = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Blocked before mutation."},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Refresh the page and try again." in response.get_data(as_text=True)
    with app.app_context():
        service = app.extensions["campaign_session_service"]
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before
        assert service.list_messages(active_session.id, can_manage_session=True) == []


def test_session_start_already_active_preserves_sync_and_async_validation_contracts(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    first_start = client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    assert first_start.status_code == 302

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        active_session = service.get_active_session(TEST_CAMPAIGN_SLUG)
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)
    assert active_session is not None

    sync_response = client.post(
        "/campaigns/linden-pass/session/start",
        follow_redirects=True,
    )
    assert sync_response.status_code == 200
    assert sync_response.history[0].headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=tools#session-controls"
    )
    assert "A live session is already running for this campaign." in sync_response.get_data(
        as_text=True
    )

    async_response = client.post(
        "/campaigns/linden-pass/session/start",
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert async_response.status_code == 200
    payload = async_response.get_json()
    assert payload["ok"] is False
    assert payload["active_session_id"] == active_session.id
    assert payload["anchor"] == "session-controls"
    assert "A live session is already running for this campaign." in payload["flash_html"]

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before


@pytest.mark.parametrize(
    ("actor", "expected_status"),
    (("party", 403), ("observer", 404), ("outsider", 404)),
)
@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/session/start",
        "/campaigns/linden-pass/session/close",
        "/campaigns/linden-pass/session/logs/999/delete",
    ),
)
def test_session_lifecycle_mutations_preserve_player_observer_and_outsider_denials(
    client,
    sign_in,
    users,
    actor,
    expected_status,
    path,
):
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.post(path, follow_redirects=False)

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "endpoint",
    (
        "campaign_session_start",
        "campaign_session_close",
        "campaign_session_log_delete",
    ),
)
def test_session_lifecycle_mutations_reject_missing_current_user_after_scope_access(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    endpoint,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    handler = inspect.unwrap(app.view_functions[endpoint])
    monkeypatch.setitem(handler.__globals__, "get_current_user", lambda: None)
    path = {
        "campaign_session_start": "/campaigns/linden-pass/session/start",
        "campaign_session_close": "/campaigns/linden-pass/session/close",
        "campaign_session_log_delete": "/campaigns/linden-pass/session/logs/999/delete",
    }[endpoint]

    response = client.post(path, follow_redirects=False)

    assert response.status_code == 403


def test_session_message_composer_includes_audience_controls(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    start = client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    assert start.status_code == 302

    session_page = client.get("/campaigns/linden-pass/session")
    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)

    assert 'name="recipient_scope"' in session_html
    assert 'name="recipient_user_id"' in session_html
    assert '<option value="global">Global</option>' in session_html
    assert '<option value="dm_only">DM only</option>' in session_html
    assert '<option value="player">Specific player</option>' in session_html
    assert "Arden March (Owner Player)" in session_html
    assert "Party Player" in session_html
    assert "owner@example.com" not in session_html
    assert "party@example.com" not in session_html


def test_session_composer_feedback_uses_shared_primitive_and_controller_routes_once(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    session_page = client.get("/campaigns/linden-pass/session")
    assert session_page.status_code == 200
    composer_html = _html_segment_after(
        session_page.get_data(as_text=True),
        'id="session-chat-compose"',
        length=3500,
    )
    assert "data-session-composer-form" in composer_html
    assert 'aria-describedby="session-chat-compose-feedback"' in composer_html
    assert (
        '<div id="session-chat-compose-feedback" data-session-form-feedback></div>'
        in composer_html
    )

    validation_response = client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "x" * 4001},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert validation_response.status_code == 200
    payload = validation_response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == "session-chat-compose"
    assert 'data-feedback-placement="transient"' in payload["flash_html"]
    assert 'data-feedback-tone="error"' in payload["flash_html"]
    assert 'role="alert"' in payload["flash_html"]
    assert 'aria-live="assertive"' in payload["flash_html"]

    session_script = _session_live_script_text()
    assert 'const composerValidationFailed = isComposerForm && payload.ok === false;' in session_script
    assert "forceComposer: !composerValidationFailed" in session_script
    assert "preserveComposer: composerValidationFailed" in session_script
    assert "forceFlash: !composerValidationFailed" in session_script
    assert "sessionFeedbackForm: composerValidationFailed ? form : null" in session_script
    assert "suppressAnchor: composerValidationFailed" in session_script
    assert 'if (flashRoot) {\n            flashRoot.innerHTML = "";' in session_script
    assert 'feedback.dataset.feedbackPlacement = "persistent";' in session_script
    assert 'form.setAttribute("aria-invalid", "true");' in session_script
    assert 'form.setAttribute("aria-busy", "true");' in session_script
    assert 'form.removeAttribute("aria-busy");' in session_script


def test_session_message_audience_filtering_respects_private_scope(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    global_message = "Global briefing now."
    dm_only_message = "DM-only tactics should stay private."
    owner_target_message = "Owner-only tactical note."
    party_to_dm_only_message = "Party is requesting an update."

    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": global_message},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={
            "body": dm_only_message,
            "recipient_scope": "dm_only",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={
            "body": owner_target_message,
            "recipient_scope": "player",
            "recipient_user_id": str(users["owner"]["id"]),
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={
            "body": party_to_dm_only_message,
            "recipient_scope": "dm_only",
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    owner_view = client.get("/campaigns/linden-pass/session")
    owner_html = owner_view.get_data(as_text=True)
    assert owner_view.status_code == 200
    assert global_message in owner_html
    assert owner_target_message in owner_html
    assert dm_only_message not in owner_html
    assert party_to_dm_only_message not in owner_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    party_view = client.get("/campaigns/linden-pass/session")
    party_html = party_view.get_data(as_text=True)
    assert party_view.status_code == 200
    assert global_message in party_html
    assert party_to_dm_only_message in party_html
    assert owner_target_message not in party_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_view = client.get("/campaigns/linden-pass/session")
    dm_html = dm_view.get_data(as_text=True)

    assert dm_view.status_code == 200
    assert global_message in dm_html
    assert dm_only_message in dm_html
    assert owner_target_message in dm_html
    assert party_to_dm_only_message in dm_html


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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "Sealed Orders" in staged_html
    assert "Deliver the crate to the eastern gate before moonrise." in staged_html

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


def test_session_article_create_and_update_preserve_service_arguments_actor_and_revision(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    original_create_article = service.create_article
    original_update_article = service.update_article
    original_update_image_metadata = service.update_article_image_metadata
    create_calls = []
    update_calls = []
    metadata_calls = []

    def record_create_article(campaign_slug, **kwargs):
        create_calls.append((campaign_slug, kwargs))
        return original_create_article(campaign_slug, **kwargs)

    def record_update_article(campaign_slug, article_id, **kwargs):
        update_calls.append((campaign_slug, article_id, kwargs))
        return original_update_article(campaign_slug, article_id, **kwargs)

    def record_update_image_metadata(campaign_slug, article_id, **kwargs):
        metadata_calls.append((campaign_slug, article_id, kwargs))
        return original_update_image_metadata(campaign_slug, article_id, **kwargs)

    monkeypatch.setattr(service, "create_article", record_create_article)
    monkeypatch.setattr(service, "update_article", record_update_article)
    monkeypatch.setattr(service, "update_article_image_metadata", record_update_image_metadata)

    with app.app_context():
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)

    create_response = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "article_mode": " NOT-A-MODE ",
            "title": "Characterized Orders",
            "body_markdown": "Keep the exact helper arguments stable.",
            "image_alt": "Original alt text.",
            "image_caption": "Original caption.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "orders.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=article-store&article_mode=manual#session-article-store"
    )
    assert create_calls == [
        (
            TEST_CAMPAIGN_SLUG,
            {
                "title": "Characterized Orders",
                "body_markdown": "Keep the exact helper arguments stable.",
                "has_content_image": True,
                "created_by_user_id": users["dm"]["id"],
            },
        )
    ]

    with app.app_context():
        revision_after_create = service.get_live_revision(TEST_CAMPAIGN_SLUG)
    assert revision_after_create > revision_before

    update_response = client.post(
        "/campaigns/linden-pass/session/articles/1",
        data={
            "title": "Updated Characterized Orders",
            "body_markdown": "The update arguments also remain stable.",
            "image_alt": "Updated alt text.",
            "image_caption": "Updated caption.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302
    assert update_response.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=staged#session-staged-articles"
    )
    assert update_calls == [
        (
            TEST_CAMPAIGN_SLUG,
            1,
            {
                "title": "Updated Characterized Orders",
                "body_markdown": "The update arguments also remain stable.",
                "has_content_image": True,
                "updated_by_user_id": users["dm"]["id"],
            },
        )
    ]
    assert metadata_calls == [
        (
            TEST_CAMPAIGN_SLUG,
            1,
            {
                "alt_text": "Updated alt text.",
                "caption": "Updated caption.",
                "updated_by_user_id": users["dm"]["id"],
            },
        )
    ]
    with app.app_context():
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) > revision_after_create


def test_session_article_create_and_update_preserve_async_validation_and_anchors(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)

    create_response = client.post(
        "/campaigns/linden-pass/session/articles",
        data={"article_mode": " UPLOAD "},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    assert create_payload["ok"] is False
    assert create_payload["anchor"] == "session-article-store"
    assert "Choose a markdown file before saving the session article." in create_payload["flash_html"]

    update_response = client.post(
        "/campaigns/linden-pass/session/articles/999",
        data={"title": "Missing", "body_markdown": "Missing target."},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_response.status_code == 200
    update_payload = update_response.get_json()
    assert update_payload["ok"] is False
    assert update_payload["anchor"] == "session-staged-articles"
    assert "That session article could not be found." in update_payload["flash_html"]
    with app.app_context():
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before
        assert service.list_articles(TEST_CAMPAIGN_SLUG) == []


@pytest.mark.parametrize(
    ("endpoint", "path"),
    (
        ("campaign_session_create_article", "/campaigns/linden-pass/session/articles"),
        ("campaign_session_update_article", "/campaigns/linden-pass/session/articles/999"),
    ),
)
def test_session_article_authoring_rejects_missing_current_user_after_manager_gate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    endpoint,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    handler = inspect.unwrap(app.view_functions[endpoint])
    monkeypatch.setitem(handler.__globals__, "can_manage_campaign_session", lambda _slug: True)
    monkeypatch.setitem(handler.__globals__, "get_current_user", lambda: None)

    response = client.post(path, follow_redirects=False)

    assert response.status_code == 403


@pytest.mark.parametrize("actor", ("party", "observer", "outsider"))
@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/session/articles",
        "/campaigns/linden-pass/session/articles/999",
    ),
)
def test_session_article_authoring_preserves_role_and_scope_denials(
    client,
    sign_in,
    users,
    actor,
    path,
):
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.post(path, follow_redirects=False)

    assert response.status_code == (403 if actor == "party" else 404)


@pytest.mark.parametrize("operation", ("create", "update"))
def test_session_article_authoring_unexpected_service_faults_propagate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    operation,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    if operation == "update":
        client.post(
            "/campaigns/linden-pass/session/articles",
            data={"title": "Fault target", "body_markdown": "Created before injection."},
            follow_redirects=False,
        )

    def fail_service(*_args, **_kwargs):
        raise RuntimeError(f"characterized article {operation} fault")

    monkeypatch.setattr(service, f"{operation}_article", fail_service)
    path = (
        "/campaigns/linden-pass/session/articles"
        if operation == "create"
        else "/campaigns/linden-pass/session/articles/1"
    )

    with pytest.raises(RuntimeError, match=f"characterized article {operation} fault"):
        client.post(
            path,
            data={"title": "Fault", "body_markdown": "Fault injection."},
            follow_redirects=False,
        )


@pytest.mark.parametrize("operation", ("create", "update"))
def test_session_article_authoring_csrf_failure_precedes_write(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    operation,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    if operation == "update":
        client.post(
            "/campaigns/linden-pass/session/articles",
            data={"title": "CSRF target", "body_markdown": "Created before protection."},
            follow_redirects=False,
        )
    calls = []

    def record_forbidden_write(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("article write must not run before CSRF denial")

    monkeypatch.setattr(service, f"{operation}_article", record_forbidden_write)
    with app.app_context():
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)
    app.config["CSRF_ENABLED"] = True
    path = (
        "/campaigns/linden-pass/session/articles"
        if operation == "create"
        else "/campaigns/linden-pass/session/articles/1"
    )

    response = client.post(
        path,
        data={"title": "Blocked", "body_markdown": "Blocked before write."},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Refresh the page and try again." in response.get_data(as_text=True)
    assert calls == []
    with app.app_context():
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before


def test_dm_can_update_staged_session_article_before_reveal_and_conversion(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Draft Orders",
            "body_markdown": "Deliver the crate to the wrong gate.",
            "image_alt": "Original draft image.",
            "image_caption": "Original caption.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "draft-orders.png"),
        },
        follow_redirects=False,
    )
    assert create_article.status_code == 302

    update_article = client.post(
        "/campaigns/linden-pass/session/articles/1",
        data={
            "title": "Sealed Orders",
            "body_markdown": "Deliver the crate to the eastern gate before moonrise.",
            "image_alt": "Updated sealed orders image.",
            "image_caption": "Updated before reveal.",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_article.status_code == 200
    payload = update_article.get_json()
    assert payload["ok"] is True
    assert "Session article updated." in payload["flash_html"]
    assert "Sealed Orders" in payload["staged_articles_html"]
    assert "Deliver the crate to the eastern gate before moonrise." in payload["staged_articles_html"]
    assert "Draft Orders" not in payload["staged_articles_html"]
    assert 'action="/campaigns/linden-pass/session/articles/1"' in payload["staged_articles_html"]
    assert "Updated sealed orders image." in payload["staged_articles_html"]

    with app.app_context():
        session_service = app.extensions["campaign_session_service"]
        article = session_service.get_article("linden-pass", 1)
        image = session_service.get_article_image("linden-pass", 1)

    assert article is not None
    assert article.title == "Sealed Orders"
    assert article.body_markdown == "Deliver the crate to the eastern gate before moonrise."
    assert image is not None
    assert image.alt_text == "Updated sealed orders image."
    assert image.caption == "Updated before reveal."

    convert_page = client.get("/campaigns/linden-pass/session/articles/1/convert")
    convert_html = convert_page.get_data(as_text=True)
    assert convert_page.status_code == 200
    assert "Sealed Orders" in convert_html
    assert "Deliver the crate to the eastern gate before moonrise." in convert_html
    assert "Draft Orders" not in convert_html

    reveal = client.post("/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=True)
    assert reveal.status_code == 200

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)
    assert player_view.status_code == 200
    assert "Sealed Orders" in player_html
    assert "Deliver the crate to the eastern gate before moonrise." in player_html
    assert "Draft Orders" not in player_html
    assert "wrong gate" not in player_html


def test_dm_session_article_store_supports_manual_upload_and_lookup_modes(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    session_page = client.get("/campaigns/linden-pass/session/dm?dm_view=article-store")

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
    assert "The article title comes from markdown frontmatter" in session_html
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
    session_page = client.get("/campaigns/linden-pass/session/dm?dm_view=article-store")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert "Search to load matching articles" in session_html
    assert "Captain Lyra Vale - Wiki" not in session_html


def test_global_search_does_not_eager_load_reference_choices(app, client, sign_in, users, monkeypatch):
    with app.app_context():
        page_store = app.extensions["campaign_page_store"]
        systems_service = app.extensions["systems_service"]

    def fail_page_search(*args, **kwargs):
        raise AssertionError("campaign pages should not eagerly load global wiki search results")

    def fail_systems_search(*args, **kwargs):
        raise AssertionError("campaign pages should not eagerly load global Systems search results")

    monkeypatch.setattr(page_store, "search_page_records", fail_page_search)
    monkeypatch.setattr(systems_service, "search_entries_for_campaign", fail_systems_search)

    sign_in(users["party"]["email"], users["party"]["password"])
    session_page = client.get("/campaigns/linden-pass/session")

    assert session_page.status_code == 200
    session_html = session_page.get_data(as_text=True)
    assert 'data-campaign-global-search-root' in session_html
    assert 'data-campaign-global-search-results' in session_html
    assert "Captain Lyra Vale - NPCs" not in session_html


def test_campaign_global_search_finds_visible_wiki_pages_and_uses_preview_modal_contract(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    short_search = client.get(
        "/campaigns/linden-pass/global-search?q=c",
        headers=_async_headers(),
    )
    assert short_search.status_code == 200
    assert short_search.get_json()["message"] == "Type at least 2 letters to search wiki pages and Systems entries."

    search = client.get(
        "/campaigns/linden-pass/global-search?q=capt",
        headers=_async_headers(),
    )
    assert search.status_code == 200
    payload = search.get_json()
    assert payload["results"]
    captain_result = next(
        result for result in payload["results"] if result["result_id"] == "wiki:npcs/captain-lyra-vale"
    )
    assert captain_result["kind"] == "wiki"
    assert captain_result["kind_label"] == "Wiki"
    assert captain_result["title"] == "Captain Lyra Vale"
    assert "href" not in captain_result

    preview = client.get(
        "/campaigns/linden-pass/global-search/preview?result_id=wiki:npcs/captain-lyra-vale",
        headers=_async_headers(),
    )
    assert preview.status_code == 200
    preview_html = preview.get_json()["preview_html"]
    assert "Captain Lyra Vale" in preview_html
    assert "Open dedicated page" in preview_html
    assert "/campaigns/linden-pass/pages/npcs/captain-lyra-vale" in preview_html


def test_campaign_global_search_finds_accessible_systems_entries_and_previews_them(
    client,
    sign_in,
    users,
    app,
    tmp_path,
):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    search = client.get(
        "/campaigns/linden-pass/global-search?q=gob",
        headers=_async_headers(),
    )
    assert search.status_code == 200
    payload = search.get_json()
    assert payload["results"]
    goblin_result = next(result for result in payload["results"] if result["result_id"] == f"systems:{goblin_slug}")
    assert goblin_result["kind"] == "systems"
    assert goblin_result["kind_label"] == "Systems"
    assert goblin_result["title"] == "Goblin"
    assert goblin_result["subtitle"] == "Monsters / MM"
    assert "href" not in goblin_result

    preview = client.get(
        f"/campaigns/linden-pass/global-search/preview?result_id=systems:{goblin_slug}",
        headers=_async_headers(),
    )
    assert preview.status_code == 200
    preview_html = preview.get_json()["preview_html"]
    assert "Goblin" in preview_html
    assert "Scimitar" in preview_html
    assert "Open dedicated page" in preview_html
    assert f"/campaigns/linden-pass/systems/entries/{goblin_slug}" in preview_html


def test_campaign_global_search_preview_endpoint_contracts_when_unavailable(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    blank = client.get(
        "/campaigns/linden-pass/global-search/preview",
        headers=_async_headers(),
    )
    assert blank.status_code == 200
    assert blank.get_json()["preview_html"] == ""

    missing = client.get(
        "/campaigns/linden-pass/global-search/preview?result_id=systems:does-not-exist",
        headers=_async_headers(),
    )
    assert missing.status_code == 404
    missing_html = missing.get_json()["preview_html"]
    assert "That reference is not currently visible." in missing_html


def test_dm_can_search_session_article_sources(client, sign_in, users, app, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
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


def test_session_article_source_search_preserves_short_empty_and_manager_gate_contracts(
    client,
    sign_in,
    users,
):
    sign_in(users["party"]["email"], users["party"]["password"])

    denied = client.get(
        "/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers=_async_headers(),
    )
    assert denied.status_code == 403

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    short = client.get(
        "/campaigns/linden-pass/session/article-sources/search?q=c",
        headers=_async_headers(),
    )
    assert short.status_code == 200
    assert short.get_json() == {
        "results": [],
        "message": "Type at least 2 letters to search published wiki pages and Systems entries.",
    }

    empty = client.get(
        "/campaigns/linden-pass/session/article-sources/search?q=definitely-no-match",
        headers=_async_headers(),
    )
    assert empty.status_code == 200
    assert empty.get_json() == {
        "results": [],
        "message": "No published wiki or Systems articles matched that search.",
    }


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


def test_session_wiki_lookup_preserves_short_blank_unavailable_and_scope_denial_contracts(
    client,
    sign_in,
    users,
):
    sign_in(users["party"]["email"], users["party"]["password"])

    short = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/search?q=c",
        headers=_async_headers(),
    )
    assert short.status_code == 200
    assert short.get_json() == {
        "results": [],
        "message": "Type at least 2 letters to search player-visible wiki articles.",
    }

    blank = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/preview",
        headers=_async_headers(),
    )
    assert blank.status_code == 200
    assert blank.get_json() == {"preview_html": ""}

    unavailable = client.get(
        "/campaigns/linden-pass/session/wiki-lookup/preview?page_ref=notes/does-not-exist",
        headers=_async_headers(),
    )
    assert unavailable.status_code == 404
    assert "That article is not currently visible to players." in unavailable.get_json()["preview_html"]

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["observer"]["email"], users["observer"]["password"])
    for path in (
        "/campaigns/linden-pass/session/article-sources/search?q=capt",
        "/campaigns/linden-pass/session/wiki-lookup/search?q=capt",
        "/campaigns/linden-pass/session/wiki-lookup/preview?page_ref=notes/operations-brief",
    ):
        assert client.get(path, headers=_async_headers()).status_code == 404


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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "Captain Lyra Vale" in staged_html
    assert "Harbor watch captain and trusted ally of the crew." in staged_html
    assert "View published page" in staged_html
    assert "/campaigns/linden-pass/pages/npcs/captain-lyra-vale" in staged_html
    assert "/campaigns/linden-pass/session-article-images/1" in staged_html
    assert "Convert to wiki page" not in staged_html

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
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "Goblin" in staged_html
    assert "Scimitar" in staged_html
    assert f"/campaigns/linden-pass/systems/entries/{goblin_slug}" in staged_html
    assert "View Systems entry" in staged_html
    assert "Convert to wiki page" not in staged_html

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
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "Ferry Note" in staged_html
    assert "Meet the ferryman at dusk." in staged_html
    assert "Bring no lanterns." in staged_html

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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "/campaigns/linden-pass/session-article-images/1" in staged_html
    assert "Found tucked into the courier&#39;s satchel." in staged_html
    assert "Use this token at the eastern dock after sunset." in staged_html

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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "/campaigns/linden-pass/session-article-images/1" in staged_html
    assert "Found tucked into the courier&#39;s satchel." in staged_html
    assert "Use this token at the eastern dock after sunset." in staged_html

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

    staged_view = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "/campaigns/linden-pass/session-article-images/1" in staged_html
    assert "Recovered from the courier&#39;s effects." in staged_html

    dm_image = client.get("/campaigns/linden-pass/session-article-images/1")
    assert dm_image.status_code == 200
    assert dm_image.mimetype == "image/png"
    assert dm_image.data == TEST_PNG_BYTES
    assert dm_image.headers["Content-Disposition"] == "inline; filename=courier-portrait.png"
    assert dm_image.headers["Content-Length"] == str(len(TEST_PNG_BYTES))

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


def test_session_article_image_access_handles_admin_scope_and_missing_records(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    missing_campaign = client.get("/campaigns/missing/session-article-images/1")
    missing_article = client.get("/campaigns/linden-pass/session-article-images/999")
    article_without_image = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Text-only Notice",
            "body_markdown": "This staged article intentionally has no image.",
        },
        follow_redirects=False,
    )
    missing_image = client.get("/campaigns/linden-pass/session-article-images/1")

    assert missing_campaign.status_code == 404
    assert missing_article.status_code == 404
    assert article_without_image.status_code == 302
    assert missing_image.status_code == 404

    image_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Staged Admin Image",
            "body_markdown": "DMs and app admins may inspect this staged image.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "staged-admin-image.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert image_article.status_code == 302

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    admin_image = client.get("/campaigns/linden-pass/session-article-images/2")
    assert admin_image.status_code == 200
    assert admin_image.data == TEST_PNG_BYTES

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["observer"]["email"], users["observer"]["password"])
    scope_denied_image = client.get("/campaigns/linden-pass/session-article-images/2")
    assert scope_denied_image.status_code == 404

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
    assert "The session is live for players and the DM." in payload["status_html"]
    assert "Close session" in payload["controls_html"]
    assert 'id="session-controls"' in payload["controls_html"]
    assert "data-session-controls-root" not in payload["controls_html"]
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


def test_player_session_live_state_short_circuits_when_revision_and_view_token_match(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    initial_live_state = client.get(
        "/campaigns/linden-pass/session/live-state",
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
        "/campaigns/linden-pass/session/live-state",
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

    returned_page = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
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

    returned_page = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    returned_html = returned_page.get_data(as_text=True)

    assert returned_page.status_code == 200
    assert "No active session is running right now." in returned_html
    assert "Unsent Orders" in returned_html
    assert "This should stay staged after the session ends." in returned_html

    revealed_page = client.get("/campaigns/linden-pass/session/dm?dm_view=revealed")
    revealed_html = revealed_page.get_data(as_text=True)
    assert revealed_page.status_code == 200
    assert "No active session is running right now." in revealed_html
    assert "Read Aloud Notice" in revealed_html
    assert "This should stay listed as revealed after the session ends." in revealed_html

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
    assert ">Overview<" not in convert_html
    assert 'value="Notes"' in convert_html
    assert 'value="Bestiary"' in convert_html

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
    assert '/campaigns/linden-pass/assets/session-articles/article-1-courier-seal.webp' in page_html
    assert "Shown to the party after the reveal." in page_html

    campaigns_dir = isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
    published_file = campaigns_dir / "linden-pass" / "content" / "notes" / "courier-seal.md"
    published_text = published_file.read_text(encoding="utf-8")
    assert "source_ref: session-article:linden-pass:1" in published_text
    assert "section: Notes" in published_text
    assert "type: note" in published_text
    assert "image: session-articles/article-1-courier-seal.webp" in published_text

    published_asset = campaigns_dir / "linden-pass" / "assets" / "session-articles" / "article-1-courier-seal.webp"
    assert_webp_bytes(published_asset.read_bytes())

    session_page = isolated_campaign_client.get(
        "/campaigns/linden-pass/session/dm?dm_view=staged"
    )
    session_html = session_page.get_data(as_text=True)
    assert session_page.status_code == 200
    assert "View published page" in session_html
    assert "/campaigns/linden-pass/pages/notes/courier-seal" in session_html

    with isolated_campaign_app.app_context():
        audit_count = get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0]
        assert audit_count == 0
        isolated_campaign_app.extensions["campaign_session_service"].delete_article(
            TEST_CAMPAIGN_SLUG,
            1,
            updated_by_user_id=isolated_campaign_users["dm"]["id"],
        )
    assert published_file.exists()
    assert published_asset.exists()
    assert isolated_campaign_client.get(publish_response.headers["Location"]).status_code == 200


def test_convert_no_image_sanitizes_and_persists_row(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Sanitized Dispatch",
            "body_markdown": "<script>blocked()</script>\n\n**Player-safe dispatch.**",
        },
        follow_redirects=False,
    )

    response = isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles/1/convert",
        data={
            "title": "Sanitized Dispatch",
            "slug_leaf": "sanitized-dispatch",
            "summary": "A safe dispatch snapshot.",
            "section": "Notes",
            "page_type": "note",
            "subsection": "Dispatches",
            "reveal_after_session": "999",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with isolated_campaign_app.app_context():
        record = isolated_campaign_app.extensions["campaign_page_store"].get_page_record(
            TEST_CAMPAIGN_SLUG,
            "notes/sanitized-dispatch",
            include_body=True,
        )
        assert record is not None
        assert record.page.source_ref == "session-article:linden-pass:1"
        assert record.page.section == "Notes"
        assert record.page.subsection == "Dispatches"
        assert record.page.page_type == "note"
        assert record.page.reveal_after_session == 999
        assert "<script>" not in record.body_markdown
        assert "Player-safe dispatch." in record.body_markdown
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0


def test_convert_same_dest_race(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    for title, filename in (("First Race", "first.png"), ("Second Race", "second.png")):
        response = isolated_campaign_client.post(
            "/campaigns/linden-pass/session/articles",
            data={
                "title": title,
                "body_markdown": f"{title} body remains authoritative.",
                "image_file": (BytesIO(TEST_PNG_BYTES), filename),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

    page_store = isolated_campaign_app.extensions["campaign_page_store"]
    reconciler = isolated_campaign_app.extensions["player_wiki_reconciler"]
    repository_store = isolated_campaign_app.extensions["repository_store"]
    session_service = isolated_campaign_app.extensions["campaign_session_service"]
    start = Barrier(2)

    def convert(article_id: int):
        with isolated_campaign_app.app_context():
            campaign = repository_store.get().get_campaign(TEST_CAMPAIGN_SLUG)
            article = session_service.get_article(TEST_CAMPAIGN_SLUG, article_id)
            article_image = session_service.get_article_image(TEST_CAMPAIGN_SLUG, article_id)
            assert campaign is not None and article is not None and article_image is not None
            start.wait(timeout=5)
            try:
                result = publish_session_article(
                    campaign,
                    article,
                    article_image=article_image,
                    options=SessionArticlePublishOptions(
                        title=article.title,
                        slug_leaf="shared-race",
                        summary="One conversion wins.",
                        section="Notes",
                        page_type="note",
                        subsection="",
                        reveal_after_session=campaign.current_session,
                    ),
                    page_store=page_store,
                    reconciler=reconciler,
                )
                return ("ok", article_id, result)
            except SessionArticlePublishError as exc:
                return ("error", article_id, str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(convert, (1, 2)))

    winners = [outcome for outcome in outcomes if outcome[0] == "ok"]
    losers = [outcome for outcome in outcomes if outcome[0] == "error"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0][2] == "That wiki page slug is already in use. Choose a different slug."
    winner_id = winners[0][1]
    loser_id = losers[0][1]
    campaigns_dir = isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "shared-race.md"
    winner_asset = (
        campaigns_dir
        / "linden-pass"
        / "assets"
        / "session-articles"
        / f"article-{winner_id}-shared-race.webp"
    )
    loser_asset = (
        campaigns_dir
        / "linden-pass"
        / "assets"
        / "session-articles"
        / f"article-{loser_id}-shared-race.webp"
    )
    assert f"source_ref: session-article:linden-pass:{winner_id}" in page_path.read_text(
        encoding="utf-8"
    )
    assert_webp_bytes(winner_asset.read_bytes())
    assert not loser_asset.exists()
    with isolated_campaign_app.app_context():
        record = page_store.get_page_record(TEST_CAMPAIGN_SLUG, "notes/shared-race")
        assert record is not None
        assert record.page.source_ref == f"session-article:linden-pass:{winner_id}"
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0


@pytest.mark.parametrize("active_state", ("prepared", "conflict", "repository_pending"))
def test_convert_active_provenance_survives_restart(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
    active_state,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Durable Guard", "body_markdown": "Private source snapshot."},
        follow_redirects=False,
    )
    page_store = isolated_campaign_app.extensions["campaign_page_store"]
    repository_store = isolated_campaign_app.extensions["repository_store"]
    auth_store = isolated_campaign_app.extensions["auth_store"]
    session_service = isolated_campaign_app.extensions["campaign_session_service"]
    reconciler = isolated_campaign_app.extensions["player_wiki_reconciler"]
    failure_event = (
        "after_repository_pending" if active_state == "repository_pending" else "after_primary_publish"
    )

    def interrupt(event: str, _operation_id: str):
        if event == failure_event:
            raise RuntimeError(f"interrupt at {event}")

    with isolated_campaign_app.app_context():
        campaign = repository_store.get().get_campaign(TEST_CAMPAIGN_SLUG)
        article = session_service.get_article(TEST_CAMPAIGN_SLUG, 1)
        assert campaign is not None and article is not None
        options = SessionArticlePublishOptions(
            title="Durable Guard",
            slug_leaf="durable-guard-a",
            summary="Durable provenance guard.",
            section="Notes",
            page_type="note",
            subsection="",
            reveal_after_session=campaign.current_session,
        )
        reconciler.hooks = ReconciliationHooks(on_event=interrupt)
        with pytest.raises(RuntimeError, match=f"interrupt at {failure_event}"):
            publish_session_article(
                campaign,
                article,
                article_image=None,
                options=options,
                page_store=page_store,
                reconciler=reconciler,
            )
        reconciler.hooks = ReconciliationHooks()

        cold_reconciler = PlayerWikiReconciler(
            page_store=page_store,
            repository_store=repository_store,
            auth_store=auth_store,
        )
        original_path = (
            Path(campaign.player_content_dir) / "notes" / "durable-guard-a.md"
        )
        if active_state == "conflict":
            original_path.write_text("third-party authority", encoding="utf-8")
            assert cold_reconciler.recover_pending()["conflict"] == 1

        unrelated_path = Path(campaign.player_content_dir) / "notes" / "unrelated-sync.md"
        unrelated_path.write_text(
            "---\ntitle: Unrelated Sync\nsection: Notes\ntype: note\npublished: true\n---\n\nUnrelated.",
            encoding="utf-8",
        )
        page_store.scan_interval_seconds = 0
        assert page_store.scan_interval_seconds == 0
        page_store.sync_campaign_pages(TEST_CAMPAIGN_SLUG, Path(campaign.player_content_dir))
        assert page_store.get_page_record(TEST_CAMPAIGN_SLUG, "notes/unrelated-sync") is not None

        retry_options = SessionArticlePublishOptions(
            title="Durable Guard Retry",
            slug_leaf="durable-guard-b",
            summary="Must be refused.",
            section="Notes",
            page_type="note",
            subsection="",
            reveal_after_session=campaign.current_session,
        )
        with pytest.raises(
            SessionArticlePublishError,
            match="already been converted into wiki content",
        ):
            publish_session_article(
                campaign,
                article,
                article_image=None,
                options=retry_options,
                page_store=page_store,
                reconciler=cold_reconciler,
            )

        rows = get_db().execute(
            """
            SELECT page_ref, state
            FROM player_wiki_reconciliation_operations
            WHERE campaign_slug = ?
            ORDER BY page_ref
            """,
            (TEST_CAMPAIGN_SLUG,),
        ).fetchall()
        assert [(row["page_ref"], row["state"]) for row in rows] == [
            ("notes/durable-guard-a", active_state)
        ]
        assert page_store.get_page_record(TEST_CAMPAIGN_SLUG, "notes/durable-guard-b") is None
        assert not (
            Path(campaign.player_content_dir) / "notes" / "durable-guard-b.md"
        ).exists()


@pytest.mark.parametrize("active_state", ("prepared", "conflict"))
@pytest.mark.parametrize(
    ("payload_name", "private_payload"),
    (
        ("no-frontmatter", b"PRIVATE-RECOVERY-PAYLOAD-WITHOUT-FRONTMATTER"),
        ("unterminated-frontmatter", b"---\nsource_ref: session-article:linden-pass:1\nPRIVATE-UNTERMINATED"),
        ("malformed-frontmatter", b"---\nsource_ref: [PRIVATE-MALFORMED\n---\n\nBody."),
        ("missing-source-ref", b"---\ntitle: PRIVATE-MISSING-SOURCE\n---\n\nBody."),
        ("non-string-source-ref", b"---\nsource_ref:\n  - PRIVATE-NON-STRING\n---\n\nBody."),
        ("invalid-utf8", b"\xffPRIVATE-INVALID-UTF8"),
    ),
)
def test_convert_untrusted_active_payload_fails_closed(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
    active_state,
    payload_name,
    private_payload,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Malformed Guard", "body_markdown": "Private source snapshot."},
        follow_redirects=False,
    )
    page_store = isolated_campaign_app.extensions["campaign_page_store"]
    repository_store = isolated_campaign_app.extensions["repository_store"]
    auth_store = isolated_campaign_app.extensions["auth_store"]
    session_service = isolated_campaign_app.extensions["campaign_session_service"]
    reconciler = isolated_campaign_app.extensions["player_wiki_reconciler"]

    def interrupt(event: str, _operation_id: str):
        if event == "after_primary_publish":
            raise RuntimeError("freeze malformed guard")

    with isolated_campaign_app.app_context():
        campaign = repository_store.get().get_campaign(TEST_CAMPAIGN_SLUG)
        article = session_service.get_article(TEST_CAMPAIGN_SLUG, 1)
        assert campaign is not None and article is not None
        reconciler.hooks = ReconciliationHooks(on_event=interrupt)
        with pytest.raises(RuntimeError, match="freeze malformed guard"):
            publish_session_article(
                campaign,
                article,
                article_image=None,
                options=SessionArticlePublishOptions(
                    title="Malformed Guard",
                    slug_leaf="malformed-guard-a",
                    summary="Durable provenance guard.",
                    section="Notes",
                    page_type="note",
                    subsection="",
                    reveal_after_session=campaign.current_session,
                ),
                page_store=page_store,
                reconciler=reconciler,
            )
        reconciler.hooks = ReconciliationHooks()
        original_row = get_db().execute(
            "SELECT operation_id FROM player_wiki_reconciliation_operations"
        ).fetchone()
        assert original_row is not None
        original_operation_id = original_row["operation_id"]
        get_db().execute(
            """
            UPDATE player_wiki_reconciliation_operations
            SET desired_markdown = ?
            WHERE campaign_slug = ? AND page_ref = ?
            """,
            (private_payload, TEST_CAMPAIGN_SLUG, "notes/malformed-guard-a"),
        )
        get_db().commit()

        cold_reconciler = PlayerWikiReconciler(
            page_store=page_store,
            repository_store=repository_store,
            auth_store=auth_store,
        )
        if active_state == "conflict":
            assert cold_reconciler.recover_pending()["conflict"] == 1
        revision_before = session_service.get_live_revision(TEST_CAMPAIGN_SLUG)
        audit_count_before = get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log"
        ).fetchone()[0]
        with pytest.raises(
            SessionArticlePublishError,
            match="reconciliation requires repair",
        ) as caught:
            publish_session_article(
                campaign,
                article,
                article_image=None,
                options=SessionArticlePublishOptions(
                    title="Malformed Guard Retry",
                    slug_leaf="malformed-guard-b",
                    summary="Must fail closed.",
                    section="Notes",
                    page_type="note",
                    subsection="",
                    reveal_after_session=campaign.current_session,
                ),
                page_store=page_store,
                reconciler=cold_reconciler,
            )
        assert str(caught.value) == (
            "Player wiki reconciliation requires repair before converting this session article."
        )
        assert caught.value.__cause__ is None
        assert "PRIVATE" not in str(caught.value)
        assert "PRIVATE" not in repr(caught.value)
        rows = get_db().execute(
            """
            SELECT operation_id, state, desired_markdown
            FROM player_wiki_reconciliation_operations
            """
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["operation_id"] == original_operation_id
        assert rows[0]["state"] == active_state
        assert bytes(rows[0]["desired_markdown"]) == private_payload
        assert page_store.get_page_record(TEST_CAMPAIGN_SLUG, "notes/malformed-guard-b") is None
        assert not (
            Path(campaign.player_content_dir) / "notes" / "malformed-guard-b.md"
        ).exists()
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log"
        ).fetchone()[0] == audit_count_before
        assert session_service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before


def test_convert_valid_unrelated_active_provenance_is_allowed(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Allowed Conversion", "body_markdown": "Player-safe source."},
        follow_redirects=False,
    )
    page_store = isolated_campaign_app.extensions["campaign_page_store"]
    repository_store = isolated_campaign_app.extensions["repository_store"]
    session_service = isolated_campaign_app.extensions["campaign_session_service"]
    reconciler = isolated_campaign_app.extensions["player_wiki_reconciler"]

    def interrupt(event: str, _operation_id: str):
        if event == "after_primary_publish":
            raise RuntimeError("freeze unrelated provenance")

    with isolated_campaign_app.app_context():
        campaign = repository_store.get().get_campaign(TEST_CAMPAIGN_SLUG)
        article = session_service.get_article(TEST_CAMPAIGN_SLUG, 1)
        assert campaign is not None and article is not None
        unrelated = prepare_campaign_page_write(
            campaign,
            "notes/unrelated-active-provenance",
            metadata={
                "slug": "notes/unrelated-active-provenance",
                "title": "Unrelated Active Provenance",
                "section": "Notes",
                "type": "note",
                "source_ref": "external:provably-unrelated",
                "published": True,
            },
            body_markdown="Unrelated active body.",
            page_store=page_store,
        )
        reconciler.hooks = ReconciliationHooks(on_event=interrupt)
        with pytest.raises(RuntimeError, match="freeze unrelated provenance"):
            reconciler.mutate(campaign, unrelated, operation_kind="api_upsert")
        reconciler.hooks = ReconciliationHooks()
        unrelated_operation_id = get_db().execute(
            "SELECT operation_id FROM player_wiki_reconciliation_operations"
        ).fetchone()["operation_id"]

        result = publish_session_article(
            campaign,
            article,
            article_image=None,
            options=SessionArticlePublishOptions(
                title="Allowed Conversion",
                slug_leaf="allowed-conversion",
                summary="A valid unrelated journal does not block this source.",
                section="Notes",
                page_type="note",
                subsection="",
                reveal_after_session=campaign.current_session,
            ),
            page_store=page_store,
            reconciler=reconciler,
        )

        assert result.route_slug == "notes/allowed-conversion"
        stored = page_store.get_page_record(
            TEST_CAMPAIGN_SLUG,
            "notes/allowed-conversion",
        )
        assert stored is not None
        assert stored.page.source_ref == "session-article:linden-pass:1"
        rows = get_db().execute(
            "SELECT operation_id, page_ref, state FROM player_wiki_reconciliation_operations"
        ).fetchall()
        assert [(row["operation_id"], row["page_ref"], row["state"]) for row in rows] == [
            (unrelated_operation_id, "notes/unrelated-active-provenance", "prepared")
        ]


def test_session_convert_read_rejects_players_and_missing_articles(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Manager Conversion",
            "body_markdown": "Only a session manager may open this conversion view.",
        },
        follow_redirects=False,
    )
    assert create_article.status_code == 302

    missing = client.get("/campaigns/linden-pass/session/articles/999/convert")
    assert missing.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked = client.get("/campaigns/linden-pass/session/articles/1/convert")
    assert blocked.status_code == 403


def test_session_convert_read_propagates_context_dependency_failures(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    session_service = app.extensions["campaign_session_service"]

    def fail_article_read(*args, **kwargs):
        raise RuntimeError("characterized convert context failure")

    monkeypatch.setattr(session_service, "get_article", fail_article_read)
    with pytest.raises(RuntimeError, match="characterized convert context failure"):
        client.get("/campaigns/linden-pass/session/articles/1/convert")


def test_convert_rev_fault(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
    monkeypatch,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    create_article = isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Revision Boundary",
            "body_markdown": "This conversion remains durable before revision failure.",
            "image_alt": "A revision boundary marker.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "revision-boundary.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert create_article.status_code == 302

    session_service = isolated_campaign_app.extensions["campaign_session_service"]

    def fail_revision_bump(*args, **kwargs):
        raise RuntimeError("characterized session revision failure")

    monkeypatch.setattr(session_service, "bump_live_state_revision", fail_revision_bump)
    with pytest.raises(RuntimeError, match="characterized session revision failure"):
        isolated_campaign_client.post(
            "/campaigns/linden-pass/session/articles/1/convert",
            data={
                "title": "Revision Boundary",
                "slug_leaf": "rev",
                "summary": "A conversion boundary characterization.",
                "section": "Notes",
                "page_type": "note",
                "subsection": "",
                "reveal_after_session": "2",
            },
            follow_redirects=False,
        )

    campaigns_dir = isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "rev.md"
    asset_path = (
        campaigns_dir
        / "linden-pass"
        / "assets"
        / "session-articles"
        / "article-1-rev.webp"
    )
    assert page_path.exists()
    assert "source_ref: session-article:linden-pass:1" in page_path.read_text(encoding="utf-8")
    assert_webp_bytes(asset_path.read_bytes())
    with isolated_campaign_app.app_context():
        campaign = isolated_campaign_app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign.pages["notes/rev"].title == "Revision Boundary"


def test_convert_response_fault(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
    monkeypatch,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Response Boundary", "body_markdown": "Durable before response."},
        follow_redirects=False,
    )
    session_service = isolated_campaign_app.extensions["campaign_session_service"]
    with isolated_campaign_app.app_context():
        revision_before = session_service.get_live_revision(TEST_CAMPAIGN_SLUG)

    def fail_redirect(*_args, **_kwargs):
        raise RuntimeError("characterized conversion response failure")

    monkeypatch.setattr("player_wiki.session_routes.redirect", fail_redirect)
    with pytest.raises(RuntimeError, match="characterized conversion response failure"):
        isolated_campaign_client.post(
            "/campaigns/linden-pass/session/articles/1/convert",
            data={
                "title": "Response Boundary",
                "slug_leaf": "resp",
                "summary": "A response boundary characterization.",
                "section": "Notes",
                "page_type": "note",
                "subsection": "",
                "reveal_after_session": "2",
            },
            follow_redirects=False,
        )

    page_path = (
        isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "notes"
        / "resp.md"
    )
    assert page_path.exists()
    with isolated_campaign_app.app_context():
        record = isolated_campaign_app.extensions["campaign_page_store"].get_page_record(
            TEST_CAMPAIGN_SLUG,
            "notes/resp",
            include_body=True,
        )
        assert record is not None
        assert record.page.source_ref == "session-article:linden-pass:1"
        assert session_service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before + 1
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0


def test_session_convert_submit_preserves_form_helper_publish_and_revision_call_order(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Conversion Call Order",
            "body_markdown": "Characterize each request-time dependency.",
            "image_alt": "A dependency map.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "dependency-map.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    service = app.extensions["campaign_session_service"]
    page_store = app.extensions["campaign_page_store"]
    reconciler = app.extensions["player_wiki_reconciler"]
    original_normalize = app_module.normalize_publish_options
    original_bump = service.bump_live_state_revision
    calls = []

    def record_normalize(**kwargs):
        calls.append(("normalize", kwargs))
        return original_normalize(**kwargs)

    def record_publish(campaign, article, *, article_image, options, page_store, reconciler):
        calls.append(
            (
                "publish",
                campaign,
                article,
                article_image,
                options,
                page_store,
                reconciler,
            )
        )
        return SimpleNamespace(route_slug="notes/not-written-by-characterization")

    def record_bump(campaign_slug, *, updated_by_user_id=None):
        calls.append(("bump", campaign_slug, updated_by_user_id))
        return original_bump(campaign_slug, updated_by_user_id=updated_by_user_id)

    monkeypatch.setattr("player_wiki.app.normalize_publish_options", record_normalize)
    monkeypatch.setattr("player_wiki.app.publish_session_article", record_publish)
    monkeypatch.setattr(service, "bump_live_state_revision", record_bump)
    submitted = {
        "title": "  Published Call Order  ",
        "slug_leaf": " Published Call Order ",
        "summary": "  Exact summary.  ",
        "section": "Notes",
        "page_type": " Note Entry ",
        "subsection": "  Field Notes  ",
        "reveal_after_session": "999",
        "ignored_field": "must not reach normalization",
    }

    response = client.post(
        "/campaigns/linden-pass/session/articles/1/convert",
        data=submitted,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/session/articles/1/convert"
    )
    assert [call[0] for call in calls] == ["normalize", "publish", "bump"]
    assert calls[0][1] == {key: submitted[key] for key in (
        "title",
        "slug_leaf",
        "summary",
        "section",
        "page_type",
        "subsection",
        "reveal_after_session",
    )}
    _, campaign, article, article_image, options, passed_page_store, passed_reconciler = calls[1]
    assert campaign.slug == TEST_CAMPAIGN_SLUG
    assert article.id == 1
    assert article.title == "Conversion Call Order"
    assert article_image is not None
    assert article_image.filename == "dependency-map.png"
    assert options.title == "Published Call Order"
    assert options.slug_leaf == "published-call-order"
    assert options.summary == "Exact summary."
    assert options.page_type == "note-entry"
    assert options.subsection == "Field Notes"
    assert options.reveal_after_session == 999
    assert passed_page_store is page_store
    assert passed_reconciler is reconciler
    assert calls[2] == ("bump", TEST_CAMPAIGN_SLUG, users["dm"]["id"])


def test_session_convert_submit_validation_rerenders_exact_submitted_form_data(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Validation Target", "body_markdown": "Preserve the failed conversion form."},
        follow_redirects=False,
    )

    response = client.post(
        "/campaigns/linden-pass/session/articles/1/convert",
        data={
            "title": "",
            "slug_leaf": "preserved-slug",
            "summary": "Preserved summary text.",
            "section": "Bestiary",
            "page_type": "preserved-type",
            "subsection": "Preserved subsection",
            "reveal_after_session": "17",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Wiki pages need a title before they can be published." in html
    assert 'name="title" maxlength="200" value=""' in html
    assert 'name="slug_leaf" maxlength="120" value="preserved-slug"' in html
    assert ">Preserved summary text.</textarea>" in html
    assert 'value="Bestiary" selected' in html
    assert 'name="page_type" maxlength="80" value="preserved-type"' in html
    assert 'name="subsection" maxlength="120" value="Preserved subsection"' in html
    assert 'name="reveal_after_session" value="17"' in html


def test_session_convert_submit_future_reveal_redirects_back_with_exact_flash(
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Future Dispatch", "body_markdown": "Wait for the later campaign session."},
        follow_redirects=False,
    )

    response = isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles/1/convert",
        data={
            "title": "Future Dispatch",
            "slug_leaf": "future-dispatch",
            "summary": "A future dispatch.",
            "section": "Notes",
            "page_type": "note",
            "subsection": "",
            "reveal_after_session": "999",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/session/articles/1/convert"
    )
    redirected = isolated_campaign_client.get(response.headers["Location"])
    assert redirected.status_code == 200
    assert (
        "Session article converted into published wiki content. It will appear once the campaign reaches session 999."
        in redirected.get_data(as_text=True)
    )


@pytest.mark.parametrize("actor", ("party", "observer", "outsider"))
def test_session_convert_submit_preserves_role_and_scope_denials(client, sign_in, users, actor):
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.post(
        "/campaigns/linden-pass/session/articles/999/convert",
        follow_redirects=False,
    )

    assert response.status_code == (403 if actor == "party" else 404)


def test_session_convert_submit_manager_gate_precedes_current_user_lookup(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["party"]["email"], users["party"]["password"])
    handler = inspect.unwrap(app.view_functions["campaign_session_convert_article_submit"])
    monkeypatch.setitem(handler.__globals__, "can_manage_campaign_session", lambda _slug: False)

    def fail_current_user_lookup():
        raise AssertionError("manager denial must precede current-user lookup")

    monkeypatch.setitem(handler.__globals__, "get_current_user", fail_current_user_lookup)
    response = client.post(
        "/campaigns/linden-pass/session/articles/999/convert",
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_session_convert_submit_rejects_missing_current_user_after_manager_gate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    handler = inspect.unwrap(app.view_functions["campaign_session_convert_article_submit"])
    monkeypatch.setitem(handler.__globals__, "can_manage_campaign_session", lambda _slug: True)
    monkeypatch.setitem(handler.__globals__, "get_current_user", lambda: None)

    response = client.post(
        "/campaigns/linden-pass/session/articles/999/convert",
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_session_convert_submit_missing_article_404_precedes_image_lookup(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]

    def fail_image_lookup(*_args, **_kwargs):
        raise AssertionError("missing articles must abort before image lookup")

    monkeypatch.setattr(service, "get_article_image", fail_image_lookup)
    response = client.post(
        "/campaigns/linden-pass/session/articles/999/convert",
        follow_redirects=False,
    )

    assert response.status_code == 404


def test_session_convert_submit_csrf_failure_precedes_publish(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "CSRF Conversion", "body_markdown": "Must not publish."},
        follow_redirects=False,
    )
    calls = []

    def record_publish(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("publish must not run before CSRF denial")

    monkeypatch.setattr("player_wiki.app.publish_session_article", record_publish)
    app.config["CSRF_ENABLED"] = True
    response = client.post(
        "/campaigns/linden-pass/session/articles/1/convert",
        data={"title": "Blocked"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Refresh the page and try again." in response.get_data(as_text=True)
    assert calls == []


def test_session_convert_submit_unexpected_publish_fault_precedes_refresh_and_revision(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Publish Fault", "body_markdown": "Characterize unexpected failure."},
        follow_redirects=False,
    )
    service = app.extensions["campaign_session_service"]
    repository_store = app.extensions["repository_store"]
    with app.app_context():
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)

    def fail_publish(*_args, **_kwargs):
        raise RuntimeError("characterized conversion publish fault")

    def fail_later_dependency(*_args, **_kwargs):
        raise AssertionError("later dependencies must not run after publish fault")

    monkeypatch.setattr("player_wiki.app.publish_session_article", fail_publish)
    monkeypatch.setattr(repository_store, "refresh", fail_later_dependency)
    monkeypatch.setattr(service, "bump_live_state_revision", fail_later_dependency)

    with pytest.raises(RuntimeError, match="characterized conversion publish fault"):
        client.post(
            "/campaigns/linden-pass/session/articles/1/convert",
            data={
                "title": "Publish Fault",
                "slug_leaf": "publish-fault",
                "summary": "Fault characterization.",
                "section": "Notes",
                "page_type": "note",
                "subsection": "",
                "reveal_after_session": "2",
            },
            follow_redirects=False,
        )
    with app.app_context():
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before


def test_convert_ref_fault(
    isolated_campaign_app,
    isolated_campaign_client,
    isolated_campaign_sign_in,
    isolated_campaign_users,
    monkeypatch,
):
    isolated_campaign_sign_in(
        isolated_campaign_users["dm"]["email"],
        isolated_campaign_users["dm"]["password"],
    )
    isolated_campaign_client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Refresh Boundary",
            "body_markdown": "This conversion remains durable before refresh failure.",
            "image_alt": "A refresh boundary marker.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "refresh-boundary.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    repository_store = isolated_campaign_app.extensions["repository_store"]

    original_refresh = repository_store.refresh_from_database

    def fail_refresh():
        raise RuntimeError("characterized repository refresh failure")

    monkeypatch.setattr(repository_store, "refresh_from_database", fail_refresh)
    with pytest.raises(RuntimeError, match="characterized repository refresh failure"):
        isolated_campaign_client.post(
            "/campaigns/linden-pass/session/articles/1/convert",
            data={
                "title": "Refresh Boundary",
                "slug_leaf": "ref",
                "summary": "A refresh boundary characterization.",
                "section": "Notes",
                "page_type": "note",
                "subsection": "",
                "reveal_after_session": "2",
            },
            follow_redirects=False,
        )

    campaigns_dir = isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "ref.md"
    asset_path = (
        campaigns_dir
        / "linden-pass"
        / "assets"
        / "session-articles"
        / "article-1-ref.webp"
    )
    assert page_path.exists()
    assert "source_ref: session-article:linden-pass:1" in page_path.read_text(encoding="utf-8")
    assert_webp_bytes(asset_path.read_bytes())
    with isolated_campaign_app.app_context():
        campaign = repository_store.get().get_campaign(TEST_CAMPAIGN_SLUG)
        assert "notes/ref" not in campaign.pages
        pending = get_db().execute(
            """
            SELECT state
            FROM player_wiki_reconciliation_operations
            WHERE campaign_slug = ? AND page_ref = ?
            """,
            (TEST_CAMPAIGN_SLUG, "notes/ref"),
        ).fetchone()
        assert pending is not None
        assert pending["state"] == "repository_pending"

    monkeypatch.setattr(repository_store, "refresh_from_database", original_refresh)
    with isolated_campaign_app.app_context():
        outcome = isolated_campaign_app.extensions["player_wiki_reconciler"].recover_pending()
        assert outcome["recovered"] == 1
        campaign = repository_store.get().get_campaign(TEST_CAMPAIGN_SLUG)
        assert campaign.pages["notes/ref"].title == "Refresh Boundary"
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0


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
    staged_page = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    assert staged_page.status_code == 200
    assert "Temporary Briefing" in staged_page.get_data(as_text=True)

    delete_article = client.post(
        "/campaigns/linden-pass/session/articles/1/delete",
        follow_redirects=True,
    )

    assert delete_article.status_code == 200
    delete_html = delete_article.get_data(as_text=True)
    assert "Session article deleted." in delete_html
    assert "Temporary Briefing" not in delete_html
    assert "This staged article should be removable." not in delete_html


@pytest.mark.parametrize("async_request", (False, True))
@pytest.mark.parametrize(
    (
        "operation",
        "path",
        "service_method",
        "service_result",
        "expected_args",
        "expected_kwargs",
        "expected_flash",
        "expected_anchor",
    ),
    (
        (
            "reveal",
            "/campaigns/linden-pass/session/articles/99/reveal",
            "reveal_article",
            None,
            (TEST_CAMPAIGN_SLUG, 99),
            "reveal",
            "Session article revealed on the player Session page and saved to the chat history.",
            "session-revealed-articles",
        ),
        (
            "delete staged",
            "/campaigns/linden-pass/session/articles/99/delete",
            "delete_article",
            SimpleNamespace(is_revealed=False),
            (TEST_CAMPAIGN_SLUG, 99),
            "updated",
            "Session article deleted.",
            "session-staged-articles",
        ),
        (
            "delete revealed",
            "/campaigns/linden-pass/session/articles/99/delete",
            "delete_article",
            SimpleNamespace(is_revealed=True),
            (TEST_CAMPAIGN_SLUG, 99),
            "updated",
            "Session article deleted. Related reveal entries were removed from chat and logs.",
            "session-revealed-articles",
        ),
        (
            "clear singular",
            "/campaigns/linden-pass/session/articles/clear-revealed",
            "delete_revealed_articles",
            [SimpleNamespace(id=99)],
            (TEST_CAMPAIGN_SLUG,),
            "updated",
            "Cleared 1 revealed session article.",
            "session-revealed-articles",
        ),
    ),
)
def test_session_article_lifecycle_preserves_service_arguments_and_sync_async_responses(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    async_request,
    operation,
    path,
    service_method,
    service_result,
    expected_args,
    expected_kwargs,
    expected_flash,
    expected_anchor,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    calls = []

    def record_service_call(*args, **kwargs):
        calls.append((args, kwargs))
        return service_result

    monkeypatch.setattr(service, service_method, record_service_call)
    response = client.post(
        path,
        headers=_async_headers() if async_request else None,
        follow_redirects=not async_request,
    )

    assert response.status_code == 200
    if expected_kwargs == "reveal":
        expected_call_kwargs = {
            "revealed_by_user_id": users["dm"]["id"],
            "author_display_name": "Dungeon Master",
        }
    else:
        expected_call_kwargs = {"updated_by_user_id": users["dm"]["id"]}
    assert calls == [(expected_args, expected_call_kwargs)]
    if async_request:
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["anchor"] == expected_anchor
        assert expected_flash in payload["flash_html"]
    else:
        expected_dm_view = (
            "revealed"
            if operation in {"reveal", "delete revealed", "clear singular"}
            else "staged"
        )
        assert response.history[0].headers["Location"].endswith(
            f"/campaigns/linden-pass/session/dm?dm_view={expected_dm_view}#{expected_anchor}"
        )
        assert expected_flash in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("endpoint", "path"),
    (
        (
            "campaign_session_reveal_article",
            "/campaigns/linden-pass/session/articles/99/reveal",
        ),
        (
            "campaign_session_delete_article",
            "/campaigns/linden-pass/session/articles/99/delete",
        ),
        (
            "campaign_session_clear_revealed_articles",
            "/campaigns/linden-pass/session/articles/clear-revealed",
        ),
    ),
)
def test_session_article_lifecycle_rejects_missing_current_user_after_manager_gate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    endpoint,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    handler = inspect.unwrap(app.view_functions[endpoint])
    monkeypatch.setitem(handler.__globals__, "can_manage_campaign_session", lambda _slug: True)
    monkeypatch.setitem(handler.__globals__, "get_current_user", lambda: None)

    response = client.post(path, follow_redirects=False)

    assert response.status_code == 403


@pytest.mark.parametrize("actor", ("party", "observer", "outsider"))
@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/session/articles/99/reveal",
        "/campaigns/linden-pass/session/articles/99/delete",
        "/campaigns/linden-pass/session/articles/clear-revealed",
    ),
)
def test_session_article_lifecycle_preserves_role_and_scope_denials(
    client,
    sign_in,
    users,
    actor,
    path,
):
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.post(path, follow_redirects=False)

    assert response.status_code == (403 if actor == "party" else 404)


def test_session_article_reveal_preserves_no_active_missing_and_already_revealed_validation(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Validation Reveal", "body_markdown": "Reveal validation target."},
        follow_redirects=False,
    )
    service = app.extensions["campaign_session_service"]

    no_active = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert no_active.status_code == 200
    no_active_payload = no_active.get_json()
    assert no_active_payload["ok"] is False
    assert no_active_payload["anchor"] == "session-revealed-articles"
    assert "Begin a session before revealing articles in the chat." in no_active_payload["flash_html"]

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    missing = client.post(
        "/campaigns/linden-pass/session/articles/999/reveal",
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert missing.status_code == 200
    missing_payload = missing.get_json()
    assert missing_payload["ok"] is False
    assert missing_payload["anchor"] == "session-revealed-articles"
    assert "That session article could not be found." in missing_payload["flash_html"]

    first_reveal = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=False,
    )
    assert first_reveal.status_code == 302
    with app.app_context():
        revision_before_duplicate = service.get_live_revision(TEST_CAMPAIGN_SLUG)
    duplicate = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert duplicate.status_code == 200
    duplicate_payload = duplicate.get_json()
    assert duplicate_payload["ok"] is False
    assert duplicate_payload["anchor"] == "session-revealed-articles"
    assert "That session article has already been revealed." in duplicate_payload["flash_html"]
    with app.app_context():
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before_duplicate


def test_session_article_delete_missing_returns_article_store_validation_response(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    with app.app_context():
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)

    response = client.post(
        "/campaigns/linden-pass/session/articles/999/delete",
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == "session-article-store"
    assert "That session article could not be found." in payload["flash_html"]
    with app.app_context():
        assert service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before


def test_session_article_clear_validation_returns_revealed_anchor(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]

    def fail_clear(*_args, **_kwargs):
        raise CampaignSessionValidationError("Characterized clear validation failure.")

    monkeypatch.setattr(service, "delete_revealed_articles", fail_clear)
    response = client.post(
        "/campaigns/linden-pass/session/articles/clear-revealed",
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == "session-revealed-articles"
    assert "Characterized clear validation failure." in payload["flash_html"]


@pytest.mark.parametrize("async_request", (False, True))
@pytest.mark.parametrize(
    ("revealed_count", "expected_flash"),
    (
        (0, "There are no revealed session articles to clear."),
        (1, "Cleared 1 revealed session article."),
        (2, "Cleared 2 revealed session articles."),
    ),
)
def test_session_article_clear_preserves_empty_singular_plural_and_one_bump_semantics(
    app,
    client,
    sign_in,
    users,
    async_request,
    revealed_count,
    expected_flash,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    if revealed_count:
        client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
        for article_number in range(1, revealed_count + 1):
            client.post(
                "/campaigns/linden-pass/session/articles",
                data={
                    "title": f"Clear target {article_number}",
                    "body_markdown": "Clear this revealed lifecycle target.",
                },
                follow_redirects=False,
            )
            client.post(
                f"/campaigns/linden-pass/session/articles/{article_number}/reveal",
                follow_redirects=False,
            )
    with app.app_context():
        revision_before = service.get_live_revision(TEST_CAMPAIGN_SLUG)

    response = client.post(
        "/campaigns/linden-pass/session/articles/clear-revealed",
        headers=_async_headers() if async_request else None,
        follow_redirects=not async_request,
    )

    assert response.status_code == 200
    if async_request:
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["anchor"] == "session-revealed-articles"
        assert expected_flash in payload["flash_html"]
    else:
        assert response.history[0].headers["Location"].endswith(
            "/campaigns/linden-pass/session/dm?dm_view=revealed#session-revealed-articles"
        )
        assert expected_flash in response.get_data(as_text=True)
    with app.app_context():
        revision_after = service.get_live_revision(TEST_CAMPAIGN_SLUG)
        assert revision_after == revision_before + (1 if revealed_count else 0)
        assert service.list_articles(TEST_CAMPAIGN_SLUG, statuses=("revealed",)) == []


@pytest.mark.parametrize(
    ("service_method", "path"),
    (
        ("reveal_article", "/campaigns/linden-pass/session/articles/99/reveal"),
        ("delete_article", "/campaigns/linden-pass/session/articles/99/delete"),
        ("delete_revealed_articles", "/campaigns/linden-pass/session/articles/clear-revealed"),
    ),
)
def test_session_article_lifecycle_unexpected_service_faults_propagate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    service_method,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]

    def fail_service(*_args, **_kwargs):
        raise RuntimeError(f"characterized {service_method} fault")

    monkeypatch.setattr(service, service_method, fail_service)
    with pytest.raises(RuntimeError, match=f"characterized {service_method} fault"):
        client.post(path, follow_redirects=False)


@pytest.mark.parametrize(
    ("service_method", "path"),
    (
        ("reveal_article", "/campaigns/linden-pass/session/articles/99/reveal"),
        ("delete_article", "/campaigns/linden-pass/session/articles/99/delete"),
        ("delete_revealed_articles", "/campaigns/linden-pass/session/articles/clear-revealed"),
    ),
)
def test_session_article_lifecycle_csrf_failure_precedes_service(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    service_method,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    service = app.extensions["campaign_session_service"]
    calls = []

    def record_service(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("lifecycle service must not run before CSRF denial")

    monkeypatch.setattr(service, service_method, record_service)
    app.config["CSRF_ENABLED"] = True
    response = client.post(path, follow_redirects=False)

    assert response.status_code == 400
    assert "Refresh the page and try again." in response.get_data(as_text=True)
    assert calls == []


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


def test_dm_can_clear_all_revealed_session_articles(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Read Aloud Notice",
            "body_markdown": "This should be cleared in bulk.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Burn After Reading",
            "body_markdown": "This should be cleared in bulk too.",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Staged Holdback",
            "body_markdown": "This should stay staged when bulk clear runs.",
        },
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=False)
    client.post("/campaigns/linden-pass/session/articles/2/reveal", follow_redirects=False)

    dm_view = client.get(
        "/campaigns/linden-pass/session/dm?dm_view=revealed",
        follow_redirects=False,
    )
    assert dm_view.status_code == 200
    dm_html = dm_view.get_data(as_text=True)
    assert "Clear all" in dm_html
    assert "Read Aloud Notice" in dm_html
    assert "Burn After Reading" in dm_html
    assert 'data-destructive-confirmation-risk="higher"' in dm_html
    assert 'data-presentation-dialog-trigger="session-clear-revealed-confirmation"' in dm_html
    assert 'data-destructive-confirmation-form' in dm_html
    assert 'name="destructive_acknowledgement"' in dm_html
    assert "This removes all 2 revealed session articles" in dm_html
    assert "related reveal chat and log entries" in dm_html
    assert "Staged articles remain unchanged." in dm_html
    assert "The result could not be confirmed. Refresh Session before repeating this action." in dm_html
    assert 'data-session-confirm=' not in dm_html

    clear_response = client.post(
        "/campaigns/linden-pass/session/articles/clear-revealed",
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert clear_response.status_code == 200
    clear_payload = clear_response.get_json()
    assert clear_payload["anchor"] == "session-revealed-articles"
    assert clear_payload["ok"] is True
    assert "Read Aloud Notice" not in clear_payload["revealed_articles_html"]
    assert "Burn After Reading" not in clear_payload["revealed_articles_html"]

    dm_view = client.get(
        "/campaigns/linden-pass/session/dm?dm_view=revealed",
        follow_redirects=False,
    )
    assert dm_view.status_code == 200
    dm_html = dm_view.get_data(as_text=True)
    assert "Clear all" not in dm_html
    assert "Read Aloud Notice" not in dm_html
    assert "Burn After Reading" not in dm_html
    assert "Staged Holdback" not in dm_html

    staged_view = client.get(
        "/campaigns/linden-pass/session/dm?dm_view=staged",
        follow_redirects=False,
    )
    assert staged_view.status_code == 200
    staged_html = staged_view.get_data(as_text=True)
    assert "Staged Holdback" in staged_html
    assert "This should stay staged when bulk clear runs." in staged_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_view = client.get("/campaigns/linden-pass/session")
    player_html = player_view.get_data(as_text=True)
    assert player_view.status_code == 200
    assert "Read Aloud Notice" not in player_html
    assert "Burn After Reading" not in player_html
    assert "Staged Holdback" not in player_html


def test_player_cannot_clear_all_revealed_session_articles(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Protected from clear",
            "body_markdown": "Only DM should be able to clear this.",
        },
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=False)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    blocked_clear = client.post(
        "/campaigns/linden-pass/session/articles/clear-revealed",
        follow_redirects=False,
    )

    assert blocked_clear.status_code == 403


def test_dm_can_close_session_and_access_chat_log_but_player_cannot(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={"body": "Keep this exchange in the session log."},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/messages",
        data={
            "body": "Manager-only history remains visible in the stored log.",
            "recipient_scope": "dm_only",
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Ashcombe Note",
            "body_markdown": "The meeting has moved to the ash yard.",
            "image_alt": "A charcoal sketch of the ash yard.",
            "image_caption": "Filed with the closed session.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "ashcombe-note.png"),
        },
        content_type="multipart/form-data",
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
    assert "Manager-only history remains visible in the stored log." in log_html
    assert "DM-only" in log_html
    assert "Ashcombe Note" in log_html
    assert "The meeting has moved to the ash yard." in log_html
    assert 'src="/campaigns/linden-pass/session-article-images/1"' in log_html
    assert 'alt="A charcoal sketch of the ash yard."' in log_html
    assert "Filed with the closed session." in log_html

    session_page = client.get("/campaigns/linden-pass/session/dm?dm_view=logs")
    session_html = session_page.get_data(as_text=True)
    assert "No active session is running right now." in session_html
    assert "Session log from" in session_html
    assert 'href="/campaigns/linden-pass/session/logs/1"' in session_html
    assert 'action="/campaigns/linden-pass/session/logs/1/delete"' in session_html
    assert 'name="_csrf_token"' in session_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked_log = client.get(log_path)
    assert blocked_log.status_code == 403


def test_session_start_and_close_persist_actor_state_redirects_and_flashes(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    start = client.post(
        "/campaigns/linden-pass/session/start",
        follow_redirects=False,
    )
    assert start.status_code == 302
    assert start.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=tools#session-controls"
    )

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        active_session = service.get_active_session(TEST_CAMPAIGN_SLUG)
        state_after_start = service.store.get_state(TEST_CAMPAIGN_SLUG)
    assert active_session is not None
    assert active_session.started_by_user_id == users["dm"]["id"]
    assert state_after_start is not None
    assert state_after_start.updated_by_user_id == users["dm"]["id"]

    close = client.post(
        "/campaigns/linden-pass/session/close",
        follow_redirects=False,
    )
    assert close.status_code == 302
    assert close.headers["Location"].endswith(
        f"/campaigns/linden-pass/session/logs/{active_session.id}"
    )

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        assert service.get_active_session(TEST_CAMPAIGN_SLUG) is None
        closed_session = service.get_session_log(TEST_CAMPAIGN_SLUG, active_session.id)
        state_after_close = service.store.get_state(TEST_CAMPAIGN_SLUG)
    assert closed_session is not None
    assert closed_session.ended_by_user_id == users["dm"]["id"]
    assert state_after_close is not None
    assert state_after_close.revision > state_after_start.revision
    assert state_after_close.updated_by_user_id == users["dm"]["id"]

    log_response = client.get(close.headers["Location"])
    assert log_response.status_code == 200
    assert "Session started. Players can now use the Session page chat." in log_response.get_data(
        as_text=True
    )
    assert "Session closed. The chat contents are now stored as a chat log." in log_response.get_data(
        as_text=True
    )


def test_session_sync_mutations_redirect_to_their_canonical_dm_tasks(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    start = client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    assert start.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=tools#session-controls"
    )

    create_validation = client.post(
        "/campaigns/linden-pass/session/articles",
        data={"article_mode": "manual"},
        follow_redirects=False,
    )
    assert create_validation.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=article-store&article_mode=manual#session-article-store"
    )

    create = client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "Redirect map", "body_markdown": "Map each native fallback."},
        follow_redirects=False,
    )
    assert create.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=article-store&article_mode=manual#session-article-store"
    )

    update = client.post(
        "/campaigns/linden-pass/session/articles/1",
        data={"title": "Redirect map updated", "body_markdown": "Still staged."},
        follow_redirects=False,
    )
    assert update.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=staged#session-staged-articles"
    )

    reveal = client.post(
        "/campaigns/linden-pass/session/articles/1/reveal",
        follow_redirects=False,
    )
    assert reveal.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=revealed#session-revealed-articles"
    )

    close = client.post("/campaigns/linden-pass/session/close", follow_redirects=False)
    assert close.headers["Location"].endswith("/campaigns/linden-pass/session/logs/1")
    delete_log = client.post(
        "/campaigns/linden-pass/session/logs/1/delete",
        follow_redirects=False,
    )
    assert delete_log.headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=logs#session-chat-logs"
    )


def test_session_close_without_active_session_flashes_error_and_returns_to_controls(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        "/campaigns/linden-pass/session/close",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.history[0].headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=tools#session-controls"
    )
    assert "There is no active session to close." in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("service_method", "path", "prepare"),
    (
        ("begin_session", "/campaigns/linden-pass/session/start", "none"),
        ("close_session", "/campaigns/linden-pass/session/close", "active"),
        (
            "delete_session_log",
            "/campaigns/linden-pass/session/logs/1/delete",
            "closed",
        ),
    ),
)
def test_session_lifecycle_dependency_exceptions_propagate(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    service_method,
    path,
    prepare,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        service = app.extensions["campaign_session_service"]
        if prepare in {"active", "closed"}:
            service.begin_session(TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"])
        if prepare == "closed":
            service.close_session(TEST_CAMPAIGN_SLUG, ended_by_user_id=users["dm"]["id"])

    def fail_dependency(*args, **kwargs):
        raise RuntimeError(f"characterized {service_method} failure")

    monkeypatch.setattr(service, service_method, fail_dependency)
    with pytest.raises(RuntimeError, match=f"characterized {service_method} failure"):
        client.post(path, follow_redirects=False)


def test_session_log_read_rejects_active_and_missing_logs(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    start = client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    assert start.status_code == 302

    active_log = client.get("/campaigns/linden-pass/session/logs/1")
    missing_log = client.get("/campaigns/linden-pass/session/logs/999")

    assert active_log.status_code == 404
    assert missing_log.status_code == 404


def test_session_log_read_propagates_service_failures(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    session_service = app.extensions["campaign_session_service"]

    def fail_log_read(*args, **kwargs):
        raise RuntimeError("characterized session log failure")

    monkeypatch.setattr(session_service, "get_session_log", fail_log_read)
    with pytest.raises(RuntimeError, match="characterized session log failure"):
        client.get("/campaigns/linden-pass/session/logs/1")


def test_dm_can_delete_closed_chat_log(app, client, sign_in, users, monkeypatch):
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

    with app.app_context():
        session_service = app.extensions["campaign_session_service"]
        revision_before = session_service.get_live_revision(TEST_CAMPAIGN_SLUG)
    original_delete_session_log = session_service.delete_session_log
    calls = []

    def record_delete_session_log(campaign_slug, session_id, *, updated_by_user_id=None):
        calls.append((campaign_slug, session_id, updated_by_user_id))
        return original_delete_session_log(
            campaign_slug,
            session_id,
            updated_by_user_id=updated_by_user_id,
        )

    monkeypatch.setattr(session_service, "delete_session_log", record_delete_session_log)

    delete_response = client.post(
        "/campaigns/linden-pass/session/logs/1/delete",
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    delete_html = delete_response.get_data(as_text=True)
    assert "Chat log deleted." in delete_html
    assert "Session log from" not in delete_html
    assert calls == [(TEST_CAMPAIGN_SLUG, 1, users["dm"]["id"])]

    with app.app_context():
        assert session_service.get_live_revision(TEST_CAMPAIGN_SLUG) > revision_before

    deleted_log = client.get(log_path)
    assert deleted_log.status_code == 404


def test_session_log_delete_missing_flashes_error_and_returns_to_logs(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        "/campaigns/linden-pass/session/logs/999/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.history[0].headers["Location"].endswith(
        "/campaigns/linden-pass/session/dm?dm_view=logs#session-chat-logs"
    )
    assert "That chat log could not be found." in response.get_data(as_text=True)


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
