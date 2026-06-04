import re
import threading

import pytest


@pytest.fixture
def frontend_gen2_session_live_server(app):
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


def test_gen2_session_browser_exposes_flask_session_capabilities(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            page.goto(f"{base_url}/campaigns/linden-pass/session")
            expect(page.get_by_role("heading", name="Chat window")).to_be_visible(timeout=5000)

            page.goto(f"{base_url}/campaigns/linden-pass/session/dm")
            expect(page.get_by_role("heading", name="Session controls")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Session article store")).to_be_visible(timeout=5000)
            expect(page.get_by_role("heading", name="Chat logs")).to_be_visible(timeout=5000)

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            session_heading = page.get_by_role("heading", name=re.compile(r"Session:", re.I)).first
            session_tabs = page.locator(".session-tab-strip")
            expect(session_heading).to_be_visible(timeout=10000)
            expect(session_tabs.get_by_role("button", name="Session", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="Character", exact=True)).to_be_visible()
            expect(session_tabs.get_by_role("button", name="DM", exact=True)).to_be_visible()

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="DM controls")).to_be_visible(timeout=5000)
            expect(page.get_by_role("button", name=re.compile(r"Begin session|Starting", re.I))).to_be_visible()
            expect(page.get_by_role("button", name=re.compile(r"Close session|Closing", re.I))).to_be_visible()
            expect(page.get_by_role("heading", name="Staged articles")).to_be_visible()
            expect(page.get_by_role("heading", name="Revealed articles")).to_be_visible()
            expect(page.get_by_role("heading", name="Session logs")).to_be_visible()

            session_tabs.get_by_role("button", name="Session", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(session_heading).to_be_visible()
            expect(page.get_by_role("heading", name="Session chat")).to_be_visible()
            expect(page.get_by_role("heading", name="Player wiki lookup")).to_be_visible()
            expect(page.get_by_label("Post Session Message")).to_be_visible()

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            expect(page).to_have_url(re.compile(r"/app-next/campaigns/linden-pass/session$"))
            expect(page.get_by_role("heading", name="Session Character")).to_be_visible(timeout=10000)
            expect(page.get_by_label("Character", exact=True)).to_be_visible()
        finally:
            page.close()
            browser.close()


def test_gen2_session_preserves_local_state_across_live_polling(
    frontend_gen2_session_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = frontend_gen2_session_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 620})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in(page, base_url, email=users["dm"]["email"], password=users["dm"]["password"])

            start_response = page.request.post(f"{base_url}/campaigns/linden-pass/session/start")
            assert start_response.status in {200, 302}
            article_response = page.request.post(
                f"{base_url}/campaigns/linden-pass/session/articles",
                form={
                    "title": "Gen2 Preservation Article",
                    "body_markdown": "This staged article should keep local draft state.",
                },
            )
            assert article_response.status in {200, 302}

            page.goto(f"{base_url}/app-next/campaigns/linden-pass/session")
            session_tabs = page.locator(".session-tab-strip")
            expect(session_tabs.get_by_role("button", name="Session", exact=True)).to_be_visible(timeout=10000)

            chat_draft = "This chat draft should survive pane switches and live polling."
            page.locator(".pane-visible").get_by_label("Post Session Message").fill(chat_draft)

            wiki_lookup = page.locator(".pane-visible")
            wiki_lookup.get_by_label("Search published pages / systems").fill("harbor")
            wiki_lookup.get_by_role("button", name="Search").click()
            harbor_result = wiki_lookup.get_by_role("button", name=re.compile(r"Harbor Duels", re.I))
            expect(harbor_result).to_be_visible(timeout=5000)
            harbor_result.click()
            expect(wiki_lookup.get_by_text("Formal harbor duels")).to_be_visible(timeout=5000)

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            character_pane = page.locator(".pane-visible")
            character_select = character_pane.get_by_label("Character", exact=True)
            expect(character_select).to_be_visible(timeout=10000)
            option_count = character_select.locator("option").count()
            assert option_count >= 2
            selected_character = character_select.locator("option").nth(1).get_attribute("value")
            assert selected_character
            character_select.select_option(selected_character)
            expect(character_select).to_have_value(selected_character)

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            dm_pane = page.locator(".pane-visible")
            article_card = dm_pane.locator("details.article-card", has_text="Gen2 Preservation Article")
            expect(article_card).to_be_visible(timeout=5000)
            article_card.locator("summary").click()
            assert article_card.evaluate("(element) => element.open") is True

            title_input = article_card.get_by_label("Title", exact=True)
            body_input = article_card.get_by_label("Body (markdown or html)")
            title_input.fill("Unsaved Gen2 Preservation Title")
            body_input.fill("Unsaved body should remain in the staged article editor.")
            title_input.focus()
            focused_id = title_input.get_attribute("id")
            assert focused_id

            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            scroll_before = page.evaluate("window.scrollY")
            assert scroll_before > 0

            page.wait_for_timeout(3600)

            assert article_card.evaluate("(element) => element.open") is True
            expect(title_input).to_have_value("Unsaved Gen2 Preservation Title")
            expect(body_input).to_have_value("Unsaved body should remain in the staged article editor.")
            assert page.evaluate("document.activeElement && document.activeElement.id") == focused_id
            scroll_after = page.evaluate("window.scrollY")
            assert abs(scroll_after - scroll_before) <= 5

            session_tabs.get_by_role("button", name="Session", exact=True).click()
            session_pane = page.locator(".pane-visible")
            expect(session_pane.get_by_label("Post Session Message")).to_have_value(chat_draft)
            expect(session_pane.get_by_text("Formal harbor duels")).to_be_visible()

            session_tabs.get_by_role("button", name="Character", exact=True).click()
            expect(page.locator(".pane-visible").get_by_label("Character", exact=True)).to_have_value(selected_character)

            session_tabs.get_by_role("button", name="DM", exact=True).click()
            article_card = page.locator(".pane-visible").locator("details.article-card", has_text="Gen2 Preservation Article")
            assert article_card.evaluate("(element) => element.open") is True
            expect(article_card.get_by_label("Title", exact=True)).to_have_value("Unsaved Gen2 Preservation Title")
            expect(article_card.get_by_label("Body (markdown or html)")).to_have_value(
                "Unsaved body should remain in the staged article editor.",
            )
        finally:
            page.close()
            browser.close()
