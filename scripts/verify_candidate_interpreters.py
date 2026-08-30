"""Verify the two explicit interpreter roles used by candidate-gate.

This helper is intentionally stdlib-only so the staging role can run from the
production-exact, pipless Python environment before any Docker work begins.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


HOST_MANIFEST_SCHEMA = "campaign-player-wiki.windows-host-environment/v1"
STAGING_CAPABILITIES = (
    "argparse",
    "hashlib",
    "json",
    "os",
    "pathlib",
    "re",
    "stat",
    "subprocess",
    "sys",
    "typing",
    "unicodedata",
)


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _load_host_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Windows host environment manifest must be a JSON object.")
    expected_keys = {
        "schema",
        "implementation",
        "python_version",
        "platform",
        "distributions",
    }
    if set(payload) != expected_keys:
        raise ValueError("Windows host environment manifest has unexpected or missing fields.")
    if payload["schema"] != HOST_MANIFEST_SCHEMA:
        raise ValueError("Windows host environment manifest schema is unsupported.")
    for key in ("implementation", "python_version", "platform"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ValueError(f"Windows host environment manifest {key} is invalid.")
    distributions = payload["distributions"]
    if not isinstance(distributions, list) or not distributions:
        raise ValueError("Windows host environment manifest distributions must be nonempty.")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in distributions:
        if not isinstance(entry, dict) or set(entry) != {"name", "version"}:
            raise ValueError("Windows host environment manifest distribution is invalid.")
        name = entry["name"]
        version = entry["version"]
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise ValueError("Windows host environment manifest distribution is invalid.")
        canonical = _canonical_distribution_name(name)
        if canonical != name or canonical in seen:
            raise ValueError(
                "Windows host environment manifest distribution names must be unique and canonical."
            )
        seen.add(canonical)
        normalized.append({"name": name, "version": version})
    if normalized != sorted(normalized, key=lambda entry: entry["name"]):
        raise ValueError("Windows host environment manifest distributions must be sorted.")
    return payload


def _installed_distributions() -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name or not distribution.version:
            raise ValueError("Installed distribution metadata is incomplete.")
        name = _canonical_distribution_name(raw_name)
        if name in installed:
            raise ValueError(f"Installed distribution name is duplicated: {name}")
        installed[name] = distribution.version
    return installed


def _pip_check() -> tuple[str, list[str]]:
    if importlib.util.find_spec("pip") is None:
        return "unavailable", ["pip is unavailable in the Windows host interpreter"]
    completed = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    detail = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        bounded = detail[:1000] or f"exit {completed.returncode}"
        return "failed", [f"pip check failed: {bounded}"]
    return detail or "pip-ok", []


def _sqlite_probe() -> str:
    sqlite3 = importlib.import_module("sqlite3")
    with sqlite3.connect(":memory:") as connection:
        value = connection.execute("SELECT sqlite_version()").fetchone()[0]
    return str(value)


def verify_staging(project_root: Path) -> dict[str, Any]:
    expected_version = (project_root / ".python-version").read_text(encoding="utf-8").strip()
    errors: list[str] = []
    implementation = platform.python_implementation()
    version = platform.python_version()
    if implementation != "CPython":
        errors.append(f"implementation: running {implementation}; expected CPython")
    if version != expected_version:
        errors.append(f"python: running {version}; expected exact {expected_version} from .python-version")
    unavailable: list[str] = []
    for module_name in STAGING_CAPABILITIES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - defensive around interpreter policy
            unavailable.append(f"{module_name}: {type(exc).__name__}: {exc}")
    if unavailable:
        errors.append("stdlib capabilities unavailable: " + "; ".join(unavailable))
    return {
        "ok": not errors,
        "role": "staging",
        "python_executable": sys.executable,
        "implementation": implementation,
        "python_version": version,
        "expected_python_version": expected_version,
        "stdlib_capabilities": list(STAGING_CAPABILITIES),
        "errors": errors,
    }


def verify_windows_host(project_root: Path) -> dict[str, Any]:
    manifest_path = project_root / "validation" / "windows-host-environment.json"
    manifest = _load_host_manifest(manifest_path)
    errors: list[str] = []
    implementation = platform.python_implementation()
    version = platform.python_version()
    current_platform = sys.platform
    for label, actual, expected in (
        ("implementation", implementation, manifest["implementation"]),
        ("python", version, manifest["python_version"]),
        ("platform", current_platform, manifest["platform"]),
    ):
        if actual != expected:
            errors.append(f"{label}: running {actual}; expected exact {expected}")

    expected_distributions = {
        entry["name"]: entry["version"] for entry in manifest["distributions"]
    }
    installed_distributions = _installed_distributions()
    for name in sorted(expected_distributions.keys() - installed_distributions.keys()):
        errors.append(f"distribution {name}: missing; expected {expected_distributions[name]}")
    for name in sorted(installed_distributions.keys() - expected_distributions.keys()):
        errors.append(f"distribution {name}: unexpected {installed_distributions[name]}")
    for name in sorted(expected_distributions.keys() & installed_distributions.keys()):
        if installed_distributions[name] != expected_distributions[name]:
            errors.append(
                f"distribution {name}: installed {installed_distributions[name]}; "
                f"expected {expected_distributions[name]}"
            )

    sqlite_version = "unavailable"
    try:
        sqlite_version = _sqlite_probe()
    except Exception as exc:
        errors.append(f"SQLite import/probe failed: {type(exc).__name__}: {exc}")

    pip_check, pip_errors = _pip_check()
    errors.extend(pip_errors)
    return {
        "ok": not errors,
        "role": "windows-host",
        "python_executable": sys.executable,
        "implementation": implementation,
        "python_version": version,
        "platform": current_platform,
        "manifest": str(manifest_path),
        "distributions_checked": len(expected_distributions),
        "sqlite_version": sqlite_version,
        "pip_check": pip_check,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify candidate-gate interpreter roles.")
    parser.add_argument("--role", choices=("staging", "windows-host"), required=True)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    arguments = parser.parse_args()
    try:
        if arguments.role == "staging":
            result = verify_staging(arguments.project_root.resolve())
        else:
            result = verify_windows_host(arguments.project_root.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "role": arguments.role, "errors": [str(exc)]}
    print(json.dumps(result, sort_keys=True))
    if result["ok"]:
        return 0
    for error in result["errors"]:
        print(f"Candidate {arguments.role} interpreter refusal: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
