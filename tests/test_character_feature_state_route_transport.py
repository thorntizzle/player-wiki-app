from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import NotFound

import player_wiki.character_feature_state_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "feature-states/arcane_armor"
)
ENDPOINT = "character_feature_state_update"


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
    record = SimpleNamespace(definition={"name": "Arden"}, state_record={})

    def update_feature_state(*args, **kwargs):
        events.append(("update", args, kwargs))
        return "updated-state"

    service = SimpleNamespace(update_feature_state=update_feature_state)

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record, 17, 42)
        events.append(("action_result", result, {}))
        return "mutation-result"

    return {
        "run_character_state_mutation": runner,
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "run_character_state_mutation",
        "get_character_state_service",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterFeatureStateRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_feature_state_routes.py").read_text(
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
        and node.name == "register_character_feature_state_route"
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
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 212
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 227
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_equipment_state_route",
            "register_character_feature_state_route",
            "register_character_equipment_remove_route",
        }
    }
    assert (
        calls["register_character_equipment_state_route"],
        calls["register_character_feature_state_route"],
        calls["register_character_equipment_remove_route"],
    ) == (275, 276, 277)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[276])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterFeatureStateRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_equipment_state_update") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("character_equipment_remove")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "feature-states/<feature_key>"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_runner_service_form_and_update_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))

    class RecordingForm:
        def get(self, key):
            events.append(("form", (key,), {}))
            return "1"

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
    ):
        assert (
            _handler(app)("linden-pass", "arden-march", "arcane_armor")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "runner",
        "service",
        "form",
        "update",
        "action_result",
    ]
    runner = events[0]
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "character-equipment-state"
    assert runner[2]["success_message"] == "Feature state updated."
    assert events[2][1] == ("enabled",)
    update = events[3]
    assert update[1][0].definition == {"name": "Arden"}
    assert update[1][1] == "arcane_armor"
    assert update[2] == {
        "expected_revision": 17,
        "enabled": True,
        "updated_by_user_id": 42,
    }


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        (("1", "0"), True),
        (("0", "1"), False),
        (("true",), False),
        (("", "1"), False),
        ((), False),
    ),
)
def test_enabled_uses_only_the_exact_first_repeated_form_value(
    app, monkeypatch, values, expected
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    form = MultiDict(("enabled", value) for value in values)
    with app.test_request_context(ROUTE_PATH, method="POST", data=form):
        assert (
            _handler(app)("linden-pass", "arden-march", "arcane_armor")
            == "mutation-result"
        )
    update = next(event for event in events if event[0] == "update")
    assert update[2]["enabled"] is expected


@pytest.mark.parametrize(
    "feature_key",
    ("arcane_armor", "arcane-armor", "Arcane Armor", "unknown"),
)
def test_feature_key_is_forwarded_unchanged_to_shared_state_service(
    app, monkeypatch, feature_key
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    with app.test_request_context(ROUTE_PATH, method="POST", data={"enabled": "1"}):
        assert _handler(app)("linden-pass", "arden-march", feature_key) == "mutation-result"
    update = next(event for event in events if event[0] == "update")
    assert update[1][1] == feature_key


def test_scope_denial_performs_no_runner_or_service_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached feature state handler")

    _install_dependencies(
        app,
        monkeypatch,
        run_character_state_mutation=unexpected,
        get_character_state_service=unexpected,
    )
    assert client.post(ROUTE_PATH).status_code == 404


def test_view_as_denial_and_bearer_precedence_preserve_global_envelope(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_character_state_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p58-feature-state")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_p34_failure_occurs_in_captured_runner_before_service_work(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        raise NotFound()

    dependencies["run_character_state_mutation"] = invalid_runner
    _install_dependencies(app, monkeypatch, **dependencies)
    malicious_path = ROUTE_PATH.replace("arden-march", "..\\victim")
    with app.test_request_context(malicious_path, method="POST"):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\victim", "arcane_armor")
    assert [event[0] for event in events] == ["runner"]


@pytest.mark.parametrize("fault_stage", ("runner", "service", "update"))
def test_faults_propagate_at_every_transport_stage(
    app, monkeypatch, fault_stage
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        dependencies["run_character_state_mutation"] = fault
    elif fault_stage == "service":
        dependencies["get_character_state_service"] = fault
    else:
        dependencies["get_character_state_service"] = lambda: SimpleNamespace(
            update_feature_state=fault
        )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "arcane_armor")
