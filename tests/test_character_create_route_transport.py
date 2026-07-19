from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.app as app_module
import player_wiki.character_create_routes as route_module


ENDPOINT = "character_create_view"
ROUTE_PATH = "/campaigns/linden-pass/characters/new"
GRANT_INPUT = "gm_granted_generic_technique_entry_keys"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _registered_dependencies(app):
    raw_view = _handler(app)
    index = raw_view.__code__.co_freevars.index("dependencies")
    return raw_view.__closure__[index].cell_contents


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    if "dependencies" in freevars:
        current = freevars["dependencies"].cell_contents
        monkeypatch.setattr(
            freevars["dependencies"],
            "cell_contents",
            replace(current, **replacements),
        )
        return

    for name, replacement in replacements.items():
        if name in freevars:
            monkeypatch.setattr(freevars[name], "cell_contents", replacement)
        else:
            monkeypatch.setattr(app_module, name, replacement)


def _definition(slug: str = "new-hero"):
    return SimpleNamespace(
        name="New Hero",
        character_slug=slug,
        to_dict=lambda: {"name": "New Hero", "character_slug": slug},
    )


def _metadata():
    return SimpleNamespace(to_dict=lambda: {"source_path": "native://builder"})


def _dependencies(tmp_path: Path, events: list[object], *, lane: str):
    campaign = SimpleNamespace(
        slug="linden-pass",
        system="Xianxia" if lane == "xianxia" else "DND-5E",
    )
    definition = _definition()
    metadata = _metadata()
    systems_service = object()

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def xianxia_context(values, *, systems_service, campaign_slug):
        events.append(("xianxia_context", values, systems_service, campaign_slug))
        return {"values": values}

    def dnd_context(
        systems_service,
        campaign_slug,
        values,
        *,
        campaign_page_records,
    ):
        events.append(
            (
                "dnd_context",
                systems_service,
                campaign_slug,
                values,
                campaign_page_records,
            )
        )
        return {
            "class_options": ["class"],
            "species_options": ["species"],
            "background_options": ["background"],
        }

    return {
        "load_campaign_context": event("campaign", campaign),
        "campaign_supports_native_character_create": event("supports", True),
        "redirect_unsupported_native_character_tools": event(
            "unsupported_redirect", "unsupported"
        ),
        "get_systems_service": event("systems", systems_service),
        "render_xianxia_character_create_page": event(
            "render_xianxia", ("xianxia", 200)
        ),
        "list_builder_campaign_page_records": event("page_records", ["page"]),
        "render_character_builder_page": event("render_dnd", ("dnd", 200)),
        "finalize_character_definition_for_write": event("finalize", definition),
        "can_manage_campaign_session": event("manage", True),
        "native_character_create_lane": event("lane", lane),
        "native_character_create_unsupported_message": event(
            "unsupported_message", "unsupported"
        ),
        "build_xianxia_character_create_context": xianxia_context,
        "build_xianxia_character_definition": event(
            "xianxia_definition", (definition, metadata)
        ),
        "build_xianxia_character_initial_state": event(
            "xianxia_initial_state", {"system": "xianxia"}
        ),
        "validate_character_slug": event("validate"),
        "publish_new_character": event("publish"),
        "build_level_one_builder_context": dnd_context,
        "build_level_one_character_definition": event(
            "dnd_definition", (definition, metadata)
        ),
        "build_initial_state": event("dnd_initial_state", {"system": "dnd"}),
    }


def _event_names(events):
    return [event[0] for event in events]


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    direct = {
        "load_campaign_context",
        "campaign_supports_native_character_create",
        "redirect_unsupported_native_character_tools",
        "get_systems_service",
        "render_xianxia_character_create_page",
        "list_builder_campaign_page_records",
        "render_character_builder_page",
        "finalize_character_definition_for_write",
    }
    expected = [
        "load_campaign_context",
        "campaign_supports_native_character_create",
        "redirect_unsupported_native_character_tools",
        "get_systems_service",
        "render_xianxia_character_create_page",
        "list_builder_campaign_page_records",
        "render_character_builder_page",
        "finalize_character_definition_for_write",
        "can_manage_campaign_session",
        "native_character_create_lane",
        "native_character_create_unsupported_message",
        "build_xianxia_character_create_context",
        "build_xianxia_character_definition",
        "build_xianxia_character_initial_state",
        "validate_character_slug",
        "publish_new_character",
        "build_level_one_builder_context",
        "build_level_one_character_definition",
        "build_initial_state",
    ]
    assert [
        field.name for field in fields(route_module.CharacterCreateRouteDependencies)
    ] == expected

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_create_routes.py").read_text(encoding="utf-8")
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
    registrations = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registrar_call = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_character_create_route"
    )
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterCreateRouteDependencies"
    )
    values = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert set(values) == set(expected)
    for name in direct:
        assert isinstance(values[name], ast.Name)
        assert values[name].id == name
    assert all(isinstance(values[name], ast.Lambda) for name in set(expected) - direct)


def test_actual_app_browser_create_publication_targets_coordinator_create(
    app,
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        app.extensions["character_publication_coordinator"],
        "create",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "created",
    )
    dependencies = _registered_dependencies(app)
    sentinels = (object(), object(), object())

    assert dependencies.publish_new_character(
        *sentinels,
        operation_kind="native_create",
    ) == "created"
    assert calls == [(sentinels, {"operation_kind": "native_create"})]


def test_forwarded_dependencies_remain_post_registration_monkeypatchable(
    app, monkeypatch
):
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    dependencies = freevars["dependencies"].cell_contents
    forwarded = [field.name for field in fields(dependencies)][8:]
    args_by_name = {
        "can_manage_campaign_session": ("linden-pass",),
        "native_character_create_lane": ("DND-5E",),
        "native_character_create_unsupported_message": ("DND-5E",),
        "validate_character_slug": ("hero",),
        "build_initial_state": (object(),),
    }
    for name in forwarded:
        if name == "publish_new_character":
            assert callable(getattr(dependencies, name))
            continue
        marker = object()
        monkeypatch.setattr(
            app_module, name, lambda *args, result=marker, **kwargs: result
        )
        assert getattr(dependencies, name)(*args_by_name.get(name, ())) is marker


def test_untouched_route_identity_methods_and_neighbor_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == "/campaigns/<campaign_slug>/characters/new"
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert _handler(app).__name__ == ENDPOINT
    assert endpoints.index("character_roster_view") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_import_xianxia_manual_view"
    )
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_xianxia_get_preserves_repeated_grants_and_call_order(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events, lane="xianxia")
    _install_dependencies(app, monkeypatch, **dependencies)

    raw_view = _handler(app)
    with app.test_request_context(
        f"{ROUTE_PATH}?name=Lotus&{GRANT_INPUT}=first&{GRANT_INPUT}=second"
    ):
        response = raw_view(campaign_slug="linden-pass")

    assert response == ("xianxia", 200)
    assert _event_names(events) == [
        "manage",
        "campaign",
        "lane",
        "supports",
        "systems",
        "xianxia_context",
        "render_xianxia",
    ]
    assert events[5][1][GRANT_INPUT] == ["first", "second"]


def test_xianxia_post_builds_state_before_validation_then_publishes_and_redirects(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events, lane="xianxia")
    _install_dependencies(app, monkeypatch, **dependencies)
    raw_view = _handler(app)
    with app.test_request_context(ROUTE_PATH, method="POST", data={"name": "Lotus"}):
        response = raw_view(campaign_slug="linden-pass")

    assert response.status_code == 302
    names = _event_names(events)
    assert names.index("xianxia_initial_state") < names.index("validate")
    assert names[names.index("publish") :] == ["publish"]
    publish = next(event for event in events if event[0] == "publish")
    assert publish[2]["operation_kind"] == "native_create"


def test_dnd_post_builds_initial_state_before_atomic_publication(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events, lane="dnd5e")
    _install_dependencies(app, monkeypatch, **dependencies)
    raw_view = _handler(app)
    with app.test_request_context(ROUTE_PATH, method="POST", data={"name": "Hero"}):
        response = raw_view(campaign_slug="linden-pass")

    assert response.status_code == 302
    names = _event_names(events)
    assert names[:8] == [
        "manage",
        "campaign",
        "lane",
        "supports",
        "page_records",
        "systems",
        "dnd_context",
        "dnd_definition",
    ]
    assert names.index("finalize") < names.index("validate")
    assert names[names.index("dnd_initial_state") :] == [
        "dnd_initial_state",
        "publish",
    ]


@pytest.mark.parametrize("lane", ("xianxia", "dnd5e"))
def test_publication_fault_propagates_without_route_level_fallback(
    app, monkeypatch, tmp_path, lane
):
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events, lane=lane)

    def publish(*args, **kwargs):
        events.append(("publish", args, kwargs))
        raise RuntimeError("publication fault")

    dependencies["publish_new_character"] = publish
    _install_dependencies(app, monkeypatch, **dependencies)

    raw_view = _handler(app)
    with app.test_request_context(ROUTE_PATH, method="POST", data={"name": "Hero"}):
        with pytest.raises(RuntimeError, match="publication fault"):
            raw_view(campaign_slug="linden-pass")

    assert _event_names(events).count("publish") == 1


def test_unsupported_lane_stops_before_builder_work(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events, lane="")
    dependencies["campaign_supports_native_character_create"] = lambda campaign: False
    _install_dependencies(app, monkeypatch, **dependencies)

    raw_view = _handler(app)
    with app.test_request_context(ROUTE_PATH):
        response = raw_view(campaign_slug="linden-pass")

    assert response == "unsupported"
    assert _event_names(events) == [
        "manage",
        "campaign",
        "lane",
        "unsupported_message",
        "unsupported_redirect",
    ]
