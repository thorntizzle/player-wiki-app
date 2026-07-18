from __future__ import annotations

import ast
from dataclasses import fields, replace
from datetime import datetime, timezone
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
import player_wiki.auth_me_settings_view_api_routes as route_module
from player_wiki.auth_store import AuthStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "dbf6f775b684d014928bb9fa096d07ddc3f9657f"
ROUTE_PATH = "/api/v1/me/settings"
ENDPOINT = "api.me_settings"
PATCH_ENDPOINT = "api.me_settings_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "get_current_user",
    "json_error",
    "get_current_user_preferences",
    "serialize_theme_preset",
    "list_theme_presets",
    "session_chat_order_choices",
    "serialize_user",
]
FORWARDED_DEPENDENCIES = {
    "get_current_user",
    "get_current_user_preferences",
    "list_theme_presets",
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
            name = (
                "SESSION_CHAT_ORDER_CHOICES"
                if node.attr == "session_chat_order_choices"
                else node.attr
            )
            return ast.copy_location(ast.Name(id=name, ctx=node.ctx), node)
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    node = _DependencyQualifier().visit(ast.fix_missing_locations(node))
    node.decorator_list = []
    return ast.dump(node, include_attributes=False)


def _dependency_set(events: list[tuple], *, user=object()):
    actual_user = (
        SimpleNamespace(id=7, email="reader@example.com", is_admin=False)
        if user.__class__ is object
        else user
    )
    preferences = SimpleNamespace(
        theme_key="parchment",
        session_chat_order="newest_first",
        frontend_mode="flask",
    )
    presets = [SimpleNamespace(key="one"), SimpleNamespace(key="two")]
    choices = [{"value": "newest_first"}]

    def get_user():
        events.append(("get_user",))
        return actual_user

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "json-error"

    def get_preferences():
        events.append(("get_preferences",))
        return preferences

    def list_presets():
        events.append(("list_presets",))
        return presets

    def serialize_preset(preset):
        events.append(("serialize_preset", preset.key))
        return {"key": preset.key}

    def serialize_user(value):
        events.append(("serialize_user", value.id))
        return {"id": value.id}

    return {
        "get_current_user": get_user,
        "json_error": error,
        "get_current_user_preferences": get_preferences,
        "serialize_theme_preset": serialize_preset,
        "list_theme_presets": list_presets,
        "session_chat_order_choices": choices,
        "serialize_user": serialize_user,
    }


def test_transport_has_exact_dependencies_registration_wrapper_and_source_shape() -> None:
    assert [
        field.name for field in fields(route_module.AuthMeSettingsViewApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "auth_me_settings_view_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_settings"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "me_settings"
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
        and node.name == "register_auth_me_settings_view_api_route"
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
    assert [item.value for item in methods.elts] == ["GET"]
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
        (165, "register_auth_me_settings_view_api_route"),
    ):
        assert isinstance(register_api.body[index], ast.Expr)
        assert register_api.body[index].value.func.id == registrar_name
    assert isinstance(register_api.body[166], ast.Expr)
    assert register_api.body[166].value.func.id == (
        "register_auth_me_settings_update_api_route"
    )
    assert isinstance(register_api.body[167], ast.Expr)
    assert register_api.body[167].value.func.id == "register_admin_api_routes"

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[165])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AuthMeSettingsViewApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    for name in DEPENDENCY_ORDER:
        value = by_name[name]
        if name in FORWARDED_DEPENDENCIES:
            assert isinstance(value, ast.Lambda)
        else:
            assert isinstance(value, ast.Name)

    assert "serialize_theme_preset" in {
        node.name
        for node in register_api.body
        if isinstance(node, ast.FunctionDef)
    }


def test_moved_handler_and_all_unrelated_register_api_statements_keep_canonical_ast() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "auth_me_settings_view_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "me_settings"
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
    original = old_register.body[165]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "me_settings"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == 268
    assert len(new_register.body) == 256
    for index, before in enumerate(old_register.body):
        if index in {165, 166}:
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


def test_route_preserves_methods_login_wrapper_headers_cache_and_patch_neighbor(
    app, client, users
):
    token = issue_api_token(app, users["party"]["email"], label="p104-party")
    get_rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    patch_rule = next(
        rule for rule in app.url_map.iter_rules() if rule.endpoint == PATCH_ENDPOINT
    )
    assert get_rule.rule == patch_rule.rule == ROUTE_PATH
    assert get_rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert patch_rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == "me_settings"
    assert inspect.unwrap(app.view_functions[PATCH_ENDPOINT]).__name__ == (
        "me_settings_update"
    )

    response = client.get(ROUTE_PATH, headers=api_headers(token))
    head = client.head(ROUTE_PATH, headers=api_headers(token))
    assert response.status_code == head.status_code == 200
    assert response.content_type == "application/json"
    assert response.headers.get("Cache-Control") is None
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert head.data == b""
    assert response.get_json()["user"]["email"] == users["party"]["email"]


def test_handler_preserves_preferences_preset_choice_user_and_jsonify_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependency_set(events))

    original_jsonify = route_module.jsonify

    def record_jsonify(*args, **kwargs):
        events.append(("jsonify",))
        return original_jsonify(*args, **kwargs)

    monkeypatch.setattr(route_module, "jsonify", record_jsonify)
    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)()
    assert events == [
        ("get_user",),
        ("get_preferences",),
        ("list_presets",),
        ("serialize_preset", "one"),
        ("serialize_preset", "two"),
        ("serialize_user", 7),
        ("jsonify",),
    ]
    assert list(response.get_json()) == [
        "ok",
        "preferences",
        "session_chat_order_choices",
        "theme_presets",
        "user",
    ]
    assert response.get_json()["preferences"] == {
        "frontend_mode": "flask",
        "session_chat_order": "newest_first",
        "theme_key": "parchment",
    }


def test_missing_user_stops_before_preferences_presets_choices_and_serialization(
    app, monkeypatch
):
    events: list[tuple] = []
    replacements = _dependency_set(events, user=None)
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH):
        assert _handler(app)() == "json-error"
    assert [event[0] for event in events] == ["get_user", "json_error"]
    assert events[-1][1] == ("Authentication required.", 401)
    assert events[-1][2] == {"code": "auth_required"}


def test_forwarded_globals_remain_late_substitutable(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependency_set(events)
    for name in FORWARDED_DEPENDENCIES:
        replacements.pop(name)
    _install_dependencies(app, monkeypatch, **replacements)

    user = SimpleNamespace(id=12)
    preferences = SimpleNamespace(
        theme_key="moonlit",
        session_chat_order="oldest_first",
        frontend_mode="flask",
    )
    monkeypatch.setattr(
        api_module,
        "get_current_user",
        lambda: events.append(("forwarded_user",)) or user,
    )
    monkeypatch.setattr(
        api_module,
        "get_current_user_preferences",
        lambda: events.append(("forwarded_preferences",)) or preferences,
    )
    monkeypatch.setattr(
        api_module,
        "list_theme_presets",
        lambda: events.append(("forwarded_presets",)) or [],
    )
    with app.test_request_context(ROUTE_PATH):
        _handler(app)()
    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_user",
        "forwarded_preferences",
        "forwarded_presets",
    ]


def test_session_chat_choices_capture_original_list_and_observe_in_place_mutation(
    app, monkeypatch
):
    dependencies = _dependencies_cell(app).cell_contents
    assert dependencies.session_chat_order_choices is api_module.SESSION_CHAT_ORDER_CHOICES
    replacements = _dependency_set([])
    replacements["session_chat_order_choices"] = dependencies.session_chat_order_choices
    _install_dependencies(app, monkeypatch, **replacements)
    dependencies = _dependencies_cell(app).cell_contents
    marker = {
        "value": "p104-marker",
        "label": "P104 marker",
        "description": "Captured list identity proof.",
    }
    dependencies.session_chat_order_choices.append(marker)
    try:
        with app.test_request_context(ROUTE_PATH):
            response = _handler(app)()
        assert response.get_json()["session_chat_order_choices"][-1] == marker
    finally:
        dependencies.session_chat_order_choices.remove(marker)


def test_browser_view_as_noncampaign_read_keeps_real_admin_and_safe_get_needs_no_csrf(
    client, sign_in, users
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    assert client.post(
        "/api/v1/me/view-as", json={"user_id": users["party"]["id"]}
    ).status_code == 200
    response = client.get(ROUTE_PATH)
    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == users["admin"]["email"]


@pytest.mark.parametrize(
    "stage",
    (
        "get_current_user",
        "get_current_user_preferences",
        "list_theme_presets",
        "serialize_theme_preset",
        "serialize_user",
        "jsonify",
    ),
)
def test_unrelated_transport_faults_propagate_at_exact_stage(app, monkeypatch, stage):
    events: list[tuple] = []
    replacements = _dependency_set(events)

    def fault(*args, **kwargs):
        events.append(("fault", stage))
        raise RuntimeError(f"{stage} fault")

    if stage == "jsonify":
        monkeypatch.setattr(route_module, "jsonify", fault)
    else:
        replacements[stage] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(RuntimeError, match=f"{stage} fault"):
            _handler(app)()


def test_bearer_token_touch_precedes_late_serializer_fault_and_remains_durable(
    app, client, users, monkeypatch
):
    token = issue_api_token(app, users["party"]["email"], label="p104-fault")
    with app.app_context():
        record = AuthStore().get_active_api_token(token)
        assert record is not None
        token_id = record.id
        before = record.last_used_at

    def fault(*args, **kwargs):
        raise RuntimeError("late serializer fault")

    _install_dependencies(app, monkeypatch, serialize_user=fault)
    with pytest.raises(RuntimeError, match="late serializer fault"):
        client.get(ROUTE_PATH, headers=api_headers(token))

    with app.app_context():
        after = AuthStore().get_api_token_by_id(token_id)
        assert after is not None
        assert after.last_used_at >= before
        assert after.last_used_at <= datetime.now(timezone.utc)
