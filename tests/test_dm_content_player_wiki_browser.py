from __future__ import annotations

import re
import threading

import pytest

from player_wiki.campaign_content_service import write_campaign_page_file
from player_wiki.db import get_db


@pytest.fixture
def player_wiki_live_server(app):
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


def _sign_in(page, base_url: str, user) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(user["email"])
    page.locator("input[name='password']").fill(user["password"])
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _assert_no_horizontal_overflow(page, viewport_name: str) -> None:
    widths = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            pageShell: document.querySelector('.page-shell')?.scrollWidth || 0,
            workflow: document.querySelector('#dm-content-player-wiki-pages')?.scrollWidth || 0,
        })"""
    )
    assert widths["document"] <= widths["viewport"] + 2, (
        f"{viewport_name}: document overflows horizontally"
    )
    assert widths["pageShell"] <= widths["viewport"] + 2, (
        f"{viewport_name}: page shell overflows horizontally"
    )
    assert widths["workflow"] <= widths["viewport"] + 2, (
        f"{viewport_name}: Player Wiki workflow overflows horizontally"
    )


def _assert_default_workflow(page, expect, *, viewport_name: str) -> None:
    expect(page.get_by_role("heading", name="DM Content", exact=True)).to_be_visible()
    expect(page.get_by_label("Search pages", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Recently updated pages", exact=True)).to_be_visible()
    editor = page.locator("#dm-content-player-wiki-editor")
    editor_summary = editor.locator(":scope > summary")
    expect(editor_summary).to_be_visible()
    expect(editor).not_to_have_attribute("open", "")
    expect(editor.locator("form.dm-content-wiki-form")).to_have_count(1)
    expect(page.locator("#wiki-page-notes-browser-recent")).to_have_count(1)
    page_order = page.locator(".dm-content-list > article").evaluate_all(
        "elements => elements.map((element) => element.id)"
    )
    assert page_order.index("wiki-page-notes-browser-recent") < page_order.index(
        "wiki-page-notes-operations-brief"
    )
    assert page.get_by_text("Preview player wiki draft", exact=True).count() == 0
    assert page.locator("input[name='force']").count() == 0
    _assert_no_horizontal_overflow(page, viewport_name)


def _seed_browser_records(app, users) -> int:
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        write_campaign_page_file(
            campaign,
            "notes/browser-recent",
            metadata={
                "title": "Browser Recent",
                "section": "Notes",
                "type": "note",
                "summary": "A recently updated browser-test page.",
                "subsection": "Browser checks",
                "display_order": 10000,
                "reveal_after_session": 0,
                "published": True,
                "source_ref": "browser-test",
            },
            body_markdown="## Description\n\nBrowser presentation fixture.",
            page_store=app.extensions["campaign_page_store"],
        )
        connection = get_db()
        connection.execute(
            "UPDATE campaign_pages SET updated_at = ? WHERE campaign_slug = ? AND page_ref = ?",
            ("2026-07-20T09:00:00+00:00", "linden-pass", "notes/operations-brief"),
        )
        connection.execute(
            "UPDATE campaign_pages SET updated_at = ? WHERE campaign_slug = ? AND page_ref = ?",
            ("2026-07-21T09:00:00+00:00", "linden-pass", "notes/browser-recent"),
        )
        connection.commit()
        app.extensions["repository_store"].refresh()
        article = app.extensions["campaign_session_service"].create_article(
            "linden-pass",
            title="Browser Staged Handout",
            body_markdown="Review this staged handout before publication.",
            created_by_user_id=users["dm"]["id"],
        )
        return article.id


def test_player_wiki_native_workflow_browser_matrix(
    app,
    player_wiki_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    article_id = _seed_browser_records(app, users)
    base_url = player_wiki_live_server
    landing_url = f"{base_url}/campaigns/linden-pass/dm-content/player-wiki"
    staged_href = (
        f"{base_url}/campaigns/linden-pass/session/dm?dm_view=staged"
        "#session-staged-articles"
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
            no_js_context = browser.new_context(
                viewport={"width": 390, "height": 800},
                java_script_enabled=False,
            )
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_page = desktop_context.new_page()
        mobile_page = mobile_context.new_page()
        no_js_page = no_js_context.new_page()
        try:
            _sign_in(desktop_page, base_url, users["dm"])
            desktop_page.goto(landing_url)
            _assert_default_workflow(desktop_page, expect, viewport_name="DM desktop")
            expect(
                desktop_page.get_by_role("link", name="Open staged Session articles", exact=True)
            ).to_have_attribute("href", staged_href.removeprefix(base_url))

            editor = desktop_page.locator("#dm-content-player-wiki-editor")
            editor_summary = editor.locator(":scope > summary")
            editor_summary.focus()
            focus_style = editor_summary.evaluate(
                "element => getComputedStyle(element).outlineWidth"
            )
            assert focus_style != "0px"
            editor_summary.press("Enter")
            expect(editor).to_have_attribute("open", "")
            editor_summary.press("Space")
            expect(editor).not_to_have_attribute("open", "")

            desktop_page.goto(
                f"{landing_url}/pages/notes/browser-recent/edit"
                "#dm-content-player-wiki-editor"
            )
            expect(editor).to_have_attribute("open", "")
            expect(editor.locator("details.dm-content-wiki-advanced")).to_have_attribute(
                "open", ""
            )
            expect(editor.locator("form.dm-content-wiki-form")).to_have_attribute(
                "action",
                "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/browser-recent",
            )
            expect(editor.get_by_text("Page file: notes/browser-recent.md", exact=False)).to_be_visible()

            desktop_page.goto(
                f"{landing_url}/session-articles/{article_id}/new"
                "#dm-content-player-wiki-editor"
            )
            expect(editor).to_have_attribute("open", "")
            expect(editor.locator("details.dm-content-wiki-advanced")).to_have_attribute(
                "open", ""
            )
            expect(editor.locator("input[name='source_session_article_id']")).to_have_value(
                str(article_id)
            )
            expect(editor.locator("input[name='source_ref']")).to_have_value(
                f"session-article:linden-pass:{article_id}"
            )
            expect(
                desktop_page.get_by_role("link", name="Open staged Session articles", exact=True)
            ).to_have_attribute("href", staged_href.removeprefix(base_url))

            desktop_page.goto(landing_url)
            editor_summary.click()
            advanced = editor.locator("details.dm-content-wiki-advanced")
            advanced.locator(":scope > summary").click()
            editor.locator("input[name='title']").fill("Browser Invalid Upload")
            editor.locator("input[name='slug_leaf']").fill("browser-invalid-upload")
            editor.locator("input[name='image_file']").set_input_files(
                {
                    "name": "invalid.txt",
                    "mimeType": "text/plain",
                    "buffer": b"not an image",
                }
            )
            editor.get_by_role("button", name="Create wiki page", exact=True).click()
            expect(editor).to_have_attribute("open", "")
            expect(advanced).to_have_attribute("open", "")
            expect(editor.locator("input[name='title']")).to_have_value(
                "Browser Invalid Upload"
            )
            expect(editor.locator("input[name='image_file']")).to_have_value("")
            expect(editor.get_by_text("Choose the image file again", exact=False)).to_be_visible()

            _sign_in(mobile_page, base_url, users["dm"])
            mobile_page.goto(landing_url)
            _assert_default_workflow(mobile_page, expect, viewport_name="DM mobile")

            _sign_in(no_js_page, base_url, users["admin"])
            no_js_page.goto(landing_url)
            _assert_default_workflow(no_js_page, expect, viewport_name="admin mobile no-JS")
            no_js_editor = no_js_page.locator("#dm-content-player-wiki-editor")
            no_js_editor.locator(":scope > summary").press("Enter")
            expect(no_js_editor).to_have_attribute("open", "")
            no_js_form = no_js_editor.locator("form.dm-content-wiki-form")
            expect(no_js_form).to_have_attribute("method", "post")
            expect(no_js_form).to_have_attribute("enctype", "multipart/form-data")
            expect(no_js_form.locator("input[name='_csrf_token']")).to_have_count(1)
            _assert_no_horizontal_overflow(no_js_page, "admin mobile no-JS expanded")
        finally:
            desktop_page.close()
            mobile_page.close()
            no_js_page.close()
            desktop_context.close()
            mobile_context.close()
            no_js_context.close()
            browser.close()
