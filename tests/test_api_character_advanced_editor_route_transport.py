from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor"
READ_ENDPOINT = "api.character_advanced_editor_read"
UPDATE_ENDPOINT = "api.character_advanced_editor_update"


def _raw_view(app, endpoint: str):
    return inspect.unwrap(app.view_functions[endpoint])


def _install_dependencies(app, endpoint: str, monkeypatch, **replacements) -> None:
    raw_view = _raw_view(app, endpoint)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    if "dependencies" in freevars:
        current = freevars["dependencies"].cell_contents
        monkeypatch.setattr(
            freevars["dependencies"],
            "cell_contents",
            replace(current, **replacements),
        )
        return

    closure_names = {
        "load_character_advanced_editor_target",
        "character_advanced_editor_is_supported",
        "build_character_advanced_editor_parts",
        "serialize_character_advanced_editor_response",
        "json_error",
        "load_json_object",
        "normalize_character_editor_values",
        "load_character_record",
        "finalize_character_definition_for_write",
    }
    for name, value in replacements.items():
        if name in closure_names and name in freevars:
            monkeypatch.setattr(freevars[name], "cell_contents", value)
        elif hasattr(api_module, name):
            monkeypatch.setattr(api_module, name, value)


def _fixtures(tmp_path: Path, events: list[tuple]):
    definition = SimpleNamespace(
        system="DND-5E",
        source={"source_type": "native_character_builder"},
        resource_templates=[],
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    updated_definition = SimpleNamespace(
        system="DND-5E",
        source={"source_type": "native_character_builder"},
        resource_templates=[],
        to_dict=lambda: {"character_slug": "arden-march", "updated": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "native"})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=4, state={"notes": {"player": "Old"}}),
    )
    refreshed = SimpleNamespace(
        definition=updated_definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=5, state={"notes": {"player": "New"}}),
    )
    campaign = SimpleNamespace(system="DND-5E", current_session=3)
    user = SimpleNamespace(id=71)
    character_dir = tmp_path / "characters" / "arden-march"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def parts(*args, **kwargs):
        events.append(("parts", args, kwargs))
        return (
            {"values": kwargs.get("form_values")},
            ["page"],
            {"optional": object()},
            {"spell": object()},
            {"item": object()},
            {"supported": True},
        )

    def apply(*args, **kwargs):
        events.append(("apply", args, kwargs))
        return updated_definition, import_metadata, {"item": 2}

    def merge(*args, **kwargs):
        events.append(("merge", args, kwargs))
        return {"notes": {"player": "Old"}}

    class StateStore:
        def replace_state(self, *args, **kwargs):
            events.append(("state", args, kwargs))

    def config(*args, **kwargs):
        events.append(("config", args, kwargs))
        return SimpleNamespace(characters_dir=character_dir.parent)

    def write(path, payload):
        events.append(("write", (path.name, payload), {}))

    return {
        "campaign": campaign,
        "record": record,
        "refreshed": refreshed,
        "state_store": StateStore(),
        "dependencies": {
            "load_character_advanced_editor_target": event(
                "target", (campaign, record, None)
            ),
            "character_advanced_editor_is_supported": event("supported", True),
            "build_character_advanced_editor_parts": parts,
            "serialize_character_advanced_editor_response": event(
                "serialize", ({"ok": True}, 200)
            ),
            "json_error": lambda message, status, *, code: (
                {"ok": False, "error": {"code": code, "message": message}},
                status,
            ),
            "load_json_object": event(
                "json", {"expected_revision": "4", "values": {" name ": ["old", "new"]}}
            ),
            "normalize_character_editor_values": event(
                "normalize", {"name": "new", "physical_description_markdown": "New"}
            ),
            "load_character_record": event("reload", refreshed),
            "finalize_character_definition_for_write": event(
                "finalize", updated_definition
            ),
            "get_current_user": event("user", user),
            "apply_native_character_edits": apply,
            "merge_state_with_definition": merge,
            "load_campaign_character_config": config,
            "write_yaml": write,
        },
    }


def test_advanced_editor_transport_has_exact_dependency_and_composition_shape() -> None:
    route_path = PROJECT_ROOT / "player_wiki" / "character_advanced_editor_api_routes.py"
    api_tree = ast.parse((PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8"))
    if not route_path.exists():
        inline = {
            node.name
            for node in ast.walk(api_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name in {"character_advanced_editor_read", "character_advanced_editor_update"}
        }
        assert inline == {"character_advanced_editor_read", "character_advanced_editor_update"}
        return

    route_module = importlib.import_module("player_wiki.character_advanced_editor_api_routes")
    assert [
        field.name
        for field in fields(route_module.CharacterAdvancedEditorApiDependencies)
    ] == [
        "api_campaign_scope_access_required",
        "api_login_required",
        "load_character_advanced_editor_target",
        "character_advanced_editor_is_supported",
        "build_character_advanced_editor_parts",
        "serialize_character_advanced_editor_response",
        "json_error",
        "load_json_object",
        "normalize_character_editor_values",
        "load_character_record",
        "finalize_character_definition_for_write",
        "get_current_user",
        "apply_native_character_edits",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
    ]
    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"character_advanced_editor_read", "character_advanced_editor_update"}
    }
    assert set(handlers) == {"character_advanced_editor_read", "character_advanced_editor_update"}
    assert all(node.decorator_list == [] for node in handlers.values())
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in handlers
        for node in ast.walk(api_tree)
    )
    registrations = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2

    dependency_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterAdvancedEditorApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    direct = {
        "api_campaign_scope_access_required",
        "api_login_required",
        "load_character_advanced_editor_target",
        "character_advanced_editor_is_supported",
        "build_character_advanced_editor_parts",
        "serialize_character_advanced_editor_response",
        "json_error",
        "load_json_object",
        "normalize_character_editor_values",
    }
    assert all(isinstance(by_name[name], ast.Name) for name in direct)
    assert all(isinstance(by_name[name], ast.Lambda) for name in set(by_name) - direct)


def test_advanced_editor_route_identity_methods_and_order(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    read = next(rule for rule in rules if rule.endpoint == READ_ENDPOINT)
    update = next(rule for rule in rules if rule.endpoint == UPDATE_ENDPOINT)
    assert read.rule == "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor"
    assert update.rule == read.rule
    assert read.methods == {"GET", "HEAD", "OPTIONS"}
    assert update.methods == {"PUT", "OPTIONS"}
    assert endpoints.index(READ_ENDPOINT) < endpoints.index(UPDATE_ENDPOINT)
    assert endpoints.index(UPDATE_ENDPOINT) < endpoints.index("api.character_retraining_read")
    assert endpoints.index(UPDATE_ENDPOINT) < endpoints.index("api.character_detail")
    assert client.options(ROUTE_PATH).status_code == 200
    assert client.post(ROUTE_PATH).status_code == 405
    assert client.delete(ROUTE_PATH).status_code == 405


def test_advanced_editor_read_preserves_supported_and_unsupported_order(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    _install_dependencies(
        app,
        READ_ENDPOINT,
        monkeypatch,
        **fixture["dependencies"],
    )
    with app.test_request_context(ROUTE_PATH):
        assert _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")[1] == 200
    assert [event[0] for event in events] == ["target", "supported", "parts", "serialize"]

    events.clear()
    _install_dependencies(
        app,
        READ_ENDPOINT,
        monkeypatch,
        character_advanced_editor_is_supported=lambda *args: events.append(
            ("supported", args, {})
        ) or False,
        build_character_advanced_editor_parts=lambda *args, **kwargs: pytest.fail(
            "unsupported GET built editor parts"
        ),
    )
    with app.test_request_context(ROUTE_PATH):
        _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["target", "supported", "serialize"]


def test_advanced_editor_update_preserves_full_commit_and_response_order(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]
    try:
        _install_dependencies(
            app,
            UPDATE_ENDPOINT,
            monkeypatch,
            **fixture["dependencies"],
        )
        with app.test_request_context(ROUTE_PATH, method="PUT", json={"ignored": True}):
            response = _raw_view(app, UPDATE_ENDPOINT)("linden-pass", "arden-march")
        assert response[1] == 200
    finally:
        app.extensions["character_state_store"] = original_store

    assert [event[0] for event in events] == [
        "target",
        "supported",
        "user",
        "json",
        "normalize",
        "parts",
        "apply",
        "finalize",
        "merge",
        "state",
        "config",
        "write",
        "write",
        "reload",
        "parts",
        "serialize",
    ]
    assert [event[1][0] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]


def test_advanced_editor_update_unsupported_excludes_user_json_and_parts(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported PUT performed eager work")

    fixture["dependencies"].update(
        character_advanced_editor_is_supported=lambda *args: False,
        get_current_user=forbidden,
        load_json_object=forbidden,
        build_character_advanced_editor_parts=forbidden,
    )
    _install_dependencies(app, UPDATE_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="PUT", json={}):
        response, status = _raw_view(app, UPDATE_ENDPOINT)("linden-pass", "arden-march")
    assert status == 400
    assert response["error"]["code"] == "unsupported_campaign_system"


@pytest.mark.parametrize("payload", [None, [], {}, {"expected_revision": "bad"}])
def test_advanced_editor_update_preserves_validation_taxonomy(
    app, client, users, set_campaign_visibility, sign_in, payload
) -> None:
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.put(ROUTE_PATH, json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_advanced_editor_post_state_fault_does_not_rollback(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]
    fixture["dependencies"]["write_yaml"] = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("definition write failed")
    )
    try:
        _install_dependencies(
            app,
            UPDATE_ENDPOINT,
            monkeypatch,
            **fixture["dependencies"],
        )
        with app.test_request_context(ROUTE_PATH, method="PUT", json={}):
            with pytest.raises(RuntimeError, match="definition write failed"):
                _raw_view(app, UPDATE_ENDPOINT)("linden-pass", "arden-march")
    finally:
        app.extensions["character_state_store"] = original_store
    assert "state" in [event[0] for event in events]
    assert [event[0] for event in events][-1] == "config"


def test_advanced_editor_helpers_and_retraining_cross_caller_stay_inline() -> None:
    tree = ast.parse((PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    helper_names = {
        "normalize_character_editor_values",
        "character_advanced_editor_is_supported",
        "build_character_advanced_editor_parts",
        "serialize_character_advanced_editor_response",
        "load_character_advanced_editor_target",
    }
    assert helper_names <= set(functions)
    retraining_links = functions["character_retraining_links"]
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "character_advanced_editor_is_supported"
        for node in ast.walk(retraining_links)
    )
