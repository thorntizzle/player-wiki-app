from __future__ import annotations

import ast
from dataclasses import fields, replace
from datetime import timedelta
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
import player_wiki.auth_me_api_routes as route_module
from player_wiki.auth_store import AuthStore, utcnow
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "ed5beede148eccdb60b71284e552ed2eac6dbfd8"
ROUTE_PATH = "/api/v1/me"
ENDPOINT = "api.me"
DEPENDENCY_ORDER = [
    "api_login_required",
    "get_authenticated_user",
    "json_error",
    "serialize_app_state",
    "get_current_auth_source",
    "serialize_user",
    "get_current_memberships",
    "serialize_membership",
    "get_current_user_preferences",
    "serialize_view_as_state",
]
FORWARDED_DEPENDENCIES = {
    "get_authenticated_user",
    "get_current_auth_source",
    "get_current_memberships",
    "get_current_user_preferences",
}


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _dependencies_cell(app):
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"]


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    cell = _dependencies_cell(app)
    monkeypatch.setattr(
        cell,
        "cell_contents",
        replace(cell.cell_contents, **replacements),
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
    node = _DependencyQualifier().visit(ast.fix_missing_locations(node))
    node.decorator_list = []
    return ast.dump(node, include_attributes=False)


def _read_dependencies(events: list[tuple]):
    user = SimpleNamespace(id=7, email="reader@example.com")
    memberships = [SimpleNamespace(slug="one"), SimpleNamespace(slug="two")]
    preferences = SimpleNamespace(
        theme_key="moonlit",
        session_chat_order="oldest_first",
        frontend_mode="flask",
    )

    def get_user():
        events.append(("get_user",))
        return user

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "json-error"

    def app_state():
        events.append(("app",))
        return {"name": "Campaign Player Wiki"}

    def auth_source():
        events.append(("auth_source",))
        return "browser_session"

    def serialize_user(value):
        events.append(("serialize_user", value))
        return {"id": value.id, "email": value.email}

    def get_memberships():
        events.append(("memberships",))
        return memberships

    def serialize_membership(value):
        events.append(("serialize_membership", value.slug))
        return {"campaign_slug": value.slug}

    def get_preferences():
        events.append(("preferences",))
        return preferences

    def view_as():
        events.append(("view_as",))
        return {"can_view_as": False, "active_user": None, "user_choices": []}

    return {
        "get_authenticated_user": get_user,
        "json_error": error,
        "serialize_app_state": app_state,
        "get_current_auth_source": auth_source,
        "serialize_user": serialize_user,
        "get_current_memberships": get_memberships,
        "serialize_membership": serialize_membership,
        "get_current_user_preferences": get_preferences,
        "serialize_view_as_state": view_as,
    }


def test_transport_has_exact_dependencies_registration_wrapper_and_source_shape() -> None:
    assert [field.name for field in fields(route_module.AuthMeApiDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_me_api_routes.py").read_text(encoding="utf-8")
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "me"
        for node in ast.walk(api_tree)
    )
    assert not any(
        isinstance(node, ast.Name)
        and node.id
        in {
            "api_campaign_scope_access_required",
            "api_admin_required",
            "current_app",
            "request",
            "get_auth_store",
        }
        for node in ast.walk(route_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "register_auth_me_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    view_func = next(
        keyword.value
        for keyword in registrations[0].keywords
        if keyword.arg == "view_func"
    )
    assert isinstance(view_func, ast.Call)
    assert isinstance(view_func.func, ast.Attribute)
    assert view_func.func.attr == "api_login_required"

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 257
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 205
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 215
    api_route_decorators = [
        decorator
        for node in ast.walk(register_api)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "api"
    ]
    assert len(api_route_decorators) == 37

    assert isinstance(register_api.body[161], ast.FunctionDef)
    assert register_api.body[161].name == "serialize_theme_preset"
    assert isinstance(register_api.body[162], ast.Expr)
    assert register_api.body[162].value.func.id == "register_auth_me_api_route"
    assert isinstance(register_api.body[163], ast.Expr)
    assert register_api.body[163].value.func.id == (
        "register_auth_me_view_as_update_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[162])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthMeApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    for name in DEPENDENCY_ORDER:
        if name in FORWARDED_DEPENDENCIES:
            assert isinstance(by_name[name], ast.Lambda)
        else:
            assert isinstance(by_name[name], ast.Name)

    helper_names = {
        "serialize_theme_preset",
        "serialize_app_state",
        "serialize_user",
        "serialize_membership",
        "serialize_view_as_state",
    }
    assert helper_names <= {
        node.name
        for node in register_api.body
        if isinstance(node, ast.FunctionDef)
    }


def test_moved_handler_and_all_unrelated_register_api_statements_keep_canonical_ast() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "auth_me_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me"
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/api.py"], text=True
        )
    )
    new_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8")
    )
    old_register = next(
        node
        for node in old_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    new_register = next(
        node
        for node in new_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    original = old_register.body[162]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "me"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == 268
    assert len(new_register.body) == 257
    for index, before in enumerate(old_register.body):
        if index in {162, 163, 164, 165, 166}:
            continue
        if 167 <= index <= 178:
            continue
        after = new_register.body[index if index < 167 else index - 11]
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_headers(
    app, client, sign_in, users
):
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    assert rule.rule == ROUTE_PATH
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == "me"

    anonymous_get = client.get(ROUTE_PATH)
    anonymous_head = client.head(ROUTE_PATH)
    assert anonymous_get.status_code == anonymous_head.status_code == 401
    assert anonymous_get.get_json()["error"]["code"] == "auth_required"
    assert anonymous_head.get_data() == b""

    sign_in(users["party"]["email"], users["party"]["password"])
    response = client.get(ROUTE_PATH)
    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.headers.get("Cache-Control") is None
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_handler_preserves_exact_read_and_serialization_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_read_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="GET"):
        response = _handler(app)()

    assert [event[0] for event in events] == [
        "get_user",
        "app",
        "auth_source",
        "serialize_user",
        "memberships",
        "serialize_membership",
        "serialize_membership",
        "preferences",
        "preferences",
        "preferences",
        "view_as",
    ]
    assert response.get_json() == {
        "ok": True,
        "app": {"name": "Campaign Player Wiki"},
        "auth_source": "browser_session",
        "user": {"id": 7, "email": "reader@example.com"},
        "memberships": [
            {"campaign_slug": "one"},
            {"campaign_slug": "two"},
        ],
        "preferences": {
            "theme_key": "moonlit",
            "session_chat_order": "oldest_first",
            "frontend_mode": "flask",
        },
        "view_as": {
            "can_view_as": False,
            "active_user": None,
            "user_choices": [],
        },
    }


def test_redundant_handler_auth_check_returns_exact_401_before_other_reads(
    app, monkeypatch
):
    events: list[tuple] = []
    replacements = _read_dependencies(events)

    def missing_user():
        events.append(("get_user",))
        return None

    replacements["get_authenticated_user"] = missing_user
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="GET"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == ["get_user", "json_error"]
    assert events[-1][1] == ("Authentication required.", 401)
    assert events[-1][2] == {"code": "auth_required"}


def test_forwarded_globals_remain_late_substitutable(app, monkeypatch):
    events: list[tuple] = []
    replacements = _read_dependencies(events)
    for name in FORWARDED_DEPENDENCIES:
        replacements.pop(name)
    _install_dependencies(app, monkeypatch, **replacements)

    user = SimpleNamespace(id=13, email="forwarded@example.com")
    preferences = SimpleNamespace(
        theme_key="ember",
        session_chat_order="newest_first",
        frontend_mode="flask",
    )
    monkeypatch.setattr(
        api_module,
        "get_authenticated_user",
        lambda: events.append(("forwarded_user",)) or user,
    )
    monkeypatch.setattr(
        api_module,
        "get_current_auth_source",
        lambda: events.append(("forwarded_source",)) or "api_token",
    )
    monkeypatch.setattr(
        api_module,
        "get_current_memberships",
        lambda: events.append(("forwarded_memberships",)) or [],
    )
    monkeypatch.setattr(
        api_module,
        "get_current_user_preferences",
        lambda: events.append(("forwarded_preferences",)) or preferences,
    )
    with app.test_request_context(ROUTE_PATH, method="GET"):
        response = _handler(app)()

    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_user",
        "forwarded_source",
        "forwarded_memberships",
        "forwarded_preferences",
        "forwarded_preferences",
        "forwarded_preferences",
    ]
    assert response.get_json()["auth_source"] == "api_token"
    assert response.get_json()["preferences"]["theme_key"] == "ember"


def test_bearer_precedence_and_browser_view_as_keep_real_actor(
    app, client, sign_in, users
):
    sign_in(users["party"]["email"], users["party"]["password"])
    admin_token = issue_api_token(app, users["admin"]["email"], label="p101-admin")
    bearer_response = client.get(ROUTE_PATH, headers=api_headers(admin_token))
    assert bearer_response.status_code == 200
    assert bearer_response.get_json()["auth_source"] == "api_token"
    assert bearer_response.get_json()["user"]["email"] == users["admin"]["email"]

    client.post("/sign-out")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    set_view_as = client.post(
        "/api/v1/me/view-as", json={"user_id": users["party"]["id"]}
    )
    assert set_view_as.status_code == 200
    browser_response = client.get(ROUTE_PATH)
    assert browser_response.status_code == 200
    assert browser_response.get_json()["auth_source"] == "browser_session"
    assert browser_response.get_json()["user"]["email"] == users["admin"]["email"]
    assert browser_response.get_json()["view_as"]["active_user"]["email"] == (
        users["party"]["email"]
    )


def test_bearer_touch_commits_before_handler_fault(
    app, client, users, monkeypatch
):
    token = issue_api_token(app, users["dm"]["email"], label="p101-touch")
    with app.app_context():
        store = AuthStore()
        token_record = store.get_active_api_token(token)
        assert token_record is not None
        store.touch_api_token(token_record.id, at=utcnow() - timedelta(days=1))
        before = store.get_active_api_token(token)
        assert before is not None
        before_used_at = before.last_used_at

    def fault():
        raise RuntimeError("serialize app fault")

    _install_dependencies(app, monkeypatch, serialize_app_state=fault)
    with pytest.raises(RuntimeError, match="serialize app fault"):
        client.get(ROUTE_PATH, headers=api_headers(token))

    with app.app_context():
        after = AuthStore().get_active_api_token(token)
        assert after is not None
        assert after.last_used_at > before_used_at


@pytest.mark.parametrize(
    "stage",
    (
        "get_authenticated_user",
        "json_error",
        "serialize_app_state",
        "get_current_auth_source",
        "serialize_user",
        "get_current_memberships",
        "serialize_membership",
        "get_current_user_preferences",
        "serialize_view_as_state",
        "jsonify",
    ),
)
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app, monkeypatch, stage
):
    events: list[tuple] = []
    replacements = _read_dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{stage} fault")

    if stage == "json_error":
        replacements["get_authenticated_user"] = lambda: None
        replacements["json_error"] = fault
    elif stage == "jsonify":
        monkeypatch.setattr(route_module, "jsonify", fault)
    else:
        replacements[stage] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="GET"):
        with pytest.raises(RuntimeError, match=f"{stage} fault"):
            _handler(app)()
