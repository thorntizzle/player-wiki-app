"""Validate source inputs for the TypeScript cutover freeze/drift audit.

This helper is intentionally lightweight: it checks local tracked evidence files
and JSON parseability only. It does not start Flask or TypeScript, open SQLite,
contact Fly, or assert route parity semantics.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REQUIRED_MARKDOWN_SECTIONS = {
    "docs/current-state/INDEX.md": ["## Current-State Docs", "## Existing Contract Docs"],
    "docs/current-state/workspace-boundaries.md": [
        "## App/Vault Bridge",
        "## Permanent Worktree Contract",
    ],
    "docs/api-v1.md": ["# API v1", "## Auth"],
    "docs/typescript-backend-rewrite/README.md": ["## Source Of Truth"],
    "docs/typescript-backend-rewrite/charter.md": [
        "## Freeze And Dual-Maintenance Rules",
        "## Cutover Workflows",
        "## Rollback Requirement",
    ],
    "docs/typescript-backend-rewrite/cutover-readiness.md": [
        "## Gate Summary",
        "Freeze and dual-maintenance",
    ],
    "docs/typescript-backend-rewrite/cutover-freeze-drift-audit.md": [
        "## Owners",
        "## Evidence Inputs",
        "## Go/No-Go Gates",
        "## Late Flask Fixes",
    ],
    "docs/typescript-backend-rewrite/parity-inventory.md": [
        "## Inventory hardening summary",
        "## 1) API endpoint families",
        "## 2) Flask/browser compatibility route families",
        "## 6) Error and response contract families",
    ],
    "docs/typescript-backend-rewrite/route-snapshots.md": [
        "## `/api/v1` Route Snapshot",
        "## Flask Browser Compatibility Route Snapshot",
    ],
    "docs/typescript-backend-rewrite/route-drift-audit-2026-06-28.md": [
        "## Commands Run",
        "## Drift Findings",
        "## Remaining Follow-Up Lanes",
    ],
    "docs/typescript-backend-rewrite/rollback-cutover-runbook.md": [
        "## Purpose",
    ],
}

REQUIRED_EXISTING_PATHS = [
    "apps/api/src/routes.ts",
    "apps/api/tests/route-parity.mjs",
    "scripts/route_snapshots.py",
    "docs/typescript-backend-rewrite/route-snapshots.json",
    "docs/typescript-backend-rewrite/typescript-route-seed.json",
]

OPTIONAL_LOCAL_PATHS = [
    ".local/roadmaps/typescript-backend-rewrite-roadmap.md",
]

VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class AuditResult:
    failures: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_text(path: Path, failures: list[str]) -> str | None:
    if not path.exists():
        failures.append(f"missing required file: {path.as_posix()}")
        return None
    if not path.is_file():
        failures.append(f"required path is not a file: {path.as_posix()}")
        return None
    return path.read_text(encoding="utf-8")


def _load_json(path: Path, failures: list[str]) -> Any | None:
    text = _load_text(path, failures)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        failures.append(f"invalid JSON in {path.as_posix()}: {exc}")
        return None


def _validate_markdown_sections(root: Path, failures: list[str]) -> None:
    for relative_path, required_sections in REQUIRED_MARKDOWN_SECTIONS.items():
        path = root / relative_path
        text = _load_text(path, failures)
        if text is None:
            continue
        for section in required_sections:
            if section not in text:
                failures.append(
                    f"{relative_path} is missing expected section text: {section}"
                )


def _validate_required_paths(root: Path, failures: list[str]) -> None:
    for relative_path in REQUIRED_EXISTING_PATHS:
        path = root / relative_path
        if not path.is_file():
            failures.append(f"missing required file: {relative_path}")


def _validate_optional_paths(root: Path, warnings: list[str]) -> None:
    for relative_path in OPTIONAL_LOCAL_PATHS:
        path = root / relative_path
        if not path.exists():
            warnings.append(f"optional local file absent: {relative_path}")


def _validate_route_snapshot(root: Path, failures: list[str]) -> None:
    snapshot_path = root / "docs/typescript-backend-rewrite/route-snapshots.json"
    snapshot = _load_json(snapshot_path, failures)
    if snapshot is None:
        return
    for collection_name in ("api_v1_routes", "flask_routes"):
        routes = snapshot.get(collection_name)
        if not isinstance(routes, list) or not routes:
            failures.append(f"route-snapshots.json {collection_name} must be a non-empty list")
            continue
        for index, route in enumerate(routes):
            if not isinstance(route, dict):
                failures.append(f"{collection_name}[{index}] must be an object")
                continue
            for key in ("method", "path", "source_file", "route_family"):
                if not isinstance(route.get(key), str) or not route[key]:
                    failures.append(f"{collection_name}[{index}] missing string key {key}")
            method = str(route.get("method", "")).upper()
            if method and method not in VALID_METHODS:
                failures.append(f"{collection_name}[{index}] has unknown method {method}")


def _validate_route_seed(root: Path, failures: list[str]) -> None:
    seed_path = root / "docs/typescript-backend-rewrite/typescript-route-seed.json"
    seed = _load_json(seed_path, failures)
    if seed is None:
        return
    routes = seed.get("routes")
    if not isinstance(routes, list) or not routes:
        failures.append("typescript-route-seed.json routes must be a non-empty list")
        return
    statuses = set()
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            failures.append(f"typescript-route-seed.json routes[{index}] must be an object")
            continue
        for key in ("method", "path", "status"):
            if not isinstance(route.get(key), str) or not route[key]:
                failures.append(f"typescript-route-seed.json routes[{index}] missing string key {key}")
        method = str(route.get("method", "")).upper()
        if method and method not in VALID_METHODS:
            failures.append(f"typescript-route-seed.json routes[{index}] has unknown method {method}")
        status = route.get("status")
        if isinstance(status, str):
            statuses.add(status)
    if "deferred_scratch_proof" not in statuses:
        failures.append("typescript-route-seed.json must keep deferred_scratch_proof entries visible")


def run_audit(root: Path | None = None) -> AuditResult:
    root = root or repo_root()
    failures: list[str] = []
    warnings: list[str] = []

    _validate_required_paths(root, failures)
    _validate_optional_paths(root, warnings)
    _validate_markdown_sections(root, failures)
    _validate_route_snapshot(root, failures)
    _validate_route_seed(root, failures)

    return AuditResult(failures=failures, warnings=warnings)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate source inputs for the TypeScript cutover freeze/drift audit."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_audit()

    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "failures": result.failures,
                    "warnings": result.warnings,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for warning in result.warnings:
            print(f"WARNING: {warning}")
        if result.ok:
            print("Cutover freeze/drift source-input audit passed.")
        else:
            print("Cutover freeze/drift source-input audit failed.")
            for failure in result.failures:
                print(f"ERROR: {failure}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
