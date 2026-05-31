import re
import threading
from copy import deepcopy

import pytest


@pytest.fixture
def character_read_shell_live_server(app):
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


def _write_character_state(app, character_slug: str, mutator) -> None:
    with app.app_context():
        repository = app.extensions["character_repository"]
        store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        payload = deepcopy(record.state_record.state)
        mutator(payload)
        store.replace_state(
            record.definition,
            payload,
            expected_revision=record.state_record.revision,
        )


def _check_no_horizontal_overflow(page, selector: str, viewport_name: str, *, required: bool) -> None:
    measurements = page.evaluate(
        """(selector) => {
            const element = document.querySelector(selector);
            if (!element) {
                return { selector, missing: true };
            }

            const rect = element.getBoundingClientRect();
            return {
                selector,
                missing: false,
                left: rect.left,
                right: rect.right,
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
            };
        }""",
        selector,
    )

    if required:
        assert not measurements["missing"], f"{viewport_name}: missing {selector}"
    elif measurements["missing"]:
        return

    assert measurements["left"] >= -1, f"{viewport_name}: {selector} starts before viewport start"
    assert measurements["right"] <= page.viewport_size["width"] + 1, (
        f"{viewport_name}: {selector} overflows to the right"
    )
    assert measurements["scrollWidth"] <= measurements["clientWidth"] + 1, (
        f"{viewport_name}: {selector} content does not fit its container"
    )


def _assert_character_read_no_overflow(page, viewport_name: str) -> None:
    required_selectors = [
        ".page-shell",
        "[data-character-read-shell-root]",
        ".character-sheet",
        ".character-header",
        ".character-subpage-nav-card",
        ".character-subpage-nav",
        ".character-header__identity h1",
    ]
    optional_selectors = [
        ".glance-grid--quick-row-3",
        ".resource-grid--compact",
        ".spell-slot-editor-list--compact",
        ".detail-grid",
        ".ability-grid--skills",
    ]

    document_width = page.evaluate(
        """() => {
            const root = document.scrollingElement || document.documentElement;
            return root.scrollWidth;
        }"""
    )
    assert document_width <= page.viewport_size["width"] + 2, (
        f"{viewport_name}: document overflows horizontally ({document_width} > {page.viewport_size['width']})"
    )

    for selector in required_selectors:
        _check_no_horizontal_overflow(page, selector, viewport_name, required=True)
    for selector in optional_selectors:
        _check_no_horizontal_overflow(page, selector, viewport_name, required=False)


def _set_overflow_test_character_name(page) -> None:
    page.locator(".character-header__identity h1").evaluate(
        """(element, value) => {
            element.textContent = value;
            element.title = value;
        }""",
        "Zigzag Blackscar With an Extremely Long Sheet Name for Overflow Testing",
    )


def _wait_for_app_loading_cover(page) -> None:
    page.wait_for_function(
        """() => {
            const root = document.documentElement;
            return !root.classList.contains("app-loading")
                && !root.classList.contains("app-loading-closing");
        }""",
        timeout=5000,
    )


def test_character_read_shell_browser_state_and_save_flow(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    arden_character_slug_path = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    notes_url_pattern = re.compile(
        r"^.*/campaigns/linden-pass/characters/arden-march\?.*page=notes.*$"
    )
    personal_url_pattern = re.compile(
        r"^.*/campaigns/linden-pass/characters/arden-march\?.*page=personal.*$"
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["owner"]["email"])
            page.locator("input[name='password']").fill(users["owner"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(rf"^{re.escape(base_url)}/.*"),
                timeout=5000,
            )

            page.set_viewport_size({"width": 1365, "height": 768})
            page.goto(arden_character_slug_path)
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            _wait_for_app_loading_cover(page)
            _set_overflow_test_character_name(page)
            _assert_character_read_no_overflow(page, "desktop-1365")
            page.screenshot(path=str(tmp_path / "character_read_zigzag_1365.png"))

            page.set_viewport_size({"width": 390, "height": 812})
            page.reload()
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            _wait_for_app_loading_cover(page)
            _set_overflow_test_character_name(page)
            _assert_character_read_no_overflow(page, "mobile-390")
            page.screenshot(path=str(tmp_path / "character_read_zigzag_390.png"))

            page.goto(arden_character_slug_path)
            page.set_viewport_size({"width": 1280, "height": 720})
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            expect(page.locator("text=Open sheet edit view")).to_have_count(0)
            expect(page.locator("[data-character-sheet-save-bar]")).to_have_count(0)
            expect(page.locator("[data-character-subpage-nav-card]")).to_be_visible(timeout=5000)
            expect(page.locator(".glance-card--vitals input[name='current_hp']")).to_be_visible(timeout=5000)
            expect(page.locator("text=Save vitals")).to_have_count(0)
            quick_row_columns = page.locator(".glance-grid--quick-row-1").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert quick_row_columns == 2
            passive_row_columns = page.locator(".glance-grid--quick-row-3").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert passive_row_columns == 4
            resource_columns = page.locator(".resource-grid--editable").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert resource_columns <= 3
            desktop_columns = page.locator(".ability-grid--skills").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert desktop_columns == 6
            page.set_viewport_size({"width": 640, "height": 900})
            mobile_passive_row_columns = page.locator(".glance-grid--quick-row-3").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert mobile_passive_row_columns == 2
            mobile_columns = page.locator(".ability-grid--skills").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert mobile_columns == 3
            page.set_viewport_size({"width": 1280, "height": 720})
            page.evaluate("window.__characterReadShellMarker = 'alive'")
            hp_field = page.locator("form[data-character-sheet-edit-form='vitals'] input[name='current_hp']")
            hp_field.fill("12")
            hp_field.press("Enter")
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Vitals updated.",
                timeout=3000,
            )
            expect(hp_field).to_have_value("12", timeout=5000)
            assert page.evaluate("window.__characterReadShellMarker") == "alive"

            _write_character_state(
                app,
                "arden-march",
                lambda state: state.__setitem__(
                    "vitals",
                    {
                        "current_hp": 9,
                        "temp_hp": 0,
                    },
                ),
            )
            hp_field.fill("4")
            hp_field.press("Enter")
            expect(page.locator("[data-flash-stack-root] .flash-error")).to_have_text(
                "This sheet changed in another session. Refresh the page and try again.",
                timeout=3000,
            )
            expect(hp_field).to_have_value("4", timeout=5000)
            assert page.evaluate("window.__characterReadShellMarker") == "alive"

            page.locator("[data-character-read-target-subpage='personal']").click()
            expect(page).to_have_url(personal_url_pattern, timeout=5000)
            page.go_back()
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)

            page.locator("[data-character-read-target-subpage='spellcasting']").click()
            expect(page.locator("h2:has-text('Spell slots')")).to_be_visible(timeout=5000)
            generic_slot_headings = page.locator("h3.spell-slot-pool-title:has-text('Spell slots')")
            assert generic_slot_headings.count() > 0
            assert generic_slot_headings.evaluate_all(
                "(elements) => elements.every((element) => getComputedStyle(element).position === 'absolute')"
            )
            spell_slot_columns = page.locator(".spell-slot-editor-list--compact").nth(0).evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert spell_slot_columns <= 3

            page.goto(f"{arden_character_slug_path}?mode=read&page=notes")
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='player_notes_markdown']")).to_be_visible(timeout=5000)

            notes_draft = "Browser draft to preserve."
            personal_draft = "Portrait caption draft from browser flow."
            page.locator("textarea[name='player_notes_markdown']").fill(notes_draft)
            page.locator("[data-character-read-target-subpage='personal']").click()
            page.wait_for_function("window.location.search.includes('page=personal')")
            expect(page).to_have_url(personal_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='background_markdown']")).to_have_count(0)
            expect(page.locator("button:has-text('Save personal details')")).to_have_count(0)
            page.locator("input[name='portrait_caption']").fill(personal_draft)

            page.go_back()
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                notes_draft,
                timeout=5000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)

            page.go_forward()
            expect(page.locator("input[name='portrait_caption']")).to_have_value(
                personal_draft,
                timeout=5000,
            )
            expect(page).to_have_url(personal_url_pattern, timeout=5000)

            page.locator("[data-character-read-target-subpage='notes']").click()
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                notes_draft,
                timeout=5000,
            )

            page.locator("textarea[name='player_notes_markdown']").fill("Saved from JS shell flow.")
            page.locator("button:has-text('Save note')").click()
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Note saved.",
                timeout=3000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            assert "session/notes" not in page.url

            _write_character_state(
                app,
                "arden-march",
                lambda state: state.__setitem__(
                    "notes",
                    {
                        **dict(state.get("notes") or {}),
                        "player_notes_markdown": "Concurrent edit from browser flow.",
                    },
                ),
            )

            page.locator("textarea[name='player_notes_markdown']").fill("Conflict should stay in shell.")
            page.locator("button:has-text('Save note')").click()
            expect(page.locator("[data-flash-stack-root] .flash-error")).to_have_text(
                "This sheet changed in another session. Refresh the page and try again.",
                timeout=3000,
            )
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                "Conflict should stay in shell.",
                timeout=5000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
        finally:
            page.close()
            browser.close()
