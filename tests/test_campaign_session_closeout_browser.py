from __future__ import annotations

import ast
import inspect
import json
import re
import threading
from pathlib import Path

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.db import get_db_query_metrics, reset_db_query_metrics
from player_wiki.session_closeout_presenter import SESSION_CLOSEOUT_STATUS_LABELS
from player_wiki.session_closeout_routes import SESSION_CLOSEOUT_HTML_MAX_BYTES
from player_wiki.session_models import SESSION_CLOSEOUT_ITEM_KEYS
from tests.sample_data import TEST_CAMPAIGN_SLUG


HUB_URL = "/campaigns/linden-pass/manager-tools/session-closeouts"


def _sign_in(sign_in, users, actor: str = "dm") -> None:
    response = sign_in(users[actor]["email"], users[actor]["password"])
    assert response.status_code == 302


def _closed_session(client) -> tuple[int, str]:
    assert client.post("/campaigns/linden-pass/session/start").status_code == 302
    closed = client.post("/campaigns/linden-pass/session/close")
    assert closed.status_code == 302
    location = closed.headers["Location"]
    match = re.search(r"/session/logs/(\d+)$", location)
    assert match is not None
    return int(match.group(1)), location


def _open_closeout(client, session_id: int):
    return client.post(
        f"{HUB_URL}/{session_id}/open",
        follow_redirects=False,
    )


def _closeout(app, session_id: int):
    with app.app_context():
        return app.extensions["campaign_session_store"].get_closeout(
            TEST_CAMPAIGN_SLUG,
            session_id,
        )


def test_presenter_vocabulary_and_item_order_are_frozen() -> None:
    assert SESSION_CLOSEOUT_STATUS_LABELS == {
        "pending": "Pending",
        "complete": "Completed in the owning workflow",
        "not_applicable": "Not applicable",
        "table_managed": "Handled at the table or outside the app",
    }
    assert SESSION_CLOSEOUT_ITEM_KEYS == (
        "table_notes",
        "character_rests",
        "rewards_and_boons",
        "encounter_disposition",
        "session_article_publication",
        "external_archive",
    )


def test_registrar_declares_exact_seven_route_method_contracts(app) -> None:
    expected = {
        "campaign_session_closeouts_view": (HUB_URL, "GET"),
        "campaign_session_closeout_view": (f"{HUB_URL}/<int:session_id>", "GET"),
        "campaign_session_closeout_open": (f"{HUB_URL}/<int:session_id>/open", "POST"),
        "campaign_session_closeout_item_update": (
            f"{HUB_URL}/<int:session_id>/items/<item_key>",
            "POST",
        ),
        "campaign_session_closeout_complete": (
            f"{HUB_URL}/<int:session_id>/complete",
            "POST",
        ),
        "campaign_session_closeout_reopen": (
            f"{HUB_URL}/<int:session_id>/reopen",
            "POST",
        ),
        "campaign_session_closeout_delete_session_history": (
            f"{HUB_URL}/<int:session_id>/delete-session-history",
            "POST",
        ),
    }
    rules = list(app.url_map.iter_rules())
    for endpoint, (path, method) in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path.replace("linden-pass", "<campaign_slug>")
        explicit = set(matches[0].methods) - {"HEAD", "OPTIONS"}
        assert explicit == {method}
        assert ("HEAD" in matches[0].methods) is (method == "GET")

    module_path = Path(__file__).resolve().parents[1] / "player_wiki" / "session_closeout_routes.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    registrar = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_session_closeout_routes"
    )
    assert sum(
        1
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ) == 1


def test_hub_detail_and_log_adoption_use_native_links_and_no_row_delete(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    _sign_in(sign_in, users)
    session_id, log_url = _closed_session(client)

    empty_hub = client.get(HUB_URL)
    assert empty_hub.status_code == 200
    assert "No Session closeouts yet" in empty_hub.get_data(as_text=True)
    assert "Open Session DM Logs" in empty_hub.get_data(as_text=True)

    log = client.get(log_url)
    log_body = log.get_data(as_text=True)
    assert "Start closeout" in log_body
    assert "data-destructive-confirmation" in log_body
    assert "<noscript>" in log_body

    logs_list = client.get("/campaigns/linden-pass/session/dm?dm_view=logs")
    assert f'/session/logs/{session_id}/delete"' not in logs_list.get_data(as_text=True)

    opened = _open_closeout(client, session_id)
    assert opened.status_code == 303
    assert opened.headers["Location"].endswith(f"{HUB_URL}/{session_id}")

    for service_name, method_name in (
        ("character_repository", "list_characters"),
        ("campaign_combat_service", "get_tracker"),
        ("campaign_dm_content_service", "list_statblocks"),
    ):
        service = app.extensions[service_name]
        if hasattr(service, method_name):
            monkeypatch.setattr(
                service,
                method_name,
                lambda *_args, **_kwargs: pytest.fail("owner workflow was read"),
            )

    detail = client.get(f"{HUB_URL}/{session_id}")
    body = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert len(detail.data) <= SESSION_CLOSEOUT_HTML_MAX_BYTES
    assert body.count("data-session-closeout-item") == 6
    assert [body.index(label) for label in (
        "Table notes",
        "Character rests",
        "Rewards and boons",
        "Encounter disposition",
        "Session article publication",
        "External archive acknowledgement",
    )] == sorted(body.index(label) for label in (
        "Table notes",
        "Character rests",
        "Rewards and boons",
        "Encounter disposition",
        "Session article publication",
        "External archive acknowledgement",
    ))
    assert 'href="/campaigns/linden-pass/characters"' in body
    assert 'href="/campaigns/linden-pass/combat/dm?view=controls#combat-tracker"' in body
    assert 'href="/campaigns/linden-pass/dm-content/player-wiki#dm-content-player-wiki-pages"' in body
    assert "View stored Session log" in body
    assert body.count('maxlength="500"') == 6
    assert "Acknowledged outside the app" in body
    assert body.count('aria-current="page"') == 1
    assert re.search(r"<h1[^>]*>Session Closeout</h1>", body)

    resumed_log = client.get(log_url).get_data(as_text=True)
    assert "Resume closeout" in resumed_log
    assert "Delete closeout and Session history" in resumed_log


def test_item_validation_stale_draft_complete_and_reopen_lifecycle(
    app,
    client,
    sign_in,
    users,
) -> None:
    _sign_in(sign_in, users)
    session_id, _ = _closed_session(client)
    _open_closeout(client, session_id)
    current = _closeout(app, session_id)
    assert current is not None

    saved = client.post(
        f"{HUB_URL}/{session_id}/items/table_notes",
        data={
            "expected_revision": current.revision,
            "status": "complete",
            "note": "Table notes filed.",
        },
    )
    assert saved.status_code == 303
    assert saved.headers["Location"].endswith("#closeout-item-1")
    current = _closeout(app, session_id)
    assert current is not None and current.revision == 2

    invalid = client.post(
        f"{HUB_URL}/{session_id}/items/external_archive",
        data={
            "expected_revision": current.revision,
            "status": "complete",
            "note": "https://private.example.invalid/archive",
        },
    )
    invalid_body = invalid.get_data(as_text=True)
    assert invalid.status_code == 400
    assert "External archive closeout may only be pending or table-managed." in invalid_body
    assert 'aria-invalid="true"' in invalid_body
    assert "https://private.example.invalid/archive" in invalid_body
    assert _closeout(app, session_id).revision == 2

    advanced = client.post(
        f"{HUB_URL}/{session_id}/items/character_rests",
        data={
            "expected_revision": current.revision,
            "status": "not_applicable",
            "note": "No rests needed.",
        },
    )
    assert advanced.status_code == 303
    stale = client.post(
        f"{HUB_URL}/{session_id}/items/rewards_and_boons",
        data={
            "expected_revision": current.revision,
            "status": "table_managed",
            "note": "Draft reward note.",
        },
    )
    stale_body = stale.get_data(as_text=True)
    assert stale.status_code == 409
    assert (
        "This closeout changed in another tab. Compare the current saved value with your draft before saving again."
        in stale_body
    )
    assert "Currently saved" in stale_body
    assert "Draft reward note." in stale_body
    assert '<option value="table_managed" selected>' in stale_body

    forged_complete = client.post(
        f"{HUB_URL}/{session_id}/complete",
        data={"expected_revision": _closeout(app, session_id).revision},
    )
    assert forged_complete.status_code == 400
    assert "Resolve all six items before completion." in forged_complete.get_data(as_text=True)

    for item_key in SESSION_CLOSEOUT_ITEM_KEYS:
        current = _closeout(app, session_id)
        item = next(item for item in current.items if item.item_key == item_key)
        if item.status != "pending":
            continue
        status = "table_managed" if item_key == "external_archive" else "not_applicable"
        response = client.post(
            f"{HUB_URL}/{session_id}/items/{item_key}",
            data={
                "expected_revision": current.revision,
                "status": status,
                "note": "",
            },
        )
        assert response.status_code == 303

    current = _closeout(app, session_id)
    completed = client.post(
        f"{HUB_URL}/{session_id}/complete",
        data={"expected_revision": current.revision},
    )
    assert completed.status_code == 303
    completed_record = _closeout(app, session_id)
    assert completed_record.status == "completed"
    completed_page = client.get(f"{HUB_URL}/{session_id}").get_data(as_text=True)
    assert "Reopen closeout" in completed_page
    assert "Save item" not in completed_page

    reopened = client.post(
        f"{HUB_URL}/{session_id}/reopen",
        data={"expected_revision": completed_record.revision},
    )
    assert reopened.status_code == 303
    reopened_record = _closeout(app, session_id)
    assert reopened_record.status == "open"
    assert reopened_record.items[0].note == "Table notes filed."


def test_auth_view_as_csrf_and_campaign_isolation_precede_closeout_mutation(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    _sign_in(sign_in, users)
    session_id, _ = _closed_session(client)
    _open_closeout(client, session_id)
    service = app.extensions["campaign_session_closeout_service"]

    _sign_in(sign_in, users, "party")
    monkeypatch.setattr(
        service,
        "update_item",
        lambda *_args, **_kwargs: pytest.fail("unauthorized mutation reached service"),
    )
    denied = client.post(
        f"{HUB_URL}/{session_id}/items/table_notes",
        data={"expected_revision": 1, "status": "complete", "note": "blocked"},
    )
    assert denied.status_code == 403

    _sign_in(sign_in, users, "admin")
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["dm"]["id"]
    hub = client.get(HUB_URL)
    detail = client.get(f"{HUB_URL}/{session_id}")
    assert hub.status_code == detail.status_code == 200
    assert "View As is read-only" in hub.get_data(as_text=True)
    assert "View As is read-only" in detail.get_data(as_text=True)
    assert "Save item" not in detail.get_data(as_text=True)
    view_as_post = client.post(
        f"{HUB_URL}/{session_id}/items/table_notes",
        data={"expected_revision": 1, "status": "complete", "note": "blocked"},
    )
    assert view_as_post.status_code == 403

    _sign_in(sign_in, users, "dm")
    app.config["CSRF_ENABLED"] = True
    missing_csrf = client.post(
        f"{HUB_URL}/{session_id}/items/table_notes",
        data={"expected_revision": 1, "status": "complete", "note": "blocked"},
    )
    assert missing_csrf.status_code == 400
    assert "Refresh the page and try again." in missing_csrf.get_data(as_text=True)
    app.config["CSRF_ENABLED"] = False

    cross_campaign = client.post(f"{HUB_URL}/999/open")
    assert cross_campaign.status_code == 404


def test_confirmed_deletion_requires_acknowledgement_and_current_revision(
    app,
    client,
    sign_in,
    users,
) -> None:
    _sign_in(sign_in, users)
    session_id, log_url = _closed_session(client)
    _open_closeout(client, session_id)
    current = _closeout(app, session_id)
    with app.app_context():
        session_service = app.extensions["campaign_session_service"]
        revision_before = session_service.get_live_revision(TEST_CAMPAIGN_SLUG)

    delete_url = f"{HUB_URL}/{session_id}/delete-session-history"
    missing_ack = client.post(
        delete_url,
        data={"expected_revision": current.revision},
    )
    assert missing_ack.status_code == 400
    assert "Confirm that you understand" in missing_ack.get_data(as_text=True)
    assert _closeout(app, session_id) is not None

    updated = client.post(
        f"{HUB_URL}/{session_id}/items/table_notes",
        data={
            "expected_revision": current.revision,
            "status": "not_applicable",
            "note": "",
        },
    )
    assert updated.status_code == 303
    stale = client.post(
        delete_url,
        data={
            "expected_revision": current.revision,
            "destructive_acknowledgement": "1",
        },
    )
    assert stale.status_code == 409
    assert "changed after you opened the confirmation" in stale.get_data(as_text=True)

    current = _closeout(app, session_id)
    deleted = client.post(
        delete_url,
        data={
            "expected_revision": current.revision,
            "destructive_acknowledgement": "1",
        },
    )
    assert deleted.status_code == 303
    assert deleted.headers["Location"].endswith(HUB_URL)
    assert _closeout(app, session_id) is None
    assert client.get(log_url).status_code == 404
    with app.app_context():
        assert session_service.get_live_revision(TEST_CAMPAIGN_SLUG) == revision_before + 1


def test_hub_and_detail_query_write_and_html_budgets(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    _sign_in(sign_in, users)
    session_id, _ = _closed_session(client)
    _open_closeout(client, session_id)

    service = app.extensions["campaign_session_closeout_service"]
    original_get = service.get_closeout
    monkeypatch.setattr(
        service,
        "get_closeout",
        lambda *_args, **_kwargs: pytest.fail("hub loaded closeout detail"),
    )
    reset_db_query_metrics()
    hub = client.get(HUB_URL)
    hub_metrics = get_db_query_metrics()
    assert hub.status_code == 200
    assert len(hub.data) <= SESSION_CLOSEOUT_HTML_MAX_BYTES
    assert int(hub_metrics["query_count"]) <= 12
    assert hub_metrics["write_count"] == 0
    assert hub_metrics["commit_count"] == 0

    monkeypatch.setattr(service, "get_closeout", original_get)
    reset_db_query_metrics()
    detail = client.get(f"{HUB_URL}/{session_id}")
    detail_metrics = get_db_query_metrics()
    assert detail.status_code == 200
    assert len(detail.data) <= SESSION_CLOSEOUT_HTML_MAX_BYTES
    assert int(detail_metrics["query_count"]) <= 15
    assert detail_metrics["write_count"] == 0
    assert detail_metrics["commit_count"] == 0


def test_closeout_handlers_authorize_before_request_form_reads(app) -> None:
    for endpoint in (
        "campaign_session_closeout_open",
        "campaign_session_closeout_item_update",
        "campaign_session_closeout_complete",
        "campaign_session_closeout_reopen",
        "campaign_session_closeout_delete_session_history",
    ):
        handler = inspect.unwrap(app.view_functions[endpoint])
        source = inspect.getsource(handler)
        assert source.index("authorize(campaign_slug, mutation=True)") < (
            source.index("request.form") if "request.form" in source else len(source)
        )


@pytest.fixture
def closeout_live_server(app, users):
    from werkzeug.serving import make_server

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        service.begin_session(
            TEST_CAMPAIGN_SLUG,
            started_by_user_id=users["dm"]["id"],
        )
        service.close_session(
            TEST_CAMPAIGN_SLUG,
            ended_by_user_id=users["dm"]["id"],
        )
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_browser_closeout_native_forms_dialog_focus_and_mobile_no_js(
    closeout_live_server,
) -> None:
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        try:
            setup_context = browser.new_context(viewport={"width": 1280, "height": 900})
            setup_page = setup_context.new_page()
            setup_page.goto(f"{closeout_live_server}/sign-in")
            setup_page.get_by_label("Email").fill("dm@example.com")
            setup_page.get_by_label("Password").fill("dm-pass")
            setup_page.get_by_role("button", name="Sign in").click()
            setup_page.wait_for_load_state("load")
            storage_state = setup_context.storage_state()
            setup_context.close()

            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                storage_state=storage_state,
            )
            page = context.new_page()
            page.goto(f"{closeout_live_server}/campaigns/linden-pass/session/logs/1")
            page.get_by_role("button", name="Start closeout").click()
            page.wait_for_load_state("load")
            expect(page.get_by_role("heading", name="Session Closeout", exact=True)).to_be_visible()
            expect(page.locator("[data-session-closeout-item]")).to_have_count(6)
            expect(
                page.get_by_role("navigation", name="Campaign navigation").locator(
                    '[aria-current="page"]'
                )
            ).to_have_text("Manager Tools")
            desktop_overflow = page.evaluate(
                """() => ({
                  scrollWidth: document.documentElement.scrollWidth,
                  clientWidth: document.documentElement.clientWidth,
                  offenders: Array.from(document.querySelectorAll("body *"))
                    .filter((node) => node.getBoundingClientRect().right > document.documentElement.clientWidth + 1 || node.scrollWidth > node.clientWidth + 1)
                    .slice(0, 12)
                    .map((node) => ({
                      tag: node.tagName,
                      className: node.className,
                      id: node.id,
                      right: node.getBoundingClientRect().right,
                      width: node.getBoundingClientRect().width,
                      scrollWidth: node.scrollWidth,
                      clientWidth: node.clientWidth,
                    })),
                })"""
            )
            assert desktop_overflow["scrollWidth"] <= desktop_overflow["clientWidth"], json.dumps(desktop_overflow)

            table_notes = page.locator("#closeout-item-1")
            table_notes.get_by_label("Result").select_option("complete")
            table_notes.get_by_label("Private Session-history note").fill(
                "Saved through the native closeout form."
            )
            table_notes.get_by_role("button", name="Save item").click()
            page.wait_for_load_state("load")
            expect(page.get_by_text("Session closeout item saved.", exact=True)).to_be_visible()

            page.goto(f"{closeout_live_server}/campaigns/linden-pass/session/logs/1")
            trigger = page.get_by_role(
                "button",
                name="Delete closeout and Session history",
            )
            trigger.focus()
            trigger.click()
            dialog = page.get_by_role(
                "dialog",
                name="Permanently delete this closeout and stored Session history?",
            )
            expect(dialog).to_be_visible()
            expect(dialog.get_by_role("button", name="Cancel").first).to_be_focused()
            page.keyboard.press("Escape")
            expect(dialog).not_to_be_visible()
            expect(trigger).to_be_focused()
            context.close()

            no_js = browser.new_context(
                viewport={"width": 390, "height": 800},
                java_script_enabled=False,
                storage_state=storage_state,
            )
            no_js_page = no_js.new_page()
            no_js_page.goto(f"{closeout_live_server}{HUB_URL}/1")
            expect(no_js_page.locator("[data-session-closeout-item]")).to_have_count(6)
            assert no_js_page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )
            rests = no_js_page.locator("#closeout-item-2")
            rests.get_by_label("Result").select_option("not_applicable")
            rests.get_by_role("button", name="Save item").click()
            no_js_page.wait_for_load_state("load")
            expect(no_js_page.get_by_text("Session closeout item saved.", exact=True)).to_be_visible()
            no_js.close()
        finally:
            browser.close()
