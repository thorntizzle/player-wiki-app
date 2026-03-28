from __future__ import annotations

import hashlib
import time
from pathlib import Path
from threading import Lock

from .repository import Repository


class RepositoryStore:
    def __init__(
        self,
        campaigns_dir: Path,
        *,
        page_store,
        reload_enabled: bool,
        scan_interval_seconds: int,
    ) -> None:
        self.campaigns_dir = campaigns_dir
        self.page_store = page_store
        self.reload_enabled = reload_enabled
        self.scan_interval_seconds = max(scan_interval_seconds, 0)
        self._lock = Lock()
        self._repository: Repository | None = None
        self._fingerprint: str | None = None
        self._last_check_monotonic = 0.0
        self._last_loaded_unix = 0.0

    def get(self) -> Repository:
        with self._lock:
            if self._repository is None:
                self._reload_repository()
                return self._repository

            if not self.reload_enabled:
                return self._repository

            now = time.monotonic()
            if now - self._last_check_monotonic < self.scan_interval_seconds:
                return self._repository

            self._last_check_monotonic = now
            fingerprint = self._build_fingerprint()
            if fingerprint != self._fingerprint:
                self._reload_repository()

            return self._repository

    def status(self) -> dict[str, object]:
        return {
            "reload_enabled": self.reload_enabled,
            "scan_interval_seconds": self.scan_interval_seconds,
            "last_loaded_unix": self._last_loaded_unix,
            "campaigns_dir": str(self.campaigns_dir),
        }

    def refresh(self) -> Repository:
        with self._lock:
            self._reload_repository()
            return self._repository

    def _reload_repository(self) -> None:
        self._repository = Repository.load(self.campaigns_dir, self.page_store)
        self._fingerprint = self._build_fingerprint()
        self._last_check_monotonic = time.monotonic()
        self._last_loaded_unix = time.time()

    def _build_fingerprint(self) -> str:
        hasher = hashlib.sha1()
        file_count = 0

        for file_path in self._iter_relevant_files():
            stat = file_path.stat()
            relative_path = file_path.relative_to(self.campaigns_dir).as_posix()
            hasher.update(relative_path.encode("utf-8"))
            hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("utf-8"))
            file_count += 1

        return f"{file_count}:{hasher.hexdigest()}"

    def _iter_relevant_files(self) -> list[Path]:
        files = list(self.campaigns_dir.rglob("*.md"))
        files.extend(self.campaigns_dir.rglob("*.yaml"))
        return sorted(files)
