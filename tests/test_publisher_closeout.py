from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "publisher_closeout.py"
SPEC = importlib.util.spec_from_file_location("publisher_closeout", SCRIPT_PATH)
assert SPEC and SPEC.loader
closeout = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = closeout
SPEC.loader.exec_module(closeout)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "publisher-test@example.invalid")
    git(root, "config", "user.name", "Publisher Test")
    (root / ".gitignore").write_text(".local/\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_one.py").write_text(
        "def test_one():\n    assert True\n", encoding="utf-8"
    )
    (root / "docs" / "contracts").mkdir(parents=True)
    (root / "docs" / "contracts" / "anchor.md").write_text("anchor\n", encoding="utf-8")
    (root / ".local" / "roadmaps").mkdir(parents=True)
    (root / ".local" / "roadmaps" / "lifecycle.md").write_text("lifecycle\n", encoding="utf-8")
    (root / ".local" / "managed").mkdir()
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return root


def candidate_config(root: Path, *, cleanup: dict | None = None) -> dict:
    commit = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", "HEAD^{tree}")
    lifecycle = root / ".local" / "roadmaps" / "lifecycle.md"
    anchor = root / "docs" / "contracts" / "anchor.md"
    return {
        "schema_version": 1,
        "phase": "phase-test",
        "phase_markers": ["phase-test"],
        "active_owner_paths": [],
        "accepted_candidate": {"commit": commit, "tree": tree},
        "target": {"ref": "main", "expected_commit": commit},
        "test_selectors": ["tests/test_one.py"],
        "live_routes": [],
        "browser": {"mode": "publisher-attached", "attachment": "publisher-task"},
        "canonical_controls": {
            "lifecycle": {"path": str(lifecycle), "sha256": closeout.sha256_path(lifecycle)},
            "anchor": {"path": str(anchor), "sha256": closeout.sha256_path(anchor)},
        },
        "managed_roots": [str(root / ".local" / "managed")],
        "cleanup": cleanup
        or {
            "worktrees": [],
            "local_refs": [],
            "remote_refs": [],
            "evidence_roots": [],
            "cache_roots": [],
            "temp_roots": [],
            "deploy_temps": [],
            "historical_residuals": [],
        },
    }


def write_config(root: Path, config: dict) -> Path:
    path = root / ".local" / "candidate.json"
    path.write_bytes(closeout.canonical_json_bytes(config))
    return path


def fake_environment(*_args, **_kwargs):
    return {
        "label": "validation-environment",
        "manifest": {
            "ok": True,
            "python_version": "fixture",
            "locked_requirements_checked": 29,
        },
    }


def fake_manifest(_root, _python, _config, cache, export, manifest, _output):
    export.write_bytes(cache.read_bytes())
    manifest.write_bytes(b'{"fixture":"manifest"}\n')
    return {"label": "publisher-manifest", "exit_code": 0}


def install_preflight_fakes(monkeypatch):
    monkeypatch.setattr(closeout, "environment_record", fake_environment)
    monkeypatch.setattr(closeout, "generate_manifest", fake_manifest)


def test_explicit_python_is_required_and_never_falls_back_to_path(tmp_path):
    missing = tmp_path / "python.exe"
    with pytest.raises(closeout.CloseoutError, match="absolute interpreter"):
        closeout.assert_explicit_python(missing)
    other = tmp_path / "other-python.exe"
    other.write_text("not executable", encoding="utf-8")
    with pytest.raises(closeout.CloseoutError, match="exact explicit"):
        closeout.assert_explicit_python(other)


def test_preflight_collects_twice_in_python_order_and_seals_cache(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    config_path = write_config(root, candidate_config(root))
    output = root / ".local" / "release"
    calls = []

    def fake_collect(_root, _python, _selectors, _output, *, label):
        calls.append(label)
        values = ["tests/test_one.py::test_z", "tests/test_one.py::test_a"]
        return values, {"label": label, "exit_code": 0}

    install_preflight_fakes(monkeypatch)
    monkeypatch.setattr(closeout, "collect_nodeids", fake_collect)
    receipt = closeout.preflight(
        project_root=root,
        python_path=Path(sys.executable),
        config_path=config_path,
        output=output,
    )
    assert calls == ["pytest-collect-1", "pytest-collect-2"]
    assert json.loads((output / "nodeids-cache.json").read_text(encoding="utf-8")) == [
        "tests/test_one.py::test_a",
        "tests/test_one.py::test_z",
    ]
    plan = closeout.read_json_utf8(output / "disposal-plan.json", label="plan")
    assert plan["plan_sha256"]
    assert receipt["collections"]["canonical_count"] == 2


def test_preflight_refuses_non_deterministic_collection(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    config_path = write_config(root, candidate_config(root))
    install_preflight_fakes(monkeypatch)
    values = iter(
        [
            (["tests/test_one.py::test_a"], {"label": "one"}),
            (["tests/test_one.py::test_b"], {"label": "two"}),
        ]
    )
    monkeypatch.setattr(closeout, "collect_nodeids", lambda *_a, **_k: next(values))
    with pytest.raises(closeout.CloseoutError, match="not deterministic"):
        closeout.preflight(
            project_root=root,
            python_path=Path(sys.executable),
            config_path=config_path,
            output=root / ".local" / "release",
        )


def test_parse_nodeids_refuses_utf16_and_malformed_capture():
    with pytest.raises(closeout.CloseoutError, match="UTF-16"):
        closeout.parse_nodeids("tests/test_one.py::test_one".encode("utf-16"))
    with pytest.raises(closeout.CloseoutError, match="well-formed"):
        closeout.parse_nodeids(b"collected 1 item\n")


def test_environment_receipt_requires_exact_29_lock_manifest_and_preserves_capture(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    output = root / ".local" / "environment"

    def fake_run(arguments, *, cwd, env=None):
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "python_version": "3.12.12",
                    "locked_requirements_checked": 29,
                    "dependency_check": "pip-ok",
                }
            ).encode("utf-8"),
            stderr=b"environment stderr retained\n",
        )

    monkeypatch.setattr(closeout, "run_child", fake_run)
    output.mkdir(parents=True)
    record = closeout.environment_record(root, Path(sys.executable), output)
    assert record["manifest"]["locked_requirements_checked"] == 29
    assert (output / "children" / "validation-environment.stderr.bin").read_bytes() == b"environment stderr retained\n"

    def failed_run(arguments, *, cwd, env=None):
        return subprocess.CompletedProcess(arguments, 1, stdout=b"{}", stderr=b"lock mismatch")

    monkeypatch.setattr(closeout, "run_child", failed_run)
    with pytest.raises(closeout.CloseoutError, match="environment check failed"):
        closeout.environment_record(root, Path(sys.executable), output)


def test_preflight_refuses_manifest_cache_binding_mismatch(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    config_path = write_config(root, candidate_config(root))
    install_preflight_fakes(monkeypatch)
    monkeypatch.setattr(
        closeout,
        "collect_nodeids",
        lambda *_a, **_k: (["tests/test_one.py::test_one"], {"label": "collect"}),
    )

    def mismatched_manifest(_root, _python, _config, _cache, export, manifest, _output):
        export.write_text("[]\n", encoding="utf-8")
        manifest.write_text("{}\n", encoding="utf-8")
        return {"label": "manifest"}

    monkeypatch.setattr(closeout, "generate_manifest", mismatched_manifest)
    with pytest.raises(closeout.CloseoutError, match="cache/export bytes differ"):
        closeout.preflight(
            project_root=root,
            python_path=Path(sys.executable),
            config_path=config_path,
            output=root / ".local" / "release",
        )


def prepare_plan(root: Path, config: dict) -> tuple[dict, Path]:
    cache = root / ".local" / "cache.json"
    export = root / ".local" / "export.json"
    manifest = root / ".local" / "manifest.json"
    cache.write_text("[]\n", encoding="utf-8")
    export.write_text("[]\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    controls = closeout._control_record(root, config)
    accepted = config["accepted_candidate"]
    plan = closeout.build_disposal_plan(
        root,
        config,
        accepted=accepted["commit"],
        tree=accepted["tree"],
        controls=controls,
        cache_path=cache,
        export_path=export,
        manifest_path=manifest,
    )
    plan_path = root / ".local" / "plan.json"
    plan_path.write_bytes(closeout.canonical_json_bytes(plan))
    return plan, plan_path


def green_receipt(plan: dict) -> dict:
    return {
        "schema_version": 1,
        "status": "GREEN",
        "plan_sha256": plan["plan_sha256"],
        "accepted_candidate": plan["accepted_candidate"],
        "git": {"status": "GREEN"},
        "deploy": {"status": "GREEN"},
        "live": {"status": "GREEN"},
    }


def test_plan_and_dispose_remove_only_phase_worktree_and_merged_local_ref(tmp_path):
    root = make_repo(tmp_path)
    phase_path = tmp_path / "phase-worktree"
    git(root, "branch", "phase-test")
    git(root, "worktree", "add", str(phase_path), "phase-test")
    config = candidate_config(
        root,
        cleanup={
            "worktrees": [{"phase": "phase-test", "path": str(phase_path)}],
            "local_refs": [{"phase": "phase-test", "ref": "refs/heads/phase-test"}],
            "remote_refs": [],
            "evidence_roots": [],
            "cache_roots": [],
            "temp_roots": [],
            "deploy_temps": [],
            "historical_residuals": [],
        },
    )
    plan, plan_path = prepare_plan(root, config)
    assert [item["disposition"] for item in plan["items"]] == ["ELIGIBLE", "ELIGIBLE"]
    receipt_path = root / ".local" / "green.json"
    receipt_path.write_bytes(closeout.canonical_json_bytes(green_receipt(plan)))
    code, result = closeout.dispose(
        project_root=root,
        plan_path=plan_path,
        formal_close_receipt_path=receipt_path,
        output=root / ".local" / "dispose",
        apply=False,
    )
    assert code == 0
    assert [row["status"] for row in result["items"]] == ["PLANNED", "PLANNED"]
    code, result = closeout.dispose(
        project_root=root,
        plan_path=plan_path,
        formal_close_receipt_path=receipt_path,
        output=root / ".local" / "dispose-apply",
        apply=True,
    )
    assert code == 0
    assert [row["status"] for row in result["items"]] == ["REMOVED", "REMOVED"]
    assert not phase_path.exists()
    assert subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/phase-test"], cwd=root).returncode != 0


def test_plan_refuses_to_seal_an_omitted_phase_ref_or_worktree(tmp_path):
    root = make_repo(tmp_path)
    phase_path = tmp_path / "phase-worktree"
    git(root, "branch", "phase-test")
    git(root, "worktree", "add", str(phase_path), "phase-test")
    config = candidate_config(root)
    with pytest.raises(closeout.CloseoutError, match="omitted from the sealed cleanup census"):
        prepare_plan(root, config)


@pytest.mark.parametrize("condition", ["dirty", "unique", "active", "main", "foreign", "reparse", "common-dir"])
def test_plan_refuses_protected_or_ambiguous_worktrees(tmp_path, monkeypatch, condition):
    root = make_repo(tmp_path)
    phase_path = tmp_path / "phase-worktree"
    git(root, "branch", "phase-test")
    git(root, "worktree", "add", str(phase_path), "phase-test")
    if condition == "dirty":
        (phase_path / "dirty.txt").write_text("x", encoding="utf-8")
    elif condition == "unique":
        (phase_path / "unique.txt").write_text("x", encoding="utf-8")
        git(phase_path, "add", "unique.txt")
        git(phase_path, "commit", "-m", "unique")
    elif condition == "active":
        pass
    elif condition == "foreign":
        git(root, "worktree", "remove", "--", str(phase_path))
        phase_path = tmp_path / "foreign"
        phase_path.mkdir()
    elif condition == "reparse":
        monkeypatch.setattr(closeout, "is_reparse", lambda path: path == phase_path)
    elif condition == "common-dir":
        real_git = closeout.git

        def mismatched_git(current_root, *args):
            if current_root == phase_path and args[-1] == "--git-common-dir":
                return "C:/wrong/.git"
            return real_git(current_root, *args)

        monkeypatch.setattr(closeout, "git", mismatched_git)
    selected_path = root if condition == "main" else phase_path
    worktrees = [{"phase": "phase-test", "path": str(selected_path)}]
    if condition == "main":
        worktrees.append({"phase": "phase-test", "path": str(phase_path)})
    config = candidate_config(
        root,
        cleanup={
            "worktrees": worktrees,
            "local_refs": [{"phase": "phase-test", "ref": "refs/heads/phase-test"}],
            "remote_refs": [], "evidence_roots": [], "cache_roots": [], "temp_roots": [],
            "deploy_temps": [], "historical_residuals": [],
        },
    )
    if condition == "active":
        config["active_owner_paths"] = [str(phase_path)]
    plan, _ = prepare_plan(root, config)
    assert plan["items"][0]["disposition"] == "REFUSED"


def test_dispose_refuses_missing_ambiguous_or_mismatched_receipt(tmp_path):
    root = make_repo(tmp_path)
    config = candidate_config(root)
    plan, plan_path = prepare_plan(root, config)
    missing = root / ".local" / "missing.json"
    with pytest.raises(closeout.CloseoutError, match="sealed plan and formal-close receipt"):
        closeout.dispose(project_root=root, plan_path=plan_path, formal_close_receipt_path=missing, output=root / ".local" / "out", apply=False)
    receipt = green_receipt(plan)
    receipt["accepted_candidate"] = {"commit": "0" * 40, "tree": "1" * 40}
    path = root / ".local" / "bad.json"
    path.write_bytes(closeout.canonical_json_bytes(receipt))
    with pytest.raises(closeout.CloseoutError, match="candidate does not match"):
        closeout.dispose(project_root=root, plan_path=plan_path, formal_close_receipt_path=path, output=root / ".local" / "out", apply=False)


def test_dispose_refuses_drifted_candidate_bound_config(tmp_path):
    root = make_repo(tmp_path)
    config = candidate_config(root)
    config_path = write_config(root, config)
    cache = root / ".local" / "cache.json"
    export = root / ".local" / "export.json"
    manifest = root / ".local" / "manifest.json"
    for path, payload in ((cache, "[]\n"), (export, "[]\n"), (manifest, "{}\n")):
        path.write_text(payload, encoding="utf-8")
    plan = closeout.build_disposal_plan(
        root, config, accepted=config["accepted_candidate"]["commit"], tree=config["accepted_candidate"]["tree"],
        controls=closeout._control_record(root, config), cache_path=cache, export_path=export,
        manifest_path=manifest, config_path=config_path,
    )
    plan_path = root / ".local" / "plan.json"
    plan_path.write_bytes(closeout.canonical_json_bytes(plan))
    config_path.write_text("{\"schema_version\": 999}\n", encoding="utf-8")
    receipt_path = root / ".local" / "green.json"
    receipt_path.write_bytes(closeout.canonical_json_bytes(green_receipt(plan)))
    with pytest.raises(closeout.CloseoutError, match="config input drifted"):
        closeout.dispose(project_root=root, plan_path=plan_path, formal_close_receipt_path=receipt_path, output=root / ".local" / "out", apply=False)


def test_nonlisted_residual_is_never_discovered_or_removed(tmp_path):
    root = make_repo(tmp_path)
    residual = root / ".local" / "managed" / "not-in-plan"
    residual.mkdir()
    (residual / "evidence.txt").write_text("retain", encoding="utf-8")
    config = candidate_config(root)
    plan, plan_path = prepare_plan(root, config)
    receipt_path = root / ".local" / "green.json"
    receipt_path.write_bytes(closeout.canonical_json_bytes(green_receipt(plan)))
    code, _ = closeout.dispose(project_root=root, plan_path=plan_path, formal_close_receipt_path=receipt_path, output=root / ".local" / "out", apply=True)
    assert code == 0
    assert residual.exists()


def test_historical_residual_requires_active_process_proof(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    residual = root / ".local" / "managed" / "historical"
    residual.mkdir()
    (residual / "raw.txt").write_text("already summarized", encoding="utf-8")
    config = candidate_config(
        root,
        cleanup={
            "worktrees": [], "local_refs": [], "remote_refs": [], "evidence_roots": [], "deploy_temps": [],
            "cache_roots": [], "temp_roots": [],
            "historical_residuals": [{
                "phase": "phase-test", "path": str(residual),
                "evidence_summary_recorded": True, "no_unique_evidence": True,
            }],
        },
    )
    plan, plan_path = prepare_plan(root, config)
    assert plan["items"][0]["disposition"] == "ELIGIBLE"
    receipt_path = root / ".local" / "green.json"
    receipt_path.write_bytes(closeout.canonical_json_bytes(green_receipt(plan)))
    monkeypatch.setattr(closeout, "no_active_process_at", lambda _path: False)
    code, result = closeout.dispose(project_root=root, plan_path=plan_path, formal_close_receipt_path=receipt_path, output=root / ".local" / "out", apply=True)
    assert code == 1
    assert result["items"][0]["status"] == "REFUSED"
    assert residual.exists()


def test_apply_prevalidates_every_item_and_aborts_before_any_removal(tmp_path):
    root = make_repo(tmp_path)
    phase_path = tmp_path / "phase-worktree"
    git(root, "branch", "phase-test")
    git(root, "worktree", "add", str(phase_path), "phase-test")
    anchor = root / "docs" / "contracts" / "anchor.md"
    config = candidate_config(
        root,
        cleanup={
            "worktrees": [{"phase": "phase-test", "path": str(phase_path)}],
            "local_refs": [{"phase": "phase-test", "ref": "refs/heads/phase-test"}],
            "remote_refs": [],
            "evidence_roots": [{
                "phase": "phase-test", "path": str(anchor),
                "evidence_summary_recorded": True, "no_unique_evidence": True,
            }],
            "cache_roots": [], "temp_roots": [], "deploy_temps": [], "historical_residuals": [],
        },
    )
    plan, plan_path = prepare_plan(root, config)
    receipt_path = root / ".local" / "green.json"
    receipt_path.write_bytes(closeout.canonical_json_bytes(green_receipt(plan)))
    code, result = closeout.dispose(
        project_root=root, plan_path=plan_path, formal_close_receipt_path=receipt_path,
        output=root / ".local" / "out", apply=True,
    )
    assert code == 1
    assert [row["status"] for row in result["items"]] == ["NOT_APPLIED", "NOT_APPLIED", "REFUSED"]
    assert phase_path.exists()
    assert subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/phase-test"], cwd=root
    ).returncode == 0


def test_literal_ancestor_reparse_is_refused_before_containment_or_fingerprint(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    alias = root / ".local" / "managed" / "alias"
    target = alias / "phase-test-evidence"
    target.mkdir(parents=True)
    config = candidate_config(
        root,
        cleanup={
            "worktrees": [], "local_refs": [], "remote_refs": [],
            "evidence_roots": [{
                "phase": "phase-test", "path": str(target),
                "evidence_summary_recorded": True, "no_unique_evidence": True,
            }],
            "cache_roots": [], "temp_roots": [], "deploy_temps": [], "historical_residuals": [],
        },
    )
    actual = closeout._is_reparse_stat
    monkeypatch.setattr(
        closeout,
        "_is_reparse_stat",
        lambda path, metadata: path == alias or actual(path, metadata),
    )
    with pytest.raises(closeout.CloseoutError, match="contains a reparse"):
        prepare_plan(root, config)
    assert target.exists()


@pytest.mark.parametrize("managed", [".local/roadmaps", ".local/data", "."])
def test_managed_roots_refuse_controls_data_and_repository_root(tmp_path, managed):
    root = make_repo(tmp_path)
    (root / ".local" / "data").mkdir(exist_ok=True)
    config = candidate_config(root)
    config["managed_roots"] = [str(root / managed)]
    with pytest.raises(closeout.CloseoutError):
        prepare_plan(root, config)


def test_managed_root_cannot_be_an_ancestor_of_a_canonical_control(tmp_path):
    root = make_repo(tmp_path)
    protected_anchor = root / ".local" / "managed" / "canonical-anchor.md"
    protected_anchor.write_text("anchor", encoding="utf-8")
    config = candidate_config(root)
    config["canonical_controls"]["anchor"] = {
        "path": str(protected_anchor), "sha256": closeout.sha256_path(protected_anchor)
    }
    with pytest.raises(closeout.CloseoutError, match="contains a canonical lifecycle/anchor control"):
        prepare_plan(root, config)


def test_inventory_requires_every_category_and_exhaustively_accounts_for_phase_markers(tmp_path):
    root = make_repo(tmp_path)
    missing = candidate_config(root)
    del missing["cleanup"]["cache_roots"]
    with pytest.raises(closeout.CloseoutError, match="cache_roots must be a present array"):
        prepare_plan(root, missing)
    undisclosed = root / ".local" / "managed" / "phase-test-undisclosed"
    undisclosed.mkdir()
    config = candidate_config(root)
    with pytest.raises(closeout.CloseoutError, match="phase-marked path omitted"):
        prepare_plan(root, config)


def test_plan_requires_an_explicit_active_ownership_inventory(tmp_path):
    root = make_repo(tmp_path)
    config = candidate_config(root)
    del config["active_owner_paths"]
    with pytest.raises(closeout.CloseoutError, match="active_owner_paths must be an array"):
        prepare_plan(root, config)


def test_zero_item_inventory_is_sealed_only_after_an_empty_exhaustive_scan(tmp_path):
    root = make_repo(tmp_path)
    plan, _ = prepare_plan(root, candidate_config(root))
    inventory = plan["cleanup_inventory"]
    assert inventory["declared_item_count"] == 0
    assert inventory["phase_owned_scan"] == {"paths": [], "count": 0}
    assert inventory["sha256"]


def test_parent_browser_fallback_requires_script_and_named_auditor(tmp_path):
    root = make_repo(tmp_path)
    config = candidate_config(root)
    config["browser"] = {"mode": "parent-fallback", "script": ""}
    with pytest.raises(closeout.CloseoutError, match="named auditing role/capability"):
        prepare_plan(root, config)
    script = root / ".local" / "parent-browser-script.json"
    script.write_text("{}\n", encoding="utf-8")
    config["browser"] = {
        "mode": "parent-fallback", "script": str(script),
        "auditing_role": "Verifier", "auditing_capability": "parent-browser-audit",
    }
    plan, _ = prepare_plan(root, config)
    assert plan["browser"]["script"]["sha256"] == closeout.sha256_path(script)


def test_local_ref_must_already_be_merged_into_main_at_plan_sealing(tmp_path):
    root = make_repo(tmp_path)
    phase_path = tmp_path / "phase-worktree"
    git(root, "branch", "phase-test")
    git(root, "worktree", "add", str(phase_path), "phase-test")
    (phase_path / "unique.txt").write_text("unique", encoding="utf-8")
    git(phase_path, "add", "unique.txt")
    git(phase_path, "commit", "-m", "unique phase work")
    config = candidate_config(
        root,
        cleanup={
            "worktrees": [{"phase": "phase-test", "path": str(phase_path)}],
            "local_refs": [{"phase": "phase-test", "ref": "refs/heads/phase-test"}],
            "remote_refs": [], "evidence_roots": [], "cache_roots": [], "temp_roots": [],
            "deploy_temps": [], "historical_residuals": [],
        },
    )
    plan, _ = prepare_plan(root, config)
    local_ref = next(item for item in plan["items"] if item["kind"] == "local_ref")
    assert local_ref["disposition"] == "REFUSED"
    assert "not merged" in local_ref["reason"]


def test_apply_revalidates_active_ownership_before_any_mutation(tmp_path):
    root = make_repo(tmp_path)
    phase_path = tmp_path / "phase-worktree"
    git(root, "branch", "phase-test")
    git(root, "worktree", "add", str(phase_path), "phase-test")
    config = candidate_config(
        root,
        cleanup={
            "worktrees": [{"phase": "phase-test", "path": str(phase_path)}],
            "local_refs": [{"phase": "phase-test", "ref": "refs/heads/phase-test"}],
            "remote_refs": [], "evidence_roots": [], "cache_roots": [], "temp_roots": [],
            "deploy_temps": [], "historical_residuals": [],
        },
    )
    plan, plan_path = prepare_plan(root, config)
    plan["census"]["active_owner_paths"] = [str(phase_path)]
    plan = closeout.seal_plan(plan)
    plan_path.write_bytes(closeout.canonical_json_bytes(plan))
    receipt_path = root / ".local" / "green.json"
    receipt_path.write_bytes(closeout.canonical_json_bytes(green_receipt(plan)))
    code, result = closeout.dispose(
        project_root=root, plan_path=plan_path, formal_close_receipt_path=receipt_path,
        output=root / ".local" / "out", apply=True,
    )
    assert code == 1
    assert result["items"][0]["status"] == "REFUSED"
    assert phase_path.exists()


def test_wrapper_is_thin_and_propagates_child_exit_without_json_parsing():
    wrapper = (PROJECT_ROOT / "local.ps1").read_text(encoding="utf-8")
    assert '"publisher-preflight"' in wrapper
    assert '"publisher-dispose"' in wrapper
    assert "ConvertFrom-Json" not in wrapper
    assert "publisher_closeout.py" in wrapper
    assert "exit $LASTEXITCODE" in wrapper


def test_wrapper_returns_child_failure_without_reencoding_json():
    powershell = "powershell.exe"
    if not __import__("shutil").which(powershell):
        pytest.skip("PowerShell is unavailable")
    result = subprocess.run(
        [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "local.ps1"),
            "-Action", "publisher-preflight", "-PythonPath", sys.executable,
            "-PublisherConfig", str(PROJECT_ROOT / ".local" / "missing-publisher-config.json"),
            "-PublisherCloseoutOutput", str(PROJECT_ROOT / ".local" / "missing-publisher-output"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Publisher closeout error" in result.stderr


def test_script_uses_no_force_prune_glob_or_broad_recursive_helper():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in ("shutil.rmtree", "worktree prune", "--force", ".glob("):
        assert forbidden not in source
