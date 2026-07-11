from __future__ import annotations

import re
import tomllib
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


def test_dockerfile_pins_the_exact_runtime_and_hashed_production_lock() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.splitlines()[0] == (
        "FROM python:3.12.12-slim-bookworm@sha256:"
        "593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c"
    )
    assert "COPY requirements-prod.lock ./" in dockerfile
    assert (
        "RUN python -m pip install --no-cache-dir --require-hashes "
        "-r requirements-prod.lock"
    ) in dockerfile
    assert "requirements.txt" not in dockerfile
    assert "requirements-prod.txt" not in dockerfile
    assert 'CMD ["/app/deploy/fly-entrypoint.sh"]' in dockerfile


def test_real_entrypoint_preserves_init_then_single_worker_gunicorn() -> None:
    entrypoint = (PROJECT_ROOT / "deploy" / "fly-entrypoint.sh").read_text(
        encoding="utf-8"
    )

    assert entrypoint.index("python manage.py init-db") < entrypoint.index("exec gunicorn")
    assert '--workers "${GUNICORN_WORKERS:-1}"' in entrypoint
    assert '--threads "${GUNICORN_THREADS:-4}"' in entrypoint
    assert '--timeout "${GUNICORN_TIMEOUT:-60}"' in entrypoint
    assert entrypoint.rstrip().endswith("wsgi:app")


def test_secondary_systemd_example_matches_the_single_worker_rule() -> None:
    service = (PROJECT_ROOT / "deploy" / "campaign-player-wiki.service").read_text(
        encoding="utf-8"
    )
    exec_start = next(line for line in service.splitlines() if line.startswith("ExecStart="))

    assert "--workers 1" in exec_start
    assert "--threads 4" in exec_start
    assert "--timeout 60" in exec_start
    assert "wsgi:app" in exec_start
    assert "-w 2" not in exec_start


def test_fly_config_keeps_generic_samples_and_single_machine_volume_shape() -> None:
    fly_text = (PROJECT_ROOT / "fly.toml").read_text(encoding="utf-8")
    fly = tomllib.loads(fly_text)

    assert "generic, non-secret sample defaults" in fly_text
    assert fly["app"] == "campaign-player-wiki-example"
    assert fly["primary_region"] == "iad"
    assert fly["mounts"] == [
        {
            "source": "player_wiki_data",
            "destination": "/data",
            "initial_size": "1gb",
        }
    ]
    assert fly["http_service"]["auto_stop_machines"] == "off"
    assert fly["http_service"]["auto_start_machines"] is True
    assert fly["http_service"]["min_machines_running"] == 1
    assert fly["http_service"]["checks"][0]["path"] == "/healthz"
    assert fly["vm"] == [
        {
            "memory": "1024mb",
            "cpu_kind": "shared",
            "cpus": 1,
            "memory_mb": 1024,
        }
    ]


def test_runtime_container_validator_is_disposable_and_fails_before_build() -> None:
    script = (
        PROJECT_ROOT / "scripts" / "validate_runtime_container.ps1"
    ).read_text(encoding="utf-8")

    assert '[switch]$KeepArtifacts' in script
    assert '[Guid]::NewGuid().ToString("N")' in script
    assert "RandomNumberGenerator" in script
    assert '$dockerExecutable info --format "{{.ServerVersion}}"' in script
    assert "No image was built" in script
    assert script.index("$serverProbe =") < script.index('"build",')
    assert '"--pull"' in script
    assert '"--rm"' in script
    assert '"--publish", "127.0.0.1::8080"' in script
    assert "PLAYER_WIKI_DB_PATH=/tmp/player-wiki-runtime-check.sqlite3" in script
    assert "PLAYER_WIKI_CAMPAIGNS_DIR=/tmp/player-wiki-runtime-check-campaigns" in script
    assert '"--entrypoint"' not in script
    assert '"--volume"' not in script
    assert "flyctl" not in script.lower()
    assert 'Invoke-WebRequest -Uri $healthUrl' in script
    assert 'platform.python_version() == "3.12.12"' in script
    assert 'metadata.version("gunicorn") == "23.0.0"' in script
    assert '"-m", "pip", "check"' in script
    assert 'Path("/proc/1/task/1/children")' in script
    stdin_body = _powershell_function_body(script, "Invoke-DockerWithInput")
    assert '$InputText | & $script:dockerExecutable @Arguments 2>&1' in stdin_body
    assert "$exitCode = $LASTEXITCODE" in stdin_body
    assert script.count("Invoke-DockerWithInput -Arguments @(") == 2
    assert script.count('"exec", "-i", $containerName, "python", "-"') == 2
    assert '"python", "-c", $metadataProbe' not in script
    assert '"python", "-c", $processProbe' not in script
    assert '"rm", "--force", $containerName' in script
    assert '"image", "rm", "--force", $imageTag' in script
    assert "finally {" in script


def test_local_wrapper_exposes_the_runtime_check_without_requiring_python() -> None:
    script = (PROJECT_ROOT / "local.ps1").read_text(encoding="utf-8")

    assert '"runtime-check"' in script
    assert "function Test-RuntimeContainer" in script
    assert 'scripts\\validate_runtime_container.ps1' in script
    assert 'if ($Action -ne "runtime-check")' in script
    assert 'Set-LocalTempEnvironment -ScopeName $Action' in script


def test_runtime_docs_state_the_supported_target_samples_and_evidence_limit() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    current_state = (PROJECT_ROOT / "docs" / "current-state" / "ops-deploy.md").read_text(
        encoding="utf-8"
    )
    combined = readme + "\n" + current_state

    assert "Fly is the canonical supported production target" in combined
    assert "generic, non-secret sample defaults" in combined
    assert "one worker, four threads, and a 60-second timeout" in combined
    assert "local.ps1 -Action runtime-check" in combined
    assert "never contacts Fly or mounts real app data" in combined
    assert "engine-backed build/run remains unverified" in combined
