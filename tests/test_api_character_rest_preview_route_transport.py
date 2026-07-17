from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.character_rest_preview_api_routes as route_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/rest-preview/long"
)
ENDPOINT = "api.character_rest_preview"
DEPENDENCY_ORDER = [
    "api_login_required",
    "load_character_record",
    "has_session_mode_access",
    "get_character_state_service",
    "json_error",
]


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    current = freevars["dependencies"].cell_contents
    monkeypatch.setattr(
        freevars["dependencies"],
        "cell_contents",
        replace(current, **replacements),
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


def _dependencies(events: list[tuple], *, preview_error=None):
    record = SimpleNamespace(slug="arden-march")
    changes = [
        SimpleNamespace(label="Current HP", from_value=3, to_value=9),
        SimpleNamespace(label="Sorcery Points", from_value=0, to_value=4),
    ]
    preview = SimpleNamespace(
        rest_type="long",
        label="Long Rest",
        changes=changes,
        adjustments={"current_hp": 9, "resources": {"sorcery-points": 4}},
    )

    def load(*args):
        events.append(("load", args))
        return record

    def access(*args):
        events.append(("access", args))
        return True

    def preview_rest(*args):
        events.append(("preview", args))
        if preview_error is not None:
            raise preview_error
        return preview

    service = SimpleNamespace(preview_rest=preview_rest)

    def get_service(*args):
        events.append(("service", args))
        return service

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "json-error"

    return {
        "load_character_record": load,
        "has_session_mode_access": access,
        "get_character_state_service": get_service,
        "json_error": error,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterRestPreviewApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_rest_preview_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_rest_preview"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_rest_preview"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_rest_preview_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    assert sum(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "dependencies"
        and node.attr == "api_login_required"
        for node in ast.walk(registrar)
    ) == 1
    assert not any(
        isinstance(node, ast.Name)
        and node.id == "api_campaign_scope_access_required"
        for node in ast.walk(registrar)
    )

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 224
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 236
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
    assert len(api_route_decorators) == 56

    assert isinstance(register_api.body[235], ast.Expr)
    assert register_api.body[235].value.func.id == (
        "register_character_portrait_mutation_api_routes"
    )
    assert isinstance(register_api.body[236], ast.Expr)
    assert register_api.body[236].value.func.id == (
        "register_character_rest_preview_api_route"
    )
    assert isinstance(register_api.body[237], ast.FunctionDef)
    assert register_api.body[237].name == "run_character_mutation"

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[236])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterRestPreviewApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert isinstance(by_name["has_session_mode_access"], ast.Lambda)
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in DEPENDENCY_ORDER
        if name != "has_session_mode_access"
    )


def test_moved_handler_keeps_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_rest_preview_api_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_rest_preview"
    )
    api_at_base = ast.parse(
        __import__("subprocess").check_output(
            [
                "git",
                "show",
                "7eb3d9a210ca39a10aa66bcd6edf0123e4cd4682:player_wiki/api.py",
            ],
            text=True,
        )
    )
    register_api = next(
        node
        for node in api_at_base.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    original = next(
        node
        for node in register_api.body
        if isinstance(node, ast.FunctionDef) and node.name == "character_rest_preview"
    )
    assert _canonical_handler(moved) == _canonical_handler(original)


def test_route_preserves_endpoint_methods_wrapper_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_portrait_delete") < endpoints.index(ENDPOINT)
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "rest-preview/<rest_type>"
    )
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_rest_preview"
    )


def test_handler_preserves_load_access_service_preview_and_serialization_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="GET"):
        response = _handler(app)("linden-pass", "arden-march", "long")
    assert [event[0] for event in events] == ["load", "access", "service", "preview"]
    assert events[-1][1][1] == "long"
    assert response.get_json() == {
        "ok": True,
        "preview": {
            "rest_type": "long",
            "label": "Long Rest",
            "changes": [
                {"label": "Current HP", "from_value": 3, "to_value": 9},
                {"label": "Sorcery Points", "from_value": 0, "to_value": 4},
            ],
            "adjustments": {
                "current_hp": 9,
                "resources": {"sorcery-points": 4},
            },
        },
    }


def test_denied_access_returns_exact_forbidden_before_service(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def denied(*args):
        events.append(("access", args))
        return False

    replacements["has_session_mode_access"] = denied
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="GET"):
        assert _handler(app)("linden-pass", "arden-march", "long") == "json-error"
    assert [event[0] for event in events] == ["load", "access", "json_error"]
    assert events[-1][1] == (
        "You do not have permission to use rest actions for this character.",
        403,
    )
    assert events[-1][2] == {"code": "forbidden"}


def test_value_error_maps_to_exact_validation_error(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, preview_error=ValueError("unsupported rest")),
    )
    with app.test_request_context(ROUTE_PATH, method="GET"):
        assert _handler(app)("linden-pass", "arden-march", "mystery") == "json-error"
    assert [event[0] for event in events] == [
        "load",
        "access",
        "service",
        "preview",
        "json_error",
    ]
    assert events[-1][1] == ("unsupported rest", 400)
    assert events[-1][2] == {"code": "validation_error"}


def test_unrelated_preview_fault_propagates(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, preview_error=RuntimeError("preview fault")),
    )
    with app.test_request_context(ROUTE_PATH, method="GET"):
        with pytest.raises(RuntimeError, match="preview fault"):
            _handler(app)("linden-pass", "arden-march", "long")
