from __future__ import annotations

import ast
import copy
from dataclasses import fields
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from flask import g
from werkzeug.datastructures import MultiDict

import player_wiki.auth as auth_module
import player_wiki.auth_account_theme_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "88d8ad80e0b4577946a342abbf85a932872133a7"
ROUTE_PATH = "/account/theme"
DEPENDENCY_ORDER = [
    "login_required",
    "get_current_user",
    "is_valid_theme_key",
    "render_account_settings_page",
    "get_theme_preset",
    "normalize_theme_key",
    "get_auth_store",
]


def _handler(app):
    return inspect.unwrap(app.view_functions["account_theme_update"])


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

    def visit_Call(self, node: ast.Call):
        node = self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "session_chat_order_labels"
            and not node.args
            and not node.keywords
        ):
            return ast.copy_location(
                ast.Name(id="SESSION_CHAT_ORDER_LABELS", ctx=ast.Load()),
                node,
            )
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    normalized = _DependencyQualifier().visit(copy.deepcopy(node))
    normalized.decorator_list = []
    return ast.dump(ast.fix_missing_locations(normalized), include_attributes=False)


def test_transport_has_exact_capture_forwarding_registration_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthAccountThemeRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse((source_root / "auth_account_theme_routes.py").read_text())
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "account_theme_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "account_theme_update"
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_account_theme_route"
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
    ) == "account_theme_update"
    assert [
        element.value
        for keyword in registration.keywords
        if keyword.arg == "methods"
        for element in keyword.value.elts
    ] == ["POST"]
    view_func = next(
        keyword.value for keyword in registration.keywords if keyword.arg == "view_func"
    )
    assert ast.unparse(view_func.func) == "dependencies.login_required"
    assert [ast.unparse(argument) for argument in view_func.args] == [
        "account_theme_update"
    ]

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
    assert (
        register_auth.body[8].value.func.id
        == "register_auth_account_settings_view_route"
    )
    assert register_auth.body[9].value.func.id == "register_auth_account_theme_route"
    assert (
        register_auth.body[10].value.func.id
        == "register_auth_account_session_chat_order_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[9])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthAccountThemeRouteDependencies"
    )
    assert [keyword.arg for keyword in dependency_call.keywords] == DEPENDENCY_ORDER
    assert [ast.unparse(keyword.value) for keyword in dependency_call.keywords] == [
        "login_required",
        "lambda: get_current_user()",
        "lambda value: is_valid_theme_key(value)",
        "render_account_settings_page",
        "lambda value: get_theme_preset(value)",
        "lambda value: normalize_theme_key(value)",
        "lambda: get_auth_store()",
    ]

    selected_theme = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "selected_theme"
            for target in node.targets
        )
    ).value
    assert ast.unparse(selected_theme) == (
        "dependencies.get_theme_preset("
        "dependencies.normalize_theme_key(requested_theme_key))"
    )


def test_moved_handler_keeps_canonical_ast_and_every_unrelated_auth_identity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "auth_account_theme_routes.py").read_text()
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
        if isinstance(node, ast.FunctionDef) and node.name == "account_theme_update"
    )
    original = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "account_theme_update"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)

    old_unrelated = [
        node for index, node in enumerate(old_register.body) if index not in {9, 10, 11, 12}
    ]
    new_unrelated = [
        node for index, node in enumerate(new_register.body) if index not in {9, 10, 11, 12}
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
        new_renderer, include_attributes=False
    )

    chat_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_account_session_chat_order_routes.py"
        ).read_text()
    )
    moved_chat = next(
        node
        for node in ast.walk(chat_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
    )
    old_chat = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
    )
    moved_chat_without_validation = copy.deepcopy(moved_chat)
    old_chat_without_validation = copy.deepcopy(old_chat)
    del moved_chat_without_validation.body[3]
    del old_chat_without_validation.body[3]
    assert _canonical_handler(moved_chat_without_validation) == _canonical_handler(
        old_chat_without_validation
    )
    assert moved_chat.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
        for node in ast.walk(new_tree)
    )


def test_route_preserves_endpoint_methods_order_redirect_cache_and_security_headers(
    app, client, sign_in, users
):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(
        rule for rule in app.url_map.iter_rules() if rule.endpoint == "account_theme_update"
    )
    assert rule.rule == ROUTE_PATH
    assert rule.methods == {"POST", "OPTIONS"}
    assert endpoints.index("account_settings_view") < endpoints.index(
        "account_theme_update"
    ) < endpoints.index("account_session_chat_order_update")

    anonymous = client.post(ROUTE_PATH, data={"theme_key": "moonlit"})
    assert anonymous.status_code == 302
    assert "/sign-in?next=/account/theme" in anonymous.headers["Location"]
    assert "Content-Security-Policy" in anonymous.headers

    sign_in(users["party"]["email"], users["party"]["password"])
    updated = client.post(ROUTE_PATH, data={"theme_key": "moonlit"})
    assert updated.status_code == 302
    assert updated.headers["Location"].endswith("/account")
    assert updated.headers["Cache-Control"] == "private, no-store"
    assert "Content-Security-Policy" in updated.headers

    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_forwarded_dependencies_preserve_raw_first_value_and_exact_event_order(
    app, monkeypatch
):
    events: list[tuple] = []
    user = SimpleNamespace(id=41)
    selected = SimpleNamespace(key="moonlit", label="Moonlit Ledger")

    class Store:
        def get_user_preferences(self, user_id):
            events.append(("current", user_id))
            return SimpleNamespace(theme_key="parchment")

        def set_user_theme_key(self, user_id, theme_key):
            events.append(("set", user_id, theme_key))
            return SimpleNamespace(theme_key=theme_key)

    monkeypatch.setattr(
        auth_module,
        "get_current_user",
        lambda: events.append(("user",)) or user,
    )
    monkeypatch.setattr(
        auth_module,
        "is_valid_theme_key",
        lambda value: events.append(("valid", value)) or True,
    )
    monkeypatch.setattr(
        auth_module,
        "normalize_theme_key",
        lambda value: events.append(("normalize", value)) or "moonlit",
    )
    monkeypatch.setattr(
        auth_module,
        "get_theme_preset",
        lambda value: events.append(("preset", value)) or selected,
    )
    monkeypatch.setattr(
        auth_module,
        "get_auth_store",
        lambda: events.append(("store",)) or Store(),
    )
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category)),
    )
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda endpoint: events.append(("url", endpoint)) or "/account",
    )
    monkeypatch.setattr(
        route_module,
        "redirect",
        lambda location: events.append(("redirect", location)) or "redirected",
    )

    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data=MultiDict(
            [("theme_key", "  MOONLIT  "), ("theme_key", "ember")]
        ),
    ):
        assert _handler(app)() == "redirected"
        assert g.current_theme is selected

    assert events == [
        ("user",),
        ("valid", "  MOONLIT  "),
        ("normalize", "  MOONLIT  "),
        ("preset", "moonlit"),
        ("store",),
        ("current", 41),
        ("set", 41, "moonlit"),
        ("flash", "Theme updated to Moonlit Ledger.", "success"),
        ("url", "account_settings_view"),
        ("redirect", "/account"),
    ]


def test_validation_noop_and_inner_missing_actor_preserve_exact_boundaries(
    app, monkeypatch
):
    monkeypatch.setattr(
        auth_module, "get_current_user", lambda: SimpleNamespace(id=7)
    )
    dependencies = _dependencies(app)
    original_renderer = dependencies.render_account_settings_page
    renders: list[int] = []
    object.__setattr__(
        dependencies,
        "render_account_settings_page",
        lambda *, status_code=200: renders.append(status_code) or ("invalid", status_code),
    )
    try:
        with app.test_request_context(ROUTE_PATH, method="POST", data={}):
            assert _handler(app)() == ("invalid", 400)
    finally:
        object.__setattr__(
            dependencies, "render_account_settings_page", original_renderer
        )
    assert renders == [400]

    events: list[tuple] = []
    user = SimpleNamespace(id=7)
    selected = SimpleNamespace(key="parchment", label="Parchment")
    store = SimpleNamespace(
        get_user_preferences=lambda user_id: events.append(("read", user_id))
        or SimpleNamespace(theme_key="parchment"),
        set_user_theme_key=lambda *args: events.append(("unexpected_write", *args)),
    )
    monkeypatch.setattr(auth_module, "get_current_user", lambda: user)
    monkeypatch.setattr(auth_module, "is_valid_theme_key", lambda value: True)
    monkeypatch.setattr(auth_module, "normalize_theme_key", lambda value: "parchment")
    monkeypatch.setattr(auth_module, "get_theme_preset", lambda value: selected)
    monkeypatch.setattr(auth_module, "get_auth_store", lambda: store)
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category)),
    )
    monkeypatch.setattr(route_module, "url_for", lambda endpoint: "/account")
    monkeypatch.setattr(route_module, "redirect", lambda location: "redirected")
    with app.test_request_context(
        ROUTE_PATH, method="POST", data={"theme_key": "parchment"}
    ):
        assert _handler(app)() == "redirected"
    assert events == [
        ("read", 7),
        ("flash", "Theme already set to Parchment.", "success"),
    ]

    monkeypatch.setattr(auth_module, "get_current_user", lambda: None)
    with app.test_request_context(
        ROUTE_PATH, method="POST", data={"theme_key": "parchment"}
    ):
        with pytest.raises(Exception) as error:
            _handler(app)()
    assert getattr(error.value, "code", None) == 401


def test_bearer_precedence_and_browser_view_as_keep_real_actor(
    app, client, sign_in, users
):
    token = issue_api_token(app, users["party"]["email"], label="p97-bearer")
    bearer = client.post(
        ROUTE_PATH,
        data={"theme_key": "moonlit"},
        headers=api_headers(token),
    )
    assert bearer.status_code == 302
    assert bearer.headers["Cache-Control"] == "private, no-store"

    browser = app.test_client()
    browser.post(
        "/sign-in",
        data={
            "email": users["admin"]["email"],
            "password": users["admin"]["password"],
        },
    )
    with browser.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert auth_module._path_supports_view_as(ROUTE_PATH) is False
    admin_update = browser.post(ROUTE_PATH, data={"theme_key": "verdant"})
    assert admin_update.status_code == 302

    with app.app_context():
        store = AuthStore()
        assert store.get_user_preferences(users["party"]["id"]).theme_key == "moonlit"
        assert store.get_user_preferences(users["admin"]["id"]).theme_key == "verdant"


def test_precommit_fault_has_zero_preference_write_and_postcommit_reload_fault_persists(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["party"]["email"], users["party"]["password"])
    user_id = users["party"]["id"]
    original_set = AuthStore.set_user_theme_key

    def fail_before_write(self, target_user_id, theme_key):
        raise RuntimeError("precommit fault")

    monkeypatch.setattr(AuthStore, "set_user_theme_key", fail_before_write)
    with pytest.raises(RuntimeError, match="precommit fault"):
        client.post(ROUTE_PATH, data={"theme_key": "moonlit"})
    with app.app_context():
        assert AuthStore().get_user_preferences(user_id).theme_key == "parchment"

    monkeypatch.setattr(AuthStore, "set_user_theme_key", original_set)
    original_get = AuthStore.get_user_preferences
    calls = 0

    def fail_internal_reload(self, target_user_id):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("postcommit reload fault")
        return original_get(self, target_user_id)

    monkeypatch.setattr(AuthStore, "get_user_preferences", fail_internal_reload)
    with pytest.raises(RuntimeError, match="postcommit reload fault"):
        client.post(ROUTE_PATH, data={"theme_key": "moonlit"})
    assert calls == 3
    with app.app_context():
        assert original_get(AuthStore(), user_id).theme_key == "moonlit"
