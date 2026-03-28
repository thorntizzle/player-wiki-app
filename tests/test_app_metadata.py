from __future__ import annotations


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
