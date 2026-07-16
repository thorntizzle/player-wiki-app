from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import NotFound

import player_wiki.app as app_module
import player_wiki.character_equipment_remove_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/equipment/manual-1/remove"
)
ENDPOINT = "character_equipment_remove"


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


def _fixtures(events: list[tuple]):
    record = SimpleNamespace(definition={"name": "Arden"}, import_metadata={"v": 1})

    def catalog(*args, **kwargs):
        events.append(("catalog", args, kwargs))
        return {"manual-1": {"name": "Rope"}}

    def systems(*args, **kwargs):
        events.append(("systems", args, kwargs))
        return "systems-service"

    def apply(*args, **kwargs):
        events.append(("apply", args, kwargs))
        return "edit-result"

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "build_character_item_catalog": catalog,
        "get_systems_service": systems,
        "run_character_definition_mutation": runner,
        "apply_equipment_catalog_edit": apply,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "build_character_item_catalog",
        "get_systems_service",
        "run_character_definition_mutation",
        "apply_equipment_catalog_edit",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterEquipmentRemoveRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_equipment_remove_routes.py").read_text(
            encoding="utf-8"
        )
    )
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
        for node in ast.walk(app_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_equipment_remove_route"
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
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "campaign_scope_access_required"
        for node in ast.walk(registrar)
    ) == 1

    create_app = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    assert len(create_app.body) == 298
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 210
    assert (
        sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 224
    )
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_feature_state_route",
            "register_character_equipment_remove_route",
        }
    }
    dao_index = next(
        index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_character_xianxia_dao_use_request_route"
    )
    assert (
        calls["register_character_feature_state_route"],
        calls["register_character_equipment_remove_route"],
        dao_index,
    ) == (276, 277, 278)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[277])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterEquipmentRemoveRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:3])
    assert isinstance(by_name["apply_equipment_catalog_edit"], ast.Lambda)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_feature_state_update") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_xianxia_dao_immolating_use_request"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/<item_id>/remove"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_eager_catalog_runner_systems_apply_order_and_contract(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", " manual-1 ")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "catalog",
        "runner",
        "systems",
        "apply",
        "action_result",
    ]
    assert events[0][1] == ("linden-pass",)
    runner = events[1]
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "character-inventory-manager"
    assert runner[2]["success_message"] == "Inventory item removed."
    apply = events[3]
    assert apply[1][:3] == (
        "linden-pass",
        {"name": "Arden"},
        {"v": 1},
    )
    assert apply[2] == {
        "item_catalog": {"manual-1": {"name": "Rope"}},
        "systems_service": "systems-service",
        "remove_item_id": " manual-1 ",
    }


@pytest.mark.parametrize("item_id", ("manual-1", " manual-1 ", "", "unknown"))
def test_item_id_is_forwarded_raw_to_shared_equipment_editor(
    app, monkeypatch, item_id
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march", item_id) == "mutation-result"
    apply = next(event for event in events if event[0] == "apply")
    assert apply[2]["remove_item_id"] == item_id


def test_scope_denial_performs_no_eager_catalog_or_runner_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached equipment remove handler")

    _install_dependencies(
        app,
        monkeypatch,
        build_character_item_catalog=unexpected,
        run_character_definition_mutation=unexpected,
    )
    assert client.post(ROUTE_PATH).status_code == 404


def test_view_as_denial_and_bearer_precedence_preserve_global_envelope(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_character_definition_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p59-remove")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == ["catalog", "runner"]


def test_p34_failure_occurs_after_eager_catalog_before_systems_or_apply(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        raise NotFound()

    dependencies["run_character_definition_mutation"] = invalid_runner
    _install_dependencies(app, monkeypatch, **dependencies)
    malicious_path = ROUTE_PATH.replace("arden-march", "..\\victim")
    with app.test_request_context(malicious_path, method="POST"):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\victim", "manual-1")
    assert [event[0] for event in events] == ["catalog", "runner"]


@pytest.mark.parametrize("fault_stage", ("catalog", "runner", "systems", "apply"))
def test_faults_propagate_at_every_transport_stage(app, monkeypatch, fault_stage):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    key = {
        "catalog": "build_character_item_catalog",
        "runner": "run_character_definition_mutation",
        "systems": "get_systems_service",
        "apply": "apply_equipment_catalog_edit",
    }[fault_stage]
    dependencies[key] = fault
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "manual-1")


def test_forwarded_apply_helper_remains_late_monkeypatchable(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    original = freevars["dependencies"].cell_contents
    dependencies["apply_equipment_catalog_edit"] = original.apply_equipment_catalog_edit
    _install_dependencies(app, monkeypatch, **dependencies)
    monkeypatch.setattr(
        app_module,
        "apply_equipment_catalog_edit",
        lambda *args, **kwargs: events.append(("forwarded", args, kwargs)) or "ok",
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "manual-1")
            == "mutation-result"
        )
    assert any(event[0] == "forwarded" for event in events)
