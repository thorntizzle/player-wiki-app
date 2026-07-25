"""Deterministic, local-only Publisher preflight and sealed-plan disposal.

This helper deliberately owns the parts of formal close that are easiest to
accidentally implement differently in a shell wrapper: JSON encoding, node-id
ordering, child-process evidence, Git census, and literal-path cleanup proof.
It does *not* grant a release authority.  ``preflight`` is local-only and
``dispose`` requires a matching, already-green formal-close receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
SHA = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)


class CloseoutError(ValueError):
    """A failed proof.  Callers must stop rather than weakening it."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def read_json_utf8(path: Path, *, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw:
        raise CloseoutError(f"{label} must be canonical UTF-8 JSON, not UTF-16/binary")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"{label} is not canonical UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CloseoutError(f"{label} must be a JSON object")
    return value


def require_sha(value: object, *, label: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise CloseoutError(f"{label} must be a full 40-character commit SHA")
    return value.lower()


def resolve_from_root(root: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CloseoutError(f"{label} must be a non-empty path string")
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve(strict=False)


def relative_label(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def is_reparse(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes  # type: ignore[attr-defined]
    except AttributeError:
        return path.is_symlink()
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def literal_child(path: Path, root: Path) -> bool:
    """Containment without accepting the root itself or following a reparse point."""
    try:
        return path.resolve(strict=False).relative_to(root.resolve(strict=False)) != Path(".")
    except ValueError:
        return False


def run_child(
    arguments: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments), cwd=cwd, check=False, capture_output=True, env=env
    )


def child_record(
    label: str, result: subprocess.CompletedProcess[bytes], output_root: Path
) -> dict[str, Any]:
    stdout_path = output_root / "children" / f"{label}.stdout.bin"
    stderr_path = output_root / "children" / f"{label}.stderr.bin"
    atomic_write(stdout_path, result.stdout)
    atomic_write(stderr_path, result.stderr)
    return {
        "label": label,
        "arguments": list(result.args) if not isinstance(result.args, str) else [result.args],
        "exit_code": result.returncode,
        "stdout": {"path": stdout_path.name if stdout_path.parent == output_root else str(stdout_path.relative_to(output_root)), "sha256": sha256_bytes(result.stdout), "bytes": len(result.stdout)},
        "stderr": {"path": stderr_path.name if stderr_path.parent == output_root else str(stderr_path.relative_to(output_root)), "sha256": sha256_bytes(result.stderr), "bytes": len(result.stderr)},
    }


def git(root: Path, *arguments: str) -> str:
    result = run_child(["git", *arguments], cwd=root)
    if result.returncode:
        raise CloseoutError(
            f"git {' '.join(arguments)} failed: "
            f"{result.stderr.decode('utf-8', errors='replace').strip() or 'unknown error'}"
        )
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CloseoutError(f"git {' '.join(arguments)} returned malformed text") from exc


def git_path(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def accepted_identity(root: Path, commit: str) -> tuple[str, str]:
    accepted = git(root, "rev-parse", "--verify", f"{commit}^{{commit}}").lower()
    tree = git(root, "rev-parse", "--verify", f"{commit}^{{tree}}").lower()
    return accepted, tree


def assert_clean_exact_checkout(root: Path, accepted: str, tree: str) -> None:
    head, actual_tree = accepted_identity(root, "HEAD")
    if head != accepted or actual_tree != tree:
        raise CloseoutError("checkout is not the accepted commit/tree")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise CloseoutError("accepted checkout is not clean")


def load_config(root: Path, path: Path) -> tuple[dict[str, Any], bytes]:
    config = read_json_utf8(path, label="Publisher candidate config")
    if config.get("schema_version") != SCHEMA_VERSION:
        raise CloseoutError("Publisher candidate config schema_version is unsupported")
    phase = config.get("phase")
    if not isinstance(phase, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", phase):
        raise CloseoutError("Publisher candidate config requires a normalized phase name")
    accepted = config.get("accepted_candidate")
    if not isinstance(accepted, dict):
        raise CloseoutError("Publisher candidate config requires accepted_candidate")
    require_sha(accepted.get("commit"), label="accepted_candidate.commit")
    require_sha(accepted.get("tree"), label="accepted_candidate.tree")
    return config, path.read_bytes()


def assert_explicit_python(python_path: Path) -> None:
    if not python_path.is_absolute() or not python_path.is_file():
        raise CloseoutError("--python-path must name an existing absolute interpreter")
    if python_path.resolve() != Path(sys.executable).resolve():
        raise CloseoutError("Publisher must run under the exact explicit --python-path; PATH fallback is forbidden")


def environment_record(root: Path, python_path: Path, output_root: Path) -> dict[str, Any]:
    result = run_child(
        [str(python_path), "-B", str(root / "scripts" / "verify_validation_environment.py"), "--project-root", str(root)],
        cwd=root,
    )
    record = child_record("validation-environment", result, output_root)
    if result.returncode != 0:
        raise CloseoutError("exact validation environment check failed")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloseoutError("validation environment did not emit canonical UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise CloseoutError("validation environment receipt did not report ok")
    record["manifest"] = payload
    return record


def parse_nodeids(raw: bytes) -> list[str]:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw:
        raise CloseoutError("pytest collection emitted UTF-16/binary output")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CloseoutError("pytest collection emitted non-UTF-8 output") from exc
    nodeids = [line.strip() for line in text.splitlines() if line.strip().startswith("tests/")]
    if not nodeids or not all("::" in nodeid and "\x00" not in nodeid for nodeid in nodeids):
        raise CloseoutError("pytest collection did not produce well-formed test node IDs")
    if len(nodeids) != len(set(nodeids)):
        raise CloseoutError("pytest collection produced duplicate node IDs")
    return nodeids


def collect_nodeids(
    root: Path, python_path: Path, selectors: Sequence[str], output_root: Path, *, label: str
) -> tuple[list[str], dict[str, Any]]:
    if not selectors or not all(isinstance(item, str) and item for item in selectors):
        raise CloseoutError("candidate config requires a non-empty string test_selectors array")
    result = run_child(
        [str(python_path), "-B", "-m", "pytest", "--collect-only", "-q", *selectors], cwd=root
    )
    record = child_record(label, result, output_root)
    if result.returncode != 0:
        raise CloseoutError(f"{label} pytest collection failed")
    return parse_nodeids(result.stdout), record


def _output_directory(root: Path, output: Path) -> Path:
    local_root = (root / ".local").resolve()
    resolved = output.resolve(strict=False)
    if not literal_child(resolved, local_root):
        raise CloseoutError("Publisher output must be an exact directory inside repository .local")
    if resolved.exists() and (not resolved.is_dir() or is_reparse(resolved)):
        raise CloseoutError("Publisher output must be a normal non-reparse directory")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _control_record(root: Path, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    controls = config.get("canonical_controls")
    if not isinstance(controls, dict):
        raise CloseoutError("candidate config requires canonical_controls")
    result: dict[str, dict[str, Any]] = {}
    for name in ("lifecycle", "anchor"):
        item = controls.get(name)
        if not isinstance(item, dict):
            raise CloseoutError(f"canonical_controls.{name} is required")
        path = resolve_from_root(root, item.get("path"), label=f"canonical_controls.{name}.path")
        if not path.is_file() or is_reparse(path):
            raise CloseoutError(f"canonical control {name} is missing or unsafe")
        expected = item.get("sha256")
        actual = sha256_path(path)
        if expected is not None and (not isinstance(expected, str) or expected.upper() != actual):
            raise CloseoutError(f"canonical control {name} hash does not match config")
        result[name] = {"path": relative_label(root, path), "sha256": actual, "bytes": path.stat().st_size}
    return result


def _worktree_records(root: Path) -> list[dict[str, str]]:
    output = git(root, "worktree", "list", "--porcelain")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        records.append(current)
    return records


def _path_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    if is_reparse(path):
        return {"exists": True, "unsafe_reparse": True}
    if path.is_file():
        return {"exists": True, "kind": "file", "bytes": path.stat().st_size, "sha256": sha256_path(path)}
    if not path.is_dir():
        return {"exists": True, "kind": "other"}
    entries: list[dict[str, Any]] = []
    pending = [path]
    while pending:
        directory = pending.pop()
        for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
            relative = child.relative_to(path).as_posix()
            if is_reparse(child):
                entries.append({"path": relative, "kind": "reparse"})
                continue
            if child.is_dir():
                entries.append({"path": relative, "kind": "directory"})
                pending.append(child)
            elif child.is_file():
                entries.append({"path": relative, "kind": "file", "bytes": child.stat().st_size, "sha256": sha256_path(child)})
            else:
                entries.append({"path": relative, "kind": "other"})
    payload = canonical_json_bytes(entries)
    return {"exists": True, "kind": "directory", "entry_count": len(entries), "sha256": sha256_bytes(payload), "unsafe_reparse": any(item["kind"] == "reparse" for item in entries)}


def _managed_roots(root: Path, config: dict[str, Any]) -> list[Path]:
    raw = config.get("managed_roots")
    if not isinstance(raw, list) or not raw:
        raise CloseoutError("candidate config requires a non-empty managed_roots list")
    roots = [resolve_from_root(root, value, label="managed_roots entry") for value in raw]
    if len({str(path) for path in roots}) != len(roots):
        raise CloseoutError("managed_roots contains duplicates")
    for path in roots:
        if not path.exists() or not path.is_dir() or is_reparse(path):
            raise CloseoutError("each managed root must be an existing normal directory")
    return roots


def _inside_any(path: Path, roots: Iterable[Path]) -> bool:
    return any(literal_child(path, root) for root in roots)


def _phase_item(config: dict[str, Any], raw: object, *, kind: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CloseoutError(f"cleanup.{kind} entries must be objects")
    if raw.get("phase") != config["phase"]:
        raise CloseoutError(f"cleanup.{kind} entry is not owned by the completed phase")
    return raw


def seal_plan(plan: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(plan)
    sealed.pop("plan_sha256", None)
    sealed["plan_sha256"] = sha256_bytes(canonical_json_bytes(sealed))
    return sealed


def _protected_control_paths(root: Path, controls: dict[str, dict[str, Any]]) -> set[Path]:
    return {resolve_from_root(root, item["path"], label="canonical control") for item in controls.values()}


def _phase_markers(config: dict[str, Any]) -> list[str]:
    raw = config.get("phase_markers", [config["phase"]])
    if not isinstance(raw, list) or not raw or not all(
        isinstance(item, str) and item for item in raw
    ):
        raise CloseoutError("candidate config requires non-empty phase_markers")
    return [item.casefold() for item in raw]


def _matches_phase(value: str, markers: Sequence[str]) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in markers)


def build_disposal_plan(
    root: Path, config: dict[str, Any], *, accepted: str, tree: str, controls: dict[str, dict[str, Any]], cache_path: Path, export_path: Path, manifest_path: Path, config_path: Path | None = None
) -> dict[str, Any]:
    managed_roots = _managed_roots(root, config)
    cleanup = config.get("cleanup")
    if not isinstance(cleanup, dict):
        raise CloseoutError("candidate config requires cleanup object")
    target = config.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("ref"), str):
        raise CloseoutError("candidate config requires target.ref and target.expected_commit")
    expected_target = require_sha(target.get("expected_commit"), label="target.expected_commit")
    if git(root, "rev-parse", "--verify", f"{target['ref']}^{{commit}}").lower() != expected_target:
        raise CloseoutError("target ref drifted before Publisher preflight")
    protected_controls = _protected_control_paths(root, controls)
    records = _worktree_records(root)
    by_path = {Path(record["worktree"]).resolve(): record for record in records if "worktree" in record}
    common = git_path(root)
    active_paths = {resolve_from_root(root, value, label="active_owner path") for value in config.get("active_owner_paths", [])}
    markers = _phase_markers(config)
    declared_worktrees = {
        resolve_from_root(root, raw.get("path"), label="cleanup worktree path")
        for raw in cleanup.get("worktrees", [])
        if isinstance(raw, dict)
    }
    local_refs = git(root, "for-each-ref", "--format=%(refname)", "refs/heads").splitlines()
    declared_refs = {
        raw.get("ref") for raw in cleanup.get("local_refs", []) if isinstance(raw, dict)
    }
    omitted_phase_worktrees = [
        record["worktree"]
        for record in records
        if "worktree" in record
        and Path(record["worktree"]).resolve() != root.resolve()
        and _matches_phase(record.get("branch", ""), markers)
        and Path(record["worktree"]).resolve() not in declared_worktrees
    ]
    omitted_phase_refs = [
        ref for ref in local_refs if _matches_phase(ref, markers) and ref not in declared_refs
    ]
    if omitted_phase_worktrees or omitted_phase_refs:
        raise CloseoutError(
            "phase-owned worktree/ref omitted from the sealed cleanup census: "
            + ", ".join([*omitted_phase_worktrees, *omitted_phase_refs])
        )
    items: list[dict[str, Any]] = []

    def item_base(kind: str, source: dict[str, Any]) -> dict[str, Any]:
        return {"id": f"{kind}:{len(items) + 1:03d}", "kind": kind, "phase": config["phase"], "source": source}

    for raw in cleanup.get("worktrees", []):
        source = _phase_item(config, raw, kind="worktrees")
        path = resolve_from_root(root, source.get("path"), label="cleanup worktree path")
        entry = item_base("worktree", source)
        entry["path"] = str(path)
        record = by_path.get(path)
        if path == root.resolve() or path in active_paths or path not in by_path:
            entry.update({"disposition": "REFUSED", "reason": "protected, active, or unregistered worktree"})
        elif not _matches_phase(by_path[path].get("branch", ""), markers):
            entry.update({"disposition": "REFUSED", "reason": "worktree branch lacks completed-phase ownership marker"})
        elif is_reparse(path) or Path(
            git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve() != common:
            entry.update({"disposition": "REFUSED", "reason": "unsafe reparse/common-dir worktree"})
        elif git(path, "status", "--porcelain=v1", "--untracked-files=all"):
            entry.update({"disposition": "REFUSED", "reason": "dirty worktree"})
        elif int(git(path, "rev-list", "--count", f"{accepted}..HEAD")):
            entry.update({"disposition": "REFUSED", "reason": "worktree has unique commits"})
        else:
            entry.update({"disposition": "ELIGIBLE", "head": record.get("HEAD", ""), "branch": record.get("branch", ""), "common_dir": str(common)})
        items.append(entry)

    for raw in cleanup.get("local_refs", []):
        source = _phase_item(config, raw, kind="local_refs")
        ref = source.get("ref")
        entry = item_base("local_ref", source)
        entry["ref"] = ref
        if not isinstance(ref, str) or not ref.startswith("refs/heads/") or ref == "refs/heads/main":
            entry.update({"disposition": "REFUSED", "reason": "protected or unsupported local ref"})
        elif not _matches_phase(ref, markers):
            entry.update({"disposition": "REFUSED", "reason": "local ref lacks completed-phase ownership marker"})
        else:
            try:
                tip = git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").lower()
            except CloseoutError:
                entry.update({"disposition": "REFUSED", "reason": "local ref is missing"})
            else:
                entry.update({"disposition": "ELIGIBLE", "tip": tip})
        items.append(entry)

    for raw in cleanup.get("remote_refs", []):
        source = _phase_item(config, raw, kind="remote_refs")
        entry = item_base("remote_ref", source)
        entry.update({"ref": source.get("ref"), "disposition": "REFUSED", "reason": "remote transport is intentionally unsupported by this helper"})
        items.append(entry)

    for kind, key in (("evidence_root", "evidence_roots"), ("deploy_temp", "deploy_temps"), ("historical_residual", "historical_residuals")):
        for raw in cleanup.get(key, []):
            source = _phase_item(config, raw, kind=key)
            path = resolve_from_root(root, source.get("path"), label=f"cleanup.{key} path")
            entry = item_base(kind, source)
            entry["path"] = str(path)
            fingerprint = _path_fingerprint(path)
            entry["fingerprint"] = fingerprint
            protected = path in protected_controls or not _inside_any(path, managed_roots)
            if protected:
                entry.update({"disposition": "REFUSED", "reason": "canonical control or path outside declared managed roots"})
            elif not source.get("evidence_summary_recorded", False) or not source.get("no_unique_evidence", False):
                entry.update({"disposition": "REFUSED", "reason": "evidence is unresolved or unique"})
            elif fingerprint.get("unsafe_reparse"):
                entry.update({"disposition": "REFUSED", "reason": "path contains a reparse point"})
            elif kind == "historical_residual" and path in by_path:
                entry.update({"disposition": "REFUSED", "reason": "historical residual remains registered"})
            elif not fingerprint.get("exists"):
                entry.update({"disposition": "REFUSED", "reason": "listed path is absent"})
            else:
                entry.update({"disposition": "ELIGIBLE"})
            items.append(entry)

    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-closeout-plan",
        "phase": config["phase"],
        "accepted_candidate": {"commit": accepted, "tree": tree},
        "target": {"ref": target["ref"], "expected_commit": expected_target},
        "canonical_controls": controls,
        "inputs": {
            "config": {
                "sha256": sha256_path(config_path) if config_path is not None else sha256_bytes(canonical_json_bytes(config)),
                **({"path": relative_label(root, config_path)} if config_path is not None else {}),
            },
            "nodeids_cache": {"path": relative_label(root, cache_path), "sha256": sha256_path(cache_path)},
            "nodeids_export": {"path": relative_label(root, export_path), "sha256": sha256_path(export_path)},
            "manifest": {"path": relative_label(root, manifest_path), "sha256": sha256_path(manifest_path)},
        },
        "managed_roots": [str(path) for path in managed_roots],
        "census": {
            "worktrees": [
                {"path": record.get("worktree"), "head": record.get("HEAD"), "branch": record.get("branch")}
                for record in records
            ],
            "local_refs": local_refs,
            "phase_markers": markers,
        },
        "items": items,
    }
    return seal_plan(plan)


def generate_manifest(
    root: Path, python_path: Path, config: dict[str, Any], cache_path: Path, export_path: Path, manifest_path: Path, output_root: Path
) -> dict[str, Any]:
    selectors = config.get("test_selectors")
    live_routes = config.get("live_routes", [])
    if not isinstance(selectors, list) or not isinstance(live_routes, list):
        raise CloseoutError("test_selectors and live_routes must be arrays")
    command = [str(python_path), "-B", str(root / "scripts" / "generate_publisher_manifest.py"), "--accepted-commit", str(config["accepted_candidate"]["commit"]), "--nodeids-cache", str(cache_path), "--nodeids-export", str(export_path), "--output", str(manifest_path)]
    for selector in selectors:
        command.extend(["--selector", str(selector)])
    for route in live_routes:
        command.extend(["--live-route", str(route)])
    result = run_child(command, cwd=root)
    record = child_record("publisher-manifest", result, output_root)
    if result.returncode != 0 or not manifest_path.is_file() or not export_path.is_file():
        raise CloseoutError("Publisher manifest generation failed")
    return record


def preflight(*, project_root: Path, python_path: Path, config_path: Path, output: Path) -> dict[str, Any]:
    root = project_root.resolve()
    assert_explicit_python(python_path)
    config, _ = load_config(root, config_path)
    output_root = _output_directory(root, output)
    accepted = require_sha(config["accepted_candidate"]["commit"], label="accepted candidate commit")
    configured_tree = require_sha(config["accepted_candidate"]["tree"], label="accepted candidate tree")
    actual_commit, actual_tree = accepted_identity(root, accepted)
    if actual_tree != configured_tree:
        raise CloseoutError("accepted candidate tree does not match the configured tree")
    assert_clean_exact_checkout(root, actual_commit, actual_tree)
    environment = environment_record(root, python_path, output_root)
    selectors = config.get("test_selectors")
    if not isinstance(selectors, list):
        raise CloseoutError("candidate config requires test_selectors")
    first, first_record = collect_nodeids(root, python_path, selectors, output_root, label="pytest-collect-1")
    second, second_record = collect_nodeids(root, python_path, selectors, output_root, label="pytest-collect-2")
    canonical = sorted(first)
    if canonical != sorted(second):
        raise CloseoutError("fresh pytest collections are not deterministic under Python sorted() ordering")
    cache_path = output_root / "nodeids-cache.json"
    export_path = output_root / "nodeids-export.json"
    manifest_path = output_root / "publisher-manifest.json"
    atomic_write(cache_path, canonical_json_bytes(canonical))
    manifest_record = generate_manifest(root, python_path, config, cache_path, export_path, manifest_path, output_root)
    if sha256_path(cache_path) != sha256_path(export_path):
        raise CloseoutError("Publisher node-id cache/export bytes differ")
    controls = _control_record(root, config)
    browser = config.get("browser")
    if not isinstance(browser, dict) or browser.get("mode") not in {"publisher-attached", "parent-fallback"}:
        raise CloseoutError("candidate config requires a browser attachment or explicit parent-fallback declaration")
    if browser.get("mode") == "publisher-attached" and not isinstance(browser.get("attachment"), str):
        raise CloseoutError("publisher-attached browser requires attachment evidence")
    if browser.get("mode") == "parent-fallback" and not isinstance(browser.get("script"), str):
        raise CloseoutError("parent browser fallback requires a canonical script declaration")
    plan = build_disposal_plan(
        root,
        config,
        accepted=actual_commit,
        tree=actual_tree,
        controls=controls,
        cache_path=cache_path,
        export_path=export_path,
        manifest_path=manifest_path,
        config_path=config_path,
    )
    plan_path = output_root / "disposal-plan.json"
    atomic_write(plan_path, canonical_json_bytes(plan))
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-preflight-receipt",
        "status": "PASS",
        "accepted_candidate": {"commit": actual_commit, "tree": actual_tree},
        "python_path": str(python_path),
        "environment": environment,
        "collections": {"first": first_record, "second": second_record, "canonical_count": len(canonical), "canonical_sha256": sha256_path(cache_path)},
        "manifest": manifest_record,
        "browser": browser,
        "disposal_plan": {"path": plan_path.name, "sha256": sha256_path(plan_path)},
    }
    atomic_write(output_root / "preflight-receipt.json", canonical_json_bytes(receipt))
    return receipt


def verify_sealed_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION or plan.get("kind") != "publisher-closeout-plan":
        raise CloseoutError("unsupported disposal plan")
    claimed = plan.get("plan_sha256")
    if not isinstance(claimed, str):
        raise CloseoutError("sealed plan is missing plan_sha256")
    unsealed = dict(plan)
    unsealed.pop("plan_sha256", None)
    if claimed.upper() != sha256_bytes(canonical_json_bytes(unsealed)):
        raise CloseoutError("sealed plan hash does not match its contents")


def verify_green_receipt(receipt: dict[str, Any], plan: dict[str, Any]) -> None:
    candidate = plan["accepted_candidate"]
    if receipt.get("schema_version") != SCHEMA_VERSION or receipt.get("status") != "GREEN":
        raise CloseoutError("formal-close receipt is not an explicit GREEN receipt")
    if receipt.get("plan_sha256") != plan["plan_sha256"]:
        raise CloseoutError("formal-close receipt is not bound to this sealed plan")
    if receipt.get("accepted_candidate") != candidate:
        raise CloseoutError("formal-close receipt candidate does not match sealed plan")
    for gate in ("git", "deploy", "live"):
        if receipt.get(gate, {}).get("status") != "GREEN":
            raise CloseoutError(f"formal-close receipt {gate} gate is not green")


def remove_exact_tree(path: Path) -> None:
    """Remove an exact, pre-audited normal tree without glob/force/rmtree APIs."""
    if is_reparse(path):
        raise CloseoutError("refusing to remove reparse path")
    if path.is_file():
        path.unlink()
        return
    if not path.is_dir():
        raise CloseoutError("refusing to remove non-file/non-directory path")
    for child in list(path.iterdir()):
        if is_reparse(child):
            raise CloseoutError("refusing to recurse through a reparse descendant")
        if child.is_dir():
            remove_exact_tree(child)
        elif child.is_file():
            child.unlink()
        else:
            raise CloseoutError("refusing to remove unknown tree entry")
    path.rmdir()


def no_active_process_at(path: Path) -> bool:
    """Best effort is intentionally insufficient: unavailable inspection refuses history."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return False
    literal = str(path.resolve(strict=False)).casefold()
    for process in psutil.process_iter(["pid", "cwd", "cmdline"]):
        try:
            cwd = process.info.get("cwd")
            command = process.info.get("cmdline") or []
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if isinstance(cwd, str) and cwd.casefold().startswith(literal):
            return False
        if any(isinstance(part, str) and literal in part.casefold() for part in command):
            return False
    return True


def _ref_has_worktree(root: Path, ref: str) -> bool:
    return any(record.get("branch") == ref for record in _worktree_records(root))


def _revalidate_path_item(root: Path, plan: dict[str, Any], item: dict[str, Any]) -> Path:
    path = Path(str(item["path"])).resolve(strict=False)
    managed = [Path(value).resolve(strict=False) for value in plan["managed_roots"]]
    if not _inside_any(path, managed) or is_reparse(path):
        raise CloseoutError("plan-listed path no longer satisfies literal containment/non-reparse proof")
    current = _path_fingerprint(path)
    if current != item.get("fingerprint"):
        raise CloseoutError("plan-listed path drifted since preflight")
    return path


def verify_bound_inputs(root: Path, plan: dict[str, Any]) -> None:
    inputs = plan.get("inputs")
    if not isinstance(inputs, dict):
        raise CloseoutError("sealed plan inputs are missing")
    for name in ("nodeids_cache", "nodeids_export", "manifest"):
        record = inputs.get(name)
        if not isinstance(record, dict):
            raise CloseoutError(f"sealed plan {name} binding is missing")
        path = resolve_from_root(root, record.get("path"), label=f"sealed plan {name} path")
        if not path.is_file() or is_reparse(path) or sha256_path(path) != record.get("sha256"):
            raise CloseoutError(f"sealed plan {name} input drifted or is unsafe")
    config = inputs.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("sha256"), str):
        raise CloseoutError("sealed plan config binding is missing")
    if "path" in config:
        path = resolve_from_root(root, config["path"], label="sealed plan config path")
        if not path.is_file() or is_reparse(path) or sha256_path(path) != config["sha256"]:
            raise CloseoutError("sealed plan config input drifted or is unsafe")
    controls = plan.get("canonical_controls")
    if not isinstance(controls, dict):
        raise CloseoutError("sealed plan canonical controls are missing")
    for name in ("lifecycle", "anchor"):
        record = controls.get(name)
        if not isinstance(record, dict):
            raise CloseoutError(f"sealed plan canonical {name} control is missing")
        path = resolve_from_root(root, record.get("path"), label=f"canonical {name} path")
        if not path.is_file() or is_reparse(path) or sha256_path(path) != record.get("sha256"):
            raise CloseoutError(f"canonical {name} control drifted or is unsafe")


def dispose(*, project_root: Path, plan_path: Path, formal_close_receipt_path: Path, output: Path, apply: bool) -> tuple[int, dict[str, Any]]:
    root = project_root.resolve()
    plan = read_json_utf8(plan_path, label="sealed disposal plan")
    receipt = read_json_utf8(formal_close_receipt_path, label="formal-close receipt")
    verify_sealed_plan(plan)
    verify_green_receipt(receipt, plan)
    output_root = _output_directory(root, output)
    accepted = plan["accepted_candidate"]["commit"]
    accepted_tree = plan["accepted_candidate"]["tree"]
    assert_clean_exact_checkout(root, accepted, accepted_tree)
    verify_bound_inputs(root, plan)
    target = plan["target"]
    if git(root, "rev-parse", "--verify", f"{target['ref']}^{{commit}}").lower() != accepted:
        raise CloseoutError("target ref is not the accepted candidate at disposal time")
    disposition_rows: list[dict[str, Any]] = []
    failed = False
    for item in plan["items"]:
        row = {"id": item["id"], "kind": item["kind"], "status": "PLANNED" if not apply else "PENDING"}
        if item.get("disposition") != "ELIGIBLE":
            row.update({"status": "REFUSED", "reason": item.get("reason", "not eligible")})
            failed = True
            disposition_rows.append(row)
            continue
        try:
            if item["kind"] == "worktree":
                path = Path(item["path"]).resolve(strict=False)
                if is_reparse(path) or Path(
                    git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
                ).resolve() != Path(str(item["common_dir"])).resolve():
                    raise CloseoutError("worktree common-dir/reparse proof failed")
                if git(path, "status", "--porcelain=v1", "--untracked-files=all"):
                    raise CloseoutError("worktree became dirty")
                if int(git(path, "rev-list", "--count", f"{accepted}..HEAD")):
                    raise CloseoutError("worktree has unique commits")
                if apply:
                    completed = run_child(["git", "worktree", "remove", "--", str(path)], cwd=root)
                    if completed.returncode:
                        raise CloseoutError("non-force git worktree remove failed")
                    row["status"] = "REMOVED" if not path.exists() else "FAILED"
                    if row["status"] == "FAILED":
                        raise CloseoutError("worktree remained after git removal")
            elif item["kind"] == "local_ref":
                ref = str(item["ref"])
                if git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").lower() != item["tip"]:
                    raise CloseoutError("local phase ref drifted")
                if apply and _ref_has_worktree(root, ref):
                    raise CloseoutError("local phase ref remains attached to a worktree")
                if run_child(["git", "merge-base", "--is-ancestor", ref, accepted], cwd=root).returncode:
                    raise CloseoutError("local phase ref is not merged into accepted main")
                if apply:
                    name = ref.removeprefix("refs/heads/")
                    completed = run_child(["git", "branch", "-d", "--", name], cwd=root)
                    if completed.returncode:
                        raise CloseoutError("non-force local branch deletion failed")
                    row["status"] = "REMOVED" if not run_child(["git", "show-ref", "--verify", "--quiet", ref], cwd=root).returncode == 0 else "FAILED"
                    if row["status"] == "FAILED":
                        raise CloseoutError("local ref remained after safe deletion")
            elif item["kind"] in {"evidence_root", "deploy_temp", "historical_residual"}:
                path = _revalidate_path_item(root, plan, item)
                if item["kind"] == "historical_residual":
                    registered = {Path(record["worktree"]).resolve() for record in _worktree_records(root) if "worktree" in record}
                    if path in registered or not no_active_process_at(path):
                        raise CloseoutError("historical residual is registered or has no active-process proof")
                if apply:
                    remove_exact_tree(path)
                    row["status"] = "REMOVED" if not path.exists() else "FAILED"
                    if row["status"] == "FAILED":
                        raise CloseoutError("exact managed path remained after removal")
            else:
                raise CloseoutError("unsupported sealed plan item")
            if not apply:
                row["status"] = "PLANNED"
        except (OSError, CloseoutError) as exc:
            row.update({"status": "FAILED", "reason": str(exc)})
            failed = True
        disposition_rows.append(row)
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-disposal-receipt",
        "status": "FAIL" if failed else "PASS",
        "mode": "APPLY" if apply else "DRY_RUN",
        "plan_sha256": plan["plan_sha256"],
        "accepted_candidate": plan["accepted_candidate"],
        "items": disposition_rows,
    }
    atomic_write(output_root / "disposal-receipt.json", canonical_json_bytes(result))
    return (1 if failed else 0), result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sealed local Publisher closeout automation.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--python-path", required=True, type=Path)
    preflight_parser.add_argument("--config", required=True, type=Path)
    preflight_parser.add_argument("--output", required=True, type=Path)
    dispose_parser = subparsers.add_parser("dispose")
    dispose_parser.add_argument("--plan", required=True, type=Path)
    dispose_parser.add_argument("--formal-close-receipt", required=True, type=Path)
    dispose_parser.add_argument("--output", required=True, type=Path)
    dispose_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            result = preflight(project_root=args.project_root, python_path=args.python_path, config_path=args.config, output=args.output)
            print(json.dumps(result, sort_keys=True))
            return 0
        exit_code, result = dispose(project_root=args.project_root, plan_path=args.plan, formal_close_receipt_path=args.formal_close_receipt, output=args.output, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        return exit_code
    except (OSError, CloseoutError) as exc:
        print(f"Publisher closeout error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
