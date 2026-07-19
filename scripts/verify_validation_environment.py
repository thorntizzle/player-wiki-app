from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.version import Version


LOCK_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)(?:\s*;\s*(.*?))?\s*\\?\s*$"
)


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _locked_requirements(lock_path: Path) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = LOCK_REQUIREMENT.fullmatch(line.strip())
        if match is None:
            continue
        name, version, marker_text = match.groups()
        if marker_text and not Marker(marker_text.strip()).evaluate():
            continue
        requirements[_canonical_name(name)] = version
    if not requirements:
        raise ValueError("The development lock contains no applicable pinned requirements.")
    return requirements


def _dependency_mismatches(requirements: dict[str, str]) -> list[str]:
    mismatches: list[str] = []
    for name, expected in sorted(requirements.items()):
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(f"{name}: missing; expected {expected}")
            continue
        if Version(actual) != Version(expected):
            mismatches.append(f"{name}: installed {actual}; expected {expected}")
    return mismatches


def _metadata_dependency_errors(requirements: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for locked_name in sorted(requirements):
        try:
            distribution = importlib.metadata.distribution(locked_name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            try:
                installed = importlib.metadata.version(requirement.name)
            except importlib.metadata.PackageNotFoundError:
                errors.append(f"{locked_name} requires missing {requirement.name}")
                continue
            if requirement.specifier and not requirement.specifier.contains(
                installed,
                prereleases=True,
            ):
                errors.append(
                    f"{locked_name} requires {requirement}; installed {installed}"
                )
    return errors


def verify_environment(project_root: Path, *, run_pip_check: bool = True) -> dict[str, object]:
    root = project_root.resolve()
    version_path = root / ".python-version"
    lock_path = root / "requirements-dev.lock"
    expected_python = version_path.read_text(encoding="utf-8").strip()
    actual_python = platform.python_version()
    lock_bytes = lock_path.read_bytes()
    requirements = _locked_requirements(lock_path)
    mismatches = _dependency_mismatches(requirements)
    dependency_check = "not-run"
    dependency_check_errors: list[str] = []
    if run_pip_check:
        if importlib.util.find_spec("pip") is not None:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "check"],
                check=False,
                capture_output=True,
                text=True,
            )
            dependency_check = (result.stdout + result.stderr).strip() or "pip-ok"
            if result.returncode != 0:
                dependency_check_errors.append(f"pip check failed: {dependency_check}")
        else:
            dependency_check_errors = _metadata_dependency_errors(requirements)
            dependency_check = (
                "metadata-ok (pip unavailable)"
                if not dependency_check_errors
                else "metadata-failed (pip unavailable)"
            )

    errors: list[str] = []
    if actual_python != expected_python:
        errors.append(
            f"python: running {actual_python}; expected exact {expected_python} from .python-version"
        )
    errors.extend(mismatches)
    errors.extend(dependency_check_errors)

    return {
        "ok": not errors,
        "python_executable": sys.executable,
        "python_version": actual_python,
        "expected_python_version": expected_python,
        "requirements_lock": str(lock_path),
        "requirements_lock_sha256": hashlib.sha256(lock_bytes).hexdigest().upper(),
        "locked_requirements_checked": len(requirements),
        "dependency_check": dependency_check,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the exact CPW validation interpreter and development lock."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--skip-pip-check", action="store_true")
    arguments = parser.parse_args()
    try:
        manifest = verify_environment(
            arguments.project_root,
            run_pip_check=not arguments.skip_pip_check,
        )
    except (OSError, ValueError) as exc:
        manifest = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(manifest, sort_keys=True))
    if manifest["ok"]:
        return 0
    for error in manifest["errors"]:
        print(f"Canonical validation environment mismatch: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
