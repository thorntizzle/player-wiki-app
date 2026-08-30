from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_candidate_interpreters as interpreters


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_candidate_interpreters.py"


def _manifest(root: Path, *, distributions: list[dict[str, str]] | None = None) -> Path:
    path = root / "validation" / "windows-host-environment.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema": interpreters.HOST_MANIFEST_SCHEMA,
                "implementation": "CPython",
                "python_version": "3.14.2",
                "platform": "win32",
                "distributions": distributions
                or [
                    {"name": "pip", "version": "25.3"},
                    {"name": "pytest", "version": "8.4.2"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_staging_role_requires_exact_cpython_and_only_stdlib_capabilities(tmp_path, monkeypatch):
    (tmp_path / ".python-version").write_text("3.12.12\n", encoding="utf-8")
    monkeypatch.setattr(interpreters.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(interpreters.platform, "python_version", lambda: "3.12.12")

    result = interpreters.verify_staging(tmp_path)

    assert result["ok"] is True
    assert result["expected_python_version"] == "3.12.12"
    assert result["stdlib_capabilities"] == list(interpreters.STAGING_CAPABILITIES)
    assert "sqlite3" not in result["stdlib_capabilities"]
    assert "pip" not in result["stdlib_capabilities"]


@pytest.mark.parametrize(
    ("implementation", "version", "expected"),
    (
        ("PyPy", "3.12.12", "expected CPython"),
        ("CPython", "3.12.11", "expected exact 3.12.12"),
    ),
)
def test_staging_role_refuses_implementation_or_version_drift(
    tmp_path, monkeypatch, implementation, version, expected
):
    (tmp_path / ".python-version").write_text("3.12.12\n", encoding="utf-8")
    monkeypatch.setattr(interpreters.platform, "python_implementation", lambda: implementation)
    monkeypatch.setattr(interpreters.platform, "python_version", lambda: version)

    result = interpreters.verify_staging(tmp_path)

    assert result["ok"] is False
    assert any(expected in error for error in result["errors"])


def test_staging_role_refuses_missing_required_stdlib_capability(tmp_path, monkeypatch):
    (tmp_path / ".python-version").write_text(platform.python_version() + "\n", encoding="utf-8")
    original_import = interpreters.importlib.import_module

    def import_module(name: str):
        if name == "unicodedata":
            raise ImportError("blocked by fixture")
        return original_import(name)

    monkeypatch.setattr(interpreters.importlib, "import_module", import_module)

    result = interpreters.verify_staging(tmp_path)

    assert result["ok"] is False
    assert any("unicodedata: ImportError" in error for error in result["errors"])


def _host_dependencies(monkeypatch, installed: dict[str, str]) -> None:
    monkeypatch.setattr(interpreters.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(interpreters.platform, "python_version", lambda: "3.14.2")
    monkeypatch.setattr(interpreters.sys, "platform", "win32")
    monkeypatch.setattr(interpreters, "_installed_distributions", lambda: installed)
    monkeypatch.setattr(interpreters, "_sqlite_probe", lambda: "3.50.4")
    monkeypatch.setattr(interpreters, "_pip_check", lambda: ("pip-ok", []))


def test_windows_host_role_accepts_exact_manifest_sqlite_and_pip(tmp_path, monkeypatch):
    _manifest(tmp_path)
    _host_dependencies(monkeypatch, {"pip": "25.3", "pytest": "8.4.2"})

    result = interpreters.verify_windows_host(tmp_path)

    assert result["ok"] is True
    assert result["distributions_checked"] == 2
    assert result["sqlite_version"] == "3.50.4"
    assert result["pip_check"] == "pip-ok"


@pytest.mark.parametrize(
    ("installed", "expected"),
    (
        ({"pip": "25.3"}, "distribution pytest: missing"),
        (
            {"pip": "25.3", "pytest": "8.4.1"},
            "distribution pytest: installed 8.4.1; expected 8.4.2",
        ),
        (
            {"extra": "1", "pip": "25.3", "pytest": "8.4.2"},
            "distribution extra: unexpected 1",
        ),
    ),
)
def test_windows_host_role_refuses_exact_distribution_drift(
    tmp_path, monkeypatch, installed, expected
):
    _manifest(tmp_path)
    _host_dependencies(monkeypatch, installed)

    result = interpreters.verify_windows_host(tmp_path)

    assert result["ok"] is False
    assert any(expected in error for error in result["errors"])


def test_windows_host_role_refuses_version_platform_sqlite_and_pip(tmp_path, monkeypatch):
    _manifest(tmp_path)
    _host_dependencies(monkeypatch, {"pip": "25.3", "pytest": "8.4.2"})
    monkeypatch.setattr(interpreters.platform, "python_implementation", lambda: "PyPy")
    monkeypatch.setattr(interpreters.platform, "python_version", lambda: "3.14.1")
    monkeypatch.setattr(interpreters.sys, "platform", "linux")

    def sqlite_refusal():
        raise ImportError("policy blocked")

    monkeypatch.setattr(interpreters, "_sqlite_probe", sqlite_refusal)
    monkeypatch.setattr(
        interpreters,
        "_pip_check",
        lambda: ("failed", ["pip check failed: fixture conflict"]),
    )

    result = interpreters.verify_windows_host(tmp_path)

    assert result["ok"] is False
    assert any("implementation: running PyPy" in error for error in result["errors"])
    assert any("expected exact 3.14.2" in error for error in result["errors"])
    assert any("platform: running linux" in error for error in result["errors"])
    assert any("SQLite import/probe failed" in error for error in result["errors"])
    assert "pip check failed: fixture conflict" in result["errors"]


def test_windows_host_manifest_requires_sorted_canonical_unique_distributions(tmp_path):
    manifest = _manifest(
        tmp_path,
        distributions=[
            {"name": "pytest", "version": "8.4.2"},
            {"name": "Pip", "version": "25.3"},
        ],
    )

    with pytest.raises(ValueError, match="unique and canonical|sorted"):
        interpreters._load_host_manifest(manifest)


def test_pip_check_refuses_missing_pip(monkeypatch):
    monkeypatch.setattr(interpreters.importlib.util, "find_spec", lambda _name: None)

    status, errors = interpreters._pip_check()

    assert status == "unavailable"
    assert errors == ["pip is unavailable in the Windows host interpreter"]


@pytest.mark.windows_host
def test_tracked_windows_host_manifest_matches_actual_authorized_interpreter():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--role",
            "windows-host",
            "--project-root",
            str(PROJECT_ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["python_version"] == "3.14.2"
    assert result["sqlite_version"] != "unavailable"
    assert result["pip_check"] == "No broken requirements found."
