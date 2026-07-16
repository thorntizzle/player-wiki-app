from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import NotFound

import player_wiki.character_session_resource_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "session/resources/sorcery-points"
)
ENDPOINT = "character_session_resource"


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

    def update_resource(*args, **kwargs):
        events.append(("update", args, kwargs))
        return "updated-state"

    service = SimpleNamespace(update_resource=update_resource)

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record, 17, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "run_session_mutation": runner,
        "get_character_state_service": get_service,
    }


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


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = ["run_session_mutation", "get_character_state_service"]
    assert [
        field.name
        for field in fields(route_module.CharacterSessionResourceRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_resource_routes.py").read_text(
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
        and node.name == "register_character_session_resource_route"
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
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 201
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 213
    route_decorators = [
        decorator
        for node in ast.walk(create_app)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "app"
        and decorator.func.attr in {"get", "post"}
    ]
    assert len(route_decorators) == 31

    assert isinstance(create_app.body[283], ast.Expr)
    assert isinstance(create_app.body[283].value, ast.Call)
    assert isinstance(create_app.body[283].value.func, ast.Name)
    assert (
        create_app.body[283].value.func.id
        == "register_character_session_xianxia_active_state_route"
    )
    assert isinstance(create_app.body[284], ast.FunctionDef)
    assert create_app.body[284].name == "_xianxia_inventory_item_payload_from_form"
    assert isinstance(create_app.body[285], ast.Expr)
    assert isinstance(create_app.body[285].value, ast.Call)
    assert isinstance(create_app.body[285].value.func, ast.Name)
    assert (
        create_app.body[285].value.func.id
        == "register_character_session_resource_route"
    )
    assert isinstance(create_app.body[286], ast.Expr)
    assert isinstance(create_app.body[286].value, ast.Call)
    assert isinstance(create_app.body[286].value.func, ast.Name)
    assert (
        create_app.body[286].value.func.id
        == "register_character_session_spell_slots_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[285])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionResourceRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order)


def test_moved_handler_and_lambda_keep_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_session_resource_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    original = ast.parse(
        '''
def character_session_resource(
    campaign_slug: str,
    character_slug: str,
    resource_id: str,
):
    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="session-resources",
        success_message="Resource updated.",
        action=lambda record, expected_revision, user_id: get_character_state_service().update_resource(
            record,
            resource_id,
            expected_revision=expected_revision,
            current=request.form.get("current"),
            delta=request.form.get("delta"),
            updated_by_user_id=user_id,
        ),
    )
'''
    ).body[0]
    assert _canonical_handler(moved) == _canonical_handler(original)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_session_xianxia_active_state") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_session_spell_slots"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/resources/<resource_id>"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_service_form_and_update_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    values = {"current": "3", "delta": "-1"}

    class RecordingForm:
        def get(self, key):
            events.append(("form", (key,), {}))
            return values[key]

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "sorcery-points")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "runner",
        "service",
        "form",
        "form",
        "update",
        "action_result",
    ]
    runner = events[0]
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "session-resources"
    assert runner[2]["success_message"] == "Resource updated."
    assert [event[1][0] for event in events if event[0] == "form"] == [
        "current",
        "delta",
    ]
    update = next(event for event in events if event[0] == "update")
    assert update[1][0].definition == {"name": "Arden"}
    assert update[1][1] == "sorcery-points"
    assert update[2] == {
        "expected_revision": 17,
        "current": "3",
        "delta": "-1",
        "updated_by_user_id": 42,
    }


def test_raw_first_repeated_form_values_are_preserved(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    data = MultiDict(
        [
            ("current", " 3 "),
            ("current", "99"),
            ("delta", ""),
            ("delta", "7"),
        ]
    )
    with app.test_request_context(ROUTE_PATH, method="POST", data=data):
        assert (
            _handler(app)("linden-pass", "arden-march", "sorcery-points")
            == "mutation-result"
        )
    update = next(event for event in events if event[0] == "update")
    assert update[2]["current"] == " 3 "
    assert update[2]["delta"] == ""


def test_scope_denial_performs_no_runner_service_form_or_update_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached resource handler")

    _install_dependencies(
        app,
        monkeypatch,
        run_session_mutation=unexpected,
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
    dependencies["run_session_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p64-resource")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_unassigned_player_denial_performs_no_state_service_or_update_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("unassigned player denial reached state service")

    _install_dependencies(
        app,
        monkeypatch,
        get_character_state_service=unexpected,
    )
    assert client.post(ROUTE_PATH).status_code == 403


def test_p34_failure_occurs_in_captured_runner_before_downstream_work(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        raise NotFound()

    dependencies["run_session_mutation"] = invalid_runner
    _install_dependencies(app, monkeypatch, **dependencies)
    malicious_path = ROUTE_PATH.replace("arden-march", "..\\victim")
    with app.test_request_context(malicious_path, method="POST"):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\victim", "sorcery-points")
    assert [event[0] for event in events] == ["runner"]


@pytest.mark.parametrize("fault_stage", ("runner", "service", "current", "delta", "update"))
def test_faults_propagate_at_every_transport_stage(
    app, monkeypatch, fault_stage
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        dependencies["run_session_mutation"] = fault
    elif fault_stage == "service":
        dependencies["get_character_state_service"] = fault
    elif fault_stage == "update":
        dependencies["get_character_state_service"] = lambda: SimpleNamespace(
            update_resource=fault
        )
    else:
        class FaultingForm:
            def get(self, key):
                if key == fault_stage:
                    fault()
                return "1"

        monkeypatch.setattr(
            route_module,
            "request",
            SimpleNamespace(form=FaultingForm()),
        )

    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "sorcery-points")
