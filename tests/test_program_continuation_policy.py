from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_agent_instructions.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

VALID_OVERSEER_SKILL = """\
---
name: campaign-player-wiki-overseer
description: Test fixture for the program continuation policy.
---

name its owner and next action, and continue automatically.
Retry count alone never converts a routine failure.
ordinary ambiguity is `RECOVERING`, not a safety stop.
The Program Overseer and the same dependent Orchestrator retain ownership.
then remain `WAITING` with reason `monitor-recovery`.
Only an unresolved product decision (`DECISION_REQUIRED`) or a genuine safety
issue (`SAFETY_STOP`) may stop the program.
Use an open side-effect gate rather than a terminal program result.
Do not make the user approve already-authorized local integration.
Never infer main or remote integration authority.
"""


def read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def compact(value: str) -> str:
    return " ".join(value.split())


def run_overseer_validator(
    tmp_path: Path, overseer_skill: str
) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        pytest.skip("PowerShell is required for the instruction validator")

    skill_root = tmp_path / "skills"
    live_skill = skill_root / "campaign-player-wiki-live" / "SKILL.md"
    live_skill.parent.mkdir(parents=True)
    live_skill.write_text(
        "---\nname: campaign-player-wiki-live\ndescription: Test fixture.\n---\n",
        encoding="utf-8",
    )
    overseer_path = skill_root / "campaign-player-wiki-overseer" / "SKILL.md"
    overseer_path.parent.mkdir(parents=True)
    overseer_path.write_text(overseer_skill, encoding="utf-8")

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


def test_core_workflow_defines_continuation_states() -> None:
    router = read("AGENTS.md")
    roles = read("docs/workflows/agent-roles.md")
    authority = read("docs/workflows/authority-lanes.md")
    program = read("docs/workflows/flask-rewrite-program.md")
    router_compact = compact(router)
    authority_compact = compact(authority)
    program_compact = compact(program)

    for state in (
        "RECOVERING",
        "WAITING",
        "READY_FOR_AUTHORIZATION",
        "DECISION_REQUIRED",
        "SAFETY_STOP",
    ):
        assert state in roles

    assert "A failed command" in router
    assert "is not a terminal program result" in router
    assert "Only an unresolved product" in router
    assert "Never record these conditions as terminal" in program
    assert "Repeated routine failure changes the recovery method" in program
    assert (
        "routine operational failures are classified and routed through a new "
        "bounded recovery gate"
    ) in program_compact
    assert (
        "Only an unresolved product decision or a genuine safety issue stops "
        "the program"
    ) in program_compact
    assert "Do not turn that" in router
    assert "routine internal assembly into a new operator gate" in router
    assert (
        "integration into `main` or another protected target"
    ) in router_compact
    assert "bounded local slice-to-durable integration" in authority_compact
    assert "do not request new approval for routine local assembly" in program
    assert (
        "Pushing, opening a pull request, merging to `main`, deploying, or "
        "performing a live-data operation remains an explicit user gate"
    ) in program_compact


def test_core_workflow_does_not_restore_terminal_hold_directives() -> None:
    router = read("AGENTS.md")
    roles = read("docs/workflows/agent-roles.md")
    authority = read("docs/workflows/authority-lanes.md")
    program = read("docs/workflows/flask-rewrite-program.md")

    combined = "\n".join((router, roles, authority, program))
    for obsolete_directive in (
        "place the slice on `HOLD`",
        "keep the slice on `HOLD`",
        "Escalate for tool or app recovery",
        "stops the Publisher",
        "stops the release gate",
    ):
        assert obsolete_directive not in combined

    assert "An authority gate is not a terminal program result" in authority
    assert "Identity ambiguity" in roles


def test_scenario_actions_remain_explicit() -> None:
    roles = read("docs/workflows/agent-roles.md")
    program = read("docs/workflows/flask-rewrite-program.md")
    validator = read("scripts/validate_agent_instructions.ps1")

    assert "correct the smallest harness" in program
    assert "rerun the same exact candidate automatically" in program
    assert "A rejected candidate returns to repair" in program
    assert "require fresh independent verification" in roles
    assert "Keep monitoring and resume automatically" in roles
    assert "Retry count alone never promotes them" in roles
    assert "only program-stopping states" in roles
    assert "This is not a failure" in roles
    assert "monitor-recovery wake state" in validator
    assert "decision and safety stop boundary" in validator
    assert "authorization is nonterminal" in validator
    assert "protected-target integration boundary" in validator


def test_overseer_validator_accepts_continuation_contract(tmp_path: Path) -> None:
    result = run_overseer_validator(tmp_path, VALID_OVERSEER_SKILL)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Agent instruction validation passed." in result.stdout


@pytest.mark.parametrize(
    ("mutated_skill", "expected_error"),
    (
        (
            VALID_OVERSEER_SKILL.replace(
                "`SAFETY_STOP`", "`SAFETY_PAUSE`"
            ),
            "decision and safety stop boundary",
        ),
        (
            VALID_OVERSEER_SKILL.replace(
                "remain `WAITING` with reason `monitor-recovery`",
                "remain `WAITING_FOR_MONITOR_RECOVERY`",
            ),
            "monitor-recovery wake state",
        ),
        (
            VALID_OVERSEER_SKILL.replace(
                "Never infer main or remote integration authority.",
                "Infer main integration authority.",
            ),
            "protected-target integration boundary",
        ),
    ),
)
def test_overseer_validator_rejects_policy_regressions(
    tmp_path: Path, mutated_skill: str, expected_error: str
) -> None:
    result = run_overseer_validator(tmp_path, mutated_skill)

    assert result.returncode != 0
    assert expected_error in result.stdout + result.stderr
