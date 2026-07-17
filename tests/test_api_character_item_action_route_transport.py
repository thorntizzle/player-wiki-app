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
import player_wiki.character_item_action_api_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "1590f127969fe15717084fe80e24aec5d49c0a48"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/item-actions/innovators-bolt/use"
)
ENDPOINT = "api.character_item_action_use"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_mutation",
    "parse_item_action_slot_selection",
    "get_character_state_service",
    "resolve_projected_item_use_action",
]


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


def _dependencies(
    events: list[tuple],
    *,
    payload=None,
    parsed_slot=("wizard:main", 2),
    resolver_error=None,
    service_error=None,
):
    record = SimpleNamespace(slug="arden-march")
    payload = payload or RecordingPayload(
        {
            "slot_lane_id": "fallback-lane",
            "slot_level": "1",
            "slot_selection": "wizard:main|2",
            "choice_id": "incendiary",
            "expected_revision": "17",
        },
        events,
    )
    projected_action = {
        "id": "innovators-bolt",
        "kind": "spell_slot_item_attack",
        "enabled": True,
    }

    def parse(*args, **kwargs):
        events.append(("parse", args, kwargs))
        return parsed_slot

    def resolve(*args, **kwargs):
        events.append(("resolve", args, kwargs))
        if resolver_error is not None:
            raise resolver_error
        return projected_action

    def use(*args, **kwargs):
        events.append(("use", args, kwargs))
        if service_error is not None:
            raise service_error
        return "updated-state"

    service = SimpleNamespace(use_spell_slot_item_action=use)

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "run_character_mutation": runner,
        "parse_item_action_slot_selection": parse,
        "get_character_state_service": get_service,
        "resolve_projected_item_use_action": resolve,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name for field in fields(route_module.CharacterItemActionApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_item_action_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_item_action_use"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_item_action_use"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_item_action_api_route"
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

    assert isinstance(register_api.body[243], ast.Expr)
    assert register_api.body[243].value.func.id == (
        "register_character_spell_slots_api_route"
    )
    assert isinstance(register_api.body[244], ast.Expr)
    assert register_api.body[244].value.func.id == (
        "register_character_item_action_api_route"
    )
    assert isinstance(register_api.body[245], ast.Expr)
    assert register_api.body[245].value.func.id == (
        "register_character_inventory_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[244])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterItemActionApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert isinstance(by_name["parse_item_action_slot_selection"], ast.Lambda)
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in DEPENDENCY_ORDER
        if name != "parse_item_action_slot_selection"
    )


def test_moved_handler_and_action_keep_canonical_ast_and_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_item_action_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_item_action_use"
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
    original = old_register.body[244]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_item_action_use"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {162, 163, 244, 245, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(
    app, client
):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_spell_slots_update") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_inventory_update")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/item-actions/<action_id>/use"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_item_action_use"
    )


def test_truthy_slot_selection_preserves_payload_parser_projection_and_use_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "runner",
        "payload_get",
        "payload_get",
        "payload_get",
        "payload_get",
        "parse",
        "service",
        "resolve",
        "payload_get",
        "payload_get",
        "use",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "slot_lane_id",
        "slot_level",
        "slot_selection",
        "slot_selection",
        "choice_id",
        "expected_revision",
    ]
    resolve = next(event for event in events if event[0] == "resolve")
    assert resolve[1] == (
        "linden-pass",
        SimpleNamespace(slug="arden-march"),
        "innovators-bolt",
    )
    use = next(event for event in events if event[0] == "use")
    assert use[2] == {
        "choice_id": "incendiary",
        "slot_level": 2,
        "slot_lane_id": "wizard:main",
        "expected_revision": 17,
        "updated_by_user_id": 42,
    }


def test_falsey_slot_selection_keeps_raw_lane_level_without_parser(app, monkeypatch):
    events: list[tuple] = []
    payload = RecordingPayload(
        {
            "slot_lane_id": " warlock:pact ",
            "slot_level": " 3 ",
            "slot_selection": "",
            "choice_id": "force",
            "expected_revision": 9,
        },
        events,
    )
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )
    assert not any(event[0] == "parse" for event in events)
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "slot_lane_id",
        "slot_level",
        "slot_selection",
        "choice_id",
        "expected_revision",
    ]
    use = next(event for event in events if event[0] == "use")
    assert use[2]["slot_lane_id"] == " warlock:pact "
    assert use[2]["slot_level"] == 3


def test_parser_remains_forwarded_from_api_module_global(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)
    replacements.pop("parse_item_action_slot_selection")
    _install_dependencies(app, monkeypatch, **replacements)

    def forwarded_parse(*args, **kwargs):
        events.append(("forwarded_parse", args, kwargs))
        return "forwarded-lane", 4

    monkeypatch.setattr(
        api_module,
        "parse_item_action_slot_selection",
        forwarded_parse,
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert (
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")
            == "mutation-result"
        )
    assert "forwarded_parse" in [event[0] for event in events]
    use = next(event for event in events if event[0] == "use")
    assert use[2]["slot_lane_id"] == "forwarded-lane"
    assert use[2]["slot_level"] == 4


@pytest.mark.parametrize("fault_stage", ("runner", "parse", "service", "resolve", "use"))
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app, monkeypatch, fault_stage
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        replacements["run_character_mutation"] = fault
    elif fault_stage == "parse":
        replacements["parse_item_action_slot_selection"] = fault
    elif fault_stage == "service":
        replacements["get_character_state_service"] = fault
    elif fault_stage == "resolve":
        replacements["resolve_projected_item_use_action"] = fault
    else:
        replacements["get_character_state_service"] = lambda: SimpleNamespace(
            use_spell_slot_item_action=fault
        )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "innovators-bolt")


def test_view_as_denial_precedes_handler_but_bearer_identity_wins(
    app, client, sign_in, users, monkeypatch
):
    events: list[tuple] = []

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        return {"ok": True}

    _install_dependencies(app, monkeypatch, run_character_mutation=runner)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []

    token = issue_api_token(app, users["admin"]["email"], label="p78-bearer")
    response = client.post(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_runner_preserves_access_invalid_json_and_precommit_atomicity(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="p78-owner")
    party_token = issue_api_token(app, users["party"]["email"], label="p78-party")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision

    def unexpected_resolve(*args, **kwargs):
        raise AssertionError("denied or malformed request reached projection")

    _install_dependencies(
        app,
        monkeypatch,
        resolve_projected_item_use_action=unexpected_resolve,
    )
    denied = client.post(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json={"expected_revision": starting_revision},
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"

    malformed = client.post(
        ROUTE_PATH,
        headers={**api_headers(owner_token), "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "invalid_json"

    _install_dependencies(
        app,
        monkeypatch,
        resolve_projected_item_use_action=lambda *args: {
            "kind": "spell_slot_item_attack",
            "enabled": True,
        },
    )
    invalid_revision = client.post(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={
            "expected_revision": "not-an-int",
            "choice_id": "force",
            "slot_level": 2,
        },
    )
    assert invalid_revision.status_code == 400
    assert invalid_revision.get_json()["error"]["code"] == "validation_error"
    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == starting_revision


def test_p34_identity_mismatch_stops_before_state_access_projection_or_service(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p78-p34")
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

    def unexpected(*args, **kwargs):
        raise AssertionError("identity mismatch reached downstream item-action work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    _install_dependencies(
        app,
        monkeypatch,
        get_character_state_service=unexpected,
        resolve_projected_item_use_action=unexpected,
    )
    response = client.post(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0},
    )
    assert response.status_code == 404


def test_committed_item_action_state_survives_refresh_serialization_fault(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p78-postcommit")
    repository = app.extensions["character_repository"]
    original_load = repository.get_visible_character
    with app.app_context():
        before = original_load("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision
    slot = next(
        row
        for row in before.state_record.state["spell_slots"]
        if int(row.get("level") or 0) > 0
        and int(row.get("used") or 0) < int(row.get("max") or 0)
    )
    level = int(slot.get("level") or 0)
    lane_id = str(slot.get("slot_lane_id") or "")

    def resolve(*args):
        return {
            "id": "test-action",
            "kind": "spell_slot_item_attack",
            "enabled": True,
            "choices": [{"id": "force", "is_supported": True}],
            "slot_options": [
                {
                    "level": level,
                    "slot_lane_id": lane_id,
                    "max": int(slot.get("max") or 0),
                }
            ],
        }

    _install_dependencies(
        app,
        monkeypatch,
        resolve_projected_item_use_action=resolve,
    )
    calls = 0

    def fail_refresh(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("refresh serialization fault")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(repository, "get_visible_character", fail_refresh)
    with pytest.raises(RuntimeError, match="refresh serialization fault"):
        client.post(
            ROUTE_PATH,
            headers=api_headers(token),
            json={
                "expected_revision": starting_revision,
                "choice_id": "force",
                "slot_level": level,
                "slot_lane_id": lane_id,
            },
        )

    with app.app_context():
        persisted = original_load("linden-pass", "arden-march")
    assert persisted is not None
    assert persisted.state_record.revision == starting_revision + 1
    persisted_slot = next(
        row
        for row in persisted.state_record.state["spell_slots"]
        if int(row.get("level") or 0) == level
        and str(row.get("slot_lane_id") or "") == lane_id
    )
    assert persisted_slot["used"] == int(slot.get("used") or 0) + 1
