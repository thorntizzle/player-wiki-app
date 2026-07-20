from tests.helpers.character_state_helpers import (
    _write_character_definition,
    _write_character_state,
)
import re
import threading
import time
from copy import deepcopy

import player_wiki.app as app_module
import pytest
import yaml
from player_wiki.auth_store import AuthStore
from player_wiki.campaign_session_service import CampaignSessionValidationError
from tests.helpers.character_builder_fakes import (
    _builder_context_fixture,
    _level_up_context_fixture,
    _minimal_character_definition,
    _minimal_import_metadata,
)
from tests.helpers.systems_seed_helpers import (
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
)
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)


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
        ".spell-card-grid",
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
    from playwright.sync_api import expect

    expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(
        0,
        timeout=5000,
    )


def _sign_in_browser(page, base_url: str, user) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(user["email"])
    page.locator("input[name='password']").fill(user["password"])
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _write_leveler_fixture(app) -> None:
    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")


def _scroll_y(page) -> float:
    return float(page.evaluate("window.scrollY"))


def test_character_native_live_previews_preserve_focus_and_viewport(
    app,
    users,
    character_read_shell_live_server,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    monkeypatch.setattr(app_module, "build_level_one_builder_context", lambda *args, **kwargs: _builder_context_fixture())
    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )
    _write_leveler_fixture(app)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 420})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])

            page.goto(f"{base_url}/campaigns/linden-pass/characters/new")
            _wait_for_app_loading_cover(page)
            strength_field = page.locator("input[name='str']")
            expect(strength_field).to_be_visible(timeout=5000)
            strength_field.scroll_into_view_if_needed()
            page.wait_for_timeout(50)
            create_scroll_before = _scroll_y(page)
            with page.expect_response(
                lambda response: "/campaigns/linden-pass/characters/new" in response.url
                and "_live_preview=1" in response.url,
                timeout=5000,
            ):
                strength_field.fill("17")
            expect(strength_field).to_be_focused(timeout=5000)
            expect(strength_field).to_have_value("17", timeout=5000)
            assert abs(_scroll_y(page) - create_scroll_before) <= 40

            page.goto(f"{base_url}/campaigns/linden-pass/characters/leveler/level-up")
            _wait_for_app_loading_cover(page)
            hp_gain_field = page.locator("input[name='hp_gain']")
            expect(hp_gain_field).to_be_visible(timeout=5000)
            hp_gain_field.scroll_into_view_if_needed()
            page.wait_for_timeout(50)
            level_scroll_before = _scroll_y(page)
            with page.expect_response(
                lambda response: "/campaigns/linden-pass/characters/leveler/level-up" in response.url
                and "_live_preview=1" in response.url,
                timeout=5000,
            ):
                hp_gain_field.fill("9")
            expect(hp_gain_field).to_be_focused(timeout=5000)
            expect(hp_gain_field).to_have_value("9", timeout=5000)
            assert abs(_scroll_y(page) - level_scroll_before) <= 40
        finally:
            page.close()
            browser.close()


def test_character_systems_item_lookup_keeps_results_visible_while_refreshing(
    app,
    users,
    character_read_shell_live_server,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    entry = _seed_systems_item_entry(app)
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        original_search = systems_service.search_entries_for_campaign

    def _slow_search(*args, **kwargs):
        if str(kwargs.get("query") or "").strip().lower() == "lantern":
            time.sleep(1.0)
        return original_search(*args, **kwargs)

    monkeypatch.setattr(systems_service, "search_entries_for_campaign", _slow_search)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])

            page.goto(f"{base_url}/campaigns/linden-pass/characters/selene-brook?page=inventory")
            _wait_for_app_loading_cover(page)
            search_input = page.locator("[data-character-systems-item-query]")
            results_select = page.locator("[data-character-systems-item-results]")
            status = page.locator("[data-character-systems-item-status]")
            expect(search_input).to_be_visible(timeout=5000)

            with page.expect_response(
                lambda response: "/equipment/systems-items/search" in response.url and "q=rope" in response.url,
                timeout=5000,
            ):
                search_input.fill("rope")
            expect(results_select).not_to_be_disabled(timeout=5000)
            expect(results_select.locator("option").first).to_have_text(re.compile(r"Rope"))
            assert results_select.input_value() == entry.slug

            search_input.fill("lantern")
            expect(status).to_have_text("Searching Systems items...", timeout=1500)
            expect(results_select).not_to_be_disabled(timeout=5000)
            expect(results_select.locator("option").first).to_have_text(re.compile(r"Rope"))
            assert results_select.input_value() == entry.slug
            expect(status).to_have_text("No enabled Systems items matched that search.", timeout=5000)
        finally:
            page.close()
            browser.close()


def test_spellcasting_subview_buttons_hide_and_show_panels(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Cleric 5"
        profile["classes"] = [{"class_name": "Cleric", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Cleric",
            "spellcasting_ability": "Wisdom",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                {
                    "name": "Guidance",
                    "level": 0,
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "1 minute",
                    "components": "V, S",
                    "source": "Cleric",
                },
                {
                    "name": "Cure Wounds",
                    "level": 1,
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "Instantaneous",
                    "components": "V, S",
                    "source": "Cleric",
                },
                {
                    "name": "Bless",
                    "level": 1,
                    "casting_time": "1 action",
                    "range": "30 feet",
                    "duration": "Concentration, up to 1 minute",
                    "components": "V, S, M",
                    "source": "Cleric (Always Prepared)",
                    "mark": "P",
                    "is_always_prepared": True,
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["dm"]["email"])
            page.locator("input[name='password']").fill(users["dm"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)

            page.goto(f"{base_url}/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
            _wait_for_app_loading_cover(page)

            current_panel = page.locator("#character-spell-current-view")
            preparation_panel = page.locator("#character-spell-preparation-view")
            expect(current_panel).to_be_visible(timeout=5000)
            expect(preparation_panel).to_be_hidden(timeout=5000)
            expect(current_panel.locator(".spell-card__name", has_text="Bless")).to_be_visible()
            expect(current_panel.locator(".spell-card__name", has_text="Cure Wounds")).to_have_count(0)

            page.get_by_role("tab", name="Preparation").click()
            expect(current_panel).to_be_hidden(timeout=5000)
            expect(preparation_panel).to_be_visible(timeout=5000)
            prep_spell_button = preparation_panel.locator(
                "[data-character-spell-modal-trigger]",
                has_text="Cure Wounds",
            )
            expect(prep_spell_button).to_be_visible()
            prep_spell_button.click()
            prep_dialog = page.locator("dialog[open]", has_text="Cure Wounds")
            expect(prep_dialog).to_be_visible()
            prep_dialog.get_by_role("button", name="Close").click()
            expect(prep_dialog).to_be_hidden()

            page.get_by_role("tab", name="Current spells").click()
            expect(current_panel).to_be_visible(timeout=5000)
            expect(preparation_panel).to_be_hidden(timeout=5000)
        finally:
            browser.close()


def test_character_read_shared_dialog_adopter_preserves_modal_and_fallback_contracts(
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

    item_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-backpack",
        title="Backpack",
        rendered_html=(
            '<p>Character item detail body from Systems.</p>'
            '<p><a href="/campaigns/linden-pass/systems/entries/phb-item-backpack">'
            "Open Backpack reference</a></p>"
        ),
    )
    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-message",
        title="Message",
        rendered_html="<p>Character spell detail body from Systems.</p>",
    )

    def _link_inventory_item(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {
            **dict(spells[0]),
            "systems_ref": _systems_ref(spell_entry),
        }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        assert len(equipment_catalog) > 4
        equipment_catalog[4] = {
            **dict(equipment_catalog[4]),
            "systems_ref": _systems_ref(item_entry),
        }
        payload["equipment_catalog"] = equipment_catalog

    _write_character_definition(app, "arden-march", _link_inventory_item)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"

    def _assert_dialog_label(page, dialog) -> None:
        labelled_by = dialog.get_attribute("aria-labelledby")
        assert labelled_by
        assert page.locator(f"#{labelled_by}").count() == 1
        assert page.locator(f"#{labelled_by}").inner_text().strip()

    def _assert_close_returns_without_scroll(page, trigger, close_action) -> None:
        scroll_before = _scroll_y(page)
        close_action()
        expect(page.locator("dialog[data-character-spell-modal][open]")).to_have_count(
            0,
            timeout=5000,
        )
        expect(trigger).to_be_focused(timeout=5000)
        assert abs(_scroll_y(page) - scroll_before) <= 1

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
        desktop_page = desktop_context.new_page()
        try:
            _sign_in_browser(desktop_page, base_url, users["owner"])
            desktop_page.goto(f"{character_url}?page=spellcasting")
            _wait_for_app_loading_cover(desktop_page)
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))

            spell_trigger = desktop_page.locator(
                "#character-spell-current-view [data-character-spell-modal-trigger]"
            ).first
            expect(spell_trigger).to_be_visible(timeout=5000)
            spell_trigger.scroll_into_view_if_needed()
            spell_trigger.focus()
            spell_scroll = _scroll_y(desktop_page)
            spell_trigger.press("Enter")
            spell_dialog = desktop_page.locator(
                "dialog[data-character-spell-modal][data-presentation-dialog][open]"
            ).first
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_dialog_label(desktop_page, spell_dialog)
            assert spell_dialog.evaluate("dialog => dialog.matches(':modal')")
            expect(
                spell_dialog.locator("[data-presentation-dialog-initial-focus]")
            ).to_be_focused(timeout=5000)
            spell_dialog.get_by_role("button", name="Close").click()
            expect(spell_trigger).to_be_focused(timeout=5000)
            assert abs(_scroll_y(desktop_page) - spell_scroll) <= 1

            spell_trigger.press("Enter")
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_close_returns_without_scroll(
                desktop_page,
                spell_trigger,
                lambda: desktop_page.keyboard.press("Escape"),
            )

            spell_trigger.press("Enter")
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_close_returns_without_scroll(
                desktop_page,
                spell_trigger,
                lambda: desktop_page.mouse.click(1, 1),
            )
            assert "page=spellcasting" in desktop_page.url
            expect(desktop_page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            _assert_character_read_no_overflow(desktop_page, "desktop-dialog-1280x900")
            desktop_page.screenshot(path=str(tmp_path / "character_dialog_desktop_1280x900.png"))
        finally:
            desktop_page.close()
            desktop_context.close()

        mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        mobile_page = mobile_context.new_page()
        try:
            _sign_in_browser(mobile_page, base_url, users["dm"])
            mobile_page.goto(f"{character_url}?page=spellcasting")
            _wait_for_app_loading_cover(mobile_page)
            mobile_page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(mobile_page.locator("html")).to_have_attribute("data-theme", "moonlit")

            mobile_page.locator("[data-character-read-target-subpage='inventory']").click()
            expect(mobile_page).to_have_url(re.compile(r"[?&]page=inventory(?:&|$)"), timeout=5000)
            item_trigger = mobile_page.locator("button.item-detail-button").first
            expect(item_trigger).to_be_visible(timeout=5000)
            item_trigger.scroll_into_view_if_needed()
            item_scroll = _scroll_y(mobile_page)
            item_trigger.click()
            item_dialog = mobile_page.locator(
                "dialog.item-detail-dialog[data-presentation-dialog][open]"
            ).first
            expect(item_dialog).to_be_visible(timeout=5000)
            _assert_dialog_label(mobile_page, item_dialog)
            assert item_dialog.evaluate("dialog => dialog.matches(':modal')")
            expect(
                item_dialog.locator("[data-presentation-dialog-initial-focus]")
            ).to_be_focused(timeout=5000)
            item_dialog.get_by_role("button", name="Close").click()
            expect(item_trigger).to_be_focused(timeout=5000)
            assert abs(_scroll_y(mobile_page) - item_scroll) <= 1
            assert "page=inventory" in mobile_page.url
            expect(mobile_page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            _assert_character_read_no_overflow(mobile_page, "mobile-dialog-390x800")
            mobile_page.screenshot(path=str(tmp_path / "character_dialog_mobile_390x800.png"))
        finally:
            mobile_page.close()
            mobile_context.close()

        no_js_context = browser.new_context(
            java_script_enabled=False,
            viewport={"width": 390, "height": 800},
        )
        no_js_page = no_js_context.new_page()
        try:
            _sign_in_browser(no_js_page, base_url, users["owner"])
            no_js_page.goto(f"{character_url}?page=spellcasting")
            expect(no_js_page.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            spell_fallback = no_js_page.locator("details.spell-card__fallback").first
            expect(spell_fallback).to_be_visible(timeout=5000)
            spell_fallback.locator("summary").click()
            expect(spell_fallback.locator(".spell-detail-content")).to_be_visible(timeout=5000)

            no_js_page.locator("[data-character-read-target-subpage='inventory']").click()
            expect(no_js_page).to_have_url(re.compile(r"[?&]page=inventory(?:&|$)"), timeout=5000)
            expect(no_js_page.locator("button.item-detail-button")).to_have_count(0)
            expect(no_js_page.locator(".item-description-detail").first).to_be_visible(timeout=5000)
            reference_link = no_js_page.get_by_role("link", name="Open Backpack reference")
            expect(reference_link).to_have_attribute(
                "href",
                "/campaigns/linden-pass/systems/entries/phb-item-backpack",
            )
            _assert_character_read_no_overflow(no_js_page, "mobile-no-js-390x800")
            no_js_page.screenshot(path=str(tmp_path / "character_dialog_no_js_390x800.png"))
        finally:
            no_js_page.close()
            no_js_context.close()
            browser.close()


def test_session_character_shared_dialog_adopter_preserves_direct_lazy_and_mutation_contracts(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-message",
        title="Message",
        rendered_html="<p>Session spell detail body from Systems.</p>",
    )

    def _link_session_details(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {**dict(spells[0]), "systems_ref": _systems_ref(spell_entry)}
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

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

    def _link_session_item_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item in enumerate(inventory):
            if str(item.get("catalog_ref") or item.get("id") or "") == "light-crossbow-1":
                inventory[index] = {
                    **dict(item),
                    "name": "Stormglass Compass",
                    "notes": "A campaign-linked Session item.",
                }
                break
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _link_session_details)
    _write_character_state(app, "arden-march", _link_session_item_state)
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    direct_url = (
        f"{base_url}/campaigns/linden-pass/session/character"
        "?character=arden-march&page=inventory"
    )

    def _assert_label(page, dialog) -> None:
        labelled_by = dialog.get_attribute("aria-labelledby")
        assert labelled_by
        assert page.locator(f"#{labelled_by}").count() == 1
        assert page.locator(f"#{labelled_by}").inner_text().strip()

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
        desktop_page = desktop_context.new_page()
        try:
            _sign_in_browser(desktop_page, base_url, users["owner"])
            desktop_page.goto(direct_url)
            _wait_for_app_loading_cover(desktop_page)
            scope = desktop_page.locator("[data-combat-workspace-root]")
            expect(scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready", timeout=5000
            )
            expect(scope.locator("[data-session-character-presentation-dialog-trigger-gate]")).to_have_count(0)
            expect(scope.locator("template[data-character-presentation-dialog-trigger-template]")).to_have_count(0)
            expect(desktop_page.locator("html")).to_have_class(re.compile(r"spell-modal-js"))
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            desktop_page.evaluate("window.__sessionDialogNoReloadMarker = 'alive'")

            item_trigger = scope.locator("button.item-detail-button").first
            item_trigger_count = scope.locator("button.item-detail-button").count()
            item_fallback = scope.locator("details[data-character-spell-fallback]").first
            expect(item_trigger).to_be_visible(timeout=5000)
            expect(item_fallback).to_be_hidden(timeout=5000)
            item_trigger.click()
            item_dialog = scope.locator("dialog.item-detail-dialog[open]").first
            expect(item_dialog).to_be_visible(timeout=5000)
            _assert_label(desktop_page, item_dialog)
            expect(item_dialog.locator("[data-presentation-dialog-initial-focus]")).to_be_focused()
            item_dialog.get_by_role("button", name="Close").click()
            expect(item_trigger).to_be_focused(timeout=5000)

            item_trigger.click()
            expect(item_dialog).to_be_visible(timeout=5000)
            item_dialog.dispatch_event("click")
            expect(item_dialog).to_be_hidden(timeout=5000)
            expect(item_trigger).to_be_focused(timeout=5000)

            desktop_page.evaluate(
                "window.__playerWikiCombatWorkspace.init(document.querySelector('[data-combat-workspace-root]'))"
            )
            expect(scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready"
            )
            assert scope.locator("button.item-detail-button").count() == item_trigger_count

            scope.locator("[data-combat-section-toggle='spells']").click()
            spell_trigger = scope.locator("[data-character-spell-modal-trigger]", has_text="Message").first
            expect(spell_trigger).to_be_visible(timeout=5000)
            spell_trigger.click()
            spell_dialog = scope.locator("dialog[data-presentation-dialog][open]", has_text="Message")
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_label(desktop_page, spell_dialog)
            desktop_page.keyboard.press("Escape")
            expect(spell_dialog).to_be_hidden(timeout=5000)
            expect(spell_trigger).to_be_focused(timeout=5000)

            scope.locator("[data-combat-section-toggle='inventory']").click()
            currency_field = scope.locator(
                "form[data-character-sheet-edit-form='currency'] input[data-session-currency-autosubmit='1']"
            ).first
            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill(next_value)
            currency_field.dispatch_event("change")
            expect(desktop_page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.", timeout=5000
            )
            replacement_scope = desktop_page.locator("[data-combat-workspace-root]")
            expect(replacement_scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready", timeout=5000
            )
            expect(replacement_scope.locator("button.item-detail-button").first).to_be_visible(timeout=5000)
            assert desktop_page.evaluate("window.__sessionDialogNoReloadMarker") == "alive"
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            desktop_page.screenshot(path=str(tmp_path / "session_character_dialog_desktop.png"))
        finally:
            desktop_page.close()
            desktop_context.close()

        mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        mobile_page = mobile_context.new_page()
        try:
            _sign_in_browser(mobile_page, base_url, users["owner"])
            mobile_page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(mobile_page)
            composer = mobile_page.locator("[data-session-composer-form] textarea")
            expect(composer).to_be_visible(timeout=5000)
            composer.fill("Preserve this Session draft while Character loads.")
            mobile_page.locator("[data-session-switch-target='character']").click()
            mobile_scope = mobile_page.locator("[data-combat-workspace-root]")
            expect(mobile_scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready", timeout=5000
            )
            expect(composer).to_have_value("Preserve this Session draft while Character loads.")
            expect(mobile_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            mobile_scope.locator("[data-combat-section-toggle='spells']").click()
            mobile_spell_trigger = mobile_scope.locator(
                "[data-character-spell-modal-trigger]", has_text="Message"
            ).first
            expect(mobile_spell_trigger).to_be_visible(timeout=5000)
            mobile_spell_trigger.click()
            mobile_spell_dialog = mobile_scope.locator(
                "dialog[data-presentation-dialog][open]", has_text="Message"
            )
            expect(mobile_spell_dialog).to_be_visible(timeout=5000)
            mobile_spell_dialog.get_by_role("button", name="Close").click()
            expect(mobile_spell_trigger).to_be_focused(timeout=5000)
            mobile_page.screenshot(path=str(tmp_path / "session_character_dialog_mobile.png"))
        finally:
            mobile_page.close()
            mobile_context.close()

        no_js_context = browser.new_context(
            viewport={"width": 390, "height": 800}, java_script_enabled=False
        )
        no_js_page = no_js_context.new_page()
        try:
            _sign_in_browser(no_js_page, base_url, users["owner"])
            no_js_page.goto(direct_url)
            expect(no_js_page.locator("button.item-detail-button")).to_have_count(0)
            expect(no_js_page.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            fallback = no_js_page.locator(
                "[data-combat-section-panel='inventory'] details[data-character-spell-fallback]"
            ).first
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            expect(fallback.locator(".item-description-detail__body")).to_be_visible(timeout=5000)
            expect(no_js_page.get_by_role("link", name="Stormglass Compass").first).to_be_visible()
        finally:
            no_js_page.close()
            no_js_context.close()
            browser.close()


@pytest.mark.parametrize("initialization_mode", ["absent", "no-op", "throws"])
def test_session_character_dialog_adopter_fails_safe_when_shared_controller_is_unavailable(
    initialization_mode,
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

    def _link_item(payload: dict) -> None:
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

    def _link_item_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item in enumerate(inventory):
            if str(item.get("catalog_ref") or item.get("id") or "") == "light-crossbow-1":
                inventory[index] = {**dict(item), "notes": "Fallback Session item details."}
                break
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _link_item)
    _write_character_state(app, "arden-march", _link_item_state)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    if initialization_mode == "absent":
        controller_body = ""
    else:
        init_body = (
            'throw new Error("shared presentation initialization failed");'
            if initialization_mode == "throws"
            else "return 0;"
        )
        controller_body = f"""
          (() => {{
            window.__playerWikiPresentationController = Object.freeze({{
              init() {{ {init_body} }},
              openDialog() {{ return false; }},
              closeDialog() {{ return false; }},
            }});
          }})();
        """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 800})
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page.route(
            "**/static/presentation-controller.js*",
            lambda route: route.fulfill(
                status=200, content_type="application/javascript", body=controller_body
            ),
        )
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            scope = page.locator("[data-combat-workspace-root]")
            expect(scope.locator("details[data-character-spell-fallback]").first).to_be_visible(
                timeout=5000
            )
            expect(page.locator("html")).not_to_have_class(re.compile(r"spell-modal-js"))
            expect(page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            expect(scope.locator("[data-combat-section-toggle='inventory']")).to_have_attribute(
                "aria-pressed", "true"
            )

            if initialization_mode == "absent":
                expect(scope).not_to_have_attribute(
                    "data-session-character-presentation-dialog-state", re.compile(".+")
                )
                expect(scope.locator("template[data-character-presentation-dialog-trigger-template]")).not_to_have_count(0)
                expect(scope.locator("[data-session-character-presentation-dialog-trigger-gate]")).to_have_count(0)
                expect(scope.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            else:
                expect(scope).to_have_attribute(
                    "data-session-character-presentation-dialog-state", "unavailable", timeout=5000
                )
                gate = scope.locator(
                    "[data-session-character-presentation-dialog-trigger-gate]"
                ).first
                expect(gate).to_have_attribute("hidden", "")
                trigger = gate.locator(
                    "[data-character-spell-modal-trigger][data-presentation-dialog-trigger]"
                )
                expect(trigger).to_have_count(1)
                assert trigger.evaluate("element => element.getClientRects().length") == 0
                expect(trigger).to_be_hidden()
            expect(scope.locator("dialog[data-presentation-dialog][open]")).to_have_count(0)
            page.screenshot(
                path=str(tmp_path / f"session_dialog_partial_controller_{initialization_mode}.png")
            )
        finally:
            page.close()
            context.close()
            browser.close()


@pytest.mark.parametrize("initialization_mode", ["no-op", "throws"])
def test_character_read_dialog_triggers_stay_gated_when_shared_initialization_fails(
    initialization_mode,
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

    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-message",
        title="Message",
        rendered_html="<p>Character spell fallback remains available.</p>",
    )

    def _link_spell(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {
            **dict(spells[0]),
            "systems_ref": _systems_ref(spell_entry),
        }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", _link_spell)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    init_body = (
        'throw new Error("shared presentation initialization failed");'
        if initialization_mode == "throws"
        else "return 0;"
    )
    controller_stub = f"""
      (() => {{
        window.__playerWikiPresentationController = Object.freeze({{
          init() {{ {init_body} }},
          openDialog() {{ return false; }},
          closeDialog() {{ return false; }},
        }});
      }})();
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 800})
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page.route(
            "**/static/presentation-controller.js*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/javascript",
                body=controller_stub,
            ),
        )
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/characters/arden-march?page=spellcasting"
            )

            shell = page.locator("[data-character-read-shell-root]")
            expect(shell).to_have_attribute(
                "data-character-presentation-dialog-state",
                "unavailable",
                timeout=5000,
            )
            expect(page.locator("html")).not_to_have_class(re.compile(r"spell-modal-js"))
            fallback = page.locator("details.spell-card__fallback").first
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            expect(fallback.locator(".spell-detail-content")).to_be_visible(timeout=5000)

            gate = page.locator("[data-character-presentation-dialog-trigger-gate]").first
            expect(gate).to_have_attribute("hidden", "")
            trigger = gate.locator(
                "[data-character-spell-modal-trigger][data-presentation-dialog-trigger]"
            )
            expect(trigger).to_have_count(1)
            assert trigger.evaluate("element => getComputedStyle(element).display") == "grid"
            assert trigger.evaluate("element => element.getClientRects().length") == 0
            expect(trigger).to_be_hidden()
            expect(page.locator("dialog[data-character-spell-modal][open]")).to_have_count(0)
            page.screenshot(
                path=str(tmp_path / f"character_dialog_partial_controller_{initialization_mode}.png")
            )
        finally:
            page.close()
            context.close()
            browser.close()


def test_session_character_panel_switch_and_resource_submit_stay_no_reload(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    base_url = character_read_shell_live_server
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

            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(page.locator("[data-combat-section-panel='overview']")).to_be_visible(timeout=5000)
            expect(page.locator(".glance-grid--quick-row-1")).to_be_visible(timeout=5000)
            expect(page.locator("form[data-character-sheet-edit-form='vitals']")).to_have_count(3)
            page.evaluate("window.__sessionCharacterNoReloadMarker = 'alive'")

            hp_field = page.locator(
                "form[data-character-sheet-edit-form='vitals'][data-character-autosubmit-mode='focus-blur'] "
                "input[name='current_hp']"
            ).first
            expect(hp_field).to_be_visible(timeout=5000)
            hp_field.click()
            hp_field.press("Control+A")
            hp_field.press("Backspace")
            page.wait_for_timeout(700)
            expect(hp_field).to_have_value("")
            assert hp_field.evaluate("element => document.activeElement === element")
            hp_field.type("12", delay=75)
            page.wait_for_timeout(700)
            expect(hp_field).to_have_value("12")
            assert hp_field.evaluate("element => document.activeElement === element")
            hp_field.press("Enter")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Vitals updated.",
                timeout=5000,
            )
            expect(hp_field).to_have_value("12", timeout=5000)
            assert hp_field.evaluate("element => document.activeElement === element")

            page.locator("[data-combat-section-toggle='resources']").click()
            expect(page.locator("[data-combat-section-panel='resources']")).to_be_visible(timeout=5000)
            resource_form = page.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='sorcery-points']"
            )
            expect(resource_form).to_be_visible(timeout=5000)
            resource_current = resource_form.locator("input[name='current']")
            resource_current.fill("4")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Resource updated.",
                timeout=5000,
            )
            expect(resource_form.locator("input[name='current']")).to_have_value("4", timeout=5000)
            assert page.evaluate("window.__sessionCharacterNoReloadMarker") == "alive"
            expect(page).to_have_url(
                re.compile(
                    rf"^{re.escape(base_url)}/campaigns/linden-pass/session/character"
                    r"\?character=arden-march&page=resources$"
                ),
                timeout=5000,
            )

        finally:
            browser.close()


def test_session_currency_change_submits_once_after_character_fragment_replacement(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="public", session="public")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Currency Crane"),
            "character_slug": "currency-crane",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    with app.app_context():
        AuthStore().upsert_character_assignment(
            users["owner"]["id"],
            "linden-pass",
            "currency-crane",
        )
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=currency-crane&page=inventory"
            )
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_post_count = 0

            def count_currency_post(request):
                nonlocal currency_post_count
                if (
                    request.method == "POST"
                    and request.url.endswith(
                        "/campaigns/linden-pass/characters/currency-crane/session/currency"
                    )
                ):
                    currency_post_count += 1

            page.on("request", count_currency_post)
            first_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill("-1")
            currency_field.dispatch_event("change")
            page.wait_for_timeout(300)
            assert currency_post_count == 0

            currency_field.fill(first_value)
            currency_field.dispatch_event("change")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                first_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1

            currency_post_count = 0
            currency_field = page.locator(currency_field_selector).first
            second_value = str(int(first_value) + 1)
            currency_field.fill(second_value)
            currency_field.dispatch_event("change")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                second_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1
        finally:
            browser.close()


def test_session_dnd_currency_change_submits_once(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_post_count = 0

            def count_currency_post(request):
                nonlocal currency_post_count
                if (
                    request.method == "POST"
                    and request.url.endswith(
                        "/campaigns/linden-pass/characters/arden-march/session/currency"
                    )
                ):
                    currency_post_count += 1

            page.on("request", count_currency_post)
            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill("-1")
            currency_field.dispatch_event("change")
            page.wait_for_timeout(300)
            assert currency_post_count == 0

            currency_field.fill(next_value)
            currency_field.dispatch_event("change")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                next_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1
        finally:
            browser.close()


def test_session_dnd_currency_synchronous_duplicate_change_submits_once(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            currency_action = (
                f"{base_url}/campaigns/linden-pass/characters/arden-march/session/currency"
            )
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_post_count = 0

            def count_currency_post(request):
                nonlocal currency_post_count
                if request.method == "POST" and request.url == currency_action:
                    currency_post_count += 1

            def delay_currency_post(route):
                time.sleep(0.4)
                route.continue_()

            page.on("request", count_currency_post)
            page.route(currency_action, delay_currency_post)

            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.evaluate(
                """(field, value) => {
                    field.value = value;
                    field.dispatchEvent(new Event("change", { bubbles: true }));
                    field.dispatchEvent(new Event("change", { bubbles: true }));
                }""",
                next_value,
            )

            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                next_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1
        finally:
            browser.close()


@pytest.mark.parametrize("failure_mode", ["non_ok", "rejected"])
def test_session_dnd_currency_failure_recovers_to_safe_session_page(
    failure_mode,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            safe_session_url = (
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            currency_action = (
                f"{base_url}/campaigns/linden-pass/characters/arden-march/session/currency"
            )
            page.goto(safe_session_url)
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            attempted_post_count = 0
            unsafe_get_count = 0
            safe_get_count = 0

            def track_currency_requests(request):
                nonlocal attempted_post_count, unsafe_get_count, safe_get_count
                if request.method == "GET" and request.url == safe_session_url:
                    safe_get_count += 1
                elif request.url == currency_action and request.method == "POST":
                    attempted_post_count += 1
                elif request.url == currency_action and request.method == "GET":
                    unsafe_get_count += 1

            def fail_currency_post(route):
                if failure_mode == "non_ok":
                    route.fulfill(status=503, body="temporary failure")
                else:
                    route.abort("failed")

            page.on("request", track_currency_requests)
            page.route(currency_action, fail_currency_post)

            next_value = str(int(currency_field.input_value()) + 1)
            with page.expect_event("load", timeout=5000):
                currency_field.fill(next_value)
                currency_field.dispatch_event("change")

            expect(page.locator(currency_field_selector).first).to_be_visible(timeout=5000)
            expect(page.get_by_text("Method Not Allowed")).to_have_count(0)
            assert page.url == safe_session_url
            assert attempted_post_count == 1
            assert safe_get_count == 1
            assert unsafe_get_count == 0
        finally:
            browser.close()


def test_session_character_reloads_after_session_started_from_another_session_pane(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")

    base_url = character_read_shell_live_server
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

            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(page.locator("form[data-character-sheet-edit-form='vitals']")).to_have_count(0)

            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)

            sign_in(users["dm"]["email"], users["dm"]["password"])
            client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

            expect(page.locator("[data-session-status-card]")).to_contain_text(
                "The session is live for players and the DM.",
                timeout=6000,
            )

            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(page.locator("form[data-character-sheet-edit-form='vitals']")).to_have_count(3)
            expect(page.locator("text=Save current HP")).to_have_count(0)
            expect(page.locator("text=Save temp HP")).to_have_count(0)
            expect(page.locator("form[data-character-sheet-edit-form='vitals'][data-character-autosubmit]")).to_have_count(3)
        finally:
            browser.close()


def test_feedback_item44_browser_header_combat_spells_and_session_chrome(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                {
                    "name": "Message",
                    "level": 0,
                    "school": "Transmutation",
                    "casting_time": "1 action",
                    "range": "120 feet",
                    "source": "Sorcerer",
                },
                {
                    "name": "Magic Missile",
                    "level": 1,
                    "school": "Evocation",
                    "casting_time": "1 action",
                    "range": "120 feet",
                    "mark": "Known",
                    "source": "Sorcerer",
                },
                {
                    "name": "Misty Step",
                    "level": 2,
                    "school": "Conjuration",
                    "casting_time": "1 bonus action",
                    "range": "Self",
                    "mark": "Known",
                    "source": "Sorcerer",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["owner"]["email"])
            page.locator("input[name='password']").fill(users["owner"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)

            page.goto(f"{base_url}/campaigns/linden-pass/combat")
            _wait_for_app_loading_cover(page)
            expect(page.locator(".site-header__campaign")).to_have_text(
                "Echoes of the Alloy Coast",
                timeout=5000,
            )
            expect(page.locator(".site-header__campaign-title")).to_be_visible()
            header_metrics = page.evaluate(
                """() => {
                    const primary = document.querySelector(".site-header__primary").getBoundingClientRect();
                    const actions = document.querySelector(".site-header__actions").getBoundingClientRect();
                    const title = document.querySelector(".site-header__campaign-title").getBoundingClientRect();
                    const titleStyle = getComputedStyle(document.querySelector(".site-header__campaign-title"));
                    return {
                        gapCenter: (primary.right + actions.left) / 2,
                        titleCenter: (title.left + title.right) / 2,
                        backgroundImage: titleStyle.backgroundImage,
                        borderTopStyle: titleStyle.borderTopStyle,
                    };
                }"""
            )
            assert abs(header_metrics["gapCenter"] - header_metrics["titleCenter"]) <= 2
            assert header_metrics["backgroundImage"] != "none"
            assert header_metrics["borderTopStyle"] == "solid"
            expect(page.locator("h1")).to_have_text("Combat", timeout=5000)

            page.locator("[data-combat-section-toggle='spells']").click()
            spells_panel = page.locator("[data-combat-section-panel='spells']")
            expect(spells_panel).to_be_visible(timeout=5000)
            expect(spells_panel.locator(".combat-spell-slot-row")).to_have_count(3)
            expect(spells_panel.locator("text=Use 1")).to_have_count(0)
            expect(spells_panel.locator("text=Restore 1")).to_have_count(0)
            expect(spells_panel.get_by_role("heading", name="Cantrips")).to_be_visible()
            expect(spells_panel.get_by_role("heading", name="1st level")).to_be_visible()
            expect(spells_panel.get_by_role("heading", name="2nd level")).to_be_visible()
            column_count = spells_panel.locator(".combat-spell-slot-list").evaluate(
                """(element) => getComputedStyle(element).gridTemplateColumns.split(" ").length"""
            )
            assert column_count == 3

            page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(page)
            expect(page.locator(".site-header__campaign")).to_have_text(
                "Echoes of the Alloy Coast",
                timeout=5000,
            )
            expect(page.locator("h1")).to_have_text("Session", timeout=5000)
            expect(page.locator("#session-chat-compose")).to_be_visible()
            expect(page.locator("textarea[name='body']")).to_be_visible()
            expect(page.locator("text=Post to chat")).to_be_visible()
            expect(page.locator("text=Search and choose a player-visible wiki article")).to_have_count(0)
            expect(page.locator("text=Live session tools")).to_have_count(0)
        finally:
            browser.close()


def test_session_clear_revealed_confirmation_preserves_dialog_async_and_transport_contracts(
    app,
    client,
    sign_in,
    users,
    character_read_shell_live_server,
    monkeypatch,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    for article_number, title in enumerate(
        ("First revealed contract", "Second revealed contract", "Staged contract guard"),
        start=1,
    ):
        assert client.post(
            "/campaigns/linden-pass/session/articles",
            data={"title": title, "body_markdown": f"Body for {title}."},
            follow_redirects=False,
        ).status_code == 302
        if article_number < 3:
            assert client.post(
                f"/campaigns/linden-pass/session/articles/{article_number}/reveal",
                follow_redirects=False,
            ).status_code == 302

    service = app.extensions["campaign_session_service"]
    original_clear = service.delete_revealed_articles
    reject_next_clear = {"value": True}

    def controlled_clear(*args, **kwargs):
        if reject_next_clear["value"]:
            reject_next_clear["value"] = False
            raise CampaignSessionValidationError("Known clear validation outcome.")
        return original_clear(*args, **kwargs)

    monkeypatch.setattr(service, "delete_revealed_articles", controlled_clear)
    base_url = character_read_shell_live_server
    clear_pattern = "**/campaigns/linden-pass/session/articles/clear-revealed"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(page)
            page.evaluate("document.documentElement.dataset.theme = 'parchment'")
            expect(page.locator("html")).to_have_attribute("data-theme", "parchment")

            composer = page.locator("form[data-session-composer-form] textarea[name='body']")
            expect(composer).to_be_visible(timeout=5000)
            composer.fill("Keep this unrelated Session draft through the clear workflow.")
            page.locator("[data-session-switch-target='dm']").click()

            confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            trigger = confirmation.locator("[data-presentation-dialog-trigger]")
            dialog = confirmation.locator("dialog[data-destructive-confirmation-dialog]")
            scope = confirmation.locator("[data-destructive-confirmation-scope]")
            recovery = confirmation.locator("[data-destructive-confirmation-recovery]")
            expect(confirmation).to_have_count(1, timeout=5000)
            expect(confirmation).to_have_attribute("data-destructive-confirmation-risk", "higher")
            expect(trigger).to_be_visible(timeout=5000)

            trigger.click()
            expect(dialog).to_have_attribute("open", "")
            expect(dialog.get_by_role("button", name="Cancel").first).to_be_focused()
            expect(scope).to_contain_text("all 2 revealed session articles")
            expect(scope).to_contain_text("related reveal chat and log entries")
            expect(scope).to_contain_text("Staged articles remain unchanged.")
            dialog.get_by_role("button", name="Cancel").first.click()
            expect(trigger).to_be_focused(timeout=5000)

            trigger.click()
            page.keyboard.press("Escape")
            expect(dialog).not_to_have_attribute("open", "")
            expect(trigger).to_be_focused(timeout=5000)
            trigger.click()
            dialog.dispatch_event("click")
            expect(dialog).not_to_have_attribute("open", "")
            expect(trigger).to_be_focused(timeout=5000)

            trigger.click()
            form = dialog.locator("form[data-destructive-confirmation-form]")
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            submit = form.locator("button[type='submit']")
            expect(acknowledgement).to_have_attribute("required", "")
            assert form.evaluate("element => element.checkValidity()") is False
            submit.click()
            expect(form).to_have_attribute("aria-busy", "false")
            expect(recovery).to_be_hidden()

            acknowledgement.check()
            desktop_scroll_y = page.evaluate("window.scrollY")
            submit.click()
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_contain_text(
                "Known clear validation outcome.", timeout=5000
            )
            expect(page.locator("[data-session-revealed-root] [data-destructive-confirmation]")).to_have_count(1)
            confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            trigger = confirmation.locator("[data-presentation-dialog-trigger]")
            expect(trigger).to_be_visible(timeout=5000)
            expect(confirmation.locator("[data-destructive-confirmation-recovery]")).to_be_hidden()
            assert abs(page.evaluate("window.scrollY") - desktop_scroll_y) <= 2
            _check_no_horizontal_overflow(
                page,
                "[data-session-revealed-root] [data-destructive-confirmation]",
                "session-clear-desktop-1280x900",
                required=True,
            )
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.screenshot(
                path=str(tmp_path / "session_clear_confirmation_1280x900_parchment.png")
            )

            page.set_viewport_size({"width": 390, "height": 800})
            page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(page.locator("html")).to_have_attribute("data-theme", "moonlit")
            expect(trigger).to_be_visible(timeout=5000)
            trigger.click()
            dialog = confirmation.locator("dialog[data-destructive-confirmation-dialog]")
            form = dialog.locator("form[data-destructive-confirmation-form]")
            form.locator("input[name='destructive_acknowledgement']").check()

            failure_handlers = (
                lambda route: route.fulfill(
                    status=503, content_type="text/plain", body="Unavailable"
                ),
                lambda route: route.abort("failed"),
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body="not-json"
                ),
            )
            for route_handler in failure_handlers:
                page.route(clear_pattern, route_handler)
                form.locator("button[type='submit']").click()
                recovery = dialog.locator("[data-destructive-confirmation-recovery]")
                expect(recovery).to_be_visible(timeout=5000)
                expect(recovery).to_be_focused()
                expect(recovery).to_have_text(
                    "The result could not be confirmed. Refresh Session before repeating this action."
                )
                expect(form).to_have_attribute("aria-busy", "false")
                expect(form.locator("button[type='submit']")).to_be_enabled()
                expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
                page.unroute(clear_pattern)

            _check_no_horizontal_overflow(
                page,
                "[data-session-revealed-root] [data-destructive-confirmation]",
                "session-clear-mobile-390x800",
                required=True,
            )
            expect(composer).to_have_value(
                "Keep this unrelated Session draft through the clear workflow."
            )
            page.screenshot(path=str(tmp_path / "session_clear_confirmation_390x800_moonlit.png"))

            form.locator("button[type='submit']").click()
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_contain_text(
                "Cleared 2 revealed session articles.", timeout=5000
            )
            expect(page.locator("[data-session-revealed-root] [data-destructive-confirmation]")).to_have_count(0)
            expect(page.locator("[data-session-staged-root]")).to_contain_text("Staged contract guard")
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.locator("[data-session-switch-target='session']").click()
            expect(composer).to_be_visible(timeout=5000)
            expect(composer).to_have_value(
                "Keep this unrelated Session draft through the clear workflow."
            )
        finally:
            page.close()
            browser.close()


def test_session_clear_revealed_confirmation_keeps_no_javascript_form(
    client,
    sign_in,
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    assert client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "No-JavaScript revealed article", "body_markdown": "Native clear target."},
        follow_redirects=False,
    ).status_code == 302
    assert client.post(
        "/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=False
    ).status_code == 302
    assert client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "No-JavaScript staged guard", "body_markdown": "Keep this staged."},
        follow_redirects=False,
    ).status_code == 302
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                java_script_enabled=False,
                viewport={"width": 390, "height": 800},
            )
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{base_url}/campaigns/linden-pass/session/dm")
            fallback = page.locator(
                "[data-session-revealed-root] details[data-destructive-confirmation-fallback]"
            )
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            form = fallback.locator("form")
            expect(form).to_have_attribute(
                "action", "/campaigns/linden-pass/session/articles/clear-revealed"
            )
            expect(form).to_have_attribute("method", "post")
            expect(fallback).to_contain_text("This removes all 1 revealed session article")
            expect(fallback).to_contain_text("Staged articles remain unchanged.")
            _check_no_horizontal_overflow(
                page,
                "[data-session-revealed-root] details[data-destructive-confirmation-fallback]",
                "session-clear-no-js-390x800",
                required=True,
            )
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            expect(acknowledgement).to_have_attribute("required", "")
            acknowledgement.check()
            form.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(
                    r".*/campaigns/linden-pass/session/dm#session-revealed-articles$"
                ),
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_contain_text(
                "Cleared 1 revealed session article."
            )
            expect(page.locator("[data-session-revealed-root]")).not_to_contain_text(
                "No-JavaScript revealed article"
            )
            expect(page.locator("[data-session-staged-root]")).to_contain_text(
                "No-JavaScript staged guard"
            )
        finally:
            page.close()
            context.close()
            browser.close()


def test_session_composer_feedback_preserves_state_across_success_validation_and_transport(
    app,
    client,
    sign_in,
    users,
    character_read_shell_live_server,
    monkeypatch,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    service = app.extensions["campaign_session_service"]
    original_post_message = service.post_message
    delayed_message = "Hold this draft while the async request is pending."

    def post_message_with_controlled_delay(*args, **kwargs):
        if kwargs.get("body_text") == delayed_message:
            time.sleep(1.25)
        return original_post_message(*args, **kwargs)

    monkeypatch.setattr(service, "post_message", post_message_with_controlled_delay)

    base_url = character_read_shell_live_server
    session_message_pattern = "**/campaigns/linden-pass/session/messages"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(page)
            page.evaluate("document.documentElement.dataset.theme = 'parchment'")
            expect(page.locator("html")).to_have_attribute("data-theme", "parchment")
            expect(page.locator("h1")).to_have_count(1)

            form = page.locator("form[data-session-composer-form]")
            textarea = form.locator("textarea[name='body']")
            local_feedback = form.locator("[data-session-form-feedback]")
            global_feedback = page.locator("[data-flash-stack-root] [data-feedback]")
            expect(form).to_have_attribute(
                "aria-describedby",
                "session-chat-compose-feedback",
            )

            invalid_draft = "x" * 4001
            textarea.fill(invalid_draft)
            textarea.scroll_into_view_if_needed()
            textarea.evaluate("element => { element.focus(); element.setSelectionRange(37, 61); }")
            validation_scroll_y = page.evaluate("window.scrollY")
            form.evaluate("element => element.requestSubmit()")

            expect(local_feedback).to_contain_text(
                "Session chat messages must stay under 4,000 characters.",
                timeout=5000,
            )
            expect(local_feedback.locator("[data-feedback]")).to_have_attribute(
                "data-feedback-placement",
                "persistent",
            )
            expect(local_feedback.locator("[data-feedback]")).to_have_class(
                re.compile(r"\bfeedback--persistent\b"),
            )
            expect(local_feedback.locator("[data-feedback]")).to_have_attribute(
                "aria-live",
                "assertive",
            )
            expect(form).to_have_attribute("aria-invalid", "true")
            expect(textarea).to_have_value(invalid_draft)
            assert textarea.evaluate("element => document.activeElement === element")
            assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [37, 61]
            assert abs(page.evaluate("window.scrollY") - validation_scroll_y) <= 2
            expect(global_feedback).to_have_count(0)
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.screenshot(path=str(tmp_path / "session_composer_validation_1280x900_parchment.png"))

            textarea.fill("Keyboard-submitted success from the desktop matrix.")
            submit_button = form.locator("button[type='submit']")
            submit_button.focus()
            submit_button.press("Enter")
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_text(
                "Message posted.",
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_attribute(
                "aria-live",
                "polite",
            )
            form = page.locator("form[data-session-composer-form]")
            textarea = form.locator("textarea[name='body']")
            expect(textarea).to_have_value("")
            assert textarea.evaluate("element => document.activeElement === element")
            expect(form.locator("[data-session-form-feedback] [data-feedback]")).to_have_count(0)
            assert form.get_attribute("aria-invalid") is None

            textarea.fill(delayed_message)
            textarea.evaluate("element => { element.focus(); element.setSelectionRange(10, 24); }")
            form.evaluate("element => element.requestSubmit()")
            expect(form).to_have_attribute("aria-busy", "true", timeout=500)
            expect(form.locator("button[type='submit']")).to_be_disabled()
            expect(textarea).to_have_value(delayed_message)
            assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [10, 24]
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            expect(page.locator("form[data-session-composer-form]")).not_to_have_attribute(
                "aria-busy",
                "true",
                timeout=5000,
            )
            expect(page.locator("form[data-session-composer-form] textarea[name='body']")).to_have_value("")

            transport_failures = (
                (
                    "HTTP",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="text/plain",
                        body="Unavailable",
                    ),
                ),
                ("network", lambda route: route.abort("failed")),
            )
            for failure_label, route_handler in transport_failures:
                form = page.locator("form[data-session-composer-form]")
                textarea = form.locator("textarea[name='body']")
                transport_draft = f"Keep this draft through an unavailable {failure_label} transport."
                textarea.fill(transport_draft)
                textarea.evaluate("element => { element.focus(); element.setSelectionRange(8, 19); }")
                transport_scroll_y = page.evaluate("window.scrollY")
                page.route(session_message_pattern, route_handler)
                form.evaluate("element => element.requestSubmit()")
                expect(form.locator("button[type='submit']")).to_be_enabled(timeout=5000)
                assert form.get_attribute("aria-busy") is None
                expect(textarea).to_have_value(transport_draft)
                assert textarea.evaluate("element => document.activeElement === element")
                assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [8, 19]
                assert abs(page.evaluate("window.scrollY") - transport_scroll_y) <= 2
                expect(form.locator("[data-session-form-feedback] [data-feedback]")).to_have_count(0)
                expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_text(
                    "Message posted."
                )
                page.unroute(session_message_pattern)

            page.set_viewport_size({"width": 390, "height": 800})
            page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(page.locator("html")).to_have_attribute("data-theme", "moonlit")
            textarea.fill(invalid_draft)
            textarea.scroll_into_view_if_needed()
            textarea.evaluate("element => { element.focus(); element.setSelectionRange(101, 125); }")
            mobile_scroll_y = page.evaluate("window.scrollY")
            form.evaluate("element => element.requestSubmit()")
            expect(form.locator("[data-session-form-feedback] [data-feedback]")).to_contain_text(
                "Session chat messages must stay under 4,000 characters.",
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_count(0)
            expect(textarea).to_have_value(invalid_draft)
            assert textarea.evaluate("element => document.activeElement === element")
            assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [101, 125]
            assert abs(page.evaluate("window.scrollY") - mobile_scroll_y) <= 2
            document_width = page.evaluate(
                "(document.scrollingElement || document.documentElement).scrollWidth"
            )
            assert document_width <= 392
            expect(page.locator("h1")).to_have_count(1)
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.screenshot(path=str(tmp_path / "session_composer_validation_390x800_moonlit.png"))
        finally:
            page.close()
            browser.close()


def test_session_composer_feedback_keeps_no_javascript_fallback(
    client,
    sign_in,
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                java_script_enabled=False,
                viewport={"width": 390, "height": 800},
            )
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            form = page.locator("form[data-session-composer-form]")
            expect(form).to_be_visible(timeout=5000)
            form.locator("textarea[name='body']").fill("Native no-JavaScript session message.")
            form.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(r".*/campaigns/linden-pass/session#session-chat-compose$"),
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_text(
                "Message posted."
            )
            expect(page.locator("[data-session-chat-card]")).to_contain_text(
                "Native no-JavaScript session message."
            )
            expect(page.locator("h1")).to_have_count(1)
            expect(page.locator("form[data-session-composer-form] textarea[name='body']")).to_have_value("")
        finally:
            page.close()
            context.close()
            browser.close()


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
    portrait_url_pattern = re.compile(
        r"^.*/campaigns/linden-pass/characters/arden-march\?.*page=portrait.*$"
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
            assert quick_row_columns == 3
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
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Vitals updated.",
                timeout=5000,
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
            expect(page.locator("[data-flash-stack-root] .flash-error")).to_have_text(
                "This sheet changed in another session. Refresh the page and try again.",
                timeout=5000,
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
            spell_card_columns = page.locator(".spell-card-grid").nth(0).evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert spell_card_columns <= 3
            spell_trigger = page.locator("[data-character-spell-modal-trigger]").first
            expect(spell_trigger).to_be_visible(timeout=5000)
            open_page_count = len(page.context.pages)
            spell_trigger.click()
            spell_dialog = page.locator("dialog[data-character-spell-modal][open]").first
            expect(spell_dialog).to_be_visible(timeout=5000)
            assert len(page.context.pages) == open_page_count
            page.keyboard.press("Escape")
            expect(page.locator("dialog[data-character-spell-modal][open]")).to_have_count(0, timeout=5000)
            expect(spell_trigger).to_be_focused(timeout=5000)

            page.goto(f"{arden_character_slug_path}?mode=read&page=notes")
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='player_notes_markdown']")).to_be_visible(timeout=5000)

            notes_draft = "Browser draft to preserve."
            portrait_draft = "Portrait caption draft from browser flow."
            page.locator("textarea[name='player_notes_markdown']").fill(notes_draft)
            page.locator("[data-character-read-target-subpage='portrait']").click()
            expect(page).to_have_url(portrait_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='background_markdown']")).to_have_count(0)
            expect(page.locator("button:has-text('Save personal details')")).to_have_count(0)
            page.locator("input[name='portrait_caption']").fill(portrait_draft)

            page.go_back()
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                notes_draft,
                timeout=5000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)

            page.go_forward()
            expect(page.locator("input[name='portrait_caption']")).to_have_value(
                portrait_draft,
                timeout=5000,
            )
            expect(page).to_have_url(portrait_url_pattern, timeout=5000)

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
