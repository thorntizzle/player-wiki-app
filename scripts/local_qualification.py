"""Local evidence primitives. No application imports, mutation adapter or replay."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import time
import uuid
from typing import Iterator


class QualificationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def regular_path(path: Path, *, directory: bool = False) -> Path:
    """Reject links/reparse points on the complete existing literal path."""
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise QualificationError("Link/reparse input is unsupported")
    info = path.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise QualificationError("Unexpected input kind")
    return path


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def file_identity(path: Path) -> dict:
    path = regular_path(path)
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if _identity(before) != _identity(opened):
            raise QualificationError("Input changed before open")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
        if _identity(opened) != _identity(os.fstat(stream.fileno())):
            raise QualificationError("Input changed during capture")
    if _identity(before) != _identity(regular_path(path).stat()):
        raise QualificationError("Input changed during capture")
    return {"bytes": before.st_size, "sha256": h.hexdigest()}


def write_new_json(path: Path, value: object) -> None:
    """Publish complete bytes atomically without replacing an existing name."""
    regular_path(path.parent, directory=True)
    payload = canonical(value)
    pending = path.with_name(path.name + ".pending-" + uuid.uuid4().hex)
    with pending.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if os.name == "nt":
            os.rename(pending, path)  # Windows rename fails if destination exists
        else:
            os.link(pending, path)  # POSIX rename would replace an existing name
    finally:
        if pending.exists():
            pending.unlink()


def load_json(path: Path) -> object:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise QualificationError("Duplicate JSON key")
            result[key] = value
        return result
    with regular_path(path).open("r", encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             QualificationError("Nonfinite JSON")))


def _tree(root: Path) -> tuple[dict[str, dict], list[str], dict[str, tuple]]:
    regular_path(root, directory=True)
    files, directories, observations = {}, [], {}
    def traversal_failed(error):
        raise error
    for folder, children, names in os.walk(root, followlinks=False, onerror=traversal_failed):
        folder_path = regular_path(Path(folder), directory=True)
        for child in sorted(children):
            path = regular_path(folder_path / child, directory=True)
            directories.append(path.relative_to(root).as_posix())
        for name in sorted(names):
            path = regular_path(folder_path / name)
            key = path.relative_to(root).as_posix()
            files[key] = file_identity(path)
            observations[key] = _identity(path.stat())
    return dict(sorted(files.items())), sorted(directories), observations


def capture_file_tree(root: Path) -> dict:
    """Complete regular files/directories; traversal errors never supply evidence."""
    root = regular_path(root, directory=True)
    files, directories, observations = _tree(root)
    if (files, directories, observations) != _tree(root):
        raise QualificationError("File tree changed during capture")
    return {"files": files, "directories": directories}


def _cell(value: object) -> list:
    if value is None:
        return ["null"]
    if type(value) is bytes:
        return ["blob", len(value), hashlib.sha256(value).hexdigest()]
    if type(value) is float:
        return ["real", value.hex()]
    if type(value) is int:
        return ["integer", str(value)]
    if type(value) is str:
        encoded = value.encode("utf-8", errors="surrogatepass")
        return ["text", len(encoded), hashlib.sha256(encoded).hexdigest()]
    raise QualificationError("Unsupported SQLite cell type")


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def capture_state(database: Path, campaigns: Path) -> dict:
    """Complete typed multisets + files on an exclusively owned stopped corpus.

    This first primitive supports rollback-journal SQLite only. It is neither a
    backup nor an atomic DB/filesystem snapshot and cannot establish quiescence.
    """
    database, campaigns = regular_path(database), regular_path(campaigns, directory=True)
    with database.open("rb") as stream:
        header = stream.read(20)
    if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
        raise QualificationError("A stopped rollback-journal SQLite corpus is required")
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(database) + suffix).exists():
            raise QualificationError("SQLite sidecar requires separate disposition")
    db_before = file_identity(database)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True,
                                 timeout=1, isolation_level=None)
    try:
        connection.execute("PRAGMA query_only=ON")
        version = connection.execute("PRAGMA data_version").fetchone()[0]
        connection.execute("BEGIN")
        schema = [list(row) for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name")]
        tables = {}
        for (name,) in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name").fetchall():
            columns = [list(row) for row in connection.execute(
                "PRAGMA table_xinfo(" + _quoted(name) + ")")]
            rows = Counter(digest([_cell(cell) for cell in row]) for row in
                           connection.execute("SELECT * FROM " + _quoted(name)))
            tables[name] = {"columns": columns, "rows": sorted(rows.items()),
                            "row_count": sum(rows.values())}
        tree = capture_file_tree(campaigns)
        connection.rollback()
        if connection.execute("PRAGMA data_version").fetchone()[0] != version:
            raise QualificationError("Concurrent SQLite change during capture")
        if file_identity(database) != db_before:
            raise QualificationError("SQLite bytes changed during capture")
        for suffix in ("-wal", "-shm", "-journal"):
            if Path(str(database) + suffix).exists():
                raise QualificationError("SQLite sidecar appeared during capture")
        return {"format": "cpw-local-capture-v1", "complete": True,
                "database": db_before, "schema": schema, "tables": tables,
                "files": tree["files"], "directories": tree["directories"]}
    finally:
        connection.close()


def compare_states(before: dict, after: dict) -> dict:
    for value in (before, after):
        if (type(value) is not dict or value.get("format") != "cpw-local-capture-v1"
                or value.get("complete") is not True
                or set(value) != {"format", "complete", "database", "schema", "tables",
                                  "files", "directories"}):
            raise QualificationError("Complete compatible captures are required")
        def hashed(item):
            return (type(item) is str and len(item) == 64
                    and all(c in "0123456789abcdef" for c in item))
        def file_record(item):
            return (type(item) is dict and set(item) == {"bytes", "sha256"}
                    and type(item["bytes"]) is int and item["bytes"] >= 0
                    and hashed(item["sha256"]))
        if (not file_record(value["database"]) or type(value["schema"]) is not list
                or type(value["tables"]) is not dict or type(value["files"]) is not dict
                or type(value["directories"]) is not list):
            raise QualificationError("Malformed capture sections")
        if any(type(row) is not list or len(row) != 4 for row in value["schema"]):
            raise QualificationError("Malformed schema")
        names = [row[1] for row in value["schema"] if row[0] == "table"]
        if len(names) != len(set(names)) or set(names) != set(value["tables"]):
            raise QualificationError("Incomplete table inventory")
        for table in value["tables"].values():
            if (type(table) is not dict or set(table) != {"columns", "rows", "row_count"}
                    or type(table["columns"]) is not list or not table["columns"]
                    or any(type(column) is not list or len(column) != 7 for column in table["columns"])
                    or type(table["rows"]) is not list or type(table["row_count"]) is not int):
                raise QualificationError("Malformed table capture")
            keys, count = set(), 0
            for row in table["rows"]:
                if (type(row) not in (list, tuple) or len(row) != 2 or not hashed(row[0])
                        or type(row[1]) is not int or row[1] < 1 or row[0] in keys):
                    raise QualificationError("Malformed row multiset")
                keys.add(row[0])
                count += row[1]
            if count != table["row_count"]:
                raise QualificationError("Incomplete row counts")
        for name, item in value["files"].items():
            if (type(name) is not str or not name or name.startswith("/")
                    or ".." in name.split("/") or not file_record(item)):
                raise QualificationError("Malformed campaign file capture")
    changed = [key for key in ("database", "schema", "tables", "files", "directories")
               if canonical(before[key]) != canonical(after[key])]
    return {"unchanged": not changed, "changed_sections": changed,
            "before_sha256": digest(before), "after_sha256": digest(after),
            "table_count": len(before["tables"]), "file_count": len(before["files"])}


class Timeline:
    def __init__(self):
        self.started_utc = utc_now()
        self._start = time.perf_counter()
        self.events = []

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        start = time.perf_counter() - self._start
        status = "complete"
        try:
            yield
        except BaseException:
            status = "failed"
            raise
        finally:
            self.events.append({"phase": name, "start_seconds": start,
                                "end_seconds": time.perf_counter() - self._start,
                                "status": status})

    def summary(self) -> dict:
        return summarize_timing(self.events, time.perf_counter() - self._start)


def summarize_timing(events: list[dict], elapsed_seconds: float) -> dict:
    if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        raise QualificationError("Invalid timing envelope")
    intervals, phases = [], []
    for event in events:
        start, end = event["start_seconds"], event["end_seconds"]
        if not all(type(x) in (int, float) and math.isfinite(x) for x in (start, end)):
            raise QualificationError("Nonfinite timing interval")
        if not 0 <= start <= end <= elapsed_seconds:
            raise QualificationError("Interval outside timing envelope")
        intervals.append((start, end))
        phases.append({**event, "seconds": end - start})
    union, last = 0.0, 0.0
    for start, end in sorted(intervals):
        union += max(0.0, end - max(start, last))
        last = max(last, end)
    return {"elapsed_seconds": elapsed_seconds, "recorded_union_seconds": union,
            "unattributed_seconds": max(0.0, elapsed_seconds - union),
            "overlap_seconds": max(0.0, sum(b-a for a, b in intervals) - union),
            "phases": phases,
            "limit": "Wall intervals include scheduling and observation; not exclusive CPU."}


class NativeProcess:
    """Own a minimal-rights native Windows handle opened while the child waits."""
    def __init__(self, pid: int):
        import ctypes
        from ctypes import wintypes as W
        if type(pid) is not int or pid <= 0:
            raise QualificationError("Invalid native PID")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = (W.DWORD, W.BOOL, W.DWORD)
        self.api.OpenProcess.restype = W.HANDLE
        self.api.GetProcessId.argtypes = (W.HANDLE,)
        self.api.GetProcessId.restype = W.DWORD
        self.api.WaitForSingleObject.argtypes = (W.HANDLE, W.DWORD)
        self.api.WaitForSingleObject.restype = W.DWORD
        self.api.GetExitCodeProcess.argtypes = (W.HANDLE, ctypes.POINTER(W.DWORD))
        self.api.GetExitCodeProcess.restype = W.BOOL
        self.api.CloseHandle.argtypes = (W.HANDLE,)
        self.api.CloseHandle.restype = W.BOOL
        self.handle = self.api.OpenProcess(0x00100000 | 0x00001000, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if self.api.GetProcessId(self.handle) != pid:
            self.close()
            raise QualificationError("Native process identity mismatch")

    def wait(self, seconds: float) -> dict:
        import ctypes
        from ctypes import wintypes as W
        milliseconds = min(0xFFFFFFFE, max(0, int(seconds * 1000)))
        result = self.api.WaitForSingleObject(self.handle, milliseconds)
        if result == 0x102:
            return {"signaled": False, "exit_code": None}
        if result != 0:
            raise QualificationError("Native wait failed")
        code = W.DWORD()
        if not self.api.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"signaled": True, "exit_code": code.value}

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise QualificationError("Native handle close failed")
            self.handle = None


class OwnedProcess:
    """Caller scopes argv/effects. Timeouts retain UNKNOWN and never kill/retry."""
    def __init__(self, argv: list[str], *, cwd: Path, env: dict, output_dir: Path):
        self.directory = regular_path(output_dir, directory=True)
        self.native = None
        self.native_pid = None
        self.stdout = (self.directory / "worker.stdout").open("xb")
        try:
            self.stderr = (self.directory / "worker.stderr").open("xb")
            try:
                self.child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                    stdout=self.stdout, stderr=self.stderr, shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except BaseException:
                self.stderr.close()
                raise
        except BaseException:
            self.stdout.close()
            raise

    def admit_native(self, pid: int, parent_pid: int):
        if type(pid) is not int or type(parent_pid) is not int or pid <= 0:
            raise QualificationError("Invalid worker witness")
        if pid != self.child.pid and parent_pid != self.child.pid:
            raise QualificationError("Worker is not the launched child/forwarded child")
        if self.child.poll() is not None:
            raise QualificationError("Launcher exited before live native admission")
        if os.name == "nt":
            self.native = NativeProcess(pid)
            if self.native.wait(0)["signaled"]:
                raise QualificationError("Native worker already exited")
        elif pid != self.child.pid:
            raise QualificationError("Forwarded child unsupported on this platform")
        self.native_pid = pid

    def finish(self, timeout_seconds: float) -> dict:
        if not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 60:
            raise QualificationError("Owned wait must be bounded to 0..60 seconds")
        deadline = time.monotonic() + timeout_seconds
        native_result = {"signaled": False, "exit_code": None}
        error_type = None
        handle_closed = self.native is None
        try:
            if self.native is not None:
                try:
                    native_result = self.native.wait(max(0, deadline-time.monotonic()))
                except Exception as error:
                    error_type = type(error).__name__
            try:
                launched = self.child.wait(timeout=max(0, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                launched = None
            except Exception as error:
                launched = None
                error_type = type(error).__name__
            if os.name != "nt" and self.native_pid == self.child.pid and launched is not None:
                native_result = {"signaled": True, "exit_code": launched}
        finally:
            if self.native is not None:
                try:
                    self.native.close()
                    handle_closed = True
                except Exception as error:
                    error_type = type(error).__name__
            self.stdout.close()
            self.stderr.close()
        closed = launched is not None and native_result["signaled"] and handle_closed and error_type is None
        return {"state": "closed" if closed else "unknown", "launched_pid": self.child.pid,
                "native_pid": self.native_pid, "launched_exit_code": launched,
                "native_exit_code": native_result["exit_code"], "native_handle_closed": handle_closed,
                "observation_error_type": error_type,
                "normal_exit": closed and launched == native_result["exit_code"] == 0}
