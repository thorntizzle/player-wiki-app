from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import sqlite3
import threading

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import player_wiki.auth as auth_module
import player_wiki.auth_store as store_module
from player_wiki.auth_store import AuthStore, isoformat, utcnow
from player_wiki.db import get_db


@pytest.fixture(params=["reset", "invite"])
def transition(request, app):
    mode = request.param
    with app.app_context():
        store = AuthStore()
        user = store.create_user(
            "transition@example.com", "Original name",
            status="active" if mode == "reset" else "invited",
            password_hash=generate_password_hash("old-password"),
        )
        issue = store.issue_password_reset_token if mode == "reset" else store.issue_invite_token
        token = issue(user.id, expires_in=timedelta(hours=1))
        session_token, _ = store.create_session(user.id, expires_in=timedelta(hours=1))
        api_token, _ = store.create_api_token(user.id, label="Old credential")
    return {
        "mode": mode, "user": user, "token": token,
        "table": "password_reset_tokens" if mode == "reset" else "invite_tokens",
        "event": "password_reset_completed" if mode == "reset" else "user_activated",
        "session_token": session_token, "api_token": api_token,
    }


def _post(client, transition, password="chosen-password"):
    return client.post(f"/{transition['mode']}/{transition['token']}", data={
        "password": password, "password_confirmation": password,
        "display_name": "Chosen name",
    })


def _snapshot(app):
    # A different connection proves durable rows, not the request's pending view.
    with sqlite3.connect(app.config["DB_PATH"]) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            for table in ("users", "password_reset_tokens", "invite_tokens", "sessions",
                          "api_tokens", "auth_audit_log")
        }


def _assert_completed(app, transition, password="chosen-password", *, new_sessions=1):
    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_id(transition["user"].id)
        assert user.status == "active"
        assert user.auth_version == transition["user"].auth_version + 1
        assert check_password_hash(user.password_hash, password)
        assert user.display_name == ("Chosen name" if transition["mode"] == "invite" else "Original name")
        assert store.get_active_session(transition["session_token"]) is None
        assert store.get_active_api_token(transition["api_token"]) is None
        row = get_db().execute(f"SELECT used_at FROM {transition['table']} WHERE user_id = ?",
                               (user.id,)).fetchone()
        assert row["used_at"] is not None
        rows = get_db().execute("SELECT * FROM auth_audit_log WHERE event_type = ? AND target_user_id = ?",
                                (transition["event"], user.id)).fetchall()
        assert len(rows) == 1
        assert rows[0]["actor_user_id"] == user.id
        assert json.loads(rows[0]["metadata_json"]) == {
            "via": "reset_token" if transition["mode"] == "reset" else "invite"
        }
        assert password not in rows[0]["metadata_json"]
        assert transition["token"] not in rows[0]["metadata_json"]
        assert get_db().execute("SELECT COUNT(*) FROM sessions WHERE user_id = ? AND revoked_at IS NULL",
                                (user.id,)).fetchone()[0] == new_sessions


def test_success_is_atomic_and_reuse_is_inert(app, client, transition):
    assert _post(client, transition).status_code == 302
    _assert_completed(app, transition)
    before = _snapshot(app)
    assert _post(app.test_client(), transition, "losing-password").status_code == 400
    assert _snapshot(app) == before


def test_store_refuses_caller_transaction_without_committing_or_rolling_it_back(app, transition):
    before = _snapshot(app)
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE users SET display_name = 'Pending caller work' WHERE id = ?",
                           (transition["user"].id,))
        store = AuthStore()
        with pytest.raises(RuntimeError, match="own transaction"):
            if transition["mode"] == "reset":
                store.complete_password_reset(transition["token"], password_hash="prepared hash")
            else:
                store.complete_invite(transition["token"], display_name="Chosen name", password_hash="prepared hash")
        assert connection.in_transaction
        assert store.get_user_by_id(transition["user"].id).display_name == "Pending caller work"
        assert _snapshot(app) == before
        connection.rollback()


def test_hash_fault_leaves_token_and_all_credentials_unchanged(app, client, monkeypatch, transition):
    before = _snapshot(app)
    def fail_hash(password):
        assert not get_db().in_transaction
        raise RuntimeError("hash fault")
    monkeypatch.setattr(auth_module, "generate_password_hash", fail_hash)
    with pytest.raises(RuntimeError, match="hash fault"):
        _post(client, transition)
    assert _snapshot(app) == before


def test_transition_never_calls_independently_committing_helpers(app, client, monkeypatch, transition):
    def forbidden(*args, **kwargs):
        pytest.fail("An independently committing account helper was called")
    for name in ("set_password", "activate_user", "consume_password_reset", "consume_invite",
                 "revoke_all_user_sessions", "revoke_all_user_api_tokens", "write_audit_event"):
        monkeypatch.setattr(AuthStore, name, forbidden)
    assert _post(client, transition).status_code == 302
    _assert_completed(app, transition)


def test_two_connections_resolved_before_hash_have_one_winner(app, monkeypatch, transition):
    barrier = threading.Barrier(2)
    connection_ids = set()
    original_hash = auth_module.generate_password_hash

    def hash_at_barrier(password):
        connection_ids.add(id(get_db()))
        password_hash = original_hash(password)
        barrier.wait(timeout=10)
        return password_hash

    monkeypatch.setattr(auth_module, "generate_password_hash", hash_at_barrier)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [(password, pool.submit(_post, app.test_client(), transition, password))
                   for password in ("winner-one-password", "winner-two-password")]
        results = [(password, future.result(timeout=20)) for password, future in futures]
    assert len(connection_ids) == 2
    assert sorted(response.status_code for _, response in results) == [302, 400]
    winner = next(password for password, response in results if response.status_code == 302)
    loser = next(response for _, response in results if response.status_code == 400)
    assert b"This link is no longer valid." in loser.data
    assert transition["user"].email.encode() not in loser.data
    _assert_completed(app, transition, winner)


@pytest.mark.parametrize("change", ["expire", "replace", "disable", "delete", "wrong_status"])
def test_eligibility_changed_during_hash_loses_without_writes(app, client, monkeypatch, transition, change):
    original_hash = auth_module.generate_password_hash
    changed_snapshot = None

    def hash_then_change(password):
        nonlocal changed_snapshot
        result = original_hash(password)
        outer_connection = get_db()
        with app.app_context():
            assert get_db() is not outer_connection
            store = AuthStore()
            user_id = transition["user"].id
            if change == "expire":
                get_db().execute(f"UPDATE {transition['table']} SET expires_at = ? WHERE user_id = ?",
                                 (isoformat(utcnow() - timedelta(seconds=1)), user_id))
                get_db().commit()
            elif change == "replace":
                issue = store.issue_password_reset_token if transition["mode"] == "reset" else store.issue_invite_token
                issue(user_id, expires_in=timedelta(hours=1))
            elif change == "delete":
                store.delete_user(user_id)
            else:
                status = "disabled" if change == "disable" else ("invited" if transition["mode"] == "reset" else "active")
                get_db().execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
                get_db().commit()
        changed_snapshot = _snapshot(app)
        return result

    monkeypatch.setattr(auth_module, "generate_password_hash", hash_then_change)
    response = _post(client, transition)
    assert response.status_code == 400
    assert b"This link is no longer valid." in response.data
    assert transition["user"].email.encode() not in response.data
    assert _snapshot(app) == changed_snapshot


@pytest.mark.parametrize("change", ["expired", "missing_user", "unknown_token"])
def test_initial_invalid_link_is_non_disclosing_and_inert(app, client, transition, change):
    with sqlite3.connect(app.config["DB_PATH"]) as connection:
        if change == "expired":
            connection.execute(f"UPDATE {transition['table']} SET expires_at = ? WHERE user_id = ?",
                               (isoformat(utcnow() - timedelta(seconds=1)), transition["user"].id))
        elif change == "missing_user":
            # A deliberately orphaned synthetic token exercises the missing-user guard.
            connection.execute("DELETE FROM users WHERE id = ?", (transition["user"].id,))
        else:
            transition["token"] = "unknown"
    before = _snapshot(app)
    response = _post(client, transition)
    assert response.status_code == 400
    assert b"This link is no longer valid." in response.data
    assert transition["user"].email.encode() not in response.data
    assert _snapshot(app) == before


class _FaultConnection:
    def __init__(self, connection, stage, when):
        self.connection, self.stage, self.when = connection, stage, when
        self.triggered = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, parameters=()):
        normalized = " ".join(sql.upper().split())
        stage = next((name for prefix, name in (
            ("UPDATE PASSWORD_RESET_TOKENS", "consume"), ("UPDATE INVITE_TOKENS", "consume"),
            ("UPDATE USERS", "account"), ("UPDATE SESSIONS", "sessions"),
            ("UPDATE API_TOKENS", "api"), ("INSERT INTO AUTH_AUDIT_LOG", "audit"),
        ) if normalized.startswith(prefix)), None)
        fault = stage == self.stage and not self.triggered
        if fault and self.when == "before":
            self.triggered = True
            raise RuntimeError("injected durable fault")
        result = self.connection.execute(sql, parameters)
        if fault:
            self.triggered = True
            raise RuntimeError("injected durable fault")
        return result

    def commit(self):
        if self.stage == "commit" and not self.triggered:
            self.triggered = True
            raise RuntimeError("injected durable fault")
        return self.connection.commit()


@pytest.mark.parametrize("stage,when", [
    (stage, when) for stage in ("consume", "account", "sessions", "api", "audit")
    for when in ("before", "after")
] + [("commit", "before"), ("readback", "after"), ("mapping", "after"), ("missing_readback", "after")])
def test_every_precommit_fault_rolls_back_all_rows_and_credentials(app, client, monkeypatch, transition, stage, when):
    before = _snapshot(app)
    original_get_db = store_module.get_db
    wrappers = []

    def fault_db():
        connection = original_get_db()
        if not wrappers:
            wrappers.append(_FaultConnection(connection, stage, when))
        return wrappers[0]

    original_user = AuthStore.get_user_by_id
    original_map = AuthStore._map_user

    def fault_readback(self, user_id):
        user = original_user(self, user_id)
        if user and user.auth_version > transition["user"].auth_version:
            if stage == "missing_readback":
                return None
            raise RuntimeError("injected durable fault")
        return user

    def fault_map(self, row):
        if row and row["id"] == transition["user"].id and row["auth_version"] > transition["user"].auth_version:
            raise RuntimeError("injected durable fault")
        return original_map(self, row)

    with monkeypatch.context() as faults:
        faults.setattr(store_module, "get_db", fault_db)
        if stage in {"readback", "missing_readback"}:
            faults.setattr(AuthStore, "get_user_by_id", fault_readback)
        if stage == "mapping":
            faults.setattr(AuthStore, "_map_user", fault_map)
        with pytest.raises(RuntimeError, match="injected durable fault|Failed to read completed account transition"):
            _post(client, transition)
    assert _snapshot(app) == before
    with app.app_context():
        store = AuthStore()
        assert store.get_active_session(transition["session_token"]) is not None
        assert store.get_active_api_token(transition["api_token"]) is not None
        assert check_password_hash(store.get_user_by_id(transition["user"].id).password_hash, "old-password")
    assert client.get(f"/{transition['mode']}/{transition['token']}").status_code == 200


@pytest.mark.parametrize("stage", ["session_insert", "session_sql_before", "session_sql_after",
                                  "session_commit", "session_commit_after", "session_readback",
                                  "begin", "flash", "url", "redirect"])
def test_postcommit_fault_returns_recovery_and_new_password_can_sign_in(app, client, monkeypatch, transition, stage):
    import player_wiki.auth_invite_setup_routes as invite_routes
    import player_wiki.auth_password_reset_routes as reset_routes
    route = reset_routes if transition["mode"] == "reset" else invite_routes

    def fail(*args, **kwargs):
        raise RuntimeError("private exception chosen-password raw-secret")

    with monkeypatch.context() as faults:
        if stage == "session_insert":
            faults.setattr(AuthStore, "create_session", fail)
        elif stage == "session_readback":
            faults.setattr(AuthStore, "get_active_session", fail)
        elif stage in {"session_sql_before", "session_sql_after", "session_commit", "session_commit_after"}:
            original_get_db = store_module.get_db
            wrappers = []
            class SessionFaultConnection:
                def __init__(self, connection):
                    self.connection = connection
                    self.inserting_session = False
                def __getattr__(self, name):
                    return getattr(self.connection, name)
                def execute(self, sql, parameters=()):
                    if " ".join(sql.upper().split()).startswith("INSERT INTO SESSIONS"):
                        self.inserting_session = True
                        if stage == "session_sql_before":
                            fail()
                        result = self.connection.execute(sql, parameters)
                        if stage == "session_sql_after":
                            fail()
                        return result
                    return self.connection.execute(sql, parameters)
                def commit(self):
                    if self.inserting_session and stage == "session_commit":
                        fail()
                    self.connection.commit()
                    if self.inserting_session and stage == "session_commit_after":
                        fail()
            def session_fault_db():
                if not wrappers:
                    wrappers.append(SessionFaultConnection(original_get_db()))
                return wrappers[0]
            faults.setattr(store_module, "get_db", session_fault_db)
        elif stage == "begin":
            original_begin = auth_module.begin_browser_session
            def begin_then_fail(token):
                original_begin(token)
                fail()
            faults.setattr(auth_module, "begin_browser_session", begin_then_fail)
        else:
            faults.setattr(route, stage if stage != "url" else "url_for", fail)
        response = _post(client, transition)
    assert response.status_code == 503
    assert b"Sign in with your new password" in response.data
    assert b'href="/sign-in"' in response.data
    assert b"chosen-password" not in response.data
    assert b"raw-secret" not in response.data
    assert transition["token"].encode() not in response.data
    assert b'type="password"' not in response.data
    assert "no-store" in response.headers["Cache-Control"]
    assert "Content-Security-Policy" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    with client.session_transaction() as browser_session:
        assert auth_module.AUTH_SESSION_KEY not in browser_session
        assert "_flashes" not in browser_session
    uncommitted_session = stage in {"session_insert", "session_sql_before", "session_sql_after", "session_commit"}
    _assert_completed(app, transition, new_sessions=0 if uncommitted_session else 1)
    assert client.get(f"/{transition['mode']}/{transition['token']}").status_code == 400
    assert client.get("/account").status_code == 302
    assert client.post("/sign-in", data={"email": transition["user"].email,
                                        "password": "chosen-password"}).status_code == 302
    assert client.get("/account").status_code == 200
