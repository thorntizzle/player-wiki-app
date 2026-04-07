from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from .version import read_app_version, resolve_build_id, resolve_git_dirty, resolve_git_sha, resolve_instance_name, resolve_runtime


def env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


def env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return float(raw_value)


def build_default_base_url(host: str, port: int, scheme: str) -> str:
    visible_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if default_port:
        return f"{scheme}://{visible_host}"
    return f"{scheme}://{visible_host}:{port}"


class Config:
    APP_ENV = os.getenv("PLAYER_WIKI_ENV", "development").strip().lower()
    DEBUG = APP_ENV == "development"
    TESTING = APP_ENV == "testing"
    LIVE_DIAGNOSTICS = env_bool("PLAYER_WIKI_LIVE_DIAGNOSTICS", APP_ENV != "production")
    LIVE_SLOW_LOG_THRESHOLD_MS = env_float(
        "PLAYER_WIKI_LIVE_SLOW_LOG_THRESHOLD_MS",
        250.0 if APP_ENV == "production" else 0.0,
    )
    COMBAT_PLAYER_SNAPSHOT_SYNC_INTERVAL_SECONDS = env_float(
        "PLAYER_WIKI_COMBAT_PLAYER_SNAPSHOT_SYNC_INTERVAL_SECONDS",
        3.0 if APP_ENV == "production" else 0.0,
    )

    BASE_DIR = Path(__file__).resolve().parent.parent
    APP_VERSION = read_app_version(BASE_DIR)
    APP_GIT_SHA = resolve_git_sha(BASE_DIR)
    APP_GIT_DIRTY = resolve_git_dirty(BASE_DIR)
    APP_BUILD_ID = resolve_build_id(BASE_DIR)
    APP_RUNTIME = resolve_runtime()
    APP_INSTANCE_NAME = resolve_instance_name()
    CAMPAIGNS_DIR = Path(os.getenv("PLAYER_WIKI_CAMPAIGNS_DIR", str(BASE_DIR / "campaigns")))
    LOCAL_DATA_DIR = BASE_DIR / ".local"

    SECRET_KEY = os.getenv("PLAYER_WIKI_SECRET_KEY", "development-only-secret-key")
    HOST = os.getenv("PLAYER_WIKI_HOST", "127.0.0.1")
    PORT = env_int("PLAYER_WIKI_PORT", 5000)

    RELOAD_CONTENT = env_bool("PLAYER_WIKI_RELOAD_CONTENT", APP_ENV != "production")
    CONTENT_SCAN_INTERVAL_SECONDS = env_int(
        "PLAYER_WIKI_CONTENT_SCAN_INTERVAL_SECONDS",
        1 if RELOAD_CONTENT else 30,
    )

    TRUST_PROXY = env_bool("PLAYER_WIKI_TRUST_PROXY", False)
    PROXY_FIX_HOPS = env_int("PLAYER_WIKI_PROXY_FIX_HOPS", 1)

    PREFERRED_URL_SCHEME = os.getenv(
        "PLAYER_WIKI_PREFERRED_URL_SCHEME",
        "https" if TRUST_PROXY else "http",
    )
    BASE_URL = os.getenv("PLAYER_WIKI_BASE_URL") or build_default_base_url(
        HOST,
        PORT,
        PREFERRED_URL_SCHEME,
    )

    DB_PATH = Path(
        os.getenv(
            "PLAYER_WIKI_DB_PATH",
            str(LOCAL_DATA_DIR / "player_wiki.sqlite3"),
        )
    )

    SESSION_COOKIE_NAME = os.getenv("PLAYER_WIKI_SESSION_COOKIE_NAME", "player_wiki_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("PLAYER_WIKI_SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = env_bool("PLAYER_WIKI_SESSION_COOKIE_SECURE", APP_ENV == "production")
    SESSION_REFRESH_EACH_REQUEST = False

    SESSION_TTL_HOURS = env_int("PLAYER_WIKI_SESSION_TTL_HOURS", 24 * 14)
    SESSION_TOUCH_INTERVAL_SECONDS = env_int(
        "PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS",
        300,
    )
    INVITE_TTL_HOURS = env_int("PLAYER_WIKI_INVITE_TTL_HOURS", 24 * 3)
    RESET_TTL_HOURS = env_int("PLAYER_WIKI_RESET_TTL_HOURS", 24)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=SESSION_TTL_HOURS)
