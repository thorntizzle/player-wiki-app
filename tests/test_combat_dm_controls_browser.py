import re
import threading
from pathlib import Path

import pytest


@pytest.fixture
def combat_dm_controls_live_server(app):
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


def _assert_controls_layout(page) -> None:
    metrics = page.evaluate(
        """() => {
            const cards = Array.from(document.querySelectorAll("section.card.sidebar-card"));
            const addCards = cards.filter((card) => {
                const heading = card.querySelector("h2");
                return heading && heading.textContent.trim() === "Add combatant";
            });
            const addCard = addCards[0] || null;
            const switcher = document.querySelector(".combat-add-combatant-mode-switcher");
            const toggle = document.querySelector(".combat-add-combatant-mode-toggle");
            return {
                innerWidth: window.innerWidth,
                scrollWidth: document.documentElement.scrollWidth,
                cardCount: cards.length,
                addCardCount: addCards.length,
                addCardWidth: addCard ? addCard.getBoundingClientRect().width : 0,
                switcherWidth: switcher ? switcher.getBoundingClientRect().width : 0,
                toggleWidth: toggle ? toggle.getBoundingClientRect().width : 0,
            };
        }"""
    )

    assert metrics["cardCount"] == 2
    assert metrics["addCardCount"] == 1
    assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1
    assert metrics["switcherWidth"] <= metrics["addCardWidth"] + 1
    assert metrics["toggleWidth"] <= metrics["addCardWidth"] + 1


def _assert_mode_switcher(page, expect) -> None:
    expect(page.get_by_role("heading", name="Add combatant")).to_be_visible(timeout=5000)
    expect(page.locator(".combat-add-combatant-mode-panel--player")).to_be_visible()
    expect(page.locator("#combat-add-mode-player")).to_be_checked()

    page.get_by_text("Add NPC from Systems", exact=True).click()
    expect(page.locator("#combat-add-mode-systems")).to_be_checked()
    expect(page.locator(".combat-add-combatant-mode-panel--systems")).to_be_visible()
    expect(page.locator(".combat-add-combatant-mode-panel--player")).not_to_be_visible()

    page.get_by_text("Add NPC from DM Content", exact=True).click()
    expect(page.locator("#combat-add-mode-dm-content")).to_be_checked()
    expect(page.locator(".combat-add-combatant-mode-panel--dm-content")).to_be_visible()
    expect(page.locator(".combat-add-combatant-mode-panel--systems")).not_to_be_visible()

    page.get_by_text("Add custom combatant", exact=True).click()
    expect(page.locator("#combat-add-mode-custom")).to_be_checked()
    expect(page.locator(".combat-add-combatant-mode-panel--custom")).to_be_visible()
    expect(page.locator(".combat-add-combatant-mode-panel--dm-content")).not_to_be_visible()


def test_flask_dm_controls_add_combatant_mode_switcher_browser(
    combat_dm_controls_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server

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
            desktop_page.goto(f"{base_url}/campaigns/linden-pass/combat/dm?view=controls")
            _assert_mode_switcher(desktop_page, expect)
            _assert_controls_layout(desktop_page)

            _sign_in(mobile_page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            mobile_page.goto(f"{base_url}/campaigns/linden-pass/combat/dm?view=controls")
            _assert_mode_switcher(mobile_page, expect)
            _assert_controls_layout(mobile_page)
        finally:
            desktop_page.close()
            mobile_page.close()
            desktop_context.close()
            mobile_context.close()
            browser.close()


def test_gen2_combat_controls_advance_turn_lives_in_status_band_browser(
    combat_dm_controls_live_server,
    users,
):
    if not (Path(__file__).resolve().parents[1] / "frontend" / "dist" / "index.html").exists():
        pytest.skip("Gen2 build is unavailable.")
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(f"{base_url}/app-next/campaigns/linden-pass/combat?view=controls")
            expect(page.get_by_role("heading", name="Encounter controls")).to_be_visible(timeout=5000)
            expect(page.locator(".combat-summary-band")).to_be_visible()
            expect(page.locator(".combat-summary-band").get_by_role("button", name="Advance turn")).to_be_visible()
            expect(page.locator(".combat-controls-layout").get_by_role("button", name="Advance turn")).to_have_count(0)
            expect(page.locator(".combat-controls-layout").get_by_role("heading", name="Tracker")).to_have_count(0)
        finally:
            page.close()
            context.close()
            browser.close()
