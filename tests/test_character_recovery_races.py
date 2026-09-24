from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest
from flask import request

from player_wiki.db import get_db
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG
from tests.test_character_read_shell_browser import (
    _configure_loopback_online,
    _sign_in_browser,
    character_read_shell_live_server,
)
from tests.test_character_reconciliation import _coordinator


@pytest.fixture
def recovery_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright browser unavailable: package missing")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {type(exc).__name__}")
        try:
            yield browser
        finally:
            browser.close()


def _prepare_session(app, users, set_campaign_visibility):
    set_campaign_visibility(TEST_CAMPAIGN_SLUG, characters="players")
    with app.app_context():
        app.extensions["campaign_session_service"].begin_session(
            TEST_CAMPAIGN_SLUG, started_by_user_id=users["dm"]["id"]
        )
        app.extensions["character_repository"].get_character(
            TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG
        )
        return _durable_state()


def _durable_state():
    return tuple(get_db().execute(
        "SELECT * FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
        (TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG),
    ).fetchone())


class _PublicationRecoveryGate:
    """Hold one real journal until the selected request runs its actual owner."""

    def __init__(self, app, monkeypatch):
        self.app = app
        self.operation_id = None
        self.prepared_row = None
        self.definition = None
        self.attempts = []
        self.completed = []
        self.release_request = None
        owner = app.extensions["character_publication_coordinator"]
        # The maintained app fixture selects its temporary DB after create_app;
        # align the owner's captured path with the real request lease provider.
        monkeypatch.setattr(owner, "database_path", Path(app.config["DB_PATH"]))
        original = owner._continue_operation

        def continue_operation(operation_id):
            if operation_id != self.operation_id:
                return original(operation_id)
            identity = (
                request.method, request.path, request.query_string.decode("ascii"),
                request.headers.get("X-Recovery-Race-Release"),
            )
            released = identity == self.release_request
            self.attempts.append((operation_id, identity, released))
            if not released:
                # recover_pending catches this bounded fault. Requests remain live,
                # including assets, on the maintained single-threaded server.
                raise RuntimeError("synthetic owner continuation still pending")
            result = original(operation_id)
            self.completed.append((operation_id, identity, result.definition.to_dict()))
            return result

        monkeypatch.setattr(owner, "_continue_operation", continue_operation)

    def capture(self, operation_id, definition):
        assert self.operation_id is None
        self.operation_id = operation_id
        self.definition = deepcopy(definition.to_dict())
        row = get_db().execute(
            "SELECT * FROM character_reconciliation_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        assert row is not None and row["state"] == "prepared"
        self.prepared_row = tuple(row)

    def assert_pending(self, before):
        assert self.operation_id is not None
        assert not self.completed
        with self.app.app_context():
            row = get_db().execute(
                "SELECT * FROM character_reconciliation_operations WHERE operation_id = ?",
                (self.operation_id,),
            ).fetchone()
            assert row is not None and row["state"] == "prepared"
            assert tuple(row) == self.prepared_row
            assert _durable_state() == before

    def hold_asset_get(self, page, base_url, before):
        asset_url = (
            f"{base_url}/campaigns/{TEST_CAMPAIGN_SLUG}/assets/lore/trade-coast-map.png"
            "?recovery-race=held"
        )
        attempts_before = len(self.attempts)
        response = page.request.get(asset_url)
        assert response.status == 200
        parsed = urlsplit(asset_url)
        selected_attempts = [
            attempt for attempt in self.attempts[attempts_before:]
            if attempt[1][:3] == ("GET", parsed.path, parsed.query)
        ]
        assert selected_attempts == [(
            self.operation_id, ("GET", parsed.path, parsed.query, None), False,
        )]
        self.assert_pending(before)

    def release_headers(self, url):
        parsed = urlsplit(url)
        self.release_request = ("GET", parsed.path, parsed.query, self.operation_id)
        return {"X-Recovery-Race-Release": self.operation_id}

    def assert_completed(self, before, calls, mutation_posts):
        assert self.completed == [(self.operation_id, self.release_request, self.definition)]
        assert [attempt for attempt in self.attempts if attempt[2]] == [(
            self.operation_id, self.release_request, True,
        )]
        assert len(calls) == len(mutation_posts) == 1
        with self.app.app_context():
            assert get_db().execute(
                "SELECT 1 FROM character_reconciliation_operations WHERE campaign_slug = ? AND character_slug = ?",
                (TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG),
            ).fetchone() is None
            assert _durable_state() == before
            character = self.app.extensions["character_repository"].get_character(
                TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG,
            )
            assert character is not None
            assert character.definition.to_dict() == self.definition
            assert _durable_state() == before

    def assert_idempotent_get(self, page, base_url, before, calls, mutation_posts):
        attempts_before = list(self.attempts)
        response = page.request.get(
            f"{base_url}/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}"
            "?page=notes&mode=read"
        )
        assert response.status == 200
        assert self.definition["name"] in response.text()
        assert "data-character-read-shell-root" in response.text()
        assert "data-character-write-conflict=" not in response.text()
        assert self.attempts == attempts_before
        self.assert_completed(before, calls, mutation_posts)

    def release_asset_get(self, page, base_url, before, calls, mutation_posts):
        asset_url = (
            f"{base_url}/campaigns/{TEST_CAMPAIGN_SLUG}/assets/lore/trade-coast-map.png"
            "?recovery-race=released"
        )
        # An ordinary asset GET caused the uncontrolled C0 cleanup. Here that
        # exact owner path must complete only on this explicitly released GET.
        response = page.request.get(asset_url, headers=self.release_headers(asset_url))
        assert response.status == 200
        self.assert_completed(before, calls, mutation_posts)
        self.assert_idempotent_get(page, base_url, before, calls, mutation_posts)


def _collide_with_real_publication(app, monkeypatch, method_name):
    service = app.extensions["character_state_service"]
    original = getattr(service, method_name)
    calls = []
    recovery = _PublicationRecoveryGate(app, monkeypatch)

    def collide(record, **kwargs):
        calls.append(deepcopy(kwargs))

        def hold_publication(event, operation_id):
            if event == "after_commit":
                recovery.capture(operation_id, record.definition)
                raise RuntimeError("synthetic publication held after journal commit")

        with pytest.raises(RuntimeError, match="synthetic publication held"):
            _coordinator(app, hold_publication).update(
                record, record.definition, record.import_metadata, record.state_record.state,
                expected_revision=record.state_record.revision, operation_kind="markdown_import",
            )
        return original(record, **kwargs)

    monkeypatch.setattr(service, method_name, collide)
    return calls, recovery


def _hold_actual_response(page, mutation_path):
    mutation_posts = []
    page.on("request", lambda sent: mutation_posts.append(sent.url)
            if sent.method == "POST" and urlsplit(sent.url).path == mutation_path else None)
    # Send the real request and wait for the app's real Response. Only delivery
    # to the Session shell is delayed; no response status/body is fabricated.
    page.evaluate("""(mutationPath) => {
        const originalFetch = window.fetch.bind(window);
        window.__recoveryRacePostCount = 0;
        window.__recoveryRaceSubmitCount = 0;
        window.__recoveryRaceSubmitFields = [];
        window.__recoveryRaceHeldStatus = null;
        document.addEventListener('submit', event => {
            if (event.target instanceof HTMLFormElement
                && new URL(event.target.action, location.href).pathname === mutationPath) {
                window.__recoveryRaceSubmitCount += 1;
                const scalar = event.target.querySelector('[data-session-currency-autosubmit="1"]');
                if (scalar) window.__recoveryRaceSubmitFields.push(scalar.name);
            }
        }, true);
        window.fetch = async (input, options = {}) => {
            const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
            if (String(options.method || 'GET').toUpperCase() !== 'POST' || path !== mutationPath) {
                return originalFetch(input, options);
            }
            window.__recoveryRacePostCount += 1;
            const response = await originalFetch(input, options);
            if (window.__recoveryRaceHeldStatus === null) {
                window.__recoveryRaceHeldStatus = response.status;
                document.documentElement.dataset.recoveryRaceHeldStatus = String(response.status);
                return new Promise(resolve => {
                    window.__releaseRecoveryRaceResponse = () => resolve(response);
                });
            }
            return response;
        };
    }""", mutation_path)
    return mutation_posts


def _assert_recovery_stays_inert(page, recovery, base_url, before, calls):
    from playwright.sync_api import expect

    pane = page.locator("[data-session-shell-pane='character']")
    expect(pane.get_by_role("heading", name="Update not saved", exact=True)).to_be_visible()
    assert pane.locator("form").count() == 0
    assert pane.locator("button[type='submit'], input[type='submit']").count() == 0
    # Allow the normal autosubmit debounce and queue microtasks to become due.
    page.wait_for_timeout(750)
    assert page.evaluate("window.__recoveryRacePostCount") == 1
    assert len(calls) == 1
    recovery.assert_pending(before)
    recovery.hold_asset_get(page, base_url, before)


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 800}], ids=["desktop", "mobile"])
def test_session_protected_response_preserves_notes_typed_after_submission(
    app, users, set_campaign_visibility, character_read_shell_live_server,
    monkeypatch, recovery_browser, viewport,
):
    from playwright.sync_api import expect

    before = _prepare_session(app, users, set_campaign_visibility)
    calls, recovery = _collide_with_real_publication(app, monkeypatch, "update_player_notes")
    base_url = character_read_shell_live_server
    context = recovery_browser.new_context(viewport=viewport)
    try:
        page = context.new_page()
        _configure_loopback_online(page)
        _sign_in_browser(page, base_url, users["owner"])
        page.goto(f"{base_url}/campaigns/{TEST_CAMPAIGN_SLUG}/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=notes")
        mutation_path = f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}/session/notes"
        mutation_posts = _hold_actual_response(page, mutation_path)
        notes = page.locator("textarea[name='player_notes_markdown']")
        submitted = "Submitted notes before the response was delayed."
        newest = "Newest local notes <script>window.recoveryDraftExecuted = true</script>"
        notes.fill(submitted)
        page.locator("form:has(textarea[name='player_notes_markdown']) button[type='submit']").click()
        expect(page.locator("html")).to_have_attribute("data-recovery-race-held-status", "409")
        expect(notes).to_be_editable()
        notes.fill(newest)
        page.evaluate("window.__releaseRecoveryRaceResponse()")

        copy = page.locator("[data-character-local-draft='player_notes_markdown']")
        expect(copy).to_have_value(newest)
        expect(copy).to_have_attribute("readonly", "")
        expect(copy).to_be_visible()
        copy.focus()
        expect(copy).to_be_focused()
        copy.press("ControlOrMeta+A")
        assert copy.evaluate("element => element.selectionEnd - element.selectionStart") == len(newest)
        assert page.evaluate("Boolean(window.recoveryDraftExecuted)") is False
        assert calls[0]["notes_markdown"] == submitted
        assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"] + 2
        _assert_recovery_stays_inert(page, recovery, base_url, before, calls)
        recovery.release_asset_get(page, base_url, before, calls, mutation_posts)
    finally:
        context.close()


def test_session_protected_response_preserves_queued_currency_without_retry(
    app, users, set_campaign_visibility, character_read_shell_live_server,
    monkeypatch, recovery_browser,
):
    from playwright.sync_api import expect

    before = _prepare_session(app, users, set_campaign_visibility)
    calls, recovery = _collide_with_real_publication(app, monkeypatch, "update_currency")
    base_url = character_read_shell_live_server
    context = recovery_browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        _configure_loopback_online(page)
        _sign_in_browser(page, base_url, users["owner"])
        page.goto(f"{base_url}/campaigns/{TEST_CAMPAIGN_SLUG}/session/character?character={ASSIGNED_CHARACTER_SLUG}&page=inventory")
        mutation_path = f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}/session/currency"
        mutation_posts = _hold_actual_response(page, mutation_path)
        copper = page.locator("input[name='cp'][data-session-currency-autosubmit='1']")
        gold = page.locator("input[name='gp'][data-session-currency-autosubmit='1']")
        copper.fill("123")
        copper.dispatch_event("change")
        expect(page.locator("html")).to_have_attribute("data-recovery-race-held-status", "409")

        gold.fill("456")
        gold.dispatch_event("change")
        # Moving focus can also dispatch the first field's native change event.
        assert page.evaluate("window.__recoveryRaceSubmitCount") >= 2
        assert "gp" in page.evaluate("window.__recoveryRaceSubmitFields")
        assert page.evaluate("window.__recoveryRacePostCount") == 1
        # Even the queued form may receive a newer edit before recovery mounts.
        gold.fill("457")
        page.evaluate("window.__releaseRecoveryRaceResponse()")

        copper_copy = page.locator("[data-character-local-draft='cp']")
        gold_copy = page.locator("[data-character-local-draft='gp']")
        expect(copper_copy).to_have_value("123")
        expect(gold_copy).to_have_value("457")
        for copy in (copper_copy, gold_copy):
            expect(copy).to_have_attribute("readonly", "")
            expect(copy).to_be_visible()
        assert calls[0]["values"]["cp"] == "123"
        assert calls[0]["values"]["gp"] is None
        _assert_recovery_stays_inert(page, recovery, base_url, before, calls)
        recovery.release_asset_get(page, base_url, before, calls, mutation_posts)
    finally:
        context.close()


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 800}], ids=["desktop", "mobile"])
def test_character_protected_response_preserves_notes_typed_after_submission(
    app, users, set_campaign_visibility, character_read_shell_live_server,
    monkeypatch, recovery_browser, viewport,
):
    from playwright.sync_api import expect

    before = _prepare_session(app, users, set_campaign_visibility)
    calls, recovery = _collide_with_real_publication(app, monkeypatch, "update_player_notes")
    base_url = character_read_shell_live_server
    character_path = f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}"
    context = recovery_browser.new_context(viewport=viewport)
    try:
        page = context.new_page()
        _configure_loopback_online(page)
        _sign_in_browser(page, base_url, users["owner"])
        page.goto(f"{base_url}{character_path}?page=notes&mode=session")
        mutation_posts = _hold_actual_response(page, character_path + "/session/notes")
        notes = page.locator("textarea[name='player_notes_markdown']")
        submitted_mode = page.locator("form:has(textarea[name='player_notes_markdown']) input[name='mode']").input_value()
        submitted = "Standalone notes submitted before the response was delayed."
        newest = "Newer standalone notes <script>window.recoveryDraftExecuted = true</script>"
        notes.fill(submitted)
        page.locator("form:has(textarea[name='player_notes_markdown']) button[type='submit']").click()
        expect(page.locator("html")).to_have_attribute("data-recovery-race-held-status", "409")
        expect(notes).to_be_editable()
        notes.fill(newest)
        page.evaluate("window.__releaseRecoveryRaceResponse()")

        scope = page.locator("[data-character-read-shell-panel]")
        expect(page.get_by_role("heading", name="Update not saved", exact=True)).to_be_visible()
        copy = scope.locator("[data-character-local-draft='player_notes_markdown']")
        expect(copy).to_have_value(newest)
        expect(copy).to_have_attribute("readonly", "")
        expect(copy).to_be_visible()
        copy.focus()
        expect(copy).to_be_focused()
        copy.press("ControlOrMeta+A")
        assert copy.evaluate("element => element.selectionEnd - element.selectionStart") == len(newest)
        # The submitted server draft remains distinct from the newer local copy.
        expect(scope.locator("textarea[name='player_notes_markdown']")).to_have_value(submitted)
        assert page.evaluate("Boolean(window.recoveryDraftExecuted)") is False
        assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"] + 2
        assert scope.locator("form").count() == 0
        assert scope.locator("button[type='submit'], input[type='submit']").count() == 0
        page.wait_for_timeout(750)
        assert page.evaluate("window.__recoveryRacePostCount") == 1
        assert len(calls) == 1
        assert calls[0]["notes_markdown"] == submitted
        recovery.assert_pending(before)
        recovery.hold_asset_get(page, base_url, before)

        refresh = scope.get_by_role("link", name="Refresh Character", exact=True)
        refresh_url = urlsplit(refresh.get_attribute("href"))
        assert refresh_url.path == character_path
        assert parse_qs(refresh_url.query) == {"page": ["notes"], "mode": [submitted_mode]}
        native_url = urljoin(base_url, refresh.get_attribute("href"))
        release_headers = recovery.release_headers(native_url)

        def release_native_navigation(route):
            # Preserve the native link URL/mode and mark only its navigation GET.
            # Background requests cannot release the operation with this header.
            if route.request.method == "GET" and route.request.is_navigation_request():
                route.continue_(headers={**route.request.headers, **release_headers})
            else:
                route.continue_()

        page.route(native_url, release_native_navigation)
        with page.expect_request(lambda sent: sent.method == "GET" and urlsplit(sent.url).path == character_path), page.expect_response(
            lambda response: response.request.method == "GET" and response.url == native_url
        ) as refreshed:
            refresh.click()
        assert refreshed.value.status == 200
        page.wait_for_load_state("load")
        expect(page.locator("[data-character-read-shell-root]")).to_be_visible()
        assert page.locator("[data-character-write-conflict]").count() == 0
        assert len(calls) == 1
        recovery.assert_completed(before, calls, mutation_posts)
        recovery.assert_idempotent_get(page, base_url, before, calls, mutation_posts)
    finally:
        context.close()
