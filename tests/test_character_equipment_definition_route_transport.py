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
import player_wiki.character_equipment_definition_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/campaigns/linden-pass/characters/arden-march/equipment"
ROUTES = {
    "character_equipment_add_systems": f"{PREFIX}/add-systems",
    "character_equipment_add_manual": f"{PREFIX}/add-manual",
    "character_equipment_add_campaign_item": f"{PREFIX}/add-campaign-item",
    "character_equipment_update": f"{PREFIX}/manual-1/update",
}


def _handler(app, endpoint: str):
    return inspect.unwrap(app.view_functions[endpoint])


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
    entry = SimpleNamespace(
        slug="rope-phb",
        title="Rope",
        entry_type="item",
        source_id="PHB",
        metadata={"weight": 10},
    )
    systems_service = SimpleNamespace(
        get_entry_by_slug_for_campaign=lambda *args: (
            events.append(("entry", args, {})) or entry
        )
    )
    definition = SimpleNamespace(
        equipment_catalog=[
            {
                "id": "manual-1",
                "source_kind": "manual_edit",
                "name": "Stored name",
                "weight": "4 lb.",
                "page_ref": "legacy/off-policy",
            },
            {
                "id": "systems-1",
                "source_kind": "manual_edit",
                "name": "Systems name",
                "weight": "7 lb.",
                "systems_ref": {"slug": "other-item"},
            },
        ]
    )
    record = SimpleNamespace(definition=definition, import_metadata={"managed": True})

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = kwargs["action"](record)
        events.append(("action_result", result, {}))
        return "mutation-result"

    return {
        "build_character_item_catalog": event("catalog", {"catalog": True}),
        "get_systems_service": event("systems", systems_service),
        "format_character_systems_item_weight": event("weight", "10 lb."),
        "build_character_systems_ref": event(
            "systems_ref", {"slug": "rope-phb"}
        ),
        "run_character_definition_mutation": runner,
        "load_campaign_context": event("campaign", SimpleNamespace(slug="linden-pass")),
        "list_visible_character_item_page_records": event(
            "item_pages", [SimpleNamespace(page_ref="items/compass")]
        ),
        "list_visible_character_page_records": event(
            "all_pages", [SimpleNamespace(page_ref="legacy/off-policy")]
        ),
        "normalize_character_page_ref": event("normalize", "legacy/off-policy"),
        "filter_character_page_records": event(
            "filter", [SimpleNamespace(page_ref="legacy/off-policy")]
        ),
        "character_items_section": "Items",
        "apply_equipment_catalog_edit": event(
            "apply", (definition, {"managed": True}, {"manual-1": 2})
        ),
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "build_character_item_catalog",
        "get_systems_service",
        "format_character_systems_item_weight",
        "build_character_systems_ref",
        "run_character_definition_mutation",
        "load_campaign_context",
        "list_visible_character_item_page_records",
        "list_visible_character_page_records",
        "normalize_character_page_ref",
        "filter_character_page_records",
        "character_items_section",
        "apply_equipment_catalog_edit",
    ]
    assert [
        field.name
        for field in fields(
            route_module.CharacterEquipmentDefinitionRouteDependencies
        )
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_equipment_definition_routes.py").read_text(
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
        and node.name == "register_character_equipment_definition_routes"
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
    assert len(create_app.body) == 298
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 211
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 226
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_spell_mutation_routes",
            "register_character_equipment_definition_routes",
            "register_character_equipment_state_route",
        }
    }
    assert (
        calls["register_character_spell_mutation_routes"],
        calls["register_character_equipment_definition_routes"],
        calls["register_character_equipment_state_route"],
    ) == (273, 274, 275)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[274])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterEquipmentDefinitionRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:11])
    assert isinstance(by_name["apply_equipment_catalog_edit"], ast.Lambda)


def test_routes_preserve_endpoint_methods_and_registration_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_spell_remove") < endpoints.index(
        "character_equipment_add_systems"
    )
    assert endpoints.index("character_equipment_add_systems") < endpoints.index(
        "character_equipment_add_manual"
    )
    assert endpoints.index("character_equipment_add_manual") < endpoints.index(
        "character_equipment_add_campaign_item"
    )
    assert endpoints.index("character_equipment_add_campaign_item") < endpoints.index(
        "character_equipment_update"
    )
    assert endpoints.index("character_equipment_update") < endpoints.index(
        "character_equipment_state_update"
    )
    for endpoint, path in ROUTES.items():
        rule = next(rule for rule in rules if rule.endpoint == endpoint)
        assert rule.rule == path.replace("linden-pass", "<campaign_slug>").replace(
            "arden-march", "<character_slug>"
        ).replace("manual-1", "<item_id>")
        assert rule.methods == {"POST", "OPTIONS"}
        assert client.options(path).status_code == 200
        for method in ("get", "head", "put", "patch", "delete"):
            assert getattr(client, method)(path).status_code == 405


@pytest.mark.parametrize(
    ("endpoint", "form", "expected_prefix", "message"),
    (
        (
            "character_equipment_add_systems",
            MultiDict(
                (
                    ("entry_slug", " rope-phb "),
                    ("entry_slug", "ignored"),
                    ("quantity", "2"),
                    ("quantity", "9"),
                    ("notes", "first note"),
                    ("notes", "ignored note"),
                )
            ),
            [
                "catalog",
                "runner",
                "systems",
                "entry",
                "systems",
                "weight",
                "systems_ref",
                "apply",
            ],
            "Systems item added to supplemental equipment.",
        ),
        (
            "character_equipment_add_manual",
            MultiDict(
                (
                    ("name", "First name"),
                    ("name", "Ignored name"),
                    ("quantity", "3"),
                    ("weight", "4 lb."),
                    ("notes", "first note"),
                )
            ),
            ["catalog", "runner", "systems", "apply"],
            "Custom item added to supplemental equipment.",
        ),
        (
            "character_equipment_add_campaign_item",
            MultiDict(
                (
                    ("page_ref", " items/compass "),
                    ("page_ref", "ignored"),
                    ("name", "First name"),
                    ("quantity", "5"),
                    ("weight", "1 lb."),
                    ("notes", "first note"),
                )
            ),
            ["campaign", "item_pages", "catalog", "runner", "systems", "apply"],
            "Campaign item added to supplemental equipment.",
        ),
    ),
)
def test_add_routes_preserve_eager_order_raw_first_forms_and_runner_contract(
    app, monkeypatch, endpoint, form, expected_prefix, message
):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)

    with app.test_request_context(ROUTES[endpoint], method="POST", data=form):
        assert _handler(app, endpoint)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events[:-1]] == expected_prefix
    runner = next(event for event in events if event[0] == "runner")
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "character-inventory-manager"
    assert runner[2]["success_message"] == message
    apply = next(event for event in events if event[0] == "apply")
    if endpoint == "character_equipment_add_systems":
        assert next(event for event in events if event[0] == "entry")[1] == (
            "linden-pass",
            "rope-phb",
        )
        assert apply[2]["quantity"] == "2"
        assert apply[2]["notes"] == "first note"
        assert apply[2]["name"] == "Rope"
        assert apply[2]["weight"] == "10 lb."
    elif endpoint == "character_equipment_add_manual":
        assert apply[2]["name"] == "First name"
        assert apply[2]["quantity"] == "3"
    else:
        assert apply[2]["page_ref"] == " items/compass "
        assert apply[2]["campaign_page_records"][0].page_ref == "items/compass"


@pytest.mark.parametrize(
    ("endpoint", "form", "message"),
    (
        (
            "character_equipment_add_systems",
            {"entry_slug": "   "},
            "Choose a Systems item to add.",
        ),
        (
            "character_equipment_add_campaign_item",
            {"page_ref": "   "},
            "Choose a valid item article to add.",
        ),
    ),
)
def test_route_owned_validation_messages_are_exact(
    app, monkeypatch, endpoint, form, message
):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(ROUTES[endpoint], method="POST", data=form):
        with pytest.raises(ValueError, match=message):
            _handler(app, endpoint)("linden-pass", "arden-march")
    assert not any(event[0] == "apply" for event in events)


def test_systems_add_preserves_enabled_item_and_duplicate_validation(
    app, monkeypatch
):
    endpoint = "character_equipment_add_systems"
    events: list[tuple] = []
    dependencies = _fixtures(events)
    missing_service = SimpleNamespace(get_entry_by_slug_for_campaign=lambda *args: None)
    dependencies["get_systems_service"] = lambda: missing_service
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(
        ROUTES[endpoint], method="POST", data={"entry_slug": "missing"}
    ):
        with pytest.raises(ValueError, match="Choose a valid enabled Systems item to add."):
            _handler(app, endpoint)("linden-pass", "arden-march")

    events.clear()
    dependencies = _fixtures(events)
    duplicate = SimpleNamespace(
        definition=SimpleNamespace(
            equipment_catalog=[
                {
                    "source_kind": "manual_edit",
                    "systems_ref": {"slug": "rope-phb"},
                }
            ]
        ),
        import_metadata={},
    )

    def runner(*args, **kwargs):
        return kwargs["action"](duplicate)

    dependencies["run_character_definition_mutation"] = runner
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(
        ROUTES[endpoint], method="POST", data={"entry_slug": "rope-phb"}
    ):
        with pytest.raises(ValueError, match="already listed in supplemental equipment"):
            _handler(app, endpoint)("linden-pass", "arden-march")


def test_update_preserves_manual_lookup_legacy_page_filter_and_raw_field_rules(
    app, monkeypatch
):
    endpoint = "character_equipment_update"
    events: list[tuple] = []
    dependencies = _fixtures(events)
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    form = MultiDict(
        (
            ("name", "New name"),
            ("name", "Ignored"),
            ("quantity", "8"),
            ("weight", "2 lb."),
            ("notes", "new notes"),
            ("page_ref", "items/new"),
        )
    )
    with app.test_request_context(ROUTES[endpoint], method="POST", data=form):
        assert _handler(app, endpoint)(
            "linden-pass", "arden-march", "manual-1"
        ) == "mutation-result"

    assert [event[0] for event in events[:-1]] == [
        "campaign",
        "all_pages",
        "catalog",
        "runner",
        "normalize",
        "normalize",
        "filter",
        "systems",
        "apply",
    ]
    filtered = next(event for event in events if event[0] == "filter")
    assert filtered[2] == {
        "section": "Items",
        "include_page_refs": {"legacy/off-policy"},
    }
    apply = next(event for event in events if event[0] == "apply")
    assert apply[2]["target_item_id"] == "manual-1"
    assert apply[2]["name"] == "New name"
    assert apply[2]["quantity"] == "8"
    assert apply[2]["weight"] == "2 lb."
    assert apply[2]["page_ref"] == "items/new"


def test_update_preserves_systems_backed_locked_fields(app, monkeypatch):
    endpoint = "character_equipment_update"
    events: list[tuple] = []
    dependencies = _fixtures(events)
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(
        ROUTES[endpoint],
        method="POST",
        data={
            "name": "Replacement",
            "quantity": "6",
            "weight": "1 lb.",
            "notes": "mutable",
            "page_ref": "items/new",
        },
    ):
        assert _handler(app, endpoint)(
            "linden-pass", "arden-march", "systems-1"
        ) == "mutation-result"

    apply = next(event for event in events if event[0] == "apply")
    assert apply[2]["name"] == "Systems name"
    assert apply[2]["weight"] == "7 lb."
    assert apply[2]["page_ref"] == ""
    assert apply[2]["systems_ref"] == {"slug": "other-item"}
    assert apply[2]["quantity"] == "6"
    assert apply[2]["notes"] == "mutable"


def test_update_rejects_nonmanual_or_missing_target(app, monkeypatch):
    endpoint = "character_equipment_update"
    events: list[tuple] = []
    dependencies = _fixtures(events)
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(ROUTES[endpoint], method="POST"):
        with pytest.raises(ValueError, match="Choose a valid supplemental equipment entry to update."):
            _handler(app, endpoint)("linden-pass", "arden-march", "missing")
    assert not any(event[0] == "apply" for event in events)


def test_scope_denial_performs_no_handler_eager_work(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("scope denial reached equipment handler")

    _install_dependencies(
        app,
        monkeypatch,
        "character_equipment_add_manual",
        build_character_item_catalog=unexpected,
    )
    assert client.post(ROUTES["character_equipment_add_manual"]).status_code == 404


def test_view_as_denial_and_bearer_precedence_preserve_global_envelope(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_character_definition_mutation"] = lambda *args, **kwargs: "ok"
    _install_dependencies(
        app,
        monkeypatch,
        "character_equipment_add_manual",
        **dependencies,
    )
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.post(ROUTES["character_equipment_add_manual"]).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p56-equipment")
    assert client.post(
        ROUTES["character_equipment_add_manual"], headers=api_headers(token)
    ).status_code == 200
    assert [event[0] for event in events] == ["catalog"]


def test_p34_failure_occurs_after_accepted_eager_reads_before_action(
    app, monkeypatch
):
    endpoint = "character_equipment_add_campaign_item"
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def invalid_runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        raise NotFound()

    dependencies["run_character_definition_mutation"] = invalid_runner
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(
        ROUTES[endpoint], method="POST", data={"page_ref": "items/compass"}
    ):
        with pytest.raises(NotFound):
            _handler(app, endpoint)("linden-pass", "..\\victim")
    assert [event[0] for event in events] == [
        "campaign",
        "item_pages",
        "catalog",
        "runner",
    ]


@pytest.mark.parametrize(
    ("endpoint", "fault_stage"),
    (
        ("character_equipment_add_systems", "catalog"),
        ("character_equipment_add_systems", "runner"),
        ("character_equipment_add_systems", "systems"),
        ("character_equipment_add_systems", "weight"),
        ("character_equipment_add_systems", "systems_ref"),
        ("character_equipment_add_systems", "apply"),
        ("character_equipment_add_campaign_item", "campaign"),
        ("character_equipment_add_campaign_item", "item_pages"),
        ("character_equipment_update", "all_pages"),
        ("character_equipment_update", "normalize"),
        ("character_equipment_update", "filter"),
    ),
)
def test_faults_propagate_at_every_transport_stage(
    app, monkeypatch, endpoint, fault_stage
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    key = {
        "catalog": "build_character_item_catalog",
        "runner": "run_character_definition_mutation",
        "systems": "get_systems_service",
        "weight": "format_character_systems_item_weight",
        "systems_ref": "build_character_systems_ref",
        "apply": "apply_equipment_catalog_edit",
        "campaign": "load_campaign_context",
        "item_pages": "list_visible_character_item_page_records",
        "all_pages": "list_visible_character_page_records",
        "normalize": "normalize_character_page_ref",
        "filter": "filter_character_page_records",
    }[fault_stage]
    dependencies[key] = fault
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    path = ROUTES[endpoint]
    item_id = "manual-1" if endpoint == "character_equipment_update" else None
    form = {
        "entry_slug": "rope-phb",
        "page_ref": "items/compass",
        "name": "Rope",
    }
    with app.test_request_context(path, method="POST", data=form):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            if item_id is None:
                _handler(app, endpoint)("linden-pass", "arden-march")
            else:
                _handler(app, endpoint)("linden-pass", "arden-march", item_id)


def test_forwarded_apply_helper_remains_late_monkeypatchable(
    app, monkeypatch
):
    endpoint = "character_equipment_add_manual"
    events: list[tuple] = []
    dependencies = _fixtures(events)
    raw_view = _handler(app, endpoint)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    original = freevars["dependencies"].cell_contents
    dependencies["apply_equipment_catalog_edit"] = original.apply_equipment_catalog_edit
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    monkeypatch.setattr(
        app_module,
        "apply_equipment_catalog_edit",
        lambda *args, **kwargs: events.append(("forwarded", args, kwargs)) or "ok",
    )
    with app.test_request_context(
        ROUTES[endpoint], method="POST", data={"name": "Rope"}
    ):
        assert _handler(app, endpoint)("linden-pass", "arden-march") == "mutation-result"
    assert any(event[0] == "forwarded" for event in events)
