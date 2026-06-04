import base64
import re
import threading

import pytest
import yaml


@pytest.fixture
def frontend_gen2_session_live_server(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _sign_in(page, base_url: str, *, email: str, password: str) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(email)
    page.locator("input[name='password']").fill(password)
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _seed_arden_portrait(app) -> None:
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    campaigns_dir = app.config["TEST_CAMPAIGNS_DIR"]
    portrait_path = campaigns_dir / "linden-pass" / "assets" / "characters" / "arden-march" / "portrait.png"
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait_path.write_bytes(tiny_png)
    definition_path = campaigns_dir / "linden-pass" / "characters" / "arden-march" / "definition.yaml"
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    profile = dict(payload.get("profile") or {})
    profile.update(
        {
            "portrait_asset_ref": "characters/arden-march/portrait.png",
            "portrait_alt": "Arden portrait",
            "portrait_caption": "Shown on the Gen2 sheet.",
        }
    )
    payload["profile"] = profile
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _seed_gen2_combat(app, users) -> None:
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        service.add_player_character(
            "linden-pass",
            character_slug="arden-march",
            turn_value=18,
            created_by_user_id=users["dm"]["id"],
        )
        service.add_npc_combatant(
            "linden-pass",
            display_name="Clockwork Hound",
            turn_value=12,
            current_hp=22,
            max_hp=22,
            temp_hp=0,
            movement_total=40,
            created_by_user_id=users["dm"]["id"],
        )


def test_gen2_session_browser_exposes_flask_session_capabilities(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/campaigns/linden-pass/session")
            expect(page.get_by_role("heading", name="Chat window")).to_be_visible(timeout=5000)

            page.goto(f"{base_url}/campaigns/linden-pass/session/dm")
            expect(page.get_by_role("heading", name="Session controls")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Session article store")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Chat logs")).to_be_visible(timeout=5000)

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            expect(page.get_by_role("link", name="Campaign Player Wiki")).to_be_visible(timeout=10000)
            expect(page.get_by_role("link", name="Account")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("Session")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("Campaign Home")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("Combat")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("Characters")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("Systems")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("DM Content")).to_be_visible()
            expect(page.locator(".campaign-nav-link").get_by_text("Control")).to_be_visible()
            expect(page.get_by_label("Search", exact=True)).to_be_visible()
            assert page.locator("a", has_text="Sign in").count() == 0

            session_heading = page.get_by_role("heading", name=re.compile(r"Session:", re.I)).first
            session_tabs = page.locator(".session-tab-strip")
            expect(session_heading).to_be_visible(timeout=10000)
            expect(session_tabs.get_by_role("button", name="Session", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="Character", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="DM", exact=True)).to_be_visible()

            page.reload()
            expect(page.get_by_role("heading", name=re.compile(r"Session:", re.I)).first).to_be_visible(timeout=10000)
            expect(page.locator(".campaign-nav-link").get_by_text("Session")).to_be_visible()

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="DM controls")).to_be_visible(timeout=5000)
            expect(page.get_by_role("button", name=re.compile(r"Begin session|Starting", re.I))).to_be_visible()
            expect(page.get_by_role("button", name=re.compile(r"Close session|Closing", re.I))).to_be_visible()
            expect(page.get_by_role("heading", name="Staged articles")).to_be_visible()
            expect(page.get_by_role("heading", name="Revealed articles")).to_be_visible()
            expect(page.get_by_role("heading", name="Session logs")).to_be_visible()

            session_tabs.get_by_role("button", name="Session", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(session_heading).to_be_visible()
            expect(page.get_by_role("heading", name="Session chat")).to_be_visible()
            expect(page.get_by_role("heading", name="Player wiki lookup")).to_be_visible()
            expect(page.get_by_label("Post Session Message")).to_be_visible()

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="Session Character")).to_be_visible(timeout=10000)
            expect(page.get_by_label("Character", exact=True)).to_be_visible()
        finally:
            page.close()
            browser.close()


def test_gen2_combat_browser_opens_player_workspace_and_preserves_focused_draft(
    app,
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    _seed_gen2_combat(app, users)
    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["owner"]["email"], password=users["owner"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat")
            expect(page.get_by_role("heading", name=re.compile(r"Combat:", re.I))).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Turn Order")).to_be_visible()
            carousel = page.locator(".combat-carousel")
            expect(carousel.get_by_role("button", name=re.compile(r"Arden March", re.I))).to_be_visible()
            expect(carousel.get_by_role("button", name=re.compile(r"Clockwork Hound", re.I))).to_be_visible()
            expect(page.get_by_role("heading", name="Combat Character")).to_be_visible(timeout=10000)

            carousel.get_by_role("button", name=re.compile(r"Clockwork Hound", re.I)).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/combat\?combatant=\d+"))
            expect(page.get_by_role("heading", name="Clockwork Hound")).to_be_visible()
            expect(page.get_by_role("heading", name="Combat Character")).to_be_visible()

            workspace = page.locator(".combat-pc-workspace")
            current_hp = workspace.get_by_label("Current HP", exact=True).first
            expect(current_hp).to_be_visible(timeout=10000)
            current_hp.fill("33")
            expect(current_hp).to_have_value("33")
            page.wait_for_timeout(1300)
            expect(current_hp).to_have_value("33")
            assert current_hp.evaluate("el => document.activeElement === el")
        finally:
            page.close()
            browser.close()


def test_gen2_wiki_browser_exposes_home_section_page_and_assets(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["party"]["email"], password=users["party"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass")
            expect(page.get_by_role("heading", name="Campaign Home")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Echoes of the Alloy Coast")).to_be_visible(timeout=10000)
            expect(page.get_by_text("Welcome to the shared player briefing")).to_be_visible()
            expect(page.get_by_role("heading", name="Browse By Section")).to_be_visible()
            expect(page.get_by_role("link", name="Locations").first).to_be_visible()

            page.get_by_label("Search", exact=True).fill("capt")
            page.get_by_role("button", name="Search").click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass\?q=capt$"), timeout=5000)
            expect(page.get_by_role("heading", name="Search Results")).to_be_visible(timeout=10000)
            expect(page.get_by_role("link", name="Captain Lyra Vale").first).to_be_visible()

            page.get_by_role("link", name="Captain Lyra Vale").first.click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale$"), timeout=5000)
            expect(page.get_by_role("heading", name="Captain Lyra Vale")).to_be_visible(timeout=10000)
            expect(page.get_by_text("Captain Lyra Vale coordinates inspections")).to_be_visible()
            image = page.locator("article img.article-image")
            expect(image).to_be_visible()
            image_src = image.get_attribute("src")
            assert image_src is not None
            assert image_src.endswith("/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png")
            asset_response = page.request.get(f"{base_url}/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png")
            assert asset_response.status == 200
            assert asset_response.headers.get("content-type", "").startswith("image/")

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/sections/locations")
            expect(page.get_by_role("heading", name="Locations")).to_be_visible(timeout=10000)
            civic_details = page.locator("details", has_text="Civic and Institutional Sites")
            expect(civic_details).to_be_visible()
            assert civic_details.evaluate("(element) => element.open") is True
            page.get_by_role("button", name="Collapse all").click()
            assert civic_details.evaluate("(element) => element.open") is False
            page.get_by_role("button", name="Expand all").click()
            assert civic_details.evaluate("(element) => element.open") is True
            expect(page.get_by_role("link", name="Tidewatch Hall")).to_be_visible()
        finally:
            page.close()
            browser.close()


def test_gen2_character_browser_exposes_roster_detail_portrait_and_conflict(
    frontend_gen2_session_live_server,
    app,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    _seed_arden_portrait(app)
    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters")
            expect(page.get_by_role("heading", name="Characters")).to_be_visible(timeout=10000)
            expect(page.get_by_role("link", name="Flask roster")).to_be_visible()
            expect(page.get_by_role("link", name="Create character")).to_be_visible()

            roster_search = page.locator("form.character-roster-search")
            roster_search.get_by_label("Search characters").fill("arden")
            roster_search.get_by_role("button", name="Search").click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/characters\?q=arden$"), timeout=5000)
            expect(page.get_by_role("link", name="Arden March").first).to_be_visible(timeout=10000)
            portrait = page.locator(".character-card__portrait")
            expect(portrait).to_be_visible()
            portrait_src = portrait.get_attribute("src")
            assert portrait_src is not None
            portrait_response = page.request.get(
                portrait_src if portrait_src.startswith("http") else f"{base_url}{portrait_src}"
            )
            assert portrait_response.status == 200
            assert portrait_response.headers.get("content-type", "").startswith("image/")

            page.get_by_role("link", name="Open sheet").click()
            expect(page).to_have_url(
                re.compile(r"/app-next/campaigns/linden-pass/characters/arden-march$"),
                timeout=5000,
            )
            expect(page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)
            expect(page.get_by_text("Shown on the Gen2 sheet.")).to_be_visible()
            expect(page.get_by_role("link", name="Flask sheet")).to_be_visible()
            expect(page.get_by_role("link", name="Advanced Editor")).to_be_visible()
            expect(page.get_by_text("Create, import, portrait upload, controls, and broader authoring stay in Flask")).to_be_visible()

            page.reload()
            expect(page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Arden March (arden-march)")).to_be_visible()

            detail_response = page.request.get(f"{base_url}/api/v1/campaigns/linden-pass/characters/arden-march")
            assert detail_response.status == 200
            detail_payload = detail_response.json()
            revision = detail_payload["character"]["state_record"]["revision"]
            external_update_response = page.request.patch(
                f"{base_url}/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
                data={
                    "expected_revision": revision,
                    "player_notes_markdown": "External Gen2 conflict update.",
                },
            )
            assert external_update_response.status == 200

            page.locator(".section-tabs").get_by_role("button", name="Notes").click()
            page.get_by_label("Player notes").fill("This stale browser draft should conflict.")
            page.get_by_role("button", name="Save notes").click()
            expect(page.get_by_text(re.compile(r"changed in another session|Refresh and try again", re.I))).to_be_visible(
                timeout=5000
            )
        finally:
            page.close()
            browser.close()


def test_gen2_session_preserves_local_state_across_live_polling(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 620})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            start_response = page.request.post(f"{base_url}/campaigns/linden-pass/session/start")
            assert start_response.status in {200, 302}
            article_response = page.request.post(
                f"{base_url}/campaigns/linden-pass/session/articles",
                form={
                    "title": "Gen2 Preservation Article",
                    "body_markdown": "This staged article should keep local draft state.",
                },
            )
            assert article_response.status in {200, 302}

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            session_tabs = page.locator(".session-tab-strip")
            expect(session_tabs.get_by_role("button", name="Session", exact=True)).to_be_visible(timeout=10000)

            chat_draft = "This chat draft should survive pane switches and live polling."
            page.locator(".pane-visible").get_by_label("Post Session Message").fill(chat_draft)

            wiki_lookup = page.locator(".pane-visible")
            wiki_lookup.get_by_label("Search published pages / systems").fill("harbor")
            wiki_lookup.get_by_role("button", name="Search").click()
            harbor_result = wiki_lookup.get_by_role("button", name=re.compile(r"Harbor Duels", re.I))
            expect(harbor_result).to_be_visible(timeout=5000)
            harbor_result.click()
            expect(wiki_lookup.get_by_text("Formal harbor duels")).to_be_visible(timeout=5000)

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            character_pane = page.locator(".pane-visible")
            character_select = character_pane.get_by_label("Character", exact=True)
            expect(character_select).to_be_visible(timeout=10000)
            option_count = character_select.locator("option").count()
            assert option_count >= 2
            selected_character = character_select.locator("option").nth(1).get_attribute("value")
            assert selected_character
            character_select.select_option(selected_character)
            expect(character_select).to_have_value(selected_character)

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            dm_pane = page.locator(".pane-visible")
            article_card = dm_pane.locator("details.article-card", has_text="Gen2 Preservation Article")
            expect(article_card).to_be_visible(timeout=5000)
            article_card.locator("summary").click()
            assert article_card.evaluate("(element) => element.open") is True

            title_input = article_card.get_by_label("Title", exact=True)
            body_input = article_card.get_by_label("Body (markdown or html)")
            title_input.fill("Unsaved Gen2 Preservation Title")
            body_input.fill("Unsaved body should remain in the staged article editor.")
            title_input.focus()
            focused_id = title_input.get_attribute("id")
            assert focused_id

            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            scroll_before = page.evaluate("window.scrollY")
            assert scroll_before > 0

            page.wait_for_timeout(3600)

            assert article_card.evaluate("(element) => element.open") is True
            expect(title_input).to_have_value("Unsaved Gen2 Preservation Title")
            expect(body_input).to_have_value("Unsaved body should remain in the staged article editor.")
            assert page.evaluate("document.activeElement && document.activeElement.id") == focused_id
            scroll_after = page.evaluate("window.scrollY")
            assert abs(scroll_after - scroll_before) <= 5

            session_tabs.get_by_role("button", name="Session", exact=True).click()
            session_pane = page.locator(".pane-visible")
            expect(session_pane.get_by_label("Post Session Message")).to_have_value(chat_draft)
            expect(session_pane.get_by_text("Formal harbor duels")).to_be_visible()

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            expect(page.locator(".pane-visible").get_by_label("Character", exact=True)).to_have_value(selected_character)

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            article_card = page.locator(".pane-visible").locator("details.article-card", has_text="Gen2 Preservation Article")
            assert article_card.evaluate("(element) => element.open") is True
            expect(article_card.get_by_label("Title", exact=True)).to_have_value("Unsaved Gen2 Preservation Title")
            expect(article_card.get_by_label("Body (markdown or html)")).to_have_value(
                "Unsaved body should remain in the staged article editor.",
            )
        finally:
            page.close()
            browser.close()


def test_gen2_dm_content_browser_statblock_workflow(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    statblock_title = "Gen2 Harbor Guard"
    statblock_updated_title = "Gen2 Harbor Sergeant"
    statblock_markdown = (
        f"# {statblock_title}\n\n"
        "Armor Class 14\n"
        "Hit Points 28\n"
        "Speed 30 ft.\n\n"
        "DEX 14 (+2)\n\n"
        "### Actions\n"
        "Harbor Hook. Melee Weapon Attack."
    )
    statblock_updated_markdown = (
        f"# {statblock_updated_title}\n\n"
        "Armor Class 16\n"
        "Hit Points 44\n"
        "Speed 35 ft.\n\n"
        "DEX 16 (+3)\n\n"
        "### Actions\n"
        "Commanding Hook. Melee Weapon Attack."
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/dm-content")
            expect(page.get_by_role("heading", name="DM Content: Statblocks")).to_be_visible(timeout=10000)
            fallback_links = page.locator(".dm-content-gen2-links")
            expect(fallback_links.get_by_role("link", name="Statblocks")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Staged Articles")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Conditions")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Player Wiki", exact=True)).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Systems")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Session DM")).to_be_visible()

            create_panel = page.locator("section.dm-statblock-create")
            expect(create_panel.get_by_role("heading", name="Create statblock")).to_be_visible()
            page.locator("#dm-statblock-create-filename").fill("gen2-harbor-guard.md")
            page.locator("#dm-statblock-create-subsection").fill("Gen2 Harbor Crew")
            page.locator("#dm-statblock-create-markdown").fill(statblock_markdown)
            create_panel.get_by_role("button", name="Save statblock").click()
            expect(page.get_by_text("Statblock saved: Gen2 Harbor Guard.")).to_be_visible(timeout=10000)

            library = page.locator("section.dm-statblock-library")
            group = library.locator("details.section-block", has_text="Gen2 Harbor Crew")
            expect(group).to_be_visible(timeout=10000)
            statblock_card = library.locator("details.dm-statblock-card", has_text=statblock_title)
            expect(statblock_card).to_be_visible(timeout=10000)
            statblock_card.locator("summary.dm-statblock-summary").click()
            expect(statblock_card.locator(".meta-badge", has_text="AC 14")).to_be_visible()
            expect(statblock_card.locator(".meta-badge", has_text="HP 28")).to_be_visible()
            expect(statblock_card.locator(".meta-badge", has_text="Init +2")).to_be_visible()
            expect(statblock_card.get_by_text(re.compile(r"Combat seed source: dm_statblock:\d+"))).to_be_visible()
            expect(statblock_card.get_by_text("Parsed combat fields: AC 14")).to_be_visible()

            library.get_by_label("Search statblocks").fill("not-here")
            expect(library.get_by_text("No statblocks matched that search.")).to_be_visible()
            library.get_by_label("Search statblocks").fill("")
            expect(statblock_card).to_be_visible()
            if not statblock_card.evaluate("element => element.open"):
                statblock_card.locator("summary.dm-statblock-summary").click()

            statblock_card.locator("input[name='subsection']").fill("Gen2 Officers")
            statblock_card.locator("textarea[name='markdown_text']").fill(statblock_updated_markdown)
            statblock_card.get_by_role("button", name="Save statblock").click()
            expect(page.get_by_text("Statblock updated: Gen2 Harbor Sergeant.")).to_be_visible(timeout=10000)

            updated_group = library.locator("details.section-block", has_text="Gen2 Officers")
            expect(updated_group).to_be_visible(timeout=10000)
            updated_card = library.locator("details.dm-statblock-card", has_text=statblock_updated_title)
            expect(updated_card).to_be_visible(timeout=10000)
            if not updated_card.evaluate("element => element.open"):
                updated_card.locator("summary.dm-statblock-summary").click()
            expect(updated_card.locator(".meta-badge", has_text="HP 44")).to_be_visible()
            expect(updated_card.locator(".meta-badge", has_text="Init +3")).to_be_visible()

            library.get_by_label("Search statblocks").fill("Gen2 Officers")
            expect(updated_card).to_be_visible()
            updated_card.get_by_role("button", name="Delete statblock").click()
            expect(page.get_by_text("Statblock deleted: Gen2 Harbor Sergeant.")).to_be_visible(timeout=10000)
            expect(library.locator("details.dm-statblock-card", has_text=statblock_updated_title)).to_have_count(0, timeout=10000)
        finally:
            page.close()
            browser.close()


def test_gen2_dm_content_browser_condition_workflow(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    condition_name = "Gen2 Dazed"
    updated_condition_name = "Gen2 Staggered"
    condition_description = "The target cannot take reactions until the start of its next turn."
    updated_condition_description = "The target has disadvantage on Dexterity checks until the condition ends."

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/dm-content?lane=conditions")
            expect(page.get_by_role("heading", name="DM Content: Conditions")).to_be_visible(timeout=10000)
            fallback_links = page.locator(".dm-content-gen2-links")
            expect(fallback_links.get_by_role("link", name="Statblocks")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Staged Articles")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Conditions")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Player Wiki", exact=True)).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Systems")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Session DM")).to_be_visible()

            create_panel = page.locator("section.dm-condition-create")
            expect(create_panel.get_by_role("heading", name="Create condition")).to_be_visible()
            page.locator("#dm-condition-create-name").fill(condition_name)
            page.locator("#dm-condition-create-description").fill(condition_description)
            create_panel.get_by_role("button", name="Save condition").click()
            expect(page.get_by_text(f"Condition saved: {condition_name}.")).to_be_visible(timeout=10000)

            library = page.locator("section.dm-condition-library")
            expect(library.get_by_text("Custom conditions merge into the Combat condition picker")).to_be_visible()
            condition_card = library.locator("details.dm-condition-card", has_text=condition_name)
            expect(condition_card).to_be_visible(timeout=10000)
            condition_card.locator("summary").click()
            expect(condition_card.locator("pre.dm-content-preview", has_text=condition_description)).to_be_visible()

            library.get_by_label("Search conditions").fill("not-here")
            expect(library.get_by_text("No conditions matched that search.")).to_be_visible()
            library.get_by_label("Search conditions").fill("")
            condition_card = library.locator("details.dm-condition-card", has_text=condition_name)
            expect(condition_card).to_be_visible()
            if not condition_card.evaluate("element => element.open"):
                condition_card.locator("summary").click()

            condition_card.locator("input[name='name']").fill(updated_condition_name)
            condition_card.locator("textarea[name='description_markdown']").fill(updated_condition_description)
            condition_card.get_by_role("button", name="Save condition").click()
            expect(page.get_by_text(f"Condition updated: {updated_condition_name}.")).to_be_visible(timeout=10000)

            updated_card = library.locator("details.dm-condition-card", has_text=updated_condition_name)
            expect(updated_card).to_be_visible(timeout=10000)
            if not updated_card.evaluate("element => element.open"):
                updated_card.locator("summary").click()
            expect(updated_card.locator("pre.dm-content-preview", has_text=updated_condition_description)).to_be_visible()

            library.get_by_label("Search conditions").fill("Gen2 Staggered")
            expect(updated_card).to_be_visible()
            updated_card.get_by_role("button", name="Delete condition").click()
            expect(page.get_by_text(f"Condition deleted: {updated_condition_name}.")).to_be_visible(timeout=10000)
            expect(library.locator("details.dm-condition-card", has_text=updated_condition_name)).to_have_count(0, timeout=10000)
        finally:
            page.close()
            browser.close()


def test_gen2_dm_content_browser_player_wiki_workflow(
    frontend_gen2_session_live_server,
    tmp_path,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    page_title = "Gen2 Field Note"
    updated_title = "Gen2 Field Note Revised"
    body_markdown = "The Gen2 Player Wiki lane can create durable page files."
    updated_body_markdown = "The Gen2 Player Wiki lane can edit and archive durable page files."
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    image_path = tmp_path / "gen2-player-wiki.png"
    image_path.write_bytes(tiny_png)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/dm-content?lane=player-wiki")
            expect(page.get_by_role("heading", name="DM Content: Player Wiki")).to_be_visible(timeout=10000)
            fallback_links = page.locator(".dm-content-gen2-links")
            expect(fallback_links.get_by_role("link", name="Statblocks")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Staged Articles")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Conditions")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Player Wiki", exact=True)).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Systems")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Session DM")).to_be_visible()

            create_panel = page.locator("section.dm-player-wiki-create")
            expect(create_panel.get_by_role("heading", name="Create player wiki page")).to_be_visible()
            page.locator("#dm-player-wiki-create-title").fill(page_title)
            page.locator("#dm-player-wiki-create-slug").fill("gen2-field-note")
            page.locator("#dm-player-wiki-create-summary").fill("Created through the Gen2 Player Wiki lane.")
            page.locator("#dm-player-wiki-create-aliases").fill("Gen2 Note\nField Lane")
            page.locator("#dm-player-wiki-create-source-ref").fill("gen2-browser-test")
            page.locator("#dm-player-wiki-create-image-upload").set_input_files(str(image_path))
            expect(create_panel.get_by_text("Selected image: gen2-player-wiki.png")).to_be_visible()
            page.locator("#dm-player-wiki-create-image-alt").fill("A one pixel Gen2 upload test image")
            page.locator("#dm-player-wiki-create-image-caption").fill("Uploaded through Gen2.")
            page.locator("#dm-player-wiki-create-body").fill(body_markdown)
            create_panel.get_by_role("button", name="Create wiki page").click()
            expect(page.get_by_text(f"Player Wiki page created: {page_title}.")).to_be_visible(timeout=10000)

            library = page.locator("section.dm-player-wiki-library")
            library.get_by_label("Search pages").fill("Gen2 Field")
            page_card = library.locator("details.dm-player-wiki-card", has_text=page_title)
            expect(page_card).to_be_visible(timeout=10000)
            page_card.locator("summary").click()
            expect(page_card.locator(".meta-badge", has_text="Image")).to_be_visible()
            expect(page_card.locator(".meta-badge", has_text="Hard delete available")).to_be_visible()

            expect(page_card.get_by_role("link", name="Open")).to_be_visible(timeout=10000)
            expect(page_card.get_by_role("link", name="Flask editor")).to_be_visible()
            expect(page_card.locator("#dm-player-wiki-edit-notes-gen2-field-note-title")).to_be_visible(timeout=10000)
            page_card.locator("#dm-player-wiki-edit-notes-gen2-field-note-title").fill(updated_title)
            page_card.locator("#dm-player-wiki-edit-notes-gen2-field-note-summary").fill("Edited through the Gen2 Player Wiki lane.")
            page_card.locator("#dm-player-wiki-edit-notes-gen2-field-note-body").fill(updated_body_markdown)
            page_card.get_by_role("button", name="Save wiki page").click()
            expect(page.get_by_text(f"Player Wiki page updated: {updated_title}.")).to_be_visible(timeout=10000)

            updated_card = library.locator("details.dm-player-wiki-card", has_text=updated_title)
            expect(updated_card).to_be_visible(timeout=10000)
            if not updated_card.evaluate("element => element.open"):
                updated_card.locator("summary").click()
            updated_card.get_by_role("button", name="Unpublish/archive").click()
            expect(page.get_by_text(f"Player Wiki page archived: {updated_title}.")).to_be_visible(timeout=10000)
            archived_card = library.locator("details.dm-player-wiki-card", has_text=updated_title)
            expect(archived_card.locator(".meta-badge", has_text="Unpublished")).to_be_visible(timeout=10000)
            if not archived_card.evaluate("element => element.open"):
                archived_card.locator("summary").click()
            archived_card.locator(".dm-content-delete-form input[type='checkbox']").check()
            archived_card.get_by_role("button", name="Delete file").click()
            expect(page.get_by_text("Player Wiki page deleted: notes/gen2-field-note.")).to_be_visible(timeout=10000)
            expect(library.locator("details.dm-player-wiki-card", has_text=updated_title)).to_have_count(0, timeout=10000)
        finally:
            page.close()
            browser.close()


def test_gen2_dm_content_browser_staged_article_workflow(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    article_title = "Gen2 DM Content Draft"
    article_body = "This article is prepared in the DM Content staged workflow."
    article_updated_body = "Rewritten prep copy for staged delivery."

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/dm-content?lane=staged-articles")
            expect(page.get_by_role("heading", name="DM Content: Staged Articles")).to_be_visible(timeout=10000)
            fallback_links = page.locator(".dm-content-gen2-links")
            expect(fallback_links.get_by_role("link", name="Statblocks")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Staged Articles")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Conditions")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Player Wiki", exact=True)).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Systems")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Session DM")).to_be_visible()

            expect(page.get_by_role("button", name="Manual")).to_be_visible()
            expect(page.get_by_role("button", name="Upload")).to_be_visible()
            expect(page.get_by_role("button", name="Wiki / Systems")).to_be_visible()

            creation_panel = page.locator("article", has_text="Stage an article").first
            creation_panel.get_by_label("Title").fill(article_title)
            creation_panel.get_by_label("Markdown body").fill(article_body)
            creation_panel.get_by_role("button", name="Create").click()
            expect(page.get_by_text("Article staged.")).to_be_visible(timeout=10000)

            staged_panel = page.locator("section.panel.panel-nested", has=page.locator("h3", has_text="Staged articles"))
            staged_card = staged_panel.locator("details.article-card", has_text=article_title)
            expect(staged_card).to_be_visible(timeout=10000)
            staged_card.locator("summary").click()
            staged_card.get_by_label("Body").fill(article_updated_body)
            staged_card.get_by_role("button", name="Save draft").click()
            expect(page.get_by_text("Article updated.")).to_be_visible(timeout=10000)

            page.get_by_role("button", name="Upload").click()
            expect(creation_panel.get_by_label("Source filename", exact=True)).to_be_visible()
            expect(creation_panel.get_by_label("Markdown text", exact=True)).to_be_visible()

            page.get_by_role("button", name="Wiki / Systems").click()
            expect(creation_panel.get_by_label("Search wiki / systems")).to_be_visible()
            creation_panel.get_by_label("Search wiki / systems").fill("capt")
            creation_panel.get_by_role("button", name="Search").click()
            captain = creation_panel.get_by_role("button", name=re.compile(r"Captain Lyra Vale", re.I)).first
            expect(captain).to_be_visible(timeout=5000)
            captain.click()
            expect(creation_panel.get_by_text(re.compile(r"Source selected:", re.I))).to_be_visible()
            creation_panel.get_by_role("button", name="Pull source").click()
            expect(page.get_by_text("Article staged.")).to_be_visible(timeout=10000)

            assert staged_panel.locator("details.article-card").count() >= 2

            deleted_count = 0
            for target_title in [article_title, "Captain Lyra Vale"]:
                target_card = staged_panel.locator("details.article-card", has_text=target_title)
                if not target_card.count():
                    continue
                if not target_card.first.evaluate("element => element.open"):
                    target_card.first.locator("summary").click()
                target_card.first.get_by_role("button", name="Delete").click()
                expect(staged_panel.locator("details.article-card", has_text=target_title)).to_have_count(0, timeout=10000)
                deleted_count += 1

            assert deleted_count == 2
        finally:
            page.close()
            browser.close()
