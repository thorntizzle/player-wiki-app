import re
import threading
import time
from copy import deepcopy

import player_wiki.app as app_module
import pytest
import yaml
from tests.helpers.character_builder_fakes import (
    _builder_context_fixture,
    _level_up_context_fixture,
    _minimal_character_definition,
    _minimal_import_metadata,
)
from tests.helpers.systems_seed_helpers import _seed_systems_item_entry


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


def _write_character_definition(app, character_slug: str, mutator) -> None:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


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
    page.wait_for_function(
        """() => {
            const root = document.documentElement;
            return !root.classList.contains("app-loading")
                && !root.classList.contains("app-loading-closing");
        }""",
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
            page.wait_for_function("window.location.search.includes('page=portrait')")
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
