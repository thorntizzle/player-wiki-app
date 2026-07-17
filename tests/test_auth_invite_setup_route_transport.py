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

import player_wiki.auth as auth_module
import player_wiki.auth_invite_setup_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "6defa25cb4c4c1aa70b498b528069e6732391989"
DEPENDENCY_ORDER = [
    "get_auth_store",
    "validate_password_inputs",
    "generate_password_hash",
    "timedelta",
    "begin_browser_session",
]


def _handler(app):
    return inspect.unwrap(app.view_functions["invite_setup"])


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


def _create_invite(app, *, email: str = "p99-invite@example.com"):
    with app.app_context():
        store = AuthStore()
        user = store.create_user(email, "P99 Invite", status="invited")
        token = store.issue_invite_token(user.id, expires_in=timedelta(hours=1))
        return user, token


def test_transport_has_exact_forwarding_registration_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthInviteSetupRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse((source_root / "auth_invite_setup_routes.py").read_text())
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "invite_setup"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "invite_setup"
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_invite_setup_route"
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
    assert registration.args[0].value == "/invite/<token>"
    assert next(
        keyword.value.value
        for keyword in registration.keywords
        if keyword.arg == "endpoint"
    ) == "invite_setup"
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
    ) == "invite_setup"

    register_auth = _register_auth(auth_tree)
    assert len(register_auth.body) == 14
    assert sum(isinstance(node, ast.FunctionDef) for node in register_auth.body) == 8
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_auth)) == 9
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
    assert len(route_decorators) == 2
    assert (
        register_auth.body[10].value.func.id
        == "register_auth_account_session_chat_order_route"
    )
    assert register_auth.body[11].value.func.id == "register_auth_invite_setup_route"
    assert register_auth.body[12].name == "password_reset"

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[11])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthInviteSetupRouteDependencies"
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
        (PROJECT_ROOT / "player_wiki" / "auth_invite_setup_routes.py").read_text()
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
        if isinstance(node, ast.FunctionDef) and node.name == "invite_setup"
    )
    original = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "invite_setup"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)

    old_unrelated = [
        node for index, node in enumerate(old_register.body) if index != 11
    ]
    new_unrelated = [
        node for index, node in enumerate(new_register.body) if index != 11
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
    old_reset = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "password_reset"
    )
    new_reset = next(
        node
        for node in new_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "password_reset"
    )
    assert ast.dump(new_reset, include_attributes=False) == ast.dump(
        old_reset, include_attributes=False
    )


def test_route_preserves_methods_order_public_html_headers_and_token_lifecycle(app, client):
    user, first_token = _create_invite(app)
    with app.app_context():
        second_token = AuthStore().issue_invite_token(
            user.id, expires_in=timedelta(hours=1)
        )
        rows = get_db().execute(
            "SELECT token_hash, used_at FROM invite_tokens WHERE user_id = ? ORDER BY id",
            (user.id,),
        ).fetchall()
        assert len(rows) == 2
        assert all(first_token not in row["token_hash"] for row in rows)
        assert rows[0]["used_at"] is not None
        assert rows[1]["used_at"] is None

    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == "invite_setup")
    assert rule.rule == "/invite/<token>"
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert endpoints.index("account_session_chat_order_update") < endpoints.index(
        "invite_setup"
    ) < endpoints.index("password_reset")

    assert client.get(f"/invite/{first_token}").status_code == 400
    valid = client.get(f"/invite/{second_token}")
    assert valid.status_code == 200
    assert valid.mimetype == "text/html"
    assert valid.headers["Cache-Control"] == "private, no-store"
    assert "Content-Security-Policy" in valid.headers
    head = client.head(f"/invite/{second_token}")
    assert head.status_code == 200
    assert head.get_data() == b""
    assert client.options(f"/invite/{second_token}").status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/invite/{second_token}").status_code == 405

    validation = client.post(
        f"/invite/{second_token}",
        data={"display_name": "", "password": "short", "password_confirmation": "different"},
    )
    assert validation.status_code == 400
    assert client.get(f"/invite/{second_token}").status_code == 200

    app.config["CSRF_ENABLED"] = True
    activated = client.post(
        f"/invite/{second_token}",
        data={
            "display_name": "Activated Invite",
            "password": "valid-invite-password",
            "password_confirmation": "valid-invite-password",
        },
    )
    assert activated.status_code == 302
    assert activated.headers["Location"].endswith("/")
    assert activated.headers["Cache-Control"] == "private, no-store"
    assert client.get(f"/invite/{second_token}").status_code == 400
    with app.app_context():
        activated_user = AuthStore().get_user_by_id(user.id)
        assert activated_user is not None
        assert activated_user.status == "active"
        assert activated_user.display_name == "Activated Invite"


def test_all_forwarded_dependencies_preserve_form_and_success_event_order(app, monkeypatch):
    events: list[tuple] = []
    invite_record = SimpleNamespace(id=73)
    user = SimpleNamespace(id=41, status="invited", display_name="Existing")

    class ResolveStore:
        def get_valid_invite(self, token):
            events.append(("resolve", token))
            return invite_record, user

    class MutationStore:
        def activate_user(self, *args, **kwargs):
            events.append(("activate", args, kwargs))

        def consume_invite(self, *args):
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
        "/invite/dynamic",
        method="POST",
        data=MultiDict(
            [
                ("display_name", "  First Name  "),
                ("display_name", "Ignored"),
                ("password", "first-password"),
                ("password", "ignored-password"),
                ("password_confirmation", "first-confirmation"),
                ("password_confirmation", "ignored-confirmation"),
            ]
        ),
        headers={"User-Agent": "P99 Agent"},
        environ_base={"REMOTE_ADDR": "192.0.2.99"},
    ):
        assert _handler(app)("dynamic") == "redirected"

    assert [event[0] for event in events] == [
        "store",
        "resolve",
        "validate",
        "hash",
        "store",
        "activate",
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
    assert events[5] == (
        "activate",
        (41,),
        {"display_name": "First Name", "password_hash": "hash"},
    )
    assert events[11][2] == {
        "expires_in": "ttl",
        "user_agent": "P99 Agent",
        "ip_address": "192.0.2.99",
    }


@pytest.mark.parametrize(
    "fault_stage",
    [
        "activate",
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
    invite_record = SimpleNamespace(id=73)
    user = SimpleNamespace(id=41, status="invited", display_name="Existing")

    def stage(name, result=None):
        events.append(name)
        if fault_stage == name:
            raise RuntimeError(f"{name} fault")
        return result

    resolve_store = SimpleNamespace(
        get_valid_invite=lambda token: (invite_record, user)
    )
    mutation_store = SimpleNamespace(
        activate_user=lambda *args, **kwargs: stage("activate"),
        consume_invite=lambda *args: stage("consume"),
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
        "/invite/fault",
        method="POST",
        data={
            "display_name": "Name",
            "password": "valid-password",
            "password_confirmation": "valid-password",
        },
    ):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("fault")

    order = [
        "activate",
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


def test_committed_activation_and_invite_consumption_survive_later_faults(
    app, client, monkeypatch
):
    user, token = _create_invite(app, email="p99-partial@example.com")
    original_consume = AuthStore.consume_invite

    def fail_consume(self, token_id):
        raise RuntimeError("consume fault")

    monkeypatch.setattr(AuthStore, "consume_invite", fail_consume)
    with pytest.raises(RuntimeError, match="consume fault"):
        client.post(
            f"/invite/{token}",
            data={
                "display_name": "Partially Active",
                "password": "partial-password",
                "password_confirmation": "partial-password",
            },
        )
    with app.app_context():
        updated = AuthStore().get_user_by_id(user.id)
        assert updated is not None
        assert updated.status == "active"
        row = get_db().execute(
            "SELECT used_at FROM invite_tokens WHERE user_id = ?", (user.id,)
        ).fetchone()
        assert row["used_at"] is None

    monkeypatch.setattr(AuthStore, "consume_invite", original_consume)
    second_user, second_token = _create_invite(app, email="p99-consumed@example.com")
    original_revoke = AuthStore.revoke_all_user_sessions

    def fail_after_consume(self, user_id):
        raise RuntimeError("revoke fault")

    monkeypatch.setattr(AuthStore, "revoke_all_user_sessions", fail_after_consume)
    with pytest.raises(RuntimeError, match="revoke fault"):
        client.post(
            f"/invite/{second_token}",
            data={
                "display_name": "Consumed Invite",
                "password": "consumed-password",
                "password_confirmation": "consumed-password",
            },
        )
    monkeypatch.setattr(AuthStore, "revoke_all_user_sessions", original_revoke)
    with app.app_context():
        row = get_db().execute(
            "SELECT used_at FROM invite_tokens WHERE user_id = ?", (second_user.id,)
        ).fetchone()
        assert row["used_at"] is not None


def test_view_as_and_csrf_exemption_do_not_change_token_target(app, client, sign_in, users):
    invited, token = _create_invite(app, email="p99-view-as@example.com")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    app.config["CSRF_ENABLED"] = True
    assert auth_module._path_supports_view_as(f"/invite/{token}") is False
    response = client.post(
        f"/invite/{token}",
        data={
            "display_name": "Token Target",
            "password": "target-password",
            "password_confirmation": "target-password",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        store = AuthStore()
        target = store.get_user_by_id(invited.id)
        admin = store.get_user_by_id(users["admin"]["id"])
        party = store.get_user_by_id(users["party"]["id"])
        assert target is not None and target.display_name == "Token Target"
        assert admin is not None and admin.display_name == "Admin User"
        assert party is not None and party.display_name == "Party Player"
