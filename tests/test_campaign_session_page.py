from __future__ import annotations

from tests.helpers.character_state_helpers import (
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.helpers.systems_import_helpers import _import_systems_goblin
from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign
import json
import shutil
from io import BytesIO
from pathlib import Path
import yaml

import pytest
from werkzeug.security import generate_password_hash

from player_wiki.app import create_app
from player_wiki.auth_store import AuthStore
from player_wiki.config import Config
from player_wiki.db import get_db_query_metrics, init_database, reset_db_query_metrics
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG, build_test_campaigns_dir


TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def test_player_cannot_open_dm_session_workspace(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm")

    assert dm_page.status_code == 403


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
    assert "hidden" not in {line.strip() for line in spells_panel.splitlines()}
    assert "hidden" in {line.strip() for line in overview_panel.splitlines()}
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


def test_session_character_inventory_row_links_and_details_use_session_item_popup(
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
    assert 'data-character-spell-modal-trigger' in inventory_panel
    assert 'data-character-spell-modal' in inventory_panel
    assert 'session-inventory-item-detail-' in inventory_panel
    assert "<noscript>" in inventory_panel
    assert "A campaign-linked session inventory item." in inventory_panel


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
    session_script = _session_live_script_text()
    assert "window.__playerWikiLiveUiTools" in session_script
    assert "uiStateTools.captureViewportAnchor(liveRoot)" in session_script
    assert 'liveRoot.dataset.loading = "1";' in session_script


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
    assert '/static/session-live.js?v=' in session_html
    session_script = _session_live_script_text()
    assert 'const collectOpenSessionArticleIds = (root) => {' in session_script
    assert 'restoreOpenSessionArticleIds(stagedRoot, openSessionArticleIds);' in session_script
    assert 'restoreOpenSessionArticleIds(revealedRoot, openSessionArticleIds);' in session_script
    assert session_script.count('statusCard = liveRoot.querySelector("[data-session-status-card]");') == 2


def test_dm_can_open_session_page_and_session_dm_page(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    session_page = client.get("/campaigns/linden-pass/session")
    dm_page = client.get("/campaigns/linden-pass/session/dm")

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
    assert "Session article store" in dm_html
    assert "Chat logs" in dm_html
    assert "Back to wiki" not in dm_html
    assert "Open DM page" not in dm_html
    assert 'data-live-active-interval-ms="2000"' in dm_html
    assert 'data-live-idle-interval-ms="5000"' in dm_html


def test_dm_session_layout_places_status_controls_in_sidebar_and_prioritizes_workflow_cards(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert 'id="session-controls"' in dm_html
    assert 'data-session-controls-root' in dm_html
    assert dm_html.count('id="session-controls"') == 1
    assert dm_html.count('<div data-session-controls-root>') == 1
    assert "Session controls" in dm_html
    assert "Session article store" in dm_html

    sidebar_start = dm_html.find('<aside class="session-sidebar">')
    controls_index = dm_html.find('id="session-controls"')
    article_store_index = dm_html.find('id="session-article-store"')
    assert sidebar_start != -1 and controls_index != -1 and article_store_index != -1
    assert sidebar_start < controls_index < article_store_index

    passive_scores_index = dm_html.find('data-session-passive-scores-bar')
    staged_index = dm_html.find('data-session-staged-root')
    revealed_index = dm_html.find('data-session-revealed-root')
    logs_index = dm_html.find('data-session-logs-root')
    assert passive_scores_index != -1
    assert staged_index != -1
    assert revealed_index != -1
    assert logs_index != -1
    assert passive_scores_index < staged_index < revealed_index < logs_index

    sidebar_end = dm_html.find("</aside>", sidebar_start)
    assert sidebar_end != -1
    sidebar_segment = dm_html[sidebar_start:sidebar_end]
    assert 'data-session-staged-root' not in sidebar_segment
    assert 'data-session-revealed-root' not in sidebar_segment
    assert 'data-session-logs-root' not in sidebar_segment


def test_dm_session_page_shows_passive_scores_for_active_dnd_characters(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm")
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

    dm_page = client.get("/campaigns/linden-pass/session/dm")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert "DM Passive Scores" not in dm_html
    assert 'data-session-passive-scores-bar' not in dm_html


def test_dm_session_page_filters_non_dnd_characters_from_passive_scores(
    client, app, sign_in, users
):
    _set_character_system(app, "arden-march", "xianxia")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm")
    dm_html = dm_page.get_data(as_text=True)

    assert dm_page.status_code == 200
    assert "DM Passive Scores" in dm_html
    assert '<h3 class="session-passive-score-card__name">Arden March</h3>' not in dm_html
    assert '<h3 class="session-passive-score-card__name">Selene Brook</h3>' in dm_html
    assert '<h3 class="session-passive-score-card__name">Tobin Slate</h3>' in dm_html


def test_dm_session_page_shows_empty_state_when_no_dnd_characters_are_visible(client, app, sign_in, users):
    _set_characters_system(app, "xianxia")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/session/dm")
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
    session_page = client.get("/campaigns/linden-pass/session/dm")

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

    session_page = isolated_campaign_client.get("/campaigns/linden-pass/session/dm")
    session_html = session_page.get_data(as_text=True)
    assert session_page.status_code == 200
    assert "View published page" in session_html
    assert "/campaigns/linden-pass/pages/notes/courier-seal" in session_html


def test_session_conversion_revision_failure_leaves_published_page_and_image_durable(
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
                "slug_leaf": "revision-boundary",
                "summary": "A conversion boundary characterization.",
                "section": "Notes",
                "page_type": "note",
                "subsection": "",
                "reveal_after_session": "2",
            },
            follow_redirects=False,
        )

    campaigns_dir = isolated_campaign_app.config["TEST_CAMPAIGNS_DIR"]
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "revision-boundary.md"
    asset_path = (
        campaigns_dir
        / "linden-pass"
        / "assets"
        / "session-articles"
        / "article-1-revision-boundary.webp"
    )
    assert page_path.exists()
    assert "source_ref: session-article:linden-pass:1" in page_path.read_text(encoding="utf-8")
    assert_webp_bytes(asset_path.read_bytes())
    with isolated_campaign_app.app_context():
        campaign = isolated_campaign_app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign.pages["notes/revision-boundary"].title == "Revision Boundary"


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

    dm_view = client.get("/campaigns/linden-pass/session/dm", follow_redirects=False)
    assert dm_view.status_code == 200
    dm_html = dm_view.get_data(as_text=True)
    assert "Clear all" in dm_html
    assert "Read Aloud Notice" in dm_html
    assert "Burn After Reading" in dm_html

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

    dm_view = client.get("/campaigns/linden-pass/session/dm", follow_redirects=False)
    assert dm_view.status_code == 200
    dm_html = dm_view.get_data(as_text=True)
    assert "Clear all" not in dm_html
    assert "Read Aloud Notice" not in dm_html
    assert "Burn After Reading" not in dm_html
    assert "Staged Holdback" in dm_html
    assert "This should stay staged when bulk clear runs." in dm_html

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
