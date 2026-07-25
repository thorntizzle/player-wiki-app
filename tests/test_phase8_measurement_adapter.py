from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

from tests.helpers.phase8_measurement_adapter import (
    ADAPTER_SCHEMA,
    ContractError,
    IMPORTED_PHASE7_EVIDENCE,
    LOCK_SHA256,
    PHASE4_IDENTITY,
    PHASE8_HARNESS_BLOB,
    SAMPLE_COUNTS,
    SURFACES,
    build_candidate_artifact,
    collect_candidate,
    evaluate_pair,
    main,
    parse_server_timing,
)


def _manifest(candidate: str) -> dict[str, object]:
    identity = (
        PHASE4_IDENTITY
        if candidate == "phase4"
        else {
            "commit": "7c7d8da54f1a33e754a487f0a374fe3c41e87a31",
            "tree": "41b240d4ca66b941b5e4f447478af5a5f1518ce8",
            "harness_blob": PHASE8_HARNESS_BLOB,
        }
    )
    return {
        "adapter_schema": ADAPTER_SCHEMA,
        "candidate": {"name": candidate, **identity},
        "fixture_sha256": "a" * 64,
        "local_settings_sha256": "b" * 64,
        "diagnostics_sha256": "c" * 64,
        "schema_sha256": "d" * 64,
        "runtime": {"python": "3.12.12", "development_lock_sha256": LOCK_SHA256},
        "combat_character": {"slug": "arden-march", "assigned": True},
        "actors": {
            "player": {"present": True, "principal": "player-fixture"},
            "manager": {"present": True, "principal": "manager-fixture"},
        },
        "surface_manifest": [surface.__dict__ for surface in SURFACES],
        "console_error_allowlist": [r"^known diagnostics noise$"],
    }


def _sample(*, changed: bool, request: float = 10.0, db: float = 2.0, render: float = 0.0, apply: float = 0.0, payload: float = 100.0) -> dict[str, object]:
    return {
        "requestMs": request,
        "applyMs": apply,
        "payloadBytes": payload,
        "requestTimeMs": request / 2,
        "serverTiming": f"state-check;dur=0.25, db;dur={db:.2f}, render;dur={render:.2f}, total;dur={request / 2:.2f}",
        "changed": changed,
        "phase_specific_raw_key": "preserved without normalization",
    }


def _raw() -> dict[str, object]:
    surfaces: dict[str, object] = {}
    for surface in SURFACES:
        surfaces[surface.name] = {
            "dataset": {"liveActiveIntervalMs": "500", "liveIdleIntervalMs": "2000"},
            "scenarios": {
                "warmup": [_sample(changed=False)],
                "cold": [_sample(changed=True, request=10, db=2, render=1, apply=2, payload=1000) for _ in range(8)],
                "steady": [_sample(changed=False, request=1, db=0.2, render=0, apply=0, payload=100) for _ in range(12)],
                "forced_apply": [_sample(changed=True, request=10, db=2, render=1, apply=2, payload=1000) for _ in range(6)],
            },
            "errors": [],
        }
    return {"surfaces": surfaces}


def _artifact(candidate: str) -> dict[str, object]:
    return build_candidate_artifact(_manifest(candidate), _raw())


def _phase4_measurement_module() -> types.ModuleType:
    result = subprocess.run(
        ["git", "show", "b80af7c7b441bb2fcecc763bf6ea4a73f9d85365:scripts/measure_live_latency.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    module = types.ModuleType("phase4_measure_live_latency_characterization")
    sys.modules[module.__name__] = module
    exec(compile(result.stdout, "phase4_measure_live_latency.py", "exec"), module.__dict__)
    return module


class _FakeResponse:
    status = 200


class _FakeLocator:
    def __init__(self, page: "_FakePage"):
        self.page = page

    def fill(self, value: str) -> None:
        self.page.filled.append(value)

    def click(self) -> None:
        self.page.clicked += 1
        self.page.url = "http://127.0.0.1:5000/campaign-picker"

    def evaluate(self, _script: str) -> dict[str, str]:
        return {"liveDiagnosticsEnabled": "1", "liveActiveIntervalMs": "500", "liveIdleIntervalMs": "2000"}


class _FakePage:
    def __init__(self):
        self.url = ""
        self.events: dict[str, object] = {}
        self.filled: list[str] = []
        self.clicked = 0
        self.sampler_calls: list[dict[str, object]] = []

    def on(self, name: str, callback: object) -> None:
        self.events[name] = callback

    def goto(self, url: str, **_kwargs: object) -> _FakeResponse:
        self.url = url
        return _FakeResponse()

    def locator(self, _selector: str) -> _FakeLocator:
        return _FakeLocator(self)

    def wait_for_load_state(self, _state: str) -> None:
        return None

    def wait_for_selector(self, _selector: str, **_kwargs: object) -> None:
        return None

    def wait_for_function(self, _script: str, **_kwargs: object) -> None:
        return None

    def evaluate(self, _script: str, arguments: dict[str, object]) -> dict[str, object]:
        self.sampler_calls.append(arguments)
        return _sample(changed=bool(arguments["forceApply"]), render=1 if arguments["forceApply"] else 0)


def test_protocol_is_source_proven_for_all_five_surfaces_and_immutable_evidence():
    assert PHASE4_IDENTITY == {
        "commit": "b80af7c7b441bb2fcecc763bf6ea4a73f9d85365",
        "tree": "30dc769f0f8d40b1f89307459cf2700541815c02",
        "harness_blob": "09340d98d72f99397c825489ea205b41dd6b3bba",
    }
    assert PHASE8_HARNESS_BLOB == "1d79c678a2c1f06a172eda9f6269c31517c36cec"
    assert SAMPLE_COUNTS == {"warmup": 1, "cold": 8, "steady": 12, "forced_apply": 6}
    assert [(surface.name, surface.actor) for surface in SURFACES] == [
        ("player_session", "player"),
        ("player_combat", "player"),
        ("dm_session_tools", "manager"),
        ("dm_combat_status", "manager"),
        ("dm_combat_controls", "manager"),
    ]
    assert IMPORTED_PHASE7_EVIDENCE["lifecycle"] == {
        "sha256": "386061832D7FCB978A30CCCD0C3B8EFCC8E07B68D397868885C1E132AED34701",
        "bytes": 159219,
    }
    assert IMPORTED_PHASE7_EVIDENCE["publishing_systems_brief"] == {
        "sha256": "C7768ACC7B3458AEF355C50A3FE6254EC1C80D0BE580A2DD939D6AE74BD9E633",
        "bytes": 29442,
    }


def test_adapter_preserves_candidate_raw_envelope_and_emits_only_common_core():
    raw = _raw()
    artifact = build_candidate_artifact(_manifest("phase4"), raw)

    assert artifact["candidate_specific_raw"] == raw
    core_surface = artifact["common_core"]["surfaces"]["player_session"]
    assert core_surface["sample_counts"] == SAMPLE_COUNTS
    assert core_surface["scenarios"]["steady"]["render_ms"] == 0.0
    assert core_surface["pressure"]["active_payload_bytes_per_minute"] == 12000.0
    assert artifact["imported_phase7_evidence"] == IMPORTED_PHASE7_EVIDENCE


def test_real_raw_server_timing_shape_from_both_committed_harnesses_is_parsed_equivalently():
    phase4 = _phase4_measurement_module()
    current_path = Path("scripts/measure_live_latency.py")
    spec = importlib.util.spec_from_file_location("phase8_measure_live_latency_characterization", current_path)
    assert spec and spec.loader
    current = importlib.util.module_from_spec(spec)
    sys.modules[current.__name__] = current
    spec.loader.exec_module(current)
    raw = _sample(changed=False, request=12.0, db=1.25, render=0.0, apply=0.0, payload=84.0)

    phase4_normalized = phase4.normalize_sample(raw, scenario="steady", surface_name="session")
    current_normalized = current.normalize_sample(raw, scenario="steady", surface_name="session")

    assert "serverTimingParsed" not in raw
    assert phase4_normalized["serverTimingParsed"] == current_normalized["serverTimingParsed"] == {
        "state-check": 0.25,
        "db": 1.25,
        "render": 0.0,
        "total": 6.0,
    }
    assert parse_server_timing(raw["serverTiming"]) == phase4_normalized["serverTimingParsed"]
    artifact = build_candidate_artifact(_manifest("phase4"), _raw())
    assert artifact["common_core"]["surfaces"]["player_session"]["scenarios"]["steady"]["db_ms"] == 0.2


def test_collection_runner_executes_the_locked_two_actor_schedule_without_harness_changes():
    pages: list[_FakePage] = []

    def page_factory() -> _FakePage:
        page = _FakePage()
        pages.append(page)
        return page

    artifact = collect_candidate(
        _manifest("phase4"),
        base_url="http://127.0.0.1:5000",
        campaign="sanitized-campaign",
        credentials={"player": ("player@example.test", "player-password"), "manager": ("dm@example.test", "dm-password")},
        page_factory=page_factory,
    )

    assert len(pages) == len(SURFACES)
    assert artifact["common_core"]["surfaces"]["dm_session_tools"]["sample_counts"] == SAMPLE_COUNTS
    assert all(len(page.sampler_calls) == sum(SAMPLE_COUNTS.values()) for page in pages)
    assert all(call["forceApply"] is False for page in pages for call in page.sampler_calls[:21])
    assert all(call["forceApply"] is True for page in pages for call in page.sampler_calls[21:])
    assert pages[0].filled[0] == "player@example.test"
    assert pages[2].filled[0] == "dm@example.test"


def test_missing_or_unassigned_combat_character_is_a_hold_not_a_pass():
    manifest = _manifest("phase4")
    manifest["combat_character"] = {"slug": "", "assigned": False}

    with pytest.raises(ContractError, match="combat_character"):
        build_candidate_artifact(manifest, _raw())


def test_adapter_refuses_ad_hoc_sample_schema_normalization():
    raw = _raw()
    sample = raw["surfaces"]["player_session"]["scenarios"]["cold"][0]
    sample["request_ms"] = sample.pop("requestMs")

    with pytest.raises(ContractError, match="requestMs"):
        build_candidate_artifact(_manifest("phase4"), raw)


def test_adapter_refuses_preinjected_server_timing_parsed_without_raw_browser_header():
    raw = _raw()
    sample = raw["surfaces"]["player_session"]["scenarios"]["cold"][0]
    sample.pop("serverTiming")
    sample["serverTimingParsed"] = {"db": 2.0, "render": 1.0}

    with pytest.raises(ContractError, match="sample.serverTiming"):
        build_candidate_artifact(_manifest("phase4"), raw)


def test_adapter_rejects_schema_or_fixture_drift_before_comparison():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["manifest"]["fixture_sha256"] = "e" * 64

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is False
    assert result["holds"] == ["manifest mismatch: fixture_sha256"]


def test_adapter_accepts_locked_schedule_zero_semantics_and_controls_within_threshold():
    result = evaluate_pair(_artifact("phase4"), _artifact("phase8"))

    assert result["accepted"] is True
    assert all(surface["accepted"] is True for surface in result["surface_results"].values())


def test_adapter_rejects_more_than_fifteen_percent_p95_regression():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["player_combat"]["scenarios"]["cold"]["request_ms"] = 11.6

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is False
    assert any("player_combat.cold.request_ms p95 regression" in hold for hold in result["holds"])


def test_adapter_rejects_nonzero_semantic_zero_render_and_unexpected_errors():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["player_session"]["scenarios"]["steady"]["render_ms"] = 0.1
    phase8["common_core"]["surfaces"]["dm_session_tools"]["errors"] = [
        {"kind": "console_error", "message": "unexpected console failure"}
    ]

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is False
    assert any("semantic zero" in hold for hold in result["holds"])
    assert any("unexpected console_error" in hold for hold in result["holds"])


def test_predeclared_console_allowlist_does_not_count_as_an_unexpected_error():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["dm_combat_status"]["errors"] = [
        {"kind": "console_error", "message": "known diagnostics noise"}
    ]

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is True


def test_compare_cli_writes_hold_result_without_normalizing_artifacts(tmp_path):
    phase4_path = tmp_path / "phase4.json"
    phase8_path = tmp_path / "phase8.json"
    output_path = tmp_path / "result.json"
    phase4_path.write_text(json.dumps(_artifact("phase4")), encoding="utf-8")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["player_session"]["sample_counts"] = {"warmup": 0}
    phase8_path.write_text(json.dumps(phase8), encoding="utf-8")

    exit_code = main([
        "compare",
        "--phase4",
        str(phase4_path),
        "--phase8",
        str(phase8_path),
        "--output",
        str(output_path),
    ])

    assert exit_code == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["accepted"] is False
    assert any("sample schedule" in hold for hold in payload["holds"])
