from __future__ import annotations

from pathlib import Path

from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db
from tests.sample_data import TEST_CAMPAIGN_TITLE


def test_anonymous_user_can_browse_public_campaign_content(client):
    response = client.get("/campaigns/linden-pass")
    page = client.get("/campaigns/linden-pass/pages/index")
    campaigns = client.get("/campaigns")

    assert response.status_code == 200
    assert page.status_code == 200
    assert campaigns.status_code == 200

    body = response.get_data(as_text=True)
    campaigns_body = campaigns.get_data(as_text=True)

    assert TEST_CAMPAIGN_TITLE in body
    assert "Operations Brief" in body
    assert "Campaign Home" in body
    assert 'href="/campaigns/linden-pass/help"' in body
    assert 'href="/campaigns/linden-pass/session"' not in body
    assert 'href="/campaigns/linden-pass/combat"' not in body
    assert 'href="/campaigns/linden-pass/characters"' not in body
    assert "Sign in" in body

    assert TEST_CAMPAIGN_TITLE in campaigns_body
    assert "System: DND-5E" in campaigns_body


def test_header_brand_routes_to_campaign_picker_without_separate_campaigns_button(client):
    response = client.get("/campaigns/linden-pass")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '<a class="brand" href="/campaigns">Campaign Player Wiki</a>' in body
    assert '<a class="header-link" href="/campaigns">Campaigns</a>' not in body


def test_account_settings_require_sign_in(client):
    response = client.get("/account", follow_redirects=False)

    assert response.status_code == 302
    assert "/sign-in?next=/account" in response.headers["Location"]


def test_signed_in_user_can_open_account_settings_with_default_theme(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/account")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'href="/account"' in body
    assert 'data-theme="parchment"' in body
    assert "Color theme" in body
    assert "Live session chat order" in body
    assert "Parchment" in body
    assert "Newest first" in body


def test_campaign_member_can_browse_visible_wiki_content(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    page = client.get("/campaigns/linden-pass/pages/index")

    assert campaign.status_code == 200
    assert page.status_code == 200

    body = campaign.get_data(as_text=True)
    assert TEST_CAMPAIGN_TITLE in body
    assert "Campaign Home" in body
    assert "Operations Brief" in body
    assert "Harbor Row" in body
    assert "Session" in body
    assert "Combat" in body
    assert "Help" in body
    assert 'href="/campaigns/linden-pass/help"' in body
    assert 'href="/campaigns/linden-pass/session"' in body
    assert 'href="/campaigns/linden-pass/combat"' in body
    assert 'href="/campaigns/linden-pass/dm-content"' not in body
    assert 'href="/campaigns/linden-pass/characters"' not in body
    assert "site-header__secondary" in body
    assert "site-header__main" in body
    assert "site-search-form" in body
    assert "Visible through session" not in body
    assert "pages visible" not in body
    assert page.get_data(as_text=True).count("Echoes of the Alloy Coast") >= 1


def test_campaign_help_page_collects_surface_guidance_and_limits(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/help")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f"{TEST_CAMPAIGN_TITLE} Help" in body
    assert "Current access" in body
    assert "Campaign Home" in body
    assert "Systems" in body
    assert "Session" in body
    assert "Combat" in body
    assert "DM Content" not in body
    assert "Characters" not in body
    assert "Control" not in body
    assert "Cross-cutting limits" in body
    assert "Visibility by scope" in body
    assert "Session and Combat refresh with polling instead of websockets." in body
    assert 'href="/campaigns/linden-pass/session"' in body
    assert 'href="/campaigns/linden-pass/combat"' in body
    assert 'href="/campaigns/linden-pass/dm-content"' not in body
    assert 'href="/campaigns/linden-pass/characters"' not in body
    assert 'href="/campaigns/linden-pass/control-panel"' not in body
    assert "This viewer cannot currently open this scope." not in body


def test_dm_campaign_help_page_still_shows_dm_only_surfaces(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/help")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "DM Content" in body
    assert "Characters" in body
    assert "Control" in body
    assert "Manage Systems source enablement, entry overrides" in body
    assert "shared/core edit routes are reserved for app admins" in body
    assert "Browser Player Wiki hard delete adds usage checks" in body
    assert 'href="/campaigns/linden-pass/dm-content/systems"' in body
    assert "Session-only articles stay separate from the published wiki until a DM converts them." in body


def test_signed_in_user_can_save_theme_preference(app, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/account/theme",
        data={"theme_key": "moonlit"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Theme updated to Moonlit Ledger." in body
    assert 'data-theme="moonlit"' in body

    campaign = client.get("/campaigns/linden-pass")
    assert campaign.status_code == 200
    assert 'data-theme="moonlit"' in campaign.get_data(as_text=True)

    with app.app_context():
        store = AuthStore()
        preferences = store.get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "moonlit"
        assert preferences.session_chat_order == "newest_first"


def test_signed_in_user_can_save_live_session_chat_order_preference(app, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/account/session-chat-order",
        data={"session_chat_order": "oldest_first"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Live session chat order updated to Oldest first." in body
    assert "Live session chat order" in body

    with app.app_context():
        store = AuthStore()
        preferences = store.get_user_preferences(users["party"]["id"])
        assert preferences.session_chat_order == "oldest_first"
        assert preferences.theme_key == "parchment"


def test_invalid_theme_preference_is_rejected(app, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/account/theme",
        data={"theme_key": "bad-theme"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Choose a valid theme preset." in body
    assert 'data-theme="parchment"' in body

    with app.app_context():
        store = AuthStore()
        preferences = store.get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "parchment"
        assert preferences.session_chat_order == "newest_first"


def test_invalid_live_session_chat_order_preference_is_rejected(app, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/account/session-chat-order",
        data={"session_chat_order": "sideways"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Choose a valid live session chat order." in body
    assert "Live session chat order" in body

    with app.app_context():
        store = AuthStore()
        preferences = store.get_user_preferences(users["party"]["id"])
        assert preferences.session_chat_order == "newest_first"


def test_theme_update_recovers_from_legacy_user_preferences_schema(app, client, sign_in, users):
    with app.app_context():
        connection = get_db()
        connection.executescript(
            """
            ALTER TABLE user_preferences RENAME TO user_preferences_current;

            CREATE TABLE user_preferences (
                user_id INTEGER PRIMARY KEY,
                theme_key TEXT NOT NULL DEFAULT 'parchment',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            INSERT INTO user_preferences (
                user_id,
                theme_key,
                updated_at
            )
            SELECT
                user_id,
                theme_key,
                updated_at
            FROM user_preferences_current;

            DROP TABLE user_preferences_current;
            """
        )
        connection.commit()

    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/account/theme",
        data={"theme_key": "moonlit"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Theme updated to Moonlit Ledger." in body
    assert 'data-theme="moonlit"' in body

    with app.app_context():
        store = AuthStore()
        preferences = store.get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "moonlit"
        assert preferences.session_chat_order == "newest_first"


def test_campaign_search_shows_matching_page_tiles(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass?q=Stormglass")

    assert campaign.status_code == 200
    body = campaign.get_data(as_text=True)
    assert "Search Results" in body
    assert "Stormglass Compass" in body
    assert "Items" in body


def test_repository_loads_page_bodies_on_demand_for_hub_and_page_views(app, client):
    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None

        overview_page = campaign.get_visible_page("index")
        notes_page = campaign.get_visible_page("notes/operations-brief")
        assert overview_page is not None
        assert notes_page is not None
        assert overview_page.content_loaded is False
        assert overview_page.html_loaded is False
        assert notes_page.content_loaded is False
        assert notes_page.html_loaded is False

    campaign_response = client.get("/campaigns/linden-pass")
    assert campaign_response.status_code == 200

    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None

        overview_page = campaign.get_visible_page("index")
        notes_page = campaign.get_visible_page("notes/operations-brief")
        assert overview_page is not None
        assert notes_page is not None
        assert overview_page.content_loaded is True
        assert overview_page.html_loaded is True
        assert notes_page.content_loaded is False
        assert notes_page.html_loaded is False

    page_response = client.get("/campaigns/linden-pass/pages/notes/operations-brief")
    assert page_response.status_code == 200

    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None

        notes_page = campaign.get_visible_page("notes/operations-brief")
        assert notes_page is not None
        assert notes_page.content_loaded is True
        assert notes_page.html_loaded is True
        assert "All crew members are expected to keep a low profile" in notes_page.body_markdown


def test_repository_seeds_campaign_pages_into_db_read_model(app):
    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None

        page_store = app.extensions["campaign_page_store"]
        assert page_store.count_pages("linden-pass") >= len(campaign.pages)

        record = page_store.get_page_record(
            "linden-pass",
            "notes/operations-brief",
            include_body=True,
        )
        assert record is not None
        assert record.page.route_slug == "notes/operations-brief"
        assert "All crew members are expected to keep a low profile" in record.body_markdown


def test_campaign_body_search_uses_db_read_model_without_hydrating_page_body(app, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None
        dock_charter = campaign.get_visible_page("notes/dock-charter")
        assert dock_charter is not None
        assert dock_charter.content_loaded is False

    response = client.get("/campaigns/linden-pass?q=bonded%20carriers")
    assert response.status_code == 200
    assert "Dock Charter" in response.get_data(as_text=True)

    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None
        dock_charter = campaign.get_visible_page("notes/dock-charter")
        assert dock_charter is not None
        assert dock_charter.content_loaded is False


def test_repository_refresh_syncs_manual_file_edits_into_db_read_model(app):
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "manual-sync-check.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        "---\n"
        "title: Manual Sync Check\n"
        "section: Notes\n"
        "type: note\n"
        "published: true\n"
        "---\n\n"
        "Freshly mirrored content from a manual file edit.\n",
        encoding="utf-8",
    )

    with app.app_context():
        repository_store = app.extensions["repository_store"]
        repository = repository_store.refresh()
        campaign = repository.get_campaign("linden-pass")
        assert campaign is not None

        page = campaign.get_visible_page("notes/manual-sync-check")
        assert page is not None

        page_store = app.extensions["campaign_page_store"]
        record = page_store.get_page_record(
            "linden-pass",
            "notes/manual-sync-check",
            include_body=True,
        )
        assert record is not None
        assert "Freshly mirrored content from a manual file edit." in record.body_markdown


def test_outsider_can_access_public_campaign_pages_but_not_member_only_routes(client, sign_in, users):
    sign_in(users["outsider"]["email"], users["outsider"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    page = client.get("/campaigns/linden-pass/pages/index")
    session_page = client.get("/campaigns/linden-pass/session")
    combat_page = client.get("/campaigns/linden-pass/combat")
    roster = client.get("/campaigns/linden-pass/characters")

    assert campaign.status_code == 200
    assert page.status_code == 200
    assert session_page.status_code == 404
    assert combat_page.status_code == 404
    assert roster.status_code == 404


def test_dm_can_open_visibility_control_panel_and_player_cannot(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_panel = client.get("/campaigns/linden-pass/control-panel")
    assert dm_panel.status_code == 200
    dm_html = dm_panel.get_data(as_text=True)
    assert "Visibility settings" in dm_html
    assert "Player Wiki" in dm_html
    assert "Session" in dm_html
    assert "Combat" in dm_html
    assert "DM Content" in dm_html
    assert "Characters" in dm_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    player_panel = client.get("/campaigns/linden-pass/control-panel")
    assert player_panel.status_code == 403


def test_dm_campaign_nav_uses_the_expected_button_order(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    expected_order = [
        'href="/campaigns/linden-pass">',
        'href="/campaigns/linden-pass/session"',
        'href="/campaigns/linden-pass/combat"',
        'href="/campaigns/linden-pass/characters"',
        'href="/campaigns/linden-pass/systems"',
        'href="/campaigns/linden-pass/dm-content"',
        'href="/campaigns/linden-pass/control-panel"',
        'href="/campaigns/linden-pass/help"',
    ]

    positions = [body.index(marker) for marker in expected_order]
    assert positions == sorted(positions)


def test_campaign_level_visibility_floor_can_hide_public_wiki_from_players_and_anonymous_users(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    update = client.post(
        "/campaigns/linden-pass/control-panel/visibility",
        data={
            "campaign_visibility": "dm",
            "wiki_visibility": "public",
            "session_visibility": "players",
            "combat_visibility": "players",
            "dm_content_visibility": "dm",
            "characters_visibility": "dm",
        },
        follow_redirects=True,
    )

    assert update.status_code == 200
    assert "Updated visibility for Campaign." in update.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)

    anonymous_campaign = client.get("/campaigns/linden-pass", follow_redirects=False)
    assert anonymous_campaign.status_code == 302
    assert "/sign-in?next=/campaigns/linden-pass" in anonymous_campaign.headers["Location"]

    sign_in(users["party"]["email"], users["party"]["password"])
    blocked_campaign = client.get("/campaigns/linden-pass")
    blocked_page = client.get("/campaigns/linden-pass/pages/index")

    assert blocked_campaign.status_code == 404
    assert blocked_page.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_campaign = client.get("/campaigns/linden-pass")
    assert dm_campaign.status_code == 200


def test_private_visibility_is_reserved_for_admins(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_update = client.post(
        "/campaigns/linden-pass/control-panel/visibility",
        data={
            "campaign_visibility": "private",
            "wiki_visibility": "public",
            "session_visibility": "players",
            "combat_visibility": "players",
            "dm_content_visibility": "dm",
            "characters_visibility": "dm",
        },
        follow_redirects=False,
    )

    assert dm_update.status_code == 400
    assert "Private visibility is reserved for app admins." in dm_update.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["admin"]["email"], users["admin"]["password"])

    admin_update = client.post(
        "/campaigns/linden-pass/control-panel/visibility",
        data={
            "campaign_visibility": "private",
            "wiki_visibility": "public",
            "session_visibility": "players",
            "combat_visibility": "players",
            "dm_content_visibility": "dm",
            "characters_visibility": "dm",
        },
        follow_redirects=True,
    )

    assert admin_update.status_code == 200
    assert "Updated visibility for Campaign." in admin_update.get_data(as_text=True)


def test_missing_wiki_page_returns_not_found_for_campaign_members(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/pages/does-not-exist")

    assert response.status_code == 404


def test_aliases_are_not_rendered_in_player_facing_wiki_ui(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    section = client.get("/campaigns/linden-pass/sections/locations")
    page = client.get("/campaigns/linden-pass/pages/locations/harbor-row")

    assert campaign.status_code == 200
    assert section.status_code == 200
    assert page.status_code == 200
    assert "Aliases:" not in campaign.get_data(as_text=True)
    assert "Aliases:" not in section.get_data(as_text=True)
    assert "Aliases:" not in page.get_data(as_text=True)


def test_article_image_renders_for_configured_page_and_asset_route_is_public(client, sign_in, users):
    page = client.get("/campaigns/linden-pass/pages/npcs/captain-lyra-vale")
    asset = client.get("/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png")

    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'src="/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png"' in body
    assert 'alt="Portrait of Captain Lyra Vale."' in body
    assert "Captain Lyra Vale keeps the harbor watch disciplined" in body
    assert asset.status_code == 200
    assert asset.mimetype == "image/png"

    client.post("/sign-in", data={"email": users["outsider"]["email"], "password": users["outsider"]["password"]})
    outsider_asset = client.get("/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png")
    assert outsider_asset.status_code == 200


def test_lore_map_page_renders_configured_image_and_asset_is_public(client):
    page = client.get("/campaigns/linden-pass/pages/lore/trade-coast-map")
    asset = client.get("/campaigns/linden-pass/assets/lore/trade-coast-map.png")

    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Trade Coast Map" in body
    assert "This simplified map gives the crew a broad sense of the coast" in body
    assert 'src="/campaigns/linden-pass/assets/lore/trade-coast-map.png"' in body
    assert 'alt="Simplified trade coast map centered on Port Meridian."' in body
    assert "A simplified regional map for route planning." in body
    assert asset.status_code == 200
    assert asset.mimetype == "image/png"


def test_page_context_links_back_to_campaign_and_section(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    page = client.get("/campaigns/linden-pass/pages/locations/harbor-row")

    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Campaign:" in body
    assert f'href="/campaigns/linden-pass">{TEST_CAMPAIGN_TITLE}</a>' in body
    assert "Section:" in body
    assert 'href="/campaigns/linden-pass/sections/locations">Locations</a>' in body
    assert "Type:" not in body
    assert "Back to campaign overview" not in body


def test_notes_section_lists_documents_and_pages_are_accessible(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/notes")
    brief_page = client.get("/campaigns/linden-pass/pages/notes/operations-brief")
    charter_page = client.get("/campaigns/linden-pass/pages/notes/dock-charter")

    assert section.status_code == 200
    assert brief_page.status_code == 200
    assert charter_page.status_code == 200

    section_body = section.get_data(as_text=True)
    brief_body = brief_page.get_data(as_text=True)
    charter_body = charter_page.get_data(as_text=True)

    assert "Operations Brief" in section_body
    assert "Dock Charter" in section_body
    assert "All crew members are expected to keep a low profile" in brief_body
    assert "authorizes bonded carriers" in charter_body


def test_session_pages_link_to_published_note_documents(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    session_one = client.get("/campaigns/linden-pass/pages/sessions/session-1-dockside-delivery")
    session_two = client.get("/campaigns/linden-pass/pages/sessions/session-2-the-brass-vault")

    assert session_one.status_code == 200
    assert session_two.status_code == 200

    session_one_body = session_one.get_data(as_text=True)
    session_two_body = session_two.get_data(as_text=True)

    assert 'href="/campaigns/linden-pass/pages/notes/operations-brief"' in session_one_body
    assert 'href="/campaigns/linden-pass/pages/notes/dock-charter"' in session_two_body


def test_races_section_and_race_pages_are_available(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/races")
    humans_page = client.get("/campaigns/linden-pass/pages/races/humans")
    tidemarked_page = client.get("/campaigns/linden-pass/pages/races/tidemarked")

    assert section.status_code == 200
    assert humans_page.status_code == 200
    assert tidemarked_page.status_code == 200

    section_body = section.get_data(as_text=True)
    humans_body = humans_page.get_data(as_text=True)
    tidemarked_body = tidemarked_page.get_data(as_text=True)

    assert "Humans" in section_body
    assert "Tidemarked" in section_body
    assert "most widespread people in the ports" in humans_body
    assert "shipcraft, storm reading" in tidemarked_body


def test_current_campaign_progress_controls_visible_session_pages(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    visible_page = client.get("/campaigns/linden-pass/pages/sessions/session-2-the-brass-vault")
    hidden_page = client.get("/campaigns/linden-pass/pages/sessions/session-3-stormglass-heist")
    hidden_npc = client.get("/campaigns/linden-pass/pages/npcs/hidden-quartermaster")

    assert visible_page.status_code == 200
    assert hidden_page.status_code == 404
    assert hidden_npc.status_code == 404


def test_sessions_section_uses_campaign_timeline_order(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/sessions")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert body.index("Session 1 - Dockside Delivery") < body.index("Session 2 - The Brass Vault")
    assert "Session 3 - Stormglass Heist" not in body


def test_factions_section_is_grouped_by_subsection(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/factions")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert "Major Powers" in body
    assert "Major Guilds" in body
    assert "Minor Guilds" in body
    assert body.index("Major Powers") < body.index("Major Guilds") < body.index("Minor Guilds")
    assert "Breaker Fleet" in body
    assert "Brass League" in body
    assert "Inkhook Couriers" in body


def test_gods_section_is_grouped_by_subsection_and_excludes_unpublished_page(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/gods")
    auriel_page = client.get("/campaigns/linden-pass/pages/gods/auriel-first-flame")
    merin_page = client.get("/campaigns/linden-pass/pages/gods/merin-keeper-of-ledgers")
    hidden_page = client.get("/campaigns/linden-pass/pages/gods/the-hidden-depths")

    assert section.status_code == 200
    assert auriel_page.status_code == 200
    assert merin_page.status_code == 200
    assert hidden_page.status_code == 404

    body = section.get_data(as_text=True)
    assert "Primeval Gods" in body
    assert "Modern Gods" in body
    assert "Fallen Gods" in body
    assert body.index("Primeval Gods") < body.index("Modern Gods") < body.index("Fallen Gods")
    assert "Auriel - First Flame" in body
    assert "Merin - Keeper of Ledgers" in body
    assert "Saelis - The Unmoored" in body
    assert "The Hidden Depths" not in body
    assert "primeval god" in body
    assert "modern god" in body
    assert "fallen god" in body


def test_locations_section_is_grouped_by_subsection(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/locations")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert "page-card page-card--featured" in body
    assert '/campaigns/linden-pass/pages/locations/port-meridian' in body
    assert '/campaigns/linden-pass/pages/locations/harbor-row' in body
    assert "Districts and City Areas" in body
    assert "Civic and Institutional Sites" in body
    assert "Venues and Residences" in body
    assert "Infrastructure and Underworks" in body
    assert body.index('/campaigns/linden-pass/pages/locations/port-meridian') < body.index('/campaigns/linden-pass/pages/locations/harbor-row')


def test_locations_section_subsections_are_collapsible(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/locations")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert "Back to campaign overview" not in body
    assert "Collapse all" in body
    assert "Expand all" in body
    assert "data-subsection-controls" in body
    assert "data-collapsible-section" in body


def test_mechanics_section_is_grouped_by_subsection(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/mechanics")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert "Class Modifications" in body
    assert "Downtime Rules" in body
    assert "Arcane Overload" in body
    assert "Downtime Projects" in body
    assert "Harbor Duels" in body


def test_downtime_rules_tile_is_pinned_first_within_its_subsection(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/mechanics")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert body.index('/campaigns/linden-pass/pages/mechanics/downtime-projects') < body.index('/campaigns/linden-pass/pages/mechanics/harbor-duels')


def test_pinned_subsection_pages_render_as_featured_cards_with_summaries(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    section = client.get("/campaigns/linden-pass/sections/mechanics")

    assert section.status_code == 200
    body = section.get_data(as_text=True)
    assert "page-card page-card--featured" in body
    assert "shared framework for crafting, research, and long-form project work" in body
