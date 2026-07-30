"""Deterministic validation identity, reuse, and compact failure receipts.

This module deliberately does not run tests, measurements, Git transport,
deployments, or live checks.  It records the identities that those gates bind
to and makes reuse decisions explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePath
from typing import Any, Iterable, Mapping


SCHEMA = "campaign-player-wiki.validation-evidence"
SCHEMA_VERSION = 1
SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
FORBIDDEN_FIELD_PATTERN = re.compile(
    r"(?:^|_)(?:secret|secrets|password|passwords|credential|credentials|token|tokens|private)(?:_|$)",
    re.IGNORECASE,
)
REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
FREEZE_REQUIRED_KEYS = frozenset(
    {
        "candidate_commit",
        "fly_blobs",
        "dependencies",
        "runner",
        "envelope",
        "suite",
        "invalidators",
    }
)
FILE_IDENTITY_KEYS = frozenset({"path", "sha256"})
DEPENDENCY_IDENTITY_KEYS = frozenset({"path", "sha256", "package_count"})
SUITE_KEYS = frozenset({"verdict", "index", "seal"})
FROZEN_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "kind",
        "candidate",
        "fly_blobs",
        "interpreter",
        "dependencies",
        "runner",
        "envelope",
        "suite",
        "invalidators",
        "root",
        "receipt_sha256",
    }
)
CANDIDATE_KEYS = frozenset(
    {
        "commit",
        "tree",
        "runtime_tree",
        "tests_tree",
        "workflow_tree",
    }
)
FLY_BLOB_KEYS = frozenset({"path", "blob"})
INTERPRETER_KEYS = frozenset(
    {
        "implementation",
        "version",
        "executable_sha256",
    }
)
ALLOWED_REUSE_DOC_PREFIXES = (
    "docs/current-state/",
    "docs/contracts/",
)
RAW_DIFF_PATTERN = re.compile(
    r"^:([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40}) ([0-9a-f]{40}) ([A-Z])$"
)
FAILURE_REQUIRED_KEYS = frozenset(
    {
        "candidate",
        "gate",
        "classification",
        "timestamp",
        "artifact_pointer",
        "fingerprints",
        "next_action",
    }
)


class EvidenceError(RuntimeError):
    """A validation-evidence contract refusal."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _reject_duplicate_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read canonical JSON input {path.name}: {exc}") from exc
    reject_private_fields(value)
    return value


def reject_private_fields(value: Any, *, location: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            if not isinstance(raw_key, str):
                raise EvidenceError(f"{location} contains a non-string field name")
            if FORBIDDEN_FIELD_PATTERN.search(raw_key):
                raise EvidenceError(f"{location} contains forbidden private field name: {raw_key}")
            reject_private_fields(child, location=f"{location}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_private_fields(child, location=f"{location}[{index}]")


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & REPARSE_FLAG)


def _literal_ancestors(path: Path) -> list[Path]:
    current = path
    result = [current]
    while current.parent != current:
        current = current.parent
        result.append(current)
    result.reverse()
    return result


def normalize_repo_root(raw_root: str | os.PathLike[str]) -> Path:
    root = Path(os.path.abspath(os.fspath(raw_root)))
    if not root.is_dir():
        raise EvidenceError("repo root must be an existing directory")
    for ancestor in _literal_ancestors(root):
        if ancestor.exists() and _is_reparse(ancestor):
            raise EvidenceError("repo root contains a reparse path")
    if run_git(root, "rev-parse", "--show-toplevel") != str(root).replace("\\", "/"):
        # Git prints slash-normalized absolute paths on Windows.
        reported = Path(run_git(root, "rev-parse", "--show-toplevel"))
        if os.path.normcase(os.path.abspath(reported)) != os.path.normcase(str(root)):
            raise EvidenceError("repo root must be the Git top level")
    return root


def _has_traversal(raw: str) -> bool:
    return any(part == ".." for part in PurePath(raw.replace("\\", "/")).parts)


def _contained(path: Path, root: Path) -> bool:
    try:
        common = os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root))))
    except ValueError:
        return False
    return common == os.path.normcase(str(root))


def resolve_contained_path(
    raw_path: str | os.PathLike[str],
    root: Path,
    *,
    label: str,
    must_exist: bool,
    require_file: bool = False,
    allow_root: bool = False,
) -> Path:
    raw = os.fspath(raw_path)
    if not raw or _has_traversal(raw):
        raise EvidenceError(f"{label} contains traversal or is empty")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = Path(os.path.abspath(candidate))
    if not _contained(candidate, root) or (candidate == root and not allow_root):
        raise EvidenceError(f"{label} must stay inside the repo root")
    for ancestor in _literal_ancestors(candidate):
        if not _contained(ancestor, root) and ancestor != root:
            continue
        if ancestor.exists() and _is_reparse(ancestor):
            raise EvidenceError(f"{label} contains a reparse path")
    if must_exist and not candidate.exists():
        raise EvidenceError(f"{label} does not exist")
    if require_file and (not candidate.is_file() or _is_reparse(candidate)):
        raise EvidenceError(f"{label} must be a normal file")
    return candidate


def repo_relative(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return relative or "."


def validate_repo_relative(
    raw_path: Any,
    root: Path,
    *,
    label: str,
    must_exist: bool,
    require_file: bool = False,
) -> tuple[Path, str]:
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise EvidenceError(f"{label} must be a non-empty repo-relative path")
    path = resolve_contained_path(
        raw_path,
        root,
        label=label,
        must_exist=must_exist,
        require_file=require_file,
    )
    return path, repo_relative(path, root)


def atomic_write(path: Path, payload: bytes, *, root: Path) -> None:
    path = resolve_contained_path(
        path,
        root,
        label="output",
        must_exist=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    resolve_contained_path(
        path.parent,
        root,
        label="output parent",
        must_exist=True,
        allow_root=True,
    )
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def run_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise EvidenceError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def run_git_bytes(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise EvidenceError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def require_sha1(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SHA1_PATTERN.fullmatch(value):
        raise EvidenceError(f"{label} must be a full lowercase 40-character Git object ID")
    return value


def require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise EvidenceError(f"{label} must be a full 64-character SHA-256")
    return value.upper()


def require_name(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value):
        raise EvidenceError(f"{label} must be a bounded typed identifier")
    return value


def require_text(value: Any, *, label: str, maximum: int = 128) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise EvidenceError(f"{label} must be a non-empty bounded string")
    return value


def require_exact_keys(value: Any, expected: frozenset[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise EvidenceError(f"{label} fields mismatch; missing={missing} extra={extra}")
    return value


def seal_receipt(core: dict[str, Any]) -> dict[str, Any]:
    reject_private_fields(core)
    return {**core, "receipt_sha256": sha256_bytes(canonical_json_bytes(core))}


def verify_sealed_payload(
    value: Any,
    *,
    expected_schema: str,
    expected_kind: str,
    expected_schema_version: int = SCHEMA_VERSION,
    hash_field: str = "receipt_sha256",
) -> dict[str, Any]:
    """Verify any canonical self-hashed receipt without owning its schema.

    Downstream Publisher, measurement, and closeout tools can use this helper
    while retaining their own schema and kind names.  The hash always covers
    the complete payload except for the named hash field.
    """

    if not isinstance(value, dict):
        raise EvidenceError("receipt must be an object")
    reject_private_fields(value)
    if (
        value.get("schema") != expected_schema
        or value.get("schema_version") != expected_schema_version
    ):
        raise EvidenceError("receipt schema is unsupported")
    if value.get("kind") != expected_kind:
        raise EvidenceError(f"expected a {expected_kind} receipt")
    claimed = require_sha256(value.get(hash_field), label=hash_field)
    core = {key: item for key, item in value.items() if key != hash_field}
    if sha256_bytes(canonical_json_bytes(core)) != claimed:
        raise EvidenceError("receipt hash does not match canonical content")
    return value


def verify_receipt(value: Any, *, expected_kind: str) -> dict[str, Any]:
    return verify_sealed_payload(
        value,
        expected_schema=SCHEMA,
        expected_kind=expected_kind,
    )


def _require_git_object(root: Path, object_id: str, object_type: str, *, label: str) -> None:
    try:
        actual_type = run_git(root, "cat-file", "-t", object_id)
    except EvidenceError as exc:
        raise EvidenceError(f"{label} is not an object in the supplied repository") from exc
    if actual_type != object_type:
        raise EvidenceError(f"{label} must identify a Git {object_type}")


def _verify_candidate_receipt(value: Any, root: Path) -> dict[str, str]:
    candidate = require_exact_keys(value, CANDIDATE_KEYS, label="candidate")
    normalized = {
        key: require_sha1(candidate[key], label=f"candidate.{key}")
        for key in CANDIDATE_KEYS
    }
    commit = normalized["commit"]
    _require_git_object(root, commit, "commit", label="candidate.commit")
    expected = {
        "tree": run_git(root, "rev-parse", f"{commit}^{{tree}}"),
        "runtime_tree": run_git(root, "rev-parse", f"{commit}:player_wiki"),
        "tests_tree": run_git(root, "rev-parse", f"{commit}:tests"),
        "workflow_tree": run_git(root, "rev-parse", f"{commit}:docs/workflows"),
    }
    for field, actual in expected.items():
        actual = require_sha1(actual, label=f"actual candidate.{field}")
        _require_git_object(root, actual, "tree", label=f"candidate.{field}")
        if normalized[field] != actual:
            raise EvidenceError(
                f"candidate.{field} does not match candidate.commit in the supplied repository"
            )
    return {
        "commit": commit,
        "tree": normalized["tree"],
        "runtime_tree": normalized["runtime_tree"],
        "tests_tree": normalized["tests_tree"],
        "workflow_tree": normalized["workflow_tree"],
    }


def _git_path_object(root: Path, commit: str, relative: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", f"{commit}:{relative}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return require_sha1(result.stdout.strip(), label=f"{relative} object")


def _require_ignored_path(root: Path, relative: str, *, label: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", relative],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise EvidenceError(f"{label} must be tracked at the candidate or retained ignored evidence")


def _verify_receipt_file_identity(
    value: Any,
    root: Path,
    commit: str,
    *,
    label: str,
    dependency: bool = False,
) -> dict[str, Any]:
    expected = DEPENDENCY_IDENTITY_KEYS if dependency else FILE_IDENTITY_KEYS
    identity = require_exact_keys(value, expected, label=label)
    raw_path = identity["path"]
    path, relative = validate_repo_relative(
        raw_path,
        root,
        label=f"{label}.path",
        must_exist=False,
    )
    if raw_path != relative:
        raise EvidenceError(f"{label}.path must use normalized repo-relative form")
    expected_hash = require_sha256(identity["sha256"], label=f"{label}.sha256")
    object_id = _git_path_object(root, commit, relative)
    if object_id is not None:
        _require_git_object(root, object_id, "blob", label=f"{label}.path")
        actual_hash = sha256_bytes(
            run_git_bytes(root, "show", f"{commit}:{relative}")
        )
    else:
        path = resolve_contained_path(
            path,
            root,
            label=f"{label}.path",
            must_exist=True,
            require_file=True,
        )
        _require_ignored_path(root, relative, label=f"{label}.path")
        actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise EvidenceError(f"{label} SHA-256 does not match candidate-bound content at {relative}")
    result: dict[str, Any] = {"path": relative, "sha256": actual_hash}
    if dependency:
        package_count = identity["package_count"]
        if (
            not isinstance(package_count, int)
            or isinstance(package_count, bool)
            or package_count <= 0
        ):
            raise EvidenceError(f"{label}.package_count must be a positive integer")
        result["package_count"] = package_count
    return result


def _verify_receipt_fly_blobs(
    value: Any,
    root: Path,
    commit: str,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise EvidenceError("fly_blobs must be a non-empty array")
    result: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, raw_identity in enumerate(value):
        identity = require_exact_keys(
            raw_identity,
            FLY_BLOB_KEYS,
            label=f"fly_blobs[{index}]",
        )
        raw_path = identity["path"]
        _, relative = validate_repo_relative(
            raw_path,
            root,
            label=f"fly_blobs[{index}].path",
            must_exist=False,
        )
        if raw_path != relative:
            raise EvidenceError(
                f"fly_blobs[{index}].path must use normalized repo-relative form"
            )
        if relative in seen_paths:
            raise EvidenceError("fly_blobs contains a duplicate path")
        blob = require_sha1(identity["blob"], label=f"fly_blobs[{index}].blob")
        actual = _git_path_object(root, commit, relative)
        if actual is None:
            raise EvidenceError(f"fly_blobs[{index}].path is not tracked at candidate.commit")
        _require_git_object(root, actual, "blob", label=f"fly_blobs[{index}].blob")
        if actual != blob:
            raise EvidenceError(f"fly_blobs[{index}] does not match {relative}")
        seen_paths.add(relative)
        result.append({"path": relative, "blob": blob})
    if result != sorted(result, key=lambda item: item["path"]):
        raise EvidenceError("fly_blobs must be sorted by path")
    return result


def verify_frozen_identity(root: Path, value: Any) -> dict[str, Any]:
    """Verify a frozen identity's complete schema and repository bindings."""

    receipt = verify_receipt(value, expected_kind="FROZEN_IDENTITY")
    receipt = require_exact_keys(receipt, FROZEN_RECEIPT_KEYS, label="FROZEN_IDENTITY")
    if (
        not isinstance(receipt["schema_version"], int)
        or isinstance(receipt["schema_version"], bool)
        or receipt["schema_version"] != SCHEMA_VERSION
    ):
        raise EvidenceError("schema_version must be the supported integer")
    if receipt["root"] != ".":
        raise EvidenceError("root must be '.'")
    candidate = _verify_candidate_receipt(receipt["candidate"], root)
    interpreter_raw = require_exact_keys(
        receipt["interpreter"],
        INTERPRETER_KEYS,
        label="interpreter",
    )
    interpreter = {
        "implementation": require_name(
            interpreter_raw["implementation"],
            label="interpreter.implementation",
        ),
        "version": require_text(
            interpreter_raw["version"],
            label="interpreter.version",
        ),
        "executable_sha256": require_sha256(
            interpreter_raw["executable_sha256"],
            label="interpreter.executable_sha256",
        ),
    }
    dependencies = _verify_receipt_file_identity(
        receipt["dependencies"],
        root,
        candidate["commit"],
        label="dependencies",
        dependency=True,
    )
    runner = _verify_receipt_file_identity(
        receipt["runner"],
        root,
        candidate["commit"],
        label="runner",
    )
    envelope = _verify_receipt_file_identity(
        receipt["envelope"],
        root,
        candidate["commit"],
        label="envelope",
    )
    suite_raw = require_exact_keys(receipt["suite"], SUITE_KEYS, label="suite")
    suite = {
        name: _verify_receipt_file_identity(
            suite_raw[name],
            root,
            candidate["commit"],
            label=f"suite.{name}",
        )
        for name in ("verdict", "index", "seal")
    }
    fly_blobs = _verify_receipt_fly_blobs(
        receipt["fly_blobs"],
        root,
        candidate["commit"],
    )
    identity_paths = [
        dependencies["path"],
        runner["path"],
        envelope["path"],
        *(item["path"] for item in suite.values()),
        *(item["path"] for item in fly_blobs),
    ]
    if len(identity_paths) != len(set(identity_paths)):
        raise EvidenceError("file identities must use distinct paths")
    invalidators = _verify_invalidators(receipt["invalidators"])
    if receipt["invalidators"] != invalidators:
        raise EvidenceError("invalidators must be unique and sorted")
    return receipt


def _verify_clean_candidate(root: Path, expected_commit: Any) -> dict[str, str]:
    commit = require_sha1(expected_commit, label="candidate_commit")
    status = run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise EvidenceError(f"freeze requires a clean repo root: {status}")
    head = require_sha1(run_git(root, "rev-parse", "HEAD"), label="HEAD")
    if head != commit:
        raise EvidenceError(f"candidate_commit {commit} does not match HEAD {head}")
    tree = require_sha1(
        run_git(root, "rev-parse", f"{commit}^{{tree}}"),
        label="candidate tree",
    )
    index_tree = require_sha1(run_git(root, "write-tree"), label="index tree")
    if tree != index_tree:
        raise EvidenceError("candidate tree and index tree differ")
    runtime_tree = require_sha1(
        run_git(root, "rev-parse", f"{commit}:player_wiki"),
        label="runtime tree",
    )
    tests_tree = require_sha1(
        run_git(root, "rev-parse", f"{commit}:tests"),
        label="tests tree",
    )
    workflow_tree = require_sha1(
        run_git(root, "rev-parse", f"{commit}:docs/workflows"),
        label="workflow tree",
    )
    return {
        "commit": commit,
        "tree": tree,
        "runtime_tree": runtime_tree,
        "tests_tree": tests_tree,
        "workflow_tree": workflow_tree,
    }


def _verify_file_identity(
    value: Any,
    root: Path,
    *,
    label: str,
    dependency: bool = False,
) -> dict[str, Any]:
    expected = DEPENDENCY_IDENTITY_KEYS if dependency else FILE_IDENTITY_KEYS
    identity = require_exact_keys(value, expected, label=label)
    path, relative = validate_repo_relative(
        identity["path"],
        root,
        label=f"{label}.path",
        must_exist=True,
        require_file=True,
    )
    expected_hash = require_sha256(identity["sha256"], label=f"{label}.sha256")
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise EvidenceError(f"{label} SHA-256 does not match {relative}")
    result: dict[str, Any] = {"path": relative, "sha256": actual_hash}
    if dependency:
        package_count = identity["package_count"]
        if not isinstance(package_count, int) or isinstance(package_count, bool) or package_count <= 0:
            raise EvidenceError(f"{label}.package_count must be a positive integer")
        result["package_count"] = package_count
    return result


def _verify_fly_blobs(value: Any, root: Path, commit: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise EvidenceError("fly_blobs must be a non-empty array")
    result: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    seen_blobs: set[str] = set()
    for index, raw_identity in enumerate(value):
        identity = require_exact_keys(
            raw_identity,
            frozenset({"path", "blob"}),
            label=f"fly_blobs[{index}]",
        )
        _, relative = validate_repo_relative(
            identity["path"],
            root,
            label=f"fly_blobs[{index}].path",
            must_exist=True,
            require_file=True,
        )
        blob = require_sha1(identity["blob"], label=f"fly_blobs[{index}].blob")
        actual = require_sha1(
            run_git(root, "rev-parse", f"{commit}:{relative}"),
            label=f"fly_blobs[{index}] actual blob",
        )
        if run_git(root, "cat-file", "-t", actual) != "blob":
            raise EvidenceError(f"fly_blobs[{index}] does not identify a Git blob")
        if actual != blob:
            raise EvidenceError(f"fly_blobs[{index}] does not match {relative}")
        if relative in seen_paths or blob in seen_blobs:
            raise EvidenceError("fly_blobs contains a duplicate path or identity")
        seen_paths.add(relative)
        seen_blobs.add(blob)
        result.append({"path": relative, "blob": blob})
    return sorted(result, key=lambda item: item["path"])


def _verify_invalidators(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise EvidenceError("invalidators must be a non-empty array")
    normalized = [require_name(item, label="invalidator") for item in value]
    if len(set(normalized)) != len(normalized):
        raise EvidenceError("invalidators contains duplicates")
    return sorted(normalized)


def build_frozen_identity(root: Path, config: Any) -> dict[str, Any]:
    config = require_exact_keys(config, FREEZE_REQUIRED_KEYS, label="freeze config")
    candidate = _verify_clean_candidate(root, config["candidate_commit"])
    dependencies = _verify_file_identity(
        config["dependencies"],
        root,
        label="dependencies",
        dependency=True,
    )
    runner = _verify_file_identity(config["runner"], root, label="runner")
    envelope = _verify_file_identity(config["envelope"], root, label="envelope")
    suite_raw = require_exact_keys(config["suite"], SUITE_KEYS, label="suite")
    suite = {
        name: _verify_file_identity(suite_raw[name], root, label=f"suite.{name}")
        for name in ("verdict", "index", "seal")
    }
    identity_paths = [
        dependencies["path"],
        runner["path"],
        envelope["path"],
        *(item["path"] for item in suite.values()),
    ]
    if len(identity_paths) != len(set(identity_paths)):
        raise EvidenceError("file identities must use distinct paths")
    interpreter_path = Path(sys.executable)
    interpreter = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executable_sha256": sha256_file(interpreter_path),
    }
    core = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "FROZEN_IDENTITY",
        "candidate": candidate,
        "fly_blobs": _verify_fly_blobs(
            config["fly_blobs"],
            root,
            candidate["commit"],
        ),
        "interpreter": interpreter,
        "dependencies": dependencies,
        "runner": runner,
        "envelope": envelope,
        "suite": suite,
        "invalidators": _verify_invalidators(config["invalidators"]),
        "root": ".",
    }
    return seal_receipt(core)


def _identity_changed(baseline: Mapping[str, Any], current: Mapping[str, Any], key: str) -> bool:
    return baseline.get(key) != current.get(key)


def _commit_is_ancestor(root: Path, baseline_commit: str, current_commit: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "merge-base",
            "--is-ancestor",
            baseline_commit,
            current_commit,
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise EvidenceError(f"cannot classify candidate ancestry: {detail}")
    return result.returncode == 0


def _commit_diff(root: Path, baseline_commit: str, current_commit: str) -> list[dict[str, str]]:
    payload = run_git_bytes(
        root,
        "diff-tree",
        "--no-commit-id",
        "--no-abbrev",
        "--no-renames",
        "--raw",
        "-z",
        "-r",
        baseline_commit,
        current_commit,
    )
    if not payload:
        return []
    fields = payload.split(b"\0")
    if fields[-1] != b"":
        raise EvidenceError("Git diff did not end at a path boundary")
    fields.pop()
    if len(fields) % 2:
        raise EvidenceError("Git diff contains an incomplete path record")
    result: list[dict[str, str]] = []
    for offset in range(0, len(fields), 2):
        try:
            header = fields[offset].decode("ascii")
            path = fields[offset + 1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceError("Git diff contains a non-UTF-8 path or malformed header") from exc
        match = RAW_DIFF_PATTERN.fullmatch(header)
        if match is None:
            raise EvidenceError(f"Git diff contains an unsupported raw record: {header}")
        old_mode, new_mode, _old_object, _new_object, status_code = match.groups()
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or _has_traversal(path)
        ):
            raise EvidenceError(f"Git diff contains an unsafe path: {path!r}")
        result.append(
            {
                "path": path,
                "old_mode": old_mode,
                "new_mode": new_mode,
                "status": status_code,
            }
        )
    return result


def _classify_descendant_diff(
    entries: list[dict[str, str]],
) -> tuple[bool, list[str], list[str]]:
    if not entries:
        return True, ["HISTORY_ONLY_DESCENDANT"], []
    reasons: list[str] = []
    changed: list[str] = []
    for entry in entries:
        path = entry["path"]
        old_mode = entry["old_mode"]
        new_mode = entry["new_mode"]
        status_code = entry["status"]
        changed.append(f"git.path:{path}")
        nonzero_modes = {mode for mode in (old_mode, new_mode) if mode != "000000"}
        mode_is_safe = nonzero_modes <= {"100644"}
        modified_mode_changed = status_code == "M" and old_mode != new_mode
        if not mode_is_safe or modified_mode_changed:
            reasons.append(f"MODE_DRIFT:{path}:{old_mode}->{new_mode}")
        if status_code not in {"A", "D", "M"}:
            reasons.append(f"UNSUPPORTED_DIFF_STATUS:{status_code}:{path}")
        if not path.startswith(ALLOWED_REUSE_DOC_PREFIXES):
            reasons.append(f"UNBOUND_PATH_DRIFT:{path}")
    if reasons:
        return False, reasons, changed
    return True, ["DOCS_HISTORY_ONLY_DESCENDANT"], changed


def build_reuse_decision(
    root: Path,
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    application_ambiguity: bool,
) -> dict[str, Any]:
    baseline = verify_frozen_identity(root, baseline)
    current = verify_frozen_identity(root, current)
    reasons: list[str] = []
    changed: list[str] = []
    baseline_candidate = baseline["candidate"]
    current_candidate = current["candidate"]
    for field, reason in (
        ("runtime_tree", "RUNTIME_TREE_DRIFT"),
        ("tests_tree", "TESTS_TREE_DRIFT"),
    ):
        if baseline_candidate.get(field) != current_candidate.get(field):
            changed.append(f"candidate.{field}")
            reasons.append(reason)
    if application_ambiguity:
        reasons.append("APPLICATION_AMBIGUITY")
    if reasons:
        decision = "INVALIDATE"
    else:
        reclassifiers: list[tuple[bool, str, str]] = [
            (
                baseline_candidate.get("workflow_tree")
                != current_candidate.get("workflow_tree"),
                "candidate.workflow_tree",
                "WORKFLOW_TREE_DRIFT",
            ),
            (_identity_changed(baseline, current, "runner"), "runner", "RUNNER_DRIFT"),
            (_identity_changed(baseline, current, "envelope"), "envelope", "ENVELOPE_DRIFT"),
            (
                _identity_changed(baseline, current, "interpreter"),
                "interpreter",
                "INTERPRETER_DRIFT",
            ),
            (
                _identity_changed(baseline, current, "dependencies"),
                "dependencies",
                "DEPENDENCY_DRIFT",
            ),
            (_identity_changed(baseline, current, "fly_blobs"), "fly_blobs", "FLY_BLOB_DRIFT"),
            (_identity_changed(baseline, current, "suite"), "suite", "SUITE_EVIDENCE_DRIFT"),
            (
                _identity_changed(baseline, current, "invalidators"),
                "invalidators",
                "INVALIDATOR_SET_DRIFT",
            ),
        ]
        for is_changed, identity, reason in reclassifiers:
            if is_changed:
                changed.append(identity)
                reasons.append(reason)
        if reasons:
            decision = "RECLASSIFY"
        else:
            baseline_commit = require_sha1(
                baseline_candidate.get("commit"),
                label="baseline candidate commit",
            )
            current_commit = require_sha1(
                current_candidate.get("commit"),
                label="current candidate commit",
            )
            if baseline_commit != current_commit:
                if not _commit_is_ancestor(root, baseline_commit, current_commit):
                    decision = "RECLASSIFY"
                    changed.append("candidate.commit")
                    reasons.append("CANDIDATE_NOT_DESCENDANT")
                else:
                    diff_entries = _commit_diff(root, baseline_commit, current_commit)
                    reusable, diff_reasons, diff_changed = _classify_descendant_diff(
                        diff_entries
                    )
                    decision = "REUSE" if reusable else "RECLASSIFY"
                    changed.append("candidate.commit")
                    if baseline_candidate["tree"] != current_candidate["tree"]:
                        changed.append("candidate.tree")
                    changed.extend(diff_changed)
                    reasons.extend(diff_reasons)
            else:
                decision = "REUSE"
                reasons.append("IDENTITIES_EQUIVALENT")
    core = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "REUSE_DECISION",
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "changed_identities": sorted(set(changed)),
        "application_ambiguity_declared": application_ambiguity,
        "baseline_receipt_sha256": baseline["receipt_sha256"],
        "current_receipt_sha256": current["receipt_sha256"],
        "root": ".",
    }
    return seal_receipt(core)


def build_failure_receipt(root: Path, config: Any) -> dict[str, Any]:
    config = require_exact_keys(config, FAILURE_REQUIRED_KEYS, label="failure config")
    candidate = require_sha1(config["candidate"], label="candidate")
    if run_git(root, "cat-file", "-t", candidate) != "commit":
        raise EvidenceError("candidate must identify a commit in the repository")
    gate = require_name(config["gate"], label="gate")
    classification = require_name(config["classification"], label="classification")
    next_action = require_name(config["next_action"], label="next_action")
    timestamp = config["timestamp"]
    if not isinstance(timestamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
        timestamp,
    ):
        raise EvidenceError("timestamp must be an explicit UTC ISO-8601 value ending in Z")
    _, artifact_pointer = validate_repo_relative(
        config["artifact_pointer"],
        root,
        label="artifact_pointer",
        must_exist=False,
    )
    raw_fingerprints = config["fingerprints"]
    if not isinstance(raw_fingerprints, dict) or not raw_fingerprints:
        raise EvidenceError("fingerprints must be a non-empty object")
    fingerprints: dict[str, str] = {}
    for key, value in raw_fingerprints.items():
        typed_key = require_name(key, label="fingerprint key")
        fingerprints[typed_key] = require_sha256(value, label=f"fingerprints.{typed_key}")
    core = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": "COMPACT_FAILURE",
        "candidate": candidate,
        "gate": gate,
        "classification": classification,
        "timestamp": timestamp,
        "artifact_pointer": artifact_pointer,
        "fingerprints": dict(sorted(fingerprints.items())),
        "next_action": next_action,
        "root": ".",
    }
    return seal_receipt(core)


def _load_contained_json(raw_path: str, root: Path, *, label: str) -> tuple[dict[str, Any], Path]:
    path = resolve_contained_path(
        raw_path,
        root,
        label=label,
        must_exist=True,
        require_file=True,
    )
    value = load_json(path)
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must contain an object")
    return value, path


def _output_path(raw_path: str, root: Path, inputs: Iterable[Path]) -> Path:
    output = resolve_contained_path(
        raw_path,
        root,
        label="output",
        must_exist=False,
    )
    if any(output == item for item in inputs):
        raise EvidenceError("output must be distinct from every input")
    return output


def command_freeze(arguments: argparse.Namespace) -> dict[str, Any]:
    root = normalize_repo_root(arguments.repo_root)
    config, config_path = _load_contained_json(arguments.config, root, label="config")
    output = _output_path(arguments.output, root, (config_path,))
    receipt = build_frozen_identity(root, config)
    atomic_write(output, canonical_json_bytes(receipt), root=root)
    return receipt


def command_assess_reuse(arguments: argparse.Namespace) -> dict[str, Any]:
    root = normalize_repo_root(arguments.repo_root)
    baseline, baseline_path = _load_contained_json(
        arguments.baseline,
        root,
        label="baseline",
    )
    current, current_path = _load_contained_json(
        arguments.current,
        root,
        label="current",
    )
    output = _output_path(arguments.output, root, (baseline_path, current_path))
    receipt = build_reuse_decision(
        root,
        baseline,
        current,
        application_ambiguity=bool(arguments.application_ambiguity),
    )
    atomic_write(output, canonical_json_bytes(receipt), root=root)
    return receipt


def command_failure(arguments: argparse.Namespace) -> dict[str, Any]:
    root = normalize_repo_root(arguments.repo_root)
    config, config_path = _load_contained_json(arguments.config, root, label="config")
    output = _output_path(arguments.output, root, (config_path,))
    receipt = build_failure_receipt(root, config)
    atomic_write(output, canonical_json_bytes(receipt), root=root)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--repo-root", required=True)
    freeze.add_argument("--config", required=True)
    freeze.add_argument("--output", required=True)
    freeze.set_defaults(handler=command_freeze)

    assess = subparsers.add_parser("assess-reuse")
    assess.add_argument("--repo-root", required=True)
    assess.add_argument("--baseline", required=True)
    assess.add_argument("--current", required=True)
    assess.add_argument("--output", required=True)
    assess.add_argument("--application-ambiguity", action="store_true")
    assess.set_defaults(handler=command_assess_reuse)

    failure = subparsers.add_parser("failure")
    failure.add_argument("--repo-root", required=True)
    failure.add_argument("--config", required=True)
    failure.add_argument("--output", required=True)
    failure.set_defaults(handler=command_failure)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        receipt = arguments.handler(arguments)
    except EvidenceError as exc:
        parser.exit(2, f"validation evidence refused: {exc}\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
