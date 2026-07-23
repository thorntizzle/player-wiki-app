from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

from player_wiki.campaign_content_service import write_campaign_page_file
from player_wiki.db import get_db


UNKNOWN_OUTCOME_GUIDANCE = (
    "If a result could not be confirmed, refresh or search the current page list "
    "before repeating the action."
)
PLAYER_WIKI_MANAGEMENT_PATH = "/campaigns/linden-pass/dm-content/player-wiki"


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


def _assert_unknown_outcome_guidance(page, expect) -> None:
    guidance = page.locator("#dm-content-player-wiki-outcome-guidance")
    expect(guidance).to_be_visible()
    expect(guidance).to_contain_text(UNKNOWN_OUTCOME_GUIDANCE)
    expect(guidance).not_to_have_attribute("role", re.compile(".+"))
    expect(guidance).not_to_have_attribute("aria-live", re.compile(".+"))
    expect(guidance.locator("form")).to_have_count(0)
    expect(
        guidance.get_by_role("link", name="Refresh current page list", exact=True)
    ).to_have_attribute("href", PLAYER_WIKI_MANAGEMENT_PATH)
    guidance_text = guidance.inner_text().lower()
    for forbidden_claim in (
        "success",
        "failure",
        "rollback",
        "compensation",
        "persistence",
        "safe retry",
        "recovery",
        "repair",
        "journal",
    ):
        assert forbidden_claim not in guidance_text


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
    _assert_unknown_outcome_guidance(page, expect)
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


def _seed_safe_removal_records(app) -> tuple[Path, bytes]:
    asset_ref = "lore/trade-coast-map.png"
    asset_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "assets"
        / Path(*asset_ref.split("/"))
    )
    assert asset_path.exists()
    asset_bytes = asset_path.read_bytes()

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        page_store = app.extensions["campaign_page_store"]
        write_campaign_page_file(
            campaign,
            "notes/browser-safe-archive",
            metadata={
                "title": "Browser Safe Archive",
                "section": "Notes",
                "type": "note",
                "summary": "A safe page for the ordinary archive workflow.",
                "published": True,
            },
            body_markdown="## Description\n\nArchive this page without deleting its file.",
            page_store=page_store,
        )
        write_campaign_page_file(
            campaign,
            "notes/browser-safe-delete",
            metadata={
                "title": "Browser Safe Delete",
                "section": "Notes",
                "type": "note",
                "summary": "An unreferenced page for the hard-delete exception.",
                "published": True,
                "image": asset_ref,
                "image_alt": "Retained browser fixture asset",
            },
            body_markdown="## Description\n\nThis page is safe to remove as an exception.",
            page_store=page_store,
        )
        write_campaign_page_file(
            campaign,
            "notes/browser-referenced-target",
            metadata={
                "title": "Browser Referenced Target",
                "section": "Notes",
                "type": "note",
                "summary": "A referenced page whose hard delete must stay blocked.",
                "published": True,
            },
            body_markdown="## Description\n\nThis page has a referrer.",
            page_store=page_store,
        )
        write_campaign_page_file(
            campaign,
            "notes/browser-referrer",
            metadata={
                "title": "Browser Referrer",
                "section": "Notes",
                "type": "note",
                "summary": "A page that protects its referenced target.",
                "published": True,
            },
            body_markdown=(
                "## Description\n\nReview [[Browser Referenced Target]] before removal."
            ),
            page_store=page_store,
        )
        app.extensions["repository_store"].refresh()
    return asset_path, asset_bytes


def _assert_safe_removal_disclosure(page, expect, *, viewport_name: str) -> None:
    safe_card = page.locator("#wiki-page-notes-browser-safe-delete")
    expect(safe_card).to_be_visible()
    expect(safe_card).to_contain_text(
        "Archive/unpublish is the normal removal action. It hides the page without "
        "deleting its Markdown file."
    )
    archive_button = safe_card.get_by_role(
        "button", name="Archive/unpublish", exact=True
    )
    disclosure = safe_card.locator("details.dm-content-delete-exception")
    summary = disclosure.locator(":scope > summary")
    expect(archive_button).to_be_visible()
    expect(summary).to_have_text("Hard delete page file (exception)")
    expect(disclosure).not_to_have_attribute("open", "")
    expect(disclosure).to_contain_text(
        "Browser Safe Delete (notes/browser-safe-delete.md)"
    )
    expect(disclosure).to_contain_text(
        "This is a reviewed, currently unreferenced exception."
    )
    expect(disclosure).to_contain_text(
        "Hard delete permanently removes the page file and Player Wiki entry. It "
        "cannot be undone in the browser."
    )
    expect(disclosure).to_contain_text(
        "Campaign assets remain retained and unchanged."
    )
    delete_form = disclosure.locator("form.dm-content-delete-form")
    expect(delete_form).to_have_attribute("method", "post")
    expect(delete_form).to_have_attribute(
        "action",
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/"
        "browser-safe-delete/delete",
    )
    expect(delete_form.locator("input[name='_csrf_token']")).to_have_count(1)
    acknowledgement = delete_form.get_by_label(
        "I reviewed this page and understand hard delete cannot be undone.",
        exact=True,
    )
    expect(acknowledgement).to_have_attribute("name", "confirm_delete")
    expect(acknowledgement).to_have_attribute("value", "1")
    expect(acknowledgement).to_have_attribute("required", "")
    submit_delete = delete_form.locator(
        "button[type='submit']", has_text="Hard delete page file"
    )
    expect(submit_delete).to_have_count(1)
    expect(safe_card.locator("input[name='force']")).to_have_count(0)

    archive_button.focus()
    expect(archive_button).to_be_focused()
    archive_button.press("Tab")
    expect(summary).to_be_focused()
    summary.press("Enter")
    expect(disclosure).to_have_attribute("open", "")
    expect(submit_delete).to_be_visible()
    summary.press("Space")
    expect(disclosure).not_to_have_attribute("open", "")
    _assert_no_horizontal_overflow(page, viewport_name)


def _assert_blocked_removal_card(page, expect) -> None:
    blocked_card = page.locator("#wiki-page-notes-browser-referenced-target")
    expect(blocked_card).to_be_visible()
    expect(blocked_card).to_contain_text("Hard delete blocked")
    expect(blocked_card).to_contain_text("Backlinked from Browser Referrer.")
    expect(
        blocked_card.get_by_role("button", name="Archive/unpublish", exact=True)
    ).to_be_visible()
    expect(blocked_card.locator("details.dm-content-delete-exception")).to_have_count(0)
    expect(blocked_card.locator("form.dm-content-delete-form")).to_have_count(0)
    expect(blocked_card.locator("input[name='confirm_delete']")).to_have_count(0)
    expect(
        blocked_card.get_by_role("button", name="Hard delete page file", exact=True)
    ).to_have_count(0)
    expect(blocked_card.locator("button[disabled]")).to_have_count(0)


def test_player_wiki_native_workflow_browser_matrix(
    app,
    player_wiki_live_server,
    users,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

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
            pytest.fail(f"Playwright browser unavailable: {exc}")

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

            refresh_link = desktop_page.get_by_role(
                "link", name="Refresh current page list", exact=True
            )
            refresh_link.focus()
            refresh_focus_style = refresh_link.evaluate(
                "element => getComputedStyle(element).outlineWidth"
            )
            assert refresh_focus_style != "0px"
            refresh_requests = []

            def record_refresh_request(request):
                if (
                    request.method == "GET"
                    and request.resource_type == "document"
                    and request.url == landing_url
                ):
                    refresh_requests.append(request.url)

            desktop_page.on("request", record_refresh_request)
            refresh_link.press("Enter")
            desktop_page.wait_for_load_state("load")
            desktop_page.remove_listener("request", record_refresh_request)
            assert refresh_requests == [landing_url]
            _assert_unknown_outcome_guidance(desktop_page, expect)

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
            with desktop_page.expect_response(
                lambda response: (
                    response.request.method == "POST"
                    and response.url == f"{landing_url}/pages"
                )
            ) as validation_response:
                editor.get_by_role("button", name="Create wiki page", exact=True).click()
            assert validation_response.value.status == 400
            expect(editor).to_have_attribute("open", "")
            expect(advanced).to_have_attribute("open", "")
            expect(editor.locator("input[name='title']")).to_have_value(
                "Browser Invalid Upload"
            )
            expect(editor.locator("input[name='image_file']")).to_have_value("")
            expect(editor.get_by_text("Choose the image file again", exact=False)).to_be_visible()
            _assert_unknown_outcome_guidance(desktop_page, expect)

            desktop_page.goto(landing_url)
            editor.locator(":scope > summary").click()
            editor.locator("input[name='title']").fill("Browser Refresh Failure")
            editor.locator("input[name='slug_leaf']").fill("browser-refresh-failure")
            editor.locator("textarea[name='body_markdown']").fill(
                "## Description\n\nThis page crosses the repository refresh failure window."
            )
            repository_store = app.extensions["repository_store"]
            original_refresh = repository_store.refresh_from_database

            def fail_refresh():
                raise RuntimeError("browser repository refresh failure")

            monkeypatch.setattr(repository_store, "refresh_from_database", fail_refresh)
            try:
                with desktop_page.expect_response(
                    lambda response: (
                        response.request.method == "POST"
                        and response.url == f"{landing_url}/pages"
                    )
                ) as refresh_failure_response:
                    editor.get_by_role("button", name="Create wiki page", exact=True).click()
                assert refresh_failure_response.value.status == 500
            finally:
                monkeypatch.setattr(
                    repository_store,
                    "refresh_from_database",
                    original_refresh,
                )

            with app.app_context():
                repository_store.refresh()
            desktop_page.goto(f"{landing_url}?q=Browser+Refresh+Failure")
            _assert_unknown_outcome_guidance(desktop_page, expect)
            expect(desktop_page.locator("#wiki-page-notes-browser-refresh-failure")).to_have_count(1)
            assert desktop_page.get_by_text("Unknown outcome", exact=False).count() == 0
            assert desktop_page.get_by_text("safe to retry", exact=False).count() == 0

            _sign_in(mobile_page, base_url, users["dm"])
            mobile_page.goto(landing_url)
            _assert_default_workflow(mobile_page, expect, viewport_name="DM mobile")
            mobile_page.get_by_label("Search pages", exact=True).fill("Operations Brief")
            mobile_page.get_by_label("Search pages", exact=True).press("Enter")
            expect(mobile_page.get_by_label("Search pages", exact=True)).to_have_value(
                "Operations Brief"
            )
            expect(
                mobile_page.get_by_role("heading", name="Search results", exact=True)
            ).to_be_visible()
            _assert_unknown_outcome_guidance(mobile_page, expect)
            _assert_no_horizontal_overflow(mobile_page, "DM mobile search")

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
            no_js_form.locator("input[name='title']").fill("No JS Known Validation")
            no_js_form.locator("input[name='slug_leaf']").fill("no-js-known-validation")
            no_js_form.locator("input[name='image_file']").set_input_files(
                {
                    "name": "invalid.txt",
                    "mimeType": "text/plain",
                    "buffer": b"not an image",
                }
            )
            with no_js_page.expect_response(
                lambda response: (
                    response.request.method == "POST"
                    and response.url == f"{landing_url}/pages"
                )
            ) as no_js_validation_response:
                no_js_form.get_by_role("button", name="Create wiki page", exact=True).click()
            assert no_js_validation_response.value.status == 400
            expect(no_js_editor).to_have_attribute("open", "")
            expect(no_js_editor.locator("details.dm-content-wiki-advanced")).to_have_attribute(
                "open", ""
            )
            expect(no_js_editor.locator("input[name='title']")).to_have_value(
                "No JS Known Validation"
            )
            expect(no_js_editor.locator("input[name='image_file']")).to_have_value("")
            expect(
                no_js_editor.get_by_text("Choose the image file again", exact=False)
            ).to_be_visible()
            _assert_unknown_outcome_guidance(no_js_page, expect)
            no_js_refresh_link = no_js_page.get_by_role(
                "link", name="Refresh current page list", exact=True
            )
            no_js_refresh_link.focus()
            no_js_refresh_focus_style = no_js_refresh_link.evaluate(
                "element => getComputedStyle(element).outlineWidth"
            )
            assert no_js_refresh_focus_style != "0px"
            with no_js_page.expect_request(
                lambda request: request.method == "GET" and request.url == landing_url
            ) as no_js_refresh_request:
                no_js_refresh_link.press("Enter")
            assert no_js_refresh_request.value.method == "GET"
            no_js_page.wait_for_load_state("load")
            _assert_unknown_outcome_guidance(no_js_page, expect)
            _assert_no_horizontal_overflow(no_js_page, "admin mobile no-JS expanded")
        finally:
            desktop_page.close()
            mobile_page.close()
            no_js_page.close()
            desktop_context.close()
            mobile_context.close()
            no_js_context.close()
            browser.close()


def test_player_wiki_safe_removal_browser_matrix(
    app,
    player_wiki_live_server,
    users,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.fail(f"Playwright unavailable: {exc}")

    asset_path, original_asset_bytes = _seed_safe_removal_records(app)
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    archive_page_path = (
        campaigns_dir
        / "linden-pass"
        / "content"
        / "notes"
        / "browser-safe-archive.md"
    )
    delete_page_path = (
        campaigns_dir
        / "linden-pass"
        / "content"
        / "notes"
        / "browser-safe-delete.md"
    )
    assert archive_page_path.exists()
    assert delete_page_path.exists()
    assert asset_path.read_bytes() == original_asset_bytes

    base_url = player_wiki_live_server
    landing_url = f"{base_url}{PLAYER_WIKI_MANAGEMENT_PATH}"
    archive_read_url = (
        f"{base_url}/campaigns/linden-pass/pages/notes/browser-safe-archive"
    )
    delete_action_url = (
        f"{landing_url}/pages/notes/browser-safe-delete/delete"
    )
    original_csrf_enabled = app.config["CSRF_ENABLED"]
    app.config["CSRF_ENABLED"] = True
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
                desktop_context = browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                mobile_context = browser.new_context(
                    viewport={"width": 390, "height": 800}
                )
                player_context = browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                no_js_context = browser.new_context(
                    viewport={"width": 390, "height": 800},
                    java_script_enabled=False,
                )
            except Exception as exc:
                pytest.fail(f"Playwright browser unavailable: {exc}")

            desktop_page = desktop_context.new_page()
            mobile_page = mobile_context.new_page()
            player_page = player_context.new_page()
            no_js_page = no_js_context.new_page()
            try:
                _sign_in(desktop_page, base_url, users["dm"])
                desktop_page.goto(landing_url)
                _assert_safe_removal_disclosure(
                    desktop_page,
                    expect,
                    viewport_name="safe removal DM desktop",
                )
                _assert_blocked_removal_card(desktop_page, expect)

                _sign_in(mobile_page, base_url, users["dm"])
                mobile_page.goto(landing_url)
                _assert_safe_removal_disclosure(
                    mobile_page,
                    expect,
                    viewport_name="safe removal DM mobile",
                )
                _assert_blocked_removal_card(mobile_page, expect)

                _sign_in(player_page, base_url, users["party"])
                player_management_response = player_page.goto(landing_url)
                assert player_management_response is not None
                assert player_management_response.status == 404
                expect(
                    player_page.get_by_role(
                        "heading", name="That page is not available.", exact=True
                    )
                ).to_be_visible()

                _sign_in(no_js_page, base_url, users["admin"])
                no_js_page.goto(landing_url)
                archive_card = no_js_page.locator(
                    "#wiki-page-notes-browser-safe-archive"
                )
                archive_form = archive_card.locator(
                    "form[action$='/notes/browser-safe-archive/unpublish']"
                )
                expect(archive_form).to_have_attribute("method", "post")
                expect(
                    archive_form.locator("input[name='_csrf_token']")
                ).to_have_count(1)
                with no_js_page.expect_request(
                    lambda request: (
                        request.method == "POST"
                        and request.url
                        == f"{landing_url}/pages/notes/browser-safe-archive/unpublish"
                    )
                ) as archive_request_info:
                    archive_form.get_by_role(
                        "button", name="Archive/unpublish", exact=True
                    ).click()
                archive_request = archive_request_info.value
                no_js_page.wait_for_load_state("load")
                assert archive_request.post_data is not None
                assert "_csrf_token=" in archive_request.post_data
                assert "force" not in archive_request.url.lower()
                assert "force" not in archive_request.post_data.lower()
                assert archive_page_path.exists()

                archived_player_response = player_page.goto(archive_read_url)
                assert archived_player_response is not None
                assert archived_player_response.status == 404

                delete_card = no_js_page.locator(
                    "#wiki-page-notes-browser-safe-delete"
                )
                delete_disclosure = delete_card.locator(
                    "details.dm-content-delete-exception"
                )
                delete_disclosure.locator(":scope > summary").press("Enter")
                expect(delete_disclosure).to_have_attribute("open", "")
                delete_form = delete_disclosure.locator(
                    "form.dm-content-delete-form"
                )
                expect(delete_form).to_have_attribute("method", "post")
                expect(delete_form).to_have_attribute(
                    "action",
                    "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/"
                    "browser-safe-delete/delete",
                )
                expect(
                    delete_form.locator("input[name='_csrf_token']")
                ).to_have_count(1)
                acknowledgement = delete_form.get_by_label(
                    "I reviewed this page and understand hard delete cannot be undone.",
                    exact=True,
                )
                submit_delete = delete_form.get_by_role(
                    "button", name="Hard delete page file", exact=True
                )
                delete_requests = []

                def record_delete_request(request):
                    if request.method == "POST" and request.url == delete_action_url:
                        delete_requests.append(request)

                no_js_page.on("request", record_delete_request)
                submit_delete.click()
                no_js_page.wait_for_timeout(150)
                no_js_page.remove_listener("request", record_delete_request)
                assert delete_requests == []
                expect(acknowledgement).to_be_focused()
                assert acknowledgement.evaluate(
                    "element => element.validity.valueMissing"
                )
                assert delete_page_path.exists()

                acknowledgement.check()
                with no_js_page.expect_request(
                    lambda request: (
                        request.method == "POST"
                        and request.url == delete_action_url
                    )
                ) as delete_request_info:
                    submit_delete.click()
                delete_request = delete_request_info.value
                no_js_page.wait_for_load_state("load")
                assert delete_request.url == delete_action_url
                assert "?" not in delete_request.url
                assert delete_request.post_data is not None
                assert "_csrf_token=" in delete_request.post_data
                assert "confirm_delete=1" in delete_request.post_data
                assert "force" not in delete_request.url.lower()
                assert "force" not in delete_request.post_data.lower()
                assert not delete_page_path.exists()
                assert asset_path.exists()
                assert asset_path.read_bytes() == original_asset_bytes
                _assert_no_horizontal_overflow(
                    no_js_page,
                    "safe removal admin mobile no-JS",
                )
            finally:
                desktop_page.close()
                mobile_page.close()
                player_page.close()
                no_js_page.close()
                desktop_context.close()
                mobile_context.close()
                player_context.close()
                no_js_context.close()
                browser.close()
    finally:
        app.config["CSRF_ENABLED"] = original_csrf_enabled
