from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
import player_wiki.auth_me_view_as_update_api_routes as route_module
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "00197bea9ff09253890e951a74c458157f0a3f16"
ROUTE_PATH = "/api/v1/me/view-as"
ENDPOINT = "api.me_view_as_update"
DELETE_ENDPOINT = "api.me_view_as_clear"
DEPENDENCY_ORDER = [
    "api_login_required",
    "get_authenticated_user",
    "json_error",
    "load_json_object",
    "clear_requested_view_as_user_id",
    "serialize_view_as_state",
    "get_auth_store",
    "set_requested_view_as_user_id",
]
FORWARDED_DEPENDENCIES = {
    "get_authenticated_user",
    "clear_requested_view_as_user_id",
    "get_auth_store",
    "set_requested_view_as_user_id",
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


def _dependency_set(events: list[tuple], *, payload=None, user=None, target=None):
    if user is None:
        user = SimpleNamespace(id=1, is_admin=True)
    if payload is None:
        payload = {"user_id": 2}
    if target is None:
        target = SimpleNamespace(id=2, is_active=True)

    def get_user():
        events.append(("get_user",))
        return user

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "json-error"

    def load():
        events.append(("load_json",))
        if isinstance(payload, BaseException):
            raise payload
        return payload

    def clear():
        events.append(("clear",))

    def serialize():
        events.append(("serialize",))
        return {"active_user": None}

    def get_target(user_id):
        events.append(("get_target", user_id))
        return target

    def store():
        events.append(("get_store",))
        return SimpleNamespace(get_user_by_id=get_target)

    def set_target(user_id):
        events.append(("set_target", user_id))

    return {
        "get_authenticated_user": get_user,
        "json_error": error,
        "load_json_object": load,
        "clear_requested_view_as_user_id": clear,
        "serialize_view_as_state": serialize,
        "get_auth_store": store,
        "set_requested_view_as_user_id": set_target,
    }


def test_transport_has_exact_dependencies_registration_wrapper_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthMeViewAsUpdateApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_me_view_as_update_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_view_as_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "me_view_as_update"
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
        and node.name == "register_auth_me_view_as_update_api_route"
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
    assert [item.value for item in methods.elts] == ["POST"]
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
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 217
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 227
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
    assert len(api_route_decorators) == 49

    assert isinstance(register_api.body[162], ast.Expr)
    assert register_api.body[162].value.func.id == "register_auth_me_api_route"
    assert isinstance(register_api.body[163], ast.Expr)
    assert register_api.body[163].value.func.id == (
        "register_auth_me_view_as_update_api_route"
    )
    assert isinstance(register_api.body[164], ast.Expr)
    assert register_api.body[164].value.func.id == (
        "register_auth_me_view_as_clear_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[163])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthMeViewAsUpdateApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    for name in DEPENDENCY_ORDER:
        if name in FORWARDED_DEPENDENCIES:
            assert isinstance(by_name[name], ast.Lambda)
        else:
            assert isinstance(by_name[name], ast.Name)

    helper_names = {"load_json_object", "serialize_view_as_state"}
    assert helper_names <= {
        node.name
        for node in register_api.body
        if isinstance(node, ast.FunctionDef)
    }


def test_moved_handler_and_all_unrelated_register_api_statements_keep_canonical_ast() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_me_view_as_update_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_view_as_update"
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
    original = old_register.body[163]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "me_view_as_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {163, 164, 165, 166}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_pair_methods_login_wrapper_headers_and_inline_delete(
    app, client, sign_in, users
):
    post_rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    delete_rule = next(
        rule for rule in app.url_map.iter_rules() if rule.endpoint == DELETE_ENDPOINT
    )
    assert post_rule.rule == delete_rule.rule == ROUTE_PATH
    assert post_rule.methods == {"POST", "OPTIONS"}
    assert delete_rule.methods == {"DELETE", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "me_view_as_update"
    )
    assert inspect.unwrap(app.view_functions[DELETE_ENDPOINT]).__name__ == (
        "me_view_as_clear"
    )

    anonymous = client.post(ROUTE_PATH, json={})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    sign_in(users["party"]["email"], users["party"]["password"])
    forbidden = client.post(ROUTE_PATH, json={})
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"] == {
        "code": "forbidden",
        "message": "Only app admins can use View As.",
    }

    client.post("/sign-out")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.headers.get("Cache-Control") is None
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.get_json()["view_as"]["active_user"]["email"] == (
        users["party"]["email"]
    )
    cleared = client.delete(ROUTE_PATH)
    assert cleared.status_code == 200
    assert cleared.get_json()["view_as"]["active_user"] is None


def test_handler_preserves_auth_admin_json_target_and_serialization_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependency_set(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        response = _handler(app)()
    assert events == [
        ("get_user",),
        ("load_json",),
        ("get_store",),
        ("get_target", 2),
        ("set_target", 2),
        ("serialize",),
    ]
    assert response.get_json() == {
        "ok": True,
        "view_as": {"active_user": None},
    }


def test_missing_and_nonadmin_stop_before_json_store_or_session_mutation(
    app, monkeypatch
):
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
        with app.test_request_context(ROUTE_PATH, method="POST"):
            assert _handler(app)() == "json-error"
        assert [event[0] for event in events] == ["get_user", "json_error"]
        assert events[-1][1] == expected[:2]
        assert events[-1][2] == {"code": expected[2]}


@pytest.mark.parametrize("payload", (None, {}, {"user_id": None}, {"user_id": ""}))
def test_blank_user_id_clears_before_serialization(app, monkeypatch, payload):
    events: list[tuple] = []
    replacements = _dependency_set(events, payload={})
    if payload is not None:
        replacements["load_json_object"] = (
            lambda: events.append(("load_json",)) or payload
        )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        response = _handler(app)()
    assert [event[0] for event in events] == [
        "get_user",
        "load_json",
        "clear",
        "serialize",
    ]
    assert response.get_json()["ok"] is True


@pytest.mark.parametrize("raw_user_id", (2.9, " 2 "))
def test_existing_int_coercion_semantics_are_preserved(
    app, monkeypatch, raw_user_id
):
    events: list[tuple] = []
    target_id = int(raw_user_id)
    target = SimpleNamespace(id=target_id, is_active=True)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependency_set(
            events, payload={"user_id": raw_user_id}, target=target
        ),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        _handler(app)()
    assert ("get_target", target_id) in events
    assert ("set_target", target_id) in events


@pytest.mark.parametrize("raw_user_id", ("not-a-user", [], {}))
def test_invalid_user_id_returns_exact_400_before_store_or_session(
    app, monkeypatch, raw_user_id
):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependency_set(events, payload={"user_id": raw_user_id}),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == [
        "get_user",
        "load_json",
        "json_error",
    ]
    assert events[-1][1] == ("Choose a valid user to view as.", 400)
    assert events[-1][2] == {"code": "validation_error"}


@pytest.mark.parametrize("raw_user_id", (True, "1"))
def test_self_target_clears_without_store_lookup(app, monkeypatch, raw_user_id):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependency_set(events, payload={"user_id": raw_user_id}),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        _handler(app)()
    assert [event[0] for event in events] == [
        "get_user",
        "load_json",
        "clear",
        "serialize",
    ]


@pytest.mark.parametrize(
    "target", (None, SimpleNamespace(id=2, is_active=False))
)
def test_missing_or_inactive_target_returns_exact_400_without_session_mutation(
    app, monkeypatch, target
):
    events: list[tuple] = []
    replacements = _dependency_set(events)
    replacements["get_auth_store"] = lambda: (
        events.append(("get_store",))
        or SimpleNamespace(
            get_user_by_id=lambda user_id: events.append(("get_target", user_id))
            or target
        )
    )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == [
        "get_user",
        "load_json",
        "get_store",
        "get_target",
        "json_error",
    ]
    assert events[-1][1] == ("Choose an active user to view as.", 400)


def test_json_validation_error_keeps_exact_taxonomy(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependency_set(
            events, payload=ValueError("Request body must be a JSON object.")
        ),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == [
        "get_user",
        "load_json",
        "json_error",
    ]
    assert events[-1][1] == ("Request body must be a JSON object.", 400)
    assert events[-1][2] == {"code": "validation_error"}


def test_forwarded_globals_remain_late_substitutable(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependency_set(events)
    for name in FORWARDED_DEPENDENCIES:
        replacements.pop(name)
    _install_dependencies(app, monkeypatch, **replacements)

    actor = SimpleNamespace(id=1, is_admin=True)
    target = SimpleNamespace(id=2, is_active=True)
    monkeypatch.setattr(
        api_module,
        "get_authenticated_user",
        lambda: events.append(("forwarded_user",)) or actor,
    )
    monkeypatch.setattr(
        api_module,
        "get_auth_store",
        lambda: events.append(("forwarded_store",))
        or SimpleNamespace(get_user_by_id=lambda user_id: target),
    )
    monkeypatch.setattr(
        api_module,
        "set_requested_view_as_user_id",
        lambda user_id: events.append(("forwarded_set", user_id)),
    )
    monkeypatch.setattr(
        api_module,
        "clear_requested_view_as_user_id",
        lambda: events.append(("forwarded_clear",)),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        _handler(app)()
    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_user",
        "forwarded_store",
        "forwarded_set",
    ]


def test_browser_view_as_keeps_real_admin_and_bearer_admin_remains_admitted(
    app, client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    first = client.post(ROUTE_PATH, json={"user_id": users["party"]["id"]})
    assert first.status_code == 200
    second = client.post(ROUTE_PATH, json={"user_id": users["dm"]["id"]})
    assert second.status_code == 200
    assert second.get_json()["view_as"]["active_user"]["email"] == (
        users["dm"]["email"]
    )

    token = issue_api_token(app, users["admin"]["email"], label="p102-admin")
    bearer = client.post(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"user_id": users["party"]["id"]},
    )
    assert bearer.status_code == 200
    assert bearer.get_json()["view_as"]["active_user"]["email"] == (
        users["party"]["email"]
    )


@pytest.mark.parametrize(
    "stage",
    (
        "get_authenticated_user",
        "json_error",
        "load_json_object",
        "clear_requested_view_as_user_id",
        "serialize_view_as_state",
        "get_auth_store",
        "set_requested_view_as_user_id",
        "jsonify",
    ),
)
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app, monkeypatch, stage
):
    events: list[tuple] = []
    replacements = _dependency_set(events)

    def fault(*args, **kwargs):
        events.append(("fault", stage))
        raise RuntimeError(f"{stage} fault")

    if stage == "json_error":
        replacements["get_authenticated_user"] = lambda: None
        replacements["json_error"] = fault
    elif stage == "clear_requested_view_as_user_id":
        replacements["load_json_object"] = lambda: {}
        replacements[stage] = fault
    elif stage == "jsonify":
        monkeypatch.setattr(route_module, "jsonify", fault)
    else:
        replacements[stage] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{stage} fault"):
            _handler(app)()


@pytest.mark.parametrize("mutation", ("clear", "set"))
def test_session_mutation_precedes_serializer_and_jsonify_faults(
    app, monkeypatch, mutation
):
    events: list[tuple] = []
    payload = {} if mutation == "clear" else {"user_id": 2}
    replacements = _dependency_set(events, payload=payload)

    def serialize_fault():
        events.append(("serialize_fault",))
        raise RuntimeError("serialize fault")

    replacements["serialize_view_as_state"] = serialize_fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match="serialize fault"):
            _handler(app)()
    mutation_event = "clear" if mutation == "clear" else "set_target"
    assert [event[0] for event in events].index(mutation_event) < [
        event[0] for event in events
    ].index("serialize_fault")
