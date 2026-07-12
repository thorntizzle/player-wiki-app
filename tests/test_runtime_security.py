from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db
from player_wiki.runtime_security import (
    PRODUCTION_SECRET_CONFIGURATION_MESSAGE,
    REDACTED_VALUE,
    ProductionSecretConfigurationError,
    sanitize_audit_metadata,
    sanitize_request_path,
    validate_production_secret,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _synthetic_exact_32_byte_secret() -> str:
    value = "SYNTHETIC-TEST-ONLY-" + ("x" * 11) + "!"
    assert len(value.encode("utf-8")) == 32
    return value


@pytest.mark.parametrize(
    "secret_key",
    (
        None,
        b"not-a-string",
        "",
        "   ",
        "x" * 31,
        " development-only-secret-key",
        "development-only-secret-key ",
        "development_only_secret_key",
        "C.H.A.N.G.E.M.E" + ("-" * 32),
        "replace_me",
        "PLACE-HOLDER",
        "default",
        "secret",
        "SECRET_KEY",
        "Your Secret Key",
        "PLAYER.WIKI.SECRET",
        "\ud800" * 32,
    ),
)
def test_production_secret_validator_rejects_unsafe_values_without_disclosure(
    secret_key,
) -> None:
    with pytest.raises(ProductionSecretConfigurationError) as exc_info:
        validate_production_secret("production", secret_key)

    assert str(exc_info.value) == PRODUCTION_SECRET_CONFIGURATION_MESSAGE
    assert repr(secret_key) not in str(exc_info.value)
    assert "31" not in str(exc_info.value)


@pytest.mark.parametrize(
    "normalized_placeholder",
    (
        "developmentonlysecretkey",
        "changeme",
        "replaceme",
        "placeholder",
        "default",
        "secret",
        "secretkey",
        "yoursecretkey",
        "playerwikisecret",
    ),
)
def test_production_secret_validator_rejects_all_normalized_placeholder_variants(
    normalized_placeholder: str,
) -> None:
    separator_inflated_variant = (
        ".".join(normalized_placeholder.upper()) + ("-" * 32)
    )
    assert len(separator_inflated_variant.encode("utf-8")) >= 32

    with pytest.raises(ProductionSecretConfigurationError):
        validate_production_secret("production", separator_inflated_variant)


@pytest.mark.parametrize(
    "secret_key",
    (
        _synthetic_exact_32_byte_secret(),
        "SYNTHETIC secret phrase with punctuation: !@#$ and suffix",
        "合成テスト専用🔐" + ("x" * 20),
        "secret-is-an-ordinary-substring-when-the-whole-value-is-not-a-placeholder",
    ),
)
def test_production_secret_validator_accepts_strong_utf8_values(secret_key: str) -> None:
    assert len(secret_key.encode("utf-8")) >= 32

    validate_production_secret("production", secret_key)


@pytest.mark.parametrize("app_env", (None, "", "development", "testing", "staging"))
def test_nonproduction_secret_validation_keeps_existing_default_compatibility(app_env) -> None:
    validate_production_secret(app_env, "development-only-secret-key")


def _minimal_subprocess_environment() -> dict[str, str]:
    allowed_names = (
        "COMSPEC",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    )
    return {name: os.environ[name] for name in allowed_names if name in os.environ}


def _run_production_app_probe(
    tmp_path: Path,
    *,
    secret_key: str | None,
    poison_storage: bool,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    database_path = tmp_path / "poison-storage-sentinel" / "wiki.sqlite3"
    campaigns_path = tmp_path / "poison-campaign-sentinel" / "campaigns"
    environment = _minimal_subprocess_environment()
    environment.update(
        {
            "PLAYER_WIKI_ENV": "production",
            "PLAYER_WIKI_DB_PATH": str(database_path),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(campaigns_path),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if secret_key is not None:
        environment["PLAYER_WIKI_SECRET_KEY"] = secret_key

    poison = (
        """
class PoisonedCampaignPageStore:
    def __init__(self, *args, **kwargs):
        raise AssertionError("POISONED_STORAGE_CONSTRUCTOR_REACHED")
app_module.CampaignPageStore = PoisonedCampaignPageStore
"""
        if poison_storage
        else ""
    )
    probe = f"""
import player_wiki.app as app_module
{poison}
app = app_module.create_app()
assert app.test_client().get("/livez").get_json() == {{"status": "ok"}}
print("PROBE_OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return result, database_path, campaigns_path


@pytest.mark.parametrize(
    ("case_name", "secret_key"),
    (
        ("missing", None),
        ("empty", ""),
        ("weak", "W" * 31),
        ("development_default", "development-only-secret-key"),
        ("placeholder", "C.H.A.N.G.E.M.E" + ("-" * 32)),
        ("surrounding_whitespace", " " + _synthetic_exact_32_byte_secret()),
    ),
)
def test_production_create_app_fails_before_storage_without_disclosing_secret(
    tmp_path: Path,
    case_name: str,
    secret_key: str | None,
) -> None:
    result, database_path, campaigns_path = _run_production_app_probe(
        tmp_path / case_name,
        secret_key=secret_key,
        poison_storage=True,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode != 0
    assert PRODUCTION_SECRET_CONFIGURATION_MESSAGE in combined_output
    assert "POISONED_STORAGE_CONSTRUCTOR_REACHED" not in combined_output
    if secret_key:
        assert secret_key not in combined_output
    assert not database_path.parent.exists()
    assert not campaigns_path.parent.exists()
    assert not list(tmp_path.rglob("*.migration.lock"))
    assert not list(tmp_path.rglob("migration-backups"))
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize(
    "secret_key",
    (
        _synthetic_exact_32_byte_secret(),
        "合成テスト専用🔐" + ("x" * 20),
    ),
)
def test_production_create_app_accepts_valid_secret_without_initializing_storage(
    tmp_path: Path,
    secret_key: str,
) -> None:
    result, database_path, campaigns_path = _run_production_app_probe(
        tmp_path,
        secret_key=secret_key,
        poison_storage=False,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert result.stdout.strip() == "PROBE_OK"
    assert secret_key not in combined_output
    assert not database_path.parent.exists()
    assert not campaigns_path.parent.exists()


def test_request_path_omits_queries_and_redacts_one_time_tokens() -> None:
    assert sanitize_request_path("/campaigns/linden-pass?access_token=query-secret") == (
        "/campaigns/linden-pass"
    )
    assert sanitize_request_path("/invite/invite-secret/tail-secret") == (
        "/invite/[REDACTED]"
    )
    assert sanitize_request_path("/RESET/reset-secret/extra") == (
        "/reset/[REDACTED]"
    )
    assert sanitize_request_path("/invite//double-slash-secret") == "/invite/[REDACTED]"
    assert sanitize_request_path("/reset/") == "/reset/[REDACTED]"
    assert sanitize_request_path(r"/invite\literal-separator-secret") == (
        "/invite/[REDACTED]"
    )
    assert sanitize_request_path("/reset%2Fencoded-separator-secret") == (
        "/reset/[REDACTED]"
    )
    assert sanitize_request_path("/invitee/not-a-token") == "/invitee/not-a-token"
    assert sanitize_request_path("/resetting/not-a-token") == "/resetting/not-a-token"


def test_audit_metadata_sanitizer_recurses_and_matches_keys_case_insensitively() -> None:
    metadata = {
        "ordinary": {
            "label": "kept",
            "items": [
                {"Authorization": "Bearer auth-secret", "count": 3},
                ("tuple-value", {"PaSsWoRd": "password-secret"}),
            ],
        },
        "Cookie": "session=cookie-secret",
        "SET-COOKIE": "session=set-cookie-secret",
        "passwd": "passwd-secret",
        "SECRET": "secret-value",
        "api_key": "underscore-secret",
        "API-KEY": "dash-secret",
        "access_token": "access-secret",
        "Refresh_Token": "refresh-secret",
        "bearer_token": "bearer-secret",
        "invite_url": "https://example.test/invite/invite-secret",
        "reset_url": "https://example.test/reset/reset-secret",
        "raw_token": "raw-secret",
        "ToKeN": "token-secret",
    }

    sanitized = sanitize_audit_metadata(metadata)

    assert sanitized["ordinary"] == {
        "label": "kept",
        "items": [
            {"Authorization": REDACTED_VALUE, "count": 3},
            ("tuple-value", {"PaSsWoRd": REDACTED_VALUE}),
        ],
    }
    for key in metadata.keys() - {"ordinary"}:
        assert sanitized[key] == REDACTED_VALUE

    serialized = repr(sanitized)
    for secret in (
        "auth-secret",
        "password-secret",
        "cookie-secret",
        "set-cookie-secret",
        "passwd-secret",
        "secret-value",
        "underscore-secret",
        "dash-secret",
        "access-secret",
        "refresh-secret",
        "bearer-secret",
        "invite-secret",
        "reset-secret",
        "raw-secret",
        "token-secret",
    ):
        assert secret not in serialized


def test_auth_store_redacts_nested_audit_metadata_before_storage(app) -> None:
    with app.app_context():
        store = AuthStore()
        store.write_audit_event(
            event_type="runtime_security_probe",
            metadata={
                "ordinary": {"label": "kept", "items": [{"count": 2}]},
                "Authorization": "Bearer stored-auth-secret",
                "nested": [
                    {
                        "Access_Token": "stored-access-secret",
                        "ordinary": "still-kept",
                    }
                ],
            },
        )
        event = next(
            item
            for item in store.list_recent_audit_events(limit=20)
            if item.event_type == "runtime_security_probe"
        )

    assert event.metadata == {
        "Authorization": REDACTED_VALUE,
        "nested": [
            {"Access_Token": REDACTED_VALUE, "ordinary": "still-kept"}
        ],
        "ordinary": {"items": [{"count": 2}], "label": "kept"},
    }
    assert "stored-auth-secret" not in repr(event.metadata)
    assert "stored-access-secret" not in repr(event.metadata)


class _UnstringableCredentialKey:
    def __str__(self) -> str:
        raise ValueError("credential key cannot be represented")


class _CountedCredentialKey:
    def __init__(self) -> None:
        self.conversion_count = 0

    def __str__(self) -> str:
        self.conversion_count += 1
        return "TOKEN"


def test_audit_metadata_key_normalization_is_safe_and_avoids_false_positives() -> None:
    counted_key = _CountedCredentialKey()
    metadata = {
        b"ToKeN": "bytes-token-secret",
        b"label": "bytes-label-kept",
        b"token\xff": "undecodable-key-secret",
        7: "integer-key-kept",
        False: "boolean-key-kept",
        None: "none-key-kept",
        "nested": [
            (
                {b"AUTHORIZATION": "nested-auth-secret"},
                {"token_count": 4, "secretary": "ordinary-title"},
            )
        ],
        "ordinary_value": "mentions password, token, and secret but remains ordinary",
        _UnstringableCredentialKey(): "unsupported-key-secret",
        counted_key: "counted-key-secret",
    }

    sanitized = sanitize_audit_metadata(metadata)

    assert sanitized["ToKeN"] == REDACTED_VALUE
    assert sanitized["label"] == "bytes-label-kept"
    undecodable_key = b"token\xff".decode("utf-8", errors="replace")
    assert sanitized[undecodable_key] == REDACTED_VALUE
    assert sanitized["7"] == "integer-key-kept"
    assert sanitized["False"] == "boolean-key-kept"
    assert sanitized["None"] == "none-key-kept"
    assert sanitized["nested"] == [
        (
            {"AUTHORIZATION": REDACTED_VALUE},
            {"token_count": 4, "secretary": "ordinary-title"},
        )
    ]
    assert sanitized["ordinary_value"] == (
        "mentions password, token, and secret but remains ordinary"
    )
    assert sanitized["[UNSUPPORTED_KEY]"] == REDACTED_VALUE
    assert sanitized["TOKEN"] == REDACTED_VALUE
    assert counted_key.conversion_count == 1

    serialized = repr(sanitized)
    for secret in (
        "bytes-token-secret",
        "undecodable-key-secret",
        "nested-auth-secret",
        "unsupported-key-secret",
        "counted-key-secret",
    ):
        assert secret not in serialized


def test_auth_store_redacts_nested_legacy_audit_metadata_on_read(app) -> None:
    raw_metadata = {
        "ordinary": {"label": "legacy-kept", "items": [{"count": 2}]},
        "nested": [
            {
                "Authorization": "Bearer legacy-auth-secret",
                "ordinary": "nested-kept",
            },
            {"RESET_URL": "https://example.test/reset/legacy-reset-secret"},
        ],
    }

    with app.app_context():
        connection = get_db()
        connection.execute(
            """
            INSERT INTO auth_audit_log (event_type, metadata_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                "legacy_runtime_security_probe",
                json.dumps(raw_metadata, sort_keys=True),
                "2026-07-10T00:00:00+00:00",
            ),
        )
        connection.commit()
        event = next(
            item
            for item in AuthStore().list_recent_audit_events(limit=20)
            if item.event_type == "legacy_runtime_security_probe"
        )

    assert event.metadata == {
        "nested": [
            {"Authorization": REDACTED_VALUE, "ordinary": "nested-kept"},
            {"RESET_URL": REDACTED_VALUE},
        ],
        "ordinary": {"items": [{"count": 2}], "label": "legacy-kept"},
    }
    assert "legacy-auth-secret" not in repr(event.metadata)
    assert "legacy-reset-secret" not in repr(event.metadata)
