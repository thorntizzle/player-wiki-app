from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

import player_wiki.character_xianxia_inventory_add_api_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "42c684a042f77d7e27a562c9740a80678fc8f47e"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/xianxia-inventory"
)
ENDPOINT = "api.character_xianxia_inventory_add"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_mutation",
    "xianxia_inventory_item_payload",
    "get_character_state_service",
]
PAYLOAD_KEYS = [
    "id",
    "name",
    "quantity",
    "item_nature",
    "item_type",
    "notes",
    "tags",
    "catalog_ref",
    "systems_ref",
    "equippable",
    "is_equipped",
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


def _dependencies(events: list[tuple], *, payload=None, service_error=None):
    record = SimpleNamespace(slug="arden-march")
    payload = payload or RecordingPayload(
        {"expected_revision": "17", "item": {"name": "Spirit Fan"}},
        events,
    )
    normalized_item = {
        "name": "Spirit Fan",
        "quantity": 2,
        "tags": ["focus"],
        "equippable": True,
        "is_equipped": False,
    }

    def normalize(*args, **kwargs):
        events.append(("normalize", args, kwargs))
        return normalized_item

    def add(*args, **kwargs):
        events.append(("add", args, kwargs))
        if service_error is not None:
            raise service_error
        return "updated-state"

    service = SimpleNamespace(add_xianxia_inventory_item=add)

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
        "xianxia_inventory_item_payload": normalize,
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(route_module.CharacterXianxiaInventoryAddApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_xianxia_inventory_add_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_inventory_add"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_inventory_add"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_xianxia_inventory_add_api_route"
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
        and node.id in {"api_campaign_scope_access_required", "is_xianxia_system"}
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

    assert isinstance(register_api.body[243], ast.Expr)
    assert register_api.body[243].value.func.id == (
        "register_character_xianxia_dao_use_record_api_route"
    )
    assert isinstance(register_api.body[244], ast.Expr)
    assert register_api.body[244].value.func.id == (
        "register_character_xianxia_inventory_add_api_route"
    )
    assert isinstance(register_api.body[245], ast.Expr)
    assert register_api.body[245].value.func.id == (
        "register_character_xianxia_inventory_item_update_api_route"
    )
    assert isinstance(register_api.body[234], ast.FunctionDef)
    assert register_api.body[234].name == "xianxia_inventory_item_payload"

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[244])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterXianxiaInventoryAddApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER)


def test_moved_handler_keeps_canonical_ast_and_all_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_xianxia_inventory_add_api_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_inventory_add"
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
    original = old_register.body[256]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_xianxia_inventory_add"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == 268
    assert len(new_register.body) == 256
    for index, before in enumerate(old_register.body):
        if index in {162, 163, 164, 165, 166, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266}:
            continue
        if 167 <= index <= 178:
            continue
        if 182 <= index <= 183:
            continue
        new_index = index if index < 167 else index - 11 if index < 182 else index - 12
        after = new_register.body[new_index]
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(
    app, client
):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_xianxia_dao_immolating_use_record") < (
        endpoints.index(ENDPOINT)
    )
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "api.character_xianxia_inventory_item_update"
    )
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/xianxia-inventory"
    )
    assert rule.methods == {"POST", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_xianxia_inventory_add"
    )


def test_handler_preserves_service_payload_revision_actor_evaluation_order(
    app, monkeypatch
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="POST"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "service",
        "normalize",
        "payload_get",
        "add",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "expected_revision"
    ]
    save = next(event for event in events if event[0] == "add")
    assert save[1] == (
        SimpleNamespace(slug="arden-march"),
        {
            "name": "Spirit Fan",
            "quantity": 2,
            "tags": ["focus"],
            "equippable": True,
            "is_equipped": False,
        },
    )
    assert save[2] == {"expected_revision": 17, "updated_by_user_id": 42}


def test_invalid_revision_follows_service_and_payload_but_precedes_save(app, monkeypatch):
    events: list[tuple] = []
    payload = RecordingPayload(
        {"expected_revision": "not-an-int", "item": {"name": "Spirit Fan"}},
        events,
    )
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == [
        "runner",
        "service",
        "normalize",
        "payload_get",
    ]


def test_original_inline_payload_helper_remains_captured_with_exact_field_order(app):
    payload_helper = _dependencies_cell(app).cell_contents.xianxia_inventory_item_payload
    assert payload_helper.__name__ == "xianxia_inventory_item_payload"
    assert payload_helper.__module__ == "player_wiki.api"

    nested = payload_helper(
        {
            "item": {
                "item_id": " spirit-fan ",
                "name": " Spirit Fan ",
                "quantity": 2,
                "item_nature": " Relic ",
                "item_type": " Artifact ",
                "notes": " Cloud sigils. ",
                "tags": ["focus"],
                "catalog_ref": " fan-catalog ",
                "systems_ref": {"slug": "spirit-fan"},
                "equippable": True,
                "is_equipped": False,
            },
            "name": "Ignored top-level name",
        }
    )
    assert list(nested) == PAYLOAD_KEYS
    assert nested == {
        "id": "spirit-fan",
        "name": "Spirit Fan",
        "quantity": 2,
        "item_nature": "Relic",
        "item_type": "Artifact",
        "notes": "Cloud sigils.",
        "tags": ["focus"],
        "catalog_ref": "fan-catalog",
        "systems_ref": {"slug": "spirit-fan"},
        "equippable": True,
        "is_equipped": False,
    }
    top_level = payload_helper({"name": " Loose Talisman ", "quantity": 1})
    assert top_level == {
        "name": "Loose Talisman",
        "quantity": 1,
        "tags": [],
    }


@pytest.mark.parametrize("fault_stage", ("runner", "service", "payload", "save"))
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app, monkeypatch, fault_stage
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        replacements["run_character_mutation"] = fault
    elif fault_stage == "service":
        replacements["get_character_state_service"] = fault
    elif fault_stage == "payload":
        replacements["xianxia_inventory_item_payload"] = fault
    else:
        replacements["get_character_state_service"] = lambda: SimpleNamespace(
            add_xianxia_inventory_item=fault
        )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march")


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

    token = issue_api_token(app, users["admin"]["email"], label="p80-bearer")
    response = client.post(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_runner_preserves_access_invalid_json_and_precommit_atomicity(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="p80-owner")
    party_token = issue_api_token(app, users["party"]["email"], label="p80-party")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision

    def unexpected_save(*args, **kwargs):
        raise AssertionError("denied or malformed request reached inventory persistence")

    monkeypatch.setattr(
        app.extensions["character_state_service"],
        "add_xianxia_inventory_item",
        unexpected_save,
    )
    denied = client.post(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json={"expected_revision": starting_revision, "name": "Spirit Fan"},
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
        json={"expected_revision": "not-an-int", "name": "Spirit Fan"},
    )
    assert invalid_revision.status_code == 400
    assert invalid_revision.get_json()["error"]["code"] == "validation_error"
    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == starting_revision


def test_p34_identity_mismatch_stops_before_state_access_payload_or_service(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p80-p34")
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
        raise AssertionError("identity mismatch reached downstream inventory work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    _install_dependencies(
        app,
        monkeypatch,
        xianxia_inventory_item_payload=unexpected,
        get_character_state_service=unexpected,
    )
    response = client.post(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0, "name": "Spirit Fan"},
    )
    assert response.status_code == 404
