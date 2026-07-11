from __future__ import annotations

import errno
import math
import os
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import BinaryIO, Literal


LeaseMode = Literal["shared", "exclusive"]

_LOCK_SUFFIX = ".runtime.lock"
_RESTORE_JOURNAL_SUFFIX = ".restore-journal.json"
_POLL_INTERVAL_SECONDS = 0.025


class RuntimeStateLeaseError(RuntimeError):
    """Base error for application-state coordination failures."""


class RuntimeStateBusyError(RuntimeStateLeaseError):
    """Raised when another process holds an incompatible state lease."""


class RuntimeRecoveryRequiredError(RuntimeStateLeaseError):
    """Raised when an interrupted restore must be resolved before startup."""


def canonical_database_path(database_path: Path) -> Path:
    return Path(database_path).expanduser().resolve(strict=False)


def runtime_state_lock_path(database_path: Path) -> Path:
    database = canonical_database_path(database_path)
    return Path(f"{database}{_LOCK_SUFFIX}")


def active_restore_journal_path(database_path: Path) -> Path:
    database = canonical_database_path(database_path)
    return Path(f"{database}{_RESTORE_JOURNAL_SUFFIX}")


def has_active_restore_journal(database_path: Path) -> bool:
    return os.path.lexists(active_restore_journal_path(database_path))


class RuntimeStateLease(AbstractContextManager["RuntimeStateLease"]):
    """A held cross-process lease for the configured application state."""

    def __init__(self, lock_file: BinaryIO, *, lock_path: Path, mode: LeaseMode) -> None:
        self._lock_file = lock_file
        self.lock_path = lock_path
        self.mode = mode
        self._closed = False

    def __enter__(self) -> RuntimeStateLease:
        if self._closed:
            raise RuntimeStateLeaseError("The application-state lease is already closed.")
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        try:
            _release_file_lock(self._lock_file)
        except OSError:
            raise RuntimeStateLeaseError(
                "The application-state lease could not be released cleanly."
            ) from None
        finally:
            self._closed = True
            self._lock_file.close()


def acquire_runtime_state_lease(
    database_path: Path,
    *,
    timeout_seconds: float = 0.0,
) -> RuntimeStateLease:
    """Acquire the shared lease required by supported app processes."""

    lease = acquire_state_lease(
        database_path,
        mode="shared",
        timeout_seconds=timeout_seconds,
    )
    if has_active_restore_journal(database_path):
        lease.close()
        raise RuntimeRecoveryRequiredError(
            "An interrupted restore requires explicit recovery before the app can start."
        )
    return lease


def acquire_exclusive_state_lease(
    database_path: Path,
    *,
    timeout_seconds: float = 0.0,
) -> RuntimeStateLease:
    """Acquire the exclusive lease reserved for restore and recovery work."""

    return acquire_state_lease(
        database_path,
        mode="exclusive",
        timeout_seconds=timeout_seconds,
    )


def acquire_state_lease(
    database_path: Path,
    *,
    mode: LeaseMode,
    timeout_seconds: float = 0.0,
) -> RuntimeStateLease:
    if mode not in ("shared", "exclusive"):
        raise ValueError("mode must be 'shared' or 'exclusive'.")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds < 0
    ):
        raise ValueError("timeout_seconds must be a finite non-negative number.")

    lock_path = runtime_state_lock_path(database_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+b")
    except OSError:
        raise RuntimeStateLeaseError(
            "The application-state lease file could not be opened."
        ) from None

    deadline = time.monotonic() + float(timeout_seconds)
    try:
        while True:
            try:
                _try_acquire_file_lock(lock_file, mode=mode)
                return RuntimeStateLease(lock_file, lock_path=lock_path, mode=mode)
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeStateBusyError(
                        "Application state is in use by an incompatible process; "
                        "stop that process or finish recovery before retrying."
                    ) from None
                time.sleep(min(_POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic())))
    except BaseException:
        lock_file.close()
        raise


def _try_acquire_file_lock(lock_file: BinaryIO, *, mode: LeaseMode) -> None:
    if os.name == "nt":
        _try_acquire_windows_file_lock(lock_file, mode=mode)
        return

    import fcntl

    operation = fcntl.LOCK_SH if mode == "shared" else fcntl.LOCK_EX
    try:
        fcntl.flock(lock_file.fileno(), operation | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            raise BlockingIOError from None
        raise


def _release_file_lock(lock_file: BinaryIO) -> None:
    if os.name == "nt":
        _release_windows_file_lock(lock_file)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _try_acquire_windows_file_lock(lock_file: BinaryIO, *, mode: LeaseMode) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = (
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        )

    lock_file_ex = ctypes.WinDLL("kernel32", use_last_error=True).LockFileEx
    lock_file_ex.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    )
    lock_file_ex.restype = wintypes.BOOL

    flags = 0x00000001
    if mode == "exclusive":
        flags |= 0x00000002
    overlapped = Overlapped()
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(lock_file.fileno()))
    if lock_file_ex(handle, flags, 0, 1, 0, ctypes.byref(overlapped)):
        return

    error_code = ctypes.get_last_error()
    if error_code in (32, 33):
        raise BlockingIOError from None
    raise OSError(error_code, "LockFileEx failed")


def _release_windows_file_lock(lock_file: BinaryIO) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = (
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        )

    unlock_file_ex = ctypes.WinDLL("kernel32", use_last_error=True).UnlockFileEx
    unlock_file_ex.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    )
    unlock_file_ex.restype = wintypes.BOOL

    overlapped = Overlapped()
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(lock_file.fileno()))
    if not unlock_file_ex(handle, 0, 1, 0, ctypes.byref(overlapped)):
        raise ctypes.WinError(ctypes.get_last_error())
