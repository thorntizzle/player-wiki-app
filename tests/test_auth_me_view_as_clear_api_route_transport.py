from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
import player_wiki.auth_me_view_as_clear_api_routes as route_module
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "7326d2f83bff5abd91d35f5477af8a8724931f06"
ROUTE_PATH = "/api/v1/me/view-as"
ENDPOINT = "api.me_view_as_clear"
POST_ENDPOINT = "api.me_view_as_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "get_authenticated_user",
    "json_error",
    "clear_requested_view_as_user_id",
    "serialize_view_as_state",
]
FORWARDED_DEPENDENCIES = {
    "get_authenticated_user",
    "clear_requested_view_as_user_id",
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


def _dependency_set(events: list[tuple], *, user=None):
    if user is None:
        user = SimpleNamespace(id=1, is_admin=True)

    def get_user():
        events.append(("get_user",))
        return user

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "json-error"

    def clear():
        events.append(("clear",))

    def serialize():
        events.append(("serialize",))
        return {"active_user": None}

    return {
        "get_authenticated_user": get_user,
        "json_error": error,
        "clear_requested_view_as_user_id": clear,
        "serialize_view_as_state": serialize,
    }


def test_transport_has_exact_dependencies_registration_wrapper_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthMeViewAsClearApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_me_view_as_clear_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_view_as_clear"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "me_view_as_clear"
        for node in ast.walk(api_tree)
    )
    assert not any(
        isinstance(node, ast.Name)
        and node.id
        in {
            "api_campaign_scope_access_required",
            "api_admin_required",
            "current_app",
            "session",
        }
        for node in ast.walk(route_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_auth_me_view_as_clear_api_route"
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
    methods = next(
        keyword.value for keyword in registration.keywords if keyword.arg == "methods"
    )
    assert isinstance(methods, ast.Tuple)
    assert [item.value for item in methods.elts] == ["DELETE"]
    view_func = next(
        keyword.value
        for keyword in registration.keywords
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
    assert len(register_api.body) == 256
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 203
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 213
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
    assert len(api_route_decorators) == 35

    for index, registrar_name in (
        (162, "register_auth_me_api_route"),
        (163, "register_auth_me_view_as_update_api_route"),
        (164, "register_auth_me_view_as_clear_api_route"),
    ):
        assert isinstance(register_api.body[index], ast.Expr)
        assert register_api.body[index].value.func.id == registrar_name
    assert isinstance(register_api.body[165], ast.Expr)
    assert register_api.body[165].value.func.id == (
        "register_auth_me_settings_view_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[164])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthMeViewAsClearApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    for name in DEPENDENCY_ORDER:
        if name in FORWARDED_DEPENDENCIES:
            assert isinstance(by_name[name], ast.Lambda)
        else:
            assert isinstance(by_name[name], ast.Name)

    assert "serialize_view_as_state" in {
        node.name
        for node in register_api.body
        if isinstance(node, ast.FunctionDef)
    }


def test_moved_handler_and_all_unrelated_register_api_statements_keep_canonical_ast() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_me_view_as_clear_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_view_as_clear"
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
    original = old_register.body[164]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "me_view_as_clear"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == 268
    assert len(new_register.body) == 256
    for index, before in enumerate(old_register.body):
        if index in {164, 165, 166}:
            continue
        if 167 <= index <= 178:
            continue
        if 182 <= index <= 183:
            continue
        new_index = index if index < 167 else index - 11 if index < 182 else index - 12
        after = new_register.body[new_index]
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_pair_methods_login_wrapper_headers_and_post_neighbor(
    app, client, sign_in, users
):
    delete_rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    post_rule = next(
        rule for rule in app.url_map.iter_rules() if rule.endpoint == POST_ENDPOINT
    )
    assert delete_rule.rule == post_rule.rule == ROUTE_PATH
    assert delete_rule.methods == {"DELETE", "OPTIONS"}
    assert post_rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == "me_view_as_clear"
    assert inspect.unwrap(app.view_functions[POST_ENDPOINT]).__name__ == (
        "me_view_as_update"
    )

    anonymous = client.delete(ROUTE_PATH)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    sign_in(users["party"]["email"], users["party"]["password"])
    forbidden = client.delete(ROUTE_PATH)
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"] == {
        "code": "forbidden",
        "message": "Only app admins can use View As.",
    }

    client.post("/sign-out")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    set_target = client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    assert set_target.status_code == 200
    response = client.delete(ROUTE_PATH)
    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.headers.get("Cache-Control") is None
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.get_json()["view_as"]["active_user"] is None


def test_handler_preserves_auth_admin_clear_and_serialization_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependency_set(events))
    with app.test_request_context(ROUTE_PATH, method="DELETE"):
        response = _handler(app)()
    assert events == [("get_user",), ("clear",), ("serialize",)]
    assert response.get_json() == {
        "ok": True,
        "view_as": {"active_user": None},
    }


def test_missing_and_nonadmin_stop_before_clear_or_serialization(app, monkeypatch):
    for user, expected in (
        (None, ("Authentication required.", 401, "auth_required")),
        (
            SimpleNamespace(id=3, is_admin=False),
            ("Only app admins can use View As.", 403, "forbidden"),
        ),
    ):
        events: list[tuple] = []
        replacements = _dependency_set(events, user=user)
        if user is None:
            replacements["get_authenticated_user"] = (
                lambda: events.append(("get_user",)) or None
            )
        _install_dependencies(app, monkeypatch, **replacements)
        with app.test_request_context(ROUTE_PATH, method="DELETE"):
            assert _handler(app)() == "json-error"
        assert [event[0] for event in events] == ["get_user", "json_error"]
        assert events[-1][1] == expected[:2]
        assert events[-1][2] == {"code": expected[2]}


def test_forwarded_globals_remain_late_substitutable(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependency_set(events)
    replacements.pop("get_authenticated_user")
    replacements.pop("clear_requested_view_as_user_id")
    _install_dependencies(app, monkeypatch, **replacements)

    actor = SimpleNamespace(id=1, is_admin=True)
    monkeypatch.setattr(
        api_module,
        "get_authenticated_user",
        lambda: events.append(("forwarded_user",)) or actor,
    )
    monkeypatch.setattr(
        api_module,
        "clear_requested_view_as_user_id",
        lambda: events.append(("forwarded_clear",)),
    )
    with app.test_request_context(ROUTE_PATH, method="DELETE"):
        _handler(app)()
    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_user",
        "forwarded_clear",
    ]


def test_browser_view_as_keeps_real_admin_and_bearer_admin_remains_admitted(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    first = client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    assert first.status_code == 200
    browser_clear = client.delete(ROUTE_PATH)
    assert browser_clear.status_code == 200
    assert browser_clear.get_json()["view_as"]["active_user"] is None

    client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    token = issue_api_token(app, users["admin"]["email"], label="p103-admin")
    bearer_clear = client.delete(ROUTE_PATH, headers=api_headers(token))
    assert bearer_clear.status_code == 200
    assert bearer_clear.get_json()["view_as"]["active_user"] is None


def test_delete_reads_no_request_body_and_clear_is_noop_safe(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    first = client.delete(ROUTE_PATH, data="not-json", content_type="text/plain")
    second = client.delete(ROUTE_PATH, json={"ignored": True})
    assert first.status_code == second.status_code == 200
    assert first.get_json()["view_as"]["active_user"] is None
    assert second.get_json()["view_as"]["active_user"] is None


@pytest.mark.parametrize(
    "stage",
    (
        "get_authenticated_user",
        "json_error",
        "clear_requested_view_as_user_id",
        "serialize_view_as_state",
        "jsonify",
    ),
)
def test_unrelated_transport_faults_propagate_at_exact_stage(app, monkeypatch, stage):
    events: list[tuple] = []
    replacements = _dependency_set(events)

    def fault(*args, **kwargs):
        events.append(("fault", stage))
        raise RuntimeError(f"{stage} fault")

    if stage == "json_error":
        replacements["get_authenticated_user"] = lambda: None
        replacements["json_error"] = fault
    elif stage == "jsonify":
        monkeypatch.setattr(route_module, "jsonify", fault)
    else:
        replacements[stage] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="DELETE"):
        with pytest.raises(RuntimeError, match=f"{stage} fault"):
            _handler(app)()


@pytest.mark.parametrize("fault_stage", ("serialize", "jsonify"))
def test_clear_precedes_serializer_and_jsonify_faults(app, monkeypatch, fault_stage):
    events: list[tuple] = []
    replacements = _dependency_set(events)

    def serialize_fault():
        events.append(("serialize_fault",))
        raise RuntimeError("serialize fault")

    def jsonify_fault(*args, **kwargs):
        events.append(("jsonify_fault",))
        raise RuntimeError("jsonify fault")

    if fault_stage == "serialize":
        replacements["serialize_view_as_state"] = serialize_fault
    else:
        monkeypatch.setattr(route_module, "jsonify", jsonify_fault)
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="DELETE"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)()
    names = [event[0] for event in events]
    fault_event = "serialize_fault" if fault_stage == "serialize" else "jsonify_fault"
    assert names.index("clear") < names.index(fault_event)


def test_clear_and_serialization_precede_session_save_fault(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependency_set(events))

    def save_fault(*args, **kwargs):
        events.append(("save_session_fault",))
        raise RuntimeError("save session fault")

    monkeypatch.setattr(app.session_interface, "save_session", save_fault)
    with pytest.raises(RuntimeError, match="save session fault"):
        client.delete(ROUTE_PATH)
    assert [event[0] for event in events] == [
        "get_user",
        "clear",
        "serialize",
        "save_session_fault",
    ]
