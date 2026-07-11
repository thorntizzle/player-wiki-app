from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import re
import time

from flask import Flask, jsonify

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.csrf import CSRF_SESSION_KEY, register_csrf
from player_wiki.db import get_db
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.sample_data import ASSIGNED_CHARACTER_SLUG


TOKEN_PATTERN = re.compile(r'name="_csrf_token" value="([A-Za-z0-9_-]+)"')
UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _enable_csrf(app) -> None:
    app.config["CSRF_ENABLED"] = True


def _rendered_token(client, path: str = "/account") -> str:
    response = client.get(path)
    assert response.status_code == 200
    tokens = TOKEN_PATTERN.findall(response.get_data(as_text=True))
    assert tokens
    assert len(set(tokens)) == 1
    return tokens[0]


def _register_method_probe(app) -> None:
    def method_probe():
        return jsonify({"ok": True, "method": request.method})

    from flask import request

    app.add_url_rule(
        "/api/v1/csrf-method-probe",
        endpoint="csrf_method_probe",
        view_func=method_probe,
        methods=list(UNSAFE_METHODS),
    )


def test_csrf_defaults_enabled_and_token_is_256_bit_session_state(app, client, sign_in, users):
    default_probe = Flask("csrf-default-probe")
    register_csrf(default_probe)
    assert default_probe.config["CSRF_ENABLED"] is True

    sign_in(users["party"]["email"], users["party"]["password"])
    token = _rendered_token(client)
    _enable_csrf(app)
    assert _rendered_token(client) == token
    assert len(token) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    with client.session_transaction() as browser_session:
        assert browser_session[CSRF_SESSION_KEY] == token


def test_csrf_rotates_on_sign_in_sign_out_invite_and_reset(app, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    _enable_csrf(app)
    first = _rendered_token(client)

    blocked_sign_out = client.post("/sign-out")
    assert blocked_sign_out.status_code == 400
    signed_out = client.post("/sign-out", data={"_csrf_token": first})
    assert signed_out.status_code == 302
    with client.session_transaction() as browser_session:
        assert CSRF_SESSION_KEY not in browser_session

    signed_in = client.post(
        "/sign-in",
        data={"email": users["party"]["email"], "password": users["party"]["password"]},
    )
    assert signed_in.status_code == 302
    assert signed_in.headers["Cache-Control"] == "private, no-store"
    assert "HttpOnly" in signed_in.headers["Set-Cookie"]
    assert "SameSite=Lax" in signed_in.headers["Set-Cookie"]
    second = _rendered_token(client)
    assert second != first

    with app.app_context():
        store = AuthStore()
        invited = store.create_user(
            "csrf-invite@example.com",
            "CSRF Invite",
            status="invited",
        )
        invite_token = store.issue_invite_token(invited.id, expires_in=timedelta(hours=1))

    invite = client.post(
        f"/invite/{invite_token}",
        data={
            "display_name": "CSRF Invite",
            "password": "invite-password",
            "password_confirmation": "invite-password",
        },
    )
    assert invite.status_code == 302
    third = _rendered_token(client)
    assert third not in {first, second}

    with app.app_context():
        store = AuthStore()
        reset_token = store.issue_password_reset_token(invited.id, expires_in=timedelta(hours=1))

    reset = client.post(
        f"/reset/{reset_token}",
        data={
            "password": "reset-password",
            "password_confirmation": "reset-password",
        },
    )
    assert reset.status_code == 302
    fourth = _rendered_token(client)
    assert fourth not in {first, second, third}


def test_csrf_rejects_all_untrusted_sources_before_touch_or_mutation(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["party"]["email"], users["party"]["password"])
    _enable_csrf(app)
    token = _rendered_token(client)
    app.config["SESSION_TOUCH_INTERVAL_SECONDS"] = 0

    with app.app_context():
        store = AuthStore()
        current_session = get_db().execute(
            "SELECT id, last_seen_at FROM sessions WHERE revoked_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert current_session is not None
        session_id = int(current_session["id"])
        last_seen_before = str(current_session["last_seen_at"])
        preferences_before = store.get_user_preferences(users["party"]["id"])
        audit_before = get_db().execute("SELECT COUNT(*) FROM auth_audit_log").fetchone()[0]

    second_client = app.test_client()
    app.config["CSRF_ENABLED"] = False
    second_client.post(
        "/sign-in",
        data={"email": users["owner"]["email"], "password": users["owner"]["password"]},
    )
    app.config["CSRF_ENABLED"] = True
    other_token = _rendered_token(second_client)

    failures = [
        client.post("/account/theme", data={"theme_key": "moonlit-ledger"}),
        client.post(
            "/account/theme",
            data={"theme_key": "moonlit-ledger", "_csrf_token": ""},
        ),
        client.post(
            "/account/theme",
            data={"theme_key": "moonlit-ledger", "_csrf_token": "malformed"},
        ),
        client.post(
            f"/account/theme?_csrf_token={token}",
            data={"theme_key": "moonlit-ledger"},
        ),
        client.post(
            "/account/theme",
            data={"theme_key": "moonlit-ledger", "_csrf_token": other_token},
        ),
    ]
    client.set_cookie("_csrf_token", token)
    failures.append(client.post("/account/theme", data={"theme_key": "moonlit-ledger"}))

    assert all(response.status_code == 400 for response in failures)
    assert all("Refresh the page and try again." in response.get_data(as_text=True) for response in failures)
    assert all("csrf_failed" not in response.get_data(as_text=True) for response in failures)

    with app.app_context():
        session_after = get_db().execute(
            "SELECT last_seen_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        assert session_after is not None
        assert str(session_after["last_seen_at"]) == last_seen_before
        preferences_after = AuthStore().get_user_preferences(users["party"]["id"])
        assert preferences_after.theme_key == preferences_before.theme_key
        assert get_db().execute("SELECT COUNT(*) FROM auth_audit_log").fetchone()[0] == audit_before

    valid = client.post(
        "/account/session-chat-order",
        data={"session_chat_order": "oldest_first", "_csrf_token": token},
    )
    assert valid.status_code == 302


def test_csrf_session_api_header_bearer_exemption_and_invalid_bearer_fallback(
    app,
    client,
    sign_in,
    users,
):
    _register_method_probe(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    _enable_csrf(app)
    token = _rendered_token(client)

    missing = client.post("/api/v1/csrf-method-probe", json={})
    assert missing.status_code == 400
    assert missing.get_json() == {
        "ok": False,
        "error": {
            "code": "csrf_failed",
            "message": "The request could not be verified.",
            "details": {},
        },
    }

    header_valid = client.post(
        "/api/v1/csrf-method-probe",
        json={},
        headers={"X-CSRF-Token": token},
    )
    assert header_valid.status_code == 200

    invalid_bearer = client.post(
        "/api/v1/csrf-method-probe",
        json={},
        headers={"Authorization": "Bearer invalid-session-mix"},
    )
    assert invalid_bearer.status_code == 400
    invalid_bearer_with_csrf = client.post(
        "/api/v1/csrf-method-probe",
        json={},
        headers={
            "Authorization": "Bearer invalid-session-mix",
            "X-CSRF-Token": token,
        },
    )
    assert invalid_bearer_with_csrf.status_code == 200

    bearer_token = issue_api_token(app, users["dm"]["email"], label="csrf-methods")
    bearer_client = app.test_client()
    for method in UNSAFE_METHODS:
        response = bearer_client.open(
            "/api/v1/csrf-method-probe",
            method=method,
            json={},
            headers=api_headers(bearer_token),
        )
        assert response.status_code == 200
        assert response.get_json()["method"] == method

    anonymous_client = app.test_client()
    anonymous_html = anonymous_client.post("/account/theme", data={"theme_key": "parchment"})
    assert anonymous_html.status_code == 302
    anonymous_api = anonymous_client.patch(
        "/api/v1/me/settings",
        json={},
        headers={"Authorization": "Bearer invalid"},
    )
    assert anonymous_api.status_code == 401
    assert anonymous_api.get_json()["error"]["code"] == "auth_required"


def test_view_as_mutation_denial_precedes_csrf(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    _enable_csrf(app)
    _rendered_token(client)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    response = client.post("/api/v1/campaigns/linden-pass/session/start", json={})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "view_as_read_only"


def test_authenticated_html_is_no_store_without_weakening_public_or_static_cache(
    app,
    client,
    sign_in,
    users,
):
    public = client.get("/campaigns/linden-pass")
    assert public.status_code == 200
    assert public.headers.get("Cache-Control") != "private, no-store"

    sign_in(users["party"]["email"], users["party"]["password"])
    _enable_csrf(app)
    account = client.get("/account")
    assert account.status_code == 200
    assert account.headers["Cache-Control"] == "private, no-store"

    app.config["APP_ENV"] = "production"
    static = client.get("/static/styles.css?v=csrf-cache-check")
    assert static.status_code == 200
    assert static.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_malicious_and_oversized_tokens_are_generic_bounded_and_not_logged(
    app,
    client,
    sign_in,
    users,
    caplog,
):
    sign_in(users["party"]["email"], users["party"]["password"])
    _enable_csrf(app)
    _rendered_token(client)
    sentinel = "CSRF-SENTINEL-DO-NOT-ECHO"

    started = time.perf_counter()
    response = client.post(
        "/account/theme",
        data={"theme_key": "parchment"},
        headers={"X-CSRF-Token": sentinel + ("x" * 100_000)},
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 400
    assert elapsed < 1.0
    assert sentinel not in response.get_data(as_text=True)
    assert sentinel not in caplog.text


def test_html_csrf_failure_is_fixed_and_discloses_no_identity_or_token_state(
    app,
    client,
    sign_in,
    users,
    caplog,
):
    display_name_sentinel = "CSRF-IDENTITY-SENTINEL"
    submitted_token_sentinel = "S" * 43
    malformed_session_sentinel = "CSRF-MALFORMED-SESSION-SENTINEL"
    with app.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (display_name_sentinel, users["party"]["id"]),
        )
        connection.commit()

    sign_in(users["party"]["email"], users["party"]["password"])
    _enable_csrf(app)
    established_token = _rendered_token(client)

    response = client.post(
        "/account/theme",
        data={
            "theme_key": "parchment",
            "_csrf_token": submitted_token_sentinel,
        },
    )
    expected = (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '  <head>\n'
        '    <meta charset="utf-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '    <title>Request Not Verified | Campaign Player Wiki</title>\n'
        '  </head>\n'
        '  <body>\n'
        '    <main>\n'
        '      <h1>That request could not be completed.</h1>\n'
        '      <p>Refresh the page and try again.</p>\n'
        '    </main>\n'
        '  </body>\n'
        '</html>'
    ).encode()
    assert response.status_code == 400
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.get_data() == expected
    assert response.get_data().count(b'name="_csrf_token"') == 0

    with client.session_transaction() as browser_session:
        browser_session[CSRF_SESSION_KEY] = malformed_session_sentinel
    malformed_response = client.post(
        "/account/theme",
        data={"theme_key": "parchment", "_csrf_token": submitted_token_sentinel},
    )
    assert malformed_response.status_code == 400
    assert malformed_response.get_data() == expected

    combined_responses = response.get_data() + malformed_response.get_data()
    for sentinel in (
        display_name_sentinel,
        submitted_token_sentinel,
        established_token,
        malformed_session_sentinel,
    ):
        assert sentinel.encode() not in combined_responses
        assert sentinel not in caplog.text


def test_all_protected_form_sources_explicitly_include_one_csrf_field():
    templates_dir = Path(__file__).resolve().parents[1] / "player_wiki" / "templates"
    protected: list[tuple[str, str]] = []
    exempt_with_field: list[str] = []
    unsafe_method = re.compile(
        r"\bmethod\s*=\s*[\"'](?:post|put|patch|delete)[\"']",
        re.IGNORECASE,
    )
    form = re.compile(r"<form\b[^>]*>(.*?)</form>", re.IGNORECASE | re.DOTALL)

    for path in sorted(templates_dir.glob("*.html")):
        for match in form.finditer(path.read_text(encoding="utf-8")):
            opening_tag = match.group(0).split(">", 1)[0]
            if not unsafe_method.search(opening_tag):
                assert "csrf_input()" not in match.group(1), path.name
                continue
            if path.name in {"sign_in.html", "invite_setup.html"}:
                if "csrf_input()" in match.group(1):
                    exempt_with_field.append(path.name)
                continue
            protected.append((path.name, match.group(1)))

    assert len(protected) == 157
    assert len({name for name, _ in protected}) == 44
    assert exempt_with_field == []
    assert all(body.count("csrf_input()") == 1 for _, body in protected)


def test_session_combat_and_character_formdata_posts_accept_rendered_token(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    _enable_csrf(app)
    token = _rendered_token(client)
    ajax_headers = {"X-Requested-With": "XMLHttpRequest"}

    session_response = client.post(
        "/campaigns/linden-pass/session/start",
        data={"_csrf_token": token},
        headers=ajax_headers,
    )
    assert session_response.status_code == 200

    combat_response = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        data={"_csrf_token": token},
        headers=ajax_headers,
    )
    assert combat_response.status_code == 200

    character = get_character(ASSIGNED_CHARACTER_SLUG)
    assert character is not None
    character_response = client.post(
        f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/session/vitals",
        data={
            "_csrf_token": token,
            "expected_revision": character.state_record.revision,
            "current_hp": character.state_record.state["vitals"]["current_hp"],
        },
        headers=ajax_headers,
    )
    assert character_response.status_code == 302
