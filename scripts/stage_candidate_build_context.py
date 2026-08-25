"""Stage and verify the candidate-gate Docker build inventory.

The staging allowlist is owned by Git, not by Docker's ignore parser.  This
keeps ignored local/private material outside the build-context boundary while
preserving the current bytes of every cached or nonignored untracked file.
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
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


SCHEMA = "campaign-player-wiki.candidate-build-context/v1"
RECEIPT_SCHEMA = "campaign-player-wiki.candidate-image-receipt/v1"
CHUNK_SIZE = 1024 * 1024
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class StageError(RuntimeError):
    """A fail-closed candidate build-context error."""


def _git_z(project_root: Path, git: str, *arguments: str) -> list[str]:
    command = [git, "-C", str(project_root), *arguments, "-z"]
    completed = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise StageError(f"Git inventory command failed ({completed.returncode}): {detail}")
    if completed.stdout and not completed.stdout.endswith(b"\0"):
        raise StageError("Git inventory was not NUL terminated.")
    try:
        return [item.decode("utf-8", "strict") for item in completed.stdout.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise StageError("Git inventory contains a path that is not valid UTF-8.") from exc


def _git_text(project_root: Path, git: str, *arguments: str) -> str:
    completed = subprocess.run(
        [git, "-C", str(project_root), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise StageError(f"Git command failed ({completed.returncode}): {detail}")
    try:
        return completed.stdout.decode("utf-8", "strict").strip()
    except UnicodeDecodeError as exc:
        raise StageError("Git command output is not valid UTF-8.") from exc


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def _lexical_child(root: Path, child: Path) -> None:
    root_text = os.path.normcase(os.path.abspath(root))
    child_text = os.path.normcase(os.path.abspath(child))
    try:
        common = os.path.commonpath((root_text, child_text))
    except ValueError as exc:
        raise StageError(f"Path is outside the candidate repository: {child}") from exc
    if common != root_text or child_text == root_text:
        raise StageError(f"Path is not a contained candidate scratch child: {child}")


def _check_existing_chain(root: Path, target: Path) -> None:
    _lexical_child(root, target)
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or _is_reparse(root_info):
        raise StageError(f"Candidate repository root is not a plain directory: {root}")
    current = root
    for part in target.relative_to(root).parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise StageError(f"Candidate scratch path is a link or reparse point: {current}")
        if current != target and not stat.S_ISDIR(info.st_mode):
            raise StageError(f"Candidate scratch parent is not a directory: {current}")


def _plain_file_or_absent(path: Path, label: str) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or _is_reparse(info) or not stat.S_ISREG(info.st_mode):
        raise StageError(f"{label} is not a plain file: {path}")
    return info


def _entry_identity(info: os.stat_result) -> tuple[int, ...]:
    if os.name == "nt":
        identity = (info.st_mode, getattr(info, "st_file_attributes", 0))
        if stat.S_ISREG(info.st_mode):
            return identity + (info.st_size, info.st_mtime_ns)
        return identity
    return (info.st_mode, info.st_dev, info.st_ino)


def _clear_directory_no_follow(root: Path) -> None:
    try:
        root_info = root.lstat()
    except FileNotFoundError:
        root.mkdir(parents=True)
        return
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or _is_reparse(root_info):
        raise StageError(f"Candidate build-context root is not a plain directory: {root}")

    files: list[tuple[Path, os.stat_result]] = []
    directories: list[tuple[Path, os.stat_result]] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or _is_reparse(info):
                    raise StageError(f"Refusing linked or reparse entry in candidate build context: {path}")
                if stat.S_ISDIR(info.st_mode):
                    directories.append((path, info))
                    stack.append(path)
                elif stat.S_ISREG(info.st_mode):
                    files.append((path, info))
                else:
                    raise StageError(f"Refusing special file in candidate build context: {path}")

    for path, inspected in files + directories:
        try:
            current = path.lstat()
        except FileNotFoundError as exc:
            raise StageError(f"Candidate build-context entry drifted during inspection: {path}") from exc
        if (
            stat.S_ISLNK(current.st_mode)
            or _is_reparse(current)
            or _entry_identity(current) != _entry_identity(inspected)
        ):
            raise StageError(f"Candidate build-context entry drifted during inspection: {path}")

    for path, _info in files:
        path.unlink()
    for directory, _info in sorted(directories, key=lambda item: len(item[0].parts), reverse=True):
        directory.rmdir()


def _validate_path(raw: str) -> str:
    if not raw or "\\" in raw or "\0" in raw or any(ord(character) < 32 for character in raw):
        raise StageError(f"Invalid Git inventory path: {raw!r}")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise StageError(f"Absolute Git inventory path is forbidden: {raw!r}")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts) or path.as_posix() != raw:
        raise StageError(f"Non-canonical or traversing Git inventory path: {raw!r}")
    if path.parts[0].casefold() in {".git", ".local"}:
        raise StageError(f"Git inventory path conflicts with a runtime mount: {raw!r}")
    for part in path.parts:
        if part.endswith((" ", ".")) or any(character in '<>:"|?*' for character in part):
            raise StageError(f"Git inventory path is not portable: {raw!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED:
            raise StageError(f"Git inventory path uses a reserved name: {raw!r}")
    return raw


def validate_inventory_paths(paths: Iterable[str]) -> list[str]:
    validated: list[str] = []
    collision_keys: dict[str, str] = {}
    for raw in paths:
        path = _validate_path(raw)
        key = unicodedata.normalize("NFC", path).casefold()
        prior = collision_keys.get(key)
        if prior is not None:
            raise StageError(f"Colliding Git inventory paths: {prior!r} and {path!r}")
        collision_keys[key] = path
        validated.append(path)
    return sorted(validated, key=lambda item: item.encode("utf-8"))


def _tracked_modes(project_root: Path, git: str) -> dict[str, str]:
    modes: dict[str, str] = {}
    for entry in _git_z(project_root, git, "ls-files", "--stage"):
        try:
            metadata, path = entry.split("\t", 1)
            mode, _object_id, stage_number = metadata.split(" ", 2)
        except ValueError as exc:
            raise StageError("Git staged inventory has an invalid record.") from exc
        _validate_path(path)
        if stage_number != "0":
            raise StageError(f"Unmerged Git inventory path is forbidden: {path!r}")
        if mode == "120000":
            raise StageError(f"Git symlink is forbidden in candidate context: {path!r}")
        if mode not in {"100644", "100755"}:
            raise StageError(f"Unsupported Git mode {mode!r} for {path!r}")
        if path in modes:
            raise StageError(f"Duplicate tracked Git path: {path!r}")
        modes[path] = mode
    return modes


def _source_info(project_root: Path, relative: str) -> tuple[Path, os.stat_result]:
    source = project_root.joinpath(*PurePosixPath(relative).parts)
    current = project_root
    root_info = project_root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or _is_reparse(root_info):
        raise StageError("Candidate repository root must be a plain directory.")
    for part in PurePosixPath(relative).parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise StageError(f"Source path is a link or reparse point: {relative!r}")
        if current != source and not stat.S_ISDIR(info.st_mode):
            raise StageError(f"Source parent is not a directory: {relative!r}")
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise StageError(f"Source is not a regular file: {relative!r}")
    return source, info


def _signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_mode, info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _copy_current_bytes(
    source: Path,
    destination: Path,
    before: os.stat_result,
    *,
    drift_hook: Callable[[Path], None] | None = None,
) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        opened = os.fstat(input_stream.fileno())
        if _signature(opened) != _signature(before) or not stat.S_ISREG(opened.st_mode):
            raise StageError(f"Source changed before copy: {source}")
        while chunk := input_stream.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
            output_stream.write(chunk)
        if _signature(os.fstat(input_stream.fileno())) != _signature(before):
            raise StageError(f"Source changed during copy: {source}")
    if drift_hook is not None:
        drift_hook(source)
    try:
        after = source.lstat()
    except FileNotFoundError as exc:
        raise StageError(f"Source disappeared after copy: {source}") from exc
    source_size, source_digest = _hash_file(source)
    copied_digest = digest.hexdigest()
    if _signature(after) != _signature(before) or source_size != size or source_digest != copied_digest:
        raise StageError(f"Source changed while staging: {source}")
    destination_size, destination_digest = _hash_file(destination)
    if destination_size != size or destination_digest != copied_digest:
        raise StageError(f"Staged file verification failed: {destination}")
    return size, copied_digest


def _recheck_source_identity(
    project_root: Path,
    relative: str,
    before: os.stat_result,
    expected_size: int,
    expected_digest: str,
) -> None:
    try:
        source, current = _source_info(project_root, relative)
    except FileNotFoundError as exc:
        raise StageError(f"Staged source disappeared before manifest publication: {relative!r}") from exc
    current_size, current_digest = _hash_file(source)
    try:
        after_hash = source.lstat()
    except FileNotFoundError as exc:
        raise StageError(f"Staged source disappeared before manifest publication: {relative!r}") from exc
    if (
        _signature(current) != _signature(before)
        or _signature(after_hash) != _signature(before)
        or current_size != expected_size
        or current_digest != expected_digest
    ):
        raise StageError(f"Staged source changed before manifest publication: {relative!r}")


def create_git_metadata(
    project_root: Path,
    metadata_root: Path,
    *,
    git: str = "git",
    alternates_path: str = "/candidate-git-objects",
) -> dict[str, str]:
    project_root = project_root.absolute()
    metadata_root = metadata_root.absolute()
    expected_root = project_root / ".local" / "candidate-gate" / "git-metadata"
    if metadata_root != expected_root:
        raise StageError("Candidate Git metadata must use the stable owned path.")
    _check_existing_chain(project_root, metadata_root)
    expected_root.parent.mkdir(parents=True, exist_ok=True)
    _check_existing_chain(project_root, metadata_root)

    head = _git_text(project_root, git, "rev-parse", "--verify", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise StageError("Candidate Git HEAD has an invalid object ID.")
    common_directory = Path(
        _git_text(project_root, git, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ).absolute()
    worktree_directory = Path(
        _git_text(project_root, git, "rev-parse", "--path-format=absolute", "--git-dir")
    ).absolute()
    for label, directory in (
        ("Git common directory", common_directory),
        ("Git worktree directory", worktree_directory),
    ):
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise StageError(f"{label} is not a plain directory: {directory}")
    objects_directory = common_directory / "objects"
    objects_info = objects_directory.lstat()
    if (
        stat.S_ISLNK(objects_info.st_mode)
        or _is_reparse(objects_info)
        or not stat.S_ISDIR(objects_info.st_mode)
    ):
        raise StageError("Candidate Git object directory is not a plain directory.")

    index_path = worktree_directory / "index"
    index_info = _plain_file_or_absent(index_path, "Candidate Git index")
    _clear_directory_no_follow(metadata_root)
    (metadata_root / "objects" / "info").mkdir(parents=True)
    (metadata_root / "refs").mkdir()
    (metadata_root / "HEAD").write_bytes(f"{head}\n".encode("ascii"))
    (metadata_root / "config").write_bytes(
        b"[core]\n\trepositoryformatversion = 0\n\tbare = false\n\tfilemode = false\n"
    )
    (metadata_root / "objects" / "info" / "alternates").write_bytes(
        f"{alternates_path}\n".encode("utf-8")
    )
    expected_files = {"HEAD", "config", "objects/info/alternates"}
    if index_info is not None:
        index_size, index_digest = _copy_current_bytes(
            index_path,
            metadata_root / "index",
            index_info,
        )
        copied_size, copied_digest = _hash_file(metadata_root / "index")
        if (copied_size, copied_digest) != (index_size, index_digest):
            raise StageError("Candidate Git index copy verification failed.")
        expected_files.add("index")

    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for directory, directory_names, file_names in os.walk(
        metadata_root, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(metadata_root)
        for name in directory_names:
            path = directory_path / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info) or not stat.S_ISDIR(info.st_mode):
                raise StageError(f"Candidate Git metadata contains an invalid directory: {path}")
            actual_directories.add((relative_directory / name).as_posix())
        for name in file_names:
            path = directory_path / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info) or not stat.S_ISREG(info.st_mode):
                raise StageError(f"Candidate Git metadata contains an invalid file: {path}")
            actual_files.add((relative_directory / name).as_posix())
    expected_directories = {"objects", "objects/info", "refs"}
    if actual_files != expected_files or actual_directories != expected_directories:
        raise StageError(
            "Candidate Git metadata inventory is not minimal: "
            f"files={sorted(actual_files)!r}, directories={sorted(actual_directories)!r}"
        )
    if index_info is None and (metadata_root / "index").exists():
        raise StageError("Candidate Git metadata retained a stale index.")
    result = {"metadata": str(metadata_root), "objects": str(objects_directory)}
    print(json.dumps(result, sort_keys=True))
    return result


def verify_runtime_temp(paths: Iterable[Path]) -> dict[str, object]:
    for name in ("TEMP", "TMP", "TMPDIR"):
        if os.environ.get(name) != "/tmp":
            raise StageError(f"{name} must be exactly /tmp in candidate containers.")
    checked: list[str] = []
    for supplied in paths:
        path = supplied
        if not path.is_absolute():
            raise StageError(f"Candidate temporary path is not absolute: {path}")
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".candidate-gate-write-probe"
        try:
            probe.write_bytes(b"candidate-gate\n")
            if probe.read_bytes() != b"candidate-gate\n":
                raise StageError(f"Candidate temporary path failed byte verification: {path}")
        finally:
            if probe.exists():
                probe.unlink()
        checked.append(str(path))
    result: dict[str, object] = {"paths": checked, "status": "ok"}
    print(json.dumps(result, sort_keys=True))
    return result


def run_linux_pytest(arguments: list[str]) -> int:
    basetemp = Path("/workspace/.local/candidate-gate/linux-pytest")
    cache = Path("/workspace/.local/candidate-gate/linux-cache")
    verify_runtime_temp((Path("/tmp"), basetemp, cache))
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--basetemp",
            str(basetemp),
            "-o",
            f"cache_dir={cache}",
            *arguments,
        ],
        check=False,
    ).returncode


def stage_context(
    project_root: Path,
    context_root: Path,
    manifest_path: Path,
    *,
    git: str = "git",
    drift_hook: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    project_root = project_root.absolute()
    context_root = context_root.absolute()
    manifest_path = manifest_path.absolute()
    expected_parent = project_root / ".local" / "candidate-gate"
    if context_root != expected_parent / "build-context":
        raise StageError("Candidate build context must use the stable owned path.")
    if manifest_path != expected_parent / "build-context-manifest.json":
        raise StageError("Candidate build manifest must use the stable sibling path.")
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    _check_existing_chain(project_root, context_root)
    _check_existing_chain(project_root, manifest_path)
    _check_existing_chain(project_root, temporary_manifest)
    expected_parent.mkdir(parents=True, exist_ok=True)
    _check_existing_chain(project_root, context_root)
    _check_existing_chain(project_root, manifest_path)
    _check_existing_chain(project_root, temporary_manifest)
    manifest_info = _plain_file_or_absent(manifest_path, "Candidate build manifest")
    _plain_file_or_absent(temporary_manifest, "Candidate temporary build manifest")

    deleted_paths = set(
        validate_inventory_paths(_git_z(project_root, git, "ls-files", "--deleted"))
    )
    tracked_modes = _tracked_modes(project_root, git)
    unknown_deleted = sorted(deleted_paths - set(tracked_modes))
    if unknown_deleted:
        raise StageError(f"Git deleted inventory contains nontracked paths: {unknown_deleted!r}")
    paths = validate_inventory_paths(
        _git_z(project_root, git, "ls-files", "--cached", "--others", "--exclude-standard")
    )
    _clear_directory_no_follow(context_root)
    if manifest_info is not None:
        manifest_path.unlink()

    files: list[dict[str, object]] = []
    deleted_tracked: list[str] = []
    staged_sources: list[tuple[str, os.stat_result, int, str]] = []
    for relative in paths:
        try:
            source, before = _source_info(project_root, relative)
        except FileNotFoundError as exc:
            if relative in deleted_paths:
                deleted_tracked.append(relative)
                continue
            if relative in tracked_modes:
                raise StageError(
                    f"Tracked non-deleted inventory path disappeared: {relative!r}"
                ) from exc
            raise StageError(f"Nontracked inventory path disappeared: {relative!r}") from exc
        destination = context_root.joinpath(*PurePosixPath(relative).parts)
        size, digest = _copy_current_bytes(source, destination, before, drift_hook=drift_hook)
        staged_sources.append((relative, before, size, digest))
        mode = tracked_modes.get(relative)
        if mode and os.name != "nt":
            destination.chmod(0o755 if mode == "100755" else 0o644)
        files.append(
            {
                "git_mode": mode,
                "path": relative,
                "sha256": digest,
                "size": size,
                "state": "tracked" if mode else "untracked",
            }
        )

    for relative, before, size, digest in staged_sources:
        _recheck_source_identity(project_root, relative, before, size, digest)

    manifest: dict[str, object] = {
        "deleted_tracked_paths": deleted_tracked,
        "files": files,
        "schema": SCHEMA,
    }
    _check_existing_chain(project_root, temporary_manifest)
    temporary_info = _plain_file_or_absent(
        temporary_manifest, "Candidate temporary build manifest"
    )
    if temporary_info is not None:
        temporary_manifest.unlink()
    with temporary_manifest.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
        )
    _plain_file_or_absent(temporary_manifest, "Candidate temporary build manifest")
    if _plain_file_or_absent(manifest_path, "Candidate build manifest") is not None:
        raise StageError("Candidate build manifest unexpectedly reappeared before publication.")
    os.replace(temporary_manifest, manifest_path)
    print(json.dumps({"deleted_tracked": len(deleted_tracked), "files": len(files), "manifest": str(manifest_path)}))
    return manifest


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StageError(f"Candidate build manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "deleted_tracked_paths",
        "files",
        "schema",
    }:
        raise StageError("Candidate build manifest has an invalid schema.")
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), list):
        raise StageError("Candidate build manifest has an invalid schema.")
    deleted = manifest.get("deleted_tracked_paths")
    if not isinstance(deleted, list) or not all(isinstance(path, str) for path in deleted):
        raise StageError("Candidate build manifest has an invalid deleted inventory.")
    validated_deleted = validate_inventory_paths(deleted)
    if deleted != validated_deleted:
        raise StageError("Candidate build manifest deleted inventory is not deterministic.")

    paths: list[str] = []
    for record in manifest["files"]:
        if not isinstance(record, dict) or set(record) != {
            "git_mode",
            "path",
            "sha256",
            "size",
            "state",
        }:
            raise StageError("Candidate build manifest contains an invalid file record.")
        path = record.get("path")
        size = record.get("size")
        digest = record.get("sha256")
        state = record.get("state")
        mode = record.get("git_mode")
        if (
            not isinstance(path, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or state not in {"tracked", "untracked"}
            or (state == "tracked" and mode not in {"100644", "100755"})
            or (state == "untracked" and mode is not None)
        ):
            raise StageError("Candidate build manifest contains invalid inventory data.")
        paths.append(path)
    validated_paths = validate_inventory_paths(paths)
    if paths != validated_paths:
        raise StageError("Candidate build manifest file inventory is not deterministic.")
    validate_inventory_paths([*deleted, *paths])
    return manifest


def verify_image_inventory(root: Path, manifest_path: Path) -> dict[str, object]:
    manifest = _load_manifest(manifest_path)
    expected: dict[str, tuple[int, str]] = {}
    for record in manifest["files"]:
        expected[record["path"]] = (record["size"], record["sha256"])

    actual: dict[str, tuple[int, str]] = {}
    root = root.absolute()
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or _is_reparse(root_info):
        raise StageError("Image workspace root must be a plain directory.")
    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(root)
        if relative_directory == Path("."):
            directory_names[:] = [name for name in directory_names if name not in {".git", ".local"}]
        for name in list(directory_names):
            info = (directory_path / name).lstat()
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise StageError(f"Image inventory contains a linked directory: {directory_path / name}")
        for name in file_names:
            path = directory_path / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info) or not stat.S_ISREG(info.st_mode):
                raise StageError(f"Image inventory contains a nonregular file: {relative!r}")
            actual[relative] = _hash_file(path)

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(path for path in set(expected) & set(actual) if expected[path] != actual[path])
    if missing or extra or changed:
        raise StageError(
            "Image inventory mismatch: "
            f"missing={missing!r}, extra={extra!r}, changed={changed!r}"
        )

    tracked_modes = _tracked_modes(root, "git")
    deleted = validate_inventory_paths(_git_z(root, "git", "ls-files", "--deleted"))
    untracked = validate_inventory_paths(
        _git_z(root, "git", "ls-files", "--others", "--exclude-standard")
    )
    _git_z(root, "git", "status", "--porcelain=v1", "--untracked-files=all")
    records = {record["path"]: record for record in manifest["files"]}
    manifest_deleted = manifest["deleted_tracked_paths"]
    if manifest_deleted != deleted:
        raise StageError(
            "Candidate build manifest deleted inventory disagrees with the mounted index: "
            f"manifest={manifest_deleted!r}, index={deleted!r}"
        )
    tracked_present = sorted(set(tracked_modes) - set(deleted), key=lambda item: item.encode("utf-8"))
    manifest_tracked = [
        record["path"] for record in manifest["files"] if record["state"] == "tracked"
    ]
    manifest_untracked = [
        record["path"] for record in manifest["files"] if record["state"] == "untracked"
    ]
    if manifest_tracked != tracked_present or manifest_untracked != untracked:
        raise StageError("Candidate build manifest state disagrees with mounted index/status.")
    for path in tracked_present:
        if records[path]["git_mode"] != tracked_modes[path]:
            raise StageError(
                f"Candidate build manifest Git mode disagrees with mounted index for {path!r}."
            )
    result: dict[str, object] = {
        "deleted_tracked": len(deleted),
        "files": len(actual),
        "status": "ok",
        "tracked": len(tracked_present),
        "untracked": len(untracked),
    }
    print(json.dumps(result, sort_keys=True))
    return result


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _receipt_publication_custody(
    manifest_path: Path,
    output_path: Path,
) -> tuple[Path, Path, Path, os.stat_result, os.stat_result | None, os.stat_result | None]:
    manifest_path = manifest_path.absolute()
    candidate_gate_root = manifest_path.parent
    project_root = candidate_gate_root.parent.parent
    expected_manifest = (
        project_root / ".local" / "candidate-gate" / "build-context-manifest.json"
    )
    if manifest_path != expected_manifest:
        raise StageError(
            "Candidate image receipt manifest must use the exact stable candidate-gate path."
        )
    expected_output = candidate_gate_root / "image-receipt.json"
    output_path = output_path.absolute()
    if output_path != expected_output:
        raise StageError(
            "Candidate image receipt output must use the exact stable sibling path."
        )
    temporary = candidate_gate_root / "image-receipt.json.tmp"

    _check_existing_chain(project_root, manifest_path)
    _check_existing_chain(project_root, output_path)
    _check_existing_chain(project_root, temporary)
    manifest_info = _plain_file_or_absent(manifest_path, "Candidate build manifest")
    if manifest_info is None:
        raise StageError("Candidate build manifest is absent.")
    candidate_root_info = candidate_gate_root.lstat()
    if (
        not stat.S_ISDIR(candidate_root_info.st_mode)
        or stat.S_ISLNK(candidate_root_info.st_mode)
        or _is_reparse(candidate_root_info)
    ):
        raise StageError("Candidate image receipt parent is not a plain directory.")
    output_info = _plain_file_or_absent(output_path, "Candidate image receipt")
    temporary_info = _plain_file_or_absent(temporary, "Candidate image receipt temporary file")
    return (
        project_root,
        output_path,
        temporary,
        candidate_root_info,
        output_info,
        temporary_info,
    )


def _custody_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_mode,
        getattr(info, "st_file_attributes", 0),
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
    )


def _directory_custody_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_mode,
        getattr(info, "st_file_attributes", 0),
        info.st_dev,
        info.st_ino,
    )


def _same_plain_file_or_absent(
    path: Path,
    inspected: os.stat_result | None,
    label: str,
) -> None:
    current = _plain_file_or_absent(path, label)
    if inspected is None:
        if current is not None:
            raise StageError(f"{label} unexpectedly appeared: {path}")
        return
    if current is None or _custody_identity(current) != _custody_identity(inspected):
        raise StageError(f"{label} drifted during custody validation: {path}")


def _invalidate_image_receipt(
    custody: tuple[
        Path,
        Path,
        Path,
        os.stat_result,
        os.stat_result | None,
        os.stat_result | None,
    ],
) -> tuple[Path, Path, Path, os.stat_result, None, None]:
    (
        project_root,
        output_path,
        temporary,
        candidate_root_info,
        output_info,
        temporary_info,
    ) = custody
    _check_existing_chain(project_root, output_path)
    _check_existing_chain(project_root, temporary)
    current_parent = output_path.parent.lstat()
    if (
        not stat.S_ISDIR(current_parent.st_mode)
        or stat.S_ISLNK(current_parent.st_mode)
        or _is_reparse(current_parent)
        or _directory_custody_identity(current_parent)
        != _directory_custody_identity(candidate_root_info)
    ):
        raise StageError("Candidate image receipt parent drifted during invalidation.")
    _same_plain_file_or_absent(output_path, output_info, "Candidate image receipt")
    _same_plain_file_or_absent(
        temporary,
        temporary_info,
        "Candidate image receipt temporary file",
    )

    try:
        if temporary_info is not None:
            temporary.unlink()
        if output_info is not None:
            output_path.unlink()
    except OSError as exc:
        raise StageError("Candidate image receipt invalidation failed.") from exc
    _same_plain_file_or_absent(output_path, None, "Candidate image receipt")
    _same_plain_file_or_absent(
        temporary,
        None,
        "Candidate image receipt temporary file",
    )
    return (
        project_root,
        output_path,
        temporary,
        candidate_root_info,
        None,
        None,
    )


def _publish_image_receipt(
    receipt_bytes: bytes,
    *,
    project_root: Path,
    output_path: Path,
    temporary: Path,
    candidate_root_info: os.stat_result,
    output_info: os.stat_result | None,
    temporary_info: os.stat_result | None,
) -> None:
    _check_existing_chain(project_root, output_path)
    _check_existing_chain(project_root, temporary)
    current_parent = output_path.parent.lstat()
    if (
        not stat.S_ISDIR(current_parent.st_mode)
        or stat.S_ISLNK(current_parent.st_mode)
        or _is_reparse(current_parent)
        or _directory_custody_identity(current_parent)
        != _directory_custody_identity(candidate_root_info)
    ):
        raise StageError("Candidate image receipt parent drifted during custody validation.")
    _same_plain_file_or_absent(output_path, output_info, "Candidate image receipt")
    _same_plain_file_or_absent(
        temporary,
        temporary_info,
        "Candidate image receipt temporary file",
    )

    if temporary_info is not None:
        temporary.unlink()
    if output_info is not None:
        output_path.unlink()
    _same_plain_file_or_absent(output_path, None, "Candidate image receipt")
    _same_plain_file_or_absent(
        temporary,
        None,
        "Candidate image receipt temporary file",
    )

    try:
        with temporary.open("xb") as stream:
            stream.write(receipt_bytes)
            stream.flush()
            os.fsync(stream.fileno())
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _is_reparse(opened):
                raise StageError("Candidate image receipt temporary file is not plain.")
    except FileExistsError as exc:
        raise StageError("Candidate image receipt temporary file unexpectedly appeared.") from exc

    temporary_info_after = _plain_file_or_absent(
        temporary,
        "Candidate image receipt temporary file",
    )
    if temporary_info_after is None:
        raise StageError("Candidate image receipt temporary file disappeared.")
    temporary_size, temporary_digest = _hash_file(temporary)
    if (
        temporary_size != len(receipt_bytes)
        or temporary_digest != hashlib.sha256(receipt_bytes).hexdigest()
    ):
        raise StageError("Candidate image receipt temporary bytes failed verification.")

    _check_existing_chain(project_root, temporary)
    current_parent = output_path.parent.lstat()
    if (
        not stat.S_ISDIR(current_parent.st_mode)
        or stat.S_ISLNK(current_parent.st_mode)
        or _is_reparse(current_parent)
        or _directory_custody_identity(current_parent)
        != _directory_custody_identity(candidate_root_info)
    ):
        raise StageError("Candidate image receipt parent drifted before publication.")
    _same_plain_file_or_absent(output_path, None, "Candidate image receipt")
    _same_plain_file_or_absent(
        temporary,
        temporary_info_after,
        "Candidate image receipt temporary file",
    )
    os.replace(temporary, output_path)

    published = _plain_file_or_absent(output_path, "Candidate image receipt")
    if published is None:
        raise StageError("Candidate image receipt publication disappeared.")
    published_size, published_digest = _hash_file(output_path)
    if published_size != len(receipt_bytes) or published_digest != hashlib.sha256(receipt_bytes).hexdigest():
        raise StageError("Candidate image receipt published bytes failed verification.")


def create_image_receipt(
    inspect_payload: object,
    *,
    manifest_path: Path,
    dockerfile_path: Path,
    dockerignore_path: Path,
    lock_path: Path,
    platform: str,
    output_path: Path | None = None,
    emit: bool = True,
    publication_custody: tuple[
        Path,
        Path,
        Path,
        os.stat_result,
        os.stat_result | None,
        os.stat_result | None,
    ]
    | None = None,
) -> dict[str, object]:
    if not isinstance(inspect_payload, list) or len(inspect_payload) != 1 or not isinstance(inspect_payload[0], dict):
        raise StageError("Docker image inspection must contain exactly one image object.")
    image = inspect_payload[0]
    if publication_custody is None and output_path is not None:
        publication_custody = _receipt_publication_custody(manifest_path, output_path)
    _load_manifest(manifest_path)
    dockerfile_text = dockerfile_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    first_instruction = next(
        (line.strip() for line in dockerfile_text.splitlines() if line.strip()), ""
    )
    if not first_instruction.startswith("FROM "):
        raise StageError("Candidate Dockerfile does not begin with a FROM instruction.")
    base_reference = first_instruction.removeprefix("FROM ").strip()
    if platform != "linux/amd64":
        raise StageError(f"Candidate image receipt requires linux/amd64, found {platform!r}.")
    rootfs = image.get("RootFS")
    config = image.get("Config")
    if not isinstance(rootfs, dict) or rootfs.get("Type") != "layers" or not isinstance(rootfs.get("Layers"), list):
        raise StageError("Docker image inspection has invalid RootFS layers.")
    layers = rootfs["Layers"]
    if not layers or not all(isinstance(layer, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", layer) for layer in layers):
        raise StageError("Docker image inspection has invalid RootFS diff IDs.")
    if not isinstance(config, dict):
        raise StageError("Docker image inspection has an invalid execution config.")
    execution_keys = (
        "ArgsEscaped",
        "Cmd",
        "Entrypoint",
        "Env",
        "ExposedPorts",
        "Healthcheck",
        "Labels",
        "OnBuild",
        "Shell",
        "StopSignal",
        "User",
        "Volumes",
        "WorkingDir",
    )
    execution_config = {key: config.get(key) for key in execution_keys}
    stable = {
        "execution_config": execution_config,
        "inputs": {
            "base_reference": base_reference,
            "build_context_manifest_sha256": _hash_file(manifest_path)[1],
            "dockerfile_sha256": _hash_file(dockerfile_path)[1],
            "dockerignore_sha256": _hash_file(dockerignore_path)[1],
            "requirements_dev_lock_sha256": _hash_file(lock_path)[1],
            "target_platform": platform,
        },
        "rootfs_diff_ids": layers,
        "schema": RECEIPT_SCHEMA,
    }
    stable_sha256 = hashlib.sha256(_canonical_json(stable)).hexdigest()
    receipt: dict[str, object] = {
        "diagnostics": {
            "created": image.get("Created"),
            "raw_image_id": image.get("Id"),
            "repo_digests": image.get("RepoDigests"),
        },
        "stable": stable,
        "stable_sha256": stable_sha256,
    }
    if publication_custody is not None:
        (
            project_root,
            output_path,
            temporary,
            candidate_root_info,
            output_info,
            temporary_info,
        ) = publication_custody
        _publish_image_receipt(
            _canonical_json(receipt),
            project_root=project_root,
            output_path=output_path,
            temporary=temporary,
            candidate_root_info=candidate_root_info,
            output_info=output_info,
            temporary_info=temporary_info,
        )
    if emit:
        print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return receipt


def _bounded_subprocess_detail(raw: bytes, *, limit: int = 400) -> str:
    detail = " ".join(raw.decode("utf-8", "replace").split())
    if len(detail) > limit:
        return f"{detail[:limit]}..."
    return detail


def inspect_image_and_create_receipt(
    *,
    docker: str,
    image_reference: str,
    manifest_path: Path,
    dockerfile_path: Path,
    dockerignore_path: Path,
    lock_path: Path,
    platform: str,
    output_path: Path,
) -> dict[str, object]:
    custody = _invalidate_image_receipt(
        _receipt_publication_custody(manifest_path, output_path)
    )
    command = [docker, "image", "inspect", image_reference]
    try:
        completed = subprocess.run(
            command,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        detail = " ".join(str(exc).split())
        if len(detail) > 400:
            detail = f"{detail[:400]}..."
        raise StageError(f"Docker image inspection could not launch: {detail}") from exc
    if completed.returncode:
        detail = _bounded_subprocess_detail(completed.stderr)
        suffix = f": {detail}" if detail else "."
        raise StageError(
            f"Docker image inspection failed ({completed.returncode}){suffix}"
        )
    try:
        inspect_text = completed.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise StageError("Docker image inspection output is not valid UTF-8.") from exc
    try:
        inspect_payload = json.loads(
            inspect_text,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant {value}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise StageError(f"Docker image inspection JSON is invalid: {exc}") from exc
    if (
        not isinstance(inspect_payload, list)
        or len(inspect_payload) != 1
        or not isinstance(inspect_payload[0], dict)
    ):
        raise StageError("Docker image inspection must contain exactly one image object.")
    image = inspect_payload[0]
    raw_image_id = image.get("Id")
    image_os = image.get("Os")
    image_architecture = image.get("Architecture")
    if (
        not isinstance(raw_image_id, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", raw_image_id)
        or image_os != "linux"
        or image_architecture != "amd64"
    ):
        raise StageError("Docker image inspection has an invalid image identity.")
    receipt = create_image_receipt(
        inspect_payload,
        manifest_path=manifest_path,
        dockerfile_path=dockerfile_path,
        dockerignore_path=dockerignore_path,
        lock_path=lock_path,
        platform=platform,
        output_path=output_path,
        emit=False,
        publication_custody=custody,
    )
    result = {
        "image_identity": {
            "architecture": image_architecture,
            "id": raw_image_id,
            "os": image_os,
        },
        "receipt": receipt,
    }
    sys.stdout.buffer.write(_canonical_json(result))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage = subparsers.add_parser("stage")
    stage.add_argument("--project-root", type=Path, required=True)
    stage.add_argument("--context-root", type=Path, required=True)
    stage.add_argument("--manifest", type=Path, required=True)
    stage.add_argument("--git", default="git")
    metadata = subparsers.add_parser("git-metadata")
    metadata.add_argument("--project-root", type=Path, required=True)
    metadata.add_argument("--metadata-root", type=Path, required=True)
    metadata.add_argument("--git", default="git")
    verify = subparsers.add_parser("verify-image")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    temporary = subparsers.add_parser("verify-temp")
    temporary.add_argument("--path", action="append", type=Path, required=True)
    pytest_runner = subparsers.add_parser("run-pytest")
    pytest_runner.add_argument("pytest_arguments", nargs=argparse.REMAINDER)
    receipt = subparsers.add_parser("image-receipt")
    receipt.add_argument("--manifest", type=Path, required=True)
    receipt.add_argument("--dockerfile", type=Path, required=True)
    receipt.add_argument("--dockerignore", type=Path, required=True)
    receipt.add_argument("--lock", type=Path, required=True)
    receipt.add_argument("--platform", required=True)
    receipt.add_argument("--output", type=Path, required=True)
    receipt.add_argument("--docker", required=True)
    receipt.add_argument("--image", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "stage":
            stage_context(
                arguments.project_root,
                arguments.context_root,
                arguments.manifest,
                git=arguments.git,
            )
        elif arguments.command == "git-metadata":
            create_git_metadata(
                arguments.project_root,
                arguments.metadata_root,
                git=arguments.git,
            )
        elif arguments.command == "verify-image":
            verify_image_inventory(arguments.root, arguments.manifest)
        elif arguments.command == "verify-temp":
            verify_runtime_temp(arguments.path)
        elif arguments.command == "run-pytest":
            pytest_arguments = arguments.pytest_arguments
            if pytest_arguments[:1] == ["--"]:
                pytest_arguments = pytest_arguments[1:]
            return run_linux_pytest(pytest_arguments)
        else:
            inspect_image_and_create_receipt(
                docker=arguments.docker,
                image_reference=arguments.image,
                manifest_path=arguments.manifest,
                dockerfile_path=arguments.dockerfile,
                dockerignore_path=arguments.dockerignore,
                lock_path=arguments.lock,
                platform=arguments.platform,
                output_path=arguments.output,
            )
    except StageError as exc:
        print(f"candidate build context refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
