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
import player_wiki.character_session_xianxia_inventory_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = "/campaigns/linden-pass/characters/arden-march/session/xianxia-inventory"
ROUTES = {
    "character_session_xianxia_inventory_add": f"{BASE_PATH}/add",
    "character_session_xianxia_inventory_update": f"{BASE_PATH}/jade-sword/update",
    "character_session_xianxia_inventory_remove": f"{BASE_PATH}/jade-sword/remove",
    "character_session_xianxia_inventory_equipped": f"{BASE_PATH}/jade-sword/equipped",
}


def _handler(app, endpoint: str):
    return inspect.unwrap(app.view_functions[endpoint])


def _dependencies(app, endpoint: str):
    raw_view = _handler(app, endpoint)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"].cell_contents


def _install_dependencies(app, monkeypatch, endpoint: str, **replacements) -> None:
    raw_view = _handler(app, endpoint)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    current = freevars["dependencies"].cell_contents
    monkeypatch.setattr(
        freevars["dependencies"],
        "cell_contents",
        replace(current, **replacements),
    )


def _fixtures(events: list[tuple]):
    record = SimpleNamespace(definition=SimpleNamespace(system="xianxia"), state_record={})

    def operation(name):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return f"{name}-state"

        return invoke

    service = SimpleNamespace(
        add_xianxia_inventory_item=operation("add"),
        update_xianxia_inventory_item=operation("update"),
        remove_xianxia_inventory_item=operation("remove"),
        update_xianxia_inventory_equipped_state=operation("equipped"),
    )

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record, 17, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def payload(*args, **kwargs):
        events.append(("payload", args, kwargs))
        return {"name": "Jade Sword", "quantity": "2"}

    return {
        "run_session_mutation": runner,
        "get_character_state_service": get_service,
        "_xianxia_inventory_item_payload_from_form": payload,
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


ORIGINAL_HANDLERS = ast.parse(
    '''
def character_session_xianxia_inventory_add(campaign_slug: str, character_slug: str):
    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="xianxia-inventory",
        success_message="Inventory item added.",
        action=lambda record, expected_revision, user_id: get_character_state_service().add_xianxia_inventory_item(
            record,
            _xianxia_inventory_item_payload_from_form(),
            expected_revision=expected_revision,
            updated_by_user_id=user_id,
        ),
    )

def character_session_xianxia_inventory_update(campaign_slug: str, character_slug: str, item_id: str):
    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="xianxia-inventory",
        success_message="Inventory item updated.",
        action=lambda record, expected_revision, user_id: get_character_state_service().update_xianxia_inventory_item(
            record,
            item_id,
            _xianxia_inventory_item_payload_from_form(),
            expected_revision=expected_revision,
            updated_by_user_id=user_id,
        ),
    )

def character_session_xianxia_inventory_remove(campaign_slug: str, character_slug: str, item_id: str):
    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="xianxia-inventory",
        success_message="Inventory item removed.",
        action=lambda record, expected_revision, user_id: get_character_state_service().remove_xianxia_inventory_item(
            record,
            item_id,
            expected_revision=expected_revision,
            updated_by_user_id=user_id,
        ),
    )

def character_session_xianxia_inventory_equipped(campaign_slug: str, character_slug: str, item_id: str):
    return run_session_mutation(
        campaign_slug,
        character_slug,
        anchor="xianxia-inventory",
        success_message="Equipment state updated.",
        action=lambda record, expected_revision, user_id: get_character_state_service().update_xianxia_inventory_equipped_state(
            record,
            item_id,
            expected_revision=expected_revision,
            is_equipped=request.form.get("is_equipped") == "1",
            updated_by_user_id=user_id,
        ),
    )
'''
).body


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "run_session_mutation",
        "get_character_state_service",
        "_xianxia_inventory_item_payload_from_form",
    ]
    assert [
        field.name
        for field in fields(
            route_module.CharacterSessionXianxiaInventoryRouteDependencies
        )
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_session_xianxia_inventory_routes.py").read_text(
            encoding="utf-8"
        )
    )
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in ROUTES
    }
    assert set(handlers) == set(ROUTES)
    assert all(handler.decorator_list == [] for handler in handlers.values())
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in ROUTES
        for node in ast.walk(app_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_session_xianxia_inventory_routes"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 4
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
        (288, "register_character_session_inventory_route"),
        (289, "register_character_session_xianxia_inventory_routes"),
    ):
        assert isinstance(create_app.body[index], ast.Expr)
        assert isinstance(create_app.body[index].value, ast.Call)
        assert isinstance(create_app.body[index].value.func, ast.Name)
        assert create_app.body[index].value.func.id == registrar_name
    assert isinstance(create_app.body[290], ast.Expr)
    assert isinstance(create_app.body[290].value, ast.Call)
    assert isinstance(create_app.body[290].value.func, ast.Name)
    assert (
        create_app.body[290].value.func.id
        == "register_character_session_currency_route"
    )

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[289])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSessionXianxiaInventoryRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(value, ast.Name) for value in by_name.values())


def test_all_four_moved_handlers_and_actions_keep_canonical_ast_parity() -> None:
    route_tree = ast.parse(
        (
            PROJECT_ROOT
            / "player_wiki"
            / "character_session_xianxia_inventory_routes.py"
        ).read_text(encoding="utf-8")
    )
    moved = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in ROUTES
    }
    original = {
        node.name: node
        for node in ORIGINAL_HANDLERS
        if isinstance(node, ast.FunctionDef)
    }
    assert set(moved) == set(original) == set(ROUTES)
    for endpoint in ROUTES:
        assert _canonical_handler(moved[endpoint]) == _canonical_handler(
            original[endpoint]
        )


def test_routes_preserve_endpoints_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    expected_order = list(ROUTES)
    assert endpoints.index("character_session_inventory") < endpoints.index(
        expected_order[0]
    )
    assert endpoints.index(expected_order[-1]) < endpoints.index(
        "character_session_currency"
    )
    assert [endpoints.index(endpoint) for endpoint in expected_order] == sorted(
        endpoints.index(endpoint) for endpoint in expected_order
    )
    for endpoint, path in ROUTES.items():
        rule = next(rule for rule in rules if rule.endpoint == endpoint)
        assert rule.methods == {"POST", "OPTIONS"}
        assert client.options(path).status_code == 200
        for method in ("get", "head", "put", "patch", "delete"):
            assert getattr(client, method)(path).status_code == 405


@pytest.mark.parametrize(
    ("endpoint", "operation", "expected_events"),
    (
        (
            "character_session_xianxia_inventory_add",
            "add",
            ["runner", "service", "payload", "add", "action_result"],
        ),
        (
            "character_session_xianxia_inventory_update",
            "update",
            ["runner", "service", "payload", "update", "action_result"],
        ),
        (
            "character_session_xianxia_inventory_remove",
            "remove",
            ["runner", "service", "remove", "action_result"],
        ),
        (
            "character_session_xianxia_inventory_equipped",
            "equipped",
            ["runner", "service", "form", "equipped", "action_result"],
        ),
    ),
)
def test_handlers_preserve_dependency_form_and_operation_order(
    app,
    monkeypatch,
    endpoint,
    operation,
    expected_events,
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, endpoint, **_fixtures(events))

    class RecordingForm:
        def get(self, key):
            events.append(("form", (key,), {}))
            assert key == "is_equipped"
            return "1"

    monkeypatch.setattr(route_module, "request", SimpleNamespace(form=RecordingForm()))
    args = ["linden-pass", "arden-march"]
    if endpoint != "character_session_xianxia_inventory_add":
        args.append("jade-sword")
    with app.test_request_context(ROUTES[endpoint], method="POST"):
        assert _handler(app, endpoint)(*args) == "mutation-result"

    assert [event[0] for event in events] == expected_events
    runner = events[0]
    assert runner[1][:2] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "xianxia-inventory"
    expected_message = {
        "add": "Inventory item added.",
        "update": "Inventory item updated.",
        "remove": "Inventory item removed.",
        "equipped": "Equipment state updated.",
    }[operation]
    assert runner[2]["success_message"] == expected_message
    call = next(event for event in events if event[0] == operation)
    assert call[1][0].definition.system == "xianxia"
    if operation != "add":
        assert call[1][1] == "jade-sword"
    if operation in {"add", "update"}:
        assert {"name": "Jade Sword", "quantity": "2"} in call[1]
    assert call[2]["expected_revision"] == 17
    assert call[2]["updated_by_user_id"] == 42
    if operation == "equipped":
        assert call[2]["is_equipped"] is True


def test_captured_payload_helper_preserves_tags_first_and_all_form_field_order(
    app,
    monkeypatch,
):
    helper = _dependencies(
        app,
        "character_session_xianxia_inventory_add",
    )._xianxia_inventory_item_payload_from_form
    values = {
        "tags": " weapon, ritual, ",
        "item_id": " jade-sword ",
        "name": " Jade Sword ",
        "quantity": " 2 ",
        "item_nature": "Relic",
        "item_type": "Weapon",
        "notes": " Bound blade ",
        "catalog_ref": " jade-catalog ",
        "systems_ref_slug": " jade-sword ",
        "systems_ref_entry_type": " equipment ",
        "systems_ref_source_id": " xianxia-core ",
        "equippable": "1",
        "is_equipped": "0",
    }
    events: list[str] = []

    class RecordingForm:
        def get(self, key, default=None):
            events.append(key)
            return values.get(key, default)

        def __contains__(self, key):
            events.append(f"contains:{key}")
            return key in values

    monkeypatch.setattr(
        app_module,
        "request",
        SimpleNamespace(form=RecordingForm()),
    )
    assert helper() == {
        "id": "jade-sword",
        "name": "Jade Sword",
        "quantity": " 2 ",
        "item_nature": "Relic",
        "item_type": "Weapon",
        "notes": "Bound blade",
        "tags": ["weapon", "ritual"],
        "catalog_ref": "jade-catalog",
        "systems_ref": {
            "slug": "jade-sword",
            "entry_type": "equipment",
            "source_id": "xianxia-core",
        },
        "equippable": True,
        "is_equipped": False,
    }
    assert events == [
        "tags",
        "item_id",
        "name",
        "quantity",
        "item_nature",
        "item_type",
        "notes",
        "catalog_ref",
        "systems_ref_slug",
        "systems_ref_entry_type",
        "systems_ref_source_id",
        "equippable",
        "contains:is_equipped",
        "is_equipped",
    ]


def test_equipped_uses_first_repeated_raw_form_value(app, monkeypatch):
    endpoint = "character_session_xianxia_inventory_equipped"
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, endpoint, **_fixtures(events))
    data = MultiDict([("is_equipped", "0"), ("is_equipped", "1")])
    with app.test_request_context(ROUTES[endpoint], method="POST", data=data):
        assert (
            _handler(app, endpoint)("linden-pass", "arden-march", "jade-sword")
            == "mutation-result"
        )
    call = next(event for event in events if event[0] == "equipped")
    assert call[2]["is_equipped"] is False


@pytest.mark.parametrize("endpoint", ROUTES)
def test_scope_denial_performs_no_runner_service_payload_or_form_work(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
    endpoint,
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached Xianxia inventory handler")

    _install_dependencies(
        app,
        monkeypatch,
        endpoint,
        run_session_mutation=unexpected,
        get_character_state_service=unexpected,
        _xianxia_inventory_item_payload_from_form=unexpected,
    )
    assert client.post(ROUTES[endpoint]).status_code == 404


def test_view_as_denial_and_bearer_precedence_preserve_global_envelope(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    endpoint = "character_session_xianxia_inventory_add"
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_session_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTES[endpoint]).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p68-xianxia-inventory")
    assert (
        client.post(ROUTES[endpoint], headers=api_headers(token)).status_code == 200
    )
    assert [event[0] for event in events] == ["runner"]


@pytest.mark.parametrize("endpoint", ROUTES)
def test_p34_failure_enters_captured_runner_before_service_payload_or_form_work(
    app,
    monkeypatch,
    endpoint,
):
    events: list[tuple] = []

    def invalid_runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        raise NotFound()

    def unexpected(*args, **kwargs):
        raise AssertionError("P34 failure reached downstream Xianxia inventory work")

    _install_dependencies(
        app,
        monkeypatch,
        endpoint,
        run_session_mutation=invalid_runner,
        get_character_state_service=unexpected,
        _xianxia_inventory_item_payload_from_form=unexpected,
    )
    malicious_path = ROUTES[endpoint].replace("arden-march", "..\\victim")
    args = ["linden-pass", "..\\victim"]
    if endpoint != "character_session_xianxia_inventory_add":
        args.append("jade-sword")
    with app.test_request_context(malicious_path, method="POST"):
        with pytest.raises(NotFound):
            _handler(app, endpoint)(*args)
    assert [event[0] for event in events] == ["runner"]


@pytest.mark.parametrize(
    ("endpoint", "fault_stage"),
    (
        ("character_session_xianxia_inventory_add", "runner"),
        ("character_session_xianxia_inventory_add", "service"),
        ("character_session_xianxia_inventory_add", "payload"),
        ("character_session_xianxia_inventory_add", "operation"),
        ("character_session_xianxia_inventory_update", "operation"),
        ("character_session_xianxia_inventory_remove", "operation"),
        ("character_session_xianxia_inventory_equipped", "form"),
        ("character_session_xianxia_inventory_equipped", "operation"),
    ),
)
def test_faults_propagate_at_every_transport_stage(
    app,
    monkeypatch,
    endpoint,
    fault_stage,
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    operation_name = endpoint.rsplit("_", 1)[-1]
    if fault_stage == "runner":
        dependencies["run_session_mutation"] = fault
    elif fault_stage == "service":
        dependencies["get_character_state_service"] = fault
    elif fault_stage == "payload":
        dependencies["_xianxia_inventory_item_payload_from_form"] = fault
    elif fault_stage == "operation":
        method_name = {
            "add": "add_xianxia_inventory_item",
            "update": "update_xianxia_inventory_item",
            "remove": "remove_xianxia_inventory_item",
            "equipped": "update_xianxia_inventory_equipped_state",
        }[operation_name]
        dependencies["get_character_state_service"] = lambda: SimpleNamespace(
            **{method_name: fault}
        )
    else:
        monkeypatch.setattr(
            route_module,
            "request",
            SimpleNamespace(form=SimpleNamespace(get=fault)),
        )

    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    args = ["linden-pass", "arden-march"]
    if endpoint != "character_session_xianxia_inventory_add":
        args.append("jade-sword")
    with app.test_request_context(ROUTES[endpoint], method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app, endpoint)(*args)
