from __future__ import annotations

import json
import logging

import pytest


def test_health_endpoint_reports_app_and_data_metadata(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["app"]["version"] == "test-version"
    assert payload["app"]["build_id"] == "test-build"
    assert payload["app"]["git_sha"] == "test-git-sha"
    assert payload["app"]["git_dirty"] is False
    assert payload["app"]["runtime"] == "test-runtime"
    assert payload["app"]["instance_name"] == "test-instance"
    assert payload["data"]["campaigns_dir"].endswith("campaigns")
    assert payload["data"]["db_path"].endswith("player_wiki.sqlite3")


def test_sign_in_page_shows_version_footer(client):
    response = client.get("/sign-in")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "vtest-version" in html
    assert "Build test-build" in html
    assert "test-runtime" in html
    assert "test-instance" in html


def test_api_app_endpoint_reports_metadata(client):
    response = client.get("/api/v1/app")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {
        "ok": True,
        "app": {
            "version": "test-version",
            "build_id": "test-build",
            "git_sha": "test-git-sha",
            "git_dirty": False,
            "runtime": "test-runtime",
            "instance_name": "test-instance",
            "environment": "development",
            "base_url": "http://127.0.0.1:5000",
            "db_path": str(client.application.config["DB_PATH"]),
            "campaigns_dir": str(client.application.config["CAMPAIGNS_DIR"]),
        },
    }


def test_request_trail_logs_start_for_campaign_route_when_enabled(app, client, caplog):
    app.config.update(
        REQUEST_TRAIL_ENABLED=True,
        REQUEST_SLOW_LOG_THRESHOLD_MS=0.0,
    )
    caplog.set_level(logging.INFO)

    response = client.get("/campaigns/linden-pass")

    assert response.status_code == 200

    start_records = [
        record
        for record in caplog.records
        if record.message.startswith("request_trail_start ")
    ]
    assert start_records

    payload = json.loads(start_records[-1].message.split(" ", 1)[1])
    assert payload["method"] == "GET"
    assert payload["path"] == "/campaigns/linden-pass"
    assert payload["endpoint"] == "campaign_view"
    assert payload["request_id"]
    assert payload["query_count"] >= 0
    assert payload["write_count"] >= 0
    assert payload["write_time_ms"] >= 0.0
    assert payload["commit_count"] >= 0
    assert payload["commit_time_ms"] >= 0.0
    assert payload["rollback_count"] >= 0
    assert payload["rollback_time_ms"] >= 0.0


@pytest.mark.parametrize(
    ("request_path", "expected_path", "secret_markers"),
    (
        (
            "/invite/encoded-slash-secret%2Fencoded-tail-secret",
            "/invite/[REDACTED]",
            ("encoded-slash-secret", "encoded-tail-secret"),
        ),
        (
            "/reset//double-slash-secret",
            "/reset/[REDACTED]",
            ("double-slash-secret",),
        ),
        (
            "/invite/trailing-secret/extra-secret/",
            "/invite/[REDACTED]",
            ("trailing-secret", "extra-secret"),
        ),
        (
            "/RESET/uppercase-prefix-secret",
            "/reset/[REDACTED]",
            ("uppercase-prefix-secret",),
        ),
        (
            "/invite%5Cliteral-separator-secret",
            "/invite/[REDACTED]",
            ("literal-separator-secret",),
        ),
        (
            "/reset%2Fencoded-prefix-secret",
            "/reset/[REDACTED]",
            ("encoded-prefix-secret",),
        ),
    ),
)
def test_request_trail_omits_query_values_and_redacts_one_time_path_tokens(
    app,
    client,
    caplog,
    request_path,
    expected_path,
    secret_markers,
):
    app.config.update(
        REQUEST_TRAIL_ENABLED=True,
        REQUEST_SLOW_LOG_THRESHOLD_MS=0.000001,
    )
    caplog.set_level(logging.INFO)

    response = client.get(
        f"{request_path}?access_token=query-token-secret&password=query-password-secret"
    )

    assert response.status_code < 500
    diagnostic_records = [
        record
        for record in caplog.records
        if record.message.startswith(
            (
                "request_trail_start ",
                "slow_request ",
                "request_exception ",
                "live_response ",
                "slow_live_response ",
            )
        )
    ]
    assert diagnostic_records
    start_record = next(
        record
        for record in diagnostic_records
        if record.message.startswith("request_trail_start ")
    )
    payload = json.loads(start_record.message.split(" ", 1)[1])
    assert payload["method"] == "GET"
    assert payload["path"] == expected_path
    assert payload["request_id"]
    for record in diagnostic_records:
        for marker in (
            *secret_markers,
            "query-token-secret",
            "query-password-secret",
        ):
            assert marker not in record.message


def test_request_trail_exception_metadata_omits_exception_text(app, client, caplog):
    exception_secret = "user-supplied-exception-secret"

    @app.get("/_test/request-trail-exception")
    def request_trail_exception_probe():
        raise RuntimeError(exception_secret)

    app.config.update(
        REQUEST_TRAIL_ENABLED=True,
        REQUEST_SLOW_LOG_THRESHOLD_MS=0.0,
    )
    caplog.set_level(logging.ERROR)

    with pytest.raises(RuntimeError, match=exception_secret):
        client.get("/_test/request-trail-exception?secret=query-exception-secret")

    exception_record = next(
        record
        for record in reversed(caplog.records)
        if record.message.startswith("request_exception ")
    )
    payload = json.loads(exception_record.message.split(" ", 1)[1])
    assert payload["path"] == "/_test/request-trail-exception"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["request_id"]
    assert "exception" not in payload
    assert exception_secret not in exception_record.message
    assert "query-exception-secret" not in exception_record.message


def test_live_response_diagnostics_omit_query_values(
    app,
    client,
    sign_in,
    users,
    caplog,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config.update(LIVE_DIAGNOSTICS=True)
    caplog.set_level(logging.INFO)

    response = client.get(
        "/campaigns/linden-pass/combat/live-state?access_token=live-query-secret",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    live_record = next(
        record
        for record in reversed(caplog.records)
        if record.message.startswith("live_response ")
    )
    payload = json.loads(live_record.message.split(" ", 1)[1])
    assert payload["path"] == "/campaigns/linden-pass/combat/live-state"
    assert "live-query-secret" not in live_record.message


def test_request_trail_skips_healthz_when_enabled(app, client, caplog):
    app.config.update(
        REQUEST_TRAIL_ENABLED=True,
        REQUEST_SLOW_LOG_THRESHOLD_MS=0.0,
    )
    caplog.set_level(logging.INFO)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert not [
        record
        for record in caplog.records
        if record.message.startswith("request_trail_start ")
    ]


def test_request_trail_logs_slow_request_warning(app, client, caplog):
    app.config.update(
        REQUEST_TRAIL_ENABLED=True,
        REQUEST_SLOW_LOG_THRESHOLD_MS=0.01,
    )
    caplog.set_level(logging.WARNING)

    response = client.get("/campaigns/linden-pass")

    assert response.status_code == 200

    slow_records = [
        record
        for record in caplog.records
        if record.message.startswith("slow_request ")
    ]
    assert slow_records

    payload = json.loads(slow_records[-1].message.split(" ", 1)[1])
    assert payload["method"] == "GET"
    assert payload["path"] == "/campaigns/linden-pass"
    assert payload["endpoint"] == "campaign_view"
    assert payload["status_code"] == 200
    assert payload["request_time_ms"] >= 0.01
    assert "rollback_count" in payload
