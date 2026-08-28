from __future__ import annotations

import re
import threading

import pytest

from tests.helpers.systems_seed_helpers import _seed_systems_item_entry


ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/update-preview"


@pytest.fixture
def character_update_preview_live_server(app):
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


def _sign_in(page, base_url: str, user: dict[str, object]) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(str(user["email"]))
    page.locator("input[name='password']").fill(str(user["password"]))
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _assert_no_horizontal_overflow(page, label: str) -> None:
    measurements = page.evaluate(
        """() => ({
            viewport: document.documentElement.clientWidth,
            documentWidth: document.documentElement.scrollWidth,
            mainRight: document.querySelector('#character-update-preview')
                .getBoundingClientRect().right,
        })"""
    )
    assert measurements["documentWidth"] <= measurements["viewport"] + 1, label
    assert measurements["mainRight"] <= measurements["viewport"] + 1, label


def test_character_update_preview_no_js_compose_validation_review_history_and_cancel(
    app,
    users,
    character_update_preview_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

    _seed_systems_item_entry(
        app,
        slug="preview-browser-lantern",
        title="Preview Browser Lantern",
    )
    base_url = character_update_preview_live_server
    target_url = f"{base_url}{ROUTE_PATH}"
    viewports = (
        ("desktop no-JS", {"width": 1280, "height": 900}),
        ("mobile no-JS", {"width": 390, "height": 800}),
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.fail(f"Playwright browser unavailable: {exc}")
        try:
            for label, viewport in viewports:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=False,
                )
                page = context.new_page()
                try:
                    _sign_in(page, base_url, users["dm"])
                    page.goto(target_url)
                    expect(
                        page.get_by_role(
                            "heading",
                            name="Preview an update for Arden March",
                            exact=True,
                        )
                    ).to_be_visible()
                    expect(page.get_by_role("heading", name="Compose update")).to_be_visible()
                    _assert_no_horizontal_overflow(page, f"{label} compose")

                    page.get_by_role("link", name="Back to character", exact=True).click()
                    expect(
                        page.get_by_role("heading", name="Arden March", exact=True)
                    ).to_be_visible()
                    page.go_back()
                    expect(page.get_by_role("heading", name="Compose update")).to_be_visible()
                    page.go_forward()
                    expect(
                        page.get_by_role("heading", name="Arden March", exact=True)
                    ).to_be_visible()
                    page.go_back()
                    expect(page.get_by_role("heading", name="Compose update")).to_be_visible()

                    source = page.locator("select[name='operation_0_choice']")
                    source.select_option(label="Preview Browser Lantern")
                    quantity = page.locator("input[name='operation_0_quantity']")
                    quantity.fill("abc")
                    page.get_by_role("button", name="Review update").click()

                    expect(
                        page.get_by_role(
                            "heading",
                            name="Review the highlighted fields",
                            exact=True,
                        )
                    ).to_be_visible()
                    quantity = page.locator("input[name='operation_0_quantity']")
                    expect(quantity).to_have_value("abc")
                    expect(quantity).to_have_attribute("aria-invalid", "true")
                    expect(quantity).to_be_focused()
                    expect(
                        page.locator(
                            ".character-update-preview__errors a[href='#operation-0-quantity']"
                        )
                    ).to_have_count(1)
                    _assert_no_horizontal_overflow(page, f"{label} validation")

                    quantity.fill("2")
                    page.get_by_role("button", name="Review update").click()
                    expect(
                        page.get_by_role("heading", name="Semantic changes", exact=True)
                    ).to_be_visible()
                    for category in (
                        "Features",
                        "Equipment/inventory",
                        "Spells",
                        "Attacks",
                        "Armor Class",
                        "Resources",
                    ):
                        expect(page.get_by_role("heading", name=category, exact=True)).to_have_count(1)
                    expect(page.get_by_role("button", name=re.compile("apply", re.I))).to_have_count(0)
                    expect(page.locator("body")).not_to_contain_text("definition.yaml")
                    expect(page.locator("body")).not_to_contain_text("source.json")
                    _assert_no_horizontal_overflow(page, f"{label} review")

                    page.get_by_role("button", name="Back to edit").click()
                    expect(source).to_have_value(re.compile("systems_item_add"))
                    expect(quantity).to_have_value("2")
                    page.get_by_role("button", name="Cancel", exact=True).click()
                    expect(
                        page.get_by_role("heading", name="Arden March", exact=True)
                    ).to_be_visible()
                finally:
                    page.close()
                    context.close()
        finally:
            browser.close()
