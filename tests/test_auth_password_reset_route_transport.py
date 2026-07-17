from __future__ import annotations

import ast
import copy
from dataclasses import fields
from datetime import timedelta
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash

import player_wiki.auth as auth_module
import player_wiki.auth_password_reset_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "e07f91d4f0acdf658700f390062ebb53a4b8de88"
DEPENDENCY_ORDER = [
    "get_auth_store",
    "validate_password_inputs",
    "generate_password_hash",
    "timedelta",
    "begin_browser_session",
]


def _handler(app):
    return inspect.unwrap(app.view_functions["password_reset"])


def _register_auth(tree: ast.Module) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_auth"
    )


class _DependencyQualifier(ast.NodeTransformer):
    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "dependencies"
        ):
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    normalized = _DependencyQualifier().visit(copy.deepcopy(node))
    normalized.decorator_list = []
    return ast.dump(ast.fix_missing_locations(normalized), include_attributes=False)


def _create_reset(app, *, email: str = "p100-reset@example.com"):
    with app.app_context():
        store = AuthStore()
        user = store.create_user(
            email,
            "P100 Reset",
            status="active",
            password_hash=generate_password_hash("old-password"),
        )
        token = store.issue_password_reset_token(
            user.id, expires_in=timedelta(hours=1)
        )
        return user, token


def test_transport_has_exact_forwarding_registration_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthPasswordResetRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse((source_root / "auth_password_reset_routes.py").read_text())
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "password_reset"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "password_reset"
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_password_reset_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registration = registrations[0]
    assert registration.args[0].value == "/reset/<token>"
    assert next(
        keyword.value.value
        for keyword in registration.keywords
        if keyword.arg == "endpoint"
    ) == "password_reset"
    assert [
        element.value
        for keyword in registration.keywords
        if keyword.arg == "methods"
        for element in keyword.value.elts
    ] == ["GET", "POST"]
    assert ast.unparse(
        next(
            keyword.value
            for keyword in registration.keywords
            if keyword.arg == "view_func"
        )
    ) == "password_reset"

    register_auth = _register_auth(auth_tree)
    assert len(register_auth.body) == 14
    assert sum(isinstance(node, ast.FunctionDef) for node in register_auth.body) == 7
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_auth)) == 8
    route_decorators = [
        decorator
        for node in ast.walk(register_auth)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "app"
    ]
    assert len(route_decorators) == 1
    assert register_auth.body[11].value.func.id == "register_auth_invite_setup_route"
    assert register_auth.body[12].value.func.id == "register_auth_password_reset_route"
    assert register_auth.body[13].name == "campaign_picker"

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[12])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthPasswordResetRouteDependencies"
    )
    assert [keyword.arg for keyword in dependency_call.keywords] == DEPENDENCY_ORDER
    assert [ast.unparse(keyword.value) for keyword in dependency_call.keywords] == [
        "lambda: get_auth_store()",
        "lambda password, confirmation: validate_password_inputs(password, confirmation)",
        "lambda password: generate_password_hash(password)",
        "lambda **kwargs: timedelta(**kwargs)",
        "lambda raw_token: begin_browser_session(raw_token)",
    ]
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ast.unparse(node.func) == "dependencies.get_auth_store"
        for node in ast.walk(handler)
    ) == 2


def test_moved_handler_keeps_canonical_ast_and_every_unrelated_auth_identity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "auth_password_reset_routes.py").read_text()
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/auth.py"], text=True
        )
    )
    new_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "auth.py").read_text())
    old_register = _register_auth(old_tree)
    new_register = _register_auth(new_tree)
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "password_reset"
    )
    original = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "password_reset"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)

    old_unrelated = [
        node for index, node in enumerate(old_register.body) if index != 12
    ]
    new_unrelated = [
        node for index, node in enumerate(new_register.body) if index != 12
    ]
    assert len(old_unrelated) == len(new_unrelated) == 13
    assert [ast.dump(node, include_attributes=False) for node in old_unrelated] == [
        ast.dump(node, include_attributes=False) for node in new_unrelated
    ]

    old_helpers = {
        node.name: ast.dump(node, include_attributes=False)
        for node in old_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "register_auth"
    }
    new_helpers = {
        node.name: ast.dump(node, include_attributes=False)
        for node in new_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "register_auth"
    }
    assert new_helpers == old_helpers


def test_route_preserves_methods_headers_token_lifecycle_and_validation_reuse(app, client):
    user, first_token = _create_reset(app)
    with app.app_context():
        store = AuthStore()
        second_token = store.issue_password_reset_token(
            user.id, expires_in=timedelta(hours=1)
        )
        rows = get_db().execute(
            "SELECT token_hash, used_at FROM password_reset_tokens WHERE user_id = ? ORDER BY id",
            (user.id,),
        ).fetchall()
        assert len(rows) == 2
        assert all(first_token not in row["token_hash"] for row in rows)
        assert rows[0]["used_at"] is not None
        assert rows[1]["used_at"] is None
        _, old_session = store.create_session(
            user.id, expires_in=timedelta(hours=1)
        )
        _, old_api_token = store.create_api_token(user.id, label="P100 old token")

    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == "password_reset")
    assert rule.rule == "/reset/<token>"
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert endpoints.index("invite_setup") < endpoints.index("password_reset") < endpoints.index(
        "campaign_picker"
    )

    assert client.get(f"/reset/{first_token}").status_code == 400
    assert client.get("/reset/not-a-token").status_code == 400
    valid = client.get(f"/reset/{second_token}")
    assert valid.status_code == 200
    assert valid.mimetype == "text/html"
    assert valid.headers["Cache-Control"] == "private, no-store"
    assert "Content-Security-Policy" in valid.headers
    head = client.head(f"/reset/{second_token}")
    assert head.status_code == 200
    assert head.get_data() == b""
    assert client.options(f"/reset/{second_token}").status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/reset/{second_token}").status_code == 405

    validation = client.post(
        f"/reset/{second_token}",
        data={"password": "short", "password_confirmation": "different"},
    )
    assert validation.status_code == 400
    assert client.get(f"/reset/{second_token}").status_code == 200

    app.config["CSRF_ENABLED"] = True
    updated = client.post(
        f"/reset/{second_token}",
        data={
            "password": "valid-reset-password",
            "password_confirmation": "valid-reset-password",
        },
    )
    assert updated.status_code == 302
    assert updated.headers["Location"].endswith("/")
    assert updated.headers["Cache-Control"] == "private, no-store"
    assert client.get(f"/reset/{second_token}").status_code == 400
    with app.app_context():
        changed = AuthStore().get_user_by_id(user.id)
        assert changed is not None
        assert check_password_hash(changed.password_hash, "valid-reset-password")
        old_session_row = get_db().execute(
            "SELECT revoked_at FROM sessions WHERE id = ?", (old_session.id,)
        ).fetchone()
        old_api_row = get_db().execute(
            "SELECT revoked_at FROM api_tokens WHERE id = ?", (old_api_token.id,)
        ).fetchone()
        assert old_session_row["revoked_at"] is not None
        assert old_api_row["revoked_at"] is not None
        assert get_db().execute(
            "SELECT COUNT(*) AS count FROM sessions WHERE user_id = ? AND revoked_at IS NULL",
            (user.id,),
        ).fetchone()["count"] == 1
        assert get_db().execute(
            "SELECT COUNT(*) AS count FROM auth_audit_log WHERE event_type = ? AND target_user_id = ?",
            ("password_reset_completed", user.id),
        ).fetchone()["count"] == 1


def test_expired_disabled_and_nonactive_tokens_are_invalid(app, client):
    with app.app_context():
        store = AuthStore()
        expired_user = store.create_user(
            "p100-expired@example.com",
            "Expired",
            status="active",
            password_hash=generate_password_hash("old-password"),
        )
        expired = store.issue_password_reset_token(
            expired_user.id, expires_in=timedelta(seconds=-1)
        )
        disabled_user = store.create_user(
            "p100-disabled@example.com",
            "Disabled",
            status="active",
            password_hash=generate_password_hash("old-password"),
        )
        disabled = store.issue_password_reset_token(
            disabled_user.id, expires_in=timedelta(hours=1)
        )
        store.disable_user(disabled_user.id)
        invited_user = store.create_user("p100-invited@example.com", "Invited")
        invited = store.issue_password_reset_token(
            invited_user.id, expires_in=timedelta(hours=1)
        )

    for token in (expired, disabled, invited):
        response = client.get(f"/reset/{token}")
        assert response.status_code == 400
        assert b"This link is no longer valid." in response.data


def test_all_forwarded_dependencies_preserve_form_and_success_event_order(app, monkeypatch):
    events: list[tuple] = []
    reset_record = SimpleNamespace(id=73)
    user = SimpleNamespace(id=41)

    class ResolveStore:
        def get_valid_password_reset(self, token):
            events.append(("resolve", token))
            return reset_record, user

    class MutationStore:
        def set_password(self, *args):
            events.append(("set_password", *args))

        def consume_password_reset(self, *args):
            events.append(("consume", *args))

        def revoke_all_user_sessions(self, *args):
            events.append(("revoke_sessions", *args))

        def revoke_all_user_api_tokens(self, *args):
            events.append(("revoke_api", *args))

        def write_audit_event(self, **kwargs):
            events.append(("audit", kwargs))

        def create_session(self, *args, **kwargs):
            events.append(("create_session", args, kwargs))
            return "raw-session", SimpleNamespace()

    stores = iter((ResolveStore(), MutationStore()))
    monkeypatch.setattr(
        auth_module, "get_auth_store", lambda: events.append(("store",)) or next(stores)
    )
    monkeypatch.setattr(
        auth_module,
        "validate_password_inputs",
        lambda password, confirmation: events.append(
            ("validate", password, confirmation)
        )
        or [],
    )
    monkeypatch.setattr(
        auth_module,
        "generate_password_hash",
        lambda password: events.append(("hash", password)) or "hash",
    )
    monkeypatch.setattr(
        auth_module,
        "timedelta",
        lambda **kwargs: events.append(("timedelta", kwargs)) or "ttl",
    )
    monkeypatch.setattr(
        auth_module,
        "begin_browser_session",
        lambda token: events.append(("begin", token)),
    )
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category)),
    )
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda endpoint: events.append(("url", endpoint)) or "/",
    )
    monkeypatch.setattr(
        route_module,
        "redirect",
        lambda location: events.append(("redirect", location)) or "redirected",
    )

    with app.test_request_context(
        "/reset/dynamic",
        method="POST",
        data=MultiDict(
            [
                ("password", "first-password"),
                ("password", "ignored-password"),
                ("password_confirmation", "first-confirmation"),
                ("password_confirmation", "ignored-confirmation"),
            ]
        ),
        headers={"User-Agent": "P100 Agent"},
        environ_base={"REMOTE_ADDR": "192.0.2.100"},
    ):
        assert _handler(app)("dynamic") == "redirected"

    assert [event[0] for event in events] == [
        "store",
        "resolve",
        "validate",
        "store",
        "hash",
        "set_password",
        "consume",
        "revoke_sessions",
        "revoke_api",
        "audit",
        "timedelta",
        "create_session",
        "begin",
        "flash",
        "url",
        "redirect",
    ]
    assert events[2] == ("validate", "first-password", "first-confirmation")
    assert events[5] == ("set_password", 41, "hash")
    assert events[9][1] == {
        "event_type": "password_reset_completed",
        "actor_user_id": 41,
        "target_user_id": 41,
        "metadata": {"via": "reset_token"},
    }
    assert events[11][2] == {
        "expires_in": "ttl",
        "user_agent": "P100 Agent",
        "ip_address": "192.0.2.100",
    }


@pytest.mark.parametrize(
    "fault_stage",
    [
        "set_password",
        "consume",
        "revoke_sessions",
        "revoke_api",
        "audit",
        "create_session",
        "begin",
        "flash",
        "url",
        "redirect",
    ],
)
def test_every_mutation_and_response_fault_keeps_exact_completed_prefix(
    app, monkeypatch, fault_stage
):
    events: list[str] = []
    reset_record = SimpleNamespace(id=73)
    user = SimpleNamespace(id=41)

    def stage(name, result=None):
        events.append(name)
        if fault_stage == name:
            raise RuntimeError(f"{name} fault")
        return result

    resolve_store = SimpleNamespace(
        get_valid_password_reset=lambda token: (reset_record, user)
    )
    mutation_store = SimpleNamespace(
        set_password=lambda *args: stage("set_password"),
        consume_password_reset=lambda *args: stage("consume"),
        revoke_all_user_sessions=lambda *args: stage("revoke_sessions"),
        revoke_all_user_api_tokens=lambda *args: stage("revoke_api"),
        write_audit_event=lambda **kwargs: stage("audit"),
        create_session=lambda *args, **kwargs: stage(
            "create_session", ("raw-session", SimpleNamespace())
        ),
    )
    stores = iter((resolve_store, mutation_store))
    monkeypatch.setattr(auth_module, "get_auth_store", lambda: next(stores))
    monkeypatch.setattr(auth_module, "validate_password_inputs", lambda *args: [])
    monkeypatch.setattr(auth_module, "generate_password_hash", lambda value: "hash")
    monkeypatch.setattr(auth_module, "timedelta", lambda **kwargs: "ttl")
    monkeypatch.setattr(auth_module, "begin_browser_session", lambda token: stage("begin"))
    monkeypatch.setattr(route_module, "flash", lambda *args: stage("flash"))
    monkeypatch.setattr(route_module, "url_for", lambda *args: stage("url", "/"))
    monkeypatch.setattr(route_module, "redirect", lambda *args: stage("redirect", "ok"))

    with app.test_request_context(
        "/reset/fault",
        method="POST",
        data={
            "password": "valid-password",
            "password_confirmation": "valid-password",
        },
    ):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("fault")

    order = [
        "set_password",
        "consume",
        "revoke_sessions",
        "revoke_api",
        "audit",
        "create_session",
        "begin",
        "flash",
        "url",
        "redirect",
    ]
    assert events == order[: order.index(fault_stage) + 1]


def test_set_password_internal_reload_fault_keeps_password_and_reusable_token(
    app, client, monkeypatch
):
    user, token = _create_reset(app, email="p100-reload@example.com")
    original_get_user = AuthStore.get_user_by_id
    calls = 0

    def fail_second_get(self, user_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("set password reload fault")
        return original_get_user(self, user_id)

    monkeypatch.setattr(AuthStore, "get_user_by_id", fail_second_get)
    with pytest.raises(RuntimeError, match="set password reload fault"):
        client.post(
            f"/reset/{token}",
            data={
                "password": "committed-password",
                "password_confirmation": "committed-password",
            },
        )
    monkeypatch.setattr(AuthStore, "get_user_by_id", original_get_user)

    with app.app_context():
        updated = AuthStore().get_user_by_id(user.id)
        assert updated is not None
        assert updated.auth_version == user.auth_version + 1
        assert check_password_hash(updated.password_hash, "committed-password")
        row = get_db().execute(
            "SELECT used_at FROM password_reset_tokens WHERE user_id = ?", (user.id,)
        ).fetchone()
        assert row["used_at"] is None
    assert client.get(f"/reset/{token}").status_code == 200


def test_committed_password_and_token_consumption_survive_later_faults(
    app, client, monkeypatch
):
    user, token = _create_reset(app, email="p100-consume-fault@example.com")
    original_consume = AuthStore.consume_password_reset

    def fail_consume(self, token_id):
        raise RuntimeError("consume fault")

    monkeypatch.setattr(AuthStore, "consume_password_reset", fail_consume)
    with pytest.raises(RuntimeError, match="consume fault"):
        client.post(
            f"/reset/{token}",
            data={
                "password": "partial-password",
                "password_confirmation": "partial-password",
            },
        )
    monkeypatch.setattr(AuthStore, "consume_password_reset", original_consume)
    with app.app_context():
        updated = AuthStore().get_user_by_id(user.id)
        assert updated is not None
        assert check_password_hash(updated.password_hash, "partial-password")
        row = get_db().execute(
            "SELECT used_at FROM password_reset_tokens WHERE user_id = ?", (user.id,)
        ).fetchone()
        assert row["used_at"] is None

    second_user, second_token = _create_reset(
        app, email="p100-after-consume@example.com"
    )
    original_revoke = AuthStore.revoke_all_user_sessions

    def fail_after_consume(self, user_id):
        raise RuntimeError("revoke fault")

    monkeypatch.setattr(AuthStore, "revoke_all_user_sessions", fail_after_consume)
    with pytest.raises(RuntimeError, match="revoke fault"):
        client.post(
            f"/reset/{second_token}",
            data={
                "password": "consumed-password",
                "password_confirmation": "consumed-password",
            },
        )
    monkeypatch.setattr(AuthStore, "revoke_all_user_sessions", original_revoke)
    with app.app_context():
        row = get_db().execute(
            "SELECT used_at FROM password_reset_tokens WHERE user_id = ?",
            (second_user.id,),
        ).fetchone()
        assert row["used_at"] is not None


def test_create_session_internal_reload_fault_keeps_all_prior_commits_and_session_row(
    app, client, monkeypatch
):
    user, token = _create_reset(app, email="p100-session-reload@example.com")
    monkeypatch.setattr(
        AuthStore,
        "get_active_session",
        lambda self, raw_token: (_ for _ in ()).throw(
            RuntimeError("session reload fault")
        ),
    )
    with pytest.raises(RuntimeError, match="session reload fault"):
        client.post(
            f"/reset/{token}",
            data={
                "password": "session-password",
                "password_confirmation": "session-password",
            },
        )

    with app.app_context():
        row = get_db().execute(
            "SELECT used_at FROM password_reset_tokens WHERE user_id = ?", (user.id,)
        ).fetchone()
        assert row["used_at"] is not None
        assert get_db().execute(
            "SELECT COUNT(*) AS count FROM sessions WHERE user_id = ? AND revoked_at IS NULL",
            (user.id,),
        ).fetchone()["count"] == 1
        assert get_db().execute(
            "SELECT COUNT(*) AS count FROM auth_audit_log WHERE event_type = ? AND target_user_id = ?",
            ("password_reset_completed", user.id),
        ).fetchone()["count"] == 1


def test_browser_view_as_and_bearer_csrf_bypass_do_not_change_token_target(
    app, client, sign_in, users
):
    target, token = _create_reset(app, email="p100-view-as@example.com")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    app.config["CSRF_ENABLED"] = True
    assert auth_module._path_supports_view_as(f"/reset/{token}") is False
    response = client.post(
        f"/reset/{token}",
        data={
            "password": "token-target-password",
            "password_confirmation": "token-target-password",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        store = AuthStore()
        reset_target = store.get_user_by_id(target.id)
        admin = store.get_user_by_id(users["admin"]["id"])
        party = store.get_user_by_id(users["party"]["id"])
        assert reset_target is not None
        assert check_password_hash(reset_target.password_hash, "token-target-password")
        assert admin is not None and not check_password_hash(
            admin.password_hash, "token-target-password"
        )
        assert party is not None and not check_password_hash(
            party.password_hash, "token-target-password"
        )

    bearer_target, bearer_reset = _create_reset(
        app, email="p100-bearer-target@example.com"
    )
    with app.app_context():
        bearer_token, _ = AuthStore().create_api_token(
            users["admin"]["id"], label="P100 bearer"
        )
    bearer_response = client.post(
        f"/reset/{bearer_reset}",
        headers={"Authorization": f"Bearer {bearer_token}"},
        data={
            "password": "bearer-target-password",
            "password_confirmation": "bearer-target-password",
        },
    )
    assert bearer_response.status_code == 302
    with app.app_context():
        changed = AuthStore().get_user_by_id(bearer_target.id)
        assert changed is not None
        assert check_password_hash(changed.password_hash, "bearer-target-password")
