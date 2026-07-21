import re
import threading
from pathlib import Path

import pytest

from tests.helpers.character_state_helpers import _write_character_definition


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
            trigger.scroll_into_view_if_needed()
            trigger.click(trial=True)
            trigger.focus()
            expect(trigger).to_be_focused()
            page.wait_for_function(
                """() => {
                    const scrollY = window.scrollY;
                    const probe = window.__combatRemoveScrollStabilityProbe;
                    if (!probe || probe.scrollY !== scrollY) {
                        window.__combatRemoveScrollStabilityProbe = {scrollY, stableFrames: 0};
                        return false;
                    }
                    probe.stableFrames += 1;
                    return probe.stableFrames >= 2;
                }"""
            )
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

            mutation_requests = []

            def abort_mutation(route):
                mutation_requests.append(route.request.url)
                route.abort()

            page.route(
                re.compile(rf".*/combat/combatants/{combatant.id}/delete$"),
                abort_mutation,
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
            expect(dialog.locator("form[data-destructive-confirmation-form]")).to_have_attribute(
                "data-live-mutation-state", "mutation-unknown"
            )
            assert len(mutation_requests) == 1
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


def test_flask_dm_status_explicit_revision_conflict_is_not_retried_browser(
    app,
    combat_dm_controls_live_server,
    users,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Conflict Watch",
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
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = context.new_page()
        mutation_requests = []
        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])
            page.goto(f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}")
            form = page.locator(
                f'form[action$="/combat/combatants/{combatant.id}/player-detail-visibility"]'
            )
            expect(form).to_be_visible()

            def conflict_response(route):
                mutation_requests.append(route.request.url)
                route.fulfill(
                    status=200,
                    headers={
                        "Content-Type": "application/json",
                        "X-Live-Mutation-Outcome": "combatant-revision-conflict",
                    },
                    body='{"ok": false}',
                )

            page.route(
                re.compile(rf".*/combat/combatants/{combatant.id}/player-detail-visibility$"),
                conflict_response,
            )
            form.locator('button[type="submit"]').click()

            expect(form).to_have_attribute(
                "data-live-mutation-state", "revision-conflict", timeout=400
            )
            expect(page.locator("[data-live-read-status-message]")).to_have_text(
                "This view changed elsewhere. Refresh and review before repeating the action.",
                timeout=400,
            )
            expect(page.locator("[data-live-safe-read-retry]")).to_be_visible(timeout=400)
            assert len(mutation_requests) == 1
            page.wait_for_timeout(100)
            assert len(mutation_requests) == 1
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


def test_flask_combat_selected_pc_shared_dialog_adopter_preserves_surface_and_replacement_contracts(
    app,
    client,
    sign_in,
    combat_dm_controls_live_server,
    users,
    tmp_path,
):
    def add_dialog_examples(payload):
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog.append(
            {
                "id": "combat-dialog-stormglass-compass",
                "name": "Stormglass Compass",
                "default_quantity": 1,
                "weight": "1 lb.",
                "notes": "Keep the face covered in bright rain.",
                "tags": ["wondrous"],
                "page_ref": {
                    "slug": "items/stormglass-compass",
                    "title": "Stormglass Compass",
                },
            }
        )
        payload["equipment_catalog"] = equipment_catalog

        spellcasting = dict(payload.get("spellcasting") or {})
        spells = []
        for spell in list(spellcasting.get("spells") or []):
            spell_payload = dict(spell or {})
            if str(spell_payload.get("name") or "").strip() == "Message":
                spell_payload["page_ref"] = {
                    "slug": "spells/message",
                    "title": "Message",
                }
            spells.append(spell_payload)
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", add_dialog_examples)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    ).status_code == 302
    with app.app_context():
        combatant = next(
            combatant
            for combatant in app.extensions["campaign_combat_service"].list_combatants(
                "linden-pass"
            )
            if combatant.source_ref == "arden-march"
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    player_url = f"{base_url}/campaigns/linden-pass/combat?combatant={combatant.id}"
    character_url = (
        f"{base_url}/campaigns/linden-pass/combat/character?combatant={combatant.id}"
    )
    canonical_status_url = (
        f"{base_url}/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    )
    compatibility_status_url = (
        f"{base_url}/campaigns/linden-pass/combat/status?combatant={combatant.id}"
    )

    def wait_for_loading(page):
        expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(
            0, timeout=5000
        )

    def workspace(page):
        scope = page.locator("[data-combat-workspace-root]")
        expect(scope).to_have_attribute(
            "data-combat-presentation-dialog-state", "ready", timeout=5000
        )
        expect(scope.locator("[data-combat-presentation-dialog-trigger-gate]")).to_have_count(0)
        expect(
            scope.locator("template[data-combat-presentation-dialog-trigger-template]")
        ).to_have_count(0)
        return scope

    def assert_dialog_label(page, dialog):
        labelled_by = dialog.get_attribute("aria-labelledby")
        assert labelled_by
        label = page.locator(f"#{labelled_by}")
        expect(label).to_have_count(1)
        assert label.inner_text().strip()

    def replace_workspace_from_fresh_response(page, section_slug):
        page.evaluate(
            """async (sectionSlug) => {
                const response = await fetch(window.location.href, {
                    credentials: "same-origin",
                    cache: "no-store",
                });
                if (!response.ok) {
                    throw new Error(`fresh workspace request failed: ${response.status}`);
                }
                const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
                const current = document.querySelector("[data-combat-workspace-root]");
                const replacement = parsed.querySelector("[data-combat-workspace-root]");
                if (!(current instanceof HTMLElement) || !(replacement instanceof HTMLElement)) {
                    throw new Error("fresh combat workspace missing");
                }
                current.replaceWith(replacement);
                window.__playerWikiCombatWorkspace.restore(replacement, sectionSlug);
            }""",
            section_slug,
        )

    test_controller_source = r"""
      (() => {
        const returnTargets = new WeakMap();
        window.__installCombatDialogTestController = (mode) => {
          const closeDialog = (dialog) => {
            if (!(dialog instanceof HTMLDialogElement) || !dialog.hasAttribute("open")) return false;
            dialog.close();
            return true;
          };
          const init = (scope) => {
            if (mode === "throws") throw new Error("test presentation init failure");
            if (mode === "no-op") return 0;
            for (const dialog of scope.querySelectorAll("dialog[data-presentation-dialog]")) {
              if (!dialog.dataset.combatTestPresentationInit) {
                dialog.dataset.combatTestPresentationInit = "1";
                dialog.addEventListener("click", (event) => {
                  if (event.target === dialog) closeDialog(dialog);
                });
                dialog.addEventListener("close", () => {
                  const target = returnTargets.get(dialog);
                  returnTargets.delete(dialog);
                  if (target instanceof HTMLElement && target.isConnected) target.focus();
                });
                for (const close of dialog.querySelectorAll("[data-presentation-dialog-close]")) {
                  close.addEventListener("click", () => closeDialog(dialog));
                }
              }
            }
            for (const trigger of scope.querySelectorAll("[data-presentation-dialog-trigger]")) {
              const target = document.getElementById(trigger.dataset.presentationDialogTrigger || "");
              if (target instanceof HTMLDialogElement && target.hasAttribute("data-presentation-dialog")) {
                trigger.hidden = false;
              }
            }
            return 1;
          };
          const openDialog = (dialog, trigger) => {
            if (!(dialog instanceof HTMLDialogElement)) return false;
            if (trigger instanceof HTMLElement) returnTargets.set(dialog, trigger);
            dialog.showModal();
            const initial = dialog.querySelector("[data-presentation-dialog-initial-focus]");
            if (initial instanceof HTMLElement) initial.focus();
            return true;
          };
          window.__playerWikiPresentationController = Object.freeze({ init, openDialog, closeDialog });
          if (!window.__combatDialogTestDelegation) {
            window.__combatDialogTestDelegation = true;
            document.addEventListener("click", (event) => {
              const trigger = event.target instanceof Element
                ? event.target.closest("[data-presentation-dialog-trigger]")
                : null;
              if (!(trigger instanceof HTMLElement)) return;
              const dialog = document.getElementById(trigger.dataset.presentationDialogTrigger || "");
              if (window.__playerWikiPresentationController.openDialog(dialog, trigger)) {
                event.preventDefault();
              }
            });
          }
        };
      })();
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
        desktop_page = desktop_context.new_page()
        try:
            _sign_in(
                desktop_page,
                base_url,
                email=users["owner"]["email"],
                password=users["owner"]["password"],
            )
            desktop_page.goto(player_url)
            wait_for_loading(desktop_page)
            desktop_page.evaluate("document.documentElement.dataset.theme = 'parchment'")
            expect(desktop_page.locator("html")).to_have_attribute("data-theme", "parchment")
            scope = workspace(desktop_page)
            expect(desktop_page.locator("html")).to_have_class(re.compile(r"spell-modal-js"))
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))

            scope.locator("[data-combat-section-toggle='inventory']").click()
            item_link = scope.get_by_role("link", name="Stormglass Compass").first
            expect(item_link).to_have_attribute(
                "href", "/campaigns/linden-pass/pages/items/stormglass-compass"
            )
            item_trigger = scope.locator("button.item-detail-button").first
            item_trigger.click()
            item_dialog = scope.locator("dialog.item-detail-dialog[open]").first
            expect(item_dialog).to_be_visible(timeout=5000)
            assert_dialog_label(desktop_page, item_dialog)
            expect(item_dialog.locator("[data-presentation-dialog-initial-focus]")).to_be_focused()
            desktop_page.screenshot(
                path=str(tmp_path / "combat_dialog_player_item_1280x900_parchment.png")
            )
            item_dialog.get_by_role("button", name="Close").click()
            expect(item_trigger).to_be_focused(timeout=5000)
            item_trigger.click()
            item_dialog.dispatch_event("click")
            expect(item_dialog).to_be_hidden(timeout=5000)
            expect(item_trigger).to_be_focused(timeout=5000)

            scope.locator("[data-combat-section-toggle='spells']").click()
            spell_trigger = scope.locator(
                "[data-character-spell-modal-trigger]", has_text="Message"
            ).first
            spell_trigger.click()
            spell_dialog = scope.locator(
                "dialog[data-presentation-dialog][open]", has_text="Message"
            )
            expect(spell_dialog).to_be_visible(timeout=5000)
            assert_dialog_label(desktop_page, spell_dialog)
            desktop_page.screenshot(
                path=str(tmp_path / "combat_dialog_player_spell_1280x900_parchment.png")
            )
            desktop_page.keyboard.press("Escape")
            expect(spell_dialog).to_be_hidden(timeout=5000)
            expect(spell_trigger).to_be_focused(timeout=5000)
        finally:
            desktop_page.close()
            desktop_context.close()

        dm_context = browser.new_context(viewport={"width": 1280, "height": 900})
        dm_page = dm_context.new_page()
        try:
            _sign_in(
                dm_page,
                base_url,
                email=users["dm"]["email"],
                password=users["dm"]["password"],
            )
            final_response = dm_page.goto(compatibility_status_url)
            assert final_response is not None
            redirected_request = final_response.request.redirected_from
            assert redirected_request is not None
            redirect_response = redirected_request.response()
            assert redirect_response is not None
            assert redirect_response.status == 302
            assert redirect_response.headers["location"] == (
                f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
            )
            assert dm_page.url == canonical_status_url
            wait_for_loading(dm_page)
            dm_page.evaluate("document.documentElement.dataset.theme = 'parchment'")
            scope = workspace(dm_page)
            scope.locator("[data-combat-section-toggle='inventory']").click()
            replace_workspace_from_fresh_response(dm_page, "inventory")
            replacement_scope = workspace(dm_page)
            expect(replacement_scope.locator("button.item-detail-button").first).to_be_visible(
                timeout=5000
            )
            replacement_scope.locator("button.item-detail-button").first.click()
            replacement_dialog = replacement_scope.locator(
                "dialog.item-detail-dialog[open]"
            ).first
            expect(replacement_dialog).to_be_visible(timeout=5000)
            assert_dialog_label(dm_page, replacement_dialog)
            dm_page.screenshot(
                path=str(tmp_path / "combat_dialog_status_redirect_1280x900.png")
            )
            replacement_dialog.get_by_role("button", name="Close").click()
            expect(replacement_scope.locator("button.item-detail-button").first).to_be_focused()
        finally:
            dm_page.close()
            dm_context.close()

        mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        mobile_page = mobile_context.new_page()
        try:
            _sign_in(
                mobile_page,
                base_url,
                email=users["owner"]["email"],
                password=users["owner"]["password"],
            )
            mobile_page.goto(character_url)
            wait_for_loading(mobile_page)
            mobile_page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(mobile_page.locator("html")).to_have_attribute("data-theme", "moonlit")
            mobile_scope = workspace(mobile_page)
            mobile_scope.locator("[data-combat-section-toggle='inventory']").click()
            mobile_trigger = mobile_scope.locator("button.item-detail-button").first
            expect(mobile_trigger).to_be_visible(timeout=5000)
            mobile_trigger.click()
            mobile_dialog = mobile_scope.locator("dialog.item-detail-dialog[open]").first
            expect(mobile_dialog).to_be_visible(timeout=5000)
            expect(mobile_dialog.locator("[data-presentation-dialog-initial-focus]")).to_be_focused()
            assert mobile_page.evaluate(
                "document.documentElement.scrollWidth - window.innerWidth"
            ) <= 1
            mobile_page.screenshot(
                path=str(tmp_path / "combat_dialog_character_390x800_moonlit.png")
            )
            mobile_dialog.get_by_role("button", name="Close").click()
            expect(mobile_trigger).to_be_focused(timeout=5000)
        finally:
            mobile_page.close()
            mobile_context.close()

        mobile_dm_context = browser.new_context(viewport={"width": 390, "height": 800})
        mobile_dm_page = mobile_dm_context.new_page()
        try:
            _sign_in(
                mobile_dm_page,
                base_url,
                email=users["dm"]["email"],
                password=users["dm"]["password"],
            )
            final_response = mobile_dm_page.goto(compatibility_status_url)
            assert final_response is not None
            redirected_request = final_response.request.redirected_from
            assert redirected_request is not None
            redirect_response = redirected_request.response()
            assert redirect_response is not None
            assert redirect_response.status == 302
            assert mobile_dm_page.url == canonical_status_url
            wait_for_loading(mobile_dm_page)
            mobile_dm_scope = workspace(mobile_dm_page)
            mobile_dm_scope.locator("[data-combat-section-toggle='inventory']").click()
            mobile_dm_trigger = mobile_dm_scope.locator("button.item-detail-button").first
            expect(mobile_dm_trigger).to_be_visible(timeout=5000)
            mobile_dm_trigger.click()
            mobile_dm_dialog = mobile_dm_scope.locator(
                "dialog.item-detail-dialog[open]"
            ).first
            expect(mobile_dm_dialog).to_be_visible(timeout=5000)
            assert mobile_dm_page.evaluate(
                "document.documentElement.scrollWidth - window.innerWidth"
            ) <= 1
            mobile_dm_page.screenshot(
                path=str(tmp_path / "combat_dialog_status_redirect_390x800.png")
            )
            mobile_dm_dialog.get_by_role("button", name="Close").click()
            expect(mobile_dm_trigger).to_be_focused(timeout=5000)
        finally:
            mobile_dm_page.close()
            mobile_dm_context.close()

        no_js_context = browser.new_context(
            viewport={"width": 390, "height": 800}, java_script_enabled=False
        )
        no_js_page = no_js_context.new_page()
        try:
            _sign_in(
                no_js_page,
                base_url,
                email=users["owner"]["email"],
                password=users["owner"]["password"],
            )
            no_js_page.goto(character_url)
            expect(no_js_page.locator("button.item-detail-button")).to_have_count(0)
            expect(no_js_page.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            fallback = no_js_page.locator(
                "[data-combat-section-panel='inventory'] details[data-character-spell-fallback]"
            ).first
            expect(fallback).to_have_count(1)
            fallback.evaluate(
                "element => element.closest('[data-combat-section-panel]').removeAttribute('hidden')"
            )
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            expect(fallback.locator(".item-description-detail__body")).to_be_visible()
            expect(no_js_page.get_by_role("link", name="Stormglass Compass").first).to_have_attribute(
                "href", "/campaigns/linden-pass/pages/items/stormglass-compass"
            )
            no_js_page.screenshot(path=str(tmp_path / "combat_dialog_no_js_390x800.png"))
        finally:
            no_js_page.close()
            no_js_context.close()

        for initialization_mode in ("absent", "no-op", "throws"):
            fail_safe_context = browser.new_context(viewport={"width": 390, "height": 800})
            fail_safe_page = fail_safe_context.new_page()
            controller_body = test_controller_source
            if initialization_mode != "absent":
                controller_body += (
                    f"\nwindow.__installCombatDialogTestController('{initialization_mode}');"
                )
            fail_safe_page.route(
                "**/static/presentation-controller.js*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=controller_body,
                ),
            )
            try:
                _sign_in(
                    fail_safe_page,
                    base_url,
                    email=users["owner"]["email"],
                    password=users["owner"]["password"],
                )
                fail_safe_page.goto(character_url)
                wait_for_loading(fail_safe_page)
                fail_safe_scope = fail_safe_page.locator("[data-combat-workspace-root]")
                fail_safe_scope.locator("[data-combat-section-toggle='inventory']").click()
                fail_safe_fallback = fail_safe_scope.locator(
                    "[data-combat-section-panel='inventory'] "
                    "details[data-character-spell-fallback]"
                ).first
                expect(fail_safe_fallback).to_be_visible(timeout=5000)
                expect(fail_safe_page.locator("html")).not_to_have_class(
                    re.compile(r"spell-modal-js")
                )
                expect(fail_safe_scope.locator("dialog[data-presentation-dialog][open]")).to_have_count(0)

                if initialization_mode == "absent":
                    expect(fail_safe_scope).not_to_have_attribute(
                        "data-combat-presentation-dialog-state", re.compile(".+")
                    )
                    expect(
                        fail_safe_scope.locator(
                            "template[data-combat-presentation-dialog-trigger-template]"
                        )
                    ).not_to_have_count(0)
                else:
                    expect(fail_safe_scope).to_have_attribute(
                        "data-combat-presentation-dialog-state", "unavailable", timeout=5000
                    )
                    gate = fail_safe_scope.locator(
                        "[data-combat-presentation-dialog-trigger-gate]"
                    ).first
                    expect(gate).to_have_attribute("hidden", "")
                    expect(gate.locator("[data-presentation-dialog-trigger]")).to_be_hidden()

                fail_safe_fallback.locator("summary").click()
                expect(fail_safe_fallback.locator(".item-description-detail__body")).to_be_visible()
                fail_safe_fallback.scroll_into_view_if_needed()
                fail_safe_page.screenshot(
                    path=str(
                        tmp_path / f"combat_dialog_fail_safe_{initialization_mode}_390x800.png"
                    )
                )
                fail_safe_page.evaluate(
                    """() => {
                        window.__installCombatDialogTestController("ready");
                        window.__playerWikiCombatWorkspace.init(
                            document.querySelector("[data-combat-workspace-root]")
                        );
                    }"""
                )
                expect(fail_safe_scope).to_have_attribute(
                    "data-combat-presentation-dialog-state", "ready", timeout=5000
                )
                expect(
                    fail_safe_scope.locator(
                        "[data-combat-section-panel='inventory'] "
                        "details[data-character-spell-fallback]"
                    ).first
                ).to_be_hidden()
                recovered_trigger = fail_safe_scope.locator("button.item-detail-button").first
                expect(recovered_trigger).to_be_visible(timeout=5000)
                recovered_trigger.click()
                recovered_dialog = fail_safe_scope.locator("dialog.item-detail-dialog[open]").first
                expect(recovered_dialog).to_be_visible(timeout=5000)
                recovered_dialog.get_by_role("button", name="Close").click()
                expect(recovered_trigger).to_be_focused(timeout=5000)
            finally:
                fail_safe_page.close()
                fail_safe_context.close()

        browser.close()


def test_flask_combat_safe_read_policy_fault_pause_retry_across_surfaces_and_viewports(
    app,
    client,
    sign_in,
    combat_dm_controls_live_server,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    ).status_code == 302
    with app.app_context():
        combatant = next(
            item
            for item in app.extensions["campaign_combat_service"].list_combatants("linden-pass")
            if item.source_ref == "arden-march"
        )

    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = combat_dm_controls_live_server
    surfaces = (
        (
            "player",
            f"/campaigns/linden-pass/combat?combatant={combatant.id}",
            "[data-combat-live-root]",
        ),
        (
            "player",
            f"/campaigns/linden-pass/combat/character?combatant={combatant.id}",
            "[data-combat-character-live-root]",
        ),
        (
            "manager",
            f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}",
            "[data-combat-live-root]",
        ),
        (
            "manager",
            "/campaigns/linden-pass/combat/dm?view=controls",
            "[data-combat-live-root]",
        ),
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            for viewport in ({"width": 1280, "height": 900}, {"width": 390, "height": 800}):
                for actor, path, root_selector in surfaces:
                    context = browser.new_context(viewport=viewport)
                    page = context.new_page()
                    requests = []
                    try:
                        user = users["owner"] if actor == "player" else users["dm"]
                        _sign_in(page, base_url, email=user["email"], password=user["password"])
                        response = page.goto(f"{base_url}{path}")
                        assert response is not None and response.status == 200
                        root = page.locator(root_selector)
                        expect(root).to_have_count(1)
                        expect(root).to_have_attribute("data-loading", "0")

                        def fail_live_read(route):
                            requests.append(route.request.url)
                            route.fulfill(
                                status=503,
                                headers={"Content-Type": "application/json"},
                                body='{"error": "unavailable"}',
                            )

                        page.route(re.compile(r".*/combat/(?:dm/|character/)?live-state(?:\?.*)?$"), fail_live_read)
                        expect(root).to_have_attribute("data-live-async-state", "poll-error", timeout=5000)
                        expect(root.locator("[data-live-read-status-message]")).to_have_text(
                            "Live Combat updates are unavailable. Current content is still shown."
                        )
                        expect(root.locator("[data-live-safe-read-retry]")).to_be_visible()
                        expect(root).to_have_attribute("data-loading", "0")
                        expect(page.locator("main h1")).to_be_visible()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth - window.innerWidth"
                        ) <= 1

                        before_retry = len(requests)
                        root.locator("[data-live-safe-read-retry]").click()
                        for _ in range(20):
                            if len(requests) > before_retry:
                                break
                            page.wait_for_timeout(25)
                        assert len(requests) == before_retry + 1
                        page.wait_for_timeout(100)
                        assert len(requests) == before_retry + 1

                        context.set_offline(True)
                        expect(root).to_have_attribute("data-live-async-state", "offline")
                        expect(root.locator("[data-live-read-status-message]")).to_have_text(
                            "Live Combat updates are paused while you are offline."
                        )
                        context.set_offline(False)
                        online_count = len(requests)
                        for _ in range(20):
                            if len(requests) > online_count:
                                break
                            page.wait_for_timeout(25)
                        assert len(requests) == online_count + 1

                        root.evaluate("element => { element.hidden = true; }")
                        paused_count = len(requests)
                        page.wait_for_timeout(700)
                        assert len(requests) == paused_count
                        root.evaluate("element => { element.hidden = false; }")
                        for _ in range(20):
                            if len(requests) > paused_count:
                                break
                            page.wait_for_timeout(25)
                        assert len(requests) == paused_count + 1
                    finally:
                        page.close()
                        context.close()
        finally:
            browser.close()

