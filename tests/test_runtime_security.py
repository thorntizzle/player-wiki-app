from __future__ import annotations

import json

from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db
from player_wiki.runtime_security import (
    REDACTED_VALUE,
    sanitize_audit_metadata,
    sanitize_request_path,
)


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
