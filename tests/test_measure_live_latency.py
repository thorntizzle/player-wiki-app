from __future__ import annotations

import threading

from scripts.measure_live_latency import (
    assert_combat_status_compatibility_redirect,
    build_checklist_evaluation,
    build_pressure_projection,
    build_surface_path,
    collect_measurements,
    DEFAULT_SAMPLE_COUNTS,
    parse_server_timing,
    percentile,
    render_markdown_report,
    SURFACE_SPECS,
    summarize_samples,
)


def test_surface_specs_cover_dm_combat_livestream_views():
    spec_by_name = {spec.name: spec for spec in SURFACE_SPECS}

    assert "combat_dm_status" in spec_by_name
    assert spec_by_name["combat_dm_status"].page_path_template == "/campaigns/{campaign}/combat/dm"
    assert spec_by_name["combat_dm_status"].root_selector == "[data-combat-live-root]"
    assert spec_by_name["combat_dm_status"].metric_view == "combat"

    assert "combat_dm_controls" in spec_by_name
    assert spec_by_name["combat_dm_controls"].page_path_template == "/campaigns/{campaign}/combat/dm?view=controls"
    assert spec_by_name["combat_dm_controls"].root_selector == "[data-combat-live-root]"
    assert spec_by_name["combat_dm_controls"].metric_view == "combat"


def test_surface_specs_use_exact_sequential_player_and_manager_inventory():
    assert [(spec.name, spec.actor) for spec in SURFACE_SPECS] == [
        ("session", "player"),
        ("combat", "player"),
        ("combat_character", "player"),
        ("session_dm", "manager"),
        ("combat_dm_status", "manager"),
        ("combat_dm_controls", "manager"),
    ]
    spec_by_name = {spec.name: spec for spec in SURFACE_SPECS}
    assert spec_by_name["session_dm"].page_path_template == "/campaigns/{campaign}/session/dm?dm_view=tools"
    assert spec_by_name["session_dm"].metric_view == "session-dm"
    assert spec_by_name["session_dm"].root_selector == (
        '[data-session-live-root][data-session-live-view="dm"]'
    )
    assert spec_by_name["session"].root_selector == (
        '[data-session-live-root][data-session-live-view="session"]'
    )
    assert spec_by_name["combat_character"].required is True
    assert "combat_status" not in spec_by_name
    assert all(spec.root_selector != "[data-combat-status-live-root]" for spec in SURFACE_SPECS)


def test_build_surface_path_keeps_dm_controls_query():
    spec = next(spec for spec in SURFACE_SPECS if spec.name == "combat_dm_controls")

    assert build_surface_path(spec, "campaign-1") == "/campaigns/campaign-1/combat/dm?view=controls"


def test_build_surface_path_targets_valid_compatibility_character_slug():
    spec = next(spec for spec in SURFACE_SPECS if spec.name == "combat_character")

    assert build_surface_path(spec, "campaign-1", "arden-march") == (
        "/campaigns/campaign-1/combat/character?character=arden-march"
    )


def test_compatibility_status_is_asserted_as_redirect_not_sampled_surface():
    class Response:
        status = 302
        headers = {"location": "/campaigns/campaign-1/combat/dm?combatant=7"}

    class Request:
        def get(self, url, max_redirects):
            assert url == "http://localhost:5000/campaigns/campaign-1/combat/status"
            assert max_redirects == 0
            return Response()

    class Context:
        request = Request()

    result = assert_combat_status_compatibility_redirect(
        Context(),
        "http://localhost:5000",
        "campaign-1",
    )

    assert result == {
        "path": "/campaigns/campaign-1/combat/status",
        "status": 302,
        "location": "/campaigns/campaign-1/combat/dm?combatant=7",
    }


def test_parse_server_timing_extracts_named_durations():
    header = "state-check;dur=0.42, db;dur=1.25, render;dur=3.50, total;dur=5.40"

    parsed = parse_server_timing(header)

    assert parsed == {
        "state-check": 0.42,
        "db": 1.25,
        "render": 3.5,
        "total": 5.4,
    }


def test_percentile_interpolates_for_p50_and_p95():
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0.50) == 25.0
    assert percentile(values, 0.95) == 38.5


def test_summarize_samples_aggregates_latency_payload_and_server_timing():
    samples = [
        {
            "requestMs": 12.0,
            "applyMs": 2.0,
            "payloadBytes": 100.0,
            "queryCount": 3.0,
            "queryTimeMs": 1.2,
            "requestTimeMs": 5.0,
            "serverTimingParsed": {"state-check": 0.3, "db": 1.2, "render": 2.2, "total": 5.0},
            "changed": False,
        },
        {
            "requestMs": 20.0,
            "applyMs": 4.0,
            "payloadBytes": 140.0,
            "queryCount": 5.0,
            "queryTimeMs": 2.8,
            "requestTimeMs": 7.0,
            "serverTimingParsed": {"state-check": 0.5, "db": 2.8, "render": 3.0, "total": 7.0},
            "changed": True,
        },
    ]

    summary = summarize_samples(samples)

    assert summary["sample_count"] == 2
    assert summary["changed_count"] == 1
    assert summary["changed_ratio"] == 0.5
    assert summary["request_ms"]["p50"] == 16.0
    assert summary["request_ms"]["p95"] == 19.6
    assert summary["payload_bytes"]["mean"] == 120.0
    assert summary["db_ms"]["p50"] == 2.0
    assert summary["total_ms"]["p95"] == 6.9


def test_build_pressure_projection_uses_unchanged_steady_samples_when_available():
    scenarios = {
        "cold": {
            "summary": {
                "payload_bytes": {"mean": 1000.0},
                "request_time_ms": {"mean": 20.0},
            }
        },
        "steady": {
            "samples": [
                {
                    "changed": False,
                    "payloadBytes": 100.0,
                    "requestMs": 8.0,
                    "applyMs": 0.0,
                    "queryCount": 1.0,
                    "queryTimeMs": 0.8,
                    "requestTimeMs": 4.0,
                    "serverTimingParsed": {"state-check": 0.2, "db": 0.8, "render": 0.0, "total": 4.0},
                },
                {
                    "changed": True,
                    "payloadBytes": 900.0,
                    "requestMs": 18.0,
                    "applyMs": 3.0,
                    "queryCount": 5.0,
                    "queryTimeMs": 3.0,
                    "requestTimeMs": 12.0,
                    "serverTimingParsed": {"state-check": 0.5, "db": 3.0, "render": 5.0, "total": 12.0},
                },
            ]
        },
    }
    dataset = {"liveActiveIntervalMs": "1000", "liveIdleIntervalMs": "3000"}

    projection = build_pressure_projection("combat", dataset, scenarios)

    assert projection["legacy"]["requests_per_minute"] == 60.0
    assert projection["current_active"]["payload_bytes_per_minute"] == 6000.0
    assert projection["current_active"]["server_ms_per_minute"] == 240.0
    assert projection["current_idle"]["requests_per_minute"] == 20.0


def test_build_checklist_evaluation_marks_pressure_reduction_passes():
    surface_reports = {
        "combat": {
            "scenarios": {
                "cold": {
                    "summary": {
                        "payload_bytes": {"mean": 1000.0},
                        "request_time_ms": {"mean": 20.0},
                    }
                },
                "steady": {
                    "summary": {
                        "payload_bytes": {"mean": 100.0},
                        "render_ms": {"p95": 0.0},
                    }
                },
            },
            "pressure_projection": {
                "legacy": {
                    "payload_bytes_per_minute": 60000.0,
                    "server_ms_per_minute": 1200.0,
                },
                "current_active": {
                    "payload_bytes_per_minute": 6000.0,
                    "server_ms_per_minute": 240.0,
                },
                "current_idle": {
                    "payload_bytes_per_minute": 2000.0,
                    "server_ms_per_minute": 80.0,
                },
            },
        }
    }

    evaluation = build_checklist_evaluation(surface_reports)

    assert evaluation["combat"]["payload_reduction_pass"] is True
    assert evaluation["combat"]["steady_render_pass"] is True
    assert evaluation["combat"]["idle_payload_pass"] is True
    assert evaluation["combat"]["idle_server_pass"] is True
    assert evaluation["combat"]["active_payload_pass"] is True
    assert evaluation["combat"]["active_server_pass"] is True


def test_render_markdown_report_includes_dm_surfaces_for_timing_summary():
    sample = {
        "requestMs": 12.0,
        "applyMs": 2.0,
        "payloadBytes": 150.0,
        "queryCount": 3.0,
        "queryTimeMs": 1.0,
        "requestTimeMs": 4.0,
        "serverTimingParsed": {"state-check": 0.2, "db": 0.9, "render": 0.8, "total": 4.0},
        "changed": False,
    }
    summary = summarize_samples([sample])
    report = {
        "base_url": "http://localhost:5000",
        "campaign": "campaign-1",
        "mode": "local",
        "run_started_at": "2026-05-15T00:00:00+00:00",
        "surfaces": {
            "combat_dm_status": {
                "scenarios": {
                    "cold": {"samples": [sample], "summary": summary},
                },
                "pressure_projection": {},
            },
            "combat_dm_controls": {
                "scenarios": {
                    "cold": {"samples": [sample], "summary": summary},
                },
                "pressure_projection": {},
            },
        },
        "checklist_evaluation": {},
        "notes": [],
    }

    markdown = render_markdown_report(report)

    assert "combat_dm_status" in markdown
    assert "combat_dm_controls" in markdown
    assert "| Scenario |" in markdown


def test_collect_measurements_uses_sanitized_sequential_player_and_manager_surfaces(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    try:
        import playwright.sync_api  # noqa: F401
    except Exception as exc:
        import pytest

        pytest.skip(f"Playwright unavailable: {exc}")

    from werkzeug.serving import make_server

    app.config["LIVE_DIAGNOSTICS"] = True
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    ).status_code == 302
    monkeypatch.setitem(
        DEFAULT_SAMPLE_COUNTS,
        "local",
        {"warmup": 0, "cold": 1, "steady": 1, "cold_apply": 1, "preview": 1},
    )

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        report = collect_measurements(
            base_url,
            "linden-pass",
            "local",
            manager_email=users["dm"]["email"],
            manager_password=users["dm"]["password"],
            player_email=users["owner"]["email"],
            player_password=users["owner"]["password"],
            combat_character_slug="arden-march",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert list(report["surfaces"]) == [
        "session",
        "combat",
        "combat_character",
        "session_dm",
        "combat_dm_status",
        "combat_dm_controls",
    ]
    assert report["compatibility_redirect"]["status"] == 302
    assert "view=status" not in report["compatibility_redirect"]["location"]
    for surface_name, surface in report["surfaces"].items():
        assert surface["actor"] == ("player" if surface_name in {"session", "combat", "combat_character"} else "manager")
        assert surface["dataset"]["liveActiveIntervalMs"] in {"500", "2000", "3000"}
        for scenario_name in ("cold", "steady", "cold_apply"):
            assert surface["scenarios"][scenario_name]["summary"]["sample_count"] == 1
        assert surface["scenarios"]["steady"]["summary"]["apply_ms"]["mean"] == 0.0
        assert surface["scenarios"]["cold"]["summary"]["payload_bytes"]["mean"] > 0
        assert surface["scenarios"]["cold_apply"]["summary"]["changed_count"] == 1
