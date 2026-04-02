from __future__ import annotations

from scripts.measure_live_latency import (
    build_checklist_evaluation,
    build_pressure_projection,
    parse_server_timing,
    percentile,
    summarize_samples,
)


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
