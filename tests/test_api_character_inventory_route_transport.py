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
import player_wiki.character_inventory_api_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "bf249f145f754d378e7c92a65302ab71acb12243"
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/"
    "session/inventory/crossbow-bolts-4"
)
ENDPOINT = "api.character_inventory_update"
DEPENDENCY_ORDER = [
    "api_login_required",
    "run_character_mutation",
    "is_xianxia_system",
    "get_character_state_service",
]
PAYLOAD_KEYS = ["expected_revision", "quantity", "delta"]


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
    system="dnd5e",
    payload=None,
    xianxia=False,
    service_error=None,
):
    record = SimpleNamespace(
        slug="arden-march",
        definition=SimpleNamespace(system=system),
    )
    payload = payload or RecordingPayload(
        {"expected_revision": "17", "quantity": 8, "delta": -1},
        events,
    )

    def is_xianxia(*args, **kwargs):
        events.append(("system", args, kwargs))
        return xianxia

    def update_inventory(*args, **kwargs):
        events.append(("ordinary_save", args, kwargs))
        if service_error is not None:
            raise service_error
        return "ordinary-state"

    def update_xianxia(*args, **kwargs):
        events.append(("xianxia_save", args, kwargs))
        if service_error is not None:
            raise service_error
        return "xianxia-state"

    service = SimpleNamespace(
        update_inventory_quantity=update_inventory,
        update_xianxia_inventory_quantity=update_xianxia,
    )

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
        "is_xianxia_system": is_xianxia,
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    assert [
        field.name for field in fields(route_module.CharacterInventoryApiDependencies)
    ] == DEPENDENCY_ORDER

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_inventory_api_routes.py").read_text(encoding="utf-8")
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_inventory_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_inventory_update"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_inventory_api_route"
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
        and node.id == "api_campaign_scope_access_required"
        for node in ast.walk(route_tree)
    )

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 219
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 229
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
    assert len(api_route_decorators) == 51

    assert isinstance(register_api.body[244], ast.Expr)
    assert register_api.body[244].value.func.id == (
        "register_character_item_action_api_route"
    )
    assert isinstance(register_api.body[245], ast.Expr)
    assert register_api.body[245].value.func.id == (
        "register_character_inventory_api_route"
    )
    assert isinstance(register_api.body[246], ast.FunctionDef)
    assert register_api.body[246].name == "xianxia_inventory_item_payload"

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[245])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterInventoryApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(
        isinstance(by_name[name], ast.Name)
        for name in (
            "api_login_required",
            "run_character_mutation",
            "get_character_state_service",
        )
    )
    forwarded = by_name["is_xianxia_system"]
    assert isinstance(forwarded, ast.Lambda)
    assert isinstance(forwarded.body, ast.Call)
    assert isinstance(forwarded.body.func, ast.Name)
    assert forwarded.body.func.id == "is_xianxia_system"


def test_moved_handler_and_action_keep_canonical_ast_and_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_inventory_api_routes.py")
        .read_text(encoding="utf-8")
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_inventory_update"
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
    original = old_register.body[245]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_inventory_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {162, 163, 164, 245, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_login_wrapper_and_registration_order(
    app, client
):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("api.character_item_action_use") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_xianxia_inventory_add")
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/inventory/<item_id>"
    )
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_inventory_update"
    )


@pytest.mark.parametrize(
    ("xianxia", "save_event"),
    ((False, "ordinary_save"), (True, "xianxia_save")),
)
def test_handler_preserves_system_service_payload_and_save_evaluation_order(
    app, monkeypatch, xianxia, save_event
):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, xianxia=xianxia),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert (
            _handler(app)("linden-pass", "arden-march", "crossbow-bolts-4")
            == "mutation-result"
        )

    assert [event[0] for event in events] == [
        "runner",
        "system",
        "service",
        "payload_get",
        "payload_get",
        "payload_get",
        save_event,
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == PAYLOAD_KEYS
    save = next(event for event in events if event[0] == save_event)
    assert save[1][:2] == (
        SimpleNamespace(
            slug="arden-march",
            definition=SimpleNamespace(system="dnd5e"),
        ),
        "crossbow-bolts-4",
    )
    assert save[2] == {
        "expected_revision": 17,
        "quantity": 8,
        "delta": -1,
        "updated_by_user_id": 42,
    }
    assert not any(
        event[0] == ("ordinary_save" if xianxia else "xianxia_save")
        for event in events
    )


def test_missing_values_and_invalid_revision_keep_exact_evaluation_boundaries(
    app, monkeypatch
):
    events: list[tuple] = []
    payload = RecordingPayload({"expected_revision": 4}, events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert (
            _handler(app)("linden-pass", "arden-march", "crossbow-bolts-4")
            == "mutation-result"
        )
    save = next(event for event in events if event[0] == "ordinary_save")
    assert save[2]["quantity"] is None
    assert save[2]["delta"] is None

    events = []
    payload = RecordingPayload({"expected_revision": "not-an-int"}, events)
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload=payload),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march", "crossbow-bolts-4")
    assert [event[0] for event in events] == [
        "runner",
        "system",
        "service",
        "payload_get",
    ]


def test_system_predicate_remains_forwarded_from_api_module_global(app, monkeypatch):
    events: list[tuple] = []
    replacements = _dependencies(events)
    replacements.pop("is_xianxia_system")
    _install_dependencies(app, monkeypatch, **replacements)

    def forwarded_system(*args, **kwargs):
        events.append(("forwarded_system", args, kwargs))
        return True

    monkeypatch.setattr(api_module, "is_xianxia_system", forwarded_system)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert (
            _handler(app)("linden-pass", "arden-march", "crossbow-bolts-4")
            == "mutation-result"
        )
    assert "forwarded_system" in [event[0] for event in events]
    assert "xianxia_save" in [event[0] for event in events]
    assert "ordinary_save" not in [event[0] for event in events]


@pytest.mark.parametrize("fault_stage", ("runner", "system", "service", "save"))
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app, monkeypatch, fault_stage
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        replacements["run_character_mutation"] = fault
    elif fault_stage == "system":
        replacements["is_xianxia_system"] = fault
    elif fault_stage == "service":
        replacements["get_character_state_service"] = fault
    else:
        replacements["get_character_state_service"] = lambda: SimpleNamespace(
            update_inventory_quantity=fault,
            update_xianxia_inventory_quantity=fault,
        )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march", "crossbow-bolts-4")


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
    assert client.patch(ROUTE_PATH).status_code == 403
    assert events == []

    token = issue_api_token(app, users["admin"]["email"], label="p79-bearer")
    response = client.patch(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_runner_preserves_access_invalid_json_and_precommit_atomicity(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="p79-owner")
    party_token = issue_api_token(app, users["party"]["email"], label="p79-party")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision

    def unexpected_save(*args, **kwargs):
        raise AssertionError("denied or malformed request reached inventory persistence")

    monkeypatch.setattr(
        app.extensions["character_state_service"],
        "update_inventory_quantity",
        unexpected_save,
    )
    denied = client.patch(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json={"expected_revision": starting_revision, "quantity": 2},
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
        json={"expected_revision": "not-an-int", "quantity": 2},
    )
    assert invalid_revision.status_code == 400
    assert invalid_revision.get_json()["error"]["code"] == "validation_error"
    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == starting_revision


def test_p34_identity_mismatch_stops_before_state_access_or_inventory_service(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p79-p34")
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
    monkeypatch.setattr(
        app.extensions["character_state_service"],
        "update_inventory_quantity",
        unexpected,
    )
    response = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": 0, "quantity": 2},
    )
    assert response.status_code == 404


def test_committed_inventory_state_survives_refresh_serialization_fault(
    client, app, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p79-postcommit")
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
            json={"expected_revision": starting_revision, "quantity": 17},
        )

    with app.app_context():
        persisted = original_load("linden-pass", "arden-march")
    assert persisted is not None
    assert persisted.state_record.revision == starting_revision + 1
    inventory = {row["id"]: row for row in persisted.state_record.state["inventory"]}
    assert inventory["crossbow-bolts-4"]["quantity"] == 17
