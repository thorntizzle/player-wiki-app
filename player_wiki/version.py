from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Mapping


DEFAULT_APP_VERSION = "0.0.0"


def read_app_version(base_dir: Path) -> str:
    override = os.getenv("PLAYER_WIKI_VERSION", "").strip()
    if override:
        return override

    version_path = base_dir / "VERSION"
    if not version_path.exists():
        return DEFAULT_APP_VERSION

    value = version_path.read_text(encoding="utf-8").strip()
    return value or DEFAULT_APP_VERSION


def _run_git_command(base_dir: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(base_dir), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    value = completed.stdout.strip()
    return value or None


def resolve_git_sha(base_dir: Path) -> str:
    override = os.getenv("PLAYER_WIKI_GIT_SHA", "").strip()
    if override:
        return override
    return _run_git_command(base_dir, "rev-parse", "--short=12", "HEAD") or "unknown"


def resolve_git_dirty(base_dir: Path) -> bool:
    override = os.getenv("PLAYER_WIKI_GIT_DIRTY", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False

    status_output = _run_git_command(base_dir, "status", "--short")
    if status_output is None:
        return False
    return bool(status_output)


def resolve_build_id(base_dir: Path) -> str:
    override = os.getenv("PLAYER_WIKI_BUILD_ID", "").strip()
    if override:
        return override

    git_sha = resolve_git_sha(base_dir)
    if git_sha == "unknown":
        return "unknown"
    if resolve_git_dirty(base_dir):
        return f"{git_sha}-dirty"
    return git_sha


def resolve_runtime() -> str:
    if os.getenv("FLY_APP_NAME", "").strip():
        return "fly"
    if os.getenv("PLAYER_WIKI_RUNTIME", "").strip():
        return os.getenv("PLAYER_WIKI_RUNTIME", "").strip()
    return "local"


def resolve_instance_name() -> str:
    explicit = os.getenv("PLAYER_WIKI_INSTANCE_NAME", "").strip()
    if explicit:
        return explicit

    fly_name = os.getenv("FLY_APP_NAME", "").strip()
    if fly_name:
        return fly_name

    return platform.node() or "unknown"


def build_app_metadata(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version": str(config["APP_VERSION"]),
        "build_id": str(config["APP_BUILD_ID"]),
        "git_sha": str(config["APP_GIT_SHA"]),
        "git_dirty": bool(config["APP_GIT_DIRTY"]),
        "runtime": str(config["APP_RUNTIME"]),
        "instance_name": str(config["APP_INSTANCE_NAME"]),
        "environment": str(config["APP_ENV"]),
        "base_url": str(config["BASE_URL"]),
    }
