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
import player_wiki.character_xianxia_dao_use_request_api_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_reconciliation import (
    CharacterPublicationCoordinator,
    CharacterReconciliationHooks,
)
from player_wiki.character_store import CharacterStateStore
from player_wiki.route_contracts import build_manifest
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.test_api_characters import _configure_xianxia_campaign, _valid_xianxia_create_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "5f25ff3581c02fa2d327b7fa36fd96019761a23b"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/xianxia-dao-immolating-use-requests"
)
ENDPOINT = "api.character_xianxia_dao_immolating_use_request"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_definition_mutation",
    "ensure_xianxia_character_definition",
    "json_payload_value",
    "optional_json_int",
    "managed_character_import_metadata",
    "request_xianxia_dao_immolating_use_definition",
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


def _dependencies(events: list[tuple], *, system="xianxia", payload_values=None):
    definition = SimpleNamespace(system=system)
    import_metadata = SimpleNamespace(name="metadata")
    record = SimpleNamespace(definition=definition, import_metadata=import_metadata)
    payload = RecordingPayload(
        {
            "expected_revision": 17,
            "request_name": "Ashen Bell",
            "notes": "Ring it at the bridge.",
            "prepared_record_index": 2,
        }
        if payload_values is None
        else payload_values,
        events,
    )
    requested_definition = SimpleNamespace(system="xianxia", requested=True)

    def ensure(record_arg, message):
        events.append(("ensure", (record_arg, message), {}))
        if record_arg.definition.system != "xianxia":
            raise ValueError(message)

    def json_value(submitted_payload, *keys):
        events.append(("json_value", keys, {}))
        for key in keys:
            if key in submitted_payload:
                return submitted_payload.get(key)
        return None

    def optional_int(submitted_payload, *keys, field_label):
        events.append(("optional_int", keys, {"field_label": field_label}))
        value = json_value(submitted_payload, *keys)
        return None if value in (None, "") else int(value)

    def request_definition(*args, **kwargs):
        events.append(("request_definition", args, kwargs))
        return SimpleNamespace(definition=requested_definition)

    def metadata(campaign_slug, record_arg):
        events.append(("metadata", (campaign_slug, record_arg), {}))
        return import_metadata

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "run_character_definition_mutation": runner,
        "ensure_xianxia_character_definition": ensure,
        "json_payload_value": json_value,
        "optional_json_int": optional_int,
        "managed_character_import_metadata": metadata,
        "request_xianxia_dao_immolating_use_definition": request_definition,
    }


def test_transport_has_exact_dependencies_registration_wrapper_and_source_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterXianxiaDaoUseRequestApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_xianxia_dao_use_request_api_routes.py").read_text()
    )
    api_tree = ast.parse((source_root / "api.py").read_text())
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_request"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_request"
        for node in ast.walk(api_tree)
    )
    assert not any(
        isinstance(node, ast.Name)
        and node.id
        in {
            "api_campaign_scope_access_required",
            "current_app",
            "request",
        }
        for node in ast.walk(route_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_xianxia_dao_use_request_api_route"
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

    assert isinstance(register_api.body[241], ast.Expr)
    assert register_api.body[241].value.func.id == (
        "register_character_xianxia_active_state_api_route"
    )
    assert isinstance(register_api.body[242], ast.Expr)
    assert register_api.body[242].value.func.id == (
        "register_character_xianxia_dao_use_request_api_route"
    )
    assert isinstance(register_api.body[243], ast.Expr)
    assert register_api.body[243].value.func.id == (
        "register_character_xianxia_dao_use_record_api_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[242])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterXianxiaDaoUseRequestApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER[:-1])
    assert isinstance(by_name["request_xianxia_dao_immolating_use_definition"], ast.Lambda)


def test_moved_handler_keeps_canonical_ast_and_all_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_xianxia_dao_use_request_api_routes.py"
        ).read_text()
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_dao_immolating_use_request"
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
    original = old_register.body[254]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_xianxia_dao_immolating_use_request"
    assert _canonical_handler(moved) == _canonical_handler(original)
    registrar_names = [
        node.value.func.id
        for node in new_register.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id.startswith("register_")
    ]
    assert registrar_names.count("register_character_xianxia_dao_use_request_api_route") == 1
    registrar_index = registrar_names.index("register_character_xianxia_dao_use_request_api_route")
    assert registrar_names[registrar_index - 1 : registrar_index + 2] == [
        "register_character_xianxia_active_state_api_route",
        "register_character_xianxia_dao_use_request_api_route",
        "register_character_xianxia_dao_use_record_api_route",
    ]


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(app, client):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/xianxia-dao-immolating-use-requests"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert client.post(ROUTE_PATH).status_code == 401
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_xianxia_dao_immolating_use_request"
    )
    assert endpoints.index("api.character_xianxia_active_state_update") < endpoints.index(
        ENDPOINT
    ) < endpoints.index("api.character_xianxia_dao_immolating_use_record")


def test_handler_preserves_xianxia_payload_request_metadata_and_runner_order(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "ensure",
        "json_value",
        "payload_contains",
        "payload_get",
        "json_value",
        "payload_contains",
        "payload_get",
        "optional_int",
        "json_value",
        "payload_contains",
        "payload_get",
        "request_definition",
        "metadata",
        "action_result",
    ]
    request_event = next(event for event in events if event[0] == "request_definition")
    assert request_event[2] == {
        "request_name": "Ashen Bell",
        "notes": "Ring it at the bridge.",
        "prepared_record_index": 2,
    }
    result = next(event for event in events if event[0] == "action_result")[1][0]
    assert result[0].requested is True
    assert result[1].name == "metadata"
    assert result[2] == {}


def test_xianxia_gate_precedes_payload_helpers_request_and_metadata(app, monkeypatch):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events, system="dnd5e"))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(ValueError, match="only available for Xianxia"):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["runner", "ensure"]


def test_forwarded_request_helper_remains_late_substitutable_after_registration(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)
    replacements.pop("request_xianxia_dao_immolating_use_definition")
    _install_dependencies(app, monkeypatch, **replacements)

    def replacement(*args, **kwargs):
        events.append(("forwarded_replacement", args, kwargs))
        return SimpleNamespace(definition=SimpleNamespace(forwarded=True))

    monkeypatch.setattr(
        api_module,
        "request_xianxia_dao_immolating_use_definition",
        replacement,
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    forwarded = next(event for event in events if event[0] == "forwarded_replacement")
    assert forwarded[2]["prepared_record_index"] == 2


@pytest.mark.parametrize(
    "fault_stage",
    ("runner", "ensure", "json", "optional", "request", "metadata"),
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
        "runner": "run_character_definition_mutation",
        "ensure": "ensure_xianxia_character_definition",
        "json": "json_payload_value",
        "optional": "optional_json_int",
        "request": "request_xianxia_dao_immolating_use_definition",
        "metadata": "managed_character_import_metadata",
    }
    replacements[dependency_by_stage[fault_stage]] = fault
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
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

    _install_dependencies(app, monkeypatch, run_character_definition_mutation=runner)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []

    token = issue_api_token(app, users["admin"]["email"], label="p92-bearer")
    response = client.post(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_runner_preserves_access_json_xianxia_validation_and_precommit_atomicity(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="p92-owner")
    party_token = issue_api_token(app, users["party"]["email"], label="p92-party")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    starting_definition = definition_path.read_bytes()

    def unexpected_request(*args, **kwargs):
        raise AssertionError("denied or malformed request reached Dao request mutation")

    monkeypatch.setattr(
        api_module,
        "request_xianxia_dao_immolating_use_definition",
        unexpected_request,
    )
    denied = client.post(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json={"expected_revision": starting_revision, "request_name": "Denied"},
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

    invalid_revision = client.post(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={"expected_revision": "not-an-int", "request_name": "No mutation"},
    )
    assert invalid_revision.status_code == 400
    assert invalid_revision.get_json()["error"]["code"] == "validation_error"

    unsupported = client.post(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={"expected_revision": starting_revision, "request_name": "No mutation"},
    )
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"]["code"] == "validation_error"

    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == starting_revision
    assert definition_path.read_bytes() == starting_definition


def test_p34_identity_mismatch_stops_before_state_access_or_dao_request_work(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p92-p34")
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["character_slug"] = "another-character"
    definition_path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")

    def unexpected(*args, **kwargs):
        raise AssertionError("identity mismatch reached state or Dao request work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(api_module, "has_session_mode_access", unexpected)
    monkeypatch.setattr(
        api_module,
        "request_xianxia_dao_immolating_use_definition",
        unexpected,
    )
    response = client.post(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0, "request_name": "Blocked"},
    )
    assert response.status_code == 404


def test_definition_runner_recovers_after_committed_publication_fault(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("P92 Dao Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    token = issue_api_token(app, users["dm"]["email"], label="p92-state-before-yaml")
    route = (
        "/api/v1/campaigns/linden-pass/characters/p92-dao-crane/"
        "session/xianxia-dao-immolating-use-requests"
    )
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "p92-dao-crane")
    assert before is not None
    starting_revision = before.state_record.revision

    def fail_after_commit(event, _operation_id):
        if event == "after_commit":
            raise RuntimeError("committed publication fault")

    original_coordinator = app.extensions["character_publication_coordinator"]
    fault_coordinator = CharacterPublicationCoordinator(
        campaigns_dir=original_coordinator.campaigns_dir,
        database_path=original_coordinator.database_path,
        state_store=original_coordinator.state_store,
        repository=original_coordinator.repository,
        hooks=CharacterReconciliationHooks(on_event=fail_after_commit),
    )
    monkeypatch.setitem(
        app.extensions, "character_publication_coordinator", fault_coordinator
    )
    with pytest.raises(RuntimeError, match="committed publication fault"):
        client.post(
            route,
            headers=api_headers(token),
            json={
                "expected_revision": starting_revision,
                "request_name": "Ashen Bell",
                "notes": "Requested before the bridge duel.",
            },
        )

    with app.app_context():
        assert repository.get_visible_character("linden-pass", "p92-dao-crane") is None
        state = app.extensions["character_state_store"].get_state(
            "linden-pass", "p92-dao-crane"
        )
        assert state is not None
        assert state.revision == starting_revision + 1
        assert original_coordinator.recover_key(
            "linden-pass", "p92-dao-crane"
        ) is True
        persisted = repository.get_visible_character(
            "linden-pass", "p92-dao-crane"
        )
        assert persisted is not None
        assert persisted.state_record.revision == starting_revision + 1


def test_manifest_metadata_keeps_characters_scope_and_xianxia_without_runtime_scope_gate():
    entries = [
        entry
        for entry in build_manifest()["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "POST"
    ]
    assert len(entries) == 1
    assert entries[0]["campaign_scope"] == "characters"
    assert entries[0]["system_restriction"] == "xianxia_only"
    assert entries[0]["authentication_policy"] == "api_identity_required"
    assert entries[0]["access_policy"] == "character_owner_or_manager_api"


def test_browser_request_and_manager_record_keep_distinct_runners_permissions_and_transports():
    api_source = (
        PROJECT_ROOT / "player_wiki" / "character_xianxia_dao_use_request_api_routes.py"
    ).read_text()
    browser_source = (
        PROJECT_ROOT / "player_wiki" / "character_xianxia_dao_use_request_routes.py"
    ).read_text()
    record_api_source = (
        PROJECT_ROOT / "player_wiki" / "character_xianxia_dao_use_record_api_routes.py"
    ).read_text()
    assert "run_character_definition_mutation" in api_source
    assert "request.form" not in api_source
    assert "run_character_definition_mutation" in browser_source
    assert "request.form" in browser_source
    assert "character_xianxia_dao_immolating_use_record" not in api_source
    assert "can_manage_campaign_session" not in api_source
    assert "def character_xianxia_dao_immolating_use_record" in record_api_source
    assert record_api_source.index("can_manage_campaign_session") < (
        record_api_source.index("run_character_definition_mutation")
    )
