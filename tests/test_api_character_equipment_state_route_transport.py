from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

import player_wiki.api as api_module
import player_wiki.character_equipment_state_api_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from player_wiki.route_contracts import build_manifest
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "85201efa486a993e1d9dbbc25e6c7ddeebad726d"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/equipment/quarterstaff-2"
)
ENDPOINT = "api.character_equipment_state_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "build_character_item_catalog",
    "run_character_definition_mutation",
    "build_shared_equipment_state_update_result",
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


def _dependencies(events: list[tuple], *, payload=None):
    record = SimpleNamespace(definition={"name": "Arden"})
    payload = payload or RecordingPayload(
        {
            "is_equipped": "0",
            "is_attuned": "",
            "weapon_wield_mode": "two-handed",
        },
        events,
    )

    def catalog(*args, **kwargs):
        events.append(("catalog", args, kwargs))
        return {"quarterstaff-2": {"name": "Quarterstaff"}}

    def shared(*args, **kwargs):
        events.append(("shared", args, kwargs))
        return "equipment-result"

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "build_character_item_catalog": catalog,
        "run_character_definition_mutation": runner,
        "build_shared_equipment_state_update_result": shared,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterEquipmentStateApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_equipment_state_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_equipment_state_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_equipment_state_update"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_equipment_state_api_route"
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
    assert not any(
        isinstance(node, ast.Name)
        and node.id
        in {
            "api_campaign_scope_access_required",
            "campaign_supports_dnd5e_character_spellcasting_tools",
        }
        for node in ast.walk(route_tree)
    )

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 221
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 231
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
    assert len(api_route_decorators) == 53

    assert isinstance(register_api.body[259], ast.Expr)
    assert register_api.body[259].value.func.id == (
        "register_character_xianxia_inventory_equipped_update_api_route"
    )
    assert isinstance(register_api.body[260], ast.Expr)
    assert register_api.body[260].value.func.id == (
        "register_character_equipment_state_api_route"
    )
    assert isinstance(register_api.body[261], ast.Expr)
    assert register_api.body[261].value.func.id == (
        "register_character_artificer_infusions_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[260])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterEquipmentStateApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in DEPENDENCY_ORDER[:3]
    )
    assert isinstance(by_name["build_shared_equipment_state_update_result"], ast.Lambda)


def test_moved_handler_keeps_canonical_ast_and_all_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_equipment_state_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_equipment_state_update"
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
    original = old_register.body[260]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_equipment_state_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {162, 253, 254, 255, 260, 261, 262, 263, 264, 265, 266}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(
    app, client
):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index(
        "api.character_xianxia_inventory_equipped_update"
    ) < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "api.character_artificer_infusions_update"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/equipment/<item_id>"
    )
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert client.patch(ROUTE_PATH).status_code == 401
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_equipment_state_update"
    )


@pytest.mark.parametrize(
    ("equipped", "attuned", "expected_equipped", "expected_attuned"),
    [
        ("0", "false", True, True),
        ("", 0, False, False),
        (None, None, False, False),
    ],
)
def test_handler_preserves_eager_catalog_dynamic_systems_and_payload_order(
    app,
    monkeypatch,
    equipped,
    attuned,
    expected_equipped,
    expected_attuned,
):
    events: list[tuple] = []
    payload = RecordingPayload(
        {
            "is_equipped": equipped,
            "is_attuned": attuned,
            "weapon_wield_mode": "off-hand",
        },
        events,
    )
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    systems_service = SimpleNamespace(name="p84-systems")
    monkeypatch.setitem(app.extensions, "systems_service", systems_service)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert (
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "catalog",
        "runner",
        "payload_get",
        "payload_get",
        "payload_get",
        "shared",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "is_equipped",
        "is_attuned",
        "weapon_wield_mode",
    ]
    shared = next(event for event in events if event[0] == "shared")
    assert shared[1][:3] == (
        "linden-pass",
        SimpleNamespace(definition={"name": "Arden"}),
        "quarterstaff-2",
    )
    assert shared[2] == {
        "item_catalog": {"quarterstaff-2": {"name": "Quarterstaff"}},
        "systems_service": systems_service,
        "values": {
            "is_equipped": expected_equipped,
            "is_attuned": expected_attuned,
            "weapon_wield_mode": "off-hand",
        },
    }


@pytest.mark.parametrize("fault_stage", ("catalog", "runner", "shared"))
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app, monkeypatch, fault_stage
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    replacements[
        {
            "catalog": "build_character_item_catalog",
            "runner": "run_character_definition_mutation",
            "shared": "build_shared_equipment_state_update_result",
        }[fault_stage]
    ] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")


def test_forwarded_shared_helper_remains_late_monkeypatchable(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)
    replacements["build_shared_equipment_state_update_result"] = (
        _dependencies_cell(app).cell_contents.build_shared_equipment_state_update_result
    )
    _install_dependencies(app, monkeypatch, **replacements)
    monkeypatch.setattr(
        api_module,
        "build_shared_equipment_state_update_result",
        lambda *args, **kwargs: events.append(("forwarded", args, kwargs)) or "ok",
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert (
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")
            == "mutation-result"
        )
    assert [event[0] for event in events] == [
        "catalog",
        "runner",
        "payload_get",
        "payload_get",
        "payload_get",
        "forwarded",
        "action_result",
    ]


def test_view_as_denial_precedes_handler_but_bearer_identity_wins(
    app, client, sign_in, users, monkeypatch
):
    events: list[tuple] = []

    def catalog(*args, **kwargs):
        events.append(("catalog", args, kwargs))
        return {}

    _install_dependencies(
        app,
        monkeypatch,
        build_character_item_catalog=catalog,
        run_character_definition_mutation=lambda *args, **kwargs: {"ok": True},
    )
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.patch(ROUTE_PATH).status_code == 403
    assert events == []

    token = issue_api_token(app, users["admin"]["email"], label="p84-bearer")
    response = client.patch(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["catalog"]


def test_p34_identity_mismatch_keeps_eager_catalog_but_stops_downstream_work(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p84-p34")
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["character_slug"] = "another-character"
    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False), encoding="utf-8"
    )
    events: list[tuple] = []

    def catalog(*args, **kwargs):
        events.append(("catalog", args, kwargs))
        return {}

    def unexpected(*args, **kwargs):
        raise AssertionError("identity mismatch reached state or equipment action work")

    _install_dependencies(
        app,
        monkeypatch,
        build_character_item_catalog=catalog,
        build_shared_equipment_state_update_result=unexpected,
    )
    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    response = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0, "is_equipped": True},
    )
    assert response.status_code == 404
    assert [event[0] for event in events] == ["catalog"]


def test_definition_runner_preserves_state_before_yaml_partial_commit(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p84-partial")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None

    def fail_yaml(*args, **kwargs):
        raise RuntimeError("p84 yaml fault")

    monkeypatch.setattr(api_module, "write_yaml", fail_yaml)
    with pytest.raises(RuntimeError, match="p84 yaml fault"):
        client.patch(
            ROUTE_PATH,
            headers=api_headers(token),
            json={
                "expected_revision": before.state_record.revision,
                "weapon_wield_mode": "two-handed",
            },
        )
    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == before.state_record.revision + 1


def test_manifest_metadata_remains_dnd_characters_without_runtime_scope_change():
    entries = [
        entry
        for entry in build_manifest()["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "PATCH"
    ]
    assert entries == [
        {
            **entries[0],
            "campaign_scope": "characters",
            "system_restriction": "dnd5e_only",
        }
    ]
