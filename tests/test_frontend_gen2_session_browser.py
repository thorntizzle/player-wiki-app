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


def test_gen2_session_page_auth_notice_card_shape(
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

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            expect(page.locator(".session-hero").get_by_role("heading", name="Session")).to_be_visible(timeout=10000)

            page.evaluate("() => localStorage.setItem('cpw-pilot-api-token', 'invalid-auth-token')")
            page.reload()

            auth_notice = page.locator(".auth-notice.card")
            expect(auth_notice).to_be_visible(timeout=10000)
            expect(auth_notice.get_by_role("heading", name="Authentication required")).to_be_visible()
            expect(auth_notice.locator(".hero-actions")).to_be_visible()
            expect(auth_notice.get_by_role("link", name="Sign in")).to_be_visible()
            expect(auth_notice.get_by_role("button", name="Continue without token")).to_be_visible()
            expect(auth_notice.locator(".button-link")).to_be_visible()
            expect(auth_notice.locator(".ghost-button")).to_be_visible()
            expect(auth_notice.get_by_role("button", name="Continue without token")).to_have_class(re.compile(r"\bghost-button\b"))
            assert page.locator(".panel.auth-notice").count() == 0
            expect(page.locator(".auth-notice .hero-actions")).to_be_visible()
            expect(page.locator(".auth-notice .button-link")).to_have_attribute(
                "href",
                re.compile(r"^/sign-in\?next="),
            )
        finally:
            page.close()
            browser.close()


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
            expect(page.locator(".session-hero").get_by_role("heading", name="Session")).to_be_visible()
            expect(page.locator(".session-hero").get_by_text("Session Workspace")).to_be_visible()
            expect(page.locator(".session-hero").get_by_text("Live play workspace.")).to_be_visible()
            expect(page.locator(".session-hero > .hero-actions.session-tab-strip")).to_be_visible()
            assert page.locator(".session-page-tab-row").count() == 0
            assert page.locator(".session-page-toolbar").count() == 0
            assert page.locator("a", has_text="Sign in").count() == 0
            assert page.locator("text=Back to list").count() == 0
            assert page.locator("text=/Session:/").count() == 0

            session_tabs = page.locator(".session-tab-strip")
            expect(session_tabs.get_by_role("button", name="Session", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="Character", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="DM", exact=True)).to_be_visible()

            page.reload()
            expect(page.locator(".session-hero").get_by_role("heading", name="Session")).to_be_visible(timeout=10000)
            expect(page.locator(".campaign-nav-link").get_by_text("Session")).to_be_visible()
            assert page.locator(".pane-visible .page-layout.session-layout.session-layout--single > .session-column").count() == 1
            assert page.locator(".pane-visible .page-layout.session-layout > .session-sidebar").count() == 0
            assert page.locator(".pane-visible .session-workspace-grid").count() == 0
            assert page.locator(".pane-visible .session-workspace-main").count() == 0
            assert page.locator(".pane-visible .session-workspace-sidebar").count() == 0

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            assert page.locator(".pane-visible .page-layout.session-layout > .session-column").count() == 1
            assert page.locator(".pane-visible .page-layout.session-layout > .session-sidebar").count() == 1
            assert page.locator(".pane-visible .session-workspace-grid").count() == 0
            assert page.locator(".pane-visible .session-workspace-main").count() == 0
            assert page.locator(".pane-visible .session-workspace-sidebar").count() == 0
            expect(page.get_by_role("heading", name="Session controls")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Session article store")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Live session")).to_be_visible(timeout=5000)
            dm_card_texts = page.evaluate(
                """() => {
                    const section = document.querySelector(".pane-visible .page-layout.session-layout > .session-column");
                    return Array.from(
                        section
                            ? section.querySelectorAll(
                                ":scope > .session-passive-scores-bar .section-title,"
                                + ":scope > .card.session-sidebar-card .section-heading > h2"
                            )
                            : [],
                    ).map((node) => (node.textContent || "").trim());
                }"""
            )
            sidebar_ids = page.evaluate(
                """() => {
                    const sidebar = document.querySelector(".pane-visible .page-layout.session-layout > .session-sidebar");
                    const ids = sidebar
                        ? {
                            status: !!sidebar.querySelector("#session-controls"),
                            articleStore: !!sidebar.querySelector("#session-article-store"),
                          }
                        : null;
                    return ids;
                }"""
            )
            main_ids = page.evaluate(
                """() => {
                    const main = document.querySelector(".pane-visible .page-layout.session-layout > .session-column");
                    const ids = main
                        ? {
                            passive: !!main.querySelector("#session-passive-scores"),
                            staged: !!main.querySelector("#session-staged-articles"),
                            revealed: !!main.querySelector("#session-revealed-articles"),
                            logs: !!main.querySelector("#session-chat-logs"),
                          }
                        : null;
                    return ids;
                }"""
            )
            assert page.locator(".pane-visible .page-layout.session-layout > .session-column .panel-nested").count() == 0
            assert page.locator(".pane-visible .page-layout.session-layout > .session-sidebar .panel-nested").count() == 0
            assert page.locator(".pane-visible .page-layout.session-layout > .session-column .card.session-sidebar-card").count() >= 2
            assert page.locator(".pane-visible .page-layout.session-layout > .session-sidebar .card.session-sidebar-card").count() >= 2
            assert "Live session" not in dm_card_texts
            assert dm_card_texts.index("Staged articles") != -1
            assert dm_card_texts.index("Chat logs") != -1
            assert sidebar_ids is not None
            assert sidebar_ids["status"] is True
            assert sidebar_ids["articleStore"] is True
            assert main_ids is not None
            assert main_ids["staged"] is True
            assert main_ids["logs"] is True
            assert main_ids["passive"] is True
            if main_ids["revealed"]:
                assert dm_card_texts.index("Revealed articles") != -1
            for viewport in (
                {"width": 1280, "height": 900},
                {"width": 390, "height": 900},
            ):
                page.set_viewport_size(viewport)
                layout_metrics = page.evaluate(
                    """(viewportWidth) => {
                        const layout = document.querySelector(".pane-visible .page-layout.session-layout");
                        const layoutColumns = layout ? window.getComputedStyle(layout).gridTemplateColumns : "";
                        const layoutColumnsCount = layoutColumns.trim()
                            ? layoutColumns.trim().split(/\\s+/).length
                            : 0;
                        const selectors = [
                            ".pane-visible .page-layout.session-layout > .session-column",
                            ".pane-visible .page-layout.session-layout > .session-sidebar",
                            ".pane-visible .page-layout.session-layout > .session-column .card.session-sidebar-card",
                            ".pane-visible .page-layout.session-layout > .session-sidebar .card.session-sidebar-card",
                        ];
                        return {
                            fits: selectors.every((selector) => {
                                const node = document.querySelector(selector);
                                return !node || node.scrollWidth <= viewportWidth + 1;
                            }),
                            layoutColumnsCount,
                        };
                    }""",
                    viewport["width"],
                )
                assert layout_metrics["fits"] is True
                if viewport["width"] <= 480:
                    assert layout_metrics["layoutColumnsCount"] == 1
                else:
                    assert layout_metrics["layoutColumnsCount"] >= 2
            passive_index = dm_card_texts.index("Passive scores") if "Passive scores" in dm_card_texts else None
            staged_index = dm_card_texts.index("Staged articles")
            logs_index = dm_card_texts.index("Chat logs")
            if passive_index is not None:
                assert passive_index == 0
                assert passive_index < staged_index
            else:
                assert dm_card_texts[0] == "Staged articles"
            assert dm_card_texts.index("Staged articles") < dm_card_texts.index("Chat logs")
            assert staged_index < logs_index
            revealed_index = dm_card_texts.index("Revealed articles") if "Revealed articles" in dm_card_texts else None
            if revealed_index is not None:
                assert staged_index < revealed_index
                assert revealed_index < logs_index
            expect(page.locator(".session-sidebar").get_by_role("heading", name="Live session")).to_be_visible()
            expect(page.locator(".session-sidebar").get_by_role("heading", name="Session controls")).to_be_visible()
            expect(page.get_by_role("button", name=re.compile(r"Begin session|Close session|Starting|Closing", re.I))).to_be_visible()
            expect(page.get_by_role("heading", name="Staged articles")).to_be_visible()
            expect(page.get_by_role("heading", name="Chat logs")).to_be_visible()

            session_tabs.get_by_role("button", name="Session", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.locator(".session-hero").get_by_role("heading", name="Session")).to_be_visible()
            expect(page.get_by_role("heading", name="Chat window")).to_be_visible()
            expect(page.locator(".session-player-wiki-details-summary")).to_have_text("Player wiki lookup")
            expect(page.get_by_role("heading", name="Send message")).to_be_visible()
            expect(page.get_by_label("Audience")).to_be_visible()
            expect(page.get_by_label("Player")).to_be_visible()
            expect(page.get_by_label("Message")).to_be_visible()
            player_card_texts = page.evaluate(
                """() => {
                    const section = document.querySelector(".pane-visible .page-layout.session-layout > .session-column");
                    return Array.from(
                        section
                            ? section.querySelectorAll(
                                ":scope > .session-status-card .section-heading h2, :scope > .session-chat-card .section-heading h2"
                            )
                            : [],
                    ).map((node) => (node.textContent || "").trim());
                }"""
            )
            assert player_card_texts[:2] == ["Live session", "Chat window"]
            assert "Revealed articles" not in player_card_texts[:2]
            assert page.locator("article.card.session-status-card[data-session-status-card]").count() == 1
            assert page.locator("article.card.session-chat-card#session-chat[data-session-chat-card]").count() == 1
            assert page.locator("article.card.session-composer-card#session-chat-compose").count() == 1

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="Session Character")).to_be_visible(timeout=10000)
            expect(page.get_by_label("Character", exact=True)).to_be_visible()
            embedded_character_shell = page.locator(".session-pane-content > article.card.character-sheet.session-character-sheet")
            expect(embedded_character_shell).to_be_visible()
            expect(embedded_character_shell.locator("> header.character-header h2")).to_be_visible()
            expect(embedded_character_shell.locator("> header.character-header h1")).to_have_count(0)
            vitals_bar = embedded_character_shell.locator("section#session-vitals.session-bar")
            expect(vitals_bar).to_be_visible()
            expect(vitals_bar.locator("> .panel-header")).to_have_count(0)
            expect(vitals_bar.locator(".session-bar__summary")).to_be_visible()
            expect(vitals_bar.locator(".session-vitals-form")).to_have_count(1)
            expect(vitals_bar.locator(".session-bar__actions .ghost-button")).to_have_count(2)
            overview_section = embedded_character_shell.locator("section#character-overview.read-section")
            expect(overview_section).to_be_visible()
            expect(overview_section.locator("> .section-heading > h2")).to_have_text("Overview")
            expect(embedded_character_shell.locator("> section.session-character-form")).to_have_count(0)
            expect(embedded_character_shell.locator("> section.read-section > h3")).to_have_count(0)
            assert page.locator(".session-pane-content > .panel").count() == 0
            expect(page.locator(".session-pane-content > .panel-header")).to_have_count(0)
            vitals_bar.get_by_role("button", name="Short rest").click()
            expect(embedded_character_shell.locator("section.card.session-card")).to_be_visible(timeout=10000)
            expect(embedded_character_shell.locator("section.card.session-card > .panel-header")).to_have_count(0)
            expect(embedded_character_shell.locator("ul.rest-preview-list")).to_have_count(1)
            expect(embedded_character_shell.locator("section.card.session-card .hero-actions .ghost-button")).to_have_count(2)
            embedded_character_shell.locator("section.card.session-card .hero-actions").get_by_role("button", name="Cancel").click()
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
            expect(desktop_page.locator(".session-tab-strip .button-link", has_text="Session")).to_be_visible()

            desktop_metrics = desktop_page.evaluate(
                """() => {
                    const bodyStyle = window.getComputedStyle(document.body);
                    const root = document.querySelector(".campaign-global-search");
                    const nav = document.querySelector(".campaign-nav-link");
                    const hero = document.querySelector(".session-hero");
                    const firstPanel = document.querySelector(".page-layout.session-layout > .session-column .session-status-card");
                    const topbar = document.querySelector(".topbar");
                    const globalSearchForm = document.querySelector(".campaign-global-search__form");
                    const globalSearchResults = document.querySelector(".campaign-global-search__results");
                    const remPx = parseFloat(window.getComputedStyle(document.documentElement).fontSize) || 16;
                    return {
                        fontFamily: bodyStyle.fontFamily,
                        bodyColor: bodyStyle.color,
                        globalSearchRootWidth: root ? root.getBoundingClientRect().width : 0,
                        navRadius: nav ? Number.parseFloat(window.getComputedStyle(nav).borderRadius) : 0,
                        heroTop: hero ? hero.getBoundingClientRect().top : 0,
                        firstPanelTop: firstPanel ? firstPanel.getBoundingClientRect().top : 0,
                        topbarBottom: topbar ? topbar.getBoundingClientRect().bottom : 0,
                        globalSearchFormWidth: globalSearchForm ? globalSearchForm.getBoundingClientRect().width : 0,
                        globalSearchResultsWidth: globalSearchResults ? globalSearchResults.getBoundingClientRect().width : 0,
                        globalSearchFormDirection: globalSearchForm
                            ? window.getComputedStyle(globalSearchForm).flexDirection
                            : "",
                        globalSearchRootCapPx: 58 * remPx,
                        globalSearchResultsCapPx: 46 * remPx,
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
            assert desktop_metrics["globalSearchFormDirection"] == "row"
            assert desktop_metrics["globalSearchRootWidth"] <= desktop_metrics["globalSearchRootCapPx"] + 1
            assert desktop_metrics["globalSearchFormWidth"] <= desktop_metrics["globalSearchRootCapPx"] + 1
            assert desktop_metrics["globalSearchResultsWidth"] <= desktop_metrics["globalSearchResultsCapPx"] + 1

            desktop_page.locator(".campaign-global-search__field input").fill("capt")
            desktop_page.locator(".campaign-global-search__form button[type='submit']").click()
            search_result = desktop_page.locator(".campaign-global-search-result", has_text="Captain Lyra Vale")
            expect(search_result).to_be_visible(timeout=10_000)
            search_results_metrics = desktop_page.evaluate(
                """() => {
                    const globalSearchResults = document.querySelector(".campaign-global-search__results");
                    const remPx = parseFloat(window.getComputedStyle(document.documentElement).fontSize) || 16;
                    const rect = globalSearchResults ? globalSearchResults.getBoundingClientRect() : { width: 0 };
                    return {
                        globalSearchResultsWidth: rect.width,
                        globalSearchResultsCapPx: 46 * remPx,
                    };
                }"""
            )
            assert search_results_metrics["globalSearchResultsWidth"] > 0
            assert search_results_metrics["globalSearchResultsWidth"] <= search_results_metrics["globalSearchResultsCapPx"] + 1
            search_result.click()
            expect(desktop_page.locator(".spell-detail-dialog.campaign-global-search-dialog")).to_be_visible(timeout=10_000)
            expect(desktop_page.locator(".campaign-global-search-dialog-panel")).to_have_count(0)
            expect(desktop_page.locator(".campaign-global-search-dialog__panel")).to_be_visible()
            expect(desktop_page.locator(".spell-detail-dialog__header h2")).to_have_text("Campaign Search")
            expect(desktop_page.locator(".spell-detail-dialog__header .ghost-button", has_text="Close")).to_be_visible()
            expect(desktop_page.locator(".campaign-global-search-dialog__body")).to_have_attribute("aria-live", "polite")
            expect(desktop_page.locator(".campaign-global-search-dialog__body")).to_have_attribute("aria-busy", "false")
            expect(desktop_page.locator(".campaign-global-search-dialog__body .campaign-global-search-preview")).to_be_visible()
            expect(desktop_page.locator(".campaign-global-search-preview__header h3", has_text="Captain Lyra Vale")).to_be_visible()
            desktop_page.locator(".spell-detail-dialog__header .ghost-button", has_text="Close").click()
            expect(desktop_page.locator(".spell-detail-dialog.campaign-global-search-dialog")).to_have_count(0)

            _sign_in(mobile_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            mobile_page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            expect(mobile_page.locator(".topbar-campaign")).to_be_visible(timeout=10000)
            expect(mobile_page.locator(".session-tab-strip")).to_be_visible()
            mobile_metrics = mobile_page.evaluate(
                """() => {
                    const globalSearchForm = document.querySelector(".campaign-global-search__form");
                    const submitButton = globalSearchForm
                        ? globalSearchForm.querySelector("button[type='submit']")
                        : null;
                    return {
                    innerWidth: window.innerWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    tabWidth: document.querySelector(".session-tab-strip")?.getBoundingClientRect().width ?? 0,
                    shellWidth: document.querySelector(".session-page-shell")?.getBoundingClientRect().width ?? 0,
                    heroTop: document.querySelector(".session-hero")?.getBoundingClientRect().top ?? 0,
                    firstPanelTop: document.querySelector(".page-layout.session-layout > .session-column .session-status-card")?.getBoundingClientRect().top ?? 0,
                    topbarBottom: document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0,
                    globalSearchFormDirection: globalSearchForm
                        ? window.getComputedStyle(globalSearchForm).flexDirection
                        : "",
                    globalSearchFormWidth: globalSearchForm ? globalSearchForm.getBoundingClientRect().width : 0,
                    globalSearchButtonWidth: submitButton ? submitButton.getBoundingClientRect().width : 0,
                    }"""
            )
            assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["tabWidth"] <= mobile_metrics["innerWidth"]
            assert mobile_metrics["shellWidth"] <= mobile_metrics["innerWidth"]
            assert mobile_metrics["heroTop"] <= 520
            assert mobile_metrics["firstPanelTop"] <= mobile_metrics["heroTop"] + 360
            assert mobile_metrics["firstPanelTop"] >= mobile_metrics["topbarBottom"] + 50
            assert mobile_metrics["globalSearchFormDirection"] == "column"
            assert mobile_metrics["globalSearchButtonWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["globalSearchButtonWidth"] >= mobile_metrics["globalSearchFormWidth"] - 1
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
            assert player_page.locator("main .campaign-help-page").count() == 0
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
                    const main = document.querySelector("main");
                    const hero = main ? main.querySelector(".hero.compact.campaign-help-hero") : null;
                    const layout = main ? main.querySelector(".page-layout.campaign-help-layout") : null;
                    const mainArea = main ? main.querySelector(".session-column.campaign-help-main") : null;
                    const sidebar = main ? main.querySelector(".session-sidebar.campaign-help-sidebar") : null;
                    const detailGrids = main ? main.querySelectorAll(".detail-grid").length : 0;
                    const sidebarCards = main ? main.querySelectorAll(".session-sidebar-card").length : 0;
                    const layoutColumns = layout ? window.getComputedStyle(layout).gridTemplateColumns : "";
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        heroRadius: hero ? Number.parseFloat(window.getComputedStyle(hero).borderRadius) : 0,
                        heroShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        hasLegacyWrapper: !!(main && main.querySelector(".campaign-help-page")),
                        heroIsDirect: !!(hero && hero.parentElement === main),
                        layoutIsDirect: !!(layout && layout.parentElement === main),
                        hasSessionColumnClass: !!(main && main.querySelector(".session-column")),
                        hasSessionSidebarClass: !!(main && main.querySelector(".session-sidebar")),
                        detailGridCount: detailGrids,
                        sidebarCardCount: sidebarCards,
                        mainAreaIsInLayout: !!(mainArea && mainArea.parentElement === layout),
                        layoutColumns,
                        layoutColumnsCount: countGridTracks(layoutColumns),
                        mainTop: mainArea ? mainArea.getBoundingClientRect().top : 0,
                        mainLeft: mainArea ? mainArea.getBoundingClientRect().left : 0,
                        sidebarLeft: sidebar ? sidebar.getBoundingClientRect().left : 0,
                        mainWidth: mainArea ? mainArea.getBoundingClientRect().width : 0,
                        sidebarWidth: sidebar ? sidebar.getBoundingClientRect().width : 0,
                    };
                }"""
            )
            assert hero_metrics["hasLegacyWrapper"] is False
            assert hero_metrics["heroIsDirect"] is True
            assert hero_metrics["layoutIsDirect"] is True
            assert hero_metrics["mainAreaIsInLayout"] is True
            assert hero_metrics["hasSessionColumnClass"] is True
            assert hero_metrics["hasSessionSidebarClass"] is True
            assert hero_metrics["detailGridCount"] >= 4
            assert hero_metrics["sidebarCardCount"] >= 3
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
                    const main = document.querySelector("main");
                    const layout = main ? main.querySelector(".page-layout.campaign-help-layout") : null;
                    const mainArea = layout && layout.querySelector(".session-column.campaign-help-main");
                    const sidebar = main ? main.querySelector(".session-sidebar.campaign-help-sidebar") : null;
                    const detailGrids = main ? main.querySelectorAll(".detail-grid").length : 0;
                    const sidebarCards = main ? main.querySelectorAll(".session-sidebar-card").length : 0;
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
                        mainTop: mainArea ? mainArea.getBoundingClientRect().top : 0,
                        mainLeft: mainArea ? mainArea.getBoundingClientRect().left : 0,
                        hasSessionColumnClass: !!(main && main.querySelector(".session-column")),
                        hasSessionSidebarClass: !!(main && main.querySelector(".session-sidebar")),
                        detailGridCount: detailGrids,
                        sidebarCardCount: sidebarCards,
                        sidebarTop: sidebar ? sidebar.getBoundingClientRect().top : 0,
                        mainWidth: mainArea ? mainArea.getBoundingClientRect().width : 0,
                        sidebarWidth: sidebar ? sidebar.getBoundingClientRect().width : 0,
                    };
                }"""
            )
            assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
            assert mobile_metrics["layoutColumnsCount"] == 1
            assert mobile_metrics["hasSessionColumnClass"] is True
            assert mobile_metrics["hasSessionSidebarClass"] is True
            assert mobile_metrics["detailGridCount"] >= 4
            assert mobile_metrics["sidebarCardCount"] >= 3
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
            expect(dm_page.locator("main.main-shell > .campaign-control-page")).to_have_count(0)
            expect(dm_page.locator("main.main-shell > .campaign-control-hero")).to_be_visible()
            expect(dm_page.locator("main.main-shell > .campaign-control-layout")).to_be_visible()
            expect(dm_page.locator(".campaign-control-form .hero-actions", has_text="Save visibility")).to_be_visible()

            dm_page.locator("#campaign-control-campaign").select_option("players")
            dm_page.locator("#campaign-control-wiki").select_option("dm")
            dm_page.get_by_role("button", name="Save visibility").click()
            expect(dm_page.get_by_text(re.compile(r"Updated visibility for .*Campaign", re.I))).to_be_visible(timeout=5000)
            expect(dm_page.locator("#campaign-control-campaign")).to_have_value("players")
            expect(dm_page.locator("#campaign-control-wiki")).to_have_value("dm")
            expect(dm_page.locator(".campaign-control-form .hero-actions + .status")).to_be_visible()
            expect(dm_page.locator(".campaign-control-form .hero-actions", has_text="Save visibility")).to_be_visible()

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
            expect(dm_mobile_page.locator("main.main-shell > .campaign-control-page")).to_have_count(0)
            expect(dm_mobile_page.locator("main.main-shell > .campaign-control-hero")).to_be_visible()
            expect(dm_mobile_page.locator("main.main-shell > .campaign-control-layout")).to_be_visible()
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
            public_context = browser.new_context(viewport={"width": 1280, "height": 900})
            desktop_page = desktop_context.new_page()
            mobile_page = mobile_context.new_page()
            public_page = public_context.new_page()
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
            expect(desktop_page.get_by_role("heading", name="Live session chat order")).to_be_visible()
            expect(desktop_page.get_by_role("link", name="Flask account")).to_be_visible()
            expect(desktop_page.get_by_role("link", name="Back to campaigns")).to_have_attribute("href", "/campaigns")
            expect(desktop_page.locator("text=Preferred frontend")).to_have_count(0)
            expect(desktop_page.locator("text=Stable Flask")).to_have_count(0)
            expect(desktop_page.locator("text=Gen2 frontend")).to_have_count(0)
            expect(desktop_page.locator("label[for='account-frontend-mode-gen2']")).to_have_count(0)
            expect(desktop_page.locator("label[for='account-frontend-mode-flask']")).to_have_count(0)

            account_hero_styles = desktop_page.evaluate(
                """() => {
                    const hero = document.querySelector(".hero.compact.account-hero");
                    const panel = document.querySelector(".card.account-panel");
                    const sidebar = document.querySelector(".card.account-sidebar");
                    const firstOption = document.querySelector(".theme-option");
                    const firstSwatch = document.querySelector(".theme-option__swatch");
                    const firstOptionGrid = document.querySelector(".theme-grid");
                    const firstOptionRect = firstOption ? firstOption.getBoundingClientRect() : null;
                    const layout = document.querySelector(".account-layout");
                    const mainChildren = Array.from(document.querySelectorAll("main > *")).map((node) => node.className);
                    const countGridTracks = (value) => value.trim().split(/\\s+/).filter(Boolean).length;
                    return {
                        heroBorderTop: hero ? window.getComputedStyle(hero).borderTopWidth : "0px",
                        heroBoxShadow: hero ? window.getComputedStyle(hero).boxShadow : "none",
                        panelBorderTop: panel ? window.getComputedStyle(panel).borderTopWidth : "0px",
                        panelBoxShadow: panel ? window.getComputedStyle(panel).boxShadow : "none",
                        sidebarBorderTop: sidebar ? window.getComputedStyle(sidebar).borderTopWidth : "0px",
                        sidebarBoxShadow: sidebar ? window.getComputedStyle(sidebar).boxShadow : "none",
                        hasLegacyFormShell: Boolean(document.querySelector("form.panel.account-settings-form")),
                        hasLegacySidebarShell: Boolean(document.querySelector("aside.panel.account-settings-sidebar")),
                        firstOptionLeft: firstOption ? firstOptionRect.left : 0,
                        firstOptionTop: firstOption ? firstOptionRect.top : 0,
                        hasSwatches: Boolean(firstSwatch),
                        panelRadius: panel ? window.getComputedStyle(panel).borderRadius : "0px",
                        sidebarRadius: sidebar ? window.getComputedStyle(sidebar).borderRadius : "0px",
                        optionGridColumns: firstOptionGrid ? countGridTracks(window.getComputedStyle(firstOptionGrid).gridTemplateColumns) : 0,
                        accountPanelHeaderCount: document.querySelectorAll(
                            ".card.account-panel .account-settings-group .panel-header"
                        ).length,
                        hasAccountPanelHeader: Boolean(
                            document.querySelector(".card.account-panel .account-settings-group .panel-header")
                        ),
                        hasRouteWrapper: Boolean(document.querySelector("main > .account-settings-page")),
                        firstMainChild: mainChildren[0] || "",
                        secondMainChild: mainChildren[1] || "",
                    };
                }"""
            )
            assert account_hero_styles["heroBorderTop"] == "0px"
            assert account_hero_styles["heroBoxShadow"] == "none"
            assert float(account_hero_styles["panelBorderTop"][:-2]) > 0
            assert float(account_hero_styles["sidebarBorderTop"][:-2]) > 0
            assert account_hero_styles["panelBoxShadow"] != "none"
            assert account_hero_styles["sidebarBoxShadow"] != "none"
            assert float(account_hero_styles["panelRadius"][:-2]) > 0
            assert float(account_hero_styles["sidebarRadius"][:-2]) > 0
            assert account_hero_styles["accountPanelHeaderCount"] == 0
            assert account_hero_styles["hasAccountPanelHeader"] is False
            assert account_hero_styles["hasSwatches"] is True
            assert account_hero_styles["hasLegacyFormShell"] is False
            assert account_hero_styles["hasLegacySidebarShell"] is False
            assert account_hero_styles["optionGridColumns"] == 1
            assert account_hero_styles["hasRouteWrapper"] is False
            assert "account-hero" in account_hero_styles["firstMainChild"]
            assert "account-layout" in account_hero_styles["secondMainChild"]
            assert account_hero_styles["firstOptionTop"] > 0
            assert account_hero_styles["firstOptionLeft"] >= 0
            expect(desktop_page.get_by_role("link", name="Flask account")).to_be_visible()

            desktop_page.locator("label[for='account-theme-moonlit']").click()
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
                "frontend_mode": "flask",
            }
            desktop_page.goto(f"{base_url}/app-next/")
            expect(desktop_page.locator("main > .campaign-picker-page")).to_have_count(0)
            expect(desktop_page.locator("main > .campaign-picker-hero")).to_be_visible(timeout=10000)
            expect(desktop_page.locator("main > .campaign-picker-grid")).to_be_visible(timeout=10000)
            expect(desktop_page.locator("main > .campaign-picker-hero + .campaign-picker-grid")).to_have_count(1)
            expect(desktop_page.get_by_role("heading", name="Select a campaign.")).to_be_visible()
            expect(desktop_page.locator(".campaign-picker-hero .eyebrow")).to_have_text("Campaign access")
            expect(desktop_page.locator(".campaign-picker-hero .lede")).to_have_text(
                "Your account can see the campaigns listed here based on app-wide admin access, campaign membership, or public visibility."
            )
            public_page.goto(f"{base_url}/app-next/")
            expect(public_page.locator(".campaign-picker-hero .eyebrow")).to_have_text("Campaign wiki")
            expect(public_page.get_by_role("heading", name="Browse available campaigns.")).to_be_visible()
            expect(public_page.locator(".campaign-picker-hero .lede")).to_have_text(
                "Public campaign wiki pages are available without signing in. Use an account only when you need admin or character access."
            )
            expect(desktop_page.locator("main > .panel")).to_have_count(0)
            campaign_card = desktop_page.locator(".campaign-picker-grid .campaign-card").first
            expect(campaign_card.locator("a.button-link")).to_have_count(1)
            expect(campaign_card.locator("a.button-link", has_text="Open campaign")).to_have_attribute(
                "href",
                "/campaigns/linden-pass",
            )
            expect(campaign_card.get_by_role("link", name="Open Session")).to_have_count(0)
            expect(campaign_card.locator(".article-actions")).to_have_count(0)
            desktop_page.goto(f"{base_url}/app-next/")

            mobile_page.goto(f"{base_url}/app-next/account")
            expect(mobile_page.get_by_role("heading", name="Party Player")).to_be_visible(timeout=10000)
            mobile_layout = mobile_page.evaluate(
                """() => {
                    const layout = document.querySelector(".account-layout");
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
            public_page.close()
            desktop_context.close()
            mobile_context.close()
            public_context.close()
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
            expect(admin_page.get_by_role("link", name="Flask admin")).to_have_count(0)
            expect(admin_page.locator("section.hero.admin-hero .hero-actions")).to_have_count(0)

            admin_dashboard_metrics = admin_page.evaluate(
                """() => {
                    const countGridTracks = (value) => value.trim().split(/\\s+/).filter(Boolean).length;
                    const main = document.querySelector("main.main-shell");
                    const mainChildren = main ? Array.from(main.children) : [];
                    const adminHero = mainChildren.find(
                        (node) =>
                            node.tagName.toLowerCase() === "section"
                            && node.classList.contains("hero")
                            && node.classList.contains("compact")
                            && node.classList.contains("admin-hero"),
                    );
                    const adminHeroIndex = mainChildren.indexOf(adminHero);
                    const panel = document.querySelector("article.card.admin-panel, aside.card.admin-panel");
                    const layouts = Array.from(document.querySelectorAll("main.main-shell > .admin-layout"));
                    const userGrids = Array.from(document.querySelectorAll("main.main-shell > .section-list .admin-user-grid"));
                    const firstLayout = layouts[0] || null;
                    const actions = document.querySelector(".audit-filter-form__actions");
                    const legacyPanelShells = document.querySelectorAll("article.panel.admin-panel, aside.panel.admin-panel");
                    const dashboardUserCards = document.querySelectorAll("article.card.admin-user-card");
                    const legacyUserCards = document.querySelectorAll("article.panel.admin-user-card");
                    const siblingDataSections = adminHeroIndex >= 0
                        ? mainChildren.slice(adminHeroIndex + 1).filter((node) => {
                            return (
                                node.tagName.toLowerCase() === "section"
                                && (node.classList.contains("admin-layout") || node.classList.contains("section-list"))
                            );
                          }).length
                        : 0;
                    return {
                        hasAdminPageWrapper: !!(main ? main.querySelector(":scope > .admin-page") : null),
                        hasDirectAdminHero: !!adminHero,
                        heroIsFirstChild: adminHero && mainChildren.length > 0 ? adminHero === mainChildren[0] : false,
                        mainChildCount: mainChildren.length,
                        siblingDataSectionCount: siblingDataSections,
                        heroTag: adminHero ? adminHero.tagName.toLowerCase() : "",
                        heroBorderTop: adminHero ? window.getComputedStyle(adminHero).borderTopWidth : "0px",
                        heroBoxShadow: adminHero ? window.getComputedStyle(adminHero).boxShadow : "none",
                        panelBorderTop: panel ? window.getComputedStyle(panel).borderTopWidth : "0px",
                        panelBoxShadow: panel ? window.getComputedStyle(panel).boxShadow : "none",
                        dashboardCardPanelCount: document.querySelectorAll("article.card.admin-panel, aside.card.admin-panel").length,
                        legacyPanelShellCount: legacyPanelShells.length,
                        dashboardUserCardCount: dashboardUserCards.length,
                        legacyUserCardCount: legacyUserCards.length,
                        layoutColumns: firstLayout ? countGridTracks(window.getComputedStyle(firstLayout).gridTemplateColumns) : 0,
                        userGridColumns: userGrids[0] ? countGridTracks(window.getComputedStyle(userGrids[0]).gridTemplateColumns) : 0,
                        actionsDisplay: actions ? window.getComputedStyle(actions).display : "",
                        filterGhostActionCount: document.querySelectorAll(".audit-filter-form__actions .ghost-button").length,
                        filterSecondaryActionCount: document.querySelectorAll(".audit-filter-form__actions .button.button-secondary").length,
                        paginationAnchorCount: document.querySelectorAll(".pagination-bar__actions a").length,
                        paginationGhostActionCount: document.querySelectorAll(".pagination-bar__actions .ghost-button").length,
                        paginationSecondaryActionCount: document.querySelectorAll(".pagination-bar__actions .button.button-secondary").length,
                    };
                }"""
            )
            assert admin_dashboard_metrics["hasAdminPageWrapper"] is False
            assert admin_dashboard_metrics["hasDirectAdminHero"] is True
            assert admin_dashboard_metrics["heroIsFirstChild"] is True
            assert admin_dashboard_metrics["mainChildCount"] >= 3
            assert admin_dashboard_metrics["heroTag"] == "section"
            assert admin_dashboard_metrics["heroBorderTop"] == "0px"
            assert admin_dashboard_metrics["heroBoxShadow"] == "none"
            assert float(admin_dashboard_metrics["panelBorderTop"][:-2]) > 0
            assert admin_dashboard_metrics["panelBoxShadow"] != "none"
            assert admin_dashboard_metrics["siblingDataSectionCount"] >= 2
            assert admin_dashboard_metrics["dashboardCardPanelCount"] >= 3
            assert admin_dashboard_metrics["legacyPanelShellCount"] == 0
            assert admin_dashboard_metrics["dashboardUserCardCount"] >= 1
            assert admin_dashboard_metrics["legacyUserCardCount"] == 0
            assert admin_dashboard_metrics["layoutColumns"] >= 2
            assert admin_dashboard_metrics["userGridColumns"] >= 2
            assert admin_dashboard_metrics["actionsDisplay"] == "flex"
            assert admin_dashboard_metrics["filterGhostActionCount"] == 2
            assert admin_dashboard_metrics["filterSecondaryActionCount"] == 0
            assert admin_dashboard_metrics["paginationGhostActionCount"] == admin_dashboard_metrics["paginationAnchorCount"]
            assert admin_dashboard_metrics["paginationSecondaryActionCount"] == 0

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
            expect(admin_page.locator("section.hero.admin-hero .hero-actions")).to_have_count(1)
            expect(admin_page.get_by_role("link", name="Back to admin dashboard")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(admin_page.get_by_role("link", name="Flask user record")).to_have_count(0)
            expect(admin_page.get_by_role("heading", name="Campaign membership")).to_be_visible()
            expect(admin_page.get_by_role("heading", name="Character assignment")).to_be_visible()
            expect(admin_page.get_by_role("heading", name="Account actions")).to_be_visible()
            expect(admin_page.get_by_text("Credential actions")).to_be_visible()
            expect(admin_page.get_by_text("Account state")).to_be_visible()
            expect(admin_page.get_by_text("Destructive actions")).to_be_visible()
            expect(admin_page.get_by_role("button", name="Delete user")).to_be_disabled()

            admin_user_detail_metrics = admin_page.evaluate(
                """() => ({
                    auditFilterGhostCount: document.querySelectorAll(".audit-filter-form__actions .ghost-button").length,
                    auditFilterSecondaryCount: document.querySelectorAll(".audit-filter-form__actions .button.button-secondary").length,
                    paginationAnchorCount: document.querySelectorAll(".pagination-bar__actions a").length,
                    paginationGhostCount: document.querySelectorAll(".pagination-bar__actions .ghost-button").length,
                    paginationSecondaryCount: document.querySelectorAll(".pagination-bar__actions .button.button-secondary").length,
                })"""
            )
            assert admin_user_detail_metrics["auditFilterGhostCount"] == 2
            assert admin_user_detail_metrics["auditFilterSecondaryCount"] == 0
            assert admin_user_detail_metrics["paginationAnchorCount"] == admin_user_detail_metrics["paginationGhostCount"] + admin_user_detail_metrics["paginationSecondaryCount"]
            assert admin_user_detail_metrics["paginationSecondaryCount"] == 0

            membership_panel = admin_page.locator("article.card.admin-panel").filter(has_text="Campaign membership")
            membership_panel.locator("#admin-membership-campaign-slug").select_option("linden-pass")
            membership_panel.locator("#admin-membership-role").select_option("player")
            membership_panel.locator("#admin-membership-status").select_option("active")
            membership_panel.get_by_role("button", name="Save membership").click()
            expect(admin_page.get_by_text(re.compile(r"Membership updated: linden-pass -> player"))).to_be_visible(timeout=10000)

            admin_page.locator("#admin-assignment-character-ref").select_option("linden-pass::selene-brook")
            admin_page.get_by_role("button", name="Assign character").click()
            expect(admin_page.get_by_text("Assigned selene-brook in linden-pass")).to_be_visible(timeout=10000)
            expect(admin_page.get_by_text("selene-brook | owner")).to_be_visible()

            admin_user_detail_metrics = admin_page.evaluate(
                """() => ({
                    userDetailCardPanelCount: document.querySelectorAll("article.card.admin-panel").length,
                    legacyUserDetailPanelCount: document.querySelectorAll("article.panel.admin-panel").length,
                    legacyUserCardCount: document.querySelectorAll("article.panel.admin-user-card").length,
                    recentActivityCardCount: Array.from(document.querySelectorAll("article.card.admin-panel"))
                        .filter((node) => {
                            const heading = node.querySelector("h2");
                            return heading?.textContent?.trim() === "Recent activity for this user";
                        }).length,
                    recentActivityPanelHeaderCount: Array.from(document.querySelectorAll("article.card.admin-panel"))
                        .filter((node) => {
                            const heading = node.querySelector("h2");
                            return heading?.textContent?.trim() === "Recent activity for this user";
                        })
                        .reduce((count, node) => count + node.querySelectorAll(".panel-header").length, 0),
                    hasAdminPageWrapper: !!document.querySelector("main.main-shell > .admin-page"),
                    adminItemActionButtonRowCount: document.querySelectorAll(".admin-item-row .admin-item-actions.button-row").length,
                    editLinkClasses: Array.from(document.querySelectorAll(".admin-item-row .admin-item-actions a")).map((el) => ({
                        text: (el.textContent || "").trim(),
                        classes: el.className,
                    })),
                    directChildren: Array.from(document.querySelectorAll("main.main-shell > *")).map((node) => ({
                        tag: node.tagName.toLowerCase(),
                        classes: node.className,
                    })),
                })"""
            )
            assert admin_user_detail_metrics["hasAdminPageWrapper"] is False
            assert admin_user_detail_metrics["directChildren"]
            assert (
                admin_user_detail_metrics["directChildren"][0]["tag"] == "section"
                and "hero" in admin_user_detail_metrics["directChildren"][0]["classes"].split()
                and "compact" in admin_user_detail_metrics["directChildren"][0]["classes"].split()
                and "admin-hero" in admin_user_detail_metrics["directChildren"][0]["classes"].split()
            )
            assert admin_user_detail_metrics["userDetailCardPanelCount"] >= 4
            assert admin_user_detail_metrics["legacyUserDetailPanelCount"] == 0
            assert admin_user_detail_metrics["legacyUserCardCount"] == 0
            assert admin_user_detail_metrics["recentActivityCardCount"] >= 1
            assert admin_user_detail_metrics["recentActivityPanelHeaderCount"] == 0
            assert admin_user_detail_metrics["adminItemActionButtonRowCount"] == 0
            assert len(admin_user_detail_metrics["editLinkClasses"]) >= 2
            assert all(
                item["text"] != "Edit" or re.search(r"\bghost-button\b", item["classes"])
                for item in admin_user_detail_metrics["editLinkClasses"]
            )
            assert any(
                (
                    node["tag"] == "section"
                    and "hero" in node["classes"].split()
                    and "compact" in node["classes"].split()
                    and "admin-hero" in node["classes"].split()
                )
                for node in admin_user_detail_metrics["directChildren"]
            )
            assert any(
                (node["tag"] == "section" and "admin-layout" in node["classes"].split())
                for node in admin_user_detail_metrics["directChildren"]
            )

            mobile_page.goto(f"{base_url}/app-next/admin")
            expect(mobile_page.get_by_role("heading", name="Admin dashboard")).to_be_visible(timeout=10000)
            mobile_layout = mobile_page.evaluate(
                """() => {
                    const countGridTracks = (value) => value.trim().split(/\\s+/).filter(Boolean).length;
                    const main = document.querySelector("main.main-shell");
                    const directChildren = main ? Array.from(main.children) : [];
                    const hero = directChildren.find(
                        (node) =>
                            node.tagName.toLowerCase() === "section"
                            && node.classList.contains("hero")
                            && node.classList.contains("compact")
                            && node.classList.contains("admin-hero"),
                    );
                    const layouts = Array.from(main ? main.querySelectorAll(":scope > .admin-layout") : []);
                    const firstLayout = layouts[0];
                    const items = firstLayout ? Array.from(firstLayout.children) : [];
                    const itemRects = items.map((item) => {
                        const rect = item.getBoundingClientRect();
                        return { left: rect.left, width: rect.width };
                    });
                    const first = itemRects[0];
                    const second = itemRects[1];
                    const filter = document.querySelector(".admin-filter-form");
                    return {
                        innerWidth: window.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        pageWidth: main ? main.getBoundingClientRect().width : 0,
                        maxItemWidth: itemRects.reduce((max, item) => Math.max(max, item.width), 0),
                        layoutCount: layouts.length,
                        heroIsFirstChild: hero && directChildren.length > 0 ? hero === directChildren[0] : false,
                        hasDirectAdminHero: !!hero,
                        hasAdminPageWrapper: !!(main ? main.querySelector(":scope > .admin-page") : null),
                        directChildCount: directChildren.length,
                        firstLayoutStacked: !second || Math.abs((second.left || 0) - (first.left || 0)) <= 4,
                        filterColumns: filter ? countGridTracks(window.getComputedStyle(filter).gridTemplateColumns) : 0,
                    };
                }"""
            )
            assert mobile_layout["hasDirectAdminHero"] is True
            assert mobile_layout["heroIsFirstChild"] is True
            assert mobile_layout["hasAdminPageWrapper"] is False
            assert mobile_layout["directChildCount"] >= 3
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
            hero = page.locator("section.hero.compact.combat-hero")
            expect(hero.get_by_role("heading", name="Combat")).to_be_visible(timeout=10000)
            expect(hero.locator(".article-actions")).to_have_count(0)
            expect(hero.locator(".hero-actions")).to_have_count(0)
            expect(hero.locator('nav[aria-label="DM encounter subview"]')).to_have_count(0)
            expect(hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(page.get_by_role("heading", name="Turn Order")).to_be_visible()
            expect(page.locator(".combat-carousel .compact-header")).to_have_count(0)
            expect(page.locator(".combat-pc-workspace .compact-header")).to_have_count(0)
            carousel = page.locator(".combat-carousel")
            expect(carousel.locator("> .section-heading > div > h2")).to_have_text("Turn Order")
            expect(carousel.locator("> .section-heading .meta")).to_contain_text("Initiative is pinned here")
            expect(carousel.get_by_label("Jump to combatant")).to_be_visible()
            expect(carousel.get_by_role("button", name=re.compile(r"Arden March", re.I))).to_be_visible()
            expect(carousel.get_by_role("button", name=re.compile(r"Clockwork Hound", re.I))).to_be_visible()
            expect(page.get_by_role("heading", name="Combat Character")).to_be_visible(timeout=10000)
            workspace = page.locator(".combat-pc-workspace")
            expect(workspace.locator("> .section-heading h2")).to_be_visible()

            carousel.get_by_role("button", name=re.compile(r"Clockwork Hound", re.I)).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/combat\?combatant=\d+"))
            expect(page.get_by_role("heading", name="Clockwork Hound")).to_be_visible()
            expect(page.get_by_role("heading", name="Combat Character")).to_be_visible()
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
            expect(page.get_by_role("heading", name="DM status")).to_be_visible(timeout=10000)
            combat_nav = page.get_by_role("navigation", name="DM encounter subview")
            expect(combat_nav.get_by_role("button", name="DM status")).to_be_visible()
            expect(combat_nav.get_by_role("button", name="DM status")).to_have_class(re.compile(r"\bbutton-link\b"))
            expect(combat_nav.get_by_role("button", name="Controls")).to_be_visible()
            expect(combat_nav.get_by_role("button", name="Controls")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator(".combat-view-switch")).to_have_count(0)
            expect(page.locator(".combat-carousel .compact-header")).to_have_count(0)
            expect(page.locator(".combat-pc-workspace .compact-header")).to_have_count(0)

            carousel = page.locator(".combat-carousel")
            expect(carousel.locator("> .section-heading > div > h2")).to_have_text("Turn Order")
            expect(carousel.locator("> .section-heading .meta")).to_contain_text("Initiative is pinned here")
            expect(carousel.get_by_label("Jump to combatant")).to_be_visible()
            carousel.get_by_role("button", name=re.compile(r"Clockwork Hound", re.I)).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/combat\?view=status&combatant=\d+"))
            expect(page.locator(".combat-dm-grid .combat-control-card").first.locator(".section-heading h2")).to_have_text(
                "Turn Focus",
            )
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

            combat_nav.get_by_role("button", name="Controls").click()
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
            expect(desktop_page.get_by_role("heading", name="Combat")).to_be_visible(timeout=10000)
            expect(desktop_page.locator(".combat-summary-band")).to_be_visible()
            expect(desktop_page.locator(".combat-carousel")).to_be_visible()
            expect(desktop_page.locator(".combat-selected-snapshot")).to_be_visible()
            expect(desktop_page.locator(".combat-carousel .compact-header")).to_have_count(0)
            expect(desktop_page.locator(".combat-pc-workspace .compact-header")).to_have_count(0)
            expect(desktop_page.locator(".combat-carousel > .section-heading > div > h2")).to_have_text("Turn Order")
            expect(desktop_page.locator(".combat-carousel > .section-heading .meta")).to_contain_text("Initiative is pinned here")
            expect(desktop_page.locator(".combat-carousel").get_by_label("Jump to combatant")).to_be_visible()
            expect(desktop_page.locator(".combat-pc-workspace > .section-heading > div > h2")).to_be_visible()
            player_metrics = desktop_page.evaluate(
                """() => {
                    const main = document.querySelector("main.main-shell") || document.querySelector("main");
                    const directChildren = main ? Array.from(main.querySelectorAll(":scope > *")) : [];
                    const hero = main ? main.querySelector(":scope > section.hero.compact.combat-hero") : null;
                    const heroHeading = hero?.querySelector("h1") || null;
                    const legacyRoute = main ? main.querySelector(":scope > .combat-page") : null;
                    const legacyPanelRoute = main ? main.querySelector(":scope > .panel.combat-page") : null;
                    const summary = document.querySelector(".combat-summary-band");
                    const summaryCard = document.querySelector(".combat-summary-band article");
                    const carousel = document.querySelector(".combat-carousel");
                    const combatant = document.querySelector(".combatant-card");
                    const snapshot = document.querySelector(".combat-selected-snapshot");
                    const snapshotHeading = snapshot?.querySelector(":scope > .section-heading > div > h2") || null;
                    const snapshotKicker = snapshot?.querySelector(":scope > .section-heading > div > .card-kicker") || null;
                    const snapshotBadges = snapshot
                        ? Array.from(snapshot.querySelectorAll(":scope > .section-heading .combatant-badges .combat-badge"))
                        : [];
                    const heroIndex = hero ? directChildren.indexOf(hero) : -1;
                    const summaryIndex = summary ? directChildren.indexOf(summary) : -1;
                    const carouselIndex = carousel ? directChildren.indexOf(carousel) : -1;
                    const snapshotIndex = snapshot ? directChildren.indexOf(snapshot) : -1;
                    const maxDirectChildWidth = directChildren.length
                        ? directChildren.reduce((width, child) => Math.max(width, child.getBoundingClientRect().width), 0)
                        : 0;
                    return {
                        firstDirectChildIsHero: hero && directChildren[0] === hero,
                        heroSize: heroHeading ? Number.parseFloat(window.getComputedStyle(heroHeading).fontSize) : 0,
                        legacyRoutePresent: Boolean(legacyRoute),
                        legacyPanelRoutePresent: Boolean(legacyPanelRoute),
                        heroIndex: heroIndex,
                        summaryIndex: summaryIndex,
                        carouselIndex: carouselIndex,
                        snapshotIndex: snapshotIndex,
                        maxDirectChildWidth: maxDirectChildWidth,
                        childCount: directChildren.length,
                        summaryRadius: summary ? Number.parseFloat(window.getComputedStyle(summary).borderRadius) : 0,
                        summaryCardRadius: summaryCard ? Number.parseFloat(window.getComputedStyle(summaryCard).borderRadius) : 0,
                        carouselRadius: carousel ? Number.parseFloat(window.getComputedStyle(carousel).borderRadius) : 0,
                        combatantRadius: combatant ? Number.parseFloat(window.getComputedStyle(combatant).borderRadius) : 0,
                        snapshotRadius: snapshot ? Number.parseFloat(window.getComputedStyle(snapshot).borderRadius) : 0,
                        snapshotHeadingText: snapshotHeading ? snapshotHeading.textContent.trim() : "",
                        snapshotKickerText: snapshotKicker ? snapshotKicker.textContent.trim() : "",
                        snapshotBadgeCount: snapshotBadges.length,
                        snapshotBadgeTexts: snapshotBadges.map((badge) => badge.textContent.trim()),
                        snapshotBareHeadingCount: snapshot
                            ? snapshot.querySelectorAll(":scope > .section-heading > div > h3").length
                            : 0,
                    };
                }"""
            )
            assert player_metrics["firstDirectChildIsHero"] is True
            assert player_metrics["heroIndex"] == 0
            assert player_metrics["summaryIndex"] > player_metrics["heroIndex"]
            assert player_metrics["carouselIndex"] > player_metrics["heroIndex"]
            assert player_metrics["snapshotIndex"] > player_metrics["carouselIndex"]
            assert player_metrics["legacyRoutePresent"] is False
            assert player_metrics["legacyPanelRoutePresent"] is False
            assert player_metrics["heroSize"] >= 32
            assert player_metrics["maxDirectChildWidth"] <= 1280 + 1
            assert player_metrics["childCount"] >= 3
            assert player_metrics["summaryRadius"] >= 20
            assert player_metrics["summaryCardRadius"] >= 16
            assert player_metrics["carouselRadius"] >= 20
            assert player_metrics["combatantRadius"] >= 16
            assert player_metrics["snapshotRadius"] >= 20
            assert player_metrics["snapshotHeadingText"]
            assert player_metrics["snapshotKickerText"] in {"Combat workspace", "Combat snapshot"}
            assert player_metrics["snapshotBadgeCount"] >= 2
            assert any(text.startswith("Round ") for text in player_metrics["snapshotBadgeTexts"])
            assert any(text.startswith("Turn ") for text in player_metrics["snapshotBadgeTexts"])
            assert player_metrics["snapshotBareHeadingCount"] == 0
            expect(desktop_page.locator(".combat-view-switch")).to_have_count(0)

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=status")
            expect(desktop_page.get_by_role("heading", name="DM status")).to_be_visible(timeout=10000)
            expect(desktop_page.get_by_role("navigation", name="DM encounter subview")).to_be_visible()
            expect(desktop_page.locator(".combat-dm-grid .combat-control-card").first).to_be_visible()
            status_metrics = desktop_page.evaluate(
                """() => {
                    const switcher = document.querySelector('nav[aria-label="DM encounter subview"]');
                    const dmStatus = Array.from(switcher?.querySelectorAll("button") || []).find(
                      (button) => button.textContent?.trim() === "DM status"
                    );
                    const controls = Array.from(switcher?.querySelectorAll("button") || []).find(
                      (button) => button.textContent?.trim() === "Controls"
                    );
                    const controlCard = document.querySelector(".combat-dm-grid .combat-control-card");
                    const condition = document.querySelector(".combat-condition-chip");
                    const grid = document.querySelector(".combat-dm-grid");
                    return {
                        dmStatusClass: dmStatus ? dmStatus.className : "",
                        controlsClass: controls ? controls.className : "",
                        controlRadius: controlCard ? Number.parseFloat(window.getComputedStyle(controlCard).borderRadius) : 0,
                        conditionRadius: condition ? Number.parseFloat(window.getComputedStyle(condition).borderRadius) : 16,
                        dmGridColumns: grid ? window.getComputedStyle(grid).gridTemplateColumns.split(" ").length : 0,
                    };
                }"""
            )
            assert "button-link" in status_metrics["dmStatusClass"].split(" ")
            assert "ghost-button" in status_metrics["controlsClass"].split(" ")
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
                        const main = document.querySelector("main.main-shell") || document.querySelector("main");
                        const directChildren = main ? Array.from(main.querySelectorAll(":scope > *")) : [];
                        const hero = main ? main.querySelector(":scope > section.hero.compact.combat-hero") : null;
                        const switcher = hero
                          ? hero.querySelector('nav[aria-label="DM encounter subview"]')
                          : null;
                        const carousel = document.querySelector(".combat-carousel");
                        const carouselTrack = document.querySelector(".combat-carousel-track");
                        const directChildWidths = directChildren.length
                            ? directChildren.reduce((width, child) => Math.max(width, child.getBoundingClientRect().width), 0)
                            : 0;
                        return {
                            innerWidth: window.innerWidth,
                            scrollWidth: document.documentElement.scrollWidth,
                            maxDirectChildWidth: directChildWidths,
                            firstDirectChildIsHero: hero && directChildren[0] === hero,
                            legacyRoutePresent: Boolean(main && main.querySelector(":scope > .combat-page")),
                            switchWidth: switcher ? switcher.getBoundingClientRect().width : 0,
                            carouselWidth: carousel ? carousel.getBoundingClientRect().width : 0,
                            trackClientWidth: carouselTrack ? carouselTrack.getBoundingClientRect().width : 0,
                        };
                    }"""
                )
                assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"] + 1
                assert mobile_metrics["legacyRoutePresent"] is False
                assert mobile_metrics["firstDirectChildIsHero"] is True
                assert mobile_metrics["maxDirectChildWidth"] <= mobile_metrics["innerWidth"] + 1
                assert mobile_metrics["switchWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["carouselWidth"] <= mobile_metrics["innerWidth"]
                assert mobile_metrics["trackClientWidth"] <= mobile_metrics["innerWidth"]
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
            browser.close()


@pytest.mark.skip(reason="Combat snapshot heading-shell parity assertions are currently suspended with Gen2 snapshot parity work.")
def test_gen2_combat_selected_snapshot_heading_shell_smoke(
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
            page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=player")

            expect(page.locator(".combat-selected-snapshot")).to_be_visible(timeout=10000)
            expect(page.locator(".combat-selected-snapshot > .section-heading > div > .card-kicker")).to_be_visible()
            expect(page.locator(".combat-selected-snapshot > .section-heading > div > .card-kicker")).to_have_text(
                re.compile(r"Combat (workspace|snapshot)")
            )
            expect(page.locator(".combat-selected-snapshot > .section-heading > div > h2")).to_be_visible()
            expect(page.locator(".combat-selected-snapshot > .section-heading > .combatant-badges")).to_be_visible()

            badge_count = page.locator(".combat-selected-snapshot .combatant-badges .combat-badge").count()
            assert badge_count >= 2
            badge_texts = page.locator(".combat-selected-snapshot .combatant-badges .combat-badge").all_inner_texts()
            badge_class_names = page.locator(".combat-selected-snapshot .combatant-badges .combat-badge").evaluate_all(
                "(nodes) => nodes.map((node) => node.className)"
            )
            assert any(text.strip().startswith("Round ") for text in badge_texts)
            assert any(text.strip().startswith("Turn ") for text in badge_texts)
            assert all("combat-badge" in classes for classes in badge_class_names)
            assert page.locator(".combat-selected-snapshot > .section-heading > div > h3").count() == 0
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
                    const overviewCard = document.querySelector(".wiki-overview-card");
                    const overviewTitle = document.querySelector(".wiki-overview-card > h2");
                    const overviewBody = document.querySelector(".wiki-overview-card .article-body");
                    const browse = document.querySelector(".wiki-section-browse");
                    const overviewBodyFirstChild = overviewBody ? overviewBody.firstElementChild : null;
                    const overviewBodyRect = overviewBody ? overviewBody.getBoundingClientRect() : null;
                    const overviewBodyFirstChildRect = overviewBodyFirstChild
                        ? overviewBodyFirstChild.getBoundingClientRect()
                        : null;
                    return {
                        routeShadow: route ? window.getComputedStyle(route).boxShadow : "",
                        heroDisplay: hero ? window.getComputedStyle(hero).display : "",
                        overviewDisplay: overviewCard ? window.getComputedStyle(overviewCard).display : "",
                        overviewTitleMarginTop: overviewTitle
                            ? Number.parseFloat(window.getComputedStyle(overviewTitle).marginTop)
                            : -1,
                        overviewTitleMarginBottom: overviewTitle
                            ? Number.parseFloat(window.getComputedStyle(overviewTitle).marginBottom)
                            : -1,
                        overviewBorder: overviewBody ? window.getComputedStyle(overviewBody).borderTopWidth : "",
                        overviewBodyFirstChildMarginTop: overviewBodyFirstChild
                            ? Number.parseFloat(window.getComputedStyle(overviewBodyFirstChild).marginTop)
                            : -1,
                        overviewBodyFirstChildGap:
                            overviewBodyRect && overviewBodyFirstChildRect
                            ? Math.round((overviewBodyFirstChildRect.top - overviewBodyRect.top) * 100) / 100
                            : -1,
                        browseRadius: browse ? Number.parseFloat(window.getComputedStyle(browse).borderRadius) : 0,
                    };
                }"""
            )
            assert home_metrics["routeShadow"] == "none"
            assert home_metrics["heroDisplay"] == "grid"
            assert home_metrics["overviewDisplay"] == "block"
            assert home_metrics["overviewTitleMarginTop"] == 0
            assert home_metrics["overviewTitleMarginBottom"] == 0
            assert home_metrics["overviewBorder"] == "0px"
            assert home_metrics["overviewBodyFirstChildMarginTop"] == 0
            assert home_metrics["overviewBodyFirstChildGap"] == 0
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
            expect(page.get_by_role("heading", level=1, name="Arden March", exact=True)).to_be_visible(timeout=10000)
            expect(page.locator("article.character-read-shell.character-sheet.card")).to_be_visible()
            expect(page.locator("header.character-header")).to_be_visible()
            expect(page.locator("section.panel.character-read-shell")).to_have_count(0)
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
            expect(page.get_by_role("heading", level=1, name="Arden March", exact=True)).to_be_visible(timeout=10000)

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
            expect(player_page.get_by_role("heading", level=1, name="Arden March", exact=True)).to_be_visible(timeout=10000)
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
            expect(page.get_by_role("heading", level=1, name="Arden March", exact=True)).to_be_visible(timeout=10000)
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
            expect(desktop_page.locator("main > section.hero.compact.character-roster-hero")).to_be_visible()
            assert desktop_page.locator(".character-roster-page").count() == 0
            expect(desktop_page.locator("main > .panel, main > .panel-nested")).to_have_count(0)
            expect(desktop_page.locator(".character-roster-tools")).to_be_visible()
            expect(desktop_page.locator(".character-roster-grid .character-card").first).to_be_visible()
            roster_metrics = desktop_page.evaluate(
                """() => {
                    const main = document.querySelector("main");
                    const hero = document.querySelector(".character-roster-hero h1");
                    const tools = document.querySelector(".character-roster-tools");
                    const cardStat = document.querySelector(".character-card__stats article");
                    const portrait = document.querySelector(".character-card__portrait");
                    const search = document.querySelector(".character-roster-search");
                    const nextAfterTools = tools ? tools.nextElementSibling : null;
                    const children = main ? Array.from(main.children) : [];
                    const heroIndex = children.indexOf(document.querySelector(".character-roster-hero") || null);
                    const toolsIndex = children.indexOf(document.querySelector(".character-roster-tools") || null);
                    return {
                        heroIndex,
                        toolsIndex,
                        nextAfterToolsClassList: nextAfterTools ? Array.from(nextAfterTools.classList) : [],
                        nextAfterToolsTag: nextAfterTools ? nextAfterTools.tagName.toLowerCase() : "",
                        mainScrollWidth: main ? document.documentElement.scrollWidth : 0,
                        mainInnerWidth: window.innerWidth,
                        heroSize: hero ? Number.parseFloat(window.getComputedStyle(hero).fontSize) : 0,
                        toolsRadius: tools ? Number.parseFloat(window.getComputedStyle(tools).borderRadius) : 0,
                        cardStatRadius: cardStat ? Number.parseFloat(window.getComputedStyle(cardStat).borderRadius) : 0,
                        portraitRadius: portrait ? Number.parseFloat(window.getComputedStyle(portrait).borderRadius) : 0,
                        searchColumns: search ? window.getComputedStyle(search).gridTemplateColumns.split(" ").length : 0,
                    };
                }"""
            )
            assert roster_metrics["heroIndex"] == 0
            assert roster_metrics["toolsIndex"] > roster_metrics["heroIndex"]
            assert (
                "character-roster-grid" in roster_metrics["nextAfterToolsClassList"]
                or (
                    "card" in roster_metrics["nextAfterToolsClassList"]
                    and roster_metrics["nextAfterToolsTag"] == "section"
                )
            )
            assert roster_metrics["mainScrollWidth"] <= roster_metrics["mainInnerWidth"] + 1
            assert roster_metrics["heroSize"] >= 32
            assert roster_metrics["toolsRadius"] >= 20
            assert roster_metrics["cardStatRadius"] >= 16
            assert roster_metrics["portraitRadius"] >= 8
            assert roster_metrics["searchColumns"] >= 2

            desktop_page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/arden-march")
            expect(desktop_page.get_by_role("heading", level=1, name="Arden March", exact=True)).to_be_visible(timeout=10000)
            expect(desktop_page.locator("article.character-read-shell.character-sheet.card")).to_be_visible()
            expect(desktop_page.locator("header.character-header")).to_be_visible()
            expect(desktop_page.locator("section.panel.character-read-shell")).to_have_count(0)
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
                        const route = document.querySelector(".character-roster-hero, .character-read-shell");
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
            create_hero = page.locator("main > section.hero.compact.character-authoring-hero")
            expect(create_hero).to_be_visible(timeout=10000)
            expect(create_hero.locator(".article-actions")).to_have_count(0)
            expect(create_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(create_hero.locator(".article-actions.character-authoring-hero-actions")).to_have_count(0)
            expect(create_hero.locator(".hero-actions.character-authoring-hero-actions")).to_have_count(1)
            expect(page.locator("main > .character-authoring-page.character-authoring-create-page")).to_have_count(0)
            expect(page.get_by_role("heading", name="Create Xianxia Character")).to_be_visible(timeout=10000)
            expect(create_hero.get_by_role("link", name="Back to roster")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(create_hero.get_by_role("link", name="Flask create")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(create_hero.get_by_role("link", name="Import existing")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.get_by_role("link", name="Flask create")).to_be_visible()
            expect(page.locator("main .character-authoring-layout > .sidebar.character-authoring-sidebar")).to_be_visible()
            assert page.locator("main .character-authoring-sidebar > .card.sidebar-card").count() >= 1
            assert page.locator("aside.panel.character-authoring-sidebar").count() == 0
            for field_name, value in create_values.items():
                page.locator(f"[name='{field_name}']").fill(value)
            for field_name, value in create_selects.items():
                page.locator(f"[name='{field_name}']").select_option(value)
            page.get_by_role("button", name="Create character").click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/characters/browser-gen2-crane$"), timeout=10000)
            expect(page.get_by_role("heading", level=1, name="Browser Gen2 Crane", exact=True)).to_be_visible(timeout=10000)
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
            cultivation_hero = page.locator("main > section.hero.compact.character-cultivation-hero.character-authoring-hero")
            expect(cultivation_hero).to_be_visible(timeout=10000)
            expect(cultivation_hero.locator(".article-actions")).to_have_count(0)
            expect(cultivation_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(cultivation_hero.locator("a.ghost-button[href='#xianxia-cultivation-realm-ascension']")).to_have_count(1)
            expect(cultivation_hero.get_by_role("link", name="Realm Ascension")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator("main > .page.campaign-page.character-authoring-page")).to_have_count(0)
            page.get_by_label("Insight available").fill("2")
            page.get_by_label("Insight spent").fill("1")
            page.get_by_role("button", name="Save Insight").click()
            expect(page.get_by_text("Insight counters saved.")).to_be_visible(timeout=10000)
            expect(page.locator("#xianxia-cultivation-insight .glance-card", has_text="Available").get_by_text("2")).to_be_visible()

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/edit")
            expect(page.get_by_role("heading", name="Edit Browser Gen2 Crane")).to_be_visible(timeout=10000)
            edit_hero = page.locator("main > section.hero.compact.character-authoring-hero")
            expect(edit_hero).to_be_visible(timeout=10000)
            expect(edit_hero.locator(".article-actions")).to_have_count(0)
            expect(edit_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(edit_hero.get_by_role("link", name="Back to sheet")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator("main > .page.campaign-page.character-authoring-page")).to_have_count(0)

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/level-up")
            expect(page.get_by_role("heading", name="Level Up Browser Gen2 Crane")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Level-Up Is Not Available In Gen2")).to_be_visible()
            level_up_hero = page.locator("main > section.hero.compact.character-authoring-hero")
            expect(level_up_hero).to_be_visible(timeout=10000)
            expect(level_up_hero.locator(".article-actions")).to_have_count(0)
            expect(level_up_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(level_up_hero.get_by_role("link", name="Back to sheet")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator("main > .page.campaign-page.character-authoring-page")).to_have_count(0)
            expect(page.get_by_role("link", name="Cultivation")).to_be_visible()

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/retraining")
            expect(page.get_by_role("heading", name="Retrain Browser Gen2 Crane")).to_be_visible(timeout=10000)
            expect(page.get_by_role("heading", name="Retraining Is Not Available In Gen2")).to_be_visible()
            retraining_hero = page.locator("main > section.hero.compact.character-authoring-hero")
            expect(retraining_hero).to_be_visible(timeout=10000)
            expect(retraining_hero.locator(".article-actions")).to_have_count(0)
            expect(retraining_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(retraining_hero.get_by_role("link", name="Back to sheet")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(retraining_hero.get_by_role("link", name="Advanced Editor")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator("main > .page.campaign-page.character-authoring-page")).to_have_count(0)
            expect(page.get_by_role("link", name="Cultivation")).to_be_visible()

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/characters/browser-gen2-crane/progression-repair")
            expect(page.get_by_role("heading", name="Prepare Browser Gen2 Crane For Native Level-Up")).to_be_visible(
                timeout=10000
            )
            expect(page.get_by_role("heading", name="Progression Repair Is Not Available In Gen2")).to_be_visible()
            progression_hero = page.locator("main > section.hero.compact.character-authoring-hero")
            expect(progression_hero).to_be_visible(timeout=10000)
            expect(progression_hero.locator(".article-actions")).to_have_count(0)
            expect(progression_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(progression_hero.get_by_role("link", name="Back to sheet")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(progression_hero.get_by_role("link", name="Flask repair")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator("main > .page.campaign-page.character-authoring-page")).to_have_count(0)
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
            expect(page.locator("main > section.hero.compact.character-authoring-hero")).to_be_visible(timeout=10000)
            import_hero = page.locator("main > section.hero.compact.character-authoring-hero")
            expect(import_hero.locator(".article-actions")).to_have_count(0)
            expect(import_hero.locator("a.button.button-secondary")).to_have_count(0)
            expect(import_hero.locator(".article-actions.character-authoring-hero-actions")).to_have_count(0)
            expect(import_hero.locator(".hero-actions.character-authoring-hero-actions")).to_have_count(1)
            expect(import_hero.get_by_role("link", name="Back to roster")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(import_hero.get_by_role("link", name="Flask import")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(page.locator("main > .character-authoring-page.character-authoring-manual-import-page")).to_have_count(0)
            expect(page.get_by_role("heading", name="Import Existing Xianxia Character")).to_be_visible(timeout=10000)
            expect(page.get_by_role("link", name="Flask import")).to_be_visible()
            expect(page.locator("main .character-authoring-layout > .sidebar.character-authoring-sidebar")).to_be_visible()
            assert page.locator("main .character-authoring-sidebar > .card.sidebar-card").count() >= 1
            assert page.locator("aside.panel.character-authoring-sidebar").count() == 0
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
            expect(page.get_by_role("heading", level=1, name="Browser Imported Lotus", exact=True)).to_be_visible(timeout=10000)
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

                expect(page.locator("section.systems-browse-index-page")).to_have_count(0)
                expect(page.locator(".systems-browse-page")).to_have_count(0)
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero")).to_be_visible(timeout=10_000)
                expect(page.locator("main.main-shell > .systems-browse-grid.page-layout")).to_be_visible()
                expect(page.locator(".systems-search-band")).to_be_visible()
                expect(page.locator(".systems-browse-sidebar")).to_be_visible()
                expect(page.get_by_role("heading", name="Systems", exact=True)).to_be_visible(timeout=10_000)
                expect(page.get_by_role("heading", name="Search Results")).to_be_visible()
                expect(page.locator(".campaign-nav-link").get_by_text("Systems")).to_be_visible()
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero .article-actions")).to_have_count(0)
                index_hero_actions = page.locator(
                    "main.main-shell > section.hero.compact.systems-hero .hero-actions.systems-hero-actions"
                )
                expect(index_hero_actions).to_have_count(1)
                expect(index_hero_actions).to_have_class(re.compile(r"\bhero-actions\b.*\bsystems-hero-actions\b"))
                expect(index_hero_actions.get_by_role("link", name="Systems settings")).to_be_visible()
                expect(index_hero_actions.get_by_role("link", name="Systems settings")).to_have_class(re.compile(r"\bghost-button\b"))
                expect(
                    page.locator("main.main-shell > section.hero.compact.systems-hero").get_by_role("link", name="Flask view")
                ).to_have_count(0)
                assert page.evaluate(
                    """() => {
                        const selectors = [
                            'main.main-shell > section.hero.compact.systems-hero',
                            'main.main-shell > .systems-browse-grid.page-layout',
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
                root_metrics = page.evaluate(
                    """() => {
                        const main = document.querySelector('main.main-shell');
                        const hero = main ? main.querySelector(':scope > section.hero.compact.systems-hero') : null;
                        const layout = main ? main.querySelector(':scope > .systems-browse-grid.page-layout') : null;
                        const children = main ? Array.from(main.children) : [];
                        const heroRect = hero ? hero.getBoundingClientRect() : null;
                        const layoutRect = layout ? layout.getBoundingClientRect() : null;
                        return {
                            heroBeforeLayout: Boolean(hero && layout && children.indexOf(hero) < children.indexOf(layout)),
                            heroLayoutGap: heroRect && layoutRect ? Math.round(layoutRect.top - heroRect.bottom) : -1,
                        };
                    }"""
                )
                assert root_metrics["heroBeforeLayout"] is True
                assert root_metrics["heroLayoutGap"] >= 12
                if viewport["width"] >= 1024:
                    assert layout_columns >= 2
                else:
                    assert layout_columns == 1

                page.get_by_role("link", name=entry_title).click()
                expect(page).to_have_url(
                    re.compile(rf"/app-next/campaigns/linden-pass/systems/entries/{re.escape(entry_slug)}$"),
                    timeout=5000,
                )
                expect(page.locator(".systems-entry-shell")).to_have_count(0)
                expect(page.locator(".systems-entry-page")).to_have_count(0)
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero")).to_be_visible(timeout=10_000)
                expect(page.locator("main.main-shell > .page-layout")).to_be_visible()
                expect(page.locator(".systems-entry-band")).to_be_visible()
                expect(page.locator(".systems-entry-sidebar")).to_be_visible()
                expect(page.locator(".systems-sidebar-card").first).to_be_visible()
                expect(page.locator(".systems-entry-navigation")).to_be_visible()
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero h1")).to_have_text(entry_title, timeout=10_000)
                expect(page.locator(".systems-entry-band > h1")).to_have_count(0)
                expect(page.get_by_role("heading", name="Entry Metadata")).to_be_visible()
                expect(page.get_by_role("link", name="Source page")).to_be_visible()
                expect(page.get_by_role("link", name="Source category")).to_be_visible()
                expect(page.get_by_text(entry_body)).to_be_visible()
                expect(page.get_by_role("link", name="Manage campaign override")).to_be_visible()

                hero_position_before_layout = page.evaluate(
                    """() => {
                        const main = document.querySelector('main.main-shell');
                        if (!main) {
                            return false;
                        }
                        const hero = main.querySelector(':scope > .hero.compact.systems-hero');
                        const layout = main.querySelector(':scope > .page-layout');
                        if (!hero || !layout) {
                            return false;
                        }
                        const children = Array.from(main.children);
                        return children.indexOf(hero) < children.indexOf(layout);
                    }"""
                )
                assert hero_position_before_layout

                page.get_by_role("link", name="Source category").click()

                expect(page.locator(".systems-source-category-page")).to_have_count(0)
                expect(page.locator(".systems-browse-page")).to_have_count(0)
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero")).to_be_visible(timeout=10_000)
                expect(page.locator("main.main-shell > .systems-browse-grid.page-layout")).to_be_visible()
                expect(page.locator(".systems-category-band")).to_be_visible()
                expect(page.locator('section.hero.compact.systems-hero .eyebrow', has_text="Systems source category")).to_be_visible()
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero .article-actions")).to_have_count(0)
                category_hero_actions = page.locator(
                    "main.main-shell > section.hero.compact.systems-hero .hero-actions.systems-hero-actions"
                )
                expect(category_hero_actions).to_have_count(1)
                expect(category_hero_actions).to_have_class(re.compile(r"\bhero-actions\b.*\bsystems-hero-actions\b"))
                expect(category_hero_actions.get_by_role("link", name="Systems settings")).to_be_visible()
                expect(category_hero_actions.get_by_role("link", name="Systems settings")).to_have_class(re.compile(r"\bghost-button\b"))
                expect(
                    page.locator("main.main-shell > section.hero.compact.systems-hero").get_by_role("link", name="Flask view")
                ).to_have_count(0)
                expect(
                    page.locator("main.main-shell > section.hero.compact.systems-hero").get_by_role("link", name="Source")
                ).to_have_count(0)
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
                            'main.main-shell > section.hero.compact.systems-hero',
                            'main.main-shell > .systems-browse-grid.page-layout',
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

                category_url = page.url
                source_match = re.search(r"/systems/sources/(?P<source_id>.+?)/types/", category_url)
                assert source_match
                source_slug = source_match.group("source_id")
                page.goto(f"{base_url}/app-next/campaigns/linden-pass/systems/sources/{source_slug}")

                expect(page.locator(".systems-source-page")).to_have_count(0)
                expect(page.locator(".systems-browse-page")).to_have_count(0)
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero")).to_be_visible(timeout=10_000)
                expect(page.locator("main.main-shell > .systems-browse-grid.page-layout")).to_be_visible()
                expect(page.locator(".systems-source-band")).to_be_visible()
                expect(page.locator('section.hero.compact.systems-hero .eyebrow', has_text="Systems source")).to_be_visible()
                expect(page.locator("main.main-shell > section.hero.compact.systems-hero .article-actions")).to_have_count(0)
                source_hero_actions = page.locator(
                    "main.main-shell > section.hero.compact.systems-hero .hero-actions.systems-hero-actions"
                )
                expect(source_hero_actions).to_have_count(1)
                expect(source_hero_actions).to_have_class(re.compile(r"\bhero-actions\b.*\bsystems-hero-actions\b"))
                expect(source_hero_actions.get_by_role("link", name="Systems settings")).to_be_visible()
                expect(source_hero_actions.get_by_role("link", name="Systems settings")).to_have_class(re.compile(r"\bghost-button\b"))
                expect(
                    page.locator("main.main-shell > section.hero.compact.systems-hero").get_by_role("link", name="Flask view")
                ).to_have_count(0)
                expect(
                    page.locator("main.main-shell > section.hero.compact.systems-hero").get_by_role("link", name="Systems")
                ).to_have_count(0)
                expect(page.get_by_role("heading", name="Browse This Source")).to_be_visible()
                expect(page).to_have_url(
                    re.compile(r"/app-next/campaigns/linden-pass/systems/sources/.+$"),
                    timeout=5_000,
                )
                expect(page.locator(".systems-browse-sidebar")).to_be_visible()
                assert page.evaluate(
                    """() => {
                        const selectors = [
                            'main.main-shell > section.hero.compact.systems-hero',
                            'main.main-shell > .systems-browse-grid.page-layout',
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
            page.locator(".pane-visible").get_by_label("Message").fill(chat_draft)

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
            expect(session_pane.get_by_label("Message")).to_have_value(chat_draft)
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
    ("lane", "lede", "active_label"),
    [
        ("", "DM-side statblocks for Combat NPC seeding.", "Statblocks"),
        ("staged-articles", "Session reveal article prep.", "Staged Articles"),
        ("conditions", "Custom combat conditions.", "Conditions"),
        ("player-wiki", "Published player wiki page management.", "Player Wiki"),
        ("systems", "Systems policy, custom entries, imports, and history.", "Systems"),
    ],
)
def test_gen2_dm_content_browser_visual_parity_smoke(
    frontend_gen2_session_live_server,
    users,
    lane: str,
    lede: str,
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
            dm_content_response = page.request.get(f"{base_url}/api/v1/campaigns/linden-pass/dm-content")
            assert dm_content_response.status == 200
            dm_content_payload = dm_content_response.json()
            dm_content_counts = dm_content_payload.get("subpage_counts")
            for viewport in (
                {"width": 1280, "height": 900},
                {"width": 390, "height": 900},
            ):
                page.set_viewport_size(viewport)
                page.goto(url)

                page_hero = page.locator("main > section.hero.compact.dm-content-hero")
                expect(page_hero).to_be_visible(timeout=10000)
                expect(page_hero.locator("p.eyebrow")).to_have_text("DM content")
                expect(page_hero.get_by_role("heading", name="DM Content")).to_be_visible(timeout=10000)
                expect(page_hero.locator("p.lede")).to_have_text(re.compile(f"^{re.escape(lede)}$"))
                expect(page_hero.get_by_role("link", name="Back to list")).to_have_count(0)
                expect(page_hero.locator(".article-actions")).to_have_count(0)
                expect(page_hero.locator(".pill")).to_have_count(0)
                dm_content_nav = page.locator(".dm-content-subpage-nav")
                expect(dm_content_nav).to_be_visible()
                expect(page.locator(".dm-content-gen2-links")).to_have_count(0)
                assert page.locator("main > .dm-content-gen2-page").count() == 0
                assert page.locator("main > .panel-nested").count() == 0
                assert page.locator(".dm-content-staged-grid > .panel-nested").count() == 0
                assert page.locator(".dm-content-systems-lane > .panel-nested").count() == 0
                content_selector = ".dm-content-systems-lane" if lane == "systems" else ".dm-content-staged-grid"
                assert page.locator(f"{content_selector} > .card .panel-header").count() == 0
                if lane == "":
                    expect(page.get_by_role("heading", name="Create statblock")).to_be_visible()
                    expect(page.get_by_role("heading", name="Statblock library")).to_be_visible()
                elif lane == "staged-articles":
                    expect(page.get_by_role("heading", name="Stage session articles")).to_be_visible()
                    expect(page.get_by_role("heading", name="Session reveal queue")).to_be_visible()
                elif lane == "conditions":
                    expect(page.get_by_role("heading", name="Create condition")).to_be_visible()
                    expect(page.get_by_role("heading", name="Custom conditions")).to_be_visible()
                elif lane == "player-wiki":
                    expect(page.get_by_role("heading", name="Create player wiki page")).to_be_visible()
                    expect(page.get_by_role("heading", name="Player wiki pages")).to_be_visible()
                elif lane == "systems":
                    expect(page.get_by_role("heading", name="Source Enablement")).to_be_visible(timeout=10000)
                    expect(page.get_by_role("heading", name="Entry Overrides")).to_be_visible()
                    expect(page.get_by_role("heading", name="Custom Entries")).to_be_visible()
                    expect(page.get_by_role("heading", name="Shared Source Imports")).to_be_visible()
                    expect(page.get_by_role("heading", name="Import-Run History")).to_be_visible()

                expect(dm_content_nav.get_by_role("link", name="Statblocks")).to_be_visible()
                expect(dm_content_nav.get_by_role("link", name="Staged Articles")).to_be_visible()
                expect(dm_content_nav.get_by_role("link", name="Conditions")).to_be_visible()
                expect(dm_content_nav.get_by_role("link", name="Player Wiki")).to_be_visible()
                expect(dm_content_nav.get_by_role("link", name="Systems")).to_be_visible()
                expect(dm_content_nav.get_by_role("link", name="Session DM")).to_have_count(0)
                for label in ("Statblocks", "Staged Articles", "Conditions", "Player Wiki", "Systems"):
                    link = dm_content_nav.get_by_role("link", name=label)
                    expect(link).to_be_visible()
                    expect(link.locator("span.meta-badge")).to_be_visible()
                    expect(link.locator("span").first).to_have_text(label)
                    expect(link.locator("span.meta-badge")).to_have_text(re.compile(r"^\d+$"))
                if dm_content_counts is not None:
                    expected_counts = {
                        "Statblocks": dm_content_counts["statblocks"],
                        "Staged Articles": dm_content_counts["staged_articles"],
                        "Conditions": dm_content_counts["conditions"],
                        "Player Wiki": dm_content_counts["player_wiki"],
                        "Systems": dm_content_counts["systems"],
                    }
                    for label, expected_count in expected_counts.items():
                        assert isinstance(expected_count, int)
                        expect(dm_content_nav.get_by_role("link", name=label).locator("span.meta-badge")).to_have_text(
                            str(expected_count),
                        )
                expect(dm_content_nav.get_by_role("link", name=active_label)).to_have_class(
                    re.compile(r"\bbutton-link\b")
                )
                for label in ("Statblocks", "Staged Articles", "Conditions", "Player Wiki", "Systems"):
                    if label == active_label:
                        continue
                    expect(dm_content_nav.get_by_role("link", name=label)).to_have_class(
                        re.compile(r"\bghost-button\b")
                    )

                route_metrics = page.evaluate(
                    """() => {
                        const main = document.querySelector('main.main-shell') || document.querySelector('main');
                        if (!main) {
                            return false;
                        }
                        const directChildren = Array.from(main.querySelectorAll(':scope > *'));
                        const hero = main.querySelector(':scope > section.hero.compact.dm-content-hero');
                        const nav = hero ? hero.querySelector('.dm-content-subpage-nav') : null;
                        const content = document.querySelector('.dm-content-staged-grid') || document.querySelector('.dm-content-systems-lane');
                        const legacyRoutePresent = Boolean(main.querySelector(':scope > .dm-content-gen2-page'));
                        if (!hero) {
                            return false;
                        }
                        return {
                            firstDirectChildIsHero: hero === directChildren[0],
                            heroIndex: directChildren.indexOf(hero),
                            navInsideHero: Boolean(hero && nav),
                            contentIndex: content ? directChildren.indexOf(content) : -1,
                            maxDirectChildWidth: directChildren.length
                                ? Math.ceil(Math.max(...directChildren.map((node) => node.getBoundingClientRect().width)))
                                : 0,
                            legacyRoutePresent,
                        };
                    }""",
                )
                assert route_metrics is not False
                assert route_metrics["firstDirectChildIsHero"] is True
                assert route_metrics["heroIndex"] == 0
                assert route_metrics["navInsideHero"] is True
                assert route_metrics["contentIndex"] > route_metrics["heroIndex"]
                assert route_metrics["maxDirectChildWidth"] <= viewport["width"] + 1
                assert route_metrics["legacyRoutePresent"] is False

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
                            const panels = Array.from(document.querySelectorAll('.dm-content-systems-lane section.card'));
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
                            '.dm-content-subpage-nav',
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
            expect(page.get_by_role("heading", name="DM Content")).to_be_visible(timeout=10000)
            dm_content_nav = page.locator(".dm-content-subpage-nav")
            expect(dm_content_nav).to_be_visible()
            expect(page.locator(".dm-content-gen2-links")).to_have_count(0)
            expect(dm_content_nav.get_by_role("link", name="Statblocks")).to_have_class(re.compile(r"\bbutton-link\b"))
            expect(dm_content_nav.get_by_role("link", name="Staged Articles")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Conditions")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Player Wiki")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Systems")).to_have_class(re.compile(r"\bghost-button\b"))

            create_panel = page.locator("section.card.dm-statblock-create")
            expect(create_panel.get_by_role("heading", name="Create statblock")).to_be_visible()
            page.locator("#dm-statblock-create-filename").fill("gen2-harbor-guard.md")
            page.locator("#dm-statblock-create-subsection").fill("Gen2 Harbor Crew")
            page.locator("#dm-statblock-create-markdown").fill(statblock_markdown)
            create_panel.get_by_role("button", name="Save statblock").click()
            expect(page.get_by_text("Statblock saved: Gen2 Harbor Guard.")).to_be_visible(timeout=10000)

            library = page.locator("section.card.dm-statblock-library")
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
            expect(page.get_by_role("heading", name="DM Content")).to_be_visible(timeout=10000)
            dm_content_nav = page.locator(".dm-content-subpage-nav")
            expect(dm_content_nav).to_be_visible()
            expect(page.locator(".dm-content-gen2-links")).to_have_count(0)
            expect(dm_content_nav.get_by_role("link", name="Statblocks")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Staged Articles")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Conditions")).to_have_class(re.compile(r"\bbutton-link\b"))
            expect(dm_content_nav.get_by_role("link", name="Player Wiki")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Systems")).to_have_class(re.compile(r"\bghost-button\b"))

            create_panel = page.locator("section.card.dm-condition-create")
            expect(create_panel.get_by_role("heading", name="Create condition")).to_be_visible()
            page.locator("#dm-condition-create-name").fill(condition_name)
            page.locator("#dm-condition-create-description").fill(condition_description)
            create_panel.get_by_role("button", name="Save condition").click()
            expect(page.get_by_text(f"Condition saved: {condition_name}.")).to_be_visible(timeout=10000)

            library = page.locator("section.card.dm-condition-library")
            expect(library.get_by_text("These names appear in the combat condition picker")).to_be_visible()
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
            expect(page.get_by_role("heading", name="DM Content")).to_be_visible(timeout=10000)
            dm_content_nav = page.locator(".dm-content-subpage-nav")
            expect(dm_content_nav).to_be_visible()
            expect(page.locator(".dm-content-gen2-links")).to_have_count(0)
            expect(dm_content_nav.get_by_role("link", name="Statblocks")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Staged Articles")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Conditions")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Player Wiki")).to_have_class(re.compile(r"\bbutton-link\b"))
            expect(dm_content_nav.get_by_role("link", name="Systems")).to_have_class(re.compile(r"\bghost-button\b"))

            create_panel = page.locator("section.card.dm-player-wiki-create")
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

            library = page.locator("section.card.dm-player-wiki-library")
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
            expect(page.get_by_role("heading", name="DM Content")).to_be_visible(timeout=10000)
            dm_content_nav = page.locator(".dm-content-subpage-nav")
            expect(dm_content_nav).to_be_visible()
            expect(page.locator(".dm-content-gen2-links")).to_have_count(0)
            expect(dm_content_nav.get_by_role("link", name="Statblocks")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Staged Articles")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Conditions")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Player Wiki")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Systems")).to_have_class(re.compile(r"\bbutton-link\b"))
            expect(dm_content_nav.get_by_role("link", name="Systems")).to_have_attribute(
                "href",
                "/app-next/campaigns/linden-pass/dm-content?lane=systems",
            )

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
            expect(page.get_by_role("heading", name="DM Content")).to_be_visible(timeout=10000)
            dm_content_nav = page.locator(".dm-content-subpage-nav")
            expect(dm_content_nav).to_be_visible()
            expect(page.locator(".dm-content-gen2-links")).to_have_count(0)
            expect(dm_content_nav.get_by_role("link", name="Statblocks")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Staged Articles")).to_have_class(re.compile(r"\bbutton-link\b"))
            expect(dm_content_nav.get_by_role("link", name="Conditions")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Player Wiki")).to_have_class(re.compile(r"\bghost-button\b"))
            expect(dm_content_nav.get_by_role("link", name="Systems")).to_have_class(re.compile(r"\bghost-button\b"))

            expect(page.get_by_role("button", name="Manual")).to_be_visible()
            expect(page.get_by_role("button", name="Upload")).to_be_visible()
            expect(page.get_by_role("button", name="Wiki / Systems")).to_be_visible()

            creation_panel = page.locator("article", has_text="Stage session articles").first
            creation_panel.get_by_label("Title").fill(article_title)
            creation_panel.get_by_label("Markdown body").fill(article_body)
            creation_panel.get_by_role("button", name="Create").click()
            expect(page.get_by_text("Article staged.")).to_be_visible(timeout=10000)

            expect(page.locator("article.card#dm-content-staged-article-store")).to_be_visible()
            staged_panel = page.locator("section.card#dm-content-staged-articles-queue")
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
