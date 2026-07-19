from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

import player_wiki.character_currency_api_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from player_wiki.route_contracts import build_manifest
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "8876d24a6979c5a2feb479652b309df8a31a9843"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/session/currency"
)
ENDPOINT = "api.character_currency_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_mutation",
    "get_character_state_service",
]
DENOMINATIONS = (
    "cp",
    "sp",
    "ep",
    "gp",
    "pp",
    "coin",
    "supply",
    "spirit_stones",
)


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


def _dependencies(events: list[tuple], *, payload_values=None, system="dnd5e"):
    record = SimpleNamespace(
        definition=SimpleNamespace(system=system),
        state_record=SimpleNamespace(state={}),
    )
    default_values = {
        "expected_revision": 17,
        "cp": "1",
        "sp": "2",
        "ep": "3",
        "gp": "4",
        "pp": "5",
        "coin": "6",
        "supply": "7",
        "spirit_stones": "8",
        "delta": "gp:99",
        "ignored": "value",
    }
    payload = RecordingPayload(
        default_values if payload_values is None else payload_values,
        events,
    )

    def update(*args, **kwargs):
        events.append(("update", args, kwargs))
        return "updated-state"

    service = SimpleNamespace(update_currency=update)

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
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [field.name for field in fields(route_module.CharacterCurrencyApiDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_currency_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_currency_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_currency_update"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_currency_api_route"
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
            "current_app",
            "request",
        }
        for node in ast.walk(route_tree)
    )

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 256
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 203
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 213
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
    assert len(api_route_decorators) == 35

    assert isinstance(register_api.body[250], ast.Expr)
    assert register_api.body[250].value.func.id == (
        "register_character_feature_state_api_route"
    )
    assert isinstance(register_api.body[251], ast.Expr)
    assert register_api.body[251].value.func.id == "register_character_currency_api_route"
    assert isinstance(register_api.body[252], ast.Expr)
    assert register_api.body[252].value.func.id == "register_character_notes_api_route"
    notes_tree = ast.parse(
        (source_root / "character_notes_api_routes.py").read_text(encoding="utf-8")
    )
    notes_handler = next(
        node
        for node in ast.walk(notes_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_notes_update"
    )
    assert notes_handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_notes_update"
        for node in ast.walk(api_tree)
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[251])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterCurrencyApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER)


def test_moved_handler_keeps_canonical_ast_and_all_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT / "player_wiki" / "character_currency_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_currency_update"
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
    original = old_register.body[263]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_currency_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    registrar_names = [
        node.value.func.id
        for node in new_register.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id.startswith("register_")
    ]
    assert registrar_names.count("register_character_currency_api_route") == 1
    registrar_index = registrar_names.index("register_character_currency_api_route")
    assert registrar_names[registrar_index - 1 : registrar_index + 2] == [
        "register_character_feature_state_api_route",
        "register_character_currency_api_route",
        "register_character_notes_api_route",
    ]


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(
    app, client
):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_feature_state_update") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_notes_update")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/currency"
    )
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert client.patch(ROUTE_PATH).status_code == 401
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_currency_update"
    )


def test_handler_preserves_service_revision_and_all_denomination_evaluation_order(
    app,
    monkeypatch,
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "service",
        *("payload_get" for _ in range(9)),
        "update",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "expected_revision",
        *DENOMINATIONS,
    ]
    runner = events[0]
    assert runner[1][:2] == ("linden-pass", "arden-march")
    update = next(event for event in events if event[0] == "update")
    assert update[2] == {
        "expected_revision": 17,
        "values": {
            "cp": "1",
            "sp": "2",
            "ep": "3",
            "gp": "4",
            "pp": "5",
            "coin": "6",
            "supply": "7",
            "spirit_stones": "8",
        },
        "updated_by_user_id": 42,
    }
    assert "delta" not in update[2]


def test_handler_preserves_missing_null_blank_values_and_ignores_unknown_keys_and_delta(
    app,
    monkeypatch,
):
    events: list[tuple] = []
    payload = {
        "expected_revision": 17,
        "cp": "",
        "sp": None,
        "delta": "gp:5",
        "unknown": 99,
    }
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload_values=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    update = next(event for event in events if event[0] == "update")
    assert update[2]["values"] == {
        "cp": "",
        "sp": None,
        "ep": None,
        "gp": None,
        "pp": None,
        "coin": None,
        "supply": None,
        "spirit_stones": None,
    }
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "expected_revision",
        *DENOMINATIONS,
    ]


def test_service_is_acquired_before_invalid_revision_stops_value_evaluation(
    app,
    monkeypatch,
):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(
            events,
            payload_values={"expected_revision": "not-an-int", "gp": "3"},
        ),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["runner", "service", "payload_get"]
    assert events[-1][1] == "expected_revision"


@pytest.mark.parametrize("fault_stage", ("runner", "service", "update"))
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app,
    monkeypatch,
    fault_stage,
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        replacements["run_character_mutation"] = fault
    elif fault_stage == "service":
        replacements["get_character_state_service"] = fault
    else:
        replacements["get_character_state_service"] = lambda: SimpleNamespace(
            update_currency=fault
        )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march")


def test_view_as_denial_precedes_handler_but_bearer_identity_wins(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    events: list[tuple] = []

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        return {"ok": True}

    _install_dependencies(app, monkeypatch, run_character_mutation=runner)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.patch(ROUTE_PATH).status_code == 403
    assert events == []

    token = issue_api_token(app, users["admin"]["email"], label="p87-bearer")
    response = client.patch(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_runner_preserves_access_json_validation_conflict_and_precommit_atomicity(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="p87-owner")
    party_token = issue_api_token(app, users["party"]["email"], label="p87-party")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision

    def unexpected_save(*args, **kwargs):
        raise AssertionError("denied or malformed request reached currency persistence")

    service = app.extensions["character_state_service"]
    original_update = service.update_currency
    monkeypatch.setattr(service, "update_currency", unexpected_save)
    denied = client.patch(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json={"expected_revision": starting_revision, "gp": 1},
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"

    malformed = client.patch(
        ROUTE_PATH,
        headers={**api_headers(owner_token), "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "invalid_json"

    invalid_revision = client.patch(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={"expected_revision": "not-an-int", "gp": 1},
    )
    assert invalid_revision.status_code == 400
    assert invalid_revision.get_json()["error"]["code"] == "validation_error"
    monkeypatch.setattr(service, "update_currency", original_update)

    negative = client.patch(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={"expected_revision": starting_revision, "gp": -1},
    )
    assert negative.status_code == 400
    assert negative.get_json()["error"]["code"] == "validation_error"

    stale = client.patch(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={"expected_revision": starting_revision + 99, "gp": 1},
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "state_conflict"

    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == starting_revision


def test_p34_identity_mismatch_stops_before_state_or_currency_service(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p87-p34")
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
        raise AssertionError("identity mismatch reached currency work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(
        app.extensions["character_state_service"],
        "update_currency",
        unexpected,
    )
    response = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0, "gp": 1},
    )
    assert response.status_code == 404


def test_committed_currency_survives_refresh_serialization_fault(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p87-postcommit")
    repository = app.extensions["character_repository"]
    original_load = repository.get_visible_character
    with app.app_context():
        before = original_load("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision
    calls = 0

    def fail_refresh(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("refresh serialization fault")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(repository, "get_visible_character", fail_refresh)
    with pytest.raises(RuntimeError, match="refresh serialization fault"):
        client.patch(
            ROUTE_PATH,
            headers=api_headers(token),
            json={"expected_revision": starting_revision, "gp": 23},
        )

    with app.app_context():
        persisted = original_load("linden-pass", "arden-march")
    assert persisted is not None
    assert persisted.state_record.revision == starting_revision + 1
    assert persisted.state_record.state["currency"]["gp"] == 23


def test_browser_currency_keeps_form_delta_distinction_and_shared_service_inline():
    api_source = (
        PROJECT_ROOT / "player_wiki" / "character_currency_api_routes.py"
    ).read_text(encoding="utf-8")
    browser_source = (
        PROJECT_ROOT / "player_wiki" / "character_session_currency_routes.py"
    ).read_text(encoding="utf-8")
    assert 'payload.get("delta")' not in api_source
    assert 'request.form.get("delta")' in browser_source
    assert "run_character_mutation" in api_source
    assert "run_session_mutation" in browser_source


def test_manifest_metadata_remains_characters_scope_without_system_gate():
    entries = [
        entry
        for entry in build_manifest()["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "PATCH"
    ]
    assert len(entries) == 1
    assert entries[0]["campaign_scope"] == "characters"
    assert entries[0]["system_restriction"] == "none"
    assert entries[0]["authentication_policy"] == "api_identity_required"
    assert entries[0]["access_policy"] == "character_owner_or_manager_api"
