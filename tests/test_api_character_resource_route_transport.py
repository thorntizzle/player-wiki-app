from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.character_resource_api_routes as route_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "b534d5a0582a87f02835e4334a4d1fb5205baca2"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/resources/sorcery-points"
)
ENDPOINT = "api.character_resource_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_mutation",
    "get_character_state_service",
]
PAYLOAD_KEYS = ["expected_revision", "current", "delta"]


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


class RecordingPayload:
    def __init__(self, values, events):
        self.values = values
        self.events = events

    def get(self, key):
        self.events.append(("payload_get", key))
        return self.values.get(key)


def _dependencies(events: list[tuple], *, payload=None, service_error=None):
    record = SimpleNamespace(slug="arden-march")
    payload = payload or RecordingPayload(
        {"expected_revision": "17", "current": 3, "delta": -1}, events
    )

    def update_resource(*args, **kwargs):
        events.append(("save", args, kwargs))
        if service_error is not None:
            raise service_error
        return "saved-state"

    service = SimpleNamespace(update_resource=update_resource)

    def get_service(*args):
        events.append(("service", args))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,)))
        return "mutation-result"

    return {
        "run_character_mutation": runner,
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [field.name for field in fields(route_module.CharacterResourceApiDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_resource_api_routes.py").read_text(encoding="utf-8")
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_resource_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_resource_update"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_resource_api_route"
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
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 218
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 228
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
    assert len(api_route_decorators) == 50

    assert isinstance(register_api.body[241], ast.Expr)
    assert register_api.body[241].value.func.id == "register_character_vitals_api_route"
    assert isinstance(register_api.body[242], ast.Expr)
    assert register_api.body[242].value.func.id == "register_character_resource_api_route"
    assert isinstance(register_api.body[243], ast.Expr)
    assert register_api.body[243].value.func.id == (
        "register_character_spell_slots_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[242])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterResourceApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER)


def test_moved_handler_and_action_keep_canonical_ast_and_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_resource_api_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_resource_update"
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
    original = old_register.body[242]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_resource_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {162, 163, 164, 165, 242, 243, 244, 245, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_vitals_update") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_spell_slots_update")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/"
        "<resource_id>"
    )
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_resource_update"
    )


def test_handler_preserves_runner_service_resource_and_payload_evaluation_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)(
            "linden-pass", "arden-march", "sorcery-points"
        ) == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "service",
        "payload_get",
        "payload_get",
        "payload_get",
        "save",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == PAYLOAD_KEYS
    runner = events[0]
    assert runner[1][:2] == ("linden-pass", "arden-march")
    save = next(event for event in events if event[0] == "save")
    assert save[1][:2] == (
        SimpleNamespace(slug="arden-march"),
        "sorcery-points",
    )
    assert save[2] == {
        "expected_revision": 17,
        "current": 3,
        "delta": -1,
        "updated_by_user_id": 42,
    }


def test_missing_values_forward_none_without_reordering(app, monkeypatch):
    events: list[tuple] = []
    payload = RecordingPayload({"expected_revision": 4}, events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)(
            "linden-pass", "arden-march", "wild-die"
        ) == "mutation-result"
    assert [event[1] for event in events if event[0] == "payload_get"] == PAYLOAD_KEYS
    save = next(event for event in events if event[0] == "save")
    assert save[1][1] == "wild-die"
    assert save[2]["expected_revision"] == 4
    assert save[2]["current"] is None
    assert save[2]["delta"] is None


def test_conversion_and_service_faults_remain_uncaught_by_transport(app, monkeypatch):
    events: list[tuple] = []
    payload = RecordingPayload({"expected_revision": "not-an-int"}, events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march", "sorcery-points")
    assert [event[0] for event in events] == ["runner", "service", "payload_get"]
    assert not any(event[0] == "save" for event in events)

    events = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, service_error=RuntimeError("service fault")),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match="service fault"):
            _handler(app)("linden-pass", "arden-march", "sorcery-points")
