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
CLEANUP_LIST_KEYS = (
    "worktrees",
    "local_refs",
    "remote_refs",
    "evidence_roots",
    "cache_roots",
    "temp_roots",
    "deploy_temps",
    "historical_residuals",
)
PATH_CLEANUP_KINDS = {
    "evidence_roots": "evidence_root",
    "cache_roots": "cache_root",
    "temp_roots": "temp_root",
    "deploy_temps": "deploy_temp",
    "historical_residuals": "historical_residual",
}
PROTECTED_MANAGED_COMPONENTS = frozenset(
    {
        "campaigns",
        "campaign",
        "data",
        "database",
        "databases",
        "sqlite",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "key",
        "keys",
        "vault",
    }
)


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


def _is_reparse_stat(path: Path, metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def assert_literal_ancestry(path: Path, *, label: str) -> None:
    """Refuse a literal path when it or an existing literal ancestor is a reparse.

    This deliberately walks lexical ancestors with ``lstat``.  It must run before
    any resolution, containment comparison, fingerprinting, or deletion so a
    junction cannot redirect a supposedly managed cleanup target.
    """
    current = path
    while True:
        metadata = _lstat_or_none(current)
        if metadata is not None and _is_reparse_stat(current, metadata):
            raise CloseoutError(f"{label} contains a reparse path: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def literal_project_root(value: Path) -> Path:
    root = Path(os.path.abspath(os.fspath(value)))
    assert_literal_ancestry(root, label="project root")
    if not _path_exists_without_following(root) or not root.is_dir() or is_reparse(root):
        raise CloseoutError("project root must be an existing normal non-reparse directory")
    return root


def resolve_from_root(root: Path, value: object, *, label: str) -> Path:
    """Return a lexical absolute path only after no-follow ancestry proof.

    ``Path.resolve`` is intentionally not used for submitted cleanup paths: it
    would follow a junction before the caller had an opportunity to reject it.
    Dot segments are refused for the same reason.
    """
    if not isinstance(value, str) or not value:
        raise CloseoutError(f"{label} must be a non-empty path string")
    supplied = Path(value)
    if any(part in {".", ".."} for part in supplied.parts):
        raise CloseoutError(f"{label} must not contain dot path segments")
    path = supplied if supplied.is_absolute() else root / supplied
    lexical = Path(os.path.abspath(os.fspath(path)))
    assert_literal_ancestry(lexical, label=label)
    return lexical


def relative_label(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def is_reparse(path: Path) -> bool:
    metadata = _lstat_or_none(path)
    return metadata is not None and _is_reparse_stat(path, metadata)


def literal_child(path: Path, root: Path) -> bool:
    """Containment without accepting the root itself or following a reparse point."""
    try:
        return path.relative_to(root) != Path(".")
    except ValueError:
        return False


def same_or_literal_ancestor(ancestor: Path, path: Path) -> bool:
    return ancestor == path or literal_child(path, ancestor)


def _path_exists_without_following(path: Path) -> bool:
    return _lstat_or_none(path) is not None


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
    path = Path(os.path.abspath(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")))
    assert_literal_ancestry(path, label="repository common directory")
    return path


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
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    resolved = resolve_from_root(root, str(output), label="Publisher output")
    if not literal_child(resolved, local_root):
        raise CloseoutError("Publisher output must be an exact directory inside repository .local")
    if _path_exists_without_following(resolved) and (not resolved.is_dir() or is_reparse(resolved)):
        raise CloseoutError("Publisher output must be a normal non-reparse directory")
    resolved.mkdir(parents=True, exist_ok=True)
    assert_literal_ancestry(resolved, label="Publisher output")
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
    assert_literal_ancestry(path, label="cleanup path")
    if not _path_exists_without_following(path):
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


def _managed_roots(
    root: Path, config: dict[str, Any], protected_controls: set[Path]
) -> list[Path]:
    raw = config.get("managed_roots")
    if not isinstance(raw, list) or not raw:
        raise CloseoutError("candidate config requires a non-empty managed_roots list")
    roots = [resolve_from_root(root, value, label="managed_roots entry") for value in raw]
    if len({str(path) for path in roots}) != len(roots):
        raise CloseoutError("managed_roots contains duplicates")
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    for path in roots:
        if (
            not _path_exists_without_following(path)
            or not path.is_dir()
            or is_reparse(path)
            or not literal_child(path, local_root)
        ):
            raise CloseoutError("each managed root must be an existing normal directory")
        if any(same_or_literal_ancestor(path, control) for control in protected_controls):
            raise CloseoutError("managed root contains a canonical lifecycle/anchor control")
        relative_parts = [part.casefold() for part in path.relative_to(root).parts]
        if any(part in PROTECTED_MANAGED_COMPONENTS for part in relative_parts):
            raise CloseoutError("managed root is a protected data or secret location")
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


def _cleanup_lists(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    cleanup = config.get("cleanup")
    if not isinstance(cleanup, dict):
        raise CloseoutError("candidate config requires cleanup object")
    result: dict[str, list[dict[str, Any]]] = {}
    for key in CLEANUP_LIST_KEYS:
        raw = cleanup.get(key)
        if not isinstance(raw, list):
            raise CloseoutError(f"cleanup.{key} must be a present array in the sealed inventory")
        if not all(isinstance(item, dict) for item in raw):
            raise CloseoutError(f"cleanup.{key} entries must be objects")
        result[key] = raw
    return result


def _declared_cleanup_paths(
    root: Path, cleanup: dict[str, list[dict[str, Any]]]
) -> set[Path]:
    paths: set[Path] = set()
    for key in PATH_CLEANUP_KINDS:
        for source in cleanup[key]:
            paths.add(resolve_from_root(root, source.get("path"), label=f"cleanup.{key} path"))
    return paths


def _scan_phase_owned_paths(roots: Sequence[Path], markers: Sequence[str]) -> list[Path]:
    """Exhaustively find top-level phase-marked children without traversing aliases."""
    discovered: list[Path] = []
    for root in roots:
        assert_literal_ancestry(root, label="managed root scan")
        pending = [root]
        while pending:
            directory = pending.pop()
            for child in sorted(directory.iterdir(), key=lambda entry: entry.name.casefold()):
                assert_literal_ancestry(child, label="managed root scan")
                if _matches_phase(relative_label(root, child), markers):
                    discovered.append(child)
                    continue
                if child.is_dir():
                    pending.append(child)
    return sorted(discovered, key=lambda item: str(item).casefold())


def _inventory_record(
    root: Path,
    cleanup: dict[str, list[dict[str, Any]]],
    managed_roots: Sequence[Path],
    markers: Sequence[str],
) -> dict[str, Any]:
    declared_paths = _declared_cleanup_paths(root, cleanup)
    discovered = _scan_phase_owned_paths(managed_roots, markers)
    omitted = [path for path in discovered if path not in declared_paths]
    if omitted:
        raise CloseoutError(
            "phase-marked path omitted from the sealed cleanup inventory: "
            + ", ".join(str(path) for path in omitted)
        )
    categories = {key: len(cleanup[key]) for key in CLEANUP_LIST_KEYS}
    core = {
        "schema_version": 1,
        "required_categories": list(CLEANUP_LIST_KEYS),
        "category_counts": categories,
        "declared_item_count": sum(categories.values()),
        "phase_owned_scan": {
            "paths": [relative_label(root, path) for path in discovered],
            "count": len(discovered),
        },
    }
    return {**core, "sha256": sha256_bytes(canonical_json_bytes(core))}


def _verify_inventory_record(root: Path, plan: dict[str, Any]) -> None:
    inventory = plan.get("cleanup_inventory")
    if not isinstance(inventory, dict):
        raise CloseoutError("sealed cleanup inventory is missing")
    claimed = inventory.get("sha256")
    unsealed = dict(inventory)
    unsealed.pop("sha256", None)
    if not isinstance(claimed, str) or claimed.upper() != sha256_bytes(canonical_json_bytes(unsealed)):
        raise CloseoutError("sealed cleanup inventory hash does not match its contents")
    if inventory.get("schema_version") != 1 or inventory.get("required_categories") != list(CLEANUP_LIST_KEYS):
        raise CloseoutError("sealed cleanup inventory schema is incomplete")
    counts = inventory.get("category_counts")
    if not isinstance(counts, dict) or any(not isinstance(counts.get(key), int) for key in CLEANUP_LIST_KEYS):
        raise CloseoutError("sealed cleanup inventory category counts are incomplete")
    if inventory.get("declared_item_count") != sum(counts[key] for key in CLEANUP_LIST_KEYS):
        raise CloseoutError("sealed cleanup inventory item count is inconsistent")
    kind_to_key = {
        "worktree": "worktrees",
        "local_ref": "local_refs",
        "remote_ref": "remote_refs",
        **{kind: key for key, kind in PATH_CLEANUP_KINDS.items()},
    }
    actual_counts = {key: 0 for key in CLEANUP_LIST_KEYS}
    for item in plan.get("items", []):
        key = kind_to_key.get(item.get("kind")) if isinstance(item, dict) else None
        if key is None:
            raise CloseoutError("sealed cleanup inventory contains an unsupported item")
        actual_counts[key] += 1
    if actual_counts != {key: counts[key] for key in CLEANUP_LIST_KEYS}:
        raise CloseoutError("sealed cleanup inventory counts do not match plan items")
    managed_roots = [resolve_from_root(root, value, label="sealed managed root") for value in plan.get("managed_roots", [])]
    if not managed_roots:
        raise CloseoutError("sealed cleanup inventory has no managed roots")
    controls = plan.get("canonical_controls")
    if not isinstance(controls, dict):
        raise CloseoutError("sealed cleanup inventory controls are missing")
    protected_controls = _protected_control_paths(root, controls)
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    for managed in managed_roots:
        assert_literal_ancestry(managed, label="sealed managed root")
        if (
            not _path_exists_without_following(managed)
            or not managed.is_dir()
            or is_reparse(managed)
            or not literal_child(managed, local_root)
        ):
            raise CloseoutError("sealed managed root is no longer an approved normal local root")
        relative_parts = [part.casefold() for part in managed.relative_to(root).parts]
        if any(part in PROTECTED_MANAGED_COMPONENTS for part in relative_parts):
            raise CloseoutError("sealed managed root is now a protected data or secret location")
        if any(same_or_literal_ancestor(managed, control) for control in protected_controls):
            raise CloseoutError("sealed managed root now contains a canonical control")
    markers = plan.get("census", {}).get("phase_markers")
    if not isinstance(markers, list) or not all(isinstance(marker, str) for marker in markers):
        raise CloseoutError("sealed cleanup inventory phase markers are missing")
    current_scan = [relative_label(root, path) for path in _scan_phase_owned_paths(managed_roots, markers)]
    scanned = inventory.get("phase_owned_scan")
    if not isinstance(scanned, dict) or scanned.get("paths") != current_scan or scanned.get("count") != len(current_scan):
        raise CloseoutError("phase-owned cleanup inventory drifted since plan sealing")
    declared_paths = {
        resolve_from_root(root, item.get("path"), label="sealed cleanup path")
        for item in plan.get("items", [])
        if isinstance(item, dict) and item.get("kind") in PATH_CLEANUP_KINDS.values()
    }
    if any(path not in declared_paths for path in _scan_phase_owned_paths(managed_roots, markers)):
        raise CloseoutError("phase-owned cleanup path is omitted at disposal time")


def _browser_record(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    browser = config.get("browser")
    if not isinstance(browser, dict) or browser.get("mode") not in {"publisher-attached", "parent-fallback"}:
        raise CloseoutError("candidate config requires a browser attachment or explicit parent-fallback declaration")
    if browser.get("mode") == "publisher-attached":
        attachment = browser.get("attachment")
        if not isinstance(attachment, str) or not attachment.strip():
            raise CloseoutError("publisher-attached browser requires named attachment evidence")
        return {"mode": "publisher-attached", "attachment": attachment}
    script = browser.get("script", browser.get("script_reference"))
    auditor_role = browser.get("auditing_role", browser.get("audit_role"))
    auditor_capability = browser.get("auditing_capability", browser.get("audit_capability"))
    if not all(isinstance(value, str) and value.strip() for value in (script, auditor_role, auditor_capability)):
        raise CloseoutError(
            "parent browser fallback requires a nonempty canonical script reference and named auditing role/capability"
        )
    script_path = resolve_from_root(root, script, label="parent browser fallback script")
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    if not literal_child(script_path, local_root) or not script_path.is_file() or is_reparse(script_path):
        raise CloseoutError("parent browser fallback script must be a canonical normal file inside .local")
    return {
        "mode": "parent-fallback",
        "script": {
            "path": relative_label(root, script_path),
            "sha256": sha256_path(script_path),
            "bytes": script_path.stat().st_size,
        },
        "auditing_role": auditor_role,
        "auditing_capability": auditor_capability,
    }


def build_disposal_plan(
    root: Path, config: dict[str, Any], *, accepted: str, tree: str, controls: dict[str, dict[str, Any]], cache_path: Path, export_path: Path, manifest_path: Path, config_path: Path | None = None
) -> dict[str, Any]:
    protected_controls = _protected_control_paths(root, controls)
    managed_roots = _managed_roots(root, config, protected_controls)
    cleanup = _cleanup_lists(config)
    target = config.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("ref"), str):
        raise CloseoutError("candidate config requires target.ref and target.expected_commit")
    if target.get("ref") != "main":
        raise CloseoutError("sealed automated disposal requires canonical target.ref main")
    expected_target = require_sha(target.get("expected_commit"), label="target.expected_commit")
    canonical_target = git(root, "rev-parse", "--verify", f"{target['ref']}^{{commit}}").lower()
    if canonical_target != expected_target:
        raise CloseoutError("target ref drifted before Publisher preflight")
    records = _worktree_records(root)
    by_path = {
        resolve_from_root(root, record["worktree"], label="registered worktree path"): record
        for record in records
        if "worktree" in record
    }
    common = git_path(root)
    raw_active_paths = config.get("active_owner_paths")
    if not isinstance(raw_active_paths, list) or not all(isinstance(value, str) for value in raw_active_paths):
        raise CloseoutError("candidate config active_owner_paths must be an array of paths")
    active_paths = {
        resolve_from_root(root, value, label="active_owner path") for value in raw_active_paths
    }
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
        and resolve_from_root(root, record["worktree"], label="registered worktree path") != root
        and _matches_phase(record.get("branch", ""), markers)
        and resolve_from_root(root, record["worktree"], label="registered worktree path") not in declared_worktrees
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
        if path == root or path in active_paths or path not in by_path:
            entry.update({"disposition": "REFUSED", "reason": "protected, active, or unregistered worktree"})
        elif not _matches_phase(by_path[path].get("branch", ""), markers):
            entry.update({"disposition": "REFUSED", "reason": "worktree branch lacks completed-phase ownership marker"})
        elif is_reparse(path) or git_path(path) != common:
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
                items.append(entry)
                continue
            if run_child(["git", "merge-base", "--is-ancestor", ref, canonical_target], cwd=root).returncode:
                entry.update({"disposition": "REFUSED", "reason": "local phase ref is not merged into canonical main"})
            elif int(git(root, "rev-list", "--count", f"{canonical_target}..{ref}")):
                entry.update({"disposition": "REFUSED", "reason": "local phase ref has unique commits"})
            else:
                entry.update({"disposition": "ELIGIBLE", "tip": tip})
        items.append(entry)

    for raw in cleanup.get("remote_refs", []):
        source = _phase_item(config, raw, kind="remote_refs")
        entry = item_base("remote_ref", source)
        entry.update({"ref": source.get("ref"), "disposition": "REFUSED", "reason": "remote transport is intentionally unsupported by this helper"})
        items.append(entry)

    for key, kind in PATH_CLEANUP_KINDS.items():
        for raw in cleanup.get(key, []):
            source = _phase_item(config, raw, kind=key)
            path = resolve_from_root(root, source.get("path"), label=f"cleanup.{key} path")
            entry = item_base(kind, source)
            entry["path"] = str(path)
            fingerprint = _path_fingerprint(path)
            entry["fingerprint"] = fingerprint
            protected = any(
                same_or_literal_ancestor(path, control) for control in protected_controls
            ) or not _inside_any(path, managed_roots)
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
        "browser": _browser_record(root, config),
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
            "active_owner_paths": [str(path) for path in sorted(active_paths, key=str)],
        },
        "cleanup_inventory": _inventory_record(root, cleanup, managed_roots, markers),
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
    root = literal_project_root(project_root)
    assert_explicit_python(python_path)
    config_path = resolve_from_root(root, str(config_path), label="Publisher candidate config path")
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    if not literal_child(config_path, local_root) or not config_path.is_file():
        raise CloseoutError("Publisher candidate config must be a normal ignored file inside .local")
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
    browser = _browser_record(root, config)
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


def remove_exact_tree(path: Path, *, managed_roots: Sequence[Path]) -> None:
    """Remove an exact, pre-audited normal tree without glob/force/rmtree APIs."""
    assert_literal_ancestry(path, label="exact removal path")
    if not _inside_any(path, managed_roots) or is_reparse(path):
        raise CloseoutError("refusing to remove unmanaged or reparse path")
    metadata = _lstat_or_none(path)
    if metadata is None:
        raise CloseoutError("refusing to remove absent path")
    if stat.S_ISREG(metadata.st_mode):
        path.unlink()
        return
    if not stat.S_ISDIR(metadata.st_mode):
        raise CloseoutError("refusing to remove non-file/non-directory path")
    for child in list(path.iterdir()):
        assert_literal_ancestry(child, label="exact removal descendant")
        child_metadata = _lstat_or_none(child)
        if child_metadata is None or _is_reparse_stat(child, child_metadata):
            raise CloseoutError("refusing to recurse through a reparse descendant")
        if stat.S_ISDIR(child_metadata.st_mode):
            remove_exact_tree(child, managed_roots=managed_roots)
        elif stat.S_ISREG(child_metadata.st_mode):
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
    literal = str(path).casefold()
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
    path = resolve_from_root(root, item.get("path"), label="plan-listed cleanup path")
    managed = [resolve_from_root(root, value, label="sealed managed root") for value in plan["managed_roots"]]
    controls = _protected_control_paths(root, plan["canonical_controls"])
    if (
        not _inside_any(path, managed)
        or is_reparse(path)
        or any(same_or_literal_ancestor(path, control) for control in controls)
    ):
        raise CloseoutError("plan-listed path no longer satisfies literal containment/non-reparse proof")
    current = _path_fingerprint(path)
    if current != item.get("fingerprint"):
        raise CloseoutError("plan-listed path drifted since preflight")
    return path


def _active_owner_paths(root: Path, plan: dict[str, Any]) -> set[Path]:
    census = plan.get("census")
    raw = census.get("active_owner_paths") if isinstance(census, dict) else None
    if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
        raise CloseoutError("sealed active ownership inventory is missing")
    return {resolve_from_root(root, value, label="sealed active-owner path") for value in raw}


def _revalidate_active_ownership(root: Path, plan: dict[str, Any]) -> set[Path]:
    """Re-read every sealed ownership path before an apply can mutate anything."""
    active_paths = _active_owner_paths(root, plan)
    for path in active_paths:
        assert_literal_ancestry(path, label="sealed active-owner path")
    return active_paths


def _revalidate_item(
    root: Path,
    plan: dict[str, Any],
    item: dict[str, Any],
    *,
    accepted: str,
    active_paths: set[Path],
    eligible_worktree_paths: set[Path],
) -> dict[str, Any]:
    """Return a mutation descriptor only after a complete current proof."""
    kind = item.get("kind")
    if kind == "worktree":
        path = resolve_from_root(root, item.get("path"), label="sealed worktree path")
        records = _worktree_records(root)
        by_path = {
            resolve_from_root(root, record["worktree"], label="registered worktree path"): record
            for record in records
            if "worktree" in record
        }
        record = by_path.get(path)
        if path == root or path in active_paths or record is None:
            raise CloseoutError("worktree is protected, active, or no longer registered")
        if record.get("branch") != item.get("branch") or record.get("HEAD") != item.get("head"):
            raise CloseoutError("worktree branch or HEAD drifted")
        if not _matches_phase(str(record.get("branch", "")), plan["census"]["phase_markers"]):
            raise CloseoutError("worktree no longer has completed-phase ownership")
        common = Path(
            git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        assert_literal_ancestry(common, label="worktree common directory")
        if is_reparse(path) or str(common) != str(item.get("common_dir")):
            raise CloseoutError("worktree common-dir/reparse proof failed")
        if git(path, "status", "--porcelain=v1", "--untracked-files=all"):
            raise CloseoutError("worktree became dirty")
        if int(git(path, "rev-list", "--count", f"{accepted}..HEAD")):
            raise CloseoutError("worktree has unique commits")
        return {"item": item, "path": path}
    if kind == "local_ref":
        ref = item.get("ref")
        if not isinstance(ref, str) or ref == "refs/heads/main" or not ref.startswith("refs/heads/"):
            raise CloseoutError("local phase ref is protected or malformed")
        if git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").lower() != item.get("tip"):
            raise CloseoutError("local phase ref drifted")
        if run_child(["git", "merge-base", "--is-ancestor", ref, accepted], cwd=root).returncode:
            raise CloseoutError("local phase ref is not merged into accepted main")
        if int(git(root, "rev-list", "--count", f"{accepted}..{ref}")):
            raise CloseoutError("local phase ref has unique commits")
        attached = {
            resolve_from_root(root, record["worktree"], label="registered worktree path")
            for record in _worktree_records(root)
            if record.get("branch") == ref and "worktree" in record
        }
        if attached - eligible_worktree_paths:
            raise CloseoutError("local phase ref remains attached outside the sealed worktree actions")
        return {"item": item, "ref": ref}
    if kind in PATH_CLEANUP_KINDS.values():
        path = _revalidate_path_item(root, plan, item)
        if kind == "historical_residual":
            registered = {
                resolve_from_root(root, record["worktree"], label="registered worktree path")
                for record in _worktree_records(root)
                if "worktree" in record
            }
            if path in registered or not no_active_process_at(path):
                raise CloseoutError("historical residual is registered or has no active-process proof")
        return {"item": item, "path": path}
    raise CloseoutError("unsupported sealed plan item")


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
    root = literal_project_root(project_root)
    plan_path = resolve_from_root(root, str(plan_path), label="sealed disposal plan path")
    formal_close_receipt_path = resolve_from_root(
        root, str(formal_close_receipt_path), label="formal-close receipt path"
    )
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    if (
        not literal_child(plan_path, local_root)
        or not literal_child(formal_close_receipt_path, local_root)
        or not plan_path.is_file()
        or not formal_close_receipt_path.is_file()
    ):
        raise CloseoutError("sealed plan and formal-close receipt must be normal ignored files inside .local")
    plan = read_json_utf8(plan_path, label="sealed disposal plan")
    receipt = read_json_utf8(formal_close_receipt_path, label="formal-close receipt")
    verify_sealed_plan(plan)
    verify_green_receipt(receipt, plan)
    output_root = _output_directory(root, output)
    accepted = plan["accepted_candidate"]["commit"]
    accepted_tree = plan["accepted_candidate"]["tree"]
    assert_clean_exact_checkout(root, accepted, accepted_tree)
    verify_bound_inputs(root, plan)
    _verify_inventory_record(root, plan)
    target = plan["target"]
    if git(root, "rev-parse", "--verify", f"{target['ref']}^{{commit}}").lower() != accepted:
        raise CloseoutError("target ref is not the accepted candidate at disposal time")
    items = plan.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise CloseoutError("sealed plan items are malformed")
    active_paths = _revalidate_active_ownership(root, plan)
    eligible_worktree_paths = {
        resolve_from_root(root, item.get("path"), label="sealed worktree path")
        for item in items
        if item.get("kind") == "worktree" and item.get("disposition") == "ELIGIBLE"
    }
    disposition_rows: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for item in items:
        row = {"id": item.get("id"), "kind": item.get("kind"), "status": "PLANNED"}
        if item.get("disposition") != "ELIGIBLE":
            row.update({"status": "REFUSED", "reason": item.get("reason", "not eligible")})
            disposition_rows.append(row)
            continue
        try:
            actions.append(
                _revalidate_item(
                    root,
                    plan,
                    item,
                    accepted=accepted,
                    active_paths=active_paths,
                    eligible_worktree_paths=eligible_worktree_paths,
                )
            )
        except (OSError, CloseoutError) as exc:
            row.update({"status": "REFUSED", "reason": str(exc)})
        disposition_rows.append(row)
    refused = any(row["status"] == "REFUSED" for row in disposition_rows)
    if apply and refused:
        for row in disposition_rows:
            if row["status"] == "PLANNED":
                row.update(
                    {
                        "status": "NOT_APPLIED",
                        "reason": "another sealed item was refused; apply transaction aborted before mutation",
                    }
                )
    elif apply:
        action_by_id = {action["item"]["id"]: action for action in actions}
        managed_roots = [resolve_from_root(root, value, label="sealed managed root") for value in plan["managed_roots"]]
        priority = {"worktree": 0, "local_ref": 1, "evidence_root": 2, "cache_root": 2, "temp_root": 2, "deploy_temp": 2, "historical_residual": 2}
        stopped = False
        for row in sorted(disposition_rows, key=lambda value: priority.get(str(value["kind"]), 99)):
            if stopped or row["status"] != "PLANNED":
                if stopped and row["status"] == "PLANNED":
                    row.update({"status": "NOT_APPLIED", "reason": "a prior exact removal failed"})
                continue
            action = action_by_id[str(row["id"])]
            item = action["item"]
            try:
                if item["kind"] == "worktree":
                    path = action["path"]
                    completed = run_child(["git", "worktree", "remove", "--", str(path)], cwd=root)
                    if completed.returncode or _path_exists_without_following(path):
                        raise CloseoutError("non-force git worktree remove failed")
                elif item["kind"] == "local_ref":
                    ref = action["ref"]
                    if _ref_has_worktree(root, ref):
                        raise CloseoutError("local phase ref remains attached to a worktree")
                    completed = run_child(["git", "branch", "-d", "--", ref.removeprefix("refs/heads/")], cwd=root)
                    if completed.returncode or not run_child(["git", "show-ref", "--verify", "--quiet", ref], cwd=root).returncode:
                        raise CloseoutError("non-force local branch deletion failed")
                else:
                    path = action["path"]
                    remove_exact_tree(path, managed_roots=managed_roots)
                    if _path_exists_without_following(path):
                        raise CloseoutError("exact managed path remained after removal")
                row["status"] = "REMOVED"
            except (OSError, CloseoutError) as exc:
                row.update({"status": "FAILED", "reason": str(exc)})
                stopped = True
    failed = any(row["status"] in {"REFUSED", "FAILED", "NOT_APPLIED"} for row in disposition_rows)
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
