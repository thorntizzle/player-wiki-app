from __future__ import annotations

import json
import logging
from pathlib import Path
import sqlite3
import time

import pytest

from player_wiki import runtime_health
from player_wiki.db import init_database
from player_wiki.migrations import MIGRATIONS


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
    assert set(payload) == {
        "status",
        "environment",
        "campaign_count",
        "app",
        "data",
        "repository",
    }


def _path_state(path: Path) -> tuple[object, ...] | None:
    try:
        stat = path.stat()
        if path.is_dir():
            return "directory", stat.st_mtime_ns
        return "file", stat.st_mtime_ns, stat.st_size, path.read_bytes()
    except FileNotFoundError:
        return None


def _database_state(path: Path) -> dict[str, tuple[object, ...] | None]:
    return {
        suffix: _path_state(Path(f"{path}{suffix}"))
        for suffix in ("", "-wal", "-shm")
    }


def _application_database_fingerprint(path: Path) -> tuple[object, ...]:
    with sqlite3.connect(path) as connection:
        schema = tuple(
            connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall()
        )
        ledger = tuple(
            connection.execute(
                "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
        users = tuple(connection.execute("SELECT * FROM users ORDER BY id").fetchall())
    return schema, ledger, users


def test_livez_is_exact_and_never_touches_configured_dependencies(app, client, monkeypatch, tmp_path):
    missing_database = tmp_path / "poison-db-secret" / "wiki.sqlite3"
    missing_campaigns = tmp_path / "poison-campaign-secret" / "campaigns"
    app.config.update(DB_PATH=missing_database, CAMPAIGNS_DIR=missing_campaigns)
    repository_store = app.extensions["repository_store"]
    monkeypatch.setattr(
        repository_store,
        "get",
        lambda: pytest.fail("liveness accessed the repository"),
    )
    monkeypatch.setattr(
        repository_store,
        "status",
        lambda: pytest.fail("liveness accessed repository status"),
    )

    response = client.get("/livez")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert not missing_database.parent.exists()
    assert not missing_campaigns.exists()


def test_readyz_reports_current_dependencies_without_mutating_database(app, client):
    database_path = Path(app.config["DB_PATH"])
    before_fingerprint = _application_database_fingerprint(database_path)
    before_database = database_path.read_bytes()
    before_lock = _path_state(Path(f"{database_path}.migration.lock"))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "ok"},
            "migrations": {"status": "ok"},
            "campaigns": {"status": "ok"},
        },
    }
    assert _application_database_fingerprint(database_path) == before_fingerprint
    assert database_path.read_bytes() == before_database
    assert _path_state(Path(f"{database_path}.migration.lock")) == before_lock
    assert not (database_path.parent / "migration-backups").exists()


@pytest.mark.parametrize(
    ("database_kind", "expected_reason"),
    (
        ("missing", "database_missing"),
        ("directory", "database_not_file"),
        ("empty", "migration_ledger_missing"),
        ("malformed", "database_unavailable"),
    ),
)
def test_readyz_database_failures_are_safe_and_nonmutating(
    app,
    client,
    tmp_path,
    database_kind,
    expected_reason,
):
    database_path = tmp_path / "dependency-secret" / "wiki.sqlite3"
    database_path.parent.mkdir()
    if database_kind == "directory":
        database_path.mkdir()
    elif database_kind == "empty":
        with sqlite3.connect(database_path):
            pass
    elif database_kind == "malformed":
        database_path.write_bytes(b"not a sqlite database dependency-secret")
    before = _database_state(database_path)
    before_lock = _path_state(Path(f"{database_path}.migration.lock"))
    app.config["DB_PATH"] = database_path

    response = client.get("/readyz")

    payload = response.get_json()
    assert response.status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["reason"] == expected_reason
    assert "dependency-secret" not in response.get_data(as_text=True)
    assert _database_state(database_path) == before
    assert _path_state(Path(f"{database_path}.migration.lock")) == before_lock
    assert not (database_path.parent / "migration-backups").exists()


@pytest.mark.parametrize("ledger_case", ("shape", "future", "name", "checksum", "gap"))
def test_readyz_rejects_invalid_ledgers_with_one_stable_safe_reason(
    app,
    client,
    tmp_path,
    ledger_case,
):
    database_path = tmp_path / f"ledger-secret-{ledger_case}.sqlite3"
    init_database(database_path)
    with sqlite3.connect(database_path) as connection:
        if ledger_case == "shape":
            connection.execute("DROP TABLE schema_migrations")
            connection.execute("CREATE TABLE schema_migrations (version INTEGER)")
        else:
            connection.execute("DELETE FROM schema_migrations")
            if ledger_case == "future":
                rows = [
                    (1, MIGRATIONS[0].name, MIGRATIONS[0].checksum, "before"),
                    (2, "0002_future", "a" * 64, "before"),
                ]
            elif ledger_case == "gap":
                rows = [(2, "0002_gap", "a" * 64, "before")]
            elif ledger_case == "name":
                rows = [(1, "0001_wrong", MIGRATIONS[0].checksum, "before")]
            else:
                rows = [(1, MIGRATIONS[0].name, "b" * 64, "before")]
            connection.executemany(
                "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                rows,
            )
    before = _database_state(database_path)
    before_lock = _path_state(Path(f"{database_path}.migration.lock"))
    app.config["DB_PATH"] = database_path

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["reason"] == "migration_ledger_invalid"
    assert f"ledger-secret-{ledger_case}" not in response.get_data(as_text=True)
    assert _database_state(database_path) == before
    assert _path_state(Path(f"{database_path}.migration.lock")) == before_lock


def test_readyz_reports_an_existing_empty_ledger_as_outdated(app, client, tmp_path):
    database_path = tmp_path / "outdated.sqlite3"
    init_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM schema_migrations")
    app.config["DB_PATH"] = database_path

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["reason"] == "migration_ledger_outdated"


def test_readyz_reads_live_wal_state_instead_of_an_immutable_main_file(app, client, tmp_path):
    database_path = tmp_path / "live-wal.sqlite3"
    init_database(database_path)
    writer = sqlite3.connect(database_path)
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = 1",
            ("b" * 64,),
        )
        writer.commit()
        wal_path = Path(f"{database_path}-wal")
        assert wal_path.stat().st_size > 0
        before_main = database_path.read_bytes()
        before_wal = wal_path.read_bytes()
        app.config["DB_PATH"] = database_path

        response = client.get("/readyz")

        assert response.status_code == 503
        assert response.get_json()["reason"] == "migration_ledger_invalid"
        assert database_path.read_bytes() == before_main
        assert wal_path.read_bytes() == before_wal
    finally:
        writer.close()


@pytest.mark.parametrize("campaigns_kind", ("missing", "file"))
def test_readyz_rejects_missing_or_non_directory_campaigns_without_creating_them(
    app,
    client,
    tmp_path,
    campaigns_kind,
):
    campaigns_path = tmp_path / "campaigns-path-secret"
    if campaigns_kind == "file":
        campaigns_path.write_text("private-content-secret", encoding="utf-8")
    app.config["CAMPAIGNS_DIR"] = campaigns_path

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["reason"] == (
        "campaigns_missing" if campaigns_kind == "missing" else "campaigns_not_directory"
    )
    assert "campaigns-path-secret" not in response.get_data(as_text=True)
    if campaigns_kind == "missing":
        assert not campaigns_path.exists()
    else:
        assert campaigns_path.read_text(encoding="utf-8") == "private-content-secret"


def test_readyz_reports_unreadable_campaigns_without_exception_details(
    app,
    client,
    monkeypatch,
):
    campaigns_path = Path(app.config["CAMPAIGNS_DIR"])

    def deny_scan(path):
        assert Path(path) == campaigns_path
        raise PermissionError("campaign-content-secret")

    monkeypatch.setattr(runtime_health.os, "scandir", deny_scan)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["reason"] == "campaigns_unreadable"
    assert "campaign-content-secret" not in response.get_data(as_text=True)


def test_readyz_fails_closed_quickly_when_database_is_exclusively_locked(app, client, tmp_path):
    database_path = tmp_path / "locked.sqlite3"
    init_database(database_path)
    lock_connection = sqlite3.connect(database_path, timeout=0)
    lock_connection.execute("BEGIN EXCLUSIVE")
    app.config["DB_PATH"] = database_path
    try:
        started_at = time.monotonic()
        response = client.get("/readyz")
        elapsed_seconds = time.monotonic() - started_at
    finally:
        lock_connection.rollback()
        lock_connection.close()

    assert response.status_code == 503
    assert response.get_json()["reason"] == "database_unavailable"
    assert elapsed_seconds < 1.0


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


@pytest.mark.parametrize("probe_path", ("/healthz", "/livez", "/readyz"))
def test_request_trail_skips_health_probes_when_enabled(app, client, caplog, probe_path):
    app.config.update(
        REQUEST_TRAIL_ENABLED=True,
        REQUEST_SLOW_LOG_THRESHOLD_MS=0.0,
    )
    caplog.set_level(logging.INFO)

    response = client.get(probe_path)

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
