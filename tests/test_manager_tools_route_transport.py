from __future__ import annotations

import ast
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = PROJECT_ROOT / "player_wiki" / "manager_tools_routes.py"
MANAGER_TOOLS_ROUTE = "/campaigns/<campaign_slug>/manager-tools"
MANAGER_TOOLS_URL = "/campaigns/linden-pass/manager-tools"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_manager_tools_registrar_owns_one_get_only_rule_without_decorators() -> None:
    register = _function("register_manager_tools_routes")
    handler = _function("campaign_manager_tools_view")
    registrations = [
        node
        for node in ast.walk(register)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]

    assert handler.decorator_list == []
    assert len(registrations) == 1
    assert ast.literal_eval(registrations[0].args[0]) == MANAGER_TOOLS_ROUTE
    keywords = {keyword.arg: keyword.value for keyword in registrations[0].keywords}
    assert ast.literal_eval(keywords["endpoint"]) == "campaign_manager_tools_view"
    assert ast.literal_eval(keywords["methods"]) == ("GET",)


@pytest.mark.parametrize("method", ("POST", "PUT", "PATCH", "DELETE"))
def test_manager_tools_write_methods_are_405_and_private_no_store(
    client,
    sign_in,
    users,
    method,
) -> None:
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.open(MANAGER_TOOLS_URL, method=method)

    assert response.status_code == 405
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_manager_tools_get_head_options_keep_implicit_transport_and_protection(
    client,
    sign_in,
    users,
) -> None:
    sign_in(users["dm"]["email"], users["dm"]["password"])

    get_response = client.get(MANAGER_TOOLS_URL)
    head_response = client.head(MANAGER_TOOLS_URL)
    options_response = client.open(MANAGER_TOOLS_URL, method="OPTIONS")

    assert get_response.status_code == 200
    assert head_response.status_code == 200
    assert head_response.data == b""
    assert options_response.status_code == 200
    assert set(options_response.allow) >= {"GET", "HEAD", "OPTIONS"}
    for response in (get_response, head_response, options_response):
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"

    missing = client.get("/campaigns/no-such-campaign/manager-tools")
    assert missing.status_code == 404
    assert missing.headers["Cache-Control"] == "private, no-store"
    assert missing.headers["Referrer-Policy"] == "no-referrer"
