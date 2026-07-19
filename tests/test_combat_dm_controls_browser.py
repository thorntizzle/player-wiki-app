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


def test_flask_dm_status_advance_turn_rerenders_without_navigation_or_workspace_loss(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        first = service.add_npc_combatant(
            "linden-pass",
            display_name="First Watch",
            turn_value=18,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        second = service.add_npc_combatant(
            "linden-pass",
            display_name="Second Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        service.set_current_turn(
            "linden-pass",
            first.id,
            updated_by_user_id=users["dm"]["id"],
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={first.id}"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(page_url)

            live_root = page.locator("[data-combat-live-root]")
            detail_root = page.locator("[data-combat-status-detail-content-root]")
            first_card = page.locator(
                f'[data-combatant-carousel-card][data-combatant-id="{first.id}"]'
            )
            second_card = page.locator(
                f'[data-combatant-carousel-card][data-combatant-id="{second.id}"]'
            )
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(first.id))
            expect(first_card).to_have_attribute("data-combatant-current-turn", "true")
            expect(first_card).to_have_attribute("data-combatant-selected", "true")
            expect(detail_root.get_by_role("heading", name="First Watch", exact=True)).to_be_visible()

            live_root.evaluate("element => { element.dataset.browserWorkspaceProbe = 'retained'; }")
            page.get_by_role("button", name="Advance turn", exact=True).click()

            expect(second_card).to_have_attribute("data-combatant-current-turn", "true", timeout=5000)
            expect(first_card).to_have_attribute("data-combatant-current-turn", "false")
            expect(first_card).to_have_attribute("data-combatant-selected", "true")
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(first.id))
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            expect(detail_root.get_by_role("heading", name="First Watch", exact=True)).to_be_visible()
            assert page.url == page_url
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_dm_status_add_condition_rerenders_without_navigation_or_focus_loss(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Condition Watch",
            turn_value=14,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(page_url)

            live_root = page.locator("[data-combat-live-root]")
            detail_root = page.locator("[data-combat-status-detail-content-root]")
            add_editor = detail_root.locator("details.combat-condition-editor--add")
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(combatant.id))
            expect(detail_root.get_by_role("heading", name="Condition Watch", exact=True)).to_be_visible()

            live_root.evaluate("element => { element.dataset.browserWorkspaceProbe = 'retained'; }")
            add_editor.locator("summary").click()
            add_form = add_editor.locator("form")
            add_form.locator('input[name="condition_name"]').fill("Frightened")
            add_form.locator('input[name="duration_text"]').fill("Until the next save")
            add_form.get_by_role("button", name="Add condition", exact=True).click()

            condition_item = detail_root.locator(".combat-condition-item").filter(has_text="Frightened")
            expect(condition_item.locator("strong")).to_have_text("Frightened", timeout=5000)
            expect(condition_item.locator(".meta")).to_have_text("Until the next save")
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(combatant.id))
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            expect(detail_root.get_by_role("heading", name="Condition Watch", exact=True)).to_be_visible()
            assert page.url == page_url
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_dm_status_remove_selected_combatant_falls_back_without_navigation(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        selected = service.add_npc_combatant(
            "linden-pass",
            display_name="Selected Cleanup Watch",
            turn_value=18,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        survivor = service.add_npc_combatant(
            "linden-pass",
            display_name="Surviving Cleanup Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    initial_page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={selected.id}"
    survivor_page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={survivor.id}"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(initial_page_url)

            live_root = page.locator("[data-combat-live-root]")
            detail_root = page.locator("[data-combat-status-detail-content-root]")
            selected_card = page.locator(
                f'[data-combatant-carousel-card][data-combatant-id="{selected.id}"]'
            )
            survivor_card = page.locator(
                f'[data-combatant-carousel-card][data-combatant-id="{survivor.id}"]'
            )
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(selected.id))
            expect(selected_card).to_have_attribute("data-combatant-selected", "true")
            expect(detail_root.get_by_role("heading", name="Selected Cleanup Watch", exact=True)).to_be_visible()

            live_root.evaluate("element => { element.dataset.browserWorkspaceProbe = 'retained'; }")
            remove_trigger = page.locator(
                '[data-presentation-dialog-trigger^="combat-remove-confirmation-"]'
            )
            remove_trigger.click()
            remove_dialog = page.locator("[data-destructive-confirmation-dialog]")
            expect(remove_dialog).to_be_visible()
            remove_dialog.get_by_role("button", name="Remove combatant", exact=True).click()

            expect(live_root).to_have_attribute(
                "data-selected-combatant-id",
                str(survivor.id),
                timeout=5000,
            )
            expect(selected_card).to_have_count(0)
            expect(survivor_card).to_have_attribute("data-combatant-selected", "true")
            expect(detail_root.get_by_role("heading", name="Surviving Cleanup Watch", exact=True)).to_be_visible()
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            assert page.url == survivor_page_url
        finally:
            page.close()
            context.close()
            browser.close()


@pytest.mark.parametrize(
    ("viewport", "theme"),
    [
        ({"width": 1280, "height": 900}, "parchment"),
        ({"width": 390, "height": 800}, "moonlit"),
    ],
)
def test_flask_dm_remove_confirmation_cancel_and_ambiguous_recovery_browser(
    app,
    combat_dm_controls_live_server,
    users,
    viewport,
    theme,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name=f"{theme.title()} Recovery Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport=viewport)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(page_url)
            page.evaluate("theme => { document.documentElement.dataset.theme = theme; }", theme)
            assert page.locator("html").get_attribute("data-theme") == theme

            trigger = page.locator(
                f'[data-presentation-dialog-trigger="combat-remove-confirmation-{combatant.id}"]'
            )
            dialog = page.locator(f"#combat-remove-confirmation-{combatant.id}")
            page.evaluate(
                """() => {
                    window.__playerWikiPresentationController.init(document);
                    window.__playerWikiPresentationController.init(document);
                }"""
            )
            trigger.focus()
            scroll_before = page.evaluate("window.scrollY")
            trigger.click()
            expect(dialog).to_be_visible()
            expect(dialog.get_by_role(
                "heading",
                name=f"Remove {theme.title()} Recovery Watch?",
            )).to_be_visible()
            expect(dialog).to_contain_text("linked character, statblock, Systems entry, and source records remain unchanged")
            dialog.get_by_role("button", name="Cancel", exact=True).first.click()
            expect(dialog).not_to_be_visible()
            expect(trigger).to_be_focused()
            assert abs(page.evaluate("window.scrollY") - scroll_before) <= 1

            trigger.click()
            expect(dialog).to_be_visible()
            page.keyboard.press("Escape")
            expect(dialog).not_to_be_visible()
            expect(trigger).to_be_focused()

            trigger.click()
            expect(dialog).to_be_visible()
            dialog.click(position={"x": 2, "y": 2})
            expect(dialog).not_to_be_visible()
            expect(trigger).to_be_focused()

            page.route(
                re.compile(rf".*/combat/combatants/{combatant.id}/delete$"),
                lambda route: route.abort(),
            )
            trigger.click()
            dialog.get_by_role("button", name="Remove combatant", exact=True).click()
            recovery = dialog.locator("[data-destructive-confirmation-recovery]")
            expect(recovery).to_be_visible(timeout=5000)
            expect(recovery).to_have_text(
                "The result could not be confirmed. Refresh Combat before repeating this action."
            )
            expect(recovery).to_be_focused()
            expect(dialog.locator("form[data-destructive-confirmation-form]")).to_have_attribute(
                "aria-busy", "false"
            )
            expect(page.locator(".app-loading-cover")).not_to_be_visible()
            expect(page.locator("html")).not_to_have_class(re.compile(r"(?:^|\s)app-loading(?:\s|$)"))
            overflow = page.evaluate(
                "document.documentElement.scrollWidth - window.innerWidth"
            )
            assert overflow <= 1
            with app.app_context():
                assert app.extensions["campaign_combat_service"].get_combatant(
                    "linden-pass", combatant.id
                ) is not None
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_dm_clear_confirmation_requires_acknowledgement_and_resets_browser(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        first = service.add_npc_combatant(
            "linden-pass",
            display_name="Clear First Watch",
            turn_value=18,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        second = service.add_npc_combatant(
            "linden-pass",
            display_name="Clear Second Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        service.set_current_turn(
            "linden-pass", first.id, updated_by_user_id=users["dm"]["id"]
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")
    base_url = combat_dm_controls_live_server
    page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={second.id}&view=controls"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(page_url)
            live_root = page.locator("[data-combat-live-root]")
            live_root.evaluate("element => { element.dataset.browserWorkspaceProbe = 'retained'; }")
            trigger = page.locator('[data-presentation-dialog-trigger="combat-clear-confirmation"]')
            trigger.click()
            dialog = page.locator("#combat-clear-confirmation")
            expect(dialog).to_be_visible()
            expect(dialog).to_contain_text("Higher-risk confirmation")
            expect(dialog).to_contain_text("Round resets to 1 and the current turn is cleared.")
            submit = dialog.get_by_role("button", name="Clear tracker", exact=True)
            submit.click()
            expect(dialog).to_be_visible()
            acknowledgement = dialog.locator('input[name="destructive_acknowledgement"]')
            expect(acknowledgement).not_to_be_checked()
            acknowledgement.check()
            submit.click()
            expect(page.get_by_text("Combat tracker cleared.", exact=True)).to_be_visible(timeout=5000)
            expect(live_root).to_have_attribute("data-selected-combatant-id", "")
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            assert page.url == f"{base_url}/campaigns/linden-pass/combat/dm?view=controls"
            expect(page.locator(".app-loading-cover")).not_to_be_visible()
            expect(page.locator("html")).not_to_have_class(re.compile(r"(?:^|\s)app-loading(?:\s|$)"))
            with app.app_context():
                tracker = app.extensions["campaign_combat_service"].get_tracker("linden-pass")
                assert tracker.round_number == 1
                assert tracker.current_combatant_id is None
                assert app.extensions["campaign_combat_service"].list_combatants("linden-pass") == []
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_dm_cleanup_no_javascript_fallbacks_are_explicit_real_forms(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="No JS Cleanup Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")
    base_url = combat_dm_controls_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 390, "height": 800}, java_script_enabled=False
            )
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
            )
            expect(page.locator('[data-presentation-dialog-trigger^="combat-remove-confirmation-"]')).not_to_be_visible()
            remove_fallback = page.locator("[data-destructive-confirmation-fallback]")
            remove_fallback.locator("summary").click()
            expect(remove_fallback).to_contain_text("Remove No JS Cleanup Watch?")
            remove_form = remove_fallback.locator("form")
            expect(remove_form).to_have_attribute(
                "action",
                f"/campaigns/linden-pass/combat/combatants/{combatant.id}/delete",
            )
            expect(remove_form.locator('input[name="_csrf_token"]')).to_have_count(1)

            page.goto(
                f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}&view=controls"
            )
            expect(page.locator('[data-presentation-dialog-trigger="combat-clear-confirmation"]')).not_to_be_visible()
            clear_fallback = page.locator("[data-destructive-confirmation-fallback]")
            clear_fallback.locator("summary").click()
            expect(clear_fallback).to_contain_text("Clear combat tracker?")
            clear_form = clear_fallback.locator("form")
            expect(clear_form).to_have_attribute(
                "action", "/campaigns/linden-pass/combat/clear"
            )
            expect(clear_form.locator('input[name="destructive_acknowledgement"]')).to_be_visible()
            expect(clear_form.locator('input[name="_csrf_token"]')).to_have_count(1)
            assert page.locator("html").evaluate("el => el.scrollWidth - innerWidth") <= 1
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_dm_remove_known_failure_stays_controller_owned_browser(
    app,
    combat_dm_controls_live_server,
    users,
    monkeypatch,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Known Failure Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    from player_wiki.campaign_combat_service import CampaignCombatValidationError

    def fail_delete(*args, **kwargs):
        raise CampaignCombatValidationError("Known cleanup blocker.")

    monkeypatch.setattr(service, "delete_combatant", fail_delete)
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")
    base_url = combat_dm_controls_live_server
    page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(page_url)
            page.locator(
                f'[data-presentation-dialog-trigger="combat-remove-confirmation-{combatant.id}"]'
            ).click()
            dialog = page.locator(f"#combat-remove-confirmation-{combatant.id}")
            dialog.get_by_role("button", name="Remove combatant", exact=True).click()
            expect(page.get_by_text("Known cleanup blocker.", exact=True)).to_be_visible(timeout=5000)
            expect(dialog).not_to_be_visible()
            expect(page.locator("[data-destructive-confirmation-recovery]")).not_to_be_visible()
            assert page.url == page_url
            with app.app_context():
                assert service.get_combatant("linden-pass", combatant.id) is not None
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_cleanup_confirmation_preserves_player_absence_and_admin_access_browser(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Access Boundary Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")
    base_url = combat_dm_controls_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            player_context = browser.new_context(viewport={"width": 390, "height": 800})
            admin_context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        player_page = player_context.new_page()
        admin_page = admin_context.new_page()
        try:
            _sign_in(
                player_page,
                base_url,
                email=users["owner"]["email"],
                password=users["owner"]["password"],
            )
            player_response = player_page.goto(
                f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
            )
            assert player_response is not None
            assert player_response.status == 403
            expect(player_page.locator("[data-destructive-confirmation]")).to_have_count(0)

            _sign_in(
                admin_page,
                base_url,
                email=users["admin"]["email"],
                password=users["admin"]["password"],
            )
            admin_page.goto(
                f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
            )
            remove_trigger = admin_page.locator(
                f'[data-presentation-dialog-trigger="combat-remove-confirmation-{combatant.id}"]'
            )
            expect(remove_trigger).to_be_visible()
            admin_page.goto(
                f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}&view=controls"
            )
            expect(admin_page.locator(
                '[data-presentation-dialog-trigger="combat-clear-confirmation"]'
            )).to_be_visible()
        finally:
            player_page.close()
            admin_page.close()
            player_context.close()
            admin_context.close()
            browser.close()


def test_flask_dm_status_player_detail_visibility_rerenders_without_navigation_or_workspace_loss(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Visibility Browser Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    page_url = f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(page_url)

            live_root = page.locator("[data-combat-live-root]")
            detail_root = page.locator("[data-combat-status-detail-content-root]")
            authority_root = page.locator("[data-combat-status-authority-root]")
            visibility_form = authority_root.locator(
                f'form[action$="/combat/combatants/{combatant.id}/player-detail-visibility"]'
            )
            expected_revision = visibility_form.locator(
                'input[name="expected_combatant_revision"]'
            )
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(combatant.id))
            expect(detail_root.get_by_role("heading", name="Visibility Browser Watch", exact=True)).to_be_visible()
            expect(visibility_form).to_contain_text(
                "Players currently see only this NPC's name, turn information, and conditions."
            )
            expect(expected_revision).to_have_value(str(combatant.revision))

            live_root.evaluate("element => { element.dataset.browserWorkspaceProbe = 'retained'; }")
            visibility_form.get_by_role(
                "button",
                name="Show NPC detail to players",
                exact=True,
            ).click()

            expect(visibility_form).to_contain_text(
                "Players can currently see this NPC's vitals and action economy.",
                timeout=5000,
            )
            expect(visibility_form.get_by_role(
                "button",
                name="Hide NPC detail from players",
                exact=True,
            )).to_be_visible()
            expect(expected_revision).to_have_value(str(combatant.revision + 1))
            expect(live_root).to_have_attribute("data-selected-combatant-id", str(combatant.id))
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            expect(detail_root.get_by_role("heading", name="Visibility Browser Watch", exact=True)).to_be_visible()
            assert page.url == page_url
        finally:
            page.close()
            context.close()
            browser.close()


def test_flask_dm_controls_basic_seeding_preserves_workspace_and_custom_form_mode(
    app,
    combat_dm_controls_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    initial_url = f"{base_url}/campaigns/linden-pass/combat/dm?view=controls"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(initial_url)

            live_root = page.locator("[data-combat-live-root]")
            controls_root = page.locator("[data-combat-controls-root]")
            player_form = controls_root.locator(
                'form[action$="/combat/player-combatants"]'
            )
            expect(page.locator("#combat-add-mode-player")).to_be_checked()
            live_root.evaluate("element => { element.dataset.browserWorkspaceProbe = 'retained'; }")
            player_form.locator('select[name="character_slug"]').select_option("arden-march")
            player_form.get_by_role("button", name="Add player character", exact=True).click()

            expect(page.get_by_text(
                "Player character added to the combat tracker.",
                exact=True,
            )).to_be_visible(timeout=5000)
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            expect(player_form.locator('option[value="arden-march"]')).to_have_count(0)

            with app.app_context():
                combatants = app.extensions["campaign_combat_service"].list_combatants(
                    "linden-pass"
                )
            assert len(combatants) == 1
            player_combatant = combatants[0]
            assert player_combatant.character_slug == "arden-march"
            canonical_url = (
                f"{base_url}/campaigns/linden-pass/combat/dm"
                f"?combatant={player_combatant.id}&view=controls"
            )
            assert page.url == canonical_url

            page.get_by_text("Add custom combatant", exact=True).click()
            expect(page.locator("#combat-add-mode-custom")).to_be_checked()
            custom_form = controls_root.locator(
                'form[action$="/combat/npc-combatants"]'
            )
            custom_form.locator('input[name="display_name"]').fill("Browser Seed Watch")
            custom_form.locator('input[name="turn_value"]').fill("11")
            custom_form.locator('input[name="initiative_priority"]').fill("3")
            custom_form.locator('input[name="dexterity_modifier"]').fill("2")
            custom_form.locator('input[name="current_hp"]').fill("14")
            custom_form.locator('input[name="max_hp"]').fill("16")
            custom_form.locator('input[name="temp_hp"]').fill("1")
            custom_form.locator('input[name="movement_total"]').fill("35")
            custom_form.get_by_role("button", name="Add NPC combatant", exact=True).click()

            expect(page.get_by_text(
                "NPC combatant added to the combat tracker.",
                exact=True,
            )).to_be_visible(timeout=5000)
            expect(page.locator("#combat-add-mode-custom")).to_be_checked()
            expect(live_root).to_have_attribute("data-browser-workspace-probe", "retained")
            expect(custom_form.locator('input[name="display_name"]')).to_have_value(
                "Browser Seed Watch"
            )
            expect(custom_form.locator('input[name="turn_value"]')).to_have_value("11")
            expect(custom_form.locator('input[name="initiative_priority"]')).to_have_value("3")
            expect(custom_form.locator('input[name="dexterity_modifier"]')).to_have_value("2")
            expect(custom_form.locator('input[name="current_hp"]')).to_have_value("14")
            expect(custom_form.locator('input[name="max_hp"]')).to_have_value("16")
            expect(custom_form.locator('input[name="temp_hp"]')).to_have_value("1")
            expect(custom_form.locator('input[name="movement_total"]')).to_have_value("35")
            assert page.url == canonical_url

            with app.app_context():
                combatants = app.extensions["campaign_combat_service"].list_combatants(
                    "linden-pass"
                )
            assert [combatant.display_name for combatant in combatants] == [
                "Browser Seed Watch",
                "Arden March",
            ]
            npc = next(row for row in combatants if row.display_name == "Browser Seed Watch")
            assert npc.source_kind == "manual_npc"
            assert npc.player_detail_visible is False
            assert npc.turn_value == 11
            assert npc.dexterity_modifier == 2
            assert npc.initiative_priority == 3
            assert npc.current_hp == 14
            assert npc.max_hp == 16
            assert npc.temp_hp == 1
            assert npc.movement_total == 35
        finally:
            page.close()
            context.close()
            browser.close()

