from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import player_wiki.app as app_module
import player_wiki.character_equipment_search_routes as search_routes
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_repository import CharacterRepository
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token


ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/"
    "equipment/systems-items/search"
)
ENDPOINT = "character_equipment_systems_item_search"


def _entry(
    *,
    slug: str,
    title: str,
    source_id: object = "PHB",
    weight: object = None,
):
    return SimpleNamespace(
        slug=slug,
        title=title,
        source_id=source_id,
        metadata={"weight": weight},
    )


def test_equipment_search_transport_has_exact_dependency_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(search_routes.CharacterEquipmentSearchRouteDependencies)
    ] == [
        "load_character_context",
        "get_systems_service",
        "format_character_systems_item_weight",
        "has_session_mode_access",
    ]

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_equipment_search_routes.py").read_text(
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
        and node.name == "register_character_equipment_search_route"
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
    controls_index = next(
        index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_character_controls_delete_route"
    )
    registration_index = next(
        index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_character_equipment_search_route"
    )
    spell_index = next(
        index
        for index, node in enumerate(create_app.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_character_spell_search_route"
    )
    assert (controls_index, registration_index, spell_index) == (269, 270, 271)

    registration = create_app.body[registration_index].value
    dependencies = next(
        keyword.value for keyword in registration.keywords if keyword.arg == "dependencies"
    )
    keyword_values = {keyword.arg: keyword.value for keyword in dependencies.keywords}
    for name in (
        "load_character_context",
        "get_systems_service",
        "format_character_systems_item_weight",
    ):
        assert isinstance(keyword_values[name], ast.Name)
        assert keyword_values[name].id == name
    assert isinstance(keyword_values["has_session_mode_access"], ast.Lambda)


def test_equipment_search_preserves_endpoint_methods_and_registration_order(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)

    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/systems-items/search"
    )
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    assert client.head(f"{ROUTE_PATH}?q=rope").status_code == 200
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert endpoints.index("character_controls_delete") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_spell_search")


def test_equipment_search_scope_preserves_missing_anonymous_and_assignment_non_bypass(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="private")
    anonymous = client.get(f"{ROUTE_PATH}?q=rope", follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/"
        "equipment/systems-items/search?q%3Drope"
    )
    assert client.get(
        "/campaigns/missing/characters/arden-march/equipment/systems-items/search?q=rope"
    ).status_code == 404

    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.get(f"{ROUTE_PATH}?q=rope").status_code == 404

    set_campaign_visibility("linden-pass", characters="public")
    assert client.get(f"{ROUTE_PATH}?q=rope").status_code == 200


@pytest.mark.parametrize("user_key", ("party", "observer", "outsider"))
def test_equipment_search_valid_record_loads_before_session_denial(
    client, sign_in, users, set_campaign_visibility, monkeypatch, user_key
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users[user_key]["email"], users[user_key]["password"])
    events: list[str] = []
    original_load = CharacterRepository.get_visible_character

    def load(repository, *args):
        events.append("load")
        return original_load(repository, *args)

    def access(*args):
        events.append("access")
        return False

    monkeypatch.setattr(CharacterRepository, "get_visible_character", load)
    monkeypatch.setattr(app_module, "has_session_mode_access", access)
    monkeypatch.setattr(
        app_module.SystemsService,
        "search_entries_for_campaign",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("denial reached Systems search")
        ),
    )

    assert client.get(f"{ROUTE_PATH}?q=rope").status_code == 403
    assert events == ["load", "access"]


def test_equipment_search_valid_record_can_lazy_initialize_before_session_denial(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="public")
    with app.app_context():
        state_store = app.extensions["character_state_store"]
        state_store.delete_state("linden-pass", "arden-march")
        assert state_store.get_state("linden-pass", "arden-march") is None

    sign_in(users["party"]["email"], users["party"]["password"])
    assert client.get(f"{ROUTE_PATH}?q=rope").status_code == 403

    with app.app_context():
        assert state_store.get_state("linden-pass", "arden-march") is not None


def test_equipment_search_preserves_view_as_and_bearer_precedence(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    assert client.get(f"{ROUTE_PATH}?q=r").status_code == 403

    token = issue_api_token(app, users["admin"]["email"], label="p53-browser-search")
    bearer = client.get(f"{ROUTE_PATH}?q=r", headers=api_headers(token))
    assert bearer.status_code == 200
    assert bearer.get_json() == {
        "results": [],
        "message": "Type at least 2 letters to search enabled Systems items.",
    }


@pytest.mark.parametrize("query", ("", " ", "r", "  r  "))
def test_equipment_search_short_query_does_not_call_systems(
    app, client, sign_in, users, monkeypatch, query
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    systems_service = app.extensions["systems_service"]
    monkeypatch.setattr(
        systems_service,
        "search_entries_for_campaign",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("short query reached Systems")
        ),
    )

    response = client.get(ROUTE_PATH, query_string={"q": query})
    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.get_json() == {
        "results": [],
        "message": "Type at least 2 letters to search enabled Systems items.",
    }


def test_equipment_search_uses_trimmed_first_repeated_query_and_exact_service_arguments(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def search(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(
        app.extensions["systems_service"], "search_entries_for_campaign", search
    )
    response = client.get(f"{ROUTE_PATH}?q=%20rope%20&q=lantern")

    assert response.status_code == 200
    assert calls == [
        (("linden-pass",), {"query": "rope", "entry_type": "item", "limit": 20})
    ]
    assert response.get_json() == {
        "results": [],
        "message": "No enabled Systems items matched that search.",
    }


def test_equipment_search_preserves_captured_systems_service_closure(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    captured_service = app.extensions["systems_service"]
    monkeypatch.setattr(
        captured_service,
        "search_entries_for_campaign",
        lambda *args, **kwargs: [],
    )
    app.extensions["systems_service"] = SimpleNamespace(
        search_entries_for_campaign=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("route dynamically substituted the Systems service")
        )
    )

    response = client.get(f"{ROUTE_PATH}?q=rope")
    assert response.status_code == 200
    assert response.get_json()["results"] == []


@pytest.mark.parametrize(
    ("source_id", "weight", "expected_subtitle", "expected_select_label"),
    (
        ("PHB", None, "PHB", "Rope - PHB"),
        ("PHB", "", "PHB", "Rope - PHB"),
        ("PHB", 0, "PHB", "Rope - PHB"),
        ("PHB", -2, "PHB", "Rope - PHB"),
        ("PHB", 10, "PHB - 10 lb.", "Rope - PHB - 10 lb."),
        ("PHB", "2.5", "PHB - 2.5 lb.", "Rope - PHB - 2.5 lb."),
        ("PHB", " variable ", "PHB - variable", "Rope - PHB - variable"),
        ("", 1, "1 lb.", "Rope - 1 lb."),
        (None, None, "", "Rope"),
    ),
)
def test_equipment_search_preserves_weight_subtitle_and_result_shape(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    source_id,
    weight,
    expected_subtitle,
    expected_select_label,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    entry = _entry(
        slug="phb-item-rope",
        title="Rope",
        source_id=source_id,
        weight=weight,
    )
    monkeypatch.setattr(
        app.extensions["systems_service"],
        "search_entries_for_campaign",
        lambda *args, **kwargs: [entry],
    )

    response = client.get(f"{ROUTE_PATH}?q=rope")
    assert response.status_code == 200
    assert response.get_json() == {
        "results": [
            {
                "entry_slug": "phb-item-rope",
                "title": "Rope",
                "source_id": source_id,
                "subtitle": expected_subtitle,
                "select_label": expected_select_label,
            }
        ],
        "message": "Found 1 matching Systems items.",
    }


def test_equipment_search_preserves_service_order_and_found_count(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    entries = [
        _entry(slug="zeta", title="Zeta", weight=1),
        _entry(slug="alpha", title="Alpha", weight=2),
    ]
    monkeypatch.setattr(
        app.extensions["systems_service"],
        "search_entries_for_campaign",
        lambda *args, **kwargs: entries,
    )

    response = client.get(f"{ROUTE_PATH}?q=gear")
    payload = response.get_json()
    assert [result["entry_slug"] for result in payload["results"]] == ["zeta", "alpha"]
    assert payload["message"] == "Found 2 matching Systems items."


@pytest.mark.parametrize("encoded_slug", ("..%5Cvictim", "C:%5Cescape"))
def test_equipment_search_p34_invalid_slug_has_no_state_access_or_systems_work(
    app, client, sign_in, users, monkeypatch, encoded_slug
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid slug reached eager work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(CharacterStateStore, "initialize_state_if_missing", unexpected)
    monkeypatch.setattr(app_module, "has_session_mode_access", unexpected)
    monkeypatch.setattr(
        app.extensions["systems_service"], "search_entries_for_campaign", unexpected
    )

    response = client.get(
        "/campaigns/linden-pass/characters/"
        f"{encoded_slug}/equipment/systems-items/search?q=rope"
    )
    assert response.status_code == 404


def test_equipment_search_definition_identity_mismatch_has_no_state_or_systems_work(
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
        raise AssertionError("identity mismatch reached eager work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(CharacterStateStore, "initialize_state_if_missing", unexpected)
    monkeypatch.setattr(app_module, "has_session_mode_access", unexpected)
    monkeypatch.setattr(
        app.extensions["systems_service"], "search_entries_for_campaign", unexpected
    )

    assert client.get(f"{ROUTE_PATH}?q=rope").status_code == 404


@pytest.mark.parametrize("fault_stage", ("load", "access", "search", "jsonify"))
def test_equipment_search_preserves_fault_propagation(
    app, client, sign_in, users, monkeypatch, fault_stage
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "load":
        monkeypatch.setattr(CharacterRepository, "get_visible_character", fault)
    elif fault_stage == "access":
        monkeypatch.setattr(app_module, "has_session_mode_access", fault)
    elif fault_stage == "search":
        monkeypatch.setattr(
            app.extensions["systems_service"], "search_entries_for_campaign", fault
        )
    else:
        monkeypatch.setattr(search_routes, "jsonify", fault)

    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        client.get(f"{ROUTE_PATH}?q=rope")
