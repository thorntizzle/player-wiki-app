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
import player_wiki.auth_account_session_chat_order_routes as route_module
import player_wiki.auth_store as auth_store_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "caa0c42325d3030311c8fae4f6d145bb6bdf1cb1"
ROUTE_PATH = "/account/session-chat-order"
DEPENDENCY_ORDER = [
    "login_required",
    "get_current_user",
    "is_valid_session_chat_order",
    "render_account_settings_page",
    "normalize_session_chat_order",
    "get_auth_store",
    "session_chat_order_labels",
]


def _handler(app):
    return inspect.unwrap(app.view_functions["account_session_chat_order_update"])


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


def test_transport_has_exact_forwarding_registration_and_source_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.AuthAccountSessionChatOrderRouteDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_account_session_chat_order_routes.py").read_text()
    )
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_account_session_chat_order_route"
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
    ) == "account_session_chat_order_update"
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
        "account_session_chat_order_update"
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
    assert register_auth.body[9].value.func.id == "register_auth_account_theme_route"
    assert (
        register_auth.body[10].value.func.id
        == "register_auth_account_session_chat_order_route"
    )
    assert register_auth.body[11].value.func.id == "register_auth_invite_setup_route"

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[10])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthAccountSessionChatOrderRouteDependencies"
    )
    assert [keyword.arg for keyword in dependency_call.keywords] == DEPENDENCY_ORDER
    assert [ast.unparse(keyword.value) for keyword in dependency_call.keywords] == [
        "login_required",
        "lambda: get_current_user()",
        "lambda value: is_valid_session_chat_order(value)",
        "render_account_settings_page",
        "lambda value: normalize_session_chat_order(value)",
        "lambda: get_auth_store()",
        "lambda: SESSION_CHAT_ORDER_LABELS",
    ]

    label_calls = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ast.unparse(node.func) == "dependencies.session_chat_order_labels"
    ]
    store_calls = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ast.unparse(node.func) == "dependencies.get_auth_store"
    ]
    assert len(label_calls) == len(store_calls) == 2


def test_moved_handler_keeps_canonical_ast_and_every_unrelated_auth_identity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_account_session_chat_order_routes.py"
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
        if isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
    )
    original = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "account_session_chat_order_update"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)

    old_unrelated = [
        node for index, node in enumerate(old_register.body) if index not in {10, 11, 12}
    ]
    new_unrelated = [
        node for index, node in enumerate(new_register.body) if index not in {10, 11, 12}
    ]
    assert len(old_unrelated) == len(new_unrelated) == 11
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
        if isinstance(node, ast.FunctionDef) and node.name == "render_account_settings_page"
    )
    new_renderer = next(
        node
        for node in new_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "render_account_settings_page"
    )
    assert ast.dump(old_renderer, include_attributes=False) == ast.dump(
        new_renderer, include_attributes=False
    )

    invite_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "auth_invite_setup_routes.py").read_text()
    )
    moved_invite = next(
        node
        for node in ast.walk(invite_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "invite_setup"
    )
    old_invite = next(
        node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name == "invite_setup"
    )
    assert _canonical_handler(moved_invite) == _canonical_handler(old_invite)
    invite_registrar = next(
        node
        for node in ast.walk(invite_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_invite_setup_route"
    )
    invite_registrations = [
        node
        for node in ast.walk(invite_registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(invite_registrations) == 1


def test_route_preserves_endpoint_methods_order_redirect_cache_and_security_headers(
    app, client, sign_in, users
):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(
        rule
        for rule in app.url_map.iter_rules()
        if rule.endpoint == "account_session_chat_order_update"
    )
    assert rule.rule == ROUTE_PATH
    assert rule.methods == {"POST", "OPTIONS"}
    assert endpoints.index("account_theme_update") < endpoints.index(
        "account_session_chat_order_update"
    ) < endpoints.index("invite_setup")

    anonymous = client.post(ROUTE_PATH, data={"session_chat_order": "oldest_first"})
    assert anonymous.status_code == 302
    assert "/sign-in?next=/account/session-chat-order" in anonymous.headers["Location"]
    assert "Content-Security-Policy" in anonymous.headers

    sign_in(users["party"]["email"], users["party"]["password"])
    updated = client.post(ROUTE_PATH, data={"session_chat_order": "oldest_first"})
    assert updated.status_code == 302
    assert updated.headers["Location"].endswith("/account")
    assert updated.headers["Cache-Control"] == "private, no-store"
    assert "Content-Security-Policy" in updated.headers

    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_forwarded_dependencies_dynamic_mapping_and_exact_event_order(app, monkeypatch):
    events: list[tuple] = []
    user = SimpleNamespace(id=41)
    updated = SimpleNamespace(session_chat_order="oldest_first")

    class FirstStore:
        def get_user_preferences(self, user_id):
            events.append(("current", user_id))
            return SimpleNamespace(session_chat_order="newest_first")

    class SecondStore:
        def set_user_session_chat_order(self, user_id, order):
            events.append(("set", user_id, order))
            return updated

    stores = iter((FirstStore(), SecondStore()))

    class Labels:
        def __getitem__(self, key):
            events.append(("label", key))
            return "Dynamic oldest"

    monkeypatch.setattr(
        auth_module, "get_current_user", lambda: events.append(("user",)) or user
    )
    monkeypatch.setattr(
        auth_module,
        "is_valid_session_chat_order",
        lambda value: events.append(("valid", value)) or True,
    )
    monkeypatch.setattr(
        auth_module,
        "normalize_session_chat_order",
        lambda value: events.append(("normalize", value)) or "oldest_first",
    )
    monkeypatch.setattr(
        auth_module,
        "get_auth_store",
        lambda: events.append(("store",)) or next(stores),
    )
    monkeypatch.setattr(auth_module, "SESSION_CHAT_ORDER_LABELS", Labels())
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
            [
                ("session_chat_order", "  OLDEST_FIRST  "),
                ("session_chat_order", "newest_first"),
            ]
        ),
    ):
        assert _handler(app)() == "redirected"
        assert g.current_user_preferences is updated

    assert events == [
        ("user",),
        ("valid", "  OLDEST_FIRST  "),
        ("normalize", "  OLDEST_FIRST  "),
        ("store",),
        ("current", 41),
        ("store",),
        ("set", 41, "oldest_first"),
        ("label", "oldest_first"),
        ("flash", "Live session chat order updated to Dynamic oldest.", "success"),
        ("url", "account_settings_view"),
        ("redirect", "/account"),
    ]


def test_invalid_noop_and_inner_missing_actor_preserve_exact_boundaries(app, monkeypatch):
    monkeypatch.setattr(auth_module, "get_current_user", lambda: SimpleNamespace(id=7))
    dependencies = _dependencies(app)
    original_renderer = dependencies.render_account_settings_page
    renders: list[int] = []
    object.__setattr__(
        dependencies,
        "render_account_settings_page",
        lambda *, status_code=200: renders.append(status_code) or ("invalid", status_code),
    )
    monkeypatch.setattr(
        auth_module,
        "get_auth_store",
        lambda: (_ for _ in ()).throw(AssertionError("invalid reached store")),
    )
    try:
        for value in ("", "  ", "sideways"):
            with app.test_request_context(
                ROUTE_PATH, method="POST", data={"session_chat_order": value}
            ):
                assert _handler(app)() == ("invalid", 400)
    finally:
        object.__setattr__(
            dependencies, "render_account_settings_page", original_renderer
        )
    assert renders == [400, 400, 400]

    events: list[tuple] = []
    user = SimpleNamespace(id=7)
    labels = {"newest_first": "Newest first"}
    store = SimpleNamespace(
        get_user_preferences=lambda user_id: events.append(("read", user_id))
        or SimpleNamespace(session_chat_order="newest_first"),
        set_user_session_chat_order=lambda *args: events.append(("unexpected_write", *args)),
    )
    monkeypatch.setattr(auth_module, "get_current_user", lambda: user)
    monkeypatch.setattr(auth_module, "is_valid_session_chat_order", lambda value: True)
    monkeypatch.setattr(
        auth_module, "normalize_session_chat_order", lambda value: "newest_first"
    )
    monkeypatch.setattr(auth_module, "get_auth_store", lambda: store)
    monkeypatch.setattr(auth_module, "SESSION_CHAT_ORDER_LABELS", labels)
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category)),
    )
    monkeypatch.setattr(route_module, "url_for", lambda endpoint: "/account")
    monkeypatch.setattr(route_module, "redirect", lambda location: "redirected")
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"session_chat_order": "newest_first"},
    ):
        assert _handler(app)() == "redirected"
    assert events == [
        ("read", 7),
        (
            "flash",
            "Live session chat order already set to Newest first.",
            "success",
        ),
    ]

    monkeypatch.setattr(auth_module, "get_current_user", lambda: None)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"session_chat_order": "newest_first"},
    ):
        with pytest.raises(Exception) as error:
            _handler(app)()
    assert getattr(error.value, "code", None) == 401


def test_bearer_precedence_invalid_bearer_csrf_and_view_as_keep_real_actor(
    app, client, sign_in, users
):
    token = issue_api_token(app, users["party"]["email"], label="p98-bearer")
    app.config["CSRF_ENABLED"] = True
    bearer = client.post(
        ROUTE_PATH,
        data={"session_chat_order": "oldest_first"},
        headers=api_headers(token),
    )
    assert bearer.status_code == 302

    browser = app.test_client()
    sign_in_response = browser.post(
        "/sign-in",
        data={
            "email": users["admin"]["email"],
            "password": users["admin"]["password"],
        },
    )
    assert sign_in_response.status_code == 302
    invalid_bearer = browser.post(
        ROUTE_PATH,
        data={"session_chat_order": "oldest_first"},
        headers=api_headers("invalid-token"),
    )
    assert invalid_bearer.status_code == 400

    app.config["CSRF_ENABLED"] = False
    with browser.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert auth_module._path_supports_view_as(ROUTE_PATH) is False
    admin_update = browser.post(
        ROUTE_PATH, data={"session_chat_order": "oldest_first"}
    )
    assert admin_update.status_code == 302

    with app.app_context():
        store = AuthStore()
        assert (
            store.get_user_preferences(users["party"]["id"]).session_chat_order
            == "oldest_first"
        )
        assert (
            store.get_user_preferences(users["admin"]["id"]).session_chat_order
            == "oldest_first"
        )


@pytest.mark.parametrize("fault_stage", ["execute", "commit"])
def test_execute_and_commit_faults_leave_no_preference_write(
    app, client, sign_in, users, monkeypatch, fault_stage
):
    sign_in(users["party"]["email"], users["party"]["password"])
    user_id = users["party"]["id"]
    with app.app_context():
        real_connection = auth_store_module.get_db()

        class ConnectionProxy:
            def execute(self, sql, parameters=()):
                if "INSERT INTO user_preferences" in sql and fault_stage == "execute":
                    raise RuntimeError("execute fault")
                return real_connection.execute(sql, parameters)

            def commit(self):
                if fault_stage == "commit":
                    raise RuntimeError("commit fault")
                return real_connection.commit()

            def __getattr__(self, name):
                return getattr(real_connection, name)

        monkeypatch.setattr(auth_store_module, "get_db", lambda: ConnectionProxy())
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            client.post(ROUTE_PATH, data={"session_chat_order": "oldest_first"})
        real_connection.rollback()
        assert (
            AuthStore().get_user_preferences(user_id).session_chat_order
            == "newest_first"
        )


def test_commit_survives_internal_reload_fault(app, client, sign_in, users, monkeypatch):
    sign_in(users["party"]["email"], users["party"]["password"])
    user_id = users["party"]["id"]
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
        client.post(ROUTE_PATH, data={"session_chat_order": "oldest_first"})
    assert calls == 3
    with app.app_context():
        assert (
            original_get(AuthStore(), user_id).session_chat_order == "oldest_first"
        )


@pytest.mark.parametrize("fault_stage", ["g", "label", "flash", "url", "redirect"])
def test_committed_preference_survives_every_later_handler_fault(
    app, client, sign_in, users, monkeypatch, fault_stage
):
    sign_in(users["party"]["email"], users["party"]["password"])
    user_id = users["party"]["id"]

    if fault_stage == "g":
        class FailingG:
            def __setattr__(self, name, value):
                raise RuntimeError("g fault")

        monkeypatch.setattr(route_module, "g", FailingG())
    elif fault_stage == "label":
        class FailingLabels:
            def __getitem__(self, key):
                raise RuntimeError("label fault")

        monkeypatch.setattr(auth_module, "SESSION_CHAT_ORDER_LABELS", FailingLabels())
    elif fault_stage == "url":
        monkeypatch.setattr(
            route_module,
            "url_for",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("url fault")),
        )
    else:
        monkeypatch.setattr(
            route_module,
            fault_stage,
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError(f"{fault_stage} fault")
            ),
        )

    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        client.post(ROUTE_PATH, data={"session_chat_order": "oldest_first"})
    with app.app_context():
        assert (
            AuthStore().get_user_preferences(user_id).session_chat_order
            == "oldest_first"
        )


def test_committed_preference_survives_response_fault(
    app, client, sign_in, users
):
    sign_in(users["party"]["email"], users["party"]["password"])
    user_id = users["party"]["id"]

    def fail_response(response):
        if response.status_code == 302 and response.headers.get("Location", "").endswith(
            "/account"
        ):
            raise RuntimeError("response fault")
        return response

    app.after_request_funcs.setdefault(None, []).append(fail_response)

    with pytest.raises(RuntimeError, match="response fault"):
        client.post(ROUTE_PATH, data={"session_chat_order": "oldest_first"})
    with app.app_context():
        assert (
            AuthStore().get_user_preferences(user_id).session_chat_order
            == "oldest_first"
        )
