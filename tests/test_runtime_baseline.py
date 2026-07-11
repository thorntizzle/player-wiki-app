from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import Flask
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


pytestmark = pytest.mark.contract

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = (
    PROJECT_ROOT / "requirements-prod.lock",
    PROJECT_ROOT / "requirements-dev.lock",
)
REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)==(?P<version>[^ ;]+)"
    r"(?P<marker> ; .+)?$"
)
HASH_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}")


def _powershell_function_body(script: str, name: str) -> str:
    start = script.index(f"function {name} {{")
    opening_brace = script.index("{", start)
    depth = 0
    for index in range(opening_brace, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[opening_brace + 1 : index]
    raise AssertionError(f"PowerShell function {name} is not balanced")


def _lock_entries(path: Path) -> dict[str, tuple[str, str, frozenset[str]]]:
    text = path.read_text(encoding="utf-8")
    blocks: list[str] = []
    current: list[str] = []

    for line in text.splitlines():
        if line and not line[0].isspace():
            if current:
                blocks.append(" ".join(current))
            current = [line.removesuffix("\\").rstrip()]
        elif line.strip():
            current.append(line.strip().removesuffix("\\").rstrip())
    if current:
        blocks.append(" ".join(current))

    entries: dict[str, tuple[str, str, frozenset[str]]] = {}
    for block in blocks:
        hashes = frozenset(HASH_RE.findall(block))
        requirement_text = block.split(" --hash=", 1)[0]
        match = REQUIREMENT_RE.fullmatch(requirement_text)
        assert match, f"{path.name} contains a non-exact requirement: {requirement_text}"
        assert hashes, f"{path.name} contains an unhashed requirement: {requirement_text}"
        remainder = HASH_RE.sub("", block).strip()
        assert remainder == requirement_text, f"{path.name} contains unsupported lock options: {block}"

        name = canonicalize_name(match.group("name"))
        assert name not in entries, f"{path.name} pins {name} more than once"
        entries[name] = (
            match.group("version"),
            match.group("marker") or "",
            hashes,
        )

    return entries


def _source_requirements(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            requirements.extend(_source_requirements(path.parent / line[3:].strip()))
            continue
        requirements.append(Requirement(line))
    return requirements


def test_python_patch_version_is_exact_and_canonical() -> None:
    version_file = PROJECT_ROOT / ".python-version"
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert version_file.read_bytes() == b"3.12.12\n"
    assert "requirements-*.lock text eol=lf" in attributes
    assert ".python-version text eol=lf" in attributes


def test_development_intent_includes_the_production_dependency_set() -> None:
    dev_lines = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()

    assert dev_lines[0] == "-r requirements-prod.txt"
    assert "-r requirements.txt" not in dev_lines


def test_locks_are_canonical_exact_hash_only_files() -> None:
    for path in LOCK_FILES:
        raw = path.read_bytes()
        text = raw.decode("utf-8")

        assert raw.endswith(b"\n")
        assert b"\r" not in raw
        assert "http://" not in text
        assert "https://" not in text
        assert not re.search(r"(?im)^[A-Za-z]:[\\/]", text)
        assert "--index-url" not in text
        assert "--find-links" not in text
        assert "-r " not in text
        assert not text.startswith("#")
        assert _lock_entries(path)


def test_production_lock_is_an_exact_component_of_development_lock() -> None:
    production = _lock_entries(PROJECT_ROOT / "requirements-prod.lock")
    development = _lock_entries(PROJECT_ROOT / "requirements-dev.lock")

    assert production.keys() < development.keys()
    for name, production_entry in production.items():
        assert development[name] == production_entry


@pytest.mark.parametrize(
    ("source_name", "lock_name"),
    (
        ("requirements-prod.txt", "requirements-prod.lock"),
        ("requirements-dev.txt", "requirements-dev.lock"),
    ),
)
def test_direct_dependency_versions_stay_within_human_owned_ranges(
    source_name: str,
    lock_name: str,
) -> None:
    locked = _lock_entries(PROJECT_ROOT / lock_name)

    for requirement in _source_requirements(PROJECT_ROOT / source_name):
        name = canonicalize_name(requirement.name)
        assert name in locked
        assert Version(locked[name][0]) in requirement.specifier


def test_lock_refresh_script_has_a_safe_deterministic_contract() -> None:
    script = (PROJECT_ROOT / "scripts" / "refresh_requirements_locks.ps1").read_text(
        encoding="utf-8"
    )

    assert 'DefaultParameterSetName = "Check"' in script
    assert '[switch]$Write' in script
    assert "uv 0.9.28 is required" in script
    assert "--python-version 3.12" in script
    assert "--universal" in script
    assert "--generate-hashes" in script
    assert "--no-annotate" in script
    assert "--no-header" in script
    assert ".local\\tmp\\runtime-baseline" in script
    assert "Test-FilesEqual" in script

    phase_one = script.index("# Phase one: compile and validate every output")
    publish_call = script.rindex("Publish-LockFiles -Locks $locks")
    compile_section = script[phase_one:publish_call]
    assert "New-LockFile -SourceName $lock.Source" in compile_section
    assert "Assert-LockFile -Path $generatedPath" in compile_section
    assert compile_section.index("New-LockFile") < compile_section.index("Assert-LockFile")
    assert "Assert-LockPair" in compile_section
    assert compile_section.index("Assert-LockFile") < compile_section.index("Assert-LockPair")
    assert "WriteAllBytes" not in compile_section
    assert "Invoke-AtomicFileReplacement" not in compile_section

    atomic_body = _powershell_function_body(script, "Invoke-AtomicFileReplacement")
    assert "[System.IO.File]::Replace" in atomic_body
    assert "[System.IO.File]::Move" in atomic_body
    assert "PlatformNotSupportedException" in atomic_body

    publish_body = _powershell_function_body(script, "Publish-LockFiles")
    assert "Split-Path -Parent $lock.TargetPath" in publish_body
    assert ".$targetName.publish-$token.tmp" in publish_body
    assert ".$targetName.backup-$token.bak" in publish_body
    assert publish_body.index("$states +=") < publish_body.index("$attempted = @()")
    assert "$attempted += $state" in publish_body
    assert "Restore-LockTarget -State $attempted[$index]" in publish_body
    assert "throw $publishError" in publish_body

    restore_body = _powershell_function_body(script, "Restore-LockTarget")
    assert "[System.IO.File]::ReadAllBytes($State.BackupPath)" in restore_body
    assert "Invoke-AtomicFileReplacement" in restore_body
    assert "foreach ($artifactPath in $publishArtifacts)" in script


def test_wsgi_exports_the_flask_app_and_metadata_routes() -> None:
    from wsgi import app

    assert isinstance(app, Flask)
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/healthz" in routes
    assert "/api/v1/app" in routes
