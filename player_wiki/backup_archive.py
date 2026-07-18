from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import unicodedata
import zipfile
import zlib
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Iterator

from .migrations import MigrationError, inspect_migration_ledger
from .sqlite_safety import SQLiteSnapshotEvidence, snapshot_sqlite_database


FORMAT_NAME = "campaign-player-wiki-backup"
FORMAT_VERSION = 2
DATABASE_MEMBER = "database/player_wiki.sqlite3"
MANIFEST_MEMBER = "manifest.json"
PRODUCER = "campaign-player-wiki"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_CHUNK_SIZE = 1024 * 1024
_WINDOWS_INVALID_COMPONENT_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul", "clock$",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


class BackupArchiveError(RuntimeError):
    """Raised when a backup archive cannot be safely created or validated."""


def _positive_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


@dataclass(frozen=True, slots=True)
class BackupArchiveLimits:
    compressed_archive_bytes: int = 8 * 1024**3
    member_count: int = 100_000
    database_bytes: int = 4 * 1024**3
    campaign_file_bytes: int = 4 * 1024**3
    expanded_payload_bytes: int = 16 * 1024**3
    manifest_bytes: int = 16 * 1024**2
    relative_path_bytes: int = 1024
    path_component_bytes: int = 255

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _positive_integer(name, getattr(self, name))


DEFAULT_LIMITS = BackupArchiveLimits()


@dataclass(frozen=True, slots=True)
class MigrationEvidence:
    ledger_exists: bool
    applied_version: int
    current_version: int
    is_current: bool
    applied_name: str | None
    applied_checksum: str | None


@dataclass(frozen=True, slots=True)
class BackupArchiveEvidence:
    archive_path: Path
    format_version: int
    verification_level: str
    manifest_hashes_verified: bool
    created_at: str
    database_filename: str
    database_byte_count: int
    database_sha256: str
    database_integrity_check: tuple[str, ...]
    database_foreign_key_violations: tuple[tuple[object, ...], ...]
    migration: MigrationEvidence
    campaign_file_count: int
    campaign_total_bytes: int
    member_count: int
    payload_byte_count: int


@dataclass(frozen=True, slots=True)
class CampaignFileEvidence:
    relative_path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class StagedBackupArchive:
    evidence: BackupArchiveEvidence
    database_path: Path
    campaigns_dir: Path
    campaign_files: tuple[CampaignFileEvidence, ...]


@dataclass(frozen=True, slots=True)
class BackupArchiveHooks:
    after_snapshot: Callable[[Path], None] | None = None
    after_campaign_scan: Callable[[], None] | None = None
    after_manifest_write: Callable[[], None] | None = None
    after_database_write: Callable[[], None] | None = None
    after_campaign_member_write: Callable[[str], None] | None = None
    before_archive_fsync: Callable[[Path], None] | None = None
    after_archive_write: Callable[[Path], None] | None = None
    after_reinspection: Callable[[BackupArchiveEvidence], None] | None = None
    before_publication: Callable[[Path], None] | None = None
    after_publication: Callable[[Path], None] | None = None


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def create_backup_archive_v2(
    *,
    db_path: Path,
    campaigns_dir: Path,
    backup_root: Path,
    archive_basename: str,
    created_at: str,
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
    snapshotter: Callable[..., SQLiteSnapshotEvidence] = snapshot_sqlite_database,
    hooks: BackupArchiveHooks | None = None,
) -> BackupArchiveEvidence:
    hooks = hooks or BackupArchiveHooks()
    db_path = Path(db_path)
    campaigns_dir = Path(campaigns_dir)
    backup_root = Path(backup_root)
    _validate_created_at(created_at)
    _validate_source_boundaries(db_path, campaigns_dir, backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    if backup_root.is_symlink() or _is_reparse_point(backup_root):
        raise BackupArchiveError("The backup root must be a regular directory.")

    snapshot_path: Path | None = None
    stage_path: Path | None = None
    try:
        snapshot_path = _exclusive_temp_path(backup_root, ".sqlite3")
        snapshot = snapshotter(source_path=db_path, destination_path=snapshot_path)
        _validate_snapshot_evidence(snapshot, snapshot_path, limits)
        if hooks.after_snapshot:
            hooks.after_snapshot(snapshot_path)

        migration = _inspect_database(snapshot_path)
        campaign_files = _scan_campaign_files(campaigns_dir, limits)
        if hooks.after_campaign_scan:
            hooks.after_campaign_scan()
        _verify_campaign_sources(campaign_files)

        manifest = _build_manifest(created_at, snapshot, migration, campaign_files)
        manifest_bytes = canonical_json_bytes(manifest)
        if len(manifest_bytes) > limits.manifest_bytes:
            raise BackupArchiveError("The backup manifest exceeds its size limit.")
        totals = _strict_object(manifest["totals"], "totals")
        if int(totals["payload_bytes"]) > limits.expanded_payload_bytes:
            raise BackupArchiveError("The backup payload exceeds its expanded size limit.")

        stage_path = _exclusive_temp_path(backup_root, ".zip")
        _write_v2_zip(stage_path, manifest_bytes, snapshot_path, campaign_files, limits, hooks)
        if hooks.before_archive_fsync:
            hooks.before_archive_fsync(stage_path)
        _sync_file(stage_path)
        if hooks.after_archive_write:
            hooks.after_archive_write(stage_path)

        evidence = inspect_backup_archive(stage_path, limits=limits)
        if hooks.after_reinspection:
            hooks.after_reinspection(evidence)
        if hooks.before_publication:
            hooks.before_publication(stage_path)
        final_path = _publish_no_clobber(stage_path, backup_root, archive_basename)
        stage_path = None
        try:
            if hooks.after_publication:
                hooks.after_publication(final_path)
            _sync_directory(backup_root)
        except BaseException:
            _remove_file(final_path)
            try:
                _sync_directory(backup_root)
            except OSError:
                pass
            raise
        return BackupArchiveEvidence(
            archive_path=final_path.resolve(),
            format_version=evidence.format_version,
            verification_level=evidence.verification_level,
            manifest_hashes_verified=evidence.manifest_hashes_verified,
            created_at=evidence.created_at,
            database_filename=evidence.database_filename,
            database_byte_count=evidence.database_byte_count,
            database_sha256=evidence.database_sha256,
            database_integrity_check=evidence.database_integrity_check,
            database_foreign_key_violations=evidence.database_foreign_key_violations,
            migration=evidence.migration,
            campaign_file_count=evidence.campaign_file_count,
            campaign_total_bytes=evidence.campaign_total_bytes,
            member_count=evidence.member_count,
            payload_byte_count=evidence.payload_byte_count,
        )
    except (BackupArchiveError, FileNotFoundError):
        raise
    except (OSError, sqlite3.Error, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise BackupArchiveError("The backup archive operation failed safely.") from exc
    finally:
        for path in (stage_path, snapshot_path):
            if path is not None:
                _remove_file(path)


def inspect_backup_archive(
    archive_path: Path,
    *,
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
) -> BackupArchiveEvidence:
    with stage_backup_archive(archive_path, limits=limits) as staged:
        return staged.evidence


@contextmanager
def stage_backup_archive(
    archive_path: Path,
    *,
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
) -> Iterator[StagedBackupArchive]:
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError("Backup archive not found.")
    if archive_path.is_symlink() or _is_reparse_point(archive_path) or not archive_path.is_file():
        raise BackupArchiveError("The backup archive must be a regular file.")
    if archive_path.stat().st_size > limits.compressed_archive_bytes:
        raise BackupArchiveError("The backup archive exceeds its compressed size limit.")

    with tempfile.TemporaryDirectory(prefix="player-wiki-archive-stage-") as temp_name:
        staging_root = Path(temp_name)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                infos = archive.infolist()
                version, manifest = _load_and_classify_manifest(archive, infos, limits)
                if version == 2:
                    staged = _stage_v2(archive_path, archive, infos, manifest, staging_root, limits)
                else:
                    staged = _stage_v1(archive_path, archive, infos, manifest, staging_root, limits)
        except (BackupArchiveError, FileNotFoundError):
            raise
        except (
            OSError, sqlite3.Error, zipfile.BadZipFile, EOFError, UnicodeError,
            json.JSONDecodeError, zlib.error, RecursionError, OverflowError,
        ) as exc:
            raise BackupArchiveError("The backup archive is invalid or unreadable.") from exc
        yield staged


def _load_and_classify_manifest(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    limits: BackupArchiveLimits,
) -> tuple[int, dict[str, object]]:
    if len(infos) > limits.member_count:
        raise BackupArchiveError("The backup archive has too many members.")
    by_name = _validate_zip_members(infos, limits)
    manifest_info = by_name.get(MANIFEST_MEMBER)
    if manifest_info is None:
        raise BackupArchiveError("The backup archive is missing manifest.json.")
    if manifest_info.file_size > limits.manifest_bytes:
        raise BackupArchiveError("The backup manifest exceeds its size limit.")
    raw = _read_member_limited(archive, manifest_info, limits.manifest_bytes)
    manifest = _load_json_object(raw)
    version = _strict_int(manifest.get("format_version"), "format_version", minimum=1)
    if version not in (1, 2):
        raise BackupArchiveError("The backup archive format is unsupported.")
    if version == 2 and raw != canonical_json_bytes(manifest):
        raise BackupArchiveError("The version 2 manifest is not canonically encoded.")
    return version, manifest


def _stage_v2(
    archive_path: Path,
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    manifest: dict[str, object],
    staging_root: Path,
    limits: BackupArchiveLimits,
) -> StagedBackupArchive:
    _require_keys(manifest, {"format", "format_version", "created_at", "producer", "database", "campaigns", "totals"})
    if manifest["format"] != FORMAT_NAME or manifest["producer"] != PRODUCER:
        raise BackupArchiveError("The backup manifest identity is invalid.")
    created_at = _strict_string(manifest["created_at"], "created_at")
    _validate_created_at(created_at)
    database = _strict_object(manifest["database"], "database")
    campaigns = _strict_object(manifest["campaigns"], "campaigns")
    totals = _strict_object(manifest["totals"], "totals")
    _require_keys(database, {"filename", "size", "sha256", "integrity_check", "foreign_key_violations", "migrations"})
    _require_keys(campaigns, {"file_count", "total_bytes", "files"})
    _require_keys(totals, {"member_count", "payload_bytes"})
    if database["filename"] != "player_wiki.sqlite3":
        raise BackupArchiveError("The backup database filename is invalid.")

    database_size = _strict_int(database["size"], "database.size", minimum=0)
    if database_size > limits.database_bytes:
        raise BackupArchiveError("The backup database exceeds its size limit.")
    database_hash = _strict_hash(database["sha256"], "database.sha256")
    expected_migration = _parse_migration_manifest(database["migrations"])
    integrity_manifest = _strict_string_list(database["integrity_check"], "database.integrity_check")
    if integrity_manifest != ("ok",):
        raise BackupArchiveError("The backup database integrity evidence is invalid.")
    fk_manifest = database["foreign_key_violations"]
    if not isinstance(fk_manifest, list) or fk_manifest:
        raise BackupArchiveError("The backup database foreign-key evidence is invalid.")

    raw_files = campaigns["files"]
    if not isinstance(raw_files, list):
        raise BackupArchiveError("The campaigns file list is invalid.")
    expected_files: list[tuple[str, int, str]] = []
    terminal_aliases: dict[str, str] = {}
    directory_aliases: dict[str, str] = {}
    for entry in raw_files:
        item = _strict_object(entry, "campaign file")
        _require_keys(item, {"path", "size", "sha256"})
        relative = _validate_relative_path(_strict_string(item["path"], "campaign path"), limits)
        _register_terminal_path(relative, terminal_aliases, directory_aliases)
        size = _strict_int(item["size"], "campaign size", minimum=0)
        if size > limits.campaign_file_bytes:
            raise BackupArchiveError("A campaign file exceeds its size limit.")
        expected_files.append((relative, size, _strict_hash(item["sha256"], "campaign sha256")))
    if expected_files != sorted(expected_files, key=lambda item: item[0].encode("utf-8")):
        raise BackupArchiveError("The campaign manifest order is not canonical.")

    file_count = _strict_int(campaigns["file_count"], "campaigns.file_count", minimum=0)
    total_bytes = _strict_int(campaigns["total_bytes"], "campaigns.total_bytes", minimum=0)
    member_count = _strict_int(totals["member_count"], "totals.member_count", minimum=0)
    payload_bytes = _strict_int(totals["payload_bytes"], "totals.payload_bytes", minimum=0)
    if file_count != len(expected_files) or total_bytes != sum(item[1] for item in expected_files):
        raise BackupArchiveError("The campaign manifest totals do not match its files.")
    if member_count != 2 + file_count or payload_bytes != database_size + total_bytes:
        raise BackupArchiveError("The backup payload totals are invalid.")
    if member_count > limits.member_count or payload_bytes > limits.expanded_payload_bytes:
        raise BackupArchiveError("The backup payload exceeds its approved limits.")

    expected_names = [MANIFEST_MEMBER, DATABASE_MEMBER, *(f"campaigns/{item[0]}" for item in expected_files)]
    actual_names = [info.filename for info in infos]
    if actual_names != expected_names:
        raise BackupArchiveError("The backup archive member layout or order is invalid.")
    expected_sizes = [
        infos[0].file_size,
        database_size,
        *(item[1] for item in expected_files),
    ]
    if any(info.file_size != expected_size for info, expected_size in zip(infos, expected_sizes, strict=True)):
        raise BackupArchiveError("A backup member central-directory size does not match the manifest.")

    database_path = staging_root / DATABASE_MEMBER
    database_info = infos[1]
    actual_db_size, actual_db_hash = _extract_and_hash(archive, database_info, database_path, limits.database_bytes)
    if (actual_db_size, actual_db_hash) != (database_size, database_hash):
        raise BackupArchiveError("The backup database hash or size does not match the manifest.")

    campaigns_dir = staging_root / "campaigns"
    for index, (relative, size, digest) in enumerate(expected_files, start=2):
        destination = campaigns_dir.joinpath(*PurePosixPath(relative).parts)
        actual_size, actual_hash = _extract_and_hash(archive, infos[index], destination, limits.campaign_file_bytes)
        if (actual_size, actual_hash) != (size, digest):
            raise BackupArchiveError("A campaign file hash or size does not match the manifest.")
    campaigns_dir.mkdir(parents=True, exist_ok=True)

    integrity, foreign_keys = _validate_database(database_path)
    migration = _inspect_database(database_path)
    migration = _validate_migration_evidence_compatibility(expected_migration, migration)
    evidence = BackupArchiveEvidence(
        archive_path=archive_path.resolve(), format_version=2, verification_level="verified_v2",
        manifest_hashes_verified=True, created_at=created_at, database_filename="player_wiki.sqlite3",
        database_byte_count=database_size, database_sha256=database_hash,
        database_integrity_check=integrity, database_foreign_key_violations=foreign_keys,
        migration=migration, campaign_file_count=file_count, campaign_total_bytes=total_bytes,
        member_count=member_count, payload_byte_count=payload_bytes,
    )
    return StagedBackupArchive(
        evidence,
        database_path,
        campaigns_dir,
        tuple(
            CampaignFileEvidence(relative, size, digest)
            for relative, size, digest in expected_files
        ),
    )


def _stage_v1(
    archive_path: Path,
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    manifest: dict[str, object],
    staging_root: Path,
    limits: BackupArchiveLimits,
) -> StagedBackupArchive:
    _require_keys(manifest, {"format_version", "created_at", "database_filename", "campaigns_dir_name"})
    created_at = _strict_string(manifest["created_at"], "created_at")
    _validate_legacy_created_at(created_at)
    database_filename = _validate_relative_path(_strict_string(manifest["database_filename"], "database filename"), limits)
    if "/" in database_filename:
        raise BackupArchiveError("The legacy database filename is invalid.")
    campaigns_name = _validate_relative_path(
        _strict_string(manifest["campaigns_dir_name"], "campaigns directory name"),
        limits,
    )
    if "/" in campaigns_name:
        raise BackupArchiveError("The legacy campaigns directory name is invalid.")
    db_member = f"database/{database_filename}"
    expected_prefixes = {MANIFEST_MEMBER, db_member}
    if not expected_prefixes.issubset({info.filename for info in infos}):
        raise BackupArchiveError("The legacy backup is missing required members.")
    campaign_infos = [info for info in infos if info.filename.startswith("campaigns/")]
    if any(info.filename not in expected_prefixes and not info.filename.startswith("campaigns/") for info in infos):
        raise BackupArchiveError("The legacy backup contains unexpected members.")
    if len(infos) != 2 + len(campaign_infos):
        raise BackupArchiveError("The legacy backup member layout is invalid.")

    db_info = next(info for info in infos if info.filename == db_member)
    if db_info.file_size > limits.database_bytes:
        raise BackupArchiveError("The legacy backup database exceeds its size limit.")
    database_path = staging_root / "database" / database_filename
    db_size, db_hash = _extract_and_hash(archive, db_info, database_path, limits.database_bytes)
    total = db_size
    campaigns_dir = staging_root / "campaigns"
    campaign_files: list[CampaignFileEvidence] = []
    for info in campaign_infos:
        relative = info.filename[len("campaigns/"):]
        relative = _validate_relative_path(relative, limits)
        if info.file_size > limits.campaign_file_bytes:
            raise BackupArchiveError("A legacy campaign file exceeds its size limit.")
        size, digest = _extract_and_hash(archive, info, campaigns_dir.joinpath(*PurePosixPath(relative).parts), limits.campaign_file_bytes)
        campaign_files.append(CampaignFileEvidence(relative, size, digest))
        total += size
        if total > limits.expanded_payload_bytes:
            raise BackupArchiveError("The legacy backup payload exceeds its size limit.")
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    integrity, foreign_keys = _validate_database(database_path)
    migration = _inspect_database(database_path)
    return StagedBackupArchive(
        BackupArchiveEvidence(
            archive_path=archive_path.resolve(), format_version=1, verification_level="legacy_v1",
            manifest_hashes_verified=False, created_at=created_at, database_filename=database_filename,
            database_byte_count=db_size, database_sha256=db_hash, database_integrity_check=integrity,
            database_foreign_key_violations=foreign_keys, migration=migration,
            campaign_file_count=len(campaign_infos), campaign_total_bytes=total - db_size,
            member_count=len(infos), payload_byte_count=total,
        ),
        database_path,
        campaigns_dir,
        tuple(sorted(campaign_files, key=lambda item: item.relative_path.encode("utf-8"))),
    )


def _build_manifest(
    created_at: str,
    snapshot: SQLiteSnapshotEvidence,
    migration: MigrationEvidence,
    campaign_files: list[tuple[str, Path, int, str, tuple[int, int, int, int]]],
) -> dict[str, object]:
    files = [{"path": relative, "size": size, "sha256": digest} for relative, _, size, digest, _ in campaign_files]
    campaign_total = sum(item[2] for item in campaign_files)
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "created_at": created_at,
        "producer": PRODUCER,
        "database": {
            "filename": "player_wiki.sqlite3", "size": snapshot.byte_count, "sha256": snapshot.sha256,
            "integrity_check": list(snapshot.integrity_check),
            "foreign_key_violations": [list(row) for row in snapshot.foreign_key_violations],
            "migrations": _migration_to_json(migration),
        },
        "campaigns": {"file_count": len(files), "total_bytes": campaign_total, "files": files},
        "totals": {"member_count": 2 + len(files), "payload_bytes": snapshot.byte_count + campaign_total},
    }


def _write_v2_zip(
    path: Path,
    manifest: bytes,
    snapshot_path: Path,
    files: list[tuple[str, Path, int, str, tuple[int, int, int, int]]],
    limits: BackupArchiveLimits,
    hooks: BackupArchiveHooks,
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        _write_bytes_member(archive, MANIFEST_MEMBER, manifest)
        if hooks.after_manifest_write:
            hooks.after_manifest_write()
        _write_file_member(archive, DATABASE_MEMBER, snapshot_path, limits.database_bytes)
        if hooks.after_database_write:
            hooks.after_database_write()
        for relative, source, size, digest, identity in files:
            _verify_source_identity(source, size, digest, identity)
            _write_file_member(archive, f"campaigns/{relative}", source, limits.campaign_file_bytes)
            if hooks.after_campaign_member_write:
                hooks.after_campaign_member_write(relative)
            _verify_source_identity(source, size, digest, identity)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.flag_bits = 0x800
    return info


def _write_bytes_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    with archive.open(_zip_info(name), "w") as destination:
        destination.write(data)


def _write_file_member(archive: zipfile.ZipFile, name: str, source: Path, maximum: int) -> None:
    total = 0
    with source.open("rb") as input_file, archive.open(_zip_info(name), "w", force_zip64=True) as destination:
        while chunk := input_file.read(_CHUNK_SIZE):
            total += len(chunk)
            if total > maximum:
                raise BackupArchiveError("A backup source changed beyond its approved size limit.")
            destination.write(chunk)


def _scan_campaign_files(
    root: Path,
    limits: BackupArchiveLimits,
) -> list[tuple[str, Path, int, str, tuple[int, int, int, int]]]:
    if not root.exists():
        return []
    if root.is_symlink() or _is_reparse_point(root) or not root.is_dir():
        raise BackupArchiveError("The campaigns source must be a regular directory.")
    files: list[tuple[str, Path, int, str, tuple[int, int, int, int]]] = []
    terminal_aliases: dict[str, str] = {}
    directory_aliases: dict[str, str] = {}
    total = 0
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        for name in list(dirnames):
            child = directory_path / name
            relative_dir = _validate_relative_path(child.relative_to(root).as_posix(), limits)
            _validate_source_entry(child, expect_directory=True)
            _register_directory_path(relative_dir, terminal_aliases, directory_aliases)
        for name in filenames:
            source = directory_path / name
            relative = _validate_relative_path(source.relative_to(root).as_posix(), limits)
            _validate_source_entry(source, expect_directory=False)
            _register_terminal_path(relative, terminal_aliases, directory_aliases)
            details = source.stat(follow_symlinks=False)
            size = details.st_size
            if size > limits.campaign_file_bytes:
                raise BackupArchiveError("A campaign source file exceeds its size limit.")
            total += size
            if total > limits.expanded_payload_bytes:
                raise BackupArchiveError("Campaign sources exceed the expanded payload limit.")
            digest = _hash_path(source, limits.campaign_file_bytes)
            identity = (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)
            files.append((relative, source, size, digest, identity))
            if len(files) + 2 > limits.member_count:
                raise BackupArchiveError("Campaign sources exceed the member limit.")
    files.sort(key=lambda item: item[0].encode("utf-8"))
    return files


def _validate_zip_members(infos: list[zipfile.ZipInfo], limits: BackupArchiveLimits) -> dict[str, zipfile.ZipInfo]:
    terminal_aliases: dict[str, str] = {}
    directory_aliases: dict[str, str] = {}
    by_name: dict[str, zipfile.ZipInfo] = {}
    expanded = 0
    for info in infos:
        name = _validate_relative_path(info.orig_filename, limits)
        if info.filename != name:
            raise BackupArchiveError("A backup path was altered by platform path normalization.")
        _register_terminal_path(name, terminal_aliases, directory_aliases)
        if info.is_dir() or name.endswith("/"):
            raise BackupArchiveError("Directory members are not allowed in backup archives.")
        if info.flag_bits & 0x1:
            raise BackupArchiveError("Encrypted backup members are not supported.")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise BackupArchiveError("The backup archive uses unsupported compression.")
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            raise BackupArchiveError("Special backup archive members are not allowed.")
        dos_attributes = info.external_attr & 0xFFFF
        if info.create_system == 0 and dos_attributes & (0x10 | 0x400):
            raise BackupArchiveError("Windows directory or reparse-point members are not allowed.")
        if info.file_size < 0 or info.compress_size < 0:
            raise BackupArchiveError("A backup member has an invalid size.")
        expanded += info.file_size
        if expanded > limits.expanded_payload_bytes + limits.manifest_bytes:
            raise BackupArchiveError("The backup archive exceeds its expanded size limit.")
        by_name[name] = info
    return by_name


def _validate_relative_path(value: str, limits: BackupArchiveLimits) -> str:
    if not value or value in (".", "..") or "\\" in value or "\x00" in value:
        raise BackupArchiveError("A backup path is unsafe.")
    if value != unicodedata.normalize("NFC", value):
        raise BackupArchiveError("A backup path is not NFC-normalized.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise BackupArchiveError("A backup path contains control characters.")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or any(part in ("", ".", "..") for part in posix.parts):
        raise BackupArchiveError("A backup path is unsafe.")
    if len(value.encode("utf-8")) > limits.relative_path_bytes:
        raise BackupArchiveError("A backup path exceeds its length limit.")
    for component in posix.parts:
        if len(component.encode("utf-8")) > limits.path_component_bytes:
            raise BackupArchiveError("A backup path component exceeds its length limit.")
        if component.endswith((".", " ")):
            raise BackupArchiveError("A backup path has a trailing dot or space.")
        if any(character in _WINDOWS_INVALID_COMPONENT_CHARACTERS for character in component):
            raise BackupArchiveError("A backup path contains a Windows-invalid character.")
        base = component.split(".", 1)[0].casefold()
        if base in _WINDOWS_RESERVED:
            raise BackupArchiveError("A backup path uses a reserved Windows name.")
    return posix.as_posix()


def _register_terminal_path(
    value: str,
    terminal_aliases: dict[str, str],
    directory_aliases: dict[str, str],
) -> None:
    parts = PurePosixPath(value).parts
    for length in range(1, len(parts) + 1):
        prefix = "/".join(parts[:length])
        alias = unicodedata.normalize("NFC", prefix).casefold()
        is_terminal = length == len(parts)
        if is_terminal:
            if alias in directory_aliases or alias in terminal_aliases:
                raise BackupArchiveError("Backup paths collide as a file/directory or duplicate path.")
            terminal_aliases[alias] = prefix
            continue
        if alias in terminal_aliases:
            raise BackupArchiveError("Backup paths collide at a file/directory prefix.")
        existing = directory_aliases.get(alias)
        if existing is not None and existing != prefix:
            raise BackupArchiveError("Backup paths collide on a supported filesystem.")
        directory_aliases[alias] = prefix


def _register_directory_path(
    value: str,
    terminal_aliases: dict[str, str],
    directory_aliases: dict[str, str],
) -> None:
    parts = PurePosixPath(value).parts
    for length in range(1, len(parts) + 1):
        prefix = "/".join(parts[:length])
        alias = unicodedata.normalize("NFC", prefix).casefold()
        if alias in terminal_aliases:
            raise BackupArchiveError("Backup paths collide at a file/directory prefix.")
        existing = directory_aliases.get(alias)
        if existing is not None and existing != prefix:
            raise BackupArchiveError("Backup paths collide on a supported filesystem.")
        directory_aliases[alias] = prefix


def _validate_source_boundaries(db_path: Path, campaigns_dir: Path, backup_root: Path) -> None:
    if db_path.is_symlink() or _is_reparse_point(db_path):
        raise BackupArchiveError("The database source must not be a symlink or reparse point.")
    db = db_path.resolve(strict=False)
    campaigns = campaigns_dir.resolve(strict=False)
    backup = backup_root.resolve(strict=False)
    if db == campaigns or db == backup or campaigns == backup:
        raise BackupArchiveError("Backup sources and destination must not overlap.")
    if _is_relative_to(backup, campaigns) or _is_relative_to(campaigns, backup):
        raise BackupArchiveError("The backup root and campaigns directory must not overlap.")
    if _is_relative_to(db, campaigns) or _is_relative_to(db, backup):
        raise BackupArchiveError("The database must not be inside campaign or backup storage.")


def _validate_source_entry(path: Path, *, expect_directory: bool) -> None:
    if path.is_symlink() or _is_reparse_point(path):
        raise BackupArchiveError("Symlink and reparse-point campaign entries are not allowed.")
    details = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(details.st_mode) if expect_directory else stat.S_ISREG(details.st_mode)
    if not expected:
        raise BackupArchiveError("Special campaign entries are not allowed.")


def _verify_campaign_sources(files: list[tuple[str, Path, int, str, tuple[int, int, int, int]]]) -> None:
    for _, path, size, digest, identity in files:
        _verify_source_identity(path, size, digest, identity)


def _verify_source_identity(path: Path, size: int, digest: str, identity: tuple[int, int, int, int]) -> None:
    _validate_source_entry(path, expect_directory=False)
    details = path.stat(follow_symlinks=False)
    current = (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)
    if current != identity or size != details.st_size or _hash_path(path, size) != digest:
        raise BackupArchiveError("A campaign source changed while the backup was being staged.")


def _validate_snapshot_evidence(snapshot: SQLiteSnapshotEvidence, path: Path, limits: BackupArchiveLimits) -> None:
    if Path(snapshot.final_path).resolve() != path.resolve() or snapshot.integrity_check != ("ok",) or snapshot.foreign_key_violations:
        raise BackupArchiveError("The SQLite snapshot evidence is invalid.")
    size, digest = _hash_path_with_size(path, limits.database_bytes)
    if size != snapshot.byte_count or digest != snapshot.sha256:
        raise BackupArchiveError("The SQLite snapshot evidence does not match its file.")


def _inspect_database(path: Path) -> MigrationEvidence:
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            inspection = inspect_migration_ledger(connection)
            row = None
            if inspection.applied_version:
                row = connection.execute(
                    "SELECT name, checksum FROM schema_migrations WHERE version = ?",
                    (inspection.applied_version,),
                ).fetchone()
    except MigrationError as exc:
        raise BackupArchiveError("The database migration ledger is not authoritative.") from exc
    return MigrationEvidence(
        ledger_exists=inspection.ledger_exists,
        applied_version=inspection.applied_version,
        current_version=inspection.current_version,
        is_current=inspection.is_current,
        applied_name=str(row[0]) if row else None,
        applied_checksum=str(row[1]) if row else None,
    )


def _validate_database(path: Path) -> tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]:
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        integrity = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall())
        foreign_keys = tuple(tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall())
    if integrity != ("ok",) or foreign_keys:
        raise BackupArchiveError("The backup database failed integrity validation.")
    return integrity, foreign_keys


def _migration_to_json(value: MigrationEvidence) -> dict[str, object]:
    return {
        "ledger_exists": value.ledger_exists, "applied_version": value.applied_version,
        "current_version": value.current_version, "is_current": value.is_current,
        "applied_name": value.applied_name, "applied_checksum": value.applied_checksum,
    }


def _parse_migration_manifest(value: object) -> MigrationEvidence:
    item = _strict_object(value, "database.migrations")
    _require_keys(item, {"ledger_exists", "applied_version", "current_version", "is_current", "applied_name", "applied_checksum"})
    ledger_exists = _strict_bool(item["ledger_exists"], "ledger_exists")
    applied = _strict_int(item["applied_version"], "applied_version", minimum=0)
    current = _strict_int(item["current_version"], "current_version", minimum=0)
    is_current = _strict_bool(item["is_current"], "is_current")
    name = _optional_string(item["applied_name"], "applied_name")
    checksum = _optional_hash(item["applied_checksum"], "applied_checksum")
    return MigrationEvidence(ledger_exists, applied, current, is_current, name, checksum)


def _validate_migration_evidence_compatibility(
    producer: MigrationEvidence,
    actual: MigrationEvidence,
) -> MigrationEvidence:
    expected_is_current = (
        producer.ledger_exists
        and producer.applied_version == producer.current_version
    )
    if (
        producer.applied_version > producer.current_version
        or producer.is_current is not expected_is_current
        or (
            producer.applied_version == 0
            and (
                producer.applied_name is not None
                or producer.applied_checksum is not None
            )
        )
        or (
            producer.applied_version > 0
            and (
                not producer.ledger_exists
                or producer.applied_name is None
                or producer.applied_checksum is None
            )
        )
    ):
        raise BackupArchiveError("The backup migration evidence is internally inconsistent.")
    if producer.current_version > actual.current_version:
        raise BackupArchiveError("The backup was produced by a newer migration registry.")
    if (
        producer.ledger_exists,
        producer.applied_version,
        producer.applied_name,
        producer.applied_checksum,
    ) != (
        actual.ledger_exists,
        actual.applied_version,
        actual.applied_name,
        actual.applied_checksum,
    ):
        raise BackupArchiveError("The backup database migration ledger does not match the manifest.")
    return actual


def _extract_and_hash(archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path, maximum: int) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    try:
        with archive.open(info, "r") as source, destination.open("xb") as output:
            while chunk := source.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > maximum:
                    raise BackupArchiveError("A backup member exceeds its approved size limit.")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except zipfile.BadZipFile as exc:
        raise BackupArchiveError("A backup member failed CRC validation.") from exc
    if total != info.file_size:
        raise BackupArchiveError("A backup member size is inconsistent.")
    return total, digest.hexdigest()


def _read_member_limited(archive: zipfile.ZipFile, info: zipfile.ZipInfo, maximum: int) -> bytes:
    with archive.open(info, "r") as source:
        data = source.read(maximum + 1)
        if len(data) > maximum or source.read(1):
            raise BackupArchiveError("The backup manifest exceeds its size limit.")
        return data


def _load_json_object(raw: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise BackupArchiveError("The backup manifest contains duplicate JSON keys.")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise BackupArchiveError("The backup manifest must be a JSON object.")
    return value


def _strict_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise BackupArchiveError(f"{name} must be an object.")
    return value


def _require_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise BackupArchiveError("The backup manifest schema is invalid.")


def _strict_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise BackupArchiveError(f"{name} must be a non-empty string.")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _strict_string(value, name)


def _strict_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise BackupArchiveError(f"{name} must be a boolean.")
    return value


def _strict_int(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BackupArchiveError(f"{name} must be an integer of at least {minimum}.")
    return value


def _strict_hash(value: object, name: str) -> str:
    text = _strict_string(value, name)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise BackupArchiveError(f"{name} must be a lowercase SHA-256 digest.")
    return text


def _optional_hash(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _strict_hash(value, name)


def _strict_string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BackupArchiveError(f"{name} must be a list of strings.")
    return tuple(value)


def _validate_created_at(value: str) -> None:
    if not value.endswith("Z"):
        raise BackupArchiveError("The backup timestamp must be UTC with a Z suffix.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BackupArchiveError("The backup timestamp is invalid.") from exc
    if parsed.tzinfo != UTC or parsed.microsecond:
        raise BackupArchiveError("The backup timestamp must use whole UTC seconds.")


def _validate_legacy_created_at(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise BackupArchiveError("The legacy backup timestamp is invalid.") from exc
    if parsed.utcoffset() != UTC.utcoffset(None) or parsed.microsecond:
        raise BackupArchiveError("The legacy backup timestamp must use whole UTC seconds.")


def _hash_path(path: Path, maximum: int) -> str:
    return _hash_path_with_size(path, maximum)[1]


def _hash_path_with_size(path: Path, maximum: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_SIZE):
            total += len(chunk)
            if total > maximum:
                raise BackupArchiveError("A backup source exceeds its approved size limit.")
            digest.update(chunk)
    return total, digest.hexdigest()


def _exclusive_temp_path(parent: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".player-wiki-backup-", suffix=suffix, dir=parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def _publish_no_clobber(stage: Path, root: Path, basename: str) -> Path:
    for suffix in range(0, 10_000):
        name = f"{basename}.zip" if suffix == 0 else f"{basename}-{suffix}.zip"
        candidate = root / name
        try:
            os.link(stage, candidate)
        except FileExistsError:
            continue
        except OSError as exc:
            raise BackupArchiveError("The backup archive could not be published without overwrite risk.") from exc
        stage.unlink()
        return candidate
    raise BackupArchiveError("No collision-free backup archive name was available.")


def _sync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _is_reparse_point(path: Path) -> bool:
    try:
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, FileNotFoundError):
        return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
