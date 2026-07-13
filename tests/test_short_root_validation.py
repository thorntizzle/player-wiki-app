from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER = PROJECT_ROOT / "scripts" / "invoke_short_root_validation.ps1"
LOCAL_WRAPPER = PROJECT_ROOT / "local.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("powershell.exe")


def run_command(
    arguments: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return run_command(["git", *arguments], cwd=repo)


def initialize_mini_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    assert git(repo, "init").returncode == 0
    assert git(repo, "config", "user.email", "short-root@example.test").returncode == 0
    assert git(repo, "config", "user.name", "Short Root Test").returncode == 0
    (repo / ".gitattributes").write_text(
        "* text=auto\n*.txt text\n*.bin -text\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(".local/\n", encoding="utf-8")
    (repo / "normalized.txt").write_text("alpha\nbeta\n", encoding="utf-8", newline="\n")
    (repo / "payload.bin").write_bytes(b"\x00\x01\r\n\xff")
    (repo / "local.ps1").write_text(
        "\n".join(
            [
                "param(",
                "    [string]$Action = '',",
                "    [string]$PythonPath = '',",
                "    [string]$TestPath = ''",
                ")",
                "$head = (& git rev-parse HEAD).Trim()",
                "$tree = (& git rev-parse 'HEAD^{tree}').Trim()",
                'Write-Host "MINI_HEAD=$head"',
                'Write-Host "MINI_TREE=$tree"',
                'Write-Host "MINI_ACTION=$Action"',
                'Write-Host "MINI_TEST_PATH=$TestPath"',
                "New-Item -ItemType Directory -Force -Path .local | Out-Null",
                "Set-Content -LiteralPath .local/validation-scratch.txt -Value scratch",
                "(Get-Item -LiteralPath .local/validation-scratch.txt).IsReadOnly = $true",
                "exit [int]$env:MINI_VALIDATION_EXIT",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    assert git(repo, "add", ".").returncode == 0
    assert git(repo, "commit", "-m", "mini validation fixture").returncode == 0
    return repo


def invoke_helper(
    repo: Path,
    short_base: Path,
    *,
    exit_code: int = 0,
    remove_on_success: bool = False,
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    env = os.environ.copy()
    env["MINI_VALIDATION_EXIT"] = str(exit_code)
    arguments = [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HELPER),
        "-SourceRoot",
        str(repo),
        "-RequestedAction",
        "test-focused",
        "-RequestedTestPath",
        "tests/example.py::test_example",
        "-RequestedShortRootBase",
        str(short_base),
    ]
    if remove_on_success:
        arguments.append("-RequestedRemoveOnSuccess")
    return run_command(arguments, cwd=repo, env=env)


def created_short_root(output: str) -> Path:
    match = re.search(r"Creating detached physical short-root checkout: (.+)", output)
    assert match is not None, output
    return Path(match.group(1).strip())


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")
def test_short_root_helper_rejects_dirty_source_including_untracked_files(tmp_path):
    repo = initialize_mini_repo(tmp_path)
    (repo / "untracked.txt").write_text("not committed", encoding="utf-8")
    short_base = tmp_path / "short"

    result = invoke_helper(repo, short_base)

    assert result.returncode == 1
    assert "requires a clean source checkout" in result.stderr
    assert not short_base.exists()


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")
def test_short_root_helper_uses_git_identity_for_normalized_text_and_raw_binary(
    tmp_path,
):
    repo = initialize_mini_repo(tmp_path)
    assert git(repo, "config", "core.autocrlf", "true").returncode == 0
    (repo / "normalized.txt").unlink()
    assert git(repo, "checkout", "--", "normalized.txt").returncode == 0
    assert (repo / "normalized.txt").read_bytes() == b"alpha\r\nbeta\r\n"
    assert git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""
    expected_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    expected_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    result = invoke_helper(repo, tmp_path / "short")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert f"Short-root identity verified: commit={expected_head} tree={expected_tree}" in output
    assert f"MINI_HEAD={expected_head}" in output
    assert f"MINI_TREE={expected_tree}" in output
    destination = created_short_root(output)
    assert destination.is_dir()
    assert (destination / "normalized.txt").read_bytes() == b"alpha\r\nbeta\r\n"
    assert (destination / "payload.bin").read_bytes() == (repo / "payload.bin").read_bytes()


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")
def test_byte_sensitive_identity_check_rejects_raw_mismatch(tmp_path):
    repo = initialize_mini_repo(tmp_path)
    destination = tmp_path / "detached"
    assert git(repo, "worktree", "add", "--detach", str(destination), "HEAD").returncode == 0
    (destination / "payload.bin").write_bytes(b"different")
    command = (
        f". '{HELPER}'; "
        f"try {{ Compare-ByteSensitiveValidationFiles -Source '{repo}' -Destination '{destination}'; exit 0 }} "
        "catch { Write-Output $_.Exception.Message; exit 1 }"
    )

    result = run_command(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=repo,
    )

    assert result.returncode == 1
    assert "Byte-sensitive tracked file differs" in result.stdout + result.stderr


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")
def test_short_root_helper_propagates_exit_and_retains_unique_failure_roots(tmp_path):
    repo = initialize_mini_repo(tmp_path)
    short_base = tmp_path / "short"

    first = invoke_helper(repo, short_base, exit_code=7, remove_on_success=True)
    second = invoke_helper(repo, short_base, exit_code=7, remove_on_success=True)

    assert first.returncode == 7
    assert second.returncode == 7
    first_root = created_short_root(first.stdout + first.stderr)
    second_root = created_short_root(second.stdout + second.stderr)
    assert first_root != second_root
    assert first_root.is_dir()
    assert second_root.is_dir()
    assert "Short-root checkout retained" in first.stdout
    assert "Short-root checkout retained" in second.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")
def test_short_root_success_retention_and_explicit_verified_cleanup(tmp_path):
    repo = initialize_mini_repo(tmp_path)
    short_base = tmp_path / "short"

    retained = invoke_helper(repo, short_base)
    removed = invoke_helper(repo, short_base, remove_on_success=True)

    retained_output = retained.stdout + retained.stderr
    removed_output = removed.stdout + removed.stderr
    retained_root = created_short_root(retained_output)
    removed_root = created_short_root(removed_output)
    assert retained.returncode == 0, retained_output
    assert removed.returncode == 0, removed_output
    assert retained_root.is_dir()
    assert not removed_root.exists()
    assert "Removed verified successful short-root checkout" in removed_output


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")
def test_complete_validation_lock_blocks_competitor_and_allows_guarded_recursion(
    tmp_path,
):
    repo = initialize_mini_repo(tmp_path)
    ready = tmp_path / "ready.txt"
    nested = tmp_path / "nested.txt"
    holder_command = (
        f". '{HELPER}'; "
        f"Invoke-WithCompleteValidationLock -ProjectRoot '{repo}' -ActionName test -ScriptBlock {{ "
        f"Invoke-WithCompleteValidationLock -ProjectRoot '{repo}' -ActionName test -ScriptBlock {{ "
        f"Set-Content -LiteralPath '{nested}' -Value nested }}; "
        f"Set-Content -LiteralPath '{ready}' -Value ready; Start-Sleep -Seconds 3 }}"
    )
    competitor_command = (
        f". '{HELPER}'; try {{ "
        f"Invoke-WithCompleteValidationLock -ProjectRoot '{repo}' -ActionName check -ScriptBlock {{ }}; exit 0 "
        "} catch { Write-Output $_.Exception.Message; exit 1 }"
    )
    holder = subprocess.Popen(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", holder_command],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not ready.exists():
        holder_stdout, holder_stderr = holder.communicate(timeout=10)
        pytest.fail(holder_stdout + holder_stderr)
    assert nested.exists()

    competitor = run_command(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", competitor_command],
        cwd=repo,
    )
    holder_stdout, holder_stderr = holder.communicate(timeout=10)

    assert holder.returncode == 0, holder_stdout + holder_stderr
    assert competitor.returncode == 1
    assert "Another complete validation is already running" in (
        competitor.stdout + competitor.stderr
    )


def test_local_wrapper_declares_exact_maintained_restore_and_browser_groups():
    content = LOCAL_WRAPPER.read_text(encoding="utf-8")
    for action in ("test-restore", "test-browser"):
        assert f'"{action}"' in content
    for path in (
        "tests/test_backup_archive.py",
        "tests/test_operations.py",
        "tests/test_restore_transaction.py",
        "tests/test_runtime_lease.py",
        "tests/test_sqlite_safety.py",
        "tests/test_character_read_shell_browser.py",
        "tests/test_combat_dm_controls_browser.py",
        "tests/test_static_assets.py",
    ):
        assert content.count(f'"{path}"') >= 1
    assert "test-focused" in content
    assert "test-serial" in content
    assert "$PhysicalShortRoot" in content
    assert "$ShortRootBase" in content
    assert "$RemoveShortRootOnSuccess" in content
