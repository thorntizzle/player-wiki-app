from __future__ import annotations

from dataclasses import replace
from html import unescape
import re
import threading
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

import pytest

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.mechanics_impact import (
    MechanicsImpactCursorError,
    MechanicsImpactIdentity,
)
from player_wiki.mechanics_impact_presenter import (
    MECHANICS_IMPACT_BROWSER_ERROR_MAX_BYTES,
    MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES,
    parse_mechanics_impact_detail_query,
    parse_mechanics_impact_queue_query,
)
from player_wiki.db import get_db_query_metrics
from player_wiki.source_health import (
    SourceHealthConsumer,
    SourceHealthInventoryPage,
    SourceHealthReference,
)
from tests.sample_data import TEST_CAMPAIGN_SLUG


QUEUE_PATH = f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/mechanics-impact"
DETAIL_PATH = f"{QUEUE_PATH}/review"


@pytest.fixture
def mechanics_impact_live_server(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _sign_in(sign_in, users, actor: str) -> None:
    credentials = users[actor]
    assert sign_in(credentials["email"], credentials["password"]).status_code == 302


def _seed_review_entry(
    app,
    *,
    source_id: str = "MI-BROWSER",
    slug: str = "safe-review",
    metadata: dict[str, object] | None = None,
):
    entry_key = f"item|{source_id}|safe-review"
    with app.app_context():
        store = app.extensions["systems_store"]
        store.upsert_library("DND-5E", title="DND-5E", system_code="DND-5E")
        store.upsert_source(
            "DND-5E",
            source_id,
            title="PRIVATE SOURCE TITLE",
            license_class="custom_campaign",
            public_visibility_allowed=True,
        )
        store.upsert_entry(
            "DND-5E",
            source_id,
            entry_key=entry_key,
            entry_type="item",
            slug=slug,
            title="PRIVATE ENTRY TITLE",
            source_path="C:/PRIVATE/SOURCE/PATH.json",
            search_text="PRIVATE SEARCH TEXT",
            metadata=metadata
            or {
                "campaign_item_mechanics_review_status": "draft",
                "campaign_item_mechanics_support_state": "needs_implementation",
                "campaign_item_mechanics_flags": [{"code": "manual_check"}],
                "bonus_ac": 1,
                "private_metadata": "PRIVATE METADATA",
            },
            body={"entries": ["PRIVATE BODY TEXT"]},
            rendered_html="<p>PRIVATE RENDERED HTML</p>",
        )
        store.upsert_campaign_enabled_source(
            TEST_CAMPAIGN_SLUG,
            library_slug="DND-5E",
            source_id=source_id,
            is_enabled=True,
            default_visibility="dm",
        )
    return entry_key


def _first_detail_url(body: str) -> str:
    match = re.search(r'href="([^"]*systems/mechanics-impact/review[^"]*)"', body)
    assert match is not None
    return unescape(match.group(1))


def _get_with_db_metrics(client, path: str):
    with client:
        response = client.get(path)
        metrics = get_db_query_metrics()
    return response, metrics


@pytest.mark.parametrize(
    "raw_query",
    (
        b"continuation=",
        b"continuation=one&continuation=two",
        b"unknown=value",
        b"continuation=%",
        b"continuation=%FF",
        b"continuation=" + b"x" * 4_096,
    ),
)
def test_queue_query_grammar_rejects_blank_duplicate_unknown_malformed_and_oversized(raw_query):
    with pytest.raises(MechanicsImpactCursorError):
        parse_mechanics_impact_queue_query(QUEUE_PATH, raw_query)


@pytest.mark.parametrize(
    "raw_query",
    (
        b"",
        b"selection=",
        b"selection=one&selection=two",
        b"selection=one&unknown=value",
        b"owner=characters",
        b"selection=one&owner=unknown",
        b"selection=one&owner_continuation=two",
        b"preview=one",
        b"character=hero",
        b"preview=one&character=hero&selection=two",
    ),
)
def test_detail_query_grammar_rejects_incompatible_or_incomplete_shapes(raw_query):
    with pytest.raises(MechanicsImpactCursorError):
        parse_mechanics_impact_detail_query(DETAIL_PATH, raw_query)


def test_browser_admission_precedes_query_parsing_and_honors_view_as(
    app, client, sign_in, users, monkeypatch
):
    presenter = app.extensions["mechanics_impact_presenter"]
    calls: list[str] = []

    def forbidden_queue(*_args, **_kwargs):
        calls.append("queue")
        raise AssertionError("inventory must not run")

    monkeypatch.setattr(presenter.kernel, "list_queue", forbidden_queue)
    signed_out = client.get(f"{QUEUE_PATH}?continuation=not-parsed")
    assert signed_out.status_code == 302
    assert calls == []

    for actor in ("owner", "observer", "outsider"):
        _sign_in(sign_in, users, actor)
        denied = client.get(f"{QUEUE_PATH}?continuation=not-parsed")
        assert denied.status_code == 403
        assert calls == []

    _sign_in(sign_in, users, "admin")
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    denied_view_as = client.get(f"{QUEUE_PATH}?continuation=not-parsed")
    assert denied_view_as.status_code == 403
    assert calls == []

    client.post("/sign-out")
    assert client.get("/campaigns/not-a-campaign/systems/mechanics-impact").status_code == 404


def test_queue_and_detail_render_only_allowlisted_identity_status_and_preview_fields(
    app, client, sign_in, users
):
    entry_key = _seed_review_entry(app)
    _sign_in(sign_in, users, "dm")

    queue = client.get(QUEUE_PATH)
    queue_body = queue.get_data(as_text=True)
    assert queue.status_code == 200
    assert len(queue.data) <= MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES
    assert queue.headers["Cache-Control"] == "private, no-store"
    assert queue.headers["Referrer-Policy"] == "no-referrer"
    assert queue_body.count("<h1") == 1
    assert entry_key in queue_body
    assert "Needs implementation" in queue_body
    for private_value in (
        "PRIVATE ENTRY TITLE",
        "PRIVATE SOURCE TITLE",
        "PRIVATE SEARCH TEXT",
        "PRIVATE METADATA",
        "PRIVATE BODY TEXT",
        "PRIVATE RENDERED HTML",
        "C:/PRIVATE/SOURCE/PATH.json",
    ):
        assert private_value not in queue_body

    detail_url = _first_detail_url(queue_body)
    parsed = urlsplit(detail_url)
    params = parse_qs(parsed.query)
    assert list(params) == ["selection", "queue_return"]
    assert entry_key not in parsed.query

    detail = client.get(detail_url)
    detail_body = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert len(detail.data) <= MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES
    assert detail.headers["Cache-Control"] == "private, no-store"
    assert detail.headers["Referrer-Policy"] == "no-referrer"
    assert detail_body.count("<h1") == 1
    assert "Deterministic approval preview" in detail_body
    assert "Bonus Ac" in detail_body
    assert "Manual Check" in detail_body
    assert "Draft" in detail_body and "Approved" in detail_body
    assert "This review does not approve, edit, acknowledge, or update" in detail_body
    for private_value in (
        "PRIVATE ENTRY TITLE",
        "PRIVATE SOURCE TITLE",
        "PRIVATE SEARCH TEXT",
        "PRIVATE METADATA",
        "PRIVATE BODY TEXT",
        "PRIVATE RENDERED HTML",
        "C:/PRIVATE/SOURCE/PATH.json",
    ):
        assert private_value not in detail_body
    main_markup = detail_body[detail_body.index("<main") : detail_body.index("</main>")]
    assert "<form" not in main_markup
    assert "<script" not in main_markup
    assert "fetch(" not in main_markup


@pytest.mark.parametrize(
    "metadata",
    (
        {
            "campaign_item_mechanics_review_status": "SECRET_REVIEW_CANARY",
            "review_status": "approved",
            "campaign_item_mechanics_support_state": "modeled",
        },
        {
            "campaign_item_mechanics_review_status": " ",
            "review_status": "SECRET_REVIEW_CANARY",
            "campaign_item_mechanics_support_state": "modeled",
        },
        {
            "campaign_item_mechanics_review_status": "approved",
            "campaign_item_mechanics_support_state": "SECRET_SUPPORT_CANARY",
            "support_state": "modeled",
            "xianxia_support_state": "reference_only",
        },
        {
            "campaign_item_mechanics_review_status": "approved",
            "campaign_item_mechanics_support_state": " ",
            "support_state": "SECRET_SUPPORT_CANARY",
            "xianxia_support_state": "modeled",
        },
        {
            "campaign_item_mechanics_review_status": "approved",
            "campaign_item_mechanics_support_state": " ",
            "support_state": " ",
            "xianxia_support_state": "SECRET_SUPPORT_CANARY",
        },
    ),
    ids=(
        "campaign-review",
        "fallback-review",
        "campaign-support",
        "fallback-support",
        "xianxia-support",
    ),
)
def test_invalid_effective_status_keys_render_only_fixed_metadata_labels(
    app, client, sign_in, users, monkeypatch, metadata
):
    entry_key = _seed_review_entry(app)
    kernel = app.extensions["mechanics_impact_kernel"]
    selected_identity = MechanicsImpactIdentity(
        "DND-5E", "MI-BROWSER", entry_key
    )
    with app.app_context():
        current = kernel.systems_service.resolve_mechanics_impact_entry(
            selected_identity
        )
    assert current is not None
    invalid = replace(current, metadata=metadata)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("invalid metadata must not inspect or interpret consumers")

    monkeypatch.setattr(
        kernel.systems_service,
        "resolve_mechanics_impact_entry",
        lambda resolved_identity: invalid
        if resolved_identity == selected_identity
        else None,
    )
    monkeypatch.setattr(
        kernel.systems_service,
        "build_mechanics_impact_approval_proposal",
        forbidden,
    )
    monkeypatch.setattr(kernel, "_preview_resolved", forbidden)
    monkeypatch.setitem(kernel._inventory_adapters, "characters", forbidden)
    _sign_in(sign_in, users, "dm")

    queue = client.get(QUEUE_PATH)
    detail_url = _first_detail_url(queue.get_data(as_text=True))
    detail_params = parse_qs(urlsplit(detail_url).query)
    detail = client.get(
        f"{DETAIL_PATH}?selection={detail_params['selection'][0]}"
        f"&owner=characters&queue_return={detail_params['queue_return'][0]}"
    )

    assert detail.status_code == 200
    body = detail.get_data(as_text=True)
    assert entry_key in body
    assert body.count("<dd>Invalid Metadata</dd>") == 2
    for canary in (
        "SECRET_REVIEW_CANARY",
        "SECRET_SUPPORT_CANARY",
        "Secret Review Canary",
        "Secret Support Canary",
    ):
        assert canary not in body
    assert "Edit custom entry" not in body
    assert "Edit shared/core entry" not in body
    assert "Manage campaign override" not in body


@pytest.mark.parametrize(
    "metadata",
    (
        {
            "campaign_item_mechanics_review_status": "draft",
            "review_status": "SECRET_REVIEW_CANARY",
            "campaign_item_mechanics_support_state": "modeled",
        },
        {
            "campaign_item_mechanics_review_status": "approved",
            "campaign_item_mechanics_support_state": "needs_implementation",
            "support_state": "SECRET_SUPPORT_CANARY",
            "xianxia_support_state": "SECRET_SUPPORT_CANARY",
        },
    ),
    ids=("review-first-nonblank", "support-first-nonblank"),
)
def test_status_precedence_keeps_dormant_canaries_out_of_detail_html(
    app, client, sign_in, users, metadata
):
    _seed_review_entry(app, metadata=metadata)
    _sign_in(sign_in, users, "dm")

    queue = client.get(QUEUE_PATH)
    detail = client.get(_first_detail_url(queue.get_data(as_text=True)))

    assert detail.status_code == 200
    body = detail.get_data(as_text=True)
    assert "Invalid metadata" not in body
    for canary in (
        "SECRET_REVIEW_CANARY",
        "SECRET_SUPPORT_CANARY",
        "Secret Review Canary",
        "Secret Support Canary",
    ):
        assert canary not in body


def test_tamper_stale_methods_and_all_response_headers_are_sanitized(
    app, client, sign_in, users
):
    _seed_review_entry(app)
    _sign_in(sign_in, users, "dm")
    queue = client.get(QUEUE_PATH)
    detail_url = _first_detail_url(queue.get_data(as_text=True))
    parsed = urlsplit(detail_url)
    params = parse_qs(parsed.query)
    selection = params["selection"][0]
    tampered = f"{selection[:-1]}{'A' if selection[-1] != 'A' else 'B'}"
    bad = client.get(f"{DETAIL_PATH}?selection={tampered}")
    assert bad.status_code == 400
    assert selection.encode() not in bad.data
    assert len(bad.data) <= MECHANICS_IMPACT_BROWSER_ERROR_MAX_BYTES

    with app.app_context():
        store = app.extensions["systems_store"]
        store.upsert_entry(
            "DND-5E",
            "MI-BROWSER",
            entry_key="item|MI-BROWSER|different-row",
            entry_type="item",
            slug="different-row",
            title="PRIVATE DRIFT TITLE",
            metadata={"review_status": "draft"},
        )
    stale = client.get(detail_url)
    assert stale.status_code == 409
    assert b"PRIVATE DRIFT TITLE" not in stale.data
    assert len(stale.data) <= MECHANICS_IMPACT_BROWSER_ERROR_MAX_BYTES

    for path in (QUEUE_PATH, DETAIL_PATH):
        head = client.head(path if path == QUEUE_PATH else f"{path}?selection=bad")
        assert head.status_code in {200, 400}
        assert head.data == b""
        assert head.headers["Cache-Control"] == "private, no-store"
        assert head.headers["Referrer-Policy"] == "no-referrer"

        options = client.open(path, method="OPTIONS")
        assert options.status_code == 200
        assert options.headers["Cache-Control"] == "private, no-store"
        assert options.headers["Referrer-Policy"] == "no-referrer"

        post = client.post(path)
        assert post.status_code == 405
        assert post.headers["Cache-Control"] == "private, no-store"
        assert post.headers["Referrer-Policy"] == "no-referrer"


def test_one_authorized_owner_page_and_one_character_preview_are_bounded_and_redacted(
    app, client, sign_in, users, monkeypatch
):
    entry_key = _seed_review_entry(app)
    kernel = app.extensions["mechanics_impact_kernel"]
    adapter_calls: list[str] = []
    projection_calls: list[tuple[str, str]] = []

    def characters_adapter(context, continuation):
        adapter_calls.append(continuation)
        return SourceHealthInventoryPage(
            consumers=(
                SourceHealthConsumer(
                    consumer_type="character",
                    consumer_key="arden-march:equipment_catalog[0].systems_ref",
                    surface="Character",
                    reference=SourceHealthReference(
                        target_kind="systems",
                        library_slug="DND-5E",
                        source_id="MI-BROWSER",
                        entry_key=entry_key,
                    ),
                    destination=(
                        f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/arden-march"
                    ),
                ),
            ),
            definition_file_count=1,
            definition_bytes=128,
        )

    monkeypatch.setitem(kernel._inventory_adapters, "characters", characters_adapter)
    monkeypatch.setattr(
        kernel,
        "_character_authorize",
        lambda campaign_slug, character_slug: (
            campaign_slug == TEST_CAMPAIGN_SLUG and character_slug == "arden-march"
        ),
    )
    monkeypatch.setattr(
        kernel,
        "_character_preview",
        lambda campaign_slug, character_slug, _current, _proposed: (
            projection_calls.append((campaign_slug, character_slug))
            or ("a" * 64, "b" * 64)
        ),
    )
    _sign_in(sign_in, users, "dm")

    detail_url = _first_detail_url(client.get(QUEUE_PATH).get_data(as_text=True))
    detail_params = parse_qs(urlsplit(detail_url).query)
    owner_url = (
        f"{DETAIL_PATH}?selection={detail_params['selection'][0]}"
        f"&owner=characters&queue_return={detail_params['queue_return'][0]}"
    )
    owner = client.get(owner_url)
    owner_body = owner.get_data(as_text=True)
    assert owner.status_code == 200
    assert adapter_calls == [""]
    assert projection_calls == []
    assert "arden-march:equipment_catalog[0].systems_ref" in owner_body
    preview_match = re.search(
        r'href="([^"]*mechanics-impact/review\?preview=[^"]+)"', owner_body
    )
    assert preview_match is not None
    preview_url = unescape(preview_match.group(1))
    assert entry_key not in urlsplit(preview_url).query

    selected = client.get(preview_url)
    selected_body = selected.get_data(as_text=True)
    assert selected.status_code == 200, preview_url
    assert adapter_calls == [""]
    assert projection_calls == [(TEST_CAMPAIGN_SLUG, "arden-march")]
    assert "Selected Character projection changes" in selected_body
    assert ">Yes<" in selected_body
    assert "a" * 64 not in selected_body
    assert "b" * 64 not in selected_body

    parsed_preview = parse_qs(urlsplit(preview_url).query)
    inexact = client.get(
        f"{DETAIL_PATH}?preview={parsed_preview['preview'][0]}&character=other"
    )
    assert inexact.status_code == 409
    assert projection_calls == [(TEST_CAMPAIGN_SLUG, "arden-march")]


def test_warmed_queue_and_detail_stay_within_frozen_query_and_write_bounds(
    app, client, sign_in, users
):
    _seed_review_entry(app)
    _sign_in(sign_in, users, "dm")

    _get_with_db_metrics(client, QUEUE_PATH)
    queue, queue_metrics = _get_with_db_metrics(client, QUEUE_PATH)
    assert queue.status_code == 200
    assert int(queue_metrics["query_count"]) <= 8
    assert queue_metrics["write_count"] == 0
    assert queue_metrics["commit_count"] == 0
    assert queue_metrics["rollback_count"] == 0

    detail_url = _first_detail_url(queue.get_data(as_text=True))
    _get_with_db_metrics(client, detail_url)
    detail, detail_metrics = _get_with_db_metrics(client, detail_url)
    assert detail.status_code == 200
    assert int(detail_metrics["query_count"]) <= 12
    assert detail_metrics["write_count"] == 0
    assert detail_metrics["commit_count"] == 0
    assert detail_metrics["rollback_count"] == 0


def test_warmed_queue_owner_detail_and_character_preview_meet_frozen_p95_bounds(
    app, client, sign_in, users, monkeypatch
):
    entry_key = _seed_review_entry(app)
    kernel = app.extensions["mechanics_impact_kernel"]

    def characters_adapter(context, continuation):
        return SourceHealthInventoryPage(
            consumers=(
                SourceHealthConsumer(
                    consumer_type="character",
                    consumer_key="arden-march:equipment_catalog[0].systems_ref",
                    surface="Character",
                    reference=SourceHealthReference(
                        target_kind="systems",
                        library_slug="DND-5E",
                        source_id="MI-BROWSER",
                        entry_key=entry_key,
                    ),
                    destination=(
                        f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/arden-march"
                    ),
                ),
            ),
            definition_file_count=1,
            definition_bytes=128,
        )

    monkeypatch.setitem(kernel._inventory_adapters, "characters", characters_adapter)
    monkeypatch.setattr(kernel, "_character_authorize", lambda *_args: True)
    monkeypatch.setattr(
        kernel,
        "_character_preview",
        lambda *_args: ("a" * 64, "b" * 64),
    )
    _sign_in(sign_in, users, "dm")

    queue = client.get(QUEUE_PATH)
    detail_url = _first_detail_url(queue.get_data(as_text=True))
    detail_params = parse_qs(urlsplit(detail_url).query)
    owner_url = (
        f"{DETAIL_PATH}?selection={detail_params['selection'][0]}"
        f"&owner=characters&queue_return={detail_params['queue_return'][0]}"
    )
    owner = client.get(owner_url)
    preview_match = re.search(
        r'href="([^"]*mechanics-impact/review\?preview=[^"]+)"',
        owner.get_data(as_text=True),
    )
    assert preview_match is not None
    preview_url = unescape(preview_match.group(1))

    def warmed_p95_ms(path: str, *, max_bytes: int):
        for _ in range(3):
            response, _metrics = _get_with_db_metrics(client, path)
            assert response.status_code == 200
        samples = []
        metrics = None
        for _ in range(20):
            started = perf_counter()
            response, metrics = _get_with_db_metrics(client, path)
            samples.append((perf_counter() - started) * 1_000)
            assert response.status_code == 200
            assert len(response.data) <= max_bytes
        assert metrics is not None
        return sorted(samples)[18], metrics

    queue_p95, queue_metrics = warmed_p95_ms(
        QUEUE_PATH,
        max_bytes=MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES,
    )
    owner_p95, owner_metrics = warmed_p95_ms(
        owner_url,
        max_bytes=MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES,
    )
    preview_p95, preview_metrics = warmed_p95_ms(
        preview_url,
        max_bytes=MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES,
    )

    assert queue_p95 <= 100.0
    assert owner_p95 <= 150.0
    assert preview_p95 <= 500.0
    assert int(queue_metrics["query_count"]) <= 8
    assert queue_metrics["write_count"] == 0
    assert queue_metrics["commit_count"] == 0
    assert queue_metrics["rollback_count"] == 0
    assert int(owner_metrics["query_count"]) <= 12
    assert owner_metrics["write_count"] == 0
    assert owner_metrics["commit_count"] == 0
    assert owner_metrics["rollback_count"] == 0
    assert int(preview_metrics["query_count"]) <= 24
    assert preview_metrics["write_count"] == 0
    assert preview_metrics["commit_count"] == 0
    assert preview_metrics["rollback_count"] == 0


def test_systems_management_hosts_add_only_the_static_count_free_review_link(
    app, client, sign_in, users, monkeypatch
):
    presenter = app.extensions["mechanics_impact_presenter"]

    def forbidden(*_args, **_kwargs):
        raise AssertionError("management hosts must not inspect mechanics impact")

    monkeypatch.setattr(presenter.kernel, "list_queue", forbidden)
    monkeypatch.setattr(presenter.kernel, "review", forbidden)
    _sign_in(sign_in, users, "dm")

    settings = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/control-panel")
    dm_content = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/dm-content/systems")

    assert settings.status_code == 200
    assert dm_content.status_code == 200
    for response in (settings, dm_content):
        body = response.get_data(as_text=True)
        assert body.count("Open mechanics review") == 1
        assert f'href="{QUEUE_PATH}"' in body
        assert "mechanics review (" not in body.lower()


def test_implementer_real_browser_smoke_is_native_responsive_focusable_and_no_js(
    app,
    mechanics_impact_live_server,
) -> None:
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    _seed_review_entry(app)
    scenarios = (
        ({"width": 1280, "height": 900}, True),
        ({"width": 390, "height": 800}, False),
    )
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        try:
            for viewport, java_script_enabled in scenarios:
                context = browser.new_context(
                    viewport=viewport,
                    java_script_enabled=java_script_enabled,
                )
                page = context.new_page()
                page.goto(f"{mechanics_impact_live_server}/sign-in")
                page.get_by_label("Email").fill("dm@example.com")
                page.get_by_label("Password").fill("dm-pass")
                page.get_by_role("button", name="Sign in").click()
                page.wait_for_load_state("load")

                response = page.goto(
                    f"{mechanics_impact_live_server}{QUEUE_PATH}",
                    wait_until="load",
                )
                assert response is not None and response.status == 200
                expect(
                    page.get_by_role("heading", name="Mechanics review", exact=True)
                ).to_be_visible()
                expect(page.get_by_role("link", name="Review support")).to_have_count(1)
                assert page.locator("main form").count() == 0
                assert page.locator("main script").count() == 0
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                page.keyboard.press("Tab")
                expect(page.locator(".skip-link")).to_be_focused()
                page.keyboard.press("Enter")
                expect(page.locator("#main-content")).to_be_focused()

                page.get_by_role("link", name="Review support").click()
                page.wait_for_load_state("load")
                expect(
                    page.get_by_role(
                        "heading", name="Mechanics review detail", exact=True
                    )
                ).to_be_visible()
                assert page.locator("main form").count() == 0
                assert page.locator("main script").count() == 0
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                context.close()
        finally:
            browser.close()
