from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import json
from pathlib import Path

import pytest
from flask import request

from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)
from tests.sample_data import ASSIGNED_CHARACTER_SLUG


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/campaigns/linden-pass/session/character"
ENDPOINT = "campaign_session_character_view"


def _install_transport_spies(
    app,
    monkeypatch,
    *,
    page_builder,
    shell_builder,
    renderer,
) -> None:
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    view_globals = raw_view.__globals__
    monkeypatch.setitem(view_globals, "render_template", renderer)

    dependencies = app.extensions.get("character_route_dependencies")
    if dependencies is None:
        replacements = {
            "build_campaign_session_character_page_context": page_builder,
            "build_campaign_session_shell_context": shell_builder,
        }
        for name, replacement in replacements.items():
            closure_index = raw_view.__code__.co_freevars.index(name)
            monkeypatch.setattr(
                raw_view.__closure__[closure_index],
                "cell_contents",
                replacement,
            )
        return

    monkeypatch.setitem(
        app.extensions,
        "character_route_dependencies",
        replace(
            dependencies,
            build_campaign_session_character_page_context=page_builder,
            build_campaign_session_shell_context=shell_builder,
        ),
    )


@pytest.mark.parametrize(
    ("actor", "query", "status_code", "expected_text", "public_session"),
    (
        ("owner", f"?character={ASSIGNED_CHARACTER_SLUG}", 200, "Arden March", False),
        ("party", "", 200, "No session character available", False),
        ("party", f"?character={ASSIGNED_CHARACTER_SLUG}", 403, None, False),
        ("observer", "", 200, "Character tab unavailable", True),
        ("dm", f"?character={ASSIGNED_CHARACTER_SLUG}", 200, "Arden March", False),
        ("admin", f"?character={ASSIGNED_CHARACTER_SLUG}", 200, "Arden March", False),
    ),
)
def test_session_character_actor_and_scope_outcomes_are_characterized(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    actor,
    query,
    status_code,
    expected_text,
    public_session,
):
    if public_session:
        set_campaign_visibility("linden-pass", session="public")
    sign_in(users[actor]["email"], users[actor]["password"])

    response = client.get(f"{ROUTE_PATH}{query}")

    assert response.status_code == status_code
    if expected_text is not None:
        assert expected_text in response.get_data(as_text=True)


def test_session_character_get_head_options_endpoint_and_registration_identity(
    app,
    client,
    sign_in,
    users,
):
    matching_rules = [rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT]
    assert len(matching_rules) == 1
    rule = matching_rules[0]
    assert rule.rule == "/campaigns/<campaign_slug>/session/character"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == ENDPOINT
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == ENDPOINT

    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.get(ROUTE_PATH).status_code == 200
    head_response = client.head(ROUTE_PATH)
    assert head_response.status_code == 200
    assert head_response.get_data() == b""
    options_response = client.options(ROUTE_PATH)
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].replace(" ", "").split(",")) == {
        "GET",
        "HEAD",
        "OPTIONS",
    }

    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("campaign_combat_delete_combatant") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_roster_view")


def test_session_character_decorator_and_manifest_contract_are_exact():
    candidates = []
    for filename in ("app.py", "character_routes.py"):
        path = PROJECT_ROOT / "player_wiki" / filename
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        candidates.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
        )
    assert len(candidates) == 1
    scope_decorators = [
        decorator
        for decorator in candidates[0].decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "campaign_scope_access_required"
    ]
    assert len(scope_decorators) == 1
    assert len(scope_decorators[0].args) == 1
    assert isinstance(scope_decorators[0].args[0], ast.Constant)
    assert scope_decorators[0].args[0].value == "session"

    manifest = json.loads(
        (PROJECT_ROOT / "docs" / "contracts" / "route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = [
        entry
        for entry in manifest["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "GET"
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["route"] == "/campaigns/<campaign_slug>/session/character"
    assert entry["owning_domain"] == "characters"
    assert entry["campaign_scope"] == "session"
    assert entry["access_policy"] == "session_character_read_browser"


@pytest.mark.parametrize(
    ("query", "expected_events", "expected_body"),
    (
        (
            f"?character={ASSIGNED_CHARACTER_SLUG}&page=equipment&fragment=1",
            (
                ("page", "linden-pass", {"character": ASSIGNED_CHARACTER_SLUG, "page": "equipment", "fragment": "1"}),
                ("render", "_session_character_panel.html", True, "page"),
            ),
            "_session_character_panel.html",
        ),
        (
            f"?character={ASSIGNED_CHARACTER_SLUG}&page=equipment",
            (
                ("shell", "linden-pass", "character", {"character": ASSIGNED_CHARACTER_SLUG, "page": "equipment"}),
                ("render", "session_character.html", None, "shell"),
            ),
            "session_character.html",
        ),
    ),
)
def test_session_character_branches_preserve_builder_render_order_and_query_visibility(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    query,
    expected_events,
    expected_body,
):
    events = []

    def page_builder(campaign_slug):
        events.append(("page", campaign_slug, request.args.to_dict()))
        return {"branch": "page"}

    def shell_builder(campaign_slug, *, active_pane):
        events.append(("shell", campaign_slug, active_pane, request.args.to_dict()))
        return {"branch": "shell"}

    def renderer(template_name, **context):
        events.append(
            (
                "render",
                template_name,
                context.get("session_character_fragment"),
                context["branch"],
            )
        )
        return template_name

    _install_transport_spies(
        app,
        monkeypatch,
        page_builder=page_builder,
        shell_builder=shell_builder,
        renderer=renderer,
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(f"{ROUTE_PATH}{query}")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == expected_body
    assert tuple(events) == expected_events


@pytest.mark.parametrize(
    ("fragment", "fault_at", "expected_events"),
    (
        (True, "builder", ("page",)),
        (False, "builder", ("shell",)),
        (True, "render", ("page", "render:_session_character_panel.html")),
        (False, "render", ("shell", "render:session_character.html")),
    ),
)
def test_session_character_builder_and_render_faults_propagate_without_cross_branch_work(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    fragment,
    fault_at,
    expected_events,
):
    events = []

    def page_builder(campaign_slug):
        events.append("page")
        if fragment and fault_at == "builder":
            raise RuntimeError("page builder fault")
        return {"branch": "page"}

    def shell_builder(campaign_slug, *, active_pane):
        events.append("shell")
        if not fragment and fault_at == "builder":
            raise RuntimeError("shell builder fault")
        return {"branch": "shell"}

    def renderer(template_name, **context):
        events.append(f"render:{template_name}")
        if fault_at == "render":
            raise RuntimeError("render fault")
        return template_name

    _install_transport_spies(
        app,
        monkeypatch,
        page_builder=page_builder,
        shell_builder=shell_builder,
        renderer=renderer,
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])
    query = f"?character={ASSIGNED_CHARACTER_SLUG}"
    if fragment:
        query += "&fragment=1"

    with pytest.raises(RuntimeError):
        client.get(f"{ROUTE_PATH}{query}")

    assert tuple(events) == expected_events


@pytest.mark.parametrize(
    ("page", "active_page", "expected_text"),
    (
        ("quick", "overview", "At a glance"),
        ("spellcasting", "spells", "Spells"),
    ),
)
def test_session_character_dnd5e_page_aliases_remain_selected(
    client,
    sign_in,
    users,
    page,
    active_page,
    expected_text,
):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        f"{ROUTE_PATH}?character={ASSIGNED_CHARACTER_SLUG}&page={page}"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert expected_text in html
    assert f"page={active_page}" in html


def test_session_character_xianxia_selection_and_legacy_aliases_remain_system_specific(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("P25 Session Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    selected = client.get(
        f"{ROUTE_PATH}?character=p25-session-crane&page=martial_arts"
    )
    assert selected.status_code == 200
    selected_html = selected.get_data(as_text=True)
    assert "P25 Session Crane" in selected_html
    assert "Martial Arts" in selected_html
    assert "page=martial_arts" in selected_html
    assert "page=spellcasting" not in selected_html

    legacy = client.get(
        f"{ROUTE_PATH}?character=p25-session-crane&page=spellcasting"
    )
    assert legacy.status_code == 200
    legacy_html = legacy.get_data(as_text=True)
    assert "At a glance" in legacy_html
    assert "page=spellcasting" not in legacy_html
