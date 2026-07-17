from __future__ import annotations

import ast
import copy
from dataclasses import fields
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from flask import g, session as flask_session

import player_wiki.auth as auth_module
import player_wiki.auth_sign_out_routes as route_module
from player_wiki.auth import AUTH_SESSION_KEY, VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.csrf import CSRF_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "922299d0fd36e0321b4d33d7a8cd89898d835725"
ROUTE_PATH = "/sign-out"
DEPENDENCY_ORDER = [
    "login_required",
    "get_current_session_record",
    "get_auth_store",
]


def _handler(app):
    return inspect.unwrap(app.view_functions["sign_out"])


def _dependencies(app):
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"].cell_contents


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


def test_transport_has_exact_capture_late_binding_registration_and_source_shape() -> None:
    assert [field.name for field in fields(route_module.AuthSignOutRouteDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse((source_root / "auth_sign_out_routes.py").read_text())
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "sign_out"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "sign_out"
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "register_auth_sign_out_route"
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
    assert next(
        keyword.value.value
        for keyword in registration.keywords
        if keyword.arg == "endpoint"
    ) == "sign_out"
    assert [
        element.value
        for keyword in registration.keywords
        if keyword.arg == "methods"
        for element in keyword.value.elts
    ] == ["POST"]
    view_func = next(
        keyword.value
        for keyword in registration.keywords
        if keyword.arg == "view_func"
    )
    assert isinstance(view_func, ast.Call)
    assert isinstance(view_func.func, ast.Attribute)
    assert ast.unparse(view_func.func) == "dependencies.login_required"
    assert [ast.unparse(argument) for argument in view_func.args] == ["sign_out"]

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
    assert register_auth.body[6].value.func.id == "register_auth_sign_in_routes"
    assert register_auth.body[7].value.func.id == "register_auth_sign_out_route"
    assert register_auth.body[8].value.func.id == "register_auth_account_settings_view_route"
    assert register_auth.body[9].value.func.id == "register_auth_account_theme_route"

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[7])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthSignOutRouteDependencies"
    )
    assert [keyword.arg for keyword in dependency_call.keywords] == DEPENDENCY_ORDER
    assert isinstance(dependency_call.keywords[0].value, ast.Name)
    assert dependency_call.keywords[0].value.id == "login_required"
    assert all(
        isinstance(keyword.value, ast.Lambda)
        for keyword in dependency_call.keywords[1:]
    )


def test_moved_handler_keeps_canonical_ast_and_every_unrelated_auth_identity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "auth_sign_out_routes.py").read_text()
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/auth.py"],
            text=True,
        )
    )
    new_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "auth.py").read_text())
    old_register = _register_auth(old_tree)
    new_register = _register_auth(new_tree)
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "sign_out"
    )
    original = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "sign_out"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)

    old_unrelated = [
        node
        for index, node in enumerate(old_register.body)
        if index not in {7, 8, 9, 10, 11}
    ]
    new_unrelated = [
        node
        for index, node in enumerate(new_register.body)
        if index not in {7, 8, 9, 10, 11}
    ]
    assert len(old_unrelated) == len(new_unrelated) == 9
    assert [ast.dump(node, include_attributes=False) for node in old_unrelated] == [
        ast.dump(node, include_attributes=False) for node in new_unrelated
    ]

    old_module_helpers = {
        node.name: ast.dump(node, include_attributes=False)
        for node in old_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "register_auth"
    }
    new_module_helpers = {
        node.name: ast.dump(node, include_attributes=False)
        for node in new_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "register_auth"
    }
    assert new_module_helpers == old_module_helpers


def test_route_preserves_endpoint_methods_order_no_store_and_security_headers(app, client):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == "sign_out")
    assert rule.rule == ROUTE_PATH
    assert rule.methods == {"POST", "OPTIONS"}
    assert endpoints.index("sign_in") < endpoints.index("sign_in_submit") < endpoints.index(
        "sign_out"
    ) < endpoints.index("account_settings_view")

    anonymous = client.post(ROUTE_PATH)
    assert anonymous.status_code == 302
    assert "/sign-in?next=/sign-out" in anonymous.headers["Location"]
    assert "Cache-Control" not in anonymous.headers
    assert "Content-Security-Policy" in anonymous.headers
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_bearer_precedence_does_not_revoke_token_or_backing_browser_session(
    app, client, sign_in, users
):
    sign_in(users["party"]["email"], users["party"]["password"])
    with client.session_transaction() as browser_session:
        raw_browser_token = browser_session[AUTH_SESSION_KEY]
        browser_session[VIEW_AS_SESSION_KEY] = users["admin"]["id"]
    api_token = issue_api_token(app, users["party"]["email"], label="p95-bearer")

    response = client.post(ROUTE_PATH, headers=api_headers(api_token))
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sign-in")
    with client.session_transaction() as browser_session:
        assert AUTH_SESSION_KEY not in browser_session
        assert VIEW_AS_SESSION_KEY not in browser_session
    with app.app_context():
        assert AuthStore().get_active_session(raw_browser_token) is not None
        assert AuthStore().get_active_api_token(api_token) is not None


def test_browser_session_view_as_csrf_revoke_clear_and_redirect_order(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        raw_token = browser_session[AUTH_SESSION_KEY]
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
        browser_session[CSRF_SESSION_KEY] = "p95-csrf"

    blocked = client.post(ROUTE_PATH)
    assert blocked.status_code == 400
    with app.app_context():
        assert AuthStore().get_active_session(raw_token) is not None

    events: list[tuple] = []
    original_get_record = auth_module.get_current_session_record
    original_get_store = auth_module.get_auth_store

    def get_record():
        record = original_get_record()
        events.append(("record", record.id if record is not None else None))
        return record

    class StoreProxy:
        def __init__(self, store):
            self.store = store

        def revoke_session(self, session_id):
            events.append(("revoke", session_id))
            return self.store.revoke_session(session_id)

    def get_store():
        events.append(("store",))
        return StoreProxy(original_get_store())

    monkeypatch.setattr(auth_module, "get_current_session_record", get_record)
    monkeypatch.setattr(auth_module, "get_auth_store", get_store)
    class SessionProxy:
        def clear(self):
            events.append(("clear",))
            flask_session.clear()

    monkeypatch.setattr(route_module, "session", SessionProxy())
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category)),
    )
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda endpoint: events.append(("url_for", endpoint)) or "/sign-in",
    )
    monkeypatch.setattr(
        route_module,
        "redirect",
        lambda target: events.append(("redirect", target)) or "redirect-result",
    )

    with app.app_context():
        session_record = AuthStore().get_active_session(raw_token)
        assert session_record is not None
    with app.test_request_context(ROUTE_PATH, method="POST"):
        g.current_session_record = session_record
        flask_session[AUTH_SESSION_KEY] = raw_token
        flask_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
        flask_session[CSRF_SESSION_KEY] = "p95-csrf"
        assert _handler(app)() == "redirect-result"
        remaining_session = dict(flask_session)
    assert [event[0] for event in events] == [
        "record",
        "store",
        "revoke",
        "clear",
        "flash",
        "url_for",
        "redirect",
    ]
    assert events[4] == ("flash", "Signed out.", "success")
    assert events[5] == ("url_for", "sign_in")
    assert remaining_session == {}
    with app.app_context():
        assert AuthStore().get_active_session(raw_token) is None


@pytest.mark.parametrize("fault_stage", ["store", "revoke", "clear", "flash", "url_for", "redirect"])
def test_fault_boundaries_preserve_revoke_and_stop_later_effects(
    app, monkeypatch, fault_stage
):
    events: list[str] = []

    class Store:
        def revoke_session(self, session_id):
            events.append("revoke")
            if fault_stage == "revoke":
                raise RuntimeError("revoke fault")

    class Session:
        def clear(self):
            events.append("clear")
            if fault_stage == "clear":
                raise RuntimeError("clear fault")

    monkeypatch.setattr(
        auth_module,
        "get_current_session_record",
        lambda: events.append("record") or SimpleNamespace(id=41),
    )

    def get_store():
        events.append("store")
        if fault_stage == "store":
            raise RuntimeError("store fault")
        return Store()

    monkeypatch.setattr(auth_module, "get_auth_store", get_store)
    monkeypatch.setattr(route_module, "session", Session())

    def flash(message, category):
        events.append("flash")
        if fault_stage == "flash":
            raise RuntimeError("flash fault")

    def url_for(endpoint):
        events.append("url_for")
        if fault_stage == "url_for":
            raise RuntimeError("url_for fault")
        return "/sign-in"

    def redirect(target):
        events.append("redirect")
        if fault_stage == "redirect":
            raise RuntimeError("redirect fault")
        return "redirect-result"

    monkeypatch.setattr(route_module, "flash", flash)
    monkeypatch.setattr(route_module, "url_for", url_for)
    monkeypatch.setattr(route_module, "redirect", redirect)
    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        _handler(app)()

    ordered = ["record", "store", "revoke", "clear", "flash", "url_for", "redirect"]
    assert events == ordered[: ordered.index(fault_stage) + 1]


def test_revoke_commit_survives_later_flash_fault(app, client, sign_in, users, monkeypatch):
    sign_in(users["party"]["email"], users["party"]["password"])
    with client.session_transaction() as browser_session:
        raw_token = browser_session[AUTH_SESSION_KEY]

    monkeypatch.setattr(
        route_module,
        "flash",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("flash fault")),
    )
    with pytest.raises(RuntimeError, match="flash fault"):
        client.post(ROUTE_PATH)
    with app.app_context():
        assert AuthStore().get_active_session(raw_token) is None
