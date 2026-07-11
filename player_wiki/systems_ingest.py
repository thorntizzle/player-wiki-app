from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import stat
import struct
from typing import BinaryIO, Iterator
import unicodedata
import zipfile
import zlib

from .local_temp import temporary_directory


class SystemsIngestError(ValueError):
    pass


@dataclass(frozen=True)
class SystemsArchiveLimits:
    max_raw_bytes: int = 64 * 1024**2
    max_compressed_bytes: int = 64 * 1024**2
    max_entries: int = 20_000
    max_member_bytes: int = 32 * 1024**2
    max_total_uncompressed_bytes: int = 512 * 1024**2
    max_compression_ratio: int = 200

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


DEFAULT_SYSTEMS_ARCHIVE_LIMITS = SystemsArchiveLimits()
_ARCHIVE_COPY_CHUNK_SIZE = 64 * 1024
_MAX_ARCHIVE_PATH_BYTES = 1024
_MAX_ARCHIVE_COMPONENT_BYTES = 255
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
    *(f"com{index}" for index in "¹²³"),
    *(f"lpt{index}" for index in "¹²³"),
}
_WINDOWS_SPECIAL_CHARS = set('<>:"|?*')
_SUPPORTED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}


def configured_systems_archive_limits(value: object = None) -> SystemsArchiveLimits:
    if value is None:
        return DEFAULT_SYSTEMS_ARCHIVE_LIMITS
    if not isinstance(value, SystemsArchiveLimits):
        raise ValueError("SYSTEMS_ARCHIVE_LIMITS must be a SystemsArchiveLimits instance")
    return value


def _normalize_archive_member_path(raw_name: str) -> PurePosixPath:
    if not isinstance(raw_name, str) or not raw_name:
        raise SystemsIngestError("Import archive contains an invalid file path.")
    if len(raw_name.encode("utf-8")) > _MAX_ARCHIVE_PATH_BYTES:
        raise SystemsIngestError("Import archive contains an invalid file path.")
    if raw_name.startswith(("/", "\\")) or "\\" in raw_name:
        raise SystemsIngestError("Import archives must not contain absolute or backslash paths.")
    if unicodedata.normalize("NFC", raw_name) != raw_name:
        raise SystemsIngestError("Import archive paths must use normalized Unicode names.")
    if any(unicodedata.category(character).startswith("C") for character in raw_name):
        raise SystemsIngestError("Import archive contains an invalid file path.")

    normalized = raw_name[:-1] if raw_name.endswith("/") else raw_name
    raw_parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in raw_parts):
        raise SystemsIngestError(
            "Import archives must not contain empty or dot segments, or parent-relative paths."
        )

    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise SystemsIngestError("Import archives must not contain absolute or parent-relative paths.")
    for component in pure_path.parts:
        if len(component.encode("utf-8")) > _MAX_ARCHIVE_COMPONENT_BYTES:
            raise SystemsIngestError("Import archive contains an invalid file path.")
        if component.endswith((" ", ".")) or any(
            character in _WINDOWS_SPECIAL_CHARS for character in component
        ):
            raise SystemsIngestError("Import archive contains a Windows-unsafe file path.")
        reserved_stem = component.rstrip(" .").split(".", 1)[0].casefold()
        if reserved_stem in _WINDOWS_RESERVED_NAMES:
            raise SystemsIngestError("Import archive contains a Windows-reserved file path.")
    return pure_path


def _member_is_special(member: zipfile.ZipInfo) -> bool:
    if member.create_system != 3:
        return False
    mode = (member.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type == 0:
        return False
    expected_type = stat.S_IFDIR if member.is_dir() else stat.S_IFREG
    return file_type != expected_type


def _validate_archive_members(
    members: list[zipfile.ZipInfo],
    *,
    limits: SystemsArchiveLimits,
) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    if len(members) > limits.max_entries:
        raise SystemsIngestError("Import archive contains too many entries.")

    validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    exact_names: set[str] = set()
    casefold_names: set[str] = set()
    nfc_names: set[str] = set()
    file_paths: set[tuple[str, ...]] = set()
    implicit_parent_paths: set[tuple[str, ...]] = set()
    compressed_total = 0
    uncompressed_total = 0

    for member in members:
        raw_name = getattr(member, "orig_filename", member.filename)
        pure_path = _normalize_archive_member_path(raw_name)
        logical_name = pure_path.as_posix()
        exact_key = logical_name
        casefold_key = logical_name.casefold()
        nfc_key = unicodedata.normalize("NFC", logical_name)
        if (
            exact_key in exact_names
            or casefold_key in casefold_names
            or nfc_key in nfc_names
        ):
            raise SystemsIngestError("Import archive contains duplicate file paths.")
        exact_names.add(exact_key)
        casefold_names.add(casefold_key)
        nfc_names.add(nfc_key)

        parts_key = tuple(part.casefold() for part in pure_path.parts)
        is_directory = member.is_dir()
        for index in range(1, len(parts_key)):
            if parts_key[:index] in file_paths:
                raise SystemsIngestError("Import archive contains conflicting file paths.")
        if not is_directory and parts_key in implicit_parent_paths:
            raise SystemsIngestError("Import archive contains conflicting file paths.")
        if not is_directory:
            file_paths.add(parts_key)
        implicit_parent_paths.update(
            parts_key[:index] for index in range(1, len(parts_key))
        )

        if member.flag_bits & 0x1:
            raise SystemsIngestError("Encrypted import archive entries are not supported.")
        if member.compress_type not in _SUPPORTED_COMPRESSION:
            raise SystemsIngestError("Import archive uses unsupported compression.")
        if _member_is_special(member):
            raise SystemsIngestError("Import archive contains unsupported special entries.")
        if member.compress_size < 0 or member.file_size < 0:
            raise SystemsIngestError("Import archive contains invalid size metadata.")

        compressed_total += member.compress_size
        if compressed_total > limits.max_compressed_bytes:
            raise SystemsIngestError("Import archive compressed content is too large.")
        if not is_directory:
            if member.file_size > limits.max_member_bytes:
                raise SystemsIngestError("Import archive contains a file that is too large.")
            uncompressed_total += member.file_size
            if uncompressed_total > limits.max_total_uncompressed_bytes:
                raise SystemsIngestError("Import archive expanded content is too large.")
            if member.file_size and member.compress_size == 0:
                raise SystemsIngestError("Import archive contains invalid compression metadata.")
            if member.file_size > member.compress_size * limits.max_compression_ratio:
                raise SystemsIngestError("Import archive compression ratio is too high.")

        validated.append((member, pure_path))
    return validated


def _prepare_archive_source(
    source: bytes | bytearray | os.PathLike[str] | str | BinaryIO,
    *,
    limits: SystemsArchiveLimits,
) -> tuple[BinaryIO | BytesIO, bool]:
    should_close = False
    if isinstance(source, (bytes, bytearray)):
        if len(source) > limits.max_raw_bytes:
            raise SystemsIngestError("Import archive is too large.")
        stream: BinaryIO | BytesIO = BytesIO(source)
        should_close = True
    elif isinstance(source, (str, os.PathLike)):
        try:
            source_path = Path(source)
            if source_path.stat().st_size > limits.max_raw_bytes:
                raise SystemsIngestError("Import archive is too large.")
            stream = source_path.open("rb")
        except SystemsIngestError:
            raise
        except (AttributeError, OSError, TypeError, ValueError):
            raise SystemsIngestError("Import archive could not be safely opened.") from None
        should_close = True
    else:
        stream = source
        try:
            original_position = stream.tell()
            stream.seek(0, os.SEEK_END)
            raw_size = stream.tell()
            stream.seek(0)
        except (AttributeError, OSError, TypeError, ValueError):
            raise SystemsIngestError("Import archive must be a seekable binary file.") from None
        if (
            isinstance(original_position, bool)
            or not isinstance(original_position, int)
            or isinstance(raw_size, bool)
            or not isinstance(raw_size, int)
            or original_position < 0
            or raw_size < 0
        ):
            raise SystemsIngestError("Import archive must be a seekable binary file.")
        if raw_size > limits.max_raw_bytes:
            try:
                stream.seek(original_position)
            except (AttributeError, OSError, TypeError, ValueError):
                pass
            raise SystemsIngestError("Import archive is too large.")
    return stream, should_close


def _resolve_extracted_data_root(extract_root: Path) -> Path:
    candidates = [extract_root]
    top_level_dirs = [path for path in extract_root.iterdir() if path.is_dir()]
    if len(top_level_dirs) == 1:
        candidates.append(top_level_dirs[0])

    for candidate in candidates:
        if (candidate / "data").is_dir():
            return candidate

    raise SystemsIngestError(
        "Import archives must contain a compatible DND 5E source data/ directory at the root or inside one top-level folder."
    )


@contextmanager
def extracted_systems_archive(
    source: bytes | bytearray | os.PathLike[str] | str | BinaryIO,
    *,
    limits: SystemsArchiveLimits | None = None,
) -> Iterator[Path]:
    active_limits = configured_systems_archive_limits(limits)
    stream, should_close = _prepare_archive_source(source, limits=active_limits)
    try:
        try:
            archive = zipfile.ZipFile(stream)
        except (
            AttributeError,
            EOFError,
            KeyError,
            NotImplementedError,
            OSError,
            OverflowError,
            struct.error,
            TypeError,
            UnicodeError,
            ValueError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
        ):
            raise SystemsIngestError("Import archive must be a valid supported ZIP file.") from None

        try:
            try:
                validated_members = _validate_archive_members(
                    archive.infolist(),
                    limits=active_limits,
                )
            except SystemsIngestError:
                raise
            except (
                AttributeError,
                EOFError,
                KeyError,
                NotImplementedError,
                OSError,
                OverflowError,
                struct.error,
                TypeError,
                UnicodeError,
                ValueError,
                zipfile.BadZipFile,
                zipfile.LargeZipFile,
            ):
                raise SystemsIngestError("Import archive must be a valid supported ZIP file.") from None
        except BaseException:
            archive.close()
            raise

        with archive, temporary_directory(prefix="player-wiki-systems-import-") as temp_dir:
            extract_root = Path(temp_dir) / "archive"
            extract_root.mkdir(parents=True, exist_ok=True)
            wrote_any_files = False
            total_written = 0

            for member, pure_path in validated_members:
                destination = extract_root.joinpath(*pure_path.parts)

                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                member_written = 0
                try:
                    with archive.open(member) as source_handle, destination.open("xb") as destination_handle:
                        while True:
                            chunk = source_handle.read(_ARCHIVE_COPY_CHUNK_SIZE)
                            if not chunk:
                                break
                            member_written += len(chunk)
                            total_written += len(chunk)
                            if (
                                member.compress_size == 0
                                or member_written
                                > member.compress_size * active_limits.max_compression_ratio
                            ):
                                raise SystemsIngestError("Import archive compression ratio is too high.")
                            if member_written > active_limits.max_member_bytes:
                                raise SystemsIngestError("Import archive contains a file that is too large.")
                            if total_written > active_limits.max_total_uncompressed_bytes:
                                raise SystemsIngestError("Import archive expanded content is too large.")
                            destination_handle.write(chunk)
                except SystemsIngestError:
                    raise
                except (
                    AttributeError,
                    UnicodeError,
                    ValueError,
                    zipfile.BadZipFile,
                    zlib.error,
                    NotImplementedError,
                    RuntimeError,
                    EOFError,
                    KeyError,
                    OSError,
                    OverflowError,
                    struct.error,
                    TypeError,
                ) as exc:
                    raise SystemsIngestError("Import archive could not be safely extracted.") from None
                wrote_any_files = True

            if not wrote_any_files:
                raise SystemsIngestError("Import archive did not contain any files.")
            yield _resolve_extracted_data_root(extract_root)
    finally:
        if should_close:
            try:
                stream.close()
            except (AttributeError, OSError, TypeError, ValueError):
                raise SystemsIngestError("Import archive could not be safely closed.") from None
