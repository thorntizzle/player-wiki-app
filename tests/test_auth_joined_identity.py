from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
import re

import pytest
from flask import g, jsonify

from player_wiki import auth as auth_module, db as db_module
from player_wiki.auth_store import AuthStore, isoformat, utcnow
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics
from tests.test_ha_measurement_loading_date import loading_world


CAMPAIGN = "linden-pass"
CHARACTER = "arden-march"
PROBE = f"/campaigns/{CAMPAIGN}/_joined_identity_probe"


@pytest.fixture
def identity_probe(app):
    def probe():
        actor = auth_module.get_authenticated_user()
        effective = auth_module.get_current_user()
        preferences = auth_module.get_current_user_preferences()
        return jsonify(
            actor=actor.id if actor else None,
            effective=effective.id if effective else None,
            source=auth_module.get_current_auth_source(),
            preferences=asdict(preferences),
            theme=auth_module.get_current_theme().key,
            memberships=[(item.campaign_slug, item.role) for item in auth_module.get_current_memberships()],
            authenticated_memberships=[(item.campaign_slug, item.role) for item in g.authenticated_memberships],
            can_access=auth_module.can_access_campaign_scope(CAMPAIGN, "characters"),
            can_edit=auth_module.can_edit_character(CAMPAIGN, CHARACTER),
            session_id=getattr(g.current_session_record, "id", None),
            token_id=getattr(g.current_api_token_record, "id", None),
        )

    app.add_url_rule(PROBE, "joined_identity_probe", probe)
    app.add_url_rule("/_joined_identity_probe", "joined_identity_actor_probe", probe)
    return app


@pytest.fixture
def sql_statements(monkeypatch):
    statements = []
    original = db_module._InstrumentedConnection.execute

    def execute(connection, sql, parameters=()):
        statements.append(" ".join(sql.split()))
        return original(connection, sql, parameters)

    monkeypatch.setattr(db_module._InstrumentedConnection, "execute", execute)
    return statements


def _credential(app, client, user_id, source):
    with app.app_context():
        store = app.extensions["auth_store"]
        if source == "browser_session":
            raw, record = store.create_session(user_id, expires_in=timedelta(hours=1))
        else:
            raw, record = store.create_api_token(user_id, label="joined-identity-test")
    if source == "browser_session":
        with client.session_transaction() as session:
            session[auth_module.AUTH_SESSION_KEY] = raw
        return {}, record
    return {"Authorization": f"Bearer {raw}"}, record


def _auth_rows(app):
    with app.app_context():
        return {
            table: [tuple(row) for row in get_db().execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
            for table in ("users", "user_preferences", "sessions", "api_tokens", "campaign_memberships", "character_assignments")
        }


def _preferences(store, user_id, theme="moonlit"):
    store.set_user_theme_key(user_id, theme)
    store.set_user_session_chat_order(user_id, "oldest_first")


def _identity_statements(statements):
    return [sql for sql in statements if re.search(r"\b(?:FROM|JOIN) (?:users|user_preferences|sessions|api_tokens|campaign_memberships)\b", sql, re.I)]


@pytest.mark.parametrize("status", ["active", "invited", "disabled"])
@pytest.mark.parametrize("preferences_present", [False, True])
def test_joined_store_preserves_all_fields_defaults_and_read_only_cost(app, users, status, preferences_present):
    user_id = users["admin"]["id"]
    with app.app_context():
        store = AuthStore()
        get_db().execute(
            "UPDATE users SET status = ?, auth_version = 17, created_at = ?, updated_at = ? WHERE id = ?",
            (status, "2026-01-02T03:04:05+00:00", "2026-02-03T04:05:06+00:00", user_id),
        )
        if preferences_present:
            _preferences(store, user_id)
            get_db().execute("UPDATE user_preferences SET frontend_mode = 'gen2', updated_at = ? WHERE user_id = ?",
                             ("2026-03-04T05:06:07+00:00", user_id))
        else:
            get_db().execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
        get_db().commit()
        expected_user = store.get_user_by_id(user_id)
        expected_preferences = store.get_user_preferences(user_id)
        before = _auth_rows(app)
        reset_db_query_metrics()
        user, joined_row = store.get_user_with_preferences_row(user_id)
        preferences = store.map_joined_user_preferences(joined_row, user_id=user_id)
        metrics = get_db_query_metrics()
        assert user == expected_user
        assert asdict(preferences) | {"updated_at": expected_preferences.updated_at} == asdict(expected_preferences)
        if preferences_present:
            assert preferences.updated_at == expected_preferences.updated_at
            assert preferences.updated_at != user.updated_at
        else:
            assert expected_preferences.updated_at <= preferences.updated_at <= utcnow()
        assert metrics["query_count"] == 1
        assert metrics["write_count"] == metrics["commit_count"] == metrics["rollback_count"] == 0
        assert _auth_rows(app) == before


def test_joined_store_missing_account_keeps_absent_projection(app):
    with app.app_context():
        assert AuthStore().get_user_with_preferences_row(999999) == (None, None)


@pytest.mark.parametrize("source", ["browser_session", "api_token"])
@pytest.mark.parametrize("actor", ["owner", "dm", "admin"])
def test_accepted_request_uses_one_join_and_fresh_actor_preferences(identity_probe, client, users, sql_statements, source, actor):
    app = identity_probe
    user_id = users[actor]["id"]
    with app.app_context():
        _preferences(AuthStore(), user_id)
    headers, record = _credential(app, client, user_id, source)
    before = _auth_rows(app)
    sql_statements.clear()
    response = client.get(PROBE, headers=headers)
    payload = response.get_json()
    observed = _identity_statements(sql_statements)
    assert response.status_code == 200
    assert payload["actor"] == payload["effective"] == user_id
    assert payload["source"] == source
    assert payload["preferences"]["user_id"] == user_id
    assert payload["preferences"]["theme_key"] == payload["theme"] == "moonlit"
    assert payload["preferences"]["session_chat_order"] == "oldest_first"
    assert payload["preferences"]["frontend_mode"] == "flask"
    assert payload["session_id" if source == "browser_session" else "token_id"] == record.id
    assert payload["memberships"] == payload["authenticated_memberships"]
    joins = [sql for sql in observed if "LEFT JOIN user_preferences" in sql]
    assert len(joins) == 1
    assert "*" not in joins[0]
    assert not any(re.search(r"FROM user_preferences\b", sql) for sql in observed)
    assert len([sql for sql in observed if "FROM campaign_memberships" in sql]) == 1
    assert len([sql for sql in observed if "FROM sessions" in sql or "FROM api_tokens" in sql]) == 1
    assert len(observed) == 3
    assert _auth_rows(app) == before


@pytest.mark.parametrize("source", ["browser_session", "api_token"])
@pytest.mark.parametrize("status", ["invited", "disabled", "missing"])
def test_rejected_account_never_processes_preferences_and_revokes_credential(identity_probe, client, users, monkeypatch, source, status):
    app = identity_probe
    user_id = users["owner"]["id"]
    headers, record = _credential(app, client, user_id, source)
    store = app.extensions["auth_store"]
    if status == "missing":
        # A stale credential record can outlive its account read. Keep the real
        # account query and credential revocation, injecting only that boundary.
        method = "get_active_session" if source == "browser_session" else "get_active_api_token"
        monkeypatch.setattr(store, method, lambda _token: replace(record, user_id=999999))
    else:
        with app.app_context():
            _preferences(store, user_id)
            get_db().execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            get_db().execute("UPDATE user_preferences SET updated_at = 'invalid-timestamp' WHERE user_id = ?", (user_id,))
            get_db().commit()
    monkeypatch.setattr(store, "_map_user_preferences", lambda *args, **kwargs: pytest.fail("Rejected account processed preferences"))
    payload = client.get(PROBE, headers=headers).get_json()
    assert payload["actor"] is payload["effective"] is None
    assert payload["source"] == "anonymous"
    with app.app_context():
        table = "sessions" if source == "browser_session" else "api_tokens"
        assert get_db().execute(f"SELECT revoked_at FROM {table} WHERE id = ?", (record.id,)).fetchone()[0] is not None
    if source == "browser_session":
        with client.session_transaction() as session:
            assert auth_module.AUTH_SESSION_KEY not in session


@pytest.mark.parametrize("source", ["browser_session", "api_token"])
@pytest.mark.parametrize("state", ["expired", "revoked", "missing"])
def test_invalid_credential_stops_before_account_or_preferences(identity_probe, client, users, monkeypatch, source, state):
    app = identity_probe
    headers, record = _credential(app, client, users["owner"]["id"], source)
    table = "sessions" if source == "browser_session" else "api_tokens"
    with app.app_context():
        if state == "missing":
            get_db().execute(f"DELETE FROM {table} WHERE id = ?", (record.id,))
        else:
            column = "expires_at" if state == "expired" else "revoked_at"
            get_db().execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (isoformat(utcnow() - timedelta(hours=2)), record.id))
        get_db().commit()
    before = _auth_rows(app)
    monkeypatch.setattr(app.extensions["auth_store"], "get_user_with_preferences_row", lambda *_args: pytest.fail("Invalid credential loaded an account"))
    assert client.get(PROBE, headers=headers).get_json()["source"] == "anonymous"
    assert _auth_rows(app) == before


@pytest.mark.parametrize("source", ["browser_session", "api_token"])
@pytest.mark.parametrize("due", [False, True])
def test_credential_touch_preserves_existing_interval_and_durable_effect(identity_probe, client, users, source, due):
    app = identity_probe
    headers, record = _credential(app, client, users["owner"]["id"], source)
    table, column = ("sessions", "last_seen_at") if source == "browser_session" else ("api_tokens", "last_used_at")
    with app.app_context():
        if due:
            get_db().execute(f"UPDATE {table} SET {column} = ? WHERE id = ?",
                             (isoformat(utcnow() - timedelta(seconds=app.config["SESSION_TOUCH_INTERVAL_SECONDS"] + 60)), record.id))
            get_db().commit()
        before = tuple(get_db().execute(f"SELECT * FROM {table} WHERE id = ?", (record.id,)).fetchone())
    assert client.get(PROBE, headers=headers).get_json()["source"] == source
    with app.app_context():
        after = tuple(get_db().execute(f"SELECT * FROM {table} WHERE id = ?", (record.id,)).fetchone())
    assert (before != after) is due


def test_missing_preferences_default_read_and_anonymous_static_paths_do_not_write(identity_probe, client, users, monkeypatch):
    app = identity_probe
    with app.app_context():
        get_db().execute("DELETE FROM user_preferences")
        get_db().commit()
    before = _auth_rows(app)
    assert client.get(PROBE).get_json()["source"] == "anonymous"
    assert _auth_rows(app) == before
    headers, _ = _credential(app, client, users["owner"]["id"], "browser_session")
    before = _auth_rows(app)
    payload = client.get(PROBE, headers=headers).get_json()
    assert payload["preferences"]["theme_key"] == "parchment"
    assert payload["preferences"]["session_chat_order"] == "newest_first"
    assert payload["preferences"]["frontend_mode"] == "flask"
    assert _auth_rows(app) == before
    monkeypatch.setattr(app.extensions["auth_store"], "get_user_with_preferences_row", lambda *_args: pytest.fail("Static asset loaded identity"))
    assert client.get("/static/styles.css").status_code == 200
    assert _auth_rows(app) == before


@pytest.mark.parametrize("path", [PROBE, "/_joined_identity_probe"])
def test_view_as_preserves_actor_preferences_and_separate_effective_memberships(identity_probe, client, users, path):
    app = identity_probe
    with app.app_context():
        _preferences(AuthStore(), users["admin"]["id"], "moonlit")
        _preferences(AuthStore(), users["owner"]["id"], "parchment")
    _credential(app, client, users["admin"]["id"], "browser_session")
    with client.session_transaction() as session:
        session[auth_module.VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    payload = client.get(path).get_json()
    assert payload["actor"] == payload["preferences"]["user_id"] == users["admin"]["id"]
    assert payload["theme"] == "moonlit"
    assert payload["effective"] == users["owner" if path == PROBE else "admin"]["id"]
    assert payload["source"] == ("view_as" if path == PROBE else "browser_session")
    if path == PROBE:
        assert payload["memberships"] == [[CAMPAIGN, "player"]]
        assert payload["authenticated_memberships"] == []


@pytest.mark.parametrize("bearer_state", ["active", "disabled", "invalid"])
def test_bearer_precedence_and_browser_fallback_keep_correct_preferences(identity_probe, client, users, bearer_state):
    app = identity_probe
    with app.app_context():
        _preferences(AuthStore(), users["owner"]["id"], "parchment")
        _preferences(AuthStore(), users["admin"]["id"], "moonlit")
    _credential(app, client, users["admin"]["id"], "browser_session")
    headers, token = _credential(app, client, users["owner"]["id"], "api_token")
    if bearer_state == "disabled":
        with app.app_context():
            AuthStore().disable_user(users["owner"]["id"])
    elif bearer_state == "invalid":
        headers = {"Authorization": "Bearer does-not-exist"}
    payload = client.get(PROBE, headers=headers).get_json()
    expected = "owner" if bearer_state == "active" else "admin"
    assert payload["actor"] == payload["effective"] == payload["preferences"]["user_id"] == users[expected]["id"]
    assert payload["source"] == ("api_token" if bearer_state == "active" else "browser_session")
    assert payload["theme"] == ("parchment" if bearer_state == "active" else "moonlit")
    if bearer_state == "disabled":
        with app.app_context():
            assert AuthStore().get_api_token_by_id(token.id).revoked_at is not None


@pytest.mark.parametrize("source", ["browser_session", "api_token"])
@pytest.mark.parametrize("change", ["preferences", "membership", "visibility", "assignment", "disable", "revoke"])
def test_next_request_observes_auth_access_and_preference_changes(identity_probe, client, users, source, change):
    app = identity_probe
    user_id = users["owner"]["id"]
    with app.app_context():
        AuthStore().upsert_campaign_visibility_setting(CAMPAIGN, "characters", visibility="players", updated_by_user_id=users["dm"]["id"])
    headers, record = _credential(app, client, user_id, source)
    first = client.get(PROBE, headers=headers).get_json()
    assert first["actor"] == user_id and first["can_access"] and first["can_edit"]
    with app.app_context():
        store = AuthStore()
        if change == "preferences":
            _preferences(store, user_id)
        elif change == "membership":
            get_db().execute("DELETE FROM campaign_memberships WHERE user_id = ?", (user_id,))
            get_db().commit()
        elif change == "visibility":
            store.upsert_campaign_visibility_setting(CAMPAIGN, "characters", visibility="private", updated_by_user_id=users["dm"]["id"])
        elif change == "assignment":
            get_db().execute("DELETE FROM character_assignments WHERE user_id = ?", (user_id,))
            get_db().commit()
        elif change == "disable":
            store.disable_user(user_id)
        elif source == "browser_session":
            store.revoke_session(record.id)
        else:
            store.revoke_api_token(record.id)
    second = client.get(PROBE, headers=headers).get_json()
    if change == "preferences":
        assert second["theme"] == "moonlit" and second["preferences"]["session_chat_order"] == "oldest_first"
    elif change in {"membership", "visibility"}:
        assert second["can_access"] is False
    elif change == "assignment":
        assert second["can_edit"] is False
    else:
        assert second["actor"] is None and second["source"] == "anonymous"


def test_membership_failure_precedes_preference_mapping_and_request_identity_setup(identity_probe, client, users, monkeypatch):
    app = identity_probe
    _credential(app, client, users["owner"]["id"], "browser_session")
    store = app.extensions["auth_store"]
    def fail_memberships(*args, **kwargs):
        assert g.current_user is g.authenticated_user is None
        raise RuntimeError("membership failure")
    monkeypatch.setattr(store, "list_memberships_for_user", fail_memberships)
    monkeypatch.setattr(store, "_map_user_preferences", lambda *args, **kwargs: pytest.fail("Preferences processed before memberships"))
    with pytest.raises(RuntimeError, match="membership failure"):
        client.get(PROBE)


def test_frozen_player_unchanged_combat_keeps_exact_work_response_and_no_writes(loading_world, monkeypatch, sql_statements):
    app, users, _ = loading_world
    client = app.test_client()
    assert client.post("/sign-in", data={"email": users["owner"]["email"], "password": users["owner"]["password"]}).status_code == 302
    url = f"/campaigns/{CAMPAIGN}/combat/live-state"
    initial = client.get(url, headers={"X-Requested-With": "XMLHttpRequest"}).get_json()
    headers = {"X-Requested-With": "XMLHttpRequest", "X-Live-Revision": str(initial["live_revision"]), "X-Live-View-Token": initial["live_view_token"]}
    assert client.get(url, headers=headers).get_json()["changed"] is False
    before = _auth_rows(app)
    sql_statements.clear()
    response = client.get(url, headers=headers)
    assert response.get_json() == {"changed": False, "live_revision": initial["live_revision"], "live_view_token": initial["live_view_token"]}
    assert len(response.data) == 83
    assert response.headers["X-Live-Query-Count"] == "11"
    assert response.headers["X-Live-Write-Count"] == response.headers["X-Live-Commit-Count"] == "0"
    assert len([sql for sql in sql_statements if "LEFT JOIN user_preferences" in sql]) == 1
    assert not any(re.search(r"FROM user_preferences\b", sql) for sql in sql_statements)
    assert _auth_rows(app) == before
