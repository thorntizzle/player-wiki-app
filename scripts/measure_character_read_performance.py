"""Deterministic Character-read baseline measurement contract and collector.

The module deliberately keeps its contract primitives importable without Flask,
Werkzeug, or Playwright.  Runtime-only dependencies are imported by the command
entry point so focused unit tests can audit the evidence rules in isolation.
"""

from __future__ import annotations

import asyncio
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import importlib.metadata as importlib_metadata
import importlib.util
import json
import math
import os
import platform
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
import unicodedata
import uuid


def _bind_repo_root_first(repo_root: Path) -> None:
    """Put one explicit candidate root first without discarding other paths."""

    def resolves_to_root(entry: object) -> bool:
        if not isinstance(entry, (str, os.PathLike)) or not entry:
            return False
        try:
            return Path(entry).resolve(strict=False) == repo_root
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    sys.path[:] = [
        os.fspath(repo_root),
        *(entry for entry in sys.path if not resolves_to_root(entry)),
    ]


# Direct absolute execution normally puts only ``scripts/`` on sys.path.  Bind
# runtime imports to the exact candidate containing this tracked harness before
# any app package can be imported.  Runtime boundaries repeat this binding
# because test collectors and launchers may safely prepend their own paths later.
SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
_bind_repo_root_first(SCRIPT_REPO_ROOT)


SCHEMA = "campaign-player-wiki.character-read-performance.v1"
EVIDENCE_RELATIVE_ROOT = Path(".local/evidence/character-read-performance/slice-0")
ARTIFACT_ORDER = (
    "samples.json",
    "summary.md",
    "acceptance.json",
    "safety-scan.json",
    "manifest.json",
)
PRE_MANIFEST_ARTIFACTS = ARTIFACT_ORDER[:-1]

DIAGNOSTIC_COMPONENTS = (
    "access",
    "admission",
    "page-records",
    "readiness",
    "presentation",
    "catalogs",
    "managers",
    "template",
    "db",
    "total",
)
ROUTE_CLASSES = frozenset(
    {
        "character-document",
        "character-fetch",
        "session-character-document",
        "session-character-fragment",
        "non-character",
    }
)
OUTCOMES = frozenset(
    {
        "ok",
        "redirect",
        "access-denied",
        "not-found",
        "admission-503",
        "client-error",
        "server-error",
        "not-applicable",
    }
)


class ContractError(ValueError):
    """The fixed measurement or privacy contract was not satisfied."""


class EvidenceRefusal(RuntimeError):
    """The no-overwrite evidence envelope refused publication."""


def _filesystem_path(path: Path) -> str:
    """Return a literal Windows long-path spelling for local evidence I/O."""

    resolved = os.fspath(path)
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


@dataclass(frozen=True)
class ActorSpec:
    key: str
    role: str
    writable: bool


@dataclass(frozen=True)
class ViewportSpec:
    key: str
    width: int
    height: int
    javascript: bool


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    surface: str
    actor: str
    section: str
    viewport: str
    samples: int
    warmups: int = 0
    method: str = "GET"
    expected_statuses: tuple[int, ...] = (200,)
    zero_contract: str = "none"
    pressure_group: str = "none"


@dataclass(frozen=True)
class AttemptSpec:
    attempt_id: str
    scenario: str
    surface: str
    actor: str
    section: str
    viewport: str
    sample_phase: str
    sample_index: int
    method: str
    expected_statuses: tuple[int, ...]
    zero_contract: str
    pressure_group: str


ACTORS = (
    ActorSpec("dm", "dm", True),
    ActorSpec("assigned_player", "player", True),
    ActorSpec("unassigned_player", "player", False),
    ActorSpec("observer_primary", "observer", False),
    ActorSpec("observer_secondary", "observer", False),
)
ACTOR_KEYS = frozenset(actor.key for actor in ACTORS)

VIEWPORTS = (
    ViewportSpec("desktop", 1280, 900, True),
    ViewportSpec("mobile", 390, 800, True),
    ViewportSpec("no-js", 1280, 900, False),
)
VIEWPORT_KEYS = frozenset(viewport.key for viewport in VIEWPORTS)

DND_NORMAL_SECTIONS = (
    "quick",
    "spellcasting",
    "features",
    "equipment",
    "inventory",
    "notes",
    "controls",
)
DND_SESSION_SECTIONS = (
    "overview",
    "spells",
    "resources",
    "features",
    "equipment",
    "inventory",
    "notes",
)
XIANXIA_SECTIONS = (
    "quick",
    "martial_arts",
    "techniques",
    "resources",
    "skills",
    "equipment",
    "inventory",
    "notes",
)
SECTION_KEYS = frozenset((*DND_NORMAL_SECTIONS, *DND_SESSION_SECTIONS, *XIANXIA_SECTIONS, "root", "health"))

def _route_cells(
    key: str,
    surface: str,
    sections: Sequence[str],
    *,
    actor: str = "assigned_player",
    samples: int = 8,
    warmups: int = 1,
    zero_contract: str = "none",
) -> tuple[ScenarioSpec, ...]:
    return tuple(
        ScenarioSpec(
            key,
            surface,
            "dm" if section == "controls" else actor,
            section,
            "desktop",
            samples,
            warmups=warmups,
            zero_contract=zero_contract,
        )
        for section in sections
    )


REPRESENTATIVE_XIANXIA_NORMAL_SECTIONS = (
    "quick",
    "martial_arts",
    "resources",
    "inventory",
)
REPRESENTATIVE_XIANXIA_SESSION_SECTIONS = (
    "quick",
    "techniques",
    "resources",
    "inventory",
)

# Frozen Slice 0 schedule: one warmup and eight measured samples for every
# cold/network cell, twelve cache/ordinary rounds, six mutation operations,
# three deterministic overload rounds, and explicit desktop/mobile/no-JS roots.
SCENARIOS = (
    *_route_cells("normal_document", "normal-character", DND_NORMAL_SECTIONS),
    *_route_cells("normal_enhanced_section", "normal-character", DND_NORMAL_SECTIONS),
    *_route_cells(
        "normal_visited_return",
        "normal-character",
        DND_NORMAL_SECTIONS,
        samples=12,
        warmups=0,
        zero_contract="cache-no-network",
    ),
    ScenarioSpec("session_shell_first_switch", "session-shell", "assigned_player", "overview", "desktop", 8, warmups=1),
    *_route_cells("session_document", "session-character", DND_SESSION_SECTIONS),
    *_route_cells("session_section_fragment", "session-character-fragment", DND_SESSION_SECTIONS),
    *_route_cells(
        "session_section_cached_apply",
        "session-character",
        DND_SESSION_SECTIONS,
        samples=12,
        warmups=0,
        zero_contract="cache-no-network",
    ),
    ScenarioSpec("session_mutation_post", "session-character", "assigned_player", "resources", "desktop", 6, method="POST", expected_statuses=(302, 303)),
    ScenarioSpec("session_mutation_redirect_get", "session-character", "assigned_player", "resources", "desktop", 6),
    *_route_cells("xianxia_normal_document", "xianxia-normal", REPRESENTATIVE_XIANXIA_NORMAL_SECTIONS),
    *_route_cells("xianxia_session_document", "xianxia-session", REPRESENTATIVE_XIANXIA_SESSION_SECTIONS),
    *(
        ScenarioSpec(f"{system}_root_smoke", surface, actor, "root", viewport, 1)
        for system, surface, actor in (
            ("dnd_normal", "normal-character", "assigned_player"),
            ("dnd_session", "session-character", "assigned_player"),
            ("xianxia_normal", "xianxia-normal", "assigned_player"),
            ("xianxia_session", "xianxia-session", "assigned_player"),
        )
        for viewport in ("desktop", "mobile", "no-js")
    ),
    ScenarioSpec("ordinary_session_fragment", "session-character-fragment", "dm", "overview", "desktop", 12, pressure_group="ordinary"),
    ScenarioSpec("ordinary_normal_read", "normal-character", "assigned_player", "quick", "desktop", 12, pressure_group="ordinary"),
    ScenarioSpec("ordinary_normal_read", "normal-character", "unassigned_player", "inventory", "desktop", 12, pressure_group="ordinary"),
    ScenarioSpec("ordinary_combat_unchanged", "combat-live", "observer_primary", "health", "desktop", 12, zero_contract="unchanged-live", pressure_group="ordinary"),
    ScenarioSpec("ordinary_session_unchanged", "session-live", "observer_secondary", "health", "desktop", 12, zero_contract="unchanged-live", pressure_group="ordinary"),
    ScenarioSpec("overload_character_busy", "normal-character", "unassigned_player", "quick", "desktop", 3, expected_statuses=(503,), pressure_group="overload"),
    ScenarioSpec("overload_livez", "livez", "assigned_player", "health", "desktop", 3, pressure_group="overload"),
    ScenarioSpec("overload_readyz", "readyz", "observer_primary", "health", "desktop", 3, pressure_group="overload"),
    ScenarioSpec("overload_campaign", "campaign", "observer_secondary", "root", "desktop", 3, pressure_group="overload"),
    ScenarioSpec("overload_session_fragment", "session-character-fragment", "dm", "overview", "desktop", 3, pressure_group="overload"),
)
SCENARIO_KEYS = frozenset(scenario.key for scenario in SCENARIOS)


def build_attempt_schedule(scenarios: Sequence[ScenarioSpec] = SCENARIOS) -> tuple[AttemptSpec, ...]:
    attempts: list[AttemptSpec] = []
    seen_cells: set[tuple[str, str, str, str, str]] = set()
    for scenario in scenarios:
        cell = (scenario.key, scenario.surface, scenario.actor, scenario.section, scenario.viewport)
        if cell in seen_cells:
            raise ContractError(f"duplicate scenario cell: {scenario.key}")
        seen_cells.add(cell)
        if scenario.actor not in ACTOR_KEYS:
            raise ContractError(f"unknown actor for scenario: {scenario.key}")
        if scenario.viewport not in VIEWPORT_KEYS:
            raise ContractError(f"unknown viewport for scenario: {scenario.key}")
        if scenario.section not in SECTION_KEYS:
            raise ContractError(f"unknown section for scenario: {scenario.key}")
        if isinstance(scenario.samples, bool) or not isinstance(scenario.samples, int) or scenario.samples < 1:
            raise ContractError(f"invalid sample count for scenario: {scenario.key}")
        if isinstance(scenario.warmups, bool) or not isinstance(scenario.warmups, int) or scenario.warmups < 0:
            raise ContractError(f"invalid warmup count for scenario: {scenario.key}")
        if scenario.method not in {"GET", "POST"}:
            raise ContractError(f"invalid method for scenario: {scenario.key}")
        if scenario.zero_contract not in {"none", "cache-no-network", "unchanged-live"}:
            raise ContractError(f"invalid zero contract for scenario: {scenario.key}")
        phases = (("warmup", scenario.warmups), ("measured", scenario.samples))
        for sample_phase, phase_count in phases:
            for sample_index in range(1, phase_count + 1):
                attempts.append(
                    AttemptSpec(
                    attempt_id=(
                        f"{scenario.key}-{scenario.section}-{scenario.viewport}-"
                        f"{scenario.actor}-{sample_phase}-{sample_index:02d}"
                    ),
                    scenario=scenario.key,
                    surface=scenario.surface,
                    actor=scenario.actor,
                    section=scenario.section,
                    viewport=scenario.viewport,
                    sample_phase=sample_phase,
                    sample_index=sample_index,
                    method=scenario.method,
                    expected_statuses=scenario.expected_statuses,
                    zero_contract=scenario.zero_contract,
                    pressure_group=scenario.pressure_group,
                    )
                )
    identifiers = [attempt.attempt_id for attempt in attempts]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("attempt schedule contains duplicate identifiers")
    return tuple(attempts)


ATTEMPT_SCHEDULE = build_attempt_schedule()
ATTEMPT_BY_ID = {attempt.attempt_id: attempt for attempt in ATTEMPT_SCHEDULE}

RUNTIME_DND_CAMPAIGN = "linden-pass"
RUNTIME_DND_CHARACTER = "arden-march"
RUNTIME_XIANXIA_CAMPAIGN = "harness-xianxia"
RUNTIME_XIANXIA_CHARACTER = "measured-cultivator"
RENDER_GATE_HEADER = "X-Character-Read-Harness-Gate"
RENDER_GATE_HOLD_VALUE = "hold"
EXPECTED_BUSY_BODY_SHA256 = "a03571b102ef582d242a36982d45e6c37276bf9326a2f608f25979152f0eca50"


def strict_number(value: object, *, label: str, integer: bool = False) -> int | float:
    """Return a finite non-negative number, rejecting bools and coercion."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label} must be a JSON number")
    if not math.isfinite(float(value)) or value < 0:
        raise ContractError(f"{label} must be finite and non-negative")
    if integer and (not isinstance(value, int) or isinstance(value, bool)):
        raise ContractError(f"{label} must be an integer")
    return value


def linear_percentile(values: Iterable[int | float], percentile: int | float) -> float:
    """Compute the inclusive linear percentile used by the frozen contract."""

    pct = strict_number(percentile, label="percentile")
    if float(pct) > 100:
        raise ContractError("percentile must be at most 100")
    normalized = [float(strict_number(value, label="percentile sample")) for value in values]
    if not normalized:
        raise ContractError("percentile requires at least one sample")
    normalized.sort()
    position = (len(normalized) - 1) * float(pct) / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return normalized[lower]
    fraction = position - lower
    return normalized[lower] + ((normalized[upper] - normalized[lower]) * fraction)


def normalize_diagnostics(payload: Mapping[str, object]) -> dict[str, object]:
    """Strictly normalize already-parsed Character diagnostics.

    Raw headers never cross this boundary; callers provide semantic fields and
    receive only the fixed route/outcome enums and numeric measurements.
    """

    expected = {"route_class", "outcome", "query_count", "response_bytes", *DIAGNOSTIC_COMPONENTS}
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ContractError(f"diagnostic fields differ; missing={missing!r}; extra={extra!r}")
    route_class = payload["route_class"]
    outcome = payload["outcome"]
    if route_class not in ROUTE_CLASSES:
        raise ContractError("diagnostic route_class is not allowlisted")
    if outcome not in OUTCOMES:
        raise ContractError("diagnostic outcome is not allowlisted")
    result: dict[str, object] = {
        "route_class": route_class,
        "outcome": outcome,
        "query_count": strict_number(payload["query_count"], label="query_count", integer=True),
        "response_bytes": strict_number(payload["response_bytes"], label="response_bytes", integer=True),
    }
    for component in DIAGNOSTIC_COMPONENTS:
        result[component] = float(strict_number(payload[component], label=f"diagnostic {component}"))
    return result


def _required_header(headers: Mapping[str, str], name: str) -> str:
    expected = name.casefold()
    matches = [value for key, value in headers.items() if str(key).casefold() == expected]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0].strip():
        raise ContractError("required Character diagnostic header is absent or duplicated")
    return matches[0].strip()


def _header_number(headers: Mapping[str, str], name: str, *, integer: bool = False) -> int | float:
    raw = _required_header(headers, name)
    if integer:
        if not re.fullmatch(r"0|[1-9][0-9]*", raw):
            raise ContractError("Character diagnostic integer header is malformed")
        return strict_number(int(raw), label="Character diagnostic header", integer=True)
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", raw):
        raise ContractError("Character diagnostic numeric header is malformed")
    return strict_number(float(raw), label="Character diagnostic header")


def extract_character_diagnostics(headers: Mapping[str, str]) -> dict[str, object]:
    """Extract only allowlisted semantic values from an in-memory header map."""

    payload: dict[str, object] = {
        "route_class": _required_header(headers, "X-Character-Read-Route"),
        "outcome": _required_header(headers, "X-Character-Read-Outcome"),
        "query_count": _header_number(headers, "X-Character-Read-Query-Count", integer=True),
        "response_bytes": _header_number(headers, "X-Character-Read-Response-Bytes", integer=True),
    }
    for component in DIAGNOSTIC_COMPONENTS:
        header_component = "-".join(part.title() for part in component.split("-"))
        payload[component] = _header_number(
            headers,
            f"X-Character-Read-{header_component}-Ms",
        )
    normalized = normalize_diagnostics(payload)
    query_time_ms = float(_header_number(headers, "X-Character-Read-Query-Time-Ms"))
    if query_time_ms != float(normalized["db"]):
        raise ContractError("Character query-time and DB diagnostics differ")
    return {**normalized, "query_time_ms": query_time_ms}


SAMPLE_FIELDS = frozenset(
    {
        "attempt_id",
        "scenario",
        "surface",
        "actor",
        "section",
        "viewport",
        "sample_phase",
        "sample_index",
        "method",
        "status_code",
        "unexpected_error",
        "expected_503",
        "network_request_count",
        "request_ms",
        "navigation_ms",
        "fetch_ms",
        "apply_ms",
        "server_ms",
        "query_count",
        "query_time_ms",
        "response_bytes",
        "route_class",
        "outcome",
        "changed",
        "rss_bytes",
        "peak_rss_bytes",
        *(f"{component.replace('-', '_')}_ms" for component in DIAGNOSTIC_COMPONENTS),
    }
)


def process_memory_snapshot() -> dict[str, int]:
    """Return current and peak process memory without adding a dependency."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = (
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            )

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.argtypes = ()
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        )
        get_process_memory_info.restype = wintypes.BOOL
        process = get_current_process()
        succeeded = get_process_memory_info(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        if not succeeded:
            raise ContractError("process memory sampler failed")
        return {
            "rss_bytes": int(counters.WorkingSetSize),
            "peak_rss_bytes": int(counters.PeakWorkingSetSize),
        }
    import resource

    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    multiplier = 1 if platform.system().lower() == "darwin" else 1024
    return {"rss_bytes": peak * multiplier, "peak_rss_bytes": peak * multiplier}


def build_sample(
    attempt: AttemptSpec,
    *,
    status_code: int,
    network_request_count: int,
    request_ms: int | float,
    navigation_ms: int | float = 0.0,
    fetch_ms: int | float = 0.0,
    apply_ms: int | float = 0.0,
    diagnostics: Mapping[str, object] | None = None,
    query_time_ms: int | float | None = None,
    changed: bool = True,
    memory: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the exact allowlisted retained record for one planned attempt."""

    status = classify_status(attempt, status_code)
    if not isinstance(changed, bool):
        raise ContractError("sample changed flag must be boolean")
    safe_diagnostics = dict(diagnostics or {})
    if diagnostics is None:
        safe_diagnostics = {
            "route_class": "non-character",
            "outcome": "not-applicable",
            "query_count": 0,
            "response_bytes": 0,
            "query_time_ms": 0.0,
            **{component: 0.0 for component in DIAGNOSTIC_COMPONENTS},
        }
    expected_diagnostic_fields = {
        "route_class",
        "outcome",
        "query_count",
        "response_bytes",
        "query_time_ms",
        *DIAGNOSTIC_COMPONENTS,
    }
    if set(safe_diagnostics) != expected_diagnostic_fields:
        raise ContractError("sample diagnostics differ from the retained allowlist")
    normalized = normalize_diagnostics(
        {key: value for key, value in safe_diagnostics.items() if key != "query_time_ms"}
    )
    normalized_query_time = float(
        strict_number(
            safe_diagnostics["query_time_ms"] if query_time_ms is None else query_time_ms,
            label="query_time_ms",
        )
    )
    resolved_memory = dict(memory or process_memory_snapshot())
    if set(resolved_memory) != {"rss_bytes", "peak_rss_bytes"}:
        raise ContractError("process memory fields differ from the retained allowlist")
    sample: dict[str, object] = {
        "attempt_id": attempt.attempt_id,
        "scenario": attempt.scenario,
        "surface": attempt.surface,
        "actor": attempt.actor,
        "section": attempt.section,
        "viewport": attempt.viewport,
        "sample_phase": attempt.sample_phase,
        "sample_index": attempt.sample_index,
        "method": attempt.method,
        "status_code": status["status_code"],
        "unexpected_error": status["unexpected_error"],
        "expected_503": status["expected_503"],
        "network_request_count": strict_number(
            network_request_count,
            label="network_request_count",
            integer=True,
        ),
        "request_ms": float(strict_number(request_ms, label="request_ms")),
        "navigation_ms": float(strict_number(navigation_ms, label="navigation_ms")),
        "fetch_ms": float(strict_number(fetch_ms, label="fetch_ms")),
        "apply_ms": float(strict_number(apply_ms, label="apply_ms")),
        "server_ms": float(normalized["total"]),
        "query_count": normalized["query_count"],
        "query_time_ms": normalized_query_time,
        "response_bytes": normalized["response_bytes"],
        "route_class": normalized["route_class"],
        "outcome": normalized["outcome"],
        "changed": changed,
        "rss_bytes": strict_number(resolved_memory["rss_bytes"], label="rss_bytes", integer=True),
        "peak_rss_bytes": strict_number(
            resolved_memory["peak_rss_bytes"],
            label="peak_rss_bytes",
            integer=True,
        ),
    }
    for component in DIAGNOSTIC_COMPONENTS:
        sample[f"{component.replace('-', '_')}_ms"] = float(normalized[component])
    if set(sample) != SAMPLE_FIELDS:
        raise ContractError("retained sample fields differ from the fixed allowlist")
    enforce_semantic_zero(attempt, sample)
    require_privacy_clean(sample)
    return sample


def build_unchanged_live_sample(
    attempt: AttemptSpec,
    result: Mapping[str, object],
    *,
    memory: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Discard live revision/token/raw timing values and retain numeric work."""

    required = {
        "changed",
        "requestMs",
        "applyMs",
        "payloadBytes",
        "queryCount",
        "queryTimeMs",
        "requestTimeMs",
    }
    if not required.issubset(result):
        raise ContractError("live sampler omitted required semantic fields")
    if result["changed"] is not False:
        raise ContractError("ordinary live sampler was not unchanged")
    request_ms = float(strict_number(result["requestMs"], label="live requestMs"))
    apply_ms = float(strict_number(result["applyMs"], label="live applyMs"))
    payload_bytes = strict_number(
        result["payloadBytes"],
        label="live payloadBytes",
        integer=True,
    )
    query_count = strict_number(
        result["queryCount"],
        label="live queryCount",
        integer=True,
    )
    query_time_ms = float(strict_number(result["queryTimeMs"], label="live queryTimeMs"))
    server_ms = float(strict_number(result["requestTimeMs"], label="live requestTimeMs"))
    diagnostics: dict[str, object] = {
        "route_class": "non-character",
        "outcome": "not-applicable",
        "query_count": query_count,
        "response_bytes": payload_bytes,
        "query_time_ms": query_time_ms,
        **{component: 0.0 for component in DIAGNOSTIC_COMPONENTS},
    }
    diagnostics["db"] = query_time_ms
    diagnostics["total"] = server_ms
    return build_sample(
        attempt,
        status_code=200,
        network_request_count=1,
        request_ms=request_ms,
        fetch_ms=request_ms,
        apply_ms=apply_ms,
        diagnostics=diagnostics,
        changed=False,
        memory=memory,
    )


def validate_expected_busy_response(
    status_code: object,
    headers: Mapping[str, str],
    body: str,
    *,
    private_markers: Sequence[str] = (),
) -> dict[str, object]:
    """Validate the real generic private admission response entirely in memory."""

    if strict_number(status_code, label="busy status", integer=True) != 503:
        raise ContractError("overload did not exercise the real admission 503")
    if _required_header(headers, "Retry-After") != "2":
        raise ContractError("busy response retry interval differs")
    cache_control = _required_header(headers, "Cache-Control").casefold()
    cache_directives = tuple(part.strip() for part in cache_control.split(","))
    if len(cache_directives) != 2 or set(cache_directives) != {"private", "no-store"}:
        raise ContractError("busy response is not private no-store")
    diagnostics = extract_character_diagnostics(headers)
    if (
        diagnostics["route_class"] != "character-document"
        or diagnostics["outcome"] != "admission-503"
    ):
        raise ContractError("busy response diagnostics differ")
    if not isinstance(body, str):
        raise ContractError("busy response body could not be checked")
    normalized_body = body.casefold()
    for phrase in ("character pages are busy", "try opening this character section again"):
        if phrase not in normalized_body:
            raise ContractError("busy response generic copy differs")
    for marker in private_markers:
        if marker and marker.casefold() in normalized_body:
            raise ContractError("busy response exposed a private fixture marker")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != EXPECTED_BUSY_BODY_SHA256:
        raise ContractError("busy response generic body differs")
    return diagnostics


def classify_status(attempt: AttemptSpec, status_code: object) -> dict[str, object]:
    status = strict_number(status_code, label="status_code", integer=True)
    expected = status in attempt.expected_statuses
    expected_503 = status == 503 and attempt.scenario == "overload_character_busy" and attempt.surface == "normal-character"
    if status == 503 and not expected_503:
        expected = False
    return {
        "status_code": status,
        "expected": bool(expected),
        "expected_503": bool(expected_503),
        "unexpected_error": not bool(expected),
    }


SEMANTIC_ZERO_FIELDS = (
    "network_request_count",
    "server_ms",
    "query_count",
    "query_time_ms",
    "response_bytes",
)


def enforce_semantic_zero(attempt: AttemptSpec, sample: Mapping[str, object]) -> None:
    if attempt.zero_contract == "none":
        return
    fields = SEMANTIC_ZERO_FIELDS if attempt.zero_contract == "cache-no-network" else ("apply_ms",)
    if attempt.zero_contract == "unchanged-live" and sample.get("changed") is not False:
        raise ContractError("unchanged-live attempt reported changed work")
    for field in fields:
        value = strict_number(sample.get(field), label=f"semantic-zero {field}")
        if float(value) != 0.0:
            raise ContractError(f"semantic-zero attempt performed {field}")


def validate_attempt_ledger(
    samples: Sequence[Mapping[str, object]],
    schedule: Sequence[AttemptSpec] = ATTEMPT_SCHEDULE,
) -> tuple[Mapping[str, object], ...]:
    expected = {attempt.attempt_id: attempt for attempt in schedule}
    observed: dict[str, Mapping[str, object]] = {}
    duplicates: list[str] = []
    for sample in samples:
        if set(sample) != SAMPLE_FIELDS:
            raise ContractError("retained sample fields differ from the fixed allowlist")
        attempt_id = sample.get("attempt_id")
        if not isinstance(attempt_id, str):
            raise ContractError("every sample needs a string attempt_id")
        if attempt_id in observed:
            duplicates.append(attempt_id)
        observed[attempt_id] = sample
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if duplicates or missing or extra:
        raise ContractError(
            f"attempt ledger differs; missing={missing!r}; extra={extra!r}; duplicates={sorted(set(duplicates))!r}"
        )
    ordered: list[Mapping[str, object]] = []
    for attempt in schedule:
        sample = observed[attempt.attempt_id]
        for field in ("scenario", "surface", "actor", "section", "viewport", "sample_phase", "sample_index", "method"):
            if sample.get(field) != getattr(attempt, field):
                raise ContractError(f"attempt {attempt.attempt_id} changed fixed field {field}")
        status = classify_status(attempt, sample.get("status_code"))
        if sample.get("unexpected_error") is not status["unexpected_error"]:
            raise ContractError(f"attempt {attempt.attempt_id} has inconsistent error classification")
        if sample.get("expected_503") is not status["expected_503"]:
            raise ContractError(f"attempt {attempt.attempt_id} has inconsistent expected-503 classification")
        enforce_semantic_zero(attempt, sample)
        require_privacy_clean(sample)
        ordered.append(sample)
    return tuple(ordered)


def validate_mutation_ledger(entries: Sequence[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    if len(entries) != 2:
        raise ContractError("mutation ledger must contain the POST and its separate redirected GET")
    post, redirected_get = entries
    if post.get("scenario") != "session_mutation_post" or post.get("method") != "POST":
        raise ContractError("mutation ledger must begin with the fixed POST attempt")
    if redirected_get.get("scenario") != "session_mutation_redirect_get" or redirected_get.get("method") != "GET":
        raise ContractError("mutation ledger must end with a separate redirected GET")
    if post.get("attempt_id") == redirected_get.get("attempt_id"):
        raise ContractError("mutation POST and redirected GET must be separate attempts")
    if post.get("sample_index") != redirected_get.get("sample_index"):
        raise ContractError("mutation POST and redirected GET operation indexes differ")
    post_status = strict_number(post.get("status_code"), label="mutation POST status", integer=True)
    get_status = strict_number(redirected_get.get("status_code"), label="redirected GET status", integer=True)
    if post_status not in {302, 303} or get_status != 200:
        raise ContractError("mutation redirect chain has an unexpected status")
    if sum(1 for entry in entries if entry.get("method") == "POST") != 1:
        raise ContractError("mutation ledger must contain exactly one POST")
    return tuple(entries)


_FORBIDDEN_KEYS = frozenset(
    {
        "url",
        "uri",
        "host",
        "hostname",
        "ip",
        "path",
        "campaign_slug",
        "character_slug",
        "name",
        "display_name",
        "email",
        "cookie",
        "cookies",
        "authorization",
        "auth",
        "csrf",
        "session_id",
        "headers",
        "raw_headers",
        "html",
        "body",
        "console",
        "exception",
        "error_text",
    }
)
_PRIVATE_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("url", re.compile(r"\b(?:https?|wss?)://", re.IGNORECASE)),
    ("ipv4", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")),
    ("windows-path", re.compile(r"\b[A-Za-z]:[\\/]")),
    ("cookie", re.compile(r"\b(?:set-cookie|cookie|bearer|csrf|sessionid)\b", re.IGNORECASE)),
    (
        "fixture-identity",
        re.compile(
            r"\b(?:linden-pass|arden-march|selene-brook|tobin-slate|"
            r"harness-xianxia|measured-cultivator|measured cultivator|"
            r"echoes of the alloy coast|synthetic xianxia measurement)\b",
            re.IGNORECASE,
        ),
    ),
)


def privacy_findings(value: object, *, location: str = "root") -> tuple[dict[str, str], ...]:
    """Return semantic finding codes without echoing sensitive source text."""

    findings: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                findings.append({"code": "non-string-key", "location": location})
                continue
            child_location = f"{location}.{key}"
            if key.lower() in _FORBIDDEN_KEYS:
                findings.append({"code": "forbidden-field", "location": child_location})
            findings.extend(privacy_findings(child, location=child_location))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            findings.extend(privacy_findings(child, location=f"{location}.{index}"))
    elif isinstance(value, str):
        for code, pattern in _PRIVATE_PATTERNS:
            if pattern.search(value):
                findings.append({"code": code, "location": location})
    elif value is not None and not isinstance(value, (bool, int, float)):
        findings.append({"code": "unsupported-value", "location": location})
    return tuple(findings)


def require_privacy_clean(value: object) -> None:
    findings = privacy_findings(value)
    if findings:
        codes = sorted({finding["code"] for finding in findings})
        raise ContractError(f"privacy scan failed with semantic codes: {codes!r}")


def _run_git(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", os.fspath(repo_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )


def require_clean_detached_git_identity(
    repo_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run_git,
) -> dict[str, str]:
    """Require an exact registered, clean, detached worktree identity."""

    root = repo_root.resolve(strict=True)

    def run(*arguments: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
        result = runner(root, *arguments)
        if result.returncode not in ok:
            raise ContractError(f"git identity command failed: {arguments[0]}")
        return result

    top = Path(run("rev-parse", "--show-toplevel").stdout.strip()).resolve(strict=True)
    if top != root:
        raise ContractError("evidence root is not the exact Git top-level")
    symbolic = run("symbolic-ref", "-q", "HEAD", ok=(0, 1))
    if symbolic.returncode == 0 or symbolic.stdout.strip():
        raise ContractError("baseline collection requires detached HEAD")
    status = run("status", "--porcelain=v1", "--untracked-files=all").stdout
    if status:
        raise ContractError("baseline collection requires a clean worktree")
    commit = run("rev-parse", "HEAD").stdout.strip()
    tree = run("rev-parse", "HEAD^{tree}").stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit) or not re.fullmatch(r"[0-9a-f]{40,64}", tree):
        raise ContractError("Git identity is malformed")
    worktrees = run("worktree", "list", "--porcelain").stdout.splitlines()
    registered = {
        Path(line.removeprefix("worktree ")).resolve(strict=True)
        for line in worktrees
        if line.startswith("worktree ")
    }
    if root not in registered:
        raise ContractError("baseline collection requires a registered worktree")
    return {"commit": commit, "tree": tree, "checkout": "detached-clean-registered"}


def require_unchanged_git_identity(
    repo_root: Path,
    initial_identity: Mapping[str, str],
    *,
    checker: Callable[[Path], Mapping[str, str]] = require_clean_detached_git_identity,
) -> dict[str, str]:
    """Recheck the publish-boundary commit/tree and require exact equality."""

    current_identity = dict(checker(repo_root))
    if current_identity != dict(initial_identity):
        raise ContractError("candidate Git identity changed before publication")
    return current_identity


_WINDOWS_RESERVED_COMPONENTS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_WINDOWS_FORBIDDEN_COMPONENT = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')


def _normalized_fixture_relative_path(
    tracked_path: str,
    fixture_prefix: str,
) -> PurePosixPath:
    """Return one canonical, cross-platform-safe tracked fixture path."""

    if not isinstance(tracked_path, str) or not isinstance(fixture_prefix, str):
        raise ContractError("Git-object fixture path is not text")
    if "\\" in tracked_path or "\\" in fixture_prefix:
        raise ContractError("Git-object fixture path uses a Windows separator")
    if unicodedata.normalize("NFC", tracked_path) != tracked_path:
        raise ContractError("Git-object fixture path is not Unicode-canonical")
    tracked = PurePosixPath(tracked_path)
    prefix = PurePosixPath(fixture_prefix)
    if (
        tracked.is_absolute()
        or prefix.is_absolute()
        or tracked.as_posix() != tracked_path
        or prefix.as_posix() != fixture_prefix
    ):
        raise ContractError("Git-object fixture path is not canonical")
    try:
        relative = tracked.relative_to(prefix)
    except ValueError as exc:
        raise ContractError("Git-object fixture escaped its prefix") from exc
    if not relative.parts:
        raise ContractError("Git-object fixture has an empty relative name")
    for component in (*prefix.parts, *relative.parts):
        if component in {"", ".", ".."} or component.rstrip(" .") != component:
            raise ContractError("Git-object fixture has an unsafe relative name")
        if unicodedata.normalize("NFC", component) != component:
            raise ContractError("Git-object fixture path is not Unicode-canonical")
        if _WINDOWS_FORBIDDEN_COMPONENT.search(component):
            raise ContractError("Git-object fixture has a Windows-unsafe component")
        if component.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_COMPONENTS:
            raise ContractError("Git-object fixture has a reserved device component")
    return relative


def _update_fixture_digest_path(digest: Any, relative: PurePosixPath) -> None:
    digest.update(relative.as_posix().encode("utf-8"))
    digest.update(b"\0")


def prove_git_object_fixture(
    repo_root: Path,
    *,
    fixture_prefix: str = "tests/fixtures/sample_campaigns/linden-pass",
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run_git,
) -> dict[str, object]:
    """Prove the sample fixture from HEAD tree entries, never working-tree bytes."""

    root = repo_root.resolve(strict=True)
    listing = runner(root, "ls-tree", "-r", "-z", "HEAD", "--", fixture_prefix)
    if listing.returncode != 0:
        raise ContractError("Git-object fixture listing failed")
    raw = listing.stdout
    entries = [entry for entry in raw.split("\0") if entry]
    if not entries:
        raise ContractError("Git-object sample fixture is empty")
    digest = hashlib.sha256()
    file_count = 0
    for entry in entries:
        metadata, separator, tracked_path = entry.partition("\t")
        parts = metadata.split()
        if not separator or len(parts) != 3 or parts[1] != "blob":
            raise ContractError("Git-object fixture contains a non-blob entry")
        mode, _kind, object_id = parts
        if mode not in {"100644", "100755"} or not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
            raise ContractError("Git-object fixture metadata is malformed")
        relative = _normalized_fixture_relative_path(tracked_path, fixture_prefix)
        blob = runner(root, "cat-file", "-e", f"{object_id}^{{blob}}")
        if blob.returncode != 0:
            raise ContractError("Git-object fixture blob proof failed")
        digest.update(mode.encode("ascii"))
        digest.update(b"\0")
        digest.update(object_id.encode("ascii"))
        digest.update(b"\0")
        _update_fixture_digest_path(digest, relative)
        file_count += 1
    return {
        "fixture": "sample-dnd5e",
        "source": "git-object",
        "file_count": file_count,
        "fixture_digest": digest.hexdigest(),
    }


def _run_git_bytes(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", os.fspath(repo_root), *arguments],
        check=False,
        capture_output=True,
    )


def materialize_git_object_fixture(
    repo_root: Path,
    destination: Path,
    *,
    fixture_prefix: str = "tests/fixtures/sample_campaigns/linden-pass",
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = _run_git_bytes,
) -> dict[str, object]:
    """Materialize only HEAD blobs under the sanitized sample-fixture tree."""

    root = repo_root.resolve(strict=True)
    destination = Path(os.path.abspath(os.fspath(destination)))
    if os.path.lexists(_filesystem_path(destination)):
        raise ContractError("runtime Git-object fixture destination already exists")
    listing = runner(root, "ls-tree", "-r", "-z", "HEAD", "--", fixture_prefix)
    if listing.returncode != 0:
        raise ContractError("runtime Git-object fixture listing failed")
    entries = [entry for entry in listing.stdout.split(b"\0") if entry]
    if not entries:
        raise ContractError("runtime Git-object fixture is empty")
    destination_physical = destination.resolve(strict=False)
    planned: list[tuple[str, str, PurePosixPath, Path, bytes]] = []
    seen_relative_names: set[str] = set()
    for entry in entries:
        metadata, separator, raw_tracked_path = entry.partition(b"\t")
        parts = metadata.split()
        if not separator or len(parts) != 3 or parts[1] != b"blob":
            raise ContractError("runtime Git-object fixture contains a non-blob entry")
        mode = parts[0].decode("ascii")
        object_id = parts[2].decode("ascii")
        tracked_path = raw_tracked_path.decode("utf-8", errors="strict")
        relative = _normalized_fixture_relative_path(tracked_path, fixture_prefix)
        normalized_name = relative.as_posix().casefold()
        if normalized_name in seen_relative_names:
            raise ContractError("runtime Git-object fixture has duplicate path topology")
        seen_relative_names.add(normalized_name)
        if mode not in {"100644", "100755"} or not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
            raise ContractError("runtime Git-object fixture metadata is malformed")
        blob = runner(root, "cat-file", "blob", object_id)
        if blob.returncode != 0:
            raise ContractError("runtime Git-object fixture blob read failed")
        target = destination_physical.joinpath(*relative.parts).resolve(strict=False)
        if not target.is_relative_to(destination_physical):
            raise ContractError("runtime Git-object fixture target escaped its destination")
        planned.append((mode, object_id, relative, target, blob.stdout))

    # Every target is parsed, normalized, and contained before the fresh root
    # is created. Recheck immediately before each filesystem write as defense
    # against a changed ancestor.
    os.makedirs(_filesystem_path(destination_physical), exist_ok=False)
    digest = hashlib.sha256()
    for mode, object_id, relative, target, payload in planned:
        target = target.resolve(strict=False)
        if not target.is_relative_to(destination_physical):
            raise ContractError("runtime Git-object fixture target escaped its destination")
        os.makedirs(_filesystem_path(target.parent), exist_ok=True)
        with open(_filesystem_path(target), "xb") as stream:
            stream.write(payload)
        digest.update(mode.encode("ascii"))
        digest.update(b"\0")
        digest.update(object_id.encode("ascii"))
        digest.update(b"\0")
        _update_fixture_digest_path(digest, relative)
        digest.update(hashlib.sha256(payload).digest())
    return {
        "fixture": "sample-dnd5e",
        "source": "git-object",
        "file_count": len(planned),
        "materialized_digest": digest.hexdigest(),
    }


def create_runtime_xianxia_fixture(campaigns_dir: Path) -> dict[str, object]:
    """Create a synthetic Xianxia campaign only inside the runtime temp tree."""

    import yaml

    from player_wiki.xianxia_character_importer import build_xianxia_manual_import_character

    campaign_root = campaigns_dir / RUNTIME_XIANXIA_CAMPAIGN
    character_root = campaign_root / "characters" / RUNTIME_XIANXIA_CHARACTER
    for relative in ("content", "assets", "characters"):
        os.makedirs(_filesystem_path(campaign_root / relative), exist_ok=True)
    os.makedirs(_filesystem_path(character_root), exist_ok=False)
    campaign_payload = {
        "title": "Synthetic Xianxia Measurement",
        "slug": RUNTIME_XIANXIA_CAMPAIGN,
        "summary": "Runtime-only synthetic measurement fixture.",
        "system": "Xianxia",
        "current_session": 1,
        "player_content_dir": "content",
        "asset_dir": "assets",
        "character_dir": "characters",
        "systems_library": "Xianxia",
        "systems_sources": [
            {
                "source_id": "XIANXIA-HOMEBREW",
                "enabled": True,
                "default_visibility": "players",
            }
        ],
    }
    character_payload = {
        "campaign_slug": RUNTIME_XIANXIA_CAMPAIGN,
        "character_slug": RUNTIME_XIANXIA_CHARACTER,
        "name": "Measured Cultivator",
        "realm": "Mortal",
        "honor": "Honorable",
        "attribute_str": 3,
        "attribute_dex": 0,
        "attribute_con": 3,
        "attribute_int": 0,
        "attribute_wis": 0,
        "attribute_cha": 0,
        "effort_basic": 3,
        "effort_weapon": 1,
        "effort_guns_explosive": 0,
        "effort_magic": 1,
        "effort_ultimate": 0,
        "energy_jing_max": 1,
        "energy_qi_max": 1,
        "energy_shen_max": 1,
        "trained_skills_text": "Tea Ceremony\nCalligraphy\nFishing",
        "martial_art_1_name": "Measured Palm",
        "martial_art_1_rank": "Initiate",
        "inventory_text": "Training staff | 1 | weapon | Runtime only",
    }
    definition, import_metadata, _initial_state = build_xianxia_manual_import_character(
        character_payload,
        campaign_slug=RUNTIME_XIANXIA_CAMPAIGN,
        imported_at_utc="2000-01-01T00:00:00+00:00",
    )

    def write_yaml(path: Path, payload: Mapping[str, object]) -> None:
        encoded = yaml.safe_dump(dict(payload), sort_keys=False).encode("utf-8")
        with open(_filesystem_path(path), "xb") as stream:
            stream.write(encoded)

    write_yaml(campaign_root / "campaign.yaml", campaign_payload)
    write_yaml(character_root / "definition.yaml", definition.to_dict())
    write_yaml(character_root / "import.yaml", import_metadata.to_dict())
    return {"fixture": "synthetic-xianxia", "source": "runtime-only", "character_count": 1}


@dataclass(frozen=True)
class RuntimeActorCredential:
    actor: str
    email: str
    password: str


@dataclass(frozen=True)
class RuntimeBootstrap:
    app: Any
    credentials: Mapping[str, RuntimeActorCredential]
    fixture_proof: Mapping[str, object]
    xianxia_proof: Mapping[str, object]


def assert_candidate_import_boundary(
    repo_root: Path = SCRIPT_REPO_ROOT,
    *,
    finder: Callable[[str], Any] = importlib.util.find_spec,
) -> None:
    """Refuse runtime imports unless ``player_wiki`` resolves inside this candidate."""

    root = repo_root.resolve(strict=True)
    _bind_repo_root_first(root)
    if Path(sys.path[0]).resolve(strict=True) != root:
        raise ContractError("candidate repository is not first on the import path")
    package_root = (root / "player_wiki").resolve(strict=True)

    def require_candidate_origin(origin: object) -> None:
        if not isinstance(origin, str):
            raise ContractError("candidate player_wiki package could not be resolved")
        try:
            resolved_origin = Path(origin).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ContractError("candidate player_wiki package could not be resolved") from None
        if not resolved_origin.is_relative_to(package_root):
            raise ContractError("player_wiki resolved outside the exact candidate")

    for module_name, module in tuple(sys.modules.items()):
        if module_name != "player_wiki" and not module_name.startswith("player_wiki."):
            continue
        module_origin = getattr(module, "__file__", None)
        if not isinstance(module_origin, str):
            module_origin = getattr(getattr(module, "__spec__", None), "origin", None)
        require_candidate_origin(module_origin)

    spec = finder("player_wiki")
    require_candidate_origin(getattr(spec, "origin", None))


def bootstrap_runtime_app(repo_root: Path, runtime_root: Path) -> RuntimeBootstrap:
    """Build the isolated app, DB, actors, assignments, and active sessions."""

    assert_candidate_import_boundary(repo_root)

    from werkzeug.security import generate_password_hash

    from player_wiki.app import create_app
    from player_wiki.auth_store import AuthStore
    from player_wiki.config import Config
    from player_wiki.db import init_database

    campaigns_dir = runtime_root / "campaigns"
    os.makedirs(_filesystem_path(campaigns_dir), exist_ok=False)
    fixture_proof = materialize_git_object_fixture(
        repo_root,
        campaigns_dir / RUNTIME_DND_CAMPAIGN,
    )
    xianxia_proof = create_runtime_xianxia_fixture(campaigns_dir)
    database_path = runtime_root / "runtime.sqlite3"

    Config.APP_ENV = "testing"
    Config.TESTING = False
    Config.DEBUG = False
    Config.CAMPAIGNS_DIR = campaigns_dir
    Config.DB_PATH = database_path
    Config.SECRET_KEY = "runtime-only-character-read-secret"
    Config.LIVE_DIAGNOSTICS = True
    Config.REQUEST_TRAIL_ENABLED = False
    Config.RELOAD_CONTENT = False
    Config.CONTENT_SCAN_INTERVAL_SECONDS = 3600
    Config.CHARACTER_READ_MAX_CONCURRENT_RENDERS = 2

    app = create_app()
    app.logger.disabled = True
    app.config.update(
        TESTING=False,
        DEBUG=False,
        DB_PATH=database_path,
        CAMPAIGNS_DIR=campaigns_dir,
        LIVE_DIAGNOSTICS=True,
        REQUEST_TRAIL_ENABLED=False,
        RELOAD_CONTENT=False,
        CHARACTER_READ_MAX_CONCURRENT_RENDERS=2,
    )
    password = "runtime-character-read-password"
    password_hash = generate_password_hash(password)
    credentials: dict[str, RuntimeActorCredential] = {}
    with app.app_context():
        init_database()
        store = AuthStore()
        users: dict[str, Any] = {}
        for index, actor in enumerate(ACTORS, start=1):
            email = f"actor-{index}@measurement.invalid"
            user = store.create_user(
                email,
                f"Measurement Actor {index}",
                status="active",
                password_hash=password_hash,
            )
            users[actor.key] = user
            credentials[actor.key] = RuntimeActorCredential(actor.key, email, password)
            for campaign_slug in (RUNTIME_DND_CAMPAIGN, RUNTIME_XIANXIA_CAMPAIGN):
                store.upsert_membership(user.id, campaign_slug, role=actor.role)
        assigned_user = users["assigned_player"]
        store.upsert_character_assignment(
            assigned_user.id,
            RUNTIME_DND_CAMPAIGN,
            RUNTIME_DND_CHARACTER,
        )
        store.upsert_character_assignment(
            assigned_user.id,
            RUNTIME_XIANXIA_CAMPAIGN,
            RUNTIME_XIANXIA_CHARACTER,
        )
        # Normal Character is party-readable, while Session Character editing
        # remains assignment-aware.  Session and Combat live reads are public
        # only inside this disposable fixture so observer actors exercise their
        # read-only authorization lane without becoming writable players.
        for campaign_slug in (RUNTIME_DND_CAMPAIGN, RUNTIME_XIANXIA_CAMPAIGN):
            store.upsert_campaign_visibility_setting(
                campaign_slug,
                "characters",
                visibility="players",
                updated_by_user_id=users["dm"].id,
            )
            for scope in ("session", "combat"):
                store.upsert_campaign_visibility_setting(
                    campaign_slug,
                    scope,
                    visibility="public",
                    updated_by_user_id=users["dm"].id,
                )
        systems_service = app.extensions["systems_service"]
        systems_service.ensure_builtin_library_seeded("DND-5E")
        systems_service.ensure_builtin_library_seeded("Xianxia")
        session_service = app.extensions["campaign_session_service"]
        dm_id = users["dm"].id
        session_service.begin_session(RUNTIME_DND_CAMPAIGN, started_by_user_id=dm_id)
        session_service.begin_session(RUNTIME_XIANXIA_CAMPAIGN, started_by_user_id=dm_id)
    return RuntimeBootstrap(
        app=app,
        credentials=credentials,
        fixture_proof=fixture_proof,
        xianxia_proof=xianxia_proof,
    )


class QuietWSGIRequestHandler:
    """Factory shim replaced with Werkzeug's handler at server construction."""


class FourWorkerWSGIServer:
    """One accepting server thread dispatching to exactly four worker threads."""

    worker_count = 4
    acceptor_count = 1

    def __init__(self, app: Any) -> None:
        from werkzeug.serving import BaseWSGIServer, WSGIRequestHandler

        class QuietHandler(WSGIRequestHandler):
            def log_request(self, code: object = "-", size: object = "-") -> None:
                return None

            def log_error(self, format: str, *args: object) -> None:
                return None

        class Server(BaseWSGIServer):
            request_queue_size = 8
            multithread = True

            def __init__(inner_self) -> None:
                inner_self._executor = ThreadPoolExecutor(
                    max_workers=FourWorkerWSGIServer.worker_count,
                    thread_name_prefix="character-read-worker",
                )
                super().__init__("127.0.0.1", 0, app, handler=QuietHandler)

            def process_request(inner_self, request: object, client_address: object) -> None:
                inner_self._executor.submit(
                    inner_self._process_request,
                    request,
                    client_address,
                )

            def _process_request(inner_self, request: object, client_address: object) -> None:
                try:
                    inner_self.finish_request(request, client_address)
                except BaseException:
                    inner_self.handle_error(request, client_address)
                finally:
                    inner_self.shutdown_request(request)

            def server_close(inner_self) -> None:
                super().server_close()
                inner_self._executor.shutdown(wait=True, cancel_futures=True)

        self._server = Server()
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="character-read-acceptor",
            daemon=True,
        )
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"
        self._started = False

    def start(self) -> None:
        if self._started:
            raise ContractError("bounded server was started more than once")
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._server.shutdown()
        self._thread.join(timeout=10)
        self._server.server_close()
        if self._thread.is_alive():
            raise ContractError("bounded server acceptor did not stop")
        self._started = False


class HarnessRenderGate:
    """Harness-only render gate used to occupy both real admission slots."""

    def __init__(self, render_character_page: Callable[..., object]) -> None:
        self._render_character_page = render_character_page
        self._condition = threading.Condition()
        self._release = threading.Event()
        self._armed = False
        self._entered = 0

    def arm(self) -> None:
        with self._condition:
            if self._armed:
                raise ContractError("render gate is already armed")
            self._entered = 0
            self._release.clear()
            self._armed = True

    def wait_for_two(self, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._entered < 2:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def release(self) -> None:
        self._release.set()

    def disarm(self) -> None:
        with self._condition:
            self._armed = False
            self._entered = 0
            self._release.clear()

    def __call__(self, *args: object, **kwargs: object) -> object:
        from flask import request

        should_hold = self._armed and request.headers.get(RENDER_GATE_HEADER) == RENDER_GATE_HOLD_VALUE
        if should_hold:
            with self._condition:
                self._entered += 1
                self._condition.notify_all()
            if not self._release.wait(timeout=30):
                raise ContractError("render gate release timed out")
        return self._render_character_page(*args, **kwargs)


def install_harness_render_gate(app: Any) -> HarnessRenderGate:
    dependencies = app.extensions["character_read_route_dependencies"]
    gate = HarnessRenderGate(dependencies.render_character_page)
    app.extensions["character_read_route_dependencies"] = replace(
        dependencies,
        render_character_page=gate,
    )
    return gate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(_filesystem_path(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _numeric_version_components(value: object, *, label: str) -> list[int]:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", value):
        raise ContractError(f"{label} is not an exact numeric release")
    return [int(component) for component in value.split(".")]


def browser_environment_identity(
    playwright_release: object,
    chromium_release: object,
    chromium_executable: Path,
) -> dict[str, object]:
    executable = chromium_executable.resolve(strict=True)
    identity: dict[str, object] = {
        "playwright_release_components": _numeric_version_components(
            playwright_release,
            label="Playwright release",
        ),
        "chromium_release_components": _numeric_version_components(
            chromium_release,
            label="Chromium release",
        ),
        "chromium_executable_sha256": _sha256_file(executable),
    }
    require_privacy_clean(identity)
    return identity


def _normalized_distribution_inventory(
    distributions: Iterable[object],
) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for distribution in distributions:
        if isinstance(distribution, tuple) and len(distribution) == 2:
            raw_name, raw_version = distribution
        else:
            metadata = getattr(distribution, "metadata", None)
            raw_name = metadata.get("Name") if metadata is not None else None
            raw_version = getattr(distribution, "version", None)
        if not isinstance(raw_name, str) or not isinstance(raw_version, str):
            raise ContractError("installed distribution metadata is incomplete")
        name = re.sub(r"[-_.]+", "-", raw_name.strip()).casefold()
        version = raw_version.strip()
        if (
            not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
            or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+!_-]*", version)
        ):
            raise ContractError("installed distribution metadata is not normalized")
        if name in inventory:
            raise ContractError("installed distribution inventory contains duplicates")
        inventory[name] = version
    if not inventory:
        raise ContractError("installed distribution inventory is empty")
    return dict(sorted(inventory.items()))


def _locked_requirement_inventory(lock_text: str) -> dict[str, str]:
    locked: dict[str, str] = {}
    for line in lock_text.splitlines():
        match = re.match(
            r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;\\]+)",
            line,
        )
        if match is None:
            continue
        name = re.sub(r"[-_.]+", "-", match.group(1)).casefold()
        version = match.group(2)
        if name in locked:
            raise ContractError("development lock contains duplicate requirements")
        locked[name] = version
    if not locked:
        raise ContractError("development lock has no exact requirements")
    return dict(sorted(locked.items()))


def _normalized_architecture(value: object) -> str:
    if not isinstance(value, str):
        raise ContractError("OS architecture is unavailable")
    normalized = value.strip().casefold().replace("-", "_")
    aliases = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86": "x86",
        "i386": "x86",
        "i686": "x86",
    }
    return aliases.get(normalized, "other")


def total_physical_memory_mib() -> int:
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ContractError("total physical memory is unavailable")
        total_bytes = int(status.total_physical)
    else:
        try:
            total_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (AttributeError, OSError, ValueError):
            raise ContractError("total physical memory is unavailable") from None
    memory_mib = total_bytes // (1024 * 1024)
    if memory_mib < 1:
        raise ContractError("total physical memory is unavailable")
    return memory_mib


def environment_manifest(
    repo_root: Path,
    browser_identity: Mapping[str, object],
    *,
    distributions: Iterable[object] | None = None,
    os_build: str | None = None,
    architecture: str | None = None,
    cpu_class: str | None = None,
    memory_mib: int | None = None,
) -> dict[str, object]:
    system = platform.system().strip().lower()
    platform_key = {"windows": "windows", "linux": "linux", "darwin": "macos"}.get(system, "other")
    lock_path = repo_root / "requirements-dev.lock"
    executable = Path(sys.executable).resolve(strict=True)
    inventory = _normalized_distribution_inventory(
        importlib_metadata.distributions() if distributions is None else distributions
    )
    locked = _locked_requirement_inventory(lock_path.read_text(encoding="utf-8"))
    if any(inventory.get(name) != version for name, version in locked.items()):
        raise ContractError("installed distributions do not match the development lock")
    expected_browser_keys = {
        "playwright_release_components",
        "chromium_release_components",
        "chromium_executable_sha256",
    }
    if set(browser_identity) != expected_browser_keys:
        raise ContractError("browser environment identity fields differ")
    for release_key in (
        "playwright_release_components",
        "chromium_release_components",
    ):
        components = browser_identity[release_key]
        if (
            not isinstance(components, list)
            or len(components) < 2
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in components)
        ):
            raise ContractError("browser release components are malformed")
    browser_hash = browser_identity["chromium_executable_sha256"]
    if not isinstance(browser_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", browser_hash):
        raise ContractError("browser executable identity is malformed")
    logical_cpu_count = int(os.cpu_count() or 0)
    if logical_cpu_count < 1:
        raise ContractError("logical CPU count is unavailable")
    cpu_class_value = (cpu_class if cpu_class is not None else platform.processor()).strip().casefold()
    if not cpu_class_value:
        cpu_class_value = _normalized_architecture(
            architecture if architecture is not None else platform.machine()
        )
    retained: dict[str, object] = {
        "platform": platform_key,
        "os_build_components": _numeric_version_components(
            os_build if os_build is not None else platform.version(),
            label="OS build",
        ),
        "architecture": _normalized_architecture(
            architecture if architecture is not None else platform.machine()
        ),
        "python_major": sys.version_info.major,
        "python_minor": sys.version_info.minor,
        "python_micro": sys.version_info.micro,
        "interpreter_sha256": _sha256_file(executable),
        "development_lock_sha256": _sha256_file(lock_path),
        "installed_distribution_count": len(inventory),
        "installed_distribution_inventory_sha256": hashlib.sha256(
            canonical_json_bytes({"distributions": [f"{name}=={version}" for name, version in inventory.items()]})
        ).hexdigest(),
        "locked_requirement_count": len(locked),
        "locked_requirements_match": True,
        "logical_cpu_count": logical_cpu_count,
        "cpu_class_sha256": hashlib.sha256(cpu_class_value.encode("utf-8")).hexdigest(),
        "total_memory_mib": strict_number(
            total_physical_memory_mib() if memory_mib is None else memory_mib,
            label="total memory MiB",
            integer=True,
        ),
        "server_acceptors": FourWorkerWSGIServer.acceptor_count,
        "server_workers": FourWorkerWSGIServer.worker_count,
        "live_diagnostics": True,
        "browser": dict(browser_identity),
    }
    if retained["total_memory_mib"] == 0:
        raise ContractError("total memory MiB must be positive")
    require_privacy_clean(retained)
    return retained


VIEWPORT_BY_KEY = {viewport.key: viewport for viewport in VIEWPORTS}


def _normal_character_path(campaign_slug: str, character_slug: str, section: str) -> str:
    return (
        f"/campaigns/{campaign_slug}/characters/{character_slug}?"
        + urlencode({"page": section})
    )


def _session_character_path(
    campaign_slug: str,
    character_slug: str,
    section: str,
    *,
    fragment: bool = False,
) -> str:
    query: dict[str, str] = {"character": character_slug, "page": section}
    if fragment:
        query["fragment"] = "1"
    return f"/campaigns/{campaign_slug}/session/character?" + urlencode(query)


def runtime_request_path(attempt: AttemptSpec) -> str:
    """Build an internal request path; callers must never retain its value."""

    scenario = attempt.scenario
    if scenario in {
        "normal_document",
        "normal_enhanced_section",
        "normal_visited_return",
        "ordinary_normal_read",
        "overload_character_busy",
    }:
        return _normal_character_path(
            RUNTIME_DND_CAMPAIGN,
            RUNTIME_DND_CHARACTER,
            attempt.section,
        )
    if scenario == "xianxia_normal_document":
        return _normal_character_path(
            RUNTIME_XIANXIA_CAMPAIGN,
            RUNTIME_XIANXIA_CHARACTER,
            attempt.section,
        )
    if scenario in {
        "session_document",
        "session_section_cached_apply",
        "session_shell_first_switch",
        "session_mutation_post",
        "session_mutation_redirect_get",
    }:
        return _session_character_path(
            RUNTIME_DND_CAMPAIGN,
            RUNTIME_DND_CHARACTER,
            "overview" if attempt.section == "root" else attempt.section,
        )
    if scenario in {
        "session_section_fragment",
        "ordinary_session_fragment",
        "overload_session_fragment",
    }:
        return _session_character_path(
            RUNTIME_DND_CAMPAIGN,
            RUNTIME_DND_CHARACTER,
            attempt.section,
            fragment=True,
        )
    if scenario == "xianxia_session_document":
        return _session_character_path(
            RUNTIME_XIANXIA_CAMPAIGN,
            RUNTIME_XIANXIA_CHARACTER,
            attempt.section,
        )
    if scenario == "overload_livez":
        return "/livez"
    if scenario == "overload_readyz":
        return "/readyz"
    if scenario == "overload_campaign":
        return f"/campaigns/{RUNTIME_DND_CAMPAIGN}"
    if scenario.endswith("_root_smoke"):
        if scenario == "dnd_normal_root_smoke":
            return _normal_character_path(RUNTIME_DND_CAMPAIGN, RUNTIME_DND_CHARACTER, "quick")
        if scenario == "dnd_session_root_smoke":
            return _session_character_path(RUNTIME_DND_CAMPAIGN, RUNTIME_DND_CHARACTER, "overview")
        if scenario == "xianxia_normal_root_smoke":
            return _normal_character_path(RUNTIME_XIANXIA_CAMPAIGN, RUNTIME_XIANXIA_CHARACTER, "quick")
        if scenario == "xianxia_session_root_smoke":
            return _session_character_path(RUNTIME_XIANXIA_CAMPAIGN, RUNTIME_XIANXIA_CHARACTER, "quick")
    raise ContractError("attempt has no runtime request route")


def _network_expectation(attempt: AttemptSpec) -> tuple[str, str]:
    if attempt.scenario in {"normal_document", "xianxia_normal_document"}:
        return "[data-character-read-shell-root]", "character-document"
    if attempt.scenario in {"session_document", "xianxia_session_document"}:
        selector = (
            ".session-character-sheet[data-combat-workspace-root]"
            if attempt.scenario == "session_document"
            else ".session-character-sheet:not([data-combat-workspace-root])"
        )
        return selector, "session-character-document"
    if attempt.scenario == "session_section_fragment":
        return ".session-character-sheet[data-combat-workspace-root]", "session-character-fragment"
    if attempt.scenario.endswith("_root_smoke"):
        if "normal_root" in attempt.scenario:
            return "[data-character-read-shell-root]", "character-document"
        selector = (
            ".session-character-sheet[data-combat-workspace-root]"
            if attempt.scenario.startswith("dnd_")
            else ".session-character-sheet:not([data-combat-workspace-root])"
        )
        return selector, "session-character-document"
    raise ContractError("attempt is not a direct browser network surface")


class AsyncBrowserCollector:
    """Isolated authenticated Playwright contexts for the fixed browser matrix."""

    def __init__(self, base_url: str, bootstrap: RuntimeBootstrap, gate: HarnessRenderGate) -> None:
        self._base_url = base_url.rstrip("/")
        self._bootstrap = bootstrap
        self._gate = gate
        self._playwright_manager: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._actor_contexts: dict[str, Any] = {}
        self._storage_states: dict[str, Mapping[str, object]] = {}
        self.live_intervals_ms: dict[str, int] = {}
        self.browser_identity: dict[str, object] = {}

    async def __aenter__(self) -> "AsyncBrowserCollector":
        try:
            from playwright.async_api import async_playwright
        except Exception:
            raise ContractError("Playwright runtime is unavailable") from None
        self._playwright_manager = async_playwright()
        try:
            self._playwright = await self._playwright_manager.start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self.browser_identity = browser_environment_identity(
                importlib_metadata.version("playwright"),
                self._browser.version,
                Path(self._playwright.chromium.executable_path),
            )
        except Exception:
            await self._close_runtime()
            raise ContractError("Chromium launch failed") from None
        try:
            for actor in ACTORS:
                context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 900},
                )
                self._actor_contexts[actor.key] = context
                await self._sign_in(context, self._bootstrap.credentials[actor.key])
                self._storage_states[actor.key] = await context.storage_state()
        except Exception:
            await self._close_runtime()
            raise ContractError("browser actor bootstrap failed") from None
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self._close_runtime()

    async def _close_runtime(self) -> None:
        for context in list(self._actor_contexts.values()):
            try:
                await context.close()
            except Exception:
                pass
        self._actor_contexts.clear()
        self._storage_states.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright_manager = None
        self._playwright = None

    async def _sign_in(self, context: Any, credential: RuntimeActorCredential) -> None:
        page = await context.new_page()
        try:
            response = await page.goto(
                urljoin(self._base_url, "/sign-in"),
                wait_until="domcontentloaded",
            )
            if response is None or response.status != 200:
                raise ContractError("browser sign-in form was unavailable")
            await page.locator('input[name="email"]').fill(credential.email)
            await page.locator('input[name="password"]').fill(credential.password)
            await page.locator('button[type="submit"]').click()
            await page.wait_for_load_state("domcontentloaded")
            if "/sign-in" in page.url:
                raise ContractError("browser sign-in did not complete")
        finally:
            await page.close()

    async def _fresh_page(self, attempt: AttemptSpec) -> tuple[Any, Any]:
        viewport = VIEWPORT_BY_KEY[attempt.viewport]
        context = await self._browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            java_script_enabled=viewport.javascript,
            storage_state=self._storage_states[attempt.actor],
        )
        return context, await context.new_page()

    async def collect_navigation(self, attempt: AttemptSpec) -> dict[str, object]:
        selector, expected_route = _network_expectation(attempt)
        context, page = await self._fresh_page(attempt)
        try:
            started_at = time.perf_counter()
            response = await page.goto(
                urljoin(self._base_url, runtime_request_path(attempt)),
                wait_until="domcontentloaded",
            )
            if response is None:
                raise ContractError("browser navigation produced no response")
            await page.locator(selector).first.wait_for(state="visible", timeout=15000)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            diagnostics = extract_character_diagnostics(await response.all_headers())
            if diagnostics["route_class"] != expected_route:
                raise ContractError("browser navigation diagnostic route differs")
            return build_sample(
                attempt,
                status_code=response.status,
                network_request_count=1,
                request_ms=elapsed_ms,
                navigation_ms=elapsed_ms,
                diagnostics=diagnostics,
            )
        except ContractError:
            raise
        except Exception:
            raise ContractError("browser navigation collection failed") from None
        finally:
            await context.close()

    @staticmethod
    async def _wait_normal_section(page: Any, section: str) -> None:
        await page.wait_for_function(
            """section => document.querySelector('[data-character-read-shell-root]')
                ?.getAttribute('data-character-read-shell-page') === section""",
            arg=section,
            timeout=15000,
        )

    @staticmethod
    async def _unique_session_locator(
        scope: Any,
        selector: str,
        *,
        description: str,
    ) -> Any:
        candidates = scope.locator(selector)
        if await candidates.count() != 1:
            raise ContractError(f"{description} must resolve to exactly one node")
        return candidates.first

    @classmethod
    async def _session_character_sheet(cls, page: Any) -> Any:
        sheet = await cls._unique_session_locator(
            page,
            (
                "[data-session-shell-pane='character']:not([hidden]) "
                ".session-character-sheet[data-combat-workspace-root]"
            ),
            description="mounted Session character sheet",
        )
        await sheet.wait_for(state="visible", timeout=15000)
        return sheet

    @classmethod
    async def _click_session_section(cls, page: Any, section: str) -> None:
        sheet = await cls._session_character_sheet(page)
        link = await cls._unique_session_locator(
            sheet,
            (
                f"[data-combat-section-toggle='{section}'], "
                f"[data-session-character-section-link='{section}']"
            ),
            description=f"Session section link for {section}",
        )
        await link.click()

    @classmethod
    async def _wait_session_section(cls, page: Any, section: str) -> None:
        sheet = await cls._session_character_sheet(page)
        roots = sheet.locator(
            f"[data-combat-section-panel='{section}']:not([hidden]), "
            "[data-session-character-section-root]"
            f"[data-session-character-section='{section}']:not([hidden])"
        )
        root = roots.first
        await root.wait_for(state="visible", timeout=15000)
        if await roots.count() != 1:
            raise ContractError(
                f"visible mounted Session section root for {section} "
                "must resolve to exactly one node"
            )

    async def collect_enhanced_section(self, attempt: AttemptSpec) -> dict[str, object]:
        if attempt.scenario != "normal_enhanced_section":
            raise ContractError("enhanced collector received a different scenario")
        context, page = await self._fresh_page(attempt)
        alternate = "features" if attempt.section == "quick" else "quick"
        try:
            setup_path = _normal_character_path(
                RUNTIME_DND_CAMPAIGN,
                RUNTIME_DND_CHARACTER,
                alternate,
            )
            setup = await page.goto(
                urljoin(self._base_url, setup_path),
                wait_until="domcontentloaded",
            )
            if setup is None or setup.status != 200:
                raise ContractError("enhanced browser setup failed")
            await page.locator("[data-character-read-shell-root]").wait_for(
                state="visible",
                timeout=15000,
            )
            target = urljoin(self._base_url, runtime_request_path(attempt))
            started_at = time.perf_counter()
            async with page.expect_response(
                lambda candidate: candidate.request.method == "GET" and candidate.url == target,
                timeout=15000,
            ) as response_info:
                await page.locator(
                    f"[data-character-read-target-subpage='{attempt.section}']"
                ).click()
            response = await response_info.value
            response_at = time.perf_counter()
            await self._wait_normal_section(page, attempt.section)
            applied_at = time.perf_counter()
            diagnostics = extract_character_diagnostics(await response.all_headers())
            if diagnostics["route_class"] != "character-fetch":
                raise ContractError("enhanced fetch diagnostic route differs")
            return build_sample(
                attempt,
                status_code=response.status,
                network_request_count=1,
                request_ms=(applied_at - started_at) * 1000,
                fetch_ms=(response_at - started_at) * 1000,
                apply_ms=(applied_at - response_at) * 1000,
                diagnostics=diagnostics,
            )
        except ContractError:
            raise
        except Exception:
            raise ContractError("enhanced browser collection failed") from None
        finally:
            await context.close()

    async def collect_visited_return(self, attempt: AttemptSpec) -> dict[str, object]:
        if attempt.scenario != "normal_visited_return":
            raise ContractError("visited-return collector received a different scenario")
        context, page = await self._fresh_page(attempt)
        alternate = "features" if attempt.section == "quick" else "quick"
        relevant_requests = 0

        def count_request(request: Any) -> None:
            nonlocal relevant_requests
            route_prefix = urljoin(
                self._base_url,
                f"/campaigns/{RUNTIME_DND_CAMPAIGN}/characters/{RUNTIME_DND_CHARACTER}",
            )
            if request.method == "GET" and request.url.startswith(route_prefix):
                relevant_requests += 1

        try:
            initial = await page.goto(
                urljoin(self._base_url, runtime_request_path(attempt)),
                wait_until="domcontentloaded",
            )
            if initial is None or initial.status != 200:
                raise ContractError("visited-return browser setup failed")
            await self._wait_normal_section(page, attempt.section)
            alternate_target = urljoin(
                self._base_url,
                _normal_character_path(
                    RUNTIME_DND_CAMPAIGN,
                    RUNTIME_DND_CHARACTER,
                    alternate,
                ),
            )
            async with page.expect_response(
                lambda candidate: (
                    candidate.request.method == "GET" and candidate.url == alternate_target
                ),
                timeout=15000,
            ):
                await page.locator(
                    f"[data-character-read-target-subpage='{alternate}']"
                ).click()
            await self._wait_normal_section(page, alternate)
            page.on("request", count_request)
            started_at = time.perf_counter()
            await page.locator(
                f"[data-character-read-target-subpage='{attempt.section}']"
            ).click()
            await self._wait_normal_section(page, attempt.section)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            page.remove_listener("request", count_request)
            return build_sample(
                attempt,
                status_code=200,
                network_request_count=relevant_requests,
                request_ms=elapsed_ms,
                apply_ms=elapsed_ms,
                diagnostics=None,
            )
        except ContractError:
            raise
        except Exception:
            raise ContractError("visited-return browser collection failed") from None
        finally:
            page.remove_listener("request", count_request)
            await context.close()

    async def collect_session_cached_apply(self, attempt: AttemptSpec) -> dict[str, object]:
        if attempt.scenario != "session_section_cached_apply":
            raise ContractError("Session cached collector received a different scenario")
        context, page = await self._fresh_page(attempt)
        relevant_requests = 0

        def count_request(request: Any) -> None:
            nonlocal relevant_requests
            route_prefix = urljoin(
                self._base_url,
                f"/campaigns/{RUNTIME_DND_CAMPAIGN}/session/character",
            )
            if request.method == "GET" and request.url.startswith(route_prefix):
                relevant_requests += 1

        try:
            setup = await page.goto(
                urljoin(
                    self._base_url,
                    _session_character_path(
                        RUNTIME_DND_CAMPAIGN,
                        RUNTIME_DND_CHARACTER,
                        "overview",
                    ),
                ),
                wait_until="domcontentloaded",
            )
            if setup is None or setup.status != 200:
                raise ContractError("Session cached browser setup failed")
            await self._wait_session_section(page, "overview")
            if attempt.section == "overview":
                await self._click_session_section(page, "spells")
                await self._wait_session_section(page, "spells")
            else:
                await self._click_session_section(page, attempt.section)
                await self._wait_session_section(page, attempt.section)
                await self._click_session_section(page, "overview")
                await self._wait_session_section(page, "overview")
            page.on("request", count_request)
            started_at = time.perf_counter()
            await self._click_session_section(page, attempt.section)
            await self._wait_session_section(page, attempt.section)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            page.remove_listener("request", count_request)
            if relevant_requests != 0:
                raise ContractError("Session cached apply performed a measured network request")
            return build_sample(
                attempt,
                status_code=200,
                network_request_count=relevant_requests,
                request_ms=elapsed_ms,
                apply_ms=elapsed_ms,
                diagnostics=None,
            )
        except ContractError:
            raise
        except Exception:
            raise ContractError("Session cached browser collection failed") from None
        finally:
            page.remove_listener("request", count_request)
            await context.close()

    async def collect_session_shell_switch(self, attempt: AttemptSpec) -> dict[str, object]:
        if attempt.scenario != "session_shell_first_switch":
            raise ContractError("Session shell collector received a different scenario")
        context, page = await self._fresh_page(attempt)
        try:
            setup = await page.goto(
                urljoin(self._base_url, f"/campaigns/{RUNTIME_DND_CAMPAIGN}/session"),
                wait_until="domcontentloaded",
            )
            if setup is None or setup.status != 200:
                raise ContractError("Session shell browser setup failed")
            await page.locator("[data-session-shell-root]").wait_for(
                state="visible",
                timeout=15000,
            )
            started_at = time.perf_counter()
            async with page.expect_response(
                lambda candidate: (
                    candidate.request.method == "GET"
                    and "/session/character" in candidate.url
                    and "fragment=1" in candidate.url
                ),
                timeout=15000,
            ) as response_info:
                await page.locator("[data-session-switch-target='character']").click()
            response = await response_info.value
            response_at = time.perf_counter()
            await page.locator(
                "[data-session-shell-pane='character']:not([hidden])"
            ).wait_for(state="visible", timeout=15000)
            await page.locator(
                ".session-character-sheet[data-combat-workspace-root]"
            ).wait_for(state="visible", timeout=15000)
            applied_at = time.perf_counter()
            diagnostics = extract_character_diagnostics(await response.all_headers())
            if diagnostics["route_class"] != "session-character-fragment":
                raise ContractError("Session shell fragment diagnostic route differs")
            return build_sample(
                attempt,
                status_code=response.status,
                network_request_count=1,
                request_ms=(applied_at - started_at) * 1000,
                fetch_ms=(response_at - started_at) * 1000,
                apply_ms=(applied_at - response_at) * 1000,
                diagnostics=diagnostics,
            )
        except ContractError:
            raise
        except Exception:
            raise ContractError("Session shell browser collection failed") from None
        finally:
            await context.close()

    async def collect_stateful_reads(self) -> list[dict[str, object]]:
        samples: list[dict[str, object]] = []
        for attempt in ATTEMPT_SCHEDULE:
            if attempt.scenario == "normal_enhanced_section":
                samples.append(await self.collect_enhanced_section(attempt))
            elif attempt.scenario == "normal_visited_return":
                samples.append(await self.collect_visited_return(attempt))
            elif attempt.scenario == "session_section_cached_apply":
                samples.append(await self.collect_session_cached_apply(attempt))
            elif attempt.scenario == "session_shell_first_switch":
                samples.append(await self.collect_session_shell_switch(attempt))
        return samples

    def _validated_mutation_redirect(self, location: str) -> str:
        if not isinstance(location, str) or not location:
            raise ContractError("mutation response omitted its redirect")
        target = urljoin(self._base_url, location)
        expected_origin = urlsplit(self._base_url)
        parsed = urlsplit(target)
        if (parsed.scheme, parsed.netloc) != (expected_origin.scheme, expected_origin.netloc):
            raise ContractError("mutation redirect escaped the harness origin")
        expected_path = f"/campaigns/{RUNTIME_DND_CAMPAIGN}/session/character"
        query = parse_qs(parsed.query, keep_blank_values=True)
        expected_query = {
            "character": [RUNTIME_DND_CHARACTER],
            "page": ["resources"],
            "fragment": ["1"],
        }
        if parsed.path != expected_path or query != expected_query:
            raise ContractError("mutation redirect is not the canonical fragment GET")
        return target

    async def collect_mutations(self) -> list[dict[str, object]]:
        post_attempts = [
            attempt
            for attempt in ATTEMPT_SCHEDULE
            if attempt.scenario == "session_mutation_post"
        ]
        get_attempts = [
            attempt
            for attempt in ATTEMPT_SCHEDULE
            if attempt.scenario == "session_mutation_redirect_get"
        ]
        if len(post_attempts) != 6 or len(get_attempts) != 6:
            raise ContractError("runtime mutation schedule is not six exact pairs")
        context, page = await self._fresh_page(post_attempts[0])
        samples: list[dict[str, object]] = []
        try:
            setup = await page.goto(
                urljoin(
                    self._base_url,
                    _session_character_path(
                        RUNTIME_DND_CAMPAIGN,
                        RUNTIME_DND_CHARACTER,
                        "resources",
                    ),
                ),
                wait_until="domcontentloaded",
            )
            if setup is None or setup.status != 200:
                raise ContractError("mutation browser setup failed")
            await page.locator(
                "[data-session-shell-root][data-session-shell-active='character']"
            ).wait_for(state="visible", timeout=15000)
            await self._wait_session_section(page, "resources")
            await page.locator(
                "[data-session-shell-pane='session'] "
                "[data-session-live-root][data-session-live-view='session']"
            ).wait_for(state="attached", timeout=15000)
            for post_attempt, get_attempt in zip(post_attempts, get_attempts, strict=True):
                vitals_form_selector = (
                    "form[data-character-sheet-edit-form='vitals']"
                    "[data-character-autosubmit-mode='focus-blur']"
                    "[data-character-autosubmit]"
                )
                input_locator = page.locator(
                    vitals_form_selector + " "
                    "input[name='current_hp']"
                ).first
                await input_locator.wait_for(state="visible", timeout=15000)
                autosubmit_ready = await input_locator.evaluate(
                    """input => Boolean(
                        typeof window.__playerWikiCombatWorkspace?.init === "function"
                        && input.form
                        && Object.hasOwn(
                          input.form.dataset,
                          "characterAutosubmitState",
                        )
                    )"""
                )
                if autosubmit_ready is not True:
                    raise ContractError("mutation focus-blur autosubmit is not initialized")
                mount_proof = await page.evaluate(
                    """() => {
                        const shell = document.querySelector("[data-session-shell-root]");
                        const characterPane = document.querySelector("[data-session-shell-pane='character']");
                        const sessionPane = document.querySelector("[data-session-shell-pane='session']");
                        const sheet = characterPane?.querySelector(
                          ".session-character-sheet[data-combat-workspace-root]"
                        );
                        const liveRoot = sessionPane?.querySelector(
                          "[data-session-live-root][data-session-live-view='session']"
                        );
                        if (!shell || !characterPane || !sessionPane || !sheet || !liveRoot) {
                          return false;
                        }
                        window.__characterReadHarnessMountProof = {
                          document,
                          shell,
                          characterPane,
                          sessionPane,
                          sheet,
                          liveRoot,
                          marker: "slice0b-mounted",
                        };
                        return true;
                    }"""
                )
                if mount_proof is not True:
                    raise ContractError("mutation setup did not retain the mounted Session shell")

                post_path = (
                    f"/campaigns/{RUNTIME_DND_CAMPAIGN}/characters/"
                    f"{RUNTIME_DND_CHARACTER}/session/vitals"
                )
                redirect_path = f"/campaigns/{RUNTIME_DND_CAMPAIGN}/session/character"
                post_requests: list[tuple[Any, float]] = []
                post_responses: list[tuple[Any, float]] = []
                get_requests: list[tuple[Any, float]] = []
                get_responses: list[tuple[Any, float]] = []
                redirected_get_observed = asyncio.Event()
                document_load_events = 0

                def request_observed(request: Any) -> None:
                    parsed = urlsplit(request.url)
                    observed_at = time.perf_counter()
                    if request.method == "POST" and parsed.path == post_path:
                        post_requests.append((request, observed_at))
                    elif request.method == "GET" and parsed.path == redirect_path:
                        get_requests.append((request, observed_at))

                def response_observed(response: Any) -> None:
                    request = response.request
                    parsed = urlsplit(request.url)
                    observed_at = time.perf_counter()
                    if request.method == "POST" and parsed.path == post_path:
                        post_responses.append((response, observed_at))
                    elif request.method == "GET" and parsed.path == redirect_path:
                        get_responses.append((response, observed_at))
                        redirected_get_observed.set()

                def document_loaded() -> None:
                    nonlocal document_load_events
                    document_load_events += 1

                page.on("request", request_observed)
                page.on("response", response_observed)
                page.on("domcontentloaded", document_loaded)
                try:
                    submit_audit_ready = await page.evaluate(
                        """selector => {
                            if (window.__characterReadHarnessSubmitAudit) return false;
                            const audit = { intercepted: 0, unguarded: 0, listener: null };
                            audit.listener = event => {
                              const form = event.target;
                              if (!(form instanceof HTMLFormElement) || !form.matches(selector)) {
                                return;
                              }
                              if (event.defaultPrevented) {
                                audit.intercepted += 1;
                              } else {
                                audit.unguarded += 1;
                                event.preventDefault();
                              }
                            };
                            document.addEventListener("submit", audit.listener);
                            window.__characterReadHarnessSubmitAudit = audit;
                            return true;
                        }""",
                        vitals_form_selector,
                    )
                    if submit_audit_ready is not True:
                        raise ContractError("mutation submit audit could not be installed")
                    await input_locator.focus()
                    value_changed = await input_locator.evaluate(
                        """input => {
                            if (!(input instanceof HTMLInputElement)) return false;
                            const current = Number.parseInt(input.value, 10);
                            const minimum = Number.parseInt(input.min || "0", 10);
                            const maximum = Number.parseInt(
                              input.max || String(current + 1),
                              10,
                            );
                            if (![current, minimum, maximum].every(Number.isFinite)) {
                              return false;
                            }
                            const next = current > minimum
                              ? current - 1
                              : Math.min(maximum, current + 1);
                            if (next === current) return false;
                            input.value = String(next);
                            input.dispatchEvent(new Event("input", { bubbles: true }));
                            return true;
                        }"""
                    )
                    if value_changed is not True:
                        raise ContractError("mutation input had no bounded adjacent value")
                    await input_locator.blur()
                    await asyncio.wait_for(redirected_get_observed.wait(), timeout=15)
                    await page.wait_for_function(
                        """() => {
                            const proof = window.__characterReadHarnessMountProof;
                            const nextSheet = proof?.characterPane?.querySelector(
                              ".session-character-sheet[data-combat-workspace-root]"
                            );
                            return Boolean(
                              proof
                              && !proof.sheet.isConnected
                              && nextSheet
                              && nextSheet !== proof.sheet
                              && nextSheet.isConnected
                            );
                        }""",
                        timeout=15000,
                    )
                    await self._wait_session_section(page, "resources")
                    await page.locator(
                        "[data-session-character-flash-stack] .flash-success",
                        has_text="Vitals updated.",
                    ).first.wait_for(state="visible", timeout=15000)
                    get_applied_at = time.perf_counter()
                    await asyncio.sleep(0)
                finally:
                    page.remove_listener("request", request_observed)
                    page.remove_listener("response", response_observed)
                    page.remove_listener("domcontentloaded", document_loaded)

                if (
                    len(post_requests) != 1
                    or len(post_responses) != 1
                    or len(get_requests) != 1
                    or len(get_responses) != 1
                ):
                    raise ContractError("mutation transport was ambiguous")
                post_request, post_started_at = post_requests[0]
                post_response, post_response_at = post_responses[0]
                get_request, get_started_at = get_requests[0]
                get_response, get_response_at = get_responses[0]
                if (
                    post_response.request is not post_request
                    or get_response.request is not get_request
                    or get_request.redirected_from is not post_request
                    or post_request.is_navigation_request()
                    or get_request.is_navigation_request()
                ):
                    raise ContractError("mutation redirect chain was not one linked POST and GET")
                if post_response.status not in {302, 303}:
                    raise ContractError("mutation POST did not return its one redirect")
                post_headers = await post_response.all_headers()
                self._validated_mutation_redirect(_required_header(post_headers, "Location"))
                self._validated_mutation_redirect(get_request.url)
                if get_response.status != 200:
                    raise ContractError("mutation redirected GET failed")
                if document_load_events != 0:
                    raise ContractError("mutation reloaded the Session document")
                submit_audit = await page.evaluate(
                    """() => {
                        const audit = window.__characterReadHarnessSubmitAudit;
                        if (!audit || typeof audit.listener !== "function") return null;
                        document.removeEventListener("submit", audit.listener);
                        delete window.__characterReadHarnessSubmitAudit;
                        return {
                          intercepted: audit.intercepted,
                          unguarded: audit.unguarded,
                        };
                    }"""
                )
                if submit_audit != {"intercepted": 1, "unguarded": 0}:
                    raise ContractError("mutation submit was not intercepted exactly once")
                shell_still_mounted = await page.evaluate(
                    """() => {
                        const proof = window.__characterReadHarnessMountProof;
                        return Boolean(
                          proof
                          && proof.marker === "slice0b-mounted"
                          && proof.document === document
                          && proof.shell === document.querySelector("[data-session-shell-root]")
                          && proof.characterPane === document.querySelector(
                            "[data-session-shell-pane='character']"
                          )
                          && proof.sessionPane === document.querySelector(
                            "[data-session-shell-pane='session']"
                          )
                          && proof.liveRoot === proof.sessionPane.querySelector(
                            "[data-session-live-root][data-session-live-view='session']"
                          )
                          && proof.shell.isConnected
                          && proof.characterPane.isConnected
                          && proof.sessionPane.isConnected
                          && proof.liveRoot.isConnected
                        );
                    }"""
                )
                if shell_still_mounted is not True:
                    raise ContractError("mutation replaced or unmounted the Session shell")
                post_elapsed_ms = (post_response_at - post_started_at) * 1000
                post_sample = build_sample(
                    post_attempt,
                    status_code=post_response.status,
                    network_request_count=1,
                    request_ms=post_elapsed_ms,
                    fetch_ms=post_elapsed_ms,
                    diagnostics=None,
                )
                diagnostics = extract_character_diagnostics(await get_response.all_headers())
                if diagnostics["route_class"] != "session-character-fragment":
                    raise ContractError("mutation redirected GET route differs")
                get_sample = build_sample(
                    get_attempt,
                    status_code=get_response.status,
                    network_request_count=1,
                    request_ms=(get_applied_at - get_started_at) * 1000,
                    fetch_ms=(get_response_at - get_started_at) * 1000,
                    apply_ms=(get_applied_at - get_response_at) * 1000,
                    diagnostics=diagnostics,
                )
                validate_mutation_ledger((post_sample, get_sample))
                samples.extend((post_sample, get_sample))
            return samples
        except ContractError:
            raise
        except Exception:
            # No ambiguous transport failure is retried.  The run ends without
            # publishing an evidence envelope.
            raise ContractError("mutation collection failed without retry") from None
        finally:
            await context.close()

    async def _ordinary_character_read(
        self,
        page: Any,
        attempt: AttemptSpec,
    ) -> dict[str, object]:
        started_at = time.perf_counter()
        response = await page.goto(
            urljoin(self._base_url, runtime_request_path(attempt)),
            wait_until="domcontentloaded",
        )
        if response is None:
            raise ContractError("ordinary Character read produced no response")
        await page.locator("[data-character-read-shell-root]").wait_for(
            state="visible",
            timeout=15000,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        diagnostics = extract_character_diagnostics(await response.all_headers())
        if diagnostics["route_class"] != "character-document":
            raise ContractError("ordinary Character diagnostic route differs")
        sample = build_sample(
            attempt,
            status_code=response.status,
            network_request_count=1,
            request_ms=elapsed_ms,
            navigation_ms=elapsed_ms,
            diagnostics=diagnostics,
        )
        if sample["unexpected_error"]:
            raise ContractError("ordinary table produced an unexpected response")
        return sample

    async def _ordinary_session_fragment_read(
        self,
        page: Any,
        attempt: AttemptSpec,
    ) -> dict[str, object]:
        started_at = time.perf_counter()
        response = await page.goto(
            urljoin(self._base_url, runtime_request_path(attempt)),
            wait_until="domcontentloaded",
        )
        if response is None:
            raise ContractError("ordinary Session Character fragment produced no response")
        await page.locator(
            ".session-character-sheet[data-combat-workspace-root]"
        ).wait_for(state="visible", timeout=15000)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        diagnostics = extract_character_diagnostics(await response.all_headers())
        if diagnostics["route_class"] != "session-character-fragment":
            raise ContractError("ordinary Session Character fragment route differs")
        sample = build_sample(
            attempt,
            status_code=response.status,
            network_request_count=1,
            request_ms=elapsed_ms,
            navigation_ms=elapsed_ms,
            diagnostics=diagnostics,
        )
        if sample["unexpected_error"]:
            raise ContractError("ordinary Session Character fragment failed")
        return sample

    async def _prepare_live_sampler(
        self,
        page: Any,
        *,
        actor: str,
        surface: str,
    ) -> str:
        if surface == "session-live":
            page_path = f"/campaigns/{RUNTIME_DND_CAMPAIGN}/session"
            root_selector = '[data-session-live-root][data-session-live-view="session"]'
            metric_view = "session"
        elif surface == "combat-live":
            page_path = f"/campaigns/{RUNTIME_DND_CAMPAIGN}/combat"
            root_selector = "[data-combat-live-root]"
            metric_view = "combat"
        else:
            raise ContractError("ordinary live surface is not allowlisted")
        response = await page.goto(
            urljoin(self._base_url, page_path),
            wait_until="domcontentloaded",
        )
        if response is None or response.status != 200:
            raise ContractError("ordinary live sampler page was unavailable")
        root = page.locator(root_selector).first
        await root.wait_for(state="visible", timeout=15000)
        if await root.get_attribute("data-live-diagnostics-enabled") != "1":
            raise ContractError("ordinary live diagnostics are disabled")
        interval = await root.get_attribute("data-live-active-interval-ms")
        if not isinstance(interval, str) or not re.fullmatch(r"[1-9][0-9]*", interval):
            raise ContractError("ordinary live active interval is malformed")
        self.live_intervals_ms[actor] = int(interval)
        await page.wait_for_function(
            """metricView => Boolean(
                window.__playerWikiLiveDiagnostics
                && window.__playerWikiLiveDiagnostics[metricView]
                && typeof window.__playerWikiLiveDiagnostics[metricView].sample === 'function'
            )""",
            arg=metric_view,
            timeout=15000,
        )
        warmup = await self._run_live_sampler(page, metric_view)
        if not isinstance(warmup, Mapping):
            raise ContractError("ordinary live warmup did not return diagnostics")
        return metric_view

    @staticmethod
    async def _run_live_sampler(page: Any, metric_view: str) -> Mapping[str, object]:
        for _attempt in range(50):
            result = await page.evaluate(
                """async metricView => {
                    const sampler = window.__playerWikiLiveDiagnostics?.[metricView]?.sample;
                    if (typeof sampler !== 'function') return null;
                    return await sampler({ mode: 'steady', forceApply: false });
                }""",
                metric_view,
            )
            if isinstance(result, Mapping):
                return result
            await page.wait_for_timeout(50)
        raise ContractError("ordinary live sampler returned no semantic result")

    async def _ordinary_live_read(
        self,
        page: Any,
        metric_view: str,
        attempt: AttemptSpec,
    ) -> dict[str, object]:
        result = await self._run_live_sampler(page, metric_view)
        sample = build_unchanged_live_sample(attempt, result)
        if sample["unexpected_error"]:
            raise ContractError("ordinary live sampler produced an unexpected response")
        return sample

    async def collect_ordinary_pressure(self) -> list[dict[str, object]]:
        attempts = [
            attempt for attempt in ATTEMPT_SCHEDULE if attempt.pressure_group == "ordinary"
        ]
        if len(attempts) != 60:
            raise ContractError("ordinary table schedule is not twelve five-actor rounds")
        pages = {
            actor.key: await self._actor_contexts[actor.key].new_page()
            for actor in ACTORS
        }
        metric_views: dict[str, str] = {}
        samples: list[dict[str, object]] = []
        try:
            live_attempts = [attempt for attempt in attempts if attempt.zero_contract == "unchanged-live"]
            for attempt in live_attempts:
                if attempt.actor not in metric_views:
                    metric_views[attempt.actor] = await self._prepare_live_sampler(
                        pages[attempt.actor],
                        actor=attempt.actor,
                        surface=attempt.surface,
                    )
            for round_index in range(1, 13):
                round_attempts = [
                    attempt for attempt in attempts if attempt.sample_index == round_index
                ]
                normal_attempts = [
                    attempt for attempt in round_attempts if attempt.surface == "normal-character"
                ]
                fragment_attempts = [
                    attempt
                    for attempt in round_attempts
                    if attempt.surface == "session-character-fragment"
                ]
                live_attempts = [
                    attempt
                    for attempt in round_attempts
                    if attempt.zero_contract == "unchanged-live"
                ]
                if (
                    len(round_attempts) != 5
                    or {attempt.actor for attempt in round_attempts} != ACTOR_KEYS
                    or len(normal_attempts) != 2
                    or {attempt.actor for attempt in normal_attempts}
                    != {"assigned_player", "unassigned_player"}
                    or len(fragment_attempts) != 1
                    or fragment_attempts[0].actor != "dm"
                    or {(attempt.actor, attempt.surface) for attempt in live_attempts}
                    != {
                        ("observer_primary", "combat-live"),
                        ("observer_secondary", "session-live"),
                    }
                ):
                    raise ContractError("ordinary round actor and surface mapping differs")
                coroutines = []
                for attempt in round_attempts:
                    if attempt.surface == "normal-character":
                        coroutines.append(
                            self._ordinary_character_read(pages[attempt.actor], attempt)
                        )
                    elif attempt.surface == "session-character-fragment":
                        coroutines.append(
                            self._ordinary_session_fragment_read(
                                pages[attempt.actor],
                                attempt,
                            )
                        )
                    else:
                        coroutines.append(
                            self._ordinary_live_read(
                                pages[attempt.actor],
                                metric_views[attempt.actor],
                                attempt,
                            )
                        )
                round_samples = await asyncio.gather(*coroutines)
                samples.extend(round_samples)
            return samples
        except ContractError:
            raise
        except Exception:
            raise ContractError("ordinary table collection failed") from None
        finally:
            for page in pages.values():
                await page.close()

    async def _timed_api_get(
        self,
        context: Any,
        request_path: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[Any, float]:
        started_at = time.perf_counter()
        response = await context.request.get(
            urljoin(self._base_url, request_path),
            headers=dict(headers or {}),
            max_redirects=0,
        )
        return response, (time.perf_counter() - started_at) * 1000

    async def _collect_overload_attempt(self, attempt: AttemptSpec) -> dict[str, object]:
        context = self._actor_contexts[attempt.actor]
        response, elapsed_ms = await self._timed_api_get(
            context,
            runtime_request_path(attempt),
        )
        diagnostics: Mapping[str, object] | None = None
        if attempt.scenario == "overload_character_busy":
            diagnostics = validate_expected_busy_response(
                response.status,
                response.headers,
                await response.text(),
                private_markers=(
                    RUNTIME_DND_CAMPAIGN,
                    RUNTIME_DND_CHARACTER,
                    *(credential.email for credential in self._bootstrap.credentials.values()),
                ),
            )
        elif attempt.scenario == "overload_session_fragment":
            if response.status != 200:
                raise ContractError("Session fragment was not preserved during overload")
            diagnostics = extract_character_diagnostics(response.headers)
            if diagnostics["route_class"] != "session-character-fragment":
                raise ContractError("overload Session fragment route differs")
        elif response.status != 200:
            raise ContractError(
                f"non-Character worker preservation request failed with status {response.status}"
            )
        sample = build_sample(
            attempt,
            status_code=response.status,
            network_request_count=1,
            request_ms=elapsed_ms,
            fetch_ms=elapsed_ms,
            diagnostics=diagnostics,
        )
        if sample["unexpected_error"]:
            raise ContractError("overload attempt produced an unexpected response")
        return sample

    async def collect_overload_pressure(self) -> list[dict[str, object]]:
        attempts = [
            attempt for attempt in ATTEMPT_SCHEDULE if attempt.pressure_group == "overload"
        ]
        if len(attempts) != 15:
            raise ContractError("overload schedule is not three five-request rounds")
        samples: list[dict[str, object]] = []
        for round_index in range(1, 4):
            round_attempts = [
                attempt for attempt in attempts if attempt.sample_index == round_index
            ]
            if len(round_attempts) != 5:
                raise ContractError("overload round is incomplete")
            hold_contexts = [
                await self._browser.new_context(storage_state=self._storage_states[actor])
                for actor in ("dm", "assigned_player")
            ]
            held_tasks: list[asyncio.Task[tuple[Any, float]]] = []
            self._gate.arm()
            try:
                held_tasks = [
                    asyncio.create_task(
                        self._timed_api_get(
                            context,
                            _normal_character_path(
                                RUNTIME_DND_CAMPAIGN,
                                RUNTIME_DND_CHARACTER,
                                section,
                            ),
                            headers={RENDER_GATE_HEADER: RENDER_GATE_HOLD_VALUE},
                        )
                    )
                    for context, section in zip(
                        hold_contexts,
                        ("quick", "inventory"),
                        strict=True,
                    )
                ]
                entered = await asyncio.to_thread(self._gate.wait_for_two, 15.0)
                if not entered:
                    raise ContractError("render gate did not occupy both admission slots")
                round_samples = await asyncio.gather(
                    *(self._collect_overload_attempt(attempt) for attempt in round_attempts)
                )
                samples.extend(round_samples)
            except ContractError:
                raise
            except Exception:
                raise ContractError("deterministic overload collection failed") from None
            finally:
                self._gate.release()
                held_results = await asyncio.gather(*held_tasks, return_exceptions=True)
                self._gate.disarm()
                for context in hold_contexts:
                    await context.close()
            if len(held_results) != 2 or any(
                isinstance(result, BaseException) or result[0].status != 200
                for result in held_results
            ):
                raise ContractError("admitted Character reads did not recover after gate release")
        return samples

    async def collect_direct_network_surfaces(self) -> list[dict[str, object]]:
        scenarios = {
            "normal_document",
            "session_document",
            "session_section_fragment",
            "xianxia_normal_document",
            "xianxia_session_document",
        }
        return [
            await self.collect_navigation(attempt)
            for attempt in ATTEMPT_SCHEDULE
            if attempt.scenario in scenarios
        ]

    async def collect_root_smoke(self) -> list[dict[str, object]]:
        return [
            await self.collect_navigation(attempt)
            for attempt in ATTEMPT_SCHEDULE
            if attempt.scenario.endswith("_root_smoke")
        ]

    async def collect_all(self) -> list[dict[str, object]]:
        samples: list[dict[str, object]] = []
        samples.extend(await self.collect_direct_network_surfaces())
        samples.extend(await self.collect_stateful_reads())
        samples.extend(await self.collect_mutations())
        samples.extend(await self.collect_root_smoke())
        samples.extend(await self.collect_ordinary_pressure())
        samples.extend(await self.collect_overload_pressure())
        return list(validate_attempt_ledger(samples))


async def collect_runtime_baseline(
    repo_root: Path,
    runtime_root: Path,
) -> tuple[
    list[dict[str, object]],
    RuntimeBootstrap,
    dict[str, int],
    dict[str, object],
]:
    bootstrap = bootstrap_runtime_app(repo_root, runtime_root)
    gate = install_harness_render_gate(bootstrap.app)
    server = FourWorkerWSGIServer(bootstrap.app)
    server.start()
    try:
        async with AsyncBrowserCollector(server.base_url, bootstrap, gate) as collector:
            samples = await collector.collect_all()
            intervals = dict(collector.live_intervals_ms)
            browser_identity = dict(collector.browser_identity)
    finally:
        gate.release()
        server.stop()
    return samples, bootstrap, intervals, browser_identity


def validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str):
        raise EvidenceRefusal("run id must use the anonymous Slice 0B format")
    match = re.fullmatch(
        r"slice0b-baseline-([0-9]{8})-([0-9a-f]{8,16})",
        run_id,
    )
    if match is None:
        raise EvidenceRefusal("run id must use the anonymous Slice 0B format")
    try:
        parsed_date = datetime.strptime(match.group(1), "%Y%m%d")
    except ValueError:
        raise EvidenceRefusal("run id contains an invalid calendar date") from None
    if parsed_date.strftime("%Y%m%d") != match.group(1):
        raise EvidenceRefusal("run id contains an invalid calendar date")
    return run_id


def _path_is_reparse_point(path: Path) -> bool:
    try:
        metadata = os.lstat(_filesystem_path(path))
    except OSError as exc:
        raise EvidenceRefusal("evidence path metadata could not be verified") from exc
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _verify_evidence_suffix_components(owner: Path, supplied_root: Path) -> None:
    try:
        relative = supplied_root.relative_to(owner)
    except ValueError as exc:
        raise EvidenceRefusal("evidence root escaped its registered owner") from exc
    if relative != EVIDENCE_RELATIVE_ROOT:
        raise EvidenceRefusal("evidence root is not the authorized Slice 0 root")
    current = owner
    for component in relative.parts:
        current = current / component
        if not os.path.lexists(_filesystem_path(current)):
            continue
        if _path_is_reparse_point(current):
            raise EvidenceRefusal("evidence suffix contains a reparse point")
        if not os.path.isdir(_filesystem_path(current)):
            raise EvidenceRefusal("evidence suffix contains a non-directory")


class EvidenceEnvelope:
    """Unique staging directory with manifest-last atomic publication."""

    def __init__(self, repo_root: Path, evidence_root: Path, run_id: str) -> None:
        self.run_id = validate_run_id(run_id)
        self.repo_root = repo_root.resolve(strict=True)
        supplied_root = Path(os.path.abspath(os.fspath(evidence_root)))
        relative_depth = len(EVIDENCE_RELATIVE_ROOT.parts)
        if len(supplied_root.parents) < relative_depth:
            raise EvidenceRefusal("evidence root has no registered-worktree owner")
        lexical_owner = supplied_root.parents[relative_depth - 1]
        expected_root = Path(
            os.path.abspath(os.fspath(lexical_owner / EVIDENCE_RELATIVE_ROOT))
        )
        if supplied_root != expected_root:
            raise EvidenceRefusal("evidence root is not the authorized Slice 0 root")
        owner_root = lexical_owner.resolve(strict=True)
        _verify_evidence_suffix_components(lexical_owner, supplied_root)
        worktrees = _run_git(self.repo_root, "worktree", "list", "--porcelain")
        if worktrees.returncode != 0:
            raise EvidenceRefusal("registered worktree census failed")
        registered = {
            Path(line.removeprefix("worktree ")).resolve(strict=True)
            for line in worktrees.stdout.splitlines()
            if line.startswith("worktree ")
        }
        if owner_root not in registered:
            raise EvidenceRefusal("evidence owner is not a registered worktree")
        ignored = _run_git(owner_root, "check-ignore", "-q", "--", EVIDENCE_RELATIVE_ROOT.as_posix())
        if ignored.returncode != 0:
            raise EvidenceRefusal("evidence root is not ignored")
        os.makedirs(_filesystem_path(supplied_root), exist_ok=True)
        realized_root = supplied_root.resolve(strict=True)
        if (
            not realized_root.is_relative_to(owner_root)
            or realized_root
            != (owner_root / EVIDENCE_RELATIVE_ROOT).resolve(strict=True)
        ):
            raise EvidenceRefusal("realized evidence root escaped its registered owner")
        _verify_evidence_suffix_components(lexical_owner, supplied_root)
        self.evidence_root = realized_root
        self.target = self.evidence_root / self.run_id
        self.staging = self.evidence_root / f".{self.run_id}.staging-{uuid.uuid4().hex}"
        if os.path.lexists(_filesystem_path(self.target)):
            raise EvidenceRefusal("evidence run already exists")
        os.mkdir(_filesystem_path(self.staging))
        self._written: list[str] = []
        self._sealed = False

    def write_json(self, name: str, payload: Mapping[str, object]) -> None:
        if name not in {"samples.json", "acceptance.json", "safety-scan.json"}:
            raise EvidenceRefusal("JSON artifact is not allowlisted or manifest must be last")
        require_privacy_clean(payload)
        self._write_bytes(name, canonical_json_bytes(payload))

    def write_summary(self, markdown: str) -> None:
        require_privacy_clean(markdown)
        self._write_bytes("summary.md", markdown.encode("utf-8"))

    def _write_bytes(self, name: str, payload: bytes) -> None:
        if self._sealed or name in self._written or name not in PRE_MANIFEST_ARTIFACTS:
            raise EvidenceRefusal("artifact write order or uniqueness refused")
        expected_name = PRE_MANIFEST_ARTIFACTS[len(self._written)]
        if name != expected_name:
            raise EvidenceRefusal("artifacts must use the fixed order")
        destination = self.staging / name
        with open(_filesystem_path(destination), "xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        self._written.append(name)

    def seal(self, manifest: Mapping[str, object]) -> Path:
        if self._sealed or tuple(self._written) != PRE_MANIFEST_ARTIFACTS:
            raise EvidenceRefusal("manifest cannot seal an incomplete envelope")
        if os.path.lexists(_filesystem_path(self.target)):
            raise EvidenceRefusal("evidence target appeared before sealing")
        if manifest.get("schema") != SCHEMA:
            raise EvidenceRefusal("manifest schema differs")
        if manifest.get("run_id") != self.run_id:
            raise EvidenceRefusal("manifest run id differs")
        if manifest.get("artifact_count") != len(ARTIFACT_ORDER):
            raise EvidenceRefusal("manifest artifact count differs")
        if manifest.get("manifest_written_last") is not True:
            raise EvidenceRefusal("manifest-last declaration differs")
        if manifest.get("artifact_sha256_scope") != list(PRE_MANIFEST_ARTIFACTS):
            raise EvidenceRefusal("manifest hash scope is not pre-manifest-only")
        retained_hashes = manifest.get("artifact_sha256")
        if not isinstance(retained_hashes, Mapping) or set(retained_hashes) != set(
            PRE_MANIFEST_ARTIFACTS
        ):
            raise EvidenceRefusal("manifest artifact hash keys differ")
        if any(
            not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in retained_hashes.values()
        ):
            raise EvidenceRefusal("manifest artifact hash is malformed")
        if {
            entry.name for entry in os.scandir(_filesystem_path(self.staging))
        } != set(PRE_MANIFEST_ARTIFACTS):
            raise EvidenceRefusal("pre-manifest envelope contains unexpected artifacts")
        actual_hashes = {
            name: _sha256_file(self.staging / name)
            for name in PRE_MANIFEST_ARTIFACTS
        }
        if dict(retained_hashes) != actual_hashes:
            raise EvidenceRefusal("manifest artifact hashes differ from staged bytes")
        require_privacy_clean(manifest)
        manifest_path = self.staging / "manifest.json"
        with open(_filesystem_path(manifest_path), "xb") as stream:
            stream.write(canonical_json_bytes(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        if {entry.name for entry in os.scandir(_filesystem_path(self.staging))} != set(ARTIFACT_ORDER):
            raise EvidenceRefusal("evidence envelope contains unexpected artifacts")
        # Recompute at the publication boundary so staged tampering cannot be
        # hidden behind hashes calculated before the manifest was written.
        if {
            name: _sha256_file(self.staging / name)
            for name in PRE_MANIFEST_ARTIFACTS
        } != actual_hashes:
            raise EvidenceRefusal("staged artifact changed before publication")
        os.rename(_filesystem_path(self.staging), _filesystem_path(self.target))
        self._sealed = True
        return self.target


def acceptance_contract() -> dict[str, object]:
    """Return frozen candidate formulas without claiming baseline optimization."""

    return {
        "baseline_freeze_only": True,
        "optimization_success_claimed": False,
        "relative_session_server_p95_reduction_percent": 60,
        "relative_normal_server_p95_reduction_percent": 50,
        "relative_session_query_and_bytes_p95_reduction_percent": 50,
        "maximum_live_regression_percent": 15,
        "cold_selected_section_p95_ms": 2000,
        "warm_selected_section_network_p95_ms": 750,
        "cached_apply_p95_ms": 100,
        "unexpected_errors_allowed": 0,
        "ordinary_unexpected_5xx_allowed": 0,
        "semantic_zero_required": True,
    }


def evaluate_baseline_freeze(
    samples: Sequence[Mapping[str, object]],
    *,
    safety_findings: Sequence[Mapping[str, str]],
    schedule: Sequence[AttemptSpec] = ATTEMPT_SCHEDULE,
) -> dict[str, object]:
    ordered = validate_attempt_ledger(samples, schedule)
    mutation = [sample for sample in ordered if str(sample["scenario"]).startswith("session_mutation_")]
    posts = [sample for sample in mutation if sample["scenario"] == "session_mutation_post"]
    redirects = [sample for sample in mutation if sample["scenario"] == "session_mutation_redirect_get"]
    if len(posts) != 6 or len(redirects) != 6:
        raise ContractError("mutation schedule must contain six POST and six redirected GET records")
    for index in range(6):
        validate_mutation_ledger((posts[index], redirects[index]))
    unexpected_errors = sum(bool(sample["unexpected_error"]) for sample in ordered)
    clean_scan = len(safety_findings) == 0
    frozen = unexpected_errors == 0 and clean_scan
    return {
        "schedule_exact": True,
        "attempt_count": len(ordered),
        "unexpected_error_count": unexpected_errors,
        "safety_scan_clean": clean_scan,
        "baseline_frozen": frozen,
        "optimization_success_claimed": False,
    }


def schedule_manifest() -> list[dict[str, object]]:
    return [asdict(attempt) for attempt in ATTEMPT_SCHEDULE]


SUMMARY_METRICS = (
    "request_ms",
    "navigation_ms",
    "fetch_ms",
    "apply_ms",
    "server_ms",
    "query_count",
    "query_time_ms",
    "response_bytes",
    "rss_bytes",
    "peak_rss_bytes",
)


def _metric_summary(values: Sequence[int | float]) -> dict[str, float]:
    if not values:
        raise ContractError("metric summary requires measured values")
    normalized = [float(strict_number(value, label="summary metric")) for value in values]
    return {
        "mean": round(sum(normalized) / len(normalized), 3),
        "p50": round(linear_percentile(normalized, 50), 3),
        "p95": round(linear_percentile(normalized, 95), 3),
    }


def scenario_statistics(samples: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    ordered = validate_attempt_ledger(samples)
    groups: dict[tuple[str, str, str, str, str], list[Mapping[str, object]]] = {}
    for sample in ordered:
        if sample["sample_phase"] != "measured":
            continue
        cell = (
            str(sample["scenario"]),
            str(sample["surface"]),
            str(sample["actor"]),
            str(sample["section"]),
            str(sample["viewport"]),
        )
        groups.setdefault(cell, []).append(sample)
    statistics_payload: list[dict[str, object]] = []
    for cell in sorted(groups):
        cell_samples = groups[cell]
        statistics_payload.append(
            {
                "scenario": cell[0],
                "surface": cell[1],
                "actor": cell[2],
                "section": cell[3],
                "viewport": cell[4],
                "sample_count": len(cell_samples),
                "unexpected_error_count": sum(
                    1 for sample in cell_samples if sample["unexpected_error"]
                ),
                "expected_503_count": sum(
                    1 for sample in cell_samples if sample["expected_503"]
                ),
                "metrics": {
                    metric: _metric_summary(
                        [sample[metric] for sample in cell_samples]  # type: ignore[list-item]
                    )
                    for metric in SUMMARY_METRICS
                },
            }
        )
    return statistics_payload


def live_pressure_summary(
    samples: Sequence[Mapping[str, object]],
    intervals_ms: Mapping[str, int],
) -> list[dict[str, object]]:
    ordered = validate_attempt_ledger(samples)
    groups: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for sample in ordered:
        if sample["sample_phase"] != "measured" or not str(sample["scenario"]).startswith("ordinary_"):
            continue
        if sample["surface"] not in {"session-live", "combat-live"}:
            continue
        groups.setdefault((str(sample["scenario"]), str(sample["actor"])), []).append(sample)
    expected_actors = {actor for _scenario, actor in groups}
    if set(intervals_ms) != expected_actors:
        raise ContractError("live active-interval ledger differs from sampler actors")
    result: list[dict[str, object]] = []
    for (scenario, actor), group in sorted(groups.items()):
        interval = strict_number(
            intervals_ms[actor],
            label="live active interval",
            integer=True,
        )
        if interval == 0:
            raise ContractError("live active interval must be positive")
        requests_per_minute = 60000.0 / float(interval)
        mean_server_ms = sum(float(sample["server_ms"]) for sample in group) / len(group)
        mean_bytes = sum(float(sample["response_bytes"]) for sample in group) / len(group)
        result.append(
            {
                "scenario": scenario,
                "actor": actor,
                "sample_count": len(group),
                "active_interval_ms": interval,
                "request_ms": _metric_summary([sample["request_ms"] for sample in group]),
                "server_ms": _metric_summary([sample["server_ms"] for sample in group]),
                "response_bytes": _metric_summary([sample["response_bytes"] for sample in group]),
                "requests_per_minute": round(requests_per_minute, 3),
                "projected_server_ms_per_minute": round(mean_server_ms * requests_per_minute, 3),
                "projected_response_bytes_per_minute": round(mean_bytes * requests_per_minute, 3),
            }
        )
    return result


def render_summary_markdown(
    samples: Sequence[Mapping[str, object]],
    baseline: Mapping[str, object],
) -> str:
    measured = [sample for sample in samples if sample["sample_phase"] == "measured"]
    by_scenario: dict[str, list[Mapping[str, object]]] = {}
    for sample in measured:
        by_scenario.setdefault(str(sample["scenario"]), []).append(sample)
    lines = [
        "# Character read performance baseline",
        "",
        f"Baseline frozen: {'yes' if baseline['baseline_frozen'] else 'no'}.",
        f"Planned attempts recorded: {baseline['attempt_count']}.",
        f"Unexpected errors: {baseline['unexpected_error_count']}.",
        "Optimization success claimed: no.",
        "",
        "| Scenario | Measured | Request p95 ms | Server p95 ms | Apply p95 ms | Expected 503 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in sorted(by_scenario):
        group = by_scenario[scenario]
        lines.append(
            "| "
            + " | ".join(
                (
                    scenario,
                    str(len(group)),
                    f"{linear_percentile([sample['request_ms'] for sample in group], 95):.3f}",
                    f"{linear_percentile([sample['server_ms'] for sample in group], 95):.3f}",
                    f"{linear_percentile([sample['apply_ms'] for sample in group], 95):.3f}",
                    str(sum(1 for sample in group if sample["expected_503"])),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def publish_baseline_evidence(
    repo_root: Path,
    evidence_root: Path,
    run_id: str,
    samples: Sequence[Mapping[str, object]],
    bootstrap: RuntimeBootstrap,
    live_intervals_ms: Mapping[str, int],
    browser_identity: Mapping[str, object],
    git_identity: Mapping[str, str],
    fixture_proof: Mapping[str, object],
) -> Path:
    ordered = validate_attempt_ledger(samples)
    baseline = evaluate_baseline_freeze(ordered, safety_findings=())
    if not baseline["baseline_frozen"]:
        raise ContractError("baseline cannot be frozen")
    samples_payload: dict[str, object] = {
        "schema": SCHEMA,
        "attempt_count": len(ordered),
        "samples": list(ordered),
    }
    acceptance_payload: dict[str, object] = {
        "schema": SCHEMA,
        "contract": acceptance_contract(),
        "baseline": baseline,
        "scenario_statistics": scenario_statistics(ordered),
        "live_pressure": live_pressure_summary(ordered, live_intervals_ms),
    }
    summary_markdown = render_summary_markdown(ordered, baseline)
    safety_payload: dict[str, object] = {
        "schema": SCHEMA,
        "clean": True,
        "finding_count": 0,
        "scanned_artifact_count": len(ARTIFACT_ORDER),
        "scan_profile": "strict-semantic-v1",
    }
    artifact_bytes = {
        "samples.json": canonical_json_bytes(samples_payload),
        "summary.md": summary_markdown.encode("utf-8"),
        "acceptance.json": canonical_json_bytes(acceptance_payload),
        "safety-scan.json": canonical_json_bytes(safety_payload),
    }
    artifact_hashes = {
        artifact: hashlib.sha256(payload).hexdigest()
        for artifact, payload in artifact_bytes.items()
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "artifact_count": len(ARTIFACT_ORDER),
        "manifest_written_last": True,
        "artifact_sha256_scope": list(PRE_MANIFEST_ARTIFACTS),
        "artifact_sha256": artifact_hashes,
        "git_identity": dict(git_identity),
        "harness_sha256": _sha256_file(repo_root / "scripts" / "measure_character_read_performance.py"),
        "fixture_proof": dict(fixture_proof),
        "runtime_fixture_proof": dict(bootstrap.fixture_proof),
        "synthetic_fixture_proof": dict(bootstrap.xianxia_proof),
        "environment": environment_manifest(repo_root, browser_identity),
        "actor_matrix": [asdict(actor) for actor in ACTORS],
        "viewport_matrix": [asdict(viewport) for viewport in VIEWPORTS],
        "attempt_count": len(ordered),
        "schedule_sha256": hashlib.sha256(
            canonical_json_bytes({"attempts": schedule_manifest()})
        ).hexdigest(),
    }
    scan_subject = {
        "samples_artifact": samples_payload,
        "summary_artifact": summary_markdown,
        "acceptance_artifact": acceptance_payload,
        "safety_scan_artifact": safety_payload,
        "manifest_artifact": manifest,
    }
    findings = privacy_findings(scan_subject)
    if findings:
        raise ContractError("retained evidence failed the final privacy scan")

    require_unchanged_git_identity(repo_root, git_identity)
    envelope = EvidenceEnvelope(repo_root, evidence_root, run_id)
    envelope.write_json("samples.json", samples_payload)
    envelope.write_summary(summary_markdown)
    envelope.write_json("acceptance.json", acceptance_payload)
    envelope.write_json("safety-scan.json", safety_payload)
    for artifact, expected_digest in artifact_hashes.items():
        if _sha256_file(envelope.staging / artifact) != expected_digest:
            raise EvidenceRefusal("serialized artifact hash differs before sealing")
    return envelope.seal(manifest)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect the fixed local Character-read baseline.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evidence-root", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if sys.version_info[:3] != (3, 12, 12):
            raise ContractError("canonical CPython 3.12.12 is required")
        validate_run_id(args.run_id)
        repo_root = Path(__file__).resolve().parents[1]
        git_identity = require_clean_detached_git_identity(repo_root)
        fixture_proof = prove_git_object_fixture(repo_root)
        runtime_parent = repo_root / ".local"
        os.makedirs(_filesystem_path(runtime_parent), exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="character-read-runtime-",
            # The wrapper requires a physical short root. Keep the runtime
            # path in native spelling because SQLite URI readiness checks do
            # not accept a Windows extended-path prefix.
            dir=os.fspath(runtime_parent),
        ) as temporary_root:
            samples, bootstrap, intervals, browser_identity = asyncio.run(
                collect_runtime_baseline(repo_root, Path(temporary_root))
            )
            publish_baseline_evidence(
                repo_root,
                Path(args.evidence_root),
                args.run_id,
                samples,
                bootstrap,
                intervals,
                browser_identity,
                git_identity,
                fixture_proof,
            )
    except (ContractError, EvidenceRefusal):
        sys.stderr.write("Character-read baseline refused by its fixed contract.\n")
        return 2
    except Exception:
        sys.stderr.write("Character-read baseline failed without publishing evidence.\n")
        return 3
    sys.stdout.write("Character-read baseline evidence sealed.\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
