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

import player_wiki.auth as auth_module
import player_wiki.auth_sign_in_routes as route_module
from player_wiki.auth import AUTH_SESSION_KEY, VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "5518acaba730c5a57d11177f274de030796a1cc3"
ROUTE_PATH = "/sign-in"
DEPENDENCY_ORDER = [
    "get_current_user",
    "get_auth_store",
    "get_login_throttle",
    "account_digest",
    "canonical_client_key",
    "render_throttled_sign_in",
    "check_sign_in_password",
    "sign_in_failure_message",
    "begin_browser_session",
    "resolve_next_url",
]


def _handler(app, endpoint: str):
    return inspect.unwrap(app.view_functions[endpoint])


def _dependencies(app, endpoint: str = "sign_in_submit"):
    raw_view = _handler(app, endpoint)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"].cell_contents


class _DependencyQualifier(ast.NodeTransformer):
    _ORIGINAL_HELPER_NAMES = {
        "render_throttled_sign_in": "_render_throttled_sign_in",
        "check_sign_in_password": "_check_sign_in_password",
    }

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
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sign_in_failure_message"
            and not node.args
            and not node.keywords
        ):
            return ast.copy_location(
                ast.Name(id="SIGN_IN_FAILURE_MESSAGE", ctx=ast.Load()),
                node,
            )
        if isinstance(node.func, ast.Name) and node.func.id in self._ORIGINAL_HELPER_NAMES:
            node.func.id = self._ORIGINAL_HELPER_NAMES[node.func.id]
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    normalized = _DependencyQualifier().visit(copy.deepcopy(node))
    normalized.decorator_list = []
    return ast.dump(ast.fix_missing_locations(normalized), include_attributes=False)


def _register_auth(tree: ast.Module) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_auth"
    )


def test_transport_has_exact_all_late_dependencies_registration_and_source_shape() -> None:
    assert [field.name for field in fields(route_module.AuthSignInRouteDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse((source_root / "auth_sign_in_routes.py").read_text())
    auth_tree = ast.parse((source_root / "auth.py").read_text())
    handlers = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"sign_in", "sign_in_submit"}
    ]
    assert {handler.name for handler in handlers} == {"sign_in", "sign_in_submit"}
    assert all(handler.decorator_list == [] for handler in handlers)
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in {"sign_in", "sign_in_submit"}
        for node in ast.walk(auth_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "register_auth_sign_in_routes"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2
    assert [
        next(
            keyword.value.value
            for keyword in registration.keywords
            if keyword.arg == "endpoint"
        )
        for registration in registrations
    ] == ["sign_in", "sign_in_submit"]
    assert [
        next(
            element.value
            for keyword in registration.keywords
            if keyword.arg == "methods"
            for element in keyword.value.elts
        )
        for registration in registrations
    ] == ["GET", "POST"]

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
    assert register_auth.body[5].name == "inject_auth_context"
    assert register_auth.body[6].value.func.id == "register_auth_sign_in_routes"
    assert register_auth.body[7].value.func.id == "register_auth_sign_out_route"
    assert register_auth.body[8].value.func.id == "register_auth_account_settings_view_route"
    assert register_auth.body[9].value.func.id == "register_auth_account_theme_route"

    dependency_call = next(
        node
        for node in ast.walk(register_auth.body[6])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthSignInRouteDependencies"
    )
    assert [keyword.arg for keyword in dependency_call.keywords] == DEPENDENCY_ORDER
    assert all(isinstance(keyword.value, ast.Lambda) for keyword in dependency_call.keywords)
    failure_getter = next(
        keyword.value
        for keyword in dependency_call.keywords
        if keyword.arg == "sign_in_failure_message"
    )
    assert isinstance(failure_getter.body, ast.Name)
    assert failure_getter.body.id == "SIGN_IN_FAILURE_MESSAGE"


def test_moved_handlers_keep_canonical_ast_and_every_unrelated_auth_identity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "auth_sign_in_routes.py").read_text()
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
    moved_by_name = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"sign_in", "sign_in_submit"}
    }
    old_by_name = {
        node.name: node
        for node in old_register.body
        if isinstance(node, ast.FunctionDef) and node.name in moved_by_name
    }
    assert {
        name: _canonical_handler(node) for name, node in moved_by_name.items()
    } == {name: _canonical_handler(node) for name, node in old_by_name.items()}

    old_unrelated = [
        node
        for index, node in enumerate(old_register.body)
        if index not in {6, 7, 8, 9, 10, 11, 12}
    ]
    new_unrelated = [
        node
        for index, node in enumerate(new_register.body)
        if index not in {6, 7, 8, 9, 10, 11}
    ]
    assert len(old_unrelated) == len(new_unrelated) == 8
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
    assert "_check_sign_in_password" in new_module_helpers
    assert "_render_throttled_sign_in" in new_module_helpers


def test_route_preserves_endpoints_methods_order_no_store_and_security_headers(app, client):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    get_rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == "sign_in")
    post_rule = next(
        rule for rule in app.url_map.iter_rules() if rule.endpoint == "sign_in_submit"
    )
    assert get_rule.rule == post_rule.rule == ROUTE_PATH
    assert get_rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert post_rule.methods == {"POST", "OPTIONS"}
    assert endpoints.index("sign_in") < endpoints.index("sign_in_submit") < endpoints.index(
        "sign_out"
    )

    response = client.get(ROUTE_PATH)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "Content-Security-Policy" in response.headers
    head = client.head(f"{ROUTE_PATH}?next=%20%2Fcampaigns%20")
    assert head.status_code == 200
    assert head.get_data() == b""
    assert client.options(ROUTE_PATH).status_code == 200
    assert client.post(ROUTE_PATH, data={}).status_code == 400
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_bearer_browser_session_view_as_and_csrf_envelope_remain_outside_handler(
    app, client, sign_in, users
):
    token = issue_api_token(app, users["party"]["email"], label="p94-bearer")
    bearer = client.get(ROUTE_PATH, headers=api_headers(token))
    assert bearer.status_code == 302
    assert bearer.headers["Location"].endswith("/")

    client = app.test_client()
    sign_in_response = client.post(
        ROUTE_PATH,
        data={
            "email": users["admin"]["email"],
            "password": users["admin"]["password"],
        },
    )
    assert sign_in_response.status_code == 302
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert auth_module._path_supports_view_as(ROUTE_PATH) is False
    assert client.get(ROUTE_PATH).status_code == 302

    app.config["CSRF_ENABLED"] = True
    session_setup_exempt = client.post(
        ROUTE_PATH,
        data={
            "email": users["party"]["email"],
            "password": users["party"]["password"],
        },
    )
    assert session_setup_exempt.status_code == 302
    with client.session_transaction() as browser_session:
        assert AUTH_SESSION_KEY in browser_session


def test_all_dependencies_are_late_bound_and_success_order_is_preserved(
    app, monkeypatch
):
    events: list[tuple] = []
    user = SimpleNamespace(
        id=17,
        display_name="Late Bound",
        is_active=True,
        password_hash="stored-hash",
    )
    decision = SimpleNamespace(blocked=False, retry_after=0)
    attempt = SimpleNamespace(decision=decision)

    class Store:
        def get_user_by_email(self, email):
            events.append(("get_user", email))
            return user

        def create_session(self, user_id, **kwargs):
            events.append(("create_session", user_id, kwargs))
            return "raw-token", SimpleNamespace(id=31)

    class Throttle:
        def precheck(self, **kwargs):
            events.append(("precheck", kwargs))
            return attempt

        def cancel(self, attempt_arg):
            events.append(("cancel", attempt_arg))

        def record_failure(self, attempt_arg):
            events.append(("failure", attempt_arg))
            return decision

        def record_success(self, attempt_arg):
            events.append(("success", attempt_arg))

    replacements = {
        "get_current_user": lambda: events.append(("current_user",)) or None,
        "get_auth_store": lambda: events.append(("store",)) or Store(),
        "get_login_throttle": lambda: events.append(("throttle",)) or Throttle(),
        "account_digest": lambda value: events.append(("account", value)) or "account-key",
        "canonical_client_key": lambda value: events.append(("client", value)) or "client-key",
        "_render_throttled_sign_in": lambda **kwargs: events.append(("render_throttled", kwargs)),
        "_check_sign_in_password": lambda account, password: events.append(
            ("password", account, password)
        )
        or True,
        "SIGN_IN_FAILURE_MESSAGE": "late failure message",
        "begin_browser_session": lambda token: events.append(("begin", token)),
        "resolve_next_url": lambda value: events.append(("resolve", value)) or "/safe-next",
    }
    for name, replacement in replacements.items():
        monkeypatch.setattr(auth_module, name, replacement)
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category)),
    )
    monkeypatch.setattr(
        route_module,
        "redirect",
        lambda target: events.append(("redirect", target)) or "redirect-result",
    )

    assert _dependencies(app)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={
            "email": "  Late@Example.COM  ",
            "password": "secret",
            "next": "  /requested  ",
        },
        environ_base={"REMOTE_ADDR": "192.0.2.44"},
        headers={"User-Agent": "P94 Agent"},
    ):
        assert _handler(app, "sign_in_submit")() == "redirect-result"

    assert [event[0] for event in events] == [
        "current_user",
        "store",
        "throttle",
        "account",
        "client",
        "precheck",
        "get_user",
        "password",
        "create_session",
        "begin",
        "success",
        "flash",
        "resolve",
        "redirect",
    ]
    assert events[3] == ("account", "Late@Example.COM")
    assert events[4] == ("client", "192.0.2.44")
    assert events[5][1] == {
        "account_key": "account-key",
        "client_key": "client-key",
    }
    assert events[8][1] == 17
    assert events[8][2] == {
        "expires_in": timedelta(hours=app.config["SESSION_TTL_HOURS"]),
        "user_agent": "P94 Agent",
        "ip_address": "192.0.2.44",
    }
    assert events[-3:] == [
        ("flash", "Signed in as Late Bound.", "success"),
        ("resolve", "/requested"),
        ("redirect", "/safe-next"),
    ]


def test_authenticated_early_redirect_precedes_query_form_store_and_throttle(
    app, monkeypatch
):
    events: list[str] = []
    monkeypatch.setattr(
        auth_module,
        "get_current_user",
        lambda: events.append("current_user") or SimpleNamespace(id=1),
    )

    def unexpected(*args, **kwargs):
        events.append("downstream")
        raise AssertionError("authenticated early redirect reached downstream work")

    for name in (
        "get_auth_store",
        "get_login_throttle",
        "account_digest",
        "canonical_client_key",
        "_render_throttled_sign_in",
        "_check_sign_in_password",
        "begin_browser_session",
        "resolve_next_url",
    ):
        monkeypatch.setattr(auth_module, name, unexpected)

    with app.test_request_context(f"{ROUTE_PATH}?next=%2Funsafe", method="GET"):
        response = _handler(app, "sign_in")()
        assert response.status_code == 302
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"email": "ignored@example.com", "password": "ignored"},
    ):
        response = _handler(app, "sign_in_submit")()
        assert response.status_code == 302
    assert events == ["current_user", "current_user"]


@pytest.mark.parametrize("fault_stage", ["password", "begin"])
def test_faults_cancel_throttle_without_rolling_back_an_already_created_session(
    app, monkeypatch, fault_stage
):
    events: list[str] = []
    user = SimpleNamespace(
        id=17,
        display_name="Fault User",
        is_active=True,
        password_hash="stored-hash",
    )
    attempt = SimpleNamespace(decision=SimpleNamespace(blocked=False, retry_after=0))

    class Store:
        def get_user_by_email(self, email):
            events.append("lookup")
            return user

        def create_session(self, user_id, **kwargs):
            events.append("session_persisted")
            return "raw-token", SimpleNamespace(id=31)

    class Throttle:
        def precheck(self, **kwargs):
            events.append("precheck")
            return attempt

        def cancel(self, attempt_arg):
            events.append("cancel")

        def record_success(self, attempt_arg):
            events.append("success")

    monkeypatch.setattr(auth_module, "get_current_user", lambda: None)
    monkeypatch.setattr(auth_module, "get_auth_store", Store)
    monkeypatch.setattr(auth_module, "get_login_throttle", Throttle)
    monkeypatch.setattr(auth_module, "account_digest", lambda value: "account")
    monkeypatch.setattr(auth_module, "canonical_client_key", lambda value: "client")

    def check_password(user_arg, password):
        events.append("password")
        if fault_stage == "password":
            raise RuntimeError("password fault")
        return True

    def begin_session(token):
        events.append("begin")
        if fault_stage == "begin":
            raise RuntimeError("begin fault")

    monkeypatch.setattr(auth_module, "_check_sign_in_password", check_password)
    monkeypatch.setattr(auth_module, "begin_browser_session", begin_session)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"email": "fault@example.com", "password": "secret"},
    ):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app, "sign_in_submit")()

    if fault_stage == "password":
        assert events == ["precheck", "lookup", "password", "cancel"]
    else:
        assert events == [
            "precheck",
            "lookup",
            "password",
            "session_persisted",
            "begin",
            "cancel",
        ]
