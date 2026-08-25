from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validation_evidence.py"
LOCAL_WRAPPER = PROJECT_ROOT / "local.ps1"
SPEC = importlib.util.spec_from_file_location("validation_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validation_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation_evidence)


def run(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(arguments),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def git(repo: Path, *arguments: str) -> str:
    result = run(repo, "git", *arguments)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def initialize_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init")
    git(repo, "config", "user.email", "validation-evidence@example.test")
    git(repo, "config", "user.name", "Validation Evidence Test")
    git(repo, "config", "core.fileMode", "false")
    write(repo / ".gitignore", ".local/\n")
    write(repo / "player_wiki" / "__init__.py", "RUNTIME = 1\n")
    write(repo / "tests" / "test_sample.py", "def test_sample():\n    assert True\n")
    write(repo / "docs" / "workflows" / "program.md", "workflow\n")
    write(repo / "docs" / "current-state" / "ops.md", "state one\n")
    write(repo / "docs" / "contracts" / "anchor.md", "anchor one\n")
    write(repo / "scripts" / "runner.py", "print('runner')\n")
    write(repo / "scripts" / "other.py", "OTHER = 1\n")
    write(repo / "config" / "settings.toml", "setting = 1\n")
    write(repo / "manage.py", "print('manage')\n")
    write(repo / "local.ps1", "Write-Output 'local'\n")
    write(repo / "requirements-dev.lock", "package==1 --hash=sha256:abcd\n")
    write(repo / "fly.toml", "[build]\n")
    write(repo / "Dockerfile", "FROM scratch\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    assert git(repo, "status", "--short") == ""
    evidence = repo / ".local" / "evidence"
    evidence.mkdir(parents=True)
    write(evidence / "envelope.json", "{}\n")
    write(evidence / "verdict.json", '{"status":"ACCEPT"}\n')
    write(evidence / "index.json", '{"entries":[]}\n')
    write(evidence / "seal.json", '{"sealed":true}\n')
    return repo


def file_identity(repo: Path, relative: str) -> dict[str, str]:
    return {
        "path": relative,
        "sha256": validation_evidence.sha256_file(repo / relative),
    }


def freeze_config(repo: Path, *, commit: str | None = None) -> dict[str, object]:
    commit = commit or git(repo, "rev-parse", "HEAD")
    return {
        "candidate_commit": commit,
        "fly_blobs": [
            {
                "path": "Dockerfile",
                "blob": git(repo, "rev-parse", f"{commit}:Dockerfile"),
            },
            {
                "path": "fly.toml",
                "blob": git(repo, "rev-parse", f"{commit}:fly.toml"),
            },
        ],
        "dependencies": {
            **file_identity(repo, "requirements-dev.lock"),
            "package_count": 29,
        },
        "runner": file_identity(repo, "scripts/runner.py"),
        "envelope": file_identity(repo, ".local/evidence/envelope.json"),
        "suite": {
            "verdict": file_identity(repo, ".local/evidence/verdict.json"),
            "index": file_identity(repo, ".local/evidence/index.json"),
            "seal": file_identity(repo, ".local/evidence/seal.json"),
        },
        "invalidators": [
            "application_ambiguity",
            "environment",
            "runner",
            "runtime_tree",
            "tests_tree",
            "workflow_tree",
        ],
    }


def frozen(repo: Path) -> dict[str, object]:
    return validation_evidence.build_frozen_identity(
        validation_evidence.normalize_repo_root(repo),
        freeze_config(repo),
    )


def reseal(receipt: dict[str, object], **changes: object) -> dict[str, object]:
    core = {
        key: value
        for key, value in receipt.items()
        if key != "receipt_sha256"
    }
    core.update(changes)
    return validation_evidence.seal_receipt(core)


def commit_file(repo: Path, relative: str, content: str, message: str = "change") -> None:
    write(repo / relative, content)
    git(repo, "add", relative)
    git(repo, "commit", "-m", message)


def assess(
    repo: Path,
    baseline: dict[str, object],
    current: dict[str, object],
    *,
    ambiguity: bool = False,
) -> dict[str, object]:
    return validation_evidence.build_reuse_decision(
        validation_evidence.normalize_repo_root(repo),
        baseline,
        current,
        application_ambiguity=ambiguity,
    )


def test_freeze_records_exact_clean_identity_and_is_canonical(tmp_path):
    repo = initialize_repo(tmp_path)
    first = frozen(repo)
    second = frozen(repo)

    assert validation_evidence.canonical_json_bytes(first) == (
        validation_evidence.canonical_json_bytes(second)
    )
    assert first["candidate"] == {
        "commit": git(repo, "rev-parse", "HEAD"),
        "tree": git(repo, "rev-parse", "HEAD^{tree}"),
        "runtime_tree": git(repo, "rev-parse", "HEAD:player_wiki"),
        "tests_tree": git(repo, "rev-parse", "HEAD:tests"),
        "workflow_tree": git(repo, "rev-parse", "HEAD:docs/workflows"),
    }
    assert first["root"] == "."
    assert first["interpreter"]["version"]
    assert len(first["interpreter"]["executable_sha256"]) == 64
    assert first["receipt_sha256"] == validation_evidence.sha256_bytes(
        validation_evidence.canonical_json_bytes(
            {
                key: value
                for key, value in first.items()
                if key != "receipt_sha256"
            }
        )
    )


def test_freeze_cli_writes_canonical_bytes_atomically(tmp_path):
    repo = initialize_repo(tmp_path)
    config_path = repo / ".local" / "freeze.json"
    output = repo / ".local" / "frozen.json"
    config_path.write_bytes(validation_evidence.canonical_json_bytes(freeze_config(repo)))

    result = validation_evidence.command_freeze(
        Namespace(
            repo_root=str(repo),
            config=str(config_path),
            output=str(output),
        )
    )

    assert output.read_bytes() == validation_evidence.canonical_json_bytes(result)
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_generic_sealed_payload_verifier_supports_downstream_schemas():
    core = {
        "schema": "campaign-player-wiki.publisher-result",
        "schema_version": 1,
        "kind": "FOCUSED_GATE_PASS",
        "count": 55,
    }
    receipt = {
        **core,
        "receipt_sha256": validation_evidence.sha256_bytes(
            validation_evidence.canonical_json_bytes(core)
        ),
    }

    assert (
        validation_evidence.verify_sealed_payload(
            receipt,
            expected_schema="campaign-player-wiki.publisher-result",
            expected_kind="FOCUSED_GATE_PASS",
        )
        is receipt
    )
    with pytest.raises(validation_evidence.EvidenceError, match="hash"):
        validation_evidence.verify_sealed_payload(
            {**receipt, "count": 54},
            expected_schema="campaign-player-wiki.publisher-result",
            expected_kind="FOCUSED_GATE_PASS",
        )


def test_freeze_refuses_dirty_repo_and_abbreviated_commit(tmp_path):
    repo = initialize_repo(tmp_path)
    config = freeze_config(repo)
    config["candidate_commit"] = str(config["candidate_commit"])[:8]
    with pytest.raises(validation_evidence.EvidenceError, match="full lowercase"):
        validation_evidence.build_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            config,
        )

    config = freeze_config(repo)
    write(repo / "untracked.txt", "dirty\n")
    with pytest.raises(validation_evidence.EvidenceError, match="clean repo root"):
        validation_evidence.build_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            config,
        )


def test_freeze_refuses_traversal_uncontained_and_reparse_paths(tmp_path, monkeypatch):
    repo = initialize_repo(tmp_path)
    config = freeze_config(repo)
    config["runner"]["path"] = "../outside.py"
    with pytest.raises(validation_evidence.EvidenceError, match="traversal"):
        validation_evidence.build_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            config,
        )

    config = freeze_config(repo)
    linked = repo / ".local" / "evidence" / "linked.json"
    write(linked, "{}\n")
    config["envelope"] = file_identity(repo, ".local/evidence/linked.json")
    original = validation_evidence._is_reparse
    monkeypatch.setattr(
        validation_evidence,
        "_is_reparse",
        lambda path: path == linked or original(path),
    )
    with pytest.raises(validation_evidence.EvidenceError, match="reparse"):
        validation_evidence.build_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            config,
        )


def test_freeze_refuses_missing_and_duplicate_identities(tmp_path):
    repo = initialize_repo(tmp_path)
    config = freeze_config(repo)
    del config["suite"]["seal"]
    with pytest.raises(validation_evidence.EvidenceError, match="fields mismatch"):
        validation_evidence.build_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            config,
        )

    config = freeze_config(repo)
    config["envelope"] = dict(config["runner"])
    with pytest.raises(validation_evidence.EvidenceError, match="distinct paths"):
        validation_evidence.build_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            config,
        )


def test_json_loader_refuses_duplicate_and_private_field_names(tmp_path):
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"runner":1,"runner":2}\n', encoding="utf-8")
    with pytest.raises(validation_evidence.EvidenceError, match="duplicate JSON field"):
        validation_evidence.load_json(duplicate)

    private = tmp_path / "private.json"
    private.write_text('{"access_token":"must-not-enter-evidence"}\n', encoding="utf-8")
    with pytest.raises(validation_evidence.EvidenceError, match="private field"):
        validation_evidence.load_json(private)


def test_frozen_receipt_strictly_validates_candidate_and_nested_shapes(tmp_path):
    repo = initialize_repo(tmp_path)
    identity = frozen(repo)
    root = validation_evidence.normalize_repo_root(repo)

    malformed_values = []

    missing_tree = copy.deepcopy(identity)
    del missing_tree["candidate"]["tree"]
    malformed_values.append(reseal(missing_tree))

    wrong_tree = copy.deepcopy(identity)
    wrong_tree["candidate"]["tree"] = "f" * 40
    malformed_values.append(reseal(wrong_tree))

    abbreviated_subtree = copy.deepcopy(identity)
    abbreviated_subtree["candidate"]["runtime_tree"] = str(
        abbreviated_subtree["candidate"]["runtime_tree"]
    )[:8]
    malformed_values.append(reseal(abbreviated_subtree))

    malformed_runner = copy.deepcopy(identity)
    del malformed_runner["runner"]["sha256"]
    malformed_values.append(reseal(malformed_runner))

    malformed_dependency = copy.deepcopy(identity)
    malformed_dependency["dependencies"]["package_count"] = True
    malformed_values.append(reseal(malformed_dependency))

    malformed_suite = copy.deepcopy(identity)
    malformed_suite["suite"]["seal"] = []
    malformed_values.append(reseal(malformed_suite))

    malformed_fly = copy.deepcopy(identity)
    malformed_fly["fly_blobs"][0]["unexpected"] = "field"
    malformed_values.append(reseal(malformed_fly))

    malformed_interpreter = copy.deepcopy(identity)
    malformed_interpreter["interpreter"]["version"] = 312
    malformed_values.append(reseal(malformed_interpreter))

    for malformed in malformed_values:
        with pytest.raises(validation_evidence.EvidenceError):
            validation_evidence.verify_frozen_identity(root, malformed)


def test_frozen_receipt_refuses_private_and_extra_fields_even_when_self_sealed(tmp_path):
    repo = initialize_repo(tmp_path)
    identity = frozen(repo)
    core = {key: value for key, value in identity.items() if key != "receipt_sha256"}
    core["access_token"] = "not-allowed"
    private_receipt = {
        **core,
        "receipt_sha256": validation_evidence.sha256_bytes(
            validation_evidence.canonical_json_bytes(core)
        ),
    }
    with pytest.raises(validation_evidence.EvidenceError, match="private field"):
        validation_evidence.verify_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            private_receipt,
        )

    extra = reseal(identity, unexpected="field")
    with pytest.raises(validation_evidence.EvidenceError, match="fields mismatch"):
        validation_evidence.verify_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            extra,
        )


def test_frozen_receipt_binds_tracked_content_at_candidate_commit(tmp_path):
    repo = initialize_repo(tmp_path)
    identity = frozen(repo)
    root = validation_evidence.normalize_repo_root(repo)
    write(repo / "scripts" / "runner.py", "print('working tree drift')\n")

    assert validation_evidence.verify_frozen_identity(root, identity) is identity

    tampered = copy.deepcopy(identity)
    tampered["runner"]["sha256"] = validation_evidence.sha256_file(
        repo / "scripts" / "runner.py"
    )
    tampered = reseal(tampered)
    with pytest.raises(validation_evidence.EvidenceError, match="candidate-bound content"):
        validation_evidence.verify_frozen_identity(root, tampered)


def test_frozen_receipt_binds_retained_ignored_evidence_hash(tmp_path):
    repo = initialize_repo(tmp_path)
    identity = frozen(repo)
    write(repo / ".local" / "evidence" / "envelope.json", '{"changed":true}\n')

    with pytest.raises(validation_evidence.EvidenceError, match="candidate-bound content"):
        validation_evidence.verify_frozen_identity(
            validation_evidence.normalize_repo_root(repo),
            identity,
        )


def test_frozen_receipt_rejects_foreign_repository_candidate(tmp_path):
    local_repo = initialize_repo(tmp_path / "local")
    foreign_repo = initialize_repo(tmp_path / "foreign")
    commit_file(
        foreign_repo,
        "docs/current-state/ops.md",
        "foreign state\n",
        "foreign",
    )
    foreign_identity = frozen(foreign_repo)

    with pytest.raises(validation_evidence.EvidenceError, match="supplied repository"):
        validation_evidence.verify_frozen_identity(
            validation_evidence.normalize_repo_root(local_repo),
            foreign_identity,
        )


def test_history_only_descendant_reuses_identity(tmp_path):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    git(repo, "commit", "--allow-empty", "-m", "history only")
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "REUSE"
    assert decision["reasons"] == ["HISTORY_ONLY_DESCENDANT"]
    assert decision["changed_identities"] == ["candidate.commit"]


@pytest.mark.parametrize(
    "relative",
    (
        "docs/current-state/ops.md",
        "docs/contracts/anchor.md",
    ),
)
def test_allowed_documentation_descendant_reuses_identity(tmp_path, relative):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    commit_file(repo, relative, "documentation two\n", "allowed docs")
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "REUSE"
    assert decision["reasons"] == ["DOCS_HISTORY_ONLY_DESCENDANT"]
    assert decision["changed_identities"] == [
        "candidate.commit",
        "candidate.tree",
        f"git.path:{relative}",
    ]


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("runtime_tree", "RUNTIME_TREE_DRIFT"),
        ("tests_tree", "TESTS_TREE_DRIFT"),
    ),
)
def test_runtime_or_tests_drift_invalidates(tmp_path, field, reason):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    relative = (
        "player_wiki/__init__.py"
        if field == "runtime_tree"
        else "tests/test_sample.py"
    )
    commit_file(repo, relative, "changed = True\n", reason)
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "INVALIDATE"
    assert reason in decision["reasons"]


def test_declared_application_ambiguity_invalidates(tmp_path):
    repo = initialize_repo(tmp_path)
    identity = frozen(repo)

    decision = assess(repo, identity, identity, ambiguity=True)

    assert decision["decision"] == "INVALIDATE"
    assert decision["reasons"] == ["APPLICATION_AMBIGUITY"]


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("runner", "RUNNER_DRIFT"),
        ("interpreter", "INTERPRETER_DRIFT"),
        ("dependencies", "DEPENDENCY_DRIFT"),
    ),
)
def test_runner_or_environment_drift_requires_reclassification(tmp_path, field, reason):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    if field == "runner":
        commit_file(repo, "scripts/runner.py", "print('runner two')\n", reason)
        current = frozen(repo)
    elif field == "dependencies":
        commit_file(
            repo,
            "requirements-dev.lock",
            "package==2 --hash=sha256:dcba\n",
            reason,
        )
        current = frozen(repo)
    else:
        changed = dict(baseline[field])
        changed["executable_sha256"] = "F" * 64
        current = reseal(baseline, **{field: changed})

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "RECLASSIFY"
    assert reason in decision["reasons"]


def test_workflow_drift_requires_reclassification(tmp_path):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    commit_file(
        repo,
        "docs/workflows/program.md",
        "workflow two\n",
        "workflow drift",
    )
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "RECLASSIFY"
    assert decision["reasons"] == ["WORKFLOW_TREE_DRIFT"]


def test_invalidator_set_drift_requires_reclassification(tmp_path):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    current = copy.deepcopy(baseline)
    current["invalidators"] = sorted(
        [*current["invalidators"], "new_invalidator"]
    )
    current = reseal(current)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "RECLASSIFY"
    assert decision["reasons"] == ["INVALIDATOR_SET_DRIFT"]
    assert decision["changed_identities"] == ["invalidators"]


@pytest.mark.parametrize("relative", ("manage.py", "local.ps1"))
def test_root_executable_drift_requires_reclassification_with_path(tmp_path, relative):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    commit_file(repo, relative, "changed root executable\n", "root executable drift")
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "RECLASSIFY"
    assert f"UNBOUND_PATH_DRIFT:{relative}" in decision["reasons"]
    assert f"git.path:{relative}" in decision["changed_identities"]
    assert "DOCS_HISTORY_ONLY_DESCENDANT" not in decision["reasons"]


@pytest.mark.parametrize(
    "relative",
    (
        "scripts/other.py",
        "config/settings.toml",
        "fly.toml",
        "Dockerfile",
        "docs/current-state/ops.md",
    ),
)
def test_mode_only_drift_requires_reclassification_with_path(tmp_path, relative):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    git(repo, "update-index", "--chmod=+x", "--", relative)
    git(repo, "commit", "-m", f"mode drift {relative}")
    assert git(repo, "status", "--short") == ""
    assert git(repo, "ls-files", "--format=%(objectmode)", "--", relative) == "100755"
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "RECLASSIFY"
    assert f"MODE_DRIFT:{relative}:100644->100755" in decision["reasons"]
    assert f"git.path:{relative}" in decision["changed_identities"]
    assert "DOCS_HISTORY_ONLY_DESCENDANT" not in decision["reasons"]


def test_unbound_scripts_and_config_content_drift_reclassifies(tmp_path):
    for relative in ("scripts/other.py", "config/settings.toml"):
        case_root = tmp_path / relative.replace("/", "-").replace(".", "-")
        repo = initialize_repo(case_root)
        baseline = frozen(repo)
        commit_file(repo, relative, "unbound change\n", "unbound")
        current = frozen(repo)

        decision = assess(repo, baseline, current)

        assert decision["decision"] == "RECLASSIFY"
        assert f"UNBOUND_PATH_DRIFT:{relative}" in decision["reasons"]


def test_non_descendant_candidate_requires_reclassification(tmp_path):
    repo = initialize_repo(tmp_path)
    baseline = frozen(repo)
    tree = str(baseline["candidate"]["tree"])
    sibling = git(repo, "commit-tree", tree, "-m", "unrelated root")
    git(repo, "reset", "--hard", sibling)
    current = frozen(repo)

    decision = assess(repo, baseline, current)

    assert decision["decision"] == "RECLASSIFY"
    assert decision["reasons"] == ["CANDIDATE_NOT_DESCENDANT"]


def failure_config(repo: Path) -> dict[str, object]:
    return {
        "candidate": git(repo, "rev-parse", "HEAD"),
        "gate": "focused-validation",
        "classification": "RECOVERING",
        "timestamp": "2026-07-30T12:00:00Z",
        "artifact_pointer": ".local/evidence/focused/stderr.bin",
        "fingerprints": {
            "environment": "A" * 64,
            "runner": "B" * 64,
        },
        "next_action": "repair-runner",
    }


def test_failure_writes_one_compact_receipt_without_full_seal(tmp_path):
    repo = initialize_repo(tmp_path)
    config_path = repo / ".local" / "failure.json"
    output = repo / ".local" / "failure-receipt.json"
    config_path.write_bytes(validation_evidence.canonical_json_bytes(failure_config(repo)))

    receipt = validation_evidence.command_failure(
        Namespace(
            repo_root=str(repo),
            config=str(config_path),
            output=str(output),
        )
    )

    assert receipt["kind"] == "COMPACT_FAILURE"
    assert receipt["root"] == "."
    assert receipt["artifact_pointer"] == ".local/evidence/focused/stderr.bin"
    assert "seal" not in receipt
    assert "index" not in receipt
    assert output.read_bytes() == validation_evidence.canonical_json_bytes(receipt)


def test_atomic_write_preserves_previous_output_on_replace_failure(tmp_path, monkeypatch):
    repo = initialize_repo(tmp_path)
    root = validation_evidence.normalize_repo_root(repo)
    output = repo / ".local" / "receipt.json"
    output.write_bytes(b"previous\n")

    def refuse_replace(_source, _destination):
        raise OSError("replace refused")

    monkeypatch.setattr(validation_evidence.os, "replace", refuse_replace)
    with pytest.raises(OSError, match="replace refused"):
        validation_evidence.atomic_write(output, b"new\n", root=root)

    assert output.read_bytes() == b"previous\n"
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_local_wrapper_exposes_thin_validation_evidence_actions():
    content = LOCAL_WRAPPER.read_text(encoding="utf-8")

    for action in (
        "validation-evidence-freeze",
        "validation-evidence-assess-reuse",
        "validation-evidence-failure",
    ):
        assert f'"{action}"' in content
    function = content.split("function Invoke-ValidationEvidence", 1)[1].split(
        "function Invoke-SelectedLocalAction",
        1,
    )[0]
    assert "ConvertFrom-Json" not in function
    assert "ConvertTo-Json" not in function
    assert "scripts\\validation_evidence.py" in function
    assert "& $PythonPath @arguments" in function
