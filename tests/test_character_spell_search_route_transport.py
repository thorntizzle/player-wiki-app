from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.app as app_module
import player_wiki.character_spell_search_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_repository import CharacterRepository
from player_wiki.character_store import CharacterStateStore
from player_wiki.system_policy import (
    DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE,
)
from tests.helpers.api_test_helpers import api_headers, issue_api_token


ENDPOINT = "character_spell_search"
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "spellcasting/spells/search"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    campaign = SimpleNamespace(system="DND-5E")
    definition = SimpleNamespace(character_slug="arden-march")
    record = SimpleNamespace(definition=definition)
    catalog = {"message-phb": object()}
    class_rows = [SimpleNamespace(row_id="class-row-1")]

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    return {
        "load_character_context": event("load", (campaign, record)),
        "campaign_supports_dnd5e_character_spellcasting_tools": event(
            "supports", True
        ),
        "load_character_spell_management_support": event(
            "management", (catalog, class_rows)
        ),
        "has_session_mode_access": event("access", True),
        "search_character_spell_management_options": event(
            "search",
            (
                [
                    {
                        "entry_slug": "message-phb",
                        "title": "Message",
                        "level_label": "Cantrip",
                        "source_id": "PHB",
                        "select_label": "Message - Cantrip - PHB",
                    }
                ],
                "Found 1 matching cantrips.",
            ),
        ),
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    expected_order = [
        "load_character_context",
        "campaign_supports_dnd5e_character_spellcasting_tools",
        "load_character_spell_management_support",
        "has_session_mode_access",
        "search_character_spell_management_options",
    ]
    assert [
        field.name
        for field in fields(route_module.CharacterSpellSearchRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_spell_search_routes.py").read_text(encoding="utf-8")
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
        and node.name == "register_character_spell_search_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1

    create_app = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    calls = {
        node.value.func.id: index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id
        in {
            "register_character_equipment_search_route",
            "register_character_spell_search_route",
        }
    }
    mutation_index = next(
        index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_character_spell_mutation_routes"
    )
    assert (
        calls["register_character_equipment_search_route"],
        calls["register_character_spell_search_route"],
        mutation_index,
    ) == (270, 271, 272)

    registrar_call = create_app.body[271].value
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterSpellSearchRouteDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:3])
    assert all(isinstance(by_name[name], ast.Lambda) for name in expected_order[3:])


def test_forwarded_dependencies_remain_late_module_global_lookups(app, monkeypatch):
    dependencies = dict(
        zip(_handler(app).__code__.co_freevars, _handler(app).__closure__ or ())
    )["dependencies"].cell_contents
    marker = object()
    monkeypatch.setattr(app_module, "has_session_mode_access", lambda *args: marker)
    monkeypatch.setattr(
        app_module,
        "search_character_spell_management_options",
        lambda *args, **kwargs: (marker, args, kwargs),
    )
    assert dependencies.has_session_mode_access("campaign", "character") is marker
    assert dependencies.search_character_spell_management_options(
        "definition", query="m"
    )[0] is marker


def test_route_identity_methods_content_type_and_neighbor_order(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "spellcasting/spells/search"
    )
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert endpoints.index("character_equipment_systems_item_search") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("character_spell_add")
    assert client.get(f"{ROUTE_PATH}?q=message").content_type == "application/json"
    assert client.head(f"{ROUTE_PATH}?q=message").status_code == 200
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_handler_preserves_order_first_repeated_query_and_response(app, monkeypatch, method):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    with app.test_request_context(
        f"{ROUTE_PATH}?q=first&q=second&kind=cantrip&kind=spell&"
        "target_class_row_id=class-row-1&target_class_row_id=class-row-2",
        method=method,
    ):
        response = _handler(app)("linden-pass", "arden-march")
    assert response.get_json() == {
        "results": [
            {
                "entry_slug": "message-phb",
                "title": "Message",
                "level_label": "Cantrip",
                "source_id": "PHB",
                "select_label": "Message - Cantrip - PHB",
            }
        ],
        "message": "Found 1 matching cantrips.",
    }
    assert [event[0] for event in events] == [
        "load",
        "access",
        "supports",
        "management",
        "search",
    ]
    search = events[-1]
    assert search[2] == {
        "spell_catalog": {"message-phb": next(iter(search[2]["spell_catalog"].values()))},
        "selected_class_rows": search[2]["selected_class_rows"],
        "query": "first",
        "kind": "cantrip",
        "target_class_row_id": "class-row-1",
    }


def test_session_denial_occurs_after_load_without_support_or_search(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["has_session_mode_access"] = (
        lambda *args: events.append(("access", args, {})) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(Forbidden):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["load", "access"]


def test_missing_or_invalid_record_stops_before_access_support_and_search(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def missing(*args):
        events.append(("load", args, {}))
        raise NotFound()

    dependencies["load_character_context"] = missing
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(NotFound):
            _handler(app)("linden-pass", "..\\escape")
    assert [event[0] for event in events] == ["load"]


def test_unsupported_system_returns_exact_404_without_management_or_search(app, monkeypatch):
    events: list[tuple] = []
    dependencies = _fixtures(events)
    dependencies["campaign_supports_dnd5e_character_spellcasting_tools"] = (
        lambda *args: events.append(("supports", args, {})) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        response, status = _handler(app)("linden-pass", "arden-march")
    assert status == 404
    assert response.get_json() == {
        "results": [],
        "message": DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE,
    }
    assert [event[0] for event in events] == ["load", "access", "supports"]


def test_scope_preserves_anonymous_next_visibility_and_assignment_non_bypass(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="private")
    anonymous = client.get(f"{ROUTE_PATH}?q=message", follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/"
        "spellcasting/spells/search?q%3Dmessage"
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.get(f"{ROUTE_PATH}?q=message").status_code == 404
    set_campaign_visibility("linden-pass", characters="public")
    assert client.get(f"{ROUTE_PATH}?q=message").status_code == 200


def test_valid_record_can_lazy_initialize_before_session_denial(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="public")
    with app.app_context():
        state_store = app.extensions["character_state_store"]
        state_store.delete_state("linden-pass", "arden-march")
        assert state_store.get_state("linden-pass", "arden-march") is None
    sign_in(users["party"]["email"], users["party"]["password"])
    assert client.get(f"{ROUTE_PATH}?q=message").status_code == 403
    with app.app_context():
        assert state_store.get_state("linden-pass", "arden-march") is not None


def test_view_as_and_bearer_precedence(app, client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.get(f"{ROUTE_PATH}?q=message").status_code == 403
    token = issue_api_token(app, users["admin"]["email"], label="p54-spell-search")
    assert client.get(
        f"{ROUTE_PATH}?q=message", headers=api_headers(token)
    ).status_code == 200


@pytest.mark.parametrize("encoded_slug", ("..%5Cvictim", "C:%5Cescape"))
def test_p34_invalid_slug_has_no_state_access_or_spell_work(
    app, client, sign_in, users, monkeypatch, encoded_slug
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid slug reached eager spell work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(CharacterStateStore, "initialize_state_if_missing", unexpected)
    _install_dependencies(
        app,
        monkeypatch,
        has_session_mode_access=unexpected,
        load_character_spell_management_support=unexpected,
        search_character_spell_management_options=unexpected,
    )
    response = client.get(
        "/campaigns/linden-pass/characters/"
        f"{encoded_slug}/spellcasting/spells/search?q=message"
    )
    assert response.status_code == 404


def test_definition_identity_mismatch_has_no_state_access_or_spell_work(
    app, client, sign_in, users, monkeypatch
):
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    payload["character_slug"] = "different-character"
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("identity mismatch reached eager spell work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(CharacterStateStore, "initialize_state_if_missing", unexpected)
    _install_dependencies(
        app,
        monkeypatch,
        has_session_mode_access=unexpected,
        load_character_spell_management_support=unexpected,
        search_character_spell_management_options=unexpected,
    )
    assert client.get(f"{ROUTE_PATH}?q=message").status_code == 404


@pytest.mark.parametrize(
    "fault_stage", ("load", "access", "supports", "management", "search", "jsonify")
)
def test_faults_propagate_at_every_transport_stage(app, monkeypatch, fault_stage):
    events: list[tuple] = []
    dependencies = _fixtures(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    dependency_name = {
        "load": "load_character_context",
        "access": "has_session_mode_access",
        "supports": "campaign_supports_dnd5e_character_spellcasting_tools",
        "management": "load_character_spell_management_support",
        "search": "search_character_spell_management_options",
    }.get(fault_stage)
    if dependency_name:
        dependencies[dependency_name] = fault
    else:
        monkeypatch.setattr(route_module, "jsonify", fault)
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march")
