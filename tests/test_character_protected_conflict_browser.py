from __future__ import annotations

import pytest

from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG
from tests.test_character_read_shell_browser import (
    _configure_loopback_online,
    _sign_in_browser,
    character_read_shell_live_server,
)
from tests.test_character_reconciliation import _coordinator


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 800}])
@pytest.mark.parametrize("javascript", [False, True])
@pytest.mark.parametrize("surface", ["character", "session"])
def test_protected_notes_conflict_preserves_draft_and_safe_navigation(
    app, users, set_campaign_visibility, character_read_shell_live_server,
    monkeypatch, viewport, javascript, surface,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility(TEST_CAMPAIGN_SLUG, characters="players")
    if surface == "session":
        with app.app_context():
            app.extensions["campaign_session_service"].begin_session(
                TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"]
            )
    service = app.extensions["character_state_service"]
    original = service.update_player_notes
    calls = []
    def collide(record, **kwargs):
        calls.append(kwargs["notes_markdown"])
        def stop(event, _operation_id):
            if event == "after_commit":
                raise RuntimeError("synthetic paused publication")
        with pytest.raises(RuntimeError, match="synthetic paused publication"):
            _coordinator(app, stop).update(
                record, record.definition, record.import_metadata, record.state_record.state,
                expected_revision=record.state_record.revision, operation_kind="markdown_import",
            )
        return original(record, **kwargs)
    monkeypatch.setattr(service, "update_player_notes", collide)
    base_url = character_read_shell_live_server
    if surface == "session":
        path = f"/campaigns/{TEST_CAMPAIGN_SLUG}/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=notes"
    else:
        path = f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}?page=notes&mode=session"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        try:
            context = browser.new_context(viewport=viewport, java_script_enabled=javascript)
            page = context.new_page()
            if javascript:
                _configure_loopback_online(page)
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(base_url + path)
            draft = "Keep my unsaved notes <script>window.untrustedDraft = true</script>"
            textarea = page.locator("textarea[name='player_notes_markdown']")
            expect(textarea).to_be_visible()
            textarea.fill(draft)
            page.locator("form:has(textarea[name='player_notes_markdown']) button[type='submit']").click()
            expect(page.get_by_role("heading", name="Update not saved", exact=True)).to_be_visible()
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(draft)
            assert calls == [draft]
            assert page.locator("main").count() == 1
            if javascript:
                assert page.evaluate("Boolean(window.untrustedDraft)") is False
                assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"] + 2
                if surface == "session":
                    assert page.locator("[data-session-shell-pane='character'] [data-session-character-fragment-root]").count() == 1
            refresh = page.get_by_role("link", name="Refresh Character", exact=True)
            href = refresh.get_attribute("href")
            assert "/session/notes" not in href
            assert ("/session/character" in href) == (surface == "session")
            refresh.focus()
            expect(refresh).to_be_focused()
            # No retry control is offered, and the only draft is the submitted one.
            assert page.locator("form:has(textarea[name='player_notes_markdown'])").count() == 0
            context.close()
        finally:
            browser.close()
