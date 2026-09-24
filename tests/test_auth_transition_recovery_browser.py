from __future__ import annotations

from datetime import timedelta
import threading

import pytest
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from player_wiki.auth_store import AuthStore


@pytest.mark.parametrize("mode", ["reset", "invite"])
@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 800}], ids=["desktop", "mobile"])
@pytest.mark.parametrize("javascript_enabled", [True, False], ids=["javascript", "no-javascript"])
def test_account_transition_recovery_native_form_and_sign_in(
    app, monkeypatch, mode, viewport, javascript_enabled
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        pytest.skip("Playwright browser unavailable: package missing")

    app.config["CSRF_ENABLED"] = True
    with app.app_context():
        store = AuthStore()
        user = store.create_user("recovery-browser@example.com", "Recovery browser",
                                 status="active" if mode == "reset" else "invited",
                                 password_hash=generate_password_hash("old-password"))
        issue = store.issue_password_reset_token if mode == "reset" else store.issue_invite_token
        token = issue(user.id, expires_in=timedelta(hours=1))

    original_session = AuthStore.create_session

    def unavailable_automatic_session(self, *args, **kwargs):
        from flask import request
        if request.endpoint in {"password_reset", "invite_setup"}:
            raise RuntimeError("synthetic private delivery failure")
        return original_session(self, *args, **kwargs)

    monkeypatch.setattr(AuthStore, "create_session", unavailable_automatic_session)
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright browser unavailable: {type(exc).__name__}")
            try:
                context = browser.new_context(viewport=viewport, java_script_enabled=javascript_enabled)
                page = context.new_page()
                assert page.goto(f"{base_url}/{mode}/{token}").status == 200
                if mode == "invite":
                    page.get_by_label("Display name", exact=True).fill("Browser chosen name")
                page.get_by_label("New password", exact=True).fill("short")
                page.get_by_label("Confirm password", exact=True).fill("different")
                button = page.get_by_role("button", name="Activate account" if mode == "invite" else "Update password", exact=True)
                with page.expect_navigation() as invalid:
                    button.click()
                assert invalid.value.status == 400
                expect(page.get_by_label("New password", exact=True)).to_have_value("")
                page.get_by_label("New password", exact=True).fill("browser-chosen-password")
                page.get_by_label("Confirm password", exact=True).fill("browser-chosen-password")
                with page.expect_navigation() as completion:
                    button.click()
                assert completion.value.status == 503
                expect(page.get_by_role("heading", name="Sign in with your new password")).to_be_visible()
                expect(page.get_by_text("Your changes are saved.", exact=False)).to_be_visible()
                assert "browser-chosen-password" not in page.content()
                assert "synthetic private delivery failure" not in page.content()
                assert page.locator('input[type="password"]').count() == 0
                assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"] + 2
                assert "no-store" in completion.value.headers["cache-control"]
                assert "content-security-policy" in completion.value.headers

                # Reach the recovery action with a keyboard in both native layouts.
                sign_in = page.locator(".auth-card").get_by_role("link", name="Sign in", exact=True)
                for _ in range(30):
                    page.keyboard.press("Tab")
                    if sign_in.evaluate("element => element === document.activeElement"):
                        break
                expect(sign_in).to_be_focused()
                with page.expect_navigation():
                    page.keyboard.press("Enter")
                assert page.url == f"{base_url}/sign-in"
                page.get_by_label("Email", exact=True).fill(user.email)
                page.get_by_label("Password", exact=True).fill("browser-chosen-password")
                with page.expect_navigation():
                    page.get_by_role("button", name="Sign in", exact=True).click()
                assert page.goto(f"{base_url}/account").status == 200
                assert page.goto(f"{base_url}/{mode}/{token}").status == 400
                expect(page.get_by_role("heading", name="This link is no longer valid.")).to_be_visible()
                context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
