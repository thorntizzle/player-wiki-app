from __future__ import annotations

import json
import logging


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
