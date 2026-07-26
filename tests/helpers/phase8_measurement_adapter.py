"""Candidate-neutral Phase 8 live-measurement support runner.

This is deliberately test support, not a replacement for
``scripts/measure_live_latency.py``.  It owns the Phase 4-to-Phase 8 protocol
where the two committed harnesses have different surface inventories and raw
envelopes.  It collects both candidates from a commit-bound manifest, keeps the
raw candidate envelopes intact, and emits only the declared common core for
comparison.

The provenance values below are source identities, not mutable configuration:

* Phase 4 hardened release: b80af7c7b441bb2fcecc763bf6ea4a73f9d85365 /
  30dc769f0f8d40b1f89307459cf2700541815c02 /
  09340d98d72f99397c825489ea205b41dd6b3bba.
* Phase 8 harness source: 1d79c678a2c1f06a172eda9f6269c31517c36cec.
* Imported Phase 7 provenance remains immutable at the two SHA-256 values in
  ``IMPORTED_PHASE7_EVIDENCE``.  No ignored evidence file is read or copied by
  this tracked support runner.

It is executable for an authorized local measurement only.  It neither starts
an application nor substitutes production measurement; callers provide the
already-running local candidate URL and a commit-bound, non-secret manifest.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
from typing import Any
from urllib.parse import urljoin


ADAPTER_SCHEMA = "phase8-candidate-neutral-live-v2"
PHASE4_IDENTITY = {
    "commit": "b80af7c7b441bb2fcecc763bf6ea4a73f9d85365",
    "tree": "30dc769f0f8d40b1f89307459cf2700541815c02",
    "harness_blob": "09340d98d72f99397c825489ea205b41dd6b3bba",
}
PHASE8_IDENTITY = {
    "commit": "3fdb48c9bed822719a2c71c8463c7e52474cdd2d",
    "tree": "ea29374fdf895bd5d24bf3145872126e0b6fbc6f",
    "harness_blob": "1d79c678a2c1f06a172eda9f6269c31517c36cec",
}
PHASE8_HARNESS_BLOB = PHASE8_IDENTITY["harness_blob"]
FIXTURE_MANIFEST_BYTES = 5004
FIXTURE_MANIFEST_SHA256 = "BEDFA24251CBE9BEE44EDC0771B223E34037028E081ADCA0CABB43531897D8F1"
LOCK_SHA256 = "E0D5BDD5AF435E5CAD17DDA2BE256EE108B1697547FD0D0ECC146BD02D8493E9"
IMPORTED_PHASE7_EVIDENCE = {
    "lifecycle": {
        "sha256": "386061832D7FCB978A30CCCD0C3B8EFCC8E07B68D397868885C1E132AED34701",
        "bytes": 159219,
    },
    "publishing_systems_brief": {
        "sha256": "C7768ACC7B3458AEF355C50A3FE6254EC1C80D0BE580A2DD939D6AE74BD9E633",
        "bytes": 29442,
    },
}

SAMPLE_COUNTS = {"warmup": 1, "cold": 8, "steady": 12, "forced_apply": 6}
ERROR_KINDS = frozenset({"unexpected_status", "sampler_exception", "page_error", "console_error"})
P95_METRICS = ("request_ms", "db_ms", "render_ms", "apply_ms", "payload_bytes")
PRESSURE_METRICS = (
    "active_payload_bytes_per_minute",
    "active_server_ms_per_minute",
    "idle_payload_bytes_per_minute",
    "idle_server_ms_per_minute",
)


@dataclass(frozen=True)
class Surface:
    """A source-proven semantic surface, independent of either harness name."""

    name: str
    actor: str
    page_path: str
    root_selector: str
    metric_view: str
    legacy_requests_per_minute: float


SURFACES = (
    Surface(
        "player_session",
        "player",
        "/campaigns/{campaign}/session",
        '[data-session-live-root][data-session-live-view="session"]',
        "session",
        20.0,
    ),
    Surface(
        "player_combat",
        "player",
        "/campaigns/{campaign}/combat",
        "[data-combat-live-root]",
        "combat",
        60.0,
    ),
    Surface(
        "dm_session_tools",
        "manager",
        "/campaigns/{campaign}/session/dm?dm_view=tools",
        '[data-session-live-root][data-session-live-view="dm"]',
        "session-dm",
        30.0,
    ),
    Surface(
        "dm_combat_status",
        "manager",
        "/campaigns/{campaign}/combat/dm",
        "[data-combat-live-root]",
        "combat",
        60.0,
    ),
    Surface(
        "dm_combat_controls",
        "manager",
        "/campaigns/{campaign}/combat/dm?view=controls",
        "[data-combat-live-root]",
        "combat",
        60.0,
    ),
)

CANONICAL_LOCAL_SETTINGS = {
    "profile": "phase8-local-settings-v1",
    "environment": {
        "PLAYER_WIKI_ENV": "development",
        "PLAYER_WIKI_HOST": "127.0.0.1",
        "PLAYER_WIKI_PREFERRED_URL_SCHEME": "http",
        "PLAYER_WIKI_RELOAD_CONTENT": "0",
        "PLAYER_WIKI_SESSION_COOKIE_SECURE": "0",
    },
    "launch": {"debug": False, "use_reloader": False},
}
CANONICAL_DIAGNOSTICS = {
    "profile": "phase8-local-diagnostics-v1",
    "environment": {
        "PLAYER_WIKI_LIVE_DIAGNOSTICS": "1",
        "PLAYER_WIKI_LIVE_SLOW_LOG_THRESHOLD_MS": "0",
        "PLAYER_WIKI_REQUEST_SLOW_LOG_THRESHOLD_MS": "0",
        "PLAYER_WIKI_REQUEST_TRAIL_ENABLED": "0",
    },
}
CANONICAL_SCHEMA = {
    "adapter_schema": ADAPTER_SCHEMA,
    "artifact_schema": "phase8-candidate-artifact-v1",
    "comparison_schema": "phase8-candidate-comparison-v1",
    "markdown_schema": "phase8-candidate-neutral-summary-v1",
    "raw_sample_fields": ["requestMs", "applyMs", "payloadBytes", "requestTimeMs", "serverTiming", "changed"],
    "artifact_fields": [
        "adapter_schema",
        "manifest",
        "candidate_specific_raw",
        "common_core",
        "imported_phase7_evidence",
    ],
    "comparison_fields": ["accepted", "holds", "surface_results"],
    "sample_counts": SAMPLE_COUNTS,
    "error_kinds": ["console_error", "page_error", "sampler_exception", "unexpected_status"],
    "p95_metrics": list(P95_METRICS),
    "pressure_metrics": list(PRESSURE_METRICS),
    "thresholds": {"p95_regression_max_ratio": 1.15, "steady_render_p95_max_ms": 1.0},
    "surface_manifest": [asdict(surface) for surface in SURFACES],
}
CANONICAL_PROVENANCE_SHA256 = {
    "local_settings_sha256": "57E76D15A76CC08918D9372E476FA1B4CAC9B216E6BEA84C509AE9B65C4BD47D",
    "diagnostics_sha256": "F0068B69015E17A6FC32919B213AC08273E8BBA6AFF0BB9D2F64EC89773FBE17",
    "schema_sha256": "09A19A23038FA47B52FEC8BF527DA229D635CA9CDC45782F8E6BC8E83DB71E90",
}


def canonical_provenance_sha256() -> dict[str, str]:
    """Construct the non-fixture provenance hashes from their declared maps."""

    constructed = {
        "local_settings_sha256": canonical_json_sha256(CANONICAL_LOCAL_SETTINGS),
        "diagnostics_sha256": canonical_json_sha256(CANONICAL_DIAGNOSTICS),
        "schema_sha256": canonical_json_sha256(CANONICAL_SCHEMA),
    }
    if constructed != CANONICAL_PROVENANCE_SHA256:
        raise RuntimeError("The checked-in Phase 8 canonical provenance maps no longer match their declared hashes.")
    return constructed


def build_measurement_manifest(
    candidate_name: str,
    *,
    candidate_root: Path,
    player_principal: str,
    manager_principal: str,
) -> dict[str, Any]:
    """Construct the only acceptable non-secret manifest for a local capture."""

    identity = {"phase4": PHASE4_IDENTITY, "phase8": PHASE8_IDENTITY}.get(candidate_name)
    if identity is None:
        raise ContractError("Manifest construction is limited to pinned phase4 or phase8 candidates.")
    player = _require_string(player_principal, "player_principal")
    manager = _require_string(manager_principal, "manager_principal")
    if player == manager:
        raise ContractError("Manifest construction requires distinct player and manager principals.")
    fixture = fixture_manifest_proof(candidate_root, identity["commit"])
    manifest: dict[str, Any] = {
        "adapter_schema": ADAPTER_SCHEMA,
        "candidate": {"name": candidate_name, **identity},
        "fixture_sha256": fixture["sha256"],
        **canonical_provenance_sha256(),
        "runtime": {"python": "3.12.12", "development_lock_sha256": LOCK_SHA256},
        "combat_character": {"slug": "arden-march", "assigned": True},
        "actors": {
            "player": {"present": True, "principal": player},
            "manager": {"present": True, "principal": manager},
        },
        "surface_manifest": [asdict(surface) for surface in SURFACES],
        "console_error_allowlist": [],
    }
    validate_manifest(manifest, expected_candidate=candidate_name)
    return manifest


class ContractError(ValueError):
    """Raised for a schema/protocol mismatch that must keep Phase 8 on HOLD."""


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the declared provenance/report representation without platform drift."""

    return (json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest().upper()


def fixture_manifest_proof(candidate_root: Path, commit: str) -> dict[str, object]:
    """Hash raw Git tree bytes, never a filesystem copy or normalized text."""

    identity = {PHASE4_IDENTITY["commit"], PHASE8_IDENTITY["commit"]}
    if commit not in identity:
        raise ContractError("Fixture provenance is limited to the pinned Phase 4 and Phase 8 commits.")
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(candidate_root),
            "ls-tree",
            "-r",
            "-z",
            commit,
            "--",
            "tests/fixtures/sample_campaigns",
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ContractError("Could not read the pinned sanitized fixture manifest from Git.")
    raw = completed.stdout
    proof = {"bytes": len(raw), "sha256": sha256(raw).hexdigest().upper()}
    if proof != {"bytes": FIXTURE_MANIFEST_BYTES, "sha256": FIXTURE_MANIFEST_SHA256}:
        raise ContractError("Pinned sanitized fixture manifest does not match the source-proven Phase 4/8 proof.")
    return proof


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object.")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string.")
    return value.strip()


def _require_hex(value: object, label: str, length: int) -> str:
    text = _require_string(value, label)
    if len(text) != length or not all(character in "0123456789abcdefABCDEF" for character in text):
        raise ContractError(f"{label} must be a {length}-character hexadecimal identity.")
    return text.lower()


def _as_number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ContractError(f"{label} must be finite.")
    return number


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ContractError("Cannot calculate p95 from an empty sample list.")
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * 0.95
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ContractError("Cannot calculate a mean from an empty sample list.")
    return statistics.fmean(values)


def parse_server_timing(header_value: str) -> dict[str, float]:
    """Parse the raw browser ``Server-Timing`` string emitted by both harnesses.

    This is intentionally the source-proven parser contract, rather than a
    fallback for a pre-injected derived mapping.  Both committed measurement
    harnesses add ``serverTimingParsed`` only later in ``normalize_sample``.
    """

    timings: dict[str, float] = {}
    for part in header_value.split(","):
        segment = part.strip()
        if not segment:
            continue
        pieces = [piece.strip() for piece in segment.split(";") if piece.strip()]
        if not pieces:
            continue
        name = pieces[0]
        duration_ms = None
        for piece in pieces[1:]:
            if not piece.startswith("dur="):
                continue
            try:
                duration_ms = float(piece.split("=", 1)[1])
            except ValueError:
                duration_ms = None
            break
        if duration_ms is not None:
            timings[name] = duration_ms
    return timings


def _server_timing(sample: Mapping[str, Any]) -> Mapping[str, Any]:
    header_value = sample.get("serverTiming")
    if not isinstance(header_value, str):
        raise ContractError("sample.serverTiming must be the raw source-proven browser diagnostic string.")
    return parse_server_timing(header_value)


def _common_sample(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Project only source-shared metric names; retain the caller's raw sample elsewhere."""

    timing = _server_timing(sample)
    changed = sample.get("changed")
    if not isinstance(changed, bool):
        raise ContractError("sample.changed must be a boolean from the source-proven diagnostic schema.")
    return {
        "request_ms": _as_number(sample.get("requestMs"), "requestMs"),
        "db_ms": _as_number(timing.get("db"), "serverTimingParsed.db"),
        "render_ms": _as_number(timing.get("render"), "serverTimingParsed.render"),
        "apply_ms": _as_number(sample.get("applyMs"), "applyMs"),
        "payload_bytes": _as_number(sample.get("payloadBytes"), "payloadBytes"),
        "request_time_ms": _as_number(sample.get("requestTimeMs"), "requestTimeMs"),
        "changed": changed,
    }


def _summary(samples: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    common_samples = [_common_sample(sample) for sample in samples]
    return {
        metric: _p95([float(sample[metric]) for sample in common_samples])
        for metric in P95_METRICS
    } | {
        "request_time_mean_ms": _mean([float(sample["request_time_ms"]) for sample in common_samples]),
        "payload_mean_bytes": _mean([float(sample["payload_bytes"]) for sample in common_samples]),
        "changed_count": float(sum(1 for sample in common_samples if sample["changed"])),
    }


def _interval(dataset: Mapping[str, Any], key: str) -> float:
    interval = _as_number(dataset.get(key), f"dataset.{key}")
    if interval <= 0:
        raise ContractError(f"dataset.{key} must be greater than zero.")
    return interval


def _pressure(surface: Surface, dataset: Mapping[str, Any], steady: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    common_samples = [_common_sample(sample) for sample in steady]
    unchanged = [sample for sample in common_samples if not sample["changed"]]
    selected = unchanged or common_samples
    payload_mean = _mean([float(sample["payload_bytes"]) for sample in selected])
    request_mean = _mean([float(sample["request_time_ms"]) for sample in selected])
    active_rate = 60000.0 / _interval(dataset, "liveActiveIntervalMs")
    idle_rate = 60000.0 / _interval(dataset, "liveIdleIntervalMs")
    return {
        "active_payload_bytes_per_minute": payload_mean * active_rate,
        "active_server_ms_per_minute": request_mean * active_rate,
        "idle_payload_bytes_per_minute": payload_mean * idle_rate,
        "idle_server_ms_per_minute": request_mean * idle_rate,
    }


def _legacy_pressure(surface: Surface, cold: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    common_samples = [_common_sample(sample) for sample in cold]
    return {
        "payload_bytes_per_minute": _mean([float(sample["payload_bytes"]) for sample in common_samples])
        * surface.legacy_requests_per_minute,
        "server_ms_per_minute": _mean([float(sample["request_time_ms"]) for sample in common_samples])
        * surface.legacy_requests_per_minute,
    }


def _surface_controls(surface: Surface, scenarios: Mapping[str, Sequence[Mapping[str, Any]]], pressure: Mapping[str, float]) -> dict[str, bool]:
    cold = scenarios["cold"]
    steady = scenarios["steady"]
    cold_payload = _mean([_common_sample(sample)["payload_bytes"] for sample in cold])
    steady_payload = _mean([_common_sample(sample)["payload_bytes"] for sample in steady])
    legacy = _legacy_pressure(surface, cold)
    steady_render_p95 = _summary(steady)["render_ms"]
    return {
        "payload_80_percent_smaller": cold_payload > 0 and steady_payload <= cold_payload * 0.20,
        "steady_render_at_most_1ms": steady_render_p95 <= 1.0,
        "active_payload_lower_than_legacy": pressure["active_payload_bytes_per_minute"]
        < legacy["payload_bytes_per_minute"],
        "active_server_lower_than_legacy": pressure["active_server_ms_per_minute"]
        < legacy["server_ms_per_minute"],
        "idle_payload_lower_than_legacy": pressure["idle_payload_bytes_per_minute"]
        < legacy["payload_bytes_per_minute"],
        "idle_server_lower_than_legacy": pressure["idle_server_ms_per_minute"]
        < legacy["server_ms_per_minute"],
    }


def validate_manifest(manifest: Mapping[str, Any], *, expected_candidate: str | None = None) -> None:
    """Reject missing setup evidence before any candidate numbers are compared."""

    if _require_string(manifest.get("adapter_schema"), "manifest.adapter_schema") != ADAPTER_SCHEMA:
        raise ContractError("manifest.adapter_schema does not identify this candidate-neutral protocol.")
    candidate = _require_mapping(manifest.get("candidate"), "manifest.candidate")
    candidate_name = _require_string(candidate.get("name"), "manifest.candidate.name")
    if expected_candidate and candidate_name != expected_candidate:
        raise ContractError(f"Expected the {expected_candidate} manifest, received {candidate_name}.")
    commit = _require_hex(candidate.get("commit"), "manifest.candidate.commit", 40)
    tree = _require_hex(candidate.get("tree"), "manifest.candidate.tree", 40)
    harness_blob = _require_hex(candidate.get("harness_blob"), "manifest.candidate.harness_blob", 40)
    if candidate_name == "phase4":
        if {"commit": commit, "tree": tree, "harness_blob": harness_blob} != PHASE4_IDENTITY:
            raise ContractError("Phase 4 manifest does not name the hardened release and exact harness blob.")
    elif candidate_name == "phase8":
        if {"commit": commit, "tree": tree, "harness_blob": harness_blob} != PHASE8_IDENTITY:
            raise ContractError("Phase 8 manifest does not name the frozen candidate and exact harness blob.")
    else:
        raise ContractError("manifest.candidate.name must be phase4 or phase8.")

    fixture_sha256 = _require_hex(manifest.get("fixture_sha256"), "manifest.fixture_sha256", 64).upper()
    if fixture_sha256 != FIXTURE_MANIFEST_SHA256:
        raise ContractError("manifest.fixture_sha256 does not match the raw pinned sanitized fixture manifest.")
    for key, expected_hash in canonical_provenance_sha256().items():
        actual_hash = _require_hex(manifest.get(key), f"manifest.{key}", 64).upper()
        if actual_hash != expected_hash:
            raise ContractError(f"manifest.{key} does not match its canonical source-proven map.")
    runtime = _require_mapping(manifest.get("runtime"), "manifest.runtime")
    if _require_string(runtime.get("python"), "manifest.runtime.python") != "3.12.12":
        raise ContractError("The adapter requires CPython 3.12.12.")
    if _require_hex(runtime.get("development_lock_sha256"), "manifest.runtime.development_lock_sha256", 64).upper() != LOCK_SHA256:
        raise ContractError("The adapter requires the exact 29-package development lock manifest.")

    combat_character = _require_mapping(manifest.get("combat_character"), "manifest.combat_character")
    if not _require_string(combat_character.get("slug"), "manifest.combat_character.slug") or not bool(
        combat_character.get("assigned")
    ):
        raise ContractError("Missing or unassigned combat_character is a HOLD, never a pass.")
    actors = _require_mapping(manifest.get("actors"), "manifest.actors")
    for actor in ("player", "manager"):
        actor_record = _require_mapping(actors.get(actor), f"manifest.actors.{actor}")
        if not bool(actor_record.get("present")):
            raise ContractError(f"manifest.actors.{actor}.present must be true.")
    if _require_string(actors["player"].get("principal"), "manifest.actors.player.principal") == _require_string(
        actors["manager"].get("principal"), "manifest.actors.manager.principal"
    ):
        raise ContractError("The player and manager actors must be distinct principals.")

    declared = manifest.get("surface_manifest")
    if declared != [asdict(surface) for surface in SURFACES]:
        raise ContractError("surface_manifest must exactly match the source-proven five-surface manifest.")
    allowlist = manifest.get("console_error_allowlist", [])
    if not isinstance(allowlist, list) or not all(isinstance(value, str) for value in allowlist):
        raise ContractError("console_error_allowlist must be a predeclared list of regular expressions.")


def _compare_shared_manifest(phase4: Mapping[str, Any], phase8: Mapping[str, Any]) -> list[str]:
    holds: list[str] = []
    for key in ("fixture_sha256", "local_settings_sha256", "diagnostics_sha256", "schema_sha256"):
        if phase4.get(key) != phase8.get(key):
            holds.append(f"manifest mismatch: {key}")
    if phase4.get("runtime") != phase8.get("runtime"):
        holds.append("manifest mismatch: runtime")
    if phase4.get("surface_manifest") != phase8.get("surface_manifest"):
        holds.append("manifest mismatch: surface_manifest")
    return holds


def _sanitize_error_text(value: object) -> str:
    """Return deterministic, bundle-safe sampler evidence without local secrets."""

    text = str(value)
    text = re.sub(
        r"(?i)\b(?:password|credential|secret|token)\b(?:\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+))?",
        "<redacted>",
        text,
    )
    text = re.sub(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s'\"<>|]*", "<path>", text)
    text = re.sub(r"(?<![a-zA-Z0-9_:/])/(?:[^\s'\"<>|]+)", "<path>", text)
    return " ".join(text.split()) or "unspecified measurement error"


def _sanitize_error(error: object, *, fallback: str) -> dict[str, str]:
    """Keep one structured error record while dropping untrusted extra fields."""

    if not isinstance(error, Mapping):
        return {"kind": "schema_error", "message": _sanitize_error_text(fallback)}
    kind = error.get("kind")
    normalized_kind = re.sub(r"[^a-z0-9_]+", "_", kind.strip().lower()) if isinstance(kind, str) else ""
    normalized_kind = normalized_kind.strip("_") or "schema_error"
    message = error.get("message", fallback)
    return {"kind": normalized_kind, "message": _sanitize_error_text(message)}


def _incomplete_schedule_error(surface: Surface, scenario: str, actual: object, expected: int) -> dict[str, str]:
    return {
        "kind": "incomplete_schedule",
        "message": f"{surface.name}.{scenario} observed {actual} samples; locked count is {expected}.",
    }


def _collection_complete(report: Mapping[str, Any]) -> bool:
    """Recognize complete legacy evidence without fabricating any sample values."""

    marker = report.get("collection_complete")
    if marker is None:
        return report.get("sample_counts") == SAMPLE_COUNTS
    return marker is True


def build_candidate_artifact(manifest: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable raw/common-core envelope from a single candidate capture."""

    validate_manifest(manifest)
    raw_copy = deepcopy(dict(raw))
    raw_surfaces_value = raw_copy.get("surfaces")
    raw_surfaces = dict(raw_surfaces_value) if isinstance(raw_surfaces_value, Mapping) else {}
    raw_copy["surfaces"] = raw_surfaces
    core_surfaces: dict[str, Any] = {}
    for surface in SURFACES:
        raw_surface_value = raw_surfaces.get(surface.name)
        observed_counts: dict[str, int | str] = {}
        errors: list[dict[str, str]] = []
        complete = True
        if not isinstance(raw_surface_value, Mapping):
            complete = False
            errors.append(
                {
                    "kind": "schema_error",
                    "message": f"raw.surfaces.{surface.name} must be an object.",
                }
            )
            raw_surface: dict[str, Any] = {}
        else:
            raw_surface = dict(raw_surface_value)
            raw_surfaces[surface.name] = raw_surface
        raw_errors = raw_surface.get("errors", [])
        if not isinstance(raw_errors, list):
            complete = False
            errors.append(
                {
                    "kind": "schema_error",
                    "message": f"raw.surfaces.{surface.name}.errors must be a list.",
                }
            )
        else:
            errors.extend(
                _sanitize_error(error, fallback=f"raw.surfaces.{surface.name}.errors item was not an object.")
                for error in raw_errors
            )
        raw_scenarios_value = raw_surface.get("scenarios")
        if not isinstance(raw_scenarios_value, Mapping):
            complete = False
            raw_scenarios: Mapping[str, Any] = {}
            errors.append(
                {
                    "kind": "schema_error",
                    "message": f"raw.surfaces.{surface.name}.scenarios must be an object.",
                }
            )
        else:
            raw_scenarios = raw_scenarios_value
        scenarios: dict[str, list[Mapping[str, Any]]] = {}
        for scenario, expected_count in SAMPLE_COUNTS.items():
            samples = raw_scenarios.get(scenario)
            actual: int | str = len(samples) if isinstance(samples, list) else "missing"
            observed_counts[scenario] = actual
            if not isinstance(samples, list) or actual != expected_count:
                complete = False
                errors.append(_incomplete_schedule_error(surface, scenario, actual, expected_count))
                continue
            try:
                scenarios[scenario] = [_require_mapping(sample, f"{surface.name}.{scenario} sample") for sample in samples]
            except ContractError as exc:
                complete = False
                errors.append({"kind": "schema_error", "message": _sanitize_error_text(exc)})
        raw_surface["errors"] = deepcopy(errors)
        core_surface: dict[str, Any] = {
            "actor": surface.actor,
            "sample_counts": observed_counts,
            "collection_complete": complete,
            "errors": deepcopy(errors),
        }
        if complete:
            try:
                dataset = _require_mapping(raw_surface.get("dataset"), f"raw.surfaces.{surface.name}.dataset")
                pressure = _pressure(surface, dataset, scenarios["steady"])
                core_surface.update(
                    {
                        "scenarios": {key: _summary(value) for key, value in scenarios.items()},
                        "pressure": pressure,
                        "controls": _surface_controls(surface, scenarios, pressure),
                    }
                )
            except ContractError as exc:
                complete = False
                errors.append({"kind": "schema_error", "message": _sanitize_error_text(exc)})
                raw_surface["errors"] = deepcopy(errors)
                core_surface["collection_complete"] = False
                core_surface["errors"] = deepcopy(errors)
        core_surfaces[surface.name] = core_surface
    return {
        "adapter_schema": ADAPTER_SCHEMA,
        "manifest": deepcopy(dict(manifest)),
        "candidate_specific_raw": raw_copy,
        "common_core": {"surfaces": core_surfaces},
        "imported_phase7_evidence": deepcopy(IMPORTED_PHASE7_EVIDENCE),
    }


def _assert_bundle_safe(value: object, *, label: str = "bundle") -> None:
    """Refuse data that would leak a timestamp, local path, or credential value."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).lower()
            if any(token in normalized_key for token in ("password", "credential", "secret")):
                raise ContractError(f"{label} contains a prohibited credential field.")
            if normalized_key in {"timestamp", "started_at", "finished_at", "created_at", "updated_at"}:
                raise ContractError(f"{label} contains a prohibited timestamp field.")
            _assert_bundle_safe(child, label=f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_bundle_safe(child, label=f"{label}[{index}]")
        return
    if isinstance(value, str):
        if re.search(r"(?i)\b(?:password|credential|secret|token)\b", value):
            raise ContractError(f"{label} contains a prohibited credential value.")
        if re.match(r"^(?:[A-Za-z]:[\\/]|\\\\)", value) or (
            value.startswith("/") and not value.startswith("/campaigns/")
        ):
            raise ContractError(f"{label} contains a prohibited absolute path.")


def _candidate_markdown(artifact: Mapping[str, Any], *, source_sha256: str) -> str:
    manifest = _require_mapping(artifact.get("manifest"), "artifact.manifest")
    candidate = _require_mapping(manifest.get("candidate"), "artifact.manifest.candidate")
    surfaces = _require_mapping(
        _require_mapping(artifact.get("common_core"), "artifact.common_core").get("surfaces"),
        "artifact.common_core.surfaces",
    )
    lines = [
        "# Phase 8 Candidate Raw Summary",
        "",
        "## Provenance",
        "",
        f"- Candidate: `{candidate['name']}`",
        f"- Commit: `{candidate['commit']}`",
        f"- Tree: `{candidate['tree']}`",
        f"- Harness blob: `{candidate['harness_blob']}`",
        f"- Source SHA-256: `{source_sha256}`",
        "",
        "## Locked surfaces",
        "",
        "| Surface | Actor | Warmup | Cold | Steady | Forced apply |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for surface in SURFACES:
        report = _require_mapping(surfaces.get(surface.name), f"artifact surface {surface.name}")
        counts = _require_mapping(report.get("sample_counts"), f"artifact sample counts {surface.name}")
        lines.append(
            "| {name} | {actor} | {warmup} | {cold} | {steady} | {forced_apply} |".format(
                name=surface.name,
                actor=surface.actor,
                warmup=counts.get("warmup"),
                cold=counts.get("cold"),
                steady=counts.get("steady"),
                forced_apply=counts.get("forced_apply"),
            )
        )
    lines.extend(
        [
            "",
            "## Collection state",
            "",
            "| Surface | Complete | Errors |",
            "| --- | --- | --- |",
        ]
    )
    for surface in SURFACES:
        report = _require_mapping(surfaces.get(surface.name), f"artifact surface {surface.name}")
        errors = report.get("errors", [])
        if not isinstance(errors, list):
            raise ContractError(f"artifact errors for {surface.name} must be a list.")
        error_text = "; ".join(
            f"{error.get('kind', 'schema_error')}: {error.get('message', '')}"
            for error in errors
            if isinstance(error, Mapping)
        )
        lines.append(
            f"| {surface.name} | `{_collection_complete(report)}` | {error_text or 'None'} |"
        )
    return "\n".join(lines) + "\n"


def _comparison_markdown(payload: Mapping[str, Any], *, source_sha256: str) -> str:
    comparison = _require_mapping(payload.get("comparison"), "comparison bundle comparison")
    surface_results = _require_mapping(comparison.get("surface_results"), "comparison bundle surface_results")
    lines = [
        "# Phase 8 Candidate Comparison Summary",
        "",
        "## Result",
        "",
        f"- Accepted: `{bool(comparison.get('accepted'))}`",
        f"- Source SHA-256: `{source_sha256}`",
        "",
        "## Surface results",
        "",
        "| Surface | Accepted | Findings |",
        "| --- | --- | --- |",
    ]
    for surface in SURFACES:
        result = _require_mapping(surface_results.get(surface.name, {}), f"comparison surface {surface.name}")
        findings = result.get("findings", [])
        if not isinstance(findings, list):
            raise ContractError(f"comparison findings for {surface.name} must be a list.")
        lines.append(f"| {surface.name} | `{bool(result.get('accepted'))}` | {'; '.join(str(item) for item in findings) or '—'} |")
    holds = comparison.get("holds", [])
    if not isinstance(holds, list):
        raise ContractError("comparison holds must be a list.")
    lines.extend(["", "## Holds", ""])
    lines.extend(f"- {hold}" for hold in holds) if holds else lines.append("- None")
    return "\n".join(lines) + "\n"


def write_deterministic_bundles(
    output_dir: Path,
    phase4_artifact: Mapping[str, Any],
    phase8_artifact: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    """Write the six stable, non-secret Phase 8 evidence artifacts.

    The returned hashes are the evidence index; the comparison JSON additionally
    binds the two raw JSON sources and the two Markdown outputs before its own
    bytes are written, avoiding a self-referential output hash.
    """

    _assert_bundle_safe(phase4_artifact, label="phase4 artifact")
    _assert_bundle_safe(phase8_artifact, label="phase8 artifact")
    phase4_json = canonical_json_bytes(phase4_artifact)
    phase8_json = canonical_json_bytes(phase8_artifact)
    phase4_source = sha256(phase4_json).hexdigest().upper()
    phase8_source = sha256(phase8_json).hexdigest().upper()
    phase4_markdown = _candidate_markdown(phase4_artifact, source_sha256=phase4_source).encode("utf-8")
    phase8_markdown = _candidate_markdown(phase8_artifact, source_sha256=phase8_source).encode("utf-8")
    comparison_payload = {
        "adapter_schema": ADAPTER_SCHEMA,
        "comparison": evaluate_pair(phase4_artifact, phase8_artifact),
        "output_sha256": {
            "phase4.raw.md": sha256(phase4_markdown).hexdigest().upper(),
            "phase8.raw.md": sha256(phase8_markdown).hexdigest().upper(),
        },
        "source_sha256": {"phase4.raw.json": phase4_source, "phase8.raw.json": phase8_source},
    }
    _assert_bundle_safe(comparison_payload, label="comparison bundle")
    comparison_json = canonical_json_bytes(comparison_payload)
    comparison_source = sha256(comparison_json).hexdigest().upper()
    comparison_markdown = _comparison_markdown(comparison_payload, source_sha256=comparison_source).encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "phase4.raw.json": phase4_json,
        "phase4.raw.md": phase4_markdown,
        "phase8.raw.json": phase8_json,
        "phase8.raw.md": phase8_markdown,
        "comparison.json": comparison_json,
        "comparison.md": comparison_markdown,
    }
    for name, contents in files.items():
        (output_dir / name).write_bytes(contents)
    return {
        "source_sha256": {
            "phase4.raw.json": phase4_source,
            "phase8.raw.json": phase8_source,
            "comparison.json": comparison_source,
        },
        "output_sha256": {name: sha256(contents).hexdigest().upper() for name, contents in files.items()},
    }


def _error_is_allowed(error: Mapping[str, Any], allowlist: Sequence[str]) -> bool:
    if error.get("kind") != "console_error":
        return False
    message = str(error.get("message", ""))
    return any(re.search(pattern, message) for pattern in allowlist)


def _surface_errors(surface: Mapping[str, Any], allowlist: Sequence[str]) -> list[Mapping[str, Any]]:
    errors = surface.get("errors", [])
    if not isinstance(errors, list):
        return [{"kind": "schema", "message": "errors was not a list"}]
    unexpected: list[Mapping[str, Any]] = []
    for error in errors:
        if not isinstance(error, Mapping):
            unexpected.append({"kind": "schema", "message": "error item was not an object"})
        elif not _error_is_allowed(error, allowlist):
            unexpected.append(error)
    return unexpected


def _p95_regression(baseline: float, candidate: float, *, metric: str) -> str | None:
    if baseline > 0:
        if candidate > baseline * 1.15:
            return f"{metric} p95 regression {candidate:.4f} exceeds 15% over {baseline:.4f}"
    elif metric.endswith(("render_ms", "apply_ms")) and candidate != 0:
        return f"{metric} must remain semantic zero; candidate is {candidate:.4f}"
    return None


def evaluate_pair(phase4_artifact: Mapping[str, Any], phase8_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a frozen comparison and return explicit PASS/HOLD findings.

    Input schema failures remain HOLD findings here so the caller can retain the
    raw artifacts, instead of silently discarding a failed measurement.
    """

    holds: list[str] = []
    try:
        if phase4_artifact.get("adapter_schema") != ADAPTER_SCHEMA or phase8_artifact.get("adapter_schema") != ADAPTER_SCHEMA:
            raise ContractError("artifact adapter_schema mismatch")
        phase4_manifest = _require_mapping(phase4_artifact.get("manifest"), "phase4 artifact manifest")
        phase8_manifest = _require_mapping(phase8_artifact.get("manifest"), "phase8 artifact manifest")
        validate_manifest(phase4_manifest, expected_candidate="phase4")
        validate_manifest(phase8_manifest, expected_candidate="phase8")
        holds.extend(_compare_shared_manifest(phase4_manifest, phase8_manifest))
        phase4_surfaces = _require_mapping(
            _require_mapping(phase4_artifact.get("common_core"), "phase4 common_core").get("surfaces"),
            "phase4 common_core.surfaces",
        )
        phase8_surfaces = _require_mapping(
            _require_mapping(phase8_artifact.get("common_core"), "phase8 common_core").get("surfaces"),
            "phase8 common_core.surfaces",
        )
    except ContractError as exc:
        return {"accepted": False, "holds": [str(exc)], "surface_results": {}}

    surface_results: dict[str, Any] = {}
    for surface in SURFACES:
        baseline = phase4_surfaces.get(surface.name)
        candidate = phase8_surfaces.get(surface.name)
        findings: list[str] = []
        if not isinstance(baseline, Mapping) or not isinstance(candidate, Mapping):
            holds.append(f"missing comparable surface: {surface.name}")
            continue
        for label, report, manifest in (
            ("phase4", baseline, phase4_manifest),
            ("phase8", candidate, phase8_manifest),
        ):
            sample_counts = report.get("sample_counts")
            if sample_counts != SAMPLE_COUNTS:
                findings.append(f"{label} sample schedule differs from locked 1/8/12/6 counts")
            if not _collection_complete(report):
                findings.append(f"{label} collection is incomplete; metric comparisons are not evaluated")
            for error in _surface_errors(report, list(manifest.get("console_error_allowlist", []))):
                findings.append(f"{label} unexpected {error.get('kind')}: {error.get('message', '')}")
        if not _collection_complete(baseline) or not _collection_complete(candidate):
            surface_results[surface.name] = {"accepted": False, "findings": findings}
            holds.extend(findings)
            continue
        try:
            baseline_scenarios = _require_mapping(baseline.get("scenarios"), f"{surface.name} phase4 scenarios")
            candidate_scenarios = _require_mapping(candidate.get("scenarios"), f"{surface.name} phase8 scenarios")
            for scenario in ("cold", "steady", "forced_apply"):
                baseline_summary = _require_mapping(baseline_scenarios.get(scenario), f"{surface.name} phase4 {scenario}")
                candidate_summary = _require_mapping(candidate_scenarios.get(scenario), f"{surface.name} phase8 {scenario}")
                for metric in P95_METRICS:
                    finding = _p95_regression(
                        _as_number(baseline_summary.get(metric), f"{surface.name}.{scenario}.phase4.{metric}"),
                        _as_number(candidate_summary.get(metric), f"{surface.name}.{scenario}.phase8.{metric}"),
                        metric=f"{surface.name}.{scenario}.{metric}",
                    )
                    if finding:
                        findings.append(finding)
            steady_render = _as_number(
                _require_mapping(candidate_scenarios.get("steady"), f"{surface.name} phase8 steady").get("render_ms"),
                f"{surface.name}.phase8.steady.render_ms",
            )
            if steady_render > 1.0:
                findings.append(f"{surface.name}.steady.render_ms {steady_render:.4f} exceeds 1.0 ms")
            baseline_pressure = _require_mapping(baseline.get("pressure"), f"{surface.name} phase4 pressure")
            candidate_pressure = _require_mapping(candidate.get("pressure"), f"{surface.name} phase8 pressure")
            for metric in PRESSURE_METRICS:
                baseline_value = _as_number(baseline_pressure.get(metric), f"{surface.name}.phase4.{metric}")
                candidate_value = _as_number(candidate_pressure.get(metric), f"{surface.name}.phase8.{metric}")
                if baseline_value > 0 and candidate_value > baseline_value * 1.15:
                    findings.append(
                        f"{surface.name}.{metric} regression {candidate_value:.4f} exceeds 15% over {baseline_value:.4f}"
                    )
            baseline_controls = _require_mapping(baseline.get("controls"), f"{surface.name} phase4 controls")
            candidate_controls = _require_mapping(candidate.get("controls"), f"{surface.name} phase8 controls")
            for control in baseline_controls:
                if bool(baseline_controls[control]) and not bool(candidate_controls.get(control)):
                    findings.append(f"{surface.name} did not retain existing control {control}")
        except ContractError as exc:
            findings.append(f"{surface.name} comparison schema error: {_sanitize_error_text(exc)}")
        surface_results[surface.name] = {"accepted": not findings, "findings": findings}
        holds.extend(findings)
    return {"accepted": not holds, "holds": holds, "surface_results": surface_results}


def _wait_for_sampler(page: Any, metric_view: str) -> None:
    page.wait_for_function(
        """(metricView) => Boolean(
            window.__playerWikiLiveDiagnostics &&
            window.__playerWikiLiveDiagnostics[metricView] &&
            typeof window.__playerWikiLiveDiagnostics[metricView].sample === "function"
        )""",
        arg=metric_view,
        timeout=10000,
    )


def _sample(page: Any, metric_view: str, scenario: str) -> Mapping[str, Any]:
    force_apply = scenario == "forced_apply"
    return _require_mapping(
        page.evaluate(
            """async ({ metricView, scenarioName, forceApply }) => {
                const sampler = window.__playerWikiLiveDiagnostics?.[metricView]?.sample;
                if (typeof sampler !== "function") {
                    throw new Error(`Missing sampler ${metricView}`);
                }
                return await sampler({
                    mode: scenarioName === "cold" || scenarioName === "forced_apply" ? "cold" : "steady",
                    forceApply,
                    forceManager: forceApply,
                    forceComposer: forceApply,
                });
            }""",
            {"metricView": metric_view, "scenarioName": scenario, "forceApply": force_apply},
        ),
        f"sampler result for {metric_view}",
    )


def _dataset(page: Any, selector: str) -> Mapping[str, Any]:
    return _require_mapping(
        page.locator(selector).evaluate(
            """(node) => Object.fromEntries(
                Object.entries(node.dataset || {}).map(([key, value]) => [key, String(value || "")])
            )"""
        ),
        "live-root dataset",
    )


def collect_candidate(
    manifest: Mapping[str, Any],
    *,
    base_url: str,
    campaign: str,
    credentials: Mapping[str, tuple[str, str]],
    page_factory: Callable[[], Any],
) -> dict[str, Any]:
    """Collect one local candidate with the locked protocol.

    ``page_factory`` is injected so focused tests can prove protocol collection
    without a browser or private credentials.  The executable CLI supplies a
    Playwright-backed factory when an authorized measurement is actually run.
    """

    validate_manifest(manifest)
    raw_surfaces: dict[str, Any] = {}
    for surface in SURFACES:
        if surface.actor not in credentials:
            raise ContractError(f"Missing credentials for required {surface.actor} actor.")
        page = page_factory()
        errors: list[dict[str, str]] = []
        allowlist = list(manifest.get("console_error_allowlist", []))
        sampling_active = False

        def record_console(message: Any) -> None:
            if getattr(message, "type", "") != "error":
                return
            text = getattr(message, "text", "")
            if not any(re.search(pattern, text) for pattern in allowlist):
                errors.append({"kind": "console_error", "message": str(text)})

        def record_response(response: Any) -> None:
            if sampling_active and int(getattr(response, "status", 0)) >= 400:
                errors.append(
                    {
                        "kind": "unexpected_status",
                        "message": f"sampler response {response.status} at {getattr(response, 'url', '')}",
                    }
                )

        page.on("pageerror", lambda error: errors.append({"kind": "page_error", "message": str(error)}))
        page.on("console", record_console)
        page.on("response", record_response)
        email, password = credentials[surface.actor]
        page.goto(urljoin(base_url, "/sign-in"), wait_until="domcontentloaded")
        page.locator('input[name="email"]').fill(email)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        if "/sign-in" in page.url:
            raise ContractError(f"{surface.name}: sign-in did not complete for {surface.actor}.")
        path = surface.page_path.format(campaign=campaign)
        response = page.goto(urljoin(base_url, path), wait_until="domcontentloaded")
        if response is not None and int(response.status) >= 400:
            errors.append({"kind": "unexpected_status", "message": f"page navigation returned {response.status}"})
        page.wait_for_selector(surface.root_selector, timeout=10000)
        dataset = _dataset(page, surface.root_selector)
        if dataset.get("liveDiagnosticsEnabled") != "1":
            raise ContractError(f"{surface.name}: diagnostics are not enabled.")
        _wait_for_sampler(page, surface.metric_view)
        scenarios: dict[str, list[Mapping[str, Any]]] = {key: [] for key in SAMPLE_COUNTS}
        sampling_active = True
        try:
            for scenario, count in SAMPLE_COUNTS.items():
                for _ in range(count):
                    try:
                        scenarios[scenario].append(_sample(page, surface.metric_view, scenario))
                    except Exception as exc:  # The error is evidence; continue to retain the attempted schedule.
                        errors.append({"kind": "sampler_exception", "message": str(exc)})
        finally:
            sampling_active = False
        raw_surfaces[surface.name] = {"dataset": dict(dataset), "scenarios": scenarios, "errors": errors}
    return build_candidate_artifact(manifest, {"surfaces": raw_surfaces})


def _read_json(path: str) -> Mapping[str, Any]:
    return _require_mapping(json.loads(Path(path).read_text(encoding="utf-8")), path)


def _write_json(path: str, payload: Mapping[str, Any]) -> None:
    Path(path).write_bytes(canonical_json_bytes(payload))


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ContractError(f"Missing required environment variable {name}.")
    return value


def _collect_with_playwright(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised only in an authorized browser lane
        raise ContractError("Playwright is required for collection.") from exc
    manifest = _read_json(args.manifest)
    credentials = {
        "player": (_env("PLAYER_WIKI_MEASURE_PLAYER_EMAIL"), _env("PLAYER_WIKI_MEASURE_PLAYER_PASSWORD")),
        "manager": (_env("PLAYER_WIKI_MEASURE_EMAIL"), _env("PLAYER_WIKI_MEASURE_PASSWORD")),
    }
    with sync_playwright() as playwright:  # pragma: no cover - browser gate is separate from focused unit tests
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            return collect_candidate(
                manifest,
                base_url=args.base_url,
                campaign=args.campaign,
                credentials=credentials,
                page_factory=context.new_page,
            )
        finally:
            context.close()
            browser.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8 candidate-neutral live measurement support runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect", help="collect one authorized local candidate")
    collect.add_argument("--manifest", required=True)
    collect.add_argument("--base-url", required=True)
    collect.add_argument("--campaign", required=True)
    collect.add_argument("--output", required=True)
    compare = subparsers.add_parser("compare", help="compare two collected adapter artifacts")
    compare.add_argument("--phase4", required=True)
    compare.add_argument("--phase8", required=True)
    compare.add_argument("--output", required=True)
    bundle = subparsers.add_parser("bundle", help="write deterministic Phase 8 JSON and Markdown evidence bundles")
    bundle.add_argument("--phase4", required=True)
    bundle.add_argument("--phase8", required=True)
    bundle.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            _write_json(args.output, _collect_with_playwright(args))
            return 0
        phase4 = _read_json(args.phase4)
        phase8 = _read_json(args.phase8)
        if args.command == "bundle":
            result = evaluate_pair(phase4, phase8)
            write_deterministic_bundles(Path(args.output_dir), phase4, phase8)
            return 0 if result["accepted"] else 2
        result = evaluate_pair(phase4, phase8)
        _write_json(args.output, result)
        return 0 if result["accepted"] else 2
    except ContractError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the explicit CLI only
    raise SystemExit(main())
