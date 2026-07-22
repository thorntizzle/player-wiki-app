from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_agent_instructions.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

REQUIRED_FILES = (
    "AGENTS.md",
    "docs/workflows/INDEX.md",
    "docs/workflows/agent-roles.md",
    "docs/workflows/authority-lanes.md",
    "docs/workflows/context-loading.md",
    "docs/workflows/worktrees.md",
    "docs/workflows/flask-rewrite-program.md",
)

VALID_ROW = (
    "| Phase 7 | `0123456789abcdef0123456789abcdef01234567` | "
    "`89abcdef0123456789abcdef0123456789abcdef` | "
    "`.local/roadmaps/phase7-lifecycle.md` | 123 | "
    "`ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789` | "
    "`2026-07-22T15:16:17.1234567Z` |"
)


def anchor_document(row: str = VALID_ROW, prose: str = "Final factual anchor.") -> str:
    return "\n".join(
        (
            "# Phase Closeout Evidence Anchors",
            "",
            "| Phase | Accepted commit | Accepted tree | Relative lifecycle record | Bytes | SHA-256 | Finalized UTC |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
            row,
            "",
            prose,
            "",
        )
    )


def run_validator(tmp_path: Path, anchor: str) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        pytest.skip("PowerShell is required for the instruction validator")

    for relative in REQUIRED_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Fixture\n", encoding="utf-8")
    anchor_path = tmp_path / "docs/contracts/phase-closeout-evidence-anchors.md"
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.write_text(anchor, encoding="utf-8")

    return subprocess.run(
        (
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VALIDATOR),
            "-RepoRoot",
            str(tmp_path),
            "-SkillRoot",
            str(tmp_path / "missing-skills"),
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_valid_anchor_row_passes(tmp_path: Path) -> None:
    result = run_validator(tmp_path, anchor_document())

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Agent instruction validation passed." in result.stdout


@pytest.mark.parametrize(
    ("bad_row", "expected_error"),
    (
        (
            VALID_ROW.replace("0123456789abcdef0123456789abcdef01234567", "short"),
            "Malformed accepted commit",
        ),
        (
            VALID_ROW.replace("89abcdef0123456789abcdef0123456789abcdef", "bad-tree"),
            "Malformed accepted tree",
        ),
        (
            VALID_ROW.replace(
                "ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789",
                "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            ),
            "Malformed uppercase SHA-256",
        ),
        (VALID_ROW.replace("| 123 |", "| 0 |"), "Malformed positive byte count"),
        (
            VALID_ROW.replace("2026-07-22T15:16:17.1234567Z", "2026-13-22 15:16:17"),
            "Malformed UTC finalization timestamp",
        ),
        (
            VALID_ROW.replace(".local/roadmaps/phase7-lifecycle.md", "../outside.md"),
            "Malformed lifecycle record path",
        ),
        (
            VALID_ROW.rsplit(" |", 1)[0] + " | unexpected |",
            "expected 7 cells",
        ),
    ),
)
def test_malformed_anchor_cells_fail(
    tmp_path: Path, bad_row: str, expected_error: str
) -> None:
    result = run_validator(tmp_path, anchor_document(row=bad_row))

    assert result.returncode != 0
    assert expected_error in result.stdout + result.stderr


@pytest.mark.parametrize(
    "pending_prose",
    (
        "These bytes are pending verification.",
        "This anchor is awaiting commit.",
        "This row will be pushed.",
        "This record is not yet verified.",
        "Commit is pending.",
    ),
)
def test_pending_anchor_state_language_fails(
    tmp_path: Path, pending_prose: str
) -> None:
    result = run_validator(tmp_path, anchor_document(prose=pending_prose))

    assert result.returncode != 0
    assert "Prospective pending-state wording" in result.stdout + result.stderr
