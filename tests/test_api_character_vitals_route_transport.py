from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.character_vitals_api_routes as route_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "848a9894204ada9989326f4c2d9b2a6ea2270a79"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/session/vitals"
ENDPOINT = "api.character_vitals_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_mutation",
    "get_character_state_service",
    "optional_json_hit_dice_current",
]
PAYLOAD_KEYS_BEFORE_HIT_DICE = [
    "expected_revision",
    "current_hp",
    "temp_hp",
    "current_stance",
    "temp_stance",
    "current_jing",
    "current_qi",
    "current_shen",
    "current_yin",
    "current_yang",
    "current_dao",
]
PAYLOAD_KEYS_AFTER_HIT_DICE = ["hp_delta", "temp_hp_delta", "clear_temp_hp"]


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


def _dependencies(events: list[tuple], *, payload=None, helper_error=None, service_error=None):
    record = SimpleNamespace(slug="arden-march")
    payload = payload or RecordingPayload(
        {
            "expected_revision": "17",
            "current_hp": 8,
            "temp_hp": 2,
            "current_stance": 6,
            "temp_stance": 1,
            "current_jing": 3,
            "current_qi": 4,
            "current_shen": 5,
            "current_yin": 6,
            "current_yang": 7,
            "current_dao": 8,
            "hp_delta": -2,
            "temp_hp_delta": 1,
            "clear_temp_hp": "yes",
        },
        events,
    )

    def update_vitals(*args, **kwargs):
        events.append(("save", args, kwargs))
        if service_error is not None:
            raise service_error
        return "saved-state"

    service = SimpleNamespace(update_vitals=update_vitals)

    def get_service(*args):
        events.append(("service", args))
        return service

    def hit_dice(source):
        events.append(("hit_dice", (source,)))
        if helper_error is not None:
            raise helper_error
        return {8: 2, 10: 1}

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,)))
        return "mutation-result"

    return {
        "run_character_mutation": runner,
        "get_character_state_service": get_service,
        "optional_json_hit_dice_current": hit_dice,
    }


def test_transport_has_exact_dependency_registration_and_late_binding_shape() -> None:
    assert [field.name for field in fields(route_module.CharacterVitalsApiDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_vitals_api_routes.py").read_text(encoding="utf-8")
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_vitals_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_vitals_update"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_vitals_api_route"
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
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 225
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 237
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
    assert len(api_route_decorators) == 57

    assert isinstance(register_api.body[240], ast.Expr)
    assert register_api.body[240].value.func.id == "register_character_sheet_edit_api_route"
    assert isinstance(register_api.body[241], ast.Expr)
    assert register_api.body[241].value.func.id == "register_character_vitals_api_route"
    assert isinstance(register_api.body[242], ast.Expr)
    assert register_api.body[242].value.func.id == "register_character_resource_api_route"

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[241])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterVitalsApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER[:3])
    late_bound = by_name["optional_json_hit_dice_current"]
    assert isinstance(late_bound, ast.Lambda)
    assert isinstance(late_bound.body, ast.Call)
    assert isinstance(late_bound.body.func, ast.Name)
    assert late_bound.body.func.id == "optional_json_hit_dice_current"


def test_moved_handler_and_action_keep_canonical_ast_and_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_vitals_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_vitals_update"
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
    original = old_register.body[241]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_vitals_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {241, 242, 243, 244, 245, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_sheet_edit_update") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_resource_update")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals"
    )
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_vitals_update"
    )


def test_handler_preserves_service_payload_helper_and_save_evaluation_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "service",
        *["payload_get"] * len(PAYLOAD_KEYS_BEFORE_HIT_DICE),
        "hit_dice",
        *["payload_get"] * len(PAYLOAD_KEYS_AFTER_HIT_DICE),
        "save",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == (
        PAYLOAD_KEYS_BEFORE_HIT_DICE + PAYLOAD_KEYS_AFTER_HIT_DICE
    )
    save = next(event for event in events if event[0] == "save")
    assert save[2] == {
        "expected_revision": 17,
        "current_hp": 8,
        "temp_hp": 2,
        "current_stance": 6,
        "temp_stance": 1,
        "current_jing": 3,
        "current_qi": 4,
        "current_shen": 5,
        "current_yin": 6,
        "current_yang": 7,
        "current_dao": 8,
        "hit_dice_current": {8: 2, 10: 1},
        "hp_delta": -2,
        "temp_hp_delta": 1,
        "clear_temp_hp": True,
        "updated_by_user_id": 42,
    }


def test_missing_values_forward_none_and_false_without_reordering(app, monkeypatch):
    events: list[tuple] = []
    payload = RecordingPayload({"expected_revision": 4}, events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    save = next(event for event in events if event[0] == "save")
    assert save[2]["expected_revision"] == 4
    assert save[2]["hit_dice_current"] == {8: 2, 10: 1}
    assert save[2]["clear_temp_hp"] is False
    assert all(
        save[2][key] is None
        for key in PAYLOAD_KEYS_BEFORE_HIT_DICE[1:] + PAYLOAD_KEYS_AFTER_HIT_DICE[:2]
    )


def test_conversion_helper_and_service_faults_remain_uncaught_by_transport(app, monkeypatch):
    events: list[tuple] = []
    payload = RecordingPayload({"expected_revision": "not-an-int"}, events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["runner", "service", "payload_get"]
    assert not any(event[0] in {"hit_dice", "save"} for event in events)

    events = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, helper_error=RuntimeError("helper fault")),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match="helper fault"):
            _handler(app)("linden-pass", "arden-march")
    assert [event[1] for event in events if event[0] == "payload_get"] == (
        PAYLOAD_KEYS_BEFORE_HIT_DICE
    )
    assert not any(event[0] == "save" for event in events)

    events = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, service_error=RuntimeError("service fault")),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match="service fault"):
            _handler(app)("linden-pass", "arden-march")
