from __future__ import annotations

import hashlib
import time
from pathlib import Path
from threading import Lock

from .repository import Repository


class _DatabaseAuthoritativePageStore:
    """Delegate page reads while suppressing filesystem-to-database seeding."""

    def __init__(self, page_store) -> None:
        self._page_store = page_store

    @staticmethod
    def ensure_campaign_seeded(_campaign_slug: str, _content_dir: Path) -> None:
        return None

    def __getattr__(self, name: str):
        return getattr(self._page_store, name)


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
        self._repository_input_specs: tuple[tuple[Path, Path], ...] = ()
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

    def refresh_from_database(self) -> Repository:
        """Rebuild the repository view without seeding page rows from Markdown."""

        with self._lock:
            self._reload_repository(seed_from_filesystem=False)
            return self._repository

    def _reload_repository(self, *, seed_from_filesystem: bool = True) -> None:
        loading_page_store = (
            self.page_store
            if seed_from_filesystem
            else _DatabaseAuthoritativePageStore(self.page_store)
        )
        repository = Repository.load(self.campaigns_dir, loading_page_store)
        repository_input_specs = tuple(repository.input_specs)
        repository.page_store = self.page_store
        self._repository = repository
        self._repository_input_specs = repository_input_specs
        self._fingerprint = self._build_fingerprint()
        self._last_check_monotonic = time.monotonic()
        self._last_loaded_unix = time.time()

    def _build_fingerprint(self) -> str:
        hasher = hashlib.sha1()
        file_count = 0

        for path_key, file_path in self._iter_relevant_files():
            stat = file_path.stat()
            hasher.update(path_key.encode("utf-8"))
            hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("utf-8"))
            file_count += 1

        return f"{file_count}:{hasher.hexdigest()}"

    def _iter_relevant_files(self) -> list[tuple[str, Path]]:
        files = [
            (
                "config:"
                f"{config_path.relative_to(self.campaigns_dir).as_posix()}:"
                f"{self._fingerprint_path_key(config_path)}",
                config_path,
            )
            for config_path in self.campaigns_dir.glob("*/campaign.yaml")
        ]

        for config_path, content_root in self._repository_input_specs:
            config_key = config_path.relative_to(self.campaigns_dir).as_posix()
            files.extend(
                (
                    "content:"
                    f"{config_key}:"
                    f"{content_path.relative_to(content_root).as_posix()}:"
                    f"{self._fingerprint_path_key(content_path)}",
                    content_path,
                )
                for content_path in content_root.rglob("*.md")
            )
        return sorted(files, key=lambda item: item[0])

    def _fingerprint_path_key(self, path: Path) -> str:
        resolved_path = path.resolve()
        campaigns_root = self.campaigns_dir.resolve()
        try:
            relative_path = resolved_path.relative_to(campaigns_root)
        except ValueError:
            return f"external:{resolved_path.as_posix()}"
        return f"campaigns:{relative_path.as_posix()}"
