from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.app as app_module
import player_wiki.character_session_spell_slots_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "session/spell-slots/1"
)
ENDPOINT = "character_session_spell_slots"


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
    campaign = SimpleNamespace(slug="linden-pass", system="dnd5e")
    record = SimpleNamespace(definition={"name": "Arden"}, state_record={})

    def load(*args, **kwargs):
        events.append(("load", args, kwargs))
        return campaign, record

    def access(*args, **kwargs):
        events.append(("access", args, kwargs))
        return True

    def supported(*args, **kwargs):
        events.append(("supported", args, kwargs))
        return True

    def redirect_unsupported(*args, **kwargs):
        events.append(("redirect", args, kwargs))
        return "unsupported-result"

    def update_spell_slots(*args, **kwargs):
        events.append(("update", args, kwargs))
        return "updated-state"

    service = SimpleNamespace(update_spell_slots=update_spell_slots)

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record, 17, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "load_character_context": load,
        "has_session_mode_access": access,
        "campaign_supports_dnd5e_character_spellcasting_tools": supported,
        "redirect_unsupported_dnd5e_character_spellcasting_tools": (
            redirect_unsupported
        ),
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
    expected_order = [
        "load_character_context",
        "has_session_mode_access",
        "campaign_supports_dnd5e_character_spellcasting_tools",
        "redirect_unsupported_dnd5e_character_spellcasting_tools",
        "run_session_mutation",
        "get_character_state_service",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterSessionSpellSlotsRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_spell_slots_routes.py").read_text(
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
        and node.name == "register_character_session_spell_slots_route"
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
    assert len(route_decorators) == 30

    assert isinstance(create_app.body[284], ast.FunctionDef)
    assert create_app.body[284].name == "_xianxia_inventory_item_payload_from_form"
    for index, registrar_name in (
        (285, "register_character_session_resource_route"),
        (286, "register_character_session_spell_slots_route"),
    ):
        assert isinstance(create_app.body[index], ast.Expr)
        assert isinstance(create_app.body[index].value, ast.Call)
        assert isinstance(create_app.body[index].value.func, ast.Name)
        assert create_app.body[index].value.func.id == registrar_name
    assert isinstance(create_app.body[287], ast.Expr)
    assert isinstance(create_app.body[287].value, ast.Call)
    assert isinstance(create_app.body[287].value.func, ast.Name)
    assert (
        create_app.body[287].value.func.id
        == "register_character_session_item_action_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[286])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionSpellSlotsRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert isinstance(by_name["has_session_mode_access"], ast.Lambda)
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in expected_order
        if name != "has_session_mode_access"
    )


def test_moved_handler_and_lambda_keep_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_session_spell_slots_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    original = ast.parse(
        '''
def character_session_spell_slots(
    campaign_slug: str,
    character_slug: str,
    level: int,
):
    campaign, _ = load_character_context(campaign_slug, character_slug)
    if not has_session_mode_access(campaign_slug, character_slug):
        abort(403)
    if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
        return redirect_unsupported_dnd5e_character_spellcasting_tools(
            campaign_slug,
            character_slug,
        )

    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="session-spell-slots",
        success_message="Spell slot usage updated.",
        action=lambda record, expected_revision, user_id: get_character_state_service().update_spell_slots(
            record,
            level,
            slot_lane_id=request.form.get("slot_lane_id", ""),
            expected_revision=expected_revision,
            used=request.form.get("used"),
            delta_used=request.form.get("delta_used"),
            updated_by_user_id=user_id,
        ),
    )
'''
    ).body[0]
    assert _canonical_handler(moved) == _canonical_handler(original)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_session_resource") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_session_item_action_use"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/spell-slots/<int:level>"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_handler_preserves_double_admission_service_form_and_update_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    values = {
        "slot_lane_id": "wizard:main",
        "used": " 2 ",
        "delta_used": "-1",
    }

    class RecordingForm:
        def get(self, key, default=None):
            events.append(("form", (key, default), {}))
            return values.get(key, default)

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march", 1) == "mutation-result"

    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "runner",
        "service",
        "form",
        "form",
        "form",
        "update",
        "action_result",
    ]
    runner = next(event for event in events if event[0] == "runner")
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "session-spell-slots"
    assert runner[2]["success_message"] == "Spell slot usage updated."
    assert [event[1] for event in events if event[0] == "form"] == [
        ("slot_lane_id", ""),
        ("used", None),
        ("delta_used", None),
    ]
    update = next(event for event in events if event[0] == "update")
    assert update[1][0].definition == {"name": "Arden"}
    assert update[1][1] == 1
    assert update[2] == {
        "slot_lane_id": "wizard:main",
        "expected_revision": 17,
        "used": " 2 ",
        "delta_used": "-1",
        "updated_by_user_id": 42,
    }


def test_raw_first_repeated_form_values_are_preserved(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    data = MultiDict(
        [
            ("slot_lane_id", " wizard:main "),
            ("slot_lane_id", "warlock:pact"),
            ("used", " 2 "),
            ("used", "9"),
            ("delta_used", ""),
            ("delta_used", "7"),
        ]
    )
    with app.test_request_context(ROUTE_PATH, method="POST", data=data):
        assert _handler(app)("linden-pass", "arden-march", 1) == "mutation-result"
    update = next(event for event in events if event[0] == "update")
    assert update[2]["slot_lane_id"] == " wizard:main "
    assert update[2]["used"] == " 2 "
    assert update[2]["delta_used"] == ""


def test_access_denial_follows_load_and_precedes_support_runner_and_service(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def denied(*args, **kwargs):
        events.append(("access", args, kwargs))
        return False

    dependencies["has_session_mode_access"] = denied
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(Forbidden):
            _handler(app)("linden-pass", "arden-march", 1)
    assert [event[0] for event in events] == ["load", "access"]


def test_unsupported_campaign_redirects_before_runner_service_and_form(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def unsupported(*args, **kwargs):
        events.append(("supported", args, kwargs))
        return False

    dependencies["campaign_supports_dnd5e_character_spellcasting_tools"] = unsupported
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march", 1) == "unsupported-result"
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "redirect",
    ]


def test_p34_load_failure_precedes_access_support_runner_and_downstream_work(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_load(*args, **kwargs):
        events.append(("load", args, kwargs))
        raise NotFound()

    dependencies["load_character_context"] = invalid_load
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\victim", 1)
    assert [event[0] for event in events] == ["load"]


def test_scope_and_view_as_denials_perform_no_handler_work_but_bearer_wins(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    events: list[tuple] = []

    def unexpected(*args, **kwargs):
        raise AssertionError("global denial reached spell-slot handler")

    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    _install_dependencies(app, monkeypatch, load_character_context=unexpected)
    assert client.post(ROUTE_PATH).status_code == 404

    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    dependencies = _fixtures(events)
    dependencies["run_session_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p65-slots")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "runner",
    ]


def test_has_session_mode_access_remains_late_forwarded_from_app_global(
    app, monkeypatch
):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies.pop("has_session_mode_access")
    dependencies["run_session_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    def forwarded(*args, **kwargs):
        events.append(("forwarded_access", args, kwargs))
        return True

    monkeypatch.setattr(app_module, "has_session_mode_access", forwarded)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march", 1) == "ok"
    assert [event[0] for event in events] == [
        "load",
        "forwarded_access",
        "supported",
        "runner",
    ]


@pytest.mark.parametrize(
    "fault_stage",
    (
        "load",
        "access",
        "supported",
        "redirect",
        "runner",
        "service",
        "slot_lane_id",
        "used",
        "delta_used",
        "update",
    ),
)
def test_faults_propagate_at_every_transport_stage(app, monkeypatch, fault_stage):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    dependency_stage = {
        "load": "load_character_context",
        "access": "has_session_mode_access",
        "runner": "run_session_mutation",
        "service": "get_character_state_service",
    }
    if fault_stage in dependency_stage:
        dependencies[dependency_stage[fault_stage]] = fault
    elif fault_stage in {"supported", "redirect"}:
        dependencies["campaign_supports_dnd5e_character_spellcasting_tools"] = (
            fault if fault_stage == "supported" else lambda *args, **kwargs: False
        )
        if fault_stage == "redirect":
            dependencies[
                "redirect_unsupported_dnd5e_character_spellcasting_tools"
            ] = fault
    elif fault_stage == "update":
        dependencies["get_character_state_service"] = lambda: SimpleNamespace(
            update_spell_slots=fault
        )
    else:
        class FaultingForm:
            def get(self, key, default=None):
                if key == fault_stage:
                    fault()
                return default

        monkeypatch.setattr(
            route_module,
            "request",
            SimpleNamespace(form=FaultingForm()),
        )

    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", 1)
