from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.app as app_module
import player_wiki.character_edit_routes as route_module


ENDPOINT = "character_edit_view"
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/edit"
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


def _event_names(events):
    return [event[0] for event in events]


def _fixtures(tmp_path: Path, events: list[object]):
    definition = SimpleNamespace(
        source={"source_type": "native_character_builder"},
        resource_templates=[],
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    updated_definition = SimpleNamespace(
        source={"source_type": "native_character_builder"},
        resource_templates=[],
        to_dict=lambda: {"character_slug": "arden-march", "updated": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "native"})
    state_record = SimpleNamespace(
        revision=7,
        state={"notes": {"player": "Existing"}},
    )
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=state_record,
    )
    campaign = SimpleNamespace(system="DND-5E", current_session=3)
    user = SimpleNamespace(id=41)
    systems_service = object()
    valid_page = SimpleNamespace(
        page=SimpleNamespace(
            published=True,
            reveal_after_session=3,
            section="Mechanics",
        )
    )
    future_page = SimpleNamespace(
        page=SimpleNamespace(
            published=True,
            reveal_after_session=4,
            section="Mechanics",
        )
    )
    session_page = SimpleNamespace(
        page=SimpleNamespace(
            published=True,
            reveal_after_session=0,
            section="Sessions",
        )
    )
    entries = {
        "spell": [SimpleNamespace(slug="spell-one")],
        "optionalfeature": [
            SimpleNamespace(slug="feature-one"),
            SimpleNamespace(slug=""),
        ],
    }
    character_dir = tmp_path / "characters" / "arden-march"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def enabled_entries(service, campaign_slug, entry_type):
        events.append(("entries", service, campaign_slug, entry_type))
        return entries[entry_type]

    def build_context(definition, **kwargs):
        events.append(("edit_context", definition, kwargs))
        return {"values": kwargs.get("form_values")}

    def apply_edits(*args, **kwargs):
        events.append(("apply", args, kwargs))
        return updated_definition, import_metadata, {"item": 2}

    def merge(definition, state, **kwargs):
        events.append(("merge", definition, state, kwargs))
        return {"notes": dict((state or {}).get("notes") or {})}

    class PageStore:
        def list_page_records(self, campaign_slug):
            events.append(("page_records", campaign_slug))
            return [valid_page, future_page, session_page]

    class StateStore:
        def replace_state(self, *args, **kwargs):
            events.append(("state", args, kwargs))

    def config(campaigns_dir, campaign_slug):
        events.append(("config", campaigns_dir, campaign_slug))
        return SimpleNamespace(characters_dir=character_dir.parent)

    def write(path, payload):
        events.append(("write", path.name, payload))

    return {
        "load_character_context": event("load", (campaign, record)),
        "campaign_supports_native_character_tools": event("supports", True),
        "redirect_unsupported_native_character_tools": event(
            "unsupported", "unsupported"
        ),
        "get_systems_service": event("systems", systems_service),
        "list_builder_campaign_page_records": event("builder_pages", ["builder"]),
        "get_campaign_page_store": event("page_store", PageStore()),
        "build_character_item_catalog": event("items", {"item": object()}),
        "render_character_edit_page": event("render", ("rendered", 200)),
        "parse_expected_revision": event("revision", 7),
        "finalize_character_definition_for_write": event(
            "finalize", updated_definition
        ),
        "has_session_mode_access": event("session_access", True),
        "native_level_up_readiness": event("readiness", {"status": "ready"}),
        "build_linked_feature_authoring_support": event(
            "linked", {"supported": True}
        ),
        "_build_spell_catalog": event("spell_catalog", {"spell": object()}),
        "_list_campaign_enabled_entries": enabled_entries,
        "build_native_character_edit_context": build_context,
        "get_current_user": event("user", user),
        "apply_native_character_edits": apply_edits,
        "merge_state_with_definition": merge,
        "load_campaign_character_config": config,
        "write_yaml": write,
        "character_state_store": StateStore(),
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    expected_order = [
        "load_character_context",
        "campaign_supports_native_character_tools",
        "redirect_unsupported_native_character_tools",
        "get_systems_service",
        "list_builder_campaign_page_records",
        "get_campaign_page_store",
        "build_character_item_catalog",
        "render_character_edit_page",
        "parse_expected_revision",
        "finalize_character_definition_for_write",
        "has_session_mode_access",
        "native_level_up_readiness",
        "build_linked_feature_authoring_support",
        "_build_spell_catalog",
        "_list_campaign_enabled_entries",
        "build_native_character_edit_context",
        "get_current_user",
        "apply_native_character_edits",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
        "character_state_store",
    ]
    direct = {
        "load_character_context",
        "campaign_supports_native_character_tools",
        "redirect_unsupported_native_character_tools",
        "get_systems_service",
        "list_builder_campaign_page_records",
        "get_campaign_page_store",
        "build_character_item_catalog",
        "render_character_edit_page",
        "parse_expected_revision",
        "finalize_character_definition_for_write",
    }
    forwarded = {
        "has_session_mode_access",
        "native_level_up_readiness",
        "build_linked_feature_authoring_support",
        "_build_spell_catalog",
        "_list_campaign_enabled_entries",
        "build_native_character_edit_context",
        "get_current_user",
        "apply_native_character_edits",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
    }
    expected = direct | forwarded | {"character_state_store"}
    assert [
        field.name for field in fields(route_module.CharacterEditRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_edit_routes.py").read_text(encoding="utf-8")
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
        and node.func.id == "register_character_edit_route"
    )
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterEditRouteDependencies"
    )
    values = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert set(values) == expected
    for name in direct:
        assert isinstance(values[name], ast.Name)
        assert values[name].id == name
    assert all(isinstance(values[name], ast.Lambda) for name in forwarded)
    assert isinstance(values["character_state_store"], ast.Name)
    assert values["character_state_store"].id == "character_state_store"


def test_forwarded_dependencies_remain_post_registration_monkeypatchable(
    app, monkeypatch
):
    dependencies = dict(
        zip(
            _handler(app).__code__.co_freevars,
            _handler(app).__closure__ or (),
        )
    )["dependencies"].cell_contents
    marker = object()
    monkeypatch.setattr(app_module, "has_session_mode_access", lambda *args: marker)
    monkeypatch.setattr(app_module, "get_current_user", lambda: marker)
    assert dependencies.has_session_mode_access("campaign", "character") is marker
    assert dependencies.get_current_user() is marker
    assert dependencies.character_state_store is app.extensions["character_state_store"]


def test_route_identity_methods_and_neighbor_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/edit"
    )
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert _handler(app).__name__ == ENDPOINT
    assert endpoints.index("character_progression_repair_view") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("character_retraining_view")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_builds_context_and_filters_pages_in_exact_order(
    app, monkeypatch, tmp_path, method
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    raw_view = _handler(app)
    with app.test_request_context(f"{ROUTE_PATH}?tab=features", method=method):
        response = raw_view(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response == ("rendered", 200)
    assert _event_names(events) == [
        "session_access",
        "load",
        "supports",
        "systems",
        "builder_pages",
        "readiness",
        "linked",
        "page_store",
        "page_records",
        "entries",
        "spell_catalog",
        "entries",
        "items",
        "edit_context",
        "render",
    ]
    context_event = next(event for event in events if event[0] == "edit_context")
    assert context_event[2]["form_values"] is None
    assert len(context_event[2]["campaign_page_records"]) == 1
    assert context_event[2]["state_notes"] == {"player": "Existing"}
    render_event = events[-1]
    assert render_event[2]["campaign_page_records"] == context_event[2][
        "campaign_page_records"
    ]


def test_unsupported_system_loads_first_then_redirects_without_catalog_work(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["campaign_supports_native_character_tools"] = (
        lambda campaign: events.append(("supports", campaign)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response == "unsupported"
    assert _event_names(events) == [
        "session_access",
        "load",
        "supports",
        "unsupported",
    ]


def test_post_preserves_edit_state_yaml_and_redirect_order(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={
            "expected_revision": "7",
            "physical_description_markdown": "Tall",
        },
    ):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response.status_code == 302
    names = _event_names(events)
    assert names[names.index("user") :] == [
        "user",
        "revision",
        "apply",
        "finalize",
        "merge",
        "state",
        "config",
        "write",
        "write",
    ]
    state_event = next(event for event in events if event[0] == "state")
    assert state_event[1][1]["notes"] == {
        "player": "Existing",
        "physical_description_markdown": "Tall",
        "background_markdown": "",
    }
    assert state_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}
    assert [event[1] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]


@pytest.mark.parametrize("error", (ValueError("invalid edit"), TypeError("bug")))
def test_validation_is_rendered_but_type_error_propagates(
    app, monkeypatch, tmp_path, error
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        raise error

    dependencies["apply_native_character_edits"] = fail
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH, method="POST"):
        if isinstance(error, TypeError):
            with pytest.raises(TypeError, match="bug"):
                _handler(app)(
                    campaign_slug="linden-pass", character_slug="arden-march"
                )
        else:
            response = _handler(app)(
                campaign_slug="linden-pass", character_slug="arden-march"
            )
            assert response == ("rendered", 200)
            render_event = events[-1]
            assert render_event[0] == "render"
            assert render_event[2]["status_code"] == 400
    assert "config" not in _event_names(events)
    assert "write" not in _event_names(events)


def test_yaml_fault_occurs_after_state_and_preserves_prior_definition_write(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def write(path, payload):
        events.append(("write", path.name, payload))
        if path.name == "import.yaml":
            raise RuntimeError("import write fault")

    dependencies["write_yaml"] = write
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match="import write fault"):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="arden-march"
            )

    names = _event_names(events)
    assert names.index("state") < names.index("write")
    assert [event[1] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
