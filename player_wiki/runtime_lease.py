from __future__ import annotations

import errno
import math
import os
import stat
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import BinaryIO, Callable, Literal


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


class _UnsafeStateIdentityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _DatabaseIdentity:
    exists: bool
    device: int | None = None
    file_id: int | None = None


_MISSING_DATABASE_IDENTITY = _DatabaseIdentity(exists=False)


@dataclass(slots=True)
class _OpenedLockFile:
    lock_file: BinaryIO
    validate_identity: Callable[[], None]
    close_auxiliary: Callable[[], None]

    def close_all(self) -> None:
        try:
            self.lock_file.close()
        finally:
            try:
                self.close_auxiliary()
            except OSError:
                pass


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
    timeout = _normalize_timeout(timeout_seconds)
    try:
        database = canonical_database_path(database_path)
    except (OSError, RuntimeError):
        raise RuntimeStateLeaseError(
            "The application-state lease identity is unavailable or unsafe."
        ) from None
    lock_path = Path(f"{database}{_LOCK_SUFFIX}")
    opened: _OpenedLockFile | None = None
    try:
        database_identity = _capture_database_identity(database)
        opened = _open_lock_file(lock_path)
        opened.validate_identity()
    except (OSError, _UnsafeStateIdentityError):
        if opened is not None:
            try:
                opened.close_all()
            except OSError:
                pass
        raise RuntimeStateLeaseError(
            "The application-state lease identity is unavailable or unsafe."
        ) from None

    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                _try_acquire_file_lock(opened.lock_file, mode=mode)
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeStateBusyError(
                        "Application state is in use by an incompatible process; "
                        "stop that process or finish recovery before retrying."
                    ) from None
                time.sleep(min(_POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic())))
                continue
            except OSError:
                raise RuntimeStateLeaseError(
                    "The application-state lease could not be acquired safely."
                ) from None

            try:
                opened.validate_identity()
                if _capture_database_identity(database) != database_identity:
                    raise _UnsafeStateIdentityError
                opened.close_auxiliary()
            except (OSError, _UnsafeStateIdentityError):
                raise RuntimeStateLeaseError(
                    "The application-state lease identity changed during acquisition."
                ) from None
            return RuntimeStateLease(
                opened.lock_file,
                lock_path=lock_path,
                mode=mode,
            )
    except BaseException:
        opened.close_all()
        raise


def _normalize_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("timeout_seconds must be a finite non-negative number.")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError):
        raise ValueError(
            "timeout_seconds must be a finite non-negative number."
        ) from None
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError("timeout_seconds must be a finite non-negative number.")
    return normalized


def _capture_database_identity(database_path: Path) -> _DatabaseIdentity:
    if os.name == "nt":
        return _capture_windows_database_identity(database_path)
    try:
        details = os.lstat(database_path)
    except FileNotFoundError:
        return _MISSING_DATABASE_IDENTITY
    except OSError:
        raise _UnsafeStateIdentityError from None
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise _UnsafeStateIdentityError
    return _DatabaseIdentity(
        exists=True,
        device=int(details.st_dev),
        file_id=int(details.st_ino),
    )


def _capture_windows_database_identity(database_path: Path) -> _DatabaseIdentity:
    try:
        handle = _windows_create_file(
            database_path,
            desired_access=0x00000080,
            creation_disposition=3,
            flags=0x00200000,
            share_mode=0x00000001 | 0x00000002 | 0x00000004,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) in (2, 3):
            return _MISSING_DATABASE_IDENTITY
        raise _UnsafeStateIdentityError from None

    try:
        attributes, link_count, volume_serial, file_index = (
            _windows_handle_information(handle)
        )
        if (
            attributes & 0x00000400
            or attributes & 0x00000010
            or link_count != 1
            or _windows_file_type(handle) != 0x0001
        ):
            raise _UnsafeStateIdentityError
        return _DatabaseIdentity(
            exists=True,
            device=volume_serial,
            file_id=file_index,
        )
    finally:
        try:
            _windows_close_handle(handle)
        except OSError:
            raise _UnsafeStateIdentityError from None


def _open_lock_file(lock_path: Path) -> _OpenedLockFile:
    if os.name == "nt":
        return _open_windows_lock_file(lock_path)
    return _open_posix_lock_file(lock_path)


def _open_posix_lock_file(lock_path: Path) -> _OpenedLockFile:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if not no_follow:
        raise _UnsafeStateIdentityError
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | no_follow
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    parent_fd = os.open(lock_path.parent, directory_flags)
    parent_identity = os.fstat(parent_fd)
    if not stat.S_ISDIR(parent_identity.st_mode):
        os.close(parent_fd)
        raise _UnsafeStateIdentityError

    file_flags = os.O_RDWR | os.O_CREAT | no_follow | getattr(os, "O_CLOEXEC", 0)
    file_flags |= getattr(os, "O_NONBLOCK", 0)
    lock_fd: int | None = None
    try:
        lock_fd = os.open(lock_path.name, file_flags, 0o600, dir_fd=parent_fd)
        try:
            lock_file = os.fdopen(lock_fd, "r+b", buffering=0)
        except BaseException:
            os.close(lock_fd)
            raise
    except BaseException:
        os.close(parent_fd)
        raise

    auxiliary_open = True

    def validate_identity() -> None:
        opened_parent = os.fstat(parent_fd)
        named_parent = os.stat(lock_path.parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(named_parent.st_mode)
            or (opened_parent.st_dev, opened_parent.st_ino)
            != (named_parent.st_dev, named_parent.st_ino)
        ):
            raise _UnsafeStateIdentityError

        opened = os.fstat(lock_file.fileno())
        named = os.stat(lock_path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or opened.st_nlink != 1
            or named.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise _UnsafeStateIdentityError

    def close_auxiliary() -> None:
        nonlocal auxiliary_open
        if auxiliary_open:
            os.close(parent_fd)
            auxiliary_open = False

    return _OpenedLockFile(lock_file, validate_identity, close_auxiliary)


def _open_windows_lock_file(lock_path: Path) -> _OpenedLockFile:
    import ctypes
    import msvcrt

    parent_handle = _windows_create_file(
        lock_path.parent,
        desired_access=0x00000080,
        creation_disposition=3,
        flags=0x02000000 | 0x00200000,
    )
    try:
        parent_attributes, _, _, _ = _windows_handle_information(parent_handle)
        if not parent_attributes & 0x00000010 or parent_attributes & 0x00000400:
            raise _UnsafeStateIdentityError

        lock_handle = _windows_create_file(
            lock_path,
            desired_access=0x80000000 | 0x40000000,
            creation_disposition=4,
            flags=0x00000080 | 0x00200000,
        )
    except BaseException:
        _windows_close_handle(parent_handle)
        raise

    try:
        descriptor = msvcrt.open_osfhandle(
            int(lock_handle),
            os.O_RDWR | getattr(os, "O_BINARY", 0),
        )
    except BaseException:
        _windows_close_handle(lock_handle)
        _windows_close_handle(parent_handle)
        raise
    try:
        lock_file = os.fdopen(descriptor, "r+b", buffering=0)
    except BaseException:
        os.close(descriptor)
        _windows_close_handle(parent_handle)
        raise

    auxiliary_open = True

    def validate_identity() -> None:
        handle = msvcrt.get_osfhandle(lock_file.fileno())
        attributes, link_count, _, file_index = _windows_handle_information(handle)
        if (
            attributes & 0x00000400
            or attributes & 0x00000010
            or link_count != 1
            or _windows_file_type(handle) != 0x0001
        ):
            raise _UnsafeStateIdentityError

        opened = os.fstat(lock_file.fileno())
        named = os.lstat(lock_path)
        named_attributes = getattr(named, "st_file_attributes", 0)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or opened.st_nlink != 1
            or named.st_nlink != 1
            or named_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            or opened.st_ino != named.st_ino
            or (file_index and opened.st_ino != file_index)
        ):
            raise _UnsafeStateIdentityError

    def close_auxiliary() -> None:
        nonlocal auxiliary_open
        if auxiliary_open:
            _windows_close_handle(parent_handle)
            auxiliary_open = False

    return _OpenedLockFile(lock_file, validate_identity, close_auxiliary)


def _windows_create_file(
    path: Path,
    *,
    desired_access: int,
    creation_disposition: int,
    flags: int,
    share_mode: int = 0x00000001 | 0x00000002,
) -> int:
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        desired_access,
        share_mode,
        None,
        creation_disposition,
        flags,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle)


def _windows_handle_information(handle: int) -> tuple[int, int, int, int]:
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    get_information = ctypes.WinDLL(
        "kernel32", use_last_error=True
    ).GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    information = ByHandleFileInformation()
    if not get_information(wintypes.HANDLE(handle), ctypes.byref(information)):
        raise ctypes.WinError(ctypes.get_last_error())
    file_index = (int(information.nFileIndexHigh) << 32) | int(
        information.nFileIndexLow
    )
    return (
        int(information.dwFileAttributes),
        int(information.nNumberOfLinks),
        int(information.dwVolumeSerialNumber),
        file_index,
    )


def _windows_file_type(handle: int) -> int:
    import ctypes
    from ctypes import wintypes

    get_file_type = ctypes.WinDLL("kernel32", use_last_error=True).GetFileType
    get_file_type.argtypes = (wintypes.HANDLE,)
    get_file_type.restype = wintypes.DWORD
    return int(get_file_type(wintypes.HANDLE(handle)))


def _windows_close_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(wintypes.HANDLE(handle)):
        raise ctypes.WinError(ctypes.get_last_error())


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
