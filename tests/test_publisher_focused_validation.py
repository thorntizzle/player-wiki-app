from __future__ import annotations

import copy
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "publisher_closeout.py"
SPEC = importlib.util.spec_from_file_location("publisher_closeout_focused", SCRIPT_PATH)
assert SPEC and SPEC.loader
closeout = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = closeout
SPEC.loader.exec_module(closeout)


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "focused-test@example.invalid")
    git(root, "config", "user.name", "Focused Test")
    (root / ".gitignore").write_text(".local/\n", encoding="utf-8")
    (root / ".python-version").write_text(
        platform.python_version() + "\n", encoding="utf-8"
    )
    (root / "requirements-dev.lock").write_bytes(
        b"fixture==1 --hash=sha256:abcd\n"
    )
    (root / "player_wiki").mkdir()
    (root / "player_wiki" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_one.py").write_text(
        "def test_one():\n    assert True\n", encoding="utf-8"
    )
    (root / "docs" / "workflows").mkdir(parents=True)
    (root / "docs" / "workflows" / "program.md").write_text(
        "workflow\n", encoding="utf-8"
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "focused_runner.py").write_bytes(b"fixture-runner")
    (root / "fly.toml").write_text("app = 'fixture'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture")
    return root


def candidate(root: Path) -> dict[str, str]:
    return {
        "commit": git(root, "rev-parse", "HEAD"),
        "tree": git(root, "rev-parse", "HEAD^{tree}"),
    }


def browser_payload(
    root: Path,
    *,
    selected_mode: str = "browser",
    ownership: dict | None = None,
    capabilities: dict | None = None,
) -> dict:
    accepted = candidate(root)
    partitions = {
        "browser": {
            "required": ["surface-navigation"],
            "browser": ["surface-navigation"],
            "independent_get": [],
            "requirements": {"surface-navigation": "navigation"},
        },
        "GET_ONLY": {
            "required": ["http-status"],
            "browser": [],
            "independent_get": ["http-status"],
            "requirements": {"http-status": "independent_get"},
        },
        "split": {
            "required": ["surface-navigation", "http-status"],
            "browser": ["surface-navigation"],
            "independent_get": ["http-status"],
            "requirements": {
                "surface-navigation": "navigation",
                "http-status": "independent_get",
            },
        },
    }
    return {
        "task_id": "publisher-task-001",
        "accepted_candidate": accepted,
        "ownership": ownership
        or {
            "mode": "publisher-attached",
            "attachment_id": "attachment-001",
            "controlled_tab_id": "tab-001",
            "exclusive": True,
        },
        "capabilities": capabilities
        or {
            "navigation": True,
            "evaluation": True,
            "fetch": True,
            "independent_get": True,
            "auth_session": False,
        },
        "required_evidence_mode": selected_mode,
        "selected_evidence_mode": selected_mode,
        "assertions": partitions[selected_mode],
    }


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(closeout.canonical_json_bytes(value))
    return path


def file_identity(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(path.parents[1]).as_posix(),
        "sha256": closeout.sha256_path(path),
    }


def prepare_focused_inputs(
    tmp_path: Path,
    *,
    nodeids: list[str] | None = None,
) -> tuple[Path, dict, Path, Path, Path, Path]:
    root = make_repo(tmp_path)
    accepted = candidate(root)
    evidence = root / ".local" / "focused-inputs"
    evidence.mkdir(parents=True)
    for name in ("envelope.json", "verdict.json", "index.json", "seal.json"):
        (evidence / name).write_text(f"{name}\n", encoding="utf-8")
    validation_module = closeout._validation_evidence_module()

    def identity(relative: str, *, package_count: int | None = None) -> dict:
        path = root / relative
        result = {
            "path": relative,
            "sha256": validation_module.sha256_file(path),
        }
        if package_count is not None:
            result["package_count"] = package_count
        return result

    def tracked_identity(relative: str) -> dict:
        payload = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        return {
            "path": relative,
            "sha256": validation_module.sha256_bytes(payload),
        }

    validation = validation_module.build_frozen_identity(
        root,
        {
            "candidate_commit": accepted["commit"],
            "fly_blobs": [
                {
                    "path": "fly.toml",
                    "blob": git(root, "rev-parse", "HEAD:fly.toml"),
                }
            ],
            "dependencies": identity("requirements-dev.lock", package_count=7),
            "runner": tracked_identity("scripts/focused_runner.py"),
            "envelope": identity(".local/focused-inputs/envelope.json"),
            "suite": {
                "verdict": identity(".local/focused-inputs/verdict.json"),
                "index": identity(".local/focused-inputs/index.json"),
                "seal": identity(".local/focused-inputs/seal.json"),
            },
            "invalidators": ["runtime-tree", "tests-tree", "workflow-tree"],
        },
    )
    validation_path = write_json(evidence / "validation.json", validation)
    browser = closeout.build_browser_capability_receipt(
        root, browser_payload(root, selected_mode="split")
    )
    browser_path = write_json(evidence / "browser.json", browser)
    nodeids = sorted(nodeids or [
        'tests/test_one.py::test_one[selector="a b"]',
        "tests/test_one.py::test_one[query=a,b[c]]",
    ])
    cache_path = write_json(evidence / "nodeids-cache.json", nodeids)
    export_path = write_json(evidence / "nodeids-export.json", nodeids)
    manifest = {
        "schema_version": 1,
        "accepted_candidate": accepted,
        "tests": {
            "nodeids_cache": {
                "path": cache_path.relative_to(root).as_posix(),
                "sha256": closeout.sha256_path(cache_path),
                "nodeid_count": len(nodeids),
            },
            "nodeids_export": {
                "path": export_path.relative_to(root).as_posix(),
                "sha256": closeout.sha256_path(export_path),
                "nodeid_count": len(nodeids),
            },
            "selectors": ["tests/test_one.py::test_one"],
            "expanded_nodeids": nodeids,
            "expanded_nodeid_count": len(nodeids),
        },
        "live_routes": {"source": {}, "assertions": []},
    }
    manifest_path = write_json(evidence / "manifest.json", manifest)
    requirements = {
        "required_evidence_mode": "split",
        "assertions": copy.deepcopy(browser["assertions"]),
    }
    config = {
        "schema_version": 1,
        "accepted_candidate": accepted,
        "test_selectors": ["tests/test_one.py::test_one"],
        "live_routes": [],
        "browser": {
            "capability_receipt": browser_path.relative_to(root).as_posix(),
            "task_id": browser["task_id"],
        },
        "browser_requirements": requirements,
        "focused_runner": "scripts/focused_runner.py",
    }
    config_path = write_json(evidence / "config.json", config)
    browser_record = {
        "mode": "capability-receipt",
        "task_id": browser["task_id"],
        "selected_evidence_mode": browser["selected_evidence_mode"],
        "receipt": {
            "path": browser_path.relative_to(root).as_posix(),
            "sha256": closeout.sha256_path(browser_path),
            "bytes": browser_path.stat().st_size,
            "receipt_sha256": browser["receipt_sha256"],
        },
    }
    plan = closeout.seal_plan(
        {
            "schema_version": 1,
            "kind": "publisher-closeout-plan",
            "accepted_candidate": accepted,
            "browser": browser_record,
            "browser_requirements": requirements,
            "focused_runner": closeout._candidate_tracked_file_identity(
                root,
                accepted,
                "scripts/focused_runner.py",
                label="focused runner",
            ),
            "inputs": {
                "config": {
                    "path": config_path.relative_to(root).as_posix(),
                    "sha256": closeout.sha256_path(config_path),
                    "bytes": config_path.stat().st_size,
                },
                "nodeids_cache": {
                    **closeout._input_identity(root, cache_path),
                    "nodeid_count": len(nodeids),
                    "ordered_nodeids_sha256": closeout._ordered_nodeids_sha256(
                        nodeids
                    ),
                },
                "nodeids_export": {
                    **closeout._input_identity(root, export_path),
                    "nodeid_count": len(nodeids),
                    "ordered_nodeids_sha256": closeout._ordered_nodeids_sha256(
                        nodeids
                    ),
                },
                "manifest": {
                    "path": manifest_path.relative_to(root).as_posix(),
                    "sha256": closeout.sha256_path(manifest_path),
                    "bytes": manifest_path.stat().st_size,
                }
            },
        }
    )
    plan_path = write_json(evidence / "plan.json", plan)
    environment_manifest = {
        "ok": True,
        "python_version": validation["interpreter"]["version"],
        "requirements_lock_sha256": validation["dependencies"]["sha256"],
        "locked_requirements_checked": 7,
        "dependency_check": "fixture-ok",
        "errors": [],
        "python_executable": sys.executable,
        "expected_python_version": validation["interpreter"]["version"],
        "requirements_lock": str(root / "requirements-dev.lock"),
    }
    children = evidence / "children"
    children.mkdir()

    def child_record(
        label: str,
        arguments: list[str],
        stdout: bytes,
        *,
        extra: dict | None = None,
    ) -> dict:
        stdout_path = children / f"{label}.stdout.bin"
        stderr_path = children / f"{label}.stderr.bin"
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(b"")
        return {
            "label": label,
            "arguments": arguments,
            "exit_code": 0,
            "stdout": {
                "path": stdout_path.relative_to(evidence).as_posix(),
                "sha256": closeout.sha256_path(stdout_path),
                "bytes": stdout_path.stat().st_size,
            },
            "stderr": {
                "path": stderr_path.relative_to(evidence).as_posix(),
                "sha256": closeout.sha256_path(stderr_path),
                "bytes": 0,
            },
            **(extra or {}),
        }

    collect_arguments = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "tests/test_one.py::test_one",
    ]
    collection_extra = {
        "nodeids": nodeids,
        "nodeid_count": len(nodeids),
        "ordered_nodeids_sha256": closeout._ordered_nodeids_sha256(nodeids),
    }
    collection_stdout = ("\n".join(nodeids) + "\n").encode("utf-8")
    first_collection = child_record(
        "pytest-collect-1",
        collect_arguments,
        collection_stdout,
        extra=collection_extra,
    )
    second_collection = child_record(
        "pytest-collect-2",
        collect_arguments,
        collection_stdout,
        extra=collection_extra,
    )
    environment_record = child_record(
        "validation-environment",
        [
            sys.executable,
            "-B",
            str(root / "scripts" / "verify_validation_environment.py"),
            "--project-root",
            str(root),
        ],
        closeout.canonical_json_bytes(environment_manifest),
        extra={"manifest": environment_manifest},
    )
    manifest_arguments = [
        sys.executable,
        "-B",
        str(root / "scripts" / "generate_publisher_manifest.py"),
        "--accepted-commit",
        accepted["commit"],
        "--nodeids-cache",
        str(cache_path),
        "--nodeids-export",
        str(export_path),
        "--output",
        str(manifest_path),
        "--selector",
        "tests/test_one.py::test_one",
    ]
    manifest_record = child_record(
        "publisher-manifest", manifest_arguments, b'{"status":"ok"}\n'
    )
    preflight = closeout.seal_publisher_receipt(
        {
            "schema": closeout.PUBLISHER_EVIDENCE_SCHEMA,
            "schema_version": 1,
            "kind": "publisher-preflight-receipt",
            "status": "PASS",
            "accepted_candidate": accepted,
            "python_path": sys.executable,
            "environment": environment_record,
            "collections": {
                "first": first_collection,
                "second": second_collection,
                "canonical_count": len(nodeids),
                "canonical_sha256": closeout.sha256_path(cache_path),
            },
            "manifest": manifest_record,
            "browser": browser_record,
            "browser_requirements": requirements,
            "focused_runner": plan["focused_runner"],
            "disposal_plan": {
                "path": plan_path.name,
                "sha256": closeout.sha256_path(plan_path),
                "bytes": plan_path.stat().st_size,
                "plan_sha256": plan["plan_sha256"],
            },
        }
    )
    preflight_path = write_json(evidence / "preflight.json", preflight)
    proof = closeout.focused_proof(
        project_root=root,
        python_path=Path(sys.executable),
        preflight_receipt_path=preflight_path,
        plan_path=plan_path,
        validation_identity_path=validation_path,
        output=root / ".local" / "proof",
    )
    proof_path = root / ".local" / "proof" / "focused-proof.json"
    return root, proof, proof_path, preflight_path, plan_path, validation_path


def install_validation_lock(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = Path(
        git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ) / "campaign-player-wiki-complete-validation.lock"
    guard = "0123456789abcdef0123456789abcdef"
    path.write_text(guard, encoding="utf-8")
    monkeypatch.setenv(closeout.VALIDATION_LOCK_PATH_ENV, str(path))
    monkeypatch.setenv(closeout.VALIDATION_LOCK_TOKEN_ENV, guard)
    return path


def observer_receipt(proof: dict, *, exit_code: int = 0) -> dict:
    count = len(proof["tests"]["expanded_nodeids"])
    failed = 0 if exit_code == 0 else 1
    return closeout.seal_publisher_receipt(
        {
            "schema": closeout.PUBLISHER_EVIDENCE_SCHEMA,
            "schema_version": 1,
            "kind": "publisher-focused-observer",
            "proof_receipt_sha256": proof["receipt_sha256"],
            "arguments": closeout._focused_arguments(proof)[4:],
            "exit_code": exit_code,
            "collected_nodeids": proof["tests"]["expanded_nodeids"],
            "counts": {
                "collected": count,
                "passed": count if exit_code == 0 else count - 1,
                "failed": failed,
                "errors": 0,
                "skipped": 0,
                "xpassed": 0,
                "xfailed": 0,
                "not_run": 0,
                "internal_errors": 0,
                "collection_errors": 0,
                "unexpected_errors": 0,
                "browser_errors": 0,
                "server_errors": 0,
            },
            "error_ledger": {
                "status": "GREEN" if exit_code == 0 else "RED",
                "entries": [] if exit_code == 0 else [proof["tests"]["expanded_nodeids"][0]],
            },
            "browser_ledger": {"status": "GREEN", "entries": []},
            "server_ledger": {"status": "GREEN", "entries": []},
        }
    )


class FakeProcess:
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        self.waited = False
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None) -> int:
        self.waited = True
        return self.exit_code

    def poll(self) -> int | None:
        return self.exit_code if self.waited else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class FaultInjectedReapProcess:
    def __init__(
        self,
        exit_code: int,
        wait_plan: list[BaseException | int],
        *,
        kill_error: BaseException | None = None,
    ):
        self.exit_code = exit_code
        self.wait_plan = list(wait_plan)
        self.kill_error = kill_error
        self.wait_timeouts: list[float | None] = []
        self.terminated = False
        self.kill_attempts = 0
        self.killed = False
        self.reaped = False

    def wait(self, timeout=None) -> int:
        self.wait_timeouts.append(timeout)
        effect: BaseException | int
        if self.wait_plan:
            effect = self.wait_plan.pop(0)
        else:
            effect = self.exit_code
        if isinstance(effect, BaseException):
            raise effect
        self.reaped = True
        self.exit_code = int(effect)
        return self.exit_code

    def poll(self) -> int | None:
        return self.exit_code if self.reaped else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.kill_attempts += 1
        if self.kill_error is not None:
            raise self.kill_error
        self.killed = True


def fake_launcher_factory(
    proof: dict,
    calls: list[list[str]],
    *,
    exit_code: int = 0,
):
    def launch(arguments, *, cwd, env, stdout, stderr):
        calls.append(list(arguments))
        stdout.write(b"focused stdout\n")
        # Intentionally preserve an empty raw stderr file.
        observer = observer_receipt(proof, exit_code=exit_code)
        write_json(Path(env[closeout.PUBLISHER_FOCUSED_OBSERVER_ENV]), observer)
        return FakeProcess(exit_code)

    return launch


def test_browser_attached_receipt_is_sealed_and_task_candidate_bound(tmp_path):
    root = make_repo(tmp_path)
    receipt = closeout.build_browser_capability_receipt(root, browser_payload(root))
    assert receipt["receipt_sha256"]
    assert receipt["ownership"]["exclusive"] is True
    assert closeout.verify_browser_capability_receipt(
        root,
        receipt,
        expected_task="publisher-task-001",
        expected_candidate=candidate(root),
    ) == receipt
    with pytest.raises(closeout.CloseoutError, match="task does not match"):
        closeout.verify_browser_capability_receipt(
            root, receipt, expected_task="other-task"
        )
    wrong_candidate = dict(candidate(root))
    wrong_candidate["commit"] = "f" * 40
    with pytest.raises(closeout.CloseoutError, match="candidate does not match"):
        closeout.verify_browser_capability_receipt(
            root, receipt, expected_candidate=wrong_candidate
        )


@pytest.mark.parametrize("mode", ["GET_ONLY", "split"])
def test_browser_explicit_get_only_and_split_modes_are_supported(tmp_path, mode):
    root = make_repo(tmp_path)
    receipt = closeout.build_browser_capability_receipt(
        root, browser_payload(root, selected_mode=mode)
    )
    assert receipt["selected_evidence_mode"] == mode


def test_browser_rejects_silent_downgrade_capability_gap_and_partition_errors(tmp_path):
    root = make_repo(tmp_path)
    downgraded = browser_payload(root)
    downgraded["selected_evidence_mode"] = "GET_ONLY"
    with pytest.raises(closeout.CloseoutError, match="silently downgraded"):
        closeout.build_browser_capability_receipt(root, downgraded)
    unsupported = browser_payload(root)
    unsupported["capabilities"]["navigation"] = False
    with pytest.raises(closeout.CloseoutError, match="navigation capability"):
        closeout.build_browser_capability_receipt(root, unsupported)
    overlap = browser_payload(root, selected_mode="split")
    overlap["assertions"]["independent_get"].append("surface-navigation")
    with pytest.raises(closeout.CloseoutError, match="overlap"):
        closeout.build_browser_capability_receipt(root, overlap)


def test_browser_parent_fallback_requires_contained_script_and_independent_auditor(tmp_path):
    root = make_repo(tmp_path)
    script = root / ".local" / "browser-script.json"
    script.parent.mkdir()
    script.write_text("{}\n", encoding="utf-8")
    ownership = {
        "mode": "parent-fallback",
        "operator_task_id": "orchestrator-task-001",
        "script": ".local/browser-script.json",
        "auditor": {
            "role": "Verifier",
            "task_id": "verifier-task-001",
            "independent": True,
        },
    }
    receipt = closeout.build_browser_capability_receipt(
        root, browser_payload(root, ownership=ownership)
    )
    assert receipt["ownership"]["script"]["sha256"] == closeout.sha256_path(script)
    absolute = browser_payload(root, ownership={**ownership, "script": str(script)})
    with pytest.raises(closeout.CloseoutError, match="repository-relative"):
        closeout.build_browser_capability_receipt(root, absolute)
    dependent = copy.deepcopy(ownership)
    dependent["auditor"]["independent"] = False
    with pytest.raises(closeout.CloseoutError, match="independent auditor"):
        closeout.build_browser_capability_receipt(
            root, browser_payload(root, ownership=dependent)
        )


def test_browser_receipt_refuses_private_fields_and_reparse_script(tmp_path):
    root = make_repo(tmp_path)
    private = browser_payload(root)
    private["secret_token"] = "forbidden"
    with pytest.raises(closeout.CloseoutError, match="private field"):
        closeout.build_browser_capability_receipt(root, private)
    target = root / ".local" / "target.json"
    target.parent.mkdir()
    target.write_text("{}\n", encoding="utf-8")
    link = root / ".local" / "browser-link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    ownership = {
        "mode": "parent-fallback",
        "operator_task_id": "orchestrator-task-001",
        "script": ".local/browser-link.json",
        "auditor": {
            "role": "Verifier",
            "task_id": "verifier-task-001",
            "independent": True,
        },
    }
    with pytest.raises(closeout.CloseoutError, match="reparse"):
        closeout.build_browser_capability_receipt(
            root, browser_payload(root, ownership=ownership)
        )


def test_focused_proof_is_deterministic_and_preserves_ordered_parameter_ids(tmp_path):
    root, first, _, preflight, plan, validation = prepare_focused_inputs(tmp_path)
    second = closeout.focused_proof(
        project_root=root,
        python_path=Path(sys.executable),
        preflight_receipt_path=preflight,
        plan_path=plan,
        validation_identity_path=validation,
        output=root / ".local" / "proof-two",
    )
    assert first == second
    assert first["tests"]["expanded_nodeids"] == sorted(
        [
            'tests/test_one.py::test_one[selector="a b"]',
            "tests/test_one.py::test_one[query=a,b[c]]",
        ]
    )


@pytest.mark.parametrize("target", ["preflight", "plan", "validation"])
def test_focused_proof_rejects_wrong_preflight_plan_or_validation_identity(
    tmp_path, target
):
    root, _, _, preflight, plan, validation = prepare_focused_inputs(tmp_path)
    path = {"preflight": preflight, "plan": plan, "validation": validation}[target]
    value = json.loads(path.read_text(encoding="utf-8"))
    if target == "plan":
        value["plan_sha256"] = "0" * 64
    else:
        value["receipt_sha256"] = "0" * 64
    write_json(path, value)
    with pytest.raises(closeout.CloseoutError):
        closeout.focused_proof(
            project_root=root,
            python_path=Path(sys.executable),
            preflight_receipt_path=preflight,
            plan_path=plan,
            validation_identity_path=validation,
            output=root / ".local" / "proof-invalid",
        )


def test_focused_run_preserves_exact_argv_zero_stderr_and_passes_finalize(
    tmp_path, monkeypatch
):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        closeout, "_launch_focused_pytest", fake_launcher_factory(proof, calls)
    )
    run_root = root / ".local" / "run"
    code, result = closeout.focused_run(
        project_root=root, proof_path=proof_path, output=run_root
    )
    assert code == 0
    assert result["invocation_count"] == 1
    assert calls == [closeout._focused_arguments(proof)]
    assert calls[0][-2:] == proof["tests"]["expanded_nodeids"]
    assert (run_root / "focused.stderr.bin").read_bytes() == b""
    finalize_code, verdict = closeout.focused_finalize(
        project_root=root,
        proof_path=proof_path,
        result_path=run_root / "focused-result.json",
        output=root / ".local" / "final",
    )
    assert finalize_code == 0
    assert verdict["status"] == "FOCUSED_GATE_PASS"


def test_focused_run_refuses_drifted_manifest_before_sentinel_or_pytest(
    tmp_path, monkeypatch
):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    manifest = root / proof["inputs"]["manifest"]["path"]
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    monkeypatch.setattr(
        closeout,
        "_launch_focused_pytest",
        lambda *_a, **_k: pytest.fail("pytest must not start"),
    )
    run_root = root / ".local" / "manifest-drift"
    with pytest.raises(closeout.CloseoutError, match="input drifted"):
        closeout.focused_run(
            project_root=root, proof_path=proof_path, output=run_root
        )
    assert not (run_root / "focused-invocation.sentinel").exists()


def test_focused_run_refuses_resealed_nodeid_drift_before_sentinel(
    tmp_path, monkeypatch
):
    root, proof, _, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    core = {key: value for key, value in proof.items() if key != "receipt_sha256"}
    core["tests"] = copy.deepcopy(core["tests"])
    core["tests"]["expanded_nodeids"] = ["tests/test_one.py::test_other"]
    core["tests"]["expanded_nodeid_count"] = 1
    core["tests"]["ordered_nodeids_sha256"] = closeout._ordered_nodeids_sha256(
        core["tests"]["expanded_nodeids"]
    )
    tampered_path = write_json(
        root / ".local" / "tampered-proof.json",
        closeout.seal_publisher_receipt(core),
    )
    run_root = root / ".local" / "nodeid-drift"
    with pytest.raises(closeout.CloseoutError, match="semantic bindings"):
        closeout.focused_run(
            project_root=root, proof_path=tampered_path, output=run_root
        )
    assert not (run_root / "focused-invocation.sentinel").exists()


def test_resealed_reordered_collections_are_rejected_before_sentinel_or_popen(
    tmp_path, monkeypatch
):
    root, proof, _, preflight_path, plan_path, validation_path = (
        prepare_focused_inputs(tmp_path)
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    core = {
        key: copy.deepcopy(value)
        for key, value in preflight.items()
        if key != "receipt_sha256"
    }
    reversed_nodeids = list(reversed(proof["tests"]["expanded_nodeids"]))
    reversed_stdout = ("\n".join(reversed_nodeids) + "\n").encode("utf-8")
    for name in ("first", "second"):
        record = core["collections"][name]
        record["nodeids"] = reversed_nodeids
        record["nodeid_count"] = len(reversed_nodeids)
        record["ordered_nodeids_sha256"] = closeout._ordered_nodeids_sha256(
            reversed_nodeids
        )
        stdout_path = preflight_path.parent / record["stdout"]["path"]
        stdout_path.write_bytes(reversed_stdout)
        record["stdout"]["sha256"] = closeout.sha256_path(stdout_path)
        record["stdout"]["bytes"] = stdout_path.stat().st_size
    write_json(preflight_path, closeout.seal_publisher_receipt(core))

    with pytest.raises(closeout.CloseoutError, match="collection contract"):
        closeout.focused_proof(
            project_root=root,
            python_path=Path(sys.executable),
            preflight_receipt_path=preflight_path,
            plan_path=plan_path,
            validation_identity_path=validation_path,
            output=root / ".local" / "reordered-proof",
        )

    proof_core = {
        key: copy.deepcopy(value)
        for key, value in proof.items()
        if key != "receipt_sha256"
    }
    proof_core["inputs"]["preflight"] = closeout._input_identity(
        root, preflight_path
    )
    tampered_proof_path = write_json(
        root / ".local" / "reordered-proof.json",
        closeout.seal_publisher_receipt(proof_core),
    )
    launch_calls: list[list[str]] = []
    monkeypatch.setattr(
        closeout,
        "_launch_focused_pytest",
        lambda arguments, **_kwargs: launch_calls.append(list(arguments)),
    )
    run_root = root / ".local" / "reordered-run"
    with pytest.raises(closeout.CloseoutError, match="semantic bindings"):
        closeout.focused_run(
            project_root=root,
            proof_path=tampered_proof_path,
            output=run_root,
        )
    assert launch_calls == []
    assert not (run_root / "focused-invocation.sentinel").exists()


def test_focused_run_missing_lock_is_preinvocation_recovering_with_zero_count(
    tmp_path, monkeypatch
):
    root, _, proof_path, *_ = prepare_focused_inputs(tmp_path)
    monkeypatch.delenv(closeout.VALIDATION_LOCK_PATH_ENV, raising=False)
    monkeypatch.delenv(closeout.VALIDATION_LOCK_TOKEN_ENV, raising=False)
    monkeypatch.setattr(
        closeout,
        "_launch_focused_pytest",
        lambda *_a, **_k: pytest.fail("pytest must not start"),
    )
    code, result = closeout.focused_run(
        project_root=root,
        proof_path=proof_path,
        output=root / ".local" / "preinvocation-failure",
    )
    assert code == 1
    assert result["invocation_count"] == 0
    assert result["postflight"] == {"pytest_not_started": True}
    assert not (
        root / ".local" / "preinvocation-failure" / "focused-invocation.sentinel"
    ).exists()


def test_inherited_validation_lock_refuses_foreign_path_and_guard(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    lock = install_validation_lock(root, monkeypatch)
    assert closeout.verify_inherited_validation_lock(root)["held"] is True
    monkeypatch.setenv(closeout.VALIDATION_LOCK_PATH_ENV, str(root / ".git" / "other.lock"))
    with pytest.raises(closeout.CloseoutError, match="path does not match"):
        closeout.verify_inherited_validation_lock(root)
    monkeypatch.setenv(closeout.VALIDATION_LOCK_PATH_ENV, str(lock))
    monkeypatch.setenv(closeout.VALIDATION_LOCK_TOKEN_ENV, "f" * 32)
    with pytest.raises(closeout.CloseoutError, match="guard does not match"):
        closeout.verify_inherited_validation_lock(root)


def test_focused_sentinel_prevents_a_second_attempt(tmp_path, monkeypatch):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    monkeypatch.setattr(
        closeout, "_launch_focused_pytest", fake_launcher_factory(proof, [])
    )
    run_root = root / ".local" / "one-shot"
    assert closeout.focused_run(
        project_root=root, proof_path=proof_path, output=run_root
    )[0] == 0
    with pytest.raises(closeout.CloseoutError, match="retry is forbidden"):
        closeout.focused_run(
            project_root=root, proof_path=proof_path, output=run_root
        )


def test_finalize_can_reclassify_retained_child_without_rerun(tmp_path, monkeypatch):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        closeout, "_launch_focused_pytest", fake_launcher_factory(proof, calls)
    )
    run_root = root / ".local" / "retained"
    closeout.focused_run(project_root=root, proof_path=proof_path, output=run_root)
    observer_path = run_root / "focused-observer.json"
    original = observer_path.read_bytes()
    observer_path.write_bytes(b"{}\n")
    code, verdict = closeout.focused_finalize(
        project_root=root,
        proof_path=proof_path,
        result_path=run_root / "focused-result.json",
        output=root / ".local" / "final-retry",
    )
    assert code == 1
    assert verdict["status"] == "RECOVERING"
    observer_path.write_bytes(original)
    code, verdict = closeout.focused_finalize(
        project_root=root,
        proof_path=proof_path,
        result_path=run_root / "focused-result.json",
        output=root / ".local" / "final-retry",
    )
    assert code == 0
    assert verdict["status"] == "FOCUSED_GATE_PASS"
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["nonzero", "postflight"])
def test_finalize_fails_closed_on_child_or_postflight_fault(
    tmp_path, monkeypatch, fault
):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    monkeypatch.setattr(
        closeout,
        "_launch_focused_pytest",
        fake_launcher_factory(proof, [], exit_code=1 if fault == "nonzero" else 0),
    )
    if fault == "postflight":
        monkeypatch.setattr(
            closeout,
            "_focused_postflight",
            lambda *_a: {
                "lock_held": True,
                "candidate_unchanged": True,
                "worktree_clean": True,
                "sentinel_unchanged": False,
            },
        )
    run_root = root / ".local" / fault
    closeout.focused_run(project_root=root, proof_path=proof_path, output=run_root)
    code, verdict = closeout.focused_finalize(
        project_root=root,
        proof_path=proof_path,
        result_path=run_root / "focused-result.json",
        output=root / ".local" / f"{fault}-final",
    )
    assert code == 1
    assert verdict["status"] == "RECOVERING"


@pytest.mark.parametrize("fault", ["exit_code", "counts", "error_ledger"])
def test_observer_verification_rejects_malformed_or_non_green_evidence(
    tmp_path, fault
):
    root, proof, *_ = prepare_focused_inputs(tmp_path)
    observer = observer_receipt(proof)
    core = {
        key: copy.deepcopy(value)
        for key, value in observer.items()
        if key != "receipt_sha256"
    }
    if fault == "exit_code":
        core["exit_code"] = 1
    elif fault == "counts":
        core["counts"].pop("skipped")
    else:
        core["error_ledger"] = {
            "status": "RED",
            "entries": [proof["tests"]["expanded_nodeids"][0]],
        }
    path = write_json(
        root / ".local" / f"observer-{fault}.json",
        closeout.seal_publisher_receipt(core),
    )
    binding = {
        "path": path.relative_to(root).as_posix(),
        "sha256": closeout.sha256_path(path),
        "bytes": path.stat().st_size,
    }
    with pytest.raises(closeout.CloseoutError, match="exact gate"):
        closeout._verify_focused_observer(root, binding, proof)


def test_pytest_plugin_is_inert_without_explicit_enablement(monkeypatch):
    monkeypatch.delenv(closeout.PUBLISHER_FOCUSED_PLUGIN_ENV, raising=False)
    registrations = []
    config = SimpleNamespace(
        pluginmanager=SimpleNamespace(
            register=lambda *args: registrations.append(args)
        ),
        invocation_params=SimpleNamespace(args=("-q",)),
    )
    closeout.pytest_configure(config)
    assert registrations == []


def test_pytest_plugin_registers_only_with_complete_explicit_environment(
    tmp_path, monkeypatch
):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv(closeout.PUBLISHER_FOCUSED_PLUGIN_ENV, "1")
    monkeypatch.setenv(
        closeout.PUBLISHER_FOCUSED_OBSERVER_ENV,
        str(root / ".local" / "observer.json"),
    )
    monkeypatch.setenv(
        closeout.PUBLISHER_FOCUSED_PROOF_ENV, proof["receipt_sha256"]
    )
    monkeypatch.setenv(
        closeout.PUBLISHER_FOCUSED_PROOF_PATH_ENV, str(proof_path)
    )
    registrations = []
    arguments = closeout._focused_arguments(proof)[4:]
    config = SimpleNamespace(
        pluginmanager=SimpleNamespace(
            register=lambda *args: registrations.append(args)
        ),
        invocation_params=SimpleNamespace(args=tuple(arguments)),
    )
    closeout.pytest_configure(config)
    assert len(registrations) == 1
    plugin, name = registrations[0]
    assert name == "publisher-focused-observer"
    assert plugin.arguments == arguments
    mismatch = SimpleNamespace(
        pluginmanager=config.pluginmanager,
        invocation_params=SimpleNamespace(args=("-q",)),
    )
    with pytest.raises(closeout.CloseoutError, match="sealed proof"):
        closeout.pytest_configure(mismatch)


@pytest.mark.parametrize(
    "target",
    [
        "resealed-preflight",
        "collection",
        "config",
        "cache",
        "export",
        "manifest",
        "runner",
        "dependency",
    ],
)
def test_focused_proof_rejects_every_drifted_or_resealed_input(tmp_path, target):
    root, proof, _, preflight_path, plan_path, validation_path = (
        prepare_focused_inputs(tmp_path)
    )
    if target in {"resealed-preflight", "collection"}:
        value = json.loads(preflight_path.read_text(encoding="utf-8"))
        core = {key: copy.deepcopy(item) for key, item in value.items() if key != "receipt_sha256"}
        if target == "resealed-preflight":
            core["collections"]["canonical_count"] += 1
        else:
            core["collections"]["first"]["nodeids"] = [
                "tests/test_one.py::test_other"
            ]
            core["collections"]["first"]["nodeid_count"] = 1
            core["collections"]["first"][
                "ordered_nodeids_sha256"
            ] = closeout._ordered_nodeids_sha256(
                core["collections"]["first"]["nodeids"]
            )
        write_json(preflight_path, closeout.seal_publisher_receipt(core))
    elif target in {"config", "cache", "export", "manifest"}:
        path = root / proof["inputs"][
            {
                "config": "config",
                "cache": "nodeids_cache",
                "export": "nodeids_export",
                "manifest": "manifest",
            }[target]
        ]["path"]
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "runner":
        (root / proof["runner"]["path"]).write_bytes(b"runner drift")
    else:
        dependency = root / proof["environment"]["dependencies_path"]
        dependency.write_bytes(dependency.read_bytes() + b"# drift\n")
    with pytest.raises(closeout.CloseoutError):
        closeout.focused_proof(
            project_root=root,
            python_path=Path(sys.executable),
            preflight_receipt_path=preflight_path,
            plan_path=plan_path,
            validation_identity_path=validation_path,
            output=root / ".local" / f"strict-{target}",
        )


def test_focused_proof_recomputes_candidate_runner_after_resealing_plan(tmp_path):
    root, _, _, preflight_path, plan_path, validation_path = prepare_focused_inputs(
        tmp_path
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_core = {key: copy.deepcopy(value) for key, value in plan.items() if key != "plan_sha256"}
    plan_core["focused_runner"]["blob"] = "f" * 40
    resealed_plan = closeout.seal_plan(plan_core)
    write_json(plan_path, resealed_plan)
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight_core = {
        key: copy.deepcopy(value)
        for key, value in preflight.items()
        if key != "receipt_sha256"
    }
    preflight_core["focused_runner"] = resealed_plan["focused_runner"]
    preflight_core["disposal_plan"].update(
        {
            "sha256": closeout.sha256_path(plan_path),
            "bytes": plan_path.stat().st_size,
            "plan_sha256": resealed_plan["plan_sha256"],
        }
    )
    write_json(
        preflight_path, closeout.seal_publisher_receipt(preflight_core)
    )
    with pytest.raises(closeout.CloseoutError, match="runner"):
        closeout.focused_proof(
            project_root=root,
            python_path=Path(sys.executable),
            preflight_receipt_path=preflight_path,
            plan_path=plan_path,
            validation_identity_path=validation_path,
            output=root / ".local" / "runner-resealed",
        )


def test_browser_receipt_joint_get_only_reseal_cannot_shrink_formal_requirements(
    tmp_path,
):
    root, proof, _, preflight_path, plan_path, validation_path = (
        prepare_focused_inputs(tmp_path)
    )
    browser_path = root / proof["inputs"]["browser_capability"]["path"]
    get_only = closeout.build_browser_capability_receipt(
        root, browser_payload(root, selected_mode="GET_ONLY")
    )
    write_json(browser_path, get_only)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_core = {key: copy.deepcopy(value) for key, value in plan.items() if key != "plan_sha256"}
    plan_core["browser"]["selected_evidence_mode"] = "GET_ONLY"
    plan_core["browser"]["receipt"].update(
        {
            "sha256": closeout.sha256_path(browser_path),
            "bytes": browser_path.stat().st_size,
            "receipt_sha256": get_only["receipt_sha256"],
        }
    )
    resealed_plan = closeout.seal_plan(plan_core)
    write_json(plan_path, resealed_plan)
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight_core = {
        key: copy.deepcopy(value)
        for key, value in preflight.items()
        if key != "receipt_sha256"
    }
    preflight_core["browser"] = copy.deepcopy(resealed_plan["browser"])
    preflight_core["disposal_plan"].update(
        {
            "sha256": closeout.sha256_path(plan_path),
            "bytes": plan_path.stat().st_size,
            "plan_sha256": resealed_plan["plan_sha256"],
        }
    )
    write_json(
        preflight_path, closeout.seal_publisher_receipt(preflight_core)
    )
    with pytest.raises(closeout.CloseoutError, match="requirements"):
        closeout.focused_proof(
            project_root=root,
            python_path=Path(sys.executable),
            preflight_receipt_path=preflight_path,
            plan_path=plan_path,
            validation_identity_path=validation_path,
            output=root / ".local" / "browser-shrink",
        )


@pytest.mark.parametrize(
    "boundary",
    ["started", "wait", "flush", "child-extraction", "postflight"],
)
def test_post_popen_faults_always_reap_and_retain_one_typed_outcome(
    tmp_path, monkeypatch, boundary
):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    processes: list[FakeProcess] = []

    def launch(arguments, *, cwd, env, stdout, stderr):
        process = FakeProcess(0)
        processes.append(process)
        stdout.write(b"retained output")
        write_json(
            Path(env[closeout.PUBLISHER_FOCUSED_OBSERVER_ENV]),
            observer_receipt(proof),
        )
        return process

    monkeypatch.setattr(closeout, "_launch_focused_pytest", launch)
    fault = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(boundary))
    monkeypatch.setattr(
        closeout,
        {
            "started": "_focused_write_started",
            "wait": "_focused_wait_child",
            "flush": "_focused_flush_streams",
            "child-extraction": "_focused_build_child",
            "postflight": "_focused_postflight",
        }[boundary],
        fault,
    )
    run_root = root / ".local" / f"boundary-{boundary}"
    code, result = closeout.focused_run(
        project_root=root, proof_path=proof_path, output=run_root
    )
    assert code == 1
    assert result["status"] == "RECOVERING"
    assert result["invocation_count"] == 1
    assert len(processes) == 1
    assert processes[0].waited is True
    assert processes[0].poll() is not None
    assert result["postflight"]["process_reaped"] is True
    assert result["postflight"]["child_outcome_retained"] is True
    assert (run_root / "focused-child-outcome.json").is_file()
    assert (run_root / "focused-result.json").is_file()


@pytest.mark.parametrize(
    ("scenario", "wait_plan", "kill_error", "expected_timeouts"),
    [
        (
            "post-kill-timeout",
            [
                subprocess.TimeoutExpired("focused", 5),
                subprocess.TimeoutExpired("focused", 5),
                23,
            ],
            None,
            [5, 5, None],
        ),
        (
            "post-kill-transient-error",
            [
                subprocess.TimeoutExpired("focused", 5),
                RuntimeError("transient post-kill wait failure"),
                23,
            ],
            None,
            [5, 5, None],
        ),
        (
            "kill-error-natural-exit",
            [subprocess.TimeoutExpired("focused", 5), 23],
            RuntimeError("kill request failed"),
            [5, None],
        ),
    ],
)
def test_reap_faults_retain_child_result_and_outcome_under_lock(
    tmp_path,
    monkeypatch,
    scenario,
    wait_plan,
    kill_error,
    expected_timeouts,
):
    root, proof, proof_path, *_ = prepare_focused_inputs(tmp_path)
    install_validation_lock(root, monkeypatch)
    processes: list[FaultInjectedReapProcess] = []

    def launch(arguments, *, cwd, env, stdout, stderr):
        process = FaultInjectedReapProcess(
            23, list(wait_plan), kill_error=kill_error
        )
        processes.append(process)
        stdout.write(b"fault-injected retained output")
        write_json(
            Path(env[closeout.PUBLISHER_FOCUSED_OBSERVER_ENV]),
            observer_receipt(proof, exit_code=1),
        )
        return process

    def fail_initial_wait(_process):
        raise RuntimeError("injected controller wait fault")

    monkeypatch.setattr(closeout, "_launch_focused_pytest", launch)
    monkeypatch.setattr(closeout, "_focused_wait_child", fail_initial_wait)
    run_root = root / ".local" / f"reap-{scenario}"
    code, result = closeout.focused_run(
        project_root=root,
        proof_path=proof_path,
        output=run_root,
    )

    assert code == 1
    assert result["status"] == "RECOVERING"
    assert result["invocation_count"] == 1
    assert len(processes) == 1
    process = processes[0]
    assert process.terminated is True
    assert process.kill_attempts == 1
    assert process.reaped is True
    assert process.poll() == 23
    assert process.wait_timeouts == expected_timeouts
    assert result["child"]["exit_code"] == 23
    assert result["child"]["termination"] == {
        "terminate_requested": True,
        "kill_requested": True,
        "wait_completed": True,
    }
    assert result["postflight"]["process_reaped"] is True
    assert result["postflight"]["child_result_retained"] is True
    assert result["postflight"]["child_outcome_retained"] is True
    verified_result = closeout.verify_focused_result(result)
    outcome = closeout.verify_publisher_receipt(
        json.loads(
            (run_root / "focused-child-outcome.json").read_text(
                encoding="utf-8"
            )
        ),
        expected_schema=closeout.PUBLISHER_EVIDENCE_SCHEMA,
        expected_kind="publisher-focused-child-outcome",
    )
    assert verified_result["child"] == outcome["child"]
    assert result["child_outcome"]["receipt_sha256"] == outcome["receipt_sha256"]
    assert (run_root / "focused-result.json").is_file()


@pytest.mark.parametrize(
    "fault",
    [
        "xpassed",
        "xfailed",
        "not_run",
        "internal_errors",
        "collection_errors",
        "unexpected_errors",
        "browser_errors",
        "server_errors",
    ],
)
def test_observer_fails_closed_for_every_non_green_structured_count(
    tmp_path, fault
):
    root, proof, *_ = prepare_focused_inputs(tmp_path)
    observer = observer_receipt(proof)
    core = {
        key: copy.deepcopy(value)
        for key, value in observer.items()
        if key != "receipt_sha256"
    }
    core["counts"][fault] = 1
    if fault == "browser_errors":
        core["browser_ledger"] = {
            "status": "RED",
            "entries": [{"code": "BROWSER", "message": "structured"}],
        }
    elif fault == "server_errors":
        core["server_ledger"] = {
            "status": "RED",
            "entries": [{"code": "SERVER", "message": "structured"}],
        }
    else:
        core["error_ledger"] = {
            "status": "RED",
            "entries": [{"code": fault.upper(), "message": "structured"}],
        }
    path = write_json(
        root / ".local" / f"observer-{fault}.json",
        closeout.seal_publisher_receipt(core),
    )
    binding = {
        "path": path.relative_to(root).as_posix(),
        "sha256": closeout.sha256_path(path),
        "bytes": path.stat().st_size,
    }
    with pytest.raises(closeout.CloseoutError, match="exact gate"):
        closeout._verify_focused_observer(root, binding, proof)


def test_focused_state_sequence_and_one_shot_contract_are_enforced(tmp_path):
    root, proof, *_ = prepare_focused_inputs(tmp_path)
    assert proof["state_sequence"] == list(closeout.FOCUSED_STATE_SEQUENCE)
    assert proof["invocation_contract"] == {
        "max_invocations": 1,
        "retry": False,
        "non_pty": True,
    }
    core = {key: copy.deepcopy(value) for key, value in proof.items() if key != "receipt_sha256"}
    core["state_sequence"] = ["ABSENT", "PASS"]
    with pytest.raises(closeout.CloseoutError, match="PROVED state"):
        closeout.verify_focused_proof(
            root, closeout.seal_publisher_receipt(core)
        )


@pytest.mark.skipif(os.name != "nt", reason="PowerShell wrapper contract is Windows-only")
@pytest.mark.windows_host
def test_wrapper_success_paths_emit_one_integer_and_release_run_lock(tmp_path):
    stub = tmp_path / "focused-python.cmd"
    stub.write_text(
        "@echo off\r\necho {\"status\":\"stub-pass\"}\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    powershell = "powershell.exe"
    common = Path(
        git(
            PROJECT_ROOT,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
    )
    outer_lock_path_raw = os.environ.get(closeout.VALIDATION_LOCK_PATH_ENV)
    outer_lock_token = os.environ.get(closeout.VALIDATION_LOCK_TOKEN_ENV)
    assert bool(outer_lock_path_raw) == bool(outer_lock_token)
    outer_lock_bytes = None
    if outer_lock_path_raw and outer_lock_token:
        outer_lock_path = Path(outer_lock_path_raw).resolve()
        assert outer_lock_path == (
            common / "campaign-player-wiki-complete-validation.lock"
        ).resolve()
        outer_lock_bytes = outer_lock_path.read_bytes()
        assert outer_lock_bytes == outer_lock_token.encode("utf-8")
    actions = [
        (
            "publisher-focused-proof",
            [
                "-PublisherPreflightReceipt",
                "preflight.json",
                "-PublisherDisposalPlan",
                "plan.json",
                "-PublisherValidationIdentity",
                "validation.json",
            ],
        ),
        (
            "publisher-focused-run",
            ["-PublisherFocusedProof", "proof.json"],
        ),
        (
            "publisher-focused-finalize",
            [
                "-PublisherFocusedProof",
                "proof.json",
                "-PublisherFocusedResult",
                "result.json",
            ],
        ),
    ]
    for action, extra in actions:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "local.ps1"),
                "-Action",
                action,
                "-PythonPath",
                str(stub),
                "-PublisherCloseoutOutput",
                str(tmp_path / action),
                *extra,
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "stub-pass" in result.stdout
        assert "Object[]" not in result.stderr
    lock_path = common / "campaign-player-wiki-complete-validation.lock"
    if outer_lock_bytes is not None:
        assert lock_path.read_bytes() == outer_lock_bytes
    lock_check = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            (
                "$s=[IO.File]::Open("
                + repr(str(lock_path))
                + ",[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,"
                "[IO.FileShare]::None);$s.Dispose()"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if outer_lock_bytes is None:
        assert lock_check.returncode == 0, lock_check.stderr
    else:
        assert lock_check.returncode != 0
        assert lock_path.read_bytes() == outer_lock_bytes


def test_wrapper_passes_only_scalar_paths_and_locks_only_focused_run():
    wrapper = (PROJECT_ROOT / "local.ps1").read_text(encoding="utf-8")
    for action in (
        "publisher-focused-proof",
        "publisher-focused-run",
        "publisher-focused-finalize",
    ):
        assert action in wrapper
    assert "ConvertFrom-Json" not in wrapper
    focused_function = wrapper.split(
        "function Invoke-PublisherFocusedLifecycle", 1
    )[1].split("function Invoke-ValidationEvidence", 1)[0]
    assert "PublisherTestSelector" not in focused_function
    assert '"--proof", $PublisherFocusedProof' in focused_function
    run_dispatch = wrapper.split(
        'if ($Action -in @("publisher-focused-proof"', 1
    )[1].split(
        'if ($Action -notin @("runtime-check"', 1
    )[0]
    assert "Invoke-WithCompleteValidationLock" in run_dispatch
    assert 'if ($Action -eq "publisher-focused-run")' in run_dispatch
