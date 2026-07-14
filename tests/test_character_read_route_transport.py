from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import json
from pathlib import Path

import pytest
from flask import request

from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march"
ENDPOINT = "character_read_view"


def _install_builder_spy(app, monkeypatch, builder) -> None:
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    dependencies = app.extensions.get("character_read_route_dependencies")
    if dependencies is not None:
        monkeypatch.setitem(
            app.extensions,
            "character_read_route_dependencies",
            replace(dependencies, render_character_page=builder),
        )
        return

    closure_index = raw_view.__code__.co_freevars.index("render_character_page")
    monkeypatch.setattr(
        raw_view.__closure__[closure_index],
        "cell_contents",
        builder,
    )


def _character_read_source_function() -> tuple[str, ast.FunctionDef]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("app.py", "character_routes.py"):
        path = PROJECT_ROOT / "player_wiki" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        matches.extend(
            (filename, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == ENDPOINT
        )
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize(
    ("visibility", "actor", "expected_status", "expected_calls"),
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
def test_character_read_actor_visibility_and_assignment_non_bypass_are_characterized(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
    visibility,
    actor,
    expected_status,
    expected_calls,
):
    if visibility is not None:
        set_campaign_visibility("linden-pass", characters=visibility)
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])

    calls: list[tuple[str, str]] = []

    def builder(campaign_slug, character_slug):
        calls.append((campaign_slug, character_slug))
        return "character-read-builder", 207, {"X-P26-Builder": "called"}

    _install_builder_spy(app, monkeypatch, builder)

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert len(calls) == expected_calls
    if expected_calls:
        assert calls == [("linden-pass", "arden-march")]
        assert response.get_data(as_text=True) == "character-read-builder"
        assert response.headers["X-P26-Builder"] == "called"


def test_character_read_optional_identity_redirect_next_and_missing_campaign_order(
    app,
    client,
    monkeypatch,
):
    calls: list[tuple[str, str]] = []

    def builder(campaign_slug, character_slug):
        calls.append((campaign_slug, character_slug))
        return "unexpected"

    _install_builder_spy(app, monkeypatch, builder)

    denied = client.get(f"{ROUTE_PATH}?mode=session&page=features")
    assert denied.status_code == 302
    assert denied.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march?mode%3Dsession%26page%3Dfeatures"
    )

    missing = client.get(
        "/campaigns/missing-campaign/characters/arden-march?mode=session&page=features"
    )
    assert missing.status_code == 404
    assert calls == []


def test_character_read_view_as_uses_effective_actor_without_assignment_override(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    calls: list[tuple[str, str]] = []

    def builder(campaign_slug, character_slug):
        calls.append((campaign_slug, character_slug))
        return "view-as-builder", 207

    _install_builder_spy(app, monkeypatch, builder)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    denied = client.get(ROUTE_PATH)
    assert denied.status_code == 404
    assert calls == []

    set_campaign_visibility("linden-pass", characters="players")
    allowed = client.get(ROUTE_PATH)
    assert allowed.status_code == 207
    assert calls == [("linden-pass", "arden-march")]


def test_character_read_get_head_options_and_exact_builder_forwarding(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    calls: list[tuple[str, str, dict[str, str]]] = []

    def builder(campaign_slug, character_slug):
        calls.append((campaign_slug, character_slug, request.args.to_dict()))
        return "forwarded-response", 207, {"X-P26-Forwarded": "yes"}

    _install_builder_spy(app, monkeypatch, builder)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    get_response = client.get(f"{ROUTE_PATH}?mode=session&page=features&extra=visible")
    head_response = client.head(f"{ROUTE_PATH}?page=equipment")
    options_response = client.options(ROUTE_PATH)

    assert get_response.status_code == 207
    assert get_response.get_data(as_text=True) == "forwarded-response"
    assert get_response.headers["X-P26-Forwarded"] == "yes"
    assert head_response.status_code == 207
    assert head_response.get_data() == b""
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].replace(" ", "").split(",")) == {
        "GET",
        "HEAD",
        "OPTIONS",
    }
    assert calls == [
        (
            "linden-pass",
            "arden-march",
            {"mode": "session", "page": "features", "extra": "visible"},
        ),
        ("linden-pass", "arden-march", {"page": "equipment"}),
    ]


def test_character_read_builder_fault_propagates_without_retry(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    calls: list[tuple[str, str]] = []

    def builder(campaign_slug, character_slug):
        calls.append((campaign_slug, character_slug))
        raise RuntimeError("character read builder fault")

    _install_builder_spy(app, monkeypatch, builder)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    with pytest.raises(RuntimeError, match="character read builder fault"):
        client.get(f"{ROUTE_PATH}?page=quick")

    assert calls == [("linden-pass", "arden-march")]


def test_character_read_endpoint_decorator_registration_and_manifest_contract_are_exact(app):
    matching_rules = [rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT]
    assert len(matching_rules) == 1
    rule = matching_rules[0]
    assert rule.rule == "/campaigns/<campaign_slug>/characters/<character_slug>"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == ENDPOINT
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == ENDPOINT

    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("character_retraining_view") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_controls_assignment")

    _, source_function = _character_read_source_function()
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
    assert entry["route"] == "/campaigns/<campaign_slug>/characters/<character_slug>"
    assert entry["owning_domain"] == "characters"
    assert entry["authentication_policy"] == "optional_identity"
    assert entry["access_policy"] == "character_read_browser"
    assert entry["campaign_scope"] == "characters"
    assert entry["visibility_policy"] == "campaign_scope"
    assert entry["object_relationship_requirement"] == "visible_character_in_characters_scope"
    assert entry["view_as_policy"] == "campaign_safe_reads_use_effective_actor"


def test_character_read_dnd_subpages_mode_alias_and_fallback_remain_selected(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    features = client.get(f"{ROUTE_PATH}?mode=session&page=features")
    fallback = client.get(f"{ROUTE_PATH}?mode=read&page=not-a-real-page")

    assert features.status_code == 200
    features_html = features.get_data(as_text=True)
    assert 'data-character-read-shell-page="features"' in features_html
    assert "?mode=session&amp;page=features" in features_html
    assert fallback.status_code == 200
    assert 'data-character-read-shell-page="quick"' in fallback.get_data(as_text=True)


def test_character_read_xianxia_subpage_and_dnd_alias_fallback_remain_system_specific(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("P26 Read Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    selected = client.get(
        "/campaigns/linden-pass/characters/p26-read-crane?page=martial_arts"
    )
    legacy = client.get(
        "/campaigns/linden-pass/characters/p26-read-crane?mode=session&page=spellcasting"
    )

    assert selected.status_code == 200
    selected_html = selected.get_data(as_text=True)
    assert "P26 Read Crane" in selected_html
    assert 'data-character-read-shell-page="martial_arts"' in selected_html
    assert "?page=martial_arts" in selected_html
    assert "?page=spellcasting" not in selected_html
    assert legacy.status_code == 200
    legacy_html = legacy.get_data(as_text=True)
    assert 'data-character-read-shell-page="quick"' in legacy_html
    assert "?mode=session&amp;page=spellcasting" not in legacy_html
