from __future__ import annotations

import re
import threading

import pytest

from player_wiki.character_update_apply import (
    CharacterUpdateApplyClassification,
    CharacterUpdateApplyResult,
    CharacterUpdateReviewIssue,
)
from tests.helpers.systems_seed_helpers import _seed_systems_item_entry
from tests.test_character_update_preview_route_transport import (
    _fixture_replacements,
    _install_dependencies,
)


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


def test_character_update_preview_compose_validation_focus_review_history_and_cancel(
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
    matrix = (
        ("desktop no-JS", {"width": 1280, "height": 900}, False),
        ("desktop JS", {"width": 1280, "height": 900}, True),
        ("mobile no-JS", {"width": 390, "height": 800}, False),
        ("mobile JS", {"width": 390, "height": 800}, True),
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.fail(f"Playwright browser unavailable: {exc}")
        try:
            for label, viewport, javascript_enabled in matrix:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=javascript_enabled,
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
                    choice_value = source.input_value()
                    quantity = page.locator("input[name='operation_0_quantity']")
                    quantity.fill("abc")
                    with page.expect_navigation() as invalid_navigation:
                        page.get_by_role("button", name="Review update").click()
                    assert invalid_navigation.value.status == 400

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
                    expect(
                        page.locator("html.app-loading, html.app-loading-closing")
                    ).to_have_count(0)
                    expect(quantity).to_be_focused()
                    focus_style = quantity.evaluate(
                        """element => {
                            const style = getComputedStyle(element);
                            return {
                                outlineStyle: style.outlineStyle,
                                boxShadow: style.boxShadow,
                            };
                        }"""
                    )
                    assert (
                        focus_style["outlineStyle"] != "none"
                        or focus_style["boxShadow"] != "none"
                    ), f"{label} invalid focus"
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
                    expect(source).to_have_value(choice_value)
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


def test_character_update_confirmation_and_receipts_work_with_js_on_off_at_both_viewports(
    app,
    users,
    monkeypatch,
    character_update_preview_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

    events = []
    replacements = _fixture_replacements(events)
    campaign, record = replacements["load_character_context"]()
    replacements["get_authenticated_user"] = lambda: type(
        "Actor", (), {"id": users["dm"]["id"], "is_admin": False}
    )()
    replacements["load_character_apply_context"] = lambda *_args: (campaign, record)

    class Engine:
        operations = ()
        outcome = CharacterUpdateApplyClassification.CONFIRMED_APPLIED

        def issue_review(self, recompute, *, actor_user_id):
            self.operations = recompute.operations
            return CharacterUpdateReviewIssue("cu1.browser.secret", None)

        def apply(self, _token, *, recompute, **_kwargs):
            recompute(self.operations)
            return CharacterUpdateApplyResult(self.outcome, "e" * 64)

    engine = Engine()
    replacements["character_update_apply_engine"] = engine
    _install_dependencies(app, monkeypatch, **replacements)

    base_url = character_update_preview_live_server
    target_url = f"{base_url}{ROUTE_PATH}"
    matrix = (
        ("desktop no-JS", {"width": 1280, "height": 900}, False),
        ("desktop JS", {"width": 1280, "height": 900}, True),
        ("mobile no-JS", {"width": 390, "height": 800}, False),
        ("mobile JS", {"width": 390, "height": 800}, True),
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.fail(f"Playwright browser unavailable: {exc}")
        try:
            for label, viewport, javascript_enabled in matrix:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=javascript_enabled,
                )
                page = context.new_page()
                try:
                    _sign_in(page, base_url, users["dm"])
                    for outcome, receipt_heading in (
                        (
                            CharacterUpdateApplyClassification.CONFIRMED_APPLIED,
                            "Update confirmed",
                        ),
                        (
                            CharacterUpdateApplyClassification.UNCERTAIN,
                            "Outcome not confirmed",
                        ),
                    ):
                        engine.outcome = outcome
                        page.goto(target_url)
                        page.locator("select[name='operation_0_choice']").select_option(index=1)
                        page.get_by_role("button", name="Review update").click()
                        expect(
                            page.get_by_role("heading", name="Confirm this update", exact=True)
                        ).to_be_visible()
                        expect(page.locator("body")).to_contain_text("Arden March")
                        expect(page.locator("body")).to_contain_text("1 reviewed operation")
                        confirm = page.get_by_role(
                            "button",
                            name="Confirm and apply update once",
                            exact=True,
                        )
                        expect(confirm).to_be_visible()
                        back = page.get_by_role("button", name="Back to edit", exact=True)
                        cancel = page.get_by_role(
                            "button",
                            name="Cancel and return",
                            exact=True,
                        )
                        action_labels = [
                            text.strip()
                            for text in page.locator(
                                ".character-update-preview__review-actions button"
                            ).all_inner_texts()
                        ]
                        assert action_labels == [
                            "Confirm and apply update once",
                            "Back to edit",
                            "Cancel and return",
                        ], f"{label} confirmation action order"
                        confirm.focus()
                        expect(confirm).to_be_focused()
                        confirm_focus = confirm.evaluate(
                            "element => getComputedStyle(element).outlineStyle"
                        )
                        assert confirm_focus != "none", f"{label} confirm focus"
                        page.keyboard.press("Tab")
                        expect(back).to_be_focused()
                        back_focus = back.evaluate(
                            "element => getComputedStyle(element).outlineStyle"
                        )
                        assert back_focus != "none", f"{label} back focus"
                        page.keyboard.press("Tab")
                        expect(cancel).to_be_focused()
                        cancel_focus = cancel.evaluate(
                            "element => getComputedStyle(element).outlineStyle"
                        )
                        assert cancel_focus != "none", f"{label} cancel focus"
                        _assert_no_horizontal_overflow(page, f"{label} confirmation")

                        confirm.focus()
                        confirm.click()
                        expect(
                            page.get_by_role("heading", name=receipt_heading, exact=True)
                        ).to_be_visible()
                        expect(
                            page.get_by_role("link", name="Inspect current Character", exact=True)
                        ).to_be_visible()
                        expect(
                            page.get_by_role("link", name="Return to Character roster", exact=True)
                        ).to_be_visible()
                        root = page.locator("#character-update-preview")
                        expect(root.get_by_role("button")).to_have_count(0)
                        expect(page.locator("body")).not_to_contain_text("cu1.browser.secret")
                        expect(page.locator("body")).not_to_contain_text("e" * 64)
                        _assert_no_horizontal_overflow(page, f"{label} {outcome.value}")

                        if outcome is CharacterUpdateApplyClassification.UNCERTAIN:
                            expect(page.locator("body")).to_contain_text(
                                "Reviewed scope — not confirmed"
                            )
                            expect(page.locator("body")).to_contain_text(
                                "Do not refresh or resubmit this update"
                            )
                            expect(page.get_by_role("link", name=re.compile("retry|preview", re.I))).to_have_count(0)
                            expect(page.get_by_role("button", name=re.compile("retry|apply|preview", re.I))).to_have_count(0)

                        if viewport["width"] == 390:
                            boxes = page.locator(".character-update-preview__receipt-actions a").evaluate_all(
                                "elements => elements.map(element => element.getBoundingClientRect().toJSON())"
                            )
                            assert len(boxes) == 2
                            assert boxes[0]["width"] >= 330 and boxes[1]["width"] >= 330
                            assert boxes[1]["top"] > boxes[0]["bottom"]
                finally:
                    page.close()
                    context.close()
        finally:
            browser.close()
