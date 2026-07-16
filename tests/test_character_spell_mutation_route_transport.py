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
import player_wiki.character_spell_mutation_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PREFIX = "/campaigns/linden-pass/characters/arden-march/spellcasting"
ROUTES = {
    "character_spell_add": {
        "path": f"{ROUTE_PREFIX}/add",
        "operation": "add",
        "message": "Spell list updated.",
        "form": MultiDict(
            (
                ("kind", "first-kind"),
                ("kind", "second-kind"),
                ("selected_value", "first-selected"),
                ("selected_value", "second-selected"),
                ("target_class_row_id", "first-row"),
                ("target_class_row_id", "second-row"),
            )
        ),
        "kwargs": {
            "kind": "first-kind",
            "selected_value": "first-selected",
            "target_class_row_id": "first-row",
        },
    },
    "character_spell_update": {
        "path": f"{ROUTE_PREFIX}/update",
        "operation": "update",
        "message": "Prepared spell selection updated.",
        "form": MultiDict(
            (
                ("spell_key", "first-spell"),
                ("spell_key", "second-spell"),
                ("prepared_value", "first-prepared"),
                ("prepared_value", "second-prepared"),
                ("target_class_row_id", "first-row"),
                ("target_class_row_id", "second-row"),
            )
        ),
        "kwargs": {
            "spell_key": "first-spell",
            "prepared_value": "first-prepared",
            "target_class_row_id": "first-row",
        },
    },
    "character_spell_remove": {
        "path": f"{ROUTE_PREFIX}/remove",
        "operation": "remove",
        "message": "Spell list updated.",
        "form": MultiDict(
            (
                ("spell_key", "first-spell"),
                ("spell_key", "second-spell"),
                ("target_class_row_id", "first-row"),
                ("target_class_row_id", "second-row"),
            )
        ),
        "kwargs": {
            "spell_key": "first-spell",
            "target_class_row_id": "first-row",
        },
    },
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
    campaign = SimpleNamespace(system="DND-5E")
    definition = SimpleNamespace(character_slug="arden-march")
    import_metadata = {"managed": True}
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
    )
    catalog = {"message-phb": object()}
    class_rows = [SimpleNamespace(row_id="class-row-1")]
    systems_service = object()

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
        "load_character_context": event("load", (campaign, record)),
        "campaign_supports_dnd5e_character_spellcasting_tools": event(
            "supports", True
        ),
        "redirect_unsupported_dnd5e_character_spellcasting_tools": event(
            "unsupported", "unsupported-result"
        ),
        "load_character_spell_management_support": event(
            "management", (catalog, class_rows)
        ),
        "get_systems_service": event("systems", systems_service),
        "run_character_definition_mutation": runner,
        "has_session_mode_access": event("access", True),
        "apply_character_spell_management_edit": event(
            "apply", (definition, import_metadata)
        ),
    }


def test_transport_has_exact_dependency_registration_and_composition_shape() -> None:
    expected_order = [
        "load_character_context",
        "campaign_supports_dnd5e_character_spellcasting_tools",
        "redirect_unsupported_dnd5e_character_spellcasting_tools",
        "load_character_spell_management_support",
        "get_systems_service",
        "run_character_definition_mutation",
        "has_session_mode_access",
        "apply_character_spell_management_edit",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterSpellMutationRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_spell_mutation_routes.py").read_text(
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
        and node.name == "register_character_spell_mutation_routes"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 3

    create_app = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    assert len(create_app.body) == 298
    assert sum(isinstance(node, ast.FunctionDef) for node in create_app.body) == 213
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(create_app)) == 229
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_spell_search_route",
            "register_character_spell_mutation_routes",
            "register_character_equipment_definition_routes",
        }
    }
    assert (
        calls["register_character_spell_search_route"],
        calls["register_character_spell_mutation_routes"],
        calls["register_character_equipment_definition_routes"],
    ) == (272, 273, 274)

    dependency_call = next(
        node
        for node in ast.walk(create_app.body[273])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSpellMutationRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:6])
    assert all(isinstance(by_name[name], ast.Lambda) for name in expected_order[6:])


def test_forwarded_dependencies_remain_late_module_global_lookups(app, monkeypatch):
    dependencies = dict(
        zip(
            _handler(app, "character_spell_add").__code__.co_freevars,
            _handler(app, "character_spell_add").__closure__ or (),
        )
    )["dependencies"].cell_contents
    marker = object()
    monkeypatch.setattr(app_module, "has_session_mode_access", lambda *args: marker)
    monkeypatch.setattr(
        app_module,
        "apply_character_spell_management_edit",
        lambda *args, **kwargs: (marker, args, kwargs),
    )
    assert dependencies.has_session_mode_access("campaign", "character") is marker
    assert dependencies.apply_character_spell_management_edit(
        "campaign", object(), {}, operation="add"
    )[0] is marker


def test_route_identity_methods_and_neighbor_order(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    assert endpoints.index("character_spell_search") < endpoints.index(
        "character_spell_add"
    )
    assert endpoints.index("character_spell_add") < endpoints.index(
        "character_spell_update"
    )
    assert endpoints.index("character_spell_update") < endpoints.index(
        "character_spell_remove"
    )
    assert endpoints.index("character_spell_remove") < endpoints.index(
        "character_equipment_add_systems"
    )
    for endpoint, expected in ROUTES.items():
        rule = next(rule for rule in rules if rule.endpoint == endpoint)
        assert rule.rule == expected["path"].replace(
            "linden-pass", "<campaign_slug>"
        ).replace("arden-march", "<character_slug>")
        assert rule.methods == {"POST", "OPTIONS"}
        assert client.options(expected["path"]).status_code == 200
        for method in ("get", "head", "put", "patch", "delete"):
            assert getattr(client, method)(expected["path"]).status_code == 405


@pytest.mark.parametrize("endpoint", tuple(ROUTES))
def test_handler_preserves_order_raw_first_values_operations_and_messages(
    app, monkeypatch, endpoint
):
    expected = ROUTES[endpoint]
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, endpoint, **_fixtures(events))
    with app.test_request_context(
        expected["path"], method="POST", data=expected["form"]
    ):
        assert _handler(app, endpoint)("linden-pass", "arden-march") == (
            "mutation-result"
        )
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supports",
        "runner",
        "management",
        "systems",
        "apply",
        "action_result",
    ]
    runner = events[3]
    assert runner[1] == ("linden-pass", "arden-march")
    assert runner[2]["anchor"] == "character-spell-manager"
    assert runner[2]["success_message"] == expected["message"]
    apply = events[6]
    assert apply[1][0] == "linden-pass"
    assert apply[2]["operation"] == expected["operation"]
    assert {name: apply[2][name] for name in expected["kwargs"]} == expected[
        "kwargs"
    ]


@pytest.mark.parametrize("endpoint", tuple(ROUTES))
def test_session_denial_occurs_after_load_without_support_or_mutation(
    app, monkeypatch, endpoint
):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["has_session_mode_access"] = (
        lambda *args: events.append(("access", args, {})) or False
    )
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(ROUTES[endpoint]["path"], method="POST"):
        with pytest.raises(Forbidden):
            _handler(app, endpoint)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["load", "access"]


@pytest.mark.parametrize("endpoint", tuple(ROUTES))
def test_missing_or_invalid_record_stops_before_access_systems_and_mutation(
    app, monkeypatch, endpoint
):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def missing(*args):
        events.append(("load", args, {}))
        raise NotFound()

    dependencies["load_character_context"] = missing
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(ROUTES[endpoint]["path"], method="POST"):
        with pytest.raises(NotFound):
            _handler(app, endpoint)("linden-pass", "..\\escape")
    assert [event[0] for event in events] == ["load"]


@pytest.mark.parametrize("endpoint", tuple(ROUTES))
def test_unsupported_system_redirects_without_management_or_mutation(
    app, monkeypatch, endpoint
):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["campaign_supports_dnd5e_character_spellcasting_tools"] = (
        lambda *args: events.append(("supports", args, {})) or False
    )
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(ROUTES[endpoint]["path"], method="POST"):
        assert _handler(app, endpoint)("linden-pass", "arden-march") == (
            "unsupported-result"
        )
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supports",
        "unsupported",
    ]


def test_scope_preserves_anonymous_next_visibility_and_assignment_non_bypass(
    client, sign_in, users, set_campaign_visibility
):
    path = ROUTES["character_spell_add"]["path"]
    set_campaign_visibility("linden-pass", characters="private")
    anonymous = client.post(path, follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/spellcasting/add"
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.post(path, follow_redirects=False).status_code == 404


def test_view_as_post_denial_precedes_handler_and_bearer_takes_precedence(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    endpoint = "character_spell_add"
    path = ROUTES[endpoint]["path"]
    set_campaign_visibility("linden-pass", characters="public")
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["run_character_definition_mutation"] = (
        lambda *args, **kwargs: events.append(("runner", args, kwargs)) or "ok"
    )
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.post(path).status_code == 403
    assert events == []
    token = issue_api_token(app, users["admin"]["email"], label="p55-spell-mutation")
    assert client.post(path, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supports",
        "runner",
    ]


@pytest.mark.parametrize("encoded_slug", ("..%5Cvictim", "C:%5Cescape"))
def test_p34_invalid_slug_has_no_state_access_or_spell_mutation_work(
    app, client, sign_in, users, monkeypatch, encoded_slug
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid slug reached eager spell mutation work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(CharacterStateStore, "initialize_state_if_missing", unexpected)
    _install_dependencies(
        app,
        monkeypatch,
        "character_spell_add",
        has_session_mode_access=unexpected,
        run_character_definition_mutation=unexpected,
    )
    response = client.post(
        "/campaigns/linden-pass/characters/"
        f"{encoded_slug}/spellcasting/add"
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "fault_stage",
    ("load", "access", "supports", "runner", "management", "systems", "apply"),
)
def test_faults_propagate_at_every_transport_stage(
    app, monkeypatch, fault_stage
):
    endpoint = "character_spell_add"
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    dependency_name = {
        "load": "load_character_context",
        "access": "has_session_mode_access",
        "supports": "campaign_supports_dnd5e_character_spellcasting_tools",
        "runner": "run_character_definition_mutation",
        "management": "load_character_spell_management_support",
        "systems": "get_systems_service",
        "apply": "apply_character_spell_management_edit",
    }[fault_stage]
    if fault_stage == "runner":
        dependencies[dependency_name] = fault
    elif fault_stage in {"management", "systems", "apply"}:
        original_runner = dependencies["run_character_definition_mutation"]
        dependencies[dependency_name] = fault
        dependencies["run_character_definition_mutation"] = original_runner
    else:
        dependencies[dependency_name] = fault
    _install_dependencies(app, monkeypatch, endpoint, **dependencies)
    with app.test_request_context(ROUTES[endpoint]["path"], method="POST"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app, endpoint)("linden-pass", "arden-march")
