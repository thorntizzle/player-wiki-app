from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.app as app_module
from player_wiki.character_builder import CharacterBuildError
from player_wiki.character_store import CharacterStateConflictError
from werkzeug.exceptions import Forbidden, NotFound


ENDPOINT = "character_level_up_view"
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/level-up"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    dependency_cell = freevars.get("dependencies")
    if dependency_cell is not None:
        current = dependency_cell.cell_contents
        selected = {
            field.name: replacements[field.name]
            for field in fields(current)
            if field.name in replacements
        }
        monkeypatch.setattr(
            dependency_cell,
            "cell_contents",
            replace(current, **selected),
        )
        return

    for name, value in replacements.items():
        cell = freevars.get(name)
        if cell is not None:
            monkeypatch.setattr(cell, "cell_contents", value)
        else:
            monkeypatch.setattr(app_module, name, value)


def _event_names(events):
    return [event[0] for event in events]


def _fixtures(tmp_path: Path, events: list[object]):
    definition = SimpleNamespace(name="Arden", to_dict=lambda: {"level": 1})
    updated_definition = SimpleNamespace(
        name="Arden",
        to_dict=lambda: {"level": 2},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "native"})
    state_record = SimpleNamespace(revision=7, state={"hp": 10})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=state_record,
    )
    campaign = SimpleNamespace(system="DND-5E")
    user = SimpleNamespace(id=41)
    systems_service = object()
    character_dir = tmp_path / "characters" / "arden-march"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    class Repository:
        def get_campaign(self, campaign_slug):
            events.append(("campaign", campaign_slug))
            return campaign

    class StateStore:
        def replace_state(self, *args, **kwargs):
            events.append(("state", args, kwargs))

    def build_context(*args, **kwargs):
        events.append(("context", args, kwargs))
        return {"next_level": 2}

    def build_definition(*args, **kwargs):
        events.append(("build", args, kwargs))
        return updated_definition, import_metadata, 5

    def merge(definition, state, **kwargs):
        events.append(("merge", definition, state, kwargs))
        return {"hp": 15}

    def config(campaigns_dir, campaign_slug):
        events.append(("config", campaigns_dir, campaign_slug))
        return SimpleNamespace(characters_dir=character_dir.parent)

    def write(path, payload):
        events.append(("write", path.name, payload))

    return {
        "get_repository": event("repository", Repository()),
        "load_character_context": event("load", (campaign, record)),
        "campaign_supports_native_character_advancement": event("supports", True),
        "redirect_unsupported_native_character_tools": event(
            "unsupported", "unsupported"
        ),
        "list_builder_campaign_page_records": event("builder_pages", ["page"]),
        "get_systems_service": event("systems", systems_service),
        "character_sheet_return_href": event("sheet_return", "/sheet"),
        "render_character_level_up_page": event("render", ("rendered", 200)),
        "parse_expected_revision": event("revision", 7),
        "finalize_character_definition_for_write": event(
            "finalize", updated_definition
        ),
        "login_required": lambda handler: handler,
        "has_session_mode_access": event("session_access", True),
        "character_advancement_unsupported_message": event(
            "unsupported_message", "unsupported system"
        ),
        "native_level_up_readiness": event("readiness", {"status": "ready"}),
        "can_manage_campaign_session": event("manage", True),
        "build_native_level_up_context": build_context,
        "get_current_user": event("user", user),
        "build_native_level_up_character_definition": build_definition,
        "merge_state_with_definition": merge,
        "load_campaign_character_config": config,
        "write_yaml": write,
        "character_state_store": StateStore(),
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    route_module = importlib.import_module("player_wiki.character_level_up_routes")
    expected_order = [
        "get_repository",
        "load_character_context",
        "campaign_supports_native_character_advancement",
        "redirect_unsupported_native_character_tools",
        "list_builder_campaign_page_records",
        "get_systems_service",
        "character_sheet_return_href",
        "render_character_level_up_page",
        "parse_expected_revision",
        "finalize_character_definition_for_write",
        "login_required",
        "has_session_mode_access",
        "character_advancement_unsupported_message",
        "native_level_up_readiness",
        "can_manage_campaign_session",
        "build_native_level_up_context",
        "get_current_user",
        "build_native_level_up_character_definition",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
        "character_state_store",
    ]
    assert [
        field.name for field in fields(route_module.CharacterLevelUpRouteDependencies)
    ] == expected_order

    source_root = PROJECT_ROOT / "player_wiki"
    route_path = source_root / "character_level_up_routes.py"
    route_source = route_path.read_text(encoding="utf-8")
    route_tree = ast.parse(route_source)
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert "from .auth import login_required" not in route_source
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
        and node.func.id == "register_character_level_up_route"
    )
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterLevelUpRouteDependencies"
    )
    values = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    direct = set(expected_order[:11])
    forwarded = set(expected_order[11:-1])
    assert set(values) == direct | forwarded | {"character_state_store"}
    for name in direct:
        assert isinstance(values[name], ast.Name)
        assert values[name].id == name
    assert all(isinstance(values[name], ast.Lambda) for name in forwarded)
    assert isinstance(values["character_state_store"], ast.Name)
    assert values["character_state_store"].id == "character_state_store"


def test_forwarded_dependencies_remain_post_registration_monkeypatchable(app, monkeypatch):
    dependencies = dict(
        zip(_handler(app).__code__.co_freevars, _handler(app).__closure__ or ())
    )["dependencies"].cell_contents
    marker = object()
    monkeypatch.setattr(app_module, "has_session_mode_access", lambda *args: marker)
    monkeypatch.setattr(app_module, "native_level_up_readiness", lambda *args, **kwargs: marker)
    monkeypatch.setattr(app_module, "get_current_user", lambda: marker)
    assert dependencies.has_session_mode_access("campaign", "character") is marker
    assert dependencies.native_level_up_readiness(object(), "campaign", object()) is marker
    assert dependencies.get_current_user() is marker
    assert dependencies.character_state_store is app.extensions["character_state_store"]


def test_route_identity_methods_and_neighbor_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up"
    )
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert _handler(app).__name__ == ENDPOINT
    assert endpoints.index("character_import_xianxia_manual_view") < endpoints.index(
        ENDPOINT
    )
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "character_xianxia_cultivation_view"
    )
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_campaign_and_session_denials_precede_character_work(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["has_session_mode_access"] = (
        lambda *args: events.append(("session_access", args)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(Forbidden):
            _handler(app)(campaign_slug="linden-pass", character_slug="arden-march")

    assert _event_names(events) == ["repository", "campaign", "session_access"]

    events.clear()
    dependencies = _fixtures(tmp_path, events)
    dependencies["get_repository"] = lambda: SimpleNamespace(
        get_campaign=lambda campaign_slug: events.append(("campaign", campaign_slug))
        or None
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(NotFound):
            _handler(app)(campaign_slug="linden-pass", character_slug="arden-march")
    assert _event_names(events) == ["campaign"]


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_ready_read_builds_and_renders_in_exact_order(
    app, monkeypatch, tmp_path, method
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(
        f"{ROUTE_PATH}?choice=first&choice=second", method=method
    ):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response == ("rendered", 200)
    assert _event_names(events) == [
        "repository",
        "campaign",
        "session_access",
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
    assert context_event[1][3] == {"choice": "first"}
    assert context_event[2]["campaign_page_records"] == ["page"]
    assert events[-1][1][2]["state_revision"] == 7


def test_readiness_redirects_preserve_manager_and_player_branches(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    dependencies["native_level_up_readiness"] = (
        lambda *args, **kwargs: events.append(("readiness", args, kwargs))
        or {"status": "repairable", "message": "repair first"}
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )
    assert response.status_code == 302
    assert response.location.endswith(
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    assert _event_names(events)[-1] == "manage"

    events.clear()
    dependencies = _fixtures(tmp_path, events)
    dependencies["native_level_up_readiness"] = lambda *args, **kwargs: {
        "status": "repairable"
    }
    dependencies["can_manage_campaign_session"] = (
        lambda *args: events.append(("manage", args)) or False
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )
    assert response.location == "/sheet"
    assert _event_names(events)[-2:] == ["manage", "sheet_return"]


def test_unsupported_system_loads_before_friendly_redirect(
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
        "repository",
        "campaign",
        "session_access",
        "load",
        "supports",
        "unsupported_message",
        "unsupported",
    ]


def test_invalid_record_load_stops_before_state_builder_and_filesystem_work(
    app, monkeypatch, tmp_path
):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)

    def missing(*args):
        events.append(("load", args))
        raise NotFound()

    dependencies["load_character_context"] = missing
    _install_dependencies(app, monkeypatch, **dependencies)
    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(NotFound):
            _handler(app)(campaign_slug="linden-pass", character_slug="..")
    assert _event_names(events) == [
        "repository",
        "campaign",
        "session_access",
        "load",
    ]


def test_post_preserves_state_yaml_and_redirect_order(app, monkeypatch, tmp_path):
    events: list[object] = []
    dependencies = _fixtures(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    with app.test_request_context(
        ROUTE_PATH,
        method="POST",
        data={"expected_revision": "7", "class_row_id": "fighter"},
    ):
        response = _handler(app)(
            campaign_slug="linden-pass", character_slug="arden-march"
        )

    assert response.status_code == 302
    names = _event_names(events)
    assert names[names.index("user") :] == [
        "user",
        "revision",
        "build",
        "finalize",
        "merge",
        "state",
        "config",
        "write",
        "write",
        "sheet_return",
    ]
    context_event = next(event for event in events if event[0] == "context")
    assert context_event[1][3] == {
        "expected_revision": "7",
        "class_row_id": "fighter",
    }
    build_event = next(event for event in events if event[0] == "build")
    assert build_event[1][2] == {
        "next_level": 2,
        "state_revision": 7,
    }
    finalize_event = next(event for event in events if event[0] == "finalize")
    assert finalize_event[2]["campaign"].system == "DND-5E"
    merge_event = next(event for event in events if event[0] == "merge")
    assert merge_event[3] == {"hp_delta": 5}
    state_event = next(event for event in events if event[0] == "state")
    assert state_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}
    assert [event[1] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
    assert response.location == "/sheet"


@pytest.mark.parametrize(
    ("error", "status"),
    (
        (ValueError("invalid level up"), 400),
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

    dependencies["build_native_level_up_character_definition"] = fail
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
            assert events[-1][0] == "render"
            assert events[-1][2]["status_code"] == status
    assert "config" not in _event_names(events)
    assert "write" not in _event_names(events)


def test_yaml_fault_occurs_after_state_and_preserves_definition_write(
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
            _handler(app)(campaign_slug="linden-pass", character_slug="arden-march")

    names = _event_names(events)
    assert names.index("state") < names.index("write")
    assert [event[1] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
