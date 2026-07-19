from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.app as app_module
import player_wiki.character_progression_repair_routes as route_module
from player_wiki.character_store import CharacterStateConflictError


ENDPOINT = "character_progression_repair_view"
ROUTE_PATH = (
    "/campaigns/linden-pass/characters/arden-march/progression-repair"
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


def _event_names(events):
    return [event[0] for event in events]


def _fixtures(
    tmp_path: Path,
    events: list[object],
    *,
    readiness_statuses: list[dict[str, object]] | None = None,
):
    definition = SimpleNamespace(
        name="Arden March",
        system="DND-5E",
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    updated_definition = SimpleNamespace(
        name="Arden March",
        system="DND-5E",
        to_dict=lambda: {"character_slug": "arden-march", "repaired": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "imported"})
    state_record = SimpleNamespace(revision=7, state={"hp": {"current": 18}})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=state_record,
    )
    campaign = SimpleNamespace(system="DND-5E")
    user = SimpleNamespace(id=41)
    systems_service = object()
    character_dir = tmp_path / "characters" / "arden-march"
    readiness_results = list(
        readiness_statuses
        or [
            {"status": "repairable", "message": "Repair first."},
            {"status": "ready", "message": "Ready."},
        ]
    )

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def readiness(*args, **kwargs):
        result = readiness_results.pop(0)
        events.append(("readiness", args, kwargs, result))
        return result

    def build_context(*args, **kwargs):
        events.append(("context", args, kwargs))
        return {"values": kwargs.get("form_values")}

    def apply_repairs(*args, **kwargs):
        events.append(("apply", args, kwargs))
        return updated_definition, import_metadata

    class Coordinator:
        def __init__(self):
            self.expected_args = (
                record,
                updated_definition,
                import_metadata,
                {"hp": {"current": 18}},
            )

        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))

    def config(campaigns_dir, campaign_slug):
        events.append(("config", campaigns_dir, campaign_slug))
        return SimpleNamespace(characters_dir=character_dir.parent)

    def write(path, payload):
        events.append(("write", path.name, payload))

    return {
        "load_character_context": event("load", (campaign, record)),
        "campaign_supports_native_character_advancement": event(
            "supports", True
        ),
        "redirect_unsupported_native_character_tools": event(
            "unsupported", "unsupported"
        ),
        "list_builder_campaign_page_records": event(
            "builder_pages", ["builder-page"]
        ),
        "get_systems_service": event("systems", systems_service),
        "render_character_progression_repair_page": event(
            "render", ("rendered", 200)
        ),
        "parse_expected_revision": event("revision", 7),
        "finalize_character_definition_for_write": event(
            "finalize", updated_definition
        ),
        "can_manage_campaign_session": event("manager", True),
        "character_advancement_unsupported_message": event(
            "unsupported_message", "Unsupported advancement."
        ),
        "native_level_up_readiness": readiness,
        "build_imported_progression_repair_context": build_context,
        "get_current_user": event("user", user),
        "apply_imported_progression_repairs": apply_repairs,
        "merge_state_with_definition": event("merge", {"hp": {"current": 18}}),
        "character_publication_coordinator": Coordinator(),
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    expected_order = [
        "load_character_context",
        "campaign_supports_native_character_advancement",
        "redirect_unsupported_native_character_tools",
        "list_builder_campaign_page_records",
        "get_systems_service",
        "render_character_progression_repair_page",
        "parse_expected_revision",
        "finalize_character_definition_for_write",
        "can_manage_campaign_session",
        "character_advancement_unsupported_message",
        "native_level_up_readiness",
        "build_imported_progression_repair_context",
        "get_current_user",
        "apply_imported_progression_repairs",
        "merge_state_with_definition",
        "character_publication_coordinator",
    ]
    direct = set(expected_order[:8])
    forwarded = set(expected_order[8:-1])
    expected = direct | forwarded | {"character_publication_coordinator"}
    assert [
        field.name
        for field in fields(
            route_module.CharacterProgressionRepairRouteDependencies
        )
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_progression_repair_routes.py").read_text(
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
        and node.func.id == "register_character_progression_repair_route"
    )
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterProgressionRepairRouteDependencies"
    )
    values = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert set(values) == expected
    for name in direct:
        assert isinstance(values[name], ast.Name)
        assert values[name].id == name
    assert all(isinstance(values[name], ast.Lambda) for name in forwarded)
    assert isinstance(values["character_publication_coordinator"], ast.Name)
    assert values["character_publication_coordinator"].id == (
        "character_publication_coordinator"
    )


def test_forwarded_dependencies_and_captured_store_keep_composition_identity(
    app, monkeypatch
):
    dependencies = dict(
        zip(_handler(app).__code__.co_freevars, _handler(app).__closure__ or ())
    )["dependencies"].cell_contents
    marker = object()
    monkeypatch.setattr(
        app_module, "can_manage_campaign_session", lambda *args: marker
    )
    monkeypatch.setattr(app_module, "get_current_user", lambda: marker)
    assert dependencies.can_manage_campaign_session("campaign") is marker
    assert dependencies.get_current_user() is marker
    assert dependencies.character_publication_coordinator is app.extensions[
        "character_publication_coordinator"
    ]


def test_route_identity_methods_and_neighbor_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair"
    )
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert _handler(app).__name__ == ENDPOINT
    assert endpoints.index("character_level_up_view") < endpoints.index(
        "character_xianxia_cultivation_view"
    )
    assert endpoints.index("character_xianxia_cultivation_view") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index("character_edit_view")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_manager_denial_precedes_character_load(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["can_manage_campaign_session"] = (
        lambda campaign_slug: events.append(("manager", campaign_slug)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(Forbidden):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="arden-march"
            )

    assert _event_names(events) == ["manager"]


def test_invalid_character_load_stops_before_state_or_repair_work(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def missing(*args, **kwargs):
        events.append(("load", args, kwargs))
        raise NotFound()

    dependencies["load_character_context"] = missing
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(NotFound):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="../escape"
            )

    assert _event_names(events) == ["manager", "load"]


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_captures_but_does_not_forward_query_values(
    app, monkeypatch, tmp_path, method
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(
        f"{ROUTE_PATH}?class_ref=fighter&class_ref=wizard", method=method
    ):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response == ("rendered", 200)
    assert _event_names(events) == [
        "manager",
        "load",
        "supports",
        "builder_pages",
        "systems",
        "readiness",
        "systems",
        "context",
        "render",
    ]
    context_event = next(event for event in events if event[0] == "context")
    assert context_event[2]["form_values"] is None
    assert context_event[2]["campaign_page_records"] == ["builder-page"]
    assert events[-1][1][2]["state_revision"] == 7


def test_unsupported_system_loads_then_redirects_without_readiness_work(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["campaign_supports_native_character_advancement"] = (
        lambda campaign: events.append(("supports", campaign)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response == "unsupported"
    assert _event_names(events) == [
        "manager",
        "load",
        "supports",
        "unsupported_message",
        "unsupported",
    ]


@pytest.mark.parametrize(
    ("readiness", "expected_suffix"),
    (
        ({"status": "ready"}, "/characters/arden-march/level-up"),
        (
            {"status": "unsupported", "message": "Unsupported sheet."},
            "/characters/arden-march",
        ),
    ),
)
def test_terminal_readiness_redirects_before_context(
    app, monkeypatch, tmp_path, readiness, expected_suffix
):
    events: list[object] = []
    dependencies = _fixtures(
        tmp_path, events, readiness_statuses=[readiness]
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
    )

    assert response.status_code == 302
    assert response.location.endswith(expected_suffix)
    assert "context" not in _event_names(events)
    assert "state" not in _event_names(events)


def test_post_preserves_repair_state_yaml_and_redirect_order(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"expected_revision": "7", "class_ref": "fighter-phb"},
    ):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response.status_code == 302
    assert response.location.endswith(
        "/campaigns/linden-pass/characters/arden-march/level-up"
    )
    names = _event_names(events)
    assert names[names.index("context") :] == [
        "context",
        "user",
        "revision",
        "apply",
        "finalize",
        "systems",
        "readiness",
        "merge",
        "publish",
    ]
    context_event = next(event for event in events if event[0] == "context")
    assert context_event[2]["form_values"] == {
        "expected_revision": "7",
        "class_ref": "fighter-phb",
    }
    apply_event = next(event for event in events if event[0] == "apply")
    assert apply_event[1][3]["state_revision"] == 7
    assert apply_event[1][4] == context_event[2]["form_values"]
    finalize_event = next(event for event in events if event[0] == "finalize")
    assert finalize_event[2]["campaign"].system == "DND-5E"
    publish_event = next(event for event in events if event[0] == "publish")
    assert publish_event[1] == dependencies[
        "character_publication_coordinator"
    ].expected_args
    assert publish_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}


@pytest.mark.parametrize(
    ("error", "status"),
    (
        (ValueError("invalid repair"), 400),
        (CharacterStateConflictError(), 409),
        (TypeError("bug"), None),
    ),
)
def test_caught_errors_rerender_but_type_error_propagates(
    app, monkeypatch, tmp_path, error, status
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        raise error

    dependencies["apply_imported_progression_repairs"] = fail
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH, method="POST"):
        if status is None:
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
            assert render_event[2]["status_code"] == status
    assert "state" not in _event_names(events)
    assert "config" not in _event_names(events)
    assert "write" not in _event_names(events)


def test_publication_fault_surfaces_after_merge(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    class FaultCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise RuntimeError("publication fault")

    dependencies["character_publication_coordinator"] = FaultCoordinator()
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH, method="POST"):
        with pytest.raises(RuntimeError, match="publication fault"):
            _handler(app)(
                campaign_slug="linden-pass", character_slug="arden-march"
            )

    assert _event_names(events).index("merge") < _event_names(events).index(
        "publish"
    )


def test_publication_conflict_is_rendered_as_stale_state(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    class ConflictCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise CharacterStateConflictError()

    dependencies["character_publication_coordinator"] = ConflictCoordinator()
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH, method="POST"):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response == ("rendered", 200)
    assert events[-1][0] == "render"
    assert events[-1][2]["status_code"] == 409
