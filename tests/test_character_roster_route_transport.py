from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import current_app
from werkzeug.exceptions import NotFound

import player_wiki.app as app_module
import player_wiki.character_routes as character_routes_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.character_state_helpers import _write_campaign_config
from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "character_roster_view"
ROUTE_PATH = "/campaigns/linden-pass/characters"
DEPENDENCY_KEY = "character_roster_route_dependencies"


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    dependencies = app.extensions.get(DEPENDENCY_KEY)
    if dependencies is not None:
        monkeypatch.setitem(
            app.extensions,
            DEPENDENCY_KEY,
            replace(dependencies, **replacements),
        )
        return

    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    closure_names = set(raw_view.__code__.co_freevars)
    for name, value in replacements.items():
        if name in closure_names:
            closure_index = raw_view.__code__.co_freevars.index(name)
            monkeypatch.setattr(raw_view.__closure__[closure_index], "cell_contents", value)
        else:
            monkeypatch.setattr(app_module, name, value)


def _install_render_template(monkeypatch, renderer) -> None:
    monkeypatch.setattr(app_module, "render_template", renderer)
    monkeypatch.setattr(character_routes_module, "render_template", renderer)


def _source_functions(name: str) -> list[tuple[str, ast.FunctionDef]]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("app.py", "character_routes.py"):
        tree = ast.parse(
            (PROJECT_ROOT / "player_wiki" / filename).read_text(encoding="utf-8")
        )
        matches.extend(
            (filename, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
    return matches


def _handler_campaign(system: str = "DND-5E"):
    return SimpleNamespace(slug="linden-pass", system=system)


def _install_minimal_handler_spies(app, monkeypatch, calls, *, system="DND-5E"):
    def renderer(template_name, **context):
        calls.append(("render", template_name, context))
        response = current_app.response_class("roster-response", status=207)
        response.headers["X-P29-Roster"] = "called"
        return response

    _install_render_template(monkeypatch, renderer)


@pytest.mark.parametrize(
    ("visibility", "actor", "expected_status", "expected_handler_calls"),
    (
        (None, "owner", 404, 0),
        (None, "party", 404, 0),
        (None, "observer", 404, 0),
        (None, "outsider", 404, 0),
        (None, "dm", 207, 1),
        (None, "admin", 207, 1),
        ("players", "owner", 207, 1),
        ("players", "party", 207, 1),
        ("players", "observer", 404, 0),
        ("players", "outsider", 404, 0),
        ("public", "observer", 207, 1),
        ("public", "outsider", 207, 1),
        ("public", None, 207, 1),
    ),
)
def test_roster_actor_visibility_and_assignment_non_bypass(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
    visibility,
    actor,
    expected_status,
    expected_handler_calls,
):
    if visibility is not None:
        set_campaign_visibility("linden-pass", characters=visibility)
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])

    calls: list[tuple] = []
    _install_minimal_handler_spies(app, monkeypatch, calls)

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert sum(
        call[0] == "render" and call[1] == "character_roster.html"
        for call in calls
    ) == expected_handler_calls
    if expected_handler_calls:
        assert response.get_data(as_text=True) == "roster-response"
        assert response.headers["X-P29-Roster"] == "called"


def test_roster_optional_identity_redirect_next_missing_campaign_and_view_as_order(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    calls: list[tuple] = []
    _install_minimal_handler_spies(app, monkeypatch, calls)

    anonymous = client.get(f"{ROUTE_PATH}?q=Arden%20March")
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters?q%3DArden%2520March"
    )
    assert not any(
        call[0] == "render" and call[1] == "character_roster.html"
        for call in calls
    )

    missing = client.get("/campaigns/missing-campaign/characters?q=arden")
    assert missing.status_code == 404
    assert not any(
        call[0] == "render" and call[1] == "character_roster.html"
        for call in calls
    )

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]

    denied = client.get(ROUTE_PATH)
    assert denied.status_code == 404
    assert not any(
        call[0] == "render" and call[1] == "character_roster.html"
        for call in calls
    )

    set_campaign_visibility("linden-pass", characters="players")
    allowed = client.get(ROUTE_PATH)
    assert allowed.status_code == 207
    assert sum(
        call[0] == "render" and call[1] == "character_roster.html"
        for call in calls
    ) == 1


def test_roster_get_head_options_disallowed_methods_and_handler_work(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    calls: list[tuple] = []
    _install_minimal_handler_spies(app, monkeypatch, calls)

    get_response = client.get(f"{ROUTE_PATH}?q=Arden")
    head_response = client.head(f"{ROUTE_PATH}?q=Tobin")
    options_response = client.options(ROUTE_PATH)
    post_response = client.post(ROUTE_PATH)

    assert get_response.status_code == 207
    assert get_response.get_data(as_text=True) == "roster-response"
    assert head_response.status_code == 207
    assert head_response.get_data() == b""
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].replace(" ", "").split(",")) == {
        "GET",
        "HEAD",
        "OPTIONS",
    }
    assert post_response.status_code == 405
    assert sum(
        call[0] == "render" and call[1] == "character_roster.html"
        for call in calls
    ) == 2


def test_roster_exact_query_pipeline_context_and_call_order(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    calls: list[tuple] = []
    campaign = _handler_campaign()
    records = [SimpleNamespace(character_slug="tobin"), SimpleNamespace(character_slug="arden")]
    cards = [
        {"name": "Tobin", "search_text": "tobin slate fighter"},
        {"name": "Arden", "search_text": "arden march artificer"},
    ]

    class Repository:
        def get_campaign(self, campaign_slug):
            calls.append(("campaign", campaign_slug))
            return campaign

    class CharacterRepository:
        def list_visible_characters(self, campaign_slug):
            calls.append(("list", campaign_slug))
            return records

    _install_dependencies(
        app,
        monkeypatch,
        get_repository=lambda: calls.append(("repository",)) or Repository(),
        campaign_supports_native_character_tools=lambda current: calls.append(
            ("native_tools", current)
        )
        or True,
        campaign_supports_native_character_create=lambda current: calls.append(
            ("native_create", current)
        )
        or True,
        native_character_create_lane=lambda system: calls.append(("lane", system))
        or "dnd5e",
        get_character_repository=lambda: calls.append(("character_repository",))
        or CharacterRepository(),
        present_character_roster=lambda current_records: calls.append(
            ("present", current_records)
        )
        or cards,
        can_manage_campaign_session=lambda campaign_slug: calls.append(
            ("manage", campaign_slug)
        )
        or True,
    )

    rendered: dict[str, object] = {}

    def renderer(template_name, **context):
        calls.append(("render", template_name))
        rendered.update(context)
        return "filtered-roster", 208

    _install_render_template(monkeypatch, renderer)
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    with app.test_request_context(f"{ROUTE_PATH}?q=%20ARDEN%20"):
        response = raw_view(campaign_slug="linden-pass")

    assert response == ("filtered-roster", 208)
    assert [call[0] for call in calls] == [
        "repository",
        "campaign",
        "native_tools",
        "native_create",
        "lane",
        "character_repository",
        "list",
        "present",
        "manage",
        "manage",
        "render",
    ]
    assert rendered == {
        "campaign": campaign,
        "character_cards": [cards[1]],
        "query": "ARDEN",
        "result_count": 1,
        "can_create_characters": True,
        "can_import_xianxia_characters": False,
        "native_character_tools_supported": True,
        "native_character_create_supported": True,
        "character_create_lane": "dnd5e",
        "active_nav": "characters",
    }


def test_roster_empty_query_preserves_presenter_order_and_skips_filter(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    calls: list[tuple] = []
    _install_minimal_handler_spies(app, monkeypatch, calls)

    response = client.get(f"{ROUTE_PATH}?q=%20%20")

    assert response.status_code == 207
    render_call = next(call for call in calls if call[0] == "render")
    assert render_call[2]["query"] == ""
    assert render_call[2]["result_count"] == len(render_call[2]["character_cards"])
    assert render_call[2]["result_count"] > 0


def test_roster_module_global_dependencies_remain_late_bound_after_registration(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    calls: list[tuple] = []
    manager_results = iter((True, False))

    monkeypatch.setattr(
        app_module,
        "native_character_create_lane",
        lambda system: calls.append(("lane", system)) or "xianxia",
    )
    monkeypatch.setattr(
        app_module,
        "present_character_roster",
        lambda records: calls.append(("present", len(records)))
        or [{"name": "Late Bound", "search_text": "late bound"}],
    )
    monkeypatch.setattr(
        app_module,
        "can_manage_campaign_session",
        lambda campaign_slug: calls.append(("manage", campaign_slug))
        or next(manager_results),
    )

    captured: dict[str, object] = {}

    def renderer(template_name, **context):
        captured.update(context)
        return current_app.response_class("late-bound-roster", status=210)

    _install_render_template(monkeypatch, renderer)
    response = client.get(f"{ROUTE_PATH}?q=late")

    assert response.status_code == 210
    assert response.get_data(as_text=True) == "late-bound-roster"
    assert [call[0] for call in calls] == ["lane", "present", "manage", "manage"]
    assert captured["character_cards"] == [
        {"name": "Late Bound", "search_text": "late bound"}
    ]
    assert captured["can_create_characters"] is True
    assert captured["can_import_xianxia_characters"] is False


@pytest.mark.parametrize(
    ("system", "expected_create", "expected_import", "expected_lane"),
    (
        ("DND-5E", True, False, "dnd5e"),
        ("xianxia", True, True, "xianxia"),
        ("Pathfinder 2E", False, False, ""),
    ),
)
def test_roster_dnd_xianxia_and_unsupported_system_presentation(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    system,
    expected_create,
    expected_import,
    expected_lane,
):
    if system == "xianxia":
        _configure_xianxia_campaign(app)
    elif system != "DND-5E":
        _write_campaign_config(app, lambda payload: payload.__setitem__("system", system))
    sign_in(users["dm"]["email"], users["dm"]["password"])

    captured: dict[str, object] = {}

    def renderer(template_name, **context):
        captured["template"] = template_name
        captured.update(context)
        return current_app.response_class("system-roster", status=209)

    _install_render_template(monkeypatch, renderer)
    response = client.get(ROUTE_PATH)

    assert response.status_code == 209
    assert captured["template"] == "character_roster.html"
    assert captured["can_create_characters"] is expected_create
    assert captured["can_import_xianxia_characters"] is expected_import
    assert captured["character_create_lane"] == expected_lane
    assert captured["native_character_tools_supported"] is (system == "DND-5E")
    assert captured["native_character_create_supported"] is expected_create
    assert captured["active_nav"] == "characters"


@pytest.mark.parametrize(
    "fault_name",
    (
        "get_repository",
        "campaign_supports_native_character_tools",
        "campaign_supports_native_character_create",
        "native_character_create_lane",
        "get_character_repository",
        "present_character_roster",
        "can_manage_campaign_session",
        "render_template",
    ),
)
def test_roster_dependency_faults_propagate_without_retry(app, monkeypatch, fault_name):
    calls: list[str] = []
    campaign = _handler_campaign()

    def stage(name, result):
        def invoke(*args, **kwargs):
            calls.append(name)
            if name == fault_name:
                raise RuntimeError(f"{name} fault")
            return result

        return invoke

    repository = SimpleNamespace(get_campaign=stage("campaign_lookup", campaign))
    character_repository = SimpleNamespace(
        list_visible_characters=stage("list_visible_characters", [])
    )
    _install_dependencies(
        app,
        monkeypatch,
        get_repository=stage("get_repository", repository),
        campaign_supports_native_character_tools=stage(
            "campaign_supports_native_character_tools", True
        ),
        campaign_supports_native_character_create=stage(
            "campaign_supports_native_character_create", True
        ),
        native_character_create_lane=stage("native_character_create_lane", "dnd5e"),
        get_character_repository=stage("get_character_repository", character_repository),
        present_character_roster=stage("present_character_roster", []),
        can_manage_campaign_session=stage("can_manage_campaign_session", True),
    )
    _install_render_template(monkeypatch, stage("render_template", "unexpected"))

    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(RuntimeError, match=f"{fault_name} fault"):
            raw_view(campaign_slug="linden-pass")

    assert calls.count(fault_name) == 1


def test_roster_missing_second_campaign_lookup_404s_before_policy_and_records(
    app, monkeypatch
):
    calls: list[str] = []
    repository = SimpleNamespace(
        get_campaign=lambda campaign_slug: calls.append("campaign_lookup") or None
    )
    _install_dependencies(
        app,
        monkeypatch,
        get_repository=lambda: calls.append("get_repository") or repository,
        campaign_supports_native_character_tools=lambda campaign: calls.append(
            "native_tools"
        ),
        get_character_repository=lambda: calls.append("character_repository"),
    )

    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(NotFound):
            raw_view(campaign_slug="linden-pass")
    assert calls == ["get_repository", "campaign_lookup"]


def test_roster_endpoint_decorator_registration_and_manifest_contract_are_exact(app):
    matching_rules = [rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT]
    assert len(matching_rules) == 1
    rule = matching_rules[0]
    assert rule.rule == "/campaigns/<campaign_slug>/characters"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == ENDPOINT
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == ENDPOINT

    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("campaign_session_character_view") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_create_view")

    matches = _source_functions(ENDPOINT)
    assert len(matches) == 1
    source_filename, source_function = matches[0]
    assert source_filename == "character_routes.py"
    scope_decorators = [
        decorator
        for decorator in source_function.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "campaign_scope_access_required"
    ]
    assert len(scope_decorators) == 1
    assert len(scope_decorators[0].args) == 1
    assert isinstance(scope_decorators[0].args[0], ast.Constant)
    assert scope_decorators[0].args[0].value == "characters"

    manifest = json.loads(
        (
            PROJECT_ROOT
            / "docs"
            / "contracts"
            / "route-api-role-visibility-manifest.json"
        ).read_text(encoding="utf-8")
    )
    entries = [
        entry
        for entry in manifest["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "GET"
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["route"] == "/campaigns/<campaign_slug>/characters"
    assert entry["owning_domain"] == "characters"
    assert entry["campaign_scope"] == "characters"
    assert entry["authentication_policy"] == "optional_identity"
    assert entry["access_policy"] == "character_read_browser"
    assert entry["object_relationship_requirement"] == (
        "visible_character_in_characters_scope"
    )
