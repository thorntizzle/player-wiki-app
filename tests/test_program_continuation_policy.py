from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.windows_host  # @pytest.mark.windows_host applies module-wide.


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_agent_instructions.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def run_validator(
    tmp_path: Path, *, include_overseer: bool = False
) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        pytest.skip("PowerShell is required for the instruction validator")

    skill_root = tmp_path / "skills"
    for name in (
        "campaign-player-wiki-app",
        "campaign-player-wiki-characters",
        "campaign-player-wiki-feedback-logger",
        "campaign-player-wiki-live",
        "campaign-player-wiki-ops-deploy",
        "campaign-player-wiki-publishing",
        "campaign-player-wiki-systems",
    ):
        skill = skill_root / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            f"---\nname: {name}\ndescription: Test fixture.\n---\n",
            encoding="utf-8",
        )
    if include_overseer:
        obsolete = skill_root / "campaign-player-wiki-overseer" / "SKILL.md"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text(
            "---\nname: campaign-player-wiki-overseer\ndescription: Obsolete.\n---\n",
            encoding="utf-8",
        )

    return subprocess.run(
        (
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VALIDATOR),
            "-RepoRoot",
            str(PROJECT_ROOT),
            "-SkillRoot",
            str(skill_root),
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_core_workflow_uses_exalt_lifecycle() -> None:
    router = read("AGENTS.md")
    roles = read("docs/workflows/agent-roles.md")
    operating = read("docs/workflows/agent-operating-model.md")
    guardrails = read("docs/workflows/repo-guardrails.md")
    delegation = read("docs/workflows/worker-delegation.md")

    assert "Stable Program ID and cumulative budgets" in router
    assert "Initial Requirements Freeze" in router
    assert "Frozen Failure Inventory" in router
    assert "one initial candidate plus two repair candidates" in router
    assert "no persistent Program Overseer or Publisher role" in roles
    assert "Replace-Only Context Capsule" in operating
    assert "Documentation-Only Validation" in guardrails
    assert "Assembly And Repair" in delegation


def test_legacy_overseer_workflows_are_removed() -> None:
    assert not (PROJECT_ROOT / "docs/workflows/authority-lanes.md").exists()
    assert not (PROJECT_ROOT / "docs/workflows/context-loading.md").exists()
    assert not (PROJECT_ROOT / "docs/workflows/flask-rewrite-program.md").exists()

    combined = "\n".join(
        read(path)
        for path in (
            "AGENTS.md",
            "docs/workflows/INDEX.md",
            "docs/workflows/agent-roles.md",
            "docs/workflows/agent-operating-model.md",
        )
    )
    assert "persistent Program Overseer or heartbeat layer" in combined
    assert "persistent tasks and heartbeats" not in combined.lower()


def test_external_side_effects_remain_explicit_gates() -> None:
    router = read("AGENTS.md")
    guardrails = read("docs/workflows/repo-guardrails.md")
    compact_router = " ".join(router.split())

    for action in ("Commit", "push", "PR", "merge", "deploy", "live content"):
        assert action in guardrails
    assert "A code request does not imply deployment" in compact_router
    assert "a content task does not imply publication" in compact_router


def test_instruction_validator_accepts_canonical_skill_family(tmp_path: Path) -> None:
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Agent instruction validation passed." in result.stdout


def test_instruction_validator_rejects_overseer_skill(tmp_path: Path) -> None:
    result = run_validator(tmp_path, include_overseer=True)
    assert result.returncode != 0
    assert "Obsolete skill directory exists: campaign-player-wiki-overseer" in (
        result.stdout + result.stderr
    )
