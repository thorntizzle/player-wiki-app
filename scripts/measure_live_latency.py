from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import statistics
from typing import Any
from urllib.parse import urlencode, urljoin


DEFAULT_SAMPLE_COUNTS = {
    "local": {"warmup": 1, "cold": 8, "steady": 12, "cold_apply": 6, "preview": 12},
    "fly": {"warmup": 1, "cold": 4, "steady": 6, "cold_apply": 3, "preview": 6},
}

LEGACY_REQUESTS_PER_MINUTE = {
    "combat": 60.0,
    "combat_status": 60.0,
    "combat_character": 60.0,
    "session": 20.0,
}


@dataclass(frozen=True)
class SurfaceSpec:
    name: str
    page_path_template: str
    root_selector: str
    metric_view: str
    kind: str
    required: bool = True


SURFACE_SPECS = (
    SurfaceSpec(
        name="combat",
        page_path_template="/campaigns/{campaign}/combat",
        root_selector="[data-combat-live-root]",
        metric_view="combat",
        kind="live",
    ),
    SurfaceSpec(
        name="combat_status",
        page_path_template="/campaigns/{campaign}/combat/status",
        root_selector="[data-combat-status-live-root]",
        metric_view="combat_status",
        kind="live",
    ),
    SurfaceSpec(
        name="session",
        page_path_template="/campaigns/{campaign}/session",
        root_selector="[data-session-live-root]",
        metric_view="session",
        kind="live",
    ),
    SurfaceSpec(
        name="builder_create",
        page_path_template="/campaigns/{campaign}/characters/new",
        root_selector="[data-live-builder-root]",
        metric_view="builder_create",
        kind="builder",
    ),
    SurfaceSpec(
        name="combat_character",
        page_path_template="/campaigns/{campaign}/combat/character",
        root_selector="[data-combat-character-live-root]",
        metric_view="combat_character",
        kind="live",
        required=False,
    ),
)


def parse_server_timing(header_value: str) -> dict[str, float]:
    timings: dict[str, float] = {}
    for part in (header_value or "").split(","):
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


def percentile(values: list[float], pct: float) -> float | None:
    cleaned = sorted(float(value) for value in values if value is not None)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    rank = (len(cleaned) - 1) * pct
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return cleaned[lower_index]
    lower_value = cleaned[lower_index]
    upper_value = cleaned[upper_index]
    weight = rank - lower_index
    return lower_value + (upper_value - lower_value) * weight


def mean(values: list[float]) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return None
    return statistics.fmean(cleaned)


def round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def summarize_numeric(values: list[float]) -> dict[str, float | None]:
    return {
        "mean": round_metric(mean(values)),
        "p50": round_metric(percentile(values, 0.50)),
        "p95": round_metric(percentile(values, 0.95)),
    }


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    request_ms = [float(sample.get("requestMs", 0.0) or 0.0) for sample in samples]
    apply_ms = [float(sample.get("applyMs", 0.0) or 0.0) for sample in samples]
    payload_bytes = [float(sample.get("payloadBytes", 0.0) or 0.0) for sample in samples]
    query_count = [float(sample.get("queryCount", 0.0) or 0.0) for sample in samples]
    query_time_ms = [float(sample.get("queryTimeMs", 0.0) or 0.0) for sample in samples]
    request_time_ms = [float(sample.get("requestTimeMs", 0.0) or 0.0) for sample in samples]
    state_check_ms = [float(sample.get("serverTimingParsed", {}).get("state-check", 0.0) or 0.0) for sample in samples]
    db_ms = [float(sample.get("serverTimingParsed", {}).get("db", 0.0) or 0.0) for sample in samples]
    render_ms = [float(sample.get("serverTimingParsed", {}).get("render", 0.0) or 0.0) for sample in samples]
    total_ms = [float(sample.get("serverTimingParsed", {}).get("total", 0.0) or 0.0) for sample in samples]
    changed_count = sum(1 for sample in samples if bool(sample.get("changed")))
    return {
        "sample_count": len(samples),
        "changed_count": changed_count,
        "changed_ratio": round_metric(changed_count / len(samples) if samples else 0.0),
        "request_ms": summarize_numeric(request_ms),
        "apply_ms": summarize_numeric(apply_ms),
        "payload_bytes": summarize_numeric(payload_bytes),
        "query_count": summarize_numeric(query_count),
        "query_time_ms": summarize_numeric(query_time_ms),
        "request_time_ms": summarize_numeric(request_time_ms),
        "state_check_ms": summarize_numeric(state_check_ms),
        "db_ms": summarize_numeric(db_ms),
        "render_ms": summarize_numeric(render_ms),
        "total_ms": summarize_numeric(total_ms),
    }


def project_pressure(mean_payload_bytes: float, mean_request_time_ms: float, requests_per_minute: float) -> dict[str, float]:
    return {
        "requests_per_minute": round(requests_per_minute, 2),
        "payload_bytes_per_minute": round(mean_payload_bytes * requests_per_minute, 2),
        "server_ms_per_minute": round(mean_request_time_ms * requests_per_minute, 2),
    }


def build_checklist_evaluation(surface_reports: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    evaluations: dict[str, dict[str, Any]] = {}
    tracked_surfaces = ("combat", "combat_status", "session")
    live_surfaces = ("combat", "combat_status", "session", "combat_character")

    for surface_name in tracked_surfaces:
        surface_report = surface_reports.get(surface_name)
        if not surface_report:
            continue
        cold_summary = surface_report["scenarios"].get("cold", {}).get("summary", {})
        steady_summary = surface_report["scenarios"].get("steady", {}).get("summary", {})
        pressure = surface_report.get("pressure_projection", {})
        cold_payload = float(cold_summary.get("payload_bytes", {}).get("mean") or 0.0)
        steady_payload = float(steady_summary.get("payload_bytes", {}).get("mean") or 0.0)
        steady_render_p95 = float(steady_summary.get("render_ms", {}).get("p95") or 0.0)
        idle_projection = pressure.get("current_idle", {})
        active_projection = pressure.get("current_active", {})
        legacy_projection = pressure.get("legacy", {})
        payload_reduction_ratio = 0.0
        if cold_payload > 0:
            payload_reduction_ratio = 1.0 - (steady_payload / cold_payload)
        evaluations[surface_name] = {
            "payload_reduction_ratio": round(payload_reduction_ratio, 4),
            "payload_reduction_pass": payload_reduction_ratio >= 0.80,
            "steady_render_p95_ms": round(steady_render_p95, 2),
            "steady_render_pass": steady_render_p95 <= 1.0,
            "active_server_pass": float(active_projection.get("server_ms_per_minute") or 0.0)
            < float(legacy_projection.get("server_ms_per_minute") or 0.0),
            "active_payload_pass": float(active_projection.get("payload_bytes_per_minute") or 0.0)
            < float(legacy_projection.get("payload_bytes_per_minute") or 0.0),
        }

    for surface_name in live_surfaces:
        surface_report = surface_reports.get(surface_name)
        if not surface_report:
            continue
        pressure = surface_report.get("pressure_projection", {})
        idle_projection = pressure.get("current_idle")
        legacy_projection = pressure.get("legacy")
        if not idle_projection or not legacy_projection:
            continue
        target = evaluations.setdefault(surface_name, {})
        target["idle_server_pass"] = float(idle_projection.get("server_ms_per_minute") or 0.0) < float(
            legacy_projection.get("server_ms_per_minute") or 0.0
        )
        target["idle_payload_pass"] = float(idle_projection.get("payload_bytes_per_minute") or 0.0) < float(
            legacy_projection.get("payload_bytes_per_minute") or 0.0
        )

    return evaluations


def format_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    separator = ["---"] * len(header)
    body = rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Live Latency Measurement Report",
        "",
        f"- Base URL: `{report['base_url']}`",
        f"- Campaign: `{report['campaign']}`",
        f"- Mode: `{report['mode']}`",
        f"- Run timestamp (UTC): `{report['run_started_at']}`",
        "",
        "## Latency Summary",
        "",
    ]

    latency_rows = [
        [
            "Surface",
            "Scenario",
            "Samples",
            "Changed %",
            "p50 Request ms",
            "p95 Request ms",
            "p50 DB ms",
            "p95 DB ms",
            "p50 Render ms",
            "p95 Render ms",
            "p50 Apply ms",
            "p95 Apply ms",
            "p50 Payload bytes",
        ]
    ]
    for surface_name, surface_report in report["surfaces"].items():
        for scenario_name, scenario_report in surface_report["scenarios"].items():
            summary = scenario_report["summary"]
            latency_rows.append(
                [
                    surface_name,
                    scenario_name,
                    str(summary["sample_count"]),
                    str(summary["changed_ratio"]),
                    str(summary["request_ms"]["p50"]),
                    str(summary["request_ms"]["p95"]),
                    str(summary["db_ms"]["p50"]),
                    str(summary["db_ms"]["p95"]),
                    str(summary["render_ms"]["p50"]),
                    str(summary["render_ms"]["p95"]),
                    str(summary["apply_ms"]["p50"]),
                    str(summary["apply_ms"]["p95"]),
                    str(summary["payload_bytes"]["p50"]),
                ]
            )
    lines.extend([format_table(latency_rows), "", "## Pressure Projection", ""])

    pressure_rows = [
        [
            "Surface",
            "Profile",
            "Req/min",
            "Payload bytes/min",
            "Server ms/min",
        ]
    ]
    for surface_name, surface_report in report["surfaces"].items():
        for profile_name, projection in surface_report.get("pressure_projection", {}).items():
            pressure_rows.append(
                [
                    surface_name,
                    profile_name,
                    str(projection["requests_per_minute"]),
                    str(projection["payload_bytes_per_minute"]),
                    str(projection["server_ms_per_minute"]),
                ]
            )
    lines.extend([format_table(pressure_rows), "", "## Checklist Evaluation", ""])

    evaluation_rows = [
        [
            "Surface",
            "80% Smaller",
            "Near-zero Render",
            "Idle Payload Lower",
            "Idle Server Lower",
            "Active Payload Lower",
            "Active Server Lower",
        ]
    ]
    for surface_name, evaluation in report["checklist_evaluation"].items():
        evaluation_rows.append(
            [
                surface_name,
                "yes" if evaluation.get("payload_reduction_pass") else "no",
                "yes" if evaluation.get("steady_render_pass") else "no",
                "yes" if evaluation.get("idle_payload_pass") else "no",
                "yes" if evaluation.get("idle_server_pass") else "no",
                "yes" if evaluation.get("active_payload_pass") else "no",
                "yes" if evaluation.get("active_server_pass") else "no",
            ]
        )
    lines.extend([format_table(evaluation_rows), ""])

    if report.get("notes"):
        lines.extend(["## Notes", ""])
        for note in report["notes"]:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure live latency and pressure for live app surfaces.")
    parser.add_argument("--base-url", required=True, help="Root URL for the running app, for example http://127.0.0.1:5000")
    parser.add_argument("--campaign", required=True, help="Campaign slug to measure")
    parser.add_argument("--mode", required=True, choices=("local", "fly"), help="Measurement profile to use")
    parser.add_argument("--output-dir", required=True, help="Directory for raw JSON and markdown summary output")
    parser.add_argument(
        "--combat-character-slug",
        default="",
        help="Optional character slug to target for the combat character surface, for example zigzag-blackscar",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def build_surface_path(spec: SurfaceSpec, campaign_slug: str, combat_character_slug: str = "") -> str:
    page_path = spec.page_path_template.format(campaign=campaign_slug)
    if spec.name == "combat_character" and combat_character_slug.strip():
        query = urlencode({"character": combat_character_slug.strip()})
        return f"{page_path}?{query}"
    return page_path


def collect_dataset(page, selector: str) -> dict[str, str]:
    return page.locator(selector).evaluate(
        """(node) => {
            const result = {};
            for (const [key, value] of Object.entries(node.dataset || {})) {
              result[key] = String(value || "");
            }
            return result;
        }"""
    )


def normalize_sample(sample: dict[str, Any], *, scenario: str, surface_name: str) -> dict[str, Any]:
    normalized = dict(sample or {})
    normalized["surface"] = surface_name
    normalized["scenario"] = scenario
    normalized["serverTimingParsed"] = parse_server_timing(str(normalized.get("serverTiming", "") or ""))
    for key in ("requestMs", "applyMs", "queryTimeMs", "requestTimeMs"):
        normalized[key] = round_metric(float(normalized.get(key, 0.0) or 0.0)) or 0.0
    for key in ("payloadBytes", "queryCount", "liveRevision"):
        try:
            normalized[key] = int(float(normalized.get(key, 0) or 0))
        except (TypeError, ValueError):
            normalized[key] = 0
    normalized["changed"] = bool(normalized.get("changed"))
    return normalized


def build_pressure_projection(surface_name: str, dataset: dict[str, str], scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    legacy_req_per_min = LEGACY_REQUESTS_PER_MINUTE.get(surface_name)
    if legacy_req_per_min is None:
        return {}
    active_interval_ms = int(dataset.get("liveActiveIntervalMs", "0") or 0)
    idle_interval_ms = int(dataset.get("liveIdleIntervalMs", "0") or 0)
    steady_samples = scenarios.get("steady", {}).get("samples", [])
    steady_unchanged = [sample for sample in steady_samples if not sample.get("changed")]
    projection_samples = steady_unchanged or steady_samples
    cold_summary = scenarios["cold"]["summary"]
    steady_summary = summarize_samples(projection_samples)
    cold_payload_mean = float(cold_summary["payload_bytes"]["mean"] or 0.0)
    cold_request_mean = float(cold_summary["request_time_ms"]["mean"] or 0.0)
    steady_payload_mean = float(steady_summary["payload_bytes"]["mean"] or 0.0)
    steady_request_mean = float(steady_summary["request_time_ms"]["mean"] or 0.0)
    result = {
        "legacy": project_pressure(cold_payload_mean, cold_request_mean, legacy_req_per_min),
        "current_active": project_pressure(
            steady_payload_mean,
            steady_request_mean,
            60000.0 / active_interval_ms if active_interval_ms > 0 else 0.0,
        ),
        "current_idle": project_pressure(
            steady_payload_mean,
            steady_request_mean,
            60000.0 / idle_interval_ms if idle_interval_ms > 0 else 0.0,
        ),
    }
    return result


def write_artifacts(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / f"{report['mode']}-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "samples.json"
    markdown_path = run_dir / "summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, markdown_path


def sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(urljoin(base_url, "/sign-in"), wait_until="domcontentloaded")
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="password"]').fill(password)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("domcontentloaded")
    if "/sign-in" in page.url:
        raise RuntimeError("Sign-in did not complete. Check PLAYER_WIKI_MEASURE_EMAIL and PLAYER_WIKI_MEASURE_PASSWORD.")


def wait_for_sampler(page, metric_view: str) -> None:
    page.wait_for_function(
        """(metricView) => Boolean(
            window.__playerWikiLiveDiagnostics &&
            window.__playerWikiLiveDiagnostics[metricView] &&
            typeof window.__playerWikiLiveDiagnostics[metricView].sample === "function"
        )""",
        arg=metric_view,
        timeout=10000,
    )


def run_surface_samples(page, metric_view: str, scenario: str, count: int, *, force_apply: bool = False) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for _ in range(count):
        result = page.evaluate(
            """async ({ metricView, scenarioName, forceApply }) => {
                const sampler = window.__playerWikiLiveDiagnostics?.[metricView]?.sample;
                if (typeof sampler !== "function") {
                  return null;
                }
                return await sampler({
                  mode: scenarioName === "cold" || scenarioName === "cold_apply" ? "cold" : "steady",
                  forceApply,
                  forceManager: forceApply,
                  forceComposer: forceApply,
                });
            }""",
            {
                "metricView": metric_view,
                "scenarioName": scenario,
                "forceApply": force_apply,
            },
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"Sampler for {metric_view} did not return a sample for scenario {scenario}.")
        samples.append(result)
        page.wait_for_timeout(100)
    return samples


def collect_surface_report(
    page,
    base_url: str,
    campaign_slug: str,
    spec: SurfaceSpec,
    sample_counts: dict[str, int],
    *,
    combat_character_slug: str = "",
) -> dict[str, Any] | None:
    page_path = build_surface_path(spec, campaign_slug, combat_character_slug)
    page.goto(urljoin(base_url, page_path), wait_until="domcontentloaded")
    try:
        page.wait_for_selector(spec.root_selector, timeout=10000)
    except Exception:
        if spec.required:
            raise RuntimeError(f"Could not find required live root {spec.root_selector} on {page_path}.")
        return None

    dataset = collect_dataset(page, spec.root_selector)
    if dataset.get("liveDiagnosticsEnabled") != "1":
        raise RuntimeError(
            f"Live diagnostics are disabled on {page_path}. Enable PLAYER_WIKI_LIVE_DIAGNOSTICS=1 on the target app first."
        )
    wait_for_sampler(page, spec.metric_view)

    scenarios: dict[str, dict[str, Any]] = {}
    if spec.kind == "builder":
        preview_samples = [
            normalize_sample(sample, scenario="preview", surface_name=spec.name)
            for sample in run_surface_samples(page, spec.metric_view, "preview", sample_counts["preview"])
        ]
        scenarios["preview"] = {
            "samples": preview_samples,
            "summary": summarize_samples(preview_samples),
        }
    else:
        if sample_counts["warmup"] > 0:
            run_surface_samples(page, spec.metric_view, "steady", sample_counts["warmup"])
        for scenario_name, force_apply in (("cold", False), ("steady", False), ("cold_apply", True)):
            scenario_samples = [
                normalize_sample(sample, scenario=scenario_name, surface_name=spec.name)
                for sample in run_surface_samples(
                    page,
                    spec.metric_view,
                    scenario_name,
                    sample_counts[scenario_name],
                    force_apply=force_apply,
                )
            ]
            scenarios[scenario_name] = {
                "samples": scenario_samples,
                "summary": summarize_samples(scenario_samples),
            }

    pressure_projection = build_pressure_projection(spec.name, dataset, scenarios) if spec.kind == "live" else {}
    return {
        "surface": spec.name,
        "page_path": page_path,
        "root_selector": spec.root_selector,
        "dataset": dataset,
        "scenarios": scenarios,
        "pressure_projection": pressure_projection,
    }


def collect_measurements(
    base_url: str,
    campaign_slug: str,
    mode: str,
    email: str,
    password: str,
    *,
    combat_character_slug: str = "",
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run `pip install -r requirements-dev.txt` first.") from exc

    sample_counts = DEFAULT_SAMPLE_COUNTS[mode]
    notes: list[str] = []
    surfaces: dict[str, dict[str, Any]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        sign_in(page, base_url, email, password)

        for spec in SURFACE_SPECS:
            surface_report = collect_surface_report(
                page,
                base_url,
                campaign_slug,
                spec,
                sample_counts,
                combat_character_slug=combat_character_slug,
            )
            if surface_report is None:
                notes.append(f"Skipped optional surface `{spec.name}` because its live root was not available.")
                continue
            surfaces[spec.name] = surface_report

        context.close()
        browser.close()

    report = {
        "base_url": base_url.rstrip("/"),
        "campaign": campaign_slug,
        "mode": mode,
        "run_started_at": datetime.now(UTC).isoformat(),
        "surfaces": surfaces,
        "checklist_evaluation": build_checklist_evaluation(surfaces),
        "notes": notes,
    }
    return report


def main() -> int:
    args = parse_args()
    email = require_env("PLAYER_WIKI_MEASURE_EMAIL")
    password = require_env("PLAYER_WIKI_MEASURE_PASSWORD")
    report = collect_measurements(
        base_url=args.base_url,
        campaign_slug=args.campaign,
        mode=args.mode,
        email=email,
        password=password,
        combat_character_slug=args.combat_character_slug,
    )
    json_path, markdown_path = write_artifacts(Path(args.output_dir), report)
    print(f"Wrote raw samples to {json_path}")
    print(f"Wrote summary report to {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
