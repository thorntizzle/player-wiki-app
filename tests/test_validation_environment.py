from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_validation_environment.py"


def _project(tmp_path: Path, *, python_version: str, requirement: str) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".python-version").write_text(f"{python_version}\n", encoding="utf-8")
    (root / "requirements-dev.lock").write_text(
        f"{requirement} \\\n    --hash=sha256:{'0' * 64}\n",
        encoding="utf-8",
    )
    return root


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(root),
            "--skip-pip-check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validation_environment_reports_exact_version_lock_and_dependency(tmp_path):
    pytest_version = importlib.metadata.version("pytest")
    root = _project(
        tmp_path,
        python_version=platform.python_version(),
        requirement=f"pytest=={pytest_version}",
    )

    result = _run(root)

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["ok"] is True
    assert manifest["python_version"] == platform.python_version()
    assert manifest["expected_python_version"] == platform.python_version()
    assert manifest["locked_requirements_checked"] == 1
    assert len(manifest["requirements_lock_sha256"]) == 64
    assert manifest["errors"] == []


def test_validation_environment_rejects_interpreter_drift(tmp_path):
    pytest_version = importlib.metadata.version("pytest")
    root = _project(
        tmp_path,
        python_version="0.0.0",
        requirement=f"pytest=={pytest_version}",
    )

    result = _run(root)

    assert result.returncode == 1
    manifest = json.loads(result.stdout)
    assert manifest["ok"] is False
    assert any("expected exact 0.0.0" in error for error in manifest["errors"])


def test_validation_environment_rejects_lock_drift(tmp_path):
    root = _project(
        tmp_path,
        python_version=platform.python_version(),
        requirement="pytest==0.0.0",
    )

    result = _run(root)

    assert result.returncode == 1
    manifest = json.loads(result.stdout)
    assert manifest["ok"] is False
    assert any("pytest: installed" in error for error in manifest["errors"])
