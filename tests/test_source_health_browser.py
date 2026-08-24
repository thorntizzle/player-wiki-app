from __future__ import annotations

from dataclasses import replace

import pytest
from flask import request

import player_wiki.db as db_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.db import get_db_query_metrics
from player_wiki.source_health import (
    SOURCE_HEALTH_ACTION_LABELS,
    SOURCE_HEALTH_BROWSER_ADAPTER_ROSTER,
    SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES,
    SOURCE_HEALTH_CLASSIFICATION_LABELS,
    SOURCE_HEALTH_STATE_LABELS,
    SourceHealthBrowserCursorCodec,
    SourceHealthConsumer,
    SourceHealthCursorError,
    SourceHealthFinding,
    SourceHealthReference,
    SourceHealthReport,
    SourceHealthService,
    SourceHealthTarget,
    present_source_health_report,
    source_health_action_destination,
)
from tests.sample_data import TEST_CAMPAIGN_SLUG


SOURCE_HEALTH_SUCCESS_BODY_MAX_BYTES = 131_072
SOURCE_HEALTH_ERROR_BODY_MAX_BYTES = 65_536


class _ReportService:
    def __init__(self, report: SourceHealthReport) -> None:
        self.report = report
        self.calls: list[tuple[str, str]] = []

    def build_report(self, campaign_slug: str, *, continuation: str = "") -> SourceHealthReport:
        self.calls.append((campaign_slug, continuation))
        return replace(self.report, campaign_slug=campaign_slug)


def _sign_in(sign_in, users, actor: str) -> None:
    credentials = users[actor]
    response = sign_in(credentials["email"], credentials["password"])
    assert response.status_code == 302


def _report(*, state: str = "empty", findings=(), continuations=()) -> SourceHealthReport:
    return SourceHealthReport(
        campaign_slug=TEST_CAMPAIGN_SLUG,
        state=state,
        findings=tuple(findings),
        complete=not bool(continuations),
        continuations=tuple(continuations),
        message="Sanitized Source Health status.",
    )


def _finding(*, action: str, destination: str) -> SourceHealthFinding:
    return SourceHealthFinding(
        consumer=SourceHealthConsumer(
            consumer_type="character",
            consumer_key="safe-character:spellcasting.spells[0]",
            surface="Character",
            reference=SourceHealthReference(target_kind="systems", entry_key="safe-entry"),
            destination=f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/safe-character",
        ),
        classification="stale-version" if action == "inspect_source" else "missing",
        severity="attention" if action == "inspect_source" else "blocked",
        action=action,
        target=(
            SourceHealthTarget(
                target_kind="systems",
                canonical_identity="DND-5E:safe-entry",
                target_type="spell",
                destination=destination,
            )
            if action == "inspect_source"
            else None
        ),
        destination=destination,
    )


def _browser_state(campaign_slug: str = TEST_CAMPAIGN_SLUG) -> dict[str, object]:
    return {
        "adapters": [
            {
                "completed": [],
                "cursor": "",
                "exhausted": False,
                "held": False,
                "id": adapter_id,
                "page_count": 0,
                "page_digest": "",
            }
            for adapter_id in SOURCE_HEALTH_BROWSER_ADAPTER_ROSTER
        ],
        "campaign": campaign_slug,
        "outcome": {"saw_any_consumer": False, "saw_nonhealthy": False},
        "roster": list(SOURCE_HEALTH_BROWSER_ADAPTER_ROSTER),
        "version": 1,
        "window": None,
    }


def test_sh2_codec_is_distinct_canonical_bounded_and_campaign_state_round_trips():
    codec = SourceHealthBrowserCursorCodec(b"browser-source-health-test-key-material")
    state = {
        "adapters": [],
        "campaign": TEST_CAMPAIGN_SLUG,
        "padding": "x" * 5_700,
        "roster": [],
        "version": 1,
    }

    first = codec.encode(state)
    second = codec.encode(dict(reversed(tuple(state.items()))))

    assert first == second
    assert first.startswith("sh2.")
    assert len(first.encode("ascii")) <= SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES == 3_840
    assert codec.decode(first) == state

    with pytest.raises(SourceHealthCursorError):
        codec.decode(first.replace("sh2.", "sh1.", 1))
    with pytest.raises(SourceHealthCursorError):
        codec.decode(f"{first}x")
    with pytest.raises(SourceHealthCursorError):
        codec.encode({"padding": "x" * 6_001})


def test_sh2_browser_state_is_schema_roster_and_campaign_bound():
    codec = SourceHealthBrowserCursorCodec(b"browser-source-health-test-key-material")
    token = codec.encode(_browser_state())

    assert codec.decode_for_campaign(token, campaign_slug=TEST_CAMPAIGN_SLUG) == _browser_state()
    with pytest.raises(SourceHealthCursorError):
        codec.decode_for_campaign(token, campaign_slug="other-campaign")

    wrong_roster = _browser_state()
    wrong_roster["roster"] = ["characters", "combat", "mechanics"]
    with pytest.raises(SourceHealthCursorError):
        codec.decode_for_campaign(
            codec.encode(wrong_roster),
            campaign_slug=TEST_CAMPAIGN_SLUG,
        )

    wrong_schema = _browser_state()
    wrong_schema["unexpected"] = True
    with pytest.raises(SourceHealthCursorError):
        codec.decode_for_campaign(
            codec.encode(wrong_schema),
            campaign_slug=TEST_CAMPAIGN_SLUG,
        )


@pytest.mark.parametrize(
    ("action", "destination", "expected"),
    [
        ("inspect_consumer", f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/hero", True),
        ("inspect_consumer", f"/campaigns/{TEST_CAMPAIGN_SLUG}/combat/dm?combatant=12", True),
        ("inspect_source", f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/shield", True),
        ("manage_source_policy", f"/campaigns/{TEST_CAMPAIGN_SLUG}/dm-content?lane=systems", True),
        ("contact_app_admin", f"/campaigns/{TEST_CAMPAIGN_SLUG}/admin", False),
        ("inspect_source", "https://example.test/private", False),
        ("inspect_source", f"//example.test/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/x", False),
        ("inspect_source", f"/campaigns/other/systems/entries/x", False),
        ("inspect_source", f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/x#secret", False),
        ("inspect_source", f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/x?next=/private", False),
        ("inspect_source", f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems\\entries\\x", False),
    ],
)
def test_presenter_destination_allowlist_is_campaign_and_action_bound(action, destination, expected):
    result = source_health_action_destination(TEST_CAMPAIGN_SLUG, action, destination)
    assert bool(result) is expected


def test_presenter_maps_every_vocabulary_and_redacts_inaccessible_targets():
    actions = (
        "inspect_consumer",
        "inspect_consumer",
        "inspect_consumer",
        "inspect_consumer",
        "manage_source_policy",
        "none",
        "review_source",
        "inspect_source",
        "none",
        "contact_app_admin",
    )
    destinations = (
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/hero",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/pages/mechanics/nested-page",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/hero",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/hero",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/dm-content?lane=systems",
        "",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/review",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/stale",
        "",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/admin",
    )
    classifications = tuple(SOURCE_HEALTH_CLASSIFICATION_LABELS) + ("healthy",)
    findings = []
    for index, (classification, action, destination) in enumerate(
        zip(classifications, actions, destinations, strict=True)
    ):
        inaccessible = classification == "inaccessible"
        findings.append(
            SourceHealthFinding(
                consumer=SourceHealthConsumer(
                    consumer_type="character",
                    consumer_key=f"consumer-{index}",
                    surface="Character",
                    reference=SourceHealthReference("systems", entry_key=f"entry-{index}"),
                    destination=f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/hero",
                ),
                classification=classification,
                severity=(
                    "healthy"
                    if classification == "healthy"
                    else "attention"
                    if classification == "stale-version"
                    else "blocked"
                ),
                action=action,
                target=SourceHealthTarget(
                    target_kind="systems",
                    canonical_identity=(
                        "PRIVATE-INACCESSIBLE-IDENTITY"
                        if inaccessible
                        else f"DND-5E:entry-{index}"
                    ),
                    target_type="spell",
                    destination=destination,
                ),
                destination=destination,
            )
        )

    report = SourceHealthReport(
        campaign_slug=TEST_CAMPAIGN_SLUG,
        state="findings",
        findings=tuple(findings),
        message="Review these references.",
    )
    presented = present_source_health_report(report, campaign_slug=TEST_CAMPAIGN_SLUG)

    assert {item["classification_label"] for item in presented["findings"]} == set(
        SOURCE_HEALTH_CLASSIFICATION_LABELS.values()
    )
    assert {item["action_label"] for item in presented["findings"]} == set(
        SOURCE_HEALTH_ACTION_LABELS.values()
    )
    assert "PRIVATE-INACCESSIBLE-IDENTITY" not in str(presented)
    inaccessible = next(
        item for item in presented["findings"] if item["classification"] == "inaccessible"
    )
    assert inaccessible["target"] is None
    assert inaccessible["destination"] == ""
    contact = next(item for item in presented["findings"] if item["action"] == "contact_app_admin")
    assert contact["destination"] == ""


@pytest.mark.parametrize("state", tuple(SOURCE_HEALTH_STATE_LABELS))
def test_presenter_maps_every_report_state(state):
    finding = _finding(
        action="inspect_source",
        destination=f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/shield",
    )
    report = _report(
        state=state,
        findings=(finding,),
        continuations=(("sh2.safe.token",) if state == "partial" else ()),
    )

    presented = present_source_health_report(report, campaign_slug=TEST_CAMPAIGN_SLUG)

    assert presented["state_label"] == SOURCE_HEALTH_STATE_LABELS[state]
    if state == "error":
        assert presented["findings"] == ()
    if state == "report_stale":
        assert all(item["destination"] == "" for item in presented["findings"])
    assert bool(presented["next_continuation"]) is (state == "partial")


def test_browser_route_manager_authorization_precedes_service_and_honors_view_as(
    app, client, sign_in, users
):
    service = _ReportService(_report())
    app.extensions["source_health_service"] = service
    route = f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health"

    signed_out = client.get(route)
    assert signed_out.status_code == 302
    assert len(signed_out.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
    assert service.calls == []

    for actor in ("owner", "observer", "outsider"):
        _sign_in(sign_in, users, actor)
        denied = client.get(f"{route}?continuation=not-even-parsed")
        assert denied.status_code == 403
        assert len(denied.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
        assert service.calls == []

    _sign_in(sign_in, users, "admin")
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    denied_view_as = client.get(f"{route}?continuation=not-even-parsed")
    assert denied_view_as.status_code == 403
    assert len(denied_view_as.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
    assert service.calls == []

    _sign_in(sign_in, users, "dm")
    assert client.get(route).status_code == 200
    _sign_in(sign_in, users, "admin")
    assert client.get(route).status_code == 200
    assert service.calls == [(TEST_CAMPAIGN_SLUG, ""), (TEST_CAMPAIGN_SLUG, "")]


def test_composed_browser_service_runs_once_with_bounded_queries_and_zero_writes(
    app, client, sign_in, users, monkeypatch
):
    service = app.extensions["source_health_service"]
    assert isinstance(service, SourceHealthService)
    assert service._adapter_ids == SOURCE_HEALTH_BROWSER_ADAPTER_ROSTER
    captured: list[tuple[str, dict[str, float | int]]] = []
    statements: list[str] = []
    original_execute = db_module._InstrumentedConnection.execute

    def recording_execute(connection, sql, parameters=()):
        statements.append(" ".join(str(sql).split()))
        return original_execute(connection, sql, parameters)

    monkeypatch.setattr(db_module._InstrumentedConnection, "execute", recording_execute)

    @app.after_request
    def capture_source_health_metrics(response):
        if request.endpoint in {
            "campaign_source_health_view",
            "campaign_systems_control_panel_view",
        }:
            captured.append((str(request.endpoint), get_db_query_metrics()))
        return response

    _sign_in(sign_in, users, "dm")
    control_response = client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/control-panel"
    )
    app.extensions["source_health_service"] = _ReportService(_report())
    shell_response = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health")
    app.extensions["source_health_service"] = service
    statements.clear()
    response = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health")

    assert control_response.status_code == 200
    assert shell_response.status_code == 200
    assert response.status_code == 200
    assert [item[0] for item in captured] == [
        "campaign_systems_control_panel_view",
        "campaign_source_health_view",
        "campaign_source_health_view",
    ]
    actual_metrics = captured[-1][1]
    assert int(actual_metrics["query_count"]) <= 12, captured
    assert actual_metrics["write_count"] == 0
    assert actual_metrics["commit_count"] == 0
    assert actual_metrics["rollback_count"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "continuation=",
        "continuation=one&continuation=two",
        "unknown=value",
        "continuation=one&unknown=value",
        "continuation=%",
        "continuation=%FF",
    ],
)
def test_browser_query_grammar_errors_are_sanitized_and_skip_inventory(
    app, client, sign_in, users, query
):
    service = _ReportService(_report())
    app.extensions["source_health_service"] = service
    _sign_in(sign_in, users, "dm")

    response = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health?{query}")

    assert response.status_code == 400
    assert service.calls == []
    assert b"Source Health could not complete" in response.data
    assert b"not-even-parsed" not in response.data
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert len(response.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES


def test_browser_page_uses_native_links_headers_nav_and_stale_action_suppression(
    app, client, sign_in, users
):
    destination = f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems/entries/shield"
    finding = _finding(action="inspect_source", destination=destination)
    service = _ReportService(
        _report(state="partial", findings=(finding,), continuations=("sh2.safe.token",))
    )
    app.extensions["source_health_service"] = service
    _sign_in(sign_in, users, "dm")

    response = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert '<h1>Source Health</h1>' in body
    assert 'aria-current="page"' in body
    assert "DM Content" in body and body.index("DM Content") < body.index("Source Health") < body.index("Control")
    assert f'href="{destination}"' in body
    assert "Next page" in body
    assert "Retry" in body
    main_markup = body[body.index("<main") : body.index("</main>")]
    assert "<script" not in main_markup
    assert len(response.data) <= SOURCE_HEALTH_SUCCESS_BODY_MAX_BYTES

    service.report = _report(state="report_stale", findings=(finding,))
    stale = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health")
    stale_body = stale.get_data(as_text=True)
    assert destination not in stale_body
    assert "Next page" not in stale_body
    assert "Retry" in stale_body


def test_browser_response_classes_use_frozen_raw_body_ceilings(
    app, client, sign_in, users
):
    route = f"/campaigns/{TEST_CAMPAIGN_SLUG}/source-health"
    _sign_in(sign_in, users, "dm")

    app_codec = app.extensions["source_health_service"]._cursor_codec
    valid_token = app_codec.encode(_browser_state())
    tampered_token = f"{valid_token[:-1]}{'A' if valid_token[-1] != 'A' else 'B'}"
    service = _ReportService(_report(state="error"))
    app.extensions["source_health_service"] = service
    report_error = client.get(route)
    assert report_error.status_code == 200
    assert len(report_error.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES

    malformed = client.get(f"{route}?continuation=sh2.bad.bad")
    assert malformed.status_code == 400
    assert len(malformed.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
    assert service.calls == [(TEST_CAMPAIGN_SLUG, "")]

    tampered = client.get(f"{route}?continuation={tampered_token}")
    assert tampered.status_code == 400
    assert len(tampered.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
    assert service.calls == [(TEST_CAMPAIGN_SLUG, "")]

    too_long_target = client.get(f"{route}?continuation={'a' * 4_096}")
    assert too_long_target.status_code == 400
    assert len(too_long_target.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
    assert service.calls == [(TEST_CAMPAIGN_SLUG, "")]

    missing = client.get("/campaigns/no-such-campaign/source-health")
    assert missing.status_code == 404
    assert len(missing.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES

    head = client.head(route)
    assert head.status_code == 200
    assert len(head.get_data()) == 0
    assert head.headers["Cache-Control"] == "private, no-store"
    assert head.headers["Referrer-Policy"] == "no-referrer"

    options = client.open(route, method="OPTIONS")
    assert options.status_code == 200
    assert len(options.get_data()) <= SOURCE_HEALTH_ERROR_BODY_MAX_BYTES
    assert options.headers["Cache-Control"] == "private, no-store"
    assert options.headers["Referrer-Policy"] == "no-referrer"
