from __future__ import annotations

import re
from typing import Any


REDACTED_VALUE = "[REDACTED]"

MINIMUM_PRODUCTION_SECRET_BYTES = 32
PRODUCTION_SECRET_CONFIGURATION_MESSAGE = (
    "Production SECRET_KEY must be at least 32 UTF-8 bytes and must not be a "
    "default or placeholder value."
)

_SECRET_PLACEHOLDER_SEPARATOR_RE = re.compile(r"[\s._-]+")
_SECRET_PLACEHOLDERS = frozenset(
    {
        "developmentonlysecretkey",
        "changeme",
        "replaceme",
        "placeholder",
        "default",
        "secret",
        "secretkey",
        "yoursecretkey",
        "playerwikisecret",
    }
)

SENSITIVE_METADATA_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "password",
        "passwd",
        "secret",
        "api_key",
        "api-key",
        "access_token",
        "refresh_token",
        "bearer_token",
        "invite_url",
        "reset_url",
        "raw_token",
        "token",
    }
)

_ONE_TIME_TOKEN_PATH_RE = re.compile(
    r"^/(invite|reset)(?=$|[/\\]|%(?:2f|5c))",
    re.IGNORECASE,
)


class ProductionSecretConfigurationError(RuntimeError):
    """Raised when production session signing configuration is unsafe."""


def _normalized_placeholder_candidate(value: str) -> str:
    return _SECRET_PLACEHOLDER_SEPARATOR_RE.sub("", value).casefold()


def validate_production_secret(app_env: Any, secret_key: Any) -> None:
    """Fail closed when production session signing configuration is unsafe."""

    if str(app_env or "").strip().casefold() != "production":
        return

    invalid = not isinstance(secret_key, str)
    if not invalid:
        invalid = not secret_key or secret_key != secret_key.strip()
    if not invalid:
        try:
            encoded_secret = secret_key.encode("utf-8")
        except UnicodeEncodeError:
            invalid = True
        else:
            invalid = len(encoded_secret) < MINIMUM_PRODUCTION_SECRET_BYTES
    if not invalid:
        invalid = _normalized_placeholder_candidate(secret_key) in _SECRET_PLACEHOLDERS

    if invalid:
        raise ProductionSecretConfigurationError(
            PRODUCTION_SECRET_CONFIGURATION_MESSAGE
        )


def sanitize_request_path(path: str | None) -> str:
    """Return a query-free request path with one-time URL tokens redacted."""

    query_free_path = str(path or "").split("?", 1)[0]
    match = _ONE_TIME_TOKEN_PATH_RE.match(query_free_path)
    if match is None:
        return query_free_path
    route_prefix = match.group(1).lower()
    return f"/{route_prefix}/{REDACTED_VALUE}"


def _normalize_metadata_key(key: Any) -> tuple[str, bool]:
    if isinstance(key, str):
        return key, False
    if isinstance(key, bytes):
        try:
            return key.decode("utf-8"), False
        except UnicodeDecodeError:
            return key.decode("utf-8", errors="replace"), True
    try:
        return str(key), False
    except Exception:
        return "[UNSUPPORTED_KEY]", True


def sanitize_audit_metadata(value: Any) -> Any:
    """Recursively redact credential-shaped audit metadata values."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text, key_is_uncertain = _normalize_metadata_key(key)
            if key_is_uncertain or key_text.strip().casefold() in SENSITIVE_METADATA_KEYS:
                sanitized[key_text] = REDACTED_VALUE
            else:
                sanitized[key_text] = sanitize_audit_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_audit_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_audit_metadata(item) for item in value)
    return value
