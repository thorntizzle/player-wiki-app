from __future__ import annotations

import ast
import copy
from dataclasses import fields
import inspect
from pathlib import Path
import subprocess

import player_wiki.admin_api_routes as route_module
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "ec56364276f65502347c1e770723b115e4b7224e"

ROUTES = (
    ("admin_dashboard_api", "/api/v1/admin", "GET", {"GET", "HEAD", "OPTIONS"}),
    (
        "admin_user_detail_api",
        "/api/v1/admin/users/<int:user_id>",
        "GET",
        {"GET", "HEAD", "OPTIONS"},
    ),
    (
        "admin_invite_user_api",
        "/api/v1/admin/users/invite",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_set_membership_api",
        "/api/v1/admin/users/<int:user_id>/membership",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_remove_membership_api",
        "/api/v1/admin/users/<int:user_id>/membership",
        "DELETE",
        {"DELETE", "OPTIONS"},
    ),
    (
        "admin_assign_character_api",
        "/api/v1/admin/users/<int:user_id>/assignment",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_remove_character_assignment_api",
        "/api/v1/admin/users/<int:user_id>/assignment",
        "DELETE",
        {"DELETE", "OPTIONS"},
    ),
    (
        "admin_issue_invite_api",
        "/api/v1/admin/users/<int:user_id>/invite",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_issue_password_reset_api",
        "/api/v1/admin/users/<int:user_id>/password-reset",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_disable_user_api",
        "/api/v1/admin/users/<int:user_id>/disable",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_enable_user_api",
        "/api/v1/admin/users/<int:user_id>/enable",
        "POST",
        {"POST", "OPTIONS"},
    ),
    (
        "admin_delete_user_api",
        "/api/v1/admin/users/<int:user_id>",
        "DELETE",
        {"DELETE", "OPTIONS"},
    ),
)

DEPENDENCY_ORDER = [field.name for field in fields(route_module.AdminApiDependencies)]


def _register_api(tree: ast.Module) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )


def _canonical_handler(node: ast.FunctionDef) -> str:
    normalized = copy.deepcopy(node)
    normalized.decorator_list = []
    return ast.dump(normalized, include_attributes=False)


def test_admin_api_family_has_exact_owner_dependencies_and_canonical_ast() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "admin_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8")
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/api.py"], text=True
        )
    )
    old_register = _register_api(old_tree)
    new_register = _register_api(api_tree)

    expected_names = [entry[0] for entry in ROUTES]
    old_handlers = old_register.body[167:179]
    assert [node.name for node in old_handlers] == expected_names
    moved_handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in expected_names
    }
    assert list(moved_handlers) == expected_names
    for original in old_handlers:
        assert _canonical_handler(moved_handlers[original.name]) == _canonical_handler(
            original
        )

    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected_names
        for node in ast.walk(api_tree)
    )
    assert {
        "serialize_user",
        "build_admin_local_url",
        "build_admin_dashboard_context",
        "require_admin_target_user",
        "build_admin_user_detail_context",
    } <= {
        node.name
        for node in new_register.body
        if isinstance(node, ast.FunctionDef)
    }
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(route_tree)) == 13

    assert sum(isinstance(node, ast.FunctionDef) for node in new_register.body) == 203
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(new_register)) == 213
    api_route_decorators = [
        decorator
        for node in ast.walk(new_register)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "api"
    ]
    assert len(api_route_decorators) == 35
    registrar_statements = [
        node
        for node in new_register.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_admin_api_routes"
    ]
    assert len(registrar_statements) == 1
    registrar_statement = registrar_statements[0]
    registrar_names = [
        node.value.func.id
        for node in new_register.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id.startswith("register_")
    ]
    registrar_index = registrar_names.index("register_admin_api_routes")
    assert registrar_names[registrar_index - 1 : registrar_index + 2] == [
        "register_auth_me_settings_update_api_route",
        "register_admin_api_routes",
        "register_campaign_visibility_api_routes",
    ]

    dependency_call = next(
        node
        for node in ast.walk(registrar_statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AdminApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(
        isinstance(by_name[name], ast.Lambda)
        for name in {
            "jsonify",
            "abort",
            "build_admin_dashboard_context",
            "require_admin_target_user",
            "build_admin_user_detail_context",
            "get_auth_store",
            "get_repository",
            "get_current_user",
            "get_character_repository",
        }
    )



def test_registrar_declares_exact_rules_methods_endpoints_and_security_order() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "admin_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    registrar = next(
        node
        for node in route_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_admin_api_routes"
    )
    routes_assignment = next(
        node
        for node in registrar.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "routes" for target in node.targets)
    )
    declared = [
        (
            item.elts[1].value,
            f"/api/v1{item.elts[0].value}",
            item.elts[3].elts[0].value,
        )
        for item in routes_assignment.value.elts
    ]
    assert declared == [(endpoint, rule, method) for endpoint, rule, method, _ in ROUTES]

    add_rule = next(
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    )
    view_func = next(
        keyword.value for keyword in add_rule.keywords if keyword.arg == "view_func"
    )
    assert ast.unparse(view_func.func) == "dependencies.api_login_required"
    assert len(view_func.args) == 1
    inner = view_func.args[0]
    assert isinstance(inner, ast.Call)
    assert ast.unparse(inner.func) == "dependencies.api_admin_required"
    assert isinstance(inner.args[0], ast.Name)
    assert inner.args[0].id == "handler"


def test_admin_api_runtime_preserves_all_rule_method_and_order_parity(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    expected_endpoints = [f"api.{entry[0]}" for entry in ROUTES]
    for endpoint, rule_path, _method, methods in ROUTES:
        matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
        assert len(matches) == 1
        assert matches[0].rule == rule_path
        assert matches[0].methods == methods
        assert app.view_functions[f"api.{endpoint}"].__name__ == endpoint

    family_positions = [endpoints.index(endpoint) for endpoint in expected_endpoints]
    assert family_positions == sorted(family_positions)
    assert endpoints.index("api.me_settings_update") < family_positions[0]
    assert family_positions[-1] < endpoints.index("api.app_state")
    assert sum(endpoint.startswith("api.") for endpoint in endpoints) == 136

    concrete_paths = {
        rule.replace("<int:user_id>", "2") for _, rule, _, _ in ROUTES
    }
    for path in concrete_paths:
        assert client.options(path).status_code == 200

    assert client.put("/api/v1/admin").status_code == 405
    assert client.patch("/api/v1/admin/users/2/membership").status_code == 405
    assert client.get("/api/v1/admin/users/2/assignment").status_code == 405


def test_login_and_admin_denials_precede_target_lookup(
    app, client, users, monkeypatch
) -> None:
    calls: list[int] = []

    def forbidden_target(user_id: int):
        calls.append(user_id)
        raise AssertionError("authorization denial reached target lookup")

    raw_view = inspect.unwrap(app.view_functions["api.admin_user_detail_api"])
    target_index = raw_view.__code__.co_freevars.index("require_admin_target_user")
    monkeypatch.setattr(
        raw_view.__closure__[target_index], "cell_contents", forbidden_target
    )
    path = f"/api/v1/admin/users/{users['party']['id']}"
    anonymous = client.get(path)
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"
    assert calls == []

    owner_token = issue_api_token(app, users["owner"]["email"], label="admin-owner-denial")
    non_admin = client.get(path, headers=api_headers(owner_token))
    assert non_admin.status_code == 403
    assert non_admin.get_json()["error"]["code"] == "forbidden"
    assert calls == []


def test_session_csrf_bearer_bypass_and_view_as_keep_real_admin_actor(
    app, client, sign_in, users
) -> None:
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session["view_as_user_id"] = users["party"]["id"]

    dashboard = client.get("/api/v1/admin")
    assert dashboard.status_code == 200

    csrf_denied = client.post(
        "/api/v1/admin/users/invite",
        json={
            "email": "admin-session-csrf@example.com",
            "display_name": "Admin Session CSRF",
            "user_type": "standard",
        },
    )
    assert csrf_denied.status_code == 400
    assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-bearer-csrf")
    bearer = app.test_client().post(
        "/api/v1/admin/users/invite",
        headers=api_headers(admin_token),
        json={
            "email": "admin-bearer-csrf@example.com",
            "display_name": "Admin Bearer CSRF",
            "user_type": "standard",
        },
    )
    assert bearer.status_code == 201
    assert bearer.get_json()["managed_user"]["email"] == "admin-bearer-csrf@example.com"
