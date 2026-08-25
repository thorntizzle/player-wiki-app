from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import browser_skip_requires_failure, pytest_runtest_makereport
from scripts import stage_candidate_build_context as build_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = PROJECT_ROOT / "local.ps1"
VALIDATOR = PROJECT_ROOT / "scripts" / "candidate_gate.ps1"
DOCKERFILE = PROJECT_ROOT / "deploy" / "candidate-gate.Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / "deploy" / "candidate-gate.Dockerfile.dockerignore"
CHROMIUM_SMOKE = PROJECT_ROOT / "scripts" / "smoke_playwright_chromium.py"
CONTEXT_STAGER = PROJECT_ROOT / "scripts" / "stage_candidate_build_context.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git(root: Path, *arguments: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        input=input_bytes,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _new_candidate_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "candidate"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "candidate@example.invalid")
    _git(root, "config", "user.name", "Candidate Test")
    context = root / ".local" / "candidate-gate" / "build-context"
    manifest = root / ".local" / "candidate-gate" / "build-context-manifest.json"
    return root, context, manifest


def _write(root: Path, relative: str, value: bytes = b"candidate\n") -> Path:
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


@pytest.mark.contract
def test_candidate_gate_new_files_pass_staged_whitespace_contract(tmp_path):
    relative_paths = (
        "deploy/candidate-gate.Dockerfile",
        "deploy/candidate-gate.Dockerfile.dockerignore",
        "scripts/candidate_gate.ps1",
        "scripts/smoke_playwright_chromium.py",
        "scripts/stage_candidate_build_context.py",
        "tests/test_candidate_gate.py",
    )
    source_bytes = {
        relative: (PROJECT_ROOT / relative).read_bytes() for relative in relative_paths
    }
    attributes_bytes = (PROJECT_ROOT / ".gitattributes").read_bytes()
    root = tmp_path / "candidate-whitespace-contract"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "candidate@example.invalid")
    _git(root, "config", "user.name", "Candidate Test")
    _write(root, ".gitattributes", attributes_bytes)
    _git(root, "add", ".gitattributes")
    _git(root, "commit", "-m", "synthetic attributes baseline")

    for relative, value in source_bytes.items():
        _write(root, relative, value)
    _git(root, "add", "--", *relative_paths)

    staged = _git(root, "diff", "--cached", "--name-only", "-z").stdout
    assert tuple(path.decode("utf-8") for path in staged.rstrip(b"\0").split(b"\0")) == relative_paths
    completed = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--check"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0, (completed.stdout + completed.stderr).decode(
        "utf-8", errors="replace"
    )


@pytest.mark.contract
def test_local_wrapper_routes_candidate_gate_through_complete_validation_lock():
    wrapper = _text(WRAPPER)

    assert '"candidate-gate"' in wrapper.split("[ValidateSet(", 1)[1].split(")]", 1)[0]
    assert '"candidate-gate" {' in wrapper
    assert 'Join-Path $projectRoot "scripts\\candidate_gate.ps1"' in wrapper
    assert '$completeActions = @("character-read-baseline", "candidate-gate", "test", "check")' in wrapper
    temp_exclusions = wrapper.split('if ($Action -notin @(', 1)[1].split("))", 1)[0]
    assert '"candidate-gate"' in temp_exclusions


@pytest.mark.contract
def test_validation_image_pins_base_lock_git_and_real_chromium():
    dockerfile = _text(DOCKERFILE)

    assert dockerfile.startswith(
        "FROM python:3.12.12-slim-bookworm@sha256:"
        "593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c\n"
    )
    assert "apt-get install --yes --no-install-recommends ca-certificates git" in dockerfile
    assert "pip install --no-cache-dir --require-hashes -r /tmp/requirements-dev.lock" in dockerfile
    assert "python -m playwright install --with-deps chromium" in dockerfile
    assert "COPY . /workspace" in dockerfile


@pytest.mark.contract
def test_validation_dockerignore_is_only_mount_boundary_defense_in_depth():
    patterns = set(_text(DOCKERIGNORE).splitlines())

    assert patterns == {".git", ".git/**", ".local", ".local/**"}
    for allowlisted_root in ("campaigns", "tests", "docs", "scripts"):
        assert allowlisted_root not in patterns
        assert f"{allowlisted_root}/**" not in patterns


@pytest.mark.contract
def test_validator_requires_linux_amd64_and_read_only_minimal_git_mounts():
    validator = _text(VALIDATOR)

    assert 'dockerPlatform -ne "linux/x86_64"' in validator
    assert 'dockerPlatform -ne "linux/amd64"' in validator
    assert '"--platform", "linux/amd64"' in validator
    assert 'dst=/workspace/.git,readonly' in validator
    assert 'dst=/candidate-git-objects,readonly' in validator
    assert '"--read-only"' in validator
    assert '"--network", "none"' in validator
    assert "git-metadata" in validator
    assert '"--metadata-root", $gitMetadataRoot' not in validator
    assert "--metadata-root $gitMetadataRoot" in validator
    assert 'alternates_path: str = "/candidate-git-objects"' in _text(CONTEXT_STAGER)
    assert "filemode = false" in _text(CONTEXT_STAGER)
    assert "Copy-Item" not in validator
    assert "New-ReadOnlyGitMetadata" not in validator
    assert "src=$commonDirectory" not in validator


@pytest.mark.contract
def test_validator_stages_git_inventory_and_verifies_image_before_other_linux_stages():
    validator = _text(VALIDATOR)

    assert '"stage Git-authoritative build context"' in validator
    assert '"--context-root", $buildContext' in validator
    assert '"--manifest", $buildManifest' in validator
    build_arguments = validator.split("$buildArguments = @(", 1)[1].split(")", 1)[0]
    assert "$buildContext" in build_arguments
    assert "$ProjectRoot" not in build_arguments
    assert '$dockerfile = Join-Path $buildContext "deploy\\candidate-gate.Dockerfile"' in validator
    assert '"--file", $dockerfile' in build_arguments
    assert validator.index("$dockerfile = Join-Path $buildContext") > validator.index(
        '"stage Git-authoritative build context"'
    )
    assert "src=$buildManifest,dst=/candidate-build-context-manifest.json,readonly" in validator
    inventory = validator.index('Label = "Linux exact image inventory"')
    environment = validator.index('Label = "Linux canonical environment"')
    pytest_stage = validator.index('Label = "Linux pytest"')
    assert inventory < environment < pytest_stage
    assert '"verify-image"' in validator[inventory:environment]


@pytest.mark.contract
def test_context_stager_uses_authoritative_nul_git_allowlist_and_fail_closed_checks():
    stager = _text(CONTEXT_STAGER)

    assert '"ls-files", "--cached", "--others", "--exclude-standard"' in stager
    assert '"ls-files", "--deleted"' in stager
    assert "*arguments, \"-z\"" in stager
    assert 'mode == "120000"' in stager
    assert "FILE_ATTRIBUTE_REPARSE_POINT" in stager
    assert "Source changed while staging" in stager
    assert '"state": "tracked" if mode else "untracked"' in stager
    assert '"sha256": digest' in stager
    assert '"git_mode": mode' in stager


@pytest.mark.contract
def test_validator_uses_stable_metadata_and_lock_hash_image_identity():
    validator = _text(VALIDATOR)

    assert "[AllowEmptyString()]" in validator
    assert '".local\\candidate-gate\\git-metadata"' in validator
    assert "[Guid]" not in validator
    assert "$runTag" not in validator
    assert validator.count('"--tag", $cacheTag') == 1
    container_arguments = validator.split("$containerBase = @(", 1)[1].split(
        "$linuxStages = @(", 1
    )[0]
    assert "$cacheTag" in container_arguments
    assert "git-metadata" in validator
    assert "Candidate Git metadata must use the stable owned path" in _text(CONTEXT_STAGER)


@pytest.mark.contract
def test_validator_uses_workspace_tmpfs_pytest_roots_and_explicit_temp_environment():
    validator = _text(VALIDATOR)
    container_arguments = validator.split("$containerBase = @(", 1)[1].split(
        "$linuxStages = @(", 1
    )[0]

    assert '"--tmpfs", "/workspace/.local:rw,exec,nosuid,nodev"' in container_arguments
    assert '"--env", "TEMP=/tmp"' in container_arguments
    assert '"--env", "TMP=/tmp"' in container_arguments
    assert '"--env", "TMPDIR=/tmp"' in container_arguments
    assert '"run-pytest", "--"' in validator
    assert 'Path("/workspace/.local/candidate-gate/linux-pytest")' in _text(CONTEXT_STAGER)
    assert 'Path("/workspace/.local/candidate-gate/linux-cache")' in _text(CONTEXT_STAGER)
    assert 'Label = "Linux writable temporary roots"' in validator
    assert '"verify-temp"' in validator


@pytest.mark.contract
def test_validator_creates_and_prints_stable_image_receipt():
    validator = _text(VALIDATOR)

    assert '"image-receipt"' in validator
    assert '"--dockerfile", $dockerfile' in validator
    assert '"--dockerignore", $dockerignore' in validator
    assert '"--lock", $lockPath' in validator
    assert '"--platform", "linux/amd64"' in validator
    assert '".local\\candidate-gate\\image-receipt.json"' in validator
    assert '"--docker", $resolvedDocker' in validator
    assert '"--image", $cacheTag' in validator
    assert "$imageReceiptJson = & $PythonPath @receiptArguments" in validator
    assert "$imageReceiptExitCode = [int]$LASTEXITCODE" in validator
    assert re.search(
        r"\$imageReceiptJson = & \$PythonPath @receiptArguments\n"
        r"        \$imageReceiptExitCode = \[int\]\$LASTEXITCODE",
        validator,
    )
    assert "candidate-gate receipt: stable_sha256=" in validator


@pytest.mark.contract
def test_validator_prints_and_validates_exact_built_image_identity():
    validator = _text(VALIDATOR)

    assert "docker image inspect" not in validator
    assert "$resolvedDocker image inspect" not in validator
    assert "image_identity.id" in validator
    assert "image_identity.os" in validator
    assert "image_identity.architecture" in validator
    assert "^sha256:[0-9a-f]{64}$" in validator
    assert '$imageIdentity[1] -ne "linux"' in validator
    assert '$imageIdentity[2] -ne "amd64"' in validator
    assert "candidate-gate image: id=" in validator


@pytest.mark.contract
def test_chromium_smoke_prints_playwright_and_real_browser_versions():
    smoke = _text(CHROMIUM_SMOKE)

    assert 'version("playwright")' in smoke
    assert "browser.version" in smoke
    assert '"playwright_package_version"' in smoke
    assert '"chromium_version"' in smoke


@pytest.mark.contract
def test_windows_marker_selection_matches_validator_allowlist():
    validator = _text(VALIDATOR)
    block = validator.split("$windowsHostTests = @(", 1)[1].split(")", 1)[0]
    selected = set(re.findall(r'"(tests/[^\"]+\.py)"', block))
    expected = {
        "tests/test_agent_instruction_anchor_validation.py",
        "tests/test_file_publication.py",
        "tests/test_generate_publisher_manifest.py",
        "tests/test_measure_character_read_performance.py",
        "tests/test_operations.py",
        "tests/test_phase_closeout_anchor.py",
        "tests/test_program_continuation_policy.py",
        "tests/test_publisher_closeout.py",
        "tests/test_publisher_focused_validation.py",
        "tests/test_runtime_lease.py",
        "tests/test_short_root_validation.py",
        "tests/test_candidate_gate.py",
    }

    assert selected == expected
    assert '"-m", "windows_host"' in validator
    assert '"-m", "not windows_host"' in validator
    host_arguments = validator.split("$hostArguments = @(", 1)[1].split(") + $windowsHostTests", 1)[0]
    assert '"--require-browser"' not in host_arguments
    assert '".local\\candidate-gate\\windows-pytest"' in host_arguments
    assert "windows-pytest-$PID" not in host_arguments
    assert "[Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT" in validator
    for relative in selected - {
        "tests/test_agent_instruction_anchor_validation.py",
        "tests/test_short_root_validation.py",
        "tests/test_candidate_gate.py",
    }:
        assert "@pytest.mark.windows_host" in _text(PROJECT_ROOT / relative)
    for relative in (
        "tests/test_agent_instruction_anchor_validation.py",
        "tests/test_short_root_validation.py",
    ):
        assert "pytestmark = pytest.mark.windows_host" in _text(PROJECT_ROOT / relative)


@pytest.mark.contract
@pytest.mark.parametrize(
    "reason",
    (
        "Playwright unavailable: import failed",
        "Playwright browser unavailable: executable missing",
        "Combat browser matrix unavailable: launch failed",
    ),
)
def test_require_browser_converts_only_capability_skips(reason):
    assert browser_skip_requires_failure(reason, strict=True)
    assert not browser_skip_requires_failure(reason, strict=False)
    assert not browser_skip_requires_failure("intentional fixture limitation", strict=True)


@pytest.mark.contract
def test_require_browser_hook_mutates_matching_skip_report_to_failure():
    report = SimpleNamespace(skipped=True, outcome="skipped", longrepr="original")
    outcome = SimpleNamespace(get_result=lambda: report)
    item = SimpleNamespace(
        nodeid="tests/example.py::test_browser",
        config=SimpleNamespace(getoption=lambda _name: True),
    )
    call = SimpleNamespace(
        excinfo=SimpleNamespace(value=RuntimeError("Playwright unavailable: blocked"))
    )

    hook = pytest_runtest_makereport(item, call)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(outcome)

    assert report.outcome == "failed"
    assert "required browser capability unavailable" in report.longrepr


@pytest.mark.contract
def test_stager_copies_current_tracked_and_untracked_bytes_omits_deletes_and_resets_stale(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    tracked = {
        "app.py": b"original\n",
        "docs/guide.md": b"docs\n",
        "tests/test_sample.py": b"tests\n",
        "scripts/helper.py": b"source\n",
        "campaigns/.gitkeep": b"",
        "campaigns/README.md": b"placeholder\n",
        "deleted.txt": b"deleted\n",
    }
    for relative, value in tracked.items():
        _write(root, relative, value)
    _git(root, "add", *tracked)
    _write(root, "app.py", b"modified-current-bytes\n")
    (root / "deleted.txt").unlink()
    _write(root, "notes/untracked.txt", b"untracked-current-bytes\n")
    _write(root, ".gitignore", b".local/\n")
    _write(context, "stale/old.txt", b"must disappear")

    first = build_context.stage_context(root, context, manifest_path)
    first_bytes = manifest_path.read_bytes()
    second = build_context.stage_context(root, context, manifest_path)

    records = {record["path"]: record for record in first["files"]}
    assert records["app.py"]["state"] == "tracked"
    assert records["app.py"]["git_mode"] == "100644"
    assert records["notes/untracked.txt"]["state"] == "untracked"
    assert records["notes/untracked.txt"]["git_mode"] is None
    assert (context / "app.py").read_bytes() == b"modified-current-bytes\n"
    assert (context / "notes" / "untracked.txt").read_bytes() == b"untracked-current-bytes\n"
    assert not (context / "stale").exists()
    assert not (context / "deleted.txt").exists()
    assert first["deleted_tracked_paths"] == ["deleted.txt"]
    assert {"docs/guide.md", "tests/test_sample.py", "scripts/helper.py", "campaigns/.gitkeep", "campaigns/README.md"} <= set(records)
    assert second == first
    assert manifest_path.read_bytes() == first_bytes


@pytest.mark.contract
def test_stager_refuses_missing_tracked_path_not_predeclared_deleted(tmp_path, monkeypatch):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    source = _write(root, "tracked.txt", b"tracked")
    _git(root, "add", "tracked.txt")
    original = build_context._git_z

    def remove_after_deleted_inventory(project_root, git, *arguments):
        result = original(project_root, git, *arguments)
        if arguments == ("ls-files", "--deleted"):
            source.unlink()
        return result

    monkeypatch.setattr(build_context, "_git_z", remove_after_deleted_inventory)
    with pytest.raises(build_context.StageError, match="Tracked non-deleted inventory path disappeared"):
        build_context.stage_context(root, context, manifest_path)


@pytest.mark.contract
def test_stager_refuses_tracked_path_disappearing_during_copy(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    source = _write(root, "tracked.txt", b"tracked")
    _git(root, "add", "tracked.txt")

    def remove_during_copy(path):
        if path == source:
            path.unlink()

    with pytest.raises(build_context.StageError, match="Source disappeared after copy"):
        build_context.stage_context(root, context, manifest_path, drift_hook=remove_during_copy)


@pytest.mark.contract
def test_stager_excludes_every_ignored_private_cache_and_archive_sentinel(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    _write(root, "included.txt", b"intended")
    _write(
        root,
        ".gitignore",
        b"\n".join(
            (
                b"campaigns/private/",
                b"databases/",
                b"backup/",
                b"backups/",
                b"archive/",
                b"archives/",
                b"*.sqlite",
                b"*.sqlite3",
                b"*.db",
                b"*.bak",
                b"*.backup",
                b"*.dump",
                b"*.sql",
                b"*.zip",
                b"*.tar",
                b"*.tar.gz",
                b"*.tgz",
                b"*.7z",
                b"*.rar",
                b".env*",
                b"secrets/",
                b"*.pem",
                b"*.key",
                b".venv/",
                b"venv/",
                b"venvs/",
                b"__pycache__/",
                b".pytest_cache/",
                b".mypy_cache/",
                b".ruff_cache/",
                b"node_modules/",
                b"cache/",
                b"caches/",
                b".task-temp*/",
                b".pytest-tmp*/",
                b"pytest-tmp*/",
                b"pytest_tmp*/",
                b"pytesttmp*/",
                b"tmp*/",
                b"scratch/",
                b"*.pyc",
                b"*.pyo",
            )
        )
        + b"\n",
    )
    ignored = (
        "campaigns/private/secret.txt",
        "databases/live.sqlite3",
        "backup/one.txt",
        "backups/two.txt",
        "archive/three.txt",
        "archives/four.txt",
        "root.sqlite",
        "root.db",
        "root.bak",
        "root.backup",
        "root.dump",
        "root.sql",
        "root.zip",
        "root.tar",
        "root.tar.gz",
        "root.tgz",
        "root.7z",
        "root.rar",
        ".env",
        ".env.local",
        "secrets/token.txt",
        "private.pem",
        "private.key",
        ".venv/python",
        "venv/python",
        "venvs/python",
        "pkg/__pycache__/cache.pyc",
        ".pytest_cache/state",
        ".mypy_cache/state",
        ".ruff_cache/state",
        "node_modules/pkg/index.js",
        "cache/item",
        "caches/item",
        ".task-temp-1/item",
        ".pytest-tmp-1/item",
        "pytest-tmp-1/item",
        "pytest_tmp_1/item",
        "pytesttmp1/item",
        "tmp-1/item",
        "pkg/tmp-2/item",
        "scratch/item",
        "compiled.pyo",
    )
    for relative in ignored:
        _write(root, relative, f"synthetic sentinel {relative}\n".encode())

    result = build_context.stage_context(root, context, manifest_path)
    staged = {record["path"] for record in result["files"]}

    assert staged == {".gitignore", "included.txt"}
    for relative in ignored:
        assert not context.joinpath(*relative.split("/")).exists()


@pytest.mark.contract
def test_stager_rejects_traversal_absolute_invalid_and_colliding_paths():
    invalid_groups = (
        ["../escape"],
        ["/absolute"],
        ["C:/absolute"],
        ["bad\\separator"],
        ["bad:name"],
        ["CON.txt"],
        ["Name.txt", "name.txt"],
        ["caf\u00e9.txt", "cafe\u0301.txt"],
    )
    for paths in invalid_groups:
        with pytest.raises(build_context.StageError):
            build_context.validate_inventory_paths(paths)


@pytest.mark.contract
def test_stager_rejects_git_symlinks_and_missing_nontracked_inventory(tmp_path, monkeypatch):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    blob = _git(root, "hash-object", "-w", "--stdin", input_bytes=b"target").stdout.decode().strip()
    _git(root, "update-index", "--add", "--cacheinfo", f"120000,{blob},linked")
    with pytest.raises(build_context.StageError, match="Git symlink"):
        build_context.stage_context(root, context, manifest_path)

    _git(root, "rm", "--cached", "linked")
    original = build_context._git_z

    def inventory_with_missing(project_root, git, *arguments):
        if arguments == ("ls-files", "--cached", "--others", "--exclude-standard"):
            return ["vanished-untracked.txt"]
        return original(project_root, git, *arguments)

    monkeypatch.setattr(build_context, "_git_z", inventory_with_missing)
    with pytest.raises(build_context.StageError, match="Nontracked inventory path disappeared"):
        build_context.stage_context(root, context, manifest_path)


@pytest.mark.contract
def test_stager_rejects_source_drift(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    source = _write(root, "drift.txt", b"before")
    _git(root, "add", "drift.txt")

    def mutate(path):
        if path == source:
            path.write_bytes(b"after")

    with pytest.raises(build_context.StageError, match="Source changed while staging"):
        build_context.stage_context(root, context, manifest_path, drift_hook=mutate)
    assert not manifest_path.exists()


@pytest.mark.contract
def test_stager_rejects_real_links_when_host_can_create_them(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    source = _write(root, "target.txt", b"target")
    _write(root, ".gitignore", b".local/\n")
    source_link = root / "untracked-link"
    try:
        source_link.symlink_to(source)
    except OSError:
        pytest.skip("Host policy does not permit creation of a synthetic symlink")
    with pytest.raises(build_context.StageError, match="link or reparse point"):
        build_context.stage_context(root, context, manifest_path)
    source_link.unlink()

    keep = _write(context, "keep.txt", b"keep")
    context_link = context / "linked-entry"
    context_link.symlink_to(source)
    with pytest.raises(build_context.StageError, match="linked or reparse entry"):
        build_context.stage_context(root, context, manifest_path)
    assert keep.read_bytes() == b"keep"
    context_link.unlink()

    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.symlink_to(source)
    with pytest.raises(build_context.StageError, match="link or reparse point"):
        build_context.stage_context(root, context, manifest_path)
    assert source.read_bytes() == b"target"


@pytest.mark.contract
def test_stager_refuses_reparse_candidate_scratch_chain(tmp_path, monkeypatch):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    context.mkdir(parents=True)
    monkeypatch.setattr(build_context, "_is_reparse", lambda _info: True)

    with pytest.raises(build_context.StageError, match="plain directory|link or reparse point"):
        build_context.stage_context(root, context, manifest_path)


@pytest.mark.contract
def test_context_reparse_mock_refuses_before_deleting_ordinary_sentinel(tmp_path, monkeypatch):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    _write(root, ".gitignore", b".local/\n")
    keep = _write(context, "keep.txt", b"ordinary sentinel")
    poison_bytes = b"p" * 137
    poison = _write(context, "nested/poison", poison_bytes)
    manifest_path.write_bytes(b"previous manifest sentinel")
    real_is_reparse = build_context._is_reparse

    def mark_poison_as_reparse(info):
        return info.st_size == len(poison_bytes) or real_is_reparse(info)

    monkeypatch.setattr(build_context, "_is_reparse", mark_poison_as_reparse)
    with pytest.raises(build_context.StageError, match="linked or reparse entry"):
        build_context.stage_context(root, context, manifest_path)

    assert keep.read_bytes() == b"ordinary sentinel"
    assert poison.read_bytes() == poison_bytes
    assert manifest_path.read_bytes() == b"previous manifest sentinel"


@pytest.mark.contract
def test_temporary_manifest_reparse_mock_refuses_without_target_write(tmp_path, monkeypatch):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    target_bytes = b"t" * 173
    target = _write(root, "target.txt", target_bytes)
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.parent.mkdir(parents=True)
    temporary_manifest.hardlink_to(target)
    real_is_reparse = build_context._is_reparse

    def mark_temporary_as_reparse(info):
        return info.st_size == len(target_bytes) or real_is_reparse(info)

    monkeypatch.setattr(build_context, "_is_reparse", mark_temporary_as_reparse)
    with pytest.raises(build_context.StageError, match="link or reparse point|not a plain file"):
        build_context.stage_context(root, context, manifest_path)

    assert target.read_bytes() == target_bytes
    assert temporary_manifest.read_bytes() == target_bytes


@pytest.mark.contract
def test_final_source_recheck_detects_cross_file_drift(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    first = _write(root, "a-first.txt", b"first")
    second = _write(root, "z-second.txt", b"second")
    _git(root, "add", "a-first.txt", "z-second.txt")

    def mutate_first_after_second_copy(path):
        if path == second:
            first.write_bytes(b"changed after its copy")

    with pytest.raises(build_context.StageError, match="changed before manifest publication"):
        build_context.stage_context(
            root,
            context,
            manifest_path,
            drift_hook=mutate_first_after_second_copy,
        )
    assert not manifest_path.exists()


@pytest.mark.contract
def test_git_metadata_is_exact_minimal_and_supports_history_commands(tmp_path):
    root, _context, _manifest_path = _new_candidate_repo(tmp_path)
    _write(root, ".gitignore", b".local/\n")
    _write(root, "history.txt", b"historical bytes\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    metadata_root = root / ".local" / "candidate-gate" / "git-metadata"
    objects = root / ".git" / "objects"

    result = build_context.create_git_metadata(
        root,
        metadata_root,
        alternates_path=objects.as_posix(),
    )

    files = {
        path.relative_to(metadata_root).as_posix()
        for path in metadata_root.rglob("*")
        if path.is_file()
    }
    directories = {
        path.relative_to(metadata_root).as_posix()
        for path in metadata_root.rglob("*")
        if path.is_dir()
    }
    assert files == {"HEAD", "config", "index", "objects/info/alternates"}
    assert directories == {"objects", "objects/info", "refs"}
    assert result["metadata"] == str(metadata_root)
    command = ["git", f"--git-dir={metadata_root}", f"--work-tree={root}"]
    for arguments in (
        ("rev-parse", "--verify", "HEAD"),
        ("cat-file", "-e", "HEAD^{commit}"),
        ("rev-list", "--max-count=1", "HEAD"),
        ("show", "HEAD:history.txt"),
    ):
        completed = subprocess.run(
            [*command, *arguments], check=False, capture_output=True, text=True
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "historical bytes" in subprocess.run(
        [*command, "show", "HEAD:history.txt"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.contract
def test_git_metadata_reset_removes_stale_index_when_source_index_is_absent(tmp_path):
    root, _context, _manifest_path = _new_candidate_repo(tmp_path)
    _write(root, ".gitignore", b".local/\n")
    _write(root, "tracked.txt", b"tracked\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    metadata_root = root / ".local" / "candidate-gate" / "git-metadata"
    build_context.create_git_metadata(root, metadata_root)
    assert (metadata_root / "index").is_file()

    (root / ".git" / "index").unlink()
    build_context.create_git_metadata(root, metadata_root)

    assert not (metadata_root / "index").exists()
    assert {
        path.relative_to(metadata_root).as_posix()
        for path in metadata_root.rglob("*")
        if path.is_file()
    } == {"HEAD", "config", "objects/info/alternates"}


@pytest.mark.contract
def test_git_metadata_contamination_refuses_without_deleting_sentinels(tmp_path, monkeypatch):
    root, _context, _manifest_path = _new_candidate_repo(tmp_path)
    _write(root, ".gitignore", b".local/\n")
    _write(root, "tracked.txt", b"tracked\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    metadata_root = root / ".local" / "candidate-gate" / "git-metadata"
    keep = _write(metadata_root, "keep", b"ordinary metadata sentinel")
    poison_bytes = b"m" * 211
    poison = _write(metadata_root, "nested/poison", poison_bytes)
    real_is_reparse = build_context._is_reparse

    monkeypatch.setattr(
        build_context,
        "_is_reparse",
        lambda info: info.st_size == len(poison_bytes) or real_is_reparse(info),
    )
    with pytest.raises(build_context.StageError, match="linked or reparse entry"):
        build_context.create_git_metadata(root, metadata_root)

    assert keep.read_bytes() == b"ordinary metadata sentinel"
    assert poison.read_bytes() == poison_bytes


@pytest.mark.contract
def test_runtime_temp_requires_exact_environment_absolute_and_writable_paths(tmp_path, monkeypatch):
    for name in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(name, "/tmp")
    absolute = tmp_path / "candidate-temp"
    assert build_context.verify_runtime_temp([absolute])["status"] == "ok"
    assert absolute.is_dir()
    assert not (absolute / ".candidate-gate-write-probe").exists()

    monkeypatch.setenv("TMPDIR", "/wrong")
    with pytest.raises(build_context.StageError, match="TMPDIR"):
        build_context.verify_runtime_temp([absolute])
    monkeypatch.setenv("TMPDIR", "/tmp")
    with pytest.raises(build_context.StageError, match="not absolute"):
        build_context.verify_runtime_temp([Path("relative")])


def _mock_image_git_inventory(monkeypatch, manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracked = [record for record in manifest["files"] if record["state"] == "tracked"]
    untracked = [record["path"] for record in manifest["files"] if record["state"] == "untracked"]
    deleted = manifest["deleted_tracked_paths"]

    def fake_git_z(_root, _git, *arguments):
        if arguments == ("ls-files", "--stage"):
            return [
                f"{record['git_mode']} {'0' * 40} 0\t{record['path']}" for record in tracked
            ] + [f"100644 {'0' * 40} 0\t{path}" for path in deleted]
        if arguments == ("ls-files", "--deleted"):
            return list(deleted)
        if arguments == ("ls-files", "--others", "--exclude-standard"):
            return list(untracked)
        if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
            return []
        raise AssertionError(arguments)

    monkeypatch.setattr(build_context, "_git_z", fake_git_z)


@pytest.mark.contract
@pytest.mark.parametrize("mutation", ("missing", "extra", "changed"))
def test_image_inventory_rejects_missing_extra_and_hash_drift(tmp_path, mutation, monkeypatch):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    _write(root, "app.py", b"exact")
    _git(root, "add", "app.py")
    build_context.stage_context(root, context, manifest_path)
    (context / ".git").mkdir()
    (context / ".git" / "mounted-index").write_bytes(b"ignored mount")
    (context / ".local").mkdir()
    (context / ".local" / "runtime").write_bytes(b"ignored mount")
    _mock_image_git_inventory(monkeypatch, manifest_path)

    assert build_context.verify_image_inventory(context, manifest_path)["status"] == "ok"
    if mutation == "missing":
        (context / "app.py").unlink()
    elif mutation == "extra":
        _write(context, "extra.txt", b"extra")
    else:
        (context / "app.py").write_bytes(b"changed")
    with pytest.raises(build_context.StageError, match="Image inventory mismatch"):
        build_context.verify_image_inventory(context, manifest_path)


@pytest.mark.contract
@pytest.mark.parametrize(
    "tamper",
    ("top-extra", "record-extra", "state", "mode", "deleted", "order", "collision"),
)
def test_image_inventory_rejects_manifest_schema_and_index_semantic_tampering(
    tmp_path, monkeypatch, tamper
):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    _write(root, "app.py", b"exact")
    _write(root, "note.txt", b"untracked")
    _git(root, "add", "app.py")
    build_context.stage_context(root, context, manifest_path)
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    _mock_image_git_inventory(monkeypatch, manifest_path)
    manifest = copy.deepcopy(original)
    tracked = next(record for record in manifest["files"] if record["state"] == "tracked")
    if tamper == "top-extra":
        manifest["unexpected"] = True
    elif tamper == "record-extra":
        tracked["unexpected"] = True
    elif tamper == "state":
        tracked["state"] = "untracked"
        tracked["git_mode"] = None
    elif tamper == "mode":
        tracked["git_mode"] = "100755"
    elif tamper == "deleted":
        manifest["deleted_tracked_paths"] = ["gone.txt"]
    elif tamper == "order":
        manifest["files"].reverse()
    else:
        duplicate = copy.deepcopy(tracked)
        duplicate["path"] = tracked["path"].upper()
        manifest["files"].append(duplicate)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(build_context.StageError):
        build_context.verify_image_inventory(context, manifest_path)


def _receipt_fixture(tmp_path):
    root, context, manifest_path = _new_candidate_repo(tmp_path)
    _write(
        root,
        "Dockerfile",
        b"FROM python:3.12.12-slim-bookworm@sha256:"
        b"593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c\n",
    )
    _write(root, "Dockerfile.dockerignore", b".git\n.local\n")
    _write(root, "requirements-dev.lock", b"fixture lock\n")
    _git(root, "add", ".")
    build_context.stage_context(root, context, manifest_path)
    inspect_payload = [
        {
            "Config": {
                "Cmd": ["python", "-m", "pytest"],
                "Entrypoint": None,
                "Env": ["PYTHONUNBUFFERED=1"],
                "Labels": None,
                "User": "",
                "WorkingDir": "/workspace",
            },
            "Created": "2026-08-25T00:00:00Z",
            "Id": f"sha256:{'1' * 64}",
            "Architecture": "amd64",
            "Metadata": {"LastTagTime": "volatile"},
            "Os": "linux",
            "RepoDigests": [f"fixture@sha256:{'2' * 64}"],
            "RootFS": {"Layers": [f"sha256:{'3' * 64}"], "Type": "layers"},
        }
    ]
    inputs = {
        "manifest_path": manifest_path,
        "dockerfile_path": root / "Dockerfile",
        "dockerignore_path": root / "Dockerfile.dockerignore",
        "lock_path": root / "requirements-dev.lock",
        "platform": "linux/amd64",
    }
    return inspect_payload, inputs


@pytest.mark.contract
def test_image_receipt_stable_hash_excludes_volatile_identity_and_provenance(tmp_path):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    first = build_context.create_image_receipt(inspect_payload, **inputs)
    changed = copy.deepcopy(inspect_payload)
    changed[0]["Created"] = "2027-01-01T00:00:00Z"
    changed[0]["Id"] = f"sha256:{'4' * 64}"
    changed[0]["RepoDigests"] = [f"fixture@sha256:{'5' * 64}"]
    changed[0]["Metadata"] = {"LastTagTime": "different provenance"}
    second = build_context.create_image_receipt(changed, **inputs)

    assert first["stable_sha256"] == second["stable_sha256"]
    assert first["diagnostics"] != second["diagnostics"]


@pytest.mark.contract
@pytest.mark.parametrize("change", ("layer", "config", "dockerfile", "ignore", "lock", "manifest"))
def test_image_receipt_stable_hash_binds_layers_config_and_candidate_inputs(tmp_path, change):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    baseline = build_context.create_image_receipt(inspect_payload, **inputs)
    changed_inspect = copy.deepcopy(inspect_payload)
    if change == "layer":
        changed_inspect[0]["RootFS"]["Layers"][0] = f"sha256:{'6' * 64}"
    elif change == "config":
        changed_inspect[0]["Config"]["WorkingDir"] = "/different"
    elif change == "dockerfile":
        inputs["dockerfile_path"].write_text(
            inputs["dockerfile_path"].read_text(encoding="utf-8") + "ENV RECEIPT=1\n",
            encoding="utf-8",
        )
    elif change == "ignore":
        inputs["dockerignore_path"].write_text(".git\n.local\nextra\n", encoding="utf-8")
    elif change == "lock":
        inputs["lock_path"].write_text("different lock\n", encoding="utf-8")
    else:
        manifest = json.loads(inputs["manifest_path"].read_text(encoding="utf-8"))
        manifest["files"][0]["sha256"] = "7" * 64
        inputs["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    changed = build_context.create_image_receipt(changed_inspect, **inputs)

    assert changed["stable_sha256"] != baseline["stable_sha256"]


@pytest.mark.contract
def test_image_receipt_refuses_nonstable_output_path_without_writes(tmp_path):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    wrong_output = inputs["manifest_path"].parent / "wrong-receipt.json"

    with pytest.raises(build_context.StageError, match="exact stable sibling path"):
        build_context.create_image_receipt(
            inspect_payload,
            **inputs,
            output_path=wrong_output,
        )

    assert not wrong_output.exists()


@pytest.mark.contract
def test_image_receipt_replaces_only_ordinary_stale_owned_files(tmp_path):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    output = inputs["manifest_path"].parent / "image-receipt.json"
    temporary = inputs["manifest_path"].parent / "image-receipt.json.tmp"
    output.write_bytes(b"ordinary old receipt")
    temporary.write_bytes(b"ordinary old temporary receipt")
    sibling = output.parent / "diagnostic-sentinel"
    sibling.write_bytes(b"keep")

    receipt = build_context.create_image_receipt(
        inspect_payload,
        **inputs,
        output_path=output,
    )

    assert output.read_bytes() == build_context._canonical_json(receipt)
    assert not temporary.exists()
    assert sibling.read_bytes() == b"keep"


@pytest.mark.contract
@pytest.mark.parametrize("contaminated_name", ("image-receipt.json", "image-receipt.json.tmp"))
def test_image_receipt_refuses_real_link_without_target_or_sentinel_write(
    tmp_path,
    contaminated_name,
):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    receipt_root = inputs["manifest_path"].parent
    output = receipt_root / "image-receipt.json"
    temporary = receipt_root / "image-receipt.json.tmp"
    contaminated = receipt_root / contaminated_name
    other = temporary if contaminated == output else output
    target = receipt_root.parent.parent / f"{contaminated_name}.target"
    target.write_bytes(b"linked target sentinel")
    other.write_bytes(b"ordinary receipt sentinel")
    try:
        contaminated.symlink_to(target)
    except OSError:
        pytest.skip("Host policy does not permit creation of a synthetic receipt symlink")

    with pytest.raises(build_context.StageError, match="link or reparse point|not a plain file"):
        build_context.create_image_receipt(
            inspect_payload,
            **inputs,
            output_path=output,
        )

    assert target.read_bytes() == b"linked target sentinel"
    assert other.read_bytes() == b"ordinary receipt sentinel"
    assert contaminated.is_symlink()


@pytest.mark.contract
@pytest.mark.parametrize("contaminated_name", ("image-receipt.json", "image-receipt.json.tmp"))
def test_image_receipt_reparse_mock_refuses_without_removing_sentinels(
    tmp_path,
    monkeypatch,
    contaminated_name,
):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    receipt_root = inputs["manifest_path"].parent
    output = receipt_root / "image-receipt.json"
    temporary = receipt_root / "image-receipt.json.tmp"
    contaminated = receipt_root / contaminated_name
    other = temporary if contaminated == output else output
    poison_bytes = b"receipt reparse poison" * 17
    target = receipt_root.parent.parent / f"{contaminated_name}.reparse-target"
    target.write_bytes(poison_bytes)
    contaminated.hardlink_to(target)
    other.write_bytes(b"ordinary receipt diagnostic")
    real_is_reparse = build_context._is_reparse
    monkeypatch.setattr(
        build_context,
        "_is_reparse",
        lambda info: info.st_size == len(poison_bytes) or real_is_reparse(info),
    )

    with pytest.raises(build_context.StageError, match="link or reparse point|not a plain file"):
        build_context.create_image_receipt(
            inspect_payload,
            **inputs,
            output_path=output,
        )

    assert target.read_bytes() == poison_bytes
    assert contaminated.read_bytes() == poison_bytes
    assert other.read_bytes() == b"ordinary receipt diagnostic"


@pytest.mark.contract
def test_image_receipt_transport_launches_exact_docker_command_without_stdin(
    tmp_path,
    monkeypatch,
):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    output = inputs["manifest_path"].parent / "image-receipt.json"
    temporary = inputs["manifest_path"].parent / "image-receipt.json.tmp"
    output.write_bytes(b"stale receipt")
    temporary.write_bytes(b"stale temporary")
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        assert not output.exists()
        assert not temporary.exists()
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(inspect_payload, ensure_ascii=False, indent=2).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(build_context.subprocess, "run", fake_run)
    receipt = build_context.inspect_image_and_create_receipt(
        docker=r"C:\Program Files\Fake Docker\docker.exe",
        image_reference="cpw-candidate-gate:fixture",
        **inputs,
        output_path=output,
    )

    assert observed["command"] == [
        r"C:\Program Files\Fake Docker\docker.exe",
        "image",
        "inspect",
        "cpw-candidate-gate:fixture",
    ]
    assert observed["kwargs"] == {
        "check": False,
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    assert output.read_bytes() == build_context._canonical_json(receipt)
    assert not temporary.exists()


@pytest.mark.contract
@pytest.mark.parametrize(
    ("failure", "message"),
    (
        ("launch", "could not launch"),
        ("nonzero", "failed (23)"),
        ("invalid_utf", "not valid UTF-8"),
        ("invalid_json", "JSON is invalid"),
        ("normalization", "invalid RootFS diff IDs"),
    ),
)
def test_image_receipt_transport_failures_are_bounded_and_leave_no_publication(
    tmp_path,
    monkeypatch,
    failure,
    message,
):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    output = inputs["manifest_path"].parent / "image-receipt.json"
    temporary = inputs["manifest_path"].parent / "image-receipt.json.tmp"
    output.write_bytes(b"stale receipt")
    temporary.write_bytes(b"stale temporary")

    def fake_run(command, **kwargs):
        assert not output.exists()
        assert not temporary.exists()
        if failure == "launch":
            raise OSError("launch detail " + "x" * 5_000)
        if failure == "nonzero":
            return subprocess.CompletedProcess(
                command,
                23,
                stdout=b"not inspected",
                stderr=b"docker detail " + b"x" * 5_000,
            )
        if failure == "invalid_utf":
            stdout = b"\xff\xfe"
        elif failure == "invalid_json":
            stdout = b'{"unfinished":'
        else:
            invalid = copy.deepcopy(inspect_payload)
            invalid[0]["RootFS"]["Layers"] = []
            stdout = json.dumps(invalid).encode("utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(build_context.subprocess, "run", fake_run)
    with pytest.raises(build_context.StageError, match=re.escape(message)) as refused:
        build_context.inspect_image_and_create_receipt(
            docker="docker-fixture",
            image_reference="cpw-candidate-gate:fixture",
            **inputs,
            output_path=output,
        )

    assert len(str(refused.value)) < 500
    assert not output.exists()
    assert not temporary.exists()


@pytest.mark.contract
@pytest.mark.parametrize(
    "failure",
    ("launch", "nonzero", "invalid_utf", "invalid_json", "normalization"),
)
def test_image_receipt_cli_transport_failures_return_one_without_artifacts(
    tmp_path,
    monkeypatch,
    capsys,
    failure,
):
    inspect_payload, inputs = _receipt_fixture(tmp_path)
    output = inputs["manifest_path"].parent / "image-receipt.json"
    temporary = inputs["manifest_path"].parent / "image-receipt.json.tmp"
    output.write_bytes(b"stale receipt")
    temporary.write_bytes(b"stale temporary")

    def fake_run(command, **_kwargs):
        if failure == "launch":
            raise OSError("launch detail " + "x" * 5_000)
        if failure == "nonzero":
            return subprocess.CompletedProcess(
                command,
                23,
                stdout=b"not JSON",
                stderr=b"docker detail " + b"x" * 5_000,
            )
        if failure == "invalid_utf":
            stdout = b"\xff\xfe"
        elif failure == "invalid_json":
            stdout = b'{"unfinished":'
        elif failure == "normalization":
            invalid = copy.deepcopy(inspect_payload)
            invalid[0]["Config"] = None
            stdout = json.dumps(invalid).encode("utf-8")
        else:
            raise AssertionError(f"Unexpected failure fixture: {failure}")
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(build_context.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage_candidate_build_context.py",
            "image-receipt",
            "--manifest",
            str(inputs["manifest_path"]),
            "--dockerfile",
            str(inputs["dockerfile_path"]),
            "--dockerignore",
            str(inputs["dockerignore_path"]),
            "--lock",
            str(inputs["lock_path"]),
            "--platform",
            inputs["platform"],
            "--output",
            str(output),
            "--docker",
            "docker-fixture",
            "--image",
            "cpw-candidate-gate:fixture",
        ],
    )

    assert build_context.main() == 1
    captured = capsys.readouterr()
    assert "candidate build context refused:" in captured.err
    assert len(captured.err) < 700
    assert not output.exists()
    assert not temporary.exists()


@pytest.mark.contract
def test_image_receipt_transport_refuses_unsafe_custody_before_docker_launch(
    tmp_path,
    monkeypatch,
):
    _inspect_payload, inputs = _receipt_fixture(tmp_path)
    receipt_root = inputs["manifest_path"].parent
    output = receipt_root / "image-receipt.json"
    temporary = receipt_root / "image-receipt.json.tmp"
    poison = b"transport reparse poison" * 13
    target = receipt_root.parent.parent / "transport-reparse-target"
    target.write_bytes(poison)
    output.write_bytes(b"ordinary receipt sentinel")
    temporary.hardlink_to(target)
    real_is_reparse = build_context._is_reparse
    monkeypatch.setattr(
        build_context,
        "_is_reparse",
        lambda info: info.st_size == len(poison) or real_is_reparse(info),
    )

    def forbidden_run(*_args, **_kwargs):
        raise AssertionError("Docker must not launch for unsafe receipt custody")

    monkeypatch.setattr(build_context.subprocess, "run", forbidden_run)
    with pytest.raises(build_context.StageError, match="link or reparse point|not a plain file"):
        build_context.inspect_image_and_create_receipt(
            docker="docker-fixture",
            image_reference="cpw-candidate-gate:fixture",
            **inputs,
            output_path=output,
        )

    assert output.read_bytes() == b"ordinary receipt sentinel"
    assert temporary.read_bytes() == poison
    assert target.read_bytes() == poison


def _prepare_executable_candidate_repo(tmp_path: Path) -> Path:
    root = tmp_path / "committed candidate repo with spaces"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "candidate@example.invalid")
    _git(root, "config", "user.name", "Candidate Test")
    _write(root, ".gitignore", b".local/\n")
    _write(root, "requirements-dev.lock", b"synthetic candidate lock\n")
    _write(root, "scripts/candidate_gate.ps1", VALIDATOR.read_bytes())
    _write(root, "scripts/stage_candidate_build_context.py", CONTEXT_STAGER.read_bytes())
    _write(root, "deploy/candidate-gate.Dockerfile", DOCKERFILE.read_bytes())
    _write(
        root,
        "deploy/candidate-gate.Dockerfile.dockerignore",
        DOCKERIGNORE.read_bytes(),
    )
    _write(
        root,
        "pytest.ini",
        b"[pytest]\nmarkers =\n    windows_host: requires Windows host behavior\n",
    )
    validator = _text(VALIDATOR)
    allowlist = validator.split("$windowsHostTests = @(", 1)[1].split(")", 1)[0]
    windows_tests = re.findall(r'"(tests/[^\"]+\.py)"', allowlist)
    for index, relative in enumerate(windows_tests):
        _write(
            root,
            relative,
            (
                "import pytest\n"
                "pytestmark = pytest.mark.windows_host\n\n"
                f"def test_synthetic_windows_lane_{index}():\n"
                "    assert True\n"
            ).encode("utf-8"),
        )

    common_log = (
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "log = Path('.local/candidate-gate/fake-docker-log.jsonl')\n"
        "log.parent.mkdir(parents=True, exist_ok=True)\n"
        "with log.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps({'command': Path(sys.argv[0]).name, 'argv': sys.argv[1:]}) + '\\n')\n"
    )
    _write(
        root,
        "info",
        (common_log + "print('linux/amd64')\n").encode("utf-8"),
    )
    _write(root, "build", (common_log + "raise SystemExit(0)\n").encode("utf-8"))
    _write(root, "run", (common_log + "raise SystemExit(0)\n").encode("utf-8"))
    image_script = (
        "import json\n"
        "import os\n"
        "import re\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "stdin_bytes = sys.stdin.buffer.read()\n"
        "argv = sys.argv[1:]\n"
        "valid_argv = len(argv) == 2 and argv[0] == 'inspect' and "
        "re.fullmatch(r'cpw-candidate-gate:[0-9a-f]{16}', argv[1]) is not None\n"
        "log = Path('.local/candidate-gate/fake-docker-log.jsonl')\n"
        "log.parent.mkdir(parents=True, exist_ok=True)\n"
        "with log.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps({'command': 'image', 'argv': argv, "
        "'stdin_eof': stdin_bytes == b'', 'valid_argv': valid_argv}) + '\\n')\n"
        "if stdin_bytes != b'' or not valid_argv:\n"
        "    print('fake inspect transport contract failed', file=sys.stderr)\n"
        "    raise SystemExit(91)\n"
        "mode = os.environ.get('CPW_FAKE_DOCKER_INSPECT_MODE', 'success')\n"
        "if mode == 'nonzero':\n"
        "    sys.stderr.write('synthetic inspect refusal ' + 'x' * 5000)\n"
        "    raise SystemExit(23)\n"
        "if mode == 'malformed':\n"
        "    sys.stdout.buffer.write('{\\n  \\\"malformed\\\": café'.encode('utf-8'))\n"
        "    raise SystemExit(0)\n"
        "payload = [{\n"
        "    'Architecture': 'amd64',\n"
        "    'Config': {\n"
        "        'Cmd': ['python', '-m', 'pytest'],\n"
        "        'Entrypoint': None,\n"
        "        'Env': ['PYTHONUNBUFFERED=1'],\n"
        "        'Labels': {'fixture': 'café 🐦'},\n"
        "        'User': '',\n"
        "        'WorkingDir': '/workspace',\n"
        "    },\n"
        "    'Created': '2026-08-25T00:00:00Z',\n"
        "    'Id': 'sha256:' + '1' * 64,\n"
        "    'Os': 'linux',\n"
        "    'RepoDigests': ['fixture@sha256:' + '2' * 64],\n"
        "    'RootFS': {'Layers': ['sha256:' + '3' * 64], 'Type': 'layers'},\n"
        "}]\n"
        "sys.stdout.buffer.write((json.dumps(payload, ensure_ascii=False, indent=2) + '\\n').encode('utf-8'))\n"
    )
    _write(root, "image", image_script.encode("utf-8"))
    _git(root, "add", ".")
    _git(root, "commit", "-m", "synthetic candidate")
    return root


def _run_executable_candidate_gate(root: Path, mode: str) -> subprocess.CompletedProcess:
    powershell = shutil.which("powershell.exe")
    git = shutil.which("git.exe") or shutil.which("git")
    assert powershell is not None
    assert git is not None
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.casefold() == "psmodulepath":
            del environment[key]
    environment["PSModulePath"] = str(
        Path(environment["WINDIR"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "Modules"
    )
    environment["CPW_FAKE_DOCKER_INSPECT_MODE"] = mode
    return subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/candidate_gate.ps1",
            "-ProjectRoot",
            str(root),
            "-PythonPath",
            sys.executable,
            "-DockerPath",
            sys.executable,
            "-GitPath",
            git,
        ],
        cwd=root,
        env=environment,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


@pytest.mark.contract
@pytest.mark.windows_host
def test_candidate_gate_executable_transport_succeeds_in_committed_path_with_spaces(tmp_path):
    root = _prepare_executable_candidate_repo(tmp_path)
    receipt_root = root / ".local" / "candidate-gate"
    receipt_root.mkdir(parents=True)
    receipt = receipt_root / "image-receipt.json"
    temporary = receipt_root / "image-receipt.json.tmp"
    sentinel = receipt_root / "path-safety-sentinel"
    receipt.write_bytes(b"seeded stale receipt")
    temporary.write_bytes(b"seeded stale temporary")
    sentinel.write_bytes(b"preserve this sibling")

    completed = _run_executable_candidate_gate(root, "success")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "candidate-gate passed all Linux and Windows host stages." in completed.stdout
    assert "candidate-gate image: id=sha256:" in completed.stdout
    assert "candidate-gate receipt: stable_sha256=" in completed.stdout
    assert sentinel.read_bytes() == b"preserve this sibling"
    assert not temporary.exists()
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt.read_bytes() == build_context._canonical_json(receipt_payload)
    assert receipt_payload["stable"]["schema"] == build_context.RECEIPT_SCHEMA
    assert receipt_payload["stable_sha256"] == hashlib.sha256(
        build_context._canonical_json(receipt_payload["stable"])
    ).hexdigest()
    manifest = receipt_root / "build-context-manifest.json"
    assert receipt_payload["stable"]["inputs"]["build_context_manifest_sha256"] == (
        hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    assert receipt_payload["diagnostics"] == {
        "created": "2026-08-25T00:00:00Z",
        "raw_image_id": f"sha256:{'1' * 64}",
        "repo_digests": [f"fixture@sha256:{'2' * 64}"],
    }
    log = [
        json.loads(line)
        for line in (receipt_root / "fake-docker-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    inspections = [entry for entry in log if entry["command"] == "image"]
    assert len(inspections) == 1
    assert inspections[0]["stdin_eof"] is True
    assert inspections[0]["valid_argv"] is True


@pytest.mark.contract
@pytest.mark.windows_host
@pytest.mark.parametrize("mode", ("nonzero", "malformed"))
def test_candidate_gate_executable_transport_failure_is_bounded_and_runs_windows_lane(
    tmp_path,
    mode,
):
    root = _prepare_executable_candidate_repo(tmp_path)
    receipt_root = root / ".local" / "candidate-gate"
    receipt_root.mkdir(parents=True)
    receipt = receipt_root / "image-receipt.json"
    temporary = receipt_root / "image-receipt.json.tmp"
    receipt.write_bytes(b"seeded stale receipt")
    temporary.write_bytes(b"seeded stale temporary")

    completed = _run_executable_candidate_gate(root, mode)

    assert completed.returncode == 1
    assert "candidate-gate stage: Windows host pytest" in completed.stdout
    assert "both platform lanes were attempted" in completed.stderr
    assert "candidate-gate Linux lane could not run" in completed.stderr
    expected = "failed (23)" if mode == "nonzero" else "JSON is invalid"
    assert expected in completed.stderr
    assert len(completed.stderr) < 2_000
    assert not receipt.exists()
    assert not temporary.exists()
    log = [
        json.loads(line)
        for line in (receipt_root / "fake-docker-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len([entry for entry in log if entry["command"] == "image"]) == 1


@pytest.mark.contract
def test_validator_aggregates_linux_stages_then_runs_windows_after_failures():
    validator = _text(VALIDATOR)
    linux_loop = validator.index("foreach ($stage in $linuxStages)")
    platform_guard = validator.index(
        "[Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT"
    )
    windows_lane = validator.index('Label "Windows host pytest"')
    aggregate = validator.index("if ($failureCount -ne 0)")

    assert linux_loop < platform_guard < windows_lane < aggregate
    assert "$failureCount += 1" in validator[linux_loop:windows_lane]
    assert "throw" not in validator[linux_loop:aggregate]
    assert "both platform lanes were attempted" in validator
    stage_runner = validator.split("function Invoke-RecordedCommand", 1)[1].split(
        "$ProjectRoot =", 1
    )[0]
    assert "[Console]::Out.WriteLine" in stage_runner
    assert "return $exitCode" in stage_runner
