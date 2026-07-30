"""Deterministic phase-closeout lifecycle evidence anchoring.

The tool copies one explicitly accepted, sanitized, ignored lifecycle record to
one explicitly bound canonical worktree and updates exactly one tracked ledger
row.  It never stages, commits, switches, fetches, pushes, deploys, deletes, or
discovers broader evidence.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import validation_evidence as evidence


SCHEMA = "campaign-player-wiki.phase-closeout-anchor"
SCHEMA_VERSION = 1
CLASSIFICATION_SCHEMA = "campaign-player-wiki.sanitized-lifecycle-classification"
CLASSIFICATION_KIND = "SANITIZED_LIFECYCLE_ACCEPTANCE"
PLAN_KIND = "PLAN"
WRITE_KIND = "WRITE_RESULT"
VERIFY_KIND = "VERIFY_RESULT"
LEDGER_RELATIVE = "docs/contracts/phase-closeout-evidence-anchors.md"
LIFECYCLE_PATTERN = re.compile(
    r"^\.local/roadmaps/[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.md$"
)
PHASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()/-]{0,126}$")
UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$"
)
REF_PATTERN = re.compile(
    r"^(?:refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]{0,180}|[0-9a-f]{40})$"
)
NON_FILE_URL_PATTERN = re.compile(
    r"(?i)([a-z][a-z0-9+.-]{1,31})://[^\s`'\"<>]+"
)
REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
EMPTY_TRACKED_DIFF_SHA256 = evidence.sha256_bytes(b"")

PLAN_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "kind",
        "phase",
        "finalized_utc",
        "accepted",
        "root_states",
        "paths",
        "source_record",
        "canonical_prestate",
        "ledger_prestate",
        "ledger_poststate",
        "ledger_update",
        "inputs",
        "receipt_sha256",
    }
)
ROOT_STATE_KEYS = frozenset(
    {
        "ref",
        "head",
        "ref_commit",
        "head_tree",
        "common_directory_sha256",
        "tracked_worktree_sha256",
    }
)
PATH_KEYS = frozenset(
    {"source", "canonical", "ledger", "frozen_identity", "classification"}
)
FILE_STATE_KEYS = frozenset({"exists", "bytes", "sha256"})
LEDGER_STATE_KEYS = frozenset({"bytes", "sha256", "newline"})
LEDGER_UPDATE_KEYS = frozenset(
    {"mode", "row", "existing_row", "replacement_authorized"}
)
INPUT_KEYS = frozenset(
    {"frozen_identity_receipt_sha256", "classification_receipt_sha256"}
)
RESULT_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "kind",
        "status",
        "plan_sha256",
        "canonical",
        "ledger",
        "reason",
        "receipt_sha256",
    }
)
RESULT_FILE_KEYS = frozenset({"correct", "bytes", "sha256"})
CLASSIFICATION_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "kind",
        "status",
        "classification",
        "source",
        "reviewed_utc",
        "reviewer",
        "receipt_sha256",
    }
)
CLASSIFICATION_SOURCE_KEYS = frozenset({"path", "bytes", "sha256"})


class AnchorError(evidence.EvidenceError):
    """A phase-closeout anchor contract refusal."""


def _starts_path_token(value: str, index: int) -> bool:
    if index == 0:
        return True
    previous = value[index - 1]
    return previous.isspace() or (
        not previous.isalnum() and previous not in "._~/\\"
    )


def _mask_non_file_urls(value: str) -> str:
    masked = list(value)
    for match in NON_FILE_URL_PATTERN.finditer(value):
        if (
            match.group(1).casefold() == "file"
            or not _starts_path_token(value, match.start(1))
        ):
            continue
        authority_index = value.find("://", match.start(), match.end()) + 3
        if authority_index < 3 or value[authority_index] in "/\\":
            continue
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    return "".join(masked)


def _starts_file_uri(value: str, index: int) -> bool:
    for prefix in ("file:", "file%3a"):
        if not value.startswith(prefix, index):
            continue
        payload = value[index + len(prefix) :]
        if payload.startswith(("/", "\\", "%2f", "%5c")):
            return True
        if (
            len(payload) >= 3
            and payload[0].isascii()
            and payload[0].isalpha()
            and payload[1] == ":"
            and payload[2] in "/\\"
        ):
            return True
    return False


def _contains_absolute_path(value: str) -> bool:
    value = _mask_non_file_urls(value)
    folded = value.casefold()
    for index in range(len(value)):
        if not _starts_path_token(value, index):
            continue
        if (
            index + 2 < len(value)
            and value[index].isascii()
            and value[index].isalpha()
            and value[index + 1] == ":"
            and value[index + 2] in "/\\"
        ):
            return True
        if _starts_file_uri(folded, index):
            return True

    for index, character in enumerate(value):
        if character not in "/\\" or not _starts_path_token(value, index):
            continue
        following = value[index + 1 :]
        if character == "/" and following.startswith("/"):
            return len(following) == 1 or not following[1].isspace()
        if character == "\\" and following.startswith("\\"):
            return len(following) == 1 or not following[1].isspace()
        if not following or not following[0].isspace():
            return True
    return False


def _exact_dict(value: Any, keys: frozenset[str], *, label: str) -> dict[str, Any]:
    try:
        return evidence.require_exact_keys(value, keys, label=label)
    except evidence.EvidenceError as exc:
        raise AnchorError(str(exc)) from exc


def _safe_scalar(value: Any, *, label: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise AnchorError(f"{label} must be a non-empty bounded string")
    if _contains_absolute_path(value):
        raise AnchorError(f"{label} contains an absolute or personal path")
    return value


def _reject_unsafe_values(value: Any, *, location: str = "$") -> None:
    try:
        evidence.reject_private_fields(value, location=location)
    except evidence.EvidenceError as exc:
        raise AnchorError(str(exc)) from exc
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_unsafe_values(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_unsafe_values(child, location=f"{location}[{index}]")
    elif isinstance(value, str):
        if _contains_absolute_path(value):
            raise AnchorError(f"{location} contains an absolute or personal path")


def _sha256_path_text(path: Path) -> str:
    normalized = os.path.normcase(os.path.abspath(path)).replace("\\", "/")
    return evidence.sha256_bytes(normalized.encode("utf-8"))


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & REPARSE_FLAG
    )


def _normal_absolute(path: Path, *, label: str, require_file: bool = False) -> Path:
    absolute = Path(os.path.abspath(path))
    ancestors: list[Path] = []
    current = absolute
    while current.parent != current:
        ancestors.append(current)
        current = current.parent
    ancestors.append(current)
    for ancestor in reversed(ancestors):
        if ancestor.exists() and _is_reparse(ancestor):
            raise AnchorError(f"{label} contains a reparse path")
    if require_file and (not absolute.is_file() or _is_reparse(absolute)):
        raise AnchorError(f"{label} must be a normal file")
    return absolute


def _normalize_root(raw: str, *, label: str) -> Path:
    try:
        root = evidence.normalize_repo_root(raw)
    except evidence.EvidenceError as exc:
        raise AnchorError(f"{label}: {exc}") from exc
    return _normal_absolute(root, label=label)


def _git(root: Path, *arguments: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if allow_failure:
            return ""
        detail = (result.stderr or result.stdout).strip()
        raise AnchorError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    )


def _common_directory(root: Path) -> Path:
    raw = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return _normal_absolute(Path(raw), label="Git common directory")


def _registered_worktrees(root: Path) -> set[str]:
    output = _git(root, "worktree", "list", "--porcelain")
    result: set[str] = set()
    for line in output.splitlines():
        if line.startswith("worktree "):
            result.add(os.path.normcase(os.path.abspath(line[9:])))
    return result


def _validate_roots(
    source_root_raw: str,
    canonical_root_raw: str,
    ledger_root_raw: str,
) -> tuple[Path, Path, Path, str]:
    source_root = _normalize_root(source_root_raw, label="source root")
    canonical_root = _normalize_root(canonical_root_raw, label="canonical root")
    ledger_root = _normalize_root(ledger_root_raw, label="ledger root")
    common = _common_directory(source_root)
    common_id = _sha256_path_text(common)
    for label, root in (
        ("source root", source_root),
        ("canonical root", canonical_root),
        ("ledger root", ledger_root),
    ):
        if not _same_path(_common_directory(root), common):
            raise AnchorError(f"{label} must share the source Git common directory")
    registered = _registered_worktrees(source_root)
    for label, root in (
        ("source root", source_root),
        ("canonical root", canonical_root),
        ("ledger root", ledger_root),
    ):
        if os.path.normcase(os.path.abspath(root)) not in registered:
            raise AnchorError(f"{label} must be a registered Git worktree")
    if _same_path(source_root, canonical_root):
        raise AnchorError("source and canonical roots must be distinct worktrees")
    return source_root, canonical_root, ledger_root, common_id


def _require_ref(raw: Any, *, label: str) -> str:
    value = _safe_scalar(raw, label=label, maximum=220)
    if not REF_PATTERN.fullmatch(value) or ".." in value or "@{" in value:
        raise AnchorError(f"{label} must be a full safe ref or commit")
    return value


def _physical_root_key(root: Path) -> str:
    return os.path.normcase(os.path.abspath(root))


def _tracked_worktree_sha256(
    root: Path,
    *,
    excluded_relative: str | None,
) -> str:
    arguments = [
        "git",
        "-C",
        str(root),
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--ignore-submodules=none",
        "--",
        ".",
    ]
    if excluded_relative is not None:
        arguments.append(f":(exclude){excluded_relative}")
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", errors="replace"
        ).strip()
        raise AnchorError(f"git tracked-worktree fingerprint failed: {detail}")
    return evidence.sha256_bytes(result.stdout)


def _root_state(
    root: Path,
    ref: str,
    common_id: str,
    *,
    tracked_worktree_sha256: str,
) -> dict[str, str]:
    ref = _require_ref(ref, label="configured ref")
    head = evidence.require_sha1(_git(root, "rev-parse", "HEAD"), label="HEAD")
    try:
        resolved_ref = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except AnchorError as exc:
        raise AnchorError("configured ref does not resolve to a commit") from exc
    ref_commit = evidence.require_sha1(resolved_ref, label="configured ref commit")
    if head != ref_commit:
        raise AnchorError("worktree HEAD does not match its configured ref")
    tree = evidence.require_sha1(
        _git(root, "rev-parse", f"{head}^{{tree}}"),
        label="HEAD tree",
    )
    return {
        "ref": ref,
        "head": head,
        "ref_commit": ref_commit,
        "head_tree": tree,
        "common_directory_sha256": common_id,
        "tracked_worktree_sha256": tracked_worktree_sha256,
    }


def _capture_root_states(
    roots: Mapping[str, Path],
    refs: Mapping[str, str],
    *,
    common_id: str,
    ledger_root: Path,
) -> dict[str, dict[str, str]]:
    fingerprints: dict[str, str] = {}
    for root in roots.values():
        key = _physical_root_key(root)
        if key in fingerprints:
            continue
        staged = _git(root, "diff", "--cached", "--name-only", "--")
        if staged:
            raise AnchorError("worktree index must match HEAD")
        fingerprint = _tracked_worktree_sha256(
            root,
            excluded_relative=(
                LEDGER_RELATIVE if _same_path(root, ledger_root) else None
            ),
        )
        if fingerprint != EMPTY_TRACKED_DIFF_SHA256:
            raise AnchorError(
                "worktree tracked unstaged drift includes an unrelated path"
            )
        fingerprints[key] = fingerprint
    return {
        name: _root_state(
            root,
            refs[name],
            common_id,
            tracked_worktree_sha256=fingerprints[_physical_root_key(root)],
        )
        for name, root in roots.items()
    }


def _validate_relative(
    raw: Any,
    root: Path,
    *,
    label: str,
    must_exist: bool,
    require_file: bool = False,
) -> tuple[Path, str]:
    try:
        path, relative = evidence.validate_repo_relative(
            raw,
            root,
            label=label,
            must_exist=must_exist,
            require_file=require_file,
        )
    except evidence.EvidenceError as exc:
        raise AnchorError(str(exc)) from exc
    if raw != relative:
        raise AnchorError(f"{label} must use normalized repo-relative form")
    return _normal_absolute(path, label=label, require_file=require_file), relative


def _is_tracked(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _require_ledger_content_only_drift(root: Path, relative: str) -> None:
    summary = _git(
        root,
        "diff",
        "--summary",
        "--no-ext-diff",
        "--ignore-submodules=none",
        "--",
        relative,
    )
    if summary:
        raise AnchorError("ledger has tracked mode or type drift")


def _is_ignored(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", relative],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _require_ignored_untracked(root: Path, relative: str, *, label: str) -> None:
    if _is_tracked(root, relative):
        raise AnchorError(f"{label} must be untracked")
    if not _is_ignored(root, relative):
        raise AnchorError(f"{label} must be ignored")


def _load_json_file(
    root: Path,
    raw_path: Any,
    *,
    label: str,
) -> tuple[dict[str, Any], Path, str, str]:
    path, relative = _validate_relative(
        raw_path,
        root,
        label=label,
        must_exist=True,
        require_file=True,
    )
    try:
        value = evidence.load_json(path)
    except evidence.EvidenceError as exc:
        raise AnchorError(str(exc)) from exc
    if not isinstance(value, dict):
        raise AnchorError(f"{label} must contain an object")
    _reject_unsafe_values(value, location=label)
    return value, path, relative, evidence.sha256_file(path)


def _verify_classification(
    value: Any,
    *,
    source_relative: str,
    source_bytes: bytes,
) -> dict[str, Any]:
    try:
        receipt = evidence.verify_sealed_payload(
            value,
            expected_schema=CLASSIFICATION_SCHEMA,
            expected_kind=CLASSIFICATION_KIND,
        )
    except evidence.EvidenceError as exc:
        raise AnchorError(f"classification receipt: {exc}") from exc
    receipt = _exact_dict(receipt, CLASSIFICATION_KEYS, label="classification receipt")
    if receipt["status"] != "ACCEPT" or receipt["classification"] != "SANITIZED_LIFECYCLE":
        raise AnchorError("classification receipt must explicitly accept sanitized lifecycle evidence")
    source = _exact_dict(
        receipt["source"],
        CLASSIFICATION_SOURCE_KEYS,
        label="classification source",
    )
    if source["path"] != source_relative:
        raise AnchorError("classification receipt source path mismatch")
    if source["bytes"] != len(source_bytes):
        raise AnchorError("classification receipt source byte count mismatch")
    if evidence.require_sha256(source["sha256"], label="classification source sha256") != (
        evidence.sha256_bytes(source_bytes)
    ):
        raise AnchorError("classification receipt source SHA-256 mismatch")
    _require_utc(receipt["reviewed_utc"], label="classification reviewed_utc")
    _safe_scalar(receipt["reviewer"], label="classification reviewer", maximum=128)
    _reject_unsafe_values(receipt)
    return receipt


def _newline_style(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnchorError("ledger must be UTF-8") from exc
    without_crlf = text.replace("\r\n", "")
    has_crlf = "\r\n" in text
    has_lf = "\n" in without_crlf
    if "\r" in without_crlf or (has_crlf and has_lf):
        raise AnchorError("ledger must use one uniform LF or CRLF newline style")
    if not has_crlf and not has_lf:
        raise AnchorError("ledger must contain line endings")
    return "CRLF" if has_crlf else "LF"


def _file_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "bytes": 0, "sha256": None}
    if not path.is_file() or _is_reparse(path):
        raise AnchorError("canonical destination must be absent or a normal file")
    payload = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(payload),
        "sha256": evidence.sha256_bytes(payload),
    }


def _ledger_payload_state(payload: bytes) -> dict[str, Any]:
    return {
        "bytes": len(payload),
        "sha256": evidence.sha256_bytes(payload),
        "newline": _newline_style(payload),
    }


def _ledger_state(path: Path) -> dict[str, Any]:
    return _ledger_payload_state(path.read_bytes())


def _parse_row(line: str) -> list[str] | None:
    stripped = line.rstrip("\r\n")
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
    if len(cells) != 7 or cells[0] in ("Phase", "---"):
        return None
    return cells


def _unquote(cell: str) -> str:
    if len(cell) >= 2 and cell.startswith("`") and cell.endswith("`"):
        return cell[1:-1]
    return cell


def _expected_row(
    phase: str,
    commit: str,
    tree: str,
    relative: str,
    byte_count: int,
    sha256: str,
    finalized_utc: str,
) -> str:
    return (
        f"| {phase} | `{commit}` | `{tree}` | `{relative}` | {byte_count} | "
        f"`{sha256}` | `{finalized_utc}` |"
    )


def _classify_ledger_update(
    payload: bytes,
    *,
    phase: str,
    relative: str,
    expected_row: str,
    replacement_authorized: bool,
) -> dict[str, Any]:
    style = _newline_style(payload)
    text = payload.decode("utf-8")
    phase_matches: list[str] = []
    path_matches: list[str] = []
    for line in text.splitlines():
        cells = _parse_row(line)
        if cells is None:
            continue
        if _unquote(cells[0]) == phase:
            phase_matches.append(line)
        if _unquote(cells[3]) == relative:
            path_matches.append(line)
    if len(phase_matches) > 1 or len(path_matches) > 1:
        raise AnchorError("ledger contains duplicate or ambiguous phase/path rows")
    if bool(phase_matches) != bool(path_matches):
        raise AnchorError("ledger phase and lifecycle path identify different rows")
    existing: str | None = None
    if phase_matches:
        if phase_matches[0] != path_matches[0]:
            raise AnchorError("ledger phase and lifecycle path identify different rows")
        existing = phase_matches[0]
    if existing is None:
        mode = "INSERT"
    elif existing == expected_row:
        mode = "EXACT"
    else:
        if not replacement_authorized:
            raise AnchorError("ledger row replacement requires explicit authorization")
        mode = "REPLACE"
    return {
        "mode": mode,
        "row": expected_row,
        "existing_row": existing,
        "replacement_authorized": bool(replacement_authorized),
        "_newline": style,
    }


def _apply_ledger_update(payload: bytes, update: Mapping[str, Any]) -> bytes:
    style = _newline_style(payload)
    newline = "\r\n" if style == "CRLF" else "\n"
    text = payload.decode("utf-8")
    lines = text.splitlines(keepends=True)
    row = str(update["row"])
    mode = update["mode"]
    existing = update["existing_row"]
    if mode == "EXACT":
        if sum(line.rstrip("\r\n") == row for line in lines) != 1:
            raise AnchorError("exact ledger row drifted")
        return payload
    if mode == "REPLACE":
        matches = [
            index for index, line in enumerate(lines) if line.rstrip("\r\n") == existing
        ]
        if len(matches) != 1:
            raise AnchorError("replacement ledger row drifted")
        suffix = newline if lines[matches[0]].endswith(("\n", "\r")) else ""
        lines[matches[0]] = row + suffix
        return "".join(lines).encode("utf-8")
    if mode != "INSERT":
        raise AnchorError("unsupported ledger update mode")
    data_indexes = [
        index for index, line in enumerate(lines) if _parse_row(line) is not None
    ]
    if not data_indexes:
        raise AnchorError("ledger contains no supported anchor table rows")
    insertion = data_indexes[-1] + 1
    if insertion > 0 and not lines[insertion - 1].endswith(("\n", "\r")):
        lines[insertion - 1] += newline
    lines.insert(insertion, row + newline)
    return "".join(lines).encode("utf-8")


def _require_phase(value: Any) -> str:
    phase = _safe_scalar(value, label="phase", maximum=127)
    if not PHASE_PATTERN.fullmatch(phase) or "|" in phase or "`" in phase:
        raise AnchorError("phase contains unsupported ledger characters")
    return phase


def _require_utc(value: Any, *, label: str) -> str:
    timestamp = _safe_scalar(value, label=label, maximum=40)
    if not UTC_PATTERN.fullmatch(timestamp):
        raise AnchorError(f"{label} must be an explicit ISO-8601 UTC timestamp")
    try:
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise AnchorError(f"{label} must be a valid ISO-8601 UTC timestamp") from exc
    return timestamp


def _validate_source_and_targets(
    source_root: Path,
    canonical_root: Path,
    ledger_root: Path,
    *,
    source_relative_raw: Any,
    canonical_relative_raw: Any,
    ledger_relative_raw: Any,
) -> tuple[Path, Path, Path, str]:
    source_path, source_relative = _validate_relative(
        source_relative_raw,
        source_root,
        label="source lifecycle path",
        must_exist=True,
        require_file=True,
    )
    if not LIFECYCLE_PATTERN.fullmatch(source_relative):
        raise AnchorError("source lifecycle path must be .local/roadmaps/<safe-name>.md")
    canonical_path, canonical_relative = _validate_relative(
        canonical_relative_raw,
        canonical_root,
        label="canonical lifecycle path",
        must_exist=False,
    )
    if canonical_relative != source_relative:
        raise AnchorError("canonical lifecycle path must match the source repo-relative path")
    if ledger_relative_raw != LEDGER_RELATIVE:
        raise AnchorError(f"ledger path must be exactly {LEDGER_RELATIVE}")
    ledger_path, ledger_relative = _validate_relative(
        ledger_relative_raw,
        ledger_root,
        label="ledger path",
        must_exist=True,
        require_file=True,
    )
    if _same_path(source_path, canonical_path):
        raise AnchorError("source and canonical lifecycle paths must not alias")
    _require_ignored_untracked(source_root, source_relative, label="source lifecycle record")
    _require_ignored_untracked(
        canonical_root,
        canonical_relative,
        label="canonical lifecycle destination",
    )
    if not _is_tracked(ledger_root, ledger_relative):
        raise AnchorError("ledger must be a tracked normal file")
    _require_ledger_content_only_drift(ledger_root, ledger_relative)
    return source_path, canonical_path, ledger_path, source_relative


def render_plan(
    *,
    source_root_raw: str,
    canonical_root_raw: str,
    ledger_root_raw: str,
    source_ref: str,
    canonical_ref: str,
    ledger_ref: str,
    source_relative: str,
    canonical_relative: str,
    ledger_relative: str,
    frozen_identity_relative: str,
    classification_relative: str,
    phase: str,
    finalized_utc: str,
    replacement_authorized: bool,
) -> dict[str, Any]:
    source_root, canonical_root, ledger_root, common_id = _validate_roots(
        source_root_raw,
        canonical_root_raw,
        ledger_root_raw,
    )
    roots = {
        "source": source_root,
        "canonical": canonical_root,
        "ledger": ledger_root,
    }
    root_states = _capture_root_states(
        roots,
        {
            "source": source_ref,
            "canonical": canonical_ref,
            "ledger": ledger_ref,
        },
        common_id=common_id,
        ledger_root=ledger_root,
    )
    source_path, canonical_path, ledger_path, relative = _validate_source_and_targets(
        source_root,
        canonical_root,
        ledger_root,
        source_relative_raw=source_relative,
        canonical_relative_raw=canonical_relative,
        ledger_relative_raw=ledger_relative,
    )
    source_payload = source_path.read_bytes()
    source_record = {
        "bytes": len(source_payload),
        "sha256": evidence.sha256_bytes(source_payload),
    }
    frozen, _, frozen_relative, frozen_file_sha = _load_json_file(
        source_root,
        frozen_identity_relative,
        label="frozen identity receipt",
    )
    _require_ignored_untracked(
        source_root,
        frozen_relative,
        label="frozen identity receipt",
    )
    try:
        evidence.verify_frozen_identity(source_root, frozen)
    except evidence.EvidenceError as exc:
        raise AnchorError(f"frozen identity receipt: {exc}") from exc
    accepted = {
        "commit": frozen["candidate"]["commit"],
        "tree": frozen["candidate"]["tree"],
    }
    classification, _, classification_relative_normalized, classification_file_sha = (
        _load_json_file(
            source_root,
            classification_relative,
            label="classification receipt",
        )
    )
    _require_ignored_untracked(
        source_root,
        classification_relative_normalized,
        label="classification receipt",
    )
    _verify_classification(
        classification,
        source_relative=relative,
        source_bytes=source_payload,
    )
    phase = _require_phase(phase)
    finalized_utc = _require_utc(finalized_utc, label="finalized_utc")
    row = _expected_row(
        phase,
        accepted["commit"],
        accepted["tree"],
        relative,
        len(source_payload),
        source_record["sha256"],
        finalized_utc,
    )
    ledger_payload = ledger_path.read_bytes()
    update = _classify_ledger_update(
        ledger_payload,
        phase=phase,
        relative=relative,
        expected_row=row,
        replacement_authorized=replacement_authorized,
    )
    ledger_poststate = _ledger_payload_state(
        _apply_ledger_update(ledger_payload, update)
    )
    update.pop("_newline")
    canonical_prestate = _file_state(canonical_path)
    if (
        canonical_prestate["exists"]
        and canonical_prestate["sha256"] != source_record["sha256"]
        and not replacement_authorized
    ):
        raise AnchorError(
            "canonical lifecycle replacement requires explicit authorization"
        )
    core = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "phase": phase,
        "finalized_utc": finalized_utc,
        "accepted": accepted,
        "root_states": root_states,
        "paths": {
            "source": relative,
            "canonical": relative,
            "ledger": LEDGER_RELATIVE,
            "frozen_identity": frozen_relative,
            "classification": classification_relative_normalized,
        },
        "source_record": source_record,
        "canonical_prestate": canonical_prestate,
        "ledger_prestate": _ledger_state(ledger_path),
        "ledger_poststate": ledger_poststate,
        "ledger_update": update,
        "inputs": {
            "frozen_identity_receipt_sha256": frozen_file_sha,
            "classification_receipt_sha256": classification_file_sha,
        },
    }
    _reject_unsafe_values(core)
    return evidence.seal_receipt(core)


def _verify_plan_shape(value: Any) -> dict[str, Any]:
    try:
        plan = evidence.verify_sealed_payload(
            value,
            expected_schema=SCHEMA,
            expected_kind=PLAN_KIND,
        )
    except evidence.EvidenceError as exc:
        raise AnchorError(f"plan: {exc}") from exc
    plan = _exact_dict(plan, PLAN_KEYS, label="plan")
    if plan["schema_version"] != SCHEMA_VERSION:
        raise AnchorError("plan schema version is unsupported")
    _require_phase(plan["phase"])
    _require_utc(plan["finalized_utc"], label="plan finalized_utc")
    accepted = _exact_dict(
        plan["accepted"], frozenset({"commit", "tree"}), label="plan accepted"
    )
    evidence.require_sha1(accepted["commit"], label="plan accepted commit")
    evidence.require_sha1(accepted["tree"], label="plan accepted tree")
    states = _exact_dict(
        plan["root_states"],
        frozenset({"source", "canonical", "ledger"}),
        label="plan root states",
    )
    common_ids: set[str] = set()
    for name in ("source", "canonical", "ledger"):
        state = _exact_dict(states[name], ROOT_STATE_KEYS, label=f"plan {name} state")
        _require_ref(state["ref"], label=f"plan {name} ref")
        for key in ("head", "ref_commit", "head_tree"):
            evidence.require_sha1(state[key], label=f"plan {name} {key}")
        evidence.require_sha256(
            state["tracked_worktree_sha256"],
            label=f"plan {name} tracked worktree",
        )
        common_ids.add(
            evidence.require_sha256(
                state["common_directory_sha256"],
                label=f"plan {name} common directory",
            )
        )
    if len(common_ids) != 1:
        raise AnchorError("plan root states do not share one Git common directory")
    paths = _exact_dict(plan["paths"], PATH_KEYS, label="plan paths")
    if not LIFECYCLE_PATTERN.fullmatch(paths["source"]):
        raise AnchorError("plan source path is unsupported")
    if paths["canonical"] != paths["source"]:
        raise AnchorError("plan canonical path mismatch")
    if paths["ledger"] != LEDGER_RELATIVE:
        raise AnchorError("plan ledger path mismatch")
    for name in ("frozen_identity", "classification"):
        path = _safe_scalar(paths[name], label=f"plan {name} path")
        if Path(path).is_absolute() or ".." in Path(path.replace("\\", "/")).parts:
            raise AnchorError(f"plan {name} path must be repo-relative")
    source_record = _exact_dict(
        plan["source_record"],
        frozenset({"bytes", "sha256"}),
        label="plan source record",
    )
    if (
        not isinstance(source_record["bytes"], int)
        or isinstance(source_record["bytes"], bool)
        or source_record["bytes"] < 0
    ):
        raise AnchorError("plan source byte count is invalid")
    evidence.require_sha256(source_record["sha256"], label="plan source sha256")
    canonical = _exact_dict(
        plan["canonical_prestate"], FILE_STATE_KEYS, label="plan canonical prestate"
    )
    if not isinstance(canonical["exists"], bool):
        raise AnchorError("plan canonical prestate exists must be boolean")
    if (
        not isinstance(canonical["bytes"], int)
        or isinstance(canonical["bytes"], bool)
        or canonical["bytes"] < 0
    ):
        raise AnchorError("plan canonical prestate bytes is invalid")
    if canonical["exists"]:
        evidence.require_sha256(
            canonical["sha256"], label="plan canonical prestate sha256"
        )
    elif canonical["sha256"] is not None or canonical["bytes"] != 0:
        raise AnchorError("absent canonical prestate must have zero bytes and null hash")
    ledger_states: dict[str, dict[str, Any]] = {}
    for state_name in ("prestate", "poststate"):
        ledger = _exact_dict(
            plan[f"ledger_{state_name}"],
            LEDGER_STATE_KEYS,
            label=f"plan ledger {state_name}",
        )
        if (
            not isinstance(ledger["bytes"], int)
            or isinstance(ledger["bytes"], bool)
            or ledger["bytes"] <= 0
        ):
            raise AnchorError(f"plan ledger {state_name} bytes is invalid")
        evidence.require_sha256(
            ledger["sha256"], label=f"plan ledger {state_name} sha256"
        )
        if ledger["newline"] not in ("LF", "CRLF"):
            raise AnchorError(f"plan ledger {state_name} newline is invalid")
        ledger_states[state_name] = ledger
    update = _exact_dict(
        plan["ledger_update"], LEDGER_UPDATE_KEYS, label="plan ledger update"
    )
    if update["mode"] not in ("INSERT", "REPLACE", "EXACT"):
        raise AnchorError("plan ledger update mode is invalid")
    _safe_scalar(update["row"], label="plan ledger row", maximum=1024)
    if update["existing_row"] is not None:
        _safe_scalar(
            update["existing_row"], label="plan existing ledger row", maximum=1024
        )
    if not isinstance(update["replacement_authorized"], bool):
        raise AnchorError("plan replacement authorization must be boolean")
    if update["mode"] == "INSERT":
        if update["existing_row"] is not None:
            raise AnchorError("plan INSERT update must not bind an existing row")
    elif update["mode"] == "EXACT":
        if update["existing_row"] != update["row"]:
            raise AnchorError("plan EXACT update must bind the expected row")
    elif (
        update["existing_row"] is None
        or update["existing_row"] == update["row"]
        or not update["replacement_authorized"]
    ):
        raise AnchorError(
            "plan REPLACE update must bind a different authorized existing row"
        )
    prestate = ledger_states["prestate"]
    poststate = ledger_states["poststate"]
    if poststate["newline"] != prestate["newline"]:
        raise AnchorError("plan ledger poststate must preserve newline style")
    newline_bytes = 2 if prestate["newline"] == "CRLF" else 1
    if update["mode"] == "EXACT":
        if poststate != prestate:
            raise AnchorError("plan EXACT ledger poststate must equal its prestate")
    elif update["mode"] == "REPLACE":
        expected_bytes = (
            prestate["bytes"]
            + len(update["row"].encode("utf-8"))
            - len(update["existing_row"].encode("utf-8"))
        )
        if poststate["bytes"] != expected_bytes:
            raise AnchorError("plan REPLACE ledger poststate byte count is invalid")
    else:
        inserted_bytes = len(update["row"].encode("utf-8")) + newline_bytes
        if poststate["bytes"] not in (
            prestate["bytes"] + inserted_bytes,
            prestate["bytes"] + inserted_bytes + newline_bytes,
        ):
            raise AnchorError("plan INSERT ledger poststate byte count is invalid")
    expected_row = _expected_row(
        plan["phase"],
        accepted["commit"],
        accepted["tree"],
        paths["canonical"],
        source_record["bytes"],
        source_record["sha256"],
        plan["finalized_utc"],
    )
    if update["row"] != expected_row:
        raise AnchorError("plan ledger row does not match its bound evidence")
    inputs = _exact_dict(plan["inputs"], INPUT_KEYS, label="plan inputs")
    evidence.require_sha256(
        inputs["frozen_identity_receipt_sha256"],
        label="plan frozen identity receipt sha256",
    )
    evidence.require_sha256(
        inputs["classification_receipt_sha256"],
        label="plan classification receipt sha256",
    )
    _reject_unsafe_values(plan)
    return plan


def _load_and_bind_plan(
    *,
    source_root_raw: str,
    canonical_root_raw: str,
    ledger_root_raw: str,
    plan_value: Any,
    require_prestates: bool,
) -> tuple[dict[str, Any], Path, Path, Path, bytes, bytes]:
    plan = _verify_plan_shape(plan_value)
    source_root, canonical_root, ledger_root, common_id = _validate_roots(
        source_root_raw,
        canonical_root_raw,
        ledger_root_raw,
    )
    roots = {
        "source": source_root,
        "canonical": canonical_root,
        "ledger": ledger_root,
    }
    actual_states = _capture_root_states(
        roots,
        {
            name: plan["root_states"][name]["ref"]
            for name in ("source", "canonical", "ledger")
        },
        common_id=common_id,
        ledger_root=ledger_root,
    )
    for name in ("source", "canonical", "ledger"):
        actual = actual_states[name]
        if actual != plan["root_states"][name]:
            raise AnchorError(f"{name} root/ref/HEAD state drifted from plan")
    paths = plan["paths"]
    source_path, canonical_path, ledger_path, relative = _validate_source_and_targets(
        source_root,
        canonical_root,
        ledger_root,
        source_relative_raw=paths["source"],
        canonical_relative_raw=paths["canonical"],
        ledger_relative_raw=paths["ledger"],
    )
    source_payload = source_path.read_bytes()
    if {
        "bytes": len(source_payload),
        "sha256": evidence.sha256_bytes(source_payload),
    } != plan["source_record"]:
        raise AnchorError("source lifecycle bytes drifted from plan")
    frozen, _, frozen_relative, frozen_file_sha = _load_json_file(
        source_root,
        paths["frozen_identity"],
        label="frozen identity receipt",
    )
    _require_ignored_untracked(
        source_root, frozen_relative, label="frozen identity receipt"
    )
    try:
        evidence.verify_frozen_identity(source_root, frozen)
    except evidence.EvidenceError as exc:
        raise AnchorError(f"frozen identity receipt: {exc}") from exc
    if {
        "commit": frozen["candidate"]["commit"],
        "tree": frozen["candidate"]["tree"],
    } != plan["accepted"]:
        raise AnchorError("frozen identity no longer matches plan accepted identity")
    if frozen_file_sha != plan["inputs"]["frozen_identity_receipt_sha256"]:
        raise AnchorError("frozen identity receipt bytes drifted from plan")
    classification, _, classification_relative, classification_file_sha = _load_json_file(
        source_root,
        paths["classification"],
        label="classification receipt",
    )
    _require_ignored_untracked(
        source_root, classification_relative, label="classification receipt"
    )
    _verify_classification(
        classification,
        source_relative=relative,
        source_bytes=source_payload,
    )
    if classification_file_sha != plan["inputs"]["classification_receipt_sha256"]:
        raise AnchorError("classification receipt bytes drifted from plan")
    ledger_payload = ledger_path.read_bytes()
    if require_prestates:
        if _file_state(canonical_path) != plan["canonical_prestate"]:
            raise AnchorError("canonical destination prestate drifted from plan")
        if _ledger_state(ledger_path) != plan["ledger_prestate"]:
            raise AnchorError("ledger prestate drifted from plan")
        classified = _classify_ledger_update(
            ledger_payload,
            phase=plan["phase"],
            relative=relative,
            expected_row=plan["ledger_update"]["row"],
            replacement_authorized=plan["ledger_update"]["replacement_authorized"],
        )
        classified.pop("_newline")
        if classified != plan["ledger_update"]:
            raise AnchorError("ledger row state drifted from plan")
        expected_ledger = _apply_ledger_update(
            ledger_payload, plan["ledger_update"]
        )
        if _ledger_payload_state(expected_ledger) != plan["ledger_poststate"]:
            raise AnchorError(
                "ledger poststate does not match the deterministic plan update"
            )
    return (
        plan,
        source_path,
        canonical_path,
        ledger_path,
        source_payload,
        ledger_payload,
    )


def _result_file(path: Path, expected: bytes) -> dict[str, Any]:
    if not path.is_file() or _is_reparse(path):
        return {"correct": False, "bytes": 0, "sha256": None}
    payload = path.read_bytes()
    return {
        "correct": payload == expected,
        "bytes": len(payload),
        "sha256": evidence.sha256_bytes(payload),
    }


def _result_receipt(
    *,
    kind: str,
    status: str,
    plan: Mapping[str, Any],
    canonical: Mapping[str, Any],
    ledger: Mapping[str, Any],
    reason: str | None,
) -> dict[str, Any]:
    if kind not in (WRITE_KIND, VERIFY_KIND) or status not in ("PASS", "RECOVERING"):
        raise AnchorError("invalid result classification")
    if reason is not None:
        _safe_scalar(reason, label="result reason", maximum=300)
    core = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "status": status,
        "plan_sha256": plan["receipt_sha256"],
        "canonical": dict(canonical),
        "ledger": dict(ledger),
        "reason": reason,
    }
    _reject_unsafe_values(core)
    return evidence.seal_receipt(core)


def _atomic_ledger_write(path: Path, payload: bytes, root: Path) -> None:
    evidence.atomic_write(path, payload, root=root)


def write_anchor(
    *,
    source_root_raw: str,
    canonical_root_raw: str,
    ledger_root_raw: str,
    plan_value: Any,
    ledger_writer: Callable[[Path, bytes, Path], None] = _atomic_ledger_write,
) -> dict[str, Any]:
    (
        plan,
        _,
        canonical_path,
        ledger_path,
        source_payload,
        ledger_payload,
    ) = _load_and_bind_plan(
        source_root_raw=source_root_raw,
        canonical_root_raw=canonical_root_raw,
        ledger_root_raw=ledger_root_raw,
        plan_value=plan_value,
        require_prestates=True,
    )
    canonical_root = _normalize_root(canonical_root_raw, label="canonical root")
    ledger_root = _normalize_root(ledger_root_raw, label="ledger root")
    evidence.atomic_write(canonical_path, source_payload, root=canonical_root)
    canonical_result = _result_file(canonical_path, source_payload)
    if not canonical_result["correct"]:
        return _result_receipt(
            kind=WRITE_KIND,
            status="RECOVERING",
            plan=plan,
            canonical=canonical_result,
            ledger={"correct": False, "bytes": len(ledger_payload), "sha256": evidence.sha256_bytes(ledger_payload)},
            reason="canonical lifecycle copy failed byte verification",
        )
    expected_ledger = _apply_ledger_update(ledger_payload, plan["ledger_update"])
    if _ledger_payload_state(expected_ledger) != plan["ledger_poststate"]:
        raise AnchorError("ledger poststate recomputation drifted before write")
    try:
        ledger_writer(ledger_path, expected_ledger, ledger_root)
    except Exception as exc:  # receipt must survive a ledger-only finalization failure
        return _result_receipt(
            kind=WRITE_KIND,
            status="RECOVERING",
            plan=plan,
            canonical=canonical_result,
            ledger=_result_file(ledger_path, expected_ledger),
            reason=f"ledger write failed after canonical copy: {type(exc).__name__}",
        )
    try:
        _require_ledger_content_only_drift(
            ledger_root, plan["paths"]["ledger"]
        )
    except AnchorError:
        ledger_result = _result_file(ledger_path, expected_ledger)
        ledger_result["correct"] = False
        return _result_receipt(
            kind=WRITE_KIND,
            status="RECOVERING",
            plan=plan,
            canonical=canonical_result,
            ledger=ledger_result,
            reason="ledger mode or type drifted during write",
        )
    ledger_result = _result_file(ledger_path, expected_ledger)
    status = "PASS" if ledger_result["correct"] else "RECOVERING"
    return _result_receipt(
        kind=WRITE_KIND,
        status=status,
        plan=plan,
        canonical=canonical_result,
        ledger=ledger_result,
        reason=None if status == "PASS" else "ledger failed byte verification",
    )


def verify_anchor(
    *,
    source_root_raw: str,
    canonical_root_raw: str,
    ledger_root_raw: str,
    plan_value: Any,
) -> dict[str, Any]:
    (
        plan,
        _,
        canonical_path,
        ledger_path,
        source_payload,
        ledger_payload,
    ) = _load_and_bind_plan(
        source_root_raw=source_root_raw,
        canonical_root_raw=canonical_root_raw,
        ledger_root_raw=ledger_root_raw,
        plan_value=plan_value,
        require_prestates=False,
    )
    canonical_result = _result_file(canonical_path, source_payload)
    ledger_state = _ledger_payload_state(ledger_payload)
    ledger_correct = ledger_state == plan["ledger_poststate"]
    ledger_result = {
        "correct": ledger_correct,
        "bytes": ledger_state["bytes"],
        "sha256": ledger_state["sha256"],
    }
    status = "PASS" if canonical_result["correct"] and ledger_correct else "RECOVERING"
    reason = None
    if not canonical_result["correct"]:
        reason = "canonical lifecycle copy does not match source"
    elif not ledger_correct:
        reason = "ledger bytes do not match the sealed deterministic poststate"
    return _result_receipt(
        kind=VERIFY_KIND,
        status=status,
        plan=plan,
        canonical=canonical_result,
        ledger=ledger_result,
        reason=reason,
    )


def _output_path(raw: str, source_root: Path, inputs: tuple[Path, ...]) -> Path:
    path = Path(raw)
    if path.is_absolute():
        try:
            relative = path.relative_to(source_root).as_posix()
        except ValueError as exc:
            raise AnchorError("output must stay inside source root") from exc
    else:
        relative = raw.replace("\\", "/")
    output, normalized = _validate_relative(
        relative,
        source_root,
        label="output",
        must_exist=False,
    )
    if not normalized.startswith(".local/"):
        raise AnchorError("output must stay in ignored .local evidence")
    _require_ignored_untracked(source_root, normalized, label="output")
    if any(_same_path(output, item) for item in inputs):
        raise AnchorError("output must not alias an input")
    return output


def _load_plan_path(source_root: Path, raw: str) -> tuple[dict[str, Any], Path]:
    path = Path(raw)
    if path.is_absolute():
        try:
            relative = path.relative_to(source_root).as_posix()
        except ValueError as exc:
            raise AnchorError("plan must stay inside source root") from exc
    else:
        relative = raw.replace("\\", "/")
    value, plan_path, normalized, _ = _load_json_file(
        source_root, relative, label="plan"
    )
    _require_ignored_untracked(source_root, normalized, label="plan")
    return value, plan_path


def _write_output(source_root: Path, output: Path, value: Mapping[str, Any]) -> None:
    evidence.atomic_write(output, evidence.canonical_json_bytes(value), root=source_root)


def _render_command(arguments: argparse.Namespace) -> int:
    source_root = _normalize_root(arguments.source_root, label="source root")
    plan = render_plan(
        source_root_raw=arguments.source_root,
        canonical_root_raw=arguments.canonical_root,
        ledger_root_raw=arguments.ledger_root,
        source_ref=arguments.source_ref,
        canonical_ref=arguments.canonical_ref,
        ledger_ref=arguments.ledger_ref,
        source_relative=arguments.source_path,
        canonical_relative=arguments.canonical_path,
        ledger_relative=arguments.ledger_path,
        frozen_identity_relative=arguments.frozen_identity,
        classification_relative=arguments.classification_receipt,
        phase=arguments.phase,
        finalized_utc=arguments.finalized_utc,
        replacement_authorized=arguments.replace_existing,
    )
    output = _output_path(arguments.output, source_root, ())
    _write_output(source_root, output, plan)
    return 0


def _bound_command(arguments: argparse.Namespace, *, verify_only: bool) -> int:
    source_root = _normalize_root(arguments.source_root, label="source root")
    plan, plan_path = _load_plan_path(source_root, arguments.plan)
    output = _output_path(arguments.output, source_root, (plan_path,))
    if verify_only:
        result = verify_anchor(
            source_root_raw=arguments.source_root,
            canonical_root_raw=arguments.canonical_root,
            ledger_root_raw=arguments.ledger_root,
            plan_value=plan,
        )
    else:
        result = write_anchor(
            source_root_raw=arguments.source_root,
            canonical_root_raw=arguments.canonical_root,
            ledger_root_raw=arguments.ledger_root,
            plan_value=plan,
        )
    _write_output(source_root, output, result)
    return 0 if result["status"] == "PASS" else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render = subparsers.add_parser("render")
    for command in (render,):
        command.add_argument("--source-root", required=True)
        command.add_argument("--canonical-root", required=True)
        command.add_argument("--ledger-root", required=True)
    render.add_argument("--source-ref", required=True)
    render.add_argument("--canonical-ref", required=True)
    render.add_argument("--ledger-ref", required=True)
    render.add_argument("--source-path", required=True)
    render.add_argument("--canonical-path", required=True)
    render.add_argument("--ledger-path", required=True)
    render.add_argument("--frozen-identity", required=True)
    render.add_argument("--classification-receipt", required=True)
    render.add_argument("--phase", required=True)
    render.add_argument("--finalized-utc", required=True)
    render.add_argument("--replace-existing", action="store_true")
    render.add_argument("--output", required=True)
    for name in ("write", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--source-root", required=True)
        command.add_argument("--canonical-root", required=True)
        command.add_argument("--ledger-root", required=True)
        command.add_argument("--plan", required=True)
        command.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "render":
            return _render_command(arguments)
        return _bound_command(arguments, verify_only=arguments.command == "verify")
    except (AnchorError, evidence.EvidenceError, OSError, UnicodeError) as exc:
        print(f"phase-closeout-anchor: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
