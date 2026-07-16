from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import NotFound

import player_wiki.app as app_module
import player_wiki.character_equipment_state_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "equipment/quarterstaff-2/state"
)
ENDPOINT = "character_equipment_state_update"


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
    record = SimpleNamespace(definition={"name": "Arden"}, import_metadata={})
    systems_service = SimpleNamespace(name="systems")
    result = ({"definition": True}, {"managed": True}, {}, {"quarterstaff-2": {}})

    def event(name, value=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return value

        return invoke

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        action_result = kwargs["action"](record)
        events.append(("action_result", action_result, {}))
        return "mutation-result"

    return {
        "build_character_item_catalog": event("catalog", {"items": True}),
        "get_systems_service": event("systems", systems_service),
        "build_equipment_state_form_values": event(
            "values",
            {
                "is_equipped": True,
                "is_attuned": False,
                "weapon_wield_mode": "two-handed",
            },
        ),
        "run_character_definition_mutation": runner,
        "build_shared_equipment_state_update_result": event("shared", result),
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "build_character_item_catalog",
        "get_systems_service",
        "build_equipment_state_form_values",
        "run_character_definition_mutation",
        "build_shared_equipment_state_update_result",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterEquipmentStateRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_equipment_state_routes.py").read_text(
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
        and node.name == "register_character_equipment_state_route"
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
    assert len(create_app.body) == 295
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 200
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 212
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_equipment_definition_routes",
            "register_character_equipment_state_route",
            "register_character_feature_state_route",
        }
    }
    assert (
        calls["register_character_equipment_definition_routes"],
        calls["register_character_equipment_state_route"],
        calls["register_character_feature_state_route"],
    ) == (274, 275, 276)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[275])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterEquipmentStateRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:4])
    assert isinstance(by_name["build_shared_equipment_state_update_result"], ast.Lambda)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_equipment_update") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_feature_state_update"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/<item_id>/state"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_eager_catalog_runner_and_action_order(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "catalog",
        "runner",
        "systems",
        "values",
        "shared",
        "action_result",
    ]
    runner = events[1]
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "character-equipment-state"
    assert runner[2]["success_message"] == "Equipment state updated."
    shared = events[4]
    assert shared[1][0] == "linden-pass"
    assert shared[1][1].definition == {"name": "Arden"}
    assert shared[1][2] == "quarterstaff-2"
    assert shared[2] == {
        "item_catalog": {"items": True},
        "systems_service": SimpleNamespace(name="systems"),
        "values": {
            "is_equipped": True,
            "is_attuned": False,
            "weapon_wield_mode": "two-handed",
        },
    }


def test_original_form_helper_preserves_first_repeated_and_checkbox_truthiness(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    original = freevars["dependencies"].cell_contents
    dependencies["build_equipment_state_form_values"] = (
        original.build_equipment_state_form_values
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    form = MultiDict(
        (
            ("is_equipped", "0"),
            ("is_equipped", ""),
            ("is_attuned", ""),
            ("is_attuned", "1"),
            ("weapon_wield_mode", "off-hand"),
            ("weapon_wield_mode", "two-handed"),
        )
    )
    with app.test_request_context(ROUTE_PATH, method="POST", data=form):
        assert (
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")
            == "mutation-result"
        )
    shared = next(event for event in events if event[0] == "shared")
    assert shared[2]["values"] == {
        "is_equipped": True,
        "is_attuned": False,
        "weapon_wield_mode": "off-hand",
    }


def test_scope_denial_performs_no_eager_catalog_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached equipment state handler")

    _install_dependencies(
        app,
        monkeypatch,
        build_character_item_catalog=unexpected,
    )
    assert client.post(ROUTE_PATH).status_code == 404


def test_view_as_denial_and_bearer_precedence_preserve_global_envelope(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_character_definition_mutation"] = lambda *args, **kwargs: "ok"
    _install_dependencies(app, monkeypatch, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p57-equipment-state")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == ["catalog"]


def test_p34_failure_occurs_after_eager_catalog_before_action(app, monkeypatch):
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
            _handler(app)("linden-pass", "..\\victim", "quarterstaff-2")
    assert [event[0] for event in events] == ["catalog", "runner"]


@pytest.mark.parametrize(
    "fault_stage",
    ("catalog", "runner", "systems", "values", "shared"),
)
def test_faults_propagate_at_every_transport_stage(app, monkeypatch, fault_stage):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    key = {
        "catalog": "build_character_item_catalog",
        "runner": "run_character_definition_mutation",
        "systems": "get_systems_service",
        "values": "build_equipment_state_form_values",
        "shared": "build_shared_equipment_state_update_result",
    }[fault_stage]
    dependencies[key] = fault
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")


def test_forwarded_shared_helper_remains_late_monkeypatchable(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    original = freevars["dependencies"].cell_contents
    dependencies["build_shared_equipment_state_update_result"] = (
        original.build_shared_equipment_state_update_result
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    monkeypatch.setattr(
        app_module,
        "build_shared_equipment_state_update_result",
        lambda *args, **kwargs: events.append(("forwarded", args, kwargs)) or "ok",
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "quarterstaff-2")
            == "mutation-result"
        )
    assert [event[0] for event in events] == [
        "catalog",
        "runner",
        "systems",
        "values",
        "forwarded",
        "action_result",
    ]
