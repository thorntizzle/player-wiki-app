import base64
import json
import re
import threading

import pytest
import yaml

from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID


pytestmark = pytest.mark.skip(reason="Gen2 frontend routes are suspended and closed.")


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


def _configure_xianxia_campaign(app) -> None:
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            "enabled": True,
            "default_visibility": "dm",
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()


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
            assert page.locator(".campaign-search-form").count() == 0
            expect(page.locator(".session-page-hero").get_by_role("heading", name="Session")).to_be_visible()
            expect(page.locator(".session-page-hero").get_by_text("Session workspace")).to_be_visible()
            expect(page.locator(".session-page-hero").get_by_text("Live play workspace.")).to_be_visible()
            expect(page.locator(".session-page-tab-row")).to_be_visible()
            assert page.locator("a", has_text="Sign in").count() == 0
            assert page.locator("text=Back to list").count() == 0
            assert page.locator("text=/Session:/").count() == 0

            session_tabs = page.locator(".session-tab-strip")
            expect(session_tabs.get_by_role("button", name="Session", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="Character", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="DM", exact=True)).to_be_visible()

            page.reload()
            expect(page.locator(".session-page-hero").get_by_role("heading", name="Session")).to_be_visible(timeout=10000)
            expect(page.locator(".campaign-nav-link").get_by_text("Session")).to_be_visible()

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="Session controls")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Session article store")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Live session")).to_be_visible(timeout=5000)
            dm_card_texts = page.evaluate(
                """() => {
                    const section = document.querySelector(".pane-visible .session-workspace-main");
                    return Array.from(section ? section.querySelectorAll(":scope > .panel-nested .panel-header h3") : []).map(
                        (node) => (node.textContent || "").trim(),
                    );
                }"""
            )
            assert dm_card_texts.index("Live session") != -1
            assert dm_card_texts.index("Passive scores") != -1
            assert dm_card_texts.index("Staged articles") != -1
            assert dm_card_texts.index("Session logs") != -1
            assert dm_card_texts.index("Live session") < dm_card_texts.index("Passive scores")
            assert dm_card_texts.index("Passive scores") < dm_card_texts.index("Staged articles")
            assert dm_card_texts.index("Staged articles") < dm_card_texts.index("Session logs")
            expect(page.get_by_role("button", name=re.compile(r"Begin session|Starting", re.I))).to_be_visible()
            expect(page.get_by_role("button", name=re.compile(r"Close session|Closing", re.I))).to_be_visible()
            expect(page.get_by_role("heading", name="Staged articles")).to_be_visible()
            expect(page.get_by_role("heading", name="Session logs")).to_be_visible()

            session_tabs.get_by_role("button", name="Session", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.locator(".session-page-hero").get_by_role("heading", name="Session")).to_be_visible()
            expect(page.get_by_role("heading", name="Session chat")).to_be_visible()
            expect(page.locator(".session-workspace-sidebar").get_by_role("heading", name="Player wiki lookup")).to_be_visible()
            expect(page.get_by_label("Post Session Message")).to_be_visible()
            player_card_texts = page.evaluate(
                """() => {
                    const section = document.querySelector(".pane-visible .session-workspace-main");
                    return Array.from(section ? section.querySelectorAll(":scope > .panel-nested > .panel-header h3") : []).map((node) => (node.textContent || "").trim());
                }"""
            )
            assert player_card_texts[:2] == ["Live session", "Session chat"]
            assert "Revealed articles" not in player_card_texts[:2]

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="Session Character")).to_be_visible(timeout=10000)
            expect(page.get_by_label("Character", exact=True)).to_be_visible()
        finally:
            page.close()
            browser.close()


def test_gen2_shell_and_session_visual_parity_smoke(
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
            desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_page = desktop_context.new_page()
        mobile_page = mobile_context.new_page()

        try:
            _sign_in(desktop_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            expect(desktop_page.locator(".topbar-campaign")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".topbar-campaign")).to_contain_text(re.compile(r"\S"))
            expect(desktop_page.locator(".api-token-details")).to_be_visible()
            expect(desktop_page.locator(".api-token-details summary")).to_be_visible()
            expect(desktop_page.locator(".api-token-details summary")).to_have_text("API token")
            expect(desktop_page.locator("#pilot-api-token")).not_to_be_visible()
            assert desktop_page.locator("text=/Gen2 companion/i").count() == 0
            expect(desktop_page.locator(".campaign-nav-link.is-active", has_text="Session")).to_be_visible()
            assert desktop_page.locator(".campaign-nav-link.is-active").count() == 1
            expect(desktop_page.locator(".campaign-nav-link", has_text="Characters")).to_have_attribute(
                "href",
                re.compile(r"/app-next/campaigns/linden-pass/characters$"),
            )
            expect(desktop_page.locator(".session-tab-strip .tab-button.active", has_text="Session")).to_be_visible()

            desktop_metrics = desktop_page.evaluate(
                """() => {
                    const bodyStyle = window.getComputedStyle(document.body);
                    const nav = document.querySelector(".campaign-nav-link");
                    const hero = document.querySelector(".session-page-hero");
                    const firstPanel = document.querySelector(".session-workspace-main .panel-nested");
                    const topbar = document.querySelector(".topbar");
                    return {
                        fontFamily: bodyStyle.fontFamily,
                        bodyColor: bodyStyle.color,
                        navRadius: nav ? Number.parseFloat(window.getComputedStyle(nav).borderRadius) : 0,
                        heroTop: hero ? hero.getBoundingClientRect().top : 0,
                        firstPanelTop: firstPanel ? firstPanel.getBoundingClientRect().top : 0,
                        topbarBottom: topbar ? topbar.getBoundingClientRect().bottom : 0,
                    };
                }"""
            )
            assert "Georgia" in desktop_metrics["fontFamily"]
            assert desktop_metrics["navRadius"] >= 20
            assert desktop_metrics["heroTop"] <= 280
            assert desktop_metrics["heroTop"] >= desktop_metrics["topbarBottom"]
            assert desktop_metrics["firstPanelTop"] <= 520
            assert desktop_metrics["firstPanelTop"] >= desktop_metrics["heroTop"]
            assert desktop_metrics["bodyColor"] != "rgb(18, 25, 38)"

            _sign_in(mobile_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            mobile_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            expect(mobile_page.locator(".topbar-campaign")).to_be_visible(timeout=10000)
            expect(mobile_page.locator(".session-tab-strip")).to_be_visible()
            mobile_metrics = mobile_page.evaluate(
                """() => ({
                    innerWidth: window.innerWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    tabWidth: document.querySelector(".session-tab-strip")?.getBoundingClientRect().width ?? 0,
                    shellWidth: document.querySelector(".session-shell")?.getBoundingClientRect().width ?? 0,
                    heroTop: document.querySelector(".session-page-hero")?.getBoundingClientRect().top ?? 0,
                    firstPanelTop: document.querySelector(".session-workspace-main .panel-nested")?.getBoundingClientRect().top ?? 0,
                    topbarBottom: document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0,
                })"""
            )
            assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["tabWidth"] <= mobile_metrics["innerWidth"]
            assert mobile_metrics["shellWidth"] <= mobile_metrics["innerWidth"]
            assert mobile_metrics["heroTop"] <= 320
            assert mobile_metrics["firstPanelTop"] <= mobile_metrics["heroTop"] + 360
            assert mobile_metrics["firstPanelTop"] >= mobile_metrics["topbarBottom"] + 50
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
            browser.close()


def test_gen2_campaign_help_uses_gen2_nav_and_campaign_guidance(
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
            player_context = browser.new_context(viewport={"width": 1280, "height": 900})
            player_mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
            dm_context = browser.new_context(viewport={"width": 1280, "height": 900})
            player_page = player_context.new_page()
            player_mobile_page = player_mobile_context.new_page()
            dm_page = dm_context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(player_page, base_url, email=users["party"]["email"], password=users["party"]["password"])

            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            help_link = player_page.locator(".campaign-nav-link", has_text="Help")
            expect(help_link).to_be_visible(timeout=10000)
            expect(help_link).to_have_attribute("href", re.compile(r"/app-next/campaigns/linden-pass/help$"))
            help_link.click()
            expect(player_page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/help$"))
            expect(player_page.get_by_role("heading", name="Help")).to_be_visible(timeout=10000)
            expect(player_page.get_by_role("heading", name="Current access")).to_be_visible()
            expect(player_page.locator("#campaign-home").get_by_role("heading", name="Campaign Home")).to_be_visible()
            expect(player_page.locator("#systems").get_by_role("heading", name="Systems")).to_be_visible()
            expect(player_page.locator("#session").get_by_role("heading", name="Session")).to_be_visible()
            expect(player_page.locator("#combat").get_by_role("heading", name="Combat")).to_be_visible()
            expect(player_page.get_by_role("heading", name="Cross-cutting limits")).to_be_visible()
            expect(player_page.get_by_role("heading", name="Visibility by scope")).to_be_visible()
            expect(player_page.get_by_role("link", name="Flask Help")).to_be_visible()
            assert player_page.locator("#dm-content").count() == 0
            assert player_page.locator("#control").count() == 0
            player_hero = player_page.locator(".campaign-help-hero")
            expect(player_hero.get_by_role("heading", name="Help")).to_be_visible()
            expect(player_hero.get_by_role("link", name="Systems")).to_be_visible()
            hero_metrics = player_page.evaluate(
                """() => {
                    const countGridTracks = (value) => {
                        let depth = 0;
                        let count = 0;
                        let inToken = false;
                        for (const char of value) {
                            if (char === "(") {
                                depth += 1;
                            } else if (char === ")") {
                                depth -= 1;
                            } else if (char === " " && depth === 0) {
                                if (inToken) {
                                    count += 1;
                                    inToken = false;
                                }
                                continue;
                            }
                            if (char === " " && depth > 0 && inToken) {
                                continue;
                            }
                            if (char !== " " || depth > 0) {
                                inToken = true;
                            }
                        }
                        if (inToken) {
                            count += 1;
                        }
                        return count;
                    };
                    const hero = document.querySelector(".campaign-help-hero");
                    const layout = document.querySelector(".campaign-help-layout");
                    const main = document.querySelector(".campaign-help-main");
                    const sidebar = document.querySelector(".campaign-help-sidebar");
                    const layoutColumns = layout ? window.getComputedStyle(layout).gridTemplateColumns : "";
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        heroRadius: hero ? Number.parseFloat(window.getComputedStyle(hero).borderRadius) : 0,
                        heroShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        layoutColumns,
                        layoutColumnsCount: countGridTracks(layoutColumns),
                        mainTop: main ? main.getBoundingClientRect().top : 0,
                        mainLeft: main ? main.getBoundingClientRect().left : 0,
                        sidebarLeft: sidebar ? sidebar.getBoundingClientRect().left : 0,
                        mainWidth: main ? main.getBoundingClientRect().width : 0,
                        sidebarWidth: sidebar ? sidebar.getBoundingClientRect().width : 0,
                    };
                }"""
            )
            assert hero_metrics["heroRadius"] == 0
            assert hero_metrics["heroShadow"] == "none"
            assert hero_metrics["scrollWidth"] <= hero_metrics["innerWidth"] + 1
            assert hero_metrics["layoutColumnsCount"] >= 2
            assert hero_metrics["sidebarLeft"] > hero_metrics["mainLeft"]
            assert hero_metrics["mainWidth"] > 0
            assert hero_metrics["sidebarWidth"] > 0

            _sign_in(player_mobile_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            player_mobile_page.goto(f"{base_url}/app-next/campaigns/linden-pass/help")
            expect(player_mobile_page.get_by_role("heading", name="Help")).to_be_visible(timeout=10000)
            mobile_metrics = player_mobile_page.evaluate(
                """() => {
                    const layout = document.querySelector(".campaign-help-layout");
                    const main = document.querySelector(".campaign-help-main");
                    const sidebar = document.querySelector(".campaign-help-sidebar");
                    const countGridTracks = (value) => {
                        let depth = 0;
                        let count = 0;
                        let inToken = false;
                        for (const char of value) {
                            if (char === "(") {
                                depth += 1;
                            } else if (char === ")") {
                                depth -= 1;
                            } else if (char === " " && depth === 0) {
                                if (inToken) {
                                    count += 1;
                                    inToken = false;
                                }
                                continue;
                            }
                            if (char === " " && depth > 0 && inToken) {
                                continue;
                            }
                            if (char !== " " || depth > 0) {
                                inToken = true;
                            }
                        }
                        if (inToken) {
                            count += 1;
                        }
                        return count;
                    };
                    const layoutColumns = layout ? window.getComputedStyle(layout).gridTemplateColumns : "";
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        layoutColumns,
                        layoutColumnsCount: countGridTracks(layoutColumns),
                        mainTop: main ? main.getBoundingClientRect().top : 0,
                        mainLeft: main ? main.getBoundingClientRect().left : 0,
                        sidebarTop: sidebar ? sidebar.getBoundingClientRect().top : 0,
                        mainWidth: main ? main.getBoundingClientRect().width : 0,
                        sidebarWidth: sidebar ? sidebar.getBoundingClientRect().width : 0,
                    };
                }"""
            )
            assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["layoutColumnsCount"] == 1
            assert mobile_metrics["sidebarTop"] > mobile_metrics["mainTop"]
            assert mobile_metrics["mainWidth"] <= mobile_metrics["innerWidth"]
            assert mobile_metrics["sidebarWidth"] <= mobile_metrics["innerWidth"]

            _sign_in(dm_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            dm_page.goto(f"{base_url}/app-next/campaigns/linden-pass/help")
            expect(dm_page.get_by_role("heading", name="Help")).to_be_visible(timeout=10000)
            expect(dm_page.locator("#dm-content").get_by_role("heading", name="DM Content")).to_be_visible()
            expect(dm_page.locator("#characters").get_by_role("heading", name="Characters")).to_be_visible()
            expect(dm_page.locator("#control").get_by_role("heading", name="Control")).to_be_visible()
            expect(dm_page.get_by_text("Browser and API boundary")).to_be_visible()
        finally:
            player_page.close()
            dm_page.close()
            player_mobile_page.close()
            player_context.close()
            player_mobile_context.close()
            dm_context.close()
            browser.close()


def test_gen2_campaign_control_updates_visibility_and_blocks_players(
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
            dm_context = browser.new_context(viewport={"width": 1280, "height": 900})
            dm_mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
            player_context = browser.new_context(viewport={"width": 1280, "height": 900})
            dm_page = dm_context.new_page()
            dm_mobile_page = dm_mobile_context.new_page()
            player_page = player_context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(dm_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            dm_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            control_link = dm_page.locator(".campaign-nav-link", has_text="Control")
            expect(control_link).to_be_visible(timeout=10000)
            expect(control_link).to_have_attribute("href", re.compile(r"/app-next/campaigns/linden-pass/control$"))
            control_link.click()
            expect(dm_page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/control$"))
            expect(dm_page.get_by_role("heading", name="Visibility", exact=True)).to_be_visible(timeout=10000)
            expect(dm_page.get_by_role("heading", name="Visibility settings")).to_be_visible()
            expect(dm_page.get_by_role("heading", name="Visibility rules")).to_be_visible()
            expect(dm_page.get_by_role("link", name="Flask Control")).to_be_visible()

            dm_page.locator("#campaign-control-campaign").select_option("players")
            dm_page.locator("#campaign-control-wiki").select_option("dm")
            dm_page.get_by_role("button", name="Save visibility").click()
            expect(dm_page.get_by_text(re.compile(r"Updated visibility for .*Campaign", re.I))).to_be_visible(timeout=5000)
            expect(dm_page.locator("#campaign-control-campaign")).to_have_value("players")
            expect(dm_page.locator("#campaign-control-wiki")).to_have_value("dm")
            expect(dm_page.locator(".campaign-control-form .article-actions + .status")).to_be_visible()
            expect(dm_page.locator(".campaign-control-form .article-actions", has_text="Save visibility")).to_be_visible()

            dm_control_metrics = dm_page.evaluate(
                """() => {
                    const countGridTracks = (value) => {
                        let depth = 0;
                        let count = 0;
                        let inToken = false;
                        for (const char of value) {
                            if (char === "(") {
                                depth += 1;
                            } else if (char === ")") {
                                depth -= 1;
                            } else if (char === " " && depth === 0) {
                                if (inToken) {
                                    count += 1;
                                    inToken = false;
                                }
                                continue;
                            }
                            if (char === " " && depth > 0 && inToken) {
                                continue;
                            }
                            if (char !== " " || depth > 0) {
                                inToken = true;
                            }
                        }
                        if (inToken) {
                            count += 1;
                        }
                        return count;
                    };
                    const hero = document.querySelector(".campaign-control-hero");
                    const layout = document.querySelector(".campaign-control-layout");
                    const form = document.querySelector(".campaign-control-form");
                    const sidebar = document.querySelector(".campaign-control-sidebar");
                    const fallback = form ? form.querySelector("a[href*='control-panel'], a[href*='control']") : null;
                    const rows = Array.from(document.querySelectorAll(".campaign-control-row"));
                    const firstRowMeta = rows[0]?.querySelectorAll(".campaign-control-row__meta p").length ?? 0;
                    const firstSelect = rows[0]?.querySelector("select");
                    const firstSelectRect = firstSelect ? firstSelect.getBoundingClientRect() : null;
                    const firstRowRect = rows[0] ? rows[0].getBoundingClientRect() : null;
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        heroRadius: hero ? Number.parseFloat(window.getComputedStyle(hero).borderRadius) : 0,
                        heroShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        layoutColumns: layout ? window.getComputedStyle(layout).gridTemplateColumns : "",
                        layoutColumnsCount: layout ? countGridTracks(window.getComputedStyle(layout).gridTemplateColumns) : 0,
                        formLeft: form ? form.getBoundingClientRect().left : 0,
                        sidebarLeft: sidebar ? sidebar.getBoundingClientRect().left : 0,
                        formWidth: form ? form.getBoundingClientRect().width : 0,
                        sidebarWidth: sidebar ? sidebar.getBoundingClientRect().width : 0,
                        hasFallback: Boolean(fallback),
                        rowMetaCount: firstRowMeta,
                        selectMinWidth: firstSelectRect ? firstSelectRect.width : 0,
                        rowHeight: firstRowRect ? firstRowRect.height : 0,
                    };
                }"""
            )
            assert dm_control_metrics["heroRadius"] == 0
            assert dm_control_metrics["heroShadow"] == "none"
            assert dm_control_metrics["layoutColumnsCount"] >= 2
            assert dm_control_metrics["scrollWidth"] <= dm_control_metrics["innerWidth"] + 1
            assert dm_control_metrics["sidebarLeft"] >= dm_control_metrics["formLeft"]
            assert dm_control_metrics["formWidth"] > 0
            assert dm_control_metrics["sidebarWidth"] > 0
            assert dm_control_metrics["hasFallback"] is True
            assert dm_control_metrics["rowMetaCount"] >= 3
            assert dm_control_metrics["selectMinWidth"] >= 160
            assert dm_control_metrics["rowHeight"] > 0

            _sign_in(player_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/control")
            expect(player_page.get_by_text("You do not have permission to manage campaign visibility.")).to_be_visible(timeout=10000)

            _sign_in(dm_mobile_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            dm_mobile_page.goto(f"{base_url}/app-next/campaigns/linden-pass/control")
            expect(dm_mobile_page.get_by_role("heading", name="Visibility", exact=True)).to_be_visible(timeout=10000)
            mobile_metrics = dm_mobile_page.evaluate(
                """() => {
                    const countGridTracks = (value) => {
                        let depth = 0;
                        let count = 0;
                        let inToken = false;
                        for (const char of value) {
                            if (char === "(") {
                                depth += 1;
                            } else if (char === ")") {
                                depth -= 1;
                            } else if (char === " " && depth === 0) {
                                if (inToken) {
                                    count += 1;
                                    inToken = false;
                                }
                                continue;
                            }
                            if (char === " " && depth > 0 && inToken) {
                                continue;
                            }
                            if (char !== " " || depth > 0) {
                                inToken = true;
                            }
                        }
                        if (inToken) {
                            count += 1;
                        }
                        return count;
                    };
                    const layout = document.querySelector(".campaign-control-layout");
                    const form = document.querySelector(".campaign-control-form");
                    const sidebar = document.querySelector(".campaign-control-sidebar");
                    const formRect = form ? form.getBoundingClientRect() : null;
                    const sidebarRect = sidebar ? sidebar.getBoundingClientRect() : null;
                    const rowSelect = document.querySelector(".campaign-control-row select");
                    const hero = document.querySelector(".campaign-control-hero");
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        layoutColumns: layout ? window.getComputedStyle(layout).gridTemplateColumns : "",
                        layoutColumnsCount: layout ? countGridTracks(window.getComputedStyle(layout).gridTemplateColumns) : 0,
                        formTop: formRect ? formRect.top : 0,
                        sidebarTop: sidebarRect ? sidebarRect.top : 0,
                        formWidth: formRect ? formRect.width : 0,
                        sidebarWidth: sidebarRect ? sidebarRect.width : 0,
                        heroRadius: hero ? Number.parseFloat(window.getComputedStyle(hero).borderRadius) : 0,
                        heroShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        selectWidth: rowSelect ? rowSelect.getBoundingClientRect().width : 0,
                    };
                }"""
            )
            assert mobile_metrics["layoutColumnsCount"] == 1
            assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["formTop"] < mobile_metrics["sidebarTop"]
            assert mobile_metrics["formWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["sidebarWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["heroRadius"] == 0
            assert mobile_metrics["heroShadow"] == "none"
            assert mobile_metrics["selectWidth"] <= mobile_metrics["innerWidth"] + 1
        finally:
            dm_page.close()
            player_page.close()
            dm_mobile_page.close()
            dm_context.close()
            dm_mobile_context.close()
            player_context.close()
            browser.close()


def test_gen2_account_settings_saves_preferences_and_updates_theme(
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
            desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
            desktop_page = desktop_context.new_page()
            mobile_page = mobile_context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(desktop_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            _sign_in(mobile_page, base_url, email=users["party"]["email"], password=users["party"]["password"])

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            account_link = desktop_page.get_by_role("link", name="Account")
            expect(account_link).to_be_visible(timeout=10000)
            expect(account_link).to_have_attribute("href", re.compile(r"/app-next/account$"))

            desktop_page.goto(f"{base_url}/app-next/account")
            expect(desktop_page.get_by_role("heading", name="Party Player")).to_be_visible(timeout=10000)
            expect(desktop_page.get_by_role("heading", name="Color theme")).to_be_visible()
            expect(desktop_page.get_by_role("heading", name="Preferred frontend")).to_be_visible()
            expect(desktop_page.get_by_role("heading", name="Live session chat order")).to_be_visible()
            expect(desktop_page.get_by_role("link", name="Flask account")).to_be_visible()

            account_hero_styles = desktop_page.evaluate(
                """() => {
                    const hero = document.querySelector(".account-hero");
                    const form = document.querySelector(".account-settings-form");
                    const sidebar = document.querySelector(".account-settings-sidebar");
                    const firstOption = document.querySelector(".settings-option");
                    const firstSwatch = document.querySelector(".settings-option__swatch");
                    const firstOptionRect = firstOption ? firstOption.getBoundingClientRect() : null;
                    const layout = document.querySelector(".account-settings-layout");
                    return {
                        heroBorderTop: hero ? window.getComputedStyle(hero).borderTopWidth : "0px",
                        heroBoxShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        formBorderTop: form ? window.getComputedStyle(form).borderTopWidth : "0px",
                        formBoxShadow: form ? window.getComputedStyle(form).boxShadow : "none",
                        sidebarBorderTop: sidebar ? window.getComputedStyle(sidebar).borderTopWidth : "0px",
                        sidebarBoxShadow: sidebar ? window.getComputedStyle(sidebar).boxShadow : "none",
                        firstOptionLeft: firstOption ? firstOptionRect.left : 0,
                        firstOptionTop: firstOption ? firstOptionRect.top : 0,
                        hasSwatches: Boolean(firstSwatch),
                        formRadius: form ? window.getComputedStyle(form).borderRadius : "0px",
                        sidebarRadius: sidebar ? window.getComputedStyle(sidebar).borderRadius : "0px",
                    };
                }"""
            )
            assert account_hero_styles["heroBorderTop"] == "0px"
            assert account_hero_styles["heroBoxShadow"] == "none"
            assert float(account_hero_styles["formBorderTop"][:-2]) > 0
            assert float(account_hero_styles["sidebarBorderTop"][:-2]) > 0
            assert account_hero_styles["formBoxShadow"] != "none"
            assert account_hero_styles["sidebarBoxShadow"] != "none"
            assert float(account_hero_styles["formRadius"][:-2]) > 0
            assert float(account_hero_styles["sidebarRadius"][:-2]) > 0
            assert account_hero_styles["hasSwatches"] is True
            assert account_hero_styles["firstOptionTop"] > 0
            assert account_hero_styles["firstOptionLeft"] >= 0
            expect(desktop_page.get_by_role("link", name="Flask account")).to_be_visible()

            desktop_page.locator("label[for='account-theme-moonlit']").click()
            desktop_page.locator("label[for='account-frontend-mode-gen2']").click()
            desktop_page.locator("label[for='account-chat-order-oldest_first']").click()
            with desktop_page.expect_response(
                lambda response: response.url.endswith("/api/v1/me/settings") and response.request.method == "PATCH"
            ):
                desktop_page.get_by_role("button", name="Save account settings").click()

            expect(desktop_page.get_by_text("Account settings saved.")).to_be_visible(timeout=10000)
            expect(desktop_page.locator("html")).to_have_attribute("data-theme", "moonlit")

            me_response = desktop_page.request.get(f"{base_url}/api/v1/me")
            assert me_response.ok
            preferences = me_response.json()["preferences"]
            assert preferences == {
                "theme_key": "moonlit",
                "session_chat_order": "oldest_first",
                "frontend_mode": "gen2",
            }
            desktop_page.goto(f"{base_url}/app-next/")
            expect(desktop_page.locator("main > .campaign-picker-page")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".campaign-picker-hero")).to_be_visible()
            expect(desktop_page.get_by_role("heading", name="Select a campaign.")).to_be_visible()
            expect(desktop_page.locator(".campaign-picker-hero .eyebrow")).to_have_text("Campaign access")
            expect(desktop_page.locator(".campaign-picker-hero .lede")).to_have_text(
                "Your account can see the campaigns listed here based on app-wide admin access, campaign membership, or public visibility."
            )
            expect(desktop_page.locator("main > .panel")).to_have_count(0)
            expect(desktop_page.get_by_role("link", name="Open Campaign").first).to_have_attribute(
                "href",
                "/app-next/campaigns/linden-pass",
            )

            desktop_page.goto(f"{base_url}/app-next/account")
            desktop_page.locator("label[for='account-frontend-mode-flask']").click()
            with desktop_page.expect_response(
                lambda response: response.url.endswith("/api/v1/me/settings") and response.request.method == "PATCH"
            ):
                desktop_page.get_by_role("button", name="Save account settings").click()
            expect(desktop_page.get_by_text("Account settings saved.")).to_be_visible(timeout=10000)

            flask_preferences_response = desktop_page.request.get(f"{base_url}/api/v1/me")
            assert flask_preferences_response.ok
            assert flask_preferences_response.json()["preferences"] == {
                "theme_key": "moonlit",
                "session_chat_order": "oldest_first",
                "frontend_mode": "flask",
            }
            desktop_page.goto(f"{base_url}/app-next/")
            expect(desktop_page.locator("main > .campaign-picker-page")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".campaign-picker-hero")).to_be_visible()
            expect(desktop_page.get_by_role("heading", name="Select a campaign.")).to_be_visible()
            expect(desktop_page.locator(".campaign-picker-hero .eyebrow")).to_have_text("Campaign access")
            expect(desktop_page.locator(".campaign-picker-hero .lede")).to_have_text(
                "Your account can see the campaigns listed here based on app-wide admin access, campaign membership, or public visibility."
            )
            expect(desktop_page.locator("main > .panel")).to_have_count(0)
            expect(desktop_page.get_by_role("link", name="Open Campaign").first).to_have_attribute(
                "href",
                "/campaigns/linden-pass",
            )
            expect(desktop_page.get_by_role("link", name="Open Session").first).to_have_attribute(
                "href",
                "/campaigns/linden-pass/session",
            )

            mobile_page.goto(f"{base_url}/app-next/account")
            expect(mobile_page.get_by_role("heading", name="Party Player")).to_be_visible(timeout=10000)
            mobile_layout = mobile_page.evaluate(
                """() => {
                    const layout = document.querySelector(".account-settings-layout");
                    const items = layout ? Array.from(layout.children) : [];
                    const shell = document.documentElement;
                    const metrics = {
                        innerWidth: window.innerWidth,
                        scrollWidth: shell.scrollWidth,
                    };
                    if (!layout) {
                        return { ...metrics, maxItemWidth: 0, count: 0, stacked: false };
                    }
                    const itemRects = items.map((item) => {
                        const rect = item.getBoundingClientRect();
                        return { left: rect.left, right: rect.right, top: rect.top, width: rect.width };
                    });
                    const first = itemRects[0];
                    const second = itemRects[1];
                    const stacked = !second || Math.abs((second.left || 0) - (first.left || 0)) <= 4;
                    return {
                        ...metrics,
                        count: itemRects.length,
                        maxItemWidth: itemRects.reduce((max, item) => Math.max(max, item.width), 0),
                        stacked,
                    };
                }"""
            )
            assert mobile_layout["count"] == 2
            assert mobile_layout["scrollWidth"] <= mobile_layout["innerWidth"] + 1
            assert mobile_layout["maxItemWidth"] <= mobile_layout["innerWidth"] + 1
            assert mobile_layout["stacked"] is True
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
            browser.close()


def test_gen2_admin_user_management_route_and_permissions(
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
            admin_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
            player_context = browser.new_context(viewport={"width": 1280, "height": 900})
            admin_page = admin_context.new_page()
            mobile_page = mobile_context.new_page()
            player_page = player_context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(admin_page, base_url, email=users["admin"]["email"], password=users["admin"]["password"])
            _sign_in(mobile_page, base_url, email=users["admin"]["email"], password=users["admin"]["password"])

            admin_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            admin_link = admin_page.get_by_role("link", name="Admin")
            expect(admin_link).to_be_visible(timeout=10000)
            expect(admin_link).to_have_attribute("href", re.compile(r"/app-next/admin$"))
            admin_link.click()
            expect(admin_page).to_have_url(re.compile(r"/app-next/admin$"))
            expect(admin_page.get_by_role("heading", name="Admin dashboard")).to_be_visible(timeout=10000)
            expect(admin_page.get_by_role("heading", name="Invite user")).to_be_visible()
            expect(admin_page.get_by_role("heading", name="Users")).to_be_visible()
            expect(admin_page.get_by_role("heading", name="Recent activity")).to_be_visible()
            expect(admin_page.get_by_role("link", name="Flask admin")).to_be_visible()

            admin_dashboard_metrics = admin_page.evaluate(
                """() => {
                    const countGridTracks = (value) => value.trim().split(/\\s+/).filter(Boolean).length;
                    const hero = document.querySelector(".admin-hero");
                    const panel = document.querySelector(".admin-panel");
                    const layout = document.querySelector(".admin-layout");
                    const userGrid = document.querySelector(".admin-user-grid");
                    const actions = document.querySelector(".admin-filter-form__actions");
                    return {
                        heroBorderTop: hero ? window.getComputedStyle(hero).borderTopWidth : "0px",
                        heroBoxShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        panelBorderTop: panel ? window.getComputedStyle(panel).borderTopWidth : "0px",
                        panelBoxShadow: panel ? window.getComputedStyle(panel).boxShadow : "none",
                        layoutColumns: layout ? countGridTracks(window.getComputedStyle(layout).gridTemplateColumns) : 0,
                        userGridColumns: userGrid ? countGridTracks(window.getComputedStyle(userGrid).gridTemplateColumns) : 0,
                        actionsDisplay: actions ? window.getComputedStyle(actions).display : "",
                    };
                }"""
            )
            assert admin_dashboard_metrics["heroBorderTop"] == "0px"
            assert admin_dashboard_metrics["heroBoxShadow"] == "none"
            assert float(admin_dashboard_metrics["panelBorderTop"][:-2]) > 0
            assert admin_dashboard_metrics["panelBoxShadow"] != "none"
            assert admin_dashboard_metrics["layoutColumns"] >= 2
            assert admin_dashboard_metrics["userGridColumns"] >= 2
            assert admin_dashboard_metrics["actionsDisplay"] == "flex"

            admin_page.locator("#admin-invite-email").fill("gen2-browser-admin@example.com")
            admin_page.locator("#admin-invite-display-name").fill("Gen2 Browser Admin")
            admin_page.locator("#admin-invite-user-type").select_option("standard")
            admin_page.get_by_role("button", name="Create invite").click()
            expect(admin_page.get_by_text("Invite URL:")).to_be_visible(timeout=10000)
            created_user_link = admin_page.get_by_role("link", name="Gen2 Browser Admin").first
            expect(created_user_link).to_be_visible(timeout=10000)

            created_user_link.click()
            expect(admin_page).to_have_url(re.compile(r"/app-next/admin/users/\d+"))
            expect(admin_page.get_by_role("heading", name="Gen2 Browser Admin")).to_be_visible(timeout=10000)
            expect(admin_page.get_by_role("heading", name="Campaign membership")).to_be_visible()
            expect(admin_page.get_by_role("heading", name="Character assignment")).to_be_visible()
            expect(admin_page.get_by_role("link", name="Flask user record")).to_be_visible()
            expect(admin_page.get_by_role("heading", name="Account actions")).to_be_visible()
            expect(admin_page.get_by_text("Credential actions")).to_be_visible()
            expect(admin_page.get_by_text("Account state")).to_be_visible()
            expect(admin_page.get_by_text("Destructive actions")).to_be_visible()
            expect(admin_page.get_by_role("button", name="Delete user")).to_be_disabled()

            membership_panel = admin_page.locator("article.admin-panel").filter(has_text="Campaign membership")
            membership_panel.locator("#admin-membership-campaign-slug").select_option("linden-pass")
            membership_panel.locator("#admin-membership-role").select_option("player")
            membership_panel.locator("#admin-membership-status").select_option("active")
            membership_panel.get_by_role("button", name="Save membership").click()
            expect(admin_page.get_by_text(re.compile(r"Membership updated: linden-pass -> player"))).to_be_visible(timeout=10000)

            admin_page.locator("#admin-assignment-character-ref").select_option("linden-pass::selene-brook")
            admin_page.get_by_role("button", name="Assign character").click()
            expect(admin_page.get_by_text("Assigned selene-brook in linden-pass")).to_be_visible(timeout=10000)
            expect(admin_page.get_by_text("selene-brook | owner")).to_be_visible()

            mobile_page.goto(f"{base_url}/app-next/admin")
            expect(mobile_page.get_by_role("heading", name="Admin dashboard")).to_be_visible(timeout=10000)
            mobile_layout = mobile_page.evaluate(
                """() => {
                    const countGridTracks = (value) => value.trim().split(/\\s+/).filter(Boolean).length;
                    const layouts = Array.from(document.querySelectorAll(".admin-layout"));
                    const firstLayout = layouts[0];
                    const items = firstLayout ? Array.from(firstLayout.children) : [];
                    const itemRects = items.map((item) => {
                        const rect = item.getBoundingClientRect();
                        return { left: rect.left, width: rect.width };
                    });
                    const first = itemRects[0];
                    const second = itemRects[1];
                    const filter = document.querySelector(".admin-filter-form");
                    const page = document.querySelector(".admin-page");
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        pageWidth: page ? page.getBoundingClientRect().width : 0,
                        maxItemWidth: itemRects.reduce((max, item) => Math.max(max, item.width), 0),
                        layoutCount: layouts.length,
                        firstLayoutStacked: !second || Math.abs((second.left || 0) - (first.left || 0)) <= 4,
                        filterColumns: filter ? countGridTracks(window.getComputedStyle(filter).gridTemplateColumns) : 0,
                    };
                }"""
            )
            assert mobile_layout["layoutCount"] >= 1
            assert mobile_layout["scrollWidth"] <= mobile_layout["innerWidth"] + 1
            assert mobile_layout["pageWidth"] <= mobile_layout["innerWidth"] + 1
            assert mobile_layout["maxItemWidth"] <= mobile_layout["innerWidth"] + 1
            assert mobile_layout["firstLayoutStacked"] is True
            assert mobile_layout["filterColumns"] == 1

            _sign_in(player_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            player_page.goto(f"{base_url}/app-next/admin")
            expect(player_page.get_by_text("You do not have permission to use the admin API.")).to_be_visible(timeout=10000)
        finally:
            admin_page.close()
            mobile_page.close()
            player_page.close()
            admin_context.close()
            mobile_context.close()
            player_context.close()
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


def test_gen2_combat_browser_exposes_dm_status_and_controls(
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
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=status")
            expect(page.get_by_role("heading", name=re.compile(r"Combat:", re.I))).to_be_visible(timeout=10000)
            combat_nav = page.get_by_role("navigation", name="Combat view")
            expect(combat_nav.get_by_role("button", name="DM Status")).to_be_visible()
            expect(combat_nav.get_by_role("button", name="DM Controls")).to_be_visible()

            carousel = page.locator(".combat-carousel")
            carousel.get_by_role("button", name=re.compile(r"Clockwork Hound", re.I)).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/combat\?view=status&combatant=\d+"))
            expect(page.get_by_role("heading", name="Vitals")).to_be_visible(timeout=5000)

            dm_current_hp = page.get_by_label("DM Current HP", exact=True)
            expect(dm_current_hp).to_be_visible()
            dm_current_hp.fill("19")
            page.get_by_role("button", name="Save DM vitals").click()
            expect(page.get_by_text("Vitals saved.")).to_be_visible(timeout=5000)
            expect(dm_current_hp).to_have_value("19")

            page.get_by_label("Condition", exact=True).fill("Restrained")
            page.get_by_label("Duration", exact=True).fill("Until round 3")
            page.get_by_role("button", name="Add condition").click()
            expect(page.get_by_text("Condition added.")).to_be_visible(timeout=5000)
            expect(page.locator(".combat-condition-chip", has_text="Restrained")).to_be_visible()

            combat_nav.get_by_role("button", name="DM Controls").click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/combat\?view=controls&combatant=\d+"))
            expect(page.get_by_role("heading", name="Add NPC")).to_be_visible(timeout=5000)
            name_input = page.get_by_label("Name", exact=True)
            name_input.fill("Glass Raider")
            page.get_by_label("Max HP", exact=True).fill("11")
            page.get_by_label("Current HP", exact=True).fill("11")
            page.get_by_label("Turn", exact=True).fill("7")
            page.wait_for_timeout(1300)
            expect(name_input).to_have_value("Glass Raider")
            page.get_by_role("button", name="Add manual NPC").click()
            expect(page.get_by_text("NPC added.")).to_be_visible(timeout=5000)
            expect(page.locator(".combat-carousel").get_by_role("button", name=re.compile(r"Glass Raider", re.I))).to_be_visible()
        finally:
            page.close()
            browser.close()


def test_gen2_combat_visual_parity_smoke(
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
            desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_page = desktop_context.new_page()
        mobile_page = mobile_context.new_page()

        try:
            _sign_in(desktop_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=player")
            expect(desktop_page.get_by_role("heading", name=re.compile(r"Combat:", re.I))).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".combat-summary-band")).to_be_visible()
            expect(desktop_page.locator(".combat-carousel")).to_be_visible()
            expect(desktop_page.locator(".combat-selected-snapshot")).to_be_visible()
            player_metrics = desktop_page.evaluate(
                """() => {
                    const route = document.querySelector(".combat-page");
                    const hero = document.querySelector(".combat-hero h2");
                    const legacyPanelRoute = document.querySelector("main > .panel.combat-page");
                    const summary = document.querySelector(".combat-summary-band");
                    const summaryCard = document.querySelector(".combat-summary-band article");
                    const carousel = document.querySelector(".combat-carousel");
                    const combatant = document.querySelector(".combatant-card");
                    const snapshot = document.querySelector(".combat-selected-snapshot");
                    return {
                        routeShadow: route ? window.getComputedStyle(route).boxShadow : "",
                        heroSize: hero ? Number.parseFloat(window.getComputedStyle(hero).fontSize) : 0,
                        legacyPanelRoutePresent: legacyPanelRoute ? true : false,
                        summaryRadius: summary ? Number.parseFloat(window.getComputedStyle(summary).borderRadius) : 0,
                        summaryCardRadius: summaryCard ? Number.parseFloat(window.getComputedStyle(summaryCard).borderRadius) : 0,
                        carouselRadius: carousel ? Number.parseFloat(window.getComputedStyle(carousel).borderRadius) : 0,
                        combatantRadius: combatant ? Number.parseFloat(window.getComputedStyle(combatant).borderRadius) : 0,
                        snapshotRadius: snapshot ? Number.parseFloat(window.getComputedStyle(snapshot).borderRadius) : 0,
                    };
                }"""
            )
            assert player_metrics["routeShadow"] == "none"
            assert player_metrics["legacyPanelRoutePresent"] is False
            assert player_metrics["heroSize"] >= 32
            assert player_metrics["summaryRadius"] >= 20
            assert player_metrics["summaryCardRadius"] >= 16
            assert player_metrics["carouselRadius"] >= 20
            assert player_metrics["combatantRadius"] >= 16
            assert player_metrics["snapshotRadius"] >= 20

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=status")
            expect(desktop_page.get_by_role("heading", name=re.compile(r"Combat:", re.I))).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".combat-view-switch")).to_be_visible()
            expect(desktop_page.locator(".combat-dm-grid .combat-control-card").first).to_be_visible()
            status_metrics = desktop_page.evaluate(
                """() => {
                    const switcher = document.querySelector(".combat-view-switch");
                    const controlCard = document.querySelector(".combat-dm-grid .combat-control-card");
                    const condition = document.querySelector(".combat-condition-chip");
                    const grid = document.querySelector(".combat-dm-grid");
                    return {
                        switchRadius: switcher ? Number.parseFloat(window.getComputedStyle(switcher).borderRadius) : 0,
                        controlRadius: controlCard ? Number.parseFloat(window.getComputedStyle(controlCard).borderRadius) : 0,
                        conditionRadius: condition ? Number.parseFloat(window.getComputedStyle(condition).borderRadius) : 16,
                        dmGridColumns: grid ? window.getComputedStyle(grid).gridTemplateColumns.split(" ").length : 0,
                    };
                }"""
            )
            assert status_metrics["switchRadius"] >= 20
            assert status_metrics["controlRadius"] >= 16
            assert status_metrics["conditionRadius"] >= 16
            assert status_metrics["dmGridColumns"] >= 2

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=controls")
            expect(desktop_page.get_by_role("heading", name="Add NPC")).to_be_visible(timeout=10000)
            controls_metrics = desktop_page.evaluate(
                """() => {
                    const layout = document.querySelector(".combat-controls-layout");
                    const controlCard = document.querySelector(".combat-controls-layout .combat-control-card");
                    return {
                        controlRadius: controlCard ? Number.parseFloat(window.getComputedStyle(controlCard).borderRadius) : 0,
                        controlsGridColumns: layout ? window.getComputedStyle(layout).gridTemplateColumns.split(" ").length : 0,
                    };
                }"""
            )
            assert controls_metrics["controlRadius"] >= 16
            assert controls_metrics["controlsGridColumns"] >= 2

            _sign_in(mobile_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            for path in (
                "/app-next/campaigns/linden-pass/combat?view=player",
                "/app-next/campaigns/linden-pass/combat?view=status",
                "/app-next/campaigns/linden-pass/combat?view=controls",
            ):
                mobile_page.goto(f"{base_url}{path}")
                expect(mobile_page.get_by_role("link", name="Campaign Player Wiki")).to_be_visible(timeout=10000)
                mobile_metrics = mobile_page.evaluate(
                    """() => {
                        const route = document.querySelector(".combat-page");
                        const switcher = document.querySelector(".combat-view-switch");
                        const carousel = document.querySelector(".combat-carousel");
                        const carouselTrack = document.querySelector(".combat-carousel-track");
                        return {
                            innerWidth: window.innerWidth,
                            scrollWidth: document.documentElement.scrollWidth,
                            routeWidth: route ? route.getBoundingClientRect().width : 0,
                            switchWidth: switcher ? switcher.getBoundingClientRect().width : 0,
                            carouselWidth: carousel ? carousel.getBoundingClientRect().width : 0,
                            trackClientWidth: carouselTrack ? carouselTrack.getBoundingClientRect().width : 0,
                        };
                    }"""
                )
                assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
                assert mobile_metrics["routeWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["switchWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["carouselWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["trackClientWidth"] <= mobile_metrics["innerWidth"]
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
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
            overview_link = page.locator(".wiki-overview-card h2 a")
            expect(overview_link).to_be_visible()
            expect(overview_link).to_have_attribute(
                "href",
                re.compile(r"^/campaigns/linden-pass/pages/.+"),
            )
            overview_article_link = page.locator(".wiki-overview-card .article-body a", has_text="Operations Brief")
            expect(overview_article_link).to_have_attribute(
                "href",
                "/campaigns/linden-pass/pages/notes/operations-brief",
            )
            expect(page.get_by_role("link", name="Locations").first).to_have_attribute(
                "href",
                "/campaigns/linden-pass/sections/locations",
            )

            frontend_toggle = page.request.post(
                f"{base_url}/account/frontend-mode",
                form={"frontend_mode": "gen2"},
            )
            assert frontend_toggle.ok
            page.goto(f"{base_url}/app-next/campaigns/linden-pass")
            expect(page.get_by_role("heading", name="Campaign Home")).to_be_visible(timeout=10000)
            overview_link = page.locator(".wiki-overview-card h2 a")
            expect(overview_link).to_have_attribute(
                "href",
                re.compile(r"^/app-next/campaigns/linden-pass/pages/.+"),
            )
            overview_article_link = page.locator(".wiki-overview-card .article-body a", has_text="Operations Brief")
            expect(overview_article_link).to_have_attribute(
                "href",
                "/app-next/campaigns/linden-pass/pages/notes/operations-brief",
            )

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


def test_gen2_wiki_visual_parity_smoke(
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
            desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_page = desktop_context.new_page()
        mobile_page = mobile_context.new_page()

        try:
            _sign_in(desktop_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass")
            expect(desktop_page.get_by_role("heading", name="Campaign Home")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".wiki-home")).to_be_visible()
            expect(desktop_page.locator(".wiki-overview-card")).to_be_visible()
            expect(desktop_page.locator(".wiki-section-browse")).to_be_visible()
            home_metrics = desktop_page.evaluate(
                """() => {
                    const route = document.querySelector(".wiki-home");
                    const hero = document.querySelector(".wiki-home");
                    const overviewBody = document.querySelector(".wiki-overview-card .html-body");
                    const browse = document.querySelector(".wiki-section-browse");
                    return {
                        routeShadow: route ? window.getComputedStyle(route).boxShadow : "",
                        heroDisplay: hero ? window.getComputedStyle(hero).display : "",
                        overviewBorder: overviewBody ? window.getComputedStyle(overviewBody).borderTopWidth : "",
                        browseRadius: browse ? Number.parseFloat(window.getComputedStyle(browse).borderRadius) : 0,
                    };
                }"""
            )
            assert home_metrics["routeShadow"] == "none"
            assert home_metrics["heroDisplay"] == "grid"
            assert home_metrics["overviewBorder"] == "0px"
            assert home_metrics["browseRadius"] >= 20

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/sections/locations")
            expect(desktop_page.get_by_role("heading", name="Locations")).to_be_visible(timeout=10000)
            section_metrics = desktop_page.evaluate(
                """() => {
                    const block = document.querySelector(".section-block--collapsible");
                    const chevron = document.querySelector(".section-toggle-chevron");
                    const featured = document.querySelector(".page-card--featured");
                    return {
                        blockRadius: block ? Number.parseFloat(window.getComputedStyle(block).borderRadius) : 0,
                        chevronRadius: chevron ? Number.parseFloat(window.getComputedStyle(chevron).borderRadius) : 0,
                        featuredPaddingTop: featured ? Number.parseFloat(window.getComputedStyle(featured).paddingTop) : 0,
                    };
                }"""
            )
            assert section_metrics["blockRadius"] >= 20
            assert section_metrics["chevronRadius"] >= 20
            assert section_metrics["featuredPaddingTop"] >= 20

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale")
            expect(desktop_page.get_by_role("heading", name="Captain Lyra Vale")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".wiki-article-page .sidebar-card").first).to_be_visible()
            article_metrics = desktop_page.evaluate(
                """() => {
                    const body = document.querySelector(".wiki-article-page .html-body");
                    const image = document.querySelector(".article-figure .article-image");
                    const layout = document.querySelector(".page-layout");
                    return {
                        bodyBorder: body ? window.getComputedStyle(body).borderTopWidth : "",
                        imageRadius: image ? Number.parseFloat(window.getComputedStyle(image).borderRadius) : 0,
                        columnCount: layout ? window.getComputedStyle(layout).gridTemplateColumns.split(" ").length : 0,
                    };
                }"""
            )
            assert article_metrics["bodyBorder"] == "0px"
            assert article_metrics["imageRadius"] >= 20
            assert article_metrics["columnCount"] >= 2

            _sign_in(mobile_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            for path in (
                "/app-next/campaigns/linden-pass",
                "/app-next/campaigns/linden-pass/sections/locations",
                "/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale",
            ):
                mobile_page.goto(f"{base_url}{path}")
                expect(mobile_page.get_by_role("link", name="Campaign Player Wiki")).to_be_visible(timeout=10000)
                mobile_metrics = mobile_page.evaluate(
                    """() => ({
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        layoutColumns: document.querySelector(".page-layout")
                            ? window.getComputedStyle(document.querySelector(".page-layout")).gridTemplateColumns.split(" ").length
                            : 1,
                    })"""
                )
                assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
                assert mobile_metrics["layoutColumns"] == 1
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
            browser.close()


def test_gen2_character_browser_exposes_roster_detail_portrait_and_conflict(
    frontend_gen2_session_live_server,
    app,
    users,
    set_campaign_visibility,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    _seed_arden_portrait(app)
    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            dm_context = browser.new_context(viewport={"width": 1280, "height": 900})
            owner_context = browser.new_context(viewport={"width": 1280, "height": 900})
            player_context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = dm_context.new_page()
            owner_page = owner_context.new_page()
            player_page = player_context.new_page()
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
            expect(page.get_by_role("link", name="Flask editor")).to_be_visible()
            expect(page.get_by_text("Progression repair appears when an imported DND-5E sheet needs it.")).to_be_visible()

            page.get_by_role("link", name="Advanced Editor").click()
            expect(page).to_have_url(
                re.compile(r"/app-next/campaigns/linden-pass/characters/arden-march/edit$"),
                timeout=5000,
            )
            expect(page.get_by_role("heading", name="Edit Arden March")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Reference Text")).to_be_visible()
            expect(page.get_by_role("heading", name="Custom Features")).to_be_visible()
            expect(page.get_by_role("link", name="Flask editor")).to_be_visible()
            page.get_by_label("Biography").fill("Browser Gen2 biography note.")
            page.get_by_role("button", name="Save character edits").click()
            expect(page.get_by_text("Character details updated.")).to_be_visible(timeout=10000)
            expect(page.get_by_label("Biography")).to_have_value("Browser Gen2 biography note.")
            page.get_by_role("link", name="Back to sheet").first.click()
            expect(page).to_have_url(
                re.compile(r"/app-next/campaigns/linden-pass/characters/arden-march$"),
                timeout=5000,
            )
            expect(page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)

            page.locator(".section-tabs").get_by_role("button", name="Controls").click()
            expect(page).to_have_url(
                re.compile(r"/app-next/campaigns/linden-pass/characters/arden-march\?page=controls$"),
                timeout=5000,
            )
            expect(page.get_by_role("heading", name="Controls", exact=True)).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Player controls", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Current owner", exact=True)).to_be_visible()
            expect(page.get_by_text("Owner Player")).to_be_visible()
            expect(page.get_by_role("heading", name="Delete character")).to_be_visible()
            expect(page.get_by_role("button", name="Delete character")).to_be_disabled()
            expect(page.get_by_role("link", name="Flask Controls")).to_be_visible()
            assert page.get_by_role("heading", name="Assignment controls").count() == 0

            _sign_in(owner_page, base_url, email=users["owner"]["email"], password=users["owner"]["password"])
            owner_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/arden-march?page=controls")
            expect(owner_page.get_by_role("heading", name="Controls", exact=True)).to_be_visible(timeout=10000)
            expect(owner_page.get_by_text("Player-controls workspace for Arden March.")).to_be_visible()
            assert owner_page.get_by_role("heading", name="Delete character").count() == 0
            assert owner_page.get_by_role("heading", name="Assignment controls").count() == 0
            owner_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/arden-march/edit")
            expect(owner_page.get_by_role("heading", name="Edit Arden March")).to_be_visible(timeout=10000)
            expect(owner_page.get_by_role("button", name="Save character edits")).to_be_visible()

            _sign_in(player_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/arden-march?page=controls")
            expect(player_page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)
            expect(player_page.get_by_role("button", name="Overview")).to_be_visible()
            assert player_page.get_by_role("button", name="Controls").count() == 0
            assert player_page.get_by_role("heading", name="Controls", exact=True).count() == 0
            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/arden-march/edit")
            expect(player_page.get_by_text("You do not have permission to edit this character.")).to_be_visible(timeout=10000)
            assert player_page.get_by_role("button", name="Save character edits").count() == 0

            page.locator(".section-tabs").get_by_role("button", name="Overview").click()
            expect(page).to_have_url(
                re.compile(r"/app-next/campaigns/linden-pass/characters/arden-march$"),
                timeout=5000,
            )

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
            owner_page.close()
            player_page.close()
            dm_context.close()
            owner_context.close()
            player_context.close()
            browser.close()


def test_gen2_character_visual_parity_smoke(
    frontend_gen2_session_live_server,
    app,
    users,
    set_campaign_visibility,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    _seed_arden_portrait(app)
    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_page = desktop_context.new_page()
        mobile_page = mobile_context.new_page()

        try:
            _sign_in(desktop_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters")
            expect(desktop_page.get_by_role("heading", name="Characters")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".character-roster-page > .character-roster-hero")).to_be_visible()
            expect(desktop_page.locator("main > .panel.character-roster-page")).to_have_count(0)
            expect(desktop_page.locator(".character-roster-tools")).to_be_visible()
            expect(desktop_page.locator(".character-roster-grid .character-card").first).to_be_visible()
            roster_metrics = desktop_page.evaluate(
                """() => {
                    const route = document.querySelector(".character-roster-page");
                    const hero = document.querySelector(".character-roster-hero h1");
                    const tools = document.querySelector(".character-roster-tools");
                    const cardStat = document.querySelector(".character-card__stats article");
                    const portrait = document.querySelector(".character-card__portrait");
                    const search = document.querySelector(".character-roster-search");
                    return {
                        routeShadow: route ? window.getComputedStyle(route).boxShadow : "",
                        heroSize: hero ? Number.parseFloat(window.getComputedStyle(hero).fontSize) : 0,
                        toolsRadius: tools ? Number.parseFloat(window.getComputedStyle(tools).borderRadius) : 0,
                        cardStatRadius: cardStat ? Number.parseFloat(window.getComputedStyle(cardStat).borderRadius) : 0,
                        portraitRadius: portrait ? Number.parseFloat(window.getComputedStyle(portrait).borderRadius) : 0,
                        searchColumns: search ? window.getComputedStyle(search).gridTemplateColumns.split(" ").length : 0,
                    };
                }"""
            )
            assert roster_metrics["routeShadow"] == "none"
            assert roster_metrics["heroSize"] >= 32
            assert roster_metrics["toolsRadius"] >= 20
            assert roster_metrics["cardStatRadius"] >= 16
            assert roster_metrics["portraitRadius"] >= 8
            assert roster_metrics["searchColumns"] >= 2

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/arden-march")
            expect(desktop_page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)
            expect(desktop_page.get_by_role("heading", name="Arden March (arden-march)")).to_be_visible()
            expect(desktop_page.locator(".character-read-shell")).to_be_visible()
            expect(desktop_page.locator(".character-selector-card")).to_be_visible()
            expect(desktop_page.locator(".character-summary")).to_be_visible()
            expect(desktop_page.locator(".section-tabs")).to_be_visible()
            detail_metrics = desktop_page.evaluate(
                """() => {
                    const shell = document.querySelector(".character-read-shell");
                    const selector = document.querySelector(".character-selector-card");
                    const summary = document.querySelector(".character-summary");
                    const summaryHeading = document.querySelector(".character-summary h3");
                    const tabs = document.querySelector(".section-tabs");
                    const stateCard = document.querySelector(".stat-grid article, .character-state-card");
                    return {
                        shellRadius: shell ? Number.parseFloat(window.getComputedStyle(shell).borderRadius) : 0,
                        selectorRadius: selector ? Number.parseFloat(window.getComputedStyle(selector).borderRadius) : 0,
                        summaryRadius: summary ? Number.parseFloat(window.getComputedStyle(summary).borderRadius) : 0,
                        summaryHeadingSize: summaryHeading ? Number.parseFloat(window.getComputedStyle(summaryHeading).fontSize) : 0,
                        tabsRadius: tabs ? Number.parseFloat(window.getComputedStyle(tabs).borderRadius) : 0,
                        stateCardRadius: stateCard ? Number.parseFloat(window.getComputedStyle(stateCard).borderRadius) : 0,
                    };
                }"""
            )
            assert detail_metrics["shellRadius"] >= 20
            assert detail_metrics["selectorRadius"] >= 16
            assert detail_metrics["summaryRadius"] >= 16
            assert detail_metrics["summaryHeadingSize"] >= 24
            assert detail_metrics["tabsRadius"] >= 16
            assert detail_metrics["stateCardRadius"] >= 16

            _sign_in(mobile_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            for path in (
                "/app-next/campaigns/linden-pass/characters",
                "/app-next/campaigns/linden-pass/characters/arden-march",
            ):
                mobile_page.goto(f"{base_url}{path}")
                expect(mobile_page.get_by_role("link", name="Campaign Player Wiki")).to_be_visible(timeout=10000)
                mobile_metrics = mobile_page.evaluate(
                    """() => {
                        const route = document.querySelector(".character-roster-page, .character-read-shell");
                        const tabs = document.querySelector(".section-tabs");
                        const selector = document.querySelector(".character-selector-card");
                        const search = document.querySelector(".character-roster-search");
                        return {
                            innerWidth: window.innerWidth,
                            scrollWidth: document.documentElement.scrollWidth,
                            routeWidth: route ? route.getBoundingClientRect().width : 0,
                            tabsWidth: tabs ? tabs.getBoundingClientRect().width : 0,
                            selectorWidth: selector ? selector.getBoundingClientRect().width : 0,
                            searchColumns: search ? window.getComputedStyle(search).gridTemplateColumns.split(" ").length : 1,
                        };
                    }"""
                )
                assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
                assert mobile_metrics["routeWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["tabsWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["selectorWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["searchColumns"] == 1
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
            browser.close()


def test_gen2_xianxia_character_authoring_create_and_import(
    frontend_gen2_session_live_server,
    app,
    users,
    set_campaign_visibility,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = frontend_gen2_session_live_server

    create_values = {
        "name": "Browser Gen2 Crane",
        "character_slug": "browser-gen2-crane",
        "attribute_str": "3",
        "attribute_dex": "0",
        "attribute_con": "3",
        "attribute_int": "0",
        "attribute_wis": "0",
        "attribute_cha": "0",
        "effort_basic": "3",
        "effort_weapon": "1",
        "effort_guns_explosive": "0",
        "effort_magic": "1",
        "effort_ultimate": "0",
        "energy_jing": "1",
        "energy_qi": "1",
        "energy_shen": "1",
        "trained_skill_1": "Fishing",
        "trained_skill_2": "Calligraphy",
        "trained_skill_3": "Tea Ceremony",
        "manual_armor_bonus": "1",
        "dao_current": "1",
    }
    create_selects = {
        "martial_art_1_slug": "demons-fist",
        "martial_art_1_rank": "initiate",
        "martial_art_2_slug": "heavenly-palm",
        "martial_art_2_rank": "initiate",
        "martial_art_3_slug": "taoist-blade",
        "martial_art_3_rank": "initiate",
    }
    import_values = {
        "name": "Browser Imported Lotus",
        "character_slug": "browser-imported-lotus",
        "reputation": "Browser route witness",
        "attribute_str": "9",
        "attribute_dex": "8",
        "attribute_con": "7",
        "attribute_int": "6",
        "attribute_wis": "5",
        "attribute_cha": "4",
        "effort_basic": "3",
        "effort_weapon": "4",
        "effort_guns_explosive": "5",
        "effort_magic": "6",
        "effort_ultimate": "7",
        "hp_max": "19",
        "stance_max": "17",
        "manual_armor_bonus": "4",
        "insight_available": "12",
        "insight_spent": "8",
        "energy_jing_max": "5",
        "energy_qi_max": "6",
        "energy_shen_max": "7",
        "yin_max": "9",
        "yang_max": "10",
        "dao_max": "3",
        "coin": "12",
        "supply": "3",
        "spirit_stones": "2",
        "trained_skills_text": "Tea Ceremony\nQi Sense | Raised by a wandering hermit\nSky Calling",
        "martial_art_1_rank": "Novice",
        "martial_art_1_teacher": "Elder Qing",
        "inventory_text": "Spirit rice | 3 | consumable | Emergency cache",
        "additional_notes_markdown": "Imported through Gen2.",
        "player_notes_markdown": "Browser import note.",
    }

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            player_context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            player_page = player_context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters")
            expect(page.get_by_role("heading", name="Characters")).to_be_visible(timeout=10000)
            create_link = page.get_by_role("link", name="Create character")
            import_link = page.get_by_role("link", name="Import existing")
            expect(create_link).to_have_attribute("href", re.compile(r"/app-next/campaigns/linden-pass/characters/new$"))
            expect(import_link).to_have_attribute("href", re.compile(r"/app-next/campaigns/linden-pass/characters/import/xianxia-manual$"))

            create_link.click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/characters/new$"))
            expect(page.locator("main > .character-authoring-page.character-authoring-create-page > .character-authoring-hero")).to_be_visible(
                timeout=10000
            )
            expect(page.locator("main > .panel.character-authoring-page")).to_have_count(0)
            expect(page.get_by_role("heading", name="Create Xianxia Character")).to_be_visible(timeout=10000)
            expect(page.get_by_role("link", name="Flask create")).to_be_visible()
            for field_name, value in create_values.items():
                page.locator(f"[name='{field_name}']").fill(value)
            for field_name, value in create_selects.items():
                page.locator(f"[name='{field_name}']").select_option(value)
            page.get_by_role("button", name="Create character").click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/characters/browser-gen2-crane$"), timeout=10000)
            expect(page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name=re.compile(r"Browser Gen2 Crane"))).to_be_visible()
            cultivation_link = page.get_by_role("link", name="Cultivation", exact=True)
            expect(cultivation_link).to_have_attribute(
                "href",
                re.compile(r"/app-next/campaigns/linden-pass/characters/browser-gen2-crane/cultivation$"),
            )
            expect(page.get_by_role("link", name="Flask Cultivation")).to_be_visible()

            cultivation_link.click()
            expect(page).to_have_url(
                re.compile(r"/app-next/campaigns/linden-pass/characters/browser-gen2-crane/cultivation$"),
                timeout=5000,
            )
            expect(page.get_by_role("heading", name="Cultivation: Browser Gen2 Crane")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Insight", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Realm Ascension")).to_be_visible()
            expect(page.get_by_role("link", name="Flask Cultivation")).to_be_visible()
            page.get_by_label("Insight available").fill("2")
            page.get_by_label("Insight spent").fill("1")
            page.get_by_role("button", name="Save Insight").click()
            expect(page.get_by_text("Insight counters saved.")).to_be_visible(timeout=10000)
            expect(page.locator("#xianxia-cultivation-insight .glance-card", has_text="Available").get_by_text("2")).to_be_visible()

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/level-up")
            expect(page.get_by_role("heading", name="Level Up Browser Gen2 Crane")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Level-Up Is Not Available In Gen2")).to_be_visible()
            expect(page.get_by_role("link", name="Cultivation")).to_be_visible()

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/retraining")
            expect(page.get_by_role("heading", name="Retrain Browser Gen2 Crane")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Retraining Is Not Available In Gen2")).to_be_visible()
            expect(page.get_by_role("link", name="Cultivation")).to_be_visible()

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/progression-repair")
            expect(page.get_by_role("heading", name="Prepare Browser Gen2 Crane For Native Level-Up")).to_be_visible(
                timeout=10000
            )
            expect(page.get_by_role("heading", name="Progression Repair Is Not Available In Gen2")).to_be_visible()
            expect(page.get_by_role("link", name="Cultivation")).to_be_visible()

            _sign_in(player_page, base_url, email=users["party"]["email"], password=users["party"]["password"])
            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/cultivation")
            expect(player_page.get_by_text("You do not have permission to manage cultivation for this character.")).to_be_visible(
                timeout=10000
            )
            assert player_page.get_by_role("button", name="Save Insight").count() == 0

            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/level-up")
            expect(player_page.get_by_text("You do not have permission to level up this character.")).to_be_visible(
                timeout=10000
            )
            assert player_page.get_by_role("button", name=re.compile(r"Advance to level")).count() == 0

            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/retraining")
            expect(player_page.get_by_text("You do not have permission to retrain this character.")).to_be_visible(
                timeout=10000
            )
            assert player_page.get_by_role("button", name="Save retraining").count() == 0

            player_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/progression-repair")
            expect(
                player_page.get_by_text("You do not have permission to repair progression for this character.")
            ).to_be_visible(timeout=10000)
            assert player_page.get_by_role("button", name="Save Repair").count() == 0

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/import/xianxia-manual")
            expect(page.locator("main > .character-authoring-page.character-authoring-manual-import-page > .character-authoring-hero")).to_be_visible(
                timeout=10000
            )
            expect(page.locator("main > .panel.character-authoring-page")).to_have_count(0)
            expect(page.get_by_role("heading", name="Import Existing Xianxia Character")).to_be_visible(timeout=10000)
            expect(page.get_by_role("link", name="Flask import")).to_be_visible()
            page.locator("[name='realm']").select_option("Immortal")
            page.locator("[name='honor']").select_option("Majestic")
            page.locator("[name='martial_art_1_slug']").select_option("heavenly-palm")
            for field_name, value in import_values.items():
                page.locator(f"[name='{field_name}']").fill(value)
            page.get_by_role("button", name="Preview import").click()
            expect(page.get_by_role("heading", name="Review Import")).to_be_visible(timeout=10000)
            expect(page.get_by_text("Browser Imported Lotus")).to_be_visible()
            page.get_by_role("button", name="Confirm import").click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/characters/browser-imported-lotus$"), timeout=10000)
            expect(page.get_by_role("heading", name="Character Sheet")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name=re.compile(r"Browser Imported Lotus"))).to_be_visible()
        finally:
            page.close()
            player_page.close()
            context.close()
            player_context.close()
            browser.close()


def test_gen2_systems_browser_exposes_search_and_entry_detail(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    entry_title = "Gen2 Browse Focus Rule"
    entry_body = "The Gen2 systems browser renders this rule."

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            create_response = page.request.post(
                f"{base_url}/api/v1/campaigns/linden-pass/systems/custom-entries",
                headers={"Content-Type": "application/json"},
                data=json.dumps(
                    {
                        "title": entry_title,
                        "slug_leaf": "gen2-browse-focus-rule",
                        "entry_type": "rule",
                        "visibility": "dm",
                        "provenance": "Gen2 browser test",
                        "search_metadata": "focus gen2 systems browse",
                        "body_markdown": f"## Browser Body\n\n{entry_body}",
                    }
                ),
            )
            assert create_response.ok
            entry_slug = create_response.json()["entry"]["slug"]

            for viewport in (
                {"width": 1280, "height": 900},
                {"width": 390, "height": 900},
            ):
                page.set_viewport_size(viewport)
                page.goto(f"{base_url}/app-next/campaigns/linden-pass/systems?q=focus")

                expect(page.locator("section.systems-browse-index-page")).to_be_visible(timeout=10_000)
                expect(page.locator(".systems-hero")).to_be_visible()
                expect(page.locator(".systems-browse-grid")).to_be_visible()
                expect(page.locator(".systems-search-band")).to_be_visible()
                expect(page.locator(".systems-browse-sidebar")).to_be_visible()
                expect(page.get_by_role("heading", name="Systems", exact=True)).to_be_visible(timeout=10_000)
                expect(page.get_by_role("heading", name="Search Results")).to_be_visible()
                expect(page.locator(".campaign-nav-link").get_by_text("Systems")).to_be_visible()
                assert page.evaluate(
                    """() => {
                        const selectors = [
                            '.systems-browse-page',
                            '.systems-hero',
                            '.systems-browse-grid',
                            '.systems-browse-sidebar',
                        ];
                        const viewportWidth = Math.ceil(document.documentElement.clientWidth);
                        return selectors.every((selector) => {
                            const node = document.querySelector(selector);
                            if (!node) {
                                return true;
                            }
                            return node.scrollWidth <= viewportWidth + 1;
                        });
                    }"""
                )
                layout_columns = page.evaluate(
                    """() => {
                        const grid = document.querySelector('.systems-browse-grid');
                        if (!grid) {
                            return 0;
                        }
                        return getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/).length;
                    }"""
                )
                if viewport["width"] >= 1024:
                    assert layout_columns >= 2
                else:
                    assert layout_columns == 1

                page.get_by_role("link", name=entry_title).click()
                expect(page).to_have_url(
                    re.compile(rf"/app-next/campaigns/linden-pass/systems/entries/{re.escape(entry_slug)}$"),
                    timeout=5000,
                )
                expect(page.locator(".systems-entry-shell")).to_be_visible(timeout=10_000)
                expect(page.locator(".systems-entry-band")).to_be_visible()
                expect(page.locator(".systems-entry-sidebar")).to_be_visible()
                expect(page.locator(".systems-sidebar-card").first).to_be_visible()
                expect(page.locator(".systems-entry-navigation")).to_be_visible()
                expect(page.get_by_role("heading", name=entry_title)).to_be_visible(timeout=10_000)
                expect(page.get_by_role("heading", name="Entry Metadata")).to_be_visible()
                expect(page.get_by_role("link", name="Source page")).to_be_visible()
                expect(page.get_by_role("link", name="Source category")).to_be_visible()
                expect(page.get_by_text(entry_body)).to_be_visible()
                expect(page.get_by_role("link", name="Manage campaign override")).to_be_visible()

                page.get_by_role("link", name="Source category").click()

                expect(page.locator(".systems-source-category-page")).to_be_visible(timeout=10_000)
                expect(page.locator(".systems-category-band")).to_be_visible()
                expect(page.locator('.systems-hero .eyebrow', has_text="Systems source category")).to_be_visible()
                expect(page.get_by_role("heading", name=re.compile(r"Browse", re.I))).to_be_visible()
                expect(page.get_by_role("link", name=entry_title)).to_be_visible()
                expect(page).to_have_url(
                    re.compile(r"/app-next/campaigns/linden-pass/systems/sources/.+/types/.+$"),
                    timeout=5_000,
                )
                expect(page.locator(".systems-browse-sidebar")).to_be_visible()
                assert page.evaluate(
                    """() => {
                        const selectors = [
                            '.systems-source-category-page',
                            '.systems-category-band',
                            '.systems-browse-sidebar',
                        ];
                        const viewportWidth = Math.ceil(document.documentElement.clientWidth);
                        return selectors.every((selector) => {
                            const node = document.querySelector(selector);
                            if (!node) {
                                return true;
                            }
                            return node.scrollWidth <= viewportWidth + 1;
                        });
                    }"""
                )
                category_layout_columns = page.evaluate(
                    """() => {
                        const grid = document.querySelector('.systems-browse-grid');
                        if (!grid) {
                            return 0;
                        }
                        return getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/).length;
                    }"""
                )
                if viewport["width"] >= 1024:
                    assert category_layout_columns >= 2
                else:
                    assert category_layout_columns == 1

                page.get_by_role("link", name="Source").click()

                expect(page.locator(".systems-source-page")).to_be_visible(timeout=10_000)
                expect(page.locator(".systems-source-band")).to_be_visible()
                expect(page.locator('.systems-hero .eyebrow', has_text="Systems source")).to_be_visible()
                expect(page.get_by_role("heading", name="Browse This Source")).to_be_visible()
                expect(page).to_have_url(
                    re.compile(r"/app-next/campaigns/linden-pass/systems/sources/.+$"),
                    timeout=5_000,
                )
                expect(page.locator(".systems-browse-sidebar")).to_be_visible()
                assert page.evaluate(
                    """() => {
                        const selectors = [
                            '.systems-source-page',
                            '.systems-source-band',
                            '.systems-browse-sidebar',
                        ];
                        const viewportWidth = Math.ceil(document.documentElement.clientWidth);
                        return selectors.every((selector) => {
                            const node = document.querySelector(selector);
                            if (!node) {
                                return true;
                            }
                            return node.scrollWidth <= viewportWidth + 1;
                        });
                    }"""
                )

                source_layout_columns = page.evaluate(
                    """() => {
                        const grid = document.querySelector('.systems-browse-grid');
                        if (!grid) {
                            return 0;
                        }
                        return getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/).length;
                    }"""
                )
                if viewport["width"] >= 1024:
                    assert source_layout_columns >= 2
                else:
                    assert source_layout_columns == 1
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


@pytest.mark.parametrize(
    ("lane", "heading", "active_label"),
    [
        ("", "DM Content: Statblocks", "Statblocks"),
        ("staged-articles", "DM Content: Staged Articles", "Staged Articles"),
        ("conditions", "DM Content: Conditions", "Conditions"),
        ("player-wiki", "DM Content: Player Wiki", "Player Wiki"),
        ("systems", "DM Content: Systems", "Systems"),
    ],
)
def test_gen2_dm_content_browser_visual_parity_smoke(
    frontend_gen2_session_live_server,
    users,
    lane: str,
    heading: str,
    active_label: str,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    base_path = f"{base_url}/app-next/campaigns/linden-pass/dm-content"
    url = base_path if not lane else f"{base_path}?lane={lane}"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = browser.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            for viewport in (
                {"width": 1280, "height": 900},
                {"width": 390, "height": 900},
            ):
                page.set_viewport_size(viewport)
                page.goto(url)

                page_root = page.locator("main > section.dm-content-gen2-page")
                page_hero = page.locator("section.dm-content-hero")
                expect(page_root).to_be_visible(timeout=10000)
                expect(page_hero).to_be_visible(timeout=10000)
                expect(page.get_by_role("heading", name=heading)).to_be_visible(timeout=10000)
                assert page.locator("main > .panel.dm-content-gen2-page").count() == 0

                fallback_links = page.locator(".dm-content-gen2-links")
                expect(fallback_links).to_be_visible()
                expect(fallback_links.get_by_role("link", name=active_label)).to_be_visible()
                expect(fallback_links.get_by_role("link", name="Session DM")).to_be_visible()
                active_classes = fallback_links.get_by_role("link", name=active_label).first.get_attribute("class") or ""
                assert "is-active" in active_classes

                assert page.evaluate(
                    """() => {
                        const pageNode = document.querySelector('.dm-content-gen2-page');
                        if (!pageNode) {
                            return false;
                        }
                        const styles = getComputedStyle(pageNode);
                        return (
                            parseFloat(styles.borderWidth) === 0 &&
                            parseFloat(styles.borderRadius) === 0 &&
                            styles.boxShadow === 'none'
                        );
                    }""",
                )

                if viewport["width"] >= 1024 and lane != "systems":
                    columns = page.evaluate(
                        """() => {
                            const grid = document.querySelector('.dm-content-staged-grid');
                            if (!grid) {
                                return 0;
                            }
                            return getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/).length;
                        }""",
                    )
                    assert columns >= 2
                elif viewport["width"] >= 1024:
                    systems_metrics = page.evaluate(
                        """() => {
                            const lane = document.querySelector('.dm-content-systems-lane');
                            const panels = Array.from(document.querySelectorAll('.dm-content-systems-lane .panel-nested'));
                            return {
                                panelCount: panels.length,
                                firstRadius: panels.length ? Number.parseFloat(getComputedStyle(panels[0]).borderRadius) : 0,
                                laneWidth: lane ? Math.ceil(lane.getBoundingClientRect().width) : 0,
                            };
                        }""",
                    )
                    assert systems_metrics["panelCount"] >= 4
                    assert systems_metrics["firstRadius"] >= 18
                    assert systems_metrics["laneWidth"] > 0

                assert page.evaluate(
                    """() => {
                        const viewportWidth = Math.ceil(document.documentElement.clientWidth);
                        const selectors = [
                            '.dm-content-hero',
                            '.dm-content-staged-grid',
                            '.dm-content-gen2-links',
                        ];
                        return selectors.every((selector) => {
                            const node = document.querySelector(selector);
                            if (!node) {
                                return true;
                            }
                            return node.scrollWidth <= viewportWidth + 1;
                        });
                    }""",
                )
                page.evaluate("window.scrollTo(0, 0)")
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


def test_gen2_dm_content_browser_systems_custom_entry_workflow(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server
    entry_title = "Gen2 Focus Rule"
    updated_entry_title = "Gen2 Focus Rule Revised"
    entry_body = "A custom Systems rule authored through the Gen2 management lane."
    updated_entry_body = "The Gen2 Systems lane can edit and restore custom campaign rules."

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/dm-content?lane=systems")
            expect(page.get_by_role("heading", name="DM Content: Systems")).to_be_visible(timeout=10000)
            fallback_links = page.locator(".dm-content-gen2-links")
            expect(fallback_links.get_by_role("link", name="Statblocks")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Staged Articles")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Conditions")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Player Wiki", exact=True)).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Systems")).to_be_visible()
            expect(fallback_links.get_by_role("link", name="Systems")).to_have_attribute(
                "href",
                "/app-next/campaigns/linden-pass/dm-content?lane=systems",
            )
            expect(fallback_links.get_by_role("link", name="Session DM")).to_be_visible()

            expect(page.get_by_role("heading", name="Source Enablement")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Entry Overrides")).to_be_visible()
            expect(page.get_by_role("heading", name="Custom Entries")).to_be_visible()
            expect(page.get_by_role("heading", name="Shared Source Imports")).to_be_visible()
            expect(page.get_by_role("heading", name="Import-Run History")).to_be_visible()

            custom_panel = page.locator("#systems-custom-entries")
            custom_panel.locator("#systems-custom-create-title").fill(entry_title)
            custom_panel.locator("#systems-custom-create-slug").fill("gen2-focus-rule")
            custom_panel.locator("#systems-custom-create-type").select_option("rule")
            custom_panel.locator("#systems-custom-create-provenance").fill("Gen2 browser test")
            custom_panel.locator("#systems-custom-create-search").fill("focus, gen2, systems")
            custom_panel.locator("#systems-custom-create-body").fill(entry_body)
            custom_panel.get_by_role("button", name="Create custom entry").click()
            expect(page.get_by_text(f"Custom Systems entry created: {entry_title}.")).to_be_visible(timeout=10000)

            custom_panel.get_by_label("Search custom entries").fill("Gen2 Focus")
            entry_card = custom_panel.locator("details.article-card", has_text=entry_title)
            expect(entry_card).to_be_visible(timeout=10000)
            entry_card.locator("summary").click()
            expect(entry_card.locator("pre.dm-content-preview", has_text=entry_body)).to_be_visible()

            entry_card.get_by_label("Title").fill(updated_entry_title)
            entry_card.get_by_label("Rendered body markdown").fill(updated_entry_body)
            entry_card.get_by_role("button", name="Update custom entry").click()
            expect(page.get_by_text(f"Custom Systems entry updated: {updated_entry_title}.")).to_be_visible(timeout=10000)

            updated_card = custom_panel.locator("details.article-card", has_text=updated_entry_title)
            expect(updated_card).to_be_visible(timeout=10000)
            if not updated_card.evaluate("element => element.open"):
                updated_card.locator("summary").click()
            expect(updated_card.locator("pre.dm-content-preview", has_text=updated_entry_body)).to_be_visible()

            updated_card.get_by_role("button", name="Archive").click()
            expect(page.get_by_text(f"Custom Systems entry archived: {updated_entry_title}.")).to_be_visible(timeout=10000)
            archived_card = custom_panel.locator("details.article-card", has_text=updated_entry_title)
            expect(archived_card).to_be_visible(timeout=10000)
            if not archived_card.evaluate("element => element.open"):
                archived_card.locator("summary").click()
            expect(archived_card.get_by_text("Archived")).to_be_visible()

            archived_card.get_by_role("button", name="Restore").click()
            expect(page.get_by_text(f"Custom Systems entry restored: {updated_entry_title}.")).to_be_visible(timeout=10000)
            restored_card = custom_panel.locator("details.article-card", has_text=updated_entry_title)
            expect(restored_card).to_be_visible(timeout=10000)
            if not restored_card.evaluate("element => element.open"):
                restored_card.locator("summary").click()
            expect(restored_card.get_by_text("Active")).to_be_visible()
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
