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
import player_wiki.character_session_item_action_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "session/item-actions/innovators-bolt/use"
)
ENDPOINT = "character_session_item_action_use"


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


def _fixtures(events: list[tuple], *, parsed_slot=("wizard:main", 2)):
    campaign = SimpleNamespace(slug="linden-pass", system="dnd5e")
    first_record = SimpleNamespace(label="first-load")
    mutation_record = SimpleNamespace(label="runner-load")
    projected_action = {
        "id": "innovators-bolt",
        "kind": "spell_slot_item_attack",
        "enabled": True,
    }

    def load(*args, **kwargs):
        events.append(("load", args, kwargs))
        return campaign, first_record

    def access(*args, **kwargs):
        events.append(("access", args, kwargs))
        return True

    def supported(*args, **kwargs):
        events.append(("supported", args, kwargs))
        return True

    def redirect_unsupported(*args, **kwargs):
        events.append(("redirect", args, kwargs))
        return "unsupported-result"

    def parse(*args, **kwargs):
        events.append(("parse", args, kwargs))
        return parsed_slot

    def resolve(*args, **kwargs):
        events.append(("resolve", args, kwargs))
        return projected_action

    def use(*args, **kwargs):
        events.append(("use", args, kwargs))
        return "updated-state"

    service = SimpleNamespace(use_spell_slot_item_action=use)

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](mutation_record, 17, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "load_character_context": load,
        "has_session_mode_access": access,
        "campaign_supports_dnd5e_character_spellcasting_tools": supported,
        "redirect_unsupported_dnd5e_character_spellcasting_tools": (
            redirect_unsupported
        ),
        "parse_item_action_slot_selection": parse,
        "get_character_state_service": get_service,
        "resolve_projected_item_use_action": resolve,
        "run_session_mutation": runner,
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
        "parse_item_action_slot_selection",
        "get_character_state_service",
        "resolve_projected_item_use_action",
        "run_session_mutation",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterSessionItemActionRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_item_action_routes.py").read_text(
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
        and node.name == "register_character_session_item_action_route"
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
    registrar_calls = [
        node.value
        for node in create_app.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id.startswith("register_")
    ]
    registrar_names = [call.func.id for call in registrar_calls]
    assert registrar_names.count("register_character_session_item_action_route") == 1
    registrar_index = registrar_names.index("register_character_session_item_action_route")
    assert registrar_names[registrar_index - 1 : registrar_index + 2] == [
        "register_character_session_spell_slots_route",
        "register_character_session_item_action_route",
        "register_character_session_inventory_route",
    ]
    registrar_call = registrar_calls[registrar_index]

    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionItemActionRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert isinstance(by_name["has_session_mode_access"], ast.Lambda)
    assert isinstance(by_name["parse_item_action_slot_selection"], ast.Lambda)
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in expected_order
        if name not in {"has_session_mode_access", "parse_item_action_slot_selection"}
    )


def test_moved_handler_and_nested_action_keep_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_session_item_action_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
    )
    original = ast.parse(
        '''
def character_session_item_action_use(
    campaign_slug: str,
    character_slug: str,
    action_id: str,
):
    campaign, _ = load_character_context(campaign_slug, character_slug)
    if not has_session_mode_access(campaign_slug, character_slug):
        abort(403)
    if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
        return redirect_unsupported_dnd5e_character_spellcasting_tools(
            campaign_slug,
            character_slug,
        )

    def _action(record, expected_revision, user_id):
        slot_lane_id, slot_level = parse_item_action_slot_selection(
            request.form.get("slot_selection")
        )
        if not slot_level:
            slot_level = int(request.form.get("slot_level") or 0)
            slot_lane_id = request.form.get("slot_lane_id", "")
        return get_character_state_service().use_spell_slot_item_action(
            record,
            resolve_projected_item_use_action(campaign_slug, campaign, record, action_id),
            choice_id=request.form.get("choice_id", ""),
            slot_level=slot_level,
            slot_lane_id=slot_lane_id,
            expected_revision=expected_revision,
            updated_by_user_id=user_id,
        )

    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="character-item-use-actions",
        success_message="Item action used.",
        action=_action,
    )
'''
    ).body[0]
    assert _canonical_handler(moved) == _canonical_handler(original)


def test_route_preserves_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_session_spell_slots") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_session_inventory")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/item-actions/<action_id>/use"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_truthy_parsed_slot_preserves_double_admission_projection_and_use_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    values = {
        "slot_selection": "wizard:main|2",
        "choice_id": "incendiary",
    }

    class RecordingForm:
        def get(self, key, default=None):
            events.append(("form", (key, default), {}))
            return values.get(key, default)

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "runner",
        "form",
        "parse",
        "service",
        "resolve",
        "form",
        "use",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "form"] == [
        ("slot_selection", None),
        ("choice_id", ""),
    ]
    runner = next(event for event in events if event[0] == "runner")
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "character-item-use-actions"
    assert runner[2]["success_message"] == "Item action used."
    resolve = next(event for event in events if event[0] == "resolve")
    assert resolve[1][0] == "linden-pass"
    assert resolve[1][1].slug == "linden-pass"
    assert resolve[1][2].label == "runner-load"
    assert resolve[1][3] == "innovators-bolt"
    use = next(event for event in events if event[0] == "use")
    assert use[1][0].label == "runner-load"
    assert use[1][1]["id"] == "innovators-bolt"
    assert use[2] == {
        "choice_id": "incendiary",
        "slot_level": 2,
        "slot_lane_id": "wizard:main",
        "expected_revision": 17,
        "updated_by_user_id": 42,
    }


def test_falsey_parsed_slot_reads_raw_level_then_lane_before_service(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events, parsed_slot=("", 0)))
    values = {
        "slot_selection": "",
        "slot_level": " 3 ",
        "slot_lane_id": " warlock:pact ",
        "choice_id": "force",
    }

    class RecordingForm:
        def get(self, key, default=None):
            events.append(("form", (key, default), {}))
            return values.get(key, default)

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )
    assert [event[1] for event in events if event[0] == "form"] == [
        ("slot_selection", None),
        ("slot_level", None),
        ("slot_lane_id", ""),
        ("choice_id", ""),
    ]
    assert [event[0] for event in events][4:10] == [
        "form",
        "parse",
        "form",
        "form",
        "service",
        "resolve",
    ]
    use = next(event for event in events if event[0] == "use")
    assert use[2]["slot_level"] == 3
    assert use[2]["slot_lane_id"] == " warlock:pact "


def test_raw_first_repeated_form_values_are_preserved(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events, parsed_slot=("", 0)))
    data = MultiDict(
        [
            ("slot_selection", ""),
            ("slot_selection", "wizard:main|2"),
            ("slot_level", "4"),
            ("slot_level", "9"),
            ("slot_lane_id", "first-lane"),
            ("slot_lane_id", "second-lane"),
            ("choice_id", "first-choice"),
            ("choice_id", "second-choice"),
        ]
    )
    with app.test_request_context(ROUTE_PATH, method="POST", data=data):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )
    parse = next(event for event in events if event[0] == "parse")
    assert parse[1] == ("",)
    use = next(event for event in events if event[0] == "use")
    assert use[2]["slot_level"] == 4
    assert use[2]["slot_lane_id"] == "first-lane"
    assert use[2]["choice_id"] == "first-choice"


def test_access_denial_follows_load_and_precedes_support_runner_action_work(
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
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
    assert [event[0] for event in events] == ["load", "access"]


def test_unsupported_campaign_redirects_before_runner_action_system_and_form_work(
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
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "unsupported-result"
        )
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "redirect",
    ]


def test_p34_load_failure_precedes_access_system_runner_and_action_work(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_load(*args, **kwargs):
        events.append(("load", args, kwargs))
        raise NotFound()

    dependencies["load_character_context"] = invalid_load
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\victim", "innovators-bolt")
    assert [event[0] for event in events] == ["load"]


def test_scope_and_view_as_denials_perform_no_handler_work_but_bearer_wins(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    events: list[tuple] = []

    def unexpected(*args, **kwargs):
        raise AssertionError("global denial reached item-action handler")

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
    token = issue_api_token(app, users["admin"]["email"], label="p66-item-action")
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "runner",
    ]


def test_access_and_parser_remain_late_forwarded_from_app_globals(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies.pop("has_session_mode_access")
    dependencies.pop("parse_item_action_slot_selection")
    _install_dependencies(app, monkeypatch, **dependencies)

    def forwarded_access(*args, **kwargs):
        events.append(("forwarded_access", args, kwargs))
        return True

    def forwarded_parse(*args, **kwargs):
        events.append(("forwarded_parse", args, kwargs))
        return "wizard:main", 2

    monkeypatch.setattr(app_module, "has_session_mode_access", forwarded_access)
    monkeypatch.setattr(app_module, "parse_item_action_slot_selection", forwarded_parse)
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"slot_selection": "wizard:main|2", "choice_id": "force"},
    ):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )
    assert [event[0] for event in events] == [
        "load",
        "forwarded_access",
        "supported",
        "runner",
        "forwarded_parse",
        "service",
        "resolve",
        "use",
        "action_result",
    ]


@pytest.mark.parametrize(
    "fault_stage",
    (
        "load",
        "access",
        "supported",
        "redirect",
        "runner",
        "slot_selection",
        "parse",
        "slot_level",
        "slot_lane_id",
        "service",
        "resolve",
        "choice_id",
        "use",
    ),
)
def test_faults_propagate_at_every_transport_stage(app, monkeypatch, fault_stage):
    events: list[tuple] = []
    dependencies = _fixtures(
        events,
        parsed_slot=("", 0) if fault_stage in {"slot_level", "slot_lane_id"} else ("lane", 1),
    )

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    dependency_stage = {
        "load": "load_character_context",
        "access": "has_session_mode_access",
        "parse": "parse_item_action_slot_selection",
        "runner": "run_session_mutation",
        "service": "get_character_state_service",
        "resolve": "resolve_projected_item_use_action",
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
    elif fault_stage == "use":
        dependencies["get_character_state_service"] = lambda: SimpleNamespace(
            use_spell_slot_item_action=fault
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
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")


def test_invalid_fallback_slot_level_preserves_uncaught_value_error(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events, parsed_slot=("", 0)))
    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"slot_selection": "", "slot_level": "not-an-int"},
    ):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "runner",
        "parse",
    ]


def test_unrelated_type_error_from_raw_fallback_value_propagates(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events, parsed_slot=("", 0)))

    class TypeErrorForm:
        def get(self, key, default=None):
            if key == "slot_level":
                return object()
            return default

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=TypeErrorForm()))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(TypeError):
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supported",
        "runner",
        "parse",
    ]
