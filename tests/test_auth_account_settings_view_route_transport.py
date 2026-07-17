from __future__ import annotations

import ast
import copy
from dataclasses import fields
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.auth as auth_module
import player_wiki.auth_account_settings_view_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "972607a6f9bfb767754b3e103b2b04471a38d5d5"
ROUTE_PATH = "/account"
DEPENDENCY_ORDER = [
    "login_required",
    "render_account_settings_page",
]


def _handler(app):
    return inspect.unwrap(app.view_functions["account_settings_view"])


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


def test_transport_has_exact_direct_dependencies_registration_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthAccountSettingsViewRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_account_settings_view_routes.py").read_text()
    )
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "account_settings_view"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "account_settings_view"
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_account_settings_view_route"
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
    ) == "account_settings_view"
    assert [
        element.value
        for keyword in registration.keywords
        if keyword.arg == "methods"
        for element in keyword.value.elts
    ] == ["GET"]
    view_func = next(
        keyword.value for keyword in registration.keywords if keyword.arg == "view_func"
    )
    assert isinstance(view_func, ast.Call)
    assert ast.unparse(view_func.func) == "dependencies.login_required"
    assert [ast.unparse(argument) for argument in view_func.args] == [
        "account_settings_view"
    ]

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
    assert register_auth.body[7].value.func.id == "register_auth_sign_out_route"
    assert (
        register_auth.body[8].value.func.id
        == "register_auth_account_settings_view_route"
    )
    assert register_auth.body[9].value.func.id == "register_auth_account_theme_route"

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[8])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthAccountSettingsViewRouteDependencies"
    )
    assert [keyword.arg for keyword in dependency_call.keywords] == DEPENDENCY_ORDER
    assert [ast.unparse(keyword.value) for keyword in dependency_call.keywords] == [
        "login_required",
        "render_account_settings_page",
    ]


def test_moved_handler_keeps_canonical_ast_and_every_unrelated_auth_identity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_account_settings_view_routes.py"
        ).read_text()
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
        if isinstance(node, ast.FunctionDef) and node.name == "account_settings_view"
    )
    original = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "account_settings_view"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)

    old_unrelated = [
        node
        for index, node in enumerate(old_register.body)
        if index not in {8, 9, 10, 11}
    ]
    new_unrelated = [
        node
        for index, node in enumerate(new_register.body)
        if index not in {8, 9, 10, 11}
    ]
    assert len(old_unrelated) == len(new_unrelated) == 10
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

    old_renderer = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "render_account_settings_page"
    )
    new_renderer = next(
        node
        for node in new_register.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "render_account_settings_page"
    )
    assert ast.dump(old_renderer, include_attributes=False) == ast.dump(
        new_renderer,
        include_attributes=False,
    )


def test_route_preserves_endpoint_methods_order_html_cache_and_security_headers(
    app, client, sign_in, users
):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(
        rule for rule in app.url_map.iter_rules() if rule.endpoint == "account_settings_view"
    )
    assert rule.rule == ROUTE_PATH
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert endpoints.index("sign_out") < endpoints.index(
        "account_settings_view"
    ) < endpoints.index("account_theme_update")

    anonymous = client.get(ROUTE_PATH, follow_redirects=False)
    assert anonymous.status_code == 302
    assert "/sign-in?next=/account" in anonymous.headers["Location"]
    assert "Content-Security-Policy" in anonymous.headers

    sign_in(users["party"]["email"], users["party"]["password"])
    response = client.get(ROUTE_PATH)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "Content-Security-Policy" in response.headers
    body = response.get_data(as_text=True)
    assert "Color theme" in body
    assert "Live session chat order" in body
    assert body.count('name="_csrf_token"') == 3

    head = client.head(ROUTE_PATH)
    assert head.status_code == 200
    assert head.get_data() == b""
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_direct_renderer_capture_preserves_evaluation_order(app, monkeypatch):
    events: list[tuple] = []
    theme = SimpleNamespace(key="late-theme")
    preferences = SimpleNamespace(session_chat_order="oldest_first")
    monkeypatch.setattr(
        auth_module,
        "list_theme_presets",
        lambda: events.append(("theme_presets",)) or ["themes"],
    )
    monkeypatch.setattr(
        auth_module,
        "get_current_theme",
        lambda: events.append(("current_theme",)) or theme,
    )
    monkeypatch.setattr(
        auth_module,
        "get_current_user_preferences",
        lambda: events.append(("preferences",)) or preferences,
    )
    monkeypatch.setattr(
        auth_module,
        "render_template",
        lambda template, **context: events.append(("render", template, context))
        or "rendered",
    )

    with app.test_request_context(ROUTE_PATH):
        assert _handler(app)() == "rendered"

    assert [event[0] for event in events] == [
        "theme_presets",
        "current_theme",
        "preferences",
        "render",
    ]
    assert events[-1] == (
        "render",
        "account_settings.html",
        {
            "theme_presets": ["themes"],
            "selected_theme_key": "late-theme",
            "session_chat_order_choices": auth_module.SESSION_CHAT_ORDER_CHOICES,
            "selected_session_chat_order": "oldest_first",
        },
    )


def test_bearer_precedence_and_browser_view_as_behavior_remain_global(
    app, client, sign_in, users
):
    token = issue_api_token(app, users["party"]["email"], label="p96-bearer")
    bearer = client.get(ROUTE_PATH, headers=api_headers(token))
    assert bearer.status_code == 200
    assert bearer.mimetype == "text/html"
    assert bearer.headers["Cache-Control"] == "private, no-store"
    assert bearer.get_data(as_text=True).count('name="_csrf_token" value=""') == 3

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert auth_module._path_supports_view_as(ROUTE_PATH) is False
    response = client.get(ROUTE_PATH)
    assert response.status_code == 200
    assert "Admin User" in response.get_data(as_text=True)


def test_identity_touch_precedes_renderer_fault_and_handler_has_no_persistence(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["party"]["email"], users["party"]["password"])
    app.config["SESSION_TOUCH_INTERVAL_SECONDS"] = 0
    events: list[str] = []
    original_get_store = auth_module.get_auth_store

    class StoreProxy:
        def __init__(self, store):
            self.store = store

        def __getattr__(self, name):
            return getattr(self.store, name)

        def touch_session(self, session_id):
            events.append("touch_session")
            return self.store.touch_session(session_id)

    monkeypatch.setattr(auth_module, "get_auth_store", lambda: StoreProxy(original_get_store()))
    dependencies = _dependencies(app)
    original_renderer = dependencies.render_account_settings_page

    def fail_renderer():
        events.append("renderer")
        raise RuntimeError("renderer fault")

    object.__setattr__(dependencies, "render_account_settings_page", fail_renderer)
    try:
        with pytest.raises(RuntimeError, match="renderer fault"):
            client.get(ROUTE_PATH)
    finally:
        object.__setattr__(
            dependencies,
            "render_account_settings_page",
            original_renderer,
        )
    assert events == ["touch_session", "renderer"]


def test_bearer_touch_precedes_renderer_fault_and_handler_has_no_persistence(
    app, client, users, monkeypatch
):
    token = issue_api_token(app, users["party"]["email"], label="p96-touch")
    app.config["SESSION_TOUCH_INTERVAL_SECONDS"] = 0
    events: list[str] = []
    original_get_store = auth_module.get_auth_store

    class StoreProxy:
        def __init__(self, store):
            self.store = store

        def __getattr__(self, name):
            return getattr(self.store, name)

        def touch_api_token(self, token_id):
            events.append("touch_api_token")
            return self.store.touch_api_token(token_id)

    monkeypatch.setattr(auth_module, "get_auth_store", lambda: StoreProxy(original_get_store()))
    dependencies = _dependencies(app)
    original_renderer = dependencies.render_account_settings_page

    def fail_renderer():
        events.append("renderer")
        raise RuntimeError("renderer fault")

    object.__setattr__(dependencies, "render_account_settings_page", fail_renderer)
    try:
        with pytest.raises(RuntimeError, match="renderer fault"):
            client.get(ROUTE_PATH, headers=api_headers(token))
    finally:
        object.__setattr__(
            dependencies,
            "render_account_settings_page",
            original_renderer,
        )
    assert events == ["touch_api_token", "renderer"]
