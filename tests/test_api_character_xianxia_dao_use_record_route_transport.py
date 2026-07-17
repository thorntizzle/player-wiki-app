from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
import player_wiki.character_xianxia_dao_use_record_api_routes as route_module
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "b9fdebbfea213d7afdb7d16838a0d5b89ced7efb"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/xianxia-dao-immolating-use-records"
)
ENDPOINT = "api.character_xianxia_dao_immolating_use_record"
DEPENDENCY_ORDER = [
    "api_login_required",
    "can_manage_campaign_session",
    "json_error",
    "run_character_definition_mutation",
    "ensure_xianxia_character_definition",
    "required_json_int",
    "json_payload_value",
    "managed_character_import_metadata",
    "record_xianxia_dao_immolating_use_definition",
]


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


class RecordingPayload:
    def __init__(self, values, events):
        self.values = values
        self.events = events

    def get(self, key):
        self.events.append(("payload_get", key))
        return self.values.get(key)

    def __contains__(self, key):
        self.events.append(("payload_contains", key))
        return key in self.values


def _dependencies(events: list[tuple], *, system="xianxia"):
    definition = SimpleNamespace(system=system, character_slug="arden-march")
    import_metadata = SimpleNamespace(name="metadata")
    record = SimpleNamespace(definition=definition, import_metadata=import_metadata)
    payload = RecordingPayload(
        {
            "expected_revision": 17,
            "use_record_index": 2,
            "notes": "Spent during the bridge duel.",
        },
        events,
    )
    updated_definition = SimpleNamespace(system="xianxia", used=True)

    def manager(*args, **kwargs):
        events.append(("manager", args, kwargs))
        return True

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "forbidden-result"

    def ensure(record_arg, message):
        events.append(("ensure", (record_arg, message), {}))
        if record_arg.definition.system != "xianxia":
            raise ValueError(message)

    def required_int(submitted_payload, *keys, field_label):
        events.append(("required_int", keys, {"field_label": field_label}))
        for key in keys:
            if key in submitted_payload:
                return int(submitted_payload.get(key))
        raise ValueError(f"{field_label} is required.")

    def json_value(submitted_payload, *keys):
        events.append(("json_value", keys, {}))
        for key in keys:
            if key in submitted_payload:
                return submitted_payload.get(key)
        return None

    def record_definition(*args, **kwargs):
        events.append(("record_definition", args, kwargs))
        return SimpleNamespace(definition=updated_definition)

    def metadata(campaign_slug, record_arg):
        events.append(("metadata", (campaign_slug, record_arg), {}))
        return import_metadata

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "can_manage_campaign_session": manager,
        "json_error": error,
        "run_character_definition_mutation": runner,
        "ensure_xianxia_character_definition": ensure,
        "required_json_int": required_int,
        "json_payload_value": json_value,
        "managed_character_import_metadata": metadata,
        "record_xianxia_dao_immolating_use_definition": record_definition,
    }


def test_transport_has_exact_dependencies_registration_wrapper_and_source_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterXianxiaDaoUseRecordApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_xianxia_dao_use_record_api_routes.py").read_text()
    )
    api_tree = ast.parse((source_root / "api.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_record"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_record"
        for node in ast.walk(api_tree)
    )
    assert not any(
        isinstance(node, ast.Name)
        and node.id in {"api_campaign_scope_access_required", "current_app", "request"}
        for node in ast.walk(route_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_xianxia_dao_use_record_api_route"
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
        keyword.value for keyword in registrations[0].keywords if keyword.arg == "view_func"
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
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 220
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 230
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
    assert len(api_route_decorators) == 52

    assert register_api.body[254].value.func.id == (
        "register_character_xianxia_dao_use_request_api_route"
    )
    assert register_api.body[255].value.func.id == (
        "register_character_xianxia_dao_use_record_api_route"
    )
    assert register_api.body[256].value.func.id == (
        "register_character_xianxia_inventory_add_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[255])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterXianxiaDaoUseRecordApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    for name in DEPENDENCY_ORDER:
        if name in {
            "can_manage_campaign_session",
            "record_xianxia_dao_immolating_use_definition",
        }:
            assert isinstance(by_name[name], ast.Lambda)
        else:
            assert isinstance(by_name[name], ast.Name)


def test_moved_handler_keeps_canonical_ast_and_all_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_xianxia_dao_use_record_api_routes.py"
        ).read_text()
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_record"
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/api.py"], text=True
        )
    )
    new_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "api.py").read_text())
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
    original = old_register.body[255]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_xianxia_dao_immolating_use_record"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {162, 163, 255}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(app, client):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/xianxia-dao-immolating-use-records"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert client.post(ROUTE_PATH).status_code == 401
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_xianxia_dao_immolating_use_record"
    )
    assert endpoints.index("api.character_xianxia_dao_immolating_use_request") < (
        endpoints.index(ENDPOINT)
    ) < endpoints.index("api.character_xianxia_inventory_add")


def test_manager_denial_precedes_runner_and_every_downstream_dependency(app, monkeypatch):
    events: list[tuple] = []

    def manager(*args, **kwargs):
        events.append(("manager", args, kwargs))
        return False

    def error(*args, **kwargs):
        events.append(("json_error", args, kwargs))
        return "forbidden-result"

    def unexpected(*args, **kwargs):
        events.append(("downstream", args, kwargs))
        raise AssertionError("manager denial reached downstream work")

    _install_dependencies(
        app,
        monkeypatch,
        can_manage_campaign_session=manager,
        json_error=error,
        run_character_definition_mutation=unexpected,
        ensure_xianxia_character_definition=unexpected,
        required_json_int=unexpected,
        json_payload_value=unexpected,
        managed_character_import_metadata=unexpected,
        record_xianxia_dao_immolating_use_definition=unexpected,
    )
    with app.test_request_context(
        ROUTE_PATH.replace("arden-march", "..%5Cvictim"),
        method="POST",
        json={"use_record_index": 0},
    ):
        assert _handler(app)("linden-pass", "..\\victim") == "forbidden-result"
    assert [event[0] for event in events] == ["manager", "json_error"]
    assert events[1][1] == (
        "You do not have permission to record Dao Immolating use for this character.",
        403,
    )
    assert events[1][2] == {"code": "forbidden"}


def test_handler_preserves_payload_record_metadata_and_runner_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "manager",
        "runner",
        "ensure",
        "required_int",
        "payload_contains",
        "payload_get",
        "json_value",
        "payload_contains",
        "payload_get",
        "record_definition",
        "metadata",
        "action_result",
    ]
    record_event = next(event for event in events if event[0] == "record_definition")
    assert record_event[2] == {
        "use_record_index": 2,
        "notes": "Spent during the bridge duel.",
    }
    result = next(event for event in events if event[0] == "action_result")[1][0]
    assert result[0].used is True
    assert result[1].name == "metadata"
    assert result[2] == {}


def test_xianxia_gate_precedes_payload_helpers_record_and_metadata(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events, system="dnd5e"))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(ValueError, match="only available for Xianxia"):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["manager", "runner", "ensure"]


def test_forwarded_manager_and_record_helper_remain_late_substitutable(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)
    replacements.pop("can_manage_campaign_session")
    replacements.pop("record_xianxia_dao_immolating_use_definition")
    _install_dependencies(app, monkeypatch, **replacements)

    monkeypatch.setattr(
        api_module,
        "can_manage_campaign_session",
        lambda *args, **kwargs: events.append(("forwarded_manager", args, kwargs))
        or True,
    )

    def replacement(*args, **kwargs):
        events.append(("forwarded_record", args, kwargs))
        return SimpleNamespace(definition=SimpleNamespace(forwarded=True))

    monkeypatch.setattr(
        api_module,
        "record_xianxia_dao_immolating_use_definition",
        replacement,
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    assert [event[0] for event in events if event[0].startswith("forwarded_")] == [
        "forwarded_manager",
        "forwarded_record",
    ]


def test_nonmanager_api_denial_has_zero_runner_or_downstream_work(
    app, client, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    events: list[tuple] = []

    def manager(*args, **kwargs):
        events.append(("manager", args, kwargs))
        return False

    def unexpected(*args, **kwargs):
        events.append(("downstream", args, kwargs))
        raise AssertionError("nonmanager denial reached runner")

    _install_dependencies(
        app,
        monkeypatch,
        can_manage_campaign_session=manager,
        run_character_definition_mutation=unexpected,
    )
    token = issue_api_token(app, users["party"]["email"], label="p93-nonmanager")
    response = client.post(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0, "use_record_index": 0},
    )
    assert response.status_code == 403
    assert [event[0] for event in events] == ["manager"]


@pytest.mark.parametrize(
    "fault_stage",
    ("manager", "error", "runner", "ensure", "required", "json", "record", "metadata"),
)
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app,
    monkeypatch,
    fault_stage,
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    dependency_by_stage = {
        "manager": "can_manage_campaign_session",
        "error": "json_error",
        "runner": "run_character_definition_mutation",
        "ensure": "ensure_xianxia_character_definition",
        "required": "required_json_int",
        "json": "json_payload_value",
        "record": "record_xianxia_dao_immolating_use_definition",
        "metadata": "managed_character_import_metadata",
    }
    if fault_stage == "error":
        replacements["can_manage_campaign_session"] = lambda *args, **kwargs: False
    replacements[dependency_by_stage[fault_stage]] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march")
