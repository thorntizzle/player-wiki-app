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
import importlib.util
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
REPARSE_UNLINK_KINDS = frozenset({"directory-reparse", "symlink"})
WINDOWS_ATTRIBUTE_NORMALIZATION = "clear-readonly-hidden-system"
WINDOWS_CLEARABLE_ATTRIBUTES = (
    ("readonly", getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x00000001)),
    ("hidden", getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x00000002)),
    ("system", getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0x00000004)),
)
WINDOWS_CLEARABLE_ATTRIBUTE_MASK = sum(mask for _, mask in WINDOWS_CLEARABLE_ATTRIBUTES)
GLOB_CHARACTERS = frozenset("*?[]{}")
PUBLISHER_EVIDENCE_SCHEMA = "campaign-player-wiki.publisher-closeout"
BROWSER_CAPABILITY_SCHEMA = "campaign-player-wiki.browser-capability"
PUBLISHER_FOCUSED_PLUGIN_ENV = "PLAYER_WIKI_PUBLISHER_FOCUSED_PLUGIN"
PUBLISHER_FOCUSED_OBSERVER_ENV = "PLAYER_WIKI_PUBLISHER_FOCUSED_OBSERVER"
PUBLISHER_FOCUSED_PROOF_ENV = "PLAYER_WIKI_PUBLISHER_FOCUSED_PROOF_SHA256"
PUBLISHER_FOCUSED_PROOF_PATH_ENV = "PLAYER_WIKI_PUBLISHER_FOCUSED_PROOF_PATH"
VALIDATION_LOCK_PATH_ENV = "PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_PATH"
VALIDATION_LOCK_TOKEN_ENV = "PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_TOKEN"
FOCUSED_STATE_SEQUENCE = (
    "ABSENT",
    "PROVED",
    "SENTINEL_CREATED",
    "PYTEST_CHILD_STARTED",
    "CHILD_RESULT_RETAINED",
    "PASS",
    "RECOVERING",
)
FOCUSED_INVOCATION_CONTRACT = {
    "max_invocations": 1,
    "retry": False,
    "non_pty": True,
}
BROWSER_CAPABILITIES = frozenset(
    {"navigation", "evaluation", "fetch", "independent_get", "auth_session"}
)
BROWSER_EVIDENCE_MODES = frozenset({"browser", "GET_ONLY", "split"})
FORBIDDEN_EVIDENCE_FIELD = re.compile(
    r"(?:^|_)(?:secret|secrets|password|passwords|credential|credentials|"
    r"token|tokens|private)(?:_|$)",
    re.IGNORECASE,
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


def reject_private_evidence_fields(value: Any, *, location: str = "$") -> None:
    """Refuse fields that could turn a retained receipt into a secret carrier."""
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise CloseoutError(f"{location} contains a non-string field name")
            if FORBIDDEN_EVIDENCE_FIELD.search(key):
                raise CloseoutError(
                    f"{location} contains forbidden private field name: {key}"
                )
            reject_private_evidence_fields(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_private_evidence_fields(child, location=f"{location}[{index}]")


def seal_publisher_receipt(core: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical self-hashed local evidence receipt."""
    reject_private_evidence_fields(core)
    return {
        **core,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(core)),
    }


def verify_publisher_receipt(
    value: Any,
    *,
    expected_schema: str,
    expected_kind: str,
) -> dict[str, Any]:
    """Verify a closeout-owned receipt without accepting alternate schemas."""
    if not isinstance(value, dict):
        raise CloseoutError(f"{expected_kind} receipt must be an object")
    reject_private_evidence_fields(value)
    if (
        value.get("schema") != expected_schema
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("kind") != expected_kind
    ):
        raise CloseoutError(f"{expected_kind} receipt schema is unsupported")
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str) or re.fullmatch(
        r"[0-9A-Fa-f]{64}", claimed
    ) is None:
        raise CloseoutError(f"{expected_kind} receipt hash is missing")
    core = {key: item for key, item in value.items() if key != "receipt_sha256"}
    if sha256_bytes(canonical_json_bytes(core)) != claimed.upper():
        raise CloseoutError(
            f"{expected_kind} receipt hash does not match canonical content"
        )
    return value


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


def _reparse_leaf_kind(path: Path, metadata: os.stat_result) -> str | None:
    """Classify a reparse leaf solely from no-follow metadata.

    A symbolic link is removed with ``unlink``.  A directory reparse point
    (including a Windows junction) is removed with non-recursive ``rmdir``.
    Other reparse types are intentionally unsupported.
    """
    if not _is_reparse_stat(path, metadata):
        return None
    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory-reparse"
    return None


def _strict_relative_child_parts(value: object, *, label: str) -> tuple[str, tuple[str, ...]]:
    """Parse an immutable lexical child path without normalizing or resolving it."""
    if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
        raise CloseoutError(f"{label} must be a non-empty normalized relative path")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        raise CloseoutError(f"{label} must be relative")
    parts = tuple(re.split(r"[\\\\/]", value))
    if (
        not parts
        or any(not part or part in {".", ".."} or ":" in part for part in parts)
        or any(any(character in GLOB_CHARACTERS for character in part) for part in parts)
    ):
        raise CloseoutError(f"{label} must not contain empty, dot, or glob path segments")
    return "/".join(parts), parts


def _literal_child_from_parts(root: Path, parts: Sequence[str]) -> Path:
    """Build a child path lexically; callers must never resolve the result."""
    return Path(os.path.abspath(os.fspath(root.joinpath(*parts))))


def _assert_normal_child_ancestors(root: Path, leaf: Path, *, label: str) -> None:
    """Require every ancestor through ``root`` to be a present normal directory.

    The leaf itself is deliberately not inspected here because the one approved
    leaf may be a reparse point.  This is the only link-specific exception.
    """
    if not literal_child(leaf, root):
        raise CloseoutError(f"{label} must be a child of its historical residual")
    current = leaf.parent
    while True:
        metadata = _lstat_or_none(current)
        if metadata is None or _is_reparse_stat(current, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise CloseoutError(f"{label} has a missing, non-directory, or reparse ancestor")
        if current == root:
            return
        current = current.parent


def _parse_reparse_unlink_entries(
    root: Path, raw: object, *, label: str
) -> list[dict[str, str]]:
    """Validate optional, literal link-only cleanup entries in deterministic order."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise CloseoutError(f"{label} must be an array when present")
    entries: list[dict[str, str]] = []
    names: set[str] = set()
    for index, value in enumerate(raw):
        entry_label = f"{label}[{index}]"
        if not isinstance(value, dict) or set(value) != {"relative_path", "kind"}:
            raise CloseoutError(f"{entry_label} must contain only relative_path and kind")
        relative_path, parts = _strict_relative_child_parts(
            value.get("relative_path"), label=f"{entry_label}.relative_path"
        )
        kind = value.get("kind")
        if kind not in REPARSE_UNLINK_KINDS:
            raise CloseoutError(f"{entry_label}.kind is unsupported")
        if relative_path in names:
            raise CloseoutError(f"{label} contains duplicate relative_path entries")
        names.add(relative_path)
        leaf = _literal_child_from_parts(root, parts)
        _assert_normal_child_ancestors(root, leaf, label=entry_label)
        entries.append({"relative_path": relative_path, "kind": kind})
    return sorted(entries, key=lambda item: item["relative_path"])


def _historical_cleanup_options(
    residual: Path, source: dict[str, Any], *, label: str
) -> dict[str, Any]:
    """Return the only optional mechanics permitted for a historical residual."""
    links = _parse_reparse_unlink_entries(
        residual, source.get("unlink_only_reparse"), label=f"{label}.unlink_only_reparse"
    )
    normalization = source.get("windows_attribute_normalization")
    if normalization is not None and normalization != WINDOWS_ATTRIBUTE_NORMALIZATION:
        raise CloseoutError(
            f"{label}.windows_attribute_normalization must be {WINDOWS_ATTRIBUTE_NORMALIZATION!r}"
        )
    result: dict[str, Any] = {}
    if links:
        result["unlink_only_reparse"] = links
    if normalization is not None:
        result["windows_attribute_normalization"] = normalization
    return result


def _validate_historical_cleanup_option_schema(source: dict[str, Any], *, label: str) -> None:
    """Reject malformed optional cleanup mechanics before planning any disposal."""
    if "unlink_only_reparse" in source:
        raw = source["unlink_only_reparse"]
        if not isinstance(raw, list):
            raise CloseoutError(f"{label}.unlink_only_reparse must be an array")
        names: set[str] = set()
        for index, value in enumerate(raw):
            entry_label = f"{label}.unlink_only_reparse[{index}]"
            if not isinstance(value, dict) or set(value) != {"relative_path", "kind"}:
                raise CloseoutError(f"{entry_label} must contain only relative_path and kind")
            relative_path, _ = _strict_relative_child_parts(
                value.get("relative_path"), label=f"{entry_label}.relative_path"
            )
            if value.get("kind") not in REPARSE_UNLINK_KINDS:
                raise CloseoutError(f"{entry_label}.kind is unsupported")
            if relative_path in names:
                raise CloseoutError(f"{label}.unlink_only_reparse contains duplicate relative_path entries")
            names.add(relative_path)
    if "windows_attribute_normalization" in source and (
        source["windows_attribute_normalization"] != WINDOWS_ATTRIBUTE_NORMALIZATION
    ):
        raise CloseoutError(
            f"{label}.windows_attribute_normalization must be {WINDOWS_ATTRIBUTE_NORMALIZATION!r}"
        )


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


def _path_fingerprint(
    path: Path, *, allowed_reparse: Sequence[dict[str, str]] = ()
) -> dict[str, Any]:
    """Fingerprint a normal path while preserving listed link leaves as opaque.

    The caller supplies only normalized, plan-bound link records.  We lstat
    each child and never inspect a listed reparse target; an unlisted, missing,
    type-changed, or ancestor reparse makes the fingerprint unsafe.
    """
    assert_literal_ancestry(path, label="cleanup path")
    if not _path_exists_without_following(path):
        return {"exists": False}
    if is_reparse(path):
        return {"exists": True, "unsafe_reparse": True}
    metadata = _lstat_or_none(path)
    if metadata is None:
        return {"exists": False}
    if stat.S_ISREG(metadata.st_mode):
        return {"exists": True, "kind": "file", "bytes": path.stat().st_size, "sha256": sha256_path(path)}
    if not stat.S_ISDIR(metadata.st_mode):
        return {"exists": True, "kind": "other"}
    expected = {
        str(item.get("relative_path")): str(item.get("kind"))
        for item in allowed_reparse
    }
    if len(expected) != len(allowed_reparse) or any(
        kind not in REPARSE_UNLINK_KINDS for kind in expected.values()
    ):
        raise CloseoutError("allowed reparse fingerprint entries are malformed")
    entries: list[dict[str, Any]] = []
    observed: set[str] = set()
    unsafe_reparse = False
    pending = [path]
    while pending:
        directory = pending.pop()
        for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
            relative = child.relative_to(path).as_posix()
            child_metadata = _lstat_or_none(child)
            if child_metadata is None:
                raise CloseoutError("cleanup path changed while its fingerprint was collected")
            if _is_reparse_stat(child, child_metadata):
                kind = _reparse_leaf_kind(child, child_metadata)
                entries.append({"path": relative, "kind": "reparse", "reparse_kind": kind})
                if expected.get(relative) != kind:
                    unsafe_reparse = True
                else:
                    observed.add(relative)
                continue
            if stat.S_ISDIR(child_metadata.st_mode):
                entries.append({"path": relative, "kind": "directory"})
                pending.append(child)
            elif stat.S_ISREG(child_metadata.st_mode):
                entries.append({"path": relative, "kind": "file", "bytes": child.stat().st_size, "sha256": sha256_path(child)})
            else:
                entries.append({"path": relative, "kind": "other"})
    payload = canonical_json_bytes(entries)
    return {
        "exists": True,
        "kind": "directory",
        "entry_count": len(entries),
        "sha256": sha256_bytes(payload),
        "allowed_reparse": [
            {"relative_path": relative, "kind": expected[relative]}
            for relative in sorted(expected)
        ],
        "unsafe_reparse": unsafe_reparse or observed != set(expected),
    }


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


def _literal_ancestors(path: Path) -> Iterable[Path]:
    """Yield lexical ancestors without resolving or traversing the filesystem."""
    current = path
    while True:
        yield current
        parent = current.parent
        if parent == current:
            return
        current = parent


def _path_cleanup_refusal_reason(
    root: Path,
    path: Path,
    managed_roots: Iterable[Path],
    protected_controls: Iterable[Path],
) -> str | None:
    """Classify a path-only cleanup item before any content-derived operation.

    This intentionally uses only lexical relationships and no-follow metadata.
    In particular, a declared data, secret, or canonical-control path must be
    refused without fingerprinting it: a fingerprint would read and retain
    information the sealed disposal policy is required to leave untouched.
    """
    assert_literal_ancestry(path, label="cleanup path")
    if any(is_reparse(ancestor) for ancestor in _literal_ancestors(path)):
        return "path contains a reparse point"
    try:
        relative_parts = [part.casefold() for part in path.relative_to(root).parts]
    except ValueError:
        relative_parts = []
    if any(part in PROTECTED_MANAGED_COMPONENTS for part in relative_parts):
        return "protected data or secret path"
    for control in protected_controls:
        if same_or_literal_ancestor(control, path) or same_or_literal_ancestor(path, control):
            return "canonical control path"
    if not _inside_any(path, managed_roots):
        return "path outside declared managed roots"
    return None


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
    unexpected_cleanup_keys = set(cleanup).difference(CLEANUP_LIST_KEYS)
    if unexpected_cleanup_keys:
        raise CloseoutError(
            "candidate config cleanup has unsupported keys: "
            + ", ".join(sorted(unexpected_cleanup_keys))
        )
    result: dict[str, list[dict[str, Any]]] = {}
    for key in CLEANUP_LIST_KEYS:
        raw = cleanup.get(key)
        if not isinstance(raw, list):
            raise CloseoutError(f"cleanup.{key} must be a present array in the sealed inventory")
        if not all(isinstance(item, dict) for item in raw):
            raise CloseoutError(f"cleanup.{key} entries must be objects")
        for index, item in enumerate(raw):
            label = f"cleanup.{key}[{index}]"
            if key in {"worktrees"}:
                allowed_keys = {"phase", "path"}
            elif key in {"local_refs", "remote_refs"}:
                allowed_keys = {"phase", "ref"}
            else:
                allowed_keys = {
                    "phase", "path", "evidence_summary_recorded", "no_unique_evidence"
                }
                if key == "historical_residuals":
                    allowed_keys.update(
                        {"unlink_only_reparse", "windows_attribute_normalization"}
                    )
            if set(item).difference(allowed_keys):
                raise CloseoutError(f"{label} has unsupported keys")
            option_keys = {"unlink_only_reparse", "windows_attribute_normalization"}
            if key != "historical_residuals" and option_keys.intersection(item):
                raise CloseoutError(
                    "link-only and Windows attribute cleanup options are permitted only on "
                    "cleanup.historical_residuals entries"
                )
            if key == "historical_residuals":
                _validate_historical_cleanup_option_schema(item, label=label)
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
                metadata = _lstat_or_none(child)
                if metadata is None:
                    raise CloseoutError("managed root changed while phase ownership was scanned")
                if _is_reparse_stat(child, metadata):
                    if _matches_phase(relative_label(root, child), markers):
                        discovered.append(child)
                    continue
                if _matches_phase(relative_label(root, child), markers):
                    discovered.append(child)
                    continue
                if stat.S_ISDIR(metadata.st_mode):
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


def _normalized_evidence_name(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", value) is None
    ):
        raise CloseoutError(f"{label} must be a normalized non-private identifier")
    return value


def read_json_value_utf8(path: Path, *, label: str) -> Any:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw:
        raise CloseoutError(f"{label} must be canonical UTF-8 JSON, not UTF-16/binary")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"{label} is not canonical UTF-8 JSON: {exc}") from exc


def _contained_local_evidence_file(
    root: Path,
    value: object,
    *,
    label: str,
    allow_absolute: bool = False,
) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or (Path(value).is_absolute() and not allow_absolute)
    ):
        raise CloseoutError(f"{label} must be a repository-relative path")
    path = resolve_from_root(root, value, label=label)
    local_root = resolve_from_root(root, ".local", label="repository .local root")
    if (
        not literal_child(path, local_root)
        or not path.is_file()
        or is_reparse(path)
    ):
        raise CloseoutError(
            f"{label} must be a contained normal file inside repository .local"
        )
    return path


def _normalize_browser_assertions(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "required",
        "browser",
        "independent_get",
        "requirements",
    }:
        raise CloseoutError(
            "browser assertions must contain required, browser, independent_get, and requirements"
        )
    normalized: dict[str, list[str]] = {}
    for key in ("required", "browser", "independent_get"):
        raw = value.get(key)
        if not isinstance(raw, list):
            raise CloseoutError(f"browser assertions.{key} must be an array")
        items = [
            _normalized_evidence_name(item, label=f"browser assertions.{key}")
            for item in raw
        ]
        if len(items) != len(set(items)):
            raise CloseoutError(f"browser assertions.{key} contains duplicates")
        normalized[key] = items
    requirements = value.get("requirements")
    if (
        not isinstance(requirements, dict)
        or set(requirements) != set(normalized["required"])
    ):
        raise CloseoutError(
            "browser assertion requirements must name every required assertion exactly"
        )
    normalized_requirements: dict[str, str] = {}
    for assertion, capability in requirements.items():
        if capability not in BROWSER_CAPABILITIES:
            raise CloseoutError(
                f"browser assertion {assertion!r} requires an unsupported capability"
            )
        normalized_requirements[assertion] = capability
    browser_set = set(normalized["browser"])
    get_set = set(normalized["independent_get"])
    required_set = set(normalized["required"])
    if browser_set & get_set:
        raise CloseoutError("browser assertion partitions overlap")
    if browser_set | get_set != required_set:
        raise CloseoutError("browser assertion partitions have a gap")
    return {
        **normalized,
        "requirements": normalized_requirements,
    }


def _normalize_browser_requirements(value: object) -> dict[str, Any]:
    """Normalize formal Browser/GET requirements without trusting a receipt."""
    if not isinstance(value, dict) or set(value) != {
        "required_evidence_mode",
        "assertions",
    }:
        raise CloseoutError(
            "browser requirements must contain required_evidence_mode and assertions"
        )
    mode = value.get("required_evidence_mode")
    if mode not in BROWSER_EVIDENCE_MODES:
        raise CloseoutError("required browser evidence mode is unsupported")
    assertions = _normalize_browser_assertions(value.get("assertions"))
    if mode == "browser" and (
        not assertions["browser"] or assertions["independent_get"]
    ):
        raise CloseoutError("browser evidence requirements need a browser-only partition")
    if mode == "GET_ONLY" and (
        assertions["browser"] or not assertions["independent_get"]
    ):
        raise CloseoutError("GET_ONLY evidence requirements need a GET-only partition")
    if mode == "split" and (
        not assertions["browser"] or not assertions["independent_get"]
    ):
        raise CloseoutError("split evidence requirements need both partitions")
    return {
        "required_evidence_mode": mode,
        "assertions": assertions,
    }


def _receipt_satisfies_browser_requirements(
    receipt: dict[str, Any], requirements: dict[str, Any]
) -> None:
    normalized = _normalize_browser_requirements(requirements)
    if (
        receipt.get("required_evidence_mode")
        != normalized["required_evidence_mode"]
        or receipt.get("selected_evidence_mode")
        != normalized["required_evidence_mode"]
        or receipt.get("assertions") != normalized["assertions"]
    ):
        raise CloseoutError(
            "Browser capability receipt does not satisfy the independent evidence requirements"
        )


def _normalize_browser_capability_payload(
    root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    """Normalize one task-local Browser/GET evidence capability claim."""
    reject_private_evidence_fields(payload)
    if not isinstance(payload, dict) or set(payload) != {
        "task_id",
        "accepted_candidate",
        "ownership",
        "capabilities",
        "required_evidence_mode",
        "selected_evidence_mode",
        "assertions",
    }:
        raise CloseoutError("browser capability payload fields are incomplete")
    task_id = _normalized_evidence_name(payload["task_id"], label="browser task_id")
    candidate = payload["accepted_candidate"]
    if not isinstance(candidate, dict) or set(candidate) != {"commit", "tree"}:
        raise CloseoutError("browser accepted_candidate must contain commit and tree")
    accepted_candidate = {
        "commit": require_sha(candidate.get("commit"), label="browser candidate commit"),
        "tree": require_sha(candidate.get("tree"), label="browser candidate tree"),
    }
    ownership = payload["ownership"]
    if not isinstance(ownership, dict):
        raise CloseoutError("browser ownership must be an object")
    mode = ownership.get("mode")
    if mode == "publisher-attached":
        if set(ownership) != {
            "mode",
            "attachment_id",
            "controlled_tab_id",
            "exclusive",
        }:
            raise CloseoutError("attached browser ownership fields are incomplete")
        if ownership.get("exclusive") is not True:
            raise CloseoutError("attached browser ownership must prove one exclusive tab")
        normalized_ownership = {
            "mode": mode,
            "attachment_id": _normalized_evidence_name(
                ownership.get("attachment_id"), label="browser attachment_id"
            ),
            "controlled_tab_id": _normalized_evidence_name(
                ownership.get("controlled_tab_id"), label="browser controlled_tab_id"
            ),
            "exclusive": True,
        }
    elif mode == "parent-fallback":
        if set(ownership) != {
            "mode",
            "operator_task_id",
            "script",
            "auditor",
        }:
            raise CloseoutError("parent browser fallback ownership fields are incomplete")
        script_path = _contained_local_evidence_file(
            root, ownership.get("script"), label="parent browser fallback script"
        )
        auditor = ownership.get("auditor")
        if (
            not isinstance(auditor, dict)
            or set(auditor) != {"role", "task_id", "independent"}
            or auditor.get("independent") is not True
        ):
            raise CloseoutError(
                "parent browser fallback requires a named independent auditor"
            )
        operator_task_id = _normalized_evidence_name(
            ownership.get("operator_task_id"),
            label="parent browser operator_task_id",
        )
        auditor_task_id = _normalized_evidence_name(
            auditor.get("task_id"), label="parent browser auditor task_id"
        )
        if len({task_id, operator_task_id, auditor_task_id}) != 3:
            raise CloseoutError(
                "parent browser fallback tasks must have independent identities"
            )
        normalized_ownership = {
            "mode": mode,
            "operator_task_id": operator_task_id,
            "script": {
                "path": relative_label(root, script_path),
                "sha256": sha256_path(script_path),
                "bytes": script_path.stat().st_size,
            },
            "auditor": {
                "role": _normalized_evidence_name(
                    auditor.get("role"), label="parent browser auditor role"
                ),
                "task_id": auditor_task_id,
                "independent": True,
            },
        }
    else:
        raise CloseoutError(
            "browser ownership must be publisher-attached or parent-fallback"
        )
    capabilities = payload["capabilities"]
    if (
        not isinstance(capabilities, dict)
        or set(capabilities) != BROWSER_CAPABILITIES
        or not all(isinstance(value, bool) for value in capabilities.values())
    ):
        raise CloseoutError(
            "browser capabilities must contain the five declared boolean capabilities"
        )
    required_mode = payload["required_evidence_mode"]
    selected_mode = payload["selected_evidence_mode"]
    if required_mode not in BROWSER_EVIDENCE_MODES:
        raise CloseoutError("required browser evidence mode is unsupported")
    if selected_mode != required_mode:
        raise CloseoutError("browser evidence mode was silently downgraded")
    assertions = _normalize_browser_assertions(payload["assertions"])
    browser_assertions = assertions["browser"]
    get_assertions = assertions["independent_get"]
    browser_set = set(browser_assertions)
    get_set = set(get_assertions)
    if selected_mode == "browser" and (
        not browser_assertions or get_assertions
    ):
        raise CloseoutError("browser evidence mode requires a browser-only partition")
    if selected_mode == "GET_ONLY" and (
        browser_assertions or not get_assertions
    ):
        raise CloseoutError("GET_ONLY evidence mode requires a GET-only partition")
    if selected_mode == "split" and (
        not browser_assertions or not get_assertions
    ):
        raise CloseoutError("split evidence mode requires both assertion partitions")
    if browser_assertions and not capabilities["navigation"]:
        raise CloseoutError("browser assertions require navigation capability")
    if get_assertions and not capabilities["independent_get"]:
        raise CloseoutError(
            "independent GET assertions require independent_get capability"
        )
    for assertion, capability in assertions["requirements"].items():
        if (
            capability in {"navigation", "evaluation", "fetch"}
            and assertion not in browser_set
        ) or (
            capability == "independent_get" and assertion not in get_set
        ):
            raise CloseoutError(
                f"browser assertion {assertion!r} is in the wrong evidence partition"
            )
        if not capabilities[capability]:
            raise CloseoutError(
                f"browser assertion {assertion!r} is unsupported by capability {capability}"
            )
    core = {
        "schema": BROWSER_CAPABILITY_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-browser-capability",
        "task_id": task_id,
        "accepted_candidate": accepted_candidate,
        "ownership": normalized_ownership,
        "capabilities": dict(capabilities),
        "required_evidence_mode": required_mode,
        "selected_evidence_mode": selected_mode,
        "assertions": assertions,
    }
    return core


def build_browser_capability_receipt(
    root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    """Normalize and seal one task-local Browser/GET evidence capability claim."""
    return seal_publisher_receipt(
        _normalize_browser_capability_payload(root, payload)
    )


def verify_browser_capability_receipt(
    root: Path,
    value: Any,
    *,
    expected_task: str | None = None,
    expected_candidate: dict[str, str] | None = None,
) -> dict[str, Any]:
    receipt = verify_publisher_receipt(
        value,
        expected_schema=BROWSER_CAPABILITY_SCHEMA,
        expected_kind="publisher-browser-capability",
    )
    if set(receipt) != {
        "schema",
        "schema_version",
        "kind",
        "task_id",
        "accepted_candidate",
        "ownership",
        "capabilities",
        "required_evidence_mode",
        "selected_evidence_mode",
        "assertions",
        "receipt_sha256",
    }:
        raise CloseoutError("browser capability receipt fields are incomplete")
    core = {
        key: item
        for key, item in receipt.items()
        if key
        not in {"schema", "schema_version", "kind", "receipt_sha256"}
    }
    # Rebuild through the normalizer so resealed malformed or contradictory
    # claims cannot gain credibility.
    ownership = core["ownership"]
    rebuild_ownership: dict[str, Any]
    if isinstance(ownership, dict) and ownership.get("mode") == "parent-fallback":
        script = ownership.get("script")
        if (
            not isinstance(script, dict)
            or set(script) != {"path", "sha256", "bytes"}
        ):
            raise CloseoutError("parent browser script identity is malformed")
        script_path = _contained_local_evidence_file(
            root, script.get("path"), label="parent browser fallback script"
        )
        if (
            script.get("sha256") != sha256_path(script_path)
            or script.get("bytes") != script_path.stat().st_size
        ):
            raise CloseoutError("parent browser fallback script identity drifted")
        rebuild_ownership = {
            "mode": "parent-fallback",
            "operator_task_id": ownership.get("operator_task_id"),
            "script": script.get("path"),
            "auditor": ownership.get("auditor"),
        }
    else:
        rebuild_ownership = ownership
    rebuilt = seal_publisher_receipt(_normalize_browser_capability_payload(
        root,
        {
            "task_id": core["task_id"],
            "accepted_candidate": core["accepted_candidate"],
            "ownership": rebuild_ownership,
            "capabilities": core["capabilities"],
            "required_evidence_mode": core["required_evidence_mode"],
            "selected_evidence_mode": core["selected_evidence_mode"],
            "assertions": core["assertions"],
        },
    ))
    if rebuilt != receipt:
        raise CloseoutError("browser capability receipt is not canonical")
    if expected_task is not None and receipt["task_id"] != expected_task:
        raise CloseoutError("browser capability receipt task does not match")
    if expected_candidate is not None and receipt["accepted_candidate"] != expected_candidate:
        raise CloseoutError("browser capability receipt candidate does not match")
    return receipt


def _browser_record(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    browser = config.get("browser")
    if isinstance(browser, dict) and "capability_receipt" in browser:
        if set(browser) != {"capability_receipt", "task_id"}:
            raise CloseoutError(
                "sealed browser config must contain only capability_receipt and task_id"
            )
        task_id = _normalized_evidence_name(
            browser.get("task_id"), label="browser config task_id"
        )
        path = _contained_local_evidence_file(
            root,
            browser.get("capability_receipt"),
            label="browser capability receipt",
        )
        receipt = verify_browser_capability_receipt(
            root,
            read_json_utf8(path, label="browser capability receipt"),
            expected_task=task_id,
            expected_candidate={
                "commit": require_sha(
                    config.get("accepted_candidate", {}).get("commit"),
                    label="accepted candidate commit",
                ),
                "tree": require_sha(
                    config.get("accepted_candidate", {}).get("tree"),
                    label="accepted candidate tree",
                ),
            },
        )
        requirements = _normalize_browser_requirements(
            config.get("browser_requirements")
        )
        _receipt_satisfies_browser_requirements(receipt, requirements)
        return {
            "mode": "capability-receipt",
            "task_id": task_id,
            "selected_evidence_mode": receipt["selected_evidence_mode"],
            "receipt": {
                "path": relative_label(root, path),
                "sha256": sha256_path(path),
                "bytes": path.stat().st_size,
                "receipt_sha256": receipt["receipt_sha256"],
            },
        }
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


def _candidate_tracked_file_identity(
    root: Path,
    candidate: dict[str, str],
    raw_path: object,
    *,
    label: str,
) -> dict[str, Any]:
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or Path(raw_path).is_absolute()
        or "\\" in raw_path
        or raw_path.startswith("../")
        or "/../" in f"/{raw_path}"
    ):
        raise CloseoutError(f"{label} must be a normalized repository-relative path")
    path = resolve_from_root(root, raw_path, label=label)
    if not path.is_file() or is_reparse(path):
        raise CloseoutError(f"{label} must be a normal tracked file")
    if git(root, "ls-files", "--error-unmatch", "--", raw_path) != raw_path:
        raise CloseoutError(f"{label} is not tracked at the current checkout")
    blob_result = run_child(
        ["git", "rev-parse", "--verify", f"{candidate['commit']}:{raw_path}"],
        cwd=root,
    )
    bytes_result = run_child(
        ["git", "show", f"{candidate['commit']}:{raw_path}"], cwd=root
    )
    if blob_result.returncode != 0 or bytes_result.returncode != 0:
        raise CloseoutError(f"{label} is absent from the accepted candidate")
    try:
        blob = blob_result.stdout.decode("ascii").strip().lower()
    except UnicodeDecodeError as exc:
        raise CloseoutError(f"{label} blob identity is malformed") from exc
    if SHA.fullmatch(blob) is None:
        raise CloseoutError(f"{label} blob identity is malformed")
    return {
        "path": raw_path,
        "blob": blob,
        "blob_sha256": sha256_bytes(bytes_result.stdout),
        "bytes": len(bytes_result.stdout),
        "worktree_sha256": sha256_path(path),
    }


def _nodeid_file_identity(root: Path, path: Path, *, label: str) -> dict[str, Any]:
    value = read_json_value_utf8(path, label=label)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise CloseoutError(f"{label} must contain distinct node IDs")
    return {
        "path": relative_label(root, path),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
        "nodeid_count": len(value),
        "ordered_nodeids_sha256": _ordered_nodeids_sha256(value),
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
            refusal_reason = _path_cleanup_refusal_reason(
                root, path, managed_roots, protected_controls
            )
            if refusal_reason is not None:
                entry.update({"disposition": "REFUSED", "reason": refusal_reason})
            elif not source.get("evidence_summary_recorded", False) or not source.get("no_unique_evidence", False):
                entry.update({"disposition": "REFUSED", "reason": "evidence is unresolved or unique"})
            else:
                options: dict[str, Any] = {}
                if kind == "historical_residual" and _path_exists_without_following(path) and not is_reparse(path):
                    options = _historical_cleanup_options(
                        path, source, label="cleanup.historical_residuals entry"
                    )
                    entry.update(options)
                fingerprint = _path_fingerprint(
                    path, allowed_reparse=options.get("unlink_only_reparse", ())
                )
                entry["fingerprint"] = fingerprint
                if fingerprint.get("unsafe_reparse"):
                    entry.update({"disposition": "REFUSED", "reason": "path contains a reparse point"})
                elif kind == "historical_residual" and path in by_path:
                    entry.update({"disposition": "REFUSED", "reason": "historical residual remains registered"})
                elif not fingerprint.get("exists"):
                    entry.update({"disposition": "REFUSED", "reason": "listed path is absent"})
                else:
                    entry.update({"disposition": "ELIGIBLE"})
            items.append(entry)

    candidate = {"commit": accepted, "tree": tree}
    browser = _browser_record(root, config)
    if browser.get("mode") == "capability-receipt":
        input_bindings = {
            "config": {
                "sha256": sha256_path(config_path) if config_path is not None else sha256_bytes(canonical_json_bytes(config)),
                "bytes": config_path.stat().st_size if config_path is not None else len(canonical_json_bytes(config)),
                **({"path": relative_label(root, config_path)} if config_path is not None else {}),
            },
            "nodeids_cache": _nodeid_file_identity(
                root, cache_path, label="Publisher node-ID cache"
            ),
            "nodeids_export": _nodeid_file_identity(
                root, export_path, label="Publisher node-ID export"
            ),
            "manifest": {
                "path": relative_label(root, manifest_path),
                "sha256": sha256_path(manifest_path),
                "bytes": manifest_path.stat().st_size,
            },
        }
    else:
        # The focused Publisher gate requires byte/count/order bindings, but the
        # established browser preflight/disposal modes intentionally accept an
        # empty node-ID fixture. Preserve their original hash-only contract.
        input_bindings = {
            "config": {
                "sha256": sha256_path(config_path) if config_path is not None else sha256_bytes(canonical_json_bytes(config)),
                **({"path": relative_label(root, config_path)} if config_path is not None else {}),
            },
            "nodeids_cache": {
                "path": relative_label(root, cache_path),
                "sha256": sha256_path(cache_path),
            },
            "nodeids_export": {
                "path": relative_label(root, export_path),
                "sha256": sha256_path(export_path),
            },
            "manifest": {
                "path": relative_label(root, manifest_path),
                "sha256": sha256_path(manifest_path),
            },
        }
    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-closeout-plan",
        "phase": config["phase"],
        "accepted_candidate": candidate,
        "target": {"ref": target["ref"], "expected_commit": expected_target},
        "canonical_controls": controls,
        "browser": browser,
        "inputs": input_bindings,
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
    if browser.get("mode") == "capability-receipt":
        plan["browser_requirements"] = _normalize_browser_requirements(
            config.get("browser_requirements")
        )
        plan["focused_runner"] = _candidate_tracked_file_identity(
            root,
            candidate,
            config.get("focused_runner"),
            label="focused_runner",
        )
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
    for record, collected in ((first_record, first), (second_record, second)):
        record["nodeids"] = list(collected)
        record["nodeid_count"] = len(collected)
        record["ordered_nodeids_sha256"] = _ordered_nodeids_sha256(collected)
    canonical = sorted(first)
    if first != second:
        raise CloseoutError(
            "fresh pytest collections are not deterministic: ordered node IDs differ"
        )
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
    receipt_core = {
        "schema": PUBLISHER_EVIDENCE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-preflight-receipt",
        "status": "PASS",
        "accepted_candidate": {"commit": actual_commit, "tree": actual_tree},
        "python_path": str(python_path),
        "environment": environment,
        "collections": {"first": first_record, "second": second_record, "canonical_count": len(canonical), "canonical_sha256": sha256_path(cache_path)},
        "manifest": manifest_record,
        "browser": browser,
        "disposal_plan": {
            "path": plan_path.name,
            "sha256": sha256_path(plan_path),
            "bytes": plan_path.stat().st_size,
            "plan_sha256": plan["plan_sha256"],
        },
    }
    if browser.get("mode") == "capability-receipt":
        receipt_core["browser_requirements"] = plan["browser_requirements"]
        receipt_core["focused_runner"] = plan["focused_runner"]
    receipt = seal_publisher_receipt(receipt_core)
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


def _unlink_exact_reparse_leaf(
    residual: Path, record: dict[str, str]
) -> dict[str, str]:
    """Unlink one sealed opaque leaf without inspecting or traversing its target."""
    relative_path, parts = _strict_relative_child_parts(
        record.get("relative_path"), label="sealed reparse leaf relative_path"
    )
    expected_kind = record.get("kind")
    if expected_kind not in REPARSE_UNLINK_KINDS:
        raise CloseoutError("sealed reparse leaf kind is unsupported")
    leaf = _literal_child_from_parts(residual, parts)
    _assert_normal_child_ancestors(residual, leaf, label="sealed reparse leaf")
    metadata = _lstat_or_none(leaf)
    if metadata is None:
        raise CloseoutError("sealed reparse leaf is absent")
    actual_kind = _reparse_leaf_kind(leaf, metadata)
    if actual_kind != expected_kind:
        raise CloseoutError("sealed reparse leaf type changed")
    if actual_kind == "symlink":
        leaf.unlink()
        operation = "unlink"
    else:
        leaf.rmdir()
        operation = "rmdir"
    if _lstat_or_none(leaf) is not None:
        raise CloseoutError("sealed reparse leaf remained after link-only removal")
    return {"relative_path": relative_path, "kind": actual_kind, "operation": operation}


def _unlink_sealed_reparse_leaves(
    residual: Path, records: Sequence[dict[str, str]], receipt: list[dict[str, str]]
) -> None:
    for record in records:
        receipt.append(_unlink_exact_reparse_leaf(residual, record))


def _is_windows_platform() -> bool:
    return os.name == "nt"


def _set_windows_file_attributes(path: Path, attributes: int) -> None:
    """Set only the already-observed Windows attributes for one normal node."""
    if not _is_windows_platform():
        raise CloseoutError("Windows attribute normalization is unavailable on this platform")
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    setter = kernel32.SetFileAttributesW
    setter.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    setter.restype = ctypes.c_int
    ctypes.set_last_error(0)
    if not setter(str(path), attributes):
        error = ctypes.get_last_error()
        raise OSError(error, "SetFileAttributesW failed", str(path))


def _normal_tree_nodes(path: Path) -> Iterable[tuple[Path, os.stat_result]]:
    """Yield an exact normal tree using lstat before every descent."""
    pending = [path]
    while pending:
        current = pending.pop()
        metadata = _lstat_or_none(current)
        if metadata is None or _is_reparse_stat(current, metadata):
            raise CloseoutError("Windows attribute normalization encountered a missing or reparse node")
        yield current, metadata
        if not stat.S_ISDIR(metadata.st_mode):
            continue
        children: list[tuple[Path, os.stat_result]] = []
        for child in current.iterdir():
            child_metadata = _lstat_or_none(child)
            if child_metadata is None or _is_reparse_stat(child, child_metadata):
                raise CloseoutError("Windows attribute normalization refuses a reparse descendant")
            children.append((child, child_metadata))
        pending.extend(path for path, _ in sorted(children, key=lambda item: item[0].name, reverse=True))


def _normalize_windows_attributes_tree(path: Path) -> dict[str, Any]:
    """Clear only ReadOnly/Hidden/System on a normal historical residual tree."""
    if not _is_windows_platform():
        return {"status": "NOT_APPLICABLE", "platform": os.name, "visited": 0, "changed": []}
    changed: list[dict[str, Any]] = []
    visited = 0
    for current, metadata in _normal_tree_nodes(path):
        visited += 1
        before = int(getattr(metadata, "st_file_attributes", 0))
        after = before & ~WINDOWS_CLEARABLE_ATTRIBUTE_MASK
        if after == before:
            continue
        _set_windows_file_attributes(current, after)
        verified = _lstat_or_none(current)
        if verified is None or _is_reparse_stat(current, verified):
            raise CloseoutError("Windows attribute normalization changed node identity")
        actual = int(getattr(verified, "st_file_attributes", 0))
        if actual & WINDOWS_CLEARABLE_ATTRIBUTE_MASK or (
            actual & ~WINDOWS_CLEARABLE_ATTRIBUTE_MASK
        ) != (before & ~WINDOWS_CLEARABLE_ATTRIBUTE_MASK):
            raise CloseoutError("Windows attribute normalization did not preserve the allowed flags")
        changed.append(
            {
                "relative_path": current.relative_to(path).as_posix() or ".",
                "before": f"0x{before:08X}",
                "after": f"0x{actual:08X}",
                "cleared": [
                    name for name, mask in WINDOWS_CLEARABLE_ATTRIBUTES if before & mask
                ],
            }
        )
    return {"status": "APPLIED", "visited": visited, "changed": changed}


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
    if _path_cleanup_refusal_reason(root, path, managed, controls) is not None:
        raise CloseoutError("plan-listed path no longer satisfies literal containment/non-reparse proof")
    allowed_reparse: Sequence[dict[str, str]] = ()
    if item.get("kind") == "historical_residual":
        options = _historical_cleanup_options(
            path, item, label="sealed historical residual item"
        )
        allowed_reparse = options.get("unlink_only_reparse", ())
    current = _path_fingerprint(path, allowed_reparse=allowed_reparse)
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
        historical_options: dict[str, Any] = {}
        if kind == "historical_residual":
            historical_options = _historical_cleanup_options(
                path, item, label="sealed historical residual item"
            )
            registered = {
                resolve_from_root(root, record["worktree"], label="registered worktree path")
                for record in _worktree_records(root)
                if "worktree" in record
            }
            if path in registered or not no_active_process_at(path):
                raise CloseoutError("historical residual is registered or has no active-process proof")
        return {"item": item, "path": path, "historical_options": historical_options}
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
                    if item["kind"] == "historical_residual":
                        options = action["historical_options"]
                        cleanup_actions: dict[str, Any] = {
                            "unlinked_reparse": [],
                            "windows_attribute_normalization": {"status": "NOT_REQUESTED"},
                        }
                        row["cleanup_actions"] = cleanup_actions
                        _unlink_sealed_reparse_leaves(
                            path,
                            options.get("unlink_only_reparse", ()),
                            cleanup_actions["unlinked_reparse"],
                        )
                        if options.get("windows_attribute_normalization") is not None:
                            cleanup_actions["windows_attribute_normalization"] = (
                                _normalize_windows_attributes_tree(path)
                            )
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


_VALIDATION_EVIDENCE_MODULE: Any | None = None


def _validation_evidence_module() -> Any:
    """Load the accepted validation-evidence contract from the sibling script."""
    global _VALIDATION_EVIDENCE_MODULE
    if _VALIDATION_EVIDENCE_MODULE is None:
        path = Path(__file__).with_name("validation_evidence.py")
        spec = importlib.util.spec_from_file_location(
            "_publisher_validation_evidence", path
        )
        if spec is None or spec.loader is None:
            raise CloseoutError("cannot load validation-evidence verifier")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _VALIDATION_EVIDENCE_MODULE = module
    return _VALIDATION_EVIDENCE_MODULE


def _load_contained_json_evidence(
    root: Path, raw_path: Path | str, *, label: str
) -> tuple[Path, dict[str, Any]]:
    path = _contained_local_evidence_file(
        root, str(raw_path), label=label, allow_absolute=True
    )
    return path, read_json_utf8(path, label=label)


def _input_identity(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": relative_label(root, path),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
    }


def _preflight_bound_file(
    root: Path,
    preflight_path: Path,
    binding: Any,
    *,
    label: str,
) -> Path:
    if not isinstance(binding, dict) or set(binding) != {
        "path",
        "sha256",
        "bytes",
    }:
        raise CloseoutError(f"{label} binding is malformed")
    raw_path = binding.get("path")
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise CloseoutError(f"{label} path must be relative to the preflight root")
    path = resolve_from_root(preflight_path.parent, raw_path, label=label)
    if (
        not literal_child(path, preflight_path.parent)
        or not path.is_file()
        or is_reparse(path)
        or binding.get("sha256") != sha256_path(path)
        or binding.get("bytes") != path.stat().st_size
    ):
        raise CloseoutError(f"{label} bytes drifted")
    _contained_local_evidence_file(
        root, str(path), label=label, allow_absolute=True
    )
    return path


def _verify_preflight_child_record(
    root: Path,
    preflight_path: Path,
    value: Any,
    *,
    label: str,
    collection: bool = False,
    environment: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    required = {
        "label",
        "arguments",
        "exit_code",
        "stdout",
        "stderr",
    }
    if collection:
        required |= {"nodeids", "nodeid_count", "ordered_nodeids_sha256"}
    if environment:
        required.add("manifest")
    if not isinstance(value, dict) or set(value) != required:
        raise CloseoutError(f"{label} child record is malformed")
    arguments = value.get("arguments")
    if (
        value.get("label") != label
        or value.get("exit_code") != 0
        or not isinstance(arguments, list)
        or not arguments
        or not all(isinstance(item, str) and item for item in arguments)
    ):
        raise CloseoutError(f"{label} child result is not an exact PASS")
    stdout = _preflight_bound_file(
        root, preflight_path, value["stdout"], label=f"{label} stdout"
    )
    stderr = _preflight_bound_file(
        root, preflight_path, value["stderr"], label=f"{label} stderr"
    )
    if collection:
        nodeids = value.get("nodeids")
        if (
            not isinstance(nodeids, list)
            or not nodeids
            or not all(isinstance(item, str) and item for item in nodeids)
            or len(nodeids) != len(set(nodeids))
            or value.get("nodeid_count") != len(nodeids)
            or value.get("ordered_nodeids_sha256")
            != _ordered_nodeids_sha256(nodeids)
            or parse_nodeids(stdout.read_bytes()) != nodeids
        ):
            raise CloseoutError(f"{label} node-ID evidence is malformed")
    return value, stdout, stderr


def _verify_environment_manifest(value: Any, *, python_path: str) -> dict[str, Any]:
    expected = {
        "ok",
        "python_executable",
        "python_version",
        "expected_python_version",
        "requirements_lock",
        "requirements_lock_sha256",
        "locked_requirements_checked",
        "dependency_check",
        "errors",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("ok") is not True
        or value.get("python_executable") != python_path
        or not isinstance(value.get("python_version"), str)
        or not value["python_version"]
        or value.get("expected_python_version") != value["python_version"]
        or not isinstance(value.get("requirements_lock"), str)
        or not value["requirements_lock"]
        or re.fullmatch(
            r"[0-9A-Fa-f]{64}", str(value.get("requirements_lock_sha256"))
        )
        is None
        or not isinstance(value.get("locked_requirements_checked"), int)
        or isinstance(value.get("locked_requirements_checked"), bool)
        or value["locked_requirements_checked"] <= 0
        or not isinstance(value.get("dependency_check"), str)
        or not value["dependency_check"]
        or value.get("errors") != []
    ):
        raise CloseoutError("Publisher preflight environment manifest is malformed")
    return value


def _verify_preflight_receipt(
    root: Path, preflight_path: Path, value: Any
) -> dict[str, Any]:
    receipt = verify_publisher_receipt(
        value,
        expected_schema=PUBLISHER_EVIDENCE_SCHEMA,
        expected_kind="publisher-preflight-receipt",
    )
    if set(receipt) != {
        "schema",
        "schema_version",
        "kind",
        "status",
        "accepted_candidate",
        "python_path",
        "environment",
        "collections",
        "manifest",
        "browser",
        "browser_requirements",
        "focused_runner",
        "disposal_plan",
        "receipt_sha256",
    }:
        raise CloseoutError("Publisher preflight receipt fields are incomplete")
    if receipt.get("status") != "PASS":
        raise CloseoutError("Publisher preflight receipt is not PASS")
    candidate = receipt.get("accepted_candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"commit", "tree"}:
        raise CloseoutError("Publisher preflight candidate is malformed")
    require_sha(candidate.get("commit"), label="preflight candidate commit")
    require_sha(candidate.get("tree"), label="preflight candidate tree")
    python_path = receipt.get("python_path")
    if not isinstance(python_path, str) or not Path(python_path).is_absolute():
        raise CloseoutError("Publisher preflight interpreter path is malformed")
    environment, _, _ = _verify_preflight_child_record(
        root,
        preflight_path,
        receipt.get("environment"),
        label="validation-environment",
        environment=True,
    )
    _verify_environment_manifest(environment["manifest"], python_path=python_path)
    collections = receipt.get("collections")
    if not isinstance(collections, dict) or set(collections) != {
        "first",
        "second",
        "canonical_count",
        "canonical_sha256",
    }:
        raise CloseoutError("Publisher preflight collections are malformed")
    first, _, _ = _verify_preflight_child_record(
        root,
        preflight_path,
        collections["first"],
        label="pytest-collect-1",
        collection=True,
    )
    second, _, _ = _verify_preflight_child_record(
        root,
        preflight_path,
        collections["second"],
        label="pytest-collect-2",
        collection=True,
    )
    nodeids = first["nodeids"]
    if (
        second["nodeids"] != nodeids
        or collections.get("canonical_count") != len(nodeids)
        or collections.get("canonical_sha256")
        != sha256_bytes(canonical_json_bytes(sorted(nodeids)))
    ):
        raise CloseoutError(
            "Publisher preflight collection records are not deterministic"
        )
    _verify_preflight_child_record(
        root,
        preflight_path,
        receipt.get("manifest"),
        label="publisher-manifest",
    )
    _normalize_browser_requirements(receipt.get("browser_requirements"))
    runner = receipt.get("focused_runner")
    if not isinstance(runner, dict) or set(runner) != {
        "path",
        "blob",
        "blob_sha256",
        "bytes",
        "worktree_sha256",
    }:
        raise CloseoutError("Publisher preflight focused runner is malformed")
    require_sha(runner.get("blob"), label="focused runner blob")
    if (
        re.fullmatch(r"[0-9A-Fa-f]{64}", str(runner.get("blob_sha256"))) is None
        or re.fullmatch(
            r"[0-9A-Fa-f]{64}", str(runner.get("worktree_sha256"))
        )
        is None
        or not isinstance(runner.get("bytes"), int)
        or isinstance(runner.get("bytes"), bool)
        or runner["bytes"] <= 0
    ):
        raise CloseoutError("Publisher preflight focused runner is malformed")
    disposal = receipt.get("disposal_plan")
    if not isinstance(disposal, dict) or set(disposal) != {
        "path",
        "sha256",
        "bytes",
        "plan_sha256",
    }:
        raise CloseoutError("Publisher preflight disposal-plan binding is malformed")
    disposal_path = _preflight_bound_file(
        root,
        preflight_path,
        {
            key: disposal[key]
            for key in ("path", "sha256", "bytes")
        },
        label="Publisher disposal plan",
    )
    disposal_value = read_json_utf8(disposal_path, label="Publisher disposal plan")
    verify_sealed_plan(disposal_value)
    if disposal_value.get("plan_sha256") != disposal.get("plan_sha256"):
        raise CloseoutError("Publisher preflight disposal plan seal differs")
    return receipt


def _verify_publisher_manifest(
    value: Any, *, expected_candidate: dict[str, str]
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "accepted_candidate",
        "tests",
        "live_routes",
    }:
        raise CloseoutError("Publisher manifest fields are incomplete")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise CloseoutError("Publisher manifest schema is unsupported")
    if value.get("accepted_candidate") != expected_candidate:
        raise CloseoutError("Publisher manifest candidate does not match")
    tests = value.get("tests")
    if not isinstance(tests, dict) or set(tests) != {
        "nodeids_cache",
        "nodeids_export",
        "selectors",
        "expanded_nodeids",
        "expanded_nodeid_count",
    }:
        raise CloseoutError("Publisher manifest test contract is malformed")
    nodeids = tests.get("expanded_nodeids")
    for name in ("nodeids_cache", "nodeids_export"):
        binding = tests.get(name)
        if (
            not isinstance(binding, dict)
            or set(binding) != {"path", "sha256", "nodeid_count"}
            or not isinstance(binding.get("path"), str)
            or not binding["path"]
            or re.fullmatch(r"[0-9A-Fa-f]{64}", str(binding.get("sha256")))
            is None
            or not isinstance(binding.get("nodeid_count"), int)
            or isinstance(binding.get("nodeid_count"), bool)
            or binding["nodeid_count"] <= 0
        ):
            raise CloseoutError(f"Publisher manifest {name} identity is malformed")
    selectors = tests.get("selectors")
    if (
        not isinstance(nodeids, list)
        or not nodeids
        or not all(
            isinstance(nodeid, str)
            and nodeid.startswith("tests/")
            and "::" in nodeid
            and "\x00" not in nodeid
            for nodeid in nodeids
        )
        or len(nodeids) != len(set(nodeids))
        or nodeids != sorted(nodeids)
        or tests.get("expanded_nodeid_count") != len(nodeids)
        or not isinstance(selectors, list)
        or not selectors
        or not all(isinstance(item, str) and item for item in selectors)
        or len(selectors) != len(set(selectors))
        or tests["nodeids_cache"]["nodeid_count"] != len(nodeids)
        or tests["nodeids_export"]["nodeid_count"] != len(nodeids)
    ):
        raise CloseoutError("Publisher manifest expanded node IDs are malformed")
    return value


def _load_validation_identity(root: Path, path: Path) -> dict[str, Any]:
    module = _validation_evidence_module()
    try:
        value = module.load_json(path)
        return module.verify_frozen_identity(root, value)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CloseoutError(f"validation identity is invalid: {exc}") from exc


def _ordered_nodeids_sha256(nodeids: Sequence[str]) -> str:
    return sha256_bytes(canonical_json_bytes(list(nodeids)))


def _write_once_or_match(path: Path, payload: bytes) -> None:
    if path.exists():
        if is_reparse(path) or not path.is_file() or path.read_bytes() != payload:
            raise CloseoutError(f"existing one-shot evidence differs: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CloseoutError(f"one-shot evidence already exists: {path.name}") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _browser_receipt_from_plan(
    root: Path, plan: dict[str, Any], candidate: dict[str, str]
) -> tuple[Path, dict[str, Any]]:
    browser = plan.get("browser")
    if (
        not isinstance(browser, dict)
        or browser.get("mode") != "capability-receipt"
        or set(browser) != {
            "mode",
            "task_id",
            "selected_evidence_mode",
            "receipt",
        }
    ):
        raise CloseoutError(
            "focused validation requires a sealed Browser capability receipt"
        )
    binding = browser.get("receipt")
    if not isinstance(binding, dict) or set(binding) != {
        "path",
        "sha256",
        "bytes",
        "receipt_sha256",
    }:
        raise CloseoutError("Browser capability receipt binding is malformed")
    path, value = _load_contained_json_evidence(
        root, binding.get("path"), label="Browser capability receipt"
    )
    if (
        binding.get("sha256") != sha256_path(path)
        or binding.get("bytes") != path.stat().st_size
    ):
        raise CloseoutError("Browser capability receipt file drifted")
    receipt = verify_browser_capability_receipt(
        root,
        value,
        expected_task=browser.get("task_id"),
        expected_candidate=candidate,
    )
    if (
        receipt["receipt_sha256"] != binding.get("receipt_sha256")
        or receipt["selected_evidence_mode"]
        != browser.get("selected_evidence_mode")
    ):
        raise CloseoutError("Browser capability receipt binding is inconsistent")
    return path, receipt


def _plan_bound_file(
    root: Path,
    binding: Any,
    *,
    label: str,
    extra_keys: frozenset[str] = frozenset(),
) -> Path:
    required = {"path", "sha256", "bytes"} | set(extra_keys)
    if not isinstance(binding, dict) or set(binding) != required:
        raise CloseoutError(f"{label} binding is malformed")
    path = _contained_local_evidence_file(root, binding.get("path"), label=label)
    if (
        binding.get("sha256") != sha256_path(path)
        or binding.get("bytes") != path.stat().st_size
    ):
        raise CloseoutError(f"{label} bytes drifted")
    return path


def _verify_focused_plan_inputs(
    root: Path,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    candidate: dict[str, str],
) -> dict[str, Path]:
    inputs = plan.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {
        "config",
        "nodeids_cache",
        "nodeids_export",
        "manifest",
    }:
        raise CloseoutError("focused plan input bindings are incomplete")
    config_path = _plan_bound_file(root, inputs["config"], label="Publisher config")
    cache_path = _plan_bound_file(
        root,
        inputs["nodeids_cache"],
        label="Publisher node-ID cache",
        extra_keys=frozenset({"nodeid_count", "ordered_nodeids_sha256"}),
    )
    export_path = _plan_bound_file(
        root,
        inputs["nodeids_export"],
        label="Publisher node-ID export",
        extra_keys=frozenset({"nodeid_count", "ordered_nodeids_sha256"}),
    )
    manifest_path = _plan_bound_file(
        root, inputs["manifest"], label="Publisher manifest"
    )
    cache = read_json_value_utf8(cache_path, label="Publisher node-ID cache")
    export = read_json_value_utf8(export_path, label="Publisher node-ID export")
    expected_nodeids = manifest["tests"]["expanded_nodeids"]
    for label, value, binding in (
        ("cache", cache, inputs["nodeids_cache"]),
        ("export", export, inputs["nodeids_export"]),
    ):
        if (
            value != expected_nodeids
            or binding.get("nodeid_count") != len(expected_nodeids)
            or binding.get("ordered_nodeids_sha256")
            != _ordered_nodeids_sha256(expected_nodeids)
        ):
            raise CloseoutError(f"Publisher node-ID {label} does not match manifest")
    if cache_path.read_bytes() != export_path.read_bytes():
        raise CloseoutError("Publisher node-ID cache/export bytes differ")
    manifest_tests = manifest["tests"]
    for name, path in (("nodeids_cache", cache_path), ("nodeids_export", export_path)):
        internal = manifest_tests[name]
        if (
            internal.get("path") != relative_label(root, path)
            or internal.get("sha256") != sha256_path(path)
            or internal.get("nodeid_count") != len(expected_nodeids)
        ):
            raise CloseoutError(f"Publisher manifest {name} binding differs")
    config = read_json_utf8(config_path, label="Publisher candidate config")
    if (
        config.get("accepted_candidate") != candidate
        or _normalize_browser_requirements(config.get("browser_requirements"))
        != plan.get("browser_requirements")
        or config.get("focused_runner") != plan.get("focused_runner", {}).get("path")
    ):
        raise CloseoutError("Publisher config formal focused contract differs")
    browser_config = config.get("browser")
    if (
        not isinstance(browser_config, dict)
        or set(browser_config) != {"capability_receipt", "task_id"}
        or browser_config.get("task_id") != plan.get("browser", {}).get("task_id")
        or browser_config.get("capability_receipt")
        != plan.get("browser", {}).get("receipt", {}).get("path")
    ):
        raise CloseoutError("Publisher config Browser binding differs")
    if read_json_utf8(manifest_path, label="Publisher manifest") != manifest:
        raise CloseoutError("Publisher plan manifest bytes differ")
    return {
        "config": config_path,
        "nodeids_cache": cache_path,
        "nodeids_export": export_path,
        "manifest": manifest_path,
    }


def focused_proof(
    *,
    project_root: Path,
    python_path: Path,
    preflight_receipt_path: Path,
    plan_path: Path,
    validation_identity_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Prove all deterministic inputs without starting pytest."""
    root = literal_project_root(project_root)
    assert_explicit_python(python_path)
    output_root = _output_directory(root, output)
    preflight_path, preflight_value = _load_contained_json_evidence(
        root, preflight_receipt_path, label="Publisher preflight receipt"
    )
    preflight = _verify_preflight_receipt(root, preflight_path, preflight_value)
    plan_path, plan = _load_contained_json_evidence(
        root, plan_path, label="Publisher disposal plan"
    )
    verify_sealed_plan(plan)
    validation_path, _ = _load_contained_json_evidence(
        root, validation_identity_path, label="validation identity"
    )
    validation = _load_validation_identity(root, validation_path)
    candidate = {
        "commit": require_sha(
            preflight["accepted_candidate"].get("commit"),
            label="preflight candidate commit",
        ),
        "tree": require_sha(
            preflight["accepted_candidate"].get("tree"),
            label="preflight candidate tree",
        ),
    }
    if plan.get("accepted_candidate") != candidate:
        raise CloseoutError("preflight and plan candidate identities differ")
    if {
        "commit": validation["candidate"]["commit"],
        "tree": validation["candidate"]["tree"],
    } != candidate:
        raise CloseoutError("validation identity is not bound to this candidate")
    actual_commit, actual_tree = accepted_identity(root, candidate["commit"])
    if {"commit": actual_commit, "tree": actual_tree} != candidate:
        raise CloseoutError("accepted candidate Git identity is unavailable")
    assert_clean_exact_checkout(root, actual_commit, actual_tree)
    if preflight.get("python_path") != str(python_path):
        raise CloseoutError("preflight interpreter path does not match")
    environment = preflight.get("environment")
    environment_manifest = (
        environment.get("manifest") if isinstance(environment, dict) else None
    )
    expected_environment_arguments = [
        str(python_path),
        "-B",
        str(root / "scripts" / "verify_validation_environment.py"),
        "--project-root",
        str(root),
    ]
    if (
        not isinstance(environment_manifest, dict)
        or environment_manifest.get("ok") is not True
        or environment_manifest.get("python_version")
        != validation["interpreter"]["version"]
        or environment_manifest.get("requirements_lock_sha256")
        != validation["dependencies"]["sha256"]
        or environment_manifest.get("locked_requirements_checked")
        != validation["dependencies"]["package_count"]
        or environment_manifest.get("errors") not in ([], None)
        or environment.get("arguments") != expected_environment_arguments
        or environment_manifest.get("python_executable") != str(python_path)
        or Path(environment_manifest.get("requirements_lock", "")).resolve()
        != (root / validation["dependencies"]["path"]).resolve()
        or sha256_path(python_path)
        != validation["interpreter"]["executable_sha256"]
    ):
        raise CloseoutError(
            "preflight environment does not match the frozen validation identity"
        )
    disposal_binding = preflight.get("disposal_plan")
    if (
        not isinstance(disposal_binding, dict)
        or disposal_binding.get("sha256") != sha256_path(plan_path)
        or disposal_binding.get("bytes") != plan_path.stat().st_size
        or disposal_binding.get("plan_sha256") != plan.get("plan_sha256")
    ):
        raise CloseoutError("preflight disposal-plan binding does not match")
    inputs = plan.get("inputs")
    manifest_binding = inputs.get("manifest") if isinstance(inputs, dict) else None
    if not isinstance(manifest_binding, dict):
        raise CloseoutError("sealed plan manifest binding is missing")
    manifest_path, manifest_value = _load_contained_json_evidence(
        root, manifest_binding.get("path"), label="Publisher manifest"
    )
    if (
        manifest_binding.get("sha256") != sha256_path(manifest_path)
        or manifest_binding.get("bytes") != manifest_path.stat().st_size
    ):
        raise CloseoutError("Publisher manifest drifted after preflight")
    manifest = _verify_publisher_manifest(
        manifest_value, expected_candidate=candidate
    )
    plan_paths = _verify_focused_plan_inputs(root, plan, manifest, candidate)
    config = read_json_utf8(
        plan_paths["config"], label="Publisher candidate config"
    )
    selectors = manifest["tests"]["selectors"]
    expected_collect_arguments = [
        str(python_path),
        "-B",
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        *selectors,
    ]
    collections = preflight["collections"]
    if (
        collections["first"]["arguments"] != expected_collect_arguments
        or collections["second"]["arguments"] != expected_collect_arguments
        or collections["first"]["nodeids"] != collections["second"]["nodeids"]
        or collections["first"]["nodeids"]
        != manifest["tests"]["expanded_nodeids"]
        or collections["second"]["nodeids"]
        != manifest["tests"]["expanded_nodeids"]
        or collections["canonical_count"]
        != manifest["tests"]["expanded_nodeid_count"]
        or collections["canonical_sha256"]
        != sha256_path(plan_paths["nodeids_cache"])
    ):
        raise CloseoutError("Publisher preflight collection contract differs")
    expected_manifest_arguments = [
        str(python_path),
        "-B",
        str(root / "scripts" / "generate_publisher_manifest.py"),
        "--accepted-commit",
        candidate["commit"],
        "--nodeids-cache",
        str(plan_paths["nodeids_cache"]),
        "--nodeids-export",
        str(plan_paths["nodeids_export"]),
        "--output",
        str(plan_paths["manifest"]),
    ]
    for selector in selectors:
        expected_manifest_arguments.extend(["--selector", selector])
    for route in config.get("live_routes", []):
        expected_manifest_arguments.extend(["--live-route", str(route)])
    if preflight["manifest"]["arguments"] != expected_manifest_arguments:
        raise CloseoutError("Publisher preflight manifest invocation differs")
    if preflight.get("browser") != plan.get("browser"):
        raise CloseoutError("preflight and plan Browser capability bindings differ")
    requirements = _normalize_browser_requirements(
        plan.get("browser_requirements")
    )
    if preflight.get("browser_requirements") != requirements:
        raise CloseoutError("preflight and plan Browser requirements differ")
    browser_path, browser = _browser_receipt_from_plan(root, plan, candidate)
    _receipt_satisfies_browser_requirements(browser, requirements)
    runner = _candidate_tracked_file_identity(
        root,
        candidate,
        plan.get("focused_runner", {}).get("path"),
        label="focused runner",
    )
    if (
        runner != plan.get("focused_runner")
        or preflight.get("focused_runner") != runner
        or validation["runner"]["path"] != runner["path"]
        or validation["runner"]["sha256"] != runner["blob_sha256"]
    ):
        raise CloseoutError("focused runner identity is not exact")
    nodeids = manifest["tests"]["expanded_nodeids"]
    core = {
        "schema": PUBLISHER_EVIDENCE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-focused-proof",
        "status": "PROVED",
        "state": "PROVED",
        "accepted_candidate": candidate,
        "python": {
            "executable": str(python_path),
            "version": validation["interpreter"]["version"],
            "sha256": validation["interpreter"]["executable_sha256"],
        },
        "environment": {
            "dependencies_path": validation["dependencies"]["path"],
            "requirements_lock_sha256": validation["dependencies"]["sha256"],
            "locked_requirements_checked": validation["dependencies"][
                "package_count"
            ],
        },
        "inputs": {
            "preflight": _input_identity(root, preflight_path),
            "plan": _input_identity(root, plan_path),
            "config": _input_identity(root, plan_paths["config"]),
            "nodeids_cache": _input_identity(root, plan_paths["nodeids_cache"]),
            "nodeids_export": _input_identity(root, plan_paths["nodeids_export"]),
            "manifest": _input_identity(root, manifest_path),
            "validation_identity": _input_identity(root, validation_path),
            "browser_capability": _input_identity(root, browser_path),
        },
        "browser": {
            "task_id": browser["task_id"],
            "required_evidence_mode": requirements["required_evidence_mode"],
            "selected_evidence_mode": browser["selected_evidence_mode"],
            "receipt_sha256": browser["receipt_sha256"],
            "assertions": requirements["assertions"],
        },
        "runner": runner,
        "tests": {
            "expanded_nodeids": nodeids,
            "expanded_nodeid_count": len(nodeids),
            "ordered_nodeids_sha256": _ordered_nodeids_sha256(nodeids),
        },
        "lock_contract": {
            "file": "campaign-player-wiki-complete-validation.lock",
            "guard_environment": [
                VALIDATION_LOCK_PATH_ENV,
                VALIDATION_LOCK_TOKEN_ENV,
            ],
        },
        "invocation_contract": dict(FOCUSED_INVOCATION_CONTRACT),
        "state_sequence": list(FOCUSED_STATE_SEQUENCE),
        "invocation_count": 0,
    }
    proof = seal_publisher_receipt(core)
    _write_once_or_match(
        output_root / "focused-proof.json", canonical_json_bytes(proof)
    )
    return proof


def verify_focused_proof(root: Path, value: Any) -> dict[str, Any]:
    proof = verify_publisher_receipt(
        value,
        expected_schema=PUBLISHER_EVIDENCE_SCHEMA,
        expected_kind="publisher-focused-proof",
    )
    if set(proof) != {
        "schema",
        "schema_version",
        "kind",
        "status",
        "state",
        "accepted_candidate",
        "python",
        "environment",
        "inputs",
        "browser",
        "runner",
        "tests",
        "lock_contract",
        "invocation_contract",
        "state_sequence",
        "invocation_count",
        "receipt_sha256",
    }:
        raise CloseoutError("focused proof fields are incomplete")
    if (
        proof.get("status") != "PROVED"
        or proof.get("state") != "PROVED"
        or proof.get("invocation_count") != 0
        or proof.get("invocation_contract") != FOCUSED_INVOCATION_CONTRACT
        or proof.get("state_sequence") != list(FOCUSED_STATE_SEQUENCE)
    ):
        raise CloseoutError("focused proof is not in the PROVED state")
    candidate = proof.get("accepted_candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"commit", "tree"}:
        raise CloseoutError("focused proof candidate is malformed")
    candidate = {
        "commit": require_sha(candidate.get("commit"), label="focused commit"),
        "tree": require_sha(candidate.get("tree"), label="focused tree"),
    }
    python = proof.get("python")
    if not isinstance(python, dict) or set(python) != {
        "executable",
        "version",
        "sha256",
    }:
        raise CloseoutError("focused proof interpreter is malformed")
    python_path = Path(python["executable"])
    assert_explicit_python(python_path)
    if python.get("sha256") != sha256_path(python_path):
        raise CloseoutError("focused proof interpreter drifted")
    nodeids = proof.get("tests", {}).get("expanded_nodeids")
    if (
        not isinstance(nodeids, list)
        or not nodeids
        or proof["tests"].get("expanded_nodeid_count") != len(nodeids)
        or proof["tests"].get("ordered_nodeids_sha256")
        != _ordered_nodeids_sha256(nodeids)
    ):
        raise CloseoutError("focused proof node-ID contract is malformed")
    inputs = proof.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {
        "preflight",
        "plan",
        "config",
        "nodeids_cache",
        "nodeids_export",
        "manifest",
        "validation_identity",
        "browser_capability",
    }:
        raise CloseoutError("focused proof inputs are malformed")
    input_paths: dict[str, Path] = {}
    input_values: dict[str, dict[str, Any]] = {}
    for name, binding in inputs.items():
        if not isinstance(binding, dict) or set(binding) != {
            "path",
            "sha256",
            "bytes",
        }:
            raise CloseoutError("focused proof input binding is malformed")
        path = _contained_local_evidence_file(
            root, binding["path"], label="focused proof input"
        )
        if (
            binding["sha256"] != sha256_path(path)
            or binding["bytes"] != path.stat().st_size
        ):
            raise CloseoutError("focused proof input drifted")
        input_paths[name] = path
        input_values[name] = (
            read_json_value_utf8(path, label=f"focused proof {name}")
            if name in {"nodeids_cache", "nodeids_export"}
            else read_json_utf8(path, label=f"focused proof {name}")
        )
    preflight = _verify_preflight_receipt(
        root, input_paths["preflight"], input_values["preflight"]
    )
    plan = input_values["plan"]
    verify_sealed_plan(plan)
    manifest = _verify_publisher_manifest(
        input_values["manifest"], expected_candidate=candidate
    )
    plan_paths = _verify_focused_plan_inputs(root, plan, manifest, candidate)
    for name in ("config", "nodeids_cache", "nodeids_export", "manifest"):
        if input_paths[name] != plan_paths[name]:
            raise CloseoutError("focused proof plan input path differs")
    validation = _load_validation_identity(
        root, input_paths["validation_identity"]
    )
    browser = verify_browser_capability_receipt(
        root,
        input_values["browser_capability"],
        expected_task=proof.get("browser", {}).get("task_id"),
        expected_candidate=candidate,
    )
    expected_browser_record = {
        "mode": "capability-receipt",
        "task_id": browser["task_id"],
        "selected_evidence_mode": browser["selected_evidence_mode"],
        "receipt": {
            **_input_identity(root, input_paths["browser_capability"]),
            "receipt_sha256": browser["receipt_sha256"],
        },
    }
    plan_inputs = plan.get("inputs")
    disposal_binding = preflight.get("disposal_plan")
    requirements = _normalize_browser_requirements(
        plan.get("browser_requirements")
    )
    _receipt_satisfies_browser_requirements(browser, requirements)
    runner = _candidate_tracked_file_identity(
        root,
        candidate,
        plan.get("focused_runner", {}).get("path"),
        label="focused runner",
    )
    environment_manifest = preflight["environment"]["manifest"]
    expected_environment_arguments = [
        str(python_path),
        "-B",
        str(root / "scripts" / "verify_validation_environment.py"),
        "--project-root",
        str(root),
    ]
    selectors = manifest["tests"]["selectors"]
    expected_collect_arguments = [
        str(python_path),
        "-B",
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        *selectors,
    ]
    collections = preflight["collections"]
    config = read_json_utf8(plan_paths["config"], label="Publisher candidate config")
    expected_manifest_arguments = [
        str(python_path),
        "-B",
        str(root / "scripts" / "generate_publisher_manifest.py"),
        "--accepted-commit",
        candidate["commit"],
        "--nodeids-cache",
        str(plan_paths["nodeids_cache"]),
        "--nodeids-export",
        str(plan_paths["nodeids_export"]),
        "--output",
        str(plan_paths["manifest"]),
    ]
    for selector in selectors:
        expected_manifest_arguments.extend(["--selector", selector])
    for route in config.get("live_routes", []):
        expected_manifest_arguments.extend(["--live-route", str(route)])
    if (
        preflight.get("accepted_candidate") != candidate
        or plan.get("accepted_candidate") != candidate
        or preflight.get("python_path") != str(python_path)
        or manifest["tests"]["expanded_nodeids"] != nodeids
        or {
            "commit": validation["candidate"]["commit"],
            "tree": validation["candidate"]["tree"],
        }
        != candidate
        or python.get("version") != validation["interpreter"]["version"]
        or python.get("sha256") != validation["interpreter"]["executable_sha256"]
        or proof.get("environment")
        != {
            "dependencies_path": validation["dependencies"]["path"],
            "requirements_lock_sha256": validation["dependencies"]["sha256"],
            "locked_requirements_checked": validation["dependencies"][
                "package_count"
            ],
        }
        or proof.get("browser")
        != {
            "task_id": browser["task_id"],
            "required_evidence_mode": requirements["required_evidence_mode"],
            "selected_evidence_mode": browser["selected_evidence_mode"],
            "receipt_sha256": browser["receipt_sha256"],
            "assertions": requirements["assertions"],
        }
        or proof.get("runner") != runner
        or preflight["environment"]["arguments"]
        != expected_environment_arguments
        or collections["first"]["arguments"] != expected_collect_arguments
        or collections["second"]["arguments"] != expected_collect_arguments
        or collections["first"]["nodeids"] != collections["second"]["nodeids"]
        or collections["first"]["nodeids"]
        != manifest["tests"]["expanded_nodeids"]
        or collections["second"]["nodeids"]
        != manifest["tests"]["expanded_nodeids"]
        or collections["canonical_count"] != len(nodeids)
        or collections["canonical_sha256"]
        != sha256_path(plan_paths["nodeids_cache"])
        or preflight["manifest"]["arguments"] != expected_manifest_arguments
        or validation["runner"]["path"] != runner["path"]
        or validation["runner"]["sha256"] != runner["blob_sha256"]
        or preflight.get("focused_runner") != runner
        or preflight.get("browser_requirements") != requirements
        or preflight.get("browser") != expected_browser_record
        or plan.get("browser") != expected_browser_record
        or not isinstance(plan_inputs, dict)
        or environment_manifest.get("python_executable") != str(python_path)
        or environment_manifest.get("python_version")
        != validation["interpreter"]["version"]
        or environment_manifest.get("requirements_lock_sha256")
        != validation["dependencies"]["sha256"]
        or environment_manifest.get("locked_requirements_checked")
        != validation["dependencies"]["package_count"]
        or Path(environment_manifest.get("requirements_lock", "")).resolve()
        != (root / validation["dependencies"]["path"]).resolve()
        or not isinstance(disposal_binding, dict)
        or disposal_binding.get("sha256") != sha256_path(input_paths["plan"])
        or disposal_binding.get("bytes") != input_paths["plan"].stat().st_size
        or disposal_binding.get("plan_sha256") != plan.get("plan_sha256")
    ):
        raise CloseoutError("focused proof semantic bindings do not match")
    lock_contract = proof.get("lock_contract")
    if lock_contract != {
        "file": "campaign-player-wiki-complete-validation.lock",
        "guard_environment": [
            VALIDATION_LOCK_PATH_ENV,
            VALIDATION_LOCK_TOKEN_ENV,
        ],
    }:
        raise CloseoutError("focused proof lock contract is malformed")
    return proof


def verify_inherited_validation_lock(root: Path) -> dict[str, Any]:
    raw_path = os.environ.get(VALIDATION_LOCK_PATH_ENV)
    raw_guard = os.environ.get(VALIDATION_LOCK_TOKEN_ENV)
    if not raw_path or not raw_guard:
        raise CloseoutError("focused run requires the inherited validation lock")
    expected = git_path(root) / "campaign-player-wiki-complete-validation.lock"
    supplied = Path(os.path.abspath(raw_path))
    if os.path.normcase(str(supplied)) != os.path.normcase(str(expected)):
        raise CloseoutError("inherited validation lock path does not match")
    if (
        not supplied.is_file()
        or is_reparse(supplied)
        or re.fullmatch(r"[0-9a-fA-F]{32}", raw_guard) is None
    ):
        raise CloseoutError("inherited validation lock is malformed")
    try:
        retained = supplied.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CloseoutError("cannot read inherited validation lock") from exc
    if retained != raw_guard:
        raise CloseoutError("inherited validation lock guard does not match")
    return {
        "file": supplied.name,
        "guard_sha256": sha256_bytes(raw_guard.encode("ascii")),
        "held": True,
    }


def _focused_arguments(proof: dict[str, Any]) -> list[str]:
    return [
        proof["python"]["executable"],
        "-B",
        "-m",
        "pytest",
        "-p",
        "scripts.publisher_closeout",
        "-q",
        *proof["tests"]["expanded_nodeids"],
    ]


def _launch_focused_pytest(
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout: Any,
    stderr: Any,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        list(arguments),
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
    )


def _exclusive_invocation_sentinel(path: Path, proof_sha256: str) -> None:
    payload = canonical_json_bytes(
        {
            "state": "SENTINEL_CREATED",
            "proof_receipt_sha256": proof_sha256,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CloseoutError("focused invocation sentinel already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _focused_postflight(
    root: Path,
    proof: dict[str, Any],
    sentinel: Path,
    lock_record: dict[str, Any],
) -> dict[str, Any]:
    current_lock = verify_inherited_validation_lock(root)
    candidate = proof["accepted_candidate"]
    commit, tree = accepted_identity(root, "HEAD")
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    expected_sentinel = canonical_json_bytes(
        {
            "state": "SENTINEL_CREATED",
            "proof_receipt_sha256": proof["receipt_sha256"],
        }
    )
    return {
        "lock_held": current_lock == lock_record,
        "candidate_unchanged": {
            "commit": commit,
            "tree": tree,
        }
        == candidate,
        "worktree_clean": status == "",
        "sentinel_unchanged": sentinel.read_bytes() == expected_sentinel,
    }


def _compact_failure(exc: BaseException) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "reason": str(exc).splitlines()[0][:240] or "unspecified failure",
    }


def _focused_write_started(path: Path, payload: bytes) -> None:
    _write_once_or_match(path, payload)


def _focused_wait_child(process: subprocess.Popen[bytes]) -> int:
    return int(process.wait())


def _focused_flush_streams(stdout_stream: Any, stderr_stream: Any) -> None:
    for stream in (stdout_stream, stderr_stream):
        stream.flush()
        os.fsync(stream.fileno())


def _focused_poll(process: Any) -> int | None:
    poll = getattr(process, "poll", None)
    if callable(poll):
        value = poll()
        return None if value is None else int(value)
    return None


def _focused_wait_until_reaped(process: Any) -> int:
    """Wait fail-closed until a spawned child has definitely exited."""
    while True:
        try:
            value = process.wait()
        except BaseException:
            # Releasing the complete-validation lock around a child whose
            # exit is unconfirmed is worse than retaining the lock.  Retry the
            # unbounded reap after transient controller/adapter failures.
            continue
        if value is not None:
            return int(value)
        try:
            polled = _focused_poll(process)
        except BaseException:
            continue
        if polled is not None:
            return polled


def _terminate_and_reap_focused_child(
    process: Any, known_exit_code: int | None
) -> tuple[int, dict[str, Any]]:
    """Guarantee that a successfully spawned child is waited before return."""
    termination = {
        "terminate_requested": False,
        "kill_requested": False,
        "wait_completed": False,
    }
    if known_exit_code is not None:
        # wait() already returned, so the process has been reaped.
        termination["wait_completed"] = True
        return int(known_exit_code), termination
    try:
        polled = _focused_poll(process)
    except BaseException:
        polled = None
    if polled is not None:
        # Call wait once more to consume implementations where poll does not
        # reap.  A transient adapter error cannot release the lock early.
        value = _focused_wait_until_reaped(process)
        termination["wait_completed"] = True
        return int(value), termination
    termination["terminate_requested"] = True
    try:
        process.terminate()
        try:
            value = process.wait(timeout=5)
        except BaseException:
            value = None
        if value is not None:
            termination["wait_completed"] = True
            return int(value), termination
    except BaseException:
        pass
    # A timeout or controller/adapter error during terminate/wait is not
    # permission to release the validation lock.  Request kill, then reap
    # fail-closed even when kill or the post-kill timed wait itself fails.
    termination["kill_requested"] = True
    try:
        process.kill()
    except BaseException:
        pass
    else:
        try:
            value = process.wait(timeout=5)
        except TypeError:
            value = _focused_wait_until_reaped(process)
        except BaseException:
            value = None
        if value is not None:
            termination["wait_completed"] = True
            return int(value), termination
    value = _focused_wait_until_reaped(process)
    termination["wait_completed"] = True
    return int(value), termination


def _focused_optional_identity(root: Path, path: Path) -> dict[str, Any] | None:
    if path.is_file() and not is_reparse(path):
        return _input_identity(root, path)
    return None


def _focused_build_child(
    root: Path,
    *,
    arguments: list[str],
    exit_code: int,
    termination: dict[str, Any],
    stdout_path: Path,
    stderr_path: Path,
    observer_path: Path,
) -> dict[str, Any]:
    return {
        "arguments": arguments,
        "exit_code": int(exit_code),
        "termination": termination,
        "stdout": _input_identity(root, stdout_path),
        "stderr": _input_identity(root, stderr_path),
        "observer": _focused_optional_identity(root, observer_path),
    }


def _focused_child_outcome(
    root: Path,
    path: Path,
    *,
    proof: dict[str, Any],
    child: dict[str, Any],
    controller_failure: dict[str, str] | None,
) -> dict[str, Any]:
    outcome = seal_publisher_receipt(
        {
            "schema": PUBLISHER_EVIDENCE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "kind": "publisher-focused-child-outcome",
            "state_sequence": list(FOCUSED_STATE_SEQUENCE),
            "invocation_contract": dict(FOCUSED_INVOCATION_CONTRACT),
            "proof_receipt_sha256": proof["receipt_sha256"],
            "accepted_candidate": proof["accepted_candidate"],
            "child": child,
            "controller_failure": controller_failure,
        }
    )
    _write_once_or_match(path, canonical_json_bytes(outcome))
    return outcome


def focused_run(
    *,
    project_root: Path,
    proof_path: Path,
    output: Path,
) -> tuple[int, dict[str, Any]]:
    """Consume the one-shot sentinel and start at most one direct pytest child."""
    root = literal_project_root(project_root)
    output_root = _output_directory(root, output)
    proof_path, proof_value = _load_contained_json_evidence(
        root, proof_path, label="focused proof"
    )
    proof = verify_focused_proof(root, proof_value)
    result_path = output_root / "focused-result.json"
    sentinel = output_root / "focused-invocation.sentinel"
    stdout_path = output_root / "focused.stdout.bin"
    stderr_path = output_root / "focused.stderr.bin"
    observer_path = output_root / "focused-observer.json"
    started_path = output_root / "focused-started.json"
    child_outcome_path = output_root / "focused-child-outcome.json"
    auxiliary_paths = (
        result_path,
        sentinel,
        stdout_path,
        stderr_path,
        observer_path,
        started_path,
        child_outcome_path,
    )
    if any(_path_exists_without_following(path) for path in auxiliary_paths):
        raise CloseoutError("focused invocation was already attempted; retry is forbidden")
    arguments = _focused_arguments(proof)
    invocation_count = 0
    state = "PROVED"
    child: dict[str, Any] | None = None
    postflight: dict[str, Any] = {}
    failure: dict[str, str] | None = None
    process: Any | None = None
    exit_code: int | None = None
    termination = {
        "terminate_requested": False,
        "kill_requested": False,
        "wait_completed": False,
    }
    child_outcome: dict[str, Any] | None = None
    try:
        lock_record = verify_inherited_validation_lock(root)
        candidate = proof["accepted_candidate"]
        assert_clean_exact_checkout(
            root, candidate["commit"], candidate["tree"]
        )
        # Rehash and cross-check every proof input after the lock is held and
        # immediately before consuming the one-shot sentinel.
        current_proof = verify_focused_proof(
            root, read_json_utf8(proof_path, label="focused proof")
        )
        if current_proof != proof:
            raise CloseoutError("focused proof changed before invocation")
        _exclusive_invocation_sentinel(sentinel, proof["receipt_sha256"])
        state = "SENTINEL_CREATED"
        env = dict(os.environ)
        env[PUBLISHER_FOCUSED_PLUGIN_ENV] = "1"
        env[PUBLISHER_FOCUSED_OBSERVER_ENV] = str(observer_path)
        env[PUBLISHER_FOCUSED_PROOF_ENV] = proof["receipt_sha256"]
        env[PUBLISHER_FOCUSED_PROOF_PATH_ENV] = str(proof_path)
        with stdout_path.open("xb") as stdout_stream, stderr_path.open(
            "xb"
        ) as stderr_stream:
            process = _launch_focused_pytest(
                arguments,
                cwd=root,
                env=env,
                stdout=stdout_stream,
                stderr=stderr_stream,
            )
            invocation_count = 1
            state = "PYTEST_CHILD_STARTED"
            _focused_write_started(
                started_path,
                canonical_json_bytes(
                    {
                        "state": state,
                        "state_sequence": list(FOCUSED_STATE_SEQUENCE),
                        "invocation_contract": dict(FOCUSED_INVOCATION_CONTRACT),
                        "proof_receipt_sha256": proof["receipt_sha256"],
                        "arguments": arguments,
                        "invocation_count": invocation_count,
                    }
                ),
            )
            exit_code = _focused_wait_child(process)
            termination["wait_completed"] = True
            _focused_flush_streams(stdout_stream, stderr_stream)
        state = "CHILD_RESULT_RETAINED"
        child = _focused_build_child(
            root,
            arguments=arguments,
            exit_code=exit_code,
            termination=termination,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            observer_path=observer_path,
        )
        child_outcome = _focused_child_outcome(
            root,
            child_outcome_path,
            proof=proof,
            child=child,
            controller_failure=None,
        )
        postflight = _focused_postflight(
            root, proof, sentinel, lock_record
        )
    except BaseException as exc:
        failure = _compact_failure(exc)
        if invocation_count == 0:
            postflight = {"pytest_not_started": True}
        else:
            assert process is not None
            exit_code, termination = _terminate_and_reap_focused_child(
                process, exit_code
            )
            if child is None:
                # Use the non-injectable emergency constructor after a fault in
                # normal child extraction.
                child = {
                    "arguments": arguments,
                    "exit_code": int(exit_code),
                    "termination": termination,
                    "stdout": _focused_optional_identity(root, stdout_path),
                    "stderr": _focused_optional_identity(root, stderr_path),
                    "observer": _focused_optional_identity(root, observer_path),
                }
            if child_outcome is None:
                child_outcome = _focused_child_outcome(
                    root,
                    child_outcome_path,
                    proof=proof,
                    child=child,
                    controller_failure=failure,
                )
            postflight = {
                "child_result_retained": child is not None,
                "child_outcome_retained": child_outcome is not None,
                "raw_stdout_retained": stdout_path.is_file(),
                "raw_stderr_retained": stderr_path.is_file(),
                "process_reaped": termination["wait_completed"],
            }
        state = "RECOVERING"
    core = {
        "schema": PUBLISHER_EVIDENCE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-focused-result",
        "status": "RECOVERING" if failure else "CHILD_RESULT_RETAINED",
        "state": "RECOVERING" if failure else state,
        "state_sequence": list(FOCUSED_STATE_SEQUENCE),
        "invocation_contract": dict(FOCUSED_INVOCATION_CONTRACT),
        "proof_receipt_sha256": proof["receipt_sha256"],
        "accepted_candidate": proof["accepted_candidate"],
        "invocation_count": invocation_count,
        "child": child,
        "child_outcome": (
            {
                **_input_identity(root, child_outcome_path),
                "receipt_sha256": child_outcome["receipt_sha256"],
            }
            if child_outcome is not None
            else None
        ),
        "postflight": postflight,
        "failure": failure,
    }
    result = seal_publisher_receipt(core)
    _write_once_or_match(result_path, canonical_json_bytes(result))
    return (1 if failure else 0), result


def verify_focused_result(value: Any) -> dict[str, Any]:
    result = verify_publisher_receipt(
        value,
        expected_schema=PUBLISHER_EVIDENCE_SCHEMA,
        expected_kind="publisher-focused-result",
    )
    if set(result) != {
        "schema",
        "schema_version",
        "kind",
        "status",
        "state",
        "state_sequence",
        "invocation_contract",
        "proof_receipt_sha256",
        "accepted_candidate",
        "invocation_count",
        "child",
        "child_outcome",
        "postflight",
        "failure",
        "receipt_sha256",
    }:
        raise CloseoutError("focused result fields are incomplete")
    if (
        result.get("state") not in {"CHILD_RESULT_RETAINED", "RECOVERING"}
        or result.get("state_sequence") != list(FOCUSED_STATE_SEQUENCE)
        or result.get("invocation_contract") != FOCUSED_INVOCATION_CONTRACT
    ):
        raise CloseoutError("focused result state is unsupported")
    invocation_count = result.get("invocation_count")
    if invocation_count not in {0, 1}:
        raise CloseoutError("focused result invocation count is invalid")
    proof_sha = result.get("proof_receipt_sha256")
    if not isinstance(proof_sha, str) or re.fullmatch(
        r"[0-9A-Fa-f]{64}", proof_sha
    ) is None:
        raise CloseoutError("focused result proof binding is malformed")
    candidate = result.get("accepted_candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"commit", "tree"}:
        raise CloseoutError("focused result candidate is malformed")
    require_sha(candidate.get("commit"), label="focused result commit")
    require_sha(candidate.get("tree"), label="focused result tree")
    failure = result.get("failure")
    if failure is not None and (
        not isinstance(failure, dict)
        or set(failure) != {"type", "reason"}
        or not all(isinstance(item, str) and item for item in failure.values())
    ):
        raise CloseoutError("focused result failure is malformed")
    retained = result["state"] == "CHILD_RESULT_RETAINED"
    if (
        retained
        and (
            result.get("status") != "CHILD_RESULT_RETAINED"
            or invocation_count != 1
            or failure is not None
        )
    ) or (
        not retained
        and (result.get("status") != "RECOVERING" or failure is None)
    ):
        raise CloseoutError("focused result status is inconsistent")
    child = result.get("child")
    if child is not None:
        if not isinstance(child, dict) or set(child) != {
            "arguments",
            "exit_code",
            "termination",
            "stdout",
            "stderr",
            "observer",
        }:
            raise CloseoutError("focused result child is malformed")
        if (
            not isinstance(child["arguments"], list)
            or not child["arguments"]
            or not all(isinstance(item, str) and item for item in child["arguments"])
            or not isinstance(child["exit_code"], int)
            or isinstance(child["exit_code"], bool)
        ):
            raise CloseoutError("focused result child process fields are malformed")
        termination = child.get("termination")
        if (
            not isinstance(termination, dict)
            or set(termination)
            != {"terminate_requested", "kill_requested", "wait_completed"}
            or not all(isinstance(item, bool) for item in termination.values())
            or termination["wait_completed"] is not True
        ):
            raise CloseoutError("focused result child was not reaped")
        for name in ("stdout", "stderr", "observer"):
            binding = child[name]
            if binding is None and (name == "observer" or not retained):
                continue
            if (
                not isinstance(binding, dict)
                or set(binding) != {"path", "sha256", "bytes"}
                or not isinstance(binding["path"], str)
                or not binding["path"]
                or not isinstance(binding["sha256"], str)
                or re.fullmatch(r"[0-9A-Fa-f]{64}", binding["sha256"]) is None
                or not isinstance(binding["bytes"], int)
                or isinstance(binding["bytes"], bool)
                or binding["bytes"] < 0
            ):
                raise CloseoutError(f"focused result {name} binding is malformed")
    if retained and child is None:
        raise CloseoutError("focused retained result is missing its child")
    child_outcome = result.get("child_outcome")
    if invocation_count == 1:
        if (
            not isinstance(child_outcome, dict)
            or set(child_outcome)
            != {"path", "sha256", "bytes", "receipt_sha256"}
            or re.fullmatch(
                r"[0-9A-Fa-f]{64}", str(child_outcome.get("receipt_sha256"))
            )
            is None
        ):
            raise CloseoutError("focused child outcome binding is malformed")
    elif child_outcome is not None:
        raise CloseoutError("pre-invocation result cannot bind a child outcome")
    postflight = result.get("postflight")
    if not isinstance(postflight, dict):
        raise CloseoutError("focused result postflight is malformed")
    if retained:
        if set(postflight) != {
            "lock_held",
            "candidate_unchanged",
            "worktree_clean",
            "sentinel_unchanged",
        } or not all(isinstance(item, bool) for item in postflight.values()):
            raise CloseoutError("focused retained-result postflight is malformed")
    elif invocation_count == 0:
        if child is not None or postflight != {"pytest_not_started": True}:
            raise CloseoutError("focused pre-invocation recovery is malformed")
    elif set(postflight) != {
        "child_result_retained",
        "child_outcome_retained",
        "raw_stdout_retained",
        "raw_stderr_retained",
        "process_reaped",
    } or not all(isinstance(item, bool) for item in postflight.values()):
        raise CloseoutError("focused post-invocation recovery is malformed")
    return result


def _verify_focused_child_outcome(
    root: Path,
    binding: dict[str, Any],
    *,
    proof: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    path = _contained_local_evidence_file(
        root, binding.get("path"), label="focused child outcome"
    )
    if (
        binding.get("sha256") != sha256_path(path)
        or binding.get("bytes") != path.stat().st_size
    ):
        raise CloseoutError("focused child outcome bytes drifted")
    outcome = verify_publisher_receipt(
        read_json_utf8(path, label="focused child outcome"),
        expected_schema=PUBLISHER_EVIDENCE_SCHEMA,
        expected_kind="publisher-focused-child-outcome",
    )
    if set(outcome) != {
        "schema",
        "schema_version",
        "kind",
        "state_sequence",
        "invocation_contract",
        "proof_receipt_sha256",
        "accepted_candidate",
        "child",
        "controller_failure",
        "receipt_sha256",
    } or (
        outcome.get("state_sequence") != list(FOCUSED_STATE_SEQUENCE)
        or outcome.get("invocation_contract") != FOCUSED_INVOCATION_CONTRACT
        or outcome.get("proof_receipt_sha256") != proof["receipt_sha256"]
        or outcome.get("accepted_candidate") != proof["accepted_candidate"]
        or outcome.get("child") != result.get("child")
        or outcome.get("receipt_sha256") != binding.get("receipt_sha256")
    ):
        raise CloseoutError("focused child outcome binding is inconsistent")
    controller_failure = outcome.get("controller_failure")
    if result.get("status") == "CHILD_RESULT_RETAINED":
        if controller_failure is not None:
            raise CloseoutError("green child outcome contains a controller failure")
    elif controller_failure not in (None, result.get("failure")):
        raise CloseoutError("recovering child outcome failure differs")
    return outcome


def _verify_focused_observer(
    root: Path,
    binding: dict[str, Any],
    proof: dict[str, Any],
) -> dict[str, Any]:
    path = _contained_local_evidence_file(
        root, binding.get("path"), label="focused pytest observer"
    )
    if (
        binding.get("sha256") != sha256_path(path)
        or binding.get("bytes") != path.stat().st_size
    ):
        raise CloseoutError("focused pytest observer drifted")
    observer = verify_publisher_receipt(
        read_json_utf8(path, label="focused pytest observer"),
        expected_schema=PUBLISHER_EVIDENCE_SCHEMA,
        expected_kind="publisher-focused-observer",
    )
    if set(observer) != {
        "schema",
        "schema_version",
        "kind",
        "proof_receipt_sha256",
        "arguments",
        "exit_code",
        "collected_nodeids",
        "counts",
        "error_ledger",
        "browser_ledger",
        "server_ledger",
        "receipt_sha256",
    }:
        raise CloseoutError("focused pytest observer fields are incomplete")
    nodeids = proof["tests"]["expanded_nodeids"]
    counts = observer.get("counts")
    if (
        observer.get("proof_receipt_sha256") != proof["receipt_sha256"]
        or observer.get("collected_nodeids") != nodeids
        or observer.get("arguments") != _focused_arguments(proof)[4:]
        or observer.get("exit_code") != 0
        or not isinstance(counts, dict)
        or counts
        != {
            "collected": len(nodeids),
            "passed": len(nodeids),
            "failed": 0,
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
        }
        or observer.get("error_ledger") != {"status": "GREEN", "entries": []}
        or observer.get("browser_ledger") != {"status": "GREEN", "entries": []}
        or observer.get("server_ledger") != {"status": "GREEN", "entries": []}
    ):
        raise CloseoutError("focused pytest observer did not satisfy the exact gate")
    return observer


def focused_finalize(
    *,
    project_root: Path,
    proof_path: Path,
    result_path: Path,
    output: Path,
) -> tuple[int, dict[str, Any]]:
    """Read existing proof/result/raw bytes and classify without spawning."""
    root = literal_project_root(project_root)
    output_root = _output_directory(root, output)
    _, proof_value = _load_contained_json_evidence(
        root, proof_path, label="focused proof"
    )
    proof = verify_focused_proof(root, proof_value)
    _, result_value = _load_contained_json_evidence(
        root, result_path, label="focused result"
    )
    result = verify_focused_result(result_value)
    failure: dict[str, str] | None = None
    try:
        if (
            result.get("proof_receipt_sha256") != proof["receipt_sha256"]
            or result.get("accepted_candidate") != proof["accepted_candidate"]
            or result.get("invocation_count") != 1
            or result.get("status") != "CHILD_RESULT_RETAINED"
            or result.get("state") != "CHILD_RESULT_RETAINED"
            or result.get("failure") is not None
        ):
            raise CloseoutError("focused result is not one retained child execution")
        child = result.get("child")
        if (
            not isinstance(child, dict)
            or child.get("arguments") != _focused_arguments(proof)
            or child.get("exit_code") != 0
            or not isinstance(child.get("observer"), dict)
        ):
            raise CloseoutError("focused child result does not match the proof")
        child_outcome_binding = result.get("child_outcome")
        if not isinstance(child_outcome_binding, dict):
            raise CloseoutError("focused child outcome binding is missing")
        _verify_focused_child_outcome(
            root,
            child_outcome_binding,
            proof=proof,
            result=result,
        )
        for stream_name in ("stdout", "stderr"):
            binding = child.get(stream_name)
            if not isinstance(binding, dict):
                raise CloseoutError(f"focused {stream_name} binding is missing")
            stream = _contained_local_evidence_file(
                root, binding.get("path"), label=f"focused {stream_name}"
            )
            if (
                binding.get("sha256") != sha256_path(stream)
                or binding.get("bytes") != stream.stat().st_size
            ):
                raise CloseoutError(f"focused {stream_name} bytes drifted")
        _verify_focused_observer(root, child["observer"], proof)
        postflight = result.get("postflight")
        if (
            not isinstance(postflight, dict)
            or set(postflight)
            != {
                "lock_held",
                "candidate_unchanged",
                "worktree_clean",
                "sentinel_unchanged",
            }
            or not all(value is True for value in postflight.values())
        ):
            raise CloseoutError("focused postflight is not completely green")
    except (OSError, CloseoutError) as exc:
        failure = _compact_failure(exc)
    core = {
        "schema": PUBLISHER_EVIDENCE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "publisher-focused-verdict",
        "status": "RECOVERING" if failure else "FOCUSED_GATE_PASS",
        "state": "RECOVERING" if failure else "PASS",
        "state_sequence": list(FOCUSED_STATE_SEQUENCE),
        "invocation_contract": dict(FOCUSED_INVOCATION_CONTRACT),
        "proof_receipt_sha256": proof["receipt_sha256"],
        "result_receipt_sha256": result["receipt_sha256"],
        "accepted_candidate": proof["accepted_candidate"],
        "invocation_count": result.get("invocation_count"),
        "failure": failure,
    }
    verdict = seal_publisher_receipt(core)
    atomic_write(
        output_root / "focused-verdict.json", canonical_json_bytes(verdict)
    )
    return (1 if failure else 0), verdict


class _FocusedPytestObserver:
    """Opt-in pytest plugin; importing this module alone has no pytest effect."""

    def __init__(self, output: Path, proof_sha256: str, arguments: list[str]):
        self.output = output
        self.proof_sha256 = proof_sha256
        self.arguments = arguments
        self.collected: list[str] = []
        self.passed: set[str] = set()
        self.failed: set[str] = set()
        self.errors: set[str] = set()
        self.skipped: set[str] = set()
        self.xpassed: set[str] = set()
        self.xfailed: set[str] = set()
        self.internal_errors: list[dict[str, str]] = []
        self.collection_errors: list[dict[str, str]] = []
        self.unexpected_errors: list[dict[str, str]] = []
        self.browser_errors: list[dict[str, str]] = []
        self.server_errors: list[dict[str, str]] = []

    def pytest_collection_finish(self, session: Any) -> None:
        self.collected = [item.nodeid for item in session.items]

    @staticmethod
    def _structured_property(
        report: Any, key: str
    ) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for name, raw in getattr(report, "user_properties", ()) or ():
            if name != key:
                continue
            if (
                not isinstance(raw, dict)
                or set(raw) != {"code", "message"}
                or not isinstance(raw.get("code"), str)
                or re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{0,63}", raw["code"])
                is None
                or not isinstance(raw.get("message"), str)
                or not raw["message"]
            ):
                entries.append(
                    {
                        "kind": "malformed-structured-evidence",
                        "nodeid": str(getattr(report, "nodeid", "")),
                        "when": str(getattr(report, "when", "")),
                        "code": "MALFORMED",
                        "message": f"{key} was malformed",
                    }
                )
                continue
            entry = {
                "kind": key,
                "nodeid": str(getattr(report, "nodeid", "")),
                "when": str(getattr(report, "when", "")),
                "code": raw["code"],
                "message": raw["message"][:240],
            }
            reject_private_evidence_fields(entry)
            entries.append(entry)
        return entries

    def pytest_runtest_logreport(self, report: Any) -> None:
        nodeid = report.nodeid
        was_xfail = bool(getattr(report, "wasxfail", False))
        if report.when == "call" and was_xfail and report.passed:
            self.xpassed.add(nodeid)
        elif report.when == "call" and was_xfail and report.failed:
            # Strict XPASS is reported as a call failure by pytest.
            self.xpassed.add(nodeid)
        elif report.skipped and was_xfail:
            self.xfailed.add(nodeid)
        elif report.skipped:
            self.skipped.add(nodeid)
        elif report.failed:
            if report.when == "call":
                self.failed.add(nodeid)
            else:
                self.errors.add(nodeid)
        elif report.when == "call" and report.passed:
            self.passed.add(nodeid)
        unexpected = self._structured_property(
            report, "publisher_unexpected_error"
        )
        browser = self._structured_property(report, "publisher_browser_error")
        server = self._structured_property(report, "publisher_server_error")
        self.unexpected_errors.extend(unexpected)
        self.browser_errors.extend(browser)
        self.server_errors.extend(server)
        # Malformed structured Browser/server entries are unexpected errors as
        # well; they can never disappear into a filename/marker heuristic.
        self.unexpected_errors.extend(
            entry
            for entry in [*browser, *server]
            if entry["kind"] == "malformed-structured-evidence"
        )

    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self.collection_errors.append(
                {
                    "kind": "collection-error",
                    "nodeid": str(getattr(report, "nodeid", "")),
                    "when": "collect",
                    "code": "PYTEST_COLLECTION_ERROR",
                    "message": str(getattr(report, "longrepr", ""))[:240],
                }
            )

    def pytest_internalerror(self, excrepr: Any, excinfo: Any) -> None:
        self.internal_errors.append(
            {
                "kind": "pytest-internal-error",
                "nodeid": "",
                "when": "internal",
                "code": "PYTEST_INTERNAL_ERROR",
                "message": str(excrepr)[:240],
            }
        )

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        terminal = (
            self.passed
            | self.failed
            | self.errors
            | self.skipped
            | self.xpassed
            | self.xfailed
        )
        not_run = sorted(set(self.collected) - terminal)
        error_entries: list[dict[str, str]] = [
            *(
                {
                    "kind": kind,
                    "nodeid": nodeid,
                    "when": "call" if kind in {"failed", "xpassed"} else "test",
                    "code": kind.upper(),
                    "message": kind,
                }
                for kind, values in (
                    ("failed", self.failed),
                    ("errors", self.errors),
                    ("skipped", self.skipped),
                    ("xpassed", self.xpassed),
                    ("xfailed", self.xfailed),
                    ("not_run", set(not_run)),
                )
                for nodeid in sorted(values)
            ),
            *self.internal_errors,
            *self.collection_errors,
            *self.unexpected_errors,
        ]
        error_entries = sorted(
            error_entries,
            key=lambda item: (
                item["kind"],
                item["nodeid"],
                item["when"],
                item["code"],
                item["message"],
            ),
        )
        browser_entries = sorted(
            self.browser_errors,
            key=lambda item: (
                item["nodeid"],
                item["when"],
                item["code"],
                item["message"],
            ),
        )
        server_entries = sorted(
            self.server_errors,
            key=lambda item: (
                item["nodeid"],
                item["when"],
                item["code"],
                item["message"],
            ),
        )
        core = {
            "schema": PUBLISHER_EVIDENCE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "kind": "publisher-focused-observer",
            "proof_receipt_sha256": self.proof_sha256,
            "arguments": self.arguments,
            "exit_code": int(exitstatus),
            "collected_nodeids": self.collected,
            "counts": {
                "collected": len(self.collected),
                "passed": len(self.passed),
                "failed": len(self.failed),
                "errors": len(self.errors),
                "skipped": len(self.skipped),
                "xpassed": len(self.xpassed),
                "xfailed": len(self.xfailed),
                "not_run": len(not_run),
                "internal_errors": len(self.internal_errors),
                "collection_errors": len(self.collection_errors),
                "unexpected_errors": len(self.unexpected_errors),
                "browser_errors": len(self.browser_errors),
                "server_errors": len(self.server_errors),
            },
            "error_ledger": {
                "status": "GREEN" if not error_entries else "RED",
                "entries": error_entries,
            },
            "browser_ledger": {
                "status": "GREEN" if not browser_entries else "RED",
                "entries": browser_entries,
            },
            "server_ledger": {
                "status": "GREEN" if not server_entries else "RED",
                "entries": server_entries,
            },
        }
        _write_once_or_match(
            self.output, canonical_json_bytes(seal_publisher_receipt(core))
        )


def pytest_configure(config: Any) -> None:
    """Register the observer only for the explicit one-shot child."""
    if os.environ.get(PUBLISHER_FOCUSED_PLUGIN_ENV) != "1":
        return
    output = os.environ.get(PUBLISHER_FOCUSED_OBSERVER_ENV)
    proof_sha256 = os.environ.get(PUBLISHER_FOCUSED_PROOF_ENV)
    proof_path = os.environ.get(PUBLISHER_FOCUSED_PROOF_PATH_ENV)
    if (
        not output
        or not proof_sha256
        or not proof_path
        or re.fullmatch(r"[0-9A-Fa-f]{64}", proof_sha256) is None
    ):
        raise CloseoutError("focused pytest observer environment is incomplete")
    root = literal_project_root(Path.cwd())
    _, proof_value = _load_contained_json_evidence(
        root, proof_path, label="focused pytest observer proof"
    )
    proof = verify_focused_proof(root, proof_value)
    if (
        proof["receipt_sha256"] != proof_sha256.upper()
        or list(config.invocation_params.args) != _focused_arguments(proof)[4:]
    ):
        raise CloseoutError(
            "focused pytest observer arguments do not match the sealed proof"
        )
    plugin = _FocusedPytestObserver(
        Path(output),
        proof["receipt_sha256"],
        list(config.invocation_params.args),
    )
    config.pluginmanager.register(plugin, "publisher-focused-observer")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sealed local Publisher closeout automation.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--python-path", required=True, type=Path)
    preflight_parser.add_argument("--config", required=True, type=Path)
    preflight_parser.add_argument("--output", required=True, type=Path)
    proof_parser = subparsers.add_parser("focused-proof")
    proof_parser.add_argument("--python-path", required=True, type=Path)
    proof_parser.add_argument("--preflight-receipt", required=True, type=Path)
    proof_parser.add_argument("--plan", required=True, type=Path)
    proof_parser.add_argument("--validation-identity", required=True, type=Path)
    proof_parser.add_argument("--output", required=True, type=Path)
    run_parser = subparsers.add_parser("focused-run")
    run_parser.add_argument("--proof", required=True, type=Path)
    run_parser.add_argument("--output", required=True, type=Path)
    finalize_parser = subparsers.add_parser("focused-finalize")
    finalize_parser.add_argument("--proof", required=True, type=Path)
    finalize_parser.add_argument("--result", required=True, type=Path)
    finalize_parser.add_argument("--output", required=True, type=Path)
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
        if args.command == "focused-proof":
            result = focused_proof(
                project_root=args.project_root,
                python_path=args.python_path,
                preflight_receipt_path=args.preflight_receipt,
                plan_path=args.plan,
                validation_identity_path=args.validation_identity,
                output=args.output,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "focused-run":
            exit_code, result = focused_run(
                project_root=args.project_root,
                proof_path=args.proof,
                output=args.output,
            )
            print(json.dumps(result, sort_keys=True))
            return exit_code
        if args.command == "focused-finalize":
            exit_code, result = focused_finalize(
                project_root=args.project_root,
                proof_path=args.proof,
                result_path=args.result,
                output=args.output,
            )
            print(json.dumps(result, sort_keys=True))
            return exit_code
        exit_code, result = dispose(project_root=args.project_root, plan_path=args.plan, formal_close_receipt_path=args.formal_close_receipt, output=args.output, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        return exit_code
    except (OSError, CloseoutError) as exc:
        print(f"Publisher closeout error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
