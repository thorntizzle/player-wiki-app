from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat
from typing import Any, BinaryIO, TextIO


_TEMP_CREATE_ATTEMPTS = 100


def atomic_write_bytes(destination: Path, data: bytes) -> int:
    """Publish bytes through a flushed and synced sibling before replacement."""
    payload = bytes(data)
    return _atomic_write(destination, payload, binary=True, encoding=None)


def atomic_write_text(destination: Path, text: str, *, encoding: str = "utf-8") -> int:
    """Publish text with the same newline handling as ``Path.write_text``."""
    if not isinstance(text, str):
        raise TypeError("data must be str, not %s" % text.__class__.__name__)
    return _atomic_write(destination, text, binary=False, encoding=encoding)


def _atomic_write(
    destination: Path,
    payload: bytes | str,
    *,
    binary: bool,
    encoding: str | None,
) -> int:
    destination = Path(destination)
    existing_mode = _existing_mode(destination)
    temp_path: Path | None = None
    handle: BinaryIO | TextIO | None = None

    try:
        temp_path, handle = _open_unique_temp(
            destination,
            binary=binary,
            encoding=encoding,
        )
        written = _write_full_payload(handle, payload)
        _flush_file(handle)
        _fsync_file(handle)
        _close_file(handle)
        handle = None
        if existing_mode is not None:
            _set_file_mode(temp_path, existing_mode)
        _replace_file(temp_path, destination)
        temp_path = None
    except BaseException:
        _cleanup_precommit_temp(handle, temp_path)
        raise

    try:
        _sync_parent_directory_best_effort(destination.parent)
    except Exception:
        # The replacement is already committed. Directory syncing is an
        # optional durability improvement and cannot safely report failure.
        pass
    return written


def _existing_mode(destination: Path) -> int | None:
    try:
        return stat.S_IMODE(destination.stat().st_mode)
    except FileNotFoundError:
        return None


def _open_unique_temp(
    destination: Path,
    *,
    binary: bool,
    encoding: str | None,
) -> tuple[Path, BinaryIO | TextIO]:
    mode = "xb" if binary else "x"
    open_kwargs: dict[str, Any] = {}
    if encoding is not None:
        open_kwargs["encoding"] = encoding

    for _ in range(_TEMP_CREATE_ATTEMPTS):
        temp_path = destination.with_name(f".{secrets.token_hex(4)}.tmp")
        try:
            return temp_path, temp_path.open(mode, **open_kwargs)
        except FileExistsError:
            continue
    raise FileExistsError(f"Could not create a unique temporary sibling for {destination}")


def _write_full_payload(handle: BinaryIO | TextIO, payload: bytes | str) -> int:
    total_written = 0
    while total_written < len(payload):
        written = handle.write(payload[total_written:])
        if written is None or written <= 0:
            raise OSError("Atomic file publication made no write progress.")
        total_written += written
    return total_written


def _flush_file(handle: BinaryIO | TextIO) -> None:
    handle.flush()


def _fsync_file(handle: BinaryIO | TextIO) -> None:
    os.fsync(handle.fileno())


def _close_file(handle: BinaryIO | TextIO) -> None:
    handle.close()


def _set_file_mode(path: Path, mode: int) -> None:
    os.chmod(path, mode)


def _replace_file(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _cleanup_precommit_temp(
    handle: BinaryIO | TextIO | None,
    temp_path: Path | None,
) -> None:
    if handle is not None:
        try:
            _close_file(handle)
        except BaseException:
            pass
    if temp_path is not None:
        try:
            temp_path.unlink(missing_ok=True)
        except BaseException:
            pass


def _sync_parent_directory_best_effort(parent_path: Path) -> None:
    if os.name != "posix":
        return
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(parent_path, flags)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
